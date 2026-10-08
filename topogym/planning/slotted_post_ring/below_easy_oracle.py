"""Below-easy Slotted Post oracle: the right hand pinches the ring, lifts it off the post top and holds it in the goal
square; in easier the left hand first carries bead2 into the gap behind the post.

very_easy (tasks/slotted_post_ring/below_easy.UnderRingLayout): the cord leaves the slot downwards inside the ring and
runs out under it on both sides, so nothing holds the ring. One radial pinch of the tube, a straight lift along the post
past its top, a carry into the goal square and a held placement.

easier (LoopOverRingLayout, EasierPolicy): the far cord loop lies over the ring, and bead2 on it (39 mm) does not pass the
gap between ring and post behind it (about 37 mm as the ring settles at birth; 40 mm with the ring centred). The right hand pinches the ring (where its full lift is reachable) and raises it 6 mm;
the left hand goes round the post's -x side, pinches bead2, carries it over the ring's back and lets it down into the gap
behind the post; it then parks. The rest of the loop is cord draped over the ring with both ends inside it: lifting the
ring (shifted 5 mm towards +y) draws it inward off the tube. Pulling the cord in through the slot is not needed (by bead1
it crushes the cord at the bead's bore lip; pushing the left disc works but the left arm's reach ends after ~25 cm).

Every stage plans from the measured privileged state when it starts (ring pose, cord vertices, joints) with the stage
helpers of policy.SlottedOraclePolicy: straight TCP lines and joint transfers, both checked against the fixed parts'
boxes. Arm joints move at most JOINT_SPEED_RAD_S x control_dt per control step, inside the standard service's per-step
limit (public_session also runs the policy through standard_rate.rate_limited_runner). Grasps are physical
finger-friction pinches (this family has no grasp assistance); no simulator state is written.
"""
import numpy as np
from scipy.spatial.transform import Rotation as R

from . import geometry as geo
from .kinematics import frame
from .policy import PathBlocked, SlottedOraclePolicy, StageFailure

DOWN = np.array([0., 0., -1.])
JOINT_SPEED_RAD_S = 1.2        # 0.03 rad per 25 ms control step; the standard service allows 0.04
# ALOHA native finger targets: q is TIP_OFFSET_M more than each fingertip's distance from the gripper axis (the tips
# touch at q = 0.0084), so the 20 mm tube stops the tips at q = 0.0183.
TIP_OFFSET_M = .0083
PINCH_OPEN_M = .024            # tips 31 mm apart around the tube
PINCH_CLOSED_M = .006          # squeeze target; the tube holds the fingers at about 0.018
HELD_TOLERANCE_M = .004        # finger q after closing within this of the tube's contact q
PINCH_DEPTH_M = .012           # the tube centre this far ahead of the TCP along the approach: the fingertips pinch it
PRE_GRASP_M = .07              # approach distance before the pinch
# The gripper body is 150 mm wide across the fingers (73-137 mm behind the TCP) and would meet the post from straight
# above, so the approach leans about the closing axis (along the ring) and optionally about the horizontal axis across it.
LEANS_DEG = (-45., 45., -30., 30., -15., 15.)
TILTS_DEG = (0., 10., -10.)
CLEAR_FIXTURES_M = .002        # arm and open fingers this far outside the post and base boxes at the pinch
CORD_CLEARANCE_M = .004        # cord kept out of the gripper box around the pinch (policy.PINCH_BOX_M)
LIFT_CLEARANCE_M = .03         # ring's lowest point above the post top before the carry
LIFT_STEP_M = .005             # TCP travel per control step while carrying the ring
PLACE_HEIGHT_M = .06           # held ring centre above the table in the goal square
CARRY_YAWS_DEG = (0., -30., 30., -60., 60., -90., 90.)
# Pinch angles about the ring centre (world frame, degrees), in order of preference: the near-right quarter, where the
# gap between ring and post is widest and the settled cord stays clear of the gripper, then round the ring (the rigid
# chain has no bending stiffness and settles beside the post front, over that quarter: 2026-10-07).
GRASP_ANGLES_DEG = (-40., -50., -30., -20., -60., -10., 0., *range(10, 181, 10), *range(-170, -60, 10))


class BelowEasyPolicy(SlottedOraclePolicy):
    def __init__(self, *, kinematics, geometry, control_dt_s=.025):
        super().__init__(kinematics=kinematics, geometry=geometry, control_dt_s=control_dt_s,
                         joint_speed_rad_s=JOINT_SPEED_RAD_S)

    def initialize(self, context):
        if context["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("BelowEasyPolicy requires JOINT_ABS")
        self.dt = float(context["timing_spec"]["control_dt_s"])

    def stages(self):
        return [("lift_ring", self.stage_lift_ring), ("place_ring", self.stage_place_ring)]

    # ----- measurements -------------------------------------------------------------------------------------------
    def ring(self):
        """(centre, unit normal pointing up) of the ring."""
        c, n = geo.ring_disk(self.world, self.geo)
        return c, (n if n[2] > 0 else -n)

    def ring_low_point(self):
        c, n = self.ring()
        g = self.geo
        return c[2] - np.sqrt(max(0., 1 - n[2] ** 2)) * g.ring_major_radius_m - g.ring_tube_radius_m * n[2]

    def finger_q(self, side):
        return float(np.mean(self.obs["robot"][side]["finger_position_m"]))

    @staticmethod
    def pinch_pose(centre, closing, lean, tilt, flip):
        """TCP pose whose fingertips pinch a part centred at centre along the horizontal closing direction; the approach
        is straight down turned by lean about the closing axis and by tilt about the horizontal axis across it; returns
        (p, r, approach)."""
        closing = np.array([closing[0], closing[1], 0.]) / np.linalg.norm(closing[:2])
        across = np.cross([0., 0., 1.], closing)
        out = R.from_rotvec(np.radians(tilt) * across)
        approach = (out * R.from_rotvec(np.radians(lean) * closing)).apply(DOWN)
        return np.asarray(centre, float) - PINCH_DEPTH_M * approach, frame(approach, flip * out.apply(closing)), approach

    def ring_pinch(self):
        """Ring pinch (p, r, approach) at the first angle whose gripper box is clear of the cord, clear of the fixed parts,
        from which the right hand's straight lift reaches the height that takes the ring's lowest point
        LIFT_CLEARANCE_M over the post top."""
        g = self.geo
        c, n = self.ring()
        cord = self.cord_points()
        boxes = list(g.fixture_boxes_m.values())
        fingers = self.kin.robot._q_indices["right"][6:]
        rise = g.post_top_z + LIFT_CLEARANCE_M + .005 - (c[2] - g.ring_tube_radius_m)
        q0 = self.qpos()
        rejected = []
        for deg in GRASP_ANGLES_DEG:
            a = np.radians(deg)
            u = geo.inplane([np.cos(a), np.sin(a), 0.], n)
            radial = np.array([u[0], u[1], 0.]) / np.linalg.norm(u[:2])
            clearance = self.ring_pinch_clearance(c, radial, np.array([-radial[1], radial[0], 0.]), cord)
            if clearance < CORD_CLEARANCE_M:
                rejected.append((deg, "cord", round(clearance, 4)))
                continue
            for lean in LEANS_DEG:
                for tilt in TILTS_DEG:
                    for flip in (1, -1):
                        p, r, approach = self.pinch_pose(c + g.ring_major_radius_m * u, radial, lean, tilt, flip)
                        try:
                            qa = self.kin.solve_near("right", p - PRE_GRASP_M * approach, r, q0)
                            qb = self.kin.solve_near("right", p, r, qa)
                            q = qb
                            for h in np.arange(.02, rise + .02, .02):
                                q = self.kin.solve("right", p + [0., 0., h], r, q)
                        except ValueError:
                            continue
                        qa[fingers] = qb[fingers] = PINCH_OPEN_M
                        if max(self.kin.penetration("right", qi, boxes, CLEAR_FIXTURES_M) for qi in (qa, qb)) > 0:
                            continue
                        self.note("ring pinch", angle_deg=deg, lean=lean, tilt=tilt, flip=flip,
                                  cord_clearance_m=clearance, rejected=rejected)
                        return p, r, approach
            rejected.append((deg, "no liftable pose"))
        raise StageFailure(f"no liftable ring pinch clear of the cord and fixtures: {rejected}")

    # ----- stages -------------------------------------------------------------------------------------------------
    def stage_lift_ring(self):
        """Pinch the tube and lift the ring straight up past the post top."""
        g = self.geo
        p, r, approach = self.ring_pinch()
        self._targets["right"][1] = PINCH_OPEN_M
        yield from self.route("right", p - PRE_GRASP_M * approach, r, speed=self.joint_speed, settle=4)
        yield from self.line({"right": (p, r)}, speed=self.joint_speed, settle=4, step_m=.003)
        yield from self.gripper("right", PINCH_CLOSED_M, steps=8)
        yield from self.hold(12)
        held, expected = self.finger_q("right"), TIP_OFFSET_M + g.ring_tube_radius_m
        self.note("ring pinched", finger_q_m=held, expected_q_m=expected)
        if abs(held - expected) > HELD_TOLERANCE_M:
            raise StageFailure(f"no tube between the fingertips (finger q {held:.4f} m, expected {expected:.4f})")
        # Straight up along the post (its sides are vertical, so the clearances of the resting ring are kept) until the
        # ring's lowest point clears the post top; a second segment if the ring sagged in the fingers.
        for _ in range(3):
            rise = g.post_top_z + LIFT_CLEARANCE_M - self.ring_low_point()
            if rise <= 0:
                break
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp + [0., 0., rise + .005], tr)}, speed=self.joint_speed, settle=2,
                                 step_m=LIFT_STEP_M)
        c, n = self.ring()
        self.note("ring lifted", center=c.tolist(), tilt_deg=float(np.degrees(np.arccos(min(1., n[2])))),
                  low_above_post_top_m=float(self.ring_low_point() - g.post_top_z),
                  on_post=geo.ring_on_post(self.world, g), finger_q_m=self.finger_q("right"))
        if self.ring_low_point() < g.post_top_z + .01:
            raise StageFailure("the ring did not rise past the post top")

    def stage_place_ring(self):
        """Carry the ring off the post top, then on a straight line down into the goal square, and hold it there until
        the task succeeds. The ring may turn about the vertical on the way (the first carry the right arm reaches)."""
        path = self.plan_carry()
        yield from self.follow({"right": path}, self.joint_speed, 4)
        c, n = self.ring()
        self.note("ring placed", center=c.tolist(), tilt_deg=float(np.degrees(np.arccos(min(1., n[2])))))
        # Hold still; the episode ends when the task's own success condition has held for its window.
        self.sync_to_measured(["right"])
        yield from self.hold(160)

    def plan_carry(self):
        """Joint waypoints: level away from the post until the ring is clear of its top, then straight to the ring centre
        PLACE_HEIGHT_M above the goal square's centre, turned by the first yaw (about the ring centre) that plans."""
        g = self.geo
        q = self.kin.with_arm(self.qpos(), "right", self._targets["right"][0])
        tp, tr = self.kin.tcp("right", q)
        c, _ = self.ring()
        off = tp - c
        goal = np.array([*g.goal_center_xy_m, g.table_z_m + PLACE_HEIGHT_M])
        away = (goal - c) * [1., 1., 0.]
        away /= np.linalg.norm(away)
        # Clear of the post when the ring's outer edge passes the post's farthest corner along the carry direction.
        corner = np.abs(away[0]) * g.post_width_m / 2 + np.abs(away[1]) * g.post_depth_m / 2
        clear_c = np.asarray(g.origin_m) * [1., 1., 0.] + [0., 0., c[2]] + away * (
            corner + g.ring_major_radius_m + g.ring_tube_radius_m + .01)
        errors = []
        for yaw in CARRY_YAWS_DEG:
            turn = R.from_rotvec([0., 0., np.radians(yaw)])
            try:
                first = self.kin.line("right", clear_c + off, tr, q, step_m=LIFT_STEP_M)
                q1 = self.kin.with_arm(q, "right", first[-1])
                second = self.kin.line("right", goal + turn.apply(off), turn * tr, q1, step_m=LIFT_STEP_M)
                path = first + second
                self.check_clear({"right": path})
            except ValueError as exc:
                errors.append((yaw, str(exc)[:60]))
                continue
            self.note("ring carry", yaw_deg=yaw, clear_center=clear_c.tolist(), goal_center=goal.tolist(),
                      waypoints=len(path), rejected=errors)
            return path
        raise StageFailure(f"no reachable carry into the goal square: {errors}")

    # ----- helpers --------------------------------------------------------------------------------------------------
    def line(self, targets, speed=None, settle=10, step_m=.004):
        self.sync_to_measured(targets)
        q, paths = self.qpos(), {}
        for side, (p, r) in targets.items():
            q = self.kin.with_arm(q, side, self._targets[side][0])
            paths[side] = self.kin.line(side, p, r, q, step_m=step_m)
            q = self.kin.with_arm(q, side, paths[side][-1])
        yield from self.follow(paths, speed, settle)


# ----- easier (LoopOverRingLayout) ----------------------------------------------------------------------------------
BEAD_OPEN_M = .037             # tips 57 mm apart round the 39 mm bead (the gripper's widest)
# A gentle squeeze, the bead's centre 11 mm ahead of the TCP: on the rigid chain (2026-10-07) a squeeze to 0.006 pressed the
# sphere out between the tips (finger q fell from 0.0257 to closed during the carry, at 12 and 14 mm alike); to 0.020 at
# 11 mm the fingers held 0.0266 from the pinch to the release (depths 9-11 mm and targets 0.016 / 0.020 compared).
BEAD_CLOSED_M = .020
BEAD_PINCH_DEPTH_M = .011
BEAD_HELD_TOLERANCE_M = .005
RING_RAISE_M = .006            # the held ring raised off the cord before bead2 is carried
RING_SHIFTS_M = (.005, .003, 0.)   # +y shift of the held ring before its lift (the gap behind the post widens); the
                                   # first that keeps the hand clear of the post (the inner finger meets its side)
BEAD_CARRY_Z_M = .11           # bead2's centre above the table while carried over the ring
BEAD_POST_GAP_M = .012         # bead2's centre this far beyond (bead radius + the post's back face) when let go: nearer,
                               # the left forearm meets the post; the bead then tips into the gap
BEAD_DROP_CLEAR_M = .003       # bead2's lowest point above the ring's top when let go
VIA_Z_M = .15                  # the left hand's path round the post's -x side: height above the table ...
VIA_X_M = -.30                 # ... and world x (left of the base)
LEFT_PARK_REL = np.array([-.30, .10, .25])   # left hand parked here (from the post centre) for the ring's lift
CARRY_LEVEL_FRACTIONS = (.4, .25, .6)
RING_SET_DOWN_M = .003         # the carried ring's lowest point above the table when the hand opens
HAND_BACK_OFF_M = .06          # the opened hand then moves back along its approach


class EasierPolicy(BelowEasyPolicy):
    """easier: the far cord loop lies over the ring, and bead2 on it (39 mm) does not pass the gap between ring and post
    (about 37 mm as the ring settles), so lifting the ring would jam it against the bead. The right hand holds the ring; the left hand carries
    bead2 over the ring's back and lets it down into the gap behind the post. The rest of the loop is then cord draped
    over the ring with both ends inside it: the lift draws it inward off the tube. Then the very_easy lift and carry."""

    def stages(self):
        return [("hold_ring", self.stage_hold_ring), ("carry_bead", self.stage_carry_bead),
                ("left_clear", self.stage_left_clear), ("lift_ring", self.stage_lift_held_ring),
                ("place_ring", self.stage_place_ring)]

    # ----- measurements -------------------------------------------------------------------------------------------
    def loop_outside(self):
        """Far-side cord points (behind the post) outside the ring's hole, and bead2's centre from the post centre."""
        g = self.geo
        c, _ = self.ring()
        x = self.cord_points()
        far = x[x[:, 1] > g.post_back_y + g.rope_radius_m]
        inner = g.ring_major_radius_m - g.ring_tube_radius_m - g.rope_radius_m
        b, _ = self.body("bead_right")
        return dict(loop_points_outside=int((np.hypot(far[:, 0] - c[0], far[:, 1] - c[1]) > inner).sum()),
                    bead2=(b - np.asarray(g.origin_m)).round(4).tolist())

    # ----- planning -----------------------------------------------------------------------------------------------
    def bead_closing(self):
        """Horizontal closing direction square to bead2's bore (the cord's direction through it)."""
        b, _ = self.body("bead_right")
        s = np.arange(0., geo.cord_length(self.world), .004)
        k = int(np.argmin([np.linalg.norm(geo.cord_point(self.world, v) - b) for v in s]))
        bore = geo.cord_point(self.world, s[k] + .012) - geo.cord_point(self.world, s[k] - .012)
        return np.array([bore[1], -bore[0], 0.]) / np.linalg.norm(bore[:2])

    def bead_plan(self, b, target, carry_z, drop_z):
        """One finger orientation with which the left hand reaches bead2's pre-grasp, pinch, lift, over-gap and drop
        poses clear of the fixed parts: {pose name: (p, r)}. Closing along x first: it keeps the forearm off the post."""
        g = self.geo
        boxes = list(g.fixture_boxes_m.values())
        fingers = self.kin.robot._q_indices["left"][6:]
        centres = dict(pick=b, lift=np.r_[b[:2], carry_z], over=np.r_[target[:2], carry_z], drop=np.r_[target[:2], drop_z])
        q0 = self.qpos()
        for closing in (np.array([1., 0., 0.]), self.bead_closing()):
            for tilt in (-15., 0., 15., -30., 30.):
                for flip in (1, -1):
                    poses, q = {}, q0
                    for name in ("pick", "pre", "lift", "over", "drop"):
                        p, r, approach = self.pinch_pose(centres["pick" if name == "pre" else name], closing, 0., tilt, flip)
                        p = p - (BEAD_PINCH_DEPTH_M - PINCH_DEPTH_M) * approach
                        if name == "pre":
                            p = p - PRE_GRASP_M * approach
                        try:
                            q = self.kin.solve_near("left", p, r, q).copy()
                        except ValueError:
                            break
                        q[fingers] = BEAD_OPEN_M if name in ("pick", "pre") else g.bead_radius_m + TIP_OFFSET_M
                        if self.kin.penetration("left", q, boxes, CLEAR_FIXTURES_M) > 0:
                            break
                        poses[name] = (p, r)
                    else:
                        self.note("bead2 plan", closing=closing.round(3).tolist(), tilt=tilt, flip=flip)
                        return poses
        raise StageFailure("no left-hand carry of bead2 reaching the gap behind the post clear of the fixed parts")

    def side_path(self, side, waypoints, q):
        """Joint waypoints from qpos q through TCP poses [(point, rotation)], each a straight joint interpolation."""
        path = []
        for point, rotation in waypoints:
            a0, a1 = self.kin.arm(side, q), self.kin.arm(side, self.kin.solve_near(side, point, rotation, q))
            path += [a0 + u * (a1 - a0) for u in np.linspace(0, 1, 13)[1:]]
            q = self.kin.with_arm(q, side, path[-1])
        return path

    # ----- stages -------------------------------------------------------------------------------------------------
    def stage_hold_ring(self):
        """Right hand pinches the ring where its straight lift is reachable and raises it a little off the cord."""
        g = self.geo
        p, r, approach = self.ring_pinch()
        self._targets["right"][1] = PINCH_OPEN_M
        yield from self.route("right", p - PRE_GRASP_M * approach, r, speed=self.joint_speed, settle=4)
        yield from self.line({"right": (p, r)}, speed=self.joint_speed, settle=4, step_m=.003)
        yield from self.gripper("right", PINCH_CLOSED_M, steps=8)
        yield from self.hold(12)
        held, expected = self.finger_q("right"), TIP_OFFSET_M + g.ring_tube_radius_m
        self.note("ring pinched", finger_q_m=held, expected_q_m=expected, **self.loop_outside())
        if abs(held - expected) > HELD_TOLERANCE_M:
            raise StageFailure(f"no tube between the fingertips (finger q {held:.4f} m, expected {expected:.4f})")
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp + [0., 0., RING_RAISE_M], tr)}, speed=self.joint_speed, settle=4, step_m=.003)

    def stage_carry_bead(self):
        """Left hand round the post's -x side to bead2, over the ring's back, down into the gap behind the post, open."""
        g = self.geo
        b, _ = self.body("bead_right")
        c, _ = self.ring()
        target = np.array([c[0], g.post_back_y + g.bead_radius_m + BEAD_POST_GAP_M, 0.])
        poses = self.bead_plan(b, target, g.table_z_m + BEAD_CARRY_Z_M,
                               c[2] + g.ring_tube_radius_m + g.bead_radius_m + BEAD_DROP_CLEAR_M)
        self._targets["left"][1] = BEAD_OPEN_M
        self.sync_to_measured(["left"])
        q = self.kin.with_arm(self.qpos(), "left", self._targets["left"][0])
        tp, tr = self.kin.tcp("left", q)
        pre_p, pre_r = poses["pre"]
        z = g.table_z_m + VIA_Z_M
        up = self.kin.line("left", np.array([tp[0], tp[1], z]), tr, q)
        path = self.side_path("left", [(np.array([VIA_X_M, tp[1], z]), pre_r), (np.array([VIA_X_M, pre_p[1], z]), pre_r),
                                       (pre_p, pre_r)], self.kin.with_arm(q, "left", up[-1]))
        yield from self.follow({"left": up + path}, self.joint_speed, 4)
        yield from self.line({"left": poses["pick"]}, speed=self.joint_speed, settle=4, step_m=.003)
        yield from self.gripper("left", BEAD_CLOSED_M, steps=8)
        yield from self.hold(10)
        held, expected = self.finger_q("left"), TIP_OFFSET_M + g.bead_radius_m
        self.note("bead2 pinched", finger_q_m=held, expected_q_m=expected)
        if abs(held - expected) > BEAD_HELD_TOLERANCE_M:
            raise StageFailure(f"no bead between the fingertips (finger q {held:.4f} m, expected {expected:.4f})")
        for name in ("lift", "over"):
            yield from self.line({"left": poses[name]}, speed=self.joint_speed, settle=4)
            self.note(f"bead2 {name}", finger_q_m=self.finger_q("left"), **self.loop_outside())
        yield from self.line({"left": poses["drop"]}, speed=self.joint_speed, settle=10, step_m=.003)
        self.note("bead2 lowered", finger_q_m=self.finger_q("left"), **self.loop_outside())
        yield from self.gripper("left", BEAD_OPEN_M, steps=6, ramp=False)
        tp, tr = self.tcp("left")
        yield from self.line({"left": (tp + [0., 0., .12], tr)}, speed=self.joint_speed, settle=20)
        self.note("bead2 let go", crossings=geo.ring_crossings(self.world, g), **self.loop_outside())

    def stage_left_clear(self):
        """Left hand out of the ring's way: back to the side path, then to its park pose."""
        g = self.geo
        self.sync_to_measured(["left"])
        q = self.kin.with_arm(self.qpos(), "left", self._targets["left"][0])
        tp, tr = self.kin.tcp("left", q)
        path = self.side_path("left", [(np.array([VIA_X_M, tp[1], g.table_z_m + VIA_Z_M]), tr),
                                       (np.asarray(g.origin_m) + LEFT_PARK_REL, tr)], q)
        yield from self.follow({"left": path}, self.joint_speed, 4)

    def stage_lift_held_ring(self):
        """Shift the held ring towards +y (the gap behind the post widens past bead2) and lift it past the post top;
        the cord still draped over the ring slides inward off the tube."""
        g = self.geo
        tp, tr = self.tcp("right")
        for shift in RING_SHIFTS_M:
            try:
                yield from self.line({"right": (tp + [0., shift, .01], tr)}, speed=self.joint_speed, settle=4, step_m=.003)
            except PathBlocked as exc:
                self.note("shift blocked", shift_m=shift, error=str(exc))
                continue
            self.note("ring shifted", shift_m=shift, **self.loop_outside())
            break
        for _ in range(3):
            rise = g.post_top_z + LIFT_CLEARANCE_M - self.ring_low_point()
            if rise <= 0:
                break
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp + [0., 0., rise + .005], tr)}, speed=self.joint_speed, settle=2,
                                 step_m=LIFT_STEP_M)
        c, n = self.ring()
        self.note("ring lifted", center=c.tolist(), tilt_deg=float(np.degrees(np.arccos(min(1., n[2])))),
                  low_above_post_top_m=float(self.ring_low_point() - g.post_top_z), finger_q_m=self.finger_q("right"),
                  crossings=geo.ring_crossings(self.world, g))
        if self.ring_low_point() < g.post_top_z + .01:
            raise StageFailure("the ring did not rise past the post top")

    def stage_place_ring(self):
        """Carry the ring into the goal square, set it down on the table, open and back the hand off, and wait for the
        task's success. Held in one hand on the rigid chain (2026-10-07) the ring swayed at 0.5-1.4 mm/s, across the
        goal's 1 mm/s stillness limit, so the success window never completed; lying on the table it is still."""
        g = self.geo
        yield from self.follow({"right": self.plan_carry()}, self.joint_speed, 4)
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp + [0., 0., g.table_z_m + RING_SET_DOWN_M - self.ring_low_point()], tr)},
                             speed=self.joint_speed, settle=8, step_m=.003)
        yield from self.gripper("right", PINCH_OPEN_M, steps=6, ramp=False)
        yield from self.hold(8)
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp - HAND_BACK_OFF_M * tr.apply([1., 0., 0.]), tr)}, speed=self.joint_speed,
                             settle=4)
        c, n = self.ring()
        self.note("ring set down", center=c.tolist(), tilt_deg=float(np.degrees(np.arccos(min(1., abs(n[2]))))))
        self.sync_to_measured(["right"])
        yield from self.hold(160)

    def plan_carry(self):
        """Joint waypoints: level away from the post until the ring is clear of its top, level on towards the goal
        square (the hand, on the ring's post side, then clears the post top too), then straight to the ring centre
        PLACE_HEIGHT_M above the goal square's centre; the first level fraction / yaw that plans."""
        g = self.geo
        q = self.kin.with_arm(self.qpos(), "right", self._targets["right"][0])
        tp, tr = self.kin.tcp("right", q)
        c, _ = self.ring()
        off = tp - c
        goal = np.array([*g.goal_center_xy_m, g.table_z_m + PLACE_HEIGHT_M])
        away = (goal - c) * [1., 1., 0.]
        away /= np.linalg.norm(away)
        corner = np.abs(away[0]) * g.post_width_m / 2 + np.abs(away[1]) * g.post_depth_m / 2
        clear_c = np.asarray(g.origin_m) * [1., 1., 0.] + [0., 0., c[2]] + away * (
            corner + g.ring_major_radius_m + g.ring_tube_radius_m + .01)
        errors = []
        for fraction in CARRY_LEVEL_FRACTIONS:
            for yaw in CARRY_YAWS_DEG:
                turn = R.from_rotvec([0., 0., np.radians(yaw)])
                try:
                    path, qi = [], q
                    for point, rotation in ((clear_c + off, tr),
                                            (clear_c + fraction * (goal - clear_c) * [1., 1., 0.] + turn.apply(off), turn * tr),
                                            (goal + turn.apply(off), turn * tr)):
                        leg = self.kin.line("right", point, rotation, qi, step_m=LIFT_STEP_M)
                        path += leg
                        qi = self.kin.with_arm(qi, "right", leg[-1])
                    self.check_clear({"right": path})
                except ValueError as exc:
                    errors.append((fraction, yaw, str(exc)[:60]))
                    continue
                self.note("ring carry", level_fraction=fraction, yaw_deg=yaw, waypoints=len(path), rejected=len(errors))
                return path
        raise StageFailure(f"no reachable carry into the goal square: {errors[:6]}")
