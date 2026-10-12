"""Reach study of key wand poses for both YAM arms (numpy model; no Isaac)."""
import sys, json
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from ik import IK, frame


def wand_T(p, R):
    return T_from(R.as_matrix() if hasattr(R, "as_matrix") else R, p)


def yaw_about_post(scene, p, R, post_xy, deg):
    Rz = Rotation.from_euler("z", deg, degrees=True)
    c = np.r_[post_xy, 0.0]
    p2 = Rz.apply(p - c) + c
    p2[2] = p[2]
    return p2, Rz * R


def main(tx=0.7645, out=None):
    s = Scene(layout=Layout(t=(tx, 0.055679, TABLE_Z)))
    iks = {k: IK(k) for k in ("left", "right")}
    AP = {k: ArmPoints(iks[k].arm) for k in iks}
    poses = {}
    sp, sR = s.start_p, s.start_R
    fp, fR = s.finish_p, s.finish_R
    post0, post1 = s.rail[0, :2], s.rail[-1, :2]
    # start: pen grip under the span (handle inward), then yawed so the handle points to the robot (-x)
    ang0 = np.degrees(np.arctan2(sR.apply([1, 0, 0])[1], sR.apply([1, 0, 0])[0]))
    for k, d in [("start_pen_inward", 0.0), ("start_pen_mid", (-180 - ang0) / 2), ("start_pen_front", -180 - ang0)]:
        p, R = yaw_about_post(s, sp, sR, post0, d)
        poses[k] = (p, R, pen("up", 0.033, -0.0275, 4.0))
    p, R = yaw_about_post(s, sp, sR, post0, -180 - ang0)
    poses["start_top_A"] = (p, R, topdown("A"))
    # up the post: lift 100 mm, loop flat, handle to the robot
    Rf = Rotation.from_euler("z", 180, degrees=True)  # wand x -> -x world, z up
    for h in [0.03, 0.08, 0.10]:
        poses[f"post0_up{int(h*1000)}_A"] = (np.r_[post0, s.rail[0, 2] + h], Rf, topdown("A"))
    # span: loop normal along the route (-y), handle -x
    Rspan = Rotation.from_matrix(np.column_stack([[-1, 0, 0], [0, 0, -1], [0, -1, 0]]))  # x=-x, y=-z, z=-y
    zs = s.rail[:, 2].max()
    for y in [0.12, 0.06, 0.0, -0.06, -0.12]:
        poses[f"span_y{int(y*100)}_A"] = (np.array([post0[0], y, zs]), Rspan, topdown("A"))
        poses[f"span_y{int(y*100)}_B"] = (np.array([post0[0], y, zs]), Rspan, topdown("B"))
    # finish post: face-down wand (z down), handle -x
    Rfd = Rotation.from_matrix(np.column_stack([[-1, 0, 0], [0, 1, 0], [0, 0, -1]]))
    for h in [0.10, 0.03]:
        poses[f"post1_up{int(h*1000)}_B"] = (np.r_[post1, s.rail[-1, 2] + h], Rfd, topdown("B"))
    # finish on the deck, handle to the robot, then pen yaw to the final pose
    ang1 = np.degrees(np.arctan2(fR.apply([1, 0, 0])[1], fR.apply([1, 0, 0])[0]))
    fRd = fR * Rotation.from_euler("x", 180, degrees=True)  # symmetric face-down finish pose
    for k, d in [("finish_top_B", 180 - ang1), ]:
        p, R = yaw_about_post(s, fp, fRd, post1, d)
        poses[k] = (p, R, topdown("B"))
    for k, d in [("finish_pen_front", 180 - ang1), ("finish_pen_mid", (180 - ang1) / 2), ("finish_pen_final", 0.0)]:
        p, R = yaw_about_post(s, fp, fRd, post1, d)
        poses[k] = (p, R, pen("down", 0.033, -0.0275, 4.0))
    res = {}
    for k, (p, R, Tg) in poses.items():
        T = wand_T(p, R) @ Tg
        row = {}
        for side in ("left", "right"):
            q, sols = iks[side].solve_multi(T[:3, 3], T[:3, :3], np.eye(4), n_random=60)
            if q is None:
                row[side] = None
                continue
            # pick the solution with the best clearance
            best = None
            for qq in sols:
                W = AP[side].world(qq, -0.0056)
                c = clearances(s, W)
                score = min(c["wire"], c["deck"], c["stops"], c["table"])
                if best is None or score > best[0]:
                    best = (score, qq, c)
            row[side] = dict(n=len(sols), q=np.round(best[1], 3).tolist(), clear={a: round(b * 1000, 1) for a, b in best[2].items()})
        res[k] = row
        print(k, {sd: (None if v is None else (v["n"], v["clear"])) for sd, v in row.items()}, flush=True)
    if out:
        json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.7645, sys.argv[2] if len(sys.argv) > 2 else None)
