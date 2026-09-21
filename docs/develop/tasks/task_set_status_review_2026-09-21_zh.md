# 13 项任务完成度盘点（2026-09-21）

按当前工作区（含尚未提交的实现）、任务专属文档、实际运行报告和 MP4 归档核对。任务范围以 [catalog.py](../../../topogym/tasks/catalog.py) 的 `TASK_IDS` 为准：原十项任务，加上被子展平、长孔立柱解环、Orbits，共 **13 项**；不包含 legacy 的旧十三项任务。

结论：**13/13 已建立基础场景与任务卡；10/13 已有至少一个实例的完整机器人流程证据；7/13 已有接入共享 seed / EpisodeSpec 的任务级变体接口，其中只有 Keyhole、Horseshoe 已走通随机实例的完整物理验收入口。** 这三个数字分别衡量不同事情，不能相加或解读为全部环境已经完成物理验收。

这里的「基础场景已搭建」指资产、配置、机器人/场景入口已经存在，不等于整个物理参数域合格。「完整流程」采用项目现有实例范围，允许明确声明的预抓取和辅助抓持；成功物理状态的重渲染可以展示原执行，但不增加一次物理成功。静态展示、运动学预演、外力台架和局部动作另记。Agent 自主求解、模型服务及数据集导出不属于本次三项完成度统计。

| # | 任务 | 基础环境搭建 | 完整机器人 demo | 变体生成逻辑与剩余缺口 |
| --- | --- | --- | --- | --- |
| 1 | [双爪互锁 Interlocked Claws](interlocked_claws_authored_physics_zh.md) | **已搭建，资格分版本**。原 A0 使用 Genesis，独立接触资格仍有缺口；新 B0/C0 使用 MuJoCo，固定原型通过双步长检查 | **有**。A0 有辅助抓持全程；B0 螺旋冠和当前 C0 等尺寸双窗完成拆解、放桌、释放、静置 | **部分接通**。`claw_seed_v1` 可采样、构建/恢复 A0；B/C 仍被旧接口拒绝。已完成的新 B0/C0 尚未接入新版 seed 生成器，三族随机闭环未完成 |
| 2 | [绳穿三环 Rope Threading](rope_threading_zh.md) | **已搭建，物理验收推进中**。三环、ALOHA、FEM/IPC、参考动作与反馈抓持已接入；时间步/静置资格仍有缺口 | **未完成**。9 月 21 日运行到 66.115 s，已出现第一、第二环穿越；第二环出口接绳因反馈目标 IK 不可达停止。新换手候选只完成离线规划 | **未形成任务级生成器**。有参数化布局与资产构造，没有 seed → 实例 → 完整穿环验证链路 |
| 3 | [开锁 Lock Picking](lock_picking_seed_generator_zh.md) | **基础实例已跑通**。150 mm 盘距、三齿、两次必要回退的完整物理执行成功 | **有流程证据**。159.35 s 三视角来自成功物理状态重渲染；被动夹爪关节按开合量重建，不能计为一次新的完整物理执行 | **几何/IK 级已接通**。1/2/3 回退家族、固定 S/M/L、seed、确定性重试及保存/重载；256 个 seed 通过几何/IK。新实例的机器人场景碰撞、接触动力学及完整流程资格仍未运行 |
| 4 | [刺球出笼 Hedgehog in Cage](hedgehog_in_cage_zh.md) | **基础实例已跑通**。CLASSIC 及当前三个原型有对应场景与执行证据 | **有**。CLASSIC 以及单斜窗、固定六刺侧孔、GEN 顶部钥匙孔均有完整辅助抓持流程 | **几何/IK 级已接通**。v2 使用当前三原型，支持尺寸、位置、朝向、木质外观和保存/重载；随机后代仍为 `physical_execution=not_run`。侧孔与 CLASSIC 可共享策略，不把“三族 IK 必须本质不同”列为缺口 |
| 5 | [光纤收束 Fiber Bundling](fiber_bundling_variant_pipeline_zh.md) | **基础实例已跑通**。固定终端、被动细线、闭环、机器人只抓粗护套的操作链路存在 | **有**。当前正式交付为 8 芯、R=13.5 mm 基础版，177 s 三视角；旧密度代表的物理记录仍保留 | **实例/几何级已接通**。稀疏/标准/密集，线数 4–16、R=12.8–15.0 mm，具名 seed、资产、保存/重载。300 个 seed 初态几何通过；随机实例仍需 IK、禁碰、受载稳定性、完整穿环及时间步对照。按已确认要求，密度家族无需不同 IK 机制 |
| 6 | [马蹄环 Horseshoe Ring](horseshoe_ring_variant_generator_zh.md) | **基础实例已跑通**。重力、自由链环、双臂交接、取环、释放落桌均有验证 | **有**。基础版 113.7 s 五视角，独立完整执行与半时间步复验通过；新家族的 9.8 s 对照仅是局部视频 | **受限物理闭环已接通**。三个接近路线家族，围绕各自成功中心小范围采样；生成、重载、完整物理验收、拒绝重试均已实现。三族各有最终条件域随机实例通过，但新实例仅验收 2 ms，未做 1 ms 复验；非圆环等形状池未开放 |
| 7 | [解绳结 Knot Untying](knot_untying_zh.md) | **已搭建，完整物理资格未齐**。FEM/IPC、三种固定结型、抓持和换手控制存在；P3 网格收敛及通用双手交接仍未通过 | **有基础版，带验收缺口**。Trefoil v9 连续解结、释放、静置共 75 s，五视角。八字结、双重单结仍是未完成的局部尝试 | **局部参数化已实现**。三种固定模板，`appearance_seed` 可采样形状尺度、yaw、颜色；尺度和 yaw 会改变物理实例。未形成全部结型均能执行成功的统一 seed/验收闭环，目标难度档位尚未标定 |
| 8 | [Cast Coil](cast_coil_seed_generator_zh.md) | **基础原型已跑通**。双臂、实体碰撞、装配及释放静置已验证；不等同于官方八步解法复刻完成 | **有**。当前基础装配版 33.15 s 五视角，历史拆解和固定变体证据保留 | **几何/IK 级已接通**。三种固定机构、族内尺寸/位置/yaw、seed、实例重载与拒绝；48 个几何样本、12 个随机双臂规划通过。新代表 6 次物理试验仅 4 次通过严格归档门槛，不能标记三族随机物理资格完成 |
| 9 | [Cast Keyhole](cast_keyhole_variants_zh.md) | **当前重建实例已跑通**。原型几何、双臂、接触及实际解锁有证据；不扩大为官方全部路线复现 | **有**。基础实例 23.917 s，多路同步物理状态视频；预抓取、接触后辅助抓持，分离后仍由双臂持稳，不包含末端释放 | **受限物理闭环已接通**。v2 三机构 × 三外形，固定/参数模式、逐实例 seed、姿态重定向、几何/机器人检查、双步长执行与审计；三个随机实例共六次物理运行通过。每个新实例仍须独立验收，`export_ready=false` |
| 10 | [立体电流棒 Buzz Wire 3D](buzz_wire_3d_family_space_zh.md) | **已验证的固定实例已跑通**。基础版、旧尺寸 F3、新 70% 玩具版 F2 分别有证据 | **有**。最新 F2 玩具版 103.04 s 三视角，4/2 ms 真实摩擦抓持执行通过；预穿环/预抓取开始，包含末端松手、撤臂与静置 | **固定原型已有，随机生成未完成**。F2/F3 已有工程实例；F1 双拱仍是提案，基础布局不能替代 F1。原型内参数构造已有部分实现，通用 seed 采样、重载及逐例验收未连成闭环；新尺寸 F3 也不能继承旧版资格 |
| 11 | [被子展平 Blanket Flatten](blanket_flatten_zh.md) | **简单初态已跑通**。PBD 单层布面近似、绑定审计、落桌/静置、抓角与释放后验收已建立 | **有简单版**。32.55 s 三视角。用户选定的复杂麻花初态稳定性通过，但完整展平仍失败；不能把基础版视为复杂版已完成 | **初态 seed 生成已实现**。折线/折角随机化、拒绝重试及多种固定折叠/卷转配置；尚无统一实例包与随机初态逐例完整展平验收闭环 |
| 12 | [长孔立柱解环 Slotted Post Ring](slotted_post_ring_zh.md) | **已搭建，基础动力学已有验证**。柔绳、自由滑珠、保孔碰撞、端部连接和双步长重力落稳通过 | **机器人未完成；外力版完整**。36 mm 孔候选完成 147 s 连续外力解环；ALOHA 完成过珠、端片穿槽及交接等局部动作。完整外力流程也尚无半步长复验 | **未形成任务级生成器**。原型、36 mm 孔径候选等为人工配置版本，尚无 seed 抽样与可解实例筛选链路 |
| 13 | [Orbits 四环阶梯解绳](orbits_zh.md) | **已搭建，局部动力学推进中**。当前器具为四环五杆；静态场景之外已有 MuJoCo 柔绳、ALOHA、接触触发辅助抓持 | **未完成**。v14 完成修正自然绳圈后的双臂撑圈、越过顶球和下放，17.55 s 四视角；后续穿环、换抓和最终解脱未完成 | **未形成任务级生成器**。已有尺度/布局版本、动作 recipe 与同模型检查点恢复；这些不等于随机任务生成 |

变体逻辑按能力可以归成四组，避免仅凭 `variants.py` 文件是否存在来判断完成：

| 层级 | 任务 | 当前可承诺范围 |
| --- | --- | --- |
| 生成、保存/恢复、逐实例完整物理验收已连通：2 项 | Keyhole、Horseshoe | 受限家族与参数域；有限样本通过，Horseshoe 新随机实例尚缺半步长复验。均非全域成功保证 |
| 共享 seed/实例接口存在，物理闭环未齐：5 项 | Lock Picking、Hedgehog、Coil、Fiber、Claws | 前三项主要到几何/IK，Fiber 主要到初态几何；Claws 的新版 B/C 原型尚未接入。七项共享接口不是七项可直接发布的物理数据生成器 |
| 任务内局部采样或固定变体：3 项 | Knot、Blanket、Buzz Wire | Knot 有固定结型及局部 seed 参数，Blanket 有随机初态，Buzz Wire 有固定线路原型；三者尚无统一合格实例生成链路 |
| 尚无任务级 seed 生成器：3 项 | Rope Threading、Slotted Post Ring、Orbits | 参数化建模/配置已存在，优先补齐完整机器人执行，再冻结可用变体范围 |

建议按可验收交付安排接下来的工作：

1. **补三项完整机器人流程**：Rope Threading 先接入并验证第二环实际绳端反馈换手；Slotted Post Ring 把已有外力解法转成连续双臂执行；Orbits 继续完成越顶球之后的穿环、换抓和解脱。
2. **收口已有 demo 的关键缺口**：Knot 的网格收敛/换手资格和两个新结型；Blanket 的选定复杂麻花初态；Claws 原 A0 接触资格。Keyhole 的末端释放若作为新要求，应单独立项，当前实例定义止于分离持稳。
3. **补变体物理验收**：Lock/Hedgehog/Coil/Fiber 将现有冻结实例直接交给执行与验收，保留拒绝原因；Claws 发布包含新 B/C 的生成器版本；Horseshoe 补新随机实例的半步长复验。
4. **再扩大变体覆盖**：Buzz Wire 补 F1 与新尺寸 F3；Knot/Blanket 先冻结可成功的家族或初态范围，再统一 seed、完整配置、资产哈希、恢复接口和资格记录。

以下是本次核对的十组完整流程视频。每格是独立 MP4；其中 Claws 选当前等尺寸 C0，Hedgehog 选 CLASSIC 基础版，Buzz Wire 选最新 F2。版本及适用范围见上表，未把局部对照计为完整 demo。

| 任务 / 版本 | 完整流程 MP4（分视角） | 同组时长 / 帧数 |
| --- | --- | --- |
| Claws C0 等尺寸双窗 | [高位](../../../demos/interlocked_claws/cam_high/2026-09-19_orthogonal_gate_balanced_physical_v1_cam_high.mp4) · [低位](../../../demos/interlocked_claws/cam_low/2026-09-19_orthogonal_gate_balanced_physical_v1_cam_low.mp4) · [左腕](../../../demos/interlocked_claws/cam_left_wrist/2026-09-19_orthogonal_gate_balanced_physical_v1_cam_left_wrist.mp4) · [右腕](../../../demos/interlocked_claws/cam_right_wrist/2026-09-19_orthogonal_gate_balanced_physical_v1_cam_right_wrist.mp4) · [近景 v1](../../../demos/interlocked_claws/detail/2026-09-19_orthogonal_gate_balanced_physical_v1_detail.mp4) | 62.05 s / 1241 |
| Lock Picking 标准外观重渲染 | [全景](../../../demos/lock_picking/agentview/2026-09-18_standard_150mm_purple_trace_v1_agentview.mp4) · [斜前](../../../demos/lock_picking/front_oblique/2026-09-18_standard_150mm_purple_trace_v1_front_oblique.mp4) · [腕部](../../../demos/lock_picking/wrist/2026-09-18_standard_150mm_purple_trace_v1_wrist.mp4) | 159.35 s / 3187 |
| Hedgehog CLASSIC wood | [全景](../../../demos/hedgehog_in_cage/agentview/2026-09-16_classic_wood_extraction_agentview.mp4) · [斜前](../../../demos/hedgehog_in_cage/front_oblique/2026-09-16_classic_wood_extraction_front_oblique.mp4) · [腕部](../../../demos/hedgehog_in_cage/wrist/2026-09-16_classic_wood_extraction_wrist.mp4) | 82.2 s / 1644 |
| Fiber 标准 8 芯 | [全景](../../../demos/fiber_bundling/agentview/2026-09-18_standard_08_r13p5mm_clean_v1_agentview.mp4) · [斜前](../../../demos/fiber_bundling/front_oblique/2026-09-18_standard_08_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/wrist/2026-09-18_standard_08_r13p5mm_clean_v1_wrist.mp4) | 177 s / 3540 |
| Horseshoe 重力修正基础版 | [高位](../../../demos/horseshoe_ring/cam_high/2026-09-18_gravity_replanned_v1_cam_high.mp4) · [低位](../../../demos/horseshoe_ring/cam_low/2026-09-18_gravity_replanned_v1_cam_low.mp4) · [左腕](../../../demos/horseshoe_ring/cam_left_wrist/2026-09-18_gravity_replanned_v1_cam_left_wrist.mp4) · [右腕](../../../demos/horseshoe_ring/cam_right_wrist/2026-09-18_gravity_replanned_v1_cam_right_wrist.mp4) · [近景](../../../demos/horseshoe_ring/detail/2026-09-18_gravity_replanned_v1_detail.mp4) | 113.7 s / 1137 |
| Knot Trefoil v9 | [高位](../../../demos/knot_untying/cam_high/2026-09-17_bounded_spread_trefoil_v9_cam_high.mp4) · [低位](../../../demos/knot_untying/cam_low/2026-09-17_bounded_spread_trefoil_v9_cam_low.mp4) · [左腕](../../../demos/knot_untying/cam_left_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_left_wrist.mp4) · [右腕](../../../demos/knot_untying/cam_right_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_right_wrist.mp4) · [近景](../../../demos/knot_untying/detail/2026-09-17_bounded_spread_trefoil_v9_detail.mp4) | 75 s / 1500 |
| Coil 基础装配版 | [高位](../../../demos/cast_coil/cam_high/2026-09-17_aloha_full_cam_high.mp4) · [低位](../../../demos/cast_coil/cam_low/2026-09-17_aloha_full_cam_low.mp4) · [左腕](../../../demos/cast_coil/cam_left_wrist/2026-09-17_aloha_full_cam_left_wrist.mp4) · [右腕](../../../demos/cast_coil/cam_right_wrist/2026-09-17_aloha_full_cam_right_wrist.mp4) · [斜前](../../../demos/cast_coil/front_oblique/2026-09-17_aloha_full_front_oblique.mp4) | 33.15 s / 663 |
| Keyhole 当前基础物理实例 | [高位](../../../demos/cast_keyhole/cam_high/2026-09-17_current_instance_physical_cam_high.mp4) · [低位](../../../demos/cast_keyhole/cam_low/2026-09-17_current_instance_physical_cam_low.mp4) · [左腕](../../../demos/cast_keyhole/cam_left_wrist/2026-09-17_current_instance_physical_cam_left_wrist.mp4) · [右腕](../../../demos/cast_keyhole/cam_right_wrist/2026-09-17_current_instance_physical_cam_right_wrist.mp4) · [近景](../../../demos/cast_keyhole/detail/2026-09-17_current_instance_physical_detail.mp4) | 23.917 s / 287 |
| Buzz Wire F2 70% 玩具版 | [全景](../../../demos/buzz_wire_3d/agentview/2026-09-20_F2_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/wrist/2026-09-20_F2_compact_toy_s70_v2_full_wrist.mp4) | 103.04 s / 2576 |
| Blanket 简单初态 | [全景](../../../demos/blanket_flatten/agentview/2026-09-18_single_arm_clear_home_v1_agentview.mp4) · [斜前](../../../demos/blanket_flatten/front_oblique/2026-09-18_single_arm_clear_home_v1_front_oblique.mp4) · [腕部](../../../demos/blanket_flatten/wrist/2026-09-18_single_arm_clear_home_v1_wrist.mp4) | 32.55 s / 651 |

本次验证：现有 `tests.check_task_baseline_catalog` 的 4 项测试通过；上表 40 个 MP4 全部通过 `ffprobe` 读取及 `ffmpeg -xerror` 完整解码，各组帧数/时长一致。物理及生成器结论来自已有实例报告与当前实现核对，**本次没有重新执行 13 项物理仿真或全套生成器测试**。

关键可机器核对的证据包括 [Keyhole 三实例六次物理验收](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/validation_summary.json)、[Horseshoe 条件域实例验收](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/pipeline_validation_report.json)、[Coil 新代表物理门槛结果](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/physics_summary.json)、[Claws C0 主步长执行](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/execution/report.json)、[Claws C0 半步长执行](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/refinement/report.json)、[开锁原执行结果副本](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/result.json)、[开锁重渲染范围](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/report.json)和 [Trefoil v9 物理资格边界](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json)。

已有总览存在时效差异：[任务源码 README](../../../topogym/tasks/README.md) 中 Fiber、Knot、Keyhole 等“完整 demo 待实现”的描述，以及 Orbits“未实现绳动力学”的描述已落后于专属记录；9 月 17 日的 [seed 审查](seed_variant_generation_audit_zh.md)也不覆盖 9 月 19 日以后新增的生成器。总 `catalog.json` 的完整 demo 布尔值还区分“本次是否新增物理执行”，例如开锁重渲染为 false，不能直接按这个字段统计有多少任务曾完成机器人流程。本表保留这些证据边界，不改写历史结论。
