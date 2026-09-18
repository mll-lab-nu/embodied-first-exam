# 固定 trace 对照与几何族

该对照固定 829 帧关节位置和时间，只改变两个未直接抓持的中间链环。
`variants.json` 中每个离散候选单独检查完整几何路径、机器人采样碰撞和正反向直线拉环对照。
结果保留在 `runs/environment-solvability/horseshoe_ring/fixed_ik_trace_v1/`，其中 8 个候选通过。

当前主要方向已改为 `../trace_scene_v1/`：同时生成新轨迹和对应的可解场景。
这里的通过实例作为其可选几何族，不能把固定关节本身当作最终变体目标。
