# F1 三拱 · 默认姿态与公共实验室录制版

`F1_triple_compact_toy_s70_home_lab_v1` 冻结 F1 从双拱改为三拱（3 拱 2 谷，多 2 道竖直弯）后，从默认 home 开始的新连续执行及完整 IK。原型为设计规格 `vertical_wave_v1.yaml` 中的 `F1_triple_arch`（半径 50 mm、拱顶 250 mm、谷底 80 mm、前后跨度 100 mm，整体 70%）。场景相对双拱版沿世界 X 移动 -20 mm、Y 移动 +70 mm，使默认 home 张爪正下方落在第二个深谷而不是中央拱顶。

环预先穿在线路上、由实体木托支撑。机械臂从配置 home 张爪开始，经连续接近、实际拾取、全部七段关卡、支撑放回、松爪撤臂及静置。4/2 ms、各 16 子步独立执行均通过。没有预抓取、焊接或运动中的位姿覆盖。

- `planning/`：可直接交给 `robot_runtime --plan`，包含 home_approach 及全部首尾动作。
- `robot_seed.json`：完整主路径、抓持变换及首尾动作；派生后必须重新验收。
- `scene_config.yaml`：原物理执行配置。实验室视觉覆盖由公共录制预设应用，模型签名一致性已检查。
- `robot_qualification.json`、`timestep_qualification.json`：物理资格、执行身份及证据哈希。
- 公共录制源、实测状态、实验室配置、三路视频验收：`runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full`。
- 旧双拱包 `F1_compact_toy_s70_home_lab_v4` 保留为历史证据，不再是默认展示代表。

使用仿真状态反馈参考控制，尚不代表视觉 agent 自主求解。参数变化不能继承本实例资格。公共重渲染不积分、不增加执行次数。
