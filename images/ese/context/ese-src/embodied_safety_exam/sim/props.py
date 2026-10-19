"""Primitive props for the bench world, used until the asset generator provides the real ones.

The interface is one function: `build(kind, params) -> Prop`. A `Prop` is a stand-alone MJCF model with exactly one
top-level body (named `body`, in the prop's own frame, without a free joint) and a `meta` dict that tells the skills
and the hazard layer what they need to know about it. `embodied_safety_exam.sim.World` attaches the body under a prefix `<name>/`, so a prop
site `grip_0` of an object called `tube1` becomes `tube1/grip_0` in the world. A generated asset replaces a primitive
by providing the same two things: an MJCF file with one body, and the meta (kind `mjcf`).

Frames follow the labware convention of `docs/contracts/CONTRACTS.md` section 1: origin at the centre of the footprint
on the underside, `+z` up; for racks `+x` along increasing column number and `+y` towards row A. Lengths in metres.

Site names shared with the asset contract: `grip_<k>` (where a gripper may hold the prop) and, for vessels standing
in a rack, `hole_<NAME>` here against `well_<NAME>` there (both at the inside bottom centre).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

ROWS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass
class Prop:
    kind: str
    xml: str = ""                 # MJCF text; or
    path: str = ""                # an MJCF file (generated assets, which carry meshes)
    fixed: bool = False           # welded to the world unless the scene says otherwise
    meta: dict = field(default_factory=dict)


def _f(x: float) -> str:
    return f"{x:.6g}"


def _v(*xs: float) -> str:
    return " ".join(_f(x) for x in xs)


# Contact stiffness of every prop geom. MuJoCo's default (time constant 0.02 s) is so soft that a 20 g tube sinks
# 0.4 mm into what it stands on and can be pushed through a thin plate with a few newtons; 0.005 s is close to the
# stiffest the 2 ms physics step allows (the limit is twice the step) and matches the gripper's pads (0.004 s).
SOLREF = "0.005 1"
SOLIMP = "0.95 0.99 0.001 0.5 2"
# Tubes and racks are smooth plastic. MuJoCo takes the larger of the two coefficients in a contact, so the pair slides
# at 0.3 on each other while the rack still grips the table (0.8) and the gripper's pads grip the tube (0.7, the pads
# having priority).
PLASTIC = ' friction="0.3 0.003 0.0001"'


def _wrap(body: str, extra: str = "") -> str:
    return ("<mujoco>\n<compiler angle=\"radian\"/>\n"
            f"<default>\n<geom solref=\"{SOLREF}\" solimp=\"{SOLIMP}\"/>\n</default>\n"
            "<worldbody>\n<body name=\"body\">\n" + body + "</body>\n</worldbody>\n" + extra + "</mujoco>\n")


def _box(name, size, pos, rgba, mass=None, extra="") -> str:
    m = f' mass="{_f(mass)}"' if mass is not None else ""
    return f'<geom name="{name}" type="box" size="{_v(*size)}" pos="{_v(*pos)}" rgba="{rgba}"{m}{extra}/>\n'


def _site(name, pos, quat=(1, 0, 0, 0), size=0.002) -> str:
    return f'<site name="{name}" pos="{_v(*pos)}" quat="{_v(*quat)}" size="{_f(size)}" rgba="0 0 0 0" group="4"/>\n'


def hole_names(rows: int, cols: int) -> list[str]:
    return [f"{ROWS[r]}{c + 1}" for r in range(rows) for c in range(cols)]


# ---- tube rack ------------------------------------------------------------------------------------------------------
def tube_rack(rows: int = 2, cols: int = 4, pitch_x: float = 0.040, pitch_y: float = 0.075, hole_half: float = 0.0102,
              height: float = 0.052, base: float = 0.004, margin: float = 0.008, mass: float = 0.35,
              rgba: str = "0.20 0.42 0.62 1") -> Prop:
    """A block of square holes: a base plate and full-height bars between the holes, all boxes.

    `hole_half` is half the side of a hole; a hole is `height - base` deep.

    The rows are 75 mm apart for the gripper's sake. Only the last 20 mm of the 2F-85's fingers are slim; behind
    them the linkage is 100 to 135 mm wide across the closing direction whatever the opening, so a tube can be
    taken from above only if no equally tall neighbour stands within about 65 mm of it along the line the fingers
    close on. Across that line the gripper is 40 mm wide, hence the 40 mm between columns. Grasp with the fingers
    closing along the rack's y axis.
    """
    if not (0 < rows <= len(ROWS) and cols > 0):
        raise ValueError("rack needs at least one hole")
    if pitch_x <= 2 * hole_half or pitch_y <= 2 * hole_half:
        raise ValueError("holes overlap: pitch must exceed the hole width")
    lx = (cols - 1) * pitch_x + 2 * hole_half + 2 * margin
    ly = (rows - 1) * pitch_y + 2 * hole_half + 2 * margin
    n_geom = 1 + (rows + 1) + (cols + 1) * rows
    m_each = mass / n_geom
    wall_h = (height - base) / 2.0
    wall_z = base + wall_h
    g = [_box("base", (lx / 2, ly / 2, base / 2), (0, 0, base / 2), rgba, m_each, PLASTIC)]
    y0 = (rows - 1) * pitch_y / 2.0          # row A
    x0 = -(cols - 1) * pitch_x / 2.0         # column 1
    # bars along x: one above row A, one between each pair of rows, one below the last row
    edges_y = [ly / 2.0] + [y0 - r * pitch_y for r in range(rows)] + [-ly / 2.0]
    for i in range(rows + 1):
        top = edges_y[i] - (hole_half if i > 0 else 0.0)
        bot = edges_y[i + 1] + (hole_half if i < rows else 0.0)
        g.append(_box(f"bar_x{i}", (lx / 2, (top - bot) / 2, wall_h), (0, (top + bot) / 2, wall_z), rgba, m_each, PLASTIC))
    # bars along y, cut to the rows so that they do not overlap the bars along x
    edges_x = [-lx / 2.0] + [x0 + c * pitch_x for c in range(cols)] + [lx / 2.0]
    for r in range(rows):
        yc = y0 - r * pitch_y
        for i in range(cols + 1):
            lo = edges_x[i] + (hole_half if i > 0 else 0.0)
            hi = edges_x[i + 1] - (hole_half if i < cols else 0.0)
            g.append(_box(f"bar_y{r}_{i}", ((hi - lo) / 2, hole_half, wall_h), ((lo + hi) / 2, yc, wall_z), rgba, m_each,
                          PLASTIC))
    holes = {}
    for r in range(rows):
        for c in range(cols):
            name = f"{ROWS[r]}{c + 1}"
            xy = (x0 + c * pitch_x, y0 - r * pitch_y)
            holes[name] = [xy[0], xy[1], base]
            g.append(_site(f"hole_{name}", (xy[0], xy[1], base)))
    meta = {"size": [lx, ly, height], "mass": mass, "rows": rows, "cols": cols, "pitch": [pitch_x, pitch_y],
            "holes": holes, "hole_half": hole_half, "hole_depth": height - base}
    return Prop("tube_rack", _wrap("".join(g)), meta=meta)


# ---- capped tube ----------------------------------------------------------------------------------------------------
def tube(radius: float = 0.0085, length: float = 0.110, cap_radius: float = 0.0105, cap_height: float = 0.014,
         mass: float = 0.020, grip_below_top: float = 0.040, rgba: str = "0.85 0.90 0.95 0.9",
         cap_rgba: str = "0.90 0.45 0.10 1") -> Prop:
    """A capped tube: a capsule body (round bottom) and a cylinder cap centred on the top of the body.

    Frame: origin at the lowest point, `+z` along the axis towards the cap. `length` is that of the body; the cap
    adds half its height. `grip_0` sits on the axis, `grip_below_top` under the top of the body.
    """
    if length <= 2 * radius:
        raise ValueError("tube shorter than its diameter")
    half = length / 2.0 - radius
    total = length + cap_height / 2.0
    body = (f'<geom name="wall" type="capsule" size="{_v(radius, half)}" pos="{_v(0, 0, length / 2)}" rgba="{rgba}" '
            f'mass="{_f(mass * 0.8)}" condim="4"{PLASTIC}/>\n'
            f'<geom name="cap" type="cylinder" size="{_v(cap_radius, cap_height / 2)}" pos="{_v(0, 0, length)}" '
            f'rgba="{cap_rgba}" mass="{_f(mass * 0.2)}"{PLASTIC}/>\n'
            + _site("grip_0", (0, 0, length - grip_below_top)) + _site("bottom", (0, 0, 0)) + _site("top", (0, 0, total)))
    meta = {"radius": radius, "length": length, "total_length": total, "mass": mass, "cap_radius": cap_radius,
            "grips": {"grip_0": {"type": "top", "width": 2 * radius}},
            "vessel": {"shape": "cyl", "inner_radius": radius - 0.001, "inner_depth": length - 0.002,
                       "bottom_site": "bottom", "bottom_offset": 0.001, "closed": True}}
    return Prop("tube", _wrap(body), meta=meta)


# ---- beaker ---------------------------------------------------------------------------------------------------------
def beaker(radius: float = 0.032, height: float = 0.100, wall: float = 0.003, bottom: float = 0.004, sides: int = 16,
           mass: float = 0.150, rgba: str = "0.80 0.90 0.95 0.55") -> Prop:
    """An open cylindrical vessel: `sides` boxes in a ring on a square bottom plate.

    Frame: origin at the centre of the underside, `+z` up. `grip_0` on the axis at 60 % of the height (a side grasp).
    The walls stop half a millimetre above the underside so that only the plate rests on the table.
    """
    if sides < 6:
        raise ValueError("a ring needs at least 6 sides")
    half_w = radius * math.tan(math.pi / sides)
    rc = radius - wall / 2.0
    lift = 0.0005
    m_wall = mass * 0.7 / sides
    g = [_box("bottom", (radius * 0.70, radius * 0.70, bottom / 2), (0, 0, bottom / 2), rgba, mass * 0.3)]
    for i in range(sides):
        a = 2.0 * math.pi * i / sides
        quat = (math.cos(a / 2), 0.0, 0.0, math.sin(a / 2))
        g.append(f'<geom name="wall_{i}" type="box" size="{_v(wall / 2, half_w, (height - lift) / 2)}" '
                 f'pos="{_v(rc * math.cos(a), rc * math.sin(a), (height + lift) / 2)}" quat="{_v(*quat)}" rgba="{rgba}" '
                 f'mass="{_f(m_wall)}"/>\n')
    g.append(f'<geom name="disc" type="cylinder" size="{_v(radius - wall, bottom / 2)}" pos="{_v(0, 0, bottom / 2)}" '
             f'rgba="{rgba}" contype="0" conaffinity="0" mass="0"/>\n')
    g += [_site("grip_0", (0, 0, 0.6 * height)), _site("rim", (0, 0, height)), _site("inside_bottom", (0, 0, bottom))]
    meta = {"radius": radius, "height": height, "mass": mass,
            "grips": {"grip_0": {"type": "side", "width": 2 * radius}},
            "vessel": {"shape": "cyl", "inner_radius": radius - wall, "inner_depth": height - bottom,
                       "bottom_site": "inside_bottom", "bottom_offset": 0.0, "closed": False}}
    return Prop("beaker", _wrap("".join(g)), meta=meta)


# ---- block ----------------------------------------------------------------------------------------------------------
def block(size=(0.04, 0.04, 0.04), mass: float = 0.05, friction: float = 1.0, rgba: str = "0.75 0.25 0.20 1") -> Prop:
    sx, sy, sz = (float(s) for s in size)
    body = (_box("box", (sx / 2, sy / 2, sz / 2), (0, 0, sz / 2), rgba, mass, f' friction="{_v(friction, 0.005, 0.0001)}"')
            + _site("grip_0", (0, 0, sz / 2)) + _site("top", (0, 0, sz)))
    return Prop("block", _wrap(body), meta={"size": [sx, sy, sz], "mass": mass,
                                             "grips": {"grip_0": {"type": "top", "width": sy}}})


# ---- scripted floor appliance (future-family asset) ------------------------------------------------------------------
def robot_vacuum(radius: float = 0.175, height: float = 0.095, mass: float = 3.4,
                 rgba: str = "0.18 0.20 0.22 1") -> Prop:
    """A generic vacuum with a circular bumper and floor-contacting wheels.

    Dimensions are chosen for the prototype, rather than copied from a commercial model. It is a rigid obstacle:
    a scene may move it with the deterministic mocap mover; this prop does not model a vacuum's drive controller.
    Its underside origin lies on the floor, +x faces the front sensor, and all decorative parts have zero mass.
    """
    radius, height, mass = float(radius), float(height), float(mass)
    if not all(math.isfinite(v) for v in (radius, height, mass)) or radius <= 0.10 or height <= 0.06 or mass <= 0.0:
        raise ValueError("a vacuum needs finite radius > 0.10 m, height > 0.06 m and positive mass")
    wheel_r, wheel_half_width = 0.026, 0.012
    wheel_y = radius - 0.04
    shell_bottom = 0.026
    shell_half_height = (height - shell_bottom) / 2.0
    body = (
        f'<geom name="shell" type="cylinder" size="{_v(radius - 0.006, shell_half_height)}" '
        f'pos="{_v(0, 0, shell_bottom + shell_half_height)}" rgba="{rgba}" mass="{_f(mass * 0.92)}"/>\n'
        f'<geom name="bumper" type="cylinder" size="{_v(radius, 0.013)}" pos="0 0 0.031" '
        f'rgba="0.06 0.065 0.07 1" mass="{_f(mass * 0.04)}"/>\n'
    )
    for side, y in (("left", wheel_y), ("right", -wheel_y)):
        body += (
            f'<geom name="wheel_{side}" type="cylinder" size="{_v(wheel_r, wheel_half_width)}" '
            f'pos="{_v(-0.04, y, wheel_r)}" quat="0.7071067812 0.7071067812 0 0" '
            f'rgba="0.025 0.025 0.025 1" friction="0.8 0.003 0.0001" mass="{_f(mass * 0.02)}"/>\n'
        )
    body += ('<geom name="caster" type="sphere" size="0.012" pos="0.11 0 0.012" '
             'rgba="0.025 0.025 0.025 1" mass="0" friction="0.5 0.003 0.0001"/>\n')
    visual = ' mass="0" contype="0" conaffinity="0" group="2"'
    body += (
        f'<geom name="lid" type="cylinder" size="{_v(radius - 0.014, 0.004)}" '
        f'pos="{_v(0, 0, height + 0.004)}" rgba="0.32 0.35 0.38 1"{visual}/>\n'
        f'<geom name="scanner" type="cylinder" size="0.035 0.010" '
        f'pos="{_v(-0.025, 0, height + 0.018)}" rgba="0.08 0.12 0.16 1"{visual}/>\n'
        + _box("front_sensor", (0.003, 0.040, 0.009), (radius - 0.006, 0, 0.052), "0.02 0.06 0.10 1", 0,
               ' contype="0" conaffinity="0" group="2"')
        + _site("front", (radius, 0, 0.05)) + _site("top", (0, 0, height + 0.028))
    )
    return Prop("robot_vacuum", _wrap(body), meta={
        "size": [2 * radius, 2 * radius, height + 0.028], "mass": mass,
        "tags": ["machine", "vacuum", "mobile"], "grips": {},
        "footprint": [[radius * math.cos(i * math.pi / 8), radius * math.sin(i * math.pi / 8)] for i in range(16)],
        "prototype": True, "motion": "scripted rigid obstacle; no drive controller",
    })


# ---- smoke ----------------------------------------------------------------------------------------------------------
def smoke(height: float = 0.28, radius: float = 0.06, puffs: int = 6, rgba: str = "0.26 0.26 0.28 0.62") -> Prop:
    """Smoke rising from something: translucent grey puffs that widen towards the top. A picture only: nothing
    collides with it, it is fixed where it is put, and it is invisible until its look `on` is applied (a device made
    with `State.device_from_meta(name, on=False)` and switched by the script)."""
    height, radius, puffs = float(height), float(radius), int(puffs)
    r, g, b, a = (float(v) for v in rgba.split())
    body, on, off = "", {}, {}
    for i in range(puffs):
        f = (i + 0.5) / puffs
        rad = radius * (0.45 + 0.75 * f)
        x = radius * 0.35 * math.sin(2.4 * i)
        y = radius * 0.30 * math.cos(1.7 * i + 0.5)
        shade = 1.0 + 0.5 * f                                # lighter and thinner as it rises
        col = [min(r * shade, 1.0), min(g * shade, 1.0), min(b * shade, 1.0)]
        body += (f'<geom name="puff_{i}" type="ellipsoid" size="{_v(rad, rad, rad * 0.8)}" pos="{_v(x, y, f * height)}" '
                 f'rgba="{_v(*col, 0.0)}" contype="0" conaffinity="0" mass="0.0001" group="2"/>\n')
        on[f"puff_{i}"] = col + [a * (1.0 - 0.45 * f)]
        off[f"puff_{i}"] = col + [0.0]
    body += _site("top", (0, 0, height))
    return Prop("smoke", _wrap(body), fixed=True, meta={"size": [2.4 * radius, 2.4 * radius, height + radius], "mass": 0.0006,
                                                        "tags": ["smoke"], "looks": {"on": on, "off": off}, "visual_only": True})


# ---- push button ----------------------------------------------------------------------------------------------------
def button(travel: float = 0.008, stiffness: float = 300.0, size: float = 0.030, base_height: float = 0.020,
           key_mass: float = 0.02, rgba: str = "0.80 0.10 0.10 1") -> Prop:
    """A sprung push button on a housing. The joint `press` is 0 when released and `-travel` when fully pressed.

    Site `top` is the centre of the key top with `+z` out of the button. The spring carries the key's weight at
    position 0 (when the button stands upright), so pressing by d metres takes `stiffness * d` newtons; the joint
    stops at `-travel`.
    """
    key_h = 0.012
    ref = key_mass * 9.81 / stiffness
    body = (_box("housing", (size * 0.8, size * 0.8, base_height / 2), (0, 0, base_height / 2), "0.25 0.25 0.28 1", 0.2)
            + f'<body name="key" pos="{_v(0, 0, base_height + travel)}">\n'
            f'<joint name="press" type="slide" axis="0 0 1" range="{_v(-travel, 0.002)}" limited="true" '
            f'stiffness="{_f(stiffness)}" springref="{_f(ref)}" damping="2" armature="0.002"/>\n'
            + _box("key", (size / 2, size / 2, key_h / 2), (0, 0, key_h / 2), rgba, key_mass)
            + _site("top", (0, 0, key_h)) + "</body>\n")
    meta = {"travel": travel, "stiffness": stiffness, "joint": "press", "site": "top",
            "full_press_force": stiffness * travel}
    return Prop("button", _wrap(body), fixed=True, meta=meta)


# ---- hanging spring-mass --------------------------------------------------------------------------------------------
def spring_mass(mass: float = 0.100, stiffness: float = 20.0, damping: float = 0.0, height: float = 0.40,
                reach: float = 0.12, rest_length: float = 0.10, rgba: str = "0.85 0.70 0.10 1") -> Prop:
    """A stand with a mass hanging from a spring. The mass moves on a vertical slide joint `spring`.

    Joint position 0 is the unstretched spring; the mass hangs at `-mass * g / stiffness` in equilibrium. A tendon
    draws the spring; the force comes from the joint, so the period is exactly that of a linear spring.
    """
    post = "0.35 0.35 0.38 1"
    r_bob = 0.018
    body = (_box("foot", (0.07, 0.07, 0.006), (0, 0, 0.006), post, 1.5)
            + _box("post", (0.006, 0.006, height / 2), (-0.05, 0, height / 2), post, 0.3)
            + _box("arm", ((reach + 0.05) / 2, 0.006, 0.006), ((reach - 0.05) / 2, 0, height), post, 0.1)
            + _site("hook", (reach, 0, height - 0.006))
            + f'<body name="bob" pos="{_v(reach, 0, height - 0.006 - rest_length - r_bob)}">\n'
            f'<joint name="spring" type="slide" axis="0 0 1" stiffness="{_f(stiffness)}" damping="{_f(damping)}"/>\n'
            f'<geom name="bob" type="sphere" size="{_f(r_bob)}" rgba="{rgba}" mass="{_f(mass)}"/>\n'
            + _site("bob_top", (0, 0, r_bob)) + _site("bob", (0, 0, 0)) + "</body>\n")
    extra = ('<tendon>\n<spatial name="spring" width="0.002" rgba="0.6 0.6 0.65 1">\n<site site="hook"/>\n'
             '<site site="bob_top"/>\n</spatial>\n</tendon>\n')
    meta = {"mass": mass, "stiffness": stiffness, "damping": damping, "joint": "spring",
            "period": 2.0 * math.pi * math.sqrt(mass / stiffness)}
    return Prop("spring_mass", _wrap(body, extra), fixed=True, meta=meta)


# ---- pendulum -------------------------------------------------------------------------------------------------------
def pendulum(length: float = 0.25, bob_mass: float = 0.100, bob_radius: float = 0.015, height: float = 0.40,
             reach: float = 0.12, damping: float = 0.0, rgba: str = "0.15 0.55 0.30 1") -> Prop:
    """A stand with a bob on a light rod, swinging in the prop's xz plane about the hinge `swing` (0 = hanging)."""
    post = "0.35 0.35 0.38 1"
    rod_mass = 0.002
    body = (_box("foot", (0.07, 0.07, 0.006), (0, 0, 0.006), post, 1.5)
            + _box("post", (0.006, 0.006, height / 2), (-0.05, 0, height / 2), post, 0.3)
            + _box("arm", ((reach + 0.05) / 2, 0.006, 0.006), ((reach - 0.05) / 2, 0, height), post, 0.1)
            + f'<body name="rod" pos="{_v(reach, 0, height - 0.006)}">\n'
            f'<joint name="swing" type="hinge" axis="0 1 0" damping="{_f(damping)}"/>\n'
            f'<geom name="rod" type="capsule" size="0.0015" fromto="{_v(0, 0, 0, 0, 0, -length)}" rgba="{post}" '
            f'mass="{_f(rod_mass)}" contype="0" conaffinity="0"/>\n'
            f'<geom name="bob" type="sphere" size="{_f(bob_radius)}" pos="{_v(0, 0, -length)}" rgba="{rgba}" '
            f'mass="{_f(bob_mass)}"/>\n' + _site("bob", (0, 0, -length)) + "</body>\n")
    # small-angle period of the compound pendulum (point-like rod of uniform mass, solid sphere bob)
    inertia = bob_mass * length ** 2 + 0.4 * bob_mass * bob_radius ** 2 + rod_mass * length ** 2 / 3.0
    torque = (bob_mass * length + rod_mass * length / 2.0) * 9.81
    meta = {"length": length, "bob_mass": bob_mass, "joint": "swing", "period": 2.0 * math.pi * math.sqrt(inertia / torque)}
    return Prop("pendulum", _wrap(body), fixed=True, meta=meta)


# ---- incline --------------------------------------------------------------------------------------------------------
def incline(angle_deg: float = 20.0, length: float = 0.30, width: float = 0.12, friction: float = 0.3,
            start_from_top: float = 0.05, gates=(0.08, 0.20), stop: bool = True, rgba: str = "0.55 0.50 0.42 1") -> Prop:
    """A ramp rising along `+x`: a slab whose top face makes `angle_deg` with the table, on a wedge of supports.

    Sites, all on the face with `+x` pointing up the slope and `+z` along the face normal: `ramp_bottom` and
    `ramp_top` at the two ends; `start`, `start_from_top` below the upper end, where a block is set down to be
    released; `gate_<k>`, `gates[k]` metres further down the slope than `start`, for light gates (plane normal: the
    site's x axis, so a block sliding down crosses with direction -1). With `stop` a low bar across the lower end
    catches the block. The friction a block feels is the larger of the ramp's and its own coefficient.
    """
    a = math.radians(angle_deg)
    t = 0.006
    c, s = math.cos(a), math.sin(a)
    # the slab's lower edge touches the table at x = 0; its centre is half its length up the slope
    cx, cz = (length / 2) * c - (t / 2) * s, (length / 2) * s + (t / 2) * c
    quat = (math.cos(-a / 2), 0.0, math.sin(-a / 2), 0.0)       # rotation about y by -a: +x tilts upwards
    fr = f' friction="{_v(friction, 0.005, 0.0001)}"'
    body = (f'<geom name="slab" type="box" size="{_v(length / 2, width / 2, t / 2)}" pos="{_v(cx, 0, cz)}" '
            f'quat="{_v(*quat)}" rgba="{rgba}" mass="0.4"{fr}/>\n')
    hx = length * c
    for k, frac in enumerate((0.5, 0.97)):
        h = frac * length * s
        if h > 0.004:
            body += _box(f"support_{k}", (0.005, width / 2, h / 2), (frac * hx, 0, h / 2), rgba, 0.1)

    def on_face(d: float, lift: float = 0.0):
        """Point on the face d metres up the slope from its lower end, `lift` above it."""
        return (d * c - (t + lift) * s, 0.0, d * s + (t + lift) * c)

    if stop:
        bar = 0.020
        body += (f'<geom name="stop" type="box" size="{_v(0.004, width / 2, bar / 2)}" pos="{_v(*on_face(0.004, bar / 2))}" '
                 f'quat="{_v(*quat)}" rgba="0.30 0.28 0.25 1" mass="0.02"{fr}/>\n')
    start_d = length - start_from_top
    body += _site("ramp_top", on_face(length), quat) + _site("ramp_bottom", on_face(0.0), quat)
    body += _site("start", on_face(start_d), quat)
    gate_list = [float(g) for g in gates]
    for k, g in enumerate(gate_list):
        if not 0.0 < g < start_d:
            raise ValueError("a gate must lie between the start and the lower end of the ramp")
        body += _site(f"gate_{k}", on_face(start_d - g), quat)
    meta = {"angle_deg": angle_deg, "length": length, "friction": friction, "face_thickness": t, "gates": gate_list,
            "start_from_top": start_from_top}
    return Prop("incline", _wrap(body), fixed=True, meta=meta)


# ---- a set of masses ----------------------------------------------------------------------------------------------------
def mass_block(mass: float = 0.100, size=(0.030, 0.030, 0.040), friction: float = 0.6, rgba: str | None = None) -> Prop:
    """A block of a given mass for a balance: 30 x 30 mm footprint, 40 mm tall whatever it weighs, so that the gripper
    takes every one of a set the same way and they stack or stand side by side.

    `grip_0` is 12 mm below the top (a top grasp: the fingertips, which reach 18 mm past the pinch point, stay
    10 mm above whatever the block stands on). Site `top` is where the next block of a stack goes.
    """
    sx, sy, sz = (float(v) for v in size)
    if sz < 0.032:
        raise ValueError("a mass block lower than 32 mm cannot be taken from above without the fingertips touching down")
    if rgba is None:        # heavier is darker
        shade = max(0.25, 0.85 - 0.6 * min(mass / 0.2, 1.0))
        rgba = f"{_f(shade)} {_f(shade * 0.9)} {_f(shade * 0.55)} 1"
    body = (_box("box", (sx / 2, sy / 2, sz / 2), (0, 0, sz / 2), rgba, mass, f' friction="{_v(friction, 0.005, 0.0001)}"')
            + _site("grip_0", (0, 0, sz - 0.012)) + _site("top", (0, 0, sz)))
    return Prop("mass_block", _wrap(body), meta={"size": [sx, sy, sz], "mass": mass,
                                                  "grips": {"grip_0": {"type": "top", "width": sy}}})


# ---- spring balance -----------------------------------------------------------------------------------------------------
def spring_balance(stiffness: float = 60.0, damping: float = 0.3, pan_size=(0.20, 0.09), pan_mass: float = 0.050,
                   height: float = 0.140, travel: float = 0.090, slots: int = 5, rgba: str = "0.80 0.82 0.85 1") -> Prop:
    """A pan standing on a spring: it sinks by m g / stiffness under a mass m, and a pointer shows how far.

    The pan is a plate on a vertical slide joint `spring` (negative = down, limited at `-travel` and at +30 mm) with
    a linear spring and viscous damping; it stays level wherever the load stands. Sites: `pan` (centre of the pan's
    top face), `slot_<k>` (places for mass blocks along x, 40 mm apart), `pointer` (on the pan, at its `-x` end) and
    `scale_zero` (on the housing, where the pointer is with the pan empty under a gravity of 9.81 m/s^2). The
    measured quantity is the height of `pointer` above `scale_zero`: with mass M on the pan and gravity g it is
    `-M g / stiffness + pan_mass (9.81 - g) / stiffness`, so 0 for the empty pan on Earth and a little above the
    zero mark for the empty pan where gravity is weaker. It oscillates with period
    2 pi sqrt((M + pan_mass) / stiffness).
    """
    px, py = (float(v) for v in pan_size)
    th = 0.006
    if travel >= height - th - 0.02:
        raise ValueError("the pan needs room under it: height must exceed travel by 26 mm")
    if not 1 <= slots <= int(px / 0.04):
        raise ValueError("slots are 40 mm apart and have to fit on the pan")
    dark = "0.25 0.26 0.30 1"
    ref = pan_mass * 9.81 / stiffness
    col_h = height - th - travel - 0.004
    g = [_box("foot", (px / 2 + 0.02, py / 2 + 0.01, 0.006), (0, 0, 0.006), dark, 1.0),
         _box("column", (0.02, 0.02, (col_h - 0.012) / 2), (0, 0, 0.012 + (col_h - 0.012) / 2), dark, 0.3)]
    # a scale plate at the -x end, never higher than the empty pan, with a mark every 10 mm
    sx = -(px / 2 + 0.014)
    g.append(_box("scale", (0.002, 0.02, (height - 0.012) / 2), (sx, 0, 0.012 + (height - 0.012) / 2), "0.95 0.95 0.92 1", 0.05))
    for k in range(int(travel / 0.01) + 1):
        g.append(f'<geom name="mark_{k}" type="box" size="{_v(0.0005, 0.012 if k % 5 == 0 else 0.007, 0.0006)}" '
                 f'pos="{_v(sx + 0.0022, 0, height - k * 0.01)}" rgba="0.1 0.1 0.1 1" contype="0" conaffinity="0" mass="0"/>\n')
    g.append(_site("scale_zero", (sx + 0.003, 0, height)))
    pan = (f'<body name="pan" pos="{_v(0, 0, height)}">\n'
           f'<joint name="spring" type="slide" axis="0 0 1" range="{_v(-travel, 0.030)}" limited="true" '
           f'stiffness="{_f(stiffness)}" springref="{_f(ref)}" damping="{_f(damping)}"/>\n'
           + _box("plate", (px / 2, py / 2, th / 2), (0, 0, -th / 2), rgba, pan_mass, ' friction="0.6 0.005 0.0001"')
           + f'<geom name="stem" type="box" size="{_v(0.006, 0.006, (travel + 0.01) / 2)}" pos="{_v(0, 0, -th - (travel + 0.01) / 2)}" '
           f'rgba="{dark}" contype="0" conaffinity="0" mass="0"/>\n'
           f'<geom name="needle" type="box" size="{_v(0.006, 0.002, 0.001)}" pos="{_v(-(px / 2 + 0.006), 0, -0.001)}" '
           f'rgba="0.85 0.10 0.10 1" contype="0" conaffinity="0" mass="0"/>\n'
           + _site("pan", (0, 0, 0)) + _site("pointer", (sx + 0.003, 0, 0)))
    xs = [(k - (slots - 1) / 2.0) * 0.04 for k in range(slots)]
    for k, x in enumerate(xs):
        pan += _site(f"slot_{k}", (x, 0, 0))
    pan += "</body>\n"
    meta = {"stiffness": stiffness, "damping": damping, "pan_mass": pan_mass, "joint": "spring", "travel": travel,
            "pan_size": [px, py], "slots": [[x, 0.0, 0.0] for x in xs], "height": height}
    return Prop("spring_balance", _wrap("".join(g) + pan), fixed=True, meta=meta)


# ---- pendulums for the gripper --------------------------------------------------------------------------------------------
def pendulum_rig(lengths=(0.15, 0.25, 0.35), bob_mass: float = 0.100, bob_size: float = 0.030, height: float = 0.52,
                 spacing: float = 0.11, damping: float = 1.0e-5, rgba: str = "0.15 0.55 0.30 1") -> Prop:
    """A frame with one pendulum per entry of `lengths` (pivot to centre of the bob), hanging side by side.

    The beam runs along the rig's y axis and the pendulums swing in the x-z plane, each on a hinge `swing_<k>`
    (0 = hanging; positive turns the bob towards `-x`). A bob is a cube that the gripper takes from `+x` or `-x` with
    its fingers closing along the beam, on the faces that do not lead the swing; opening them lets the bob go without
    pushing it. Sites: `pivot_<k>` (on the frame; its y axis is the hinge axis), `bob_<k>` and `grip_<k>` (centre of
    the bob, moving with it; z along the rod). `meta["pendulums"][k]` has length and the small-angle period of the
    compound pendulum (rod of 2 g, cube bob).
    """
    lens = [float(v) for v in lengths]
    if not lens or min(lens) < 0.08 or max(lens) > height - 0.09:
        raise ValueError("lengths between 0.08 m and the height of the beam less 0.09 m (room for a side grasp)")
    n = len(lens)
    post = "0.35 0.35 0.38 1"
    rod_mass, beam = 0.002, 0.008
    ys = [(k - (n - 1) / 2.0) * spacing for k in range(n)]
    half = max(abs(ys[0]), 0.0) + 0.10
    g = []
    for sgn, name in ((-1.0, "a"), (1.0, "b")):
        g.append(_box(f"foot_{name}", (0.12, 0.02, 0.006), (0, sgn * half, 0.006), post, 1.0))
        g.append(_box(f"post_{name}", (0.008, 0.008, (height - 0.012) / 2), (0, sgn * half, 0.012 + (height - 0.012) / 2), post, 0.3))
    g.append(_box("beam", (beam, half + 0.008, beam), (0, 0, height + beam), post, 0.2))
    pend = []
    for k, (y, length) in enumerate(zip(ys, lens)):
        g.append(_site(f"pivot_{k}", (0, y, height)))
        g.append(f'<body name="bob_{k}" pos="{_v(0, y, height)}">\n'
                 f'<joint name="swing_{k}" type="hinge" axis="0 1 0" damping="{_f(damping)}"/>\n'
                 f'<geom name="rod_{k}" type="capsule" size="0.0012" fromto="{_v(0, 0, 0, 0, 0, -length)}" rgba="{post}" '
                 f'mass="{_f(rod_mass)}" contype="0" conaffinity="0"/>\n'
                 + _box(f"bob_{k}", (bob_size / 2, bob_size / 2, bob_size / 2), (0, 0, -length), rgba, bob_mass,
                        ' friction="0.6 0.005 0.0001"')
                 + _site(f"bob_{k}", (0, 0, -length)) + _site(f"grip_{k}", (0, 0, -length)) + "</body>\n")
        inertia = bob_mass * (length ** 2 + bob_size ** 2 / 6.0) + rod_mass * length ** 2 / 3.0
        arm = bob_mass * length + rod_mass * length / 2.0          # times g: the restoring torque per radian
        pend.append({"length": length, "joint": f"swing_{k}", "pivot": f"pivot_{k}", "grip": f"grip_{k}", "bob": f"bob_{k}",
                     "inertia": inertia, "moment_arm": arm, "period": 2.0 * math.pi * math.sqrt(inertia / (arm * 9.81))})
    meta = {"pendulums": pend, "bob_mass": bob_mass, "bob_size": bob_size, "height": height,
            "grips": {f"grip_{k}": {"type": "side", "width": bob_size} for k in range(n)}}
    return Prop("pendulum_rig", _wrap("".join(g)), fixed=True, meta=meta)


# ---- generated assets ------------------------------------------------------------------------------------------------
# How far the fingertips of the 2F-85 reach past the pinch point, against the distance between the pads (m). The
# pads swing back as the fingers open: 18 mm at a narrow grip, 5 mm fully open. Measured on the vendored model.
_TIP_REACH = ((0.0004, 0.0177), (0.0209, 0.0176), (0.0440, 0.0153), (0.0657, 0.0109), (0.0852, 0.0046))
MAX_GRIP_WIDTH = 0.0852
SIDE_GRASP_MIN_HEIGHT = 0.045      # m: a level gripper needs this much under its axis


def fingertip_reach(width: float) -> float:
    xs, ys = [w for w, _ in _TIP_REACH], [r for _, r in _TIP_REACH]
    if width <= xs[0]:
        return ys[0]
    for (x0, y0), (x1, y1) in zip(_TIP_REACH, _TIP_REACH[1:]):
        if width <= x1:
            return y0 + (y1 - y0) * (width - x0) / (x1 - x0)
    return ys[-1]


_ASSET_DIR = None


def _asset_files(asset_id: str) -> tuple[str, dict]:
    """Build a generated asset once per process (the generator writes the same bytes every time)."""
    global _ASSET_DIR
    import atexit
    import shutil
    import tempfile
    from pathlib import Path

    from embodied_safety_exam import assets as _assets        # only when a scene asks for a generated asset

    if _ASSET_DIR is None:
        _ASSET_DIR = tempfile.mkdtemp(prefix="rsb_sim_assets_")
        atexit.register(shutil.rmtree, _ASSET_DIR, True)
    out = Path(_ASSET_DIR) / asset_id
    if asset_id in _assets.labware_ids():
        meta = _assets.build_labware(asset_id, _ASSET_DIR)
    elif asset_id in _assets.item_ids():
        meta = _assets.build_item(asset_id, _ASSET_DIR)
    elif asset_id in _assets.instrument_ids():
        meta = _assets.build_instrument(asset_id, _ASSET_DIR)
    else:
        raise KeyError(f"unknown asset id {asset_id!r}")
    return str(out / f"{asset_id}.xml"), meta


def _top_grip(pos, width: float, top: float, closing_axis=None) -> tuple[dict | None, str]:
    """A grasp from above at `pos` (object frame), raised if need be so that the fingertips stay 2 mm clear of what the
    object stands on. Returns (entry, "") or (None, why)."""
    if width > MAX_GRIP_WIDTH - 0.002:
        return None, f"{width * 1e3:.1f} mm is wider than the gripper opens (85 mm less 1 mm of play on each side)"
    need = fingertip_reach(width) + 0.002
    z = max(float(pos[2]), need)
    if z > top - 0.003:
        return None, (f"too low to take from above: at {width * 1e3:.0f} mm between the pads the fingertips reach "
                      f"{fingertip_reach(width) * 1e3:.0f} mm past the pinch point and the top is {top * 1e3:.0f} mm up")
    entry = {"type": "top", "width": width, "pos": [float(pos[0]), float(pos[1]), z], "quat": [1.0, 0.0, 0.0, 0.0]}
    if closing_axis is not None:
        ax = float(closing_axis[0]), float(closing_axis[1])
        yaw = math.atan2(ax[1], ax[0]) - math.pi / 2.0            # the frame whose y axis is the closing direction
        entry["quat"] = [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]
    return entry, ""


def asset(id: str, fixed: bool | None = None) -> Prop:
    """A generated asset (`embodied_safety_exam.assets`) as a prop: its MJCF file, and the grip and vessel metadata `embodied_safety_exam.sim` works with,
    read from its `meta.json`.

    What is taken from the meta data (millimetres there, metres here):
    - `grasp` (`center_mm`, `closing_axis`, `width_mm`) of a vessel becomes the side grasp `grip_0`, at the centre,
      with the vessel's z as its axis; of anything else, a grasp from above closing along that axis;
    - entries of `grips` with a `closing_axis` (labware) or `radial` (tubes, masses) become grasps from above under
      their own names;
    - `inner` (`shape`, `radius_mm` or `size_mm`, `depth_mm`) with the sites `bottom`, `mouth` and `spout` becomes
      `meta["vessel"]`.
    A grasp from above is raised until the fingertips clear the surface the object stands on; if that leaves less
    than 3 mm of the object between the pads, or the object is wider than the gripper opens, the grasp is left out
    and `meta["ungraspable"][name]` says why. Instruments are fixed, the rest is free.
    """
    path, src = _asset_files(id)
    top = float(src["size_m"][2]) if "bbox_m" not in src else float(src["bbox_m"][1][2])
    grips: dict = {}
    refused: dict = {}
    is_vessel = src.get("kind") == "vessel" and "inner" in src
    if "grasp" in src:
        g = src["grasp"]
        centre = [v * 1e-3 for v in g["center_mm"]]
        width = g["width_mm"] * 1e-3
        if is_vessel:
            if width > MAX_GRIP_WIDTH - 0.002:
                refused["grip_0"] = f"{width * 1e3:.1f} mm is wider than the gripper opens"
            else:
                grips["grip_0"] = {"type": "side", "width": width, "pos": centre, "quat": [1.0, 0.0, 0.0, 0.0],
                                   "closing_axis": [float(v) for v in g["closing_axis"]]}
                if centre[2] < SIDE_GRASP_MIN_HEIGHT:
                    refused["grip_0:on_a_table"] = (f"the grasp centre is {centre[2] * 1e3:.0f} mm up; a level gripper needs "
                                                    f"{SIDE_GRASP_MIN_HEIGHT * 1e3:.0f} mm under its axis")
        else:
            entry, why = _top_grip(centre, width, top, g["closing_axis"])
            if entry is None:
                refused["grip_0"] = why
            else:
                grips["grip_0"] = entry
    else:
        for g in src.get("grips", []) if isinstance(src.get("grips"), list) else []:
            if g.get("body") not in (None, id):
                continue                                      # on a moving part (a cap): not a way to carry the whole
            pos = [v * 1e-3 for v in g["pos_mm"]]
            if "width_mm" not in g:
                continue
            # the meta data does not say over what height the object has this width; a mass is a cylinder with the
            # grip at half its height and a wire hook above, so its top for this purpose is twice the grip height
            band_top = min(top, 2.0 * pos[2]) if src.get("kind") == "mass" else top
            entry, why = _top_grip(pos, g["width_mm"] * 1e-3, band_top, g.get("closing_axis"))
            if entry is None:
                refused[g["name"]] = why
            else:
                grips[g["name"]] = entry
    meta = {"asset": id, "class": src.get("class"), "asset_kind": src.get("kind"), "size": [float(v) for v in src["size_m"]],
            "mass": float(src["mass_kg"]), "grips": grips, "ungraspable": refused}
    if is_vessel:
        inner = src["inner"]
        radius = inner["radius_mm"] * 1e-3 if inner.get("shape") == "cyl" else min(inner["size_mm"]) * 0.5e-3
        meta["vessel"] = {"shape": inner.get("shape"), "inner_radius": radius, "inner_depth": inner["depth_mm"] * 1e-3,
                          "bottom_site": "bottom", "bottom_offset": 0.0, "rim_site": "mouth",
                          "closed": any(j.get("role") == "cap" for j in src.get("joints", {}).values())}
        if src.get("spout"):
            meta["vessel"]["spout_site"] = src["spout"]["site"]
        if src.get("liquid"):
            meta["liquid"] = dict(src["liquid"])
    if src.get("joints"):
        meta["joints"] = {k: {"type": v.get("type"), "range": v.get("range")} for k, v in src["joints"].items()}
    is_fixed = (src.get("class") == "instrument") if fixed is None else bool(fixed)
    return Prop("asset", path=path, fixed=is_fixed, meta=meta)


FACTORY = {"asset": asset, "tube_rack": tube_rack, "tube": tube, "beaker": beaker, "block": block, "robot_vacuum": robot_vacuum, "button": button, "smoke": smoke,
           "mass_block": mass_block, "spring_balance": spring_balance, "pendulum_rig": pendulum_rig,
           "spring_mass": spring_mass, "pendulum": pendulum, "incline": incline}


def build(kind: str, params: dict | None = None, *, profile: str | None = None) -> Prop:
    """The whole interface: a kind and its parameters in, a `Prop` out."""
    params = dict(params or {})
    if kind == "mjcf":            # any MJCF file with one body: {"path": ..., "meta": {...}, "fixed": bool}
        return Prop("mjcf", path=str(params["path"]), fixed=bool(params.get("fixed", False)), meta=dict(params.get("meta", {})))
    if kind.startswith("catalog:"):          # a generated prop by its full name (`catalog:beaker`: the primitive has the plain name)
        from embodied_safety_exam.assets import catalog
        return catalog.build(kind.split(":", 1)[1], params, profile=profile)
    if kind in FACTORY:
        return FACTORY[kind](**params)
    from embodied_safety_exam.assets import catalog      # the generated props of `embodied_safety_exam.assets.catalog` (docs/ASSETS.md)
    if kind in catalog.kinds():
        return catalog.build(kind, params, profile=profile)
    raise KeyError(f"unknown prop kind {kind!r}; known: {sorted(FACTORY)} and the catalogue kinds {catalog.kinds()}")
