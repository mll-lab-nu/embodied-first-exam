# 三档变体资产代码位置清单

核对日期：2026-09-25。对应 [13 任务 easy / medium / hard 评估表](variant_difficulty_review_20260924_zh.md)。表中编号沿用原表，不调整难度顺序。

本文保留部署前的追溯结论；任务目录迁移和当前接入状态见[部署实施记录](variation_deployment_implementation_20260925_zh.md)。原[部署计划](variation_deployment_plan_20260925_zh.md)已获授权并实施，下面“尚未接入”等描述指清单核对时的状态。

本轮检查当前 Python 源码、历史源码快照、配置和资产文件，未导入项目、执行生成器或运行仿真。**“代码还在”不等于“当前 Env 已接入”，也不等于“可解性、无捷径或完整机器人流程已验收”。** 行号为本次读取位置，代码继续修改后可能移动。

位置分三类：

- **当前源码**：`topogym/` 内保留的几何实现。部分函数尚未接入默认 Task 或具名 variation。
- **历史源码**：`runs/` 或根目录 `assets/` 内的实现快照，可用于迁移；不能假定旧 import、相对路径和后端在当前目录直接可运行。
- **配置／资产**：YAML、JSON、OBJ、URDF 等参数或产物，不冒充 Python 生成脚本。

下文为按功能选取的代码入口，不重复列出大量相同运行快照。检索覆盖当前 `topogym/`、`scripts/`、`assets/`、`configs/` 以及 `runs/`、`reports/`、`legacy/`；“未找到”指本次路径、符号和家族名检索未找到对应专用实现，不构成对所有压缩包或未命名实验的穷尽证明。

## 总表：原表位置与当前保留情况

| 原表位置 | setting | 对应代码定位 | 保留情况 |
|---|---|---|---|
| 1 easy / medium / hard | Keyhole F1 / F2 / F3 | 下文 K1–K4 | 专用三族生成链在历史源码中；当前几何入口主要是基础模板构建 |
| 2 easy | Coil baseline_assembly | C1 | 当前源码有基础几何生成 |
| 2 medium / hard | axial_screw_turn / split_turn_offset | C2–C3 | 当前源码保留反向设计生成及参数；未注册同名运行 variation |
| 3 easy / medium / hard | Horseshoe 宽／标准／窄余量 | H1–H2 | 有基础几何和旧路线家族生成器；**没有找到新余量三档生成实现** |
| 4 easy | Hedgehog CLASSIC | G1 | 当前源码有十刺五窗模板生成 |
| 4 medium / hard | oblique_gate / gen_keyhole | G2–G3 | 历史代码可选取固定原型并缩放重建；完整原型资产仍在 |
| 5 easy / medium / hard | Lock F1 / standard_150mm / F3 | L1–L2 | 当前参数化几何＋历史槽位／限位家族采样器 |
| 6 easy / medium / hard | Fiber 4 / 8 / 16 芯 | F1–F2 | 当前源码可按线数生成；历史密度采样与保存入口仍在 |
| 7 easy / medium / hard | Buzz F1 / F2 / F3 | B1–B2 | 当前有通用导线／工具生成；三族线路构造函数在历史源码中 |
| 8 easy | Claws B0 当前同形螺旋件 | I1 | 当前源码有 `helical_claws_balanced_v2` 构造 |
| 8 medium | Claws C0 当前紧凑双窗 | I2 | 当前源码有 `orthogonal_gate_balanced_v2`；不是新提议的两件全等框 |
| 8 hard | Claws A0，基础 | I3 | 当前源码有原始 Claw 生成 |
| 9 easy / medium / hard | Trefoil / figure_eight / double_overhand | N1–N2 | 三结型均在当前源码；八字放大 25% 候选需另配参数 |
| 10 easy / medium | simple_folds / fold_roll | Q1 | 当前几何支持折叠及卷曲；fold_roll 未作为具名 variation 注册 |
| 10 hard | gathered_twist | Q2 | 聚褶／扭转目标和物理准备流程保留在历史源码 |
| 11 medium | Rope 三环 wang_reference_v1，基础 | R1 | 当前源码可从三环 reference 生成 |
| 11 easy / hard | 两环／三环小孔 | R1 可作为改造基础 | **没有找到对应专用生成实现**；当前 Layout 不暴露环数／环径分档 |
| 12 hard | Slotted 原尺寸，基础 | S1 | 当前源码有参数化几何；另有槽宽 36 mm 的历史候选 |
| 12 easy / medium | 大／中目标环顶部退出 | S1 可作为改造基础 | **没有找到对应 setting 的专用生成实现**；36 mm 是柱槽宽，不是目标环内径 |
| 13 hard | Orbits 四环，基础 | O1 | 当前源码有四环参数化几何 |
| 13 easy / medium | Orbits 两环／三环 | O1 需改造 | **没有找到对应生成实现；现有校验明确只接受四环** |

## 1. Cast Keyhole：F1 / F2 / F3

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| K1 | [当前 cast_keyhole.py:227](../../../topogym/assets/geometry/cast_keyhole.py#L227)，`generate_assets`；同文件 `KeyholeAssembly` | 基础模板读入和实体输出。不能仅用此入口名称认定已支持新基础 F1；它不接收 F1/F2/F3 家族参数 |
| K2 | [历史 family_variants.py:100](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/family_variants.py#L100)，`build` | **三档共同的关键构建入口**：从固定家族核心构造外形及族内参数变化 |
| K3 | [历史 variants.py:100](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/variants.py#L100)，`sample`；`:188 prepare`、`:217 generate` | F1/F2/F3 的 seed、参数选择和实例输出，调用 K2 |
| K4 | [历史 variant_assets.py:37](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/variant_assets.py#L37)，`generate_variant_assets` | 将记录中的逆向设计几何物化为网格、碰撞分块与 URDF |

更早的结构设计源码也在同一 `sources/`： [inverse_variants.py](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/inverse_variants.py)、[eccentric_window.py](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/eccentric_window.py)、[turnback.py](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/sources/turnback.py)。复用最终三档应优先查看 K2/K3 与冻结核心，而非直接用早期默认参数重新生成。

固定核心：[F1 geometry.json](../../../assets/tasks/cast_keyhole/seed_families_v2/F1/geometry.json) → easy；[F2](../../../assets/tasks/cast_keyhole/seed_families_v2/F2/geometry.json) → medium；[F3](../../../assets/tasks/cast_keyhole/seed_families_v2/F3/geometry.json) → hard。总目录：[seed_families_v2](../../../assets/tasks/cast_keyhole/seed_families_v2)。

## 2. Cast Coil：基础／轴向螺旋／分段错位

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| C1 | [当前 cast_coil.py:243](../../../topogym/assets/geometry/cast_coil.py#L243)，`generate_assets` | easy 基础装配几何；接受模板和尺度 |
| C2 | [当前 cast_coil.py:266](../../../topogym/assets/geometry/cast_coil.py#L266)，`synthesize(kind, output, …)` | **medium axial_screw_turn、hard split_turn_offset 的实际几何合成代码**；沿目标运动扫掠切削实体并输出模板。也保留已从三档剔除的 eccentric_turn |
| C3 | [迁移后的 cast_coil_variants.py](../../../topogym/assets/geometry/cast_coil_variants.py)，`FAMILY_PARAMETERS / family_parameter` | 原 task_variations/cast_coil.py 的机构参数；同文件 `create_template` 另保留 face_small / depth_thick / corner_cut 外形变体，不对应三档主机制 |

运动构造依赖仍在 [planning/motions/cast_coil.py](../../../topogym/planning/motions/cast_coil.py)，包括 `variant_route`；它是 C2 的输入辅助，不单独当作资产生成器。

固定家族数据：[axial_screw_turn.json](../../../assets/tasks/cast_coil/seed_families_v1/axial_screw_turn.json)、[split_turn_offset.json](../../../assets/tasks/cast_coil/seed_families_v1/split_turn_offset.json)。当前参数工具中轴向／错位默认量为 6 mm，原表选的是 9 mm 代表；迁移时必须读出选定实例实际参数，不能只靠 family 名字。历史完整生成实现另在 [source_inverse_design.py](../../../runs/demo_metadata/cast_coil/2026-09-21_variation_restore_v1/axial_screw_turn/physics/source_inverse_design.py)。

## 3. Horseshoe Ring：新余量三档与旧路线三族分开

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| H1 | [当前 horseshoe_ring.py:149](../../../topogym/assets/geometry/horseshoe_ring.py#L149)，`HorseshoeAssembly`；`:392 generate_assets` | 原基础马蹄、链与目标环的模板构建，可作为新三档改造基础 |
| H2 | [历史 variant_generator.py:91](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring/variant_generator.py#L91)，`create_instance`；`:179 retarget_seed` | 旧 F1/F2/F3 的参数抽样和路线重定向；**不能对应成新表的大／中／小余量** |

另有历史 [family_space.py:74](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring/family_space.py#L74) `build`，用于原家族空间构建。保留库包括 [family_space_v1](../../../assets/tasks/horseshoe_ring/family_space_v1)、[family_space_v2](../../../assets/tasks/horseshoe_ring/family_space_v2)、[coupled_shapes_v1](../../../assets/tasks/horseshoe_ring/coupled_shapes_v1) 和 [fixed_trace_v1](../../../assets/tasks/horseshoe_ring/fixed_trace_v1)。这些旧形状／路线设计不能自动填入新表三档。

缺口：尚未找到计算通行区间并生成 wide / standard / narrow 三个代表的代码或确定参数集。

## 4. Hedgehog in Cage：CLASSIC／斜窗／顶部钥匙孔

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| G1 | [当前 hedgehog_in_cage.py:267](../../../topogym/assets/geometry/hedgehog_in_cage.py#L267)，`generate_assets` | easy CLASSIC；模板读取明确校验十根刺，不能直接拿来生成六刺 GEN |
| G2 | [历史 variants.py:271](../../../runs/variant_checks/hedgehog_in_cage/2026-09-19_replacements_v2/gen_keyhole_fixed/generator_source/variants.py#L271)，`materialize`；`:363 generate` | medium oblique_gate、hard gen_keyhole 的原型选择、参数抽样和实例生成；也保留 fixed_side_window |
| G3 | [历史 variant_validation.py:33](../../../runs/variant_checks/hedgehog_in_cage/2026-09-19_replacements_v2/gen_keyhole_fixed/generator_source/variant_validation.py#L33)，`build_assets` | **实际资产构建**：复制固定原型资产，再对笼体网格与碰撞分块应用参数变化；不是从空白重新设计钥匙孔 |

原型库：[classic_3star](../../../assets/tasks/hedgehog_in_cage/classic_3star) → easy；[seed_families_v1/oblique_gate](../../../assets/tasks/hedgehog_in_cage/seed_families_v1/oblique_gate) → medium；[seed_families_v2/gen_keyhole](../../../assets/tasks/hedgehog_in_cage/seed_families_v2/gen_keyhole) → hard。注意 oblique_gate 在旧库，GEN 在 v2 库。

当前几何文件末尾还保留 `Sweep / annular_cells / rectangular_gate_cells` 等扫掠建模函数，但不构成完整的 GEN 生成入口。未找到原文档提及的 `classic_families.py / prepare_classic_prototypes.py` 独立 Python 文件；已生成原型仍在，G2/G3 的原型派生链也仍在。旧 staggered_gates / helical_guide 属于历史方案，不占当前三档。

## 5. Lock Picking：一次／两次／三次回退

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| L1 | [当前 lock_picking.py:30](../../../topogym/assets/geometry/lock_picking.py#L30)，`LockGeometry`；`:577 export_assets` | 基础与派生槽位参数的盘、钥匙、限位件和支架输出；medium 基础可复用 |
| L2 | [历史 variants.py:139](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1/implementation/variants.py#L139)，`sample`；`:253 write_instance` | easy F1、hard F3 的槽位／限位家族选择、条件尺寸采样和资产输出；同时保留已剔除的 F2 不等角双回退 |

固定机构在 [seed_families_v1/catalog.json](../../../assets/tasks/lock_picking/seed_families_v1/catalog.json)。medium 使用原 standard_150mm，不能误用目录中的 F2 two_unequal 冒充原基础。当前 `variant_geometry` 还包含其他局部几何扰动，不等于新的必要回退家族。

## 6. Fiber Bundling：4／8／16 芯

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| F1 | [当前 fiber_bundling.py:33](../../../topogym/assets/geometry/fiber_bundling.py#L33)，`FiberLayout`；`:558 generate_anchored_assets` | 三档共用；`fiber_count=4/8/16` 对应 easy/medium/hard，生成固定终端、护套、细线和环等资产 |
| F2 | [历史 generation.py:56](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit/instances/fixed_seed0/generator_source/topogym/tasks/fiber_bundling/generation.py#L56)，`build_episode`；`:124 save_instance` | 三档密度家族的抽样、拒绝与实例保存链 |

采样逻辑：[历史 variants.py:22](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit/instances/fixed_seed0/generator_source/topogym/tasks/fiber_bundling/variants.py#L22) `sample_parameters`；参数域：[fiber_bundling_density_v1.yaml](../../../configs/task_variants/fiber_bundling_density_v1.yaml)。三档固定代表环内半径均为 13.5 mm，不只设置线数后就能声称复现了历史全部配置。

当前 [FiberBundlingTask](../../../topogym/tasks/fiber_bundling/common.py)确实调用 `generate_anchored_assets` 并读取 `geometry`，但 sparse/standard/dense 还不是统一解析器中的具名 variation。

## 7. Buzz Wire 3D：三拱／错层八字／多平面

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| B1 | [当前 buzz_wire_3d.py:32](../../../topogym/assets/geometry/buzz_wire_3d.py#L32)，`BuzzWireLayout`；`:667 generate_assets` | 三档共用的导线、工具环、底座与支撑几何；可接受 authored controls |
| B2 | [历史 family_geometry.py:19](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/evidence/source/evidence/nominal/implementation/family_geometry.py#L19)，`vertical_wave_controls`；`:150 compose` | **三族线路构造**：F1 波浪；F2 comb/eight/w_valleys；F3 comb/w_valleys/omega/coil |

三族设计参数：[vertical_wave_v1.yaml](../../../configs/task_variants/buzz_wire_3d/vertical_wave_v1.yaml)、[over_under_eight_v1.yaml](../../../configs/task_variants/buzz_wire_3d/over_under_eight_v1.yaml)、[plane_switch_v1.yaml](../../../configs/task_variants/buzz_wire_3d/plane_switch_v1.yaml)。精确的正式代表应以 [fixed_home_lab_v4.yaml](../../../configs/task_variants/buzz_wire_3d/fixed_home_lab_v4.yaml) 指向的包为准，不能仅从原设计 YAML 推断已还原最终缩放与摆位。

对应资产目录：[F1 三拱](../../../assets/tasks/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1)、[F2](../../../assets/tasks/buzz_wire_3d/F2_compact_toy_s70_home_lab_v4)、[F3](../../../assets/tasks/buzz_wire_3d/F3_compact_toy_s70_home_lab_v4)。F1/F2 包内还各有 `planning/implementation/geometry.py` 快照；这类快照不是新增家族。旧双拱及 wood/toy/supported 修订不增加表格档位。

## 8. Interlocked Claws：B0／C0／A0

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| I1 | [当前 interlocked_claws.py:328](../../../topogym/assets/geometry/interlocked_claws.py#L328)，`FamilyModel._helical_claws_balanced_v2` | easy 当前 B0：两个同形三爪螺旋件。选择字符串应为 `helical_claws_balanced_v2` |
| I2 | [当前 interlocked_claws.py:365](../../../topogym/assets/geometry/interlocked_claws.py#L365)，`FamilyModel._orthogonal_gate_balanced_v2` | medium 当前 C0：紧凑等尺寸双窗框架与配合件；不是两件全等框的新提案 |
| I3 | [当前 interlocked_claws.py:64](../../../topogym/assets/geometry/interlocked_claws.py#L64)，`ClawAssembly`；`:130 generate_assets` | hard A0 原始 Claw |

I1/I2 共用 [FamilyModel:243](../../../topogym/assets/geometry/interlocked_claws.py#L243) 构建实体，`:419 save` 输出资产。旧 `_helical_crown`（`:267`）和 `_orthogonal_gate`（`:299`）也保留；它们与当前 balanced 修订不是同一资产。不能因表格写 B0 helical_crown 就选到已退役的旧冠笼／翼片版。

冻结资产：[authored_compound_v2/helical_claws_balanced_v2](../../../assets/tasks/interlocked_claws/authored_compound_v2/helical_claws_balanced_v2)、[orthogonal_gate_balanced_v2](../../../assets/tasks/interlocked_claws/authored_compound_v2/orthogonal_gate_balanced_v2)。当前 [InterlockedClawsTask](../../../topogym/tasks/interlocked_claws/common.py)调用基础 `generate_assets`；当前文件含 B/C 生成代码不等于默认 Task 已能选择 B/C。

## 9. Knot Untying：三叶／八字／双重单结

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| N1 | [当前 knot_untying.py:23](../../../topogym/assets/geometry/knot_untying.py#L23)，`KnotLayout`；`:226 generate_assets` | 三档中心线及管状网格；`family=overhand_trefoil / figure_eight / double_overhand` |
| N2 | [当前 task_variations/knot_untying.py](../../../topogym/tasks/task_variations/knot_untying.py)，`VARIATIONS` | 已有具名 figure_eight / double_overhand / left_overhand 参数映射；基础走 base |

八字结放大 25% 候选额外使用 [figure8_local_curve_v2.yaml](../../../configs/task_variants/knot_untying/profiles/figure8_local_curve_v2.yaml) 中结区参数，资产为 [figure_eight_local_support_v2](../../../assets/tasks/knot_untying/figure_eight_local_support_v2)。只选择 `figure_eight` 不会自动等价于这个指定候选。

其余固定资产：[trefoil_v1](../../../assets/tasks/knot_untying/trefoil_v1)、[figure_eight_v1](../../../assets/tasks/knot_untying/figure_eight_v1)、[double_overhand_v1](../../../assets/tasks/knot_untying/double_overhand_v1)。left_overhand 是手性泛化，不占新增难度档。

## 10. Blanket Flatten：简单折叠／折叠加卷／聚褶扭转

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| Q1 | [当前 blanket_flatten.py:16](../../../topogym/assets/geometry/blanket_flatten.py#L16)，`BlanketLayout`；`:134 generate` | easy simple_folds 与 medium fold_roll：已有 `fold_count` 和 `roll_fold_count / roll_angle_deg` 等生成参数 |
| Q2 | [历史 gathered_geometry.py:11](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/gathered_geometry.py#L11)，`gathered_target`；[preparation.py:132](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/preparation.py#L132)，`prepare` | hard gathered_twist：构造连续聚褶／扭转目标，再通过物理准备形成初态。不是仅生成一个静态 OBJ 就完成此 setting |

参数：[blanket_flatten_fold_roll.yaml](../../../configs/blanket_flatten_fold_roll.yaml) → medium；[blanket_flatten_gathered_twist.yaml](../../../configs/blanket_flatten_gathered_twist.yaml) → hard。Q1 也能表达表外 fold_spiral 的卷曲参数；Q2 的准备函数还保留交叉折叠路线，这些不增加三档数量。

当前具名 variation 只有 [three_folds / five_folds](../../../topogym/tasks/task_variations/blanket_flatten.py)。[当前 Task:53](../../../topogym/tasks/blanket_flatten/common.py#L53) 构建 Layout 时只传入七项尺寸／折叠字段及 seed，没有传入 `roll_fold_count` 等卷曲字段；因此几何代码支持 fold_roll，但当前 Task 还未接好该 setting。Q2 在历史快照中，不是当前准备模块。

## 11. Rope Threading：三环基础有代码，两环／小环尚无对应 setting

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| R1 | [当前 rope_threading.py:16](../../../topogym/assets/geometry/rope_threading.py#L16)，`ThreadingLayout`；`:158 ring_mesh`；`:215 generate_assets` | medium wang_reference_v1 三环基础：读取离线 reference 后生成绳与环／支架 |

固定来源：[wang_reference_v1](../../../assets/tasks/rope_threading/wang_reference_v1)。当前 Layout 提供整体变换、绳网格细分与中心线插值等参数，未暴露两环选择或小环径的三档合同。

原表 easy 两环、hard 三环缩小余量：没有找到对应专用生成器或冻结参数包。`ring_mesh` 是可复用底层函数，不能据此把两个 setting 记成已经实现。

## 12. Slotted Post Ring：原型与 36 mm 柱槽有代码，大／中目标环尚无对应 setting

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| S1 | [当前 slotted_post_ring.py:23](../../../topogym/assets/geometry/slotted_post_ring.py#L23)，`SlottedPostLayout`；`:176 make_meshes`；`:286 generate_assets` | hard 原基础几何；参数包括柱槽宽、目标环主半径／截面半径、珠径和端盘尺寸 |

原资产：[video_reconstruction_v1](../../../assets/tasks/slotted_post_ring/video_reconstruction_v1)。历史 36 mm 候选对应 `slot_width_m=.036`；它可由柱槽参数表达，但不对应用户原表 easy 的“大目标环”。[36 mm 完整外力证据](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_clearance36_full_physics_v1/README.md)记录的是另一项尺寸变化。

原表 easy／medium 顶部解脱：未找到专用构造代码或已确定的目标环参数。S1 的几何合法性校验也不是顶部完整解脱的可解性证明。

## 13. Orbits：四环有代码，两环／三环被当前校验拒绝

| 编号 | 脚本位置／函数 | 对应位置与作用 |
|---|---|---|
| O1 | [当前 orbits.py:23](../../../topogym/assets/geometry/orbits.py#L23)，`OrbitsLayout`；`:138 cord_centerline`；`:169 make_meshes`；`:290 generate_assets` | hard 四环基础：器具、木柄和初始绳路径生成 |

关键限制：[orbits.py:81](../../../topogym/assets/geometry/orbits.py#L81) 明确要求 `ring_count == 4`。虽然有 ring_count 字段，不能直接传 2 或 3 就称为支持 easy／medium。

原型资产：[video_reconstruction_v1](../../../assets/tasks/orbits/video_reconstruction_v1)；[rope_video_solution_v2.json](../../../configs/task_variants/orbits/rope_video_solution_v2.json) 是参考动作配置，不是两／三环资产生成器。75% 器具和工作绳参数也须随选定实例一起读取，不能拿几何类默认值代替视频版全部设置。

## 使用这份清单时的边界

当前统一 [variation 解析器](../../../topogym/tasks/task_variations/__init__.py)读取各任务的 `VARIATIONS` 映射。现有几何函数、历史采样器、已生成资产包是三种不同能力；尤其 Coil、Claws 的家族几何代码已保留，但没有对应具名运行参数合同。

历史源码中的 `topogym.tasks.<task>.*`、`topogym.generation.*` 等 import 可能指向重构前结构，部分还包含旧后端依赖。因此本文提供的是**已写代码的定位与迁移依据**，没有给出未经验证的可直接执行命令。恢复使用时应将需要的纯几何能力接到当前统一资产与 Task 链路，不整份恢复历史运行框架。

上述对应关系只回答资产实现在哪里。关于必要动作、捷径风险、物理流程及难度是否成立，仍以 [变体评估文档](variant_difficulty_review_20260924_zh.md) 和逐实例验收为准。
