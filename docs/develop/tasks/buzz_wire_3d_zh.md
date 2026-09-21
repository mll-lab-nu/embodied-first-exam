# 3D Buzz Wire：三个已验收的紧凑单臂变体

截至 2026-09-21，**F1、F2、F3 的 70% 玩具版场景、完整连续 IK、双步长物理执行与三视角完整 demo 均已完成**。本次补齐 F1 和 F3；F2 沿用此前通过的同一实例与物理运行。后续参数变体以这三套固定场景及 IK 为起点。

## 当前完整 demo

| 固定家族 | 每路时长 / 帧数 | 三路同步 MP4 | 种子与证据 |
| --- | --- | --- | --- |
| F1：两座高拱与中央深谷 | 44.60 s / 1115 | [全景](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/agentview/2026-09-21_F1_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/front_oblique/2026-09-21_F1_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/wrist/2026-09-21_F1_compact_toy_s70_v2_full_wrist.mp4) | [IK 种子](../../../assets/tasks/buzz_wire_3d/F1_compact_toy_s70_v2/robot_seed.json) · [验收](../../../runs/demo_metadata/buzz_wire_3d/2026-09-21_F1_compact_toy_s70_v2_full/README.md) |
| F2：三连回折、错层八字、竖直 W | 103.04 s / 2576 | [全景](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/agentview/2026-09-20_F2_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/front_oblique/2026-09-20_F2_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/wrist/2026-09-20_F2_compact_toy_s70_v2_full_wrist.mp4) | [IK 种子](../../../assets/tasks/buzz_wire_3d/F2_compact_toy_s70_v2/robot_seed.json) · [验收](../../../runs/demo_metadata/buzz_wire_3d/2026-09-20_F2_compact_toy_s70_v2_full/README.md) |
| F3：水平梳齿、竖直 W、侧向 Ω、倾斜螺旋 | 98.36 s / 2459 | [全景](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/agentview/2026-09-21_F3_compact_toy_s70_v2_full_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/front_oblique/2026-09-21_F3_compact_toy_s70_v2_full_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/wrist/2026-09-21_F3_compact_toy_s70_v2_full_wrist.mp4) | [IK 种子](../../../assets/tasks/buzz_wire_3d/F3_compact_toy_s70_v2/robot_seed.json) · [验收](../../../runs/demo_metadata/buzz_wire_3d/2026-09-21_F3_compact_toy_s70_v2_full/README.md) |

全部为 25 fps、960 × 720。从预穿环、预抓取位置开始，完成夹紧保持、整条迷宫通行、末端直立段松手、撤臂和重力落稳；不包含桌面拾取或初次穿环。视频按 `demos/buzz_wire_3d/varaition_<id>/<camera>/` 保存，每个叶目录一份独立 MP4。三路来自各自同一次主运行的实测状态重渲染，包含真实被动夹爪关节，不增加物理成功次数。

## 场景和动作

保留已有固定关卡及顺序，迷宫、环、杆和手柄按原设计线性缩至 70%；Panda + Robotiq 2F-85 的尺寸、安装位及关节限位不变。底座为削角分层浅木板、小方木线脚，铜色轨道、银色套环与木柄；不包含电路板、电池或线缆摆设。F1/F2 底座为 520.1 × 368.9 × 17.5 mm，F3 为 520.1 × 385 × 17.5 mm。

- **F1 高低双拱**：两座高拱、中央深谷及前后错位，反复爬升、俯冲和转腕；不同于旧基础照片布局。连续 IK 采用可覆盖全程的正向第五关节分支，保留原始关节限位。
- **F2 错层八字**：三连回折 → 错层八字 → 竖直 W，连续通过三个关卡。
- **F3 换平面**：水平梳齿 → 竖直 W → 侧向 Ω → 倾斜螺旋，连续通过四个关卡；本次沿用既有紧凑场景的尺寸、摆位和抓持点，重新求解完整 IK。

抓持通过真实接触摩擦，无焊接或环杆外力驱动。机械臂采用有限力矩关节控制，使用仿真中的实际夹爪/圆环位姿更新抓持变换；本交付属于状态反馈参考控制，不代表视觉 agent 已自主解出任务。导线为固定刚体，未建模铜线弹性或蜂鸣电路。

## 可解性与物理验收

三个实例均通过完整工具连续净空、密集机器人 IK/碰撞检查、Genesis CPU 64 位物理执行，以及 4 ms / 2 ms、各 16 子步的独立复验。每次执行均完成全部关卡与释放静置；受控通行零触线、双侧夹爪持续接触，机器人对固定玩具和自身无记录穿透。接触检查在每个外层物理步执行，不等同于积分子步连续碰撞证明。

| 固定实例 | 密集 IK 位姿数 | 两步长受控阶段最大位置差 | 完整执行 / 减半步长 |
| --- | ---: | ---: | --- |
| F1 | 2887 | 0.0805 mm | 通过 / 通过 |
| F2 | 13549 | 0.1154 mm | 通过 / 通过 |
| F3 | 11333 | 0.0988 mm | 通过 / 通过 |

F1 的腕相机采用固定于手部的偏置 `[-0.070, 0, 0.015] m`，保证末端释放可见；只改变渲染视角。所有正式视频通过 SHA-256、完整解码及同组帧数/时长一致性检查，配置、状态、资产、源码快照和验收报告均独立归档。新增实现通过 30 项任务回归；腕相机参数修改后另通过 6 项机器人回归。

## 后续变体从三个固定 IK 派生

机器可读入口：[fixed_compact_toy_v2.yaml](../../../configs/task_variants/buzz_wire_3d/fixed_compact_toy_v2.yaml)。每个家族绑定固定 `scene_config.yaml`、完整 `robot_seed.json`、资格报告及 SHA-256，可显式选取并重载。原始设计与候选范围仍在 [F1](../../../configs/task_variants/buzz_wire_3d/vertical_wave_v1.yaml)、[F2](../../../configs/task_variants/buzz_wire_3d/over_under_eight_v1.yaml)、[F3](../../../configs/task_variants/buzz_wire_3d/plane_switch_v1.yaml)；其未缩放范围及其他原型不因本次三个实例通过而获得资格。

后续实现按以下约束派生：

1. 先选择 F1/F2/F3 固定构型，保持关卡数、关卡顺序和整段通行要求。
2. 在所选场景附近微调转弯半径、跨度/高度、底座 pose 等参数，以对应的抓持变换和 IK 分支作规划初值；不能等比例缩放关节角。
3. 对新几何重新求解连续 IK，检查完整工具、机器人、桌面及跨关卡碰撞，再执行完整摩擦抓持、释放静置和半步长复验；失败保留原因并拒绝该实例。
4. 保存新场景、资产、种子和独立资格。**不继承母实例的成功标签。**

当前已冻结三个确认可解的派生起点；通用随机参数采样器及可保证成功的参数范围尚未完成。纯外观变化也需核对物理资产未改变，不能误改摩擦或密度。

## 加载与复现

以下输出目录需使用新名称。将 `F1` 替换为 `F2` 或 `F3` 即可选择其他固定家族。

```bash
# 重载固定场景，生成资产并检查完整工具几何；加 --render 可生成静态预览。
PYOPENGL_PLATFORM=egl PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.buzz_wire_3d_compact_wood \
  --family F1 --style toy-v2 \
  --output runs/environment_bootstrap/buzz_wire_3d/F1_toy_v2_review

# 从冻结 IK 生成密集计划。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_plan \
  --seed-plan assets/tasks/buzz_wire_3d/F1_compact_toy_s70_v2/robot_seed.json \
  --output runs/environment-solvability/buzz_wire_3d/F1_toy_v2_replan
```

完整物理复验使用 `robot_runtime --plan <计划目录> --output <主运行目录>`，再加 `--dt 0.002` 运行独立复验；`robot_verify` 对照两次执行。`robot_render` 从通过的实测轨迹重渲染，`robot_archive` 负责解码、证据复制和目录登记。各家族的完整命令输入、配置与运行时源码见上表归档。

现有[基础实例 agent adapter](../modules/buzz_wire_agent_adapter_zh.md)对应较早的基础布局和短程协议验证，尚未将三个新版家族接入自主 agent 完整通行验收。
