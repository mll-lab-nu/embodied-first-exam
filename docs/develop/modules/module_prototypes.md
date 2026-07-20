# `prototypes/` — 展示入口与迁移状态

每个 `*_demo.py` 是一种任务的一种展示方式（tabletop baseline / physical execution / oracle / 特定交互手法等）。这里只记录"是否已经消费 `generation`/`planning`/`runtime` 新架构"，不重复描述每个 demo 的内容。

## 已接入新架构（`generation` + `planning`，部分还接了 `runtime`）

| 任务 | Demo 文件 |
| --- | --- |
| Swap | `swap_physical_grasp_demo.py` |
| One-Stroke | `onestroke_physical_wall_demo.py` |
| Maze Wall Removal | `maze_wall_removal_physical_demo.py` |
| Stacked Plate | `stacked_plate_physical_rotate_demo.py` |
| Untangle | `untangle_physical_handle_demo.py` |
| Peeling | `peeling_physical_single_demo.py`（PBD cloth 研究线）；`peeling_rigid_patch_suction_demo.py`（刚体贴片稳定线，复用 `generation/peeling_generator.py` 的 episode/result 命名） |
| Cable Routing | `cable_routing_physical_handle_demo.py`（新增 `generation/cable_routing_generator.py` + `planning/cable_routing_planner.py`；自由端 waypoint 几何计算已搬到 planner，rope/peg routing 指标和 verification 已搬到 `supervision/cable_routing.py`） |

这几个 demo 的物理行为和迁移前基本一致，但日志里能看到稳定的 `episode_id` / `plan_id` / `stable_ready` / `export_ready`（细节见 `../overall_module_dict_zh.md`）。

## 尚未接入新架构

**Cable Routing 的另外两个 demo 还没有跟上（`cable_routing_physical_handle_demo.py` 已迁移，见上表）：**

| 任务 | Demo 文件 |
| --- | --- |
| Cable Routing | `cable_routing_oracle_demo.py`（符号/kinematic oracle 演示，已经从 `planning.cable_routing_planner` 和 `supervision.cable_routing` 导入共享 helper，但还没有自己的 `EpisodeSpec`/`EpisodePlan` 调用）、`cable_routing_tabletop_baseline_demo.py` |

**Peeling 的另外一个 demo 还没有跟上（`peeling_physical_single_demo.py` 和 `peeling_rigid_patch_suction_demo.py` 已迁移，见上表）：**

| 任务 | Demo 文件 |
| --- | --- |
| Peeling | `peeling_oracle_demo.py`（多层 film 的符号层 oracle 演示，用的是 `peeling.py` 而不是 `peeling_physical.py`，还没有对应 generator/planner） |

`overall_module_dict_zh.md` 里的"迁移顺序"章节把 cable_routing / peeling 排在最后（因为涉及 PBD 绳/布，风险最高）；两个任务的主力物理 demo 现在都已经完成第一轮迁移。

**已迁移任务的其它 baseline/变体 demo，还没有跟着各自任务的 physical demo 一起接入：**

- Swap: `swap_empty_slot_demo.py`、`swap_tabletop_baseline_demo.py`
- One-Stroke: `onestroke_tabletop_baseline_demo.py`、`onestroke_wall_place_demo.py`
- Maze Wall Removal: `maze_wall_removal_demo.py`、`maze_wall_removal_tabletop_baseline_demo.py`
- Untangle: `untangle_robot_drag_demo.py`、`untangle_rope_drag_demo.py`、`untangle_tabletop_baseline_demo.py`

这些理论上可以直接复用同任务 physical demo 里已经写好的 `generator`/`planner` 调用方式，工作量应该比 cable_routing/peeling 小。

其余：`basic_env_demo.py`、`common_task_demo.py`、`knot_pbd_viewer_probe.py`、`record_physical_demos.py` 是跨任务的通用小工具/探针，不属于某一个具体任务的迁移范围。
