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

模型接入的拟议拆分见 [独立模型服务与 Prompt 设计草案](model_service_design_zh.md)，包含 Astra 配置、输入预览和单轮调用方案；新增模块尚未实现。

当前可执行步骤见 [Agent rollout 实用手册](agent_rollout_usage_zh.md)：Linux 环境检查、无 API key 的 Cast Coil SDK smoke、API 配置、短评测、预算监测与共享变体重复评测。

Reviewer 意见的解析见 [目标 agent rollout pipeline 与当前实现差距](agent_rollout_target_gap_review_zh.md)：
区分 RGB 与 simulator access，定义固定初态 reset、trial/episode 与累计预算，比较 Harbor / RoboWits 参考方式和实施优先级。

开锁当前使用的 `runner`、`planner`、`certificate`、`grasp`、`oracle`、`evaluator`、`review`
全部由 `topogym/tasks/lock_picking/` 持有，避免当前入口依赖历史 demo。

Agent 接入采用[公共会话 / 机器人 adapter / 任务判定三层](agent_adapter_architecture_zh.md)。
[Cast Keyhole](cast_keyhole_agent_adapter_zh.md) 与 Horseshoe 共用 ALOHA 控制及接触辅助。
[Interlocked Claws](interlocked_claws_agent_adapter_zh.md) 基础实例复用同一 ALOHA adapter，保留双件分离、支架承载和释放静置判定。
[Hedgehog in Cage](hedgehog_agent_adapter_zh.md) 通过 Panda 单臂端口复用同一刚体执行循环，提供本地创建命令和可复制的 solver prompt。
[Lock Picking](lock_picking_agent_adapter_zh.md) 复用相同 Panda 端口，从承托架自由钥匙开始，保留被动锁片和 END 释放判定。
[Buzz Wire 3D](buzz_wire_agent_adapter_zh.md) 复用 Panda 和公共刚体执行循环，保留基础实例真实摩擦抓持、三路观测、连续穿环与末端释放静置判定；已完成短程协议验证。
包入口只导出当前通用契约，不再集中导入旧任务。

[Knot Untying](knot_untying_agent_adapter_zh.md) 新增 FEM 公共执行层，复用四路 ALOHA 观测与本地协议；需要 CUDA/IPC，验证状态见接入文档。

旧模块说明和早期 A–G 蓝图见 [历史模块文档](../../../legacy/docs/develop/modules/)。
