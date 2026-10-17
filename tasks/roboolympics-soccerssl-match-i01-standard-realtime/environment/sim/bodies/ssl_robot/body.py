"""The RoboCup SSL robot (body.toml; bodies/ssl_robot/README.md): mount into a mujoco.MjSpec, rig, drive.

    import mujoco
    from bodies.ssl_robot import body as SSL
    spec = mujoco.MjSpec()                                   # the world (sports/soccer_ssl/sim/field.py)
    h = SSL.mount(spec, "blue_1", "blue", 1, pose=(-1.0, 0.5, 0.0))
    model = spec.compile(); data = mujoco.MjData(model)
    rig = SSL.rig(model, data, h, limits=None)               # body.toml's limits (a sport may only tighten them)
    rig.set_base_target(0.0, 0.0, 1.57)                      # world frame
    rig.dribble(3000); rig.kick(5.0, "flat", armed_for=1.0)
    SSL.step_world(model, data, [rig])                       # one 10 ms control step: rig.step, then per 1 ms
                                                             # physics step rig.substep + mujoco.mj_step

The interface of docs olympiad_review/screening/soccer_ssl_interfaces_zh.md section 3, plus `substep`: the servo,
the dribbler's motor and the kicker's break beam run every 1 ms physics step (the real robot's 1 kHz loops, S1, S3);
`step` runs once per 10 ms control step. A world that cannot call substep gets a coarse fallback (see Rig.step).

The robot: a cylinder of 178 x 148 mm cut flat at the front (S1, S5), a dribbler opening in the front with a 14 mm
TPU bar (S3) on a damped hinged carrier (S2) above a chip shovel that stops the ball at 19.8 % coverage (S1, S7), a
break beam across the opening (S1 2.3), the SSL vision pattern on top (S7 3.2.5). Planar joints: x, y (world axes)
and yaw; qpos of these three joints IS the robot's world pose (x, y, yaw), its qpos0 the mount pose. The base is
driven through bodies/servo.py (PlanarBase setpoints at body.toml [limits.base], PD + inertia feed-forward, the
output stage at the drive force caps), the dribbler's motor through bodies/servo.py Actuators at its torque limit.
"""
from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .. import servo as SV
from .assist import Assist
from .kicker import Kicker
from .trajectory import Plan2D

HERE = Path(__file__).resolve().parent
BALL_R = 0.0215               # the sport's ball (sports/soccer_ssl/sim/ball.py: 43 mm, the rules' 0.043 m, S7 2.2)
TEAM_RGBA = {"blue": (0.0, 0.25, 1.0, 1.0), "yellow": (1.0, 0.9, 0.0, 1.0)}
DOT_RGBA = {"P": (1.0, 0.0, 1.0, 1.0), "G": (0.0, 1.0, 0.0, 1.0)}        # pink (magenta), green: S7 figure 6
HULL_RGBA = (0.12, 0.12, 0.12, 1.0)   # the robot top must be black or dark grey, matte (S7 3.2.5)
# S7 figure 6 (images/standard_colors2010.svg, read off the rendered figure): the four dots of each id, in the order
# front-left, front-right, back-left, back-right (robot frame: front = the flat side), P pink, G green
PATTERN = {0: "PPGP", 1: "GPGP", 2: "GGGP", 3: "PGGP", 4: "PPPG", 5: "GPPG", 6: "GGPG", 7: "PGPG",
           8: "GGGG", 9: "PPPP", 10: "PPGG", 11: "GGPP", 12: "GPGG", 13: "GPPP", 14: "PGGG", 15: "PGPP"}


def load_decl() -> dict:
    return tomllib.loads((HERE / "body.toml").read_text())


def coverage(d, R=BALL_R):
    """the fraction of the ball's top view inside a straight hull line at distance d (< R) from its centre"""
    d = min(max(d, -R), R)
    return (R * R * math.acos(d / R) - d * math.sqrt(R * R - d * d)) / (math.pi * R * R)


def layout(G: dict) -> dict:
    """the derived geometry (robot frame, metres) from body.toml [geometry]"""
    r_bar = G["bar_diameter"] / 2
    x_bar = G["front"] - r_bar                                  # the bar's front tangent on the front chord
    z_bar = G["bar_axis_height"]
    reach = math.sqrt((BALL_R + r_bar) ** 2 - (z_bar - BALL_R) ** 2)
    lo, hi = 0.0, BALL_R                                        # the ball's centre at the shovel: coverage limit
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if coverage(mid) > G["shovel_coverage"]:
            lo = mid
        else:
            hi = mid
    x_ball_min = G["front"] + hi
    return dict(r_bar=r_bar, x_bar=x_bar, z_bar=z_bar, x_ball_rest=x_bar + reach, x_ball_min=x_ball_min,
                x_shovel=x_ball_min - BALL_R, x_cav=G["front"] - G["cavity_depth"],
                y_front=math.sqrt(G["radius"] ** 2 - G["front"] ** 2),
                pivot=(x_bar - G["pivot_behind_bar"], z_bar + G["pivot_above_bar"]))


def _prism(xy, z0, z1):
    out = []
    for x, y in xy:
        out += [x, y, z0, x, y, z1]
    return out


def _hull_pieces(G, Lg):
    """convex pieces of the chassis (each a convex mesh): the main body behind the dribbler opening, the opening's
    two side walls up to the front chord, the cover over the opening"""
    R, z0, z1 = G["radius"], G["ground_clearance"], G["height"]
    xc, xf, w = Lg["x_cav"], G["front"], G["cavity_half_width"]
    n = 72
    main = [(R * math.cos(t), R * math.sin(t)) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)
            if R * math.cos(t) <= xc]
    yc = math.sqrt(R * R - xc * xc)
    main += [(xc, yc), (xc, -yc)]
    arc = [(R * math.cos(t), R * math.sin(t)) for t in np.linspace(0, math.pi / 2, 60)
           if xc <= R * math.cos(t) <= xf]
    left = [(x, y) for x, y in arc if y >= w] + [(xf, Lg["y_front"]), (xf, w), (xc, w), (xc, yc)]
    right = [(x, -y) for x, y in left]
    cover = [(xc, -w), (xc, w), (xf, w), (xf, -w)]
    outer = [(R * math.cos(t), R * math.sin(t)) for t in np.linspace(0, 2 * math.pi, n, endpoint=False)
             if R * math.cos(t) <= xf] + [(xf, Lg["y_front"]), (xf, -Lg["y_front"])]
    return {"main": _prism(main, z0, z1), "wall_l": _prism(left, z0, z1), "wall_r": _prism(right, z0, z1),
            "cover": _prism(cover, G["cavity_top"], z1)}, _prism(outer, z0, z1)


def _quat_z(a):
    return [math.cos(a / 2), 0.0, 0.0, math.sin(a / 2)]


def _side_band(spec, body, p, team, D, Lg, mat):
    """the team colour on the sides (S12, rules 3.2.3): thin visual panels (contype / conaffinity 0, no mass) just
    outside the hull's curved side and on the front chord, between side_band_z, all round except a window of
    +-side_band_front_gap_deg in front. Inside the rules' 0.09 m radius. Returns the geoms and the share of the
    side area they cover."""
    import mujoco as mj
    G, A = D["geometry"], D["appearance"]
    R, H, xf = G["radius"], G["height"], G["front"]
    z0, z1 = A["side_band_z"]
    gap = math.radians(A["side_band_front_gap_deg"])
    a_front = math.acos(xf / R)                                # the front chord ends at +-a_front
    rc, th = R + 0.0002, 0.0005                                # panel centre radius, half thickness: outer 0.0897 m
    n = 40                                                     # 7 deg panels: corners stay inside 0.09 m
    span = 2 * math.pi - 2 * a_front                           # the curved side
    hw = rc * math.tan(span / n / 2) * 1.01
    m = mat("band", A["side_band_rgba"][team])
    geoms = []
    for k in range(n):
        a = a_front + span * (k + 0.5) / n
        g = body.add_geom(name=p + f"band_{k}", type=mj.mjtGeom.mjGEOM_BOX, size=[th, hw, (z1 - z0) / 2],
                          pos=[rc * math.cos(a), rc * math.sin(a), (z0 + z1) / 2], quat=_quat_z(a), material=m,
                          contype=0, conaffinity=0, mass=0.0, density=0.0, group=1)
        geoms.append(g.name)
    y_gap, y_end = xf * math.tan(gap), Lg["y_front"]
    for sgn in (1, -1):                                        # the front chord, outside the camera window
        g = body.add_geom(name=p + f"band_front_{'l' if sgn > 0 else 'r'}", type=mj.mjtGeom.mjGEOM_BOX,
                          size=[th, (y_end - y_gap) / 2, (z1 - z0) / 2],
                          pos=[xf + th, sgn * (y_gap + y_end) / 2, (z0 + z1) / 2], material=m,
                          contype=0, conaffinity=0, mass=0.0, density=0.0, group=1)
        geoms.append(g.name)
    perim = R * span + 2 * y_end
    covered = R * span + 2 * (y_end - y_gap)
    return dict(geoms=geoms, share=covered / perim * (z1 - z0) / H)


@dataclass
class Handles:
    """The names of one mounted robot (mount's result): everything a world, a referee or a camera needs."""
    name: str
    team: str
    number: int
    pose: tuple
    body: str                                   # the chassis body (x, y, yaw joints)
    joints: tuple                               # (x, y, yaw): qpos = the world pose
    dribbler_body: str
    dribbler_hinge: str                         # the damped carrier's hinge
    roller_body: str
    roller_joint: str
    actuators: dict                             # x, y, yaw, roller
    geoms: dict                                 # hull (list), roller, shovel, carrier, pattern (list)
    sites: dict                                 # beam_a, beam_b (the break beam), kick (the ball's resting point), top
    pattern: str                                # the four dots (FL FR BL BR)
    extra: dict = field(default_factory=dict)


def mount(spec, name: str, team: str, number: int, pose=(0.0, 0.0, 0.0), lod: str = "sim", decl: dict | None = None
          ) -> Handles:
    """Add one SSL robot to a mujoco.MjSpec. team in {"blue", "yellow"}; number 0..15 (the vision pattern's id; the
    sport uses 0..5); pose = (x, y, yaw) in the world frame. lod: one level of detail (simple solids); accepted for
    the interface. Names are prefixed with `name` + "_". Returns the Handles."""
    if team not in TEAM_RGBA:
        raise ValueError(f"team must be one of {sorted(TEAM_RGBA)}, not {team!r}")
    if int(number) not in PATTERN:
        raise ValueError(f"number must be 0..15 (the SSL vision patterns), not {number!r}")
    import mujoco as mj
    D = decl or load_decl()
    G, Lb, Ld = D["geometry"], D["limits"]["base"], D["limits"]["dribbler"]
    Lg = layout(G)
    p = f"{name}_"
    x0, y0, yaw0 = (float(v) for v in pose)
    c, s = math.cos(yaw0), math.sin(yaw0)
    ang = math.degrees if spec.compiler.degree else float   # the scene's compiler angle unit (MjSpec: degrees)
    mats = {}

    def mat(key, rgba):
        if key not in mats:
            mats[key] = spec.add_material(name=p + "mat_" + key, rgba=list(rgba), specular=0.05, shininess=0.0)
        return p + "mat_" + key

    body = spec.worldbody.add_body(name=p + "robot", pos=[x0, y0, 0.0], quat=_quat_z(yaw0))
    # x, y slide along the WORLD axes (their axes are given in the body's frame, rotated by -yaw0) and qpos0 = the
    # mount pose (ref), so qpos[x, y, yaw] is the world pose at any time
    jx = body.add_joint(name=p + "x", type=mj.mjtJoint.mjJNT_SLIDE, axis=[c, -s, 0.0], ref=x0)
    jy = body.add_joint(name=p + "y", type=mj.mjtJoint.mjJNT_SLIDE, axis=[s, c, 0.0], ref=y0)
    jw = body.add_joint(name=p + "yaw", type=mj.mjtJoint.mjJNT_HINGE, axis=[0.0, 0.0, 1.0], ref=ang(yaw0))
    for j in (jx, jy, jw):
        j.armature = 0.0
        j.damping = 0.0
    m_carrier, m_bar = 0.10, 0.012                           # ESTIMATE (README): the dribbler module and the bar
    m_chassis = float(D["body"]["mass_kg"]) - m_carrier - m_bar
    R, H = G["radius"], G["height"]
    body.explicitinertial = True
    body.mass = m_chassis
    body.ipos = [0.0, 0.0, 0.045]                             # ESTIMATE: low centre of mass (battery, motors)
    body.inertia = [m_chassis * (3 * R * R + H * H) / 12] * 2 + [0.5 * m_chassis * R * R]
    hull = []
    pieces, outer = _hull_pieces(G, Lg)
    # robot against robot: the whole convex outline (the cut cylinder), on its own collision bit (2): the thin pieces
    # around the dribbler opening would let two fast robots slide into each other (README "Contacts")
    spec.add_mesh(name=p + "mesh_outer", uservert=outer)
    g = body.add_geom(name=p + "hull_outer", type=mj.mjtGeom.mjGEOM_MESH, meshname=p + "mesh_outer", contype=2,
                      conaffinity=2, group=3, rgba=[0.3, 0.3, 0.3, 0.0], mass=0.0, density=0.0)
    g.solref, g.friction, g.condim = [0.005, 1.0], [0.3, 0.005, 0.0001], 3   # covers absorb the energy (S1 2.4)
    outer_name = g.name
    for key, verts in pieces.items():
        spec.add_mesh(name=p + "mesh_" + key, uservert=verts)
        g = body.add_geom(name=p + "hull_" + key, type=mj.mjtGeom.mjGEOM_MESH, meshname=p + "mesh_" + key,
                          material=mat("hull", HULL_RGBA), mass=0.0, density=0.0)
        g.priority = 2                                        # above the ball's 1: the hull owns the contact (README)
        g.friction = [0.3, 0.005, 0.0001]
        g.solref = [-20000.0, -50.0]                          # restitution about 0.6 with the ball (S10)
        g.condim = 3
        hull.append(g.name)
    # the chip shovel / kicker plunger face: stops the ball at the rules' coverage (S1 19.8 %, S7)
    xs, w = Lg["x_shovel"], G["cavity_half_width"]
    sh = body.add_geom(name=p + "shovel", type=mj.mjtGeom.mjGEOM_BOX,
                       size=[(xs - Lg["x_cav"]) / 2, w - 0.001, (G["shovel_height"] - G["ground_clearance"]) / 2],
                       pos=[(xs + Lg["x_cav"]) / 2, 0.0, (G["shovel_height"] + G["ground_clearance"]) / 2],
                       material=mat("metal", (0.55, 0.55, 0.58, 1.0)), mass=0.0, density=0.0)
    sh.priority, sh.friction, sh.condim = 2, [0.3, 0.005, 0.0001], 3
    sh.solref = list(D.get("dribbler_model", {}).get("shovel_solref", [0.004, 1.0]))   # the plunger's dampers (S1 2.2)
    # the vision pattern (S7 3.2.5): visual only
    top = H + 0.0005
    pats = []
    rc, rd = G["pattern_center_diameter"] / 2, G["pattern_dot_diameter"] / 2
    g = body.add_geom(name=p + "pattern_center", type=mj.mjtGeom.mjGEOM_CYLINDER, size=[rc, 0.0005, 0],
                      pos=[0, 0, top], material=mat("team", TEAM_RGBA[team]), contype=0, conaffinity=0,
                      mass=0.0, density=0.0)
    pats.append(g.name)
    (fx, fy), (bx, by) = G["pattern_front_dot"], G["pattern_back_dot"]
    code = PATTERN[int(number)]
    for k, (px, py) in enumerate(((fx, fy), (fx, -fy), (bx, by), (bx, -by))):
        g = body.add_geom(name=p + f"pattern_{'FL FR BL BR'.split()[k]}", type=mj.mjtGeom.mjGEOM_CYLINDER,
                          size=[rd, 0.0005, 0], pos=[px, py, top], material=mat("dot" + code[k], DOT_RGBA[code[k]]),
                          contype=0, conaffinity=0, mass=0.0, density=0.0)
        pats.append(g.name)
    band = _side_band(spec, body, p, team, D, Lg, mat)
    # the break beam (S1 2.3): emitter and receiver on the opening's side walls
    bx_, bz = G["beam_x"], G["beam_height"]
    body.add_site(name=p + "beam_a", pos=[bx_, w, bz], size=[0.002, 0, 0], rgba=[1, 0, 0, 0.6], group=4)
    body.add_site(name=p + "beam_b", pos=[bx_, -w, bz], size=[0.002, 0, 0], rgba=[1, 0, 0, 0.6], group=4)
    body.add_site(name=p + "kick", pos=[Lg["x_ball_rest"], 0, BALL_R], size=[0.003, 0, 0], rgba=[1, 1, 0, 0.4],
                  group=4)
    body.add_site(name=p + "top", pos=[0, 0, H], size=[0.003, 0, 0], group=4)
    # the dribbler: a carrier on a damped hinge (S2), the bar on its own motor-driven axle (S3)
    px_, pz_ = Lg["pivot"]
    car = body.add_body(name=p + "dribbler", pos=[px_, 0.0, pz_])
    D_ = D.get("dribbler_model", {})
    hinge = car.add_joint(name=p + "dribbler_hinge", type=mj.mjtJoint.mjJNT_HINGE, axis=[0.0, 1.0, 0.0])
    hinge.range = [0.0, ang(float(D_.get("hinge_range_rad", 0.14)))]
    hinge.limited = 1
    hinge.stiffness = float(D_.get("hinge_stiffness", 0.5))
    hinge.springref = ang(float(D_.get("hinge_springref", -0.05)))
    hinge.damping = float(D_.get("hinge_damping", 0.002))
    hinge.solref_limit = list(D_.get("hinge_solref_limit", [0.01, 1.0]))
    cg = car.add_geom(name=p + "carrier", type=mj.mjtGeom.mjGEOM_BOX, size=[0.008, w - 0.004, 0.012],
                      pos=[G["pivot_behind_bar"] * 0.5, 0, -G["pivot_above_bar"] * 0.45],
                      material=mat("metal", (0.55, 0.55, 0.58, 1.0)), contype=0, conaffinity=0, mass=m_carrier)
    rol = car.add_body(name=p + "roller", pos=[G["pivot_behind_bar"], 0.0, -G["pivot_above_bar"]])
    rj = rol.add_joint(name=p + "roller", type=mj.mjtJoint.mjJNT_HINGE, axis=[0.0, 1.0, 0.0])
    rj.armature = float(D_.get("rotor_inertia", 2e-7))
    rj.damping = float(D_.get("bearing_damping", 1e-7))
    rg = rol.add_geom(name=p + "roller", type=mj.mjtGeom.mjGEOM_CYLINDER, size=[Lg["r_bar"], G["bar_half_length"], 0],
                      quat=[math.cos(math.pi / 4), math.sin(math.pi / 4), 0, 0],
                      material=mat("tpu", (0.85, 0.85, 0.8, 1.0)), mass=m_bar)
    rg.priority = 3                                           # the bar's TPU decides the ball-bar contact
    rg.friction = list(D_.get("bar_friction", [1.0, 0.005, 0.0001]))
    rg.solref = list(D_.get("bar_solref", [0.004, 1.0]))
    rg.solimp = list(D_.get("bar_solimp", [0.9, 0.95, 0.001, 0.5, 2.0]))
    rg.condim = int(D_.get("bar_condim", 6))
    for a, b_ in ((p + "robot", p + "dribbler"), (p + "robot", p + "roller")):
        spec.add_exclude(bodyname1=a, bodyname2=b_)
    acts = {}
    for key, j, lim in (("x", p + "x", Lb["drive_force_n"]), ("y", p + "y", Lb["drive_force_n"]),
                        ("yaw", p + "yaw", Lb["drive_torque_nm"]), ("roller", p + "roller", Ld["torque_max_nm"])):
        a = spec.add_actuator(name=p + "m_" + key, target=j, trntype=mj.mjtTrn.mjTRN_JOINT)
        a.set_to_motor()
        a.ctrlrange = [-float(lim), float(lim)]
        a.ctrllimited = 1
        acts[key] = a.name
    return Handles(name=name, team=team, number=int(number), pose=(x0, y0, yaw0), body=p + "robot",
                   joints=(p + "x", p + "y", p + "yaw"), dribbler_body=p + "dribbler", dribbler_hinge=p + "dribbler_hinge",
                   roller_body=p + "roller", roller_joint=p + "roller", actuators=acts,
                   geoms=dict(hull=hull, outer=outer_name, side_band=band["geoms"], shovel=p + "shovel", roller=p + "roller", carrier=p + "carrier", pattern=pats),
                   sites=dict(beam_a=p + "beam_a", beam_b=p + "beam_b", kick=p + "kick", top=p + "top"),
                   pattern=code, extra=dict(layout=Lg, side_band_share=band["share"]))


def _check_tighter(base: dict, over: dict, path=""):
    """a sport may tighten body.toml's limits, never loosen them (bodies/README.md: no scaled(k > 1))"""
    for k, v in over.items():
        if k == "source" or k not in base:
            continue
        if isinstance(v, dict):
            _check_tighter(base[k], v, f"{path}{k}.")
        elif isinstance(v, (int, float)) and isinstance(base[k], (int, float)) and k not in ("chip_angle_deg",):
            if (k.endswith("sigma_rel") or k.endswith("sigma_deg") or k in ("charge_full_s", "recharge_after_max_s",
                                                                            "spinup_s")):
                if v < base[k] - 1e-12:
                    raise ValueError(f"limits.{path}{k} = {v} is looser than body.toml's {base[k]}")
            elif v > base[k] + 1e-12:
                raise ValueError(f"limits.{path}{k} = {v} is looser than body.toml's {base[k]}")


def rig(model, data, handles: Handles, limits: dict | None = None, seed: int = 0) -> "Rig":
    """Drive one mounted robot. limits: None (body.toml) or a dict like body.toml's [limits] with tighter values
    (e.g. {"base": {"speed_m_s": 1.5}}); seed: the kicker's error stream."""
    return Rig(model, data, handles, limits, seed)


class RatePlanarBase(SV.PlanarBase):
    """bodies/servo.py PlanarBase, unchanged (the same limits and laws), with its two tracking gains scaled to a
    100 Hz step. The library's gains (limits.JerkLimiter KP 60 /s, KV 300 /s) are tuned for 1 kHz: at 10 ms the
    velocity loop's gain x step is 3 and the acceleration chatters between its limits (measured: 19 sign flips of
    the yaw acceleration in a 2.5 rad turn, 2 cm overshoot, no settling). KV = 50 /s keeps KV x dt = 0.5 (the
    ratio KP / KV = 1 / 5 as in the library): no chatter, no overshoot, the same time to the goal (2.01 s for
    1.7 m and 2.5 rad, against 2.04 s for the 1 kHz generator). The limits are clipped exactly as before."""
    KP, KV = 10.0, 50.0


class Rig:
    """One robot in a compiled model: the base servo, the kicker, the dribbler; commands in the world frame."""

    def __init__(self, model, data, h: Handles, limits=None, seed=0):
        import mujoco as mj
        self.mj = mj
        self.m, self.h, self.d = model, h, data
        D = load_decl()
        L = {k: dict(v) for k, v in D["limits"].items()}
        if limits:
            _check_tighter(L, limits)
            for k, v in limits.items():
                L[k].update({q: x for q, x in v.items() if q != "source"})
        self.L, self.decl = L, D
        C = D["controller"]
        self.dt = float(C["control_dt_s"])
        self.pdt = float(model.opt.timestep)
        self.substeps = int(round(self.dt / self.pdt))
        jid = lambda n: mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, n)
        ids = [jid(n) for n in h.joints]
        if min(ids) < 0:
            raise ValueError(f"robot {h.name!r} not in the model")
        self.qadr = np.array([model.jnt_qposadr[i] for i in ids])
        self.vadr = np.array([model.jnt_dofadr[i] for i in ids])
        aid = [mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, h.actuators[k]) for k in ("x", "y", "yaw")]
        self.base_lim = SV.BaseLimits.of(L["base"])
        tau = [L["base"]["drive_force_n"], L["base"]["drive_force_n"], L["base"]["drive_torque_nm"]]
        # the setpoint generator (bodies/servo.py PlanarBase: speed, acceleration, jerk on the norm in the robot's
        # frame) runs at setpoint_dt_s, the control rate, as SSL robots plan at their command rate; the 1 kHz PD in
        # substep follows its knots by cubic Hermite interpolation (exact for its constant-jerk segments at a
        # constant heading). Its tracking gains are scaled to that rate (RatePlanarBase). README "Speed".
        self.sp_dt = float(C.get("setpoint_dt_s", self.dt))
        self.n_sp = max(1, int(round(self.dt / self.sp_dt)))
        self.pb = RatePlanarBase(self.base_lim, self.sp_dt)
        self.kp = [float(x) for x in C["kp_base"]]
        self.kd = [float(x) for x in C["kd_base"]]
        rj = jid(h.roller_joint)
        self.r_vadr = int(model.jnt_dofadr[rj])
        self.r_aid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_ACTUATOR, h.actuators["roller"])
        # the one output stage of all four motors (bodies/servo.py Actuators: the only writer of d.ctrl)
        self.out = SV.Actuators(model, aid + [self.r_aid], list(self.vadr) + [self.r_vadr],
                                tau + [L["dribbler"]["torque_max_nm"]], self.pdt)
        self.dribbler_act = self.out
        Mf = np.zeros((model.nv, model.nv))
        d0 = mj.MjData(model)
        d0.qpos[:] = data.qpos
        mj.mj_forward(model, d0)
        mj.mj_fullM(model, Mf, d0.qM)
        self.M3 = [float(Mf[i, i]) for i in self.vadr]       # the base's inertia for the acceleration feed-forward
        self.kp_v, self.kd_v, self.M3_v = np.array(self.kp), np.array(self.kd), np.array(self.M3)
        self._out = np.zeros(4)
        self._iq = [int(i) for i in self.qadr]
        self._iv = [int(i) for i in self.vadr]
        self.hinge_qadr = int(model.jnt_qposadr[jid(h.dribbler_hinge)])
        self.kp_drib = float(C["dribbler_kp"])
        Pa = D["dribbler_assist"]
        self.assist_on = bool(Pa.get("enabled", True))
        Lg = layout(D["geometry"])
        self.assist = Assist(Pa, (Lg["x_ball_rest"], 0.0), BALL_R)
        self.assist.m, self.assist.rdofs = model, self.vadr.copy()
        self.w_max = float(L["dribbler"]["speed_max_rpm"]) * 2 * math.pi / 60
        self.w_target = 0.0
        self.body_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_BODY, h.body)
        self._balls = [b for b in range(model.nbody) if model.body_jntnum[b] == 1 and model.body_mass[b] <= 0.1
                       and model.jnt_type[model.body_jntadr[b]] == mj.mjtJoint.mjJNT_FREE]
        self.site_a = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, h.sites["beam_a"])
        self.site_b = mj.mj_name2id(model, mj.mjtObj.mjOBJ_SITE, h.sites["beam_b"])
        self.kicker = Kicker(L["kicker"], np.random.default_rng(seed))
        self.events: list = []
        self.beam = (False, -1)
        self.resync_m = float(C["resync_m"])
        self._substeps_seen = 0
        self.target = None
        self.plan = None
        self._spin = None
        self.sync(data)

    # ------------------------------------------------------------------ state
    def pose(self, d):
        return d.qpos[self.qadr].copy()

    def vel(self, d):
        return d.qvel[self.vadr].copy()

    def sync(self, d):
        """the setpoint generator to the measured state (start, teleport, a collision push); holds the pose"""
        self.pb.reset(self.pose(d), self.vel(d))
        self._knots_reset()
        self.plan = None
        if self.target is None:
            q = self.pose(d)
            self._hold = q

    def place(self, d, x, y, yaw):
        """teleport (between steps, e.g. a restart): at rest at (x, y, yaw); the target becomes that pose"""
        d.qpos[self.qadr] = (x, y, yaw)
        d.qvel[self.vadr] = 0.0
        self.target = None
        self.sync(d)
        self._hold = np.array([x, y, yaw], float)

    # ------------------------------------------------------------------ skills
    def set_base_target(self, x, y, yaw, t=None, v_end=(0.0, 0.0)):
        """Move to (x, y, yaw) (world frame), arriving at match time t (None: as fast as the limits allow) moving
        at v_end = (vx, vy) (world frame; the robot moves on at v_end after arriving until the next command).
        Returns {"status": "ok" | "late", "eta": the planned arrival time} (late: t is earlier than the limits
        allow; the robot goes as fast as it can)."""
        vals = [float(v) for v in (x, y, yaw, *v_end)]
        if not all(math.isfinite(v) for v in vals):
            raise ValueError("set_base_target: finite numbers only")
        vend = np.array(vals[3:5])
        sp = float(np.linalg.norm(vend))
        status = "ok"
        if sp > self.base_lim.speed:                          # cannot arrive faster than the speed limit
            vend *= self.base_lim.speed / sp
            status = "clipped"
        self.target = dict(p=np.array(vals[0:2]), yaw=vals[2], t=None if t is None else float(t), v_end=vend)
        self._t_cmd = None
        plan = self._replan(float(self.d.time))
        eta = plan["eta"]
        if status == "ok" and t is not None and eta > float(t) + 0.02:
            status = "late"
        return {"status": status, "eta": round(eta, 3)}

    PLAN_ACCEL = 0.8      # the reference's share of the acceleration limit: PlanarBase follows it with a lag and
    PLAN_LEAD = 0.03      # overshoots a reference planned at the full limit (README "Base"); the lead (s) offsets the lag
    ETA_ACCEL = 0.75      # a direct move (PlanarBase to the goal, braking at BRAKE x A) takes about as long as a
                          # bang-bang profile at this share of A (measured: README "Base")

    def _replan(self, now):
        """the reference from the setpoint generator's current state to the target. A move to rest with no arrival
        time goes straight to PlanarBase (its own braking never overshoots); a timed move or one that ends moving
        follows a bang-bang reference (trajectory.Plan2D) at PLAN_ACCEL x the acceleration limit."""
        q, qd, _ = self.pb.state()
        T = self.target
        dur = None if T["t"] is None else max(0.0, T["t"] - now)
        direct = T["t"] is None and not np.any(T["v_end"])
        A = float(self.base_lim.accel) * (self.ETA_ACCEL if direct else self.PLAN_ACCEL)
        P = Plan2D(q[0:2], qd[0:2], T["p"], T["v_end"], self.base_lim.speed, A, dur)
        self.plan = dict(plan=P, t0=now - (0.0 if direct else self.PLAN_LEAD), eta=now + P.T, direct=direct)
        return self.plan

    def kick(self, speed, mode="flat", armed_for=0.0) -> str:
        """Discharge the kicker at `speed` (m/s; flat: horizontal, chip: 3-D at the chip angle) along the robot's
        heading: now (armed_for = 0: effective only if the ball is in the break beam) or the moment the beam is
        blocked within armed_for seconds. Returns "ok", "clipped" (beyond the machine's maximum: clipped),
        "kicker_not_ready" (the capacitor holds too little; the event says how long to wait) or "disarmed"
        (speed 0 cancels an armed kick)."""
        now = float(self.d.time)
        status, info = self.kicker.command(speed, mode, armed_for, now)
        if status == "kicker_not_ready":
            self.events.append(dict(event="kicker_not_ready", t=round(now, 4), **info))
        elif status == "clipped":
            self.events.append(dict(event="kick_clipped", t=round(now, 4), mode=mode, speed=info["speed"]))
        return status

    def dribble(self, rpm):
        """The dribbling bar's speed setpoint (rpm, 0 .. speed_max_rpm; negative = 0). The motor's speed loop is
        saturated at its torque limit, so the bar slows down when the ball resists (S3 2.2)."""
        rpm = float(rpm)
        if not math.isfinite(rpm):
            raise ValueError("dribble: a finite rpm")
        self.w_target = float(np.clip(rpm, 0.0, self.w_max * 60 / (2 * math.pi))) * 2 * math.pi / 60
        return "ok" if 0.0 <= rpm <= self.w_max * 60 / (2 * math.pi) else "clipped"

    # ------------------------------------------------------------------ the loops
    def _knots_reset(self):
        q, qd, qdd = self.pb.state()
        self.knots = [(q.copy(), qd.copy(), qdd.copy())]
        self._substeps_seen = 0
        self._t0 = float(self.d.time)
        self._dirty = True

    def _idle(self, st):
        """the setpoint at rest exactly on a resting goal (no plan in motion, no spin)"""
        if self._spin is not None or (self.plan is not None and not self.plan["direct"]):
            return False
        q, qd, qdd = st
        if np.any(np.abs(qd) > 1e-9) or np.any(np.abs(qdd) > 1e-9):
            return False
        g = (self.target["p"][0], self.target["p"][1], self.target["yaw"]) if self.target is not None else self._hold
        return abs(q[0] - g[0]) < 1e-9 and abs(q[1] - g[1]) < 1e-9 and abs(_wrap(q[2] - g[2])) < 1e-9

    def _reference(self, t):
        """the base's reference (r, rd) for time t (world frame)"""
        if self.plan is not None and self.plan["direct"]:
            p, v, yaw_goal = self.target["p"], (0.0, 0.0), self.target["yaw"]
        elif self.plan is not None:
            P = self.plan
            p, v = P["plan"].at(t - P["t0"])
            yaw_goal = self.target["yaw"]
        else:
            p, v, yaw_goal = self._hold[0:2], (0.0, 0.0), self._hold[2]
        y_sp = self.pb.yaw
        r = np.array([p[0], p[1], y_sp + _wrap(yaw_goal - y_sp)])
        rd = np.array([v[0], v[1], 0.0])
        if self._spin is not None:                           # tools/dribble_lab.py's turn test: spin on the spot
            r[2], rd[2] = y_sp + self._spin * self.sp_dt, self._spin
        return r, rd

    def step(self, model, data):
        """Once per 10 ms control step, before its physics steps: re-sync after a push, re-plan, and advance the
        setpoint generator over the step (its knots; substep interpolates them)."""
        self.d = data
        self._now = t = float(data.time)
        q, qsp = self.pose(data), self.knots[-1][0]
        err = float(math.hypot(q[0] - qsp[0], q[1] - qsp[1]))
        if err > self.resync_m or abs(_wrap(q[2] - qsp[2])) > 0.2:
            self.pb.reset(q, self.vel(data))
            self.events.append(dict(event="base_resync", t=round(t, 4), err_m=round(err, 4)))
            if self.target is None:
                self._hold = q
            if self.target is not None:                       # re-plan from where the push left the robot
                self._replan(t)
            self.knots = [self.pb.state()]
        start = self.knots[-1]
        if self._idle(start):                                # at rest on the goal: the generator would not move
            self.knots = [start, start]
        else:
            self.knots = [start]
            pb = self.pb
            for k in range(1, self.n_sp + 1):
                r, rd = self._reference(t + k * self.sp_dt)
                self.knots.append(pb.step(r, rd))            # bodies/servo.py PlanarBase: the limits
        self._t0 = t
        self._substeps_seen = 0
        self._dirty = True

    def _table(self):
        """the setpoints at the step's physics steps (cubic Hermite between the knots) and the PD's constant part
        u0 = kp q_sp + kd qd_sp + M qdd_sp, one row per physics step"""
        h, n = self.sp_dt, self.substeps
        tau = (np.arange(1, n + 1) * self.pdt)
        K = np.array([k[0] for k in self.knots]), np.array([k[1] for k in self.knots])
        if len(self.knots) == 1:
            q = np.repeat(K[0][0:1], n, 0)
            qd = np.repeat(K[1][0:1], n, 0)
            qdd = np.zeros_like(q)
        else:
            k = np.minimum((tau / h).astype(int), len(self.knots) - 2)
            s = np.clip((tau - k * h) / h, 0.0, 1.0)[:, None]
            P0, V0, P1, V1 = K[0][k], K[1][k] * h, K[0][k + 1], K[1][k + 1] * h
            s2, s3 = s * s, s * s * s
            q = (2 * s3 - 3 * s2 + 1) * P0 + (s3 - 2 * s2 + s) * V0 + (-2 * s3 + 3 * s2) * P1 + (s3 - s2) * V1
            qd = ((6 * s2 - 6 * s) * P0 + (3 * s2 - 4 * s + 1) * V0 + (-6 * s2 + 6 * s) * P1 + (3 * s2 - 2 * s) * V1) / h
            qdd = ((12 * s - 6) * P0 + (6 * s - 4) * V0 + (-12 * s + 6) * P1 + (6 * s - 2) * V1) / (h * h)
        self.sp_table = (q, qd, qdd)
        self.u0 = self.kp_v * q + self.kd_v * qd + self.M3_v * qdd

    def substep(self, model, data):
        """Every 1 ms physics step, before mujoco.mj_step: the base PD on the interpolated setpoint, the dribbler's
        motor, the kicker and its break beam, the dribbler's capped grip."""
        if self._dirty:
            self._table()
            self._dirty = False
        j = min(self._substeps_seen, self.substeps - 1)
        tau = self.u0[j] - self.kp_v * data.qpos[self.qadr] - self.kd_v * data.qvel[self.vadr] \
            + data.qfrc_bias[self.vadr]
        self._out[0:3] = tau
        self._out[3] = self.kp_drib * (self.w_target - data.qvel[self.r_vadr])
        self.out.write(data, self._out)
        self._misc(model, data)

    def _misc(self, model, data):
        """the cheap 1 kHz parts: the capacitor, the break beam, the armed kick, the dribbler's grip"""
        t = float(data.time)
        self._now = t
        k = self.kicker
        k.charge_step(self.pdt)
        if (self.w_target > 0.0 or k.armed is not None or k.pending is not None or self.assist.ball >= 0) \
                and self._ball_near(data):
            self.beam = self._beam(data)
        else:
            self.beam = (False, -1)                          # read on demand (state()) when nothing uses it
        self.assist.step(model, data, self.body_id, data.qpos[self.qadr], data.qvel[self.vadr], self.beam,
                         self.w_target > 0.0, self.assist_on)
        fire = None
        if k.pending is not None:
            fire, k.pending = k.pending, None
        elif k.armed is not None:
            if t > k.armed["until"]:
                self.events.append(dict(event="kick_expired", t=round(t, 4), mode=k.armed["mode"]))
                k.armed = None
            elif self.beam[0]:
                fire, k.armed = k.armed, None
        if fire is not None:
            self.assist.release("kick")
            self.assist.step(model, data, self.body_id, data.qpos[self.qadr], data.qvel[self.vadr], (False, -1),
                             False, False)
            yaw = float(data.qpos[self.qadr[2]])
            info = k.fire(model, data, self.body_id, self.beam[1], yaw, fire["speed"], fire["mode"])
            self.events.append(dict(event="kicked", t=round(t, 4), **info))
        self._substeps_seen += 1

    def _ball_near(self, d, r2=0.15 ** 2):
        """a cheap pre-check of the break beam: some light free body (a ball) within 0.15 m of the centre"""
        xp = d.xpos
        x, y = xp[self.body_id, 0], xp[self.body_id, 1]
        for b in self._balls:
            dx, dy = xp[b, 0] - x, xp[b, 1] - y
            if dx * dx + dy * dy < r2:
                return True
        return False

    def _beam(self, d):
        """the break beam: (blocked, the blocking body or -1)"""
        a, b = d.site_xpos[self.site_a], d.site_xpos[self.site_b]
        vec = b - a
        gid = np.zeros(1, np.int32)
        x = self.mj.mj_ray(self.m, d, a, vec, None, 1, self.body_id, gid)
        if 0.0 <= x <= 1.0:
            return True, int(self.m.geom_bodyid[gid[0]])
        return False, -1

    def state(self) -> dict:
        """The robot's own state (what its controller and the agent may read: no ball, no other robot): pose and
        velocity (world; vel_body in the robot's frame), the dribbler's speed and deflection, the capacitor, the
        break beam (ball_in_beam), the armed kick, the current target and its planned arrival."""
        data = self.d
        q, v = self.pose(data), self.vel(data)
        c, s = math.cos(q[2]), math.sin(q[2])
        k = self.kicker
        need_max = k.need(k.flat_max, "flat")
        return dict(
            t=round(float(data.time), 4),
            pose=[float(q[0]), float(q[1]), float(q[2])],
            vel=[float(v[0]), float(v[1]), float(v[2])],
            vel_body=[float(c * v[0] + s * v[1]), float(-s * v[0] + c * v[1]), float(v[2])],
            dribbler_rpm=float(data.qvel[self.r_vadr] * 60 / (2 * math.pi)),
            dribbler_target_rpm=float(self.w_target * 60 / (2 * math.pi)),
            dribbler_deflection_rad=float(data.qpos[self.hinge_qadr]),
            kicker_charge=round(float(k.charge), 4),
            kicker_wait_max_s=round(k.wait_s(need_max), 3),
            kicker_armed=None if k.armed is None else dict(mode=k.armed["mode"], speed=k.armed["speed"],
                                                          until=round(k.armed["until"], 4)),
            ball_in_beam=bool(self._beam(data)[0]),
            dribbler_engaged=bool(self.assist.ball >= 0),
            target=None if self.target is None else dict(x=float(self.target["p"][0]), y=float(self.target["p"][1]),
                                                         yaw=self.target["yaw"], t=self.target["t"],
                                                         v_end=self.target["v_end"].tolist()),
            eta=None if self.plan is None else round(self.plan["eta"], 3),
        )

    def take_events(self) -> list:
        out, self.events = self.events, []
        return out


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Group:
    """Several rigs in one model, driven together (the fast path; README "Speed"): per control step every rig's
    step (resync, plan, the setpoint generator's knots), one Hermite table for all of them; per physics step one
    vectorised PD for all bases and dribbler motors through one bodies/servo.py Actuators (the only writer of
    d.ctrl), then each rig's cheap 1 kHz parts (capacitor, break beam, armed kick, grip). The same arithmetic as
    Rig.substep, robot by robot."""

    def __init__(self, model, rigs):
        self.m, self.rigs = model, list(rigs)
        R = self.rigs
        self.qa = np.concatenate([r.qadr for r in R])
        self.va = np.concatenate([r.vadr for r in R])
        self.rv = np.array([r.r_vadr for r in R])
        self.kp = np.concatenate([r.kp_v for r in R])
        self.kd = np.concatenate([r.kd_v for r in R])
        self.M = np.concatenate([r.M3_v for r in R])
        self.kdr = np.array([r.kp_drib for r in R])
        aid = np.concatenate([r.out.aid[0:3] for r in R] + [np.array([r.r_aid for r in R])])
        vadr = np.concatenate([self.va, self.rv])
        tau = np.concatenate([r.out.tau_max[0:3] for r in R] + [np.array([r.out.tau_max[3] for r in R])])
        self.out = SV.Actuators(model, aid, vadr, tau, R[0].pdt)
        self.n = R[0].substeps
        s = (np.arange(1, self.n + 1) * R[0].pdt / R[0].sp_dt)[:, None]
        if R[0].n_sp != 1:
            raise ValueError("Group needs setpoint_dt_s == control_dt_s")
        s2, s3 = s * s, s * s * s
        h = R[0].sp_dt
        self.H = [(2 * s3 - 3 * s2 + 1), (s3 - 2 * s2 + s) * h, (-2 * s3 + 3 * s2), (s3 - s2) * h]
        self.Hd = [(6 * s2 - 6 * s) / h, (3 * s2 - 4 * s + 1), (-6 * s2 + 6 * s) / h, (3 * s2 - 2 * s)]
        self.Hdd = [(12 * s - 6) / h ** 2, (6 * s - 4) / h, (-12 * s + 6) / h ** 2, (6 * s - 2) / h]
        self._buf = np.zeros(len(aid))
        self.j = 0

    def step(self, data):
        for r in self.rigs:
            r.step(self.m, data)
            r._dirty = True
        P0 = np.concatenate([r.knots[0][0] for r in self.rigs])
        V0 = np.concatenate([r.knots[0][1] for r in self.rigs])
        P1 = np.concatenate([r.knots[-1][0] for r in self.rigs])
        V1 = np.concatenate([r.knots[-1][1] for r in self.rigs])
        X = (P0, V0, P1, V1)
        q = sum(c * x for c, x in zip(self.H, X))
        qd = sum(c * x for c, x in zip(self.Hd, X))
        qdd = sum(c * x for c, x in zip(self.Hdd, X))
        self.table = (q, qd, qdd)
        self.u0 = self.kp * q + self.kd * qd + self.M * qdd
        self.wt = np.array([r.w_target for r in self.rigs])
        self.j = 0

    def substep(self, data):
        j = min(self.j, self.n - 1)
        nb = len(self.qa)
        b = self._buf
        b[0:nb] = self.u0[j] - self.kp * data.qpos[self.qa] - self.kd * data.qvel[self.va] + data.qfrc_bias[self.va]
        b[nb:] = self.kdr * (self.wt - data.qvel[self.rv])
        self.out.write(data, b)
        for r in self.rigs:
            r._misc(self.m, data)
            r._substeps_seen += 1
        self.j += 1


_GROUPS: dict = {}


def step_world(model, data, rigs, substeps: int | None = None):
    """One control step of a world with these rigs (the fast path): Group.step, then per physics step
    Group.substep and mujoco.mj_step. The group is cached per (model, rigs)."""
    import mujoco as mj
    key = (id(model), tuple(id(r) for r in rigs))
    g = _GROUPS.get(key)
    if g is None:
        _GROUPS.clear()
        g = _GROUPS[key] = Group(model, rigs)
    g.step(data)
    for _ in range(substeps or g.n):
        g.substep(data)
        mj.mj_step(model, data)


class Body:
    """The registry's view (bodies.load_body("ssl_robot")): the module's mount / rig with the library's metadata."""
    kind = "planar"

    def __init__(self):
        self.decl = load_decl()
        self.name = self.decl["body"]["name"]
        self.revision = self.decl["body"]["revision"]

    mount = staticmethod(mount)
    rig = staticmethod(rig)


_BODY: dict = {}


def load() -> Body:
    if "b" not in _BODY:
        _BODY["b"] = Body()
    return _BODY["b"]
