# Horseshoe Ring 教程结构可解原型 v3

旧运动学演示：`runs/environment_bootstrap/horseshoe_ring/aloha_full/index.html`。
新重力解法：[双臂 IK 与物理验收](../../../../docs/develop/tasks/horseshoe_ring_physical_ik_zh.md)。
路径及证书：`runs/environment-solvability/horseshoe_ring/tutorial_solvable_v3/`。

结构参考 [Professor Puzzle 官方教程](https://www.youtube.com/watch?v=LAE1w1VNIZg)：
2 只马蹄、2 只独立中间链环、1 只目标环；端部连接眼和马蹄为同一刚体。
5 个谜题刚体均自由，没有将链环焊死或删除碰撞。模板使用 mm，演示统一放大 2 倍。

| 参数 | 模板 | 演示场景 |
| --- | --- | --- |
| 马蹄椭圆半轴 | 32 / 29 mm | 64 / 58 mm |
| 扁带宽 / 厚 | 8 / 4 mm | 16 / 8 mm |
| 中间链环中心线半轴 | 18 / 5 mm | 36 / 10 mm |
| 中间链环线半径 | 1 mm | 2 mm |
| 目标环中心线半径 / 线半径 | 31 / 1.4 mm | 62 / 2.8 mm |
| 目标环内径 | 59.2 mm | 118.4 mm |

场景马蹄最大外宽约 131.99 mm。此版本经过翻转、折合、调整目标环及脱出，
具有 3365 帧的完整独立刚体路径。连续区间的保守间隙下界为 0.1006086 mm；
终态目标环与装配的包围盒间距为 54.8865 mm。证书同时验证初始连接和最终分离。

这是名义尺寸的可解性原型，不是商品实测 CAD。正证据只适用于证书对应的精确模板、
尺度及各刚体 COM 线性移动 / 四元数 SLERP 插值；改尺寸后须重新验证。
更小目标环的有限搜索失败没有被解释为无解。

旧 ALOHA 演示采用预置抓持、逐帧关节与物体位姿回放。其换抓支撑是运动学假设，
不能用作力驱动夹持、重力执行和抗扰动成功的证据；旧录像不计入物理任务成功率。

`physical_seed.json` 是新重力执行器使用的初态、折合关节种子和取环几何里程碑，
不是物理成功证书。新执行器重新求解交接和取环，并以实测接触和自由落桌终态验收；
入口与证据范围见 [重力下的双臂 IK](../../../../docs/develop/tasks/horseshoe_ring_physical_ik_zh.md)。
