"""Javelin throw (World Athletics TR 32 and 38) with the women's 600 g javelin. The javelin is a free body held at
its cord grip, across the palm, by the contact and friction of the H1-2's own right hand, its Inspire five-finger hand
(the core's rfo.realhand, "inspire"): it can slip along the fingers, turn in the hand and drop. The release is the
javelin's last contact with the robot after the hand has let go of the cord (opening it; the fingers open at most
260 deg/s, so when it happens is the thrower's timing, not a switch).
From the runway, throw it over the shoulder from behind the arc so that its head strikes the ground first, inside the
sector, at least the qualifying mark away; then leave the runway behind the arc. The Unitree H1-2.

* the official runway, arc, sector and implement (TR 32.9, 32.12, 38.3-38.6);
* the cord grip is a collision body: TR 38.4's grip at the centre of gravity, 160 mm long (TR 38: 150-160 mm), of
  uniform thickness, 29 mm across (the shaft's 25 mm plus 4; TR 38: at most 8 mm more);
* the right hand is the Inspire hand at the core's forces (20 N per fingertip, 30 N the thumb): the cord lies across the palm (a power
  grasp, the javelin's axis along the hand's grasp frame's y), the fingers and thumb closed round it at reset
  (close_on);
* the javelin's flight: published wind-tunnel coefficients applied as forces (below: aero_wrench);
* the hold, the release and no re-grip are judged from contacts (below), not from a grip switch; the release is
  clean: a touch after it may not change the javelin's flight (its contact impulses summed: contact_dv below).
"""
import math

import mujoco
import numpy as np

from rfo.scene import HITTABLE, VISUAL
from rfo.task import TaskBase
# A rigid javelin (steel head, aluminium shaft)'s contact with the robot, the venue's fixtures and the other props
# (the ground keeps its own: rfo/world.py GROUND_SOLMIX): the stiff contact of the core's shells (rfo/world.py
# SHELL_CONTACT: solref 0.004 s, solimp 0.99 0.999 0.0005, from Embodied Olympics' weightlifting fix, a rigid prop on the
# robot's aluminium) with a solmix that wins over a default- contact geom; a ball (priority 1) keeps its own bounce.
# With MuJoCo's default soft contact (solref 0.02 1, solimp 0.9 0.95) it sank 197 mm into the floor at 65 m/s (and
# then spun up and diverged) and 165 mm into the torso (stress test).
from rfo.world import SHELL_CONTACT as RIGID  # noqa: E402

# The implement: World Athletics' women's javelin (TR 38.3-38.6, the 600 g implement; this family's deviation: the
# H1-2's swing cannot release the 800 g men's javelin fast enough along its path), its ranges fixed at the javelin whose
# aerodynamics were measured (below: 2.21 m, the centre of gravity 0.92 m from the tip, 24.7 mm at its thickest):
SHAFT_R, TIP_R = 0.01235, 0.005              # collision radii: the shaft (24.7 mm; TR 38: 20-25 mm), the head
CORD_R, CORD_HALF = 0.01435, 0.0725          # the cord grip: 28.7 mm across (shaft + 4 mm; TR 38: at most + 8 mm), 145 mm
# kg m^2 about the centre of gravity: the men's javelin's measured transverse moment (0.42, Hubbard and Rust 1984) is
# 0.90 of a uniform rod's of its mass and length; the same ratio for this one (0.90 x 0.6 x 2.21^2 / 12); the axial one
# from the men's (6.3e-5) by mass and diameter squared
I_AXIAL, I_TRANSVERSE = 4.6e-5, 0.219
# Flight in air: published aerodynamic coefficients, applied as a force and a moment on the javelin every physics step
# (aero_wrench below; MuJoCo's own fluid model is off for it): the static wind-tunnel case of Seo, Okuizumi, Konishi,
# Kobayashi, Hasegawa and Obayashi, "Measurement of aerodynamic force and moment acting on a javelin using a magnetic
# suspension and balance system", Scientific Reports 13, 357 (2023), Fig. 10: a World Athletics women's javelin (Nishi
# Hybrid Genome X, 2.21 m, the centre of gravity 0.92 m from the tip, 24.7 mm at its thickest) in the 1 m magnetic
# suspension tunnel at 25 m/s (no support interference), read off the figure at its 12 angles of attack from 0 to 18
# degrees: C_D and C_L on the cross-section at the thickest point, C_m about the centre of gravity on that area times
# the length (positive nose up: this javelin pitches up below 12 degrees and down above). Beyond 18 degrees the
# normal-force coefficient grows as sin^2(alpha) (cross-flow on a cylinder; at 90 degrees it is then 1.14 on the
# planform, a cylinder's 1.1-1.2), the axial one falls as cos(alpha), and the centre of pressure stays where it is at 18
# degrees (0.12 m behind the centre of gravity). Rotation: the cross-flow drag of the spinning shaft (C_dc 1.2, a
# circular cylinder in sub-critical cross-flow, Hoerner, Fluid-Dynamic Drag, 1965) added along it in 12 stations, the
# static part taken out, damps the pitching and yawing.
AERO_ALPHA = (0.0, 2.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 15.0, 16.0, 18.0)       # degrees
AERO_CD = (1.30, 1.50, 1.65, 1.75, 1.80, 1.95, 2.10, 2.45, 2.85, 3.15, 3.50, 4.55)
AERO_CL = (0.00, 0.20, 0.45, 0.60, 0.80, 1.40, 2.35, 3.45, 4.70, 5.50, 6.35, 9.10)
AERO_CM = (0.00, 0.00, 0.01, 0.02, 0.03, 0.05, 0.04, 0.01, -0.06, -0.14, -0.25, -0.56)
SEO_L, SEO_D = 2.21, 0.0247                  # the measured javelin: length, its reference diameter
JAV_D = 2 * SHAFT_R                          # this javelin's diameter at its thickest
CROSSFLOW_CD, AERO_STATIONS = 1.2, 12
RHO_AIR = 1.225                              # kg/m^3 (scene.AIR: sea level, 15 C)


def aero_coefficients(alpha: float) -> tuple[float, float, float]:
    """(C_N, C_A, C_m) at the angle of attack alpha (rad, 0..pi/2) on the measured javelin's cross-section (C_m also
    on its length): the normal force (perpendicular to the shaft, towards the side the air comes from below), the
    axial one (along it, against the motion), the pitching moment about the centre of gravity (positive nose up)."""
    a = math.degrees(alpha)
    if a <= AERO_ALPHA[-1]:
        cd, cl = float(np.interp(a, AERO_ALPHA, AERO_CD)), float(np.interp(a, AERO_ALPHA, AERO_CL))
        cm = float(np.interp(a, AERO_ALPHA, AERO_CM))
        return cl * math.cos(alpha) + cd * math.sin(alpha), cd * math.cos(alpha) - cl * math.sin(alpha), cm
    a18 = math.radians(AERO_ALPHA[-1])
    cn18 = AERO_CL[-1] * math.cos(a18) + AERO_CD[-1] * math.sin(a18)
    ca18 = AERO_CD[-1] * math.cos(a18) - AERO_CL[-1] * math.sin(a18)
    cn = cn18 * (math.sin(alpha) / math.sin(a18)) ** 2
    return cn, ca18 * math.cos(alpha) / math.cos(a18), AERO_CM[-1] * cn / cn18      # (the centre of pressure kept)


def aero_wrench(R: np.ndarray, v: np.ndarray, omega: np.ndarray, length: float, cg_from_tip: float):
    """The air's force and moment (about the centre of gravity), world frame, on a javelin whose axis (to the tip) is
    R[:, 0], moving at v with angular velocity omega in still air."""
    ax = R[:, 0]
    speed = float(np.linalg.norm(v))
    F, M = np.zeros(3), np.zeros(3)
    if speed < 1e-6 and float(np.linalg.norm(omega)) < 1e-6:
        return F, M
    seo_a = math.pi * SEO_D ** 2 / 4
    scale = (length * JAV_D) / (SEO_L * SEO_D)              # planform: this javelin over the measured one (1 here)
    u = float(v @ ax)
    vp = v - u * ax                                          # the cross-flow (velocity across the shaft)
    wp = float(np.linalg.norm(vp))
    if speed > 1e-6:
        alpha = math.atan2(wp, abs(u))
        cn, ca, cm = aero_coefficients(alpha)
        q = 0.5 * RHO_AIR * speed * speed * seo_a * scale
        Fa = -q * ca * math.copysign(1.0, u) * ax if abs(u) > 1e-9 else np.zeros(3)
        if wp > 1e-9:
            up = -vp / wp                                    # the normal force's side ("up" for a positive angle)
            F += -q * cn * vp / wp
            lead = math.copysign(1.0, u) * ax if abs(u) > 1e-9 else ax    # the end that leads into the air
            M += q * length * cm * np.cross(lead, up)        # positive C_m turns the leading end towards that side
        F += Fa
    # rotation: the cross-flow drag of each station with the spin's velocity added, less the static part
    xs = np.linspace(cg_from_tip - length, cg_from_tip, AERO_STATIONS + 1)
    xm, dx = 0.5 * (xs[1:] + xs[:-1]), xs[1] - xs[0]
    spin = np.cross(omega, ax)
    spin = spin - float(spin @ ax) * ax                      # the spin's velocity across the shaft per metre from the CG
    w1 = vp[None, :] + xm[:, None] * spin[None, :]
    k = -0.5 * RHO_AIR * CROSSFLOW_CD * JAV_D * dx
    df = k * (np.linalg.norm(w1, axis=1)[:, None] * w1 - wp * vp[None, :])
    F += df.sum(axis=0)
    M += np.cross(ax, (xm[:, None] * df).sum(axis=0))
    return F, M


CORD_IN_HAND_M = (-0.004, 0.0)               # the cord's axis from the hand's grasp centre: out of the palm, along
#                                              the fingers (a search)
CORD_TURN_DEG = 0.0                          # the javelin's axis turned in the palm from straight across it towards
#                                              the fingers
LINE_W, ARC_W = 0.05, 0.07                   # TR 32.9: side lines 50 mm, the arc and its end lines 70 mm
RUNWAY = (0.72, 0.25, 0.18, 1)


def contact_dv(w, prop: np.ndarray, who: np.ndarray, mass: float) -> float:
    """The size of the velocity change (m/s) that the contacts between the geoms `prop` and `who` gave the prop in the
    physics step just taken: MuJoCo's contact forces of that step (mj_contactForce, in each contact's frame) summed in
    the world frame, times the step, over the prop's mass."""
    d, m = w.d, w.m
    n = d.ncon
    if not n:
        return 0.0
    g = d.contact.geom[:n]
    a, b = prop[g[:, 0]] & who[g[:, 1]], prop[g[:, 1]] & who[g[:, 0]]
    J, f = np.zeros(3), np.zeros(6)
    for i in np.flatnonzero(a | b):
        if d.contact.efc_address[i] < 0:
            continue
        mujoco.mj_contactForce(m, d, int(i), f)
        F = d.contact.frame[i].reshape(3, 3).T @ f[:3]
        J += F if b[i] else -F                    # the force on geom2, along the normal from geom1 to geom2
    return float(np.linalg.norm(J)) * m.opt.timestep / mass


def set_arm(w, **angles) -> None:
    """Put arm joints (names without "_joint") at angles for t = 0, and their held targets with them."""
    r, d = w.robot, w.d
    for name, v in angles.items():
        i = w.L.JOINTS.index(name + "_joint")
        d.qpos[r.qadr[i]] = v
        r.arb.q_a[i] = r.arb.q_b[i] = v
    mujoco.mj_kinematics(w.m, d)


class Task(TaskBase):
    name = "javelin"
    title = "Athletics: javelin throw"
    category = "throwing-catching-striking"
    robot = "unitree_h1"
    rulebook = ("World Athletics Competition and Technical Rules 2024: TR 32.9 (the javelin runway and its arc), TR "
                "32.12 (the sector), TR 32.14, 32.16, 32.17 and 32.20 (throwing events: failures, the landing, leaving "
                "the runway, the measurement), TR 38.1 (the throw), TR 38.3-38.6 (the javelin: the women's implement, "
                "its grip)")
    deviations = [
        "TR 38.1(a) (\"the javelin shall be held at the grip with one hand\"): the hand is the H1-2's own Inspire "
        "five-finger hand (six drives: four fingers, the thumb's flexion and rotation; fingertip forces 20 N, the "
        "thumb 30 N, at {grip_scale} times these forces; one closure command for the whole hand); the cord "
        "lies across its palm and is held by its fingers' and thumb's contact and friction only. Held means the cord "
        "touching the hand's fingers and its thumb or palm; the hold may break for at most {grip_gap_s} s (contacts "
        "flicker); the release is the javelin's last contact with any part of you once the hold has ended, when it "
        "has then touched nothing of you for {grip_gap_s} s (between the end of the hold and the release only the "
        "right arm may touch it, for at most {carry_s} s). \"Over the shoulder or upper part of the throwing arm\" "
        "is judged at the release: the javelin's centre of gravity must then be at least {release_above_shoulder_m} m higher "
        "than the throwing shoulder's joint.",
        "TR 38.1(a) (one hand): before the release the javelin may not touch your left arm or hand (it may rest "
        "against the rest of you: the rule book forbids only the second hand).",
        "TR 38.1(c): \"turned completely around\" is judged as the chest's heading more than {back_turn_deg} degrees "
        "away from the throwing direction at any time before the release.",
        "TR 38.3-38.6 (the implement): the robot throws the women's javelin, 600 g and 2.21 m (the men's is 800 g and "
        "2.60-2.70 m): the H1-2's swing, holding the javelin by friction alone, cannot release the men's "
        "javelin pointing along its path fast enough to throw it head first past a line (its best: 15.3 m); a lighter "
        "official implement leaves faster from the same arm. Everything about the throw is otherwise real.",
        "TR 38.3-38.6: the javelin is one rigid body (no bending or vibration) whose head does not stick in the ground; "
        "the mark is the point where the head first touches the ground; the cord grip is a smooth band "
        "{cord_length_m} m long and {cord_diameter_m} m across (no pattern: the finger pads' rubber gives the "
        "friction).",
        "Flight: quasi-steady aerodynamics in still air, no wind: drag and lift against the angle of attack from the "
        "wind-tunnel measurement of this very kind of javelin (a World Athletics women's javelin, Seo et al., "
        "Scientific Reports 2023; drag, lift and pitching moment from 0 to 18 degrees, beyond that a cylinder's "
        "cross-flow); the shaft's cross-flow damps its rotation. The javelin does not bend or vibrate.",
        "TR 32.15 (interrupting a trial, laying the implement down): not modelled; the first release is the throw, "
        "and the javelin may not be gripped again.",
        "TR 38.1(a) (\"held at the grip with one hand ... shall not be slung or hurled\"): the throw is the hand's "
        "alone and its release clean. The rule book has no article on touching the javelin after it has left the "
        "hand; here the right arm may still brush it during {retouch_grace_s} s after the release, but those touches "
        "may change its velocity by at most {retouch_dv_m_s} m/s in all (the sum of their contact impulses over its "
        "mass): a harder touch is a second propulsion of a released implement, and fails the throw.",
        "TR 32.14 names no fall: here a fall ends the trial as a failure, as in every task of this benchmark; the "
        "trial ends when the robot has left the runway correctly and stands.",
        "TR 25.17 (one minute for a trial): the whole trial, leaving the runway included, has {time_limit_s} s.",
        "The qualifying mark of {qualifying_mark_m} m is this benchmark's (a girls' school standard for the 600 g "
        "javelin); the rule book only measures.",
    ]
    time_limit_s = 60.0
    start = (-2.0, 0.0, 0.0)
    stages = ["release", "landing", "exit"]
    fall_z = 0.50
    params = dict(javelin_mass_kg=0.600, javelin_length_m=2.21, javelin_cg_from_tip_m=0.92, javelin_head_m=0.28,
                  cord_length_m=2 * CORD_HALF, cord_diameter_m=2 * CORD_R,
                  runway_width_m=4.0, runway_length_m=30.0, arc_radius_m=8.0, exit_line_m=4.0,
                  qualifying_mark_m=20.0, release_above_shoulder_m=0.0, back_turn_deg=135.0, grip_gap_s=0.02,
                  retouch_grace_s=0.20, retouch_dv_m_s=0.5, carry_s=0.20, stand_s=1.0, fall_pelvis_m=0.50, grip_scale=1.0)

    sentence = ("Throw the javelin held by its cord in your right hand over the shoulder from behind the arc so "
                "that its head strikes the ground first, inside the sector, at least {qualifying_mark_m} m from the "
                "arc, then leave the runway behind the arc and stand.")
    rules = ("The women's javelin ({javelin_mass_kg} kg, {javelin_length_m} m long, its centre of gravity "
             "{javelin_cg_from_tip_m} m from the tip, a metal head of {javelin_head_m} m; its cord grip, "
             "{cord_length_m} m long and {cord_diameter_m} m across, covers the centre of gravity) starts held at its "
             "cord across the palm of your right hand, a five-finger hand that holds only by contact and friction: "
             "the javelin can slip along the fingers or turn in the hand, and drop. It is held while the cord touches "
             "the hand's fingers and its thumb or palm (breaks of at most {grip_gap_s} s are ignored). The release is "
             "the javelin's last contact with any part of you after the hold has ended (however it ends: opened, "
             "slipped or dropped), once it has then touched nothing of you for {grip_gap_s} s; between the end of the "
             "hold and the release only your right arm and hand may touch it, for at most {carry_s} s. Until the "
             "release the javelin may not touch your left arm or hand (the javelin is held with one hand). The runway is {runway_width_m} m wide between "
             "the inner edges of its side lines and {runway_length_m} m long; it ends at the arc, a white strip whose "
             "inner edge is a circle of {arc_radius_m} m radius round a point on the runway's centre line; short "
             "white lines run outwards from the arc's two ends at right angles to the side lines. The sector is "
             "bounded by the two lines from the arc's centre through the arc's ends (28.96 degrees between them). The "
             "throw: at the release the javelin's centre of gravity must be at least {release_above_shoulder_m} m "
             "higher than your right shoulder joint. There is one release: after it the javelin may not be held again "
             "(the cord in the hand's fingers and thumb or palm once more) and no part of you may touch it, except "
             "that your right arm and its hand may still brush it during the first {retouch_grace_s} s, if those "
             "touches change its velocity by at most {retouch_dv_m_s} m/s in all (the sum of their contact impulses "
             "over its mass: the release must be clean). The throw is valid only if the head touches the ground before any other part of the javelin, at "
             "a point inside the sector lines (on a line is out). It is measured from that point to the inner edge "
             "of the arc along the line through the arc's centre. You succeed when a valid throw measures at least "
             "{qualifying_mark_m} m and you have then left the runway correctly and stood for {stand_s} s. Leaving "
             "correctly: after the javelin has landed, your first touch of a side line or of the ground outside the "
             "runway is behind the arc's end lines, or you touch the ground {exit_line_m} m or more behind the arc's "
             "ends. Standing: only your feet on the ground, the torso within about 20 degrees of upright, the pelvis "
             "slower than 0.35 m/s. You fail if, at any time before that, any part of you touches the arc, its end "
             "lines or the ground beyond them; if you touch a side line or the ground outside the runway (also behind "
             "its rear end) before the javelin has landed; if your chest is turned more than {back_turn_deg} degrees "
             "away from the throwing direction before the release (your back to the arc); if the javelin touches your "
             "left arm or hand before the release; if it is released lower than the "
             "shoulder; if after the end of the hold it stays on your right arm for more than {carry_s} s or touches "
             "another part of you; if it is held again, or touched, after the release (but for the brush above); if "
             "it does not "
             "land head first, lands outside the sector or short of {qualifying_mark_m} m; if you fall (your pelvis "
             "lower than {fall_pelvis_m} m above the ground, or any part of you other than your feet on the ground); "
             "or after {time_limit_s} s. Where you touch the ground is judged on the points of contact.")
    venue = ("You stand on the runway's centre line facing the sector (+x), your pelvis 2.0 m behind the middle of "
             "the arc; the arc's centre is 6.0 m behind you, its ends are 0.25 m behind its middle and "
             "2.0 m to either side, and the runway reaches 28 m behind you. Your right arm hangs down, the hand's "
             "fingers pointing down; the javelin lies level across the closed hand's palm, its cord held by the "
             "fingers and thumb, pointing forwards (the tip {javelin_cg_from_tip_m} m ahead of the hand). Still air. "
             "The hand opens when your right grip command goes to 0 (the fingers at most 260 deg/s).")
    difficulty = ("{qualifying_mark_m} m asks for a release near 18 m/s at 25 to 30 degrees with the javelin "
                  "pointing close enough to its flight that it comes down head first; the H1-2 has no running policy "
                  "and its arm motors give 40 N m at the shoulder. Nothing holds the 2.21 m javelin but the "
                  "fingers round its cord: a whip of the arm pulls it out across them (the finger drives give way at "
                  "their self-locking limits), and the hand must let go of it at the right moment, above the shoulder, on a body that has to stay on its feet behind the arc.")

    # ------------------------------------------------------------------ geometry
    def geometry(self):
        p = self.p
        R, hw = p["arc_radius_m"], p["runway_width_m"] / 2
        xe = -R + math.sqrt(R * R - hw * hw)                 # the arc's ends (the arc's middle is the origin)
        return dict(R=R, hw=hw, cx=-R, x_end=xe, x_rear=xe - p["runway_length_m"], half_sector=math.asin(hw / R))

    def build(self, sc):
        p, g = self.p, self.geometry()
        self.fall_z = p["fall_pelvis_m"]
        sc.real_hands["right"] = "inspire"
        if p["grip_scale"] != 1.0:                                # a declared deviation (the grip-force factor)
            sc.real_hand_options["right"] = {"grip_scale": float(p["grip_scale"])}
        R, hw, cx, xe, xr = g["R"], g["hw"], g["cx"], g["x_end"], g["x_rear"]
        sc.box("runway", ((xr + xe) / 2, 0, 0.0003), ((xe - xr) / 2, hw, 0.0003), rgba=RUNWAY)
        k = 16
        for i in range(k):                                   # ... and the segment between the arc's chord and the arc
            y = -hw + (i + 0.5) * 2 * hw / k
            xa = cx + math.sqrt(R * R - y * y)
            sc.box(f"runway_cap{i}", ((xe + xa) / 2, y, 0.0003), ((xa - xe) / 2, hw / k, 0.0003), rgba=RUNWAY)
        for s, tag in ((1, "L"), (-1, "R")):
            sc.line(f"side_line{tag}", (xr, s * (hw + LINE_W / 2)), (xe, s * (hw + LINE_W / 2)), width=LINE_W)
            sc.line(f"arc_end_line{tag}", (xe + ARC_W / 2, s * hw), (xe + ARC_W / 2, s * (hw + 0.75)), width=ARC_W)
            far = 45.0                                       # the sector lines: 50 mm wide, outside the sector
            a = s * g["half_sector"]
            n = (-math.sin(a) * s, math.cos(a) * s)
            p0 = (cx + R * math.cos(a) + n[0] * LINE_W / 2, R * math.sin(a) + n[1] * LINE_W / 2)
            p1 = (cx + (R + far) * math.cos(a) + n[0] * LINE_W / 2, (R + far) * math.sin(a) + n[1] * LINE_W / 2)
            sc.line(f"sector_line{tag}", p0, p1, width=LINE_W, z=0.0012)
        n = 24
        for i in range(n):                                   # the arc: 70 mm wide, its inner edge at the radius
            a0 = -g["half_sector"] + 2 * g["half_sector"] * i / n
            a1 = -g["half_sector"] + 2 * g["half_sector"] * (i + 1) / n
            rr = R + ARC_W / 2
            sc.line(f"arc{i}", (cx + rr * math.cos(a0), rr * math.sin(a0)), (cx + rr * math.cos(a1), rr * math.sin(a1)),
                    width=ARC_W, z=0.0012)
        D = p["qualifying_mark_m"]
        m = 12
        for i in range(m):                                   # the qualifying mark: an arc across the sector
            a0 = -g["half_sector"] + 2 * g["half_sector"] * i / m
            a1 = -g["half_sector"] + 2 * g["half_sector"] * (i + 1) / m
            sc.line(f"mark{i}", (cx + (R + D) * math.cos(a0), (R + D) * math.sin(a0)),
                    (cx + (R + D) * math.cos(a1), (R + D) * math.sin(a1)), width=0.05, rgba=(0.95, 0.85, 0.2, 1))
        L, cg, head = p["javelin_length_m"], p["javelin_cg_from_tip_m"], p["javelin_head_m"]
        b = sc.body("javelin", (-2.0, -0.3, 0.75), free=True)   # the body's origin: the centre of gravity; +x: the tip
        b.insert(1, b.makeelement("inertial", dict(pos="0 0 0", mass=f"{p['javelin_mass_kg']!r}",
                                                    diaginertia=f"{I_AXIAL} {I_TRANSVERSE} {I_TRANSVERSE}")))
        col = dict(friction=(0.8, 0.005, 0.0001), condim=4, mass=0, **HITTABLE, **RIGID)
        sc.geom(b, "javelin_head", type="capsule", fromto=(cg - head, 0, 0, cg - TIP_R, 0, 0), size=(TIP_R,),
                rgba=(0.75, 0.76, 0.8, 1), **col)
        sc.geom(b, "javelin_shaft", type="capsule", fromto=(cg - L + SHAFT_R, 0, 0, cg - head, 0, 0), size=(SHAFT_R,),
                rgba=(0.85, 0.75, 0.2, 1), **col)
        # the cord grip: a collision band (capsule ends inside the band's length), what the hand holds
        sc.geom(b, "javelin_cord", type="capsule", fromto=(-CORD_HALF + CORD_R, 0, 0, CORD_HALF - CORD_R, 0, 0),
                size=(CORD_R,), rgba=(0.2, 0.3, 0.7, 1), **col)
        sc.geom(b, "javelin_cord_look", type="cylinder", fromto=(-CORD_HALF, 0, 0, CORD_HALF, 0, 0),
                size=(CORD_R - 0.0002,), rgba=(0.2, 0.3, 0.7, 1), mass=0, **VISUAL)
        # MuJoCo's fluid model off for the javelin (an ellipsoid of zero coefficients: without one, a body in the
        # venue's air would get MuJoCo's inertia-box drag); the air acts through aero_wrench (substep)
        sc.geom(b, "javelin_air", type="ellipsoid", pos=(0, 0, 0),
                size=(L / 2, SHAFT_R, SHAFT_R), rgba=(0, 0, 0, 0), mass=0, fluidshape="ellipsoid",
                fluidcoef=(0, 0, 0, 0, 0),
                **VISUAL)
        sc.camera("venue", (-8.5, -7.5, 4.5), (4.0, 0.5, 0.3), fovy=55)
        sc.camera("sector", (-3.0, 0.0, 14.0), (12.0, 0.0, 0.0), fovy=70)
        sc.camera("hand", (-1.2, -1.4, 1.2), (-1.85, -0.3, 0.75), fovy=45)

    def reset(self, w):
        # javelin's start: the right arm straight down, a little away from the leg; the javelin level, its axis along
        # the hand's grasp frame's y (forwards), its centre of gravity (the cord's middle) at the grasp point
        set_arm(w, right_elbow_pitch=1.57, right_shoulder_roll=-0.15)
        c, R = w.grasp_frame("right")                         # x: out of the palm, z: along the fingers, y = z x x
        phi = math.radians(CORD_TURN_DEG)
        ax = math.cos(phi) * R[:, 1] + math.sin(phi) * R[:, 2]          # the javelin's axis (to the tip)
        Rb = np.column_stack([ax, np.cross(R[:, 0], ax), R[:, 0]])     # across the palm, turned by CORD_TURN_DEG
        q = np.zeros(4)
        mujoco.mju_mat2Quat(q, Rb.reshape(-1))
        w.put("javelin", c + R[:, 0] * CORD_IN_HAND_M[0] + R[:, 2] * CORD_IN_HAND_M[1], quat=q)
        w.close_on("right", "javelin", closure=1.0)

    # ------------------------------------------------------------------ the referee
    def referee_reset(self, w, ref):
        self.jav = ref.geoms(body="javelin")
        self.head = ref.geoms(names=["javelin_head"])
        self.shaft = ref.geoms(names=["javelin_shaft", "javelin_cord"])
        self.cord = ref.geoms(names=["javelin_cord"])
        ng = w.m.ngeom
        self.grips = [np.isin(np.arange(ng), w.hands.group_geoms(w, "right", g)) for g in ("fingers", "thumb_palm")]
        self.robot = ref.part("robot")
        self.arm = ref.part("right_arm")
        self.not_arm = self.robot & ~self.arm
        self.other_arm = ref.part("left_arm")
        self.jav_id = w.m.body("javelin").id
        self.jav_mass = float(w.m.body_subtreemass[self.jav_id])
        self.shoulder = w.m.body("right_shoulder_roll_link").id
        # held: the last time the hand held the cord; touch: the last time any part of the robot touched the
        # javelin; at: the javelin's state then (the release, if it ends there); dv: the velocity the touches after
        # the release have given it, in all (m/s)
        held = 0.0 if self._held(ref) else None
        self.trackers = {"held": held, "touch": held, "at": self._snapshot(w), "released": None, "dv": 0.0,
                         "landed": None, "exit": False}

    def _held(self, ref) -> bool:
        return all(ref.touching(g, self.cord) for g in self.grips)

    def _snapshot(self, w) -> list:
        c, v = w.pos("javelin"), w.vel("javelin")
        ax = w.d.xmat[self.jav_id].reshape(3, 3)[:, 0]
        return [round(float(x), 6) for x in (*c, *v, ax[2], c[2] - w.d.xpos[self.shoulder][2])]

    def may_grip(self, w, side, name):
        return False                                          # (nothing is grippable)

    def _marks(self, w, ref):
        """Where the robot touches the ground now: None, or (in front of the arc or its end lines?, outside the
        runway behind them?, at or behind the exit line?)."""
        pts = ref.contact_points(self.robot, ref.ground)
        if not len(pts):
            return None
        g, p = self.geometry(), self.p
        x, y = pts[:, 0], pts[:, 1]
        inside = np.abs(y) < g["hw"]
        front = (inside & (np.hypot(x - g["cx"], y) >= g["R"])) | (~inside & (x >= g["x_end"]))
        out = (~inside & (x < g["x_end"])) | (x < g["x_rear"])
        back = x <= g["x_end"] - p["exit_line_m"]
        return bool(front.any()), bool(out.any()), bool(back.any())

    def _release(self, ref):
        """The hold has ended and the javelin has touched nothing of the robot for more than grip_gap_s: the release,
        judged on the javelin's state at its last contact with the robot."""
        tr, p = self.trackers, self.p
        tr["released"] = tr["touch"] if tr["touch"] is not None else 0.0
        x, y, z, vx, vy, vz, axz, above = tr["at"]
        ref.metrics["release_speed_m_s"] = round(math.sqrt(vx * vx + vy * vy + vz * vz), 2)
        ref.metrics["release_height_m"] = round(z, 3)
        ref.metrics["release_elevation_deg"] = round(math.degrees(math.atan2(vz, math.hypot(vx, vy))), 1)
        ref.metrics["release_attitude_deg"] = round(math.degrees(math.asin(max(-1.0, min(1.0, axz)))), 1)
        if above < p["release_above_shoulder_m"]:
            return ref.fail("the javelin was released below the shoulder", above_shoulder_m=round(above, 3))
        ref.stage("release", t=tr["released"])

    def air(self, w) -> None:
        """The air's force and moment on the javelin for the next physics step (aero_wrench, at its centre of
        gravity: the body's origin)."""
        d, b = w.d, self.jav_id
        R = d.xmat[b].reshape(3, 3)
        _, va = w.free["javelin"]
        F, M = aero_wrench(R, d.qvel[va:va + 3], R @ d.qvel[va + 3:va + 6], self.p["javelin_length_m"],
                           self.p["javelin_cg_from_tip_m"])
        d.xfrc_applied[b, :3], d.xfrc_applied[b, 3:] = F, M

    def substep(self, w, ref):
        self.air(w)
        tr, p, g = self.trackers, self.p, self.geometry()
        mk = self._marks(w, ref)
        if mk is not None:
            if mk[0]:
                return ref.fail("touched the arc or the ground beyond it")
            if tr["landed"] is None and mk[1]:
                return ref.fail("left the runway before the javelin had landed")
            if tr["landed"] is not None and (mk[1] or mk[2]) and not tr["exit"]:
                tr["exit"] = True
                ref.stage("exit")
        if tr["landed"] is not None:
            return
        held = self._held(ref)
        if tr["released"] is None:
            if ref.touching(self.jav, self.other_arm):
                return ref.fail("the javelin touched your other arm before the release (one hand)",
                                parts=sorted(ref.parts_touching(self.jav)))
            if held:
                tr["held"] = tr["touch"] = round(ref.time, 4)
                tr["at"] = self._snapshot(w)
                return
            if tr["held"] is not None and ref.time - tr["held"] <= p["grip_gap_s"] + 1e-9:
                return
            if ref.touching(self.jav, self.robot):            # the hold has ended, the javelin still on you
                if ref.touching(self.jav, self.not_arm):
                    return ref.fail("the javelin was touched after the release",
                                    parts=sorted(ref.parts_touching(self.jav)))
                if tr["held"] is not None and ref.time - tr["held"] > p["carry_s"] + 1e-9:
                    return ref.fail("the javelin stayed on the arm without the hand's hold",
                                    unheld_s=round(ref.time - tr["held"], 3))
                tr["touch"], tr["at"] = round(ref.time, 4), self._snapshot(w)
                return
            if tr["touch"] is not None and ref.time - tr["touch"] <= p["grip_gap_s"] + 1e-9:
                return
            self._release(ref)
            if ref.done:
                return
        elif held:
            return ref.fail("the javelin was held again after the release")
        elif (ref.touching(self.jav, self.not_arm)
              or (ref.time - tr["released"] > p["retouch_grace_s"] and ref.touching(self.jav, self.arm))):
            return ref.fail("the javelin was touched after the release", parts=sorted(ref.parts_touching(self.jav)))
        elif ref.failed is None and ref.touching(self.jav, self.arm):    # a brush in the grace: no second throw
            tr["dv"] = round(tr["dv"] + contact_dv(w, self.jav, self.robot, self.jav_mass), 6)
            ref.metrics["retouch_dv_m_s"] = round(tr["dv"], 3)
            if tr["dv"] > p["retouch_dv_m_s"]:
                return ref.fail("the javelin was struck after the release (not a clean release)",
                                dv_m_s=round(tr["dv"], 3))
        if not ref.touching(self.jav, ref.ground):
            return
        head = ref.contact_points(self.head, ref.ground)       # the landing: the first touch of the ground
        tip_first = len(head) > 0 and not ref.touching(self.shaft, ref.ground)
        pt = head[0] if len(head) else ref.contact_points(self.jav, ref.ground)[0]
        dx, dy = float(pt[0]) - g["cx"], float(pt[1])
        dist = math.hypot(dx, dy) - g["R"]
        tr["landed"] = [round(float(pt[0]), 4), round(dy, 4)]
        ref.metrics["distance_m"] = round(dist, 3)
        ref.metrics["head_first"] = float(tip_first)
        if not tip_first:
            ref.fail("the javelin did not land head first")
        elif dist <= 0 or abs(math.atan2(dy, dx)) >= g["half_sector"]:
            ref.fail("the javelin landed outside the sector", x=round(float(pt[0]), 3), y=round(dy, 3))
        elif dist < p["qualifying_mark_m"]:
            ref.fail("the throw is short of the qualifying mark", distance_m=round(dist, 3))
        else:
            ref.stage("landing", distance_m=round(dist, 3))

    def step(self, w, ref):
        tr, p = self.trackers, self.p
        if tr["released"] is None:
            fwd = w.d.xmat[w.robot.torso].reshape(3, 3)[:, 0]
            turn = abs(math.degrees(math.atan2(float(fwd[1]), float(fwd[0]))))
            if turn > p["back_turn_deg"]:
                return ref.fail("turned the back to the arc before the throw", turn_deg=round(turn, 1))
        if ref.has("exit") and ref.hold("stand", ref.standing(), p["stand_s"]):
            ref.succeed()

    def privileged(self, w):
        g = self.geometry()
        return {"javelin": w.pos("javelin").tolist(), "javelin_velocity": w.vel("javelin").tolist(),
                "javelin_axis": w.d.xmat[self.jav_id].reshape(3, 3)[:, 0].tolist(),
                "held": self.trackers.get("released") is None and w.held["right"] == "javelin",
                "released_t": self.trackers.get("released"),
                "arc_centre": [g["cx"], 0.0], "arc_radius": g["R"], "arc_ends_x": g["x_end"],
                "sector_half_angle_deg": math.degrees(g["half_sector"])}
