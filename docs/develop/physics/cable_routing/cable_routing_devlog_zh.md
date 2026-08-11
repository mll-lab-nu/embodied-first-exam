# 开发日志：任务迁移到新架构 + Cable Routing 打磨

> 日期：2026-07-08
> 目的：用大白话记录这一轮做了什么、为什么这么做、还差什么。看这份就能接着往下干。

---

## 一句话总结

把 `peeling` 和 `cable_routing` 两个任务接到了新的分层架构上（`generation` 生成 + `planning` 规划 + `supervision` 监控），顺手把桌面、终点靶心这些观感问题改了，并诊断了两个物理 bug（两桩之间的停顿、放置时绳子飞出）。

---

## 1. 文档整理（docs/develop/modules）

背景：`modules/` 里原来的 `A_world.md`~`G3_eval.md` 是一套**理想蓝图**，和现在真实代码对不上（代码里根本没有 `embodiment`/`policy` 这些模块）。

做了什么：
- 以 `overall_module_dict_zh.md` 作为**权威**说明。
- 给每个真实模块补了一份简单说明：`module_core / world / tasks / primitives / robot / utils / envs / prototypes.md`。
- 把过期的 A–G 蓝图挪到 `legacy_ag_blueprint/`，并写了 README 说明"别拿它理解现在的代码"。

结论：想看现在代码长什么样，先看 `overall_module_dict_zh.md` 和 `module_*.md`。

---

## 2. 什么是"新架构"（一分钟理解）

一局任务被拆成几层，各管一段，互不越界：

```
generation  这一局的输入条件（task_id + seed + 变式）→ EpisodeSpec
planning    这一局要怎么走（子目标 + waypoint）      → EpisodePlan
tasks/world 把它搭成 Genesis 场景
primitives  把 waypoint 变成真实物理动作（抓/拖/放）
supervision 运行时看护（接触太紧、穿透、跟随误差…）
prototypes  CLI/viewer/录制入口，只做"门牌号"，不塞主逻辑
```

好处：demo 脚本变薄，日志里能稳定看到 `episode_id / plan_id / stable_ready / export_ready`，方便复现和以后产数据。

---

## 3. Peeling 迁移

- 新增 `topogym/generation/peeling_generator.py`：生成单膜 Peeling 的 `EpisodeSpec`。
- 新增 `topogym/planning/peeling_planner.py`：把布料网格/粘附分组换算成"剥离→搬运→放置"的 waypoint 计划。
- `prototypes/peeling_physical_single_demo.py`：改成消费 spec/plan，最后返回结构化的 `EpisodeResult`。

验证：headless 跑通，架构日志正常。那次物理尝试本身失败（角落没提够高度）是 CPU 后端调参问题，和迁移无关。

---

## 4. Cable Routing 迁移

- 新增 `topogym/generation/cable_routing_generator.py`：生成 `EpisodeSpec`。
- 新增 `topogym/planning/cable_routing_planner.py`：把目标签名解析成自由端拖拽的 waypoint 计划。**顺手解决了一处重复**：绕桩/过渡的几何函数原来写在 `cable_routing_oracle_demo.py` 里、物理 demo 靠导入私有函数复用；现在统一搬进 planner，两个 demo 都从这里导入。
- `topogym/supervision/cable_routing.py`：把 rope/peg 的接触指标和 routing 验证（`rope_wrap_metrics` / `print_routing_verification` 等）抽出来，两个 demo 共用。
- `demos/routing/cable_routing_physical_handle_demo.py`：消费 spec/plan，返回 `EpisodeResult`。

至此"先 Swap 再扩展"迁移顺序里的 7 个任务（swap / onestroke / maze_wall_removal / stacked_plate / untangle / peeling / cable_routing）主力物理 demo 都完成了第一轮迁移。

---

## 5. Cable Routing 轨迹长什么样（速查）

自由端 handle 走的点（都在桌面上方，绕桩时会抬高一点）：

```
抓取 → 绕 P1 左侧 → （两桩之间过渡）→ 绕 P2 右侧一圈 → 切向出线 → 小步爬进 C 槽 → 卡住/松爪/撤离
```

注意：这个任务的 planner 其实是**直接读 config 里手写的 `endpoint_oracle_waypoints`**，不是算法现算的。要改轨迹 = 改这份点位表。

---

## 6. 这一轮的具体改动

### 6.1 去掉一个"真·停顿点" ✅
`green_exit_over_C` 和 `green_exit_to_C` 坐标完全一样，前者 340 步却零位移 = 纯发呆。已删除，末端几何不变。

### 6.2 绳子飞出——修复实验 #1 ✅（待 GPU 验证）
诊断：绳子是**实心四面体弹性管**，网格很细 + 体积约束偏硬 + 迭代少，被挤/急弯时 tet 翻转 → 爆解弹飞。
改了 `configs/task_configs/cable_routing_topogym_tabletop_v1.yaml`（都带 `[flyout experiment #1]` 注释、附旧值）：

| 项 | 旧 | 新 |
|---|---|---|
| `mesh.maxvolume` | 1.2e-8 | 5.0e-8（tet 变少） |
| `pbd.max_volume_solver_iterations` | 8 | 16 |
| `elastic.volume_compliance` | 0.0004 | 0.0020（更软） |

### 6.3 桌面边框（通用）✅
`topogym/world/tabletop.py` 加了 `_add_table_frame`：在桌面四周加一圈**无碰撞**的木色边框（默认开，`env.world.table.frame` 可调/可关）。所有走 `StandardTabletopSceneBuilder` 的任务都生效（symbolic peeling 和 common_room 走的是自己的建表路径，暂未覆盖）。

### 6.4 终点靶心 ✅
`topogym/tasks/routing/cable_routing.py` 加了 `_add_connector_target_marker`：在终点 C 画一个**红白同心方环**的无碰撞地贴，更显眼（`task.connector_target` 可调）。

---

## 7. 两个还没动代码、只做了诊断的问题

### 7.1 两桩之间的停顿（观感）
原因：`green_P1_top → green_between_pegs → green_P2_approach_mid` 形成 **下左→上右→下左** 的两个发夹弯（航向反转 ~159° 和 ~137°），机械臂到尖点必须减速反向 → 看着像停顿。没有运动曲线技巧能消除真实的方向反转。
建议修法：**删掉 `green_between_pegs`**，让 P1_top→P2_approach_mid 变成一条顺下去的线。风险：会改动 P1→P2 之间绳子的走线，要用 viewer 确认绕桩仍正确。**待批准后再动。**

### 7.2 放置到终点后绳子又飞出
触发点：`ConnectorLatch` 一旦吸附，会每步把 handle **硬 set 到目标位姿并强制摆正**（`connector_latch.py`），而绳子端点是焊在 handle 上的 → 一步之内被瞬移，正好赶上夹爪 attachment 释放。
能量来源排序：
1. **P2 处绳子绷太紧**（最可能）：放置时绳子缠 P2 最紧，硬吸附+释放把储存的张力从中段甩出。
2. **端点扎进桌子**（可能）：靠近 C 不抬高，端点若掉到桌面以下，碰撞冲量把它弹飞。
3. **latch 和夹爪 attachment 抢着控制同一个 handle**，几步内互相打架。
下一步：加一个探针（记录端点离桌面高度、P2 穿透量、粒子最大速度）跑到 C 附近，用数字确认是哪一个，再对症修。**待批准后再动。**

---

## 8. 待办清单

- [ ] #2：删 `green_between_pegs` 消除停顿（需 viewer 验证走线）。
- [ ] #4：加放置飞出探针 → 定位 → 修复。
- [ ] 实验 #1 若没完全压住飞出：试 #2（env `substeps` 4→8）或 #3（缩短 initial route 减少松弛）。
- [ ] 飞出稳定后，把那些为了"喂"绳子而堆的超大 `segment_steps`（全程约 7000 步）调小，测试会快很多。
- [ ] 还没迁移的 demo：`peeling_oracle_demo.py`、`cable_routing_oracle_demo.py`、各任务的 tabletop baseline。
- [ ] 桌面边框覆盖 symbolic `peeling.py` 和 `common_room.py`（如需要）。

---

## 9. 常用命令 & 小坑

跑 cable routing 物理 demo（GPU、看 viewer）：
```
python -m demos.routing.cable_routing_physical_handle_demo env.genesis.backend=gpu run.viewer=true run.allow_target_lag=true run.verbose=true
```
- **小坑**：这个 demo（以及 `untangle_physical_handle_demo.py`）**没有 `--keep-open`**，viewer 默认就一直开着，用 `--close-on-finish` 才关。别的 demo 才用 `--keep-open`。
- `--allow-target-lag`：不因 handle 落后目标点就中途 abort，这样能一路跑到 C 附近（复现飞出的地方）。
- 嫌慢加 `--viewer-speedup 4` 按比例压步数。

---

# iter 2（诊断探针 + 观感改动）

> 日期：2026-07-08

## 这一轮加了什么

1. **桌面边框**（`topogym/world/tabletop.py` 的 `_add_table_frame`）：桌面四周一圈无碰撞木色边框，默认开，`env.world.table.frame` 可调/可关。所有走 `StandardTabletopSceneBuilder` 的任务生效。
2. **终点靶心**（`topogym/tasks/routing/cable_routing.py` 的 `_add_connector_target_marker`）：终点 C 处红白同心方环无碰撞地贴，`task.connector_target` 可调。
3. **诊断探针 `--probe`**（`cable_routing_physical_handle_demo.py`）：包住 `scene.step`，每 `--probe-every` 步采样一次，专门回答两个问题——停顿是"卡住"还是"本身慢"，以及放置飞出到底是哪种原因。

## 探针打印什么

跑之前先打一张 **commanded 速度表**（每段"应该多快"）：
```
PROBE_PLAN phase=<段名> dist=<该段位移> steps=<步数> commanded_v=<位移/步数, m/步>
```
运行中每隔几步打一行 **实际状态**：
```
PROBE step=.. phase=<段名> hand_v=<实际每步手位移> handle_z_above=<handle离桌面高度>
  rope_minz_above_surf=<最低绳粒子离桌面高度> rope_spread=<绳子铺开范围>
  rope_jump=<绳粒子单步最大跳变> p2_gap=<P2穿透量> p2_contact=<P2接触粒子数>
  [STALL] [FLYOUT?]
```
- `STALL`：`hand_v` 低于阈值（手几乎不动）。
- `FLYOUT?`：绳子扎进桌面（`rope_minz_above_surf<0`）或单步跳变过大（`rope_jump` 爆表）。

## 怎么用它下结论

**问题 #2（两桩间的长停顿）——区分"卡住" vs "本身慢"：**
- 看 `green_between_pegs` / `green_P1_top` 附近的 `PROBE` 行：
  - 若 `hand_v` 掉到接近 0 并标 `STALL`，但同段的 `PROBE_PLAN commanded_v` 并不小 → **是方向反转（发夹弯）导致机械臂减速反向卡顿**，符合上一轮的尖点诊断。
  - 若 `hand_v ≈ commanded_v` 且两者都很小 → **是这段本身就被安排得很慢**（步数太多、位移太小），不是卡住，那就直接调小该段 `segment_steps` 即可提速。
  - 两者可能叠加：既是尖点、这段步数又大 → 停顿时间被放大。探针能量化到底哪个占主导。

**问题 #4（放置后绳子飞出）——区分三种成因：**
- 放置/`connector_latch` 前后几行 `PROBE`：
  - `rope_minz_above_surf` 变负 → **端点扎进桌子**（用户猜想 1）。
  - `p2_gap` 明显变负 / `p2_contact` 突然飙升 → **P2 接触太紧**（用户猜想 2）。
  - `rope_jump` 突然巨大（配合 `rope_spread` 暴涨）→ 抓到**爆解那一刻**，再回看上一行是上面哪个先越界，即为触发源。

## 现状

- 边框 / 靶心：代码已加，构建走到绳子四面体化（在这两个方法之后）都没报错，说明能正常建出来；最终以 viewer 里肉眼为准。
- 探针：`--probe` / `--probe-every` 已接好，`scene.step` 包裹顺序（probe→attachment→latch→genesis）已确认安全。

## 探针跑出来的结论（关键）

日志 `/tmp/cable_probe.log` 明确定位了飞出：

```
step=07090 phase=green_exit_pre_C rope_jump=17.27 rope_spread 0.16→166→169m
           p2_gap=+0.14 p2_contact=0 rope_minz_above_surf=+0.0017
```

- 绳子从抓取一路绕过 P1/P2 都是健康的（spread ~0.16m、jump ~0.0025），**在 `green_exit_pre_C`（终点 socket 处）一步炸开**（单帧粒子跳变 17m，spread 直接飙到 169m）。
- 炸的瞬间 `p2_contact=0`、`p2_gap=0.14`——**P2 张力完全无关，排除**；`rope_minz` 当时还在桌面之上——**扎桌也不是起因**（桌面以下是炸开之后的余波）。
- `green_exit_pre_C` 位置 `[0.221,-0.102]` 正好落在 C 的 socket 外框内（C=`[0.220,-0.095]`，outer 0.056）。physical demo 的 override 把 C 的 **socket 墙设成有碰撞**（`wall_height≈6mm`, `collision=True`）。**结论：机械臂拖着 handle（绳端焊在上面）横向"强行突破"那圈 6mm 的凸起碰撞墙，绳端一帧内深穿墙体，刚体↔PBD 接触求解把它弹飞 → 整根爆炸。用户的"凸起圈"猜想被证实。**

## 修复（已应用，待 GPU 复测）

在 `cable_routing_physical_handle_demo.py` 的 `load_configs` override 里，把终点 `C.collision` 从 `True` 改成 `False`（socket 仍可见、变成纯装饰红墙 + 红白靶心）。理由：C 是"要把绳子放进去"的目标，不该像障碍一样把绳子弹开；而卡入判定（ConnectorLatch）是几何 set_pos，不依赖墙体碰撞，所以照常工作。带注释、一行可回退（改回 `True` 即可做 A/B 对照）。

顺带确认：这也解释了为什么"实验 #1"（软化体积/tet）没压住飞出——触发源是**外部刚体接触**，不是绳子内部体积失稳，所以要从接触这边治。

## 还没做（部分已在下一节解决）

- ~~`green_between_pegs`（消两桩间停顿）~~ → 已被下面的平滑 S 形生成器整体取代。
- C 改成非碰撞后，若还想要"放进凹槽"的真实感，可另做：终点改成从正上方竖直下降入槽，而不是横向滑入。

---

# 平滑 S 形轨迹生成器（planner）

## 背景

原来自由端轨迹是 config 里手写的 18 个 `endpoint_oracle_waypoints`，有两个毛病：两桩之间"冲过去再折返"（两个 ~159°/137° 发夹弯），绕 P2 是贴着小半径的 5 点紧环容易卡。用户要的是一条**横放的 S 形**平滑曲线（绕 P1 左 → 过渡 → 绕 P2 右 → 进 C）。

## 做法（`topogym/planning/cable_routing_planner.py`）

新增 `_smooth_route_targets` + `_smooth_wrap_arc`，`routing.smooth_route=true` 时旁路手写点、改用参数化生成：

- 每个 peg = 一段**以 apex（signature 指定侧：P1 左 / P2 右）为中心的有界圆弧**，半径 = `peg_r + rope_r + smooth_clearance_{p1,p2}`。这样绝不会像切线带那样绕整圈。
- **入口端**取半绕角外侧（朝来向）；**出口端**朝"下一个节点方向"做 clamp（不越过 apex 反向），所以绕完直接朝下一站甩出去，不会冲过头再倒回来。
- 两个 peg 分别绕相反侧 → 天然拼成横向 S。
- 每段步数 = 段长 / `smooth_speed`，**匀速**（去掉爬行式停顿）。绕桩段抬高（`wrap_z_lift`），临近 C 落下。
- 末点 label 仍是 `green_exit_to_C`，对齐 `early_complete_segments` 和 latch，demo 不用改。

config 新增（`endpoint_oracle_waypoints` 保留，`smooth_route:false` 可一键回退对照）：
```yaml
routing:
  smooth_route: true
  smooth_clearance_p1: 0.030
  smooth_clearance_p2: 0.045   # 更宽，避免卡 P2
  smooth_arc_points: 9
  smooth_wrap_deg: 170         # 每个 peg 的半绕角
  smooth_speed: 0.0005         # m/步，匀速
```

## 纯几何自检（无需 Genesis）结果

迭代了几版（切线带最短弧 → 会绕整圈；对称 ±half → 出口冲过头 177° 尖点）后，最终 **apex 居中 + 出口朝下一站 clamp**：

- `max_heading_turn = 84°`（原手写路径 ~159°；无尖点，84° 是 S 弯的正常圆角）。
- `P1_left` dot 全为正（0.004~0.046）、`P2_right` dot 全为正（0.005~0.061）→ 两段确实各绕在指定侧、是**有界半绕**不是整圈。
- waypoint 轨迹：P1 `N→W→S`（凸左）→ 斜向过渡 → P2 `S→E`（凸右，~93°，收在东侧 apex 附近）→ 出到 C。一条干净的横向 S。
- 匀速：各段 commanded_v ≈ 0.0005 m/步，一致。

## 待 GPU 复测确认

几何已是平滑 S，但"绳子实际是否仍缠到 P1 左 / P2 右"只能靠运行时 `print_routing_verification` 在 viewer 里确认。

## 修正：按用户明确轨迹重建（取代抽象 S）

用户澄清实际想要的轨迹（机械臂初始朝向为北：raw 角 N=+x=0, W=+y=90, S=-x=180, E=-y=270，SE=225）：
**handle 从 P1 北侧穿过 P1/P2 中心 → 从东南(SE)入、绕 P2 一圈到朝 C 出**。之前的"抽象 left/right 半绕 S"没成功缠到两个桩，故按此重建 `_smooth_route_targets`：

- 从 layout 实时取 P1/P2/start/C 坐标。
- `gap_north_of_P1` = P1/P2 中点（在 P1 的 +x/北侧，可用 `smooth_p1_north_margin` 再往北推）。
- P2 绕弧：从 `smooth_p2_entry_deg`(默认 225=SE) 起、`smooth_p2_ccw`(默认 true=经东侧向北) 扫到朝 C 的出口角，半径 = P2半径+绳半径+`smooth_clearance_p2`。
- 匀速步数、末点 `green_exit_to_C`。

纯几何自检（NEWS 标注）确认：gap 在 P1 北侧、P2 弧从 SE 入经东侧到北出、末点到 C。所有形状都是 `smooth_*` 参数，方向/角度改配置即可，不用动代码。缠绕是否达标仍以 viewer 的 `cable_routing_verify` 为准。

## 第一次 GPU 复测：卡在 P2 内侧（reach 诊断）

第一次跑（`smooth_clearance_p2=0.045`，绕行半径 R2≈0.061）**失败**：
- log 里 `waypoint_complete` 显示 handle 只到 ~`(0.04,-0.08)`（P2 的**内侧/西北**），`target_error` 一路涨到 0.12，`p2_contact=0` 全程——**根本没绕到、绳子没碰到 P2**。
- **不是绳子不够长**：`routes.initial` 长 0.734m（余量巨大），handle 却只到离锚点 S 0.197m 处就卡住。所以是**物理卡顿**，不是绷紧。
- 原因：新弧太贴（R2 0.061），去 SE 入弧点要贴着 P2 内侧挤过去，夹爪卡住。旧手写路径能成是因为它绕了个**大回环**（离 P2 ~0.18m）。

修复尝试（纯配置）：`smooth_clearance_p2` 0.045 → 0.130 → 0.180，入弧角 225(SE)→270(正下方，从 gap 直接下探不往左兜)。

## 第二/三次复测：内侧入弧修好，但机械臂本体扫过 P2

- 入弧修好：entry=270 后所有绕行点都不再 `left_of_gap`，不再"擦着内圈进去"。
- **但机械臂前臂（base→EE 连线）扫过 P2**：机械臂底座在西侧(-0.570,0)，EE 绕到 P2 **东侧**时，前臂从西边伸到东边正好横穿 P2——自检里 loop_06/07/08 及 C 出口处前臂离 P2 只有 **0.014~0.05m**（P2 半径 0.012 + 臂杆 ~0.04→需要 ~0.06+）。把圈放大反而更糟：东侧点更靠东(x≈0.25)，前臂横穿 P2 更近(0.014)。
- **根因**：底座在西，任何把 EE 兜到 P2 东侧的绕法都会让前臂横扫 P2。**从零画圆无法兼顾机械臂本体体积**。
- 旧手写路径能成，是因为它东侧点压得很**低**(y≈-0.24~-0.29)，前臂从 P2 **南侧**掠过(clr 0.075~0.13)，不横穿。对称圆在东侧要回到 C(y=-0.095) 就必然横穿 P2。

结论/下一步：从零画圆这条路对机械臂体积不友好。更稳的做法是**把已验证过的旧手写 `endpoint_oracle_waypoints`（大低回环、机械臂安全、能真绕上）重采样成平滑匀速曲线**，而不是自己画圆。待用户确认方向。

## 定案：向心 Catmull-Rom 平滑手写路径（用户选定）

弃用从零画圆，改为 `_smooth_route_targets` = 对手写 `endpoint_oracle_waypoints` 做**向心 Catmull-Rom(α=0.5)**样条重采样（`_centripetal_catmull_rom`）：
- 曲线**穿过每个手写控制点** → 保留已验证的机械臂安全形状（大低回环、前臂从 P2 南侧掠过）；α=0.5 向心避免在不均匀控制点处过冲穿进 pole。
- **匀速**：每段步数 = 段长 / `smooth_speed`。
- 只剩两个旋钮：`smooth_arc_points`(每段手写 waypoint 间的样条采样点数)、`smooth_speed`(越小越慢越稳)。`smooth_route:false` 回退原始手写点。

自检：137 点、总步数 2246(手写 ~7000 的 1/3、匀速)、max_turn 128°(手写 159° 尖点已圆化，剩一处较急弯多半在靠 C 的密集入槽段)、min_dist_to_P2 0.08(不穿 pole)、末点 green_exit_to_C。
（注：自检里的 forearm 净空是 base→EE 的 2D 直线粗代理，会高估碰撞；真实 Franka 肘部抬高，只有腕段贴桌。之前用户看到的撞臂是我那版圆把 EE 甩到 P2 东侧同纬度导致的，换回手写形状应缓解。）
