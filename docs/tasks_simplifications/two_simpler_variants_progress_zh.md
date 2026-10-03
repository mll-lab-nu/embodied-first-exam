# 两个更简单变体的任务进度表

本表用于本 session 持续维护：为当前任务各新增 `very_easy`、`easier`，目标为 `very_easy < easier < easy`，保留原三档。按用户要求排除 `hedgehog_in_cage`、`slotted_post_ring`、`horseshoe_ring`，它们由其他成员负责。本表覆盖 **10 个任务、20 个新变体**。

最近更新：2026-10-02 23:44 CDT，时区 America/Chicago。检查对象为分支 `dev/jianwen`、HEAD `f0d233115` 加当前未提交改动。依据当前注册表、任务源码、任务说明和实际运行报告进行只读盘点；本轮没有重新运行物理、录像或 Harbor 验收。其他会话仍在开发，下面是检测时的证据快照。首轮盘点为同日 HEAD `ba31fdb4b`。

**当前已有 14/20 个具名变体实现、11/20 个变体有原生机器人完整成功证据、2/20 个变体通过双模式完整正向评分。** 原生成功中 9 个从默认 home 开始，2 个 Claws 变体从任务预抓姿态开始。双模式通过的是 Keyhole 两档；easier 的最新闭环参考已解决此前公开回放失败，两个正式 job 均已结束并得 1 分，较早失败记录保留。

## 统计口径

| 检查项 | 当前数量 | 含义 |
| --- | ---: | --- |
| 新两档入口及场景已实现 | 14/20 | Coil、Keyhole、Claws、Lock Picking、Buzz Wire、Fiber Bundling、Rope Threading 各两档。 |
| 原生机器人完整任务成功 | 11/20 | Coil、Keyhole、Claws、Lock Picking、Fiber Bundling 各两档，加 Buzz Wire very_easy；仅限各自实例、时序与辅助抓持配置。 |
| 有完整成功运行录像及校验记录 | 10/20 | 上述成功变体除 Claws easier；Fiber 为成功状态重渲染，不增加物理成功次数。本轮未重新解码。 |
| 两种模式的候选任务包已生成 | 12/20 | 共 24 个包；Coil、Keyhole 的 8 包在运行目录；Claws、Lock、Buzz、Fiber 的 16 包在根目录 `tasks/`。Rope 尚无新包。 |
| 两种模式完整正向评分均通过 | 2/20 | Keyhole very_easy 与 easier，四个正式 job 的最终 reward 均为 1。包内 oracle 元数据／正式发布另记。 |
| 尚未发现新两档实现 | 6/20 | Knot Untying、Orbits、Blanket Flatten 各两档。 |

不把上述分项相加计算总体百分比。“未见实现”指在当前注册表、活动源码、资源及相关文档中未发现本轮两档实现或专属计划，不推断其他工作区或尚未保存的工作。已有旧家族、旧 easy 或名字不同的历史简化场景不自动计作本轮新增两档。

## 任务总表

| 任务 | very_easy | easier | 下一步与当前缺口 |
| --- | --- | --- | --- |
| [Cast Coil](cast_coil_very_easy_easier_engineering_plan_zh.md) | 已实现；从 home 完整成功，46.30 s；录像通过 | 已实现；从 home 完整成功，48.55 s；录像通过 | 四包及镜像内短回放已通过；补双模式完整评分和正式交付。 |
| [Cast Keyhole](devs/cast_keyhole_very_easy_easier_oracle_plan_zh.md) | 从 home 成功，有录像；双模式完整评分通过 | 正式冻结 Session 闭环成功，155.605 s；双模式完整评分通过 | 两档均完成正向验收；候选包仍标 oracle=none，待整理资格元数据与正式交付。GPU 回放不保证逐位相同。 |
| [Interlocked Claws](../develop/tasks/interlocked_claws_zh.md) | 已实现；从预抓姿态完整成功，108.775 s；录像已有校验记录 | 已实现；从预抓姿态完整成功，517.675 s；成功运行无录像 | 补 easier 成功录像及双模式完整评分。四包已登记，privileged 短 verifier 通过。 |
| [Lock Picking](../develop/tasks/lock_picking_zh.md) | 两片直槽；从 home 成功，35.6325 s；审计及录像通过 | 第一片偏转 20°；从 home 接触转片后成功，48.2575 s；审计及录像通过 | 默认时序原生执行和新进程关节目标回放均成功；四包及双模式短测通过，完整 Harbor 正向评分待验。 |
| [Buzz Wire 3D](../develop/tasks/buzz_wire_3d_zh.md) | 直道布局及双模式包已接入；planning oracle 从 home 无回溯成功，262.8 s，审计及三路 Nyx 视频通过 | 横弯接下凹弯；planning oracle 从 home 无回溯成功，290.875 s，审计及三路 Nyx 视频通过 | 两档 seed 0、CPU64、25 ms / 1 倍 / 40 子步、接触辅助抓持已验证。默认任务包负例评分通过；默认时序完整正分及难度排序未资格化。 |
| [Fiber Bundling](../develop/tasks/fiber_bundling_zh.md) | 2 根相对细线，seed 0 从 home 完整成功并独立审计 | 3 根三角细线，seed 0 从 home 完整成功并独立审计 | 两档三视角录像、4 个包已生成；privileged 和 standard 短流程均通过。辅助护套抓持；两档默认时序复验与独立审计通过，难度排序未评测。 |
| [Rope Threading](../develop/tasks/rope_threading_zh.md) | 下半圆搭绳场景与完整终态判据已接入 | 单环穿越、双手交接历史及终态判据已接入 | 五档统一 0° 摆位与 20.9 mm 底座垫高；合成状态／回溯检查通过，正常 IPC 初始化已修复，完整机器人解法仍待验收。 |
| [Knot Untying](../develop/tasks/knot_untying_zh.md) | 未见实现 | 未见实现 | 制定两档解结初态与操作要求，进入建模和验证。 |
| [Orbits](../develop/tasks/orbits_zh.md) | 未见实现 | 未见实现 | 制定两档结构与初态，随后核对软体稳定性和完整执行。 |
| [Blanket Flatten](../develop/tasks/blanket_flatten_zh.md) | 未见实现 | 未见实现 | 制定两档展平初态；新状态需独立准备、冻结并验证恢复。 |

上表的下一步是待办，不表示本轮已开始实现。当前七组已实现变体的参考动作或场景有区别，但没有找到覆盖新两档与原 easy 的统一难度校准结果；不以运行时长证明难度顺序。

## 已实现变体的证据与限制

### Cast Coil

very_easy 为大齿直插，版本 `cubic_comb_v2_aloha_v1`；easier 为挡板约束下的错位直插加横移，版本 `cubic_baffle_v2_aloha_v1`。运行尺寸均为 51 mm 正方体，复用装配、落桌、解除抓持、撤手及稳定 0.5 s 的原生判据。

| 变体 | 原生成功与复核 | 完整运行录像 |
| --- | --- | --- |
| very_easy | [执行报告](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/run_report.json)；[全 tick 复核](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/native_tick_audit.json) | [上方](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/segments/segment_1/videos/cam_high.mp4) · [前方](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/segments/segment_1/videos/cam_low.mp4) · [左腕](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/segments/segment_1/videos/cam_left_wrist.mp4) · [右腕](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_a05/segments/segment_1/videos/cam_right_wrist.mp4) |
| easier | [执行报告](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/run_report.json)；[全 tick 复核](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/native_tick_audit.json) | [上方](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/segments/segment_1/videos/cam_high.mp4) · [前方](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/segments/segment_1/videos/cam_low.mp4) · [左腕](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/segments/segment_1/videos/cam_left_wrist.mp4) · [右腕](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_a03/segments/segment_1/videos/cam_right_wrist.mp4) |

[实施汇总](../../runs/test_results/cast_coil_variants_gpu_20261002/implementation_report.json)记录 45 项回归、[24 项包检查](../../runs/test_results/cast_coil_variants_gpu_20261002/package_checks_v2.json)以及两档成功录像。本轮复核其中脚本哈希，Coil 专属文件仍一致；共享 `variation_records.py`、`goal_description.py` 已变化，历史运行不替代当前共享环境重验。[四个候选包](../../runs/test_results/cast_coil_variants_gpu_20261002/tasks/)已生成，[very_easy](../../runs/test_results/cast_coil_variants_gpu_20261002/very_easy_package_smoke/smoke.json) 和 [easier](../../runs/test_results/cast_coil_variants_gpu_20261002/easier_package_smoke/smoke.json) 的镜像内 3 步短测通过。

成功范围为每档 seed=0 的一个冻结实例，CUDA、25 ms tick、40 子步，使用接触触发的 `contact_weld_v1` 并在终态解除。完整 Harbor agent/verifier 尚未运行；不扩展为纯摩擦、默认时序、半步长或随机参数域资格。

### Cast Keyhole

两档均为 `simplified_original_layout_v4`，恢复原三档外形及初始摆位、无额外支撑；very_easy 为直通主槽，easier 有两处错位。完整普通运行使用默认 home 起点、branch 0，均有 `task_success=True`；采用接触触发的辅助抓持。

| 变体 | 原生成功报告 | 策略阶段四路录像 |
| --- | --- | --- |
| very_easy | [执行报告](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/very_easy_full_qualified_02/run_report.json) | [上方](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/very_easy_full_qualified_02/segments/segment_2/videos/cam_high.mp4) · [前方](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/very_easy_full_qualified_02/segments/segment_2/videos/cam_low.mp4) · [左腕](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/very_easy_full_qualified_02/segments/segment_2/videos/cam_left_wrist.mp4) · [右腕](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/very_easy_full_qualified_02/segments/segment_2/videos/cam_right_wrist.mp4) |
| easier | [执行报告](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_full_qualified_01/run_report.json) | [上方](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_full_qualified_01/segments/segment_2/videos/cam_high.mp4) · [前方](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_full_qualified_01/segments/segment_2/videos/cam_low.mp4) · [左腕](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_full_qualified_01/segments/segment_2/videos/cam_left_wrist.mp4) · [右腕](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_full_qualified_01/segments/segment_2/videos/cam_right_wrist.mp4) |

初态与自然落稳前缀另存同次执行的 segment 0、1。上表保留最初本地完整成功及录像；[本地完整运行汇总](../../runs/test_results/cast_keyhole_oracle_20261002_01/local_full_summary.json)中的 `harbor_qualified=false` 是该阶段状态，后续正式评分以以下最终报告为准。策略与私有适配器已继续修改，不把旧快照当作当前整个工作区已验证。

[四个 nop 负对照](../../runs/test_results/cast_keyhole_oracle_20261002_01/harbor_nop_summary.json)已正常得 0。两档完整正向评分现在均通过：

| 变体 | privileged 最终评分 | standard 最终评分 |
| --- | --- | --- |
| very_easy | [reward.json](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/harbor_jobs/very-easy-privileged-oracle01/topogym-cast-keyhole-very-easy-i__WpdiLPK/verifier/reward.json)：success=1、all_success=1、两遍回放 | [reward.json](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/harbor_jobs/very-easy-standard-oracle01/topogym-cast-keyhole-very-easy-i__hCxTssZ/verifier/reward.json)：success=1、live_success=1、replay_success=1 |
| easier | [reward.json](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/harbor_jobs/easier-privileged-oracle05/topogym-cast-keyhole-easier-i00__gqgni5P/verifier/reward.json)：success=1、all_success=1、两遍回放 | [reward.json](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/harbor_jobs/easier-standard-oracle01/topogym-cast-keyhole-easier-i00__2fMYZEj/verifier/reward.json)：success=1、live_success=1、replay_success=1 |

四个 job 均已结束、grader_error=0；standard 的 infra_error=0。GPU 末态摘要不逐位相同，`deterministic=0`，不声称逐位复现。[闭环调度报告](../../runs/test_results/cast_keyhole_oracle_20261002_01/large_runs/easier_feedback05_orchestration.json)已为 `both_modes_passed`。运行目录的四个候选 `task.toml` 仍标 `oracle="none"`，正式资格元数据、收录和发布尚需整理，不能将评分通过与发布完成混为一项。

easier 先前两次公开回放失败，分别发现夹爪宽度转换损失和自然落稳差异；[首轮失败](../../runs/test_results/cast_keyhole_oracle_20261002_01/easier_public_replay_failure_01.json)、[第二轮失败](../../runs/test_results/cast_keyhole_oracle_20261002_01/easier_public_replay_failure_02.json)仍保留。最新候选在正式冻结 Session 中按实测姿态闭环求解，经原有预检选用向上 1 mm 的 TCP 抓点偏移；未改模型、物理或判据。实际提交 6,225 个动作、62,242 tick，155.605 s 完成，随后两种模式评分均成功。因此不再把这两次旧失败列为当前阻塞。

较早[场景修订计划](cast_keyhole_very_easy_easier_revision_plan_zh.md)的开头仍写“完整机器人求解为后续工作”，而后续原始报告已成功。本表以新的运行证据为准；没有把旧计划改写为最新验收报告。

### Interlocked Claws

very_easy 为垂直短边交错的 L 钩，版本 `perpendicular_short_legs_pregrasp_candidate_v2`；easier 为十字件穿方框，版本 `xyz_cross_offset_frame_candidate_v1`。两档入口、连续物体通路和双臂采样预检均已有；策略分别使用小角度解钩和多段旋转／平移。

very_easy 的 [CPU 完整报告](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt04_cpu/run_report.json)及[带录像运行报告](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/run_report.json)均为 `passed`、`task_success=true`，108.775 s，原生 `Goal stable`。easier 的 [CPU 第四次尝试](../../runs/test_results/claws_simplified_development_20261002/easier_attempt04_cpu/run_report.json)也已 `passed`、`task_success=true`，517.675 s，但未开启录像。**两档起点均是任务预抓姿态，采用辅助抓持，不能记成从默认 home 完成。**

very_easy 成功运行的初态、取得抓持、解锁及搬运分别保存在同次执行的 segment 0、1、2。解锁与搬运视频：[上方](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_high.mp4) · [前方](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_low.mp4) · [左腕](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_left_wrist.mp4) · [右腕](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_right_wrist.mp4)。[录像校验记录](../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/validation.json)中四路均为 3,258 帧、30 fps、848×480。

[交付审计](../../runs/test_results/claws_simplified_development_20261002/delivery_audit.json)对上述三次成功执行记录了完整 World tick 与源码身份，均通过，未记录抓持脱落；其范围不包括连续求解子步或执行器力资格。本轮复核审计中的任务专属源码哈希，均与当前文件一致。较早 easier 第三次执行的 `policy_error` 及 GPU 执行证据不完整记录保留，不计为成功。

[四包生成报告](../../runs/test_results/claws_simplified_development_20261002/harbor_packages02/report.json)通过，并已在 [dataset.toml](../../tasks/dataset.toml)登记；四包均仍为 `oracle="none"`。[privileged verifier 重试](../../runs/test_results/claws_simplified_development_20261002/harbor_verifier_retry02/report.json)通过两档各 3 个 hold 动作、独立 verifier 两遍回放及媒体收尾，正常得 0；这不覆盖 standard 完整服务链或完整参考解评分。[独立 wheel 检查](../../runs/test_results/claws_simplified_development_20261002/package_check03/report.json)也已通过。本轮比较 very_easy 成功快照中的任务模块、简化策略／通路／预检模块和简化几何生成器，均与当前对应文件一致。

### Lock Picking

两档为 `two_rotor_v1`：两个被动锁片、双齿钥匙和固定 END 板。very_easy 两片槽对齐；easier 第一片偏转 20°，需以钥匙接触带动锁片回正再插入。两档均从 home 完成，使用接触触发辅助抓持，允许终态保持抓持。

[验证汇总](../../runs/test_results/lock_picking_oracles_20261002/oracle_validation_report.json)与 [very_easy 执行](../../runs/test_results/lock_picking_oracles_20261002/very_easy_attempt01/run_report.json)、[easier 执行](../../runs/test_results/lock_picking_oracles_20261002/easier_attempt01/run_report.json)确认默认 2.5 ms tick／4 子步／40 Hz、CUDA float32 下分别 35.6325 s、48.2575 s 成功，逐 tick 独立审计通过。新进程重新执行原生关节目标也成功；这不是 Harbor 公开宽度动作或 standard 服务的完整正向评分。

- very_easy 回放录像：[主视角](../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/agentview.mp4) · [侧视角](../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/front_oblique.mp4) · [腕相机](../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/wrist.mp4)。
- easier 回放录像：[主视角](../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/agentview.mp4) · [侧视角](../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/front_oblique.mp4) · [腕相机](../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/wrist.mp4)。

[任务包验收](../../runs/test_results/lock_picking_variants_20261002/validation_report.json)记录四包与双模式短流程通过、预期得 0。正式完整正向评分待验；包内仍为 `oracle="none"`。

### Fiber Bundling

两档为 `symmetric_branches_v1`，分别采用 2 根相对细线和 3 根三角细线，沿用完整穿环及细线禁碰判据。机器人从 home 抓粗护套，接触触发辅助抓持，不辅助细线。

[交付报告](../../runs/test_results/fiber_bundling_simplified_development_20261002/delivery_report.json)确认两档在开发时序与包内默认时序共四次完整成功，并独立审计：开发时序分别 106.350 s、155.425 s；默认时序分别 106.635 s、155.4175 s。默认时序为 CPU float64、2.5 ms tick／4 子步／10 倍控制降采样，采用包内接触配置。easier 的[默认时序审计](../../runs/test_results/fiber_bundling_simplified_development_20261002/easier_package_timing02_cpu_audit/audit.json)已通过，不再列为待复验。

正式三视角来自已审计成功状态的 Nyx 重渲染，关节及 link 位姿恢复核对通过；不增加物理成功次数：

- very_easy：[全景](../../demos/fiber_bundling/varaition_very_easy/agentview/varaition_very_easy_agentview.mp4) · [近景](../../demos/fiber_bundling/varaition_very_easy/front_oblique/varaition_very_easy_front_oblique.mp4) · [腕部](../../demos/fiber_bundling/varaition_very_easy/wrist/varaition_very_easy_wrist.mp4)。
- easier：[全景](../../demos/fiber_bundling/varaition_easier/agentview/varaition_easier_agentview.mp4) · [近景](../../demos/fiber_bundling/varaition_easier/front_oblique/varaition_easier_front_oblique.mp4) · [腕部](../../demos/fiber_bundling/varaition_easier/wrist/varaition_easier_wrist.mp4)。

四个本地任务包已生成并登记，两种模式短流程通过。完整 Harbor oracle 评分和难度排序未完成；本地镜像未推送。

### Buzz Wire 3D

两档独立布局已接入：very_easy 为直道，easier 为横弯接下凹弯。[验证汇总](../../runs/test_results/buzz_wire_simplified_development_20261002/validation_summary.json)确认 very_easy 在 seed 0、CPU float64、25 ms tick／40 子步、辅助抓持下两次完整成功，均为 262.1 s；[带录像执行](../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/run_report.json)与[独立审计](../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/independent_audit.json)保留实际证据。完整视频：[主视角](../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/agentview.mp4) · [侧视角](../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/front_oblique.mp4) · [腕相机](../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/wrist.mp4)。

easier 已走完整条线路并完成第一次低位释放，但终点重新抓取／摆正仍未完成。[带录像尝试](../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/run_report.json)与后续 [CPU 尝试](../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt07_cpu/run_report.json)均为失败，不计成功。另一个 oracle 开发目录中的 [very_easy 反馈尝试](../../runs/test_results/buzz_wire_simplified_oracle_20261002/very_easy_feedback_01/run_report.json)尚无最终成功，不增加资格。

四包已生成并登记；默认时序容器加载、短静置及 privileged 负例评分通过。没有把开发时序的成功外推为默认包时序或完整 Harbor 正向评分通过。

### Rope Threading

very_easy 的下半圆搭绳场景与 easier 的单环穿越／双手交接场景均已注册，并启用各自完整终态判据。五档统一 0° 摆位，ALOHA 底座垫高 20.9 mm；[离线检查](../../runs/test_results/rope_threading_scenes_20261002/offline_checks.json)与任务页记录场景、合成状态和回溯检查。正式 IPC 初始化已修复，但判据与初始化通过不代表机器人成功。

very_easy 的[首次抓绳尝试](../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt01/run_report.json)到接近阶段 1.06 s，[第二次尝试](../../runs/test_results/rope_threading_development_20261002/very_easy_pickup_attempt02/run_report.json)到下探阶段 5.47 s，均为 `incomplete`、`pickup_passed=false`、`task_success=false`。两档尚无完整机器人成功或新 Harbor 包；后续先补实际抓绳、交接及完整终态证据。

## 本 session 的维护方式

- 本轮已完成：重新核对 20 个目标变体，确认 14 个入口、11 个变体的原生成功、10 个变体的成功录像，以及 Keyhole 两档四个正式 job 的最终正向评分；保留其他会话已补充的任务进度。
- 后续每完成方案、建模、注册、参考策略、原生完整运行、录像或双模式验收，更新同一任务行及相应证据，不另建每日重复进度表。
- 报告 `running`、短流程通过或文档声称完成，都不自动升级为完整任务成功；模型 revision、初态或时序改变后注明证据范围，保留失败和旧版记录。
- 当前待办：Buzz easier 完整收尾、Rope 两档实际抓绳与完整求解、Claws easier 成功录像，以及尚缺的完整 Harbor 正向评分；Knot、Orbits、Blanket 两档仍待设计和实现。用户调整优先级时更新本表。

任务全集及具名入口依据 [registry.py](../../topogym/config/registry.py)、[variation_records.py](../../topogym/config/variation_records.py)；运行与交付口径参照[场景调整注意事项](post_fix_scene_variant_guidelines_zh.md)。原[三个任务计划](two_levels_below_easy_plan_20261001_zh.md)仅覆盖本 session 排除的三项，不将其中的六变体或 90 项矩阵数字套用于本表。
