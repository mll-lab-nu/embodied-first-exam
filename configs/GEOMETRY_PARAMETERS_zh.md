# 当前几何参数入口

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

| 对象 | 配置/源码（路径相对仓库根目录） |
| --- | --- |
| 通用任务坐标与机器人安装面 | `configs/common_configs/manipulation_space_tabletop_v1.yaml` |
| 桌子、机器人世界位置、相机、仿真时基 | `configs/env_configs/world_tabletop_v1.yaml`、`world_tabletop_fem_v1.yaml` |
| 封闭实验室与公共外观 | `configs/presentation_configs/nyx_lab.yaml`、`topogym/world/nyx_lab.py` |
| 开锁基线几何、限位、接触与成功条件 | `configs/task_configs/lock_picking.yaml`、`topogym/tasks/lock_picking/` |
| 加宽锁片间距与对应钥匙长度 | `configs/lock_picking_spaced_preview.yaml` 的 `task.geometry.pitch` / `grip_offset` |
| CLASSIC 刺猬与笼子 | `configs/hedgehog_in_cage_classic_preview.yaml`、`topogym/tasks/hedgehog_in_cage/geometry.py` |
| 十项任务的候选参数轴 | `configs/task_cards/*.yaml`；参数卡不等同于已实现/已验证的场景 |

单位以米、秒、千克为主；角度按具体字段后缀（如 `deg`）解释。
任务坐标的 `z=0` 通常是桌面，不能把实体中心高度当成底面高度；
具体转换见 [坐标说明](../docs/develop/framework/genesis_world_coordinates_zh.md)。
共享预设锁定时修改桌面或相机几何会触发 builder 校验；需要变体的任务必须显式声明自己的场景配置。

旧任务逐项参数速查已保存到 [旧版文档](../legacy/configs/GEOMETRY_PARAMETERS_zh.md)。
