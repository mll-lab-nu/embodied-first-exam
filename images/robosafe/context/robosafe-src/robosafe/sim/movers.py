"""Scripted movers (added in 0.5.1): table-scale things that start moving while the robot works.

A mover drives one scene object, or a chain of them, along a deterministic, seeded script: a path, a speed profile
along it, and a start that keys off what the robot actually does. The script is plain data, a function of the tick
alone once it has started, so a record replays to the same state hashes; the start is a trigger of the episode
(`Episode.on_tick`, looked at after every control tick) whose condition reads the physical state (`robosafe.episode
.when`: `tcp_progress`, `hand_travelled`, `lifted`; `sim_time` as a second option), never the number of calls or wall
time. Time passes only while a call of the agent runs (a skill, or a chunk of rows under the control interface), so a
mover moves only then, as everything else does, and stands still between calls.

Kinds (`Mover.kind`):

- `mocap`: a scripted body (`"mocap": true` in the scene: a figure, a cat). Legs `{"to": [x, y, z], "s": seconds}`
  (or `"speed"` m/s) with a speed profile `"ease"` (`smooth`, `linear`, `in`, `out`), or `"jump": true`: a ballistic
  flight, level motion uniform in time and height under gravity, from where the body is to `to` in `s` seconds (the
  apex follows from the two heights and the time). `"yaw_deg"` turns the body to that heading over the leg (else, with
  `front_deg`, it turns to face the way it goes, as `Episode.walk` does). `{"wait": seconds}` stands still. Nothing
  pushes a scripted body back; the script keeps it out of the furniture (`clearance`).
- `joint`: a slide or hinge of an object, set each tick (position and velocity) along legs `{"to": value, "s"}`; with
  `actuator`, the servo's target goes along (a door on a servo then stays where the path leaves it). `"wrap": period`
  makes an endless belt: the value written is `from + ((value - from) mod period)` and the velocity written is that of
  the unwrapped way, so the belt never jerks back; the leg leaves the joint at the wrapped value. A wrapped part jumps
  back by one period in one tick, so its collision surface must be flat and uniform along its length and its cleats
  drawn only (`contype`/`conaffinity` 0): a colliding cleat would jump into whatever rests on the belt.
  `joint` may be a list of joints (and `actuator` a list of the same length, None where a joint has no servo): the
  legs then go to vectors (a scripted arm on its own servos). `mover.go(ep, [], label)` stops a joint mover and holds it where it is (velocity 0, set each tick, as a brake) until
  it is sent along another path; a `{"wait": s}` leg holds it for that long.
- Any kind but `launch`: `Mover.pause_when(ep) -> bool` (a family's rule, read before each step): while true the mover
  stands where it is and its path waits (`paused_ticks`); a scripted arm stops short of a robot in its way.
- `launch`: a free object given a velocity once (`{"v": [vx, vy, vz], "w": [wx, wy, wz]}`, both in the bench frame:
  `World.push`); physics does the rest.
- `chain`: several scripted bodies posed together from a joint vector by the family's `fk(q) -> {object: (pos,
  quat)}` (a scripted arm whose links are scripted bodies); legs `{"to": [q...], "s"}`.

What the episode records about each mover (`Mover.summary`; the record's `movers`, the verdict's
`diagnostics.movers`): the onset (tick and time of its first start), every scripted path it was sent along (when, the
legs as numbers), when it got there, whether the robot or a thing in its hand touched it (first tick, total time, by
which part: read after every physics step, like the contact log), and the least gap between the robot (and what it
holds) and the mover from the onset on (read once per control tick, on the shapes that collide).

Reactive movers (0.5.1, B2; lane movers-b). An instance carries the condition `movers`: `scripted` (the default) or
`reactive` (`Instance.movers`, in its key only when reactive; `Episode.reactive`). A family declares how a mover answers
the robot with `Mover.react_to(Reaction(...))`: `freeze` (it pauses on its path when the robot comes within a distance,
then goes on), `back_off` (it steps away from the robot's hand), `drawn_to` (it goes towards a thing while a condition
holds, stopping short of it). The numbers are the family's, drawn from its seed. Under `scripted` reactions are never
looked at: the episode, its hash and its record are what they were. Under `reactive` the episode calls `Mover.react`
once per control tick, after the physics and the gap; a reaction that is due sends the mover along a new path with
`go` (label `react:<label>`), so it shows in the record's paths and replays like any other; the ticks it fired at are
in the state hash and in the summary's `reactions`.

Hooks for other modules (the proximity lane): `Episode.movers` lists the movers; `Mover.onset_tick`, `Mover.objects`,
`Mover.summary()`; `Mover.listeners` are called as `f(mover, episode)` when the mover first starts. Nothing here
writes to the hazard state or decides an outcome.
"""
from __future__ import annotations

import math

import mujoco
import numpy as np

from . import tf
from .world import CONTROL_DT

GRAVITY = 9.81
KINDS = ("mocap", "joint", "launch", "chain")
EASES = ("smooth", "linear", "in", "out")
TURN_TICKS = 15             # control ticks over which a body turns to face a new leg (as `Episode.walk`)
GAP_RANGE = 2.0             # m: gaps beyond this are not measured (reported as None)
STILL_MPS = 0.05            # m/s: a robot whose pinch point moves slower than this when a moving mover touches it was struck
                            # (provisional: lane L1's `struck_by` attribution in hazard/contact.py replaces this rule)


def ease(kind: str, s: float) -> float:
    """Fraction of a leg's way covered at the fraction `s` of its time."""
    if kind == "linear":
        return s
    if kind == "in":
        return s * s
    if kind == "out":
        return 1.0 - (1.0 - s) * (1.0 - s)
    return s * s * (3.0 - 2.0 * s)      # smooth: starts and stops at rest


def _ticks(seconds: float) -> int:
    return max(int(round(float(seconds) / CONTROL_DT)), 1)


def jump_apex(p0, p1, seconds: float, g: float = GRAVITY) -> float:
    """Highest point of a ballistic flight from p0 to p1 taking `seconds` (bench frame z)."""
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    T = float(seconds)
    vz = (p1[2] - p0[2]) / T + g * T / 2.0
    t = min(max(vz / g, 0.0), T)
    return float(p0[2] + vz * t - g * t * t / 2.0)


def flight(p0, p1, seconds: float, tau: float, g: float = GRAVITY) -> np.ndarray:
    """Where a ballistic flight from p0 to p1 in `seconds` is at time `tau` after take-off."""
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    T = float(seconds)
    s = tau / T
    vz = (p1[2] - p0[2]) / T + g * T / 2.0
    return np.array([p0[0] + (p1[0] - p0[0]) * s, p0[1] + (p1[1] - p0[1]) * s, p0[2] + vz * tau - g * tau * tau / 2.0])


class Mover:
    """One scripted mover. Make it in `Family.setup`, register it with `Episode.add_mover`, and start it from a
    trigger of every tick: `ep.on_tick(name, when.lifted("pot", 0.03), lambda e: mover.go(e, path, "jump"))`, or
    `mover.when(ep, condition, path, label, mark="onset")`, which does that and sets the episode's mark."""

    def __init__(self, name: str, obj, *, kind: str = "mocap", joint: str | None = None, front_deg: float | None = None,
                 fk=None, q0=None, actuator: str | None = None):
        if kind not in KINDS:
            raise ValueError(f"mover kind is one of {KINDS}, got {kind!r}")
        self.name, self.kind = name, kind
        self.objects = list(obj) if isinstance(obj, (list, tuple)) else [obj]
        self.obj = self.objects[0]
        self.joint, self.front_deg, self.fk, self.actuator = joint, front_deg, fk, actuator
        if kind == "joint" and not joint:
            raise ValueError("a `joint` mover names the object's joint")
        if kind == "chain":
            if fk is None or q0 is None:
                raise ValueError("a `chain` mover has `fk(q)` and the starting joint vector `q0`")
            self.q = np.asarray(q0, dtype=np.float64).copy()
        self.onset_tick: int | None = None
        self.onset_t: float | None = None
        self.paths: list[dict] = []         # every path it was sent along: {"label", "tick", "legs", "done"}
        self.legs: list[dict] = []          # the path running now (compiled), and where it is on it
        self.leg = self.k = 0
        self.hold: float | None = None      # a joint mover stopped by an empty path: held there
        # `pause_when(ep) -> bool`, looked at before every step of a path: while true the mover stands where it is and
        # its path waits (a family's stop-short rule; a function of the state, so a replay pauses alike)
        self.pause_when = None
        self.paused_ticks = 0
        self.gap: float | None = None       # the gap to the robot as of the last tick (from the onset)
        self.listeners: list = []           # f(mover, episode) when the mover first starts (the proximity lane's hook)
        self.reactions: list = []           # `Reaction`s: looked at only under the condition `movers="reactive"` (0.5.1, B2)
        self.reactive = False               # set by `Episode.add_mover` from the instance's condition
        self._ep = None
        # contact and gap, from the onset on
        self.touches: list[dict] = []       # {"by", "tick0", "tick1", "s"}
        self._touch_open: dict[str, dict] = {}
        self.min_gap: float | None = None
        self.min_gap_tick: int | None = None
        self.min_gap_by: str | None = None
        self.gap_at_onset: float | None = None
        self._last_tcp = None
        self._tcp_speed = 0.0

    # ---- set-up ------------------------------------------------------------------------------------------------------
    def bind(self, ep) -> None:
        """Called by `Episode.add_mover`: index the shapes of the mover and of the robot, and listen to contacts."""
        self._ep = ep
        w = ep.world
        m = w.model
        own = set(self.objects)
        self._geoms = np.array([g for g in range(m.ngeom) if w._geom_owner[g] in own and _collides(m, g)], dtype=np.int64)
        self._robot_geoms = np.array([g for g in range(m.ngeom) if w._geom_owner[g] == "robot" and _collides(m, g)], dtype=np.int64)
        self._geom_mask = np.zeros(m.ngeom, dtype=bool)
        self._geom_mask[self._geoms] = True
        self._robot_mask = np.zeros(m.ngeom, dtype=bool)
        self._robot_mask[self._robot_geoms] = True
        self._owner = list(w._geom_owner)
        self._part = _robot_parts(w)
        self._fromto = np.zeros(6)
        w._sensor_list.append(_TouchSensor(self))

    def when(self, ep, condition, path, label: str = "start", mark: str | None = "onset") -> None:
        """Start the mover along `path` the first time `condition(ep)` holds after a control tick, and set `mark`."""
        def go(e):
            if mark:
                e.mark(mark)
            self.go(e, path, label)
        ep.on_tick(f"{self.name}:{label}", condition, go)

    # ---- motion ------------------------------------------------------------------------------------------------------
    def go(self, ep, path, label: str = "start") -> None:
        """Send the mover along `path` from where it is now (replacing a path it is on). It takes its first step with
        the next control tick."""
        w = ep.world
        if self.onset_tick is None:
            self.onset_tick, self.onset_t = w.tick, round(w.time, 4)
            self.gap_at_onset = self._gap(ep)[0]
            for f in self.listeners:
                f(self, ep)
        steps = list(path) if isinstance(path, (list, tuple)) else [path]
        if self.kind == "launch":
            v = steps[0] if steps else {}
            w.push(self.obj, v.get("v", (0.0, 0.0, 0.0)), v.get("w"))
            self.legs, self.leg, self.k = [], 0, 0
            self.paths.append({"label": label, "tick": w.tick, "legs": [{"v": [float(x) for x in v.get("v", (0, 0, 0))],
                                                                         "w": None if v.get("w") is None else [float(x) for x in v["w"]]}],
                               "done": w.tick})
            ep.state.event("script", mover=self.name, path=label)
            return
        self.legs = self._compile(ep, steps)
        self.leg, self.k = 0, 0
        self.hold = None
        if self.kind == "joint" and not self.legs:     # stopped: held where it is, at rest (a braked belt), until sent again
            self.hold = self._here(ep)[0]
            self._write(w, self.hold, 0.0)
        self.paths.append({"label": label, "tick": w.tick, "legs": [_plain_leg(x) for x in self.legs], "done": None if self.legs else w.tick})
        ep.state.event("script", mover=self.name, path=label)

    @property
    def moving(self) -> bool:
        return bool(self.legs) and self.leg < len(self.legs)

    @property
    def started(self) -> bool:
        return self.onset_tick is not None

    def _here(self, ep):
        w = ep.world
        if self.kind == "mocap":
            p, q = w.mocap_pose(self.obj)
            return p, q
        if self.kind == "joint":
            if isinstance(self.joint, (list, tuple)):
                return np.array([float(w.data.qpos[self._qadr(w, j)]) for j in self.joint]), None
            return float(w.data.qpos[self._qadr(w, self.joint)]), None
        return self.q.copy(), None

    def _qadr(self, w, joint) -> int:
        return int(w.model.joint(f"{self.obj}/{joint}").qposadr[0])

    def _write(self, w, value, vel) -> None:
        """Set the joint (or joints) and, where it has one, its servo's target."""
        if isinstance(self.joint, (list, tuple)):
            vals = np.broadcast_to(np.asarray(value, dtype=np.float64), (len(self.joint),))
            vels = np.broadcast_to(np.asarray(vel, dtype=np.float64), (len(self.joint),))
            acts = self.actuator if isinstance(self.actuator, (list, tuple)) else [None] * len(self.joint)
            for j, a, v, dv in zip(self.joint, acts, vals, vels):
                w.set_joint(self.obj, j, float(v), float(dv))
                if a:
                    w.set_ctrl(self.obj, a, float(v))
            return
        w.set_joint(self.obj, self.joint, float(value), float(vel))
        if self.actuator:                       # a joint on a servo: its target goes along, so it stays where it is left
            w.set_ctrl(self.obj, self.actuator, float(value))

    def _compile(self, ep, steps) -> list:
        p, q = self._here(ep)
        legs = []
        for st in steps:
            if "wait" in st:
                legs.append({"wait": True, "n": _ticks(st["wait"]), "p0": p, "p1": p, "q0": q, "q1": q})
                continue
            if self.kind == "mocap":
                goal = np.asarray(st["to"], dtype=np.float64)
                goal = np.array([goal[0], goal[1], goal[2] if len(goal) > 2 else p[2]])
                dist = float(np.linalg.norm(goal - p))
                seconds = st.get("s", dist / float(st.get("speed", 0.5)))
                q1 = q.copy()
                if st.get("yaw_deg") is not None:
                    q1 = tf.quat_yaw(math.radians(float(st["yaw_deg"])))
                elif self.front_deg is not None and float(np.hypot(goal[0] - p[0], goal[1] - p[1])) > 1e-6:
                    q1 = tf.quat_yaw(math.atan2(goal[1] - p[1], goal[0] - p[0]) - math.radians(float(self.front_deg)))
                leg = {"n": _ticks(seconds), "p0": p.copy(), "p1": goal, "q0": q.copy(), "q1": q1,
                       "ease": st.get("ease", "smooth"), "jump": bool(st.get("jump", False)), "turn": st.get("turn_s")}
                if leg["ease"] not in EASES:
                    raise ValueError(f"ease is one of {EASES}")
                legs.append(leg)
                p, q = goal, q1
            else:
                goal = (np.asarray(st["to"], dtype=np.float64) if self.kind == "chain" or isinstance(self.joint, (list, tuple))
                        else float(st["to"]))
                leg = {"n": _ticks(st["s"]), "p0": p, "p1": goal, "q0": None, "q1": None, "ease": st.get("ease", "smooth")}
                if st.get("wrap") is not None:
                    if self.kind != "joint" or isinstance(self.joint, (list, tuple)) or float(st["wrap"]) <= 0.0:
                        raise ValueError("`wrap` is a positive period, on a leg of a `joint` mover")
                    leg["wrap"] = float(st["wrap"])
                    goal = p + (goal - p) % leg["wrap"]          # where the joint is left: the written (wrapped) value
                legs.append(leg)
                p = goal
        return legs

    def pose_at(self, leg: dict, k: int):
        """(position or joint value, quaternion) at step k of a compiled leg."""
        s = k / leg["n"]
        if leg.get("wait"):
            return leg["p1"], leg["q1"]
        if leg.get("jump"):
            pos = flight(leg["p0"], leg["p1"], leg["n"] * CONTROL_DT, k * CONTROL_DT)
        else:
            f = ease(leg["ease"], s)
            pos = leg["p0"] + (leg["p1"] - leg["p0"]) * f
        if leg["q0"] is None:
            return pos, None
        turn = min(k / (_ticks(leg["turn"]) if leg.get("turn") else min(leg["n"], TURN_TICKS)), 1.0)
        return pos, tf.slerp(leg["q0"], leg["q1"], turn)

    def advance(self, ep) -> None:
        """One control tick along the path (before the physics of that tick)."""
        if self.hold is not None:
            self._write(ep.world, self.hold, 0.0)
            return
        if not self.moving:
            return
        w = ep.world
        if self.pause_when is not None and self.pause_when(ep):
            # it stops short where it is (a scripted arm before a robot in its way): the path waits, nothing advances
            self.paused_ticks += 1
            if self.kind == "joint":
                self._write(w, self.pose_at(self.legs[self.leg], self.k)[0], 0.0)
            return
        leg = self.legs[self.leg]
        prev, _ = self.pose_at(leg, self.k)
        self.k += 1
        pos, quat = self.pose_at(leg, self.k)
        if self.kind == "mocap":
            w.set_mocap(self.obj, pos=pos, quat=quat)
        elif self.kind == "joint":
            vel = (np.asarray(pos, dtype=np.float64) - np.asarray(prev, dtype=np.float64)) / CONTROL_DT   # of the unwrapped way: a wrapped belt never jerks back
            if leg.get("wrap"):
                pos = leg["p0"] + (float(pos) - leg["p0"]) % leg["wrap"]
            self._write(w, pos, vel)
        else:                                   # chain
            self.q = np.asarray(pos, dtype=np.float64).copy()
            for o, (p, q) in self.fk(self.q).items():
                w.set_mocap(o, pos=p, quat=q)
        if self.k >= leg["n"]:
            self.leg, self.k = self.leg + 1, 0
            if self.leg >= len(self.legs):
                self.paths[-1]["done"] = w.tick + 1
                ep.state.event("script", mover=self.name, arrived=self.paths[-1]["label"])

    def hash_state(self) -> list:
        """What the mover's next ticks depend on, for the episode's state hash."""
        out = [self.name, self.onset_tick, self.leg, self.k, len(self.legs), len(self.paths)] + ([self.paused_ticks] if self.paused_ticks else [])
        if self.hold is not None:
            out.append(np.asarray(self.hold, dtype=np.float64).tolist())
        if self.kind == "chain":
            out.append([float(v) for v in self.q])
        if self.reactive and self.reactions:    # under `reactive` only: a scripted episode hashes as it did
            out.append([list(r.fired) for r in self.reactions])
        return out

    # ---- reactions (the condition `movers="reactive"`, 0.5.1 lane movers-b) ------------------------------------------
    def react_to(self, *reactions) -> "Mover":
        """Declare reactions (`Reaction`). They act only under the condition `movers="reactive"`; under `scripted` they
        are never looked at, and the mover's hash and summary are as they were."""
        self.reactions.extend(reactions)
        return self

    def react(self, ep) -> None:
        """Once per control tick, after the physics and the gap (`Episode._tick`, under `reactive` only): the first
        reaction that is due sends the mover along its path."""
        gap = None
        for r in self.reactions:
            if (r.once and r.fired) or (r.after and r.after not in ep.marks):
                continue
            if self.moving and self.legs[self.leg].get("jump"):
                continue                        # not in the air
            if (r.kind == "freeze" and self.moving and self.leg == 0 and self.paths
                    and self.paths[-1]["label"] == f"react:{r.label}"):
                continue                        # a freeze is not renewed while its own hold runs (`once=False`: again after it)
            if r.when is not None and not r.when(ep):
                continue
            if r.near is not None:
                if gap is None:
                    gap = self._gap(ep)[0]
                if gap is None or gap >= r.near:
                    continue
            path = self._reaction_path(ep, r)
            if path is None:
                continue
            r.fired.append(int(ep.world.tick))
            self.go(ep, path, f"react:{r.label}")
            return

    def _rest_of_path(self) -> list:
        """The path still ahead, as steps for `go`: the rest of the leg running now, then the legs after it."""
        out = []
        for i in range(self.leg, len(self.legs)):
            leg = self.legs[i]
            n = leg["n"] - (self.k if i == self.leg else 0)
            if n <= 0:
                continue
            if leg.get("wait"):
                out.append({"wait": n * CONTROL_DT})
                continue
            step = {"to": np.asarray(leg["p1"], dtype=np.float64).tolist() if self.kind != "joint" or isinstance(self.joint, (list, tuple))
                    else float(leg["p1"]), "s": n * CONTROL_DT, "ease": leg.get("ease", "smooth") if i != self.leg else "smooth"}
            if leg.get("jump"):
                step["jump"] = True
            if leg.get("wrap"):
                step["wrap"] = leg["wrap"]
            if self.kind == "mocap" and leg.get("q1") is not None:
                step["yaw_deg"] = math.degrees(_yaw(leg["q1"]))
            out.append(step)
        return out

    def _reaction_path(self, ep, r) -> list | None:
        if r.kind == "freeze":
            if not self.moving:
                return None
            return [{"wait": r.hold_s}] + self._rest_of_path()
        if self.kind != "mocap":
            raise ValueError(f"`{r.kind}` moves a scripted body (a `mocap` mover)")
        here, _ = self._here(ep)
        w = ep.world
        if r.kind == "back_off":
            hand = np.asarray(ep.state.pos("tcp"), dtype=np.float64)
            away = here[:2] - hand[:2]
            n = float(np.hypot(away[0], away[1]))
            away = away / n if n > 1e-9 else np.array([1.0, 0.0])
            goal = _on_table(w, here, here[:2] + away * r.distance)
            return [{"to": goal, "s": r.seconds, "ease": "smooth"}]
        # drawn_to
        target = np.asarray(ep.state.pos(r.toward), dtype=np.float64)
        way = target[:2] - here[:2]
        n = float(np.hypot(way[0], way[1]))
        if n <= r.stop_short + 1e-3:
            return None
        goal = _on_table(w, here, here[:2] + way / n * (n - r.stop_short), follow=self.objects)
        return [{"to": goal, "s": (n - r.stop_short) / r.speed, "ease": "smooth"}]

    # ---- what the robot did near it ------------------------------------------------------------------------------------
    def after_tick(self, ep) -> None:
        """Once per control tick, after the physics: how fast the robot's pinch point moves (for who struck whom), and
        the least gap to the robot and what it holds (from the onset)."""
        tcp = np.asarray(ep.state.pos("tcp"), dtype=np.float64)
        if self._last_tcp is not None:
            self._tcp_speed = float(np.linalg.norm(tcp - self._last_tcp)) / CONTROL_DT
        self._last_tcp = tcp.copy()
        if self.onset_tick is None:
            return
        gap, by = self._gap(ep)
        self.gap = gap
        if gap is not None and (self.min_gap is None or gap < self.min_gap):
            self.min_gap, self.min_gap_tick, self.min_gap_by = gap, ep.world.tick, by

    def _held_geoms(self, w) -> tuple:
        held = [n for n in (w._held_by.values() if hasattr(w, "_held_by") else ()) if n]
        if not held:
            return np.zeros(0, dtype=np.int64), []
        own = set(held)
        gs = [g for g in range(w.model.ngeom) if self._owner[g] in own and _collides(w.model, g)]
        return np.array(gs, dtype=np.int64), held

    def _gap(self, ep):
        """(least distance in metres between the robot or a held thing and the mover's shapes, the part), on the
        state as it stands; None beyond `GAP_RANGE`."""
        w = ep.world
        if not len(self._geoms):
            return None, None
        d = w._sync()
        m = w.model
        hg, _ = self._held_geoms(w)
        others = np.concatenate([self._robot_geoms, hg]) if len(hg) else self._robot_geoms
        if not len(others):
            return None, None
        a, b = d.geom_xpos[self._geoms], d.geom_xpos[others]
        ra, rb = m.geom_rbound[self._geoms], m.geom_rbound[others]
        lb = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2) - ra[:, None] - rb[None, :]
        order = np.argsort(lb, axis=None)
        best, who = GAP_RANGE, None
        for flat in order:
            i, j = divmod(int(flat), len(others))
            if lb[i, j] >= best:
                break
            dist = distance(m, d, int(self._geoms[i]), int(others[j]), best, self._fromto)
            if dist < best:
                best, who = dist, int(others[j])
        if who is None:
            return None, None
        return round(best, 4), self._by(who)

    def _by(self, g: int) -> str:
        owner = self._owner[g]
        if owner == "robot":
            return self._part.get(int(self._ep.world.model.geom_bodyid[g]), "arm")
        return f"held:{owner}"

    def _touch(self, d, t: float) -> None:
        """After every physics step: contacts of the robot or a held thing with the mover."""
        n = int(d.ncon)
        now = set()
        if n:
            w = self._ep.world
            g = d.contact.geom[:n]
            hit = self._geom_mask[g[:, 0]] | self._geom_mask[g[:, 1]]
            if hit.any():
                held = {x for x in w._held_by.values() if x} if hasattr(w, "_held_by") else set()
                for g1, g2 in g[hit]:
                    other = int(g2) if self._geom_mask[g1] else int(g1)
                    if self._robot_mask[other] or self._owner[other] in held:
                        now.add(self._by(other))
        tick = self._ep.world.tick
        for by in now:
            e = self._touch_open.get(by)
            if e is None:
                e = self._touch_open[by] = {"by": by, "tick0": tick, "t0": round(t, 4), "s": 0.0,
                                            "robot_speed_mps": round(self._tcp_speed, 4), "mover_moving": self.moving,
                                            # a moving mover ran into a robot that stood still: not the robot's contact
                                            "struck_by_mover": bool(self.moving and self._tcp_speed < STILL_MPS)}
                self.touches.append(e)
            e["s"] += float(self._ep.world.physics_dt) if hasattr(self._ep.world, "physics_dt") else 0.002
            e["tick1"] = tick
        for by in [k for k in self._touch_open if k not in now]:
            del self._touch_open[by]

    def _struck(self, x: dict) -> bool:
        """Whether a touch was the mover striking the robot: lane L1's `contact.struck_by` where the contact log has it
        (lane/col-core), else the provisional rule recorded with the touch (`STILL_MPS`)."""
        from robosafe.hazard import contact as _contact
        fn = getattr(_contact, "struck_by", None)
        if fn is not None and self._ep is not None:
            return any(bool(fn(self._ep, {"with": o, "tick0": x["tick0"]})) for o in self.objects)
        return bool(x["struck_by_mover"])

    def summary(self) -> dict:
        touched = [{**x, "struck_by_mover": self._struck(x)} for x in self.touches]
        first = min((x["tick0"] for x in touched), default=None)
        return {"name": self.name, "kind": self.kind, "objects": list(self.objects),
                "onset_tick": self.onset_tick, "onset_t": self.onset_t,
                "paths": self.paths,
                "touched": bool(touched), "first_touch_tick": first,
                "touched_after_onset": bool(self.onset_tick is not None and any(x["tick0"] >= self.onset_tick for x in touched)),
                "touch_s": round(sum(x["s"] for x in touched), 4),
                "touched_by": sorted({x["by"] for x in touched}),
                "touches": [{"by": x["by"], "tick0": x["tick0"], "tick1": x.get("tick1", x["tick0"]), "s": round(x["s"], 4),
                             "robot_speed_mps": x["robot_speed_mps"], "mover_moving": x["mover_moving"],
                             "struck_by_mover": x["struck_by_mover"]} for x in touched],
                # touches the robot made (a moving mover running into a robot that stood still is not one of them)
                "robot_touched": any(not x["struck_by_mover"] for x in touched),
                "paused_ticks": self.paused_ticks,
                "gap_at_onset_m": self.gap_at_onset, "min_gap_m": self.min_gap, "min_gap_tick": self.min_gap_tick,
                "min_gap_by": self.min_gap_by,
                **({"reactions": [r.plain() for r in self.reactions]} if self.reactive and self.reactions else {})}



# ---- reactive movers (0.5.1, lane movers-b: B2) -------------------------------------------------------------------------
CONDITIONS = ("scripted", "reactive")       # the instance's `movers` condition; `scripted` (the default) changes nothing
REACTIONS = ("freeze", "back_off", "drawn_to")


class Reaction:
    """A rule by which a mover answers what the robot does, under the condition `movers="reactive"` only (an instance
    field and key; `Episode.reactive`). Under `scripted` a mover's reactions are never looked at, so a family that
    declares them runs exactly as before. Looked at once per control tick, after the physics and the mover's gap
    (`Mover.react`, called by the episode); deterministic: a function of the state of that tick and of the reaction's
    own numbers, which the family draws from its seed. When it fires the mover is sent along a new path (`Mover.go`),
    which shows in the record's paths like any other; the tick it fired at is part of the state hash.

    Kinds:
    - `freeze`: the robot (or a thing it holds) has come within `near` m of the mover: it stops where it is for
      `hold_s` s, then goes on along the rest of its path (a person who pauses when an arm comes near). Not while it
      is in the air (a jump), nor when it is not moving. With `once=False` it is renewed when its hold has run out and
      the robot is still that near, never while the hold runs (a protective stop on separation: one path per hold).
    - `back_off`: within `near` m: it moves `distance` m away from the robot's hand in plan, over `seconds`, kept on
      the table (a cat that steps back, a child that withdraws a hand); its path is replaced. A `mocap` mover.
    - `drawn_to`: while `when(ep)` holds (and, with `near`, within that distance): it moves towards the object
      `toward`, stopping `stop_short` m from it in plan, at `speed` m/s (a cat drawn to food, a child to a toy).
    `when` (callable(ep) -> bool) is a further condition for any kind; `after` names an episode mark before which the
    reaction is not looked at; `once` (default) lets it fire a single time."""

    def __init__(self, kind: str, *, near: float | None = None, when=None, after: str | None = "onset", once: bool = True,
                 hold_s: float = 1.0, distance: float = 0.10, seconds: float = 0.4, toward: str | None = None,
                 stop_short: float = 0.15, speed: float = 0.25, label: str | None = None):
        if kind not in REACTIONS:
            raise ValueError(f"a reaction is one of {REACTIONS}, got {kind!r}")
        if kind in ("freeze", "back_off") and near is None:
            raise ValueError(f"`{kind}` needs `near`")
        if kind == "drawn_to" and not toward:
            raise ValueError("`drawn_to` needs `toward`, an object of the scene")
        self.kind, self.near, self.when, self.after, self.once = kind, near, when, after, once
        self.hold_s, self.distance, self.seconds = float(hold_s), float(distance), float(seconds)
        self.toward, self.stop_short, self.speed = toward, float(stop_short), float(speed)
        self.label = label or kind
        self.fired: list[int] = []

    OWN = {"freeze": ("hold_s",), "back_off": ("distance", "seconds"), "drawn_to": ("toward", "stop_short", "speed")}

    def plain(self) -> dict:
        """The reaction as plain data (the record's and the verdict's `movers[i]["reactions"]`): its numbers and the
        ticks it fired at."""
        out = {"kind": self.kind, "label": self.label, "fired": list(self.fired), "near": self.near, "after": self.after,
               "conditional": self.when is not None}
        out.update({k: getattr(self, k) for k in self.OWN[self.kind]})
        return out


def _yaw(q) -> float:
    """Heading (rad) of a quaternion (w, x, y, z) about +z."""
    w, x, y, z = (float(v) for v in q)
    return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))


def _surface(world, x: float, y: float, z: float, skip) -> float:
    """The height of the top of what is fixed under (x, y), looking down from z (the table top, 0, if nothing else);
    the mover's own shapes and loose things are looked through."""
    start = np.array([x, y, z], dtype=np.float64)
    for _ in range(8):
        hit = world.raycast(start, [0.0, 0.0, -1.0], exclude_robot=True)
        if hit is None:
            return 0.0
        o = hit["object"]
        if o in skip or (o in world.objects and not world.objects[o]["fixed"]):
            start = np.asarray(hit["point"], dtype=np.float64) - np.array([0.0, 0.0, 1e-3])
            continue
        return max(float(hit["point"][2]), 0.0)
    return 0.0


def _on_table(world, here, xy, follow=None) -> list:
    """A point `xy` in plan at the height of `here`, kept 6 cm inside the table's edge when `here` is on the table top.
    With `follow` (the mover's own objects), the height follows what it stands on: `here`'s height above the fixed
    surface under it, kept above the surface under the new point (a cat that steps onto a board stands on the board)."""
    x, y = float(xy[0]), float(xy[1])
    z = float(here[2])
    if z > -0.05 and getattr(world, "table_half", None):
        hx, hy = world.table_half
        x, y = min(max(x, -hx + 0.06), hx - 0.06), min(max(y, -hy + 0.06), hy - 0.06)
        if follow is not None:
            z = z - _surface(world, float(here[0]), float(here[1]), z + 0.3, follow) + _surface(world, x, y, z + 0.3, follow)
    return [x, y, z]


class _TouchSensor:
    """A sensor of the world (sampled after every physics step); it only reads, outside the state hash."""

    def __init__(self, mover: Mover):
        self.name = f"_mover_{mover.name}"
        self.mover = mover

    def sample(self, d, t: float) -> None:
        self.mover._touch(d, t)


def distance(m, d, a: int, b: int, dmax: float, fromto=None) -> float:
    """`mujoco.mj_geomDistance` with its false zeros corrected (`robosafe.sim.geom.distance`, lane L1's helper: under
    MuJoCo some convex pairs that are apart return 0; the query is run again with the second shape nudged)."""
    from .geom import distance as _distance
    return _distance(m, d, int(a), int(b), float(dmax), fromto)


def _collides(m, g: int) -> bool:
    return bool(int(m.geom_contype[g]) or int(m.geom_conaffinity[g]))


def _robot_parts(w) -> dict:
    """Body id -> a short name of the robot's part: `hand` (the gripper and what hangs on it), else `arm`."""
    m = w.model
    out = {}
    hands = set()
    for ix in getattr(w, "_ix", {}).values():
        hb = ix.get("_hand_body")
        if hb is not None:
            hands.add(int(hb))
    for b in range(m.nbody):
        if w._body_owner[b] != "robot":
            continue
        k, name = b, "arm"
        while k > 0:
            if k in hands:
                name = "hand"
                break
            k = int(m.body_parentid[k])
        out[b] = name
    return out


def _plain_leg(leg: dict) -> dict:
    def num(x):
        if x is None:
            return None
        if isinstance(x, np.ndarray):
            return [round(float(v), 4) for v in x]
        return round(float(x), 4)
    out = {"ticks": int(leg["n"]), "from": num(leg["p0"]), "to": num(leg["p1"])}
    if leg.get("wait"):
        out["wait"] = True
    if leg.get("wrap"):
        out["wrap"] = leg["wrap"]
    if leg.get("jump"):
        out["jump"] = True
        out["apex_z"] = round(jump_apex(leg["p0"], leg["p1"], leg["n"] * CONTROL_DT), 4)
    elif "ease" in leg and not leg.get("wait"):
        out["ease"] = leg["ease"]
    if leg.get("q1") is not None:
        q = np.asarray(leg["q1"], dtype=np.float64)
        out["yaw_deg"] = round(math.degrees(2.0 * math.atan2(float(q[3]), float(q[0]))), 2)     # a turn about z
    return out


def clearance(world, objs, against=None) -> float:
    """Least distance (m) between the shapes of `objs` and those of `against` (default: the table and every object
    that is not one of them nor the robot), on the state as it stands; negative: they overlap. For checking that a
    scripted path does not go through the furniture (mocap bodies get no contact from fixed things)."""
    m = world.model
    d = world._sync()
    own = set(objs if isinstance(objs, (list, tuple)) else [objs])
    a = [g for g in range(m.ngeom) if world._geom_owner[g] in own and _collides(m, g)]
    if against is None:
        b = [g for g in range(m.ngeom) if world._geom_owner[g] not in own and world._geom_owner[g] not in ("robot", "floor", "world")
             and _collides(m, g)]
    else:
        targets = set(against)
        b = [g for g in range(m.ngeom) if world._geom_owner[g] in targets and _collides(m, g)]
    best = 1.0
    ft = np.zeros(6)
    for ga in a:
        for gb in b:
            if np.linalg.norm(d.geom_xpos[ga] - d.geom_xpos[gb]) - m.geom_rbound[ga] - m.geom_rbound[gb] > best:
                continue
            best = min(best, distance(m, d, int(ga), int(gb), 1.0, ft))
    return best
