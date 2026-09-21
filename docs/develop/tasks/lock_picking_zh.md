# 开锁

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

Panda + Robotiq 从承托架抓起钥匙，穿过被动锁片、执行必要回退，抵达 END 后释放静置。基础版盘距 150 mm、三齿、两次必要回退。

源码：[runner.py](../../../topogym/tasks/lock_picking/runner.py) · [planner.py](../../../topogym/tasks/lock_picking/planner.py) · [certificate.py](../../../topogym/tasks/lock_picking/certificate.py) · [evaluator.py](../../../topogym/tasks/lock_picking/evaluator.py) · [variants.py](../../../topogym/tasks/lock_picking/variants.py) · [verify_variants.py](../../../topogym/tasks/lock_picking/verify_variants.py) · [agent_adapter.py](../../../topogym/tasks/lock_picking/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/lock_picking.yaml)；场景入口：`python -m demos.environment_bootstrap.lock_picking`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

标准外观三视角 159.35 秒来自成功物理状态重渲染；夹爪被动连杆按记录开合量重建，没有新增一次动力学成功。runner、planner、certificate、grasp、oracle、evaluator 均由任务包持有。

## 变体与下一步

F1/F2/F3 为 1/2/3 次回退家族，含 S/M/L 固定代表；支持具名 seed、条件尺寸域、确定性拒绝重试和保存/重载。256 个 seed 几何/IK 通过，随机后代的机器人场景碰撞、接触动力学与完整流程仍待验收。

## 当前证据

2026-09-21 按 `varaition_<id>/<camera>/` 整理视频。标准外观仍保留完整三视角；F1/F3 恢复已有正斜视角 IK 预演，文件名含 `kinematic`，不计为完整物理 demo。

- [2026-09-18_standard_150mm_purple_trace_v1](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1)
- [2026-09-19_seed_generator_v1](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.lock_picking.variants --seed 42 --output runs/my_lock_instance
```
