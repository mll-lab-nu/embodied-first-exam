# Orbits oracle 开发进度与当前问题

更新日期：2026-10-04。任务：`orbits`，覆盖 `easy`、`medium`、`hard` 三档。

**当前完成的是外部 Orbits oracle 源码移植及本地约束适配，尚未验证本地可运行性、有效 pass 或完整求解。** 已迁入拓扑搜索、双臂交接、托举、提取和 IK 审计；本地 v15 的默认几何、绳长、目标区、材料和成功判据继续保留。来源的运行成绩不能直接继承。

按用户要求，代码移植期间只做源码语法解析、差异与受保护文件核对，未运行测试、几何生成、仿真、搜索、审计或录像。本次仅补充文档，仍不启动这些工作。

## 1. 已完成的工作

| 内容 | 当前实现 | 代码入口 |
| --- | --- | --- |
| 拓扑约束 | 无限球模型的自由群词和穿环记录；一个 pass 必须恰好减少一个 b，且执行结果必须匹配预测词 | [invariant.py](../../../topogym/planning/orbits/invariant.py)、[topology.py](../../../topogym/planning/orbits/topology.py) |
| 路线搜索 | 绳弯、无孔搬运、环孔竖直上升、绕行及路径变体；支持分片与候选缓存 | [routes.py](../../../topogym/planning/orbits/routes.py)、[bight_search.py](../../../topogym/planning/orbits/bight_search.py)、[ribbon.py](../../../topogym/planning/orbits/ribbon.py) |
| 操作原语 | 单臂搬运、helper 托举、环孔交接、开放空间二次交接、双臂套球和绳整理 | [robot_oracle.py](../../../topogym/planning/orbits/robot_oracle.py) |
| 最终提取 | 先释放木柄提供松弛，再尝试逐手拉入、抬升、回拖及成对穿环回退 `unpoke`；最后一个 pass 的接受包含提取条件 | [extract](../../../topogym/planning/orbits/robot_oracle.py) |
| IK 与碰撞审计 | 连续下探和上升、双臂逐采样碰撞、丰富姿态候选、竖直撤离、原地等待与重定向；机器人模式最终提取也纳入审计 | [aloha_ik.py](../../../topogym/planning/orbits/aloha_ik.py)、[ik_audit.py](../../../topogym/planning/orbits/ik_audit.py) |
| 搜索恢复 | `--round-seconds`、`--round-attempts`、tidy 后重新规划及检查点续跑；检查点记录模型身份，提取失败重试同步回滚状态、帧和日志 | [robot_oracle.py](../../../topogym/planning/orbits/robot_oracle.py)、[rope_sim.py](../../../topogym/planning/orbits/rope_sim.py) |
| 本地任务适配 | 与 Task 共用既有 compact 绳参数；读取本地场景，通过共享 `choose_region` 推导目标区；检查完整木柄、绳厚度和静止速度 | [local_contract.py](../../../topogym/planning/orbits/local_contract.py)、[common.py](../../../topogym/tasks/orbits/common.py) |
| 开发接口 | 增加 `drive_object_groups`，支持多个互不重叠 FEM 顶点组的有界 PD 外力；保留取消、清力、原生终止与干预日志 | [object_drives.py](../../../topogym/planning/calibration_tools/object_drives.py)、[api.py](../../../topogym/planning/calibration_tools/api.py) |
| 候选预览 | 在独立开发场景中比较本地模型与来源 v8 放大环；不写回安装的 Task | [Orbits adapter](../../../topogym/planning/calibration_tools/adapters/orbits.py)、[preview_orbits_geometry.py](../../../scripts/preview_orbits_geometry.py) |

规划模型、几何预览和多点外力开发接口都不构成正式机器人完成。代码存在、语法可解析和运行通过是不同的进度。

## 2. 本地保留的环境与移植差异

### 任务几何和物理

下表中的环、柱和底座尺寸是缩放前的模板值；两边三档均使用 `linear_scale=0.85`。绳长和 compact 木柄位置则是缩放后的显式值。

| 项目 | 来源实现 | 本地保留值 |
| --- | --- | --- |
| 环半径 | 0.1353 m | 0.066 m |
| 柱距 | 0.1465 m | 0.082 m |
| 相邻环高差 | 0.1059 m | 0.068 m |
| 最低环高度 | 补丁中为 0.1613 m | 0.126 m |
| 底座宽 | 0.329 m | 0.18 m |
| 底座长，easy／medium／hard | 0.581／0.727／0.874 m | 三档均为 0.47 m |
| 绳长，easy／medium／hard | 2.20／3.00／3.60 m | 三档均为 0.80 m |
| compact 木柄位置 | 0.44／0.44／0.47 m | 三档均为 0.41 m |
| 目标区 | 0.60 × 0.26 m 矩形 | 原共享算法选择的正方形区域，含绳时半边长至少 0.20 m |
| 模型修订 | `compact_external_handle_bigring_v8_fem_soft50_fine_v1` | `compact_external_handle_v1_fem_soft50_fine_v1` |
| FEM、连接与终止 | 来源另有 MuJoCo 绳规划模型及其护栏 | 正式环境继续使用本地 Genesis FEM/IPC、永久连接和 Task terminal |

几何定义见 [OrbitsLayout](../../../topogym/assets/geometry/orbits.py)，三档定义见 [easy](../../../topogym/tasks/orbits/orbits_easy.py)、[medium](../../../topogym/tasks/orbits/orbits_medium.py)、[hard](../../../topogym/tasks/orbits/orbits_hard.py)。共享 [placement.py](../../../topogym/tasks/placement.py)、[task_metrics.py](../../../topogym/evaluation/task_metrics.py) 和 [release_profile.py](../../../topogym/tasks/release_profile.py) 未因本次 Orbits 移植而调整。

`CORD_PROFILES` 只提取本地既有的绳长与木柄位置供任务和规划器共用。来源的放大环参数仅保留在独立预览候选中；未导入“为够到绳段再降低最低环”等后续建模建议。

### 规划护栏与 v15 执行规则

| 项目 | 来源规划器 | 本地移植后的规划器 |
| --- | --- | --- |
| 绳模型穿透 | 通常 6 mm，部分初始化动作放宽到 10–20 mm | 1 mm，初始化、套球和提取不另行放宽 |
| 点抓持误差 | 通常 20 mm，套球 10 mm | 读取本地 `GraspAssistConfig`，当前为 10 mm |
| 单段拉伸 | 通常 1.8，初始化和提取可到 2.0 | 读取本地 `SoftGraspTarget` 默认上限，当前为 1.3 |
| 总长比例 | 通常 1.10，初始化可到 1.20 | 保留 1.10 的额外搜索护栏 |
| 机器人与夹具碰撞 | 源码为 1 mm | 读取本地 `TASK_CONTACT_PENETRATION_M`，当前为 1 mm |
| 支撑面捏取偏移 | 最高抬高 3 mm | 不超过实际绳半径 |
| 普通 IK 跟踪步长 | 0.6 rad | 0.5 rad；重定向另有路径检查，实际动作仍须经过原生准入 |

**这些是独立规划模型的预筛选条件，不是重新定义 v15 环境规则。** 例如 1.3 来自软抓持配置，不能解释为所有 FEM 状态统一采用的物理失效阈值；MuJoCo 绳段拉伸也不能替代四面体体积和永久连接诊断。

正式执行仍应由本地 [Harbor Session tooling](../../../harbor_templates/topogym/common/rcb_topogym.py) 负责：按适用任务处理接触深度、软体异常的 0.25 s 持续窗口、2 mm 连接误差、驱动力矩上限、桌面保护及 standard 动作限制。本次没有改这些规则，也尚未为 Orbits 接入原生机器人执行。审计中的 `standard_time_scale` 只是按 0.04 rad／25 ms 计算的放慢建议，尚不是实际回放证据。

## 3. 来源进度与本地进度

以下数字来自用户提供的交接材料，截至来源记录的 2026-10-04 17:20 CDT。分母表示来源拓扑模型计划的越球 pass 数，**不是完整任务的成功率**。

| 难度 | 来源机器人感知规划与 IK 审计进度 | 来源物体级进度 | 本地状态 |
| --- | --- | --- | --- |
| easy | 2／4 | 4／4，但最终提取未成功 | 代码已移植，未运行 |
| medium | 4／8 | 4／8 | 代码已移植，未运行 |
| hard | 2／16 | 6／16 | 代码已移植，未运行 |

这里的“机器人”仍指 MuJoCo 绳规划加 ALOHA IK／碰撞审计；“物体级”使用虚拟点抓手，不包含机械臂可达性。二者都不能当作 Genesis 原生完整执行。来源对无限球拓扑模型的可解分析也不证明当前本地几何、绳长与物理条件下能够完成任务。

本地未迁入来源的二进制检查点、完整轨迹、审计结果或视频。当前检查点通过 `model.json` 核对布局、Task 参数、修订、模型哈希及护栏；没有身份信息或身份不符的来源状态会被拒绝。后续应从本地初态生成新搜索链。

## 4. 当前问题

### 已确定的实现与证据缺口

1. **尚无 Genesis 原生机器人执行器。** 当前模拟绳的一维 MuJoCo 模型和虚拟点抓手不能复现真实双指接触、FEM 材料带抓持、驱动力限制与 IPC 连接行为。仍需将计划转换为经本地 Session 执行的动作，并使用实测状态闭环反馈。
2. **模型仍有明确简化。** 木柄采用近似碰撞形状，绳与木柄的碰撞被屏蔽以处理两端连接；不存在 FEM 四面体体积诊断。拓扑词和拉伸护栏可以筛除部分错误候选，但不能据此证明全程无穿透或满足原生物理规则。
3. **本地几何下没有有效 pass 或可达性证据。** 环径、层距和绳长与来源差异明显，路线偏置、交接距离、9 cm 深度预筛选及动作余量仍需针对本地重新评估。现在不能声称三档已经可解，也不能从尚未运行推断无解。
4. **尚无完整成功与独立验收。** 本地没有从标准 home 开始的连续机器人轨迹、原生 terminal 成功、完整稳定窗口、视频或 Harbor verifier 结果。提取末态的几何与速度检查只用于规划接受，不等同于原生任务成功。
5. **当前覆盖范围有限。** 入口面向三档具名变体的默认参数与 seed 0；坐标适配要求底座居中、90° 摆位以及与机器人匹配的世界 x 位置。随机场景、其他朝向和 `reference85` 不在当前验证范围内。
6. **运行入口尚未实测。** 可选 MuJoCo／Matplotlib 依赖、机器人资源加载、检查点恢复、候选预览和新增多组 FEM 外力接口均未在本轮执行；不能把源码核对称为运行验收。

### 来源已暴露的问题及本地含义

| 问题 | 来源观察 | 对本地开发的含义 |
| --- | --- | --- |
| 穿孔抓取深度不足 | 来源探针报告 TCP 只能下探环面以下约 6–10 cm，而部分绳段在最低环下约 11.5 cm；手腕／前臂受环管限制 | 应优先量化本地可达空间；这些深度不是本地实测值 |
| 交接后仍无法上升 | 侧向可抓不等于能竖直穿环；交接点受双臂碰撞与绳自然下垂共同限制 | 需检查整条下探、接绳和上升轨迹；helper 原语已有代码，效果待验证 |
| 拓扑自由但仍卡在器具上 | easy 物体级已消去拓扑词，仍有成对抵消的穿环和环管挂绳，最终提取失败 | 不能把 b=0 当完成；还需完整脱离、放入本地目标区并停稳 |
| 木柄拉紧导致提取受阻 | 来源先拉至目标区远端会耗尽余量；改为近边放下并松手后，`unpoke` 曾将穿环数从 6 降到 5，仍未完成 | 已保留松弛与回退策略，但对本地 0.80 m 绳是否有效未知 |
| 贪心搜索与耗时 | 只接受立即减少缠绕的动作会排除先变差再改善的序列；昂贵 IK 候选可能消耗很长时间 | 仍需研究多步提取和候选预算；轮次时间上限不能视为每次 IK 的硬超时 |

本地更小的环、更短的绳和更保守的规划护栏，可能使来源候选被提前拒绝，或使原有启发式不再合适。这是依据差异识别的风险，尚无本地失败数据支持具体瓶颈排序。后续不能通过修改本地 v15 环境规则来掩盖这些问题。

## 5. 后续工作顺序

以下为后续开发清单，本次文档更新不启动执行；用户“不跑测试”的要求继续有效。

1. 在代码层核对仍依赖来源几何的路径偏置、抓取姿态、交接间距、深度预筛选和绳余量条件，标明哪些只是排序启发式。
2. 明确原生执行方案：使用本地 Session、真实抓持和状态反馈；把 MuJoCo 路线、IK 候选、实际动作及 terminal 结果分别记录。
3. 完善提取阶段的多步搜索与回退，使它能够处理需要暂时增加穿环数的动作序列，并保持模型／检查点身份一致。
4. 用户后续要求恢复验证时，先检查依赖和本地可达性，再做短段搬运、交接及单 pass；每个结果都绑定当前模型和实际输入，不复用来源成绩。
5. 从本地初态逐档生成新搜索链；完成拓扑消解后，继续验证全绳与木柄进入目标区、原生连接完整及完整稳定窗口。
6. 原生连续执行和独立审计齐备后，再处理正式录像、可解证明和 Harbor 发布；每档分别记录资格。

## 6. 入口与材料索引

- [规划入口](../../../scripts/plan_orbits_robot_oracle.py)：MuJoCo 开发搜索，支持 `--plumb`、`--plumb-first`、`--shard/--nshard`、`--start` 和 `--object-level`。
- [审计入口](../../../scripts/audit_orbits_oracle.py)：记录轨迹的 ALOHA IK、双臂时间线和分阶段拉伸诊断；不是原生物理验收。
- [几何预览入口](../../../scripts/preview_orbits_geometry.py)：本地模型与独立来源候选的比较，不推进物理。
- [模块说明与命令示例](../../../topogym/planning/orbits/README.md)、[Orbits 任务说明](../../develop/tasks/orbits_zh.md)。
- 草稿探针、复现和编排脚本：`/home/jianwen/orbits_solvability_work/imported_20261004/scratch_tools/`，共 14 个文件，均未运行。该目录在仓库外，不随 Git checkout 自动携带。
- 原始交接材料：用户附件 `6bc15da8-f57d-46c9-8621-2483a922ace7/pasted-text.txt`，标题为《TopoGym Orbits oracle —— 代码、改动、结论与经验汇总》。其中路径、检查点和运行数字均属于来源环境记录。

以后更新本页时，分别写清代码完成、短段运行、拓扑进度、IK 审计、原生成功和正式资格，避免把其中一个状态替代其他状态。
