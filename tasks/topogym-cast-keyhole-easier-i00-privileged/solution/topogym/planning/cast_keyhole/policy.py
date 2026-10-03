"""Pick up the current tabletop puzzle, follow its route, and place the silver.

Only observations enter this module and native actions leave it. The manager
owns scene creation, IK, physical stepping, contact-gated assist and success.
Reference poses use canonical planar plate coordinates, not the current URDF
COM frames. No archived robot qpos or engine state is replayed.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

PARTS = {"left": "keyhole_gold", "right": "keyhole_silver"}
FAMILIES = {"easy": "F1", "medium": "F2", "hard": "F3"}
ASSEMBLY_ROTATIONS = {
    "left": Rotation.from_euler("z", 90, degrees=True) * Rotation.from_euler("x", 90, degrees=True),
    "right": Rotation.from_euler("x", 90, degrees=True),
}
# The higher gold prong is reachable above the current tabletop. The old lower
# prong is only 9 mm above the table and is not a valid pickup for these fingers.
GRASP_POINTS = {"left": np.array([.0318, -.093, 0.]), "right": np.array([-.024, .081, 0.])}
REGRASP_POINTS = {"left": np.array([-.0318, -.093, 0.]), "right": np.array([0., .0891, 0.])}
REGRASP_ROTATIONS = {
    "left": Rotation.from_matrix([[0, 0, 1], [1, 0, 0], [0, 1, 0]]),
    "right": (Rotation.from_matrix([[0, 0, -1], [-1, 0, 0], [0, 1, 0]])
              * Rotation.from_euler("x", 180, degrees=True)),
}
PAD_TO_TCP = np.array([-.01381, 0., .00055])


def rotation(q):
    return Rotation.from_quat(np.asarray(q)[[1, 2, 3, 0]])


def placement_targets(bodies, grasp_offsets, vertices, region, *, variation):
    """Object-space goals shared by native preflight and passive execution."""
    targets, current = [], dict(bodies)
    normal = np.asarray(region["separator_normal_xy"])
    gold_p, gold_r = current["left"]
    gold_points = gold_r.apply(vertices["left"])+gold_p
    excess = max(0., float(np.max(gold_points[:, :2]@normal))-region["separator_offset_m"]+.015)
    delta = np.r_[-excess*normal, 0.]
    if variation.removeprefix("cast_keyhole_") == "easy":
        # In F1's checked final arm posture the left camera occupies the
        # silver transfer sweep. Move the entire held gold/tool outward first.
        delta += [-.08, 0., 0.]
    if np.linalg.norm(delta) > 1e-12:
        current = dict(current, left=(gold_p+delta, gold_r))
        targets.append(("gold_to_system_side", 3., current))
    goal_tool = Rotation.from_matrix([[0., 0., -1.], [0., -1., 0.], [-1., 0., 0.]])
    target_r = goal_tool*grasp_offsets["right"][1].inv()
    points = target_r.apply(vertices["right"])
    midpoint = (points.min(0)+points.max(0))/2
    center = np.r_[region["center_xy_m"], region["table_height_m"]+.5*region["placement_height_m"]]
    targets.append(("silver_to_goal", 4., dict(current, right=(center-midpoint, target_r))))
    return targets


def load_reference(variation):
    level = variation.removeprefix("cast_keyhole_")
    if level not in FAMILIES:
        raise ValueError(f"Unsupported Cast Keyhole variation: {variation}")
    family = FAMILIES[level]
    data = json.loads((Path(__file__).parent / "references" / f"{family}.json").read_text())
    from topogym.assets.library import resource_path
    geometry = resource_path(f"variations/cast_keyhole/{family}/geometry.json")
    if hashlib.sha256(geometry.read_bytes()).hexdigest() != data["geometry_sha256"]:
        raise ValueError("Reference geometry differs from the current frozen variant")
    return data


def canonical_offsets(body_origins, gold_offset_m=-.141):
    """The URDF COM in each original planar plate coordinate system."""
    return {s: ASSEMBLY_ROTATIONS[s].inv().apply(np.asarray(body_origins[name]) -
            (np.array([0., 0., gold_offset_m]) if s == "left" else 0.))
            for s, name in PARTS.items()}


class CastKeyholePolicy:
    def __init__(self, *, variation, body_origins, goal_region, mount_position,
                 canonical_vertices, part="pickup", speed=1., route_clearance_m=.0004, plan=None,
                 regrasp_rotation=None, regrasp_approach=None, regrasp_transit=None,
                 park_target=None, supported_raise_m=.20, reference=None, gold_offset_m=-.141):
        self.reference = load_reference(variation) if reference is None else reference
        self.origins = canonical_offsets(body_origins, gold_offset_m=gold_offset_m)
        self.region = dict(goal_region)
        self.mount = np.asarray(mount_position, dtype=float)
        self.vertices = {s: np.asarray(v, dtype=float) for s, v in canonical_vertices.items()}
        self.part, self.speed = part, float(speed)
        if part not in {"pickup", "solve", "release_left", "release_right", "grasp_left", "grasp_right",
                        "park_left", "raise_supported"}:
            raise ValueError("Unsupported policy segment")
        self.plan = plan
        self.regrasp_rotation = regrasp_rotation
        self.regrasp_transit = regrasp_transit
        self.park_target = park_target
        self.supported_raise = float(supported_raise_m)
        self.regrasp_approach = ([(.05, .035), (.04, 0.), (0., 0.)] if regrasp_approach is None
                                else regrasp_approach)
        self.route_clearance = float(route_clearance_m)
        self.phase = "created"
        self.diagnostics = {}

    def initialize(self, context):
        spec = context["action_spec"]
        if spec["robot_id"] != "aloha" or spec["mode"] != "EE_ABS":
            raise ValueError("Cast Keyhole requires ALOHA EE_ABS")
        self.dt = context["timing_spec"]["control_dt_s"]
        self.grip = {s: .027 if self.part == "pickup" else .002 for s in PARTS}
        if self.part.startswith("grasp_"):
            self.grip[self.part.split("_")[1]] = .027
        if self.part in {"park_left", "raise_supported"}:
            self.grip["left"] = .027
        self.program = None
        self.bias = {s: np.zeros(3) for s in PARTS}
        self.angle_bias = {s: np.zeros(3) for s in PARTS}

    def act(self, obs):
        self.obs = obs
        if self.program is None:
            self.program = self.actions()
        return next(self.program, None)

    def time(self):
        return self.obs["state"]["sim_time_s"]

    def bodies(self):
        world = self.obs["privileged"]["world"]
        out = {}
        for s, name in PARTS.items():
            b = world["bodies"][name]
            r = rotation(b["quaternion_wxyz"]) * ASSEMBLY_ROTATIONS[s]
            out[s] = (np.asarray(b["position_m"]) - r.apply(self.origins[s]), r)
        return out

    def tcp(self):
        return {s: (np.asarray(v["tcp_position_world_m"]), rotation(v["tcp_orientation_wxyz"]))
                for s, v in self.obs["robot"].items()}

    def command(self, targets):
        return {s: dict(position_world_m=p.tolist(), orientation_wxyz=r.as_quat()[[3, 0, 1, 2]].tolist(),
                        gripper_position_m=self.grip[s]) for s, (p, r) in targets.items()}

    def hold(self, seconds):
        start = self.time()
        while self.time() - start < seconds - 1e-8:
            yield {}

    def move(self, targets, seconds, phase, *, position_bias_limit_m=.012,
             angle_bias_limit_rad=.06, settle_timeout_s=4.):
        self.phase = phase
        self.diagnostics = {}
        initial = self.tcp()
        turns = {s: Slerp([0, 1], Rotation.from_quat([initial[s][1].as_quat(), r.as_quat()]))
                 for s, (_, r) in targets.items()}
        start = self.time()
        while True:
            t = min(1., (self.time() - start + self.dt) / seconds)
            u = float(np.clip(t*t*t*(10. + t*(-15. + 6.*t)), 0., 1.))
            yield self.command({s: (initial[s][0]+u*(p-initial[s][0]), turns[s](u))
                                for s, (p, _) in targets.items()})
            if t >= 1. - 1e-8:
                break
        yield from self.hold(.35)
        started = self.time()
        bias = {s: np.zeros(3) for s in targets}
        angle_bias = {s: np.zeros(3) for s in targets}
        while True:
            actual = self.tcp()
            errors = {s: (float(np.linalg.norm(p-actual[s][0])),
                          float((r*actual[s][1].inv()).magnitude())) for s, (p, r) in targets.items()}
            if all(p < .0006 and a < .008 for p, a in errors.values()):
                break
            if self.time()-started > settle_timeout_s:
                raise RuntimeError(f"Pregrasp tracking failed in {phase}: {errors}")
            corrected = {}
            for s, (p, r) in targets.items():
                bias[s] = np.clip(bias[s]+2.*self.dt*(p-actual[s][0]),
                                  -position_bias_limit_m, position_bias_limit_m)
                angle_bias[s] = np.clip(angle_bias[s]+2.*self.dt*(r*actual[s][1].inv()).as_rotvec(),
                                        -angle_bias_limit_rad, angle_bias_limit_rad)
                corrected[s] = (p+bias[s], Rotation.from_rotvec(angle_bias[s])*r)
            self.diagnostics = dict(pregrasp_errors=errors)
            yield self.command(corrected)

    def grasp_targets(self, bodies):
        result = {}
        down = np.array([0., 0., -1.])
        for s, (p, r) in bodies.items():
            # Pinch across the elevated gold prong / silver rim from above.
            # Closing along the plate normal from its side leaves the camera
            # shell below the tabletop at the settled initial configuration.
            radial = (GRASP_POINTS[s]-np.array([0., .063, 0.]) if s == "right"
                      else np.array([1., 0., 0.]))
            jaw = r.apply(radial)
            jaw[2] = 0.
            jaw /= np.linalg.norm(jaw)
            turn = Rotation.from_matrix(np.column_stack([down, jaw, np.cross(down, jaw)]))
            result[s] = (p+r.apply(GRASP_POINTS[s])+turn.apply(PAD_TO_TCP), turn)
        return result

    def attached_targets(self, targets):
        actual = self.bodies()
        commands, errors = {}, {}
        for s, (p, r) in targets.items():
            e = p-actual[s][0]
            a = (r*actual[s][1].inv()).as_rotvec()
            gain = getattr(self, "integral_gain", 1.5)
            proportional = getattr(self, "proportional_gain", .25)
            derivative = getattr(self, "derivative_gain", 0.)
            velocity, angular_velocity = np.zeros(3), np.zeros(3)
            if derivative:
                observed = self.obs["privileged"]["world"]["bodies"][PARTS[s]]
                angular_velocity = np.asarray(observed["angular_velocity_rad_s"])
                velocity = (np.asarray(observed["linear_velocity_m_s"])
                    - np.cross(angular_velocity, actual[s][1].apply(self.origins[s])))
            self.bias[s] = np.clip(self.bias[s] + gain*self.dt*e, -.035, .035)
            self.angle_bias[s] = np.clip(self.angle_bias[s] + gain*self.dt*a, -.18, .18)
            cr = Rotation.from_rotvec(self.angle_bias[s]+proportional*a-derivative*angular_velocity)*r
            commands[s] = (p+self.bias[s]+proportional*e-derivative*velocity+cr.apply(self.grasp_offsets[s][0]),
                           cr*self.grasp_offsets[s][1])
            errors[s] = dict(position_m=float(np.linalg.norm(e)), rotation_rad=float(np.linalg.norm(a)))
        self.diagnostics = dict(self.diagnostics, body_errors=errors,
                                integral_position_m={s: b.tolist() for s, b in self.bias.items()})
        def relative(poses):
            lp, lr = poses["left"]
            rp, rr = poses["right"]
            return lr.inv().apply(rp-lp), lr.inv()*rr
        ap, ar = relative(actual)
        tp, tr = relative(targets)
        self.diagnostics["relative_displacement_bound_m"] = float(
            np.linalg.norm(tp-ap)+.15*(tr*ar.inv()).magnitude())
        return self.command(commands)

    def follow_bodies(self, pose_at, seconds, phase, *, precise=False, tracking_tolerance_m=.0015):
        self.phase = phase
        self.integral_gain = 3. if precise else 1.5
        self.proportional_gain = 2.5 if precise else .25
        self.derivative_gain = .06 if precise else 0.
        progress, start = 0., self.time()
        while True:
            target = pose_at(progress)
            action = self.attached_targets(target)
            errors = self.diagnostics["body_errors"]
            position_tol, angle_tol = ((.003, .02) if precise else (tracking_tolerance_m, .015))
            arrived = all(e["position_m"] < position_tol and e["rotation_rad"] < angle_tol for e in errors.values())
            if precise:
                arrived &= self.diagnostics["relative_displacement_bound_m"] < self.route_clearance
            if arrived:
                if progress >= 1.-1e-8:
                    break
                advance = min(1.-progress, self.dt/seconds)
                if precise:
                    # A nominal speed change must not jump across the narrow
                    # channel while the previous target is still being tracked.
                    # Bound the next relative target step independently of the
                    # 0.4 mm feedback gate and the requested playback speed.
                    def relative(poses):
                        lp, lr = poses["left"]
                        rp, rr = poses["right"]
                        return lr.inv().apply(rp-lp), lr.inv()*rr
                    p0, r0 = relative(target)
                    budget = max(.00002, .00048-self.diagnostics["relative_displacement_bound_m"])
                    for _ in range(8):
                        pp, rr = relative(pose_at(progress+advance))
                        step = float(np.linalg.norm(pp-p0)+.15*(rr*r0.inv()).magnitude())
                        if step <= budget:
                            break
                        advance *= .99*budget/step
                    else:
                        raise RuntimeError("Unable to bound the next relative target step")
                    self.diagnostics["commanded_relative_step_bound_m"] = step
                progress += advance
            if self.time()-start > max(seconds*8., seconds+20.):
                raise RuntimeError(f"Tracking stalled in {phase} at {progress:.4f}: {errors}")
            self.diagnostics.update(progress=progress)
            yield action

    def rigid_transfer(self, final_gold, seconds, phase):
        initial = self.bodies()
        pg, rg = initial["left"]
        endp, endr = final_gold
        turn = Slerp([0, 1], Rotation.from_quat([rg.as_quat(), endr.as_quat()]))
        relative = {s: (rg.inv().apply(p-pg), rg.inv()*r) for s, (p, r) in initial.items()}
        def pose(u):
            v = float(np.clip(u*u*u*(10.+u*(-15.+6.*u)), 0., 1.))
            p, r = pg+v*(endp-pg), turn(v)
            return {s: (p+r.apply(dp), r*dr) for s, (dp, dr) in relative.items()}
        # Whole-assembly lifting need not reproduce the contact equilibrium
        # at acquisition to sub-millimetre accuracy. Use the measured final
        # grasp configuration for all subsequent planning.
        yield from self.follow_bodies(pose, seconds, phase, tracking_tolerance_m=.003)

    def reference_pose(self, index):
        frames = self.reference["frames"]
        index = np.clip(index, 0., len(frames)-1.)
        i = min(int(index), len(frames)-2)
        u = index-i
        result = {}
        for s, name in PARTS.items():
            a, b = frames[i]["bodies"][name], frames[i+1]["bodies"][name]
            r = Slerp([0, 1], Rotation.from_quat([a["quat"], b["quat"]]))(u)
            result[s] = (self.mount+(1.-u)*np.asarray(a["pos"])+u*np.asarray(b["pos"]), r)
        return result

    def actions(self):
        if self.part == "park_left":
            if self.park_target is None:
                raise ValueError("Parking requires an explicitly planned TCP pose")
            yield from self.move({"left": (np.asarray(self.park_target["tcp_position_world_m"]),
                rotation(self.park_target["tcp_orientation_wxyz"]))}, 4., "park_left")
            return
        if self.part == "raise_supported":
            p, r = self.tcp()["right"]
            yield from self.move({"right": (p+[0., 0., self.supported_raise], r)}, 5., "raise_supported",
                position_bias_limit_m=.04, angle_bias_limit_rad=.18, settle_timeout_s=8.)
            yield from self.settle_free_piece("left")
            return
        if self.part.startswith("release_"):
            yield from self.release_for_regrasp(self.part.split("_")[1])
            return
        if self.part.startswith("grasp_"):
            yield from self.regrasp(self.part.split("_")[1])
            return
        if self.part == "solve":
            bodies, tcp = self.bodies(), self.tcp()
            self.grasp_offsets = {s: (r.inv().apply(tcp[s][0]-p), r.inv()*tcp[s][1])
                                  for s, (p, r) in bodies.items()}
            yield from self.follow_plan()
            yield from self.place_target()
            return
        self.phase = "open_at_home"
        yield {s: dict(gripper_position_m=self.grip[s]) for s in PARTS}
        yield from self.hold(.35)
        # Cross the wrist's straight configuration before introducing lateral
        # motion. Simultaneous yaw/translation otherwise selects forearm +/-pi
        # and leaves no margin for load compensation during the later lift.
        down = np.array([0., 0., -1.])
        at_home = {}
        for s, (p, _) in self.tcp().items():
            jaw = np.array([0., 1. if s == "left" else -1., 0.])
            at_home[s] = (p, Rotation.from_matrix(np.column_stack([down, jaw, np.cross(down, jaw)])))
        yield from self.move(at_home, 2., "orient_at_home")
        grasp = self.grasp_targets(self.bodies())
        outside = {s: (p-r.apply([.020, 0., 0.]), r) for s, (p, r) in grasp.items()}
        above = {s: (p+np.array([0., 0., .10]), r) for s, (p, r) in outside.items()}
        yield from self.move(above, 3., "home_to_pregrasp")
        yield from self.move(outside, 2., "descend_outside")
        grasp = self.grasp_targets(self.bodies())
        yield from self.move(grasp, 2., "side_approach")
        self.phase = "close_and_acquire"
        self.grip = {s: .002 for s in PARTS}
        yield {s: dict(gripper_position_m=self.grip[s]) for s in PARTS}
        yield from self.hold(.8)
        hands = self.obs["privileged"]["world"]["grasp"]["hands"]
        if any(hands[s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("No bilateral contact-gated grasp: "+str(hands))
        bodies, tcp = self.bodies(), self.tcp()
        self.grasp_offsets = {s: (r.inv().apply(tcp[s][0]-p), r.inv()*tcp[s][1])
                              for s, (p, r) in bodies.items()}
        pg, rg = bodies["left"]
        # A released peer swings down under gravity. Lift far enough for its
        # real hanging pose and the side-approach wrist/camera, not just for the
        # two-hand pose before release.
        yield from self.rigid_transfer((pg+[0., 0., .30], rg), 6., "lift_assembly")
        return

    def side_grasp_target(self, side):
        p, r = self.bodies()[side]
        local = (Rotation.from_quat(self.regrasp_rotation) if self.regrasp_rotation is not None
                 else REGRASP_ROTATIONS[side])
        turn = r*local
        return p+r.apply(REGRASP_POINTS[side])+turn.apply(PAD_TO_TCP), turn

    def release_for_regrasp(self, side):
        """The peer supports the interlocked assembly during a real handoff."""
        self.phase = "release_for_regrasp_"+side
        self.grip[side] = .027
        yield {side: dict(gripper_position_m=self.grip[side])}
        yield from self.hold(.25)
        p, r = self.tcp()[side]
        yield from self.move({side: (p-r.apply([.035, 0., 0.]), r)}, 2., "regrasp_retreat_"+side)
        yield from self.settle_free_piece(side)

    def settle_free_piece(self, side):
        self.phase = "settle_for_regrasp_"+side
        start, quiet = self.time(), 0.
        while quiet < .5:
            b = self.obs["privileged"]["world"]["bodies"][PARTS[side]]
            stable = (np.linalg.norm(b["linear_velocity_m_s"]) < .002
                      and np.linalg.norm(b["angular_velocity_rad_s"]) < .03)
            quiet = quiet+self.dt if stable else 0.
            if self.time()-start > 8.:
                raise RuntimeError("Released piece did not settle for read-only IK planning")
            yield {}

    def regrasp(self, side):
        if self.regrasp_rotation is None:
            raise ValueError("Regrasp requires an explicitly checked local rotation")
        for index, ((backoff, lift), seconds, phase) in enumerate(zip(self.regrasp_approach, (3., 2., 2.),
                ("regrasp_above_", "regrasp_outside_", "regrasp_approach_"), strict=True)):
            if index == 0 and self.regrasp_transit:
                yield from self.follow_tcp_transit(side, self.regrasp_transit)
                continue
            p, r = self.side_grasp_target(side)
            target = p-r.apply([backoff, 0., 0.])+[0., 0., lift]
            yield from self.move({side: (target, r)}, seconds, phase+side)
        self.phase = "regrasp_acquire_"+side
        self.grip[side] = .002
        yield {side: dict(gripper_position_m=self.grip[side])}
        yield from self.hold(.8)
        hands = self.obs["privileged"]["world"]["grasp"]["hands"]
        if any(hands[s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("Regrasp did not retain two contact-gated bindings: "+str(hands))

    def follow_tcp_transit(self, side, rows):
        """Follow dense FK poses as EE actions; never write the planned qpos."""
        self.phase = "regrasp_joint_transit_"+side
        poses = [(np.asarray(row["position_m"]), rotation(row["quaternion_wxyz"])) for row in rows]
        turns = [Slerp([0, 1], Rotation.from_quat([a[1].as_quat(), b[1].as_quat()]))
                 for a, b in zip(poses, poses[1:])]
        start = self.time()
        while True:
            t = min(1., (self.time()-start+self.dt)/5.)
            u = float(np.clip(t*t*t*(10.+t*(-15.+6.*t)), 0., 1.))*(len(poses)-1)
            index = min(int(u), len(poses)-2)
            fraction = u-index
            a, b = poses[index:index+2]
            yield self.command({side: (a[0]+fraction*(b[0]-a[0]), turns[index](fraction))})
            if t >= 1.-1e-8:
                break
        yield from self.move({side: poses[-1]}, .25, "settle_regrasp_transit_"+side)

    def follow_plan(self):
        if not self.plan:
            raise ValueError("Solve segment requires an explicit coupled IK candidate")
        rows = self.plan["frames"]
        def decode(row):
            return {s: (np.asarray(v["position_m"]), rotation(v["quaternion_wxyz"]))
                    for s, v in row["bodies"].items()}
        for index, (first, second) in enumerate(zip(rows, rows[1:]), 1):
            self.diagnostics.update(route_frame=index, reference_index=second.get("reference_index"))
            a, b = decode(first), decode(second)
            turns = {s: Slerp([0, 1], Rotation.from_quat([a[s][1].as_quat(), b[s][1].as_quat()])) for s in PARTS}
            yield from self.follow_bodies(lambda u: {s: (a[s][0]+u*(b[s][0]-a[s][0]), turns[s](u)) for s in PARTS},
                max(self.dt, second["duration_s"]/self.speed), second["stage"],
                # The settled start has real surface contact. Its first
                # separating displacement is only micrometres; forcing the
                # later free-space tolerance here deadlocks progress against
                # the physical contact equilibrium. Keep normal tracking and
                # all Task penetration guards during entry, then enforce the
                # narrow-channel relative tolerance on the actual puzzle path.
                precise=second["stage"] not in {"align_route_entry", "restore_after_regrasp", "lift_after_regrasp"},
                tracking_tolerance_m=.003 if second["stage"] == "lift_after_regrasp" else .0015)

    def place_target(self):
        initial = self.bodies()
        for stage, duration, target in placement_targets(initial, self.grasp_offsets, self.vertices,
                self.region, variation=self.reference["variation_id"]):
            turns = {s: Slerp([0, 1], Rotation.from_quat([initial[s][1].as_quat(), target[s][1].as_quat()]))
                     for s in PARTS}
            yield from self.follow_bodies(lambda u: {s: (initial[s][0]+u*(target[s][0]-initial[s][0]),
                                                        turns[s](u)) for s in PARTS}, duration, stage)
            initial = self.bodies()
        self.phase = "goal_hold"
        target = self.bodies()
        yield from self.follow_bodies(lambda u: target, 1., "goal_hold", precise=True)
        yield from self.hold(2.)
        self.phase = "complete"
