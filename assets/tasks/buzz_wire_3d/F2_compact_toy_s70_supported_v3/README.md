# F2：支撑拾取与放回的固定实例

完整流程已通过 4/2 ms、各 16 子步物理复验。环预先套在线路上，初始由木托支撑；机械臂张爪分离开始，实际拾取、通过所有关卡、放到终点木托、松爪撤臂并静置。没有预抓取、焊接或运动中的位姿覆盖。

- `scene_config.yaml`：固定几何、摆位、控制设置。
- `planning/`：可直接交给 `robot_runtime --plan` 的完整计划及资产，包含 approach / pickup / traverse / placement / retreat。
- `robot_seed.json`：主路径 IK、抓持变换和首尾动作，可用 `robot_plan --seed-plan` 重新审计。
- `robot_qualification.json`：该实例的独立资格及证据哈希。

底座垫高 40 mm，轨道整体同步抬升；木支座承接起终点工具。F2 终点采用倾斜环与柄颈托架，避免强行放平时的腕关节极限。

后续参数变化必须重新规划全部动作并重新做双步长物理验收；不得继承本实例的成功标签。历史 agent adapter 不随此实例更改。视频与原始物理证据：`runs/demo_metadata/buzz_wire_3d/2026-09-21_F2_supported_pick_place_v3_full`。
