# Assist 接入标准 simulator：工程评估与分步计划

日期：2026-09-25；2026-09-26 开始实施。前文保留调查当时的判断；最新部署范围与验证边界见 §10 及[公共模块说明](../modules/grasp_assist_zh.md)。

关联：[历史 assist 与外部 agent 环境调查](../../../legacy/cleanup_20260929/docs/develop/tasks/assist_grasp_recovery_and_agent_contract_review_20260925_zh.md)、[各变体历史 planner 清单](../../../legacy/cleanup_20260929/docs/develop/tasks/planner_oracle_inventory_20260925_zh.md)、[标准执行与证据计划](../../../legacy/cleanup_20260929/docs/develop/tasks/planner_recovery_and_standard_execution_plan_20260925_zh.md)、[action 接收端测试](../../../runs/test_results/action_receiver_20260925_02/README.md)。

## 1. 工程判断

**建议采用“无 assist 样板先行、少量抓取探针分流、按需接入刚体 assist”的顺序。不要先全面恢复旧工具，也不要先为 13 项任务各写完整无 assist planner。**

1. 历史 assist 中确有真实物理约束：刚体 weld、PBD 局部粒子绑到机器人 link、FEM 局部材料带约束。但它们大多由任务执行器显式取得／释放，有些混入 IK、推进时间或预抓取初始化。**引擎执行了约束，不等于标准 simulator 已经提供自动抓取。**
2. 若近期目标是先得到首个完整解题样板，优先回收 **Buzz easy / F1 三拱**的无 assist 策略；它不必等待辅助系统。然后尝试同一任务的 F2 / F3。当前实例重定向、完整判据和证据链仍需补齐，历史成功不是当前成功。
3. 若目标是较快覆盖多项任务，**一个共用的刚体自动 assist 值得早做**：Keyhole、Coil、Hedgehog、Lock 的历史路线都有相关依赖。先用少量短探针确认收益，随后在恢复这些完整 planner 之前接好必要能力，避免每个 planner 再写一次私有 weld。
4. 柔体与旧 MuJoCo 连接另排：它们涉及材料选择、约束自由度、运行时更新和恢复，不能由刚体 weld 一次解决。Knot / Rope / Blanket / Slotted / Orbits 不应挡住首批刚体与 Buzz 的交付。
5. Assist 只解决抓持模型的一部分。**支撑失稳、home 接近不可达、控制跟踪、资产变化、穿透、解法捷径和成功判据缺失**仍需独立处理。没有证据支持“把 assist 补回来，旧 planner 就都能 solve”。

这里的“先做”是后续排期建议，不表示本文已经启动实现。赶时间时优先交付少量真实闭环，39 个入口齐全不是第一个解法的前置条件。

## 2. 历史 assist 到底由谁触发

### 2.1 三个层次需要分开

| 层次 | 历史情况 | 是否已经满足当前要求 |
|---|---|---|
| 引擎中的保持机制 | Genesis weld、PBD link binding、FEM 约束或 MuJoCo equality 实际参与求解 | 部分满足“物理后端承担保持”；还需核对碰撞、自由度和状态恢复 |
| 任务执行脚本中的抓取逻辑 | 在某个阶段调用 `attach()`、`close_and_attach()`、`engage_grasp()`，或自己每步检测接触 | 有可回收逻辑，但触发权仍在旧任务执行器中 |
| 新 simulator 的统一自动行为 | 普通 `Interaction.step(action)` 更新夹爪目标，环境自主检测取得／释放 | **尚未接入。** 当前 registry 仍声明刚体／柔体 assist 缺口 |

历史 Keyhole 就有“脚本每步发现双指接触后自动 weld”的循环，因此不能概括成所有历史代码都没有自动检测。但这种自动检测属于特定 demo 循环；换成当前公共 `Interaction`，该循环不会自动出现。

### 2.2 可追溯的具体实现与迁移判断

下表链接到已归档的源码，源提交固定为 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6`；完整文件哈希见[历史来源清单](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/historical_source_manifest.json)。不是统计整个 Git 历史所有可能分支。

| 历史实现与坐标 | 实际取得／保持／释放方式 | 自动接入时保留什么、改什么 |
|---|---|---|
| Lock：[grasp.py，StagedLockGrasp.attach](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/lock_picking/grasp.py#L28) | `runner.execute` 接近并闭合后显式调用；检查距离、闭合量、同一帧双指接触，再建 hand–key weld；`detach()` 显式解除。取得失败时内部还有 IK 重定位和 `c.step(60)` 重试 | 保留实测抓取坐标、同帧接触和距离检查；把接近／重试留给 policy，约束生命周期交给 simulator，删除 helper 中隐藏的时钟 |
| Keyhole：[variant_runtime.py，execute](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/cast_keyhole/variant_runtime.py#L137) | 自己 `scene.step()` 后逐臂检查双指接触，创建 weld；旧代表从 pregrasp 起步，结束仍可持握 | 门控可转成统一每 tick 检查；补 home 取得，不能照搬旧起点或 0.12 s 取得期限 |
| Coil：[robot_demo.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/cast_coil/robot_demo.py#L416) | 闭合后要求两臂各自双指接触连续约 20 ms，脚本建立两个 weld；末尾显式移除 | 保留稳定接触时间和实测相对位姿；各手应能独立取得／释放，不强制所有任务同时双手取得 |
| Coil 共用释放：[grasp_constraints.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/robot/grasp_constraints.py#L12) | 查询真实 solver constraints；按注册逆序删除以绕开旧引擎非尾删除问题；删除后再核查 | 保留真实查询与释放验证。逆序“全部释放”不是支持任意双手交错释放的通用解法 |
| Hedgehog：[family_runtime.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/hedgehog_in_cage/family_runtime.py#L253) | 执行器等到双指接触球体后 weld，沿路线执行，放桌前删除 | 是较直接的单刚体候选；仍要核对完整 home 接近和当前几何，保留刺–笼碰撞 |
| Fiber：[robot_sequence.py，close_and_attach](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/fiber_bundling/robot_sequence.py#L312) | 脚本闭合并等待双指接触指定护套 link，按 `args.assist` 建 weld；运行中监测接触丢失，失效时解除并停止 | 回收“取得后持续检查”；只能辅助声明的护套，不能顺便固定所有细线。旧脚本指定 link 要改为环境从合格接触中选择 |
| Horseshoe：[physical_motion.py，grasp_connected / replace_grasps](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/horseshoe_ring/physical_motion.py#L140) | 后续换抓要求两指间有受力接触路径，路径覆盖所抓刚体；`step_count == 0` 绕过这项检查并建立初始抓持；可一次绑定多体 | 接触图有价值，但初始旁路不保留；多体绑定会改变内部自由度，不纳入首版单体 assist |
| Claws：[physical.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/interlocked_claws/physical.py#L1)、[family_robot.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/interlocked_claws/family_robot.py) | A0 使用预抓取 Genesis weld；B0/C0 使用旧 MuJoCo 预置抓持连接 | 不是已验证的自然取得模块。要补真实抓取与后端移植；有 assist 也不能证明必须转脱／翻转 |
| Knot／Rope：[robot_probe.py，close / release](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/knot_untying/robot_probe.py#L150)、[reference_actions.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/rope_threading/reference_actions.py) | 策略选择材料带；两指的 IPC 表面距离达到门限后激活局部约束，记录相对实际手位姿的偏移，再随实测手平移／旋转；逐带维护 owner | 保留局部材料范围、实际手跟随、所有权；旧邻近证据不能写成双指接触力证据。运行时材料选择／解除需适配当前 IPC |
| Blanket：[execution.py，pull](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/blanket_flatten/execution.py#L238) | 执行器拒绝被埋角点，以空间邻域∩材料邻域选粒子；检查两指垫表面距离，`fix_particles_to_link`；释放用 `release_particle`，另有应变保护 | 可回收单层局部抓片；门控是几何邻近，不是力证据。旧执行器包装 `scene.step`，这部分不恢复 |
| Slotted／Orbits：[robot_sequence.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/slotted_post_ring/robot_sequence.py)、[robot_runtime.py，engage_grasp](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/orbits/robot_runtime.py#L164) | MuJoCo 接触门控的 weld／点连接；Orbits 由脚本指定柄或材料点，检查双指接触，再改绑 equality/site；保存动态绑定用于恢复 | 回收接触归属、实际接点和恢复设计。点连接允许转动，不能直接换成 6 自由度全锁定 weld |
| 旧通用 Attachment／虚拟手：[attachment.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/primitives/attachment.py#L269)、[virtual_hands.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/blanket_flatten/virtual_hands.py) | 一部分直接 `set_pos / set_quat / set_particles_pos`，或外部材料点驱动；还可能包装场景 step | 只提取坐标计算、候选路线等纯逻辑；不作为标准机械臂 assist 执行层 |

Lock 的调用归属另核对了旧 `topogym/tasks/lock_picking/runner.py::execute`（同一固定提交，约第 106–175 行）：先 `set_gripper(...)`，再在 `cfg.assist.enabled` 时调用 `assist.attach()`，最终显式 `assist.detach()`。因此只迁回 `grasp.py`、却不改 simulator 的调用链，普通夹爪动作仍不会得到这项能力。

Buzz 是优先做无辅助样板的实证依据：选定 [F1](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/evidence/source/evidence/nominal/report.json)、[F2](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/evidence/source/evidence/nominal/report.json)、[F3](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/evidence/source/evidence/nominal/report.json) 报告均为 `assisted_grasp=false`、`grasp_method="friction"`。源码存在可选 weld 分支，不改变这三个代表的证据身份。

前一份调查按职责划出的 **11 组**仍适用：4 组纯计算／监测、5 组约束及后端适配、2 组参考逻辑。这个数字既不是 11 套完整工具，也不表示必须全部恢复。

## 3. 赶时间时，先试什么、什么时候转向 assist

### 3.1 不做 13 项完整无辅助试错，先做两种小范围工作

**工作一：回收 Buzz F1 的策略和参考路线，经标准 API 连续执行。** 优先复用历史动作结构，重算当前坐标、IK 和完成条件；不从头另写一套探索算法，不直接回放旧 qpos 或运行旧执行器。首先检查 Task 的完整判据缺口，由负责 Task 的会话补齐；判据未齐时可报告路线执行进展，不能标 solved。

**工作二：对依赖旧辅助的代表做“静置 → 接近 → 闭合 → 小幅抬起／转动 → 放下／释放”的无 assist 探针。** 首选 Lock medium 用来诊断钥匙支撑和持握；若初态支撑本身失败，停止该抓取试验并交给 Task 侧处理，可换 Hedgehog 的单刚体取得作为候选。Coil easy 用于后续双臂资格，不必先恢复完整装配路线。

建议初筛预算：每个代表先固定 1 个 seed、最多 2 个经 IK／碰撞预检的抓取候选；允许根据已定位原因修正一轮接近或等待策略。仍反复滑落就先记录为“当前无辅助抓持候选未通过”，评估最小 assist；不继续投入整条长路线。这个预算是工程分流规则，**不是不可解性证明或成功率评估**。局部通过后才扩展 seed 与完整路线。

| 探针结果 | 接下来的工程决定 |
|---|---|
| 物体还未被抓就下垂／滚走 | 查初态与支撑；assist 不应在未接触时悬空托住物体 |
| 夹爪仍在正常闭合 | 等待实测进展；重新设合理动作预算，不据此添加 assist |
| 到不了抓取位、指垫碰器具或 IK 失败 | 修接近／抓取候选；自动 weld 不负责把手移动到目标 |
| 取得、抬起、代表性转动和释放均稳定 | 沿无 assist 路线回收完整 planner；后续仍检查长程负载 |
| 已有合格双指接触，抬起／转动持续滑落，且历史路线靠 weld 保持 | 优先接入最小刚体 assist 后重跑同一探针；预期收益较高，必要性仍是实验判断 |
| 受阻时穿透、关节大幅跟踪失败或物体变形失控 | 查接触／控制／材料和步长；不能靠更强绑定宣告通过 |
| 辅助稳定抓住，但任务路线仍失败 | 记录独立的路线／判据问题，停止把失败继续归因于缺 assist |

原 0.5 秒 Robotiq 测试不能作为需要 assist 的理由。它是无物体时从 0 到 **0.28 rad 的部分闭合**；默认控制周期诊断约 2.325 秒进入误差阈值，延长保持已验证收敛。这个结果既不要求所有抓取都等 3 秒，也不表示夹到物体时必须到达空载闭合目标。带物体时应按接触、实际指位、运动趋势与阶段预算判断取得；物体阻挡夹爪继续闭合本身可以是正常现象。

### 3.2 13 项任务的排期建议

| 任务／档位 | 建议先做的工作 | assist 排期与主要限制 |
|---|---|---|
| Buzz easy，随后 medium / hard | 无辅助完整样板，恢复判据、当前实例重定向 | 不等 assist；三档分别验收，不继承成功 |
| Lock medium | 支撑与单手抓取探针，再迁移历史阶段逻辑 | 刚体 assist 首批候选；easy / hard 的完整路线仍待开发 |
| Hedgehog 三档 | 选一个初态稳定、抓取可达的代表接入 | 单体 assist 首批推广；各笼型路径和碰撞分别核查 |
| Coil easy，随后 medium / hard | 双手取得、独立释放资格，再完整装配 | 刚体 assist 主要收益对象；非尾删除问题是前置条件 |
| Keyhole 三档 | 补 home 到实际取得，再重定向分离路线 | 复用刚体 assist；历史 pregrasp 路线不覆盖取得 |
| Fiber 三档 | 护套抓取探针及所有细线穿环判据 | 刚体护套可以复用；不需要为此先恢复通用 FEM 抓持 |
| Horseshoe 新三档 | 新余量实例的可穿过性、抓取与路线核对 | 多体接触图／多体绑定另做；旧基础流程不覆盖新三档 |
| Claws 三档 | home 取得、后端重定向、错误解法／侧移捷径检查 | 可借用刚体保持，但不列为最快首样板；assist 不保证旋转／翻转必要 |
| Knot easy，随后新结型 | 单材料带取得／释放与必要换手 | FEM 专项；medium / hard 原本也未完成，回收 assist 不等于已有解法 |
| Blanket easy | 当前双臂机器人下的单层局部抓放 | PBD 专项；旧单臂可借策略，medium / hard 的路线另做 |
| Rope medium | 可达与换手局部阶段，修复失败原因 | 复用合格 FEM 能力；easy / hard 暂无完整 planner |
| Slotted 三档 | 确认实例、抓取对象和点连接自由度 | 旧 MuJoCo 改造加路线缺口，后排 |
| Orbits hard，随后简化档 | 双手资源、材料点取得与参考路线重写 | 不先恢复全套外部驱动；assist 不能增加第三个独立控制点 |

若只追求尽快得到首个成功，优先 Buzz。若要短期覆盖多个不同任务，就应在上述少量探针之后及早建设共用刚体 assist，而不是反复为细柄抓持逐任务调参。是否最终纳入正式 setting，取决于任务要测的能力：若主要测动作结构，声明的理想保持可接受；若还要测抗扭、滑移和换抓，weld 会改变目标，需要更细的抓持模型。

## 4. 最小刚体自动 assist 应是什么合同

下面的 `assistance_model`、模型名及模块名均为**拟新增设计**，当前没有这些公共配置或接口。

### 4.1 管理方选模型，agent 继续输出原 action

建议首版只有两个明确模型身份：`none` 与 `contact_weld_v1`。由管理方在创建 setting 时选择，固定到整个 episode，并写入配置与报告。初始默认保持 `none`；只有通过资格的 setting 才启用具体辅助模型。普通 agent 与 oracle 对同一 setting 使用完全相同的取得／保持／释放规则；`enable_privileged` 只控制信息与回溯权限，绝不能顺带开启 assist。

Agent 继续发送 `gripper_position_m` 或 `gripper_position_rad` 及原有运动字段。**不新增 `attach(object_id)` 或 oracle 特供的施力入口。** Task 只声明允许抓取的对象／区域，环境从实际指垫接触中确定对象；policy 通过移动手选择抓哪里。可抓区域不应编码“第几阶段必须抓哪个物体”的参考解法。模型是否启用、取得／释放规则、单位和限制应在公开 setting／动作说明中明确；公开规则不等于公开实时接触真值。

### 4.2 取得、保持、释放的首版边界

| 项目 | 建议合同 |
|---|---|
| 闭合意图 | 从已提交并持续保持的夹爪目标解释，结合机器人开／合方向与实测指位。`{}` 或省略整臂继续保持意图，不能误认为释放 |
| 取得门控 | 有闭合／保持闭合意图；同一物理 tick 的两指接触同一合格刚体及声明区域；距离／穿透在限值内；连续满足声明的稳定时间。不能累加不同时刻的左右接触来凑双指 |
| 夹爪实际状态 | 指垫几何与接触才是准入依据；不把“已发闭合指令”或“必须到达空载全闭坐标”当作取得条件 |
| 捕获相对关系 | 用取得时实测 hand–object 相对变换建约束；不把物体吸到标准中心，不改对象位姿／速度来对齐 |
| 持握模型 | 首版是明确声明的理想 6 自由度 weld。限制的是取得范围和对象，不宣称具有经过验证的有限握力／抗扭上限 |
| 碰撞 | 物体与其他任务对象、器具、机器人和桌面的必要碰撞继续存在；核对创建 weld 是否影响实际碰撞行为，不以跳过碰撞换取成功 |
| 数量与归属 | 首版每只手至多一个刚体；双手各持一个物体。多体绑定和双手同持一个物体的交接先明确不支持，后续单独验收再开放 |
| 张爪释放 | 有明确张开意图时，在下一次物理推进前移除本手辅助并核查；实际手指随后按原动力学张开。移除 weld 不等于指尖接触已消失，撤手还需正常等待 |
| 异常解除 | 约束不在、相对误差超限或声明的持握失效条件成立时记录失效并解除；有迟滞／重新准入规则，防止同一闭合命令下失效后立刻反复焊回 |
| 持握健康 | 不要求每 tick 都有正接触力才能保持：理想 weld 可能承担载荷而使指垫接触力下降。接触丢失窗口／几何脱离条件须按该模型验证，不能机械复制旧 100 ms 常数 |
| 候选歧义 | 按公开、确定性的规则选择合格候选或拒绝歧义；不由 oracle 传入真值对象 ID 决定辅助结果 |

普通 agent 不需要读取接触真值才能触发辅助；它们可以只留在环境内部。特权报告可以暴露候选、拒绝原因和实际约束。自动触发是当前低层 action 设计下推荐的实现方式；公平性要求的是相同执行模型，并不意味着所有可能的高层 API 都只能用这种触发形式。

## 5. 怎样接入当前代码，不另建一个执行框架

### 5.1 分层与复用

| 位置 | 当前可复用部分 | 拟补工作 |
|---|---|---|
| [robot/description.py](../../../topogym/robot/description.py)、两种机器人 description | 原生夹爪字段、范围、hand link、TCP 偏移 | 补明确开／合语义、实际指垫 link／几何描述；当前 `JointGroup` 没有完整 assist 描述，不能仅凭范围大小推断闭合方向 |
| [robot/joint_position.py](../../../topogym/robot/joint_position.py)、[robot/control.py](../../../topogym/robot/control.py) | 目标保持、动作验证、四种模式和关节驱动 | 向内部 assist 提供已提交目标与实测手状态；不改变 action 单位或引入第二套控制器 |
| [utils/geometry/rigid_motion.py](../../../topogym/utils/geometry/rigid_motion.py) 等 | 坐标变换与运动采样；旧 hand 偏移可结合当前 TCP 定义重写 | 只提取缺少的纯计算；不恢复旧 `RigidAttachment.sync` 的位姿写入 |
| [solvers/genesis_kinematics.py](../../../topogym/solvers/genesis_kinematics.py)、[solvers/collision](../../../topogym/solvers/collision) | IK/FK、几何可达／碰撞查询 | planner 复用；assist 的纯候选／门控计算统一放拟新增 `utils/grasp.py`，不得暗中 step 或做 IK 纠偏 |
| `world/physics/grasp_manager.py`（拟新增） | 当前没有共用运行时 grasp manager | 持有状态机、所有权、取得／释放与真实后端核查；首版只接刚体，后续后端各自适配 |
| [world/genesis_world.py](../../../topogym/world/genesis_world.py)、[world/state.py](../../../topogym/world/state.py) | 实际物理推进、引擎全缓冲捕获、Python 缓存和 IPC checkpoint | 扩展 assist 内部读数／生命周期与可恢复状态；保持 World 对物理副作用的管理 |
| [simulator/env.py](../../../topogym/simulator/env.py) | 唯一动作与 tick 循环，task update、每 tick checkpoint、错误边界 | 在既有循环加入固定的 assist 前／后钩子；不把 `scene.step` 包装权交给 planner |
| Task 声明／[config/registry.py](../../../topogym/config/registry.py) | 实体身份、setting 参数、显式能力缺口 | 声明可抓区域和支持的模型；按真实验收解除具体能力缺口，不能移除所有 Task 的 assist gap 就算完成 |
| [simulator/config.py](../../../topogym/simulator/config.py)、证据与 recording 层 | 管理配置、权限、公共录像与历史身份 | 固定模型版本／参数；补逐 tick 私有日志和 assist 事件。复用共享 recording，不新建 writer |

涉及 Task 声明、判据和初态的修改应由负责 Task 的会话接入；公共接口工作不修改当前并行会话负责的 assets 或场景预设。共享 `env.py / config.py / genesis_world.py` 的实现阶段使用小改动与固定源码快照验收。

### 5.2 接入时序

当前 `Env.step` 已经是 `compile_action → robot.apply_action → world.advance → task.update → _save_state`。建议在这一条循环中扩展，示意如下；不是已存在的接口：

```text
Interaction.step(action)
  验证整个 action，成功后提交机器人目标
  对每个 physics tick：
    assist.before_tick(持续目标、实测手状态)
      处理张爪解除；后续柔体模式在这里更新已持材料的约束目标
    world.advance()                 # 仍然只推进一次
    assist.after_tick(本 tick 接触、实测状态、dt)
      更新准入计时／持握健康；合格时创建并核实实际约束
    task.update(...)
    保存包括 assist 在内的 checkpoint
    向管理方 state sink 导出该 tick 状态和事件
  生成原有 observation / transition / RGB
```

在 `after_tick` 创建的约束在下一次物理求解生效；报告区分“已注册”与“经过求解验证”，避免把同一 tick 的旧接触／受力写成新约束作用结果。明确这里的 tick 是当前 `world.advance()` 的外层物理步，不冒称逐 solver substep 检查。

非法 action 必须在更新闭合意图或约束之前被拒绝。后端若在有效动作中途失败，沿用现有 faulted 状态与最后有效 checkpoint 诊断，不假装整个动作已回滚。`observe / get / render` 和 segment 切换都不触发取得、释放或额外推进。

Reset 创建新 episode 时清空全部 assist；初始化静置阶段不允许隐含预焊接。Rewind 恢复旧 episode 内已有的 assist 状态；恢复动作本身不重新搜索抓取点或重新捕获相对位姿。Segment 结束只停止提交动作，不释放手中物体。

### 5.3 状态恢复不是“存一个 active 布尔值”

当前 World 已捕获引擎缓冲、动态约束查询缓存、控制输入和 IPC checkpoint；这提供基础，但**尚未证明新加入的动态 assist 全部可恢复**。建议把 manager 的可序列化逻辑状态纳入 `WorldState`，恢复时与原生缓冲同步，包括：

- 模型／参数身份，每只手的闭合意图、候选、稳定计时、状态、解除冷却／重新准入条件。
- 对象与 link 稳定身份、owner、捕获的相对位姿、实际约束映射、失效计时和原因。
- 后续柔体模式的材料／粒子集合、局部偏移、目标、带宽和运行时 backend handle 映射。
- 原生约束容量、有效槽、求解所需状态与缓存；不能把可能重排的槽编号当永久对象 ID。

恢复后检查 manager 与 solver 的实际绑定一致，再继续同一动作序列验证。Rewind 后的旧未来状态和事件标为失效，保留审计材料但不算当前解题轨迹。标准 home 起步的最终成功见证应从新 episode 连续重跑，不能拼接搜索中的多条分支。

## 6. 已发现的工程障碍与成本

| 问题 | 已核对事实 | 首版处理建议 |
|---|---|---|
| 非尾 weld 删除 | 本机归档的 Genesis 1.2.1 [删除内核](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/installed_genesis_1_2_1/genesis/engine/solvers/rigid/constraint/solver.py#L1763)仅把最后槽 `eq_type` 复制到被删槽，没有一起复制对象／约束数据；本轮是静态核查，尚未动态复现 | 实现前先复现两个抓持的交错释放。优先做有版本／源码哈希保护的最小后端修复或适配，再验收；不要以“倒序全删”代替任意单手释放，也不通过释放另一只手再重建来伪装连续持握 |
| 动态容量不足不抛异常 | [add_weld_constraint](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/installed_genesis_1_2_1/genesis/engine/solvers/rigid/constraint/solver.py#L418)容量耗尽会警告并忽略添加 | 建场时预留容量；创建后核查真实约束，无约束则明确失败，不能仅设置 Python active |
| 任意升级引擎影响回溯 | 当前 World 完整恢复显式绑定 Genesis 1.2.1 | 升级作为独立兼容工作；本计划不把升级当作免费的修复步骤 |
| 理想 weld 没有显式有限握力参数 | 所查运行时添加接口未提供最大抓持力／抗扭上限 | 首版如实声明理想保持；反力不可可靠取得时标 unavailable，不填写零或宣称已验证力限 |
| 柔体准入证据不同 | PBD 指垫距离、FEM IPC 邻近与刚体接触力是不同观测 | 各后端分别命名门控与覆盖范围；不共用一个 `contact=True` 掩盖差别 |
| 当前 IPC 永久连接不是运行时抓取 | [ipc.py，_create_attachments](../../../topogym/world/physics/ipc.py#L359)在建场创建 stitch；运行时选带／释放还需设计 | FEM 不列入首版。先证实后端生命周期能力，再迁移长解结／穿环策略 |
| planner／判据另有缺口 | 当前 registry 仍有 Buzz、Lock、Fiber 等完整判据缺口，历史机器人和资产亦有差异 | assist 资格与 Task 成功分开报告；首样板前检查判据，避免视频做完才发现无法证明目标 |

成本判断：**单个 `add_weld_constraint` 调用很小；一个能自动取得、可靠释放、跨 segment 保持、逐 tick 回溯且对 agent 公平的能力，是一个完整的小功能。** 首版最值得复用的是门控、实测相对关系、真实约束核查，不是旧执行器的整个类。

粗略排期仅用于比较投入，假设现有环境可运行、工程者熟悉代码、没有额外场景大改；不包含长任务反复调参，也不是实测工时：

| 工作包 | 估计量级 | 主要不确定项 |
|---|---|---|
| 1–2 个代表的静置／抓放无辅助探针 | 约 0.5–1.5 人日 | home 接近是否已有可用候选、单次仿真与证据开销 |
| 最小刚体自动 assist：模型配置、单手取得释放、真实查询与状态恢复 | 约 2–4 人日 | 当前控制／接触数据适配、完整 rewind |
| 后端删除修复验证、双手交错释放、权限／证据资格 | 另约 1–2 人日；若需升级引擎则重新估算 | 原生约束数据和 checkpoint 兼容 |
| PBD 局部抓片 | 刚体公共生命周期稳定后另约 2–4 人日 | 多层选择、机器人差异、粒子绑定恢复 |
| FEM 动态抓带／旧 MuJoCo 点连接移植 | 当前不足以给可靠窄区间，先做后端能力探针 | 运行时添加／解绑、刚柔双向作用、自由度与完整原生恢复 |

不建议同时启动最后两类以争取首个解法。纯物理调试可以明确关闭 RGB；最终资格再用固定源码的 Genesis＋Nyx 标准录制。开发探针也保留配置、动作和失败状态；正式报告仍需用户要求的完整逐 tick 证据，不能为了加快运行永久关闭这项记录。

## 7. 实施顺序、验收与停止条件

| 阶段 | 交付 | 通过／分流条件 |
|---|---|---|
| P0：确认一套当前实例 | 选 Buzz F1 及 1 个刚体抓取代表；记录资产、机器人、seed、初态、控制周期与判据缺口 | 明确哪些能力已经有、哪些由 Task 会话补；不迁移全部 39 套 |
| P1：无辅助快速分流 | Buzz 历史策略的标准接入；Lock 或替代代表的短探针与失败定位 | 稳定者继续无 assist；重复的持握失败者进入 P2。P2 不阻塞 Buzz 自身工作 |
| P2：刚体辅助后端与自动取得 | 最小 manager、模型身份、单手取得／释放；先处理已知删除风险 | 空夹、单指、超距离不得 attach；正确接触能取得；无吸附跳变；开放夹爪能解除；容量失败明确 |
| P3：生命周期与双手资格 | 回溯、跨 segment、双手交错释放、失败证据与普通／特权一致性 | 下列专项全部通过，才推广到双臂完整 planner；不靠旧 demo 代替 |
| P4：第一批完整可解性证据 | Buzz 无辅助样板；随后选一个刚体 assisted setting，再同任务其他档位 | 当前标准 home 连续执行，Task 目标与物理资格独立通过，逐 tick 状态与视频同一次运行 |
| P5：按目标扩展 | 刚体推广、护套；确实要做 Knot／Blanket 等时才接对应柔体能力 | 只给具体模型／任务／实例授予已验证状态；未验证继续标缺口 |

P2 / P3 的必要专项应先使用短策略或小测试场景，不需要完整 planner：

1. **准入与不跳变：**空夹、单指、跨时刻双指、错误区域均拒绝；合格双指才取得；捕获前后实际位姿连续。张爪未接触不应创建任何绑定。
2. **释放正确性：**两个独立物体先后取得，按两个不同次序逐手释放；另一只手的对象、相对变换和约束保持不变。结合真实运动检查，不能只看约束数量。
3. **受阻行为：**持物撞到任务器具时仍受阻；有意走错方向不会通过穿透绕过几何；相应跟踪误差和失败按原资格处理。
4. **持续目标与边界：**一次闭合后连续 `{}` 可以延迟取得和持握；拆为两个 segment 与连续执行在同一模型下等价。非法 action 不改变意图、绑定或时钟。
5. **回溯：**分别回到取得前、取得后、释放后，再执行同样动作；比对绑定对象、位姿／速度、目标、门控计时、健康和事件序列。Reset 后不能残留旧 owner。
6. **权限一致：**相同实例和 action 序列分别经普通与特权 interaction 执行，在声明数值容差内取得相同物理结果；普通返回数据不因开启 assist 泄漏真值。
7. **模型对照：**同一配置仅切换声明的 assist 模型比较局部动作；保持 dt、控制周期、轨迹速度、碰撞与增益一致。若确需调整这些参数，另建有身份的实验，不能把收益全部归于 assist。

**停止条件：**后端可靠释放／恢复未通过，停止推广该 assist；Task 几何或判据阻塞，记录归属并切换可继续的代表；无完整机器人路线的任务，不因已有辅助组件就提前开长时间批量求解。局部探针失败不宣称全局不可解，单例成功不宣称全家族稳定。

## 8. Planner 和报告最终如何使用它

Planner 只负责“接近、闭合、等待取得、搬动、换抓、张开、等待清离”等普通动作阶段。Oracle 可通过批准的只读查询看对象与抓持诊断，生成动作；环境负责触发和维持约束。旧 `attach()` 中的对准重试应改写为可记录的标准 action，不能包装成私有引擎调用。普通 agent 是否能仅凭 RGB 发现策略，与 oracle 的执行见证是两项评估。

最小 planner 迁移不必等待 `PolicySpec / PolicyDecision`：它们是可选共用适配结构，直接脚本也可以循环 `interaction.step(action)`。但正式解题必须接上管理方逐 tick state sink 和统一报告；当前 action 接收端测试只保存了控制边界数组，不能冒称这一项已经完成。

最终沿用已约定的布局和拼写：

```text
task_rollouts/<experiment_name_date>/<task_name>/trail_<x>_<difficulty>/
  segment_0.mp4
  segment_1.mp4
  report.json
  segments/segment_0.json
  views/<camera>/segment_0.mp4
  private/physics_states.jsonl
  private/arrays/...
  private/assist_events.jsonl        # 拟补：实际物理事件，与 planner 阶段事件分开
```

完整布局、同步合成、初末 RGB 与媒体映射继续遵循[标准执行计划 §7](../../../legacy/cleanup_20260929/docs/develop/tasks/planner_recovery_and_standard_execution_plan_20260925_zh.md#7-每一步详细状态与固定产物位置)。增加的 assist 证据至少包括模型版本／参数、闭合目标与实测指位、取得所用接触／邻近证据、对象与 link、相对变换、真实约束、拒绝／解除原因及 tick 身份。每个 tick 能索引到当时的 assist 状态；大数组按原约定分块，不仅保存事件或最终摘要。

报告分别记录 **API／生命周期合格、assist 合格、Task 目标完成、物理资格、证据完整性**。最终结论应明确写成“该配置和 seed 下，无 assist／contact_weld_v1 的机器人连续执行成功”。不能把 assisted 成功记到 `none` 设置下，也不能将模拟辅助结果解释为真实夹爪力学可解性的证明。

本轮完成的是调用归属核对和上述工程分流方案；尚无新 assist 后端、自动触发功能、完整 planner 或当前变体成功记录。

## 9. Blanket 初始化之外可以独立推进的 assist（2026-09-26 复核）

本节是对当前源码的增量复核与排期，前文 09-25 的接口／判据进度不是当前验收结论。当前 `topogym/config/registry.py` 仍声明 `rigid_attachment_creation`、`soft_attachment` 缺口，`GenesisWorld` 输出仍为 `assist_active=False, assist_model="none"`；公共自动 assist 尚未接入。

**Blanket 初始化不会阻止其他任务开发公共 assist。** 完整 planner、最终 terminal 和三难度全部可解都不应作为抓持工具的前置条件。先用标准 simulator 的短抓放脚本验证工具，再把它接到具体任务。任务本身在抓取前不稳定时，先用稳定 fixture 验证工具；不能用自动 assist 在未接触时把任务物体托住。

### 9.1 按任务划分可立即做的能力和剩余前置条件

| 任务 | 现在可以开发／回收的公共能力 | 该任务实物验收的前置条件；是否等待 Blanket |
|---|---|---|
| Cast Keyhole | 单手单刚体双指门控、实测相对位姿捕获、双手各持一件、独立释放 | 补 home 接近与实际双指取得；不等 Blanket |
| Cast Coil | 同上，重点是两手先后取得、任意次序释放 | 验证非尾 weld 删除不伤另一只手；装配接触仍正常；不等 Blanket |
| Hedgehog in Cage | 单刚体取得／保持／张爪释放，保留刺与笼碰撞 | 优先选稳定可接近的一档作首个真实任务探针；不等 Blanket |
| Lock Picking | 只把 hand 与 key 的实际刚体 link 建立保持约束 | 钥匙在抓取前的支撑稳定性单独检查；盘、锁体和钥匙不能一起固定；不等 Blanket |
| Interlocked Claws | 两手独立刚体保持、受阻时不穿透的回归 | 当前几何的侧移捷径、旋转必要性、home 取得独立处理；不等 Blanket |
| Fiber Bundling | 将通用刚体能力绑定到明确的护套／trunk link | 每档识别真正护套 link，保持其他串联关节和细线自由度；不需等待 FEM 抓持或 Blanket |
| Buzz Wire 3D | 可以参加通用刚体工具测试，但历史 F1/F2/F3 有无 assist 摩擦抓持代表 | 优先保留无 assist 路线；不为统一接口而强制开启辅助；不等 Blanket |
| Horseshoe Ring | 单体取得可复用；接触图判定、候选归属可先实现为纯计算 | 抓持若跨多个互相活动的构件，需单独定义允许约束的 link 与保留自由度；旧 tick 0 旁路和“一把焊住多件”不进入首版；不等 Blanket |
| Knot Untying | 材料弧长带选择、双指局部表面邻近门控、owner／换手状态协议、FEM 接口 fixture | 运行时 IPC 局部约束的激活／撤销／移动目标与 rewind 尚需专项实现；不等 Blanket，但也不能用普通刚体 weld 代替 |
| Rope Threading | 与 Knot 共用局部材料带抓持、双手交接与释放 | 同一个 IPC 动态抓持后端；现有路线与各档初态另验；不等 Blanket |
| Blanket Flatten | 空间邻域∩材料 UV 邻域的单层抓片、埋层拒绝、应变保护；PBD link attach/release 的稳定布片 fixture | 单折候选已通过 5 s 续跑、重复物理初态与回溯，可以用作抓放测试场景；抓持能力本身尚未验证。八面板仍不合格；严格 RGB 复现另有缺口，不等同于粒子初态变化 |
| Slotted Post Ring | 环／珠／圆盘的候选归属，以及绳的局部材料带选择 | 当前是 FEM+IPC 混合场景；`ipc_only` 刚体需要 IPC 中实际生效的保持约束，不能假设 Genesis rigid weld 有效。绳端永久连接必须保留；不等 Blanket |
| Orbits | 木柄刚体候选、绳的局部材料带候选、同一对象的抓取自由度声明 | 同样等待 IPC 运行时刚体／柔体抓持适配；当前已有绳端到木柄的永久连接不等于可开合的手部抓持；不等 Blanket |

因此首批可直接推进的是 **Keyhole、Coil、Hedgehog、Lock、Claws、Fiber 共用的刚体工具**；Buzz 保留无辅助样板，Horseshoe 先限定单体。Knot／Rope 的 IPC 工具可以独立开展，但开发量大于前一批。Slotted／Orbits 随 IPC 路线推进。Blanket 阻塞的是未合格初态上的验证，不是所有 PBD 抓持工具的开发。

上表“可以开发”不表示已部署或全部档位已验收，也不是每个任务一定需要 assist 的证明。优先级仍以短探针结果决定。

### 9.2 公共模块怎么放

用户希望作为公共工具集复用是合适的。建议沿当前分层落位，避免每个 planner 持有一套私有 attach/release：

| 拟定文件 | 职责与边界 |
|---|---|
| `topogym/utils/grasp.py` | 纯计算：指垫坐标变换、候选范围、空间∩材料邻域、同帧双指证据匹配、确定性歧义拒绝。可由 Task、诊断和各后端共享；不接收 Scene、不 step、不写位姿 |
| `topogym/world/physics/grasp_manager.py` | 公共运行时 `GraspManager`：闭合意图、连续准入计时、owner、取得／保持／释放／失效、完整 capture/restore 与事件；由唯一 World 生命周期驱动 |
| `topogym/world/physics/grasp_rigid.py` | 首批刚体后端：真实 weld 创建、查询、任意顺序删除与恢复、保留碰撞；以取得时的实测相对关系约束，不吸附到预设中心 |
| `topogym/world/physics/grasp_pbd.py` | 后续 PBD 后端：局部材料片 attach/release、实际 link offset、free／绑定数组的恢复；与 visual skinning binding 区分 |
| `topogym/world/physics/grasp_ipc.py` | 后续 IPC 后端：运行时局部材料约束及 IPC 刚体抓持；永久连接与临时手部约束分开，接入 native checkpoint |

`utils/grasp.py` 可以作为大家共用的选择／判定工具；会改变物理约束的部分放在 World 下，才能保证普通 agent 和 oracle 经过相同的自动机制。planner 继续只输出接近、夹爪闭合／张开和移动 action。

按本次命名确认，World 管理器统一使用 `grasp_manager.py`，与纯计算的 `utils/grasp.py` 区分；三个物理后端保留 `grasp_rigid.py / grasp_pbd.py / grasp_ipc.py`。这些是待新增模块的部署坐标，本次更新没有创建空壳运行时代码，也不改名历史快照中的 `grasp.py`。

柔体 owner 应落实到材料片／材料带，不能把整张布或整根绳只分配给一只手：两手可以持有同一实体上互不重叠的两个区域；重叠区域的取得、换手和释放另有明确规则。刚体则按实际受约束的 link 记录 owner。这个归属协议和候选选择可以先做纯计算测试，不依赖八面板静置成功。

当前已有 `world/physics/rigid_contacts.py` 的刚体 substep 接触记录，可复用其证据语义和读取边界；它明确不覆盖 IPC，而且任务物体角色完整不等于已声明机器人左右指垫，仍须补指垫／link 描述。当前 `AttachmentSpec`／`ipc.py::_create_attachments` 是建场景时创建永久绳端连接，尚不是动态手部抓持接口。

本次复核 legacy unroll 还确认了一项 PBD 抓持要求：`fix_particles_to_link` 的物理附着与 visual skinning 是两套关系；旧实验曾把已经被手指压到桌下的粒子附着到 link，导致它们持续穿桌。局部抓片准入因此应检查整片粒子的埋层／穿透情况，而不只检查抓点中心离 TCP 的距离；绑定后继续做几何健康检查，释放时另验实际位置与速度连续性。不能把“支持表正确”当作“手部附着一定物理合格”。来源见 [unroll 历史说明 §2.2](../../../legacy/docs/develop/tasks/cloth_unroll_zh.md#22-刚性绑定冻结竖直状态)。

### 9.3 实施顺序和共享会话边界

1. 先落纯计算工具、机器人指垫与开合语义，以及可恢复 manager 的数据协议；用空夹、单指、跨时刻双指、歧义候选、非法动作等负例验收。
2. 实现刚体后端，先做单手取得、抬起、受阻、释放；再做双手交错释放及取得前／后 rewind。首个真实任务优先 Hedgehog 或支撑已合格的 Lock。
3. 推广到 Coil／Keyhole／Claws 和 Fiber 的指定护套 link。工具资格与完整 solve 分别记录。
4. IPC 动态抓持和 PBD 局部抓片可独立于 Blanket 八面板调参开展；只在稳定 fixture 上先验后端，目标任务随后接入。

可独立新增的 `utils/grasp.py`、`world/physics/grasp*.py` 及专用测试，与本轮 Blanket 准备实验没有文件重叠。真正接入自动行为时，`world/genesis_world.py`、`world/state.py`、`simulator/env.py`、`tasks/base.py` 和 robot description 属于共享修改点，需要与对应会话按函数增量合并、重新固定源码快照后验收。Blanket 的冻结状态身份包含 World/state 源码哈希；这些共享文件变化后旧资源会被严格拒绝，须重新导出／资格复验，不能通过放宽哈希校验“兼容”。

本次只更新上述能力清单与落位计划，没有趁 Blanket 试验修改公共 World 或部署自动 assist。

本轮单折的具体边界见[稳定初态报告](../../../runs/test_results/blanket_stable_segment0_20260926_01/README.md)：同配置／seed 的粒子 x/v 可精确恢复，正常物理续跑 5 s 最大漂移 0.149 mm；补证三次机器人观测、相机参数与绑定相同，但第三次 RGB 有最多 2/255 的通道差，严格 RGB 断言保留失败。这个结果足以提供物理抓持 fixture，不构成“视觉复现全部解决”或“Blanket 已有可解 planner”的证明。

### 9.4 历史代码怎样填入上述公共模块（2026-09-26 源码复核）

**有可直接提取的计算函数，也有可以改造的实际约束代码。** 最有价值的不是整套旧 runner，而是双指证据筛选、连续计时、材料片选择、实测相对偏移、真实约束核查这几部分。以下“可提取”表示有现成函数体，仍需适配当前数据格式与验证；不表示旧模块可直接 import 后用于 agent。

来源固定为提交 `cb60f01b32786cc9c26f754f91b7be4bef3f9ca6`；已归档文件及哈希见[历史源码清单](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/historical_source_manifest.json)。表内链接指向归档源码；未归档的底层 IPC 文件另给 Git 坐标。

| 来源与具体代码 | 可以回收的内容 → 新位置 | 必须适配的部分 |
|---|---|---|
| Fiber [robot_sequence.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/fiber_bundling/robot_sequence.py#L45)：`touching_grasp_fingers`、`grasp_health` | 接触对数组筛选可直接提取到 `utils/grasp.py`；接触丢失累计时间和失效原因可作为 `grasp_manager.py` 的材料 | 先按候选 link 分组，不能把左指接触 A、右指接触 B 合并为单体取得。旧半开度以米计，当前 Robotiq 驱动坐标以 rad 计，不能搬常数；旧健康函数甚至有写死的“100 ms”错误文字，应按模型和实际阈值生成 |
| Lock [grasp.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/lock_picking/grasp.py#L28)：`StagedLockGrasp.attach / detach`；Coil [robot_demo.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/cast_coil/robot_demo.py#L416) 的取得段 | 距离＋实际指位＋当前双指证据、连续接触计时 → `utils/grasp.py` 与 manager；weld 调用 → `grasp_rigid.py` | 删除 Lock 内嵌 IK 重试与 `c.step(60)`；Coil 的“两手同时满足”改成每手独立计时，按物理时间累计。取得时核验实际约束，不能 `add_weld` 后只设 `active=True` |
| 共用 [robot/grasp_constraints.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/robot/grasp_constraints.py#L12)：`active_grasps / release_grasps` | 从 solver 读真实约束、释放前后核查、保存释放证据 → `grasp_rigid.py`，是最直接的后端素材之一 | 原函数是按注册逆序全部释放，用于绕过历史删除问题；新后端必须支持只释放指定手，保留另一只手和永久约束。旧问题需按实际引擎复验，不能将此函数当成任意顺序删除已经解决 |
| Blanket [execution.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/blanket_flatten/execution.py#L239)：`pull` 中选片／准入／附着段；[grasp_sites.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/blanket_flatten/grasp_sites.py#L45)：`exposed_boundary_site` | 空间半径∩材料 UV 半径、遮挡深度、稳定排序的暴露边界搜索 → `utils/grasp.py`；`fix_particles_to_link / release_particle` → `grasp_pbd.py` | 旧遮挡检查主要针对中心点，需补整片埋层／穿桌拒绝；pad 距离是几何邻近证据。纯候选函数可供 oracle 搜索抓点，但 manager 只检查实际手附近的候选，不能替 agent 决定下一次去抓哪个角 |
| Knot [robot_probe.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/knot_untying/robot_probe.py#L150)：`close / release` 与 `update` 末尾；[fem_attachment.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/primitives/fem_attachment.py#L32)：`FEMRopeAttachment` | 按材料带记录 owner；取得时计算手局部偏移，随**实测**手位姿旋转和平移 → manager 与 `grasp_ipc.py`；已有 engage／更新目标／release 包装 | 旧脚本预选两条材料带，当前候选必须从公开可抓范围和实际手部邻近中确定；去掉定时动作脚本、私有 `_handle` 访问和夹爪命令副作用。保留其 IPC 表面距离证据身份；补运行时材料选择与完整恢复 |
| Horseshoe [physical_motion.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/horseshoe_ring/physical_motion.py#L140)：`grasp_connected` | 两指之间受力接触路径、被抓物体是否真的处于路径中的图算法 → `utils/grasp.py`，先作为诊断及后续多体门控素材 | 不保留 tick 0 跳过准入；接触图通过也不自动授权把多个可动构件全部焊死。多体约束自由度另行定义，首批仍限单体 |
| Orbits [robot_runtime.py](../../../legacy/cleanup_20260929/runs/research/assist_survey_20260925/local_history/topogym/tasks/orbits/robot_runtime.py#L134)：`grasp_contacts / engage_grasp / save_checkpoint / restore_checkpoint` | 接触必须归属目标材料点、取得时捕获实际接点；恢复动态绑定、局部接点与求解器状态的设计 → manager 数据协议和 IPC 验收用例 | 实现是 MuJoCo，不能搬 equality/site API 到 Genesis。保存的字段提供恢复清单，不是当前可用 codec；点连接保留的转动自由度不能被全锁定 weld 替代 |

**另外找到了 IPC 后端本身的历史素材。** 同一提交的 `topogym/world/genesis_ipc_vertex_constraints.py` 包含 `FollowHandle.engage / update_targets / release`、`follow_near`、`_resolve_spec` 与 `_animate_fem_follow`。可用下面的只读命令定位；该文件不在上述已归档清单内：

```bash
git show cb60f01b32786cc9c26f754f91b7be4bef3f9ca6:topogym/world/genesis_ipc_vertex_constraints.py
```

它已经实现“建场前预留容量，运行时启用／撤销 `SoftPositionConstraint`，更新目标位置”的核心过程。因此 `grasp_ipc.py` 不必从零探索这套调用，但不能原样恢复其全局安装方式。迁移时需要处理：

- 将全局 `_SPECS`／`_INSTALLED` 和替换 coupler 的 `install()` 收敛到当前 World／IPC 生命周期；复用当前版本适配，避免重复安装旧的 dt、FEM 建场和材料补丁。
- 区分预留容量与取得资格。旧 `_select` 在半径内无粒子时回退到最近粒子，可用于某些建场选择，但不能成为自动抓取准入；手附近没有合格候选时必须拒绝。
- 保留“先清空可用区域，再写入所有 active 区域”的更新顺序，避免未激活材料带擦掉已激活邻带；多个 active 区域重叠时仍需 manager 明确拒绝或执行已声明的交接规则，不能按循环最后一次写入决定归属。
- 为材料索引、active、targets、owner、局部 offset 与 native checkpoint 补成对 capture/restore；旧句柄的 `active` 或 `_SPECS` 不会因为现有引擎 checkpoint 自动恢复。恢复时不得重新搜索最近材料带。

**旧逻辑仍然留下三块主要新工作：**（1）从持续夹爪 action 自动驱动取得／释放，而不是由 planner 指名调用 attach；（2）独立于任务的状态机和可恢复事件、计时、归属；（3）当前后端上的碰撞、独立释放、失败与 rewind 验收。历史代码能节省门控和约束适配的开发，但不能替代这三块工程。

回收顺序按 §9.3：先用 Fiber 的纯接触筛选、Lock／Coil 的取得规则和共用约束核查完成刚体抓放链路；随后把 Blanket 选片和 PBD 附着放到稳定单折 fixture 上验证；IPC 使用已找到的句柄／animator 代码作为适配起点。各项保留原提交、函数来源和修改说明，将代码提取到当前模块，**不从当前源码 import `legacy/` 或 `runs/`**。坐标数学优先复用现有工具，不重复恢复旧 Attachment 中直接写物体／粒子位姿和包装 `scene.step` 的控制方式。

## 10. 首批实施状态（2026-09-26）

**2026-09-27 后续排期更新：**按用户要求新增 [FEM IPC 绳与 PBD 布的公共自动抓持开发计划](../modules/soft_grasp_assist_engineering_plan_20260927_zh.md)。两种材料通过独立夹具开发和验收，不等待完整 Task、Blanket 复杂初态或彼此后端完成；该安排替代本文旧的“先 PBD、后 IPC”排期。历史成功证据、可提取函数、PBD 碰撞限制及实施门槛见新计划。本次仅新增计划，未部署柔体后端。

§9.3 的第一批纯计算、机器人开合／指部描述、可恢复 manager、刚体后端和 World 自动生命周期已实现。文件与配置说明见[公共抓持模块](../modules/grasp_assist_zh.md)。`world/physics/grasp_manager.py` 与 `utils/grasp.py` 使用不同文件名；PBD／IPC 不创建假实现占位。

实际执行仍是原有 `interaction.step(action)`。新增的管理配置叫 `SimulatorConfig.grasp_assist`，默认 `none`；开启 `contact_weld_v1` 必须明确允许的实体／link／局部区域。静态合同对普通 agent 可见，候选／接触真值只进入特权 state 与管理员日志。没有修改 13 个任务的 assets、setting、planner 或成功判据，未把 assist 批量开启。

已用独立源码快照完成[CUDA 机械夹具验收](../../../runs/test_results/grasp_assist_20260926_04_cuda/README.md)：双指取得、重力下抬起、非末尾单手释放、保留另一只手、障碍阻挡、取得前／中 rewind、非法 action、reset，以及创建约束后故意失败再恢复。该结果是公共工具资格，不是正式机器人或拓扑任务 solve。配套单元／合同回归 **185 passed**。

另用现有方块策略完成了[实际 Panda／Robotiq 与标准 Nyx segment 链路验收](../../../runs/test_results/grasp_assist_robot_20260926_02/README.md)：从默认 home 连续取得、抬起、跨两段搬运、释放和放稳，期间没有抓持失效。514 个 tick／515 份状态，段间持握与三路 RGB 一致，录像和逐 tick 索引核查通过；参与此次 assist 修改的运行时文件与快照一致。此结果仍是测试方块的共享工具资格，不将 13 个任务记为已解。

后续依次是：正式任务声明／验收抓持区域和接近路径；在稳定布片上实现 PBD 后端；再适配 IPC 的临时局部材料约束与恢复。历史端点永久连接继续保持其独立身份。修改 World/state 后，旧 Blanket 冻结初态资源必须重新导出与复验；当前默认 authored setting 未切换为旧冻结资源。
