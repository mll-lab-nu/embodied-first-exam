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
| `lift_ramp` | 0.020 | 抬高段坡长 |
| `base_z` | 0.007 | 同 untangle_continuous |
| `center` | (0.02, 0) | 绳头落在 x ≈ −0.08、闭合叶顶 x ≈ +0.12，在工作区内 |
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
3. 放置点 = 以交叉点为圆心、过另一绳头的圆上，离另一绳头 `place_clearance`（0.035）弦长、
   在远离抓取点的那一侧。到交叉点的距离与出发时相同，绳既不绷紧也不多余，因此**不需要** swap 那种 reach 夹取。
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
| `tests/check_band_untwist_geometry.py` | 离线门（无 GPU） |

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

### 6.2 GPU 门（待跑，按顺序，前一项不过不跑后一项）

命令见 `cli_commands.txt` 的 band_untwist 段。

| # | 命令 | 判据 |
|---|---|---|
| 1 | `band_untwist_inspect_demo` | 沉降收敛、无 blow-up、`band_untwist_hold` 300 步内 `self_crossings` 恒 1、`gt_match=True`、两插头间距 ≥ 70 mm |
| 2a | `band_untwist_physical_pinch_demo`（oracle） | 终态 `self_crossings=0`、`ends_on_table=True`、退出码 0、`rope_blow_ups` 为 0 |
| 2b | 同上 `run.oracle_mode=wrong_end` | 终态 `self_crossings=2`、`failure_label=wrong_end`、退出码 1 |
| 2c | 同上 `task.rope.fem.rest_shape=straight` | 与 2a 比较终态 O 的形状（spawn 档材料记得 8 字，O 是受力态） |

### 6.3 已知风险与处置

| 风险 | 处置 |
|---|---|
| 抬起时把交叉处的 under 股一起带走（摩擦不够） | 先降 `pinch.lift_clearance`；再升 `rope.fem.friction_mu`；最后把 `figure_eight.center` 向机械臂侧移让抬升段更短 |
| 放下后新的擦边交叉（读数抖 0/1） | 加大 `pinch.place_clearance`；`success.crossing_merge_radius` 保持 0.012 |
| 8 字在沉降中张开（spawn 静止态下不应该） | 说明 rest_shape 未生效，查 `tube_morph` retet 后的顶点对应 |
| 抬升 183 mm 内 IK 失败 | 降 `lift_clearance`，或改小 `open_lobe_radius` 缩短交叉点到绳头的弧长 |
