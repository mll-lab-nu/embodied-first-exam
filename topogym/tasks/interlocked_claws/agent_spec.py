"""Public Claw task facts; all object geometry stays in the private evaluator."""
from topogym.agent_bridge.aloha_contract import contract


def describe_task(cfg):
    public = contract(cfg)
    public["camera_calibration"]["cam_low"]["role"] = "斜前低位：悬空零件和固定支架的整体关系"
    return dict(public, task_id="interlocked_claws", task_spec_version=5,
        objective="separate",
        task_goal="用双臂将橙色和青蓝色互锁件完全分离，并短暂停稳。可以继续抓持；不要求搬运、落架或松爪。不得移动或破坏支架。",
        initialization="固定基础实例，双手分别辅助预抓持一件，从悬空互锁初态开始；tick=0 未推进物理。"
            "不包含自主接近或初次抓取。当前关节和指轨位移读 observation.robot，home_qpos 仅为通用 home。",
        grasp_model="明确声明的辅助预抓持，不是纯摩擦抓取。增大某手夹爪目标即解除该手辅助；"
            "减小目标启用重新抓持尝试，只有力 >0.01 N 的双指简单承载接触路径上的零件才可新建辅助。"
            "支架不能抓持；无按名字指定物体、直接附着或物体位姿指令。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        observation_policy="四路实时 RGB、对应相机位姿、机器人本体状态和每手辅助状态；"
            "无物体真值位姿、网格、目标误差、参考图片或解题轨迹。",
        evaluator="pilot_claw_separation_v2", physics_qualified=False,
        success_rule="两件世界 AABB 至少一轴间隔 >0.02 m；线速度各 <0.005 m/s、角速度各 <0.05 rad/s，"
            "连续保持 1 s。允许保留辅助抓持，不要求放置、解除辅助或支架承载。初态表面有间隙不等于完全分离。",
        failure_rule="两件原三角网格接触深度 >0.00015 m 或完整包含；"
            "谜题相关接触、机器人自碰撞或机器人/桌面/支架/垫座穿透 >0.001 m；"
            "零件掉至桌面下 0.1 m、非有限状态、支架位姿异常；关节跟踪误差 >0.2 rad 持续超过 0.2 s。",
        evaluator_limit="基础实例的 agent 接入试验版。原任务独立非凸接触对照尚未通过，不能据此宣称通用物理资格。"
            "每控制步检查原三角网格及原生接触；三角接触深度是局部诊断，不是完整体积穿透距离。"
            "不宣称逐子步或连续路径证明；重新抓持、完整自主分离与随机变体仍待验证。")
