# 马蹄环

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

更新：2026-09-30。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 当前默认三档的 oracle 与证明工作

当前 easy / medium / hard 分别是 `waist_mild` / `u_mild` / `waist_ellipse`，revision 为 `coupled_shapes_settled_v2`，从桌面物理静置姿态出生。下文 9 月 18–21 日的 F1/F2/F3 视频属于旧的接近方向家族，不能授予当前三档成功资格。

目前按物体路径、机器人 IK、连续物理执行的顺序补充证据，**尚未取得当前版本的完整机器人可解性证明**：

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
| 当前衔接缺口 | 圆环在支撑交接后贴住上下马蹄。把上件固定的取出搜索尚未通过；正在检查包含局部接触脱离、允许环推动自由上件和链条的取出候选。取出、固定区域放置与完整成功尚待真实连续执行。尚无独立审计合格的完整成功记录。 |

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

### 证明结构与验收边界

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
