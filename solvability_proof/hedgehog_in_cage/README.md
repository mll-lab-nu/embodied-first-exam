# Hedgehog in Cage 可解性证明

三变体目标的当前完成度是 **2/3**：easy、medium 已完成默认 home 全程执行、原生成功、独立审计和证据归档；hard 尚未完成。逐变体索引见[汇总](summary.json)，不能将两档完成称为三变体全部完成。

| 变体 | 已有证据 | 尚缺内容 |
| --- | --- | --- |
| easy / `simulator_v1` | [正式证明批次](2026-09-30_easy/README.md)：默认 home 两次抓取全程 238.875 s，原生 `task_success=True`；[9,556 个状态独立审计](2026-09-30_easy/evidence/runs/easy_qualified_audit_01/execution_audit.json)通过 | 该有限实例已完成 |
| medium / `waisted4_dark_wood_v1` | 完整证据已归档；[新增初态及逐次抓取接触检查后的复核](../../runs/hedgehog_three_20260930/medium_audit_regression_03/execution_audit.json)仍通过 | 该有限实例已完成 |
| hard / `fixed_v2` | 原初态自然稳定后的[顶部物体路线](../../runs/hedgehog_three_20260930/hard_settled_top_object_01/object_report.json)及[独立复核](../../runs/hedgehog_three_20260930/hard_settled_top_audit_01/object_audit.json)；首轮实际抓取和抬升已执行 | 保留原任务继续构思顶部取出的抓持/IK；初始穿透与支撑接触须单独记录，完整连续执行及审计尚未完成 |

进行中的尝试及恢复入口保存在[进度检查点](../../runs/hedgehog_three_20260930/progress.json)。规划失败、局部抓取和替代初态提案均未计入正式完成数；保存的物理状态只供只读规划，新的完整执行仍须从默认 home 开始。

按用户最新要求，先汇报纯物体路线，再进入抓取与 IK。当前 easy 的动作分解和 hard 条件路线见[任务说明](../../docs/develop/tasks/hedgehog_in_cage_zh.md#当前纯物体解法)，easy 的[关键姿态图](../../runs/hedgehog_three_20260930/object_route_report_01/easy_gate_sequence.png)只展示已复核的几何通路。

本轮曾因旧守护逻辑记录的[CPU 99.4% 事件](../../runs/hedgehog_three_20260930/easy_measured_offline_guard_11/resource_pause.json)暂停，随后已按 AGENTS.md 最新资源规则恢复：CPU 只监控，内存达到 90% 才自动停止本轮工作进程。旧运行证据保持原样。hard 的[初态及版本修正补丁](../../runs/hedgehog_three_20260930/hard_initial_proposal_01/proposed_task_change.patch)保留为未应用的历史候选；用户已授权沿原任务的顶部出口继续，无须以应用该补丁为前提。

[2026-09-30 已验收批次](2026-09-30/README.md)：当前四腰窗 `waisted4_dark_wood_v1` 的 medium、默认参数、seed 0，完成物体通路、机械臂 IK、默认 home 开始的连续物理执行及独立审计。原生 `task_success=True`，56.5 s。

[2026-09-30 easy 已验收批次](2026-09-30_easy/README.md)：先抓 S8 从宽侧窗移出，自然释放到支撑后换抓 S6，微转约 4.4° 完成出笼并进入原目标区。原生成功及独立审计通过；16,708 个文件、约 3.80 GB 的独立副本已逐文件校验。首次诊断的原始 `task_success=False` 保留，未追改；原 medium 批次也保持原样。

两档均使用 Panda + Robotiq、接触触发的 `contact_weld_v1` 辅助抓持、CPU 双精度、25 ms tick / 40 子步。easy 明确声明可覆盖两次抓取邻域的接触球域，并分别验证两次新的双指接触。未证明纯摩擦抓取、其他 seed、hard 或整个参数域；没有新增 RGB/视频。
