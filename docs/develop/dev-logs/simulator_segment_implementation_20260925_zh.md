# Simulator segment 实施与验收记录

日期：2026-09-25（最终验收于 2026-09-26 UTC 完成）。状态：本地接口及本轮分层验收完成；测试配置、源码快照和跟踪资格分别列明。

已按[低层 segment 计划](../modules/simulator_segment_execution_plan_20260925_zh.md)实现：policy 连续提交既有低层 action，begin/end 组织段与证据；end 不推进物理。不增加单段 actions/token/时间预算，保留 Env 的 episode 时限。调用方式见[本地 API](../modules/simulator_api_zh.md)，复现命令见[测试说明](../../../tests/README.md#segment-与低层方块-policy-验收)。

| 实现 | 职责 |
|---|---|
| [simulator/segment.py](../../../topogym/simulator/segment.py) | SegmentRunner / SegmentInteraction、流式及列表执行、request_id/sequence 幂等、终态收尾、错误前缀、管理方与 actor 互斥 |
| [simulator/env.py](../../../topogym/simulator/env.py)、[interaction.py](../../../topogym/simulator/interaction.py) | 只读 timing_spec、提交后逐 tick 测量事件、重入保护、公开反馈投影；沿用唯一 Env.step 物理执行路径 |
| [evidence.py](../../../topogym/simulator/evidence.py)、[artifacts.py](../../../topogym/simulator/artifacts.py) | 管理日志、数值块、来源/配置/资产身份、权限和逻辑 artifact ID |
| [recording/segment.py](../../../topogym/recording/segment.py)、[session.py](../../../topogym/recording/session.py) | 复用 RecordingSession/VideoWriter；首末 PNG、三/四视角及同步合成、展示补帧、解码校验 |
| [cube_transfer.py](../../../tests/fixtures/cube_transfer.py)、[cube_policy.py](../../../tests/fixtures/cube_policy.py) | 临时注册的独立测试 Task 与普通权限低层 scripted policy，不进入生产任务列表 |
| [验收入口](../../../scripts/test_policy_cube_transfer.py) | 独立源码快照、逐例进程、运行前报告、真实 Genesis/Nyx 录像与资格结果 |

本轮没有修改生产 Task/场景资产、World 求解器或延期 agent；Task 状态格式的后续变化来自并行会话，本轮对其作兼容性检查。

## 验收结果与来源

最终冻结源码上的合同、录制、架构、控制、配置、机器人描述及 Task 状态回归：**157 passed、1 deselected**。[JUnit](../../../runs/test_results/segments_20260925_default_aloha_final/contract_junit.xml)、[完整源码哈希](../../../runs/test_results/segments_20260925_default_aloha_final/source_manifest.json)。包括管理方 reset 与 runner 绑定竞态、收尾期间 reset/close 拒绝且环境不 fault、重建期间互斥、报告写失败不得发布 complete、受阻/短暂抬起/未抓持飞行/掉落的评价器反例。此前重叠批次不累加。

真实串行套件 **15/15 按各自资格通过**：[汇总](../../../runs/test_results/segments_20260925_acceptance_02/summary.json)、[逐例资格与误差](../../../runs/test_results/segments_20260925_acceptance_02/qualification.json)、[对应源码哈希](../../../runs/test_results/segments_20260925_acceptance_02/source_manifest.json)。

| 验证 | 结果 |
|---|---|
| 方块完整搬运，seeds 0–4 | 5/5 成功；稳定抓持 ≥0.2 s，离桌峰值 8.07–8.34 cm、空中横移 19.35–20.11 cm，最终目标误差 0.283–0.572 mm；张开撤离后稳定 0.5 s |
| 同策略拆成两段，seed 0 | 成功；289 + 226 = 515 ticks，与单段相同。交界均为 state_id=289，三路末/首 PNG 逐字节相同 |
| 同 seed 初态 | 单段/两段的初始物理状态哈希及三路初态 PNG 均相同，[对比记录](../../../runs/test_results/segments_20260925_acceptance_02/split_comparison.json) |
| 空抓反例 | 549 控制步正常完成、证据完整；方块始终未满足抓持/抬起/搬运，task_success=false。反例通过表示没有误报成功 |
| Panda × 四种控制模式 | 段连续性、日志与媒体通过；原 0.5 s 窗口夹爪未达原 0.03 rad 容差。测试代码另提交保持段后，均在 2.325 s 达到全部原阈值 |
| ALOHA × 四种控制模式 | 段连续性、日志与四视角媒体通过，均在原 0.5 s 窗口达到全部原阈值 |

上述 15 例使用显式配置 **physics_dt_s=0.025、control_decimation=1、solver_substeps=40**。控制频率仍为 40 Hz、求解子步为 0.625 ms；库默认值未改变。此结果不能称为默认 2.5 ms tick 的完整方块搬运/全矩阵验收。保持段是测试代码主动提交的 `{}` 动作，runner 不自动等待目标到达；原短程跟踪失败没有被覆盖或放宽阈值。

另外在**最终冻结源码、默认 0.0025 s × 10 / solver_substeps=4** 下完成 ALOHA JOINT_ABS 两段真实验证：20 控制步、200 ticks、0.5 s，首尾相接、201 条含初态 tick 记录，四视角和合成视频均通过。双臂最大 TCP 误差约 0.0402 mm、姿态误差 0.000156 rad、关节误差 0.000144 rad、夹爪误差 0.0399 mm，全部达到原阈值，无额外保持。[报告](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/report.json)、[媒体/日志核对](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/offline_evidence_audit.json)。

15 例套件的快照早于最终并发/报告发布边界修正及并行会话的 Task schema 2 更新；最终 157 项回归及默认 ALOHA 验证使用同一份更新后的独立快照。七份方块测量轨迹也用最终 Task schema 2 离线重算，结果全部符合预期；这不增加真实运行次数，不是重渲染。[重算记录](../../../runs/test_results/segments_20260925_acceptance_02/task_schema2_reevaluation.json)。所有通过结论绑定所列源码，不代表其他后续变化的生产 Task 判据已验证或完整解题已成功。

## 视频与证据

代表完整流程为套件 seed 0：实际 Genesis/Nyx，从 robot home 连续抓起、搬运、放下并撤离；未使用物体绑定、位置瞬移或外力托举。

- [同步合成](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/segment_1.mp4)
- [agentview](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/views/agentview/segment_1.mp4)、[front_oblique](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/views/front_oblique/segment_1.mp4)、[wrist](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/views/wrist/segment_1.mp4)
- [管理报告](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/report.json)、[逐控制步日志](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/private/control_steps.jsonl)、[逐 tick 日志](../../../runs/test_results/segments_20260925_acceptance_02/cube_seed_0/trail/private/physics_states.jsonl)
- 两段版本：[第一段](../../../runs/test_results/segments_20260925_acceptance_02/cube_split/trail/segment_1.mp4)、[第二段](../../../runs/test_results/segments_20260925_acceptance_02/cube_split/trail/segment_2.mp4)
- 默认时序 ALOHA 第一段：[cam_high](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/trail/views/cam_high/segment_1.mp4)、[cam_low](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/trail/views/cam_low/segment_1.mp4)、[cam_left_wrist](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/trail/views/cam_left_wrist/segment_1.mp4)、[cam_right_wrist](../../../runs/test_results/segments_20260925_default_aloha_final/case_0_seed_0/trail/views/cam_right_wrist/segment_1.mp4)

各原始视角为 Nyx + compact_lab、848×480、30 fps；合成保留完整原始分辨率。每个完成段经过完整解码、帧数同步、frame_map → state_id/tick、控制步计数及文件哈希核对。[离线关联检查器](../../../runs/test_results/segment_contracts_20260925/offline_evidence_audit.py)。seed 0 单段为 516 条含初态物理记录、每路 387 帧；两段分别 218/170 帧，第一段有 1 帧明确标注的末状态展示补帧，不算额外 physics tick。新结果区分实际推进、已保存与未形成 checkpoint 的 ticks，故障图片另标真实 final_frame_state_id。

## 保留的限制和历史失败

- API 权限不等于同 OS 用户下任意 Python 的进程隔离。普通 policy 可取授权媒体，详细日志始终由管理方记录、只向特权句柄开放；Harbor/网络 RPC/不可信脚本隔离未实施。
- 完整 IPC 接触、实际执行器力及引擎 checkpoint 导出均未承诺，覆盖标记为 false。可读日志不作为可恢复引擎 checkpoint。
- 串行 seed 0 峰值 RSS 约 5.76 GB，可读日志约 23.19 MB，12.875 s 仿真耗时约 509 s。现有完整历史和幂等 step 反馈（含 RGB）随执行增长；未实现其磁盘缓存或长期内存优化，也未引入段预算。默认时序短测显示每 tick checkpoint 约 1.1 s、物理 advance 约 6 ms，性能瓶颈仍在完整 checkpoint。
- `segments_20260925_cube_01` 因 Nyx 木纹资源缺失而失败；从既有副本校验项目声明 SHA-256 后恢复标准缓存。cube_02/03 为性能诊断主动中断，不能计通过。
- `segments_20260925_profile_01` 的默认 Panda 原 0.5 s 夹爪误差 0.18294 rad，超过 0.03 rad，原失败保留；不与后来保持段后的达标混淆。
- `segments_20260925_acceptance_01` 与 `segments_20260925_default_matrix_01` 两批合计六个实例并发触发显存不足，已停止本次 dispatcher/worker 并完整保留产物；后续串行完成验收。
- `segments_20260925_cube_04` 是更早判据的首次成功，保留但不计入最终五 seed 清单。以上运行均位于 `runs/test_results/`，没有删除失败证据。
