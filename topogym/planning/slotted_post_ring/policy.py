"""Slotted Post Ring oracle: a stage script emitting standard JOINT_ABS actions.

Route (mirror of Cabalar & Santos' Fisherman's Folly solution, Fig. 4, using the
left disc): the left disc passes edge-on through the slot from the front to the
back while its bead stays in front; the ring goes over the post top; the bead
passes through the ring; the ring passes edge-on through the slot; the bead
passes back; the free ring is carried to the goal square.

Every stage measures the scene from the privileged world observation when it
starts and re-solves IK from the measured joints; motions are joint-space
interpolations or straight TCP lines, and placement uses a closed-loop TCP
servo. Only rigid parts are grasped, by finger friction; the cord is never
held. No simulator state is written.
"""
import numpy as np
from scipy.spatial.transform import Rotation as R
from . import geometry as geo
from .kinematics import frame


# Grip points on disc1's rim, as in-plane angles from the disc top towards +y (the back).
PICK_ANGLE_RAD = np.radians(-25.)   # front-top; 75 degrees from the cord eye (50 degrees towards the back)
BACK_ANGLE_RAD = np.radians(75.)    # regrasp behind the post once the eye has been turned to the top
GRIP_DEPTH_M = .008                 # TCP inside the rim
# Room kept in the slot beside the disc's -x face for the cord's end stop (11.2 mm across; the disc drifts ~2 mm
# towards it); the disc mid-plane is offset towards +x accordingly.
END_STOP_ROOM_M = .015
# Candidate spots (relative to the post origin) where disc1 is set down right of the base: outside the ring's
# footprint and inside the separator once down; the first reachable, collision-free one is used.
PARK_CANDIDATES_M = ((.21, .03), (.21, -.02), (.19, .07), (.24, .0), (.17, -.06))
# Left hand on the ring: the left arm reaches the ring's -x half, approaching 50 degrees from vertical towards +x.
RING_LEFT_ANGLES_DEG = tuple(range(120, 245, 15))
RING_APPROACH_TILT_RAD = np.radians(50.)
# Gripper envelope around a ring pinch (tangential, radial, below the tube centre), kept clear of the cord.
PINCH_BOX_M = (.030, .035, .016)


# Planned arm configurations keep every collision sample this far outside the fixed parts' boxes.
CLEAR_MARGIN_M = .002
CHECK_STEP_RAD = .05


class StageFailure(RuntimeError):
    pass


class PathBlocked(ValueError):
    """A planned arm path would enter a fixed part (post, base or stand)."""


class StageRetry(RuntimeError):
    """Go back to an earlier stage (re-planned from the measured state)."""
    def __init__(self, stage, reason):
        super().__init__(reason)
        self.stage = stage


MAX_STAGE_RETRIES = 3


class SlottedOraclePolicy:
    def __init__(self, *, kinematics, geometry, control_dt_s=.025, joint_speed_rad_s=.25, stop_after=None,
                 start_at=None):
        self.kin, self.geo = kinematics, geometry
        self.dt, self.joint_speed = float(control_dt_s), float(joint_speed_rad_s)
        self.stop_after = stop_after
        self.start_at = start_at    # development only: resume from a stage of a saved state
        self.obs = None
        self.phase = "start"
        self.done = False
        self.log = []          # (sim time, phase, message, values)
        self._script = None
        self._targets = None   # side -> [arm joints, gripper]

    # ----- protocol ---------------------------------------------------------
    def initialize(self, context):
        if context["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("SlottedOraclePolicy requires JOINT_ABS")
        names = {name for name, _ in self.stages()}
        if self.stop_after is not None and self.stop_after not in names:
            raise ValueError(f"Unknown stop stage: {self.stop_after}")
        if self.start_at is not None and self.start_at not in names:
            raise ValueError(f"Unknown start stage: {self.start_at}")
        if not self.geo.standing_discs and self.start_at in (None, "bead_to_slot", "pick_disc") \
                and self.stop_after != "bead_to_slot":
            raise StageFailure(
                "The imported pickup stage requires an upright disc. Local v15 has flat discs; "
                "a flat-disc pickup must be planned before a full run. The environment is unchanged. "
                "Only --stop-after bead_to_slot is available as an unverified prefix.")

    def act(self, obs):
        if self.done:
            return None
        self.obs = obs
        if self._targets is None:
            self._targets = {side: [np.asarray(obs["robot"][side]["joint_position_rad"], float), None]
                             for side in ("left", "right")}
        if self._script is None:
            self._script = self.script()
        try:
            return next(self._script)
        except StopIteration:
            self.done = True
            return None

    # ----- observation ------------------------------------------------------
    @property
    def world(self):
        return self.obs["privileged"]["world"]

    def qpos(self):
        """Full robot qpos assembled from the observed arm joints (fingers from the last command)."""
        q = np.zeros(self.kin.robot.entity.n_qs)
        for side in ("left", "right"):
            arm = self.obs["robot"][side]
            q[self.kin.robot._q_indices[side][:6]] = arm["joint_position_rad"]
            fingers = arm.get("finger_position_m")
            if fingers is not None:
                q[self.kin.robot._q_indices[side][6:]] = fingers
        return q

    def tcp(self, side):
        arm = self.obs["robot"][side]
        return np.asarray(arm["tcp_position_world_m"], float), R.from_quat(np.asarray(arm["tcp_orientation_wxyz"])[[1, 2, 3, 0]])

    def body(self, name):
        return geo.body(self.world, self.geo, name)

    def note(self, message, **values):
        self.log.append(dict(t=float(self.obs["state"]["sim_time_s"]), phase=self.phase, message=message, **values))

    # ----- action helpers (generators yielding one action per control step) -
    def _action(self):
        out = {}
        for side, (arm, grip) in self._targets.items():
            item = dict(joint_position_rad=[float(v) for v in arm])
            if grip is not None:
                item["gripper_position_m"] = float(grip)
            out[side] = item
        return out

    def hold(self, steps):
        for _ in range(int(steps)):
            yield self._action()

    def gripper(self, side, opening, steps=12, ramp=True):
        start = self._targets[side][1]
        if start is None or not ramp:
            self._targets[side][1] = opening
            yield from self.hold(steps)
            return
        for u in np.linspace(0, 1, int(steps)+1)[1:]:
            # The last step is the exact target: interpolation round-off can leave the gripper range.
            self._targets[side][1] = start+u*(opening-start) if u < 1 else opening
            yield self._action()

    def sync_to_measured(self, sides, tolerance_m=.003):
        """Drop servo wind-up: when a hand is blocked (by a part or fixture) its commanded joints run ahead of the
        measured ones; plan the next motion from where the arm actually is."""
        q = self.qpos()
        for side in sides:
            commanded = self.kin.tcp(side, self.kin.with_arm(q, side, self._targets[side][0]))[0]
            if np.linalg.norm(commanded-self.tcp(side)[0]) > tolerance_m:
                self._targets[side][0] = np.asarray(self.obs["robot"][side]["joint_position_rad"], float).copy()

    def check_clear(self, paths, payload=None):
        """Raise PathBlocked if any (densified) waypoint puts an arm, or the part it carries (payload: side ->
        points fixed in the TCP frame), into a fixed part."""
        boxes = list(self.geo.fixture_boxes_m.values())
        q = self.qpos()
        for side, path in paths.items():
            previous = self._targets[side][0]
            # A hand already touching a fixture (a finger on the base beside a grasped ring) may move as long as
            # it goes no deeper into the clearance margin; elsewhere the full margin applies.
            allowed = self.kin.penetration(side, self.kin.with_arm(q, side, previous), boxes, CLEAR_MARGIN_M)+5e-4
            for arm in path:
                arm = np.asarray(arm, float)
                count = max(1, int(np.ceil(np.abs(arm-previous).max()/CHECK_STEP_RAD)))
                for u in np.linspace(0, 1, count+1)[1:]:
                    qu = self.kin.with_arm(q, side, previous+u*(arm-previous))
                    depth = self.kin.penetration(side, qu, boxes, CLEAR_MARGIN_M)
                    if payload and side in payload:
                        tp, tr = self.kin.tcp(side, qu)
                        depth = max(depth, geo.box_penetration(tr.apply(payload[side])+tp, boxes, CLEAR_MARGIN_M))
                    if depth > allowed:
                        raise PathBlocked(f"{side} hand path enters a fixed part by {depth*1000:.1f} mm")
                previous = arm

    def follow(self, paths, speed=None, settle=10):
        """paths: side -> list of arm joint waypoints; retimed to the joint speed limit and checked clear first."""
        self.check_clear(paths)
        speed = speed or self.joint_speed
        seq = {s: [self._targets[s][0]]+[np.asarray(p, float) for p in path] for s, path in paths.items()}
        n = max(len(v) for v in seq.values())
        for s in seq:
            seq[s] += [seq[s][-1]]*(n-len(seq[s]))
        for i in range(1, n):
            d = max(np.abs(seq[s][i]-seq[s][i-1]).max() for s in seq)
            k = max(1, int(np.ceil(d/(speed*self.dt))))
            for j in range(1, k+1):
                for s in seq:
                    self._targets[s][0] = seq[s][i-1]+(j/k)*(seq[s][i]-seq[s][i-1])
                yield self._action()
        yield from self.hold(settle)

    def goto(self, targets, speed=None, settle=10, waypoints=12):
        """Joint-space transfer to multi-seed IK solutions; free space only."""
        self.sync_to_measured(targets)
        q, paths = self.qpos(), {}
        for side, (p, r) in targets.items():
            a0 = self._targets[side][0]
            a1 = self.kin.arm(side, self.kin.solve_near(side, p, r, q))
            paths[side] = [a0+u*(a1-a0) for u in np.linspace(0, 1, waypoints+1)[1:]]
        yield from self.follow(paths, speed, settle)

    def route(self, side, p, r, *, speed=.3, settle=6, heights=(1.32, 1.26, 1.20, 1.14), payload=None):
        """Reach (p, r) through free space: directly, over the top at the highest workable height, or round
        the side of the post. Every candidate is planned in full and collision-checked before it is executed."""
        from scipy.spatial.transform import Slerp
        p = np.asarray(p, float)
        self.sync_to_measured([side])
        q0 = self.kin.with_arm(self.qpos(), side, self._targets[side][0])
        tp, tr = self.kin.tcp(side, q0)
        turn = Slerp([0, 1], R.concatenate([tr, r]))
        post_lo, post_hi = (np.asarray(v) for v in self.geo.fixture_boxes_m["post"])
        candidates = [[("joint", p, r)]]
        for z in heights:
            if z > max(tp[2], p[2]):
                candidates.append([("line", (tp[0], tp[1], z), tr), ("joint", (p[0], p[1], z), r), ("line", p, r)])
                candidates.append([("joint", (tp[0], tp[1], z), r), ("joint", (p[0], p[1], z), r), ("line", p, r)])
        for clearance in (.07, .10, .13):
            side_x = post_hi[0]+clearance if side == "right" else post_lo[0]-clearance
            for z in (p[2], p[2]+.05, tp[2]):
                for last in ("line", "joint"):
                    candidates.append([("joint", (side_x, tp[1], z), turn(1/3)),
                                       ("joint", (side_x, p[1], z), turn(2/3)), (last, p, r)])
        error = None
        for legs in candidates:
            try:
                path, q = [], q0
                for kind, point, rotation in legs:
                    point = np.asarray(point, float)
                    if kind == "line":
                        segment = self.kin.line(side, point, rotation, q)
                    else:
                        a0, a1 = self.kin.arm(side, q), self.kin.arm(side, self.kin.solve_near(side, point, rotation, q))
                        segment = [a0+u*(a1-a0) for u in np.linspace(0, 1, 13)[1:]]
                    path += segment
                    q = self.kin.with_arm(q, side, segment[-1])
                self.check_clear({side: path}, None if payload is None else {side: payload})
            except ValueError as exc:
                error = exc
                continue
            yield from self.follow({side: path}, speed, settle)
            return
        raise StageFailure(f"no collision-free route for the {side} hand: {error}")

    def line(self, targets, speed=None, settle=10):
        self.sync_to_measured(targets)
        q, paths = self.qpos(), {}
        for side, (p, r) in targets.items():
            q = self.kin.with_arm(q, side, self._targets[side][0])
            paths[side] = self.kin.line(side, p, r, q)
            q = self.kin.with_arm(q, side, paths[side][-1])
        yield from self.follow(paths, speed, settle)

    def servo(self, targets, iters=12, steps=8, tol=.0008, limit=.03):
        """Integral TCP correction (position and orientation) against the measured TCP; returns position errors."""
        corr = {s: np.zeros(3) for s in targets}
        rcorr = {s: np.zeros(3) for s in targets}
        errs = {}
        for _ in range(iters):
            q = self.qpos()
            errs = {}
            for side, (p, r) in targets.items():
                actual, actual_r = self.tcp(side)
                e = np.asarray(p, float)-actual
                errs[side] = float(np.linalg.norm(e))
                corr[side] = np.clip(corr[side]+e, -limit, limit)
                rcorr[side] = np.clip((r*actual_r.inv()).as_rotvec()+rcorr[side], -.3, .3)
                self._targets[side][0] = self.kin.arm(side, self.kin.solve(
                    side, np.asarray(p)+corr[side], R.from_rotvec(rcorr[side])*r, q))
            if max(errs.values()) < tol:
                break
            yield from self.hold(steps)
        return errs

    # ----- the route ----------------------------------------------------------
    def script(self):
        stages = self.stages()
        names = [name for name, _ in stages]
        i = names.index(self.start_at) if self.start_at is not None else 0
        retries = 0
        while i < len(stages):
            name, stage = stages[i]
            self.phase = name
            self.note("stage start")
            try:
                yield from stage()
            except StageRetry as exc:
                retries += 1
                self.note("stage retry", back_to=exc.stage, reason=str(exc), retries=retries)
                if retries > MAX_STAGE_RETRIES:
                    raise StageFailure(f"{name}: {exc} (retries exhausted)")
                i = names.index(exc.stage)
                continue
            self.note("stage end")
            if self.stop_after == name:
                return
            i += 1

    def stages(self):
        return [("bead_to_slot", self.stage_bead_to_slot),
                ("pick_disc", self.stage_pick_disc), ("disc_into_slot", self.stage_disc_into_slot),
                ("disc_out_back", self.stage_disc_out_back), ("park_disc", self.stage_park_disc),
                ("ring_over_post", self.stage_ring_over_post), ("ring_edge_on", self.stage_ring_edge_on),
                ("ring_into_slot", self.stage_ring_into_slot), ("ring_out_front", self.stage_ring_out_front),
                ("ring_off_bight", self.stage_ring_off_bight), ("disc_tidy", self.stage_disc_tidy),
                ("ring_to_goal", self.stage_ring_to_goal)]

    def disc(self):
        """(center, rotation, face normal) of disc1, using the current instance's authored disc plane."""
        c, rd = self.body("disc_left")
        return c, rd, rd.apply(self.geo.disc_normal_local)

    def rim_grip(self, angle_rad):
        """TCP pose pinching disc1's rim at an in-plane angle from the top towards +y; returns (p, r, u)."""
        c, _, n = self.disc()
        u = geo.inplane([0., np.sin(angle_rad), np.cos(angle_rad)], n)
        return c+(self.geo.disc_radius_m-GRIP_DEPTH_M)*u, frame(-u, n if n[0] > 0 else -n), u

    def take_rim(self, angle_rad):
        """Approach, align in the disc plane and close the right hand on disc1's rim."""
        p, r, u = self.rim_grip(angle_rad)
        try:
            yield from self.line({"right": (p+u*.02, r)}, speed=.1, settle=8)
        except PathBlocked:
            raise
        except ValueError:
            # No continuous straight line from here (IK branch): a checked joint-space move instead.
            yield from self.goto({"right": (p+u*.02, r)}, speed=.15, settle=8)
        for _ in range(4):
            p, r, u = self.rim_grip(angle_rad)
            yield from self.servo({"right": (p, r)}, tol=.0005, limit=.02)
            c, _, n = self.disc()
            if abs(float(np.dot(self.tcp("right")[0]-c, n))) < .0015:
                break
        yield from self.gripper("right", .02, steps=4, ramp=False)
        yield from self.gripper("right", .002, steps=36)

    def grip_angle(self, side="right"):
        c, _, n = self.disc()
        d = geo.inplane(self.tcp(side)[0]-c, n)
        return float(np.arctan2(d[1], d[2]))

    def disc_pose_targets(self):
        """TCP poses carrying the held disc edge-on along the slot axis: (center y, center z) -> (p, r).

        The measured grip offset is kept. The disc is turned so that its face normal is world x and its cord
        eye is on top, clear of the front and back grips; its -x face keeps END_STOP_ROOM_M to the slot wall.
        """
        c, rd, n = self.disc()
        tp, tr = self.tcp("right")
        eye = geo.inplane(geo.cord_point(self.world, 0.)-c, n)
        target = R.from_rotvec([np.arctan2(eye[1], eye[2]), 0., 0.])*R.align_vectors([[1., 0., 0.]], [n])[0]*rd
        off_p, off_r = rd.inv().apply(tp-c), rd.inv()*tr
        x = self.geo.slot_center[0]+max(0., END_STOP_ROOM_M+self.geo.disc_thickness_m/2-self.geo.slot_width_m/2)

        def pose_at(center_y, center_z):
            return np.array([x, center_y, center_z])+target.apply(off_p), target*off_r
        return pose_at, target

    def bead_grip(self, name="bead_left"):
        """Top-down pinch across a bead, closing horizontally and square to its bore (the cord's direction)."""
        b, _ = self.body(name)
        s = np.arange(0., float(np.max(self.world["fem"]["cord"]["material_s_m"])), .004)
        k = int(np.argmin([np.linalg.norm(geo.cord_point(self.world, v)-b) for v in s]))
        bore = geo.cord_point(self.world, s[k]+.012)-geo.cord_point(self.world, s[k]-.012)
        bore[2] = 0.
        bore /= np.linalg.norm(bore)
        return b, frame([0., 0., -1.], [bore[1], -bore[0], 0.])

    def stage_bead_to_slot(self):
        """Right hand sets bead1 on the base just in front of the slot, so the cord between disc1 and the slot
        is slack (the table loop otherwise has to be dragged and pulls the disc back out of the slot)."""
        g = self.geo
        base_top = g.fixture_boxes_m["base"][1][2]

        def spots():
            # As close to the slot as the gripper allows (its carriage is wide across the closing direction).
            for gap in (.008, .02, .03, .045, .06):
                yield np.array([g.origin_m[0]-.015, g.post_front_y-g.bead_radius_m-gap, base_top+g.bead_radius_m+.004])
        target = next(spots())
        for attempt in range(3):
            b, r = self.bead_grip()
            self._targets["right"][1] = .037
            yield from self.route("right", b+[0., 0., .07], r, speed=.5)
            yield from self.line({"right": (b+[0., 0., .004], r)}, speed=.1, settle=4)
            b, _ = self.body("bead_left")
            yield from self.servo({"right": (b+[0., 0., .004], r)}, iters=8, limit=.01)
            yield from self.gripper("right", .004, steps=30)
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp+[0., 0., .06], tr)}, speed=.1, settle=4)
            lifted = self.body("bead_left")[0][2]-b[2]
            self.note("bead lift", attempt=attempt, rise_m=float(lifted))
            if lifted < .03:
                yield from self.gripper("right", .037, steps=8, ramp=False)
                continue
            offset = self.tcp("right")[0]-self.body("bead_left")[0]
            target = next((t for t in spots() if self.pose_clear("right", t+offset, tr)
                           and self.pose_clear("right", t+offset+[0., 0., .05], tr)), None)
            if target is None:
                raise StageFailure("no clear spot for bead1 in front of the slot")
            yield from self.route("right", target+offset+[0., 0., .05], tr, speed=.2)
            yield from self.line({"right": (target+offset, tr)}, speed=.08, settle=8)
            yield from self.gripper("right", .037, steps=10, ramp=False)
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp+[0., 0., .06], tr)}, speed=.15, settle=20)
            b = self.body("bead_left")[0]
            self.note("bead placed", center=b.tolist(), error_m=float(np.linalg.norm(b[:2]-target[:2])))
            if np.linalg.norm(b[:2]-target[:2]) < .03:
                return
        raise StageFailure("bead1 not placed in front of the slot")

    def stage_pick_disc(self):
        """Right hand pinches disc1's front-top rim and lifts it out of its stand (re-measured and retried)."""
        for attempt in range(3):
            p, r, u = self.rim_grip(PICK_ANGLE_RAD)
            self._targets["right"][1] = .037
            yield from self.route("right", p+u*.07, r, speed=.5, settle=15)
            c0 = self.disc()[0]
            yield from self.take_rim(PICK_ANGLE_RAD)
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp+[0., 0., .04], tr)}, speed=.08, settle=15)
            c = self.disc()[0]
            self.note("disc lift", attempt=attempt, center=c.tolist(), rise_m=float(c[2]-c0[2]))
            if c[2]-c0[2] > .03:
                return
            yield from self.gripper("right", .037, steps=8, ramp=False)
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp-tr.apply([.05, 0., 0.]), tr)}, speed=.15, settle=20)
        raise StageFailure("disc did not leave its stand with the hand")

    def pose_clear(self, side, p, r):
        """Whether the hand pose (p, r) is reachable with every collision sample outside the fixed parts."""
        try:
            q = self.kin.solve_near(side, p, r, self.qpos())
        except ValueError:
            return False
        return self.kin.penetration(side, q, list(self.geo.fixture_boxes_m.values()), CLEAR_MARGIN_M) == 0

    def slot_cord_top(self, below_z=np.inf):
        """Top of the cord lying through the slot below below_z (z, m); the slot floor if none is there.

        below_z excludes the cord coming from a disc that is itself in the slot (its eye is at the disc's top)."""
        g = self.geo
        cord = self.cord_points()
        in_slot = cord[(cord[:, 1] > g.post_front_y-.01) & (cord[:, 1] < g.post_back_y+.01)
                       & (np.abs(cord[:, 0]-g.slot_center[0]) < g.slot_width_m/2+.005) & (cord[:, 2] < below_z)]
        floor = g.origin_m[2]+g.slot_bottom_m+g.slot_width_m/2
        return float(in_slot[:, 2].max())+g.rope_radius_m if len(in_slot) else floor

    def stage_disc_into_slot(self):
        """Carry the held disc edge-on to the slot front and push it along +y until the fingers would touch the
        post (collision-checked, not a fixed limit)."""
        g = self.geo
        pose_at, _ = self.disc_pose_targets()
        # Ride above the cord already lying through the slot (the disc's rim would pinch it against the rounded
        # slot bottom), and below the slot top.
        floor = g.origin_m[2]+g.slot_bottom_m+g.slot_width_m/2
        cord_top = self.slot_cord_top()
        z = min(max(floor, cord_top+.012)+g.disc_radius_m,
                g.origin_m[2]+g.slot_top_m-g.slot_width_m/2-g.disc_radius_m-.006)
        self.note("slot height", disc_bottom_z=float(z-g.disc_radius_m), cord_top_z=cord_top)
        front = g.post_front_y-g.disc_radius_m-.02
        yield from self.route("right", *pose_at(front-.04, z+.02), speed=.3)
        yield from self.line({"right": pose_at(front, z)}, speed=.12, settle=8)
        yield from self.servo({"right": pose_at(front, z)}, iters=8, limit=.01)
        center_y, step, regrasps = front, .01, 0
        while step >= .0025 and self.disc()[0][1] < g.post_back_y-.002:
            try:
                yield from self.line({"right": pose_at(center_y+step, z)}, speed=.08, settle=4)
            except PathBlocked:
                step /= 2
                continue
            center_y += step
            yield from self.servo({"right": pose_at(center_y, z)}, iters=4, limit=.006)
            lag = center_y-self.disc()[0][1]
            if lag > .006:
                if regrasps == 3:
                    self.note("disc keeps slipping; push stopped", lag_m=float(lag))
                    break
                # Re-take the rim at the same place on the disc and continue from where the disc is.
                regrasps += 1
                self.note("disc slipped in the fingers; regrasping", lag_m=float(lag))
                angle = self.grip_angle()
                yield from self.gripper("right", .037, steps=8, ramp=False)
                tp, tr = self.tcp("right")
                yield from self.line({"right": (tp-tr.apply([.02, 0., 0.]), tr)}, speed=.1, settle=8)
                yield from self.take_rim(angle)
                pose_at, _ = self.disc_pose_targets()
                center_y = float(self.disc()[0][1])
        c, _, n = self.disc()
        self.note("disc pushed", center=c.tolist(), cord_volume_ratio=geo.cord_volume_ratio(self.world))
        p, r, _ = self.rim_grip(BACK_ANGLE_RAD)
        if not self.pose_clear("right", p, r):
            raise StageFailure("disc not far enough through the slot for a clear back grip")

    def stage_disc_out_back(self):
        """Set the disc down in the slot, let go, regrasp it behind the post and pull it out of the slot."""
        g = self.geo
        # Set the disc down until its rim almost rests on the cord in the slot: released higher, it wedges across
        # the slot and slides out in front.
        c = self.disc()[0]
        drop = c[2]-g.disc_radius_m-(self.slot_cord_top(below_z=c[2]-g.disc_radius_m)+.003)
        tp, tr = self.tcp("right")
        if drop > .001:
            yield from self.line({"right": (tp-[0., 0., drop], tr)}, speed=.03, settle=10)
        yield from self.gripper("right", .02, steps=12, ramp=False)
        yield from self.gripper("right", .037, steps=8, ramp=False)
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp-tr.apply([.05, 0., 0.]), tr)}, speed=.06, settle=20)
        c = self.disc()[0]
        self.note("disc released in the slot", center=c.tolist(), dropped_m=float(drop))
        if not (g.post_front_y-.005 < c[1] < g.post_back_y+g.disc_radius_m
                and abs(c[0]-g.slot_center[0]) < g.slot_width_m/2):
            raise StageRetry("pick_disc", "disc left the slot when released")
        # Over the top or round the post's side, whichever is reachable and clear. Pull until the trailing rim
        # has left the post's back face, regrasping whenever the disc slips in the fingers.
        for attempt in range(4):
            p, r, u = self.rim_grip(BACK_ANGLE_RAD)
            if attempt == 0:
                yield from self.route("right", p+u*.06, r, speed=.3, settle=8)
            yield from self.take_rim(BACK_ANGLE_RAD)
            tp, tr = self.tcp("right")
            c = self.disc()[0]
            slipped = False
            for dy in np.arange(.01, g.post_back_y+g.disc_radius_m+.02-c[1], .01):
                yield from self.line({"right": (tp+[0., dy, 0.], tr)}, speed=.08, settle=4)
                if dy-(self.disc()[0][1]-c[1]) > .006:
                    slipped = True
                    break
            if not slipped:
                break
            self.note("disc slipped while leaving the slot; regrasping", attempt=attempt)
            yield from self.gripper("right", .037, steps=8, ramp=False)
            tp, tr = self.tcp("right")
            yield from self.line({"right": (tp-tr.apply([.03, 0., 0.]), tr)}, speed=.1, settle=10)
        if self.disc()[0][1]-g.disc_radius_m < g.post_back_y+.003:
            raise StageFailure("disc did not leave the slot")
        c = self.disc()[0]
        self.note("disc behind the post", center=c.tolist(), cord_volume_ratio=geo.cord_volume_ratio(self.world))

    def disc_in_hand(self, side="right", count=48):
        """Disc1 rim and face samples in the TCP frame (the payload while it is carried)."""
        c, rd, n = self.disc()
        tp, tr = self.tcp(side)
        t = np.linspace(0, 2*np.pi, count, endpoint=False)
        ring = np.column_stack([np.zeros(count), np.cos(t), np.sin(t)])*self.geo.disc_radius_m
        faces = [ring+[h, 0., 0.] for h in (-self.geo.disc_thickness_m/2, self.geo.disc_thickness_m/2)]
        world = rd.apply(np.vstack(faces))+c
        return tr.inv().apply(world-tp)

    def stage_park_disc(self):
        """Stand disc1 on the table beside the base, outside the ring's footprint, let go and tip it over.

        The spot is the first candidate whose collision-free route and set-down pose are reachable; lying flat
        or leaning on the base both count, as long as the disc stays out of the ring's way."""
        g = self.geo
        c, rd, _ = self.disc()
        tp, tr = self.tcp("right")
        off_p, off_r = rd.inv().apply(tp-c), rd.inv()*tr
        payload = self.disc_in_hand()

        def pose(center):
            return np.asarray(center, float)+rd.apply(off_p), rd*off_r
        yield from self.line({"right": pose([c[0], c[1], c[2]+.02])}, speed=.1, settle=4)
        down_z = g.table_z_m+g.disc_radius_m+.004
        for dx, dy in PARK_CANDIDATES_M:
            x, y = g.origin_m[0]+dx, g.origin_m[1]+dy
            if not self.pose_clear("right", *pose([x, y, down_z])):
                continue
            try:
                yield from self.route("right", *pose([x, y, c[2]+.02]), speed=.2, settle=8, payload=payload)
                break
            except StageFailure:
                continue
        else:
            raise StageFailure("no reachable parking spot for disc1")
        yield from self.line({"right": pose([x, y, down_z])}, speed=.08)
        yield from self.gripper("right", .037, steps=12, ramp=False)
        tp, tr = self.tcp("right")
        for dx in (.01, .02, .03, .045):
            yield from self.line({"right": (tp+[dx, 0., 0.], tr)}, speed=.1, settle=4)
            if abs(self.disc()[2][2]) > .5:
                break
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp+[0., 0., .08], tr)}, speed=.2, settle=40)
        c, _, n = self.disc()
        reach = np.linalg.norm(c[:2]-np.asarray(g.origin_m[:2]))-g.disc_radius_m
        self.note("disc parked", center=c.tolist(), normal=n.tolist(), clearance_from_ring_m=float(
            reach-g.ring_major_radius_m-g.ring_tube_radius_m))
        # Lying flat or leaning does not matter; it must stay out of the ring's way up the post.
        if reach < g.ring_major_radius_m+g.ring_tube_radius_m+.005:
            raise StageFailure("disc parked inside the ring's footprint")

    def cord_points(self, step_m=.005):
        s = np.arange(0., float(np.max(self.world["fem"]["cord"]["material_s_m"])), step_m)
        return np.array([geo.cord_point(self.world, v) for v in s])

    def ring_pinch_clearance(self, center, radial, tangent, cord):
        """Distance from the cord to the gripper box around a ring pinch (negative when the cord is inside)."""
        d = cord-(center+self.geo.ring_major_radius_m*radial)
        t, r, below = PINCH_BOX_M
        gap = np.column_stack([np.abs(d @ tangent)-t, np.abs(d @ radial)-r, -below-d[:, 2]])
        inside = (gap < 0).all(axis=1)
        return -1. if inside.any() else float(np.linalg.norm(np.maximum(gap, 0), axis=1).min())

    def stage_ring_over_post(self):
        """Lift the ring off the post with the left hand; a ring that drops back onto the post is lifted again.

        Lifted past the top it tips over behind the post, and the front bight (bead1) slips off its front: the
        ring ends hanging behind the post on the two strands leaving the slot (Fisherman's Folly state s3)."""
        for attempt in range(3):
            yield from self.lift_ring_once()
            if not geo.ring_on_post(self.world, self.geo):
                yield from self.gripper("left", .03, steps=8, ramp=False)
                tp, tr = self.tcp("left")
                yield from self.line({"left": (tp+[0., 0., .04], tr)}, speed=.15, settle=30)
                crossings = self.crossings()
                self.note("ring off the post", crossings=crossings)
                if [side for _, _, side in crossings] != ["back", "back"]:
                    raise StageFailure(f"expected the ring on the two back strands, found {crossings}")
                return
            self.note("ring still on the post; retrying", attempt=attempt)
            yield from self.gripper("left", .028, steps=8, ramp=False)
            tp, tr = self.tcp("left")
            yield from self.line({"left": (tp+[0., 0., .05], tr)}, speed=.2, settle=20)
        raise StageFailure("ring still on the post")

    def lift_ring_once(self):
        """Left hand pinches the ring where the cord leaves room and lifts it along the post past the top."""
        g = self.geo
        c, rr = self.body("target_ring")
        cord = self.cord_points()
        best = None
        for a in np.radians(RING_LEFT_ANGLES_DEG):
            radial, tangent = np.array([np.cos(a), np.sin(a), 0.]), np.array([-np.sin(a), np.cos(a), 0.])
            clearance = self.ring_pinch_clearance(c, radial, tangent, cord)
            if best is None or clearance > best[0]:
                best = (clearance, radial)
        clearance, radial = best
        self.note("ring pinch", angle_deg=float(np.degrees(np.arctan2(radial[1], radial[0]))), clearance_m=clearance)
        if clearance < .01:
            raise StageFailure("no ring pinch clear of the cord")
        approach = np.array([np.sin(RING_APPROACH_TILT_RAD), 0., -np.cos(RING_APPROACH_TILT_RAD)])
        r = frame(approach, radial-np.dot(radial, approach)*approach)
        # Slightly above the tube's centre: the tilted fingers otherwise press on the base under the ring.
        p = c+g.ring_major_radius_m*radial+[0., 0., .008]
        self._targets["left"][1] = .028
        yield from self.route("left", p-approach*.08, r, speed=.4, settle=8)
        yield from self.line({"left": (p-approach*.02, r)}, speed=.12, settle=6)
        yield from self.servo({"left": (p, r)}, iters=10, tol=.0006, limit=.01)
        yield from self.gripper("left", .002, steps=30)
        tp, tr = self.tcp("left")
        for dz in np.arange(.02, .42, .02):
            yield from self.line({"left": (tp+[0., 0., dz], tr)}, speed=.08, settle=3)
            c2, r2 = self.body("target_ring")
            n = r2.apply([0., 0., 1.])
            low = c2[2]-np.sqrt(max(0., 1-n[2]**2))*g.ring_major_radius_m-g.ring_tube_radius_m
            if low > g.post_top_z+.015:
                break
        c2, _ = self.body("target_ring")
        crossings = geo.ring_crossings(self.world, g)
        self.note("ring lifted", center=c2.tolist(), on_post=geo.ring_on_post(self.world, g), crossings=crossings,
                  cord_volume_ratio=geo.cord_volume_ratio(self.world))
        # Success is topological: the ring is off the post, whether still held above it or dropped behind it.

    # ----- ring through the slot ---------------------------------------------
    def crossings(self):
        """Cord crossings of the ring's disk as (material s, sign, 'front'|'slot'|'back' of the post)."""
        g, out = self.geo, []
        for s_m, sign in geo.ring_crossings(self.world, g):
            y = geo.cord_point(self.world, s_m)[1]
            out.append((s_m, sign, "front" if y < g.post_front_y else "back" if y > g.post_back_y else "slot"))
        return out

    def ring_pose(self):
        """(centre, unit normal with a non-positive x component) of the ring."""
        c, n = geo.ring_disk(self.world, self.geo)
        return c, (n if n[0] <= 0 else -n)

    def ring_slot_height(self):
        """Ring centre height in the slot: the lowest tube clears the rounded slot bottom by 2 mm."""
        g = self.geo
        floor = g.origin_m[2]+g.slot_bottom_m+g.slot_width_m/2
        return floor-(g.slot_width_m/2-g.ring_tube_radius_m)+g.ring_major_radius_m+.002

    def stage_ring_edge_on(self):
        """Right hand pinches the hanging ring at its top from above and turns it edge-on (plane along the slot)
        behind the slot, above the slot's mid-height."""
        g = self.geo
        R_ = g.ring_major_radius_m
        c, n = self.ring_pose()
        up = np.cross(n, np.cross([0., 0., 1.], n))
        top = c+R_*up/np.linalg.norm(up)
        r = frame([0., 0., -1.], n)
        above = next((h for h in (.05, .04, .03, .02) if self.pose_clear("right", top+[0., 0., h], r)), None)
        if above is None:
            raise StageFailure("ring top not reachable from above")
        self._targets["right"][1] = .028
        yield from self.route("right", top+[0., 0., above], r, speed=.3)
        yield from self.line({"right": (top+[0., 0., .004], r)}, speed=.08, settle=6)
        yield from self.servo({"right": (top+[0., 0., .004], r)}, iters=8, limit=.008)
        yield from self.gripper("right", .002, steps=30)
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp+[0., 0., .02], tr)}, speed=.08, settle=6)
        # Turn about the vertical through the ring centre by a quarter turn, ending behind the slot.
        from scipy.spatial.transform import Slerp
        tp, tr = self.tcp("right")
        c, _ = self.ring_pose()
        off = tp-c
        end_c = np.array([g.slot_center[0], g.post_back_y+R_+g.ring_tube_radius_m+.03, g.slot_center[2]+.026])
        for sign in (1, -1):
            turn = R.from_rotvec([0., 0., sign*np.pi/2])
            if self.pose_clear("right", end_c+turn.apply(off), turn*tr):
                break
        else:
            raise StageFailure("no reachable edge-on pose behind the slot")
        sweep = Slerp([0, 1], R.concatenate([R.identity(), turn]))
        for f in (.25, .5, .75, 1.):
            point = c+f*(end_c-c)+[0., 0., .03*np.sin(np.pi*f)]
            yield from self.goto({"right": (point+sweep(f).apply(off), sweep(f)*tr)}, speed=.2, waypoints=8, settle=4)
        c, n = self.ring_pose()
        self.note("ring edge-on behind the slot", center=c.tolist(), normal=n.tolist(), crossings=self.crossings())
        if abs(n[0]) < .9:
            raise StageFailure("ring not edge-on")

    def stage_ring_into_slot(self):
        """Left hand takes the ring's rear point in the ring plane (one finger inside the ring), the right lets
        go, and the left pushes the ring edge-on into the slot until its fingers near the post (collision-checked)."""
        g = self.geo
        R_ = g.ring_major_radius_m
        c, n = self.ring_pose()
        d = geo.inplane([0., 1., 0.], n)
        p, approach = c+R_*d, -n
        r = frame(approach, d)
        self._targets["left"][1] = .03
        yield from self.route("left", p-approach*.07, r, speed=.3)
        yield from self.line({"left": (p-approach*.015, r)}, speed=.08, settle=4)
        c, n = self.ring_pose()
        yield from self.servo({"left": (c+R_*geo.inplane([0., 1., 0.], n), r)}, iters=8, limit=.008)
        yield from self.gripper("left", .002, steps=30)
        yield from self.gripper("right", .03, steps=10, ramp=False)
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp+[0., 0., .05], tr)}, speed=.1, settle=10)
        lp, lr = self.tcp("left")
        c, _ = self.ring_pose()
        off = lp-c
        z = self.ring_slot_height()
        x = g.slot_center[0]
        yield from self.line({"left": (np.array([x, c[1], z])+off, lr)}, speed=.06, settle=8)
        for center_y in np.arange(c[1]-.01, g.origin_m[1]-g.post_depth_m, -.01):
            try:
                yield from self.line({"left": (np.array([x, center_y, z])+off, lr)}, speed=.06, settle=3)
            except PathBlocked:
                break
            c2, _ = self.ring_pose()
            if abs((self.tcp("left")[0]-c2)[1]-off[1]) > .008:
                break
        c, _ = self.ring_pose()
        crossings = self.crossings()
        self.note("ring pushed into the slot", center=c.tolist(), crossings=crossings)
        if c[1]-R_ > g.post_front_y-.03:
            raise StageFailure("ring front not far enough out of the slot for the front grip")

    def stage_ring_out_front(self):
        """Right hand takes the ring's front point in the ring plane on an IK branch that can pull it all the way
        out, the left lets go, and the right pulls until the ring's rear clears the post's front face."""
        g = self.geo
        R_ = g.ring_major_radius_m
        c, n = self.ring_pose()
        d = geo.inplane([0., -1., 0.], n)
        p, approach = c+R_*d, n
        out = g.post_front_y-R_-g.ring_tube_radius_m-.02
        pull = p+[0., out-c[1], 0.]
        q0 = self.qpos()
        chosen = None
        for sign in (1., -1.):
            r = frame(approach, sign*d)
            for seed in self.kin.seeds("right", q0):
                try:
                    q_app = self.kin.solve("right", p-approach*.07, r, seed)
                    q_grip = self.kin.solve("right", p, r, q_app)
                    self.kin.line("right", p-approach*.015, r, q_app)
                    self.kin.line("right", pull, r, q_grip)
                except ValueError:
                    continue
                chosen = (r, q_app)
                break
            if chosen:
                break
        if chosen is None:
            raise StageFailure("no IK branch takes and pulls the ring's front point")
        r, q_app = chosen
        # Reach that branch through a raised waypoint; joint interpolation straight to it can sweep the post.
        a0, a1 = self._targets["right"][0], self.kin.arm("right", q_app)
        for lift, dx in ((.10, 0.), (.10, .05), (.15, 0.), (.15, .05), (.20, .05), (.25, .10)):
            try:
                aw = self.kin.arm("right", self.kin.solve("right", p-approach*.07+[dx, 0., lift], r, q_app))
                path = [a0+u*(aw-a0) for u in np.linspace(0, 1, 25)[1:]]+[aw+u*(a1-aw) for u in np.linspace(0, 1, 13)[1:]]
                self.check_clear({"right": path})
            except ValueError:
                continue
            break
        else:
            raise StageFailure("no clear way to the ring's front grip")
        self._targets["right"][1] = .03
        yield from self.follow({"right": path}, speed=.3, settle=6)
        yield from self.line({"right": (p-approach*.015, r)}, speed=.08, settle=4)
        c, n = self.ring_pose()
        yield from self.servo({"right": (c+R_*geo.inplane([0., -1., 0.], n), r)}, iters=8, limit=.006)
        yield from self.gripper("right", .002, steps=30)
        yield from self.gripper("left", .03, steps=10, ramp=False)
        lp, lr = self.tcp("left")
        yield from self.line({"left": (lp-lr.apply([.06, 0., 0.]), lr)}, speed=.1, settle=6)
        tp, tr = self.tcp("right")
        c, _ = self.ring_pose()
        for center_y in np.arange(c[1]-.01, out-.001, -.01):
            yield from self.line({"right": (tp+[0., center_y-c[1], 0.], tr)}, speed=.06, settle=3)
        c, _ = self.ring_pose()
        crossings = self.crossings()
        self.note("ring out in front", center=c.tolist(), crossings=crossings,
                  cord_volume_ratio=geo.cord_volume_ratio(self.world))
        if c[1]+R_+g.ring_tube_radius_m > g.post_front_y or [side for _, _, side in crossings] != ["front", "front"]:
            raise StageFailure(f"ring not out on the front bight: {crossings}")

    def stage_ring_off_bight(self):
        """Turn the ring about the vertical in small steps: the bight hanging over its lower tube slips off
        (bead1 passes through the ring) and the ring is free."""
        tp, tr = self.tcp("right")
        c, _ = self.ring_pose()
        off = tp-c
        for k in range(1, 13):
            turn = R.from_rotvec([0., 0., np.radians(5*k)])
            yield from self.goto({"right": (c+[0., -.002*k, .003*k]+turn.apply(off), turn*tr)}, speed=.15,
                                 waypoints=2, settle=3)
            if not self.crossings():
                break
        crossings = self.crossings()
        self.note("ring off the bight", turn_deg=5*k, crossings=crossings)
        if crossings:
            raise StageFailure(f"ring still on the cord: {crossings}")
        tp, tr = self.tcp("right")
        yield from self.line({"right": (tp+[0., -.03, .06], tr)}, speed=.08, settle=20)

    # ----- tidy and place ------------------------------------------------------
    def disc_extent(self):
        """(lower, upper) corners of disc1's footprint (rim samples)."""
        c, rd, _ = self.disc()
        t = np.linspace(0, 2*np.pi, 64, endpoint=False)
        rim = rd.apply(np.column_stack([np.zeros(64), np.cos(t), np.sin(t)])*self.geo.disc_radius_m)+c
        return rim.min(axis=0), rim.max(axis=0)

    def edge_push(self, side, direction, stop_center, steps=10):
        """Fingertips against disc1's rim, the broad finger face square to `direction`; normal force, not
        friction, moves the disc (the cord's shape memory drags it back from under pressed fingers)."""
        g = self.geo
        d = np.array([direction[0], direction[1], 0.])
        d /= np.linalg.norm(d)
        c = self.disc()[0]
        z = g.table_z_m+.008
        contact0 = np.array([c[0], c[1], z])-d*(g.disc_radius_m+.006)
        contact1 = np.array([stop_center[0], stop_center[1], z])-d*(g.disc_radius_m+.006)+d*.015
        tip = .016
        for tilt in np.radians((0., 25., 40., 55.)):
            approach = np.array([-d[0]*np.sin(tilt), -d[1]*np.sin(tilt), -np.cos(tilt)])
            r = frame(approach, d)
            s0, s1 = contact0-approach*tip, contact1-approach*tip
            if all(self.pose_clear(side, q, r) for q in (s0, s1, (s0+s1)/2)):
                break
        else:
            raise StageFailure("no reachable edge push for disc1")
        self._targets[side][1] = .002
        yield from self.route(side, s0, r, speed=.3, settle=4)
        for f in np.linspace(0, 1, steps+1)[1:]:
            yield from self.line({side: (s0+f*(s1-s0), r)}, speed=.04, settle=2)
        yield from self.hold(10)

    def stage_disc_tidy(self):
        """Left hand pushes disc1 (dragged behind the base by the cord) clear of the base's -x side, then forward
        inside the separator, and leaves its fingers behind the disc as a fence."""
        g = self.geo
        base_lo = np.asarray(g.fixture_boxes_m["base"][0])
        target = np.array([base_lo[0]-g.disc_radius_m-.023, g.separator_offset_m-.02-g.disc_radius_m])
        lo, hi = self.disc_extent()
        if hi[1] < g.separator_offset_m-.015:
            self.note("disc1 already inside the separator", max_y=float(hi[1]))
            return
        for attempt in range(2):
            if self.disc_extent()[1][0] < base_lo[0]-.004:
                break
            yield from self.edge_push("left", (-1., 0.), (target[0]-.01*attempt, self.disc()[0][1]))
            tp, tr = self.tcp("left")
            yield from self.line({"left": (tp+[0., 0., .05], tr)}, speed=.1, settle=2)
        yield from self.edge_push("left", (0., -1.), (self.disc()[0][0], target[1]))
        tp, tr = self.tcp("left")
        for k in range(1, 7):
            if self.disc_extent()[1][1] < g.separator_offset_m-.015:
                break
            yield from self.line({"left": (tp+[0., -.006*k, 0.], tr)}, speed=.03, settle=3)
        lo, hi = self.disc_extent()
        self.note("disc1 tidied", center=self.disc()[0].tolist(), max_y=float(hi[1]),
                  cord_volume_ratio=geo.cord_volume_ratio(self.world))
        if hi[1] > g.separator_offset_m-.002:
            raise StageFailure("disc1 still beyond the separator")

    def stage_ring_to_goal(self):
        """Right hand carries the free ring above the post top to the goal square's centre, rests its rim on the
        table and holds it still (holding is allowed); the left keeps fencing disc1."""
        g = self.geo
        R_ = g.ring_major_radius_m
        tp, tr = self.tcp("right")
        c, _ = self.ring_pose()
        off = tp-c
        rest = g.table_z_m+R_+g.ring_tube_radius_m+.002
        gx, gy = g.goal_center_xy_m
        # A vertical ring fits the goal square at any yaw; search yaw, crossing height and centre for a pose the
        # right arm reaches both above the post top and resting in the goal.
        chosen = None
        for clear in (.05, .03, .015):
            high = g.post_top_z+R_+g.ring_tube_radius_m+clear
            for yaw in np.radians((0., 30., -30., 60., -60., 90., -90., 120., -120., 180.)):
                turn = R.from_rotvec([0., 0., yaw])
                o, r = turn.apply(off), turn*tr
                for dx, dy in ((0., 0.), (.03, -.03), (-.03, -.03), (.03, .03), (-.03, .03)):
                    centre = np.array([gx+dx, gy+dy])
                    if (self.pose_clear("right", np.array([*centre, high])+o, r)
                            and self.pose_clear("right", np.array([*centre, rest])+o, r)
                            and self.pose_clear("right", np.array([c[0], c[1], high])+o, r)):
                        chosen = (high, o, r, centre)
                        break
                if chosen:
                    break
            if chosen:
                break
        if chosen is None:
            raise StageFailure("no reachable way to carry the ring into the goal")
        high, o, r, (gx, gy) = chosen
        self.note("ring transfer", height=float(high), centre=[float(gx), float(gy)])
        yield from self.line({"right": (np.array([c[0], c[1], high])+off, tr)}, speed=.1, settle=4)
        yield from self.goto({"right": (np.array([c[0], c[1], high])+o, r)}, speed=.15, waypoints=10, settle=4)
        yield from self.goto({"right": (np.array([gx, gy, high])+o, r)}, speed=.2, waypoints=20, settle=6)
        for z in np.arange(high-.02, rest, -.02):
            yield from self.line({"right": (np.array([gx, gy, z])+o, r)}, speed=.06, settle=2)
        yield from self.line({"right": (np.array([gx, gy, rest])+o, r)}, speed=.03, settle=10)
        c, _ = self.ring_pose()
        self.note("ring placed", center=c.tolist())
        # Hold still; the episode ends when the task's own success condition has held for its window.
        self.sync_to_measured(["left", "right"])
        yield from self.hold(400)
