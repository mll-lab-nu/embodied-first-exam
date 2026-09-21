# Cast Keyhole

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

开口金叉与封闭银色阶梯孔的双刚体谜题；ALOHA 从预抓取开始，通过真实接触后辅助抓持，沿当前实例的可行路线分离。

源码：[geometry.py](../../../topogym/tasks/cast_keyhole/geometry.py) · [scene.py](../../../topogym/tasks/cast_keyhole/scene.py) · [variants.py](../../../topogym/tasks/cast_keyhole/variants.py) · [variant_runner.py](../../../topogym/tasks/cast_keyhole/variant_runner.py) · [agent_adapter.py](../../../topogym/tasks/cast_keyhole/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/cast_keyhole.yaml)；场景入口：`python -m demos.environment_bootstrap.cast_keyhole`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

正式目录只收录最终 F1/F2/F3 三个家族各一个已验收代表，共三个变体、21 个 MP4。每组包含六路同步相机与一份拼屏，覆盖预抓取、接触后辅助抓持到完全分离并双臂持稳，不含拾取和放桌释放。新增 v2 三组来自各自已有成功物理状态的重渲染，未增加物理执行次数。旧 baseline 与旧固定代表已转入历史证据目录，不与新实例混用验收证据；不宣称官方全部路线均已复现。

## 变体与下一步

v2 三机构 × 三外形，支持 fixed/parameterized、逐实例 seed、姿态重定向、几何/机器人检查及保存/恢复；KeyholeVariantRunner 执行双步长物理验收。三个随机实例六次物理运行通过，export_ready=false；新实例仍须独立验收。

## 当前视频

目录统一采用 `demos/cast_keyhole/varaition_<family>/<camera>/`，每个家族只收录一个最终代表，每个相机目录仅一份 MP4。目录不按版本或 seed 扩展；具体版本、样式及 seed 保留在归档元数据中用于复现。旧 baseline、开发过程及其他 seed 不进入正式展示。

| 变体 | 结构与路线 | 同步视频 |
| --- | --- | --- |
| f1_long_stroke | 长行程；23.833 s、286 帧 | [近景](../../../demos/cast_keyhole/varaition_f1_long_stroke/detail/2026-09-21_f1_long_stroke_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f1_long_stroke/four_views/2026-09-21_f1_long_stroke_v2_four_views.mp4) |
| f2_eccentric_window | 偏心绕行；24.917 s、299 帧 | [近景](../../../demos/cast_keyhole/varaition_f2_eccentric_window/detail/2026-09-21_f2_eccentric_window_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f2_eccentric_window/four_views/2026-09-21_f2_eccentric_window_v2_four_views.mp4) |
| f3_turnback | 推进、转向、回退后侧出；28.333 s、340 帧 | [近景](../../../demos/cast_keyhole/varaition_f3_turnback/detail/2026-09-21_f3_turnback_v2_detail.mp4) · [拼屏](../../../demos/cast_keyhole/varaition_f3_turnback/four_views/2026-09-21_f3_turnback_v2_four_views.mp4) |

全部视角直链见 [Demo 目录](../../../demos/README.md)。视频通过 SHA-256、完整解码、帧数/时长同步、实际状态一致性和相机 FK 检查；各家族证据含 1 ms / 0.5 ms 两次已通过的物理运行。

## 当前证据

- [2026-09-19_seed_generator_v2](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2)
- [2026-09-21_family_v2_multiview](../../../runs/demo_metadata/cast_keyhole/2026-09-21_family_v2_multiview/README.md)

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
