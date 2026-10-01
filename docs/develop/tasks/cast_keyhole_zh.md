# Cast Keyhole

更新：2026-09-28。全项目进度见[当前进度](../../progress/current_zh.md)，历史正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

开口金叉与封闭银色阶梯孔的双刚体谜题。当前标准场景从桌面物体与 ALOHA 默认 home 开始；目标为整件银色零件进入实例固定的绿色区域，金色件留在分界另一侧并持稳，允许保留抓持。

源码：[当前 Task](../../../topogym/tasks/cast_keyhole/common.py) · [policy 与验证说明](../../../topogym/planning/cast_keyhole/README.md) · [双臂 IK 规划](../../../topogym/planning/cast_keyhole/kinematics.py) · [运行入口](../../../scripts/oracle_runners/run_cast_keyhole_policy.py)。运行使用标准 `Env` / `SegmentRunner`，不再使用旧场景或 variant runner 入口。

## 当前状态与边界

本轮可解性证明已正式完成 **3/3**：F1 / easy、F2 / medium、F3 / hard 均从当前默认 home 与桌面初态连续执行至 `task_success=True`，独立逐 tick 复核分别覆盖 19,547、18,385、21,492 个状态并通过。全部动作、数值状态、接触抓持、源码与配置身份均已保存，无 RGB/视频。见 [实际成功报告与复现命令](../../../solvability_proof/cast_keyhole/2026-09-28/README.md)、[机器可读证据汇总](../../../solvability_proof/cast_keyhole/2026-09-28/summary.json) 和 [policy 说明](../../../topogym/planning/cast_keyhole/README.md)。

本轮范围为默认参数、seed 0、ALOHA、CPU 双精度、显式 25 ms World tick / 40 子步，以及实际双指接触触发的 `contact_weld_v1` 辅助抓持。资格绑定几何和目标区身份，不扩大为随机参数域、其他时序或纯摩擦抓持证明。

旧正式目录收录 F1/F2/F3 各一个历史代表。历史流程覆盖预抓取、接触辅助抓持到分离持稳，不含当前桌面拾取和绿色目标区后缀；不能继承为本轮成功证据。以下视频与旧双步长资格仅描述历史实例。

## 变体与执行线路

当前冻结三档为 easy / F1 长行程、medium / F2 偏心窗口、hard / F3 转向回退。逐档步骤与底层 action / IK 线路见[变体解法研究](task_variant_solutions_action_ik_zh.md#keyhole)。对应正式运行分别是 `trial_38_easy_qualified`、`trial_35_medium_qualified`、`trial_37_hard_qualified`；每档均从 home 连续执行拾取、真实换抓、解锁、目标区搬运和稳定窗口。

## 历史视频

目录统一采用 `demos/cast_keyhole/varaition_<family>/<camera>/`，每个家族只收录一个最终代表，每个相机目录仅一份 MP4。目录不按版本或 seed 扩展；具体版本、样式及 seed 保留在归档元数据中用于复现。旧 baseline、开发过程及其他 seed 不进入正式展示。

| 变体 | 结构与路线 | 同步视频 |
| --- | --- | --- |
| f1_long_stroke | 长行程；23.833 s、286 帧 | [近景](../../../demos/cast_keyhole/varaition_f1_long_stroke/detail/2026-09-21_f1_long_stroke_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f1_long_stroke/four_views/2026-09-21_f1_long_stroke_v2_four_views.mp4) |
| f2_eccentric_window | 偏心绕行；24.917 s、299 帧 | [近景](../../../demos/cast_keyhole/varaition_f2_eccentric_window/detail/2026-09-21_f2_eccentric_window_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f2_eccentric_window/four_views/2026-09-21_f2_eccentric_window_v2_four_views.mp4) |
| f3_turnback | 推进、转向、回退后侧出；28.333 s、340 帧 | [近景](../../../demos/cast_keyhole/varaition_f3_turnback/detail/2026-09-21_f3_turnback_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f3_turnback/four_views/2026-09-21_f3_turnback_v2_four_views.mp4) |

全部视角直链见 [Demo 目录](../../../demos/README.md)。视频通过 SHA-256、完整解码、帧数/时长同步、实际状态一致性和相机 FK 检查；各家族证据含 1 ms / 0.5 ms 两次已通过的物理运行。

## 历史证据

- [2026-09-19_seed_generator_v2](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2)
- [2026-09-21_family_v2_multiview](../../../runs/demo_metadata/cast_keyhole/2026-09-21_family_v2_multiview/README.md)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 当前运行入口

输出必须使用新目录。把 `easy` 替换为 `medium` / `hard` 可分别运行。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_cast_keyhole_policy.py \
  --variation easy --backend cpu --tick .025 --speed .6 --horizon 900 \
  --output runs/test_results/keyhole_easy_new
```

显式 `.025` 使用 40 个积分子步，保留 0.625 ms 积分与 40 Hz action，但每 tick 接触、assist、终态和回溯采样为 40 Hz；默认 `.0025` 为 400 Hz。辅助抓持须由真实双指接触触发，本轮不宣称纯摩擦抓持资格。
