# 当前运行入口

自 2026-09-19 起，开发进展直接交付相关 MP4 视频链接，不再创建、更新或部署 HTML 展示页。
完整流程 demo 在本目录对应的 `<task_id>/`（已有多视角任务沿用 `<task_id>/<camera>/`）中迭代，视频目录内的文件只能是 `.mp4`。
报告、配置、清单等配套材料放在 `runs/demo_metadata/`；本文件下方的 HTML 链接仅为历史记录，不作为后续交付入口。
具体约定见 [项目规则](../AGENTS.md)。

Horseshoe Ring 重力修正基础版位于 [`horseshoe_ring/`](horseshoe_ring/)，按
`cam_high/`、`cam_low/`、`cam_left_wrist/`、`cam_right_wrist/`、`detail/` 各保存一份完整 MP4。
每路 **113.7 秒、1137 帧、10 fps**，来自同一次连续物理执行，无文字或画中画。
包含翻转、折合、交接、抓环、取出及松爪自由落桌；从预抓持开始，含接触确认后的辅助抓持。
[五路同步播放与物理验收](../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1/index.html)。
后续[同代码 2 ms / 1 ms 完整复验](../runs/demo_metadata/horseshoe_ring/2026-09-18_timestep_validation_v1/index.html)也已通过，
两次分别独立重规划并完成取环与自由落桌；视频仍对应上面同一次 113.7 秒完整录制。

2026-09-19 的 Horseshoe v2 新增三个已成功物理实例的接近阶段对照：
[高位](horseshoe_ring/cam_high/2026-09-19_families_v2_approach_comparison_cam_high.mp4)、
[低位](horseshoe_ring/cam_low/2026-09-19_families_v2_approach_comparison_cam_low.mp4)。
每段 9.8 秒，从左到右是高位接近、外侧接近、后撤再接近；这些是局部对照，不计作三份新完整 demo。
[随机实例生成契约及验收](../docs/develop/tasks/horseshoe_ring_variant_generator_zh.md) 独立于录像与数据 writer，未生成 H5。

Buzz Wire 3D 历史基型单臂视频位于 [`buzz_wire_3d/`](buzz_wire_3d/)，按 `agentview/`、`front_oblique/`、`wrist/` 保存独立 MP4；每路 **91.84 秒、2296 帧、25 fps**。Panda 从预抓取起点以摩擦夹持圆环，走完迷宫并在末端松手、退开和静置。[同步播放与物理证据](../runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/index.html)位于 `runs/demo_metadata/`，减半时间步复验通过。旧无机器人台架的 `overview / front_oblique / topdown` 视频及 `runs/demos/buzz_wire_3d/` 副本保留。

2026-09-20 Buzz Wire 新增 70% 尺寸的木质 / 金属场景预览：[基础布局](buzz_wire_3d/front_oblique/2026-09-20_baseline_compact_wood_s70_v1_scene_preview_front_oblique.mp4)、[F2 错层八字](buzz_wire_3d/front_oblique/2026-09-20_F2_compact_wood_s70_v1_scene_preview_front_oblique.mp4)、[F3 换平面](buzz_wire_3d/front_oblique/2026-09-20_F3_compact_wood_s70_v1_scene_preview_front_oblique.mp4)。每个实例有全景、斜前、俯视三路同步视频，各 8 秒 / 120 帧 / 15 fps。**静态场景与材质展示，机械臂停放作尺度参照，不计作完整动作 demo**；新版工具几何通过，机器人连续 IK / 物理执行未验收。[全部视角及验证报告](../runs/demo_metadata/buzz_wire_3d/2026-09-20_compact_wood_s70_scene_preview/README.md)。历史完整执行副本保留。

同日按实物照片再改为 **toy-v2**：削角、分层收边木底座，小方木线脚，铜色轨道、银环木柄，无电子摆设。新版静态预览：[基础](buzz_wire_3d/front_oblique/2026-09-20_baseline_compact_toy_s70_v2_scene_preview_front_oblique.mp4) · [F2](buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_scene_preview_front_oblique.mp4) · [F3](buzz_wire_3d/front_oblique/2026-09-20_F3_compact_toy_s70_v2_scene_preview_front_oblique.mp4)。[全部三视角及验证](../runs/demo_metadata/buzz_wire_3d/2026-09-20_photo_toy_s70_v2_scene_preview/README.md)；各路仍为 8 秒 / 120 帧，不计作完整机器人 demo。

2026-09-20 **F2 紧凑玩具版完整单臂 demo** 已通过 4 ms / 2 ms 独立物理执行验收，场景尺寸、摆位与抓持点保持原预览配置。三连回折 → 错层八字 → 竖直 W → 末端松手、撤臂、静置；从预穿环 / 预抓取开始，真实摩擦抓持，受控通行零触线。三路为同一次主运行实测状态重渲染，各 **103.04 秒、2576 帧、25 fps**。

[全景](buzz_wire_3d/agentview/2026-09-20_F2_compact_toy_s70_v2_full_agentview.mp4) · [斜前](buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](buzz_wire_3d/wrist/2026-09-20_F2_compact_toy_s70_v2_full_wrist.mp4) · [物理验收与归档](../runs/demo_metadata/buzz_wire_3d/2026-09-20_F2_compact_toy_s70_v2_full/README.md)。仅覆盖此 F2 实例及策略。

被子展平完整视频位于 [`blanket_flatten/`](blanket_flatten/)，按 `agentview/`、`front_oblique/`、`wrist/` 各保存一份独立 MP4；每路 **32.55 秒、651 帧、20 fps**，包含悬空出生、自然落桌、机器人辅助抓角展开、释放、撤手与静置。[三视角同步播放与物理证据](../runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/index.html)仍保存在 `runs/demo_metadata/`；原 `runs/demos/blanket_flatten/` 副本保留备份。

开锁新外观标准变体位于 [`lock_picking/`](lock_picking/)，按 `agentview/`、`front_oblique/`、`wrist/` 各保存一份完整 MP4；每路 159.35 秒、20 fps，无文字或画中画。标准结构为 150 mm 盘距、三齿、两次必要回退，使用紫色第一锁片与四个锁孔的黄色描边。[三路同步播放与来源记录](../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/index.html)。视频由成功物理执行的实测状态重渲染，夹爪被动连杆按记录开合量重建，未重跑动力学。

开锁 seed 生成器新增同一斜视相机的三类 M 代表：[F1 一次回退](lock_picking/front_oblique/2026-09-19_F1_M_kinematic_front_oblique.mp4)、[F2 两次回退](lock_picking/front_oblique/2026-09-19_F2_M_kinematic_front_oblique.mp4)、[F3 三次回退](lock_picking/front_oblique/2026-09-19_F3_M_kinematic_front_oblique.mp4)。分别为 11.96 / 17.58 / 21.75 秒、24 fps；均为已对齐起点到插入终点的 **IK 运动学预演**，没有动力学步进，不含抓起／松手，不替代上面的完整基线视频。[生成接口与验证范围](../docs/develop/tasks/lock_picking_seed_generator_zh.md)。

解绳结完整视频位于 [`knot_untying/`](knot_untying/)，按 `cam_high/`、`cam_low/`、`cam_left_wrist/`、`cam_right_wrist/`、`detail/` 分视角保存，每路均为同一次执行的完整 75 秒录像。[同步播放页与物理证据](../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)保留在 `runs/demo_metadata/`。

光纤收束当前只保留基础版无 UI 三视角，位于 [`fiber_bundling/`](fiber_bundling/)，按 `agentview/`、`front_oblique/`、`wrist/` 分目录各一份；每路完整 177 秒，无文字、状态栏或画中画。文件名前缀为 `2026-09-18_standard_08_r13p5mm_clean_v1`；[当前视频与历史物理证据](../runs/demo_metadata/fiber_bundling/README.md)。旧 52 份视频已按用户要求删除。

Claw 默认版完整录像已按视角整理到 [`demos/interlocked_claws/`](interlocked_claws/)：
`cam_high/`、`cam_low/`、`cam_left_wrist/`、`cam_right_wrist/`、`detail/` 各有一份 158.6 秒 MP4。
这是按 2026-09-18 用户要求增加的视频目录；原 `runs/demos/interlocked_claws/` 保留独立备份。
[五路同步播放与物理证据](../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/index.html)仍在 `runs/demo_metadata/`。

在仓库根目录用 `.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.<入口>` 执行。

| 入口 | 范围 |
| --- | --- |
| `presentation_preview` | 默认 Nyx 封闭实验室、腕部跟随、视频与 HDF5 RGB 检查 |
| `orbits` | 第 13 项 Orbits 四环阶梯解绳；默认原始尺寸的 75%、旋转 90°，以木底座中心对齐双臂基座中点，22 个接近姿态及四组双臂姿态重新通过 IK / 碰撞检查。ALOHA / Nyx 零物理步初态预览，见[场景与复现](../docs/develop/tasks/orbits_zh.md) |
| `slotted_post_ring` | 第 12 项长孔立柱解环；历史一维绳模型的 28 mm 原版与 36 mm 候选版通过重力及半步长验证。36 mm 候选版 [147 秒完整外力驱动解环](slotted_post_ring/front_oblique/2026-09-21_clearance36_full_physics_v1_front_oblique.mp4)通过逐步物理检查，三视角已归档；另有 ALOHA 过珠、端片穿槽及交接局部录像，使用预抓取及辅助连接，完整机器人解环仍未通过。新增 [FEM 动态试跑](../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_fem_gravity_attempt_v2_front_oblique.mp4)，余振检查未通过。[场景、其他视角与复现](../docs/develop/tasks/slotted_post_ring_zh.md) |
| `blanket_flatten` | 此入口录制悬空出生、自然落桌与静置；已验证的单臂展平完整流程另用 `topogym.tasks.blanket_flatten.robot_demo`，三视角录制及证据见[任务说明](../docs/develop/tasks/blanket_flatten_zh.md)。 |
| `aloha_lab` | ALOHA 2 双臂相机预设：四路观测、官方模型展示位及实验室展示；可选短时位置保持检查 |
| `rope_threading` | Wang 三环参考初态：U 形自由绳、三环侧置支架、ALOHA 双臂、七路初态图与短时 FEM 静置；[说明](../docs/develop/tasks/rope_threading_zh.md) |
| `interlocked_claws` | 原始 Claw 网格、参考互锁初态、ALOHA 双臂姿态与支架；装配／拆件静态检查及相机绕行，未执行物理脱困 |
| `lock_picking` | 当前开锁物理执行，默认基线配置 |
| `lock_picking_inspect` | 加宽锁片间距的初态 review；不代表长行程执行通过 |
| `hedgehog_in_cage` | CLASSIC 三星刺猬初态场景 |
| `fiber_bundling` | 粗绳分叉细绳与窄环的基础场景、静置检查及 Nyx 预览 |
| `knot_untying` | 一个松 trefoil / overhand 单结的 FEM 初态、短时静置与 Nyx 预览；依赖 `requirements/uv-topogym-fem-ipc.txt` |
| `chain_links` | 三只闭合刚体链环的局部接触试验 |
| `horseshoe_ring` | v3 基础实例已连续完成重力下双臂交接、取环和自由落桌；含预抓持与接触确认后的辅助抓持。[新 IK 与验收范围](../docs/develop/tasks/horseshoe_ring_physical_ik_zh.md)，旧几何变体需分别重验 |
| `cast_coil` | 金银方形卷绕件装配、拆件静态检查、绕行视频与自由落桌检查；原型三段解已验证，双臂执行使用下述独立入口 |
| `cast_keyhole` | 金叉与银色阶梯孔基础场景、拆件轮廓检查、相机绕行及短时自由静置；本地完整解法待验证 |
| `buzz_wire` | 环杆双向接触夹具试验 |
| `buzz_wire_3d` | 紧凑低矮单臂场景，真实摩擦抓持、完整迷宫通行、释放 / 静置与减半时间步复验；同步三视角各 91.84 秒。旧照片尺寸台架保留。[说明](../docs/develop/tasks/buzz_wire_3d_zh.md) |
| `lock_aperture` | 钥匙和孔槽轮廓的几何初态检查 |

Hydra 入口可用 `--cfg job` 查看解析配置；argparse 入口用 `--help` 查看选项。
Cast Coil 双臂执行使用 `python -m topogym.tasks.cast_coil.robot_demo --plan <计划.json> --output <新目录> --record`；
计划生成、半时间步复核和正式归档命令见 [Cast Coil 文档](../docs/develop/tasks/cast_coil_zh.md#完整双臂物理执行与录制)。
该流程从预抓取状态开始，接触后采用辅助抓持，最终解除并自由静置。
历史结果汇总保留在 `runs/environment_bootstrap/index.html`；后续进展直接提供相关 MP4 链接。
新完整机器人多视角演示在本目录对应的任务视频子目录中迭代，已有 [`runs/demos/`](../runs/demos/) 副本继续保留；配套材料放在 [`runs/demo_metadata/`](../runs/demo_metadata/)。新 demo 交付前按 [项目规则](../AGENTS.md) 完成复制与检查，不再要求更新 HTML 播放页。
刺球出笼 CLASSIC wood 基础版按用户要求收录在本目录的 [`hedgehog_in_cage/`](hedgehog_in_cage/)，下分 `agentview/`、`front_oblique/`、`wrist/` 三个视角文件夹。
2026-09-19 刺球出笼默认家族改为单斜窗、固定六刺侧孔、GEN 风格顶部钥匙孔；新代表沿用上述三视角目录，旧双门／螺旋录像保留。[当前代表视频及生成器说明](../docs/develop/tasks/hedgehog_in_cage_zh.md)。
Cast Coil 基础装配版收录在本目录的 [`cast_coil/`](cast_coil/)，下分 `cam_high/`、`cam_low/`、`cam_left_wrist/`、`cam_right_wrist/`、`front_oblique/` 五个视角文件夹；每路为同一次执行的完整 33.15 秒录像。[同步播放页与执行证据](../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/index.html)保留在原配套目录。
旧任务入口移到 [`legacy/demos/`](../legacy/demos/)，只读保存。

2026-09-19 Buzz Wire 默认 F2 / F3 工程候选新增主动触碰物理检查录像，每路 7.04 秒、176 帧、25 fps。**无机械臂，有限外力驱动，不是完整单臂通关 demo**；[首轮验收报告](../runs/environment-solvability/buzz_wire_3d/family_physics_20260919/result.md)分别记录工具台架与机器人检查结果。

| 候选 | 全景 MP4 | 斜前 MP4 | 俯视 MP4 |
| --- | --- | --- | --- |
| F2 错层八字多关 | [全景](buzz_wire_3d/overview/2026-09-19_F2_rounded18mm_contact_diagnostic_overview.mp4) | [斜前](buzz_wire_3d/front_oblique/2026-09-19_F2_rounded18mm_contact_diagnostic_front_oblique.mp4) | [俯视](buzz_wire_3d/topdown/2026-09-19_F2_rounded18mm_contact_diagnostic_topdown.mp4) |
| F3 换平面多关 | [全景](buzz_wire_3d/overview/2026-09-19_F3_rounded18mm_contact_diagnostic_overview.mp4) | [斜前](buzz_wire_3d/front_oblique/2026-09-19_F3_rounded18mm_contact_diagnostic_front_oblique.mp4) | [俯视](buzz_wire_3d/topdown/2026-09-19_F3_rounded18mm_contact_diagnostic_topdown.mp4) |

2026-09-19 新增 Buzz Wire F3 四关单臂完整动作 v3：梳齿 → W → 侧向 Ω → 倾斜螺旋；三路各 106.96 秒、2674 帧、25 fps。预穿环 / 预抓取、实际摩擦夹持、末端释放与静置；4 / 2 ms 独立执行均通过，视频为同一主运行的实测状态重渲染。

- [全景](buzz_wire_3d/agentview/2026-09-19_F3_comb_w_omega_coil_v3_agentview.mp4) · [斜前](buzz_wire_3d/front_oblique/2026-09-19_F3_comb_w_omega_coil_v3_front_oblique.mp4) · [腕部](buzz_wire_3d/wrist/2026-09-19_F3_comb_w_omega_coil_v3_wrist.mp4)
- [物理证据与归档检查](../runs/demo_metadata/buzz_wire_3d/2026-09-19_F3_comb_w_omega_coil_v3/README.md) · [固定工程实例配置](../configs/task_variants/buzz_wire_3d/plane_switch_clearance_v3.yaml)。本结论仅覆盖此实例及控制策略。
