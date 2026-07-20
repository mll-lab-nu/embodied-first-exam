# `topogym/tasks` — 任务资产与任务状态

每个任务一个文件，负责"这局任务长什么样、算不算成功"，不碰 CLI、录制、长流程控制。

| 任务 | 文件 | 备注 |
| --- | --- | --- |
| Swap | `swap.py` | `SwapLayout` / `SwapScene(Builder)` / `SwapPuzzleEvaluator` / `SwapSuccessChecker` / `SwapOraclePlan` |
| One-Stroke | `onestroke.py` | `OneStrokeLayout` / `OneStrokeScene(Builder)` / `OneStrokePuzzleEvaluator` |
| Maze Wall Removal | `maze_wall_removal.py` | 额外带 `MazeGraphSolver` / `MazeWallGenerator`（迷宫图论 + 随机生成墙体） |
| Stacked Plate | `stacked_plate.py` | `StackedPlateLayout` / `StackedPlateScene(Builder)` / `StackedPlatePuzzleEvaluator`，另有物理同步 helper `sync_stacked_plate_physics` |
| Untangle | `untangle.py` | `UntangleLayout` / `UntangleScene(Builder)` / `RopeEndpointHandle`（PBD 绳子任务） |
| Cable Routing | `cable_routing.py` | `CableRoutingLayout` / `CableRoutingScene(Builder)` / `CableRoutingSignature` |
| Peeling（符号层） | `peeling.py` | `PeelingLayout` / `PeelingScene(Builder)` / `PeelingPuzzleEvaluator` |
| Peeling（物理执行层/PBD 研究线） | `peeling_physical.py` | `PeelingPhysicalScene(Builder)` / `PeelingKinematicSheetDriver` / `PeelingPhysicalEvaluator`，专门管 PBD cloth 角起和撕揭动作；现阶段稳定 baseline 优先使用刚体 suction demo |

每个任务基本都遵循同一套命名：`XxxLayout`（这局的几何布局）→ `XxxScene` / `XxxSceneBuilder`（在 `world` 的桌面基座上把 layout 搭成 Genesis 场景）→ `XxxPuzzleEvaluator` / `XxxSuccessChecker`（读场景状态判断进度/成功）。

**不负责**：CLI 参数解析、视频录制、长流程运行控制（那些是 `prototypes` / `runtime` 的事）。
