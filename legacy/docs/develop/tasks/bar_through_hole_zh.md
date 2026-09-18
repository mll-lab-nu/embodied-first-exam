# bar_through_hole（docx 2.3）：变体生成与可解性

> 日期：2026-09-04 部署，2026-09-08 退役 far 托座、孔径下界 29 → 24 mm（§7），2026-09-09 圆杆圆孔与三孔改造（§8、§9）。本任务此前没有任务文档；场景、原语、判据的取值与理由在
> `configs/task_configs/bar_through_hole_topogym_tabletop_v1.yaml`、`topogym/tasks/routing/bar_through_hole.py` 的注释
> 与 `rigid_first_track_zh.md` §4.1。本文只记变体部署这一步（`variation_axes_plain_zh.md` §6.2 第 12 步）。

---

## 1. 任务回顾（术语按仓库）

左侧两个 V 形托座（`cradles.near_a` / `near_b`）托着一根六棱柱杆（`bar`，对边距 0.018），右侧竖立面板（`panel`）中央开六角孔
（`aperture`，对边距 `across_flats`），面板后方另一托座（`cradles.far`），其 `seat_axis_z` 与孔下沿 + 杆 inradius 相等，穿过去的杆落在
「孔 + far 托座」两点上。oracle（`AxialInsertPrimitive`，`run.oracle_mode=insert`）：抓杆 → 抬升 → 手腕对准（`max_align_tilt_deg` 1.0）→
横推穿孔 → 落座释放。判据 `threading_count`：杆轴与面板中平面的交点落在六边形内、两端分居两侧。

对照 `run.oracle_mode=bypass`：起止 xy 完全相同、搬运高度抬到面板顶之上，杆落在面板顶上，交点在六边形外 → 判失败。
没有防捷径离散轴，绕过面板顶由物理本身判 0。

## 2. 可解性判据与横推高度窗口

第 12 步排在最后的原因是两项前置：四个搬运高度（`primitive.grasp_z / lift_z / insert_z / seat_z`）是手写绝对值、任务没有校验器。
本轮把四个高度改为 `BarThroughHoleLayout` 推导（`grasp_hand_z / lift_hand_z / insert_hand_z / seat_hand_z`，杆心 z + `HAND_TO_PAD_Z`），
yaml 只留推导所需的量（`primitive.lift_height` 0.045、`seat_drop` 0.001、`push_clearance_min`、`hand_half_depth` 0.025）与不随轴动的
`approach_z` / `clear_z`。

**横推高度窗口 `push_window`**（本轮新定义的量）：杆心在横推段允许的 z 区间。
下界 = 各托座斜面顶端（apex + `jaw_width`·cos 45°）的最大值 + 杆 inradius（杆底不刮 far 槽的夹板）；
上界 = 孔心 + (孔 inradius − 杆 inradius)（杆顶不撞孔上沿）。far 托座 `seat_axis_z` 随孔下沿走，所以

    窗口宽度 = across_flats − 0.02412        0.029 → 4.88 mm、0.032 → 7.88 mm、0.038 → 13.88 mm

原手写 `insert_z` 0.193 把 0.032 的 7.88 mm 切成 4.9 / 3.0；推导取窗口中点（0.192），两侧各 3.94 mm。
计划文档 §3.3 原表把 `across_flats` 下界放在 0.027（横向单边净空 4.5 mm），但没算这条竖直窗口：0.027 只剩 2.9 mm，每侧 1.45 mm。
**决定（2026-09-04 当时）**：包络下界 0.029，`push_clearance_min` 0.0024（窗口 ≥ 4.8 mm）。**2026-09-08 起这一节的算术已被 §7.2 取代**：far 托座退役，窗口不再由它的斜面顶端定，下界放到 0.024。以下保留当时的推导。要再往下推，可改的是 far 托座 `jaw_width`
（0.016 → 0.010 使窗口 +4.2 mm），那是几何决定，留到实测之后。

## 3. 变体轴与派生

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| B | `aperture.across_flats` | U[0.024, 0.038] | 单调裕度轴。横向单边净空 = (af − 0.018)/2 = **3.0 .. 10 mm**。2026-09-08 下界从 0.029 放到 0.024：卡住它的是横推窗口，而那条窗口的下沿由 far 托座定，托座退役后窗口宽了一倍多（§7.2） |
| B | `bar.rest_x`、`bar.rest_y` | U[−0.080, −0.020]、U[−0.030, 0.030] | 杆连同两个近端托座平移。`rest_pos: [x,y,z]` 拆成三个标量叶子（随机化不走列表下标） |
| B | `panel.x` | U[0.100, 0.160] | 面板连同 far 托座平移 |
| B→C | `bar.length_frac` → `bar.length` | **派生** | `[0.170, min(0.230, 2·(面板近面 − 0.010 − rest_x))]`；最坏角点（rest_x −0.020、panel.x 0.100）上限 0.190 |
| B→C | `bar.grasp_frac` → `bar.grasp_offset` | **派生** | `[0.060, min(0.090, length/2 − 0.015)]`；下界 = 手半深 + 面板半厚 + 0.020，上界保证指垫合在杆上 |
| C | `cradles.near_a.x`、`near_b.x`、`far.x` | **派生** | `rest_x − 0.020`、`rest_x + length/2 − 0.030`、`panel.x + length/2 − 0.030`（基准还原 −0.070 / 0.020 / 0.200） |
| C | `cradles.far.seat_axis_z` | **派生** | 孔下沿 + 杆 inradius（随 `across_flats` 变） |
| C | 托座 y（无 yaml 叶子，`Layout.cradle_y`） | **派生** | 近端两个 = `bar.rest_y`，far = 0（面板中线）。此前三个硬写 0，见 §5 首跑 |
| D | `aperture.center_z`、`bar.rest_z`、近端 `seat_axis_z`、`panel.top_z`、`jaw_width`、`approach_z` / `clear_z` | 固定 | |

不用 `pair` kind：托座跟随由 `derived` 就地写回，与 gate / c_ring 同形。三者独立抽会撞的组合（杆端进面板、抓点越过杆端）
都用归一化 frac 派生成构造式满足，不靠拒绝。

`checks()` 九行（统一签名；`validate()` 任一行不 ok 即拒绝；建场景、随机化、离线门、角点门、demo 启动共用）：

| 行 | 读数 | 门 | 基准 |
|---|---|---|---|
| `push_window` | 窗口宽度 | ≥ 2·`push_clearance_min` = 0.0048 | 0.0079 |
| `bar_end_clears_panel` | 面板近面 − 杆静置近端 | ≥ 0.010 | 0.065 |
| `near_cradle_clears_panel` | 面板近面 − near_b 远缘 | ≥ 0.010 | 0.080 |
| `grasp_on_shaft` | length/2 − grasp_offset | ≥ 0.015 | 0.025 |
| `grasp_clears_near_a` | 抓点到 near_a 的 x 距 − 半槽长 | ≥ 0.015 | 0.040 |
| `hand_short_of_panel` | 面板近面 − 落座时手前缘 | ≥ 0.010 | 0.035 |
| `panel_clears_home` | home 指尖 0.1608 − `panel.top_z` | ≥ 0（守编辑，不随轴动） | 0.0108 |
| `hand_reach` | 落座时手心距底座 | ≤ `reach.max_hand_dist` 0.700 | 0.625 |
| `far_cradle_matches_sill` | far 托座轴高与孔下沿 + inradius 之差 | ≤ 0.001 | 0 |

## 4. 离线实测（2026-09-04）

- `tests/check_bar_through_hole_geometry.py`（新）：推导高度在基准 yaml 上还原手写值（grasp 0.1579 / lift 0.2029 / seat 0.1829；
  insert 0.1920 对原 0.193）；`derive_task_cfg` 在基准 frac 上还原杆长 0.200、抓取偏移 0.075、三个托座 x、far 托座 0.079；
  窗口在 0.029 / 0.032 / 0.038 三点 4.88 / 7.88 / 13.88 mm；最坏角点杆长区间 [0.170, 0.190]、抓取区间 [0.060, 0.070]，九行全过。
- `tests/check_variant_rng.py` bar 段：1000 seed 首抽拒绝率 **0.000**；派生叶子逐 seed 复核公式；九行全过。
- `tests/check_variant_corners.py --task bar_through_hole`：6 条连续轴 → 64 角点。首跑 32 个 `across_flats=0.029` 角点全部被
  `push_window` 行拒（4.88 < 5.0 mm：手算偏置 0.0241 实际是 0.02412），`push_clearance_min` 0.0025 → 0.0024 后 **64/64 feasible**，
  Hydra 覆盖路径复现一致。
- 固定布局 GPU 复跑（推导高度，insert 由 0.193 → 0.192）：`success=True threading=1 phases=16/16`，`align_tilt` 0.01°，
  `finger_qpos` 0.0092，与 08 月基线相同。

## 5. GPU 实测（4090，2026-09-04）

### 5.1 seed 0–9（`bash bash_scripts/tests/bar_through_hole_variation_sweep.sh`，`runs/bar_through_hole_variation/20260904_seeds/`）

visual 10/10 有帧且逐 seed 可分（孔径、杆长、杆与面板的位置逐格不同，无穿模）。oracle / bypass 逐格：

| seed | af | rest_x | rest_y | panel_x | length | grasp_off | side_clear | window | align_tilt | finger_qpos | oracle | bypass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.0329 | −0.0655 | +0.0081 | 0.1016 | 0.1787 | 0.0632 | 0.0074 | 0.0087 | 0.01° | 0.0092 | PASS | bar_not_threaded |
| 1 | 0.0317 | −0.0693 | +0.0253 | 0.1458 | 0.1880 | 0.0730 | 0.0069 | 0.0076 | 0.01° | 0.0093 | PASS | bar_not_threaded |
| 2 | 0.0295 | −0.0692 | −0.0111 | 0.1219 | 0.1816 | 0.0712 | 0.0057 | 0.0054 | 0.01° | 0.0091 | PASS | bar_not_threaded |
| 3 | 0.0326 | −0.0292 | −0.0114 | 0.1344 | 0.2186 | 0.0885 | 0.0073 | 0.0085 | 0.01° | 0.0091 | PASS | bar_not_threaded |
| 4 | 0.0358 | −0.0480 | −0.0105 | 0.1322 | 0.2265 | 0.0841 | 0.0089 | 0.0117 | 0.01° | 0.0091 | PASS | bar_not_threaded |
| 5 | 0.0348 | −0.0555 | −0.0121 | 0.1136 | 0.1781 | 0.0643 | 0.0084 | 0.0106 | 0.01° | 0.0091 | PASS | bar_not_threaded |
| 6 | 0.0292 | −0.0308 | +0.0041 | 0.1227 | 0.2270 | 0.0764 | 0.0056 | 0.0051 | 0.01° | 0.0092 | PASS | bar_not_threaded |
| 7 | 0.0377 | −0.0374 | +0.0182 | 0.1242 | 0.1942 | 0.0629 | 0.0098 | 0.0136 | 0.01° | 0.0093 | PASS | bar_not_threaded |
| 8 | 0.0363 | −0.0309 | −0.0181 | 0.1536 | 0.1772 | 0.0645 | 0.0092 | 0.0122 | 0.01° | 0.0091 | PASS | bar_not_threaded |
| 9 | 0.0315 | −0.0329 | −0.0041 | 0.1434 | 0.1876 | 0.0662 | 0.0067 | 0.0074 | 0.01° | 0.0092 | PASS | bar_not_threaded |

结论：

- oracle **10/10**，`phases=16/16`、`threading=1`、`release_stable=True`，`drift` ≤ 0.00034。
- bypass **10/10 判失败**（`threading=0`，`geometry_ok=False`）：起止 xy 相同、搬运高度抬到面板顶之上，杆落在面板顶上，交点在六边形外。
  没有防捷径离散轴，绕过面板顶由判据本身判 0，与 §1 的设计一致。
- `align_tilt` 全部 0.01°（门 `max_align_tilt_deg` 1.0）：手腕对准的残差不随轴变。`push_z` 恒 0.0891，是 §2 窗口中点推导的结果
  （杆心横推高度只依赖孔心与托座顶，两者本轮都不随轴动，只有窗口宽度随 `across_flats` 变）。
- 窗口最窄的两格 seed 2 / 6（`across_flats` 0.029x，窗口 5.1–5.4 mm）也过。

### 5.2 角点 sweep（`bash bash_scripts/tests/variant_corners_sweep.sh bar_through_hole oracle bypass`，`runs/bar_through_hole_corners/20260904/`）

`tests/check_variant_corners.py` 把 6 条连续轴的端点全组合成 64 个角点，每格走 demo 的固定布局路径（`run.randomize_layout=false` + `task.*` 覆盖），
一格 25 s。结果：oracle **64/64**，bypass **64/64 判失败**（`bar_not_threaded`）。

**首跑暴露的隐含假设：三个托座 y 硬写 0。** 第一个 `bar.rest_y ≠ 0` 的角点（c000，`rest_y=−0.03`）里，两个近端托座还留在 y=0，
杆按 `rest_y` 生成在槽旁边、掉到桌上，手指在杆的原定位置合了个空。这是本任务在执行链里的隐含假设，与 diverter `max_lag`、gate `pinched` 与取板姿态插值、
c_ring `passed_through` 同列：随机 sweep 里 `rest_y` 离 0 最远只有 0.025，托座斜面还兜得住；角点把它推到 0.030 才掉出去。
处置：`BarThroughHoleLayout.cradle_y(name)`，近端两个托座跟随 `bar.rest_y`，far 托座留在面板中线（孔在哪杆就落在哪）；
建场景与 `checks()` 都从这里取；`tests/check_bar_through_hole_geometry.py` 加断言（`rest_y=0.030` 时 near 0.030 / far 0）。
修前失败格的日志已被复跑覆盖，本节只记机制，不记读数。包络不动。

**取杆读数只随 `rest_y` 变。** 64 格的 `finger_qpos` 只有两种值：`rest_y=−0.03` 的 32 格 0.0090、`rest_y=+0.03` 的 32 格 0.0094，
`across_flats` / `rest_x` / `panel.x` / `length_frac` / `grasp_frac` 都不影响；seed 0–9（`rest_y` −0.018 … +0.025）落在中间 0.0091–0.0093。
与 gate「取板读数只随停放架位置变」同型。

**窗口最窄的 32 格**（`across_flats=0.029`，`push_window` 4.88 mm，门 4.8 mm）全过：`push_clearance_min` 0.0024 的门不紧，§2 的决定成立。

### 5.3 `physical.min_finger_qpos` 回填（`rigid_first_track_zh.md` §7 第 5 条）

`finger_qpos` 是合爪并静置 `close_hold_steps` 后两指行程的最小值，在 attachment 挂上之前读（`axial_insert.py`）。assisted attachment 下
`lift_delta` / `lift_tilt` / `grasp_xy_error` 三条门都由 attachment 保证，指行程是唯一能区分「夹到杆」和「夹了个空」的读数。
此前门为 `null`（只打印不判），yaml 注释约定「先跑一次看读数，再把门设在读数与指令位之间」。

| 侧 | 读数 | 来源 |
|---|---|---|
| 夹到杆 | 0.0090–0.0094 | 5.1 + 5.2 共 148 格（oracle 与 bypass 同格相同：bypass 也抓杆，只是搬运高度不同） |
| 夹空 | ≤ 0.008 | 未实测。指垫之间没有杆时，位置控制把两指合到指令位 `grasp_qpos` 0.008；bar 自己唯一的夹空格（5.2 首跑 c000）日志已被复跑覆盖。gate 的空夹读数（指令位 0.005，读到 0.0018 / −0.0010）说明合爪前手指若被撞过，读数还会低于指令位，只会离门更远 |

门取 **0.0086**：低于最低夹杆读数 0.4 mm，高于指令位 0.6 mm。与 gate 的 0.004（夹板 0.0063–0.0075、空夹 ≤ 0.0018）同一做法。
这不是按分布反推 metric：metric 早已定为指行程，夹杆侧是抽样得到的经验簇，夹空侧是几何确定的指令位，门夹在两者之间。
回填后不重跑全 sweep（148 格读数已知全部 ≥ 0.0090），只复核两格：

| 格 | 目录 | 结果 |
|---|---|---|
| seed 0 oracle（读数 0.0092） | `runs/bar_through_hole_variation/20260904_fingergate/` | `success=True finger_qpos=0.0092`，`phases=16/16` |
| 角点 c000 oracle（`rest_y=−0.03`，读数 0.0090，离门最近） | `runs/bar_through_hole_corners/20260904_fingergate/` | `success=True finger_qpos=0.0090`，`phases=16/16`；resolved config 里 `min_finger_qpos: 0.0086` 已生效 |

**c000 目视核对（2026-09-05，`runs/bar_through_hole_grasp_video/`）。** 斜视录像里合爪那几帧被面板挡住，看不到指垫。
同一格开 `run.verbose=true` 加俯视 / 手腕 / 斜视三机位复跑（`oracle_c000_multi_{topdown,wrist,oblique}.mp4`、`oracle_c000_verbose.log`），结果行不变
（`success=True finger_qpos=0.0090 phases=16/16`），三处证据一致：

- 手腕视角（画面底部带白色指身的一对深色方块是指垫，中部一对灰色方块是托座侧壁）：两指从全开向杆合拢，同时贴到杆的两侧，杆在正中；抬升与横移期间两指一直贴着杆。
- 阶段行：`approach` 杆心 (−0.0800, −0.0300, 0.9746) → `lift_test` (−0.0799, −0.0300, 1.0172)，xy 不动、z 升 0.0426，杆是被正夹起来的，不是被拨动后挂住。
- 读数 0.0090 是单指到中心的距离，两指开度 18 mm 等于杆径；指令位 8 mm，两指是被杆挡住才停在 9 mm。

结论：离门最近的这一格，0.0090 对应的物理状态就是「指垫压在杆上」。夹空侧仍未实测，上表不变。

## 6. 文件集

```
configs/task_configs/bar_through_hole_topogym_tabletop_v1.yaml   primitive 段改为推导所需量、variation 块、min_finger_qpos 0.0086（09-04）
configs/run_configs/bar_through_hole.yaml                         randomize_layout / difficulty / variant_id
topogym/tasks/routing/bar_through_hole.py                         Layout 四个手高推导、push_window、cradle_x / cradle_y、length / grasp bounds+from_frac、checks（九行）/ validate / derive_task_cfg / validate_task_cfg
demos/routing/bar_through_hole_physical_insert_demo.py            randomize_task_cfg 接线、variant 行、checks 行、min_finger_qpos 接线
tests/check_bar_through_hole_geometry.py                          新：高度还原、派生还原、窗口三点、最坏角点区间、cradle_y、九行
tests/check_variant_rng.py                                        bar 段（1000 seed 拒绝率 0.000）
tests/check_variant_corners.py                                    TASKS 登记（64 角点）
bash_scripts/tests/bar_through_hole_variation_sweep.sh            新（visual / oracle / bypass）
bash_scripts/tests/variant_corners_sweep.sh                       bar 分支（对照组 bypass）
runs/bar_through_hole_variation/20260904_seeds/                   seed 0–9 三组
runs/bar_through_hole_corners/20260904/                           64 角点 oracle + bypass
```


## 7. 退役 far 托座，孔径下界随之放宽（2026-09-08）

### 7.1 会上的决定与实测结果

面板后方 20 cm 处原来还有第三个 V 形托座，接住穿过去的杆端。09-08 会上定：这是「不必要的难度来源」，改成**杆穿过孔、由孔本身架住**（顺带解决「干扰孔要不要也配支架」——都不配）。

实测比预期干净得多。原以为松手后杆的远端会下坠、在孔里前低后高地楔住，需要把倾角门从 10° 改成按孔的净空与板厚推导（那会是 20–35°）。**实际上杆是平衡在孔里的**：插入原语把杆推到 `insert_xy[0] = aperture_center()[0] = panel.x`，也就是把**杆心推到孔心**，所以杆的质心正好落在面板上。关掉 far 托座跑 oracle：

```
success=True threading=1 geometry_ok=True release_stable=True drift=0.00000
lift_tilt=0.03deg align_tilt=0.01deg
```

松手后位移 0，倾角 0.03°。**所以落座判据一个数都不用改**：`seated_z` 仍是「孔下沿 + 杆内接圆半径」（判定器本来就这么写，跟托座无关），`tilt_tolerance_deg` 仍是 10°，`seated_z_tolerance` 仍是 0.015。计划里「倾角门要按净空 / 板厚推导」那一条作废。

杆长在包络里变（0.170–0.230），但插入终点恒等于孔心，所以「质心落在面板上」是构造式成立的，与杆长无关。

### 7.2 孔径下界从 29 mm 放到 24 mm

原来卡住下界的是**横推高度窗口**：那条窗口的下沿取「所有启用的托座里最高的斜面顶端 + 杆内接圆半径」，而 far 托座的座高跟着孔下沿走——孔越小下沿越高，托座也越高，窗口越窄。29 mm 时窗口只剩 4.88 mm，正好压着 `push_window` 行的门（2 × `push_clearance_min` = 4.8 mm）。

far 托座退役之后只剩两个近端托座，它们在杆的出生高度 0.055，远低于孔心 0.086，于是窗口变成关于孔心对称的 ±(孔内接圆 − 杆内接圆) = `across_flats − 0.018`，比原来宽一倍多：

| 孔的对边距 | 改前窗口 | 改后窗口 |
|---|---|---|
| 24 mm | —（当时不可达） | 6.0 mm |
| 29 mm | 4.9 mm | 11.0 mm |
| 32 mm | 7.9 mm | 14.0 mm |
| 38 mm | 13.9 mm | 20.0 mm |

顺带，横推高度从 0.193 落到 **0.1889**——杆改为从孔的正中穿过，而不是骑在托座的斜面上方。

**下界取 24 mm 是量出来的**：关掉 far 托座跑 oracle，0.029 / 0.027 / 0.024 三档都 `success=True`、松手后 `drift=0.00000`；0.022 被 `push_window` 行拦下（窗口 4.0 mm < 门 4.8 mm），所以判据自己的几何底在 22.8 mm。取实测过的最紧值 24 mm，单边净空 3.0 mm，包络顶点由角点 sweep 复核。

**这条轴的量程因此从 [29, 38] 变成 [24, 38]**，单边净空 5.5–10 mm → 3.0–10 mm，难度范围宽了一倍还多。

### 7.3 跟着退役的东西

- `checks()` 九行 → **八行**：`far_cradle_matches_sill`（托座座高与孔下沿一致，≤ 1 mm）随托座一起走。
- `derive_task_cfg` 少写两个叶子：`cradles.far.x` 与 `cradles.far.seat_axis_z`。派生的托座只剩两个近端的。
- `far_seat_axis_z()` 改名 `seated_axis_z()`——它量的是「杆在孔里落座时的轴高」，与托座无关，判定器读的是同一个量。
- 指令去掉后半句：`"Push the bar through the hole in the panel and let it rest there."`
- yaml 的 `cradles.far` 段保留但 `enabled: false`：`add_v_block` 与 `push_window` 都按 `enabled` 逐个跳过，关掉就够；数值留作当时标定的记录。

### 7.4 实测

- 离线门 `check_variant_rng.py` bar 段：1000 seed 首抽拒绝率 **0.000**；单边净空最小 3.00 mm、横推窗口最小 6.00 mm（门 4.8）；加一行断言 far 托座不会被重新启用。
- 角点门：**64 角点 64 可行 0 拒**（轴数没变，只是孔径的下端换了）。
- 几何离线门：八行读数全过；四处钉住的期望值按新的推导更新（横推高度 0.193 → 0.1889，四个孔径的窗口宽度）。
- GPU 单格：oracle `success=True`（0.029 / 0.027 / 0.024 三档都过），对照 `bypass` 仍 `threading=0`、`bar_not_threaded` 判失败。
- GPU seed 0–9 三组（`runs/bar_through_hole_variation/20260908_nofarcradle/`）：**oracle 10/10**、
  `bypass` 10/10 判失败、`visual` 10/10 出片。抽到的孔径最紧到 **24.3 mm**（单边净空 3.1 mm，seed 6）
  也通过，`align_tilt` 十格都是 0.01°。
- **横推高度十格恒为 0.0860 = 孔心 z**，与孔径无关——这是「窗口不再由托座定、变成关于孔心对称」
  最直接的读数（改前它随孔径在 0.191–0.195 之间移动）。
- 变体行与汇总表去掉 `far_x` 一列：它报的是已停用的托座，留着会让读表的人以为那东西还在。
  上面这一轮的日志里还有这一列（改动在 sweep 之后），数据本身不受影响。


## 8. 圆杆圆孔（2026-09-09）

会上说六角孔「太像拼图游戏」，主体改成圆的，六角降为额外变体。

**用 16 边正棱柱，不用 `gs.morphs.Cylinder`。** 棱柱让三件事一行都不用改：生成的网格本来就轴沿 +x
（Genesis 的圆柱默认轴沿 z，要加出生旋转）、`convexify=True` 对棱柱是精确的（凸体的凸包是自己）、
判定器读杆的轴向是 `R @ (1,0,0)`。16 边在 18 mm 的杆上边长 3.6 mm，在本场景的相机距离下读作圆。

- `hexagon_vertices` → `regular_polygon_vertices(sides, across_flats)`；`hex_prism_mesh` → `prism_mesh(sides, …)`。
- 新增 `polygon_extents` 读外接矩形。**原来这里写死了 `circumradius`**——六角的最宽处是角、
  16 边的最宽处是平边中点，实测半宽 18.48 vs 16.00 mm，不改框子就是错的。
- 判定器 `hexagon_contains` → `polygon_contains`（N/2 个平行板带的交集）；奇数边直接拒绝，
  不当成偶数悄悄算。
- 新叶子 `bar.sides` / `aperture.sides` 默认 16，`checks()` 加 `profiles_match` 行：两者必须相等，
  否则「孔比杆宽多少」这个难度轴的量没有定义。六角变体把两个都设 6。

**开工前查过、不用改的两处**：`push_window` 用 `孔内接圆 − 杆内接圆`，对正 N 边形定义不变；
`v_block_seat_drop` 的文档明写「取截面而不是半径，正是为了让同一个 V 槽既接圆料也接六角料」。

**顺带修的**：`_visuals.add_aperture_ring` 把每段描边延长整整一个带宽好让拐角接上，那是 90° 拐角的
斜接量。六角上看不出来，16 边上每段多出 3 mm、描边渲染成齿轮。改成 `band/2 · tan(π/N)`，
16 边每端只多 1.0 mm。

## 9. 三个孔，只有一个通（2026-09-09）

### 9.1 设计原则：凡是提到孔的地方，都去问孔的实际位置

这个任务从一开始只有一个孔，而且那个孔恒在面板中线上。把孔挪开，这个假设散在几处会同时露出来。
用户 09-09 定的做法是不把它们当成几处难点，而是让每一处都**读真值**——收下来只剩一处真正的新代码。

`BarThroughHoleLayout.aperture_center()` 是全任务读孔位置的**唯一入口**：

| 谁读它 | 改了源头之后 |
|---|---|
| oracle 的插入终点 `insert_part_xy`（demo） | **零改动自动跟** |
| 判定器的穿孔判定 `aperture_center_yz` | **零改动自动跟** |
| `aperture_bbox()` / `sill_top_z()` | 已经走它，自动跟 |

同一条原则还收掉两处：

- **`hand_reach` 那一行量错了 y，是既有的潜在 bug**：`hypot(seat_hand_x − base_x, bar.rest_y − base_y)`
  用的是**杆的出生 y**，而落座时手在**孔的 y** 上。孔在中线、`rest_y` 只有 ±3 cm 时两者差 0.7 mm，
  从没显形；孔挪到 ±9.5 cm 就少报 8 mm。改成读孔的 y 之后，外侧孔 0.6322、中间孔 0.6250。
- **孔缘描边**（`add_aperture_ring`）隐含孔心在 y = 0，加 `center_y` 参数按孔放。
  （`add_panel_bolts` 已经吃显式的 `(y, z)` 站点，天然支持三个孔。）

**`center_y` 是记录不是真值。** `aperture_center()` 由 `open_index` 与 `pitch` **现算**，不读那个派生叶子；
派生只是把算出来的值写进配置好让它进 episode 的 variant 记录，`checks()` 的 `center_y_recorded` 行守两者一致。
为什么必须这样：任何不走随机化的路径（每一次固定布局的 demo）都不跑派生，叶子会停在 0.0，
于是无论 `open_index` 是几，任务都瞄中线那个孔——**09-09 第一次跑就是这样**，杆被送去撞盲孔，
而判定器读同一个过期叶子，把它判成了成功。

### 9.2 唯一的新代码：三开口的框

`_add_panel` 从「左柱 + 右柱 + 横贯的下槛与上楣」推广成 **[左柱][孔1][中柱][孔2][中柱][孔3][右柱]**，
下槛与上楣仍横贯整宽，每个开口各放自己的一圈斜角块（16 边形 14 块 × 3 孔 = 42 块）。
写法照旧：框的面朝面平铺不重叠（共面会 z-fight），斜角块之间允许体积重叠。

**盲孔**：从远侧塞一块盖板，厚度 = 板厚 − `blind_recess`，近侧留 8 mm 深的凹坑、坑底涂深色。
盖板填开口的外接矩形即可，多出去的部分埋进框里。

新增 `checks()` 行 `panel_strip`：三个孔留下的最窄一条实心面板（最外侧孔到板边，或两孔之间）
≥ 20 mm。1000 seed 实测最窄 43.2 mm。

### 9.3 **盲孔必须真的挡住杆**——搬运的物理模型是这条轴经过的地方

第一次跑 `wrong_hole` 时它成功了，本该失败。根因是我漏查了一条「这条新轴经过什么」：
**它经过了搬运的物理模型**。`il_contract` 那一行写着 `runtime_attachment=True`——插入阶段杆是被
`AttachmentManager` **运动学带着走**的（`RigidAttachment.sync()` 每步直接写位姿），不走接触，
**所以盲孔的盖板根本挡不住它**。

只靠判定器（瞄错孔 → 穿越点不在通孔内 → `threading = 0`）是不够的。用户 09-09 指出：
**RL 看到的画面必须和物理一致**，否则面板显示一个封死的孔而杆能捅穿，策略学到的是「封死不算数」。
这是仿真自洽性问题，不是评分问题。

处置与仓库已有的先例同形（gate_cage_ball 的球换向：求解器给不了零回弹之外的东西，由驱动器给）：

- `RigidAttachment` 加一个可选的 `clamp_fn`，把命令位姿映射成材料允许的位姿；默认 None，
  其余任务逐位不变（gate_cage_ball 回归通过）。
- `BarThroughHoleLayout.max_shaft_center_x(shaft_y)` 给出杆心能走到多远：
  对准通孔 → 无限；对准盲孔 → 杆的前端停在该孔盖板的近面；其余（两孔之间的实体）→ 停在板的近面。
  三种情况都按「杆自己的截面能不能过」判（`|杆 y − 孔心 y| ≤ 孔内接圆 − 杆内接圆`）。
- demo 把它包成 `stop_at_material` 传给 attachment。

**实测**：`insert` 瞄通孔，杆的远端到面板中平面之后 **+95.9 mm**（穿过去）；
`wrong_hole` 瞄盲孔，远端停在 **−3.7 mm**（中平面之前，抵住盖板，3.7 mm 是 IK 的跟随滞后）。
杆尖停在 8 mm 凹坑里抵着盖板——一根杆捅进盲孔停住的样子。

### 9.4 「封没封一眼可辨」——量出来的，不是看出来的

会上的原话是「现在远看分不清」。三个孔缘**都**描鲜黄（只描通的那个等于把答案画在漆上，
而三个孔存在的意义正是要策略从几何上读「这个能看穿」），板厚 30 → 16 mm，盲孔留 8 mm 暗坑。

孔内平均亮度实测：

| 机位 | 通孔 | 盲孔 | 差 |
|---|---|---|---|
| `front` 768×768 | 0.60 | 0.16 | **+0.44** |
| **`base_camera` 256×256（策略相机）** | **0.63** | **0.24** | **+0.38** |

通孔比盲孔亮 **2.5 倍**，而且亮的那个跟着 `open_index` 走。第一眼看 256×256 的缩略图会觉得
「三个都是暗的」——那是缩略图的错觉，像素数据是决定性的。**这一条是本项唯一可能被推翻的风险，
现在过了。**

**09-09 补测：三个机位、跨孔径的完整读数。** 上表只量了基线孔径的一格。孔径轴的下界是 24 mm，
孔越小可读的像素越少，所以按 seed 4 / 6 / 7（`open_index` 恰好是 0 / 1 / 2，孔径 34.7 / 24.3 / 37.5 mm）
在三个机位各量一次。做法：按颜色分割出三个黄色孔缘，取每个孔缘的形心与半径，
量该孔内 0.45 半径圆盘的平均亮度。

| 机位 | 通孔 | 盲孔 | 差 | 最小孔（24.3 mm）上还剩多少像素 |
|---|---|---|---|---|
| `front` 512×512 | 0.55 … 0.62 | 0.15 … 0.19 | **+0.37 … +0.47** | 88 px |
| `front` 缩到 256×256 | 0.55 … 0.62 | 0.15 … 0.19 | **+0.37 … +0.46** | 22 px |
| `oblique` 512×512 | 0.46 … 0.49 | 0.16 … 0.20 | **+0.27 … +0.33** | 23 px |
| `topdown` 512×512 | 0.54 … 0.57 | 0.46 … 0.58 | **−0.01 … +0.05** | — |

三件事：

1. **从 512 缩到 256 几乎不掉**（最差一格 +0.38 → +0.37）。策略相机的分辨率不是瓶颈，
   最小的孔在 256×256 上仍有 22 个像素、亮 0.55 对 0.19。
2. **`oblique` 也读得出**，只是对比度比 `front` 低三分之一——面板是斜着看的，
   能看穿的立体角更小。
3. **`topdown` 读不出，差在噪声里（±0.05）**。俯视机位看到的是面板的顶边，机械臂还挡在前面；
   黄环有 300–460 个像素，孔内却没有信息。**所以「给数据集加 `topdown` 机位」这条要撤销**——
   本任务的数据集相机保持 `EpisodeDatasetWriter` 的默认 `("front", "wrist")`，`front` 就是带信息的那个。
   要加第三个就加 `oblique`，不是 `topdown`。这是量出来的，不是看出来的。

### 9.5 新轴与对照

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| 防捷径离散轴 | `aperture.open_index` | Cat{0, 1, 2} | 哪个孔是通的。信息只在画面里，指令是常量句。1000 seed 实测 332 / 320 / 348 |
| 连续布局轴 | `aperture.pitch` | U[0.080, 0.110] | 三孔间距。上限由最外侧孔外缘 + 立柱定，下限由最窄中柱定 |
| 派生（记录） | `aperture.center_y` | 由 open_index 与 pitch 算 | 见 §9.1 |

对照 `wrong_hole`：无视画面永远瞄中间那个孔。判定仍按实际通的那个孔算，所以只在抽到中间孔的
实例上成功，预期 ≈ 1/3——与 cloth_fold 的 `fixed_corner`、linkbar 的 `nearest_zone` 同形。
实测三个 `open_index` 上分别判失败 / 成功 / 判失败。

指令改成 `"Push the bar through the hole that goes all the way through the panel."`

**角点数**：6 条连续轴 64 × `open_index` 3 × `pitch` 两端 2 = **384**，纯刚体可全跑。

### 9.6 离线实测

- `check_variant_rng.py` bar 段：1000 seed 首抽拒绝率 **0.000**；三个孔各当通孔 332 / 320 / 348；
  最窄面板条 43.2 mm；单边净空最小 3.00 mm、横推窗口最小 6.00 mm。
- 角点门：**384 角点 384 可行 0 拒**。
- 几何门：十一行读数全过（`profiles_match` / `panel_strip` / `center_y_recorded` 是本轮新增的三行）；`length_bounds` 的上界 0.190 → 0.204——板从 30 mm 减到 16 mm，
  近面外移 7 mm，而这条界是「杆的近端不进面板」，所以杆能长两倍于那个位移。是变松。

### 9.7 GPU 实测：seed 0–9（`runs/bar_through_hole_variation/20260909_threeholes/`）

`SKIP_OFFLINE=1 bash bash_scripts/tests/bar_through_hole_variation_sweep.sh`，四组各 10 格，
每格 19–20 s。录制走三机位（`recording.camera=[oblique,front,topdown]`）。

| 组 | 结果 |
|---|---|
| `oracle`（`insert`） | **10 / 10 success=True**，`threading=1`、`geometry_ok=True`、`release_stable=True` |
| `bypass` | **10 / 10 判失败**，`threading=0`、`failure=bar_not_threaded` |
| `wrong_hole` | **10 格里成功 2 格**，恰好是 `open_index=1` 的 seed 2 与 seed 6 |
| `visual` | 10 seed × 3 机位 = 30 段 mp4 |

`wrong_hole` 的 2 / 10 是这一节最要紧的一行：**成功的格数等于抽到中间孔的格数**，多一格就说明
瞄错孔也能判成功。十个 seed 的 `open_index` 抽到 0 / 1 / 2 各 5 / 2 / 3 次，中间孔两次，
`wrong_hole` 就成功两次，一一对上。

十个 seed 的包络读数：

| 量 | 跨度 |
|---|---|
| `hole_y`（通孔的实际 y） | **−0.1090 … +0.1049 m** |
| `af`（孔的对边距） | 0.0243 … 0.0375 m |
| `pitch`（孔心间距） | 0.0867 … 0.1091 m |
| `panel_x` | 0.1016 … 0.1536 m |
| `window`（横推窗口） | 0.0063 … 0.0195 m |
| `side_clear`（单边净空） | 0.0031 … 0.0098 m |

**「手能不能把杆横着搬 11 cm 而不掉」这条只能实测的问题，答案是能**：`hole_y` 走到 ±10.9 cm，
十格的 `align_tilt` 全是 **0.01°**、`lift_tilt` 0.02–0.03°、`drift` ≤ 0.00001 m。
`AxialInsertPrimitive` 的 `align` 相位是一次直线移动，不需要新原语——这一条现在有数了。

另一处值得记的读数：`wrong_hole` 在 seed 8 上 `release_stable=False`、`drift=0.00957`。
那正是 §9.3 想要的画面——杆被盖板挡住、停在凹坑里，松手后从抵着的位置滑了 9.6 mm。
盲孔挡住杆不是判定器写的，是物理拦的。

### 9.8 GPU 实测：384 角点（`runs/bar_through_hole_corners/20260909_threeholes/`）

`bash bash_scripts/tests/variant_corners_sweep.sh bar_through_hole oracle bypass wrong_hole`。
6 条连续轴的两端 64 × `open_index` 三档 × `pitch` 两端 = 384 个角点，三组共 1152 格全跑，
每格 18–21 s，合计 6.1 h。

| 组 | 结果 |
|---|---|
| `oracle`（`insert`） | **384 / 384 PASS** |
| `bypass` | **384 / 384 判失败**，理由一律 `bar_not_threaded`，无一漏判 |
| `wrong_hole` | **成功 128 / 384，全部落在 `open_index=1` 的角点上；反例 0** |

三行各自说明一件事：

1. **oracle 覆盖包络的顶点。** 孔径 24 / 38 mm 两端、三个 `open_index`、`pitch` 80 / 110 mm 两端、
   杆的出生位与板位的全组合，一格没掉。上一轮（09-04）只有 64 个角点、单孔，这一轮是它的六倍。
2. **`bypass` 没有靠角点的极端几何蒙混过关。** 最宽的孔（38 mm）配最厚的可通行余量也没有一格判成功。
3. **`wrong_hole` 的成功集合与 `open_index=1` 的角点集合逐格相等**——128 = 64（`across_flats=0.024`
   那半边）+ 64（`0.038` 那半边）。既没有「瞄错孔也判成功」的多余格，也没有「瞄对孔却判失败」的缺格。
   这是本轮防捷径轴最强的一条证据：判定按实际通的那个孔算，而画面是唯一能读到它的地方。

至此 bar_through_hole 的六项交付在三孔版本上全部重跑一遍并通过：yaml 的 `variation` 块、
`checks()` 的十一行、demo 与 run 配置、三道离线门、两个 sweep 脚本、以及本节与 §9.7 的 GPU 证据。

