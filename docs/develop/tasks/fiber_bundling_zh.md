# 光纤收束

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

固定电源终端和被动细线保持连续，机器人只操作粗护套，使分叉端先进入闭环并完成整束穿环；需要逐步检查细线禁碰、抓持及受载稳定性。

源码：[generation.py](../../../topogym/tasks/fiber_bundling/generation.py) · [robot_sequence.py](../../../topogym/tasks/fiber_bundling/robot_sequence.py) · [ik_search.py](../../../topogym/tasks/fiber_bundling/ik_search.py) · [variant_trial.py](../../../topogym/tasks/fiber_bundling/variant_trial.py) · [variant_demo.py](../../../topogym/tasks/fiber_bundling/variant_demo.py)。
参数入口：[任务卡](../../../configs/task_cards/fiber_bundling.yaml)；场景入口：`python -m demos.environment_bootstrap.fiber_bundling`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

正式视频为 8 芯、环内半径 13.5 mm、细铜杆支架，无 UI 三视角各 177 秒。它展示既有完整物理轨迹，末态仍保持辅助夹持；严格全程时间步线形对照未通过，也不为任意随机线数和孔径提供资格。

## 变体与下一步

稀疏/标准/密集是线数家族，不要求三种 IK 机制。fixed 使用 4/8/16 芯和 R=13.5 mm；parameterized 分别采样 4–6/7–10/11–16 芯及 R=12.8–15.0 mm。300 个 seed 初态几何通过；IK、禁碰、受载稳定性、完整穿环和时间步对照必须逐实例补齐。

## 当前证据

- [2026-09-18_standard_08_r13p5mm_clean_v1](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1)
- [2026-09-19_variant_generation_audit](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.generation \
  --seed 42 --family standard --mode parameterized \
  --output runs/environment-solvability/fiber_bundling/generated_seed42
```
