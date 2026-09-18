# Cast Coil：基础版的三个单参数外观实验

种子是 `2026-09-17_aloha_full` 对应的原始 `photo_reference_v1` 三倍实例。
本轮不组合此前的三种运动反推结构，也不联合改变外观参数。

| 实例 | 唯一外观改动 | 实际包络宽 × 深 × 高 |
| --- | --- | --- |
| `face_small` | 正面 x、z 同比缩小 5%；厚度和切角不变 | 96.9 × 74.25 × 96.9 mm |
| `depth_thick` | y 向厚度与层间距同时增加 10%；正面和切角不变 | 102 × 81.675 × 102 mm |
| `corner_cut` | 正面四个外角切去 5.25 mm；尺寸缩放均为 1 | 102 × 74.25 × 102 mm |

切角沿深度贯穿各层，使用种子坐标 0.75 mm 正交阶梯近似，尚非光滑倒角。两件同步处理。
继承基础版“滑开、绕 y 转动 90°、移出”的动作结构。尺寸改变时，同步派生转轴、位移、抓点、初始高度和抬升量；机器人关节角重新求 IK。
质量、惯量由新实体和原密度计算，未固定为旧数值。两种缩放与切角分别测试，不能把三个单参数成功视为联合随机生成已验证。

`synthesis_report.json` 记录生成阶段的实体、连续路径证书和六方向直拉重叠见证；完整机器人执行与半时间步复核另存在每个 Demo 的 `validation.json`。
控制器沿用基础版增益、力矩上限与接触门控辅助抓持。从张爪预抓取开始，完成解锁、分离落桌、解除辅助、松爪、撤手和自由静置。未验证纯摩擦抓持或真实硬件能力。

生成与计划入口（使用新的目标目录）：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.appearance \
  --kind face_small --output runs/environment-solvability/cast_coil/NEW_RUN/design
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_plan \
  --template runs/environment-solvability/cast_coil/NEW_RUN/design/template.json \
  --output runs/environment-solvability/cast_coil/NEW_RUN/robot_plan.json
```

之后使用 `robot_demo --backend cpu --save-render-states` 保存一次物理执行的精确状态；另用 `--dt 0.00125` 完整重跑。
默认步长为 0.0025 秒、10 子步、双精度。`render_physical_trace` 根据实际状态生成五路 Nyx 视频，不插值、不执行渲染场景物理步进。
`robot_archive` 在物理、时间步和视频解码检查通过后，将独立 MP4 放到 `runs/demos/cast_coil/`，证据保存到 `runs/demo_metadata/cast_coil/`。
