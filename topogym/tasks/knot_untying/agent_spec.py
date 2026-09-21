"""Public rope task facts; no material coordinates, grasp indices or route."""
from topogym.agent_bridge.aloha_contract import contract


def describe_task(cfg):
    return dict(contract(cfg), task_id="knot_untying", task_spec_version=4, objective="untie_release",
        task_goal="解开桌上的单根绳结，把整根绳放回桌面，双手释放并稳定静置。不能切断、穿透或移除绳索。",
        initialization="ALOHA 双臂从开爪 home 开始；绳索两端自由，无固定顶点、无初始抓持和隐藏预推进。",
        rope_model="连续 FEM 绳体，直绳材料参考态，具有重力、自接触和桌面接触；不是刚体链或位置回放。",
        grasp_model="减小夹爪目标启用接触辅助尝试。沿整根绳均匀提供局部抓持带，不预选求解抓点。"
            "只有两侧实际 IPC 指垫表面都距同一抓持带表面 <=0.801 mm 才能附着；这是距离门槛，不宣称测得抓持力。"
            "每手最多一带，两手不能同时约束重叠顶点；软位置约束跟随实测手部位姿，不改写绳节点位置。"
            "接触后保持实测指间距，增大夹爪目标解除辅助。不是纯摩擦抓持。",
        perception=dict(object_configuration_source="current_episode_camera_frames", reference_images_provided=False,
                        object_geometry_provided=False),
        observation_policy="仅本轮四路 RGB、相机外参、机器人本体和各手辅助状态；无绳节点／中心线、交叉点、材料索引、结型答案或解结路线。",
        evaluator="pilot_released_planar_rope_v1", physics_qualified=False,
        success_rule="双手释放并撤离（指垫与绳的世界包围盒间隔 >0.8 mm）；整绳处于桌面范围，所有节点在桌面上方 12 mm 内；XY 中心线无交叉，"
            "投影弧长间隔 >24 mm 的非局部投影线段间距 >8 mm；原生 FEM 速度 RMS <1 mm/s、最大 <5 mm/s，"
            "连续 2 s，期间节点最大漂移 <2 mm。",
        failure_rule="FEM 倒置或体积比 <=0.2、非有限状态、独立表面 CCD 拒绝、桌面穿透 >0.05 mm、"
            "总绳长变化 >5% 或局部轴向应变 >20%；刚体穿透 >0.5 mm、实际关节超限、"
            "原生碰撞面与可视机器人偏差 >2 mm、辅助跟随误差 >2 mm，或持续关节失跟踪。",
        evaluator_limit="保守的释放后平面展开判据，不是一般结型拓扑不变量；未完成 agent 全程求解资格。"
            "CCD 逐 IPC 子步检查；相机逐控制步保存。后端异常可能中断一个不完整物理步，不能重放。")
