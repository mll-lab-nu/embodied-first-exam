# 绳索求解器后端迁移：PBD → FEM + IPC

本文记录迁移的进度、回滚判据与各阶段验收结果。计划正文（18 步）见批准的迁移计划，
穿模问题的分析见 [`untangle/debug-log/untangle_continuous_rope_contact_zh.md`](untangle/debug-log/untangle_continuous_rope_contact_zh.md) §9。

## 1. 为什么迁移

`untangle_continuous` 的状态是绳与绳的 over/under 关系。三次同参数运行在同一 step 1176
出现符号改变，检测器与 braid ground truth 由一致变为不一致。Genesis 的 PBD 把接触作为
每子步一次的位置投影，前面有 34 次形状约束迭代，且没有连续碰撞检测。

绳↔绳接触的归属决定了可选项：PBD 绳在 `pbd_solver` 内部，FEM 绳在 coupler
（`sap_coupler.py` 与 `ipc_coupler/` 中 `pbd` 出现 0 次，`legacy_coupler.py` 中 56 次）。

## 2. 回滚锚点

| 项 | 值 |
|---|---|
| 基线提交 | `0e9d320` |
| tag | `pbd-baseline` |
| 迁移分支 | `fem-ipc-migration` |
| 配置级回滚 | 任务配置的 `rope.model` 改回 `pbd_elastic_tube` |

阶段 1 之后 PBD 与 FEM 两条代码路径分离，配置级回滚不需要改代码。

**接缝管不到的一处：场景级求解器参数。** `sim.dt` = 0.01 与 `sim.substeps` = 4 在
`configs/env_configs/world_tabletop_v1.yaml`，由全部任务共用，且 `world/tabletop.py:453`
写死校验 `substeps == 4`。

Genesis 支持每个求解器自己的 `dt`（`base_solver.py:108`，缺省继承 `SimOptions`），
但 `substeps` 是场景级的（`simulator.py:107` 的 `substep_dt = dt / sim.substeps`，
第 281 行的子步循环）。给 FEM 单独设 `dt` 会让绳与机械臂按不同的时间前进，耦合器每个
子步交换力，这种不同步不可用。

修改共用值的代价：`substeps` 决定 PBD 的 `substeps × iterations` 总求解次数，
提高它会改变绳的行为（rope_contact 文档 §5.4 正是据此把它列为穿模的可调量）。
现有的摩擦 0.05/0.02、`move_steps` 260、`damp_every`、`max_taut_ratio` 0.90 都在
`substeps` = 4 下标定，刚体任务的接触频率同理。改共用值等于开一个 env baseline v2 并
重新标定全部任务，属于独立项目。

隐式 FEM 与 IPC 在大 `dt` 下稳定，但不要求大 `dt`。在 `substep_dt` = 2.5ms 下运行数值上
成立，代价是每个 scene step 做 4 次 Newton 求解。因此这一条按成本项处理，并入 §3.3 的
吞吐判据，不作为独立的阻断项。阶段 2 的 spike 仍需确认它能在该取值下运行。

## 3. 回滚判据表

四个量。迁移后的每个阶段都与本表比对；FEM 侧任一项达不到，用第 2 节的方式回滚。

### 3.1 untangle_continuous

实验设置：seed 0、word=(1,)、2 根绳、`segment_length` = 4mm、`radial_segments` = 8、
`substeps` = 4。

| 量 | PBD 基线 | 来源 | FEM 目标 |
|---|---|---|---|
| 穿模步号（抓下方那根） | 1176 | run10 / run11 / run13 三次一致 | 全程不变号 |
| 最小 `pair_gap`（抓下方那根） | 1.58 ~ 2.13mm | 同上 | ≥ 8mm |
| 最小 `pair_gap`（抓上方那根） | 1.60mm，且在 1.6 ~ 2.5mm 维持 214 步 | run12 | ≥ 8mm |
| 静止交叉间距 | 8.7mm（应为 12mm） | §3.4 扫描 | ≥ 11mm |
| 单 episode 墙钟 | 阶段 4 与 FEM 背靠背测 | 见 §3.5 | 判据见 §3.4 |
| oracle 成功率 | 阶段 4 与 FEM 背靠背测 | | 不低于基线 |

### 3.2 untangle（离散版）与 cable_routing

两项都在阶段 4 与 FEM 背靠背测：单 episode 墙钟、oracle 成功率。
cable_routing 另加一项：连接器飞出是否出现（历史问题，见
`untangle/untangle_connector_flyout_debug_zh.md`）。

### 3.3 吞吐判据

**在阶段 4 开跑前先定死这个数**，不要看到 FEM 的实测值之后再定。取值依据是 RoboMME
流水线的生成预算：一条 episode 现在多久、要生成多少条。

| 项 | 值 |
|---|---|
| 可接受的墙钟倍数上限 | 待定 |

实测（2026-08-06，RTX 4060 Laptop 8GB，同机同时段背靠背）：

| | FEM+IPC（无臂 demo） | PBD（pinch demo，带机械臂） |
|---|---|---|
| 端到端 `real` | 447.7s | 427.6s |
| 仿真段速度 | 8.34 steps/s | 31.14 FPS |
| 步数 | 1480 | ~2800 |
| 任务结果 | crossings 1→0，min_sep 36.6mm，terminal=True | crossings 1→0，min_sep 42.6mm，terminal=True |

端到端差 4.7%（两侧均为启动与编译开销占大头）。单步成本 FEM ≈ 3.7× PBD。

带臂实测（2026-08-06，`--arm` 模式，臂 `needs_coup=False` 不进 IPC）：

| | FEM+IPC+臂 solve | PBD+臂（pinch demo） |
|---|---|---|
| 端到端 `real` | 642.3s | 427.6s |
| 倍数 | **1.50×** | 基准 |
| 仿真段速度 | 7.27 steps/s（IK 开销约 13%） | 31.14 FPS |
| 任务结果 | crossings 1→0，min_sep 36.5mm，terminal=True，0 翻转 | crossings 1→0，min_sep 42.6mm，terminal=True |

带臂接触测试同样 PASS（交叉存活，min_separation 0.0096→0.0097，0 翻转）。

### 3.4 墙钟与成功率为什么不在阶段 0 测

回滚不依赖这两个量：`pbd-baseline` 的 tag 与 `rope_backends/pbd.py` 都长期保留，
PBD 路径在迁移全过程可运行，随时可以补测。

改为在阶段 4 与 FEM 背靠背测的理由：同一台机器、同一时段、同样的负载，两个数字的比值
才不含机器状态的差异。

方法用 shell 自带的 `time`，取 `real` 行，不带 `--viewer`（带窗口测的是渲染速度，
且需要手动关闭窗口）：

```bash
time python -m prototypes.untangle_continuous_physical_pinch_demo \
  --verbose --seed 0 --segment-length 0.004 --trace
```

同一条命令在 `rope.model` 的两个取值下各跑一次。

## 4. 基线归档

| 任务 | trace | 视频 | 状态 |
|---|---|---|---|
| untangle_continuous 抓下方那根（无窗口、录像） | `untangle/debug-log/run11_2026-08-05_grasp_under_strand_trace.log` | `runs/untangle_fail_pull_under_strand.mp4` | 已归档 |
| untangle_continuous 抓上方那根（无窗口、录像） | `untangle/debug-log/run12_2026-08-05_grasp_over_strand_trace.log` | `runs/untangle_solve_pull_over_strand.mp4` | 已归档 |
| untangle_continuous 抓下方那根（viewer） | `untangle/debug-log/run13_2026-08-06_viewer_grasp_under_strand_trace.log` | 无 | 已归档 |
| untangle_continuous 完整 episode（默认抓上方那根） | `untangle/debug-log/run14_2026-08-06_full_episode_baseline_trace.log` | 无 | 已归档。min `pair_gap` 1.52mm，step 900 与 1109 两次变号 |
| untangle、cable_routing | 阶段 4 与 FEM 背靠背跑 | | |

`runs/` 在 `.gitignore` 内，视频不进版本库。trace 归档进 `debug-log/`。

## 5. 阶段进度

| 阶段 | 步 | 状态 |
|---|---|---|
| 0 基线与回滚保障 | 1 分支与 tag | 已完成 |
| | 2 归档 PBD 接触基线 | 已完成（run10~run14，穿模步号与 `pair_gap` 已读出） |
| | 3 判据表 | 本文 §3。墙钟与成功率移至阶段 4，吞吐上限待定 |
| 切片 1 FEM 绳部署 | spike 脚本 + pyuipc 安装 + 首轮标定 | **已完成** 2026-08-06。E=1e5/nu=0.45/rho=650/d_hat=2mm：静止中心线间距 9.66mm（理论 10mm），沉降 50 步收敛，6.8~9.7 steps/s |
| 切片 2 FEM attachment | `is_fixed` + animator 接线，三项验收 | **已完成** 2026-08-06。anchor 漂移 0.000mm；follow 抬 60mm 滞后 ≤0.18mm；**contact 抬 80mm 无翻转**（dz 全程 +8.2~+8.7mm，min_dist ≥2.0mm）。log 归档 `untangle/debug-log/run15{a,b,c}_2026-08-06_fem_ipc_*.log` |
| 切片 3 无臂 demo | 接触测试 + 解题运行 + 背靠背墙钟 | **已完成** 2026-08-06。接触测试 PASS（run17：pair_gap 全程 9.4~9.5mm，无翻转，交叉存活）；解题运行 PASS（run18：crossings 1→0，终态间距 36.6mm，0 次翻转，terminal=True）；背靠背墙钟见 §3.3（端到端 +4.7%，单步 ≈3.7×） |
| 机械臂接入（`--arm`） | 臂 `needs_coup=False` 留在 IPC 之外（符合 §3.5 抓取设计），IK 每步驱动，带跟随指令手位 | **已完成** 2026-08-06。接触测试 + solve 均 PASS（run19/run20），端到端 1.50× PBD（§3.3）。external_articulation 路线未启用，留作真实夹持力学的将来项 |
| 推迟 | 后端接缝（48 处调用点）、锁定 preset 适配、另两个任务迁移、改名 | 切片验收后再排 |

锁定 preset 适配的已知点（2026-08-06 带臂运行发现）：`substeps=1` 下 substep_dt=10ms，
刚体接触的 `timeconst` 被 Genesis 从 MJCF 的 0.005 自动抬到 0.02（要求 ≥ 2×substep_dt），
刚体↔刚体接触变软。本 demo 中刚体接触仅剩臂的自碰撞（大半已被中立位过滤排除），无实际影响；
并回正式任务时刚体接触参数需按 substep_dt 重新核对。

部署阶段 1（后端接缝）2026-08-07 完成：`rope_backends/{__init__,pbd,fem_ipc}.py` 协议落地；
untangle_continuous 生产路径全部调用点改走协议（untangle / cable_routing 留待各自迁移轮，
避免超出 1176 回归的覆盖面）；回归通过——清扫后仍在 step 1176 翻转（gap 1.70mm，
落在同代码三次运行 1.58/1.72/2.13mm 的散布内），step 1 各列逐位相同。
原计划的"FEM 拖拽原语"取消：pinch demo 的 oracle 用 `PBDHandleDragPrimitive` 拖刚体插头
（零求解器调用，grep 验证），绳经 `follow_link` 跟随——该操作已在协议内。

执行顺序 2026-08-06 起改为垂直切片（用户决定）：先用最少代码钉死三个未知数
（pyuipc 可装性、顶点约束接线、吞吐），切片期间不改任何现有文件。原 18 步计划的
阶段 1（后端接缝）后移。切片场景用 `dt=0.01, substeps=1`：stock IPC coupler 每子步
`advance()` 一次但拿整个 `sim.dt`（`ipc_coupler/utils.py:93`），即按 `substeps=1` 设计，
锁定 preset 的适配放到集成期。
