# 开放八字结固定模板

`figure_eight_open_v1`：单根绳、两个自由端、一个结区。初始闭合参数曲线为
`((2+cos(2t))*cos(3t), (2+cos(2t))*sin(3t), sin(4t))`，切去外侧无交叉弧段后接出平滑尾段。
只在几何诊断中闭合为 [4₁](https://katlas.org/wiki/4_1)，物理场景不含闭合线。

绳径 8 mm，长度约 1.241 m，两个尾段各 180 mm，四个交叉交替上下穿。
初态最小非相邻绳面间距 5.72 mm，最小弯曲半径 16.84 mm。
`geometry/` 保存带封盖的单连通绳管、GLB、材料顺序中心线、几何检查和 SHA-256。
这些是初态资产；文件中的 `physics_qualified=false` 不应被静态检查改为通过。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets --family figure_eight
```

场景入口为 [固定配置](../../../../configs/task_variants/knot_untying/figure_eight.yaml)。
采用直绳参考态的 FEM+IPC，自接触、桌面接触和正常重力；两端无固定约束。
机器人参考朝向为桌面 yaw 90°，medium 是待实测的目标难度。
详见 [实施与证据](../../../../docs/develop/tasks/knot_untying_family_space_zh.md)。
