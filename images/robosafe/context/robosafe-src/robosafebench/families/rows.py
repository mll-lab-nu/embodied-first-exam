"""Scripted motion by low-level rows (`ee_pose`, `joint_position`, one 0.02 s step each): what the two-hand families'
row references and `robosafebench.sim.measure_two_hands` share.

A script here emits rows through the control interface (`Episode.act`, `robosafebench/episode/control.py`; the episode's
instance has `interface == "control"`): one row is one control step of both arms (left first on two arms), and an arm
that is not moving gets the command in force. It reads where things are from the episode's ground truth, as the
skill references read the driver's private copy. Nothing plans a way or tests one for collisions while it moves: poses are chosen beforehand, by IK with
the arm's own collision test, where a script says so. The gripper is a command between 0 (open) and 1 (closed).
"""
from __future__ import annotations

import math

import numpy as np

from robosafebench.sim import skills as S
from robosafebench.sim import tf
from robosafebench.sim.world import CONTROL_DT

UP = np.array([0.0, 0.0, 1.0])
LIN = 0.12                  # m/s: straight moves of the pinch point
ANG = 0.9                   # rad/s: turns of the hand
JOINT = 0.8                 # rad/s: the fastest joint on a joint move


class RowError(RuntimeError):
    pass


class Rows:
    """Emits rows for the arms of one episode. `cmd[arm]` is what the arm was last told (pose, gripper)."""

    def __init__(self, ep):
        self.ep = ep
        self.world = ep.world
        self.two = bool(ep.world.arm_names)
        self.cmd: dict = {}
        self.ik_misses = 0

    # ---- arms and names -------------------------------------------------------------------------------------------
    def arm(self, name: str | None):
        return self.world.arm(name) if self.two else self.world

    def _index(self, name) -> int:
        return list(self.world.arm_names).index(name) if self.two else 0

    def emit(self, name, how: str, part) -> dict:
        """One control step: the row of type `how` in force, with this arm's part replaced by `part`."""
        row = np.array(self.ep.command(how), dtype=np.float64)
        width = 8 if how == "ee_pose" else None
        i = self._index(name)
        if width is None:
            sizes = [self.arm(n).spec.n + 1 for n in (self.world.arm_names or (None,))]
        else:
            sizes = [width] * max(len(self.world.arm_names), 1)
        k = sum(sizes[:i])
        part = np.asarray(part, dtype=np.float64)
        if how == "ee_pose" and float(np.dot(part[3:7], row[k + 3:k + 7])) < 0.0:      # keep consecutive rows continuous
            part = part.copy()
            part[3:7] *= -1.0
        row[k:k + sizes[i]] = part
        out = self.ep.act(how, row)
        if not out.get("ok"):
            raise RowError(f"{how} refused: {out.get('error')}")
        return out.get("result") or {}

    def _grip_now(self, name) -> float:
        a = self.arm(name)
        return float(self.cmd.get(name, {}).get("grip", float(a.target[-1]) / float(a.spec.gripper_max)))

    # ---- moves ----------------------------------------------------------------------------------------------------
    def joints(self, name, q, grip: float | None = None, speed: float = JOINT, settle: float = 0.3) -> None:
        """A straight line in joint space to `q`, as `joint_position` rows."""
        a = self.arm(name)
        g = self._grip_now(name) if grip is None else float(grip)
        q0 = np.asarray(a.target[:-1], dtype=np.float64)
        q = np.asarray(q, dtype=np.float64)
        n = max(int(math.ceil(float(np.max(np.abs(q - q0))) / (speed * CONTROL_DT))), 1)
        for k in range(1, n + 1):
            self.emit(name, "joint_position", list(q0 + (q - q0) * k / n) + [g])
        for _ in range(int(round(settle / CONTROL_DT))):
            self.emit(name, "joint_position", list(q) + [g])
        p, quat = a.ik.fk(q)
        self.cmd[name] = {"pos": np.asarray(p), "quat": np.asarray(quat), "grip": g}

    def pose(self, name, pos, quat=None, grip: float | None = None, lin: float = LIN, ang: float = ANG, settle: float = 0.2) -> int:
        """The pinch point on a straight line to `pos` while the hand turns to `quat`, as `ee_pose` rows. Returns the
        number of steps whose pose had no IK solution near the last (the arm kept its targets there)."""
        a = self.arm(name)
        if name not in self.cmd:
            p, q = a.tcp_pose()
            self.cmd[name] = {"pos": np.asarray(p), "quat": np.asarray(q), "grip": self._grip_now(name)}
        c = self.cmd[name]
        pos = np.asarray(pos, dtype=np.float64)
        quat = c["quat"] if quat is None else tf.unit(np.asarray(quat, dtype=np.float64))
        g = c["grip"] if grip is None else float(grip)
        dist = float(np.linalg.norm(pos - c["pos"]))
        turn = float(np.linalg.norm(tf.rotvec(c["quat"], quat)))
        n = max(int(math.ceil(max(dist / lin, turn / ang) / CONTROL_DT)), 1)
        misses = 0
        for k in range(1, n + 1):
            f = k / n
            p = c["pos"] + (pos - c["pos"]) * f
            q = tf.slerp(c["quat"], quat, f)
            out = self.emit(name, "ee_pose", list(p) + list(q) + [g])
            misses += 1 if out.get("ik") else 0
        for _ in range(int(round(settle / CONTROL_DT))):
            self.emit(name, "ee_pose", list(pos) + list(quat) + [g])
        self.cmd[name] = {"pos": pos, "quat": quat, "grip": g}
        self.ik_misses += misses
        return misses

    def grip(self, name, value: float, seconds: float = 0.8) -> None:
        """Ramp the gripper command to `value` (0 open .. 1 closed) and wait, the arm keeping its targets."""
        a = self.arm(name)
        q = np.asarray(a.target[:-1], dtype=np.float64)
        g0 = self._grip_now(name)
        n = max(int(round(seconds / CONTROL_DT)), 1)
        ramp = max(int(round(0.4 / CONTROL_DT)), 1)
        for k in range(1, n + 1):
            g = g0 + (float(value) - g0) * min(k / ramp, 1.0)
            self.emit(name, "joint_position", list(q) + [g])
        if name in self.cmd:
            self.cmd[name]["grip"] = float(value)
        else:
            p, qq = a.tcp_pose()
            self.cmd[name] = {"pos": np.asarray(p), "quat": np.asarray(qq), "grip": float(value)}

    def opening(self, name, width: float) -> float:
        """The gripper command (0 .. 1) that leaves `width` metres between the pads."""
        a = self.arm(name)
        return float(S.gripper_target_for_opening(min(width, S.max_opening(a)), a)) / float(a.spec.gripper_max)

    def wait(self, seconds: float) -> None:
        for _ in range(max(int(round(seconds / CONTROL_DT)), 1)):
            typ, row = self.ep.hold()
            self.ep.act(typ, row)

    def holds(self, name, obj: str) -> bool:
        """The hand of `name` holds `obj`: welded by the grasp assist, or both finger pads on it."""
        from robosafebench.hazard.state import fingers_on
        a = self.arm(name)
        return a.held == obj or obj in fingers_on(a)

    # ---- poses worked out beforehand --------------------------------------------------------------------------------
    def solve(self, name, pos, quat, seeds=(), ignore=()) -> np.ndarray | None:
        """A configuration of the arm at the pose, free of collisions (but with `ignore`), from the arm's targets or
        one of `seeds`."""
        a = self.arm(name)
        for seed in [np.asarray(a.target[:-1], dtype=np.float64), a.ready, a.home] + [np.asarray(s, dtype=np.float64) for s in seeds]:
            for jitter in (0.0, 0.6, -0.6):
                s = np.array(seed, dtype=np.float64)
                s[0] += jitter
                r = a.ik.solve(np.asarray(pos, dtype=np.float64), tf.unit(quat), s, max_jump=10.0, max_iters=200)
                if r.ok and a.ik.collision(r.q, ignore) is None:
                    return r.q
        return None


def down(yaw_deg: float) -> np.ndarray:
    """The hand straight down, fingers closing along (-sin yaw, cos yaw, 0)."""
    return tf.quat_from_ypr(float(yaw_deg), 0.0, 0.0)


def side_quat(point, base_xy, tilt_deg: float, lean_deg: float = 0.0) -> np.ndarray:
    """A hand tipped `tilt_deg` from straight down that points into `point` from the side of `base_xy` (turned by
    `lean_deg` about the vertical), its fingers closing level and across."""
    a = math.atan2(float(base_xy[1] - point[1]), float(base_xy[0] - point[0])) + math.radians(lean_deg)
    towards = np.array([math.cos(a), math.sin(a), 0.0])
    t = math.radians(tilt_deg)
    z = -math.cos(t) * UP - math.sin(t) * towards
    return tf.quat_from_axes(y=np.cross(UP, towards), z=z)


def yaw_run(R: Rows, name, pinch, ignore=(), step: int = 10) -> list[float]:
    """The longest run of neighbouring yaws (degrees) at which the hand of `name` reaches `pinch` straight down
    without touching anything but `ignore` (other things where they are now, the other arm included)."""
    ok = {yaw for yaw in range(-180, 180, step) if R.solve(name, pinch, down(yaw), ignore=ignore) is not None}
    runs, cur = [], []
    for yaw in range(-180, 540, step):
        if ((yaw + 180) % 360) - 180 in ok:
            cur.append(float(yaw))
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    runs = [r for r in runs if r[0] < 180]
    if len(ok) == 360 // step:
        return [float(v) for v in range(-180, 180, step)]
    return max(runs, key=len) if runs else []


# ---- holding a standing thing still, turning a cap, by rows -------------------------------------------------------
HOLD_TILTS = (90.0, 75.0, 60.0)
HOLD_LEANS = (0.0, 30.0, -30.0, 60.0, -60.0)


def _posed(R: Rows, name, q, fn):
    """`fn()` with the arm `name` standing at `q` for the collision tests only: the live state is put back exactly
    (positions only, nothing stepped), so the episode does not change."""
    w = R.world
    adr = R.arm(name)._arm_qadr
    saved = w.data.qpos[adr].copy()
    try:
        w.data.qpos[adr] = q
        return fn()
    finally:
        w.data.qpos[adr] = saved
        w._scratch_tick = -1


def hold_candidates(R: Rows, name, obj: str, point, back: float = 0.08) -> list[dict]:
    """The level or tipped poses from which the hand of `name` can take a standing thing by its side at `point`: a
    way in along the hand's axis from `back`, and a free move to above that way in."""
    a = R.arm(name)
    base = np.asarray(a.scene["robot"]["pos"][:2], dtype=np.float64)
    point = np.asarray(point, dtype=np.float64)
    out = []
    for tilt in HOLD_TILTS:
        for lean in HOLD_LEANS:
            quat = side_quat(point, base, tilt, lean)
            z = tf.rotate(quat, [0.0, 0.0, 1.0])
            pre = point - back * z
            high = pre + np.array([0.0, 0.0, 0.10])        # above the way in: the free move does not sweep the thing
            q_high = R.solve(name, high, quat)
            q_pre = R.solve(name, pre, quat, seeds=[q_high] if q_high is not None else (), ignore=(obj,))
            q_at = R.solve(name, point, quat, seeds=[q_pre] if q_pre is not None else (), ignore=(obj,))
            if q_high is None or q_pre is None or q_at is None:
                continue
            out.append({"tilt": tilt, "lean": lean, "quat": quat, "pre": pre, "high": high, "q_high": q_high, "q_at": q_at, "point": point})
    return out


def hold_for_twist(R: Rows, holder, twister, obj: str, cap: str, point, width: float, heights=(0.0, 0.01, 0.02, 0.035)) -> dict:
    """Of the holding poses (at `point` and at `heights` above it on the body), the one that leaves the turning hand
    the longest run of yaws over the cap; then hold."""
    lo, hi = (np.asarray(v) for v in R.world.box(cap))
    pinch = (lo + hi) / 2.0
    pinch[2] = max(float(pinch[2]), float(hi[2]) - 0.010)
    best = None
    for dz in heights:
        for c in hold_candidates(R, holder, obj, np.asarray(point, dtype=np.float64) + np.array([0.0, 0.0, dz])):
            run = _posed(R, holder, c["q_at"], lambda: yaw_run(R, twister, pinch, ignore=(cap, obj), step=20))
            if best is None or len(run) > best[0]:
                best = (len(run), c)
        if best is not None and best[0] >= 12:
            break
    if best is None:
        raise RowError(f"no free pose for {holder} to hold {obj!r} by its side")
    out = hold_by_side(R, holder, obj, point, width, only=best[1])
    out["twist_yaws"] = (best[0] - 1) * 20
    return out


def hold_by_side(R: Rows, name, obj: str, point, width: float, back: float = 0.08, only: dict | None = None) -> dict:
    """Take a standing thing by its side at `point` (on its axis) with a level or tipped hand from the arm's own side,
    and close on it; it stays where it stands. Raises RowError where no such pose is free. `only`: one candidate of
    `hold_candidates`."""
    for c in ([only] if only else hold_candidates(R, name, obj, point, back)):
        if True:
            tilt, lean, quat, pre, q_high = c["tilt"], c["lean"], c["quat"], c["pre"], c["q_high"]
            point = c["point"]
            open_ = R.opening(name, width + 0.024)
            R.grip(name, open_, 0.5)
            R.joints(name, q_high, open_)
            R.pose(name, pre, quat, open_, lin=0.10)
            R.pose(name, point, quat, open_, lin=0.08)
            R.grip(name, 1.0, 1.0)
            return {"tilt": tilt, "lean": lean, "held": R.holds(name, obj)}
    raise RowError(f"no free pose for {name} to hold {obj!r} by its side")


def hold_by_handle(R: Rows, name, obj: str, back: float = 0.06) -> dict:
    """Take a thing by its handle from straight above (the asset's grasp called `handle`) and close on it; the thing
    stays where it stands (a saucepan held still by its long handle). Raises RowError where the hand cannot."""
    from robosafebench.sim import actions as A
    g = next((g for g in A.grasps_of(R.world, obj) if g["name"] == "handle" and g["type"] == "top"), None)
    if g is None:
        raise RowError(f"{obj!r} has no handle to take from above")
    pos = np.asarray(g["pose"][0], dtype=np.float64)
    closing = tf.rotate(g["pose"][1], [0.0, 1.0, 0.0])
    yaw = math.degrees(math.atan2(-float(closing[0]), float(closing[1])))
    for y in (yaw, yaw + 180.0):
        quat = down(y)
        q_pre = R.solve(name, pos + np.array([0.0, 0.0, back]), quat, ignore=(obj,))
        if q_pre is None or R.solve(name, pos, quat, seeds=[q_pre], ignore=(obj,)) is None:
            continue
        open_ = R.opening(name, float(g["width"]) + 0.024)
        R.grip(name, open_, 0.4)
        R.joints(name, q_pre, open_)
        R.pose(name, pos, quat, open_, lin=0.06)
        R.grip(name, 1.0, 1.0)
        return {"yaw": round(y, 1), "held": R.holds(name, obj)}
    raise RowError(f"no free pose for {name} to take the handle of {obj!r}")


def twist_off(R: Rows, name, cap: str, done, stroke_max: float = 200.0, strokes: int = 8, step: float = 30.0, ignore=()) -> dict:
    """Take hold of a cap from straight above and turn it anticlockwise (seen from above) in strokes, letting go and
    turning back between them, until `done()`; then lift it 6 cm. Returns {"strokes", "turned_deg", "off", ...}."""
    w = R.world
    lo, hi = (np.asarray(v) for v in w.box(cap))
    pinch = (lo + hi) / 2.0
    pinch[2] = max(float(pinch[2]), float(hi[2]) - 0.010)
    width = float(min(hi[0] - lo[0], hi[1] - lo[1]))
    run = yaw_run(R, name, pinch, ignore=(cap,) + tuple(ignore))
    if len(run) < 7:
        raise RowError(f"the hand of {name} cannot turn far enough over the cap ({len(run)} yaws)")
    stroke = min(run[-1] - run[0], stroke_max)
    start = run[0]
    open_ = R.opening(name, width + 0.024)
    for above in (0.08, 0.06, 0.04, 0.025):              # a hand pointing down is not held high far from its base
        q_pre = R.solve(name, pinch + np.array([0.0, 0.0, above]), down(start), ignore=(cap,) + tuple(ignore))
        if q_pre is not None:
            break
    if q_pre is None:
        raise RowError("no free pose above the cap")
    R.grip(name, open_, 0.4)
    R.joints(name, q_pre, open_)
    R.pose(name, pinch, down(start), open_, lin=0.06)
    turned, k = 0.0, 0
    for k in range(1, strokes + 1):
        R.grip(name, 1.0, 0.8)
        yaw, left = start, stroke
        while left > 1e-6 and not done():
            d = min(step, left)
            R.pose(name, pinch, down(yaw + d), lin=0.05, ang=0.8, settle=0.05)
            yaw += d
            left -= d
            turned += d
        R.wait(0.1)
        if done():
            break
        R.grip(name, open_, 0.5)
        while abs(yaw - start) > 1e-6:                      # back the way it came (a turn of more than half a turn
            yaw -= math.copysign(min(step, abs(yaw - start)), yaw - start)      # would otherwise be taken the short way)
            R.pose(name, pinch, down(yaw), open_, lin=0.05, ang=1.2, settle=0.0)
    out = {"strokes": k, "turned_deg": turned, "stroke_deg": stroke, "off": bool(done())}
    if out["off"]:
        R.pose(name, pinch + np.array([0.0, 0.0, 0.06]), lin=0.05)
    out["in_hand"] = R.holds(name, cap)
    return out
