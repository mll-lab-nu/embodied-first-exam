"""Sensors with the resolution of the physics step.

A control row lasts ten physics steps. What happens in between (a block passing a gate, a pendulum going through its
lowest point) is lost to anything that looks once per row. The sensors here are evaluated inside `World.step`, after
every physics step, and only read: they never call into the solver and never write to the simulation data, so they
cannot change the trajectory. What they have recorded is not part of the state hash; it is a function of the rows,
so a replay records the same.

After `mj_step` the positions and contacts in the data are those of the state *before* the integration of that step,
at time `data.time - timestep`. The sensors use exactly these, with that time stamp. They therefore run one physics
step behind the state; `read()` of a displacement sensor, which looks at the present state, goes through the world's
scratch copy instead.

Declared in the scene (`"sensors": [{"name": ..., "kind": ..., ...}]`) or added with `World.add_sensor(spec)`:

- `light_gate`: the times at which a point crosses a plane, linearly interpolated between physics steps, with direction.
    {"name": "gate", "kind": "light_gate", "track": "block" | "rig/bob_0", "plane": "ramp/gate_1", "axis": "x",
     "radius": 0.05}
  `track` is an object (its origin), a site or a body. The plane goes through the site `plane` and is normal to
  that site's `axis` (default "z"); or give `"point": [x, y, z], "normal": [x, y, z]` in the bench frame. With
  `radius`, only crossings within that distance of the plane's point count (a gate of finite size).
  `.crossings` is a list of `{"t": seconds, "direction": +1 | -1}` (+1: moving along the normal).
- `displacement` (alias `height`): the position of a site along an axis.
    {"name": "pointer", "kind": "displacement", "site": "balance/pointer", "relative_to": "balance/scale_zero",
     "axis": [0, 0, 1], "record": true, "every": 1}
  `.read()` gives the present value in metres. With `record`, `.samples` holds `(t, value)` every `every` physics
  steps.
- `contact_timer`: when two things touch.
    {"name": "grip", "kind": "contact_timer", "a": "robot", "b": "rig"}  or  {"a_geoms": "2f85/", "b_body": "rig/bob_0"}
  `a` and `b` are object names or `robot`, `table`, `floor`; `a_body` / `b_body` name one body instead;
  `a_geoms` / `b_geoms` a prefix of geom names. `.intervals` is a list of `[t_start, t_end]` (`t_end` None while
  touching), `.touching`, `.total()`.
"""
from __future__ import annotations

import numpy as np

from . import tf

_AXES = {"x": 0, "y": 1, "z": 2}


def _point_reader(world, name: str):
    """A function data -> position (3,) of an object origin, a site or a body."""
    m = world.model
    if name in world.objects:
        b = world.objects[name]["body_id"]
        return lambda d: d.xpos[b]
    try:
        s = m.site(name).id
        return lambda d: d.site_xpos[s]
    except KeyError:
        pass
    try:
        b = m.body(name).id
    except KeyError:
        raise KeyError(f"sensor: no object, site or body called {name!r}") from None
    return lambda d: d.xpos[b]


class LightGate:
    kind = "light_gate"

    def __init__(self, world, spec: dict):
        self.name = spec["name"]
        self.spec = dict(spec)
        self._point = _point_reader(world, spec["track"])
        self._radius = float(spec["radius"]) if spec.get("radius") is not None else None
        if "plane" in spec:
            sid = world.model.site(spec["plane"]).id
            col = _AXES[spec.get("axis", "z")]
            self._plane = lambda d: (d.site_xpos[sid], d.site_xmat[sid].reshape(3, 3)[:, col])
        else:
            p0, n = np.asarray(spec["point"], dtype=np.float64), tf.unit(spec["normal"])
            self._plane = lambda d: (p0, n)
        self.crossings: list[dict] = []
        self._last = None          # (time, signed distance, in-plane distance from the gate's point)

    def sample(self, d, t: float) -> None:
        p = self._point(d)
        p0, n = self._plane(d)
        rel = p - p0
        s = float(np.dot(rel, n))
        off = float(np.linalg.norm(rel - s * n))
        last = self._last
        if last is not None and (last[1] < 0.0) != (s < 0.0):
            f = last[1] / (last[1] - s)                       # fraction of the step at which the plane was met
            if self._radius is None or last[2] + f * (off - last[2]) <= self._radius:
                self.crossings.append({"t": last[0] + f * (t - last[0]), "direction": 1 if s > last[1] else -1})
        self._last = (t, s, off)

    def read(self) -> dict:
        return {"crossings": [dict(c) for c in self.crossings], "count": len(self.crossings)}

    def clear(self) -> None:
        self.crossings.clear()


class Displacement:
    kind = "displacement"

    def __init__(self, world, spec: dict):
        self.name = spec["name"]
        self.spec = dict(spec)
        self._world = world
        self._site = world.model.site(spec["site"]).id
        self._ref = world.model.site(spec["relative_to"]).id if spec.get("relative_to") else None
        self._axis = tf.unit(spec.get("axis", [0.0, 0.0, 1.0]))
        self._record = bool(spec.get("record", False))
        self._every = max(int(spec.get("every", 1)), 1)
        self._n = 0
        self.samples: list[tuple[float, float]] = []

    def _value(self, d) -> float:
        p = d.site_xpos[self._site]
        if self._ref is not None:
            p = p - d.site_xpos[self._ref]
        return float(np.dot(p, self._axis))

    def sample(self, d, t: float) -> None:
        if self._record:
            if self._n % self._every == 0:
                self.samples.append((t, self._value(d)))
            self._n += 1

    def read(self) -> float:
        """The value now (metres), from the world's scratch copy."""
        return self._value(self._world._sync())

    def clear(self) -> None:
        self.samples.clear()


class ContactTimer:
    kind = "contact_timer"

    def __init__(self, world, spec: dict):
        self.name = spec["name"]
        self.spec = dict(spec)
        m = world.model
        self._sets = []
        for side in ("a", "b"):
            if side in spec:
                mask = np.array([world.geom_owner(g) == spec[side] for g in range(m.ngeom)])
            elif side + "_body" in spec:
                b = m.body(spec[side + "_body"]).id
                mask = np.array([int(m.geom_bodyid[g]) == b for g in range(m.ngeom)])
            elif side + "_geoms" in spec:
                mask = np.array([m.geom(g).name.startswith(spec[side + "_geoms"]) for g in range(m.ngeom)])
            else:
                raise KeyError(f"contact_timer {self.name!r} needs '{side}', '{side}_body' or '{side}_geoms'")
            if not mask.any():
                raise KeyError(f"contact_timer {self.name!r}: side {side!r} matches no geom")
            self._sets.append(mask)
        self.intervals: list[list] = []
        self.touching = False

    def sample(self, d, t: float) -> None:
        n = d.ncon
        now = False
        if n:
            g = d.contact.geom[:n]
            a, b = self._sets
            hit = ((a[g[:, 0]] & b[g[:, 1]]) | (b[g[:, 0]] & a[g[:, 1]])) & (d.contact.dist[:n] <= 0.0)
            now = bool(hit.any())
        if now and not self.touching:
            self.intervals.append([t, None])
        elif self.touching and not now:
            self.intervals[-1][1] = t
        self.touching = now

    def total(self, until: float | None = None) -> float:
        """Seconds of contact so far (an open interval counts up to `until`, default: not at all)."""
        return float(sum((e if e is not None else (until if until is not None else s)) - s for s, e in self.intervals))

    def read(self) -> dict:
        return {"touching": self.touching, "intervals": [list(i) for i in self.intervals]}

    def clear(self) -> None:
        self.intervals = [[self.intervals[-1][0], None]] if self.touching else []


KINDS = {"light_gate": LightGate, "displacement": Displacement, "height": Displacement, "contact_timer": ContactTimer}


def build(world, spec: dict):
    if "name" not in spec or spec.get("kind") not in KINDS:
        raise ValueError(f"a sensor needs a name and a kind out of {sorted(KINDS)}: {spec!r}")
    return KINDS[spec["kind"]](world, spec)
