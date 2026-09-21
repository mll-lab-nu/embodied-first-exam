# Cast Coil

更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

ALOHA 双臂将分离的金银卷绕零件装配成整体，放桌、释放、撤手并静置；也保留拆解目标。当前原型不等于官方八步路线复刻。

源码：[geometry.py](../../../topogym/tasks/cast_coil/geometry.py) · [scene.py](../../../topogym/tasks/cast_coil/scene.py) · [variants.py](../../../topogym/tasks/cast_coil/variants.py) · [robot_demo.py](../../../topogym/tasks/cast_coil/robot_demo.py) · [robot_archive.py](../../../topogym/tasks/cast_coil/robot_archive.py) · [agent_adapter.py](../../../topogym/tasks/cast_coil/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/cast_coil.yaml)；场景入口：`python -m demos.environment_bootstrap.cast_coil`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

视频按 `demos/cast_coil/varaition_<变体 ID>/<camera>/` 保存，`varaition_` 沿用项目约定拼写；基础装配版为 `varaition_baseline_assembly`。每个视角只保留一份独立 MP4，配置、轨迹和验收报告放在 `runs/demo_metadata/cast_coil/`。`robot_archive` 支持 `--variant-id` 指定代表款目录，默认按实际几何 ID 区分实例；保持双步长物理验收要求，生成直接视频链接，不生成 HTML。单步长通过的补录会单独注明资格范围。

## 当前状态与边界

基础装配版有 33.15 秒五视角和半时间步检查，含预抓取及接触后辅助抓持。agent adapter 从 home 与桌面自由物体开始，不启用相同的辅助抓持；其 pilot evaluator 通过也不等于完整物理资格。

## 变体与下一步

cast_coil_seed_v2 固定三种 9 mm 核心：偏心回转、45°回转→错位→45°回转、轴向螺旋回转；族内尺寸、位置/yaw、质量条件域联动。48 个几何样本、12 个随机双臂规划通过；新代表 6 次物理运行仅 4 次满足严格归档门槛，尚无全随机域物理保证。

## 当前证据

- [2026-09-17_aloha_full](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full)
- [2026-09-19_seed_generator_validation_v2](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 生成入口

输出必须使用新目录；接受目录以结果文件为准，不能假定总是 `attempt_00`。

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.variants \
  --seed 42 --output runs/environment-solvability/cast_coil/seed42
```
