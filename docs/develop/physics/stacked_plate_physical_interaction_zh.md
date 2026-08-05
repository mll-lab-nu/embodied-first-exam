# Stacked Plate 物理交互实现

## 目标

`stacked_plate_physical_rotate_demo` 用 Franka 夹爪与竖直圆盘盘缘的刚体接触完成旋转。
执行阶段不创建 attachment，也不调用 `set_pos`、`set_quat` 或直接写入转盘关节角——
盘的转动**只来自指腹对盘缘的接触摩擦**，符合 collision-based IL 合约。

## 机构建模

三个竖直圆盘 `D1/D2/D3` 串在一根沿 Y 的水平横杆上（左右并排）：

- 每个圆盘是一个固定基座 URDF：`disk_base` 固定在共享 tabletop 的 task frame 中，
  `rotating_disk` 通过绕世界 Y 轴的 continuous joint 与基座连接（见
  `topogym/tasks/connectivity/stacked_plate.py:_write_disk_urdf`）；
- **碰撞和质量是均匀完整圆柱**，质心在轴上——没有重力力矩，圆盘在任意角度都是中性
  稳定的。这正是纯接触驱动可行的关键：夹爪只需克服关节 damping/friction/armature 和
  转动惯量，而不必对抗重力；
- 扇形缺口（pac-man）是**纯视觉 mesh**，嵌在旋转 link 里随关节一起转；不参与碰撞；
- 盘做大（半径 0.078）以增大力臂、便于捏缘驱动。半径只在 XZ 平面展开，盘厚仅 0.014、
  沿 Y 间隔 ±0.065，所以放大半径不会与相邻盘碰撞；
- 横杆两端有竖直支柱托住，横杆本身有碰撞，给机构真实转轴边界；
- 刚体求解器使用额外的 `noslip_iterations`，降低持续夹持圆弧运动中的接触滑移。

## 动作阶段（`RimRotatePrimitive`）

路径几何与执行都在可复用 primitive `topogym/primitives/rim_rotate.py` 里，prototype
只负责装配摩擦、逐盘调用 primitive、再判定成功。每个盘的相位序列：

1. `open` 张开夹爪。
2. `approach` 移动到盘缘捏取点正上方；接近高度按盘缘点动态抬高一段
   `approach_clearance`，避免张爪阶段就撞进盘。
3. `descend` 下降，让两指腹夹住盘缘捏取点——指腹沿 Y 方向跨夹圆盘两个面（薄边）。
   捏取起点方位由 `physical.grasp_rim_angle_deg` 指定（0=盘缘正上方，向 +X 前方为正），
   从前上方一点起捏，向下滚动更像“手指捏着转”。
4. `close` 夹住盘缘薄边（`grasp_qpos≈盘厚`）。
5. `rotate` 末端沿理论盘缘圆弧缓慢下滚，方位角从 `grasp_rim_angle_deg` 扫过
   `signed_rotation(start,target,roll_sign)`。**过程中不写任何关节角**，圆盘完全由指腹
   摩擦带动。每步读取真实关节角计算跟随误差。
6. `arc_settle` 保持轻夹等关节速度衰减。
7. `release` 张爪，读取松爪后的角度漂移。
8. `retreat` 按动态安全高度向上撤离。

滚动方向：`roll_sign` 为 +1/-1 时强制被捏点上/下滚，为 0 时取到目标角的最短路径。
当前 init/target 下最短路径即为正向下滚，故默认 `roll_sign=0`。

## 成功判定

`RimRotateResult` 逐盘检查（阈值来自 `physical`）：

- `rotation_achieved`：真实关节角相对起始角的旋转量达到 `min_rotation_deg`（`driven`）；
- `target_error`：真实角落在目标角容差 `rotation_tolerance_deg` 内；
- `max_follow_error`：指腹中心与理论盘缘点的最大跟随误差不超 `max_rim_follow_error`；
- `release_drift`：松爪后角度漂移不超 `max_release_drift_deg`；
- 全盘扇形世界角极差 ≤ `success.alignment_tolerance_deg`（`StackedPlatePuzzleEvaluator`）。

`task_success` 只看扇形是否对齐；`physical_quality_success` 额外要求每盘 primitive 都
通过上述物理检查且总跟随误差达标。这区分了“机械臂走完轨迹”和“夹爪确实捏转了圆盘”。

## 调参要点

- 若指腹在到达目标角前就打滑：加大 `finger_friction`/`disk_friction`、或增大
  `grasp_qpos` 的夹紧、或放慢 `arc_steps`；也可减小各盘 `init_angle_deg` 与 target 的
  角差，使被捏点始终留在夹爪从上方可达的上半球。
- 若未被操作的盘被路过的机械臂蹭动超限：适当抬高 `mechanism.joint_friction` /
  `joint_armature`（注意过高会让盘更难被驱动，需折中）。

## 运行

```bash
python -m prototypes.stacked_plate_physical_rotate_demo --viewer --verbose
```

录制视频：

```bash
python -m prototypes.stacked_plate_physical_rotate_demo \
  --record-video runs/demo_stacked_plate_contact.mp4 \
  --record-fps 30 --record-every-n-steps 2 \
  --record-camera oblique --record-res 640 640 --verbose
```
