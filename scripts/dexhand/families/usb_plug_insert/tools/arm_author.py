#!/usr/bin/env python3
"""Authoring only (not shipped): re-author the USB oracle on the Marvin right arm.

The accepted floating-stage episode (wave 2) is the reference: its achieved hand-root world poses after every control
(``--poses``, recorded by the wave-3 rig tool ``family_poses.py``) and its finger rows (``--old-rows``). The arm
(``arm_ik.track``: damped-least-squares IK + joint integral) follows

* controls 0-459 (approach, pinch, lift, transport/rotate): the old achieved hand-root poses (``--lead`` controls ahead);
* controls 460-784 (alignment in front of the desk edge, approach, insertion): the old controller's closed loop on the
  measured plug pose (the same goal schedule, plug-position integral and rate limits as the wave-2 ``demo.py``);
* controls 785-: (release, withdraw, hold): the old hand-root motion relative to its pose at control 785.

Between the lift and the alignment the arm changes IK branch (the pick and the under-the-edge insertion lie on
different branches): a joint-space move through a sampled waypoint that keeps every arm link, the stand and the
parked hand out of contact (``--plan``). The executed rows are recorded (open-loop replayable) and padded with
``--slack`` copies of the last row. ``reference/floating_oracle.npz``: the wave-2 floating-stage oracle rows
(``actions``) and its achieved hand-root world poses after every control (``right_pos``, ``right_mat``).

The packaged solution (success at control 1,475) is reproduced by

  arm_author.py --base 0.93 -0.52 -0.1 --yaw 135 --plan --plan-margin 0.01 --n-joint 450 --box-ymin -0.25 \
      --box-zmax 0.95 --release-stretch 2 --straighten-middle-at 900 --out DIR
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
FAMILY = HERE.parent
sys.path.insert(0, str(FAMILY))
sys.path.append(str(FAMILY.parents[1] / "shared"))
os.chdir(FAMILY)

import numpy as np  # noqa: E402

from runtime import Session  # noqa: E402
from scene import USB, arm_rig  # noqa: E402
import arm_ik  # noqa: E402

CLOSED = (460, 785)


def frame(R, p):
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, p
    return T


def rot_clip(R_from, R_to, max_angle):
    """Rotate R_from toward R_to by at most max_angle (rad)."""
    from scipy.spatial.transform import Rotation

    d = Rotation.from_matrix(R_to @ R_from.T).as_rotvec()
    n = np.linalg.norm(d)
    if n > max_angle:
        d *= max_angle / n
    return Rotation.from_rotvec(d).as_matrix() @ R_from


def run_tracker(session, targets_fn, ki=0.25, bias_limit=0.25, on_step=None):
    """arm_ik.track for the right arm, plus joint-space targets ({"joint": q7, "fingers": f})."""
    m, d = session.model, session.data
    lay = arm_rig.layout(m)
    ik = arm_ik.ArmIK(m, "right")
    row = np.array(d.ctrl, dtype=float)
    lo, hi = m.actuator_ctrlrange.T
    arm = lay["arm"]["right"]
    bias = np.zeros(7)
    q_cmd_prev = row[arm].copy()
    rows, log, k = [], [], 0
    while not session.done:
        session._author_q_cmd = q_cmd_prev
        target = targets_fn(session, k)
        if target is None:
            break
        q_meas = d.qpos[ik.qadr].copy()
        if "joint" in target:
            q_star, ep, er = np.asarray(target["joint"], float), 0.0, 0.0
        else:
            q_star, ep, er = ik.solve(target["pos"], target["R"], q0=q_cmd_prev - bias, qpos=d.qpos)
        bias = np.clip(bias + ki * (q_star - q_meas), -bias_limit, bias_limit)
        q_cmd = np.clip(q_star + bias, lo[arm], hi[arm])
        row[arm] = q_cmd
        row[lay["fingers"]["right"]] = target["fingers"]
        q_cmd_prev = q_cmd
        row = np.clip(row, lo, hi)
        session.step(row.copy())
        rows.append(row.copy())
        if "joint" in target:
            pe = re = 0.0
        else:
            p_now, R_now = ik.fk(d.qpos[ik.qadr], qpos=d.qpos)
            pe = float(np.linalg.norm(target["pos"] - p_now))
            re = float(np.linalg.norm(arm_ik.rot_error(target["R"], R_now)))
        log.append({"k": k, "pos_err": pe, "rot_err": re, "ik_pos_err": ep, "ik_rot_err": er})
        if on_step is not None:
            on_step(session, k, log[-1])
        k += 1
    return np.array(rows), log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=float, nargs=3, required=True)
    ap.add_argument("--yaw", type=float, required=True, help="degrees")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hand", default="sharpa")
    ap.add_argument("--poses", type=Path, default=HERE / "reference/floating_oracle.npz")
    ap.add_argument("--old-rows", type=Path, default=HERE / "reference/floating_oracle.npz")
    ap.add_argument("--config", type=Path, default=FAMILY / "task.json")
    ap.add_argument("--lead", type=int, default=2)
    ap.add_argument("--ki", type=float, default=0.25)
    ap.add_argument("--slack", type=int, default=120)
    ap.add_argument("--extra", type=int, default=300, help="extra hold controls after the old episode's end")
    ap.add_argument("--depth", type=float, default=0.0118)
    ap.add_argument("--standoff", type=float, default=0.012)
    ap.add_argument("--max-step", type=float, default=0.0015)
    ap.add_argument("--max-rot", type=float, default=0.015)
    ap.add_argument("--seed", type=float, nargs=7, default=None)
    ap.add_argument("--stop", type=int, default=None)
    ap.add_argument("--n-joint", type=int, default=200)
    ap.add_argument("--pose-until", type=int, default=280)
    ap.add_argument("--branch-seed", type=float, nargs=7, default=None,
                    help="initial arm pose: backward sequential IK from old control 750 seeded here")
    ap.add_argument("--qb", type=float, nargs=7, default=[-1.65, -1.58, 0.92, -1.23, 2.53, 0.94, 1.07],
                    help="insertion-branch arm joints at old control 750 (seed)")
    ap.add_argument("--via", type=float, nargs=7, default=None, help="optional joint waypoint (mid-path)")
    ap.add_argument("--via-lift", type=float, default=None)
    ap.add_argument("--safe", type=float, nargs=3, default=None)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--hold-middle", action="store_true")
    ap.add_argument("--straighten-middle-at", type=float, default=None)
    ap.add_argument("--box-ymin", type=float, default=-0.36)
    ap.add_argument("--box-zmax", type=float, default=1.02)
    ap.add_argument("--release-stretch", type=float, default=1.0)
    ap.add_argument("--release-push", type=float, default=0.0)
    ap.add_argument("--lift-after", type=float, default=0.0)
    ap.add_argument("--plan-margin", type=float, default=0.0)
    ap.add_argument("--pre-lift", type=float, default=0.0, help="raise the old lift-end pose (branch A) first")
    ap.add_argument("--via-frac", type=float, default=0.5)
    a = ap.parse_args()

    poses = np.load(a.poses)
    P_old, M_old = poses["right_pos"], poses["right_mat"]
    old_rows = np.load(a.old_rows)["actions"]
    n_old = len(P_old) - 1          # controls of the old episode (success at the last one)

    cfg = copy.deepcopy(json.loads(a.config.read_text()))
    cfg["rig"] = "marvin"
    cfg["marvin"] = {"base_pos": [float(x) for x in a.base], "base_yaw": float(np.radians(a.yaw))}
    cfg["floor_z"] = round(float(a.base[2]) - 0.1, 6)   # the stand stands on the floor (base_z = floor_z + 0.1)
    # Initial arm pose: the old initial hand-root pose by multi-start IK (lowest elbow), fingers as before.
    import scene

    model = scene.build(cfg, None, a.hand)[0]
    lay = arm_rig.layout(model)
    ik0 = arm_ik.ArmIK(model, "right")
    if a.branch_seed is not None:
        q0 = np.array(a.branch_seed, float)
        q0, ep, er = ik0.solve(P_old[750], M_old[750], q0=q0, iters=600)
        for j in list(range(750, -1, -3)) + [0]:
            q0, ep, er = ik0.solve(P_old[j], M_old[j], q0=q0, iters=60)
        q0, ep, er = ik0.solve(P_old[0], M_old[0], q0=q0, iters=400)
    elif a.seed is not None:
        q0, ep, er = ik0.solve(P_old[0], M_old[0], q0=np.array(a.seed), iters=600)
    else:
        q0, ep, er = ik0.solve_best(P_old[0], M_old[0])
    print(f"initial IK {ep * 1000:.2f} mm {er:.4f} rad q {np.round(q0, 3)}", flush=True)
    row0 = arm_rig.default_targets(model, arm_pose={"right": q0})
    nf = lay["fingers"]["right"].stop - lay["fingers"]["right"].start
    old_f0 = np.asarray(cfg["initial_targets"][a.hand], float)[6:6 + nf]
    row0[lay["fingers"]["right"]] = old_f0
    cfg["initial_targets"] = dict(cfg["initial_targets"])
    cfg["initial_targets"][a.hand] = [float(x) for x in row0]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"task.marvin.{a.hand}.json").write_text(json.dumps(cfg, indent=1))

    s = Session(config=cfg, hand=a.hand)
    m, d = s.model, s.data
    hand_root = m.body("wrist_stage").id
    plug, hub = m.body("plug").id, m.body("hub").id
    target_port = int(cfg["target_port"])

    def old_fingers(k):
        return old_rows[min(k, len(old_rows) - 1)][6:6 + nf]

    def port_frame():
        R = d.xmat[hub].reshape(3, 3)
        mouth = d.xpos[hub] + R @ np.array([USB["hub"]["ports_x"][target_port], USB["hub"]["mouth_y"], 0.0])
        return R, mouth

    st = {"integ": np.zeros(3), "cmd": None, "anchor": None, "T0": None}
    standoff, depth = a.standoff, a.depth
    LIFT_END = a.pose_until              # old poses tracked until here (280: plug pinched and lifted)
    C0 = LIFT_END + a.n_joint            # start of the old closed-loop schedule (old control 460)
    C1 = C0 + (CLOSED[1] - CLOSED[0])    # end of the insertion (old control 785)

    # Insertion-branch joints at the old control 460: backward sequential IK from the seed at old control 750.
    ikB = arm_ik.ArmIK(model, "right")
    qB = np.array(a.qb, float)
    qB, ep, er = ikB.solve(P_old[750], M_old[750], q0=qB, iters=600)
    print(f"branch B @750: {ep * 1000:.2f} mm {er:.4f} rad", flush=True)
    for j in range(750, CLOSED[0] - 1, -1):
        qB, ep, er = ikB.solve(P_old[j], M_old[j], q0=qB, iters=100)
    print(f"branch B @460: {ep * 1000:.2f} mm {er:.4f} rad q {np.round(qB, 3)}", flush=True)
    st["qB"] = qB
    if a.safe is not None:
        # Joint-space target: branch-B pose in front of the edge (old control-460 pose + --safe offset); the closed
        # loop then brings the hand back to the old in-front point with Cartesian, rate-limited moves.
        qS = qB.copy()
        goal = P_old[CLOSED[0]] + np.array(a.safe)
        for t in np.linspace(0, 1, 30)[1:]:
            qS, ep, er = ikB.solve(P_old[CLOSED[0]] + t * np.array(a.safe), M_old[CLOSED[0]], q0=qS, iters=100)
        print(f"safe {np.round(goal, 3)}: {ep * 1000:.2f} mm {er:.4f} rad q {np.round(qS, 3)}", flush=True)
        qB = qS
    if a.via is None and a.via_lift is not None:
        # Raised waypoint: halfway pose between the lift and the old control-460 pose, lifted by --via-lift,
        # solved from the joint midpoint of the two branches.
        from scipy.spatial.transform import Rotation, Slerp

        qA_est = q0.copy()
        for j in range(0, LIFT_END + 1):
            qA_est, _, _ = ikB.solve(P_old[j], M_old[j], q0=qA_est, iters=60)
        sl = Slerp([0, 1], Rotation.from_matrix([M_old[LIFT_END], M_old[CLOSED[0]]]))
        Rv = sl([a.via_frac]).as_matrix()[0]
        pv = P_old[LIFT_END] + (P_old[CLOSED[0]] - P_old[LIFT_END]) * a.via_frac + np.array([0, 0, a.via_lift])
        best = None
        for seed in [0.5 * (qA_est + qB), qA_est, qB] + [np.random.default_rng(i).uniform(ikB.lo, ikB.hi) for i in range(16)]:
            qv, ep, er = ikB.solve(pv, Rv, q0=seed, iters=400)
            score = ep * 1000 + 30 * er + 2.0 * (np.abs(qv - qA_est).max() + np.abs(qv - qB).max())
            if ep < 3e-3 and er < 3e-2 and (best is None or score < best[0]):
                best = (score, qv, ep, er)
        if best is not None:
            a.via = list(best[1])
            print(f"via {np.round(pv, 3)}: {best[2] * 1000:.2f} mm {best[3]:.4f} rad q {np.round(best[1], 3)} "
                  f"(|dqA| {np.abs(best[1] - qA_est).max():.2f}, |dqB| {np.abs(best[1] - qB).max():.2f})", flush=True)
        else:
            print("via: no IK solution", flush=True)

    def plan_via(qA, qB, n_try=600, seed=0):
        """Sample a joint waypoint so that qA -> via -> qB keeps every arm link / the stand / the parked hand out
        of contact and the working hand off the desk and the hub (full model, fingers frozen; see plan_via.py)."""
        import mujoco

        ck = s.checker
        robot = ck.robot_geom
        handg = np.asarray(ck.geom_owner == "hand")
        bad = np.asarray([(ck.geom_owner[g] == "hub") or g in (ck.counter, ck.floor) for g in range(m.ngeom)])
        qadr = arm_rig.arm_qpos_index(m, "right")
        lo_, hi_ = m.actuator_ctrlrange[lay["arm"]["right"]].T
        dd = mujoco.MjData(m)
        base_q = d.qpos.copy()

        def ok(q):
            dd.qpos[:] = base_q
            dd.qpos[qadr] = q
            mujoco.mj_forward(m, dd)
            p = dd.xpos[hand_root]
            if not (0.40 <= p[0] <= 1.10 and a.box_ymin <= p[1] <= 0.30 and 0.62 <= p[2] <= a.box_zmax):
                return False
            if p[1] > -0.16 and p[2] < 0.80:
                return False
            for i in range(dd.ncon):
                c = dd.contact[i]
                g1, g2 = int(c.geom1), int(c.geom2)
                if c.dist > a.plan_margin:
                    continue
                if robot[g1] or robot[g2] or (handg[g1] and bad[g2]) or (handg[g2] and bad[g1]):
                    return False
            return True

        def path_ok(pts, n=60):
            return all(ok(x + (y - x) * u) for x, y in zip(pts[:-1], pts[1:]) for u in np.linspace(0, 1, n))

        rng = np.random.default_rng(seed)
        best = None
        for t in range(n_try):
            via = np.clip(qA + (qB - qA) * 0.5 + rng.normal(0, 0.7, 7), lo_ + 0.05, hi_ - 0.05)
            length = np.abs(via - qA).max() + np.abs(qB - via).max()
            if best is not None and length >= best[0]:
                continue
            if ok(via) and path_ok([qA, via, qB]):
                best = (length, via)
        print("planned via:", None if best is None else (round(float(best[0]), 3), np.round(best[1], 4).tolist()),
              flush=True)
        return None if best is None else best[1]

    def joint_path(u):
        if st.get("qA") is None:
            st["qA"] = np.array(s._author_q_cmd, float)
            if a.plan:
                a.via = plan_via(st["qA"], qB)
        qA = st["qA"]
        if a.via is None:
            return qA + (qB - qA) * smooth(u)
        via = np.array(a.via)
        return qA + (via - qA) * smooth(2 * u) if u < 0.5 else via + (qB - via) * smooth(2 * u - 1)

    def smooth(u):
        u = min(max(u, 0.0), 1.0)
        return u * u * (3 - 2 * u)

    def plug_goal(i):
        Rport, mouth = port_frame()
        y = lambda v: mouth + Rport @ np.array([0.0, v[0], v[1]])  # noqa: E731
        if i < 60:
            return Rport, y((-0.10, 0.05))
        i -= 60
        if i < 60:
            return Rport, y((-0.10, 0.05 * (1 - min(1, (i + 1) / 50))))
        i -= 60
        if i < 25:
            return Rport, y((-0.10, 0.0))
        i -= 25
        if i < 60:
            return Rport, y((-0.10 + (0.10 - standoff) * min(1, (i + 1) / 50), 0.0))
        i -= 60
        if i < 30:
            return Rport, y((-standoff, 0.0))
        i -= 30
        return Rport, y((-standoff + (depth + standoff) * min(1, (i + 1) / 70), 0.0))

    def closed_loop(H, Rg, pg, k_old, integrate=True):
        Pp = frame(d.xmat[plug].reshape(3, 3).copy(), d.xpos[plug].copy())
        T_hp = np.linalg.inv(H) @ Pp
        H_goal = frame(Rg, pg) @ np.linalg.inv(T_hp)
        if integrate:
            st["integ"] = np.clip(st["integ"] + (pg - Pp[:3, 3]) * 0.05, -0.004, 0.004)
        want_p = H_goal[:3, 3] + st["integ"]
        R_prev, p_prev = st["cmd"]
        p_cmd = p_prev + np.clip(want_p - p_prev, -a.max_step, a.max_step)
        R_cmd = rot_clip(R_prev, H_goal[:3, :3], a.max_rot)
        st["cmd"] = (R_cmd, p_cmd)
        return {"pos": p_cmd, "R": R_cmd, "fingers": old_fingers(k_old)}

    def targets(session, k):
        if a.stop is not None and k >= a.stop:
            return None
        H = frame(d.xmat[hand_root].reshape(3, 3).copy(), d.xpos[hand_root].copy())
        if k < LIFT_END:
            j = min(k + 1 + a.lead, LIFT_END)
            pos, R = P_old[j], M_old[j]
            st["cmd"] = (R, pos)
            return {"pos": pos, "R": R, "fingers": old_fingers(k)}
        Rport, mouth = port_frame()
        if k < C0:
            # Joint-space move (the arm changes IK branch) from the lift pose to the old pose at control 460,
            # through a raised waypoint; the hand keeps the old transport finger targets.
            u = (k - LIFT_END + 1) / (C0 - LIFT_END)
            j_old = LIFT_END + int(round(u * (CLOSED[0] - 1 - LIFT_END)))
            return {"joint": joint_path(u), "fingers": old_fingers(j_old)}
        if k < C1:
            i = k - C0
            if i == 0:
                st["cmd"] = (H[:3, :3].copy(), H[:3, 3].copy())
            Rg, pg = plug_goal(i)
            return closed_loop(H, Rg, pg, CLOSED[0] + i)
        if st["anchor"] is None:
            R_prev, p_prev = st["cmd"]
            st["anchor"] = (R_prev, p_prev, M_old[CLOSED[1]], P_old[CLOSED[1]])
        R_a, p_a, R_o, p_o = st["anchor"]
        k_rel = (k - C1) / a.release_stretch           # the old release, slowed down by --release-stretch
        j = min(CLOSED[1] + int(k_rel) + 1, n_old)
        if CLOSED[1] + k_rel >= n_old + a.extra:
            return None
        pos = p_a + (P_old[j] - p_o)
        Rport, _ = port_frame()
        j_rel = CLOSED[1] + k_rel
        # Keep pressing the plug home while the pinch relaxes and opens (old controls 785-920), then lift the hand
        # (its extended ring/little fingers rest above the hub) before it moves aside.
        pos = pos + Rport[:, 1] * a.release_push * smooth((j_rel - CLOSED[1]) / 25) * (1 - smooth((j_rel - 900) / 20))
        pos = pos + np.array([0.0, 0.0, a.lift_after]) * smooth((j_rel - 915) / 15)
        R = M_old[j] @ R_o.T @ R_a
        fingers = old_fingers(CLOSED[1] + int(k_rel)).copy()
        if a.hold_middle:
            # The middle finger (straightened before the approach) stays straight while the pinch opens: on the
            # arm its "opened" pinch pose would rest on the hub case.
            fingers[9:13] = old_fingers(CLOSED[1] - 1)[9:13]
        elif a.straighten_middle_at is not None:
            # The middle finger follows the old release (it steadies the plug while the thumb lets go), then
            # straightens off the hub case before the hand moves aside.
            w = smooth((j_rel - a.straighten_middle_at) / 15)
            fingers[9:13] = (1 - w) * fingers[9:13] + w * old_fingers(CLOSED[1] - 1)[9:13]
        return {"pos": pos, "R": R, "fingers": fingers}

    def on_step(session, k, entry):
        if k % 50 == 0 or (k > C1 and k % 25 == 0):
            f = session.status()
            print(f"k={k:4d} stage={f['stage']} reason={f['reason']!r} perr={entry['pos_err'] * 1000:.1f}mm "
                  f"rerr={entry['rot_err']:.3f} depth={f['target_depth_m'] * 1000:.2f} lat={f['target_lateral_m'] * 1000:.2f} "
                  f"vert={f['target_vertical_m'] * 1000:.2f} axis={f['axis_error_deg']:.2f} fingers={f['fingers_on_plug']} "
                  f"touch={f['plug_touch']} hub={f['hub_displacement_m'] * 1000:.1f}mm hubhand={f['hub_hand_contacts']} "
                  f"cable_min_z={min(d.xpos[m.body(f'cable_{i}').id][2] for i in range(20)):.3f} "
                  f"far={np.round(d.xpos[m.body('cable_far_end').id], 3)}", flush=True)

    t0 = time.time()
    rows, log = run_tracker(s, targets, ki=a.ki, on_step=on_step)
    f = s.status()
    e = np.array([[x["pos_err"], x["rot_err"]] for x in log])
    print(f"arm episode: {f['reason']!r} stage {f['stage']} after {s.steps} controls ({time.time() - t0:.0f} s) "
          f"detail {f['failure_detail']} | track err mean {e[:, 0].mean() * 1000:.1f} max {e[:, 0].max() * 1000:.1f} mm, "
          f"rot mean {e[:, 1].mean():.3f} max {e[:, 1].max():.3f}", flush=True)
    rows = np.concatenate([rows, np.repeat(rows[-1:], a.slack, axis=0)])
    s.save_trajectory(rows, a.out / f"{a.hand}.npz")
    (a.out / f"author_{a.hand}.json").write_text(json.dumps({
        "reason": f["reason"], "stage": f["stage"], "steps": int(s.steps), "rows": int(len(rows)),
        "state_sha": s.state_sha(), "failure_detail": f["failure_detail"],
        "tracking": {"pos_err_mean": float(e[:, 0].mean()), "pos_err_max": float(e[:, 0].max()),
                     "rot_err_mean": float(e[:, 1].mean()), "rot_err_max": float(e[:, 1].max())},
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()}}, indent=1, default=str))


if __name__ == "__main__":
    main()
