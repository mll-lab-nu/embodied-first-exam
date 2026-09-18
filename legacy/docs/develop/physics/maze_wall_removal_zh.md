# Maze Wall Removal 开发记录

## 目标语义

`maze_wall_removal` 是一个 connectivity restoration 任务：

- 场景是 cell grid，wall block 放在相邻 cell 的 edge gap 上。
- 初始时 A/B 两个 cell 之间不连通，且至少一堵墙挡住通路。
- 高层动作是选择一条 edge，把该 edge 上的 wall block 移走。
- 成功条件是 A/B 在未被 wall 阻断的 cell 邻接图中重新连通。
- oracle 是 A 到 B 的最小 wall-cost path；需要移走的墙数等于 0-1 BFS 的最小代价。

## 当前落地文件

- `topogym/tasks/legacy/maze_wall_removal.py`
  - `MazeWallRemovalLayout`
  - `MazeGraphSolver`
  - `MazeWallGenerator`
  - `MazeWallRemovalPuzzleState`
  - `MazeWallRemovalPuzzleEvaluator`
  - `MazeWallRemovalSceneBuilder`
- `topogym/envs/maze_wall_removal_mdp.py`
  - `MazeWallRemovalHighLevelEnv`
  - `MazeWallRemovalRewardWeights`
- `configs/task_configs/maze_wall_removal.yaml`
- `prototypes/maze_wall_removal_demo.py`

## 生成器

当前 sampler 先用 randomized DFS 生成 perfect-maze 风格的 open-edge spanning tree，再在 A/B 的 tree path 上强制关闭若干 edge，最后按 `wall_density` 调整 decoy walls。

当前 smoke 版几何先用 4x4 grid，maze 整体比第一版更靠工作台远端，避免 Franka 为了接近近端墙块出现夸张旋转。
默认布局中心约在 `x=0.665`，cell 从早期 `46 mm` 放大到 `70 mm`，gap 从 `18 mm`
放大到 `40 mm`，wall block 当前为 `56 x 16 x 26 mm`。
这版不再让 wall 长度等于 cell 边长，而是故意在 wall 两端留下约 `7 mm` 端部余量；
同时 `40 mm` gap 配合 `16 mm` 墙厚，给夹爪单侧手指留下约 `12 mm` 侧向余量，减少下探时扰动相邻 wall blocks。
wall block 采用以下几何约束：

- `wall_block.size[0] < grid.cell_size[0]`
- `wall_block.size[1] < grid.cell_gap`
- `edge_slots.length_padding == 0`
- `jitter_xy == jitter_yaw == 0`

场景只实例化初始 maze 中真实存在的 blocking wall blocks；不会像 OneStroke 那样在棋盘外额外摆 supply walls。
`edge_slots` 默认既不渲染也不创建碰撞体，因此 viewer 中不会再看到 gap 之间的浅灰凹槽，也不会留下隐藏承托体。
`discard` 是棋盘右侧的逻辑长条区域，默认不可见；其 x 方向长度与棋盘一致。移除后的 wall block
应该落到该区域，而不是堆到 maze cell 上。

采样约束：

- `wall_density`
- `min_manhattan_distance / max_manhattan_distance`
- `min_required_removals / max_required_removals`
- `turn_bias`
- `max_straight_run`

每个候选样本都会用 `MazeGraphSolver.min_wall_path` 复核：

- A/B 初始必须不连通。
- 最优移除墙数必须在配置范围内。
- 长直墙段不能超过 `max_straight_run`。

## 高层 MDP

动作：

```text
action = edge_index
```

观测：

```text
active_wall_mask[E] + A_onehot[R*C] + B_onehot[R*C] + [current_min / optimal, removed / E]
```

终态：

```text
terminal=True iff A/B connected and no invalid/duplicate wall state
```

奖励项：

- `success`
- `progress`
- `remove`
- `excess`
- `invalid`
- `step`

## Viewer 命令

只检查建模：

```bash
python -m prototypes.maze_wall_removal_demo --viewer --keep-open --seed 11 --verbose
```

运行 oracle 搬走最优墙集合并录制：

```bash
python -m prototypes.maze_wall_removal_demo --solve-oracle --record-video runs/demo_maze_wall_removal_solve.mp4 --record-fps 60 --record-camera oblique --record-res 960 960 --verbose
```
