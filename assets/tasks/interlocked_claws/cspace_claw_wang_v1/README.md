# Claw 原始参考资产

`piece-0.obj`、`piece-1.obj` 是 [Qineng Wang 演示页](https://qinengwang-aiden.github.io/demos/constraint_demos/)
公开提供的原始文件，字节内容未修改。来源为 SIGGRAPH 2020
**C-Space Tunnel Discovery for Puzzle Path Planning** 的补充材料。

`reference_scene.json` 摘录上游 manifest 的初始关节状态、机器人运动链、两件抓持变换、
初态位姿、颜色和放置支架，并记录原 manifest 的 SHA-256、网址及下载日期。
完整上游 manifest / viewer 读取代码保留在本机 `.external/interlocked_claws/`；
当前场景运行只依赖本目录文件，不需要网络或该缓存。

坐标转换严格沿用上游：`v_local_m = (v_obj - source_origin) * 0.1`；
每件 `T_reference_piece = T_reference_gripper @ inverse_grasp`。
`inverse_grasp_column_major` 按列展开，不能直接按 NumPy 默认行序 reshape。
原始坐标和源文件保留，生成到 `runs/` 的 OBJ 则以米为单位。

| 文件 | 三角面 | 焊合重复位置后的顶点 | SHA-256 |
| --- | ---: | ---: | --- |
| piece-0.obj | 14780 | 7392 | 35e40f140642310e64f587c528213fe60c64202bdababd654013f205b1602ed5 |
| piece-1.obj | 14480 | 7242 | 15305d656b31248c13fad76089683a94f2720ce45ee22d3f4eacb7313eb6658b |

OBJ 含用于纹理／法向接缝的重复顶点。导入器只焊合重合位置，逐三角面核对位置没有改变，
不填洞、不重新建模、不简化、不做整体凸包。两件均为单连通、封闭、法向一致的实体。
600 kg/m³ 密度仅为加载时的工程设定，不是原件实测值。

上游[来源说明](https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html)
明确表示未确认零件几何的独立再分发许可证。本目录保留来源，不将查看器 MIT 或
论文代码 GPL 许可证套用到几何上。
