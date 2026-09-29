"""Public Keyhole task facts; infer the puzzle solely from episode images."""
from topogym.agent_bridge.aloha_contract import contract


def describe_task(cfg):
    return dict(contract(cfg), task_id="cast_keyhole", task_spec_version=4, objective="disassemble",
        task_goal="用双臂将金色和银色零件完全分离，并稳定保持。允许末态仍由夹爪抓持，不要求放回桌面。",
        initialization="抬高的双臂预抓取初态；初始手指轨位移 0.0127 m，闭合控制目标 0.0105 m。"
            "tick=0 尚无辅助约束，未推进物理；后续只有实际承载接触满足条件才启用辅助。"
            "不包含从桌面自主拾取。当前关节读 observation.robot，home_qpos 仅是通用 home。",
        grasp_model="接触触发的辅助抓持，并非纯摩擦。闭合时在接触力 >0.01 N 的双指简单承载路径上的"
            "零件才允许附着；增大夹爪目标会释放该手辅助，减小目标重新启用抓持尝试。"
            "初始双手已启用抓持尝试。不提供按名字指定物体、直接附着或物体位姿指令。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        observation_policy="四路实时 RGB、每帧相机位姿、机器人本体状态、每手辅助是否激活；"
            "不提供物体真值位姿、几何、路线或目标误差。",
        evaluator="pilot_keyhole_separation_hold_v1", physics_qualified=False,
        success_rule="评测器内部凸体分离下界 >0.02 m，两件线速度各 <0.001 m/s、角速度各 <0.02 rad/s，"
            "连续保持 0.5 s；可由机械臂保持，不要求释放。",
        failure_rule="两件凸体 SAT 间隙 <−0.0005 m；谜题相关、机器人自碰撞或机器人/桌面穿透 >0.001 m；"
            "任一零件掉到桌面下方 0.1 m；非有限状态；关节跟踪误差 >0.2 rad 持续超过 0.2 s。",
        evaluator_limit="固定基础实例上的 agent 接入试验版；任意动作与新的自动接触辅助未获得完整物理资格。"
            "接触和 SAT 在每个控制步检查，不声称逐子步连续碰撞证明。")
