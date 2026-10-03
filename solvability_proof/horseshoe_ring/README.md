# 马蹄环可解性证明

当前 **easy / medium / hard 的 seed 0 全部已验收，三档 3/3**。每档从默认 ALOHA home 连续执行到原生 `task_success=True`，独立逐 tick 审计接受，零回溯、零抓持丢失。

| 变体 | 仿真时长 | 完整记录状态 | 证明与复现 |
| --- | --- | --- | --- |
| easy | 275.2 s | 11,009 | [完整证明](2026-10-03_easy/README.md) |
| medium | 264.5 s | 10,581 | [完整证明](2026-10-03_medium/README.md) |
| hard | 252.4 s | 10,097 | [完整证明](2026-10-03_hard/README.md) |

从仓库根目录运行，输出目录必须尚不存在：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_horseshoe_oracle.py \
  --variant medium --seed 0 --output runs/test_results/horseshoe_medium_new
```

将 variant 和输出路径改为 hard 可运行 hard。正式入口读取[已验收配方](recipes.json)，核对模型、判据与五份规划输入，冻结源码、执行反馈 IK 并自动独立审计。正式策略不导入或调用 calibration-tools。[汇总](summary.json)保留各次独立执行身份。

建模调整服务于抓取、折合及释放路线。三档完整马蹄沿环法向直接穿出的充分阻挡余量分别为 19.160 / 21.372 / 1.855 mm；马蹄、链环、环线径和原生接触／成功判据不变。当前初态 Nyx 截图：[medium](2026-10-03_medium/evidence/supporting/medium_v5_model_screenshot/frames/479c139ab94148b3a618c99d1bffa9d5/raw.png) · [hard](2026-10-03_hard/evidence/supporting/hard_v8_model_screenshot/frames/7e512145340c46bfa739b5147867ea84/raw.png)，均为零物理推进预览。

采用 `contact_weld_v1` 接触辅助抓持、CPU float64、25 ms / 40 子步、`use_contact_island=False`。资格仅覆盖各档 seed 0 的冻结源码和配置，不扩展为纯摩擦、默认 400 Hz、连续时间或整个参数域保证。用户已免除本轮 medium / hard 视频；easy 的原有四路完整视频保留。
