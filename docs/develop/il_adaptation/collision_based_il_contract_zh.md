# Collision-Based IL Demo Contract

本文记录当前先行整理为 collision/contact-based 的四个刚体任务：

- Swap
- OneStroke
- Maze Wall Removal
- Stacked Plate

这些任务用于生成模仿学习数据时，默认遵守同一条合约：物体运动必须来自 Genesis 刚体碰撞、摩擦、关节约束与 Franka PD 控制；执行阶段不使用 `AttachmentManager` 把物体绑定到机械臂，也不调用 `set_pos` / `set_quat` 直接改被操作物体位姿。

## 运行时合约日志

四个 physical demo 都会打印一行：

```text
<demo_name> il_contract mode=collision_based_contact ...
```

关键字段：

- `mode=collision_based_contact`：该 demo 的操作路径以碰撞接触为基线。
- `runtime_attachment=False`：执行阶段不把物体 attach 到机械臂。
- `runtime_set_pose=False`：执行阶段不 teleport 被操作物体。
- `success_checks=...`：该 demo 被认为适合进入 IL 数据集前必须通过的检查项。

最终 result 行会打印：

```text
il_ready=True/False
```

采集脚本应只接受 `il_ready=True` 的 episode。

## 任务口径

### Swap

Franka 夹爪通过刚体接触和摩擦夹起方块，并放入目标空槽。成功检查包括：

- 试抬高度 `lift_delta`
- 抓取 XY 漂移 `grasp_xy_error`
- 放置 XY / Z 误差
- puzzle terminal

### OneStroke

每个 wall block 都通过长轴端夹的刚体抓取搬运到目标 edge。成功检查包括：

- wall 是否被真实试抬
- edge XY / Z 误差
- yaw 误差
- tilt 误差，翻滚 wall 不算成功
- task terminal

### Maze Wall Removal

每个 wall block 通过刚体夹持从 maze 中拔出，并释放到 discard 区。成功检查包括：

- 试抬高度和保持阶段 drift
- 抓取 XY 漂移
- discard 放置误差
- maze terminal

### Stacked Plate

Franka 指腹跨夹竖直圆盘的盘缘薄边，靠接触摩擦把 revolute 圆盘向下捏转，使各盘的缺口扇形
转到同一角度重合。执行阶段不写关节角，圆盘完全由指腹摩擦驱动。成功检查包括：

- rotation achieved（真实旋转量达标）
- rim follow error（指腹跟随理论盘缘点的误差）
- target angle error（真实角落在目标角容差内）
- release drift（松爪后角度漂移）
- sector alignment terminal（各盘扇形世界角极差 ≤ 容差）

## 和 PBD / Peeling 的区别

这份合约只覆盖刚体优先任务。Cable、Untangle、Peeling cloth 等 PBD/薄片任务仍然需要混合机制：PBD 负责绳索/布料形变，必要时使用 endpoint constraint、socket latch、sticky-tip 或 kinematic sheet driver。它们不能直接套用这里的 collider-only 规则。
