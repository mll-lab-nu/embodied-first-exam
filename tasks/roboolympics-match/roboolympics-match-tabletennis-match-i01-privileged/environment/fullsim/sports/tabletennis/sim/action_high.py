"""High-level action plugin (action level `high`, the switch on): the player gives the paddle state at contact
(optionally the base position at contact); the plugin plans the stroke with match.Match's planner (the base's go-to
trajectory, IK, a joint-speed-limited swing, rehearsals on a simulator copy, seeded execution scatter) and hands the
swing to the arm command layer (arm_commands.py) as a `traj` command of 9-joint rows followed by the rest command (the
arm back to the ready pose at 60 % of its speed limits, the base to its rest position). `move` sets the base's rest
position (home at each point). With no stroke under way the robot returns to / holds its ready pose and rest position.
"""
from __future__ import annotations

import numpy as np

from rcb_tt import BASE_HI, BASE_LO, CONTROL_DT

LEVEL = "high"
REST = 0.6                         # rest command: slew to the ready pose at 60 % of the joint speed limits
ACT_CALL = ("{'type':'act','t':T_from_now,'pos':[x,y,z],'normal':[nx,ny,nz],'vel':[vx,vy,vz]} (optional "
            "'base':[bx,by], the base position at contact) | {'type':'move','base':[bx,by]} | "
            "{'type':'toss','pos':[x,y,z],'height':H} (your service) | {'type':'none'}")
POS_LIMITS = "|x| <= 2.0, -3.3 <= y <= -0.3, -0.5 <= z <= 1.5"


def base_xy(v) -> list | str:
    """A base position [bx, by] within the travel, or the reason it is refused."""
    try:
        b = [float(x) for x in v]
    except Exception:  # noqa: BLE001
        return "base must be [bx, by] (metres, your frame)"
    if len(b) != 2 or not np.all(np.isfinite(b)):
        return "base must be 2 finite numbers [bx, by]"
    if not (BASE_LO[0] <= b[0] <= BASE_HI[0] and BASE_LO[1] <= b[1] <= BASE_HI[1]):
        return (f"base out of its travel: {BASE_LO[0]} <= bx <= {BASE_HI[0]}, {BASE_LO[1]} <= by <= {BASE_HI[1]}")
    return b
OBSERVE_CALL = "the newest camera frames (2 x 4), heard bounces, time, your arm and command"


def toss_body(body) -> dict | str:
    """`toss` {pos: [x, y, z], height}: your service's toss (both action levels; serve.py; the racket sports' common
    form). Static checks here; whether it is your service and the toss point is legal and reachable is judged by the
    match (refused with the reason)."""
    import serve as SV
    try:
        pos = [float(x) for x in body["pos"]]
        h = float(body["height"])
    except Exception:  # noqa: BLE001
        return "toss needs pos [x, y, z] (the toss point, your frame) and height (m the ball rises above pos)"
    if len(pos) != 3 or not np.all(np.isfinite(pos + [h])):
        return "toss: pos must be 3 finite numbers and height a finite number"
    if not (SV.H_MIN <= h <= SV.H_MAX):
        return f"toss: height must be in [{SV.H_MIN}, {SV.H_MAX}] m (Law 2.6.2: the ball rises at least 16 cm)"
    return {"type": "toss", "pos": pos, "height": h}


def validate(body: dict, core) -> dict | str:
    if body.get("type") == "none":
        return {"type": "none"}
    if body.get("type") == "move":
        b = base_xy(body.get("base"))
        return b if isinstance(b, str) else {"type": "move", "base": b}
    if body.get("type") == "toss":
        return toss_body(body)
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
    if not (abs(pos[0]) <= 2.0 and -3.3 <= pos[1] <= -0.3 and -0.5 <= pos[2] <= 1.5):
        return "pos out of range: " + POS_LIMITS
    if np.linalg.norm(vel) > 8.0:
        return "vel too large: |vel| <= 8 m/s"
    out = {"type": "act", "t": T, "pos": pos, "normal": nrm, "vel": vel}
    if body.get("base") is not None:
        b = base_xy(body["base"])
        if isinstance(b, str):
            return b
        out["base"] = b
    return out


def apply(R, dec: dict) -> dict:
    if dec["type"] == "none":                          # cancel: the arm returns to the ready pose
        R.cmd = R.rest_command()
        R._last_act = None
        R.contact_k = R.k
        return {"stroke": "cleared: the arm returns to the ready pose"}
    if dec["type"] == "move":
        return {"base_rest": R.set_base_rest(dec["base"])}
    T = float(dec["t"])
    t_hit = (R.k - R.leg["launch"]) * CONTROL_DT + T
    R._ik_seed = R._planned_hit if R.traj_active() else None
    plan, info = R.plan_paddle(t_hit, dec["pos"], dec["normal"], dec["vel"], dec.get("base"))
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
    if dec["type"] == "move":
        return {"base_rest": info.get("base_rest")}
    return {"stroke": {k: info.get(k) for k in ("stroke", "n_swing_steps_available", "n_swing_steps", "ik_residual",
                                                "blade_error_m", "normal_error_deg", "speed_scale", "base",
                                                "base_goal", "approach", "table_contact_in_rehearsal", "paddle_vel_delivered",
                                                "T_from_now")}}


def state(R) -> dict:
    la = getattr(R, "_last_act", None)
    return {"command": ({"contact_in_s": round(max(0, R.contact_k - R.k) * CONTROL_DT, 3),
                         "phase": "approach" if R.k < R.contact_k else "follow_through", "pos": la.get("paddle_pos"),
                         "normal": la.get("paddle_normal"), "vel": la.get("paddle_vel"), "stroke": la.get("stroke"),
                         "base_goal": la.get("base_goal")}
                        if R.traj_active() and la else "none (the arm returns to / holds the ready pose)"),
            "base_rest": [round(float(x), 4) for x in R.base_rest]}


def spec(R) -> dict:
    return {}
