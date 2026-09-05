# bar_through_hole（docx 2.3）：变体生成与可解性

> 日期：2026-09-04。本任务此前没有任务文档；场景、原语、判据的取值与理由在
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
**决定**：包络下界 0.029，`push_clearance_min` 0.0024（窗口 ≥ 4.8 mm）。要再往下推，可改的是 far 托座 `jaw_width`
（0.016 → 0.010 使窗口 +4.2 mm），那是几何决定，留到实测之后。

## 3. 变体轴与派生

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| B | `aperture.across_flats` | U[0.029, 0.038] | 单调裕度轴。横向单边净空 = (af − 0.018)/2 = 5.5 .. 10 mm |
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
