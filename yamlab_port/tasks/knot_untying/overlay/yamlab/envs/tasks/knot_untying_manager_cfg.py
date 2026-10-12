"""Configuration for the KnotUntying tasks (port of RoboTangle knot_untying).

The rope is one PhysX articulation: a capsule chain (r 4 mm, ~10 mm links) with spherical joints
whose implicit PD drives pull towards the straight rest shape. Its USD and its settled start state
are generated per tier by ``scripts/build_assets.py`` into ``knot_untying_lib/assets/<tier>/``.
"""

import os

import torch

import isaaclab.sim as sim_utils
import isaaclab.envs.mdp as mdp
from isaaclab.actuators import ImplicitActuatorCfg
from isaaclab.assets import ArticulationCfg
from isaaclab.managers import EventTermCfg, RewardTermCfg, SceneEntityCfg, TerminationTermCfg
from isaaclab.utils import configclass

from yamlab.envs.yam_bimanual_scene import YamBimanualSceneCfg
from yamlab.robot.yam import ROBOT

from .yam_bimanual_env_cfg import YamBimanualEnvCfg, BaseEventsCfg
from .knot_untying_lib import rope_params as RP

ASSET_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knot_untying_lib", "assets")
TIERS = {"KnotUntying-VeryEasy-v0": "very_easy", "KnotUntying-Easier-v0": "easier",
         "KnotUntying-Easy-v0": "easy", "KnotUntying-Medium-v0": "medium"}


def rope_usd_path(tier: str) -> str:
    return os.path.join(ASSET_ROOT, tier, "rope.usda")


def rope_cfg(tier: str) -> ArticulationCfg:
    d = None
    meta = os.path.join(ASSET_ROOT, tier, "rope_meta.json")
    if os.path.exists(meta):
        import json
        d = json.load(open(meta))["link_length_m"]
    d = d or RP.LINK_LENGTH_NOMINAL
    P = RP.ROPE
    return ArticulationCfg(
        prim_path="{ENV_REGEX_NS}/rope",
        # per-asset physics re-applied from rope_params on spawn (same values as authored in the USD)
        spawn=sim_utils.UsdFileCfg(
            usd_path=rope_usd_path(tier),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                linear_damping=P["linear_damping"], angular_damping=P["angular_damping"],
                max_depenetration_velocity=P["max_depenetration_velocity"]),
            articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                enabled_self_collisions=True,
                solver_position_iteration_count=P["solver_position_iterations"],
                solver_velocity_iteration_count=P["solver_velocity_iterations"])),
        # Root pose / joint coordinates are overwritten from start_state.npz by the manager.
        init_state=ArticulationCfg.InitialStateCfg(pos=(0.0, 0.0, 0.0)),
        actuators={
            "rope_bend": ImplicitActuatorCfg(joint_names_expr=[r"j_\d+:1", r"j_\d+:2"],
                                             stiffness=RP.bend_stiffness(d), damping=P["joint_damping"],
                                             armature=P["armature"]),
            "rope_twist": ImplicitActuatorCfg(joint_names_expr=[r"j_\d+:0"],
                                              stiffness=RP.twist_stiffness(d), damping=P["joint_damping"],
                                              armature=P["armature"]),
        },
    )


def reset_rope_joint_targets(env, env_ids, asset_cfg: SceneEntityCfg):
    """reset_scene_to_default sets joint targets = default (knotted) joint pos; the rope's drives
    must keep pulling towards the straight rest shape (target 0)."""
    rope = env.scene[asset_cfg.name]
    z = torch.zeros(len(env_ids), rope.num_joints, device=rope.device)
    rope.set_joint_position_target(z, env_ids=env_ids)
    rope.set_joint_velocity_target(z, env_ids=env_ids)


def knot_goal_success(env):
    """Latched goal (old evaluate_state held for 0.5 s); evaluated here so it runs every step."""
    return env.update_goal()


def rope_fell_off_table(env, margin: float = 0.05):
    pos = env.scene["rope"].data.body_link_pos_w[..., 2] - env.scene.env_origins[:, 2:3]
    return (pos < ROBOT.table_position[2] - margin).any(dim=1)


def _scene_cfg(tier: str):
    @configclass
    class _Scene(YamBimanualSceneCfg):
        rope = rope_cfg(tier)
    _Scene.__name__ = f"KnotUntying{tier.title().replace('_', '')}SceneCfg"
    return _Scene


@configclass
class KnotUntyingEventsCfg(BaseEventsCfg):
    reset_rope_targets = EventTermCfg(func=reset_rope_joint_targets, mode="reset",
                                      params={"asset_cfg": SceneEntityCfg("rope")})


def knot_success_reward(env):
    return env.goal_latched.float()


@configclass
class KnotUntyingRewardsCfg:
    success = RewardTermCfg(func=knot_success_reward, params={}, weight=1.0)


@configclass
class KnotUntyingTerminationsCfg:
    time_out = TerminationTermCfg(func=mdp.time_out, time_out=True)
    task_success = TerminationTermCfg(func=knot_goal_success, params={})
    rope_off_table = TerminationTermCfg(func=rope_fell_off_table, params={"margin": 0.05})


def _env_cfg(tier: str):
    Scene = _scene_cfg(tier)

    @configclass
    class _Cfg(YamBimanualEnvCfg):
        scene: Scene = Scene(num_envs=1, env_spacing=3.0)
        events: KnotUntyingEventsCfg = KnotUntyingEventsCfg()
        rewards: KnotUntyingRewardsCfg = KnotUntyingRewardsCfg()
        terminations: KnotUntyingTerminationsCfg = KnotUntyingTerminationsCfg()
        obj_name_to_event_name: dict = {}

        def __post_init__(self):
            super().__post_init__()
            # Finger contact sensors (YamRobot requires them) need one filter body per object
            # (PhysX tensor filters must match exactly one body per env), so they filter the
            # rope's first link only: is_grasping()/the grasp clamp are NOT meaningful for the rope.
            self._contact_body_links = {"rope": "link_000"}
            # No HDF5 action/state recorder (oracle/replay log their own npz; parallel runs would
            # otherwise contend for the recorder's file lock).
            self.recorders = None

    _Cfg.__name__ = f"KnotUntying{tier.title().replace('_', '')}ManagerEnvCfg"
    _Cfg.TIER = tier
    _Cfg.CONTACT_OBJECT_NAMES = []
    return _Cfg


KnotUntyingVeryEasyManagerEnvCfg = _env_cfg("very_easy")
KnotUntyingEasierManagerEnvCfg = _env_cfg("easier")
KnotUntyingEasyManagerEnvCfg = _env_cfg("easy")
KnotUntyingMediumManagerEnvCfg = _env_cfg("medium")
