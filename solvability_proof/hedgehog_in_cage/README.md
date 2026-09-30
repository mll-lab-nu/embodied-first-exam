# Hedgehog in Cage 可解性证明

三变体目标的当前完成度是 **1/3**：medium 已验收，easy 和 hard 尚未完成。单独完成 medium 不代表整个 Hedgehog 任务的三变体证明已经完成。

| 变体 | 已有证据 | 尚缺内容 |
| --- | --- | --- |
| easy / `simulator_v1` | [当前初态到目标区的物体路径审计](../../runs/hedgehog_three_20260930/easy_object_audit_01/object_audit.json)；[默认 home 开始的双指抓取及 11.8 mm 实际抬升](../../runs/hedgehog_three_20260930/easy_trial_04/oracle_report.json) | 抓持状态的完整出笼 IK、实际全程执行及独立验收；局部抓取成功不算任务成功 |
| medium / `waisted4_dark_wood_v1` | 完整证据已归档；[新增初态检查后的复核](../../runs/hedgehog_three_20260930/medium_audit_regression_01/execution_audit.json)仍通过 | 该有限实例已完成 |
| hard / `fixed_v2` | [默认初态相交诊断](../../runs/hedgehog_three_20260930/hard_initial_diagnostic_01/diagnostic.json)；[替代初态及完整物体路线提案](../../runs/hedgehog_three_20260930/hard_initial_proposal_01/proposal.json) | 默认初态修正的范围确认及修正后的整套证明；提案不代表当前变体已通过 |

进行中的尝试及恢复入口保存在[进度检查点](../../runs/hedgehog_three_20260930/progress.json)。规划失败、局部抓取和替代初态提案均未计入正式完成数；保存的物理状态只供只读规划，新的完整执行仍须从默认 home 开始。

按用户最新要求，先汇报纯物体路线，再进入抓取与 IK。当前 easy 的动作分解和 hard 条件路线见[任务说明](../../docs/develop/tasks/hedgehog_in_cage_zh.md#当前纯物体解法)，easy 的[关键姿态图](../../runs/hedgehog_three_20260930/object_route_report_01/easy_gate_sequence.png)只展示已复核的几何通路。

本轮曾因旧守护逻辑记录的[CPU 99.4% 事件](../../runs/hedgehog_three_20260930/easy_measured_offline_guard_11/resource_pause.json)暂停，随后已按 AGENTS.md 最新资源规则恢复：CPU 只监控，内存达到 90% 才自动停止本轮工作进程。旧运行证据保持原样。hard 的[初态及版本修正补丁](../../runs/hedgehog_three_20260930/hard_initial_proposal_01/proposed_task_change.patch)仅为待确认提案，尚未应用。

[2026-09-30 已验收批次](2026-09-30/README.md)：当前四腰窗 `waisted4_dark_wood_v1` 的 medium、默认参数、seed 0，完成物体通路、机械臂 IK、默认 home 开始的连续物理执行及独立审计。原生 `task_success=True`，56.5 s。

使用 Panda + Robotiq、接触触发的 `contact_weld_v1` 辅助抓持、CPU 双精度、25 ms tick / 40 子步。未证明纯摩擦抓取、其他 seed、easy/hard 或整个参数域；没有新增 RGB/视频。
