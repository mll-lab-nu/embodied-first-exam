"""Below-easy Slotted Post oracle (very_easy): the right hand pinches the ring, lifts it off the post top and holds it in
the goal square.

very_easy (tasks/slotted_post_ring/below_easy.UnderRingLayout): the cord leaves the slot downwards inside the ring and
runs out under it on both sides, so nothing holds the ring. One radial pinch of the tube, a straight lift along the post
past its top, a carry into the goal square and a held placement.

easier (LoopOverRingLayout) has no oracle: its far cord loop lies over the ring and none of the tried moves brings it into
the ring's hole (bead 2 slides on the cord; the E 50 kPa cord cannot be pinched without inverting its tets).
public_session refuses it; docs/rcb/ORACLE_FIXES_2_FOR_JIANWEN.md section 5 has the attempts and the scene options.

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
from .policy import SlottedOraclePolicy, StageFailure

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
# gap between ring and post is widest and the settled cord stays clear of the gripper.
GRASP_ANGLES_DEG = (-40., -50., -30., -20., -60., -10., 0.)


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

    def find_pinch(self, centre, closing, opening):
        """The pinch (p, r, approach, choice) nearest the current arm among the leans / tilts / finger orientations whose
        pre-grasp and pinch the right arm reaches with the arm and the open fingers clear of the post and base; None if
        there is none."""
        q = self.qpos()
        fingers = self.kin.robot._q_indices["right"][6:]
        boxes = list(self.geo.fixture_boxes_m.values())
        current = self.kin.arm("right", q)
        best = None
        for lean in LEANS_DEG:
            for tilt in TILTS_DEG:
                for flip in (1, -1):
                    p, r, approach = self.pinch_pose(centre, closing, lean, tilt, flip)
                    try:
                        qa = self.kin.solve_near("right", p - PRE_GRASP_M * approach, r, q)
                        qb = self.kin.solve_near("right", p, r, qa)
                    except ValueError:
                        continue
                    qa[fingers] = qb[fingers] = opening
                    if max(self.kin.penetration("right", qi, boxes, CLEAR_FIXTURES_M) for qi in (qa, qb)) > 0:
                        continue
                    distance = float(np.abs(self.kin.arm("right", qa) - current).max())
                    if best is None or distance < best[0]:
                        best = (distance, p, r, approach, dict(lean=lean, tilt=tilt, flip=flip))
        return None if best is None else best[1:]

    def ring_pinch(self):
        """First ring angle whose gripper box is clear of the cord and which has a clear, reachable pinch."""
        g = self.geo
        c, n = self.ring()
        cord = self.cord_points()
        rejected = []
        for deg in GRASP_ANGLES_DEG:
            a = np.radians(deg)
            u = geo.inplane([np.cos(a), np.sin(a), 0.], n)
            radial = np.array([u[0], u[1], 0.]) / np.linalg.norm(u[:2])
            clearance = self.ring_pinch_clearance(c, radial, np.array([-radial[1], radial[0], 0.]), cord)
            if clearance < CORD_CLEARANCE_M:
                rejected.append((deg, "cord", round(clearance, 4)))
                continue
            found = self.find_pinch(c + g.ring_major_radius_m * u, radial, PINCH_OPEN_M)
            if found is not None:
                self.note("ring pinch", angle_deg=deg, cord_clearance_m=clearance, rejected=rejected, **found[3])
                return found[:3]
            rejected.append((deg, "no clear reachable pose"))
        raise StageFailure(f"no reachable ring pinch clear of the cord and fixtures: {rejected}")

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
