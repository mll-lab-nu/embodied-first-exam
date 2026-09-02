# gate_cage_ball（docx 4.1）：变体生成与可解性

> 日期：2026-09-03。本任务此前没有任务文档；场景、原语、判据的取值与理由都在
> `configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml` 与 `topogym/tasks/connectivity/gate_cage_ball.py` 的注释里，
> 本文只记变体部署这一步（`variation_axes_plain_zh.md` §6.2 第 3 步）。

---

## 1. 任务回顾（术语按仓库）

球从入口段（`channel.entry_start_y` 到 `channel.door_y`）匀速滚进封闭区（`door_y` 到 `channel.flat_end_y`），撞远端墙后原速滚回。
机器人从停放架（`gate_rack`）取闸板，搬到门口导柱槽（`gate_slot`）上方悬停，等球进门后把闸板插下，把球关在封闭区里。
球一开始就是自由的，机械臂在和它赛跑。

| 量 | 来源 | 现值 |
|---|---|---|
| `entry_delay` = (`door_y` − `release_y`) / `speed` | `GateCageBallLayout.entry_delay()` | 3.33 s |
| 窗口 `window` = 2·(`flat_end_y` − 球半径 − `door_y`) / `speed` | `predicted_window()` | 2.00 s |
| `t_ready`：臂拿着闸板在门口悬停就位 | `motion.*` 步数 × `timing.sim_dt`（= `GatedInsertPrimitive.time_to_station`） | 2.40 s |
| `insert_duration`：从下板到落座 | 同上（= `insert_duration`） | 1.30 s |

触发规则（`topogym/planning/gate_cage_ball_planner.py`，`run.trigger`）：

| 规则 | 行为 | 预期 |
|---|---|---|
| `oracle` | 球在门内且「回到门口的时间 − `insert_duration`」≥ `timing.safety_margin` 才下板 | 成功 |
| `greedy` | 到位就插，不看球 | 臂先到（`hover_wait` > 0）失败，球先到可能侥幸 |
| `fixed_delay` | 开始后 `run.fixed_delay_s` 秒就插，不看球（2026-09-03 新增） | 起点与球速逐 seed 变后落到中间；「不感知」策略的上限 |

## 2. 可解性判据与 `timing:` 段

- 判据 A：`window` ≥ `insert_duration` + `safety_margin`（球进来后封得住）。
- 判据 B：`entry_delay` + `window` − `insert_duration` ≥ `t_ready` + `ready_margin`（臂就位时最晚下板时刻还没过）。

两条判据把球的时间量和机械臂的时间量放在一起比。机械臂的时间量是步数乘步长，步长本来只在 env 配置（`env.sim.dt`），
触发规则的富余本来只在 run 配置；而 yaml `variation:` 块引用的 `validate_task_cfg(task_cfg)` / `derive_task_cfg(task_cfg)`
只拿得到 `cfg.task`。所以 task yaml 加了 `timing:` 段：`sim_dt` 0.01、`safety_margin` 0.15（从 run 配置搬来）、`ready_margin` 0.10（新）。
demo 建场景时断言 `timing.sim_dt == env.sim.dt`，并断言 Layout 的 `t_ready()` / `insert_duration()` 与原语的同名公式相等。

`entry_delay − t_ready`（`hover_wait`）的正负只报告不约束：它是三条触发规则拉开差距的机制，按它调几何等于把基线分数写进场景定义
（`configs/run_configs/gate_cage_ball_gate.yaml` 尾注）。

## 3. 变体轴与派生

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| B | `ball.speed` | U[0.08, 0.16] | 同时缩放 `entry_delay` 与窗口 |
| B | `channel.center_x` | U[0.055, 0.095] | 轨道左右平移 |
| B | `gate_rack.center_y` | U[−0.03, 0.03] | 停放架沿轨道方向平移 |
| B→C | `channel.flat_end_frac` → `channel.flat_end_y` | **派生** | `[max(flat_end_y_min 0.11, 判据 A 取等), flat_end_y_max 0.20]`；球速越快下界越长 |
| B→C | `ball.release_frac` → `ball.release_y` | **派生** | `[entry_start_y + 0.02, min(door_y − r − 0.02, 判据 B 取等)]`；先派生封闭区再派生它 |
| B→C | `gate_rack.x_frac` → `gate_rack.center_x` | **派生** | `[x_min −0.120, 导柱外侧面 − channel_gap 0.010 − 半底座长]`；随 `center_x` 变 |
| D | `motion.*_z`、`gate_slot.*`、`gate.*`、`ball.radius`、`inner_width`、`timing.*` | 固定 | `motion.*_z` 是手写绝对高度（§2.5 约定 1 的已知欠账） |

没有防捷径离散轴：时机本身就是隐藏信息。计划文档 §3.6 原表 `release_y ∈ [−0.46, −0.34]` 下界越过轨底起点 −0.42，由派生区间取代。

`checks()` 五行（统一签名；`validate()` 任一行不 ok 即拒绝；建场景、随机化、离线门、demo 启动共用）：

| 行 | 读数 | 门 | 默认 |
|---|---|---|---|
| `window_margin` | 判据 A 余量 | ≥ 0 | +0.55 s |
| `ready_margin` | 判据 B 余量 | ≥ 0 | +1.53 s |
| `ball_spawn` | `release_y` | 在派生区间内 | −0.400 |
| `rack_channel_gap` | 架子近缘到导柱外侧面 | ≥ 0.010 | 0.0465 |
| `hover_reach` | 门口悬停点距底座 | ≤ 0.700 | 0.645 |

## 4. 离线实测（2026-09-03）

- `tests/check_variant_rng.py` gate 段：1000 seed 首抽拒绝率 **0.000**；球先到 462 / 臂先到 538；派生叶子全部在各自区间内。
- `tests/check_gate_cage_ball_geometry.py`：seed 0–199 checks 全过；16 个包络角点（球速 × 三个 frac 0/1）`slack` 0.00–5.45 s、
  `hover_wait` −1.77–+2.60 s；`t_ready` / `insert_duration` 与原语公式一致；三条规则在四个合成球状态上的判定符合定义。
- 1000 seed 分布：`flat_end_y` 0.110–0.200、`release_y` −0.400–−0.057、`rack_x` −0.120–−0.038、`window` 1.45–4.05 s、`hover_reach` ≤ 0.665。

## 5. GPU 实测（4090，`bash bash_scripts/tests/gate_cage_ball_variation_sweep.sh`，seed 0–9）

### 5.1 首跑暴露的判据问题（`runs/gate_cage_ball_variation/` 首个目录）

visual 10/10 有帧且逐 seed 可分；oracle **6/10**，四格失败标签 `ball_pinched_in_doorway`（seed 5/6/7/8），
greedy 与 fixed_delay 各有几格同一标签。逐条看：四格 `caged=True`、`gate_blocking=True`、`gate_bottom_z` 0.009（闸板整个坐到轨底），
球在轨底上（z 0.039）、在门内 47 mm 处自由往复——任务实际成功。
`GateCageBallEvaluator` 的 `pinched` 原来只问「球心是否落在导柱条带 ± 球半径之内」（门口 ±51 mm）；封闭区短、窗口 1.7–2.2 s 的实例里，
判定时刻球恰好在门口附近往返，就被标成夹住。这是判据的定义错误，不是行为错误；默认实例没暴露只是窗口相位凑巧。
改为：`pinched` = 闸板挡着 **且** 闸板被顶住没坐到位（`gate_bottom_z` > `gate.seated_bottom_z` + 5 mm）**且** 球体在板的 y 跨度内。
只有「板压在球上」才算夹住。

### 5.2 判据修正后重跑（oracle / greedy / fixed_delay，`runs/gate_cage_ball_variation/*_judgefix/`）

| seed | 球速 | flat_end_y | release_y | center_x | rack x / y | entry_delay | window | hover_wait | slack | oracle 悬停 | oracle | greedy | fixed_delay |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.083 | 0.142 | −0.393 | 0.070 | −0.084 / +0.017 | 4.73 | 2.70 | +2.33 | 3.63 | 2.34 s | PASS | ball_outside | ball_outside |
| 1 | 0.110 | 0.144 | −0.208 | 0.087 | −0.093 / −0.012 | 1.89 | 2.07 | −0.51 | 0.16 | 0.00 s | PASS | success | ball_outside |
| 2 | 0.134 | 0.168 | −0.389 | 0.065 | −0.104 / −0.024 | 2.90 | 2.06 | +0.50 | 1.17 | 0.51 s | PASS | success | success |
| 3 | 0.137 | 0.148 | −0.397 | 0.077 | −0.098 / +0.017 | 2.90 | 1.73 | +0.50 | 0.83 | 0.51 s | PASS | success | success |
| 4 | 0.144 | 0.155 | −0.382 | 0.094 | −0.041 / +0.012 | 2.66 | 1.73 | +0.26 | 0.60 | 0.27 s | PASS | success | success |
| 5 | 0.150 | 0.155 | −0.382 | 0.069 | −0.072 / −0.001 | 2.54 | 1.66 | +0.14 | 0.41 | 0.15 s | PASS | success | ball_outside |
| 6 | 0.092 | 0.113 | −0.226 | 0.068 | −0.110 / −0.006 | 2.45 | 1.80 | +0.05 | 0.45 | 0.05 s | PASS | success | success |
| 7 | 0.142 | 0.189 | −0.347 | 0.056 | −0.074 / +0.015 | 2.44 | 2.23 | +0.04 | 0.87 | 0.04 s | PASS | success | success |
| 8 | 0.109 | 0.133 | −0.213 | 0.058 | −0.107 / −0.006 | 1.96 | 1.89 | −0.44 | 0.06 | 0.00 s | PASS | success | success |
| 9 | 0.091 | 0.192 | −0.307 | 0.076 | −0.096 / −0.010 | 3.36 | 3.55 | +0.96 | 3.11 | 0.97 s | PASS | ball_outside | success |

结论：

- oracle **10/10**；悬停时长 0–2.34 s 与 `hover_wait` 一致（臂先到的格等球，球先到的格立即下板）。slack 最小的 seed 8（0.06 s）也过。
- greedy 8/10：只在 `hover_wait` ≥ 0.96 s 的两格失败（球被关在外面）。`hover_wait` 0.14–0.50 s 的格也成功，机制正是 run 配置尾注预言的
  「球从下降中的闸板底下钻进去」：下板 1.0 s，板底降到球顶高度要 0.57 s，比 0.5 s 的提前量长。这个成绩不回调包络（不按基线分数反推）；
  要让 greedy 更接近随机，合理的做法是缩短下板时间（`motion.insert_steps`），那是原语参数，另议。
- fixed_delay 6/10：3.6 s 这个常数在 `entry_delay` 早于 3.6 s 且窗口还没关的格成功，太早（seed 0 球 4.73 s 才到）或太晚（seed 1/5/8 窗口已关）失败。
  起点与球速逐 seed 变后，「记住一个时间线」的策略确实落到中间。
- 十格首帧可分（5.1 的 visual 组）。

## 6. 文件集

```
configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml   timing / reach 段、派生叶子、variation 块
configs/run_configs/gate_cage_ball.yaml, _gate.yaml            randomize_layout / difficulty / variant_id；final_hold_steps；fixed_delay_s；safety_margin 搬走
topogym/tasks/connectivity/gate_cage_ball.py                    t_ready / insert_duration / 三个 bounds+from_frac / checks / validate / derive_task_cfg / validate_task_cfg
topogym/planning/gate_cage_ball_planner.py                      FixedDelayRule、make_trigger_rule；decide 多一个 elapsed_s
demos/connectivity/gate_cage_ball_{physical_gate,inspect}_demo.py  接线、variant 行、checks 行、dt 与时序断言
tests/check_variant_rng.py                                      gate 段
tests/check_gate_cage_ball_geometry.py                          新
bash_scripts/tests/gate_cage_ball_variation_sweep.sh            新
```
