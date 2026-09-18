# `topogym/tasks` — 任务资产与场景构建

每个任务一个文件，负责"这局任务长什么样"，不碰 CLI、录制、长流程控制，也**不判成功**
（判定在 `topogym/verification/`，见 [`../framework/module_boundaries_zh.md`](../framework/module_boundaries_zh.md)）。

## 目录结构

任务模块放在以能力类别命名的子包里，路径即分类；类别定义见
[`../framework/task_taxonomy_zh.md`](../framework/task_taxonomy_zh.md)。这是唯一按类别分子目录的层，
`verification/` `planning/` `generation/` `supervision/` `envs/` `prototypes/` 均保持平铺。

```text
topogym/tasks/
├── __init__.py          # 把各任务的公开名平铺 re-export（调用方不感知类别）
├── _visuals.py          # 跨任务共享的 box_entity_enabled
├── deformation/         # 类别 1：形状与自身层叠 —— 尚无实现
├── routing/             # 类别 2：路径与围绕
├── entangle/            # 类别 3：缠绕与互锁
├── connectivity/        # 类别 4：连接与可达性
└── legacy/              # 四分类之前的任务，见该目录 README.md
```

`topogym/core/taxonomy.py` 的 `CATEGORIES` 表镜像这个布局，供 bash/工具链在不 import Genesis 的
前提下查类别；`python topogym/core/taxonomy.py` 校验表与目录一致，不一致时非零退出。

## 任务清单

| 类别 | 任务 | 文件 | 主要类型 |
| --- | --- | --- | --- |
| `routing` | Cable Routing | `routing/cable_routing.py` | `CableRoutingLayout` / `CableRoutingScene(Builder)` / `CableRoutingSignature` |
| `entangle` | Untangle（离散版） | `entangle/untangle.py` | `UntangleLayout` / `UntangleScene(Builder)` / `RopeEndpointHandle`（PBD 绳子） |
| `entangle` | Untangle（连续版） | `entangle/untangle_continuous.py` | `UntangleContinuousLayout` / `UntangleContinuousScene(Builder)` / `settle_scene` |
| `entangle` | Band Untwist（docx 3.3，开口绳桌面版；四种出生形态、交叉 1–2 个） | `entangle/band_untwist.py`（8 字几何在 `entangle/_figure_eight_geometry.py`，6 字 / 麻花 / O\|-\|O 在 `entangle/_band_shapes.py`，oracle 的直线模型在 `planning/band_untwist_sequence.py`） | `BandUntwistLayout` / `BandUntwistScene(Builder)`；`settle_scene` 复用连续版 |
| `connectivity` | Stacked Plate | `connectivity/stacked_plate.py` | `StackedPlateLayout` / `StackedPlateScene(Builder)`，另有 `sync_stacked_plate_physics` / `apply_stacked_plate_visuals` |
| `deformation` | —— | —— | 尚无实现；候选任务见 `TopoGym_tasks.docx` 第 1 节 |
| `legacy` | Swap | `legacy/swap.py` | `SwapLayout` / `SwapScene(Builder)` / `SwapOraclePlan` |
| `legacy` | One-Stroke | `legacy/onestroke.py` | `OneStrokeLayout` / `OneStrokeScene(Builder)` |
| `legacy` | Maze Wall Removal | `legacy/maze_wall_removal.py` | 额外带 `MazeGraphSolver` / `MazeWallGenerator`（迷宫图论 + 随机生成墙体） |
| `legacy` | Peeling（符号层） | `legacy/peeling.py` | `PeelingLayout` / `PeelingScene(Builder)` / `apply_peel_zone_markers` |
| `legacy` | Peeling（物理执行层 / PBD 研究线） | `legacy/peeling_physical.py` | `PeelingPhysicalScene(Builder)` / `PeelingKinematicSheetDriver`，管 PBD cloth 角起与撕揭动作 |

每个任务遵循同一套命名：`XxxLayout`（这局的几何布局）→ `XxxScene` / `XxxSceneBuilder`
（在 `world` 的桌面基座上把 layout 搭成 Genesis 场景）。对应的 `XxxPuzzleState` /
`XxxPuzzleEvaluator` 住在 `topogym/verification/<task>_verifier.py`。

## import 约定

调用方走包级 re-export，不写类别段：

```python
from topogym.tasks import StackedPlateSceneBuilder     # 推荐：任务改类别时不受影响
```

只有 `verification/` 的 7 个 verifier 与 `envs/maze_wall_removal_mdp.py` 走深层 import
（它们需要具体的 Scene/Layout 类型做标注）：

```python
from topogym.tasks.connectivity.stacked_plate import StackedPlateScene
```

**不负责**：CLI 参数解析、视频录制、长流程运行控制（`prototypes` / `runtime` 的事），以及成功判定
（`verification` 的事）。
