# 稳定环境生成系统 Dev Log

本文记录一次针对 RoboMME 稳定生成环境与 demonstrations 的方式的对照分析，并给出 TopoGym 需要落地的系统规划。

当前阶段的首要目标不是生成 IL 数据，而是建立一套稳定、可复现、可按 seed 生成随机变式的环境生成系统。IL 数据、demo 视频、viewer 观察、RL 训练都应该是这套环境系统的下游消费者。

目标不是复制 RoboMME 的任务，而是复现它背后的工程模式：标准化场景、可复现 seed、分层 planner、严格成功检查、失败过滤，以及可以批量跑的环境/episode pipeline。

## 1. 外部参考：RoboMME 做对了什么

RoboMME benchmark 仓库：

- [https://github.com/RoboMME/robomme_benchmark](https://github.com/RoboMME/robomme_benchmark)
- RouteStick 任务示例：[https://github.com/RoboMME/robomme_benchmark/blob/main/src/robomme/robomme_env/RouteStick.py](https://github.com/RoboMME/robomme_benchmark/blob/main/src/robomme/robomme_env/RouteStick.py)
- 子目标/运动规划工具：[https://github.com/RoboMME/robomme_benchmark/blob/main/src/robomme/robomme_env/utils/subgoal_planner_func.py](https://github.com/RoboMME/robomme_benchmark/blob/main/src/robomme/robomme_env/utils/subgoal_planner_func.py)

RoboMME README 里明确给出几个和我们直接相关的设计点：

- 任务共享标准桌面、机械臂、相机和 episode seed。
- 数据集是固定数量的 demonstrations，训练/验证/测试 episode 都由固定 seed 驱动。
- 动作类型不是只有底层 joint action，还包含 `ee_pose` 和 `waypoint`。
- 当前环境生成主要服务于 imitation learning，而不是一开始就追求通用并行 RL。

从代码结构看，RoboMME 的 RouteStick 不是在模拟 PBD 绳索绕桩，而是用 stick 末端、刚体物体、子目标函数和运动规划器去产生可复现的轨迹。因此它的稳定性主要来自“规划好的子目标 + motion planner + 成功过滤”，而不是依赖一个很脆弱的连续软体接触过程自然成功。

这对我们很关键：TopoGym 的 cable routing 如果坚持让 PBD rope、peg contact、connector insertion 全部自然物理涌现，就会比 RoboMME 的数据生成问题难很多，也更容易触发 Genesis 底层 solver 崩溃。

## 2. 我们当前代码的状态



### 已经具备的能力

刚体任务已经开始形成可进入 IL 的合约：

- `docs/develop/il_adaptation/collision_based_il_contract_zh.md`
- `prototypes/swap_physical_grasp_demo.py`
- `prototypes/onestroke_physical_wall_demo.py`
- `prototypes/maze_wall_removal_physical_demo.py`
- `prototypes/stacked_plate_physical_rotate_demo.py`

这些任务的优点是：对象运动主要来自 Genesis rigid collision、摩擦、重力和 Franka 控制，失败也能通过 result 行里的 success / failure reason 过滤。旧文档和旧 demo 中偶尔会出现 `il_ready` 命名，第二阶段应逐步替换为更中性的 `export_ready` 或 `stable_ready`。

PBD handle 类任务也已有基础合约：

- `docs/develop/physics/pbd_physical_handle_interaction_zh.md`
- `topogym/primitives/pbd_handle_drag.py`
- `prototypes/untangle_physical_handle_demo.py`
- `prototypes/cable_routing_physical_handle_demo.py`

核心模式是：Franka 夹住一个 rigid handle，rope endpoint particles 通过 Genesis `fix_particles_to_link` 连接到 handle。机械臂不直接 teleport rope，也不逐帧 `set_particles_pos`。

录制入口也有雏形：

- `prototypes/record_physical_demos.py`

目前它主要覆盖 `swap/onestroke/maze`，还没有变成完整的数据生成 supervisor。

### 当前最大短板

1. prototype 仍然承担太多职责。

`prototypes/cable_routing_physical_handle_demo.py` 同时做配置覆盖、场景创建、oracle waypoint 读取、夹爪执行、PBD 安全检查、connector latch、recording 和 result 判断。调 demo 可以，但不适合长期稳定采数据。

1. planner 层还不够独立。

Cable routing 的 waypoint 目前主要写在 YAML 里，属于“手工路径表”。它缺少一个独立 planner 去根据 peg/connector/rope 参数自动生成安全路径、细分动作、调整 clearance、标记危险段。

1. 失败处理还偏 demo 化。

现在会打印 `segment_follow_failed`、`wrap_contact_safety_abort`、`Segmentation fault` 前的日志，但还没有统一的 episode supervisor 来执行：

- seed 重试
- 参数扰动重试
- 分阶段保存诊断文件
- 失败 episode quarantine
- 成功 episode manifest

1. PBD rope 的真实性和稳定性存在冲突。

Cable routing 要求 rope 与 peg 有接触、绕行、滑动、终点捕获。这个任务比 untangle 更容易崩，因为一端固定，另一端被持续拖拽，且需要绕过两个刚性 peg 后插入 socket。绳子如果过紧、局部弯折过大、粒子压入 peg、handle 被夹爪拖偏，都可能把 PBD + rigid coupling 推到 Genesis 1.1.0 的不稳定区域。

## 3. 第二阶段迭代 1：稳定环境生成系统

本迭代的目标从“把一个 demo 调通”升级为“建立一个读者友好、模块清晰、可按 seed 稳定生成环境和任务变式的系统”。Demo/viewer/video 仍然保留，但它们不再承载核心逻辑，只是环境系统的展示入口。

### 3.1 本迭代目标

1. 命名清晰：读者看到文件名和类名就能判断它负责“造场景、生成任务、规划动作、执行动作、验证结果、录制展示”中的哪一层。

2. Prototype 减负：`prototypes/` 只保留 CLI、viewer、recording glue，不再长期存放任务生成、路径规划和安全检查主逻辑。

3. 环境可复现：每个 episode 由 `task_id + preset_id + seed + variant_id` 唯一确定，并且可以导出 resolved config 和 scene manifest。

4. 变式可控：随机性集中在 environment generator / task variant generator，而不是散落在 demo 脚本里。

5. 稳定性优先：PBD/rope 等高风险任务要有 preflight、runtime monitor、soft abort 和 failure report，避免把 Genesis 拖到 segfault。

6. 展示入口统一：viewer demo、recorded video、未来 IL/RL 都调用同一套 environment generator，不再各写一套场景创建逻辑。

### 3.2 推荐命名体系

当前仓库已有 `topogym/world`、`topogym/tasks`、`topogym/primitives`、`topogym/robot`、`topogym/utils`。建议在不大拆现有代码的前提下，把新系统命名为：

```text
topogym/world/          # 通用物理世界：桌面、机器人、相机、坐标系
topogym/tasks/          # 任务资产和状态：棋盘、方块、绳子、peg、目标
topogym/generation/     # 环境/任务变式生成：seed -> layout/spec/manifest
topogym/planning/       # oracle / route / subgoal planner
topogym/execution/      # 把 plan 变成机器人动作；可复用 primitives
topogym/supervision/    # 稳定性监控、soft abort、失败诊断
topogym/verification/   # task success / physical success / scene sanity
topogym/runtime/        # episode runner；viewer/video/未来训练共用
topogym/recording/      # 录制与导出；可以先复用 topogym/utils/recording.py
prototypes/             # 薄 CLI：只负责 parse args + 调 runtime
```

如果想更少改目录，第一版可以只新增四个目录：

```text
topogym/generation/
topogym/planning/
topogym/supervision/
topogym/runtime/
```

`execution` 暂时继续放在 `topogym/primitives/`，`verification` 暂时放在各 `tasks/*.py` 旁边，等接口稳定后再迁移。

### 3.3 关键对象命名

建议避免继续混用 `demo/oracle/physical/profile` 这些容易重叠的词。核心对象命名如下：

```text
ScenePreset
  一套共享桌面/机械臂/相机/颜色/坐标系设置。

TaskVariant
  某个任务在某个 seed 下生成的具体变式，例如 maze 的墙分布、cable 的 peg 和 connector 布局。

TaskLayout
  TaskVariant 转成世界坐标后的几何布局，供 builder 和 planner 使用。

SceneManifest
  Genesis 实体清单：实体名 -> entity handle，用于调试、验证、录制。

EpisodeSpec
  一次 episode 的完整输入：task_id、preset_id、seed、variant、runtime profile。

EpisodePlan
  planner 输出的高层子目标和 waypoint。

ExecutionProfile
  执行动作时的速度、步数、夹爪力度、摩擦策略、安全阈值。

EpisodeResult
  本次 episode 的结构化结果：success、failure_reason、metrics、artifact paths。
```

### 3.4 文件命名规则

建议采用读者一眼能看懂的后缀：

```text
*_builder.py       # 负责把 spec/layout 搭成 Genesis scene
*_generator.py     # seed -> variant/layout/spec
*_planner.py       # layout/state -> plan/subgoals/waypoints
*_executor.py      # plan/subgoal -> robot commands
*_monitor.py       # runtime safety/stability checks
*_verifier.py      # result/success checks
*_runner.py        # reset -> plan -> execute -> verify 的 episode 循环
*_demo.py          # CLI 展示入口
```

当前 `prototypes/cable_routing_physical_handle_demo.py` 以后应该变薄为：

```text
parse args
load preset/spec/profile
runner = CableRoutingEpisodeRunner(...)
runner.run(viewer=True/recording=True)
```

### 3.5 代码迁移计划

第一步，先不改行为，只移动责任边界。

#### 3.5.1 新增 generation 层

新增：

```text
topogym/generation/
  __init__.py
  episode_spec.py
  variants.py
```

职责：

- 定义 `EpisodeSpec`、`TaskVariant`、`ScenePreset`。
- 统一 seed 和 variant 生成。
- 生成 resolved config / manifest metadata。

迁移来源：

- 各 prototype 的 `load_configs`
- task YAML 中散落的随机布局参数
- `configs/common_configs/topogym_tabletop_v1.yaml`

#### 3.5.2 新增 planning 层

新增：

```text
topogym/planning/
  __init__.py
  subgoal.py
  waypoint.py
  cable_routing_planner.py
  maze_wall_removal_planner.py
  onestroke_wall_planner.py
```

职责：

- 把 task layout 转成 `EpisodePlan`。
- 对 cable routing，先把 YAML waypoint 表包成 planner 输出，之后再改成几何规则生成。
- 对 onestroke/maze，把“需要移动哪些 wall block、移动到哪”从 demo 中抽出来。

迁移来源：

- `prototypes/cable_routing_physical_handle_demo.py` 的 `_endpoint_oracle_targets`
- `configs/task_configs/cable_routing*_v1.yaml` 的 `endpoint_oracle_waypoints`
- `prototypes/onestroke_physical_wall_demo.py` 中 planned walls 相关逻辑
- `prototypes/maze_wall_removal_physical_demo.py` 中 planned removals 相关逻辑

#### 3.5.3 新增 supervision 层

新增：

```text
topogym/supervision/
  __init__.py
  stability.py
  pbd_monitor.py
  episode_result.py
```

职责：

- 统一 `follow_error`、`target_error`、`min_gap`、`contact_particles` 等安全阈值。
- 发现危险时返回 soft abort，而不是由 demo callback 临时决定。
- 输出结构化 failure report。

迁移来源：

- `prototypes/cable_routing_physical_handle_demo.py` 的 `on_segment_complete` safety 检查
- `topogym/primitives/pbd_handle_drag.py` 的 segment abort 逻辑
- `docs/develop/physics/untangle/untangle_pbd_segfault_debug_zh.md` 中总结出的 PBD 崩溃模式

#### 3.5.4 新增 runtime 层

新增：

```text
topogym/runtime/
  __init__.py
  episode_runner.py
  demo_runner.py
```

职责：

- 执行统一流程：

```text
EpisodeSpec
 -> build scene
 -> generate plan
 -> execute plan
 -> monitor stability
 -> verify result
 -> optionally record/view
```

- viewer 和 video 只是 runner 的输出模式。
- 未来 IL/RL 也调用同一个 runner 或其 vectorized 版本。

迁移来源：

- 各 prototype 的 `main()` 和 `run_demo()`
- `prototypes/record_physical_demos.py`
- `topogym/utils/recording.py`

### 3.6 Prototype 保留方式

`prototypes/` 不删除，但重新定义为“用户入口 / 实验入口”：

```text
prototypes/basic_env_demo.py
  继续作为桌面/坐标/相机检查器。

prototypes/*_physical_*_demo.py
  只作为具体 task 的 viewer/recording CLI。

prototypes/record_physical_demos.py
  变成调用 runtime runner 的批量展示脚本，而不是自己拼 command。
```

Prototype 中允许存在：

- argparse
- logging
- viewer/recording flags
- 调用 runner

Prototype 中不再长期存在：

- task-specific geometry generation
- path planning
- safety thresholds 的业务解释
- success verifier 主逻辑
- config override 魔法

### 3.7 第一轮可交付成果

第二阶段迭代 1 的最小可交付物建议是：

1. 新增 `topogym/generation/episode_spec.py`，定义 `EpisodeSpec`、`EpisodeResult`。

2. 新增 `topogym/planning/subgoal.py` 和 `topogym/planning/waypoint.py`，定义 `PlannedSubgoal`、`WaypointPlan`。

3. 新增 `topogym/runtime/demo_runner.py`，先服务一个任务，例如 cable routing 或 maze。

4. 把 `prototypes/cable_routing_physical_handle_demo.py` 里的 waypoint 读取和 safety callback 抽出一层，但保持 CLI 行为不变。

5. 给 `prototypes/basic_env_demo.py` 或新 `prototypes/environment_generation_demo.py` 增加：

```text
--task cable_routing
--seed 11
--variant smoke
--viewer
--print-spec
```

6. 让该 demo 输出：

```text
episode_spec task=cable_routing preset=topogym_tabletop_v1 seed=11 variant=smoke
scene_manifest entities=...
plan_summary subgoals=...
stability_profile=...
```

### 3.8 判断本迭代成功的标准

本迭代不以“生成多少 IL 数据”为成功标准，而以以下标准判断：

- 同一个 seed 重复运行，场景和 plan 一致。
- 不同 seed 可以生成可解释的任务变式。
- viewer 和 video 入口使用同一套生成结果。
- demo 文件明显变薄，核心逻辑进入 `topogym/generation/planning/supervision/runtime`。
- cable routing 失败时能得到结构化 `EpisodeResult`，而不是只剩一段 terminal log。
- 文档中的命名和代码目录能够一一对应，新读者能顺着名字读懂系统。

## 4. 建议的系统目标

在第二阶段中，建议系统目标定义为：

```text
TopoGym Environment Generator =
  Standard Scene
 Task Variant Generator
+ Task Planner
+ Motion Planner / Primitive Executor
+ Safety Supervisor
+ Success Verifier
+ Demo / Recording Exporter
+ Failure Quarantine
```

其中 planner 不是可有可无的装饰，而是核心模块。它要把任务目标拆成可执行、可验证、可恢复的子目标。IL 数据生成以后可以复用这个系统，但不应该反过来支配当前的模块命名和职责划分。

## 5. 分层架构规划



### A. Standard Scene Layer

职责：

- 统一桌面、机械臂、相机、坐标系、颜色方案。
- 提供 task frame 到 world frame 的转换。
- 提供相机配置，例如 front/policy camera、wrist camera、oblique debug camera。

现有基础：

- `configs/common_configs/topogym_tabletop_v1.yaml`
- `configs/env_configs/topogym_tabletop_v1.yaml`
- `configs/GEOMETRY_PARAMETERS_zh.md`
- `docs/develop/framework/genesis_world_coordinates_zh.md`

下一步：

- 给每个 physical task 增加 scene contract test，检查是否都使用同一套 tabletop baseline。
- 让 recording script 输出场景 preset 名和 camera preset 名。



### B. Task Layout Layer

职责：

- 从 YAML 读取任务资产、目标、随机 seed。
- 只负责“摆什么、摆哪里、什么算目标结构”。
- 不负责具体机械臂怎么走。

现有基础：

- `topogym/tasks/cable_routing.py`
- `topogym/tasks/untangle.py`
- `topogym/tasks/onestroke.py`
- `topogym/tasks/maze_wall_removal.py`

下一步：

- 把 demo 内的强制 override 显式命名为 runtime profile，例如 `physical_il_profile`。
- 不要让 YAML 的视觉默认值和 physical demo 的运行合约混在一起造成误读。



### C. Task Planner Layer

职责：

- 根据任务状态生成离散子目标。
- 对 cable routing，planner 应输出 route graph / safe zones / waypoint constraints，而不是只输出一串硬编码点。
- 每个子目标都要带 success predicate 和 safety predicate。

建议接口：

```python
class PlannedSubgoal:
    name: str
    target_pose: PoseLike
    clearance: float
    max_segment_length: float
    expected_contact: tuple[str, ...]
    success_check: str
    safety_check: str
```

对 cable routing，planner 应该生成：

```text
grasp_handle
depart_start
wrap_P1_outer
cross_between_pegs
approach_P2_outer
wrap_P2_outer
unload_after_P2
approach_connector
connector_capture
release
```

这里的“动作拆细”不是手工调魔法点，而是 planner 按规则把长段拆成短段：

- 单段 XY 距离不超过阈值。
- 单段方向变化不超过阈值。
- 接近 peg 时自动增大外侧 clearance。
- 离开 peg 时加入 tangent unload waypoint。
- 接近 connector 时先卸载 rope tension，再低位进入。



### D. Motion Planner / Primitive Layer

职责：

- 把子目标转成 Franka 可执行的末端轨迹。
- 做 IK reachability 检查。
- 执行 grasp、lift、drag、place、release 等 primitive。

现有基础：

- `topogym/primitives/pbd_handle_drag.py`
- `topogym/primitives/physical_contact.py`
- `topogym/robot/franka.py`

下一步：

- 把 `PBDHandleDragPrimitive` 中的 segment interpolation 抽成通用 `WaypointMotionExecutor`。
- 增加 preflight 检查：目标是否 reach、是否会穿过 peg/桌面/机器人底座、是否需要绕行。
- 对高风险段提慢的 execution profile，而不是只在 YAML 里手写 steps。



### E. Safety Supervisor Layer

职责：

- 在执行中实时判断是否继续。
- 发现高风险状态时 soft abort，而不是把 Genesis 拖到 segfault。

Cable routing 的危险信号包括：

- `follow_error` 逐步扩大，说明 handle 跟不上夹爪。
- `target_error` 在段末仍然很大，说明路径被 rope/peg/IK 阻塞。
- `min_gap < 0`，说明 PBD rope 粒子已经压入 peg 表面。
- `contact_particles` 异常高，说明 rope 被压得太紧。
- endpoint 附近急转、过低、过高，导致 rope 局部弯折过大。

下一步：

- 把这些检查从 demo callback 抽到 `topogym/supervision/`。
- 所有 PBD 任务共享一套 `PBDStabilityMonitor`。
- 每个 abort 都保存结构化 JSON：phase、seed、target、handle、rope metrics、screenshot/video tail。



### F. Success Verifier Layer

职责：

- 判断 episode 是否是一个稳定、可信、可展示、可复现的环境实例。
- 区分 physical success、task success、stability success、export readiness。

建议统一 result：

```text
physical_success: 机械臂是否真实完成接触/夹持/释放
task_success: 拓扑或几何任务是否完成
stability_success: 是否没有触发高风险物理状态
recording_success: viewer/video/观测导出是否完整
export_ready: 是否可以作为后续 demo/IL/RL/eval 的输入
```

对 cable routing，不建议只依赖 PBD 最终形态。更稳妥的是混合验证：

- handle 轨迹是否穿过 route graph 的正确侧。
- rope 是否没有明显穿 peg。
- P1/P2 附近是否存在合理接触或包角。
- connector latch 是否捕获成功。



### G. Demo / Recording Exporter Layer

职责：

- 记录 viewer/video 所需 artifact。
- 可选记录 obs/action/reward/info，但这不是当前迭代的主目标。
- 保存 planner subgoal trace，方便复现和调试。

建议先支持两种轨迹导出：

- `ee_pose_dense`：每个 control step 的末端目标。
- `waypoint_sparse`：planner 输出的关键 waypoint。

这和 RoboMME 的 `waypoint` 动作类型方向一致。以后如果要生成 IL 数据，可以直接复用这些 artifact；但当前先把它当成环境调试和复现材料。

### H. Batch Runner / Failure Quarantine

职责：

- 批量跑 task set。
- 每个 seed 失败后按规则重试。
- 成功 episode 进入 accepted manifest，失败 episode 进入 quarantine。

现有脚本：

- `prototypes/record_physical_demos.py`

下一步应扩展为：

```text
python -m prototypes.record_physical_demos \
  --tasks swap,onestroke,maze,cable_routing \
  --episodes-per-task 100 \
  --seed-start 0 \
  --max-retries 3 \
  --accept-stable-only \
  --write-manifest runs/environment_manifest.jsonl
```



## 6. Cable Routing 的特别建议

Cable routing 是目前最能暴露系统边界的任务。建议把它拆成两个 profile：

### Profile 1：Stable-Route Hybrid

目标：稳定生成可观察、可复现的 cable routing episode。IL 数据只是后续可能的导出格式。

原则：

- 机械臂仍然真实夹持 rigid handle。
- Rope 仍然由 PBD 演化，但不把“自然绕桩完美成形”作为唯一成功来源。
- planner 维护 route state：handle 是否按正确侧绕过 P1/P2。
- connector 可以使用 latch，因为真实插座也会有离散锁扣。
- rope 的最终几何用于 sanity check 和可视化，不作为唯一真值。

这更接近 RoboMME 的工程取向：先保证环境和轨迹可复现，再逐步提高物理真实性。

### Profile 2：Physics-Stress

目标：测试 Genesis PBD/rigid coupling 极限。

原则：

- 严格依赖 PBD contact。
- 不使用 route-state canonicalization。
- 允许失败，不用于主数据集。
- 专门保存崩溃复现材料，未来给 Genesis 提 issue。

这样可以避免把“研究引擎边界”的工作和“稳定生成环境 episode”的工作搅在一起。

## 7. 近期落地计划



### 第 0 步：冻结当前事实

- 为每个 demo 打印 `runtime_contract`。
- 为每次 run 保存 resolved config。
- 为每个 result 保存 JSON。
- 对 segfault 前一段保留 log 和短视频。



### 第 1 步：抽 planner 接口

新增：

```text
topogym/planning/
  base.py
  cable_routing_planner.py
  waypoint_utils.py
```

把 cable routing YAML 中的固定 waypoint 表迁移为 planner 输出。YAML 保留 peg、connector、clearance、风险阈值等参数。

### 第 2 步：抽 supervisor

新增：

```text
topogym/supervision/
  result_schema.py
  pbd_stability_monitor.py
  episode_supervisor.py
```

让 `pbd_handle_drag.py` 不再自己决定所有失败语义，而是把状态交给 monitor。

### 第 3 步：扩展 batch recorder

把 `record_physical_demos.py` 从“录几个视频”升级为“批量环境 episode 生成器”：

- 支持 task registry。
- 支持 per-task command/profile。
- 支持 seed range。
- 支持 retry。
- 支持 `export_ready` / `stable_ready` 过滤。
- 输出 manifest。



### 第 4 步：Cable routing 改为双 profile

默认环境生成使用 `stable-route`：

- route graph success + connector latch + PBD sanity。
- 对 PBD 接触使用宽松但非穿模的安全阈值。
- 失败则重试，不继续硬拖。

调试使用 `physics-stress`：

- 保留强 PBD 验证。
- 专门用于复现 segfault 和给 Genesis issue 准备证据。



## 8. 和 RoboMME 的核心差异

RoboMME 的 RouteStick 规避了我们最痛的部分：它不是一根 PBD 绳子被迫绕过刚性 peg 后插入 socket。它的 planner 可以更直接地驱动 stick/rigid objects。

TopoGym 如果要保留 rope/cable 的拓扑任务，就需要承认：

- 真实物理层会比 RoboMME 更难。
- 稳定 IL 采集层不能完全依赖 Genesis PBD 的自然接触求解。
- planner、supervisor、latch、route-state verifier 不是作弊，而是数据生成系统的稳定性工程。

最终目标应该是：RL/IL policy 学到的是“如何在标准场景里通过动作完成拓扑目标”，而不是被迫学习 Genesis PBD solver 的偶发数值崩溃模式。

## 9. 当前结论

下一轮不建议继续只微调 cable routing 的单个 waypoint 或摩擦系数。更有价值的工程方向是：

1. 把 planner 从 demo 中抽出来。
2. 把 route-state 和 PBD sanity 分开。
3. 建立 episode supervisor 和 failure quarantine。
4. 用 RoboMME 式的 waypoint/subgoal hierarchy 生成稳定 episode。
5. 把 Genesis PBD segfault 当作 physics-stress profile 的 issue 证据，而不是让它阻断主环境生成系统。

这会让我们从“一个很难调的视频 demo”转向“一套可复现、可扩展、可过滤的数据生成系统”。
