"""Configuration for the FiberBundling tasks (port of the old RoboTangle fiber_bundling family).

Scene = YAM bimanual workstation + static fixtures (copper ring as 64 exact capsules, U cradle,
ring mount) + the branched cable as one fixed-base articulation (root = terminal box with the
first lead segment, passive slack lead, 6-link working trunk, fine strands; free ball joints
with the old viscous damping; gravity disabled on the cable as in the old model, which used
gravity compensation 1.0). A contact sensor on every strand link, filtered to the gripper
bodies (link_6 + both fingers) of both arms, latches the "gripper touched a strand" failure.

Assets per tier live in ``fiber_bundling_assets/<tier>/`` (override the root with the
environment variable YAMLAB_FIBER_ASSETS). Set YAMLAB_STRIP_CAMERAS=1 to build the scene
without camera sensors (physics-only hosts where the RTX renderer is unavailable).
"""

import os

import isaaclab.sim as sim_utils
import isaaclab.envs.mdp as mdp
from isaaclab.assets import ArticulationCfg, AssetBaseCfg
from isaaclab.managers import RewardTermCfg, TerminationTermCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.utils import configclass

from yamlab.envs.yam_bimanual_scene import YamBimanualSceneCfg
from yamlab.utils.task_logic import compute_sparse_success_reward

from .yam_bimanual_env_cfg import YamBimanualEnvCfg, BaseEventsCfg

FIBER_ASSET_ROOT = os.environ.get(
    "YAMLAB_FIBER_ASSETS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fiber_bundling_assets"))

TIERS = {"FiberBundling-VeryEasy-v0": "very_easy", "FiberBundling-Easier-v0": "easier", "FiberBundling-Easy-v0": "easy"}

GRASP_DETECT_LINK = "trunk_04"
# Solver iterations of the cable articulation (task-level asset property; YAMLab's scene minimum is 16/1).
CABLE_SOLVER_ITERS = tuple(int(v) for v in os.environ.get("YAMLAB_FIBER_SOLVER_ITERS", "16,1").split(","))

# Gripper bodies of both arms whose contact with any strand fails the task.
GRIPPER_BODY_PATHS = [f"{{ENV_REGEX_NS}}/{arm}/arm/{link}"
                      for arm in ("LeftArm", "RightArm") for link in ("link_6", "left_finger", "right_finger")]


def fiber_task_success(env):
    """Latched success (goal held for stable_duration_s); evaluates the goal for this step."""
    env.evaluate_goal()
    return env.goal_success.clone()


def fiber_task_failed(env):
    """Latched failure: gripper-strand contact, cable below table, or non-finite cable state."""
    env.evaluate_goal()
    return env.goal_failed.clone()


def _root_pose(asset_dir):
    """World pose of the cable's fixed root link (Isaac Lab writes the articulation root pose from init_state)."""
    import json
    import numpy as np
    from scipy.spatial.transform import Rotation
    path = os.path.join(asset_dir, "layout_world.json")
    if not os.path.exists(path):  # tier assets not built/installed: the env fails at spawn with a clear error
        return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)
    with open(path) as f:
        root = json.load(f)["links"]["terminal"]
    q = Rotation.from_matrix(np.asarray(root["R"])).as_quat()  # xyzw
    return tuple(float(v) for v in root["origin"]), (float(q[3]), float(q[0]), float(q[1]), float(q[2]))


def make_scene_cfg(tier: str):
    asset_dir = os.path.join(FIBER_ASSET_ROOT, tier)
    root_pos, root_rot = _root_pose(asset_dir)

    @configclass
    class FiberBundlingSceneCfg(YamBimanualSceneCfg):
        fixtures = AssetBaseCfg(
            prim_path="{ENV_REGEX_NS}/fixtures",
            spawn=sim_utils.UsdFileCfg(usd_path=os.path.join(asset_dir, "fixtures.usda")),
        )
        cable = ArticulationCfg(
            prim_path="{ENV_REGEX_NS}/cable",
            spawn=sim_utils.UsdFileCfg(
                usd_path=os.path.join(asset_dir, "cable.usda"),
                activate_contact_sensors=True,
                articulation_props=sim_utils.ArticulationRootPropertiesCfg(
                    solver_position_iteration_count=CABLE_SOLVER_ITERS[0],
                    solver_velocity_iteration_count=CABLE_SOLVER_ITERS[1]),
            ),
            init_state=ArticulationCfg.InitialStateCfg(pos=root_pos, rot=root_rot,
                                                       joint_pos={".*": 0.0}, joint_vel={".*": 0.0}),
            # Passive cable: no actuators. Damping/armature come from the USD (old MJCF values).
            actuators={},
        )
        strand_contact = ContactSensorCfg(
            prim_path="{ENV_REGEX_NS}/cable/fiber_.*",
            update_period=0.0,          # every physics substep
            history_length=4,           # = decimation: all substeps of a control step are checked
            track_pose=False,
            filter_prim_paths_expr=GRIPPER_BODY_PATHS,
        )

        def __post_init__(self):
            super().__post_init__()
            # Sensors must refresh every substep so the contact history covers all of them.
            self.lazy_sensor_update = False
            if os.environ.get("YAMLAB_STRIP_CAMERAS", "0") == "1":
                for name in list(vars(self)):
                    if name.endswith("_camera"):
                        setattr(self, name, None)

    return FiberBundlingSceneCfg


@configclass
class FiberBundlingEventsCfg(BaseEventsCfg):
    """Reset = scene default (fixed start layout; the old task had no randomization)."""


@configclass
class FiberBundlingRewardsCfg:
    sparse_success_reward = RewardTermCfg(func=compute_sparse_success_reward, params={}, weight=1.0)


@configclass
class FiberBundlingTerminationsCfg:
    time_out = TerminationTermCfg(func=mdp.time_out, time_out=True)
    task_success = TerminationTermCfg(func=fiber_task_success, params={})
    task_failed = TerminationTermCfg(func=fiber_task_failed, params={})


def make_env_cfg(task_name: str):
    tier = TIERS[task_name]
    scene_cls = make_scene_cfg(tier)

    @configclass
    class FiberBundlingManagerEnvCfg(YamBimanualEnvCfg):
        scene: scene_cls = scene_cls(num_envs=1, env_spacing=3.0)
        events: FiberBundlingEventsCfg = FiberBundlingEventsCfg()
        rewards: FiberBundlingRewardsCfg = FiberBundlingRewardsCfg()
        terminations: FiberBundlingTerminationsCfg = FiberBundlingTerminationsCfg()
        obj_name_to_event_name: dict[str, str] = {}

        def __post_init__(self):
            super().__post_init__()
            # Rigid-body sub-path of the grasp-detection target "cable" (read by configure_contact_sensors).
            self._contact_body_links = {"cable": GRASP_DETECT_LINK}

    FiberBundlingManagerEnvCfg.TASK_NAME = task_name
    FiberBundlingManagerEnvCfg.TIER = tier
    FiberBundlingManagerEnvCfg.ASSET_DIR = os.path.join(FIBER_ASSET_ROOT, tier)
    FiberBundlingManagerEnvCfg.CONTACT_OBJECT_NAMES = []
    return FiberBundlingManagerEnvCfg


FiberBundlingVeryEasyManagerEnvCfg = make_env_cfg("FiberBundling-VeryEasy-v0")
FiberBundlingEasierManagerEnvCfg = make_env_cfg("FiberBundling-Easier-v0")
FiberBundlingEasyManagerEnvCfg = make_env_cfg("FiberBundling-Easy-v0")
