"""Instance-fixed placement goals shared by the six separation tasks."""
from dataclasses import asdict, replace
import hashlib
import json
import numpy as np

from topogym.evaluation.task_metrics import body_points
from topogym.utils.geometry.regions import GoalRegion


def choose_region(clouds, targets, remainder, table_bounds, table_height, *, excluded_bounds=(), separation_margin=.03,
                  side=None):
    """Deterministic tabletop candidates; robot IK is a separate qualification.

    ``side=(axis, sign)`` keeps only that candidate, so moving the puzzle cannot
    flip the region to the other side of the table.

    The separator covers every remaining component's authored geometry. The
    target rigid bounding sphere fits the zone; soft material can be coiled.
    No runtime body pose can move this region after declaration.
    """
    lower, upper = np.asarray(table_bounds, float)
    obstacle = np.vstack([clouds[n] for n in remainder])
    rigid_size = [np.linalg.norm(np.ptp(clouds[n], axis=0)) for n in targets if n != "cord"]
    half = max(.10, max(rigid_size, default=.15)/2 + .015)
    if "cord" in targets:
        half = max(half, .20)
    height = max(.15, max(rigid_size, default=.15)+.02)
    candidates = []
    for axis in (0, 1):
        for sign in (-1, 1):
            if side is not None and (axis, sign) != tuple(side):
                continue
            normal = np.zeros(2); normal[axis] = sign
            edge = float(np.max(obstacle[:, :2] @ normal)) + .005
            # The other coordinate can move to fit the finite tabletop.
            center = np.mean([lower, upper], axis=0)
            center[axis] = sign*(edge+separation_margin+half)
            if np.any(center-half < lower+.02) or np.any(center+half > upper-.02):
                continue
            # A pregrasp assembly can sit over the robot mounting footprint.
            # Move the candidate outward past that footprint instead of rejecting
            # the whole side when its first (nearest) candidate overlaps it.
            for lo, hi in excluded_bounds:
                if np.all(center+half+.02 > lo) and np.all(center-half-.02 < hi):
                    boundary = hi[axis] if sign > 0 else lo[axis]
                    center[axis] = boundary+sign*(half+.021)
            if np.any(center-half < lower+.02) or np.any(center+half > upper-.02):
                continue
            if any(np.all(center+half+.02 > lo) and np.all(center-half-.02 < hi)
                   for lo, hi in excluded_bounds):
                continue
            region = GoalRegion(tuple(center), (half, half), table_height, height,
                                tuple(normal), edge, separation_margin_m=separation_margin)
            if all(region.system_side(clouds[n]) for n in remainder):
                # Prefer the central, near side of the actual tabletop.
                score = float(np.linalg.norm(center-np.mean([lower, upper], axis=0)))
                candidates.append((score, region))
    if not candidates:
        raise ValueError("No separated tabletop goal region fits this instance")
    return min(candidates, key=lambda item: item[0])[1]


class PlacementGoalMixin:
    terminal_revision = "placement_region_v2_default_success"
    # Inherit default success enablement; qualification is metadata only.
    # (axis, sign) of the side the nominal scene uses; None lets choose_region pick.
    goal_side = None

    def finalize_spec(self, spec, *, asset_dir, scene_config):
        from topogym.assets.geometry.goal_region import write_goal_region
        if hasattr(self, "goal_region"):
            raise ValueError("The placement region is already fixed for this task instance")
        clouds = {}
        for entity in spec.entities:
            if entity.name not in (*self.placement_targets, *self.placement_remainder):
                continue
            if entity.volume_path is not None:
                with np.load(entity.volume_path) as volume:
                    points = volume["spawn"]
            else:
                points = self.placement_vertices[entity.name]
            clouds[entity.name] = body_points(dict(position_m=entity.position_m,
                quaternion_wxyz=entity.quaternion_wxyz), points)
        table = scene_config.env.world.table
        center, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
        mount = scene_config.env.robot_mount
        mount_xy = np.asarray(mount.pos[:2])
        if mount.get("footprint_min") is not None:
            excluded = [(mount_xy+np.asarray(mount.footprint_min), mount_xy+np.asarray(mount.footprint_max))]
        else:
            size = np.asarray(mount.footprint_size[:2])/2
            excluded = [(mount_xy-size, mount_xy+size)]
        self.goal_region = choose_region(clouds, self.placement_targets, self.placement_remainder,
                                         (center-half, center+half), self.table_height_m,
                                         excluded_bounds=excluded,
                                         separation_margin=max(.03, self.config.get("minimum_separation_m", .03)),
                                         side=self.goal_side)
        self.goal_region_identity = hashlib.sha256(json.dumps(asdict(self.goal_region),
            sort_keys=True).encode()).hexdigest()
        self.instance_id = hashlib.sha256((self.instance_id+self.goal_region_identity).encode()).hexdigest()
        return replace(spec, entities=(*spec.entities, write_goal_region(asset_dir, self.goal_region)),
                       metadata={**spec.metadata, "instance_id": self.instance_id,
                                 "terminal": self.terminal_metadata()})

    def terminal_metadata(self):
        metadata = super().terminal_metadata()
        metadata.update(target_entities=self.placement_targets, remainder_entities=self.placement_remainder,
                        thresholds_calibrated=False, reachability_qualified=False,
                        placement_limits=dict(linear_speed_m_s=.001, angular_speed_rad_s=.02),
                        holding_allowed=True)
        if hasattr(self, "goal_region"):
            metadata.update(goal_region=asdict(self.goal_region), goal_region_identity=self.goal_region_identity)
        return metadata

    def public_instruction(self):
        return super().public_instruction()

    def observe(self):
        return dict(instruction=self.public_instruction())

    def evaluate_placement(self, state):
        if hasattr(self, "rigid_measurements"):
            # Preserve the old rigid tasks' physical failure guards. Their
            # all-body quiet/release measurements do not define this new goal.
            _, _, _, failure = self.rigid_measurements(state)
            if failure:
                return False, failure, dict(evaluation_status="available")
        if not hasattr(self, "goal_region"):
            if self.physics_model == "fem_ipc":
                from topogym.evaluation.task_metrics import ipc_integrity
                intact = ipc_integrity(state, ("cord",), self.placement_attachment_names)
                if intact is False:
                    return False, "connection_or_volume_invalid", dict(evaluation_status="available")
            return False, None, dict(evaluation_status="unavailable", missing="fixed goal region")
        reached, failure, metrics = self.evaluate_goal_region(state, self.goal_region)
        return reached, failure, dict(metrics, terminal_revision=self.terminal_revision,
                                      thresholds_calibrated=False)
