"""Offline kinematic dry run of Plan R (nominal grasps), stage by stage, with clearances."""
import json
import sys
import time
import numpy as np
from scipy.spatial.transform import Rotation
from bw_geom import *
from grasps import *
from plan_r import *

TX = float(sys.argv[1]) if len(sys.argv) > 1 else 0.96
s = Scene(layout=Layout(yaw_deg=-90.0, t=(TX, 0.055679, TABLE_Z)))
P = Planner(s)
p0, p1 = s.rail[0, :2], s.rail[-1, :2]
Gup, Gdn, Rg = pen("up", 0.033, -0.0275, 4.0), pen("down", 0.033, -0.0275, 4.0), ring()
FQ_PEN, FQ_RING, FQ_OPEN_PEN, FQ_OPEN_RING = -0.0056, -0.0023, -0.0089, -0.0053
back = lambda T, d: T @ T_from(np.eye(3), [0, 0, -d])
report = {}


def free_move(side, qa, qb, fq):
    path = rrt_connect(P, side, qa, qb, fq)
    return densify(path), {}


q = {"left": np.zeros(6), "right": np.zeros(6)}
traj = {"left": [], "right": []}


def log(name, worst=None, extra=None):
    report[name] = dict(worst_mm={k: round(v * 1000, 1) for k, v in (worst or {}).items()}, **(extra or {}))
    print(name, report[name], flush=True)


def add(side, qs):
    traj[side] += [np.array(x) for x in qs]
    if qs:
        q[side] = np.array(qs[-1])


try:
    t0 = time.time()
    # ---- 1. right G_up pick at the start
    W0 = T_from(s.start_R.as_matrix(), s.start_p)
    Tg = W0 @ Gup
    best = None
    for d in (0.04, 0.03, 0.05):
        try:
            qpre, c = P.ik_best("right", back(Tg, d), FQ_OPEN_PEN)
            mv, w1 = free_move("right", q["right"], qpre, OPEN)
            ap, w2 = P.cart_move("right", back(Tg, d), Tg, qpre, FQ_OPEN_PEN)
            best = (d, mv, ap, w1, w2)
            break
        except PlanError as e:
            print("  pick approach", d, e)
    if best is None:
        raise PlanError("pick approach")
    add("right", best[1] + best[2])
    log("1_pick_right", {**best[3]}, dict(approach_m=best[0], approach_worst_mm={k: round(v * 1000, 1) for k, v in best[4].items()}))
    # ---- 2. lift to 55 mm with a 40 deg tilt
    h0 = s.start_R.apply([1, 0, 0]); h0[2] = 0; h0 /= np.linalg.norm(h0)
    BETA, HZ1 = 40.0, 0.055
    n2 = Rotation.from_rotvec(np.radians(BETA) * h0).apply([0, 0, 1.0])
    W1 = T_from(s.start_R.as_matrix(), s.start_p + [0, 0, 0.003])
    W2 = T_from(frame_h_n(h0, n2), np.r_[p0, s.deck_top + HZ1])
    variants = []
    for zf in (0.02, 0.03, 0.04):
        for zt in (zf, zf + 0.01):
            for bt in (20.0, 40.0):
                variants.append((zf, zt, bt))
    res2 = None
    for zf, zt, bt in variants:
        nt = Rotation.from_rotvec(np.radians(bt) * h0).apply([0, 0, 1.0])
        W1b = T_from(frame_h_n(h0, [0, 0, 1]), np.r_[p0, s.deck_top + zf])
        W1c = T_from(frame_h_n(h0, nt), np.r_[p0, s.deck_top + zt])
        Ws = interp_T(W0, W1, 3)
        for Wa, Wb in ((W1, W1b), (W1b, W1c), (W1c, W2)):
            Ws += interp_T(Wa, Wb, n_steps(Wa, Wb))
        try:
            qs, w = P.track("right", [W @ Gup for W in Ws], q["right"], FQ_PEN, ignore=("stops",))
            res2 = (zf, zt, bt)
            break
        except PlanError as e:
            print("  lift variant", zf, zt, bt, e)
    if res2 is None:
        raise PlanError("lift/tilt")
    report["lift_variant"] = res2
    print("  lift variant OK", res2)
    add("right", qs)
    log("2_lift_tilt_right", w)
    # ---- 3. left ring grip (handover 1), right releases and parks
    Tr = W2 @ Rg
    best = None
    for d in (0.04, 0.03, 0.05, 0.02):
        try:
            qpre, c = P.ik_best("left", back(Tr, d), FQ_OPEN_RING)
            mv, w1 = free_move("left", q["left"], qpre, OPEN)
            ap, w2 = P.cart_move("left", back(Tr, d), Tr, qpre, FQ_OPEN_RING)
            best = (d, mv, ap, w1, w2)
            break
        except PlanError as e:
            print("  ring approach", d, e)
    if best is None:
        raise PlanError("ring approach")
    add("left", best[1] + best[2])
    log("3a_ring_grip_left", best[3], dict(approach_m=best[0], approach_worst_mm={k: round(v * 1000, 1) for k, v in best[4].items()}))
    Tcur = W2 @ Gup
    qs, w = P.cart_move("right", Tcur, back(Tcur, 0.05), q["right"], OPEN)
    add("right", qs)
    qs2, w2 = free_move("right", q["right"], np.zeros(6), OPEN)
    add("right", qs2)
    log("3b_right_release_park", w, dict(park_worst_mm={k: round(v * 1000, 1) for k, v in w2.items()}))
    # ---- 4. left: untilt + yaw to h=+x on the start post, then carry along the rail
    z_start = s.rail[0, 2]
    a1 = HZ1 + s.deck_top - z_start            # arc length where the loop sits on the start post
    W3 = T_from(frame_h_n([1, 0, 0], [0, 0, 1]), np.r_[p0, s.deck_top + HZ1])
    Ws = interp_T(W2, W3, n_steps(W2, W3))
    qs, w = P.track("left", [W @ Rg for W in Ws], q["left"], FQ_RING)
    add("left", qs)
    log("4a_untilt_yaw_left", w)
    HZ2 = 0.062
    a2 = s.arc[-1] - (HZ2 + s.deck_top - s.rail[-1, 2])
    Ws = P.wand_route(a1, a2, h=(1, 0, 0))
    qs, w = P.track("left", [W @ Rg for W in Ws], q["left"], FQ_RING, check_every=8)
    add("left", qs)
    log("4b_carry_left", w, dict(n=len(Ws)))
    W4 = Ws[-1]
    # ---- 5. yaw to -120 deg on the finish post
    Ws = P.wand_yaw(W4, p1, -120.0)
    qs, w = P.track("left", [W @ Rg for W in Ws], q["left"], FQ_RING)
    add("left", qs)
    W5 = Ws[-1]
    log("5_yaw_finish_left", w)
    # ---- 6. right G_down (handover 2); left releases and parks
    Td = W5 @ Gdn
    best = None
    for d in (0.04, 0.03, 0.05):
        try:
            qpre, c = P.ik_best("right", back(Td, d), FQ_OPEN_PEN)
            mv, w1 = free_move("right", q["right"], qpre, OPEN)
            ap, w2 = P.cart_move("right", back(Td, d), Td, qpre, FQ_OPEN_PEN)
            best = (d, mv, ap, w1, w2)
            break
        except PlanError as e:
            print("  gdown approach", d, e)
    if best is None:
        raise PlanError("G_down approach right")
    add("right", best[1] + best[2])
    log("6a_gdown_right", best[3], dict(approach_m=best[0], approach_worst_mm={k: round(v * 1000, 1) for k, v in best[4].items()}))
    Tcur = W5 @ Rg
    qs, w = P.cart_move("left", Tcur, back(Tcur, 0.05), q["left"], OPEN)
    add("left", qs)
    qs2, w2 = free_move("left", q["left"], np.zeros(6), OPEN)
    add("left", qs2)
    log("6b_left_release_park", w, dict(park_worst_mm={k: round(v * 1000, 1) for k, v in w2.items()}))
    # ---- 7. right lowers onto the deck, yaws to 180 deg, releases, parks
    Rfd = (s.finish_R * Rotation.from_euler("x", 180, degrees=True)).as_matrix()
    ang_f = np.degrees(np.arctan2(Rfd[1, 0], Rfd[0, 0]))
    Rz = lambda d: Rotation.from_euler("z", d, degrees=True).as_matrix()
    W6 = T_from(Rz(-120.0 - ang_f) @ Rfd, np.r_[p1, s.finish_p[2] + 0.0015])
    Ws = interp_T(W5, W6, n_steps(W5, W6))
    qs, w = P.track("right", [W @ Gdn for W in Ws], q["right"], FQ_PEN, ignore=("stops",))
    add("right", qs)
    log("7a_lower_right", w)
    Ws = P.wand_yaw(W6, p1, -60.0)
    qs, w = P.track("right", [W @ Gdn for W in Ws], q["right"], FQ_PEN, ignore=("stops",))
    add("right", qs)
    W7 = Ws[-1]
    log("7b_yaw_deck_right", w)
    Tcur = W7 @ Gdn
    qs, w = P.cart_move("right", Tcur, back(Tcur, 0.05), q["right"], OPEN)
    add("right", qs)
    qs2, w2 = free_move("right", q["right"], np.zeros(6), OPEN)
    add("right", qs2)
    log("7c_right_release_park", w, dict(park_worst_mm={k: round(v * 1000, 1) for k, v in w2.items()}))
    # ---- 8. left G_down from the front, yaw to the finish pose, release, park
    Tg = W7 @ Gdn
    best = None
    for d in (0.04, 0.03, 0.05):
        try:
            qpre, c = P.ik_best("left", back(Tg, d), FQ_OPEN_PEN)
            mv, w1 = free_move("left", q["left"], qpre, OPEN)
            ap, w2 = P.cart_move("left", back(Tg, d), Tg, qpre, FQ_OPEN_PEN)
            best = (d, mv, ap, w1, w2)
            break
        except PlanError as e:
            print("  final approach", d, e)
    if best is None:
        raise PlanError("final approach left")
    add("left", best[1] + best[2])
    log("8a_gdown_left", best[3])
    Ws = P.wand_yaw(W7, p1, ang_f - 180.0)
    qs, w = P.track("left", [W @ Gdn for W in Ws], q["left"], FQ_PEN, ignore=("stops",))
    add("left", qs)
    W8 = Ws[-1]
    log("8b_yaw_final_left", w, dict(final_err_mm=float(np.linalg.norm(W8[:3, 3] - s.finish_p) * 1000),
                                     final_ang_deg=float(np.degrees(Rotation.from_matrix(W8[:3, :3] @ Rfd.T).magnitude()))))
    Tcur = W8 @ Gdn
    qs, w = P.cart_move("left", Tcur, back(Tcur, 0.05), q["left"], OPEN)
    add("left", qs)
    qs2, w2 = free_move("left", q["left"], np.zeros(6), OPEN)
    add("left", qs2)
    log("8c_left_release_park", w, dict(park_worst_mm={k: round(v * 1000, 1) for k, v in w2.items()}))
    print("PLAN_OK in %.0f s" % (time.time() - t0))
except PlanError as e:
    print("PLAN_FAIL", e)
np.savez(f"../../results/plan_r_offline_{TX:.3f}.npz", left=np.array(traj["left"]), right=np.array(traj["right"]))
json.dump(report, open(f"../../results/plan_r_offline_{TX:.3f}.json", "w"), indent=1)
