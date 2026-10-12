"""Layout sweep for plan P: key-pose IK feasibility + rest-pose clearance for candidate re-layouts."""
import json
import sys
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import IK


def handle_frame(hdir, normal):
    x = np.asarray(hdir, float)
    z = np.asarray(normal, float)
    z = z - x * np.dot(x, z)
    z /= np.linalg.norm(z)
    return Rotation.from_matrix(np.column_stack([x, np.cross(z, x), z]))


def best_sol(ik, AP, s, T, finger=-0.0056, n_random=60):
    q, sols = ik.solve_multi(T[:3, 3], T[:3, :3], np.eye(4), n_random=n_random)
    if q is None:
        return None
    best = None
    for qq in sols:
        c = clearances(s, AP.world(qq, finger))
        sc = min(c.values())
        if best is None or sc > best[0]:
            best = (sc, qq, c)
    return dict(n=len(sols), min_clear_mm=round(best[0] * 1000, 1), clear={k: round(v * 1000, 1) for k, v in best[2].items()})


def evaluate(yaw, tx, ty, carry_arm, finish_arm):
    s = Scene(layout=Layout(yaw_deg=yaw, t=(tx, ty, TABLE_Z)))
    iks = {k: IK(k) for k in ("left", "right")}
    APs = {k: ArmPoints(iks[k].arm) for k in iks}
    out = dict(layout=dict(yaw=yaw, tx=tx, ty=ty), carry_arm=carry_arm, finish_arm=finish_arm)
    # rest-pose clearance (fingers open)
    out["rest_clear_mm"] = {k: round(min(clearances(s, APs[k].world(np.zeros(6), -0.0475)).values()) * 1000, 1) for k in iks}
    tang = s.tangents()
    # wire plane normal (planar tiers): perpendicular to the span direction, horizontal
    span = s.rail[-1] - s.rail[0]
    span[2] = 0
    span /= np.linalg.norm(span)
    side = np.cross([0, 0, 1.0], span)          # horizontal, perpendicular to the wire plane
    base = np.array(iks[carry_arm].arm.base[:3, 3])
    if np.dot(base[:2] - s.rail[0, :2], side[:2]) < 0:
        side = -side                            # handle points toward the carrying arm's side
    Gup, Gdn = pen("up", 0.033, -0.0275, 4.0), pen("down", 0.033, -0.0275, 4.0)
    ikC, APC = iks[carry_arm], APs[carry_arm]
    ikF, APF = iks[finish_arm], APs[finish_arm]
    poses = {}
    poses["K1_start_grasp"] = (s.start_p + [0, 0, 0.0015], s.start_R, Gup, ikC, APC)
    poses["K2_start_flat_side"] = (np.r_[s.rail[0, :2], s.start_p[2] + 0.004], handle_frame(side, [0, 0, 1]), Gup, ikC, APC)
    for name, frac in [("K3a_elbow1", 0.25), ("K3b_span_mid", 0.5), ("K3c_elbow2", 0.75), ("K3d_post1_top", 0.88)]:
        sarc = frac * s.arc[-1]
        p = np.array([np.interp(sarc, s.arc, s.rail[:, k]) for k in range(3)])
        t = np.array([np.interp(sarc, s.arc, tang[:, k]) for k in range(3)])
        poses[name] = (p, handle_frame(side, t), Gup, ikC, APC)
    # drop: face-down wand, handle to the side, loop centre ~55 mm above the deck
    poses["K4_drop"] = (np.r_[s.rail[-1, :2], s.deck_top + 0.055], handle_frame(side, [0, 0, -1]), Gup, ikC, APC)
    # finish arm: face-down wand on the deck, handle to the side -> final pose
    Rfin = s.finish_R * Rotation.from_euler("x", 180, degrees=True)
    poses["K5a_finish_side"] = (s.finish_p + [0, 0, 0.0015], handle_frame(side, [0, 0, -1]) , Gdn, ikF, APF)
    hf = Rfin.apply([1, 0, 0])
    hm = (hf + side) / np.linalg.norm(hf + side)
    poses["K5b_finish_mid"] = (s.finish_p + [0, 0, 0.0015], handle_frame(hm, [0, 0, -1]), Gdn, ikF, APF)
    poses["K5c_finish_final"] = (s.finish_p + [0, 0, 0.0015], Rfin, Gdn, ikF, APF)
    for k, (p, R, Tg, ik, AP) in poses.items():
        T = T_from(R.as_matrix(), p) @ Tg
        out[k] = best_sol(ik, AP, s, T)
    return out


if __name__ == "__main__":
    cands = [
        (-90.0, 0.7645, 0.055679, "right", "left"),
        (-90.0, 0.9700, 0.055679, "right", "left"),
        (180.0, 0.6257, -0.270, "right", "left"),
        (180.0, 0.6257, -0.270, "right", "right"),
        (0.0, 0.5144, 0.270, "right", "left"),
        (0.0, 0.5144, 0.270, "right", "right"),
        (180.0, 0.6257, -0.270, "left", "left"),
        (0.0, 0.5144, 0.270, "left", "right"),
    ]
    sel = [int(a) for a in sys.argv[1:]] or range(len(cands))
    for i in sel:
        r = evaluate(*cands[i])
        print(json.dumps(r), flush=True)
