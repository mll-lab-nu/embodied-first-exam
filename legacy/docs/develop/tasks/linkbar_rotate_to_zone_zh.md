# docx 4.4 旋转连接杆转到同色区域 —— 工程记录

> 日期：2026-08-20 开工（首版：插口 + 小车），2026-08-27 改造（颜色区域），2026-09-01 改版（固定导轨 + 自由两区，见 §5.3），2026-09-08 销与目标区分色、目标改由指令说（见 §9），2026-09-09 定为红蓝两色、梁上不留标识色、加 `obs/goal_id`（见 §11）
> 上游：`../TopoGym_tasks.docx` §4.4；2026-08-27 review 意见；2026-09-01 变体要求
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）、
> [`variation_and_difficulty_plan_zh.md`](variation_and_difficulty_plan_zh.md) §3.8 / §6.8（随机化）
>
> 目标模块：`topogym/tasks/connectivity/linkbar_rotate_to_zone.py`

---

## 0. 结论摘要

- 场景：固定立柱上铰接一条连接梁，梁绕竖直轴转，梁端的销在水平圆上走。圆上画一段固定跨度
  （±90°）的虚线导轨，导轨上任意位置放两块互不重叠的颜色区域（可同侧、可相邻），一块红、一块蓝，
  哪块是红逐 episode 对换。**连接梁上没有任何标识色**（2026-09-09 起销、销套环、手柄盖与转轴同灰）。
  区键名 `color_1` / `color_2` 无方位含义（2026-09-01 前为 `left` / `right`）。
- 判据：松手沉降后，销的关节角落在**指令说的那种颜色**的色条所标出的扇形内（角窗口
  ±`half_width_deg`，不看半径），且关节角速度低于阈值。单帧画面可辨：梁指向目标色那条色条，
  或指向另一条／两条之外。
- 2026-08-27 改造：删除小车、导轨、两个插口、weld 闩、行程测试、约束图 union-find。
  保留立柱、连接梁、`PivotLeverPrimitive` 及全部实测过的高度与夹持参数。
- 离线门已过：`tests/check_linkbar_planner.py`（oracle 6/6，`nearest_zone` 3/6）、
  `tests/check_linkbar_zone_geometry.py`（边界翻转、无重叠、七种非法布局被拒、同侧与相邻布局被接受）、
  两个 demo 的 hydra 组合。GPU：2026-08-27 版八格已过（§8.1、§8.2）；2026-09-01 改版后 seed 0–9 sweep 已过（§8.4：oracle 10/10、`nearest_zone` 5/10）。
- 时长：去掉行程测试（180 步）与部分停顿后，估计每 episode ≈ 560 步（原 ≈ 860）。

---

## 1. 任务定义

### 1.1 现行定义

| 项 | 内容 |
|---|---|
| 场景 | 桌面上一根固定立柱；连接梁铰接于立柱顶，绕 +z 转，无限位；梁端销半径 0.170 处；梁上手柄半径 0.100 处 |
| 目标 | 销停进指令说的那种颜色的色条所标出的扇形内 |
| 区域 | 两块，在固定导轨 [−90°, +90°] 上任意放置、互不重叠（默认 −45° / +55°），角半宽 8°，径向宽 40 mm，纯视觉 |
| 动作 | 夹爪夹手柄转梁一次，松手，退刀 |
| 不变量 | `pin_zone ∈ {color_1, color_2, None}`，定义在梁的关节角上（`"space": "joint_angle"`） |
| 物理层 | `at_rest`：沉降 30 步后关节角速度 ≤ 0.05 rad/s |
| 指令 | 模板 `"Turn the bar so its pin comes to rest inside the sector marked by the {target_colour} band."`，`{target_colour}` 填 red / blue，逐 seed 变；**目标只在这句话里，画面里读不出来**。无语言输入的基线读 `obs/goal_id`（red=0、blue=1，见 §11） |

### 1.2 与首版的差异及理由

首版（2026-08-20 ~ 08-22）：两块区域的位置上各有一个同款插口，一个装在固定件 A 上、一个
装在导轨小车 B 上；销扣进插口后 weld 锁死；判据为约束图连通分量 2→1，物理复核为推小车
不动（行程 0.0000 m 对 0.1002 m）。

review 意见（2026-08-27）：「原成功判据为小车保持静止，在视频中可辨识度低；改为将杆转动
至指定颜色区域，钉子颜色与目标区域颜色对应；任务时长应尽量短。」

改造决定：

| 项 | 首版 | 现版 | 理由 |
|---|---|---|---|
| 决策对象 | 两个同款插口，归属不同 | 两块同形区域，颜色不同 | 保留「二选一」结构；区分线索从「装在谁身上」改为「颜色」，画面可读 |
| 锁定机制 | weld 闩 | 无，靠关节摩擦 0.10 N·m 停住 | 少一个机制；摩擦值已在首版实测为「home 沉降 40 步不自转」 |
| 判据 | 约束图 + 行程测试 | 关节角窗口 + 静止 | 与画面一致；去掉 180 步的推小车段 |
| 契约字段 | `invariant=component_count`, `space=constraint_graph` | `invariant=pin_zone`, `space=joint_angle` | 已在 `task_taxonomy_zh.md` §4.4 登记为偏离 |
| 任务名 | `linkbar_merge_components` | `linkbar_rotate_to_zone` | 不再合并任何东西，名称随功能改 |

首版的记录（场景形态、高度链、行程测试两档读数、weld spike）保留在 git 历史
（提交 `a884929` 及之前的 `docs/develop/tasks/linkbar_merge_components_zh.md`）。

---

## 2. 场景形态

### 2.1 结构

| 实体 | 类型 | 碰撞 | 说明 |
|---|---|---|---|
| `pivot_column` | 固定圆柱 r 0.026 h 0.078 | 是 | 梁转在它上面 |
| `linkbar` | 单自由度铰链机构，7 个 `HingeShape` | 梁／转轴／轮毂／销／手柄座／手柄碰撞；销套环、手柄盖不碰撞 | 连续关节，`joint_friction 0.100` |
| `zone_color_1_00..06` / `zone_color_2_00..06` | 沿弧铺的 7 段直盒 | 否 | 每块角半宽 8°，径向 40 mm，厚 1 mm |
| `rail_tick_00..35` | 虚线导轨 | 否 | 固定跨度 [−90°, +90°]，5° 一格；落在区跨度内的格不画 |

销、销套环、手柄盖三处与转轴同灰（2026-09-09 起）。这三处是标识色原来所在的地方——销是梁上
最小的零件且在梁下方，套环与手柄盖把同一颜色放到 oblique / wrist 机位看得见的位置——正因为如此，
现在它们一处都不能带颜色。

### 2.2 颜色

| 用途 | 值 |
|---|---|
| 区域 red | `[0.85, 0.15, 0.15]` |
| 区域 blue | `[0.15, 0.45, 0.85]` |
| 梁 | `[0.42, 0.46, 0.52]` |
| 转轴／轮毂／手柄座／**销／销套环／手柄盖** | `[0.55, 0.56, 0.58]` |
| 手柄 | `[0.12, 0.13, 0.15]` |
| 立柱 | `[0.50, 0.51, 0.53]` |
| 桌面 | 0.78–0.82 浅灰 |

红与蓝对桌面浅灰、对梁的蓝灰都有明度或色相差；不随机化时默认 color_1=red、color_2=blue。

**鲜艳色只出现在桌面的两块区域上（2026-09-09 起）。** 调色板从六色收到红蓝两色，销、套环、手柄盖
改与转轴同灰，梁上只剩灰／蓝灰／炭黑三种中性色。`zones.colors` 里两个键的书写顺序就是
`obs/goal_id` 的编号顺序（red=0、blue=1）。改动的理由与后果见 §11；此前（2026-09-08 起）销取的是
六色里的第三种，与两块区域都不同，见 §9。

### 2.3 区域的画法

**区域是扇形，色条只是把它标出来（2026-09-10 起的说法）。** 判据 `in_zone` 只看角度、
不看半径——销焊在梁上，半径恒为 `arm_radius`，半径不是自由度。所以「区域」指的是
`half_width_deg` 划出的整个扇形，桌面上那条色条不是区域的边界，它是这个扇形画在桌面上
的标记。指令也照这个说法写：`"...comes to rest inside the sector marked by the red band."`

`LinkbarRotateSceneBuilder._add_zones`：沿销的圆弧，从 `centre − half` 到 `centre + half`
均分 `segments` 段，每段一个 `gs.morphs.Box(fixed=True, collision=False)`，yaw 取该段中心角，
径向宽 `radial_width`、切向长为该段弦长 + 0.5 mm 搭接。7 段各 2.3°，弦弧偏差 < 0.1 mm。

两条色条出自同一个循环，除颜色外完全相同。

**2026-09-10 修的画法 bug。** `_box` 按该段自己的角度 yaw，所以盒子 `size` 的第一项落在
**径向**、第二项落在切向（导轨的格子用的是同一套约定）。此前 `size` 写成
`(length, radial_width, thickness)`，把弦长摆到了径向、把径向宽摆到了切向，于是画出来的是：

| | 改前（错） | 修 bug 后 | **定稿（放宽弧、收窄条）** | 判据 |
|---|---|---|---|---|
| 角向跨度 | ±13.71° | ±8.25° | **±12.16°** | ±12.00° |
| 弧长（半径 170 mm） | — | 47.5 mm | **71.2 mm** | — |
| 径向宽 | 7.2 mm | 40.0 mm | **18.0 mm** | 不看半径 |
| 弧 : 径 | — | 1.2 : 1（像方块） | **4.0 : 1（像扇形外周）** | — |
| 拼段数 | 7 | 7 | **10** | — |

两个后果都是实打实的：销停在离区中心 8°–13.71° 之间时**画面上看着在颜色里、判据报
`outside_zone`**，每侧 5.71° 的画面与判决打架带；色条径向 7.2 mm 比 20 mm 的销还窄，销一压
上去就把它盖住，人眼确认不了。改后残留 0.25° 的过画，是直盒子在弧两端的凸出（半径 170 mm
上 0.74 mm），无法用直盒子消掉，加段数可减小。

这个 bug 自 2026-08-27 建这套色块起就在，一直没被发现：离线门只验角度算术（`in_zone`），
不验画出来的几何；而 09-08 之前销与目标区同色，看的人是**对颜色**而不是判位置，细线也够用。
09-09 销改成灰的之后才暴露。修复不影响任何已录的物理读数——oracle / nearest / 角点读的都是
关节角，不是像素。

**导轨的格子不动。** `rail.tick_size` 在同一套约定下画成 12 mm 长的径向刻度、4 mm 宽，
看上去就是一圈刻度线，读作虚线导轨没有问题，且它不与任何被记录的数字冲突。

---

## 3. 机构与几何

高度（task 帧，桌面 z = 0）与首版一致，未动：

| 量 | 值 | 来源 |
|---|---|---|
| 立柱顶 | 0.078 | 轮毂底 0.093 下余 15 mm |
| 转轴底 | 0.080 | 立柱顶 + 0.002 轴承间隙（不能为 0，2026-08-20 实测卡死） |
| 梁 | 0.095–0.115 | |
| 销 | 0.052–0.095 | 销不碰任何东西；保留旧值以不动梁的质心与夹持实测 |
| 手柄 | 0.125–0.165 | 指腹在 0.150 |
| 手柄盖顶 | 0.171 | `approach_z 0.315` 对应指腹 0.212，余 41 mm |

枢轴 `x = +0.020`：共用 home 下手部落在轮毂正上方，手柄圆与指尖水平净空 43 mm
（首版 2026-08-20 实测结论，不改共用 home）。

派生量（`LinkbarRotateLayout`）：

| 量 | 公式 |
|---|---|
| `zone_center_xy(z)` | `pivot + arm_radius · (cos θ_z, sin θ_z)` |
| `in_zone(angle, z)` | `|wrap(angle − θ_z)| ≤ half_width` |
| `zone_at(angle)` | 第一个 `in_zone` 为真的区，否则 `None` |
| `target_zone()` | `cfg.zones.target` |
| `target_colour()` | `zone_color_name(target_zone())`——指令里填的那个词 |
| `zone_for_colour(c)` | 涂 `c` 的那块区（两区不同色保证唯一） |
| `goal_id()` | `target_colour()` 在 `zones.colors` 键序里的下标（red=0、blue=1） |
| `nearest_zone(angle)` | 角差最小的区 |

| `rail_span()` | `(rail.start_deg, rail.end_deg)`，弧度 |

`validate()`（2026-09-01 版）拒绝：初始角不在导轨上；任一区未整体落在导轨内（`centre ± half_width` 出 [−90°, 90°]）；
初始销在任一区内或其 `pin_start_margin_deg`（2°）余量内（即 `|init − centre| < half_width + 2°`）；两区中心角距 < 2·half_width（相等 = 相邻，允许）；
两区同色（否则指令与 `goal_id` 会同时指向两块，`zone_for_colour` 也无从选择）；`target` 不是 color_1/color_2。
改版前的「两区异侧」「扫掠幅度 [15°, 75°]」「角距 ≥ 2·half_width + 5°」三条已删除；
「销的颜色不得与任一区相同」一条在 2026-09-09 随销的颜色一并删除。

---

## 4. 判定

### 4.1 读数

`LinkbarRotateEvaluator.classify(scene, rotate_ok)` → `LinkbarRotateState`：

| 字段 | 来源 |
|---|---|
| `pin_angle` | 关节角 |
| `pin_zone` | `layout.zone_at(pin_angle)` |
| `target_zone` | `layout.target_zone()` |
| `angular_speed` | 关节角速度 |
| `rotate_ok` | 原语自身的门（到位角、跟随误差、滞后、松手漂移、指位） |

`is_terminal = in_target and at_rest and rotate_ok`。

### 4.2 失败标签

| 标签 | 条件 |
|---|---|
| `rotate_check_failed` | 原语门未过 |
| `outside_zone` | `pin_zone is None` |
| `wrong_zone` | `pin_zone != target_zone` |
| `not_at_rest` | 角速度 > `max_angular_speed` |

### 4.3 时序

决策 → `PivotLeverPrimitive.run`（approach / descend / close / rotate / release / retreat）
→ 沉降 `success.settle_steps` 30 步 → `classify` → `final_hold_steps` 60 步。

---

## 5. 防捷径与随机化

> 本节写的是 2026-09-01 改版后的状态。**2026-09-08 起销与目标区不再同色、目标改由指令说**（§9），
> **2026-09-09 起调色板只剩红蓝、梁上不留任何标识色、加 `obs/goal_id`**（§11）。
> 下面几张表已按 09-09 的状态更新。

三条随机化轴，均为 hydra 覆盖：

| 轴 | 叶子 | 说明 |
|---|---|---|
| 目标 | `task.zones.target` | color_1 / color_2 |
| 角位置 | `task.zones.color_1.angle_deg` / `task.zones.color_2.angle_deg` | 导轨 [−90°, 90°] 上任意，两区不重叠 |
| 颜色分配 | `task.zones.assignment.color_1` / `.color_2` | 红与蓝各给一块，逐 episode 对换（2026-09-09 起；此前是六色里抽三种，含销） |

对照规则（`run.oracle_mode`）：

| 模式 | 规则 | 期望成功率 |
|---|---|---|
| `oracle` | 读指令说的颜色，在画面里找到涂那个颜色的区，转过去（`zone_for_colour(target_colour())`） | 1 |
| `nearest_zone` | 转到角差最小的区 | 0.5（target 与角位置独立抽样时） |

`tests/check_linkbar_planner.py` 六例交叉（异侧两例、同侧四例，红蓝分配也在六例上交叉）：oracle 6/6，`nearest_zone` 恰好 3/6。
`nearest_colour`（转到与销颜色最接近的区，2026-09-08 加）在 2026-09-09 随销的颜色一并删除，见 §11.3。

变体轴声明在任务 yaml 末尾的 `variation:` 块（2026-08-29 首次注册在 python `_REGISTRY`，2026-09-01 改为固定导轨版并搬进 yaml；`generation/layout_randomization.py` 只读该块）：

| kind | 叶子 | 取值 |
|---|---|---|
| `choice` | `zones.target` | color_1 / color_2 |
| `distinct_choice` | `zones.assignment.color_1` / `.color_2` | `zones.colors` 的键，**2 种有序对**（红蓝对换；2026-09-08–09 期间是六色取三种、120 种有序三元组，含销） |
| `spaced_pair` | `zones.color_1.angle_deg` ≤ `zones.color_2.angle_deg` | 两中心在 [−82, 82]（导轨 ±90 减半宽 8），角距 ≥ 16（= 2·半宽，相邻允许）。先在 [−82, 66] 独立抽两值、排序、大者加 16：非重叠对上的均匀分布，无需为重叠拒绝 |
| `uniform` | `linkbar.init_angle_deg` | [−15, 15] |
| `validate` | `linkbar_rotate_to_zone:validate_task_cfg` → `LinkbarRotateLayout.validate()` | 不过则整体重采（按 seed 确定） |

触发：`run.randomize_layout=true run.seed=<seed>`（两个 demo 均接入，打印一行 `linkbar_rotate_to_zone variant seed=… target=… color_1_deg=… color_2_deg=… init_deg=… gap_deg=… same_side=…`）。
离线门 `tests/check_variant_rng.py`（1000 个 seed 的包络与确定性）。
实验脚本 `bash_scripts/tests/linkbar_variation_sweep.sh`：每 seed 三格——`visual`（静态一帧录像，人眼看）、`oracle`（须 `task_success=True`）、`nearest`（对照成功率，期望接近 1/2）。`colour` 格随 `nearest_colour` 规则在 2026-09-09 删除。2026-08-27 版结果见 §8.2；改版后待跑。
分档不预设，按 sweep 结果划定：`variation_axes_plain_zh.md` §5。

### 5.3 2026-09-01 改版：固定导轨 + 自由两区

§8.2 的视觉结论是十个变体画面几乎一样：两区被限制为分居初始角两侧、各在 [15°, 75°]（改前 [35°, 75°]）扫掠带内，
离散组合只有 2×2，角度包络在 oblique 机位上只差几个像素。改为：

- **导轨固定**：`rail.start_deg / end_deg = ±90°`，不随两区位置变；`_add_rail` 沿整条导轨等距画 36 格，
  落在区跨度内的格跳过（色块盖在那段上，同高度两种标记会闪烁）。±90° 是已实测过的绝对范围（seed 6 区中心 +84.45° oracle 通过；
  改版前 `_ShiftBy` 平移后区中心绝对值本就到 90°）。
- **两区自由**：中心可在导轨上任意处，同侧或异侧、相邻或分开都允许，只要求不重叠。`nearest_zone` 对照在同侧布局下同样只有一半正确。
  同侧且目标是远区时，销在途中会掠过近区——判据只读松手后的静止态，不算错。
- **销出生不在区内**：新增 `zones.pin_start_margin_deg = 2°`，`|init − centre| ≥ half_width + 2°`。09-01 版靠拒绝实现，
  1000 seed 实测首抽拒绝率 0.234（每区 20° 禁区 / 约 164° 可用），`check_variant_rng.py` 对本任务单独放宽阈值到 0.30。
  **2026-09-02 改为构造式**：`variation:` 里不再抽 `init_angle_deg`，改抽 `linkbar.init_frac ∈ [0, 1]`，`derived` 条目调
  `derive_task_cfg`，把它按长度比例映射到 `init_span_deg`（±15°）扣掉两区禁区后剩下的 1–3 段并集上
  （`LinkbarRotateLayout.init_angle_segments` / `init_angle_from_frac`）。并集为空（两区把 ±15° 盖满）才拒绝，
  1000 seed 首抽拒绝率 0.002；阈值回到全任务统一的 0.02。代价：seed → 变体的映射变了，§8.4 的十格不再对应同 seed，
  需按新规则重跑 `linkbar_variation_sweep.sh` 复核（oracle 10/10、nearest ≈ 1/2）。离线 1000 seed：同侧 390、异侧 610、
  近邻 65、初始角贴禁区边 103。
- **键名**：`left` / `right` → `color_1` / `color_2`，随机化后 `color_1` 是角度较小的那块。判据字段 `pin_zone` / `target_zone`
  的取值随之变为 `color_1` / `color_2`；本任务此前无录制数据集，不涉及兼容。
- 离线实测（1000 seed）：同侧 368、异侧 632、净角距 < 5° 的近邻对 69；六色 30 种有序组合全覆盖。
- 未动：`half_width_deg` 8。
- GPU sweep 结果见 §8.4：oracle 10/10、`nearest_zone` 5/10、十格画面可分；`max_lag` 随扫掠角增长，最大 4.79° @ 88°（门 6°）→ 同日把 `motion.steps_arc` 改为按扫掠角推导（§8.5）。

---

## 6. 文件集与登记点

| 文件 | 内容 |
|---|---|
| `topogym/tasks/connectivity/linkbar_rotate_to_zone.py` | `LinkbarRotateLayout` / `LinkbarRotateScene` / `LinkbarRotateSceneBuilder` |
| `topogym/verification/linkbar_rotate_to_zone_verifier.py` | `LinkbarRotateState` / `LinkbarRotateEvaluator` |
| `topogym/planning/linkbar_rotate_to_zone_planner.py` | `LinkbarOracleRule` / `NearestZoneRule` / `make_linkbar_rule` |
| `topogym/primitives/pivot_lever.py` | `PivotLeverPrimitive`（与 4.3 共用，未改） |
| `configs/task_configs/linkbar_rotate_to_zone_topogym_tabletop_v1.yaml` | 全部几何、区域、判据、时长 |
| `configs/linkbar_rotate_to_zone.yaml` / `_rotate.yaml` | 顶层组合 |
| `configs/run_configs/linkbar_rotate_to_zone.yaml` / `_rotate.yaml` | 运行档 |
| `demos/connectivity/linkbar_rotate_to_zone_inspect_demo.py` | sweep / seat / classify |
| `demos/connectivity/linkbar_rotate_to_zone_physical_demo.py` | 完整 episode |
| `tests/check_linkbar_planner.py` | 规划器离线门 |
| `tests/check_linkbar_zone_geometry.py` | 布局几何离线门 |

登记点：`topogym/core/taxonomy.py` `CATEGORIES["connectivity"]`；`topogym/tasks/__init__.py`、
`topogym/verification/__init__.py`、`topogym/planning/__init__.py` 的再导出。

已删除：`topogym/tasks/connectivity/_travel_probe.py`、`topogym/primitives/socket_weld.py`。
`tests/weld_constraint_spike.py` 保留为 weld API 的记录。

---

## 7. 步骤与验收状态

| 步骤 | 门 | 状态 |
|---|---|---|
| 离线：规划器 | `python tests/check_linkbar_planner.py` 退出 0 | 过（2026-08-27） |
| 离线：布局几何 | `python tests/check_linkbar_zone_geometry.py` 退出 0 | 过（2026-08-27，`.venv-gs110`） |
| 离线：配置组合 | 两个 demo `--cfg job` | 过（2026-08-27） |
| GPU：inspect sweep | `run.sweep_joint=true`，`reached_both=True` | 过（2026-08-27，worst_error 0.00°） |
| GPU：inspect seat | `seat_phase=color_2/color_1/none`，`pin_zone` 分别为 color_2/color_1/None，`speed` < 0.05 | 过（2026-08-27，三相位 speed 0.0000；改版前相位名 left/right） |
| GPU：physical oracle | `task_success=True`，`angular_speed` 读数记入 §8 | 过（2026-08-27） |
| GPU：physical nearest | 默认布局（target=color_2 在 +55°，比 color_1 的 −45° 更远）判 `wrong_zone` | 过（2026-08-27，同一默认几何） |
| GPU：physical offset | `run.target_offset_deg=12` 判 `outside_zone` | 过（2026-08-27） |
| 录像 | oblique / front / wrist 三机位，`runs/videos/linkbar_rotate_to_zone/`，检查销色与区色可辨 | 待跑 |

一键脚本（八格，逐格 PASS/FAIL，日志落 `runs/linkbar_zone/<时间戳>/`）：

```
bash bash_scripts/tests/linkbar_rotate_to_zone_check.sh              # 全部
bash bash_scripts/tests/linkbar_rotate_to_zone_check.sh offline seat # 只跑几组：offline / sweep / seat / physical
```

单条命令：

```
python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.sweep_joint=true 2>&1 | tee runs/linkbar_zone_sweep.log
python -m demos.connectivity.linkbar_rotate_to_zone_inspect_demo run.seat_phase=color_2 2>&1 | tee runs/linkbar_zone_seat_color_2.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo 2>&1 | tee runs/linkbar_zone_oracle.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.oracle_mode=nearest_zone 2>&1 | tee runs/linkbar_zone_nearest.log
python -m demos.connectivity.linkbar_rotate_to_zone_physical_demo run.target_offset_deg=12 2>&1 | tee runs/linkbar_zone_offset.log
```

---

## 8. 实测值

### 8.1 2026-08-27 GPU 验收（`bash_scripts/tests/linkbar_rotate_to_zone_check.sh`，4090）

| 格 | 读数 | 结论 |
|---|---|---|
| sweep | 两区均 error 0.00°，`touching=none` | 梁能到两块区域，无接触 |
| seat none / 同色区 / 异色区 | drift 0.000°，speed 0.0000 rad/s；判据分别 `outside_zone` / `terminal=True` / `wrong_zone` | 判据与相位一一对应 |
| physical oracle | final +56.71°（目标 +55°），target_error 1.71°，max_lag 2.82°，release_drift 0.00°，finger_qpos 0.0105，沉降后 speed 0.0000 | `task_success=True` |
| physical nearest_zone | final −46.39°（目标 −45°），target_error 1.39°，max_lag 2.30° | `wrong_zone`（期望） |
| physical offset +12° | final +69.00°（目标 +67°），target_error 2.00°，max_lag 3.37° | `outside_zone`（期望） |

观察：

- 三条 episode 松手后关节角速度均为 0.0000 rad/s，`max_angular_speed 0.05` 余量充足，阈值不动。
- 三条 episode 终角都**越过**目标 1.4–2.0°（同向），`release_drift` 为 0，说明过冲发生在扫掠末段而不是松手后。
  对 8° 半宽与 4° 到位容差无影响；若将来把半宽收到 4° 以下，要先查这项。
- 时长缩短项（`steps_per_phase 80`、`arc_settle 30`、`release_hold 30`）下 `max_lag` ≤ 3.37°、
  `follow_error` ≤ 0.0116，均未触门（6° / 0.040）。
- 首次扰动在 step ≈ 360（合爪阶段，指腹接触 1.5 N），与首版一致。

首版实测（仍适用于保留的部分）：

| 项 | 值 |
|---|---|
| 关节摩擦 0.10 N·m | home 沉降 40 步梁不自转；0.05 时自转（2026-08-22） |
| 夹持 `grasp_qpos 0.001` | 能力 0.48 N·m，对扫掠阻力矩 0.125 N·m 余 3.8 倍 |
| 枢轴 x +0.020 | 手柄圆与指尖净空 43 mm |
| `approach_z 0.315` | 指腹对手柄盖余 41 mm |

### 8.2 2026-08-29 变体 sweep（`bash_scripts/tests/linkbar_variation_sweep.sh`，4090，seed 0–9）

> 改版前（异侧 + 扫掠带包络，区键名 left/right）的结果，保留作对照；改版后的 sweep 待跑（§9）。

| seed | target | assignment | left | right | init | visual | oracle | nearest_zone |
|---|---|---|---|---|---|---|---|---|
| 0 | right | left:blue, right:orange | +57.27 | −56.45 | −11.78 | ok | PASS | success |
| 1 | left | left:orange, right:blue | +51.00 | −75.10 | −14.53 | ok | PASS | wrong_zone |
| 2 | right | left:orange, right:blue | +61.57 | −67.97 | +3.97 | ok | PASS | wrong_zone |
| 3 | right | left:blue, right:orange | +70.40 | −45.66 | +10.23 | ok | PASS | success |
| 4 | right | left:blue, right:orange | +65.67 | −38.29 | +6.83 | ok | PASS | success |
| 5 | right | left:blue, right:orange | +33.77 | −53.78 | −4.82 | ok | PASS | wrong_zone |
| 6 | right | left:orange, right:blue | +84.45 | −55.54 | +9.60 | ok | PASS | success |
| 7 | right | left:blue, right:orange | +57.06 | −55.23 | −3.75 | ok | PASS | success |
| 8 | right | left:blue, right:orange | +34.76 | −66.29 | −6.06 | ok | PASS | wrong_zone |
| 9 | right | left:orange, right:blue | +57.86 | −70.42 | +2.24 | ok | PASS | wrong_zone |

结论：

- oracle **10/10** `task_success=True`：在声明的包络（两区扫掠角 [35°, 75°]、横梁初始角 ±15°、目标与颜色随机）内，同一个 oracle 对每个变体都可解，无需改动。
- `nearest_zone` **5/10**：与期望 1/2 一致。逐条核对：它转向 |sweep| 较小的那块，成功当且仅当那块恰为目标（seed 0/3/4/6/7）。防捷径成立。
- 离线：1000 个 seed 校验拒绝率 0.000（包络本身保证两区异侧且角距 ≥ 70°）；黄金值在 numpy 2.4.4 上与 2.2.2 一致。
- seed 0–9 里 `target=right` 占 9/10，是这十个种子的偶然（1000 个种子上 right 占 0.494，颜色互换率 0.516）。做人眼演示时若要两种目标都出现，多取几个种子即可，不要为此改采样。
- 视觉（`visual_s*.mp4`）：人眼看首帧，十格几乎一样。原因：离散组合只有 2×2=4 种（seed 0/3/4/5/7/8 六个同为「左蓝右橙、目标右」），角度包络 [35°, 75°] 只有 40° 宽，在半径 0.170 的圆弧上从 oblique 机位只差几个像素。

### 8.3 2026-08-29 包络加宽（已被 2026-09-01 改版取代）

针对 §8.2 的视觉结论改了三处：`min_sweep_deg` 35 → 15（下界只需保证销出生时不在区里：half_width 8° + 余量）；`zones.colors` 扩成六色调色板，`assignment` 改为不放回抽两种（`_DistinctChoiceJitter`，替代原互换）；注册条目角度边界改为 [15, 75]。`max_sweep_deg` 75 是可达上界，不动；两侧规则不动。离线门 1000 seed 通过。扫掠角 15–25° 未在 GPU 实测过。这一版没有跑 GPU：2026-09-01 改为固定导轨 + 自由两区（§5.3），`min_sweep_deg` / `max_sweep_deg` 与两侧规则一并删除。

### 8.4 2026-09-01 改版后变体 sweep（`bash_scripts/tests/linkbar_variation_sweep.sh`，4090，seed 0–9，`runs/linkbar_variation/20260901_183506/`）

> 注（2026-09-02）：本节与 §8.5 的 `max_lag` 是旧定义——关节角与**指令角**之差，含手的 IK 跟踪滞后（约 11 mm，在 100 mm 手柄圆上折合 2–3°）。
> 2026-09-02 起原语改为关节角与**手部实际角**之差，只量指垫打滑；新旧读数不可比。「lag 随扫掠角增长」是跟踪滞后随角速度增长，不是打滑；
> 恒定角速度的改动保留，理由是角速度决定跟踪滞后与终角过冲。新定义下的读数见 §8.7。


| seed | target | assignment (c1 / c2) | c1 | c2 | init | gap | 同侧 | 目标扫掠 | oracle final / err / max_lag | nearest_zone |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | color_2 | blue / red | +15.35 | +76.23 | −11.78 | 44.9 | 是 | 88.0° | +78.43 / 2.19 / **4.79** | wrong_zone |
| 1 | color_1 | orange / red | −80.11 | +51.50 | −14.53 | 115.6 | 否 | 65.6° | −82.16 / 2.05 / 2.77 | success（两区离初始角 65.6° vs 66.0°，近区恰为目标） |
| 2 | color_2 | yellow / red | −15.49 | +47.14 | +3.97 | 46.6 | 否 | 43.2° | +48.62 / 1.49 / 2.12 | wrong_zone |
| 3 | color_2 | green / red | −54.73 | +76.13 | +10.23 | 114.9 | 否 | 65.9° | +78.33 / 2.20 / 2.94 | wrong_zone |
| 4 | color_2 | green / purple | −19.28 | +22.43 | +6.83 | 25.7 | 否 | 15.6° | +23.10 / 0.66 / 0.74 | success |
| 5 | color_1 | orange / red | −56.30 | −26.02 | −11.90 | 14.3 | 是 | 44.4° | −57.97 / 1.67 / 1.85 | wrong_zone |
| 6 | color_2 | green / orange | −46.39 | −23.31 | +9.60 | 7.1 | 是 | 32.9° | −24.02 / 0.71 / 2.10 | success |
| 7 | color_2 | green / orange | −77.69 | −24.80 | −3.75 | 36.9 | 是 | 21.0° | −25.58 / 0.78 / 1.05 | success |
| 8 | color_2 | purple / orange | −44.83 | +43.01 | −6.06 | 71.8 | 否 | 49.1° | +44.36 / 1.35 / 2.78 | wrong_zone |
| 9 | color_2 | red / green | −30.98 | +28.44 | +2.24 | 43.4 | 否 | 26.2° | +29.31 / 0.87 / 1.40 | success |

结论：

- oracle **10/10** `task_success=True`；十条 `release_drift` 均 0.00°、沉降后 `angular_speed` 均 0.0000 rad/s、`finger_qpos` 均 0.0105。
  覆盖了改版新增的三种形态：同侧（seed 0/5/6/7）、同侧且目标是远区（seed 0、5：途中掠过近区，判据不受影响）、近邻（seed 6 净角距 7.1°）。
- `nearest_zone` **5/10**：逐条核对，成功当且仅当离初始角更近的那块恰为目标（seed 1/4/6/7/9）。seed 1 两区离初始角只差 0.4°，是「几乎等远」的实例。防捷径成立。
- 视觉（`visual_s*.mp4` 首帧）：十格一眼可分——两区位置、同侧/异侧、相邻与否、六色组合都不同，导轨长度固定。§8.2 的「十格几乎一样」已解决。
- **`max_lag` 随扫掠角线性增长**：0.74° @ 15.6° → 2.8° @ 49–66° → 4.79° @ 88°，约 0.05°/°。外推到包络内最大扫掠 105°（同侧远区 + 初始角反向）约 5.7°，贴着 `max_lag_deg` 6° 的门。
  终角过冲同样随扫掠增长（0.66° → 2.2°），仍在 4° 容差内。原因是 `motion.steps_arc` 固定 240 步，扫掠越大角速度越高。
  处置：把 `steps_arc` 改为按扫掠角推导（§2.5 约定 4），而不是调门。→ §8.5。

### 8.5 2026-09-01 扫掠步数改为按扫掠角推导

`motion.steps_arc: 240` 改为 `arc_deg_per_step: 0.23`（= 55°/240 步，08-27 验收时的角速度）+ `min_steps_arc: 120`，
`LinkbarRotateLayout.steps_arc(sweep) = max(120, ceil(|sweep| / 0.23°))`；physical demo 按 plan 的实际扫掠角取步数（offset run 也按偏移后的目标算）。
固定的是角速度而不是步数。

seed 0–9 oracle 组重跑（`runs/linkbar_variation/20260901_212731/`，10/10 PASS）与上界 seed 259：

| seed | 扫掠 | 步数（240 → 新） | max_lag（旧 → 新） | target_error（旧 → 新） |
|---|---|---|---|---|
| 0 | 88.0° | 383 | **4.79 → 2.89** | 2.19 → 2.23 |
| 1 | 65.6° | 286 | 2.77 → 2.15 | 2.05 → 2.06 |
| 2 | 43.2° | 188 | 2.12 → 2.83 | 1.49 → 1.46 |
| 3 | 65.9° | 287 | 2.94 → 2.30 | 2.20 → 2.23 |
| 4 | 15.6° | 120 | 0.74 → 1.66 | 0.66 → 0.61 |
| 5 | 44.4° | 194 | 1.85 → 2.47 | 1.67 → 1.65 |
| 6 | 32.9° | 144 | 2.10 → 3.40 | 0.71 → 0.66 |
| 7 | 21.0° | 120 | 1.05 → 2.29 | 0.78 → 0.72 |
| 8 | 49.1° | 214 | 2.78 → 3.13 | 1.35 → 1.34 |
| 9 | 26.2° | 120 | 1.40 → 2.95 | 0.87 → 0.80 |
| 259 | 92.3°（400 个 seed 里最大） | 402 | — → 2.86 | — → 2.09 |

- `max_lag` 与扫掠角的相关性消失：改前 0.74° @ 15.6° 到 4.79° @ 88° 单调爬升，改后十一条落在 1.66–3.40°，均值 2.6°，最大 3.40°（seed 6），对 6° 门余量 1.8 倍。
  小扫掠的 lag 上来了（seed 4/7/9 从 ~1° 到 ~2–3°），因为它们现在和大扫掠跑同一角速度，步数从 240 降到 120——这正是「lag ∝ 角速度」的另一半证据。
  `release_drift` 十一条全 0.00°；`follow_error` 0.0104–0.0116，与步数无关。
- **过冲与速度无关**：每条 seed 的 `target_error` 改前改后一致到 0.05° 以内（2.19 → 2.23、0.66 → 0.61）。§8.4 里「过冲同样是速度相关」的推测不成立。
  它由几何决定，随扫掠角增长（约 2.5%：15.6° → 0.6°，88° → 2.2°），来源待查；离 4° 容差还有余量，暂不处理，划档 sweep 时记读数。
- 包络内理论最大扫掠 105° 需要初始角与目标区同时贴边，400 个 seed 里最大 92.3°；按恒定速度外推 105° ≈ 457 步、lag 仍 ≈ 2.9°。
- 时长：扫掠段随扫掠角在 1.2–4.6 s 之间，小扫掠比改版前更短。

---

### 8.6 2026-09-02 初始角改为派生后复核（`linkbar_variation_sweep.sh`，4090，seed 0–9，`runs/linkbar_variation/20260902_144216/`）

seed→变体映射改变后重跑三组：visual 10/10 有帧且逐 seed 可分；oracle **10/10**；`nearest_zone` **3/10**（seed 5/6/7 成功，
逐条核对均为「近区恰为目标」；seed 4 两区离初始角 13.0° vs 28.7°、目标是远区，wrong_zone）。同侧 4 / 异侧 6，近邻对 seed 6（净角距 7.1°）。
初始角贴禁区边的实例出现（seed 8 init −10.85°，color_1 −44.83°），与离线的「贴边 103/1000」一致。防捷径与 oracle 覆盖结论不变。

### 8.7 2026-09-02 `max_lag` 改为关节相对手部实际角后的读数（`runs/lag_fix/linkbar/`，seed 0–2）

| seed | 扫掠 | target_error | follow_error | max_lag（新定义） | 旧定义读数（§8.6 同 seed） |
|---|---|---|---|---|---|
| 0 | 80.0° | 2.24° | 0.0110 m | **0.77°** | 2.67° |
| 1 | 93.4° | 2.08° | 0.0112 m | **0.76°** | — |
| 2 | 37.7° | 1.46° | 0.0110 m | **0.48°** | — |

三格 `rotate success=True`、`task_success=True`。关节相对手的真实落后不到 1°：本任务的指垫确实是带着手柄转的，
旧读数里的 2–3° 几乎全是手的跟踪滞后（`follow_error` 11 mm 在 100 mm 半径上 ≈ 6°，扫弧方向上的分量 2–3°）。

## 9. 未决事项

- 终角过冲随扫掠角增长（0.66° @ 15.6° → 2.2° @ 90°），与角速度无关（§8.5），来源待查；容差 4°，暂不处理。
- 改版后 `linkbar_rotate_to_zone_check.sh` 的八格（seat 相位名已改为 color_1/color_2）尚未重跑；默认几何与改版前相同，预期不变。
- `mdp.max_episode_steps` 无消费者（无 gym env）。
- `segments` 7 段为估计值；俯视机位若看出折线，加到 11。

## 10. 风险

- 静止判据依赖关节摩擦：若 GPU 上沉降 30 步后仍有 > 0.05 rad/s 的残余转动，先看
  `touching` 是否有接触，再调 `settle_steps`；不先调阈值。
- 连续关节无限位：`nearest_zone` 对照转错时销停在异色区，是期望画面；`validate` 要求区整体在
  导轨 ±90° 内，即手柄不出工作区。导轨端点附近（|θ| > 84°）尚无 GPU 实测。
- 时长缩短项未经 GPU 验证。


## 9. 销与目标区分色，目标改由指令说（2026-09-08）

### 9.1 改之前是什么样

销、套环、手柄盖三处都涂成**目标区的颜色**，指令是一句常量：
`"Turn the bar so its pin rests on the zone that matches its colour."`
两块区被强制不同色，所以「转到和销同色的那一块」既是唯一解，也是 oracle 的实现
（`LinkbarOracleRule` 的 reason 就叫 `match_pin_colour`）。

09-08 会上点出的问题：**这是一次低层次的颜色配对**。策略只要会「找出画面里与销同色的色块，转过去」就能满分，不需要读懂任务是什么，也不需要读指令。会上的说法是「防『转到同色』被 hack」。

### 9.2 改成什么样

销取**第三种**颜色，与两块区都不同。这样画面里就没有任何东西指认目标了，目标只能由指令说：

```yaml
goal:
  instruction: "Turn the bar so its pin rests on the {target_colour} zone."
  instruction_fn: "topogym.tasks.connectivity.linkbar_rotate_to_zone:render_instruction"
```

`{target_colour}` 由 `LinkbarRotateLayout.instruction()` 填成目标区的颜色名，所以**指令随 seed 变**。原来的 `command.prompt` 常量句退役。

三色不放回由现有的 `distinct_choice` 承担，只是从两条路径扩到三条：

```yaml
- {kind: distinct_choice,
   paths: [zones.assignment.color_1, zones.assignment.color_2, linkbar.pin.colour_name],
   keys_of: zones.colors}
```

「销与两区都不同」因此是构造式保证的，不靠拒绝；`validate()` 里仍补一行同义检查，挡住手写布局。

### 9.3 对照组：把退役的捷径留下来当证据

新增 `run.oracle_mode=nearest_colour`：转到**与销颜色最接近**的那块区。这条规则在 09-08 之前**就是 oracle**（那时销取目标区的颜色，色距为 0）。销改成第三种颜色之后，它挑哪一块与目标无关，应当掉到约一半——这正是「转到同色」被堵掉的直接读数。若它重新接近满分，说明销的颜色又与某块区挂上了钩。

三条规则现在是：

| 规则 | 读什么 | 预期 |
|---|---|---|
| `oracle` | 指令说的颜色 | 全对 |
| `nearest_zone` | 只看角度，不看颜色也不看指令 | 约一半 |
| `nearest_colour` | 只看销与区的颜色，不看指令 | 约一半（09-08 之前是全对） |

### 9.4 这条改动把 linkbar 换到了另一栏

追踪表 §7.3 的表里，linkbar 原本在「指令不用随 seed 变，要读的信息在画面里」那一栏。改完之后它在「要随 seed 变」那一栏：同一张出生图配两句不同的指令对应两个不同的正确动作，指令写成常量就会让训练集自相矛盾。

**连带的一条**：不读语言的基线（RL / SAC）现在拿不到目标是哪一块。这不是 linkbar 一个任务的事，落点在数据集写入侧的 `obs/goal_id`。（这一条 2026-09-09 落地了，但形式与这里设想的不同：不是「把几条离散轴打包成定长向量」，而是一个整数，由任务 yaml 的 `goal.goal_id_fn` 算出——见 §11.4。）

### 9.5 实测

- 离线门 `check_linkbar_zone_geometry.py`：原来断言「`pin_color()` 就是目标区的颜色」的两条改成反向——销与两块区**都不同色**；另加「换 `zones.target` 指令跟着变」「指令里出现目标区的颜色名」两条。全过。
- 离线门 `check_linkbar_planner.py`：加 `nearest_colour` 进对照，六个用例上 `nearest_zone` 3/6、`nearest_colour` 3/6、oracle 6/6。
- `check_variant_rng.py` 的 linkbar 段：`sampled_leaves` 加 `linkbar.pin.colour_name`，首抽拒绝率 **0.002**（门 0.02，与改动前相同）。
- 角点门：`distinct_choice` 固定取前 `len(paths)` 个键，角点数仍是 **20，20 可行 0 拒**。
- GPU seed 0–9 四组（`runs/linkbar_variation/20260908_pincolour/`）：**oracle 10/10 PASS**、
  `nearest_zone` 3/10、**`nearest_colour` 2/10**、`visual` 10/10 出片。两条对照都落在 0.3–0.7 的
  防捷径带里（`nearest_colour` 的 0.2 在 n = 10 下与 0.5 的差距不显著，二项 P(≤2) = 5.5%）。
  seed 0 的指令是 `'Turn the bar so its pin rests on the blue zone.'`，销 yellow、两区 green / blue。
- **对照率用 1000 个 seed 离线复核**（不吃 GPU，比十格准得多）：`nearest_colour` 命中
  **512 / 1000 = 51.2%**、`nearest_zone` 467 / 1000 = 46.7%，两条都在随机水平；
  `zones.target` 抽样 color_1 507 / color_2 493 平衡；**销与某块区同色 0 / 1000**（构造式保证成立）。
  顺带解释 sweep 表上的一处观感：seed 0–9 里九格 `target=color_2`，那只是前十次抽样的运气，
  不是轴偏了——同一条流在 1000 个 seed 上是 507 / 493。


## 11. 红蓝定色、梁上不留标识色、`obs/goal_id`（2026-09-09）

> 编号接在 §10 之后。文件里 §9 出现了两次（「未决事项」与「销与目标区分色」），是 09-08
> 追加时的既有编号重复，本次不动它。

### 11.1 改之前是什么样

09-08 之后的状态：`zones.colors` 是一张六色调色板（orange / blue / green / red / purple /
yellow），每个 episode 不放回地抽三种——两块区域各一种，**销、销套环、手柄盖三处再取第三种**。
目标是哪一块只写在指令里。

会上提的两条：

1. **颜色的自由度太多。** 任务要读的信息只有「两块里哪一块」。六种颜色不增加这件事的难度，
   只让每个 seed 的画面颜色都不一样，增加了与任务无关的方差。
2. **连接梁上还挂着一种标识色。** 那第三种颜色虽然与两块区都不同，但它是整根梁上唯一一块
   鲜艳的、一眼看得出是特意涂上去的颜色，也是画面里最扎眼的东西。策略容易学成「盯着梁上那个
   彩色小零件」，而不是「读指令说的颜色，再去画面里找那块色块」。原话是「不能让它在连接杆上
   展现，否则容易被 cheat」。

### 11.2 改成什么样

**第一条：调色板收到红、蓝两色**，RGB 取原来六色表里的那两条（red `[0.85, 0.15, 0.15]`、
blue `[0.15, 0.45, 0.85]`），不改数。

**红蓝仍然逐 episode 对换**，`zones.assignment` 仍是一条随机轴，只是 `distinct_choice` 从三条
路径缩到两条：

```yaml
- {kind: distinct_choice,
   paths: [zones.assignment.color_1, zones.assignment.color_2],
   keys_of: zones.colors}
```

不能把红钉在 `color_1` 上：随机化之后 `color_1` 永远是导轨上角度较小的那块，在 front 相机里就是
偏左那块。红永远给 `color_1` 的话，指令里的「red」就等价于「画面偏左那块」，策略根本不用看
色块的颜色。对换之后取值空间是：

| 事实 | 取值 | 概率 |
|---|---|---|
| 目标区 `zones.target` | color_1（偏左） / color_2（偏右） | 各 1/2 |
| 红蓝分配 `zones.assignment` | (red, blue) / (blue, red) | 各 1/2 |
| ⇒ 目标区的颜色 = 指令里的词 = `goal_id` | red(0) / blue(1) | 各 1/2 |

四种组合各占 1/4，「目标在哪一侧」与「目标是什么颜色」互相独立。于是「永远转向角度更近那块」
「不读指令永远转向红块」「不读指令永远转向偏左那块」三条都是抛硬币。

**第二条：梁上不留任何标识色。** `linkbar.pin.colour_name` 这个叶子删掉；销、销套环、手柄盖
三处改用梁上已有的转轴灰 `linkbar.axle.color = [0.55, 0.56, 0.58]`，不新增颜色叶子。改完之后
整根梁是「蓝灰梁身 + 灰色转轴／轮毂／销／套环／手柄座 + 炭黑手柄」，鲜艳色只出现在桌面的两块
区域上。

### 11.3 对照组：`nearest_colour` 删除，oracle 改成按颜色找区

`nearest_colour`（转到与销颜色最接近的那块区）在 09-08 加进来当证据，前提是销带一种颜色。
现在销不带任何颜色，这条规则没有输入，`NearestColourRule` 与 `run.oracle_mode=nearest_colour`
一并删除，`linkbar_variation_sweep.sh` 的 `colour` 格也删掉（每 seed 四格 → 三格）。

同一次把 **oracle 改成按颜色找区**：

```python
zone = layout.zone_for_colour(layout.target_colour())   # 原来是 layout.target_zone()
```

两种写法在同一个布局上给出同一块区（目标区的颜色就是 `target_colour()` 的定义），改的是
**oracle 的输入**：现在它读的是指令里的那个颜色词，再查画面里哪块区涂了它——与策略要做的两步
一致；原来读的是配置里的区键名，跳过了查找这一步。

剩下两条规则：

| 模式 | 读什么 | 期望成功率 |
|---|---|---|
| `oracle` | 指令说的颜色 → 涂那个颜色的区 | 1 |
| `nearest_zone` | 只看角度，不看颜色也不看指令 | 约 1/2 |

### 11.4 `obs/goal_id`：给没有语言输入的基线的目标通道

指令承重之后，不读语言的基线（RL / SAC）拿不到目标是哪一块。09-08 的计划把这一条记为
「linkbar 改动的必然后果」，这次一起落地。

做法与已有的 `goal.instruction_fn` 同形，任务侧不写 python 注册表：

```yaml
goal:
  instruction: "Turn the bar so its pin comes to rest inside the sector marked by the {target_colour} band."
  instruction_fn: "…linkbar_rotate_to_zone:render_instruction"
  goal_id_fn:     "…linkbar_rotate_to_zone:render_goal_id"
```

`render_goal_id` 返回 `LinkbarRotateLayout.goal_id()` = 目标区颜色在 `zones.colors` 键序里的
下标，即 **red=0、blue=1**。yaml 里两个键的书写顺序就是编号顺序，不另存一张映射表。

**给的是颜色编号，不是区编号。** 给区编号（0=color_1、1=color_2）等于直接把「往左转还是往右转」
告诉策略，画面可以完全不看——那和把颜色涂在销上是同一类捷径。给颜色编号，策略拿到的是「这回
要红的」，还得在画面里找红块在哪。

落到数据集（`h5_schema.py` 版本 0.2.0 → **0.3.0**，纯增字段）：

| 位置 | 内容 |
|---|---|
| `setup.attrs["goal_id"]` | 本 episode 的目标编号 |
| `timestep_<K>/obs/goal_id` | 同一个数，int64 标量，逐帧重复 |

逐帧重复是因为它是策略输入的一部分，和图像一样：一个 timestep 就该够拼出策略的输入向量。
值从 `EpisodeSpec.variant.goal_id` 来（新增字段，默认 0），由
`variant_episode.resolve_goal_id` 读 `goal.goal_id_fn` 填。

**没有声明 `goal_id_fn` 的任务写 0。** 这是老实的：它们的指令本来就是常量（diverter_route_ball
一个终点，bar_through_hole 哪个孔通只在画面里），只有一个目标，编号就该只有一个值。

**不另存编号↔颜色的对照表。** 每一帧的 `info.attrs["task_goal"]` 里写着完整句子
（"…rests on the red zone."），所以 `(goal_id, task_goal)` 这一对在文件里自解释，拿到 H5 而
没有仓库的读者也能把 0 对上 red。

### 11.5 实测

离线（已过）：

| 门 | 读数 |
|---|---|
| `check_linkbar_zone_geometry.py` | 全过。第 3 条从「销与两区都不同色」改成「梁上三处涂色（梁／转轴组／手柄）都不在调色板里」，另加「`zone_for_colour(target_colour())` 等于目标区」「`goal_id` 反查回目标颜色」「换 `zones.target` 时 `goal_id` 跟着变」三条 |
| `check_linkbar_planner.py` | oracle 6/6，`nearest_zone` 恰好 3/6。六个用例上红蓝分配也交叉了，所以 oracle 的颜色查找确实被考到 |
| `check_variant_corners.py --task linkbar_rotate_to_zone` | **20 角点，20 可行，0 拒**（角点数不变：`distinct_choice` 在角点里固定取前两个键） |
| `check_variant_rng.py`（13 个任务全跑）| 全过。linkbar 段：`sampled_leaves` 去掉 `linkbar.pin.colour_name`，`assignment` 覆盖 2 种有序对，**首抽拒绝率 0.002**（门 0.02，与改动前逐位相同——颜色从来不参与拒绝，几何逐 seed 也没变）|

1000 个 seed 上两条轴的实际分布，用来核「目标在哪一侧」与「目标是什么颜色」确实独立：

| 量 | 读数 |
|---|---|
| `zones.target` | color_1 507 / color_2 493 |
| `zones.assignment` | (red, blue) 492 / (blue, red) 508 |
| 目标区的颜色（= 指令里的词 = `goal_id`）| red 489 / blue 511 |
| 四种组合 | color_1+red 244、color_1+blue 263、color_2+red 245、color_2+blue 248（各约 250）|

四格都在 250 附近，所以「不读指令、永远转向偏左那块」与「不读指令、永远转向红块」都恰好是抛硬币。
同一份 1000 seed 里两区同侧 390、异侧 610、净角距 < 5° 的 65、初始角贴禁区边的 103——与改动前一致。

GPU seed 0–9（**改画法后重跑**：`runs/linkbar_variation/20260910_band/`，4090，三格/seed；
09-09 那批 `20260909_redblue/` 是旧画法、旧指令句子，留档但以本节为准）：

| 组 | 读数 |
|---|---|
| `oracle` | **10/10 PASS** |
| `nearest_zone` | **3/10 success**（落在 0.3–0.7 的防捷径带里）|
| `visual` | 10/10 出片 |

同一批 seed 上目标颜色 red 6 / blue 4，红蓝分配 (red, blue) 3 / (blue, red) 7；两区同侧 4、
异侧 6；净角距最小 7.08°（seed 6，接近相邻），最大 115.61°（seed 1）。

目视（oblique 机位，抽 seed 0 / 1 / 5 的首帧核对）：连接梁通体是灰的，梁上看不到任何鲜艳
颜色；桌上只有一红一蓝两块，红在左在右逐 seed 变（seed 0 红 +15.35°／蓝 +76.23° 同侧，
seed 1 蓝 −80.11°／红 +51.50° 异侧，seed 5 蓝 −34.36°／红 −8.03° 几乎相邻）。

角点物理 20 格（`runs/linkbar_rotate_to_zone_corners/20260910_band/`）：**oracle 20/20 PASS**。
此前唯一一份角点证据是 `20260902_205605/`，行里还写着 `assignment.color_1=orange`，早于 09-08
与 09-09 两次改动，已作废。（2026-09-09 角点证据的口径改为「解析层跑全部顶点 + 物理层跑覆盖
数组」，linkbar 只有四条轴、20 个顶点，两种口径在这里是同一件事。）

**落位帧目视（2026-09-10）**：`runs/linkbar_variation/20260910_band/seat_color_{1,2}_{oblique,topdown}.mp4`。
三条结论：

1. 改画法后色条是看得清的方块，红蓝在任何机位都分得出。
2. **`topdown` 机位这个任务用不了**：Franka 的小臂正压在连接梁上方，挡掉大半个场景。
   （`seat_color_2` 那张仍能看出灰梁指向左侧、梁端落在蓝条上。）人看的机位仍用 `oblique`。
3. 销悬在桌面上方 52 mm，所以从任何斜机位看，销与桌面上的色条都不会重合——这是视差，
   画法解决不了。**「色条标出一个扇形、进扇形即成功」这个说法正是为此**：要读的是
   「梁指不指着那条色条」，不是「销压没压住色条」。指令措辞已与这个读法对齐。

**seed → 变体的映射只在颜色这一条轴上变。** 每条轴有自己命名的随机流，颜色这条流叫
`linkbar_rotate_to_zone/zones.colors`，抽法从「六选三」变成「二选二」；`zones.target`、两区角度、
`init_frac` 三条流的输出逐 seed 不变。所以 §8.6 记录的角度、扫掠幅度、`max_lag` 仍然成立，重跑
sweep 是为了新的画面和少掉一个对照组，不是因为几何变了。

### 11.6 销改成灰色之后的可辨性

这是目视项，不是算出来的。桌面是浅灰 0.78–0.82，销是 0.55 的转轴灰，色块是红
`[0.85, 0.15, 0.15]` 或蓝 `[0.15, 0.45, 0.85]`——亮度差是够的，但要在真视频里确认。如果看不清，
退路是把销、套环、手柄盖改成手柄已有的炭黑 `[0.12, 0.13, 0.15]`：梁上本来就有这个颜色，不算
引入新的标识色。

### 11.7 判据窗口放宽到 ±12°、色条收窄到 18 mm（2026-09-10 下午）

11.6 修完画法之后，色条是 47.5 mm 弧 × 40 mm 径向，**看着像方块而不是扇形的外周**。要让它读作
一条弧带，弧长要比径向宽出好几倍。两个数一起动：

| | 改前 | 改后 |
|---|---|---|
| `zones.half_width_deg` | 8° | **12°**（弧长 47.5 → 71.2 mm） |
| `zones.radial_width` | 40 mm | **18 mm** |
| `zones.segments` | 7 | **10**（两端过画 +0.25° → +0.16°，半径 170 mm 上 0.47 mm） |
| 弧 : 径 | 1.2 : 1 | **4.0 : 1** |

**12° 是上界，不是随手取的。** 销的出生禁区跟着半宽走（`half_width + pin_start_margin`），而
初始角只有 `init_span_deg = ±15°` 可抽，区一落到 0° 附近就把可用区间吃光。1000 seed 实测首抽
拒绝率：

| 半宽 | ±8° | ±10° | **±12°** | ±14° | ±16° |
|---|---|---|---|---|---|
| 拒绝率 | 0.002 | 0.005 | **0.010** | 0.036 ✗ | 0.075 ✗ |

门是 0.02（`check_variant_rng.py` 的 `MAX_REJECTION`），所以 ±12° 是不破门的最宽。

**径向宽不需要比销宽。** 40 mm 原本是按「销压在色条上、两侧各露 10 mm」设计的（= 销直径两倍）。
自 11.6 起说法已经改成「色条标出一个扇形，进扇形即成功」，而销悬在桌面上方 52 mm、斜机位下
与色条本来就因视差不重合，要读的是「梁指不指着这条色条」。所以径向宽只需要看得清，18 mm 够。

**跟着半宽同步改的四处**（不改就会两区重叠或跑出导轨）：

| 量 | 改前 | 改后 | 定义 |
|---|---|---|---|
| 两区中心可放范围 | ±82° | ±78° | 导轨端点 90° − 半宽 |
| 两区最小中心角距 | 16° | 24° | 2 × 半宽 |
| 销出生禁区 | 10° | 14° | 半宽 + `pin_start_margin_deg` |
| 角点命名对 | `rail_ends` ±82、`touching` 间距 16、`same_side_far` (60, 82) | ±78、间距 24、(54, 78) | 同上两条 |

**`motion.target_tolerance_deg` 不跟着放宽**，仍是 4°：它原本是半宽的一半，现在是三分之一，
等于对机械臂的要求比以前严一点。放宽判据是为了画面，不给执行让路。

**任务确实变容易一档**：成功窗口 16° → 24°，oracle 实测到位误差 2.27° 从占窗口的 28% 降到 19%。

**顺带：几何门里写死的 8° 全部改成读真值。** 半宽一改，`check_linkbar_zone_geometry.py` 里
`touching` / `rail_edge` / `pin_at_margin` / `overlap` / `off_rail` / `pin_near_zone` 以及三组
初始角区间的期望值同时冒出 8 条假失败——它们都把 8° 和 10° 抄成了字面量。现在这些用例按
`half_deg`、`keep_out = half + margin`、`rail.end_deg`、`init_span_deg` 算出来，半宽再动不会
再假失败。

**读数（`runs/linkbar_variation/20260910_arc/`、`runs/linkbar_rotate_to_zone_corners/20260910_arc/`）**

| 门 | 结果 |
|---|---|
| 几何门 / planner 门 | 通过；oracle 6/6、`nearest_zone` 3/6 |
| 角点解析 20 顶点 | 20 可行、0 拒 |
| 1000 seed 包络 | 首抽拒绝率 **0.010**（门 0.02）；同侧 329 / 异侧 671、净角距 <5° 的 64 格 |
| GPU seed 0–9 | oracle **10/10**、`nearest_zone` **3/10**、visual 10/10 |
| GPU 角点物理 20 格 | oracle **20/20** |

目视：色条现在是沿导轨的一段弧带，红蓝都读得出，梁通体是灰的。示例
`episode_s1_oracle_oblique.mp4`（seed 1，指令说 blue，蓝在 −76.32° 是远的那条，红在 +50.80° 更近，
梁转 −89.63° 绕开近处的红条落到蓝条，`task_success=True`）。
