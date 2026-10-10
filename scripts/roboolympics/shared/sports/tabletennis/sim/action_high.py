"""High-level action plugin (action level `high`, the switch on): the player gives the paddle state at contact; the
plugin plans the stroke with match.Match's planner (IK, a joint-speed-limited swing, rehearsals on a simulator copy,
seeded execution scatter) and hands the swing to the arm command layer (core.py) as a `traj` command followed by a
slew back to the ready pose at 60 % of the speed limits. With no stroke under way the arm returns to / holds the ready
pose. This reproduces the original high-level tasks target for target (scripts/olympiad/tabletennis/test_modes.py).
"""
from __future__ import annotations

import numpy as np

from rcb_tt import CONTROL_DT

LEVEL = "high"
REST = 0.6                         # rest command: slew to the ready pose at 60 % of the joint speed limits
ACT_CALL = "{'type':'act','t':T_from_now,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz]} or {'type':'none'}"
OBSERVE_CALL = "the newest camera frames (2 x 4), heard bounces, time, your arm and command"


def validate(body: dict, core) -> dict | str:
    if body.get("type") == "none":
        return {"type": "none"}
    try:
        T = float(body["t"]); pos = [float(x) for x in body["pos"]]
        nrm = [float(x) for x in body["normal"]]; vel = [float(x) for x in body["vel"]]
    except Exception:  # noqa: BLE001
        return ("act needs T (s from now until contact), pos [x, y, z] (blade centre at contact), normal [nx, ny, nz] "
                "(blade face normal) and vel [vx, vy, vz] (blade velocity at contact, m/s); or `act none`")
    if len(pos) != 3 or len(nrm) != 3 or len(vel) != 3 or not np.all(np.isfinite(pos + nrm + vel + [T])):
        return "pos, normal and vel must have 3 finite numbers each"
    if np.linalg.norm(nrm) < 1e-6:
        return "normal must be a non-zero vector"
    if not (0.0 < T <= 2.5):
        return "T must be in (0, 2.5] s from now"
    if not (abs(pos[0]) <= 1.2 and -2.5 <= pos[1] <= -0.5 and 0.0 <= pos[2] <= 1.2):
        return "pos out of range: |x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2"
    if np.linalg.norm(vel) > 8.0:
        return "vel too large: |vel| <= 8 m/s"
    return {"type": "act", "t": T, "pos": pos, "normal": nrm, "vel": vel}


def apply(R, dec: dict) -> dict:
    if dec["type"] == "none":                          # cancel: the arm returns to the ready pose
        R.cmd = R.rest_command()
        R._last_act = None
        R.contact_k = R.k
        return {"stroke": "cleared: the arm returns to the ready pose"}
    T = float(dec["t"])
    t_hit = (R.k - R.leg["launch"]) * CONTROL_DT + T
    R._ik_seed = R._planned_hit if R.traj_active() else None
    plan, info = R.plan_paddle(t_hit, dec["pos"], dec["normal"], dec["vel"])
    info["T_from_now"] = round(T, 4)
    if plan:                                           # the swing, then back to the ready pose
        res = R.submit({"type": "traj", "k0": R.k, "q": plan, "then": R.rest_command()})
        assert "command" in res, res                   # the planner's swing starts at the target in force
    R.shots.append({"k": R.k, "leg": R.n_our_legs, **{k: info[k] for k in info if k != "paddle_vel_delivered"}})
    if plan:
        R.contact_k = R.k + info["n_swing_steps_available"]
        R._last_act = info
    return info


def reply(dec: dict, info: dict) -> dict:
    if dec["type"] == "none":
        return {"command": "cleared: the arm returns to the ready pose"}
    return {"stroke": {k: info.get(k) for k in ("stroke", "n_swing_steps_available", "n_swing_steps", "ik_residual",
                                                "blade_error_m", "normal_error_deg", "speed_scale",
                                                "paddle_vel_delivered", "T_from_now")}}


def state(R) -> dict:
    la = getattr(R, "_last_act", None)
    return {"command": ({"contact_in_s": round(max(0, R.contact_k - R.k) * CONTROL_DT, 3),
                         "phase": "approach" if R.k < R.contact_k else "follow_through", "pos": la.get("paddle_pos"),
                         "normal": la.get("paddle_normal"), "vel": la.get("paddle_vel"), "stroke": la.get("stroke")}
                        if R.traj_active() and la else "none (the arm returns to / holds the ready pose)")}


def spec(R) -> dict:
    return {}
