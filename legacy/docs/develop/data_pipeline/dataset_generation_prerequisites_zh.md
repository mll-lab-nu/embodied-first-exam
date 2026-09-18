# 数据集生成 · 逐任务前置件核对表

> 日期：2026-07-18
> 目的：在开始正式录数据（路线图 W3/W4，见 `robomme_pipeline_roadmap_zh.md`）之前，逐任务核对"这个任务能不能被拿来生成 RoboMME 式数据集"。
> 结论先行：**唯一普遍缺的前置件是 W1 的 split 登记（便宜）**；MDP 不是前置件；真正的逐任务风险差异在 PBD 稳定性（cable/peeling）和成功信号是否统一（untangle/cable）。

---

## 1. RoboMME 一个任务需要哪些前置件（据 robomme.github.io + `robomme_benchmark_deliverables_zh.md`）

RoboMME 的 demo 是**脚本化 oracle planner 在环境里跑出来录的**（不是 RL）。所以一个任务要能产数据，需要：

1. **任务类**：场景 + 资产 + 按 seed 随机化 + 成功判定，内聚一处。
2. **固定 episode split**：train/val/test 的 seed 列表（每任务约 50 条）。
3. **环境接口**：obs（相机 rgb + 本体）、action（末端/waypoint 等）、status 信号。
4. **oracle 子目标 planner**：产生逐帧 grounded subgoal，脚本化生成 demo（`subgoal_planner_func.py`）。
5. **多相机录制**：front（sim）+ wrist/肩视角。
6. **成功判定**：明确的完成条件，落到 status。

**注意：RL 的并行环境是 planned，IL 数据这条线不依赖它。** —— 即 **MDP / reward 环境不是录 IL 数据的前置件。**

---

## 2. 映射到 TopoGym：一个任务"可录数据"的前置清单

| # | 前置件 | 对应 TopoGym 代码 | 说明 |
| --- | --- | --- | --- |
| 1 | 生成器（seed→EpisodeSpec） | `topogym/generation/<task>_generator.py` | 迁移过的 7 个任务都有 |
| 2 | oracle planner（EpisodePlan：subgoals+waypoints） | `topogym/planning/<task>_planner.py` | 迁移过的 7 个都有；这就是 RoboMME 花力气造的 grounded subgoal |
| 3 | SceneBuilder | `topogym/tasks/<task>.py` | 7 个都有 |
| 4 | 物理 demo（跑 plan、产 EpisodeResult） | `demos/<类别>/<task>_physical_*_demo.py` | oracle rollout，= RoboMME 的脚本化采集范式 |
| 5 | 成功/status 判定 | `*PuzzleEvaluator` 或 supervision/demo 级检查 | **不统一**：部分是 Evaluator 类，部分在 demo/supervision 里 |
| 6 | 相机（front/wrist rgb） | `configs/env_configs/world_tabletop_v1.yaml` 的 `cameras` | env 层共享：`base_camera(256)`、`oblique(512)`、`topdown`、`front`、`wrist` —— 全任务共用 |
| 7 | split 登记（点名寻址） | `configs/episode_splits/<task>.yaml` + `episode_index.py` 路由表 | **目前只有 swap**（W1） |
| — | ~~MDP / reward 环境~~ | `topogym/envs/<task>_mdp.py` | **不是前置件**，只服务 RL；列此仅为澄清 |

---

## 3. 逐任务现状

图例：✅ 就绪 · ⚠️ 就绪但有注意点 · ⬜ 缺（需补）

| 任务 | 1 生成器 | 2 planner | 3 scene | 4 demo→Result | 5 成功判定 | 6 相机 | 7 split | PBD 风险 | 净差距 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **swap** | ✅ | ✅ | ✅ | ✅ | ✅ `SwapPuzzleEvaluator` | ✅ | ✅ 已登记 | 无（刚体） | **无 —— 完全就绪** |
| **maze_wall_removal** | ✅ | ✅ | ✅ | ✅ | ✅ `MazeWallRemovalPuzzleEvaluator` | ✅ | ⬜ | 无 | 只差 split 登记 |
| **onestroke** | ✅ | ✅ | ✅ | ✅ | ✅ `OneStrokePuzzleEvaluator` | ✅ | ⬜ | 无 | 只差 split 登记 |
| **stacked_plate** | ✅ | ✅ | ✅ | ✅ | ✅ `StackedPlatePuzzleEvaluator` | ✅ | ⬜ | 无（刚体） | 只差 split；另在 sim 内调参中 |
| **untangle** | ✅ | ✅ | ✅ | ✅ | ⚠️ 无 Evaluator 类，连接器/demo 级判定 | ✅ | ⬜ | PBD 绳（中） | split + 成功信号未统一成 Evaluator |
| **peeling** | ✅ | ✅ | ✅ | ⚠️ 确认主 demo（`peeling_physical_single_demo.py`）产 Result | ✅ `PeelingPuzzleEvaluator` | ✅ | ⬜ | PBD 布（高） | split + 确认主 demo + PBD 稳定性 |
| **cable_routing** | ✅ | ✅ | ✅ | ✅ `cable_routing_physical_handle_demo` | ⚠️ supervision 级 `print_routing_verification` | ✅ | ⬜ | PBD 绳（最高，flyout） | split + 成功信号未统一 + PBD 稳定性 |

---

## 4. 读表结论

1. **对绝大多数任务，"可录数据"的唯一净差距就是 W1 的 split 登记**（加一个 `<task>.yaml` + `episode_index.py` 路由表加一行）—— 便宜，且和录制器 W3 解耦，可以随时补。
2. **MDP 是个红鲱鱼**：只有 4 个任务有 `*_mdp.py`，但录 IL 数据不需要它。别因为 stacked_plate/cable_routing/peeling 没 MDP 就以为它们不能录。
3. **真正的逐任务风险差异有两类**，都不是"缺前置"而是"质量"：
   - **PBD 稳定性**：cable_routing（最高，flyout 见 [[cable-routing-flyout-experiment]]）、peeling（布）、untangle（绳）。这三个即使前置齐全，成功率也可能不稳——所以路线图选 **swap 先验机**。
   - **成功信号不统一**：untangle / cable_routing 的成功判定散在 demo/supervision 里，不是 `*PuzzleEvaluator` 类。录数据时 status 仍能产出（demo 已经在算），但将来若要统一评测，值得把这些判定收敛成 Evaluator。

## 5. 对录制顺序的建议

```
swap            ← 完全就绪，W3/W4 在它身上验机（路线图既定）
maze / onestroke / stacked_plate  ← 补个 split 就能录（纯刚体，低风险）
untangle        ← 补 split；PBD 绳，中风险
cable_routing / peeling  ← 补 split；PBD 最高风险，放最后（等物理调稳）
```

即：**W3 录制器先在 swap 上做对，然后"补 split → 录"可以按刚体→PBD 的风险梯度逐个任务铺开**，不必等所有任务都稳定。
