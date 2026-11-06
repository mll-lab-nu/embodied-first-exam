"""The RL opponent's own swing (version 2, RLTT 2026-10-16): the joint-level stroke a built-in seat's act may ask for
with a `swing` field (plugin.StrokeLayer: only for a seat named in RO_BUILTIN_SEATS; never for a seat played over
HTTP). It replaces the platform's stroke rows (workers.trajectory) at the effect boundary, from the same prepared
contact (workers.prepare: the execution scatter, the base goal, the arm's IK at it), and differs in two ways:

  redundancy  the arm's joint velocity at contact is the one that needs the smallest share of the joints' velocity
              limits (an L-infinity least-norm solution, by iteratively reweighted least squares) instead of the
              velocity-limit-weighted least-squares inverse, so more blade speed fits under the limits;
  rail        the base may still be moving at contact: a share of the blade velocity's horizontal part comes from the
              rail (its own limits: 2 m/s, 8 m/s^2, 200 m/s^3 at the go-to generator's 0.85 margin), the base reaching
              the planned contact position at the contact step and braking afterwards inside its travel.

Everything else is the platform's: the arm's rows from bodies/trajopt (rally.stroke_rows: within the velocity,
acceleration and jerk limits, the torque-rate jerk caps), the per-step speed guard, the table check (a swing that
would touch the table falls back to the platform's rows), the low-level command checks at install, the servo and its
reflexes. swing = {"base_share": 0..1, "overdrive": 0.8..1.5}: the rail's share of the horizontal blade velocity and
a factor on the blade speed asked for (the platform's swing under-delivers; see the report). numpy only."""
from __future__ import annotations

import numpy as np

SWING_KEYS = {"base_share": (0.0, 1.0), "overdrive": (0.8, 1.5)}
BASE_MARGIN = 0.85                 # the rail's go-to generator's share of its limits
BASE_V_CONTACT = 1.6               # m/s per axis at most at the contact
FOLLOW = 25                        # steps after the contact (the platform's follow-through length)


def sanitize(sw) -> dict | None:
    if not isinstance(sw, dict):
        return None
    out = {}
    for k, (lo, hi) in SWING_KEYS.items():
        v = sw.get(k)
        if v is None:
            continue
        v = float(v)
        if not np.isfinite(v):
            return None
        out[k] = float(np.clip(v, lo, hi))
    return out


def _box_ls(A, v, t, x0, iters=600):
    """min |A x - v|^2 with |x_i| <= t (projected gradient, step 1 / |A|^2)."""
    L = float(np.linalg.norm(A, 2)) ** 2 + 1e-12
    x = np.clip(x0, -t, t)
    for _ in range(iters):
        x = np.clip(x - (A.T @ (A @ x - v)) / L, -t, t)
    return x


def minimax_qd(J, v, vmax, tol=1e-4):
    """qd with J qd = v that needs the smallest share of the joints' velocity limits, max_i |qd_i| / vmax_i (an
    L-infinity least-norm solution: bisection on the share, a box-constrained least squares each), refined to meet
    J qd = v exactly with the weighted inverse on the remainder."""
    A = J * vmax[None, :]
    W = np.diag(vmax ** 2)
    x_ls = (W @ J.T @ np.linalg.solve(J @ W @ J.T + 1e-12 * np.eye(J.shape[0]), v)) / vmax   # the L2 solution
    hi = float(np.max(np.abs(x_ls))); lo = 0.0; best = x_ls
    nv = float(np.linalg.norm(v)) + 1e-12
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        x = _box_ls(A, v, mid, best)
        if np.linalg.norm(A @ x - v) <= tol * nv:
            hi, best = mid, x
        else:
            lo = mid
    qd = best * vmax
    r = v - J @ qd                                             # exact equality: the small remainder
    qd = qd + W @ J.T @ np.linalg.solve(J @ W @ J.T + 1e-12 * np.eye(J.shape[0]), r)
    return qd


def base_rows(b0, v0, a0, b_c, vb, n, follow=FOLLOW):
    """Rail targets: from (b0, v0, a0) to b_c at step n with velocity vb, then braking to rest (n + follow rows)."""
    import rcb_tt
    from rally import trajopt
    lim = rcb_tt.BASE_LIM
    wps = [trajopt.Waypoint(k=n, q=np.asarray(b_c, float), v=np.asarray(vb, float), tol_q=2e-4, tol_v=2e-2),
           trajopt.Waypoint(k=n + follow, v=np.zeros(2), a=np.zeros(2), tol_v=2e-2, tol_a=0.5)]
    pl = trajopt.plan(b0, v0, a0, n + follow, rcb_tt.CONTROL_DT, lim, wps, lo=rcb_tt.BASE_LO, hi=rcb_tt.BASE_HI,
                      margin=BASE_MARGIN, iters=300)
    rows = np.asarray(pl["q"], float)
    err = float(np.linalg.norm(rows[n - 1] - b_c))
    verr = float(np.linalg.norm(pl["v"][n - 1] - vb))
    return rows, err, verr


_TWIN: list = []
MAX_BLADE_ERR = 0.01               # m: the rehearsed swing's blade-centre error at contact, else the platform's swing
MAX_NORMAL_ERR_DEG = 3.0
MAX_RATIO = 1.6                    # beyond this share of the velocity limits at the contact pose: the platform's swing
REHEARSALS = int(__import__("os").environ.get("RLTT_REHEARSALS", "4"))                    # robot-only rehearsals that correct the servo's lag (as the match's platform does)


def _twin():
    if not _TWIN:
        import rally
        import rcb_tt
        _TWIN.append(rcb_tt.Session(instance=str(rally.INSTANCE), scene=str(rally.SCENE)))
    return _TWIN[0]


def rehearse(world, rows, n):
    """Robot-only rollout of `rows` from the live robot of world = (duel, seat): its joints, velocities, target and
    servo state copied onto a single-robot twin (the seat's own frame), the ball parked. The paddle's (pos, normal,
    vel) after n steps and whether the twin touched the table or the net."""
    import mujoco as mj
    g, seat = world
    tw = _twin()
    m, d = tw.m, tw.d
    mj.mj_resetData(m, d)
    d.qpos[tw._qadr] = g.d.qpos[g.qadr[seat]]
    d.qvel[tw._vadr] = g.d.qvel[g.vadr[seat]]
    d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qpos[3:7] = [1, 0, 0, 0]
    mj.mj_forward(m, d)
    tw._target = np.asarray(g.target[seat], float).copy(); tw._k = 0; tw._actions = []; tw._events = []
    tw._last_touch = {}
    tw.servo.copy_from(g.servo[seat])
    tw.substep_hook = None
    tw._robot_table = 0; tw._robot_net = 0
    for j in range(n):
        d.qpos[0:3] = [3.0, 3.0, 5.0]; d.qvel[0:6] = 0
        tw.step(np.asarray(rows[j], float))
    st = tw.state()
    return (np.asarray(st["paddle_pos"], float), np.asarray(st["paddle_normal"], float),
            np.asarray(st["paddle_vel"], float), bool(tw._robot_table or tw._robot_net))


def _log(row):
    import os
    if os.environ.get("RLTT_SWING_LOG"):            # experiments only: one JSON line per swing
        import json
        with open(os.environ["RLTT_SWING_LOG"], "a") as f:
            f.write(json.dumps(row, default=float) + "\n")


def trajectory(target, previous, prepared, T, low, high, swing, acc=None, serve=False, world=None):
    """The swing's 9-joint rows (as workers.trajectory) and an info dict; None when it cannot do better than the
    platform (the caller then uses workers.trajectory): too little time, no joint velocity under the limits, a swing
    the table would stop, or a rehearsal that stays inaccurate."""
    out = _trajectory(target, previous, prepared, T, low, high, swing, acc, serve, world)
    if isinstance(out, str):
        _log({"fallback": out, "T": round(float(T), 3)})
        return None
    _log(out[1])
    return out


def _trajectory(target, previous, prepared, T, low, high, swing, acc, serve, world):
    import rally
    import rcb_tt
    import workers
    from rally import ARM_VEL, CONTROL_DT
    sw = sanitize(swing) or {}
    start = np.asarray(target, float)
    speed = (start - np.asarray(previous, float)) / CONTROL_DT
    acc0 = np.zeros(rcb_tt.NQ) if acc is None else np.asarray(acc, float)
    n = max(1, int(np.ceil(T / CONTROL_DT)))
    if n < 12:
        return "short"
    cs = workers._check_session()
    goal = np.asarray(prepared.get("base_goal", start[:2]), float)
    q_c = np.asarray(prepared["q"], float)
    Jfull = cs.jacobian(np.r_[goal, q_c])[:3]
    J = Jfull[:, 2:]
    v_req = J @ (np.asarray(prepared["qd"], float) * float(prepared.get("speed_scale", 1.0)))   # the scattered act's
    v_req = v_req * float(sw.get("overdrive", 1.0))                                                 # blade velocity
    share = float(sw.get("base_share", 0.0))
    vb = np.zeros(2)
    if share > 0:
        t_av = max(0.0, (n - 3) * CONTROL_DT)
        cap = min(BASE_V_CONTACT, BASE_MARGIN * rcb_tt.BASE_AMAX * t_av * 0.5)
        vb = np.clip(share * v_req[:2], -cap, cap)
        room_hi = rcb_tt.BASE_HI - goal; room_lo = goal - rcb_tt.BASE_LO   # braking room inside the travel
        a_b = BASE_MARGIN * rcb_tt.BASE_AMAX
        for i in range(2):
            need = vb[i] ** 2 / (2 * a_b) + abs(vb[i]) * 0.05
            room = room_hi[i] if vb[i] > 0 else room_lo[i]
            if need > room:
                vb[i] = np.sign(vb[i]) * max(0.0, np.sqrt(max(0.0, 2 * a_b * (room - 0.01))) - 0.05)
    brows = None
    if np.any(np.abs(vb) > 1e-3):
        brows, err, verr = base_rows(start[:2], speed[:2], acc0[:2], goal, vb, n)
        if err > 0.004 or verr > 0.15:
            vb, brows = np.zeros(2), None
    if brows is None:
        brows, _ = rcb_tt.base_plan(start[:2], speed[:2], goal, n + FOLLOW, a=acc0[:2])
    Ms = [prepared["M"]] if prepared.get("M") is not None else []
    Ms += [rally.arm_inertia(cs, start), rally.arm_inertia(cs, np.r_[start[:2], 0.5 * (start[2:] + q_c)])]
    p_c, R_c = cs.fk(np.r_[goal, q_c])
    nrm = np.asarray(R_c, float)[:, 0]
    brows0, _ = rcb_tt.base_plan(start[:2], speed[:2], goal, n + FOLLOW, a=acc0[:2])
    qd_platform = np.asarray(prepared["qd"], float) * float(prepared.get("speed_scale", 1.0)) * float(sw.get("overdrive", 1.0))

    def attempt(qd0, brows_, vb_):
        """one candidate swing: rows (with a table-avoiding via if needed), rehearsed and corrected; a reason
        string when it fails, else (loss, rows, si, reh, first, ratio, via)"""
        v_t = v_req if np.any(np.abs(vb_) > 1e-3) or qd0 is not None else v_req
        if qd0 is None:                            # the minimum-share joint velocity for the arm's part
            qd_ = minimax_qd(J, v_req - np.r_[vb_, 0.0], 0.9 * ARM_VEL)
        else:
            qd_ = qd0 - np.linalg.pinv(J) @ np.r_[vb_, 0.0] if np.any(np.abs(vb_) > 1e-3) else qd0.copy()
        ratio_ = float(np.max(np.abs(qd_) / (0.9 * ARM_VEL)))
        if ratio_ > MAX_RATIO:
            return f"ratio {ratio_:.2f}"
        if ratio_ > 1.0:
            qd_ = qd_ / ratio_
            v_t = J @ qd_ + np.r_[vb_, 0.0]
        q_goal, qd_goal = q_c.copy(), qd_.copy()
        via_ = None
        rows_, si_ = rally.stroke_rows(start, speed, acc0, q_goal, qd_goal, n, brows_, low + 1e-4, high - 1e-4,
                                       n_follow=FOLLOW, M=Ms, serve=serve)
        if rally.touches_table(cs, rows_[:n]):
            for dz, q_pre in prepared.get("vias") or []:
                cand, _ = rally.stroke_rows(start, speed, acc0, q_goal, qd_goal, n, brows_, low + 1e-4, high - 1e-4,
                                            via=np.asarray(q_pre, float), n_follow=FOLLOW, M=Ms, serve=serve)
                if not rally.touches_table(cs, cand[:n]):
                    via_ = np.asarray(q_pre, float)
                    break
            else:
                return "table"
        best_, first_ = None, {}
        for it in range(REHEARSALS if world is not None else 1):
            rows_, si_ = rally.stroke_rows(start, speed, acc0, q_goal, qd_goal, n, brows_, low + 1e-4, high - 1e-4,
                                           via=via_, n_follow=FOLLOW, M=Ms, serve=serve)
            if world is None:
                return (0.0, rows_, si_, None, {}, ratio_, via_)
            p, n_act, v_act, touch = rehearse(world, rows_, n)
            ang = float(np.arccos(np.clip(n_act @ nrm, -1, 1)))
            perr, verr = float(np.linalg.norm(p - p_c)), float(np.linalg.norm(v_act - v_t))
            if it == 0:
                first_ = dict(err0=round(perr, 4), nerr0=round(float(np.degrees(ang)), 2),
                              v0=round(float(np.linalg.norm(v_act)), 3))
            loss = perr + 0.1 * ang + 0.01 * verr + (1.0 if touch else 0.0)
            if best_ is None or loss < best_[0]:
                best_ = (loss, rows_, si_, dict(blade_err=round(perr, 4), normal_err_deg=round(float(np.degrees(ang)), 2),
                                                v_rehearsed=round(float(np.linalg.norm(v_act)), 3), touch=touch, it=it))
            if perr < 5e-4 and ang < np.radians(0.2) and verr < 0.02:
                break
            Ja = np.asarray(cs.jacobian(np.r_[goal, q_goal]), float)[:, 2:]
            e = np.r_[p_c - p, np.cross(n_act, nrm)]
            q_goal = np.clip(q_goal + Ja.T @ np.linalg.solve(Ja @ Ja.T + 1e-4 * np.eye(6), e),
                             np.asarray(low)[2:] + 1e-4, np.asarray(high)[2:] - 1e-4)
            qd_goal = qd_goal + minimax_qd(Ja[:3], (v_t - v_act) * 0.7, 0.9 * ARM_VEL)
            qd_goal = qd_goal / max(1.0, float(np.max(np.abs(qd_goal) / ARM_VEL)))
        loss, rows_, si_, reh_ = best_
        if rally.touches_table(cs, rows_[:n]) or reh_["touch"]:
            return "table"
        if reh_["blade_err"] > MAX_BLADE_ERR or reh_["normal_err_deg"] > MAX_NORMAL_ERR_DEG:
            return f"inaccurate {reh_['blade_err']}"
        return (loss, rows_, si_, reh_, first_, ratio_, via_)

    cands = [("minimax+rail", None, brows, vb), ("platform+rail", qd_platform, brows, vb),
             ("minimax", None, brows0, np.zeros(2)), ("platform", qd_platform, brows0, np.zeros(2))]
    seen, tried, got = set(), [], None
    for name, qd0, br, vb_ in cands:
        if name.endswith("+rail") and not np.any(np.abs(vb_) > 1e-3):
            continue
        r = attempt(qd0, br, vb_)
        tried.append(name + ": " + (r if isinstance(r, str) else "ok"))
        if not isinstance(r, str):
            got = (name, vb_, r)
            break
    if got is None:
        return "; ".join(tried)
    kind, vb, (_, rows, si, reh, first, ratio, via) = got
    q1, q0 = np.asarray(rows[n - 1], float), np.asarray(rows[n - 2], float)
    p1, _ = cs.fk(q1)
    p0, _ = cs.fk(q0)
    v_plan = (p1 - p0) / CONTROL_DT
    info = dict(contact_steps=n, approach="rl swing: " + kind, tried=tried, swing=sw, base_v_contact=[round(float(x), 3) for x in vb],
                v_request=round(float(np.linalg.norm(v_req)), 3), v_planned=round(float(np.linalg.norm(v_plan)), 3),
                qd_ratio=round(ratio, 3), via=via is not None, base_goal=[round(float(x), 4) for x in goal], **(reh or {}), **first, **si)
    return rows, info
