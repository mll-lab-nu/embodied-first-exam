from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from robosafe.sim import tf
from robosafe.sim.world import CONTROL_DT, World

WATER_LIKE = ("water", "juice", "soup", "saline", "tea")
LIQUID_COLOURS = {"default": [0.55, 0.70, 0.85, 0.75], "water": [0.62, 0.80, 0.92, 0.55], "saline": [0.62, 0.80, 0.92, 0.55],
                  "juice": [0.96, 0.62, 0.12, 0.90], "soup": [0.90, 0.42, 0.15, 0.95], "tea": [0.62, 0.38, 0.16, 0.85],
                  "bleach": [0.93, 0.93, 0.62, 0.80], "ammonia": [0.78, 0.86, 0.80, 0.70], "cleaner": [0.20, 0.45, 0.90, 0.85],
                  "detergent": [0.25, 0.75, 0.55, 0.90], "ethanol": [0.85, 0.90, 0.95, 0.50], "oil": [0.90, 0.78, 0.25, 0.85],
                  "honey": [0.88, 0.62, 0.10, 0.95], "waste": [0.45, 0.40, 0.30, 0.90], "peroxide": [0.90, 0.92, 0.95, 0.55],
                  "milk": [0.97, 0.96, 0.92, 0.97], "porridge": [0.90, 0.84, 0.70, 0.98], "coffee": [0.30, 0.18, 0.10, 0.95],
                  "soil": [0.33, 0.24, 0.16, 1.0], "solvent": [0.80, 0.88, 0.95, 0.55], "acetone": [0.80, 0.88, 0.95, 0.55],
                  "buffer": [0.70, 0.86, 0.80, 0.65], "acid": [0.90, 0.90, 0.70, 0.60], "vinegar": [0.93, 0.88, 0.70, 0.70],
                  "soy": [0.20, 0.10, 0.06, 0.97], "pill": [0.96, 0.96, 0.96, 1.0], "cola": [0.22, 0.10, 0.06, 0.95],
                  "wine": [0.50, 0.06, 0.14, 0.92], "broth": [0.85, 0.65, 0.30, 0.90], "syrup": [0.75, 0.25, 0.30, 0.90],
                  "blueberry": [0.25, 0.16, 0.50, 0.93], "raisin": [0.25, 0.14, 0.10, 1.0], "copper": [0.10, 0.45, 0.88, 0.85]}


def liquid_colour(substance: str) -> list:
    """The colour a substance is drawn in: its own entry, else the longest entry its name contains (`orange_juice` is
    drawn as `juice`), else a pale default."""
    if substance in LIQUID_COLOURS:
        return LIQUID_COLOURS[substance]
    inside = [k for k in LIQUID_COLOURS if k != "default" and k in substance]
    return LIQUID_COLOURS[max(inside, key=len)] if inside else LIQUID_COLOURS["default"]


# zones of generated assets that are places for things unless the asset says otherwise (`"place": false`)
PLACE_NAMES = ("surface", "slot", "inside", "top", "cavity", "socket", "drum", "bin", "tray", "shelf", "rack", "drain", "hopper", "nest", "day", "above")


class SharedLook:
    """A monitor: shapes of an object that are drawn one way while any of several devices is on and another way
    while none is (the lamp of a hob that says its glass is hot). A picture only."""

    def __init__(self, obj: str, devices: list, on: dict, off: dict):
        self.obj, self.devices, self.on, self.off = obj, list(devices), dict(on), dict(off)
        self.lit: bool | None = None

    def update(self, st: "State") -> None:
        lit = any(bool(st.devices[d].state.get("on")) for d in self.devices)
        if lit != self.lit:
            self.lit = lit
            for geom, rgba in sorted((self.on if lit else self.off).items()):
                st.world.set_look(f"{self.obj}/{geom}", rgba)

    def snapshot(self) -> dict:
        return {"shared_look": self.obj, "lit": bool(self.lit)}


@dataclass
class Zone:
    """A volume fixed to an object: a box, cylinder (axis z) or sphere in the frame of a site or at a pose given in
    the object's frame. `size`: box half extents [x, y, z]; cylinder [radius, half height]; sphere [radius];
    `rbox` (since 0.4.2) [x, y, z, r]: everything within `r` in plan of the box of half extents x, y (a clearance
    around a footprint, its corners rounded), between -z and z."""
    obj: str
    name: str = "zone"
    shape: str = "box"
    size: tuple = (0.05, 0.05, 0.05)
    site: str | None = None            # "<site name>" of the object
    pos: tuple = (0.0, 0.0, 0.0)       # in the object frame (or the site frame when `site` is given)
    quat: tuple = (1.0, 0.0, 0.0, 0.0)
    place: bool = False                # a thing can be put down here: `place` aimed at the object goes to this zone
    open: bool = False                 # a place made of bars with gaps between them (the rails of a rack): pointing
                                       # at what shows through it from above still means this place

    def pose(self, world: World) -> tf.Pose:
        base = world.locate(f"{self.obj}/{self.site}") if self.site else world.locate(self.obj)
        return tf.compose(base, (np.asarray(self.pos, dtype=np.float64), np.asarray(self.quat, dtype=np.float64)))

    def in_plan(self, p, margin: float = 0.0) -> bool:
        """A point in the zone's frame lies within the zone seen from above."""
        s = self.size
        if self.shape == "box":
            return bool(abs(p[0]) <= s[0] + margin and abs(p[1]) <= s[1] + margin)
        if self.shape == "rbox":
            return bool(math.hypot(max(abs(p[0]) - s[0], 0.0), max(abs(p[1]) - s[1], 0.0)) <= s[3] + margin)
        return bool(math.hypot(p[0], p[1]) <= s[0] + margin)

    def contains(self, world: World, point, margin: float = 0.0) -> bool:
        p = tf.compose(tf.inverse(self.pose(world)), (np.asarray(point, dtype=np.float64), np.array([1.0, 0, 0, 0])))[0]
        s = self.size
        if self.shape == "rbox":
            return bool(self.in_plan(p, margin) and abs(p[2]) <= s[2] + margin)
        if self.shape == "box":
            return bool(abs(p[0]) <= s[0] + margin and abs(p[1]) <= s[1] + margin and abs(p[2]) <= s[2] + margin)
        if self.shape == "cylinder":
            return bool(math.hypot(p[0], p[1]) <= s[0] + margin and abs(p[2]) <= s[1] + margin)
        if self.shape == "sphere":
            return bool(float(np.linalg.norm(p)) <= s[0] + margin)
        raise ValueError(f"unknown zone shape {self.shape!r}")

    @classmethod
    def of(cls, world: World, obj: str, name: str) -> "Zone":
        """A zone declared in an asset's meta (`meta["zones"][name]`)."""
        z = world.objects[obj]["meta"]["zones"][name]
        place = z.get("place")
        if place is None:
            place = name.startswith(PLACE_NAMES)
        shape, size = z.get("shape", "box"), [float(v) for v in z["size"]]
        # asset metadata gives full extents (box x, y, z; cylinder radius, height); a Zone holds half extents
        size = [v / 2.0 for v in size] if shape == "box" else ([size[0], size[1] / 2.0] if shape == "cylinder" else size)
        return cls(obj=obj, name=name, shape=shape, size=tuple(size), site=z.get("site"),
                   pos=tuple(z.get("pos", (0.0, 0.0, 0.0))), quat=tuple(z.get("quat", (1.0, 0.0, 0.0, 0.0))), place=bool(place),
                   open=bool(z.get("open", False)))

    def half_height(self) -> float:
        return float(self.size[2] if self.shape in ("box", "rbox") else (self.size[1] if self.shape == "cylinder" else self.size[0]))

    def crossing(self, world: World, origin, direction) -> np.ndarray | None:
        """Where a ray that comes from above crosses the lower face of the zone (the surface things are put on), or
        None if it does not pass through that face."""
        pose = self.pose(world)
        inv = tf.inverse(pose)
        o = tf.compose(inv, (np.asarray(origin, dtype=np.float64), np.array([1.0, 0, 0, 0])))[0]
        d = tf.rotate(inv[1], direction)
        h = self.half_height()
        if d[2] >= -1e-9 or o[2] <= -h:
            return None
        p = o + d * ((-h - o[2]) / d[2])
        inside = self.in_plan(p)
        return tf.compose(pose, (p, np.array([1.0, 0, 0, 0])))[0] if inside else None


@dataclass
class Device:
    """Something with a state the agent can change: a burner, a power strip, a lamp. `state` is a dict of plain
    values; `controls` maps a control name to the state key it toggles; `looks` maps (key, value) to appearances
    {geom: rgba} applied whenever that key takes that value."""
    name: str
    obj: str
    state: dict = field(default_factory=dict)
    controls: dict = field(default_factory=dict)       # control name -> state key
    looks: dict = field(default_factory=dict)          # "key=value" -> {geom: rgba}

    def get(self, key: str, default=None):
        return self.state.get(key, default)


@dataclass
class Vessel:
    """Liquid or loose contents in an object. Geometry (object frame): the mouth is a disc of `radius` at `mouth`;
    the inside reaches down to `bottom`."""
    obj: str
    capacity_ml: float
    contents: dict = field(default_factory=dict)       # substance -> ml
    mouth: tuple = (0.0, 0.0, 0.1)
    bottom: tuple = (0.0, 0.0, 0.005)
    radius: float = 0.03
    closed: bool = False
    fixed_level: bool = False                          # a sink or drain: takes anything, never fills
    half: tuple | None = None                          # a box-shaped vessel (a tub, a bin): the half sizes of its inside
                                                       # in plan (x, y); None: round, the mouth's disc is its plan

    def within(self, p) -> bool:
        """A point in the vessel's frame lies within its inside in plan and between its bottom and its mouth (the
        test of `rules.Immersion` and `rules.in_vessel`). A box-shaped vessel is tested on its rectangle (since
        0.4.2; the inscribed disc before, which left out its ends and corners), a round one on the mouth's disc."""
        if self.half is not None:
            inside = abs(p[0] - self.bottom[0]) <= self.half[0] and abs(p[1] - self.bottom[1]) <= self.half[1]
        else:
            inside = math.hypot(p[0], p[1]) <= self.radius
        return bool(inside and self.bottom[2] - 0.01 <= p[2] <= self.mouth[2])

    def total(self) -> float:
        return float(sum(self.contents.values()))

    def add(self, substance: str, ml: float) -> float:
        """Returns the overflow (ml)."""
        room = float("inf") if self.fixed_level else max(self.capacity_ml - self.total(), 0.0)
        take = min(ml, room)
        if take > 0:
            self.contents[substance] = self.contents.get(substance, 0.0) + take
        return ml - take

    def take_fraction(self, ml: float) -> dict:
        total = self.total()
        if total <= 0.0:
            return {}
        f = min(ml / total, 1.0)
        out = {k: v * f for k, v in self.contents.items()}
        for k in list(self.contents):
            self.contents[k] -= out[k]
            if self.contents[k] < 1e-9:
                del self.contents[k]
        return out


class Cap:
    """A cap that closes a vessel. When the cap is let go with its underside on the vessel's mouth it is fastened
    there (`World.fasten`: the scene must list the pair under `fasteners`) and the vessel is closed; taking the cap
    in the hand again opens it. `place` aimed at the vessel with the cap in the hand goes to the mouth."""

    def __init__(self, cap: str, vessel: str, tolerance: float = 0.015):
        self.cap, self.vessel, self.tolerance = cap, vessel, float(tolerance)

    def update(self, st: "State") -> None:
        w, v = st.world, st.vessels[self.vessel]
        on = self.cap in w.fastened
        if on and w.holds(self.cap):
            w.unfasten(self.cap)
            v.closed = False
            st.event("cap", cap=self.cap, vessel=self.vessel, closed=False)
        elif not on and not w.holds(self.cap):
            o = st.p["objects"]
            mouth = o[self.vessel]["pos"] + tf.rotate(o[self.vessel]["quat"], v.mouth)
            d = o[self.cap]["pos"] - mouth
            if math.hypot(d[0], d[1]) <= self.tolerance and abs(d[2]) <= self.tolerance and st.speed(self.cap) < 0.05:
                w.fasten(self.cap)
                v.closed = True
                st.event("cap", cap=self.cap, vessel=self.vessel, closed=True)

    def snapshot(self) -> dict:
        return {"cap": self.cap, "vessel": self.vessel}


class State:
    def __init__(self, world: World):
        self.world = world
        self.tags: dict[str, set] = {name: set(o["meta"].get("tags", [])) for name, o in world.objects.items()}
        self.vars: dict[str, dict] = {name: {} for name in world.objects}
        self.devices: dict[str, Device] = {}
        self.vessels: dict[str, Vessel] = {}
        self.zones: dict[str, Zone] = {}
        self.rules: list = []
        self.events: list[dict] = []
        self.spills: list[dict] = []
        self.monitors: list = []
        # watchers: like monitors, updated every tick, but what they keep is read by the verdict only and never enters
        # the state hash (a mark that decides nothing must not make the records of a version unreplayable)
        self.watchers: list = []
        self.dose: dict[str, float] = {}       # vessel -> what it may still let out during the pour in progress (`pour` with "some")
        self.caps: dict[str, str] = {}        # vessel object -> the cap object that closes it (see `Cap`)
        self.inserts: dict[str, object] = {}  # object -> what it can go into (`insert.Blade`, `insert.Plug`)
        self._p: dict | None = None
        self._p_tick = -1
        self._fired: set = set()

    # ---- building ------------------------------------------------------------------------------------------------
    def tag(self, obj: str, *tags: str) -> None:
        self.tags.setdefault(obj, set()).update(tags)

    def untag(self, obj: str, *tags: str) -> None:
        self.tags.setdefault(obj, set()).difference_update(tags)

    def has(self, obj: str, tag: str) -> bool:
        return tag in self.tags.get(obj, ())

    def tagged(self, tag: str) -> list[str]:
        return sorted(o for o, t in self.tags.items() if tag in t)

    def add_device(self, dev: Device) -> Device:
        self.devices[dev.name] = dev
        for key, value in sorted(dev.state.items()):
            self._apply_look(dev, key, value)
        return dev

    def device_from_meta(self, obj: str, name: str | None = None, controls: dict | None = None, **state) -> Device:
        """A device for a generated asset. Its named appearances follow state keys: `on` / `off` follow `on`;
        `lit` / `unlit` follow `lit`; `running` / `idle` follow `running`; `locked` / `unlocked` follow `locked`;
        the colours of a signal lamp (`red`, `amber`, `green`, `blue`, `off`) follow `colour`. `controls` maps each
        control of the asset to the boolean state key it toggles (default: every control toggles `on`; give it for
        things with several buttons, e.g. {"start": "running", "open": "door_open"}). Pass the initial state as
        keywords, e.g. `on=True`."""
        meta = self.world.objects[obj]["meta"]
        names = set(meta.get("looks", {}))
        table = {}
        if names & {"red", "amber", "green", "blue"}:
            table.update({n: ("colour", n) for n in names})
        else:
            for a, b, key in (("on", "off", "on"), ("lit", "unlit", "lit"), ("running", "idle", "running"), ("locked", "unlocked", "locked")):
                if a in names:
                    table[a] = (key, True)
                if b in names:
                    table[b] = (key, False)
            if "running" in names and "idle" not in names and "off" in names and "on" not in names:
                table["off"] = ("running", False)
        looks = {f"{key}={value}": dict(meta["looks"][look]) for look, (key, value) in table.items()}
        if controls is None:
            controls = {c: "on" for c in meta.get("controls", {})}
        return self.add_device(Device(name or obj, obj, state=dict(state), controls=dict(controls), looks=looks))

    def burners_from_meta(self, obj: str, on=()) -> dict:
        """The heating zones of a hob as devices, one per zone, from the asset's `meta["burners"]` (per zone: its
        `zone`, its `control`, the shapes that show that it is on, and which of the asset's appearances has them on
        and off). A device is called `<obj>/<zone name>` and has the state `on`; pressing the zone's control toggles
        it. `on`: the zones that are on at the start. Shapes of those appearances that belong to no single zone (the
        lamp that says the glass is hot) follow "any zone is on" (`SharedLook`)."""
        meta = self.world.objects[obj]["meta"]
        looks = meta["looks"]
        out, own = {}, set()
        for name, b in sorted(meta["burners"].items()):
            shapes = list(b["geoms"])
            own.update(shapes)
            out[name] = self.add_device(Device(f"{obj}/{name}", obj, state={"on": name in on}, controls={b["control"]: "on"},
                                               looks={"on=True": {g: looks[b["looks"]["on"]][g] for g in shapes},
                                                      "on=False": {g: looks[b["looks"]["off"]][g] for g in shapes}}))
        first = next(iter(sorted(meta["burners"].values(), key=lambda b: b["control"])))
        shared = sorted(g for g in looks[first["looks"]["off"]] if g not in own)
        if shared:
            self.monitors.append(SharedLook(obj, [d.name for d in out.values()], {g: looks[first["looks"]["on"]][g] for g in shared},
                                            {g: looks[first["looks"]["off"]][g] for g in shared}))
            self.monitors[-1].update(self)
        return out

    def add_vessel(self, v: Vessel) -> Vessel:
        self.vessels[v.obj] = v
        return v

    def vessel_from_meta(self, obj: str, contents: dict | None = None) -> Vessel:
        meta = self.world.objects[obj]["meta"]
        vm = meta.get("vessel") or {}
        sites = meta.get("sites", {})
        depth = float(vm.get("inner_depth", meta.get("height", meta.get("size", [0, 0, 0.1])[-1])))
        radius = float(vm.get("inner_radius", meta.get("radius", 0.03)))
        mouth = sites.get(vm.get("mouth_site", "mouth"))
        bottom = sites.get(vm.get("bottom_site", "bottom_in"))
        if mouth is None:
            top = float(meta.get("height", meta.get("size", [0, 0, 0.1])[-1]))
            mouth, bottom = (0.0, 0.0, top), (0.0, 0.0, top - depth)
        cap = float(vm.get("capacity_ml", math.pi * radius * radius * depth * 1e6))
        size = vm.get("inner_size")
        half = (float(size[0]) / 2.0, float(size[1]) / 2.0) if vm.get("shape") == "box" and size else None
        return self.add_vessel(Vessel(obj=obj, capacity_ml=cap, contents=dict(contents if contents is not None else meta.get("contents", {})),
                                      mouth=tuple(mouth), bottom=tuple(bottom if bottom is not None else (0.0, 0.0, 0.005)), radius=radius,
                                      closed=bool(vm.get("closed", False)), half=half))

    def add_cap(self, cap: str, vessel: str) -> Cap:
        """`cap` closes `vessel` when it is put on its mouth (see `Cap`)."""
        c = Cap(cap, vessel)
        self.monitors.append(c)
        self.caps[vessel] = cap
        return c

    def add_blade(self, tool: str, into, **kw):
        """The blade of `tool` goes into the soft objects `into` when the hand pushes it in, and stays in when let go
        of there (see `insert.Blade`; the scene pairs the tool with each of them under `fasteners`)."""
        from .insert import Blade
        m = Blade(tool, [into] if isinstance(into, str) else into, **kw)
        m.bind(self)
        self.monitors.append(m)
        self.inserts[tool] = m
        return m

    def add_plug(self, plug: str, sockets, **kw):
        """`plug` fits the sockets `sockets`: zone keys `<object>/<zone>`, or objects, meaning all their zones called
        `socket...` (see `insert.Plug`; the scene pairs the plug with each object under `fasteners`)."""
        from .insert import Plug
        keys = []
        for s in ([sockets] if isinstance(sockets, str) else sockets):
            if "/" in s:
                keys.append(s)
            else:
                keys += [f"{s}/{name}" for name in sorted(self.world.objects[s]["meta"].get("zones", {})) if name.startswith("socket")]
        m = Plug(plug, keys, **kw)
        m.bind(self)
        self.monitors.append(m)
        self.inserts[plug] = m
        return m

    def add_zone(self, z: Zone) -> Zone:
        self.zones[f"{z.obj}/{z.name}"] = z
        return z

    def zone(self, key: str) -> Zone:
        if key not in self.zones:
            obj, name = key.split("/", 1)
            self.zones[key] = Zone.of(self.world, obj, name)
        return self.zones[key]

    def add_rule(self, rule) -> None:
        self.rules.append(rule)

    # ---- devices -------------------------------------------------------------------------------------------------
    def _apply_look(self, dev: Device, key: str, value) -> None:
        look = dev.looks.get(f"{key}={value}")
        if look:
            for geom, rgba in sorted(look.items()):
                self.world.set_look(geom if "/" in geom else f"{dev.obj}/{geom}", rgba)

    def set_device(self, name: str, key: str, value, cause: str = "script") -> None:
        dev = self.devices[name]
        if dev.state.get(key) != value:
            dev.state[key] = value
            self._apply_look(dev, key, value)
            self.event("device", device=name, key=key, value=value, cause=cause)

    def set_door(self, obj: str, door: str, open_: bool) -> None:
        """Open or close a door of a generated asset through its actuator (asset metadata `doors`)."""
        d = self.world.objects[obj]["meta"]["doors"][door]
        self.world.set_ctrl(obj, d["actuator"], float(d["open"] if open_ else d["closed"]))
        self.event("door", obj=obj, door=door, open=bool(open_))

    def pressed(self, obj: str, control: str, cause: str = "robot") -> dict | None:
        """A control of an object was operated. Toggles the boolean state it belongs to."""
        for dev in self.devices.values():
            if dev.obj == obj and control in dev.controls:
                key = dev.controls[control]
                self.set_device(dev.name, key, not bool(dev.state.get(key)), cause=cause)
                return {"device": dev.name, key: dev.state[key]}
        self.event("press", obj=obj, control=control, cause=cause)
        return None

    # ---- reading the world -----------------------------------------------------------------------------------------
    @property
    def p(self) -> dict:
        if self._p_tick != self.world.tick:
            self._p = self.world.privileged()
            self._p_tick = self.world.tick
        return self._p

    @property
    def time(self) -> float:
        return self.world.time

    def pos(self, name: str) -> np.ndarray:
        """Position of an object, of `<object>/<site>`, or of the hand (`tcp`)."""
        if name == "tcp":
            return self.p["tcp"][0]
        if name in self.p["objects"]:
            return self.p["objects"][name]["pos"]
        return self.world.locate(name)[0]

    def centre(self, obj: str) -> np.ndarray:
        """The middle of an object's bounding box (its `size` in the meta), in the bench frame."""
        o = self.p["objects"][obj]
        meta = self.world.objects[obj]["meta"]
        if "bbox" in meta:                            # generated assets: the origin need not be under the middle
            lo, hi = meta["bbox"]
            return o["pos"] + tf.rotate(o["quat"], [(lo[k] + hi[k]) / 2.0 for k in range(3)])
        size = meta.get("size")
        if size is None:
            size = [0.0, 0.0, meta.get("height", 0.0)]
        return o["pos"] + tf.rotate(o["quat"], [0.0, 0.0, float(size[2]) / 2.0])

    def footprint(self, obj: str) -> list:
        """Points of an object's footprint (its bounding box seen from above, at the height of its middle), in the bench
        frame: the four corners and the middles of the four sides. A rectangle whose footprint comes within a distance
        of another is caught by these to within a few millimetres."""
        o = self.p["objects"][obj]
        meta = self.world.objects[obj]["meta"]
        if "bbox" in meta:
            lo, hi = meta["bbox"]
            zc = (float(lo[2]) + float(hi[2])) / 2.0
        else:
            size = meta.get("size", [0.0, 0.0, meta.get("height", 0.0)])
            sx, sy = float(size[0]), float(size[1])
            lo, hi, zc = (-sx / 2.0, -sy / 2.0), (sx / 2.0, sy / 2.0), float(size[2]) / 2.0 if len(size) > 2 else 0.0
        xs = (float(lo[0]), (float(lo[0]) + float(hi[0])) / 2.0, float(hi[0]))
        ys = (float(lo[1]), (float(lo[1]) + float(hi[1])) / 2.0, float(hi[1]))
        local = [(x, y) for x in xs for y in ys if not (x == xs[1] and y == ys[1])]
        return [o["pos"] + tf.rotate(o["quat"], [x, y, zc]) for x, y in local]

    def footprint_distance(self, obj: str, point) -> float:
        """Distance in the horizontal plane from a point to the footprint of an object (its bounding box seen from
        above); 0 when the point is over it."""
        o = self.p["objects"][obj]
        meta = self.world.objects[obj]["meta"]
        if "bbox" in meta:
            lo, hi = meta["bbox"]
        else:
            sx, sy = (float(v) for v in meta.get("size", [0.0, 0.0, 0.0])[:2])
            lo, hi = (-sx / 2.0, -sy / 2.0), (sx / 2.0, sy / 2.0)
        p = tf.compose(tf.inverse((o["pos"], o["quat"])), (np.asarray(point, dtype=np.float64), np.array([1.0, 0, 0, 0])))[0]
        dx = max(float(lo[0]) - p[0], 0.0, p[0] - float(hi[0]))
        dy = max(float(lo[1]) - p[1], 0.0, p[1] - float(hi[1]))
        return float(math.hypot(dx, dy))

    def tilt_deg(self, obj: str) -> float:
        return float(tf.tilt_deg(self.p["objects"][obj]["quat"]))

    def speed(self, obj: str) -> float:
        return float(np.linalg.norm(self.p["objects"][obj]["linvel"]))

    def contacts(self, a: str, b: str | None = None) -> list[dict]:
        return [c for c in self.p["contacts"] if (c["a"] == a and (b is None or c["b"] == b)) or (c["b"] == a and (b is None or c["a"] == b))]

    def select(self, who) -> list[str]:
        """Objects named by a selector: a name, {"tag": t}, {"names": [...]}, or "held"."""
        if who == "held":
            if self.world.held is None and not self.world.assist:          # no grasp assist: what both finger pads touch
                from robosafe.sim import skills
                return list(skills.held_objects(self.world)[:1])
            return [n for n in self.world.held_by.values() if n]
        if isinstance(who, str):
            return [who]
        if "tag" in who:
            return self.tagged(who["tag"])
        return list(who.get("names", []))

    # ---- events --------------------------------------------------------------------------------------------------
    def event(self, kind: str, **fields) -> dict:
        e = {"t": round(self.world.time, 4), "tick": self.world.tick, "kind": kind, **fields}
        self.events.append(e)
        return e

    def fire_once(self, key, kind: str, **fields) -> bool:
        if key in self._fired:
            return False
        self._fired.add(key)
        self.event(kind, **fields)
        return True

    def harms(self) -> list[dict]:
        return [e for e in self.events if e["kind"] == "hazard" and e.get("severity") == "harm"]

    def violations(self) -> list[dict]:
        return [e for e in self.events if e["kind"] == "hazard" and e.get("severity") == "violation"]

    # ---- per tick ------------------------------------------------------------------------------------------------
    def update(self) -> None:
        self._liquids()
        for m in self.monitors:
            m.update(self)
        for r in self.rules:
            r.update(self)
        for w in self.watchers:
            w.update(self)

    def finish(self) -> None:
        """Rules that are decided when the episode ends."""
        for r in self.rules:
            end = getattr(r, "at_end", None)
            if end is not None:
                end(self)

    def _liquids(self) -> None:
        """Pouring: a vessel tilted past the angle at which its contents reach the rim lets them out of the lowest
        point of the rim; what is below decides where they go."""
        for name in sorted(self.vessels):
            v = self.vessels[name]
            if v.closed or v.total() <= 0.0 or self.world.objects[name]["fixed"]:
                continue
            o = self.p["objects"][name]
            axis = tf.rotate(o["quat"], [0.0, 0.0, 1.0])
            tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(axis[2])))))
            fill = min(v.total() / max(v.capacity_ml, 1e-9), 1.0)
            onset = 30.0 + 60.0 * (1.0 - fill)          # a full vessel spills early, a nearly empty one near level
            if tilt <= onset:
                continue
            rate = min(8.0 * (tilt - onset), 250.0)     # ml per second
            amount = rate * CONTROL_DT
            if name in self.dose:                        # a measured pour: the hand turns back when that much is out
                amount = min(amount, self.dose[name])
                self.dose[name] -= amount
            out = v.take_fraction(amount) if amount > 0.0 else {}
            if not out:
                continue
            horiz = np.array([axis[0], axis[1], 0.0])
            horiz = tf.unit(horiz) if float(np.linalg.norm(horiz)) > 1e-9 else np.array([1.0, 0.0, 0.0])
            mouth = o["pos"] + tf.rotate(o["quat"], v.mouth)
            # the lowest point of the rim: mouth + r (h cos t - z sin t) for a tilt t towards the level direction h;
            # past 90 degrees cos t is negative and the point lies behind the middle of the mouth, not in front of it
            lip = mouth + horiz * v.radius * float(axis[2]) - np.array([0.0, 0.0, v.radius * math.sqrt(max(1.0 - axis[2] ** 2, 0.0))])
            self._land(name, lip, out)

    def _land(self, source: str, lip: np.ndarray, out: dict) -> None:
        target = None
        for other in sorted(self.vessels):
            if other == source:
                continue
            w = self.vessels[other]
            if w.closed:
                continue
            o = self.p["objects"][other]
            mouth = o["pos"] + tf.rotate(o["quat"], w.mouth)
            if mouth[2] <= lip[2] + 0.01 and math.hypot(lip[0] - mouth[0], lip[1] - mouth[1]) <= w.radius:
                if target is None or mouth[2] > target[1][2]:
                    target = (other, mouth)
        ml = float(sum(out.values()))
        if target is not None:
            w = self.vessels[target[0]]
            over = 0.0
            for sub, q in sorted(out.items()):
                over += w.add(sub, q)
            self._flow(source, "vessel", target[0], out, lip)
            self.redraw(target[0])
            self.redraw(source)
            if over > 1e-9:
                self._flow(target[0], "overflow", target[0], {"mixed": over}, target[1])
            return
        hit = self.world.raycast(lip, [0.0, 0.0, -1.0], exclude_robot=True)
        onto = hit["object"] if hit else "floor"
        # past the source's own walls: a vessel lying on its side is met twice by a ray from its lip (0.5.1: before, the
        # second wall took the liquid, and a knocked-over glass spilled into itself)
        for _ in range(4):
            if not (onto == source and hit):
                break
            hit2 = self.world.raycast(hit["point"] - np.array([0.0, 0.0, 0.002]), [0.0, 0.0, -1.0], exclude_robot=True)
            onto = hit2["object"] if hit2 else "floor"
            hit = hit2 or hit
        self._flow(source, "spill", onto, out, hit["point"] if hit else lip)

    def redraw(self, obj: str) -> None:
        """Draw a vessel's contents at their present level (generated vessels have a fill geom; others are skipped).
        A picture only."""
        from robosafe.assets import liquid as _liquid
        v = self.vessels.get(obj)
        if v is None or not _liquid.has_fill(self.world.model, obj):
            return
        meta = self.world.objects[obj]["meta"]
        depth = float((meta.get("vessel") or {}).get("inner_depth", 0.1))
        total = v.total()
        level = depth * 1e3 * min(total / max(v.capacity_ml, 1e-9), 1.0)
        rgba = None
        if total > 0:
            main = max(sorted(v.contents), key=lambda k: v.contents[k])
            rgba = liquid_colour(main)
        try:
            self.world.show_liquid(obj, level, rgba)
        except KeyError:              # a fill that is part of the body's picture and cannot be redrawn (closed bottles)
            pass

    def _flow(self, source: str, how: str, onto: str, out: dict, where) -> None:
        """Accumulate a stream into one record per (source, how, onto); the rules read `self.spills`."""
        for s in self.spills:
            if s["source"] == source and s["how"] == how and s["onto"] == onto:
                for sub, q in out.items():
                    s["ml"][sub] = s["ml"].get(sub, 0.0) + q
                s["t1"] = self.world.time
                return
        self.spills.append({"source": source, "how": how, "onto": onto, "ml": dict(out), "t0": self.world.time, "t1": self.world.time,
                            "tick": self.world.tick, "pos": [float(x) for x in where]})
        self.event("pour" if how == "vessel" else how, source=source, onto=onto, substances=sorted(out))

    def poured(self, source: str | None = None, onto: str | None = None, how: str | None = None) -> float:
        return float(sum(sum(s["ml"].values()) for s in self.spills
                         if (source is None or s["source"] == source) and (onto is None or s["onto"] == onto) and (how is None or s["how"] == how)))

    # ---- hashing -------------------------------------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {"devices": {k: self.devices[k].state for k in sorted(self.devices)},
                "vessels": {k: self.vessels[k].contents for k in sorted(self.vessels)},
                "closed": sorted(k for k, v in self.vessels.items() if v.closed),
                "tags": {k: sorted(v) for k, v in sorted(self.tags.items())},
                "vars": self.vars, "events": len(self.events), "spills": self.spills,
                "rules": [r.snapshot() for r in self.rules], "monitors": [m.snapshot() for m in self.monitors]}
