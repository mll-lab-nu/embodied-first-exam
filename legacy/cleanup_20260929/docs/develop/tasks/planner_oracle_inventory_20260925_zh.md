# 13 项任务的 planner / oracle 支持清单

核对日期：2026-09-25。范围包括当前源码、`runs/` 中的执行源码快照、规划输入和结果，以及 Git 提交 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6` 中保留的旧任务包。本轮仅检查源码与既有证据，没有运行物理、恢复旧入口或修改任务实现。

后续方案见[历史控制链回收、标准 segment 执行与 planner 编写计划](planner_recovery_and_standard_execution_plan_20260925_zh.md)，其中区分可以复用的策略、必须替换的旧执行层和当前框架缺口。

**按“固定代表曾由机器人完成任务，且控制脚本／指令可追溯”统计，主表 39 个档位中有 21 个；它们分布在 9 个任务中。其中 6 个任务的三档均有历史完整机器人流程。** Horseshoe 另有旧基础版及三条接近路线的完整流程，但它们不是新选定的形状三档。

**当前新标准 simulator 尚未找到接入并验收的全流程 oracle。** [当前 planning 说明](../../../topogym/planning/README.md)明确只保留 Coil 参考运动采样；[motions/cast_coil.py](../../../topogym/planning/motions/cast_coil.py) 不负责机器人执行。已部署 Task、成功构建 assets、历史完整执行是三种不同状态。

这里的“完整”按历史任务起点和终点判断：允许档案明确声明的预抓取起点、辅助抓持、分离后持稳。它不自动满足现在的 home 起步、Genesis、当前资产与统一 interaction 控制要求，也不表示该家族所有 seed 均能求解。不能仅凭视频或 `render/replay` 脚本认定有 planner。

## 主三档对照

- **历史完整**：有机器人执行脚本／指令和对应完整成功记录；限制见逐项说明。
- **候选**：已写动作规划或控制流程，但尚无对应完整机器人成功证据。
- **几何 / IK**：有对象路线或关节预演，未完成机器人动力学闭环。
- **外力完整**：有完整无臂／外力流程，不能计为机器人 oracle。
- **未找到**：尚未找到该设置的求解流程；不代表整个任务没有历史代码。

| 任务 | easy | medium | hard |
|---|---|---|---|
| Cast Keyhole | **历史完整**：F1 long_stroke | **历史完整**：F2 eccentric_window | **历史完整**：F3 turnback |
| Cast Coil | **历史完整**：baseline_assembly | **历史完整**：axial_screw_turn，9 mm | **历史完整**：split_turn_offset，9 mm |
| Horseshoe Ring | waist_mild：有几何路径，无完整机器人 planner | u_mild：有几何路径，无完整机器人 planner | waist_ellipse：有几何路径，无完整机器人 planner |
| Hedgehog in Cage | **历史完整**：CLASSIC | **历史完整**：oblique_gate | **历史完整**：gen_keyhole |
| Lock Picking | 几何 / IK：F1 one_retreat | **历史完整**：standard_150mm | 几何 / IK：F3 three_retreats |
| Fiber Bundling | **历史完整**：4 芯 | **历史完整**：8 芯 | **历史完整**：16 芯 |
| Buzz Wire 3D | **历史完整**：F1 triple home_lab_v1 | **历史完整**：F2 home_lab_v4 | **历史完整**：F3 home_lab_v4 |
| Interlocked Claws | **历史完整**：B0 balanced | **历史完整**：C0 balanced | **历史完整**：A0 original |
| Knot Untying | **历史完整**：overhand_trefoil | 候选：figure_eight local_curve_v2 | 候选：double_overhand |
| Blanket Flatten | **历史完整**：simple_folds，旧单臂 | 未找到完整求解：fold_roll，已有初态 | 外力完整；机器人未完成：gathered_twist |
| Rope Threading | 未找到：两环 | 候选：wang_reference_v1 三环；完整参考 IK＋失败实跑 | 未找到：小孔三环 |
| Slotted Post Ring | 未找到：大环顶部解脱 | 未找到：中环倾斜解脱 | 局部机器人：原尺度 28 mm 槽 |
| Orbits | 未找到：两环 | 未找到：三环 | 外力完整＋局部机器人：四环 75%，video_solution_v2 |

这张表与[部署实施记录](variation_deployment_implementation_20260925_zh.md)的具名难度设置对应；后续表外入口归档已将 Keyhole、Buzz 的 `base` 切到 easy；Horseshoe 也已切换为形状三档 easy；Orbits 仍保留不同的旧实例，不能按其默认入口套用此表。

## 1. Cast Keyhole

**easy / medium / hard 均有历史完整控制链。** F1 / F2 / F3 共用路线构造、双臂 IK 和执行器，不是各自必须有一份独立 oracle 文件。

- 规划入口：[family_variants.py](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/family_variants.py)、[robot_motion.py](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/robot_motion.py)。执行入口：[robot_execution.py，`run`](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/robot_execution.py#L26)；调度入口：[family_pipeline.py，`physics` / `qualify_physics`](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/family_pipeline.py#L37)。后者确实调用 `robot_execution`，不是只调用渲染。
- 路线输入：各冻结家族的 [F1](../../../assets/tasks/cast_keyhole/seed_families_v2/F1)、[F2](../../../assets/tasks/cast_keyhole/seed_families_v2/F2)、[F3](../../../assets/tasks/cast_keyhole/seed_families_v2/F3) 下的 `geometry.json`、`robot_motion.json`、`ik_proposal.json`。
- 执行证据：[F1 report](../../../runs/demo_metadata/cast_keyhole/2026-09-21_family_v2_multiview/F1/evidence/robot_physics/report.json)、[F2 report](../../../runs/demo_metadata/cast_keyhole/2026-09-21_family_v2_multiview/F2/evidence/robot_physics/report.json)、[F3 report](../../../runs/demo_metadata/cast_keyhole/2026-09-21_family_v2_multiview/F3/evidence/robot_physics/report.json)，同目录各有 `robot_physics_half` 对照。
- 范围：Genesis；预抓取开始，双指接触后 weld 辅助抓持，执行到两件完全分离并持稳。没有 home 接近、桌面拾取或末态释放；后两者不是该历史任务的完成条件。
- 表外旧默认也有：[旧实例执行源码](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/evidence/runner_sources/robot_execution.py)及[归档说明](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/archive_manifest.json)。它与 F1 新基础代表分开保留。

## 2. Cast Coil

**三档都有完整装配流程。** 还找到了退役的 `eccentric_turn` 完整流程。

| 设置 | 实际执行源码 | 成功证据 |
|---|---|---|
| easy baseline_assembly | [execution_source.py，`main`](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/execution_source.py) | [result.json](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/result.json) |
| medium axial_screw_turn | [execution_source.py，`main`](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/axial_screw_turn/physics/execution_source.py#L10) | [result.json](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/axial_screw_turn/physics/result.json) |
| hard split_turn_offset | [execution_source.py，`main`](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/split_turn_offset/physics/execution_source.py#L10) | [result.json](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/split_turn_offset/physics/result.json) |
| 表外 eccentric_turn | [execution_source.py](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/eccentric_turn/physics/execution_source.py) | [result.json](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/eccentric_turn/physics/result.json) |

规划在同目录 `source_robot_plan.py` 的 `build`，装配阶段与反向路线在 `source_assembly_task.py`，几何专用路线在 `source_inverse_design.py`；`source_plan.json` 保存该次执行的具体计划。medium / hard 的计划模板分别记录 9 mm 轴移／错位参数。

范围：Genesis；从两件分离、机器人预抓取开始，经接触辅助抓持、对齐、插入、旋转闭合、落桌、释放、撤手和静置。基础报告的 `objective=assemble`、`success=true`，不是把拆解视频倒放当装配。家族的严格步长验收存在差异，见[物理汇总](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/physics_summary.json)；完整任务成功与全部数值资格分开统计。

`face_small / depth_thick / corner_cut` 的资产构造可追溯，但本次未找到这些具名设置各自完成机器人流程的证据，不由上述成功自动继承。

## 3. Horseshoe Ring

同日更新：用户选定 waist_mild / u_mild / waist_ellipse 为暂定 easy / medium / hard；已有完整零件几何证书，不增加本清单的完整机器人支持计数。下文关于原余量方案的讨论属于历史状态。详见[选定方案](horseshoe_existing_candidates_tier_review_20260925_zh.md)。

**旧基础版与旧 F1 / F2 / F3 都有完整机器人流程；新余量三档仍没有。**

- 主流程：[physical_demo.py，`run` / `extract_ring`](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1/physical_demo.py)，依次调用取环、搬运和放置；执行器：[execution_source.py，`PhysicalMotion`](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1/execution_source.py#L22)。路径拆分在同目录 `physical_plan.py / physical_extraction.py / physical_place.py`。
- 变体路线：[family_routes.py，`plan` / `execute`](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/F2_source/family_routes.py#L19)。源码的 `ROUTES` 明确为 F1 `high_approach`、F2 `outer_approach`、F3 `rear_approach`。较完整依赖快照在 [source_snapshot/topogym/tasks/horseshoe_ring](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring)。
- 证据：[基础版物理档案](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1)、[四组完整流程说明](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/README.md)、[恢复时核对的物理来源](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/source_physics_validation.json)。
- 范围：旧 Genesis 双臂流程，取环并放桌；抓持模型和起始条件仍按各次旧配置。`tutorial_solvable_v3` 与当前 `reference` 的链环结构也不同，不能直接复用成功标签。

新 easy / medium / hard 要改变可穿过的几何余量；上述三条接近路线没有实现这件事。coupled-shape / fixed-trace 候选中的对象位姿见证与局部 IK，也不能替代这些新设置的完整机器人 oracle。

## 4. Hedgehog in Cage

**CLASSIC / oblique_gate / gen_keyhole 均有历史完整机器人流程；另有三个表外家族。**

- easy CLASSIC：完整执行入口在 Git 快照 `topogym/tasks/hedgehog_in_cage/extract.py:18` 的 `main`；几何路线与抓取规划在同版本 `plan_escape.py / plan_robot.py / plan_release.py`。工作目录中这些旧文件已移除，读取方法见文末。成功流程与预抓取范围见 [CLASSIC archive_manifest](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood/archive_manifest.json)；这里只确认对应源码可取回，未宣称 Git 版本与原运行源码逐字一致。
- medium oblique_gate：[family_motion.py](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/provenance/family_motion.py) 规划，[family_runtime.py，`execute`](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/provenance/family_runtime.py#L171) 执行；[物理报告](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/physics/report.json)。
- hard gen_keyhole：执行源码在 [generator_source/family_runtime.py](../../../runs/variant_checks/hedgehog_in_cage/2026-09-19_replacements_v2/gen_keyhole_fixed/generator_source/family_runtime.py)，其 SHA-256 与[成功报告](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2/gen_keyhole/physics/report.json)的 `runner_sha256` 一致。几何、对象路线及机器人计划构造在 Git 的 `classic_families.py`，函数为 `plan / robot_plan / stable_release`；固定代表的 `ik_before_geometry.json / grasp.json` 已保存在[完整档案](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2/gen_keyhole)。名字叫 `generator_source` 不表示里面只有几何代码。
- 范围：Genesis 实跑；预抓取、接触辅助抓持、出笼、落桌、解除辅助、撤手和自由静置。IK 工具引用 MuJoCo 不等于该执行器使用 MuJoCo 推进物理。

表外有 `fixed_side_window` 的[完整报告](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2/fixed_side_window/physics/report.json)，以及 `staggered_gates`、`helical_guide` 各自的 [B 家族源码与证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_b_staggered_gates_v1)、[C 家族源码与证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_c_helical_guide_v1)。这些历史完整代表不重新纳入主三档。

## 5. Lock Picking

**medium 标准版有完整流程；easy F1、hard F3 没有对应完整机器人成功证据。**

- 最直接的成功来源：[physical_controller.py](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/physical_controller.py)＋[commands.jsonl](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/commands.jsonl)。后者保留 57 条指令，包括抓取、回退换槽、中途换抓、最终插入、松爪和结束；引用的 [regrasp_arm_path.json](../../../runs/environment-solvability/lock_picking/spaced_initial/attempt04/regrasp_arm_path.json) 也仍存在。这是一套可追溯的脚本式解法，不是只有状态回放。
- [原执行 result.json](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/result.json)：`success / reached_endpoint / at_rest / grasp_released` 均为 true。历史三视角是这次执行的状态重渲染，重建了未记录的夹爪被动连杆；[归档说明](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/README.md)没有将重渲染计为新增物理成功。
- Git 还保留结构化入口：`runner.py:106 execute`、`:188 run`；`planner.py:6 next_entry_angle`、`:15 insertion_window`；`oracle.py:10 execute_reindex`。它们属于旧任务包，尚未适配新 simulator。
- **不能把这套 oracle 直接标到 F1 / F3：** `execute_reindex` 明确要求证书中的 `minimum_required_decoupling_retreats == 2`。F1 一次回退和 F3 三次回退需要改控制逻辑，而不是仅换参数文件。
- F1 / F3 及表外 F2 two_unequal 的已有能力见 [seed_generator_v1/implementation](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1/implementation)：逆向路线、证书、IK、运动学渲染。尚无它们完成抓取至终点释放的动力学证明。

## 6. Fiber Bundling

**4 / 8 / 16 芯都有对应的完整机器人序列。**

| 档位 | 执行源码 | 对应结果 |
|---|---|---|
| easy，4 芯 | [source/robot_sequence.py](../../../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1/source/robot_sequence.py) | [report.json](../../../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1/report.json) |
| medium，8 芯 | [source/robot_sequence.py](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1/source/robot_sequence.py) | [report.json](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1/report.json) |
| hard，16 芯 | [source/robot_sequence.py](../../../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1/source/robot_sequence.py) | [report.json](../../../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1/report.json) |

共同入口是 `RobotSequence.run`，包含 `grasp / prepare / align_and_check_bundle`，同目录 `ik_search.py / sequential.py` 提供规划。三个代表的环内半径都是 13.5 mm；Genesis 中只抓粗护套，接触后辅助抓持，末态仍持住。报告的 `full_threading_verified` 与全程线形步长收敛是不同检查，后者不能在三档间互相继承。随机生成的所有芯数／环径也没有因此获得完整执行资格。

## 7. Buzz Wire 3D

**三个指定修订都有 home → 接近拾取 → 全程走线 → 放回释放的完整机器人流程，是接入新 oracle 时比较合适的首批候选。**

| 档位／修订 | 执行源码 | 完整执行身份 |
|---|---|---|
| easy，F1 triple home_lab_v1 | [robot_runtime.py，`execute`](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/evidence/source/evidence/nominal/implementation/robot_runtime.py#L22) | [archive_manifest](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/archive_manifest.json) |
| medium，F2 home_lab_v4 | [robot_runtime.py，`execute`](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/evidence/source/evidence/nominal/implementation/robot_runtime.py#L22) | [archive_manifest](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/archive_manifest.json) |
| hard，F3 home_lab_v4 | [robot_runtime.py，`execute`](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/evidence/source/evidence/nominal/implementation/robot_runtime.py#L22) | [archive_manifest](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/archive_manifest.json) |

同目录 `robot_plan.py / family_plan.py / supported_plan.py / home_plan.py` 分别负责主路径、家族路线、拾放及 home 接近。每个档案均有 nominal / refined 执行记录，`task_result` 明确为 `robot_physics`、`complete=true`、`home_start=true`、`assistance=[]`。环最初已套在导线上（`prethreaded=true`），任务不是从铁丝外先把环套进去。

表外 [旧 F1 home_lab_v4](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_home_lab_v4_full) 也有完整 robot runtime，但它是旧双拱，不能冒充新三拱。更早的 compact / supported_pick_place 记录是同家族流程修订，不按每个录像日期另计一种变体。

特别注意：当前保留默认对应的旧 `spatial_maze_v2` 完整档案是**无臂外力台架**，执行代码为 [physics.py，`run`](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/source_evidence/implementation/physics.py#L146)；其[归档清单](../../../runs/demo_metadata/buzz_wire_3d/2026-09-18_spatial_maze_fixture_v1/archive_manifest.json)明确 `counts_as_complete_robotics_demo=false`。它不能继承三档的机器人成功状态。

## 8. Interlocked Claws

**B0 balanced / C0 balanced / A0 original 都有完整历史机器人流程；B0、C0 的执行后端与现在不同。**

| 档位 | 规划／执行源码 | 证据与范围 |
|---|---|---|
| easy，B0 balanced v2 | [family_balanced_robot.py，`build_plan`](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/implementation/family_balanced_robot.py#L23)；[family_robot.py，`execute`](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/implementation/family_robot.py#L217) | [archive_manifest](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/archive_manifest.json)：MuJoCo；预抓取辅助，分离后持稳 |
| medium，C0 balanced v2 | [family_balanced_robot.py](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/implementation/family_balanced_robot.py)；[family_robot.py](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/implementation/family_robot.py) | [archive_manifest](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/archive_manifest.json)：MuJoCo；预抓取辅助，拆解、放置、释放和静置 |
| hard，A0 original | [physical.py](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/implementation/physical.py)；[reference.py](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/implementation/reference.py) | [archive_manifest](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/archive_manifest.json)：Genesis；原始 12 阶段，理想刚性辅助抓持 |

表外旧 `helical_crown`、旧大尺寸 `orthogonal_gate` 也保留各自的 [B0 旧执行源码](../../../runs/demo_metadata/interlocked_claws/2026-09-19_helical_crown_physical_v1/implementation/family_robot.py)、[C0 旧执行源码](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_physical_v1/implementation/family_robot.py)及同级档案，但不是当前 easy / medium 代表。

**有 oracle 不等于结构强制该解法。** [B0 新版说明](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/README.md)包含有限错误动作和固定姿态直拉阻挡检查，但不证明所有侧移绕行都被排除。C0 也不能因为 planner 做了两次翻转，就声称两次翻转是全局必需。

## 9. Knot Untying

**easy trefoil 有完整历史流程；medium / hard 已写候选控制器，尚未跑通。**

- easy：[untying.py，`RobotUntyingActions`](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/implementation/topogym/tasks/knot_untying/untying.py#L124)，结合 [control.py](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/implementation/topogym/tasks/knot_untying/control.py) 的双臂 IK；真正执行入口为 [physics_probe.py，`main`](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/implementation/topogym/tasks/knot_untying/physics_probe.py#L119) 的 `robot_untying` 模式。75 秒完整抓持、解结、放回释放及静置见 [README](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/README.md)、[report](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json)。预备位开始、接触辅助抓持；P3 网格收敛和通用双手交接资格尚不完整。
- medium / hard：[family_actions.py，`FamilyUntyingActions`](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v11_home_support_reanchor/implementation/topogym/tasks/knot_untying/family_actions.py#L170) 已包含撑开、观测绳段、穿出、换抓、释放与终态阶段，是有实质内容的候选 oracle。两家族参数由 `route_for_config` 分派，不是只有 knot 几何。
- 失败证据：[figure-eight local_curve](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v5_local_curve/report.json) 超局部应变；[figure-eight v9](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v9_pitched_regrasp/report.json) 余绳不足；[double-overhand v8](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v8_pitched_regrasp/report.json) IK 不可达。更晚 home 接近尝试也未完成，不能凭文件版本更新提升状态。

表外 left_overhand、原尺寸 figure_eight 没有查到各自完整机器人成功证据。

## 10. Blanket Flatten

- **easy simple_folds：历史完整。** [robot_demo.py，`main`](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/source_snapshot/robot_demo.py#L11) 调用 [execution.py，`Execution.pull / flatten / final_check`](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/source_snapshot/execution.py)。[report](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/report.json) 与[归档清单](../../../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/archive_manifest.json)对应 32.5 秒旧单臂、辅助抓持流程。当前标准 Task 使用双臂配置，因此不能直接当作当前机器人已支持。
- **medium fold_roll：已有初态，没有查到该初态的完整机器人展平流程。** easy 的拉角脚本可以作为尝试起点，不能据此标“支持”。
- **hard gathered_twist：外力完整，机器人未完成。** [virtual_hands.py，`VirtualHands.unfold`](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/source_snapshot/virtual_hands.py#L222) 实现两处材料区域的速度驱动；[external_review.json](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/external_review.json)明确 `external_manipulation_verified=true`、`full_robot_task_verified=false`。不能把“两只虚拟手”理解成两条机器人机械臂。

已有 gathered robot / ALOHA refinement 尝试仅为候选或局部整理。hard 在当前部署中还缺物理准备流程，这与是否保留旧外力解法是两个问题；three_folds / fold_spiral 等表外初态同样不继承 easy 的成功记录。

## 11. Rope Threading

**medium 三环已有完整参考规划和候选机器人控制链，但尚无完整成功实跑。**

- 动作流程：[reference_actions.py，`ReferenceThreadingActions`](../../../runs/environment-solvability/rope_threading/full_feedback_ik_20260921_attempt_3/implementation/topogym/tasks/rope_threading/reference_actions.py#L24)。在线换手控制：[feedback_actions.py，`FeedbackThreadingActions`](../../../runs/environment-solvability/rope_threading/full_feedback_ik_20260921_attempt_3/implementation/topogym/tasks/rope_threading/feedback_actions.py#L15)。参考 IK 在同目录 `reference_ik.py`，反馈 IK 在 `feedback_ik_plan.py / feedback_paths.py`。
- [完整参考 IK 方案](../../../runs/environment-solvability/rope_threading/ik_margin_v3_20260920/README.md) 已覆盖参考动作序列；[物理尝试报告](../../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1/report.json) 在约 66.115 秒因右臂目标不可达停止，`full_demo=false / full_threading_verified=false`。离线参考全路径可行不保证实测柔绳偏离后在线换手仍可行。
- easy 两环、hard 小孔三环没有对应完整 planner／实例证据。不能把少执行一次循环、缩小环径视为已验证支持。

## 12. Slotted Post Ring

**没有完整机器人 oracle；原尺度有局部机器人控制，clearance36 表外候选有完整外力流程。**

- 原尺度 hard 的局部机器人源码：[robot_sequence.py，`Episode`](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_partial_robot_disc_handoff_v1/source_code/robot_sequence.py#L26)，包含移动、抓持、交接和释放原语；[局部执行说明](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_partial_robot_disc_handoff_v1/README.md)明确环未完全解出，控制跟踪资格也没有整体通过。
- 36 mm 槽候选：完整外力执行器 [fixture.py，`route / execute`](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/source_code/fixture.py#L35)，配套 [main/schedule.json](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/main/schedule.json)；[147 秒完整流程说明](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/README.md)。旧 MuJoCo 外力仿真，无机器人。
- 这个 36 mm 是**柱槽宽度**，不是新 easy 的“大环”。所以它不填入 easy，也不提升 hard 原尺度 28 mm 的状态。新 easy / medium 暂无对应求解流程。

## 13. Orbits

**hard 有完整 rope-only 解法与动作表；机器人仅有局部流程和重定向预检。easy / medium 尚无对应 planner。**

- 动作表：[rope_video_solution_v2.json](../../../configs/task_variants/orbits/rope_video_solution_v2.json)，四环、75% 器具、93 个动作。生成器：[orbits_build_video_route_v2.py](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_video_full_v2/source/source_snapshot/orbits_build_video_route_v2.py)；执行器：[rope_route.py，`execute`](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_video_full_v2/source/source_snapshot/topogym/tasks/orbits/rope_route.py#L23)、[rope_only_demo.py](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_video_full_v2/source/source_snapshot/topogym/tasks/orbits/rope_only_demo.py)。
- [完整流程身份](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_video_full_v2/recording_manifest.json) 标为 `external_physics`、`complete=true`、`continuous_execution=true`，同时 `physics_qualified=false`；[场景报告](../../../runs/environment_bootstrap/orbits/solution_development_v1/rope_video_full_v2/scene_report.json)记录 MuJoCo、无机器人、材料点外部约束。它是可参考的全解法，不是完整机械臂 oracle。
- [robot_video_retarget_v1/full_route_preflight.json](../../../runs/environment_bootstrap/orbits/solution_development_v1/robot_video_retarget_v1/full_route_preflight.json) 指出动作中存在超过双手控制点数量的阶段，以及有限搜索未找到安全直接抓取的目标。后续 home pickup / 两控制点探针没有完成机器人全解；不能把它们拼接到无臂路线后计为机器人成功。
- 当前默认 `reference85` 与这个 75% / video-v2 工作初态也不同。减少为两环、三环仍需重新制定回穿次序和抓取策略。

## Git 源码坐标与后续接入

本文的 Git 坐标均固定到 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6`，不是可能移动的分支名。可以只读查看，不改当前工作树：

```bash
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/tasks/hedgehog_in_cage/extract.py
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/tasks/hedgehog_in_cage/classic_families.py
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/tasks/lock_picking/runner.py
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/tasks/lock_picking/planner.py
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/tasks/lock_picking/oracle.py
```

[源码核对索引](planner_oracle_sources_20260925.json)记录本文直链 Python 文件与上述 Git 文件的 SHA-256、函数／类坐标。本次检查链接存在性并解析 AST，没有导入或执行旧脚本，也没有声称全部历史依赖能在当前环境直接运行。

后续可以优先适配 Buzz 三档，再迁移 Keyhole／Coil／Hedgehog／Fiber 的固定代表；这些已有完整任务动作，主要工作是统一观测、动作下发、抓持能力及起点。Claws B0／C0 需要替换旧 MuJoCo 执行链，Blanket easy 需要处理机器人配置变化。Horseshoe 新形状三档、Lock F1／F3，以及未成功的柔体任务仍包含解法设计／验证工作，不能仅按“复制 oracle 文件”估算。
