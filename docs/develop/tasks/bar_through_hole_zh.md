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
