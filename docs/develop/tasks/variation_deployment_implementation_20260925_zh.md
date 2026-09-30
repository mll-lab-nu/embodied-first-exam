# 三档场景描述与变体部署记录

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**2026-09-29 Blanket 场景范围更新：** 三个难度类已改为共用聚褶构造，构形目标角 0° / 135° / 270°，`gathered_scene_v1`。采用平坦出生与物理构形的冻结状态，按用户要求显式暂缓粒子静稳资格，保留材料／绑定／落桌检查；实际释放后形态会松弛。旧五折、折卷分别保留为 `simple_folds` / `five_folds` 和 `fold_roll` 实验入口。具体初态、seed 范围、调用和验证见 [Blanket 当前说明](blanket_flatten_zh.md) 与 [本轮证据](../../../runs/test_results/blanket_three_tiers_20260929_01/README.md)。下文 32/39 及旧 Blanket 家族是 9 月 25 日核对快照，不是本轮最新统计。

**2026-09-29 Rope 场景补齐：**Easy 已接入 R1/R2、138 mm 净孔；Medium 保留原三环、138 mm 净孔；Hard 已接入同位置三环、100 mm 净孔，支架同步内移。绳初态和材料共用，三档资产重复构建通过。见 [Rope 当前说明](rope_threading_zh.md)及[三档预览与报告](../../../runs/test_results/rope_threading_scenes_20260929/preview.md)。以下全局数量与缺口清点保留其标注日期的历史口径，Rope 的占位描述由本条和更新后的场景行覆盖；场景接入不代表解法或难度已验收。

首次部署：2026-09-25；场景描述核对：2026-09-26。当前 39 档的具体场景见下方“三档场景描述”表。Lock medium 经候选画面核对已恢复 150 mm 盘距；其余历史参数差异仍单列记录。

按用户授权，将任务直接组织为 `topogym/tasks/<task_name>/`；没有新增平行 simulator 或运行循环。

后续核对：[各任务／档位的 planner、oracle 与历史完整执行清单](../../../legacy/cleanup_20260929/docs/develop/tasks/planner_oracle_inventory_20260925_zh.md)。资产部署不等于完整机器人规划已接入。

后续设计计划：[三难度 setting 补齐工程计划](three_tier_setting_completion_plan_20260925_zh.md)。拟验证 Orbits 两／三／四环的难度关系，并将 Blanket 改成共用聚褶构造、扭转程度递增的三档；目前仅形成计划，下面的当前代码统计与已部署家族尚未因此改变。

**当前源码清点补充（2026-09-25）：**逐项核对注册表和 39 个三档类，现为 **32 个已有具体任务构造、6 个待设计占位、1 个初态准备流程阻塞**。本次只检查源码、所引用资源和既有证据，没有重新运行物理。下面的三档表已补齐逐文件链接；“历史候选”与 `demos/` 的关系、判据缺口见后文。

**表外入口归档更新（同日）：**首批 15 个入口归档后，用户进一步确认 Horseshoe 采用 waist_mild / u_mild / waist_ellipse 三档；该任务 22 个旧入口也已移入 [tasks/legacy](../../../legacy/cleanup_20260929/topogym/tasks/legacy/README.md)，累计 37 个。9 个三档齐备任务均仅保留 common、三个难度模块及 __init__。Horseshoe 新三档接入，base 改指 easy，原照片比例 reference 退役；其他 36 个难度文件及所有 common 未改。前一批[47 项检查](../../../runs/test_results/variation_legacy_cleanup_20260925_01/README.md)与本轮[Horseshoe 验收](../../../runs/test_results/horseshoe_tiers_20260925_01/README.md)各自绑定源码快照。

## 已部署结构与调用

13 个任务均有 `common.py` 和 `<task>_easy.py`、`<task>_medium.py`、`<task>_hard.py`。具体设置继承同任务公共实现；39 个难度文件全部存在，缺少构造的文件提供明确不可实例化的占位类。

```python
import topogym

env = topogym.make("cast_coil", variation_id="cast_coil_medium")
initial, info = env.reset(seed=2)
operator = env.interaction()
# 控制仍通过统一 interaction/Env，录像仍通过 topogym.recording。
env.close()

# "medium" 是同一设置的短别名。
# details 同时包含可选择设置、占位原因和当前默认 base 的规范名字。
catalog = topogym.env_list(details=True)
```

注册与解析由 [registry.py](../../../topogym/config/registry.py) 统一负责，[variation_records.py](../../../topogym/config/variation_records.py) 保存轻量目录，具体参数只在对应 Task 脚本声明。目录查询不加载所有几何生成器。旧 `task_variations` 只保留兼容转发；Coil 的纯几何参数／外形工具已移到 [cast_coil_variants.py](../../../topogym/assets/geometry/cast_coil_variants.py)。

`instance_id` 包括家族、修订、有效参数、seed 和所选冻结资源哈希；别名不制造不同实例。episode 元数据记录请求 ID、规范 ID、目标难度、家族和修订。参数深合并，所选设置明确冻结的尺寸字段不能通过覆盖悄悄改成另一档。所有难度仍是设计目标，未进行模型难度校准。

## 三档场景描述（2026-09-26 源码核对）

这一节描述**当前难度入口实际选择的场景**。核对来源为 [注册表](../../../topogym/config/variation_records.py)、各任务的三个难度类、`common.py` 和它们引用的几何资源；下节保留逐档源码链接与默认 `base` 对照。共 39 档：**32 已接入、6 规划占位、1 准备阻塞**。“已接入”只表示具体场景构造已接线，不等于机器人成功、terminal 资格或难度排序已验收。

所有场景沿用公共实验桌和机器人配置。下表中的旋转、回退、换轴是结构／参考解法的描述，不是要求 agent 必须执行某个脚本；没有把参考动作数当成所有解法的最少动作数。

| 任务与共有场景 | Easy：场景与区别 | Medium：场景与区别 | Hard：场景与区别 |
|---|---|---|---|
| **Cast Keyhole／钥匙孔互锁件**：金、银两件带孔槽的刚体相互嵌合，目标取出银色件 | **已接入 · F1 `long_stroke`**。长行程通道，沿相对清楚的推进／退出方向完成解锁；作为基础形态 | **已接入 · F2 `eccentric_window`**。窗口偏心，取出过程中需要配合侧向对准和绕行，不能只把 F1 路径拉长 | **已接入 · F3 `turnback`**。含让位和折返结构；参考路线先前进让位，再回退、转向退出，推进方向并非一直单调 |
| **Cast Coil／回绕构件装配**：金、银两件方形回绕构件起初分开放在桌面，当前三档目标均为装配 | **已接入 · `baseline_assembly`**。基础对齐、插入与回转闭合结构 | **已接入 · `axial_screw_turn`**。回转通道带轴向变化，参考动作强调旋转与平移连续配合；选用冻结的 9 mm 家族代表 | **已接入 · `split_turn_offset`**。回转被中间错位段分开，参考动作为一段回转、错位／重对准、再回转；选用冻结的 9 mm 家族代表 |
| **Horseshoe Ring／马蹄解环**：两只马蹄由两条短链连接，每侧一个链节，中央套着可取出的铜色环 | **已接入 · `waist_mild`**。马蹄轻微收腰，目标环接近圆形，形状配合较温和 | **已接入 · `u_mild`**。马蹄轮廓更接近较方的 U，仍搭配近圆环；改变转移和通过时的形状配合 | **已接入 · `waist_ellipse`**。轻收腰马蹄配更明显的椭圆环，环的长短轴方向成为操作变量；不是单纯把圆孔缩小 |
| **Hedgehog in Cage／刺球出笼**：带刺木球被困在有开口的木笼里，调整球姿态使完整球体穿出 | **已接入 · `classic_3star`**。CLASSIC 木笼与十根刺的木球；`3star` 是原型名字，不代表只有三根刺 | **已接入 · `oblique_gate`**。十刺球与单斜窗木笼，出口取向使姿态对准与穿窗方向耦合 | **已接入 · `gen_keyhole`**。六刺球与顶部钥匙孔式出口，需配合特定开口形状；难度来源不是刺更多 |
| **Lock Picking／穿片开锁**：三片被动转盘、外圈实体销槽限位、终点板和带三个榫片的长钥匙 | **已接入 · F1**。盘距 150 mm，三盘槽数为 2／1／1，起始盘角均为 0°；来自“一次回退”设计代表 | **已接入 · `standard_150mm`**。盘距已恢复 **150 mm**，握柄偏移同步为 495 mm；三盘各有三个槽，起始盘角为 20°／−5°／−25°。这些槽形仍与历史“两次回退”代表不同 | **已接入 · F3**。盘距 150 mm，三盘槽数为 4／1／1，第一盘槽角依次 −72°／−48°／−24°／0°；来自“三次回退”设计代表 |
| **Fiber Bundling／光纤收束**：一束带公共根部的柔性细线与铜环，需让细线按材料顺序穿环且避免强烈弯折 | **已接入 · `4_strands`**。4 芯，铜环内半径 13.5 mm，线束稀疏 | **已接入 · `8_strands`**。8 芯，铜环内半径仍为 13.5 mm，同时管理更多线头和弯折状态 | **已接入 · `16_strands`**。16 芯，同一 13.5 mm 内半径铜环，线束更密、互相遮挡和整理压力更大；没有同步放大环孔 |
| **Buzz Wire 3D／立体电流棒**：木底座上的铜色导线、银色金属套环与木柄、起终点承托，要求沿线通行不触金属线 | **已接入 · `F1_triple`**。三座高拱和两个深谷，重点是连续上下绕弯；当前是三拱版，不是旧双拱版 | **已接入 · F2**。三连回折、错层八字和竖直 W 串联，路线有前后错层和折返 | **已接入 · F3**。水平梳齿、竖直 W、侧向 Ω 和倾斜螺旋串联，通行平面多次变化，需连续调整套环朝向 |
| **Interlocked Claws／互锁爪**：棕色件与蓝绿色件互锁，当前目标取出棕色件 | **已接入 · B0 `helical_claws_balanced_v2`**。两件对等的三头螺旋爪相向交错，各有底环、三根螺旋指和把手；参考运动为轴向移动配合旋转 | **已接入 · C0 `orthogonal_gate_balanced_v2`**。两个互相垂直的窗口构成换轴通道，另一件从一窗转移到另一窗；`balanced` 不代表两件全等 | **已接入 · A0 `claw_weave`**。原始多爪网格相互穿插的结构，需寻找可分离的相对姿态；旋转／翻转是否不可省略仍需捷径检查 |
| **Knot Untying／解绳结**：桌面上一根有两条自由尾端的 FEM 绳，目标整理为贴桌、静止且投影无交叉／重叠 | **已接入 · `overhand_trefoil`**。开放的单结／三叶结来源模板，标准结区与两条自由尾端 | **已接入 · `figure_eight`**。开放八字结模板，当前 `local_curve_v2` 的平面尺度参数为 32.5 mm、交叉高度参数为 10 mm | **已接入 · `double_overhand`**。开放双重单结模板，构造来自 (2,5) 环面曲线；不能把该源码家族误写成 5₂ 扭结 |
| **Blanket Flatten／布料展平**：60 × 48 cm 的 PBD 布料，目标展开并平稳覆盖桌面 | **已接入 · `simple_folds`**。五条主折痕形成的折叠初形，折角基础值 105°；默认仍是 authored 初始化 | **已接入 · `fold_roll`**。三条主折痕叠加五条卷曲折铰，带折角、板宽等扰动；“五卷”不是五个完整 360° 卷绕 | **准备阻塞 · `gathered_twist`**。设计为纵向聚褶后扭转，目标函数含 270° 扭转；难度类仍拒绝实例化，尚不能把目标网格当成已交付的平稳初态 |
| **Rope Threading／绳穿环**：桌面绳索与带支架的目标环，要求按指定顺序和方向穿过并稳定 | **已接入 · `two_rings`**。保留 R1/R2，净孔径 138 mm，目标 R1−／R2+；移除 R3 及对应支架、底座，沿用完整绳初态 | **已接入 · `wang_reference_v1`**。原参考三环及其支架，净孔径 138 mm，目标穿越序为 R1−／R2+／R3+；保留默认 base 与原实例身份 | **已接入 · `three_tight_rings`**。三环净孔径 100 mm；位置、法向、顺序及绳初态不变，支架与底座随缩环内移 19 mm。解法与难度资格待验 |
| **Slotted Post Ring／长孔立柱解环**：带长槽的立柱、绳、滑珠、两个末端圆盘和套在柱上的活动环 | **规划占位 · `large_ring`**。拟用较大目标环，获得较宽松的完整顶部解脱路线；尚无冻结环径与完整路径 | **规划占位 · `middle_ring`**。拟用中等环径，让顶部解脱需要更准确的倾角；不是已存在的可运行场景 | **已接入 · `original_scale`**。原尺寸结构：柱槽宽 28 mm，目标环内直径 102 mm，端盘直径 110 mm；需将环从完整穿套系统中取出 |
| **Orbits／阶梯连环解绳**：阶梯排列的环、带顶球的立柱，以及两端连在木柄上的受困绳圈 | **规划占位 · `2_rings`**。拟两环、三柱，配套受困绳圈；几何底层已支持减环，标准初态与解法资格未冻结 | **规划占位 · `3_rings`**。拟三环、四柱，增加一层环柱关系；仍不是当前可实例化的 medium | **已接入 · `four_rings_video`**。四环、五柱，整体 75% 尺度，使用 `video_solution_v2` 工作绳初态；绳的两端仍连接同一木柄 |

### 当前任务目标与场景描述的关系

六类分离任务——Keyhole、Horseshoe、Hedgehog、Claws、Slotted、Orbits——已接入**桌面绿色虚线目标区**：指定目标的全部几何必须入区，其余系统组件留在分界另一侧，并满足稳定条件；允许继续抓持。Orbits 的目标包含**整绳和木柄**。区域是这些任务各档共用的新终态要求，不是新增一个难度档。

这十一项新 terminal 规则已接线，但正式成功资格仍关闭；明确失败仍可 terminate。场景是否 `integrated` 与成功资格是否开放是两件事，详见[terminal 接入记录](../dev-logs/task_terminal_integration_20260926_zh.md)。Coil 的默认目标仍是装配后释放稳定；Blanket 仍使用展平指标，不套用分离目标区。

### Lock medium：实际参数不能由家族名推断

本次按 `common.declare()` 的实际合并顺序构造 `LockGeometry`，得到：

| 参数 | easy / F1 | medium / `standard_150mm` | hard / F3 |
|---|---|---|---|
| 盘距 | 150 mm | **150 mm（本轮恢复）** | 150 mm |
| 握柄偏移 | 495 mm | **495 mm（同步加长）** | 495 mm |
| 中心孔半径 | 7.5 mm | **14 mm** | 7.5 mm |
| 槽角半宽 | 8° | **14°** | 8° |
| 第一盘槽角 | −30°、0° | 0°、90°、210° | −72°、−48°、−24°、0° |
| 第二盘槽角 | −30° | 30°、150°、270° | −72° |
| 第三盘槽角 | 0° | 0°、180°、300° | 0° |
| 初始盘角 | 0°、0°、0° | 20°、−5°、−25° | 0°、0°、0° |

最初核对时，[medium 类](../../../topogym/tasks/lock_picking/lock_picking_medium.py)仅声明家族身份，继承 [common](../../../topogym/tasks/lock_picking/common.py) 与 [LockGeometry 默认值](../../../topogym/assets/geometry/lock_picking.py)，因而实际盘距为 85 mm。本轮按用户授权，在 medium 类显式覆盖 `pitch=0.150`、`grip_offset=0.495`，默认 `base` 同步生效；其余孔径、槽形、初始角和限位保持用户已运行候选的配置。历史“两次回退”资格仍不能直接继承，也没有开放新的成功资格。

### Lock 150 mm 是否越桌：当前摆位与历史预览的区别

2026-09-26 按统一 `load_scene_config()` 的解析结果和当前 `key_rest_layout()`／底座公式核对：桌面为 **1.5 × 1.4 m**，世界 X 边界 **[−0.8856786, 0.6143214] m**。配置中的旧 Compact AABB 注释未随桌面加大更新，本节使用实际 `pos ± size/2`，不使用旧注释数值。

| 设置 | 首盘 X | 底座 X 范围 | X 负向／正向桌边余量 |
|---|---|---|---|
| 修改前 medium：85 mm 盘距、300 mm 握柄偏移 | 0 m | [−0.405, 0.325] m | 480.7／289.3 mm |
| 当前三档：150 mm 盘距、495 mm 握柄偏移 | 0 m | [−0.665, 0.520] m | 220.7／94.3 mm |
| 旧预览摆位的 150 mm 版，放到当前共享桌面作对照 | 0.20 m | [−0.465, 0.720] m | 420.7／**−105.7 mm** |

当前两种尺寸的底座 Y 范围均为 [−0.365, −0.155] m，位于桌面 Y=[−0.7, 0.7] m 内。钥匙出生轴向范围也在对应底座 X 范围内；这里检查的是静态出生布局，不是全程运动包络或机器人可达性。

因此历史“150 mm 机构越出共享桌面”有依据：[旧预览配置](../../../configs/lock_picking_spaced_preview.yaml)显式使用 1.8 m 桌长，[录制记录](../modules/recording_module_usage_zh.md)记有 `world_compatible=false`。但当前首盘已移到 X=0，**现有 easy / hard 的 150 mm 布局不再越桌**；不能仅凭历史越桌记录判定 medium 必须保持 85 mm。也未找到足以证明当前 medium 采用 85 mm 就是由该记录直接决定的变更证据。

**取景仍有独立问题。** 使用当前 Panda 的 `agentview`／`front_oblique` 位姿、848×480 分辨率及 52° 垂直 FOV，将底座八角点做透视投影：85 mm 底座在 agentview 下方略有裁切、在 front_oblique 内完整覆盖；150 mm 底座在 agentview 下方和 front_oblique 左侧有裁切。Nyx 插件将该 FOV 写入 `fovY`，因此检查使用垂直视角。这是静态视锥计算，未新增 RGB 渲染，不包含遮挡或全流程画面验收。恢复历史 medium 时，仍应一起核对槽形、钥匙长度、相机覆盖和机器人可达性；仅改 `pitch` 会违反钥匙握柄净空约束。

**后续真实画面核对与恢复：**用户明确将要求限定为钥匙、锁片和终点孔入画，底座无需完整入画。用户运行的 [150 mm 候选报告](../../../runs/test_results/lock_pitch150_visual_render_20260926/lock_picking/report.json)通过 1 s home 保持，三路各 31 帧／约 1.03 s。检查真实首帧、末帧，并按生成网格核对投影后，主视角中的整把钥匙、三片锁片及终点孔范围均位于 848×480 图像内；终点孔保守包络约为 x=506.5..572.5、y=358.4..447.0 px。存在常规局部遮挡：主视角后排锁片互相遮挡，斜视角补充观察，但机器人也遮住部分钥匙／第一盘；斜视角终点孔在画外，home 腕视角主要朝向桌面。这是关键部件入画检查，不是所有视角无遮挡或全操作过程的资格。

视频实际位于 `lock_picking/branch_000/videos/`：[主视角](../../../runs/test_results/lock_pitch150_visual_render_20260926/lock_picking/branch_000/videos/agentview.mp4) · [斜视角](../../../runs/test_results/lock_pitch150_visual_render_20260926/lock_picking/branch_000/videos/front_oblique.mp4) · [腕视角](../../../runs/test_results/lock_pitch150_visual_render_20260926/lock_picking/branch_000/videos/wrist.mp4)。本轮默认值修改后，[静态等价报告](../../../runs/test_results/lock_pitch150_default_restoration_20260926/report.json)确认 medium／base 参数与该候选一致，1704 个资产文件逐字节一致，common、几何、预设和材质生成源码与运行快照一致；未重复声称新增了一次物理执行。

### 已有底层能力，不等于难度入口已经部署

- **Blanket**：common 已提供 `authored / flat_for_preparation / frozen` 初始化模式，但 easy/medium 默认仍为 authored，hard 仍为 blocked。统一聚褶、0°／135°／270° 的三档属于[补齐计划](three_tier_setting_completion_plan_20260925_zh.md)，没有替换本表的当前入口。不能宣称默认出生就是已验收的平稳落桌形态。
- **Rope**：底层已有环选择、孔径参数化与有序穿环目标；easy/hard 仍继承 `UnavailableTaskDefinition`。
- **Orbits**：底层已有 N=2/3/4、N+1 柱和匹配绳长参数化；easy/medium 入口中的“几何只支持四环”错误信息已落后于底层进展，但占位状态仍属实。
- **Slotted**：大／中环仍未冻结。表外 `clearance36` 改的是立柱槽宽，不能作为“大环 easy”的别名。
- **默认 base**：不是统一等于 easy。Lock/Fiber/Rope 指 medium，Claws/Slotted 指 hard；Orbits 仍指表外的四环 `reference85`（85%），与显式 hard 的 75% video-v2 不是同一实例；其余七项指 easy。

场景总览最初为源码核对；后续 Lock medium 的两项尺寸默认值已按上方记录恢复，并引用用户实际运行的候选证据。其余场景未在本轮修改，当前表中的三档顺序仍是设计目标，未新增难度资格。

## 三档落位与基础实例

“已接入”表示有具体 Task 类，通过 `common.py` 复用实体构造，并声明该档所需参数、几何家族或随包资源；资产构建结果见后文，**不代表完整 terminal、planner、当前机器人解题与模型难度校准均已完成**。部分基础档文件只声明身份并继承共用默认值，这是有意复用，不是空占位；真正占位继承 `UnavailableTaskDefinition`，不能实例化，也不会偷偷退回基础场景。

这里的“定档”只表示按已讨论的表确定了设计位置。全部 easy / medium / hard 仍是设计难度，不能写成已经通过模型表现校准的最终难度。

| 任务目录 | easy | medium | hard | 当前默认 `base` |
|---|---|---|---|---|
| [cast_keyhole](../../../topogym/tasks/cast_keyhole) | [F1 long_stroke](../../../topogym/tasks/cast_keyhole/cast_keyhole_easy.py)，已接入 | [F2 eccentric_window](../../../topogym/tasks/cast_keyhole/cast_keyhole_medium.py)，已接入 | [F3 turnback](../../../topogym/tasks/cast_keyhole/cast_keyhole_hard.py)，已接入 | easy（F1；旧 reference 已归档） |
| [cast_coil](../../../topogym/tasks/cast_coil) | [baseline_assembly](../../../topogym/tasks/cast_coil/cast_coil_easy.py)，已接入 | [axial_screw_turn 9 mm](../../../topogym/tasks/cast_coil/cast_coil_medium.py)，已接入 | [split_turn_offset 9 mm](../../../topogym/tasks/cast_coil/cast_coil_hard.py)，已接入 | easy |
| [horseshoe_ring](../../../topogym/tasks/horseshoe_ring) | [waist_mild](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_easy.py)，已接入 | [u_mild](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_medium.py)，已接入 | [waist_ellipse](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_hard.py)，已接入 | easy；原 reference 已归档 |
| [hedgehog_in_cage](../../../topogym/tasks/hedgehog_in_cage) | [CLASSIC 十刺](../../../topogym/tasks/hedgehog_in_cage/hedgehog_in_cage_easy.py)，已接入 | [oblique_gate 十刺](../../../topogym/tasks/hedgehog_in_cage/hedgehog_in_cage_medium.py)，已接入 | [gen_keyhole 六刺](../../../topogym/tasks/hedgehog_in_cage/hedgehog_in_cage_hard.py)，已接入 | easy |
| [lock_picking](../../../topogym/tasks/lock_picking) | [F1 one_retreat](../../../topogym/tasks/lock_picking/lock_picking_easy.py)，已接入 | [standard_150mm](../../../topogym/tasks/lock_picking/lock_picking_medium.py)，已接入 | [F3 three_retreats](../../../topogym/tasks/lock_picking/lock_picking_hard.py)，已接入 | medium |
| [fiber_bundling](../../../topogym/tasks/fiber_bundling) | [4 芯](../../../topogym/tasks/fiber_bundling/fiber_bundling_easy.py)，已接入 | [8 芯](../../../topogym/tasks/fiber_bundling/fiber_bundling_medium.py)，已接入 | [16 芯](../../../topogym/tasks/fiber_bundling/fiber_bundling_hard.py)，已接入 | medium |
| [buzz_wire_3d](../../../topogym/tasks/buzz_wire_3d) | [F1 三拱 home_lab_v1](../../../topogym/tasks/buzz_wire_3d/buzz_wire_3d_easy.py)，已接入 | [F2 home_lab_v4](../../../topogym/tasks/buzz_wire_3d/buzz_wire_3d_medium.py)，已接入 | [F3 home_lab_v4](../../../topogym/tasks/buzz_wire_3d/buzz_wire_3d_hard.py)，已接入 | easy（F1；旧 spatial_maze 已归档） |
| [interlocked_claws](../../../topogym/tasks/interlocked_claws) | [B0 balanced 螺旋](../../../topogym/tasks/interlocked_claws/interlocked_claws_easy.py)，已接入 | [C0 balanced 双窗](../../../topogym/tasks/interlocked_claws/interlocked_claws_medium.py)，已接入 | [A0 原始 Claw](../../../topogym/tasks/interlocked_claws/interlocked_claws_hard.py)，已接入 | hard |
| [knot_untying](../../../topogym/tasks/knot_untying) | [overhand_trefoil](../../../topogym/tasks/knot_untying/knot_untying_easy.py)，已接入 | [figure_eight local_curve_v2](../../../topogym/tasks/knot_untying/knot_untying_medium.py)，已接入 | [double_overhand](../../../topogym/tasks/knot_untying/knot_untying_hard.py)，已接入 | easy |
| [blanket_flatten](../../../topogym/tasks/blanket_flatten) | [simple_folds 五折](../../../topogym/tasks/blanket_flatten/blanket_flatten_easy.py)，已接入 | [fold_roll 三折五卷](../../../topogym/tasks/blanket_flatten/blanket_flatten_medium.py)，已接入 | [gathered_twist](../../../topogym/tasks/blanket_flatten/blanket_flatten_hard.py)，准备流程阻塞 | easy |
| [rope_threading](../../../topogym/tasks/rope_threading) | [两环，138 mm 净孔](../../../topogym/tasks/rope_threading/rope_threading_easy.py)，已接入 | [wang_reference_v1 三环](../../../topogym/tasks/rope_threading/rope_threading_medium.py)，已接入 | [三环，100 mm 净孔](../../../topogym/tasks/rope_threading/rope_threading_hard.py)，已接入 | medium |
| [slotted_post_ring](../../../topogym/tasks/slotted_post_ring) | [大环顶部解脱](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_easy.py)，占位 | [中环倾斜解脱](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_medium.py)，占位 | [原尺度](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_hard.py)，已接入 | hard |
| [orbits](../../../topogym/tasks/orbits) | [两环](../../../topogym/tasks/orbits/orbits_easy.py)，占位 | [三环](../../../topogym/tasks/orbits/orbits_medium.py)，占位 | [四环 75%＋video-v2 工作绳初态](../../../topogym/tasks/orbits/orbits_hard.py)，已接入 | 保留 reference85；四环基础属于 hard 家族，精确实例不同 |

主三档共 **32 个具体 Task、6 个待设计占位和 1 个准备流程阻塞占位**。

本轮归档后 Keyhole／Buzz 默认 base 已切换为表中 easy。Orbits 仍保留旧默认，只有显式 hard 选择表中新代表。Horseshoe 已采用形状／方向配合三档，替代原余量方案；旧照片比例 reference 已归档，不能继承它或旧圆环机器人的成功标签。

### 当前哪些已经填入内容

- **三档构造全部接入，共 9 项／27 档：**Horseshoe、Cast Keyhole、Cast Coil、Hedgehog、Lock Picking、Fiber Bundling、Buzz Wire、Interlocked Claws、Knot Untying。
- **部分接入，共 4 项／5 档：**Blanket easy / medium、Rope medium、Slotted hard、Orbits hard。
- Horseshoe 三档为暂定设计难度；只有历史零件几何解，机器人与模型难度资格仍待验证。

7 个未完成档位的缺口如下；这些不是缺 planner 才被标为占位，而是 setting 的几何／初态契约本身尚未完成：

| 档位 | 未填完的具体部分 |
|---|---|
| Blanket hard（1） | 已有 gathered 目标形状计算，缺保持平坦材料静止构型的分阶段 PBD 初态准备；不能加载扭曲 OBJ 来替代 |
| Rope easy / hard（2） | 缺少冻结的环布局和配套绳初态／穿环契约，不能只改环数或环径就当作接入 |
| Slotted easy / medium（2） | 缺少满足顶部解脱且不能越过末端圆盘的环径；`clearance36` 改的是柱槽宽，不是目标环径 |
| Orbits easy / medium（2） | 底层已支持两／三／四环，尚缺冻结并接入主档的两环／三环代表 |

### 尚未完善的 setting：当前源码核对（2026-09-25，Horseshoe 定档之后）

当前主表 **13 个任务、39 档：32 integrated、6 planned、1 blocked**。9 个任务三档构造齐备；剩余 **4 个任务／7 档**需要继续补齐。这里统计的是任务设置，不把缺 planner、缺完整机器人成功或缺模型校准混算为“没有变体”。本轮只核对源码并更新文档，没有修改几何或运行物理。

| 任务 | 已有主档 | 待补档位 | 项目现有支持 | 仍需决定／实现 |
|---|---|---|---|---|
| Rope Threading | medium：wang_reference_v1 三环 | easy：两环；hard：小孔三环 | [ThreadingLayout、ring_mesh、route_crossings](../../../topogym/assets/geometry/rope_threading.py)、现有三环参考资源、[FEM Task](../../../topogym/tasks/rope_threading/common.py) | 决定 easy 保留哪两个环及穿环顺序；hard 优先仅缩环内径，固定其他几何，避免同时改环距混入第二条难度轴。增加冻结布局／环选择与半径配置，连同支架、初始绳位置、碰撞及目标顺序一起核对 |
| Slotted Post Ring | hard：原尺度 | easy：大环顶部解脱；medium：中环倾斜解脱 | [SlottedPostLayout](../../../topogym/assets/geometry/slotted_post_ring.py) 已有环主半径、管径、柱槽、珠和端盘尺寸参数及合法性检查；[clearance36](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_clearance36.py) 是现存表外候选 | 先确认三档机制能在同一柱／绳／端盘结构中成立；搜索大／中环数值，使顶部解脱分别宽松／需倾斜，同时不能越过端盘。不能把环能套过柱截面的静态检查当作带绳完整解脱证明；36 mm 改槽宽，不填大环档 |
| Orbits | hard：四环、75% video-v2 工作初态 | easy：两环；medium：三环 | [OrbitsLayout、cord_centerline、make_meshes](../../../topogym/assets/geometry/orbits.py)、[hard 参数](../../../topogym/tasks/orbits/orbits_hard.py)；[工作绳构造](../../../topogym/tasks/orbits/common.py) | 将两／三／四环统一参数化，并同步决定柱数、阶梯高度、绳初始绕法、绳长及木柄位置；检查回穿轮次是否真的减少。2026-09-26 核对底层已完成 N=2/3/4 参数化；主档仍需冻结匹配绳初态并验证解法，不能把参数化通过等同于档位部署 |
| Blanket Flatten | easy：simple_folds；medium：fold_roll | hard：gathered_twist（blocked） | [hard.preparation_target](../../../topogym/tasks/blanket_flatten/blanket_flatten_hard.py)、[gathered_target](../../../topogym/assets/geometry/blanket_gathered.py)；[历史 preparation.py](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/preparation.py) 保留分阶段物理准备 | 设计方向已有，主要缺工程接入：保留平坦材料 rest shape，物理准备聚褶／扭转，移除准备控制并稳定，再交付 episode 初态；核对 seed 复现、历史／回溯身份与实际起始 RGB，不能用扭曲 OBJ 重定义材料静止形状 |

**目录支持到哪一步：**7 个难度入口都已存在，使用 `UnavailableTaskDefinition` 明确拒绝运行；registry 会公开缺口。`assets/geometry` 提供已有构造和部分尺寸参数，历史快照提供可回收的路径／初态准备逻辑，但没有一个现成生成器能自动补齐这 7 档。当前 [planning](../../../topogym/planning/README.md) 仍只有 Coil 参考运动，尚无 39 档完整 planner 入口；它与 setting 补齐是两项工作。通用 [solvers](../../../topogym/solvers) 已有运动学与碰撞工具，也不等于特定变体已有解。

**建议推进顺序（工程判断）：**先做 Rope easy，再在同一参数化上确定 Rope hard；同时优先做 Slotted 的小范围几何／解法可行性调查，因为它可能需要调整原难度设计。随后补 Orbits 两／三环构造；Blanket hard 的物理初态准备作为独立工程处理。每次先确定一个具体代表，再检查初态、预期解法与简单捷径，最后填入口，不先扩成随机家族。

三档构造齐备的 9 项为 Keyhole、Coil、Horseshoe、Hedgehog、Lock、Fiber、Buzz、Claws、Knot；它们仍有第二类“完善”工作：Horseshoe 的形状档位暂定且只有零件几何路径，Claws 需排除侧移等捷径，Lock easy/hard 缺完整机器人流程，Knot medium/hard 尚无完整成功证据。其他已接入档同样不能由 integrated 推导为新 simulator 下已 solve。整体难度顺序仍需模型校准；这些不增加上述 7 个空缺档位。

### 完成度口径

| 层次 | 当前核对结果 |
|---|---|
| 三档设计位置 | 39 档已有名字与预期家族；难度排序仍待模型校准 |
| 具体构造接入 | 32 档；本次核对类身份、占位类型及显式资源路径一致，无缺失。既有安装包资产检查见文末；新增 Horseshoe 三档本轮另作资产构建检查 |
| 当前成功判据 | 2026-09-26：十一项新规则及执行链接入已完成，但成功资格仍为 false；Coil / Blanket 沿用既有判据。详见本页场景描述后的 terminal 说明 |
| 历史完整机器人流程 | 按[历史 oracle 清单](../../../legacy/cleanup_20260929/docs/develop/tasks/planner_oracle_inventory_20260925_zh.md)有 21 个主档代表；允许其档案声明的旧起点／辅助／后端，不能转成新框架资格 |
| 新标准完整 solve／难度资格 | 本次没有补入新的完整成功证据，也没有进行模型难度标定；由后续 terminal、assist、planner 与逐实例验收分别完成 |

“有现行判据”是代码事实，不表示已经满足最近讨论的全部任务要求或通过完整机器人终态验收。[terminal 工程计划](terminal_judgement_engineering_plan_20260925_zh.md)中新增的目标区、历史进度和失败条件已接线，真实物理及成功资格仍须逐实例验收。Claws 的几何已接入同样不证明旋转／翻转是结构上必需。

## 历史候选与 demos 的关系

**二者有交集，但不是同一份集合。** 更准确的叫法是“表外历史／实验设置”：既包括曾经展示过的完整旧任务，也包括只有构造、几何证书、IK 或失败尝试的设置。反过来，很多历史 demo 正是当前三档选用的来源，因此“历史”不等于“被三档淘汰”。

| 具体例子 | 当前 demos 与源码事实 | 在主三档中的位置 |
|---|---|---|
| Keyhole F1/F2/F3、Coil 三个选定代表、Buzz F1/F2/F3、Fiber 4/8/16 芯、Claws A0/B0/C0 | 当前 [demos](../../../demos/README.md) 仍有相应展示；精确版本／执行范围以归档为准 | 已作为主三档构造来源，不应随表外候选一起剔除 |
| Coil `eccentric_turn` | [展示目录](../../../demos/cast_coil/varaition_eccentric_turn)存在，历史有完整流程；旧入口已移入 tasks/legacy，视频和证据保留 | 表外，与 baseline 动作结构过近而未列入当前三档 |
| Hedgehog `fixed_side_window` | [展示目录](../../../demos/hedgehog_in_cage/varaition_fixed_side_window)存在，历史有完整流程 | 表外入口已归档；当前 easy 是 CLASSIC，不能用 fixed_side_window 冒充。CLASSIC 的完整历史在归档，当前 demos 下未见其独立目录 |
| Blanket 的三个额外脚本 | 当前 [Blanket 展示目录](../../../demos/blanket_flatten)只见 `varaition_simple_folds`；`three_folds / fold_spiral / corner_cross_twist` 是源码中的额外设置 | simple_folds 对应 easy；三个额外脚本不是当前 demos 中的三套完整解法 |
| Horseshoe 旧 `baseline / F1 / F2 / F3` | [展示目录](../../../demos/horseshoe_ring)有旧流程；旧三条路线是 high / outer / rear approach | 不对应新选定的形状／定向三档；不能按相同 F 编号直接配对 |
| Lock F1/F3 | [展示目录](../../../demos/lock_picking)存在；历史清单核对的是几何／IK／运动学预演，尚无对应全流程动力学成功 | 构造已填 easy / hard，但不能因此标完整 planner 已支持 |
| Slotted `clearance36` | [展示目录](../../../demos/slotted_post_ring/varaition_clearance36)及外力完整流程存在 | 表外柱槽设置，不是新 easy“大环”；当前 hard 为原尺度 |
| Orbits `rope_only / base_centered` | [展示目录](../../../demos/orbits)保留无臂／旧参考材料；video-v2 的完整参考路线不是机器人完整成功 | hard 采用 75% video-v2 工作初态来源并改接 Genesis FEM；不能继承无臂成功。`base=reference85` 仍是不同实例 |

当前注册表共有 **39 个 `tier`、4 个 `experimental`、1 个 `compatibility`**（归档前为 39／38／4）。`experimental` 是表外分组，不代表失败；`compatibility` 保留旧默认，也不代表没有 demo。删除或迁出额外任务入口与保存旧 demo 是两件事，两轮累计移动了 37 个表外入口并撤下其注册，未删除旧 demo 或几何资源。

## 迁入的构造与表外设置

- **Keyhole：**随包保存 F1/F2/F3 冻结轮廓／分层记录，迁移 slab 重建；不要求 reset 执行逆向搜索，也不继承历史运动证书。
- **Coil：**使用 seed_families_v1 的实际 9 mm 模板。eccentric_turn、face_small、depth_thick、corner_cut 已归档至 tasks/legacy；原合成和外形构造能力仍在几何层。
- **Horseshoe：**使用 coupled_shapes_v1 的 waist_mild / u_mild / waist_ellipse 冻结资源，链长统一 18 mm，直接接入三个难度类。21 个描述性候选及旧 reference 入口归档；旧 F1/F2/F3 接近路线不映射到新三档。
- **Hedgehog：**部署冻结网格、逐块碰撞、局部球姿态和刺数。fixed_side_window、staggered_gates、helical_guide 已归档至 tasks/legacy；不恢复成默认难度池。机器人仍从标准 home 开始，未复制历史预抓持关节状态。
- **Lock：**F1/F3 的槽位和实体限位一起进入标准 Task；F2 two_unequal 已移入 tasks/legacy，不再注册。三齿钥匙与槽数是不同参数，未改成“几槽就是几齿”。
- **Buzz：**冻结完整 authored controls、姿态、支撑和端挡参数，不再用通用 maze 冒充 F1。旧双拱 double_arch 与旧默认 spatial_maze 已归档。
- **Claws：**共用 FamilyModel 的 compound URDF，保留初始相对姿态。旧 helical_crown／orthogonal_gate 已归档；新 C0 仍为已有的框架／钥件结构，不声称两件全等。
- **Knot：**medium 显式采用 0.0325 m 结区尺度、0.010 m 交叉高度；原尺寸 figure_eight 与 left_overhand 已归档并移除旧别名，不将旧 figure_eight 请求重定向到放大版 medium。这里的“放大 25%”针对原 figure-eight 候选 0.026 m，不是相对当前 trefoil 默认 0.032 m。
- **Blanket：**全部现有 BlanketLayout 字段已接线，包括卷曲和初态朝向；seed 仍归管理方，seed=2 对应 fold_roll 的原候选。three_folds、fold_spiral 保留。gathered_target 已迁入纯几何模块，并由 hard 文件提供 `preparation_target`；它不等于物理准备完成。corner_cross_twist 另有阻塞占位。
- **Slotted：**clearance36 明确为柱槽候选，没有把它误名为大环 easy。
- **Orbits：**从历史源码只抽取工作绳初态计算，以 75% 器具、0.60 m 木柄位置及对应绳长连接当前 FEM/IPC 声明；旧 MuJoCo 执行与录制代码未迁入。它不继承旧无臂执行的成功标签。

当前目录共 44 条规范记录（两次归档前依次为 81、66 条）：39 个主档位，另有兼容或实验设置。`pool` 字段区分 `tier / compatibility / experimental`。当前保留的实验代表是有限清单；没有把随机域内每个 seed、每种颜色或重复录制修订展开成独立 Task。

所需输入已放入安装包 [resources/variations](../../../topogym/assets/resources/variations)，经资源 catalog 校验；历史 `runs/`、仓库根目录 `assets/tasks/` 不再是这些设置的运行依赖。[来源清单](../../../legacy/cleanup_20260929/docs/develop/tasks/variation_deployment_sources_20260925.json) 保存原路径、SHA-256 和迁移目标；历史档案与视频没有改名。

## 检查与运行限制

以下记录原变体部署验收批次及当时的环境限制，证据绑定该批源码／安装包；本轮没有重跑以下历史验收批次；入口归档有独立报告，也不以当时的 CUDA 检测代表其他会话或当前机器的可用状态。

- 单元、接口合同和架构检查：**174 项通过**。包括占位拒绝、具体类选择、旧别名、不同结构的身份区分、参数保护以及原有 episode／回溯权限合同。
- Blanket／Fiber 随机初态另补查 seed=0：7 个具体设置均构建通过，2 个占位排除。
- 主三档外的 Horseshoe 初次构建暴露了模板选错：fixed_trace 明确基于 tutorial_solvable_v3 的单链环模板，不能套用当前 reference 的三链环照片模板。已修正来源并复查，失败报告保留，没有放宽几何碰撞校验。
- 新 wheel 已包含 39 个难度模块及全部冻结资源。独立安装目录中 **70 个具体设置全部通过资产构建、结构检查和跨输出目录重复生成；11 个占位被明确排除**。其中主三档是 29 个通过、10 个占位。seed=2 的[最终资产报告](../../../runs/test_results/variation_deployment_20260925/installed_assets_final/report.json)断言加载的所有 TopoGym 模块来自该安装目录；安装包文件与最终工作树逐文件比较无差异。
- 本环境检测结果为 `cuda_available=False`、设备数 0。**当前变体真实 Genesis＋Nyx 初始化、推进、录像和回溯未执行**；没有换用 Rasterizer，也没有将历史视频当本轮证据。

完整证据入口：[验收说明](../../../runs/test_results/variation_deployment_20260925/README.md)、[单元测试报告](../../../runs/test_results/variation_deployment_20260925/unit_contract_architecture.xml)、[wheel 身份](../../../runs/test_results/variation_deployment_20260925/wheel_report.json)、[CUDA 检查](../../../runs/test_results/variation_deployment_20260925/runtime_preflight.json)。

GPU 可用的环境中运行全部已有主档位：

```bash
cd /home/jianwen/topogym
.venv-gs121-nyx/bin/python scripts/test_variation_runtime.py \
  --output runs/test_results/variation_runtime_gpu_20260925 \
  --steps 20 --timeout 1800
```

该脚本按设置启动隔离进程，复用 `scripts/test_base_tasks.py` 的标准 Nyx 录像、源码指纹、seed 重建和回溯验证。占位项记录 unavailable。输出目录需不存在；重复验收换一个新目录名。也可单独运行：

```bash
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --tasks cast_coil --variation cast_coil_medium --checks base \
  --steps 20 --output runs/test_results/cast_coil_medium_runtime
```

原有未完成成功判据及抓持能力缺口保持可查询。此次部署没有验证旋转／翻转是否结构必需，也没有解决此前讨论的侧移捷径；难度标记不能当作这些性质已获证明。
