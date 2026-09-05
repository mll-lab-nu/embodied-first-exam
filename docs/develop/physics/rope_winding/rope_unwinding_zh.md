# rope_unwinding：从柱上解下 start_turns 圈绳 + 放置

任务书（`docs/develop/TopoGym_tasks.docx`）§2.5「从柱子上解下一圈绳（1 → 0）」的实现，
圈数扩展为 `winding.start_turns ∈ {1, 2, 3}`。2026-08-26 新建。

## 1. 任务定义

绳出生时已绕柱 `start_turns` 圈，锚定端由固定端子钉死，自由端的工业插头平躺在板面上，
由 spawn latch 钉住。夹爪抓插头（不抓绳身），从最上一圈的高度开始，沿与缠绕相反的方向
连续环绕 `start_turns` 圈、每圈下降 `climb_per_turn`，winding number 从 `±start_turns`
变为 0，然后把插头放到 C。

- **柱顶是改变 winding 的唯一 gateway。** oracle 全程在柱顶以下，判据 `below_post_top`
  与 rope_winding 相同；抬过柱顶把绳甩下来不算解绕。
- **方向敏感。** `winding.direction` 描述柱上已有缠绕的方向（`ccw` 出生读 +start_turns）；
  夹爪轨道方向由 planner 派生为反向。任务书的失败对照例「方向做错时 winding 变成 2 而不是 0」
  对应 `task.winding.orbit_direction=ccw`（在 ccw 缠绕上强制同向轨道）：读数
  `2·start_turns`，判失败。`task.winding.direction=cw` 是镜像布局（出生缠绕与轨道同时反向），
  仍应成功。

任务书 §2.5 没有成功判定段。这里沿用 rope_winding 的判据：
`|winding_number − 0| ≤ success.winding_tolerance` ∧ 缠绕段不高于柱顶 ∧ 插头落在 C 的
`connector_tolerance_xy` 内 ∧ 原语没中止。

## 2. 与 rope_winding 的关系

| 层 | 做法 |
| --- | --- |
| 场景装配、资产、材料 | 全部复用。`RopeUnwindingSceneBuilder` 是 `CableRoutingSceneBuilder` 的子类（`tasks/routing/rope_unwinding.py`），布局数值与 `rope_winding_topogym_tabletop_v1.yaml` 相同 |
| 出生路线 | 新增路线条目 `helix_around`（`planning/waypoint.py::helix_route_points`，`cable_routing.py::route_polyline` 解析）：从 S 沿切线接上柱，绕 `start_turns` 圈，再接尾弧到插头出生点。09-04 起引入点与尾弧也是规则条目 `lead_in_toward` / `tail_arc`（§7.1），yaml 里不再有手写坐标 |
| oracle | 同一个 planner（`planning/rope_winding_planner.py`）。`WindingSpec` 新增 `start_turns`、`orbit_direction`，派生 `orbit_turns = |turns − start_turns|`、`turn_step`（每圈 +1 或 −1）、`orbit_sign`、`initial_winding`、`expected_winding`。`start_turns=0` 时行为与改前完全一致（`tests/check_rope_winding_geometry.py` 回归通过） |
| 判据 | `supervision/rope_winding.py` 不改；`target_winding = sign × turns = 0` |
| demo | `demos/routing/rope_unwinding_physical_handle_demo.py` 只有入口；主体 `rope_winding_physical_handle_demo.run_from_config` 按 spec 派生量工作（slack 检查、banner、任务描述） |
| 离线门 | `tests/check_rope_unwinding_geometry.py`，复用 rope_winding 门的 stand-in layout（加镜像规则的子类 `UnwindingStandIn`） |

## 3. 出生螺旋的几何

- 螺旋半径 = 柱半径 + 绳半径 + 2 mm（`helix_around.standoff`），比落位半径多 2 mm，
  避免绳管出生在 IPC 的接触距离内。
- 从 S 到柱的切入点：`bearing(S) + sign·arccos(r/d)`，绳沿切线到达柱面后按缠绕方向继续。
- 最下一圈在 `wind_z_start`（0.045），每圈爬 `climb_per_turn`（0.014，圈间净空 6 mm），
  三圈最上一圈顶 0.091，柱顶 0.105。
- **尾弧必须沿最上一圈的切线离开柱子**，否则出生时绳在柱面上带一个折角。切线方向 −33°，
  向远离柱子的一侧（ccw 缠绕时是顺时针）弯 130° 的尾弧，其弦相对切线偏 −65°、弦长 0.216
  （`rope.spawn_arc.chord`），因此插头出生点在 (−0.034, −0.214)；弧向 −x 侧鼓出，离柱轴始终 > 0.15 m。
  09-04 前这个点是手写的 (−0.006, −0.218)，离切线 5°；现在由 `tail_arc` 条目按上式推导（§7.1）。
  门里检查夹角 < 30°。
- 绳长由出生路线决定；松弛只来自尾弧的鼓出。最紧时刻在解绕**开始**（所有圈都在柱上），
  需求 = |S−柱| + start_turns × 2π × 落位半径 + |柱−插头|。出生螺旋每圈比落位周长多出约
  12 mm，抵消了大部分需求增量，所以 `spawn_arc.sweep_deg = −130` 一个值服务三档：
  松弛 8.5% / 8.9% / 9.2%（带 5~15%）。

## 4. oracle

航点与 rope_winding 同构：`lift_from_port` → `wind_entry`（在最上一圈的高度、轨道半径 0.140）
→ `wind_t{n}_{k}` × `start_turns × 8`（反向轨道、每圈下降 0.014）→ `wind_exit`（切向离开）
→ `to_C_hover` → `place_at_C`。搬运姿态、插头自转（`plug_spin_tracks_orbit`，按手的实际方位角
计算，方向自适应）、`before_release` 交接全部沿用。

出生时绳从最上一圈离开的方位比绷紧后的切点靠前约 50°，第一次抬起并拉入轨道时缠绕先少掉
约 0.14 圈；这使最后一圈能完整脱离柱面，`taut_demand` 因此偏保守约 2 cm。

## 5. 已知风险（待 GPU 实跑确认）

1. **多出的绳段没有去处。** `rest_shape=spawn` 使出生螺旋成为无应力构型，绳不会自己弹离柱子；
   代价是解开之后绳保留螺旋记忆，每圈约 0.151 m 的绳松散躺在板上，可能缠上柱底座或进入夹爪
   路径。`rest_shape=straight` 会让预绕的绳储存弯曲能、在静置时就试图弹离柱子，本轮不采用。
2. 柱面摩擦下，反向轨道拉动时圈是否逐圈脱离、还是整体上滑越过柱顶（`wound_max_z` 会记录）。
3. 解绕过程中插头出线口相对下方各圈的高度（`blocking_gap`，只报不判）。

## 6. 运行

### 6.1 2026-08-27 两圈 / 三圈：判据与去 C 的路线

`start_turns=2`、`3` 各跑两次（全程 21 / 29 航点、放置误差 3.3 mm、`physical_success=True`），
判定都失败。两个独立原因：

1. **柱上读数被松绳误导。** 第一次跑：两圈时第一圈内柱上读数 2 → 1 → 0（下面那圈松了，
   跟着一起脱离柱面），第二圈 `post_contact` 从 470 回升到 2251、读数回到 +1；三圈同样。
   回升的符号与原缠绕相同，是脱下来的松绳被张力拖回柱面贴了 0.65~0.73 圈，`winding_number`
   只看柱面带内的绳段，按 canonical closure 四舍五入成 1；反过来松掉但还没脱离的整圈又读成 0。
   解法：`supervision/rope_winding.py` 新增 `winding_topological`——整条绳绕柱轴的展开方位角
   加端点间短路闭合——由 `success.winding_metric: closure` 选为判据（rope_winding 保持 `on_post`）。
   第二次跑验证：每个 `turn_complete` 的闭合计数都正确（X=3：2 → 1 → 0），柱上读数不是。
2. **去 C 的路线本身改变闭合计数。** 第二次跑闭合计数在最后一圈末读 0、到 C 后读 +1。
   闭合到锚点的计数在自由端穿过**锚点对径射线**时变 1（短路闭合换边），从最后一个轨道点
   （方位 245°）直线去 C（38°）恰好穿过 335° 那条射线。`planning/rope_winding_planner.py`
   新增 `free_end_winding_delta`（沿自由端路径累计的计数变化）与 `winding.to_c_route: closure`：
   直线路线计数不对时绕柱的另一侧去 C，多一个航点 `to_C_around`（轨道半径上、远侧中点、
   悬停高度）。门里校验「出生读数 + 自由端全程 = 目标」并有负对照（直线会多 1）。

第三次跑（`start_turns=2`，`to_c_route: closure`，22 航点）：`success=True`，闭合计数在
`wind_t1_08` / `wind_t2_08` / 终态读 1 / 0 / 0，`placement_error_xy=0.0032`；同一时刻柱上读数
是 0 / 0 / −1（终态柱脚旁的松绳贴柱 0.73 圈），只作诊断。

`start_turns=3` 同样通过（30 航点，闭合计数 2 / 1 / 0 / 0，放置 3.2 mm，`pad_gap` 最小 1.8 mm）。
三档全部通过。质量项（不判定）：三圈时 `twist_turns` 终态 +1.44、`max_twist` 2.46，
`plug_vs_rope` 钝角 10/265（绳从插头侧面进入的时刻），比一圈 / 两圈高，来源待查。

**两种计数的关系与统一（2026-08-27 用户决定）。** 柱上读数是任务书「0 → 2」的口径，但它依赖
绳绷紧贴柱；闭合计数是纯几何的拓扑不变量。C 在东北 (0.150, 0.120) 时，两个任务从最后一个轨道点
直线去 C 都穿过锚点对径射线，闭合计数 = 柱上读数 + 1（rope_winding 读 3）。统一做法是把 **C 挪到
柱的南侧 (0.075, −0.130)**（方位 292°，在 150°~335° 的允许区内）：两个任务直线去 C 都不穿对径射线，
闭合计数 = 柱上圈数，`to_C_around` 不再需要（`to_c_route: straight`），rope_winding 的判据改为
`success.winding_metric: closure`、oracle 不变。离线门：rope_winding 1/2/3 圈松弛 11.1% / 9.1% /
10.6%（配对表 155/200/230 不变），rope_unwinding 三档 8.5% 起不变。GPU 验证（2026-08-27，rope_winding 两圈，C 挪后）：`success=True`，闭合计数与柱上读数在 `wind_t1_08` / `wind_t2_08` / 终态全部相等（1 / 2 / 2），`placement_error_xy=0.0002`，21/21 航点。rope_unwinding 一圈（直线去 C，13 航点）：`success=True`，闭合计数与柱上读数均 0，`contact_nodes=76`（绳完全脱离柱面），`placement_error_xy=0.0011`。两个任务在同一口径下闭环。

### 6.2 2026-08-27 一圈 A/B：`plug_spin_tracks_orbit`

开：`twist_net=-1.08`，终态 `contact_nodes=479`；关：`twist_net=+0.02`，`contact_nodes=57`，
其余判据相同。解绕时插头自转与绳的扫掠同向叠加而不是抵消（绕柱任务里它是为抵消设计的），
本任务默认关闭。


2026-08-26 首跑（start_turns=1，GPU，无 viewer）：`success=True`，`winding_number=0.000`
（`swept_turns=+0.156`，`turn_complete` 时已读 0），`placement_error_xy=0.0034`，13/13 航点，
`wound_max_z=0.005`（解下来的绳躺在柱脚旁的板面上，没有越顶）。`post_contact` 沿轨道单调下降
（2079 → 1009 → 479），即圈是逐渐剥离而不是整体上滑。`twist_net` 累计 −1.1 圈，
`pad_gap` 最小 1.4 mm（绳末段贴在指垫上）——与 rope_winding 的同类读数相当，待 A/B
`plug_spin_tracks_orbit`。

2026-08-27 失败对照例（`task.winding.orbit_direction=ccw`，轨道与缠绕同向）：`success=False`，
`winding_number=+2.000`（`swept_turns=+2.298`），`below_post_top=True`，`placement_error_xy=0.0034`，
13/13 航点——同样的抓取、同样的放置终点，只有拓扑不同，与任务书 §2.5 的对照定义一致。


```bash
python tests/check_rope_unwinding_geometry.py                     # 离线门，默认 start_turns=1
python tests/check_rope_unwinding_geometry.py --start-turns 3
python -m demos.routing.rope_unwinding_physical_handle_demo run.probe=true | tee runs/rope_unwinding_x1.log
python -m demos.routing.rope_unwinding_physical_handle_demo run.randomize_layout=true run.seed=3   # 变体（§7）
python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.start_turns=2 | tee runs/rope_unwinding_x2.log
python -m demos.routing.rope_unwinding_physical_handle_demo task.winding.orbit_direction=ccw | tee runs/rope_unwinding_wrong_way.log
```

实跑观察项：出生静置后 `winding_number` 读 ±start_turns、`post_contact` 稳定；每个
`turn_complete` 读数减 1；终态 winding 0、`placement_error_xy` 在容差内；多余绳段的去向。

## 7. 变体轴与派生（2026-09-04，变体计划 §6.2 第 7 步）

按 linkbar / diverter / gate / band / c_ring / bar 的六项清单部署：yaml `variation:` 块、`checks()` 与派生钩子、demo 接线 +
variant 行 + run 配置键、`check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测。参考样例 `docs/develop/tasks/bar_through_hole_zh.md` §3–§6。
没有防捷径离散轴：方向由物理本身守（同向轨道读 2·start_turns），`winding.direction` 是实例轴。

**物理图景。** 绳出生时绕柱 `start_turns` 圈（§1）。出生路线 `routes.initial` 是四个条目：S 中心（坐标）→ `lead_in_toward`（S 沿指向柱心的方向
水平走 40 mm，见 §3 折角的理由）→ `helix_around`（圈数 / 方向 / 首圈高度 / 圈距读 `winding` 块）→ `tail_arc`（沿最上一圈的切线离开、向远离柱子的一侧
弯 `spawn_arc.sweep_deg` 130°、弦长 `spawn_arc.chord` 0.216，弦终点即插头出生点）。除 S 外都是 Layout 规则（`planning/waypoint.py` 的
`lead_in_route_point` / `tail_arc_route_points`，`cable_routing.py::route_polyline` 解析），S / POST / 圈数 / 方向一变路线跟着变。

**术语。** 松弛 = (绳长 − `taut_demand`) / `taut_demand`，带 [5%, 15%]（§3）；闭合计数 = `winding_topological`（§6.1）；首抽拒绝率 = 1000 个 seed 里
第一次抽样就被派生 / 校验拒掉的比例，门 2%（`tests/check_variant_rng.py` 的 `MAX_REJECTION`）；角点 = 连续轴两端 × 离散轴全部取值的组合
（`tests/check_variant_corners.py`）；对照组 = `winding.orbit_direction=same`（轨道与缠绕同向，新关键字，sweep 脚本不知道该 seed 抽到哪个方向）。

### 7.1 轴

| 类 | 叶子 | 抽法 | 基准 | 说明 |
|---|---|---|---|---|
| A | `winding.start_turns` | Cat{1, 2, 3} | 1 | 难度候选。一格耗时 8 / 13 / 18 min |
| A | `winding.direction` | Cat{ccw, cw} | ccw | **cw = 镜像布局**：yaml 的 fixture 位置一律按 ccw 写，`RopeUnwindingLayout.fixture_pos` 在 cw 时把三个 fixture 的 y 取反（对机械臂 x 轴镜像）。底座与工作区都关于 y=0 对称，两个方向的十二行读数完全相同（离线门有一行断言出生折线与航点逐点镜像）。先试过「只翻缠绕、S / C 不动」：插头出生到东北角，首抽拒绝率 21%（可达 0.806、出生折线贴工作区边），弃用 |
| B | `fixtures.POST.x` / `.y` | U[−0.020, 0.060] × 2 | 0.020 / 0.020 | 柱位置 ±0.040。`pos: [x, y, z]` 拆成 `x / y / z` 三个标量键（随机化器不支持列表下标；`CableRoutingLayout.fixture_pos` 对没有 `pos` 的 fixture 读三个键，rope_winding 的 yaml 不动） |
| B | `fixtures.S.x` / `.y` | U[−0.180, −0.120] / U[0.070, 0.130] | −0.150 / 0.100 | 端子 ±0.030 |
| B | `fixtures.C.y` | U[−0.160, −0.100] | −0.130 | 靶心 y ±0.030 |
| B→C | `fixtures.C.x_frac` → `fixtures.C.x` | U[0, 1] **派生** | 0.075 | `x_range` [0.045, 0.105] 挖掉离插头出生点 < 0.040 的一段（插头法兰 0.015 + 靶心半长 0.020 + 5 mm），frac 按剩余区间长度映射。独立抽 C.x 时 3.3% 的抽样让 C 落在插头旁；插头出生点随柱与锚点走（锚点几乎正西时尾弧向东离开、插头到柱的东侧），所以挖的是整个净空盘，不是只抬下端 |
| B | `winding.climb_per_turn` | U[**0.012**, 0.016] | 0.014 | 圈距。计划表的下界 0.010 被 GPU 首跑切掉（§7.4 seed 6：3 圈 × 0.0102 建场景时 tetgen 报管皮自交）；离线 tetgen 扫 圈数 × 圈距 × 首圈高度 × 端子距（§7.4 表）：0.010 在 ≥ 2 圈几乎全失败、0.011 在 3 圈且最上一圈 ≥ 0.083 失败、≥ 0.012 全过、与端子距无关。0.008 = 2·绳半径实测零间隙失败 |
| B→C | `winding.wind_z_frac` → `winding.wind_z_start` | U[0, 1] **派生** | 0.045 | 最下一圈高度，区间 [0.035, min(0.055, 柱顶 0.105 − 0.010 − 绳半径 0.004 − start_turns·climb)]；3 圈 × 0.016 时 [0.035, 0.043]，恒非空 |
| C（Layout 规则，无叶子） | 引入点、插头出生点、尾弧弯向、cw 镜像 | 派生 | | 见物理图景 |
| D | `spawn_arc.sweep_deg` 130（改为幅值）、`spawn_arc.chord` 0.216（新键）、`wind_radius` 0.140、`to_c_route: closure`（原 straight；planner 只在直线去 C 会多算一圈时加 `to_C_around`，基准路线不变）、`plug_spin_tracks_orbit=false`、`rest_shape=spawn`、柱高 | 固定 | | 松弛对位置抖动不敏感：\|S−柱\| 同时进供给（引入段）和需求，1000 seed 松弛 6.8–10.6%，所以 sweep 不随位置反解 |

三个字面量副本（角点门裸加载 task yaml，`${prefabs…}` / `${common…}` 解析不了）：`rope.radius` 0.004、`POST.base_height` 0.010、`workspace.x/y`；
`RopeUnwindingSceneBuilder.build` 断言与 prefab / common 相等。

派生顺序（`derive_task_cfg`）：`wind_z_frac → wind_z_start`（要圈数与圈距），再 `C.x_frac → C.x`（要插头出生点，即要 POST / S / 圈数 / 方向）。

### 7.2 `checks()` 十二行

纯函数在 `topogym/tasks/routing/_rope_unwinding_geometry.py`（numpy + planner，不 import Genesis；`cable_routing.py` 模块级 import 了 Genesis，
所以离线门一直用 stand-in layout），接收任何提供 `fixture_pos / route_point / route_polyline / world_z` 的布局对象；`RopeUnwindingLayout.checks()`
与离线门的 `UnwindingStandIn` 读同一份。行里跑真实 planner（不建场景），可达与松弛读的是 oracle 的实际航点。

| 行 | 读数 | 门 | 基准 | 1536 角点最紧 |
|---|---|---|---|---|
| `anchor_clears_post` | \|S−POST\|_xy − (引入 0.040 + 螺旋半径 0.026) | ≥ 0.020 | 0.122 | 0.0345（S (−0.12, 0.07)、POST (−0.02, 0.06)） |
| `wraps_below_post_top` | 柱顶 − 0.010 − (wind_z_start + start_turns·climb + 绳半径) | ≥ 0 | 0.032 | 0（`wind_z_frac=1` 构造取等） |
| `bottom_wrap_above_base` | wind_z_start − 绳半径 − `POST.base_height` | ≥ 0 | 0.031 | 0.021 |
| `wrap_gap` | climb − 2·绳半径（相邻两圈管皮的间隙） | ≥ 0.004 | 0.006 | 0.004（climb 0.012 取等） |
| `tail_clears_post` | 尾弧各点离柱轴最小距离 − (柱半径 + 3·绳半径) | ≥ 0 | 0.0058 | 0.0058（常量：尾弧形状不随轴变） |
| `spawn_in_workspace` | 出生折线到工作区 x / y 边界的最小距离 | ≥ 0.040 | 0.086 | 0.0411（POST (0.06, −0.02)、S (−0.18, 0.07)：插头 y −0.259） |
| `plug_clears_target` | \|插头出生点 − C\|_xy | ≥ 0.040 | 0.137 | 0.040（`C.x_frac` 取窗口端点） |
| `palm_clears_post_top` | 最低轨道高度 + `PALM_ABOVE_PADS` − 柱顶 | > 0 | 0.017 | 0.007（wind_z_start 0.035） |
| `hand_reach` | 规划航点离 `reach.base_xy` (−0.570, 0) 的最大距离 | ≤ `reach.max_hand_dist` 0.780 | 0.727 | 0.7727（POST x 0.060） |
| `slack_in_band` | 松弛 | ∈ [0.05, 0.15] | 8.2% | 6.6% |
| `spawn_reads_start_turns` | \|`spawn_winding` − sign·start_turns\| | < 1e−6 | 0 | 0 |
| `free_end_reads_target` | 出生读数 + `free_end_winding_delta`(自由端全程) − 0 | = 0 | 0 | 0 |

`reach.max_hand_dist` 0.780 是新键、是假设：bar / gate / c_ring 的 0.700 是落座高度的口径，本任务手在 0.05–0.10 高、基准布局已经 0.727。
角点子集先跑 POST x = 0.060 的格（c1248 / c1504），跟随误差中止就把 `POST.x` 上界收到能过的值并把实测写回这个键。

### 7.3 离线实测（2026-09-04）

| 门 | 结果 |
|---|---|
| `tests/check_rope_unwinding_geometry.py`（默认 / `--start-turns 2` / `3`） | PASS：原 18 行不变（尾弧折角 2°，是螺旋采样弦与弧首段的离散差；改前手写点 5°）；松弛 8.2 / 8.6 / 8.9%（改前 8.5 / 8.9 / 9.2%，插头西移 28 mm）；新段 variation envelope：引入点还原 (−0.1138, 0.0830)、插头 (−0.0338, −0.2137)、frac 0.5 还原 wind_z_start 0.045 与 C.x 0.075、3 圈 × 0.016 区间 [0.035, 0.043]、cw 出生折线与 13 个航点逐点镜像、十二行基准全过、**1536 角点全部可行**、三个负例（POST x 0.060 对 0.700 可达门拒；S 离柱 42 mm 拒；3 圈 × climb 0.010 被 `wrap_gap` 拒） |
| `tests/check_rope_winding_geometry.py` | PASS（rope_winding 不回归：stand-in 的改动是回退分支与新条目） |
| `tests/check_variant_rng.py` rope_unwinding 段 | 叶子顺序、seed 3 确定性、1000 seed 每轴在区间内、`wind_z_start` 与 `C.x` 逐 seed 等于派生公式、C 离插头 ≥ 0.040、十二行全过、三档圈数 371 / 327 / 302、ccw / cw 509 / 491、最大可达 0.772、松弛 6.9–10.7%；首抽拒绝率 **0.000**（未派生前：独立抽 C.x 时 3.3%、不镜像的 cw 21%） |
| `tests/check_variant_corners.py --task rope_unwinding` | **1536 角点 1536 可行**，Hydra compose 读数一致（派生叶子 `C.x` / `wind_z_start` 作为 `task.*` 覆盖传给固定布局路径） |
| `tests/check_configs_compose.py`、`tests/check_demo_configs.py` | PASS（rope_winding 的 run yaml 同时补了 `randomize_layout` / `difficulty`：demo 共用，键必须存在；rope_winding 还没有 variation 块，开了也是空操作） |

### 7.4 GPU 实测（4090，共用，2026-09-04 起）

固定布局基准复跑（1 圈，插头出生点由推导给出，比手写点西移 28 mm；`runs/rope_unwinding_variation/20260904_baseline/fixed_x1.log`）：
`task_success=True`，13/13 航点，闭合计数 `turn_complete` 读 0、终态 0，`placement_error_xy=0.0012`，终态 `contact_nodes=0`（绳完全脱离柱面），
`twist_turns` +0.92。与 08-27 的一圈结果（放置 1.1 mm，`contact_nodes` 76）同量级。

**首跑（climb 下界 0.010，`runs/rope_unwinding_variation/20260904_seeds_firstrun/`）暴露的隐含假设：出生管皮的网格生成。** seed 0–5、7 oracle 7/7 PASS
（其中 cw 镜像 4 格、2 圈 2 格），seed 6（3 圈、climb 0.0102、wind_z_start 0.0417）建场景时 tetgen 报 `The input surface mesh contain self-intersections`，
物理一步没跑。离线复现：`RopeUnwindingLayout.rope_mesh("initial")` 的管皮直接送 tetgen（与 Genesis 同一套 switch `pq1.1/10a5e-08`），扫 圈数 × 圈距 × 首圈高度，
端子位置取基准 / 最近 / 最远三处（结果与端子距无关）：

| 圈数 \ 圈距 | 0.010 | 0.011 | 0.012 | 0.013–0.016 |
|---|---|---|---|---|
| 1 | 过 | 过 | 过 | 过 |
| 2 | 首圈 ≤ 0.040 过，≥ 0.045 失败 | 过 | 过 | 过 |
| 3 | 全失败 | 首圈 ≤ 0.045 过，≥ 0.050（最上一圈 ≥ 0.083）失败 | 过 | 过（柱顶窗口内） |

机制：管皮相邻两圈的间隙 = climb − 8 mm；出生中心线过 Catmull-Rom 样条，最上一圈接尾弧、最下一圈接引入段的两处拐点样条有过冲，
间隙 2–3 mm 时过冲的管皮碰到相邻圈。这是网格生成的硬边界（不是执行链的假设），按 `variation_and_difficulty_plan_zh.md` §4.3「CRASH 集中在某轴的包络边缘 → 该轴收窄」
处置：`climb_per_turn` 下界 0.010 → **0.012**（管皮间隙 4 mm），`checks()` 的 `wrap_gap` 门 0.002 → 0.004。seed → 变体映射随之改变（每个 seed 的 climb 都变），
所以 seed 0–9、wrong_way、角点子集全部按新包络重跑；重跑前离线 tetgen 复核 10 个 seed 与 12 个角点的管皮全部可四面体化。

seed 0–9（`bash_scripts/tests/rope_unwinding_variation_sweep.sh oracle visual`，`runs/rope_unwinding_variation/20260904_seeds/`）、
wrong_way seed 0–2（`…/20260904_wrong_way/`）、角点子集 12 格（`variant_corners_sweep.sh rope_unwinding oracle`，`runs/rope_unwinding_corners/20260904/`，
子集清单 `runs/rope_unwinding_variation/corner_subset.txt`：每行最紧的 ccw / cw 各一格 —— 可达最远 c1248 / c1504、手掌离柱顶最近 c1024 / c1280、
插头贴靶心 c1224 / c1480、出生折线贴工作区边 c1152 / c1408、锚点最贴柱 c1120 / c1376、需要绕远侧去 C 的 c1052 / c1308）。

**seed 0–9 oracle（新包络）：10/10。** 位置是物理位置（cw 格已镜像，task 系）；`contact` 是终态柱面接触粒子数（`rope_winding_verify` 行），
`twist` 是终态 `twist_turns`；耗时含与另两个 GPU 租户共用。

| seed | T | 向 | POST (x, y) | S (x, y) | C (x, y) | climb | wind_z | 插头出生 | 松弛 | 航点 | 闭合计数 | 放置 | contact | twist | 耗时 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 2 | cw | (+0.039, −0.051) | (−0.144, −0.124) | (+0.059, +0.127) | 0.0127 | 0.0428 | (+0.001, +0.186) | 8.3% | 21/21 | 0 | 0.0005 | 1692 | −0.65 | 692 s |
| 1 | 1 | cw | (−0.012, +0.019) | (−0.164, −0.115) | (+0.071, +0.137) | 0.0130 | 0.0414 | (−0.126, +0.230) | 7.8% | 13/13 | 0 | 0.0019 | 109 | −0.70 | 513 s |
| 2 | 1 | cw | (+0.014, −0.007) | (−0.153, −0.096) | (+0.088, +0.101) | 0.0159 | 0.0366 | (−0.051, +0.224) | 7.8% | 13/13 | 0 | 0.0014 | 89 | −0.69 | 487 s |
| 3 | 1 | ccw | (+0.041, +0.000) | (−0.169, +0.084) | (+0.095, −0.154) | 0.0143 | 0.0406 | (+0.011, −0.238) | 7.5% | 13/13 | 0 | 0.0011 | 0 | +0.92 | 482 s |
| 4 | 2 | ccw | (+0.057, −0.020) | (−0.135, +0.109) | (+0.089, −0.159) | 0.0129 | 0.0532 | (−0.022, −0.247) | 8.4% | 21/21 | 0 | 0.0013 | 1572 | +0.86 | 755 s |
| 5 | 1 | ccw | (−0.005, −0.010) | (−0.149, +0.129) | (+0.097, −0.111) | 0.0157 | 0.0386 | (−0.129, −0.215) | 7.8% | 13/13 | 0 | 0.0021 | 564 | +0.88 | 718 s |
| 6 | 3 | ccw | (−0.003, −0.004) | (−0.163, +0.122) | (+0.080, −0.118) | 0.0122 | 0.0415 | (−0.104, −0.221) | 8.4% | 29/29 | 0 | 0.0018 | 2722 | +1.35 | 1761 s |
| 7 | 1 | cw | (+0.034, +0.007) | (−0.142, −0.096) | (+0.064, +0.153) | 0.0151 | 0.0451 | (−0.036, +0.237) | 8.0% | 13/13 | 0 | 0.0009 | 33 | −0.70 | 904 s |
| 8 | 2 | ccw | (+0.037, −0.017) | (−0.164, +0.073) | (+0.045, −0.114) | 0.0155 | 0.0537 | (−0.005, −0.253) | 8.8% | 21/21 | 0 | 0.0015 | 298 | +0.89 | 1427 s |
| 9 | 1 | cw | (+0.014, −0.053) | (−0.180, −0.083) | (+0.063, +0.115) | 0.0155 | 0.0510 | (+0.030, +0.186) | 8.6% | 13/13 | 0 | 0.0006 | 0 | −0.70 | 848 s |

- 十格全部 `task_success=True`，航点全走完，闭合计数终态 0，放置误差 0.5–2.1 mm（容差 18 mm）。
- **镜像轴生效**：cw 5 格（seed 0 / 1 / 2 / 7 / 9）出生缠绕 −start_turns、oracle 反向（ccw）轨道、去 C 直线；`twist_turns` 符号随方向翻转（cw −0.65 … −0.70，ccw +0.86 … +1.35），量值与 08-27 的一圈 A/B 相当。
- 十格都没用到 `to_C_around`（`detour=0`）：C 在 [0.045, 0.105] × [−0.160, −0.100] 的方位角始终落在允许区。
- **松绳贴柱脚**（§5 风险 1 的实测）：终态 `contact_nodes` 从 0（seed 3 / 9）到 2722（seed 6，三圈）；两圈 / 三圈格解下的绳堆在柱脚、贴着柱面（`wound_max_z` 在 task 系 0.014–0.040，即柱底附近），闭合计数不受影响（读 0），也没进夹爪路径。圈数越多贴柱越多，是划档时圈数轴的旁证。
- 三圈格（seed 6）29 航点 1761 s：三个 GPU 租户共用时约为 08-27 单独跑（18 min）的 1.6 倍。

**visual 10/10**：每格 `run.max_waypoints=1`（抓起插头就停）录像，`visual_s*.mp4` 有帧，柱 / 端子 / 靶心位置、圈数、方向（cw 镜像）逐 seed 不同。

**wrong_way 首跑暴露的第二个隐含假设：对照组的强制轨道进了布局校验。** 三格都在 `randomize_task_cfg` 里被拒 21 次（`RuntimeError: layout rejected 21 times`）：
sweep 的对照组覆盖 `task.winding.orbit_direction=same` 在随机化之前就写进了配置，`checks()` 的 `free_end_reads_target` 行用它规划，
`to_c_route: closure` 的 planner 在同向轨道下找不到任何一条去 C 的路线能把闭合计数凑到 0，抛错 → 每次抽样都被拒。08-27 的固定布局对照例没碰到，
因为那时 `to_c_route` 是 `straight`。两处都按「修执行链」处理：`checks()` 一律用 oracle 自己的轨道方向评估布局（`_oracle_view`：拷贝配置、清掉
`orbit_direction`，行判的是布局不是策略）；planner 在轨道被强制且绕远侧也凑不对时不再抛错，改走直线（`targets.pop()`），让判据去读 2·start_turns。
离线门加两行：`orbit_direction=same` 下十二行不变；需要 `to_C_around` 的布局在强制轨道下少一个航点（30 → 29）。wrong_way 三格排在角点子集之后重跑。

**角点子集首跑暴露的第三个隐含假设：贴柱节点数的绝对门。** c1120（3 圈、climb 0.012、锚点离柱最近 0.100）第一圈末 `post_contact_safety_abort`，
`contact_nodes=5001 > safety_max_contact_nodes 4800`；同圈数同圈距的 c1024 通过。离线把出生管皮四面体化后数柱面带内的节点：c1120 11913、c1024 11552、
基准三圈（08-27 通过）11618，只差 3%（模拟器读数约是四面体节点数的 0.44 倍：基准一圈出生静置读 2011，离线 4577）。也就是说三圈出生时贴柱节点本来就
≈ 5000，与 4800 的门齐平；这个门是 rope_winding 按「两圈缠满的峰值 x 2」标定的绝对数（yaml 注释），本任务出生圈数是轴，绝对数在三圈格随机压线。
按「修判据定义不动包络」处理：demo 在出生静置后记一次 `post_contact`（新行 `post_contact_baseline`），门 = max(`safety_max_contact_nodes`,
`safety_contact_growth` 1.5 × 出生贴柱数)，守的是「整根绳堆到柱上」这种增长；rope_winding 出生贴柱 0，门不变。c1120 排在 wrong_way 之后重跑。

**wrong_way seed 0–2（修后重跑）：3/3 判失败。** seed 1 / 2（1 圈 cw）13/13 航点走完，闭合计数 −2 = 2·start_turns，`physical_success=True`、
`task_success=False`（与 08-27 的固定布局对照例同型）；seed 0（2 圈 cw）第一圈末读 −3（同向轨道把绳越缠越多），第二圈开头贴柱数 5437 超过
出生值的 1.5 倍被守卫中止，同样判失败。对照组的物理就是「继续缠」，守卫中止是预期内的结束方式。

**角点子集 12 格：10/12 通过，两个失败格都是「锚点离柱最近」（S (−0.12, 0.07)、POST (−0.02, 0.06)，|S−柱| = 0.100）的 ccw / cw 镜像对。**

| 角点 | 取的极值 | T | 向 | POST | S | C | 航点 | 闭合计数 | 放置 | contact | 耗时 | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c1024 | 最低轨道、手掌离柱顶最近 | 3 | ccw | (−0.02, −0.02) | (−0.18, 0.07) | (0.045, −0.16) | 29/29 | 0 | 0.0014 | 1891 | 1916 s | PASS |
| c1280 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 29/29 | 0 | 0.0012 | 2666 | 1100 s | PASS |
| c1052 | 需要绕远侧去 C | 3 | ccw | (−0.02, −0.02) | (−0.18, 0.13) | (0.105, −0.10) | 30/30（含 `to_C_around`） | 0 | 0.0020 | 2739 | 1902 s | PASS |
| c1308 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 30/30 | 0 | 0.0020 | 2372 | 1183 s | PASS |
| c1152 | 出生折线贴工作区边 | 3 | ccw | (0.06, −0.02) | (−0.18, 0.07) | (0.045, −0.16) | 29/29 | 0 | 0.0009 | 2235 | 1084 s | PASS |
| c1408 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 29/29 | 0 | 0.0008 | 2301 | 1115 s | PASS |
| c1224 | 插头出生贴靶心净空 | 3 | ccw | (0.06, 0.06) | (−0.18, 0.07) | (0.105, −0.16) | 29/29 | 0 | 0.0002 | 2134 | 1227 s | PASS |
| c1480 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 29/29 | 0 | 0.0001 | 2515 | 965 s | PASS |
| c1248 | 可达最远（手 0.7727） | 3 | ccw | (0.06, 0.06) | (−0.12, 0.07) | (0.045, −0.16) | 29/29 | 0 | 0.0005 | 2907 | 1145 s | PASS |
| c1504 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 29/29 | 0 | 0.0002 | 2683 | 921 s | PASS |
| c1120 | 锚点最贴柱 | 3 | ccw | (−0.02, 0.06) | (−0.12, 0.07) | (0.045, −0.16) | 10/29 | — | — | 5001（第一圈末） | 393 s | 守卫中止（绝对门 4800） |
| c1376 | 同上镜像 | 3 | cw | 同上 | 同上 | 同上 | 18/29 | — | — | 7388（第二圈末） | 554 s | 守卫中止（出生值 × 1.5） |

- 可达行成立：柱 x = +0.060 的四格（c1152 / c1408 / c1224 / c1480 / c1248 / c1504，手离底座 0.770–0.773）全过，`reach.max_hand_dist` 0.780 的假设没被切。
- 绕远侧的两格（c1052 / c1308）`to_C_around` 生效，闭合计数 0；不加它直线去 C 会读 +1。
- 每格都是 3 圈、圈距 0.012（角点门取每行最紧值时圈数取 3），耗时 15–32 min（GPU 三个租户共用）。

**c1120 / c1376 的诊断（`runs/rope_unwinding_corners/20260904_diag/`，守卫放到 3 倍、`run.probe=true`）：c1376 `task_success=True`**，29/29，闭合计数
逐圈 −2 / −1 / 0，放置 0.5 mm。贴柱数轨迹：出生 4857 → 第一圈剥离时降到 3890 → 第二圈起回升 → 第三圈末 8119、去 C 时 8130（出生值的 1.67 倍）。
机制：锚点离柱只有 0.100，解下来的三圈绳（每圈 0.15 m）没有别处可去，堆在柱脚并贴着柱面绕了不到一圈（`on_post_winding` −1、`swept_turns` −0.65，
闭合计数 0 —— 正是 §6.1 把判据改成 closure 的那种情形），`twist_turns` 终态 −3.43（三圈 + 松绳贴柱的自转，只报不判）。
**c1120 同样 `task_success=True`**：出生 4901 → 最低 3972 → 峰值 8027（1.64 倍），闭合计数 +2 / +1 / 0，放置 0.6 mm，`twist_turns` +3.11（镜像对的符号相反）。
所以「贴柱数超过出生值的 1.5 倍」不是发散，是这个角点的正常物理；c1120 在 1.5 倍门下也是第三圈开头 7382 中止（1.51 倍）。
守卫再改一次定义（修判据，包络不动）：门 = max(`safety_max_contact_nodes`, `safety_max_contact_fraction` × 全绳节点数)，取 0.85 —— 这就是
rope_winding 原标定「阈值 3000 / 全绳 3399」的口径（88%），`post_contact_baseline` 行同时打印全绳节点数。两格按新门重跑
（`runs/rope_unwinding_corners/20260904_anchor_retry/`）：**c1120 / c1376 都 PASS**，全绳 10520 / 10531 节点（门 8942），出生贴柱 4888 / 4880，
终态 7694 / 7724（73%），闭合计数 0，放置 0.6 / 0.5 mm，29/29。角点子集最终 **12/12**。

**六项交付的 GPU 结论。** 固定布局复跑通过；seed 0–9 oracle 10/10、visual 10/10；wrong_way 3/3 判失败；角点子集 12/12。三次首跑失败都不是包络问题：
一次网格生成的硬边界（圈距下界收到 0.012，唯一的包络改动），两次执行链的隐含假设（对照组覆盖进了布局校验；贴柱守卫的绝对门按两圈标定），与
diverter / gate / c_ring / band / bar 的先例同型。

### 7.5 文件集

```
configs/task_configs/rope_unwinding_topogym_tabletop_v1.yaml   fixture x/y/z、routes.initial 规则条目、spawn_arc 幅值 + chord、wind_z_frac、C.x_frac / x_range、reach、workspace 副本、variation 块
configs/run_configs/rope_unwinding.yaml                        randomize_layout / difficulty / variant_id（rope_winding.yaml 同步补键）
topogym/planning/waypoint.py                                   lead_in_route_point、tail_arc_route_points
topogym/planning/rope_winding_planner.py                       post_top_z 走 fixture_pos；orbit_direction 接受 same
topogym/tasks/routing/cable_routing.py                         fixture_pos 读 x/y/z；route_polyline 新条目 lead_in_toward / tail_arc，helix_around 参数缺省读 winding；builder 的 layout_cls
topogym/tasks/routing/_rope_unwinding_geometry.py              新：mirror_sign、wind_z_bounds/from_frac、target_x_windows/from_frac、rope_unwinding_checks（十二行）
topogym/tasks/routing/rope_unwinding.py                        RopeUnwindingLayout（镜像 fixture_pos、checks、validate）、builder 断言字面量副本、derive_task_cfg / validate_task_cfg
demos/routing/rope_winding_physical_handle_demo.py             randomize_task_cfg 接线、variant 行、checks 行、post_contact_baseline 行与 safety_max_contact_fraction 门（rope_winding 共用）
topogym/planning/rope_winding_planner.py                       （另）强制轨道下 closure 路线退回直线
tests/check_rope_winding_geometry.py                           StandInLayout：x/y/z 回退、新条目
tests/check_rope_unwinding_geometry.py                         UnwindingStandIn、resolve 断言字面量副本、variation envelope 段（还原、镜像、1536 角点、负例）
tests/check_variant_rng.py                                     rope_unwinding 段（1000 seed 拒绝率 0.000）
tests/check_variant_corners.py                                 TASKS 登记（1536 角点）
bash_scripts/tests/rope_unwinding_variation_sweep.sh           新（visual / oracle / wrong_way）
bash_scripts/tests/variant_corners_sweep.sh                    rope_unwinding 分支（对照组 wrong_way）
runs/rope_unwinding_variation/20260904_baseline/               固定布局复跑
runs/rope_unwinding_variation/20260904_seeds_firstrun/         首跑（climb 下界 0.010，seed 6 tetgen 自交）
runs/rope_unwinding_variation/20260904_seeds/                  seed 0–9 oracle + visual（最终包络）
runs/rope_unwinding_variation/20260904_wrong_way_firstrun/     首跑（对照组覆盖进校验，三格被拒）
runs/rope_unwinding_variation/20260904_wrong_way/              wrong_way seed 0–2（修后）
runs/rope_unwinding_corners/20260904/                          角点子集 12 格首跑（10/12；c1120 绝对门、c1376 1.5 倍门中止）
runs/rope_unwinding_corners/20260904_diag/                     c1120 / c1376 诊断（守卫 3 倍、probe）
runs/rope_unwinding_corners/20260904_anchor_retry/             c1120 / c1376 按 0.85 全绳节点门重跑（PASS）
```
