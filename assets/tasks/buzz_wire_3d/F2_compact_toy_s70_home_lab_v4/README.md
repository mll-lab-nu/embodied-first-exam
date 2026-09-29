# F2 默认姿态与公共实验室录制版

`F2_compact_toy_s70_home_lab_v4` 冻结本次从默认 home 开始的新连续执行及完整 IK。新旧执行由 execution UUID、run ID、计划哈希区分；保留原配置的 producer instance_id，不改写原运行身份。

环预先穿在线路上、由实体木托支撑。机械臂从配置 home 张爪开始，经连续接近、实际拾取、全部关卡、支撑放回、松爪撤臂及静置。4/2 ms、各 16 子步独立执行均通过。没有预抓取、焊接或运动中的位姿覆盖。

- `planning/`：可直接交给 `robot_runtime --plan`，包含 home_approach 及全部首尾动作。
- `robot_seed.json`：完整主路径、抓持变换及首尾动作；派生后必须重新验收。
- `scene_config.yaml`：原物理执行配置。实验室视觉覆盖由公共录制预设应用，模型签名一致性已检查。
- `robot_qualification.json`、`timestep_qualification.json`：物理资格、执行身份及证据哈希。
- 若有 `measured_retreat_plan.json`，保存从实际释放姿态求解的撤臂 IK；控制器按配置重新规划实测分支，不能直接跳回名义关节轨迹。
- 公共录制源、实测状态、实验室配置、三路视频验收：`runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full`。

使用仿真状态反馈参考控制，尚不代表视觉 agent 自主求解。参数变化不能继承本实例资格。公共重渲染不积分、不增加执行次数。
