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
| `agent_bridge` | [Coding agent 分段交互协议](agent_bridge_zh.md)：不可回滚会话、可选 HTTP / 本地文件队列、完整多视角 frames、2M token 计量；[Horseshoe adapter](horseshoe_agent_adapter_zh.md) |
| `agent_rollout` | [工具驱动 rollout](agent_rollout_pipeline_zh.md)：RGB / simulator、实时状态 SDK、固定初态 reset、跨 episode 预算与视频、共享变体 × 独立重复评测 |
| `supervision` | 稳定性、粒子与绳诊断；旧任务专用监控已归档 |
| `data`、`utils` | HDF5 schema/writer、相机和录像工具；旧任务 replay 已归档 |

当前使用入口：[rollout 实用手册](agent_rollout_usage_zh.md)、[模型接入与预算](model_service_design_zh.md)、[adapter 分层](agent_adapter_architecture_zh.md)。
独立模型服务未实现；任务与变体的验收状态见[当前进度](../../progress/current_zh.md)。
