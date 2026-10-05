# Slotted Post Ring oracle 开发进度与当前问题

更新日期：2026-10-04。任务：`slotted_post_ring`（长孔立柱解环）。

同目录其他任务：[Orbits oracle 开发进度与当前问题](orbits/README.md)。

**当前完成的是外部 oracle 代码迁移及本地 v15 执行接口适配，尚未完成本地完整解题。** 外部策略依赖直立端盘，本地端盘平放，抓盘阶段存在明确适配缺口；完整执行入口因此在策略初始化时拒绝继续。首阶段开发入口已保留，但没有运行验证。

按用户要求，本次只迁移代码，未运行测试、几何生成、仿真、审计或录像。外部方案与本地 v15 的物理、几何和评估约束不同时，以本地为准。

## 1. 已完成的工作

| 内容 | 当前实现 | 入口 |
| --- | --- | --- |
| 分阶段策略 | 迁入 12 阶段 JOINT_ABS 生成器、抓取候选、失败回退、实测 TCP 同步与伺服逻辑 | [policy.py](../../topogym/planning/slotted_post_ring/policy.py) |
| 运动学 | 迁入 ALOHA 多种子 IK、FK、关节限位检查、IK 分支跳变检查和碰撞采样 | [kinematics.py](../../topogym/planning/slotted_post_ring/kinematics.py) |
| 几何与拓扑观测 | 读取当前 Task 的尺寸、目标区及固定件；提供绳与环盘穿越、环是否套柱等探针；端盘法向取自本地网格，不强制假定直立 | [geometry.py](../../topogym/planning/slotted_post_ring/geometry.py) |
| v15 执行适配 | 从本地 release profile 获取配置，经共享 `SessionPolicyRunner` 和 `Session.step` 执行，保留本地规则 | [runtime.py](../../topogym/planning/slotted_post_ring/runtime.py) |
| 管理入口与记录 | 冻结源码和实际使用的 Session tooling，记录执行动作、逐 tick 测量、阶段结果与资源信息 | [run_slotted_post_ring_oracle.py](../../scripts/oracle_runners/run_slotted_post_ring_oracle.py) |
| 只读诊断 | 迁入并适配模型身份、tick 连续性、v15 绳异常持续窗口、目标稳定窗口及机器人几何采样诊断 | [audit.py](../../topogym/planning/slotted_post_ring/audit.py)、[审计入口](../../scripts/audit_slotted_post_ring_oracle.py) |
| 开发经验 | 记录外部方案的抓取、换抓、穿槽、避绳、关节分支和证据归档经验 | [模块说明](../../topogym/planning/slotted_post_ring/README.md) |

以上均为代码层面的进度，不代表入口已实测可运行、各阶段已通过或任务已解通。

## 2. 保留本地 v15 的环境约束

迁移过程中曾应用的外部环境补丁，已按用户后续要求撤回。本次没有为适配 oracle 修改 Task、几何生成器、共享绳生成器、FEM/IPC、规则常量或模型修订号。

| 项目 | 外部实现 | 本地保留的实现 |
| --- | --- | --- |
| 三档槽宽 | 34 mm | 28 mm；独立 `clearance36` 变体也保留原值 |
| 端盘初态 | 支架内直立 | 桌面平放，不新增支架 |
| 绳布局 | 双余量圈、约 1.105 m 长绳 | 原有绳路线和长度 |
| 绳材料 | E=1 MPa | E=50 kPa |
| 绳网格 | 3.5 mm 轴向间距、12 边 | 共享 1.375 mm 轴向间距、24 边配方 |
| 弹性参考 | 新增弯曲初态参考 `stress_free_spawn` | 不导入该开关，沿用本地参考模型 |
| 接触与同步 | 指垫摩擦 0.8、新增固定件接触选项、同步容差 5 mm | 沿用本地接触设置和 2 mm 同步保护 |
| 执行规则 | 直接通过 Env 推进 | 通过本地 Session，保留持续异常判定、力矩上限、桌面保护等规则 |
| 时序与求解设置 | runner 内写死 v12 常量 | 读取本地公开 release profile 和 tooling 配置 |
| 检查点限存 | 修改共享 World 的 solver `_ckpt` 清理 | 复用本地 Session 已有实现，不改共享 World |

本地配置来源是 [release_profile.py](../../topogym/tasks/release_profile.py) 与 [rcb_topogym.py](../../harbor_templates/topogym/common/rcb_topogym.py)。部分时序数值相同，也不能把外部 v12 运行资格转移到本地 v15。

## 3. 策略路线与实际进度

| 阶段 | 用途 | 本地状态 |
| --- | --- | --- |
| `bead_to_slot` | 把左珠移到槽前，为后续端盘移动留余量 | 保留开发入口，未运行 |
| `pick_disc` | 夹起左端盘 | **明确缺口：源代码要求直立端盘，本地平放抓取待适配** |
| `disc_into_slot` / `disc_out_back` / `park_disc` | 端盘从前向后穿槽、换抓并停放 | 源码迁入，受抓盘缺口阻塞；窄槽与本地绳模型下未验证 |
| `ring_over_post` | 把环越过柱顶移到柱后 | 源码迁入，未验证 |
| `ring_edge_on` / `ring_into_slot` / `ring_out_front` | 环侧立并从后向前穿槽 | 源码迁入，未验证 |
| `ring_off_bight` | 旋转环，让绳圈滑脱 | 源码迁入，未验证 |
| `disc_tidy` | 把端盘推回分隔线内 | 源码迁入，未验证 |
| `ring_to_goal` | 环搬入目标区并稳定保持 | 源码迁入，未验证 |

完整入口的拒绝发生在 `SlottedOraclePolicy.initialize()`，在第一条策略动作之前；这不表示 Env 尚未构建或尚未进行初始化落稳。`--stop-after bead_to_slot` 只开放开发前缀，阶段结束不能当作任务成功。

## 4. 当前问题

### 已确定的适配缺口

1. **平放端盘抓取尚未实现。** 需要在本地初态、夹爪限位、桌面保护与绳连接约束内规划拾取和后续姿态转换，不能用添加支架、改出生姿态或直接摆位来替代。
2. **后续阶段仍保留外部模型上的候选参数。** 代码会读取实测状态和本地尺寸，但抓取角、穿槽偏置、抬升余量等仍来自外部开发经验，尚未完成本地逐阶段适配。
3. **没有本地连续成功和验证证据。** 当前既无从 home 完整执行的轨迹，也无本地原生成功、全程审计、视频或 Harbor verifier 结果。

### 尚待验证的风险

- 槽宽从外部 34 mm 回到本地 28 mm，手持端盘、侧立环与绳共用槽口时的通路和换抓空间可能不足。
- 本地绳更软、长度与布局不同，珠子搬运、端盘穿槽和环越柱顶可能出现新的拉紧、滑脱或绳受压问题。
- 外部的高摩擦与较宽同步容差没有导入，原夹持和伺服动作可能无法保持物体或触发本地同步保护。
- Session 的驱动力限制和桌面保护可能改变实际执行目标或跟踪误差，需要以实际记录重新规划。

这些是根据模型差异识别出的风险，不是本轮实测失败结论。

### 诊断范围的限制

只读审计使用本地 v15 绳异常持续窗口，不引入外部每 tick 立即失败的规则。机器人与固定件的采样深度仅作诊断，不能证明连续不穿透，也不覆盖驱动力验证。报告保持 `qualification="unqualified"`、`harbor_qualified=false`，不替代 Harbor 独立验证。

## 5. 外部进度与本地证据的区别

交接材料报告 hard、seed 0 在开发环境中两次取得原生成功：一次由实验片段逐段推进，一次从 `after_ring_lift` 检查点运行后半段；后者约在仿真 t=348 s 成功，报告最小绳体积比 0.912。

两次都不是从 home 起的完整连续运行。另一条 `hard_full01` 连续尝试在第三阶段、仿真 t=37 s 被人工停止；其 `running` 报告是停止前残留，不能理解为仍在运行。easy/medium 在交接环境中只验证过几何生成。

上述状态仅来自用户提供的交接说明。完整轨迹、原生检查点、审计产物及开发服务器内存状态未迁入；本地保留的 v15 环境也与外部不同，因此不能继承其成功标签。

## 6. 后续工作顺序

以下是继续开发时的工作清单，本次文档更新不启动执行，用户“不跑测试”的要求仍然有效。

1. 完成平放端盘拾取与转向的代码方案，明确阶段入口、出口及失败条件。
2. 在代码层重新核对 28 mm 槽、本地绳路线、夹持方式与各阶段参数，处理对外部直立端盘和余量圈的依赖。
3. 保持全部动作经 Session 执行，保留受保护后的实际目标和状态反馈，不更改环境约束以迁就策略。
4. 用户后续要求恢复验证时，先验证短段和阶段衔接，再从标准 home 连续执行 hard、seed 0，取得原生成功后做独立审计。
5. hard 的证据完整后再分别处理 medium/easy；各档独立记录结果，不由环更大推断成功。
6. 取得完整证据后，再处理可解证明归档、Harbor 包与录像；当前不发布成功配方。

详细开发命令见 [模块说明中的开发入口](../../topogym/planning/slotted_post_ring/README.md#后续开发入口本轮没有执行)。当前命令仅用于后续开发，不代表已通过验收。

## 7. 材料索引

- [Slotted Post Ring 任务说明](../develop/tasks/slotted_post_ring_zh.md)
- [oracle 模块、迁移差异与开发经验](../../topogym/planning/slotted_post_ring/README.md)
- [oracle runner 索引](../../scripts/oracle_runners/README.md)
- 原始用户附件：`05823cab-9484-4169-b37b-4fe5e7dd373a/pasted-text.txt`；来源标注仓库基线 `e49b116e`，SHA-256 为 `3744ce0cb534f88bf35175db4e85ef72b0e0da44caca9a996dedcaf564d02b4c`。
