# Horseshoe easy：完整机器人 IK 与物理执行

`waist_mild`、seed 0、`ring_clearance_candidate_v3` 已从默认 ALOHA home 连续执行到原生 `task_success=True`。总计 **275.2 s、11,008 个动作、11,009 个状态，零回溯**；[独立审计](evidence/runs/from_home_09/independent_audit.json)为 `accepted_proof=True`。原始 [run_report](evidence/runs/from_home_09/run_report.json)保留审计之前的 pending 状态，不改写历史报告。

策略实际完成双手抓马蹄、抬升折合、倾转 90°、释放上件并退手、让圆环自然脱落、右手让开余件、左手浅抓桌面圆环、抬升并送入固定目标区。终态全环在目标区、四件余件在系统侧，原生稳定窗口达到 0.5 s。19 对跨物体闭环关系全程保持，最大普通接触 0.0911 mm，合格夹指接触 0.2851 mm，无抓持丢失。

实际环中心线半轴为 74.101 / 70.763 mm，比旧版各增大 4 mm；线径 5.6 mm，马蹄及链环不变。完整马蹄投影见证跨度 167.362 mm，大于忽略线材厚度后的保守孔径上界 148.202 mm，阻挡余量至少 19.160 mm，见[法向穿出检查](evidence/supporting/selected_normal_passage_guard.json)。新初态经共同抬升 3 mm 后自然静置得到；没有在解题中改写物体状态。正式安装资源与通过运行的实例、资产、初态和目标区完全一致，见[落地复核](evidence/supporting/approved_model_promotion.json)。布局文件中的“unverified”是生成时原始备注，为保留已验收资源哈希未改写；完整资格以本批审计为准。

正式入口为 `topogym.planning.horseshoe_ring.stages:gravity_release_table_pickup_stages`，只使用正式 IK、接触筛选及普通关节动作，不导入或调用 calibration-tools。开发工具仅用于建模、只读候选和截图。使用 v12 已有的刚体全局求解设置 `rigid_options.use_contact_island=False`，保留 25 ms World tick / 40 子步、1 mm 普通接触／2 mm 合格夹指限值。折合前缀的单轮对照每 tick 墙钟时间约减少 5.1%；并发负载和反馈路径不同，不构成稳定提速或求解器物理等价证明。

范围仅为本实例、CPU float64、JOINT_ABS、40 Hz Task/动作检查和双指接触触发的 `contact_weld_v1` 辅助抓持。不扩展为纯摩擦、默认 400 Hz、全部积分子步或其他 seed／medium／hard 的成功。原物理运行关闭 RGB；Nyx 截图及随后四路录像均为实测状态重渲染，不增加执行次数。

证据为独立文件副本：[汇总](summary.json)、[逐文件清单](archive_manifest.json)、[哈希及来源校验](archive_validation.json)。冻结源码、配置、全部动作／状态和五项策略输入均在 `evidence/runs/from_home_09/`；没有依赖 calibration 开发进程。

在仓库根目录复跑已选配方（输出目录须不存在）：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_solvability_workflow.py \
  --output runs/test_results/horseshoe_easy_reproduction \
  --mode proof --seed 0 \
  --config solvability_proof/horseshoe_ring/2026-10-03_easy/evidence/runs/from_home_09/config.json \
  --selection solvability_proof/horseshoe_ring/2026-10-03_easy/reproduction_selection.json \
  --stage-factory topogym.planning.horseshoe_ring.stages:gravity_release_table_pickup_stages
```

新运行仍须用其冻结源码下的 `topogym.planning.horseshoe_ring.audit` 独立验收；该命令没有代表额外一次已通过的执行。资源监控按根目录 AGENTS.md 运行。成功录像和图像的当前链接统一见[任务页](../../../docs/develop/tasks/horseshoe_ring_zh.md)。
