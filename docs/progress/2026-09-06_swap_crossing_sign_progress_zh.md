# 2026-09-06 进度：swap_crossing_sign 变体部署（第 5 步，13/13 最后一个）

详细记录 `../develop/tasks/swap_crossing_sign_zh.md`；追踪表 `weekly_tracker_zh.md` §1 第 5 行。原排期 09-07，提前到 09-06 下午开始。

**一句话。** 六项交付离线部分全齐（yaml 变体块、共用 Layout 的 `checks()` 八行、demo 接线、三道离线门、sweep 脚本、文档），1000 seed 拒绝率 0、32 角点全过，untangle_continuous 共用构建器回归 braid 字逐位一致；固定布局 GPU 复跑 terminal=True（一格 8 min）；seed 0–9 oracle / visual / restack_same / 角点子集的 GPU 链在跑（结果见 §2）。

## 1. 离线部分（16:00–16:45）

| 项 | 内容 |
|---|---|
| 轴 | `braid.crossing_sign` Cat{+1, −1}（防捷径，braid 字直接给 `(±1,)`，0 = 沿用 seed 采样）；`braid.crossing_frac` U[0.30, 0.75]；`channel_spacing` U[0.072, 0.095]；`center_y` ±0.040；`x_end` U[0.16, 0.20]。无派生叶子 |
| 三处取值与计划表 §3.4 不同 | 交叉位置下限 0.25 → 0.30（separate 步预测抬升 38.5 → 36 cm，顶 40 cm，同类估计偏差 ±2.6 cm）；线长上限 0.22 → 0.20（cover 步合成形状最坏抬升 41.9 cm 超顶；插头销尖离工作区边 1 mm）；间距下限 0.060 → 0.072（两插头 < 7.0 cm 拒建）。白话表三档改 9.5 / 8.3 / 7.2 cm |
| 生成器 | `braid.py`：`crossing_frac` 字段 + 换道窗口按位置向 `braid_span` 两端裁剪（0.75 时 30.3 → 8.5 cm，换道角 45°）；`build_braid_spec(word=…)`；`verify_braid_spec` 改按裁剪后窗口逐交叉判陡峭度。不给这两个输入时输出逐位不变 |
| 共用 Layout | `checks()` 七行（插头间距、换道窗口、自由直段、工作区 x / y、插线板覆盖、separate 步预测抬升 ≤ 0.40；GPU 首跑后加第八行 `lane_entry_gap`，见 §2）；构建器建场景前 `validate()` + 断言 `tube_radius == rope.radius` + `verify_braid_spec`（此前只有 inspect demo 调它） |
| 离线门 | `check_swap_crossing_sign_geometry.py` PASS（冻结各行钉值、弧长 0.4376 不变、两个新输入、32 角点、六负例）；`check_swap_crossing_sign_planner.py` PASS（包络四角点 cover 最坏抬升 363 / 344 / 399 / 379 mm）；`check_variant_rng.py` swap 段 PASS（sign 461 / 539，最大预测抬升 0.357，拒绝率 0）；`check_variant_corners.py` 32/32 且 Hydra compose 一致；`check_configs_compose.py`、`check_demo_configs.py` PASS |
| untangle_continuous 回归 | `untangle_continuous_inspect_demo run.seeds=0-9 run.no_build=true` 改前后十行 braid 字逐位一致（seed 4 / 7 / 8 为 (−1,)） |

## 2. GPU（4090，无头；16:44 起）

| 格 | 结果 |
|---|---|
| 固定布局 oracle seed 0 | terminal=True，1 → 0 → 1、`s0 over s1` → `s1 over s0`；separate 抬升 279 mm（预测 280）、cover 抬升 349 mm；8 min 6 s（`runs/swap_crossing_sign_variation/20260906_164435_fixed/`） |
| seed 0–9 oracle 首跑 | **7 / 10**（`…_164435_oracle/`）：seed 2 / 3 / 5 在第一步后停——交叉 1 → 0 但两线贴着（最近距 9.7 mm < 16），`separated_seen` 不成立。`gt_match` 10/10、move 1 抓在上那根 10/10（sign 轴生效）；separate 实测抬升与预测逐格差 ≤ 1 mm |
| 定位（录像 + 加打印最近点） | 失败格都是交叉靠锚定端（frac 0.36–0.42）。一次交叉后另一根的尾段就躺在被搬那根的自家车道里；被搬的线从锚点（车道中心）直线铺到越界 `lane_overshoot` 40 mm 的落点，在对方进入车道处（换道窗口末端）两线直线间距只有 40 × (x_w − x_start)/(落点 x − x_start)：默认布局 35 mm、frac 0.30–0.42 时 21–26 mm，铺下的线弓 5–10 mm 就贴上。第一次处置（第四路点 `straighten` 拖到 97% 伸展）没解决（9.7 → 12.8 / 9.8 / 10.0）；第二次处置 `lane_overshoot` 0.040 → 0.090（最紧角 48 mm）+ `checks()` 第八行 `lane_entry_gap` ≥ 16 + 16 mm，包络没动 |
| 复跑 seed 2 / 3 / 5（`…_192452_fix_confirm/`） | 三格 terminal=True，放下后最近距 51.4 / 24.0 / 32.9 mm |
| seed 0–9 oracle 复跑（越界 0.090） | **10 / 10**（`…_194631_oracle/`），放下后最近距 23.8–88.4 mm，cover 抬升 125–320 mm |
| restack_same 0–2 | 3 / 3 判失败（两步跑完、符号不变） |
| 角点子集首跑（越界 0.090） | c001 / c005（交叉 0.30、x_end 0.20、拉回 236–239 mm）**失败**：最近距 13.3 / 10.0，铺下的线偏离直线 34–38 mm；c008 过（72 mm） |
| 第三次尝试 | 沿可达球面下放让绳全程绷着（cross → 落点直线段中点只有 0.77 倍绳长）——复跑 c001 / c005 **没变**（11.2 / 9.8） |
| 根因 | FEM 绳无应力形状 = 出生 S 形（`rest_shape: spawn`），松手后换道段回弹，回弹量随交叉靠锚定端而增大（38 mm）；靠张力拉直的两处改动撤回 |
| 第四次处置 | `lane_overshoot` 0.090 → **0.130**：最紧角车道入口间距 69 mm，减去 38 mm 回弹仍 ≥ 16 mm；cover 合成形状复算最坏抬升 0.360。23:12 起排队最后一轮：c001 / c005 确认 → seed 0–9 oracle → restack 0–2 → 角点子集 8 格 → visual 0–2（约 4 h，结果见 §3） |

## 3. 最后一轮结果（23:16 起，09-07 03:06 跑完）

`lane_overshoot` 0.130 的全量复跑，目录 `runs/swap_crossing_sign_variation/20260906_231606_*/` 与 `runs/swap_crossing_sign_corners/20260906_231606_{subset,ov130_confirm}/`。

| 组 | 结果 |
|---|---|
| c001 / c005 确认（越界 0.130） | 2 / 2 PASS —— 就是越界 0.090 时失败的那两格 |
| seed 0–9 oracle | **10 / 10**，`gt_match` 全 True、`sep_strand` 逐格跟着 sign 走、无抬升超顶告警 |
| restack_same（seed 0–2） | 3 / 3 `sign_flipped=False`、`terminal=False`，对照成立 |
| 角点子集 8 格 | **8 / 8 PASS**，两个符号各四格 |
| visual（seed 0–2） | 3 / 3 PASS，录像在 `…_visual/` |

**六项交付齐全，13 个任务的变体部署到此收口。** 详细表格与最紧余量见 `../develop/tasks/swap_crossing_sign_zh.md` §5.8。

一处随后修正（2026-09-07）：任务文档 §4 的 `check_swap_crossing_sign_planner.py` 数字是按 `lane_overshoot` 0.040 记的，改成 0.130 之后复跑是冻结布局 347 mm、四角点 321 / 300 / 360 / 337 mm（旧值 387 与 363 / 344 / 399 / 379）。第一根被放得更远之后，cover 的落点被夹回来时预测交叉点更靠插头，手下悬垂的弧短了，抬升反而低了。§2 第 2 条「x_end 0.20 只剩 1 mm」是按旧值写的，现按新值余量 4 cm，包络仍保守停在 0.20。
