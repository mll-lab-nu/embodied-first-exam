"""Panda + Robotiq ports and public metadata, independent of any puzzle."""
import numpy as np
from .adapters import finite_vector
from .robot_adapter import array


def contract(cfg):
    import mujoco
    from omegaconf import OmegaConf
    from topogym.robot.assets import robot_asset
    from .camera_info import camera_contract
    model = mujoco.MjModel.from_xml_path(robot_asset(cfg.robot_control))
    c = OmegaConf.to_container(cfg.robot_control, resolve=True)
    env = OmegaConf.to_container(cfg.env, resolve=True)
    names = c["robot"]["joint_names"][:7]
    limits = [model.joint(n).range.tolist() for n in names]
    cameras = camera_contract(env["cameras"])
    roles = dict(agentview="整体工作区和机械臂", front_oblique="斜前方的场景空间关系", wrist="随手部运动的近景")
    for name, camera in cameras.items():
        camera["role"] = roles[name]
        if camera["motion"] == "wrist_attached":
            camera["world_pose"] = "Read observation.camera_poses for this frame; parent is the hand link"
    return dict(robot=dict(model="Franka Panda 7DOF + Robotiq 2F-85", arms=["arm"], arm_dofs_each=7,
        arm_joint_order=names, end_effector_link="hand", mount_world=env["robot_mount"], gravity_compensation=1.0,
        home_qpos=c["home"]["qpos"][:7],
        controller={k: v[:7] if isinstance(v, list) else v for k, v in c["controller"].items()},
        gripper_controller={k:c["gripper"]["robotiq"][k] for k in ("kp", "kv", "max_driver_torque_nm")},
        observation_fields=dict(arm_qpos="seven measured joint angles, radians",
            hand_pos="hand link origin, world metres; not pad center", hand_quat_wxyz="hand-to-world quaternion, wxyz",
            grasp_center_pos="midpoint of measured inner pad faces, world metres",
            gripper_half_gap_m="half of measured pad opening; not a sliding-joint displacement",
            gripper_driver_qpos_rad="two measured Robotiq driver angles, radians")),
        world=dict(position_units="metres", rotation_units="radians unless explicitly labelled",
            up_axis="+z", gravity_m_s2=env["sim"]["gravity"],
            table_surface_origin_m=env["frames"]["table_surface"]["origin"], table_size_m=env["world"]["table"]["size"]),
        action_schema=dict(arm="optional {qpos: [7 radians], gripper: commanded HALF pad opening in metres}",
            joint_limits_rad=limits, gripper_limits_m=[c["gripper"]["closed_qpos"], c["gripper"]["open_qpos"]]),
        action_semantics="Joint position targets, not teleportation. gripper is half aperture (0.04 means 80 mm full opening). "
            "Omitted fields retain targets; {} holds. Interpolate large joint movements.",
        control_dt_s=float(env["sim"]["dt"]), physics_substeps=int(env["sim"]["substeps"]),
        cameras=list(cameras), camera_calibration=cameras,
        initial_observation=dict(required_cameras=list(roles), format="synchronized PNGs at tick 0", delivery="all before first action"),
        example_code="env.step({}, steps=20)")


def validate_action(action, schema):
    if not isinstance(action, dict) or set(action)-{"arm"}:
        raise ValueError("Single-arm action has only optional arm command")
    if "arm" not in action:
        return
    command = action["arm"]
    if not isinstance(command, dict) or not command or set(command)-{"qpos", "gripper"}:
        raise ValueError("arm has qpos and/or gripper")
    if "qpos" in command:
        finite_vector(command["qpos"], 7, "qpos")
        if any(not lo <= q <= hi for q, (lo, hi) in zip(command["qpos"], schema["joint_limits_rad"])):
            raise ValueError("Panda joint limit exceeded")
    if "gripper" in command:
        finite_vector([command["gripper"]], 1, "gripper")
        lo, hi = schema["gripper_limits_m"]
        if not lo <= command["gripper"] <= hi:
            raise ValueError("Half aperture outside gripper limits")


class PandaPort:
    """Adapts the existing position controller without hidden physics steps."""
    def __init__(self, controller):
        self.controller = controller
        self.arms = {"arm": self}

    @property
    def current_gripper_qpos(self):
        return self.controller.current_gripper_qpos

    def arm_qpos(self):
        return self.controller.arm_qpos()

    def set_arm_qpos(self, target):
        self.controller.robot.control_dofs_position(np.asarray(target), self.controller.arm_dofs)

    def set_gripper(self, target):
        self.controller.set_gripper(target, steps=0)

    def state(self):
        c = self.controller
        q = array(c.robot.get_qpos())
        ids = [c.robot.get_joint(n).qs_idx_local[0] for n in ("finger_joint1", "finger_joint2")]
        return dict(arm=dict(arm_qpos=c.arm_qpos().tolist(), hand_pos=c.hand_pos().tolist(),
            hand_quat_wxyz=c.hand_quat().tolist(), grasp_center_pos=c.grasp_center_pos().tolist(),
            gripper_half_gap_m=float(c.gripper_qpos()[0]), gripper_driver_qpos_rad=q[ids].tolist()))
