# 2026-09-04 进度归档：bar_through_hole 变体部署（第 12 步）+ 夹空门回填 + 周追踪表建立

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 12 步全流程（离线 + GPU + 收尾）。
> 详细记录：`../develop/tasks/bar_through_hole_zh.md`（新建，§1–§6）；本文只汇总。周目标与排期见 `weekly_tracker_zh.md`（本日新建）。
> 离线五项与 GPU sweep 脚本已于 12:59 提交（00053e0）；收尾（yaml 阈值、文档四处、本文）未提交，见文末清单。

---

## 0. 一句话

第 12 步 bar_through_hole 六项交付齐全。四个手写搬运高度改为 Layout 推导，新定义横推高度窗口 `push_window`，包络下界据此从计划表的 0.027 提到 0.029；
1000 seed 拒绝率 0.000，64 角点离线全可行。GPU：seed 0–9 oracle **10/10**、bypass 10/10 判失败；64 角点 oracle **64/64**、bypass 64/64 判失败。
角点首跑晒出托座 y 硬写 0，修 `Layout.cradle_y`。`physical.min_finger_qpos` 由 148 格实测回填 0.0086。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 搬运高度 | `primitive.grasp_z / lift_z / insert_z / seat_z` 手写绝对值改为 `BarThroughHoleLayout` 推导，yaml 只留 `lift_height` / `seat_drop` / `push_clearance_min` / `hand_half_depth` |
| 横推窗口 | 新量 `push_window` = 杆心横推段允许的 z 区间，宽度 = `across_flats` − 0.02412；取窗口中点。包络下界 0.029（窗口 4.88 mm），`push_clearance_min` 0.0024 |
| 派生 | `length_frac` → `bar.length`、`grasp_frac` → `grasp_offset`、三个托座 x、far 托座轴高，都由归一化量构造式满足，不靠拒绝 |
| 托座 y | 近端两个跟随 `bar.rest_y`，far 留在面板中线（`Layout.cradle_y`）。角点首跑暴露，见 §4 |
| 夹空门 | `min_finger_qpos` 0.0086：148 格夹到杆 0.0090–0.0094（只随 `rest_y` 变），指令位 0.008，门取中间。不是按分布反推 metric，metric 早定为指行程 |
| 不做 | 不补跑「故意夹空」对照（要把托座 y 写回 0，是复现已修的 bug）；`grasp_qpos` 不动 |

## 2. 做了什么

- Layout：四个手高推导、`push_window`、`cradle_x` / `cradle_y`、`length_bounds/from_frac`、`grasp_bounds/from_frac`、`checks()` 九行、`validate()`、模块级 `derive_task_cfg` / `validate_task_cfg`。
- yaml：`primitive` 段改推导所需量；`bar.rest_pos` 拆三个标量叶子；末尾 `variation:` 块（6 条连续轴，2 条派生）；`min_finger_qpos` 0.0086（本日收尾）。
- run 配置：`randomize_layout` / `difficulty` / `variant_id` 三键。
- demo：`randomize_task_cfg` 接线、variant 行、checks 行。
- 离线门：`tests/check_bar_through_hole_geometry.py`（新）；`check_variant_rng.py` bar 段；`check_variant_corners.py` 登记。
- sweep：`bash_scripts/tests/bar_through_hole_variation_sweep.sh`（新）；`variant_corners_sweep.sh` bar 分支（对照组 bypass）。
- 文档：`bar_through_hole_zh.md` 新建 §1–§6；`rigid_first_track_zh.md` §2 进度行与 §7 第 5 条收尾；`weekly_tracker_zh.md` 新建。

## 3. 实测

| 门 | 结果 |
|---|---|
| `check_bar_through_hole_geometry.py` | PASS：推导高度还原手写值（insert 0.192 对原 0.193）；窗口三点 4.88 / 7.88 / 13.88 mm；最坏角点区间；`cradle_y`；九行 |
| `check_variant_rng.py` bar 段 | 1000 seed 首抽拒绝率 **0.000** |
| `check_variant_corners.py --task bar_through_hole` | 首跑 32 个 `across_flats=0.029` 角点被 `push_window` 行拒（4.88 < 5.0，手算偏置 0.0241 实为 0.02412）；`push_clearance_min` 0.0025 → 0.0024 后 **64/64** |
| 固定布局 GPU 复跑 | `success=True threading=1 phases=16/16`，与 08 月基线相同 |
| seed 0–9 三组（`runs/bar_through_hole_variation/20260904_seeds/`） | visual 10/10；oracle **10/10**；bypass 10/10 `bar_not_threaded`；`align_tilt` 全 0.01° |
| 64 角点两组（`runs/bar_through_hole_corners/20260904/`，一格 25 s） | oracle **64/64**；bypass 64/64 判失败；`finger_qpos` 只随 `rest_y` 变（−0.03 → 0.0090，+0.03 → 0.0094） |
| 夹空门回填后复核 | seed 0 oracle `success=True finger_qpos=0.0092`；角点 c000 oracle `success=True finger_qpos=0.0090`（离门最近的格）；resolved config 里 `min_finger_qpos: 0.0086` 生效（目录 `*_fingergate/`） |
| 回填后离线门 | `check_bar_through_hole_geometry.py`、`check_variant_corners.py` 复跑 PASS（阈值不进 `checks()`，只确认 yaml 没误改） |

## 4. 遗留 / 观察

- **托座 y 硬写 0**（已修）：第一个 `rest_y ≠ 0` 的角点 c000 里杆生成在槽旁边、掉到桌上、手指合了个空。随机 sweep 里 `rest_y` 最远 0.025，托座斜面兜得住；角点推到 0.030 才掉出去。
  修 `Layout.cradle_y`、几何测试加断言，c000 复跑过。修前日志已被复跑覆盖，只记机制。本任务的隐含假设与 diverter `max_lag`、gate `pinched`、c_ring `passed_through` 同列：修的是执行链，包络不动。
- bar 自己没有留下夹空读数；夹空侧按指令位 0.008 取（无阻挡时位置控制合到指令位）。gate 的空夹读数 0.0018 / −0.0010（指令位 0.005）说明被撞过的手指读数只会更低。会话里一度把 gate 日志中 0.0081 的**夹板**读数误当成空夹旁证，已改正。
- `push_z` 恒 0.0891：孔心与托座顶本轮都不随轴动。以后若让 `aperture.center_z` 进包络，窗口中点会随之变，`push_window` 行已经在 `checks()` 里。
- `TopoGym_变体参数轴表.xlsx` 的 bar 行需手动同步（下界 0.027 → 0.029）。

## 5. 当前进度与下一步

| 步 | 任务 | 离线六项 | GPU | 备注 |
|---|---|---|---|---|
| 1 | linkbar_rotate_to_zone | 完成 | oracle 10/10，角点 20/20 | `init_frac` 改法后十格待复核 |
| 2 | diverter_route_ball | 完成 | oracle 10/10，角点 256/256 | |
| 3 | gate_cage_ball | 完成 | oracle 10/10，greedy 8/10，fixed_delay 6/10，角点 64/64 | 09-03 |
| 4 | band_untwist | 完成 | oracle 10/10，wrong_end 3/3，角点子集 | 09-03 / 09-04 c130 处置 |
| 8 | unlink_c_ring | 完成 | oracle 10/10，no_align 10/10，角点 32/32 | 09-03 |
| 12 | bar_through_hole | 完成 | oracle 10/10，bypass 10/10 判失败，角点 64/64，bypass 角点 64/64 判失败 | 本日 |
| 5–7、9–11 | 其余七个（全形变体） | 未开始 | — | 按 `weekly_tracker_zh.md` §4 排期：09-05 rope_unwinding、09-06 rope_winding、09-07 swap_crossing_sign、09-08 ring_transfer、09-09 cloth_unpleat / unroll、09-10 cloth_fold |

**下一步**：按 `weekly_tracker_zh.md` §4。09-05 第 7 步 rope_unwinding；刚体五任务（linkbar / diverter / gate / c_ring / bar）50 seed 稳定性 sweep 夜间跑；
目标 3 的 RL 算法与首个训练任务等 §5 决策点拍板（建议 PPO / rsl-rl + linkbar）。

## 6. 文件清单

```
已提交（00053e0，12:59）：
topogym/tasks/routing/bar_through_hole.py
configs/task_configs/bar_through_hole_topogym_tabletop_v1.yaml, configs/run_configs/bar_through_hole.yaml
demos/routing/bar_through_hole_physical_insert_demo.py
tests/check_bar_through_hole_geometry.py（新）, tests/check_variant_corners.py, tests/check_variant_rng.py
bash_scripts/tests/bar_through_hole_variation_sweep.sh（新）, bash_scripts/tests/variant_corners_sweep.sh
docs/develop/tasks/bar_through_hole_zh.md §1–§4（新）

未提交（本日收尾）：
configs/task_configs/bar_through_hole_topogym_tabletop_v1.yaml（min_finger_qpos 0.0086 + 注释）
docs/develop/tasks/bar_through_hole_zh.md §5–§6
docs/develop/tasks/rigid_first_track_zh.md（§2 进度行、§7 第 5 条）
docs/progress/weekly_tracker_zh.md（新）
docs/progress/2026-09-04_progress_zh.md（本文）
runs/bar_through_hole_variation/20260904_fingergate/, runs/bar_through_hole_corners/20260904_fingergate/（复核日志）
```

---

## 7. 晚间追加：rope_unwinding 变体部署（第 7 步，提前自 09-05）

详细记录 `../develop/physics/rope_winding/rope_unwinding_zh.md` §7；本节只汇总。

**一句话。** 六项交付齐全（GPU 至 09-05 凌晨）：seed 0–9 oracle 10/10、visual 10/10、wrong_way 3/3 判失败、角点子集 12/12。三次首跑失败各修一处：圈距下界（网格硬边界，唯一的包络改动）、对照组覆盖不进布局校验、贴柱守卫改全绳比例门。

| 决定 | 内容 |
|---|---|
| 两个手写出生点 | 改为 `routes.initial` 的规则条目 `lead_in_toward`（S 沿柱心方向 40 mm）与 `tail_arc`（沿最上一圈切线离开、向远离柱子一侧弯 130°、弦长 0.216）；yaml 里只剩 S 一个坐标。基准插头出生点由此从手写的 (−0.006, −0.218) 变为 (−0.034, −0.214)（手写点离切线 5°），固定布局 GPU 复跑通过 |
| `direction=cw` | 定义为镜像布局：yaml 位置按 ccw 写，`RopeUnwindingLayout.fixture_pos` 在 cw 时取反三个 fixture 的 y。先试「只翻缠绕」：插头出生到东北角，首抽拒绝率 21%（可达、工作区），弃用 |
| 派生 | `wind_z_frac → wind_z_start`（区间上限随圈数与圈距）；`C.x_frac → C.x`（`x_range` 挖掉插头 0.040 净空盘后按长度映射；独立抽时 3.3% 拒绝，且插头可能在柱东侧，所以挖整个盘而不是只抬下端） |
| 不反解 sweep | 位置抖动时 \|S−柱\| 同时进供给与需求，松弛 6.8–10.6% 稳在带内；`sweep_deg` 改为幅值 130，弯向由 Layout 定 |
| 可达门 | 新键 `reach.max_hand_dist` 0.780（假设；基准 0.727、柱 x 0.060 时 0.772）；角点子集先跑这两格 |
| 圈距下界 | GPU 首跑 seed 6（3 圈 × 0.0102）建场景时 tetgen 报管皮自交；离线 tetgen 扫圈数 × 圈距 × 首圈高度，≥ 0.012 全过。网格生成的硬边界，`climb_per_turn` 下界 0.010 → 0.012、`wrap_gap` 门 0.004；seed 映射变了，GPU 三组全部重跑 |
| fixture 位置 | `pos` 列表拆成 `x / y / z`（本任务三个 fixture），`CableRoutingLayout.fixture_pos` 加回退，rope_winding 不动 |
| 对照组 | `winding.orbit_direction=same`（planner 新关键字），sweep 脚本不需要知道 seed 抽到的方向 |

| 门 | 结果 |
|---|---|
| `check_rope_unwinding_geometry.py`（1/2/3 圈） | PASS；新段：还原、镜像、1536 角点全可行、两个负例 |
| `check_variant_rng.py` rope_unwinding 段 | 1000 seed 首抽拒绝率 **0.000** |
| `check_variant_corners.py --task rope_unwinding` | **1536/1536**，Hydra compose 一致 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| 固定布局 GPU 复跑 | `task_success=True` 13/13，放置 1.2 mm，终态 `contact_nodes=0` |
| 首跑 seed 0–7（climb 下界 0.010） | oracle 7/7 PASS（cw 4 格、2 圈 2 格），seed 6 建场景 tetgen 自交 → 收圈距下界，`…/20260904_seeds_firstrun/` |
| seed 0–9（新包络） | oracle **10/10**（cw 5 格、2 圈 3 格、3 圈 1 格），放置 0.5–2.1 mm，闭合计数全 0；visual 10/10 |
| wrong_way 首跑 | 三格在随机化里被拒 21 次：对照组的 `orbit_direction=same` 进了 `checks()` 的规划行，closure 路线凑不到 0 抛错。修执行链：`checks()` 用 oracle 轨道评估、planner 强制轨道下退回直线；重跑排在角点之后 |
| 角点 c1120（3 圈、锚点最贴柱） | 第一圈末 `contact_nodes=5001 > 4800` 中止；离线四面体节点数与通过的 c1024 只差 3%，三圈出生贴柱本就 ≈ 5000。修判据：门 = max(4800, 1.5 × 出生贴柱数)（`safety_contact_growth`），c1120 重跑排在 wrong_way 之后 |
| 角点 12 格 | 首跑 10/12：两个失败都是锚点最贴柱（|S−柱| 0.100）的镜像对，被贴柱守卫中止；诊断跑（守卫 3 倍、probe）两格都成功（闭合计数 3 → 0、放置 < 1 mm、贴柱数峰值 1.65 倍出生值 —— 解下的绳绕在柱脚）；守卫改为 max(4800, 0.85 × 全绳节点) 后重跑 PASS → **12/12** |
| wrong_way 0–2（修后） | 3/3 判失败：1 圈格读 −2、2 圈格第一圈末 −3 后被守卫中止 |

未提交文件见 `rope_unwinding_zh.md` §7.5 的清单。

---

## 8. 晚间追加：ring_transfer 变体部署（第 10 步，提前自 09-08）

详细记录 `../develop/tasks/ring_transfer_zh.md` §7；本节只汇总。

**一句话。** 六项交付里离线五项完成并全部通过；GPU 被 rope_unwinding 链占着，只起了固定布局 carry 复跑一格，seed / 对照 / 角点子集按排期 09-08 跑。

| 决定 | 内容 |
|---|---|
| 三个搬运高度 | `lift_low_z / hang_bottom_z / drop_z` 从 yaml 删除，改为 Layout 按挡头顶、底座高、掌底高推导（常量 0.012 / 0.024 / 0.009，基准值逐个还原）；柱高轴由此可动 |
| 柱对 | `posts:` 列表改 dict + 共用 `post_shape:`；新增 `pair:`（中点、柱距、朝向），两柱位置由 `derived` 写出——不加新的 `pair` kind |
| 中点 | `mid_x_frac / mid_y_frac` 派生：窗口 = 范围 ∩ 工作区 ∩ 可达圆（0.780）；直接抽 ±0.030 在柱距 0.28 时必拒（推过 B 的手位出工作区），可达是最先碰到的边界（基准已 0.770） |
| 指令轴 | `ring.on_post` choice [A, B]，`goal.on_post` / instruction 派生；enclosure 列表改标量，多柱预留放弃 |
| 长轴 / 捏取 | 长轴 = (sin θ, −cos θ)；捏取侧 = 远离目标柱的直段；pinch_along = min(直段长, 挡头半径 + 掌半厚 + 0.014) |
| 对照组 | `lift_only`（只提离不套柱），`drape_outside` 依赖不可用的 transfer 几何 |
| 先探针再接线 | scratch 里用现有几何模块算 256 个规划角点，确认区间与常量（rope_unwinding 的做法）；接好后门读数一致 |

| 门 | 结果 |
|---|---|
| `check_ring_transfer_geometry.py` | PASS：十五行 + 还原 / 旋转 / on_post B / 256 角点 / 三负例 |
| `check_variant_rng.py` ring_transfer 段 | 1000 seed 首抽拒绝率 **0.000**，最窄 mid_x 窗口 11.1 mm |
| `check_variant_corners.py --task ring_transfer` | **256/256**，Hydra compose 一致 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| demo build_only seed 3（GPU） | variant / checks 两行正常，场景建成 |
| 固定布局 GPU carry 复跑 | **success=True** 1292 步，终态 {A:0, B:1}、两顶越过、间隙 2.0 mm（`…/20260904_baseline/fixed_carry_retry.log`）；第一次尝试在首步被 libuipc `cudaErrorInvalidDevice` 终止，GPU 当时三租户、无臂 spike 同时能跑、原样重跑通过 → 记为争用 |
