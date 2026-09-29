# 模拟器命名语义审计与统一词汇建议

日期：2026-09-23。基于本轮已重排的 `topogym/` 实际文件内容；**只分析和写文档，没有改名、改代码或修复 import**。

## 1. 结论与口径

命名问题主要有三种，不能都靠全局替换解决：

1. **同一个词指向不同职责。** 如 adapter、backend、episode、manifest；需要限定所属模块和对象。
2. **同一字段或方法名承诺了不同的行为。** 如 `gripper`、`step`、`set_arm_qpos`、`render`、`resume`；必须先明确单位、时间粒度、副作用和返回值。
3. **同类功能使用多个名字，或者一个名字包办多个职责。** 如 `sha/digest/file_hash`、各类 verification/audit，以及 task recording adapter 中混合的重建、状态恢复、录制和导出。

对 adapter 的直接回答：**按本报告的职责分组，有 4 类显式 adapter 用法，另外 3 类在其他类的说明、兼容代码或坐标字段中也叫 adapter，共 7 类实际语义。** 此外还有 2 处“需要某种 adapter”的错误提示，不能算已经实现了两个新模块。细分见第 3 节。

这次检查覆盖：

- 包内 **496 个 Python 文件**：功能目录 391 个、`redundants/` 105 个；另检查 4 个 HTML 文件名和 1 个资产来源 JSON 文件名。
- AST 提取 **3,326 处 class/def 声明**，包含方法、私有和局部声明；其中按名称判断的非局部公开声明为 **2,528 处**。
- 检查目录名、文件名、类名、函数/方法名；对动作字段、状态值、配置和序列化键做有针对性的调用处核对。
- `configs/` 中的 backend、profile、variant 等只作为语义证据，不混入上述源码命名数量；不对所有变量和配置键宣称完成穷尽式语义证明。
- 不把 `runs/`、legacy、第三方安装包中的历史复本重复累计。源码已移动但 import 字符串未更新，这些旧路径是迁移待办，不是另一套仍实际存在的目录。

配套材料：[完整命名与声明索引](simulator_naming_inventory_zh.md) · [统计口径、命中路径和源码哈希](simulator_naming_counts_20260923.json) · [此前文件迁移记录](structure_move_20260923_zh.md)。

## 2. “标准 simulator 命名”采用什么依据

本报告建议的是 **TopoGym 内部统一词汇**，不是声称行业存在一份强制的目录/后缀标准。采用公开模拟器接口中已经清楚的职责边界：

- **Env：** 对外负责 `reset/step/render/close`，step 区分 observation、reward、terminated、truncated、info；任务成功不能简单等同于 episode 停止。[Gymnasium Env](https://gymnasium.farama.org/api/env/)
- **Wrapper：** 包装已有环境，变换动作、观测或奖励并保留其环境接口；区别于负责跨协议转换的 Adapter。当前 `VisualAdapter` 还不是 Gymnasium Wrapper 的实现。[Gymnasium Wrappers](https://gymnasium.farama.org/api/wrappers/)
- **Scene：** Genesis 用它承载实体、build 和物理 step。TopoGym 可以用 World 包装这一层，但不应把 agent 客户端、任务目标或录制会话也称为 Scene。[Genesis 入门](https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/hello_genesis.html)
- **Action / Observation / Reward / Termination：** 可按职责明确命名；尤其要区分每个环境步的 action 处理和每个物理步的 action 应用。这里参考边界，不要求照搬一整套 Manager 类。[Isaac Lab managers](https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.managers.html)

后文的新名字均为建议，只有实现满足其含义后才能成为公开 API。把现有类改名为 `Env`，不会自动获得 reset、close 或 Gymnasium 兼容性。

### 2.1 名称族统计

下表的“路径命中”包含目录和文件名，不是只数同名文件；常见复数归一，例如 adapters → adapter。定义列只数非局部、非下划线命名的 class/def，方法也计入。不同名称族会重叠，不能横向相加得出文件总数；频次也不等于语义种类或问题数量。

| 名称族 | 功能目录路径命中 | redundants 路径命中 | 公开类定义 | 公开函数/方法定义 |
|---|---:|---:|---:|---:|
| adapter | 26 | 1 | 13 | 0 |
| binding | 0 | 0 | 15 | 4 |
| scene / world / env / task | 206 | 29 | 32 | 69 |
| runtime / runner / execution / session | 20 | 2 | 7 | 9 |
| config / spec / schema / contract / protocol | 24 | 0 | 2 | 29 |
| registry / catalog / factory / builder | 4 | 0 | 11 | 10 |
| policy / planner / controller / solver | 79 | 0 | 6 | 9 |
| variant / variation / family / instance | 57 | 13 | 12 | 37 |
| preset / profile / template / layout | 4 | 0 | 15 | 24 |
| episode / run / rollout / trial / segment | 15 | 4 | 17 | 63 |
| step / tick / frame | 0 | 1 | 4 | 49 |
| state / snapshot / checkpoint / restore | 1 | 1 | 1 | 66 |
| replay / resume / render / record | 59 | 4 | 7 | 59 |
| validate / verify / audit / review / qualify | 35 | 8 | 7 | 109 |
| geometry / model / asset | 72 | 0 | 4 | 58 |
| manifest / source / signature | 3 | 0 | 2 | 48 |
| demo / probe / preview | 10 | 39 | 5 | 18 |
| result / status / verdict / success | 0 | 0 | 14 | 1 |
| backend / device / engine | 3 | 0 | 2 | 1 |

## 3. adapter 到底有多少种含义

### 3.1 四类显式用法

| 类别 | 当前命名与规模 | 实际职责、输入 → 输出 | 应采用的职责名称 |
|---|---|---|---|
| A. 环境控制与任务接入 | `envs/adapters/` 11 个文件；相关 12 个 `*Adapter` 类声明含 `TaskAdapter` 协议 | 动作字典 → 控制目标、物理推进、观测、成功/失败；部分还安装抓持约束 | 公共 Env 生命周期、Robot 控制、Task 判据应分开；现有协议暂称控制 tick 接口 |
| B. 观测权限包装 | `agents/rollout/runtime.py::VisualAdapter` 1 个类 | 已有环境端口 → 过滤后的描述和空结构观测，RGB 继续透传 | 当前可称 `RgbOnlyObservationView`；统一 Env 后可用 observation wrapper |
| C. 录制与引擎连接 | `recording/adapters/` 2 个文件含包标记；MuJoCo 实现在 redundants 另 1 个文件 | 在线场景/保存状态 ↔ clock、render、export_state、restore、subscribe | `RecordingBinding`；具体为 `GenesisRecordingBinding`，保留明确的录制限定 |
| D. 任务录制接入 | `recording/task_adapters/` 13 个文件 | 任务 run/轨迹/配置 → 来源包、重建场景、任务 Binding、录制或视频结果 | 按内容拆成 render-state 编解码、重建工厂、录制接入与资产来源打包；不能整组直接改叫 codec |

数量的关系：

- 名称含 `Adapter` 的类共 **13 个**：A 类 12 个，B 类 1 个。不是 13 种职责。
- A 类 12 个包含：1 个协议、4 个通用/机器人实现、7 个具名任务实现；Coil 的第 8 个任务接入模块直接组装 `GenesisAdapter`，没有再声明 `CoilAdapter`。
- 路径中含 adapter/adapters 的文件共 **27 个**：11 + 2 + 13 + 1；`TaskAdapter` 和 `VisualAdapter` 的文件路径本身不含 adapter。
- `*Binding` 类另有 **15 个**，含协议、引擎 Binding 和任务 Binding；它们与 adapter 目录发生交叉，不能把 13 + 15 当作“28 个 adapter”。[全部声明位置](simulator_naming_inventory_zh.md)

关键证据：

- [`TaskAdapter`](../../../topogym/envs/protocol.py#L5) 只有 describe、validate_action、step、observe、render、evaluate；**没有 reset/close**。名字暗示“任务转换”，实际定义的是 agent 侧环境操作面。
- [`GenesisAdapter.step`](../../../topogym/envs/adapters/base.py#L82) 设置目标后直接调用 `scene.step()`；[`RigidRobotAdapter`](../../../topogym/envs/adapters/rigid_robot.py#L60) 还处理接触、焊接辅助抓持、跟踪失败和稳定成功。它不是一个仅做格式转换的薄层。
- [`VisualAdapter`](../../../topogym/agents/rollout/runtime.py#L16) 的 observe 返回空字典，其余多数操作透传；该类不创建独立动力学。
- [`RecordingBinding`](../../../topogym/recording/contracts.py#L58) 明确要求 render/restore 不积分；其职责恰好与环境侧 adapter 的 step 相反。
- [`KnotBinding` / `SharedKnotRecorder`](../../../topogym/recording/task_adapters/knot_untying.py#L35) 同在一个 task_adapter 文件；前者声明状态范围，后者接公共录制。文件名不能代表文件内只有一种适配功能。
- [`BlanketBinding`](../../../topogym/recording/task_adapters/blanket_flatten.py#L102) 同时恢复粒子和关节、抽查间隙、输出检查结果；不是可直接统一成纯 serializer 的实现。

### 3.2 另外三类隐式用法

| 类别 | 当前证据 | 实际含义 | 建议措辞 |
|---|---|---|---|
| E. 传感器接口转换 | [`NyxCamera`](../../../topogym/sensors/nyx.py#L149) 的说明称自身为 adapter | 把 Nyx RGB 传感器接到现有 camera render/pose 接口 | `NyxCameraAdapter`，明确 source 与 target interface |
| F. 引擎接口与版本兼容 | [`ipc_compat.py`](../../../topogym/world/physics/knot_untying/ipc_compat.py)、[`runtime_memory.py`](../../../topogym/world/physics/knot_untying/runtime_memory.py)、[`PBD backend`](../../../topogym/world/rope_backends/pbd.py) | 分别是关节轴兼容修正、历史缓存管理、绳物理接口封装 | 按实际行为用 `JointAxisCompatibility`、`ForwardHistoryLimiter`、`PbdRopePhysics`，不要都简称 adapter |
| G. 模型导入坐标偏移 | [`robot_adapter_z_translation_m`](../../../topogym/sensors/aloha_cameras.py#L80)、[`source_base_adapter_z_translation_m`](../../../topogym/robot/aloha_contract.py#L21) | ALOHA 原模型基座转到当前场景时的 z 偏移，数值还含 riser | `source_base_z_offset_m` 或明确的 frame transform；不是 env adapter 对象，也不能据此推断存在机械转接件模型 |

另有两种措辞只在提示中出现：

- [`recording/archive.py`](../../../topogym/recording/archive.py#L48) 的 “qualification adapter” 实际检查资格标识是否匹配；尚不能据此说存在一个 `QualificationAdapter` 模块，提示应描述缺失的 qualification evidence/validator。
- [`recording/sources.py`](../../../topogym/recording/sources.py#L80) 的 “dependency adapter” 表示非 MJCF XML 的依赖解析尚不支持；未来若实现，应称 `AssetDependencyResolver`。

**命名规则：** Adapter 只用于明确的接口转换边界，必须能说明“从什么协议/表示转换到什么协议/表示”。承担整个物理循环的类不能因对外提供接口就全部叫 Adapter；版本补丁、坐标偏移和资格条件也不沿用这个泛称。

## 4. 优先处理的语义冲突

### P0-1：gripper、qpos、set 隐藏不同物理意义

- [`aloha_contract.contract`](../../../topogym/robot/aloha_contract.py#L5) 中 `gripper` 是**单个手指滑轨位移，单位 m**；[`panda_contract.contract`](../../../topogym/robot/panda_contract.py#L7) 中同名字段是 **Robotiq 半开口，单位 m**。单位一样仍不代表语义一样，不能直接复用数值。
- 建议公共动作选用经过机器人转换层定义的 `gripper_width_m`；如果这一轮保留原生控制，分别公开 `finger_slide_target_m`、`gripper_half_width_target_m`，并声明 action type。不能仅改键名却不转换数值。
- [`set_arm_qpos`](../../../topogym/robot/aloha.py#L49) 调 `control_dofs_position`，是发送目标；它还可通过 steps 参数推进物理。建议拆为 `set_joint_position_target` 与 Env 推进，直接修改状态才使用 `set_joint_positions`，且受 reset/restore 阶段约束。
- 状态与目标分开：`joint_positions_rad` 对应测量，`joint_position_target_rad` 对应命令；泛化关节模型如含直线关节，应按关节类型声明单位，不能把所有 qpos 都标成 rad。

### P0-2：step、tick、frame 没有统一粒度

- [`TaskAdapter.step`](../../../topogym/envs/protocol.py) 承诺一个 control tick；[`FrankaPositionIKController.step(steps)`](../../../topogym/robot/franka.py#L114) 推进任意数量物理步；[`Environment.step(action, steps)`](../../../topogym/agents/rollout/env_sdk.py#L55) 是远程请求，可要求多步；部分 `TaskScene.step` 又直接转发引擎。
- `frame` 既是 [`TaskLayout.frame`](../../../topogym/config/episode_spec.py#L84) 的空间坐标系，也是 [`FrameSet`](../../../topogym/recording/contracts.py#L42) 的视频采样；本来可以共存，但不能在跨模块字段里都只叫 `frame`。
- 建议 `env.step(action)` 固定为一控制步；多步调用明确 `step_n(..., control_steps=...)`。物理计数 `physics_step`、内部积分 `physics_substep`、控制计数 `control_step`、视频 `video_frame_index`、坐标系 `reference_frame` 分开。
- 使用 `physics_dt_s`、`control_dt_s`、`sim_time_s`、`video_time_s`；render/observe 不因名称相似就被允许推进时间。实际步长关系必须由实现证明，不能改名后假设一个控制步必等于一个物理步。

### P0-3：backend、solver、model 跨了三个层级

- [`config/registry.py`](../../../topogym/config/registry.py#L8) 与 [`create`](../../../topogym/envs/adapters/cast_coil.py#L5) 的 backend 传给 `gs.init`，值为 cpu/cuda 等，是**计算后端**。
- [`configs/task_cards/lock_picking.yaml`](../../../configs/task_cards/lock_picking.yaml#L44) 的 physics.backend 是 `genesis_1.2.1_rigid`，混合了**引擎、版本和物理类型**。
- [`world/rope_backends`](../../../topogym/world/rope_backends/__init__.py) 的 backend 是 **PBD/FEM+IPC 绳物理实现**；不是第二套引擎，也不是 IK。
- 统一限定：`physics_engine`（本项目固定 Genesis）、`compute_backend`、`render_backend`、`rope_physics_model`；`ik_solver`、`rigid_solver`、`fem_solver` 分开。第三方 `gs.init(backend=...)` 的正式参数名原样使用，在我们配置层作明确映射。
- 模型资源 `robot_model`、绳物理 `rope_physics_model`、agent 的 `llm_model` 各自限定；不要求机械地把所有局部变量 model 都改名。

### P0-4：status、success、passed、qualified 不能互换

- [`EpisodeStatus`](../../../topogym/config/episode_spec.py#L9) 使用 `ongoing/success/fail/timeout/error`；环境判定使用 `running/succeeded/failed`；[`Trial`](../../../topogym/agents/rollout/tool_runtime.py#L22) 又有预算、协议或 pipeline 终止状态。
- [`recording.validate`](../../../topogym/recording/validation.py) 的通过是媒体/证据检查；[`catalog.validate_card`](../../../topogym/config/catalog.py#L29) 的通过是任务卡格式；它们都不能证明任务成功。
- 建议拆清 `task_success`、`episode_outcome`、`termination_reason`、`validation_passed`、`qualification`、`trial_status`、`recording_status`；同一层只用一套枚举。
- Env 对外另保留 `terminated/truncated` 的明确定义；失败或成功是任务结果，超时通常是截断原因，基础设施错误单独记录。已有 `EpisodeResult` 中 `success/stable_ready/export_ready` 的区分应保留，不能为了“统一”压成一个 passed。

### P0-5：task_id 的确存在跨模块名称不一致

- 当前注册名与文件名是 `lock_picking`，但 [`StagedLockEvaluator.evaluate`](../../../topogym/evaluation/tasks/lock_picking/evaluator.py#L16) 返回 `task_id='staged_lock'`。这是身份不一致，可能影响汇总与 join，不只是可读性。
- `ClawScene`、`ClawsAdapter`、`interlocked_claws` 是同一任务的多个缩写；`RopeBinding`、`FEMBinding` 则隐去了自己属于 Orbits/Slotted 的事实。
- 建议唯一任务 ID 使用当前 catalog 的 13 个 snake_case ID。类名使用对应任务前缀或由模块上下文限定；公开导出的 `RopeBinding` 应为 `OrbitsRenderStateBinding`，不能将所有绳任务都映射成 Rope。
- 老报告字符串、注册别名、序列化工厂路径都需在改名时显式处理；不能只修一个文件名就认为身份已统一。

### P1-1：Env、Task、Scene、World、Environment 指的不是同一层

- 13 个 `tasks/<id>.py` 当前是原 Scene/SceneBuilder；它们还没有统一的 Task 类。`task` 局部变量有时实际拿的是场景对象，带 scene、manifest、cameras。
- [`Environment`](../../../topogym/agents/rollout/env_sdk.py#L14) 是 HTTP 客户端；[`EnvironmentServer`](../../../topogym/agents/rollout/tool_runtime.py#L237) 是试验访问服务。它们不应和本地物理 Env 都使用无修饰的环境名。
- 建议 `Env` 管公共生命周期；`Task` 管实体声明、初态、奖励与判据；`World` 管 Genesis 场景与时钟；`TaskScene/SceneHandles` 只表示已构建的句柄集合；远程端为 `EnvClient/EnvServer`。
- 当前可以准确地叫 TaskScene 的对象先保留该名，不要直接改成 Task 或 Env，掩盖尚未实现的接口。

### P1-2：runtime、runner、execution、session 名字太宽

- `envs/execution/*` 是物理执行，`agents/rollout/runtime.py` 是 agent 交互编排，`world/physics/*/runtime_memory.py` 是引擎内存管理。它们共用 runtime 但没有共同接口。
- [`EpisodeRunner`](../../../topogym/envs/episode_runner.py#L30) 已有明确的整段运行协议，可保留；[`Session`](../../../topogym/agents/bridge/session.py#L27) 管 agent 分段交互，应称 `AgentSession`；`RecordingSession` 已限定领域，无需为去重再改名。
- `runtime.py` 应按实际对象称 `agent_rollout.py`、`episode_runner.py` 或 `history_limiter.py`。混合文件要先拆职责；不新增一个更泛的 RuntimeManager 来包住旧实现。

### P1-3：episode、trial、rollout、run、segment 混合了身份和执行

- [`EpisodeKey`](../../../topogym/config/episode_spec.py#L29) 的字段是 task、seed、preset、variant，实际标识生成实例；没有这次执行的 episode 编号。
- [`agents/rollout/Episode`](../../../topogym/agents/rollout/episode.py#L101) 拥有 multiprocessing Process/Pipe，是子进程句柄，应称 `EpisodeProcess`；隔离区中另有同名 Episode 但承担任务执行，两者不是同一接口。
- [`Trial`](../../../topogym/agents/rollout/tool_runtime.py#L22) 可持有累计预算和多个重建 episode；建议 `AgentTrial`。`rollout` 只表示采集策略执行轨迹的过程/结果，`segment` 表示一次动作批次，`run_id` 表示运行产物身份。
- `EpisodeKey → TaskInstanceKey` 是语义纠正候选，必须连同持久化 schema 审查；`EpisodeSpec` 可继续表示一次 episode 的输入规格，内部引用实例身份，不将输入规格当作完整物理 checkpoint。

### P1-4：config、spec、schema、contract、protocol 混用

- [`EpisodeSpec`](../../../topogym/config/episode_spec.py#L114) 是展开输入；`TaskAdapter` 是行为 Protocol；`robot/*_contract.py` 同时返回机器人事实、相机、动作字符串说明并实施校验；`recording/contracts.py` 又同时包含数据类和行为协议。
- 约定 `*Config` 是配置参数，`*Spec` 是声明性输入/能力规格，`*Schema` 是序列化结构规则，`*Protocol` 是调用接口。`contract` 可作为文档中的总称，不作为任何不易归类字典的默认名字。
- `action_schema` 当前部分字段只是自然语言，不能误称已提供可机器验证的统一 schema。拆出的说明可用 `action_description`，正式结构和约束另有 `ActionSpec`。

### P1-5：registry、catalog、factory、builder、manifest 边界混淆

- [`registry.factory_for`](../../../topogym/config/registry.py#L8) 选择构造入口；[`catalog`](../../../topogym/config/catalog.py) 读取任务卡；它们职责不同，可以并存，但对外任务身份应来自同一权威描述。
- [`EntityManifest`](../../../topogym/world/manifest.py#L8) 是内存中的名称→Genesis 句柄表，适合叫 `EntityRegistry`；录制 source/asset manifest 则是可持久化的文件与哈希清单。
- Factory 表示选择/创建实例；Builder 表示分阶段构建；Registry 表示键→工厂/句柄查询；Catalog 表示元数据目录；Manifest 表示产物/输入清单。不要把这些同名化为 Registry。

### P1-6：solver、planner、controller、policy、agent 被交叉使用

- `solvers/kinematics/*/robot_plan.py` 中既有 Kinematics，又有任务路线和文件输出；`policies/tasks/*/physical_extraction.py` 又含 IK。上一轮按文件搬迁没有完成函数层拆分。
- `policy` 有三种相关但不同用法：机器人控制策略、[`script_policy`](../../../topogym/policies/script_policy.py) 的动作程序解释、[`tool_policy`](../../../topogym/agents/bridge/tool_policy.py) 的工具访问规则；后两者不能冒充控制策略。
- 约定 Solver 做约束/数值求解，Planner 产生目标/路径，Controller 把目标变成控制命令，Policy 根据观测选择动作，Agent 负责外层决策/交互。
- 对公开对象限定为 `IKSolver`、`CollisionChecker`、`MotionPlanner`、`JointPositionController`、`ControlPolicy`、`ActionProgramInterpreter`、`ToolAccessPolicy`；不要求所有现有实现都立即变成一个新类。

### P1-7：variant、variation、family、instance、preset、profile

- [`lock_picking/variants.py`](../../../topogym/assets/variants/lock_picking/variants.py#L139) 同时有 family、prototype、variation 指令、variant 标签、instance hash；这些不应靠一个 variant_id 装下全部身份。
- 建议 family=机制族，template/prototype=生成基型，variation=采样规则，variant=参数化结果类别，instance=完整冻结实例；family_id、variant_id、instance_id、seed 分别保留。
- `preset` 是可复用的命名配置组合；`profile` 是特定运行/呈现/访问规则。用 `ScenePreset`、`RobotPreset`、`RecordingProfile`、`AgentAccessProfile` 限定；[`recording.prepare(preset=...)`](../../../topogym/recording/config.py#L45) 实际选择 recording profile，应在 API 整理时统一术语。
- `varaition_` 是用户指定的旧 demo 目录拼写，**不是本轮擅自纠正的拼写错误**；只留在文件系统兼容边界，新的 Python 类型/字段仍用 variant/variation。是否取消旧目录约定，应与目录清理一起决定。

### P1-8：snapshot、checkpoint、state、replay、resume 混淆能力

- [`Session.snapshot`](../../../topogym/agents/bridge/session.py#L85) 返回会话摘要；录制 task_adapter 的 snapshot 打包来源配置与状态文件；引擎缓存还有内部 checkpoint。三者不能都表示可续跑的物理快照。
- [`recording.replay(..., resume=True)`](../../../topogym/recording/replay.py#L84) 恢复渲染/编码作业，报告明确 `physics_resume_supported=False`；[`ReplayAgent`](../../../topogym/agents/rollout/agents.py#L27) 则重放测试决策。
- 建议：`session_summary`、`export_render_source`、`RenderState`、`SimulationCheckpoint`、`rerender_recording`、`resume_render_job`、`DecisionReplayAgent` 分开。只有状态足够且恢复能力经过验证时才命名为 simulation checkpoint/resume。
- `RenderState` 可支持画面恢复，不自动等于速度、约束、接触和内部求解状态完整；名称应反映能力范围。

### P1-9：render、observe、record、write、export、archive 混在一起

- 环境 render 返回 PNG 字节、NyxCamera.render 返回图像元组、task recording 文件里的 render 常返回视频/报告；[`Env SDK`](../../../topogym/agents/rollout/env_sdk.py#L44) 还把 render 作为 observe 的别名。
- 约定 observe=读取传感器观测，render=生成图像，record=按时间采集，encode=帧转媒体，write=写当前格式，export=转换/输出外部格式，archive=发布并冻结已验收产物。
- 模块上下文已明确时可以叫 render；跨模块 API 或 CLI 应使用 `render_rgb`、`render_video`、`export_episode_dataset`、`publish_recording` 等具体名。录制完成与任务成功分开报告。

### P2-1：validate、verify、audit、qualify、review 都在“检查”

- validate 用于输入/结构检查；verify 用于检查性质/不变量；audit 用于保存执行的证据核对；qualify 用于按资格条件作决定；review 用于生成供人阅读的材料。
- 现有任务的同名函数经常跨越这几类。例如 `RobotAudit` 有在线接触查询和离线几何检查；不能只按 audit 后缀判断是否纯离线。
- 建议带宾语：`validate_action`、`verify_geometry`、`audit_execution`、`assess_physics_qualification`、`write_review_report`。要先说明执行的是哪一种检查，不能把函数重命名当成其性质证明。

### P2-2：geometry、assets、model、utils 的归属要靠内容

- 包内 12 个 `geometry.py` 主要是各任务建模，跨任务共同存在不等于应合成一个巨型 geometry.py；几何生成、碰撞计算、纯数学与实体实例化仍应分开。
- 包内 `assets/` 是生成/加载代码，根目录 `assets/` 是素材；`assets/generators/<task>/geometry.py` 在限定路径下可以保留。真正通用的纯计算才进 `utils/geometry/`。
- `utils` 不应收容 Env 初始化、物理 step、任务成功判断、录制流程。`core/common/base/shared/helpers` 也不能成为未想清楚职责时的默认分类。

### P2-3：sha、digest、array、numpy 等公共工具没有统一对象语义

- 同名 `digest` 有的哈希文件，有的哈希 JSON；`sha`、`sha256`、`file_hash` 又表示相近功能。已有 [`utils/io.py`](../../../topogym/utils/io.py#L30) 同时提供文件 SHA-256 与 canonical JSON hash，是可比较的候选实现。
- 建议 `sha256_file`、`hash_canonical_json`、`to_numpy`、`write_json_atomic`；但先核对是否复制、设备搬运、精度转换、键排序、NaN 和原子写入语义，不能直接全仓换调用。
- `shared` 只能说明复用意图；是否真的共用，要由调用链判断。`physical/full/official/ready` 不应替代能力字段和验证结果。

## 5. 同名不一定需要改名

扫描发现 **10 组完全同名的公开类**，全部位置列于 [附录](simulator_naming_inventory_zh.md)。其中最值得比较的是：

- `Kinematics` 5 处：4 处在 solvers，1 处在 Hedgehog 的逆向变体文件；单/双臂、模型来源和任务约束不同，不应仅因同名就替换为一个实现。
- `RobotAudit` 3 处：Hedgehog 两个运行器和 Buzz Wire 规划器；建议按在线接触检查或规划碰撞检查分别命名。
- `Episode` 2 处：进程对象和隔离区任务执行对象，语义不一致。
- `ForwardOnlyMemory` 2 处、`StabilityLimits` 2 处：可能是重复机制，也可能参数与验证范围不同，应比较实现再合并。

允许保留的正常重复：

- 不同 Task 实现同一协议的 `reset/step/observe/evaluate`。
- `tasks/` 对应的各任务建模模块都提供 `generate_assets`，只要输入输出契约一致或保持在任务限定的内部空间。
- `RecordingSession` 与 `AgentSession` 都含 Session，但前缀已经表达管理对象。
- `physics.fem_solver` 与 `kinematics.ik_solver` 都含 solver，但对象限定明确。
- 局部变量 model、state、cfg 在短小且类型明确的作用域中可保留，不追求全仓每个名字唯一。

## 6. 目标 base 的推荐命名词典

这是未来接口的职责约束，不是要求新建下表每一个类。

| 模块 | 推荐核心名 | 必须表达的边界 |
|---|---|---|
| Config / Registry | `EnvConfig`、`TaskSpec`、`TaskRegistry`、`make_env` | 配置、声明、查询、实例构造分别命名 |
| Env | `Env`、`EnvProtocol`、`StepResult` | 唯一 reset/step/close；step 的时间和结果合同一致 |
| Task | `<TaskName>Task`、`TaskResult`、`is_success`、`compute_reward` | 任务实体/初态/目标/判据；不是录制与进程宿主 |
| World | `GenesisWorld`、`WorldState`、`EntityRegistry` | 持有 Genesis scene、物理时间及实体句柄 |
| Scene 构建 | `SceneBuilder`、`TaskScene` / `SceneHandles` | Builder 构建；SceneHandles 为结果，不叫运行会话 |
| Robot | `Robot`、`RobotSpec`、`JointPositionController`、`GraspConstraint` | 本体、命令与约束；不隐式占有完整环境循环 |
| Solvers | `IKSolver`、`FKSolver`、`CollisionChecker`、`MotionPlanner` | 查询/求解与在线控制、积分有明确边界 |
| Sensors | `Camera`、`CameraCalibration`、`Observation`、`SensorFrame` | 观测、标定、时间与坐标系明确 |
| 接口转换 | `<Source><Target>Adapter` 或限定名称 `NyxCameraAdapter` | 必须标明适配两端；不作为任何“接入代码”的泛称 |
| 环境包装 | `<Purpose>ObservationWrapper` 等 | 保留完整环境协议，改变某一特性 |
| Recording | `RecordingSession`、`GenesisRecordingBinding`、`RecordingResult` | 对物理观测流采集、编码、发布，不判断任务策略 |
| 状态重渲染 | `RenderState`、`RenderStateCodec`、`rerender_recording` | 声明可恢复字段；不承诺物理续跑 |
| Dataset | `EpisodeDatasetWriter`、`DatasetSchema`、`DatasetExporter` | episode 数据写入与外部格式转换 |
| Evaluation | `ExecutionValidator`、`EvaluationReport`、`QualificationResult` | 输入校验、实测验收与资格结论分别表达 |
| 策略 | `ControlPolicy`、`ActionProgram`、`MotionPlan` | 选择动作、动作程序与目标路线分开 |
| Agent | `AgentSession`、`AgentTrial`、`EnvClient`、`EpisodeProcess` | 外层决策、会话、预算、传输和进程 |
| Assets | `AssetGenerator`、`AssetLoader`、`AssetManifest` | 建模生成、加载、来源清单 |
| Utils | `to_numpy`、`sha256_file`、`hash_canonical_json` | 名称说明纯计算/数据操作；无隐藏仿真推进 |

对象命名应回答三个问题：**它属于哪个领域；它是数据、接口还是执行者；它能否改变模拟状态。** 比后缀统一更重要的是，不能用一个无副作用的名字包装有副作用的实现。

## 7. 可执行的命名整理清单

以下都未实施。A 表示职责已较清楚，可在下一轮修复引用时改名；B 表示必须先统一/拆分行为；C 表示还涉及外部标识或持久化格式，不可仅做源码符号替换。

| 当前名称/位置 | 建议名称或拆分目标 | 类型 |
|---|---|---|
| `TaskAdapter` | 当前可描述为 `ControlTickProtocol`；补齐生命周期后才使用 `EnvProtocol` | B |
| `GenesisAdapter`、`RigidRobotAdapter`、`FEMRobotAdapter` | 公共 Env + Robot controller/grasp + Task evaluator；不逐个创建同名新 Env 子体系 | B |
| 8 个 task agent_adapter 工厂 | 一个 Task 构造接入约定，注册后经 `make_env(task_id, ...)` 创建 | B/C |
| `VisualAdapter` | `RgbOnlyObservationView`；统一 Env 后采用 wrapper | A/B |
| `GenesisBinding` | `GenesisRecordingBinding` | A |
| `RopeBinding`、`FEMBinding` | 若保留其能力，分别限定为 Orbits/Slotted 的 render-state binding；退役后端不为改名而保留 | A/B |
| `recording/task_adapters/*` | 拆分状态编解码、场景重建、录制接入、来源打包；不整文件改叫 codec | B |
| `NyxCamera` | `NyxCameraAdapter` | A |
| `adapter_z`、`robot_adapter_z_translation_m` | `source_base_z_offset_m`，或明确的模型坐标变换对象 | A/C |
| `ForwardOnlyMemory` | `ForwardHistoryLimiter`，比较两份实现后集中 | B |
| `EntityManifest` | `EntityRegistry` | A |
| bridge `Session` | `AgentSession` | A |
| SDK `Environment` | `EnvClient` | A/C |
| rollout `Episode` | `EpisodeProcess` | A |
| `Trial` | `AgentTrial` | A |
| `EpisodeKey` | `TaskInstanceKey`，重新检查身份字段和 schema | B/C |
| `ReplayAgent` | `DecisionReplayAgent` | A |
| `Session.snapshot()` | `snapshot_session()` 或 `session_summary()`，明确不是物理状态 | A/C |
| 录制 `snapshot(run, ...)` | `export_render_source(...)` | A/C |
| 录制 `replay(..., resume=...)` | `rerender_recording(..., resume_render_job=...)` | A/C |
| 通用字段 `backend` | 按值域分成 compute_backend / physics_engine / rope_physics_model | B/C |
| action `gripper` | 统一物理量并转换；否则按原生指令明确字段名和 action type | B/C |
| `set_arm_qpos(..., steps=...)` | `set_joint_position_target(...)` + Env 明确推进 | B |
| `task_id='staged_lock'` | 统一为 `lock_picking` 或建立显式旧身份映射 | C |
| `sha/digest/file_hash` | 按输入分为 `sha256_file` / `hash_canonical_json` | B |

下一轮宜先处理 P0 字段与行为合同，再确定 Env/Robot/Task/Recording 的类型名，最后更新工厂字符串、序列化、CLI、测试和文档。退役脚本继续保留原名便于追溯，不为“命名整齐”重做一整套不用的实现。

## 8. 项目命名规则建议

1. 模块/文件/函数用 snake_case，类用 PascalCase，常量用 UPPER_SNAKE_CASE；关键是完整限定名明确，不要求全局唯一短名。
2. 公共类优先用“领域对象 + 职责”；只在确有跨接口转换时使用 Adapter。禁止用新增 `BaseManager/CommonHelper/GenericAdapter` 掩盖混合职责。
3. 配置、数据、执行者分开：`Config/Spec/State/Result` 不隐式启动物理或写视频；`Builder/Controller/Runner/Writer` 的副作用在名称和接口中可见。
4. 方法带清楚的操作与对象：`set_*_target`、`read_*_state`、`validate_action`、`render_rgb`、`export_dataset`；对同一协议允许相同短名。
5. 时间字段注明粒度与单位；空间字段注明 frame、单位和四元数顺序，如 `position_world_m`、`orientation_wxyz`。关节顺序由 RobotSpec 固定。
6. 数据字段区分 measured/target、physics/render、task/trial、source/output；禁止以含混的 state/status/success 连接不同层的结果。
7. 内部只有 Genesis 时，不为命名对称而保留可选 engine registry；compute backend 与物理模型仍分别命名。
8. Task ID、实例 ID、执行 ID 和 artifact ID 不混用；任务名以 catalog 为权威，类前缀采用明确对应，不靠缩写猜测。
9. 改名必须检查 import、动态工厂、字符串协议、配置键、schema、CLI 和外部调用；迁移前记录 old → new。是否保留兼容别名按当前需要决定，不默认无限期兼容旧 demo。
10. 审查“名称是否说明职责”和“实现是否符合承诺”两项；后者不成立时，先拆代码或改行为，不宣称改名已经完成模块化。

## 9. 验证范围

- 名称数量来自当前 496 个 Python 文件的 AST，不导入包，不执行物理或旧 demo。
- 附录对 501 个扫描文件逐项给出名称，全部 3,326 个 class/def 声明含行号；统计 JSON 保留输入文件哈希及名称族命中路径。
- 报告中的 adapter 分类、动作单位、后台含义和恢复能力来自相关实现/调用处的人工核对；频次统计不能自动证明全仓所有同名符号行为等价。
- 本轮没有源码改动，亦未把标准文档中的 API 当成项目已经实现的能力。
