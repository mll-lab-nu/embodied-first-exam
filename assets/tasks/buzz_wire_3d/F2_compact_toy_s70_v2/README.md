# F2 · photo-style wooden toy v2

按用户参考照片设计：削角、两层收边浅木底座，小方木线脚，铜色轨道，银色套环与木柄；无电池、电路板或线缆摆设。保留 70% 尺寸和原关卡布局。

`scene_config.yaml` 可独立加载。2026-09-20 本实例已通过完整连续 IK、4 ms / 2 ms 摩擦抓持物理执行及末端释放 / 静置；场景尺寸、摆位和抓持点保持原配置。预穿环 / 预抓取起点，不含桌面拾取及初始穿环。

运行：`PYOPENGL_PLATFORM=egl PYTHONPATH=. .venv-gs121-nyx/bin/python demos/environment_bootstrap/buzz_wire_3d_compact_wood.py --style toy-v2 --family F2 --output runs/environment_bootstrap/buzz_wire_3d/F2_toy_v2_review --render`。

[预览与验证](../../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_photo_toy_s70_v2_scene_preview/README.md)。

完整 demo（每路 103.04 秒、2576 帧、25 fps，来自同一物理运行的实测状态重渲染）：

[全景](../../../../demos/buzz_wire_3d/agentview/2026-09-20_F2_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../../demos/buzz_wire_3d/front_oblique/2026-09-20_F2_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../../demos/buzz_wire_3d/wrist/2026-09-20_F2_compact_toy_s70_v2_full_wrist.mp4)。

[验收与归档](../../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_F2_compact_toy_s70_v2_full/README.md)。`robot_seed.json` 保存 13549 个通过复核的连续 IK 位姿；`robot_qualification.json` 记录原场景、种子和物理报告哈希。此资格仅适用于该实例及保存策略。

复用种子生成计划（使用新的输出目录）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
.venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/F2_compact_toy_s70_v2/robot_seed.json \
  --output runs/environment-solvability/buzz_wire_3d/F2_toy_v2_replan
```
