# Untangle 连续版实现计划：braid-word 生成 + 几何拓扑 + lift-test

> 日期：2026-07-26
> 来源：策划案（连续版绳子解缠场景设计）+ 现有离散版代码勘查。
> 关系：本文规划的是 untangle 的**第二个变体（连续版）**，与现有**离散版**（固定孔板 + 端点插孔/拔孔）并列，尽量复用同一套 PBD 绳子管线与抓取原语。离散版实现见 `topogym/tasks/entangle/untangle.py` / `topogym/envs/untangle_mdp.py`；重构史见 `[untangle_redesign_plan_zh.md](untangle_redesign_plan_zh.md)`。
> 设计原则：延续 benchmark 定位——**隔离拓扑推理、剔除低层控制混杂、拓扑事件原子性、自带 ground truth**。

---

## 0. 目标与范围（MVP 冻结）

**离散版 vs 连续版一句话对比**


|       | 离散版（已实现）                                 | 连续版（本计划）                      |
| ----- | ---------------------------------------- | ----------------------------- |
| 初始态   | 绳两端插在固定孔板的孔里                             | 几根绳缠在一起，一端锚在插线板，另一端自由         |
| 任务    | 拔/插孔重排端点消除交叉                             | 抓绳身把缠绕理顺、放到一边                 |
| 拓扑判定  | **组合**：网格孔索引上算线段相交（`untangle_mdp.py`）    | **几何**：PBD 粒子俯视投影上算曲线相交       |
| 成功    | crossings/knots/overlaps 全空              | 交叉=0 的几何 proxy + 物理 lift-test |
| GT 来源 | config 里手写 `strands.points` + `z_offset` | **braid word 解析生成，逆序即最优解**    |


**MVP 冻结（对齐策划案"最小版本"）**：2~~3 根绳；braid 长度 2~~5；一端锚定在插线板、另一端自由；离散 primitive 动作（`grasp` / `lift_move_place` / `release` / `pull_free_end`）；几何 proxy + lift-test 双层判定；braid 逆序自带 oracle。连续控制（VLA）留到之后。

**明确不做（MVP 阶段）**：真实夹爪-绳摩擦抓取（用 kinematic attachment 绕过，见 §3.5）；真实打死结（braid 只做可解缠的相邻交叉，不做需要穿端点的 knot）；>3 根绳、braid>5、双端自由。

---



## 1. 复用地图（先读后写——哪些直接用现成的）

连续版**不重写绳子物理**，只换"初始几何来源"和"拓扑判定方式"。下表是已勘查确认、可直接复用的符号：


| 需求           | 复用符号（文件）                                                                                        | 说明                                                               |
| ------------ | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 样条中心线        | `catmull_rom_centerline`, `sample_polyline`（`topogym/world/rope.py`）                            | braid 控制点 → 等弧长平滑中心线                                             |
| 圆管网格         | `make_elastic_tube_mesh`, `write_obj`, `tube_morph`（同上）                                         | 平行输运 tube，竖直段也不塌（锚点出线用得上）                                        |
| PBD 求解/材质    | `pbd_options`, `elastic_material`（同上）                                                           | 单源 `prefabs.rope_pbd`，物理参数零改动                                    |
| 端点粒子选取       | `endpoint_particle_indices`（同上）                                                                 | 锚定端选固定粒子带                                                        |
| **抓绳中段并拖拽**  | `PBDParticlePinchDragPrimitive`（`topogym/primitives/pbd_particle_pinch.py`）                     | 夹一组追踪粒子、lift-test 抓取校验、follow-error 门限、逐段拖拽——**连续版动作原语的核心，几乎照用** |
| kinematic 附着 | `AttachmentManager`（`topogym/primitives/attachment.py`）                                         | 抓取=把粒子焊到手坐标系，抓取成功率恒 100%                                         |
| 桌面基线/相机/机器人  | `StandardTabletopSceneBuilder`, `initialize_franka_controller`, `recording_session_from_config` | 与所有任务同一 tabletop V1                                              |
| 数据集录制        | `dataset_writer_or_null`（`topogym/data`）                                                        | RoboMME 结构 H5，subgoal 标签复用                                       |
| 布局随机化 seam   | `randomize_task_cfg`（`topogym/generation/layout_randomization.py`）                              | 只需在 `_REGISTRY` 加 `untangle_continuous` 条目                       |
| episode 契约   | `build_untangle_episode_spec` 模式（`topogym/generation/untangle_generator.py`）                    | 照抄写一个 continuous 版                                               |


**不复用**：`UntangleHighLevelEnv`（网格组合拓扑，与连续版几何判定不兼容）、`plan_next_untangle_move`（在孔上贪心）、`ConnectorLatch`/插头连接器（连续版端点不插孔）。

---



## 2. 新增组件总览



### 2.1 架构决策（✅ 已拍板 2026-07-26）

**连续版做成独立 sibling 任务** `untangle_continuous`，而不是给 `untangle` 加 `--mode continuous` 开关。理由：

- 拓扑判定、成功判定、场景构建、planner **四处都不同**，塞进离散版会让 `untangle.py`/`untangle_mdp.py` 长满 `if mode==`，违反本仓 CLAUDE.md 的"简单/外科手术"守则。
- 独立 task id 让 config 双轴架构（layer × baseline，见记忆 `config-baseline-architecture`）保持干净，episode manifest、数据集 task 字段天然分开。
- **共享的是 module 层**（`world/rope.py`、`primitives/`），不是 task 层——这正是 `world/rope.py` 抽出来的初衷。



### 2.2 新增文件清单

```
topogym/generation/braid.py                 # 纯 Python：braid word → 控制点 + GT + 最优解
topogym/supervision/rope_topology.py        # 从 PBD 粒子算几何交叉 + 成功 proxy + lift-test
topogym/tasks/entangle/untangle_continuous.py        # 连续版场景构建（插线板锚 + 自由端，无孔板）
topogym/planning/untangle_continuous_planner.py  # oracle = 逆 braid word
topogym/generation/untangle_continuous_generator.py  # episode spec 契约
configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml
prototypes/untangle_continuous_inspect_demo.py   # 无机器人：看初始态 + 校验 GT
prototypes/untangle_continuous_solve_demo.py     # 机械臂跑 oracle 解缠
tests/test_braid.py                          # braid 生成器纯单测（不依赖 Genesis）
tests/test_rope_topology.py                  # 几何交叉检测单测（合成 polyline）
```

改动现有（小、外科手术）：`layout_randomization._REGISTRY` 加一条；`topogym/generation/__init__.py`、`topogym/planning/__init__.py`、`topogym/supervision/__init__.py` 导出新符号。

---



## 3. 模块详细设计



### 3.1 braid 生成器（`topogym/generation/braid.py`，纯函数、无 Genesis）

**这是连续版最大的新增，也是"自带 GT"的来源。** 与策划案第 1 节一致，用辫群参数化，而不是随机撒绳 settle。

**数据流**

```
seed ──► sample_braid_word(n_strands, length, seed)   # e.g. [+1, -2, +1]  (σ1 σ2⁻¹ σ1)
      ──► reduce(word)                                  # 化简：消掉 σ_i σ_i⁻¹，得有效交叉数
      ──► braid_to_control_points(word, layout)         # 每根绳一条解析 3D 控制折线
      ──► BraidSpec(control_points, crossing_sequence, optimal_untangle_sequence)
```

**接口草案**

```python
@dataclass(frozen=True)
class BraidCrossing:
    over_strand: int      # 上方绳（σ_i 正号=第 i 根从 i+1 上方过）
    under_strand: int
    position_frac: float  # 沿主轴 0~1，用于放置 + planner 定位抓取点
    sign: int             # +1 / -1

@dataclass(frozen=True)
class BraidSpec:
    n_strands: int
    word: tuple[int, ...]                 # 化简后的有效 braid word
    control_points: dict[int, np.ndarray] # strand_idx -> (K,3) task-frame 控制点
    crossings: tuple[BraidCrossing, ...]  # 俯视 GT 交叉序列
    optimal_sequence: tuple[...]          # 逆 reduced word = 最少操作解缠序列（步数下界）

def build_braid_spec(*, n_strands, length, seed, layout) -> BraidSpec: ...
```

**几何生成（关键实现点，对齐策划案）**

- n 根绳平行铺开（沿 +x 主轴，等间距 y 通道），一端（-x 端）锚在插线板。
- 逐个处理 word 里的 σ_i：在主轴对应弧长位置，让第 i、i+1 通道的两根绳做一次相邻交叉——上方绳抬高 **≥ 2×绳半径**（否则 settle 时穿模，这是离散版 flyout blowup 的病根，见 `[untangle_connector_flyout_debug_zh.md](untangle_connector_flyout_debug_zh.md)`）。
- 交叉处 xy 用平滑过渡（两通道互换 y），z 只给上方绳一个凸起、下方绳贴桌——**用** `catmull_rom_centerline` **生成时天然圆滑**。
- 输出的 `control_points` 直接喂给 §3.2 的 tube mesh 管线。

**为什么值钱**：`optimal_sequence` = 化简 braid word 的逆，给出**步数下界**，评测能算"实际步数 / 最优步数"效率指标——随机生成给不了。`crossings` 是判定 GT，用于 §3.3 的检测器自校验。

**单测（不依赖 Genesis，快）**：化简正确性（σ_i σ_i⁻¹ → 空）；有效交叉数 == GT；逆序 word 施加后交叉数归零；控制点在 workspace 界内、上方绳 z 抬够。

### 3.2 连续版场景（`topogym/tasks/entangle/untangle_continuous.py`）

仿 `UntangleSceneBuilder` 结构，但：

- **无孔板、无插头连接器、无 peg**。
- **插线板（power strip）**：一个矮长方体（`gs.morphs.Box`, fixed），沿 -x 端横跨 n 个通道，视觉说明"绳从这里长出来"。可选 `fixed_terminal_mesh`（`world/rope.py` 已有）做每根绳的出线口。
- **绳**：`control_points = BraidSpec.control_points[i]` → `catmull_rom_centerline` → `make_elastic_tube_mesh` → `tube_morph` + `elastic_material`（**全部复用 §1**）。
- **锚定**：只锚 -x 端一小带粒子（`endpoint_particle_indices` + `fix_particles`）到插线板；自由端不锚。
- **settle + reject**：`build()` 后跑 settle 到最大粒子速度 < ε；重投影数交叉，偏离 GT 或出现意外自结 → 抛可捕获的 `BraidRejected`，demo/generator 换 seed 重试（策划案第 1 节的有效性校验）。

复用 `StandardTabletopSceneBuilder` + `pbd_options`。**substeps 注意**：tabletop V1 preset 把 `sim.substeps` 锁死 4；若 settle 稳定性不够，需给连续版开 preset 例外（同离散版 redesign §3 的记录），先靠加 XPBD 迭代顶。

### 3.3 几何拓扑检测器（`topogym/supervision/rope_topology.py`）

**与离散版彻底分家**：离散版在网格孔索引上算（`untangle_mdp._segments_cross`）；连续版在**实际粒子**上算。

```python
def strand_polylines(rope_entities, *, project="xy", smooth=True) -> dict[int, np.ndarray]:
    # get_particles_pos() -> 每根绳一条俯视 polyline；smooth 时拟合同一条渲染样条
def count_crossings(polylines, z_by_strand) -> list[GeoCrossing]:
    # 两两 polyline 2D 线段相交；over/under 由交点处粒子 z 决定
def min_inter_strand_distance(polylines) -> float:
def is_geometrically_untangled(polylines, *, sep_threshold) -> bool:
    # 交叉数==0 且 min 距离 > 阈值（对应"放到一边"）
```

**硬守则（抄 redesign §3）**：交叉判定用的俯视 polyline **必须和渲染用的是同一条平滑曲线**，否则会出现"像素里有、GT 里无"的脱节。→ 检测器直接从渲染样条采样。

**自校验门（Phase 2 验收）**：settle 后检测器数出的交叉数 == `BraidSpec.crossings` 数量，在全部回归 seed 上一致。这是几何检测器可信的证据。

### 3.4 成功判定（`topogym/supervision/rope_topology.py`）

两层，对齐策划案第 2 节：

- **几何 proxy（每步算，作中间指标/reward shaping）**：`is_geometrically_untangled`。
- **物理 lift-test（episode 结束金标准）**：依次抓每根绳自由端提到高度 h，检查其余绳 zmax 仍 < ε。纯物理、无法被感知层作弊糊弄，且 demo 视频好看。实现复用 `PBDParticlePinchDragPrimitive` 的抓取+lift 段（只抓不放）。

```python
def lift_test(controller, rope_entities, free_ends, *, lift_h, other_zmax_eps) -> LiftTestResult
```



### 3.5 动作原语与规划（`topogym/planning/untangle_continuous_planner.py`）

**动作**（策划案第 3 节，离散 primitive）——全部搭在 `PBDParticlePinchDragPrimitive` + `AttachmentManager` 上：

- `grasp(x, y)`：吸附到最近绳段，返回抓的是哪根绳、弧长位置。=原语的 approach+close+lift-test 段。
- `lift_move_place(x', y', height)`：`height` 决定从其他绳上方跨过还是贴桌拖——**over/under 选择正是拓扑推理核心**。=原语的逐段拖拽（target_centers）。
- `release()` / `pull_free_end(rope_i, direction, dist)`。

**抓取用 kinematic attachment，不做摩擦抓取**（对齐 redesign §2 哲学 + 记忆 `untangle-connector-phase-b`）：`grasp` 成功后把最近几个粒子焊到手坐标系，抓取成功率恒 100%，把低层控制误差排除出评测变量。会上提过 Genesis 夹爪-PBD 接触不确定，这条正是绕过它。

**oracle 规划器 = 逆 braid word**：对 `BraidSpec.crossings` 逆序，每个交叉抓其 over-strand 在 `position_frac` 附近的绳段，`lift_move_place` 到能解开该交叉的位置（跨到 under 绳另一侧）。每步后用 §3.3 检测器确认交叉数下降。这给出可回放的最优演示序列。

### 3.6 配置 / episode spec / 随机化

- `untangle_continuous_topogym_tabletop_v1.yaml`：`rope:` 块复用 `${prefabs.rope_pbd.*}`（与离散版同源）；新增 `braid:`（`n_strands`, `length`, `main_axis`, `channel_spacing`, `over_lift`, `sep_threshold`, `lift_h`）与 `power_strip:` 几何；删掉 `holes`/`peg`/`anchor_pins.connector`。
- `build_untangle_continuous_episode_spec`：照抄 `untangle_generator.py`，把 `braid` 参数写进 variant identity，`seed` 成为真正的布局种子（离散版里 seed 是保留字段，连续版里 seed 真正驱动 braid 采样）。
- 随机化：在 `layout_randomization._REGISTRY` 加 `"untangle_continuous"`——但**注意**：braid 结构（交叉数/序列）是 GT，不能 jitter；只能 jitter **不改拓扑的** 量（如 `channel_spacing`、`over_lift`、锚点微扰）。braid 难度用 `length` 桶（easy/default/hard → 2/3/5）实现，走 episode seed，不走 jitter seam。

---



## 4. 分阶段实施顺序（每阶段一个验收门）


| 阶段                       | 交付                                            | 验收门（可自动化）                                                            | 测试                                                   |
| ------------------------ | --------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------- |
| **P0** braid 生成器         | `braid.py` + `BraidSpec`                      | 化简/有效交叉数/逆序归零/界内，全绿                                                  | `test_braid.py`（纯，秒级）                                |
| **P1** 连续场景（无机器人）        | `untangle_continuous.py` + inspect demo       | settle 后无爆解/飞粒子；reject 率可测                                           | 手动 viewer（用户跑）+ settle 稳定断言                          |
| **P2** 几何检测器 + lift-test | `rope_topology.py`                            | **检测器交叉数 == BraidSpec GT**，全 seed 一致；lift-test 在已解态返回 True、缠绕态 False | `test_rope_topology.py`（合成 polyline）+ 场景内断言          |
| **P3** 动作原语              | grasp/lift_move_place 单步 smoke                | 单个交叉能被一次 lift_move_place 解开，交叉数 -1；抓取成功率 100%                        | solve demo `--max-moves 1`                           |
| **P4** oracle 全解         | `untangle_continuous_planner.py` + solve demo | 从 braid 初态跑到几何 proxy=0 且 lift-test=True；步数==最优                       | solve demo 全流程 + 录像                                  |
| **P5** 数据集 + 随机化 + sweep | episode spec、dataset、randomizer、sweep 脚本      | H5 结构合法；多 seed 稳定；效率指标（步数/最优）落盘                                      | `verify_dataset_recording.sh` + `stability_sweep.sh` |


依赖：P0 是纯的、可最先并行做；P2 依赖 P1 出场景、P0 出 GT；P4 依赖 P0（逆序）+ P2（每步校验）+ P3（原语）。

---



## 5. 关键风险与设计权衡（把"隐形决策"摆上桌）

1. **PBD 交叉稳定性**：初始上方绳 z 抬 <2×半径 → settle 穿模爆解（离散版 flyout 血泪史）。缓解：生成时强制 `over_lift ≥ 2×radius`；settle-and-freeze；必要时给连续版开 substeps preset 例外。
2. **夹爪-PBD 接触脆弱**：MVP 用 kinematic attachment 绕过（抓取恒成功），真实夹持力学之后再换。这是有意的"控制混杂剔除"，不是偷懒。
3. **GT / 渲染脱节**：交叉检测与 mesh 必须同一条样条（§3.3 硬守则）。
4. **reject 率**：绳半径/桌面摩擦决定 settle 后绳是否滑开导致交叉数偏离 → reject 重采。建议 P1 先做个小 sweep 找摩擦/半径安全区（策划案第 6 节）。
5. **架构决策（sibling task）**：见 §2.1，推荐独立 `untangle_continuous`；若拍板做 flag，则 §2.2 文件清单折叠进现有文件、并接受 `untangle.py` 变复杂。

---



## 6. 验收标准（整体）

1. 全部回归 seed 上，**几何检测器交叉数 == braid GT 交叉数**（判定可信）。
2. oracle 能把每个生成实例从初态解到**几何 proxy=0 且物理 lift-test 通过**。
3. oracle 步数 == braid 最优步数（逆序下界）；效率指标落盘。
4. 同 seed 下 braid 初态 + oracle 端点轨迹确定；中段物理不要求逐帧一致，但**全程稳定无爆解/飞粒子**。
5. 评测分辨率下各色绳、缠绕/解开状态可清晰区分。

---



## 7. 决策记录（2026-07-26 已拍板）

1. ✅ **架构**：独立 `untangle_continuous` 任务（非 `--mode` 开关）。
2. ✅ **锚定**：**单端锚**——-x 端锚在插线板，另一端自由（可被抓/甩动）。lift-test 的"自由端"= 非锚定端。
3. ✅ **动作层**：MVP 只做 `grasp` + `lift_move_place` + `release`（够 oracle 逆 braid 解缠）；`pull_free_end` 延后到需要时再加。
4. ⏳ **难度轴（未定，非阻塞）**：暂定 `n_strands=3` 固定，braid `length` 桶 easy/default/hard = 2/3/5 交叉。是否让 n_strands 也进难度轴，等 P4 跑通后再定。

