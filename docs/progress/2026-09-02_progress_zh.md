# 2026-09-02 进度归档：`derived` kind + linkbar 收尾 + diverter 变体部署

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 0 步补 `derived`、第 1 步收尾、第 2 步 diverter。
> 详细记录：`../develop/tasks/diverter_route_ball_zh.md` §6.2、§8 步骤 5；`linkbar_rotate_to_zone_zh.md` §5.3；本文只汇总。
> 昨日 17 个文件已提交（`89eb8bb`）；本日改动未提交，见文末清单。

---

## 0. 一句话

定下「每任务首抽拒绝率 ≤ 2%，区间依赖其他轴的量抽归一化位置再由 Layout 派生」的范式，通用层加 `derived` kind；
linkbar 的初始角按此收尾（拒绝率 0.234 → 0.002）；diverter_route_ball 的变体逻辑按 linkbar 六项清单部署完毕，
离线门全过（拒绝率 0）；GPU sweep：linkbar 新规则复核 oracle 10/10 / nearest 3/10，diverter oracle 首跑 9/10 → 修接近高度后 10/10。
拨杆原语的 `max_lag` 读数改为关节相对手部实际角；diverter 角速度降到 linkbar 的 0.23°/步后旋转判据全过、`export_ready=True`。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 下一个任务 | diverter_route_ball（§6.2 第 2 步）：planner 只读 layout、Rule 接口已有、2×2 已在配置，前置最少；gate 的可解性依赖 `env.sim.dt`，留到第 3 步 |
| 包络范式 | 每条轴各自 `[lo, hi]`，联合包络是乘积盒。边界依赖其他轴的量不用独立区间 + 拒绝：抽 `[0,1]` 归一化量，`derived` 条目调任务模块函数按当时几何派生真实叶子。`validate` 只兜构造式消不掉的情形 |
| 拒绝率门 | 全任务统一 `MAX_REJECTION = 0.02`（`tests/check_variant_rng.py`），删掉 linkbar 专用的 0.30。超标的处置是加派生或收窄区间，不是提高重试 |
| linkbar 收尾 | `init_angle_deg` 改由 `init_frac` 在 ±15° 扣掉两区禁区后的并集上定位；接受 seed→变体映射改变，09-01 §8.4 十格需重跑复核 |
| diverter 包络修订 | 计划表 §3.7 的 `fork_origin_x ±0.015 / angle ±6 / lever ±0.008` 独立抽时手柄超 0.69 m 可达的比例 47%；`release_x ±0.03` 下半段球心进后挡板。改为 `fork_frac` 按可达反解、`spawn_frac` 按直道长度派生；张角保持 [24, 36] |
| 可达常量 | 底座位置与手柄距离上限写在 task yaml `reach:` 段（校验只拿得到 task cfg），注释指回 `manipulation_space_tabletop_v1.yaml` 的 `mount.pos`；0.690 = 实测 0.688 留 2 mm，GPU 若更远仍可抓则放宽 |

## 2. 做了什么

### 2.1 通用（第 0 步）

- `layout_randomization.py`：`_Derived(fn)` / yaml `derived`，采样后、校验前调用；派生函数抛 `ValueError` 同样算拒绝（无 validate 条目时直接抛）。`_resolve_validate` → `_resolve_fn`。模块文档补「归一化量 + 派生」一段。
- `check_variant_rng.py`：新 `directives` 段（两条 derived / 缺 fn 报错、派生-校验顺序、派生叶子不进 `sampled_leaves`、无 validate 时派生错误不被吞）；`MAX_REJECTION = 0.02`；`_first_draw_rejected` 同时跑 derive 与 validate。

### 2.2 linkbar 收尾（第 1 步）

- yaml：`linkbar.init_span_deg [-15, 15]`、`linkbar.init_frac 0.5`；`variation:` 的 `uniform init_angle_deg` 换成 `uniform init_frac` + `derived`。
- Layout：`init_angle_segments()`（扣禁区，去掉浮点残段）、`init_angle_from_frac()`、模块级 `derive_task_cfg`。
- 测试：`check_linkbar_zone_geometry.py` 加三段/两段/空集三例；`check_variant_rng.py` linkbar 段改写。

### 2.3 diverter（第 2 步）

- yaml：`channel.fork_x_min/-max/fork_frac`、`ball.spawn_wall_margin/spawn_fork_margin/spawn_frac`、`reach:` 段、`motion.steps_arc` → `arc_deg_per_step 0.23 + min_steps_arc 60`（先按 0.5 上线，指垫打滑后降到 linkbar 的 0.23）、末尾 `variation:` 块（3 choice + 3 uniform + 2 frac + derived + validate）。
- Layout：`fork_origin_x_bounds/-from_frac`、`release_x_bounds/-from_frac`、`knob_reach`、`half_open_bypass_gap`、`checks()` 六行、`validate()`、`steps_arc()`；`check_pivot_clearance()` 并入 `checks()`；builder 改调 `validate()`；模块级 `derive_task_cfg` / `validate_task_cfg`。
- demo：两个 demo 接 `randomize_task_cfg` + `variant` 行；physical demo `steps_arc` 由 layout 推导、`EpisodeKey.variant_id`、启动打印 `checks` 行；run 配置加 `randomize_layout / difficulty / variant_id`。
- 离线门：`check_variant_rng.py` diverter 段；新 `tests/check_diverter_geometry.py`。
- sweep：`bash_scripts/tests/diverter_variation_sweep.sh`（visual / oracle / fixed）。

## 3. 实测（离线，无 GPU）

| 门 | 结果 |
|---|---|
| `check_variant_rng.py` | 五段全 PASS。linkbar 首抽拒绝率 0.002（同侧 390 / 异侧 610 / 近邻 65 / 初始角贴禁区边 103）；diverter 拒绝率 0.000，`rotate_needed` 516/1000，手柄距底座最大 0.690，`fork_origin_x` ∈ [−0.060, −0.020] |
| `check_linkbar_zone_geometry.py`、`check_linkbar_planner.py` | PASS（oracle 6/6、nearest 3/6） |
| `check_diverter_geometry.py` | PASS：seed 0–199 checks 全过；16 个包络角点 `knob_reach` 0.625–0.690、旁通间隙 40.9–41.9 mm；判据 flood-fill 三条结论在每个角点一致；oracle 2×2 正确、`fixed_direction` 2/4；`steps_arc` 60°→120、48°→96、72°→144 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS（26 个 demo） |

### 3.1 GPU（4090，用户跑 + 单格诊断）

| 任务 | 结果 |
|---|---|
| linkbar `linkbar_variation_sweep.sh` seed 0–9（新采样规则） | visual 10/10、oracle **10/10**、`nearest_zone` 3/10（逐条核对均为近区恰为目标）；详见 `linkbar_rotate_to_zone_zh.md` §8.6 |
| diverter `diverter_variation_sweep.sh` seed 0–9 首跑 | visual 全 FAIL（`static_only` 无帧可录）、oracle 9/10（seed 0 `flap_not_seated`）、`fixed_direction` 7/10 |
| seed 0 诊断（`rotate_only` verbose） | 接近段指尖撞拨杆 −34° → −105°，抓空中止。`approach_z` 0.260 只给指垫 22 mm 净空（端盖顶 0.135，yaml 注释的 0.114 是旧几何） |
| 修后重跑 oracle / visual（`runs/diverter_variation/20260902_150649_rerun/`） | oracle **10/10**，`target_error` 1.9–2.6°；visual 10/10 有帧。详见 `diverter_route_ball_zh.md` §8 步骤 5 |

| `max_lag` 定义修正后复测（`runs/lag_fix/`） | linkbar 0.5–0.8°；diverter 默认 7.9°、变体 6.3–9.6°，0.23°/步 诊断 3.3° |
| diverter `arc_deg_per_step` 0.23 重跑 seed 0–9（`runs/lag_fix/diverter_023/`） | oracle 10/10，旋转格 `rotate success=True`，`max_lag` 2.2–4.4° |

修的三处：`motion.approach_z` / `retreat_z` 0.260 → 0.300；`checks()` 加第七行 `approach_clearance ≥ 30 mm`（linkbar 同门）；
inspect demo 加 `run.final_hold_steps` 60（run 配置新键）。

## 4. 遗留 / 观察

- **`max_lag` 读数定义已修正**（`topogym/primitives/pivot_lever.py`，linkbar / diverter 共用）：原比关节角与指令角，含手的 IK 跟踪滞后
  （11 mm 在 55 mm 手柄圆上 ≈ 11°）；改为比关节角与手部实际位置对转轴的角度（`hand_angle_about`），阈值 6° 不动，`max_follow_error`
  继续把关跟踪。复测：linkbar seed 0–2 由 2.7° 降到 0.5–0.8°；diverter 默认布局 14.7° → 7.9°，五个需旋转变体 13.8–16.4° → 6.3–9.6°。
- **diverter 降角速度**：修正读数后仍有 6–10° 真实落后，且随角速度变（诊断 0.23°/步 降到 3.3°）——指垫在 ⌀18 mm 握持段上打滑。
  用户定：`arc_deg_per_step` 0.5 → 0.23，与 linkbar 同（真机一致性）。重跑 seed 0–9 oracle **10/10**，五个旋转格 `rotate success=True`、
  `export_ready=True`，`max_lag` 2.2–4.4°、`target_error` 2.0–2.6°、`release_drift` 0（`runs/lag_fix/diverter_023/`）。
- `fixed_direction` 7/10 是这十个 seed 的死路侧恰好 7 个 right；1000 seed 离线 0.486，不是包络偏置。

- diverter 的 `release_x` 包络上限在分岔口最靠 −x 时约 −0.07（球心离交接点 36 mm），球到板的距离短，起跑加速段（0.35 s）可能还没到速；sweep 时看 `spawn_frac` 接近 1 的格。
- `diverter_route_ball_zh.md` §3.2 的板长 0.0999 / 旁通 46.2 mm 是 `wall_gap=0.004` 时代的值（现 0.0839 / 41.5 mm）；§6.1「两条指令字符串」已过时（指令恒定）。未改。
- `TopoGym_变体参数轴表.xlsx` 的 linkbar 初始角行与 diverter 全部行需手动同步。

## 5. 下一步

§6.2 第 3 步 gate_cage_ball：`release_y`（相对 `entry_start_y`）与 `flat_end_y` 同样用归一化量派生；`checks()` 三行。
前置决定：`t_ready` / `insert_duration` 依赖 `env.sim.dt`，校验要么把 dt 写进 task yaml，要么 `checks(dt)`。
另注意 §3.6 的 `release_y ∈ [−0.46, −0.34]` 下界越过地板起点 `entry_start_y = −0.42`。

## 6. 文件清单

```
topogym/primitives/pivot_lever.py                                       max_lag 改为关节相对手部实际角；hand_angle_about
topogym/generation/layout_randomization.py                              derived kind、_resolve_fn、派生错误算拒绝
topogym/tasks/connectivity/linkbar_rotate_to_zone.py                    init_angle_segments / init_angle_from_frac / derive_task_cfg
topogym/tasks/connectivity/diverter_route_ball.py                       bounds / derive / checks（七行）/ validate / steps_arc；check_pivot_clearance 并入
configs/task_configs/linkbar_rotate_to_zone_topogym_tabletop_v1.yaml    init_span_deg / init_frac / variation 块；max_lag_deg 注释
configs/task_configs/diverter_route_ball_topogym_tabletop_v1.yaml       派生叶子、reach 段、arc_deg_per_step、approach_z 0.300、variation 块
configs/run_configs/diverter_route_ball.yaml, _route.yaml               randomize_layout / difficulty / variant_id；inspect 加 final_hold_steps
demos/connectivity/diverter_route_ball_{physical_route,inspect}_demo.py  接线、variant 行、steps_arc、checks 行
tests/check_variant_rng.py                                              directives 段、MAX_REJECTION、linkbar 段改写、diverter 段
tests/check_linkbar_zone_geometry.py                                    init 段三例
tests/check_diverter_geometry.py                                        新（steps_arc 期望按 0.23°/步）
bash_scripts/tests/diverter_variation_sweep.sh                          新
docs/develop/tasks/diverter_route_ball_zh.md                            §6.2、§8 步骤 5（含 GPU 结果表）
docs/develop/tasks/linkbar_rotate_to_zone_zh.md                         §5.3、§8.4 注、§8.6、§8.7
docs/develop/tasks/variation_and_difficulty_plan_zh.md                  §2.3 / §2.4 / §2.5 / §3.7 / §3.8 / §5
docs/develop/tasks/variation_axes_plain_zh.md                           §4 两行、§6.1、§6.2
docs/progress/2026-09-02_progress_zh.md                                 本文
```
