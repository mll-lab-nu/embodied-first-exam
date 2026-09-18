# TopoGym 模块说明入口

这份目录以 `overall_module_dict_zh.md` 作为总入口和权威说法。`overall_module_dict_zh.md` 里已经有深入说明的模块（`generation` / `planning` / `supervision` / `runtime`）不在这里重复；其余每个实际代码模块各有一份简单说明：

| 文件 | 对应代码模块 |
| --- | --- |
| `module_core.md` | `topogym/core` |
| `module_world.md` | `topogym/world` |
| `module_tasks.md` | `topogym/tasks` |
| `module_primitives.md` | `topogym/primitives` |
| `module_robot.md` | `topogym/robot` |
| `module_utils.md` | `topogym/utils` |
| `module_envs.md` | `topogym/envs` |
| `module_demos.md` | `demos/`（含各任务迁移状态） |

推荐阅读顺序：

1. `overall_module_dict_zh.md`：先看每个代码模块负责什么，以及命名为什么这样定。
2. 上表里对应你关心的模块的 `module_*.md`：简单版说明 + 关键文件/对象。
3. `../stable_il_generation_system_devlog_zh.md`：看这次架构整改背后的动机和第二阶段计划。
4. `legacy_ag_blueprint/`：早期 A-G 系统蓝图草案，**和当前代码模块不是一一对应关系**，只在需要了解"设想中的在线 RL/离线数据/评测全流程"时再看，理解当前代码请以本目录其它文件为准（详见该子目录的 `README.md`）。

当前整改重点不是立刻生成 IL 数据，而是把"稳定、可复现、可按 seed 生成变式"的环境生成系统搭起来。Viewer、录制视频、未来 IL/RL 都应该只是这套系统的下游入口。

## 任务迁移到新架构的状态

已完成第一轮迁移（有 `generation` + `planning`，物理 demo 已切换消费 spec/plan/result）：

- `swap`、`onestroke`、`maze_wall_removal`、`stacked_plate`、`untangle`、`peeling`（`peeling_physical_single_demo.py`）、`cable_routing`（`cable_routing_physical_handle_demo.py`）

`cable_routing` 和 `peeling` 涉及 PBD 绳/布，是 `overall_module_dict_zh.md` 迁移顺序里排最后、风险最高的一档；两个任务各自的主力物理 demo 现在都已完成第一轮迁移，但同任务下的其它 demo（oracle / tabletop baseline / 其它交互手法）还没跟上，见 `module_demos.md`。另外 `topogym/envs` 下的 RL 环境壳目前只覆盖 `swap`/`onestroke`/`maze_wall_removal`/`untangle`，`stacked_plate`/`cable_routing`/`peeling` 还没有对应的 `*_mdp.py`，细节见 `module_envs.md`。
