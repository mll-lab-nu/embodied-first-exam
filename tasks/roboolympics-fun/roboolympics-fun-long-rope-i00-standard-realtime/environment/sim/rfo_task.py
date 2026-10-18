"""Long rope (跳长绳): two scripted turners turn a long rope; standing in the middle, the robot jumps it, the rope
passing under both feet while they are off the ground, a number of times in a row, without the rope ever touching
it.

The rope is a chain of 40 capsules (a 10 mm cotton rope, 60 g/m), each a free body joined to its neighbours by
`connect` equalities (ball-joint chains cost far more: see SUB_K); its two ends are tied the same way to the turners'
hands, mocap bodies that the referee moves on their circles at every
physics step. It hangs, swings and slaps the floor under gravity, air drag and its own inertia, and collides with the
floor and every part of the robot (never with itself). At t = 0 it is already turning: its state is that of the
same rope model turned for a few seconds by the same hands (computed once per process, in a model of the rope and
the floor alone), so the first pass comes at a fixed time."""
import math
import xml.etree.ElementTree as ET

import numpy as np

import mujoco

from rfo.referee import Flights
from rfo.task import TaskBase

SIDES = ("left", "right")
N_SEG = 40                     # rope segments (8 cm for the 3.2 m between the hands)
SUB_K = 1                      # segments per sub-chain: 1 = every segment a free body tied to its neighbours by
#                                `connect`s (deeper sub-chains with ball joints cost more: the implicit integrator
#                                factors each tree densely; K = 5 doubles the step, one 40-deep chain is 10 times it)
JOINT_DAMPING = 0.001          # N m s / rad, each ball joint (SUB_K > 1 only)
JOINT_ARMATURE = 1e-6          # kg m^2, each ball joint (SUB_K > 1 only)
TWIST_INERTIA = 2e-6           # kg m^2: a segment's inertia about its own axis (numerical: a 10 mm cord's is ~7e-8,
#                                which makes the twist mode stiff at 1 ms; a rope's twist plays no part in its motion)
EQ_SOLREF = "0.004 1"          # the connects' constraint time constant (s) and damping ratio
CONTACT_SOLREF = "0.005 1"     # the rope's contacts (priority 1: the rope's numbers win)
ROPE_RGBA = (0.85, 0.12, 0.10, 1)
# the air on each segment, MuJoCo's ellipsoid model on the capsule's own size (not the body's inertia box, which the
# twist inertia above would inflate): blunt drag C_d / 2 with C_d = 1.2 (a cylinder in cross flow), the default
# slender drag and angular drag, no Kutta or Magnus lift (a cord makes none worth having)
FLUIDCOEF = (0.6, 0.25, 1.5, 0.0, 0.0)
PREROLL_S = 8.0                # the rope is turned this long before t = 0 (it reaches its steady loop in about 3 s)
RAMP_S = 0.6                   # ... the turners' spin-up from the rope hanging still, at the start of that
_PREROLL: dict = {}            # the pre-rolled rope state, by its parameters


def _catenary_a(L: float, span: float) -> float:
    lo, hi = 1e-3, 1e3
    for _ in range(200):
        a = (lo + hi) / 2
        lo, hi = (a, hi) if 2 * a * math.sinh(span / (2 * a)) > L else (lo, a)
    return (lo + hi) / 2


def _fmt(v) -> str:
    return " ".join(f"{float(x):.6g}" for x in v)


def rope_geometry(p) -> dict:
    """The derived numbers of the rope and the turners' hands."""
    free = p["rope_length_m"] - 2 * p["rope_held_from_end_m"]
    half = p["turner_distance_m"] / 2 - p["hand_inset_m"]
    r = p["rope_diameter_m"] / 2
    return dict(free=free, half=half, r=r, seg=free / N_SEG, mass=free * p["rope_linear_density_kg_m"],
                hz=p["hand_height_m"], rt=p["hand_circle_radius_m"], omega=2 * math.pi * p["tempo_rev_s"])


def hand_pos(g, phi: float, side: int) -> tuple:
    """A turner's hand at angle phi of its circle (side -1: the turner at -y, +1: at +y). The circle is in the plane
    x-z; phi = 0 is +x, phi = pi/2 is the top. The rope turns with phi decreasing: over the top towards +x, down in
    front of the robot, under it towards -x."""
    return (g["rt"] * math.cos(phi), side * g["half"], g["hz"] + g["rt"] * math.sin(phi))


def rope_xml(p) -> tuple[str, str]:
    """(bodies, equalities) MJCF of the rope and the two hands. Canonical: every segment lies along its body's x
    axis, a child body sits at its parent's segment end, so a rope state (qpos) means the same shape in any model
    built from these parameters; the shape itself is set by rope_rest_qpos / preroll."""
    g = rope_geometry(p)
    m_seg, L = g["mass"] / N_SEG, g["seg"]
    i_bend = m_seg * (L * L / 12 + g["r"] ** 2 / 4)     # a solid cylinder's, about a diameter through its centre
    geom = (f'size="{g["r"]:.6g}" mass="{m_seg:.6g}" contype="2" conaffinity="13" condim="3" '
            f'friction="0.6 0.005 0.0001" solref="{CONTACT_SOLREF}" priority="1" rgba="{_fmt(ROPE_RGBA)}" '
            f'fluidshape="ellipsoid" fluidcoef="{_fmt(FLUIDCOEF)}"')
    hand = ('<body name="hand_{k}" mocap="true" pos="{pos}"><site name="hand_{k}" size="0.01"/><geom name="hand_{k}" '
            'type="sphere" size="0.045" contype="0" conaffinity="0" rgba="0.85 0.65 0.5 1"/></body>')
    bodies = (hand.format(k="a", pos=_fmt(hand_pos(g, math.pi / 2, -1)))
              + hand.format(k="b", pos=_fmt(hand_pos(g, math.pi / 2, 1))))
    eqs = ""
    for g0 in range(0, N_SEG, SUB_K):
        chain = ""
        for i in reversed(range(g0, min(g0 + SUB_K, N_SEG))):
            root = i == g0
            j = (f'<freejoint name="rope{i}"/>' if root else
                 f'<joint name="rope{i}" type="ball" damping="{JOINT_DAMPING:g}" armature="{JOINT_ARMATURE:g}"/>')
            pos = f"0 {-g['half'] + i * L:.6g} 3" if root else f"{L:.6g} 0 0"
            iner = (f'<inertial pos="{L / 2:.6g} 0 0" mass="{m_seg:.6g}" '
                    f'diaginertia="{TWIST_INERTIA:g} {i_bend:.6g} {i_bend:.6g}"/>')
            chain = (f'<body name="rope{i}" pos="{pos}">{iner}{j}<geom name="rope{i}" type="capsule" '
                     f'fromto="0 0 0 {L:.6g} 0 0" {geom}/><site name="rope{i}" size="0.002"/>'
                     f'<site name="rope{i}_end" pos="{L:.6g} 0 0" size="0.002"/>{chain}</body>')
        bodies += chain
        eqs += (f'<connect name="rope_tie{g0}" site1="rope{g0}" site2="{"hand_a" if g0 == 0 else f"rope{g0 - 1}_end"}" '
                f'solref="{EQ_SOLREF}"/>')
    eqs += f'<connect name="rope_tie_end" site1="rope{N_SEG - 1}_end" site2="hand_b" solref="{EQ_SOLREF}"/>'
    return bodies, eqs


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def rope_rest_qpos(p, phi: float) -> list:
    """The rope hanging still between the hands at angle phi: a catenary in their vertical plane (where it would
    reach below the floor, it lies on it), as each rope joint's qpos."""
    g = rope_geometry(p)
    ha = hand_pos(g, phi, -1)
    a = _catenary_a(g["free"], 2 * g["half"])
    pts = []
    for i in range(N_SEG + 1):
        s = i * g["seg"]
        y = a * math.asinh(s / a - math.sinh(g["half"] / a))
        z = ha[2] + a * (math.cosh(y / a) - math.cosh(g["half"] / a))
        pts.append(np.array((ha[0], y, max(z, g["r"] + 0.001))))
    out, qprev = [], None
    for i in range(N_SEG):
        u = pts[i + 1] - pts[i]
        u = u / np.linalg.norm(u)
        q = np.array([1.0 + u[0], 0.0, -u[2], u[1]])     # the rotation of +x onto u
        q /= np.linalg.norm(q)
        if i % SUB_K == 0:
            out.append(np.r_[pts[i], q])
        else:
            out.append(_qmul(qprev * [1, -1, -1, -1], q))
        qprev = q
    return out


def rope_joints(m) -> list[int]:
    return [m.joint(f"rope{i}").id for i in range(N_SEG)]


def preroll(p, phi_start: float):
    """The rope's state (qpos, qvel per rope joint, in order) after the hands have turned it for about PREROLL_S
    from hanging still with the hands at the top of their circles (a spin-up of RAMP_S, then the steady tempo),
    ending with the hands at phi_start (to within one physics step's turn); a model of the floor and the rope
    alone, in the venue's air. Cached per parameters."""
    g = rope_geometry(p)
    key = (tuple(sorted((k, float(v)) for k, v in p.items())), round(phi_start, 12))
    if key in _PREROLL:
        return _PREROLL[key]
    w, dt = g["omega"], 0.001
    sweep = lambda t: w * t * t / (2 * RAMP_S) if t < RAMP_S else w * RAMP_S / 2 + w * (t - RAMP_S)  # noqa: E731
    n0 = int(round(PREROLL_S / dt))
    per = int(round(2 * math.pi / w / dt))
    # the number of steps that brings the hands from the top to (nearly) phi_start: phi_a - sweep(n dt) = phi_start
    n = min(range(n0, n0 + per + 1), key=lambda k: abs(math.remainder(phi_start + sweep(k * dt) - math.pi / 2,
                                                                      2 * math.pi)))
    phi_a = phi_start + sweep(n * dt)
    bodies, eqs = rope_xml(p)
    xml = ('<mujoco><compiler angle="radian" autolimits="true"/><option timestep="0.001" integrator="implicitfast" '
           'density="1.225" viscosity="1.8e-05"/><worldbody><geom name="floor" type="plane" size="40 20 0.05" '
           f'contype="1" conaffinity="5" friction="1 0.005 0.0001"/>{bodies}</worldbody><equality>{eqs}</equality>'
           '</mujoco>')
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    for j, q in zip(rope_joints(m), rope_rest_qpos(p, phi_a)):
        qa = int(m.jnt_qposadr[j])
        d.qpos[qa:qa + len(q)] = q
    for j, s in ((0, -1), (1, 1)):
        d.mocap_pos[j] = hand_pos(g, phi_a, s)
    mujoco.mj_forward(m, d)
    for k in range(n):
        for j, s in ((0, -1), (1, 1)):
            d.mocap_pos[j] = hand_pos(g, phi_a - sweep((k + 1) * dt), s)
        mujoco.mj_step(m, d)
    if not np.all(np.isfinite(d.qpos)):
        raise RuntimeError("long-rope: the rope's pre-roll diverged")
    out = []
    for j in rope_joints(m):
        qa, va = int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])
        nq, nv = (7, 6) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE else (4, 3)
        out.append((d.qpos[qa:qa + nq].copy(), d.qvel[va:va + nv].copy()))
    _PREROLL[key] = out
    return out


def rope_point_at_y(nodes: np.ndarray, y: float):
    """The rope's point (x, y, z) where it crosses the plane y = const, interpolated between the nodes; of several
    crossings, the one nearest the rope's middle (by node index). None if the rope does not reach that plane."""
    s = nodes[:, 1] - y
    idx = np.flatnonzero((s[:-1] <= 0) != (s[1:] <= 0))
    if not len(idx):
        return None
    i = int(idx[np.argmin(np.abs(idx + 0.5 - (len(nodes) - 1) / 2))])
    f = s[i] / (s[i] - s[i + 1]) if s[i] != s[i + 1] else 0.0
    return nodes[i] + f * (nodes[i + 1] - nodes[i])


def zspan(w, ids):
    """The lowest and highest points of the geoms `ids` (their oriented bounding boxes)."""
    m, d = w.m, w.d
    R = d.geom_xmat[ids].reshape(-1, 3, 3)
    c = d.geom_xpos[ids] + np.einsum("gij,gj->gi", R, m.geom_aabb[ids, :3])
    half = np.sum(np.abs(R[:, 2, :]) * m.geom_aabb[ids, 3:], axis=1)
    return float(np.min(c[:, 2] - half)), float(np.max(c[:, 2] + half))


class Task(TaskBase):
    name = "long-rope"
    title = "Long rope (jumping a rope turned by two turners)"
    category = "track-and-jumps"
    robot = "unitree_g1"
    rulebook = ("The Asian Jump Rope Union's AC2026 Asian Long Rope Championship Rules (AJRU, IJRU's continental "
                "body): event #2 '8 Jumpers' (two turners turn one long rope, the jumpers jump it together; the rope "
                "must pass under the feet of the jumpers to score 1 point) with the turners {turner_distance_m} m "
                "apart, the distance event #1 'Figure 8' sets (event #2 sets none); the common rules (the rope "
                "remains still until the start signal; leaving the event area is a space violation); and the IJRU "
                "Judging Manual (show freestyle, long rope): a long rope is at least {rope_length_m} m long")
    deviations = [
        "8 Jumpers: one jumper (the robot) instead of eight, and a count of consecutive jumps, {jumps_required} "
        "in a row with no miss, instead of the jumps in 1 minute; the count is the benchmark's qualifying mark, a "
        "round number (school long-rope practice counts runs of consecutive jumps; no rule book sets this one)",
        "the turners are scripted, not athletes: each holds the rope {rope_held_from_end_m} m from its end, the rest "
        "wound round the hand, so that the free rope between the hands ({free_length_m} m) just brushes the floor "
        "under the jumper (as turners shorten a long rope to the jumpers); each moves the hand on a vertical circle of "
        "{hand_circle_radius_m} m radius whose centre is {hand_height_m} m high and {hand_inset_m} m in front of the "
        "turner, at a steady {tempo_rev_s} revolutions per second; they never adapt to the jumper, and they do not "
        "stop when the rope is caught (the rope's ends beyond the hands are not modelled)",
        "the start: the rope is already turning at the start (t = 0), not still until a signal; its lowest part "
        "has just passed under the robot, going backwards",
        "the end: the event has none (the clock stops the round); here the robot must land on its feet after the "
        "last jump and stand still for {stand_s} s, all before the still-turning rope comes round again (a "
        "longer stand would need the turners to stop the rope, and a stopping rope swings on into the jumper)",
        "a miss is any touch of the rope on the robot (the rules only score the passes); a jump is a pass of the "
        "rope under both feet while nothing of the robot touches the ground, and the robot must stay in the middle "
        "of the rope (the centre zone) instead of the event's space rule",
        "the rope: a {rope_diameter_m} m cotton rope of {rope_linear_density_kg_m} kg/m (a typical 10 mm braided "
        "cotton rope) modelled as a chain of 40 short capsules joined end to end by stiff point constraints (free to "
        "bend and twist: a cord has almost no bending stiffness), in still air with its drag; no wind",
    ]
    time_limit_s = 20.0
    start = (0.0, 0.0, 0.0)
    params = dict(turner_distance_m=3.6, hand_inset_m=0.4, hand_height_m=1.0, hand_circle_radius_m=0.4,
                  rope_length_m=6.0, rope_held_from_end_m=1.4, free_length_m=3.2, turner_y_m=1.8, rope_diameter_m=0.010,
                  rope_linear_density_kg_m=0.06, tempo_rev_s=1.0, hand_angle0_deg=-130.0, jumps_required=10,
                  zone_half_x_m=0.5, zone_half_y_m=0.5, stand_s=0.5,
                  fall_z_m=0.35)

    def __init__(self):
        super().__init__()
        self._sync_stages()

    def configure(self, params):
        super().configure(params)
        self._sync_stages()

    def _sync_stages(self):
        p = self.p
        p["free_length_m"] = round(p["rope_length_m"] - 2 * p["rope_held_from_end_m"], 6)     # derived (texts)
        p["turner_y_m"] = round(p["turner_distance_m"] / 2, 6)
        self.stages = [f"jump {i}" for i in range(1, int(p["jumps_required"]) + 1)] + ["landing", "stand"]

    sentence = ("Jump the long rope: standing in the middle of a rope turned by two turners, jump it {jumps_required} "
                "times in a row, the rope passing under both your feet while you are in the air, without the rope "
                "ever touching you.")
    rules = ("Two turners stand {turner_distance_m} m apart, one on each side of you (on the y axis, at y = "
             "-{turner_y_m} and +{turner_y_m} m); they turn a {rope_length_m} m rope, {rope_diameter_m} m thick, "
             "holding it {rope_held_from_end_m} m from each end, at a steady {tempo_rev_s} revolutions per second: "
             "each hand goes round a vertical circle of {hand_circle_radius_m} m radius, {hand_height_m} m above "
             "the floor, {hand_inset_m} m in front of its turner. The rope goes over your head from behind you to "
             "the front, down in front of you and under you towards your back; it is already turning at the start. "
             "A jump "
             "counts when the rope passes under both your feet while nothing of you touches the ground (at the "
             "moment it passes under each foot), after it has passed over your head since the last counted jump (one "
             "jump per turn of the rope). You succeed when, after {jumps_required} counted jumps, the first "
             "contact with the floor is your feet only and you then stand still for {stand_s} s (only your feet on "
             "the floor, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s): the "
             "turners keep turning, so this has to be done before the rope comes round again, and it must not touch "
             "you until then. You fail at once if the rope touches any part of you (a miss: the turners do not "
             "stop), if "
             "your pelvis leaves the centre zone (within {zone_half_x_m} m of the rope's axis forwards and backwards "
             "and {zone_half_y_m} m of the middle between the turners sideways), if the rope passes under a foot "
             "that is on the ground or through you, on a fall (your pelvis lower than {fall_z_m} m, or any part of "
             "you other than your feet on the ground), on a landing that is not on the feet after the last jump, or "
             "after {time_limit_s} s.")
    venue = ("You stand facing +x on a wooden gym floor, in the middle between two turners, who stand at y = "
             "-{turner_y_m} m and y = +{turner_y_m} m on the line through your feet (you face across the rope). The "
             "rope's axis, the line between the centres of the turners' hand circles, is {hand_height_m} m above the "
             "floor right above your feet. The centre zone is painted on the floor. At the start the rope is turning "
             "at {tempo_rev_s} revolutions per second; its lowest part has just passed under you and is rising "
             "behind you: it comes over your head, down in front of you and under your feet once per turn.")
    difficulty = ("Neither built-in gait can jump: the robot must hop again and again, in time with a rope it "
                  "has to watch, with its feet off the ground at the very moment the rope passes and back on "
                  "balance before the next turn. Each landing must be absorbed while the next take-off is already "
                  "being prepared, and any drift out of the middle or a toe left behind catches the rope.")

    # ------------------------------------------------------------------ the venue
    def _phi0(self) -> float:
        return math.radians(self.p["hand_angle0_deg"])

    def build(self, sc):
        p = self.p
        hd = p["turner_distance_m"] / 2
        sc.box("gym_floor", (0, 0, 0.0003), (4.0, hd + 1.5, 0.0003), rgba=(0.76, 0.58, 0.38, 1))
        zx, zy = p["zone_half_x_m"], p["zone_half_y_m"]
        for i, (a, b) in enumerate((((-zx, -zy), (zx, -zy)), ((zx, -zy), (zx, zy)), ((zx, zy), (-zx, zy)),
                                    ((-zx, zy), (-zx, -zy)))):
            sc.line(f"zone{i}", a, b, width=0.04, z=0.0009)
        for s in (-1, 1):                                # the turners (drawn only): a body, a head, a spot
            y = s * hd
            sc.geom(sc.wb, f"turner{s:+d}_body", type="capsule", fromto=(0, y, 0.15, 0, y, 1.35), size=(0.16,),
                    rgba=(0.20, 0.32, 0.65, 1), contype="0", conaffinity="0")
            sc.geom(sc.wb, f"turner{s:+d}_head", type="sphere", pos=(0, y, 1.62), size=(0.12,),
                    rgba=(0.85, 0.65, 0.5, 1), contype="0", conaffinity="0")
            sc.box(f"turner{s:+d}_spot", (0, y, 0.0008), (0.25, 0.25, 0.0005), rgba=(0.96, 0.96, 0.96, 1))
        bodies, eqs = rope_xml(p)
        for el in ET.fromstring(f"<x>{bodies}</x>"):
            sc.wb.append(el)
        eq = sc.root.find("equality")
        for el in ET.fromstring(f"<x>{eqs}</x>"):
            eq.append(el)
        sc.camera("venue", (4.2, -3.6, 1.9), (0.0, 0.0, 0.8), fovy=55)
        sc.camera("side", (1.3, -5.2, 0.9), (0.0, 0.0, 0.8), fovy=45)        # along the rope, past the turner

    def reset(self, w):
        m, d = w.m, w.d
        self._init(w)
        state = preroll(self.p, self._phi0())
        for j, (q, v) in zip(rope_joints(m), state):
            qa, va = int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j])
            d.qpos[qa:qa + len(q)] = q
            d.qvel[va:va + len(v)] = v
        self._set_hands(w, 0.0)

    def _init(self, w):
        self.g = rope_geometry(self.p)
        self._mocap = [int(w.m.body_mocapid[w.m.body(n).id]) for n in ("hand_a", "hand_b")]

    def _phi(self, t: float) -> float:
        return self._phi0() - self.g["omega"] * t

    def _set_hands(self, w, t: float) -> None:
        """The hands where they are at time t (MuJoCo moves a mocap body to its target at the next step: the step
        from t - dt to t gets the hands' position at t, as in the pre-roll)."""
        ph = self._phi(t)
        for j, s in zip(self._mocap, (-1, 1)):
            w.d.mocap_pos[j] = hand_pos(self.g, ph, s)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        m = w.m
        self.fall_z = self.p["fall_z_m"]
        self._init(w)
        self._set_hands(w, ref.time + w.PHYS_DT)        # the first physics step's target
        self.rope = ref.geoms(prefix="rope")
        self.robot_sel = ref.part("robot")
        self.nodes = np.array([m.site(f"rope{i}").id for i in range(N_SEG)] + [m.site(f"rope{N_SEG - 1}_end").id])
        self.foot_ids = {s: np.flatnonzero(ref.part(f"{s}_foot")) for s in SIDES}
        self.trackers = {"flights": Flights(ref, min_air=0.0), "jumps": 0, "prev": {"left": None, "right": None,
                         "head": None}, "under": {"left": None, "right": None}, "over": False, "passes": [],
                         "last_jump_t": None}

    def _rope_nodes(self, w) -> np.ndarray:
        return w.d.site_xpos[self.nodes]

    def substep(self, w, ref):
        p, tr, d, r = self.p, self.trackers, w.d, w.robot
        self._set_hands(w, ref.time + w.PHYS_DT)        # the hands' target for the next physics step
        fl = tr["flights"]
        landed = fl.update()
        if ref.touching(self.rope, self.robot_sel):
            return ref.fail("the rope touched the robot", parts=sorted(ref.parts_touching(self.rope)))
        if ref.has(self.stages[-3]):                     # the last jump is in: the landing, then the stand
            if landed is not None and not ref.has("landing"):
                if set(landed["landing_parts"]) <= {"left_foot", "right_foot"}:
                    ref.stage("landing")
                else:
                    ref.fail("the landing was not on the feet", parts=landed["landing_parts"])
            return
        nodes = self._rope_nodes(w)
        hz = self.g["hz"]
        refs = {s: d.site_xpos[r.foot_site[s]] for s in SIDES}
        refs["head"] = d.site_xpos[r.head_site]
        for key, q in refs.items():
            pt = rope_point_at_y(nodes, float(q[1]))
            if pt is None:
                tr["prev"][key] = None
                continue
            sx = float(pt[0] - q[0])
            prev, tr["prev"][key] = tr["prev"][key], sx
            if prev is None:
                continue
            if key == "head":
                if prev < 0.0 <= sx and pt[2] > hz:     # over the top, from behind to the front
                    top = ref.robot_span((0.0, 0.0, 1.0))[1]
                    if pt[2] - self.g["r"] <= top:
                        return ref.fail("the rope passed through the robot", rope_z=round(float(pt[2]), 3))
                    if tr["under"]["left"] is not None or tr["under"]["right"] is not None:
                        return ref.fail("the rope passed under only one foot")
                    tr["over"] = True
                continue
            if not (prev > 0.0 >= sx and pt[2] < hz):    # under the robot, from the front to the back
                continue
            sole = zspan(w, self.foot_ids[key])[0]
            if pt[2] + self.g["r"] >= sole:
                return ref.fail("the rope passed through the robot", foot=key, rope_z=round(float(pt[2]), 3),
                                sole_z=round(sole, 3))
            if not ref.airborne():
                return ref.fail("the rope passed under a foot while the robot was on the ground", foot=key)
            if not tr["over"]:
                return ref.fail("the rope passed under the feet without having passed over the head", foot=key)
            tr["under"][key] = round(ref.time, 4)
            ref.event("under", foot=key, clearance_m=round(sole - float(pt[2]) - self.g["r"], 4))
            if tr["under"]["left"] is not None and tr["under"]["right"] is not None:
                tr["jumps"] += 1
                tr["passes"].append([tr["under"]["left"], tr["under"]["right"]])
                tr["under"] = {"left": None, "right": None}
                tr["over"] = False
                tr["last_jump_t"] = round(ref.time, 4)
                ref.metrics["jumps"] = tr["jumps"]
                ref.stage(f"jump {tr['jumps']}")
    def step(self, w, ref):
        x, y = w.pelvis()[:2]
        if abs(x) > self.p["zone_half_x_m"] or abs(y) > self.p["zone_half_y_m"]:
            return ref.fail("the robot left the centre zone", pelvis=[round(float(x), 3), round(float(y), 3)])
        if ref.has("landing") and ref.hold("stand", ref.standing(), self.p["stand_s"]):
            if ref.stage("stand"):
                ref.succeed()

    def privileged(self, w):
        tr = self.trackers
        ph = self._phi(w.ref.time)
        return {"pelvis": w.pelvis().tolist(), "rope_nodes": self._rope_nodes(w).round(4).tolist(),
                "rope_radius_m": self.g["r"], "hand_angle_rad": ph, "hands": [list(hand_pos(self.g, ph, s)) for s in
                                                                             (-1, 1)],
                "rope_axis_z": self.g["hz"], "tempo_rev_s": self.p["tempo_rev_s"], "jumps": tr["jumps"],
                "over_since_last_jump": tr["over"]}
