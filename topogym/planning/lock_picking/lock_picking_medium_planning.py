"""Measured-pose lock oracle emitting one standard EE_ABS action per act().

Semantic two-retreat route recovered from the 2026-09-18 standard_150mm
commands (cb60f01b32786cc9c26f754f91b7be4bef3f9ca6). No historical module,
simulator handle, attach call, scene.step or object-pose write is used here.
Qualification is reported by each rollout, never inferred from this filename.
"""
import math
import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def rotation(q):
    return Rotation.from_quat(np.asarray(q)[[1, 2, 3, 0]])


def pickup_waypoints(p, r, center, grasp_rotation, style):
    """Robot TCP waypoints; the side route avoids the near-base elbow fold."""
    high = max(p[2], center[2]+.25)
    result = [(np.array([p[0], p[1], high]), r, 1., "clear_home")]
    if style == "side":
        side = np.array([-.30, -.45, high])
        result += [(side, Rotation.from_euler("x", 180., degrees=True), 2., "clear_side_workspace"),
                   (side, grasp_rotation, 1.5, "orient_at_side"),
                   (np.array([center[0], -.45, center[2]+.20]), grasp_rotation, 2., "pass_behind_base")]
    result += [(center+[0, 0, .20], grasp_rotation, 1.5 if style == "side" else 3., "approach_handle"),
               (center+[0, 0, .002], grasp_rotation, 2., "descend_to_handle")]
    return result


class LockPickingMediumPolicy:
    def __init__(self, *, geometry, part="pickup", grasp_roll_deg=0., grasp_style="top"):
        if part not in {"pickup", "solve"}:
            raise ValueError("part must be pickup or solve")
        self.geometry = dict(geometry)
        self.part = part
        self.grasp_roll_deg = float(grasp_roll_deg)
        if grasp_style not in {"top", "side"}:
            raise ValueError("grasp_style must be top or side")
        self.grasp_style = grasp_style
        self.phase = "created"
        self.completed = False

    def initialize(self, context):
        spec = context["action_spec"]
        if spec["robot_id"] != "panda_robotiq" or spec["mode"] != "EE_ABS":
            raise ValueError("Lock oracle requires panda_robotiq / EE_ABS")
        if context["mode"] != "unlimited" or "world" not in context["observation_spec"]["privileged_fields"]:
            raise ValueError("Measured-pose oracle requires authorized world observations")
        if spec["grasp_assist"]["model"] != "contact_weld_v1":
            raise ValueError("This oracle is qualified only with contact_weld_v1")
        self.dt = context["timing_spec"]["control_dt_s"]
        self.grip = 0.
        self.program = None
        self.commanded_tcp = None
        self.precise_insertion = False
        self.phase = "ready"

    def act(self, obs):
        self.obs = obs
        if self.part == "solve":
            self._check_mechanism_contacts()
        if self.program is None:
            self.program = self._actions()
        try:
            return next(self.program)
        except StopIteration:
            self.completed = True
            self.phase = "done"
            return None

    def on_segment_end(self, obs, result):
        self.final_reason = result["reason"]

    def _time(self):
        return float(self.obs["state"]["sim_time_s"])

    def _tcp(self):
        arm = self.obs["robot"]["arm"]
        return np.array(arm["tcp_position_world_m"]), rotation(arm["tcp_orientation_wxyz"])

    def _key(self):
        key = self.obs["privileged"]["world"]["bodies"]["lock_key"]
        return np.array(key["position_m"]), rotation(key["quaternion_wxyz"])

    def _holding(self):
        return self.obs["privileged"]["world"]["grasp"]["hands"]["arm"]["binding"] is not None

    def _disc_angle(self, index):
        joint = self.obs["privileged"]["world"]["articulations"][f"lock_disc_{index}"]["joints"]["disc_hinge"]
        return float(np.degrees(np.asarray(joint["position"]).item()))

    def _entry_angle(self, first_slot):
        centers = [self._disc_angle(0)+self.geometry["slots"][0][first_slot],
                   self._disc_angle(1)+self.geometry["slots"][1][0]]
        half = self.geometry["slot_half_deg"]-self.geometry["tab_half_deg"]-.4
        low, high = max(c-half for c in centers), min(c+half for c in centers)
        if low >= high:
            raise RuntimeError(f"Measured slot windows have no safe overlap: {centers}")
        return (low+high)/2

    def _check_mechanism_contacts(self):
        world = self.obs["privileged"]["world"]
        key = set(world["bodies"]["lock_key"]["link_indices"])
        fixture = {link for name, body in world["bodies"].items()
                   if name.startswith(("lock_disc_", "lock_frame_", "lock_goal"))
                   for link in body["link_indices"]}
        contacts = world["contacts"]
        force_sum = 0.
        for a, b, depth, force in zip(contacts["link_a"], contacts["link_b"], contacts["penetration"], contacts["force"]):
            if (int(a) in key and int(b) in fixture) or (int(b) in key and int(a) in fixture):
                force_sum += np.linalg.norm(force)
                if depth > .002:
                    raise RuntimeError(f"Key/fixture penetration exceeds 2 mm at {self.phase}: {float(depth):.6f} m")
        if force_sum > 10.:
            raise RuntimeError(f"Key/fixture contact force exceeds historical 10 N gate at {self.phase}: {force_sum:.3f} N")

    def _hold(self, seconds, require_grasp=False):
        start = self._time()
        while self._time()-start < seconds-1e-9:
            if require_grasp and not self._holding():
                raise RuntimeError("Automatic grasp lost during " + self.phase)
            yield {}

    def _pose(self, p, r):
        self.commanded_tcp = (np.asarray(p).copy(), r)
        return {"arm": dict(position_world_m=np.asarray(p).tolist(),
            orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(), gripper_position_rad=self.grip)}

    def _move(self, p1, r1, seconds, phase, *, held=False):
        self.phase = phase
        p0, r0 = self._tcp()
        p1 = np.asarray(p1)
        interp = Slerp([0., 1.], Rotation.from_quat([r0.as_quat(), r1.as_quat()]))
        n = max(1, math.ceil(seconds/self.dt))
        for i in range(1, n+1):
            if held and not self._holding():
                raise RuntimeError("Automatic grasp absent during " + phase)
            u = i/n
            u = u*u*(3-2*u)
            yield self._pose(p0+(p1-p0)*u, interp(u))
        yield from self._hold(.15, require_grasp=held)
        p, r = self._tcp()
        if np.linalg.norm(p-p1) > .008 or (r.inv()*r1).magnitude() > .04:
            raise RuntimeError("Robot tracking failed at " + phase)

    def _move_key(self, *, depth=None, angle=None, seconds=3., phase="key", lift=False, z_offset=0.):
        if not self._holding():
            raise RuntimeError("Key motion requires an automatically acquired grasp")
        self.phase = phase
        g = self.geometry
        p0, r0 = self._key()
        # Preserve the preceding action's load compensation across the tight
        # insertion stages. Restarting from measured TCP would drop that offset
        # at every stage boundary, even after the key was precisely aligned.
        tp, tr = (self.commanded_tcp if self.precise_insertion and self.commanded_tcp is not None
                  else self._tcp())
        local_p, local_r = r0.inv().apply(tp-p0), r0.inv()*tr
        p1 = p0.copy()
        if depth is not None:
            p1[0] = g["first_x"] + (depth-1)*g["pitch"]
        p1[1:] = [g["center_y"], g["axis_z"]+z_offset]
        r1 = r0 if angle is None else Rotation.from_euler("x", -angle, degrees=True)
        interp = Slerp([0., 1.], Rotation.from_quat([r0.as_quat(), r1.as_quat()]))
        n = max(1, math.ceil(seconds/self.dt))
        for i in range(1, n+1):
            if not self._holding():
                raise RuntimeError("Automatic grasp lost during " + phase)
            u = i/n
            u = u*u*(3-2*u)
            r, p = interp(u), p0+(p1-p0)*u
            commanded_p, commanded_r = p+r.apply(local_p), r*local_r
            yield self._pose(commanded_p, commanded_r)
        yield from self._hold(.3, require_grasp=True)
        # Robot tracking and a solver weld have finite compliance. Correct the
        # measured key, through more ordinary actions, before entering a bore
        # with only 1 mm shaft clearance. Never move/rotate the key directly.
        position_tolerance = .00015 if self.precise_insertion else .00035
        angle_tolerance = .0003 if self.precise_insertion else .001
        for _ in range(10 if self.precise_insertion else 6):
            actual_p, actual_r = self._key()
            delta_p, delta_r = p1-actual_p, r1*actual_r.inv()
            if np.linalg.norm(delta_p) < position_tolerance and delta_r.magnitude() < angle_tolerance:
                break
            tcp_p, _ = self._tcp()
            correction = delta_p + delta_r.apply(tcp_p-actual_p) - (tcp_p-actual_p)
            if np.linalg.norm(correction) > .004 or delta_r.magnitude() > .03:
                raise RuntimeError("Fine alignment exceeds its bounded correction at " + phase)
            commanded_p += correction
            commanded_r = delta_r*commanded_r
            yield self._pose(commanded_p, commanded_r)
            yield from self._hold(.2, require_grasp=True)
        actual_p, actual_r = self._key()
        error = float(np.linalg.norm(actual_p-p1))
        angular = float((actual_r.inv()*r1).magnitude())
        if error > (position_tolerance*2) or angular > (angle_tolerance*2):
            raise RuntimeError(f"Key target not reached at {phase}: position={error:.6f} m, angle={angular:.6f} rad")

    def _regrasp(self):
        """Release the supported key and approach again using ordinary actions.

        The old elbow joint path was tied to a different fixture placement.
        Current Cartesian clearance waypoints replace that recorded joint path.
        """
        self.phase, self.grip = "open_for_supported_regrasp", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self._hold(3.)
        if self._holding():
            raise RuntimeError("Automatic grasp did not release for regrasp")
        p, r = self._tcp()
        yield from self._move(p+[-.08, 0, 0], r, 1.5, "withdraw_for_regrasp")
        yield from self._move(p+[-.08, 0, .12], r, 2., "clear_supported_key")
        kp, kr = self._key()
        center = kp+kr.apply([-self.geometry["grip_offset"], 0, 0])
        r = kr*Rotation.from_euler("x", self.grasp_roll_deg, degrees=True)*Rotation.from_euler("y", 90., degrees=True)
        yield from self._move(center+[-.08, 0, .12], r, 1.5, "reorient_for_regrasp")
        yield from self._move(center+[-.08, 0, 0], r, 2., "approach_supported_handle")
        # The released shaft may settle/slide on the bores during withdrawal.
        kp, kr = self._key()
        center = kp+kr.apply([-self.geometry["grip_offset"], 0, 0])
        r = kr*Rotation.from_euler("x", self.grasp_roll_deg, degrees=True)*Rotation.from_euler("y", 90., degrees=True)
        yield from self._move(center, r, 2., "center_supported_handle")
        self.phase, self.grip = "close_for_automatic_regrasp", .8
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self._hold(3.)
        if not self._holding():
            raise RuntimeError("No automatic bilateral regrasp on the supported key")
        self.precise_insertion = True
        yield from self._move_key(angle=0., seconds=3., phase="align_after_regrasp")
        yield from self._move_key(depth=3., angle=0., seconds=3., phase="reinsert_third_disc")

    def _actions(self):
        if self.part == "pickup":
            self.phase = "open_and_settle"
            yield {"arm": {"gripper_position_rad": 0.}}
            yield from self._hold(.5)
            kp, kr = self._key()
            center = kp + kr.apply([-self.geometry["grip_offset"], 0, 0])
            grasp_rotation = (Rotation.from_euler("xyz", [180., 0., self.grasp_roll_deg], degrees=True)
                if self.grasp_style == "top" else
                kr * Rotation.from_euler("x", self.grasp_roll_deg, degrees=True)
                * Rotation.from_euler("y", 90., degrees=True))
            p, r = self._tcp()
            for target, orientation, duration, phase in pickup_waypoints(p, r, center, grasp_rotation, self.grasp_style):
                yield from self._move(target, orientation, duration, phase)
            self.phase, self.grip = "close_and_wait_for_automatic_assist", .8
            yield {"arm": {"gripper_position_rad": self.grip}}
            yield from self._hold(3.)
            if not self._holding():
                raise RuntimeError("No automatic bilateral grasp after closing")
            yield from self._move_key(angle=0., seconds=2., phase="lift_to_lock_axis", lift=True)
            yield from self._hold(.5, require_grasp=True)
            return
        self.grip = .8
        expected = [[-60., -30., 0.], [-60.], [0.]]
        if [list(row) for row in self.geometry["slots"]] != expected:
            raise ValueError("Recovered two-retreat route does not match this setting's slots")
        # Object-space route; each stage uses the current measured key-to-TCP
        # transform. All rotations/retreats are produced by ordinary robot actions.
        route = [
            (None, -60., 2.75, "align_entry"),
            (1., -60., 6.5, "insert_first_disc"),
            (2., -60., 5.5, "insert_second_disc"),
            (None, -42.5, 3.5, "first_index"),
            (1., -42.5, 6.5, "first_retreat"),
            (None, -77.5, 4.5, "reset_first_disc"),
            (1.15, -77.5, 1.6, "clear_first_disc"),
            (None, -45.25, 3.75, "select_middle_slot"),
            (2., -45.25, 5.5, "reengage_two_discs"),
            (None, -12.5, 4.25, "second_index"),
            (None, -16.8, 1.2, "center_coupled_slots"),
            (1., -16.8, 6.5, "second_retreat"),
            (None, -47.5, 4.25, "reset_first_disc_again"),
            (1.15, -47.5, 1.6, "clear_for_final_slot"),
            (None, -15.6, 3.75, "select_final_slot"),
            (2., -15.6, 5.5, "reengage_final_branch"),
            (None, 4.5, 4.5, "align_all_discs"),
            (None, 0., 1.3, "center_final_slots"),
            (3., 0., 6.5, "insert_third_disc"),
            (3.8, 0., 6.5, "approach_endpoint"),
            (4.08, 0., 4.5, "insert_endpoint"),
        ]
        selected_angle = None
        for depth, angle, seconds, phase in route:
            if phase in {"first_retreat", "second_retreat"}:
                # Between depth 1.15 and 2 all tabs can leave the discs. The
                # first rotor may drift as its preceding tab leaves. Re-read
                # it before returning the leading tab into the first plate.
                yield from self._move_key(depth=1.15, angle=angle, seconds=seconds,
                                          phase=phase+"_clear_second")
                first_slot = 0 if phase == "first_retreat" else 1
                center = self._disc_angle(0)+self.geometry["slots"][0][first_slot]
                yield from self._move_key(angle=center, seconds=1., phase=phase+"_align_first")
                yield from self._move_key(depth=1., angle=center, seconds=1., phase=phase+"_enter_first")
                continue
            if phase in {"select_middle_slot", "select_final_slot"}:
                selected_angle = self._entry_angle(1 if phase == "select_middle_slot" else 2)
                angle = selected_angle
            elif phase in {"reengage_two_discs", "reengage_final_branch"}:
                angle = selected_angle
            yield from self._move_key(depth=depth, angle=angle, seconds=seconds, phase=phase)
            if phase in {"first_index", "reset_first_disc", "second_index", "reset_first_disc_again", "align_all_discs"}:
                yield from self._hold(.75, require_grasp=True)
            if phase == "insert_third_disc":
                yield from self._hold(1., require_grasp=True)
                yield from self._regrasp()
        self.phase = "hold_final_insertion"
        yield from self._hold(.6, require_grasp=True)
        self.phase, self.grip = "release_at_goal", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self._hold(2.)
        if self._holding():
            raise RuntimeError("Automatic grasp failed to release")
        p, r = self._tcp()
        yield from self._move(p+[0, 0, .13], r, 1.5, "withdraw_gripper")
        self.phase = "verify_stable_insertion"
        start, stable_since = self._time(), None
        while self._time()-start < 15.:
            key = self.obs["privileged"]["world"]["bodies"]["lock_key"]
            quiet = (not self._holding() and np.linalg.norm(key["linear_velocity_m_s"]) < .01
                     and np.linalg.norm(key["angular_velocity_rad_s"]) < .1)
            stable_since = (self._time() if stable_since is None else stable_since) if quiet else None
            if stable_since is not None and self._time()-stable_since >= .5:
                return
            yield {}
        raise RuntimeError("Released key did not remain at rest for 0.5 s within 15 s")
