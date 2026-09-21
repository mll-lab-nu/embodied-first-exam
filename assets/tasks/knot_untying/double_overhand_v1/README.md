# 开放双重单结固定模板

`double_overhand_open_v1`：单根绳、两个自由端、同一结区内额外绕穿一周。
初态取 T(2,5) 曲线 `((3+cos(5t))*cos(2t), (3+cos(5t))*sin(2t), sin(5t))` 的开放弧段，
接出两个平滑尾段。外侧诊断闭合对应 **5₁**，见 [Knot Atlas T(5,2)](https://www.katlas.org/wiki/T%285%2C2%29)；
不是 5₂，也不是两个串联单结。诊断闭合线不进入物理场景。

绳径 8 mm，长度约 1.384 m，两个尾段各 180 mm，五个交叉交替上下穿。
初态最小非相邻绳面间距 6.82 mm，最小弯曲半径 22.73 mm。
`geometry/` 保存绳管、GLB、材料顺序中心线、几何检查和 SHA-256。
资产报告只认证初始几何，不认证动力学、机器人解结或难度。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets --family double_overhand
```

[固定配置](../../../../configs/task_variants/knot_untying/double_overhand.yaml) 的机器人参考朝向为桌面 yaw 90°。
采用直绳参考态的 FEM+IPC；两端无固定约束。hard 为目标难度，须通过实际动作与简单策略对照检验。
详见 [实施与证据](../../../../docs/develop/tasks/knot_untying_family_space_zh.md)。
