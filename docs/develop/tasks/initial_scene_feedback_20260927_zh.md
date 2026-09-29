# 初始化场景反馈与答复（2026-09-27）

下一轮工作：[Hedgehog / Claws 新机制 scripted policy 开发与全流程验收](hedgehog_claws_scripted_policy_plan_20260927_zh.md)，细化两个 medium 的阶段策略、几何与抓持前置检查、机制反例、当前目标区终态合同和完整录像交付；当前为需求文档，未新增完整解题资格。

本页对应本轮的数量疑问及 8 条场景反馈。历史反馈的核对依据是当时的 Task 定义、资产生成代码、冻结资产和 9 月 27 日初始化录制报告。历史录制状态截点为 **2026-09-27 18:24 UTC（Chicago 13:24）**；后台队列后续状态以[录像索引](../../../runs/test_results/base_acceptance_final/README.md)和[汇总报告](../../../runs/test_results/initial_scenes_20260927_01/summary.json)为准。

**用户已批准按本文进行一轮开发，并要求 Hedgehog medium 使用深色实木纹理。本文第 0–8 节保留反馈时的核对记录；本轮实现及验证状态见末尾第 9 节，旧录制状态不代表开发后的结果。** 用户已选定第 3.2 节的双夹爪完全相对布局作为 Claws medium 建模方向，并明确原夹爪模型不变、segment0 已持件且中央互锁。选定方向与已验证实现分别记录，尺寸仍需按真实夹爪适配。

## 0. 为什么是 44 个？Orbits compatibility 是什么？

**正式范围应为 13 个任务 × easy / medium / hard = 39 个入口。** 上一版索引按整个注册表展开，把兼容和实验入口混入主表，造成了“44 个正式变体”的误解；这是索引统计口径不符合原要求。

额外 5 个入口如下，不是额外的正式难度：

| 入口 | 类型 | 用途／当前关系 |
|---|---|---|
| `orbits_reference85` | compatibility | 保留 0.85 倍参考几何和较紧凑绳路；当前 Orbits 的 `base` 别名仍指向它，没有 easy / medium / hard 标签 |
| `blanket_flatten_three_folds` | experimental | 三折实验入口 |
| `blanket_flatten_fold_spiral` | experimental | 折叠加螺旋实验入口 |
| `blanket_flatten_corner_cross_twist` | experimental | 角部交叉扭转实验入口，目前阻塞 |
| `slotted_post_ring_clearance36` | experimental | 额外的 clearance36 几何候选 |

`compatibility` 的意思是保留参考版本／默认入口的兼容性，不表示一种难度，也不表示经过了比 hard 更充分的难度校准。[参考版本定义](../../../topogym/tasks/orbits/orbits_reference85.py)明确写着 `difficulty = None`。

索引后续应改为 **39 行正式三档主表 + 5 行兼容／实验附表**；未开发档位保留空白媒体格，已开发但录制失败者写出失败原因。`base` 只标为别名，不重复计数。若参考版的紧凑绳路用于新的 hard，应修改 hard 的实际定义和证据，再核对默认别名；不能只把旧视频改标签。

截至上述截点，正式 39 个入口中：32 个已接入、6 个待开发、1 个阻塞；其中 29 个已有本批通过的初始化短片，3 个尚缺（Buzz medium、Knot hard、Slotted hard）。全注册表的 32 个已录制入口另包含 3 个兼容／实验入口。初始化短片仅覆盖 4 个控制步、0.1 秒物理时间，不能据此认定完整可解或长期稳定。

## 1. Orbits：缩小 hard 绳圈，把连接的小木件放到圈外

**反馈：** hard 绳圈过大；与绳圈连接的小木球应位于圈外；这样是否能抵消初始猛地弹开？参考 compatibility 的尺寸更合适。

**核对结果：** 大小差异确实存在，且不只是视角造成。实际录制资产报告给出的绳长是：

| 版本 | 框架比例 | 绳长 | 木柄局部 X 坐标 | 初始图 |
|---|---:|---:|---:|---|
| hard / `four_rings_video` | 0.75 | 约 1.697 m | 0.600 m | [hard 首帧](../../../runs/test_results/initial_scenes_20260927_01/orbits_hard/orbits/initial_frames/cam_high.png) |
| compatibility / `reference85` | 0.85 | 约 0.532 m | 0.3655 m | [reference85 首帧](../../../runs/test_results/initial_scenes_20260927_01/orbits_reference85/orbits/initial_frames/cam_high.png) |

hard 的绳长约为参考版的 **3.19 倍**，框架却略小。[初态生成函数](../../../topogym/assets/geometry/orbits_initial.py)保留旧工作绳的总长度，再让富余长度向两侧鼓出；[hard 实际构造](../../../topogym/tasks/orbits/common.py)又把木柄放到局部 X = 0.60 m。这解释了当前大圈形状，但“大圈”本身不是已验证的 hard 难度来源。

这里需要区分两个木件：绳两端连接的是可动的双孔小木柄 `handle`；高处立柱上的圆木球 `stopper_ball` 是固定件，没有连接绳端。本条按“**与绳相连的末端小木件**”理解，修改对象是小木柄及两端出绳方向。应让它处于主要绳圈外侧，避免绳腿绕回包住木柄；不把固定挡球误当成末端木柄搬走。

**对弹开问题的答复：可能改善局部接触或出绳方向，但不能保证消除。** 目前静态报告的绳—木柄净空下界仍为正，不能直接断定是木柄挤压造成。另一方面，[FEM 绳体生成器](../../../topogym/assets/geometry/rope_volume.py)保存的是直的材料参考坐标 `rest` 和弯曲初态 `spawn`；弯曲形状相对材料参考构型的应变、端点绑定误差与初始接触响应，都需要检查。这里有可排查的原因，尚没有定位到视频中猛弹的单一根因。

**修改要求与验证：** 以 reference85 的紧凑外形作为 hard 改形参考，保留四环约束；同步设计绳长、圈形、木柄位置和端点方向。新绳长仍须允许完整解题，不能只按视觉缩短。分别对照原形、紧凑形、木柄外置形，记录 reset 后若干步的绳速、端点误差、接触及形变；验证无明显初始冲量、无穿模、没有直接脱出的捷径。此处不以提高阻尼或截掉弹开片段代替原因修复。

## 2. Interlocked Claws：初态应已经双手持件、中央互锁

**反馈：** 两个夹爪应已夹住或安装好各自的 claw，两件在中间纠缠。

**当前行为：** [任务定义](../../../topogym/tasks/interlocked_claws/common.py)将参考装配整体平移到桌面上，并明确记录 `robot remains at home`。因此现有视频中的“物件在桌面、夹爪未持件”是当前初始化实现，并未达到本次要求。

**修改要求：** 三档统一从双臂各持一件、两件在工作区中央处于有效互锁的状态开始，任务重点是解锁分离。本次要求更新了 Claws 的起始条件，后续不能继续套用“所有任务首帧都必须 home 未抓取”的旧假设。

**用户最新确认：仍由现有夹爪夹着独立的 claw，不修改夹爪建模。** 保留原 ALOHA 夹爪的视觉网格、碰撞形状、手指机构及关节限位；调整的是 claw、其握柄及初始装配姿态。概念图中的灰色占位夹爪不能替换真实夹爪，也不能把 claw 并入夹爪网格或焊成新的末端工具。夹爪关节开合及机械臂位姿的设置属于初始化配置，不属于更改夹爪模型。

**segment0 起始合同：** 管理方初始化／reset 完成后、第一条操作动作之前，两只夹爪已经分别闭合夹住各自的 claw，两件 claw 在工作区中央处于相扣、卡住但无穿透的装配状态。后续 segment 从解锁动作开始；拾取和把两件组装到一起不属于 segment0 待完成动作。不能先交付未抓持状态，再在第一个 step 瞬移或补上抓持。

初始化需同时保存并恢复机械臂关节、手指开度、两件位姿及实际抓持状态；如使用现有 grasp assist 辅助稳定，须如实记录，且真实手指仍应夹在握柄上。两件之间的“卡住”来自几何约束，不给两件添加固定连接；后续仍须可通过正确相对运动分离。验收覆盖首帧双手已持件、直接拉开受到几何阻挡、无穿模及无操作短程稳定。静态图中的“不相交”尚不足以证明有效互锁或稳定抓持。

## 3. Interlocked Claws medium：锐角双窗、独立握柄和两阶段转动

**反馈：** 现状看起来一次转动就能拔出；窗侧需要横向篮子提手式握柄；两窗应成锐角，蓝色件改成钩形，通过第一窗后还必须再次转动才能通过第二窗。

**现状与答复：** 当前是 `orthogonal_gate_balanced_v2`。[几何定义](../../../topogym/assets/geometry/interlocked_claws.py)使用两扇正交窗，外框约 250 × 190 mm、净开口约 220 × 160 mm；蓝件由叉形结构与长横杆组成。代码中的预设路线确实安排了“先 roll，通过第一窗，再 yaw，通过第二窗”，但这只说明设计者提供了这样一条路线，**不能证明不存在一次转动后整体拔出的捷径**。已有省略某一步的少量反例检查也不能排除所有其他姿态。用户提出的捷径疑问应保留为待排查问题。[当前首帧](../../../runs/test_results/initial_scenes_20260927_01/interlocked_claws_medium/interlocked_claws/initial_frames/cam_high.png)。

**修改要求：**

1. 窗框外侧增设横向篮子提手式握柄，给夹爪完整的接近、闭合和转动空间。
2. 两窗改成锐角夹角，具体角度由几何可行性确定，不直接沿用 90°。
3. 蓝件改成有明确钩头／回弯的结构；姿态 A 能斜穿第一窗，抵达第二窗时被倾斜窗框压缩的有效通行空间挡住。
4. 在两窗之间留出可重新定向的空间；切换到姿态 B 后才能退出第二窗。窗口间距与钩头尺寸需共同设计，避免变成根本无解。

验收需要同时找到一条可执行的两阶段路线，并主动搜索“固定同一姿态贯穿两窗”“一次旋转后直拔”“从外侧绕开第二窗”等捷径。新增握柄不能扩大开口形成绕行通道。这里的 medium 难度目标是**必须重新定向**，不能仅靠窗口数量或更窄的间隙命名。

### 3.1 新架构的早期侧抓候选（保留对照，采用方案见 3.2）

我建议先做一个 **55° 锐角双窗 + 长柄 J 形回钩**的候选。棕色件是一个完整刚体：两扇前后错开的封闭矩形窗，通过窗角外侧的连接杆连在一起；靠操作者的一侧另有横向篮子提手。蓝色件也是一个完整刚体：长杆贯穿两窗，左端向下回弯并带一小段向上的钩尖，右端是独立握柄。

初始时，钩头留在第一窗外侧，长杆已穿过第一窗和第二窗，回钩尚未通过任何一窗。两侧夹爪分别持棕色提手和蓝色握柄，两件在桌面上方中央相扣；预期向握柄一侧取出蓝件。这比“两个窗旁边放一根钩子”更明确地表达了需要解开的初始装配。

以下是**实际尺寸网格在 Nyx + compact_lab 中的静态渲染**，不是生成式想象图。它展示拟采用的首帧构型，**还不是正式 Task 经 `reset()` 得到的首帧**。灰色夹爪为平行夹爪占位模型，用来表达预装握持位置；尚未替换为真实 ALOHA 夹爪与手臂，也未求解机器人 IK、建立实际抓持约束或推进物理步。

#### 预期首帧：斜视

![Claws medium 锐角双窗与 J 形回钩：静态首帧构型预览](../../../runs/test_results/claws_medium_acute_concept_20260927/initial_oblique.png)

棕色横向提手在窗框外侧，灰色夹爪从其外侧接近；蓝色握柄在另一端。蓝色长杆已穿窗，钩头留在入口侧。图中握持方式仅表示待实现的初态安排。

#### 俯视：看两窗的锐角关系

![Claws medium 俯视：两窗平面夹角 55 度](../../../runs/test_results/claws_medium_acute_concept_20260927/initial_top.png)

两窗平面夹角为 55°，不是两扇平行窗，也不是原方案的直角窗；窗心沿初始长杆方向相距 180 mm。外侧提手不穿过通行开口。

#### 钩头侧视：看回弯和第一道限制

![Claws medium 钩头细节：第一窗之前的 J 形回钩](../../../runs/test_results/claws_medium_acute_concept_20260927/hook_detail.png)

#### 当前候选尺寸与动作构思

| 部位 | 本图使用的参数 | 设计目的 |
|---|---|---|
| 两扇窗 | 净开口均为 160 × 180 mm；方形框条厚 12 mm | 给倾斜后的钩头留通道，同时挡住竖直直拔 |
| 窗的相对布置 | 平面夹角 55°；窗心沿初始杆轴相距 180 mm | 两道限制的有效通过方向不同，窗间留重新定向空间 |
| 蓝色回钩 | 杆径 12 mm；钩头上下包络约 212 mm，轴向包络约 54 mm | 竖直尺寸大于窗高；需要倾转，不能保持初始姿态沿杆轴直拔 |
| 棕色提手 | 横向握持段约 200 mm，直径 16 mm | 独立于窗边，避免夹爪占用通行空间 |
| 蓝色握柄 | 70 × 28 × 24 mm | 为另一夹爪提供独立的接近和持件位置 |

预想动作分三段：**倾转通过第一窗 → 在窗间转向 → 斜穿第二窗**。第一段可从绕长杆轴倾转约 45° 的姿态开始探索：200 mm 的钩头中心线高度加上杆径，在该角度的横向／竖向包络约为 153 mm，能进入第一窗的 160 × 180 mm 开口，但还需要平移对中。

保持第一段姿态及原来的直拔方向到第二窗时，倾斜窗沿原方向呈现的横向投影宽度仅约 `160 × cos(55°) ≈ 92 mm`。这解释了我希望引入的第二道空间约束。第二段应让钩头连同长杆转向第二窗的法向附近，再微调倾角穿出；不是重复同一个直拔动作。

上述投影尺寸是构思依据，**不能单独证明第二次转动必不可少，也不能证明全程可解**。J 形件不是实心矩形，可能存在逐段穿越的捷径；转向时长杆、握柄和夹爪也可能撞第一窗或外侧连接杆。下一步需要对整个刚体的连续运动检查净空，并搜索一次转动、侧绕、反向脱出等替代路径，再决定是否收窄窗、缩短长杆或调整窗距。这些参数目前是用于讨论的建模起点。

已完成的检查仅为：本候选**初始棕／蓝两件表面无相交，最小表面间距约 4 mm**。它不包含运动路径、夹持接触、稳定性或机器人可达性资格。

模型和复现资料：[可下载的三维装配 GLB](../../../runs/test_results/claws_medium_acute_concept_20260927/assembly.glb)、[参数与静态检查结果](../../../runs/test_results/claws_medium_acute_concept_20260927/concept.json)、[建模／渲染脚本](../../../runs/test_results/claws_medium_acute_concept_20260927/render_source.py)、[产物 SHA-256](../../../runs/test_results/claws_medium_acute_concept_20260927/sha256.json)。正式 `interlocked_claws_medium` 定义尚未被本候选替换。

### 3.2 双夹爪完全相对的初始方案（按默认面对面布局修订）

**用户已确认采用这一版作为后续建模方向。** 上一版把棕色提手放在侧面，导致两夹爪从近似正交方向持件，没有体现默认的面对面布局。这一版保留 55° 双窗与 J 形钩的构思，把棕色件的握持结构改成**后置 U 形连接架 + 向左伸出的轴向握柄**；蓝色件的握柄仍朝右。两只夹爪同高、共轴，分别朝 +X 和 −X，开合轴平行。正式实现必须使用原夹爪模型来夹持这两件 claw，并满足第 2 节的 segment0 合同；图中占位夹爪仅用于构型说明。

#### 正视：两夹爪完全相对

![两夹爪完全相对的 Claws medium 初始构型，Nyx 静态预览](../../../runs/test_results/claws_medium_opposed_concept_20260927/initial_front.png)

左夹爪持棕色短柄，右夹爪持蓝色长柄。棕色 U 形架从钩头两侧绕过并连接第一窗，避免让握柄正好挡在钩头活动区。蓝色杆已经穿过两扇窗，J 形回钩留在第一窗之前；两件不是分开放置后再靠近。

#### 斜视：连接架、回钩和两窗的位置

![相对夹爪方案斜视：棕色后置连接架与蓝色回钩](../../../runs/test_results/claws_medium_opposed_concept_20260927/initial_oblique.png)

#### 俯视：共轴持件与 55° 双窗

![相对夹爪方案俯视：两握持点共轴，两窗保持锐角](../../../runs/test_results/claws_medium_opposed_concept_20260927/initial_top.png)

**尺寸适配：** 根据[默认 home 配置](../../../topogym/config/profiles/robot_control_configs/aloha_position_ik.yaml)、[机器人 XML](../../../assets/robots/aloha/aloha.xml)和[抓持点定义](../../../topogym/robot/aloha/description.py)进行静态正运动学计算，两侧抓持点间距约 **375.08 mm**。本图用这个间距约束两个握柄的位置，将解锁结构相对上一版缩至约 0.633 倍，同时保留适于夹持的握柄截面。

| 项目 | 本版建模值 |
|---|---|
| 两握持点 | 同高、同一条水平轴线，间距约 375 mm |
| 夹爪朝向 | 左侧 +X、右侧 −X；方向向量点积 −1，严格相对 |
| 两窗净开口 | 约 101 × 114 mm |
| 两窗平面夹角／窗心轴向间距 | 55°／约 114 mm |
| 钩头上下包络／杆径 | 约 134 mm／7.6 mm |
| 两个握柄截面 | 28 × 24 mm，便于使用相同的夹爪开度 |
| 初始棕／蓝两件间距 | 表面无相交，最小间距约 2.53 mm |

**初态面对面，不要求解题全程保持面对面。** 起步时可让左手稳定持窗、右手转动蓝件，尝试倾转钩头通过第一窗，再在窗间转向并通过第二窗。必要时两手配合调整相对姿态；若把两夹爪整个过程中都锁定为共轴反向，会把本来需要的旋转自由度限制掉。

本版的 U 形连接架会成为新的实体障碍，后续需要特别检查钩头第一次倾转时是否碰架，以及是否出现反向退回、侧绕或单次转动就脱出的捷径。缩小结构也会改变夹爪与窗框的相对净空，因此上一版的定性动作构思不能直接当成本版的完整可解证明。

**与精确 home 状态的区别：** 当前配置的 home 末端有小幅仰角，并非数学上完全反平行。本图沿用其名义抓持点位置与间距，以严格水平相对的朝向表达这次布局要求；灰色夹爪仍为占位模型，尚未用真实机器人求解此姿态，也未建立物理抓持。它是新场景首帧的静态建模方案，不是已验证的 `reset()` 画面。若要求六个手臂关节角也逐项保持 home 不变，应在该 FK 位姿下继续调整握柄安装角，而非声称本图已经复现了精确 home。

本次已检查握持点共轴、朝向相反、两件初始表面不相交，并实际渲染三个视角。模型和复现资料：[三维装配 GLB](../../../runs/test_results/claws_medium_opposed_concept_20260927/assembly.glb)、[候选参数及检查结果](../../../runs/test_results/claws_medium_opposed_concept_20260927/concept.json)、[建模／渲染脚本](../../../runs/test_results/claws_medium_opposed_concept_20260927/render_source.py)、[产物 SHA-256](../../../runs/test_results/claws_medium_opposed_concept_20260927/sha256.json)。

## 4. Hedgehog medium：为什么像破笼子？机制与理论解法

**反馈：** 看不清笼子结构，像破损笼子且不美观；似乎比 easy 更简单，需要解释机制和解法。

**实际结构：** medium 是 `oblique_gate`，使用冻结的木笼资产与 **10 根刺**的刺球；easy 是 `classic_3star`，并非同一个笼子简单调窄。[medium 定义](../../../topogym/tasks/hedgehog_in_cage/hedgehog_in_cage_medium.py)、[当前初始图](../../../runs/test_results/initial_scenes_20260927_01/hedgehog_in_cage_medium/hedgehog_in_cage/initial_frames/front_oblique.png)。

medium 的生成方法会先构造环形笼体和侧窗，再削去与预设解题运动扫掠体冲突的材料。目标窗的中心方向随高度倾斜；基础生成参数在上下有效窗高处分别偏转约 −14° 和 +14°。离散单元削切会留下阶梯、凹口和不规则边缘，因而容易呈现“破了一块”的观感。[生成代码](../../../topogym/assets/geometry/hedgehog_in_cage.py)与[资产报告](../../../assets/tasks/hedgehog_in_cage/seed_families_v1/oblique_gate/assets/asset_report.json)支持这一解释；资产报告记录笼体连通，所以至少不能把这种外观直接解释成运行中刚体断裂。

**设计机制：** 刺球在不同朝向下占据的空间不同；笼窗随高度偏斜，刺尖需要在转动和小幅平移中依次避开窗边。它的设计重点是带刺刚体的姿态通行约束，不是把球或笼子挤变形。

**理论解法／历史路线的直观解释：**

| 阶段 | 运动 | 目的 |
|---|---|---|
| 对准出口 | 初始倾斜姿态下稍向侧窗靠近 | 把一组刺对准可通过方向 |
| 进入斜窗 | 向外推进，同时小幅侧移、抬升和倾转 | 让领先的刺先越过窗边 |
| 窗边换向 | 球心停留在窗口附近，连续调整姿态及高度 | 给后续刺让出净空，避免一次直拔时被窗框卡住 |
| 撤出 | 所有刺均越过限制面后向外平移 | 完整分离，再完成放置与静置要求 |

历史[运动提案](../../../assets/tasks/hedgehog_in_cage/seed_families_v1/oblique_gate/motion_proposal.json)包含 `initial_adjustment → approach_oblique_gate → lateral_oblique_turn → withdraw`：笼体局部 X 从约 34 mm 接近至 63 mm，在约 65–78 mm 的窗边区域多次改变姿态，最后撤至约 170 mm。可结合[历史完整演示](../../../demos/hedgehog_in_cage/varaition_oblique_gate/front_oblique/2026-09-21_oblique_gate_restored_v1_front_oblique.mp4)理解这些动作。这些是旧方案的路线证据，**不等于最新 simulator 已完成同一路线验证**。

**难度答复：目前不能证明 medium 比 easy 更难。** 沿成功路径削材料只提供一条通道，并不会自动排除更简单的其他通道；当前初态也已靠近侧窗。因此“看起来更容易”的反馈有充分理由需要重查，不能用刺更多或有历史成功视频来反驳。

**后续方向：** 把目标出口重整为边界清晰、连续且美观的斜窗，保留可读的完整笼体；同时检查直拔／单次旋转是否就能逃出。再以必要姿态变化、有效净空和真实执行比较 easy / medium，决定加强约束还是重新分档；重整后的视觉网格和碰撞几何必须一致。

### 4.1 新概念：均匀纵向椭圆窗，先抬到中央再转出（用户已确认）

**用户新反馈：** 将“柱子 + 不规则镂空”的侧壁改为均匀分布、接近笼子全高的椭圆镂空，让可转出刺球的高度范围集中到中央最宽处。本节是按这一方向制作的独立概念模型；当前正式 medium 仍是前述 `oblique_gate`，尚未替换。

**建模方案：** 用一个连续圆筒壳开出 **6 个相同的纵向椭圆窗，圆周方向每 60° 一个**。窗边连续光滑，中间宽、两端窄；不再按一条预设解法削出不规则缺口。现有十刺球的网格和尺寸保持不变，只调整本图中的摆放朝向。笼体顶部与底部封闭，避免直接从顶端取出。

#### 低位初态构型

![Hedgehog medium 椭圆窗笼：低位刺球的静态概念图](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/initial_front.png)

刺球球心位于笼体中央以下约 54 mm。此高度的窗口宽约 50.8 mm，窄于 54 mm 球核，不能保持这个低位直接横向取出。图示尚未加入机械臂和抓持状态；靠近底部的刺与笼体有约 2 mm 最小静态间距，并非已验证的重力静置初态。

#### 中央位置对照

![Hedgehog medium 椭圆窗笼：球心抬至中央后的独立静态构型](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/center_front.png)

这张图把同一刺球放到笼体中部，表示应探索的转出区域。它与上一张是两个独立摆放的静态画面，**不是机械臂已执行抬升或转出的录像**。要完整出去，还需要调整十根刺的朝向，并沿窗边连续转动和平移。

侧面外观见[斜视图](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/initial_oblique.png)，中央位置见[中央斜视图](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/center_oblique.png)。所有图片均由尺寸明确的网格在 Nyx + compact_lab 中渲染。

#### 窗口收窄的几何解释

![椭圆窗低位受阻、中央变宽的尺寸示意](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/height_constraint.svg)

| 参数 | 本概念图取值 | 目的 |
|---|---|---|
| 笼体高度／外径／内径 | 240／180／164 mm | 容纳原尺寸十刺球，并留出笼内抬升空间 |
| 壁厚 | 8 mm | 连续完整的笼壳；窗口为实际贯穿孔 |
| 窗口数量与间隔 | 6 个／60° | 均匀分布，采用相同高度限制 |
| 椭圆窗高度 | 224 mm | 覆盖约 93% 笼高；上下各留 8 mm 完整边框，避免窗尖切断端部 |
| 中央最大窗宽 | 58 mm | 比 54 mm 球核仅宽 4 mm，限制可通过高度 |
| 初始球心高度 | 相对笼中央 −54 mm | 此处窗宽约 50.8 mm，低位球核受阻 |

“与笼子等高”在本图中实现为接近全高的长椭圆，并保留很薄的上下边框。笼子的内外径、窗口数量和宽度是用于讨论的候选参数，不是已冻结的正式任务参数；这里收窄的是**出口与可通过高度**，并未等比缩小刺球。

令 `z` 为相对窗口中央的高度（单位 mm），本图的窗口宽度为 `w(z) = 58 × sqrt(1 − (z / 112)²)`。仅以球核直径 54 mm 为必要条件，需要 `w(z) ≥ 54`，得到球心通过限制面时的高度约束 `|z| ≤ 40.9 mm`。也就是先把球心送到中央约 82 mm 高的区域内，才有继续转出的可能；更靠近上下端的窗口即使姿态改变，也容不下球核。

这不是“只有一个数学高度点可通过”，而是一段围绕中央的通行带。刺、壳体厚度、窗口曲率以及夹爪会进一步限制实际空间；上述球核条件不能单独证明存在完整解法。若希望通行带更集中，可以继续小幅收窄中央窗宽，但须同时检查是否仍能让十根刺连续转出。

**已完成与下一步：** 当前笼体网格连通且封闭，两个展示姿态均无刺球—笼体表面相交；从低位到中央的 19 个平移采样姿态也均无表面相交。这只是静态几何检查。后续需验证真实夹爪能抓持和抬升、连续转出路径可行，并排查其余五扇窗是否存在更简单的捷径，再评价是否达到 medium 难度。

模型和复现资料：[低位装配 GLB](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/assembly_initial.glb)、[中央装配 GLB](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/assembly_center.glb)、[参数与静态检查](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/concept.json)、[建模／渲染脚本](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/render_source.py)、[产物 SHA-256](../../../runs/test_results/hedgehog_medium_ellipse_concept_20260927/sha256.json)。

## 5. Buzz Wire：起终点小支架的用途与整体抬高

**2026-09-28 用户纠正并要求实施：** 上轮只做整体抬高，未完成其要求的端点结构修改。当前要求是端点连接块必须细到能穿过工具环，移除工具下的小托架，环与握柄直接放在底板上；底座提高到原机械臂可接近抓取。以下“保留端部固定与必要被动支撑”的旧答复不再作为新版本的建模要求。实施与新录像见[本轮记录](../../../runs/test_results/buzz_deck_rest_20260928/README.md)。

**反馈：** 如果小支架用于支撑环和握柄、方便夹爪抓持，可以进一步整体抬高底部。

**答复：** 当前端部结构承担两类作用：导线的端部安装／挡块固定线路并防止环直接滑出；旁边的木托承托工具，让起点可拾取、终点可放回和松爪静置。F2 终点还使用环部 V 形支撑及颈部／柄部支撑。它们有实体碰撞，不只是装饰，也不全是同一种“支架”。[支撑生成代码](../../../topogym/assets/geometry/buzz_wire_3d.py)、[任务说明](buzz_wire_3d_zh.md)。

当前 medium 冻结布局已设置 `base_elevation_m = 0.04`，即整体抬高参数为 40 mm；这不代表抓持净空已经满足本次要求。整体抬高有助于增加相对桌面的进爪空间；如果问题是木托紧贴握柄，则还需调整托座形状或支撑位置，因为整套结构同步平移不会改变木托与握柄之间的距离。

**修改要求：** 进一步抬高底部及工作区，保留端部固定与必要的被动支撑；检查夹爪从桌面上方接近、闭合及提起时的完整空间。高度以机器人可达和净空检查决定。注意当前三档直接读取冻结 `layout.json`；仅修改 Task 中同名默认参数不会覆盖该文件。应同步更新实际布局资源中的底座、导线、托座与工具初始位姿，并复验终点放回。[medium 实际布局](../../../topogym/assets/resources/variations/buzz_wire_3d/F2_compact_toy_s70_home_lab_v4/layout.json)、[布局读取逻辑](../../../topogym/tasks/buzz_wire_3d/common.py)。

## 6. Buzz Wire medium：已有方案，为什么没有初始化视频？

**已有实现，也已经尝试录制。** medium 使用冻结的 F2 `over_under_eight` 多段线路，实际包含入口梳形段、分层 8 字段、前侧竖向 W 段和出口弯曲段。[medium 定义](../../../topogym/tasks/buzz_wire_3d/buzz_wire_3d_medium.py)。

缺片的实际过程是：

1. 首批 Buzz 三档在碰撞角色识别处遇到 primitive 参数长度不一致的启动错误。该公共问题已修复；后续 easy / hard 补录通过。
2. medium 重试在 reset 保存引擎状态时遇到 `CUDA_ERROR_OUT_OF_MEMORY`，没有完成可交付的初始化录制。[失败报告](../../../runs/test_results/initial_scenes_20260927_retry_01/buzz_wire_3d_medium/buzz_wire_3d/report.json)。
3. 再下一轮设置空闲显存门槛后，等待超时，尚未启动该轮 simulator。[重试队列报告](../../../runs/test_results/initial_scenes_20260927_retry_02/summary.json)。

所以索引应写“已开发，补录失败／待可用显存重试”，不能写成未开发。可以查看[历史 F2 完整演示](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/front_oblique/F2_home_lab_v4_full.mp4)，但它不替代这次最新源码的初始化 recording。后续在运行条件满足后从固定源码重新录制并核对来源；不会用旧 demo 冒充新片。

## 7. Knot Untying：整体上移一档，补一个更简单的 easy

**反馈：** 当前 medium 已经很难；整体难度往上调一级，easy 留给最简单的绳圈结，即一个绳圈在某处彼此重叠两次。

**按本次要求记录的迁移关系：**

| 新正式档位 | 来源／目标 | 状态 |
|---|---|---|
| easy | 新建最简单的局部两次重叠绳圈 | 待设计和实现；先留空，不沿用旧 easy 视频 |
| medium | 当前 easy：`overhand_trefoil` | 待迁移定义及对应元数据 |
| hard | 当前 medium：`figure_eight` | 待迁移定义及对应元数据 |
| 正式三档之外 | 当前 hard：`double_overhand` | 建议留作历史／实验候选，不占第四个正式难度 |

现有定义见 [easy](../../../topogym/tasks/knot_untying/knot_untying_easy.py)、[medium](../../../topogym/tasks/knot_untying/knot_untying_medium.py)、[hard](../../../topogym/tasks/knot_untying/knot_untying_hard.py)。

新 easy 应先明确两处重叠的上下穿越次序、两端走向以及预期的一步或少步解法。“画面上重叠两次”暂作为造型需求，不据此直接命名成某个数学结型，也不能让初态自穿透。应做成容易看懂、可抓持、所需动作明显少于新 medium 的实例，并检验是否完全无需操作就会松开。迁移时必须同步 family、说明、默认别名和录制身份；不能把旧 MP4 仅改文件名后称为新档位最新证据。

## 8. Slotted：为什么没有开始录制？

**实际上已经尝试；尚未生成通过检查的初始化视频。** 需要按入口分别看：

| 入口 | 开发状态 | 缺片原因 |
|---|---|---|
| easy / `large_ring` | 待开发 | 目前是正式档位占位，媒体应留空 |
| medium / `middle_ring` | 待开发 | 目前是正式档位占位，媒体应留空 |
| hard / `original_scale` | 已接入 | 首批及重试遇到 CUDA 分配／设备错误；后续排队等空闲显存 |
| `clearance36` | 已接入的实验候选 | 已尝试但发生原生 CUDA 错误；后续重试排在 hard 之后，不计入正式三档 |

首轮和重试日志包含 OOM，以及原生进程中止（`process exit -6`、CUB `cudaErrorInvalidDevice`）。显存压力已有记录，但不能把所有 `InvalidDevice` 都未经排查地认定为同一个 OOM 根因。截至本页截点，hard 的队列状态是 `running`，实际处于等待 GPU 显存阶段，并非正在推进物理步；clearance36 是 `pending`。

证据：[首轮结果](../../../runs/test_results/initial_scenes_20260927_01/summary_first_attempt.json)、[hard 重试日志](../../../runs/test_results/initial_scenes_20260927_retry_01/slotted_post_ring_hard.log)、[实验候选重试日志](../../../runs/test_results/initial_scenes_20260927_retry_01/slotted_post_ring_clearance36.log)、[后续队列](../../../runs/test_results/initial_scenes_20260927_retry_02/summary.json)。

后续优先补正式 hard；easy / medium 需要先完成实际任务定义才能录制。等待超时是录制未完成，不能记作任务物理验收失败；也不能把仍在等待的条目写成已录制。

## 后续修改清单

| 项目 | 本轮记录的要求 | 完成条件 |
|---|---|---|
| 索引范围 | 正式 39 行；兼容／实验另表 | 三档计数明确，未开发与录制失败分别显示 |
| Orbits hard | 紧凑绳圈，末端木柄外置，排查初始弹开 | 四环机制保留，初态稳定，尺寸与完整解法相容 |
| Claws 全档 | 原夹爪模型不变；segment0 已各夹住一件，中央两件卡住 | reset 首帧已持件且有效互锁，无首步补抓、瞬移与穿模，短程稳定 |
| Claws medium | 已选第 3.2 节面对面方案：锐角双窗、后置 U 架及轴向握柄、蓝色 J 钩 | 适配真实夹爪，两次必要定向，存在可执行路径并排查单次转动捷径 |
| Hedgehog medium | 第 4.1 节均匀纵向椭圆窗已确认（深色实木纹理），限制到中央高度后转出 | 完整窗边、真实夹爪可抓持抬升、存在连续解法，排查其他窗捷径并复核难度 |
| Buzz 全档 | 工作区进一步整体抬高并检查托座 | 可接近、可抓取、可放回，实际冻结资源同步更新 |
| Buzz medium / Slotted hard | 完成当前缺失的初始化补录 | 当前源码快照、短程运行及视频解码检查通过 |
| Knot 三档 | 新 easy；旧 easy → medium；旧 medium → hard | 定义、元数据、别名及视频来源一致；旧 hard 不占正式三档 |

所有受改形或初始化合同影响的旧短片仅作为旧版本参考；实现之后需重新录制对应实例，逐项保存实际源码身份。本文没有把待实施要求写成已完成，也没有用历史完整演示替代当前初始化验证。


## 9. 本轮开发与验证（2026-09-27）

**本轮结束状态：正式主表 39 项中，32 个已开发入口全部具有通过检查的初始化录像；6 个待开发、1 个阻塞入口保留空白。附表另有 6 个兼容／实验入口，其中 5 个已录制、1 个阻塞。合计 37 组、136 个 MP4；视频哈希、完整解码结果、相机同步与 390 条索引链接核对通过，未留待刷新的旧版任务定义行。**

源码改动前的副本与测试报告保存在 [本轮工作目录](../../../runs/test_results/scene_feedback_development_20260927/)。所有视频继续由公共 RecordingSession 录制；原始机器人模型未修改。以下区分已落地的模型与尚未完成的解法资格。

| 项目 | 本轮实现 | 验证边界 |
|---|---|---|
| Hedgehog medium | 六个相隔 60° 的纵向椭圆窗；外径 180 mm、高 240 mm，窗宽 58 mm、高 224 mm，上下封闭端厚 8 mm；复用原 10 刺球；笼体使用带 UV 的深色木纹贴图 | 31 个抬升采样位姿无碰撞；球核在中间能通过、在低处不能通过；初始化录制通过。完整出笼及机器人抓持解法尚未验收 |
| Buzz 三档 | 各自工作区整体再抬高 40 mm；实际冻结线路、起终点托座和握柄同步抬升 | 三档初始化录制通过；轨道抬升一致性单测通过；完整机器人取放还需专门验证 |
| Knot | easy 新单绳圈、颈部两处重叠；原 easy 变 medium；原 medium 变 hard；原 hard 保留为 `knot_untying_double_overhand` 实验入口 | 新 easy 两处交叉、绳体最小间隙约 2.3 mm；它是可消去的两交叉重叠，不宣称新的闭合数学结型；新版物理录制见索引 |
| Orbits hard | 保留四环，框架采用 0.85 比例；绳长约 0.800 m，木柄局部 X=0.410 m，绳路不再越过木柄中心 | 比旧 hard 约缩短 53%；加大木柄转弯和柱边折返半径，并提前平滑抬升绳路；仍有初始松弛，见下文定量结果；完整解法所需长度未验收 |
| Claws | medium 改为 55° 锐角双窗、后置 U 架和独立蓝色 J 钩；三档均声明任务自己的初始手臂／手指姿态及闭合控制目标；hard 的 claw 增加 30×28×24 mm 平整握柄块，夹爪模型不变 | medium 两件初态表面间隙约 2.5 mm，直接轴向拔出被几何阻挡；三档 0.1 s GPU 初始化录像及 0.5 s CPU 持件、segment0 回溯检查通过；两次转向的必要性和完整路径仍未验收 |
| 索引 | 正式主表 39 行；附表保留兼容／实验入口，新加入旧 Knot hard 后附表为 6 行 | 逐行保留实际录制源码来源；未开发、失败、旧版待刷新分别标明 |
| 缺失录制 | Buzz medium、Slotted hard 已补录 | 当前录制为 reset 后 0.1 s，不能替代完整任务演示 |

Claws 首次验证发现现有落地区域选择器只尝试紧邻物体的候选区域，物体改为机器人正前方预抓持后，该区域与机器人安装底座范围重叠而被整侧拒绝。已补充沿分离方向外移至底座之外的选择逻辑，保留原有分离边界和终点规则；这一修复不修改夹爪建模。

本轮新增几何检查见 [测试文件](../../../tests/unit/test_initial_scene_feedback.py)，已有相关测试结果见 [日志](../../../runs/test_results/scene_feedback_development_20260927/unit_existing.log)，新增检查结果见 [日志](../../../runs/test_results/scene_feedback_development_20260927/unit_feedback.log)。实时媒体与失败诊断统一链接到 [39 项正式初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。


### 9.1 当前真实首帧与录像

以下来自实际任务 reset；Claws 中是原 ALOHA 模型，物件保持为独立刚体。没有把概念图中的灰色代理夹爪接入任务，也没有使用固定焊接或 grasp assist。实际手指在接触宽度初始化，控制目标为原夹爪允许的闭合位置；这一闭合预紧目标进入统一历史并随 segment0 回溯恢复。

| 当前版本 | 首帧 | 初始化 MP4 |
|---|---|---|
| Hedgehog medium / 深色实木椭圆窗 | [front_oblique](../../../runs/test_results/initial_scenes_feedback_20260927_a/hedgehog_in_cage_medium/hedgehog_in_cage/initial_frames/front_oblique.png) | [front_oblique](../../../runs/test_results/initial_scenes_feedback_20260927_a/hedgehog_in_cage_medium/hedgehog_in_cage/branch_000/videos/front_oblique.mp4) · [agentview](../../../runs/test_results/initial_scenes_feedback_20260927_a/hedgehog_in_cage_medium/hedgehog_in_cage/branch_000/videos/agentview.mp4) |
| Claws medium / 相对夹爪、锐角双窗与 J 钩 | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_d/interlocked_claws_medium/interlocked_claws/initial_frames/cam_high.png) | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_d/interlocked_claws_medium/interlocked_claws/branch_000/videos/cam_high.mp4) · [cam_low](../../../runs/test_results/initial_scenes_feedback_20260927_d/interlocked_claws_medium/interlocked_claws/branch_000/videos/cam_low.mp4) |
| Knot 新 easy / 两次重叠 | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_b/knot_untying_easy/knot_untying/initial_frames/cam_high.png) | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_b/knot_untying_easy/knot_untying/branch_000/videos/cam_high.mp4) |
| Orbits hard / 紧凑绳路与外置木柄 | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_d/orbits_hard/orbits/initial_frames/cam_high.png) | [cam_high](../../../runs/test_results/initial_scenes_feedback_20260927_d/orbits_hard/orbits/branch_000/videos/cam_high.mp4) |

![Hedgehog medium 实际初始化首帧](../../../runs/test_results/initial_scenes_feedback_20260927_a/hedgehog_in_cage_medium/hedgehog_in_cage/initial_frames/front_oblique.png)

![Claws medium 实际初始化首帧](../../../runs/test_results/initial_scenes_feedback_20260927_d/interlocked_claws_medium/interlocked_claws/initial_frames/cam_high.png)

### 9.2 验证结果与仍需处理的项目

- **Claws：** 三档都通过了 0.5 s 持件和同一 episode 的 segment0 回溯；关节、指距、两件物体位姿和闭合控制目标均恢复。没有凭此宣称完全静稳：相对抓持点位移约 0.2–1.5 mm，hard 仍出现最大约 17.3° 的角度调整，应继续改善握柄内的抗转稳定性。[逐档数据](../../../runs/test_results/scene_feedback_development_20260927/claw_segment0_checks.json)。
- **Orbits：** 初始四面体主伸长相对 1 的最大偏差由旧版约 57.2% 降至 15.9%；0.1 s 内最大向上位移由约 52.5 mm 降至 18.0 mm。不过最大总位移仍约 49.9 mm，主要转为平面内收缩，不能宣称已消除弹开或完成静稳初始化。材料直线参考构形、弹性参数和阻尼未改变；下一步仍需物理松弛初态及完整绳长需求验证。[新旧定量对照](../../../runs/test_results/scene_feedback_development_20260927/orbits_comparison.json)。
- **新机制资格：** Hedgehog 椭圆窗的完整连续出笼路线、机器人抬升与旋转解法，以及 Claws medium 是否必须两次定向、是否存在反向退出或单次转动捷径，仍待验证；初始几何检查和几步录像不能替代这些结论。
- **源码与测试：** [最终相关单测](../../../runs/test_results/scene_feedback_development_20260927/unit_final.log) 57 项通过；追加的 [hard 握柄资产声明检查](../../../runs/test_results/scene_feedback_development_20260927/unit_hard_grip.log) 通过。Easy/medium Claws 因共享文件仅更新 hard 分支，另做了[当前资产逐字节与初始关节一致性核对](../../../runs/test_results/scene_feedback_development_20260927/claw_asset_equivalence.json)，保留其对应的真实录制来源。

录制来源是逐行的固定源码快照，不是把整个目录描述成一次运行。当前 MP4 的完整解码、SHA-256、相机同步、首帧哈希和链接检查见 [交付核验](../../../runs/test_results/scene_feedback_development_20260927/delivery_audit.json)。

后续 scripted policy 实施已将 Claws 持件检查延长到 2 s，并补充位置/转角、半时间步、segment0 恢复与有限几何路线搜索。两个 medium 仍未取得完整解题资格；此前 0.5 s 初始化检查不能替代新的抓持门槛。见[首轮实施与证据](../../../runs/test_results/hedgehog_claws_policy_20260927/README.md)。
