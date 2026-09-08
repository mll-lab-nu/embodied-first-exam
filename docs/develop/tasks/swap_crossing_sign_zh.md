# swap_crossing_sign（docx 3.2　交换两根线的上下关系）——变体部署记录

> 日期：2026-09-07。变体计划 `variation_axes_plain_zh.md` §6.2 第 5 步，13 个任务里最后一个部署的。
> 场景与执行链的设计记录在 `../physics/untangle/untangle_continuous_plan_zh.md`（本任务与 untangle_continuous 共用场景构建器，`tasks/entangle/swap_crossing_sign.py` 是别名模块），本文只记变体轴、判据、离线与 GPU 实测。
> 样板：`band_untwist_zh.md` §7。

## 1. 任务回顾与文件集

桌面上一条插线板贴着工作区后沿（x = −25 cm 到 −21.5 cm）。两根 8 mm 粗的软线从插线板里长出来（锚定端 x = −22.5 cm），沿 +x 铺在桌上，各占一条平行的「车道」（间距 8.5 cm），到 x = 20 cm 处各自接一个躺平的插头，机械臂只抓插头。两根线在中段换一次车道，恰好交叉一次；出生时哪根压在上面由交叉符号决定（+：出生在 −y 车道那根在上；−：反之）。

任务：终态仍只有一个交叉，但压在上面的换成另一根。oracle 两步：① separate——抓上面那根的插头，抬起、拉回自己的车道放下（交叉 1 → 0，两线分开 ≥ 1.6 cm）；② cover——抓另一根的插头，抬高越过第一根、放到它插头外侧（交叉 0 → 1，后放的在上）。对照 restack_same：第二步把同一根放回去，终态交叉仍为 1 但符号不变，预期判失败。

抬升规则（planner 现有，不改）：抓插头后，从交叉点到插头这段线垂在手下面，手要抬到「另一根线的顶面 + 这段弧长 + 4 cm」。交叉离插头越远、线越长，抬得越高；上限是工作区顶 40 cm。这是包络的主要约束。

| 层 | 文件 |
|---|---|
| 生成器 | `topogym/generation/braid.py`：`BraidLayout.crossing_frac`、`crossing_position_frac` / `crossing_window_at`（按位置裁剪换道窗口）、`build_braid_spec(word=…)`、`verify_braid_spec` 改按裁剪后窗口判陡峭度 |
| 场景 / Layout | `topogym/tasks/entangle/untangle_continuous.py`（共用）：`braid_layout()` 读 `crossing_frac`，`braid_spec()` 读 `crossing_sign`，新增 `checks()` / `validate()` / `predicted_lift()`；`build()` 先 `validate()`、断言 `braid.tube_radius == rope.radius`、跑 `verify_braid_spec` |
| 判据纯函数 | `topogym/tasks/entangle/_swap_crossing_sign_geometry.py`（Genesis-free，离线门按路径加载） |
| 钩子 | `topogym/tasks/entangle/swap_crossing_sign.py`：`validate_task_cfg` |
| 配置 | `configs/task_configs/swap_crossing_sign_topogym_tabletop_v1.yaml` 末尾 `workspace:` + `variation:`；`configs/run_configs/swap_crossing_sign.yaml` 的 `randomize_layout / difficulty / variant_id` |
| demo | `demos/entangle/swap_crossing_sign_physical_pinch_demo.py`：`run.randomize_layout=true` 时 `randomize_task_cfg`，打印 `checks` 行与 `variant` 行 |
| 离线门 | `tests/check_swap_crossing_sign_geometry.py`、`tests/check_swap_crossing_sign_planner.py`（角点扫描）、`tests/check_variant_rng.py` 的 swap 段、`tests/check_variant_corners.py` |
| sweep | `bash_scripts/tests/swap_crossing_sign_variation_sweep.sh`（visual / oracle / restack_same）、`bash_scripts/tests/variant_corners_sweep.sh swap_crossing_sign` |

## 2. 变体轴

| 类 | 叶子 | 抽法 | 默认 | 说明 |
|---|---|---|---|---|
| A 防捷径 | `braid.crossing_sign` | Cat{1, −1} | 0 | 出生时哪根在上。±1 直接给 braid 字 `(±1,)`；0 = 沿用 seed 的 `braid/word` 流（固定布局跑法与 untangle_continuous 不变）。画面里只有交叉处本身能看出来；planner 只读判定器实测的在上那根 |
| B 布局 | `braid.crossing_frac` | U[0.30, 0.75] | 0.475（= 等分公式 0.10 + 0.75 × 0.5，几何逐位不变） | 交叉点在整条 x 跨度上的比例。换道窗口 = min(0.95 × 跨度, 2 × (frac − 0.10) × 总长, 2 × (0.85 − frac) × 总长)：0.75 时从 30.3 cm 缩到 8.5 cm（x_end 0.20），换道俯视角 45°，在 59° 门内 |
| B 布局 / 单调裕度候选 | `braid.channel_spacing` | U[0.072, 0.095] | 0.085 | 车道间距 = 两插头出生间距 |
| B 布局 | `braid.center_y` | U[−0.040, 0.040] | 0.000 | 两根线整体左右平移 |
| B 布局 | `braid.x_end` | U[0.16, 0.20] | 0.200 | 插头位置即线长，只往短里变 |
| D 固定 | `braid_span` [0.10, 0.85]、`crossing_fill` 0.95、`over_lift`、`base_z`、`pinch.*`、`rope.*` | 不动 | | 都有实测事故记录（yaml 注释） |

无派生叶子：四条连续轴各自区间在全包络内可行（§3 的 32 角点）。

**三处与 `variation_and_difficulty_plan_zh.md` §3.4 原表不同，都是算出来的：**

1. 交叉位置下限 0.25 → 0.30。separate 步预测抬升 = 下面那根线的顶（0.7 + 0.4 cm）+ 交叉到插头的控制折线弧长 + 4 cm。x_end 0.20、间距 9.5 cm 时：frac 0.25 弧长 33.5 cm、抬升 38.5 cm；frac 0.30 弧长 31 cm、抬升 36 cm。band_untwist 同类估计实测偏差 ±2.6 cm，0.25 只剩 1.5 cm 余量，0.30 留 4 cm。
2. 线长上限 0.22 → 0.20。cover 步的抬升取决于第一根放下后的形状，离线只能用合成形状扫（`check_swap_crossing_sign_planner.py`：1–3 个弓形 × 两档松弛）：x_end 0.22 时最坏 41.9 cm 超过 40 cm 顶；0.20 时最坏 39.9 cm（间距 7.2 cm，只剩 1 mm，但那是最悲观的单弓形 + 5% 松弛；实际放下的线接近拉直，GPU 实测见 §5）。插头销尖 x = x_end + 2.9 cm，0.20 时离工作区边 2.1 cm。
3. 间距下限 0.060 → 0.072。两插头出生在同一 x、相距一个间距；构建器规定两插头 < 7.0 cm 拒建（夹爪半跨 4 cm + 柱半径 + 余量），`rope.free_end_connector.min_clearance` 由代码默认值改为显式写在 yaml。0.072 留 2 mm 不取等。白话表的「6.5 cm」档不可行，三档改为 9.5 / 8.3 / 7.2 cm。

## 3. `checks()` 八行

纯函数 `_swap_crossing_sign_geometry.braid_checks`（只接 `BraidSpec` + 标量）；共用 Layout 的 `checks()` / `validate()` 委托它，构建器建场景前 `validate()`。校验只拿得到未解析的 task 配置，所以 `braid.tube_radius` 是 `rope.radius` 的字面量副本、`workspace:` 段是 `manipulation_space.workspace` 的副本（两份 yaml 都加了，构建器与离线门各断言一处相等）。

| 行 | 读数 | 门 | 默认 | 32 角点最紧 |
|---|---|---|---|---|
| `end_separation` | 两插头出生 xy 距 = 间距 | ≥ `min_clearance` 0.070 | 0.085 | 0.072（间距下限） |
| `crossing_window` | 裁剪后换道窗口宽 | ≥ 0.6 × 间距（`braid.py` 的 `_MIN_WINDOW_PER_LANE`，换道俯视角 ≤ 59°） | 0.303 | 0.077（frac 0.75、x_end 0.16；角 43–51°） |
| `free_tail` | 窗口末端到插头的直段 | ≥ 0.050（插头本体 2.9 cm + 跟随带 1.2 cm 要落在直段上，留 9 mm；**假设**，未实测） | 0.072 | 0.058（x_end 0.16、frac 0.75） |
| `footprint_x` | min(工作区 x 上沿 − 插头销尖 (x_end + 0.029)，锚定端 − 下沿) | ≥ 0 | 0.021 | 0.021（x_end 0.20） |
| `footprint_y` | 工作区 y 半宽 − (车道最外 + 法兰半径 0.015) | ≥ `workspace.margin` 0.040 | 0.243 | 0.198 |
| `strip_cover` | 插线板半长 0.130 − 出线口最外 y | ≥ `tube_radius` 0.004 | 0.088 | 0.043 |
| `lift_height` | `base_z + tube_radius` + 交叉到插头的控制折线弧长（俯视，半段换道弦 + 直段）+ `pinch.lift_clearance` | ≤ `workspace.z_max` 0.40 | 0.280（固定布局 GPU 实测 279 mm） | 0.361（x_end 0.20、间距 0.095、frac 0.30） |
| `lane_entry_gap`（09-06 晚，首跑后加） | separate 步把线沿自家车道铺回去、插头越界 `lane_overshoot`；一次交叉后**另一根的尾段就在这条车道里**，铺下的线是从锚点（车道中心）到越界落点的直线，所以在另一根进入车道处（它换道窗口末端 x_w）两线直线间距 = overshoot × (x_w − x_start) / (落点 x − x_start) | ≥ `success.separation_threshold` 0.016 + 4 × `tube_radius`（两个绳径）= 0.032（**下界**，不含回弹，见 §5.6） | 0.115（overshoot 0.130） | 0.069（frac 0.30；overshoot 0.040 时只有 0.021，就是首跑三格失败的原因） |

`pinch.lane_overshoot` 因此由 0.040 改为 0.130（先试 0.090，角点 c001 / c005 仍不够，见 §5.6；本任务 yaml，untangle_continuous 不动；untangle 默认布局这一行 0.035 仍过）；cover 步用合成形状复算，最坏抬升 0.399 → 0.360，落点离对方线身 ≥ 35 mm、都预测到交叉、落点 y ≥ −0.216。

`lift_height` 与 band_untwist 同性质：是估计不是上界，planner 用沉降后实测中心线；cover 步的抬升不在行里（依赖第一根放下后的形状），由 planner 测试的合成形状扫描与 GPU 实测兜底，demo 在 planner 要求超过 0.40 时打印 WARNING、sweep 记 `lift_warn` 列。

## 4. 离线实测（2026-09-06）

| 门 | 结果 |
|---|---|
| `check_swap_crossing_sign_geometry.py`（numpy + PyYAML） | PASS：冻结布局各行与本文 §3 逐值一致（第八行 `lane_entry_gap` 09-06 晚加入后复跑仍 PASS）、控制折线弧长 0.4376 不变、`crossing_frac` 0.475 与等分公式逐位相同；0.30 / 0.75 窗口裁在 `braid_span` 内且过陡峭度门；±1 只换哪根带鼓包；3 字 word 槽位不变；32 角点各行 + braid 自检全过，最紧余量 end_separation 2.0 mm、free_tail 7.8 mm、crossing_window 20 mm、lift_height 39 mm；七个负例各挂预期的行 |
| `check_swap_crossing_sign_planner.py` | PASS。**这一行的数字随 `lane_overshoot` 0.040 → 0.130 变过**（2026-09-07 复跑）：冻结布局最坏 cover 抬升 **347 mm**；包络四角点 (x_end, 间距) = (0.16, 0.072) **321**、(0.16, 0.095) **300**、(0.20, 0.072) **360**、(0.20, 0.095) **337** mm，都 ≤ 400。改越界量之前的旧值是 387 与 363 / 344 / 399 / 379——第一根被放得离另一根更远之后，cover 的落点被夹回来时预测交叉点更靠插头，手下悬垂的弧短了，所以抬升反而低了。§2 第 2 条「x_end 0.20 时最坏 39.9 cm、只剩 1 mm」是按旧值写的依据，现按新值是 36.0 cm、余量 4 cm；包络仍保守地停在 0.20 |
| `check_variant_rng.py`（swap 段） | PASS：1000 seed 五条轴都在区间内、braid 字随 sign、交叉位置随 frac，sign +1 / −1 = 461 / 539，最大预测抬升 0.357，首抽拒绝率 0.000 |
| `check_variant_corners.py --task swap_crossing_sign` | PASS：32 角点全部可行、Hydra compose 读数一致 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| untangle_continuous 回归 | `untangle_continuous_inspect_demo run.seeds=0-9 run.no_build=true`：十行 braid 自检全绿，braid 字与改前逐位一致（seed 4 / 7 / 8 为 (−1,)，其余 (1,)） |

## 5. GPU 实测（4090，Genesis 1.2.1，无头；2026-09-06 16:44 起）

### 5.1 固定布局复跑

`runs/swap_crossing_sign_variation/20260906_164435_fixed/`：seed 0（braid 字 (1,)）terminal=True，`s0 over s1` → 1 → 0 → 1 → `s1 over s0`；separate 抬升 279 mm（`lift_height` 预测 280）、放下后两线最近距 28.6 mm；cover 抬升 349 mm；一格 8 min 6 s。改动前后行为一致（`checks` 行七行 ok）。

### 5.2 seed 0–9 oracle 首跑：7 / 10（`…/20260906_164435_oracle/`）

| seed | sign | frac | 间距 | cy | x_end | 预测抬升 | separate 实测抬升 | 放下后最近距 | cover 抬升 | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | +1 | 0.539 | 0.091 | +0.010 | 0.199 | 0.254 | 255 | 38.0 | 320 | PASS |
| 1 | −1 | 0.401 | 0.082 | +0.031 | 0.164 | 0.291 | 290 | 36.1 | 130 | PASS |
| 2 | +1 | 0.422 | 0.083 | +0.003 | 0.185 | 0.295 | 295 | **9.7** | — | FAIL：交叉 1 → 0 但两线贴着（< 16 mm），`separated_seen` 不成立，停在第一步 |
| 3 | +1 | 0.356 | 0.079 | −0.033 | 0.190 | 0.325 | 325 | **9.7** | — | FAIL（同上） |
| 4 | −1 | 0.684 | 0.088 | +0.031 | 0.183 | 0.193 | 193 | 32.8 | 132 | PASS |
| 5 | +1 | 0.374 | 0.078 | −0.036 | 0.175 | 0.308 | 308 | **9.6** | — | FAIL（同上） |
| 6 | −1 | 0.605 | 0.085 | +0.007 | 0.184 | 0.221 | 221 | 35.2 | 123 | PASS |
| 7 | +1 | 0.585 | 0.076 | −0.035 | 0.199 | 0.233 | 233 | 19.2 | 370 | PASS |
| 8 | −1 | 0.656 | 0.083 | −0.007 | 0.163 | 0.195 | 195 | — | — | PASS |
| 9 | −1 | 0.652 | 0.073 | −0.012 | 0.195 | 0.205 | 205 | — | — | PASS |

- `gt_match` 10/10（判定器读到的出生符号 = 抽到的 sign），move 1 抓的都是实测在上那根（10/10）：**sign 轴生效**。
- separate 步实测抬升与 `lift_height` 预测逐格相差 ≤ 1 mm（预测用的就是 planner 的公式，只差沉降后中心线与控制折线的弧长差）。cover 步抬升 123–370 mm，seed 7（间距最窄 0.076）370 mm 离 0.40 顶 30 mm，无 WARNING。
- **三格失败同一机制**（录像 `…_visual/visual_s2.mp4`，seed 2）：separate 放下的那根线与另一根**并排贴着**（最近距 9.7 mm = FEM 的接触静止距 2r + d_hat），交叉数虽为 0 但「分开 ≥ 16 mm」不成立。原因在执行链不在包络：`within_reach` 把落点夹在 0.90 倍绳长，绳永远留 10%（约 4 cm）松弛；下放段的手路径中点离锚点比两端更近，绳在半空先松再紧，落地时松弛冻成一个侧向弓形。设计上放下的绳离另一根只有 `lane_overshoot` 40 mm，弓形吃掉 30 mm 以上就贴上。seed 0 弓形 2 mm、固定布局 11 mm、seed 7 21 mm、三个失败格 ≥ 30 mm；失败格都是 sign +1、交叉靠锚定端（frac ≤ 0.42、抬升 295–325 mm、拉回 166–199 mm），sign −1 的 seed 1（frac 0.40、抬升 290）却过——弓形朝哪边偏与抬升 / 拉回量和左右侧都有关，录像只看得出结果。
- 第一次处置（09-06 19:00）：separate 步加第四个路点 `straighten`——插头放到桌面后沿「锚点 → 落点」同一方位再往外拖到绳伸展 `pinch.place_taut_ratio` 0.97，想把弓形拉直。复跑三格：seed 2 最近距 9.7 → 12.8 mm，seed 3 / 5 不变（9.8 / 10.0）——**没解决**。拉到 97% 仍允许 3% 松弛（单弓形最大 4 cm），且桌面摩擦让拉力只传到插头附近那一段。路点保留（无害，落点更直），但不是修复。
- 定位（19:20，加打印 `swap_crossing_sign_geometry after move 1: closest …`，seed 3）：两线最近点在 (0.026, −0.072) 与 (0.028, −0.063)——x ≈ 0.03 正是另一根（strand 1）换道窗口的末端、它进入 −y 车道的地方；被搬的 strand 0 在那里就在自家车道中心 y = −0.072（锚点就在这条车道上），而不是直线到越界落点该有的 −0.098。**几何本身留的余量太小**：一次交叉后另一根的尾段就躺在被搬那根的自家车道里，40 mm 越界只在插头那一端；在对方进入车道处两线直线间距 = 0.040 × (x_w − x_start)/(落点 x − x_start)，默认布局 35 mm，交叉在 0.30–0.42 时窗口末端前移、只剩 21–26 mm，铺下的线再弓 5–10 mm 就低于 16 mm。这解释了失败都在交叉靠锚定端的格；sign −1 的 seed 1（frac 0.40）过是弓形恰好朝外。
- 第二次处置（19:30）：`pinch.lane_overshoot` 0.040 → 0.090（本任务 yaml），最紧角（frac 0.30）那一处拉到 48 mm；`checks()` 加第八行 `lane_entry_gap` 守它 ≥ 16 + 16 mm，把这个执行链假设写成判据。cover 步合成形状复算最坏抬升 0.384（原 0.399），落点净空与交叉预测不变。包络没动。复跑见 §5.4。
- 另一个观察：`rope_blow_ups` 在 6/10 的格里报「离群粒子」（27–123 个、35–45 mm，s ≈ 0.4–0.75），成败格都有、固定布局一次没有；成功格终态正常，说明这个读数在随机布局下不是爆解而是分箱中心线与粒子的偏差，待单独看。

### 5.3 visual（seed 0–2，`…_visual/`）与 restack_same

visual = oracle + 录像：seed 0 / 1 PASS、seed 2 与 §5.2 同样在第一步停（复现，两次读数都是 9.7 mm）。restack_same 组在改 planner 前中止，与角点子集一起在 §5.5 用新参数跑。

### 5.4 三个失败格复跑（`lane_overshoot` 0.090 + `straighten`；`…/20260906_192452_fix_confirm/`）

| seed | 放下后最近距（首跑 → 复跑） | 最近点 | cover 抬升 | 结果 |
|---|---|---|---|---|
| 2 | 9.7 → **51.4** mm | (−0.073, −0.044) / (−0.060, +0.006)：在对方换道段，不再在车道里 | 297 | terminal=True |
| 3 | 9.7 → **24.0** mm | (−0.011, −0.087) / (−0.006, −0.063)：仍在对方进入车道处，直线间距 48 mm 被弓形吃掉 24 mm | — | terminal=True |
| 5 | 9.6 → **32.9** mm | (−0.018, −0.095) / (−0.009, −0.063) | — | terminal=True |

三格都翻转成功（`s0 over s1` → `s1 over s0`）。seed 3 的弓形 24 mm 超过 `lane_entry_gap` 行留的 16 mm 余量：这一行是下界不是保证，真正的余量来自 0.090 的越界量（48 − 24 = 24 mm ≥ 16）。

### 5.5 seed 0–9 oracle 复跑（越界 0.090）：**10 / 10**（`runs/swap_crossing_sign_variation/20260906_194631_oracle/`）

| seed | sign | frac | 间距 | cy | x_end | 预测抬升 | separate 抬升 | 放下后最近距 | cover 抬升 | 终态最近距 | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | +1 | 0.539 | 0.091 | +0.0096 | 0.1986 | 0.254 | 255 | 88.4 | 131 | 9.7 | PASS |
| 1 | -1 | 0.401 | 0.082 | +0.0312 | 0.1637 | 0.291 | 290 | 80.0 | 127 | 10.0 | PASS |
| 2 | +1 | 0.422 | 0.083 | +0.0034 | 0.1854 | 0.295 | 295 | 52.2 | 300 | 10.4 | PASS |
| 3 | +1 | 0.356 | 0.079 | -0.0332 | 0.1900 | 0.325 | 325 | 23.8 | 320 | 9.8 | PASS |
| 4 | -1 | 0.684 | 0.088 | +0.0309 | 0.1831 | 0.193 | 193 | 79.9 | 137 | 10.0 | PASS |
| 5 | +1 | 0.374 | 0.078 | -0.0363 | 0.1745 | 0.308 | 308 | 32.9 | 308 | 9.8 | PASS |
| 6 | -1 | 0.605 | 0.085 | +0.0074 | 0.1836 | 0.221 | 221 | 82.7 | 129 | 10.1 | PASS |
| 7 | +1 | 0.585 | 0.076 | -0.0354 | 0.1985 | 0.233 | 233 | 75.1 | 125 | 9.8 | PASS |
| 8 | -1 | 0.656 | 0.083 | -0.0065 | 0.1627 | 0.195 | 195 | 82.4 | 132 | 10.2 | PASS |
| 9 | -1 | 0.652 | 0.073 | -0.0123 | 0.1954 | 0.205 | 206 | 72.6 | 150 | 9.9 | PASS |

- 十格全部 terminal=True、`gt_match` 10/10、move 1 抓在上那根 10/10；无抬升超顶 WARNING。
- 放下后最近距 23.8–88.4 mm（首跑 9.6–38.0）：越界 0.090 之后连最紧的 seed 3（frac 0.356）也留 8 mm 余量。
- cover 步抬升 125–320 mm（首跑 123–370）：被搬的插头离得更远，cover 的落点被夹回后交叉预测点更靠插头，手下悬垂弧短了；seed 3 / 5（frac 最小）仍要 308–320 mm，离 0.40 顶 8–9 cm。
- 一格 8–9 min，十格 88 min（含前置离线门 10 min）。

### 5.6 角点子集首跑（`runs/swap_crossing_sign_corners/20260906_194631_subset/`，越界 0.090）：c001 / c005 失败

| 角点 | 取的极值 | 拉回 | 抬升 | 放下后最近距 | 结果 |
|---|---|---|---|---|---|
| c001 | sign +、frac 0.30、间距 0.072、cy −0.04、x_end 0.20 | 239 mm | 356 | **13.3** | FAIL（第一步后停） |
| c005 | sign +、frac 0.30、间距 0.095、cy −0.04、x_end 0.20 | 236 mm | 364 | **10.0** | FAIL |
| c008 | sign +、frac 0.75、间距 0.072、cy −0.04、x_end 0.16 | 47 mm | 163 | 72.0 | PASS |
| c012 | sign +、frac 0.75、间距 0.095、cy −0.04、x_end 0.16 | 40 mm | 171 | 84.5 | （改动前中止） |

最近点仍在对方进入车道处（c001：(−0.025, −0.087) / (−0.022, −0.074)），被搬的线离它该在的直线 34 mm；直线间距 48 mm 被弓形吃到 13 mm。弓形随**拉回量**长大：拉回 40–47 mm 的格弓 ≈ 10 mm，seed 2 / 3 / 5（拉回 166–199）14–24 mm，c001 / c005（拉回 236–239）34–38 mm。

根因（离线复算）：cross 路点与落点都被 `within_reach` 夹在 0.90 倍绳长的球面上，但两点之间的直线段穿过球内——c001 的直线段中点离锚点只有 **0.77 倍绳长**，也就是下放到一半时绳松了 13% 的长度（约 6 cm），到位时再绷紧，松掉的那截落地冻成侧向弓形；拉回越多、cross 与落点夹角越大，中点陷得越深。

第三次尝试（22:30）：cross → 落点之间在以锚点为球心的可达球面上插 4 个下放路点，绳全程绷着落地。复跑 c001 / c005：**11.2 / 9.8 mm，没变**（`runs/swap_crossing_sign_corners/20260906_223446_taut_confirm/`），最近点位置也没变。

真正的根因：FEM 绳的无应力形状是出生时的 S 形（`prefabs.rope_fem.rest_shape: spawn`）。被搬的线松手后，原来换道的那一段朝原弯向回弹，回弹量 = 铺下的线偏离直线的量：交叉 0.30 的角点 34–38 mm，交叉 0.36–0.42 的 seed 15–30 mm，交叉 ≥ 0.47 的 2–21 mm（换道段越靠中段、越不受插头端张力约束，回弹越大）。任何靠张力拉直的办法（拖到 97%、绷着下放）在松手那一刻都被抵消，两次实测都没改读数。**两处拉直改动已撤回**，planner / demo 回到原样，只保留最近点打印。

第四次处置（23:10）：`pinch.lane_overshoot` 0.090 → **0.130**——余量只能从几何来。最紧角（交叉 0.30）的车道入口间距 48 → 69 mm，减去 38 mm 回弹仍 ≥ 16 mm 门；`lane_entry_gap` 行的 32 mm 是下界不含回弹。cover 步合成形状复算：最坏抬升 0.360，落点离对方线身 ≥ 35 mm，落点 y ≥ −0.216，工作区 y 最外 0.2325 < 0.26。包络仍没动。复跑见 §5.8。

### 5.7 restack_same 对照（seed 0–2，`…/20260906_194631_restack/`）：3 / 3 判失败

第二步把同一根放回去：三格都跑完两步（moves 2/2）、终态交叉 1、符号与出生态相同（`s0 over s1` → `s0 over s1`，seed 1 为 `s1 over s0` → `s1 over s0`），`sign_flipped=False`、terminal=False。放下后最近距 88.5 / 80.0 / 52 mm，与 oracle 同一第一步。对照对成立：同样两步、同样的抓放，只差压上去的是哪根。

### 5.8 最终一轮全量复跑（`lane_overshoot` 0.130，2026-09-06 23:16 – 09-07 03:06）

**这是收口的那一轮，§5.5 / §5.6 / §5.7 的读数都被它取代**（那些是越界 0.090 或更早的中间状态，保留是为了记住处置过程）。目录 `runs/swap_crossing_sign_variation/20260906_231606_*/` 与 `runs/swap_crossing_sign_corners/20260906_231606_subset/`。

**seed 0–9 oracle：10 / 10**

| seed | sign | frac | 间距 | cy | x_end | 预测抬升 | 结果 |
|---|---|---|---|---|---|---|---|
| 0 | +1 | 0.539 | 0.091 | +0.0096 | 0.199 | 0.254 | PASS |
| 1 | −1 | 0.401 | 0.082 | +0.0312 | 0.164 | 0.291 | PASS |
| 2 | +1 | 0.422 | 0.083 | +0.0034 | 0.185 | 0.295 | PASS |
| 3 | +1 | 0.356 | 0.079 | −0.0332 | 0.190 | 0.325 | PASS |
| 4 | −1 | 0.684 | 0.088 | +0.0309 | 0.183 | 0.193 | PASS |
| 5 | +1 | 0.374 | 0.078 | −0.0363 | 0.175 | 0.308 | PASS |
| 6 | −1 | 0.605 | 0.085 | +0.0074 | 0.184 | 0.221 | PASS |
| 7 | +1 | 0.585 | 0.076 | −0.0354 | 0.199 | 0.233 | PASS |
| 8 | −1 | 0.656 | 0.083 | −0.0065 | 0.163 | 0.195 | PASS |
| 9 | −1 | 0.652 | 0.073 | −0.0123 | 0.195 | 0.205 | PASS |

十格 `gt_match` 全 True（判定器读到的出生符号 = 抽到的 sign）、`sep_strand` 逐格跟着 sign 走（+1 搬 strand 0、−1 搬 strand 1，说明防捷径轴生效）、`lift_warn` 全 no（没有一格要求的抬升超过工作区顶 0.40）。

**其余三组**

| 组 | 结果 |
|---|---|
| visual（seed 0–2，带录像） | 3 / 3 PASS，`…_231606_visual/visual_s{0,1,2}.mp4` |
| restack_same（seed 0–2） | 3 / 3 `sign_flipped=False`、`terminal=False` —— 两步都跑完、终态仍是一个交叉但符号没变，对照成立 |
| 角点子集（8 格） | **8 / 8 PASS**，`…_corners/20260906_231606_subset/`。两个符号各四格，八行 `checks()` 的余量都打印在 `summary.csv` 里，最紧的是 `end_separation` 2.0 mm（间距取下限 0.072）与 `lane_entry_gap` 0.0691 / 门 0.032 |
| c001 / c005 单独确认 | 2 / 2 PASS（`…_corners/20260906_231606_ov130_confirm/`），这两格正是越界 0.090 时失败的那两个 |

至此六项交付齐全，13 个任务的变体部署收口。

## 6. 决定与风险

- 三处包络取值（§2）是本次部署的决定，依据是算术不是实测；GPU 实测若在包络顶点上 planner 报抬升超顶，处置是收窄该轴（交叉位置下限上调或 x_end 上限下调），不加重试。
- `free_tail` 的 0.050 门是假设：插头本体 2.9 cm + 跟随带 1.2 cm；包络内最紧 5.8 cm，这一行目前不约束任何角点。
- cover 步的抬升只能按合成形状估计；x_end 0.20 / 间距 0.072 在最悲观形状下只剩 1 mm。真实放下的线接近拉直（`place_pullback` 2.5 cm），实测见 §5。
- `braid.crossing_sign = 0` 时仍走 seed 的 `braid/word` 流，是「抽随机数只在 `layout_randomization.py` 一处」规则的既有例外（计划表 §3.4 注明「现有机制」）；随机化打开后符号来自 `swap_crossing_sign/braid.crossing_sign` 流。
