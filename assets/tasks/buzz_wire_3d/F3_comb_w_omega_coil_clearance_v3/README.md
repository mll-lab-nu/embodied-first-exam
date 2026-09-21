# F3 四关单臂工程实例 v3

固定关卡：水平梳齿 → 竖直 W → 270° 侧向 Ω → 0.75 圈倾斜螺旋。
`robot_seed.json` 包含完整线路、环姿态与偏心、单次抓持变换、IK 引导及接触参数。
它是可复现的规划输入，单独存在不代表物理验收。

相对默认 v2：螺旋半径 45→50 mm、轴向推进 70→80 mm、中心 Y +10 mm；底座深度 527→550 mm；板整体世界 X +80 mm。
同尺寸环、短杆、标准机械臂及原有限位；初始握柄扁面转 -90°，通行中不换抓。
后段允许环中心在孔内偏心，仍要求全工具净空和穿环拓扑独立验收。
18 mm 是弧长滤波尺度，不是最小曲率半径。

复现规划（使用全新输出目录）：

```bash
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/F3_comb_w_omega_coil_clearance_v3/robot_seed.json \
  --output runs/environment-solvability/buzz_wire_3d/F3_recheck/plan
```

规划通过后，用 `robot_runtime` 分别执行 4 ms 和 2 ms，再用 `robot_verify` 对照。
视频从主运行的实测状态生成，见 [任务文档](../../../../docs/develop/tasks/buzz_wire_3d_zh.md)。

本固定实例已通过 4 / 2 ms 双步长完整执行。[归档视频与证据](../../../../runs/demo_metadata/buzz_wire_3d/2026-09-19_F3_comb_w_omega_coil_v3/README.md)；[工程规格](../../../../configs/task_variants/buzz_wire_3d/plane_switch_clearance_v3.yaml)。两次全程受控触线均为 0，同进度位置差最大 0.073 mm。此结论不覆盖其他参数组合。
