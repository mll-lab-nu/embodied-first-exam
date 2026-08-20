# rope_winding：绳绕柱两圈 + 放置

任务书（`docs/develop/TopoGym_tasks.docx`）§2.4「绳子绕柱（0 → 2 圈）」的实现。
2026-08-11 新建。

## 1. 任务定义

绳的一端由固定端子锚定，另一端是工业插头，初始坐在出生端口里。夹爪抓插头，
沿一条连续的环绕轨迹绕柱 `winding.turns` 圈，然后把插头插进不远处的目标端口。

- **柱底固定、柱顶是改变 winding 的唯一 gateway。** oracle 全程把插头保持在
  柱顶以下（两圈爬升到 z=0.054，柱顶 0.070），所以圈数只能靠绕、不能靠越顶。
  验收里 `below_post_top` 这一项就是查这个：抬过柱顶的轨迹不算缠绕。
- **方向敏感。** winding number 带号：`ccw` 目标 +2，`cw` 目标 −2。
  `task.winding.direction=cw` 跑出来的就是任务书要求的 contrast pair —— 同样的抓取
  位形、镜像的轨迹、同样的放置终点，只有拓扑相反。
  （方向是 task 键不是 run 键：`run_configs/default.yaml` 的判据是「同一份 task/env
  配置配上不同的 run.* 应当产生相同的物理」，换方向直接换掉整条轨迹。）

## 2. 为什么新建任务而不是改 cable_routing

cable_routing 是任务书 §2.2 的变体（线缆从障碍物哪一侧通过），有自己的验收基线和
回归史；绕柱圈数是另一种空间关系（§2.4「围住谁、绕了几圈」）。所以场景装配复用、
任务语义分开：

| 层 | 做法 |
| --- | --- |
| 资产与场景装配 | 全部复用。`RopeWindingSceneBuilder` 是 `CableRoutingSceneBuilder` 的子类，柱 / 固定端子 / 插头 / 平嵌端口都是同一组 prefab，后端接缝（锚定带、跟随带、`rest_shape` 分支）一行不改 |
| 材料 | 单源 `prefabs.rope_fem.*`，与 untangle / cable_routing 同值 |
| oracle | 新写。`planning/rope_winding_planner.py`：单柱螺旋，不是手写多桩路线 |
| 判据 | 新写。`supervision/rope_winding.py`：带号 winding number，不是「在桩的哪一侧」签名 |

`WindingSpec`（`task.winding` 的读取，含符号约定）放在 planner 里，verifier 从那里
导入。方向是反的话两边就会对不上，而这个任务的全部意义就在符号上，所以只允许有
一处定义。（依赖方向是被现状定的：`supervision/cable_routing.py` 本来就 import
planning。）

## 3. 线圈化的构造性规避

> **先澄清一个容易读错的地方：`rest_shape` 说的是无应力构型，不是可见形状。**
> 两种取值下出生顶点位置完全相同——都是那条弧，看上去都是弯的。差别全在看不见的地方：
> 绳是「被掰成弧、一直想弹直」（存着弯曲能，`straight`），还是「天生就是这个弧、
> 待着很舒服」（零弯曲能，`spawn`）。钢尺掰弯会回弹，电话线安心保持卷曲——
> cable_routing 的螺旋正是因为我们把布线弧烤进了静止形，把它做成了电话线。

cable_routing 的螺旋（"电话线"）根因链见 `../rope_backend_migration_zh.md`：
FEM 的静止构型 = 出生路线，出生路线带固有曲率 κ₀，两端受约束 + 富余长度，
能量极小态就是螺旋。本任务在 formulate 阶段就把三个因子逐个拆掉：

| 因子 | 本任务的做法 | 数值 |
| --- | --- | --- |
| 静止形失配 | 出生路线是单段大半径圆弧，κ₀ 均匀且小，没有孤立紧钩 | R=0.20 m（κ₀=5/m）；cable 出事时尾部钩形是 R=0.027 m |
| 静止形语义 | `rope.fem.rest_shape: spawn`（2026-08-20 由 `straight` 改回，与实际运行对齐） | 见下方「直杆映射的退化」：`straight` 从未真正生效过 |
| 富余长度 | 绳长按 oracle 绷紧路径的最大需求定 | 0.628 m vs 最紧需求 0.553 m，富余 0.075 m（12%）；cable 出事时是 0.119 m（19%） |
| 自由跨距 | 锚点 / 柱 / 目标口彼此靠近，富余没有成圈的空间 | 锚点↔柱 0.188 m，柱↔目标口 0.164 m |

富余不能再压：`x1.08` 只剩 0.027 m（<5%），绳会绷到跟锚定带较劲。

### 3.1 直杆映射的退化（2026-08-11 首次 GPU 运行暴露）

`rest_shape: straight` 的实现是把管网格的每个顶点投影到出生中心线，取
（弧长, 法向偏移, 副法向偏移），再沿 +x 摊平成直管。第一次真正跑到这条路径时
libuipc 拒收：`determinant of the tetrahedron is non-positive (-1.26e-9)`。

原因是投影**丢掉了沿切向的残差**。连接器出线口那里中心线有近 90° 的硬拐角，
拐角外侧一整个楔形区的顶点投影落点都是同一个角点，于是被赋予同一个弧长坐标——
那块区域在直管里被压成零厚度，里面的四面体退化并翻转。

修法是把切向残差加回弧长：`s = 落点弧长 + rel·切向`。落点落在线段内部时该残差
恒为零（投影本来就正交），所以只在拐角处起作用，正是需要的地方。离线验证：
沿管的每条纵向棱线弧长严格递增（无折叠），内部点弧长误差从 3.7e-5 降到 5.2e-7。

同时加了兜底：注册前用 `entity.elems` 逐个算四面体定向，与出生网格比对；一旦仍有
翻转，打印数量与所在弧长区间并**退回 `rest_shape=spawn`**，不再让 C++ 断言中止整个
run。本任务的出生弧本来就平缓（κ₀=5/m），静止形只是保险带，退回不影响主要防线。

**2026-08-12 实测**：修复后仍有 **1/8430** 个四面体翻转，位置在弧长 0.6732–0.6752 m
（全长 0.7067 m），正是插头出线口那个尖角。兜底生效，本任务实际跑在 `spawn` 上。
立案不再深挖：出生弧平缓，静止形收益小于再改映射的风险；等 cable_routing 要用
`rest_shape=straight` 时一并解决。

**2026-08-19 复测**：插头改侧躺后老的尖角没了，翻转点换到了另一端——**1/12683**，
弧长 0.0303–0.0326 m（全长 0.7414 m），即固定端子出口那个 8 mm 半径的 U 形掉头弯
（`with_end_entries` 的 `arc_radius = max(0.008, 2*rope_radius)`，等于绳直径）。
兜底照旧生效。

**2026-08-20 配置对齐**：`rope.fem.rest_shape` 改为 `spawn`。理由是这条路径两次实测
都被兜底拦下，任务的全部历史验证都建立在 `spawn` 上，而 `rope_contract` banner 一直
印 `straight`——判据与实际不符本身就是要修的东西。同一轮把入口弧的采样加密到 10°
（见 §3.3），翻转条件很可能已经不成立，但那样一来 `straight` 会在无人验证的情况下
第一次生效：绕柱段曲率差 36.8 → 41.7 /m（+13%）、弯曲能约 +28%，出生弧本身也从零能
变成存能。所以显式钉成 `spawn`，`straight` 另立实验。

### 3.2 出生态实测（里程碑 A，2026-08-11）

`runs/winding_a_spawn.log`，静置 600 步：

| 量 | 读数 | 含义 |
| --- | --- | --- |
| `rope_spread` | 0.2287 → 0.2351 | 600 步只舒展 6.4 mm，是预应力与重力下的正常松弛，不是卷曲 |
| `rope_jump` | ≈ 0.0000 | 无单步跳变，求解稳定 |
| `rope_minz_above_surf` | 恒 +0.0020 | 绳一直贴桌，没有悬空拱 |
| `winding` | +0.000 | 与离线预测的出生 winding 一致 |

对照 cable_routing：那条绳出生后自旋成电话线，并在释放实验里向锚定端回缩 20 cm。
本任务没有任何一项对应现象——**构造性规避成立**。

### 3.3 表皮镶嵌（2026-08-20）

用户报告绳从第一帧起表面就带一层密集的环状/螺旋纹理，不像电缆。

先排除着色：**平滑法线本来就是开的**。Genesis 的 `Surface.smooth` 默认为 True
（`options/surfaces.py:91`），`vis/rasterizer_context.py:922` 把它传给
`pyrender.Mesh.from_trimesh`，FEM 每帧经 `jit_render.py` 的 `update_normal_smooth`
按相邻面重新平均顶点法线。所以三角化的对角线方向不会在着色上显形，能显形的只有
几何本身；仓库里也没有任何 `smooth=` 的覆盖可调。

再确认渲染的是哪张皮：形变体的渲染面是**四面体网格的边界**（`fem_entity.py:92-116`，
取只出现一次的面），不是 OBJ 的原始三角化。但 2026-08-19 那次运行输入 4920 个面片、
输出 `Mesh faces on exterior boundary: 4920`，937 个 Steiner 点全在内部——tetgen 这次
没有在表面插点，两者重合。所以改管皮就是改画面。

出生网格的构造：`make_elastic_tube_mesh` 沿中心线每个采样点放一圈
`radial_segments` 个顶点，环与环之间连成四边形。

| 量 | 改前 | 改后 |
| --- | --- | --- |
| `radial_segments` | 12 | 20 |
| 截面偏离真圆 | 0.136 mm（管半径的 3.4%） | 0.049 mm（1.2%） |
| 周向面片弦 | 2.07 mm | 1.25 mm |
| 入口弧采样步长 | 30°（U 形弯是七边形） | 10° |
| 纵向弦高最大值 | 0.268 mm（在那个 U 形弯上） | 0.039 mm |
| 自由端最后 28 mm 环距 | 4.72 mm（绳体 3.54 mm） | 3.54 mm |
| 表皮顶点 | 2462 | 4502 |

三处成因分别对应三处改动：

1. **截面边数**。12 边形在 4 mm 管上的偏差是半径的 3.4%，周向弦 2.07 mm——轮廓
   与法线插值都在这个粒度上分档。改 20 边形后偏差 0.049 mm、周向弦 1.25 mm。
2. **入口弧的角步长**。这些点是在样条**之后**插入的，后面没有任何东西再去圆滑它们
   （`sample_polyline` 只做线性切分）。30° 采样等于一个七边形，弦高 0.27 mm，是周向
   面片误差的两倍，而且是一条纵向折痕；`parallel_transport_frames` 还要在每个这样的
   顶点上把环的框架转满 30°。改 10° 后弦高 0.030 mm，绳长 +0.4 mm。
3. **自由端的密度断层**。`reserve_endpoint_footprint` 原先无条件在两端各清出 28 mm，
   但侧躺插头（`connector.pose: flat`）的那一端**永远不回填**（`end_entry=None`），
   于是那 28 mm 被重采样成 6 × 4.72 mm，与绳体 3.54 mm 差 1.33 倍——位置正是夹爪
   合拢的那一段。改成只对将要插入 entry 的一端预留。

环距本身**不要求均匀**：弯得越急的地方环本来就该排得越密（入口弧 1.39 mm vs 绳体
3.54 mm 是对的）。判据是两个方向的镶嵌误差谁也不该明显粗于对方，即环距按局部曲率
折算的纵向弦高 `d²/8R` 不超过截面弦高。离线体检脚本见 §7。

绕柱段同理：柱面落位半径 24 mm，3.54 mm 环距在那里的纵向弦高是 0.065 mm；若为省
节点把环距放到 7 mm，该处会涨到 0.26 mm，正好在绕柱时显形。所以只加周向、不减环密。

表皮顶点 2462 → 4502，因此节点数会从 3399 涨到 6000 上下（Steiner 点数随体网格密度
走，具体值以第一次 GPU 运行的 tetgen banner 为准）。`safety_max_contact_nodes` 必须
同步——它是节点**绝对数**，2026-08-19 那次跑贴柱峰值 1476 / 3399 = 43%，同比例外推
约 2500，阈值按同样的一倍余量由 3000 提到 4800。

**这一轮只治静态几何。** 若实拍下来出生帧已经干净、但绳一动起来仍有细碎起伏，那是
另一层机理：渲染面的每个边界节点都是独立的 FEM 自由度，节点之间是直线段，平滑法线
在一张不规则且各自运动的三角网上平均，得到的就是细碎感。那一层由**体网格密度**
（`maxvolume`，当前 5e-8 并非约束，实际平均 tet 体积 2.9e-9）与求解器决定，加密表皮
帮不上——与 `cable_routing_element_design_zh.md` 附录 3 对「折线感」的归因是同一条。

## 4. 布局

单位米，task 坐标系（z=0 是桌面）。几何预算脚本见 §7。

| 元素 | 位置 | 说明 |
| --- | --- | --- |
| S（固定端子） | (−0.150, 0.100) | 绳的锚定端，视觉是工业端子；fixtures 里的桩体关闭，只提供坐标 |
| POST（绕线柱） | (0.020, 0.020) | 半径 0.012、高 0.070，喇叭底座；**collision: true**（绳缠在它上面，接触就是任务本身） |
| C（目标端口） | (0.150, 0.120) | 平嵌端口 + ConnectorLatch 捕获，离柱 0.164 m |
| 插头出生点 | (0.156, −0.157) | 出生弧的终点，离柱 0.224 m、离 C 0.277 m |

出生弧：圆心 (0.003, −0.029)、R=0.20、180°，从柱**南侧**绕过 —— 出生时不环绕柱，
winding number 从 0 开始（离线校验过，见 §7）。

缠绕轨道：半径 0.050（夹爪 + 插头法兰在柱杆外需要 ~0.04，留 1 cm 余量），
每圈爬升 0.012（1.5 倍绳径，让下一圈落在上一圈旁边而不是压上去），
每圈 8 个路点（45°/点，折线相对真圆最大偏差 3.8mm < 绳径）。
绳在张力下自己收落到柱面半径 0.016，轨道不需要贴柱。

### 4.1 耗时

一步 FEM+IPC 约 0.66 秒且没有已知有效的求解器提速旋钮
（`../fem_ipc_step_cost_zh.md`），所以**总时长 = 路径长 ÷ 指令速度 × 0.66 秒**，
唯一能动的是路径与速度。步数不再逐段手写，由「段长 ÷ 速度」算出来（整条路线匀速），
两档速度：

| 旋钮 | 值 | 理由 |
| --- | --- | --- |
| `wind_speed` | 0.0009 m/步 | 缠绕段绳正被拖上柱子，快了跟不上。cable 缠桩是 0.0005，这里 1.8 倍 |
| `travel_speed` | 0.0020 m/步 | 自由段绳只是跟着走，没有新接触要建立 |
| `min_segment_steps` | 40 | 防止插入这种 35mm 短段被算成几步猛冲 |

路点之外还有一段**固定开销**：`HandleDragPrimitive` 的抓取前置序列（开爪 → 接近 →
下降 → 闭合 → 保持 → 试提），由 `physical_handle` 的 `move_steps` / `gripper_steps` /
`close_hold_steps` 决定。它与任务语义无关，全程空载自由移动（插头与端口都是
`collision=false`），2026-08-12 从 240/90/60 降到 120/60/40，720 → 400 步。

当前完整预算（`tests/check_rope_winding_geometry.py` 每次都会打出来）：

| 段 | 步数 | 耗时 |
| --- | --- | --- |
| 抓取序列 | 400 | 4.4 min |
| 缠绕（16 个轨道路点） | 688 | 7.6 min |
| 自由移动 | 265 | 2.9 min |
| 静置 + 释放 | 120 | 1.3 min |
| **合计** | **1473** | **16.2 min** |

演进：初版每圈 12 点、逐段手写步数，2360 步（路点）+ 720（抓取）≈ 34 分钟；
改成两档速度 + 每圈 8 点后降到 20 分钟；砍掉抓取空跑后 16.2 分钟。

## 5. 判据

`supervision/rope_winding.py`：

- **有序中心线**：FEM 绳是无序四面体网格（tetgen 加内部点且不保持管的顶点顺序），
  所以先用 `tube_material_coords` 把**出生**节点位置投影到出生中心线，得到每个节点的
  弧长坐标，按弧长分箱。分箱是材料性的，之后任何时刻对每组当前位置取均值就是
  有序中心线。这个函数与 FEM 直杆静止形映射同一个（`world/rope.py`），两个用途一份实现。
- **winding number**：中心线各点对柱轴的方位角沿弧长 unwrap，累计角除以 2π，
  再加 canonical closure（从自由端沿短程回到锚定端的方位角）。两端都远离柱且低于
  柱顶，所以任何闭合路径都不会穿过柱、不会改变计数；和是整数（离散化误差内）。
- **成功** = |winding − 目标| ≤ `success.winding_tolerance` ∧ 缠绕段不高于柱顶
  ∧ latch 捕获 ∧ 终点位置误差在 `connector_tolerance_xy` 内 ∧ 原语没中止。

`--probe` 每 N 步打印实时 winding number，缠绕正常的 run 每圈涨 1；绳从柱上滑脱的
run 会停住或回落。每圈结束还会单独打一行 `turn_complete`。

## 6. 绳↔夹爪接触

里程碑 B 的 viewer 里绳直接从指垫中间穿过去。这不是求解器漏了接触，是**当前设计刻意没有
这个接触对**：机械臂以 `needs_coup=False` 建入场景，而 IPC 耦合器读到它就整体跳过
（`genesis/engine/couplers/ipc_coupler/coupler.py:207`），机械臂从未进入 IPC 场景。

### 6.1 以前为什么关着，现在为什么能开

关的理由有两条，一条已经过时，一条仍然成立：

- **PBD 时代的实测**（`../untangle/untangle_connector_flyout_debug_zh.md` §2 的 A/B 表）：
  开接触两次把绳撕烂。机理是「kinematic 焊接每步把粒子按回原位」和「刚体手指同时推同一批
  粒子」两个写位置的人对着干，位置突变被 PBD 反推成巨大速度。
  **这条不再适用**：现在绳端由 IPC 内部的 `SoftPositionConstraint` 跟随带持有，手指接触也在
  同一个 IPC 能量里，由 Newton 一起解——是一个变分问题里的两项，不是两个外部写位置的人打架。
  而且夹爪夹的是**刚体插头**，焊接管的是插头，不是绳节点。
- **benchmark 设计**（设计文档 §3.5）：抓取是 kinematic weld，抓取成功率恒 100%，
  把低层控制误差排除出评测变量。**这条仍然成立**——所以插头的抓取机制一行没动，
  这次打开的只是「绳能不能看见手指」。

### 6.2 选型：只注册两根手指

Genesis 1.2.1 有两条把机械臂接进 IPC 的路：

| 路 | 机制 | 结论 |
| --- | --- | --- |
| 整条臂 `external_articulation` | 关节级耦合，IPC 回写 `qpos` | **否决**：`set_qpos` 被禁（`rigid_entity.py:3764`），本仓的 IK 控制器直接失效；关节刚度还是硬编码的 |
| **`two_way_soft_constraint` + `coup_links`** | 只有列进 `coup_links` 的 link 进 IPC（`coupler.py:388-392`），作为 ABD 体每步被钉到 Genesis 给的位姿上 | **采用**：一行材质，其余臂体仍归刚体求解器，IK 保持完全控制 |

`coup_links` 是**包含列表**（列谁谁进 IPC），所以「只要手指」正好是它的一行用法。
（`untangle_continuous.py` 里那条注释担心的是反向用法——保留整臂耦合但排除手指——
那才需要枚举除手指外的所有 link。）

开关是 `physical_handle.robot_rope_contact`，取值 `off` / `fingers`，默认 `off`：
cable_routing 与 untangle 三个任务的配置里没有这个键，行为逐位不变。
用字符串而不是布尔，是因为 `untangle_continuous` 那个 `robot_rope_contact: true` 布尔在 FEM
下会退化成「交给耦合器自动选」，而自动选对机械臂给的正是被否决的 `external_articulation`
——布尔表达不了「哪一种接触」。

手指名复用 `physical_handle.finger_links`（`configure_gripper_contact_friction` 已经在用的
同一份），不新增第二处名字。

### 6.3 一个不免费的副作用：手指与柱之间不再有碰撞

柱在 IPC 里是 `ipc_only`；手指注册后也成了 IPC 委托体。刚体碰撞器只在**两边都被委托**时才
丢弃这对（`collider.py:405`），而本后端的 IPC 选项里 `enable_rigid_rigid_contact=False`
（为了柱的 shaft + 喇叭底座那对故意互嵌的静态体，见 `fem_ipc.py:139`）。两者叠加的结果是
**手指与柱之间不再有任何碰撞**。

几何上本来就够不着（轨道半径 0.050，柱杆半径 0.012；喇叭底座半径 0.035 但很矮，手指在
z ≥ 0.030），但这是**几何保证不是求解器保证**，要在 viewer 里确认手指没穿过柱底喇叭。
若确实穿了：把 `winding.wind_radius` 抬到 0.065，或把底座改成非 IPC 的装饰体 + 单独的碰撞代理。

### 6.4 保持不变的部分

插头仍然 `collision=false` + `needs_coup=False` + kinematic 焊接。它必须留在 IPC 之外：
绳端节点按设计就住在插头内部，把它拉进 IPC 会让接触势垒把绳从插头里顶出来
（`cable_routing.py` `_add_endpoint_handle` 的注释）。

## 6.5 扭转与转环

成功例的绳最后是**拧着**插进 C 的。成因与绳↔夹爪接触无关，是另一条独立的链。

### 6.5.1 成因：朝向冻结 + 切向随轨道旋转

插头在整个绕柱过程中朝向被冻结。`RigidAttachment.sync()`（`primitives/attachment.py:136-148`）
每步用 `yaw_quat(self.yaw + child_yaw_offset)` 写 `set_quat`，而 `self.yaw` 只在 `attach()` 时
设一次——`set_yaw`（:104）在这次改动之前全仓库零调用。

绳端连同它的**材料标架**被刚性带着走（跟随带读 `link.get_quat()`），可是绳在插头处的**切向**
随轨道每圈转 360°。两者的差额就是扭转：**每绕一圈往绳里灌一整圈**，两圈两圈；另一端锚死在
固定端子上，扭转跑不掉，只能拧着插进目标端口。

这不是 bug，是「手不转、端着绳绕柱」的忠实模拟——真人绕线要么转手腕，要么让接头打转。

**手腕替代不了**：Franka joint7 限位 ±2.8973 rad = ±166°（`panda.xml:9-10`，joint7 无显式
range，继承 class 默认），从 −45° 的 home 出发总行程 332°，连一圈都不够，两圈需要 720°。

### 6.5.2 走过的弯路：转插头（已撤销）

第一次尝试是让**插头**随轨道角原地自转 45°/点来抵消扭转。实测**反而让绳与夹爪缠得更厉害**。

原因很直接：绳端是焊在插头上的，转插头等于把绳端贴着**静止的指垫**拧——那正是最容易把绳
卷上指垫的动作。扭转要在绳端与插头**之间**释放，而不是把整个插头连同绳端一起转。

2026-08-12 撤销，`winding.swivel` 键一并删除。留在这里是因为它解释了为什么解法在下一节
那个位置，而不是更靠外的位置。

### 6.5.3 解法：两端的跟随带当作转环

`rope.fem.follow_swivel: true`。跟随带原本给绳端每个节点都指定了目标位置，等于**扭转夹具**：
绳端连绕轴的转角都被定死。打开后它仍然定住绳端沿轴和横截面上的位置，**只是不再约束绕轴的
转角**——真正的转环，而且转环在它该在的位置：绳端与插头之间。

实现在 `world/rope_backends/fem_ipc.py` 的 `_FollowSync._spun()`：每步用绳自己当前的方位角
重新对准跟随带，而不是用插头的。整条带**共用一个刚性角**（不是逐节点各转各的，那会让
截面剪切变形），用复数乘积拟合最佳绕轴转角——它天然按半径加权，所以靠近轴心、方位角本就
没有意义的节点几乎不参与。

两端都这样处理（插头端和固定端子端），扭转从两头自行泄掉。

离线用构造的带验过（`scratchpad/test_swivel.py`）：绳转 0/+30/−120/+179 度、插头本身既旋转
又平移、节点位置带 0.2mm 噪声——跟踪角全部正确，且**沿轴与径向位置一字未动**；
全零输入退回原偏移，不产生 NaN。

### 6.5.4 绳↔指垫摩擦

夹爪只是搬运工具，任务的物理内容是绳与柱的交互。指垫上有摩擦时，绳会顺着扭转爬上指垫并
缠住，所以把这对接触做滑。

IPC 的接触摩擦是**逐实体材质的几何平均**（`ipc_coupler/coupler.py:681`）：绳出
`rope.fem.friction_mu`，手指出材质的 `coup_friction`。`physical_handle.robot_rope_friction`
就是后者，取 0.004 →实际摩擦 `sqrt(0.3 × 0.004) ≈ 0.035`，而 Genesis 默认的 0.1 会给到 0.17。

它**只**影响绳↔指垫：`enable_rigid_rigid_contact=False` 让手指在 IPC 里没有别的接触对，
而真正握住插头的是刚体求解器的摩擦（`configure_gripper_contact_friction`），是另一套。

### 6.5.5 把扭转变成读数

`supervision/rope_winding.py` 的 `rope_twist_turns()`：沿**当前**中心线做 parallel transport，
在每个材料分箱里比较节点当前的横截面方位角与它出生时的材料方位角，沿弧长 unwrap，
末首之差除以 2π 就是总扭转（圈）。首端的任意相位在做差时抵消。

`--probe` 每次采样打一列 `twist`，验收行末尾也报 `twist_turns`。**它只报不判**——绳拧着是
质量问题，任务定义在 winding number 上，两者分开记。

离线用构造好的绳验过（`scratchpad/test_twist.py`）：直绳 0/+1/−2 圈、平面弧 0/+1.5 圈、
**螺旋（缠绕后的形状）0/+2 圈**，七例全部读数精确。最后那两例是关键——朴素的算法会把螺旋
自身的 writhe 误当成扭转，这个实现不会。

## 7. 离线校验（不需要 GPU）

```bash
python tests/check_rope_winding_geometry.py
```

拿**真实**配置和**真实** planner / winding 代码跑（只需要 numpy + PyYAML），
一次完整缠绕是几分钟的 IPC 求解，这个是秒级的：

| 组 | 查什么 |
| --- | --- |
| oracle | 路点结构、轨道半径、爬升单调且等于 `turns × climb_per_turn`、**不越柱顶** |
| topology | 出生路线不环绕柱（winding 出生为 0）、终态 winding = ±turns、镜像方向符号相反且轨道反向 |
| swivel | 插头自转角逐点跟住轨道角、每段 45° 在 slerp 安全区内、turns×360° 后回到出厂朝向 |
| rope length | 绷紧路径最紧时刻绳够长、富余落在 5%~15%（低了绳跟锚定带较劲，高了是 cable 螺旋的燃料） |

改布局（柱/端口/锚点位置、出生弧、`winding.*`）之后必须重跑它。出生弧本身由
`tests/check_rope_winding_geometry.py` 校验、由会话脚本 `winding_geometry.py` 求解
（圆心/半径/扫角的搜索，见 §4 的数值）。注意它读的是 `route_polyline`，**看不到**
样条、端点预留与入口弧，所以 `rope.mesh.*` 的改动对它是隐形的；它报的 0.708 m 也
不是成网后的真实绳长（0.7414 m，真实富余 13.5% 而非 8.4%）。

表皮几何单独有一份体检（§3.3 的判据），量的是喂给 tetgen 的那张管皮：

```bash
python -B -m demos.routing.rope_winding_physical_handle_demo run.build_only=true
python tests/check_rope_tube_mesh.py --radial 20
```

| 判据 | 阈值 |
| --- | --- |
| 纵向弦高 `d²/8R` 最大值 | 不超过截面弦高（radial=20 时 0.049 mm） |
| 表皮自带扭转 | < 1°（Bishop 框架上构造为零，非零说明框架漂了） |
| 最小曲率半径 / 管半径 | ≥ 1（低于 1 内侧表皮自折）；端子入口弯目前是 2.0，只报不拦 |

其余仓库自带检查：`python tests/check_demo_configs.py`（demo 形态 7 项 + run 键
存在性，本 demo 全绿无警告）、`python tests/check_configs_compose.py`（需要
hydra，在 WSL 跑）、`python topogym/core/taxonomy.py`。

## 8. 里程碑（GPU，用户跑）

全部 viewer 判读、不录视频。`-B` 是这个 `/mnt/c` 仓库的必需项：Windows 侧改代码、
WSL 侧跑，字节码缓存会漏更新（2026-08-11 实测漏掉了两个模块，报错指向一个已删除的键）。

```bash
# A. 出生与静置 —— 已通过（见 §3.2）
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true run.max_waypoints=2 2>&1 | tee runs/winding_a_spawn.log
# 每步代价：绳↔夹爪接触关 / 开 各测一次（只空跑计时，不跑物理）
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.bench_steps=60 task.physical_handle.robot_rope_contact=off 2>&1 | tee runs/winding_bench_off.log
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.bench_steps=60 2>&1 | tee runs/winding_bench_on.log
# B. 先跑一圈：回答「松绳会不会真的套上柱子」，并确认绳不再穿过指垫
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true task.winding.turns=1 2>&1 | tee runs/winding_b_turn1.log
# B2. 转环的 A/B：先不转环拿基线扭转，再默认跑一遍看它掉到 0 附近
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true \
  task.winding.turns=1 task.rope.fem.follow_swivel=false 2>&1 | tee runs/winding_twist_off.log
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true task.winding.turns=1 \
  2>&1 | tee runs/winding_twist_on.log
# C. 成功例（完整两圈 + 放置）
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true 2>&1 | tee runs/winding_c_success.log
# D. 方向反转的失败对照例（winding = −2）
python -B -m demos.routing.rope_winding_physical_handle_demo \
  run.viewer=true run.probe=true run.keep_open=true task.winding.direction=cw 2>&1 | tee runs/winding_d_cw.log
```

### 8.1 B 轮要回答的问题：松绳能否成圈

出生时绳有约 0.44 m 富余（全长 0.628 m，而锚点到入绕位只有约 0.19 m）。富余是任务固有的
——终态需要 0.553 m，其中 0.20 m 要被两圈吃掉，成圈之前那段长度必然是松的，真实绕线也
一样。问题是松绳被拖着绕柱时到底会**套上柱子**，还是只在柱子附近**扫过去**。

`--probe` 的实时 `winding` 就是这把尺，第一圈内它应当单调爬向 ±1.0；每圈结束另打一行
`turn_complete winding_number=...`。若它停在 0 不动，按顺序试补救，一次只动一个：

1. `task.winding.wind_radius=0.065` —— 轨道放大，扫过的范围更大、更容易兜住柱子；
2. 入绕前先把绳拉直：在 planner 里加一个「反向张紧」路点（先把插头拉到柱的远侧、
   离锚点更远处吃掉松弛，再收回轨道），对应真实绕线前的抖直动作；
3. 缩短出生弧减少初始富余（代价：终态富余变小，离线 gate 的 5%~15% 判据会拦，
   需要连带把 C 挪近）。

其余要盯的：圈间接触在 `contact_d_hat=2 mm` 下是否稳定；机械臂绕柱 720° 的 IK 与净空
（`wind_radius` 与 `climb_per_turn` 是调参钮）；缠满后绳的张力是否把锚定带拽动
（`safety_min_gap` 会兜底中止，读 `surface_gap` 判断是接触求解问题还是策略问题）。

圈塌成一堆不算失败：winding number 是拓扑量，塌堆只影响观感，不影响计数。
