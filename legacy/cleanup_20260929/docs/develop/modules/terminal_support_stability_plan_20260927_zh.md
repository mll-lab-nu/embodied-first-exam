# 公共 terminal 与支撑面稳定判据：工程计划

## 最新范围修订（用户确认后实施）

用户进一步明确：公共功能用于确认最终动作后，夹爪离开、辅助解除时物体能否持续稳定。`declare/finalize_spec` 指 Task 方法而非目录。下文原方案中的通用承载力/支撑图、后端接触力扩展和 core 搬迁不属于此次实施；保留现有公共 TaskDefinition 的唯一计时，在 `evaluation/terminal/` 增加通用释放后稳定测量。Coil/Buzz/Knot/Blanket 接入，各任务继续负责自己的几何目标。实际接口、修改文件及验证边界以[公共终态确认说明](final_settling_zh.md)为准。以下保留为原提案背景，不能视为当前实现清单。

日期：2026-09-27。状态：计划，尚未实施。依据当前 `/home/jianwen/topogym` 源码核对；本文不代表新增物理验收或任务成功资格。

## 1. 目标与当前缺口

把“目标物体稳定在桌面或指定支撑面上”的共同条件纳入公共 terminal 模块。任务声明目标、允许的支撑来源及是否必须释放；公共模块统一计算支撑、解除辅助、机器人释放、运动稳定，以及连续确认和终止结果。

当前已有一部分公共机制：`tasks/base.py::TaskDefinition.update()` 负责连续物理 tick、稳定计时、失败优先、终止锁存；`get_state/set_state` 负责恢复。各 Task 的 `evaluate_state/evaluate_transition` 提供任务目标。`evaluation/task_metrics.py` 提供若干纯测量。因此本次是在现有单一运行链上收敛公共实现，不新建 Env、物理循环或历史存储。

Coil 当前成功条件为对齐、低速、机器人接触力小，并持续 0.5 s。`RigidTaskDefinition.released()` 没有读取 assist，Coil 也没有桌面支撑检查。上一轮使用三档实际生成的几何构造合成状态：悬空 20 cm 且 assist 开启、悬空且 assist 关闭、处于桌面高度但无支撑证据且 assist 开启，三档共 9 项均被判成功。这些是判据反例，不是真实物理轨迹。

`World.read_state()` 已输出 assist 状态；刚体 contacts 目前只输出 link、force、penetration。Buzz 的子步接触事件另有角色和覆盖声明，但只有力幅值，且“某个子步接触过”不能证明整个 tick 持续承载。IPC/PBD 接触不能从这份刚体数组推断。

## 2. 模块归属与职责

拟新增 `topogym/evaluation/terminal/`，作为公共 terminal 包；仍由 Task 声明任务成功语义。

```text
World.advance / read_state
  → 物理状态、接触覆盖、支撑面身份、实际辅助绑定
Task.evaluate_state / evaluate_transition
  → 任务目标/失败 + 公共支撑稳定测量
TaskDefinition.update
  → terminal.advance_terminal（纯状态转移）
  → 一次提交 TaskResult、确认时间和任务历史
Env
  → 保存同一 tick，终止或继续；时间预算仍由 Env 处理
```

| 拟新增文件 | 职责 |
|---|---|
| `evaluation/terminal/types.py` | `TaskResult`、公共确认状态、支撑规范、测量结果及证据覆盖类型；无引擎依赖 |
| `evaluation/terminal/core.py` | 从 `TaskDefinition.update` 提取纯终止状态转移：连续确认、不可用证据阻断、失败优先、成功与结果锁存 |
| `evaluation/terminal/support.py` | 指定表面的有效支撑测量，有限表面范围、法向、承载证据、合法间接支撑 |
| `evaluation/terminal/release.py` | 目标范围内 assist 解除、机器人接触/间距证据；区分释放与撤手 |
| `evaluation/terminal/settling.py` | 刚体、关节 link、软体材料点速度及可选窗口漂移测量，组合所需条件 |
| `evaluation/terminal/__init__.py` | 导出稳定的少量入口；不建立 task_id 到判据的第二份注册表 |

`tasks/base.py` 保留声明、调度、输入校验、原子提交与唯一 checkpoint 所有权。`TaskResult` 移入公共类型文件后，从旧路径重新导出，保持现有导入兼容。提取后的 core 不读取 Task 子类，不导入 World，不自行推进时钟或保存历史。

`task_metrics.py` 已有速度测量迁移后用兼容导出保持单一实现；区域、穿越及拓扑测量继续保留原职责。布料、绳和刚体使用相同结果协议，但测量依据按物理类型适配。

## 3. 任务声明与接口草案

规范在 `declare/finalize_spec` 时固定，以实际场景的碰撞支撑面为准；在 `bind` 阶段解析运行时实体/link/geom 身份。不要把机器人 link 编号、固定桌面高度或 task_id 分支写进公共算法。

```python
# 以下为拟定接口，不是已经可调用的 API。
SupportStabilitySpec(
    targets=("coil_gold", "coil_silver"),
    supports=("table_top",),
    support_mode="assembly",     # 另有 each_body / deformable_surface
    require_support=True,
    require_assist_released=True,
    require_robot_released=True,
    require_robot_clearance=False,
    thresholds=...,
)

measurement = evaluate_support_stability(world_state, spec, geometry)
# measurement: satisfied、evaluation_status、各条件、缺失证据、数值指标
# 任务将 measurement 与自身 alignment / route / topology 等目标组合。

decision = advance_terminal(previous, candidate, failure, evidence_status,
                            physics_dt_s, stable_duration_s, goal_complete)
```

现有 `config['terminal']` 对键集和值有严格数值校验，不能直接塞入上述字符串、实体列表和布尔值。结构化规范由 Task 内部声明；数值阈值沿用任务配置并校验。后续若开放管理方覆盖，应单独定义 schema，并进入实例身份；操作方不能修改成功要求。

确认时长仍只有现有 `stable_duration_s` 一处来源。任务可只复用静止检查，也可启用完整支撑稳定组合；没有启用的条件明确标为不适用，不应伪造“已验证”。

## 4. 支撑与释放的精确定义

### 4.1 指定表面确实承载目标

支撑面规范包含实体/碰撞几何身份、局部坐标系、允许接触的表面片区、有限边界、有效外法向及静止要求。首批覆盖固定桌面、Buzz 终点托架；倾斜/曲面按其真实碰撞表面测量。首批不承诺移动托盘：当前“不动”使用世界坐标速度，今后支持随动支撑需显式声明相对速度规则。

至少联合检查：

1. 目标与指定表面存在有效接触，排除仅接近、负 penetration 的预测候选、桌侧和桌底。
2. 接触位置属于允许支撑片区；不能只看物体 z 接近桌高。是否要求整个物体投影在桌内，由任务声明，不能为了支撑检查擅自增加摆放区域要求。
3. 接触法向、作用于目标的力方向和目标受力相符，能够提供抵抗重力的支撑。正确归一化 a/b 顺序、力的作用对象和单位；先以已知质量的静置方块验证引擎读数。
4. 在确认窗口内目标保持低速，按任务启用漂移上界；拒绝严重穿透。接触力阈值按质量、步长和后端标定，不照搬所有任务共用的绝对 0.05 N。

`assembly` 模式允许 Coil 一件经另一件获得桌面支撑。只允许声明集合内的传力路径，机器人和 assist 不能成为支撑节点。接触图连通仅为必要条件，还要检验有效承载方向、系统外部支撑力与稳定性，不能把普通侧面碰触当成承载。拆解目标使用 `each_body` 分别检查；不沿用装配态的传力路径。

### 4.2 辅助解除、机器人释放、撤手分别测量

- 解除辅助：目标上不存在活动的临时辅助约束。读取 World 管理的实际绑定，并由后端核验真实约束；不以夹爪命令、低接触力或仅配置为 `none` 代替运行态。
- 目标级范围：公共接口支持目标集合，辅助仍作用于无关物体时不自动阻断。Coil 可先用全局 `assist_active=False` 作保守检查，随后接目标绑定索引。
- 永久结构连接与临时 assist 分开：绳和木柄、任务锚点的设计连接不能全被当成待解除约束；支撑合同另行决定某固定锚点是否属于允许支撑源。
- 机器人释放：使用覆盖完整的接触/间距证据；聚合接触需同时关注力幅值和合力，避免对向夹持力相互抵消后被当作释放。低力只能作容差内的释放判定，不能独自证明无承载。
- 撤手：任务要求时检查完整机器人相关碰撞表面与目标表面的间距及误差界，不只看 TCP 或夹爪开口。Coil 文档已有撤手要求，接入时应显式启用并标定距离；其他任务按合同选择。

### 4.3 软体的证据要求

Knot/Blanket 的高度包络与低速继续有用，但只能说明靠近表面且运动小。软体支撑必须使用实际 FEM/PBD 碰撞表面或粒子半径约定，不能用 visual 网格、中心线单点或几个最低顶点冒充整件支撑。

IPC/PBD 后端分别声明可观测范围。优先接原生接触/约束或接触冲量证据；如后端没有可靠导出，完整支撑测量返回 unavailable。几何近表面诊断仍输出，但不降级成已确认支撑，也不偷偷使用 Genesis 刚体空接触数组作证据。

支撑覆盖率、悬垂容差、最大高度和材料完整性由任务选择：布不必每个粒子都直接接触桌面，绳不必每个中心线点都位于同一平面。只有经后端夹具验证的测量方式才能启用成功确认。

## 5. 时间与证据合同

完整组合条件共同控制现有稳定窗口：目标成立、指定支撑有效、必要的释放/撤手成立、速度与漂移合格、证据可用。任何必需条件失效或不可用均清零；不把释放前的静止时间带入释放后，也不增加默认宽限期。

保留当前语义：首次成立的 tick 只启动非零窗口；随后按实际 physics_dt 累计。重复读取/重复 tick 不累计；必须连续物理步；失败即时优先，零时长目标按原合同处理。terminal 成功/失败与 time-limit truncation 保持区别。

接触数据必须记录 physics_step、子步覆盖和来源。Buzz 的触线失败使用“任一子步触碰”；支撑成功不能复用事件并集中的“曾经碰到”，而应检查每个已声明采样子步的支撑条件。速度/位姿若只在 tick 末采样，报告中明确采样范围，不声称连续时间证明。assist 在 tick 前后新增/解除的时序也要记录，避免期末解除掩盖 tick 内仍受辅助。

数据状态分三类：

- 支持且完整，测量为假：正常继续，不成功。
- 后端明确不支持/覆盖不足：`evaluation_status='unavailable'`，禁止累计和成功。
- 已声明支持却字段缺失、过期、形状损坏或非有限：按现有接口/物理故障路径处理，不伪装成普通任务失败。

公共确认状态和可选漂移参考只在 Task checkpoint 中保存一份。World 保存接触摘要与约束状态；回溯同时恢复二者。若状态格式改变，显式升级 schema、拒绝不兼容快照；不能默认补零继续累计。

## 6. 13 项任务的接入范围

| 任务 | 当前终态合同/实现 | 本计划接入 |
|---|---|---|
| Cast Coil | 装配/拆解、放桌、释放、撤手、稳定；缺真实支撑和 assist 检查 | 首批完整支撑稳定；装配/拆解分别声明传力规则，覆盖 easy/medium/hard |
| Buzz Wire 3D | 完整沿线进度、禁止触线、终点托架释放稳定；已有角色接触 | 首批完整支撑稳定，指定 finish_support；保留任一子步触线立即失败和原确认时长 |
| Knot Untying | 解结后贴桌静止；当前是高度包络、无投影交叠、速度 | IPC 阶段接入桌面支撑与无临时辅助承载；保留解结几何及完整性条件 |
| Blanket Flatten | 覆盖、平整、高度、伸长、速度及漂移 | PBD 阶段接入桌面支撑与无临时辅助承载；保留材料和覆盖条件，迁移漂移历史 |
| Cast Keyhole | 指定银件完整入区、静止，允许握持 | 复用公共 core/静止；保持 holding_allowed，不默认强制支撑/释放 |
| Horseshoe Ring | 指定环入区、静止，允许握持 | 同上 |
| Hedgehog in Cage | 刺球连全部尖刺入区、静止，允许握持 | 同上，保留自身确认时长 |
| Interlocked Claws | 当前目标区合同允许握持；历史文档有分离目标差异 | 按当前已部署合同复用 core/静止，本轮不改目标区或增加松手要求 |
| Slotted Post Ring | 可移除环入区、静止，允许握持 | 复用 core/静止；涉及 IPC 时不借用刚体接触假定 |
| Orbits | 整绳和木柄入区、静止，允许握持 | 复用 core/静止，保留永久绳柄连接，不强制解除握持 |
| Rope Threading | 按序穿环后整绳低速 | 复用 core/软体速度，不增加落桌或松手要求 |
| Fiber Bundling | 穿越材料次序、弯曲和完成进度 | 复用 core，保留原任务条件，不自动要求全链静止/落桌 |
| Lock Picking | 钥匙穿越终点及实体限位规则 | 复用 core，保留原任务条件，不增加松手/落桌 |

“桌面上的目标区”当前是空间区域，不自动等于“解除握持后由桌面承载”。若今后这些任务也要求真正落桌，只需更新任务规范和版本，调用同一模块。现有 `goal_complete=False` 不因接入模块自动改成 True；判据接线、物理测量资格、机器人完整成功分别记录。

## 7. 预计修改的现有文件

| 文件 | 预计改动 |
|---|---|
| `topogym/tasks/base.py` | 调用公共 core；TaskResult 兼容导出；增加固定支撑规范的声明/元数据接点；整理 released 的公共委托；保留原子提交与唯一历史 |
| `topogym/evaluation/task_metrics.py` | 速度函数委托公共 settling；保留区域/拓扑职责，消除重复实现 |
| `topogym/world/genesis_world.py` | 只采集和导出标准化接触、覆盖、表面身份、目标约束证据；按 Task 需求安装采集器 |
| `topogym/world/physics/rigid_contacts.py` | 扩展 link/geom、接触点、法向、带方向的力、逐子步支撑摘要；保留 Buzz 任一触碰事件语义 |
| `topogym/world/physics/grasp_manager.py`、`grasp_rigid.py`、`grasp_ipc.py`、`grasp_pbd.py` | 输出目标级临时辅助绑定及核验状态；保持实际约束恢复一致；仅补缺失证据，不改抓持策略 |
| `topogym/world/tabletop.py` | 导出真实碰撞桌面的局部范围和面身份；不改桌面建模、材质或布局 |
| `topogym/world/physics/ipc.py`、`pbd.py` | 后端能力探查与软体支撑证据适配；需要独立代码时新增 `support_ipc.py` / `support_pbd.py`，不将物理访问放进 evaluation |
| `topogym/world/state.py` | 检查新增证据能否沿用 contact_events 快照；必要时扩展保存/恢复和版本验证，不复制一套历史 |
| `topogym/tasks/cast_coil/common.py` | 声明桌面/目标集合，组合对齐与完整支撑稳定，新增可诊断阈值和 terminal_revision |
| `topogym/tasks/buzz_wire_3d/common.py` | 复用指定终点托架的支撑释放测量，保留沿线进度和触线失败 |
| `topogym/tasks/knot_untying/common.py` | IPC 阶段组合解结条件与公共支撑稳定 |
| `topogym/tasks/blanket_flatten/common.py` | PBD 阶段组合展平条件与公共支撑稳定；将 _stable_origin 及定制 update/快照逻辑纳入一致状态合同 |
| `topogym/tasks/placement.py` 及六项区域任务 | 仅在必要处改公共测量入口，显式保持握持策略；不批量改写任务目标 |
| `topogym/simulator/env.py`、`interaction.py`、`rollout_simulation/` | 审查 TaskResult/元数据接线和公共结果过滤；需要时调整兼容接点，绝不加入任务专属成功分支 |
| `scripts/run_cast_coil_policy.py` | 最终检查作为交叉核验，正式成功统一采用 terminal；验证策略不会在放桌前被截断 |
| `topogym/evaluation/README.md`、任务说明与 terminal 工程文档 | 记录公共包职责、任务声明、版本、阈值来源及资格范围 |

现有共享文件有其他会话改动，实施时重新核对并局部修改，不整份覆盖。阈值、支撑规范、判据版本和证据合同版本写入 terminal 元数据及实例身份；运行时 geom 数字编号不作为跨重建身份。

## 8. 实施顺序与交付门槛

1. **公共 core 收敛。** 先做语义等价提取，全部任务沿用原结果；验证失败优先、锁存、计时、重复 tick、回溯与公开结果，避免重构改变任务行为。
2. **刚体证据与公共测量。** 在独立方块/双刚体/托架夹具上校准表面、法向、力单位、assist 绑定和间接支撑；保持 evidence scope 明确。
3. **Coil 与 Buzz 接入。** 消除 Coil 悬空反例，保留 Buzz 触线机制；更新各自 terminal_revision，验证三档几何与完整物理流程。此阶段的验收仅代表刚体支撑功能完成。
4. **IPC/PBD 支撑接入。** 分别完成后端证据、软体夹具、Knot/Blanket 接入及漂移恢复。若缺原生数据，明确列为未完成，不将几何贴桌结果冒充完整公共支撑验收。
5. **全任务兼容与文档。** 核对 13 项任务的终止合同，确保允许握持任务没有新增释放条件；统一证据格式和版本说明。

## 9. 测试与验收清单

拟新增 `tests/unit/test_terminal_core.py`、`test_terminal_support_stability.py`、`test_terminal_cast_coil.py`，扩展现有 `test_task_state.py`、`test_terminal_public_outcomes.py`、Buzz/Knot/目标区测试，补 Blanket 的支撑与漂移测试。用共同夹具覆盖：

- 对齐但悬空、辅助单手/双手未解除、只处于桌面高度、仅桌侧/错误支撑接触，均不成功。
- 合法直接支撑和装配件间接支撑为正例；拆解两件仅一件支撑为反例；图连通但没有有效承载不通过。
- 力的 a/b 交换、方向、质量变化、多个小接触、对向夹持力抵消、非法/过期/缺失数据。
- 一个子步触桌而其他子步悬空、一个子步机器人重新接触、辅助重新激活、速度或漂移越界，均按声明范围阻断窗口。
- 到 0.5 s 前不得成功；释放前累计时间不可沿用；其他任务的 1 s/2 s 和零时长合同不被改写。
- 反复 observe 不计时；rewind 到释放前/确认中/成功前后并重放，结果一致，废弃未来不污染新分支。
- 目标以外的辅助绑定、合法永久附件、允许握持的区域任务，按各自规范处理。
- 软体静止贴桌但仍受辅助、局部搭桌而主体悬空、半径/厚度与穿透容差边界，不被错误确认。

真实验证拟新增 `tests/integration/test_terminal_support_runtime.py`，扩展 `test_terminal_runtime.py` 中遗漏的 Coil/Blanket，并接入 `scripts/test_base_tasks.py` 的显式检查入口。先在夹具验证接触/解除机制，再执行 Coil 放桌释放与 Buzz 终点托架流程，最后验证 IPC/PBD 支撑；机制探针和完整机器人成功分别报告。

运行产物放 `runs/test_results/`，记录源码/配置身份、阈值、每条件时序、实际约束、接触覆盖、成功 tick 和 rewind 对照。需要录像的真实验收沿用公共 recording、Nyx 和标准场景；CPU 单元/合成检查不算真实物理资格。GPU 不可用时报告未执行并提供实际 CLI。

## 10. 完成定义

公共 terminal 只有一份确认/终止实现和一份历史状态；Task 用声明选择支撑/释放策略。Coil 悬空误成功被阻断，Buzz 保留即时失败，Knot/Blanket 有明确且经过后端验证的支撑依据；其他任务语义不被无意改变。必需证据缺失时不能返回成功，完整支撑条件必须在释放后的共同确认窗口内成立。交付报告分别列清实现、单元/机制验证和完整物理执行，不以公共模块接入替代任务资格。
