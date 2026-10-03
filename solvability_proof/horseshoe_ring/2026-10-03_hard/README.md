# Horseshoe Ring hard / seed 0

`waist_ellipse` 的 `ring_release_clearance_candidate_v8` 从默认 ALOHA home 连续执行 **252.4 s**，10,096 个动作、10,097 个状态，原生 `task_success=True` 与独立审计 `accepted_proof=True`，零回溯、零抓持丢失，19 对闭环关系保持。

[最终结果](evidence/runs/hard_from_home_22/oracle_result.json) · [原生报告](evidence/runs/hard_from_home_22/run_report.json) · [独立审计](evidence/runs/hard_from_home_22/independent_audit.json) · [归档校验](archive_validation.json) · [配方](recipe.json)。底层报告保留审计前 pending 状态，以独立审计和最终结果判定资格。

从仓库根目录运行：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_horseshoe_oracle.py \
  --variant hard --seed 0 --output runs/test_results/horseshoe_hard_new
```

输出目录必须尚不存在。入口冻结源码、核对模型及五份规划输入，执行反馈 IK 并自动独立审计，只在原生成功、审计通过且实例一致时返回 0。正式策略不导入或调用 calibration-tools。右手采用马蹄圆弧 270° 处的侧向抓点；折合在参考第 3629 帧结束并直接进入 90° 倾转。hard 在左手松开马蹄并撤离后，主动抓住仍悬挂的圆环；双手将环及右马蹄共同平移 [0, 220.0, 0] mm，再让右手松开并撤离。左手逐段上提圆环，直到观测到它与全部余件真实分离，随后送入固定目标区。余件自然落在分隔线系统侧；不要求圆环在左手抓取前就已自然脱落。原生 IK、接触及终态阈值保持不变。

环中心线半轴为 83.000 / 83.000 mm，相对原模型增加 6.877 / 16.806 mm；相位 0°，马蹄、链环及 5.6 mm 环线径不变。完整马蹄法向直接穿出的充分阻挡余量仍为 **1.855 mm**。[建模检查](evidence/supporting/hard_circle83_v8_trial/candidate.json)与[自然静置](evidence/supporting/hard_circle83_v8_trial/settled_layout.json)保留开发证据；开发报告的未取得完整资格标记保留原义，最终资格由本批真实执行给出。[Nyx 高视角](evidence/supporting/hard_v8_model_screenshot/frames/7e512145340c46bfa739b5147867ea84/raw.png)和[低视角](evidence/supporting/hard_v8_model_screenshot/frames/412b985fd64b4b99901c50b28bc42466/raw.png)为初态零物理推进预览。本轮按用户要求不制作新视频。

采用 `contact_weld_v1` 接触辅助抓持、CPU float64、25 ms World tick / 40 子步、`use_contact_island=False`。普通接触最大 0.45776 mm、合格夹指最大 0.31197 mm，原生上限仍为 1 / 2 mm，终态安静保持仍为 0.5 s。证明仅覆盖该 seed、冻结源码及配置，不扩展为纯摩擦、默认 400 Hz、连续时间或整个随机参数域保证。

参考 [Logica 官方六步解法](https://www.logicagiochi.com/pub/media/wysiwyg/pdf/Ferri-di-madrid.pdf)核对折合及沿外缘取环顺序。机器人交接、系统侧平移与放置动作来自本地规划及真实执行验证。
