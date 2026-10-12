"""Configuration for the BuzzWire3D tasks (port of the old RoboTangle buzz_wire_3d family).

Scene: the unchanged YAM bimanual workstation plus
  * deck  : wooden deck (kinematic; top plate 520 x 369 mm, 142.5 mm above the table),
  * rail  : the bent metal wire, 2.94 mm diameter, as kinematic capsules along the old centreline,
  * stops : the two 8 x 8 x 12 mm wooden end blocks (kinematic),
  * wand  : the dynamic loop tool (ring + stem + wooden grip), old collision model 1:1.
All parts keep the old millimetre geometry; the whole old scene is re-placed in the YAM
workspace by one rigid transform (BUZZ_LAYOUTS). USD assets are built by
tasks/buzz_wire_3d/tools/make_assets.py.
"""

import json
import math
import os

import torch

import isaaclab.sim as sim_utils
import isaaclab.envs.mdp as mdp
from isaaclab.assets import AssetBaseCfg, RigidObjectCfg
from isaaclab.managers import RewardTermCfg, SceneEntityCfg, TerminationTermCfg
from isaaclab.sensors import ContactSensorCfg
from isaaclab.utils import configclass

from yamlab.envs.yam_bimanual_scene import YamBimanualSceneCfg
from yamlab.robot.yam import ROBOT
from yamlab.utils.task_logic import check_obj_below_table, compute_sparse_success_reward

from .yam_bimanual_env_cfg import YamBimanualEnvCfg, BaseEventsCfg

# Old table frame (mm) -> YAMLab world (m):  p_world = Rz(yaw) p_old / 1000 + translation.
# yaw 0: the old wire span (old +x) runs along world +x: start post near the arms (x 0.395, y -0.035), finish
# post far (x 0.745, y -0.035); the deck (520 x 369 mm) spans x 0.31-0.83, y -0.185..0.185, clear of both
# arms' initial open fingers (>= 50 mm).
# start_handle_yaw_deg (approved deviation, see STATUS.md): the wand's start rest pose is the old one rotated
# about the start post so that its handle points to this world yaw; the YAM gripper cannot pick the wand in
# the old start pose (handle under the wire span). Wire, deck, posts and the finish/goal are unchanged.
BUZZ_LAYOUTS = {
    "very_easy": dict(yaw_deg=0.0, translation=(0.5144, 0.270, ROBOT.table_position[2]), start_handle_yaw_deg=60.0),
    "easier": dict(yaw_deg=0.0, translation=(0.5144, 0.270, ROBOT.table_position[2]), start_handle_yaw_deg=60.0),
}

# Filter bodies of the wand contact sensor (order matters: columns of force_matrix_w).
WAND_FILTERS = ["rail", "deck", "stops"]
ROBOT_LINKS = ["link_4", "link_5", "link_6", "left_finger", "right_finger", "camera_mount", "camera_d405"]
for _arm in ("LeftArm", "RightArm"):
    for _link in ROBOT_LINKS:
        WAND_FILTERS.append(f"{_arm}/arm/{_link}")


def buzz_assets_dir(tier: str) -> str:
    root = os.environ.get("BUZZ_WIRE_ASSETS")
    if not root:
        import yamlab
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(yamlab.__file__))), "assets", "buzz_wire_3d")
    return os.path.join(root, tier)


def load_buzz_geometry(tier: str) -> dict:
    with open(os.path.join(buzz_assets_dir(tier), "geometry.json")) as f:
        return json.load(f)


def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def layout_quat(tier: str):
    h = math.radians(BUZZ_LAYOUTS[tier]["yaw_deg"]) / 2
    return (math.cos(h), 0.0, 0.0, math.sin(h))


def layout_point(tier: str, p_old_m):
    yaw = math.radians(BUZZ_LAYOUTS[tier]["yaw_deg"])
    c, s = math.cos(yaw), math.sin(yaw)
    t = BUZZ_LAYOUTS[tier]["translation"]
    x, y, z = p_old_m
    return (c * x - s * y + t[0], s * x + c * y + t[1], z + t[2])


def start_pose_world(tier: str):
    """Wand start pose (pos, quat wxyz) in the world: old start pose, re-laid out, then yawed about the start post."""
    geo = load_buzz_geometry(tier)
    p = layout_point(tier, geo["start_p"])
    q = _quat_mul(layout_quat(tier), tuple(geo["start_q_wxyz"]))
    hy = BUZZ_LAYOUTS[tier].get("start_handle_yaw_deg")
    if hy is None:
        return p, q
    w, x, y, z = q
    hx, hyy = 1 - 2 * (y * y + z * z), 2 * (x * y + z * w)      # body x axis in the world (xy part)
    d = math.radians(hy) - math.atan2(hyy, hx)
    post = layout_point(tier, geo["rail_m"][0])
    c, s_ = math.cos(d), math.sin(d)
    px, py = p[0] - post[0], p[1] - post[1]
    p = (post[0] + c * px - s_ * py, post[1] + s_ * px + c * py, p[2])
    q = _quat_mul((math.cos(d / 2), 0.0, 0.0, math.sin(d / 2)), q)
    return p, q


def _fixed_asset(tier: str, name: str) -> AssetBaseCfg:
    return AssetBaseCfg(
        prim_path=f"{{ENV_REGEX_NS}}/{name}",
        spawn=sim_utils.UsdFileCfg(
            usd_path=os.path.join(buzz_assets_dir(tier), f"{name}.usda"),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(kinematic_enabled=True, disable_gravity=True),
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=0.001, rest_offset=0.0),
            activate_contact_sensors=True,
        ),
        init_state=AssetBaseCfg.InitialStateCfg(pos=BUZZ_LAYOUTS[tier]["translation"], rot=layout_quat(tier)),
    )


def add_buzz_assets(scene_cfg, tier: str):
    """Attach the buzz-wire objects (and the wand contact sensor) to a YAM scene cfg."""
    geo = load_buzz_geometry(tier)
    scene_cfg.deck = _fixed_asset(tier, "deck")
    scene_cfg.rail = _fixed_asset(tier, "rail")
    scene_cfg.stops = _fixed_asset(tier, "stops")
    scene_cfg.wand = RigidObjectCfg(
        prim_path="{ENV_REGEX_NS}/wand",
        spawn=sim_utils.UsdFileCfg(
            usd_path=os.path.join(buzz_assets_dir(tier), "wand.usda"),
            rigid_props=sim_utils.RigidBodyPropertiesCfg(
                disable_gravity=False,
                max_depenetration_velocity=float(os.environ.get("BUZZ_WAND_DEPEN", "0.5")),
                solver_position_iteration_count=int(os.environ.get("BUZZ_WAND_POS_ITERS", "32")),
                solver_velocity_iteration_count=int(os.environ.get("BUZZ_WAND_VEL_ITERS", "4")),
                angular_damping=float(os.environ.get("BUZZ_WAND_ANG_DAMP", "0.05")),
            ),
            mass_props=sim_utils.MassPropertiesCfg(mass=0.012906269247007685),
            collision_props=sim_utils.CollisionPropertiesCfg(contact_offset=0.001, rest_offset=0.0),
            activate_contact_sensors=True,
        ),
        init_state=RigidObjectCfg.InitialStateCfg(pos=start_pose_world(tier)[0], rot=start_pose_world(tier)[1]),
    )
    # Wand contacts with the rail / deck / stops / both grippers, every physics substep
    # (history_length = decimation, sensors updated eagerly).
    scene_cfg.wand_contacts = ContactSensorCfg(
        prim_path="{ENV_REGEX_NS}/wand",
        update_period=0.0,
        history_length=4,
        track_contact_points=False,
        filter_prim_paths_expr=[f"{{ENV_REGEX_NS}}/{f}" for f in WAND_FILTERS],
    )
    scene_cfg.lazy_sensor_update = False
    if os.environ.get("BUZZ_DEBUG_ARM_CONTACTS", "0") == "1":
        # debugging aid: unfiltered net contact forces on every link of both arms
        for arm in ("LeftArm", "RightArm"):
            setattr(scene_cfg, f"debug_{arm.lower()}_contacts", ContactSensorCfg(
                prim_path=f"{{ENV_REGEX_NS}}/{arm}/arm/.*", update_period=0.0, history_length=1))
        scene_cfg.debug_right_link6 = ContactSensorCfg(
            prim_path="{ENV_REGEX_NS}/RightArm/arm/link_6", update_period=0.0, history_length=1,
            track_contact_points=True, max_contact_data_count_per_prim=32,
            filter_prim_paths_expr=["{ENV_REGEX_NS}/rail", "{ENV_REGEX_NS}/deck", "{ENV_REGEX_NS}/stops",
                                    "{ENV_REGEX_NS}/wand", "{ENV_REGEX_NS}/Workstation"])
    if os.environ.get("BUZZ_NO_CAMERAS", "0") == "1":
        # Physics-only hosts (no RTX): drop the camera sensors (task-level switch; the robot is unchanged).
        for name in list(vars(scene_cfg)):
            if name.endswith("_camera"):
                setattr(scene_cfg, name, None)


@configclass
class BuzzWire3DVeryEasySceneCfg(YamBimanualSceneCfg):
    def __post_init__(self):
        super().__post_init__()
        add_buzz_assets(self, "very_easy")


@configclass
class BuzzWire3DEasierSceneCfg(YamBimanualSceneCfg):
    def __post_init__(self):
        super().__post_init__()
        add_buzz_assets(self, "easier")


@configclass
class BuzzWire3DEventsCfg(BaseEventsCfg):
    """Reset = scene default (the fixed old start state i00); no randomization."""


@configclass
class BuzzWire3DRewardsCfg:
    sparse_success_reward = RewardTermCfg(func=compute_sparse_success_reward, params={}, weight=1.0)


def buzz_task_success(env):
    env.buzz_update()
    return env.buzz_success.clone()


def buzz_wire_touched(env):
    env.buzz_update()
    return env.buzz_touched.clone()


@configclass
class BuzzWire3DTerminationsCfg:
    time_out = TerminationTermCfg(func=mdp.time_out, time_out=True)
    task_success = TerminationTermCfg(func=buzz_task_success, params={})
    # Old rule: any wand-metal / wire contact fails the episode (latched).
    wire_touched = TerminationTermCfg(func=buzz_wire_touched, params={})
    wand_below_table = TerminationTermCfg(
        func=check_obj_below_table,
        params={"asset_cfg": SceneEntityCfg("wand"), "table_z": ROBOT.table_position[2], "margin": 0.01},
    )


@configclass
class BuzzWire3DVeryEasyManagerEnvCfg(YamBimanualEnvCfg):
    scene: BuzzWire3DVeryEasySceneCfg = BuzzWire3DVeryEasySceneCfg(num_envs=1, env_spacing=3.0)
    events: BuzzWire3DEventsCfg = BuzzWire3DEventsCfg()
    rewards: BuzzWire3DRewardsCfg = BuzzWire3DRewardsCfg()
    terminations: BuzzWire3DTerminationsCfg = BuzzWire3DTerminationsCfg()
    obj_name_to_event_name: dict[str, str] = {}


@configclass
class BuzzWire3DEasierManagerEnvCfg(YamBimanualEnvCfg):
    scene: BuzzWire3DEasierSceneCfg = BuzzWire3DEasierSceneCfg(num_envs=1, env_spacing=3.0)
    events: BuzzWire3DEventsCfg = BuzzWire3DEventsCfg()
    rewards: BuzzWire3DRewardsCfg = BuzzWire3DRewardsCfg()
    terminations: BuzzWire3DTerminationsCfg = BuzzWire3DTerminationsCfg()
    obj_name_to_event_name: dict[str, str] = {}


BuzzWire3DVeryEasyManagerEnvCfg.CONTACT_OBJECT_NAMES = ["wand"]
BuzzWire3DEasierManagerEnvCfg.CONTACT_OBJECT_NAMES = ["wand"]
# The wand is spawned from our own USD (no --asset instance dir): its rigid body is the root prim.
BuzzWire3DVeryEasyManagerEnvCfg._contact_body_links = {"wand": ""}
BuzzWire3DEasierManagerEnvCfg._contact_body_links = {"wand": ""}

BUZZ_ENV_CFGS = {"very_easy": BuzzWire3DVeryEasyManagerEnvCfg, "easier": BuzzWire3DEasierManagerEnvCfg}
