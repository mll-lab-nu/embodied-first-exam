# Horseshoe Ring medium / seed 0

`u_mild` 的 `ring_clearance_grasp_candidate_v5` 从默认 ALOHA home 连续执行 **264.5 s**，10,580 个动作、10,581 个状态，原生 `task_success=True`，独立审计 `accepted_proof=True`，零回溯、零抓持丢失，19 对闭环关系保持。

[最终结果](evidence/runs/medium_from_home_08/oracle_result.json) · [原生报告](evidence/runs/medium_from_home_08/run_report.json) · [独立审计](evidence/runs/medium_from_home_08/independent_audit.json) · [归档校验](archive_validation.json) · [配方](recipe.json)。原生报告保留审计前的 pending 标记，最终资格以独立审计和最终结果为准。

从仓库根目录运行：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_horseshoe_oracle.py \
  --variant medium --seed 0 --output runs/test_results/horseshoe_medium_new
```

输出目录必须尚不存在。入口冻结源码、核对模型及五份规划输入，执行反馈 IK 策略并自动审计；只在原生成功、审计通过且实例一致时返回 0。正式策略不导入 calibration-tools，也不重放已有动作来冒充新的执行。

环中心线半轴为 73.862 / 70.535 mm，均比原模型增加 4 mm；相位 0°，线径、马蹄和链环不变。完整马蹄法向直接穿出的充分阻挡余量为 21.372 mm。[模型与静置证据](evidence/supporting/medium_phase0_cached_trial/settled_layout.json)保留同一几何的自然静置来源。[Nyx 高视角](evidence/supporting/medium_v5_model_screenshot/frames/479c139ab94148b3a618c99d1bffa9d5/raw.png)与[低视角](evidence/supporting/medium_v5_model_screenshot/frames/fb4df4fc57b549ec8a4bf5ccfeb02809/raw.png)为初态建模预览，零物理推进。本轮按用户要求不制作新视频。

采用接触触发的 `contact_weld_v1` 辅助抓持、CPU float64、25 ms World tick / 40 子步、`use_contact_island=False`。普通接触最大 0.15393 mm、合格夹指最大 0.40365 mm，原生上限仍为 1 / 2 mm；原生终态安静保持仍为 0.5 s。证明仅覆盖此 seed、冻结源码及配置，不扩展为纯摩擦、默认 400 Hz、连续时间或整个随机参数域资格。
