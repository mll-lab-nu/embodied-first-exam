# 2026-09-03 进度归档：gate_cage_ball 变体部署（第 3 步）

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 3 步。
> 详细记录：`../develop/tasks/gate_cage_ball_zh.md`（新建）；本文只汇总。
> 昨日改动由用户提交；本日改动未提交，见文末清单。

---

## 0. 一句话

gate_cage_ball 的变体逻辑按 linkbar / diverter 的范式部署完毕：两条可解性判据所需的步长与触发富余搬进任务定义的 `timing:` 段，
三个耦合叶子按判据反解区间后派生，离线 1000 seed 拒绝率 0；GPU seed 0–9：oracle 首跑 6/10 → 修正判据 `pinched` 的定义后 **10/10**，greedy 8/10，fixed_delay 6/10。
另加一道三任务通用的**角点门**（包络全部顶点，离线 + GPU）：linkbar 20/20、diverter 256/256、gate **54/64**，gate 的 10 个失败格全在闸架 `center_y=−0.03` 且 `x_frac=0` 那一角，未处理。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 校验函数拿不到 env / run 段 | task yaml 加 `timing:`（`sim_dt` 0.01、`safety_margin` 0.15 从 run 配置搬来、`ready_margin` 0.10 新）；demo 断言 `timing.sim_dt == env.sim.dt`，并断言 Layout 的 `t_ready()` / `insert_duration()` 与 `GatedInsertPrimitive` 同名公式相等 |
| 包络 | `speed` [0.08, 0.16]、`center_x` [0.055, 0.095]、`rack.center_y` ±0.03 独立抽；`flat_end_y`（判据 A）、`release_y`（判据 B）、`rack.center_x`（不与导柱重叠）由归一化量派生。原表 `release_y` 下界 −0.46 越过轨底起点，弃用 |
| 不约束的量 | `hover_wait = entry_delay − t_ready` 的正负只报告：它是三条触发规则拉开差距的机制 |
| 第三条对照规则 | `FixedDelayRule`（`run.trigger=fixed_delay`，`run.fixed_delay_s` 3.6）：不感知球的策略的上限 |
| 角点门 | 随机 sweep 抽不到包络边界，可解性判据恰在那里最紧。加边界值测试：从 yaml `variation:` 块构造全部顶点（uniform 两端点 × choice 全部值；spaced_pair 用手写命名对），离线过派生 / 校验 / `checks()`，再逐格送进物理。只走 demo 的固定布局路径（`run.randomize_layout=false` + `task.*` 覆盖），不碰 `randomize_task_cfg`，seed→变体映射不变 |

## 2. 做了什么

- Layout：`t_ready` / `insert_duration` / `window_margin` / `last_commit` / `ready_margin` / `hover_wait`；三个 `*_bounds` / `*_from_frac`；`rack_channel_gap`、`hover_reach`；`checks()` 五行、`validate()`；模块级 `derive_task_cfg` / `validate_task_cfg`；builder 建场景前 `validate()`。
- yaml：`timing:`、`reach:`；`channel.flat_end_y_min/max/flat_end_frac`、`ball.spawn_entry_margin/spawn_door_margin/release_frac`、`gate_rack.x_min/channel_gap/x_frac`；头注两条判据改指向 `checks()`；末尾 `variation:` 块。
- 规则：`FixedDelayRule`、`make_trigger_rule`；三条规则的 `decide` 多一个 `elapsed_s`。
- demo：两个 demo 接 `randomize_task_cfg` + `variant` 行；physical demo 加 `checks` 行、dt 与时序断言、`safety_margin` 改读 task、死键 `task.feed_ramp.rise` 文案改掉、`EpisodeKey.variant_id`；inspect demo 加 `final_hold_steps`。
- run 配置：三个变体键；gate 配置删 `safety_margin`、加 `fixed_delay_s`、尾注改写。
- 离线门：`check_variant_rng.py` gate 段；`tests/check_gate_cage_ball_geometry.py`。
- sweep：`bash_scripts/tests/gate_cage_ball_variation_sweep.sh`（visual / oracle / greedy / fixed）。
- 角点门（三任务通用）：`tests/check_variant_corners.py`（`TASKS` 表登记 yaml / physical config / Layout / 命名对；linkbar 尚无 `checks()`，用 `_linkbar_checks` 把 `validate()` 的四条不等式改写成余量并加 `sweep_deg`；每个角点经 Hydra compose 复现读数，`--manifest` 输出 TSV）；
  `bash_scripts/tests/variant_corners_sweep.sh <task> [oracle visual 对照…]`（先跑离线门产清单，再每格一跑；`CORNERS="c002 c016"` 选格、`DRY_RUN=1` 只打印命令；产出 `runs/<task>_corners/<时间戳>/{corners.tsv,summary.csv,*.log}`）。用法与读法见 `tests/README.md`、白话文档 §4.3。
- 文档：`gate_cage_ball_zh.md` 新建；计划文档 §2.5 / §3.6 / §5；白话文档 §4 / §6.2；README 索引。

## 3. 实测

| 门 | 结果 |
|---|---|
| `check_variant_rng.py`（六段） | 全 PASS。gate 首抽拒绝率 0.000；球先到 462 / 臂先到 538 |
| `check_gate_cage_ball_geometry.py` | PASS：seed 0–199 checks 全过；16 个包络角点 slack 0.00–5.45 s；时序公式与原语一致；三条规则四个合成状态判定正确 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| `check_variant_corners.py`（离线） | 三任务全 PASS：linkbar 20、gate 64、diverter 256 个角点全部可行、无拒绝，Hydra compose 读数一致 |
| GPU sweep seed 0–9 首跑 | visual 10/10；oracle 6/10，四格 `ball_pinched_in_doorway`；greedy 4/10；fixed 6/10 |
| seed 5 复盘 | 闸板整个坐到轨底（`gate_bottom_z` 0.009）、球在门内 47 mm 自由往复——任务其实成功；`pinched` 只问「球心在门口 ±51 mm 内」，短封闭区里判定时刻球常在门口附近 |
| 判据修正后重跑三组（`*_judgefix/`） | oracle **10/10**（悬停 0–2.34 s 与 `hover_wait` 一致）；greedy 8/10（只在臂提前 ≥ 0.96 s 时失败，其余「从下降中的闸板底下钻进去」）；fixed_delay 6/10 |
| GPU 角点 sweep，oracle 组（`runs/*_corners/20260902_205605/`，判据修正之后跑） | linkbar **20/20**；diverter **256/256**（`knob_reach` 0.625–0.690）；gate **54/64**，每格 8–13 s。gate 失败格见 §4 |
| gate 取板原语修正后重跑（`runs/gate_cage_ball_corners/20260903_145828_slerpfix/`、`runs/gate_cage_ball_variation/20260903_145828_slerpfix/`） | 角点 oracle **64/64**，64 格 `finger_qpos` 0.0062–0.0069、`plate_yaw` 0.22–0.35°（修前那一角 −0.0010 / 2.19°）；时序最紧的 c002 / c034 也过；seed 0–9 oracle 10/10、greedy 8/10、fixed 6/10，逐格与判据修正后那轮相同 |
| `check_gate_cage_ball_geometry.py`（六行 + `approach_z=0.220` 必拒）、`check_variant_rng.py`、`check_variant_corners.py --task gate_cage_ball`、`check_configs_compose.py`、`check_demo_configs.py` | 全 PASS；64 角点 `approach_clearance` 恒 0.032 |

## 4. 遗留 / 观察

- **判据修正**（`topogym/verification/gate_cage_ball_verifier.py`）：`pinched` 改为「闸板挡着 且 板被顶住没坐到位（板底高于 `gate.seated_bottom_z` 5 mm 以上）且 球体在板的 y 跨度内」，
  即只有板压在球上才算夹住。旧定义在默认实例上没暴露只是窗口相位凑巧。与 diverter 的 `max_lag` 同一类：变体把判据里的隐含假设晒了出来。
- greedy 8/10 偏高，原因是下板 1.0 s 慢于臂的提前量；不按它的分数回调包络。若要让它更接近随机，动的是 `motion.insert_steps`（原语参数），另议。
- **gate 角点 10/64 失败，未处理**。全部落在 `gate_rack.center_y=−0.03` 且 `gate_rack.x_frac=0`（该组合 16 格，失败 10）：
  - 8 格 `grasp_check_failed`（c016/018/020/022/048/050/052/054）：都在 `channel.center_x=0.095`，与球速和两个派生 frac 无关；`phases=8/15`，死在取板后的 `lift_test`。形式上判负的是 **`plate_yaw` 2.19° > `max_plate_yaw_deg` 2.0**；同格 `finger_qpos` −0.0010（正常格被板挡在 0.0063–0.0075），按原语文档的定义是「夹了个空」，只因 `min_finger_qpos` 为 null 不判；`lift_delta` 0.106 是 assisted attachment 带起来的。
    **根因（09-03 逐步追踪 + 对照实验，GPU 复现）**：板在 approach 阶段就被手指扫走，descend / close 还没开始。approach 是从 home 位（指开合轴沿 x）30 步移到停放架上方 `approach_z` 0.240，同时姿态要转到 `default_ee_quat`（指开合轴沿 y），腕转 90°。`GatedInsertPrimitive._move` 收了 `start_quat` 却没用：每一步给 IK 的姿态目标都是最终姿态，而 `PivotLeverPrimitive._move` / `AxialInsertPrimitive._move_linear` 都用 `_quat_slerp` 把姿态在 30 步里插值——从 axial_insert 派生时把 slerp 丢了。后果：IK 每步面对 90° 的姿态误差，给出的中间关节角让手下沉到指令下方 63–70 mm、倾 17–18°（只转腕不平移也是 70 mm；放慢到 120 步仍 70 mm，说明是解序列本身而不是动态滞后）。`approach_z` 只给指尖 12 mm 静态净空（指尖 ≈ 0.117，板顶 0.105），指尖从板顶边缘扫过：第 12 步起两根（耦合的）手指被顶着合拢到 −0.001，板被推向 −x 14 mm、偏摆 2.1°；随后合爪、attachment 把已偏的板挂上手，`lift_test` 读到 2.19°。对照：同一移动加 slerp，下沉 1.5 mm、倾 1.6°。另有一项独立的水平滞后（165 mm 平移在 0.3 s 内，终点落后 40 mm，不转腕也一样），settle 30 步即归零，不是撞板原因。c000 同一机制但推得更远（板离手 69 mm），偏摆只 1.76°，判「过」，全程手指空夹、靠 attachment 拎着插进了槽——是现门漏掉的假成功；停放架在 `center_y=−0.03`、`x_frac=0` 的 16 格里指位全部 ≤ 0.0018，都是这种。停放架在 `center_y=+0.03` 时同样的扫掠从板旁边过、不碰，指位保持 0.040。可达性不是问题：底座到停放架 0.451 m，`lift_test` 时手到位 ±4 mm。
    **已处置（oracle 侧，包络不动）：** ① `gated_insert._move` 补 `_quat_slerp`（逐字同 axial_insert，用上原本收了没用的 `start_quat`）；② `min_finger_qpos` null → 0.004；③ `checks()` 第六行 `approach_clearance = approach_z − HAND_TO_PAD_Z − 停放架上板顶 ≥ 0.030`（现值 0.032，不随任何轴变）；④ 几何测试加 `approach_z=0.220` 必被 `validate()` 拒。**用户定：不加 settle**（会把 `t_ready` 2.40 → 2.70 s、改变 `release_y` 派生上界，v=0.16 且封闭区最短的格会被挤空），**`approach_z` 不动**。重跑结果见 §3 末两行：64/64。
  - 2 格时序：c002 `pinched`、c034 `ball_outside`，都是 `center_x=0.055, flat_end_frac=0, release_frac=1`（球放得最近），`slack` 只有 +0.10 s、`window_margin` ≈ 0。这是包络里时序最紧的顶点，和随机 sweep 里 oracle 10/10 不矛盾——随机抽不到它。**原语修正后这 2 格也过了**（板不再带 1.76° 偏摆进 3 mm 槽；只是观察，`ready_margin` 未动）。旋钮是 `timing.ready_margin`（`release_y` 上界由判据 B 取等给出）：0.10 → 0.30 时 c002 的上界 −0.144 → −0.160；但 v=0.16、`flat_end_frac=0` 的格在 0.10 时区间只剩 0.024 m，0.30 就空了（拒绝）。抬 `ready_margin` 要么同时抬 `safety_margin`（判据 A，`flat_end` 下界随之变长），要么接受高速端拒绝率上升；改后重跑拒绝率门。
  - 两类都按 09-02 原则处理：修 oracle 执行参数或收窄该轴，不加重试。

- `motion.*_z` 仍是手写绝对高度（§2.5 约定 1）；本步的轴不动 z，欠账留着。
- `TopoGym_变体参数轴表.xlsx` 的 gate 行需手动同步。

## 5. 当前进度与下一步

变体计划 §6.2 的第 0–3 步已落地：通用层（`VariantRng`、yaml `variation:` 块、`derived` kind、拒绝率门 2%）和三个 C4 强制任务
（linkbar、diverter、gate_cage_ball）。三个任务的完成度一致：六项清单齐全，GPU seed 0–9 oracle 10/10；角点门三任务全过（gate 修取板原语后 64/64，§4）。§4.3 的 50 seed 全包络 sweep
与 §4.4 划档尚未开始，等 13 个任务的变体逻辑都立住再做。

**下一个：§6.2 第 4 步 band_untwist**（docx 3.3，8 字绳解自交叉；计划文档 §3.12）。按范式要做的：

| 项 | 内容 |
|---|---|
| 防捷径离散轴 | 上压股（端 0 / 端 1）。现在 `OVER_END = 0` 由折线点序固定（`_figure_eight_geometry.py`），要加镜像开关，且 `layout.over_end` 同步；对照规则 `wrong_end` 已有 |
| 连续轴 | `heading_deg` ±30、`center` ±0.03、`half_angle_deg` [30, 60]、`closed_lobe_radius` [0.032, 0.055]、`open_lobe_radius` [0.040, 0.065] 独立抽 |
| 派生 | `end_gap`：下限 `min_clearance` 0.07（夹爪跨距），上限 `2·open_lobe_radius`——依赖其他轴，抽归一化量派生 |
| `checks()` | 转角半径 ≥ 3·管半径、足迹在工作区、抬升高度 ≤ 0.40（由 `open_lobe_radius` 决定）、放置弦长 = `place_clearance`；现有 `FigureEightSpec.__post_init__` 抛错式与 `check_band_untwist_geometry.py` 断言迁进来 |
| 随机数 | 只在 `layout_randomization.py` 抽；`BandUntwistLayout.seed` 已传入未消费，`figure_eight_spec()` 只接收采好的值 |
| 风险 | FEM 绳任务一格几十分钟，GPU sweep 成本远高于前三个刚体任务；先把离线门做扎实再上 GPU |

## 6. 文件清单

```
topogym/tasks/connectivity/gate_cage_ball.py（含 checks 第六行 approach_clearance、plate_top_on_rack）
topogym/primitives/gated_insert.py（_move 姿态插值 _quat_slerp）
topogym/planning/gate_cage_ball_planner.py, topogym/planning/__init__.py
topogym/verification/gate_cage_ball_verifier.py（pinched 定义）
configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml
configs/run_configs/gate_cage_ball.yaml, gate_cage_ball_gate.yaml
demos/connectivity/gate_cage_ball_physical_gate_demo.py, gate_cage_ball_inspect_demo.py
tests/check_variant_rng.py, tests/check_gate_cage_ball_geometry.py（新）, tests/check_variant_corners.py（新，三任务角点门）, tests/README.md
bash_scripts/tests/gate_cage_ball_variation_sweep.sh（新）, bash_scripts/tests/variant_corners_sweep.sh（新）
docs/develop/tasks/gate_cage_ball_zh.md（新）, README.md, variation_and_difficulty_plan_zh.md, variation_axes_plain_zh.md
docs/progress/2026-09-03_progress_zh.md（本文）
```
