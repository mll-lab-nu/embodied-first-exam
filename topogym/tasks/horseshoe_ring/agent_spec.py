"""Solver-facing task facts; no paths, object poses, geometry or solutions."""
from topogym.agent_bridge.aloha_contract import contract


def describe_task(cfg):
    base = contract(cfg)
    base["camera_calibration"]["cam_low"]["role"] = "低位斜前视：补充环孔和零件空间关系；使用任务专用固定安装位"
    return dict(base, task_id="horseshoe_ring", task_spec_version=4, objective="remove_ring",
        task_goal="用双臂取下场景中的目标圆环，保持其余装配的连接完整，将圆环放到桌上，松开并静置。",
        initialization="双手各预抓持一只马蹄件，初始辅助抓持已启用；目标圆环和链节自由受重力作用。"
            "初始观测前不推进物理。当前起点不包含桌面自主抓起。home_qpos 是机器人的通用 home，"
            "当前关节初值以 observation.robot 为准。",
        grasp_model="接触触发的辅助抓持，并非纯摩擦：夹爪目标增大时立即解除该手辅助；"
            "目标减小后启用抓取尝试，接触力 >0.01 N 的双指简单承载路径上的马蹄件/目标环才可附着。"
            "允许同时夹住两只马蹄件；不辅助链节，不提供指定物体或直接附着指令。",
        observation_policy="四路实时 RGB、每帧相机位姿、机器人本体状态和夹爪辅助是否激活；"
            "不返回物体真值位姿、几何、目标误差或参考图。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        evaluator="pilot_ring_separation_release_stability_v1", physics_qualified=False,
        success_rule="圆环与其余装配的世界 AABB 至少一个轴的间隔 >0.02 m；圆环无辅助抓持，"
            "仅有桌面承载接触（>0.01 N），线速度 <0.01 m/s、角速度 <0.2 rad/s，连续满足 0.5 s。"
            "其余装配连接必须完整。",
        failure_rule="谜题相关接触、机器人自碰撞或机器人与桌面穿透 >0.001 m，"
            "任一零件掉到桌面下方 0.1 m，链/孔连接丢失，或关节跟踪误差 >0.2 rad 持续超过 0.2 s，失败。",
        evaluator_limit="已验证基础场景上的 agent 接入试验版；新的自动接触辅助与任意 agent 动作尚未完成全流程物理资格验证。")
