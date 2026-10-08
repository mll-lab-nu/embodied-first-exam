# Slotted Post Ring oracle（代码迁移，未验证）

2026-10-04：迁入外部交接材料中的控制器与诊断代码。按用户最新要求，**不运行测试、几何生成、仿真、审计或录像；物理、几何和评估约束坚持本地 v15**。本次迁移不产生本地成功证据。

来源：用户附件 `05823cab-9484-4169-b37b-4fe5e7dd373a/pasted-text.txt`，SHA-256 为
`3744ce0cb534f88bf35175db4e85ef72b0e0da44caca9a996dedcaf564d02b4c`。
附件标注来源仓库基线 `e49b116e`，其工作区改动未提交。

## 迁入代码

| 文件 | 内容 |
| --- | --- |
| `geometry.py` | 从当前 Task/观测读取几何、环盘与绳的穿越、环是否套柱、固定件包围盒；支架按实际存在读取，端盘法向由当前网格获得 |
| `kinematics.py` | ALOHA 多种子 IK、FK、关节限位、分支跳变和机器人碰撞采样 |
| `policy.py` | 12 阶段 JOINT_ABS 生成器、候选搜索、失败回退、实测 TCP 同步、伺服及拓扑判断 |
| `runtime.py` | 读取当前公开 release profile，通过共享 `SessionPolicyRunner` 执行策略 |
| `audit.py` | 机器人几何导出、逐 tick 连续性、当前模型身份、v15 绳有效性持续窗口及目标稳定窗口诊断 |
| `scripts/oracle_runners/run_slotted_post_ring_oracle.py` | 冻结源码及本地 tooling、由 Session 执行、记录实际动作与逐 tick 测量、资源监控 |
| `scripts/audit_slotted_post_ring_oracle.py` | 独立只读诊断入口；当前不执行 |

外部 146 个实验片段、开发服务器及其内存检查点不接入活动执行链；原始附件保留这些材料。

## 与本地 v15 的差异及处理

| 项目 | 交接实现 | 本次处理 |
| --- | --- | --- |
| 槽宽 | easy/medium/hard 改成 34 mm | 保留本地 28 mm；已有 clearance36 也保留原值 |
| 端盘与绳布局 | 固定支架、端盘直立、桌面双余量圈、约 1.105 m 绳 | 保留本地平放端盘、原绳路线与长度，不增加支架 |
| 绳材料与网格 | E=1 MPa，3.5 mm × 12 边 | 保留本地 E=50 kPa，共享 1.375 mm × 24 边配方 |
| 弹性参考 | `stress_free_spawn` 弯曲参考 | 不加入该开关，保留本地材料参考及现有 FEM 接口 |
| IPC 接触 | 新增指垫摩擦 0.8、固定件接触选项、同步容差 5 mm | 不导入 `ipc_robot` 或放宽同步；沿用本地接触与 2 mm 同步保护 |
| 时序 | runner 固定 v12 常量 | 从本地 `release_profile.environment_inputs` 和 `rcb_topogym.simulator_config` 读取；当前相同数值不代表版本身份相同 |
| 评估与控制 | 直接 Env 执行，逐 tick 异常即失败 | 通过本地 Session，保留其持续窗口、力矩上限、桌面保护、速度保护及夹爪动作换算 |
| GPU 检查点 | 在共享 World 中清空 solver `_ckpt` | 不改共享 World，复用本地 Session 已有的 FEM 检查点限存实现 |
| 模型修订 | 换成 `*_e1mpa_slack_pads_contact_*` | Task 与 variation registry 均保持本地修订号 |

任务、几何生成器、共享绳生成器、FEM/IPC、release profile、规则常量及既有 Harbor 包均未修改。
审计读取本地 v15 的绳异常持续窗口，不导入外部每 tick 立即失败的阈值。机器人与固定件的采样深度仅作诊断，不额外定义本地环境的失败约束；也不代表连续碰撞或驱动力审计通过。

## 策略路线与当前适配边界

| 阶段 | 动作 |
| --- | --- |
| `bead_to_slot` | 移动左珠到槽前，让端盘至槽的绳段留余量 |
| `pick_disc` | 夹起左端盘；交接代码要求端盘直立 |
| `disc_into_slot` / `disc_out_back` / `park_disc` | 端盘从前向后穿槽、换抓、停放 |
| `ring_over_post` | 把环越过柱顶移至柱后 |
| `ring_edge_on` / `ring_into_slot` / `ring_out_front` | 环侧立，从后向前穿槽 |
| `ring_off_bight` | 绕竖轴转环，直到绳与环盘无穿越 |
| `disc_tidy` | 把端盘推回分隔线内 |
| `ring_to_goal` | 把环搬入实例目标区并保持 |

**完整路线尚不适配本地平放端盘的初态。** 初始化时会在第一条动作前明确报告这一差异，不会改变环境来迎合策略。首阶段 `--stop-after bead_to_slot` 可作为后续开发入口，但本轮也未验证。其余阶段源码保留；即使补齐抓盘步骤，较窄槽、更软更短的绳、原摩擦和 v15 驱动规则仍可能要求重新规划。

策略路径检查用 FK 采样、0.05 rad 关节加密、2 mm 规划余量。这些是规划候选参数，不替代物理接触或本地任务判据。阶段重试从实测状态重规划，不恢复历史状态。交接实现的重试上限是**整次脚本累计 3 次**。

## 保留的开发经验

- 每段从实测位置、姿态和绳形重规划；TCP 指令与实测偏差过大时消除伺服累积误差。
- 抓取与推盘时避开绳；穿槽高度依据槽内绳顶确定，避免端盘把绳压在槽底。
- 单点夹环会转动，换抓需考虑接触与腕部关节限位；先检查抓取和拉出路径的同一 IK 分支。
- 由环盘穿越判断脱绳，不能仅凭环的位置判断成功。
- 夹爪插值末步使用精确目标，避免浮点误差越过原生动作限位。
- 绳回弹可能把端盘拉回分隔线外；源策略使用侧向推边与留手阻挡。是否适用于本地材料尚未验证。
- 检查点续跑可用于探索，但不能作为从 home 连续执行证据；当前正式候选始终通过 Session.step，保留实际受保护后的动作。

## 后续开发入口（本轮没有执行）

从仓库根目录运行，需当前依赖、CUDA/Nyx 资源，输出目录须不存在。Session 延迟渲染，不在这里另建录制循环。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_slotted_post_ring_oracle.py \
  --variant hard --seed 0 --stop-after bead_to_slot \
  --output runs/oracle_dev/slotted_post_ring/hard_v15_prefix_NEW
```

不传 `--stop-after` 的完整执行会明确拒绝当前平放端盘初态，需先适配抓盘策略。首阶段完成仍返回非成功状态，不计入可解证明。源码冻结包含实际本地 Session tooling，其 v15 规则负责物理推进；逐 tick 记录复用共享 `SegmentEvidence`，未伪造 SegmentRunner 段证据。

```bash
.venv-gs121-nyx/bin/python scripts/audit_slotted_post_ring_oracle.py \
  --run runs/oracle_dev/slotted_post_ring/hard_v15_prefix_NEW \
  --output runs/oracle_dev/slotted_post_ring/hard_v15_prefix_NEW/audit
```

`--require-native-success` 要求末态原生成功、逐 tick 重算稳定窗口成功时刻一致，且运行不是开发前缀。诊断报告始终 `harbor_qualified=false`；未接入 Harbor 候选目录、未生成发布包或 `solvability_proof`。

## 外部证据边界

附件称 hard/seed 0 两次从检查点开发续跑取得原生成功，其中一次 t≈348 s、最小体积比 0.912；都不是从 home 的完整连续执行。`hard_full01` 在第三阶段 t=37 s 被人工停止，**并非仍在运行**。easy/medium 只生成过几何。运行轨迹、原生检查点和审计产物未随本次代码迁入，这些描述不能授予本地 v15 成功资格。

## below-easy oracle（2026-10-06）

`below_easy_oracle.py` + `public_session.py`，经 `harbor_bridge/below_easy.py` 分派，与上面迁入的 12 阶段路线无关，只复用
`policy.SlottedOraclePolicy` 的直线、转移与固定件检查。very_easy：右臂指尖径向捏环管（沿环倾斜 30-45° 进手，夹爪本体
150 mm 宽，竖直进手必碰立柱），直上至环最低点高出柱顶 30 mm，平移离柱后直线放到目标区中心上方 6 cm 并保持至任务成功；
每行关节步长不超过 0.03 rad，经 `standard_rate.rate_limited_runner`。

easier（2026-10-07，`EasierPolicy`）：困住环的只是远侧绳圈上的珠 2（直径 39 mm），它过不了环与立柱背面之间的空隙（出生
落稳后约 37 mm）；绳本身只是搭在环上，两端都在环内。右手先选直上越柱顶可达的捏法捏环并抬 6 mm；左手经立柱 −x 侧
（离桌 15 cm、世界 x = −0.30 m）到珠 2，沿 x 方向捏起，越过环后段，放到立柱背面后方 12 mm 处（再近左前臂会碰立柱）松手，
珠倒进空隙；左手退回停放位；环向 +y 移 5 mm 后直上，搭着的绳向内滑落；放置多加一段平移，让在环靠立柱一侧的手越过柱顶后
再下降。开发 Session 上经 `public_session` 从出生态连续一次原生成功，874 行；证据
`runs/test_results/slotted_easier_oracle_dev_20261007_01/`。试过但不用的：捏珠 1 拉绳（珠孔口把 E 50 kPa 的绳压出反转
四面体）、推左端盘把绳从长孔拉回（可行但左臂够不远）。FEM 版 2026-10-07 在 mll-4090-1 Harbor 双模式 1
（`runs/test_results/slotted_easier_harbor_v19_20261007_01/`）。

刚体链（2026-10-07，团队链标准）：very_easy / easier 的绳改为 16.5 mm 胶囊链（球关节，阻尼 2e-4，无弯曲刚度，只按圆柱计质量），
端盘用球关节挂在盘眼上，珠子与链同一 MJCF 实体（Genesis 的碰撞位掩码只在实体内生效），环为 32 段胶囊；CPU float64，
`contact_weld_v1` 可焊链节和环、不焊珠子（`assets/geometry/slotted_post_chain.py`、`tasks/slotted_post_ring/below_easy.py`）。
oracle 读链关节作为绳的中心线（`geometry._chain`）；随链改动的三处：捏环角度扩到整圈并预检直上越柱顶可达（链落稳后
贴在立柱前面，very_easy 改捏 120°）；捏珠 2 改为深度 11 mm、夹紧目标 0.020（0.006 会把球从指尖间挤出）；easier 放下环
后松手（单手夹着的环摆动 0.5–1.4 mm/s，越过 1 mm/s 的静止门槛）。本机 CPU 开发运行：very_easy 431 行、easier 871 行原生
成功，每步 0.15–0.2 s。
