"""Alpine skiing, slalom (FIS International Competition Rules, Alpine): one run down a slalom course of open
gates on a groomed slope, on the robot's own skis: both ski tips and both feet through every gate, then the finish."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.task import TaskBase

# ==================================================================================== BEGIN ski-snow block v3
# The equipment and the snow (the same block in alpine_slalom, giant_slalom, snowboard and the freeski
# families). Ported, with its authors'
# permission, from the ski-snow model of the Embodied Olympics freeski sport (github.com/CHIGUI0/roboolympics PR #259,
# branch sport-freeski, commit d566cffb4, sports/freeski/skisnow.py, MIT): frictionless condim-1 contacts of the planks'
# edge spheres with the snow, and, every 1 ms physics step, the tangential forces of the snow on every contact in the
# plank's own frame, plus the air's forces on every link (lift included). It follows that file's final version: 9 spheres
# per edge, a ski of three bodies (its forebody and afterbody on hinges with the ski's bending stiffness), hard well-
# damped snow (timeconst 5 ms, damping ratio 1.5), the forces' slope against the slip capped at K_V (the explicit
# step's stability), and solid planks (boxes over the running surface, shovel and tail, in stiff contact with every
# collision hull of the robot, the core's waist and shoulder shells, and the other plank). Changes in the port: the
# forces are written to d.xfrc_applied (at the bodies' centres of mass, torque included) instead of mj_applyFT; a plank
# is a free body held to the boot by a weld (the binding: rigid, as a real binding is until it releases) because the
# core mounts the robot after the family's build(); the snow is a profile of thin boxes (straight pieces and circular
# arcs in 25 cm steps), smooth enough that no snow pad (freeski's mocap boxes laid under each sphere) is needed; the
# solids collide by contact bits instead of explicit pairs (the robot's geoms do not exist yet at build()); the boot is
# mass on the plank, its forward-flex spring is not modelled; the air's drag is recomputed every physics step.
#
# Why a model of its own: MuJoCo's contact friction is isotropic in the tangent plane, a ski is not: it glides along
# its length and holds across it when it is edged. Per contact of a plank segment with the snow (Fn its normal force):
#   along   -mu_k(v) Fn sat(v_long): kinetic ski-snow friction, mu_k(v) after Wolfsperger, Meyer & Gilgien 2021
#           (Front. Mech. Eng. 7:728722): 0.043 at its optimum (6.5-11.5 m/s), up to +0.02 towards a standstill,
#           +0.003 per m/s above 11.5 m/s
#   across  -C sat(v_lat), C = mu_k Fn + min(Fn tan(phi), S_f e l): the snow carries the edged plank by the volume it
#           displaces (Mossner et al. 2013, J. Glaciol. 59(218):1170; Federolf's race-piste hardness H_V 0.21 N/mm^3 and
#           shear strength S_f 0.52 N/mm^2), so an edge at angle phi sinks e = sqrt(2 Fn tan(phi) / (H_V l)) and the snow
#           can hold its platform only up to its shear strength over the groove; a flat plank skids on its base
#   sidecut the "along" direction follows the arc of radius R_sc cos(phi) the edged plank is bent onto (Howe 2001;
#           Lieu & Mote 1985): an edged plank carves a turn of that radius, a flat one runs straight
# sat(v) = v / sqrt(v^2 + V0^2), V0 = max(0.03 m/s, force / K_V): each force opposes its own segment's sliding and never
# does positive work (an edged plank cannot climb, a sliding one cannot push itself). The snow's normal reaction is
# MuJoCo's soft contact. Air (lift included): every link of the robot and of the planks feels the quasi-steady
# normal-force aerodynamics of its hull's faces: along each of its own axes k, -0.5 rho C_N A_k |v| v_k (Hoerner's
# cross-flow principle; A_k the convex hull of its visual shapes projected along its axis k; C_N 1.17, a flat plate's),
# times the overlap factor (the robot's true silhouette over the links' summed areas, measured once standing). A flat
# inclined link (a ski, a trunk laid over the skis) gets lift across the flow as well as drag along it, a compact one
# drag: the posture decides both. Check: a V-style elite jumper made of plates (body 1.75 x 0.40 m,
# skis 2.60 x 0.11 m, a 35 degree V) gets L/q 0.63 m^2 and D/q 0.55 m^2 at 35 degrees of attack, inside what ski-jumping aerodynamics
# reports for elite flight (Schmolzer & Muller 2005, J. Biomech. 38:1055; Virmavirta et al. 2005, J. Biomech.
# 38:2157: lift areas about 0.6-0.8 m^2, drag areas about 0.5 m^2 at 30-40 degrees). The venue's air density is a
# mountain venue's, 1.052 kg/m^3 (ISA, about 2000 m at -10 C). MuJoCo's own fluid model is off in these worlds (it
# would count the air twice).
SNOW_BIT, PLANK_BIT, SOLID_BIT = 1, 2, 16    # the snow accepts the edge spheres (2), the feet (1), the hulls (4)
SNOW_CONAFF = 1 | 2 | 4 | 8
SOLID_CONAFF = 4 | 16                        # a plank's solid: the robot's hulls (4) and the other plank's solid (16);
#                                              the core's shells (SHELL_BIT) see it through its contype (world.py)
SNOW_RGBA = (0.94, 0.95, 0.98, 1)            # groomed snow (drawn flat white: looks.py leaves white surfaces alone)
SEG = 9                                      # contact spheres per edge along the running surface
SPHERE_R = 0.012
BIND_HALF = 0.18                             # the binding's half length: the rigid middle between the flex hinges (m)
K_V = 3000.0                                 # N s/m: the largest slope of a ski-snow force against the slip
PLANK_SOLREF = "0.005 1.5"                   # hard prepared snow: about 1 mm under a standing robot; well damped
PLANK_SOLIMP = "0.95 0.99 0.002"
SOLID_SOLREF = "0.004 1"                     # a plank against the robot's body and the other plank: stiff (freeski E11)
SOLID_SOLIMP = "0.99 0.999 0.0005"
BIND_SOLREF = "0.002 1"                      # the binding (a weld): as stiff as the 1 ms step allows
BIND_SOLIMP = "0.99 0.999 0.001"            # (0.95 0.99 let a thrashing leg stretch it 2 cm in a stress test)
AIR_RHO = 1.052
C_N = 1.17                                   # a flat plate's normal-force coefficient across the flow (Hoerner 1965,
#                                              Fluid-Dynamic Drag, ch. 3: 1.17 for a square plate normal to the flow)


class Plank:
    """A ski or a snowboard: metres and kilograms. `mount`: the binding centre's offset from the middle of the running
    surface (negative: behind); widths at the tip, the waist and the tail; `radius` the sidecut radius. For a
    snowboard `stance` is the distance between the two bindings' centres (0 for a ski). EI_fore / EI_aft: the bending
    stiffness (N m^2) of the forebody and the afterbody; None: a rigid plank."""

    def __init__(self, model, length, tip_w, waist_w, tail_w, radius, mass, mount, binding_mass, stand_h,
                 shovel=0.16, tail=0.10, tip_rise=0.06, tail_rise=0.025, thick=0.016, boot_mass=0.0, stance=0.0,
                 EI_fore=None, EI_aft=None):
        self.model, self.length, self.tip_w, self.waist_w, self.tail_w = model, length, tip_w, waist_w, tail_w
        self.radius, self.mass, self.mount, self.binding_mass, self.stand_h = radius, mass, mount, binding_mass, stand_h
        self.shovel, self.tail, self.tip_rise, self.tail_rise, self.thick = shovel, tail, tip_rise, tail_rise, thick
        self.boot_mass, self.stance = boot_mass, stance
        self.EI_fore, self.EI_aft = EI_fore, EI_aft

    @property
    def run_len(self):
        return self.length - self.shovel - self.tail

    @property
    def flex(self):
        return self.EI_fore is not None and self.EI_aft is not None

    def half_width(self, s):
        """Half the width at s along the running surface (s = 0 its middle, + forward): the sidecut's parabola."""
        h = 0.5 * self.run_len
        w = self.tip_w if s >= 0 else self.tail_w
        return 0.5 * self.waist_w + 0.5 * (w - self.waist_w) * min((s / h) ** 2, 1.0)

    def tip_x(self):
        """The front end of the plank (the shovel's tip) along it from the middle of the running surface."""
        return 0.5 * self.run_len + self.shovel

    def sphere_s(self):
        """(edge, name, s along the plank from its middle, z of the sphere's bottom, half width) of every contact
        sphere: SEG along each edge, one at the shovel and one at the tail."""
        H, L = 0.5 * self.run_len, self.run_len
        out = []
        for e in ("l", "r"):
            for i in range(SEG):
                s = -H + L * i / (SEG - 1)
                out.append((e, f"{e}{i}", s, 0.0, self.half_width(s)))
            out.append((e, f"{e}tipc", H + 0.55 * self.shovel, 0.55 * self.tip_rise, 0.42 * self.tip_w))
            out.append((e, f"{e}tailc", -H - 0.55 * self.tail, 0.55 * self.tail_rise, 0.42 * self.tail_w))
            # the shovel's and the tail's ends (without them a ski pitched into the snow sank its tip, a solid
            # that does not touch the snow, up to 8 cm: the stress test)
            out.append((e, f"{e}tipe", H + self.shovel - SPHERE_R, self.tip_rise - SPHERE_R, 0.42 * self.tip_w))
            out.append((e, f"{e}taile", -H - self.tail + SPHERE_R, self.tail_rise - SPHERE_R, 0.42 * self.tail_w))
        return out


def _f6(v):
    return " ".join(f"{float(x):.6g}" for x in v)


def _box_inertia(m, a, b, c):
    return m * (b * b + c * c) / 12, m * (a * a + c * c) / 12, m * (a * a + b * b) / 12


def add_plank(sc, name, pk: Plank, rgba=(0.85, 0.12, 0.10, 1), top_rgba=(0.95, 0.95, 0.95, 1), n_bind=1):
    """A free plank `name` (its frame: the middle of the running surface, x forward along it, z up from its base) with
    its binding(s) and boot(s) as mass, looks, two rows of edge spheres (the snow contacts) and raised spheres at the
    shovel and the tail, and solid boxes (`<name>_plate...`) for what the plank hits besides the snow. A flexing plank
    (pk.flex) is three bodies: `name` (the middle under the binding, rigid), `<name>_fore` and `<name>_aft` on hinges
    across the plank at the binding's ends, each with the torsional spring k = 3 EI / l of the ski's bending stiffness
    (a cantilever of length l with the same tip deflection) and a little damping (damping ratio about 0.1). Returns
    the parts' body names."""
    b = sc.body(name, (0.0, 0.0, -50.0), free=True)
    L, H, T = pk.run_len, 0.5 * pk.run_len, pk.thick
    mb = (pk.binding_mass + pk.boot_mass) * n_bind
    tot = pk.length
    if pk.flex:
        xf, xb = pk.mount + BIND_HALF, pk.mount - BIND_HALF          # the hinges along the plank from its middle
        segs = (("", xb, xf), ("_fore", xf, H + pk.shovel), ("_aft", -H - pk.tail, xb))
    else:
        xf, xb = H + pk.shovel, -H - pk.tail
        segs = (("", xb, xf),)
    parts, off = {"": b}, {"": 0.0}
    for nm, x0, x1 in segs[1:]:
        hinge = xf if nm == "_fore" else xb
        bb = ET.SubElement(b, "body", name=f"{name}{nm}", pos=_f6((hinge, 0.0, 0.0)))
        ln = abs(x1 - hinge) - (pk.shovel if nm == "_fore" else pk.tail)
        EI = pk.EI_fore if nm == "_fore" else pk.EI_aft
        k = 3.0 * EI / max(ln, 0.05)
        seg_m = pk.mass * (x1 - x0) / tot
        Iy = seg_m * (x1 - x0) ** 2 / 3.0
        ET.SubElement(bb, "joint", name=f"{name}{nm}_flex", type="hinge", axis="0 1 0", stiffness=f"{k:.5g}",
                      damping=f"{0.2 * math.sqrt(k * Iy):.4g}", range="-0.35 0.35", armature="0.0005")
        parts[nm], off[nm] = bb, hinge
    for nm, x0, x1 in segs:
        seg_m = pk.mass * (x1 - x0) / tot
        c = 0.5 * (x0 + x1) - off[nm]
        if nm == "":                               # the binding(s) and the boot(s) ride on the middle
            m_tot = seg_m + mb
            Ixx, Iyy, Izz = _box_inertia(seg_m, x1 - x0, pk.waist_w, T)
            dx = pk.mount - c
            Ixx += mb * (0.07 ** 2 + 0.06 ** 2) / 12
            Iyy += mb * ((0.3 ** 2 + 0.06 ** 2) / 12 + dx ** 2)
            Izz += mb * ((0.3 ** 2 + 0.07 ** 2) / 12 + dx ** 2)
            ET.SubElement(b, "inertial", pos=_f6(((seg_m * c + mb * pk.mount) / m_tot, 0, T + 0.02)),
                          mass=f"{m_tot:.5g}", diaginertia=_f6((Ixx, Iyy, Izz)))
        else:
            ET.SubElement(parts[nm], "inertial", pos=_f6((c, 0, 0.5 * T)), mass=f"{seg_m:.5g}",
                          diaginertia=_f6(_box_inertia(seg_m, x1 - x0, pk.waist_w, T)))

    def part_of(s):
        return "" if xb <= s <= xf else ("_fore" if s > xf else "_aft")

    n = 12
    for i in range(n):                         # the running surface with its sidecut (looks only)
        s0, s1 = -H + L * i / n, -H + L * (i + 1) / n
        sm = 0.5 * (s0 + s1)
        p = part_of(sm)
        hw = pk.half_width(sm)
        sc.geom(parts[p], f"{name}_v{i}", type="box", pos=(sm - off[p], 0, 0.5 * T), size=(0.5 * (s1 - s0) + 2e-4, hw,
                0.5 * T), rgba=rgba, group=1, mass=0, contype=0, conaffinity=0)
        sc.geom(parts[p], f"{name}_t{i}", type="box", pos=(sm - off[p], 0, T + 0.0006), size=(0.5 * (s1 - s0) + 2e-4,
                0.45 * pk.waist_w, 0.0007), rgba=top_rgba, group=1, mass=0, contype=0, conaffinity=0)
    solid = dict(contype=SOLID_BIT, conaffinity=SOLID_CONAFF, condim=3, priority=1, friction=(0.5, 0.005, 0.0001),
                 solref=SOLID_SOLREF, solimp=SOLID_SOLIMP, group=3, mass=0, rgba=(0.9, 0.3, 0.3, 0.3))
    for nm, sgn, ln, rise, wd in (("tip", 1, pk.shovel, pk.tip_rise, pk.tip_w), ("tail", -1, pk.tail, pk.tail_rise,
                                                                                   pk.tail_w)):
        ang = math.atan2(rise, ln)
        p = part_of(sgn * (H + 0.5 * ln))
        kw = dict(type="box", pos=(sgn * (H + 0.5 * ln) - off[p], 0, 0.5 * T + 0.5 * rise), euler=(0, -sgn * ang, 0),
                  size=(0.5 * math.hypot(ln, rise), 0.40 * wd, 0.5 * T))     # (inside the end spheres' cover)
        sc.geom(parts[p], f"{name}_{nm}", rgba=rgba, group=1, mass=0, contype=0, conaffinity=0, **kw)
        sc.geom(parts[p], f"{name}_plate_{nm}", **kw, **solid)        # the upturned shovel / tail: solid too
    for nm, x0, x1 in segs:                    # the solids over the running surface, one per part
        a, c_ = max(x0, -H), min(x1, H)
        hw = min(pk.half_width(a), pk.half_width(c_), pk.half_width(0.5 * (a + c_)))
        sc.geom(parts[nm], f"{name}_plate{nm}", type="box", pos=(0.5 * (a + c_) - off[nm], 0, 0.5 * T),
                size=(0.5 * (c_ - a), hw, 0.5 * T), **solid)
    offs = [0.0] if n_bind == 1 else [-0.5 * pk.stance, 0.5 * pk.stance]
    for k, o in enumerate(offs):               # binding(s): looks
        x0 = pk.mount + o
        sc.geom(b, f"{name}_bind{k}", type="box", pos=(x0, 0, T + 0.5 * pk.stand_h),
                size=(0.15, 0.03, 0.5 * pk.stand_h - 0.002) if n_bind == 1 else (0.04, 0.13, 0.5 * pk.stand_h - 0.002),
                rgba=(0.18, 0.18, 0.2, 1), group=1, mass=0, contype=0, conaffinity=0)
    r = SPHERE_R
    for e, nm, s_, z, hw in pk.sphere_s():
        sgn = 1 if e == "l" else -1
        p = part_of(s_)
        sc.geom(parts[p], f"{name}_e{nm}", type="sphere", size=(r,), pos=(s_ - off[p], sgn * (hw - r), z + r),
                contype=PLANK_BIT, conaffinity=0, condim=1, priority=2, group=4, mass=0, solref=PLANK_SOLREF,
                solimp=PLANK_SOLIMP, rgba=(0.3, 0.3, 0.9, 0.5))
    return [f"{name}{nm}" for nm, _, _ in segs]


def bind(sc, plank, foot, relpos, relquat=(1, 0, 0, 0), name=None):
    """The binding: a weld of the plank to the foot body; relpos / relquat: the plank's frame in the foot's frame."""
    ET.SubElement(sc.root.find("equality"), "weld", name=name or f"binding_{plank}_{foot}", body1=foot, body2=plank,
                  relpose=_f6(tuple(relpos) + tuple(relquat)), solref=BIND_SOLREF, solimp=BIND_SOLIMP)


def no_fluid(sc):
    """The world's air is this block's drag model: MuJoCo's own fluid forces off (they would count the air twice)."""
    opt = sc.root.find("option")
    for k in ("density", "viscosity"):
        opt.attrib.pop(k, None)


def _hull_poly(pts2):
    p = np.unique(np.round(pts2, 6), axis=0)
    if len(p) < 3:
        return p
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for q in p:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], q) <= 0:
            lower.pop()
        lower.append(tuple(q))
    for q in p[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], q) <= 0:
            upper.pop()
        upper.append(tuple(q))
    return np.array(lower[:-1] + upper[:-1])


def _hull_area(pts2):
    h = _hull_poly(pts2)
    if len(h) < 3:
        return 0.0
    x, y = h[:, 0], h[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _geom_points(m, g):
    t, size = m.geom_type[g], m.geom_size[g]
    if t == mujoco.mjtGeom.mjGEOM_MESH:
        mid = int(m.geom_dataid[g])
        P = m.mesh_vert[m.mesh_vertadr[mid]:m.mesh_vertadr[mid] + m.mesh_vertnum[mid]].astype(float)
    elif t == mujoco.mjtGeom.mjGEOM_BOX:
        P = np.array([[a, b, c] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]) * size
    else:
        r = size[0]
        hz = size[1] if t in (mujoco.mjtGeom.mjGEOM_CAPSULE, mujoco.mjtGeom.mjGEOM_CYLINDER) else 0.0
        a = np.linspace(0, 2 * np.pi, 16, endpoint=False)
        ring = np.stack([r * np.cos(a), r * np.sin(a), 0 * a], 1)
        P = np.concatenate([ring + [0, 0, z] for z in (-hz, hz)] + [np.array([[0, 0, -hz - r], [0, 0, hz + r]])])
    R = np.zeros(9)
    mujoco.mju_quat2Mat(R, m.geom_quat[g])
    return P @ R.reshape(3, 3).T + m.geom_pos[g]


class SnowModel:
    """The snow's tangential forces on the planks and the air's drag on the robot and the planks, written to
    d.xfrc_applied after every physics step from that step's contacts (the forces of the next step)."""

    def __init__(self, w, planks: dict, snow_geoms, H_V=0.21e9, S_f=0.52e6, mu_opt=0.043, cd=None, v0=0.03,
                 phi_max_deg=70.0):
        m = w.m
        self.m, self.H_V, self.S_f, self.mu_opt, self.cd, self.v0 = m, H_V, S_f, mu_opt, C_N if cd is None else cd, v0
        self.phi_max = math.radians(phi_max_deg)
        self.is_snow = np.zeros(m.ngeom, bool)
        self.is_snow[[m.geom(n).id for n in snow_geoms]] = True
        self.seg_body = np.full(m.ngeom, -1, int)
        self.seg_s, self.seg_len, self.seg_w = np.zeros(m.ngeom), np.zeros(m.ngeom), np.zeros(m.ngeom)
        self.radius = np.ones(m.nbody) * 1e9
        self.plank_ids = []
        for name, pk in planks.items():
            L = pk.run_len
            for e, nm, s, _, hw in pk.sphere_s():
                g = m.geom(f"{name}_e{nm}").id
                bid = int(m.geom_bodyid[g])
                if bid not in self.plank_ids:
                    self.plank_ids.append(bid)
                self.radius[bid] = pk.radius
                self.seg_body[g], self.seg_s[g] = bid, s
                if nm[1:] in ("tipc", "tailc", "tipe", "taile"):
                    self.seg_len[g] = 0.5 * L / (SEG - 1)
                    self.seg_w[g] = pk.tip_w if nm[1:].startswith("tip") else pk.tail_w
                else:
                    i = int(nm[1:])
                    self.seg_len[g] = L / (SEG - 1) * (0.5 if i in (0, SEG - 1) else 1.0)
                    self.seg_w[g] = 2 * hw
        self.is_seg = self.seg_body >= 0
        # the drag's links: the robot's bodies with visual shapes, and the planks' parts
        bs, cs, As, pts = [], [], [], []
        for b in sorted(set(w.robot.bodies) | set(self.plank_ids)):
            gs = [g for g in range(m.ngeom) if m.geom_bodyid[g] == b and m.geom_group[g] in (1, 2)]
            if not gs:
                continue
            P = np.concatenate([_geom_points(m, g) for g in gs])
            c = 0.5 * (P.min(0) + P.max(0))
            bs.append(b)
            cs.append(c)
            As.append([_hull_area(P[:, [1, 2]]), _hull_area(P[:, [0, 2]]), _hull_area(P[:, [0, 1]])])
            pts.append(P)
        self.drag_b, self.drag_c, self.drag_A = np.array(bs, int), np.array(cs), np.array(As)
        self.drag_root = m.body_rootid[self.drag_b]
        self.overlap = self._overlap(w, pts)
        self.bodies = np.unique(np.r_[self.drag_b, self.plank_ids]).astype(int)
        self.last = {}

    def _overlap(self, w, pts, res=0.01) -> float:
        """The robot's true silhouette seen from the front over its links' summed areas (standing as at t = 0, before
        the family places it; the planks excluded)."""
        m = self.m
        d0 = mujoco.MjData(m)
        mujoco.mj_kinematics(m, d0)
        rob = [i for i, b in enumerate(self.drag_b) if b not in self.plank_ids]
        u = d0.xmat[w.robot.pelvis].reshape(3, 3)[:, 0]
        e1 = np.cross(u, [0.0, 0.0, 1.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(u, e1)
        polys, summed = [], 0.0
        for i in rob:
            b = self.drag_b[i]
            R = d0.xmat[b].reshape(3, 3)
            W_ = pts[i] @ R.T + d0.xpos[b]
            polys.append(_hull_poly(np.stack([W_ @ e1, W_ @ e2], 1)))
            loc = R.T @ u
            summed += float(np.sum(np.abs(loc) * self.drag_A[i]))
        allp = np.concatenate([p for p in polys if len(p) >= 3])
        lo, hi = allp.min(0) - res, allp.max(0) + res
        gx, gy = np.meshgrid(np.arange(lo[0], hi[0], res), np.arange(lo[1], hi[1], res))
        q = np.stack([gx.ravel(), gy.ravel()], 1)
        inside = np.zeros(len(q), bool)
        for h in polys:
            if len(h) < 3:
                continue
            ok = np.ones(len(q), bool)
            for k in range(len(h)):
                a0, a1 = h[k], h[(k + 1) % len(h)]
                ok &= ((a1[0] - a0[0]) * (q[:, 1] - a0[1]) - (a1[1] - a0[1]) * (q[:, 0] - a0[0])) >= 0
            inside |= ok
        return float(inside.sum() * res * res) / max(summed, 1e-9)

    def mu_k(self, v):
        v = np.abs(v)
        return self.mu_opt + 0.02 * np.clip((6.5 - v) / 3.2, 0.0, 1.0) + 0.003 * np.maximum(v - 11.5, 0.0)

    def apply(self, d) -> None:
        m = self.m
        xf = d.xfrc_applied
        xf[self.bodies] = 0.0
        # the air
        b = self.drag_b
        R = d.xmat[b].reshape(-1, 3, 3)
        cpos = d.xpos[b] + np.einsum("bij,bj->bi", R, self.drag_c)
        cv = d.cvel[b]
        vel = cv[:, 3:] + np.cross(cv[:, :3], cpos - d.subtree_com[self.drag_root])
        sp = np.linalg.norm(vel, axis=1)
        loc = np.einsum("bji,bj->bi", R, vel / np.maximum(sp, 1e-9)[:, None])
        # the quasi-steady normal-force model: each face of a link's hull pushes back along its own normal with
        # 0.5 rho C_N A_k |v| v_k (Hoerner's cross-flow principle): an inclined flat link (a ski, a flat trunk) gets lift
        # across the flow as well as drag along it; a compact link, drag nearly along -v. F . v <= 0 always.
        Fl = -0.5 * AIR_RHO * self.cd * self.overlap * sp[:, None] * (self.drag_A * (loc * sp[:, None]))
        F = np.einsum("bij,bj->bi", R, Fl)
        xf[b, :3] = F
        xf[b, 3:] = np.cross(cpos - d.xipos[b], F)
        self.last = {"drag_n": float(np.linalg.norm(F.sum(0))), "n": 0}
        # the snow
        nc = d.ncon
        if nc == 0:
            return
        con = d.contact
        g1, g2 = con.geom1[:nc], con.geom2[:nc]
        a = self.is_seg[g1] & self.is_snow[g2]
        bb = self.is_seg[g2] & self.is_snow[g1]
        sel = np.nonzero((a | bb) & (con.efc_address[:nc] >= 0))[0]
        if len(sel) == 0:
            return
        seg = np.where(a[sel], g1[sel], g2[sel])
        pos = con.pos[sel]
        nrm = con.frame[sel, :3] * np.where(a[sel], -1.0, 1.0)[:, None]
        fn = np.maximum(d.efc_force[con.efc_address[sel]], 0.0)
        body = self.seg_body[seg]
        Rs = d.xmat[body].reshape(-1, 3, 3)
        xs, ys = Rs[:, :, 0], Rs[:, :, 1]
        cvb = d.cvel[body]
        v = cvb[:, 3:] + np.cross(cvb[:, :3], pos - d.subtree_com[m.body_rootid[body]])

        def dot(u, q):
            return np.sum(u * q, axis=1)

        phi = np.arcsin(np.clip(dot(ys, nrm), -1.0, 1.0))      # + : rolled onto the right (-y) edge
        aphi = np.minimum(np.abs(phi), self.phi_max)
        t0 = xs - dot(xs, nrm)[:, None] * nrm
        t0 /= np.maximum(np.linalg.norm(t0, axis=1), 1e-9)[:, None]
        l0 = np.cross(nrm, t0)
        engage = np.clip(aphi / math.radians(5.0), 0.0, 1.0)    # the sidecut's arc engages from 0 to 5 degrees
        kappa = -np.sign(phi) * engage / (self.radius[body] * np.cos(aphi))
        al = kappa * self.seg_s[seg]
        t = np.cos(al)[:, None] * t0 + np.sin(al)[:, None] * l0
        lat = np.cross(nrm, t)
        vt = v - dot(v, nrm)[:, None] * nrm
        vl, vq = dot(vt, t), dot(vt, lat)
        mu = self.mu_k(np.linalg.norm(vt, axis=1))
        ln = self.seg_len[seg]
        V = fn / self.H_V                                        # the displaced volume (Mossner et al. 2013)
        tp = np.tan(aphi)
        bw = self.seg_w[seg]
        e_wedge = np.sqrt(2.0 * V * np.maximum(tp, 1e-6) / ln)
        e_full = V / (ln * bw) + 0.5 * bw * np.sin(aphi)
        e = np.where(e_wedge <= bw * np.sin(aphi), e_wedge, e_full)
        cap = mu * fn + np.minimum(fn * tp, self.S_f * e * ln)
        vl0 = np.maximum(self.v0, mu * fn / K_V)                 # the forces' slope at zero slip at most K_V
        vq0 = np.maximum(self.v0, cap / K_V)
        f_long = -mu * fn * vl / np.sqrt(vl * vl + vl0 ** 2)
        f_lat = -cap * vq / np.sqrt(vq * vq + vq0 ** 2)
        Fc = f_long[:, None] * t + f_lat[:, None] * lat
        Tc = np.cross(pos - d.xipos[body], Fc)
        np.add.at(xf, (body, slice(0, 3)), Fc)
        np.add.at(xf, (body, slice(3, 6)), Tc)
        self.last.update(n=len(sel), fn=float(fn.sum()), phi_deg=float(np.degrees(np.mean(phi))),
                         f_long=float(f_long.sum()), f_lat=float(f_lat.sum()))


class Digest:
    """The applied forces in the state hash (they carry the last physics step's contact forces into the next)."""

    def __init__(self, w, bodies):
        self.w, self.b = w, np.asarray(sorted(set(bodies)), int)

    def state(self):
        return [round(float(x), 9) for x in self.w.d.xfrc_applied[self.b].ravel()]


class Profile:
    """A snow surface's long profile z(x) of straight lines and circular arcs (freeski's lines.py), extruded across
    the course: built as thin tilted boxes, one per piece (a slab under the surface)."""

    def __init__(self, x0=0.0, z0=0.0, angle_deg=0.0):
        self.pts = [(x0, z0)]
        self.ang = math.radians(angle_deg)
        self.marks = {}
        self.idx = {}

    @property
    def end(self):
        return self.pts[-1]

    def mark(self, name):
        self.marks[name] = self.end
        self.idx[name] = len(self.pts) - 1
        return self

    def line(self, length, angle_deg=None):
        if angle_deg is not None:
            self.ang = math.radians(angle_deg)
        x, z = self.end
        self.pts.append((x + length * math.cos(self.ang), z + length * math.sin(self.ang)))
        return self

    def arc(self, radius, to_angle_deg, step=0.25):
        a1 = math.radians(to_angle_deg)
        da = a1 - self.ang
        if abs(da) < 1e-12:
            return self
        n = max(2, int(math.ceil(abs(da) * radius / step)))
        x, z = self.end
        sgn = 1.0 if da > 0 else -1.0
        cx, cz = x - sgn * radius * math.sin(self.ang), z + sgn * radius * math.cos(self.ang)
        for i in range(1, n + 1):
            a = self.ang + da * i / n
            self.pts.append((cx + sgn * radius * math.sin(a), cz - sgn * radius * math.cos(a)))
        self.ang = a1
        return self

    def arrays(self):
        p = np.array(self.pts)
        return p[:, 0], p[:, 1]

    def z_at(self, x):
        xs, zs = self.arrays()
        return np.interp(x, xs, zs)

    def slope_at(self, x):
        """The surface's angle (rad, + rising along +x) at x."""
        xs, zs = self.arrays()
        i = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
        return math.atan2(zs[i + 1] - zs[i], xs[i + 1] - xs[i])

    def build(self, sc, prefix, half_width, rgba=SNOW_RGBA, thick=1.0, y=0.0, i0=0, i1=None, material=None):
        """The snow: one box per piece (pieces i0 .. i1 - 1), overlapping its neighbours by 2 mm (at a convex bend the
        overlap is a ridge of 2 mm x the bend's angle: 0.06 mm on a 25 cm piece of an 8 m arc). half_width and thick
        may be functions of the piece's middle x. Returns the geoms' names."""
        xs, zs = self.arrays()
        i1 = len(xs) - 1 if i1 is None else i1
        names = []
        for i in range(i0, i1):
            dx, dz = xs[i + 1] - xs[i], zs[i + 1] - zs[i]
            L = math.hypot(dx, dz)
            a = math.atan2(dz, dx)
            ux, uz = dx / L, dz / L
            nx, nz = -uz, ux                       # the surface's normal
            xm = 0.5 * (xs[i] + xs[i + 1])
            th = thick(xm) if callable(thick) else thick
            hw = half_width(xm) if callable(half_width) else half_width
            cx = xm - nx * 0.5 * th
            cz = 0.5 * (zs[i] + zs[i + 1]) - nz * 0.5 * th
            nm = f"{prefix}{i}"
            look = dict(material=material) if material else dict(rgba=rgba)
            sc.geom(sc.wb, nm, type="box", pos=(cx, y, cz), size=(0.5 * L + 0.002, hw, 0.5 * th),
                    quat=(math.cos(-a / 2), 0.0, math.sin(-a / 2), 0.0), **look, contype=SNOW_BIT,
                    conaffinity=SNOW_CONAFF, friction=(0.35, 0.005, 0.0001), condim=3, solref=PLANK_SOLREF,
                    solimp=PLANK_SOLIMP, priority=1)    # one snow for the skis and the body: its parameters win
                    #                                     (the body's soft default contact sank it 5-10 cm)
            names.append(nm)
        return names


def rot_y(a):
    return np.array([math.cos(a / 2), 0.0, math.sin(a / 2), 0.0])


def qmul(a, b):
    out = np.zeros(4)
    mujoco.mju_mulQuat(out, np.asarray(a, float), np.asarray(b, float))
    return out


def place_on_slope(w, slope_rad, zfun, planks: dict, legs=None):
    """t = 0: the robot standing perpendicular to the snow (the surface z = zfun(x), falling at slope_rad along +x;
    0: a level start platform), its planks under its boots as the bindings hold them, resting on the snow. planks: name
    -> (foot body, relpos, relquat) of its binding. legs: the 12 leg joint angles to start in (default: as they are);
    the leg motors hold them (the arbiter's stand hold)."""
    m, d, r = w.m, w.d, w.robot
    a = r.arb
    if legs is not None:
        d.qpos[r.qadr[:12]] = legs
    fq = r.fq
    d.qpos[fq + 3:fq + 7] = qmul(rot_y(slope_rad), d.qpos[fq + 3:fq + 7])
    mujoco.mj_kinematics(m, d)
    for name, (foot, relpos, relquat) in planks.items():  # each plank where its binding holds it
        b = m.body(foot).id
        R = d.xmat[b].reshape(3, 3)
        w.put(name, d.xpos[b] + R @ np.asarray(relpos, float), qmul(d.xquat[b], relquat))
    mujoco.mj_kinematics(m, d)
    c = math.cos(slope_rad)
    gaps = [(float(d.geom_xpos[g][2]) - float(zfun(float(d.geom_xpos[g][0])))) * c - SPHERE_R
            for g in range(m.ngeom) if "_e" in m.geom(g).name and m.geom(g).name.rsplit("_e", 1)[0] in planks]
    dz = -(min(gaps) + 0.0003) / c                # the lowest edge sphere 0.3 mm into the snow
    d.qpos[fq + 2] += dz
    for name in planks:
        d.qpos[w.free[name][0] + 2] += dz
    L = a.GROUPS["legs"]
    a.q_a[L] = a.q_b[L] = d.qpos[a.qadr[L]]
    mujoco.mj_kinematics(m, d)


# ------------------------------------------------------------------------ how a ski venue looks (and its solid fences)
# Groomed snow: near-white with a fine grain and a faint corduroy of the piste machine (looks.py leaves white surfaces
# alone, so the snow brings its own material); the course's fences are solid (a robot sliding off the course meets
# them, it never passes through), their posts, banners and markers looks only (merged meshes: looks._Batch).
SNOW_MAT = "eo_snow"
FENCE_RGBA = (0.95, 0.35, 0.08, 0.55)        # an orange safety net
FENCE_CONTACT = dict(contype=1, conaffinity=1 | 4 | 8 | 16, condim=3, friction=(0.6, 0.005, 0.0001),
                     solref="0.02 1", solimp="0.9 0.95 0.001")   # a net: soft (it gives, about 2 cm under a body)


def snow_material(sc) -> str:
    asset = sc.root.find("asset")
    if not any(t.get("name") == SNOW_MAT for t in asset.findall("material")):
        ET.SubElement(asset, "texture", name=SNOW_MAT, type="2d", builtin="checker", rgb1="0.965 0.97 0.985",
                      rgb2="0.935 0.945 0.97", mark="random", markrgb="0.88 0.9 0.95", random="0.06",
                      width="512", height="512")
        ET.SubElement(asset, "material", name=SNOW_MAT, texture=SNOW_MAT, texuniform="true", texrepeat="0.8 6",
                      specular="0.25", shininess="0.3", reflectance="0.02")
    return SNOW_MAT


def snow_side_terrain(sc, pr, prefix, i0, i1, inner, outer, z_of=None, thick=2.0) -> list:
    """Snow terrain beside the course (both sides, from the course's edge `inner` to `outer` m from its centre line),
    flush with the profile's pieces i0 .. i1 - 1 (or with z_of(x), a flat level, when given). Returns the geoms."""
    xs, zs = pr.arrays()
    names = []
    for side in (1, -1):
        y = side * 0.5 * (inner + outer)
        if z_of is None:
            names += pr.build(sc, f"{prefix}{'L' if side > 0 else 'R'}", 0.5 * (outer - inner), thick=thick, y=y,
                              i0=i0, i1=i1, material=snow_material(sc))
        else:
            x0, x1 = xs[i0], xs[i1]
            nm = f"{prefix}{'L' if side > 0 else 'R'}"
            sc.geom(sc.wb, nm, type="box", pos=(0.5 * (x0 + x1), y, z_of - 0.5 * thick),
                    size=(0.5 * (x1 - x0) + 0.002, 0.5 * (outer - inner), 0.5 * thick), material=snow_material(sc),
                    contype=SNOW_BIT, conaffinity=SNOW_CONAFF, friction=(0.35, 0.005, 0.0001), condim=3,
                    solref=PLANK_SOLREF, solimp=PLANK_SOLIMP, priority=1)
            names.append(nm)
    return names


def fence_line(sc, batch, prefix, zfun, x0, x1, y, height=1.2, step=2.0) -> None:
    """A solid safety net along the course at y from x0 to x1, following the snow (zfun(x)): one thin panel per
    `step` m and a post at each panel's end (looks)."""
    n = max(1, int(math.ceil((x1 - x0) / step)))
    for i in range(n):
        a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
        za, zb = float(zfun(a)), float(zfun(b))
        L = math.hypot(b - a, zb - za)
        ang = math.atan2(zb - za, b - a)
        sc.geom(sc.wb, f"{prefix}{i}", type="box", pos=(0.5 * (a + b), y, 0.5 * (za + zb) + 0.5 * height),
                size=(0.5 * L, 0.01, 0.5 * height), quat=(math.cos(-ang / 2), 0.0, math.sin(-ang / 2), 0.0),
                rgba=FENCE_RGBA, group=1, **FENCE_CONTACT)
        batch.add((0.25, 0.25, 0.27), (b, y, zb + 0.5 * height + 0.05), (0.025, 0.025, 0.5 * height + 0.05))


def arch(batch, x, y, z, half_w, height=3.0, rgb=(0.12, 0.3, 0.75)) -> None:
    """A banner arch across the course at x (looks): two posts and the banner."""
    for s_ in (1, -1):
        batch.add((0.2, 0.2, 0.22), (x, y + s_ * half_w, z + 0.5 * height), (0.08, 0.08, 0.5 * height))
    batch.add(rgb, (x, y, z + height - 0.25), (0.05, half_w, 0.3))
    batch.add((0.95, 0.95, 0.95), (x - 0.06, y, z + height - 0.25), (0.005, 0.8 * half_w, 0.12))
# ====================================================================================== END ski-snow block v3

# ==================================================================================== BEGIN alpine-race block v2
# A race through gates on a groomed slope (the same block in alpine_slalom, giant_slalom and snowboard): the slope, the flex poles and the gates, the start, the referee of gate
# passing (FIS ICR 661.4), the finish and the falls. The start as the Embodied Olympics freeski sport's
# (github.com/CHIGUI0/roboolympics PR #259, sport.toml D6 / D8, MIT): no start gate and nothing that holds or
# releases the robot: it stands on a level start platform (6 m) behind the start line, the platform's edge rounded
# (the brink) onto the slope, and leaves it by its own action; the clock starts when its boots cross the start line.
POLE_R = 0.014                 # m: a 28 mm slalom pole (ICR 680: a round pole; FIS children rules: 25-27 mm, ICR
#                                803.2.1: light flex poles of 25-28.9 mm for U16-U14)
POLE_H = 1.80                  # m above the snow (ICR 680; the poles' FIS specification: at least 1.80 m out of the snow)
POLE_MASS = 0.60               # kg (a fibreglass pole and its flex head: estimate)
POLE_HINGE_Z = 0.03            # m: the flex head's pivot above the snow (the pole's base below it is screwed into the snow)
POLE_K = 20.0                  # N m / rad: the flex head's return spring (estimate: no published figure; a shin's
#                                shove of about 15 N at knee height folds it 20 degrees; it lies down under a body)
POLE_DAMP = 0.6                # N m s / rad (estimate)
POLE_FOLD = 1.45               # rad: how far it folds before its base stops it (nearly flat)
RED, BLUE = (0.85, 0.12, 0.12, 1), (0.10, 0.25, 0.80, 1)
FLAG_W, FLAG_H, FLAG_Z = 0.75, 0.50, 1.00    # m: a GS panel (ICR 901.2.2: about 75 x 50 cm, lower edge >= 1 m up)
TRACK = ("left_tip", "right_tip", "left_foot", "right_foot")   # what must cross every gate line (ICR 661.4.1)
TRACK_BOARD = ("nose", "tail", "left_foot", "right_foot")      # a snowboard's
BRINK_BACK = 1.0               # m: the brink's arc meets the slope this far up the slope from x = 0 (the gates' origin)


class AlpineRace(TaskBase):
    """The race: the profile and the gates from params; the referee. A family sets params, the plank(s) and texts."""
    category = "track-and-jumps"
    robot = "unitree_g1"
    fall_rule = False                                # the snow's own fall rule (step)
    legal_ground = ("left_foot", "right_foot", "left_hand", "right_hand")
    gate_kind = "sl"                                 # "sl": one flex pole per side; "gs": a pair with a panel; "psl":
    #                                                  snowboard parallel slalom's triangular panel on two poles
    planks: dict = {}                                # plank body -> (Plank, foot body, relpos, relquat)
    track = TRACK

    # ------------------------------------------------------------------ the geometry
    def slope(self):
        return math.radians(self.p["slope_deg"])

    def profile(self) -> Profile:
        """The level start platform ({platform_m} m), its edge (the start line) rounded by the brink's arc onto the
        slope, the straight slope through (0, 0) (the gates are measured along it from there), the outrun."""
        p = self.p
        th = p["slope_deg"]
        t = math.radians(th)
        R = p["brink_radius_m"]
        ex, ez = -BRINK_BACK * math.cos(t), BRINK_BACK * math.sin(t)        # the brink's end on the slope's line
        sx, sz = ex - R * math.sin(t), ez + R * (1.0 - math.cos(t))         # the platform's edge
        pr = Profile(sx - p["platform_m"], sz, 0.0)
        pr.line(p["platform_m"], 0.0).mark("start_edge")
        pr.arc(R, -th).mark("brink_end")
        x_end = p["course_m"] * math.cos(t) + 6.0
        pr.line((x_end - pr.end[0]) / math.cos(t), -th).mark("slope_end")
        pr.arc(p["outrun_radius_m"], 0.0).mark("outrun")
        pr.line(p["outrun_m"], 0.0).mark("end")
        return pr

    def start_x(self) -> float:
        """The robot's x at t = 0: its front boot start_back_m behind the start line."""
        return self.profile().marks["start_edge"][0] - self.p["start_back_m"] - self.boot_ahead()

    def boot_ahead(self) -> float:
        """How far the front boot's middle is ahead of the pelvis at t = 0 (along +x)."""
        return G1_FOOT_X

    @property
    def start(self):
        """On the level start platform, facing down the fall line (+x)."""
        return (self.start_x(), 0.0, 0.0)

    def surf(self, s):
        """(x, z) of the point s metres down the slope from the start, along the surface's straight part."""
        th = self.slope()
        return s * math.cos(th), -s * math.sin(th)

    def gates(self) -> list[dict]:
        """Every gate: x of its gate line, its colour, the side of its turning pole (+1 left, -1 right) and the gate
        line's y interval (from the turning pole to the outside pole)."""
        p = self.p
        out = []
        for i in range(int(p["n_gates"])):
            s = p["first_gate_m"] + i * p["gate_spacing_m"]
            x, z = self.surf(s)
            side = 1.0 if (i % 2 == 0) == (p["first_side"] > 0) else -1.0
            yt = side * p["offset_m"]
            yo = yt + side * p["gate_width_m"]
            out.append(dict(i=i, s=s, x=x, z=z, side=side, y_turn=yt, y_out=yo, lo=min(yt, yo), hi=max(yt, yo),
                            colour="red" if i % 2 == 0 else "blue"))
        return out

    def finish(self):
        x, z = self.surf(self.p["course_m"])
        return x, z

    # ------------------------------------------------------------------ the venue
    def _pole(self, sc, name, x, y, z, rgba, flag=None):
        """A flex pole: a body on two crossed hinges at the snow (the flex head) with its return spring."""
        b = sc.body(name, (x, y, z + POLE_HINGE_Z))
        for ax, tag in (("1 0 0", "x"), ("0 1 0", "y")):
            ET.SubElement(b, "joint", name=f"{name}_flex{tag}", type="hinge", axis=ax, stiffness=f"{POLE_K:g}",
                          damping=f"{POLE_DAMP:g}", range=f"{-POLE_FOLD:g} {POLE_FOLD:g}", armature="0.002")
        m = POLE_MASS if flag is None else 2 * POLE_MASS + 0.15
        sc.geom(b, name, type="capsule", fromto=(0, 0, 0.03, 0, 0, POLE_H - POLE_HINGE_Z), size=(POLE_R,), mass=m,
                rgba=rgba, contype=1, conaffinity=1 | 4 | 8, condim=3, friction=(0.3, 0.005, 0.0001))
        if flag is not None:                          # a GS gate's pair: the second pole and the panel between them
            dy = flag
            sc.geom(b, f"{name}_b", type="capsule", fromto=(0, dy, 0.03, 0, dy, POLE_H - POLE_HINGE_Z),
                    size=(POLE_R,), mass=0, rgba=rgba, contype=1, conaffinity=1 | 4 | 8, condim=3,
                    friction=(0.3, 0.005, 0.0001))
            sc.geom(b, f"{name}_panel", type="box", pos=(0, dy / 2, FLAG_Z + FLAG_H / 2 - POLE_HINGE_Z),
                    size=(0.003, abs(dy) / 2 - POLE_R, FLAG_H / 2), mass=0, rgba=rgba, contype=1,
                    conaffinity=1 | 4 | 8, condim=3, friction=(0.3, 0.005, 0.0001))
        self._poles.append(name)
        return b

    def build_course(self, sc):
        p = self.p
        no_fluid(sc)
        pr = self.pr = self.profile()
        # the open ground (looks.py's floor) lowered under the lowest snow, so that it never meets the slope
        floor = next(g for g in sc.wb.findall("geom") if g.get("name") == "floor")
        floor.set("pos", f"0 0 {min(pr.arrays()[1]) - 3.0:.4g}")
        self.snow = pr.build(sc, "snow", p["course_width_m"] / 2, material=snow_material(sc))
        # the mountain beside the piste (to 60 m from the centre line), flush with it
        self.snow += snow_side_terrain(sc, pr, "side", 0, len(pr.pts) - 1, p["course_width_m"] / 2, 60.0)
        sc.ground = ["floor"] + list(self.snow)
        self._poles = []
        for g in self.gates():
            rgba = RED if g["colour"] == "red" else BLUE
            s = g["side"]
            if self.gate_kind == "sl":
                self._pole(sc, f"gate{g['i']}_turn", g["x"], g["y_turn"], g["z"], rgba)
                self._pole(sc, f"gate{g['i']}_out", g["x"], g["y_out"], g["z"], rgba)
            else:                                     # pairs: the inner poles at the gate line's ends
                self._pole(sc, f"gate{g['i']}_turn", g["x"], g["y_turn"], g["z"], rgba, flag=-s * FLAG_W)
                self._pole(sc, f"gate{g['i']}_out", g["x"], g["y_out"], g["z"], rgba, flag=s * FLAG_W)
        fx, fz = self.finish()
        hw = p["finish_width_m"] / 2
        for tag, y in (("L", hw), ("R", -hw)):        # the finish posts and the banner (looks)
            sc.geom(sc.wb, f"finish_post{tag}", type="cylinder", pos=(fx, y, fz + 1.5), size=(0.08, 1.5),
                    rgba=(0.2, 0.2, 0.22, 1), contype=0, conaffinity=0)
        sc.geom(sc.wb, "finish_banner", type="box", pos=(fx, 0, fz + 2.8), size=(0.04, hw, 0.2),
                rgba=(0.15, 0.3, 0.75, 1), contype=0, conaffinity=0)
        sc.geom(sc.wb, "finish_line", type="box", pos=(fx, 0, fz + 0.002), size=(0.04, hw, 0.002),
                quat=(math.cos(self.slope() / 2), 0, math.sin(self.slope() / 2), 0), rgba=(0.85, 0.1, 0.1, 1),
                contype=0, conaffinity=0)
        # the looks of a race piste: B-nets along both edges (solid), the start house over the start platform, the
        # finish arch, the finish area's fenced corral beyond the line
        from rfo import looks as _looks
        b = _looks._Batch(sc, "alp_look")
        xs, zs = pr.arrays()
        for s_ in (1, -1):
            fence_line(sc, b, f"bnet{'L' if s_ > 0 else 'R'}", pr.z_at, float(xs[0]) + 0.5, float(xs[-1]) - 1.0,
                       s_ * (p["course_width_m"] / 2 + 0.3), height=1.8, step=4.0)
        sx, sz = pr.marks["start_edge"]
        b.add((0.3, 0.3, 0.35), (float(xs[0]) + 1.0, 0.0, sz + 1.5), (1.0, 3.0, 1.5))       # the start house
        b.add((0.75, 0.1, 0.1), (float(xs[0]) + 1.0, 0.0, sz + 3.1), (1.3, 3.3, 0.12))
        arch(b, sx + 0.6, 0.0, float(pr.z_at(sx + 0.6)), 2.5, height=3.0, rgb=(0.8, 0.1, 0.1))
        arch(b, fx, 0.0, fz, hw, height=3.5)
        fence_x1 = min(fx + 40.0, float(xs[-1]) - 2.0)
        for s_ in (1, -1):
            fence_line(sc, b, f"corral{'L' if s_ > 0 else 'R'}", pr.z_at, fx + 2.0, fence_x1, s_ * (hw + 2.0),
                       height=1.2, step=4.0)
        b.emit()
        # the planks and their bindings
        for name, (pk, foot, relpos, relquat) in self.planks.items():
            add_plank(sc, name, pk, n_bind=2 if pk.stance else 1, rgba=self.plank_rgba)
        for name, (pk, foot, relpos, relquat) in self.planks.items():
            for f, rp in (foot if isinstance(foot, tuple) else ((foot, relpos),)):
                bind(sc, name, f, rp, relquat)
        cont = sc.root.find("contact")
        sx, sz = self.pr.marks["start_edge"]
        sc.geom(sc.wb, "start_line", type="box", pos=(sx - 0.05, 0, sz + 0.002), size=(0.05, 3.0, 0.002),
                rgba=(0.85, 0.1, 0.1, 1), contype=0, conaffinity=0)
        solids = [g.get("name") for g in sc.root.iter("geom") if (g.get("name") or "").split("_plate")[0] in self.planks
                  and "_plate" in (g.get("name") or "")]
        for a in solids:                              # the planks' solids hit the poles (the planks and the robot: by
            for pole in self._poles:                  # their contact bits, the ski-snow block)
                for gn in (pole, f"{pole}_b", f"{pole}_panel") if self.gate_kind != "sl" else (pole,):
                    ET.SubElement(cont, "pair", geom1=a, geom2=gn, condim="3")

    def plank_frames(self):
        """plank -> (foot body, relpos, relquat) of its (first) binding: where place_on_slope puts it."""
        out = {}
        for name, (pk, foot, relpos, relquat) in self.planks.items():
            if isinstance(foot, tuple):
                f, rp = foot[0]
                out[name] = (f, rp, relquat)
            else:
                out[name] = (foot, relpos, relquat)
        return out

    def reset(self, w):
        self.place(w)

    def place(self, w):
        place_on_slope(w, self.slope(), self.pr.z_at, self.plank_frames(), legs=self.start_legs(w))

    def start_legs(self, w):
        return None

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        self.ss = SnowModel(w, {n: v[0] for n, v in self.planks.items()}, self.snow)
        self.plank_body = {n: m.body(n).id for n in self.planks}
        self.pole_mask = np.zeros(m.ngeom, bool)
        for pole in self._poles:
            self.pole_mask |= ref.geoms(body=pole)
        self.snow_mask = ref.geoms(names=self.snow)
        self.robot_mask = ref.part("robot")
        self.gl = self.gates()
        G = len(self.gl)
        self.trackers = {
            # per gate, per tracked point: None (not yet crossed downwards), True (its latest downward crossing was
            # inside the gate line), False (outside)
            "cross": [[None] * len(self.track) for _ in range(G)],
            "prev": None, "passed": 0, "slow_k": 0, "started": False, "t_start": None,
            "snow": Digest(w, list(self.ss.bodies)),
        }
        self.ss.apply(w.d)                            # the forces of the first physics step, from the state at t = 0

    def points(self, w):
        """The tracked points now: the skis' tips (the front ends of their shovels) and the feet (ICR 661.4.1)."""
        d = w.d
        out = []
        for name, (pk, foot, relpos, relquat) in self.planks.items():
            b = self.plank_body[name]
            R = d.xmat[b].reshape(3, 3)
            out.append(d.xpos[b] + R[:, 0] * pk.tip_x())
        if len(out) == 1:                             # a snowboard: its nose and its tail
            name, (pk, *_) = next(iter(self.planks.items()))
            b = self.plank_body[name]
            R = d.xmat[b].reshape(3, 3)
            out.append(d.xpos[b] - R[:, 0] * pk.tip_x())
        for s in ("left", "right"):
            out.append(d.site_xpos[w.robot.foot_site[s]].copy())
        return np.array(out)

    def height(self, w, p) -> float:
        """Height of a point above the snow, along the surface's normal."""
        a = self.pr.slope_at(float(p[0]))
        return (float(p[2]) - float(self.pr.z_at(float(p[0])))) * math.cos(a)

    def substep(self, w, ref):
        self.ss.apply(w.d)
        if not (ref.failed or ref.success):              # the snow's fall rule, after every physics step (1 ms)
            bad = ref.parts_touching(self.snow_mask) - set(self.legal_ground)
            if bad:
                return ref.fail("fell", on_the_snow=sorted(bad))
        tr = self.trackers
        P = self.points(w)
        prev, tr["prev"] = tr["prev"], P[:, :2].round(9).tolist()
        if prev is None or ref.failed:
            return
        if not tr["started"]:                         # the start: both boots past the start line, by its own action
            if min(float(f[0]) for f in P[-2:]) > self.pr.marks["start_edge"][0]:
                tr["started"], tr["t_start"] = True, round(ref.time, 3)
                ref.stage("start")
            return
        prev = np.asarray(prev)
        fx, _ = self.finish()
        n_passed = tr["passed"]
        for k in range(len(self.gl) + 1):             # the gate lines, then the finish line (x = const planes)
            x = self.gl[k]["x"] if k < len(self.gl) else fx
            for j in range(len(P)):
                x0, x1 = prev[j, 0], P[j, 0]
                if (x0 < x) == (x1 < x):
                    continue
                f = (x - x0) / (x1 - x0)
                y = prev[j, 1] + f * (P[j, 1] - prev[j, 1])
                down = x1 >= x
                if k == len(self.gl):                 # the finish line
                    continue
                g = self.gl[k]
                if not down:                          # back up through it: that point's crossing no longer counts
                    tr["cross"][k][j] = None
                    continue
                if k > n_passed:                      # beyond a gate that has not been passed (ICR 614.2.2)
                    return ref.fail("missed a gate", gate=n_passed + 1,
                                    points=[self.track[i] for i, c in enumerate(tr["cross"][n_passed]) if c is not True])
                tr["cross"][k][j] = bool(g["lo"] <= y <= g["hi"])
        while n_passed < len(self.gl) and all(c is True for c in tr["cross"][n_passed]):
            n_passed += 1
            tr["passed"] = n_passed
            ref.stage(f"gate {n_passed}")
        ref.metrics["gates"] = n_passed
        # the finish: both feet over the finish line between its posts, every gate passed
        feet = P[-2:]
        if all(f[0] >= fx for f in feet):
            if n_passed < len(self.gl):
                return ref.fail("missed a gate", gate=n_passed + 1,
                                points=[self.track[i] for i, c in enumerate(tr["cross"][n_passed]) if c is not True])
            if all(abs(f[1]) <= self.p["finish_width_m"] / 2 for f in feet):
                ref.metrics["time_s"] = round(ref.time - tr["t_start"], 3)       # the run's time from the start line
                if ref.stage("finish", time_s=ref.metrics["time_s"]):
                    ref.succeed()
            else:
                ref.fail("missed the finish", y=[round(float(f[1]), 2) for f in feet])

    def step(self, w, ref):
        p, tr = self.p, self.trackers
        if ref.failed or ref.success:
            return
        pel = w.d.xpos[w.robot.pelvis]
        h = self.height(w, pel)
        if h < p["fall_h_m"]:
            return ref.fail("fell", pelvis_height_m=round(h, 3))
        v = float(np.linalg.norm(w.d.qvel[w.robot.fv:w.robot.fv + 3]))
        ref.metrics["speed_m_s"] = round(v, 3)
        if not tr["started"]:                         # on the start platform: no stop rule; a DNS after dns_s
            tr["slow_k"] = 0
            if w.t >= p["dns_s"] - 1e-9:
                return ref.fail("did not start", t_s=round(w.t, 2))
            return
        tr["slow_k"] = tr["slow_k"] + 1 if v < p["stop_speed_m_s"] else 0
        if tr["slow_k"] * w.CONTROL_DT >= p["stop_s"]:
            return ref.fail("stopped", speed_m_s=round(v, 3))

    def privileged(self, w):
        pel = w.d.xpos[w.robot.pelvis]
        return {"pelvis": w.pelvis().tolist(), "pelvis_height_m": self.height(w, pel), "slope_deg": self.p["slope_deg"],
                "gates": [{k: g[k] for k in ("i", "x", "z", "colour", "y_turn", "y_out")} for g in self.gl],
                "gates_passed": self.trackers.get("passed", 0), "finish_x": self.finish()[0],
                "start_line_x": self.pr.marks["start_edge"][0],
                "planks": {n: {"pos": w.d.xpos[b].tolist(), "xmat": w.d.xmat[b].tolist()}
                           for n, b in self.plank_body.items()},
                "points": dict(zip(self.track, self.points(w).tolist())), "snow_model": dict(self.ss.last)}
# ====================================================================================== END alpine-race block v2

# The G1's foot: its sole (four 5 mm spheres) 0.035 m below the ankle-roll link's origin, its middle 0.035 m ahead of it
G1_SOLE_Z, G1_FOOT_X = -0.035, 0.035
# Rossignol Hero SL Pro 128 (Rossignol's junior slalom race ski for U10-U16 racers; the maker's data: 128 cm,
# 112 / 65 / 98 mm, sidecut radius 8 m, 3.0 kg the pair): the length a junior racer of the robot's 1.32 m takes
# (chin height). Shovel and tail lengths, rises, the plate-and-binding mass (a junior race plate with its binding)
# and the mounting point are estimates; the stand height (base to boot sole) is within the 50 mm of the FIS
# Specifications for Competition Equipment.
SL_SKI = Plank("Rossignol Hero SL Pro 128 cm", 1.28, 0.112, 0.065, 0.098, 8.0, 1.50, -0.06, 0.90, 0.045,
               shovel=0.15, tail=0.05, tip_rise=0.055, tail_rise=0.012, EI_fore=60.0, EI_aft=80.0)


def ski_relpos(pk):
    """The ski's frame in the ankle-roll link's frame (the binding)."""
    return (G1_FOOT_X - pk.mount, 0.0, G1_SOLE_Z - pk.stand_h)


class Task(AlpineRace):
    name = "alpine-slalom"
    title = "Alpine skiing: slalom"
    gate_kind = "sl"
    plank_rgba = (0.85, 0.12, 0.10, 1)
    planks = {f"{s}_ski": (SL_SKI, f"{s}_ankle_roll_link", ski_relpos(SL_SKI), (1, 0, 0, 0)) for s in ("left", "right")}
    rulebook = ("FIS International Competition Rules (ICR), Book IV, Alpine, edition 2025: Art. 614.2 (gates, no "
                "continuing after a missed gate or a stop), 661.4.1 and 661.4.1.2 (a gate is passed when both ski "
                "tips and both feet cross the gate line, the shortest line between the turning pole and the outside "
                "pole), 680 (flex poles), 801 (slalom technical data: gates of two poles, alternately red and blue, "
                "{gate_width_m} m wide (4-6 m), turning poles of consecutive gates 6-13 m apart, direction changes "
                "30-35 % of the vertical drop +/- 3), 802 (the slope: about 33-45 %, may be gentler)")
    deviations = [
        "ICR 801.1 (vertical drop: men 140-220 m, U16-U14 100-160 m, at least 50 m in a three-run slalom): the course "
        "is {course_m} m long on a slope of {slope_deg} degrees, a vertical drop of about 100 m, the U16-U14 "
        "minimum (the category of racers the robot's size), with {n_gates} gates: direction changes about 32 % of "
        "the vertical drop (801.2.4: 30-35 %, plus or minus 3).",
        "ICR 802.1.1 (a slope of about 33-45 %): {slope_deg} degrees, 33 %, the rule's gentlest, uniform over the "
        "whole course (a real slope varies).",
        "ICR 803.2-803.4 (a slalom sets open and vertical gates, hairpins, vertical and delayed combinations): only "
        "open gates, at a regular {gate_spacing_m} m (801.2.3: 6-13 m), their turning poles alternately {offset_m} m "
        "left and right of the course's centre line (the course setter's choice; ICR sets no offset).",
        "ICR 805 (the start: the racer pushes out of the start gate with the poles, the start wand starts the "
        "clock): there is no start gate and nothing holds or releases the robot (the start of the "
        "Embodied Olympics freeski sport, MIT): it stands on its skis on a level start platform ({platform_m} m), "
        "its boots {start_back_m} m behind the platform's edge (the start line), the edge rounded (radius "
        "{brink_radius_m} m) onto the slope; the start signal is given at t = 0 and the robot must leave by "
        "its own action within {dns_s} s (a DNS otherwise); the run's time starts when both boots cross the "
        "start line.",
        "ICR 614.2.4 and 628 (a racer who falls may get up and go on): a fall ends the run here (the families' fall "
        "rule): a part of the robot other than its feet and its hands on the snow, or its pelvis less than "
        "{fall_h_m} m above the snow.",
        "Equipment: no ski poles (the G1's hands are its rubber fists, which do not close: nothing to hold one with), no ski boots (the feet are "
        "bound directly); the binding is rigid and never releases; each ski is three bodies, its forebody and "
        "afterbody on hinges with the ski's bending stiffness (EI 60 / 80 N m^2: estimates, as the "
        "Embodied Olympics freeski sport's skis); the skis are solid against the robot's body and each other.",
        "Snow and air: the ski-snow contact is the freeski model of the CHIGUI0/roboolympics project (MIT, ported): kinetic friction along the "
        "ski after Wolfsperger et al. 2021, the edge's hold across it after Mossner et al. 2013 with race-piste "
        "snow, the sidecut's arc after Howe 2001, hard well-damped snow (the model's final version, PR #259); the "
        "snow keeps no ruts. Still air at a mountain venue (1.052 kg/m^3), drag and lift on every link (a normal-force model).",
        "Gates: a flex pole is a 28 mm pole on a sprung two-axis hinge at the snow (return stiffness and mass are "
        "estimates; ICR 680 requires flex turning poles but publishes no stiffness); it can be hit and folds.",
    ]
    time_limit_s = 90.0
    stages = ["start"] + [f"gate {i + 1}" for i in range(32)] + ["finish"]
    params = dict(platform_m=6.0, start_back_m=0.30, dns_s=20.0, slope_deg=18.3, brink_radius_m=6.0, outrun_radius_m=60.0, outrun_m=80.0, course_width_m=40.0,
                  n_gates=32, first_gate_m=12.0, gate_spacing_m=9.6, offset_m=0.8, gate_width_m=4.0, first_side=1.0,
                  course_m=320.0, finish_width_m=12.0, fall_h_m=0.35, stop_speed_m_s=0.10, stop_s=1.5)

    sentence = ("Ski the slalom: one run down the course on your skis, both ski tips and both feet through each of the "
                "{n_gates} gates in order, then over the finish line.")
    rules = ("FIS alpine slalom, one run (a course of the U16-U14 minimum vertical drop). The course is a groomed slope falling at "
             "{slope_deg} degrees along +x (the fall line), {course_width_m} m wide, centred on y = 0. Each of your "
             "feet is bound to a slalom ski. You stand on your skis on the level start platform at the top of the course, your boots "
             "{start_back_m} m behind its edge (the start line); the start signal is given at t = 0 and you "
             "must leave the platform by your own action (nothing holds or pushes you) within {dns_s} s; your "
             "run's time starts when both feet cross the start line. There are "
             "{n_gates} open gates: gate 1's line is {first_gate_m} m down the slope (measured along it) from x = 0, "
             "the slope's reference line, 1 m below where the brink's curve meets the slope; each next one {gate_spacing_m} m further. A gate is two flexible poles across the slope, "
             "red and blue in turn: its turning pole stands {offset_m} m from the centre line, on the left (y > 0) "
             "for gate 1 and then alternately right and left, its outside pole {gate_width_m} m further out on the "
             "same side. Its gate line is the line on the snow from the turning pole to the outside pole. A gate is "
             "passed when both ski tips (the front ends of the skis) and both feet have crossed its gate line going "
             "down the slope; a point that comes back up across a gate line must cross it again. Gates are passed in "
             "order: if any of those four points goes down past the next gate's line, or the finish line, while a "
             "gate is not passed, you missed it and the run fails. Hitting or folding a pole is allowed. The finish "
             "line is {course_m} m down the slope from x = 0, {finish_width_m} m wide and centred on y = 0: you "
             "succeed when, after every gate, both feet cross it between its posts, within {time_limit_s} s. The run "
             "fails if you fall (a part of you other than your feet and your hands touches the snow, or your pelvis "
             "is less than {fall_h_m} m above the snow, measured along the slope's normal), if you stop after the "
             "start (your pelvis slower than {stop_speed_m_s} m/s for {stop_s} s; ICR 614.2.3), if you do not start "
             "within {dns_s} s, if a foot crosses the finish line "
             "outside its posts, or at {time_limit_s} s.")
    venue = ("You stand on the level start platform ({platform_m} m long) at the top, facing down the fall line "
             "(+x), on your skis (128 cm junior slalom skis, sidecut radius 8 m), your boots {start_back_m} m "
             "behind its edge (the red start line, about 1.6 m before x = 0 and 0.14 m above it); the edge rounds "
             "onto the slope, which falls at {slope_deg} degrees for the whole course and flattens out after the finish into an "
             "outrun. The gates' poles are red and blue, 1.8 m out of the snow; the finish has two posts and a "
             "banner.")
    difficulty = ("Skis glide and carve: to turn, the robot must roll its skis onto their edges and lean its body into "
                  "the turn so that the snow's force passes through its centre of mass, with no walking or running "
                  "policy to help; each change of turn shifts its whole body across the skis. Speed builds on the "
                  "slope, and a lean that does not match the turn throws it on the snow.")

    def build(self, sc):
        self.build_course(sc)
        fx, fz = self.finish()
        sc.camera("venue", (-6.0, -14.0, 9.0), (18.0, 0.0, -6.0), fovy=60)
        sc.camera("follow_start", (-4.0, 0.0, 2.5), (6.0, 0.0, -2.0), fovy=60)
