# 光纤收束

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

固定电源终端和被动细线保持连续，机器人只操作粗护套，使分叉端先进入闭环并完成整束穿环；需要逐步检查细线禁碰、抓持及受载稳定性。

源码：[generation.py](../../../topogym/tasks/fiber_bundling/generation.py) · [robot_sequence.py](../../../topogym/tasks/fiber_bundling/robot_sequence.py) · [ik_search.py](../../../topogym/tasks/fiber_bundling/ik_search.py) · [variant_trial.py](../../../topogym/tasks/fiber_bundling/variant_trial.py) · [variant_demo.py](../../../topogym/tasks/fiber_bundling/variant_demo.py)。
参数入口：[任务卡](../../../configs/task_cards/fiber_bundling.yaml)；场景入口：`python -m demos.environment_bootstrap.fiber_bundling`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

正式视频已覆盖稀疏 4 芯、标准 8 芯、密集 16 芯三个代表，环内半径均为 13.5 mm、细铜杆支架，每个变体三路无 UI 完整视频。目录为 `demos/fiber_bundling/varaition_<实例名>/<视角>/`；每个相机叶子目录一份 MP4。8 芯原视频直接迁移，4/16 芯从各自成功物理轨迹补录；均以辅助夹持保持末态。三例的两种时间步均完成穿环，严格全程线形对照仅 4 芯通过；这些代表不为任意随机参数提供资格。

## 变体与下一步

稀疏/标准/密集是线数家族，不要求三种 IK 机制。fixed 使用 4/8/16 芯和 R=13.5 mm；parameterized 分别采样 4–6/7–10/11–16 芯及 R=12.8–15.0 mm。300 个 seed 初态几何通过；IK、禁碰、受载稳定性、完整穿环和时间步对照必须逐实例补齐。

## 当前证据

- [稀疏 4 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/agentview/2026-09-21_sparse_04_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/front_oblique/2026-09-21_sparse_04_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/wrist/2026-09-21_sparse_04_r13p5mm_clean_v1_wrist.mp4)，各 116.7 秒。
- [标准 8 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/agentview/2026-09-18_standard_08_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/front_oblique/2026-09-18_standard_08_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/wrist/2026-09-18_standard_08_r13p5mm_clean_v1_wrist.mp4)，各 177 秒。
- [密集 16 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/agentview/2026-09-21_dense_16_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/front_oblique/2026-09-21_dense_16_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/wrist/2026-09-21_dense_16_r13p5mm_clean_v1_wrist.mp4)，各 237.15 秒。
- [2026-09-19_variant_generation_audit](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.generation \
  --seed 42 --family standard --mode parameterized \
  --output runs/environment-solvability/fiber_bundling/generated_seed42
```
