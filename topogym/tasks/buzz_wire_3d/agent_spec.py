"""Public task rules and Panda facts, without wire coordinates or a solution."""
from topogym.agent_bridge.panda_contract import contract


def describe_task(cfg):
    return dict(contract(cfg), task_id="buzz_wire_3d", task_spec_version=4,
        objective="traverse_release",
        task_goal="用机械臂握持蓝色手柄，让金属环从绿色端沿整条空间导线移动到橙色端，"
            "保持穿环且通行时不触线；通过最后弯道后松手，让环沿末端立柱靠重力滑到橙色限位球并稳定静置。",
        initialization="固定紧凑单臂基础实例，初始环已穿在线上，机械臂处于预抓取位置；"
            "tick=0 未推进物理、无辅助约束，夹爪初始半开口 0.0071 m、闭合目标 0 m。"
            "不包括自主接近、桌面拾取或初次穿环。当前关节读 observation.robot，home_qpos 不是初态。",
        grasp_model="真实接触摩擦，无焊接或其他辅助抓持；grasp_assistance 始终 inactive。"
            "增大夹爪半开口目标张爪，减小则闭合；可以自行重新抓取。"
            "环杆无外力驱动和重力补偿，无自动姿态跟踪或抓持变换修正。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        observation_policy="三路实时 RGB、对应相机位姿和机器人本体状态；无导线坐标、环杆真值位姿、"
            "路线进度、目标误差、网格、参考图或参考动作。腕相机固定在手部，不利用物体真值自动追踪。",
        contact_solver=dict(constraint_timeconst_s=float(cfg.task.physics.constraint_timeconst),
            noslip_iterations=int(cfg.task.physics.noslip_iterations),
            noslip_tolerance=float(cfg.task.physics.noslip_tolerance),
            note="实验性摩擦收敛后处理；不增加物体连接约束"),
        evaluator="pilot_buzz_wire_traverse_release_v1", physics_qualified=False,
        success_rule="保持穿环并连续通过线路至末端；环中心距橙色限位球中心 <0.05 m、"
            "穿孔交点处于最后 0.05 m 导线，已脱离机器人接触且由末端承载 >0.01 N；"
            "线速度 <0.002 m/s、角速度 <0.02 rad/s，连续 1 s。仍抓持或只到达末端附近不算完成。",
        failure_rule="失去穿环、穿孔交点沿线路单控制步跳跃 >0.03 m；末端松手区以外的环杆触线；"
            "环杆接触穿透 >0.0005 m，机器人/固定物或机器人自碰穿透 >0.0002 m；"
            "机器人非指垫部位接触环杆；掉落、固定玩具位姿改变、非有限状态、异常速度或持续跟踪失控。"
            "末端脱离机器人后机械能额外增长 >0.001 J 也会失败。",
        evaluator_limit="固定基础实例接入试验版，重新抓取、完整自主通行和终态尚未物理验证。"
            "几何、接触与穿环按控制步检查，不是逐积分子步或连续几何证明；不继承历史演示的完整资格。"
            "末端允许接触只在已连续通过最后弯道、位于末端立柱且已脱离机器人时生效。")
