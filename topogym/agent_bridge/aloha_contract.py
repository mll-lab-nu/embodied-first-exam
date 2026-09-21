"""Public ALOHA facts and position commands, independent of puzzle geometry."""
from .adapters import finite_vector


def contract(cfg):
    from omegaconf import OmegaConf
    from .camera_info import camera_contract
    control = OmegaConf.to_container(cfg.robot_control, resolve=True)
    env = OmegaConf.to_container(cfg.env, resolve=True)
    cameras = camera_contract(env["cameras"])
    roles = dict(cam_high="高位俯视：桌面和双臂整体工作区", cam_low="低位前视：物体高度和操作区域",
                 cam_left_wrist="左腕随动：夹爪附近", cam_right_wrist="右腕随动：夹爪附近")
    for name, camera in cameras.items():
        camera["role"] = roles[name]
    return dict(robot=dict(model="ALOHA 2 dual-arm (ViperX 300 6DOF derived), native parallel grippers",
        arms=["left", "right"], arm_dofs_each=6, finger_slide_dofs_each=2,
        arm_joint_order=control["robot"]["arm_joint_names"],
        finger_joint_order=control["robot"]["finger_joint_names"],
        home_qpos={s: control["home"][s] for s in ("left", "right")},
        mount_world=env["robot_mount"],
        source_base_adapter_z_translation_m=-.02+float(control["robot"].get("base_riser_height_m", 0)),
        end_effector_link="{left|right}/"+control["robot"]["ee_link"],
        grasp_center_offset_in_ee_m=[.13, 0, -.003], controller=control["controller"],
        observation_fields=dict(arm_qpos="six joint angles, radians, same order as action",
            finger_qpos="two finger rail displacements, metres, NOT the pad opening",
            hand_pos="gripper_link origin in world metres, NOT fingertip center",
            hand_quat_wxyz="gripper_link to world quaternion, wxyz",
            grasp_center_pos="hand_pos + R(hand_quat_wxyz) @ [0.13, 0, -0.003]")),
        world=dict(position_units="metres", rotation_units="radians unless labelled otherwise",
            up_axis="+z", gravity_m_s2=env["sim"]["gravity"],
            table_surface_origin_m=env["frames"]["table_surface"]["origin"],
            task_frame_origin_m=env["frames"]["task"]["origin"], task_axes="parallel to world axes",
            table_size_m=env["world"]["table"]["size"]),
        control_dt_s=float(env["sim"]["dt"]), physics_substeps=int(env["sim"]["substeps"]),
        action_schema=dict(left="optional {qpos: [6 radians], gripper: single finger rail displacement in metres}",
            right="same as left; both targets applied before stepping",
            joint_limits_rad=control["robot"]["arm_joint_limits"],
            gripper_limits_m=[control["gripper"]["closed_qpos"], control["gripper"]["open_qpos"]]),
        action_semantics="Position targets, not teleportation. Omitted fields retain targets; {} holds. "
            "Duration is ticks * control_dt_s; observe actual reached poses. Interpolate large movements.",
        example_code="env.step({}, steps=20)", cameras=list(cameras), camera_calibration=cameras,
        initial_observation=dict(required_cameras=list(roles), delivery="all cameras before first action",
            format="synchronized PNGs at tick 0"))


def validate_action(action, schema):
    if not isinstance(action, dict) or set(action)-{"left", "right"}:
        raise ValueError("Action has only optional left/right commands")
    for command in action.values():
        if not isinstance(command, dict) or not command or set(command)-{"qpos", "gripper"}:
            raise ValueError("Each arm command has qpos and/or gripper")
        if "qpos" in command:
            finite_vector(command["qpos"], 6, "qpos")
            if any(not lo <= q <= hi for q, (lo, hi) in zip(command["qpos"], schema["joint_limits_rad"])):
                raise ValueError("Arm joint limit exceeded")
        if "gripper" in command:
            finite_vector([command["gripper"]], 1, "gripper")
            lo, hi = schema["gripper_limits_m"]
            if not lo <= command["gripper"] <= hi:
                raise ValueError("Finger displacement outside limits")
