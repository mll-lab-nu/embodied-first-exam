# Cast Keyhole

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

开口金叉与封闭银色阶梯孔的双刚体谜题；ALOHA 从预抓取开始，通过真实接触后辅助抓持，沿当前实例的可行路线分离。

源码：[geometry.py](../../../topogym/tasks/cast_keyhole/geometry.py) · [scene.py](../../../topogym/tasks/cast_keyhole/scene.py) · [variants.py](../../../topogym/tasks/cast_keyhole/variants.py) · [variant_runner.py](../../../topogym/tasks/cast_keyhole/variant_runner.py) · [agent_adapter.py](../../../topogym/tasks/cast_keyhole/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/cast_keyhole.yaml)；场景入口：`python -m demos.environment_bootstrap.cast_keyhole`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

当前基础物理实例有 23.917 秒多视角完整分离视频。2026-09-21 同时恢复加长穿齿、偏心绕行、转后回退三套已有固定代表，各自七路视频归入 `demos/cast_keyhole/varaition_<id>/<camera>/`；这些视频对应原固定代表，不冒充 v2 随机样本。末态双臂仍持稳零件，不含最终释放；也不宣称官方全部路线均已复现。

## 变体与下一步

v2 三机构 × 三外形，支持 fixed/parameterized、逐实例 seed、姿态重定向、几何/机器人检查及保存/恢复；KeyholeVariantRunner 执行双步长物理验收。三个随机实例六次物理运行通过，export_ready=false；新实例仍须独立验收。

## 当前证据

- [2026-09-17_current_instance_physical](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical)
- [2026-09-19_seed_generator_v2](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variants sample --seed 19
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variants generate \
  --seed 19 --family F1 --style A --output runs/keyhole_seed19
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_runner \
  --spec runs/keyhole_seed19/attempt_00/episode_spec.json \
  --output runs/keyhole_seed19_physics
```
