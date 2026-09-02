# 2026-09-03 进度归档：gate_cage_ball 变体部署（第 3 步）

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 3 步。
> 详细记录：`../develop/tasks/gate_cage_ball_zh.md`（新建）；本文只汇总。
> 昨日改动由用户提交；本日改动未提交，见文末清单。

---

## 0. 一句话

gate_cage_ball 的变体逻辑按 linkbar / diverter 的范式部署完毕：两条可解性判据所需的步长与触发富余搬进任务定义的 `timing:` 段，
三个耦合叶子按判据反解区间后派生，离线 1000 seed 拒绝率 0；GPU seed 0–9：oracle 首跑 6/10 → 修正判据 `pinched` 的定义后 **10/10**，greedy 8/10，fixed_delay 6/10。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 校验函数拿不到 env / run 段 | task yaml 加 `timing:`（`sim_dt` 0.01、`safety_margin` 0.15 从 run 配置搬来、`ready_margin` 0.10 新）；demo 断言 `timing.sim_dt == env.sim.dt`，并断言 Layout 的 `t_ready()` / `insert_duration()` 与 `GatedInsertPrimitive` 同名公式相等 |
| 包络 | `speed` [0.08, 0.16]、`center_x` [0.055, 0.095]、`rack.center_y` ±0.03 独立抽；`flat_end_y`（判据 A）、`release_y`（判据 B）、`rack.center_x`（不与导柱重叠）由归一化量派生。原表 `release_y` 下界 −0.46 越过轨底起点，弃用 |
| 不约束的量 | `hover_wait = entry_delay − t_ready` 的正负只报告：它是三条触发规则拉开差距的机制 |
| 第三条对照规则 | `FixedDelayRule`（`run.trigger=fixed_delay`，`run.fixed_delay_s` 3.6）：不感知球的策略的上限 |

## 2. 做了什么

- Layout：`t_ready` / `insert_duration` / `window_margin` / `last_commit` / `ready_margin` / `hover_wait`；三个 `*_bounds` / `*_from_frac`；`rack_channel_gap`、`hover_reach`；`checks()` 五行、`validate()`；模块级 `derive_task_cfg` / `validate_task_cfg`；builder 建场景前 `validate()`。
- yaml：`timing:`、`reach:`；`channel.flat_end_y_min/max/flat_end_frac`、`ball.spawn_entry_margin/spawn_door_margin/release_frac`、`gate_rack.x_min/channel_gap/x_frac`；头注两条判据改指向 `checks()`；末尾 `variation:` 块。
- 规则：`FixedDelayRule`、`make_trigger_rule`；三条规则的 `decide` 多一个 `elapsed_s`。
- demo：两个 demo 接 `randomize_task_cfg` + `variant` 行；physical demo 加 `checks` 行、dt 与时序断言、`safety_margin` 改读 task、死键 `task.feed_ramp.rise` 文案改掉、`EpisodeKey.variant_id`；inspect demo 加 `final_hold_steps`。
- run 配置：三个变体键；gate 配置删 `safety_margin`、加 `fixed_delay_s`、尾注改写。
- 离线门：`check_variant_rng.py` gate 段；`tests/check_gate_cage_ball_geometry.py`。
- sweep：`bash_scripts/tests/gate_cage_ball_variation_sweep.sh`（visual / oracle / greedy / fixed）。
- 文档：`gate_cage_ball_zh.md` 新建；计划文档 §2.5 / §3.6 / §5；白话文档 §4 / §6.2；README 索引。

## 3. 实测

| 门 | 结果 |
|---|---|
| `check_variant_rng.py`（六段） | 全 PASS。gate 首抽拒绝率 0.000；球先到 462 / 臂先到 538 |
| `check_gate_cage_ball_geometry.py` | PASS：seed 0–199 checks 全过；16 个包络角点 slack 0.00–5.45 s；时序公式与原语一致；三条规则四个合成状态判定正确 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| GPU sweep seed 0–9 首跑 | visual 10/10；oracle 6/10，四格 `ball_pinched_in_doorway`；greedy 4/10；fixed 6/10 |
| seed 5 复盘 | 闸板整个坐到轨底（`gate_bottom_z` 0.009）、球在门内 47 mm 自由往复——任务其实成功；`pinched` 只问「球心在门口 ±51 mm 内」，短封闭区里判定时刻球常在门口附近 |
| 判据修正后重跑三组（`*_judgefix/`） | oracle **10/10**（悬停 0–2.34 s 与 `hover_wait` 一致）；greedy 8/10（只在臂提前 ≥ 0.96 s 时失败，其余「从下降中的闸板底下钻进去」）；fixed_delay 6/10 |

## 4. 遗留 / 观察

- **判据修正**（`topogym/verification/gate_cage_ball_verifier.py`）：`pinched` 改为「闸板挡着 且 板被顶住没坐到位（板底高于 `gate.seated_bottom_z` 5 mm 以上）且 球体在板的 y 跨度内」，
  即只有板压在球上才算夹住。旧定义在默认实例上没暴露只是窗口相位凑巧。与 diverter 的 `max_lag` 同一类：变体把判据里的隐含假设晒了出来。
- greedy 8/10 偏高，原因是下板 1.0 s 慢于臂的提前量；不按它的分数回调包络。若要让它更接近随机，动的是 `motion.insert_steps`（原语参数），另议。

- `motion.*_z` 仍是手写绝对高度（§2.5 约定 1）；本步的轴不动 z，欠账留着。
- `TopoGym_变体参数轴表.xlsx` 的 gate 行需手动同步。

## 5. 下一步

§6.2 第 4 步 band_untwist：镜像开关（同步 `layout.over_end`）、planner 抬升 ≤ 0.40 守卫、`end_gap` 上限随开口叶半径。

## 6. 文件清单

```
topogym/tasks/connectivity/gate_cage_ball.py
topogym/planning/gate_cage_ball_planner.py, topogym/planning/__init__.py
topogym/verification/gate_cage_ball_verifier.py（pinched 定义）
configs/task_configs/gate_cage_ball_topogym_tabletop_v1.yaml
configs/run_configs/gate_cage_ball.yaml, gate_cage_ball_gate.yaml
demos/connectivity/gate_cage_ball_physical_gate_demo.py, gate_cage_ball_inspect_demo.py
tests/check_variant_rng.py, tests/check_gate_cage_ball_geometry.py（新）
bash_scripts/tests/gate_cage_ball_variation_sweep.sh（新）
docs/develop/tasks/gate_cage_ball_zh.md（新）, README.md, variation_and_difficulty_plan_zh.md, variation_axes_plain_zh.md
docs/progress/2026-09-03_progress_zh.md（本文）
```
