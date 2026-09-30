# 被动策略与参考运动

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

当前已验收的可解性证明统一保存于 [solvability_proof/](../../solvability_proof/README.md)。[Cast Keyhole](../../solvability_proof/cast_keyhole/README.md) 与 [Cast Coil](../../solvability_proof/cast_coil/README.md) 均完成三档默认参数、seed 0 的实际 Task success 和独立逐 tick 复核，包含冻结 policy/IK 源码与完整 action/状态证据；使用显式 CPU 25 ms tick / 40 子步、接触触发的辅助抓持，无 RGB/视频。下方 9 月 27 日 Coil 记录保留原批次范围。

**分段可解性验证流程**（`solvability.py` + `scripts/run_solvability_workflow.py`，2026-09-29）把一局拆成若干段（空手移动、抓取、持工具交互、松手、静置），每段有入口检查、逐物理 tick 的不变量检查（例如工具／机械臂不碰导线、接触统计完整）、出口检查和仿真时长上限，下一段总是从上一段结束时的实际状态重新规划。诊断模式在同一个存活的 Env 里运行：某段失败就回溯到这一段的起点，换下一个候选参数；候选用完则保持 Env 存活，等待 `control/next.json` 提交的新参数（只收 JSON 参数，不热加载代码）。每段选中的参数写入 `qualification/selection.json`，正式模式用 `--selection` 从 home 连续执行、不回溯。一次零回溯、从出生态开始且原生 success 的诊断运行，本身就是连续执行证据，状态记为 `native_success_pending_independent_audit`。无论哪种，仍须任务自己的独立审计通过才计入 `solvability_proof`；局部段通过、只读路径检查通过都不算证明。任务接入方式是 `factory(env, context)` 逐步产出 `Step(name, candidates, build)`，Buzz 的实现见 `buzz_wire_3d/stages.py`。

2026-09-27 历史首轮：Hedgehog / Claws 两个新 medium 的实现见 `hedgehog_in_cage/`、`interlocked_claws/` 和共享 `rigid_reference/`。目前提供明确路线的实测反馈执行器、完整物体几何检查、有限 SE(3) 路线搜索及 Claws 三档摩擦持件诊断；尚无已验证的完整机器人路线，CLI 不开放未取得 P1/T2 资格的 `solve`。入口为 `scripts/run_hedgehog_policy.py` 与 `scripts/run_interlocked_claws_policy.py`，默认 `--part geometry`；结果与阻挡项见[实施记录](../../runs/test_results/hedgehog_claws_policy_20260927/README.md)。不得从文件名或 policy_done 推断解题成功。

**2026-09-30 Hedgehog 更新：** 当前四腰窗 medium、默认参数、seed 0 已完成物体通路、1,273 点 IK、从默认 home 连续执行和独立审计，原生 `task_success=True`。新入口为 `plan_hedgehog_object_oracle.py`、`run_hedgehog_oracle.py --assisted` 和 `audit_hedgehog_oracle.py`；旧 `run_hedgehog_policy.py --part solve` 的资格门控保持其历史范围。辅助抓持、时序与有限实例边界见[正式证明](../../solvability_proof/hedgehog_in_cage/README.md)。

`motions/cast_coil.py` 提供 Coil 所需的螺旋/刚体参考运动和采样，使用公共 `utils/geometry/rigid_motion.py` 运动合同，由几何派生与证书测试引用。

`base.py` 定义单输入 `act(obs) → action/None` 协议与 `ActionSequencePolicy`。`examples/cube_pick_place.py` 是可读的 Panda EE_ABS 拾起／放下策略：使用自身状态与获准的 world 观测，返回一条低层 action，由管理方 SegmentRunner 负责执行。默认原位放回，指定 `place_entity_id="target_marker"` 可搬运；它需要 unlimited 观测，不是 RGB 视觉策略。`part=pickup/transfer` 支持管理方显式拆分两段，transfer 必须给出原始拾取位置。

运行样板：`.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py --case pick_place`。默认使用显式长程测试时序，真实结果与默认时序资格分开，详见[实施记录](../../docs/develop/dev-logs/scripted_policy_execution_implementation_20260926_zh.md)。

`lock_picking/lock_picking_medium_planning.py` 提供 Lock 的实测位姿 oracle，同样只实现 `act(obs)`，没有 Scene 或 attach/detach。自动 assist 由 Env 管理；执行入口为 `scripts/run_lock_picking_policy.py`。medium 的 `historical_physics_v2` 恢复历史两次回退槽形和被动机构物理参数；策略包含拾取、两次回退换槽、支撑换抓、终点释放。旧摆位绑定的关节路径改用当前摆位下的 TCP 路径，窄孔插入阶段保留负载补偿并检查实测对准误差。seed 0 的 CUDA／Nyx 全程已通过独立插入、释放、静置检查，正式 Task terminal 尚未完成资格校准。具体时序、视频和失败记录见[本轮报告](../../task_rollouts/lock_assist_20260927/README.md)，不由 planner 文件存在推断其他实例资格。

未接入的 subgoal、waypoint、grasp_sites 及旧 Horseshoe/Lock 运动工具已删除。本目录只产生参考运动或低层动作。实际物理推进由 simulator 的管理方 runner 完成；参考路径本身不代表任务成功。

`horseshoe_ring/`（2026-09-30）为当前三档复核物体参考路径，并为 easy 提供只读双臂联合 IK、观测反馈控制和独立逐 tick 审计。`scripts/run_horseshoe_policy.py` 冻结输入与源码，分开记录几何、IK 和物理诊断，监控资源，仅内存达到 90% 时停止本次进程，CPU 只记录。三档物体路径及 easy 从默认 home 到折合、支撑交接和抓环已有证据；取环和固定区域放置尚未完成。`ring_route.py` 的短段接触候选、`joint_route.py` 的自由圆环搬运搜索均需另行物理验收；详见[任务说明](../../docs/develop/tasks/horseshoe_ring_zh.md)。

`cast_coil/baseline.py` 提供基础装配被动策略：从 ALOHA home 接近，双指接触取得自动 assist，以实测物体位姿补偿负载偏差，执行原型路线的逆向装配、落桌、释放和沿手爪轴线撤离。入口为 `scripts/run_cast_coil_policy.py`，只通过 `SegmentRunner.run_policy` 执行。seed 0 的一次 Nyx 完整运行已经通过当前 Task terminal 及独立释放/桌面支承复核，视频与失败尝试见[运行报告](../../task_rollouts/cast_coil_assist_20260927/README.md)。该次运行显式采用 10 Hz 控制 / 160 子步，不能当作默认 tick、半时间步、多 seed 或纯摩擦抓取资格。

后续[时序与接触复核](../../task_rollouts/cast_coil_assist_20260927/investigation_06/README.md)发现该视频有高接触力卡滞和突跳；策略过程质量尚需修正，不能仅凭末态成功视为合格装配。执行入口现继承 simulator 默认时序，60 秒 episode 预算单独设置；当前默认时序完整任务成功仍未验证。
