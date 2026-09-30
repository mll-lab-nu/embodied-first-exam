# FEM IPC 绳与 PBD 布的公共自动抓持开发计划

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

2026-09-27。状态：**两种柔体后端已实现；独立双夹爪机制、标准 Panda 的两种材料完整 rollout 与 Nyx 录像已通过。实际范围见 §10；多层布、完整 ALOHA 双臂与 T10 等未验收项单列，下面的完整矩阵不是全通过声明。**

## 1. 开发结论与任务边界

可以现在开展。用独立 FEM IPC 短绳和 PBD 布测试公共 assist，不等待 Knot 解结、Rope 穿环、Orbits 交接路径、Slotted 解环、Blanket 复杂初态或完整 planner。上述任务的初态与可解性资格只影响后续任务接入，不构成本计划的开发前置条件。

本计划落实用户本轮要求，调整[原 assist 工程计划](../tasks/assist_integration_engineering_plan_20260925_zh.md)中“先 PBD、后 IPC”的排期：共享协议完成后，FEM 与 PBD 两条路线可分别开发、分别验收、分别交付，一条失败不阻止另一条取得工具资格。这里是依赖关系说明，不要求并行 agent 或多会话实施。

目标保持当前环境自动触发合同：管理方固定模型、允许材料区域与阈值；策略仅提交现有手臂／夹爪 action；环境根据实际手位姿、开合意图和局部几何证据自动取得、保持、释放。不能增加策略侧 `attach(entity, indices)`，不能让 manager 替策略搜索远处抓点或执行 IK。

首批范围：

- FEM IPC 绳：运行时选择局部材料弧长带，以 IPC 求解器内的局部软位置约束保持；同一根绳可被两手持有互不重叠的材料带。
- PBD 布：运行时选择空间邻域与材料 UV 邻域相交的局部片，通过实际 hand link 附着；同一张布可被两手持有互不重叠的片。
- 两种后端均覆盖自动准入、独立释放、失效、跨 segment、reset 和当前 episode 内 rewind；受阻与释放连续性必须有专项结果。
- 保留刚体 `contact_weld_v1` 原合同及回归。默认继续 `none`，不批量启用正式任务、不清除其未验收缺口。

本轮不含 IPC-only 刚体抓持、同一材料点被两手同时约束的交接、真实握力标定、完整拓扑任务求解、FEM 布／PBD 绳、混合多种 assist 模型的单场景调度、批量环境及跨进程 checkpoint。首版支持在同一实体不同材料区完成“接收手取得后，原手释放”；重叠抓区明确拒绝。

## 2. 已核对的基础与真实限制

| 当前基础 | 对开发的意义与限制 |
|---|---|
| [grasp_manager.py](../../../topogym/world/physics/grasp_manager.py)、[grasp_rigid.py](../../../topogym/world/physics/grasp_rigid.py) | 已有动作意图、连续准入、事件与恢复框架；manager 的 link key、`relative_error` 和 `ideal_six_dof_weld` 读数仍带刚体假设，需要扩展。 |
| [utils/grasp.py](../../../topogym/utils/grasp.py) | 已有 `material_patch` 交集选片；缺材料区域声明、柔体候选分组、表面邻近门控与区域重叠协议。 |
| [ipc.py](../../../topogym/world/physics/ipc.py) | 当前 `SoftVertexStitch` 是建场时的永久端点连接；已有 native dump 和数值 geometry 属性恢复基础，没有临时手部约束生命周期。 |
| [fem.py](../../../topogym/world/physics/fem.py)、[FEM checkpoint 探针](../../../legacy/research_tools_20260929/tests/integration/test_genesis_fem_ipc.py) | 有 FEM 材料坐标、短管建模及永久连接测试素材，可提取为独立绳夹具；现有端点探针不是动态抓持验收。 |
| 已安装 Genesis 1.2.1 的 `PBDBaseEntity.fix_particles_to_link / release_particle`（布实体继承） | 有真实附着／释放入口，保存实际 link 局部偏移；仍需核对原生数组、碰撞范围和释放速度，不能只设置 Python `active`。 |
| [world/state.py](../../../topogym/world/state.py) | 已捕获 solver/coupler 数组；新增 Python 状态要显式保存。新增模块不自动进入数组遍历白名单，必须逐字段审计恢复覆盖。 |

静态核对还发现三项必须在实施中处理的限制：

1. `SimulatorConfig` 目前只接受 `none/contact_weld_v1`，Env 和刚体 backend 都拒绝 IPC。需要按模型选择后端和建场准备，不能只删掉拒绝条件。
2. 已安装 `FEMEntity.set_vertex_constraints()` 在 `isinstance(coupler, IPCCoupler)` 时抛异常；异常文字“only supported by IPC”与条件相矛盾。以实际分支为准，采用已验证过的 libuipc 约束适配路线。
3. PBD native attach 把粒子置为 `free=False`，保存 `particle_attach_info.link_idx/local_pos`；detach 恢复 free 并清除附着。原生跟随通过 link 速度与位置纠偏更新粒子速度，源码注明更新时序存在一帧偏差。因此“调用成功”不能替代跟随、旋转、动态释放和受阻资格。旧 unroll 还记录了绑定后穿桌无法靠碰撞纠正的问题。

固定当前支持栈 Genesis 1.2.1 / pyuipc 0.0.25。FEM IPC 真实验收需要 CUDA；PBD 可先做 CPU 机制探针，正式机器人与 Nyx 录像用 CUDA。当前核查没有执行 GPU 可用性或新场景资格测试，设备不可用只阻塞相应运行，不阻塞纯计算、协议和代码开发。

## 3. 历史成功证据与代码回收

### 3.1 成功证据的范围

- **FEM：Trefoil v9。**[归档报告](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json)的 `passed=true`、`untying_verified=true`，同时明确 `scope=local_fem_physics_only`、`robot_grasp_qualified=false`、`complete_physics_suite_passed=false`。历史有实际机器人辅助抓持、跟随与释放，不代表通用双手抓持、网格收敛或当前 simulator 接口已验收。录像和资格边界见[任务页](../tasks/knot_untying_zh.md)及[复测记录](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_recording_attempt_zh.md)。
- **PBD：Blanket simple folds / single_arm_clear_home_v1。**[归档报告](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/report.json)记录 `success=true`，有[归档复核](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/review.json)与实际运行源码快照。它使用局部辅助抓片，机器人与布料的 PBD 碰撞耦合关闭；不能把其几何邻近证据说成双指接触力，也不能继承“机器人与布料碰撞始终生效”的资格。
- **PBD 失败经验：**[cloth_unroll §2](../../../legacy/docs/develop/tasks/cloth_unroll_zh.md#2-已解决接触链)记录指垫压布入桌、绑定冻结穿桌状态，以及关闭机器人耦合带来的限制。这些用于设计负例，不能照搬关闭耦合的处理来使公共后端通过验收。

### 3.2 提取到哪里、还缺什么

| 历史来源 | 可提取内容 | 迁移工作 |
|---|---|---|
| 提交 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6` 的 `topogym/world/genesis_ipc_vertex_constraints.py` | `FollowHandle.engage/update_targets/release`、预留 `SoftPositionConstraint`、`_animate_fem_follow` 写 `is_constrained/aim_position` | 放入当前 IPC 生命周期；取消模块全局 `_SPECS/_INSTALLED` 及旧 coupler 全局替换；支持运行时材料选择和 checkpoint。 |
| [FEMRopeAttachment](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/primitives/fem_attachment.py) | `indices/attach/drive_to/band_center/release`，取得时捕获实际形状 | helper 本身仅平移，不能直接作为旋转跟随实现；不带回其任务调用与旧 import。 |
| [Knot robot_probe.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/knot_untying/robot_probe.py) 的 `close/release/update/observe` | 双指表面间隙检查、owner、手坐标系局部 offset、随实测手位姿旋转／平移、跟随健康测量 | 移除预选两条材料带、定时动作、夹爪命令副作用和私有 `_handle` 访问；取得改由 manager 自动驱动。此调查快照与 v9 运行快照分开记录身份。 |
| [Blanket 成功运行 execution.py](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/source_snapshot/execution.py) 的 `pull` 及释放／健康段 | 空间∩UV 选片、双侧 pad 几何距离、`fix_particles_to_link/release_particle`、应变保护 | 纯计算进入 utils，实际附着进入 `grasp_pbd.py`；不迁移私有执行循环、固定时间抓取及关机器人耦合的默认设置；整片而非仅中心点检查埋层和穿透。 |
| [Blanket grasp_sites.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/blanket_flatten/grasp_sites.py) 的 `exposed_boundary_site` | 材料邻域、暴露边界判断、稳定排序 | 提取几何判定。全局抓点搜索可供测试策略使用；manager 只检查真实手附近候选。 |

历史 IPC 文件可只读获取：

```bash
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/world/genesis_ipc_vertex_constraints.py
```

本次读取字节的 SHA-256，实施时核对来源并记录提取函数与改写内容：

| 来源 | SHA-256 |
|---|---|
| 上述 Git IPC 文件 | `c86943f9a5d97d1a08ed121dfc119d452ea6abe0ff74c3fd09b51b8fe7e99297` |
| 调查快照 FEMRopeAttachment | `64b84062770621ccd20d8e5a3f6b17732a05452257e5c0a79ecfc62ecd34be53` |
| 调查快照 Knot robot_probe | `3e50c420553a1891b840d036026ffd4baefe18974dcc9f009ccc45e953320502` |
| Blanket 成功运行 execution | `e5622bca85d8759307e6f26e2bc362237eeec7a13ebd89c1293fe8b849b48f48` |
| 调查快照 Blanket grasp_sites | `4365b74daae177fcc8bb0c692dbe9c60e83fe4ffb4b546c655e748eea19abaac` |

活动源码不得 import `legacy/` 或 `runs/`，不恢复逐步直接写粒子位置的旧 `ParticleAttachment`，不包装另一套 `scene.step()`，不修改已安装引擎来隐藏项目适配。

### 3.3 历史代码提取规则（2026-09-27 用户补充）

**以函数中的可复用逻辑为迁移单位，不以恢复历史文件／类为交付目标。** 历史源码仅用于阅读、提取和核对行为；新实现遵循当前 World、manager、backend 与纯计算分层。不得先恢复旧 runner 及其依赖树，再用一层 wrapper 将其包装为新后端。

| 历史逻辑 | 新落点 | 原文件中不迁移的部分 |
|---|---|---|
| `FollowHandle` 启用／停用及目标数组更新 | `grasp_ipc.py` 的原生约束适配和 backend 状态 | 全局 `_SPECS`、旧句柄对私有全局对象的依赖、旧包 import 路径。 |
| SoftPositionConstraint 注册、animator 合并 active 区域 | 当前 `ipc.py` 的 coupler 建场与子步回调 | 整份旧 coupler、全局 install、旧版 dt／材料补丁。 |
| `FEMRopeAttachment.attach` 捕获局部形状，以及 Knot 中随实测手旋转的 offset 计算 | 变换数学复用 `utils/grasp.py`；取得数据和目标生命周期进入 `grasp_ipc.py` | 原 `FEMRopeAttachment` 类壳、仅平移的控制假设、task 直接访问 `_handle`。 |
| Knot／Blanket 双指表面距离、局部选带／选片与遮挡判断 | `robot/grasp_geometry.py` 读取当前指垫；`utils/grasp.py` 做纯数组几何；backend 组织证据 | 固定抓点、全局搜索下一次抓角、闭爪／IK 命令和时间表。 |
| owner、取得／释放计时和失效事件 | 扩展现有 `grasp_manager.py` | 每个任务私有的一套 owner 字典与并行状态机。 |
| PBD attach／release 和真实绑定核查 | `grasp_pbd.py` | `execution.py` 的整条 pull／flatten 流程、私有 step 循环、全局关闭耦合。 |
| 旧健康检查中的材料应变、非有限值和穿透测量 | 优先复用现有 diagnostics；缺少的纯测量放 `utils/grasp.py`，失效处置交 manager/backend | 重复的 recorder、报表框架和按某条历史轨迹硬编码的成功判断。 |

提取步骤固定为：确认来源和函数 → 写明输入输出及原有副作用 → 去掉任务控制／全局状态 → 接入现有数据协议 → 用独立正负例与真实物理验证。来源、必要行为差异与新增限制记在目标函数注释和本计划的来源表中，不另复制一套“history restored”运行包。

这里的 attachment 指抓持所用的实际约束能力，当前代码仍统一使用 `grasp_*` 命名。**不另建与它并存的 `attachment/` 框架，不恢复 `primitives/attachment.py`、`primitives/fem_attachment.py`、`world/genesis_ipc_vertex_constraints.py` 或旧任务 runner 的活动版本。** 已有 `AttachmentSpec` 仍只表示永久端点连接，临时手部抓持不混入该声明。

## 4. 公共协议与修改位置

模型名暂定 `ipc_soft_band_v1`、`pbd_local_patch_v1`，准确描述各自物理机制；`contact_weld_v1` 保持原意。首版每个配置选择一种 assist 模型，模型与场景材料不匹配时明确拒绝。

**修改范围复核（2026-09-27）：本轮没有发现需要重做刚体抓持或重新标定机器人指垫的依据。** 下表与目录区分“柔体新增”“共享接入”“最小接口适配”“复用／条件修改”，不能把涉及的文件全部理解为必须重写。

- **必须接入共享层：**现有 manager 在 `after_tick` 无条件调用刚体 `relative_pose/relative_error`，按完整 target key 判断独占，`read` 写死刚体接触证据和六自由度 weld。柔体应增加材料区域冲突、后端健康和模型读数；config/Env/World 还需要接受新模型、分派后端并保存其状态。只增加两个柔体文件不能通过现有入口使用。
- **刚体后端仅最小接口适配：**将 manager 原有相对位姿检查移到刚体后端，保持原阈值、错误原因及原有判断优先级；需要时补冲突／模型读数的薄接口。现有双指接触门控、weld 创建／删除、开合规则、碰撞设置及物理参数不扩展、不重做。旧刚体回归应原样通过。
- **机器人描述默认复用：**当前已有 finger_links、开合坐标、hand_link 与 TCP；新增几何读取模块先使用这些字段和原生 link 碰撞几何。只有实际核查证明一个 finger link 包含不能作为准入表面的其他几何、现有字段无法唯一选出所需表面时，才按具体机器人补充可选表面选择字段。描述文件和对应测试由无条件修改收窄为条件项；不改变机器人模型、夹爪尺寸、home、TCP 或开合标定。
- **已有状态／材料工具先审计再决定编辑：**`WorldState.grasp_state` 可承载扩展状态，FEM 已有材料坐标。新增内容能放进现有机制时直接复用 `state.py/fem.py`；只有明确字段遗漏或读取接口不足时才修改，避免为本轮开发做无关重构。

| 文件／位置 | 拟交付内容 |
|---|---|
| `topogym/utils/grasp.py` | 柔体目标声明、候选材料区域、重叠判定和确定性选区；保留既有刚体声明兼容性。定义清楚实体局部材料坐标、空间距离与长度单位。 |
| `topogym/world/physics/grasp_manager.py` | 保留开合意图、连续准入、失效锁存与事件；把硬编码刚体健康比较移交 backend，把实体/link 独占扩展成后端声明的材料区域冲突；按模型输出诊断。 |
| `topogym/world/physics/grasp_rigid.py` | 仅做公共 backend 的最小接口适配，等价承接原 manager 中的刚体健康检查；实际 weld 查询、独立删除、准入阈值和旧事件语义保持。 |
| 新增 `topogym/world/physics/grasp_ipc.py` | FEM 材料带选择、准入证据、临时约束槽、目标更新、健康与 backend 状态。 |
| 新增 `topogym/world/physics/grasp_pbd.py` | PBD 材料片选择、整片健康检查、原生 attach/detach 与状态核查。 |
| `topogym/world/physics/ipc.py` | 在现有 EpisodeIPCCoupler 中预留／注册临时约束和 animator，保持永久 stitch 与临时手部约束分离，扩展 native checkpoint 属性审计。 |
| `topogym/world/genesis_world.py`；`world/state.py` 先复用 | World 增加模型分派、建场前准备、初始化后的启用、逐 tick 更新与 manager/backend 成对恢复；state.py 仅在现有状态容器／数组捕获遗漏新状态时修改。仍由 World 唯一推进物理。 |
| `topogym/simulator/config.py`、`simulator/env.py` | 解析并公开静态材料抓取合同；建场前按模型预留资源；按能力而非统一 IPC 禁令校验配置。普通 action 不变。 |
| `topogym/robot/description.py` 及机器人描述（复用／条件修改） | 优先复用现有 finger link、开合和 TCP；仅在实际碰撞表面选择存在歧义时增补可选描述，禁止复制某任务固定偏移和夹爪常数。 |
| 新增 `topogym/robot/grasp_geometry.py` | 从显式机器人描述读取实际指垫碰撞表面和手部坐标变换，供两种柔体 backend 共用；不包含抓取状态机、动作或 step。 |
| `topogym/tasks/base.py`、`world/physics/pbd.py`；`world/physics/fem.py` 先复用 | 在 EntitySpec 增加可选材料映射资源声明；PBD build 后绑定并验证粒子 UV，FEM 复用已有 entity.material_coordinates，仅在读取不足时补适配；无新声明的现有实体保持原行为。 |
| `tests/fixtures/soft_grasp.py`、`tests/fixtures/soft_grasp_policy.py`（拟新增） | 前者只在测试中注册短绳／小布片 Task、生成初态与配置，后者提供输出普通 action 的短策略；不加入正式 13 项目录。 |
| 专用 unit/integration 测试与 `scripts/test_grasp_assist.py` | 增加柔体 case，沿用独立源码快照和公共证据；扩展引擎哈希，不能只记录 rigid solver 身份。 |

backend 协议至少覆盖：`candidates`、`acquire`、`release`、`exists/verify_bindings`、材料冲突判断、模型专属健康读数、逐步目标更新及自身 `capture/restore`。刚体姿态误差继续在刚体 backend 核查；柔体用选中材料相对实测手部目标的误差、有限性、应变和穿透判断，不能将整根绳／整张布套入六自由度姿态误差。

绑定记录至少包含：schema/model、hand、entity、材料坐标映射身份、确定的粒子／顶点索引、取得时手局部 offset、原生槽／link 身份、证据种类与采样时间、准入／失效计时、owner、目标和事件。公开静态配置不包含运行时位置、动态候选或接触真值。

运行时候选应把空间邻近且材料连续的点归成局部带／片，再在手附近确定中心；不能把同一片上的每个顶点都当作互相歧义的目标。空间相近但材料不连续的绳腿／布层分开判断；多个不可消解候选拒绝，禁止“半径内没有点就改抓最近点”。

### 4.1 新增运行时脚本：每个文件的交付边界

实施时新增四个运行时文件：原计划三个适配文件，以及 `grasp_soft.py`。后者集中两种柔体共用的材料选区、冲突、实际手坐标偏移、健康和 checkpoint 状态，避免在两个后端重复这些逻辑；原生约束仍由各自后端负责。

| 新增文件 | 拟定类／接口与主要逻辑 | 不承担的职责 |
|---|---|---|
| `topogym/world/physics/grasp_soft.py` | `SoftGraspBackend`；材料连通区、局部空间∩材料选区、owner 冲突、实际手局部 offset、健康与 backend capture/restore。 | 不推进物理、不实现原生 attach/detach、不读取任务私有抓点。 |
| `topogym/world/physics/grasp_ipc.py` | `IPCGraspBackend`；建场资源声明；`candidates/acquire/release`；活动材料带和真实约束核对；根据实测手位姿更新目标；健康与 `capture/restore`。读取纯计算选区和共享指垫快照。 | 不复制 IPC 初始化／checkpoint 引擎，不操作夹爪命令，不拥有物理循环。 |
| `topogym/world/physics/grasp_pbd.py` | `PBDGraspBackend`；`candidates/acquire/release`；PBD 原生 free/link/offset 核查；材料片应变、暴露和穿透健康；`capture/restore`。 | 不恢复 BlanketExecution，不处理任务展平判据，不改视觉 skinning。 |
| `topogym/robot/grasp_geometry.py` | `read_grasp_geometry(robot, hand)` 等只读入口；从已声明的 finger link／碰撞几何获得实际世界坐标表面、hand pose、TCP 和采样身份；静态几何缓存限定当前 World。 | 不选择任务目标、不 attach、不发 action、不维护 owner；纯距离计算仍放 utils。 |

### 4.2 现有运行时脚本：必要修改与条件项

| 修改文件 | 本轮应修改的部分 |
|---|---|
| `topogym/utils/grasp.py` | 扩展 `GraspAssistConfig` 的模型／柔体目标解析；新增材料范围与绑定数据声明、候选分组、区域冲突、整片暴露和表面距离纯计算。复用已有四元数、相对变换和 `material_patch`，不再复制历史数学函数。 |
| `topogym/world/physics/grasp_manager.py` | 在现有 `before_tick/after_tick` 中接后端接口；将刚体相对位姿健康移入刚体后端；增加材料区冲突判断；`capture/restore/read` 纳入 backend 状态和模型读数。统一取得／失效／释放事件，不建立第二个 manager。 |
| `topogym/world/physics/grasp_rigid.py`（最小接口适配） | 等价承接 manager 原有刚体相对位姿检查，保留阈值、失败原因及判断优先级；按需提供模型读数／冲突接口。既有真实 weld 查询、独立删除、双指门控和物理行为不变。 |
| `topogym/world/physics/ipc.py` | 在当前 `EpisodeIPCCoupler` 增加 build 前临时约束声明、finalize 注册和求解前目标更新钩子；扩展 `CheckpointStore` 的属性覆盖核查。保留 `_create_attachments` 永久连接路径，不混用临时抓带。 |
| `topogym/world/physics/pbd.py` | 增加 build 后材料映射绑定／读取适配：将声明的 authored 几何和材料坐标映射到实际粒子，验证索引、单位、歧义、身份。运行时 attach 仍在 `grasp_pbd.py`。 |
| `topogym/world/physics/fem.py`（复用／条件修改） | 先复用既有材料坐标与 `add_volume` 稳定顶点映射；确有表面／体顶点读取缺口时才补适配；不重建历史 rope entity。 |
| `topogym/world/genesis_world.py` | 增加建场前 grasp 资源准备；build 后材料映射检查；`configure_grasp` 按模型分派；`advance` 复用原 tick 与 coupler 子步时序；读数和恢复覆盖后端。 |
| `topogym/world/state.py`（复用／条件修改） | 先将新 backend 状态纳入 manager 的 `grasp_state` payload，审计现有数组捕获；仅发现明确漏项才改此文件。payload 版本由 manager/backend 管理，不因版本变化自动修改通用 WorldState。恢复先物理、后 backend/manager 核对。 |
| `topogym/simulator/config.py` | 支持新模型和柔体声明的不可变配置、JSON 往返及参数校验；保留默认 none 和旧刚体配置。 |
| `topogym/simulator/env.py` | reset/build 前传递资源声明；按后端能力校验 IPC/PBD；初始化完成后启用；更新公开静态合同与身份，复用原 action/segment 流程。 |
| `topogym/tasks/base.py` | 为 `EntitySpec` 增加默认空的材料映射资源声明（拟 `material_map_path`，精确格式在 S1 冻结）；资源提供 authored 顶点、拓扑、材料坐标及身份，World build 后生成真实粒子映射。`AttachmentSpec` 保留永久连接含义。 |
| `topogym/robot/description.py`（复用／条件修改） | 现有 `GraspDescription.finger_links/open_position/closed_position` 先直接使用。只有 link 上碰撞几何无法唯一表达准入表面时，才补可选表面选择信息；不重做指垫描述系统。 |
| `topogym/robot/aloha/description.py`、`topogym/robot/panda_robotiq/description.py`（复用／条件修改） | 沿用既有 finger link、hand/TCP、开合坐标与 home；只有上述歧义确实出现在该机器人时补字段，另一机器人不连带修改。 |

材料映射由建场资源与实际采样关系确定，不能从已经折叠的当前 XYZ 最近邻猜 UV。已有 Blanket `material_coordinates` 算法可审查提取其通用数学，但不从 Task 私有 `material_uv` 取依赖，也不恢复整套 Blanket 几何／执行脚本。若某种采样结果不能唯一绑定材料，建场明确失败；在 fixture 中先固定可验证的映射。

`pbd_initial_state.py`、`pbd_binding.py`、正式 `tasks/<task>/`、资产生成器、recording 和 rollout 调度模块首批复用现有接口，不列为默认修改范围。若验证发现必要的状态字段遗漏或 PBD 原生约束适配缺口，先在本表补充具体文件／函数、原因和测试，再做最小增量修改；不预建空壳模块。`config/registry.py` 不批量清除任务缺口，独立测试 Task 仅临时注册。

### 4.3 新增／修改测试与交付脚本

| 操作 | 文件 | 覆盖内容 |
|---|---|---|
| 新增 | `tests/fixtures/soft_grasp.py` | 独立短绳、布片、双层、双手、永久连接和障碍变体；资产／材料映射写本次临时运行目录；负责 Task 声明与测试注册。 |
| 新增 | `tests/fixtures/soft_grasp_policy.py` | 短程接近、闭合、抬起、转动、释放策略，复用当前 policy 合同。只输出普通 action；测试参数由管理方冻结，不接触 backend/scene。 |
| 新增 | `tests/unit/test_soft_grasp.py` | 材料选区和分组、叠层／绳腿歧义、owner 重叠、配置、后端状态版本和恢复；使用明确 fake backend 测状态机。 |
| 新增 | `tests/unit/test_grasp_geometry.py` | 指垫坐标变换、表面范围和几何证据的正负例；验证双指、采样身份及非有限数据拒绝。 |
| 新增 | `tests/integration/test_grasp_ipc.py` | FEM 真实约束、移动目标、释放、永久连接保留、故障注入及 T0–T10。 |
| 新增 | `tests/integration/test_grasp_pbd.py` | PBD 原生附着、free/offset 恢复、层选择、应变、碰撞范围、释放与 T0–T10。 |
| 新增 | `tests/integration/test_soft_grasp_mechanism.py` | 参数化两种材料的真实双夹爪、无 assist 对照、原生约束与故障恢复；标准 Panda rollout 共用 `test_grasp_pbd.py` 的 harness，由 `test_grasp_ipc.py` 复用，避免另建重复 runner。 |
| 修改 | `tests/unit/test_grasp_assist.py` | 保留既有刚体断言，并检查共享协议变更后原意图、释放和恢复行为一致。 |
| 修改 | `tests/unit/test_configuration.py`、`tests/unit/test_task_definitions.py` | 分别覆盖新配置与往返、可选材料声明的兼容性。 |
| 复用／条件修改 | `tests/unit/test_robot_descriptions.py` | 原测试直接作为回归；只有实际增加了可选表面字段才新增相应断言。 |
| 修改 | `scripts/test_grasp_assist.py` | 扩展现有 `--case`；保存当前源码／生成资产／依赖和 FEM/PBD 引擎文件哈希；复用原隔离执行与失败落盘。不新增另一套 test runner。 |
| 修改 | `docs/develop/modules/grasp_assist_zh.md`、`tests/README.md`、`scripts/README.md` | 实施后补两种模型使用、准确支持范围、真实测试命令与报告／视频链接。 |

已有 `test_grasp_assist.py`、`test_grasp_robot_runtime.py`、`test_genesis_fem_ipc.py`、`test_simulator_segments.py` 和 `test_pbd_initial_state.py` 作为回归入口复用，不为每个后端复制其框架。必要改动限定夹具适配及新增合同断言；不修改原通过条件来掩盖回归。

### 4.4 开发后的目录结构（拟定，非当前已实现）

以下只列本次相关文件，省略其他现有模块。`[新增]`、`[修改]` 是计划状态；`[适配]` 限于保持行为的接口调整；`[复用*]` 表示默认不编辑，仅在上表的具体缺口被确认时修改；`[复用]` 表示保留原入口。均不能据此认为已运行验收。

```text
topogym/
├── utils/
│   └── grasp.py                          [修改] 声明、选区、冲突与纯几何
├── robot/
│   ├── description.py                    [复用*] 现有指垫描述
│   ├── grasp_geometry.py                 [新增] 实际指垫／手部几何读取
│   ├── aloha/description.py              [复用*] ALOHA 具体描述
│   └── panda_robotiq/description.py       [复用*] Robotiq 具体描述
├── world/
│   ├── genesis_world.py                  [修改] 唯一生命周期、后端分派
│   ├── state.py                          [复用*] 现有状态容器与数组恢复
│   └── physics/
│       ├── grasp_manager.py              [修改] 唯一自动抓持状态机
│       ├── grasp_rigid.py                [适配] 原刚体行为保持
│       ├── grasp_soft.py                 [新增] 两种柔体共用材料区域与状态
│       ├── grasp_ipc.py                  [新增] FEM IPC 材料带后端
│       ├── grasp_pbd.py                  [新增] PBD 局部材料片后端
│       ├── ipc.py                        [修改] 原生约束／子步／checkpoint
│       ├── fem.py                        [复用*] 既有 FEM 材料坐标
│       ├── pbd.py                        [修改] PBD 材料映射适配
│       ├── pbd_binding.py                [复用] 视觉绑定读取
│       └── pbd_initial_state.py          [复用] 初态资源身份边界
├── simulator/
│   ├── config.py                         [修改] 管理方辅助配置
│   ├── env.py                            [修改] 建场准备与静态合同
│   └── rollout_simulation/               [复用] 现有 policy/segment 执行
├── tasks/
│   └── base.py                           [修改] 可选材料映射声明
└── recording/                            [复用] 公共录制

tests/
├── fixtures/
│   ├── soft_grasp.py                     [新增] 材料夹具与测试配置
│   └── soft_grasp_policy.py              [新增] 仅输出 action 的短策略
├── unit/
│   ├── test_soft_grasp.py                [新增]
│   ├── test_grasp_geometry.py            [新增]
│   ├── test_grasp_assist.py              [修改]
│   ├── test_configuration.py             [修改]
│   ├── test_task_definitions.py           [修改]
│   ├── test_robot_descriptions.py         [复用*]
│   └── test_pbd_initial_state.py          [复用]
├── integration/
│   ├── test_grasp_ipc.py                 [新增]
│   ├── test_grasp_pbd.py                 [新增]
│   ├── test_soft_grasp_mechanism.py       [新增] 双夹爪、无 assist 对照及状态恢复
│   ├── test_grasp_assist.py              [复用] 刚体真实机制回归
│   ├── test_grasp_robot_runtime.py        [复用] 刚体机器人回归
│   ├── test_genesis_fem_ipc.py            [复用] 原生 FEM checkpoint 回归
│   └── test_simulator_segments.py        [复用]
├── runtime_evidence.py                   [复用] 现有物理证据工具
└── README.md                             [修改]

scripts/
├── test_grasp_assist.py                  [修改] 唯一抓持验收 CLI
└── README.md                             [修改]

docs/develop/modules/
├── grasp_assist_zh.md                    [修改] 实施后的模型用法及资格
└── soft_grasp_assist_engineering_plan_20260927_zh.md
                                         [本计划] 来源、边界、进度与目录

runs/test_results/soft_grasp_<date>_<run_id>/
                                         [运行时生成] 源码／配置／资产身份、
                                         分 case 报告、状态与公共录制 MP4
```

### 4.5 调用与依赖归属

静态配置经 Env 交给 World，World 管理材料映射、建场准备和唯一 `GraspManager`；manager 调用当前模型 backend。两个柔体 backend 共同使用 `utils/grasp.py` 的纯计算和 `robot/grasp_geometry.py` 的实测几何。

FEM backend 与现有 IPC coupler 之间通过 World 配置的场景内钩子交换约束数据，`ipc.py` 不反向调用 Task/planner；PBD backend 通过实体原生接口附着，manager 不接触原生数组。测试策略仅调用现有 Interaction，测试 harness 负责配置、证据与验收。`runs/` 和 `legacy/` 在运行时依赖图中没有位置。

## 5. FEM IPC 实施要点

1. **建场准备。** 在现有 coupler finalize 前注册 SoftPositionConstraint 与固定容量的属性/槽。覆盖允许抓取的材料范围，建场时不选定本轮实际抓点、不激活约束。不得通过无限建场开销掩盖设计问题；记录顶点量、初始化耗时和显存。
2. **运行时选带。** 从实际手附近的表面候选确定材料弧长范围，再选取对应体网格顶点；明确表面索引与体顶点映射，不能假定 tetgen 前后索引相同。拒绝跨越空间相邻但弧长远离的绳腿；永久连接／固定材料区首版不允许成为手部抓区。
3. **准入。** 使用实际双指碰撞表面到同一局部材料表面的距离及穿透/遮挡检查，证据命名为 IPC 表面邻近，不冒充 rigid solver 双指力证据。距离、持续时间、片宽与刚度进入固定配置和日志。
4. **取得与跟随。** 取得时捕获当前顶点位置，计算 `offset_i = R_hand^-1 (x_i - p_hand)`；随实际手位姿更新 `target_i = p_hand + R_hand offset_i`，禁止跟随尚未实现的命令位姿。目标进入 IPC Newton 求解，不直接重置顶点。
5. **更新时序。** 在当前 coupler 完成刚体姿态同步后、IPC 求解前更新目标；核对当前子步使用的实际手姿态与诊断身份，不随意包一层 step。先清空本后端可控区域，再合并所有 active 抓带，未激活邻带不能擦掉另一只手。
6. **释放与恢复。** 只关闭指定手的约束，永久 stitch 和另一只手保留；不归零速度。build 时预分配 checkpoint 所需属性，核查 `CheckpointStore` 缓存的属性槽包含新约束；native restore 后恢复 Python active/owner/targets/offsets 并核对真实属性。不重新选择材料带。
7. **物理资格。** 先做小幅抬升和平移／转动，再做受阻与释放；记录跟随误差、体积 Jacobian、轴向应变、长度、接触穿透与求解失败。若 SoftPositionConstraint 未提供可验证的握力，保持力输出不可用，不声称力限抓持。

## 6. PBD 布实施要点

1. **材料身份。** 为 build 后物理粒子建立并校验固定 UV；与视觉 skinning 的索引/权重分开。平布与双层 fixture 都从 authored 材料映射产生，不依赖 Blanket 冻结资源。
2. **局部选片。** 复用空间∩UV 交集，增加材料连通性和整片暴露／穿透检查。叠层用不同材料邻域区分；不能仅因为中心暴露，就附着已埋入另一层或桌下的粒子。候选以实际双指几何邻近证据准入。
3. **原生附着。** 优先适配 `fix_particles_to_link`，核对每个索引的 free、link_idx、local_pos 与取得时真实位置；位移与旋转均跟随实测 hand link。记录该模型为局部运动学附着，不能冒充有限握力或完整双向受力耦合。
4. **释放与恢复。** 只对本手持有的索引调用 `release_particle`，不影响另一片和永久固定粒子。确认位置连续、速度未被任意清零，检查下一步没有异常冲量。恢复 free、attach_info、位置/速度、排序/邻域缓冲和 Python 状态；保持视觉绑定身份。
5. **必须先验证碰撞范围。** 已知原生 free=False 附着不能直接继承自由粒子的全部碰撞资格；当前引擎更新还有时序限制。分别测试绑定片与障碍、自由布面与障碍、指垫与布、桌面和自接触，不从普通平布抬起推断全部合格。
6. **受阻不通过时的处理。** 记录失败和模型限制；增加项目内可维护的局部 compliant 约束适配或抓片扫掠/穿透健康保护后重新验收。健康保护触发失效与释放只能算受控失败，不算物理受阻保持通过；不能为了通过而关闭机器人耦合、屏蔽障碍、直接改粒子位置或放宽阈值。旧原生 attach 可交付为有明确范围的工具，但碰撞资格未齐时不能宣称完整后端验收完成。
7. **应变保护。** 整片及邻接布面记录材料边长比、局部面积/退化、跟随误差；过度拉伸触发失效并留存状态，阈值提前固定。不把因保护而松手算成策略主动完成放置。

## 7. 独立测试场景与验收矩阵

每种材料单独建场，材料、网格、dt/substeps、接触设置、机器人、seed、准入与健康阈值均写入 fixture 配置。fixture 尺度由当前夹爪可达与网格预检确定，正式运行前冻结；历史毫米阈值不直接复制为通用常数。

| 测试夹具 | 目的 |
|---|---|
| `fem_rope_free`：桌面稳定短绳，无结、无任务器具、无预抓持 | 从实际接近开始，选任意允许弧长带，取得、抬升、转动、放下、释放。 |
| `fem_rope_dual`：同一根较长短绳，两处分离材料带 | 双手同时／先后取得、不同次序释放、接收手持另一带再原手退出；近邻绳腿与重叠申请反例。 |
| `fem_rope_stitched`：额外带有声明的永久端点连接 | 临时约束建立、释放、失败和 rewind 不破坏永久连接。独立于无永久连接的基础夹具。 |
| `pbd_cloth_flat`：稳定小矩形平布，可接近边缘 | 单手局部抓片、转动、放下与释放；未选中布面继续自由变形。 |
| `pbd_cloth_layers`：稳定简单折叠／局部双层布 | 暴露层选片、埋层拒绝、材料邻域防跨层；不使用复杂八面板初始化。 |
| `pbd_cloth_dual`：同一张布的分离区域 | 两手分片、交错释放、重叠冲突及过应变失效。 |
| 两后端障碍变体 | 抓持材料/自由材料/夹爪分别接近桌面或明确障碍，验证碰撞范围、受阻行为或明确失败。 |

测试分两层：先可控双指机械夹具完成机制与故障注入，再用实际 Panda/Robotiq 单手和 ALOHA 双手经标准 Env/Interaction/SegmentRunner 验证集成。正式机器人从默认 home 连续运动，不能以预抓取初态替代取得。

| 编号 | 必须验证的行为 | 通过标准／证据 |
|---|---|---|
| T0 | 夹具无 assist 初态 | 重力、支撑与静置合格，无预抓约束；不合格先修夹具。 |
| T1 | 空夹、单指、超距离、错误区域、跨时刻双指、埋层／错误绳腿 | 均无原生绑定；错误原因和材料候选可审计。 |
| T2 | 持续普通闭合 action 自动取得 | 达到固定采样时间才取得；不改变 action 合同；单个实体的连续材料区不会产生伪歧义。 |
| T3 | 取得与保持 | 取得调用前后位置连续；平移、转动、短暂停握的误差在预设阈值内；自由材料仍受重力和材料约束。 |
| T4 | 同实体双手与冲突 | 分离材料区域可并持；索引重叠及声明保护邻域冲突拒绝，遍历顺序不决定 owner。 |
| T5 | 独立释放／再次取得 | 两个释放顺序均通过；另一手和永久约束不变；释放后位置/速度连续且自由物理续跑正常。 |
| T6 | 障碍与健康失效 | 报告所有碰撞组合；不得穿透取巧。原生物理受阻、保护性释放和未防住穿透分别记录，后两者不能记为受阻保持通过。 |
| T7 | rewind | 回到准入中、取得前、取得后、双手持握、单手释放后、全部释放后，重复同一 action 分支；比对索引、owner、offset、targets、约束数组、计时、事件与数值物理状态。 |
| T8 | 非法 action／部分失败 | 非法输入无物理副作用；在约束激活／释放写入后故意抛错，World fault，恢复已有 checkpoint 后残留清除且可继续。 |
| T9 | reset／权限／segment | reset 清空，旧句柄失效；普通与特权相同 action 等价；跨 segment 持握不变；observe/render 不推进 manager 或目标。 |
| T10 | 离散化与性能 | 每后端至少比较两档网格分辨率、两档 dt/substeps 的短抓放，预先固定容差，说明稳定范围及耗时/显存/checkpoint 成本；这不代替完整 FEM 网格收敛研究。 |
| T11 | 机器人录像与现有刚体回归 | 当前源码快照下完成 home→接近→取得→移动→释放→撤手；标准 Nyx 多视角与逐 tick 证据一致；原刚体关键行为无回归。 |

位置／速度连续性分别检查“切换约束的瞬间”和后续物理步；不能把正常重力积分误差算作切换跳变，也不能只比较截图。确定性比较同时记录数值容差、属性精确一致性和事件顺序，不假定不同 GPU 或网格之间逐位相同。

## 8. 实施顺序与完成条件

| 阶段 | 工作 | 退出条件 |
|---|---|---|
| S0 证据固定与夹具定义 | 保留本节历史身份；冻结当前依赖和适配点；建立独立 fixture、阈值、报告及录像入口 | 静置夹具可运行；材料映射与准入证据可读；仍未把无辅助稳定视为抓持成功。 |
| S1 共享协议 | 配置、材料选择/分组、区域 owner、backend 健康与状态协议；适配刚体实现 | 纯计算负例、manager 状态机、序列化和现有刚体关键回归通过。 |
| S2-F FEM 路线 | 临时约束预留、动态材料带、目标跟随、释放与 native 恢复 | FEM 机制 T0–T10 有明确结论；不等待 S2-P。 |
| S2-P PBD 路线 | UV、局部选片、原生附着、碰撞范围审计、必要适配及完整恢复 | PBD 机制 T0–T10 有明确结论；碰撞缺口未解决保持部分完成；不等待 S2-F。 |
| S3 标准机器人验收 | 分别接入短策略、单手／双手、segment、Nyx 与证据归档 | 每个后端独立通过相应 T0–T11，报告配置适用范围、失败与限制。 |
| S4 任务侧后续接入 | 工具合格后，由目标 Task 提供材料可抓范围与接近策略 | 逐任务另验。不是本轮公共材料抓持交付的必需项。 |

S0 的运行资格是后端物理验收前置，不阻止 S1 纯计算与协议开发。S2 初期可以直接调用 backend 做窄接口探针，但最终资格必须由环境自动触发，不能以显式 attach 的单元探针替代 T2/T11。

**每个后端“开发完成”要求：**真实原生约束有效、自动准入和双手分区行为正确、释放及所有恢复节点通过、碰撞资格或限制如实可验、标准机器人链路和现有刚体回归完成。只有简单抓起视频、只有 Python active 标志、只有旧成功报告均不足以完成。若只能交付受限模式，单独标明已通过的范围和未完成项。

## 9. 证据、共享文件与后续运行入口

本轮已进入实施。运行产物放 `runs/test_results/soft_grasp_<date>_<run_id>/`，每个后端／case 独立报告，沿用公共录制模块与当前证据框架。源码快照、配置、生成资产、依赖版本及引擎关键文件都记录 SHA-256；历史来源与本次实现身份分开。

报告至少记录 material mapping、实际粒子/顶点索引、准入表面距离、原生绑定字段、活动槽、offset/targets、跟随和应变、穿透、释放前后 x/v、全部事件、checkpoint 分支、最终残留约束数，以及 dt、采样覆盖范围与物理模型身份。失败保留最后有效 checkpoint 和异常阶段，不能被后续成功覆盖。

机制探针可明确关闭 RGB；正式机器人资格复用 Nyx + compact_lab 和公共 RecordingSession，单臂三路、双臂四路。读状态、录像和 segment 边界不新增物理步；冻结状态重渲染声明为重渲染。视频仍使用 MP4，不另建进展 HTML。物理与视觉复现分别报告。

已扩展已有脚本的 `--case` 为 `fem-mechanism`、`pbd-mechanism`、`fem-robot`、`pbd-robot`。实际已覆盖范围单独记录；以下为可执行命令：

```bash
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-mechanism --output runs/test_results/soft_grasp_fem_mechanism
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case pbd-mechanism --output runs/test_results/soft_grasp_pbd_mechanism
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-robot --output runs/test_results/soft_grasp_fem_robot
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case pbd-robot --output runs/test_results/soft_grasp_pbd_robot
```

共享修改点是 config/env、World/state、manager、robot description 和 TaskSpec；按函数增量合并，不覆盖其他会话修改。独立 fixture 不改正式 tasks/assets/default setting。World/state 变化会使旧 Blanket 冻结初态严格源码身份失效；使用那些资源的会话需重新导出并复验，不能放宽校验。本计划夹具从自有 authored 初态建立，因而不等待该重导出。

实施中只更新与实际能力相符的文档和 registry：工具通过不自动清除四个 FEM Task 或 Blanket 的场景级抓持资格缺口。最终交付为代码、独立测试入口、分后端报告与视频链接、已知限制及使用示例。

## 10. 本轮实际实现与验收记录

### 10.1 已落地的文件边界

两种柔体模型已接入当前 Env 的自动 manager。策略只有普通手臂／夹爪动作，未增加显式 attach action。永久 `AttachmentSpec` 和临时 grasp 分开管理。history 只提供局部选区、局部偏移和原生约束接法的参考，没有恢复旧 Task 执行器或第二套 step／录像循环。

实际新增四个运行时文件：

```text
topogym/
├── robot/grasp_geometry.py          # 现有 finger 描述 → 实际碰撞三角面
└── world/physics/
    ├── grasp_soft.py                # 两种柔体共用的准入、材料区、健康和状态
    ├── grasp_ipc.py                 # 临时 SPC flags／目标／原生核查
    └── grasp_pbd.py                 # 粒子 link 附着／释放／速度参考点适配
tests/
├── fixtures/{soft_grasp,soft_grasp_policy}.py
├── unit/{test_soft_grasp,test_grasp_geometry}.py
└── integration/
    ├── test_soft_grasp_mechanism.py # 同一机械夹具分别跑 FEM／PBD
    ├── test_grasp_pbd.py            # 标准机器人、两段 policy、释放和回溯
    └── test_grasp_ipc.py            # 复用上述 runner 的 FEM 入口
scripts/test_grasp_assist.py         # 扩展现有隔离验收入口
```

必要的现有代码增量为 `utils/grasp.py`、`grasp_manager.py`、`grasp_rigid.py`、`physics/ipc.py`、`physics/pbd.py`、`genesis_world.py`、`simulator/config.py`、`simulator/env.py`，以及 `tasks/base.py` 的可选 `material_map_path`。**本轮没有修改 robot description、指垫参数、home、TCP、`physics/fem.py` 或 `world/state.py`。**刚体后端仅接回原 manager 的相对位姿健康判断，保留原优先级与阈值。

现有 unit 文件复用为回归；新增断言集中在新测试文件，没有为完成计划表而改写原通过条件。

### 10.2 真实运行中发现并处理的问题

- PBD 的两个指面通常接近同一片的不同顶点。准入已改为同一材料片内双侧证据，并增加该情况及跨材料误抓负例，避免要求同一顶点同时靠近两指。
- PBD 14 mm 半径选片在小夹口中跨到指外，碰撞与固定片冲突造成拉伸失效。独立夹具现使用空间半径 6 mm、材料半径 9 mm；保护阈值未放宽。选择范围属于建场配置，不能由 policy 临时指定。
- Genesis 1.2.1 `LegacyCoupler.kernel_pbd_rigid_solve_animate_particles_by_link` 的速度参考点与 `RigidSolver.get_links_vel` 不一致。PBD 后端在本场景 coupling 后为自己拥有的粒子补 `cd_ang × i_pos`，不修改安装包、不设置位置，也不影响未参与 assist 的粒子。原生更新晚一个子步的限制仍存在。
- 原生 PBD 刚体碰撞仍处理 attached 粒子，而内部材料约束不再移动这些粒子；因此本模型是有显式失效保护的运动学局部附着，不能据此宣称柔顺夹持或完整受阻保持。
- 小型 IPC 机械夹具最初漏建标准场景的 ground Plane，出现无 assist 对照也不稳定／原生异常。修正夹具并复用项目 `scene_options` 后重新验收；失败目录保留。最终实现未采用调试期间试过的 robot 自碰撞过滤改动。
- Robotiq 从完全张开直接在薄布上闭合会扫过桌面。fixture policy 改为在桌面上方预收拢，再连续接近实际材料点；仍从标准 home 开始，全部通过普通 action 和 SegmentRunner。

### 10.3 已取得的证据

以下每项只对应各自目录的不可变源码／配置快照。失败尝试同样保留；后续新增资格在此续记。

| 检查 | 结果与范围 |
|---|---|
| 相关 unit 回归 | 87 passed；覆盖新材料／表面几何，以及原刚体、配置、Task 声明、机器人描述、控制模式、PBD 初态。 |
| 原刚体真实机制回归 | `soft_grasp_20260927_rigid_regression` 通过。 |
| PBD 双机械夹爪 | [报告](../../../runs/test_results/soft_grasp_20260927_pbd_mechanism_11/evidence/report.json)通过：无 assist 稳定对照、分区并持、平滑转动抬升、两种释放顺序、持握回溯数值重放、出生回溯、非法 action 原子性、创建原生约束后故障恢复、reset 和旧句柄失效。 |
| PBD 碰撞／永久固定负例 | 同上；桌面阻挡触发 `material_strain` 保护性释放，永久固定边界负例保留原固定点；没有将其记为受阻保持。 |
| FEM 双机械夹爪与永久连接 | [报告](../../../runs/test_results/soft_grasp_20260927_fem_mechanism_12/evidence/report.json)通过；覆盖双区并持、两个释放顺序、持握动力学重放、非法 action、部分失败恢复和 reset。桌面负例实际受阻保持；临时抓持释放后永久端点残差 2.66e-6 m。正常阶段最大跟随误差 0.720 mm、最大材料边长比 1.170。 |
| PBD 标准 Panda 物理流程 | [报告](../../../runs/test_results/soft_grasp_20260927_pbd_robot_08_cpu/evidence/report.json)通过；默认 home、两段 policy 完成抓取／搬运／释放／撤手及持握／出生回溯，无 lost。释放后布面最低点高于桌面约 3 mm，最大粒子速度 0.0264 m/s 以下；该次明确关闭 RGB。 |
| PBD 最终 Panda＋Nyx | [报告与六路分段视频](../../../runs/test_results/soft_grasp_20260927_pbd_robot_09_rgb/README.md)通过；两段共 11.425 s，抬升 46.79 mm，最大跟随误差 0.204 mm、材料边长比 1.0691，无 lost，持握／出生回溯通过。三视角各两段完整解码，分辨率／帧率／帧数同步验证通过。 |
| FEM 最终 Panda＋Nyx | [报告与六路分段视频](../../../runs/test_results/soft_grasp_20260927_fem_robot_02_rgb/README.md)通过；当前材料片准入与策略，两段共 10.9 s，抬升 45.98 mm，最大跟随误差 0.211 mm、材料边长比 1.00583，最小体积 Jacobian 0.99666 以上，无 lost，持握／出生回溯通过。三视角各两段完整解码、帧数同步验证通过。 |
| FEM 标准 Panda＋Nyx 初版 | [报告](../../../runs/test_results/soft_grasp_20260927_fem_robot_01/evidence/report.json)通过；默认 home→接近→取得→抬升→搬运→落桌→释放→撤手，两段共 11.375 s，持握与出生回溯通过，无 lost。此快照早于材料片双侧准入改动。 |

FEM 初版录像：[抓取／抬起](../../../runs/test_results/soft_grasp_20260927_fem_robot_01/evidence/rollout/views/front_oblique/segment_1.mp4)、[搬运／释放](../../../runs/test_results/soft_grasp_20260927_fem_robot_01/evidence/rollout/views/front_oblique/segment_2.mp4)。三路六个文件均完整解码通过。实际最大跟随误差 1.774 mm、最大材料边长比 1.0535、最小体积 Jacobian 0.9558；落桌后最大速度约 1.76e-7 m/s。量化结果来自同次逐 tick 状态及体网格，见其 `offline_validation.json`。

最终两次机器人运行的关键运行时文件、夹具和策略已与当前工作区逐项比对 SHA-256，一致。两种材料都经过真实 `Env → SegmentRunner.run_policy → simulator` 执行；没有使用静态动画或历史视频替代。源码、配置、生成资产和失败尝试保留在各自结果目录。当前配置启用逐 tick checkpoint 和三路 Nyx，实测 PBD 约 531 s、FEM 约 1000 s 墙钟时间；不能将其称为实时性能资格。

### 10.4 资格范围与剩余项

这是独立材料夹具的功能交付，不能把 §7 的整个 T0–T11 矩阵标为全通过。T1 的单指／超距／跨材料／埋层目前主要是几何单元反例，尚缺全部真实动力学场景；T4 已测不同区域并持和索引冲突，未对所有保护邻域与复杂交接取得资格；T7 已测关键持握与出生回溯，未穷举每种准入／释放中间态；T8 注入的是创建约束后失败，释放中途失败还需专项覆盖。

尚未完成真实折叠多层布、邻近双绳腿、ALOHA 双臂完整机器人流程、全部碰撞组合，以及 T10 的两档网格×两档时间离散化稳定性扫描。报告记录运行耗时和进程峰值 RSS，但这不是完整显存／checkpoint 成本评测。此前 architecture 检查中的 `planning/cast_coil`、`planning/lock_picking` 目录白名单失败属于现有并行工作，未在此修改。

ALOHA 单手诊断 `pbd_aloha_03_cpu` 抓住后在测量姿态回送 IK 时触发关节限位；`pbd_aloha_04_cpu` 改变工具绕轴朝向后能保持局部抓片，但未达到策略的抬升目标。两次均记失败，不能继承 Panda 的完整流程通过标签；公共后端不修改 ALOHA 限位或 IK 来绕过此问题。

正式 FEM Task 仍需各自提供抓取区和接近动作；Blanket 还需提供与实际出生网格一致的材料映射并完成多层场景资格。本轮没有批量启用 assist，也没有清除这些任务的已有缺口。

### 10.5 用户指出“抓绳像刚体杆”后的复核

对最终 FEM 录像的原始顶点重新测量：试件长 160 mm、直径 8 mm，`E=1 MPa`、`nu=0.45`、`rho=1100 kg/m³`；体网格只有 189 点、480 个线性四面体。该试件是实心弹性圆柱，尚未标定成易弯曲绳索。

本次实际 assist 索引为 81–107，共 27 点，覆盖材料弧长 72–88 mm 的三个截面；约束带实际长 16 mm，两端各有约 72 mm 未加临时约束。5.625 s 持握状态中，相对中间带切线，两端分别下垂 2.699 / 2.694 mm。因此没有把全绳绑定为刚体，但变形在原相机里很不明显。见 [实测数据](../../../runs/test_results/soft_grasp_20260927_fem_robot_02_rgb/evidence/sag_audit.json)与[真实比例／放大比例曲线](../../../runs/test_results/soft_grasp_20260927_fem_robot_02_rgb/evidence/sag_audit.png)。

当前准入只要求局部材料片同时具备两指表面邻近证据，实际绑定仍取空间球与材料邻域交集；**没有逐点裁剪到真实指垫夹持包络**。这属于选区实现仍需收紧的边界，但现有证据不能把录像近似直杆完全归因于它，也没有证明此次 16 mm 带超出了指垫。

另做离线小变形线性 FEM 诊断，在相同材料、几何和 16 mm 固定带下，将原四面体网格整体二分细化。原网格／一次细化／二次细化的端部平均下垂分别约 2.013 / 4.302 / 6.236 mm，提示粗网格存在明显弯曲刚化影响。该诊断没有运行 Genesis/IPC，不能替代原生网格收敛验收；原生本构、动态过程和软位置约束与该线性诊断有差别。数据、脚本和哈希保留在同一 evidence 目录。

上一轮通过只证明所选试件的抓取、搬运、释放和状态恢复，**不包含自由端下垂或绳索弯曲顺应性的资格**。用户进一步明确：吸附范围位于两指垫之间、与指垫尺寸相当并允许小容差即可，不要求精确贴合指垫轮廓。后续应检查这个范围要求，并增加悬空端部下垂／曲率指标；材料、几何、体网格与选区宽度的贡献需区分，不能仅凭更软的视频宣称物理标定完成。

### 10.6 历史 v13 绳材在独立夹具中的对照

用户授权在现有机器人测试场景试用历史 FEM 绳。新增 `tests/fixtures/fem_rope_profiles.py` 提取历史 Rope Threading v13 的材料和网格配方，不导入历史运行器。`tests/fixtures/soft_grasp.py` 的 FEM 分支通过 `rope_profile` 选择；`tests/integration/test_grasp_pbd.py` 的共享测试把选择传入 `SimulatorConfig.task_parameters`；`scripts/test_grasp_assist.py` 新增 `--fem-rope-profile v13_material_mesh`，只用于 `fem-robot`。生产材质、资产生成器、抓持后端与机器人策略没有因这次对照而修改。

第一轮保持绳长 160 mm、直径 8 mm、默认 Panda/Robotiq home、动作、assist 配置、25 ms tick/10 substeps 与 Nyx 相机。材料改为 `E=50 kPa / nu=.30 / rho=650 kg/m³`；截面 24 边，轴向约 1.375 mm，TetGen 请求最大四面体体积 `2.5e-9 m³`，IPC 接触距离 0.2 mm。实际生成 4,809 点、20,364 个四面体，最大实际体积 `3.367e-9 m³`；TetGen 请求值不被当作实际硬上限。

历史 20/s 的专用形变阻尼尚未接入当前运行链，本轮不启用；这不是历史 1.1 m 穿环场景的完整复现，也不是只改变 E 的单变量实验。相同 assist 半径在细网格下可能选中不同长度的实际材料带，必须从记录的绑定索引测量。

首轮 `runs/test_results/soft_grasp_20260927_fem_v13_01_rgb` **通过**抓放、持握／出生回溯及三路六段视频检查。10.9 s 仿真，pytest 约 1048 s。抬升终点两端下垂 46.07 / 48.97 mm，原试件为 2.70 / 2.69 mm；但最小离桌间隙仅 0.206 mm，形状仍受桌面接触限制。实际绑定 771 点、27.35 mm 材料带；最大跟随误差 0.734 mm，最大材料边长比 1.2221，最小体积比 0.5085，最终最大速度约 0.0052 mm/s，无 lost。详见[报告与全部视频](../../../runs/test_results/soft_grasp_20260927_fem_v13_01_rgb/README.md)。

离线生成验证正体积与有限坐标，相关软体/几何单元检查 15 项通过。与旧基线相比，其他会话已增加的 Env/World 初始夹爪目标与最终释放几何检查在此独立夹具中均未启用；差异列表保存为 `production_source_comparison.json`。

为检查绳端完全离桌时的行为，测试策略新增可选 `lift_height_m`（默认仍为 55 mm），CLI 为 `--lift-height-m .10`，参数进入报告和 submission hash。第二轮 `soft_grasp_20260927_fem_v13_02_high_rgb` 在首轮退出后串行执行，使用相同绳材和 assist、100 mm 抬升；**完整抓放、回溯与六段视频检查通过**。11.0 s 仿真、约 1048 s 墙钟时间；两轮体网格数组和 771 个抓持索引逐项相同，均于第 173 步取得。

第二轮 5.65 s 抬升终点两端下垂 49.56 / 49.39 mm，全绳最低点离桌 44.63 mm，确认完全悬空。该时刻最大顶点速度仍为 0.160 m/s；最后 0.25 s 的两端下垂范围为 41.02–51.00 / 42.88–53.59 mm，是带摆动的形状测量而非静态标定。全程最大跟随误差 0.778 mm、边长比 1.2541、最小体积比 0.5085，无 lost／翻转；最终最大速度约 0.00072 mm/s。见[报告、曲线与三路视频](../../../runs/test_results/soft_grasp_20260927_fem_v13_02_high_rgb/README.md)。两轮证明当前 assist 可以处理该较软试件，不把结果推广为所有绳材／网格资格，也不改正式任务默认参数。


### 10.7 将已测试的软绳配方设为共享默认

用户在上述对照后授权替换当前 FEM 绳。正式默认迁入的是已测试的材料与网格配方，不包含历史专用 20/s 形变阻尼，也不恢复旧运行器。范围为 Rope Threading、Knot Untying、Orbits、Slotted Post Ring；保留各任务的绳长、半径、初始路线和端部结构。

- `topogym/assets/materials.py`：共享 `E=50 kPa / nu=.30 / rho=650 / friction_mu=.3`，新增绳用 IPC `contact_d_hat=.0002`。
- `topogym/assets/geometry/rope_volume.py`：默认采用 24 边、最大轴向间隔 1.375 mm 的表皮及 TetGen `pq1.1/10a2.5e-09YQ`；保留直线参考、曲线出生映射、端部加粗和材料坐标。TetGen 的请求体积不是每个实际单元的硬上限。旧单层扇形网格仅保留为显式 `structured_baseline` 诊断配置。
- `topogym/utils/geometry/rope.py` 和两类绳判据：从保存的表面截面索引取中心线，不假定细网格每站存在轴心点；继续校验材料身份和顺序。Orbits / Slotted 的永久连接仍按端部材料长度选区。
- 四类 `tasks/*/common.py` 使用绳专用接触距离并记录 `fem_rope_profile`；未修改全局 IPC 默认值。
- `tests/fixtures/fem_rope_profiles.py` 改用共享生成器；独立夹具、集成测试及 CLI 默认切至该配方，旧 `baseline` 显式保留原 1 MPa 材料与粗网格，避免覆盖既有对照含义。`pyproject.toml` 的 `fem` 组增加 TetGen 0.8.2。

验证与实际限制记录在 `runs/test_results/fem_rope_default_20260927/README.md`。本次迁移不继承历史完整任务成功标签。

9 个已接入 FEM 绳变体的 `model_revision` 和 catalog 同步增加 `_fem_soft50_fine_v1`，使相同 seed 的新配方具有不同 instance identity。身份单测验证新旧实例不同、catalog 与类定义一致。版本号修改发生在原生生命周期快照冻结后；`model_revision_parity.json` 核对这些追加改动仅为版本字符串，物理代码不变，避免把旧编号的快照称为最终全部源码逐字相同。

本次最终结果：9 个变体离线网格检查通过；4 类基础场景均完成 0.5 s 推进、原生回溯续跑和子步回溯。Rope Threading / Slotted Post Ring 整体生命周期通过；Knot / Orbits 在严格 seed RGB 复现失败，但生成资产及保存物理初态完全一致，未放宽断言。追加模型身份检查通过。

新共享短绳（4803 节点 / 20342 四面体）实际完成默认 home → 接近 → 被动取得 → 100 mm 抬升，791 点、27.35 mm 抓持带，两端下垂 49.62 / 49.25 mm，最低点离桌 44.63 mm；该时刻仍有摆动。最大跟随误差 0.788 mm、最大材料边长比 1.25995，首段三路视频完整解码通过。其后连续两次 RGB 和一次无 RGB 的完整尝试都在 checkpoint 因并行 GPU 显存争用 OOM 中断，**本次新共享网格的完整释放与回溯尚未验收**。历史 4809 节点试件的通过记录不替代这项缺口。详见 `runs/test_results/fem_rope_default_20260927/README.md`，CLI 可在 GPU 资源稳定后直接补跑。
