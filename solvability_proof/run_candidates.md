# 现有 run 与下一批可解性证明候选

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

核对日期：2026-09-28。范围为当前 13 个正式 Task，另列 Cube 等机制样板。检查现有报告、冻结源码、当前变体/终态与 policy 入口；本次未运行新仿真，未修改成功判据，也未增加已验收数量。[机器记录与所读证据哈希](run_candidates.json)。

2026-10-03 补充：Hedgehog easy / medium / hard 高位支座新版三档已完成原生成功、独立审计与[正式归档](hedgehog_in_cage/README.md)。下表为当前状态，`run_candidates.json` 和下方 09-28 扫描结论保留原历史范围，数量以 [catalog.json](catalog.json) 为准。

**除已归档的 Keyhole / Coil 六个实例，本轮未找到可以直接按当前正式 Task 的 success 标准追加的其他任务。** 最有复用价值的是 **Lock medium、Fiber 三档、Buzz Wire 三档、Horseshoe 三档**。它们距离新证明的缺口不同；建议首先处理 Lock medium 的终态诊断，再从 Fiber easy 开始迁移。

## 当前任务盘点

| 任务 | 可复用的 run / 路线 | 当前证明状态 | 下一步最小工作 |
| --- | --- | --- | --- |
| Cast Keyhole | F1/F2/F3 三次当前 Env 实际成功 | 已归档 3/3 | [已有证明](cast_keyhole/README.md) |
| Cast Coil | easy/medium/hard 三次当前 Env 实际成功 | 已归档 3/3 | [已有证明](cast_coil/README.md) |
| **Lock Picking** | 当前 medium 的 `trail_12_medium`、`trail_13_medium` 连续完成全控制链 | 最接近；仍无正式 Task success | 诊断同轴正间隙与转盘资格，修正后连续重跑；easy/hard 不继承 medium |
| **Fiber Bundling** | easy_02 / medium_full_01 / hard_full_01 完整连续穿环 | 2026-10-03 独立审计及当前 v4 复核通过，seed 0 正式 3/3 | [三档证明](fiber_bundling/README.md)；其他 seed、默认时序和纯摩擦另行验收 |
| **Buzz Wire** | F1/F2/F3 历史 home→拾取→全路线→放回，4/2 ms 复验均通过 | 历史证据完整；当前三档整体抬高 40 mm | 重算当前布局 IK、迁移反馈控制、补终态资格并重跑 |
| **Horseshoe** | 当前三形状有完整对象几何路径；旧 F1/F2/F3 有机器人成功 | 当前形状证书明确未验证机器人/动力学 | 优先 `waist_mild`，补抓取/交接/IK 和固定目标区搬运 |
| Hedgehog | easy / medium / hard 高位支座新版均完成物体通路、IK 和辅助抓持完整执行 | 默认参数 seed 0 三档已收录；旧低位 hard 和随机实例未覆盖 | [三档证明](hedgehog_in_cage/README.md) |
| Interlocked Claws | 旧同形螺旋爪等完整辅助预抓持路线 | 当前 medium 通路未通过；当前三档摩擦保持诊断均失败 | 分开解决各档抓持和路线，不能把旧分离终点当当前目标区成功 |
| Blanket Flatten | 旧简单折叠单臂展平成功；当前 PBD 抓放夹具通过 | 旧流程关闭 robot-soft coupling；当前复杂初态仅局部执行 | 可先迁移 easy，验证当前初态、抓区、耦合、释放后展平 |
| Knot Untying | 旧 Trefoil 75 s 解结、释放及静置 | 不是默认 home 连续起步；完整物理/通用抓持资格未齐 | 当前 Trefoil 对应 medium；适配当前 FEM/抓持与 home 接近，再做终态资格 |
| Rope Threading | 三环旧部分轨迹、反馈交接 IK | 最长代表执行到 66.115 s，第二环接绳 IK 失败 | 先完成连续交接与全部穿环；当前 easy 两环可作为较短目标，仍需实跑 |
| Slotted Post Ring | 147 s 完整外力解环，机器人过珠/穿槽/交接局部 run | 外力解不构成机器人 IK 可解证明 | 将动作表改成真实双臂连续抓放并执行当前终态 |
| Orbits | 无臂 93 动作 / 213 s 完整解绳；机器人拾取/交接局部 run | 原路线最多同时控制四点，完整机器人路线未建立 | 重排为双臂可执行的供绳/交接和目标区放置 |

优先级是根据可复用证据和缺口作出的工程判断，不是已测得的开发工时或成功率。

## 1. Lock medium：现有 policy 最接近，但不能只改资格开关

优先来源为 [CPU trail_13 报告](../task_rollouts/lock_assist_20260927/lock_picking/trail_13_medium/run_report.json)与[审计](../task_rollouts/lock_assist_20260927/lock_picking/trail_13_medium/evidence_audit.json)：156.7 s、1,567 tick、1,568 个状态，从默认 home 连续拾取、两次回退、支撑换抓、终点插入、释放静置。另有 [CUDA/Nyx trail_12](../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/run_report.json)，156.4 s；[完整视频](../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/full_solve.mp4)。

两份冻结清单各 470 个源文件的哈希此次全部匹配。Task common、medium 定义、policy 与 runner 四个文件均仍匹配工作区；公共 `robot/control.py` 已变化，不能据此宣称当前完整执行栈已重验。

两个原报告均为 `status=route_completed`、`task_success=False`。`leading_tab_inserted=True`、`shaft_in_goal=True`，但 **`coaxial=False`、`independent_goal_check.reached=False`**：释放后轴心贴孔壁，偏移约 1.000～1.003 mm，未满足正式判据额外要求的正间隙。独立 resting-insertion 检查采用明确的 0.2 mm 接触形变余量，其通过不等于原 Task 完整目标通过。另有 `rotor_mechanism_runtime_verified=False`、`goal_complete=False` 的机构资格缺口。

下一步可先离线分析现有完整状态，核对孔壁接触、同轴条件、转盘受限运动及稳定窗口；据此确定控制修正或判据实现问题，再以新源码身份从默认起点重跑至真实 success。不能把两个旧报告改写成成功，也不能静默放宽间隙条件。沿用已测配置时必须声明 **100 ms tick / 160 子步 / float32 / 自动接触辅助**；25 ms 加速配置在这个任务上尚无完整通过记录。

当前可执行完整策略入口：[run_lock_picking_policy.py](../scripts/run_lock_picking_policy.py)；因此它比需重新迁移控制器的其他候选更接近新证明。

## 2. Fiber：先做 4 芯，再扩展 8/16 芯

2026-10-03：当前三档 seed 0 的原生成功运行已补齐独立审计，分别核对 7,604／13,761／25,566 个状态，正式收录 3/3。easy 的历史 v3 身份与同轨迹 v4 复核分开记录；[正式证明](fiber_bundling/README.md)。下文保留 09-28 的历史候选说明，不再代表当前缺口。

| 代表 | 历史完整执行报告 | 仿真时间 | 半步长对照 |
| --- | --- | ---: | --- |
| 4 芯 / easy 候选 | [sparse_04](../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1/report.json) | 114.614 s | 严格对照通过 |
| 8 芯 / medium 候选 | [standard_08](../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1/report.json) | 174.904 s | 两次穿环成功；严格全程对照未通过 |
| 16 芯 / hard 候选 | [dense_16](../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1/report.json) | 235.094 s | 两次穿环成功；严格全程对照未通过 |

均保存 `robot_commands.json`、`turn_ik_audits.json`、`trajectory.npz`、`source/robot_sequence.py`；报告为 `passed=True`、`full_threading_verified=True`，采用双指接触后的原生 weld，末态保持粗护套抓持。这里列的是物理报告时长，不是重渲染视频时长。

当前 [terminal_v3_fiber_contacts](../topogym/tasks/fiber_bundling/common.py) 已对三档启用 `goal_complete=True`，但保留 `thresholds_calibrated=False`。成功需要所有细芯按材料顺序穿过入口/出口、前护套清出、弯折角合格并稳定 0.5 s；任何夹爪后代几何与细芯的子步接触都拒绝成功。旧轨迹/接触规则不能直接替代这个新合同，也尚无对应的当前正式 Fiber 解题 CLI/policy。

可复用路线是“抓粗护套 → 调姿/压整束 → 按实测束形选倾斜与绕行 → 沿环轴进给 → 全束清出并保持”；把旧控制器的策略部分移入 `act(obs)`，经标准 Env 自动抓持和低层 action 执行，先验证 4 芯。8/16 芯的半步长严格对照失败不能改写为通过，但也不抹去各自单次完整执行的历史结果。

另查到的 [fiber_medium_cli_20260928](../runs/test_results/fiber_medium_cli_20260928/report.json) 只是配置/prepare/文档检查，明确没有 Fiber 物理 rollout；其中 `prior_pick_archive.task_success=True` 属于 Cube 样板，不能计入 Fiber。

## 3. Buzz Wire：三套完整路线可复用，当前摆位必须重验

F1 三拱、F2、F3 的归档均有 home 连续接近、实际摩擦抓取、全路线、支撑放回、释放静置及独立 4/2 ms 完整复验：

- [F1 三拱资格](../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/evidence/source/evidence/qualification.json)
- [F2 资格](../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/evidence/source/evidence/qualification.json)
- [F3 资格](../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/evidence/source/evidence/qualification.json)

三份资格均 `passed=True`，包含纯接触抓取、持件通行段零触线、相同物理资产/计划和默认 home 检查；冻结 `planning/`、原 `robot_runtime.py` 与实测状态仍在归档内。

当前三档 revision 均为 `*_raised40mm`，相对旧成功布局整体升高 40 mm。机器人关节轨迹不能直接平移继承；需要沿旧对象相对路线在新摆位重求 TCP/IK 和接近/撤退，再迁移为当前 policy。当前 Task `goal_complete=False`，出生、触线与支撑/释放资格仍需补齐。旧报告证明原固定实例，不能直接作为新摆位 success。

## 4. Horseshoe：扩环 easy 已验收，medium / hard 待验证

2026-10-03：`waist_mild` 扩环 v3、seed 0 从默认 ALOHA home 连续执行 275.2 s，原生成功且独立审计通过，11,009 状态零回溯。正式反馈策略完成折合、倾转释放、桌面抓环和目标区搬运；采用 v12 刚体优化及接触辅助抓持。圆环仍有充分法向直接穿出阻挡证据；[完整证明与复现](horseshoe_ring/README.md)。下述路线证书对应原三档几何，当前 medium / hard 尚无新增机器人成功。

当前三档是 `waist_mild` / `u_mild` / `waist_ellipse`，与旧 F1/F2/F3 的“接近方向”家族不同。对应现存路线和证书：

- [waist_mild](../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/references/waist_mild/certificate.json)
- [u_mild](../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/references/u_mild/certificate.json)
- [waist_ellipse](../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/references/waist_ellipse/certificate.json)

三份证书均 `continuous_collision_free=True`，但明确 **`robot_execution_verified=False`、`dynamic_execution_verified=False`、`lab_obstacle_collision_verified=False`**。旁边的 `body_poses.json` 可用于路线生成；最小对象间隙下界约 0.148 / 0.127 / 0.117 mm，并非机器人跟踪误差余量。

旧 [F1/F2/F3 完整物理资格](../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/physical_evidence) 可供动作和交接设计参考。medium / hard 仍需实际抓取、联合 IK、重力/自由链环执行，以及完整目标环进入固定区域、其余系统留在另一侧的后缀。不能将几何证书计成机器人成功，也不将扩环 easy 的成功授予旧几何。

## 其余任务的具体阻挡证据

- **Hedgehog / Claws 的 09-27 历史批次：**[当前两种 medium 搜索与三档 Claws 抓持报告](../runs/test_results/hedgehog_claws_policy_20260927/README.md)。两种 medium 有反馈执行器和 CLI，但 `--part solve` 尚未取得 P1/T2 资格，不能直接启动为已知解。Hedgehog easy/hard 和 Claws 旧原型的历史流程仍有参考价值，需单独核对当前模型和目标区。
- **Blanket：**[旧简单折叠报告](../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/report.json) 为 `success=True`、`full_robot_task_verified=True`，同时明确 `robot_soft_coupling=False`。[当前 PBD 抓放夹具](../runs/test_results/soft_grasp_20260927_pbd_robot_09_rgb/README.md) 已从 home 完整抓放，但不是 Blanket Task 展平。复杂初态的无臂成功不能增加机器人成功数。
- **Knot：**[Trefoil v9 报告](../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json) 为 `untying_verified=True`，但 `complete_physics_suite_passed=False`、`robot_grasp_qualified=False`、`neutral_to_hover_motion_recorded=False`。当前 Trefoil 在 medium，不能按旧 easy 标签收录。
- **Rope：**[66.115 s 尝试](../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/report.json) 为 `passed=False`，右手目标 IK 不可达；后续反馈重跑的两个报告分别在 1.855 / 1.620 s 主动停止，不能从较新的目录名推断已补齐成功。
- **Slotted：**[完整外力证明及其执行范围](../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/README.md)明确为外力版；机器人现有 run 仅覆盖局部动作。
- **Orbits：**[93 动作完整无臂报告](../runs/demo_metadata/orbits/2026-09-22_rope_video_full_v2/README.md)明确最多四个控制点、`physics_qualified=false`；需要重排双臂抓放，不能直接套用其轨迹作为机器人 IK 解。

## 正式 13 项以外：Cube 可作机制证明候选

[scripted_policy_pick_place_20260926](../task_rollouts/scripted_policy_pick_place_20260926/validation_summary.json) 有 **7 次真实 Task success**：`cube_pick_place/rollout_0001`，以及 `cube_transfer/rollout_0001/0002/0005/0006/0007/0008`。逐份核对 `run_report.json` 和 `offline_audit.json` 均成功；保存源码清单、连续 tick/action、实际 home、关节限位、接触和媒体审计。

例如 [pick-place 审计](../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/offline_audit.json)、[transfer 审计](../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/offline_audit.json)。这些可另收为公共控制/抓放机制证明，不能增加 13 项拓扑 Task 的覆盖数。原审计主要核对证据与运行结果；若沿用 Keyhole/Coil 的归档标准，还应补冻结 Task 的逐 tick 判据重算及归档时全量哈希核对。

该批次另两次 `status=passed` 分别是预期空抓负例和 limited 短反馈验收，`task_success=False`，不计成功。类似地，PBD/FEM 抓持夹具通过只能支撑公共抓持机制，不能替 Blanket / Knot / Rope 的完整可解性证明。

## 建议执行顺序与节省时间的方法

1. **Lock medium：**先利用已有 1,568 个状态定位终态不满足的原因，完成机构资格/控制修正后再连续实跑；无需重新探索整条操作路线。
2. **Fiber easy → medium → hard：**复用粗护套反馈、IK 和动作阶段，先让 4 芯通过当前子步禁碰与 terminal，再扩展线数。
3. **Buzz F1 → F2/F3：**沿旧路线重新求新摆位 IK，通过后做当前完整物理证明。
4. **Horseshoe easy → 其余两档：**已有对象路径可以省去几何路线搜索，主要工作仍是机器人抓取/交接和目标区后缀。

新增证明可继续关闭 RGB/视频，保留完整 action、逐 tick 状态、配置/源码身份和独立复核。先做离线几何、IK、历史状态诊断，再做新 episode 连续物理执行。不要统一把所有任务改成 25 ms tick：Lock 已测的是 100 ms，Fiber 的禁碰依赖每 solver 子步，柔体也有不同稳定性约束，需逐任务选定并声明时序。

本页只登记候选；已通过数量仍以 [catalog.json](catalog.json) 的 Keyhole / Coil 六例为准。
