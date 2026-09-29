# 3D Buzz Wire：从默认姿态开始的三个单臂变体

> **2026-09-28 当前版本：** 三档端点改为 8 × 8 × 12 mm 细连接块，可穿过约 28.3 mm 内径的工具环；移除工具托架，环与原尺寸握柄直接落在底板上，底板顶面距桌面 142.5 mm。原机械臂模型保持不变。三档 1 秒初始化录像已完成，40 项相关单测通过；Medium 另完成落板稳定性、采样接近路径和双指接触空间检查。实际验证范围与录像见[实施记录](../../../runs/test_results/buzz_deck_rest_20260928/README.md)。下述 9 月 27 日整体抬高版及历史完整 demo 保留各自版本含义。

> **2026-09-27 更新：** 三档冻结布局的底座、线路与起终点支撑均整体再抬高 40 mm，medium 初始化录像已补录。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


F1/F2/F3 已更新为 **home_lab_v4**：使用公共 `topogym.recording` 和 `lab_default_v1` 实验室背景，从机器人配置的默认 home 姿态开始，连续完成接近、拾取、全部关卡、支撑放回、松爪撤臂与静置。三个新执行均通过 4/2 ms 独立物理复验，完整 IK 和九路正式视频已冻结。

2026-09-22 起 F1 由双拱改为 **三拱**（设计规格 `vertical_wave_v1.yaml` 的 `F1_triple_arch`：3 座高拱夹 2 个深谷，比双拱多 1 拱 1 谷，即多 2 道竖直弯；半径由 55 mm 改为 50 mm，拱顶 250 mm、谷底 80 mm、前后跨度 100 mm 不变）。三拱版沿用 70% 紧凑玩具版、同一工具和抓持，重新走完搜索、拾放、home 接近、4/2 ms 复验与公共录制，包为 `F1_triple_compact_toy_s70_home_lab_v1`。旧双拱包 `F1_compact_toy_s70_home_lab_v4` 与其归档保留为历史证据，不再是默认展示代表。

## 当前完整 demo

| 固定家族 | 每路时长 / 帧数 | 三路同步 MP4 | 种子与证据 |
| --- | --- | --- | --- |
| F1：三座高拱与两个深谷 | 96.57 s / 2897 | [全景](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/agentview/F1_triple_home_lab_v1_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/front_oblique/F1_triple_home_lab_v1_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/wrist/F1_triple_home_lab_v1_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/archive_manifest.json) |
| F2：三连回折、错层八字、竖直 W | 136.63 s / 4099 | [全景](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/agentview/F2_home_lab_v4_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/front_oblique/F2_home_lab_v4_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/wrist/F2_home_lab_v4_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F2_compact_toy_s70_home_lab_v4/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/archive_manifest.json) |
| F3：水平梳齿、竖直 W、侧向 Ω、倾斜螺旋 | 131.47 s / 3944 | [全景](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/agentview/F3_home_lab_v4_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/front_oblique/F3_home_lab_v4_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/wrist/F3_home_lab_v4_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F3_compact_toy_s70_home_lab_v4/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/archive_manifest.json) |

全部为 30 fps；公共外部相机为 1280 × 720，腕部为 960 × 720。每族三路来自同一次新的连续物理执行，第一条实测状态的七个主臂关节与 `robot_control.home.qpos` 一致，夹爪按 home 开度张开，时间为 0。记录完整机器人关节（含被动夹爪关节）和工具位姿，再由公共模块零积分重渲染；没有拼接 home 片头，不增加物理执行次数。

环初始已穿在线路上，由底座实体木托支撑；机械臂张爪且未抓持。视频包含实际拾取和放回，不包含首次穿环。正式目录每族每视角一份 MP4，共九份；替换记录和旧版副本位于归档元数据。

## 场景与支撑

保留 70% 紧凑玩具版的全部关卡及顺序，Panda + Robotiq 2F-85 的尺寸、安装位及物理关节限位不变。底板与导线整体同步抬升；底板采用削角分层浅木材、铜色导线、银色套环、木柄及木托，无电池或电路板。F1/F2 底板为 520.1 × 368.9 × 17.5 mm，F3 为 520.1 × 385 × 17.5 mm。

F1/F3 使用倾斜柄托；F2 终点用固定在底座上的 V 形环托和柄颈托，保留机械臂可达倾角。与支撑拾放 v3 相比，F2 整体沿世界 X 移动 -30 mm、Y 移动 +25 mm，避开默认姿态下夹爪与线路的干涉；完整主路径与首尾 IK 已重算并重新验收。F3 的玩具摆位不变。F1 三拱版的中央拱顶恰好落在默认 home 张爪正下方（双拱版此处是深谷），因此相对双拱摆位沿世界 X 移动 -20 mm、Y 移动 +70 mm，让第二个深谷落在张爪下方，home 张爪与线路净空 20 mm；向 -Y 移动会使终点立柱一侧的 IK 超出姿态容差，已排除。

| 家族 | 底座垫高 | 世界 X / Y | 主路径 IK 位姿数 | 两步长通行最大位置差 | 两次运行最大工具接触穿透 |
| --- | --- | --- | ---: | ---: | ---: |
| F1 | 25 mm | -0.050 / +0.070 m | 4571 | 0.0795 mm | 0.3251 mm |
| F2 | 40 mm | -0.010 / +0.025 m | 13549 | 0.2964 mm | 0.3794 mm |
| F3 | 25 mm | -0.010 / +0.000 m | 11333 | 0.1015 mm | 0.3492 mm |

接触穿透包含抓持和木托接触，是每个外层物理步的实测值，不能视为积分子步的连续上界。F2 松爪后从实测关节姿态重新求解并审计撤臂路径，避免抓持反馈改变冗余分支后跳回名义关节轨迹；实际撤臂 IK 随包保存。

## 动作与验收

1. 机械臂从配置 home 张爪开始，工具在木托上无抓持静置 2 秒。
2. 沿经过关节限位及碰撞审计的连续路径接近；张爪对准木柄，缓慢闭合、提离木托。
3. 通过全部关卡，检查触线、双侧夹爪接触与机器人碰撞。
4. 放到终点木托，确认连续支撑接触后松爪。
5. 张爪退开并至少静置 4 秒，检查末态速度、位置及支撑接触。

三族均通过完整工具连续导线净空、密集 IK/碰撞审计及 Genesis CPU 64 位、4 ms / 2 ms、各 16 子步的独立执行。通行阶段无记录触线，双侧夹爪持续接触。抓持依靠真实接触摩擦，无焊接、环杆外力或运行中位姿覆盖。公共 replay 检查 CPU 执行模型与 CUDA/Nyx 录制模型的物理签名一致；归档检查哈希、完整解码、帧数及三视角同步。

这仍是仿真状态反馈参考控制，不代表视觉 agent 自主求解。导线为固定刚体，未模拟铜线弹性和蜂鸣电路。新包保留源配置 producer instance_id；新旧运行通过 execution UUID、run ID 和计划哈希区分，不改写原执行身份。

## 从三个完整 IK 派生

当前机器入口：[fixed_home_lab_v4.yaml](../../../configs/task_variants/buzz_wire_3d/fixed_home_lab_v4.yaml)（F1 条目已指向三拱包，`previous_representative` 记录旧双拱包）。每族保存原执行配置、含 home_approach 的完整 `planning/`、`robot_seed.json`、资格报告及哈希。`fixed_supported_toy_v3.yaml` 只描述历史拾取附近起步、棋盘背景的版本。

后续先选 F1/F2/F3，再微调转弯半径、跨度、高度或底座 pose，保留关卡数与顺序。使用对应 IK 和抓持变换作为初值，不能缩放关节角。每次变化都重新检查默认 home 与张爪净空，重规划接近、拾取、通行、下放与撤臂，并独立执行完整流程和半步长复验；不得继承母实例资格。通用随机采样器及保证成功的参数范围尚未完成。

原始设计候选范围：[F1](../../../configs/task_variants/buzz_wire_3d/vertical_wave_v1.yaml)、[F2](../../../configs/task_variants/buzz_wire_3d/over_under_eight_v1.yaml)、[F3](../../../configs/task_variants/buzz_wire_3d/plane_switch_v1.yaml)。

## 复现与公共录制

在仓库根目录执行，替换 `F1` 可选择 F2/F3，输出目录使用新名称。环境：`.venv-gs121-nyx`；公共 Nyx 录制需要 CUDA。

```bash
# 新的完整物理执行：默认 home → 拾取 → 全关卡 → 放回 → 静置。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_runtime \
  --plan assets/tasks/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1/planning \
  --output runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal

# 同一计划加 --dt 0.002，写入 F1_home_review_refined；随后对照两次执行。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_verify \
  --nominal runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal \
  --refined runs/environment-solvability/buzz_wire_3d/F1_home_review_refined \
  --output runs/environment-solvability/buzz_wire_3d/F1_home_review_suite.json

# 任务适配器只冻结资格、实测状态与资产，不自行取帧或编码。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.recording_adapter snapshot \
  --run runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal \
  --suite runs/environment-solvability/buzz_wire_3d/F1_home_review_suite.json \
  --output runs/recordings/buzz_wire_3d/F1_home_review_source \
  --family F1 --run-id F1_home_review_full

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. PYOPENGL_PLATFORM=egl \
  .venv-gs121-nyx/bin/python -m topogym.recording replay \
  --source runs/recordings/buzz_wire_3d/F1_home_review_source/source_manifest.json \
  --output runs/recordings/buzz_wire_3d/F1_home_review_full --fps 30

# 全片校验后按变体替换正式三视角；旧版保留在归档回滚证据中。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.recording archive \
  runs/recordings/buzz_wire_3d/F1_home_review_full
```

从种子重建使用 `robot_plan --seed-plan .../robot_seed.json`，新计划仍须重新做物理验收。共享录制说明见[模块用法](../modules/recording_module_usage_zh.md)。旧 `robot_render` 已删除；`robot_archive` 仅保留对历史 v3 目录的校验，新演示使用上述公共入口。

现有[基础实例 agent adapter](../../../legacy/cleanup_20260929/docs/develop/modules/buzz_wire_agent_adapter_zh.md)仍对应较早布局和短程协议验证，三个新家族尚未完成自主 agent 完整通行验收。
