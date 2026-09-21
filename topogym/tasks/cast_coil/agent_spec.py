"""Text objective and robot/camera facts; object geometry stays unobserved."""


def describe_task(cfg):
    from omegaconf import OmegaConf
    from topogym.agent_bridge.camera_info import camera_contract

    control = OmegaConf.to_container(cfg.robot_control, resolve=True)
    env = OmegaConf.to_container(cfg.env, resolve=True)
    objective = str(cfg.task.objective)
    if objective not in ("assemble", "disassemble"):
        raise ValueError("Unknown Cast Coil objective")
    cameras = camera_contract(env["cameras"])
    roles = dict(cam_high="High overhead view: tabletop layout, both arms and the overall positions of the pieces",
                 cam_low="Low front view with an additional +20-degree pitch: height, grasping and release",
                 cam_left_wrist="Left wrist close-up: local contact between the left gripper and the pieces",
                 cam_right_wrist="Right wrist close-up: local contact between the right gripper and the pieces")
    for name, camera in cameras.items():
        camera["role"] = roles.get(name, name)
    rule = ("Both pieces reach the intended assembled fit; the evaluator's internal relative-position error "
            "is <0.001 m and relative-orientation error is <0.02 rad. "
            if objective == "assemble" else
            "The pieces' world-space AABBs have a surface gap >0.01 m along at least one axis. ")
    return dict(task_id="cast_coil", task_spec_version=4, objective=objective,
        evaluator="pilot_pose_release_stability_v1", physics_qualified=False,
        # Describe the visible goal, without disclosing a solution path or target transform.
        # Hanayama calls the assembled puzzle a box-like form with a hole. This
        # authored prototype has unequal width/depth and intentional clearances.
        task_goal=("Use both robot arms to assemble the gold and silver Cast Coil pieces into one compact "
                   "box-shaped block with a square outer profile and a central opening. "
                   "Fully seat the two coiled pieces in their complementary, interleaved positions so that "
                   "their outer edges align and neither piece remains partially withdrawn. "
                   "Preserve the central opening and the designed clearances between surfaces; "
                   "do not force the pieces to overlap. "
                   "Place the completed assembly on the tabletop, release both grippers and withdraw them, "
                   "and leave the assembly at rest for at least 0.5 seconds of simulated time."
                   if objective == "assemble" else
                   "Use both robot arms to separate the gold and silver Cast Coil pieces completely. "
                   "The final state must contain two detached pieces with a visible gap between them, "
                   "each resting on the tabletop. Release both grippers and withdraw them, and leave "
                   "both pieces at rest for at least 0.5 seconds of simulated time."),
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False,
            instruction="Infer the current object configuration, relative relationships and feasible actions "
                        "from this episode's camera views and action feedback. You may inspect historical "
                        "frames from this episode and construct and test your own geometric hypotheses."),
        initialization="ALOHA home, free pieces on table, no grasp assistance; no settling ticks before initial observation",
        robot=dict(model="ALOHA 2 dual-arm (ViperX 300 6DOF derived), native ALOHA 2 parallel grippers",
            arms=["left", "right"],
            arm_dofs_each=6, finger_slide_dofs_each=2, actuators_each=7,
            arm_joint_order=control["robot"]["arm_joint_names"],
            finger_joint_order=control["robot"]["finger_joint_names"],
            home_qpos={side: control["home"][side] for side in ("left", "right")},
            mount_world=env["robot_mount"], source_base_adapter_z_translation_m=-.02+float(control["robot"].get("base_riser_height_m", 0)),
            end_effector_link="{left|right}/"+control["robot"]["ee_link"],
            observation_fields=dict(arm_qpos="6 joint angles in radians, same order as action",
                finger_qpos="two measured finger rail displacements in metres, NOT pad opening",
                hand_pos="world position of gripper_link origin in metres, NOT fingertip center",
                hand_quat_wxyz="gripper_link to world rotation quaternion, wxyz order",
                grasp_center_pos="world position: hand_pos + R(hand_quat_wxyz) @ [0.13, 0, -0.003]"),
            grasp_center_offset_in_ee_m=[.13, 0, -.003], controller=control["controller"]),
        world=dict(position_units="metres", rotation_units="radians unless explicitly labelled degrees",
            up_axis="+z", gravity_m_s2=env["sim"]["gravity"], table_surface_origin_m=env["frames"]["table_surface"]["origin"],
            task_frame_origin_m=env["frames"]["task"]["origin"], task_axes="parallel to world axes",
            table_size_m=env["world"]["table"]["size"]),
        control_dt_s=float(env["sim"]["dt"]), physics_substeps=int(env["sim"]["substeps"]),
        action_schema=dict(left="optional {qpos: [6 radians], gripper: single finger rail displacement in metres}",
            right="same as left; both targets applied before stepping", joint_limits_rad=control["robot"]["arm_joint_limits"],
            gripper_limits_m=[control["gripper"]["closed_qpos"], control["gripper"]["open_qpos"]]),
        action_semantics="Position-control targets, not teleportation. Omitted fields retain targets; {} holds. "
                         f"A tick is {float(env['sim']['dt']):g} s; duration = ticks * control_dt_s. Observe actual reached poses.",
        example_code='env.step({}, steps=20)', cameras=list(cameras), camera_calibration=cameras,
        observation_policy="RGB and robot proprioception, with per-frame camera poses in new runs; live object poses/goal error are not observation fields",
        success_rule=rule+"Both pieces must be released (all robot-piece contact forces <=0.05 N), "
                         "with linear speeds <0.001 m/s and angular speeds <0.02 rad/s, "
                         "continuously for 0.5 seconds of simulated time.",
        failure_rule="Interpiece contact penetration >0.001 m or either piece's assembly origin falling "
                     "more than 0.1 m below the tabletop causes immediate failure. Execution or observation "
                     "errors also terminate the attempt; no rollback is available.",
        evaluator_limit="pilot evaluator checks pose/separation, release and speed; it does not certify a commercial replica or a full physical benchmark")
