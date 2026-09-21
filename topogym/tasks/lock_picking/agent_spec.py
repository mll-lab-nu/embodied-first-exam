"""Public instructions without slot layouts, rotor angles or solving steps."""
from topogym.agent_bridge.panda_contract import contract


def describe_task(cfg):
    return dict(contract(cfg), task_id="lock_picking", task_spec_version=4, objective="insert_release",
        task_goal="用机械臂从实体承托架抓取钥匙，操作钥匙通过三个被动锁片，插入标有 END 的固定终点孔板；松手并稳定保持。",
        initialization="固定标准实例；Panda 从 home 开始，钥匙为承托架上的自由刚体。tick=0 无预推进、无辅助抓持。",
        scene_mechanics="三个锁片由接触被动转动，有实体限位；无锁片电机指令。只允许用夹持的钥匙操作锁片，"
            "不允许机械臂或夹爪直接拨动锁片、固定面板或限位结构。目标不是开真实门锁。",
        grasp_model="接触辅助：减小夹爪半开口目标启用抓持尝试；只有实际双指承载接触路径的力 >0.01 N 才可附着钥匙。"
            "增大目标立即解除辅助。不得指定物体附着、瞬移钥匙或设置锁片角度。不是纯摩擦抓持。",
        perception=dict(object_configuration_source="current_episode_camera_frames",
            reference_images_provided=False, object_geometry_provided=False),
        observation_policy="仅本轮三视角图像、相机位姿、机器人本体和辅助状态；无钥匙真值位姿、锁片角度、孔槽参数、目标误差或求解路线。",
        evaluator="pilot_lock_insert_release_v1", physics_qualified=False,
        success_rule="钥匙尖端到达 END 平面（轴向误差 <=3.75 mm），轴线横向误差 <=10 mm、倾角 <=3°，"
            "凸片与孔槽匹配（0.5°判定容差）。辅助已解除、机器人与钥匙总接触力 <0.01 N，"
            "钥匙线速度 <0.01 m/s、角速度 <0.1 rad/s，连续 0.5 s。",
        failure_rule="钥匙与机构总接触力 >10 N；接触穿透 >2 mm；机械臂直接触碰机构的总力 >0.01 N；"
            "同轴啮合时凸片与孔槽角度违规 >2°；掉落、非有限状态、固定基座移动或锁片限位异常；"
            "关节跟踪误差 >0.2 rad 持续超过 0.2 s。失败不可恢复。",
        evaluator_limit="固定初态接入试验版，逐控制步检查，非逐子步连续碰撞证明。"
            "偏轴操作依赖真实接触检查；尚未完成本 adapter 的全流程开锁或随机变体验证。")
