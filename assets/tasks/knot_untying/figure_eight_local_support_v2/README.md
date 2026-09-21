# 八字结局部支撑候选 v2

这是独立的固定摆法，保留原 `figure_eight_v1` 及其失败和静置证据。
结区平面尺度为 32.5 mm，高度参数为 10 mm，尾段仍为 180 mm，绳径仍为 8 mm；
开放绳长约 1.461 m，诊断闭合为 4₁。网格采用相同直绳材料参考态和 FEM+IPC 配置。

配置为 `configs/task_variants/knot_untying/profiles/figure8_local_curve_v2.yaml`。
参考 yaw 为 45°；B 端首个下穿段内侧由左手抓取，右手支撑相应上穿支路，
先侧移 100 mm 避让，再按实际绳形分段退穿。动作来自状态观察，不能把 CPU 预检当作解结成功。

初态几何和 100 mm 侧移加 300 mm 名义退穿的离散机器人预检已通过；
证据位于 `runs/environment-stability/knot_untying/families_20260919/figure_eight/local_profile_v2_final_preflight.json`。
尚未获得该摆法的动力学成功或完整 demo。原 v1 的静置、外观参数边界和录像不适用于此 v2。

运行时显式选择 `--family figure_eight --route-profile figure8_local_curve_v2`。
默认 `--family figure_eight` 仍加载原 v1。

相同几何另有 `figure8_local_curve_narrow_v3` 动作配置：先在空中收窄手指，再下降至目标。
它针对 v5 闭爪时挤压邻近绳段的失败；不改变材质、辅助抓持强度或物理阈值。
相应 v6 连续试录尚待验收，不能把预检通过当作完整解结成功。
