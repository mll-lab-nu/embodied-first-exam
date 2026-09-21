# 马蹄环

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

双马蹄通过独立链环连接，ALOHA 在重力下翻转、折合、交接、抓环、取出并释放到桌面。使用预抓持及接触确认后的辅助抓持。

源码：[geometry.py](../../../topogym/tasks/horseshoe_ring/geometry.py) · [scene.py](../../../topogym/tasks/horseshoe_ring/scene.py) · [physical_demo.py](../../../topogym/tasks/horseshoe_ring/physical_demo.py) · [gravity_demo.py](../../../topogym/tasks/horseshoe_ring/gravity_demo.py) · [variant_generator.py](../../../topogym/tasks/horseshoe_ring/variant_generator.py) · [variant_pipeline.py](../../../topogym/tasks/horseshoe_ring/variant_pipeline.py) · [agent_adapter.py](../../../topogym/tasks/horseshoe_ring/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/horseshoe_ring.yaml)；场景入口：`python -m demos.environment_bootstrap.horseshoe_ring`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

基础版五视角 113.7 秒；同代码 2 ms / 1 ms 独立完整执行通过。F1 上方接近、F2 外侧接近、F3 后方接近均已补齐完整五视角，分别 129.7 / 125.8 / 119.7 秒；它们来自原成功物理状态重渲染，仅保留原 2 ms 验收范围。

## 变体与下一步

三个接近路线家族，围绕已成功中心做小范围条件采样。variant_generator 产生实例，variant_pipeline 做生成、重载、完整物理验收及拒绝重试。三族各有条件域随机实例通过 2 ms，新随机实例仍缺 1 ms 复验；非圆环形状池尚未开放。

## 当前证据

正式目录：`demos/horseshoe_ring/varaition_baseline/<camera>/`、`varaition_f1/<camera>/`、`varaition_f2/<camera>/`、`varaition_f3/<camera>/`，共 20 份独立 MP4。[全部视角与证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-21_variation_restore_v1/README.md)。F1/F2/F3 低位相机统一移到桌面上方，改善遮挡及落桌画面的可见性；五路使用同一次执行的相同帧与时间戳。


- [2026-09-18_gravity_replanned_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1)
- [2026-09-18_timestep_validation_v1](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_timestep_validation_v1)
- [2026-09-19_variant_generator_v2](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
# 仅产生一个候选实例描述，不运行机器人，不生成数据集或视频。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.variant_generator \
  --seed 42 --family F2 --output runs/variant_checks/horseshoe_seed42.json
```
