"""Candidate reference controller for the two simplified Keyhole scenes.

Object-route collision checks are separate from robot qualification. This
policy uses observations and native actions only, with contact-gated grasping.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from .policy import CastKeyholePolicy, PARTS, PAD_TO_TCP


def route_displacements(variation, *, scale=3.):
    """Channel translations AFTER transverse alignment, in the gold plate frame.

    The v4 initial pose matches F1/F2/F3. These points exclude pickup, lift
    and the transition into transverse alignment.
    """
    level = variation.removeprefix("cast_keyhole_")
    if level == "very_easy":
        points = [(-3.65, 5.), (-3.65, -45.)]
    elif level == "easier":
        points = [(-3.65, 5.), (-3.65, -3.), (3.5, -3.), (3.5, -20.),
                  (-3.65, -20.), (-3.65, -45.)]
    else:
        raise ValueError(f"Unsupported simplified variation: {variation}")
    points = np.asarray(points, dtype=float)
    return np.c_[(points-points[0])*float(scale)/1000., np.zeros(len(points))]


def channel_guides(variation, *, scale=3.):
    """Lower silver bar centre in gold planar coordinates, in metres.

    The first three edges enter the slot from the circular bore. They are
    shared by both variants; route_displacements describes the lower channel.
    """
    entry = np.asarray([(0., 21.35, 0.), (-2.875, 12., 0.),
                        (-2.875, 6.5, 0.), (-3.65, 5., 0.)])*scale/1000.
    return np.vstack((entry, entry[-1]+route_displacements(variation, scale=scale)[1:]))


class SimplifiedKeyholePolicy(CastKeyholePolicy):
    """Reuse feedback/placement primitives, with new grasps and no old regrasp route."""

    def __init__(self, *, geometry, variation, part="all", pickup_transit=None, **kwargs):
        if part not in {"pickup", "all"}:
            raise ValueError("Simplified policy supports pickup or all")
        if geometry.get("initial_relative_pose_id") != "perpendicular_lower_bore_v1":
            raise NotImplementedError(
                "This candidate requires the restored v4 initial pose; older layouts need their own route.")
        self.geometry = geometry
        self.pickup_transit = pickup_transit
        self.grasp_points = {side: np.asarray(geometry["grasp_regions"][name]["center_plate_mm"])
                            * geometry["scale"]/1000.
                            for side, name in (("left", "gold"), ("right", "silver"))}
        super().__init__(variation=variation, reference=dict(variation_id=variation),
                         gold_offset_m=geometry["gold_offset_z_mm"]*geometry["scale"]/1000.,
                         route_clearance_m=.002, part="pickup", **kwargs)
        from topogym.assets.geometry.cast_keyhole import plate_assembly_transforms
        transforms = plate_assembly_transforms(geometry)
        self.assembly_rotations = {s: Rotation.from_matrix(transforms[n][:3, :3])
                                  for s, n in (("left", "gold"), ("right", "silver"))}
        self.origins = {s: self.assembly_rotations[s].inv().apply(
            np.asarray(kwargs["body_origins"][PARTS[s]])-transforms[n][:3, 3])
            for s, n in (("left", "gold"), ("right", "silver"))}
        self.part = part

    def bodies(self):
        world = self.obs["privileged"]["world"]
        result = {}
        for side, name in PARTS.items():
            body = world["bodies"][name]
            turn = Rotation.from_quat(np.asarray(body["quaternion_wxyz"])[[1, 2, 3, 0]])
            turn *= self.assembly_rotations[side]
            result[side] = (np.asarray(body["position_m"])-turn.apply(self.origins[side]), turn)
        return result

    def initialize(self, context):
        super().initialize(context)
        self.grip = {s: .024 for s in PARTS}
        self.grasp_offsets = None

    def act(self, obs):
        if getattr(self, "grasp_offsets", None):
            hands = obs["privileged"]["world"]["grasp"]["hands"]
            for side, name in PARTS.items():
                hand = hands[side]
                if hand["phase"] != "holding" or hand["binding"]["target"][0] != name:
                    raise RuntimeError(f"Lost {side} grasp during {self.phase}: {hand}")
        return super().act(obs)

    def grasp_targets(self, bodies):
        targets = {}
        for side, (p, r) in bodies.items():
            # Approach from the two outside ends. A 35-degree downward slope
            # clears the tabletop while the fingers contact opposite faces.
            angle = np.deg2rad(35.)
            local_along = np.array([0., 1. if side == "left" else -1., 0.])
            if side == "left":
                # Keep the finger bodies outside the silver plate's exit sweep.
                local_along = Rotation.from_euler("z", 30., degrees=True).apply(local_along)
            along = r.apply(local_along)
            normal = r.apply([0., 0., 1.])
            approach = along*np.cos(angle)+normal*np.sin(angle)
            jaw = -along*np.sin(angle)+normal*np.cos(angle)
            turn = Rotation.from_matrix(np.column_stack((approach, jaw, np.cross(approach, jaw))))
            targets[side] = (p+r.apply(self.grasp_points[side])+turn.apply(PAD_TO_TCP), turn)
        return targets

    def actions(self):
        self.phase = "open_at_home"
        yield {s: dict(gripper_position_m=self.grip[s]) for s in PARTS}
        yield from self.hold(.75)
        yield from self.approach_transit()
        # The pieces settle while the arms approach. Refresh the final grasp
        # against the current observation, not the authored first frame.
        yield from self.move(self.grasp_targets(self.bodies()), 3., "approach_outer_faces")
        self.phase = "close_on_faces"
        self.grip = {s: .002 for s in PARTS}
        yield {s: dict(gripper_position_m=self.grip[s]) for s in PARTS}
        yield from self.hold(.8)
        hands = self.obs["privileged"]["world"]["grasp"]["hands"]
        if any(hands[s]["phase"] != "holding" for s in PARTS):
            raise RuntimeError("New geometry did not acquire both contact-gated grasps")
        bodies, tcp = self.bodies(), self.tcp()
        self.grasp_offsets = {s: (r.inv().apply(tcp[s][0]-p), r.inv()*tcp[s][1])
                              for s, (p, r) in bodies.items()}
        pg, rg = bodies["left"]
        yield from self.rigid_transfer((pg+[0., 0., .10], rg), 3., "lift_clear_of_table")
        if self.part == "pickup":
            self.phase = "pickup_complete"
            return
        # Both outer grasps leave room around the bore. Move the whole assembly
        # into a workspace where the right wrist can complete its turn.
        pg, rg = self.bodies()["left"]
        yield from self.rigid_transfer(
            (pg+[0., .20, 0.], Rotation.from_euler("z", 30., degrees=True)*rg),
            6./self.speed, "position_for_channel")
        yield from self.align_to_channel()
        yield from self.extract_from_channel()
        yield from self.place_target()

    def bar_point(self):
        return np.array([0., -25.65, 0.])*self.geometry["scale"]/1000.

    def transverse_rotation(self):
        nominal = self.assembly_rotations["left"].inv()*self.assembly_rotations["right"]
        # Take the cap toward gold -x, after the common workspace adjustment.
        return Rotation.from_euler("z", 90, degrees=True)*nominal

    def align_to_channel(self):
        bodies = self.bodies()
        pg, rg = bodies["left"]
        ps, rs = bodies["right"]
        r0 = rg.inv()*rs
        nominal = self.assembly_rotations["left"].inv()*self.assembly_rotations["right"]
        halfway = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), nominal.as_quat()]))(.5)
        intermediate = Rotation.from_euler("z", 45, degrees=True)*halfway
        goal = channel_guides(self.reference["variation_id"], scale=self.geometry["scale"])[0]
        bar = self.bar_point()
        self.route_clearance = .001
        for name, target in (("stand_and_turn_silver", intermediate),
                             ("turn_silver_to_channel", self.transverse_rotation())):
            ps, rs = self.bodies()["right"]
            c0, r0 = rg.inv().apply(ps+rs.apply(bar)-pg), rg.inv()*rs
            turns = Slerp([0, 1], Rotation.from_quat([r0.as_quat(), target.as_quat()]))
            def poses(u):
                r = rg*turns(u)
                return dict(left=(pg, rg), right=(pg+rg.apply(c0+u*(goal-c0))-r.apply(bar), r))
            yield from self.follow_bodies(poses, 6./self.speed, name,
                precise=name == "turn_silver_to_channel", tracking_tolerance_m=.0015)
            yield from self.follow_bodies(lambda u: poses(1.), 1., name+"_hold", precise=True)

    def extract_from_channel(self):
        bodies = self.bodies()
        pg, rg = bodies["left"]
        ps, rs = bodies["right"]
        bar = self.bar_point()
        last = rg.inv().apply(ps+rs.apply(bar)-pg)
        target_r = rg*self.transverse_rotation()
        # The inlet's sampled minimum clearance is 1.125 mm. Gate relative
        # tracking more tightly than that, including rotation at a 15 cm radius.
        self.route_clearance = .0005
        for index, goal in enumerate(channel_guides(self.reference["variation_id"],
                                                    scale=self.geometry["scale"])):
            a = last.copy()
            def poses(u, a=a, goal=goal):
                return dict(left=(pg, rg), right=(pg+rg.apply(a+u*(goal-a))-target_r.apply(bar), target_r))
            yield from self.follow_bodies(poses, max(1., np.linalg.norm(goal-a)/(.012*self.speed)),
                                         f"channel_segment_{index}", precise=True)
            last = goal
        self.phase = "channel_complete"

    def placement_targets(self, bodies):
        """Nominal separated-piece poses, also used by owner-side mesh checks."""
        pg, rg = bodies["left"]
        ps, rs = bodies["right"]
        normal = np.asarray(self.region["separator_normal_xy"])
        gold_points = rg.apply(self.vertices["left"])+pg
        excess = max(0., float(np.max(gold_points[:, :2]@normal))
                     -self.region["separator_offset_m"]+.015)
        # Lift gold before crossing the right arm's workspace. Moving it to the
        # right at the extraction height sweeps the plate into that forearm.
        clearance_move = np.array([0., 0., .12])
        park = pg-np.r_[excess*normal, 0.]+clearance_move
        silver_points = rs.apply(self.vertices["right"])
        center = np.r_[self.region["center_xy_m"],
                       self.region["table_height_m"]+.5*self.region["placement_height_m"]]
        goal = center-(silver_points.min(0)+silver_points.max(0))/2
        return (
            ("gold_raise_clear", 6., dict(left=(pg+clearance_move, rg), right=(ps, rs))),
            ("gold_to_system_side", 8., dict(left=(park, rg), right=(ps, rs))),
            ("silver_to_goal_yz", 6., dict(left=(park, rg), right=(np.r_[ps[0], goal[1:]], rs))),
            ("silver_to_goal_x", 6., dict(left=(park, rg), right=(goal, rs))),
        )
    def place_target(self):
        """Keep the face grasps while moving the separated pieces to their sides."""
        initial = self.bodies()
        for name, duration, target in self.placement_targets(initial):
            yield from self.follow_bodies(lambda u: {
                s: (initial[s][0]+u*(target[s][0]-initial[s][0]), target[s][1]) for s in PARTS},
                duration/self.speed, name)
            initial = self.bodies()
        target = self.bodies()
        self.route_clearance = .001
        yield from self.follow_bodies(lambda u: target, 1., "goal_hold", precise=True)
        yield from self.hold(2.)
        self.phase = "complete"

    def approach_transit(self):
        """Execute owner-planned native-FK waypoints using ordinary EE actions."""
        path = self.pickup_transit
        if not path or len(path) < 2:
            raise ValueError("A checked home-to-pregrasp TCP path is required")
        times = np.linspace(0., 1., len(path))
        points = {s: np.asarray([frame[s]["position_m"] for frame in path]) for s in PARTS}
        turns = {s: Slerp(times, Rotation.from_quat(np.asarray(
            [frame[s]["quaternion_wxyz"] for frame in path])[:, [1, 2, 3, 0]])) for s in PARTS}
        for side, (position, turn) in self.tcp().items():
            if (np.linalg.norm(position-points[side][0]) > .001
                    or (turn*turns[side](0.).inv()).magnitude() > .01):
                raise ValueError("Pickup transit does not start at the observed robot pose")
        self.phase, start = "continuous_pregrasp", self.time()
        while self.time()-start < 6.-1e-8:
            u = min(1., (self.time()-start+self.dt)/6.)
            yield self.command({s: (np.array([np.interp(u, times, points[s][:, j]) for j in range(3)]),
                                    turns[s](u)) for s in PARTS})
        yield from self.move({s: (points[s][-1], turns[s](1.)) for s in PARTS}, .5, "settle_pregrasp")
