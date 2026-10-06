# 解绳结：一个松 Trefoil 的基础场景

> **2026-09-27 更新：** 正式 easy 为两次重叠单绳圈；medium 为原 easy 的 overhand_trefoil；hard 为原 medium 的 figure_eight。double_overhand 已移到实验附表。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。

## very_easy / easier 已确认场景（2026-10-05）

用户已确认预览形状。两个入口现登记到 `below_easy`，分别具有 `very_easy` / `easier` 难度标识；保留 easy / medium / hard、base 和原 `seeded` 的对应关系：

- `knot_untying_very_easy`：一个宽绳圈，圈口仅一处交叠，两条自由端。
- `knot_untying_easier`：一个宽绳圈，圈口两处交叠，沿同一侧绳段的上下关系交替，呈麻花状。现有 easy 则为同一侧绳段在两处都位于上方。

两者复用当前任务的 ALOHA home、桌面原点、yaw=0、橙色绳材质、8 mm 绳径、80 mm 圈半径和 FEM/IPC 材料网格及终态判据；形状生成见 [`knot_untying_simplified.py`](../../../topogym/assets/geometry/knot_untying_simplified.py)。资源由源码确定性生成，无新增外部模板或网格依赖。

几何检查覆盖交叉数、上下顺序、自穿透／穿桌、弯曲半径、闭合网格及场景继承；现有四种结型的左右手版本资产哈希全部保持一致。已确认的初态截图与源码快照保留在 [`knot_below_easy_preview_20261005/`](../../../runs/test_results/knot_below_easy_preview_20261005/)，没有修改该版形状。

当前实现及验证产物在 [`knot_below_easy_implementation_20261005/`](../../../runs/test_results/knot_below_easy_implementation_20261005/)。两档均通过当前 v16 公共工具执行 600 ticks 静置并独立重建，保存新的完整 IPC 初态和实例。`check_knot_initial_states.py` 核对全状态 SHA、reset 恢复、短时漂移、交叉结构、初态未成功及只读抓取 IK，使用公共四路 Nyx 录制。参考策略复用现有 ALOHA 纯摩擦抓取：单交叉先尝试两端展开，交替双交叉按实时绳形选择下穿段并逐处抽出；已接入具名 CLI 和 Harbor callback。策略存在及初态检查不表示完整求解或 Harbor 评分已通过，难度排序也须另行验证。

初态验收：very_easy 状态 SHA `54061df528743330`，静置 1 s 最大节点漂移 0.242 mm、末速 0.228 mm/s；easier 为 `d2ae0ea7cf69a49c`，静置 1 s 最大漂移 0.828 mm、末速 0.780 mm/s。两档均保持各自交叉结构，初态不成功，独立进程恢复和 reset 全状态一致。easier 的首选 A 端抓点 IK 不可达，现仅在新两档参考策略中按实时交叉依次检查另一端及相邻材料位置，选择了可达的 B 端；同实例二次检查通过，未改变场景。证据见 [very_easy](../../../runs/test_results/knot_below_easy_implementation_20261005/very_easy_initial_check/report.json)、[easier 静置](../../../runs/test_results/knot_below_easy_implementation_20261005/easier_initial_check/report.json)与 [easier 抓点复核](../../../runs/test_results/knot_below_easy_implementation_20261005/easier_initial_check_02/report.json)。

场景实现阶段的 68 项几何、策略、回放合同及入口检查通过。两次本地机器人试跑均从冻结 home 初态开始，very_easy 执行到两端展开，easier 执行到抽出下穿段；尚未完成解绳，已在转入正式 Harbor 验证时主动停止并保留日志、录像及停止记录。原进程身份见 [运行记录](../../../runs/test_results/knot_below_easy_implementation_20261005/active_robot_runs.json)，该记录不代表目前仍在运行或完整成功。

**Harbor oracle 开发（2026-10-05）：** 按用户要求以两档实际 `solved=1` 为目标，使用独立冻结的 v16 镜像及双模式任务包。工作目录与判定范围见 [验证计划](../../../runs/test_results/knot_below_easy_harbor_20261005_01/plan.json)。privileged 要求隔离 verifier 的两遍 grading replay 均成功，至少一遍在提交行内达到严格目标，并通过初态／运行绑定及接触复核规则；standard 要求 live 与独立 replay 均成功。原生策略返回成功不能代替评分。

已有 hard 的真实轨迹中，23 行关节目标变化超过 standard 的 0.04 rad/控制步上限，导致服务额外插入控制步。新两档现从所选 tooling 读取该上限，将较大移动拆成实际执行和记录的连续控制步；没有重定时已有成功轨迹，也没有修改 verifier 或原 easy–hard 策略。新增两项控制合同检查通过，Knot oracle 合同检查共 34 项；冻结私有回调在候选镜像中导入通过。双模式任务包已生成，实际评分进展见下文。

**very_easy 已在 privileged 和 standard 两种模式通过正式 Harbor 评分（均为 `solved=1`）。** 本轮实例状态 SHA 为 `e1d88911f85faea8`，与上述初态验收实例分别记录；初态恢复为 exact。ALOHA 从冻结 home 经纯摩擦双端抓取、展开、落桌释放，在 **20.8525 s** 成功：835 actions／8,341 ticks，末行动 1 tick 后正常终止，连续稳定 0.5 s，最大绳速 0.4920 mm/s。投影无交叉／重叠、落桌、静止与完整终态判据均成立；835 行请求动作与实际接受动作一致，无 guard 改写。见[原生报告](../../../runs/test_results/knot_below_easy_harbor_20261005_01/grading/very_easy_01/jobs/001-oracle/topogym-knot-untying-very-easy-i__ogUUME8/artifacts/app/output/report.json)和[桥接执行证据](../../../runs/test_results/knot_below_easy_harbor_20261005_01/grading/very_easy_01/jobs/001-oracle/topogym-knot-untying-very-easy-i__ogUUME8/artifacts/app/output/bridge_report.json)。

隔离 verifier 的两遍回放均在第 **835 行**达到严格成功，均为 8,341 ticks／20.8525 s；`replay_hold_steps=0`、`replay_tolerance_needed=0`、`review_events=0`。Harbor 成绩、verdict、reward、轨迹及实例哈希、运行绑定和冻结私有源码已逐项核对，见[评分证据复核](../../../runs/test_results/knot_below_easy_harbor_20261005_01/very_easy_privileged_verification.json)。两遍最终状态哈希不同，这是 GPU 诊断项，不影响当前 verifier 对两遍严格成功的判定。[Harbor 第二遍回放视频（合并视角）](../../../runs/test_results/knot_below_easy_harbor_20261005_01/grading/very_easy_01/jobs/001-oracle/topogym-knot-untying-very-easy-i__ogUUME8/verifier/replay.mp4)完整解码通过：314 帧、15 fps、1130×480。

standard 的 live 与新进程独立回放均已成功：835 actions／8,341 ticks／20.8525 s，live 的四次提交分别执行 241、251、245、98 行；单次调用达到时限后从已确认行继续，无重启。完整动作和 tick 台账与同一参考轨迹逐字节一致，四批均零裁剪、零额外控制步。独立回放在第 835 行达到严格目标，额外保持步和容差使用均为零；实际 Harbor reward、运行绑定、初态身份、冻结源码与完整媒体已核对，见[standard 评分证据复核](../../../runs/test_results/knot_below_easy_harbor_20261005_01/very_easy_standard_verification.json)。[standard 独立回放视频](../../../runs/test_results/knot_below_easy_harbor_20261005_01/grading/very_easy_01/jobs/002-oracle/topogym-knot-untying-very-easy-i__TwfG4TY/verifier/replay.mp4)完整解码通过，314 帧、15 fps、1130×480。live 与 replay 最终状态不逐位相同，当前 GPU verifier 接受二者各自严格成功。

easier 首次正式 privileged 尝试完成了第一轮抽绳，交叉数 2→1，但随后的双端整理抓取失效：闭爪前左臂仍有约 27.8 mm 的 TCP 位置误差，之后目标绳段未随夹爪移动。已主动停止该次尝试，保留 1,513 actions／15,130 ticks 的完整已记录前缀及日志，见[失效抓取诊断](../../../runs/test_results/knot_below_easy_harbor_20261005_01/diagnostics/easier_failed_end_grasp_01/diagnosis.json)。SIGINT 发生在 stepping 中，结束时的 `Env is faulted` 属于中断结果；不能将其当作先前物理失稳原因。该次尝试没有 easier Harbor 分数，standard 未运行；后续修正仅针对私有抓取策略，复用同一公共场景、物理与 verifier。

very_easy 已获成绩与 easier 首次尝试绑定 [`oracle_source_01`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/oracle_source_01/) 和 [`references_01.json`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/references_01.json)，冻结的 18 个私有文件保持不变。工作区共享控制器随后加入了统一限速、crush guard 和 hover gate 等修改；这些修改不在上述执行快照内，不能沿用其成绩，差异见[源码版本核对](../../../runs/test_results/knot_below_easy_harbor_20261005_01/diagnostics/worktree_drift_20261005.json)。

easier 第二轮使用冻结的 [`oracle_source_02`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/oracle_source_02/)，完成第一处交叠的消除，但三次双端抓取的空中对准最终误差分别为 **14.1、6.9、5.9 mm**，均拒绝闭爪。原生策略正常结束并保存 1,271 actions／12,710 ticks／31.775 s 的完整失败轨迹；没有执行空抓后的拉伸。桥接报告原生任务未成功，随后主动停止该失败轨迹的 verifier 回放，未产生完整 Harbor 分数；standard 未运行。见[第二轮失败证据](../../../runs/test_results/knot_below_easy_harbor_20261005_01/diagnostics/easier02_failed_pregrasp.json)。这次没有原生中断或物理失稳，不能与第一轮 SIGINT 后的 fault 混为一谈。

第三轮使用 [`oracle_source_03`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/oracle_source_03/) 的 19 个私有模块，相对第二轮只改 [`BelowEasyRunner`](../../../topogym/planning/knot_untying/below_easy_runner.py)。它根据实时剩余交叠再选一次下穿段抽绳，优先路线保留已成功的 A 端 15 mm 锚点；保留原有接近容差和首轮成功采用的抓取高度，在闭爪前严格核对实时目标与实测 TCP（2 mm／0.1 rad），并在抬升后验证绳段跟随。第一次成功抽绳的空中误差约 13.6 mm、下降后约 1.6 mm，因而空中接近与闭爪对准分开判断。公共候选、初态、物理和 verifier 不变。7 项抓取回归、34 项原有 oracle 合同、12 项命令安全检查、两档打包与镜像内 19 模块导入通过；这些静态检查与下文原生执行分别记录。见[第三轮计划](../../../runs/test_results/knot_below_easy_harbor_20261005_01/retry03_plan.json)。

第三轮已实测通过第二次抓取：闭爪前左／右 TCP 位置误差分别为 **1.71／1.49 mm**；右侧材料点抬升 **9.09 mm**，实际接触点抬升 **8.82 mm**，两者距离 **1.23 mm**。对应动作前缀及测量见[第二次抓取证据](../../../runs/test_results/knot_below_easy_harbor_20261005_01/diagnostics/easier03_followup_grasp/report.json)。随后在约 **22.625 s** 观察到投影交叉数 **1→0**，在 **26.6125 s** 完成释放及连续 0.5 s 停稳，原生完整任务成功。1,065 actions／10,645 ticks，末行 5 ticks，动作请求、接受值与轨迹一致；见[原生执行复核](../../../runs/test_results/knot_below_easy_harbor_20261005_01/easier_native_execution_check.json)。用户随后要求转入 v18+ 验证，已停止尚未完成的 v16 verifier 并保留全部原生证据；该轮没有完整的 easier Harbor 分数，standard 未运行。[停止记录](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/old_run_stop.json)。

**v18 复验已启动，尚无新版成绩。** 独立目录为 [`regrades/v18_20261006_01`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/plan.json)，实际镜像为 `topogym-below-easy:v18-20261005-01`，tooling 18／`0.2.16-dev`／确定性 `pyuipc 0.0.25+topogym.det1.cuda128`。very_easy 使用此前 source01、easier 使用 source03 的逐字节副本。v18 的 K2 使用 5 ms × 5 ticks／控制步及半隐式至少三轮 Newton，控制周期仍为 25 ms；冻结初态须由该版本重新生成，不能将旧轨迹的实例身份改写后当作新版成绩。[环境差异核对](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/environment_comparison.json)确认场景生成代码、任务参数和成功判据未改变。流程为新实例构建、exact 恢复、privileged 原生执行和两遍回放、standard 在线执行和独立回放；实际进度见[状态文件](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/status.json)。

v18 两档任务包均已生成并通过独立进程 exact 初态恢复：very_easy 为 `00922855b3029266`，easier 为 `befb901fe8841b8a`。[冻结初态投影核对](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/initial_projection_check.json)确认原网格哈希、一处／交替两处交叠和初态投影目标未满足；这不代替完整求解。Very-easy 的 v18 原生 Harbor 执行已开始，正式分数仍待产生。

几何回归入口：`.venv-gs121-nyx/bin/python ci_checks/test-knot-simplified-geometry.py`。
准备、运行和回放命令见 [Knot oracle 用法](../../../topogym/planning/knot_untying/README.md#已确认的-very_easy--easier-变体)。

## 当前释放规则与 hard11–hard14 的修正验证（2026-10-04）

**最新方向：按用户要求转入现有 Harbor bridge grading。** hard14 的本地原生成功（51.335 s、2,054 actions）及冻结证据保留；本地首遍回放已主动停止，最后完整采集为 9.8425 s／3,938 个状态，机器人／桌面观察器无 findings，但整段回放、FEM 审计和视频资格未完成。停止是验证路线调整，不是原生物理失败，见[停止记录](../../../runs/test_results/knot_oracle_20261003/hard14_replay/harbor_handoff_stop.json)。已用独立冻结的当前 v16 源码和专属镜像生成 hard 双模式候选，实例身份 `66ea1051ee23377c`；Harbor privileged oracle 已通过现有 Knot Session 回调在新实例上取得原生成功：51.0625 s、2,043 actions／20,425 ticks、连续稳定 0.5 s，`instance_exact=true`、终态 `robot_clear=true`／`robot_no_penetration=true`。见[新实例原生报告](../../../runs/test_results/knot_harbor_hard14_20261004_01/grading/jobs/001-oracle/topogym-knot-untying-hard-i00-pr__ysFovdT/artifacts/app/output/bridge_report.json)。现已进入隔离 verifier 的两遍独立核验，第一遍初态加载完成，评分后再由 bridge 提交同实例轨迹给 standard 服务。当前分数尚未产生，见[Harbor 运行状态](../../../runs/test_results/knot_harbor_hard14_20261004_01/status.json)。新实例须独立验收，不继承 hard14 的成功标签。

已启动每 30 秒一次的只读监控：[最新动作与评分状态](../../../runs/test_results/knot_harbor_hard14_20261004_01/monitoring/latest.json)、[监控存活状态](../../../runs/test_results/knot_harbor_hard14_20261004_01/monitoring/watch_status.json)。它绑定本轮调度器 PID／出生时间／命令，记录实际 Harbor 分数，运行结束后封存；不改模拟或 grader。首抓下降阶段的 [10 s 非阻塞采样](../../../runs/test_results/knot_harbor_hard14_20261004_01/diagnostics/early_runtime_sampling/summary.json)中，187/197 个主线程样本位于 IPC 耦合调用，只有 1 个样本位于 IK；该比例不外推为整程或纯 GPU 用时。

版本名称分别记录：`terminal_v5_fixed_contact_active_clearance_1mm` 是 Knot **终态释放判据的本地修订号**；Tooling v16 是本轮 Harbor 候选的工具版本；hard14 是此前本地候选运行编号。下文旧版原生成功和回放记录保留原范围。

**首遍正式回放的 0–3 s 桌面窗口已完成：1,201 个状态，零 findings。** [窗口记录核验](../../../runs/test_results/knot_oracle_20261003/hard14_replay/early_table_window_validation.json)确认连续状态链、原始前缀哈希以及两个同内核观察器的测量前缀一致。手指相对桌面顶面的最小垂直间隙约 0.4654 mm（tick 794）；旧反例 ticks 782–784 现在均有约 0.488–0.499 mm 正间隙。早期观察器已正常结束；整段观察器随后随 Harbor 路线调整停止，最后检查到 9.8425 s；此结论仅覆盖该窗口的原生启用机器人／桌面对，不替代后续完整 FEM／碰撞审计。

按用户授权，Knot 改为 `terminal_v5_fixed_contact_active_clearance_1mm`。这是本地任务判据的新版本，不能将其结果标为原始 v14 任务通过；v14 安全规则、动力学、绳体和碰撞模型保留。

- 夹爪及所有可活动连杆与绳体的释放间隙为 **1 mm**，取消统一 **5 mm** 要求。
- 世界固定底座允许正常边界接触，不要求额外间隙。部件身份使用 Genesis 沿关节祖先链计算的 `is_fixed`；连接在活动腕部上的固定关节／夹爪仍属于活动部件。
- 每个机器人部件都保留与完整绳体四面体的内部相交检查。外包盒或凸包不能证明分离时，继续检查原生凸实体、解析球或闭合凹网格；活动部件的正间隙使用面／顶点及边／边距离细化。真实穿透或无法判定均不能通过。
- **1 nm** 是几何比较的数值分辨率，不是允许穿透深度。影像只作补充，不能凭肉眼放行几何穿透。原有全 tick 接触／穿透审计保留，含固定底座；全过程无穿透资格仍待完整审计。
- 无投影交叉／重叠、落桌、IPC 完整性、无辅助抓持、速度 ≤1 mm/s、漂移 ≤1 mm，以及连续 0.5 s 稳定均保留。搜索也不再为已允许的底座接触追加搬绳动作。

[源码和验证计划](../../../runs/test_results/knot_oracle_20261003/hard11_native_launcher/launch_plan.json)已冻结；96 项相关 CPU 检查通过，包括 9 项新释放边界测试、120 对三角形距离与独立 FCL 的对照、原有碰撞／物理审计与命令安全检查。公共目标文字检查中的 Knot 部分通过，完整套件仍有既有 Claws 的 6 个失败，日志保留，未改动 Claws。

[两个实测状态的离线复核](../../../runs/test_results/knot_oracle_20261003/diagnostics/release_v5_saved_states/report.json)中，hard10 的 54.3925 s 样本原先 `robot_clear=false`、间隙下界为零；实际底座实体与 5 个可疑体单元精查均为分离，其余 35 个碰撞体间隙下界至少 38.696 mm。64.7125 s 样本也通过新释放检查。它们只证明单时刻释放条件，不代表连续稳定、完整回放或全过程无穿透已通过。

hard10 已在 91.425 s [主动停止并保留原版本证据](../../../runs/test_results/knot_oracle_20261003/hard10/release_policy_upgrade_stop.json)。hard11 从原始物理 S0 真实执行保存的 73.275 s 动作前缀，不恢复旧 Task 成功状态。[原生预检已通过](../../../runs/test_results/knot_oracle_20261003/hard11_preflight_retry01/report.json)：物理 world、机器人读数、控制目标和资产均逐项一致，并完成 10 个真实物理 ticks。旧证据中零接触向量的 `[]` 与 `(0,3)` 仅规范化空数组表示，其余数据不放宽比较。新评价 SHA 为 `182eb5736b649784`，与旧 `a4fbd7af273b0379` 分别保留；仅左右 `base_link` 被原生模型判为世界固定。

**hard11 已在 51.7925 s 取得本地 v5 原生成功**：[原生报告](../../../runs/test_results/knot_oracle_20261003/hard11/report.json)、[实际动作](../../../runs/test_results/knot_oracle_20261003/hard11/trajectory.npz)。共 2,072 actions／20,717 ticks，末动作执行 7 ticks 后正常成功终止；无需执行输入前缀中后续的搬绳动作。投影无重叠、落桌、松手、静止、漂移和机器人释放检查均通过，连续稳定 0.5 s。终态活动部件间隙下界 38.263 mm、最大绳速 0.8823 mm/s、最大漂移 0.4516 mm；底座的保守间隙下界仍为零，但实体复核未发现穿透。该终态结果不能替代全过程穿透检查。

[独立身份核验](../../../runs/test_results/knot_oracle_20261003/hard11/native_evidence_validation.json)已确认实际动作与输入前缀一致、计时及 SHA 一致、正式回放的 684 个源码文件与冻结源一致；首遍正式回放实际采集的物理 S0 再次与原始证据逐项一致。原生成功动作 SHA-256 为 `ed43224366dac37bebaba68cd53a34544fecafff9b23c55f08aa488ad2ccb4ea`。但首遍正式回放发现了下述真实几何反例，已主动停止，不能交付为全过程无穿透成功。

**hard11 的原生成功保留，但无穿透资格被反例否定。** [六个运动状态的完整几何抽查](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard11_motion_samples/report.json)在 10、20、27.5 s 发现桌面与右夹爪两侧手指内部相交；31.25、32.5、34 s 的三个样本无 findings。[原生碰撞网格顶点直接复核](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard11_table_overlap/report.json)检查到 tick 14,237，在 8,630 个 tick 找到严格位于桌面实体内部的手指顶点：首次为 6.7325 s，所查前缀最大深度为 28.42 s 的 **0.06535 mm**。这是浅重叠，不能归因于保守包络误报；该检查只覆盖两个手指与桌面，不构成全轨迹全碰撞审计。[主动停止记录](../../../runs/test_results/knot_oracle_20261003/hard11/replay_physical_rejection.json)保留了证据和停止原因，不把人工停止当成原生任务失败。

**hard12 增加了固定绳端的 2 mm 抬升，但早期下降仍有反例。** [冻结计划](../../../runs/test_results/knot_oracle_20261003/hard12_native_launcher/launch_plan.json)只改变 oracle 路径：抓紧后选中的 anchor 先抬高 **2 mm** 再拉绳，释放时不额外降低该手臂；左右手互换时跟随实际分配。`anchor_lift_m` 是可搜索的动作参数，保留 0、4、8 mm 备选，不增加桌面命令拒绝门槛。29 项 oracle CPU 检查通过，桌面诊断已用六个真实状态校验。实际运行在 1.875–2.025 s 的 5 个控制步末发现左手指与桌面的浅重叠，[直接顶点复核](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard12_descent_overlap/report.json)确认最大约 **0.11704 mm**；hard11 的相同时刻也存在该问题，早于新增抬升动作。hard12 已在首次拉绳阶段[主动停止并保留证据](../../../runs/test_results/knot_oracle_20261003/hard12/motion_physical_rejection.json)，未进入正式回放。

**hard13 已在 50.8575 s 取得本地 v5 原生成功，但正式回放发现步内浅重叠。** [冻结计划](../../../runs/test_results/knot_oracle_20261003/hard13_native_launcher/launch_plan.json)保留 2 mm anchor 抬升，并将 hard 抓取目标 `pinch_height_m` 设为 **+1 mm**；降低绳子准备释放时也保留该偏移，开爪后由真实物理落桌。30 项 oracle CPU 检查通过，覆盖左右分配和放下高度；原有桌面诊断源码与几何模块逐项不变，复用六状态验证。新增逐控制步接受动作／实际 tick 台账和原子部分轨迹快照，便于保留中途停止的实际执行。v5 释放、v14 安全、动力学和穿透判据不变。

[最终原生报告](../../../runs/test_results/knot_oracle_20261003/hard13/report.json)记录 **2,035 actions／20,343 ticks**，末动作执行 3 ticks 后成功终止；两次决策、零回退，交叉 **4→1→0**。终态连续稳定 0.5 s，活动部件间隙下界 **38.916 mm**、最大绳速 **0.9054 mm/s**、漂移 **0.4704 mm**，`robot_clear=true`。固定底座的保守间隙下界约 **0.001357 mm**，新规则正确接受这一正间隙，不要求 5 mm。[独立记录核验](../../../runs/test_results/knot_oracle_20261003/hard13/native_evidence_validation.json)确认完整动作、接受台账、实际计时、输入及 684 个运行源码文件一致。包括 S0 的 2,036 个控制步边界均无机器人–桌面 findings；这不覆盖步内或 FEM 穿透。两遍正式回放、首遍全 tick 审计及共享四路录像仍待完成，当前不能声明全过程无穿透资格。

**hard13 首轮完整抽绳和双手释放已完成**：29.25 s、1,170 actions／11,700 ticks，投影交叉数从 4 降至 1，随后进入第二轮两端抓取／拉开。该节点的[检查点与动作核验](../../../runs/test_results/knot_oracle_20261003/hard13/milestones/decision_1/validation.json)确认检查点、原生动作台账、部分轨迹和控制日志逐项一致，并保存独立副本。包括 S0 的 1,171 个控制步边界桌面检查均无 findings；这不覆盖步内或 FEM 穿透，仍不能作为完整无穿透或任务成功证明。

第二轮两端拉开已实测出现 **`planar_clear=true`、投影交叉为零**。[原生观察记录](../../../runs/test_results/knot_oracle_20261003/hard13/milestones/planar_clear_observation/observation.json)绑定实际控制步身份、动作台账前缀哈希及源码身份。此时仍未落桌／稳定，`task_success=false`；继续执行后续释放和稳定检查，不能把交叉清零作为成功结论。

[hard13 专用归档与四视角发布助手](../../../runs/test_results/knot_oracle_20261003/supporting/archive_helpers/release_v5_hard13/preparation.json)已按本轮实际搜索报告和接受动作台账完成适配。10 项 CPU 检查覆盖回退分支、末动作不足一个完整控制步、动作／时序不一致和记录缺失；实际前 481 actions／4,810 ticks 的独立副本与台账逐项一致。这些仅是归档完整性检查，不证明解结或无穿透。缺少完整成功、两遍正式回放或物理审计时，归档与发布均会拒绝执行，当前未创建成功归档或视频。正式归档前还会核对录像回放的物理 S0、完整 tick 数据哈希及新规则身份，保存独立副本。

末态哈希一致性按 v14 验证器仅作诊断：两遍必须都成功，但不要求 GPU 求解产生逐位相同的最终状态。两遍由独立于搜索的新回放进程执行，在该进程内分别恢复初态；完整物理审计及四路录像覆盖第 1 遍。

hard13 首遍正式回放的[独立初态核验](../../../runs/test_results/knot_oracle_20261003/hard13_replay/independent_preflight_validation.json)已通过：实际采集的物理 S0、机器人和控制目标与原始证据逐项一致，684 个回放源码文件与冻结快照相同。[工作进程身份](../../../runs/test_results/knot_oracle_20261003/hard13_replay/verified_process_identity.json)也已核对。完整动作 SHA-256 为 `adc44ddd9e5b7c251c7d3cb7f2dd1f0ecfb0e52e203644a373ac7a0298d9035c`；此预检不等于两遍回放完成或物理审计通过。

hard12 的[原生初态预检](../../../runs/test_results/knot_oracle_20261003/hard12/preflight.json)已通过：所有物理 world 字段、机器人读数、控制目标和资产与原始 S0 相同，评价 SHA 仍为 `182eb5736b649784`。[运行身份核验](../../../runs/test_results/knot_oracle_20261003/hard12/verified_process_identity.json)确认实际 684 个源码文件与冻结快照一致；相对 hard11 仅修改两个 oracle 文件及对应 CPU 测试。hard13 也已通过[相同物理 S0 预检](../../../runs/test_results/knot_oracle_20261003/hard13/preflight.json)及[684 文件运行身份核验](../../../runs/test_results/knot_oracle_20261003/hard13/verified_process_identity.json)，初段接受动作／实际 tick 与部分轨迹核对一致。这些预检不代表新动作或完整任务已经通过。

hard13 的早期动作诊断已有实测结果：[1.7–2.2 s 下降段](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard13_early_descent/report.json)的 21 个控制步末无桌面重叠 findings，左手指最小顶面间隙约 0.01223 mm；[6.75–7.4 s 拉绳段](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard13_early_pull/report.json)的 27 个控制步末也无 findings，右手指间隙至少 2.205 mm。它们表明两处修正在已观测时刻有效，不能排除控制步内或后续阶段的穿透。10 s [无暂停性能采样](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard13_runtime_sampling/summary.json)中，83.8% 样本位于 IPC 耦合推进，5.1% 位于新增桌面几何诊断；此比例仅覆盖首次抓取收敛片段。

正式首遍回放的[早期逐 tick 桌面检查](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard13_early_replay_table/report.json)已覆盖 0–2.5 s 的全部 1,001 个 tick，发现 **782／783／784 三个 tick（1.955–1.960 s）** 的左手指与桌面内部重叠。[独立原生网格顶点复核](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard13_descent_overlap/report.json)确认最大深度 **3.4375 μm（0.003438 mm）**；三个状态都在控制步中间，解释了控制步末检查为何没有 findings。这是真实但极浅的几何反例，不能作为全过程无穿透成功发布。已[主动停止回放](../../../runs/test_results/knot_oracle_20261003/hard13/replay_physical_rejection.json)，原生成功结果及未完成的回放／录像证据保留；人工停止不算原生任务失败。

**hard14 修正已启动。** 仅将 oracle 抓取／放下目标从 +1 mm 调至 **+1.5 mm**，保留 2 mm anchor 抬升，原生安全、物理及释放规则不变。新增只读原生状态订阅，在第一段抓取的 **0–3 s** 检查每个已提交物理 tick，随后取消订阅；仍保留全程控制步末诊断和成功后的正式逐 tick 审计。回溯或不连续只会结束这段诊断并如实标记，不拒绝搜索候选。30 项 oracle CPU 检查通过；[新观察器的实际状态验证](../../../runs/test_results/knot_oracle_20261003/hard14_native_launcher/monitor_validation.json)覆盖 hard13 的 1,001 个 tick，输出与原观察器逐字节一致，检出全部三个反例，且输入状态未改动、到达窗口终点自动退订、回溯不拒绝搜索。完整解结路径仍待 hard14 真实运行验证。

hard14 的[原生初态预检](../../../runs/test_results/knot_oracle_20261003/hard14/preflight.json)与[实际运行身份核验](../../../runs/test_results/knot_oracle_20261003/hard14/verified_process_identity.json)已通过：原始物理 S0、机器人、控制目标及资产一致，实际 684 个源码文件与本轮冻结源相同。

[默认 home 起步身份](../../../runs/test_results/knot_oracle_20261003/hard14/home_start_validation.json)也已直接核对：实际 S0 的双臂关节、两指位置、零关节速度和持有目标均逐项等于冻结的 ALOHA home 配置。正式录像仍待回放采集完成，届时还需核对首帧与 S0 的状态映射及四视角连续性。

**hard14 原生前 3 s 的桌面诊断窗口已完整结束：1,201 个连续状态，0 findings。** [窗口与动作身份核验](../../../runs/test_results/knot_oracle_20261003/hard14/milestones/early_tick_window/validation.json)确认每个 tick 的时间、分支、父状态以及前 120 个实际接受动作一致，并保存独立副本。该窗口中手指相对桌面顶面的最小垂直间隙约 **0.4654 mm**（1.985 s）；旧反例对应的三个 tick 现在约为 **0.488–0.499 mm** 正间隙。观察器已按计划退订，原生执行继续抬绳。这些是初始分支的桌面诊断及记录一致性结果，不是后续路径、FEM 或正式回放的无穿透资格。

**hard14 首次抽绳及释放已在 29.275 s 完成，交叉数 4→1，零回退。** [实际动作前缀核验](../../../runs/test_results/knot_oracle_20261003/hard14/milestones/first_withdrawal/validation.json)确认 1,171 个动作／11,710 ticks 与原生接受台账逐项一致，1,172 个控制边界桌面记录无 findings，并保留报告、中心线、原始部分轨迹和提取前缀的独立副本。第二次决策继续两端整理，约 42 s 已观测到零交叉及 `planar_clear=true`，并[保留实际指标快照](../../../runs/test_results/knot_oracle_20261003/hard14/milestones/planar_clear_observation/observation.json)；仍需放绳、撤手及停稳。这是当前搜索路径的中间结果，仍可能被后续搜索修订，不代表原生成功或完整逐 tick／FEM／回放资格。

[hard14 归档／发布准备](../../../runs/test_results/knot_oracle_20261003/supporting/archive_helpers/release_v5_hard14/preparation.json)已适配本轮身份，10 项动作台账 CPU 检查及前 17 个真实动作／170 ticks 的独立副本核对通过。缺少两遍成功回放或完整物理资格时，两个发布入口均拒绝执行；未创建成功归档或视频。还为正式首遍回放挂接了相同源码的只读 CPU 观察器，等待采集后核对前 3 s 的逐 tick 桌面几何，不额外运行模拟。

另已挂接[整段正式回放桌面观察器](../../../runs/test_results/knot_oracle_20261003/supporting/hard14_full_table_watch/validation.json)，从 S0 跟随已写出的全部 tick，直到采集封存或所属进程退出。它在真实 11 状态 hold 采集上确认窗口完整且任务未成功，在 hard13 的 1,278 状态失败前缀上复现全部三个穿透反例，前 1,001 行测量和反例位姿与旧观察器逐字节一致。它只读取原始几何和位姿，不改变模拟、不自动停止运行，也不代替完整 FEM／碰撞审计；当前等待 hard14 原生成功后的首遍回放。

正式视频元数据计划保留复现实例、实际动作、冻结源码、审计报告、静态碰撞几何及帧映射的真实副本；完整逐 tick 采集继续保存在独立主归档中，并在视频发布前按主归档清单逐文件复核。元数据同时保存主归档清单及其哈希，不再制作第三套大体积状态数组副本。按旧实测采集推算，约 50.86 s 的首遍状态需约 47 GiB；实际执行长度及复制前空间仍需最终检查。原始运行和失败证据均保留，当前没有发布成功视频。

旧 hard11／hard13 归档助手保留为历史材料；因已发现物理反例，不执行成功发布。当前 hard14 助手绑定本轮实际动作、源码和完整审计结果，不能复用旧运行的资格标签。

当前调度器：`/tmp/knot_hard14_supervisor.py`；[实时状态](../../../runs/test_results/knot_oracle_20261003/background_status.json)。镜像固定为本机 `0.2.13-dev`，不代表官方 `0.2.12` 已验证。下面 hard10 及更早的 5 mm 记录保留历史含义。

## 冻结实例 oracle 交接与整合（2026-10-03）

已导入用户提供的 `knot_untying_oracle_artifacts.tar.gz`：原始运行、三档 IPC 存档及日志位于
`runs/test_results/knot_handoff_20261003/runs/knot_oracle/`，
[导入清单](../../../runs/test_results/knot_handoff_20261003/import_manifest.json) 记录压缩包与每个文件的 SHA-256。
代码归入 [planning/knot_untying](../../../topogym/planning/knot_untying/README.md)，
执行入口为 `scripts/oracle_runners/run_knot_oracle.py` 和 `run_knot_branching.py`。

| 档位 | 已收到的物理证据 | 本轮状态 |
|---|---|---|
| easy | `easy05` 原生成功，575 actions、5,744 ticks、14.360 s；已有正式实例新进程回放成功日志，exact=true | 原证据已核验导入；单次回放不证明重复确定性 |
| medium | `medium03` 原生成功，1,927 actions、19,268 ticks、48.170 s | 正式初态精确恢复；本轮首遍跑完全部动作但 `success=false, episode_end=null`，第二遍按用户要求取消，原因待查 |
| hard | `hard01` 部分执行 53.075 s，4→3→1，仍有紧卷；没有完整成功 | `hard13` 已取得本地释放 v5 原生成功（50.8575 s），但正式回放检出最大 3.4375 μm 的真实步内桌面浅重叠；已主动停止。`hard14` 修正抓取高度并增加原生早期逐 tick 检查，完整物理资格及录像待验。`hard11` 原生成功但存在手指与桌面浅重叠，`hard12` 首次下降仍检出旧问题；这些旧失败证据保留 |

medium 首遍返回值见 [原生结果](../../../runs/test_results/knot_oracle_20261003/medium_first_replay_result.json)。
原命令请求两遍；第一遍完成后在第二遍初态恢复期间暂停，通过只读进程检查保存第一遍
`Session.replay` 的完整返回值，并由原生 session 日志交叉确认。随后停止进程给 hard 释放显存；
不能将进程的人工停止码当成首遍物理失败，也不能称本轮回放通过。末尾静置余量与轨迹偏差尚未区分。

此前交接回放与 hard06 使用已冻结工作区源码、`ghcr.io/luigivamper/rcb-topogym:0.2.6-cu128`、
Genesis 1.2.1／libuipc build `292c98c3`。日志与快照在
[本轮验证目录](../../../runs/test_results/knot_oracle_20261003/)。原交接使用镜像 0.2.3，
结果不自动移植给新环境；新进程回放单独记结果。当前源码已启用 `goal_complete=True`，
绳接触摩擦平滑为 1 mm/s；导入时旧 `tasks/` 存档与此不同，所以当时使用交接的重建实例。
现已合入 v14 新实例，后续入口不再默认选择交接存档，版本差异见下节。
oracle 搜索修改没有改变任务判据、绳径、有效体积要求或旧 benchmark 包。

执行保持实例时序：2.5 ms tick × 10、IPC 子步 1、纯摩擦抓持、默认 ALOHA home 起步。
easy 抬起 s=224 mm 的上股 25 mm、沿 −x 搬运 95 mm；medium 远端固定、删交叉再两端拉开。
夹爪命令是实际开口宽度，默认 **5 mm**；两端拉开的抓点离端头 **35 mm**。
旧运行中零开口曾压翻体单元，medium 离端头 15 mm 的一次尝试也失败；当前搜索不把这些经验当成参数禁令，保留失败证据并按原生规则及独立几何检查验收。
hard 的物体路线经验是完整拉 0.55 m，不能在第一次交叉减少时即停止。

本次补全了：实际 tick 计时、原生终止立即收尾、失败退出码、动作前缀存盘、完整决策回溯、
续跑前的实例／tick／绳形核对，以及正式 RGB 实例的新进程 replay 检查。
交叉已清零但原生稳定窗口未完成仍判未解开；分支搜索成功仍须重新回放。
复现和实例重建命令见 [oracle README](../../../topogym/planning/knot_untying/README.md)。
这批证据不扩展到其他 seed、网格／时间步收敛或逐子步机器人禁碰资格；本轮没有新录像。

## v14 / 0.2.12 对当前 hard 的影响（2026-10-03）

本地合并后的代码与 **hard05 实际执行快照**逐文件对比：Knot Task、基础 Task、
终态／稳定检查、Env、SimulatorConfig、IPC articulation 初始化及放宽后的分支搜索均相同。
因此这次更新没有给当前 oracle 新增固定终点或参考路径要求；主要变化在 `rcb_topogym.py` 的运行时规则。
[完整对比与实例哈希](../../../runs/test_results/knot_oracle_20261003/version_audit_v14/comparison.json)保存了核对范围。

| 变化 | 对 Knot hard 的影响 |
|---|---|
| R2 软体异常持续时间 | 原快照体积比 ≤0 当 tick 失败；v14 连续 0.25 s（100 ticks）才失败，短暂异常判不可评估、不能积累成功。原生 IPC invalid 仍立即失败。后续按用户“原生规则优先”要求，逐 tick 体积异常保留诊断，任务结论按原生 R2；独立实体穿透检查另行判定 |
| R3 手臂力矩上限 | 每臂六关节上限为 `[12.9, 80, 59, 12.9, 35, 17.5]` N·m，并与模型原上限取较小值；夹爪驱动力不变。可能改变接近、抓稳和抽绳时的跟随误差，需要新环境实测 |
| R4 桌面命令保护 | 按夹爪碰撞网格限制 arm target，最低允许桌面下 **15 mm**；会裁剪部分命令，但不是实际无穿桌检查 |
| R1 / R5 | R1 针对 rigid-task 接触判据，不直接用于 Knot FEM。R5 的每步 0.04 rad 限速及 0.5 rad IK 跳变拒绝位于 standard 服务；当前 privileged Session 的直接 JOINT_ABS oracle 不经过该服务 |
| cloth-contact 与 instability guard | 前者修复 PBD 刚体接触，后者检查 `particles` 速度；Knot 绳位于 FEM 状态，不能把这两项当作新增绳防穿模保障 |
| 新冻结实例 | 三档资产、模拟配置与 IPC 身份元数据相同，但 settled state 的数组与原生 dump 已重建；hard 初态 SHA 从 `90fc4a2f1ae464ba` 变为 `a4fbd7af273b0379`。hard 绳顶点最大位置差约 9.0 nm，数值虽小，仍属于不同冻结实例 |
| 步耗时文案 | hard 新文案为 unloaded 1.7 s / shared 3.3 s 每控制步；物理仍是 2.5 ms × 10、40 Hz。文案更新不使本机现有运行自动加速，按实际日志估时 |

`hard05` 已为控制器修复主动停止；`hard06` 当时使用 **0.2.6 + 冻结源码 + 旧 hard 初态**，后也保留证据并停止。
不会将其结果重标为 v14 成功。0.2.12 镜像拉取返回 registry `denied`；当前已用本机固定
0.2.13-dev 镜像运行 v14 工具和精确新初态，见下方 hard07 / hard08 记录。此组合正在真实执行，正式新进程回放仍待原生成功后进行。
后续新运行默认选择当前任务包实例，历史重放须显式给出旧实例并使用对应源码／镜像，避免新规则混用旧默认输入。
本次通过 25 项安全规则 CPU 测试和 18 项 Knot 回归；不代表新力矩／桌面保护下已完成真实抓绳。

## hard04 / hard05 的初次限制检查与放宽（历史）

本节保留 hard04 / hard05 时的限制检查和证据；当前 hard08 已进一步放宽，见下方“hard07 / hard08：原生规则优先、空间搜索与跟踪修复”，不沿用下表旧搜索预算。本节只核对 Knot 的 easy / medium / hard；初始检查依据 `hard04` 冻结源码，随后按用户要求放宽搜索并重启为 `hard05`。
**三档原生 Task 的固定 XY 终点限制为 0，参考路径匹配限制为 0。原搜索的 2 条操作末尾硬剪枝已放宽，新运行 `hard05` 使用该策略。**
源码哈希和 CPU 判据探针见 [检查记录](../../../runs/test_results/knot_oracle_20261003/constraint_audit/predicate_probes.json)。
检查中 48 个合成终态候选覆盖直绳／弯曲绳、平移／旋转和不同机器人远离位置，均通过候选判据；
6 个无效体积、运动、低于桌面、未释放或机器人过近的反例均未通过。
这些输入使用合成表面环和诊断字段，只证明判据行为，不构成真实 FEM 执行或无穿模证明。

| 层次 | 当时限制 | hard05 当时如何处理 |
|---|---|---|
| 原生终态 | 不指定绳端坐标、XY 目标区、机器人回 home 姿态或动作阶段顺序；要求无投影交叉／重叠、贴桌、松手、机器人离绳至少 5 mm，速度不超过 1 mm/s、漂移不超过 1 mm，稳定 0.5 s | 保留完成语义；弯曲但无重叠的绳也可以完成。不满足时通常继续等待，并非立即失败 |
| easy 路线 | 固定材料坐标 `s=.224 m`，抬 25 mm、沿 −x 搬运 95 mm；当前 carry 只有一个默认候选 | 这是求解器配方，不是评分规则；若该配方失效，可扩展抓点和搬运方向候选 |
| medium / hard 路线 | 按较短自由端选首个下穿交叉；竖直下夹，拉绳阶段保持抓取方向；主要只有删交叉／两端拉开两类动作 | 已允许同一节点交替尝试两类动作的参数候选，旧规则仅决定优先级；抓点和姿态仍沿用已有物理动作 |
| 原分支硬剪枝 1 | **一次完整操作后**交叉数不减少（`after >= before`）就回退 | 已改为默认允许连续 2 次未刷新本分支最低交叉数的操作；下一次若取得新低可继续。`4→5→4` 不刷新预算，可用 `--max-nonprogress-decisions` 调整上限 |
| 原分支硬剪枝 2 | 两端拉开后仍有材料跨度小于 **12 cm** 的交叉圈就回退 | 已改成 `tight_curl_after_spread` 诊断标记，不再据此回退，允许继续尝试恢复 |
| 搜索与等待预算 | 默认最多 8 层决策、30 次候选；交叉清零后最多再等 10 s | 预算耗尽只能说明本求解器尚未找到解，不能证明其他路径失败 |
| 新进程回放 | 精确核对**初始实例**，执行提交动作及 tick；不要求末态 SHA 与原运行一致，也不检查是否属于已知路线；动作结束后不自动追加静置 | 保留证据身份检查。需要更长静置时显式补动作、重新验证；medium 首遍未成功的原因仍未确定 |
| checkpoint 续跑 | 前缀回放后，绳形／关节必须与该 checkpoint 接近（0.2 mm／0.2 mrad） | 这是恢复控制器状态的前提，不是要求最终回到该位置；保留 |

本轮放宽只改搜索剪枝和动作类别候选，没有修改 Task、绳模型、碰撞参数或正在执行的
`hard04` 快照；不能通过放宽体积有效性、减小绳径或容许穿透来获取成功。
`branching.json` 记录策略版本 `bounded_nonmonotonic_v1`、每次操作的诊断标记和未进展计数。
计数由有效决策前缀重算，回溯和旧 checkpoint 续跑不会带入已丢弃分支的计数。
17 项 Knot CPU 回归通过，覆盖交叉数不变／增加后成功、小紧圈恢复、振荡预算、物理失败拒绝和完整回溯；
这些结果不代表放宽后的策略已经完成新的物理执行。原始判据检查记录保留修改前源码哈希。

用户要求重跑后，`hard04` 保留日志、源码和已有检查点，标为主动取消而非物理失败；
其第一个动作原语尚未结束，未完整写出这段执行的动作前缀。
`hard05` 从相同 hard 冻结初态重新开始，沿用 `hard04` 的物理／几何／资源源码，
只替换 `branching.py`、`cli.py` 和只读回放指标观察器 `replay_audit.py`。
[启动身份记录](../../../runs/test_results/knot_oracle_20261003/hard05_launcher/launch_plan.json)保留旧运行身份。
该轮曾由 `supervisor_v4` 接管，未因此重启物理执行，见[接管记录](../../../runs/test_results/knot_oracle_20261003/hard05_physics_replay_launcher_v2/adoption.json)。
发现下面的命令高度缺陷后主动停止，取消记录和全部旧证据保留；其待回放队列未执行。
[实时状态](../../../runs/test_results/knot_oracle_20261003/background_status.json)追踪当前 hard 轮次；hard06 的历史证据保留。

首个完整操作的[动作与检查点副本](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/decision_1/manifest.json)
已单独保留：1,192 actions、11,920 ticks、29.8 s，完整拉出 0.55 m 后释放撤手，交叉 4→1。
末次中心线采样 29.625 s 中，剩余局部圈对应约 27.0 cm 材料跨度，随后自动进入两端拉开；
这是实测部分流程与中心线诊断，不是完整成功或体网格无穿模证明。

第二轮已完成两端拉开与释放：43.62 s 的采样日志首次记录零交叉，49.2 s 时完整前缀为
1,968 actions／19,680 ticks，原生 `planar_clear=true`、`on_table=true`，非局部平面最小间距约 16.4 mm。
此时最大速度约 2.14 mm/s，高于 1 mm/s 阈值，`quiet=false`、稳定时间为 0。
[第二轮完整前缀](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/prefix_19680_6883325517a5/manifest.json)
已按动作数、tick 数和复制前后哈希核对保存；它仍不是完整成功或无穿模证明。
随后按原策略静置至 59.225 s，交叉持续为零，但未触发稳定成功，搜索回退到 29.8 s 并改试退绳。
[该分支的静置与拒绝记录](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/first_zero_crossing_settle_rejected.json)
保留完整日志；49.2 s 后没有完整详细指标落盘，因此不能断言最终仍只差速度。
后续静置阶段已加独立只读指标采样，保存实际阶段、分支、最后已提交 Task tick 和原生判据。
诊断会短暂停顿后恢复同一进程，不注入代码或写进程内存；首次有效读取发生在回退后，不用于解释上一分支。

随后替代的退绳候选在 40.305 s 被原生 `rope_volume_invalid` 拒绝，
[失败日志](../../../runs/test_results/knot_oracle_20261003/hard05_milestones/second_candidate_volume_invalid.json)
已保存，失败动作没有纳入当前有效前缀。日志未保存失败 tick 的完整 FEM 数据，不能再细分为体积翻转或其他原生 IPC 无效。
搜索随后从 29.8 s 检查点尝试 50 mm 抓点，但在此候选完成前因下述命令缺陷主动停止，不能将人工停止解释为该候选的物理失败。

### hard06：修复低于桌面的命令并从初态重跑

对零交叉前缀全部 1,968 条动作，按原生 float32、限位裁剪和开口转换做独立 CPU FK 检查，
发现第一次释放目标最低约低于桌面 14.93 mm，第二次释放约 17.76 mm。
这是**命令几何**，不是实际物理穿透深度，见[诊断报告](../../../runs/test_results/knot_oracle_20261003/diagnostics/first_zero_command_kinematics/report.json)。
根因是水平移动每段从下沉的实测 TCP 重设高度，释放又减去最初的抬升量。
因此已[主动停止 hard05](../../../runs/test_results/knot_oracle_20261003/hard05/cancellation.json)，保留旧证据，不续跑其动作前缀。

控制器现保持计划的搬运高度，释放不低于绳在桌面上时的夹取高度；两臂路径长度不同时，短路径等待长路径完成。
每条提交命令按原生夹爪碰撞体的保守外包络检查桌面间隙，至少 0.5 mm；不满足则在推进前拒绝。
IK 只向上修正 Z 来满足这个规划余量，不放宽实际穿透、体积或成功判据。
每 8 控制步及终止时保存完整原生指标；被拒候选在回溯前保存完整动作前缀、终态指标和共享模块的最后一 tick 证据。
最后一 tick 记录不会标成全程碰撞证明。

18 项 oracle、5 项命令安全、10 项几何、11 项记录、6 项证据审计 CPU 测试通过。
真实模型 FK/IK 抽检 11 个旧危险姿态：全部原命令被拒，修正后包络间隙均至少 0.5 mm，
见[验证记录](../../../runs/test_results/knot_oracle_20261003/hard06_launcher/command_guard_native_fk_validation.json)。
这些是无物理积分的验证，不能证明修正后的实际抓取可行或无穿模。

`hard06` 在至少 10,000 MiB 空闲显存持续 30 s 后，于 23:25:34 UTC 启动；只在系统 RAM 达到 90% 时停止本轮工作，不停止其他任务。
其[冻结启动方案](../../../runs/test_results/knot_oracle_20261003/hard06_launcher/launch_plan.json)只覆盖 8 个控制／审计文件，
另 653 个运行文件与 hard05 相同；Task、物理、几何、时序和输入实例保持原字节。
从原始旧 hard 初态开始；原生成功后自动做两遍正式实例回放，首遍记录全 tick、四路共享录像并做独立碰撞审计。
当前尚无 hard 完整原生成功、正式回放或防穿模资格。

hard06 已实际完成首次闭合／夹紧并进入抬升，见[首次夹取记录](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/first_pinch.json)。
已封存的[早期抬升采样](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/first_lift_following.json)
中，左侧抓点绳中心升高约 20.4 mm，相对指垫接触点偏移仍不超过约 1.6 mm。
5.625 s／2,250 ticks 时已进入第一轮抽绳，尚无保护拒绝或原生失败。
这支持修复后仍能完成此次夹取和早期抬升，不代表完整抽绳、任务成功或防穿模资格。

hard06 第一轮退绳、释放和撤手已完整执行：30.0 s、1,200 actions、12,000 ticks，
拉出 0.55 m 后交叉 4→1，已进入第二轮两端拉开。动作前缀与决策 2 检查点的数组／tick 完全一致，
复制前后哈希核对通过，见[第一轮证据副本](../../../runs/test_results/knot_oracle_20261003/hard06_milestones/decision_1/manifest.json)。
此时原生最大速度约 0.877 mm/s，`quiet=true`，但 `planar_clear=false`、`on_table=false`，
仍未任务成功；命令保护未拒绝这一轮，也不能据此代替全程实际碰撞检查。

hard06 在第一轮释放／撤手阶段做了 30 s 非阻塞只读栈采样：594 个有效主线程样本中，
560 个（94.3%）位于镜像内 Genesis 的 `_ipc_world.advance()`，3 个（0.5%）位于 IK／FK／命令检查，
其余主要为状态读取和判据；另有 5 次采样读取错误。
这支持该窗口的主要耗时在原生 IPC 推进，不能细分 GPU 计算、同步等待或资源竞争，也不能外推为全程精确比例。
采样未注入代码或主动暂停 worker，见[原始栈与采样汇总](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard06_runtime_sampling/summary.json)。

后续检查发现 Genesis 原生 FK 会恢复 qpos 后重算实时 solver 的位姿字段，新版 tooling 的 `_ChainFK`
也明确规避了这个查询副作用。工作区已把命令几何检查改为只读 CPU 链式 FK，保留原生 IK；
1,968 个历史命令姿态加 100 个随机姿态与原生 FK 的最大位置差为 6.7×10⁻¹⁶ m、
最大角差为 1.1×10⁻¹⁵ rad，查询前后实测 solver 字段不变。
3 项链式 FK 合同检查、5 项命令安全及 18 项 oracle 回归通过，
见[真实模型对照记录](../../../runs/test_results/knot_oracle_20261003/diagnostics/static_command_fk_validation/report.json)。
此改动作为后续候选保存，**没有热替换 hard06 的冻结源码**；不能据 CPU 测试声称实际吞吐提升或物理资格通过。

另在 CPU 回归中复现了拒绝证据的目录冲突：子分支耗尽后，父分支用当前尝试总数命名，
会与最后一个子分支重名并中断搜索。工作区改为尝试开始时分配固定编号，父子失败前缀分别保存；
18 项 oracle 回归通过，包含真实临时目录写入和回退后继续找到解的检查，
见[冻结代码复现与候选验证](../../../runs/test_results/knot_oracle_20261003/supporting/rejected_evidence_id_candidate/validation.json)。
该修复尚未部署到 hard06；当前运行若触发此问题，会保留已有证据后再用修复快照恢复搜索，不将其报告为物理失败。

后续全 tick 记录还补了磁盘处理：原共享 writer 会每 tick 重存不变的单元连接表等大数组，
60 s 绳数据的两份副本估算就可能超过当前空闲磁盘。共享 `SegmentEvidence` 已增加默认关闭的
逐字段精确数组引用复用，Knot 回放启用；dtype、shape、C-order 字节均相同才复用，保留所有 tick 和字段，
仅缓存当前字段路径的上一值。原 decoder 直接读取，失败写入不会发布未提交数组引用。
5 项共享记录检查、11 项 Knot 记录检查和 6 项完整证据检查均通过，包括冻结回放快照中的复测。
[8-tick 编解码对照](../../../runs/test_results/knot_oracle_20261003/diagnostics/array_reuse_payload_validation/report.json)
使用实际绳拓扑和变化的测试位置／速度：解码字段逐字节相同，后续绳数据每 tick 从约 4.64 MB 降至 1.85 MB。
60 s 两份绳数据约 89 GB，未计刚体、录像及后续其他占用，仍不是容量保证。

[新的回放启动方案](../../../runs/test_results/knot_oracle_20261003/hard06_replay_array_reuse_launcher/launch_plan.json)
只在 hard06 快照上替换共享 writer 和 Knot 回放观察器，物理／任务源码不变，也未混入待验的 CPU FK 改动。
等待程序已绑定原 hard06 容器 ID；只有它退出且原生成功、完整动作文件存在后，才接管旧回放调度器。
目标目录为 `hard06_replay_array_reuse` 与 `hard06_collision_audit_array_reuse`，仍为两遍回放、首遍全 tick／四路录像及独立审计。
该 hard06 队列现已随迁移停止；hard07 使用新的独立调度器，实际完整回放资格仍待验证。

**防穿模仍有验收缺口。** `hard05` 原快照每 tick 检查 IPC 有效和体单元正体积，末态检查贴桌与机器人离开，
但这些不等价于全程网格无相交。`KnotIK.check()` 能检查机器人对桌面、同臂和双臂碰撞，
目前 `robot_oracle.py` 没有调用它；该函数本身也不包括形变绳的碰撞体。
抓点的中心线间隙、95% 材料跨度停止线和 5 mm 夹爪开口是预防措施，不能代替实际接触审计。
现有贴桌判据允许低于桌面至多 1 mm，这不是已经满足用户“无穿模”要求的证明，也不应继续放宽。
在扩展路线后的正式验收中，需要补充实际机器人／绳／桌面接触检查，并报告时间采样范围；
本轮 native success 或 replay success 均不能单独标成完整无穿模资格。

为补这部分证据，已接入可选的 `--physics-evidence` 回放观察器，复用共享数值证据 writer，
记录初态及每个物理 tick，不改变原生动作或时序。独立几何检查已覆盖体单元翻转和非相邻绳面自交，
现有 10 项几何检查、11 项记录合同检查与 6 项完整证据审计检查通过，均为 CPU 测试。
三角形算法与 FCL 的 600 组随机结果一致，新增 150 组实体凸体／四面体结果也一致；
覆盖物体完全包含、零间隙接触、瞬时翻转、记录缺失／篡改及 replay rewind 后分支编号不为 0 的情况。
hard 冻结初态的 40,769 顶点／174,085 四面体／47,376 表面三角形检查中，最小体积比约 0.9020，
未发现翻转或非相邻表面相交；这是**初态检查**，不能外推到执行全过程。
记录见 [初态几何诊断](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard05_initial_geometry_audit.json)。
带物理证据的回放与离线碰撞检查已接入成功后的队列，尚待实际物理运行验证。
两遍原生回放中首遍记录全部 tick，并通过共享 `RecordingSession` 保存同次执行的四路 Nyx 视频，
逐帧核对与数值证据的状态身份，结束后全量解码；第二遍只验证原生成功。证据保留 10 GiB 磁盘余量，
不足时明确失败，不截断后冒充完整。回放观察器采用独立快照，除 5 个审计入口／模块外，
656 个运行文件与 hard05 快照相同，见[启动方案](../../../runs/test_results/knot_oracle_20261003/hard05_physics_replay_launcher_v4/launch_plan.json)。
网格导出使用静态顶点和只读原生几何位姿，不调用会刷新 solver 顶点缓存的 `get_verts()`。
ALOHA 指尖另有 12 个球形碰撞体；球体采用按原生半径外扩至所有支撑平面都包住球体的多面体，
不能用内接三角网格凸包漏掉真实球面。BOX 使用解析角点，未知 primitive 拒绝认证。
独立检查使用实际机器人／桌面碰撞顶点的凸包外包络，逐个填充四面体检查分离，因此不会漏掉完全包含；
外包络重叠只表示不能认证，可能来自凹槽或接触，不据此声称确定穿透。刚体配对沿用原生启用列表，
检查所有记录时刻及原生刚体接触深度；不覆盖相邻绳面折叠、禁用刚体配对或 tick 之间的连续 CCD。

## hard07 / hard08：原生规则优先、空间搜索与跟踪修复

用户要求优先遵循 v14，并尽量减少 oracle 附加限制。hard06 第二轮两端抓取曾在
32.175 s 被额外 +0.5 mm 命令保护拒绝；退绳替代分支还出现过原生体积无效。
[停止记录](../../../runs/test_results/knot_oracle_20261003/hard06/cancellation_native_rules_migration.json)
保留最后指标、搜索状态、此前完整第一轮和各拒绝前缀，不将人工停止计为原生物理失败。

hard07 的[冻结方案](../../../runs/test_results/knot_oracle_20261003/hard07_native_launcher/launch_plan.json)
使用 v14 任务工具（SHA `062af946…`）、v14 hard 初态 `a4fbd7af273b0379`，以及本机
`0.2.13-dev-cu128` 镜像（ID `a54e0a324bc2…`）。官方 0.2.12 仍未安装；该组合不冒称官方镜像验证。
[真实预检](../../../runs/test_results/knot_oracle_20261003/hard07_preflight/report.json)
确认初态 exact、R2 100 ticks、R3 ALOHA 力矩上限和 R4 −15 mm 均已安装；一个控制步正常推进，
8 个竖直／偏转／倾斜抓姿均有 IK 解。这不是实际抓取或完整解结成功。
初态加 10 个物理 tick 的[几何审计](../../../runs/test_results/knot_oracle_20261003/hard07_preflight/contact_audit/audit.json)
完整，无穿透发现或 unresolved；最小体积比约 0.9020。因为任务未完成，qualified=false 正确保留。

hard07 的 `native_rules_spatial_search_v2`（hard08 继续沿用以下规则）：

- 有 v14 原生桌面保护时取消 oracle 的 +0.5 mm 门槛及自动向上修正；原生实际接受的目标成为后续 IK 种子。
- 默认关闭交叉数停滞剪枝，紧卷仍仅诊断；有限运行预算扩大为 16 层、128 次候选。
- 候选搜索两端、交换手臂、不同抓点和固定点、抓姿偏转／倾斜、不同拉动角度以及带抬升／侧移的路径。
- 抓点改为三维空间排序，拥挤点不再因二维投影余量不足直接失败；取消默认 95% 材料跨度停止线。
- IK 当前种子失败后尝试 home 和两个关节扰动种子；接受残差为 0.5 mm／0.01 rad，原生关节限位不变。
- 零交叉后等待未成功时继续撤手、重新落绳或拉开；完成仍只能由原生 task_success 决定。
- 抬升不再硬限 100 mm、拉开比例不再硬限 0.95、闭合宽度不再硬限绳径；输入必须有限且满足参数语义，机器人范围交原生裁剪。

接触审计也已调整。BOX 和原生凸网格用实际凸实体，球用解析半径；闭合凹网格在包络碰撞后
进一步检查实际表面和包含关系。边界接触不计为穿透，确认内部相交才记录 penetration；
未支持或缺失几何明确记录 unresolved，不能因此声称完整合格。几何比较分辨率为 1 nm。
绳自接触由非相邻表面及其相邻实体单元细分；仍不覆盖共享顶点面的自折叠、无表面接触的完整
自包含、禁用刚体配对或 tick 间连续 CCD。体积异常每 tick 保留，是否因持续时间失败由原生 R2 决定，
不另加“一个 tick 异常即任务失败”。原生刚体接触深度保留为诊断，不与精确实体相交混为同一测量。

hard07 的退绳和两端抓取候选都在接近结束的 1.0 s 遇到 IK 不可达，未触发额外桌面拒绝。
[实测状态与 CPU 重建](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard07_approach_ik/report.json)
表明左腕相对命令尚差约 1.56 rad；在这个实际位置强制最终朝向不可达，但预抓位本身可达。
另一夹爪朝向同样可达，并把 home 到预抓位的最大单关节转动从 3.14 rad 降为 1.77 rad。
该替代抓姿计算使用最后一份 0.825 s 中心线，不是未保存失败目标的精确重放，也不代表真实抓取通过。
hard07 已按[停止记录](../../../runs/test_results/knot_oracle_20261003/hard07/cancellation_approach_tracking.json)保留失败状态和动作。

hard08 使用[新的冻结源码](../../../runs/test_results/knot_oracle_20261003/hard08_native_launcher/launch_plan.json)，
策略 `native_rules_tracking_search_v3` 对两个可达夹爪朝向按实测关节转动排序，并在接近结束后
最多等待 4 s，待预抓位误差在 20 mm／0.1 rad 内再下降；超时仍尝试 IK，不额外判抓取失败。
接近时间和等待预算可配置，原生 R2／R3／R4、摩擦抓取和完成判据不变。
33 项相关 CPU 回归通过；旧版公共图像／初态预检不作为新控制器完整物理成功的证据。
实测接近后额外等待 0.05 s，右／左 TCP 距预抓位约 13.35／15.48 mm、姿态差约 0.083／0.091 rad，
通过下降转换条件，并已真实下降至 1.625 s／650 ticks、无回溯，见[首段下降证据](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/first_descent.json)；尚不代表抓取完成。该段 10 s [只读采样](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_runtime_sampling/summary.json)
的 199 个有效样本中 198 个在原生 IPC advance，采样不区分 GPU 计算、共享竞争或同步等待。
新的 hard08 证据／四路视频归档助手已完成语法检查和缺证据拒绝检查；尚未执行正式归档或发布。
随后已完成首次定位、闭合和夹紧，并进入退绳。3.02–4.42 s 的[实测抬升采样](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/first_lift_following.json)
显示左侧抓点上升 25.4 mm，采样接触偏差最大约 1.24 mm，右端仍固定；这支持早期抓取跟随有效。
这些是中心线和计划夹爪接触点的舍入采样，不构成全轨迹碰撞或完整解结证明。
第一轮退绳已经完整完成：29.125 s、1,165 actions／11,650 ticks，拉出 0.55 m 后释放两端并退开，投影交叉 4→1，无回溯、无原生 episode failure；第二轮两端拉开已开始。只读[前缀观察器](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/watcher_plan.json)已保存[完整第一轮动作前缀](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/prefix_11650_78299a35c0ad/manifest.json)。
[检查点核对](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/decision_1_validation.json)确认前缀 action／tick 数组与第二轮检查点逐项相同，文件哈希一致；命令保护归原生 Session，R4 为 −15 mm，额外 oracle 桌面余量为 null。此处证明一轮操作及其证据完整，不表示原生任务成功或全 tick 无穿透资格。
第二轮两端抓取已完成位置收敛，31.425 s 进入闭合，未出现旧的额外桌面保护拒绝，见[该阶段实测记录](../../../runs/test_results/knot_oracle_20261003/hard08_milestones/second_grasp_convergence.json)。它使用新的初态／运行版本，不是 hard06 失败命令的对照重放；第二轮完整结果仍待验证。

随后 hard08 在 37.625 s／15,050 ticks 的第二轮拉开阶段收到外部 SIGTERM，监督进程和容器已退出，见[中断记录](../../../runs/test_results/knot_oracle_20261003/hard08/interruption_sigterm.json)。当时仍为一个交叉、无原生失败；不能把进程终止计为解法失败。用户确认并非其主动停止，并要求继续。
`hard08_resume01` 已按[恢复方案](../../../runs/test_results/knot_oracle_20261003/hard08_resume01_native_launcher/launch_plan.json)完成从精确初态 `a4fbd7af273b0379` 的首轮真实回放：控制器与原 hard08 冻结源码逐字节相同，1,165 actions／11,650 ticks 后中心线最大坐标偏差为 0.09750 mm、关节最大偏差为 1.610×10⁻⁷ rad，均通过 0.2 mm／0.2 mrad 容差，见[恢复检查结果](../../../runs/test_results/knot_oracle_20261003/hard08_resume01/resume.json)。日志确认 `RESUMED at 29.125s: 1 crossings`，已进入第二轮两端抓取；没有直接设置中断姿态。
原续跑循环仅打印开始／结束；[外部只读计数采样](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_resume01_progress_probe/plan.json)曾按实际容器、PID、创建时间和源码哈希绑定当前 worker，在不暂停模拟的情况下连续读取两次 Session 已提交动作数／tick／时间，核对一致性。观察器已在恢复检查通过后自动结束，见[观察器结果](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_resume01_progress_probe/watcher.json)；其最后一次计数仅属历史恢复诊断。后续进度直接读取 [native_progress.json](../../../runs/test_results/knot_oracle_20261003/hard08_resume01/native_progress.json)，计数采样不构成完整物理证明。
恢复使用的控制器历史日志包含原第一轮采样；最终物理证明和视频必须来自随后的一次完整连续正式回放。

恢复后第二轮已完成抓取收敛、夹紧和抬升，持续拉开超过原中断点；约 41.82 s 的日志首次记录交叉 1→0。42.425 s／16,970 ticks 的原生指标为 `planar_clear=true`、`on_table=false`、`quiet=false`、`failure=null`，见[清零阶段证据](../../../runs/test_results/knot_oracle_20261003/hard08_resume01_milestones/first_zero_crossing.json)。此时仍在抓持，程序继续执行零交叉后的额外拉开、释放和终态整理；不能将交叉清零当作完整成功或无穿透证明。

第二轮于 47.45 s／1,898 actions／18,980 ticks 完成两端释放并退开，[完整前缀](../../../runs/test_results/knot_oracle_20261003/hard08_resume01_milestones/prefix_18980_67cb85e294eb/manifest.json)五个文件哈希已核对。52.425 s 的[原生终态指标](../../../runs/test_results/knot_oracle_20261003/hard08_resume01_milestones/settle_robot_clearance_pending.json)显示零交叉、落桌、低速及有界漂移均通过，但 `robot_clear=false`，保守体积间隙下界为 0；这是终态间隙未通过，不能等同于确认穿透。原静置窗口结束后已进入第三步 `retreat`，58.025 s 仍在真实执行；原生间隙阈值与任务规则未修改。

第三步额外退开后，机器人间隙仍未通过。对 tick 27,332 的两次一致只读几何采样离线核对，36 个机器人包络中仅右臂固定底座（`geom_20`／`right/base_link`）未通过，见[定位结果](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_resume01_clearance_probe/clearance_localization.json)。底座的全部支撑平面与冻结模型吻合，误差小于 2×10⁻¹⁶ m；[实体相交查询](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_resume01_clearance_probe/fixed_base_contact_check.json)未发现该 tick 绳体穿入底座、边界接触或 unresolved。另有一处[实测顶点距离](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard08_resume01_clearance_probe/fixed_base_proximity.json)仅 0.383 mm，确实不满足原生 5 mm 终态间隙。这是单 tick、单底座诊断，不是完整无穿透资格；抬高夹爪不会移动固定底座附近的绳子。

已增加 `native_rules_clearance_search_v4`：零交叉、已落桌但间隙不足时，优先尝试双端平移，保留撤手／落绳／拉开的其他候选。八个桌面方向、2／4／8 cm 位移及 5 mm 临时拱形抬升由两臂同步执行；每一步两臂 IK 都成功后才提交动作。现有原生几何只用于排序，不删除预测较差的候选或修改成功判据。该采样上沿 −Y 平移 1／2／4 cm 的几何估算可通过原生间隙检查，仍需真实物理验收。[候选代码与 37 项 CPU 检查](../../../runs/test_results/knot_oracle_20261003/supporting/clearance_translation_candidate/validation.json)已保存。

hard08_resume01 第四步重新落绳后仍未通过机器人间隙检查；最后记录为 80.425 s／32,170 ticks，零交叉、落桌、低速均通过，`failure=null`。已保存[策略升级停止记录](../../../runs/test_results/knot_oracle_20261003/hard08_resume01/strategy_upgrade_stop.json)，确认旧监督进程、容器和观察器退出，再启动 [hard09 冻结运行](../../../runs/test_results/knot_oracle_20261003/hard09_native_launcher/launch_plan.json)。新运行只替换控制器、候选搜索及其参数依赖／检查，任务、物理和安全源码保持原冻结版本。初态 `a4fbd7af273b0379` 已加载，正在从头真实重放 `d3_a2.pkl` 的 2,299 actions／22,990 ticks（57.475 s），之后核对 0.2 mm／0.2 mrad 容差并执行整理候选。没有直接设置绳形或机器人姿态；恢复日志中继承的历史采样不替代新的连续物理证明。

恢复期间另做了[CPU 运动学预检](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard09_translation_ik/report.json)：使用该检查点绳形、实测关节与已学习偏差，两端默认抓姿均可解，24 条平移候选中 23 条的首／中／末段 IK 采样通过，包含沿 −Y 移动 2 cm 的候选。预检没有推进物理，不覆盖实际接近、跟踪、抓持变形、R4 裁剪或穿透；未据此删减候选。当前恢复计数见[只读采样](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard09_progress_probe/latest.json)，其中进度比例仅指恢复前缀，不代表整个任务完成比例。

hard09 已实际重放完前 1,165 个动作并进入第二轮，[第一轮恢复计数证据](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/resume_first_primitive_completed.json)不宣称已通过完整检查点偏差核对。另在第二轮拉开的 tick 14,056（35.14 s）取得[两次一致的只读物理采样](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/replayed_spread_metrics.json)：原生 `planar_clear/on_table/quiet=false`，绳体最大速度约 40.5 mm/s。这些是本次回放的实际指标；单时刻采样不替代随后完整回放的逐 tick 穿透检查。
后续 tick 16,804（42.01 s）的[一致物理采样](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/replayed_planar_clear.json)已观察到原生 `planar_clear=true`，非局部投影间距约 15.53 mm；落桌和静止条件仍未通过。这是本次回放再次达到无交叉的证据，不是完整 hard 成功，也不确定清零发生的精确时刻。
静置至 tick 21,444（53.61 s）的[一致物理采样](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/replayed_settled_clearance_unmet.json)显示 `planar_clear/on_table/quiet=true`、已松手、最大速度约 0.535 mm/s，但原生 `robot_clear=false`，稳定时间仍为零。当前剩余终态问题确认为机器人间隙，恢复后的平移候选将针对它尝试整理；保守间隙下界为零本身不能证明实际穿透。

2,299 actions／22,990 ticks 已全部真实重放，[恢复检查](../../../runs/test_results/knot_oracle_20261003/hard09/resume.json)通过：中心线最大坐标误差 0.05613 mm，关节最大误差 4.255×10⁻⁸ rad。当前冻结 v4 的搜索入口会再静置 10 s，因为旧检查点未记录已完成初始等待；本轮保持原冻结源码继续运行。工作区 v5 已为新检查点记录 `search_phase=candidates`，恢复后仅跳过已执行的入口等待，旧检查点保守兼容，下一层新决策仍正常等待。[26 项 CPU 回归](../../../runs/test_results/knot_oracle_20261003/diagnostics/resume_settle_phase_fix.json)通过；该记账修复未部署到 hard09，也不改变原生稳定时间或成功判据。

额外静置已于 67.475 s 结束，[首个实际平移尝试](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/translation_started.json)选择两端沿 −Y 移动 2 cm、临时拱升 5 mm，已进入抓取接近。24 个候选全部保留，首选的刚性平移估计间隙下界为 5.007 mm；这只用于排序，仍须验证真实摩擦抓持、绳体跟随、释放及原生终态。

hard09 的平移尝试已完整结束于 83.15 s，[动作前缀](../../../runs/test_results/knot_oracle_20261003/hard09_milestones/prefix_33260_ba175bb7e7e7/manifest.json)保留 3,326 actions／33,260 ticks。73.6525 s 的[静置绳体诊断](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard09_translation_result/report.json)仍只有右臂固定底座间隙未通过，下界约 0.124 mm。相比本轮 53.61 s，底座附近顶点沿 −Y 位移中位数仅 1.47 mm，原近点仅 0.35 mm；刚性平移估计没有反映局部绳段的实际跟随。该比较包含中间静置和抓取过程，不是穿透资格检查。

已在 86.025 s [主动停止 hard09](../../../runs/test_results/knot_oracle_20261003/hard09/strategy_upgrade_stop.json)并启动 [hard10 / v6](../../../runs/test_results/knot_oracle_20261003/hard10_native_launcher/launch_plan.json)。新策略按原生体网格间隙定位受限机器人部件，以其附近材料绳段前后 8 cm 的抓点和远端配合，保留两端抓取；共 72 条默认平移候选，参数 `translate_grasp`／`translate_grasp_offset_m` 可配置。v6 同时识别旧检查点已记录的完整 `final_settle` 尾段，避免重等；物理前缀仍全部真实重放并核对恢复偏差。

40 项冻结 CPU 检查通过。[局部抓取预检](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard10_local_grasp_preflight/report.json)中两种偏移各 24 条路径的首／中／末 IK 均通过。+8 cm 首选的张开夹爪下降采样未发现顶点进入固定底座；−8 cm 在恢复前绳形上仍有 4 个规划顶点进入底座，不作为首选。这是命令姿态的局部采样，不能保证真实接近、所有碰撞对或整条路径无穿透。直接抓最近绳段及 ±4 cm 的规划重叠见[诊断](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard09_local_grasp_ik/approach_geometry.json)；没有通过允许实际穿透来消除这些问题。hard10 仅更改控制器、分支搜索及测试，沿用 v14 任务／物理／安全源码和本机固定 0.2.13-dev 镜像。

hard10 的[实际平面解结采样](../../../runs/test_results/knot_oracle_20261003/hard10_milestones/replayed_planar_clear.json)已在 tick 17,101（42.7525 s）确认原生 `planar_clear=true`，非局部投影间距约 15.49 mm；`on_table/quiet=false`，最大速度约 43.46 mm/s。该证据来自本轮进程的两次一致只读状态采样，Task／world／geometry tick 一致，没有暂停或修改模拟。它只证明该时刻的平面解结条件，不确定首次清零时刻，也不代表完整 hard 成功或逐 tick 穿透资格。此时仍在恢复前缀中的拉直段，新的局部抓取尚未执行。

随后 tick 21,757（54.3925 s）的[停稳采样](../../../runs/test_results/knot_oracle_20261003/hard10_milestones/replayed_settled_clearance_unmet.json)确认本轮 `planar_clear/on_table/quiet=true`、`assist_released=true`，最大速度约 0.790 mm/s；`robot_clear=false`、稳定时间为零。原生保守间隙下界为零本身不能证明真实穿透。恢复后的局部抓取将针对剩余机器人间隙尝试整理；此时尚未完成完整恢复偏差核对、实际局部抓取和逐 tick 资格检查。

hard10 的[完整恢复检查](../../../runs/test_results/knot_oracle_20261003/hard10_milestones/resume_verified.json)已通过：2,299 actions／22,990 ticks 全部真实重放，中心线最大坐标误差 0.06839 mm、关节误差 5.056×10⁻⁹ rad，均在 0.2 mm／0.2 mrad 容差内。首个新候选从 57.475 s 立即开始，使用 `translate_grasp=clearance`、材料偏移 +8 cm，沿 −Y 平移 2 cm、临时拱升 5 mm；没有再等待额外 10 s。局部抓取、平移及释放已实际执行，原生终态仍须继续验证。

对 `robot_clear` 的[规则复核与阈值扫描](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard10_robot_clear_review/report.json)使用本轮 54.3925 s 的停稳样本：36 个机器人碰撞体中仅 index 18（与既有右臂固定底座边界一致）未通过，其余部件的保守间隙至少 38.696 mm。按冻结原生算法将阈值分别设为 5／2／1／0.5／0.1 mm 离线复算，该样本仍全部失败，底座间隙下界均为零；这不是精确距离或穿透结论。`robot_clear` 属于共享释放完成条件：Knot 使用默认 5 mm，范围含所有机器人碰撞几何。是否允许与固定底座正常接触、是否改用更精确的几何分离证明，是任务判据的设计问题；本次仅核对并提出调整建议，未修改 hard10 的 v14 成功条件或物理规则。

首次局部整理后的[实际绳段跟随诊断](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard10_translation_result/report.json)比较本轮 tick 21,757 与 25,885（54.3925／64.7125 s）：底座附近材料顶点沿 −Y 位移中位数约 4.46 mm，旧近点移动约 3.23 mm，原生机器人间隙下界从零增至 2.147 mm，仍只有右臂固定底座未达 5 mm。后一个样本的平面解结、落桌、静止、松手均通过；这只证明该时刻的改善，后续静置间隙可能变化。比较包含中间静置、抓取、平移和释放，不等同于独立因果试验或整条轨迹无穿透资格。该次采样时仍执行原 v14 判据下的整理搜索；现已按上方新授权转入 hard11。

首次局部整理已完整结束于 73.275 s，[一致动作前缀](../../../runs/test_results/knot_oracle_20261003/hard10_milestones/prefix_29310_d514f10acd7c/manifest.json)保存 2,931 actions／29,310 ticks；[输入一致性核对](../../../runs/test_results/knot_oracle_20261003/diagnostics/hard10_first_local_prefix_identity.json)确认前 2,299 个动作、22,990 ticks 和动作布局与恢复检查点完全相同。实际抓点为右臂材料位置 0.266851 m、左臂远端 1.319632 m，未记录 IK 提前停止。该整理未取得原生成功，搜索已进入第 4 步撤手；动作前缀的一致性不替代后续正式回放和逐 tick 物理资格。

hard10 当时的调度器为 `/tmp/knot_hard10_supervisor.py`，状态见
[background_status.json](../../../runs/test_results/knot_oracle_20261003/background_status.json)。
原生成功后仍做两遍正式实例回放，首遍全 tick／共享四路录像及独立几何审计。
只读 CPU 并行审计的 9 项测试通过，同一 11 个真实状态的
逐 tick 结果、汇总和证据哈希与串行完全一致，1／4／8 进程耗时约 10.85／4.74／4.32 s。
[独立冻结方案及基准](../../../runs/test_results/knot_oracle_20261003/hard08_parallel_audit_launcher/launch_plan.json)
只改调度与 CLI；接触、穿透、体积和资格判据相同。原 hard08 审计等待队列已随上游中断退出。恢复队列使用相同的已验证审计源码，在完整 capture 封存后直接启动 8 个 CPU 测量进程，不再重复运行串行审计。恢复运行的归档助手已绑定该审计源码及前缀检查点，语法和缺证据拒绝检查通过；尚未发布。
完整 hard 原生成功、正式回放和最终物理资格尚待验证。

## 三档物体路线与 IK 的历史记录（2026-09-30）

本节描述当时状态；机器人与终态开关的最新情况以上方 10 月 3 日记录为准。

按"只动绳的路线 → 机器人 IK → 任务 Env 内连续物理执行"的顺序补证据，**机器人物理执行尚未完成**。绳上位置一律用弧长 s（从 A 端起，直绳参考态的材料坐标）；"交叉"指俯视投影中两段不相邻绳的交点；"抓点"指离 s 不超过 6 mm 的那一段绳。

**动作及出处。** 三档只用两类动作：
- 删交叉（node deletion，[HULK](https://arxiv.org/abs/2011.04999)）：从较近的自由端往里找第一个"该端从下面穿过"的交叉，一只手按住、另一只手抓住该交叉之后 35 mm 处抬起并往外拉，每拉 50 mm 重新数交叉（HULK 每次动作后重新感知）。与 HULK 不同，按住的是另一端离端 15 mm 处（v9 demo 的远端固定）：按 HULK 原样按在交叉旁的上股时，两手之间只有约 291 mm 绳，拉开时绳被拉长、松手回弹（`hard_cl_v4/v5`），不采用。
- 两端拉开（Reidemeister move，HULK 与 [SGTM 2.0](https://arxiv.org/abs/2207.07813)）：只剩局部小圈（一个交叉的两次经过之间没有别的交叉）时，两手捏住两端往外拉，小圈翻转消失。
- easy 的两个交叉都是同一条腿压在上面（Reidemeister II 构型），一只手把上面那条腿抬起越过另一条即可。

| 档位 | 只动绳的路线（粗网格，IPC 摩擦平滑 1 mm/s） | 交叉数 | 机器人 IK（CPU，仅运动学） |
|---|---|---|---|
| easy | A 腿鼓包 s=224 mm 抬 25 mm、−x 平移 95 mm、放回 | 2→0，终态判据稳定通过 | 右臂可达，桌面最小间隙 2.1 mm |
| medium | 远端 B 固定；A 侧 s=249 mm 抬 15 mm 沿绳拉 300 mm；两端拉开到约 0.9 m | 3→2→0，稳定通过；绳总长最大 +1.8 % | 左臂按 B、右臂拉 A；两端拉开右 A 左 B；均可达 |
| hard | 远端 A 固定；B 侧 s=1135 mm 抬 30 mm 往外拉 0.55 m；两端拉开到约 1.15 m | 4→1→0，稳定通过；绳总长最大 +1.9 % | 右臂按 A、左臂拉 B；两端拉开右 A 左 B；均可达 |

只动绳的证据与失败轮次见 [README](../../../runs/test_results/knot_object_route_20260930/README.md)；IK 检查见 `runs/test_results/knot_ik_keyframes_20260930/`（`scripts/check_knot_keyframes.py`，竖直下夹、夹指垂直于绳，预抓位与撤离各高 80 mm，查桌面、同臂、两臂与关节限位，绳不作碰撞体）。机器人执行器为 `scripts/run_knot_robot_route.py`，选点规则与只动绳共用 `topogym/planning/knot_untying/route_rule.py`，抓取为纯摩擦（不开抓持辅助）。

**已知边界。** 只动绳的路线用的是 8 边粗网格（约 1.6k 顶点，正式约 3.2 万）并把接触摩擦平滑速度设为 1 mm/s；正式配置未设该参数（libuipc 默认 10 mm/s），此时弯绳以约 3 mm/s 持续蠕动，过不了"最大速度 ≤ 1 mm/s"。机器人执行沿用正式网格与正式接触参数，只把时序改为每物理步 25 ms、40 子步（IPC 积分步长仍为 0.625 ms），原因是正式时序下每模拟秒约 2700 s 墙钟。`KnotUntyingTask.goal_complete=False`，Env 不会报 `task_success`，Harbor 中 knot 的 trial 因而不会判成功；可解性证明直接核对终态判据（无投影交叉/重叠、贴桌、静止、已松手、机器人离开 ≥5 mm、稳定 0.5 s）。


Agent 接入见 [Knot Untying adapter](../../../legacy/cleanup_20260929/docs/develop/modules/knot_untying_agent_adapter_zh.md)：本地文件队列、双臂四图、CUDA FEM 接触辅助与可复制 prompt。该接口的验证状态独立于下述历史 demo。

变体设计见 [固定结型与家族内参数构造方案](knot_untying_family_space_zh.md)：三叶结、开放八字结、双重单结分别作为 easy / medium / hard 的目标代表，每个结型配独立的动作与 IK 路径。三档均要求持续支撑、余量控制和受限方向下的操作；难度须经实际执行及简单路线对照确认，当前 v9 也需补查这一操作要求。新增家族与参数范围目前为设计提案。固定实例可直接选择，参数采样另设入口。

实施与结果见 [物理稳定性验收与三视角全过程 demo 计划](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_physics_demo_plan_zh.md)。已完成 [完整机器人解结录像](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)，实际连续模拟 75 s，保留五路同步视角。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。详细记录见 [抓持与录像复测](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_recording_attempt_zh.md)。

完整 demo 的 MP4 已按视角独立归档至 `demos/knot_untying/varaition_<id>/<camera>/`；播放页、报告、轨迹和归档清单保存至 `runs/demo_metadata/knot_untying/<date>_<run_id>/`。

本阶段铺设一根绳上只打一次结的场景。采用开放绳的 overhand knot；将自由端从外侧无交叉地闭合后，得到 trefoil / 3₁。物理场景中保留两个自由端，可供后续抓取和退绳。结型参考：[MathWorld](https://mathworld.wolfram.com/TrefoilKnot.html)。

## 几何和配置

源码在 `topogym/tasks/knot_untying/`，Hydra 入口为 `configs/knot_untying_preview.yaml`，基线登记在 `configs/task_cards/knot_untying.yaml`。

| 参数 | 默认值 |
| --- | --- |
| 绳径 | 8 mm |
| 总长 | 约 1.074 m，由曲线和自由端共同决定 |
| 每端余长 | 180 mm，包含平滑转向段 |
| 结形平面尺度 a | 32 mm；参数卡圈径比定义为 2a / 绳径 = 8 |
| 高度幅值 h | 8 mm |
| 初态桌面净距 | 至少 1 mm |
| 网格轴向间距 / 圆周段数 | ≤2.5 mm / 12 |
| 自接触作用距离 | 0.8 mm |
| 材料 | E=100 kPa，ν=0.45，ρ=650 kg/m³，μ=0.3，沿用共享候选值 |
| 材料参考态 | 直绳，初始结形有弯曲预应力 |
| 时间步 / 子步 | 5 ms / 4 |
| 固定或跟随顶点 | 0 |

采用曲线 `x=a(sin t+2 sin 2t), y=a(cos t−2 cos 2t), z=h sin 3t`，截取 `[π+0.5, 3π−0.5]`，升高到桌面之上；两端用切向连续的曲线转向结外，再接直尾。镜像 x 可切换手性。

几何验收检查三个横截交叉、沿绳的交替上下顺序、Gauss 顺序 123123 和一致交叉符号，并确认外侧诊断闭合不添加交叉。因此不是仅凭“有三个投影交点”判断结型。初始管面最小间距使用线段到线段距离；排除沿绳距离小于 πr 的局部邻居，另查局部弯曲半径。

## 运行

Nyx 环境需要额外安装 FEM 接触库；本机补齐的是旧仿真环境已有的同版本：

```bash
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-fem-ipc.txt
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.knot_untying
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_untying
```

默认输出 [trefoil_initial/index.html](../../../runs/environment_bootstrap/knot_untying/trefoil_initial/index.html)，包含 Nyx 实验室全景、俯视、近景静态图以及自由静置前后状态；不再生成相机环绕视频。`run.settle_steps=0` 仅建场与渲染，不会声明静置通过。

`inspection_report.json` 保存实际求解参数、体网格检查、模拟时长与初末状态；`settle_trace.json` 逐步记录位移与交叉数，`settle_states.npz` 保留实际顶点与中心线。直绳参考态若会翻转四面体，任务在构建前拒绝，不能静默改成结形参考态。

当前预览包含单台待命 Panda＋Robotiq 2F-85；机器人与绳接触已接入，未执行抓取。独立物理探针已加入长时接触检查和 ALOHA 双臂试跑，实际通过范围见上方验收页面。短时预览记录只检查这一初态的有限状态、体单元方向与投影交叉保留，不能代替连续碰撞的全程拓扑认证。

## 本机检查结果

2026-09-16 的默认运行完成 40 步、0.2 s 自由静置。实际体网格包含 6,516 个顶点、21,519 个四面体；直绳参考态和静置末态均无反转单元。三个交叉在每个采样步保留，末态 Gauss 顺序、上下交替和手性复查通过。

最大顶点位移约 37.27 mm，属于初始预弯曲绳的松弛，不能称为静止不动。末态按中心线及名义半径重建的管面净距约 0.48 mm，距桌面约 0.60 mm；这两个数是中心线诊断，不是形变后 FEM 表面的精确碰撞距离。实际报告保存该检查方法和范围。

几何、配置组合、参数卡和当前目录引用共 14 项测试通过；新增 Python 文件通过 Ruff 检查。Nyx 视频已检查为 45 帧、15 fps，只展示初始结形的相机环绕。
