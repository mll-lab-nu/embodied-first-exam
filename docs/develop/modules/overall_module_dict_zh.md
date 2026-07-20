# TopoGym Overall Module Dict

本文是当前代码架构的总字典，用尽量简单的语言说明每个模块负责什么、名字是什么意思，以及后续拆分 prototype 时应该把逻辑放到哪里。

## 一句话总览

TopoGym 的稳定环境系统可以理解为：

```text
generation 生成一局任务
world/tasks 把它搭成 Genesis 场景
planning 规划这局要做什么
primitives/robot 把计划变成物理动作
supervision 监控是否进入危险状态
runtime 串起一次完整 episode
utils/prototypes 负责展示、录制和临时实验
```

## 当前模块字典

| 模块 | 中文含义 | 主要职责 | 不应该承担的职责 |
| --- | --- | --- | --- |
| `topogym/core` | 核心小工具 | 配置加载、实体 manifest 等跨模块小对象 | 任务逻辑、运动规划、物理执行 |
| `topogym/world` | 通用物理世界 | 标准桌面、机器人底座、相机、坐标系、通用场景 builder | 根据 seed 随机生成任务；判断任务是否成功 |
| `topogym/tasks` | 任务资产与任务状态 | 每个任务的棋盘、方块、绳子、桩、目标区域、task layout、success checker | CLI 参数、视频录制、长流程运行控制 |
| `topogym/generation` | 环境/任务变式生成 | 把 `task_id + preset_id + seed + variant_id` 变成可复现的 `EpisodeSpec`、`TaskVariant`、`TaskLayout` | 直接操作 Genesis entity；驱动机械臂运动 |
| `topogym/planning` | 任务规划 | 把 layout/state 转成高层 subgoal 和 waypoint，例如“拿第几个 wall block 去哪个 gap” | 直接 step 物理引擎；处理 viewer 或录制 |
| `topogym/primitives` | 动作原语 | 抓取、放置、拖拽 handle、夹爪摩擦设置等可复用物理动作 | 决定整局任务该怎么随机化；批量 episode 管理 |
| `topogym/robot` | 机器人控制 | Franka 的 IK、夹爪开合、末端执行器移动 | 任务成功判定；任务几何生成 |
| `topogym/supervision` | 稳定性监控 | 统一检查 `follow_error`、`target_error`、`min_gap`、接触粒子数等危险信号，并返回 soft abort 决策 | 自己规划路径；自己移动机器人 |
| `topogym/runtime` | Episode 运行器 | 串起 build/reset/plan/execute/verify/export，一次跑完一个 episode | 写任务细节；把所有任务逻辑塞进一个巨型 runner |
| `topogym/utils` | 通用杂项 | HUD、录制、已有通用 helper | 新增核心架构逻辑 |
| `topogym/envs` | RL 环境壳 | 面向未来 RL/MDP 的环境接口 | demo 专用调参和长脚本 |
| `prototypes` | 临时展示入口 | CLI、viewer、recording glue、小实验 | 长期保存任务生成、规划、监督主逻辑 |
| `configs` | 配置文件 | 尺寸、颜色、物理参数、任务默认值 | 放 Python 控制流 |
| `docs` | 说明文档 | 坐标系、模块职责、调参教程、debug log | 运行时逻辑 |

## 新增代码层的命名含义

### `generation`

`generation` 的意思是“生成这一局环境的输入条件”。它不负责把场景真的建出来，而是回答：

- 这是什么任务？
- 用哪套桌面/机械臂/相机 preset？
- seed 是多少？
- 这一局随机到了什么布局？
- 这些信息如何稳定复现？

核心对象：

| 名字 | 含义 |
| --- | --- |
| `EpisodeKey` | 一局任务的稳定身份：`task_id + preset_id + seed + variant_id` |
| `ScenePreset` | 一套共享桌面、机械臂、相机、颜色、坐标系设置 |
| `TaskVariant` | seed 生成出的任务变式，例如 maze 的墙分布或 cable 的 peg 布局 |
| `TaskLayout` | 变式换算到世界坐标后的几何布局 |
| `ExecutionProfile` | 执行策略参数，例如速度、夹爪、稳定性阈值 |
| `EpisodeSpec` | 一次 episode 的完整输入 |
| `EpisodeResult` | 一次 episode 的结构化结果 |

注意：旧 demo 里常出现的 `il_ready` 以后应逐步改为更中性的 `stable_ready` 或 `export_ready`。当前阶段我们优先关心环境是否稳定可复现，而不是立刻产 IL 数据。

### `planning`

`planning` 的意思是“决定这局任务要按什么步骤完成”。它把任务布局变成更接近动作的计划，但仍然不直接控制机器人。

核心对象：

| 名字 | 含义 |
| --- | --- |
| `PlannedSubgoal` | 高层子目标，例如“移走 maze_wall_18” |
| `WaypointTarget` | 一个物理目标点，例如 handle 要经过的某个 `(x, y, z)` |
| `WaypointPlan` | 一串有顺序的 waypoint |
| `EpisodePlan` | 高层 subgoal 加 waypoint 的完整计划 |

未来迁移方向：

- onestroke：把 planned walls 从 demo 脚本迁到 planner。
- maze：把 planned removals 从 demo 脚本迁到 planner。
- cable routing：先把 YAML waypoint 包成 planner 输出，再逐步改成几何规则自动生成。

### `supervision`

`supervision` 的意思是“运行时看护”。它不是 planner，也不是 controller；它只负责发现风险。

典型输入：

- `follow_error`：被抓物体和夹爪预期位置相差多少。
- `target_error`：物体离本段 waypoint 目标还差多少。
- `min_gap`：绳子/物体和障碍物的最小间隙；负值通常表示轻微压入或穿入。
- `contact_particles`：PBD rope 与 peg 等物体接触的粒子数量。

核心对象：

| 名字 | 含义 |
| --- | --- |
| `StabilityLimits` | 一组安全阈值 |
| `StabilitySample` | 某一帧或某一段动作的测量值 |
| `StabilityDecision` | 是否继续、是否 soft abort、原因是什么 |

这个层的目标是：在 Genesis 底层 solver 被推到崩溃前，尽量提前停下来并留下可读日志。

`cable_routing` 的绕桩检查也放在这里：`topogym/supervision/cable_routing.py`
统一计算 rope/peg 接触指标、endpoint trace 是否经过目标侧、阶段性 routing
metric 打印和最终 routing verification。这样 physical demo 和 oracle demo 不再互相
导入 prototype helper。

### `runtime`

`runtime` 的意思是“把一局 episode 串起来跑”。它不应该知道每个任务的所有细节，而是用统一流程调用其他层：

```text
EpisodeSpec -> build scene -> plan -> execute primitives -> supervise -> verify -> EpisodeResult
```

核心对象：

| 名字 | 含义 |
| --- | --- |
| `EpisodeRunOptions` | viewer、record video、verbose 等展示选项 |
| `EpisodeRunContext` | spec + plan + options 的组合 |
| `EpisodeRunner` | 任务 runner 需要实现的最小接口 |

## 文件命名规则

后续新增文件尽量使用下面的后缀：

| 后缀 | 用途 |
| --- | --- |
| `*_builder.py` | 把 spec/layout 搭成 Genesis scene |
| `*_generator.py` | seed 到 variant/layout/spec |
| `*_planner.py` | layout/state 到 subgoal/waypoint |
| `*_executor.py` | plan 到 robot/primitives |
| `*_monitor.py` | runtime safety checks |
| `*_verifier.py` | success / physical sanity checks |
| `*_runner.py` | 一次 episode 的完整流程 |
| `*_demo.py` | CLI/viewer/recording 展示入口 |

## Prototype 之后应该变薄成什么样

现在很多 prototype 文件同时做配置覆盖、场景创建、路径规划、安全检查、录制和结果判断。后续应该逐步变成：

```python
args = parse_args()
spec = generator.from_args(args)
plan = planner.plan(spec)
runner = TaskEpisodeRunner(...)
result = runner.run(EpisodeRunContext(spec=spec, plan=plan, options=options))
print(result)
```

也就是说，prototype 可以继续存在，但它应该像“门牌号”，而不是把整栋楼都塞在门牌里。

## 第一轮整改已经落地的代码入口

本轮新增了这些纯 Python 架构层：

```text
topogym/generation/
topogym/planning/
topogym/supervision/
topogym/runtime/
```

这些模块暂时不 import Genesis，因此不会改变现有 demo 的物理行为。下一步可以从最臃肿、最脆弱的 `prototypes/cable_routing_physical_handle_demo.py` 开始，把 waypoint 生成和 safety monitor 迁到新层。

## 迁移顺序：先 Swap，再扩展

所有任务最终都应该迁到这套分层里，但不应该一次性把全部 prototype 大改。推荐顺序是：

1. `swap`：刚体 pick-and-place，逻辑最短，适合作为新架构样板。
2. `onestroke` / `maze`：仍然是刚体 wall block，但规划步骤更多，可以验证 planner 是否能表达多步任务。
3. `stacked_plate` / `peeling`：有特殊机构或任务约束，需要更细的 verifier 和 execution profile。
4. `untangle` / `cable_routing`：涉及 PBD rope，是最高风险任务，应在前面任务验证好分层后再迁移。

当前 `swap` 已经完成第一步试点：

```text
topogym/generation/swap_generator.py  # 生成 Swap EpisodeSpec
topogym/planning/swap_planner.py      # 生成 Swap pick-place EpisodePlan
prototypes/swap_physical_grasp_demo.py # 仍是 CLI，但开始消费 spec/plan/result
```

`onestroke` 也已经完成刚体多步任务的第一轮迁移：

```text
topogym/generation/onestroke_generator.py      # 生成 OneStroke EpisodeSpec
topogym/planning/onestroke_wall_planner.py     # 生成完整 separator wall sequence
prototypes/onestroke_physical_wall_demo.py     # 消费 spec/plan/result，保留原物理执行
```

这一步的标准是：旧 demo 的物理行为基本不变，但日志中已经能看到稳定的 `episode_id`、`plan_id`、`stable_ready` 和 `export_ready`。后续其他任务应该按照这个模板逐步迁移，而不是在各自 prototype 里继续堆长逻辑。
## 当前迁移状态补充

`maze_wall_removal` 已按和 `swap`、`onestroke` 相同的模式完成第一轮迁移：

```text
topogym/generation/maze_wall_removal_generator.py  # 生成 Maze Wall Removal EpisodeSpec
topogym/planning/maze_wall_removal_planner.py      # 将 sampled oracle_edges 包装成移除命令序列
prototypes/maze_wall_removal_physical_demo.py      # 消费 spec/plan/result，保留原物理抓取和移除执行
```

这一阶段的标准仍然是：旧 demo 的物理行为基本不变，但日志中能看到稳定的
`episode_id`、`plan_id`、`stable_ready` 和 `export_ready`，方便之后把
prototype 继续变薄。

`stacked_plate` 已按同一模式完成第一轮迁移：

```text
topogym/generation/stacked_plate_generator.py  # 生成 Stacked Plate EpisodeSpec
topogym/planning/stacked_plate_planner.py      # 将 oracle angle 包装成接触旋转命令
prototypes/stacked_plate_physical_rotate_demo.py # 消费 spec/plan/result，保留原接触旋转执行
```

这个任务和普通 pick-and-place 不同：planner 输出的是“推动某层圆盘绕 revolute
joint 旋转”的高层命令，而不是搬运物体的命令。物理接触、摩擦和 release drift
检查仍然留在 demo/primitive 执行层。

`untangle` 已开始按同一模式迁移到 PBD rope 任务：

```text
topogym/generation/untangle_generator.py  # 生成 Untangle EpisodeSpec
topogym/planning/untangle_planner.py      # 根据当前拓扑选择下一次 endpoint relocation
prototypes/untangle_physical_handle_demo.py # 消费 spec/plan/result，保留原 PBD handle drag 执行
```

这里的 planner 是动态的：每完成一次端点搬运后，先更新高层 topology state，
再规划下一次移动。demo 不再自己决定“移动哪根绳子的哪个端点到哪个 hole”，
只负责把 planner 给出的 endpoint move 交给物理 primitive 执行，并把
`task_success` 与 `physical_success` 分开写入 `EpisodeResult`。

`peeling` 的单膜物理任务已按同一模式完成第一轮迁移。这里现在分两条线：
PBD cloth 版本保留为研究线，用来探索真实柔性揭起；刚体 suction 版本作为现阶段
更稳定的环境生成 baseline，用刚体方形贴片和接触后吸附来表达“触碰、搬运、放置”：

```text
topogym/generation/peeling_generator.py     # 生成 Peeling EpisodeSpec
topogym/planning/peeling_planner.py         # PBD cloth 版本的 flap/粘附分组 waypoint 计划
prototypes/peeling_physical_single_demo.py  # PBD cloth 研究线，保留角起-搬运-放置执行
prototypes/peeling_rigid_patch_suction_demo.py # 刚体 suction 稳定线，接触后自动吸附并搬运贴片
```

`cable_routing` 也已按同一模式完成第一轮迁移，并顺带解决了两处重复实现：
之前自由端 waypoint 的几何计算（绕 peg 缠绕、front-pull、transition 走廊等）
整段写在 `cable_routing_oracle_demo.py` 里，`cable_routing_physical_handle_demo.py`
靠 prototype 互相导入才能复用。这一轮把 waypoint 生成搬进了
`planning/cable_routing_planner.py`，又把 rope/peg 接触检查、routing verification
搬进了 `supervision/cable_routing.py`，两个 demo 现在都从正式模块导入：

```text
topogym/generation/cable_routing_generator.py  # 生成 Cable Routing EpisodeSpec
topogym/planning/cable_routing_planner.py       # 把 target_signature 解析成自由端 drag 的 waypoint 计划（原先在 oracle demo 里的几何函数搬到这里）
topogym/supervision/cable_routing.py            # rope/peg wrap 指标、阶段验证和最终 routing verification
prototypes/cable_routing_physical_handle_demo.py # 消费 spec/plan/result，保留原 PBD handle drag 执行
prototypes/cable_routing_oracle_demo.py          # 改为从 planning/supervision 导入共享 helper，行为不变
```

至此 `overall_module_dict_zh.md` 里“先 Swap，再扩展”迁移顺序列出的全部任务
（`swap` / `onestroke` / `maze_wall_removal` / `stacked_plate` / `untangle` /
`cable_routing` / `peeling`）都已完成第一轮迁移；同一任务下的其它 baseline/
变体 demo（tabletop baseline、oracle-only、其它交互手法等）还没有跟上，见
`module_prototypes.md` 的迁移状态表。
