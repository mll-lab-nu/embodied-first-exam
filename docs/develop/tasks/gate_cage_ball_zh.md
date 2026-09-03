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

`checks()` 六行（统一签名；`validate()` 任一行不 ok 即拒绝；建场景、随机化、离线门、demo 启动共用）：

| 行 | 读数 | 门 | 默认 |
|---|---|---|---|
| `window_margin` | 判据 A 余量 | ≥ 0 | +0.55 s |
| `ready_margin` | 判据 B 余量 | ≥ 0 | +1.53 s |
| `ball_spawn` | `release_y` | 在派生区间内 | −0.400 |
| `rack_channel_gap` | 架子近缘到导柱外侧面 | ≥ 0.010 | 0.0465 |
| `hover_reach` | 门口悬停点距底座 | ≤ 0.700 | 0.645 |
| `approach_clearance` | `approach_z − HAND_TO_PAD_Z − 停放架上板顶 0.105`（指垫到板顶） | ≥ 0.030（linkbar / diverter 同门） | 0.032 |

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

### 5.3 角点 sweep 暴露的取板原语缺陷（2026-09-03，`runs/gate_cage_ball_corners/`）

`tests/check_variant_corners.py` 把包络 6 条轴的端点全组合成 64 个角点，`variant_corners_sweep.sh` 逐格送进物理（固定布局路径，不碰随机化）。
09-02 晚首跑 oracle **54/64**：10 个失败格全在停放架 `center_y=−0.03` 且 `x_frac=0`（架在 x_min −0.120）那一角，8 格 `grasp_check_failed`
（`plate_yaw` 2.19° > 2.0°，`finger_qpos` −0.0010）、2 格时序（c002 `pinched`、c034 `ball_outside`，`slack` 0.10 s）。

**根因（逐步追踪 + 对照实验）。** approach 是从 home（指开合轴沿 x）30 步移到停放架上方 `approach_z`，同时姿态要转到 `default_ee_quat`
（指开合轴沿 y），腕转 90°。`GatedInsertPrimitive._move` 收了 `start_quat` 却没用，每一步给 IK 的姿态目标都是终态；派生源
`AxialInsertPrimitive._move_linear` 和 `PivotLeverPrimitive._move` 都用 `_quat_slerp` 把姿态沿同一条余弦曲线插值，08-17 派生时没抄。
IK 面对 90° 的姿态误差给出的中间解让手下沉、倾斜。同一段移动（home → 停放架上方）的对照：

| 做法 | 下沉 | 倾角 | 水平落后 |
|---|---|---|---|
| 只平移，腕不转 | 1.5 mm | 1.7° | 61 mm |
| 平移 + 每步姿态目标为终态（原写法） | 63 mm | 17° | 56 mm |
| 只原地转腕，不平移 | 70 mm | 18° | 40 mm |
| 原写法放慢 4 倍（120 步） | 70 mm | 18° | 39 mm |
| 平移 + 姿态插值（修后） | 1.5 mm | 1.6° | 60 mm |

放慢不消下沉，说明是解序列本身而非动态滞后；水平落后 40 mm 是 165 mm 平移压在 0.3 s 里的独立现象，settle 30 步归零，
不是撞板原因（且加 settle 会把 `t_ready` 2.40 → 2.70 s、改变 `release_y` 派生上界，本次不加）。
`approach_z` 0.240 给指尖的静态净空只有 12 mm（指垫 32 mm），下沉 60 mm 后指尖从板顶边缘扫过：第 12 步起两根耦合的手指被顶着合拢到
−0.001，板被推向 −x 14 mm、偏摆 2.1°；随后合爪、attachment 把已偏的板挂上手。腕单向转，转到一半两指都甩到手的 −y 侧，板在 −y 侧
（`center_y=−0.03`）时正好套住一根手指；在 +y 侧时从板面旁边过，不碰。架越靠 x_min 路径越长，最低点越深入板端。
可达性无关：底座到架 0.451 m，`lift_test` 时手到位 ±4 mm。

被碰的其实是 16 格：另 8 格板被推 69 mm、偏摆只 1.76°，判「过」，全程手指空夹（`finger_qpos` 0.0018）、靠 attachment 拎着插进槽——
`min_finger_qpos` 为 null 漏掉的假成功。

**处置（oracle 侧，包络不动）：** ① `_move` 补 `_quat_slerp`（对齐派生源）；② `min_finger_qpos` null → 0.004（夹到板 0.0063–0.0075，
空夹 ≤ 0.0018）；③ `checks()` 加 `approach_clearance ≥ 0.030`（不随任何轴变，现值 0.032，防以后改低 `approach_z`）；
④ `check_gate_cage_ball_geometry.py` 加 `approach_z=0.220` 必须被 `validate()` 拒绝。不把「板不能在扫掠体积里」写进包络：那是固化 bug 的形状。

**修后重跑（`runs/gate_cage_ball_corners/20260903_145828_slerpfix/`、`runs/gate_cage_ball_variation/20260903_145828_slerpfix/`）：**

| 组 | 修前 | 修后 |
|---|---|---|
| 角点 oracle（64 格） | 54/64 | **64/64** |
| 角点取板读数 `finger_qpos` / `plate_yaw` | 停放架在 −0.03 一角：0.0018 ~ −0.0010 / 1.76 ~ 2.19° | 全部 64 格 0.0062–0.0069 / 0.22–0.35° |
| 时序最紧的 c002 / c034（`slack` 0.10 s） | pinched / ball_outside | 过（板不再带 1.76° 偏摆进 3 mm 槽，插入不再拖时间；只是观察，未单独验证） |
| seed 0–9 oracle / greedy / fixed_delay | 10/10 / 8/10 / 6/10 | 10/10 / 8/10 / 6/10，逐格标签与 5.2 表相同，悬停时长相同 |

取板读数只随停放架位置变、与其他轴无关，64 格里 7 组不同读数对应 7 种架位组合。`min_finger_qpos` 0.004 在所有格之下 2 mm 以上。

## 6. 文件集

```
configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml   timing / reach 段、派生叶子、variation 块
configs/run_configs/gate_cage_ball.yaml, _gate.yaml            randomize_layout / difficulty / variant_id；final_hold_steps；fixed_delay_s；safety_margin 搬走
topogym/tasks/connectivity/gate_cage_ball.py                    t_ready / insert_duration / 三个 bounds+from_frac / checks（六行）/ validate / derive_task_cfg / validate_task_cfg / plate_top_on_rack
topogym/primitives/gated_insert.py                              _move 姿态插值（_quat_slerp，09-03）
topogym/planning/gate_cage_ball_planner.py                      FixedDelayRule、make_trigger_rule；decide 多一个 elapsed_s
demos/connectivity/gate_cage_ball_{physical_gate,inspect}_demo.py  接线、variant 行、checks 行、dt 与时序断言
tests/check_variant_rng.py                                      gate 段
tests/check_gate_cage_ball_geometry.py                          新
bash_scripts/tests/gate_cage_ball_variation_sweep.sh            新
```
