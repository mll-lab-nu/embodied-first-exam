# 马蹄环

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

更新：2026-10-03。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## Calibration-tools 续作：建模候选待审核

本轮仍为 **easy / seed 0 开发探索，完整机器人成功数没有增加**。正式 scripted policy 没有引入 calibration-tools；新增建模生成、参数补丁、质心坐标对齐及 Nyx 预览仅在 [开发适配器](../../../topogym/planning/calibration_tools/adapters/horseshoe_ring.py)。用户要求先审核建模截图，再继续采用新模型。

对原模型 844.5 s 停点的[接触对照](../../../runs/oracle_dev/horseshoe_20261003/original_contact_comparison.json)复现了全部机器人链接位置，128 项生成资产 SHA-256 与原运行完全相同。FCL 最大合格夹指穿透为 0.154 mm，原生记录为 0.165 mm，普通接触约 0.034 mm；该停点通过原生 1 mm／2 mm 上限。旧 oracle 的 0.8 mm 额外余量确曾造成失败，但不能据此认定原生判据普遍误报，或把放宽判据作为完整解法。

当前送审候选只修改目标环：实际中心线半轴从 **70.101 / 66.763 mm** 增至 **74.101 / 70.763 mm**，线径仍为 5.6 mm，马蹄与链环尺寸保持原值。按原密度重新生成资产后，环质量从 81.66 g 变为 86.43 g。[候选及未应用参数补丁](../../../runs/oracle_dev/horseshoe_20261003/selected_candidate.json)保留原模板哈希；正式模板、材料、辅助抓持和任务判据没有修改。

审核图：[正面同尺度对照](../../../runs/oracle_dev/horseshoe_20261003/selected_geometry_review_v2/front.png) · [侧面对照](../../../runs/oracle_dev/horseshoe_20261003/selected_geometry_review_v2/side.png)。这是实际生成网格的工程投影，**不是仿真截图**。早期原模型 Nyx 近景成功；最终候选的 Nyx 在原生 renderer `startup()` 处反复段错误，关闭离线内核缓存、独立工作目录／缓存及显式 CUDA 重试均未恢复，故不能交付这版的 Nyx 帧；失败日志保留在本轮目录，不将崩溃当作物理任务失败。

该候选从上述实测构型出发，在其余四个部件固定时找到[完整物体退出路线](../../../runs/oracle_dev/horseshoe_20261003/selected_exit_certificate.json)：7 个姿态，初始实体包含检查通过，全部视觉面和保守包围碰撞体、桌面参与连续边界检查，净空下界至少 0.150 mm，终点分隔面间隙约 8 mm。它只证明该假设起点的物体退出，不包含新模型从 home 到起点的物理过程、被动部件动力学或固定目标区成功。较早同时减薄／收窄马蹄的探索不再是送审方案；工具已处理尺寸变化造成的质心偏移，避免把非预期实体平移当作净空改善。

[原生 IK／接触筛选](../../../runs/oracle_dev/horseshoe_20261003/selected_exit_ik.json)仍拒绝当前抓法：左手夹指与非抓持上马蹄的预测接触达到约 1.40 mm，超过普通接触 1 mm 上限。实际重新抓持与完整机器人路线未完成；不能将纯物体证书改写成 IK 成功。后续需在用户审核尺寸后重新规划抓姿、验证新初态并从 home 连续执行。

工具验证：5 项新增建模合同、12 项既有会话合同、16 项候选／抓持合同及静态发布隔离检查通过；这些检查不授予任务成功或运行镜像资格。证据集中在 [`runs/oracle_dev/horseshoe_20261003/`](../../../runs/oracle_dev/horseshoe_20261003/)。

## 当前默认三档的 oracle 与证明工作

当前 easy / medium / hard 分别是 `waist_mild` / `u_mild` / `waist_ellipse`，revision 为 `coupled_shapes_settled_v2`，从桌面物理静置姿态出生。下文 9 月 18–21 日的 F1/F2/F3 视频属于旧的接近方向家族，不能授予当前三档成功资格。

目前按物体路径、机器人 IK、连续物理执行的顺序补充证据，**尚未取得当前版本的完整机器人可解性证明**：

**最新连续实证：** 直线优先方案 `live46` 已从默认 home 完成折合、交接、抓环、参考翻环检查点，并实际执行上提与侧移。截至 1122.5 s 的[44901 状态前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_46/prefix_audit_through_state44900.json)全部通过，源码与 home 有效、机器人观测完整，普通接触最大 0.391 mm、合格夹指最大 0.384 mm，无抓持丢失、19 对闭环保持。尚未分离或达到原生成功。`live42`、`live46`、`live47`、`live48` 仍验证基线、直线优先、原生接触上限及细分 IK 补偿的候选；`live43`、`live44`、`live45` 已停止，均已回溯，仅保留诊断资格。

`live39` 的[33377 状态／834.4 s 历史前缀](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_39/prefix_audit_through_state33376.json)通过全部审计，但其后已多次回溯，整个运行只用于诊断。减速至 1 mm/s、逐段更新支撑目标并允许 30 s 无进展等待的公开参数重试，越过了先前停滞的第 211 段，随后在第 224／225 段再次出现角跟踪停滞；此结果不增加连续证明资格。已通过公开 abort/stop 请求停止，[收尾记录](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_39/diagnostic_stop_request.json)区分取消前七次回溯与后续取消行为。`live42` 保持原实测支撑目标，已排队减速和延长等待的短步备选，只在内置候选耗尽后生效。桌面运输备选已停止，两次尝试均未完成释放交接。

当前主 oracle 从两手分别抓持马蹄、抬升和折合开始，整体倾转 90° 后释放上件，左手以 295°／切线 roll 40° 抓取圆环。右手保持下件，左手按每段最多 4 mm 的实测路径推进；引导停滞时重新搜索，实际达到参考翻环检查点后再规划退出和目标区放置。规划采用原生机器人 IK 与任务接触分类，实际执行逐 tick 检查抓持、穿透及全部 19 对闭环连接；仅规划通过不会授予成功资格。

`live42` 后续已执行到 671.875 s，仍零回溯。该停点的[短段对照](../../../runs/test_results/horseshoe_oracle_20260930/actual42_short_stage_probe_01/result.json)发现截短采样过粗：4 mm 预算只保留 0.738 mm，低于 1 mm 进展门槛；2.5 mm 预算可保留通过相同检查的 1.25 mm。`ring_route.py` 新增可选 `refine_short_stage_prefix`，对截短区间再做六次细分，每个保留的整段仍须通过原有加密审计。相同实测输入的[修正复查](../../../runs/test_results/horseshoe_oracle_20260930/actual42_refined_short_stage_probe_01/result.json)保留约 1.338 mm，有效接触限值仍为 0.8 mm。`live43` 已从 home 启动 `stages:patient_reference_tube_exit_stages` 的冻结连续验证：翻环前沿用原配方，翻环后启用细分，速度最多 1 mm/s、无进展窗口 30 s、位置补偿上限 100 mm，保持固定支撑目标；[工厂合约检查](../../../runs/test_results/horseshoe_oracle_20260930/patient_exit_factory_contract_01/result.json)通过。该新运行尚无完整结果，不能把只读修正复查计作实际成功。

`live43` 已在 610.075 s 实际到达参考翻环检查点，机器人与五个物体状态同 `live42` [逐项一致](../../../runs/test_results/horseshoe_oracle_20260930/live43_pivot_reproduction.json)；[24404 状态前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_43/prefix_audit_through_state24403.json)全部通过、零回溯。修正参数已在翻环后启用，退出结果仍待验证。另在 `live39` 第 224 段分解出：位置误差约 0.123 mm，角误差约 2.337°；[记录命令的只读 FK 核对](../../../runs/test_results/horseshoe_oracle_20260930/actual39_angle_bias_probe_01/result.json)估计偏航补偿为 0.149995 rad，已抵达原每轴 0.15 rad 上限。`policy.py` 因此新增有界的 `rotation_bias_limit_rad`，默认值保持 0.15，新增角补偿日志；[控制与工厂合约检查](../../../runs/test_results/horseshoe_oracle_20260930/rotation_compensation_contract_01/result.json)通过。独立 `live44` 从 home 冻结验证 `stages:rotation_compensated_reference_exit_stages`，仅在翻环后使用每轴 0.3 rad 上限并包含截短修正。它不改变机器人增益、力矩、物理约束或验收规则，物理结果仍待验证。

`live44` 的 191.025 s [实际抓环状态](../../../runs/test_results/horseshoe_oracle_20260930/live44_grasp_reproduction.json)也逐项复现。`live39` 已结束，共七次跟踪失败回溯及一次公开取消回溯，没有原生成功。另对实际翻环停点的[参考出口复查](../../../runs/test_results/horseshoe_oracle_20260930/actual42_pivot_canonical_exit_probe_01/result.json)发现：对称姿态 3 的初始桥接仅约 0.902 mm，参考前缀可通过，后半程仍有 IK 阻挡，不能算完整路径。`live45` 因而从 home 验证 `stages:canonical_first_reference_exit_stages`，翻环后先尝试原参考后缀的实测短段，受阻时保留关节搜索候选；它也包含前述截短和角补偿修正。[真实停点的只读接入检查](../../../runs/test_results/horseshoe_oracle_20260930/canonical_first_exit_integration_01/result.json)正确选择参考第 3209 帧，首个 4 mm 短段通过 9 个加密样本；没有推进物理时间，也没有赋予执行成功资格。

`live39` 的向上候选多次被随动上件挡住，随后改为侧移约 121 mm 并转动 45° 的候选；在第 208 短段因圆环约 2.18 mm、支撑约 15.58 mm 的跟踪误差停滞，右手补偿达到 60 mm 上限。诊断分支排队尝试参考出口及 100 mm 补偿上限，接触阈值和 1.5 mm 跟踪门槛保持原值。独立 `live42` 从 home 验证 `stages:reference_tube_exit_stages`：沿用同一翻环配方，仅在实测翻环完成后的首次参考出口搜索启用目标附近采样及 995–997 搜索种子。参数和生成器关闭行为的[合约检查](../../../runs/test_results/horseshoe_oracle_20260930/reference_exit_factory_contract_01/result.json)通过；`live42` 已在 191.025 s 完成实际抓环，机器人及五个物体状态与已有抓环记录完全一致；477.325 s 的[首次重规划观测也逐项复现](../../../runs/test_results/horseshoe_oracle_20260930/live42_first_replan_reproduction.json)，参考出口物理结果仍待验收。另从 `live39` 的 682.7 s 停点得到[155 姿态／1217 样本的参考退出候选](../../../runs/test_results/horseshoe_oracle_20260930/actual39_second_upward_reference_tube_probe_01/result.json)，以及假设参考终点的[678 姿态／4349 样本放置候选](../../../runs/test_results/horseshoe_oracle_20260930/actual39_hypothetical_exit_placement_probe_01/result.json)；它们均未取得实际退出或放置资格。

慢速配方已有[实际退出进展对照](../../../runs/test_results/horseshoe_oracle_20260930/patient_exit_actual_progress_comparison.json)：`live43` 与 `live42` 的翻环实态及首条退出引导完全一致，却已越过后者在引导 index 24 的阻塞，完成 index 26→27 的物理短段。此时尚未触发截短细分，不能把改善单独归因于该算法；后续在 719.525 s／index 32 处因预测普通接触重新规划，仍零回溯。`live44` 也已在 610.075 s [逐项复现实际翻环状态](../../../runs/test_results/horseshoe_oracle_20260930/live44_pivot_reproduction.json)，角补偿仅从此后的退出段开始比较。两者均未分离或达到原生目标。

上述新增轨迹的独立复核已完成：`live43` [28782 状态／719.525 s](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_43/prefix_audit_through_state28781.json)、`live44` [24404 状态／610.075 s](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_44/prefix_audit_through_state24403.json)均从默认 home 连续覆盖、零回溯、机器人观测完整、无检查失败。两份都是前缀审计，尚不包含完整脱环或目标区成功。

`live42` 的连续实证已扩展至 [33781 状态／844.5 s](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_42/prefix_audit_through_state33780.json)：零回溯、home 与源码有效、全部观测覆盖、闭环保持且无失败。该停点的[六方向直移检查](../../../runs/test_results/horseshoe_oracle_20260930/actual42_later_direct_axes_probe_01/result.json)发现保持姿态向上 60.615 mm 可通过加密 IK／接触；[244 点静态闭环复核](../../../runs/test_results/horseshoe_oracle_20260930/actual42_later_direct_axes_probe_01/direct_z_topology.json)也通过。现有[全方向关节规划](../../../runs/test_results/horseshoe_oracle_20260930/actual42_later_allaxes_route_01/result.json)找到同一向上端点的 27 姿态／130 样本候选，已作为公开参数备选排队，仅在内置候选耗尽后从实态重新规划。

新增默认关闭的 `direct_axis_exit_first`，先按距离检查六轴保持姿态的直移，再回退原关节搜索；每条路径保留加密有序 IK、接触及静态被动闭环检查。该停点的[接入验证](../../../runs/test_results/horseshoe_oracle_20260930/direct_first_exit_integration_01/result.json)通过完整直移和首个 4 mm 短段，工厂仅修改翻环后选项，保持原生物理与验收条件。`live46` 使用 `stages:direct_first_reference_exit_stages` 从 home 独立冻结验证；直移候选及放置均尚未取得物理成功资格。

角补偿方案 `live44` 的[42703 状态／1067.55 s 前缀](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_44/prefix_audit_through_state42702.json)已通过全部审计，仍零回溯；运行中右手 100 mm 位置补偿和每轴 0.3 rad 角补偿也曾饱和，不能仅靠此参数保证退出。参考后缀方案 `live45` 的实际翻环起点同样逐项复现，已经真实执行参考短段，其[36366 状态／909.125 s 前缀](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_45/prefix_audit_through_state36365.json)全部通过，零回溯、观测覆盖完整，普通接触最大 0.313 mm、合格夹指最大 0.326 mm；尚无完整退出结果。

慢速 `live43` 后续在第 205 段达到 50 s 时间上限，于 925.05 s 结束失败段并首次回溯；随后公开停止，最终另有两次取消回溯，见[停止记录](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_43/diagnostic_stop_request.json)已提交。失败检查为 `stage_time_budget`，不是接触或闭环守卫失败。此前[36476 状态／911.875 s 历史前缀](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_43/prefix_audit_through_state36475.json)检查全部通过，但审计结束时工作流已有一次回溯，整个运行不能取得完整证明资格。`live46` 则已于 191.025 s [逐项复现抓环实态](../../../runs/test_results/horseshoe_oracle_20260930/live46_grasp_reproduction.json)，继续零回溯翻环。

向上 60.615 mm 候选的[固定全部部件复查](../../../runs/test_results/horseshoe_oracle_20260930/actual42_later_strict_direct_axes_probe_01/result.json)在最初约 0.748 mm 处出现 0.613 mm 预测穿透；此前通过的路线依赖自由部件接触响应，不能称为固定障碍下的无碰撞出口。`live45` 的参考后缀随后在 830.625 s／index 3246 处被夹指与上件普通接触阻塞，开始原有关节搜索后备。

该实态的[规划接触余量对照](../../../runs/test_results/horseshoe_oracle_20260930/actual45_canonical_contact_margin_probe_01/result.json)中，0.8／0.9／1.0 mm 上限分别保留 0.956／1.080／1.203 mm 短段；后两者超过 1 mm 进展门槛。另修复 `contact_limit_m` 原先只传入执行守卫、未传入 `ContactHorseshoeIK` 的不一致，默认仍为 0.8 mm；[真实 Stage 接入检查](../../../runs/test_results/horseshoe_oracle_20260930/native_limit_exit_integration_01/result.json)验证两端一致，超出原生 1 mm 拒绝、合格夹指仍为原生 2 mm，未推进物理。`live47` 从 home 验证 `stages:native_limit_reference_exit_stages`：翻环后采用 1 mm 原生普通接触上限，优先参考后缀，后备先检查直移再做关节搜索。没有修改 Task、assist、物理或原生成功条件；完整结果尚待验证。

`live46` 已[逐项复现 610.075 s 翻环实态](../../../runs/test_results/horseshoe_oracle_20260930/live46_pivot_reproduction.json)，随后直接选中[向上 133.813 mm 的候选](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_46/planning/withdraw_one_151/joint_withdrawal_plan.json)，358 个有序样本通过；较短的侧移因静态闭环连接改变被拒绝。已经开始真实执行；最新[32662 状态／816.525 s 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_46/prefix_audit_through_state32661.json)全部通过、零回溯，源码与 home 有效、机器人观测完整、无抓持丢失且 19 对闭环保持。普通接触最大 0.313 mm、合格夹指最大 0.276 mm；完整退出仍待验证。

`live45` 后续于 1027.075 s 首次违反旧 oracle 的 0.8 mm 阶段余量并回溯，已提交公开停止。[原始失败 tick 复核](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_45/first_contact_failure_diagnosis.json)确认左手单指与上马蹄的普通接触为 0.810953 mm，低于原生 1 mm，Task 当时未终止。这是执行余量造成的失败，不能套用合格夹指的 2 mm，也不能追溯消除已发生的回溯。`live47` 正从 home 独立验证统一后的 1 mm 规划／阶段上限，已逐项复现 191.025 s 的抓环实态和 [477.325 s 的首次重规划实态](../../../runs/test_results/horseshoe_oracle_20260930/live47_first_replan_reproduction.json)。`live45` 已停止，最终一次自然失败回溯，取消操作未新增回溯。

`live46` 在 790.9 s 的[目标区端点预检](../../../runs/test_results/horseshoe_oracle_20260930/actual46_goal_endpoint_preview_01/result.json)中，45 个候选有 5 个同时通过全环区域包含、原生 IK 和接触检查。它使用当时抓持偏移及固定的剩余组件位姿，仅说明候选端点可达，不包含脱环、运输路径或真实放置。

`live44` 后续在 1558.175 s／state 62327 首次失败并回溯：退出第 338 段的控制器 IK 报不可达，位置残差约 80.16 mm、姿态残差约 0.139 rad；该段 35 个已完成 tick 没有守卫违规，Task 当时仍 ongoing。已[请求公开停止](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_44/diagnostic_stop_request.json)，历史 1511.825 s 前缀通过不能授予整段资格。`live47` 已逐项复现 610.075 s 翻环实态，并通过[24860 状态／621.475 s 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_47/prefix_audit_through_state24859.json)，继续零回溯执行原生 1 mm 接触上限的参考退出。

`live44` 已停止，最终一次自然失败回溯、两次取消回溯。[失败点只读复查](../../../runs/test_results/horseshoe_oracle_20260930/actual44_support_seed_matrix_01/result.json)复现固定右手名义目标的 IK 错误；原支撑初值虽能求解，但相对上一命令需要约 0.27 rad 变化。随后[细分补偿检查](../../../runs/test_results/horseshoe_oracle_20260930/actual44_support_seed_refinement_01/result.json)发现 99.5% 补偿能通过原生容差，命令变化仅 0.0009504 rad。新增默认关闭的 `refine_ik_compensation`，在原减半策略之前尝试更细比例；[真实控制器接入验证](../../../runs/test_results/horseshoe_oracle_20260930/refined_ik_controller_integration_01/result.json)复现旧失败并验证新分支通过，未推进物理或修改 IK 容差。`live48` 从 home 冻结验证 `stages:refined_native_limit_reference_exit_stages`，仅在参考翻环之后开启新选项，完整结果仍待执行。

`live47` 已零回溯执行到使用参考 index 3254 的后续短段，越过 `live45` 此前 index 3246 附近的余量阻塞，见[实际进展与原始观测](../../../runs/test_results/horseshoe_oracle_20260930/native_limit_canonical_actual_progress.json)。两者翻环检查点逐项相同，但后续被动响应与重规划不同，不能将这一比较视为同一实态的因果试验。仍须完成全程退出与目标区成功。

| 检查 | 实际结果与范围 |
| --- | --- |
| 当前资产的物体路径 | easy / medium / hard 的 3393 / 3385 / 3364 段参考运动全部通过自适应连续表面间隙检查，下界分别为 0.050317 / 0.050259 / 0.050100 mm。起点是模板装配姿态，包含初态实体占据检查；尚不覆盖桌面静置初态前缀、实验室障碍和自由链环动力学。 |
| easy 翻转与折合 IK | 已找到保持物体相对路线的双臂联合 IK；784 个加密样本通过本体、双臂、桌面和拼图几何检查。仍是运动学候选。 |
| easy 水平折合与关节余量 | 两手抓外弧、以 18 mm 单指开度接近，避免初始目标环进入夹爪。翻转后将马蹄放平，再允许至多 0.07 rad 倾角，为腕部俯仰留出 0.10 rad 余量；909 个密集原生 IK / 碰撞样本通过，冻结源码重现轨迹最大关节差约 2.6e−15 rad。其他关节的余量不同，见计划中的逐关节数组。 |
| easy 反向路线 | 对参考运动作 y 反射并交换上下链名称后，3393 段物体运动重新通过连续间隙检查；另一组抓点通过 784 个加密 IK 样本。物理执行尚未通过。 |
| easy home → 接近 → 抓取 → 抬升 | 一次连续 900 tick 的实际执行通过独立复核：双指接触触发 `contact_weld_v1`，两件抬高 18 cm，链环连接保持、没有抓持丢失，最大任务接触穿透 0.270 mm。不是完整解题成功。 |
| easy 完整物理折合 | `support_cone_01` 从默认 home 连续抓取、抬升、翻转并走完 3630 帧折合候选，115.925 s 进入 `folded_settle`。完整 7038 tick 独立复核通过历史连续性、双指抓取、链环连接、无抓持丢失，最大任务接触穿透 0.284 mm。交接前再次微调因右腕限位而超时，整段任务尚未完成。 |
| easy 支撑交接与抓环 | `extract_cone_02` 从 home 连续完成折合、释放上件、由下件接触支撑、左手撤离与重新抓环。5499 tick 独立复核通过，逐 tick 检查的 19 对跨物体闭环连接数全部保持，最大任务接触穿透 0.298 mm，无机器人自碰、碰桌或抓持丢失。两手分别只绑定目标环、下件；上件仍是自由物体。 |
| easy 接触取环前缀 | `staged_solve_02` 从 home 连续完成 14 个取环短段，圆环上提时自由上件随接触移动。11984 tick 的接触、抓持和全部闭环连接审计通过，最大任务接触穿透仍为 0.298 mm；尚未完全分离。下一段入口因约 0.04 µrad 的观测关节限位残差被严格规划检查拒绝。后续只读规划种子允许投影不超过 1 µrad 的数值残差，原始观测和物理状态不改写；审计另报告实际关节残差峰值并拒绝超过该界限的运行。 |
| easy 完整取环候选 | `joint_withdrawal_probe_02` 从真实抓环记录构造 106 个位姿的关节空间候选，867 个加密原生 IK / 碰撞检查通过；对当前上件环眼和链环加入连接数筛选。仍允许圆环推动自由部件，因此必须通过完整动力学验证。 |
| 当前衔接缺口 | 参考翻环检查点已实际到达；翻环后的退出及固定区域放置尚待真实连续执行。允许被动物体响应的接触规划仍必须由物理守卫与独立审计复核，尚无完整原生成功记录。 |

物体证据：[easy](../../../runs/test_results/horseshoe_oracle_20260930/object_easy_frozen/object_certificate.json) · [medium](../../../runs/test_results/horseshoe_oracle_20260930/object_medium_frozen/object_certificate.json) · [hard](../../../runs/test_results/horseshoe_oracle_20260930/object_hard_frozen/object_certificate.json)。
机器人证据：[加密 IK](../../../runs/test_results/horseshoe_oracle_20260930/fold_refined_01/dense_ik.json) · [抬升独立复核](../../../runs/test_results/horseshoe_oracle_20260930/pickup_04/independent_audit.json) · [首轮折合中断说明](../../../runs/test_results/horseshoe_oracle_20260930/fold_01/interruption.json)。

正式 CLI 重现结果：[正向规划](../../../runs/test_results/horseshoe_oracle_20260930/oracle_plan_frozen/oracle_plan.json) · [反向物体证书](../../../runs/test_results/horseshoe_oracle_20260930/mirrored_geometry/object_certificate.json) · [反向规划](../../../runs/test_results/horseshoe_oracle_20260930/mirrored_ik/oracle_plan.json)。延长跟踪窗口的 `fold_02` 与小角度重新悬挂的 `fold_03` 均因跟踪超时结束，没有触发资源上限；不能记作通过。重新悬挂、支撑交接接口目前仍属实验诊断。

当前候选：[带关节余量的冻结规划](../../../runs/test_results/horseshoe_oracle_20260930/reserved_oracle_frozen/oracle_plan.json) · [首次完整物理折合记录](../../../runs/test_results/horseshoe_oracle_20260930/support_cone_01/run_report.json) · [独立复核](../../../runs/test_results/horseshoe_oracle_20260930/support_cone_01/independent_audit.json)。该方案只约束双臂持有的马蹄，链与目标环始终服从真实动力学。支撑交接只释放左手并让上件依靠接触落在下件上，不给右手添加第二个焊接约束。在线抓环与取环规划在 `manipulation.py` / `ring_route.py`；取环的初始 3 mm 接触脱离邻域与离散碰撞采样不是连续正间隙证明，须由物理运行单独验收。

实际抓环的证据：[执行报告](../../../runs/test_results/horseshoe_oracle_20260930/extract_cone_02/run_report.json) · [独立复核](../../../runs/test_results/horseshoe_oracle_20260930/extract_cone_02/independent_audit.json)。抓环规划围绕线材切线旋转夹爪方向，以避开支撑手。`ring_route.py` 的接触规划模式将已经释放的上件与两个链环列为可受圆环推动的自由物体；它不改变碰撞、重力、焊接或原生失败判据，也不将该候选写成无碰撞证明。`placement.py` 提供固定区域的后续候选，尚未物理验收。`--withdrawal-mode staged` 每次最多执行 12 mm 已检查的引导段，再按真实被动部件姿态重规划；每段仍检查双臂、桌面和持有的下件，不改变 Genesis 的接触约束。首次 54 样本检查通过仅属于短段运动学候选。

接触前缀的[独立审计](../../../runs/test_results/horseshoe_oracle_20260930/staged_solve_02/independent_audit.json)与[实际物体姿态示意](../../../runs/test_results/horseshoe_oracle_20260930/staged_solve_02/geometry_snapshots/contact_progress.png)已保存，示意图不属于相机 RGB 或完整成功视频。`--withdrawal-mode joint-staged` 将[完整关节空间候选](../../../runs/test_results/horseshoe_oracle_20260930/joint_withdrawal_probe_02/free_ring_transport_plan.json)用作短段引导；放置端另有 2074 样本的绕行候选，均等待实际执行。`joint_staged_solve_01` 在折合中触发 CPU 99.4% 的资源停止，内存当时为 21.4%；[中断记录](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_01/interruption.json)明确保留未完成状态，不拼接续跑。

`joint_staged_solve_02` 在 16290 tick / 407.25 s 被旧版 CPU 资源守护中断（CPU 99.7%，内存 24.5%），未完成取环；保留[中断说明](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_02/interruption.json)。实测右手持有的下件随接触载荷偏移约 2 cm，导致随下件更新的引导路径反复移动。当前候选在取环中同时反馈保持右手支撑物，并在短段末反馈停稳；`joint_staged_solve_03` 在首段接触脱离中因 0.7 mm 跟踪门槛超时，6064 tick 的[独立审计](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_03/independent_audit.json)仍通过全部连接、接触和抓持检查。当前 `joint_staged_solve_04` 使用 1.5 mm 取环跟踪门槛和反向右手抓持，从 home 重新执行；审计门槛不变。另有[反向右手抓持的 909 点 IK 检查](../../../runs/test_results/horseshoe_oracle_20260930/opposite_right_grasp_probe_01/audit.json)通过，右腕旋转关节最小余量约 1.36 rad，尚未物理验证。

`joint_staged_solve_04` 的反向抓持完成了折合与抓环，并推进到第 11 个取环短段；在 tick 8688 圆环与下链环穿透达到 1.052 mm，触发原生失败。[完整审计](../../../runs/test_results/horseshoe_oracle_20260930/joint_staged_solve_04/independent_audit.json)保留了该失败，19 对闭环连接仍保持。后续[链环避碰候选](../../../runs/test_results/horseshoe_oracle_20260930/joint_strict_chains_probe_01/free_ring_transport_plan.json)只允许圆环推动自由上件，两个链环均作为避碰障碍。

[`stages.py`](../../../topogym/planning/horseshoe_ring/stages.py) 已接入现有 `run_solvability_workflow.py`。当前 `live_diagnostic_01` 将 home 到抓环、取环、放环、移动剩余组件、验证目标拆成独立阶段；失败诊断可在同一活环境中通过公开 rewind 重试，记录分支与候选。初始取环参数为 4 mm 短段、2 mm/s、1.5 mm 跟踪门槛及 0.8 mm 提前接触停止线，原生 1 mm 失败标准不改。发生回溯的记录不能取得完整证明资格；选定方案必须再次从 home 连续执行。`audit.py --prefix` 仅审计调用时已写入的完整 tick 前缀，始终不授予最终资格。

逐短段版本 `live_diagnostic_02` 进一步把每个最多 4 mm 的取环动作拆成一个检查点，并在成功段之间保留控制补偿、固定支撑目标和引导索引。连续三个短段索引不推进时，从最新实测姿态重新搜索；段内失败仅回溯该短段。上一版 `live_diagnostic_01` 因自由链环移动后遮挡旧引导而停止诊断，三次公开回溯均保留；其记录不具备完整证明资格。从停滞实测状态出发的[172 位姿重新规划](../../../runs/test_results/horseshoe_oracle_20260930/joint_replan_probe_01/free_ring_transport_plan.json)已通过只读检查，仍需动力学验证。首次运行通过 `TOPOGYM_HORSESHOE_ORACLE_INPUTS` 指定绑定五项输入路径及哈希的 JSON；后续正式重跑可使用 workflow 生成的 `qualification/selection.json`。

`live_diagnostic_02` 连续完成 34 个取环短段后仍未分离。进一步检查发现，局部脱离 LP 最大化间隙时会选择数毫米平移和约 0.03–0.04 rad 转动，使后续 4 mm 预算反复用于返回引导。当前 `ring_route.py` 从小到大检查该扭量的分数，只执行达到 60 µm 间隙的最小已检查分数；若无法一步达到，则保留通过检查且间隙改善最大的候选。在 tick 11832 的实测状态上，[局部只读检查](../../../runs/test_results/horseshoe_oracle_20260930/minimal_escape_probe_01/contact_escape_plan.json)将材料位移减至约 0.076 mm；旧引导仍被链环阻挡，未通过后续推进检查。`live_diagnostic_03` 使用修正后的冻结源码从 home 重新执行；尚不代表完整成功。旧诊断的公开停止与回溯记录保留，不拼接到新执行。

最小脱离端点在上述停滞状态上的完整关节搜索于 600 s 超时；保持原搜索的大间隙引导、仅缩小逐段实际脱离时，[4 mm 衔接段的 9 个加密检查](../../../runs/test_results/horseshoe_oracle_20260930/minimal_escape_newguide_probe_01/ring_stage_000.json)通过。因此当前 `joint_route.py` 保留较大的已检查接触脱离前缀以供全局搜索，逐段 `ring_route.py` 使用最小脱离，再按剩余预算跟踪持久引导。`live_diagnostic_04` 从 home 验证这一组合；`live_diagnostic_03` 的冻结源码仍是全局与局部都最小脱离的版本，两个运行不可混用。

`live_diagnostic_03` 的 [8266 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_03/prefix_audit.json)通过全部 19 对闭环连接与抓持检查，最大任务接触穿透 0.301 mm；仍未取出圆环。第 25 个短段的旧引导被链条阻挡，动作执行前拒绝后重新找到 174 位姿路线，保持零回溯。旧适配器会永久继承重试的 2 mm / 1 mm/s 设置，剩余路线接近 300 段上限。当前适配器在三个保守短段成功后重新尝试 4 mm / 2 mm/s，默认预算 600 段并实际执行 `maximum_stages` 限制；每个候选仍经过原有规划和物理检查。`live_diagnostic_05` 从 home 验证这一修改，尚无完整成功结论。

`live_diagnostic_03` / `04` 后续出现跟踪停滞，重新搜索的剩余路线超过各自冻结的 300 段预算，已通过公开接口停止，最终各记录 5 次回溯（含操作方停止）；不能作为完整证明。第 51 段入口的圆环离下马蹄约 33 mm、离上马蹄仅约 0.006 mm。固定所有剩余部件的两次原生关节搜索各耗尽 600 s；[纯物体搜索](../../../runs/test_results/horseshoe_oracle_20260930/measured_object_stage50_probe_01/object_route.json)在 10000 次扩展内也未连接，均不是无解证明。当前关节搜索会保留长扩展中已检查通过的短前缀，且接触脱离与允许推动哪些部件已拆为独立选项。

更早的实测偏差发生在交接前：tick 4584 / 114.6 s 的马蹄相对旋转误差仅 0.0086 rad，但自由圆环距物体参考位置已有 0.1044 m 偏差。[折合后共同倾斜检查](../../../runs/test_results/horseshoe_oracle_20260930/folded_tilt_probe_01/results.json)的 15° / 30° / 45° 候选通过，30° 为 62 个原生 IK / 碰撞样本；60° 以上未通过可达检查。`live_diagnostic_06` 使用 `stages:gravity_stages` 从 home 验证：两手分别持有马蹄时倾斜、保持、恢复，再按实测圆环沿出口方向的位置决定是否交接。实际前进到参考位置前 25 mm 内，或出现至少 5 mm 的整体分隔平面，才接受该局部阶段。圆环和链条始终自由，尚无完整成功结论。

实现位于 [`topogym/planning/horseshoe_ring/`](../../../topogym/planning/horseshoe_ring/)；当前入口为 [`scripts/oracle_runners/run_horseshoe_policy.py`](../../../scripts/oracle_runners/run_horseshoe_policy.py)。`--part geometry --reference .../body_poses.json` 复核物体路径；`--part plan --reference .../body_poses.json` 搜索完整折合所需抓点和联合 IK；`--part pickup` / `--part fold` 执行诊断。运行会冻结源码和输入，每秒记录资源用量；按最新资源规则，仅内存达到 90% 时停止本次工作进程，CPU 只监控记录。无 RGB 的 CPU 运行使用 25 ms World tick / 40 子步、JOINT_ABS，IK 只读查询后输出普通关节动作。局部通过不计入 `solvability_proof/`。

`--part plan --retarget-plan .../horizontal_oracle_frozen/fold_plan.json --grasps .../grasp_selection.json --reference .../body_poses.json` 复现上述余量规划；`--part support` / `--part grasp_ring` / `--part extract` 分别追加支撑交接、抓环和取环阶段，均须传入 `--grasps`、`--reference`、`--fold-plan`、`--support-plan`。这些阶段仍按诊断结果报告，尚无固定目标区的完整成功记录。

`live_diagnostic_06` 的 15° / 30° / 45° 物理倾斜均未留下稳定的沿出口位移：30° / 45° 保持时约前移 20 mm，恢复水平后又回到原位置附近。60° 加前移 40 mm 的候选继续诊断。实测与参考的[几何对照](../../../runs/test_results/horseshoe_oracle_20260930/folded_comparison/comparison.png)显示，自由圆环仍悬在链环一侧，不能由马蹄相对姿态接近参考推断圆环已走完同一路线。图像仅为几何重建，不是相机 RGB。

进一步的[工作区检查](../../../runs/test_results/horseshoe_oracle_20260930/folded_tilt_workspace_probe_02/results.json)找到先前移 100 mm、下移 40 mm 再倾斜 90° 的原生 IK / 机器人碰撞候选。`live_diagnostic_07` 使用独立冻结源码，从 home 验证该路线；每 0.5° / 1 mm 规划样本执行 0.1 s 并反馈保持两个马蹄，链环和圆环仍自由。尚无完整成功结论。实测折叠姿态的纯物体搜索同时进行；可选的缩短扩展仅保留重新通过连续间隙检查的边，不放宽几何门槛。

最新诊断：60° 与 90° 保持时的圆环相对位置仍停在同一卡点附近。`live_diagnostic_07` 的 [4992 tick 连续前缀](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_07/prefix_audit.json)通过全部 19 对闭环连接、双指抓取与关节限位检查，最大接触穿透 0.27568 mm；尚未取环。`live_diagnostic_08` 测试 60° 倾斜后侧转 −60°。进一步的[朝向检查](../../../runs/test_results/horseshoe_oracle_20260930/folded_yaw_probe_01/results.json)找到整体绕竖直轴转 30° / 60° 时的 120° 倾斜路线，`live_diagnostic_09` 从 home 验证。两种路线均只约束双手分别持有的马蹄，未修改自由圆环、链环或原生判据。

固定实测折叠姿态中所有剩余部件的两轮纯物体搜索分别耗尽 10000 次扩展和 600 s 预算，未找到出口；第二轮允许缩短扩展，但每条接受边仍经过同一连续间隙检查。结果仅表示有限搜索失败，不能推广成任务无解或机器人不可达。

交接误差的进一步定位：左手放开上马蹄并抓环后，上件相对下件比参考低约 8.98 mm，转角误差约 0.0985 rad；交接前则只有约 1.06 mm 平移和 0.0086 rad 转角误差。405 条绕链连接处转环的物体候选最多推进 0.75° 就碰到固定上件，尚无几何出口。`live_diagnostic_10` 的 `stages:suspended_stages` 因而保留已经检查的 120° 倾斜和 30° 整体转向，在该姿态释放上件，让它沿原链环悬挂；待上件与圆环的实测速度持续低于局部门槛后，重新规划抓环。这里验收的是交接朝向，不要求或宣称圆环已经位移、分离或完成任务。每手最多一个辅助绑定、原生接触与最终成功判据均不变，物理结果仍待验证。

`live_diagnostic_10` 已实际到达 120° 倾斜并释放上件；[6521 tick 的连续前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_10/prefix_audit.json)通过全部连接、接触、抓持与关节检查，最大接触穿透仍为 0.27568 mm。左手撤离的旧检查在起点拒绝了刚释放上件与夹爪的已有接触。[新的只读撤离候选](../../../runs/test_results/horseshoe_oracle_20260930/suspended_retreat_probe_01/free_hand_plan.json)沿世界 +X 退 30 mm，初始约 14.95 µm 穿透不增加，并在终点恢复完整避碰要求；只允许脱离这一已有接触，不能重新接触其他物体。`live_diagnostic_11` 使用新冻结源码从 home 验证，尚无完整任务成功。

另对 5 s 静置后的真实出生姿态补查直接取环：抓环 IK 已找到，但竖直抬升的前 10 mm 会穿过固定链环，因此端点空闲不构成有效通路。包含桌面的纯物体接触脱离搜索停在约 18.31 µm 间隙，未达到检查门槛；没有将直接抬起写成可解证明。

`live_diagnostic_11` 到 173.125 s 的 6926 tick 连续前缀通过独立审计，仍未抓到圆环。松手、撤 30 mm、静置之后的实测姿态缩小了两手间隙，原生 FCL 抓环规划起点拒绝接近。直接沿同一方向撤 40–80 mm 也会碰到下马蹄；新的[撤手候选](../../../runs/test_results/horseshoe_oracle_20260930/suspended_retreat_probe_04/free_hand_plan.json)先完成原 30 mm 接触脱离，再使用固定另一只手的关节空间绕行，1103 次查询通过，关节边采样不超过 0.015 rad。`live_diagnostic_13` 从默认 home 验证这一新候选；采样规划不代替运动中自由物体的真实响应。

`live_diagnostic_12` 补做出生姿态直接抓环的真实接触抬升。抬升到 80 mm 仍未将圆环与完整余件分开，策略按预期报错退出；[3790 tick 审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_12/prefix_audit.json)保留全部 19 对闭环连接，最大接触穿透 0.26209 mm，无完整目标成功。有限失败不能推断任务无解。

撤手的进一步筛选拒绝了先前绕行终点：它虽对释放瞬间的物体无碰撞，却与 `live11` 静置后的上件相交。因此 `live13` 在前缀阶段通过公开 abort/stop 停止，记录保留。新[撤手检查](../../../runs/test_results/horseshoe_oracle_20260930/suspended_retreat_probe_05/free_hand_plan.json)要求末端整只左臂与五个物体及右臂至少有 50 mm 间隙，找到 245.33 mm 的候选；[在此前静置几何中的假设抓环检查](../../../runs/test_results/horseshoe_oracle_20260930/retreat_to_grasp_probe_02/ring_grasp_plan.json)也通过。该假设状态只用于规划，不是物理记录或执行拼接。`live14` 从 home 验证 120° 交接。

[实测相对姿态](../../../runs/test_results/horseshoe_oracle_20260930/suspended_relative_diagnosis.json)显示，120° 交接前两马蹄的相对角误差约 0.592°，静置后增至 19.707°，且相对位置明显变化。`live15` 的 `stages:vertical_stages` 因而验证 90° 竖直交接，假设重力可能减小张开角；尚未证实。静态纯物体和原生 IK 的搜索同时增加六个世界坐标方向的整体分离终点，仍执行原有碰撞与连接检查；未放宽任务判据。

`live14` 已实际完成安全撤手、静置和双指抓环。[7779 tick 独立审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_14/prefix_audit_through_grasp.json)到 194.45 s 保持全部 19 对闭环连接，无抓持丢失或物理检查失败，最大接触穿透 0.275681 mm。圆环相对下马蹄的位置由早先悬挂观测的约 −45 mm 沿出口方向移到约 −17 mm，尚未分离；后续尝试见下文。先前 `live11` 静态物体搜索和假设抓取下的 IK 搜索失败不直接适用于该新实测状态。

`live16` 的 90° 竖直路线加入了关节空间绕行接近，实际抓环成功；[7979 tick 抓环审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_16/prefix_audit_through_grasp.json)保持 19 对闭环连接，最大穿透 0.321537 mm，无检查失败，尚未取环。先前 `live15` 静置后的两马蹄相对角误差约 0.6125°，但相对位置仍偏离折合参考约 94.65 mm；不能将平行视为已经靠拢。

[双臂配合候选](../../../runs/test_results/horseshoe_oracle_20260930/move_lower_integrated_probe_01/lower_reposition_plan.json)保持圆环不动，右手将下马蹄移向上件。起点先提出 0.1 mm 接触脱离；随后约 95 mm 的运动对实测上件、圆环和桌面具有 53.3744 µm 连续表面间隙下界，并通过 200 个原生 IK / 机器人碰撞样本。接触前缀与两条被动链的运动尚未证明。`alignment.py` / `stages:reposition_stages` 已接入，`live17` 从 home 做真实验证；逐 tick 同时检查全部 19 对闭环连接。

`live14` 完成 8 个取环小阶段后，在 219.9 s 被机器人／上件间隙检查阻止。[实测 FCL 检查](../../../runs/test_results/horseshoe_oracle_20260930/live14_hand_gap_probe_01/result.json)给出左指与上件的正间隙 0.32930 mm、无穿透，低于原规划余量 0.5 mm。[下一段 4 mm 的复查](../../../runs/test_results/horseshoe_oracle_20260930/live14_narrow_stage_probe_01/ring_stage_008.json)在 0.1 mm 正规划余量下通过。`live18` 使用 `stages:close_clearance_stages` 从 home 验证；源路径作为带 SHA-256 的 `withdrawal_guide` 输入，只提供以所持下件为坐标系的引导，每段仍重查实测物体、IK 和碰撞。原生接触阈值、自碰撞、桌面及闭环检查未放宽，旧轨迹没有获得成功或连续执行信用。

`live16` 随后连续完成 32 个取环小阶段；[11699 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_16/prefix_audit.json)到 292.45 s 保持全部 19 对闭环连接，无抓持丢失、关节越限或接触检查失败。第 33 段在 312.85 s 因右手支撑误差约 1.957 mm 超过 1.5 mm 推进门限而超时，诊断流程发生回溯，不能算完整连续证明。`live19` 从 home 使用该规划路径作为哈希绑定引导，单独设右手推进门限 3 mm，环仍为 1.5 mm；碰撞、物理穿透与拓扑验收标准不变，尚待执行验证。

`live17` 的下件移动在约 69.5% 处持续停滞，右手误差约 2 mm，尚未达到候选终点。已通过公开 abort/stop 停止该试验并保留证据；正对实测中间状态做退环规划检查，不把预期上件位置当作真实位置。

`live17` 的 [11753 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_17/prefix_audit.json)覆盖到 293.8 s，未发现拓扑、接触、抓持或关节失败。中间实测姿态的[退环候选](../../../runs/test_results/horseshoe_oracle_20260930/repositioned_exit_probe_01/joint_withdrawal_plan.json)为约 52.19 mm 平移，通过 110 个 IK／碰撞样本；但[完整静态物体复查](../../../runs/test_results/horseshoe_oracle_20260930/repositioned_exit_object_check_01/result.json)明确拒绝前约 9.5 mm，因此它仍需要被动接触执行，不能算无碰撞物体证书。`live20` 使用 `stages:partial_reposition_stages` 从 home 执行下件自由边的 65%，随后重测并重规划退环。

`live18` 已通过第 9 个取环小阶段，但下一段再次被夹爪／上件间隙阻止，现已公开 stop。[8894 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_18/prefix_audit.json)未发现检查失败，19 对连接保持，最大穿透 0.275681 mm；没有完整取环或目标成功。

`live20` 实际完成了 65% 下件移动，竖直位移约 −61.71 mm，末端下件误差 1.201 mm、圆环误差 0.535 mm；随后侧向退环把上件一起带走，在第 16 个阶段因支撑误差超过 3 mm 超时。`live19` 也在第 34 个阶段再次超时，两者均发生实际回溯，不能算完整连续证明，已请求公开 abort/stop。

关节空间退环的目标集合补入了参考路径的最终环姿态及椭圆半转对称姿态，并增加 `exit_goal_mode=reference`，可只沿参考退出方向搜索。[实测下件移动后检查](../../../runs/test_results/horseshoe_oracle_20260930/reference_exit_probe_01/endpoints.json)找到两个有效终态，[候选路径](../../../runs/test_results/horseshoe_oracle_20260930/reference_exit_probe_01/joint_withdrawal_guide.json)含 128 个姿态、通过 621 个密集样本；主要向下移动并转平环，终点的完整环几何距桌面约 46.86 mm。被动上件／链条的实际响应仍未验证。`live21` 使用 `stages:reference_reposition_stages` 从 home 重做完整流程，哈希绑定引导明确标为下件移动后使用，每段仍重查实测状态；没有直接复用机器人或物体状态。

[新目标集合的集成调用](../../../runs/test_results/horseshoe_oracle_20260930/reference_exit_integrated_probe_01/joint_withdrawal_plan.json)通过 625 个密集样本。`live22` 的 `stages:measured_support_reference_stages` 增加 `rebase_support_each_stage=True`：每个取环短段以实测下件姿态更新右手支撑目标，与该段规划冻结的几何一致；保留抓持标定与控制补偿，只通过普通机器人动作执行。它与 `live21` 的固定支撑作对照，尚无成功结论，原有物理和目标验收标准不变。

`live21` 的 [11187 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_21/prefix_audit.json)无失败，但固定支撑在取环第 25 个阶段超时。`live22` 越过了这一位置，其 [12626 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_22/prefix_audit.json)同样无失败；随后在第 31 个阶段的静置中，环误差约 0.03 mm、右手支撑误差约 3.1 mm，触发控制超时与回溯。二者均非完整证明。`live23` 的 `stages:ring_tracking_reference_stages` 保留逐段支撑重测和右手笛卡尔反馈，设置 `gate_support_tracking=False`，退环进度只由左手环跟踪门限决定，右手误差仍记录；其固定姿态不是任务成功条件。原生接触、全部闭环、抓持、关节和最终放置规则不变，仍须真实执行和独立审计。

`live23` 连续越过了上述两处超时，其 [13285 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_23/prefix_audit_through_stage33.json)通过；向下目标不可达后，通过公开 `control/next.json` 切换为 `all_axes` 重新规划，没有回溯。但侧向阶段测得环前进约 56 mm、两个马蹄也前进约 51–53 mm，说明逐段重设支撑目标会累积整体漂移，不能把这些短阶段的完成计作退环成功。`live24` 使用 `stages:fixed_support_ring_tracking_stages` 从默认 home 重新执行：保持初次退环时的右手支撑目标，`rebase_support_each_stage=False`、`gate_support_tracking=False`，其余几何、IK、物理和最终目标条件不变；结果待验证。同时从 `live23` 第 59 段入口的实测姿态进行固定其余全部物体的纯几何搜索，单独记录其接触释放和 IK 边界。

`live23` 停止前的[扩展前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_23/prefix_audit.json)覆盖 18169 tick / 454.2 s，仍无失败；主动中止后的回溯不属于该审计范围。[固定全部其余物体的搜索](../../../runs/test_results/horseshoe_oracle_20260930/live23_stage59_fixed_object_probe_01/result.json)在约 65.10 μm 的局部释放端点之后耗尽 300 s，未找到完整路线，不能据此判定无解。`live25` 是另一个默认 home 对照：`stages:full_reposition_fixed_support_stages` 执行完整让位边，只把右手的推进门限从 1.5 mm 设为 3 mm，圆环门限仍为 1.5 mm，最后两件的实测到位检查仍为 3 mm；随后固定支撑目标退环。该运行不载入仅适用于 65% 让位后的参考引导，完整结果待验证。

`live25` 实际越过原停滞位置，但在 73.12% 再次停滞，主要误差为横向位置约 5 mm，姿态误差很小，尚未完成让位。当前 `follow_bodies` 的位置积分补偿上限为 30 mm；右臂腰关节增益和命令差显示力矩上限仍有余量，因此 `live26` 的 `stages:compensated_full_reposition_stages` 测试 50 mm 补偿上限，并恢复完整让位时的 1.5 mm 推进门限。新增日志记录各手位置补偿量；默认行为仍为 30 mm，机器人增益、力矩限制、接触/拓扑/关节检查和最终目标均不改动。控制补偿假设仍需实际执行验证，不能据此授予任务资格。

后续实测：`live24` 的[18884 tick 前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_24/prefix_audit.json)通过，但第 66 段跟踪超时后回溯并停止。`live26` 的 50 mm 补偿使完整移动段首次完成，但 branch0 在末段停稳超时；通过公开参数重试的 branch1 以 3 mm 右手推进门限完成约 94 mm 移动，最终加权误差 3.29 mm，仍被原来的 3 mm 到位条件拒绝。branch2 使用 2 mm 推进门限，避免推进检查的 0.10 m 姿态权重与最终检查的 0.15 m 权重造成上述不一致；其[完整让位结果](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_26/planning/reposition_lower_005/lower_reposition_result.json)通过，实测下方误差 1.97 mm、环误差 0.95 mm，随后开始执行 83 姿态退环候选。这些回溯分支均无完整证明资格。[末段数值诊断](../../../runs/test_results/horseshoe_oracle_20260930/live26_terminal_tracking_diagnosis.json)记录到明显往复运动，位置控制力矩估计仅占配置上限约 10%–15%；[实际配对几何](../../../runs/test_results/horseshoe_oracle_20260930/live26_full_geometry_diagnosis/result.json)相对参考仍有约 14° 角度偏差，不能把单件移动到位称为两件完全对齐。该历史姿态的固定全障碍物搜索达到约 60.55 μm 局部释放间隙后耗尽 300 s，未形成完整路径。

`live27` 从默认 home 开始测试 `stages:damped_full_reposition_stages`：完整让位、右手推进门限 2 mm、位置补偿上限 60 mm、积分增益 0.75/s、实测线速度反馈 0.25 s（目标偏移每轴最多 20 mm）；退环沿用同组反馈和固定支撑目标。默认反馈仍为 30 mm、2/s、无速度反馈。新增项只改变普通机器人目标生成，未改变原生机器人增益、力矩、物理或最终目标规则。完整运行及资格尚未完成。

`live27` 的原始速度反馈在约 94% 处激发了逐 tick 正负交替的快速运动，目标偏移触及 20 mm 限制，并反复触发原生 IK 补偿回退；已通过公开 abort 中止该阶段，branch1 仅关闭速度反馈，保留 0.75/s 积分和 60 mm 上限重试。该运行已有回溯，不能作为完整证明。`live26` 在第 41 段附近失去参考方向的有效终点；只让链环被动的全方向搜索耗尽 600 s，随后允许上件被动的全方向候选找到 64 姿态路线，正在短段执行。两者均尚未完整取环。

`live27` 的无速度反馈重试完成了移动，但最终停稳阶段仍超时，已公开停止。新[参考路线检查](../../../runs/test_results/horseshoe_oracle_20260930/canonical_guide_full_reposition_probe_01/results.json)拒绝直接拼接整条退出参考：四种椭圆半转姿态均在桥接处碰撞或 IK 不可达，但参考翻环中段存在可达检查点。新增 `reference_pivot` 规划模式先搜索 `fold_end_index + 80` 的中间姿态，实测达到 3 mm 材料位姿邻域后才切换到原参考退出目标；这一局部门槛不是分离或原生任务成功条件。机器人、桌面、闭环和最终目标检查保持不变。

[翻环中点关节候选](../../../runs/test_results/horseshoe_oracle_20260930/canonical_pivot_joint_probe_01/free_ring_transport_plan.json)通过 629 个姿态、3849 个密集 IK／碰撞样本，所选终点确为 `fold_end_index + 80` 的第 2 个半转对称姿态，与集成目标的材料位姿差约 0.323 μm。[路线度量](../../../runs/test_results/horseshoe_oracle_20260930/canonical_pivot_joint_probe_01/route_metrics.json)给出总材料运动约 2.177 m；对固定余件，路径第 246 个姿态首次满足 5 mm 分离平面，但实际被动物体会移动，不能授予物理成功。`live28` 使用 `stages:pivot_reference_stages` 和哈希绑定的该引导从默认 home 重新执行：完整让位采用右手 2 mm 门限、50 mm 补偿；退环采用 60 mm 补偿、2/s 积分、无速度反馈、固定支撑，逐段和逐 tick 重查。`live26` 在第 71 段跟踪超时后累计 3 次回溯，已请求公开停止；无完整取环。

`live28` 的[抓环前缀对比](../../../runs/test_results/horseshoe_oracle_20260930/live28_grasp_prefix_comparison.json)在 199.45 s 与 `live26` 的五物体位姿及双臂关节值完全一致；其[独立前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_28/prefix_audit_11110.json)覆盖 11110 tick / 277.725 s，保持 branch0、全部 19 对连接、有效双指抓取及关节限位，无抓持丢失，最大任务接触穿透 0.321537 mm。仍只覆盖前缀，不构成取环和原生目标成功。随后[完整让位](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_28/planning/reposition_lower_003/lower_reposition_result.json)在 branch0 的 336.775 s 实际通过，误差与 `live26` 已通过的局部分支一致；新的翻环引导开始连续执行。

`live28` 的[扩展前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_28/prefix_audit.json)通过 14371 tick / 359.25 s，包含完整让位与翻环起步，最大接触穿透 0.329827 mm；随后第 10 段在 408.725 s 跟踪超时并首次回溯，不能算完整证明。`live29` 从 home 测试 `stages:filtered_pivot_reference_stages`：让位参数不变，翻环使用控制周期内实测位移差分、0.1 s 一阶滤波、0.25 s 速度反馈。滤波状态跨短段保留，同一观测不会重复差分，换持有物体时重置；默认无速度反馈的行为不变。[历史观测离线计算](../../../runs/test_results/horseshoe_oracle_20260930/filtered_velocity_diagnosis.json)降低了旧振荡记录的反馈偏移，但不能证明闭环稳定，真实执行仍待验证。

进一步审查发现，旧 `follow_bodies` 每个短段都从实测右手物体位姿重新插值至支撑目标，段内参考并非常量。[实测诊断](../../../runs/test_results/horseshoe_oracle_20260930/support_target_interpolation_diagnosis.json)记录第 10 段右侧实际支撑偏移曾达 22.06 mm，但不能仅据此认定全部振荡原因。新增 `fixed_sides` 并在取环运动与保持中固定右侧参考；`live30` 以这一修正和滤波反馈重新从 home 执行，`live29` 保留为此前控制方式的独立对照，二者均使用各自冻结源码。运行入口现为 `scripts/oracle_runners/run_solvability_workflow.py`；旧目录迁移不影响已冻结的运行。

`live29` 的滤波反馈实际越过了 `live28` 反复失败的参考索引 13，但在下一段 `withdraw_010` 跟踪超时并回溯，仍无完整证明。`live28` 的额外局部重试（原始速度反馈 0.02 s，以及 0.05 s 加右手 3 mm 推进门限）均未通过原停滞段，已停止。[误差拆分](../../../runs/test_results/horseshoe_oracle_20260930/live28_tracking_error_breakdown.json)显示其末端主要为平移误差，左／右约 1.78 / 4.18 mm；固定环的[再次对齐搜索](../../../runs/test_results/horseshoe_oracle_20260930/second_alignment_probe_01/error.json)没有接受任何候选自由边，未进入 IK 检查，不能据此推断无解。`live30` 继续验证段内固定支撑参考。

`live30` 在完成让位前收到未知来源的终止（外层进程退出码 143），最后资源记录约 47.08% 内存，未记录 90% 保护触发；原运行报告与轨迹未改写，另存[中断记录](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_30/interruption_observation.json)。`live31` 使用 `live30/source_snapshot` 的相同冻结源码从 home 重新执行，避免混入同时进行的仓库修改；旧前缀不拼接为新证明。

### 当前 assist / terminal 更新复核

[配置与合同复核](../../../runs/test_results/horseshoe_oracle_20260930/assist_terminal_review.json)确认：有效抓持的手指接触允许 2 mm，其他任务接触仍为 1 mm；真实双指接触不要求非零接触力。原 oracle 的统一 0.8 mm 阶段限制和统一 1 mm 审计未使用这一分类，现已同步：普通接触保留阶段提前停止门限，合格抓持手指接触使用 Task 的 2 mm；新运行记录终止与接触规则元数据，缺少该元数据的历史证据继续使用旧审计规则，不追溯授予资格。闭环、自碰、桌面、抓持健康和完整目标要求不变。

新版推荐 assist 覆盖整个马蹄表面；easy 的马蹄抓取区域半径由局部 40 mm 改为 90.55 mm，TCP 距离门限由 90 mm 改为 120.55 mm，仍须实际双指闭合接触且每手最多绑定一个目标。圆环采用包围实际表面的 77.90 mm 区域。[下一次运行配置](../../../runs/test_results/horseshoe_oracle_20260930/oracle_config_current_assist.json)已生成，未热改正在执行的冻结运行。现有接触规则 12 项、terminal 默认规则 7 项和推荐 assist 区域 4 项检查全部通过，仅属于合同／配置检查。最近取环失败为跟踪超时，并非触发旧接触上限；扩大马蹄可抓区域可用于新的换抓与接触支撑候选，但效果仍需真实执行验证。

[停滞计时复核](../../../runs/test_results/horseshoe_oracle_20260930/withdrawal_timeout_diagnosis.json)显示，`live28` / `live29` 首次失败前最后一次推进仅距终止 4.625 / 1.900 s，固定总时长上限把缓慢推进也归为停滞。新增 `stages:patient_pivot_reference_stages` 仅在连续 10 s 无推进时触发局部停滞，外层每段 50 s 总预算不变；三项合成时钟回归验证慢推进、真实停滞和旧默认行为。`live32` 使用新版推荐 assist、分类型接触检查、固定支撑参考与这一计时策略，从 home 重新验证。`live31` 已经由公开 stop/abort 请求结束，未将其前缀拼接到新运行。`live29` 的第三个局部候选越过了 `withdraw_010`，但此前两次回溯仍使其仅具诊断资格。

新版 assist 的[实际早期对比](../../../runs/test_results/horseshoe_oracle_20260930/new_assist_grasp_prefix_comparison.json)确认 `live32` 在 tick 500 / 12.5 s 两手分别抓住正确马蹄，五物体位姿与速度和旧 `live28` 完全一致；[独立新规则前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_32/prefix_audit.json)通过 1364 tick / 34.075 s，普通接触最大 8.714 μm、合格手指接触最大 0.275681 mm，19 对闭环、双指取得抓持、home 与源码身份均通过，无抓持丢失。此证据只覆盖抓取、抬升和折合起步，没有取环或最终目标成功。

[替代抓环姿态筛选](../../../runs/test_results/horseshoe_oracle_20260930/alternate_exit_grasp_probe_01/results.json)在完整让位的实测固定余件上检查 240 组位置／夹爪角度：25 组预抓与抓取端点通过，但本次 IK 种子下没有同时通过参考翻环中点与最终出口的组合；未验证接近、换抓或动力学，不构成不可达证明。`live29` 已在两次回溯后的分支持续取环；其 513.075 s 实测状态的[再次让位检查](../../../runs/test_results/horseshoe_oracle_20260930/second_alignment_probe_02/error.json)仍未找到保持圆环不动的合格直接路径，没有据此执行第二次让位。

新版抓环实际到达 branch0 的 191 s，但固定圆环的下马蹄让位搜索没有找到合格路径，尚未执行让位。改从这一实测抓姿直接搜索，[40 姿态候选](../../../runs/test_results/horseshoe_oracle_20260930/live32_direct_withdrawal_probe_01/joint_withdrawal_guide.json)在 494 次查询、约 5.86 s 内通过有限采样原生 IK、几何与被动闭环检查；它允许三个被动部件接触，仍须验证真实响应，不能视为已取环。

`live33` 使用新版 assist 与接触分类，从 home 重新执行 `live32` 保存的 7640 条普通关节／夹爪动作，再实际验证上述较短候选。[动作输入](../../../runs/test_results/horseshoe_oracle_20260930/oracle_inputs_replay32_direct.json)按 SHA-256 固定；配置仅允许工作目录不同。重放结束须核对五物体位姿、双臂关节与实际抓持，然后才进入取环；没有恢复物理状态或拼接执行。重放模块三项回归检查通过，真实末态复现与完整成功仍待该运行验证。`live32` 已在公开等待点停止；`live29` 再次跟踪失败并回溯，已请求停止，保留诊断证据。

`live32` 的完整抓环前缀审计随后通过 7641 个观测（tick 0–7640 / 191 s）：普通接触最大 0.313204 mm、合格手指接触最大 0.276155 mm，无失败或抓持丢失。`live33` 的[早期比对](../../../runs/test_results/horseshoe_oracle_20260930/live33_early_replay_comparison.json)发现动作虽一致，物理状态从 tick 422 出现微小差异，到 tick 500 环位置已差约 46.86 μm，未确定原因，不能认定精确重现抓姿。该重放尝试已请求停止。当前 `live34` 使用 `stages:patient_direct_exit_stages` 从 home 重新执行原实时反馈前缀，然后直接验证短候选，按每段实测状态重查 IK、碰撞和连接；仍无取环或完整成功结论。

`live34` 随后在 191 s [实际复现抓环末态](../../../runs/test_results/horseshoe_oracle_20260930/live34_grasp_prefix_comparison.json)：五物体完整状态与双臂状态均和 `live32` 一致，未使用状态恢复。[前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_34/prefix_audit.json)通过 7749 个观测至 193.7 s，覆盖真实抓环和取环起步，无失败或抓持丢失。短取环候选连续通过前九段后，第十段跟踪停滞并首次回溯；上方马蹄随圆环移动，两侧控制补偿达 60 mm 上限，没有真实分离。该运行后续仅用于诊断。

从 `live34` 的 223.825 s 实测状态进行[下马蹄单独让位检查](../../../runs/test_results/horseshoe_oracle_20260930/live34_alignment_probe_01/error.json)，没有找到合格直线边；[双物体对齐端点检查](../../../runs/test_results/horseshoe_oracle_20260930/live34_coupled_alignment_probe_01/results.json)将圆环和下马蹄一起对齐参考，在 24 个端点中未找到合格项，主要为双夹爪碰撞或原生 IK 不可达。均为有限只读筛选，不是无解证明；正在检查同时适合抓取和后续对齐的替代抓姿。

`live34` 最终在三次诊断回溯后停止。重新搜索短路线和将位置补偿上限从 60 mm 提高至 100 mm 均未解除阻挡，后者增大了跟踪误差。此前通过的前缀审计保持原范围，不涵盖这些失败分支。

替代抓姿的[完整接近检查](../../../runs/test_results/horseshoe_oracle_20260930/coupled_alignment_grasp_approach_probe_01/results.json)找到 285°、300°、315°（approach sign +1、flip −1、roll 45°）三个候选，分别通过自由手转移、直线接近及闭指几何检查；尚未实际取得抓持。双臂共同对齐的直线候选均被拒绝，按新版普通 0.8 mm／合格手指 2 mm 分类的[关节搜索](../../../runs/test_results/horseshoe_oracle_20260930/coupled_alignment_joint_contact_policy_probe_04/result.json)在 300 s、10070 次查询内没有连通端点。这些有限搜索不能证明无解。

保持下马蹄不动的[独立端点筛选](../../../runs/test_results/horseshoe_oracle_20260930/upper_exit_grasp_probe_01/results.json)发现 315° 抓姿可达向上翻环的中间姿态，但相同对称姿态下的最终出口不可达。后续先验证这段翻环及被动上件响应。另有[上件接触支撑优化](../../../runs/test_results/horseshoe_oracle_20260930/upper_support_clamp_optimization_01/result.json)检查 2928 个局部六维姿态，未找到同时满足双指支撑与物体穿透门限的候选，未实际执行。

细化抓姿后，295°／roll 40° 的[完整接近检查](../../../runs/test_results/horseshoe_oracle_20260930/refined_upward_grasp_approach_probe_01/results.json)通过；[局部向上翻环引导](../../../runs/test_results/horseshoe_oracle_20260930/refined_upward_prefix_guide_01/partial_pivot_guide.json)覆盖直线关节候选的 78.92%，压缩为 136 个姿态后通过 610 个有序 Cartesian IK／碰撞样本。它没有覆盖最后翻环和出口。`live35` 使用 `stages:patient_upward_pivot_stages` 与哈希绑定输入，从 home 验证新抓姿和这一局部路径，采用新版 assist、手指接触分类及原生 terminal；真实抓持、被动响应和完整成功仍待验证。

桌面支撑作为另一候选：[右手下降与抓环检查](../../../runs/test_results/horseshoe_oracle_20260930/table_support_native_probe_01/results.json)通过 114.54 mm 的假定刚性下降路径，使垂下的上件距桌面 1 mm；实际被动运动尚未执行。原右手弯底抓法无法完成桌边对齐，横向位置筛选还出现桌面碰撞。完整表面 assist 覆盖了原局部区域之外的 270°／315° 马蹄抓点，见[区域比较](../../../runs/test_results/horseshoe_oracle_20260930/expanded_assist_grasp_region_comparison.json)。替代右手抓法有桌边合格端点，其中 270°／flip −1 通过 228 个折合样本，但后续倾斜尚未通过原生 IK，不能直接作为执行配方。

随后 295°／roll 40° 的[完整翻环关节搜索](../../../runs/test_results/horseshoe_oracle_20260930/refined_upward_joint_probe_01/result.json)在 214.12 s、17337 次查询后连通参考中间姿态（index 3209，symmetry 3）：5 个关节折点、1126 个密集样本。它的首段沿用上述局部引导，末段绕开下马蹄；压缩为 [283 姿态完整翻环引导](../../../runs/test_results/horseshoe_oracle_20260930/refined_upward_full_guide_01/full_pivot_guide.json)后，通过 1126 个有序 Cartesian 样本复核。完整引导另存为下一次运行的哈希输入，未替换正在执行的 `live35` 局部输入；实际被动响应和取环仍未通过。备用桌面方案的 270°／flip −1 抓姿，在平移 `[-0.04, 0.10, -0.04] m` 后通过 [296 个双臂倾斜样本](../../../runs/test_results/horseshoe_oracle_20260930/table_support_high_grip_tilt_probe_01/result.json)，尚无该新抓法的物理执行。

`live35` 未取得新抓姿：在实际交接后的 183.425 s，295°／roll 40° 的两种接近距离都被原生 IK 拒绝，随后一次诊断回溯并停止；没有执行向上翻环。[实际状态差异](../../../runs/test_results/horseshoe_oracle_20260930/live35_pregrasp_differences.json)显示，相对 `live34` 用于筛选的状态，圆环位置差 32.82 mm、姿态差 127.06°，差异原因尚未确定。此前完整翻环引导仍仅适用于它记录的规划状态与假定抓姿，不能转移成功资格。后续改为在实际交接状态筛选抓姿，并要求该抓姿至少有一个通过原生检查的翻环端点；接近、连接路径和真实执行仍分别验证。

继续比对确认，`live34`／`live35` 的折合与倾斜记录完全相同；第一次动作差异出现在 tick 6693 / 167.325 s。[撤手路径对比](../../../runs/test_results/horseshoe_oracle_20260930/live35_free_transit_comparison.json)显示，前者选到腰关节 +1 rad 的两点直线转移，后者选到 −1 rad 的四点 RRT 路径。原实现为每个候选依次分配 10 s 搜索，再考虑下一个候选；旧失败候选的具体超时原因未保存，不能把负载影响称为已直接观测的原因。现在先检查全部候选的直线路径，再尝试 RRT，保持原有碰撞与末端间隙检查。

`live36` 使用 `stages:adaptive_upward_pivot_stages`，从 home 验证实际状态下的抓姿筛选与翻环；它冻结时尚未包含上述撤手优先级修改。在 `live35` 实测状态上的[自适应抓姿检查](../../../runs/test_results/horseshoe_oracle_20260930/actual35_adaptive_grasp_probe_01/result.json)找到 300°／sign −1／flip +1／roll 0° 候选，接近路径和两个翻环端点通过。关节规划另增加可选的目标附近采样与保留已检查直线前段，默认旧搜索方式不变；这些改动不放宽接触、碰撞、连接或原生成功门限。

`live37` 使用完整 283 姿态翻环引导，并冻结先检查全部直线候选的撤手策略，从 home 验证 295°／roll 40° 抓姿。该撤手修改在 [同一实测输入的复核](../../../runs/test_results/horseshoe_oracle_20260930/direct_first_retreat_probe_01/result.json)中，产生与 `live34` 完全相同的目标、关节样本、观测物体和两点路径；实际后续状态仍须独立确认。与此同时，[实际 `live35` 状态下的自适应完整翻环规划](../../../runs/test_results/horseshoe_oracle_20260930/actual35_adaptive_pivot_route_01/result.json)找到 290 姿态路径，并通过有序 Cartesian 检查。这两条均只到中间翻环姿态；`live36`／`live37` 的真实抓持、被动运动及最终取环尚待运行结果。

`live36` 已在 199.45 s 真实取得 300°／sign −1／flip +1／roll 0° 抓姿，并保持右手持下马蹄。[前缀独立审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_36/prefix_audit.json)覆盖出生至此的 7979 个连续状态：branch 0、闭环连接全部保持、双指获取有效、无抓持丢失或其他失败；普通接触最大 0.321537 mm，合格手指接触最大 0.286271 mm。实际抓持后的翻环路径正在重新规划，该前缀不含翻环或最终成功。

`live37` 的[实际交接起点比较](../../../runs/test_results/horseshoe_oracle_20260930/live37_pregrasp_reproduction.json)确认抓环规划时五个物体的位姿与 `live34` 完全一致。它于 191.025 s 真实取得 295°／roll 40° 抓姿，随后完整引导在[实际抓持偏移复核](../../../runs/test_results/horseshoe_oracle_20260930/actual37_full_guide_probe_01/result.json)中通过 1129 个有序样本；物理短段正在执行。[独立前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_37/prefix_audit.json)覆盖至 216.25 s 的 8651 个连续状态，全部检查通过，无抓持丢失。`live36` 的实际抓持后规划也通过（329 姿态、2023 个有序样本），但早期物理响应出现持续支撑偏移。均未完成翻环与取出，不能授予完整成功资格。

`live37` 的[扩展前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_37/prefix_audit.json)已覆盖 360.45 s／14419 个连续状态，全部检查通过，普通接触最大 0.313204 mm、合格手指最大 0.275681 mm；较早范围另存 [216.25 s 审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_37/prefix_audit_through_216_25s.json)。翻环仍在执行、尚未分离。[出口端点预检查](../../../runs/test_results/horseshoe_oracle_20260930/future37_exit_endpoint_probe_01/result.json)有 8／68 个候选通过，但它假设已经到达翻环端点，并冻结抓取时的被动物体位姿；不能代替未来实际状态的连接规划。

`live36` 在实际状态重新规划后仍于第 19 段停滞：306.225 s 时环误差约 1.53 mm、下马蹄相对支撑目标误差 29.49 mm，随后一次诊断回溯。已中断后续搜索，见[中断说明](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_36/interruption.json)；原始 `run_report.json` 未完成收尾，保留其 `running` 字段并单独说明，不伪造正常完成。[停止前审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_36/prefix_audit.json)只覆盖 branch 0 至 298.525 s 的 11942 个连续状态，全部检查通过；这不包含之后的停滞终点或回溯，也不是完整成功。

`live37` 最终在 564.425 s／第 125 段规划入口停止，保留零回溯的连续出生前缀；[最终前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_37/prefix_audit.json)覆盖 22578 个状态，全部检查通过，无抓持丢失。之前一次 600 s 搜索超时发生在物理动作前，未引入回溯；随后仅允许链环被动接触的后备路线曾继续推进。最后的[起点阻塞诊断](../../../runs/test_results/horseshoe_oracle_20260930/wait125_start_contact_probe_01/result.json)定位到左手单根手指与上马蹄约 11.009 µm 的接触，50 µm／100 µm 正间隙规划都拒绝它，而实际 Task 普通接触允许这一深度。没有完成分离或原生目标。

新增可选 [ContactHorseshoeIK](../../../topogym/planning/horseshoe_ring/native_contacts.py) 对所有机器人／任务物体接触显式分类：普通接触上限 0.8 mm，符合原生条件的手指接触 2 mm；保留关节、自碰、双臂和桌面检查，不改变物理、assist 或成功判据。[实测等待状态复核](../../../runs/test_results/horseshoe_oracle_20260930/wait125_native_contact_route_probe_01/start_check.json)通过；[分离姿态候选路线](../../../runs/test_results/horseshoe_oracle_20260930/wait125_native_contact_route_probe_01/result.json)有 131 姿态、3986 次查询、390 个有序样本，仅为未执行的接触规划。`live38` 使用 `stages:contact_upward_pivot_stages` 从 home 验证：折合和抓环仍沿用严格规划，取环／放置改用上述分类，完整物理成功待验证。

`live38` 在首次取环规划时遇到 `deepcopy(mappingproxy)` 接口错误，三个候选均未推进物理状态，零回溯。修复采用公共 `snapshots.thaw`；[真实只读观测回归](../../../runs/test_results/horseshoe_oracle_20260930/native_contact_frozen_observation_regression.json)确认接触分类不变、复制与观测隔离。[完整引导复核](../../../runs/test_results/horseshoe_oracle_20260930/actual38_native_frozen_guide_probe_01/result.json)通过 1129 个样本。`live38` 已正常停止，[前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_38/prefix_audit.json)覆盖 7642 个状态／191.025 s，全部检查通过；其实际抓环状态与 `live37` 完全相同。`live39` 使用修复后的独立源码快照从 home 重新验证。

桌面备用方案找到原双手抓法的连接候选：[301 姿态路线](../../../runs/test_results/horseshoe_oracle_20260930/folded_table_contact_path_from_tilt_probe_04/result.json)采用较长转动方向、目标 yaw 增加 10°、横移 +0.10 m，先横移后下降；终点上马蹄距桌面 1 mm。[密集复核](../../../runs/test_results/horseshoe_oracle_20260930/folded_table_dense_guide_01/table_support_guide.json)通过 1328 个有序样本、最大材料采样步长 0.75 mm，机器人最小离桌间隙 75.61 mm。新增 [table_support.py](../../../topogym/planning/horseshoe_ring/table_support.py) 与 `stages:table_supported_stages`，用哈希绑定的引导、实际抓持偏移和原生接触分类重查路线，再经普通动作执行；仍须验证被动部件的桌面响应、释放交接、抓环和取出。几何筛选中的刚性运输假设不施加到物理世界。

`live39` 已精确复现 `live37` 的机器人及五个物体抓环状态，并越过首次取环规划；[前缀审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_39/prefix_audit.json)覆盖 9366 个状态／234.125 s，全部检查通过，取环仍在执行。桌面模块的[实际只读观测复核](../../../runs/test_results/horseshoe_oracle_20260930/table_module_frozen_probe_01/result.json)通过 1328 个样本；假定刚性运输终点的[撤手与抓环预检查](../../../runs/test_results/horseshoe_oracle_20260930/table_handoff_endpoint_preview_01/result.json)通过，但实际被动物体明显偏离该假设。

`live40` 实际运输时圆环先落桌，随后两个链环接触桌面；在最后第 299 个姿态、进度 65.29% 处停滞，392.925 s 时左／右物体跟踪误差约 1.017／0.420 mm，未达到专门设置的 0.5 mm 控制门槛。物理守卫没有失败，但发生一次诊断回溯，已公开停止。保留[最后真实观测](../../../runs/test_results/horseshoe_oracle_20260930/live40_last_table_observation.json)及[停止说明](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_40/operator_stop_reason.json)。`live41` 从 home 重跑，运输末段及停稳使用明确记录的 1.5 mm 跟踪门槛；IK 路线、接触守卫、原生 Task、assist 和成功条件不变。此处改变的是 oracle 控制精度要求，尚不代表已完成桌面交接或取环。

`live39` 首次实际到达[参考翻环中间姿态](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_39/planning/withdraw_one_150/reference_pivot_reached.json)（reference index 3209、symmetry 3），材料位姿误差约 1.002 mm；仍未分离。此前两次实测重规划分别通过 47 姿态／258 个有序样本和 55 姿态／261 个有序样本。最新[前缀独立审计](../../../runs/test_results/horseshoe_oracle_20260930/live_diagnostic_39/prefix_audit.json)覆盖 24404 个状态／610.075 s：branch 0、来源与 home 有效、无抓持丢失或其他失败、19 对闭环全部保持。正在规划翻环后的退出路线；[实际翻环观测](../../../runs/test_results/horseshoe_oracle_20260930/live39_reference_pivot_observation.json)保留原始记录行哈希，不用于状态注入。较早停滞快照的[全方向出口预检](../../../runs/test_results/horseshoe_oracle_20260930/actual39_stall102_allaxes_probe_01/result.json)通过 104 姿态／514 个有序样本，未实际执行。

`live41` 虽越过桌面末段的早期慢点，仍在最后姿态进度 99.868% 处停滞：322.075 s 时左／右误差约 0.757／3.275 mm，随后一次诊断回溯。已公开停止并保存[真实末态](../../../runs/test_results/horseshoe_oracle_20260930/live41_last_table_observation.json)，没有完成桌面释放或抓环。[此前真实桌面末态的抓环预检](../../../runs/test_results/horseshoe_oracle_20260930/actual40_table_handoff_preview_01/result.json)假设左手已释放和撤离；960 个粗候选、54 个细角度候选及 16 个轴向偏移候选均未通过固定姿态筛选，主要受到其他物体或另一只手的阻挡。这些假设预检不能证明释放后的实际构型不可抓，也没有获得物理抓取信用。当前优先推进已经真实完成翻环的 `live39`。

### 证明结构与验收边界

[旧物体证书与当前实例的复核](../../../runs/test_results/horseshoe_oracle_20260930/object_certificate_current_identity_review.json)确认 easy / seed 0 的全部资产 SHA-256、初始位姿、目标区域及建模版本一致；实例标识随 terminal 从 `placement_region_v1` 改为 `placement_region_v3_grasp_contact_2mm` 而改变。旧证书仍保留原始身份与模板起点范围，其几何结果不等于当前机器人或 terminal 已通过。

物体路径证书枚举五个刚体的全部十对组合。每段使用质心线性插值与最短四元数 SLERP；设物体包围半径为 \(r_i\)，单段任一点的位移上界为 \(L_i=\|\Delta p_i\|+r_i\Delta\theta_i\)。在参数子区间宽度 \(h\) 上，中点距离 \(d\) 给出整段表面间隙的数值下界 \(d-\varepsilon-(L_i+L_j)h/2\)。程序递归细分，直到每个子区间都超过 50 µm，或者明确失败。当前距离误差预算 \(\varepsilon\) 为 1 µm；这属于固定网格、指定插值与误差预算下的数值证书，不是浮点区间算术证明。初始实体互不占据另由资产报告检查，不能仅凭表面距离排除完全包含。

机器人阶段另行验证：默认 home 出生、普通控制动作、真实双指接触后生效的单目标辅助抓持、连续 World tick 历史，以及被动部件的接触响应。独立审计逐 tick 重算全部 19 对跨物体闭环连接数，并检查任务物体、机器人自碰和桌面的接触穿透。有限采样 IK 与上述物体证书均不能替代这段动力学证据。

最终还必须实际达到固定目标区：圆环的全部可见与碰撞几何在区内、剩余组件位于分隔面系统侧，并满足速度和持续时间要求。当前尚无这一记录，也不写入正式可解性证明目录。仓库提交 `2ec4b8d6` 已让公共成功判据默认开启，证明资格只作元数据；`live28` 的冻结源码和实测 `goal_evaluation_complete=true` 已确认采用这一规则。新运行需从 home 连续取得原生成功，再经独立审计才能归档，不需要为了打开成功开关另外修改 Task。`live26` 等旧冻结副本仍关闭放置成功判据，其历史结果不追溯修改。

## 任务与实现

双马蹄通过两个独立链环连接。当前任务要求整个目标环进入固定区域、剩余组件留在分隔面系统侧，并短暂停稳；允许保持抓持。当前 oracle 从 ALOHA 默认 home 开始，通过真实双指接触取得单物体辅助抓持，依次尝试翻转、折合、交接、抓环和取出。

活动源码：[任务定义](../../../topogym/tasks/horseshoe_ring/common.py) · [几何生成](../../../topogym/assets/geometry/horseshoe_ring.py) · [oracle 与规划](../../../topogym/planning/horseshoe_ring/) · [执行 CLI](../../../scripts/oracle_runners/run_horseshoe_policy.py)。三档配置位于 `topogym/tasks/horseshoe_ring/horseshoe_ring_{easy,medium,hard}.py`。

## 历史 demo 状态与边界

基础版五视角 113.7 秒；同代码 2 ms / 1 ms 独立完整执行通过。F1 上方接近、F2 外侧接近、F3 后方接近均已补齐完整五视角，分别 129.7 / 125.8 / 119.7 秒；它们来自原成功物理状态重渲染，仅保留原 2 ms 验收范围。

## 历史变体记录

三个接近路线家族，围绕已成功中心做小范围条件采样。variant_generator 产生实例，variant_pipeline 做生成、重载、完整物理验收及拒绝重试。三族各有条件域随机实例通过 2 ms，新随机实例仍缺 1 ms 复验；非圆环形状池尚未开放。

## 历史视频证据

正式目录：`demos/horseshoe_ring/varaition_baseline/<camera>/`、`varaition_f1/<camera>/`、`varaition_f2/<camera>/`、`varaition_f3/<camera>/`，共 20 份独立 MP4。[全部视角与证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/README.md)。F1/F2/F3 低位相机统一移到桌面上方，改善遮挡及落桌画面的可见性；五路使用同一次执行的相同帧与时间戳。


- [2026-09-18_gravity_replanned_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1)
- [2026-09-18_timestep_validation_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_timestep_validation_v1)
- [2026-09-19_variant_generator_v2](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 历史生成入口（已归档）

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
# 仅产生一个候选实例描述，不运行机器人，不生成数据集或视频。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.variant_generator \
  --seed 42 --family F2 --output runs/variant_checks/horseshoe_seed42.json
```
