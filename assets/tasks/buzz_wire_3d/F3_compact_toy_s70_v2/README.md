# F3 · 紧凑玩具版固定代表

水平梳齿、竖直 W、侧向 Ω、倾斜螺旋。保留固定构型，70% 等比例尺寸，削角分层木底座、小木块线脚、铜色轨道和银环木柄。机器人保持原尺寸。

已通过完整连续 IK、4 ms / 2 ms 摩擦抓持物理执行和末端释放 / 静置。三路视频为同一次主运行的实测状态重渲染，各 98.36 秒、2459 帧、25 fps；包含真实夹爪被动关节。预穿环 / 预抓取起点，不含桌面拾取和初始穿环。

[全景](../../../../demos/buzz_wire_3d/varaition_f3_plane_switch/agentview/2026-09-21_F3_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../../demos/buzz_wire_3d/varaition_f3_plane_switch/front_oblique/2026-09-21_F3_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../../demos/buzz_wire_3d/varaition_f3_plane_switch/wrist/2026-09-21_F3_compact_toy_s70_v2_full_wrist.mp4)

[验收与归档](../../../../runs/demo_metadata/buzz_wire_3d/2026-09-21_F3_compact_toy_s70_v2_full/README.md)。`scene_config.yaml` 是固定场景，`robot_seed.json` 是完整 IK 参考，`robot_qualification.json` 固定配置、种子及报告哈希。后续参数变体以该种子作为初值，变化后的实例需要重新规划及验收。

场景预览：

```bash
PYOPENGL_PLATFORM=egl PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.buzz_wire_3d_compact_wood \
  --family F3 --style toy-v2 --render \
  --output runs/environment_bootstrap/buzz_wire_3d/F3_toy_v2_review
```

复用 IK（使用新的输出目录）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/F3_compact_toy_s70_v2/robot_seed.json \
  --output runs/environment-solvability/buzz_wire_3d/F3_toy_v2_replan
```
