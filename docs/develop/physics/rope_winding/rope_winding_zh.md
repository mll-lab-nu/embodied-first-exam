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

**加密表皮本身不解决观感**，见 §3.4：真正让绳起皱的是接触势垒，而且截面加密会加重
它。两件事必须一起改。

### 3.4 接触势垒撞上管皮自身的分辨率（2026-08-20）

`rope.fem.contact_d_hat` 是 IPC 接触势垒的作用距离。libuipc 只对**共顶点**的图元对
跳过接触，因此这个距离必须小于绳**自己表面**上不共顶点的最近一对图元间距。管半径
4mm 时该间距由截面边数决定（周向：一个顶点对隔位的那条棱；轴向：隔一环）：

| `radial_segments` | 自身表面最近间距 | 对 `d_hat=0.002` |
| --- | --- | --- |
| 8（untangle 系） | 3.06 mm | 余量 53% |
| 12（改前的 winding / cable_routing） | 2.07 mm | **余量 3.5%** |
| 20（本轮） | 1.25 mm | **已在势垒内** |

prefab 里 `contact_d_hat: 0.002` 是照两根绳叠放的静止间距标定的（见该处注释），从未
对过管皮自身的分辨率。违反之后绳的表面在自己内部互相排斥，后果是三件事同时发生：

1. 排斥力沿整根管皮作用 → 表面全长起皱；
2. ν=0.45 接近不可压，周向被撑开 → 轴向缩短 → 绳向出生弧的圆心收缩；
3. 扭转被持续泵入 → 扭转转成 writhe → 卷成电话线。

实测（radial=20，静置 300 步，机械臂一步未动）：

| | `d_hat=0.002` | `d_hat=0.0008` |
| --- | --- | --- |
| `rope_spread` | 0.2303 单调降到 0.2242 | **0.2624 一位不变** |
| `rope_jump` | 每步 0.0002 | **0.0000** |
| `TWIST span` | 0.090 → 0.285 | 0.046 → 0.066 后完全静止 |
| `twist_summary onset` | step 5 | **none** |
| `max_twist` | 2.67 圈 | **0.17 圈** |
| 绳离桌面 | 1.9 mm | 0.8 mm |
| 结果 | lift 检查失败 | 完成 2/2，`placement_success` |

对照组：只把跟随带半径从 12mm 缩到 5mm（`task.rope.anchor_radius=0.005`）不但没治，
扭转反而更大（span 0.333、legacy 2.67），该嫌疑排除。

因此本任务把 `contact_d_hat` 覆写为 **0.0008**，并在建场景时加了校验
（`world/rope.py` 的 `check_self_contact_clearance`）：`d_hat` 达到自身间距即拒绝启动，
落在 75%~100% 之间打印同一组算术但继续跑——`cable_routing` 的 12 边形 + 2mm 正落在
这一档，而它从未按这条判据实测过。**cable_routing 那条被记录为「电话线螺旋」的老故障，
与本条的机理一致，值得回头复核。**

顺带修正一条历史判断：`twist_legacy` 随网格密度变化，曾被怀疑是读数假象；实际是势垒
的违反程度随网格密度变化，它测的是真实扭转。`d_hat` 改小后它与 `TWIST` 探针一致。

**仍未解决的一层**：若势垒改好之后绳一动起来还有细碎起伏，那是渲染面的每个边界节点
都是独立 FEM 自由度、节点之间是直线段所致，由**体网格密度**（`maxvolume`，当前 5e-8
并非约束，实际平均 tet 体积 2.9e-9）与求解器决定，加密表皮帮不上——与
`cable_routing_element_design_zh.md` 附录 3 对「折线感」的归因是同一条。

## 4. 布局

单位米，task 坐标系（z=0 是桌面）。几何预算脚本见 §7。

| 元素 | 位置 | 说明 |
| --- | --- | --- |
| S（固定端子） | (−0.150, 0.100) | 绳的锚定端，视觉是工业端子；fixtures 里的桩体关闭，只提供坐标 |
| POST（绕线柱） | (0.020, 0.020) | 半径 0.020、高 0.109（柱顶 0.105，2026-08-16 加高），喇叭底座；**collision: true**（绳缠在它上面，接触就是任务本身） |
| C（靶心） | (0.075, −0.130) | 地面靶心（2026-08-12 由平嵌端口改成），离柱 0.160 m；2026-08-27 从东北 (0.150, 0.120) 挪到柱南侧，让直线去 C 不穿锚点对径射线（见 `rope_unwinding_zh.md` §6.1） |
| 插头出生点 | (0.156, −0.157) | 出生弧的终点，离柱 0.223 m；2026-09-05 起由规则推导（§9.1），基准还原到 0.2 mm |

出生弧：单段圆弧、张角 `rope.spawn_arc.sweep_deg` 200°（两圈），从柱**南侧**绕过 —— 出生时不环绕柱，
winding number 从 0 开始（离线校验过，见 §7）；张角随圈数配对（§8 / `rope_winding_gripper_rope_interference_zh.md` §2.9），
变体里按松弛带反解（§9.1）。

缠绕轨道：半径 0.140（手掌碰撞体长半轴 0.104 + 柱 0.020 + 余量，见 yaml `wind_radius` 注释），
每圈爬升 0.014（圈间净空 6 mm），每圈 8 个路点（45°/点，折线相对真圆最大偏差 3.8mm < 绳径）。
绳在张力下自己收落到柱面半径 0.024，轨道不需要贴柱。

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

## 9. 变体轴与派生（2026-09-05，变体计划 §6.2 第 6 步）

按 linkbar / diverter / gate / band / c_ring / bar / rope_unwinding 的六项清单部署：yaml `variation:` 块、`checks()` 与派生钩子、
demo 接线 + variant 行 + run 配置键、`check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测。
参考样例 `rope_unwinding_zh.md` §7（同族任务，机制大多共用）。

**画面。** 桌上三样东西：固定端子 S（绳的一头钉死在这里）、绕线柱 POST、靶心 C；绳从 S 出发弯成一段圆弧（出生弧）绕过柱的南边、
不碰柱、不绕柱，躺到插头出生点。机械臂抓起插头，拉到柱旁，围着柱子转 `turns` 圈、每圈升高一个圈距 `climb_per_turn`，绳一圈圈缠上柱，
然后放到靶心。判据：闭合计数 = sign × turns、缠绕不越柱顶、插头落在 C 的 0.018 内。

**术语。** 出生弧 = `routes.initial` 的那段圆弧，张角 `spawn_arc.sweep_deg` 决定绳长；松弛 = (绳长 − `taut_demand`) / `taut_demand`，
带 [5%, 15%]，最紧时刻在插头举到 C 上方（`to_C_hover`）；闭合计数 = `winding_topological`；锚点对径射线 = S 相对柱心方位角 + 180°，
自由端穿过它时闭合计数变 1；首抽拒绝率门 2%；角点 = 连续轴两端 × 离散轴全部取值；对照组 = `orbit_direction: opposite`（轨道与指令相反）。

### 9.1 轴

| 类 | 叶子 | 抽法 | 基准 | 说明 |
|---|---|---|---|---|
| A | `winding.turns` | Cat{1, 2, 3} | 2 | 难度候选。此前只有 2 圈 ccw 有 GPU 证据（08-27） |
| A | `winding.direction` | Cat{ccw, cw} | ccw | **防捷径离散轴**（`variation_axes_plain_zh.md` §3）：桌上的东西不动，只有轨道方向与目标符号翻转，策略必须读指令。与 rope_unwinding 不同，这里 cw 不做镜像布局：出生弧与方向无关，离线门断言 cw 与 ccw 的出生折线逐点相同 |
| B | `fixtures.POST.x` / `.y` | U[−0.020, **0.045**] / U[−0.020, 0.060] | 0.020 / 0.020 | x 上界从计划的 0.060 收到 0.045：手最远的点是插头出生点（柱东南 0.223 m），(0.570 + x + 0.137)² + 0.196² ≤ 0.780² 给 x ≤ 0.048。`pos` 拆成 `x / y / z` |
| B | `fixtures.S.x` / `.y` | U[−0.180, −0.120] / U[0.070, 0.130] | −0.150 / 0.100 | 端子 ±0.030 |
| B→C | `fixtures.C.y_frac` → `fixtures.C.y`，`fixtures.C.x_frac` → `fixtures.C.x` | U[0, 1] × 2 派生（先 y 后 x） | (0.075, −0.130) | 靶心的方框 `x_range` [0.045, 0.105] × `y_range` [−0.160, −0.100] 里两种位置不用：离插头出生点不到 0.040 的（插头法兰 0.015 + 靶心半长 0.020 + 5 mm；独立抽时 15% 会撞到插头），以及「从缠绕出口直线去 C 会穿过锚点对径射线」的（§9.4 c1052 之后加；对径射线是相对柱心的方位角，端子在柱东北时靶心靠北的整行 y 都不行，所以 y 也要派生）。按 2 mm 步长扫出可用的 y 区间、再扫该 y 上可用的 x 区间，frac 按长度映射（`_rope_winding_geometry.target_y_from_frac / target_x_from_frac`）。基准 frac 0.5 / 0.5 还原 (0.075, −0.130) |
| B | `winding.climb_per_turn` | U[0.010, 0.016] | 0.014 | 圈距。出生没有螺旋，rope_unwinding 的 tetgen 边界 0.012 不适用；0.010（圈间净空 2 mm）此前没实跑过 |
| B→C | `winding.wind_z_frac` → `winding.wind_z_start` | U[0, 1] 派生 | 0.045 | 首圈高度，区间 [0.035, min(0.055, 柱顶 0.105 − 0.010 − 绳半径 − turns·climb)]（共用 `wind_z_from_frac`） |
| C（派生叶子） | `rope.spawn_arc.sweep_deg` | 反解 | 200 | 绳长反解：先用当前布局规划航点，`need = taut_demand`，目标绳长 = need × 1.10（松弛带中点），弧长 = 弦长 × θ / (2 sin(θ/2)) 二分解 θ（`_rope_winding_geometry.sweep_from_slack`）。基准解出 201.3°；1 / 2 / 3 圈解出 152.8 / 201.3 / 229.3，对配对表 155 / 200 / 230 |
| C（Layout 规则，无叶子） | 插头出生点 | 派生 | (0.156, −0.157) | `routes.initial` 的 `plug_spawn_from` 条目：柱心外 `plug_distance` 0.2233、方位角 `plug_bearing_deg` 307.5°（还原手写点到 0.2 mm）；方位角上限 = S 对径射线 − `anchor_lead_deg` 27°，S 在柱东北（S 方位角 < 154.5°）时插头沿圆往回滑，出生弧才不绕住柱。27° = 切向出口段的 23°（`exit_extension` 0.060 在轨道半径 0.140 上）+ 4° 余量：出口也不能越过对径射线（§9.4 c1052）；也正好是基准 S 离射线的角度，基准不滑 |
| D | `wind_radius` 0.140、`rope.z`、`contact_d_hat`、`rope.mesh.*`、`POST.collision`、`plug_spin_tracks_orbit`、`yaw_track: false`、`exit_extension`、`to_c_route: straight`（试过 closure，c1052 否掉） | 固定 | | |

`anchor_lead_deg` 的取值经过两轮：先按「出生弧不绕住柱」扫 1536 角点（10° 有 48 个角点凑不出闭合计数、15° 有 24 个、20° 起全过，20° 时约四分之一
的布局滑动），首跑 c1052 之后按「切向出口也不越对径射线」改为 27°。

三个字面量副本（角点门裸加载 task yaml 读不到 `${prefabs…}` / `${common…}`）：`rope.radius` 0.004、`POST.base_height` 0.010、`workspace.x/y`，
`RopeWindingSceneBuilder.build` 断言相等。派生顺序：`wind_z_frac → wind_z_start`，`C.x_frac → C.x`（要先有插头出生点），最后 `sweep_deg`（要先有 C）。

### 9.2 `checks()` 十三行

纯函数在 `topogym/tasks/routing/_rope_winding_geometry.py`（numpy + planner，不 import Genesis），与 rope_unwinding 共用的规则在
`_winding_post_geometry.py`（09-05 从 `_rope_unwinding_geometry.py` 搬出，rope_unwinding 的离线门与 rng 段重跑不变）。行里跑真实 planner，
可达与松弛读的是 oracle 的实际航点；对照组的强制轨道不进入行（`oracle_view`）。

| 行 | 读数 | 门 | 基准 | 1536 角点最紧 |
|---|---|---|---|---|
| `wraps_below_post_top` | 柱顶 − 0.010 − (wind_z_start + turns·climb + 绳半径) | ≥ 0 | 0.018 | 0（`wind_z_frac=1` 构造取等） |
| `bottom_wrap_above_base` | wind_z_start − 绳半径 − `POST.base_height` | ≥ 0 | 0.031 | 0.021 |
| `wrap_gap` | climb − 2·绳半径 | ≥ 0.002 | 0.006 | 0.002（climb 0.010 取等） |
| `arc_clears_post` | 出生弧各点离柱轴最小距离 | ≥ 0.060 | 0.188 | 0.1005 |
| `plug_in_workspace` | 插头出生点到工作区 x/y 边界的最小距离 | ≥ 0.040 | 0.093 | 0.063 |
| `plug_clears_target` | \|插头出生点 − C\|_xy | ≥ 0.040 | 0.086 | 0.040（`C.x_frac` 取窗口端点） |
| `palm_clears_post_top` | 最低轨道高度 + `PALM_ABOVE_PADS` − 柱顶 | > 0 | 0.019 | 0.008 |
| `spawn_reads_zero` | \|出生路线的闭合计数\| | < 1e−6 | 0 | 0 |
| `free_end_reads_target` | 出生读数 + `free_end_winding_delta`(自由端全程) − sign·turns | = 0 | 0 | 0 |
| `run_to_c_is_straight` | 规划里 `to_C_around` 航点的个数 | = 0 | 0 | 0（靶心派生后没有角点需要绕远侧） |
| `hand_reach` | 规划航点离 (−0.570, 0) 的最大距离 | ≤ 0.780 | 0.743 | 0.7764 |
| `slack_in_band` | 松弛 | ∈ [0.05, 0.15] | 9.1%（固定 200°）/ 10.0%（反解） | 10.0% |
| `sweep_in_range` | 反解的张角 | ∈ [60°, 300°] | 201° | 139°–251° |

现有离线门的「螺旋在柱顶下」一行改读 `post.z`（原 `post.pos[2]`）；「判据是闭合计数且去 C 走直线」保留，另加「基准 C 在锚点对径射线的近侧」。

### 9.3 离线实测（2026-09-05，最终规则）

| 门 | 结果 |
|---|---|
| `tests/check_rope_winding_geometry.py`（默认 / `--turns 1 --sweep-deg 155` / `--turns 3 --sweep-deg 230`） | PASS：原 45 行不变（松弛 9.1 / 11.1 / 10.6%）；配对表那段改成断言：反解 152.8 / 201.3 / 229.3 对 155 / 200 / 230 在 3° 内；插头规则还原 (0.1559, −0.1572)；新段 variation envelope：frac 0.5 还原 wind_z 0.045、C (0.075, −0.130)、张角 201.3；十三行基准全过；cw 出生折线与 ccw 逐点相同、21 航点；**1536 角点全部可行、没有一个需要绕远侧**；两个负例（POST x 0.060 拒可达；S 在柱东北时不设方位角上限出生读 +1、设了读 0） |
| `tests/check_rope_unwinding_geometry.py`、`check_variant_rng.py` rope_unwinding 段 | PASS（共用规则搬家不回归） |
| `tests/check_variant_rng.py` rope_winding 段 | 叶子顺序、seed 3 确定性、1000 seed 每轴在区间内、四个派生叶子（首圈高度、靶心 y、靶心 x、张角）逐 seed 等于规则、C 离插头 ≥ 0.040、十三行全过、三档圈数 317 / 356 / 327、ccw / cw 494 / 506、最大可达 0.775、张角 144–249°、插头滑动 520 次；首抽拒绝率 **0.000** |
| `tests/check_variant_corners.py --task rope_winding` | **1536 角点 1536 可行**，Hydra compose 读数一致（派生叶子 `wind_z_start` / `C.y` / `C.x` / `sweep_deg` 作为 `task.*` 覆盖传给固定布局路径） |
| `tests/check_configs_compose.py`、`tests/check_demo_configs.py` | PASS |
| 离线 tetgen 探针（`RopeWindingLayout.rope_mesh("initial")` + `pq1.1/10a5e-08`） | seed 0–9 与 10 个角点的出生弧管皮全部可四面体化 |

### 9.4 GPU 实测（4090，与 ring_transfer 会话共用，2026-09-05 起）

**首跑（靶心只派生 x、`to_c_route: closure`、插头方位角上限离射线 20°；`runs/rope_winding_variation/20260905_*_firstrun/`、
`runs/rope_winding_corners/20260905_firstrun/`）：** 固定布局复跑 2 圈 ccw 通过（闭合计数 +2、21/21、放置 0.2 mm、终态贴柱 2654，与 08-27 相同）；
seed 0–9 oracle **10/10**、visual 10/10；wrong_way 3/3 判失败；角点子集 c1024、c1032 通过，**c1052 失败**：

| seed | T | 向 | 张角 | 闭合计数 | 放置 | 终态贴柱 | 耗时 |
|---|---|---|---|---|---|---|---|
| 0 | 3 | ccw | 240.6° | +3 | 0.1 mm | 3772 | 18 min |
| 1 | 3 | ccw | 242.6° | +3 | 0.3 mm | 3543 | 19 min |
| 2 | 1 | cw | 151.4° | −1 | 0.3 mm | 0 | 7 min |
| 3 | 2 | ccw | 197.4° | +2 | 0.4 mm | 2596 | 13 min |
| 4 | 2 | ccw | 196.2° | +2 | 0.4 mm | 2669 | 12 min |
| 5 | 1 | ccw | 156.5° | +1 | 0.1 mm | 1364 | 7 min |
| 6 | 3 | ccw | 237.2° | +3 | 0.3 mm | 4096 | 15 min |
| 7 | 1 | cw | 170.5° | −1 | 0.4 mm | 0 | 6 min |
| 8 | 2 | ccw | 216.1° | +2 | — | — | 11 min |
| 9 | 2 | cw | 198.8° | −2 | — | — | 11 min |

三圈与顺时针都是第一次在 GPU 上跑通。三圈缠满贴柱 3500–4100 个节点，离绝对门 4800 不远，是 `safety_max_contact_fraction` 的依据。
**一个观察**：顺时针一圈的两格（seed 2 / 7）终态贴柱 0、最近的绳离柱面 18 mm——闭合计数读 −1、判成功，但绳是松松套在柱子周围而不是贴在柱身上；
逆时针一圈的 seed 5 贴着柱（间隙 0.8 mm）。按既定口径（闭合计数是拓扑量，§8.1「圈塌成一堆不算失败」）不算失败，顺逆时针的物理表现不对称记在这里。
wrong_way：seed 0 / 1（3 圈 ccw 指令、轨道强制 cw）读 −3，seed 2（1 圈 cw 指令）读 +1，全部 `task_success=False`。

**c1052 暴露的隐含假设：绕远侧去 C 的路线（`to_C_around`）不适用于缠满的绳。** 这个角点 S 在柱东北（方位角 136.8°，对径射线 316.8°），插头按规则滑到
离射线 20°，三圈缠完后切向出口在 320°——已经越过射线 3°；C 在 327.4°。planner 算出直线去 C 闭合计数会多 1，于是走远侧：从 320° 顺时针绕到 143.7°
（柱的另一边、离机械臂底座只有 0.44 m）再去 C。三圈闭合计数 1 / 2 / 3 都对，走这一步时插头被拽脱手（`segment_follow_failed`，`intrusion=1605`，
手掉到桌面以下）：绳已经缠满三圈绷着，绕远侧等于把缠好的绳倒拖近一圈，机械臂又折到底座旁。rope_unwinding 用这条路线时绳已经全部解下、是松的，所以那里没事。

处置（修执行链，包络不动）：本任务 `to_c_route` 回到 `straight`；靶心位置在派生时就放到「直线去 C 不穿对径射线」的位置——射线是相对柱心的方位角，
端子在柱东北时靶心靠北的整行 y 都不行，所以 y 也改为由 `y_frac` 派生（先 y 后 x，各按 2 mm 扫出可用区间）；插头方位角上限从离射线 20° 改回 27°
（切向出口段占 23°，出口也不能越过射线）。离线复核：1536 角点全可行、没有角点再需要绕远侧；固定布局的插头点、靶心、张角原样还原。
seed 映射随之改变（每个 seed 的靶心 y 都变），所以固定复跑、seed 0–9、wrong_way、角点子集全部按新规则重跑。

**重跑（最终规则；`runs/rope_winding_variation/20260905_baseline/`、`20260905_seeds/`）。** 固定布局复跑 2 圈 ccw 通过（与首跑相同）。
**seed 0–9 oracle 10/10**（位置为 task 系，`contact` 是终态贴柱节点数、`gap` 是绳离柱面最近距离、`twist` 是终态 `twist_turns`）：

| seed | T | 向 | POST (x, y) | S (x, y) | C (x, y) | climb | wind_z | 张角 | 插头出生 | 航点 | 闭合计数 | 放置 | contact | gap | twist | 耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 3 | ccw | (−0.016, +0.031) | (−0.146, +0.078) | (+0.068, −0.142) | 0.0117 | 0.0402 | 242.6° | (+0.120, −0.146) | 29/29 | +3 | 0.0002 | 3722 | 0.0008 | +0.21 | 882 s |
| 1 | 3 | ccw | (−0.018, +0.043) | (−0.168, +0.077) | (+0.060, −0.132) | 0.0140 | 0.0465 | 242.3° | (+0.118, −0.134) | 29/29 | +3 | 0.0003 | 3672 | 0.0008 | +0.21 | 876 s |
| 2 | 1 | cw | (+0.038, +0.015) | (−0.141, +0.082) | (+0.081, −0.116) | 0.0110 | 0.0483 | 151.4° | (+0.174, −0.163) | 13/13 | −1 | 0.0003 | 0 | 0.0216 | −0.76 | 332 s |
| 3 | 2 | ccw | (+0.017, −0.004) | (−0.142, +0.098) | (+0.055, −0.107) | 0.0156 | 0.0367 | 199.3° | (+0.129, −0.198) | 21/21 | +2 | 0.0007 | 2628 | 0.0008 | +0.19 | 546 s |
| 4 | 2 | ccw | (+0.007, +0.001) | (−0.153, +0.123) | (+0.103, −0.131) | 0.0136 | 0.0421 | 200.2° | (+0.104, −0.201) | 21/21 | +2 | 0.0004 | 2634 | 0.0008 | +0.18 | 555 s |
| 5 | 1 | ccw | (+0.021, +0.020) | (−0.159, +0.079) | (+0.105, −0.114) | 0.0124 | 0.0506 | 155.4° | (+0.157, −0.158) | 13/13 | +1 | 0.0001 | 1311 | 0.0008 | +0.15 | 336 s |
| 6 | 3 | ccw | (−0.008, +0.040) | (−0.124, +0.099) | (+0.048, −0.131) | 0.0131 | 0.0361 | 240.8° | (+0.124, −0.140) | 29/29 | +3 | 0.0003 | 3875 | 0.0008 | +0.21 | 896 s |
| 7 | 1 | cw | (+0.041, +0.054) | (−0.139, +0.073) | (+0.051, −0.103) | 0.0107 | 0.0481 | 163.8° | (+0.177, −0.124) | 13/13 | −1 | 0.0003 | 0 | 0.0203 | −0.79 | 353 s |
| 8 | 2 | ccw | (+0.014, +0.052) | (−0.154, +0.072) | (+0.081, −0.101) | 0.0117 | 0.0477 | 212.8° | (+0.150, −0.126) | 21/21 | +2 | 0.0001 | 2834 | 0.0008 | +0.21 | 623 s |
| 9 | 2 | cw | (+0.035, +0.002) | (−0.173, +0.071) | (+0.091, −0.146) | 0.0154 | 0.0540 | 199.4° | (+0.171, −0.175) | 21/21 | −2 | 0.0002 | 1817 | 0.0008 | −0.80 | 568 s |

- 十格全部 `task_success=True`，航点全走完，闭合计数 = sign × turns，放置误差 ≤ 0.7 mm；松弛全部 10.0%（反解取中点）。
- 三圈（seed 0 / 1 / 6）与顺时针（seed 2 / 7 / 9）都是第一次在 GPU 上跑通。顺时针格 `twist_turns` 符号相反（−0.76 … −0.80），量值大于逆时针（+0.15 … +0.21）。
- 三圈缠满贴柱 3672–3875 个节点：绝对门 4800 还有余量，但 `safety_max_contact_fraction` 0.85（全绳 7000–7700 节点，门 6000 左右）才是随圈数走的门。
- **顺时针一圈的两格（seed 2 / 7）终态贴柱 0、绳离柱面 20 mm**：闭合计数读 −1、判成功，但绳只是松松套在柱子周围而没有贴在柱身上；顺时针两圈的 seed 9 贴柱 1817（间隙 0.8 mm），逆时针一圈的 seed 5 贴柱 1311。按既定口径（闭合计数是拓扑量，§8.1「圈塌成一堆不算失败」）不算失败；一圈 + 顺时针这一组合的绳不贴柱，是划档或改判据时要记得的读数。

**visual 10/10**：每格 `run.max_waypoints=1`（抓起插头就停）录像，`visual_s*.mp4` 有帧；cw 格画面与同布局的 ccw 相同（方向只在指令里）。

**wrong_way seed 0–2：3/3 判失败**（`runs/rope_winding_variation/20260905_wrong_way/`）：seed 0 / 1（3 圈 ccw 指令、轨道强制 cw）读 −3，
seed 2（1 圈 cw 指令、轨道强制 ccw）读 +1，全部 `task_success=False`、`physical_success=True`。反向轨道照样把绳缠上柱，只是符号相反——判据靠符号抓住它。

**角点子集 10 格：10/10**（`runs/rope_winding_corners/20260905/`；全部 3 圈，每行最紧的 ccw / cw 各一格）：

| 角点 | 取的极值 | 向 | POST | S | 派生出的 C | 张角 | 闭合计数 | 放置 | contact | 手最远 | 耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1024 | 最低轨道（首圈 0.035、圈距 0.010） | ccw | (−0.02, −0.02) | (−0.18, 0.07) | (0.045, −0.160) | 229.0° | +3 | 0.0003 | 3588 | 0.705 | 813 s |
| c1280 | 同上 | cw | 同上 | 同上 | 同上 | 229.0° | −3 | 0.0002 | 2935 | 0.705 | 842 s |
| c1086 | 锚点在柱东北、插头往回滑（圈距 0.016） | ccw | (−0.02, −0.02) | (−0.12, 0.13) | (0.047, −0.122) | 229.2° | +3 | 0.0012 | 3678 | 0.689 | 799 s |
| c1342 | 同上 | cw | 同上 | 同上 | 同上 | 229.2° | −3 | 0.0012 | 2412 | 0.689 | 845 s |
| c1100 | 插头贴靶心净空 | ccw | (−0.02, 0.06) | (−0.18, 0.07) | (0.080, −0.100) | 244.3° | +3 | 0.0001 | 3598 | 0.696 | 915 s |
| c1356 | 同上 | cw | 同上 | 同上 | 同上 | 244.3° | −3 | 0.0003 | 3095 | 0.696 | 945 s |
| c1120 | 出生弧离柱最近（0.100） | ccw | (−0.02, 0.06) | (−0.12, 0.07) | (0.045, −0.160) | 256.7° | +3 | 0.0007 | 4005 | 0.696 | 940 s |
| c1376 | 同上 | cw | 同上 | 同上 | 同上 | 256.7° | −3 | 0.0006 | 2581 | 0.696 | 932 s |
| c1152 | 可达最远（手 0.776）、圈距 0.010 | ccw | (0.045, −0.02) | (−0.18, 0.07) | (0.045, −0.160) | 222.0° | +3 | 0.0003 | 2962 | 0.776 | 779 s |
| c1408 | 同上 | cw | 同上 | 同上 | 同上 | 222.0° | −3 | 0.0002 | 2571 | 0.776 | 787 s |

- 圈距 0.010（圈间净空 2 mm）的六格全过：计划表的下界成立，本任务不需要 rope_unwinding 那种 0.012 的网格边界（出生没有螺旋）。
- 可达 0.776 的两格过：`reach.max_hand_dist` 0.780 与 POST.x 上界 0.045 成立。
- 张角最大 256.7°（c1120 / c1376：锚点近、去 C 远），绳 1.0 m 上下，出生弧鼓到桌面上没出问题（板关着，绳躺桌上）。
- 贴柱数 2412–4005：cw 三圈普遍比 ccw 少 600–1400 个节点（同布局对比），与 seed 里「cw 一圈不贴柱」是同一现象的弱版本；闭合计数都对。

**六项交付的 GPU 结论。** 固定布局复跑通过；seed 0–9 oracle 10/10、visual 10/10；wrong_way 3/3 判失败；角点子集 10/10。首跑唯一的失败
（c1052）是执行链的隐含假设（绕远侧的路线对缠满的绳不成立），处置是靶心位置的派生规则与插头方位角上限，包络没动。

### 9.5 文件集

```
configs/task_configs/rope_winding_topogym_tabletop_v1.yaml     fixture x/y/z、plug_spawn_from 条目、spawn_arc 三个参数、to_c_route closure、orbit_direction、wind_z_frac、C.x_frac / x_range、reach、workspace 副本、safety_max_contact_fraction、variation 块
configs/run_configs/rope_winding.yaml                          randomize_layout / difficulty / variant_id 的注释
topogym/planning/waypoint.py                                   plug_spawn_point
topogym/planning/rope_winding_planner.py                       orbit_direction 接受 opposite
topogym/tasks/routing/cable_routing.py                         route_point 识别 plug_spawn_from；arc_to 的 sweep_deg 缺省读 rope.spawn_arc
topogym/tasks/routing/_winding_post_geometry.py                新：两个绕柱任务共用的规则（首圈高度、靶心 x、可达、工作区、oracle_view）
topogym/tasks/routing/_rope_winding_geometry.py                新：sweep_from_slack、rope_winding_checks（十三行）
topogym/tasks/routing/rope_winding.py                          RopeWindingLayout（checks / validate）、builder 断言字面量副本、derive_task_cfg / validate_task_cfg
topogym/tasks/routing/_rope_unwinding_geometry.py              共用规则改为 import
demos/routing/rope_winding_physical_handle_demo.py             variant 行加 turns / sweep_deg
tests/check_rope_winding_geometry.py                           resolve、post.z、closure 三行、反解断言、variation envelope 段
tests/check_variant_rng.py                                     rope_winding 段（1000 seed 拒绝率 0.000）
tests/check_variant_corners.py                                 TASKS 登记（1536 角点）
bash_scripts/tests/rope_winding_variation_sweep.sh             新（visual / oracle / wrong_way）
bash_scripts/tests/variant_corners_sweep.sh                    rope_winding 分支（对照组 wrong_way = orbit_direction opposite）
topogym/tasks/routing/_rope_winding_geometry.py（另）                 target_y_windows / target_x_windows_straight、exit_and_opposite_bearings、run_to_c_is_straight 行
runs/rope_winding_variation/20260905_*_firstrun/、runs/rope_winding_corners/20260905_firstrun/   首跑（靶心只派生 x、closure 路线；c1052 失败）
runs/rope_winding_variation/20260905_baseline/、20260905_seeds/、20260905_wrong_way/、runs/rope_winding_corners/20260905/   最终规则 GPU sweep
```
