# 已部署任务的变体参数与难度分布方案

> 日期：2026-08-26
> 范围：`runs/videos/` 下 11 个已录制任务
> 上游：`../framework/task_taxonomy_zh.md` §4.4（C4 类随机化为准入条件）、
> `topogym/generation/layout_randomization.py`（现有随机化接缝）、
> `bash_scripts/tests/stability_sweep.sh`（SEED × DIFFICULTY 测量器）

---

## 0. 本文回答的三个问题

1. 每个任务哪些参数可以按种子变化，哪些不能变，变化范围由什么约束决定。
2. 场景几何简单的情况下，如何让不同种子产生实质不同的实例。
3. 难度档位如何绑定到**分布**而非取值组合，以及如何验证。

第 1 节是现状，第 2 节是通用规则，第 3 节是逐任务表，第 4 节是测试与实施顺序。

### 0.1 录像目录与 task_id 对照


| `runs/videos/` 目录          | task_id                    | 类别           | 任务配置                                                |
| -------------------------- | -------------------------- | ------------ | --------------------------------------------------- |
| `rope_winding`             | `rope_winding`             | routing      | `rope_winding_topogym_tabletop_v1.yaml`             |
| `transfer-rope-ring`       | `ring_transfer`            | routing      | `ring_transfer_topogym_tabletop_v1.yaml`            |
| `bar_through_hole`         | `bar_through_hole`         | routing      | `bar_through_hole_topogym_tabletop_v1.yaml`         |
| `switch_rope_side`         | `swap_crossing_sign`       | entangle     | `swap_crossing_sign_topogym_tabletop_v1.yaml`       |
| `unlink_c_ring`            | `unlink_c_ring`            | entangle     | `unlink_c_ring_topogym_tabletop_v1.yaml`            |
| `close_gate`               | `gate_cage_ball`           | connectivity | `gate_cage_ball_topogym_tabletop_v1.yaml`           |
| `diverter_route_ball`      | `diverter_route_ball`      | connectivity | `diverter_route_ball_topogym_tabletop_v1.yaml`      |
| `linkbar_rotate_to_zone`   | `linkbar_rotate_to_zone`   | connectivity | `linkbar_rotate_to_zone_topogym_tabletop_v1.yaml`   |
| `cloth_fold`               | `cloth_fold`               | deformation  | `cloth_fold_topogym_tabletop_v1.yaml`               |
| `cloth_unpleat`            | `cloth_unpleat`            | deformation  | `cloth_unpleat_topogym_tabletop_v1.yaml`            |
| `cloth_unroll`             | `cloth_unroll`             | deformation  | `cloth_unroll_topogym_tabletop_v1.yaml`             |


---



## 1. 现状


| 项             | 状态                                                                                                                                                                                                                                                    |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 随机化接缝         | `layout_randomization.py::randomize_task_cfg(cfg, task_id, seed, difficulty)`：深拷贝 `cfg.task`、按注册表施加有界抖动、未注册任务原样返回。四种 directive 全部是连续量：`_AbsXYJitter` / `_FracJitter` / `_EachScalarJitter` / `_EachAbsXYJitter`。                                      |
| 已注册任务         | `untangle` / `cable_routing` / `stacked_plate` / `peeling`。**本文 11 个任务均未注册。**                                                                                                                                                                         |
| 难度实现          | `_DIFFICULTY_SCALE = {easy: 0.5, smoke: 0.5, default: 1.0, hard: 1.8}`，作用为全部抖动半宽的统一倍率。                                                                                                                                                                |
| 种子对场景的作用      | 仅 `swap_crossing_sign` 的 `run.seed` 进入 braid 采样（只决定交叉符号，两种实例）。其余 10 个任务 seed 只是 `EpisodeKey` 身份字段。                                                                                                                                                    |
| run 配置键       | `randomize_layout` / `difficulty` 只存在于 cable_routing / stacked_plate / untangle 的 run 配置；11 个任务的 run 配置无此键。                                                                                                                                           |
| 测量器           | `stability_sweep.sh` 任务表含 untangle / untangle_continuous / cable_routing / stacked_plate / unlink_c_ring；其余 10 个未登记。                                                                                                                                  |
| 离线几何门         | rope_winding / ring_transfer / unlink_c_ring / cloth_fold / cloth_unpleat / cloth_unroll 有 `tests/check_*_geometry.py`；linkbar 有 `tests/check_linkbar_zone_geometry.py` + `LinkbarRotateLayout.validate()`；diverter 有 `check_pivot_clearance()`；gate_cage_ball 有运行期可解性检查；bar_through_hole 无校验器。 |
| episode split | `configs/episode_splits/` 仅 cable_routing / swap / untangle。                                                                                                                                                                                          |
| oracle 对配置的依赖 | 11 个任务的 oracle 路点均由配置或实时状态推导，无手写绝对路点。例外：`bar_through_hole.primitive.*_z` 与 `gate_cage_ball.motion.*_z` 是手工推导的绝对高度，不随布局重算。                                                                                                                             |


---



## 2. 通用规则



### 2.1 参数分四类

每个任务的配置叶子按下列四类划分，第 3 节逐任务给出归属。


| 类别    | 定义                                          | 采样方式           |
| ----- | ------------------------------------------- | -------------- |
| A 实例轴 | 离散取值，改变正确动作本身（哪根柱、哪一侧、绕几圈、交叉符号）。            | Categorical 分布 |
| B 布局轴 | 连续几何量，oracle 读回后自适应，改变动作的位置与幅度。             | 有界连续分布         |
| C 派生量 | 由 A/B 决定、必须随之重算的量（绳长、步数、随动高度）。              | 重解，不采样         |
| D 固定量 | 已有实测失败记录或求解器约束的参数（粒径、d_hat、步长、摩擦、substeps）。 | 不变             |


物理参数（摩擦、刚度、d_hat）全部归 D 类。各任务配置注释均记录了这些值的实测来源，改动会改变物理稳定性而非任务难度。

### 2.2 同一种子如何产生多样实例

场景几何简单时，多样性主要来自 A 类而非 B 类。原则：**每个任务至少一条 A 类轴**，使脚本化策略（固定方向、最近目标、固定延时）的期望成功率被固定在随机水平；B 类轴提供连续覆盖，使策略无法记忆绝对坐标。

采样流程（每个 episode）：

1. `rng = np.random.SeedSequence(seed)`；每条轴用 `spawn` 出的独立子流，子流索引由轴名的稳定哈希决定。新增一条轴不改变已有轴在同一种子下的取值。
2. 先采 A 类，再采 B 类，再重算 C 类。
3. 调用该任务的可行性校验（第 3 节「校验」列）；不通过则整体重采，最多 N 次（建议 20），超过则报错并记录该难度档的拒绝率。
4. 采样结果写入 `TaskVariant.parameters`（`episode_spec.py`），H5 `setup/` 已有 `difficulty` 字段。

视觉轴（颜色、纹理 `texture.seed`、装饰件）可以单独随机，与物理层无关，本文不展开；按 `visual-realism-workstream` 的「装饰与碰撞分离」规则处理。

### 2.3 难度绑定到分布

定义：难度档 $d \in \text{easy}, \text{default}, \text{hard}$ 为一个映射，把每条轴 $a$ 映射到一个分布 $P_d(a)$。一个 episode 是 $(d, \text{seed})$ 的函数：seed 决定从 $P_d$ 中抽哪个样本。


| 轴类型  | 分布族                                      | 难度改变的参数                             |
| ---- | ---------------------------------------- | ----------------------------------- |
| B 连续 | 截断均匀 $U[c - w_d, c + w_d]$，或以基线值为中心的截断正态 | 半宽 $w_d$、中心 $c_d$（允许随难度平移，如孔径中心值下移） |
| A 离散 | Categorical$(p_d)$                       | 各取值概率（如 turns=3 的概率随难度上升）           |


约束：

- **支撑集单调**：$\text{supp}P_{\text{easy}} \subseteq \text{supp}P_{\text{default}} \subseteq \text{supp}P_{\text{hard}}$，或分布中心沿一个明确的「裕度统计量」单调（例如期望间隙递减）。第 3 节每个任务指明该统计量。
- **难度不写成取值表**：不存在「hard = (孔径 0.028, 长度 0.22)」这类固定组合；hard 只声明分布参数。
- **范围来自物理量程，不从基线分数反推**（`run_configs/gate_cage_ball_gate.yaml` 已记录该原则）。
- 现有 `_DIFFICULTY_SCALE` 是本定义的特例（$c_d = c$，$w_d = k_d \cdot w$）。实施时把它推广为每条 directive 可声明 per-difficulty 的 $(c_d, w_d)$ 或 $p_d$；未声明时退化为倍率。

难度统计量的验证方式见 §4.1：对每档抽 1000 个样本，检查统计量的均值随档位单调、拒绝率低于阈值。

### 2.4 需要新增的 directive


| directive                           | 用途                     | 使用任务                                                                 |
| ----------------------------------- | ---------------------- | -------------------------------------------------------------------- |
| `_ScalarJitter(path, lo_d, hi_d)`   | 单个标量叶子的截断均匀采样，边界按难度声明  | 多数任务                                                                 |
| `_ChoiceJitter(path, choices, p_d)` | 离散实例轴                  | diverter / linkbar / rope_winding / ring_transfer / 布料 material_axis |
| `_DerivedSolve(fn)`                 | 采样后调用任务模块的重算函数写回 C 类叶子 | rope_winding（sweep_deg）、cradle 跟随、post 对称                            |
| `_Validate(fn, max_retry)`          | 采样后调用可行性校验，失败重采        | 全部                                                                   |


`_ScalarJitter` 与 `_ChoiceJitter` 的需求已在 `diverter_route_ball_zh.md` §6.2 与 `linkbar_rotate_to_zone_zh.md` §5 提出，本文合并。

---



## 3. 逐任务方案

表内「难度统计量」指 §2.3 的单调量；「校验」指采样后调用的可行性函数。范围单位：m / deg，任务坐标系。`c` 为当前配置值。

### 3.1 rope_winding（docx 2.4）


| 类   | 叶子                                                                                                                                 | 当前值             | easy                                                     | default                  | hard              | 说明                                                            |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------- | -------------------------------------------------------- | ------------------------ | ----------------- | ------------------------------------------------------------- |
| A   | `winding.turns`                                                                                                                    | 2               | Cat{1:0.7, 2:0.3}                                        | Cat{1:0.2, 2:0.6, 3:0.2} | Cat{2:0.4, 3:0.6} | 主难度轴；3 圈出生足迹 x[−0.277,0.156] 已超出 workspace 盒，受板面 0.70×0.80 约束 |
| A   | `winding.direction`                                                                                                                | ccw             | Cat{ccw:0.5, cw:0.5}（三档相同）                               |                          |                   | 指令轴；cw 同时是 contrast pair                                      |
| B   | `fixtures.POST.pos[x,y]`                                                                                                           | (0.020, 0.020)  | ±0.015                                                   | ±0.025                   | ±0.040            |                                                               |
| B   | `fixtures.C.pos[x,y]`                                                                                                              | (0.150, 0.120)  | ±0.010                                                   | ±0.020                   | ±0.030            | 落点                                                            |
| B   | `fixtures.S.pos[x,y]`                                                                                                              | (−0.150, 0.100) | ±0.010                                                   | ±0.020                   | ±0.030            | 锚点                                                            |
| B   | `winding.climb_per_turn`                                                                                                           | 0.014           | [0.013, 0.016]                                           | [0.011, 0.016]           | [0.010, 0.016]    | 下限 `2·rope.radius = 0.008` 实测为零间隙失败点，故 ≥ 0.010                |
| B   | `winding.wind_z_start`                                                                                                             | 0.045           | ±0.005                                                   | ±0.008                   | ±0.010            | 与 turns·climb 共同受 post 顶 0.105 − 0.010 封顶                     |
| C   | `rope.spawn_arc.sweep_deg`                                                                                                         | 200             | 按 slack ∈ [0.05, 0.15]、目标 0.10 重解（`planner.taut_demand`） |                          |                   | 现有 turns→sweep 表：1/2/3 → 155/200/230                          |
| D   | `winding.wind_radius`（≥0.140）、`rope.z` = `flange_radius`、`contact_d_hat`、`rope.mesh.*`、`safety_max_contact_nodes`、`POST.collision` |                 |                                                          |                          |                   | 各有实测事故记录                                                      |


- 难度统计量：期望圈数；次要：POST 到 C 的距离。
- 校验：`tests/check_rope_winding_geometry.py` 全套不等式（slack 带、螺旋在柱顶下、圈间净空、插头轴线对齐）。
- 前置代码：`_DerivedSolve` 调 `planner` 的 taut_demand 反解 sweep_deg；run 配置补 `randomize_layout`/`difficulty`。
- 镜像任务 `rope_unwinding`（docx 2.5，2026-08-26 落地）的主难度轴是 `winding.start_turns`（出生时柱上的圈数，1/2/3），同一张表的 B/D 类叶子照搬；`rope.spawn_arc.sweep_deg = −130` 三档通用（slack 8.5%–9.2%），不需要 `_DerivedSolve`；校验 `tests/check_rope_unwinding_geometry.py --start-turns N`。



### 3.2 ring_transfer（docx 2.6）


| 类   | 叶子                                                                                                             | 当前值        | easy                                                     | default        | hard           | 说明                                            |
| --- | -------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------- | -------------- | -------------- | --------------------------------------------- |
| A   | `ring.enclosure` / `goal.enclosure`                                                                            | [A] / [B]  | Cat{A→B:0.5, B→A:0.5}（三档相同）                              |                |                | 指令轴；两柱几何相同，交换即可，oracle 读 `layout.crossings()` |
| B   | 柱对中点 xy（同时平移 A、B）                                                                                              | (0.010, 0) | ±0.010                                                   | ±0.020         | ±0.030         | 单柱独立抖动会改变柱距                                   |
| B   | 柱距                                                                                                             | B−A        |                                                          | 0.220          | [0.20, 0.24]   | [0.19, 0.26]                                  |
| B   | 柱对朝向角                                                                                                          | 0°         | ±10°                                                     | ±20°           | ±30°           | 需把 `ring.long_axis` 同步旋转（C 类）                 |
| B   | `posts[*].radius`                                                                                              | 0.016      | [0.015, 0.018]                                           | [0.014, 0.020] | [0.013, 0.022] | 上限受 `loop_radius ≥ r + tube + d_hat`          |
| B   | `posts[*].head_radius − radius`                                                                                | 0.010      | ≥0.008（`≥ 2·tube_radius`）                                |                |                |                                               |
| C   | `ring.long_axis`、`carry.hang_depth`                                                                            |            | 前者随柱对朝向旋转；后者是实测值（0.14 对 perimeter 0.46），perimeter 不动则不重算 |                |                |                                               |
| D   | `ring.perimeter`、`ring.loop_radius`、`grasp.grasp_qpos`、`rope.fem.*`、`robot_rope_contact`、`carry.hang_bottom_z` |            |                                                          |                |                | perimeter 变化要求重测 hang_depth，第一阶段固定            |


- 难度统计量：柱距与柱半径（B 柱套入所需张开宽度 `2(r_post + 2 r_tube + d_hat)`）。
- 校验：`tests/check_ring_transfer_geometry.py`（环净空、手掌与挡头净空、悬挂股避开挡头、workspace）。
- 前置代码：run 配置无 `seed`/`randomize_layout`；demo 未建 EpisodeSpec。`posts` 是列表，需要「成对平移/旋转」的 directive。



### 3.3 bar_through_hole（docx 2.3 变体）


| 类   | 叶子                                                                                                                                          | 当前值         | easy                 | default        | hard           | 说明                                                                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | -------------------- | -------------- | -------------- | ---------------------------------------------------------------------- |
| B   | `aperture.across_flats`                                                                                                                     | 0.032       | [0.034, 0.038]       | [0.030, 0.036] | [0.027, 0.032] | 单边净空 = (across_flats − 0.018)/2；实测 IK 跟踪误差 7.5 mm，hard 下限净空 4.5 mm 需实测 |
| B   | `bar.rest_pos[x,y]`                                                                                                                         | (−0.050, 0) | ±0.010               | ±0.020         | ±0.030         | `cradles.near_a.x`/`near_b.x` 随之平移（C）                                  |
| B   | `panel.x`                                                                                                                                   | 0.130       | ±0.010               | ±0.020         | ±0.030         | `cradles.far.x` 随之平移（C）；EE 全程需在 panel.x 一侧                             |
| B   | `bar.length`                                                                                                                                | 0.200       | [0.19, 0.21]         | [0.18, 0.22]   | [0.17, 0.23]   | 影响 `max_align_tilt_deg` 的几何上限                                          |
| B   | `bar.grasp_offset`                                                                                                                          | 0.075       | ±0.005               | ±0.010         | ±0.015         |                                                                        |
| C   | `cradles.near_a.x`、`near_b.x`、`far.x`                                                                                                       |             | 与 bar / panel 保持当前偏移 |                |                |                                                                        |
| D   | `aperture.center_z`、`bar.rest_pos[z]`、`cradles.*.seat_axis_z`、`panel.top_z`（≤0.1608，余量 11 mm）、`cradles.*.jaw_width`（≤0.023）、`primitive.*_z` |             |                      |                |                | `primitive.*_z` 是手工绝对高度                                                |


- 难度统计量：期望单边净空。
- 校验：无现成校验器；需新增 `BarThroughHoleLayout.validate()`：净空 > 0、cradle 顺序、EE 位置 < panel.x、`primitive.*_z` 与 `aperture.center_z` 一致。
- 前置代码：把 `primitive.insert_z / seat_z / grasp_z` 改为由 `aperture.center_z`、`bar.rest_pos[z]` 推导（diverter 与 linkbar 的 `knob_grasp_world()` 是先例），否则 z 轴全部归 D。



### 3.4 swap_crossing_sign（docx 3.2）


| 类   | 叶子                                                                                                                                | 当前值     | easy                    | default        | hard           | 说明                                                       |
| --- | --------------------------------------------------------------------------------------------------------------------------------- | ------- | ----------------------- | -------------- | -------------- | -------------------------------------------------------- |
| A   | 交叉符号（braid 字）                                                                                                                     | seed 决定 | Cat{+:0.5, −:0.5}（三档相同） |                |                | 现有机制，`generation/braid.py:153-162`                       |
| B   | 交叉位置 `frac ∈ braid_span`                                                                                                          | 固定中点    | [0.45, 0.55]            | [0.35, 0.65]   | [0.25, 0.75]   | 需改 `braid.py:225`（length=1 时取中点）为按 seed 采样               |
| B   | `braid.channel_spacing`                                                                                                           | 0.085   | [0.080, 0.095]          | [0.070, 0.095] | [0.060, 0.095] | 上限 ≈0.101（`crossing_window ≥ 0.6·spacing`）；越小两绳越近        |
| B   | `braid.center_y`                                                                                                                  | 0       | ±0.020                  | ±0.030         | ±0.040         |                                                          |
| B   | `braid.x_end`                                                                                                                     | 0.200   | [0.19, 0.21]            | [0.17, 0.22]   | [0.16, 0.22]   | 自由端插头须留夹爪级净空                                             |
| D   | `braid.length`（=1）、`n_strands`、`over_lift`（=0.012）、`base_z`、`rope.mesh.segment_length`（0.009）、`rope.elastic.*_friction`、`pinch.*` |         |                         |                |                | `pinch.tail_clearance = −0.030` 是进行中的 H7 实验，随机化不应叠加在未定值上 |


- 难度统计量：期望 channel_spacing（间距小则两绳干扰增大、`separation_threshold` 0.016 更难达到）。
- 校验：`braid.verify_braid_spec`（已在建场景时调用）+ `tests/check_swap_crossing_sign_planner.py`。
- 说明：task 配置 `:18-19` 写明「不开难度轴」，指 `braid.length`；本文难度轴是间距与位置，不改交叉数。



### 3.5 unlink_c_ring（docx 3.4）


| 类   | 叶子                                                                                                        | 当前值            | easy                      | default  | hard       | 说明                                                      |
| --- | --------------------------------------------------------------------------------------------------------- | -------------- | ------------------------- | -------- | ---------- | ------------------------------------------------------- |
| B   | `c_ring.gap_deg`                                                                                          | 23             | [25, 28]                  | [23, 27] | [21.5, 24] | 单边净空 = R·sin(gap/2) − r_c − r_f，当前 2.0 mm；下限受不等式 #1     |
| B   | `c_ring.gap_azimuth_deg`                                                                                  | 315            | ±5                        | ±10      | ±15        | 下限避开开口半角、上限受手腕行程（`unlink_c_ring_zh.md` 第 7 条）           |
| B   | `stand.hang_yaw_deg`                                                                                      | 180            | ±5                        | ±10      | ±15        | 投影方向已由 `bisector_projection` 推导；270° 实测位姿误差 28.6°，不进入范围 |
| B   | `fixed_ring.center[x,y]`                                                                                  | (0.060, 0.055) | ±0.010                    | ±0.015   | ±0.020     | 整体平移                                                    |
| C   | `primitive.grasp_azimuth_deg`                                                                             | 67.5           | 保持与 gap_azimuth 相差 112.5° |          |            |                                                         |
| D   | 全部 z、`c_ring.major_radius`、`fixed_ring.*_radius`、`c_ring.tab.*`、`primitive.slide_lift`、`max_regrasp_*`、摩擦 |                |                           |          |            | 不等式 #5（home 指尖与支架顶）余量 15.8 mm                           |


- 难度统计量：期望开口单边净空。
- 校验：`SceneGeometry.checks()` 返回 `(name, measured, limit, ok)`，直接作为拒绝采样判据；另跑 `tests/check_c_ring_clearance.py`。
- 说明：C3 类随机化非强制，但本任务 gateway 唯一且靠碰撞防捷径，随机化能验证该性质在范围内成立。



### 3.6 gate_cage_ball（docx 4.1，C4 强制）


| 类     | 叶子                                                                                                          | 当前值         | easy           | default        | hard           | 说明                        |
| ----- | ----------------------------------------------------------------------------------------------------------- | ----------- | -------------- | -------------- | -------------- | ------------------------- |
| B（时机） | `ball.release_y`                                                                                            | −0.400      | [−0.42, −0.38] | [−0.44, −0.36] | [−0.46, −0.34] | run 配置已规划为第 2 阶段注册项       |
| B（时机） | `ball.speed`                                                                                                | 0.120       | [0.09, 0.11]   | [0.10, 0.14]   | [0.12, 0.16]   | 同时缩短 entry_delay 与 window |
| B     | `channel.flat_end_y`                                                                                        | 0.150       | [0.16, 0.20]   | [0.13, 0.18]   | [0.11, 0.15]   | 只改 window 长度              |
| B     | `gate_rack.center[x,y]`                                                                                     | (−0.090, 0) | ±0.010         | ±0.020         | ±0.030         | 抓取位，oracle 读回             |
| B     | `channel.center_x`                                                                                          | 0.075       | ±0.010         | ±0.015         | ±0.020         |                           |
| D     | `gate_slot.guide_gap`（3 mm/侧）、`gate_slot.post_height`、`gate.seated_*`、`gate_rack.base_size[z]`、`motion.*_z` |             |                |                |                | `motion.*_z` 手工绝对高度       |


- 难度统计量：期望 `last_commit = entry_delay + window − insert_duration − t_ready`（可提交余量）。
- 校验：`window > insert_duration + safety_margin`（demo 已打印并告警，改为采样拒绝）。
- 说明：时机随机化本身就是实例轴——固定延时策略的成功率随 `release_y`/`speed` 分布落到中间水平，这是预期机制（run 配置注释）。



### 3.7 diverter_route_ball（docx 4.3，C4 强制）


| 类   | 叶子                                                                                                      | 当前值            | easy                            | default                  | hard                     | 说明                                                  |
| --- | ------------------------------------------------------------------------------------------------------- | -------------- | ------------------------------- | ------------------------ | ------------------------ | --------------------------------------------------- |
| A   | `diverter.dead_end_side`                                                                                | left           | Cat{left:0.5, right:0.5}（三档相同）  |                          |                          | 指令轴                                                 |
| A   | `diverter.init_sealed_side`                                                                             | right          | Cat{left:0.5, right:0.5}，与上一条独立 |                          |                          | 2×2 中一半实例正确动作为不旋转                                   |
| A   | `target_pad.enabled`                                                                                    | true           | Cat{true:1.0}                   | Cat{true:0.7, false:0.3} | Cat{true:0.3, false:0.7} | false = 仅语言可解                                       |
| B   | `branch.angle_deg`                                                                                      | 30             | ±2                              | ±4                       | ±6                       | oracle 目标角 = 该值；需重算 `ball.radius` 双侧不等式             |
| B   | `diverter.lever.radius`                                                                                 | 0.055          | ±0.003                          | ±0.005                   | ±0.008                   |                                                     |
| B   | `channel.fork_origin_x`                                                                                 | −0.020         | ±0.005                          | ±0.010                   | ±0.015                   | 拨杆落点距基座 0.688 m，需复核可达                               |
| B   | `ball.speed` / `ball.release_x`                                                                         | 0.120 / −0.170 | ±0.01 / ±0.01                   | ±0.02 / ±0.02            | ±0.03 / ±0.03            |                                                     |
| D   | `ball.radius`、`channel.inner_width`、`flap.thickness`、`joint_limited`（=false）、`mechanism.*`、`grid_pitch` |                |                                 |                          |                          | `ball.radius` 上下界由 `inner_width` 与 `angle_deg` 共同决定 |


- 难度统计量：`target_pad.enabled=false` 的概率；次要：`branch.angle_deg` 偏离 30° 的幅度。
- 校验：`check_pivot_clearance()`（建场景时抛错）+ 半开间隙 < 球径 < 落座通道宽度的双侧不等式（需从配置注释 `:181-186` 抽成函数）。
- 说明：IL 录制时按 `diverter_route_ball_zh.md` §6.3 只取需旋转的两种组合；评测保留 2×2。



### 3.8 linkbar_rotate_to_zone（docx 4.4，C4 强制）

> 2026-08-27 任务改造后叶子名变更：`sockets.b1_angle_deg / a2_angle_deg` → `zones.left.angle_deg / zones.right.angle_deg`；
> 「B1 所在侧」轴 → `zones.target`（Cat{left, right}）与 `zones.assignment`（两色互换，Cat 0.5）；
> D 类中 `socket.entry_depth`、`component_b.*`、高度链已随小车一并删除。下表数值仍适用。


| 类   | 叶子                                                                                                                                                      | 当前值 | easy                    | default   | hard      | 说明                                      |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --- | ----------------------- | --------- | --------- | --------------------------------------- |
| A   | B1 所在侧                                                                                                                                                  | +   | Cat{+:0.5, −:0.5}（三档相同） |           |           | 采样后 b1、a2 同时取反                          |
| B   | `sockets.b1_angle_deg`（绝对值）                                                                                                                             | 55  | U[40, 70]               | U[35, 75] | U[35, 75] | 硬范围 `[min_sweep, max_sweep]` = [35, 75] |
| B   | `sockets.a2_angle_deg`（绝对值）                                                                                                                             | 45  | 与                       | b1        | 之差 ≥ 20   | 无约束 U[35, 75]                           |
| B   | `linkbar.init_angle_deg`                                                                                                                                | 0   | ±5                      | ±10       | ±15       | 两插口角同步平移（C），否则 `validate()` 拒绝          |
| D   | `pivot.x`、`motion.approach_z`、`motion.grasp_qpos`、`socket.entry_depth`、`mechanism.joint_friction`（0.10）、`component_b.mechanism.joint_friction`（4.0）、高度链 |     |                         |           |           | 各有 2026-08-20~22 事故记录                   |


- 难度统计量：期望 b1 − a2（越小，最近插口捷径的期望成功率越接近 0.5）。
- 校验：`LinkbarRotateLayout.validate()`（已实现：异侧、扫掠范围、两区不重叠、两色不同）。
- 说明：本任务是准备度最高的一个，oracle 按销的颜色决策，无需改动。



### 3.9 cloth_fold（docx 1.x）


| 类   | 叶子                                                                                                                                                      | 当前值        | easy         | default      | hard         | 说明                                                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------ | ------------ | ------------ | ----------------------------------------------------------- |
| A   | 抓取角序号（4 角）                                                                                                                                              | 固定一角       | Cat 均匀（三档相同） |              |              | `_grasp_offset()` 目前只实现一角，需扩展；`edge_mid` 实测三项判据不过，排除        |
| B   | `cloth.center[x,y]`                                                                                                                                     | (0.040, 0) | ±0.010       | ±0.020       | ±0.030       | 抓取角与落点须在 x[−0.23, 0.31] y[−0.30, 0.30] 内，且抬升可达（实测 33 mm 上限） |
| B   | `grasp.inset`                                                                                                                                           | 0          | [0, 0.006]   | [0, 0.012]   | [0, 0.020]   | 上限由附着盘在布内决定                                                 |
| B   | `physical.fold_slack`                                                                                                                                   | 0.98       | [0.97, 0.99] | [0.95, 1.00] | [0.93, 1.00] | <1 布松垂被拖，=1 恰好绕折线                                           |
| D   | `cloth.size`、`mesh.cols/rows`、`particle_size`（33×33 + 0.004 是唯一实测保序组合）、`fold_step_m`、`touch_clearance`、`grasp_qpos`、`contact_band`、`bending_relaxation` |            |              |              |              | 布的 yaw 无叶子，网格生成器轴对齐，需新代码                                    |


- 难度统计量：期望 inset 与 center 偏移（抓取点离基座距离）。
- 校验：`tests/check_cloth_fold_geometry.py`；落点/抓取点在作业区内。
- 说明：`success.particle_off_target_frac_max = 0.02` 两侧余量约 2 倍，配置注释已预告多种子后需重定；随机化后先按 §4.3 重新标定阈值再定成功率。



### 3.10 cloth_unpleat（docx 1.x）


| 类   | 叶子                                                                                                        | 当前值        | easy                    | default        | hard           | 说明                               |
| --- | --------------------------------------------------------------------------------------------------------- | ---------- | ----------------------- | -------------- | -------------- | -------------------------------- |
| A   | `cloth.material_axis`                                                                                     | y          | Cat{y:0.5, x:0.5}（三档相同） |                |                | 90° 离散旋转，layout 与 evaluator 各读一次 |
| B   | `cloth.center[x,y]`                                                                                       | (0.040, 0) | ±0.010                  | ±0.020         | ±0.030         | 展开后跨 y 到 +0.161，拉伸终点须 < 0.30     |
| B   | `cloth.pleat.width`                                                                                       | 0.024      | [0.030, 0.040]          | [0.026, 0.038] | [0.024, 0.030] | 0.024 是实测下限（压塌一侧余量 0.09）；只向上取    |
| B   | `cloth.pleat.crest_height`                                                                                | 0.022      | [0.020, 0.024]          | [0.018, 0.026] | [0.016, 0.028] | `pleat_profile` 要求 tail > 0      |
| B   | `physical.pull_scale`                                                                                     | 1.05       | [1.03, 1.08]            | [1.00, 1.10]   | [0.98, 1.12]   |                                  |
| B   | `grasp.edge_inset`                                                                                        | 0.012      | [0.010, 0.014]          | [0.009, 0.016] | [0.008, 0.018] | 下限 `2·particle_size`             |
| D   | `bending_relaxation`（=0.0，任务成立条件）、布间摩擦 0.4、`pull_step_m`、`mesh.spacing`、`particle_size`、`touch_clearance` |            |                         |                |                |                                  |


- 难度统计量：期望 pleat.width（越窄，正确与压塌的判据间距越小）。
- 校验：`tests/check_cloth_unpleat_geometry.py`；起始态守卫（`spread_ratio ≤ 0.80`、三层格 ≥ 12）在建场景后仍会拦截。
- 说明：oracle 在 settle 后重新观测自由端（`observe()`），布局抖动不需要额外补偿。



### 3.11 cloth_unroll（docx 1.4）


| 类   | 叶子                                                                                                                   | 当前值             | easy                    | default        | hard           | 说明                                                                |
| --- | -------------------------------------------------------------------------------------------------------------------- | --------------- | ----------------------- | -------------- | -------------- | ----------------------------------------------------------------- |
| A   | `cloth.material_axis`                                                                                                | y               | Cat{y:0.5, x:0.5}（三档相同） |                |                |                                                                   |
| B   | `cloth.center[x,y]`（杆轴）                                                                                              | (0.040, −0.100) | ±0.010                  | ±0.020         | ±0.030         | `center[axis] + material_length < 0.30`，余量 0.12                   |
| B   | `cloth.roll.turns`                                                                                                   | 1.5             | [1.25, 1.5]             | [1.0, 1.75]    | [1.25, 1.75]   | 行程封顶约 200 mm（2.0 圈需 246 mm）；终点位置与圈数无关（`final_grasp_position` 恒等式） |
| B   | `cloth.roll.pitch`                                                                                                   | 0.014           | [0.014, 0.016]          | [0.014, 0.018] | [0.014, 0.018] | 只向上；≥3.8× 粒距否则视觉网格错绑                                              |
| B   | `dispenser.bar_height`                                                                                               | 0.045           | ±0.003                  | ±0.005         | ±0.008         | 须 > roll_radius，且 post_height > bar_height + roll_radius          |
| D   | `pull_step_m`（0.0003）、`pull_scale`（1.30 实测非单调）、`roll.clearance`、`attach_radius`、`particle_size`、`bending_relaxation` |                 |                         |                |                |                                                                   |


- 难度统计量：期望圈数（材料存量 `stored`）。
- 校验：`tests/check_cloth_unroll_geometry.py`（平铺段 > 4·spacing、附着盘离垂落段、挡头/立柱高度链）。
- 说明：同一配置两次运行 `single_layer_frac` 相差 0.09（GPU 非确定性）；随机化引入的变化需大于该值才可归因，阈值余量需保持 ≥ 0.09。

---



## 4. 测试方案



### 4.1 第 0 级：纯配置单元测试（无 Genesis）

扩展现有 7 项性质测试到 11 个任务：确定性（同 seed 同结果）、seed 敏感、越界为零、输入不可变、未注册 no-op。新增两项：

- **分布统计**：每档抽 1000 个样本，第 3 节「难度统计量」的均值按 easy → default → hard 单调；离散轴的经验频率与声明的 $p_d$ 偏差 < 0.05。
- **拒绝率**：每档校验拒绝率 < 5%；超过则该档范围过宽，收窄而非提高重试次数。



### 4.2 第 1 级：离线几何门批量运行（无 GPU）

对每个任务、每档、seed 0–99，采样后调用第 3 节「校验」列的函数，输出 `runs/variation/<task>/<difficulty>_gate.csv`（seed、各不等式读数、通过与否）。目标：通过率 100%（拒绝采样后）。

### 4.3 第 2 级：物理稳定性 sweep（GPU）

`stability_sweep.sh` 任务表补齐 11 个任务；`SEEDS="0 1 2 3 4 5 6 7 8 9" DIFFICULTIES="easy default hard" RANDOMIZE=1`。头条指标 CRASH 计数 = 0；FAIL 单独统计。布料三任务另记 `single_layer_frac` 等读数的跨种子散布，用于重定 `success.*` 阈值（配置注释均标注现值为单次标定）。

### 4.4 第 3 级：基线成功率矩阵（GPU）

每任务在同一组 seed 上跑 oracle 与对照策略（`cw`、`restack_same`、`no_align`、`greedy`、`fixed_direction`、`nearest_zone`、`bypass`、`shove`/`overpull`），按难度档报告成功率。预期：oracle 在三档均保持高成功率（下降为几何余量收窄所致，逐格记录失败标签）；对照策略在含 A 类轴的任务上接近该轴的随机水平。

### 4.5 第 4 级：固化 split

每任务写 `configs/episode_splits/<task>.yaml`（train/val/test seed 列表 × 难度档），`EpisodeKey.variant_id` 取难度标签。此后随机化注册表的任何改动视为版本变更，split 文件随之升版。

---



## 5. 实施顺序

按「前置代码量最少、C4 强制优先」排序：


| 序   | 任务                           | 前置代码                                            | 理由                               |
| --- | ---------------------------- | ----------------------------------------------- | -------------------------------- |
| 1   | linkbar_rotate_to_zone       | `_ScalarJitter` + `_ChoiceJitter` + `_Validate` | C4 强制；`validate()` 已有；oracle 无需改 |
| 2   | diverter_route_ball          | 同上 + ball.radius 不等式函数                          | C4 强制；2×2 实例轴已在配置                |
| 3   | gate_cage_ball               | `_ScalarJitter` + 可解性拒绝                         | C4 强制；run 配置已规划                  |
| 4   | swap_crossing_sign           | `braid.py` 交叉位置按 seed 采样                        | seed 已接入                         |
| 5   | rope_winding                 | `_DerivedSolve`（sweep_deg 反解）                   | EpisodeSpec 已建                   |
| 6   | unlink_c_ring                | `SceneGeometry.checks()` 接入拒绝采样                 | 已在 sweep 表                       |
| 7   | cloth_unpleat / cloth_unroll | run 配置补 seed 键；`_ChoiceJitter`                  | oracle 有重观测                      |
| 8   | ring_transfer                | 成对 post directive；run 配置 + EpisodeSpec          |                                  |
| 9   | cloth_fold                   | 四角抓取扩展                                          | 阈值余量最窄                           |
| 10  | bar_through_hole             | `primitive.*_z` 改为推导 + 新增 validate              | 无校验器、z 手工                        |


每步交付物：注册表条目、单元测试、run 配置键、`stability_sweep.sh` 表项、第 1 级 gate CSV。GPU 级别（§4.3、§4.4）由用户按 `interactive-verification-preference` 自行运行。
---

## 6. 逐任务的直观说明（参数改变后的场景形态）

本节用非形式化语言复述第 3 节：每个参数改变后场景会呈现什么，三档难度各自的典型场景。数值以第 3 节为准。

### 6.1 rope_winding

基准：左后方固定端子，中部偏右一根立柱，右前方靶心贴纸；绳弧形铺在桌上，插头在右前方。任务为抓插头绕柱 2 圈后放到靶心。

- `turns`：绕 1 / 2 / 3 圈。圈数多则绳更长、柱上螺旋更高、手臂绕行路径更长。
- `direction`：逆时针或顺时针。画面相同，需读指令。
- `POST.pos` / `C.pos` / `S.pos`：柱、靶心、端子各自在桌面平移数厘米。
- `climb_per_turn`：圈与圈的间距，小则螺旋密集，大则松散。
- `wind_z_start`：第一圈离桌面的高度。
- `sweep_deg`：随上述量重算的绳长，柱移远或圈数增加则绳自动变长。

三档：easy 以 1 圈为主，物体平移 1–2 cm，圈距宽松；default 以 2 圈为主，物体平移 2–3 cm；hard 以 2–3 圈为主，物体平移 3–4 cm，3 圈绳长约 0.9 m，圈距压到 1 cm。

### 6.2 ring_transfer

基准：两根带挡头的走线柱左右并排（相距 22 cm），弹性环平铺套在左柱 A。任务为把环搬到右柱 B。

- `enclosure/goal` 交换：环出生在右柱、目标为左柱。
- 柱对中点：两柱一起平移。柱距：18–28 cm。柱对朝向角：两柱连线相对桌边倾斜，环长轴随之旋转。
- `posts.radius`：柱身粗细，粗柱要求环张开更宽才能套入。`head_radius`：挡头大小。

三档：easy 柱距 20–24 cm、近似正对、柱径与当前相同；default 柱距 19–26 cm、倾斜 ≤20°、柱径 ±2 mm；hard 柱距 18–28 cm、倾斜 ≤30°、柱径最大 22 mm。

### 6.3 bar_through_hole

基准：左侧两个 V 形托架托着六角杆，右侧竖立面板中央开六角孔，面板后方另一托架。任务为抓杆、抬起、水平穿孔、放到后方托架。

- `across_flats`：孔径。杆 18 mm，孔 32 mm 时单边余量 7 mm；孔 27 mm 时单边 4.5 mm。
- `bar.rest_pos` xy：杆与前方两托架一起平移。`panel.x`：面板与后方托架一起平移，穿孔距离改变。
- `bar.length`：杆长，长杆更易倾斜卡孔。`grasp_offset`：抓取点离杆中心的距离。
- 各高度不变（手臂抬升/插入高度为手写常数）。

三档：easy 孔 34–38 mm、物体平移 ≤1 cm；default 孔 30–36 mm、平移 2 cm；hard 孔 27–32 mm（最小余量低于 7.5 mm 的实测跟踪误差，需实测）、杆最长 23 cm。

### 6.4 swap_crossing_sign

基准：左侧插线板，两根绳并排向右铺设，中段交叉一次，右端各有插头。任务为翻转交叉的上下关系。

- 交叉符号：出生时哪根在上。交叉位置：交叉点在绳的哪一段（当前固定在中点）。
- `channel_spacing`：两绳平行间距，60 mm 时抓一根易碰另一根，分离判据更难满足。
- `center_y`：两绳整体前后平移。`x_end`：绳长与插头位置。

三档：easy 交叉在 45–55% 处、间距 8–9.5 cm；default 交叉 35–65%、间距 7–9.5 cm、平移 3 cm；hard 交叉 25–75%、间距最小 6 cm、绳最短 16 cm。

### 6.5 unlink_c_ring

基准：支架悬臂挂一个竖直闭合圆环，C 环挂在圆环上。任务为抓 C 环、缺口对准圆环管身、滑出。

- `gap_deg`：缺口角度，决定对准余量（28° 约 4 mm，21.5° 约 1 mm）。
- `gap_azimuth_deg`：出生时缺口朝向，决定手腕转动量。
- `hang_yaw_deg`：整个装置绕竖轴旋转，接近方向改变。`fixed_ring.center` xy：装置平移。
- 半径与高度不变（支架顶与初始指尖仅 16 mm）。

三档：easy 缺口 25–28°、装置朝向 ±5°；default 缺口 23–27°、朝向 ±10°、平移 1.5 cm；hard 缺口 21.5–24°、朝向 ±15°、缺口方位 ±15°。

### 6.6 gate_cage_ball

基准：直槽道，前端开口，中部有闸槽，末端封闭；闸板置于左侧架子；球从远端滚入。任务为球过闸槽后插入闸板。

- `release_y`：球的起滚点，决定到闸口的时刻。`speed`：球速，快则可插闸窗口短。
- `flat_end_y`：过闸后到末端的距离，长则窗口长。
- `gate_rack.center`：架子位置。`channel.center_x`：槽道左右平移。

三档：easy 球速 9–11 cm/s、内段 16–20 cm；default 球速 10–14 cm/s、内段 13–18 cm、起滚点 ±4 cm；hard 球速最高 16 cm/s、内段最短 11 cm、架子与槽道各平移 2–3 cm。

### 6.7 diverter_route_ball

基准：槽道中段分为左右两岔，分岔口有可转拨板与带旋钮的拨杆，一条岔为死路。任务为按指令转板后放球。

- `dead_end_side`：死路在左或右。`init_sealed_side`：板出生时封左或封右。组合中一半实例正确动作为不转板。
- `target_pad.enabled`：活路出口是否有目标垫；无垫时只能依赖指令。
- `branch.angle_deg`：岔道张角，拨板目标角随之改变。`lever.radius`：拨杆长度。`fork_origin_x`：分岔口位置。`ball.speed / release_x`：球速与起点。

三档：easy 两离散轴各半、一定有目标垫、张角 28–32°；default 三成无目标垫、张角 26–34°；hard 七成无目标垫、张角 24–36°、拨杆 ±8 mm。

### 6.8 linkbar_rotate_to_zone

基准：转轴上装横梁，梁端有销钉、梁上有旋钮，初始指向正前；左右各一块颜色区域（橙／蓝），销钉与其中一块同色。任务为转梁把销钉停进同色区域。

- `zones.target`：目标是左区还是右区（销钉取该区颜色）。`zones.assignment`：两区颜色互换。
- `zones.left.angle_deg` / `zones.right.angle_deg`：两区离梁初始方向的角度（35–75°）。二者之差决定「转向最近区域」策略的猜中概率。
- `init_angle`：梁初始偏转 ±15°，两区随之偏移。

三档：easy 两区远近差 ≥20°；default 两角独立随机；hard 差 ≤10° 且梁初始偏转。

### 6.9 cloth_fold

基准：24 cm 方布平铺，中心略偏右。任务为捏一角沿对角线弧线放到对角，对折成三角。

- 抓取角序号：四角之一（当前只实现一角）。`cloth.center`：布平移。
- `grasp.inset`：从角尖向内的捏取距离，大则角尖下垂。`fold_slack`：弧线半径与对角线之比，<1 布下垂拖行。
- 布尺寸、网格、粒径不变；布不可旋转（网格生成器轴对齐）。

三档：easy 四角随机、平移 ≤1 cm、从角尖捏、弧线绷紧；default 平移 2 cm、内缩 ≤1 cm、松紧 0.95–1.0；hard 平移 3 cm、内缩 ≤2 cm、松紧最低 0.93。

### 6.10 cloth_unpleat

基准：12×26 cm 布带，中段叠一个 Z 形褶（三层），沿前后方向铺设。任务为捏自由端沿带方向拉平。

- `material_axis`：前后或左右铺设。`cloth.center`：平移。
- `pleat.width`：褶叠入宽度，24 mm 为实测下限，40 mm 时褶大、拉距长。`crest_height`：褶隆起高度。
- `pull_scale`：拉距相对理论值的比例。`edge_inset`：捏取点离布边的距离。

三档：easy 褶宽 30–40 mm、平移 1 cm；default 褶宽 26–38 mm、隆起 ±4 mm、平移 2 cm；hard 褶宽 24–30 mm、平移 3 cm。

### 6.11 cloth_unroll

基准：小支架横一根杆，布带卷在杆上 1.5 圈，尾端垂到桌面。任务为捏桌上的布带末端沿桌面拉，把布全部拉下展平。

- `material_axis`：支架与拉向旋转 90°。`cloth.center`（杆位置）：支架平移，展开后末端须在工作区内。
- `roll.turns`：1–1.75 圈，圈数多则拉距长（1.75 圈约 20 cm，接近单次行程上限）。
- `roll.pitch`：层间距，只允许增大。`bar_height`：杆高。

三档：easy 1.25–1.5 圈、平移 ≤1 cm；default 1–1.75 圈、前后/左右各半、平移 2 cm；hard 1.25–1.75 圈为主、平移 3 cm、杆高 ±8 mm。

### 6.12 难度作为分布的含义

每档是一个抽样范围而非固定场景。bar_through_hole 的 hard 表示孔径在 27–32 mm 内按 seed 抽取，easy 表示范围整体移到 34–38 mm；离散轴同理，难度改变的是各选项的概率（如 hard 档 70% 实例无目标垫）。

---

## 7. IL 数据量、oracle 覆盖与先例

### 7.1 变体数量对 IL 的充分性

- 连续轴使可生成的实例数无上限；数据规模的实际约束是物理耗时（FEM+IPC 绳任务约 46 min/episode），两三千 GPU 小时预算下每任务约数百条。
- 含 A 类离散轴的任务（diverter、linkbar、rope_winding、ring_transfer、swap_crossing_sign、三个布料任务）每条离散组合下叠加连续抖动，模式数 2–12，IL 可学到「按场景或指令选择动作」。
- 仅有连续轴的任务（bar_through_hole、gate_cage_ball、unlink_c_ring）数百条数据在视觉上接近，IL 主要学到位置泛化。此为结构性限制；可选补充为视觉随机化（纹理、颜色、相机微扰），不改物理层。
- 拒绝采样与 oracle 胜任域会过滤掉最难实例，数据集中 hard 档的实际难度低于声明；每档须报告 oracle 成功率与拒绝率，作为任务规格的一部分。

### 7.2 oracle 通用性现状

| 状态 | 任务 |
|---|---|
| oracle 由 layout / 实时状态推导，随机化后无需修改 | diverter、linkbar、gate_cage_ball、swap_crossing_sign、unlink_c_ring、cloth_unpleat、cloth_unroll、rope_winding（绳长需重解） |
| oracle 存在但部分量手写或范围受限 | bar_through_hole、gate_cage_ball（z 高度手写）；cloth_fold（单角、不重观测）；ring_transfer（`hang_depth` 为实测值，环周长固定；仅 `carry` 路线可用） |

11 个任务均有 oracle；无一在第 3 节范围上验证过。每个 oracle 的胜任域由各自的不等式集合界定，hard 档下限是否在域内需 GPU sweep 确认。

### 7.3 先例

纯仿真基准中「单一 oracle 覆盖随机化变体」的四种机制：

| 机制 | 代表 | 与本方案的关系 |
|---|---|---|
| 特权状态脚本 oracle，参数化 | Ravens / Transporter Networks（Zeng 等，CoRL 2020）；DeformableRavens（Seita 等，ICRA 2021，报告演示器成功率）；FabricFlowNet（Weng 等，CoRL 2021）、Foldsformer 的 SoftGym 脚本专家 | 本方案主路线。本方案的「先观测后规划」为闭环脚本，比 Ravens 的开环脚本多一次测量 |
| 逐实例搜索重解 | SoftGym（Lin 等，CoRL 2020）以仿真器为模型的 CEM | 每条演示需数百次回滚，本方案不采用 |
| 物体系路点 + 运动规划，失败丢弃 | RLBench（James 等）；ManiSkill2/3 的 motion-planning 解法 | 本方案的拒绝采样与之同形 |
| 少量示范 + 变换重放 + 仿真验证 | MimicGen（Mandlekar 等，CoRL 2023）；RoboCasa 数据生成 | 数据源不同（人类示范），「变换后验证、失败丢弃」相同 |
| 单示范 + 对应关系迁移 | DexGarmentLab（2025） | 用于标出解析式路线的适用边界 |

以上引用细节据记忆整理，成文前需核对原文（尤其 DeformableRavens 的演示器成功率数字与 DexGarmentLab 的机制描述）。LIBERO 为人类遥操作数据，不属于 oracle 生成路线。
