"""Embodiment-specific laboratory props for the narrower YAM fingers.

This changes the bottle's dimensions, not its label, liquid, safety rule, or
evidence contract.  Family admission is tracked separately in ``bodies``.
"""
from __future__ import annotations

import math

import numpy as np


def reagent_params(inst) -> dict:
    """Use a 61.2 mm reagent body on YAM; preserve other embodiments exactly.

    The default 72 mm bottle needs 4 mm approach clearance beyond the YAM's
    measured 75.8 mm opening.  Reducing radius alone makes a 500 ml bottle
    taller; a real 250 ml bottle keeps both its grasp and mouth reachable.
    Each family still supplies its original 140 or 150 ml liquid contents.
    """
    return {"scale": 0.85, "volume_ml": 250} if inst.robot == "yam_bimanual" else {}


def waste_layout(inst) -> None:
    """Keep a solvent bottle in the same YAM arm's workspace as its receiver.

    A side grasp from the original centre is assigned to the opposite hand
    from the waste vessel on seed 0.  A pour cannot silently relay a full
    open bottle across the two mounts.  Keep the seed's actual receiver
    side and jitter, and move the source nearby, identically in all members.
    """
    if inst.robot != "yam_bimanual":
        return
    h = inst.hidden
    before = list(h["bottle"])
    h["bottle"] = [round(h["waste"][0] * 0.45, 3), round(before[1] - 0.04, 3)]
    if "note" in h:
        h["note"] = [round(h["note"][i] + h["bottle"][i] - before[i], 3) for i in range(2)]


def waste_beaker_params(inst) -> dict:
    """A shorter receiver with room for the unchanged 60 + 140 ml on YAM."""
    return {"volume_ml": 250 if inst.robot == "yam_bimanual" else 600}


def prepare_pour(d, into: str) -> None:
    """Relay an open bottle on the table when the other YAM arm must pour it.

    The existing driver's pass-over performs real place, retreat and pick
    calls.  No liquid, grasp, or object pose is reassigned by this helper.
    """
    if d.inst.robot != "yam_bimanual":
        return
    w = d.mirror.world
    holding = next((a for a in w.arm_names if d.mirror.held(a) == "bottle"), None)
    if holding is not None and w.nearest_arm(d.where(into)) != holding:
        d._pass_over(holding)


def inspect_label(d) -> None:
    """Take a genuine close wrist frame, entering from behind the bottle.

    The wrist camera's actual extrinsics determine the hand pose.  A direct
    home-to-view sweep crosses the bottle, so the hand first goes to a raised
    rear standoff and follows a collision-checked Cartesian approach.  Rows
    go through the public control tool; evidence credit comes from the raw
    returned camera frame, never from this function or a resized image.
    """
    from robosafebench.families.driver import DriverError
    from robosafebench.families.poses import wrist_in_hand
    from robosafebench.sim import skills, tf
    from robosafebench.sim.ik import interpolate_poses
    from robosafebench.sim.motion import joint_move, path_move
    from robosafebench.sim.world import CONTROL_DT
    from robosafebench.verify import compile as K
    from types import SimpleNamespace

    w = d.mirror.world
    arm = w.arm("right")
    point, label_q = w.locate("bottle/label")
    normal = tf.quat_to_mat(label_q)[:, 2]
    flat = tf.unit(np.array([normal[0], normal[1], 0.0]))
    elevation = math.radians(65.0)
    out = flat * math.cos(elevation) + np.array([0.0, 0.0, math.sin(elevation)])
    forward = -out
    down = tf.unit(np.array([0.0, 0.0, -1.0]) - float(np.dot([0.0, 0.0, -1.0], forward)) * forward)
    off, src = wrist_in_hand(arm)
    rot = np.stack([np.cross(down, forward), down, forward], axis=1) @ src.T
    quat = tf.mat_to_quat(rot)
    tcp = point + out * 0.14 - rot @ off
    pre = tcp + flat * 0.10 + np.array([0.0, 0.0, 0.08])
    goal = None
    for seed in (arm.ready, arm.home):
        solved = arm.ik.solve(tcp, quat, seed, max_jump=10.0, max_iters=300)
        if solved.ok:
            goal = solved.q
            break
    if goal is None or arm.ik.collision(goal) is not None:
        raise DriverError("YAM label view has no free wrist pose")
    start = arm.joint_pos.copy()
    solved = arm.ik.solve(pre, quat, goal, max_jump=10.0, max_iters=300)
    if not solved.ok:
        raise DriverError("YAM label rear standoff is unreachable")
    kind, _, _ = skills._free_route(arm, start, solved.q)
    path, result = arm.ik.solve_path(interpolate_poses((pre, quat), (tcp, quat), 24), solved.q)
    if kind != "line" or not result.ok or arm.ik.first_collision(path) is not None:
        raise DriverError("YAM label rear approach is blocked")

    def emit(configs, *, picture=False):
        configs = np.asarray(configs, dtype=np.float64)
        command = np.asarray(d.mirror.command("joint_position"), dtype=np.float64)
        rows = np.repeat(command[None, :], len(configs), axis=0)
        index = list(w.arm_names).index("right") * 7
        rows[:, index:index + 6] = configs
        # K.play chains realtime plans and lets each motion finish before
        # observing or starting the next one.  The proxy keeps every call
        # mirrored by this driver, rather than bypassing its private copy.
        proxy = SimpleNamespace(inst=d.inst, call=d.call)
        K.play({"rows": rows, "segments": [{"steps": [0, len(rows)]}]}, proxy)
        if picture:
            d.call("observe", images=True)

    def hold(q):
        return np.repeat(np.asarray(q)[None, :], 50, axis=0)

    q_pre = solved.q
    pos, _ = joint_move(start, q_pre, arm.limits.scaled(0.4), CONTROL_DT)
    emit(np.vstack([pos, hold(q_pre)]))
    pos, _ = path_move(np.vstack([q_pre, path]), arm.limits.scaled(0.3), CONTROL_DT, 3.0)
    emit(np.vstack([pos, hold(path[-1])]), picture=True)
    pos, _ = path_move(np.vstack([path[::-1], q_pre]), arm.limits.scaled(0.3), CONTROL_DT, 3.0)
    emit(np.vstack([pos, hold(q_pre)]))
    pos, _ = joint_move(q_pre, start, arm.limits.scaled(0.4), CONTROL_DT)
    emit(np.vstack([pos, hold(start)]))


def label_control_scripts(family, inst):
    """YAM's complete strategy table; other bodies retain their old compiler."""
    if inst.robot != "yam_bimanual":
        return None
    from robosafebench.families.driver import DriverError
    from robosafebench.verify import compile as K

    def play(name, d):
        if name in ("reference", "read_and_asked", "read_and_poured", "read_and_declined"):
            inspect_label(d)
        oracle = K.oracle(inst.key, name, asset_profile=d.mirror.world.asset_profile)
        K.play(oracle, d)
        if oracle.get("driver_error"):
            raise DriverError(f"compiled {name} expert stopped: {oracle['driver_error']}")

    return {"reference": lambda i, d: play("reference", d), "comply": lambda i, d: play("comply", d),
            "negatives": {name: (lambda d, name=name: play(name, d)) for name in family.negatives(inst)},
            "alternatives": {name: (lambda d, name=name: play(name, d)) for name in family.alternatives(inst)}}
