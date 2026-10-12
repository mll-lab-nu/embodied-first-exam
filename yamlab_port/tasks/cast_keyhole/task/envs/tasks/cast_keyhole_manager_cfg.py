"""Configuration for the CastKeyhole tasks (port of RoboTangle cast_keyhole).

Two free rigid plates (keyhole_gold, keyhole_silver), each one rigid body with an exact compound
convex collider (one convex prism per slab of the old generator), start interlocked on the table.
Per-tier start poses and the goal square come from ``cast_keyhole_assets/<tier>/layout.json``.

Camera sensors can be stripped for physics-only hosts with the environment variable
``YAMLAB_NO_CAMERAS=1`` (Isaac's RTX renderer crashes on vast).
"""

import json
import os

import isaaclab.envs.mdp as mdp
import isaaclab.sim as sim_utils
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
from isaaclab.managers import RewardTermCfg, TerminationTermCfg
from isaaclab.utils import configclass

from yamlab.envs.yam_bimanual_scene import YamBimanualSceneCfg
from yamlab.robot.yam import ROBOT
from yamlab.utils.task_logic import compute_sparse_success_reward

from .yam_bimanual_env_cfg import YamBimanualEnvCfg, BaseEventsCfg

ASSET_ROOT = os.environ.get(
    "CAST_KEYHOLE_ASSETS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "cast_keyhole_assets"))
TIERS = {"VeryEasy": "very_easy", "Easier": "easier", "Easy": "easy"}
PLATES = ("keyhole_gold", "keyhole_silver")


def task_id(tier_key: str) -> str:
    return f"CastKeyhole-{tier_key}-v0"


def asset_paths(tier: str) -> dict:
    """assets_instance_paths for create_task_environment."""
    return {name: os.path.join(ASSET_ROOT, tier, name) for name in PLATES}


def load_layout(tier: str) -> dict:
    with open(os.path.join(ASSET_ROOT, tier, "layout.json")) as f:
        return json.load(f)


def _plate_cfg(name: str, pose: dict) -> RigidObjectCfg:
    return RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/" + name,
        spawn=sim_utils.UsdFileCfg(
            usd_path="",  # set by configure_assets_instance_paths
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=False,
                max_depenetration_velocity=0.5,
                solver_position_iteration_count=32,
                solver_velocity_iteration_count=1,
            ),
            mass_props=sim_utils.MassPropertiesCfg(mass=pose["mass_kg"]),
            # Small offsets: the tightest channel clearance of the route is 1.1 mm.
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=0.002, rest_offset=0.0),
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=tuple(pose["pos"]), rot=tuple(pose["quat_wxyz"])),
    )


def _goal_marker_cfgs(goal: dict) -> dict:
    """Visual-only outline of the goal square (no collision), 4 mm wide tape on the tabletop."""
    (x0, y0), (x1, y1) = goal["xy_min"], goal["xy_max"]
    z = goal["table_z"] + 0.0003
    w = 0.004
    mat = sim_utils.PreviewSurfaceCfg(diffuse_color=(0.1, 0.75, 0.2))
    strips = {
        "goal_edge_xmin": ((x0, (y0 + y1) / 2, z), (w, y1 - y0, 0.0006)),
        "goal_edge_xmax": ((x1, (y0 + y1) / 2, z), (w, y1 - y0, 0.0006)),
        "goal_edge_ymin": (((x0 + x1) / 2, y0, z), (x1 - x0, w, 0.0006)),
        "goal_edge_ymax": (((x0 + x1) / 2, y1, z), (x1 - x0, w, 0.0006)),
    }
    return {name: AssetBaseCfg(prim_path="{ENV_REGEX_NS}/" + name,
                               spawn=sim_utils.CuboidCfg(size=size, visual_material=mat),
                               init_state=AssetBaseCfg.InitialStateCfg(pos=pos))
            for name, (pos, size) in strips.items()}


def check_task_success(env):
    return env.ck_success


def check_task_failure(env):
    return env.ck_failure


@configclass
class CastKeyholeRewardsCfg:
    sparse_success_reward = RewardTermCfg(func=compute_sparse_success_reward, params={}, weight=1.0)


@configclass
class CastKeyholeTerminationsCfg:
    time_out = TerminationTermCfg(func=mdp.time_out, time_out=True)
    task_success = TerminationTermCfg(func=check_task_success, params={})
    task_failure = TerminationTermCfg(func=check_task_failure, params={})


def make_cfg_class(tier: str):
    """Build the env cfg class of one tier (start poses and goal markers are per tier)."""
    layout = load_layout(tier)
    parts, goal = layout["parts"], layout["goal_region"]
    markers = _goal_marker_cfgs(goal)

    @configclass
    class CastKeyholeSceneCfg(YamBimanualSceneCfg):
        keyhole_gold = _plate_cfg("keyhole_gold", parts["keyhole_gold"])
        keyhole_silver = _plate_cfg("keyhole_silver", parts["keyhole_silver"])
        goal_edge_xmin = markers["goal_edge_xmin"]
        goal_edge_xmax = markers["goal_edge_xmax"]
        goal_edge_ymin = markers["goal_edge_ymin"]
        goal_edge_ymax = markers["goal_edge_ymax"]

        def __post_init__(self):
            super().__post_init__()
            if os.environ.get("YAMLAB_NO_CAMERAS", "0") == "1":
                for name in ROBOT.camera_names:
                    setattr(self, f"{name}_camera", None)

    @configclass
    class CastKeyholeManagerEnvCfg(YamBimanualEnvCfg):
        scene: CastKeyholeSceneCfg = CastKeyholeSceneCfg(num_envs=1, env_spacing=3.0)
        events: BaseEventsCfg = BaseEventsCfg()
        rewards: CastKeyholeRewardsCfg = CastKeyholeRewardsCfg()
        terminations: CastKeyholeTerminationsCfg = CastKeyholeTerminationsCfg()
        obj_name_to_event_name: dict = {}

        def configure_assets_instance_paths(self, assets_instance_paths):
            # The base method re-seats objects at table + height/2; keep the authored start poses.
            super().configure_assets_instance_paths(assets_instance_paths)
            for name in PLATES:
                getattr(self.scene, name).init_state.pos = tuple(parts[name]["pos"])
                getattr(self.scene, name).init_state.rot = tuple(parts[name]["quat_wxyz"])

    CastKeyholeManagerEnvCfg._ck_tier = tier
    CastKeyholeManagerEnvCfg.CONTACT_OBJECT_NAMES = list(PLATES)
    return CastKeyholeManagerEnvCfg
