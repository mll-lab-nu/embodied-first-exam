"""Low-level action plugin (action level `low`, the high-level switch off): the player's commands go straight to the
arm command layer (arm_commands.py); nothing plans for it (no IK, no stroke planner, no rehearsal, no return to a ready pose,
no execution scatter). The robot's own joint controller (PD + gravity/Coriolis compensation at 1 kHz, torque limits;
rcb_tt.Session.step) tracks the targets. `spec` documents the robot's kinematic chain, limits and controller.

Commands (each replaces the previous one when it takes effect, at the start of the next control step after it
arrives):
  traj  {"type": "traj", "k0": K0, "q": [[q1..q7], ...]}   1..MAX_ROWS rows; row i is the joint target of control
        step K0 + i. Passed rows are skipped; before K0 the current target is held; after the last row it is held.
        Rows must lie in the joint ranges and consecutive rows may differ by at most VEL_LIMIT x 10 ms per joint
        (HTTP 400). The first row used must be within that limit of the target in force (else rejected, arm_commands.py).
  slew  {"type": "slew", "q": [q1..q7], "speed": F}   every joint independently towards q at F x its speed limit.
  hold  {"type": "hold"}
At the end of a point the command is cleared: the arm holds its targets.
"""
from __future__ import annotations

import numpy as np

import mujoco as mj
from arm_commands import STEP_LIM
from rcb_tt import KD, KP, TORQUE_LIMIT, VEL_LIMIT

LEVEL = "low"
REST = None                        # rest command: hold
MAX_ROWS = 300                     # 3 s of targets per command
CHAIN = ["link0", "link1", "link2", "link3", "link4", "link5", "link6", "link7", "paddle"]
ACT_CALL = ("{'type':'traj','k0':K0,'q':[[7 joint targets], ...]} (row i = target of control step K0+i, <= 300 rows) "
            "| {'type':'slew','q':[7],'speed':F} | {'type':'hold'}")
OBSERVE_CALL = "the newest camera frames (2 x 4), heard bounces, time, your arm (q, qd, q_target) and command"


def validate(body: dict, core) -> dict | str:
    low, high = core.s.JOINT_LOW, core.s.JOINT_HIGH
    t = body.get("type")
    if t == "hold":
        return {"type": "hold"}
    if t == "slew":
        try:
            q = [float(x) for x in body["q"]]
            speed = float(body.get("speed", 1.0))
        except Exception:  # noqa: BLE001
            return "slew needs q: 7 joint angles (rad) and optionally speed in (0, 1]"
        if len(q) != 7 or not np.all(np.isfinite(q)):
            return "q must be 7 finite joint angles (rad)"
        if not (0.0 < speed <= 1.0):
            return "speed must be in (0, 1] (fraction of each joint's speed limit)"
        if np.any(np.asarray(q) < low) or np.any(np.asarray(q) > high):
            return f"q outside the joint ranges: low {np.round(low, 4).tolist()}, high {np.round(high, 4).tolist()}"
        return {"type": "slew", "q": q, "speed": speed}
    if t == "traj":
        try:
            k0 = body["k0"]
            if type(k0) is not int:
                raise TypeError
            Q = np.asarray(body["q"], dtype=float)
        except Exception:  # noqa: BLE001
            return "traj needs k0 (an integer control step) and q: a list of rows of 7 joint targets (rad)"
        if Q.ndim != 2 or Q.shape[1] != 7 or not (1 <= len(Q) <= MAX_ROWS) or not np.all(np.isfinite(Q)):
            return f"q must be 1..{MAX_ROWS} rows of 7 finite joint targets"
        if k0 < 0:
            return "k0 must be >= 0"
        if np.any(Q < low) or np.any(Q > high):
            r, j = np.argwhere((Q < low) | (Q > high))[0]
            return f"row {int(r)}, joint {int(j) + 1}: {Q[r, j]:.5f} outside its range [{low[j]:.4f}, {high[j]:.4f}]"
        if len(Q) > 1:
            dq = np.abs(np.diff(Q, axis=0))
            if (dq > STEP_LIM).any():
                r, j = np.argwhere(dq > STEP_LIM)[0]
                return (f"rows {int(r)}->{int(r) + 1}, joint {int(j) + 1}: moves {dq[r, j]:.5f} rad in one 10 ms step "
                        f"(limit {STEP_LIM[j]:.5f} = {VEL_LIMIT[j]} rad/s)")
        return {"type": "traj", "k0": int(k0), "q": Q.tolist()}
    return "act type must be traj, slew or hold (this task's action level is low: joint targets)"


def apply(R, dec: dict) -> dict:
    return R.submit(dec)


def reply(dec: dict, info: dict) -> dict:
    return {"result": info}


def state(R) -> dict:
    st = R.s.state()
    return {"qd": st["qd"].round(4).tolist(), "q_target": st["q_target"].round(6).tolist(),
            "command": R.command_state()}


def kinematics(m: mj.MjModel) -> dict:
    """The robot's kinematic model (its own body, not world state): the body chain from the world to the paddle."""
    bodies = []
    for name in CHAIN:
        b = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, name)
        j = [i for i in range(m.njnt) if m.jnt_bodyid[i] == b]
        e = {"body": name, "pos_in_parent": [round(float(x), 6) for x in m.body_pos[b]],
             "quat_in_parent_wxyz": [round(float(x), 7) for x in m.body_quat[b]]}
        if j:
            e["joint"] = mj.mj_id2name(m, mj.mjtObj.mjOBJ_JOINT, j[0])
            e["joint_axis_in_body"] = [float(x) for x in m.jnt_axis[j[0]]]
            e["joint_pos_in_body"] = [float(x) for x in m.jnt_pos[j[0]]]
        bodies.append(e)
    site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center")
    return {
        "chain": bodies,
        "rule": ("world pose of a body = parent pose x translate(pos_in_parent) x rotate(quat_in_parent_wxyz); a body "
                 "with a joint then rotates by the joint angle q about joint_axis_in_body (through joint_pos_in_body). "
                 "The parent of link0 is the world."),
        "blade_center_in_paddle": [round(float(x), 6) for x in m.site_pos[site]],
        "blade_normal": "the paddle body's local +x axis (the face normal); the handle runs along its local +z",
        "blade_half_size_m": [0.0075, 0.075, 0.075],
    }


def limits(s) -> dict:
    return {"joint_low_rad": [round(float(x), 4) for x in s.JOINT_LOW],
            "joint_high_rad": [round(float(x), 4) for x in s.JOINT_HIGH],
            "joint_speed_limit_rad_s": VEL_LIMIT.tolist(), "torque_limit_nm": TORQUE_LIMIT.tolist(),
            "max_target_step_rad": [round(float(x), 6) for x in STEP_LIM],
            "controller": {"kp": KP.tolist(), "kd": KD.tolist(),
                           "law": "tau = kp (q_des - q) + kd (qd_des - qd) + gravity/Coriolis compensation, clipped "
                                  "at the torque limits, at 1 kHz; q_des interpolates linearly from the previous "
                                  "target to the new one over the 10 ms step and qd_des is their difference / 10 ms"},
            "ready_pose_rad": [round(float(x), 5) for x in s.inst["q0"]],
            "max_rows_per_command": MAX_ROWS}


def spec(R) -> dict:
    return {"action_interface": "joint position targets at 100 Hz; no IK or stroke planner",
            "kinematics": kinematics(R.s.m), "limits": limits(R.s)}
