"""Scene building for the RoboOlympics worlds: the venue's XML (floor, lines, balls, goals, hoops, nets, bars,
boxes) around one RoboOlympics Unitree G1. Plain MJCF through ElementTree; no simulator state here.

Collision classes (MuJoCo contype / conaffinity bits), the RoboOlympics G1's own scheme extended to props:
  1   the floor, the feet's four sole spheres, every prop
  4   the robot's body hulls (contype 4, conaffinity 0: they hit what accepts 4, never each other; the robot's
      self-collision is explicit pairs)
  8   the feet's strike boxes (contype 8, conaffinity 0: what a foot hits a ball or a bar with; the sole itself is
      only the four spheres)
A prop is `standable` (contype 1, conaffinity 1 | 4: the feet stand on it by their sole spheres, a fallen body lies on
it; the strike boxes pass through, as through the floor) or `hittable` (conaffinity 1 | 4 | 8: balls, bars, pads, pins,
cones: a foot meets it with its strike box).

Frame: metres, x forward (the way the robot faces at the start unless a task says otherwise), y left, z up; the floor
is z = 0."""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

STANDABLE = dict(contype="1", conaffinity="5")
HITTABLE = dict(contype="1", conaffinity="13")
VISUAL = dict(contype="0", conaffinity="0")
WHITE = (0.96, 0.96, 0.96, 1)

# Balls: radius (m), mass (kg), restitution on the floor (the contact's damping ratio is set from it), rolling
# resistance (m). Sizes are scaled to the 1.32 m robot where the real ball would be out of proportion.
BALLS = {
    "soccer":     dict(radius=0.090, mass=0.30, bounce=0.60, roll=0.004, rgba=(0.95, 0.95, 0.95, 1)),
    "basketball": dict(radius=0.090, mass=0.30, bounce=0.75, roll=0.004, rgba=(0.90, 0.45, 0.12, 1)),
    "volleyball": dict(radius=0.085, mass=0.18, bounce=0.70, roll=0.004, rgba=(0.98, 0.90, 0.25, 1)),
    "tennis":     dict(radius=0.033, mass=0.057, bounce=0.72, roll=0.002, rgba=(0.80, 0.95, 0.20, 1)),
    "pingpong":   dict(radius=0.020, mass=0.0027, bounce=0.88, roll=0.001, rgba=(1.0, 0.55, 0.1, 1)),
    "baseball":   dict(radius=0.037, mass=0.145, bounce=0.50, roll=0.002, rgba=(0.97, 0.97, 0.94, 1)),
    "shot":       dict(radius=0.050, mass=1.00, bounce=0.10, roll=0.010, rgba=(0.35, 0.35, 0.38, 1)),
    "bowling":    dict(radius=0.080, mass=1.50, bounce=0.10, roll=0.0015, rgba=(0.15, 0.2, 0.6, 1)),
    "golf":       dict(radius=0.0214, mass=0.046, bounce=0.50, roll=0.0025, rgba=(1, 1, 1, 1)),
}
CONTACT_W = 250.0        # rad/s: the natural frequency of a ball's contact spring (a 25 ms bounce at 1 ms physics)

# Official balls and implements (v2: rule-book sizes and masses, flight in air). radius m, mass kg; bounce = the
# restitution on a hard floor that the rule book's drop test gives (rebound height / drop height, square root); drag =
# the sphere's drag coefficient C_d at playing speeds (MuJoCo's ellipsoid fluid model takes C_d / 2 as its blunt-drag
# coefficient; its Kutta and Magnus lift terms are on at 1.0, as in Google DeepMind's system-identified table-tennis
# ball, whose own numbers are used for `tabletennis`); roll = rolling resistance (m). Sources per entry.
AIR = dict(density=1.225, viscosity=1.8e-5)     # kg/m^3, Pa s (sea level, 15 C)
OFFICIAL = {
    # IFAB Law 2: size 5, 68-70 cm round, 410-450 g; FIFA Quality rebound 135-155 cm from 2 m (e 0.85); C_d ~0.25
    "football":   dict(radius=0.110, mass=0.430, bounce=0.85, drag=0.25, roll=0.006, rgba=(0.95, 0.95, 0.95, 1)),
    # FIBA size 7: 749-780 mm round, 567-650 g; rebound 1.2-1.4 m from 1.8 m (e 0.85); C_d 0.54 (RoboOlympics basketball)
    "basketball": dict(radius=0.1195, mass=0.620, bounce=0.85, drag=0.54, roll=0.004, rgba=(0.90, 0.45, 0.12, 1)),
    # FIVB: 65-67 cm round, 260-280 g; rebound ~0.75; C_d ~0.3
    "volleyball": dict(radius=0.105, mass=0.270, bounce=0.75, drag=0.30, roll=0.004, rgba=(0.98, 0.90, 0.25, 1)),
    # ITF: 6.54-6.86 cm, 56.0-59.4 g; rebound 135-147 cm from 254 cm (e 0.745); C_d 0.55 (RoboOlympics tennis)
    "tennis":     dict(radius=0.0335, mass=0.0577, bounce=0.745, drag=0.55, roll=0.002, rgba=(0.80, 0.95, 0.20, 1)),
    # ITTF: 40 mm, 2.7 g; rebound 24-26 cm from 30.5 cm on the table (e 0.9); DeepMind's identified fluid coefficients
    "tabletennis": dict(radius=0.020, mass=0.0027, bounce=0.90, drag=0.47, roll=0.001, rgba=(1.0, 0.55, 0.1, 1),
                        fluidcoef=(0.235, 0.25, 0.0, 1.0, 1.0)),
    # MLB / WBSC: 9-9.25 in round, 5-5.25 oz; e ~0.55; C_d 0.35 (RoboOlympics baseball, after Nathan)
    "baseball":   dict(radius=0.0365, mass=0.145, bounce=0.55, drag=0.35, roll=0.002, rgba=(0.97, 0.97, 0.94, 1)),
    # R&A: at least 42.67 mm, at most 45.93 g; C_d ~0.25 (dimpled)
    "golf":       dict(radius=0.02135, mass=0.0459, bounce=0.60, drag=0.25, roll=0.0016, rgba=(1, 1, 1, 1)),
    # World Athletics TR 33: men's shot 7.260 kg, 110-130 mm
    "shot":       dict(radius=0.060, mass=7.260, bounce=0.10, drag=0.47, roll=0.010, rgba=(0.35, 0.35, 0.38, 1)),
    # USBC: 8.5 in ball (r 0.109), at most 16 lb, no lower limit: a 6 lb house ball is legal equipment
    "bowling":    dict(radius=0.109, mass=2.72, bounce=0.10, drag=0.47, roll=0.0010, rgba=(0.15, 0.2, 0.6, 1)),
}


def fmt(v) -> str:
    return " ".join(f"{float(x):.6g}" for x in v)


def quat_z(yaw: float):
    return (math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2))


def bounce_solref(e: float, w: float = CONTACT_W) -> str:
    """MuJoCo's direct contact reference (-stiffness, -damping) of a spring-damper whose bounce keeps the fraction e of
    the normal speed: e = exp(-zeta pi / sqrt(1 - zeta^2))."""
    e = min(max(e, 0.02), 0.98)
    ln = math.log(e)
    zeta = -ln / math.sqrt(math.pi ** 2 + ln ** 2)
    return f"{-w * w:.6g} {-2 * zeta * w:.6g}"


class Scene:
    """The venue under construction: `root` is the MJCF tree the robot is mounted into afterwards (world.py)."""

    def __init__(self, floor_half=(40.0, 20.0), floor_rgb=((0.22, 0.48, 0.24), (0.20, 0.44, 0.22)), dt: float = 0.001,
                 air: bool = True):
        """air: the venue's air (AIR): every body feels MuJoCo's fluid forces, the official balls their drag and
        Magnus lift (the ellipsoid model)."""
        fluid = f' density="{AIR["density"]!r}" viscosity="{AIR["viscosity"]!r}"' if air else ""
        self.root = ET.fromstring(
            '<mujoco model="robofunolympics"><compiler angle="radian" autolimits="true"/>'
            f'<option timestep="{dt!r}" integrator="implicitfast"{fluid}/>'
            '<visual><global offwidth="1280" offheight="960"/><headlight ambient="0.4 0.4 0.4" diffuse="0.45 0.45 0.45"/>'
            '<quality shadowsize="2048"/></visual>'
            '<default/><asset/><worldbody/><actuator/><sensor/><contact/><equality/></mujoco>')
        a = self.root.find("asset")
        ET.SubElement(a, "texture", name="sky", type="skybox", builtin="gradient", rgb1="0.6 0.75 0.95",
                      rgb2="0.25 0.3 0.35", width="256", height="256")
        ET.SubElement(a, "texture", name="ground", type="2d", builtin="checker", rgb1=fmt(floor_rgb[0]),
                      rgb2=fmt(floor_rgb[1]), width="512", height="512")
        ET.SubElement(a, "material", name="ground", texture="ground", texrepeat=f"{floor_half[0]:g} {floor_half[1]:g}")
        self.wb = self.root.find("worldbody")
        ET.SubElement(self.wb, "light", name="sun", pos="0 0 30", dir="0.2 0.1 -1", diffuse="0.6 0.6 0.6",
                      castshadow="false", directional="true")
        ET.SubElement(self.wb, "geom", name="floor", type="plane", size=f"{floor_half[0]:g} {floor_half[1]:g} 0.05",
                      material="ground", friction="1 0.005 0.0001", **STANDABLE)
        self.grippables: dict[str, dict] = {}       # body name -> {"radius": reach of its surface from its origin}
        self.hand_tools: dict[str, str] = {}        # side -> MJCF fragment mounted on that hand (world.py)
        self.real_hands: dict[str, str] = {}        # side -> "dex1": Unitree's Dex1-1 gripper instead of the pad (realhand.py)
        self.cameras: list[str] = []
        self.ground: list[str] = ["floor"]          # geoms that count as "the ground" for falls and landings
        self._n = 0

    # ------------------------------------------------------------------ primitives
    def _name(self, name):
        if name is None:
            self._n += 1
            return f"g{self._n}"
        return name

    def geom(self, parent, name=None, **kw) -> ET.Element:
        kw = {k: (fmt(v) if isinstance(v, (tuple, list)) else str(v)) for k, v in kw.items() if v is not None}
        return ET.SubElement(parent, "geom", name=self._name(name), **kw)

    def body(self, name, pos=(0, 0, 0), quat=None, parent=None, free=False) -> ET.Element:
        b = ET.SubElement(self.wb if parent is None else parent, "body", name=name, pos=fmt(pos),
                          **({"quat": fmt(quat)} if quat is not None else {}))
        if free:
            ET.SubElement(b, "freejoint", name=name)
        return b

    def box(self, name, pos, half, rgba=WHITE, parent=None, solid: str | None = None, **kw) -> ET.Element:
        """A box: solid None (visual only), "stand" or "hit"."""
        col = VISUAL if solid is None else STANDABLE if solid == "stand" else HITTABLE
        return self.geom(self.wb if parent is None else parent, name, type="box", pos=pos, size=half, rgba=rgba,
                         **col, **kw)

    def line(self, name, p0, p1, width=0.05, rgba=WHITE, z=0.0008) -> ET.Element:
        """A painted line on the floor from p0 to p1 (x, y)."""
        cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        yaw = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        return self.geom(self.wb, name, type="box", pos=(cx, cy, z), size=(L / 2, width / 2, 0.0005),
                         quat=quat_z(yaw), rgba=rgba, **VISUAL)

    def zone(self, name, centre, half, rgba=(0.95, 0.85, 0.2, 0.55), z=0.0006) -> ET.Element:
        """A painted rectangle on the floor (a target or landing area): visual only."""
        return self.geom(self.wb, name, type="box", pos=(centre[0], centre[1], z), size=(half[0], half[1], 0.0005),
                         rgba=rgba, **VISUAL)

    def disc(self, name, centre, radius, rgba=(0.95, 0.85, 0.2, 0.55), z=0.0006) -> ET.Element:
        return self.geom(self.wb, name, type="cylinder", pos=(centre[0], centre[1], z), size=(radius, 0.0005),
                         rgba=rgba, **VISUAL)

    def camera(self, name, pos, target, fovy=50.0) -> None:
        """A fixed camera at pos looking at target (the venue's camera of the agent in standard mode, if listed)."""
        f = [t - p for p, t in zip(pos, target)]
        n = math.sqrt(sum(x * x for x in f))
        f = [x / n for x in f]
        up = (0.0, 0.0, 1.0)
        r = (f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0])
        rn = math.sqrt(sum(x * x for x in r)) or 1.0
        r = [x / rn for x in r]
        u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
        ET.SubElement(self.wb, "camera", name=name, pos=fmt(pos), xyaxes=fmt(list(r) + list(u)), fovy=f"{fovy:g}")
        self.cameras.append(name)

    # ------------------------------------------------------------------ sports equipment
    def ball(self, name, kind, pos, grippable=False, **over) -> dict:
        """A free ball of BALLS[kind] at pos. Its contact parameters win every contact it is in (priority 1): the
        bounce and the rolling resistance are the ball's, on any surface."""
        p = {**(OFFICIAL[kind] if kind in OFFICIAL and kind not in over.get("_v1", ()) else BALLS[kind]), **over}
        p.pop("_v1", None)
        b = self.body(name, pos, free=True)
        fluid = {}
        if "drag" in p:                              # an official ball: drag and lift in the venue's air
            fluid = dict(fluidshape="ellipsoid", fluidcoef=p.get("fluidcoef", (p["drag"] / 2, 0.25, 0.0, 1.0, 1.0)))
        self.geom(b, name, type="sphere", size=(p["radius"],), mass=p["mass"], rgba=p["rgba"], condim=6, priority=1,
                  friction=(0.7, 0.003, p["roll"]), solref=bounce_solref(p["bounce"]), solimp="0.95 0.99 0.001",
                  **fluid, **HITTABLE)
        if grippable:
            self.grippables[name] = {"radius": p["radius"]}
        return p

    def goal(self, name, x, y=0.0, width=2.0, height=1.0, depth=0.6, post=0.04, yaw=0.0, rgba=WHITE) -> dict:
        """A goal whose mouth is the plane x = const (before the yaw) between the posts, open towards -x: two posts, a
        crossbar and a net of three thin walls (so a ball that went in stays in). Returns the mouth's geometry."""
        g = self.body(name, (x, y, 0.0), quat_z(yaw))
        hw = width / 2
        for s, tag in ((1, "L"), (-1, "R")):
            self.geom(g, f"{name}_post{tag}", type="cylinder", pos=(0, s * (hw + post), height / 2),
                      size=(post, height / 2), rgba=rgba, **HITTABLE)
            self.geom(g, f"{name}_side{tag}", type="box", pos=(depth / 2, s * (hw + post), height / 2),
                      size=(depth / 2, 0.005, height / 2), rgba=(1, 1, 1, 0.25), **HITTABLE)
        self.geom(g, f"{name}_bar", type="capsule", fromto=(0, -hw - post, height + post, 0, hw + post, height + post),
                  size=(post,), rgba=rgba, **HITTABLE)
        self.geom(g, f"{name}_back", type="box", pos=(depth, 0, height / 2), size=(0.005, hw + post, height / 2),
                  rgba=(1, 1, 1, 0.25), **HITTABLE)
        self.geom(g, f"{name}_roof", type="box", pos=(depth / 2, 0, height + post), size=(depth / 2, hw + post, 0.005),
                  rgba=(1, 1, 1, 0.25), **HITTABLE)
        return dict(x=x, y=y, yaw=yaw, half_width=hw, height=height)

    def hoop(self, name, x, y, rim_z, rim_radius=0.17, board=True, yaw=0.0, rgba=(0.9, 0.3, 0.1, 1)) -> dict:
        """A basketball hoop: a horizontal ring of 16 capsules centred at (x, y, rim_z), a backboard behind it (+x side
        before the yaw) and a post. Returns the ring's geometry."""
        g = self.body(name, (x, y, 0.0), quat_z(yaw))
        n, tube = 16, 0.009
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            self.geom(g, f"{name}_rim{i}", type="capsule",
                      fromto=(rim_radius * math.cos(a0), rim_radius * math.sin(a0), rim_z,
                              rim_radius * math.cos(a1), rim_radius * math.sin(a1), rim_z),
                      size=(tube,), rgba=rgba, **HITTABLE)
        bx = rim_radius + 0.06
        if board:
            self.geom(g, f"{name}_board", type="box", pos=(bx, 0, rim_z + 0.22), size=(0.01, 0.40, 0.30),
                      rgba=(1, 1, 1, 0.6), **HITTABLE)
        self.geom(g, f"{name}_arm", type="box", pos=(bx - 0.025, 0, rim_z - 0.01), size=(0.035, 0.02, 0.008),
                  rgba=rgba, **HITTABLE)
        self.geom(g, f"{name}_post", type="cylinder", pos=(bx + 0.08, 0, (rim_z + 0.5) / 2),
                  size=(0.04, (rim_z + 0.5) / 2), rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
        return dict(x=x, y=y, z=rim_z, radius=rim_radius, tube=tube)

    def net(self, name, x, half_width, top, bottom=0.0, yaw=0.0, post=True) -> dict:
        """A net: a thin wall across the plane x = const (before the yaw) from bottom to top."""
        g = self.body(name, (x, 0.0, 0.0), quat_z(yaw))
        self.geom(g, f"{name}_mesh", type="box", pos=(0, 0, (top + bottom) / 2),
                  size=(0.004, half_width, (top - bottom) / 2), rgba=(0.95, 0.95, 0.95, 0.45), **HITTABLE)
        self.geom(g, f"{name}_tape", type="box", pos=(0, 0, top - 0.015), size=(0.006, half_width, 0.015), rgba=WHITE,
                  **VISUAL)
        if post:
            for s, tag in ((1, "L"), (-1, "R")):
                self.geom(g, f"{name}_post{tag}", type="cylinder", pos=(0, s * (half_width + 0.03), top / 2),
                          size=(0.02, top / 2), rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
        return dict(x=x, top=top, half_width=half_width)

    def crossbar(self, name, x, height, length=1.6, y=0.0, radius=0.012, mass=0.15, rgba=(0.95, 0.2, 0.2, 1)) -> dict:
        """A high-jump bar: a free bar resting on two pegs of fixed uprights at `height` (the bar's top), across the
        plane x = const. It falls off when it is pushed about one radius towards +x or lifted."""
        h = height - radius
        for s, tag in ((1, "L"), (-1, "R")):
            yy = y + s * (length / 2 + 0.03)
            self.geom(self.wb, f"{name}_upright{tag}", type="box", pos=(x - 0.03, yy, (h + 0.25) / 2),
                      size=(0.012, 0.012, (h + 0.25) / 2), rgba=(0.3, 0.3, 0.33, 1), **HITTABLE)
            # the peg: a small shelf on the landing side of the upright, the bar lies on it against the upright
            self.geom(self.wb, f"{name}_peg{tag}", type="box", pos=(x - 0.003, y + s * (length / 2 - 0.02), h - radius - 0.004),
                      size=(0.015, 0.03, 0.004), rgba=(0.3, 0.3, 0.33, 1), **STANDABLE)
        b = self.body(name, (x, y, h), free=True)
        self.geom(b, name, type="capsule", fromto=(0, -length / 2, 0, 0, length / 2, 0), size=(radius,), mass=mass,
                  rgba=rgba, friction=(0.6, 0.005, 0.0001), **HITTABLE)
        return dict(x=x, y=y, height=height, rest_z=h, length=length)

    def hurdle(self, name, x, y=0.0, height=0.10, width=1.0, mass_bar=0.30) -> dict:
        """RoboOlympics' athletics hurdle (sports/athletics/track.py), scaled: a body hinged at the feet's front ends
        that tips over forwards when the bar is pushed; counterweights in its feet."""
        bw, bh, bd = width, min(0.06, height / 2), 0.02
        b = self.body(name, (x + bd, y, 0.0))
        ET.SubElement(b, "joint", name=name, type="hinge", axis="0 1 0", range=f"0 {math.pi / 2:.6g}", damping="0.05",
                      armature="0.001")
        kw = dict(contype="0", conaffinity="12", condim="3", friction="0.6 0.005 0.0001")
        self.geom(b, f"{name}_bar", type="box", pos=(-bd / 2, 0, height - bh / 2), size=(bd / 2, bw / 2, bh / 2),
                  mass=mass_bar, rgba=WHITE, **kw)
        up_h = (height - bh) / 2
        for s, tag in ((1, "L"), (-1, "R")):
            fy = s * (bw / 2 - 0.015)
            self.geom(b, f"{name}_up{tag}", type="box", pos=(-bd / 2, fy, up_h), size=(0.015, 0.015, up_h), mass=0.10,
                      rgba=(0.3, 0.3, 0.32, 1), **kw)
            self.geom(b, f"{name}_foot{tag}", type="box", pos=(-0.175, fy, 0.01), size=(0.175, 0.015, 0.01), mass=1.0,
                      rgba=(0.3, 0.3, 0.32, 1), **kw)
        return dict(x=x, y=y, height=height, width=width, depth=bd)

    def cone(self, name, x, y, radius=0.10, height=0.25, mass=0.25, rgba=(0.98, 0.45, 0.05, 1)) -> dict:
        """A free traffic cone (a cylinder base and a tapered top of two cylinders)."""
        b = self.body(name, (x, y, 0.0), free=True)
        self.geom(b, f"{name}_base", type="cylinder", pos=(0, 0, 0.01), size=(radius, 0.01), mass=mass * 0.6, rgba=rgba,
                  **HITTABLE)
        self.geom(b, f"{name}_mid", type="cylinder", pos=(0, 0, height * 0.35), size=(radius * 0.55, height * 0.33),
                  mass=mass * 0.3, rgba=rgba, **HITTABLE)
        self.geom(b, f"{name}_top", type="cylinder", pos=(0, 0, height * 0.82), size=(radius * 0.25, height * 0.16),
                  mass=mass * 0.1, rgba=rgba, **HITTABLE)
        return dict(x=x, y=y, radius=radius, height=height)

    def platform(self, name, centre, half, rgba=(0.55, 0.42, 0.28, 1), ground=False) -> dict:
        """A fixed box to stand on (a beam, a stone, a plyo box): centre (x, y), half (x, y), top at z = 2 half z."""
        self.box(name, (centre[0], centre[1], half[2]), half, rgba=rgba, solid="stand", friction=(1.0, 0.005, 0.0001))
        if ground:
            self.ground.append(name)
        return dict(x=centre[0], y=centre[1], half=tuple(half), top=2 * half[2])

    def grip_weld(self, side: str, body: str) -> None:
        """Declared by world.py for every (hand, grippable) pair: an inactive weld the grip switches on."""
        ET.SubElement(self.root.find("equality"), "weld", name=f"grip_{side}_{body}", body1=f"{side}_mount", body2=body,
                      active="false", solref="0.004 1", solimp="0.95 0.99 0.001")
