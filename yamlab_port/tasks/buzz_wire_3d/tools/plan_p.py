"""Plan P (numpy, offline): wand path for the buzz-wire oracle and per-phase IK feasibility.

Right arm, pen grip camera-up (G_up) under the span at the start post -> yaw the handle to the robot side
-> carry the loop along the whole rail (handle kept at -x, loop normal along the tangent) -> on the
finish post lower until the gripper is just above the deck -> release (short drop onto the deck).
Left arm, pen grip camera-up on the face-down wand (G_down) -> yaw the handle inward (finish pose) ->
release -> retreat.
"""
import json
import sys
import numpy as np
from scipy.spatial.transform import Rotation, Slerp
from bw_geom import *
from grasps import *
from ik import IK


def frames_along_rail(scene, s_from, s_to, ds=0.002):
    """Wand poses with the loop centre on the rail centreline, normal = tangent, handle = -x world."""
    arc = scene.arc
    tang = scene.tangents()
    out = []
    n = max(2, int(abs(s_to - s_from) / ds) + 1)
    for s in np.linspace(s_from, s_to, n):
        p = np.array([np.interp(s, arc, scene.rail[:, k]) for k in range(3)])
        t = np.array([np.interp(s, arc, tang[:, k]) for k in range(3)])
        t /= np.linalg.norm(t)
        x = np.array([-1.0, 0.0, 0.0])
        x = x - t * np.dot(x, t)
        x /= np.linalg.norm(x)
        y = np.cross(t, x)
        out.append((p, Rotation.from_matrix(np.column_stack([x, y, t]))))
    return out


def yaw_frames(p, R, post_xy, deg_total, step_deg=2.0, dz=0.0):
    out = []
    n = max(2, int(abs(deg_total) / step_deg) + 1)
    c = np.r_[post_xy, 0.0]
    for a in np.linspace(0, deg_total, n):
        Rz = Rotation.from_euler("z", a, degrees=True)
        q = Rz.apply(p - c) + c
        q[2] = p[2] + dz
        out.append((q, Rz * R))
    return out


def track(ik, frames, Tg, q0, AP=None, scene=None, check_every=5, finger=-0.0056):
    qs, worst, fails = [], dict(wire=1, deck=1, stops=1, table=1), 0
    q = np.array(q0, float)
    for k, (p, R) in enumerate(frames):
        T = T_from(R.as_matrix(), p) @ Tg
        q, ok, e = ik.solve(T[:3, 3], T[:3, :3], np.eye(4), q, iters=200)
        if not ok:
            fails += 1
        if qs and np.abs(q - qs[-1]).max() > 0.2:
            fails += 1000  # discontinuity
        qs.append(q.copy())
        if AP is not None and (k % check_every == 0 or k == len(frames) - 1):
            c = clearances(scene, AP.world(q, finger))
            for kk in worst:
                worst[kk] = min(worst[kk], c[kk])
    return np.array(qs), fails, worst


def main(tx=0.7645):
    s = Scene(layout=Layout(t=(tx, 0.055679, TABLE_Z)))
    ikR, ikL = IK("right"), IK("left")
    APR, APL = ArmPoints(ikR.arm), ArmPoints(ikL.arm)
    post0, post1 = s.rail[0, :2], s.rail[-1, :2]
    Gup = pen("up", 0.033, -0.0275, 4.0)
    Gdn = pen("down", 0.033, -0.0275, 4.0)
    report = {}
    # ---- phase 1: grasp at the start pose, yaw to the robot side (lift 1.5 mm)
    ang0 = np.degrees(np.arctan2(*s.start_R.apply([1, 0, 0])[[1, 0]]))
    yaw1 = -180.0 - ang0 if -180.0 - ang0 > -180 else 180.0 - ang0
    fr1 = yaw_frames(s.start_p + [0, 0, 0.0015], s.start_R, post0, yaw1)
    T = T_from(fr1[0][1].as_matrix(), fr1[0][0]) @ Gup
    q0, sols = ikR.solve_multi(T[:3, 3], T[:3, :3], np.eye(4), n_random=80)
    best = None
    for qq in sols:
        qs, fails, worst = track(ikR, fr1, Gup, qq, APR, s, check_every=10)
        sc = (fails, -min(worst.values()))
        if best is None or sc < best[0]:
            best = (sc, qq, qs, worst)
    report["yaw_start"] = dict(yaw_deg=yaw1, fails=best[0][0], worst_mm={k: v * 1000 for k, v in best[3].items()})
    qs1 = best[2]
    print("phase1 yaw", report["yaw_start"], flush=True)
    # ---- phase 2: flatten the wand (handle -x, loop normal +z) and lift to the rail start
    p_end, R_end = fr1[-1]
    R_flat = Rotation.from_matrix(np.column_stack([[-1, 0, 0], [0, -1, 0], [0, 0, 1]]))
    lift = []
    p_a = np.r_[post0, p_end[2]]
    for u in np.linspace(0, 1, 15):
        lift.append((p_a + [0, 0, 0.004 * u], Slerp([0, 1], Rotation.concatenate([R_end, R_flat]))(u)))
    z_start = s.rail[0, 2]
    for z in np.arange(p_a[2] + 0.004, z_start, 0.002):
        lift.append((np.r_[post0, z], R_flat))
    route = frames_along_rail(s, 0.0, s.arc[-1])
    fr2 = lift + route
    qs2, fails2, worst2 = track(ikR, fr2, Gup, qs1[-1], APR, s, check_every=10)
    report["carry"] = dict(fails=fails2, worst_mm={k: v * 1000 for k, v in worst2.items()}, n=len(fr2))
    print("phase2 carry", report["carry"], flush=True)
    # ---- phase 3: down the finish post (handle -x, face down) until the gripper is 3 mm above the deck
    R_fd = Rotation.from_matrix(np.column_stack([[-1, 0, 0], [0, 1, 0], [0, 0, -1]]))
    zs = np.arange(s.rail[-1, 2], s.deck_top + 0.02, -0.002)
    fr3 = []
    lowest = None
    q = qs2[-1]
    for z in zs:
        p = np.r_[post1, z]
        T = T_from(R_fd.as_matrix(), p) @ Gup
        q, ok, e = ikR.solve(T[:3, 3], T[:3, :3], np.eye(4), q, iters=200)
        c = clearances(s, APR.world(q, -0.0056))
        if not ok or c["deck"] < 0.003 or c["stops"] < 0.001:
            break
        fr3.append((p, R_fd))
        lowest = (z, c)
    report["descend"] = dict(lowest_loop_z_above_deck_mm=(lowest[0] - s.deck_top) * 1000, clear_mm={k: v * 1000 for k, v in lowest[1].items()})
    print("phase3 descend", report["descend"], flush=True)
    # ---- phase 5: left arm on the face-down wand at the finish, handle -x -> finish pose
    R_fin_dn = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
    ang1 = np.degrees(np.arctan2(*R_fin_dn.apply([1, 0, 0])[[1, 0]]))
    yaw5 = ang1 - 180.0 if ang1 > 0 else ang1 + 180.0
    p_start5 = s.finish_p.copy()
    R_start5 = Rotation.from_euler("z", -yaw5, degrees=True) * R_fin_dn
    fr5 = yaw_frames(p_start5 + [0, 0, 0.0015], R_start5, post1, yaw5)
    T = T_from(fr5[0][1].as_matrix(), fr5[0][0]) @ Gdn
    q0, sols = ikL.solve_multi(T[:3, 3], T[:3, :3], np.eye(4), n_random=80)
    best = None
    for qq in sols:
        qs, fails, worst = track(ikL, fr5, Gdn, qq, APL, s, check_every=10)
        sc = (fails, -min(worst.values()))
        if best is None or sc < best[0]:
            best = (sc, qq, qs, worst)
    report["yaw_finish"] = dict(yaw_deg=yaw5, fails=best[0][0] if best else None,
                                worst_mm={k: v * 1000 for k, v in best[3].items()} if best else None)
    print("phase5 yaw", report["yaw_finish"], flush=True)
    json.dump(report, open(f"../plan_p_{tx:.4f}.json", "w"), indent=1)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.7645)
