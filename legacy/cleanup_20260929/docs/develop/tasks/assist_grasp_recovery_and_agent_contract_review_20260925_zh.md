# 辅助抓持回收、agent 使用方式与可解性证据调查

日期：2026-09-25。范围：先验收标准 action 接收端，再调查历史 assist 与外部项目；本轮不部署任务 planner、不接入辅助抓持，不预先决定正式 benchmark 必须使用 assist。本文中的回收位置与实验是建议，须与已执行的接收端测试区分。

关联：[planner 回收计划](planner_recovery_and_standard_execution_plan_20260925_zh.md)、[历史 oracle 清单](planner_oracle_inventory_20260925_zh.md)。

后续针对工期与实现顺序的评估见 [Assist 接入工程计划](assist_integration_engineering_plan_20260925_zh.md)：进一步核对历史触发归属，建议 Buzz 无辅助样板独立推进、少量抓取探针分流，再按需接入共用刚体辅助；包含具体模块、成本、后端问题与验收条件。该补充同样是文档方案，尚未部署。

## 1. 调查结论与待决策项

1. **现成 planner 不是接收端验收的前提。** 本轮 action 合同、提交与时序检查通过，但 0.5 秒真实响应矩阵为 **4 passed / 4 failed**：Panda 夹爪尚未收敛。默认周期的延长保持诊断在约 2.325 秒进入阈值，详见 §2。不能把正确接收目标写成瞬时精确到达，也不能把短程动作写成任务可解。
2. **历史 assist 有可回收价值，但不能按源码文件数量整包恢复。** 本轮按职责归纳 **11 组回收单元**：4 组纯计算／监测候选、5 组需改造的约束或后端适配、2 组仅保留参考。前 9 组有复用价值，不等于 9 组都必要或已经兼容。
3. **已有 assist 成功记录，不能证明没有 assist 就不可解。** 需要在同一当前实例上比较取得、保持、受阻、释放和换手；特别是 Lock 的抓取前下垂，应先排查托架支撑。
4. **若 assisted oracle 被用作正式 setting 的可解性证据，正式 agent 应得到相同的动作执行机制。** 相同的不是 oracle 的真值信息或参考轨迹，而是抓取条件、约束类型、保持强度、碰撞与释放行为。若正式 agent 禁用 assist，assisted oracle 只能作为参考，需另补无 assist 的连续成功轨迹。
5. **外部项目没有统一做法。** 调查到的 RLBench、OmniGibson、Habitat、VIMA-Bench 和 SoftGym 各自包含不同的抓持抽象；ManiSkill 的标准 Panda 路径主要使用夹爪力与接触。不能用“其他项目也这样做”代替 TopoGym 自己的模型选择与验收。固定版本与源码见 §5。

建议当前保留未启用抓持辅助的行为，先完成调查评审，再决定是否做小范围辅助模型实验。本文概念上记为 `assistance_model=none`，这不是当前已有的公开配置字段。暂不恢复 oracle 专用 `attach(object_id)`、开局预焊接或位姿跟随写入作为正式能力。

## 2. 前置：标准 action 接收端验收

### 2.1 本轮实际做了什么

新增 [test_policy_action_receiver.py](../../../tests/integration/test_policy_action_receiver.py)，仅用于短程验收。普通 `Interaction` 执行一次目标 action 后保持，分两个 Python segment；管理方独立准备附近可达目标、读取特权测量并保存证据。未新增 `planning/<task>/` 模块，也未改变 simulator、Task、机器人增益或 assist 配置。

- 静态／合同回归：控制模式、机器人描述、公共接口、生命周期、历史回溯和录制分支测试共 **65 项通过**。其中新增非交换旋转／TCP 工具偏移、EE 模式只动夹爪与空动作不调用 IK 的检查。这些包含替身对象，不能独自证明真实动力学。
- 真实验收矩阵：ALOHA 与 Panda＋Robotiq，分别检查 `JOINT_ABS / JOINT_DELTA / EE_ABS / EE_DELTA`；Genesis 1.2.1、Nyx、compact_lab、848×480、多视角，seed=17。
- 每例两个连续 segment、20 个 control step、200 个 physics tick，共 0.5 秒；内部历史包含初态共 201 个 checkpoint。响应阈值通过后，再检查非法动作不改变状态及回溯边界；Panda 原矩阵在阈值处结束，没有执行这些末尾检查，另由延长保持诊断补查。
- 预先固定验收阈值：TCP 位置 3 mm、朝向 0.01 rad、关节跟踪 0.005 rad；夹爪原生坐标误差 ALOHA 3 mm、Robotiq 0.03 rad。报告同时保留实际误差，阈值不是标准接口承诺的全空间控制精度。

核对的 action 合同来自当前 `interaction.action_spec`，不是另造一套测试格式：

| 控制模式 | 每臂的运动字段 | 解释 |
|---|---|---|
| `JOINT_ABS` | `joint_position_rad` | 关节绝对目标；按具名机器人关节顺序 |
| `JOINT_DELTA` | `joint_delta_rad` | 加到本次动作前实测关节位置，不是加到上次目标 |
| `EE_ABS` | `position_world_m`、`orientation_wxyz` | 世界系 TCP 完整位姿；四元数为单位 wxyz |
| `EE_DELTA` | `translation_world_m`、`rotation_world_rad` | 相对动作前实测 TCP；世界系旋转向量左乘，不能按局部 Euler 角解释 |

夹爪在四种模式下均为**原生关节绝对目标**：ALOHA 为 `gripper_position_m`，Robotiq 为 `gripper_position_rad`，不是统一开合比例或夹爪总开口。`{}`／省略整臂保持上次目标；仅提供夹爪字段也应保持手臂目标。重复提交同一个非零 delta 会持续产生新目标，不能当作 hold。本轮短策略只提交一次目标，之后用 `{}` 等待动力学跟踪。

第一批发现测试脚本在关闭 Env 后才关闭最后一段录像，引起文件描述符错误。动作检查已走完，但该批报告仍标失败；修正为先完成录像再关闭 Env，并用新的源码快照重跑。[首次记录](../../../runs/test_results/action_receiver_20260925_01)保留，未覆盖。

真实矩阵已完成：**ALOHA 四项通过，Panda＋Robotiq 四项未通过 0.5 秒夹爪精度阈值**。八项均走完目标提交／保持、时钟与两个 Python segment 连续检查；手臂 TCP 和关节跟踪均在预设阈值内。失败集中在 Robotiq：目标 0.28 rad，0.5 秒时实测约 0.0971 rad，误差约 **0.1829 rad**，超过 0.03 rad。

后续 [CPU 无 RGB 诊断](../../../runs/test_results/action_receiver_20260925_02/robotiq_settling_probe/report.json)保持默认 25 ms 控制周期和相同增益、力矩，延长到 3 秒：约 **2.325 秒**首次进入 0.03 rad，末误差 **0.01533 rad**。因此不能把原失败解释成 action 丢失；当前夹爪响应与任意指定的 0.5 秒完成期限不一致。该诊断是补充证据，**不改写原矩阵的 failed 状态**。

独立的 [CUDA＋Nyx 延长保持复核](../../../runs/test_results/action_receiver_20260925_02/robotiq_settling_rgb/evidence/report.json)也已通过：Panda `EE_DELTA`，3 秒末误差 **0.01533 rad**；目标保持、跨段连续、非法动作原子性、权限和 rewind 均通过。该诊断使用 150 ms 控制周期、20 次 action、1200 tick，源 RGB 按控制边界采样，再映射为 30 fps 录像；没有更改增益／力矩。它不是原来四种模式的 0.5 秒期限复测，也不授予抓取成功资格。

![同一夹爪目标的实际响应：CPU 默认周期与 GPU 前 0.5 秒测量](../../../runs/test_results/action_receiver_20260925_02/robotiq_settling_probe/response.png)

曲线使用实测驱动关节位置；前 0.5 秒 CPU 与 GPU 的两指位置最大差约 `3.01e-14 rad`（[比较数据](../../../runs/test_results/action_receiver_20260925_02/robotiq_settling_probe/backend_comparison.json)）。这只比较已测区间，不据此推断所有后端、接触场景或时长等价。

报告、逐例误差、快照与多视角视频汇总于[接收端验收页](../../../runs/test_results/action_receiver_20260925_02/README.md)。81 个视频的 manifest、哈希、frame map 和多视角帧数对应已核对。固定源码和哈希独立于仍在修改的工作树；原阈值没有因失败而放宽，也没有更改机器人增益或加入 assist。

### 2.2 本次验收的边界

目标格式、编译与推进语义的验证，可以支持下一步调查与模型设计。当前结果不支持“所有目标在 0.5 秒内精确到达”，更不证明任意 EE 目标可达、一次 step 就收敛、重载或接触操作成立。`step` 表示推进配置规定的物理时间，planner 后续应按实测误差、速度及超时预算判断动作阶段完成，不能把发送目标或固定等 20 步当作完成。

本轮复用现有测试录制与报告，产物在 `runs/test_results/`。详细数组采样位于 control step 边界；每 tick checkpoint 已核对，但**尚未实现逐 tick state sink、正式 segment runner 或 `task_rollouts` 自动布局**，不把这些计划功能算作已完成。

## 3. 历史里面到底有什么可以回收

### 3.1 检索口径

旧 Git 提交固定为 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6`。在旧 `topogym/tasks / primitives / robot` 中检索 weld、particle-to-link、FEM attachment、MuJoCo equality 等相关调用，得到 **67 个文件、168 处文本命中**，包含注释、归档器与重复版本，不能算成 67 套辅助抓持。

本轮保存 27 个代表源码并检查关键抓取／保持／释放函数，另外交叉对照历史运行快照。[检索原始结果](../../../runs/test_results/action_receiver_20260925_01/historical_assist_scan.json)与[源码、符号行号及哈希清单](../../../runs/research/assist_survey_20260925/historical_source_manifest.json)可复查。这是有明确边界的调查，不宣称穷尽所有未索引的 runs 快照。

以下 `Git 路径` 均指上述提交；`tasks/...`、`primitives/...`、`robot/...` 前补 `topogym/`，省略 `tasks/` 的任务路径前补 `topogym/tasks/`。可用 `git show <commit>:<完整路径>` 读取，清单保存完整路径。表中编号按工程职责去重，同一文件可能贡献多个单元。

### 3.2 11 组回收单元

| 编号／回收单元 | 可追溯来源与入口 | 适配当前框架的判断 | 对可解性工作的帮助与限制 |
|---|---|---|---|
| R1 实测抓点与相对坐标 | Git `tasks/lock_picking/grasp.py::actual_hand_pose`；`primitives/attachment.py::RigidAttachment.attach` | **纯计算可提取**。改用当前 RobotDescription 的 TCP 与 wxyz 约定，去掉硬编码旧工具偏移 | 钥匙在托架上有 pitch/yaw 时仍可计算抓点；捕获实际相对姿态，避免吸附瞬移。本身不施力 |
| R2 抓取准入与接触过滤 | Git `lock_picking/grasp.py::attach`；`fiber_bundling/robot_sequence.py::touching_grasp_fingers`；`horseshoe_ring/physical_motion.py::grasp_connected` | **纯判定可提取**。按当前接触表和具名 link 适配；Horseshoe 是双 pad 间的受力接触路径，不能降格为任意邻接就夹住所有刚体 | 拒绝隔空抓、单侧触碰和跨帧拼接双指接触；Horseshoe 的多物体夹持仍需单独资格验证 |
| R3 抓持丢失／释放风险监测 | Git `fiber_bundling/robot_sequence.py::grasp_health`；`blanket_flatten/execution.py` 的拉伸释放 guard；`rope_threading/reference_actions.py::release` | **监测逻辑可提取**，计时改用实际 dt。把策略建议、环境失效和物理释放分开；不要因旧高度 guard 而让公开张爪动作无声失效 | 识别 weld 独自吊住物体、布料过拉伸及无人支撑的放绳。监测通过不等于抓取摩擦真实 |
| R4 材料抓片选择与可见性 | Git `blanket_flatten/execution.py::pull`、`grasp_sites.py`；Knot/Rope 的材料带映射 | **几何逻辑可提取**。空间邻域与材料邻域相交，排除埋藏层；按当前网格重新求索引 | 降低同时吸住两层布或跨绳段抓取的风险。几何邻近证据不能标成接触力测量 |
| R5 接触后刚体 weld | Git `cast_keyhole/robot_execution.py`、`cast_coil/robot_demo.py`、`hedgehog_in_cage/family_runtime.py`、`lock_picking/grasp.py`、Fiber 等 | **需 World 后端改造**。统一容量、准入、当前相对变换、真实约束、释放与 checkpoint；不直接复制旧执行循环 | 稳定细柄、重心偏置件和长时间转动；同时可能掩盖握力或抗扭不足，不代表纯摩擦可解 |
| R6 真实约束查询与可靠释放 | Git `robot/grasp_constraints.py::active_grasps / release_grasps`；[Coil 同实现快照](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/source_robot_grasp.py) | **需后端适配**。旧逆序删除针对 Genesis 非尾删除问题；本机 1.2.1 源码仍含该缺陷，见 §4.1。双臂交错释放与永久约束必须重测 | 防止只有 Python 标志变成 false、实际仍焊住。保留求解器真实列表核验，不能盲目复制局部 LIFO |
| R7 PBD 局部粒子到 link | Git `blanket_flatten/execution.py::pull`；`primitives/cloth_link_attach_drag.py`、`pbd_particle_pinch.py` | **需 PBD 生命周期接入**。局部抓片、实际 link 跟随、释放、局部索引与可逆状态全部显式管理 | 布料拉角和展开可复用；接触/穿透及材料应变仍需验证，不能据此保证当前双臂配置可用 |
| R8 FEM 软约束抓持带 | Git `primitives/fem_attachment.py::FEMRopeAttachment`；`knot_untying/robot_probe.py::close / update / release`；Rope 继承动作 | **需当前 IPC 适配**。基类只平移；Knot 已有按实测手位姿旋转局部顶点偏移的用法，可回收。建场前容量、材料映射、运行时选带及完整恢复尚需接通 | 对 Knot/Rope 的抓端、换手有价值。旧准入使用 IPC 表面距离阈值，并非完整接触力观测；约束带不能锁死过长绳段或跨交叉点 |
| R9 MuJoCo 的接触门控 weld / point 连接 | Git `slotted_post_ring/robot_sequence.py::grasp / release`；`orbits/robot_runtime.py::engage_grasp / save_checkpoint` | **只能迁语义并重写后端**。区分固定姿态与球／点连接；保留实测捕获、所有权、动态绑定和 checkpoint 字段，不保留 MuJoCo 运行依赖 | Slotted 的珠子球连接、Orbits 的双指接触后材料点连接，比任意外部牵引更接近可用能力；历史仍是局部流程，不能升级为完整成功 |
| R10 每步覆盖位姿／粒子位置的 attachment | Git `primitives/attachment.py::RigidAttachment.sync / ParticleAttachment.drive_to / AttachmentManager` | **执行方式不回收，仅作参考**。保存相对姿态的数学可归 R1；逐步 set_pos / set_quat / set_particles_pos 及 scene.step 包装不进入标准途径 | 易绕过接触、注入速度或隐藏跟踪误差。不能以“辅助抓持”的名称直接作为正式可解证据 |
| R11 虚拟手与外部目标点驱动 | Git `blanket_flatten/virtual_hands.py`；Orbits/Slotted 的无臂路线 | **只作路线／形变参考**。需要真实双手接近、抓取、交接后才可能迁移为机器人过程 | 有助于寻找操作次序；多于两处同时控制点、无臂驱动、任意材料点移动不证明双臂可解 |

R1–R4 的“可提取”表示函数职责适合共享层，不表示旧函数签名可直接 import；旧 link 名称、坐标偏置和网格索引仍需核对。R5–R9 的“需改造”是工程可行性判断，尚未在当前框架验证。

### 3.3 13 个任务的必要性判断

| 任务／设置范围 | 历史使用情况 | 当前建议与尚未证明的事情 |
|---|---|---|
| Cast Keyhole 三档 | 双指接触后 weld；历史从预抓取附近开始 | 适合作刚体辅助候选，但先测试当前可达抓点和无 assist 持稳；辅助不能补上缺失的 home 接近 |
| Cast Coil 三档 | 双件 weld，末态有释放验证 | 有助于长流程装配；必须测转动受阻与放桌后真实释放，不能只核对轨迹执行完 |
| Horseshoe 旧基础／旧路线 | 初始预抓取焊接；后续换抓使用双 pad 受力接触路径 | 跨多刚体的辅助可能锁住本应相对活动的部件，需谨慎。旧初始化绕过正常准入；新余量三档不能继承必要性或成功 |
| Hedgehog 三档 | 接触辅助抓住球／柄后出笼 | 可减少持握不稳，但必须保留刺—笼及机器人—笼碰撞；辅助不能扩大窗口或跳过姿态约束 |
| Lock medium；easy/hard 候选 | 旧 `StagedLockGrasp` 双指门控 weld | 首选调查对象。区分抓取前托架失稳与抬起后柄部滑转；尚不能判定后者必须用 assist |
| Fiber 三档 | 抓护套 weld，并持续检查双指接触／丢失 | 候选价值较高；不能把辅助施加到细线或整束全部节点。持续 guard 比只在取得时检查更值得回收 |
| Buzz 三档代表 | 源码保留 `contact_weld` 可选分支，但选定 home_lab 成功代表使用无 assist 模式 | 保留无 assist 作为优先路径。**代码存在可选 assist ≠ 这三个代表使用过 assist** |
| Claws A0/B0/C0 | A0 Genesis 预置 weld；B0/C0 MuJoCo 预置连接 | 尚缺从 home 自然取得的证据。assist 不能回答“是否可纯侧移分开”；结构捷径须独立审查 |
| Knot 三档 | FEM 局部带、实测手位姿跟随；新结型仍候选 | 有助于稳定换抓，但抓持带宽、扭转锁定和滑移会改变解结动作；先做局部抓放与受阻检查 |
| Blanket easy／复杂初态 | easy PBD 局部抓片；hard 有虚拟手 | 可研究局部抓片；不可把虚拟手当成当前机器人的辅助模式，旧单臂流程也不直接覆盖当前双臂 |
| Rope medium | FEM 材料带与双臂换手；完整实跑未成功 | assist 不会消除实测绳形偏离后的不可达和碰撞；不能把旧失败全部归因于缺少 attachment |
| Slotted hard／表外候选 | MuJoCo 接触门控 weld／球连接；另有外力路线 | 先明确环、珠、绳各自允许的抓取；后端移植和完整路线均缺，不适合作首个快速辅助样板 |
| Orbits hard | 局部机器人已有双指门控材料点／柄连接；完整路线主要为无臂驱动 | 有可回收的取得／释放／动态绑定设计，但完整 93 动作含双手资源问题；assist 不能创造第三只手 |

以上必要性均为待实验判断。历史完整流程、历史使用某辅助、当前必须使用该辅助，是三个不同命题。

Buzz 的判断来自三个选定代表的实际报告：字段 `assisted_grasp=false`、`grasp_method="friction"`，见 [F1 三拱](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/evidence/source/evidence/nominal/report.json)、[F2](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/evidence/source/evidence/nominal/report.json)、[F3](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/evidence/source/evidence/nominal/report.json)。它们支持优先尝试无 assist 路线，不授予当前迁移实例成功资格。

### 3.4 Lock 下垂问题应如何解释

旧 `StagedLockGrasp.attach` 在夹爪闭合、抓点距离合格且**同一次接触查询中双指都触及钥匙**之后才创建 weld。旧 `actual_hand_pose` 还会读取钥匙在托架上的实际 pitch/yaw，修正抓取姿态。这两部分都值得考虑回收。

但这个 weld 并不负责抓取前支撑钥匙。当前 [Lock 实体声明](../../../topogym/tasks/lock_picking/common.py) 包含自由钥匙、托盘和 V 形支撑；若初始 RGB 阶段钥匙就下垂，应先查这些接触和初态。若只在抬起／旋转后滑转，才进入无辅助夹持与接触辅助的对照。旧 `attach` 内部还有 IK 重试和 60 tick 推进，迁移时必须拆为标准 policy action，不能让一次“接触判定”暗中推进时间。

## 4. 能否适配新框架，以及该放在哪里

当前 [registry](../../../topogym/config/registry.py) 已明确列出 `rigid_attachment_creation / soft_attachment` 缺口；[PBD 模块](../../../topogym/world/physics/pbd.py) 目前负责材料构造，现有 IPC 永久连接也不等于运行中可选择、可释放的抓持。

| 位置 | 合适的职责 | 本轮状态 |
|---|---|---|
| `utils/geometry` | 实测坐标变换、抓片／材料邻域、pad 距离 | 调查候选，不新增运行实现 |
| `solvers` | 纯候选选择、接触门控、误差和丢失判定 | 调查候选，不接收场景时钟所有权 |
| `world/physics` | 实际约束创建、目标更新、解除、约束身份与 capture / restore | 若后续选择辅助模式，必须在这里统一接入 |
| Task / setting 配置 | 可抓对象与区域、模型／参数、物理健康及成功判据 | 任何参数变更都应进入 setting 身份 |
| policy / oracle | 选择接近、闭合、运动、换手、释放动作 | 无权限直接创建 weld 或选择任意真值粒子 |

适配需要明确：闭合意图如何由原生夹爪坐标识别；每 tick 哪个时刻检查准入；抓取时是否保留实际相对姿态；刚体连接到底约束几个自由度；FEM/PBD 选择哪一小片材料；可同时拥有几个抓持；接触丢失和超载如何处理；张爪释放顺序；历史恢复是否包含全部 Python 逻辑和后端约束。

其中闭合方向应从机器人定义取得：ALOHA 的米制夹爪坐标与 Robotiq 的旋转坐标不能共用一个数值门限，也不能只凭数值增大就认定在张爪。当前 TCP 是手部固定参考，准入还需实际指垫／接触位置，不能把 TCP 无条件当作随夹爪变化的抓片中心。若后续增加公共抓持模式，还需公开各机器人的开／合目标含义，并声明辅助参数的单位；引擎的 impulse 上限、force 上限和弹性 stiffness 不能按同一个数值互换。

**不能仅把旧 `attach()` 移到 utils 就算完成迁移。** 有副作用的引擎约束属于物理执行模型。旧 `attach()` 中隐藏的 IK 重试和 `scene.step` 应拆成可记录的普通动作。某些后端缺少可靠的约束反力、运行时改绑或完整接触数据，届时应明确阻塞相应资格，不用常数零或 Python active 标志填补。

### 4.1 当前引擎已经有的接口，以及不能省略的改造

以下对照本机实际安装的 **Genesis 1.2.1**，源码已按哈希保存在[引擎来源清单](../../../runs/research/assist_survey_20260925/installed_engine_source_manifest.json)。本节是静态检查，没有新建辅助约束或修改引擎。

- **刚体取得／查询接口存在。** `RigidSolver.add_weld_constraint / delete_weld_constraint / get_weld_constraints` 可作为 R5/R6 的底层起点。但动态容量需预留；本版本容量耗尽时警告并忽略添加，因此创建后必须核实实际约束，不能仅把 `active=True` 写入 Python。
- **本机仍含非尾 weld 删除缺陷。** `constraint/solver.py::kernel_delete_weld_constraint` 的非尾删除只从末槽复制 `eq_type`，没有复制对象编号、相对变换和求解参数。这与官方 [issue #3122](https://github.com/Genesis-Embodied-AI/genesis-world/issues/3122) 描述一致；在两只手先后抓取后先释放较早一只手的场景中，会危及正确释放。该判断来自安装源码，尚未在本轮动态复现。回收前需有针对性的修复／适配及回溯验收，不能仅恢复旧调用。当前 World 完整缓存恢复绑定 1.2.1，直接升级引擎也不是未经验证的替代方案。
- **原生 weld 不等于有限握力。** 其添加接口没有显式最大抓持力或抗扭上限参数；官方也把它描述为理想刚性连接。若采用该模型，应如实命名；若想提供有限保持力，则需另设计并验证限力或失效机制，不能只写一个阈值参数就宣称真实力限。[官方抓取说明](https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/control_your_robot.html)、[动态约束容量与类型](https://genesis-world.readthedocs.io/en/latest/user_guide/robot_control/constraints.html)。
- **PBD 底层接口尚在。** `PBDBaseEntity.fix_particles_to_link` 与 `release_particle` 提供局部粒子绑定和解除；缺的是统一选择／门控、所有权、抓持参数和完整恢复的集成，不能说底层功能已经全部丢掉。
- **FEM 与点连接仍有不同难度。** 当前 IPC 的 `_create_attachments` 在建场时创建端部 stitch，用于已声明的物理连接；它不是运行时任意抓带和释放接口。刚体官方运行时 API 也只提供 weld，不能用锁住 6 个自由度的 weld 无条件替代 Slotted/Orbits 原本允许转动的点／球连接；R8/R9 需要分别设计后端适配。

## 5. 外部 agent 环境如何使用辅助抓取

调查覆盖面向策略的本地 action API，以及专门评测 LLM 决策的高层接口（§5.2）。不是所有项目都提供 HTTP API；是否通过网络传输不决定抓持的物理语义，底层机器人、action mode 和配置才决定执行方式。本轮只阅读官方文档与仓库源码，没有运行这些外部项目。

外部源码按固定 commit 下载并记录 SHA-256，见[来源清单](../../../runs/research/assist_survey_20260925/external_source_manifest.json)。以下结论仅覆盖所列路径／模式，不代表该仓库所有任务、历史版本或排行榜配置。

| 项目与核查范围 | 实际实现 | agent 如何获得这项能力 | 对 TopoGym 的启示 |
|---|---|---|---|
| RLBench 的 `Discrete` gripper＋PyRep | `attach_grasped_objects=True` 为该动作模式默认值；闭合时尝试抓取注册对象。PyRep 以 proximity sensor 检出，保持当前位置改父节点，释放时恢复原父节点 | 普通 gripper action 即可触发；demo 生成也调用 grasp。不是 oracle 独占权限 | 同一评测中 action mode 与 demo 机制需一致。该邻近 attach 不等于双指力学夹持。[动作模式](https://github.com/stepjam/RLBench/blob/02720bba4c73fe02eb75df946b8791b806028a9d/rlbench/action_modes/gripper_action_modes.py)、[PyRep](https://github.com/stepjam/PyRep/blob/8f420be8064b1970aae18a9cfbc978dfb15747ef/pyrep/robots/end_effectors/gripper.py)、[demo](https://github.com/stepjam/RLBench/blob/02720bba4c73fe02eb75df946b8791b806028a9d/rlbench/backend/scene.py) |
| OmniGibson／BEHAVIOR 的 Robot 抓持模式 | `physical` 依赖接触；`assisted` 用接触、双指及射线过滤候选；`sticky` 更宽松。按控制意图取得／释放，关节相对坐标纳入状态恢复 | 配置决定执行模型，普通夹爪控制进入同一处理逻辑；所查构造函数默认 `physical` | 可借鉴明确模式与状态恢复。不能把 sticky 和双指门控混称同一种辅助；本页默认也不代表所有 challenge 配置。[Robot 源码](https://github.com/StanfordVL/BEHAVIOR-1K/blob/6cbf70b075816096e9be53958780769f3264d25d/OmniGibson/omnigibson/robots/robot.py)、[模式说明](https://behavior.stanford.edu/reference/robots/robot.html) |
| Habitat-Lab Rearrangement 的 `MagicGraspAction / SuctionGraspAction` | Magic 按 EE 到最近对象距离门限调用 snap；Suction 要求末端接触。动态 manager 建 hold constraint；另有 force snap、kinematic 和碰撞组处理分支 | 它们就是注册的 agent grip action/controller，不要求 oracle 直接访问内部 manager | 模拟抓取可以是公开动作抽象。但 force snap、held-object 碰撞过滤不能直接用于互锁拓扑任务；还要区分动态约束与运动学跟随。[grip actions](https://github.com/facebookresearch/habitat-lab/blob/0fb6f43ffe806a8088a171b036336c093bcf604e/habitat-lab/habitat/tasks/rearrange/actions/grip_actions.py)、[manager](https://github.com/facebookresearch/habitat-lab/blob/0fb6f43ffe806a8088a171b036336c093bcf604e/habitat-lab/habitat/tasks/rearrange/rearrange_grasp_manager.py) |
| VIMA-Bench 的 Suction 与操作原语 | 检测吸盘接触可吸取刚体后，以当前相对位姿创建 PyBullet 固定约束；release 移除约束。PickPlace / MoveEndEffector 原语调用它 | 环境提供的操作原语使用该末端模型；吸盘是公开工具设定 | 约束可以表示公开的工具模型；不能据此把我们的平行夹爪直接改为吸盘。[Suction](https://github.com/vimalabs/VIMABench/blob/97e0af11e126fd477c9d81eeabfb6c739021c680/vima_bench/tasks/components/end_effectors.py)、[操作原语](https://github.com/vimalabs/VIMABench/blob/97e0af11e126fd477c9d81eeabfb6c739021c680/vima_bench/tasks/components/action_primitives.py) |
| SoftGym 的 Picker action mode | agent 控制 picker 位移与抓放位；按距离选择粒子，将所抓粒子逆质量设为零并更新位置，释放时恢复 | 属于明确公开的抽象 action space，经 Gym 接口给策略使用 | 柔体任务可以明确选择抽象手，但此类结果证明 picker 模型下的可解性，不能作为完整机械臂动力学证据。[Picker 源码](https://github.com/Xingyu-Lin/softgym/blob/bb383f64cd488062587714abbae38f27ed9f2457/softgym/action_space/action_space.py)、[官方项目说明](https://github.com/Xingyu-Lin/softgym) |
| ManiSkill 的标准 Panda 配置 | PD 驱动夹爪、声明接触摩擦；`is_grasping` 依据两指接触力大小和方向做测量，所查路径不自动 attach | agent 使用普通 arm＋gripper action；is_grasping 是判定，非施加抓持的 API | 稳定抓取也可通过接触、增益与几何质量取得；应先定位我们的失败原因。不能推断 ManiSkill 所有机器人都无辅助。[Panda 源码](https://github.com/mani-skill/ManiSkill/blob/62ff3a5896b4d5b4cf0ac4c8d79afe600c9404a3/mani_skill/agents/robots/panda/panda.py) |

### 5.1 从源码能得出的共同点

上述辅助模式是环境或末端执行器的动作语义，通常由正常 grip / pick 动作进入。启用某个辅助模式时，agent 的策略不必拥有修改引擎约束的权限，也不必获得 simulator 使用的接触真值。这与“oracle 偷偷焊接，而 agent 只能靠摩擦”有本质差异。此处是对上述实现的比较归纳，不是所有机器人 benchmark 的统一规范。

还应警惕名称：`grasp()` 可能是邻近 attach，`is_grasping()` 可能仅为测量，`Suction` 是工具模型，`Picker` 是抽象操作器。仅搜索到函数名无法判断物理保证。RLBench 的 demo 路径和可配置 agent gripper 路径也说明：关闭一个开关后，应重新核对演示与评测是否仍处于同一模型。

### 5.2 专门面向 LLM agent 的接口对照

**Embodied Agent Interface（EAI）** 的 BEHAVIOR transition model 暴露 `LEFT_GRASP / RIGHT_GRASP` 等具名动作。`apply_action(action, obj)` 分派到 `grasp`：检查可交互性和手是否空闲，必要时自动导航，再更新手中物体和关系树；底层 `_set_in_hand_magic` 直接调用对象 `set_position`。因此该路径把“取得物体”作为高层状态转移，并不要求 LLM 输出连续机械臂接近与双指闭合轨迹。[公开动作入口](https://github.com/embodied-agent-interface/embodied-agent-interface/blob/531c62f8df2cb392bdf1907923c76da41cad4fe6/src/behavior_eval/transition_model/eval_env.py)、[抓取逻辑](https://github.com/embodied-agent-interface/embodied-agent-interface/blob/531c62f8df2cb392bdf1907923c76da41cad4fe6/src/behavior_eval/transition_model/action_env.py)、[几何执行](https://github.com/embodied-agent-interface/embodied-agent-interface/blob/531c62f8df2cb392bdf1907923c76da41cad4fe6/src/behavior_eval/transition_model/position_geometry.py)。

这适合其高层决策评测目标，但不能直接移植为 TopoGym 的抓取模型：我们希望 agent 自己产生运动段，并保留互锁、穿环、回退和碰撞约束。对照这些项目后，更合适的候选是**保留当前低层 action，闭合取得后由环境提供受限保持辅助**，而不是增加一个自动移动并取得指定对象的高层动作。这是结合 TopoGym 目标作出的设计判断。

## 6. 如果可解性证明用了 assist，是否必须也给 agent 用

**如果要把那次成功当作同一正式 setting 的可解性证据，就应让 agent 使用相同辅助机制；否则结论必须降为 assisted 模型中的参考解法。**

设同一初态下，纯接触模型的状态转移为 `T_contact(s, a)`，辅助模型为 `T_assist(s, a)`。即使 action 字典完全相同，只要接触后额外创建约束，二者一般就不同。存在一条在 `T_assist` 中成功的轨迹，不推出在 `T_contact` 中也存在或同一路线可以执行。辅助约束还可能阻止原本允许的滑移，因此不能无条件把 assisted 结果解释成纯物理性能的严格上界。

| oracle 使用方式 | 正式 agent 的模型 | 可以给出的结论 |
|---|---|---|
| 无 assist 的普通机器人动作 | 相同无 assist 配置 | 该实例有机器人执行见证；特权 oracle 成功仍不保证 RGB agent 能自行发现解法 |
| 使用声明的接触门控 assist，动作仍是标准夹爪控制 | 相同取得／保持／释放模型及参数 | 该 assisted setting 有机器人执行见证；报告明确辅助模型 |
| 只有 oracle 可以直接 weld，agent 无此机制 | 纯接触 | 只能算不同执行条件的参考，不能证明正式 agent setting 可解 |
| oracle 用辅助搜索路径，再完全关闭辅助连续重跑成功 | 纯接触 | 后一次无辅助运行可作证据；前一次只是搜索工具 |
| 外部材料点、预焊接或对象位姿写入完成路线 | 从 home 开始的标准机器人 | 几何／对象操作参考，须另补真实取得与机器人执行 |

“开放给 agent”建议理解为：**管理方在 setting 中固定抓持模型，agent 正常发送夹爪动作，就可按同样条件获得抓持辅助。** 不要求在 action 中增加 `assist=true` 或任意 `attach(object_id)`，也不让 agent 在 episode 中切换物理模型、改变半径或握持强度。公开动作规格和模型说明即可，约束创建仍由环境管理。

普通 agent 与 oracle 可以有不同信息权限；两者的执行模型和成功判据须一致。oracle 读取 world 真值来选择动作，与 oracle 获得额外施力能力是两个问题。辅助取得所用真值留在 simulator 内部，并不自动泄漏给 RGB agent。

## 7. 对 TopoGym 来说，这样做是否好

### 7.1 可能带来的便利

- 如果目标主要是发现互锁、回退、穿环和换手结构，接触取得后的有限辅助可以减少偶然滑落造成的噪声，帮助判断路线本身是否可执行。
- 局部布片或材料带比直接拉整片对象更接近真实手的作用范围，历史源码已提供一些材料选择和实测跟随方法。
- 统一取得、保持、释放和恢复，比散落在各 oracle 中的 weld 更容易复现与审查；但这是后续选择辅助模型后的工程收益，不是现在必须开启的理由。

### 7.2 可能改变我们真正想测的难度

- Lock 的长钥匙、Coil 的耦合旋转、Claws 的翻转都可能依赖实际抗扭能力；完全固定的 weld 会隐藏握力、滑转或换抓需求。
- Knot、Rope、Orbits 的宽抓持带或过强局部姿态约束可能冻结绳段、改变扭转传递，或者让原本需要换手的动作失去必要性。
- Horseshoe 一次绑定多个刚体可能固定它们本应有的相对自由度；Blanket 抓到多个折层可能直接改变展开难度。
- 吸附半径过大、取得时重对齐物体、忽略受持物与器具碰撞，可能绕过钥匙孔／窗口／圆环约束。这类变化会损害 TopoGym 的核心任务含义。
- 辅助不能修复不可达、碰撞几何错误、自由物体托架失稳、任务成功判据缺失，也不能证明 easy / medium / hard 排序合理。

### 7.3 建议的选择依据

先比较无 assist 与一个**接触后、保持当前相对关系、可释放、作用范围受限**的候选模型，再做决定。若无 assist 在合理接触／控制参数下已经稳定，优先不增加机制；若失败主要来自细柄或柔体离散化造成的持握不稳，且辅助没有改变任务所需动作结构，可考虑将它正式写入 setting。

若最终同时保留 assisted 与 contact 两种协议，它们应分别报告，不能混在同一成功率或难度标定中。这里不建议立即给 39 个变体全部加双模式；先用少量代表确认必要性和影响。

## 8. 文档评审后可做的最小对照实验

以下尚未执行，本轮不据此自动部署 assist 或 planner。

| 探针 | 固定条件与测量 | 能回答的问题 |
|---|---|---|
| Lock 初态静置 | 同一 seed、托架、钥匙质量与初态，机器人 home 保持；记录两端高度、倾角、托架接触与速度 | 下垂是否在尚未抓取时已发生，是否应先修支撑 |
| Lock 闭合—抬起—转动—放下 | 同一可达接近；分别无辅助／候选辅助，记录取得率、相对滑移和转角、受力覆盖、跟踪误差、释放残留 | 辅助是否确实解决持稳，是否掩盖异常载荷 |
| Coil / Claws / Cage 受阻运动 | 合法路线与明显受几何阻挡的小动作；不改变目标判据 | 开启辅助后是否仍保留物体间阻挡，是否引入可穿透捷径 |
| Knot / Rope 单带与换手 | 固定材料坐标、小抓持带、真实手跟随，单手释放／双手交接；测应变、滑移、扭转、残留约束 | 局部辅助是否过强、是否偷抓邻近绳段、换手是否真实成立 |
| Blanket 单层抓片 | 空间相近而材料不相邻的折层；比较抓取集合、释放和铺展 | 是否跨层粘连、是否依赖过大抓片 |
| 生命周期与模式一致 | 两个普通／特权句柄提交同类合法动作，验证取得条件、参数与结果；在取得前中后 rewind | 是否存在 oracle 专用物理能力，逻辑和后端状态能否一起恢复 |

实验必须记录相同设置下的明确 seed 集、实际成功／失败次数及失败阶段；必要性先由取得和持稳数据判断，再通过完整路线检查任务结构。无辅助失败不能仅因一次抓点不佳就归结为物理模型不足；辅助成功也不能省略释放、接触与数值健康检查。

本轮后的工程顺序是：**接收端结果审查 → 本调查文档评审与抓持模型选择 → 选定后的小范围辅助对照 → 再部署任务 planner**。39 个 planner 入口、通用 PolicySpec / PolicyDecision 和完整 segment runner 继续作为后续计划，不抢在抓持模型选择前实施。
