# 刺球出笼

2026-09-30 success 开关更新：所有已集成变体及随机实例现均默认开启成功判断，不再要求历史资格匹配。当前规则为 `hedgehog_placement_v3_default_success`，全尖刺进入目标区及低速保持 2 s 的要求不变。下文的资格、证据范围和 2/3 进度只描述物理解法验收，不控制 episode 能否判成功；历史轨迹及原始结果不改写。详见[当前 success 条件](success_conditions_zh.md)。

**三变体目标进度：2/3 正式完成。** [easy 正式证明](../../../solvability_proof/hedgehog_in_cage/2026-09-30_easy/README.md)和 [medium 正式证明](../../../solvability_proof/hedgehog_in_cage/2026-09-30/README.md)均已完成纯物体路径、IK、默认 home 全程执行、原生成功、独立审计及证据归档。hard 当前默认初态的球核与笼壁碰撞网格相交，已保存[原初态与无碰撞候选初态对照](../../../runs/hedgehog_three_20260930/hard_initial_diagnostic_01/diagnostic.json)，尚未修改其默认初态或授予资格。当前资源规则是 CPU 只监控、内存达到 90% 停止；[恢复点](../../../runs/hedgehog_three_20260930/progress.json)保存剩余 hard 工作，goal 尚未完成。

easy 原生成功运行共 9,555 tick / 238.875 s，从默认 home 连续完成 S8 抓取、侧窗移出、自然释放、S6 重新抓取及最终入区稳定 2 s。[独立审计](../../../solvability_proof/hedgehog_in_cage/2026-09-30_easy/evidence/runs/easy_qualified_audit_01/execution_audit.json)检查全部 9,556 个状态并通过，两次新绑定与同 tick 原生接触力及穿透量一致。[正式归档](../../../solvability_proof/hedgehog_in_cage/2026-09-30_easy/archive_validation.json)包含 16,708 个文件、约 3.80 GB 独立副本；本次内存峰值 28.7%。

此前的[两次抓取完整诊断执行](../../../runs/hedgehog_three_20260930/easy_two_grasp_native_01/oracle_report.json)共 9,584 tick / 239.6 s，完整刺球在同一目标区低速保持 2.725 s。[独立审计](../../../runs/hedgehog_three_20260930/easy_two_grasp_audit_02/execution_audit.json)通过全部 9,585 个状态；两次新绑定分别在 tick 928、7,637 获得真实双指接触证据，运输球体间隙最小 0.100888 mm、机械臂环境间隙最小 2.668452 mm，禁止接触力均为 0，最大接触穿透 0.131217 mm。该次原始 `task_success=False` 保留；首次诊断审计通过后才为 easy 当前默认参数、seed 0 启用有限资格，并以新的原生成功运行取得正式验收。

[六个实测关键状态示意图](../../../solvability_proof/hedgehog_in_cage/2026-09-30_easy/evidence/supporting/easy_audited_execution_figure_01/audited_execution.png)直接使用上述已审计诊断状态中的刺球和夹爪位姿，不是 RGB 录像，也不增加物理成功次数。[资格边界检查](../../../solvability_proof/hedgehog_in_cage/2026-09-30_easy/evidence/supporting/easy_boundary_checks_01/checks.json)通过：其他 seed、参数/默认值/几何/模板变更不继承 easy 资格，缺指接触、未知运输阶段、非 home 起点和缺失末段状态均被拒绝。

此前的[中间段实际执行](../../../runs/hedgehog_three_20260930/easy_far_release_native_01/oracle_report.json)共 7,326 tick / 183.15 s：S8 抓取后从默认 home 连续送到笼局部约 `(88.42, 1.67, 32.93)` mm；松开后自然停靠在底座附近，球心约 `(89.36, 19.94, -77.06)` mm。[该次独立审计](../../../runs/hedgehog_three_20260930/easy_far_release_audit_01/execution_audit.json)的唯一失败项是尚未在最终目标区保持 2 s，保留为第二次抓取和物体续接的起点来源。后来的完整诊断从默认 home 重新执行，没有恢复或拼接该中间段快照；[逐 tick 比对](../../../runs/hedgehog_three_20260930/two_grasp_prefix_regression_02/comparison.json)确认第一次释放前的实际状态与动作完全一致。

## 当前纯物体解法

按用户 2026-09-30 最新要求，后续每个变体先汇报不带机械臂的动作分解、关键姿态和几何验证结果，再构思抓取与 IK。物体路线找到后即汇报，不等机械臂全程成功才展示。

easy / `simulator_v1`、默认参数、seed 0 的完整物体路线已通过独立审计。下面的坐标以笼中心为原点，单位为 mm，+X 指向宽度 60 mm 的侧窗；允许直接控制刺球的平移和转动，尚不约束机械臂或抓持。

1. 保持初始朝向，把球心从 `(0, 0, -29.25)` 上移到笼中心 `(0, 0, 0)`。
2. 在笼内多次倾斜和转向，同时向 +X 侧窗靠近，达到约 `(34, 0, -13.09)`。这段包含调整和小幅回退，不能用一次直线平移替代。
3. 先推进到 `(40, 0, -13.09)`，再边转边移到约 `(63, 0, -6.72)`，让球核穿过侧窗。
4. 在窗边继续上抬与转向，球心经过约 `(66.77, 0.72, 27.51)` 和 `(75.17, 4.07, 26.95)`，随后调整高度与朝向，让其余尖刺避开窗框。
5. 从约 `(75, 0.50, 11.44)` 保持朝向向外移动到 `(170, 0.50, 11.44)`，完全离笼；再经笼外 `(220, -283.44, 11.44)` 搬到目标区中心 `(0, -283.44, -41.56)`。

[六个关键姿态图](../../../runs/hedgehog_three_20260930/object_route_report_01/easy_gate_sequence.png)来自实际场景网格和保存的位姿，不是物理执行录像。完整路径有 20 个关键位姿；几何检查覆盖完整可视/碰撞表面、关键位姿之间的连续运动及最终全部尖刺进入目标区，连续间隙下界为 **0.100379 mm**。见[物体路径证据](../../../runs/hedgehog_three_20260930/easy_object_frozen_01/object_witness.json)及[独立复核](../../../runs/hedgehog_three_20260930/easy_object_audit_01/object_audit.json)。这些结果只确立纯物体几何通路，未确立完整机械臂执行。

最新实测释放姿态已有更短的[物体续接路线](../../../runs/hedgehog_three_20260930/easy_far_released_escape_01/compact_goal_continuation.json)，同样先向用户报告再搜索第二次抓取。其[关键姿态图](../../../runs/hedgehog_three_20260930/easy_far_released_escape_01/short_continuation.png)展示：保持朝向抬起 12 mm；再向外约 7 mm、上抬约 6 mm，同时转约 4.4°；随后向外上方移到球心 x=150 mm 并转回原朝向；最后保持朝向经笼外一侧进入原目标区，全部尖刺包含在区域内。[独立重建几何复核](../../../runs/hedgehog_three_20260930/easy_far_continuation_audit_01/object_audit.json)已通过，核对了实际释放状态、资产身份及原目标区域，主要路线连续间隙下界为 **0.100429 mm**。该几何证书不覆盖最初离开支撑的 0.1 mm，其后的竖直抬升段下界为 98.18 μm；重新抓取和离开支撑已由后续完整诊断实际执行并逐 tick 审计，不扩大为连续动力学无穿透证明。

第二次抓取选择 S6；最初的[637 个假定抓持 IK 样本](../../../runs/hedgehog_three_20260930/easy_far_regrasp_dense_02/candidate_2.json)通过后，实际第二次抓取抬升了 11.631 mm，再用[实测抓持位姿重新规划](../../../runs/hedgehog_three_20260930/easy_two_grasp_native_01/regrasp_1_held_plan_0.json)，637 个 IK 样本通过，机械臂间隙最小 6.642 mm、关节限位余量最小 0.837 rad。配置使用 `contact_weld_v1`，单一声明接触球域包含两次抓取各自的 30 mm 邻域，合并半径为 67.513 mm；两次绑定均须重新满足真实双指接触、闭合意图及原 TCP 距离门限。

较早在 x≈65 mm 处释放的[续接路线](../../../runs/hedgehog_three_20260930/easy_released_object_03/object_report.json)需要约 121° 的窗口转向；其有限抓法搜索未找到可达的完整 IK。另一个 144° 窄窗方向已接通[物体出笼后半段](../../../runs/hedgehog_three_20260930/easy_narrow_tail_01/tail_report.json)，但[26,000 次初态连接搜索](../../../runs/hedgehog_three_20260930/easy_narrow_object_01/object_witness.json)未接通；这些均不构成无解结论，也未增加正式完成数。

hard / `fixed_v2` 按用户最新授权保留默认初态，继续验证原仿真任务的顶部取出路线。初始球笼穿透不是全局无解结论，但不能声称存在从 t=0 起全程无穿透的几何路径。[原任务自然静置记录](../../../runs/hedgehog_three_20260930/hard_default_settle_01/settle_report.json)保存从默认 home 开始的 3 s / 120 tick：未启用辅助抓持，机械臂保持 home；初始消穿透瞬态仍完整保留，不能删除或替换为后续状态。

自然稳定后的[完整物体续接路线](../../../runs/hedgehog_three_20260930/hard_settled_top_object_01/object_report.json)已通过[独立重建复核](../../../runs/hedgehog_three_20260930/hard_settled_top_audit_01/object_audit.json)：球心由约 `(-5.606, -15.882, -66.788)` 保持朝向抬升 12 mm，再经 `(-8.480, -8.445, -14.833)` 边上抬边转向，接至 `(-6, 0, 55)`，继续上抬并分段转动，通过顶部钥匙孔；升至 z=225 完全离笼后搬入原目标区。[关键姿态图](../../../runs/hedgehog_three_20260930/hard_settled_top_figure_01/hard_settled_top_sequence.png)只展示物体路径，非机器人执行。主要路线连续间隙下界 **0.111443 mm**；几何证书排除最初离开支撑的 0.1 mm，其后的抬升段下界为 98.966 μm。初始消穿透、接触离开支撑与连续机器人执行仍须分开审计；不能计作 hard 完整证明。

上述物体机制已先向用户报告，再进入抓取与 IK。[首轮实际抓取](../../../runs/hedgehog_three_20260930/hard_top_native_probe_01/oracle_report.json)从原初态/default home 连续完成接近、双指接触触发绑定及约 11.928 mm 抬升，后续有限搜索未找到完整实测抓持 IK 路径，运行如实记录为失败。当前继续检查夹爪沿笼柱扭转方向上抬后转入顶部出口的路线，没有恢复或拼接物理快照。

后续 S6 抓法已从原初态连续[实际送达顶口候选位置并释放](../../../runs/hedgehog_three_20260930/hard_top_release_native_01/oracle_report.json)，共 2,749 tick / 68.725 s。球心曾到达笼局部 z≈121 mm，但释放后落回笼底，没有形成顶口支撑，不能算换抓成功或完成取出。[独立审计](../../../runs/hedgehog_three_20260930/hard_top_release_audit_01/execution_audit.json)唯一未通过项为最终目标区保持时间；运输中的球体间隙最小 0.905 mm、机械臂间隙最小 0.265 mm、运输球笼接触力为 0。这只是完整记录的中间阶段试验。

原任务审计新增显式 `--allow-hard-initial-settle` 范围：仅限默认 hard / `fixed_v2` / seed 0、25 ms tick / 40 子步，保留并声明 t=0 穿透；记录的静置阶段须在 home、无辅助绑定、球心留在声明的笼内范围并最终稳定。默认严格审计仍拒绝初态相交，不能将该范围称为从初态开始全程无穿透的几何证明。[篡改与范围检查](../../../runs/hedgehog_three_20260930/hard_settle_audit_boundaries_01/checks.json)已通过，[medium 回归审计](../../../runs/hedgehog_three_20260930/medium_audit_regression_04/execution_audit.json)仍通过。hard 尚无原生完整成功或正式资格。

笼内翻转、释放的[连续实际试验](../../../runs/hedgehog_three_20260930/hard_s2_up_release_native_01/oracle_report.json)已完成 2,813 tick；释放后 S2 未保持朝上，而 S6 形成更接近竖直的稳定朝向。[独立审计](../../../runs/hedgehog_three_20260930/hard_s2_up_release_audit_01/execution_audit.json)唯一未通过项仍为最终目标区保持时间；运输球体间隙最小 0.761 mm、机械臂间隙最小 1.141 mm，运输球笼接触力为 0。

从这个实测姿态出发的[新物体路线](../../../runs/hedgehog_three_20260930/hard_flipped_s6_top_object_01/object_report.json)已通过[独立重建复核](../../../runs/hedgehog_three_20260930/hard_flipped_s6_top_audit_01/object_audit.json)：上抬 12 mm，逐步将 S6 转至朝上，到顶口后倾斜，使长刺 S2 通过窄槽，球体从圆口转出，再移入原目标区。主路径连续间隙下界 0.100326 mm；仍排除最初离开支撑的 0.1 mm。机制已先向用户报告，尚未获得相应完整机器人执行。当前检查上方重新抓 S6，以及原 S6 实测抓法直接采用该出口朝向的可能性；每次正式候选均须从原初态/default home 连续重做。

进一步的[转正 S2 后降低释放高度试验](../../../runs/hedgehog_three_20260930/hard_s2_upright_lower_native_01/oracle_report.json)完成 3,581 tick / 89.525 s；1,213 个离线 IK 样本通过后，实际释放仍未保持 S2 竖直，稳定后的 S2 向上分量为 0.4153、S6 为 0.8721。[独立执行审计](../../../runs/hedgehog_three_20260930/hard_s2_upright_lower_audit_01/execution_audit.json)只有最终目标区保持时间未通过，不能算完成任务。从这次实测释放姿态出发的[另一条顶部物体路线](../../../runs/hedgehog_three_20260930/hard_released_s2_top_object_02/object_report.json)通过[独立复核](../../../runs/hedgehog_three_20260930/hard_released_s2_top_audit_01/object_audit.json)：再抬升 12 mm，在笼内将 S2 转正，S6 穿窄槽，球体从圆口转出。主路径间隙下界 0.122686 mm；此次单独排除最初 0.2 mm 支撑接触段，其后离开支撑段下界仅 2.017 μm，仍须实际抓取和起吊验证。当前为第二次 S2 抓取重规划包含夹爪的笼内路径；尚无完整 hard 机器人证明。

最新的[平端支撑试验](../../../runs/hedgehog_three_20260930/hard_s1_flat_foot_native_01/oracle_report.json)已从原初态/default home 连续完成 S1 抓取、抬高转正、放低及释放，共 2,763 tick / 69.075 s。释放 5 s 后，S5 平端支撑在笼底、S6 向上分量为 0.999999999999585，球心位于笼坐标约 `(-22.885, -15.086, -54.000)` mm，速度接近零。[独立审计](../../../runs/hedgehog_three_20260930/hard_s1_flat_foot_audit_01/execution_audit.json)仅有最终目标区保持时间未通过；运输球体间隙最小 0.640 mm、机械臂间隙最小 0.928 mm，最大接触穿透 0.0247 mm。这是实际稳定换抓支撑，尚未证明能完成第二次抓取或取出。

从这次实际站稳姿态出发，[顶部物体续接路径](../../../runs/hedgehog_three_20260930/hard_standing_s6_top_object_02/object_report.json)保留 S6 朝上取出的机制：先抬升 12 mm，再倾斜并使 S2 通过窄槽、球心穿过圆口，升到 z=225 mm 后搬入原目标区。主路径间隙下界 0.119157 mm；最初离开支撑的 0.1 mm 单独排除，其后抬升段下界 98.987 μm。[独立几何复核](../../../runs/hedgehog_three_20260930/hard_standing_s6_top_audit_01/object_audit.json)与[候选机制示意图](../../../runs/hedgehog_three_20260930/hard_flat_s6_top_figure_01/flat_top_candidate.png)均不代替第二次实际抓取。初步顶部抓姿仍受夹爪与笼口碰撞限制；S4/S6 顶圈支撑路径虽已连通并通过 IK，但[提前释放试验](../../../runs/hedgehog_three_20260930/hard_s1_rim_early_native_01/oracle_report.json)和[平移修正后的试验](../../../runs/hedgehog_three_20260930/hard_s1_rim_refined_native_01/oracle_report.json)均落回笼内；前者还触发机械臂/固定物接触停止，后者的[审计](../../../runs/hedgehog_three_20260930/hard_s1_rim_refined_audit_01/execution_audit.json)仅有最终目标区未通过。几何可达和两刺投影位于顶圈上，不能替代实际稳定支撑。hard 仍为未完成。

为筛选支撑机制，另建了[独立纯物体接触诊断](../../../runs/hedgehog_three_20260930/hard_rim_stability_diagnostic_01/report.json)，使用原笼体/球体资产、摩擦系数及求解参数，但直接在候选支撑姿态初始化独立模型；**这不是 Task 默认初态执行，也不转移为证明**。四个接触高度对齐后的短 S4/S6 支撑都滑落，长 S2/S6 居中支撑保持在顶圈 5 s，末态仍有约 5.37 mm/s 瞬时速度，不能称为已静止。作为对照，平端 S5 站立姿态保持稳定。当前继续检查实际笼底站稳后换用另一 S1 抓法，再送到长 S2/S6 支撑的路线。

oracle 增加可选 `pickup_departure_hints`：先实际抬离支撑 0.1–1 mm，再从新实测抓持状态重新验证侧移/转动/上抬路径。新 `pickup_departure` 阶段使用运输保护，并由独立审计归为 `clear_transport`，不能把整段操作隐藏在离开支撑的接触例外内。默认仍竖直抬升 12 mm；[30 项边界检查](../../../runs/hedgehog_three_20260930/hard_departure_boundaries_01/checks.json)和 [medium 回归审计](../../../runs/hedgehog_three_20260930/medium_audit_regression_05/execution_audit.json)通过。新分支尚待实际运行验证，不构成 hard 完整成功。

松手后的实际空夹爪距笼体约 0.928 mm，低于空手转移规划器的 1 mm 起点要求。[只读转移诊断](../../../runs/hedgehog_three_20260930/hard_side_retreat_ik_01/ik_report.json)表明，先沿手轴退出 8 mm、选用 15 mm 预抓取距离，可使五个侧抓候选通过转移和接近 IK；这不等于实际换抓。oracle 新增可选 `release_retreat_m`，从释放后的实时状态重算并检查 IK；独立审计将其作为 `released_transfer`，要求全程无绑定且保留机械臂碰撞检查。[13 项边界检查](../../../runs/hedgehog_three_20260930/hard_retreat_boundaries_01/checks.json)和 [medium 回归审计](../../../runs/hedgehog_three_20260930/medium_audit_regression_06/execution_audit.json)通过，新退开动作尚待原生试验验证。

[六个可达顶口姿态的独立释放诊断](../../../runs/hedgehog_three_20260930/hard_reachable_release_diagnostic_01/report.json)均落回笼内；不能只凭两刺投影越过圆口就推断松手后能挂住。另一条研究分支筛选更倾斜的 S1 抓法，[225 个候选](../../../runs/hedgehog_three_20260930/hard_steep_exit_screen_01/report.json)通过顶口附近至出笼、原目标区的连续刚体几何检查，但笼底到顶口的连接仍在搜索。其中三个候选通过[空手转移及接近 IK](../../../runs/hedgehog_three_20260930/hard_steep_s1_pickup_ik_01/ik_report.json)，当前启动原初态连续换抓试验；正式证明仍为 easy / medium 两变体，hard 未完成。

旧[替代初态提案](../../../runs/hedgehog_three_20260930/hard_initial_proposal_01/proposal.json)及补丁保留为历史候选，尚未应用，也不是继续原任务验证的必要前提。[局部初态检查](../../../runs/hedgehog_three_20260930/hard_initial_local_review_01/review.json)另发现保持高度和朝向、向内平移 3 mm 即可消除相交，但这是另一初态的端点检查，没有转移为当前任务资格。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**2026-09-30：当前 medium 已完成有限实例可解证明。** 四腰窗 `waisted4_dark_wood_v1`、默认参数、seed 0 已通过物体通路、机械臂 IK、默认 home 开始的连续物理执行及独立逐 tick 审计；原生 `task_success=True`，56.5 s，完整刺球在固定目标区低速保持 2 s。完整证据及复现命令见[正式证明目录](../../../solvability_proof/hedgehog_in_cage/README.md)。

物体路径有 7 个关键位姿，初始抬升段连续间隙下界 0.199 mm，后续出笼和入区段下界 1.044 mm。把实测夹爪和腕部加入后重新规划，得到 1,273 个 IK 采样点；实际执行审计的球体运输间隙最小 1.027 mm，机械臂环境间隙最小 2.924 mm。几何证书检查完整可视/碰撞表面并采用刚体运动上界与 1 μm 数值误差预算；不等于连续动力学证明。

该 medium 证明使用 Panda + Robotiq、真实双指接触触发的 `contact_weld_v1` 辅助抓持、CPU float64、25 ms tick / 40 子步，无 RGB/视频；不向纯摩擦抓持、其他 seed、easy/hard 或整个参数域转移资格，其他变体须各自取得证据。旧 demos 仅作为解法参考。固定目标区、全尖刺包含、低速保持 2 s 的规则未放宽，允许保留抓持。此前未启用 terminal 的资格运行保留原始 `task_success=False`。

活动入口：[物体规划](../../../scripts/plan_hedgehog_object_oracle.py)、[机器人 oracle](../../../scripts/run_hedgehog_oracle.py)、[独立审计](../../../scripts/audit_hedgehog_oracle.py)。三个入口均冻结源码并保存资源记录，内存超过 90% 时停止本次进程；本次正式复跑峰值为 24.4%。

下文为历史版本记录，六椭圆窗、旧三原型、落桌释放规则和 09-27 搜索失败均不代表当前四腰窗的验收状态。

> **2026-09-27 更新：** medium 已改为深色实木、六个均匀纵向椭圆窗（58×224 mm）的笼体，复用原刺球；原 oblique_gate 描述属于旧版。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

Panda + Robotiq 将带刺球从木笼开口取出，放桌、解除辅助抓持并静置。基础原型包含 CLASSIC wood，当前生成器采用单斜窗、固定六刺侧孔和 GEN 顶部钥匙孔三个原型。

源码：[geometry.py](../../../topogym/tasks/hedgehog_in_cage/geometry.py) · [scene.py](../../../topogym/tasks/hedgehog_in_cage/scene.py) · [classic_families.py](../../../topogym/tasks/hedgehog_in_cage/classic_families.py) · [prepare_classic_prototypes.py](../../../topogym/tasks/hedgehog_in_cage/prepare_classic_prototypes.py) · [variants.py](../../../topogym/tasks/hedgehog_in_cage/variants.py) · [variant_validation.py](../../../topogym/tasks/hedgehog_in_cage/variant_validation.py) · [agent_adapter.py](../../../topogym/tasks/hedgehog_in_cage/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/hedgehog_in_cage.yaml)；场景入口：`python -m demos.environment_bootstrap.hedgehog_in_cage`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

当前三个有效基础变体各保留完整三视角，分别位于 `demos/hedgehog_in_cage/varaition_oblique_gate/`、`varaition_fixed_side_window/`、`varaition_gen_keyhole/`。2026-09-21 从原完整实测状态补录了单斜窗和固定侧孔，未增加动力学执行成功次数；GEN 原视频迁入对应目录。每个相机叶子目录一份 MP4，直链见 Demo 目录。

## 变体与下一步

v2 支持固定/参数模式、尺寸、位置、朝向、木质外观与保存/重载；随机后代仍是 physical_execution=not_run。侧孔与 CLASSIC 可以共享策略，不要求所有家族的 IK 本质不同。

## 当前证据

- [2026-09-16_classic_wood](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood)
- [2026-09-19_classic_replacements_v2](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_classic_replacements_v2)
- [2026-09-19_generator_replacements_review_v2](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_generator_replacements_review_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 2026-09-27 Scripted policy 首轮实施

新 medium 的反馈执行器与几何搜索已接入，但完整机器人路线尚未建立。六窗对照、8,192 个候选及 12,000 次 SE(3) 搜索扩展未在声明范围内找到完整出笼通路；这不是全局无解证明。当前目标仍要求全部尖刺进入固定区域并低速保持 2 s，正式终态资格未开启。见[实施与证据](../../../runs/test_results/hedgehog_claws_policy_20260927/README.md)及[开发计划实际进展](hedgehog_claws_scripted_policy_plan_20260927_zh.md#11-首轮实施已接入与未通过项)。
