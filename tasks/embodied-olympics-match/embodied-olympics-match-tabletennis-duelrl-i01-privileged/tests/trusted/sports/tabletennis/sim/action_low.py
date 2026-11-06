"""Low-level action plugin (action level `low`, the high-level switch off): the player's commands go straight to the
arm command layer (arm_commands.py); nothing plans for it (no IK, no stroke planner, no rehearsal, no return to a ready pose,
no execution scatter). The robot's own servo (rcb_tt.TTServo, revision wallclock-10: the real Franka Panda's limits as in
fencing-3, the rail base's real limits) tracks the targets at 1 kHz. `spec` documents the robot's kinematic chain (the
rail base's two prismatic joints, then the arm), limits and controller.

Commands (each replaces the previous one when it takes effect, at the start of the next control step after it
arrives):
  traj  {"type": "traj", "k0": K0, "q": [[base_x, base_y, q1..q7], ...]}   1..MAX_ROWS rows of 9 targets; row i is
        the joint target of control step K0 + i. Passed rows are skipped; before K0 the current target is held; after
        the last row it is held. Rows must lie in the joint ranges (the base's travel), consecutive rows may differ by
        at most VEL_LIMIT x 10 ms per joint (2 cm per base axis) and three consecutive rows by a second difference of at
        most ACC_LIMIT x (10 ms)^2 (the acceleration limits; HTTP 400). The first row used must satisfy both with the
        target in force and its velocity (else rejected, arm_commands.py). Jerk is not checked: the servo smooths it.
  slew  {"type": "slew", "q": [9], "speed": F}   every arm joint independently towards q at F x its speed limit within
        its acceleration limit, the base towards q's base position with the bounded go-to generator (F x 2 m/s,
        8 m/s^2).
  hold  {"type": "hold"}
At the end of a point the command is cleared: the arm holds its targets.
"""
from __future__ import annotations

import numpy as np

import mujoco as mj
import rcb_tt
from arm_commands import STEP_LIM
from rcb_tt import KD, KP, NQ, TORQUE_LIMIT, TORQUE_RATE, VEL_LIMIT

LEVEL = "low"
REST = None                        # rest command: hold
MAX_ROWS = 300                     # 3 s of targets per command
CHAIN = ["base", "link0", "link1", "link2", "link3", "link4", "link5", "link6", "link7", "paddle"]
ACT_CALL = ("{'type':'traj','k0':K0,'q':[[9 joint targets: base_x, base_y, q1..q7], ...]} (row i = target of control "
            "step K0+i, <= 300 rows) | {'type':'slew','q':[9],'speed':F} | {'type':'hold'} | "
            "{'type':'toss','pos':[x,y,z],'height':H} (your service)")
OBSERVE_CALL = "the newest camera frames (2 x 4), heard bounces, time, your arm (q, qd, q_target) and command"


def validate(body: dict, core) -> dict | str:
    low, high = core.s.JOINT_LOW, core.s.JOINT_HIGH
    t = body.get("type")
    if t == "hold":
        return {"type": "hold"}
    if t == "toss":
        from action_high import toss_body
        return toss_body(body)
    if t == "slew":
        try:
            q = [float(x) for x in body["q"]]
            speed = float(body.get("speed", 1.0))
        except Exception:  # noqa: BLE001
            return "slew needs q: 9 joint targets [base_x, base_y, q1..q7] and optionally speed in (0, 1]"
        if len(q) != NQ or not np.all(np.isfinite(q)):
            return "q must be 9 finite joint targets [base_x, base_y (m), q1..q7 (rad)]"
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
            return "traj needs k0 (an integer control step) and q: a list of rows of 9 joint targets"
        if Q.ndim != 2 or Q.shape[1] != NQ or not (1 <= len(Q) <= MAX_ROWS) or not np.all(np.isfinite(Q)):
            return f"q must be 1..{MAX_ROWS} rows of 9 finite joint targets [base_x, base_y, q1..q7]"
        if k0 < 0:
            return "k0 must be >= 0"
        if np.any(Q < low) or np.any(Q > high):
            r, j = np.argwhere((Q < low) | (Q > high))[0]
            return (f"row {int(r)}, joint {rcb_tt.JOINTS[int(j)]}: {Q[r, j]:.5f} outside its range "
                    f"[{low[j]:.4f}, {high[j]:.4f}]")
        if len(Q) > 1:
            dq = np.abs(np.diff(Q, axis=0))
            if (dq > STEP_LIM).any():
                r, j = np.argwhere(dq > STEP_LIM)[0]
                return (f"rows {int(r)}->{int(r) + 1}, joint {rcb_tt.JOINTS[int(j)]}: moves {dq[r, j]:.5f} in one "
                        f"10 ms step (limit {STEP_LIM[j]:.5f} = {VEL_LIMIT[j]} per s)")
            why = rcb_tt.rows_problem(Q)               # the real limits: the acceleration between rows too
            if why:
                return f"traj rows beyond the robot's limits: {why}"
        return {"type": "traj", "k0": int(k0), "q": Q.tolist()}
    return "act type must be traj, slew, hold or toss (this task's action level is low: joint targets)"


def apply(R, dec: dict) -> dict:
    return R.submit(dec)


def reply(dec: dict, info: dict) -> dict:
    return {"result": info}


def state(R) -> dict:
    st = R.s.state()
    return {"qd": st["qd"].round(4).tolist(), "q_target": st["q_target"].round(6).tolist(),
            "qd_target": R._target_vel().round(6).tolist(),     # the target in force's velocity (its last two rows /
            "command": R.command_state(),                         # 10 ms): what a new traj's first row must join
            "servo": servo_state(R.s.servo, R.s.d.time)}


def servo_state(sv, t_now: float) -> dict:
    """The servo's own state (as a real Franka reports its desired joint state q_d, dq_d, ddq_d and its desired torque
    tau_J_d): the setpoint generator's position, velocity and acceleration (9: base, arm) and the arm's last commanded
    torque (7), full precision: with the robot's model and the documented law (toolkit tt_servo) a player can roll its
    commands out exactly."""
    return {"q": np.r_[sv.jb.q, sv.jl.q].tolist(), "qd": np.r_[sv.jb.qd, sv.jl.qd].tolist(),
            "qdd": np.r_[sv.jb.qdd, sv.jl.qdd].tolist(), "tau": sv.trl.tau.tolist(),
            # the joint-velocity reflex (revision 15/12; libfranka reports it as joint_velocity_violation): the
            # simulation time it fired and the pose it holds until REFLEX_RECOVER_S later, else None; reflexes so far
            "reflex": (None if sv.reflex_at is None else
                       {"s_left": max(0.0, rcb_tt.REFLEX_RECOVER_S - (float(t_now) - sv.reflex_at[0])),
                        "q": sv.reflex_at[1].tolist()}),
            "n_reflex": int(sv.n_reflex), "n_collision_reflex": int(sv.n_collision_reflex)}


def kinematics(m: mj.MjModel, suffix: str = "") -> dict:
    """The robot's kinematic model (its own body, not world state): the body chain from the world to the paddle, the
    rail base's two prismatic joints first. `suffix` names the duel's robot B (its chain is A's, in its own frame)."""
    bodies = []
    for name in CHAIN:
        b = mj.mj_name2id(m, mj.mjtObj.mjOBJ_BODY, name + suffix)
        js = [i for i in range(m.njnt) if m.jnt_bodyid[i] == b]
        e = {"body": name, "pos_in_parent": [round(float(x), 6) for x in m.body_pos[b]],
             "quat_in_parent_wxyz": [round(float(x), 7) for x in (m.body_quat[b] if not suffix or name != "base"
                                                                   else (1.0, 0.0, 0.0, 0.0))]}
        if len(js) == 1:
            jn = mj.mj_id2name(m, mj.mjtObj.mjOBJ_JOINT, js[0])
            e["joint"] = jn[:len(jn) - len(suffix)]
            e["joint_type"] = "hinge"
            e["joint_axis_in_body"] = [float(x) for x in m.jnt_axis[js[0]]]
            e["joint_pos_in_body"] = [float(x) for x in m.jnt_pos[js[0]]]
        elif js:
            e["joints"] = [{"joint": rcb_tt.JOINTS[i], "joint_type": "slide",
                            "joint_axis_in_body": [float(x) for x in m.jnt_axis[j]]} for i, j in enumerate(js)]
        bodies.append(e)
    site = mj.mj_name2id(m, mj.mjtObj.mjOBJ_SITE, "paddle_center" + suffix)
    return {
        "chain": bodies,
        "joint_order": rcb_tt.JOINTS,
        "rule": ("world pose of a body = parent pose x translate(pos_in_parent) x rotate(quat_in_parent_wxyz); a body "
                 "with a hinge joint then rotates by the joint angle q about joint_axis_in_body (through "
                 "joint_pos_in_body); the base body's two slide joints translate it by base_x along its x axis and "
                 "base_y along its y axis (so the base sits at (base_x, base_y, 0) in your frame). The parent of the "
                 "base is the world (your frame)."),
        "blade_center_in_paddle": [round(float(x), 6) for x in m.site_pos[site]],
        "blade_normal": "the paddle body's local +x axis (the face normal); the handle runs along its local +z",
        "blade_half_size_m": [0.0075, 0.075, 0.075],
    }


def limits(s) -> dict:
    return {"joint_names": rcb_tt.JOINTS,
            "joint_low": [round(float(x), 4) for x in s.JOINT_LOW],
            "joint_high": [round(float(x), 4) for x in s.JOINT_HIGH],
            "joint_speed_limit": VEL_LIMIT.tolist(),
            "joint_accel_limit": rcb_tt.ACC_LIMIT.tolist(),
            "joint_jerk_limit": rcb_tt.JERK_LIMIT.tolist(),
            "units": "base_x, base_y in m, m/s, m/s^2, m/s^3; q1..q7 in rad, rad/s, rad/s^2, rad/s^3",
            "arm": {"robot": "Franka Emika Panda (FER): the manufacturer's joint limits (Franka 'Control Interface "
                             "Specification and Robot Limits'; bodies/franka_panda/body.toml)",
                    "torque_limit_nm": rcb_tt.ARM_LIM.tau.tolist(), "torque_rate_limit_nm_s": TORQUE_RATE.tolist()},
            "base": {"travel_x": [rcb_tt.BASE_LO[0], rcb_tt.BASE_HI[0]], "travel_y": [rcb_tt.BASE_LO[1], rcb_tt.BASE_HI[1]],
                     "home": rcb_tt.HOME.tolist(), "max_speed_m_s": rcb_tt.BASE_VMAX,
                     "max_accel_m_s2": rcb_tt.BASE_AMAX, "max_jerk_m_s3": rcb_tt.BASE_JMAX,
                     "force_limit_n": rcb_tt.BASE_FORCE, "moving_mass_kg": 76.8,
                     "note": "per axis; speed 2 m/s (a belt-driven linear gantry, as DeepMind's table-tennis robot), "
                             "acceleration 8 m/s^2 (the drives' force limit for the moving mass), jerk 200 m/s^3 "
                             "(an estimate: no manufacturer value)"},
            "torque_limit": TORQUE_LIMIT.tolist(),
            "max_target_step": [round(float(x), 6) for x in STEP_LIM],
            "max_target_second_difference": [round(float(x), 6) for x in rcb_tt.ACC_LIMIT * rcb_tt.CONTROL_DT ** 2],
            "checks": ("a traj is refused (400) if two consecutive rows differ by more than max_target_step or three "
                       "consecutive rows have a second difference beyond max_target_second_difference (= the "
                       "acceleration limit x (10 ms)^2); the first row used is rejected if it does so with the target "
                       "in force (and its velocity, zero if the rows start later). Jerk is not checked: the servo "
                       "smooths it"),
            "controller": {"kp": KP.tolist(), "kd": KD.tolist(), "resync_rad": rcb_tt.RESYNC,
                           "law": ("at 1 kHz; the reference r interpolates linearly from the previous target to the "
                                   "new one over the 10 ms step, its velocity rd = their difference / 10 ms. A setpoint "
                                   "generator follows (r, rd) and never exceeds the speed (the arm's at 0.9 of its "
                                   "limits), acceleration and jerk limits (the arm's jerk also capped by its torque-rate limit at the pose: "
                                   "0.7 x 1000 N m/s / the row sums of the arm's inertia matrix); a reference beyond "
                                   "them is followed late. Arm: tau = M qdd_sp + kp (q_sp - q) + kd (qd_sp - qd) + "
                                   "gravity/Coriolis, then limited to 87 / 12 N m and 1000 N m/s of change (1 N m per "
                                   "ms); a joint pushed more than resync_rad from its setpoint makes the setpoint "
                                   "follow it. Velocity reflex: an arm joint faster than 1.05 x its velocity limit "
                                   "stops the robot - the targets are ignored and the setpoints brake to rest at the "
                                   "pose of the trigger - for 1 s, then it resumes from rest (servo.reflex, "
                                   "servo.n_reflex); the collision reflex does the same when the robot's links or paddle "
                                   "press on the table with more than 20 N (servo.n_collision_reflex). Base: force = kp (b_sp - b) + kd (bd_sp - bd) + bias, clipped at "
                                   "force_limit_n")},
            "ready_pose": [round(float(x), 5) for x in s.inst["q0"]],
            "ready_configuration": [round(float(x), 5) for x in np.r_[rcb_tt.HOME, s.inst["q0"]]],
            "max_rows_per_command": MAX_ROWS}


def spec(R) -> dict:
    return {"action_interface": "joint position targets at 100 Hz for the rail base and the arm; no IK or stroke planner",
            "kinematics": kinematics(R.s.m), "limits": limits(R.s)}
