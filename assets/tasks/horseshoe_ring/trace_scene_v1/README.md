# 从轨迹到场景的离散提案

`proposals.json` 给出受约束的 TCP 轨迹变形参数，而不是“任意 IK 都能反推场景”的假设。
完整过程见 `docs/develop/tasks/horseshoe_ring_trace_scene_variants_zh.md`。

每个提案先生成新 IK，再从双臂初始抓持的 FK 拟合尺度、旋转、平移，选择匹配链环几何，
重规划空手换抓段，并检查全程一致性、几何可解性与采样碰撞。只有 `result.json` 中通过的实例收录。

批次产物：`runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/`。
此处参数不构成连续范围保证；基于同一输入重新运行时，OMPL 的空手路径可能不同。
全部仍为运动学预演，未验证力驱动执行。
