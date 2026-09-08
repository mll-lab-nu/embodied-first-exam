# 已部署任务的变体参数化方案

> 日期：2026-08-26 初稿；2026-08-27 增补 `rope_unwinding`、`band_untwist`，`linkbar_merge_components` 改造为 `linkbar_rotate_to_zone`；
> **2026-08-28 按 review 意见改版：先把全部变体参数化并给出可行包络，难度档位改为实测后划定，不再预设三档范围。**
> 范围：`runs/videos/` 下 13 个已录制任务
> 上游：`../framework/task_taxonomy_zh.md` §4.4（C4 类随机化为准入条件）、
> `topogym/generation/layout_randomization.py`（现有随机化接缝）、
> `bash_scripts/tests/stability_sweep.sh`（SEED × 参数 测量器）

---

## 0. 本文回答的问题

1. 每个任务哪些参数按种子变化，哪些不变，变化范围（可行包络）由什么约束决定。
2. 场景几何简单的情况下，如何让不同种子产生实质不同的实例。
3. 难度档位如何从实测结果划定（§4），而不是预先指定。

第 1 节是现状，第 2 节是参数化规则，第 3 节是逐任务参数表，第 4 节是实测与划档程序，第 5 节是实施顺序，第 6 节是逐任务直观说明，第 7 节是数据量与先例。

### 0.1 录像目录与 task_id 对照


| `runs/videos/` 目录      | task_id                  | 类别           | 任务配置                                              |
| ---------------------- | ------------------------ | ------------ | ------------------------------------------------- |
| `rope_winding`         | `rope_winding`           | routing      | `rope_winding_topogym_tabletop_v1.yaml`           |
| `rope_unwinding`       | `rope_unwinding`         | routing      | `rope_unwinding_topogym_tabletop_v1.yaml`         |
| `transfer-rope-ring`   | `ring_transfer`          | routing      | `ring_transfer_topogym_tabletop_v1.yaml`          |
| `bar_through_hole`     | `bar_through_hole`       | routing      | `bar_through_hole_topogym_tabletop_v1.yaml`       |
| `switch_rope_side`     | `swap_crossing_sign`     | entangle     | `swap_crossing_sign_topogym_tabletop_v1.yaml`     |
| `unlink_c_ring`        | `unlink_c_ring`          | entangle     | `unlink_c_ring_topogym_tabletop_v1.yaml`          |
| `rope_untwist`         | `band_untwist`           | entangle     | `band_untwist_topogym_tabletop_v1.yaml`           |
| `close_gate`           | `gate_cage_ball`         | connectivity | `gate_cage_ball_topogym_tabletop_v1.yaml`         |
| `diverter_route_ball`  | `diverter_route_ball`    | connectivity | `diverter_route_ball_topogym_tabletop_v1.yaml`    |
| `linkbar_color_region` | `linkbar_rotate_to_zone` | connectivity | `linkbar_rotate_to_zone_topogym_tabletop_v1.yaml` |
| `cloth_fold`           | `cloth_fold`             | deformation  | `cloth_fold_topogym_tabletop_v1.yaml`             |
| `cloth_unpleat`        | `cloth_unpleat`          | deformation  | `cloth_unpleat_topogym_tabletop_v1.yaml`          |
| `cloth_unroll`         | `cloth_unroll`           | deformation  | `cloth_unroll_topogym_tabletop_v1.yaml`           |


### 0.2 改版说明（2026-08-28）

review 意见：先把计划的全部变体参数化，难度按实测结果划定。对本文的影响：


| 项                   | 改版前                            | 改版后                                                        |
| ------------------- | ------------------------------ | ---------------------------------------------------------- |
| 逐任务表                | 每轴给 easy / default / hard 三个范围 | 每轴给一个**可行包络**（采样分布），边界只由物理、几何、可达约束决定                       |
| 离散轴                 | 各档概率不同                         | 一律等概率                                                      |
| 难度                  | 预设为分布参数                        | §4 的划档程序：在包络内 sweep，按实测 oracle 成功率、失败标签与候选统计量划分，划定后再写成分布参数 |
| `_DIFFICULTY_SCALE` | 难度倍率                           | 划档前不使用；`run.difficulty` 保留键位，划档前取值 `envelope`（全包络）         |


原三档数值保留在 git 历史（2026-08-27 版本），划档时可作为初始分箱参考。

---

## 1. 现状


| 项             | 状态                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 随机化接缝         | `layout_randomization.py::randomize_task_cfg(cfg, task_id, seed, difficulty)`：深拷贝 `cfg.task`、按任务 yaml 的 `variation:` 块施加抖动、无块原样返回（2026-09-01 起；此前为 python 注册表 `_REGISTRY`，四种连续 directive）。                                                                                                                                                                                     |
| 已声明变体的任务     | `linkbar_rotate_to_zone`（2026-09-01）。其余 12 个未声明；legacy 四任务的条目已于 08-29 删除。                                                                                                                                                                                                                                                                                                                        |
| 种子对场景的作用      | 仅 `swap_crossing_sign` 的 `run.seed` 进入 braid 采样（只决定交叉符号）。`band_untwist` 的 seed 传到 `BandUntwistLayout.seed` 但未消费。其余任务 seed 只是 `EpisodeKey` 身份字段；`RopeUnwindingSceneBuilder`、`LinkbarRotateSceneBuilder` 无 seed 参数。                                                                                                                                                                                    |
| run 配置键       | `randomize_layout` / `difficulty` 只存在于 cable_routing / stacked_plate / untangle 的 run 配置。                                                                                                                                                                                                                                                                                                            |
| 测量器           | `stability_sweep.sh` 任务表含 untangle / untangle_continuous / cable_routing / stacked_plate / unlink_c_ring。                                                                                                                                                                                                                                                                                            |
| 可行性校验         | 已有函数：`LinkbarRotateLayout.validate()`、`DiverterRouteBallLayout.check_pivot_clearance()`、`unlink_c_ring` `SceneGeometry.checks()`、`FigureEightSpec.__post_init__` + builder 断言、`WindingSpec.from_config` + demo 的 slack 带拒绝、gate_cage_ball 运行期可解性打印；离线门 `tests/check_*_geometry.py`（rope_winding / rope_unwinding / ring_transfer / band_untwist / cloth×3 / linkbar / c_ring）。bar_through_hole 无校验器。 |
| episode split | `configs/episode_splits/` 仅 cable_routing / swap / untangle。                                                                                                                                                                                                                                                                                                                                         |
| oracle 对配置的依赖 | 13 个任务的 oracle 路点均由配置或实时状态推导。例外：`bar_through_hole.primitive.*_z` 与 `gate_cage_ball.motion.*_z` 是手写绝对高度；`rope_unwinding.routes.initial` 有两个手写出生点。                                                                                                                                                                                                                                                     |


---

## 2. 参数化规则

### 2.1 参数分四类


| 类别    | 定义                                          | 采样方式            |
| ----- | ------------------------------------------- | --------------- |
| A 实例轴 | 离散取值，改变正确动作本身（哪根柱、哪一侧、绕几圈、交叉符号）。            | 等概率 Categorical |
| B 布局轴 | 连续几何量，oracle 读回后自适应，改变动作的位置与幅度。             | 包络内均匀分布         |
| C 派生量 | 由 A/B 决定、必须随之重算的量（绳长、出生点、步数、随动高度）。          | 重解，不采样          |
| D 固定量 | 已有实测失败记录或求解器约束的参数（粒径、d_hat、步长、摩擦、substeps）。 | 不变              |


物理参数（摩擦、刚度、d_hat）全部归 D 类。各任务配置注释均记录了这些值的实测来源，改动会改变物理稳定性而非任务难度。

### 2.2 可行包络的定义

每条 B 类轴的包络是一个区间 `[lo, hi]`，边界只来自三种来源，逐任务表的「边界来源」列注明：


| 来源       | 举例                                                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 校验函数的硬边界 | `zones.min_sweep_deg`=35、`end_gap ≥ min_clearance`、`c_ring` 不等式 #1                                                              |
| 实测事故记录   | `climb_per_turn` 0.008 零间隙、`pleat.width` 0.024 压塌余量、`hang_yaw_deg` 270° 位姿误差 28.6°                                              |
| 可达约束     | 工作区盒 x[−0.25, 0.25] y[−0.30, 0.30] z[0.03, 0.40]；各任务实测可达点（cloth_unroll y ≤ 0.181、linkbar 拨杆 ≤ 0.688 m、cloth_fold 抓取角抬升 ≤ 33 mm） |


包络内不区分难易；包络之外的样本由校验拒绝。包络边界本身是**待实测量**：§4 的 sweep 会把包络边缘 oracle 失败或物理不稳的区域切掉。

多条轴联合采样时，边界以校验函数为准（如 `ball.radius` 的双侧不等式同时受 `inner_width` 与 `angle_deg` 影响）。

### 2.3 采样流程

1. `rng = np.random.SeedSequence(seed)`；每条轴用 `spawn` 出的独立子流，子流索引由轴名的稳定哈希决定。新增一条轴不改变已有轴在同一种子下的取值。
2. 先采 A 类，再采 B 类，再重算 C 类。
3. 调用该任务的校验函数；不通过则整体重采，最多 20 次，超过则报错并记录拒绝率。**每个任务的首抽拒绝率必须 ≤ 2%**（`tests/check_variant_rng.py` 的 `MAX_REJECTION`）。区间依赖其他轴的量（球起点依赖分岔口、分岔口依赖张角与可达）不用独立区间 + 拒绝，而是抽归一化量再由 Layout 派生（`derived` kind），让约束由构造满足；超标的处置是加派生或收窄区间，不是提高重试次数（2026-09-02 定）。
4. 采样结果（含 A/B/C 全部取值）写入 `TaskVariant.parameters`（`episode_spec.py`），H5 `setup/` 逐 episode 落盘，供 §4 划档使用。

场景几何简单时，多样性主要来自 A 类而非 B 类。原则：**每个任务至少一条 A 类轴**，使脚本化策略（固定方向、最近目标、固定延时）的期望成功率被固定在随机水平；B 类轴提供连续覆盖。

B 类抖动幅度的下限：必须大于两个噪声底——仿真非确定性（cloth_unroll 同配置两次运行 `single_layer_frac` 相差 0.09）与控制误差（IK 跟踪 7.5 mm、拨板落座 4°）。小于噪声底的差异策略与评测都无法分辨；位置轴包络半宽通常 ≥ 2 cm、角度轴 ≥ 10°。

视觉轴（颜色、纹理 `texture.seed`、装饰件）可以单独随机，与物理层无关，本文不展开；按「装饰与碰撞分离」规则处理。

### 2.4 需要新增的 directive


| directive                      | 用途                                                                           | 使用任务                                                                                  |
| ------------------------------ | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `_ScalarJitter(path, lo, hi)`  | 单个标量叶子的均匀采样                                                                  | 多数任务                                                                                  |
| `_ChoiceJitter(path, choices)` | 离散实例轴，等概率                                                                    | diverter / linkbar / rope_winding / rope_unwinding / ring_transfer / 布料 material_axis |
| `_PairJitter(paths, ...)`      | 成对平移 / 旋转（ring_transfer 两柱、bar_through_hole 杆与托架）——**未实现，两任务都改走 `derived`**：bar 由 `rest_x` 派生三个托座 x，ring 由 `pair`（中点、柱距、朝向）派生两柱位置 | （已由 `derived` 覆盖）                                                        |
| `_SpacedPairJitter(paths, lo, hi, min_gap)` | 区间内间距 ≥ min_gap 的有序标量对，构造式采样不拒绝（**已落地 2026-09-01**）                 | linkbar 两区中心                                                                        |
| `_Derived(fn)`（yaml `derived`）| 采样后、校验前调用任务模块函数就地写回派生叶子；区间依赖其他轴的量抽归一化 `[0,1]` 再派生，构造式满足约束（**已落地 2026-09-02**） | linkbar（`init_frac`→初始角）、diverter（`fork_frac`→分岔口、`spawn_frac`→球起点）；待用：rope_winding（sweep_deg）、rope_unwinding（两个出生点）、ring_transfer（long_axis） |
| `_Validate(fn, max_retry)`     | 采样后调用可行性校验，失败重采                                                              | 全部                                                                                    |


划档后再扩展：每条 directive 可声明 per-difficulty 的 `(lo_d, hi_d)` 或 `p_d`（§4.4）。

### 2.5 参数化过程中同步固定的 Layout / Planner 接口约定

oracle 对变体的适应程度由 Layout 层提供的接口决定。diverter / linkbar / gate_cage_ball / band_untwist 四个任务的 planner 在随机化后无需改动，其余任务需要补接口。参数化落地时按下列六条同步整理。


| 约定             | 内容                                                                                                      | 已符合                                                                                                                         | 需补                                                                                                                          |
| -------------- | ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1 单一几何来源       | planner 只调用 `Layout` 方法，不读 `cfg.task` 叶子。测试：对 50 个随机 seed 的 cfg 离线调用 `plan_*()`，不建 Genesis 场景。          | diverter、linkbar、gate、band_untwist、cloth×3、rope_winding、rope_unwinding、ring_transfer                                        | bar_through_hole（`primitive.*_z`）、gate_cage_ball（`motion.*_z`）：改为 `Layout` 推导，先例 `knob_grasp_world()`；rope_unwinding 的两个出生点 |
| 2 实例轴以语义查询暴露   | planner 问 `layout.live_side()` / `target_zone()` / `goal_enclosure()` / `winding_target()`，同一段代码覆盖全部实例。 | diverter、linkbar、ring_transfer、band_untwist（实测 `over_end`）                                                                  | rope_winding / rope_unwinding（direction 在 `WindingSpec` 中）、cloth 的 `material_axis` / 抓取角序号                                  |
| 3 先观测后规划       | planner 输入为 settle 后测量的状态，不用设计位。                                                                        | cloth_unpleat / cloth_unroll `observe()`、unlink_c_ring `regrasp_pose()`、swap_crossing_sign、band_untwist、ring_transfer 反应式抬升 | cloth_fold、bar_through_hole、gate_cage_ball 的抓取位                                                                             |
| 4 步数由距离与速度推导   | 每段步数 = 距离 / 步长，不写固定步数。                                                                                  | cloth_fold `fold_steps()`、cloth_unroll `stroke_steps()`、rope_winding、linkbar `steps_arc(sweep)`（2026-09-01）、diverter `steps_arc(sweep)`（2026-09-02） | gate `insert_steps`、bar_through_hole `move_steps`                                                      |
| 5 可行性校验统一签名    | `Layout.checks() -> list[(name, measured, limit, ok)]`，一份实现同时供随机化拒绝采样、离线门、demo 启动断言。                    | unlink_c_ring `SceneGeometry.checks()`、diverter `checks()`（七行，2026-09-02）、gate_cage_ball `checks()`（五行，2026-09-03）；linkbar `validate()`、`FigureEightSpec`（抛错式）       | 其余任务的 `tests/check_*_geometry.py` 断言迁入 Layout；抛错式改为返回读数                                                                     |
| 6 决策规则与对照策略同接口 | `Rule.decide(layout, observation, command)`；oracle 与捷径基线是同一接口的不同实现。                                     | diverter、linkbar、gate_cage_ball、band_untwist（`wrong_end`）                                                                   | 其余任务的 `oracle_mode` 分支改为 Rule 类                                                                                             |


附带约束：planner 不读 `difficulty`。

约定 1、2、5 与随机化注册是同一次改动（注册一条轴时必须同时提供该轴的 Layout 查询与校验项），约定 3、4、6 按 §5 顺序逐任务补。

---

## 3. 逐任务参数化

表列说明：「包络」为采样分布（A 类等概率 Categorical，B 类均匀分布）；「边界来源」对应 §2.2；「候选难度统计量」是 §4 划档时的第一候选，划档前不使用。单位 m / deg，任务坐标系。

### 3.1 rope_winding（docx 2.4）


| 类   | 叶子                                                                                                                                 | 当前值             | 包络                                                        | 边界来源                                                                              |
| --- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------- |
| A   | `winding.turns`                                                                                                                    | 2               | Cat{1, 2, 3}                                              | 3 圈出生足迹 x[−0.277, 0.156] 超出工作区盒，受板面 0.70×0.80 约束；更多圈受柱顶封顶                         |
| A   | `winding.direction`                                                                                                                | ccw             | Cat{ccw, cw}                                              | 指令轴；cw 同时是 contrast pair                                                          |
| B   | `fixtures.POST.pos[x,y]`                                                                                                           | (0.020, 0.020)  | ±0.040                                                    | 工作区；C 方位角约束（下）                                                                    |
| B   | `fixtures.C.pos[x,y]`                                                                                                              | (0.075, −0.130) | ±0.030                                                    | C 相对柱心方位角须在 150°–335°                                                             |
| B   | `fixtures.S.pos[x,y]`                                                                                                              | (−0.150, 0.100) | ±0.030                                                    | 工作区；slack 带                                                                       |
| B   | `winding.climb_per_turn`                                                                                                           | 0.014           | [0.010, 0.016]                                            | 0.008 = 2·rope.radius 实测零间隙失败；上限受柱顶                                               |
| B   | `winding.wind_z_start`                                                                                                             | 0.045           | ±0.010                                                    | `wind_z_start + turns·climb + rope.radius ≤ post_top − 0.010`                     |
| C   | `rope.spawn_arc.sweep_deg`                                                                                                         | 200             | 按 slack ∈ [0.05, 0.15]、目标 0.10 由 `planner.taut_demand` 反解 | 现有 turns→sweep 表 1/2/3 → 155/200/230                                              |
| C   | C 相对柱心方位角                                                                                                                          | 292°            | 须在 150°–335°，否则拒绝或改 `winding.to_c_route: closure`         | 2026-08-27 判据改为 `winding_metric: closure`：最后一个轨道点直线去 C 若穿过锚点 S 的对径射线，闭合计数比柱上圈数多 1 |
| D   | `winding.wind_radius`（≥0.140）、`rope.z` = `flange_radius`、`contact_d_hat`、`rope.mesh.*`、`safety_max_contact_nodes`、`POST.collision` |                 |                                                           | 各有实测事故记录                                                                          |


- 校验：`tests/check_rope_winding_geometry.py`（slack 带、螺旋在柱顶下、圈间净空、插头轴线对齐、C 方位角）。
- 前置代码：`_DerivedSolve` 反解 sweep_deg；run 配置补 `randomize_layout` / `difficulty`。
- 候选难度统计量：圈数；POST 到 C 的距离。
- **已落地（2026-09-05，`docs/develop/physics/rope_winding/rope_winding_zh.md` §9）。** 与上表的差异：`sweep_deg` 由 `derived` 钩子按松弛带中点反解（没有单独的 `_DerivedSolve` 类）；
  `fixtures.C.pos` 的 x、y 各由归一化量派生，C 方位角约束不靠拒绝、也不靠 `to_c_route: closure`（角点 c1052 实测绕远侧会把缠满的绳倒拖），而是派生时就把 C 放到直线去 C 不穿锚点对径射线的位置；
  插头出生点是 Layout 规则（离对径射线 ≥ 27°）；POST.x 上界因插头出生点的可达从 0.060 收到 0.045；`direction` 不镜像，对照组 `orbit_direction: opposite`。

### 3.1b rope_unwinding（docx 2.5）

rope_winding 的镜像：绳出生时已绕柱 `start_turns` 圈，任务为反向环绕解到 0 圈后把插头放到 C。场景装配、planner、判据全部复用（`RopeUnwindingSceneBuilder` 为空子类；`WindingSpec` 新增 `start_turns` / `orbit_direction`）。


| 类   | 叶子                                                                                                                          | 当前值    | 包络                                                                       | 边界来源                                                                                    |
| --- | --------------------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| A   | `winding.start_turns`                                                                                                       | 1      | Cat{1, 2, 3}                                                             | 三档 GPU 已各通过一次（2026-08-27）                                                               |
| A   | `winding.direction`                                                                                                         | ccw    | Cat{ccw, cw}                                                             | 出生缠绕方向；轨道方向由 planner 反向派生。`orbit_direction` 强制同向是 contrast pair（读数 2·start_turns），不是实例轴 |
| B   | `POST.pos`、`S.pos`、`C.pos`、`climb_per_turn`、`wind_z_start`                                                                  | 同 §3.1 | 同 §3.1                                                                   | 同 §3.1，含 C 方位角约束                                                                        |
| C   | `routes.initial[1].pos`（S 出口切线引入点，当前 [−0.114, 0.083]）                                                                       |        | 随 `S.pos` 重算：沿 S 出口弧切线 40 mm                                             | 手写字面值；不重算会在出生网格上形成 49° 折角（弯曲半径 2.7 mm < 管半径），tetgen 报自交                                 |
| C   | `routes.initial[3].arc_to.pos`（插头出生点，当前 [−0.006, −0.218]）                                                                   |        | 随 `POST.pos`、`start_turns` 重算：沿最上一圈切线离开，尾弧弦与切线夹角 < 30°                   | 手写字面值                                                                                   |
| C   | `rope.spawn_arc.sweep_deg`                                                                                                  | −130   | 三种圈数通用（slack 8.5% / 8.9% / 9.2%）；位置抖动后由离线门复核 slack 仍在 [0.05, 0.15]，越界则反解 | 出生螺旋每圈比落位周长多 12 mm，抵消了圈数增加的需求                                                           |
| D   | 同 §3.1；另加 `plug_spin_tracks_orbit = false`（2026-08-27 A/B：开则插头自转与解绕扫掠同向叠加，`twist_net` −1.1/圈）、`rope.fem.rest_shape = spawn` |        |                                                                          |                                                                                         |


- 校验：`tests/check_rope_unwinding_geometry.py --start-turns N --sweep-deg D`（出生读数 = ±start_turns、尾弧无折角、oracle 全程在柱顶下、最紧时刻 slack 带、C 方位角）。
- 前置代码：两个 `routes.initial` 字面值改为由 layout 推导；run 配置补键（`run_configs/rope_unwinding.yaml:37-40` 已说明缺失）。
- 候选难度统计量：出生圈数。
- 已知风险：解下的绳保留螺旋记忆散在柱脚，圈数多、柱距 C 近时可能进入夹爪路径；sweep 时记录 `contact_nodes` 终值。
- **已落地（2026-09-04，`docs/develop/physics/rope_winding/rope_unwinding_zh.md` §7）。** 与上表的差异：C 类两个出生点没有做成叶子，而是 `routes.initial` 的规则条目
  （`lead_in_toward` / `tail_arc`，Layout 展开）；`sweep_deg` 不反解（位置抖动时 |S−柱| 同时进供给与需求，松弛 6.8–10.6%），改为幅值、弯向由 Layout 定；
  `direction=cw` 定义为镜像布局（Layout 取反 fixture 的 y），不镜像的 cw 首抽拒绝率 21%；`wind_z_start` 与 `C.x` 各由一个归一化量派生；
  C 方位角约束由 `to_c_route: closure` 吸收。

### 3.2 ring_transfer（docx 2.6）


| 类   | 叶子                                                                                                                  | 当前值        | 包络               | 边界来源                                                   |
| --- | ------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------- | ------------------------------------------------------ |
| A   | `ring.enclosure` / `goal.enclosure`                                                                                 | [A] / [B]  | Cat{A→B, B→A}    | 指令轴；两柱几何相同，交换即可，oracle 读 `layout.crossings()`          |
| B   | 柱对中点 xy（A、B 同时平移）                                                                                                   | (0.010, 0) | ±0.030           | 工作区；`carry` 路径最高点 + `hand_above` ≤ 0.40                |
| B   | 柱距 abs(B − A)                                                                                                       | 0.220      | [0.18, 0.28]     | 下限：悬挂股避开 A 挡头、手掌与两挡头净空；上限：工作区                          |
| B   | 柱对朝向角                                                                                                               | 0°         | ±30°             | 手腕偏航行程；`ring.long_axis` 随之旋转（C）                        |
| B   | `posts[*].radius`                                                                                                   | 0.016      | [0.013, 0.022]   | 上限 `loop_radius ≥ r + tube + d_hat`（0.050 ≥ r + 0.006） |
| B   | `posts[*].head_radius − radius`                                                                                     | 0.010      | [0.008, 0.014]   | 下限 `≥ 2·tube_radius`；上限：悬挂股避开挡头、抬升高度                   |
| C   | `ring.long_axis`                                                                                                    | [0, −1]    | 随柱对朝向旋转          |                                                        |
| C   | `carry.hang_depth`                                                                                                  | 0.140（实测）  | perimeter 不动则不重算 | 用推导值 0.19 曾使环底擦过 B 挡头                                  |
| D   | `ring.perimeter`、`ring.loop_radius`、`grasp.grasp_qpos`、`rope.fem.*`、`robot_rope_contact`（off）、`carry.hang_bottom_z` |            |                  | perimeter 变化要求重测 hang_depth，第一阶段固定                     |


- 校验：`tests/check_ring_transfer_geometry.py`（环净空、手掌与挡头净空、悬挂股避开挡头、workspace、`lift_low_z` 与挡头顶）。
- 前置代码：run 配置无 `seed` / `randomize_layout`；demo 未建 EpisodeSpec；`posts` 是列表，需 `_PairJitter`。
- 候选难度统计量：柱距；柱半径（B 柱套入所需张开宽度 `2(r_post + 2 r_tube + d_hat)`）。

**已落地（2026-09-04/05，`ring_transfer_zh.md` §7）**，与上表的对应：

| 上表的叶子 | 落地后的叶子 | 说明 |
|---|---|---|
| `ring.enclosure` / `goal.enclosure` | `ring.on_post`（choice [A, B]）/ `goal.on_post`（派生为另一根） | 列表叶子既抽不了也进不了角点 sweep 的 Hydra 覆盖，改标量；多柱出生形的预留放弃 |
| 柱对中点 xy | `pair.mid_x_frac` / `pair.mid_y_frac` → `pair.mid_x` / `mid_y` | 窗口 = `mid_*_range` ∩ 工作区 ∩ 可达圆（0.780）；直接抽 ±0.030 在柱距 0.28 时必拒 |
| 柱距、柱对朝向角 | `pair.spacing` [0.18, 0.28]、`pair.heading_deg` ±30 | 两柱位置 `posts.A/B.x,y` 由 `derived` 写出，不加 `_PairJitter` |
| `posts[*].radius`、`head_radius − radius` | `post_shape.radius` [0.013, 0.022]、`post_shape.head_overhang` [0.008, 0.014] | 两柱共用 `post_shape` 块 |
| 柱高（§2 的单调裕度轴） | `post_shape.height` [0.085, 0.115] | 三个搬运高度改为 Layout 按挡头顶 / 底座高推导后才能动；上界由 lift_low < hang_depth 定 |
| `ring.long_axis`（C） | 无叶子，Layout 由朝向推导 | 捏取侧、捏取点同样是 Layout 规则 |
| `carry.hang_bottom_z`（D） | 无叶子，Layout = base_height + 0.024 | `drop_z`、`lift_low_z` 同 |

结果：离线 1000 seed 拒绝率 0、256 角点全过；GPU seed 0–9 oracle 10/10、角点子集 8/8、`lift_only` 对照 3/3 判失败。

### 3.3 bar_through_hole（docx 2.3 变体）

> **2026-09-04 落地**（`bar_through_hole_zh.md`）。`across_flats` 下界 0.027 → 0.029：原表只算了横向单边净空，没算横推段的竖直窗口
> （far 托座斜面顶端到孔上沿，宽度 = across_flats − 0.0241），0.027 每侧只剩 1.45 mm。`rest_pos` 拆成 `rest_x / rest_y / rest_z`；
> `bar.length`、`bar.grasp_offset` 抽归一化 frac 再派生（三者独立抽会让杆端进面板、抓点越过杆端）；托座跟随用 `derived` 而非 `pair`。
> `primitive.*_z` 四个高度改由 Layout 推导；`checks()` 九行。


| 类   | 叶子                                                                                                                                          | 当前值         | 包络                   | 边界来源                                                                                 |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | -------------------- | ------------------------------------------------------------------------------------ |
| B   | `aperture.across_flats`                                                                                                                     | 0.032       | [0.027, 0.038]       | 单边净空 = (across_flats − 0.018)/2；下限 4.5 mm 低于实测 IK 跟踪误差 7.5 mm，包络下边缘预期被 §4 切掉；上限受面板尺寸 |
| B   | `bar.rest_pos[x,y]`                                                                                                                         | (−0.050, 0) | ±0.030               | `cradles.near_a.x` / `near_b.x` 随之平移（C）；EE 全程在 x < panel.x                           |
| B   | `panel.x`                                                                                                                                   | 0.130       | ±0.030               | `cradles.far.x` 随之平移（C）；工作区                                                          |
| B   | `bar.length`                                                                                                                                | 0.200       | [0.17, 0.23]         | `max_align_tilt_deg` 几何上限；杆两端不出工作区                                                   |
| B   | `bar.grasp_offset`                                                                                                                          | 0.075       | ±0.015               | 抓取点不与 near 托架重叠                                                                      |
| C   | `cradles.near_a.x`、`near_b.x`、`far.x`                                                                                                       |             | 与 bar / panel 保持当前偏移 |                                                                                      |
| D   | `aperture.center_z`、`bar.rest_pos[z]`、`cradles.*.seat_axis_z`、`panel.top_z`（≤0.1608，余量 11 mm）、`cradles.*.jaw_width`（≤0.023）、`primitive.*_z` |             |                      | `primitive.*_z` 是手写绝对高度                                                              |


- 校验：无现成校验器；需新增 `BarThroughHoleLayout.validate()`：净空 > 0、cradle 顺序、EE 位置 < panel.x、`primitive.*_z` 与 `aperture.center_z` 一致。
- 前置代码：`primitive.insert_z / seat_z / grasp_z` 改为由 `aperture.center_z`、`bar.rest_pos[z]` 推导，否则 z 轴全部归 D。
- 候选难度统计量：单边净空。

### 3.4 swap_crossing_sign（docx 3.2）

> **2026-09-07 落地**（`swap_crossing_sign_zh.md`）。三处取值与下表不同，都是算出来的：交叉位置下限 0.25 → 0.30（separate 步预测抬升 = 下面那根线的顶 1.1 cm + 交叉到插头的弧长 + 4 cm，x_end 0.20 / 间距 9.5 cm 时 0.25 要 38.5 cm、0.30 要 36 cm，工作区顶 40 cm，band_untwist 同类估计实测偏差 ±2.6 cm）；`x_end` 上限 0.22 → 0.20（cover 步在合成形状下最坏抬升 0.22 时 41.9 cm 超顶，0.20 时 39.9 cm；插头销尖 x_end + 2.9 cm，0.22 时离工作区边只剩 1 mm）；`channel_spacing` 下限 0.060 → 0.072（两插头出生相距一个间距，< 0.070 构建器拒建）。交叉符号作为显式 `choice` 轴 `braid.crossing_sign`（band_untwist 的 `over_end` 同款），0 = 沿用 seed 的 `braid/word` 流。B 类四条轴各自区间在全包络内可行（32 角点），无派生叶子。


| 类   | 叶子                                                                                                                                | 当前值     | 包络             | 边界来源                                                                 |
| --- | --------------------------------------------------------------------------------------------------------------------------------- | ------- | -------------- | -------------------------------------------------------------------- |
| A   | 交叉符号（braid 字）                                                                                                                     | seed 决定 | Cat{+, −}      | 现有机制，`generation/braid.py:153-162`                                   |
| B   | 交叉位置 `frac ∈ braid_span`                                                                                                          | 固定中点    | [0.25, 0.75]   | `braid_span` = [0.10, 0.85]；自由尾段 ≥ 64 mm；需改 `braid.py:225` 按 seed 采样 |
| B   | `braid.channel_spacing`                                                                                                           | 0.085   | [0.060, 0.095] | 上限 ≈0.101（`crossing_window ≥ 0.6·spacing`）；下限：两绳最近距离 > 抓取干扰（待实测）     |
| B   | `braid.center_y`                                                                                                                  | 0       | ±0.040         | 工作区 y ±0.30 减 spacing/2                                              |
| B   | `braid.x_end`                                                                                                                     | 0.200   | [0.16, 0.22]   | 自由端插头须留夹爪级净空；`x_end ≤ 0.22` 工作区                                      |
| D   | `braid.length`（=1）、`n_strands`、`over_lift`（=0.012）、`base_z`、`rope.mesh.segment_length`（0.009）、`rope.elastic.*_friction`、`pinch.*` |         |                | `pinch.tail_clearance = −0.030` 是进行中的 H7 实验，随机化不叠加在未定值上              |


- 校验：`braid.verify_braid_spec`（已在建场景时调用）+ `tests/check_swap_crossing_sign_planner.py`。
- 候选难度统计量：`channel_spacing`（间距小则两绳干扰增大、`separation_threshold` 0.016 更难达到）。
- 说明：task 配置 `:18-19` 「不开难度轴」指 `braid.length`；本文轴是间距与位置，不改交叉数。

### 3.5 unlink_c_ring（docx 3.4）

> **2026-09-03 落地**（`unlink_c_ring_zh.md` §11）。`gap_azimuth_deg` 由 ±15 收到 ±10：新加的手净空行在 302.4° 以下失败。GPU：`passed_through` 判据改判 `success.max_pass_through_depth`；首跑 oracle 7/10、角点 16/32 暴露摆动段 9 mm 稳态落后，`gateway_extract.py` 加闭环修正后 oracle 10/10、角点 32/32、no_align 10/10 判失败。


| 类   | 叶子                                                                                                        | 当前值            | 包络                      | 边界来源                                                                     |
| --- | --------------------------------------------------------------------------------------------------------- | -------------- | ----------------------- | ------------------------------------------------------------------------ |
| B   | `c_ring.gap_deg`                                                                                          | 23             | [21.5, 28]（已落地）        | 单边净空 = R·sin(gap/2) − r_c − r_f = 1.26 .. 4.31 mm；下限：不等式 #1（缺口塞得下管身）；上限：开口半角 14° 以内保证自释放裕度 |
| B   | `c_ring.gap_azimuth_deg`                                                                                  | 315            | ±10（已落地；原计划 ±15）   | 下限：手净空行 R·sin(gap_az + 112.5°) > 45 mm 在 302.4° 失效，±15 约 8% 拒绝超 2% 门；上限：抓取点不到 90°（管身竖直，手腕偏航推导退化） |
| B   | `stand.hang_yaw_deg`                                                                                      | 180            | ±15（已落地）              | 270° 实测位姿误差 28.6°，不进入包络；0 的抓取点 0.738 m 被可达行排除；投影方向由 `bisector_projection` 推导 |
| B   | `fixed_ring.center_x` / `center_y`                                                                        | (0.060, 0.055) | ±0.020（已落地）            | 整体平移；原 `center: [x, y, z]` 拆成三个标量键，z 不动 |
| C   | `primitive.grasp_azimuth_deg`                                                                             | 67.5           | = gap_azimuth + `primitive.grasp_offset_deg`（112.5）mod 360（已落地，`derive_task_cfg`） |                                                                          |
| D   | 全部 z、`c_ring.major_radius`、`fixed_ring.*_radius`、`c_ring.tab.*`、`primitive.slide_lift`、`max_regrasp_*`、摩擦、`reach.*`、`HAND_HALF_WIDTH` 0.045 |                |                         | 不等式 #5（home 指尖与支架顶）余量 26.8 mm                                            |


- 校验（09-03 落地）：`SceneGeometry.checks()` 七行——原五行加「抓取点可达」（`reach:` 段照 gate_cage_ball）与「手在闭合环之外」（yaml 注释里的 45 mm 规则写成判据）；`UnlinkCRingLayout.checks()` 转发，`validate_task_cfg` 作拒绝采样判据；`tests/check_c_ring_clearance.py` 加第五段对 32 角点重做四问。
- 候选难度统计量：开口单边净空。
- 前置代码（已做）：`checks()` 接入拒绝采样；抓取方位角派生；可达行。
- 说明：C3 类随机化非强制，但本任务 gateway 唯一且靠碰撞防捷径，随机化可验证该性质在包络内成立；离线 32 角点八条非 gateway 全卡，即是该性质的证据。

### 3.6 gate_cage_ball（docx 4.1，C4 强制）

> **2026-09-03 落地**。原表 `release_y ∈ [−0.46, −0.34]` 下界越过轨底起点 `entry_start_y = −0.42`；`release_y`、`flat_end_y`、`gate_rack.center_x` 改为按两条可解性判据反解区间后派生。详见 `gate_cage_ball_zh.md`。


| 类     | 叶子                                                                                                          | 当前值         | 包络             | 边界来源                                              |
| ----- | ----------------------------------------------------------------------------------------------------------- | ----------- | -------------- | ------------------------------------------------- |
| B（时机） | `ball.speed`                                                                                                | 0.120       | [0.08, 0.16]   | 送料量程；同时缩放 `entry_delay` 与窗口                       |
| B     | `channel.center_x`                                                                                          | 0.075       | [0.055, 0.095] | 工作区                                               |
| B     | `gate_rack.center_y`                                                                                        | 0           | ±0.030         | 架子沿轨道方向平移                                          |
| C     | `channel.flat_end_y` ← `channel.flat_end_frac` U[0,1]                                                       | 0.150       | `[max(0.11, door_y + r + ½·v·(insert_duration + safety_margin)), 0.20]` | 判据 A（窗口 ≥ 插入耗时 + 富余）取等                            |
| C     | `ball.release_y` ← `ball.release_frac` U[0,1]                                                               | −0.400      | `[entry_start_y + 0.02, min(door_y − r − 0.02, door_y − v·max(0, t_ready + insert_duration − window + ready_margin))]` | 判据 B（臂就位时最晚下板时刻还没过）取等；整球在门外、在轨底上           |
| C     | `gate_rack.center_x` ← `gate_rack.x_frac` U[0,1]                                                            | −0.090      | `[−0.120, 导柱外侧面 − 0.010 − ½·base_size[0]]` | 架子与导柱不重叠                                          |
| D     | `gate_slot.*`、`gate.*`、`gate_rack.base_size`、`motion.*_z`（手写绝对高度）、`timing.*`（`sim_dt` 0.01、`safety_margin` 0.15、`ready_margin` 0.10） |             |                | `timing:` 段是 env.sim.dt 与 run.safety_margin 在 task 里的副本，demo 断言一致 |


- 校验：`GateCageBallLayout.checks()` 五行（判据 A 余量、判据 B 余量、球起点在派生区间内、架子到导柱净距 ≥ 0.010、门口悬停点距底座 ≤ 0.700）；`validate()` 任一行不 ok 即拒绝。
- 对照规则三条：`oracle` / `greedy` / `fixed_delay`（2026-09-03 新增 `FixedDelayRule`，`run.fixed_delay_s`）。`hover_wait = entry_delay − t_ready` 的正负只报告不约束（离线 1000 seed 球先到 46%）。
- 离线：`check_variant_rng.py` gate 段、`check_gate_cage_ball_geometry.py`。GPU：`gate_cage_ball_variation_sweep.sh`。
- 候选难度统计量：`ready_margin`（判据 B 余量，越小越紧）；`window`；`hover_wait`。

### 3.7 diverter_route_ball（docx 4.3，C4 强制）

> **2026-09-02 落地**。§3.7 原表的 `fork_origin_x ±0.015`、`angle ±6`、`lever ±0.008` 独立抽时手柄超出 0.69 m 可达的比例约 47%，`release_x ±0.03` 下半段球心进后挡板；两者改为派生叶子，张角包络保持 24–36°，首抽拒绝率 0。详见 `diverter_route_ball_zh.md` §6.2。


| 类   | 叶子                                                                                                      | 当前值            | 包络                  | 边界来源                                        |
| --- | ------------------------------------------------------------------------------------------------------- | -------------- | ------------------- | ------------------------------------------- |
| A   | `diverter.dead_end_side`                                                                                | left           | Cat{left, right}    | 场景轴（封闭端墙可见）                                 |
| A   | `diverter.init_sealed_side`                                                                             | right          | Cat{left, right}，独立 | 2×2 中一半实例正确动作为不旋转                           |
| A   | `target_pad.enabled`                                                                                    | true           | Cat{true, false}    | false = 画面无目标提示                              |
| B   | `branch.angle_deg`                                                                                      | 30             | [24, 36]            | 下界受可达（张角小分流鼻远）；上界受占地；球径双侧不等式在 `checks()` 复核 |
| B   | `diverter.lever.radius`                                                                                 | 0.055          | [0.047, 0.063]      | 与张角一起进可达反解                                  |
| B   | `ball.speed`                                                                                            | 0.120          | [0.090, 0.150]      | 有界推力驱动量程                                    |
| C   | `channel.fork_origin_x` ← `channel.fork_frac` U[0,1]                                                    | −0.020         | `[−0.060, min(−0.020, 可达上界)]` | `reach.base_xy` (−0.570, 0)、`reach.max_knob_dist` 0.690；上界 = `base_x + sqrt(D² − (r sin a)²) − hw/sin a − r cos a`；只向 −x 挪（进料道变短）永远安全 |
| C   | `ball.release_x` ← `ball.spawn_frac` U[0,1]                                                             | −0.170         | `[entry_start_x + r + 0.004, junction_x − r − 0.010]` | 整球离开后挡板；整球在分岔交接点上游                          |
| C   | `steps_arc`                                                                                             | 261（@60°）     | `max(60, ceil(|sweep| / 0.23°))` | 恒定角速度（与 linkbar 同 0.23°/步；0.5°/步 时指垫打滑，关节落后手 6–10°）；落座到落座扫 2×张角 |
| D   | `ball.radius`、`channel.inner_width`、`flap.thickness`、`joint_limited`（=false）、`mechanism.*`、`grid_pitch`、`reach.*` |                |                     |                                             |


- 校验：`DiverterRouteBallLayout.checks()` 七行（枢轴净空 ≥ 2 mm、半开旁通间隙 < 球径 − 4 mm、落座通道 ≥ 球径 + 20 mm、分岔口派生区间非空、球起点在派生区间内、手柄距底座 ≤ 0.690、接近高度指垫到端盖顶 ≥ 30 mm）；`validate()` 任一行不 ok 即拒绝；建场景、随机化、离线门共用。
- 离线：`tests/check_variant_rng.py` diverter 段、`tests/check_diverter_geometry.py`（16 个包络角点 + 判据 flood-fill 一致性 + 规则 2×2）。GPU：`bash_scripts/tests/diverter_variation_sweep.sh`。
- 候选难度统计量：`target_pad.enabled`；`rotate_needed`；`branch.angle_deg` 偏离 30° 的幅度；`knob_reach`。
- 说明：IL 录制时按 `diverter_route_ball_zh.md` §6.3 只取需旋转的两种组合；评测保留 2×2。

### 3.8 linkbar_rotate_to_zone（docx 4.4，C4 强制）

> 2026-08-27 由 `linkbar_merge_components` 改造：删除小车、导轨、插口、weld 闩、行程测试；保留立柱、横梁、`PivotLeverPrimitive` 与全部实测高度。判据改为「销的关节角落在同色区域角窗口内且静止」。首版记录见 git 历史（`a884929` 及之前）。
> **2026-09-01 改版**：两区不再分居初始角两侧，而是放在一条固定跨度（±90°）的虚线导轨上任意位置，可同侧、可相邻，只要求不重叠；区键名 `left/right` → `color_1/color_2`（无方位含义，随机化后 `color_1` 角度较小）。理由与实测见 `linkbar_rotate_to_zone_zh.md` §5.3。


| 类   | 叶子                                                                                                                                                                    | 当前值           | 包络               | 边界来源                                                 |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ---------------- | ---------------------------------------------------- |
| A   | `zones.target`                                                                                                                                                        | color_2       | Cat{color_1, color_2} | 目标区；销、销套环、手柄盖取该区颜色                                   |
| A   | `zones.assignment.color_1` / `.color_2`                                                                                                                               | blue / orange | 六色不放回抽两种（30 种有序对） | 与 target 独立                                          |
| B   | `zones.color_1.angle_deg` ≤ `zones.color_2.angle_deg`                                                                                                                 | −45 / +55     | 有序对，两中心 ∈ [−82, 82]，角距 ≥ 16 | 导轨 `rail.start/end_deg` ±90 减半宽 8；角距 = 2·half_width（相邻允许）。`_SpacedPairJitter` 构造式采样，不为重叠拒绝 |
| C   | `linkbar.init_angle_deg` ← `linkbar.init_frac` U[0,1]                                                                                                                 | 0             | `init_span_deg` ±15 扣掉两区禁区后的并集 | **2026-09-02 改为派生**：先抽两区，初始角在 ±15° 减去每区 `half_width + pin_start_margin`（10°）后的 1–3 段并集上按长度比例定位；并集为空（两区盖满 ±15°，约 0.25%）才拒绝。此前独立抽 + 拒绝，首抽拒绝率 0.234 |
| B   | `zones.half_width_deg`                                                                                                                                                | 8             | [6, 10]（尚未采样）    | 下限受 `motion.target_tolerance_deg` 4° 与实测落座误差；上限受两区角距 |
| C   | `steps_arc`                                                                                                                                                           | 240（@55°）    | `max(120, ceil(|sweep| / 0.23°))` | 固定角速度而非步数：步数固定时 `max_lag` 随扫掠角 0.05°/° 增长（2026-09-01 §8.4/§8.5） |
| D   | `pivot.x`（+0.020）、`motion.approach_z`（0.315）、`motion.grasp_qpos`（0.001）、`motion.arc_deg_per_step`（0.23）、`mechanism.joint_friction`（0.10）、`axle.clearance`（0.002）、高度链、`knob.*`、`rail.*` |               |                  | 各有 2026-08-20~22 事故记录；`arm_radius` / `pivot` 不进判据；导轨跨度固定是任务定义    |


- 校验：`LinkbarRotateLayout.validate()`（初始角在导轨上、区整体在导轨内、销出生不在区内、两区不重叠、两色不同、target 合法）；离线 `tests/check_linkbar_zone_geometry.py`、`tests/check_linkbar_planner.py`（oracle 6/6，`nearest_zone` 3/6）。
- 前置代码：已全部落地（注册条目、demo 接线、sweep 脚本）。`LinkbarRotateSceneBuilder` 无 seed 参数，走 `randomize_task_cfg` 在 `cfg.task` 层做。
- 候选难度统计量：abs(|c1 − init| − |c2 − init|)（两区离初始角的远近差；越小，`nearest_zone` 捷径的期望成功率越接近 0.5）；目标区的扫掠角（同侧远区最大约 105°）；`half_width_deg`。

### 3.9 cloth_fold（docx 1.x）

**已落地（2026-09-06，`cloth_fold_zh.md`）。** 下表是落地后的实际包络；与原计划的差别：`fold_slack` 下限 0.93 → 0.96（按判据算：手停在离对角 材料长 × (1 − slack)，0.93 差 11.9 mm 超过主判据的 7.5 mm 平均误差门，oracle 自己就判失败）；`center_x` 不独立抽而由远角可达盘派生（基准远角离底座 0.740 已是本任务一直在抓的最远点，独立抽到 0.070 + center_y 0.030 时远角 0.775 无实测）。

| 类   | 叶子                                  | 当前值      | 包络                                   | 边界来源                                                                          |
| --- | ----------------------------------- | -------- | ------------------------------------ | ----------------------------------------------------------------------------- |
| A   | `grasp.corner`                      | far_left | Cat{far_left, far_right, near_left, near_right} | 指令轴（`goal.instruction` 模板 + `Layout.instruction()`）；`edge_mid` 实测三项判据不过，排除 |
| A   | `goal.fold_fraction`                | 1.0      | Cat{1.0, 0.9, 0.8}                   | 单调裕度轴 + 指令轴（2026-09-07 取代 `grasp.inset`）：折痕位置，f = 抓点到折痕 ÷ 半对角线 16.97 cm。下限由实测定（余量 7.57 / 7.05 / 1.98 mm）；不取 > 1（悬空带有一个布厚的系统偏差）|
| B   | `cloth.center_y`                    | 0        | ±0.030                               | 布边最远到 y = 0.150，离工作区边 0.30 余量大，不派生                                            |
| B   | `physical.fold_slack`               | 0.98     | [0.96, 1.00]                         | `slack_within_gate` 行：材料长 × (1 − slack) ≤ `particle_error_mean_max` 0.0075        |
| C   | `cloth.center_x_frac` → `cloth.center_x` | 1.0 → 0.040 | [0.010, min(0.070, 可达盘封顶)]（基准 0.0402；96 角点窗口宽 0.025–0.057） | 远角（抓取点 / 落点里 x 大的）离 `reach.base_xy` ≤ `reach.max_hand_dist` 0.740（假设，固定布局复跑 + 角点子集钉住） |
| D   | `cloth.size`、`mesh.cols/rows`、`particle_size`（33×33 + 0.004 是唯一实测保序组合）、`fold_step_m`、`touch_clearance`、`grasp_qpos`、`attach_radius`、`contact_band`、`bending_relaxation` |          |                                      | 布的 yaw 无叶子，网格生成器轴对齐                                                             |

- 校验：`_cloth_fold_geometry.cloth_fold_checks` 五行（远角可达、出生布在工作区内、最高点低于工作区顶、松紧差距 ≤ 平均误差门、捏取点还在布上）；`tests/check_cloth_fold_geometry.py`「变体包络」段 96 角点。
- 变体前修的执行链：判定器占用网格锚到静置点云最小角（cloth_unpleat 同一缺陷）；`_grasp_offset` 四角。角点子集晒出两处（`cloth_fold_zh.md` §5.2）：控制网格三角形对角线方向按抓哪个角选（折痕顺着对角线边走时半布落地侧滑 30 mm；交替对角线的对称网格被 Genesis 重网格成 4604 粒子、顶点顺序丢失，只能整张统一按角选向）；`grasp.finger_axis` 默认改 `arm_default`（near_left 落点在可达盘边上时 across 8.5 mm 判失败、arm_default 5.3 mm 过）。
- 对照走法：`drag`（贴地拖，预期两层率 ≈ 0.2 判失败）、`fixed_corner`（无视指令永远折 far_left，预期 1/4 成功）。
- 候选难度统计量：**移动那半布的平均误差**离 15 mm 单点容差的距离（随 `fold_fraction` 单调收窄，实测 7.57 / 7.05 / 1.98 mm）；或折痕偏移。**不要用整块布的平均误差**——折得短时动的材料少，它反而不涨（实测三档 3.75 / 2.85 / 3.54 mm）。
- 说明：`success.particle_off_target_frac_max = 0.02` 两侧余量约 2 倍，配置注释已预告多种子后需重定；§4.3 先重标定阈值再统计成功率。

### 3.10 cloth_unpleat（docx 1.x）


| 类   | 叶子                                                                                                        | 当前值        | 包络             | 边界来源                                                    |
| --- | --------------------------------------------------------------------------------------------------------- | ---------- | -------------- | ------------------------------------------------------- |
| A   | `cloth.material_axis`                                                                                     | y          | Cat{x, y}      | 90° 离散旋转，layout 与 evaluator 各读一次                        |
| B   | `cloth.center[x,y]`                                                                                       | (0.040, 0) | ±0.030         | 展开后跨 y 到 +0.161，拉伸终点 < 0.30                             |
| B   | `cloth.pleat.width`                                                                                       | 0.024      | [0.024, 0.040] | 0.024 实测下限（压塌一侧余量 0.09）；上限 `pleat_profile` tail > 0     |
| B   | `cloth.pleat.crest_height`                                                                                | 0.022      | [0.016, 0.028] | `pleat_profile` tail > 0；`crest_height > attach_z_band` |
| B   | `physical.pull_scale`                                                                                     | 1.05       | [0.98, 1.12]   | 多拉会把布带整体拖走                                              |
| B   | `grasp.edge_inset`                                                                                        | 0.012      | [0.008, 0.018] | 下限 `2·particle_size`                                    |
| D   | `bending_relaxation`（=0.0，任务成立条件）、布间摩擦 0.4、`pull_step_m`、`mesh.spacing`、`particle_size`、`touch_clearance` |            |                |                                                         |


- 校验：`tests/check_cloth_unpleat_geometry.py`；起始态守卫（`spread_ratio ≤ 0.80`、三层格 ≥ 12）在建场景后仍会拦截。
- 候选难度统计量：`pleat.width`（越窄，正确与压塌的判据间距越小）。
- 说明：oracle 在 settle 后重新观测自由端（`observe()`），布局抖动不需要额外补偿。

### 3.11 cloth_unroll（docx 1.4）


| 类   | 叶子                                                                                                                   | 当前值             | 包络             | 边界来源                                                           |
| --- | -------------------------------------------------------------------------------------------------------------------- | --------------- | -------------- | -------------------------------------------------------------- |
| A   | `cloth.pull_side`（2026-09-05 起）                                                                                      | +1              | Cat{+1, −1}    | −1 = 镜像布局（支架在 y = +0.100，向 −y 拖）。原写的 `material_axis` Cat{x, y} 不采用：沿 +x 拖终点 x ≈ +0.32 出工作区，朝机械臂拖的可达未实测 |
| B   | `cloth.center_x`（杆轴，拆键）                                                                                            | 0.040           | [0.010, 0.050] | 上限由可达盘：终点 y ≈ 0.225 时弦长 0.240                                  |
| B → 派生 | `cloth.center_y_frac` → `cloth.center_y`                                                                          | 0.5 → −0.100    | −0.100 ± 0.030 | 上端 = min(可达盘弦长 − 终点偏移, 工作区 − 0.040 − 终点偏移)；1000 seed 里 57 个被封顶 |
| B   | `cloth.roll.turns`                                                                                                   | 1.5             | Cat{1.0, 1.25, 1.5} | **[1.0, 1.75] 不成立**：0.280 m 布上 1.75 圈任何层距都没有平铺段，1.5 圈只允许层距 ≤ 0.0158（杆高 0.053）；终点位置与圈数无关 |
| B → 派生 | `cloth.roll.pitch_frac` → `cloth.roll.pitch`                                                                     | 0 → 0.014       | [0.014, pitch_max ≤ 0.018] | 只向上；≥3.8× 粒距否则视觉网格错绑；pitch_max = 平铺段五行（≥ 4 格、附着盘离垂落段、抓取点离梁心 ≥ 57 mm、卷底离桌、立柱高过卷顶）都成立的最大层距，二分 |
| B   | `dispenser.bar_height`                                                                                               | 0.045           | ±0.008         | > roll_radius；post_height > bar_height + roll_radius（立柱 0.075 → 0.090） |
| 派生 | `grasp.max_start_spread_ratio`                                                                                       | 0.50            | 设计铺展比 + 0.11 | 1 圈的松卷设计铺展比 0.60–0.66 > 0.50，固定守卫会把健康布局当 material_already_released |
| D   | `material_axis` y、`pull_step_m`（0.0003）、`pull_scale`（1.30 实测非单调）、`roll.clearance`、`attach_radius`、`particle_size`、`bending_relaxation`、`edge_inset` |                 |                |                                                                |


- 校验：`ClothUnrollLayout.checks()` 十行（`_cloth_unroll_geometry.py`），`tests/check_cloth_unroll_geometry.py` 变体包络段 96 角点。
- 候选难度统计量：圈数（材料存量 `stored`）。
- 说明：同一配置两次运行 `single_layer_frac` 相差 0.09（GPU 非确定性）；阈值余量需保持 ≥ 0.09。
- 离线落地 2026-09-05，`cloth_unroll_zh.md` §9；GPU seed 10/10、角点 96/96（09-05）。09-06：胶带式保持默认开（§9.8）；判据加门 `over_pull`（§9.9）；09-06 晚横梁改为辊、布尾粘在辊上、拉过头扯断（§9.11）：oracle 终点由几何定（`pull_scale` 退役），判据四条门（`tail_on_bar`、`over_pull` 按放松位），探针四格两层格 0–16、单层率 0.93–0.97；全量待复跑。

### 3.12 band_untwist（docx 3.3）

开口 FEM 绳平放桌面摆成 8 字（闭合叶朝 +x、开口叶两绳头朝机械臂、一处自交叉），两绳头各一个刚体插头。任务为抓压在上面那股的绳头，整股抬离桌面跨过另一股，放到另一绳头外侧，自交叉 1 → 0。闭合弹性带路线因无自接触势垒自行回弹而废弃（`band_untwist_zh.md` §1.1）。


| 类   | 叶子                                                                                                                                                                                             | 当前值       | 包络             | 边界来源                                                                                                                                    |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| A   | `figure_eight.over_end`（哪一端在上）                                                                                                                                                                | 0         | Cat{0, 1}       | **已落地（09-03）**：`over_end=1` 时几何模块把局部 b 取反并把点序反转，两绳头位置不变、上下股互换；`layout.over_end` 读 cfg。planner 从实测 `over_end` 决定抓哪端，未改 |
| B   | `figure_eight.heading_deg`                                                                                                                                                                     | 0         | ±30            | 整个 8 字绕中心旋转；无代码读回；足迹在工作区                                                                                                                |
| B   | `figure_eight.center_x` / `center_y`（原 `center` 列表拆成两键：随机化器不支持列表元素）                                                                                                                  | (0.02, 0) | x [−0.01, 0.05]，y ±0.030 | 绳头 x≈−0.08、闭合叶顶 x≈+0.12；`checks()` 的 `footprint` 行（≥ `workspace.margin` 0.040）                                                            |
| B   | `figure_eight.half_angle_deg`                                                                                                                                                                  | 45        | [30, 60]       | 两股交叉夹角 = 2·half_angle；偏离 90° 越多投影计数越易抖                                                                                                  |
| B   | `figure_eight.closed_lobe_radius`                                                                                                                                                              | 0.040     | [0.032, 0.055] | 控制多边形最小转角半径 ≥ 3·管半径 = 0.012                                                                                                             |
| B   | `figure_eight.open_lobe_radius`                                                                                                                                                                | 0.050     | [0.040, 0.065] | 交叉点到绳头弧长决定抬升高度（当前 183 mm，上限 workspace z 0.40）                                                                                           |
| B→C | `figure_eight.end_frac` → `end_gap`                                                                                                                                                            | 0.080     | 派生 [0.070, 0.95·2·r_o] | 下限 `min_clearance` 0.070（现已显式写进 yaml）；上限 `end_gap_max_ratio` × 开口叶直径；`end_gap_from_frac` 派生，区间空则拒                                    |
| D   | `over_lift`（0.012 = 2r + particle_size）、`base_z`（0.007）、`lift_ramp`（0.030）、`rope.mesh.segment_length`（0.005，仅 FEM 下合法）、`rope.fem.*`、`rope.elastic.*_friction`、`pinch.*`、`free_end_connector.*` |           |                | `lift_ramp` 0.030 只过了离线门，GPU 三门在 0.020 下过                                                                                               |


- 校验（09-03 落地，09-04 加落点两行）：`BandUntwistLayout.checks()` 八行（绳头间距、开口比、转角半径 3D 含鼓包、足迹、抬升高度 ≤ `workspace.z_max` 0.40、管底净空、落点离留桌那股 ≥ `place_clearance`、铺绳直线离留桌那股 ≥ 2·管半径），纯函数在 `_figure_eight_geometry.figure_eight_checks`；`FigureEightSpec.__post_init__` 与 builder 的两个 raise 保留。`figure_eight.tube_radius` 是 `rope.radius` 的字面量副本（校验只拿得到未解析 task 配置），`workspace:` 段是 `manipulation_space.workspace` 的副本。详见 `band_untwist_zh.md` §7。
- 前置代码（已做）：镜像轴；run 配置三个变体键；两个 demo 接 `randomize_task_cfg`；inspect demo 加 `static_only`。`BandUntwistLayout.seed` 保留为 run seed，不消费。
- 候选难度统计量：`open_lobe_radius`（抬升高度）；`half_angle_deg` 偏离 45° 的幅度。
- 说明：oracle 只读实时量（插头位姿、实测交叉点与 over 端、绳顶高）与 `pinch.lift_clearance` / `place_clearance`，不读 `figure_eight.*`，全部 B 类轴对 oracle 透明。

---

## 4. 实测与划档程序

### 4.1 第 0 级：纯配置单元测试（无 Genesis）

扩展现有 7 项性质测试到 13 个任务：确定性（同 seed 同结果）、seed 敏感、越界为零、输入不可变、未注册 no-op。新增：

- **拒绝率**：每任务抽 1000 个样本，校验拒绝率 < 5%；超过则收窄包络。
- **planner 离线可解**：对 50 个随机 seed 的 cfg 调用 `plan_*()`（不建 Genesis），无异常且路点在工作区内（§2.5 约定 1）。

### 4.2 第 1 级：离线几何门批量运行（无 GPU）

对每任务 seed 0–199，采样后调用第 3 节「校验」列的函数，输出 `runs/variation/<task>/envelope_gate.csv`（seed、全部轴取值、各不等式读数、通过与否）。目标：拒绝采样后通过率 100%。

### 4.3 第 2 级：包络 sweep（GPU）

`stability_sweep.sh` 任务表补齐 13 个任务；`SEEDS="0 … 49" DIFFICULTIES="envelope" RANDOMIZE=1`。每格记录：全部轴取值、物理分类（OK / FAIL / CRASH-segv / CRASH-phys / TIMEOUT）、oracle 成功与失败标签、对照策略（`cw` / `orbit_direction` / `restack_same` / `no_align` / `wrong_end` / `greedy` / `fixed_direction` / `nearest_zone` / `bypass` / `shove` / `overpull`）成功与否、任务读数（净空、`single_layer_frac`、闭合计数等）。

布料三任务另记读数的跨种子散布，用于重定 `success.*` 阈值（配置注释均标注现值为单次标定）。

处置：CRASH 集中在某轴的包络边缘 → 该轴收窄；oracle FAIL 集中在某轴边缘 → 记为该轴的 oracle 胜任边界，包络保留但在划档时归入最高档或剔除（§4.4 决定）。

### 4.4 划档

划档在 §4.3 数据上进行，输出为每档、每轴一个分布参数，写回注册表（`_ScalarJitter` 的 `(lo_d, hi_d)`、`_ChoiceJitter` 的 `p_d`）。步骤：

1. 对每任务选定难度统计量 `s`（第 3 节「候选难度统计量」为初选；以 sweep 中与 oracle 失败率、对照策略成功率相关性最高者为准）。
2. 按 `s` 把 sweep 样本分成 3 个分位区间，检查：各区间 oracle 成功率单调递减、对照策略成功率在含 A 类轴的任务上接近随机水平、无区间 CRASH。
3. 每档的分布 = 该分位区间在各轴上的投影（连续轴取区间端点为 `(lo_d, hi_d)`，离散轴取经验频率为 `p_d`）；满足 `supp P_easy ⊆ supp P_default ⊆ supp P_hard`。
4. 每档报告：oracle 成功率、拒绝率、对照策略成功率。三者作为任务规格的一部分进入产物文档。
5. 划档不由基线分数反推（`run_configs/gate_cage_ball_gate.yaml` 已记录该原则）：区间边界来自 `s` 的分位数，不因某个基线的分数调整。

若某任务在整个包络内 oracle 成功率无显著变化（如仅连续轴的位置抖动），该任务只设一档 `default`，不强行分三档。

### 4.5 第 4 级：固化 split

每任务写 `configs/episode_splits/<task>.yaml`（train / val / test seed 列表 × 难度档），`EpisodeKey.variant_id` 取难度标签。此后注册表的任何改动视为版本变更，split 文件随之升版。

---

## 5. 实施顺序

按「前置代码量最少、C4 强制优先」排序：


| 序   | 任务                           | 前置代码                                            | 理由                               |
| --- | ---------------------------- | ----------------------------------------------- | -------------------------------- |
| 1   | linkbar_rotate_to_zone       | `_ScalarJitter` + `_ChoiceJitter` + `_SpacedPairJitter` + `_Validate`（已落地） | C4 强制；`validate()` 已有；oracle 无需改 |
| 2   | diverter_route_ball          | `derived` kind + `checks()` 七行（**已落地 2026-09-02**，GPU seed 0–9 oracle 10/10） | C4 强制；2×2 实例轴已在配置                |
| 3   | gate_cage_ball               | `derived` 三叶子 + `checks()` 五行 + `timing:` 段（**已落地 2026-09-03**，GPU seed 0–9 oracle 10/10、greedy 8/10、fixed_delay 6/10；判据 `pinched` 定义修正） | C4 强制                              |
| 4   | band_untwist                 | 镜像轴；在 `figure_eight_spec()` 消费 seed             | oracle 不读布局叶子                    |
| 5   | swap_crossing_sign           | 已落地（**2026-09-07**）：`braid.crossing_frac` 接收采样值并裁剪窗口、`braid.crossing_sign` 直接给 braid 字、`verify_braid_spec` 进构建器、共用 Layout `checks()` 八行（第八行 `lane_entry_gap` 是 GPU 首跑 7/10 后加的）；离线 1000 seed 拒绝率 0、32 角点全过；GPU：seed 0–9 oracle 10/10、角点子集 8/8、restack_same 3/3 判失败 | 与 untangle_continuous 共用构建器，改前后 seed 0–9 braid 字逐位一致 |
| 6   | rope_winding                 | `_DerivedSolve`（sweep_deg 反解）+ C 方位角校验          | EpisodeSpec 已建                   |
| 7   | rope_unwinding               | 两个 `routes.initial` 字面值改为推导 + run 配置键           | 复用 rope_winding 注册项              |
| 8   | unlink_c_ring                | `checks()` 七行接入拒绝采样 + 抓取方位角派生（**已落地 2026-09-03**，1000 seed 拒绝率 0、32 角点离线全过；GPU oracle 10/10、角点 32/32、no_align 10/10 判失败；判据 `passed_through` 与摆动段闭环修正两处改动） | 已在 sweep 表                       |
| 9   | cloth_unpleat / cloth_unroll | run 配置补 seed 键；`_ChoiceJitter`                  | oracle 有重观测                      |
| 10  | ring_transfer                | `_PairJitter`；run 配置 + EpisodeSpec              | 已落地（09-04/05）：`pair` + `derived`，run 配置三键；EpisodeSpec 归目标 3 |
| 11  | cloth_fold                   | 四角抓取扩展                                          | 阈值余量最窄                           |
| 12  | bar_through_hole             | `primitive.*_z` 改为推导 + 新增 validate              | 无校验器、z 手写                        |


每步交付物：注册表条目、单元测试、run 配置键、`stability_sweep.sh` 表项、第 1 级 gate CSV。GPU 级别（§4.3、§4.4）由用户自行运行。

---

## 6. 逐任务的直观说明（参数改变后的场景形态）

本节用非形式化语言复述第 3 节：每个参数改变后场景会呈现什么，以及包络两端的极端形态。数值以第 3 节为准。

### SoftGym 的变体生成流程为：每个任务预先采样 1000 个环境变体，其中 800 个作为训练集、200 个作为评测集。变体的内容为初始状态：物体尺寸、初始位形、初始位置等参数在采样范围内随机取值，生成后缓存为初始状态文件，训练与评测时从缓存中加载。SoftGym 无语言输入接口，每个环境的目标固定（例如布料对折），目标信息隐含在奖励函数中，变体之间的差异仅存在于初始状态。 [arxiv](https://arxiv.org/pdf/2011.07215)

难度处理方式：SoftGym 划分为 SoftGym-Medium、SoftGym-Hard、SoftGym-Robot 三个部分，其中 SoftGym-Hard 包含四个更困难的独立任务场景。难度差异通过注册独立任务实现，单一环境内部不按参数值划分难度档。这与此前已确定的原则一致（难度档位实现为独立注册的环境配置，初始状态变体为批内变化）。 [arxiv](https://arxiv.org/pdf/2510.10903)

### 6.2 rope_unwinding

基准：与 rope_winding 同一桌面，绳出生时已绕柱 1 圈，插头平放在柱南侧板面上。任务为抓插头反向环绕把绳解下，再把插头放到靶心。

- `start_turns`：出生时绕 1 / 2 / 3 圈，柱上螺旋更高，手臂反向绕更多圈。
- `direction`：出生缠绕为逆时针或顺时针，解绕方向随之相反。
- 柱、端子、靶心位置：同 rope_winding；引入点与插头出生点随之重算，出生绳无折角。

包络两端：1 圈 ↔ 3 圈、物体平移 3–4 cm。

### 6.3 ring_transfer

基准：两根带挡头的走线柱左右并排（相距 22 cm），弹性环平铺套在左柱 A。任务为把环搬到右柱 B。

- `ring.on_post` 交换：环出生在右柱、目标为左柱（落地时列表 `enclosure/goal` 改成了标量）。
- 柱对中点：两柱一起平移。柱距：18–28 cm。柱对朝向角：两柱连线相对桌边倾斜最多 30°，环长轴随之旋转。
- `posts.radius`：柱身粗细，粗柱要求环张开更宽才能套入。`head_radius`：挡头大小。

包络两端：柱距 18 cm、正对、柱径 13 mm ↔ 柱距 28 cm、倾斜 30°、柱径 22 mm。

### 6.4 bar_through_hole

基准：左侧两个 V 形托架托着六角杆，右侧竖立面板中央开六角孔，面板后方另一托架。任务为抓杆、抬起、水平穿孔、放到后方托架。

- `across_flats`：孔径。杆 18 mm，孔 38 mm 时单边余量 10 mm；孔 27 mm 时单边 4.5 mm。
- `bar.rest_pos` xy：杆与前方两托架一起平移。`panel.x`：面板与后方托架一起平移。
- `bar.length`：杆长，长杆更易倾斜卡孔。`grasp_offset`：抓取点离杆中心的距离。
- 各高度不变。

包络两端：孔 38 mm、物体在基准位 ↔ 孔 27 mm、物体平移 3 cm、杆 23 cm。

### 6.5 swap_crossing_sign

基准：左侧插线板，两根绳并排向右铺设，中段交叉一次，右端各有插头。任务为翻转交叉的上下关系。

- 交叉符号：出生时哪根在上。交叉位置：交叉点在绳的哪一段。
- `channel_spacing`：两绳平行间距，60 mm 时抓一根易碰另一根。
- `center_y`：两绳整体前后平移。`x_end`：绳长与插头位置。

包络两端：交叉在中段、间距 9.5 cm ↔ 交叉靠近插线板或插头（25% / 75%）、间距 6 cm、绳最短 16 cm。

### 6.6 unlink_c_ring

基准：支架悬臂挂一个竖直闭合圆环，C 环挂在圆环上。任务为抓 C 环、缺口对准圆环管身、滑出。

- `gap_deg`：缺口角度，决定对准余量（28° 约 4 mm，21.5° 约 1 mm）。
- `gap_azimuth_deg`：出生时缺口朝向，决定手腕转动量。
- `hang_yaw_deg`：整个装置绕竖轴旋转。`fixed_ring.center` xy：装置平移。
- 半径与高度不变。

包络两端：缺口 28°、装置正对 ↔ 缺口 21.5°、装置转 15°、缺口方位偏 15°。

### 6.7 band_untwist

基准：一根开口绳平放桌面摆成 8 字，闭合叶朝远离机械臂的方向，两个带插头的绳头朝机械臂，中间一处交叉。任务为抓压在上面那股的绳头，整股抬起跨过另一股，放到另一绳头外侧。

- 上压股（待新增）：出生时哪一端的绳压在上面，决定抓哪个插头。
- `heading_deg`：整个 8 字绕中心旋转。`center`：8 字平移。
- `half_angle_deg`：交叉处两股的夹角（当前 90°）。
- `closed_lobe_radius` / `open_lobe_radius`：两叶大小；开口叶越大，交叉点到绳头越长，抬升越高。
- `end_gap`：两绳头相距多远，下限由夹爪跨距决定。

包络两端：基准形状 ↔ 旋转 30°、平移 3 cm、交叉夹角 60° 或 120°、开口叶最大（抬升接近工作区顶）。

### 6.8 gate_cage_ball

基准：直槽道，前端开口，中部有闸槽，末端封闭；闸板置于左侧架子；球从远端滚入。任务为球过闸槽后插入闸板。

- `release_y`：球的起滚点。`speed`：球速，快则可插闸窗口短。
- `flat_end_y`：过闸后到末端的距离，长则窗口长。
- `gate_rack.center`：架子位置。`channel.center_x`：槽道左右平移。

包络两端：球速 8 cm/s、内段 20 cm ↔ 球速 16 cm/s、内段 11 cm（窗口只比插闸动作略长）。

### 6.9 diverter_route_ball

基准：槽道中段分为左右两岔，分岔口有可转拨板与带旋钮的拨杆，一条岔为死路。任务为按指令转板后放球。

- `dead_end_side`：死路在左或右。`init_sealed_side`：板出生时封左或封右。组合中一半实例正确动作为不转板。
- `target_pad.enabled`：活路出口是否有目标垫；无垫时只能依赖指令。
- `branch.angle_deg`：岔道张角，拨板目标角随之改变。`lever.radius`：拨杆长度。`fork_origin_x`：分岔口位置。`ball.speed / release_x`：球速与起点。

包络两端：有目标垫、张角 30° ↔ 无目标垫、张角 24° 或 36°、拨杆 ±8 mm。

### 6.10 linkbar_rotate_to_zone

基准：转轴上装横梁，梁端有销钉、梁上有旋钮，初始指向正前；销的圆上画一段固定跨度（±90°）的虚线导轨，导轨上放两块颜色区域（默认 −45° 蓝、+55° 橙），销钉与其中一块同色。任务为转梁把销钉停进同色区域。

- `zones.target`：目标是哪块区。`zones.assignment`：两区各取六色里的哪两种。
- `zones.color_1/color_2.angle_deg`：两区在导轨上的位置，可同侧、可相邻（净角距 0），不重叠；两区离初始角的远近差决定「转向最近区域」策略的猜中概率。
- `init_angle`：梁初始偏转 ±15°，销出生时不在任一区里。`half_width_deg`：区域宽度（判定窗口，尚未采样）。

包络两端：两区分居两侧、远近差大 ↔ 两区同侧相邻、目标是远的那块（销途中掠过近区，扫掠可达约 105°）。

### 6.11 cloth_fold

基准：24 cm 方布平铺，中心略偏右。任务为捏一角沿对角线弧线放到对角，对折成三角。

- 抓取角序号：四角之一（当前只实现一角）。`cloth.center`：布平移。
- `goal.fold_fraction`：折痕位置，抓点到折痕的垂直距离 ÷ 布中心到角尖的距离（半对角线 16.97 cm）；1.0 = 角对角对折。`fold_slack`：弧线半径与材料长之比。
- 布尺寸、网格、粒径不变；布不可旋转。

包络两端：从角尖捏、弧线绷紧、布在基准位 ↔ 向内 2 cm 捏、松紧 0.93、布平移 3 cm。

### 6.12 cloth_unpleat

基准：12×26 cm 布带，中段叠一个 Z 形褶（三层），沿前后方向铺设。任务为捏自由端沿带方向拉平。

- `material_axis`：前后或左右铺设。`cloth.center`：平移。
- `pleat.width`：褶叠入宽度，24 mm 为实测下限。`crest_height`：褶隆起高度。
- `pull_scale`：拉距相对理论值的比例。`edge_inset`：捏取点离布边的距离。

包络两端：褶宽 40 mm、隆起 28 mm ↔ 褶宽 24 mm、隆起 16 mm、布带平移 3 cm。

### 6.13 cloth_unroll

基准：小支架横一根杆，布带卷在杆上 1.5 圈，尾端垂到桌面。任务为捏桌上的布带末端沿桌面拉，把布全部拉下展平。

- `pull_side`：支架在 −y 侧向 +y 拖，或镜像到 +y 侧向 −y 拖（2026-09-05 起；原「支架与拉向旋转 90°」不采用，沿 +x 拖终点出工作区）。`center_x` / `center_y`（杆位置）：支架朝 / 离机械臂平移、沿拉动方向平移。
- `roll.turns`：1 / 1.25 / 1.5 圈，圈数多则拉距长；1.75 圈在 28 cm 布上留不下平铺段。`roll.pitch`：层间距，只允许增大，上限随圈数、杆高派生。`bar_height`：杆高。

包络两端：1 圈、支架在基准位 ↔ 1.5 圈、层距 0.0158–0.0172（拉距 263 mm）、支架平移 3 cm、杆高 ±8 mm。

---

## 7. IL 数据量、oracle 覆盖与先例

### 7.1 变体数量对 IL 的充分性

- 连续轴使可生成的实例数无上限；数据规模的实际约束是物理耗时（FEM+IPC 绳任务约 46 min/episode），两三千 GPU 小时预算下每任务约数百条。
- 含 A 类离散轴的任务（diverter、linkbar_rotate_to_zone、rope_winding、rope_unwinding、ring_transfer、swap_crossing_sign、三个布料任务；band_untwist 待补镜像轴）每条离散组合下叠加连续抖动，模式数 2–12，IL 可学到「按场景或指令选择动作」。
- 仅有连续轴的任务（bar_through_hole、gate_cage_ball、unlink_c_ring）数百条数据在视觉上接近，IL 主要学到位置泛化。此为结构性限制；可选补充为视觉随机化，不改物理层。
- 拒绝采样与 oracle 胜任域会过滤掉最难实例；每档须报告 oracle 成功率与拒绝率（§4.4 第 4 步）。

### 7.2 oracle 通用性现状


| 状态                                | 任务                                                                                                                                                                   |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| oracle 由 layout / 实时状态推导，随机化后无需修改 | diverter、linkbar_rotate_to_zone、gate_cage_ball、swap_crossing_sign、unlink_c_ring、band_untwist、cloth_unpleat、cloth_unroll、rope_winding（绳长需重解）、rope_unwinding（两个出生点需重算） |
| oracle 存在但部分量手写或范围受限              | bar_through_hole、gate_cage_ball（z 高度手写）；cloth_fold（单角、不重观测）；ring_transfer（`hang_depth` 为实测值，环周长固定；仅 `carry` 路线可用；09-05 起三个搬运高度已改为推导）                                                    |


13 个任务均有 oracle；无一在第 3 节包络上验证过。每个 oracle 的胜任域由各自的不等式集合界定，包络边缘是否在域内由 §4.3 确认。

### 7.3 先例

纯仿真基准中「单一 oracle 覆盖随机化变体」的机制：


| 机制                 | 代表                                                                                                                                                      | 与本方案的关系                                                             |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| 特权状态脚本 oracle，参数化  | Ravens / Transporter Networks（Zeng 等，CoRL 2020）；DeformableRavens（Seita 等，ICRA 2021，报告演示器成功率）；FabricFlowNet（Weng 等，CoRL 2021）、Foldsformer 的 SoftGym 脚本专家 | 本方案主路线。本方案的「先观测后规划」为闭环脚本，比 Ravens 的开环脚本多一次测量                        |
| 逐实例搜索重解            | SoftGym（Lin 等，CoRL 2020）以仿真器为模型的 CEM                                                                                                                    | 每条演示需数百次回滚，本方案不采用                                                   |
| 物体系路点 + 运动规划，失败丢弃  | RLBench（James 等）；ManiSkill2/3 的 motion-planning 解法                                                                                                      | 本方案的拒绝采样与之同形；RLBench 的 variation（语义差异）/ episode（位姿随机）二分对应本文 A / B 类 |
| 少量示范 + 变换重放 + 仿真验证 | MimicGen（Mandlekar 等，CoRL 2023）；RoboCasa 数据生成                                                                                                           | 数据源不同（人类示范），「变换后验证、失败丢弃」相同                                          |
| 单示范 + 对应关系迁移       | DexGarmentLab（2025）                                                                                                                                     | 用于标出解析式路线的适用边界                                                      |


以上引用细节据记忆整理，成文前需核对原文。LIBERO 为人类遥操作数据，不属于 oracle 生成路线；domain randomization（Tobin 等 2017）对应视觉轴，不构成变体。