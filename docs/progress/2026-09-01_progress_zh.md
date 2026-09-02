# 2026-09-01 进度归档：linkbar 变体改版 + 变体声明搬进 yaml

> 范围：变体计划（`../develop/tasks/variation_axes_plain_zh.md` §6.2）第 0 步与第 1 步。
> 详细记录：`../develop/tasks/linkbar_rotate_to_zone_zh.md` §5.3、§8.4、§8.5；本文只汇总。
> 未提交：本日改动共 17 个文件（含本文），见文末清单。

---

## 0. 一句话

linkbar_rotate_to_zone 的变体逻辑按新要求（固定虚线导轨 + 两块自由色区）重做并在 GPU 上验收通过；变体轴的声明从 python 注册表搬进任务 yaml 的 `variation:` 块，后续 12 个任务注册时只加 yaml、不动 python。

## 1. 会话里定下的决定

| 决定 | 内容 |
|---|---|
| 范围 | 13 个目标任务（`TopoGym_变体参数轴表.xlsx` 的 13 行）。cable_routing / untangle / untangle_continuous / stacked_plate / peeling / swap 及 `tasks/legacy/` 定为 **legacy**，不纳入工程开发，代码不删不改 |
| 优先级 | 先把 13 个任务的变体生成逻辑确立并部署；`EpisodeSpec` / H5 落盘属数据管线，**暂缓** |
| linkbar 场景 | 固定 ±90° 虚线导轨；两块色区在导轨上任意放置，可同侧、可相邻，只要求不重叠；颜色六色不放回抽两种 |
| 区键名 | `left` / `right` → `color_1` / `color_2`（无方位含义，随机化后 `color_1` 角度较小） |
| 销出生 | 不得落在任一区内（`half_width + 2°` 余量），validate 拒绝；首抽拒绝率 0.234 是结构性约束，测试阈值单独设 0.30 |
| 扫掠步数 | 不固定 240，按扫掠角推导：`steps = max(120, ceil(|sweep| / 0.23°))`，固定角速度 |
| 变体声明 | 每个任务 yaml 末尾一段 `variation:` 列表；`validate` 用 `"模块:函数"` 字符串引用 |

## 2. 做了什么

### 2.1 linkbar 改版（第 1 步）

- `validate()` 五条规则：初始角在导轨上、区整体在导轨内、销出生不在区内、两区不重叠（相邻允许）、两色不同。删除「异侧」「扫掠带 [15°, 75°]」。
- 导轨 `rail.start/end_deg = ±90`，36 格，落在区跨度内的格跳过。
- 新通用 directive `_SpacedPairJitter`：构造式采「间距 ≥ min_gap 的有序对」，不为重叠拒绝。
- `steps_arc` 由 `LinkbarRotateLayout.steps_arc(sweep)` 推导。
- 两个 demo、两份 run 配置、`linkbar_variation_sweep.sh`（CSV 加 `gap_deg` / `same_side`）、`linkbar_rotate_to_zone_check.sh`（seat 相位改名）同步。

### 2.2 变体声明搬进 yaml（第 0 步）

- linkbar yaml 末尾加 `variation:` 块（choice / distinct_choice / spaced_pair / uniform / validate 五条）。
- `layout_randomization.py`：删 `_REGISTRY`、`registered_tasks()`、`_SwapJitter`；新增 `_parse_directives` / `_resolve_validate` / `has_variation`；采样与重采逻辑不动。
- 任务模块加 `validate_task_cfg(task_cfg)` 供 yaml 引用。

## 3. 实测

| 门 | 结果 |
|---|---|
| 离线五门（geometry / planner / variant_rng / configs_compose / demo_configs） | 全 PASS |
| 1000 seed 离线 | 同侧 368 / 异侧 632 / 近邻 (<5°) 69；六色 30 种有序对全覆盖；首抽拒绝率 0.234 |
| GPU sweep seed 0–9（改版后） | oracle **10/10**；`nearest_zone` **5/10**（逐条：近区恰为目标时才成功）；十格首帧一眼可分 |
| `max_lag`（步数固定 240） | 随扫掠角线性增长 0.05°/°，88° 时 4.79°（门 6°） |
| `max_lag`（步数推导后，重跑 seed 0–9 + seed 259 @ 92.3°） | 1.66–3.40°，与扫掠角无关；oracle 11/11 |
| yaml 搬家 | seed 0–99 采样值改前改后 `diff` 为空；黄金值、包络、拒绝率与之前一致；GPU seed 2 variant 行逐字一致 |

## 4. 遗留 / 观察

- 终角过冲随扫掠角增长（0.6° @ 15.6° → 2.2° @ 90°），与角速度无关，来源待查；容差 4°，暂不处理，划档 sweep 时记读数。
- `linkbar_rotate_to_zone_check.sh` 八格在 seat 相位改名后未重跑；默认几何未变，预期全过。
- `docs/progress/TopoGym_变体参数轴表.xlsx` 的 linkbar 三行（键名、连续布局轴描述、校验函数）需手动同步；`TopoGym_环境进度追踪表.xlsx` 整体落后于文档。
- `variation_axes_plain_zh.md` §2 的 linkbar 单调裕度轴「两区角差分箱」留到划档。

## 5. 下一步

按 §6.2 顺序：**diverter_route_ball**（第 2 步）。前置：球径双侧不等式从配置注释抽成函数、可达行（拨杆 ≤ 0.69 m）；交付物按 linkbar 的六项清单（轴声明 yaml 块、Layout `validate` / 派生、demo 接线 + variant 行、`check_variant_rng.py` 任务段、sweep 脚本、实测写回文档）。随后 gate_cage_ball（第 3 步，新增 `checks()`）。

建议先提交今日改动再开 diverter。

## 6. 文件清单

```
configs/task_configs/linkbar_rotate_to_zone_topogym_tabletop_v1.yaml   区键 / rail / pin_start_margin / arc_deg_per_step / variation 块
configs/run_configs/linkbar_rotate_to_zone.yaml, _rotate.yaml           注释示例改键名
topogym/tasks/connectivity/linkbar_rotate_to_zone.py                    validate 五规则、rail_span、_add_rail、steps_arc、validate_task_cfg
topogym/generation/layout_randomization.py                              读 yaml variation 块；_SpacedPairJitter；删注册表
topogym/planning/linkbar_rotate_to_zone_planner.py                      docstring
demos/connectivity/linkbar_rotate_to_zone_{physical,inspect}_demo.py    键名、variant 行、steps_arc 推导
bash_scripts/tests/linkbar_variation_sweep.sh, linkbar_rotate_to_zone_check.sh
tests/check_linkbar_zone_geometry.py, check_linkbar_planner.py, check_variant_rng.py
docs/develop/tasks/linkbar_rotate_to_zone_zh.md                         §5.3 / §8.4 / §8.5 / §9
docs/develop/tasks/variation_and_difficulty_plan_zh.md                  §1 / §2.4 / §2.5 / §3.8 / §6.10
docs/develop/tasks/variation_axes_plain_zh.md                           §2–§4 linkbar 行、§6.1 / §6.2
docs/progress/2026-09-01_progress_zh.md                                 本文
```
