# `demos/` — 展示入口与迁移状态

每个 `*_demo.py` 是一种任务的一种展示方式（physical execution / inspect / 特定后端对照等）。
目录分类与 `topogym/tasks/` 对齐，文件清单见 [`../../../demos/README.md`](../../../demos/README.md)，
这里不重复。本文只记录两项状态：是否消费 `generation`/`planning`/`runtime` 架构，
以及是否已迁到 Hydra。

2026-08-10 由平铺的 `prototypes/` 改为按类别分目录，同一次把参数体系从 argparse
迁到 Hydra 并删除 argparse 那一套。

## 主线 demo

全部消费 `generation` + `planning`（日志里可见 `episode_id` / `plan_id`），
全部使用 Hydra（`@hydra.main` + `configs/<demo>.yaml`）。

| 类别 | 任务 | Demo 文件 |
| --- | --- | --- |
| `entangle/` | untangle_continuous | `untangle_continuous_physical_pinch_demo.py`、`untangle_continuous_fem_demo.py`、`untangle_continuous_inspect_demo.py` |
| `entangle/` | untangle（离散版） | `untangle_physical_handle_demo.py` |
| `connectivity/` | stacked_plate | `stacked_plate_physical_rotate_demo.py`、`stacked_plate_inspect_demo.py` |
| `routing/` | cable_routing | `cable_routing_physical_handle_demo.py` |
| `routing/` | bar_through_hole | `bar_through_hole_physical_insert_demo.py` |

## 已删除的 legacy demo

2026-08-10 删除 `demos/legacy/` 下的 5 个文件（swap / onestroke / maze_wall_removal /
peeling 各一个 physical demo，加录制批处理 `record_physical_demos.py`，共 2242 行、
102 个 argparse 参数）。它们是 argparse 配置体系仅剩的使用者，而这四个任务已不在主线范围。

任务代码 `topogym/tasks/legacy/` 保留 —— `topogym/envs/` 下三个 RL 环境壳还在 import。

## 参数语法

只剩一套：Hydra 配置点路径。`bash_scripts/tests/` 与 `bash_scripts/recordings/` 下的
脚本直接写 `run.seed=0`、`env.genesis.backend=gpu` 这样的覆盖。
此前为翻译两套语法而设的 `bash_scripts/lib/demo_cli.sh` 已随之删除。

参数体系本身的盘点与迁移记录见
[`../framework/demo_cli_and_config_zh.md`](../framework/demo_cli_and_config_zh.md)。
