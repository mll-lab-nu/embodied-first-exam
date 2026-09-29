"""Public scene/robot facts only; shape and configuration come from live views."""
from topogym.agent_bridge.panda_contract import contract


def describe_task(cfg):
    return dict(contract(cfg), task_id="hedgehog_in_cage", task_spec_version=4, objective="extract_release",
        task_goal="用机械臂将刺球从固定笼体中完整取出，放到桌面，松开并稳定静置。不得破坏或移动固定笼体。",
        initialization="CLASSIC wood 固定基础实例，从预抓取位置开始；不包含从远处自主接近和抓取。"
            "tick=0 无辅助约束、无预推进；夹爪按半开口 0.0054 m 初始化（实测值读观测），闭合目标 0.0044 m。"
            "当前关节初值读 observation.robot.arm；home_qpos 仅为通用 home。",
        grasp_model="非纯摩擦的接触辅助：初始已启用抓持尝试；实际双指承载路径的接触力 >0.01 N 才可附着刺球。"
            "增大夹爪半开口目标立即解除辅助，减小目标重新启用尝试。无指定物体附着或位姿指令。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        observation_policy="实时三视角 RGB、对应相机位姿、机器人本体状态及夹爪辅助状态；无刺球真值位姿、几何、退出路线或目标误差。",
        evaluator="pilot_hedgehog_extraction_release_v1", physics_qualified=False,
        success_rule="刺球与笼体世界 AABB 在至少一个轴上相隔 >0.005 m，且刺球在桌面范围内；"
            "辅助已解除，仅桌面承载接触 >0.01 N；线速度 <0.001 m/s、角速度 <0.008727 rad/s，"
            "连续 2 s 且原点相对静置窗口起点漂移 <=0.0002 m。",
        failure_rule="刺球/笼体或机器人/固定物穿透 >0.00015 m；其余刺球接触或机器人自碰撞穿透 >0.001 m；"
            "刺球掉落到桌面以下 0.1 m、非有限状态、固定笼位姿异常，或关节跟踪误差 >0.2 rad 持续超过 0.2 s。",
        evaluator_limit="固定初态上的 agent 接入试验版。逐控制步检查，不是逐物理子步连续几何证明；"
            "任意动作、重新抓持、完整取出和随机变体尚未获得本 adapter 的全流程物理资格。")
