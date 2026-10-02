"""Candidate reference controller for the two simplified Keyhole scenes.

Object-route collision checks are separate from robot qualification. This
policy uses observations and native actions only, with contact-gated grasping.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation

from .policy import CastKeyholePolicy, PARTS, PAD_TO_TCP


def route_displacements(variation, *, scale=3.):
    """Channel translations AFTER transverse alignment, in the gold plate frame.

    The v4 initial pose matches F1/F2/F3; reaching this route's transverse
    alignment requires a new transition and is not verified by these points.
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


class SimplifiedKeyholePolicy(CastKeyholePolicy):
    """Reuse feedback/placement primitives, with new grasps and no old regrasp route."""

    def __init__(self, *, geometry, variation, part="all", **kwargs):
        if part not in {"pickup", "all"}:
            raise ValueError("Simplified policy supports pickup or all")
        if part == "all" and geometry.get("initial_relative_pose_id") == "perpendicular_lower_bore_v1":
            raise NotImplementedError(
                "The v3 transverse extraction policy does not support the restored v4 initial pose. "
                "A collision-checked alignment transition is still required; part='pickup' is "
                "an unqualified candidate only.")
        self.geometry = geometry
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
        self.grip = {s: .027 for s in PARTS}

    def grasp_targets(self, bodies):
        targets = {}
        down = np.array([0., 0., -1.])
        for side, (p, r) in bodies.items():
            jaw = r.apply([0., 0., 1.])
            jaw[2] = 0.
            if np.linalg.norm(jaw) < .1:
                raise ValueError("No valid top-down grasp for this plate pose")
            jaw /= np.linalg.norm(jaw)
            # Approach the gold cap from its closed end, keeping the left
            # wrist/forearm away from the higher silver hand.
            approach = down.copy()
            if side == "left":
                along = r.apply([0., 1., 0.]); along[2] = 0.; along /= np.linalg.norm(along)
                approach = np.cos(np.pi/6)*down-np.sin(np.pi/6)*along
            turn = Rotation.from_matrix(np.column_stack((approach, jaw, np.cross(approach, jaw))))
            targets[side] = (p+r.apply(self.grasp_points[side])+turn.apply(PAD_TO_TCP), turn)
        return targets

    def actions(self):
        self.phase = "open_at_home"
        yield {s: dict(gripper_position_m=self.grip[s]) for s in PARTS}
        yield from self.hold(.35)
        for stage, seconds, targets in self.pickup_waypoints():
            yield from self.move(targets, seconds, stage)
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
        yield from self.rigid_transfer((pg+[0., 0., .10], rg), 4., "lift_clear_of_table")
        if self.part == "pickup":
            return
        entry = self.bodies()
        gold_rotation = entry["left"][1]
        route = route_displacements(self.reference["variation_id"], scale=self.geometry["scale"])
        for index, (a, b) in enumerate(zip(route, route[1:]), 1):
            def poses(u, a=a, b=b):
                return dict(entry, right=(entry["right"][0]+gold_rotation.apply(a+u*(b-a)),
                                          entry["right"][1]))
            yield from self.follow_bodies(poses, max(1., np.linalg.norm(b-a)/(.015*self.speed)),
                                         f"channel_segment_{index}", precise=False,
                                         tracking_tolerance_m=.001)
        yield from self.place_target()

    def pickup_waypoints(self):
        """The owner preflight and passive controller use identical TCP stages."""
        grasp, home = self.grasp_targets(self.bodies()), self.tcp()
        down = np.array([0., 0., -1.])
        vertical = {}
        for side, (p, _) in home.items():
            jaw = np.array([0., 1. if side == "left" else -1., 0.])
            vertical[side] = (p, Rotation.from_matrix(np.column_stack((down, jaw, np.cross(down, jaw)))))
        return (
            ("orient_at_home", 2., vertical),
            ("align_jaw_at_home", 2., {s: (p, grasp[s][1]) for s, (p, _) in home.items()}),
            ("home_to_pregrasp", 4., {s: (p-r.apply([.06, 0., 0.]), r) for s, (p, r) in grasp.items()}),
            ("descend_to_grasp", 3., grasp))
