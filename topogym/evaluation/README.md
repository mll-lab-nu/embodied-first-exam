# 只读评估

此目录接收数组、阈值或运动与碰撞查询，不创建环境、不推进物理；任务成功语义由 Task 定义。

- `terminal/`：公共“释放后稳定”测量。任务通过 `final_settling_spec()` 选择目标；检查 assist 已解除、机器人碰撞几何与目标有保守间隙、速度及相对确认起点的位移/转角。`TaskDefinition` 将它与任务目标组合，复用原有唯一稳定计时和 checkpoint。Coil、Buzz、Knot、Blanket 已接入；允许握持任务不启用。缺证据禁止成功，包围盒重叠只表示间隙未确认，不等同实际碰撞。详见[实现说明](../../docs/develop/modules/final_settling_zh.md)。

- `cloth_metrics.py`：布面投影覆盖、拉伸、速度等测量；当前 Blanket 判据使用覆盖测量。
- `cloth_binding.py`：对实际 visual support 表做纯数组材料局部性、位置／假想展平重建与仿射权重检查；配合管理侧 `world/physics/pbd_binding.py` 读取出生缓冲区。调用方须提供可靠的 remesh 后材料坐标；通过不表示落桌稳定或任务成功。
- `motion_certificate.py`：通过共享碰撞查询和刚体运动合同，计算自适应连续运动间隙证书。

无当前调用方的 geometry_metrics、particle_metrics、stability、surface_collision 和旧 Lock 离线统计已删除。保留脚本中的辅助函数不自动成为成功判据；其阈值和调用范围仍由 Task 或调用者选择。

最初目录整理未运行测试；后续新增绑定审计的单元测试和零步 Genesis 构建验证见[证据](../../runs/test_results/setting_independent_20260925_01/README.md)。这些检查不声明物理稳定性或任务完成率。
