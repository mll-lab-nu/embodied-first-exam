"""Option A stage logic (approved deviation: the wand's START rest yaw is rotated about the start post).

Layout x-span (yaw 0): start post near the robot (x 0.395), finish post far (x 0.745), wire plane y = -0.035.
  1 L  top-down tip pinch A on the handle (start rest yaw H_START), lift + tilt to the handover pose H1
  2 R  ring grip on the far side of the loop (handover 1); L leaves
  3 R  yaw the handle to +y, carry the loop along the rail (camera up on the span), down the finish post
  4 L  pen grip G_down on the handle end (handover 2) at h = +y; R leaves
  5 L  yaw the handle to the finish yaw, lower to the release height, open (short drop onto the deck), leave
"""
import numpy as np
from scipy.spatial.transform import Rotation
from grasps import pen, ring, topdown, T_from, TIP_Z
from bw_geom import GRIP_XC
from plan_r import PlanError, frame_h_n, interp_T, n_steps, rrt_connect, densify
from stages_r import StagesR, Rz, yaw_of, wrap, back, OPEN, CLOSED

from optA_lift_check import tilted_A
# tip pinch on the outer handle half, gripper tilted 30 deg about the closing axis (the only start grasp that can
# lift the wand: tools/optA_lift_check.py); tips 1.5 mm above the deck
import os as _os
# tip pinch on the outer part of the (enlarged) grip, gripper tilted about the closing axis (the only start grasps
# the YAM can lift: tools/optA_lift_check.py); tip_gap < 0: the tips sit below the grip mid-plane
A_TILT = float(_os.environ.get("BUZZ_A_TILT", "20"))
A_GRIP = tilted_A(A_TILT, c=float(_os.environ.get("BUZZ_A_C", "0.062")),
                  tip_gap=float(_os.environ.get("BUZZ_A_TIPGAP", "-0.004")))
G_DOWN = pen("down", 0.036, 0.0, 0.0)                   # handle on the finger centre line (tip contact patch)


def gdown_grip(roll_deg, yaw_deg=0.0, xc=0.043, tilt_deg=0.0, x_tip=0.036):
    """G_DOWN rolled about the handle (wand x) axis, then turned about the wand z axis through the handle point
    (xc, 0, 0). roll 0: closing across the 9.8 mm width, camera up (very_easy). roll +-90: closing across the
    16 mm height (pads on the top/bottom faces), so the approach can also be turned in the deck plane (yaw) and
    the wrist kept off a low or laterally bent span. Returns (grip, fq_hold, fq_open); pad face at |q| - 1 mm."""
    Rr = np.eye(4)
    Rr[:3, :3] = Rotation.from_euler("x", roll_deg, degrees=True).as_matrix()
    Ty = np.eye(4)
    Ty[:3, :3] = Rotation.from_euler("z", yaw_deg, degrees=True).as_matrix()
    c = np.array([xc, 0.0, 0.0])
    Ty[:3, 3] = c - Ty[:3, :3] @ c
    a = np.radians(roll_deg)
    half = 0.0049 * abs(np.cos(a)) + 0.008 * abs(np.sin(a))
    G0 = G_DOWN if (tilt_deg == 0.0 and x_tip == 0.036) else pen("down", x_tip, 0.0, tilt_deg)
    return Ty @ Rr @ G0, -(half + 0.001), -(half + 0.0046)


# finish pen grip per tier. easier: tips on the outer handle end (62 mm), rolled 10 deg about the handle and tilted
# -8 deg about the closing axis, so that the left wrist clears the bent/dipped easier span at the finish yaw
# (tools/finish_grip_map.py, results/fgm2/); handover-2 at 90 mm (lower, this grip's fingers meet the deck)
GD_TIER = {"very_easy": (0.0, 0.0), "easier": (10.0, 0.0)}            # (roll, yaw)
GD_TILT_TIER = {"very_easy": (0.0, 0.036), "easier": (-8.0, 0.062)}   # (tilt about the closing axis, x_tip)


def ring_clamp(phi_deg, cam_sign=1.0, tip_past=0.002):
    """Clamp on the ring tube at wand angle phi, approaching along +wand z (= world down for the face-down wand at
    the finish post), closing radially across the tube, finger width along the tube tangent (camera side =
    cam_sign * tangent). The tips stop tip_past beyond the tube centre. Returns (grip, fq_hold, fq_open)."""
    from bw_geom import LOOP_R, TUBE_R
    f = np.radians(phi_deg)
    rad = np.array([np.cos(f), np.sin(f), 0.0])
    tan = np.array([-np.sin(f), np.cos(f), 0.0]) * cam_sign
    z = np.array([0.0, 0.0, 1.0])
    x = np.cross(tan, z)
    R = np.column_stack([x, tan, z])
    c = LOOP_R * rad
    return T_from(R, c + (tip_past - TIP_Z) * z), -(TUBE_R + 0.001), -0.0053


# finish grip per tier: "gdown" = left pen grip on the handle (very_easy); "clamp" = left top-down clamp on the ring
# tube beside the finish post (easier: its span bends toward the left arm and dips, so a low pen grip under the span
# hits the left forearm / wrist camera; tools/dry_run_a.py logs in results/gd_grid/)
FINISH_TIER = {"very_easy": "gdown", "easier": "gdown"}

# MIRROR (easier): the same sequence mirrored about the vertical wire plane, arm roles swapped (right picks and
# places, left carries). The easier span bends toward +y (the left arm) between the posts; with the left arm placing,
# its forearm meets that bend under every finish pen grip tried (results/gd_grid, gd_hi, lay_grid). Mirrored
# frames: yaw h -> -h, tilt b -> -b; mirrored grips G -> N G D (N: wand y -> -y, D: link6 x -> -x; the wand and the
# two fingers are symmetric under these reflections).
MIRROR_TIER = {"very_easy": False, "easier": False}
_N = np.diag([1.0, -1.0, 1.0, 1.0])
_D = np.diag([-1.0, 1.0, 1.0, 1.0])


def mirror_grip(G):
    return _N @ G @ _D
R_GRIP = ring()
FQ_A, FQ_A_OPEN = -0.0059, -0.016
FQ_PEN, FQ_PEN_OPEN = -0.0059, -0.0095
FQ_RING, FQ_RING_OPEN = -0.0023, -0.0053
H1 = (30.0, -30.0, 0.055)      # handover-1 pose on the start post (tools/optA_h1c.py: pinch 35 mm, ring 7 mm clear)
H_CARRY = 90.0                 # handle +y during the carry (ring-grip camera points up on the span)
HZ_FINISH = 0.060
HZ_FINISH_TIER = {"easier": 0.090}
H_START = 60.0                 # new start rest yaw of the handle (deg, world)


class StagesA(StagesR):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        m = _os.environ.get("BUZZ_MIRROR")
        self.mirror = MIRROR_TIER.get(self.s.tier, False) if m is None else m == "1"
        self.sg = -1.0 if self.mirror else 1.0
        self.A, self.C = ("right", "left") if self.mirror else ("left", "right")   # picker/placer, carrier
        self.notes["mirror"] = self.mirror

    def ph(self, name):
        if self.mirror:
            name = name.replace("left", "@").replace("right", "left").replace("@", "right")
        self.ex.phase(name)

    def g(self, G):
        return mirror_grip(G) if self.mirror else G

    @staticmethod
    def grasp_error(G, G_nom):
        d = np.linalg.inv(G_nom) @ G
        return dict(pos_mm=float(np.linalg.norm(d[:3, 3]) * 1000),
                    rot_deg=float(np.degrees(Rotation.from_matrix(d[:3, :3]).magnitude())))

    def frame(self, hdeg, beta, hz, post, normal_down=False):
        h = np.array([np.cos(np.radians(hdeg)), np.sin(np.radians(hdeg)), 0.0])
        n = Rotation.from_rotvec(np.radians(beta) * h).apply([0, 0, -1.0 if normal_down else 1.0])
        return T_from(frame_h_n(h, n), np.r_[post, self.s.deck_top + hz])

    def run(self):
        s, ex, P = self.s, self.ex, self.P
        ex.hold(5)
        self.ph("1_left_pick_start")
        W0 = ex.wand()
        h0 = yaw_of(W0)
        W1 = W0.copy(); W1[2, 3] += 0.003
        sg = self.sg
        H1m = (sg * H1[0], sg * H1[1], H1[2])
        A_G = self.g(A_GRIP)
        lift = []
        # the left pinch's feasible region on the start post is an island around handle yaw 30-60 deg, tilt
        # -45..0 deg (tools/optA_map.py); stay inside it
        for nodes in ([(h0, 0, 0.02), (h0, 0, 0.035), (0.5 * (h0 + H1m[0]), H1m[1] / 2, 0.045), H1m],
                      [(h0, 0, 0.015), (h0, -15 * sg, 0.03), (h0, -30 * sg, 0.045), H1m],
                      [(h0, 0, 0.025), (H1m[0], -15 * sg, 0.04), H1m]):
            lift.append([W0, W1] + [self.frame(a, b, c, self.p0) for a, b, c in nodes])
        last = None
        for Wl in lift:
            try:
                Ws = self.wand_moves(Wl)
                G = self.grasp(self.A, W0 @ A_G, [W @ A_G for W in Ws], FQ_A_OPEN, FQ_A, "pick",
                               approach_ignore=("stops",), follow_ignore=("stops",))
                break
            except PlanError as e:
                last = e
                print("   lift plan rejected:", e, flush=True)
        else:
            raise PlanError(f"pick+lift: {last}")
        self.ph("2_left_lift_tilt")
        W = ex.wand()
        self.notes["pick_in_hand_error"] = self.grasp_error(G, A_G)
        # re-plan the lift with the measured grasp (the pinch can shift/turn the light wand a little)
        for Wv in [Wl] + [x for x in lift if x is not Wl]:
            try:
                self.held_track(self.A, self.wand_moves([W] + Wv[1:]), G, FQ_A, lin=0.012, ignore=("stops",))
                break
            except PlanError as e:
                last = e
                print("   lift re-plan rejected:", e, flush=True)
        else:
            raise PlanError(f"lift with measured grasp: {last}")
        ex.hold(15)
        Ga = G
        if _os.environ.get("BUZZ_STOP_AFTER_LIFT") == "1":
            self.notes["lift_test_wand_z_mm"] = float((ex.wand()[2, 3] - s.deck_top) * 1000)
            return
        self.ph("3_right_ring_handover")
        Gr = None
        last = None
        # try the measured pose first, then put the wand (closed loop, measured pinch) on nominal / nearby H1 poses
        cands = [None] + [(H1m[0] + sg * dy, H1m[1] + sg * db, H1m[2]) for dy, db in ((0, 0), (5, 0), (-5, 0), (0, 5), (0, -5), (10, 0))]
        for cand in cands:
            if cand is not None:
                for _ in range(2):
                    W = ex.wand()
                    Wt = self.frame(*cand, self.p0)
                    try:
                        self.held_track(self.A, interp_T(W, Wt, n_steps(W, Wt, lin=0.001)), Ga, FQ_A, lin=0.006, ignore=("stops",))
                    except PlanError as e:
                        last = e
                        break
                    ex.hold(10)
            Wm = ex.wand()
            hz = Wm[2, 3]
            HC = sg * H_CARRY
            Wc = self.frame(HC, 0.0, hz - s.deck_top, self.p0)
            a1 = hz - s.rail[0, 2]
            hzf = float(_os.environ.get("BUZZ_HZ_FINISH", HZ_FINISH_TIER.get(s.tier, HZ_FINISH)))
            a2 = s.arc[-1] - (s.deck_top + hzf - s.rail[-1, 2])
            hvec = (np.cos(np.radians(HC)), np.sin(np.radians(HC)), 0.0)
            route = P.wand_route(a1, a2, h=hvec)
            if self.skip_traverse:
                route = interp_T(Wc, route[-1], n_steps(Wc, route[-1]))
            yaw_c = [Wm] + P.wand_yaw(self.frame(yaw_of(Wm), 0.0, hz - s.deck_top, self.p0), self.p0, wrap(HC - yaw_of(Wm)))
            carry = self.wand_moves([Wm, yaw_c[1]]) + yaw_c[1:] + route
            try:
                R_G = self.g(R_GRIP)
                Gr = self.grasp(self.C, Wm @ R_G, [W @ R_G for W in carry] if not self.skip_traverse else [],
                                FQ_RING_OPEN, FQ_RING, "ring",
                                approach_axes=((0, 0, 1), (0, 1, 0), (0, -1, 0), (0, 0.7071, 0.7071), (0, -0.7071, 0.7071)))
                self.notes["handover1_pose"] = None if cand is None else list(cand)
                break
            except PlanError as e:
                last = e
                print("   ring handover rejected at", cand, e, flush=True)
        if Gr is None:
            raise PlanError(f"ring handover: {last}")
        self.ph("3b_left_release")
        self.release(self.A, Ga, fq_open=FQ_A_OPEN)
        ex.hold(10)
        self.ph("4_right_carry")
        W = ex.wand()
        self.held_track(self.C, self.wand_moves([W, yaw_c[1]]) + yaw_c[1:], Gr, FQ_RING, lin=0.012)
        self.notes["carry_worst_clear_mm"] = {k: v * 1000 for k, v in
                                               self.held_track(self.C, route, Gr, FQ_RING, lin=0.02, check_every=8,
                                                              ignore=("wire", "deck") if self.skip_traverse else ()).items()}
        ex.hold(15)
        kind = _os.environ.get("BUZZ_FINISH", FINISH_TIER.get(s.tier, "gdown"))
        if kind == "relay":
            self.finish_relay(Gr)
            return
        self.ph("5_left_gdown_handover" if kind == "gdown" else "5_left_clamp_handover")
        Wm = ex.wand()
        Rfd = self.Rfd
        last = None
        cands = []
        if kind == "gdown":
            roll, gyaw = GD_TIER.get(s.tier, (0.0, 0.0))
            roll = float(_os.environ.get("BUZZ_GD_ROLL", roll))
            gyaw = float(_os.environ.get("BUZZ_GD_YAW", gyaw))
            gtilt, gxt = GD_TILT_TIER.get(s.tier, (0.0, 0.036))
            gtilt = float(_os.environ.get("BUZZ_GD_TILT", gtilt))
            gxt = float(_os.environ.get("BUZZ_GD_XTIP", gxt))
            G_D, FQ_PEN, FQ_PEN_OPEN = gdown_grip(roll, gyaw, tilt_deg=gtilt, x_tip=gxt)
            self.notes["gdown_roll_yaw_deg"] = [roll, gyaw]
            self.notes["gdown_tilt_deg_xtip"] = [gtilt, gxt]
            # descend at the handover yaw first, then yaw to the finish yaw low (tools/optA_fin.py: at 34-38 mm the
            # pen grip keeps 12-16 mm from the span and 5-9 mm from the deck; higher up the wrist camera meets the span)
            hs = _os.environ.get("BUZZ_GD_HEIGHTS")
            dflt = {"easier": (0.040, 0.044, 0.036, 0.048, 0.050)}.get(s.tier, (0.036, 0.034, 0.038, 0.040, 0.032))
            for hzr in (dflt if not hs else [float(v) for v in hs.split(",")]):
                cands.append(((roll, gyaw), self.g(G_D), FQ_PEN, FQ_PEN_OPEN, hzr))
        else:
            rest = float(s.finish_p[2] - s.deck_top)
            for phi, cs in ((90, 1), (90, -1), (70, 1), (110, 1), (70, -1), (110, -1), (50, 1), (130, 1)):
                G_C, fqh, fqo = ring_clamp(phi, cs)
                for dh in (0.010, 0.012, 0.015, 0.020, 0.008):
                    cands.append(((phi, cs), self.g(G_C), fqh, fqo, rest + dh))
        for key, G_D, FQ_PEN, FQ_PEN_OPEN, hzr in cands:
            Wlow = T_from(Rz(yaw_of(Wm) - self.ang_f) @ Rfd, np.r_[self.p1, s.deck_top + hzr])
            Wy = P.wand_yaw(Wlow, self.p1, wrap(self.ang_f - yaw_of(Wlow)))
            Wd = Wy[-1]
            try:
                follow = [Wm] + interp_T(Wm, Wlow, n_steps(Wm, Wlow)) + Wy
                Gl = self.grasp(self.A, Wm @ G_D, [W @ G_D for W in follow], FQ_PEN_OPEN, FQ_PEN, kind,
                                follow_ignore=("stops",))
                self.notes["release_height_mm"] = float(hzr * 1000)
                self.notes["finish_grip"] = [kind, list(key)]
                break
            except PlanError as e:
                last = e
                print("   finish grip rejected:", kind, key, round(hzr * 1000, 1), e, flush=True)
        else:
            raise PlanError(f"finish handover ({kind}): {last}")
        self.ph("5b_right_release")
        self.release(self.C, Gr, fq_open=-0.007)
        ex.hold(10)
        self.ph("6_left_yaw_lower")
        W = ex.wand()
        self.held_track(self.A, [W] + interp_T(W, Wlow, n_steps(W, Wlow)) + Wy, Gl, FQ_PEN, lin=0.008, ignore=("stops",))
        for _ in range(2):  # aim the measured loop centre over the finish point
            W = ex.wand()
            Wt = T_from(Rfd, np.r_[self.p1, Wd[2, 3]])
            self.held_track(self.A, interp_T(W, Wt, n_steps(W, Wt, lin=0.0005)), Gl, FQ_PEN, lin=0.004, ignore=("stops",))
            ex.hold(10)
        self.ph("6b_left_release_drop")
        self.release(self.A, Gl, fq_open=FQ_PEN_OPEN)
        self.ph("7_settle")
        ex.hold(60)

    def finish_relay(self, Gr):
        """Finish with two handle grips (easier; tools/finish_grip_map.py, results/fgm/):
        5  left pen grip on the outer handle end (tips 62 mm from the loop centre), the carrier releases the ring;
        6  left turns the handle from +y to h_mid at the relay height (its forearm stays clear of the bent span);
        7  right side pinch (closing across the 16 mm height, approach across the handle from -y, centred on the
           inner handle half); left releases;
        8  right turns the handle to the finish yaw, aims the loop centre over the finish point, opens (the side
           pinch's lower finger bars need >= ~54 mm loop height, so the wand drops ~50 mm onto the deck)."""
        s, ex, P = self.s, self.ex, self.P
        A, C = self.A, self.C
        self.ph("5_left_pen_handover")
        Wm = ex.wand()
        Rfd = self.Rfd
        G_L, FQ_L, FQ_L_OPEN = gdown_grip(0.0, 0.0, x_tip=0.062)
        G_L = self.g(G_L)
        last = None
        plan = None
        hzs = _os.environ.get("BUZZ_RELAY_HZ")
        for hz in ((0.056, 0.060, 0.053, 0.064) if not hzs else [float(v) for v in hzs.split(",")]):
            for h_mid in (140.0, 130.0, 150.0, 120.0):
                Wa = T_from(Rz(yaw_of(Wm) - self.ang_f) @ Rfd, np.r_[self.p1, s.deck_top + hz])
                Wy1 = P.wand_yaw(Wa, self.p1, wrap(h_mid - yaw_of(Wa)))
                follow = [Wm] + interp_T(Wm, Wa, n_steps(Wm, Wa)) + Wy1
                try:
                    Gl = self.grasp(A, Wm @ G_L, [W @ G_L for W in follow], FQ_L_OPEN, FQ_L, "relay_pen",
                                    follow_ignore=("stops",))
                    plan = (hz, h_mid, Wa, Wy1)
                    break
                except PlanError as e:
                    last = e
                    print("   relay pen rejected:", hz, h_mid, e, flush=True)
            if plan:
                break
        if plan is None:
            raise PlanError(f"relay pen handover: {last}")
        hz, h_mid, Wa, Wy1 = plan
        self.notes["relay"] = dict(hz_mm=hz * 1000, h_mid_deg=h_mid)
        self.ph("5b_right_release")
        self.release(C, Gr, fq_open=-0.007)
        ex.hold(10)
        self.ph("6_left_turn")
        W = ex.wand()
        self.held_track(A, [W] + interp_T(W, Wa, n_steps(W, Wa)) + Wy1, Gl, FQ_L, lin=0.008, ignore=("stops",))
        ex.hold(10)
        self.ph("7_right_side_pinch")
        W = ex.wand()
        Wf = T_from(Rz(yaw_of(W) - self.ang_f) @ Rfd, np.r_[self.p1, W[2, 3]])
        Wy2 = P.wand_yaw(Wf, self.p1, wrap(self.ang_f - yaw_of(Wf)))
        Wd = Wy2[-1]
        last = None
        for roll, xc in ((90.0, 0.040), (-90.0, 0.040), (90.0, 0.044), (-90.0, 0.044), (90.0, 0.037)):
            G_S, FQ_S, _ = gdown_grip(roll, -90.0 * self.sg, xc=xc)
            G_S = self.g(G_S)
            try:
                Gs = self.grasp(C, W @ G_S, [x @ G_S for x in [W] + Wy2], FQ_S - 0.0036, FQ_S, "relay_side",
                                follow_ignore=("stops",), other_parked=True)
                self.notes["relay"]["side_roll_xc"] = [roll, xc]
                break
            except PlanError as e:
                last = e
                print("   side pinch rejected:", roll, xc, e, flush=True)
        else:
            raise PlanError(f"relay side pinch: {last}")
        self.ph("7b_left_release")
        self.release(A, Gl, fq_open=FQ_L_OPEN)
        ex.hold(10)
        self.ph("8_right_turn_aim")
        W = ex.wand()
        self.held_track(C, [W] + Wy2, Gs, FQ_S, lin=0.008, ignore=("stops",))
        for _ in range(2):  # aim the measured loop centre over the finish point
            W = ex.wand()
            Wt = T_from(Rfd, np.r_[self.p1, Wd[2, 3]])
            self.held_track(C, interp_T(W, Wt, n_steps(W, Wt, lin=0.0005)), Gs, FQ_S, lin=0.004, ignore=("stops",))
            ex.hold(10)
        self.notes["release_height_mm"] = float((ex.wand()[2, 3] - s.deck_top) * 1000)
        self.ph("8b_right_release_drop")
        # open wide enough that the 16 mm handle cannot wedge between the pads when the wand tips off the lower pad
        # (pad gap >= 25 mm > sqrt(16^2 + 18^2)); then wait for the drop before retreating
        fq_rel = float(_os.environ.get("BUZZ_RELAY_OPEN", FQ_S - 0.002))
        ex.grip(C, fq_rel, 15)
        ex.hold(int(_os.environ.get("BUZZ_RELAY_WAIT", "0")))
        self.release(C, Gs, fq_open=fq_rel)
        self.ph("9_settle")
        ex.hold(60)
