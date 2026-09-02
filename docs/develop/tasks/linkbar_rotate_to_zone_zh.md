# docx 4.4 旋转连接杆转到同色区域 —— 工程记录

> 日期：2026-08-20 开工（首版：插口 + 小车），2026-08-27 改造（颜色区域），2026-09-01 改版（固定导轨 + 自由两区，见 §5.3）
> 上游：`../TopoGym_tasks.docx` §4.4；2026-08-27 review 意见；2026-09-01 变体要求
> 配套：[`rigid_first_track_zh.md`](rigid_first_track_zh.md)（本任务在纯刚体轨道中的位置）、
> `../framework/task_taxonomy_zh.md` §4.4（C4 判定契约）、
> [`variation_and_difficulty_plan_zh.md`](variation_and_difficulty_plan_zh.md) §3.8 / §6.8（随机化）
>
> 目标模块：`topogym/tasks/connectivity/linkbar_rotate_to_zone.py`

---

## 0. 结论摘要

- 场景：固定立柱上铰接一条连接梁，梁绕竖直轴转，梁端的销在水平圆上走。圆上画一段固定跨度
  （±90°）的虚线导轨，导轨上任意位置放两块互不重叠的颜色区域（可同侧、可相邻；从 `zones.colors`
  六色调色板里取两种不同颜色），销、销套环、手柄盖三处取其中一块的颜色。区键名 `color_1` / `color_2`
  无方位含义（2026-09-01 前为 `left` / `right`）。
- 判据：松手沉降后，销的关节角落在同色区域的角窗口内，且关节角速度低于阈值。单帧画面
  可辨：销在同色区里，或在异色区／区外。
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
| 目标 | 销停在与销同色的区域内 |
| 区域 | 两块，在固定导轨 [−90°, +90°] 上任意放置、互不重叠（默认 −45° / +55°），角半宽 8°，径向宽 40 mm，纯视觉 |
| 动作 | 夹爪夹手柄转梁一次，松手，退刀 |
| 不变量 | `pin_zone ∈ {color_1, color_2, None}`，定义在梁的关节角上（`"space": "joint_angle"`） |
| 物理层 | `at_rest`：沉降 30 步后关节角速度 ≤ 0.05 rad/s |
| 指令 | 常量 `"Turn the bar so its pin rests on the zone that matches its colour."`；要读的信息（销的颜色）在场景里 |

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

销、销套环、手柄盖三处同色。销是梁上最小的零件且在梁下方，套环与手柄盖把同一颜色放到
oblique / wrist 机位看得见的位置。

### 2.2 颜色

| 用途 | 值 |
|---|---|
| 区域 orange | `[0.88, 0.55, 0.10]` |
| 区域 blue | `[0.15, 0.45, 0.85]` |
| 区域 green | `[0.20, 0.68, 0.28]` |
| 区域 red | `[0.85, 0.15, 0.15]` |
| 区域 purple | `[0.58, 0.25, 0.75]` |
| 区域 yellow | `[0.95, 0.85, 0.15]` |
| 梁 | `[0.42, 0.46, 0.52]` |
| 转轴／轮毂／手柄座 | `[0.55, 0.56, 0.58]` |
| 手柄 | `[0.12, 0.13, 0.15]` |
| 立柱 | `[0.50, 0.51, 0.53]` |
| 桌面 | 0.78–0.82 浅灰 |

六色对桌面浅灰、对梁的蓝灰都有明度或色相差；不随机化时默认 color_1=blue、color_2=orange。

### 2.3 区域的画法

`LinkbarRotateSceneBuilder._add_zones`：沿销的圆弧，从 `centre − half` 到 `centre + half`
均分 `segments` 段，每段一个 `gs.morphs.Box(fixed=True, collision=False)`，yaw 取该段中心角，
长度为该段的弦长 + 0.5 mm 搭接。7 段各 2.3°，弦弧偏差 < 0.1 mm。

两块区域出自同一个循环，除颜色外完全相同。

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
| `pin_color()` | `zone_color(target_zone())` |
| `nearest_zone(angle)` | 角差最小的区 |

| `rail_span()` | `(rail.start_deg, rail.end_deg)`，弧度 |

`validate()`（2026-09-01 版）拒绝：初始角不在导轨上；任一区未整体落在导轨内（`centre ± half_width` 出 [−90°, 90°]）；
初始销在任一区内或其 `pin_start_margin_deg`（2°）余量内（即 `|init − centre| < half_width + 2°`）；两区中心角距 < 2·half_width（相等 = 相邻，允许）；
两区同色；`target` 不是 color_1/color_2。改版前的「两区异侧」「扫掠幅度 [15°, 75°]」「角距 ≥ 2·half_width + 5°」三条已删除。

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

三条随机化轴，均为 hydra 覆盖：

| 轴 | 叶子 | 说明 |
|---|---|---|
| 目标 | `task.zones.target` | color_1 / color_2 |
| 角位置 | `task.zones.color_1.angle_deg` / `task.zones.color_2.angle_deg` | 导轨 [−90°, 90°] 上任意，两区不重叠 |
| 颜色分配 | `task.zones.assignment.color_1` / `.color_2` | 调色板六色里两种不同颜色 |

对照规则（`run.oracle_mode`）：

| 模式 | 规则 | 期望成功率 |
|---|---|---|
| `oracle` | 转到 `target_zone()` | 1 |
| `nearest_zone` | 转到角差最小的区 | 0.5（target 与角位置独立抽样时） |

`tests/check_linkbar_planner.py` 六例交叉（异侧两例、同侧四例）：oracle 6/6，`nearest_zone` 恰好 3/6。

变体轴声明在任务 yaml 末尾的 `variation:` 块（2026-08-29 首次注册在 python `_REGISTRY`，2026-09-01 改为固定导轨版并搬进 yaml；`generation/layout_randomization.py` 只读该块）：

| kind | 叶子 | 取值 |
|---|---|---|
| `choice` | `zones.target` | color_1 / color_2 |
| `distinct_choice` | `zones.assignment.color_1` / `.color_2` | `zones.colors` 的键，30 种有序组合 |
| `spaced_pair` | `zones.color_1.angle_deg` ≤ `zones.color_2.angle_deg` | 两中心在 [−82, 82]（导轨 ±90 减半宽 8），角距 ≥ 16（= 2·半宽，相邻允许）。先在 [−82, 66] 独立抽两值、排序、大者加 16：非重叠对上的均匀分布，无需为重叠拒绝 |
| `uniform` | `linkbar.init_angle_deg` | [−15, 15] |
| `validate` | `linkbar_rotate_to_zone:validate_task_cfg` → `LinkbarRotateLayout.validate()` | 不过则整体重采（按 seed 确定） |

触发：`run.randomize_layout=true run.seed=<seed>`（两个 demo 均接入，打印一行 `linkbar_rotate_to_zone variant seed=… target=… color_1_deg=… color_2_deg=… init_deg=… gap_deg=… same_side=…`）。
离线门 `tests/check_variant_rng.py`（1000 个 seed 的包络与确定性）。
实验脚本 `bash_scripts/tests/linkbar_variation_sweep.sh`：每 seed 三格——`visual`（静态一帧录像，人眼看）、`oracle`（须 `task_success=True`）、`nearest`（对照成功率，期望接近 1/2）。2026-08-27 版结果见 §8.2；改版后待跑。
分档不预设，按 sweep 结果划定：`variation_axes_plain_zh.md` §5。

### 5.3 2026-09-01 改版：固定导轨 + 自由两区

§8.2 的视觉结论是十个变体画面几乎一样：两区被限制为分居初始角两侧、各在 [15°, 75°]（改前 [35°, 75°]）扫掠带内，
离散组合只有 2×2，角度包络在 oblique 机位上只差几个像素。改为：

- **导轨固定**：`rail.start_deg / end_deg = ±90°`，不随两区位置变；`_add_rail` 沿整条导轨等距画 36 格，
  落在区跨度内的格跳过（色块盖在那段上，同高度两种标记会闪烁）。±90° 是已实测过的绝对范围（seed 6 区中心 +84.45° oracle 通过；
  改版前 `_ShiftBy` 平移后区中心绝对值本就到 90°）。
- **两区自由**：中心可在导轨上任意处，同侧或异侧、相邻或分开都允许，只要求不重叠。`nearest_zone` 对照在同侧布局下同样只有一半正确。
  同侧且目标是远区时，销在途中会掠过近区——判据只读松手后的静止态，不算错。
- **销出生不在区内**：新增 `zones.pin_start_margin_deg = 2°`，`|init − centre| ≥ half_width + 2°`，否则拒绝。这是结构性约束，
  1000 seed 实测首抽拒绝率 0.234（预估 20–25%：每区 20° 禁区 / 约 164° 可用），不适用「拒绝率 > 5% 即包络过宽」的一般规则；
  `check_variant_rng.py` 对本任务的阈值为 0.30，并注明理由。重采仍是 seed 的纯函数。
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
