# 当前模块职责

| 模块 | 保留职责 |
| --- | --- |
| `core` | 配置与实体清单；旧四类任务登记表已归档 |
| `world` | 桌面、绳与软体后端、接触辅助、Nyx 渲染、封闭实验室与[相机预设](../../../configs/camera_configs/README.md) |
| `robot` | 机器人资产、Franka IK、Robotiq 开口映射、[ALOHA 双臂控制与接入](dual_arm_aloha_zh.md) |
| `primitives` | 可复用的抓持、插入、拖动、附件与接触动作 |
| `tasks/<task_id>` | 当前任务专用的几何、场景、执行器、规划及判定 |
| `planning` | 通用 subgoal、waypoint 和绳交叉几何；旧任务 planner 已归档 |
| `generation` | episode 数据结构、确定性随机数、布局随机化与 braid 工具；旧任务 split 注册表已归档 |
| `runtime` | 通用 episode 运行契约 |
| `supervision` | 稳定性、粒子与绳诊断；旧任务专用监控已归档 |
| `data`、`utils` | HDF5 schema/writer、相机和录像工具；旧任务 replay 已归档 |

开锁当前使用的 `runner`、`planner`、`certificate`、`grasp`、`oracle`、`evaluator`、`review`
全部由 `topogym/tasks/lock_picking/` 持有，避免当前入口依赖历史 demo。
包入口只导出当前通用契约，不再集中导入旧任务。

旧模块说明和早期 A–G 蓝图见 [历史模块文档](../../../legacy/docs/develop/modules/)。
