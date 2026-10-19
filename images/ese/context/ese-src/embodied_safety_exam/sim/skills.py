"""Skills: generators of control rows.

A skill is a Python generator. It yields one control row at a time; the caller applies the row with `world.step(row)`
and asks for the next one. The skill reads the robot's own sensors between rows (joint positions, gripper opening, pad
forces, wrist force), so the caller must step the world with every row it is given before resuming the generator.
When the skill is done the generator returns a `Status`. `run(world, skill)` does this loop.

    status = run(world, pick(world, "tube1"))

A trial is still fully described by the rows: replaying `world.record` reproduces the state without running any skill.

What a skill may use:
- to decide where to go: poses of objects and sites from `world.locate` (a stand-in for perception, see there), or
  poses given by the caller;
- to decide whether it succeeded: only joint positions and velocities, the gripper opening, the forces on the finger
  pads and the force at the wrist. A status never looks at where the object really is.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Generator

import numpy as np

from . import tf
from .ik import interpolate_poses
from . import robots as _robots
from .motion import joint_move, path_move
from .world import CONTROL_DT, GRIPPER_MAX, World

Row = np.ndarray
Skill = Generator[Row, None, "Status"]

SETTLE_POS = 5.0e-4        # rad: a move is over when every joint is this close to its target ...
SETTLE_VEL = 5.0e-3        # rad/s: ... and this slow
SETTLE_POS_LOADED = 3.0e-3  # rad: accepted when the arm has stopped (what a held object's weight does to the servo)
# The hand's numbers. Both robots carry the Robotiq 2F-85, so these are module constants read from its description in
# `robots.py`; a robot with another hand needs them looked up per world.
TIP_BEYOND_TCP = _robots.get(None).tip_reach_closed    # m: how far the closed fingertips reach past the pinch point
# free distance between the pads (m) against the gripper target (rad), measured on the model
_OPENING_TABLE = _robots.get(None).opening_table
MAX_OPENING = _OPENING_TABLE[0][1]
HOLD_MIN_OPENING = 0.003   # m: fingers closed further than this hold nothing
HOLD_MIN_FORCE = 0.3       # N on each pad


@dataclass
class Status:
    ok: bool
    reason: str = "ok"
    info: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok


def run(world: World, skill: Skill, on_step: Callable[[World], None] | None = None) -> Status:
    """Drive a skill to its end: step the world with each row it yields. Returns the skill's status."""
    try:
        while True:
            row = next(skill)
            world.step(row)
            if on_step is not None:
                on_step(world)
    except StopIteration as stop:
        return stop.value if isinstance(stop.value, Status) else Status(True)


def gripper_target_for_opening(width: float, world=None) -> float:
    """Gripper target (rad) that leaves `width` metres between the pads (of the hand of `world`; default: the 2F-85)."""
    table = _OPENING_TABLE if world is None else world.spec.opening_table
    xs = [w for _, w in reversed(table)]
    ys = [g for g, _ in reversed(table)]
    return float(np.interp(width, xs, ys))


def max_opening(world=None) -> float:
    """The widest free distance between the pads of the hand of `world` (m)."""
    return MAX_OPENING if world is None else float(world.spec.opening_table[0][1])


def fingertip_reach(world, width: float) -> float:
    """How far the fingertips of the hand of `world` reach past the pinch point with `width` between the pads."""
    from . import props as _props
    tip = world.spec.extra.get("tip_reach")
    return _props.fingertip_reach(width) if tip is None else float(tip)


def holding(world: World) -> bool:
    """Something is between the fingers: they are not fully closed and both pads feel a force."""
    if world.held is not None:                 # the grasp assist holds it
        return True
    pads = world.pad_forces()
    return bool(world.gripper_opening() > HOLD_MIN_OPENING and pads[0] > HOLD_MIN_FORCE and pads[1] > HOLD_MIN_FORCE)


def ready_posture(world: World, kind: str) -> np.ndarray:
    """A posture from which grasps of this kind are reached without passing a singularity.

    `top`: the ready posture (`world.ready`), tool pointing down. `side`: the same with wrist_1 turned back a quarter turn; the tool
    is level and points away from the robot, with the wrist's last link 0.1 m *under* the tool axis. `side_low`:
    wrist_1 turned the other way and wrist_2 by half a turn; the tool is level and points the same way, 0.2 m lower,
    with the wrist *over* the tool axis: the posture for reaching something low, where the wrist of `side` would be
    in the table.
    """
    spec = world.spec
    if kind == "top":
        return world.ready.copy()
    if kind not in ("side", "side_low"):
        raise ValueError(f"no ready posture called {kind!r}")
    # the robot's own side postures, moved along with a ready posture the scene has changed
    side = np.array(spec.ready_side if kind == "side" else spec.ready_side_low, dtype=np.float64)
    return side + (world.ready - np.array(spec.ready, dtype=np.float64))


def _ready_list(world: World, kind: str) -> list[np.ndarray]:
    if kind == "side":
        return [ready_posture(world, k) for k in ("side", "side_low")]
    alt = getattr(world, "ready_alt", None)
    return [ready_posture(world, "top")] + ([alt.copy()] if alt is not None else [])


# ---- building blocks (generators that return plain values) ---------------------------------------------------------
def _row(q, grip: float) -> Row:
    return np.concatenate([np.asarray(q, dtype=np.float64), [float(grip)]])


def _track(world: World, pos: np.ndarray, vel: np.ndarray, grip: float, guard: Callable[[], bool] | None = None):
    """Yield rows that follow a sampled joint trajectory. Returns the index reached (len(pos) when complete).

    With `world.hand_speed_limit` set (a tool called with `speed="slow"`) the trajectory is first played slower, the
    same way at a uniformly stretched time, so that the pinch point moves no faster than that limit anywhere on it;
    the index returned is then that of the trajectory as given."""
    n0 = pos.shape[0]
    pos, vel, stretch = _slowed(world, pos, vel)
    for k in range(pos.shape[0]):
        if guard is not None and guard():
            return min(int(k / stretch), n0 - 1) if stretch != 1.0 else k
        yield _row(pos[k] + world.lead * vel[k], grip)
    return n0


SLOW_MARGIN = 0.95          # a slowed trajectory aims this far under the limit: the servos follow the samples closely, not exactly


def _slowed(world: World, pos: np.ndarray, vel: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """The trajectory (pos, vel), sampled at the control period from where the arm is now, stretched in time so that
    the pinch point moves no faster than `world.hand_speed_limit` (m/s); unchanged, with stretch 1, when no limit is
    set or the trajectory keeps under it. The peak is read from the pinch point's positions at the samples (forward
    kinematics), so a joint move, a straight line and a turn of the wrist are all held to the same figure."""
    cap = getattr(world, "hand_speed_limit", None)
    if not cap or pos.shape[0] < 1:
        return pos, vel, 1.0
    q0 = np.asarray(world.joint_pos, dtype=np.float64)
    pts = np.array([world.ik.fk(q)[0] for q in [q0] + list(pos)])
    peak = float(np.max(np.linalg.norm(np.diff(pts, axis=0), axis=1))) / CONTROL_DT
    if peak <= cap * SLOW_MARGIN:
        return pos, vel, 1.0
    stretch = peak / (cap * SLOW_MARGIN)
    n0 = pos.shape[0]
    n = int(math.ceil(n0 * stretch))
    t_old = np.arange(n0 + 1, dtype=np.float64)                   # sample times of the given trajectory (in ticks, 0: now)
    t_new = np.minimum((np.arange(n, dtype=np.float64) + 1.0) / stretch, float(n0))
    full = np.vstack([q0[None, :], pos])
    v_full = np.vstack([np.zeros((1, vel.shape[1])), vel])
    new_pos = np.column_stack([np.interp(t_new, t_old, full[:, j]) for j in range(full.shape[1])])
    new_vel = np.column_stack([np.interp(t_new, t_old, v_full[:, j]) for j in range(v_full.shape[1])]) / stretch
    new_pos[-1], new_vel[-1] = pos[-1], vel[-1] / stretch
    return new_pos, new_vel, stretch


def _settle(world: World, q, grip: float, timeout: float = 1.5, min_ticks: int = 2):
    """Hold a target until the arm has arrived and is still. Returns (arrived, largest joint error)."""
    q = np.asarray(q, dtype=np.float64)
    n = max(int(round(timeout / CONTROL_DT)), min_ticks)
    # a robot whose servos give more under a load than the bench arms' says how much (`RobotSpec.extra`)
    spec = getattr(world, "spec", None)
    loaded = float((getattr(spec, "extra", None) or {}).get("settle_pos_loaded", SETTLE_POS_LOADED))
    err = float("inf")
    still = 0
    for k in range(n):
        yield _row(q, grip)
        err = float(np.max(np.abs(world.joint_pos - q)))
        still = still + 1 if float(np.max(np.abs(world.joint_vel))) < SETTLE_VEL else 0
        if k + 1 >= min_ticks and still > 0 and err < SETTLE_POS:
            return True, err
        if still >= 10 and err < loaded:                  # at rest a little off target: the servo is carrying a load
            return True, err
    return False, err


def hold(world: World, seconds: float) -> Skill:
    """Keep the present targets for a while."""
    q, grip = world.target[:-1].copy(), float(world.target[-1])
    for _ in range(max(int(round(seconds / CONTROL_DT)), 1)):
        yield _row(q, grip)
    return Status(True)


def _plan(world: World, goal: tf.Pose, step: float = 0.004, ang_step: float = 0.02, q_from=None):
    """IK for a straight tool path from a configuration (default: where the arm is) to `goal`.

    Returns (joint path including the start, IKResult, length in m, turn in rad)."""
    q0 = world.joint_pos if q_from is None else np.asarray(q_from, dtype=np.float64)
    start = world.ik.fk(q0)
    dist = float(np.linalg.norm(goal[0] - start[0]))
    ang = float(np.linalg.norm(tf.rotvec(start[1], goal[1])))
    n = max(int(math.ceil(dist / step)), int(math.ceil(ang / ang_step)), 1)
    path, res = world.ik.solve_path(interpolate_poses(start, goal, n), q0)
    return np.vstack([q0[None, :], path]), res, dist, ang


def _reach(world: World, first: tf.Pose, then: list[tf.Pose], ready: list | None, ignore=(), ignore_last=(),
           carried=(), seeds: list | None = None):
    """Find how to get to `first` by a free joint move and on to the poses in `then` along straight lines.

    Tries from where the arm is and, failing that, by way of each of the `ready` postures, of which the cheapest
    that works is taken. The free moves are routed by `_free_route` (a joint-space line, if need be after rising),
    with what is in the hand (`carried`) moving along. The straight lines are refused when the robot would pass
    through something on them (checked on the scratch data, objects taken where they are now, `ignore` excepted; on
    the last straight line also `ignore_last`: the thing the fingers are about to close on).
    With `seeds` (postures) the configuration at `first` is also looked for by solving for it outright from each seed,
    wherever that lands, and going there by one free move: for poses far from every ready posture (the hand turned
    back towards the robot to press a button on the front of an appliance).
    Returns (plan, "ok") or (None, why); the plan has `via` (a posture to go through first, or None), `q_first`
    (the configuration at `first`) and `cost` (joint travel).
    """
    q_now = world.joint_pos
    why = "ik_unreachable"
    best = None
    tries = [(via, None) for via in [None] + list(ready or [])] + [(None, seed) for seed in (seeds or [])]
    for via, seed in tries:
        q_start = q_now if via is None else via
        if seed is None:
            path, res, _, _ = _plan(world, first, step=0.02, ang_step=0.1, q_from=q_start)
        else:
            res = world.ik.solve(first[0], first[1], seed, max_jump=10.0)
            path = np.vstack([q_now[None, :], res.q[None, :]])
        if not res.ok:
            continue
        mid: list = []
        last: list = []
        q, ok = path[-1], True
        for i, pose in enumerate(then):
            sub, r2, _, _ = _plan(world, pose, q_from=q)
            if not r2.ok:
                ok = False
                break
            (last if i == len(then) - 1 else mid).extend(list(sub[5::5]) + [sub[-1]])
            q = sub[-1]
        if not ok:
            continue
        hit = world.ik.first_collision(mid, ignore) or world.ik.first_collision(last, tuple(ignore) + tuple(ignore_last))
        if hit is None:
            for q_a, q_b in ([(q_now, path[-1])] if via is None else [(q_now, via), (via, path[-1])]):
                kind, blocker, _ = _free_route(world, q_a, q_b, carried)
                if kind is None:
                    hit = blocker
                    break
        if hit is not None:
            why = "blocked_by_" + hit[1]
            continue
        cost = float(np.sum(np.abs(path[-1] - q_start)))
        if via is not None:
            cost += float(np.sum(np.abs(via - q_now)))
        if best is None or cost < best["cost"] - 1e-9:
            best = {"via": via, "q_first": path[-1], "cost": cost}
        if via is None and seed is None:
            break                       # reachable from where the arm is: no need to look at the detours
    return (best, "ok") if best is not None else (None, why)


def _move_joints(world: World, q_goal, grip: float, speed: float = 1.0, settle: float = 1.5):
    """Straight line in joint space to a known configuration. Returns a Status."""
    pos, vel = joint_move(world.joint_pos, q_goal, world.limits.scaled(speed), CONTROL_DT)
    yield from _track(world, pos, vel, grip)
    ok, err = yield from _settle(world, q_goal, grip, timeout=settle)
    return Status(ok, "ok" if ok else "not_reached", {"joint_err": err})


PATH_CLEARANCE = 0.005     # m: how far a planned transfer or turn keeps the hand and its load from everything else


def _path_hit(world: World, configs, ignore=(), carried=(), arm_vs_load: bool = False, clearance: float = 0.0) -> tuple[str, str] | None:
    """First thing the robot or its load would be inside (or, with `clearance`, nearer to than that) along a sequence
    of configurations. What it already touches at the first of them (a load standing on the table, fingers next to
    something) is tolerated over the first fifth."""
    configs = list(configs)
    if not configs:
        return None
    at_start = world.ik.collision(configs[0], ignore, carried, arm_vs_load=arm_vs_load, clearance=clearance)
    lead = max(len(configs) // 5, 1) if at_start is not None else 0
    for k, q in enumerate(configs):
        hit = world.ik.collision(q, tuple(ignore) + ((at_start[1],) if k < lead else ()), carried, arm_vs_load=arm_vs_load, clearance=clearance)
        if hit is not None:
            return hit
    return None


def _move(world: World, goal: tf.Pose, grip: float, *, linear: bool, speed: float = 1.0, lin_speed: float = 0.20,
          ang_speed: float = 1.5, guard: Callable[[], bool] | None = None, settle: float = 1.5, check=None):
    """Move the tool to `goal`. Returns a Status (reasons: ik_<why>, path_blocked, stopped, not_reached). With
    `check = (ignore, carried)` the way is first tested for collisions and nothing is moved if it is not free."""
    limits = world.limits.scaled(speed)
    path, res, dist, ang = _plan(world, goal)
    if not res.ok:
        return Status(False, "ik_" + res.reason, {"pos_err": res.pos_err, "rot_err": res.rot_err, "jump": res.jump,
                                                  "solved": int(path.shape[0] - 1)})
    if check is not None:
        hit = _path_hit(world, list(path[0::4]) + [path[-1]], check[0], check[1])
        if hit is not None:
            return Status(False, "path_blocked", {"by": hit[1], "who": hit[0]})
    if linear:
        duration = max(dist / (lin_speed * speed), ang / (ang_speed * speed)) / 0.75    # 25 % ramps at both ends
        pos, vel = path_move(path, limits, CONTROL_DT, duration)
    else:
        pos, vel = joint_move(path[0], path[-1], limits, CONTROL_DT)
    reached = yield from _track(world, pos, vel, grip, guard)
    if reached < pos.shape[0]:
        yield from _settle(world, world.joint_pos, grip, timeout=0.3)
        return Status(False, "stopped", {"fraction": reached / pos.shape[0]})
    ok, err = yield from _settle(world, path[-1], grip, timeout=settle)
    if not ok:
        return Status(False, "not_reached", {"joint_err": err})
    return Status(True, "ok", {"joint_err": err})


def _samples(q0, q1, step: float = 0.03) -> list[np.ndarray]:
    """Configurations along a straight joint-space line, close enough together to test it for collisions."""
    q0, q1 = np.asarray(q0, dtype=np.float64), np.asarray(q1, dtype=np.float64)
    n = max(int(math.ceil(float(np.max(np.abs(q1 - q0))) / step)), 1)
    return list(np.linspace(q0, q1, n + 1)[1:])


def held_objects(world: World) -> tuple[str, ...]:
    """Names of the objects both finger pads touch. Ground truth, used only to leave what is in the hand out of
    path tests (on the scratch data a held object stays where it was while the arm moves on)."""
    sides: dict[str, set] = {}
    for c in world.privileged()["contacts"]:
        if "robot" in (c["a"], c["b"]):
            other, geom = (c["b"], c["geom_a"]) if c["a"] == "robot" else (c["a"], c["geom_b"])
            side = world._pad_names.get(geom)
            if side == "left":
                sides.setdefault(other, set()).add("l")
            elif side == "right":
                sides.setdefault(other, set()).add("r")
    names = {n for n, s in sides.items() if len(s) == 2 and n in world.objects}
    if world.held is not None:
        names.add(world.held)
    for a, b in sorted(getattr(world, "fastened", {}).items()):      # what is fastened onto a held thing goes with it (a cap on a bottle)
        if b in names:
            names.add(a)
    return tuple(sorted(names))


def _follow(world: World, path: np.ndarray, grip: float, length: float, *, lin_speed: float, speed: float = 1.0,
            guard: Callable[[], bool] | None = None, settle: float = 1.5):
    """Follow a joint path whose tool travels `length` metres, at `lin_speed`. Returns a Status."""
    duration = length / max(lin_speed * speed, 1e-6) / 0.75
    pos, vel = path_move(path, world.limits.scaled(speed), CONTROL_DT, duration)
    reached = yield from _track(world, pos, vel, grip, guard)
    if reached < pos.shape[0]:
        yield from _settle(world, world.joint_pos, grip, timeout=0.3)
        return Status(False, "stopped", {"fraction": reached / pos.shape[0]})
    ok, err = yield from _settle(world, path[-1], grip, timeout=settle)
    return Status(ok, "ok" if ok else "not_reached", {"joint_err": err})


def _carry(world: World, targets, offset, grip: float, *, lin_speed: float = 0.10, speed: float = 1.0,
           guard: Callable[[], bool] | None = None, settle: float = 1.5, carried=None, ignore=()):
    """Move a point fixed to the tool through `targets` on straight lines without tilting the tool (`IK.solve_carry`).

    With `carried` (what is in the hand, from `_attached`; may be empty) the way is first tested for collisions and
    refused if the robot or what it carries would pass through anything not named in `ignore`.
    Returns a Status: ik_<why>, path_blocked, stopped, not_reached, ok.
    """
    q0 = world.joint_pos
    start = world.ik.carried_point(q0, offset)
    path, res = world.ik.carry_path(targets, q0, offset)
    if not res.ok:
        return Status(False, "ik_" + res.reason, {"pos_err": res.pos_err, "jump": res.jump, "solved": int(path.shape[0] - 1)})
    if carried is not None:
        hit = world.ik.first_collision(list(path[4::4]) + [path[-1]], ignore, carried)
        if hit is not None:
            return Status(False, "path_blocked", {"by": hit[1]})
    pts = [start] + [np.asarray(t, dtype=np.float64) for t in targets]
    length = float(sum(np.linalg.norm(b - a) for a, b in zip(pts, pts[1:])))
    return (yield from _follow(world, path, grip, length, lin_speed=lin_speed, speed=speed, guard=guard, settle=settle))


def _grip(world: World, target: float, rate: float = 2.0, timeout: float = 1.5, keep: bool = False):
    """Ramp the gripper target and wait until the fingers stop. Returns the opening (m). Opening the hand lets go of
    an assisted grasp: at once, or, with `keep`, when the fingers have stopped."""
    q = world.target[:-1].copy()
    g = float(world.target[-1])
    target = min(max(float(target), 0.0), GRIPPER_MAX)
    let_go = world.held is not None and target < g - 1e-9
    if let_go and not keep:                               # opening the hand lets go of an assisted grasp
        world.detach()
    step = rate * CONTROL_DT
    while abs(target - g) > 1e-12:
        g = target if abs(target - g) <= step else g + math.copysign(step, target - g)
        yield _row(q, g)
    still = 0
    for _ in range(int(round(timeout / CONTROL_DT))):
        yield _row(q, g)
        still = still + 1 if abs(world.gripper_vel) < 0.02 else 0
        if still >= 5:
            break
    if let_go and keep:
        world.detach()
    return world.gripper_opening()


def _close(world: World, squeeze: float | None = None):
    """Close until the fingers stop. With `squeeze` the target runs in at 1 rad/s only until both pads feel the
    object and is then held `squeeze` past where the fingers are, so the full force never comes on (a light or
    hanging object is not pushed about)."""
    if squeeze is None:
        return (yield from _grip(world, GRIPPER_MAX))
    q = world.target[:-1].copy()
    g = float(world.target[-1])
    while g < GRIPPER_MAX:
        g = min(g + 1.0 * CONTROL_DT, GRIPPER_MAX)
        yield _row(q, g)
        if float(np.min(world.pad_forces())) > HOLD_MIN_FORCE:
            break
    return (yield from _grip(world, min(world.gripper_pos + max(float(squeeze), 0.0), GRIPPER_MAX)))


def _grasp_frames(kind: str, grip_pose: tf.Pose, yaw_deg: float | None, approach_dir, base_xy) -> list[np.ndarray]:
    """Tool orientations (quaternions) for a grasp at a grip site. Entries come in pairs: the same grasp with the
    gripper turned half a turn about its approach axis."""
    axis = tf.rotate(grip_pose[1], [0.0, 0.0, 1.0])
    if kind == "top":
        z = -axis                                           # come down along the object's axis
        if float(axis[2]) < -0.2:                           # the object lies upside down (a knife that fell over): its
            z = axis                                        # grasp is then reached from its other side, from above
        if yaw_deg is None:
            y = tf.rotate(grip_pose[1], [0.0, 1.0, 0.0])    # close along the grip site's y axis
        else:
            y = np.array([math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg)), 0.0])
        y = tf.unit(y - np.dot(y, z) * z)
        return [tf.quat_from_axes(y=y, z=z), tf.quat_from_axes(y=-y, z=z)]
    if kind == "side":
        if approach_dir is None:
            out = np.array([grip_pose[0][0] - base_xy[0], grip_pose[0][1] - base_xy[1], 0.0])   # away from the robot
            out = tf.unit(out - np.dot(out, axis) * axis)
            across = np.cross(axis, out)
            dirs = [out, across, -across]
        else:                                               # one direction, or several to choose from
            given = np.atleast_2d(np.asarray(approach_dir, dtype=np.float64))
            dirs = [tf.unit(a - np.dot(a, axis) * axis) for a in given]     # approach square to the object's axis
        frames = []
        for z in dirs:
            y = np.cross(axis, z)                           # fingers close across the object
            frames += [tf.quat_from_axes(y=y, z=z), tf.quat_from_axes(y=-y, z=z)]
        return frames
    raise ValueError(f"unknown grasp type {kind!r}")


# ---- skills --------------------------------------------------------------------------------------------------------
def move_to(world: World, pose, *, linear: bool = False, speed: float = 1.0) -> Skill:
    """Move the tool centre point to `pose` ((pos, quat) or {"pos", "quat"}), keeping the gripper as it is.

    `linear=True` moves the tool along a straight line; otherwise the joints move along a straight line in joint
    space to the configuration that continues the current one. Status reasons: `ik_not_converged`, `ik_branch_flip`,
    `ik_joint_limit` (nothing was moved), `not_reached` (the arm did not arrive: something is in the way).
    """
    goal = tf.as_pose(pose)
    st = yield from _move(world, goal, float(world.target[-1]), linear=linear, speed=speed)
    p, _ = world.tcp_pose()
    st.info["tcp_err"] = float(np.linalg.norm(p - goal[0]))
    return st


# A fast joint-space move is tracked to about 0.02 rad per joint (the servos lag differently under acceleration), which
# at arm's length is 15 mm of tool position. A free line is therefore accepted only if it also stays clear with each
# of the three big joints off by this much either way.
FREE_SLACK = 0.03          # rad


def _off_line(world: World) -> list:
    """The offsets a free line is tested with: none, and each of the big joints (all but the last three) either way."""
    if getattr(world, "_off_line_cache", None) is None:
        n = world.spec.n
        world._off_line_cache = [np.zeros(n)] + [s * FREE_SLACK * np.eye(n)[j] for j in range(n - 3) for s in (1.0, -1.0)]
    return world._off_line_cache


def _slack_hit(world: World, q, ignore=(), carried=()) -> tuple[str, str] | None:
    for off in _off_line(world):
        hit = world.ik.collision(q + off, ignore, carried)
        if hit is not None:
            return hit
    return None


def _line_hit(world: World, q0, q1, carried=()) -> tuple[str, str] | None:
    """First thing the robot (or what it carries) would touch on the straight joint-space line from q0 to q1, the
    line taken with `FREE_SLACK` of error on the big joints. Something already that close at q0 (fingers next to an
    object just let go of, a held object standing on the table) is tolerated over the first fifth of the way."""
    configs = _samples(q0, q1, 0.02)
    at_start = _slack_hit(world, np.asarray(q0, dtype=np.float64), (), carried)
    lead = max(len(configs) // 5, 1) if at_start is not None else 0
    for k, q in enumerate(configs):
        hit = _slack_hit(world, q, (at_start[1],) if k < lead else (), carried)
        if hit is not None:
            return hit
    return None


def _free_route(world: World, q0, q1, carried=()):
    """How to get from q0 to q1 by a free move. Returns ("line", None, 0.0); or ("turn", configuration, 0.0) when
    the straight joint-space line is blocked but two lines by way of that configuration are free (the base joint
    turned first with everything else as it is, or last); or ("rise", joint path, metres) when the line is free after
    raising the tool straight up by 0.08, 0.16 or 0.24 m (without tilting it); or, on a base that drives, ("back",
    joint path, metres) when it is free after drawing the tool straight back towards the base; or (None, (who,
    what), 0.0) when nothing works."""
    hit = _line_hit(world, q0, q1, carried)
    if hit is None:
        return ("line", None, 0.0)
    q0 = np.asarray(q0, dtype=np.float64)
    q1 = np.asarray(q1, dtype=np.float64)
    if abs(float(q1[0] - q0[0])) > 0.05:
        for way in (np.concatenate([q1[:1], q0[1:]]), np.concatenate([q0[:1], q1[1:]])):
            if _line_hit(world, q0, way, carried) is None and _line_hit(world, way, q1, carried) is None:
                return ("turn", way, 0.0)
    top = world.ik.carried_point(q0)
    at_start = world.ik.collision(q0, (), carried)
    tolerate = (at_start[1],) if at_start is not None else ()
    for rise in (0.08, 0.16, 0.24):
        up, res = world.ik.carry_path([top + np.array([0.0, 0.0, rise])], q0)
        if not res.ok:
            break
        if world.ik.first_collision(list(up[4::4]) + [up[-1]], tolerate, carried) is not None:
            continue
        if _line_hit(world, up[-1], q1, carried) is None:
            return ("rise", up, rise)
    if getattr(world, "base", None):
        # An arm on a base that drives works over furniture taller than its own rest posture: a hand over a counter
        # cannot rise much and the line home dips through the counter's edge. It is drawn straight back towards the
        # base's vertical first (without tilting it), as far as it takes.
        to_base = np.array([world.scene["robot"]["pos"][0] - top[0], world.scene["robot"]["pos"][1] - top[1], 0.0])
        if float(np.linalg.norm(to_base)) > 0.25:
            to_base = tf.unit(to_base)
            for back in (0.10, 0.20, 0.30, 0.40):
                if back > float(np.hypot(world.scene["robot"]["pos"][0] - top[0], world.scene["robot"]["pos"][1] - top[1])) - 0.15:
                    break
                way, res = world.ik.carry_path([top + back * to_base], q0)
                if not res.ok:
                    break
                if world.ik.first_collision(list(way[4::4]) + [way[-1]], tolerate, carried) is not None:
                    break
                if _line_hit(world, way[-1], q1, carried) is None:
                    return ("back", way, back)
    return (None, hit, 0.0)


def _go(world: World, q_goal, grip: float, carried=(), speed: float = 1.0):
    """Free move to a configuration by the route `_free_route` finds. Returns a Status (path_blocked: not moved)."""
    kind, data, rise = _free_route(world, world.joint_pos, q_goal, carried)
    if kind is None:
        return Status(False, "path_blocked", {"by": data[1]})
    if kind in ("rise", "back"):
        st = yield from _follow(world, data, grip, rise, lin_speed=0.15, speed=speed)
        if not st.ok:
            return Status(False, f"{st.reason}:{kind}", st.info)
    if kind == "turn":
        st = yield from _move_joints(world, data, grip, speed, settle=0.3)
        if not st.ok and st.info.get("joint_err", 1.0) > 0.02:
            return Status(False, f"{st.reason}:turn", st.info)
    st = yield from _move_joints(world, q_goal, grip, speed)
    if kind == "rise":
        st.info["rose_by"] = rise
    return st


def move_joints(world: World, q, *, speed: float = 1.0, check: bool = True) -> Skill:
    """Move to a joint configuration along a straight line in joint space, keeping the gripper as it is.

    With `check` (the default) the line is first tested for collisions, what is in the hand moving along. If the
    robot or its load would pass through something, the tool is first raised straight up (by 0.08, 0.16 or 0.24 m,
    without tilting it) and the line taken from there; if that does not clear the way either, nothing is moved.
    Reasons: `joint_limit`, `path_blocked` (`info["by"]`; arm not moved), `not_reached`.
    """
    q = np.asarray(q, dtype=np.float64)
    if q.shape != world.home.shape or np.any(q < world.arm_range[:, 0]) or np.any(q > world.arm_range[:, 1]):
        return Status(False, "joint_limit", {})
    g = float(world.target[-1])
    if not check:
        return (yield from _move_joints(world, q, g, speed))
    return (yield from _go(world, q, g, _attached(world, held_objects(world)), speed))


def carry(world: World, pos, obj: str | None = None, *, lin_speed: float = 0.10, speed: float = 1.0, check: bool = True) -> Skill:
    """Move the tool centre point (or, with `obj`, the origin of the held object) to `pos` on a straight line
    without tilting the tool: a vessel held upright stays upright to the last decimal.

    Only the shoulder pan, the shoulder lift and the elbow do the moving, wrist_1 undoing the turn of the other two;
    the tool turns about the vertical with the pan. Unlike `move_to(linear=True)` this works in wrist-singular
    postures (a tool held level and square to the arm, as after a side grasp from the left or right).
    With `check` the way is tested first, the load moving along with the hand.
    Reasons: `ik_not_converged`, `ik_joint_limit`, `ik_branch_flip`, `path_blocked` (arm not moved), `not_reached`.
    """
    offset = None
    if obj is not None:
        offset = tf.compose(tf.inverse(world.tcp_pose()), world.locate(obj))[0]
    carried = _attached(world, held_objects(world)) if check else None
    st = yield from _carry(world, [np.asarray(pos, dtype=np.float64)], offset, float(world.target[-1]),
                           lin_speed=lin_speed, speed=speed, carried=carried)
    return st


def position_to_pour(world: World, obj: str, over: str, *, offset: float = 0.010, lin_speed: float = 0.10) -> Skill:
    """Bring the lip of the held vessel `obj` over the opening of the vessel `over`, ready to tilt about that lip.

    The vessel must be held by its side, upright. The lip is the point of its rim that will be lowest once the wrist
    rolls towards `over`; it is carried (level, see `carry`) to `offset` metres short of the centre of the other
    rim, at the height it is at. On success `info` has what `tilt` needs to pour on the spot:
    `tilt(world, obj, info["sign"] * angle, rate, axis=info["axis"], pivot=info["pivot"])`.
    Reasons: `not_holding`, `not_a_vessel`, `ik_...`, `path_blocked` (arm not moved), `not_reached`.
    """
    if not holding(world):
        return Status(False, "not_holding", {})
    v = world.objects.get(obj, {}).get("meta", {}).get("vessel")
    if not v or "vessel" not in world.objects.get(over, {}).get("meta", {}):
        return Status(False, "not_a_vessel", {})
    ik = world.ik
    up = np.array([0.0, 0.0, 1.0])
    tcp = world.tcp_pose()
    tcp_inv = tf.inverse(tcp)
    axis = tf.rotate(tcp[1], [0.0, 0.0, 1.0])
    lean = tf.unit(np.cross(axis, up))                           # a positive roll of the wrist leans the top this way
    v_over = world.objects[over]["meta"]["vessel"]
    src_rim = world.locate(f"{obj}/{v.get('rim_site', 'rim')}")[0]
    dst_rim = world.locate(f"{over}/{v_over.get('rim_site', 'rim')}")[0]
    if v.get("spout_site"):
        # a vessel with a spout pours over it: the turn is about the level axis square to the spout's direction
        lip = world.locate(f"{obj}/{v['spout_site']}")[0]
        lean = lip - src_rim
        lean = tf.unit(np.array([lean[0], lean[1], 0.0]))
        axis = np.cross(up, lean)
        sign = 1.0
    else:
        sign = 1.0 if float(np.dot((dst_rim - src_rim)[:2], lean[:2])) >= 0.0 else -1.0
        lip = src_rim + sign * v["inner_radius"] * lean
    lip_in_tool = tf.compose(tcp_inv, (lip, tcp[1]))[0]
    lean_in_tool = tf.rotate(tcp_inv[1], lean)
    q0 = world.joint_pos
    aim = np.array([dst_rim[0], dst_rim[1], lip[2]]) - sign * offset * lean
    for _ in range(3):                                           # the hand turns with the shoulder pan: aim again
        path, res = ik.carry_path([aim], q0, lip_in_tool)
        if not res.ok:
            return Status(False, "ik_" + res.reason, {"pos_err": res.pos_err})
        lean_end = tf.rotate(ik.fk(path[-1])[1], lean_in_tool)
        new_aim = np.array([dst_rim[0], dst_rim[1], lip[2]]) - sign * offset * lean_end
        done = float(np.linalg.norm(new_aim - aim)) < 2e-4
        aim = new_aim
        if done:
            break
    carried = _attached(world, held_objects(world))
    st = yield from _carry(world, [aim], lip_in_tool, float(world.target[-1]), lin_speed=lin_speed, carried=carried)
    if not st.ok:
        return st
    tcp = world.tcp_pose()
    st.info.update({"axis": (tf.rotate(tcp[1], tf.rotate(tcp_inv[1], axis))).tolist(), "sign": sign,
                    "pivot": (tcp[0] + tf.rotate(tcp[1], lip_in_tool)).tolist()})
    return st


def open_gripper(world: World, width: float | None = None) -> Skill:
    """Open the fingers fully, or to `width` metres between the pads. Always ok; `info["opening"]` is the result."""
    target = 0.0 if width is None else gripper_target_for_opening(width, world)
    opening = yield from _grip(world, target)
    return Status(True, "ok", {"opening": opening, "pad_force": world.pad_forces().tolist()})


def close_gripper(world: World, squeeze: float | None = None) -> Skill:
    """Close the fingers until they stop. ok when they stopped on something (`info["holding"]`), failed with
    reason `nothing_grasped` when they closed on air.

    By default the gripper keeps pushing with all it has (78 N on each pad on the 17 mm tube; 88 N at the force cap,
    `RobotSpec.grip_servo`). With `squeeze` (rad) the fingers
    close slowly until both pads touch and the target is then held that far past where they are, which limits the
    force from the first moment, since the finger servo pulls in proportion to its position error. Measured on the
    17 mm tube: 0.05 rad gives 32 N per pad, 0.03 rad 19 N, 0.02 rad 13 N, 0.01 rad 8 N, 0.005 rad 6 N."""
    opening = yield from _close(world, squeeze)
    held = holding(world)
    return Status(held, "ok" if held else "nothing_grasped", {"opening": opening, "holding": held,
                                                             "pad_force": world.pad_forces().tolist()})


def pick(world: World, obj: str, grasp: str | dict | None = None, *, approach: float = 0.10, lift: float = 0.10,
         clearance: float = 0.012, hover: float = 0.12, squeeze: float | None = None, speed: float = 1.0) -> Skill:
    """Grasp `obj` at its grip site and lift it.

    `grasp`: None (what the object's grip site says), "top", "side", or a dict {"type": "top" | "side",
    "site": "grip_0", "yaw_deg": direction the fingers close along (top grasps, world frame),
    "approach_dir": [x, y, z] or a list of such directions to choose from (side grasps; with "ordered": True the first
    that works is taken, else the cheapest), "pose": (pos, quat) of the grip site if the caller has its own estimate}.
    Steps: open to the object's width plus `clearance` on each side; move to the pre-grasp pose, `approach` back
    from the grip site along the tool axis (a side grasp first goes to a point `hover` above it and comes straight
    down); go in on a straight line; close; lift by `lift` straight up. A side grasp without `approach_dir` tries
    approaching away from the robot and from either side. Among the candidate approaches the cheapest one is taken
    whose way in is reachable and does not pass through another object or the table (checked on a scratch copy with
    the objects where `world` has them now). `squeeze` limits the grip force (see `close_gripper`).
    ok when the fingers stopped on something and still hold it after the lift. Reasons: `ik_unreachable:pregrasp`
    and `path_blocked:pregrasp` (the arm was not moved), `ik_...:<stage>`, `not_reached:<stage>`, `nothing_grasped`,
    `lost_in_lift`.
    """
    spec = {"type": grasp} if isinstance(grasp, str) else dict(grasp or {})
    site = spec.get("site", "grip_0")
    meta = world.objects[obj]["meta"].get("grips", {}).get(site, {}) if obj in world.objects else {}
    kind = spec.get("type") or meta.get("type", "top")
    width = float(spec.get("width", meta.get("width", 0.03)))
    clearance = float(spec.get("clearance", clearance))     # a grasp may ask the fingers to open less (under a plate's rim)
    if "pose" in spec:
        grip_pose = tf.as_pose(spec["pose"])
    elif "pos" in meta:                         # a grasp given in the object's frame (generated assets)
        grip_pose = tf.compose(world.locate(obj), (np.asarray(meta["pos"], dtype=np.float64), tf.unit(meta.get("quat", [1.0, 0, 0, 0]))))
    else:
        grip_pose = world.locate(f"{obj}/{site}")
    frames = _grasp_frames(kind, grip_pose, spec.get("yaw_deg"), spec.get("approach_dir"), world.scene["robot"]["pos"][:2])
    ready = _ready_list(world, kind)
    # what the fingers may touch on the way in: the object, or only the part of it the grip site sits on (the bob of
    # a pendulum rig, not its frame)
    part = obj
    if obj in world.objects and "pose" not in spec and "pos" not in meta:
        m = world.model
        body = int(m.site_bodyid[m.site(f"{obj}/{site}").id])
        if body != world.objects[obj]["body_id"]:
            part = m.body(body).name
    opening = yield from _grip(world, gripper_target_for_opening(min(width + 2 * clearance, max_opening(world)), world))
    g = float(world.target[-1])
    # Of the candidate tool orientations take the one reached with the least joint travel among those whose way in
    # is free. A side grasp starts from a point above the pre-grasp pose so that the gripper comes down behind the
    # object, not through it.
    best = None
    refused = []
    # A grasp marked `free` (on an arm whose hand cannot point down everywhere: `actions.pick`) may be far from every
    # ready posture: its configuration is also solved for outright, and it is taken only if the lift can follow: the
    # whole of `lift`, or as much of it as the arm reaches there (`LIFTS`), so that a grasp that cannot be lifted is
    # refused before anything moves. With `free == "full"` only the whole lift will do; with `free == "roomy"` it
    # must also leave the arm room to carry what it took.
    free = spec.get("free")
    seeds = [world.home, ready_posture(world, "top"), ready_posture(world, "side"), ready_posture(world, "side_low")] if free else None
    cramped = False                 # a grasp that could be lifted but leaves no room: the caller may come back to it
    for quat in frames:
        goal = (grip_pose[0].copy(), quat)
        pre = (grip_pose[0] + tf.rotate(quat, [0.0, 0.0, -approach]), quat)
        chain = [pre, goal] if kind == "top" else [(pre[0] + np.array([0.0, 0.0, hover]), quat), pre, goal]
        if seeds is not None and not _in_span(world, goal):      # the wrist would be beyond the arm's length: no need to solve
            refused.append("ik_unreachable")
            continue
        plan, why = _reach(world, chain[0], chain[1:], ready, ignore_last=(part,), seeds=seeds)
        if plan is not None and seeds is not None:
            q_end = _chain_end(world, plan["q_first"], chain)
            if q_end is None:
                plan, why = None, "ik_unreachable"
            elif world.ik.collision(q_end, depth=JAM_DEPTH) is not None:
                # the open fingers would be this deep in the thing itself (a tipped finger inside a narrow mug): they
                # would jam on the way in
                plan, why = None, "blocked_by_" + obj
            else:
                plan["lift"] = _liftable(world, q_end, chain[-1], lift, free if free in ("full", "roomy") else None)
                if plan["lift"] is None:
                    cramped = cramped or (free in ("full", "roomy") and _liftable(world, q_end, chain[-1], lift) is not None)
                    plan, why = None, "ik_unreachable"
        if plan is None:
            refused.append(why)
        elif best is None or plan["cost"] < best[0]["cost"] - 1e-9:
            best = (plan, chain)
            if spec.get("ordered"):             # the caller's order of approach directions is one of preference
                break
    if best is None:
        blocked = sorted({w for w in refused if w.startswith("blocked")})
        return Status(False, "path_blocked:pregrasp" if blocked else "ik_unreachable:pregrasp",
                      {"tried": len(frames), "refused": refused, **({"cramped": True} if cramped else {})})
    plan, chain = best
    goal = chain[-1]
    quat = goal[1]

    if plan["via"] is not None:
        st = yield from _go(world, plan["via"], g, (), speed)
        if not st.ok:
            return Status(False, f"{st.reason}:ready", st.info)
    st = yield from _go(world, plan["q_first"], g, (), speed)
    if not st.ok:
        return Status(False, f"{st.reason}:pregrasp", st.info)
    for pose in chain[1:]:
        st = yield from _move(world, pose, g, linear=True, speed=speed, lin_speed=0.10)
        if not st.ok:
            # fingers that came to rest against the object a few millimetres short of the grasp may still close on it
            if st.reason == "not_reached" and pose is chain[-1] and float(np.linalg.norm(world.tcp_pose()[0] - pose[0])) < 0.006:
                break
            if st.reason == "not_reached" and pose is chain[-1]:        # stuck against it: back out, leave it alone
                back = yield from _move(world, chain[-2], g, linear=True, speed=speed, lin_speed=0.10)
                st.info["backed_out"] = back.ok
            return Status(False, f"{st.reason}:approach", st.info)
    opening = yield from _close(world, squeeze)
    if (getattr(world, "assist", True) and world.objects.get(obj, {}).get("weld_id") is not None
            and float(np.linalg.norm(world.tcp_pose()[0] - goal[0])) < 0.03):
        world.attach(obj)                       # grasp assist: the object now moves with the hand
    if not holding(world):
        yield from _grip(world, g)
        return Status(False, "nothing_grasped", {"opening": opening})
    lift = plan.get("lift", lift)
    up = (goal[0] + np.array([0.0, 0.0, lift]), quat)
    st = yield from _move(world, up, float(world.target[-1]), linear=True, speed=speed, lin_speed=0.08)
    if not st.ok:
        return Status(False, f"{st.reason}:lift", st.info)
    if not holding(world):
        return Status(False, "lost_in_lift", {"opening": world.gripper_opening()})
    return Status(True, "ok", {"opening": world.gripper_opening(), "grasp": kind, "via_ready": plan["via"] is not None,
                               "pad_force": world.pad_forces().tolist(), "lift": lift})


LIFTS = (0.08, 0.05)        # m: what a tipped grasp is lifted by where the arm cannot lift it by all that was asked


def _in_span(world: World, pose) -> bool:
    """A quick test before solving: with the tool at `pose`, is the wrist within the arm's length of the shoulder? For
    an arm whose spec names its shoulder, elbow and wrist joints (`RobotSpec.extra["span"]`; their axes meet the
    lines between them, as on an arm with a spherical wrist); True for any other. A pose that passes may still have
    no solution (joint limits, the arm folded onto itself)."""
    names = world.spec.extra.get("span")
    if not names:
        return True
    ik = world.ik
    m, d = ik.model, ik.data
    span = getattr(world, "_span_cache", None)
    prefix = world.spec.arm_prefix if not getattr(world, "name", "") else f"{world.name}/"
    ids = [m.joint(prefix + n).id for n in names]
    if span is None:                                # the lengths, measured once in the ready posture
        tool = ik.fk(world.ready)
        a, b, c = (d.xanchor[i].copy() for i in ids)
        span = world._span_cache = (float(np.linalg.norm(b - a) + np.linalg.norm(c - b)), float(np.linalg.norm(tool[0] - c)))
    ik.fk(world.joint_pos)                          # where the shoulder is now (the base may have driven)
    shoulder = d.xanchor[ids[0]].copy()
    wrist = np.asarray(pose[0], dtype=np.float64) - span[1] * tf.rotate(pose[1], [0.0, 0.0, 1.0])
    return float(np.linalg.norm(wrist - shoulder)) <= span[0] + 0.01


ROOM = (0.30, 0.05)         # m: a grasp that leaves room can be carried this far to either side, and this much further out, once it is lifted


JAM_DEPTH = 0.003           # m: open fingers this deep in the thing they are to take would jam on it


def _chain_end(world: World, q_first, chain):
    """The configuration at the end of a way in (`chain`, entered at `q_first`), or None when a line has no solution."""
    q = np.asarray(q_first, dtype=np.float64)
    for pose in chain[1:]:
        path, res, _, _ = _plan(world, pose, q_from=q)
        if not res.ok:
            return None
        q = path[-1]
    return q


def _liftable(world: World, q, goal, lift: float, need: str | None = None) -> float | None:
    """How far a grasp can be lifted straight up from its end pose `goal` (the arm at `q`), of `lift` and then
    `LIFTS`: the first for which the straight line has a solution. With `need` (`full` or `roomy`) only the whole of
    `lift` will do; with `roomy` the hand must also be able to go from there to the places `ROOM` names (to either
    side as the robot sees the thing, a little beyond it) without tilting. None when none of the lifts will do."""
    roomy = need == "roomy"
    out = np.array([goal[0][0] - world.scene["robot"]["pos"][0], goal[0][1] - world.scene["robot"]["pos"][1], 0.0])
    out = tf.unit(out) if float(np.linalg.norm(out)) > 1e-6 else np.array([0.0, 1.0, 0.0])
    side = np.cross([0.0, 0.0, 1.0], out)
    for h in (lift,) + (() if need else tuple(v for v in LIFTS if v < lift)):
        top = goal[0] + np.array([0.0, 0.0, h])
        if not _in_span(world, (top, goal[1])):
            continue
        path, res, _, _ = _plan(world, (top, goal[1]), q_from=q)
        if not res.ok:
            continue
        if not roomy or all(world.ik.carry_path([top + s * ROOM[0] * side + ROOM[1] * out], path[-1])[1].ok for s in (1.0, -1.0)):
            return float(h)
    return None


def riders(world: World, names) -> tuple:
    """0.5.4 (lane p5person054, `d_tray_or_child`): the loose things a family declares as riding in a container
    (`world.riders = {container: (thing, ...)}`, set in `Family.setup`; no family but that one sets it) that stand in
    that container now, while it is one of `names` (held): the glasses in a carrier. Path tests carry them along with
    the hand, as they do the held thing itself; nothing else reads them (`held_objects` is unchanged)."""
    own = getattr(world, "riders", None)
    if not own:
        return ()
    out = []
    for c in names:
        if c not in own:
            continue
        lo, hi = world.box(c)
        for r in own[c]:
            if r in names or r in out or world.objects[r]["fixed"]:
                continue
            rl, rh = world.box(r)
            mx, my = (float(rl[0]) + float(rh[0])) / 2.0, (float(rl[1]) + float(rh[1])) / 2.0
            if lo[0] <= mx <= hi[0] and lo[1] <= my <= hi[1] and float(lo[2]) - 0.01 <= float(rl[2]) <= float(hi[2]):
                out.append(r)
    return tuple(out)


def _attached(world: World, names) -> tuple:
    """Where the named objects sit in the tool frame now, in the form `IK.collision(carried=...)` takes. 0.5.4: with
    them the things riding in them (`riders`)."""
    tcp_inv = tf.inverse(world.tcp_pose())
    names = tuple(names) + riders(world, names)
    return tuple((n, tf.compose(tcp_inv, world.locate(n))) for n in names if not world.objects[n]["fixed"])


def _put_down_level(world: World, obj: str, spot, approach: float, release_above: float, max_force: float,
                    retreat: float | None, speed: float):
    """Set down an upright object that is held by its side, without tilting it on the way.

    The object travels level at the height it is at (or `approach` above the spot if that is higher), on a straight
    line to above the spot, then straight down; all of it with `IK.solve_carry`, which cannot tilt the tool and does
    not care about the wrist singularity a side grasp from the left or right sits in. The whole way is tested
    beforehand with the object moving along in the hand; if it is blocked, 60 and 120 mm higher are tried. After
    letting go the gripper backs straight out along its own axis.
    """
    g = float(world.target[-1])
    ik = world.ik
    q0 = world.joint_pos
    tcp, o = world.tcp_pose(), world.locate(obj)
    offset = tf.compose(tf.inverse(tcp), o)[0]              # the object's origin in the tool frame
    here = o[0]
    goal = np.asarray(spot, dtype=np.float64) + np.array([0.0, 0.0, release_above])
    carried = _attached(world, (obj,))
    plan, why = None, "ik_unreachable"
    for extra in (0.0, 0.06, 0.12):
        z = max(float(here[2]), float(goal[2]) + approach) + extra
        pts = ([np.array([here[0], here[1], z])] if z > here[2] + 1e-4 else []) + [np.array([goal[0], goal[1], z])]
        across, res = ik.carry_path(pts, q0, offset)
        if res.ok:
            down, res = ik.carry_path([goal], across[-1], offset)
        if not res.ok:
            why = "ik_" + res.reason
            continue
        hit = ik.first_collision(list(across[3::3]) + list(down[3::3]) + [down[-1]], (), carried)
        if hit is not None:
            why = "blocked_by_" + hit[1]
            continue
        length = float(sum(np.linalg.norm(b - a) for a, b in zip([here] + pts, pts)))
        plan = (across, down, length, z)
        break
    if plan is None:
        return Status(False, ("path_blocked" if why.startswith("blocked") else "ik_unreachable") + ":preplace", {"refused": [why]})
    across, down, length, z = plan

    st = yield from _follow(world, across, g, length, lin_speed=0.12, speed=speed)
    if not st.ok:
        return Status(False, f"{st.reason}:preplace", st.info)
    yield from hold(world, 0.1)
    tare = world.wrist_wrench()[0]
    peak = [0.0]

    def blocked() -> bool:
        df = float(np.linalg.norm(world.wrist_wrench()[0] - tare))
        peak[0] = max(peak[0], df)
        return df > max_force

    drop = z - float(goal[2])
    st = yield from _follow(world, down, g, drop, lin_speed=0.05, speed=speed, guard=blocked)
    if not st.ok:
        back = yield from _carry(world, [np.array([goal[0], goal[1], z])], offset, g, lin_speed=0.05, speed=speed)
        reason = "obstructed" if st.reason == "stopped" else f"{st.reason}:descent"
        return Status(False, reason, {**st.info, "peak_force": peak[0], "returned": back.ok})
    opening = yield from _grip(world, gripper_target_for_opening(min(world.gripper_opening() + 0.030, max_opening(world)), world))
    yield from hold(world, 0.2)
    pads = world.pad_forces()
    tcp = world.tcp_pose()
    away = tcp[0] - (approach if retreat is None else retreat) * tf.rotate(tcp[1], [0.0, 0.0, 1.0])
    st = yield from _carry(world, [away], None, float(world.target[-1]), lin_speed=0.10, speed=speed)
    if float(np.max(pads)) > HOLD_MIN_FORCE:
        return Status(False, "stuck_to_gripper", {"pad_force": pads.tolist(), "opening": opening})
    if not st.ok:
        return Status(False, f"{st.reason}:retreat", st.info)
    return Status(True, "ok", {"peak_force": peak[0], "opening": opening, "level": True, "transit_height": z})


def place(world: World, obj: str, target_pose, *, approach: float = 0.10, release_above: float = 0.003,
          symmetric: bool = True, max_force: float = 12.0, retreat: float | None = None, speed: float = 1.0) -> Skill:
    """Put the held object down so that its frame coincides with `target_pose`, then let go and back off.

    `target_pose` is the pose the object's own frame should end at (for a tube: its lowest point on the floor of a
    rack hole, axis along the hole's `+z`). With `symmetric=True` only the object's axis is aligned with the target's
    `+z`; the turn about that axis is left as it is. The object is released `release_above` metres short of the
    target, coming in along the target's `-z` from `approach` away. The descent stops if the wrist force changes by
    more than `max_force` newtons (something is in the way). After letting go the gripper backs off by `retreat`
    (default `approach`): up the approach line if it held the object from above, straight back along its own axis
    if it held it by the side.
    ok when the descent completed, the fingers opened and no pad feels a force afterwards. Reasons: `not_holding`,
    `ik_unreachable:preplace` and `path_blocked:preplace` (the arm was not moved; the gripper would pass through
    something), `ik_...:<stage>`, `obstructed` (the object is still held, back at the approach pose),
    `stuck_to_gripper`.
    """
    if not holding(world):
        return Status(False, "not_holding", {})
    target = tf.as_pose(target_pose)
    t_obj = world.locate(obj)
    t_tcp = world.tcp_pose()
    tcp_in_obj = tf.compose(tf.inverse(t_obj), t_tcp)
    z_t = tf.rotate(target[1], [0.0, 0.0, 1.0])
    if symmetric:
        z_o = tf.rotate(t_obj[1], [0.0, 0.0, 1.0])
        axis = np.cross(z_o, z_t)
        s = float(np.linalg.norm(axis))
        turn = tf.quat_axis_angle(axis / s, math.atan2(s, float(np.dot(z_o, z_t)))) if s > 1e-9 else np.array([1.0, 0, 0, 0])
        goal_quat = tf.unit(tf.quat_mul(turn, t_obj[1]))
    else:
        goal_quat = target[1]
    goal = tf.compose((target[0] + release_above * z_t, goal_quat), tcp_in_obj)
    pre = (goal[0] + approach * z_t, goal[1])
    g = float(world.target[-1])

    # An upright object held by its side and to be set down upright (a beaker after pouring) is carried level: see
    # `_put_down_level`. Everything else goes the general way below.
    z_tool_now = tf.rotate(t_tcp[1], [0.0, 0.0, 1.0])
    if (symmetric and abs(float(z_tool_now[2])) < 0.5 and float(z_t[2]) > 0.9986
            and float(np.dot(tf.rotate(t_obj[1], [0.0, 0.0, 1.0]), z_t)) > 0.9986):
        return (yield from _put_down_level(world, obj, target[0], approach, release_above, max_force, retreat, speed))

    # the gripper's own way there must be free (the held object is left out: the force at the wrist watches over it)
    carried = _attached(world, (obj,))
    plan, why = _reach(world, pre, [goal], None, ignore=(obj,), carried=carried)
    if plan is None:
        return Status(False, ("path_blocked" if why.startswith("blocked") else why) + ":preplace", {"refused": [why]})
    st = yield from _go(world, plan["q_first"], g, carried, speed)
    if not st.ok:
        return Status(False, f"{st.reason}:preplace", st.info)
    yield from hold(world, 0.1)
    tare = world.wrist_wrench()[0]
    peak = [0.0]

    def blocked() -> bool:
        df = float(np.linalg.norm(world.wrist_wrench()[0] - tare))
        peak[0] = max(peak[0], df)
        return df > max_force

    st = yield from _move(world, goal, g, linear=True, speed=speed, lin_speed=0.05, guard=blocked)
    if not st.ok:
        back = yield from _move(world, pre, g, linear=True, speed=speed, lin_speed=0.05)
        reason = "obstructed" if st.reason == "stopped" else f"{st.reason}:descent"
        return Status(False, reason, {**st.info, "peak_force": peak[0], "returned": back.ok})
    width = world.gripper_opening()
    opening = yield from _grip(world, gripper_target_for_opening(min(width + 0.030, max_opening(world)), world))
    yield from hold(world, 0.2)
    pads = world.pad_forces()
    # leave the way the fingers point away from: back up the approach line when the object was held from above,
    # straight back along the tool axis when it was held by its side
    z_tool = tf.rotate(goal[1], [0.0, 0.0, 1.0])
    back = z_t if abs(float(np.dot(z_tool, z_t))) > 0.5 else -z_tool
    away = (goal[0] + (approach if retreat is None else retreat) * back, goal[1])
    st = yield from _move(world, away, float(world.target[-1]), linear=True, speed=speed, lin_speed=0.10)
    if float(np.max(pads)) > HOLD_MIN_FORCE:
        return Status(False, "stuck_to_gripper", {"pad_force": pads.tolist(), "opening": opening})
    if not st.ok:
        return Status(False, f"{st.reason}:retreat", st.info)
    return Status(True, "ok", {"peak_force": peak[0], "opening": opening})


PRESS_STANDOFF = 0.004     # m: down to this far from the surface the hand must be clear of the thing it presses, too
TIP_HALF_WIDTH = 0.016     # m: from the middle of the closed fingertips to their edge


def press(world: World, site, depth: float, *, approach=0.03, speed: float = 0.02,
          max_force: float = 30.0, min_force: float = 0.5, dwell: float = 0.2, along=None, ignore=()) -> Skill:
    """Press on a surface with the closed fingertips: go `depth` metres past the site, then back off.

    `site` is a site name (its `+z` points out of the surface) or a pose. The fingertips travel along `along`: a
    direction in the bench frame, or several in order of preference (default: straight into the surface, the site's
    `-z`). The stroke starts `approach` metres in front of the site (one distance, or several to choose from). The
    fingers are closed first. The configuration at the start of the stroke is solved for outright from the present
    and the ready postures, with the wrist turned four ways about the stroke; of the directions the first is taken,
    and of its configurations the nearest, for which the stroke is free of everything down to `PRESS_STANDOFF` from
    the surface (from there on the hand may touch the object a named site belongs to and what is named in `ignore`)
    and the free move to it is free.
    ok when the wrist felt at least `min_force` newtons and the tip got to the depth. Reasons:
    `ik_unreachable:approach`, `path_blocked:approach` (arm not moved), `ik_...:<stage>`, `no_contact` (nothing was
    felt), `force_limit` (more than `max_force` before the depth was reached; the tip stopped there and
    `info["depth_reached"]` says how far it got), `not_reached`.
    """
    target = world.locate(site) if isinstance(site, str) else tf.as_pose(site)
    if isinstance(site, str) and "/" in site:
        ignore = tuple(ignore) + (site.split("/", 1)[0],)       # the thing the site is on is what gets pressed
    if along is None:
        normals = [tf.rotate(target[1], [0.0, 0.0, 1.0])]
    else:
        normals = [-tf.unit(a) for a in np.atleast_2d(np.asarray(along, dtype=np.float64))]
    approaches = tuple(np.atleast_1d(np.asarray(approach, dtype=np.float64)).tolist())
    if world.gripper_opening() > 0.002 or world.target[-1] < GRIPPER_MAX:
        yield from _grip(world, GRIPPER_MAX)
    g = float(world.target[-1])
    q_now = world.joint_pos
    y_now = tf.rotate(world.tcp_pose()[1], [0.0, 1.0, 0.0])
    seeds = [q_now, world.ready] + _ready_list(world, "side")
    tip = TIP_BEYOND_TCP
    plan, why = None, "ik_unreachable"
    for k, n in enumerate(normals):
        y0 = y_now - np.dot(y_now, n) * n
        if float(np.linalg.norm(y0)) < 1e-6:
            y0 = np.cross(n, [1.0, 0.0, 0.0])
        y0 = tf.unit(y0)
        cands = []
        for ap in approaches:
            for turn in (0.0, 90.0, 180.0, 270.0):          # the closing axis is free about the stroke
                quat = tf.quat_from_axes(y=tf.unit(tf.rotate(tf.quat_axis_angle(n, math.radians(turn)), y0)), z=-n)
                pre = (target[0] + (ap + tip) * n, quat)
                for seed in seeds:
                    r = world.ik.solve(pre[0], pre[1], seed, max_jump=10.0)
                    if r.ok and not any(float(np.max(np.abs(r.q - c[2]))) < 0.05 for c in cands):
                        cands.append((float(np.sum(np.abs(r.q - q_now))), len(cands), r.q, pre, ap))
        cands.sort(key=lambda c: (c[0], c[1]))
        for _, _, q, pre, ap in cands[:8]:
            hit = world.ik.collision(q)
            if hit is not None:
                why = "blocked_by_" + hit[1]
                continue
            # a slanted fingertip meets the surface with its edge first: allow for that much more
            slant = math.sqrt(max(1.0 - float(np.dot(n, tf.rotate(target[1], [0.0, 0.0, 1.0]))) ** 2, 0.0))
            near = (target[0] + (PRESS_STANDOFF + TIP_HALF_WIDTH * slant + tip) * n, pre[1])
            low = (target[0] + (tip - depth) * n, pre[1])
            p1, r1, _, _ = _plan(world, near, q_from=q)
            if not r1.ok:
                continue
            p2, r2, _, _ = _plan(world, low, q_from=p1[-1])
            if not r2.ok:
                continue
            hit = world.ik.first_collision(list(p1[2::2]) + [p1[-1]]) or world.ik.first_collision(list(p2[1:]), tuple(ignore))
            if hit is None:
                kind, blocker, _ = _free_route(world, q_now, q)
                hit = None if kind is not None else blocker
            if hit is not None:
                why = "blocked_by_" + hit[1]
                continue
            plan = (q, pre, low, n, ap, k, near, PRESS_STANDOFF + TIP_HALF_WIDTH * slant)
            break
        if plan is not None:
            break
    if plan is None:
        return Status(False, ("path_blocked" if why.startswith("blocked") else "ik_unreachable") + ":approach", {"refused": [why]})
    q, pre, low, n, approach, chosen, near, lead = plan
    st = yield from _go(world, q, g)
    if not st.ok:
        return Status(False, f"{st.reason}:approach", st.info)
    yield from hold(world, 0.1)
    tare = world.wrist_wrench()[0]
    peak = [0.0]

    def too_hard() -> bool:
        df = float(np.linalg.norm(world.wrist_wrench()[0] - tare))
        peak[0] = max(peak[0], df)
        return df > max_force

    # quickly to just short of the surface, then slowly: a fingertip that meets something rigid at speed hits hard
    st = yield from _move(world, near, g, linear=True, lin_speed=2.5 * speed, guard=too_hard, settle=0.3)
    if st.ok:
        st = yield from _move(world, low, g, linear=True, lin_speed=0.4 * speed, guard=too_hard, settle=0.6)
    for _ in range(max(int(round(dwell / CONTROL_DT)), 1)):
        yield _row(world.target[:-1], g)
        too_hard()
    reached = float(np.dot(pre[0] - world.tcp_pose()[0], n)) - approach
    back = yield from _move(world, pre, g, linear=True, lin_speed=max(speed, 0.05))
    # `at_surface`: the fingertips got to where the surface is (a stroke stopped short of that met something else)
    info = {"peak_force": peak[0], "depth_reached": reached, "retreated": back.ok, "direction": chosen,
            "at_surface": bool(reached > -(lead + 0.002))}
    if st.reason.startswith("ik_"):
        return Status(False, f"{st.reason}:press", {**info, **st.info})
    if st.reason == "stopped":
        return Status(False, "force_limit", info)
    if peak[0] < min_force:
        return Status(False, "no_contact", info)
    if reached < depth - 0.0015:
        return Status(False, "not_reached", info)
    return Status(True, "ok", info)


def tilt_path(world: World, q0, tcp: tf.Pose, delta: float, axis, pivot):
    """Joint path (without the start) that turns the tool, from the pose `tcp` it has at `q0`, by `delta` radians
    about the level `axis` through `pivot`, in steps of a degree. Returns (path, IKResult, number of steps)."""
    n = max(int(math.ceil(abs(delta) / math.radians(1.0))), 1)
    poses = []
    for k in range(1, n + 1):
        turn = tf.quat_axis_angle(axis, delta * k / n)
        poses.append((pivot + tf.rotate(turn, tcp[0] - pivot), tf.unit(tf.quat_mul(turn, tcp[1]))))
    path, res = world.ik.solve_path(poses, q0)
    return path, res, n


def tilt(world: World, obj: str, angle: float, rate: float = 30.0, *, axis=None, pivot=None, check: bool = False) -> Skill:
    """Hold `obj` and turn the wrist about a horizontal axis until the object's axis is `angle` degrees from vertical.

    `angle` is absolute and signed (right-handed about `axis`): 0 is upright, so `tilt(obj, 60)` followed by
    `tilt(obj, 0)` pours and comes back. `rate` is in degrees per second. `axis` (world frame) defaults to the
    gripper's approach axis when the gripper is held sideways (a roll of the wrist, as when pouring from a vessel
    held by its side) and to the closing axis otherwise; it is made horizontal. `pivot` is the point that stays in
    place (default: the pinch point).
    With `check` the turn is first tested for collisions (the hand and what it holds against everything else, and
    what it holds against the arm) and nothing is moved if it is not free.
    ok when the wrist completed the turn and the fingers held all the way. Reasons: `not_holding`, `ik_...`,
    `path_blocked` (`info["by"]`), `not_reached`, `lost_grip`.
    """
    if not holding(world):
        return Status(False, "not_holding", {})
    tcp = world.tcp_pose()
    if axis is None:
        z = tf.rotate(tcp[1], [0.0, 0.0, 1.0])
        axis = z if abs(z[2]) < 0.5 else tf.rotate(tcp[1], [0.0, 1.0, 0.0])
    axis = np.array(axis, dtype=np.float64)
    axis[2] = 0.0
    axis = tf.unit(axis)
    z_o = tf.rotate(world.locate(obj)[1], [0.0, 0.0, 1.0])
    up = np.array([0.0, 0.0, 1.0])
    now = math.degrees(math.atan2(float(np.dot(np.cross(up, z_o), axis)), float(np.dot(up, z_o))))
    delta = math.radians(float(angle) - now)
    pivot = tcp[0] if pivot is None else np.asarray(pivot, dtype=np.float64)
    q0 = world.joint_pos
    path, res, n = tilt_path(world, q0, tcp, delta, axis, pivot)
    if not res.ok:
        return Status(False, "ik_" + res.reason, {"from_deg": now, "solved_deg": math.degrees(delta) * path.shape[0] / n})
    if check:
        hit = _path_hit(world, [q0] + list(path[1::2]) + [path[-1]], (), _attached(world, held_objects(world)), arm_vs_load=True,
                        clearance=PATH_CLEARANCE)
        if hit is not None:
            return Status(False, "path_blocked", {"by": hit[1], "who": hit[0], "from_deg": now})
    g = float(world.target[-1])
    duration = abs(math.degrees(delta)) / max(float(rate), 1e-3) / 0.75
    pos, vel = path_move(np.vstack([q0[None, :], path]), world.limits, CONTROL_DT, duration)
    lost = [False]

    def dropped() -> bool:
        lost[0] = lost[0] or not holding(world)
        return False

    yield from _track(world, pos, vel, g, dropped)
    ok, err = yield from _settle(world, path[-1], g)
    turned = math.degrees(float(np.linalg.norm(tf.rotvec(tcp[1], world.tcp_pose()[1]))))
    # `joint_path`: the way the joints went (start included), so that a caller can take the same way back
    info = {"from_deg": now, "turned_deg": turned, "joint_err": err, "joint_path": np.vstack([q0[None, :], path]), "rad": abs(delta)}
    if lost[0] or not holding(world):
        return Status(False, "lost_grip", info)
    if not ok:
        return Status(False, "not_reached", info)
    return Status(True, "ok", info)


# ---- skills for the measurement rigs ------------------------------------------------------------------------------
def release(world: World, *, relax: bool = True, width: float | None = None, rate: float = 4.0) -> Skill:
    """Let go of what the fingers hold, disturbing it as little as the gripper can.

    With `relax` the grip is first eased to its weakest hold (about 12 N per pad instead of 41) and the hand waits
    0.2 s: an object resting on something settles onto it while the fingers still guide it, and the arm, which gave
    a little under the load, comes back before the object is free. Then the fingers open at `rate` rad/s to `width`
    metres between the pads (default: 24 mm more than now, which clears the object without a long stroke).
    For something that must start moving at a sharp instant (a pendulum bob held aside, a block on a slope) use
    `relax=False`.
    ok when no pad feels a force afterwards. `info["released_at"]` is the time of the first control row after which
    both pads were free. Reason: `stuck_to_gripper`.
    """
    q = world.target[:-1].copy()
    g = float(world.target[-1])
    start_opening = world.gripper_opening()
    assisted = world.detach() is not None
    if relax and not assisted and holding(world):
        weak = min(world.gripper_pos + 0.004, g)
        while g - weak > 1e-12:
            g = max(weak, g - 1.0 * CONTROL_DT)
            yield _row(q, g)
        for _ in range(10):
            yield _row(q, g)
    target = gripper_target_for_opening(min((start_opening + 0.024) if width is None else float(width), max_opening(world)), world)
    released_at = None
    still = 0
    for _ in range(int(round(1.5 / CONTROL_DT))):
        g = max(target, g - rate * CONTROL_DT)
        yield _row(q, g)
        if released_at is None and float(np.max(world.pad_forces())) <= 0.0:
            released_at = world.time
        still = still + 1 if (g <= target and abs(world.gripper_vel) < 0.02) else 0
        if still >= 5:
            break
    pads = world.pad_forces()
    info = {"released_at": released_at, "opening": world.gripper_opening(), "pad_force": pads.tolist()}
    if float(np.max(pads)) > HOLD_MIN_FORCE or released_at is None:
        return Status(False, "stuck_to_gripper", info)
    return Status(True, "ok", info)


def set_on(world: World, obj: str, target, *, approach: float = 0.06, speed: float = 0.010, max_sink: float = 0.12,
           symmetric: bool = True, retreat: float = 0.08) -> Skill:
    """Set the held object down on a support that may give way under it (the pan of a spring balance), and let go.

    `target` is a site name or a pose: where the object's frame is to come to rest, `+z` out of the support. The
    object is brought `approach` above it, lowered quickly to 8 mm above, and then at `speed` m/s for as long as the
    gripper still carries its weight: the wrist force says how much hangs on the fingers (`World.carried_load`), and
    the descent goes on, the support sinking with it, until the support carries all it can (all of the weight on a
    level support; on a slope, the part square to it). Only then are the fingers opened (`release`), so the load is
    handed over without a drop and without a push. At most `max_sink` metres below the target.
    With `symmetric` only the object's axis is aligned with the target's `+z` (as in `place`); otherwise the full
    orientation is matched (a block on a ramp).
    ok when the support took the load and no pad feels a force afterwards. `info`: `weight_n` (as felt before
    touching down), `sink` (how far past the target it went), `released_at`. Reasons: `not_holding`,
    `ik_unreachable:approach`, `path_blocked:approach` (arm not moved), `obstructed` (met something hard on the
    quick part of the way down; still held), `no_support` (nothing took the load within `max_sink`; still held, back
    above the target), `stuck_to_gripper`, `ik_...:<stage>`.
    """
    if not holding(world):
        return Status(False, "not_holding", {})
    tgt = world.locate(target) if isinstance(target, str) else tf.as_pose(target)
    n = tf.rotate(tgt[1], [0.0, 0.0, 1.0])
    t_obj, t_tcp = world.locate(obj), world.tcp_pose()
    tcp_in_obj = tf.compose(tf.inverse(t_obj), t_tcp)
    if symmetric:
        z_o = tf.rotate(t_obj[1], [0.0, 0.0, 1.0])
        axis = np.cross(z_o, n)
        s = float(np.linalg.norm(axis))
        turn = tf.quat_axis_angle(axis / s, math.atan2(s, float(np.dot(z_o, n)))) if s > 1e-9 else np.array([1.0, 0, 0, 0])
        goal_quat = tf.unit(tf.quat_mul(turn, t_obj[1]))
    else:
        goal_quat = tgt[1]

    def tcp_at(above: float) -> tf.Pose:
        return tf.compose((tgt[0] + above * n, goal_quat), tcp_in_obj)

    g = float(world.target[-1])
    near = 0.008
    carried = _attached(world, (obj,))
    plan, why = _reach(world, tcp_at(approach), [tcp_at(near)], None, ignore=(obj,), carried=carried)
    if plan is None:
        return Status(False, ("path_blocked" if why.startswith("blocked") else why) + ":approach", {"refused": [why]})
    st = yield from _go(world, plan["q_first"], g, carried)
    if not st.ok:
        return Status(False, f"{st.reason}:approach", st.info)
    yield from hold(world, 0.3)
    weight = world.carried_load()
    rest = weight * (1.0 - float(n[2]) ** 2)             # what a frictionless slope leaves hanging on the fingers

    def hard_contact() -> bool:
        return world.carried_load() < weight - max(0.5 * weight, 0.5)

    st = yield from _move(world, tcp_at(near), g, linear=True, lin_speed=0.05, guard=hard_contact, settle=0.5)
    if not st.ok:
        if st.reason == "stopped":
            return Status(False, "obstructed", {**st.info, "weight_n": weight})
        return Status(False, f"{st.reason}:descent", st.info)
    # While the hand moves, the wrist reads a few hundredths of a newton more than at rest, so the hand-over is judged
    # by how far the reading has dropped from its highest value on the way down, not by its absolute value. The
    # reading is smoothed over three rows; the stop then comes about one row late, and that much of the drop is
    # anticipated from the slope seen so far (the stiffness of the support times the speed of the hand).
    recent: list[float] = []
    smooth: list[float] = []
    need = (weight - rest) - max(0.005 * weight, 0.003)

    def carried() -> bool:
        recent.append(world.carried_load())
        if len(recent) < 3:
            return False
        smooth.append(sum(recent[-3:]) / 3.0)
        drop = max(smooth) - smooth[-1]
        per_row = max(smooth[-2] - smooth[-1], 0.0) if len(smooth) >= 2 else 0.0
        return drop + per_row >= need

    st = yield from _move(world, tcp_at(-max_sink), g, linear=True, lin_speed=speed, guard=carried, settle=0.3)
    if st.ok or st.reason != "stopped":
        back = yield from _move(world, tcp_at(approach), g, linear=True, lin_speed=0.05)
        reason = "no_support" if st.ok or st.reason == "not_reached" else f"{st.reason}:sink"
        return Status(False, reason, {**st.info, "weight_n": weight, "returned": back.ok})
    sink = float(np.dot(tcp_at(0.0)[0] - world.tcp_pose()[0], n))
    rel = yield from release(world, relax=float(n[2]) > 0.996)
    tcp = world.tcp_pose()
    away = (tcp[0] + retreat * n, tcp[1])
    st = yield from _move(world, away, float(world.target[-1]), linear=True, lin_speed=0.10)
    info = {"weight_n": weight, "sink": sink, "released_at": rel.info.get("released_at"), "opening": rel.info.get("opening")}
    if not rel.ok:
        return Status(False, rel.reason, info)
    if not st.ok:
        return Status(False, f"{st.reason}:retreat", {**info, **st.info})
    return Status(True, "ok", info)
