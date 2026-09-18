# FEM+IPC 单步耗时测量

状态：**已定位，暂停**。成本 = 每次 `_ipc_world.advance()` 约 130 ms × `substeps`，加约 50 ms/根绳。
那 130 ms 与网格规模、Newton 上限、计算后端、刚体数量都无关。**耗时本身一步也没有降低**——
本轮产出的是定位、度量工具，以及一条待验证的方案，不是提速。

一次 untangle 单 move 的完整物理跑约 46 分钟，这个速度不支持迭代。本文记录为定位
成本所做的测量，包括被排除的假设，避免同样的推断被重复一遍。

测量工具：`run.bench_steps=N`（实现在 `topogym/supervision/step_bench.py`）。它把建好
的场景空跑 N 步——场景静止、机械臂不动——所以量到的是一步的地板价。前一半步数作为
warmup 排除在计时之外，避开 JIT 编译与 libuipc 首帧接触装配。

报告把一步拆成 `solver` 与 `hooks` 两部分。拆分办法：本仓所有每步钩子都把自己装成
scene 的**实例属性**（`scene.step = wrapped`），而 `type(scene).step` 是未被包装的类
方法，直接调它就绕过了 attachment manager、每个端点一个的 connector latch、以及 FEM
的 follow-band 同步。

## 测量结果（2026-08-11，untangle，三绳，RTX / WSL2）

命令：`python -m demos.entangle.untangle_physical_handle_demo run.bench_steps=100 <覆盖>`

| 变体 | per_step | solver | hooks | hooks 占比 | per_ipc_advance |
|---|---:|---:|---:|---:|---:|
| 基线 | 660 ms | 643 ms | 17 ms | 3% | 161 ms |
| `task.rope.fem.newton_max_iterations=64` | 664 ms | 635 ms | 29 ms | 4% | 159 ms |
| `run.lite=true` | 685 ms | 645 ms | 40 ms | 6% | 161 ms |
| `env.sim.substeps=1` | 未跑完 | | | | |

`per_ipc_advance` = `solver / substeps`。`couple()` 每 substep 调一次
`_ipc_world.advance()`（`ipc_coupler/coupler.py:818`），基线 `substeps=4`。

`env.sim.substeps=1` 被 `topogym/world/tabletop.py:518` 的锁定预设校验拒绝，报
`Locked preset requires sim.substeps=4`。该校验按设计生效。

## 已排除的假设

| 假设 | 判据 | 结论 |
|---|---|---|
| 表面网格过密 | 缓存的 `*_fem_ipc_tube.obj`：每根绳 362–378 顶点、720–752 三角；三根合计约 1100 顶点、2200 三角 | 规模本身很小 |
| 四面体过多 | `run.lite=true` 的 tetgen 输出：802 + 602 + 644 = 2048 个四面体，基线约 3000。少三分之一，耗时 643 → 645 ms | 成本与网格规模无关 |
| Newton 迭代撞上限 | 上限 1024 → 64，耗时 643 → 635 ms，在噪声内 | 求解器本来就在很少的迭代内收敛 |
| 每步钩子的 GPU 往返 | `hooks` 占 3–6%，17–40 ms | 八层包装器合计可忽略 |
| 整条机械臂进入 IPC | `topogym/tasks/entangle/untangle.py:222`：FEM 下机器人是 `Rigid(needs_coup=False)` | 早已排除在 IPC 之外 |
| rigid-rigid 走 IPC | `rope_backends/fem_ipc.py`：`enable_rigid_rigid_contact=False`、`enable_rigid_ground_contact=False` | 早已关闭 |
| dt 过小导致步数过多 | `dt=0.01`；步数由 primitive 的 `move_steps` 决定，不由 dt 决定 | 与步数无关 |
| 首次 JIT 编译 | 建场景约 70 秒含编译；bench 的 warmup 段已排除 | 不在计时内 |

IPC 世界里实际只有：地面、桌子、三根 FEM 绳。16 个 hole 是 `collision: false`，走
decoration 材质（`needs_coup=False`）；board 与 peg 在本任务配置里 disabled。

## 结论：成本 = 每次 advance 约 130 ms × substeps

把所有场景按**实际** substeps 归一之后，四次测量落在同一区间：

| 场景 | 实际 substeps | FEM | per_step | 每次 advance |
|---|---:|---|---:|---:|
| spike（2 绳 + 地面），cpu | 1 | 3772 四面体 | 125 ms | 125 ms |
| spike（2 绳 + 地面），gpu | 1 | 3772 四面体 | 131 ms | **131 ms** |
| inspect 去掉机械臂（2 绳 + 桌 + 11 个箱 + 2 插头） | 4 | 3809 四面体 | 448 ms | **112 ms** |
| inspect 带机械臂（+ Franka 全臂） | 4 | 同上 | 442 ms | **110 ms** |
| untangle demo（3 绳 + 桌 + 臂 + 6 插头 + 16 hole） | 4 | ~3000 四面体 | 643 ms | **160 ms** |

**机械臂的贡献为零**（442 vs 448，在噪声内）。从一个地面到"桌子 + 11 个箱 + 2 个做过凸分解的
插头 + 整条 Franka"，每次 advance 的耗时没有上升。所以刚体侧不是成本来源，
`_store_gs_rigid_states` 的全量设备→主机拷贝这个假设不成立。

剩下两个因素：

- **每次 advance 约 130 ms 的固定成本**，与网格规模、Newton 上限、backend、刚体数量都无关
- **绳的数量**：2 根 112 ms、3 根 160 ms，约 50 ms/根

因此 `substeps=4` 就是四倍算力，这是目前唯一的量级杠杆。

### 一处需要更正的记录

2026-08-11 早些时候我先提出"substeps=4 是四倍算力"，随后读到
`genesis_ipc_vertex_constraints` 的 substep-aware dt 补丁，就把整个判断收回了。收回过头了：
那个补丁修的是**时间基准**（IPC 从按整个 `sim.dt` 前进改为按 `substep_dt`），
**计算量仍然是每 substep 一次 advance**。计算量那一半当时是对的。

之后 spike 的数字又强化了这个错误方向，因为 bench 报的 substeps 取自配置（4），
而 spike 自建 scene 时硬编码 `substeps=1`（`tests/fem_ipc_rope_spike.py:137`），
每次 advance 的耗时被报小了 4 倍。已改为读场景实际值
（`scene.sim._substeps`）。

## 可行的方向

降 `substeps` 是唯一的量级杠杆，但它被一个实测的回归挡着：FEM 预设 v1.0 用 substeps=1 时，
边缘搁置的自由端插头在 10ms 刚体子步下走位 21mm/百步，v1.1 因此回到 4，
`topogym/world/tabletop.py` 的锁定预设校验会拒绝这个覆盖。

所以方向不是"改 substeps"，而是"换一种方式解决插头走位，然后 substeps 才能降"：

- 静置期间的插头本来就有 `ConnectorLatch` 在做运动学固定（spawn latch 就是干这个的）。
  若把它的覆盖范围扩到所有未被抓取的插头，走位问题不再依赖刚体子步长度
- `gs.options.SimOptions` 有 `substeps_local`（`simulator.py:109`），若它支持按求解器分别设
  子步数，就可以让刚体保持 4、IPC 降到 1。未验证

两条都成立的话，全部 FEM 任务提速约四倍：untangle 单 move 从 46 分钟降到约 12 分钟，
cable_routing 从约 3.4 小时降到约 50 分钟。

## 待验证的方案：IPC 每步 advance 一次，刚体保持 4 个子步

三种组合的区别：

| | IPC 的 dt | 每步 advance 次数 | 时间基准 | 算力 | 插头走位 |
|---|---|---:|---|---:|---|
| stock genesis 1.2.1 | 完整 `sim.dt` | 4 | 错（IPC 快 4 倍） | 4× | — |
| 本仓现状（已打补丁） | `substep_dt` | 4 | 对 | 4× | 无 |
| 待验证 | 完整 `sim.dt` | **1** | 对 | **1×** | 预计无 |

关键点：插头走位是**刚体子步长度**的问题（10ms 时走位 21mm/百步，2.5ms 时约 0），
与 IPC 无关。所以降的是 IPC 的 advance 次数，而不是 `sim.substeps`，刚体仍然跑 4 个
2.5ms 子步，那条回归不会回来。

落点：`couple(self, f)` 的 `f` 就是子步序号（`coupler.py:790`），而本仓已经有
`VertexConstraintIPCCoupler(IPCCoupler)` 这个子类（`genesis_ipc_vertex_constraints.py`）。
加一个 `couple` 覆写，`f` 不是最后一个子步就直接返回，同时把
`_substep_aware_build_cfg` 的 dt 改回完整 `sim.dt`。约 10 行。

代价：绳与刚体的耦合从每 2.5ms 一次变为每 10ms 一次。需要验证两件事——
`run.bench_steps` 是否掉到约 160 ms/步；插头静置 100 步的位移是否仍接近 0。

建议做成默认关闭的开关，测出数据再决定是否翻默认值。

## 另一条线：cable_routing 的路点密度

cable_routing 单次完整跑约 7700 步，其中 7100 步来自 `physical_handle.segment_steps`
里 18 个路段的步数之和。它只有 1 根绳，每步成本比 untangle 低，3.4 小时基本是步数堆出来的。
这与本文的 130 ms 是两个独立问题：一个是每步多贵，一个是要跑多少步。
路段步数是否配得过密，需要单独看。

## 暂停时的工作方式

`run.build_only=true`（约 90 秒）**不是提速**，它跳过物理，只确认配置解析、场景构建、
契约校验、primitive 构造这一段。适用范围是「改动只涉及参数怎么传、场景怎么搭」；
改动涉及物体怎么动时它不适用，仍然要跑完整的。

物理行为的确认按批次跑，不逐次等待。见 `demos/README.md`。
