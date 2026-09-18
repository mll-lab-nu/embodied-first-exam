# Cast Coil：由解锁运动反推的三个结构

这三个实例从已验证的双臂 IK 相对路径出发，先改变运动，再在金件设计包络内添加材料、扣除银件沿变体运动的保守扫掠体。银件与原抓持面保持不变。实体、碰撞盒、质量和惯量均从最终几何重新生成；不是在旧结构上仅更换动作。

模板坐标单位为 mm，实例使用 `scale=3`。下表均为实例实际尺寸；方向采用零件局部坐标，场景整体另有 90° yaw。

| 子目录 | 变体运动 | 金件碰撞盒数 |
| --- | --- | --- |
| `eccentric_turn` | 滑开 27.75 mm，绕偏移 3 mm 的转轴转动 90°，移出 207 mm | 16 |
| `split_turn_offset` | 滑开 21.75 mm，转动 45°，沿 z 错位 6 mm，再绕移动后的轴转动 45°，移出 207 mm | 24 |
| `axial_screw_turn` | 滑开 21.75 mm，转动 90°的同时沿 y 推进 6 mm，移出 207 mm | 97 |

三者金件均为连通、水密实体，中央贯通孔宽 36 mm，外包络仍为 102 × 74.25 × 102 mm。第三种通道是正交阶梯近似，尚不是平滑螺旋面或制造定型产品。

`synthesis_report.json` 是生成阶段报告：指定路径通过连续 SAT 与材料点位移界证书（60 μm 余量），原版三段路径与六方向直拉均被阻挡。第三种额外拒绝“先轴向推进再转动”的测试。以上负对照不证明全局解法唯一。报告中的机器人/物理未验证标志只表示该生成阶段；后续完整机器人与半时间步证据存放在 demo 归档中。

生成器：`topogym.tasks.cast_coil.inverse_design`。完整流程：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_plan \
  --template assets/tasks/cast_coil/inverse_variants_v1/eccentric_turn/template.json \
  --output runs/environment-solvability/cast_coil/NEW_RUN/robot_plan.json
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_demo \
  --backend cpu --save-render-states \
  --plan runs/environment-solvability/cast_coil/NEW_RUN/robot_plan.json \
  --output runs/environment-solvability/cast_coil/NEW_RUN/physical
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_demo \
  --backend cpu --dt 0.00125 \
  --plan runs/environment-solvability/cast_coil/NEW_RUN/robot_plan.json \
  --output runs/environment-solvability/cast_coil/NEW_RUN/half_dt
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.render_physical_trace \
  --source runs/environment-solvability/cast_coil/NEW_RUN/physical \
  --output runs/environment_bootstrap/cast_coil/NEW_RUN
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_archive \
  --source runs/environment_bootstrap/cast_coil/NEW_RUN \
  --reference runs/environment-solvability/cast_coil/NEW_RUN/half_dt \
  --run-id NEW_DATE_NEW_RUN
```

物理执行为 CPU 双精度、有接触门控辅助抓持的关节控制，从张爪预抓取开始，覆盖抬升、解锁、分离落桌、解除辅助、撤手、自由静置。Nyx 视频用同一次物理执行的精确 20 Hz 状态离线渲染，不插值、不推进渲染场景的物理；不是纯 IK 轨迹预演。未证明纯摩擦抓持、真实机器人负载能力或商业原版的官方八步解法。

视频保留在 `runs/demos/cast_coil/2026-09-17_inverse_<kind>_<camera>.mp4`；配套页面与独立证据位于 `runs/demo_metadata/cast_coil/2026-09-17_inverse_<kind>/`。
