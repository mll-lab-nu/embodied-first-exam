# band_untwist（docx 3.3　8 字绳圈改成 O 形）——开口绳桌面版

工程名 `band_untwist`，类别 `entangle`。本文记录闭合带路线为何废弃、开口绳桌面版的几何与判定契约、
oracle 与对照、以及待跑的 GPU 验证。代码落地日期 2026-08-27。

相关：`task_environment_buildout_zh.md` §3（闭合环能力盘点）、`../framework/task_taxonomy_zh.md` §4.3
（C3 判定契约）、`tests/closed_band_spike.py`（闭合带 spike，已废弃路线的证据）。

---

## 1. docx 原设计与实际落地的差异

| | docx 3.3 | 本任务 |
|---|---|---|
| 物体 | 闭合弹性带 | 开口 FEM 绳（`untangle_continuous` 同款管线） |
| 固定方式 | 壁面挂销，带自由悬垂 | 平放桌面，桌面摩擦固定 |
| 初态 | 带自身扭成 8 字（一个自交叉） | 绳摆成 8 字：一个闭合叶 + 一个开口叶，交叉点一处 |
| 动作 | 抓下瓣从正确一侧翻转 | 抓交叉处压在上面那股的绳头，抬起跨过另一股，放到另一绳头外侧 |
| 判定 | 规定投影下自交叉 1 → 0 | 同：俯视投影自交叉 1 → 0，且两绳头落回桌面 |
| 防捷径 | 翻错一侧变 2；压扁 8 字不改变判定 | 抓错端变 2（`run.oracle_mode=wrong_end`）；压扁用例在离线门里 |
| 物理层复核 | 向下轻拉带的下缘，验证周长展开成单圈 | **推迟**（同 `untangle_continuous` 的 lift-test） |

### 1.1 闭合带路线为何废弃

Phase 0 spike（`tests/closed_band_spike.py`，`world/closed_band.py`，2026-08-21）在 FEM+IPC 下的读数：

- 网格与接缝（U1）、载入与沉降（U2）、拧成 8 字的机构（`follow` band 驱动）全部通过。
- **U3 失败**：拧成的 8 字在释放后 25 步（0.25 s）内完全回弹成平整 O，之后 700 步不动，三次一致。
- 原因是几何而非刚度：交叉处两股中心线相距 40.4 mm，接触需要 ≤ 2r + d_hat = 10 mm，
  **8 字全程没有任何自接触、没有势垒**，纯弹性应变能一放即释。生成器把环宽固定为 `2·loop_radius`
  且 `loop_radius ≥ peg_radius + 管半径 + d_hat`，只要环宽是常数交叉处永远成不了接触点。
- 同一 spike 记录了 8 字站得住的条件：**平放在桌面上**，重力把一股压在另一股上、摩擦固定形状。

一个不需要机器人就自解的场景不是任务。开口绳桌面版直接取那个站得住的条件作为场景，
同时消掉了闭合带的整个接缝扭转 / 自链数 `Lk` 问题（开口绳没有 `Lk` 约束）。

---

## 2. 几何

`topogym/tasks/entangle/_figure_eight_geometry.py`（纯 numpy），配置块 `task.figure_eight`。

8 字 = 两个「泪滴」在交叉点相接。每个泪滴 = 一个圆 + 从交叉点到圆的两条切线，
两股都以 `half_angle_deg` 离开交叉点，互成 `2·half_angle_deg` 相交。闭合叶是完整泪滴；
开口叶在远端截断，两个绳头相距 `end_gap`。

```
   （机械臂在 -x 侧）                      +x →
   端 0 ──┐                          _________
          \                        /         \
    开口叶  \      交叉点 X       |   闭合叶   |
            /                      \_________/
   端 1 ──┘
```

绳子走向（决定 over 端）：端 0 → 开口叶一侧 → 交叉点（**抬高 `over_lift`，over**）→ 闭合叶整圈 →
交叉点（贴桌面，under）→ 开口叶另一侧 → 端 1。所以**端 0 的那股压在上面**；判定器实测
（`over_at < 0.5`），不信任生成器。

| 键 | 值 | 依据 |
|---|---|---|
| `closed_lobe_radius` | 0.040 | 最小弯曲半径，≫ 管半径 0.004 |
| `open_lobe_radius` | 0.050 | 比闭合叶略大，两绳头有地方错开 |
| `end_gap` | 0.080 | ≥ `rope.free_end_connector.min_clearance` 0.07（夹爪跨距规则，builder 强制） |
| `half_angle_deg` | 45 | 两股互成 90° 交叉，投影最稳 |
| `over_lift` | 0.012 | 同 untangle_continuous：2r + particle_size；IPC 静止间距 2r + d_hat = 10 mm |
| `lift_ramp` | 0.030 | 抬高段坡长；0.020 时样条最小弯曲半径 7.9 mm < 3×管半径，GPU 首跑后放宽 |
| `base_z` | 0.007 | 同 untangle_continuous |
| `center_x` / `center_y` | (0.02, 0) | 绳头落在 x ≈ −0.08、闭合叶顶 x ≈ +0.12，在工作区内（09-03 由 `center` 列表拆成两键） |
| `heading_deg` | 0 | 闭合叶朝 +x（远离机械臂），绳头朝机械臂 |

绳长 ≈ 0.51 m（解析值 511 mm，控制线 515 mm）。`rope.mesh.segment_length` 取 0.005（closed_band spike
在 FEM 下的取值；PBD 的 9 mm 约束来自假自碰撞规则，IPC 下不存在）。

两个绳头各一个刚体插头（与 untangle_continuous 同一零件、同一理由），插头偏航按绳端切线
（`cable_routing.rope_axis_heading` 的做法）；绳走 `declare_follow` × 2 + `follow_link(band=token)`；
**不 `declare_anchor`**，两端自由。

---

## 3. 判定契约（C3）

`topogym/verification/band_untwist_verifier.py`。

- 不变量 `self_crossing_number`：开口折线的带号自交叉计数 `open_self_crossings`。
  段 `i` 只与 `j ≥ i + skip_adjacent + 1` 比较，**没有 `N−1 → 0` 的闭合段**——`closed_band.band_self_crossings`
  是闭合专用，用在开口绳上会凭空多一条落在两绳头之间的幻影段（离线门的「C 形读 0」用例专抓这个）。
- 投影 `top_down_xy`；边界条件「开口绳平放桌面、两端自由、仅靠摩擦」。
- 终态：`crossing_count == 0` **且** 两插头都落回桌面（`end_height_tolerance` 5 mm）——提着绳头时交叉数也是 0，那不是解开。
- 失败标签：`crossing_count ≥ 2` → `wrong_end`。
- 防捷径：投影计数对深度不敏感，8 字压扁（深度 ×0.02）仍读 1（离线门用例）。
- 物理层「向下轻拉验证周长展开」推迟，与 `untangle_continuous_verifier.py:8-14` 的 lift-test 同一处置。

---

## 4. oracle 与对照

`topogym/planning/band_untwist_planner.py`。一步：

1. 从实测交叉的 `over_end` 定抓哪端（`oracle` 抓 over 端，`wrong_end` 抓 under 端）。
2. 抓取点 = 该端插头位姿；抬升 = 场景顶 + max(`lift_clearance`, 交叉点到该端的弧长 + `lift_clearance`)
   ≈ 183 mm——被抓那股从绳头到交叉点整段离开桌面，交叉点才跟着走；只抬绳头是把绳头拖过去。
3. 放置点 = 以交叉点为圆心、过另一绳头的圆上，从离另一绳头 `place_clearance`（0.035）弦长、远离抓取点那一侧的点起，
   沿圆继续外摆（0.5° 步进），直到落点离**留在桌上那股绳的整条折线**（另一绳头到交叉点）≥ `place_clearance`。
   到交叉点的距离与出发时相同，绳既不绷紧也不多余，因此**不需要** swap 那种 reach 夹取。
   只量到插头不够（09-04 角点 c130 的教训，§7.5）：开口叶大、两绳头最近时，那股的弧鼓出插头之外 40 mm，被搬那股会正好压在它上面。
   扫到 150° 仍不满足则抛错；包络内由 `checks()` 的 `place_clearance` 行先拦。
4. 航点 `grasp / carry / cross / place`；交叉数 ≠ 1 时拒绝动作（已解或已绕成 2 都不再动）。

预期读数：`oracle` 终态 0；`wrong_end` 终态 2（under 股被带过 over 股形成第二个交叉，原交叉仍在）。

---

## 5. 文件集

| 文件 | 内容 |
|---|---|
| `topogym/tasks/entangle/_figure_eight_geometry.py` | 几何（纯 numpy） |
| `topogym/tasks/entangle/band_untwist.py` | Layout / Scene / SceneBuilder；`settle_scene` 复用连续版 |
| `topogym/verification/band_untwist_verifier.py` | `open_self_crossings`、`BandUntwistPuzzleState/Evaluator` |
| `topogym/planning/band_untwist_planner.py` | `plan_untwist_move`、`BandUntwistRule`、`make_band_untwist_rule` |
| `topogym/supervision/band_untwist.py` | `crossing_lines` |
| `demos/entangle/band_untwist_physical_pinch_demo.py` | 主 demo（`HandleDragPrimitive` + assisted attachment） |
| `demos/entangle/band_untwist_inspect_demo.py` | 建场景、沉降、静置 300 步逐 25 步读交叉数 |
| `configs/task_configs/band_untwist_topogym_tabletop_v1.yaml`、`configs/band_untwist_{pinch,inspect}.yaml`、`configs/run_configs/band_untwist{,_inspect}.yaml` | 配置 |
| `tests/check_band_untwist_geometry.py` | 离线门（无 GPU）：几何、计数、规划器、变体包络 256 角点 |
| `tests/check_variant_rng.py`（band 段）、`tests/check_variant_corners.py`（`TASKS` 登记） | 拒绝率门、角点门（需要 venv） |
| `bash_scripts/tests/band_untwist_variation_sweep.sh`、`variant_corners_sweep.sh`（band 分支） | GPU sweep：visual / oracle / wrong_end；角点子集 |

登记：`core/taxonomy.py`、`tasks/verification/planning` 三个 `__init__`、`demos/README.md`、四个 bash 注册表、
`configs/GEOMETRY_PARAMETERS_zh.md`、`configs/README.md`、`cli_commands.txt`、`tests/README.md`、`docs/develop/modules/module_{tasks,demos}.md`。

`closed_band.py` / `closed_band_spike.py` 不删不改：`ring_transfer` 在用前者，后者是本文 §1.1 的证据。

---

## 6. 验证

### 6.1 无 GPU（2026-08-27 全过）

- `python tests/check_band_untwist_geometry.py`：几何 6 项、计数 6 项、规划器 19 项全绿。
- `python tests/check_demo_configs.py`：两个新 demo 四项检查无命中。
- `tests/check_configs_compose.py`（项目 venv）：新配置 compose 通过。
- `python topogym/core/taxonomy.py`：`entangle` 一致（`deformation` 一行的不一致早于本任务）。

### 6.2 GPU 门（2026-08-27 三门全过，RTX 4090，Genesis 1.2.1，无头模式）

命令见 `cli_commands.txt` 的 band_untwist 段。实测读数（`runs/band_untwist_{inspect,oracle,wrong_end}.log`）：

- 门 1：`settle_steps=1`（出生即静止）、`gt_match=True`、交叉处 z_gap 11.5 mm（IPC 静止间距 10 mm 之上），
  静置 300 步自交叉恒 1、z_gap 11.4~11.6 mm，无 blow-up。**8 字在桌面上站得住。**
- 门 2a oracle：抓端 0（over 股），弧长 121 mm，抬升 182 mm，`success=True grasped=True`，
  `self_crossings=1->0 ends_on_table=True terminal=True`，无 blow-up，退出码 0。
- 门 2b wrong_end：抓端 1（under 股），`self_crossings=1->2 failure_label=wrong_end terminal=False`，
  两个交叉分别为 over_end=1（新压上去的，z_gap 9.7 mm）与 over_end=0（原交叉，12.1 mm），退出码 1。
  与 docx「翻错一侧变 2」一致。
- 这三次跑的是 `lift_ramp=0.020`（spawn 最小弯曲半径 7.9 mm）；之后已改 0.030，几何门仍过，GPU 未重跑。

| # | 命令 | 判据 |
|---|---|---|
| 1 | `band_untwist_inspect_demo` | 沉降收敛、无 blow-up、`band_untwist_hold` 300 步内 `self_crossings` 恒 1、`gt_match=True`、两插头间距 ≥ 70 mm |
| 2a | `band_untwist_physical_pinch_demo`（oracle） | 终态 `self_crossings=0`、`ends_on_table=True`、退出码 0、`rope_blow_ups` 为 0 |
| 2b | 同上 `run.oracle_mode=wrong_end` | 终态 `self_crossings=2`、`failure_label=wrong_end`、退出码 1 |
| 2c | 同上 `task.rope.fem.rest_shape=straight` | 与 2a 比较终态 O 的形状（spawn 档材料记得 8 字，O 是受力态） |

### 6.3 已知风险与处置

| 风险 | 处置 |
|---|---|
| 抬起时把交叉处的 under 股一起带走（摩擦不够） | 先降 `pinch.lift_clearance`；再升 `rope.fem.friction_mu`；最后把 `figure_eight.center_x` 向机械臂侧移让抬升段更短 |
| 放下后新的擦边交叉（读数抖 0/1） | 加大 `pinch.place_clearance`；`success.crossing_merge_radius` 保持 0.012 |
| 8 字在沉降中张开（spawn 静止态下不应该） | 说明 rest_shape 未生效，查 `tube_morph` retet 后的顶点对应 |
| 抬升 183 mm 内 IK 失败 | 降 `lift_clearance`，或改小 `open_lobe_radius` 缩短交叉点到绳头的弧长 |

---

## 7. 变体轴与派生（2026-09-03，变体计划 §6.2 第 4 步）

按 linkbar / diverter / gate_cage_ball 的范式部署：轴在 task yaml 末尾的 `variation:` 块声明，随机数只在
`generation/layout_randomization.py` 抽，Layout 只接收采好的值（`BandUntwistLayout.seed` 保留为 run seed，不再是「未来的布局种子」）。

### 7.1 轴

| 类 | 叶子 | 抽法 | 说明 |
|---|---|---|---|
| A | `figure_eight.over_end` | Cat{0, 1} | **防捷径离散轴**：哪一端的绳压在上面。实现：`figure_eight_local_points` 末尾把局部 b 分量取反并把点序（与 `over_mask`）反转。两个绳头位置与 `over_end=0` 完全相同，只是压在上面的换成另一股；judge 实测 `over_at > 0.5` → 1，planner 只读实测值，`matches_spawn_ground_truth` 比实测与 `layout.over_end`。画面里除了交叉处本身，没有别的线索说该抓哪头 |
| B | `figure_eight.heading_deg` | U[−30, 30] | 8 字轴线朝向 |
| B | `figure_eight.center_x` / `center_y` | U[−0.01, 0.05] / U[−0.03, 0.03] | 交叉点位置。原 `center: [x, y]` 拆成两个标量键：随机化器按点路径抽样，不支持列表元素 |
| B | `figure_eight.half_angle_deg` | U[30, 60] | 两股离开交叉点的半角，交叉夹角 = 2× |
| B | `figure_eight.closed_lobe_radius` | U[0.032, 0.055] | 闭合叶半径 |
| B | `figure_eight.open_lobe_radius` | U[0.040, 0.065] | 开口叶半径，决定交叉点到绳头弧长即抬升高度（难度候选） |
| B→C | `figure_eight.end_frac` → `figure_eight.end_gap` | **派生** | `[min_clearance 0.070, end_gap_max_ratio 0.95 × 2·open_lobe_radius]`（`_figure_eight_geometry.end_gap_from_frac`）；r_o=0.040 时区间 [0.070, 0.076]。`min_clearance` 原是代码默认值，现在显式写在 `rope.free_end_connector` |
| D | `over_lift`、`base_z`、`lift_ramp`、`pinch.*`、`rope.fem.*` | 固定 | `lift_ramp` 0.030 在半角大、闭合叶小的角上被 `0.8·min(t_c, t_o)` 静默截短到 14.8 mm，`corner_radius` 行（3D 外接圆，含鼓包三点）把它判出来：最紧 15.1 mm ≥ 12 mm |

### 7.2 `checks()` 八行（09-04 加落点两行）

判据的纯函数在 `_figure_eight_geometry.figure_eight_checks`（只接 spec + 标量，离线门按路径加载保持 Genesis-free）；
`BandUntwistLayout.checks()` / `validate()` 委托它，builder 建场景前 `validate()`；模块级 `derive_task_cfg` / `validate_task_cfg` 钩子在 `band_untwist.py`。
校验只拿得到未解析的 task 配置，所以 `figure_eight.tube_radius` 是 `rope.radius`（`${prefabs…}` 插值）的字面量副本，
`workspace:` 段是 `manipulation_space.workspace` 的副本；builder 与离线门各断言一处相等。

| 行 | 读数 | 门 | 默认 | 256 角点最紧 |
|---|---|---|---|---|
| `end_separation` | 两绳头 xy 距离 | ≥ `min_clearance` 0.070 | 0.080 | 0.070（`end_frac=0`，构造取等） |
| `end_gap_ratio` | `end_gap / (2·open_lobe_radius)` | ≤ 0.95 | 0.80 | 0.95（`end_frac=1`，构造取等） |
| `corner_radius` | 控制多边形最小转角外接圆半径（3D，含鼓包） | ≥ 3·`tube_radius` 0.012 | 0.040 | 0.0151（半角 60°、闭合叶 0.032） |
| `footprint` | 控制点到工作区 x/y 边界最小距离 | ≥ `workspace.margin` 0.040（≥ `place_clearance`，落点由此在工作区内） | 0.130 | 0.0497（`center_x` 0.05、闭合叶 0.055、朝向 −30°） |
| `lift_height` | `base_z + over_lift + r + open_half + lift_clearance`，`open_half = t_o + r_o·(π − cut − φ)`（与 planner 公式同构；planner 用沉降后实测的交叉位置，seed 0–9 实测抬升在预测的 −24 / +26 mm 内，半角大的格偏高，**是估计不是上界**） | ≤ `workspace.z_max` 0.40 | 0.184（GPU 实测 182 mm） | 0.309（开口叶 0.065、半角 30°；距 0.40 还有 91 mm，盖得住偏差） |
| `bottom_clearance` | `base_z − tube_radius` | ≥ 0 | 0.003 | 常量 |
| `place_clearance`（09-04） | 用控制点重演 planner 落点（`predicted_place`，同一个 `place_beside`，交叉点取 `spec.center`），落点到留桌那股折线的距离 | ≥ `pinch.place_clearance` 0.035 | 0.035 | 0.0351（扫描构造取等；只有扫描耗尽才失败） |
| `lay_down_clearance`（09-04） | 被搬那股离桌点（交叉点后沿绳 `lift_clearance`，在闭合叶上）到落点的直线，与留桌那股折线的最小距离 | ≥ 2·`tube_radius` 0.008 | 0.030 | 0.0150（半角 60°、开口叶 0.065、`end_frac=0`；改前这一组是 0.0001） |

### 7.3 离线实测（2026-09-03）

| 门 | 结果 |
|---|---|
| `check_band_untwist_geometry.py`（无 venv） | PASS：原三段全过；镜像格实测 `over_end=1` 且两绳头位置与未镜像相同；256 角点六行全过、恰一个交叉且实测 over 端 = spec；负例（开口叶 0.036 区间闭合、`center_x` 0.16 足迹拒）均拒 |
| `check_variant_rng.py`（七段） | PASS：band 段 1000 seed `over_end` 0/1 = 479/521，最大预测抬升 0.298 m，首抽拒绝率 0.000 |
| `check_variant_corners.py --task band_untwist` | PASS：256 角点全部可行、Hydra compose 读数一致（脚本改为不解析插值地遍历叶子） |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |

### 7.4 GPU 实测（4090，Genesis 1.2.1，无头；`runs/band_untwist_variation/20260903_155802_{seeds,wrong_end}/`）

`bash_scripts/tests/band_untwist_variation_sweep.sh visual oracle`（seed 0–9）与 `wrong_end`（seed 0–2）：

| seed | over_end | heading | cx / cy | half | r_c / r_o | end_gap | 预测抬升 | 实测弧长 / 抬升 | oracle | wrong_end |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0 | −19.6 | −0.003 / +0.008 | 37.1 | 0.043 / 0.060 | 0.102 | 0.229 | 147 / 208 mm | PASS | wrong_end |
| 1 | 1 | +8.5 | +0.016 / −0.002 | 38.4 | 0.037 / 0.061 | 0.088 | 0.242 | 164 / 225 mm | PASS（抓端 1） | wrong_end |
| 2 | 1 | −20.7 | +0.007 / +0.022 | 41.2 | 0.054 / 0.056 | 0.106 | 0.193 | 121 / 183 mm | PASS（抓端 1） | wrong_end |
| 3 | 1 | +2.5 | +0.037 / +0.023 | 56.3 | 0.035 / 0.053 | 0.072 | 0.173 | 133 / 193 mm | PASS（抓端 1） | |
| 4 | 1 | −4.5 | −0.006 / −0.025 | 37.2 | 0.045 / 0.056 | 0.086 | 0.229 | 148 / 208 mm | PASS（抓端 1） | |
| 5 | 0 | +8.5 | +0.024 / +0.024 | 55.9 | 0.052 / 0.047 | 0.079 | 0.148 | 102 / 163 mm | PASS | |
| 6 | 0 | +23.6 | −0.006 / −0.004 | 32.8 | 0.049 / 0.041 | 0.074 | 0.188 | 104 / 164 mm | PASS | |
| 7 | 1 | −0.3 | +0.000 / −0.027 | 59.0 | 0.049 / 0.064 | 0.087 | 0.190 | 156 / 216 mm | PASS（抓端 1） | |
| 8 | 0 | −15.7 | +0.027 / +0.025 | 40.3 | 0.040 / 0.063 | 0.081 | 0.246 | 171 / 233 mm | PASS | |
| 9 | 1 | −12.2 | −0.003 / +0.004 | 38.1 | 0.052 / 0.048 | 0.089 | 0.184 | 109 / 170 mm | PASS（抓端 1） | |

- oracle **10/10**：每格沉降后 `gt_match=True`（实测交叉数 1、over 端 = spec），`self_crossings 1→0`、`ends_on_table=True`、无 blow-up、无工作区顶警告；每格 265–311 s。
- **镜像轴生效**：`over_end=1` 的 6 格 planner 全部抓端 1（它只读实测 over 端），并解开；`over_end=0` 的 4 格抓端 0。
- wrong_end 3/3 判 `failure_label=wrong_end`（1 → 2），每格 ≈ 5 min（原估 13 min 是首次 GPU 门的读数，含编译）。
- visual 十格首帧可分（`visual_s*.mp4`，`static_only` 只步进 20 步录帧）。
- 预测抬升 vs 实测：−24 mm（seed 6）到 +26 mm（seed 7，半角 59°）。planner 用沉降后实测中心线上的交叉位置，半角大时交叉沿绳的位置比控制多边形的解析值靠后。
  预测只作包络校验用（最大 0.309，距 0.40 还有 91 mm），不作为上界；docstring 已改。

角点子集（`variant_corners_sweep.sh band_untwist oracle`，`CORNERS="c002 c130 c008 c136 c036 c164"`，`runs/band_untwist_corners/20260903_155802_subset/`）：**5/6**。

| 角点 | 取的极值 | over_end | 实测抬升 | 结果 |
|---|---|---|---|---|
| c002 | 抬升最高（r_o 0.065、半角 30°、朝向 −30°、end_gap 0.070） | 0 | 266 mm | PASS，1→0 |
| c130 | 同上镜像 | 1 | 272 mm | **FAIL**：抓端 1 正确、抬起成功，落下后 1→2 |
| c008 / c136 | 转角最紧（半角 60°、闭合叶 0.032） | 0 / 1 | 149 / 151 mm | PASS |
| c036 / c164 | 足迹最贴边（cx 0.05、闭合叶 0.055、朝向 −30°） | 0 / 1 | 168 / 168 mm | PASS |

c130 与 c002 的两个插头位置完全相同（镜像只换上下股，`connector_probe` 逐 mm 一致），差别只在抓哪头、落哪边：c002 抓端 0 落在 (−0.196, −0.002)，
c130 抓端 1 落在 (−0.127, +0.117)（世界系），后者压出了第二个交叉。抓取与抬升都成功（`grasped=True`、无 blow-up、无工作区顶警告），
问题在 planner 的落点规则（`place_beside`：以交叉点为圆心过另一绳头的圆上、离另一绳头 `place_clearance` 的远侧点）在这一角放下的那段绳跨过了另一股。
处置待定（用户决定）：改 planner 落点规则（按剩余折线选不跨越的一侧 / 半径），或收窄 `open_lobe_radius` 上限 / `heading_deg` 区间；不加重试。
补充诊断的命令（09-04 已跑完，结果见 §7.5）：

```bash
# 新交叉的位置与 over 端（verbose 打印每个 self-crossing）
python -B -m demos.entangle.band_untwist_physical_pinch_demo run.randomize_layout=false run.verbose=true run.oracle_mode=oracle \
  $(awk -F'\t' '$2=="c130"{print $4}' runs/band_untwist_corners/20260903_155802_subset/corners.tsv)
# 同一角只换绳头间距（c131：end_frac=1）或开口叶（c128：r_o=0.040）
CORNERS="c131 c128" bash bash_scripts/tests/variant_corners_sweep.sh band_untwist oracle
```

### 7.5 c130 诊断与落点规则修正（2026-09-04）

复跑与补跑（`runs/band_untwist_corners/20260904_c130diag/`、`20260904_c130diag_worst/`，verbose 日志在会话暂存目录）：

| 格 | 取的极值 | 结果 |
|---|---|---|
| c130（verbose 复跑） | 开口叶 0.065、半角 30°、`end_frac=0`、镜像 | **FAIL 复现**，1→2。三段终点误差 ≤ 2 mm，落点实际 (−0.122, +0.118) 对命令 (−0.127, +0.117)：机械臂没问题。放下后两个交叉：新交叉在端 0 附近（被搬那股末端 4 cm 压在端 0 那股末端上，over_at 0.93 / under_at 0.08），原交叉没解掉、被拖了 8 cm |
| c002（verbose 复跑） | 同上不镜像 | PASS，1→0（确定性复现） |
| c131 / c003 | 同 c130 / c002，只把 `end_frac` 0→1（绳头间距 0.070→0.124） | PASS |
| c128 | 同 c130，只把开口叶 0.065→0.040 | PASS |
| c106 / c234 | 半角 60°、开口叶 0.065、`end_frac=0`（落点余量最差的一组） | PASS |

机制（纯 numpy 在 256 角点上复算）：落点规则 `place_beside` 只量到另一**插头**（弦长 35 mm），不看那股绳的弧。
开口叶 0.065 且绳头间距取下限 0.070 时，留桌那股的开口叶弧鼓出「交叉点→插头」弦之外 40 mm > 35 mm，
落点离那股只剩 18 mm（半角 60° 组 15 mm），被搬那股放下时沿直线铺开的那段离那股仅 **0.1 mm**，绳压在绳上，往哪边滑由动力学决定。
这个余量只由 `half_angle_deg`、`open_lobe_radius`、`end_frac` 决定，朝向 / 中心 / 闭合叶半径 / `over_end` 的影响为零；
其余 6 组（192 格）铺绳直线余量 16–27 mm，GPU 已试的 7 格全过。零余量那 64 格试了 4 格：3 过 1 败——c130 不是参数特殊，是运气。
c002 / c130 孪生对可见的一处世界系差异：c002 手指合在插头法兰上（张开 30 mm，插头在指间转了约 40°），c130 合在抓取柱上（20 mm）；未验证是否是决定因素。

处置（用户定：改落点规则，不收包络，不改判定器）：
- `place_beside` 加 `stay_strand` 参数：从原远侧候选点起沿圆继续外摆（0.5° 步进），直到落点离留桌那股整条折线 ≥ `place_clearance`；半径不变；150° 内无解则抛错。`plan_untwist_move` 用实测折线与交叉的 `over_at / under_at` 切出留桌那股（`stay_strand_xy`）。
- `checks()` 加 `place_clearance` / `lay_down_clearance` 两行（§7.2），`predicted_place` 用控制点重演同一个 `place_beside`；离线门断言 planner 在 dense 折线上的落点与重演相差 < 5 mm（默认布局 0.0 mm）。
- 预演（256 角点）：最紧组外摆角从 10.7° 增到 31°，铺绳直线余量 0.1 → 15 mm（半角 30° 组 18.8 mm），两插头相距 63–72 mm，落点离工作区边界 ≥ 52 mm。默认布局落点离另一插头 35 → 54 mm。
- 没做：同时约束铺绳直线（会把最紧组外摆到 64°、插头相距 142 mm）；若回归在零余量组仍有失败再加，预演数据在 09-04 会话。

离线：`check_band_untwist_geometry.py`（八行 256 角点全过、planner 与重演一致、新负例 `place_clearance=0.30` 抛错且该行判负、鼓包折线把落点推远）、
`check_variant_corners.py --task band_untwist` 256/256、`check_variant_rng.py` band 段拒绝率 0.000、配置组合与 demo 配置全 PASS。

GPU 回归（`runs/band_untwist_corners/20260904_placefix/`、`runs/band_untwist_variation/20260904_placefix_{seeds,wrong_end}/`）：待填。

