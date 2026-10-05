"""Read local task rules for the detached oracle; never edit the environment.

The MuJoCo rope is only a planning model. These conservative bounds and placement
checks do not replace Genesis FEM/IPC integrity, grasp admission or task success.
"""
from dataclasses import dataclass
from itertools import product

import numpy as np
from scipy.spatial.transform import Rotation

from topogym.utils.grasp import TASK_CONTACT_PENETRATION_M, GraspAssistConfig, SoftGraspTarget


MAX_PENETRATION_M = TASK_CONTACT_PENETRATION_M
MAX_GRIP_ERROR_M = GraspAssistConfig().max_translation_error_m
MAX_SEGMENT_STRETCH = SoftGraspTarget(entity="cord").max_strain_ratio
# An additional search guard from the source oracle, not a new environment rule.
MAX_TOTAL_STRETCH = 1.10
# Conservative kinematic planning bounds matching the current Harbor v15
# standard interface (harbor_templates/topogym/common/rcb_topogym.py).
# The native service remains authoritative for actual action admission.
MAX_IK_STEP_RAD = .5
STANDARD_JOINT_SPEED_RAD_S = .04 / .025


def task_for(variant):
    from topogym.config.registry import task_definition
    from topogym.tasks.release_profile import environment_inputs

    parameters, _, _ = environment_inputs("orbits", variant, variation=variant)
    return task_definition("orbits", variant)(parameters, seed=0)


@dataclass
class PlanningGoal:
    region: object
    rotation: Rotation
    origin: np.ndarray
    handle_vertices: np.ndarray
    box: dict

    def world(self, points):
        return self.rotation.apply(points) + self.origin

    def contains(self, oracle):
        # Cover the cord's thickness and the entire authored handle, rather than
        # accepting only the centreline and the handle's centre as in the source.
        offsets = np.array(list(product((-1., 1.), repeat=3))) * oracle.lay.cord_radius_m
        cord = (oracle.points()[:, None, :] + offsets).reshape(-1, 3)
        p, q = oracle.handle_pose()
        handle = Rotation.from_quat(q[[1, 2, 3, 0]]).apply(self.handle_vertices) + p
        return dict(cord=self.region.contains(self.world(cord)),
                    handle=self.region.contains(self.world(handle)))


def planning_goal(variant, layout, initial):
    """Use local choose_region, including tabletop bounds and the robot footprint."""
    from topogym.assets.geometry.orbits import make_meshes
    from topogym.config.scene import load_scene_config
    from topogym.simulator.config import SimulatorConfig
    from topogym.tasks.placement import choose_region

    task = task_for(variant)
    scene = load_scene_config(SimulatorConfig(task_id="orbits", variation_id=variant,
                                             enable_rgb=False, compute_backend="cpu"))
    if task.config["placement_anchor"] != "base_center" or not np.isclose(task.config["yaw_deg"], 90.):
        raise ValueError("The imported oracle requires the local base-centred, 90-degree Orbits scene")
    mount = scene.env.robot_mount
    if not np.isclose(task.config["base_center_xy_m"][0], mount.pos[0]):
        raise ValueError("The imported ALOHA frame requires the base and robot to share world x")
    meshes, _ = make_meshes(layout, initial_cord=initial)
    rotation = Rotation.from_euler("z", task.config["yaw_deg"], degrees=True)
    table = scene.env.world.table
    table_height = float(table.pos[2] + table.size[2]/2)
    base = rotation.apply(meshes["base"].vertices)
    origin = np.r_[np.asarray(task.config["base_center_xy_m"]) - (base.min(0)+base.max(0))[:2]/2,
                   table_height]
    clouds = {name: rotation.apply(mesh.vertices) + origin for name, mesh in meshes.items()}
    center, half = np.asarray(table.pos[:2]), np.asarray(table.size[:2])/2
    mount_xy = np.asarray(mount.pos[:2])
    if mount.get("footprint_min") is not None:
        excluded = [(mount_xy+np.asarray(mount.footprint_min), mount_xy+np.asarray(mount.footprint_max))]
    else:
        size = np.asarray(mount.footprint_size[:2])/2
        excluded = [(mount_xy-size, mount_xy+size)]
    region = choose_region(clouds, ("cord", "handle"), tuple(n for n in meshes if n not in {"cord", "handle"}),
                           (center-half, center+half), table_height, excluded_bounds=excluded,
                           separation_margin=max(.03, task.config.get("minimum_separation_m", .03)),
                           side=task.goal_side)
    corners = np.array(list(product((-1., 1.), repeat=2))) * np.asarray(region.half_size_m)
    world_xy = corners @ region.rotation.T + np.asarray(region.center_xy_m)
    local = rotation.inv().apply(np.column_stack([world_xy, np.full(4, table_height)]) - origin)
    lo, hi = local.min(0), local.max(0)
    margin = region.boundary_margin_m
    box = dict(xmin=float(lo[0]+margin), xmax=float(hi[0]-margin),
               ymin=float(lo[1]+margin), ymax=float(hi[1]-margin),
               ycenter=float((lo[1]+hi[1])/2), zmax=region.placement_height_m)
    handle_center = np.array([layout.handle_x_m, 0., layout.clearance_m+layout.handle_height_m/2])
    return PlanningGoal(region, rotation, origin, np.asarray(meshes["handle"].vertices)-handle_center, box)
