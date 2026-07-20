# Peeling Segmentation Fault Debug Log

## 现象

命令：

```bash
python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose
```

最后输出：

```text
peeling_physical_single_demo scene_ready
peeling_physical_single_demo robot_home_ready hand=[0.045013412833213806, 0.0, 1.1928247213363647]
peeling_physical_single_demo flat_ready corner=[0.09333320707082748, -0.04062488675117493, 0.9426431059837341] released_groups=0
Segmentation fault (core dumped)
```

前面的 MJCF tendon、neutral qpos、self-collision filter、quadrants weakref
都是已有 warning。当前真正错误是 Python 无 traceback 的 native
`Segmentation fault`。

## 当前相关代码

- `prototypes/peeling_physical_single_demo.py`
  - 构建 tabletop V1 Peeling 场景；
  - `flat_hold` 后调用 `PBDCornerLiftPrimitive.run()`；
  - 起角成功后进入 `PBDParticlePinchDragPrimitive` 做夹持、揭开、搬运和放置。
- `topogym/tasks/peeling_physical.py`
  - 创建单个 PBD Cloth 贴片；
  - 贴片初始完全平整，`grasp.initial_lift=0.0`；
  - 角部粒子自由，其余粒子分成 13 个胶黏组并 `fix_particles()`；
  - 没有刚性把手，没有 `fix_particles_to_link()`。
- `topogym/primitives/pbd_particle_pinch.py`
  - `PBDCornerLiftPrimitive` 首先闭合夹爪；
  - 移动到角部附近；
  - 释放靠近角部的胶黏组；
  - 用指尖向外扫动并抬起角部。

## 初步疑点

1. **PBD-rigid 接触 native crash**
   - 崩溃发生在 `flat_ready` 后，场景已经稳定 step 过；
   - 后续第一件事是 `corner_lift`，会让 Franka finger 逐渐接近 PBD Cloth；
   - Genesis 1.1.0 的 PBD-rigid 接触在绳索/布料靠近刚体边缘时可能比较脆弱。

2. **闭合夹爪或 IK 连续控制触发**
   - `PBDCornerLiftPrimitive.run()` 进入后先执行 `controller.set_gripper(tool_qpos=0.0, steps=55)`；
   - 如果崩在这里，说明不是接触贴片，而是 PBD scene + articulated gripper step 的组合有问题。

3. **`release_particle()` 时机触发**
   - 起角动作在 `corner_descend` 后释放 `corner_release_groups=2`；
   - 如果崩在 `corner_release` 附近，可能是释放固定 PBD 粒子后马上进入 rigid contact 的状态不稳定。

4. **viewer/native visualizer 触发**
   - 当前命令开启 viewer；
   - 如果 `--debug-stop-after` 能在 headless 下通过、viewer 下崩，则需要把 visualizer 也列入嫌疑。

## 已加诊断

## 当前定位结论

用户已运行：

```bash
python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_close
```

结果正常停止：

```text
[pbd_corner_lift after_tool_close] ...
peeling debug stop reached after corner_close
```

随后运行到 `corner_descend` 时：

```text
[pbd_corner_lift after_approach] target=[0.08484792569658892, -0.03213960537693636, 1.1696429] ...
Segmentation fault (core dumped)
```

因此已经排除：

- flat scene + viewer 本身；
- PBD scene 中闭合 gripper；
- 第一段 approach IK/PD 运动。

崩溃点落在 `after_approach` 到 `after_descend` 之间，也就是闭合 finger
继续下降到贴片角附近的过程中。此时还没有调用 `release_particle()`，
所以当前最高优先级嫌疑是 **rigid finger 与 PBD cloth/基底近距离接触导致
Genesis native crash**。

## 当前临时修复策略

默认 `grasp.mode` 已切到 `contact_attachment`：

- 机械臂靠近角点；
- 当末端目标点进入容差范围，就认为“接触并吸附/粘住”；
- 选中的角部 PBD 粒子随后跟随末端运动；
- 不再让 closed finger 和 PBD cloth 做硬接触；
- 仍保留 13 组胶黏粒子的逐步 `release_particle()`，因此剥离/搬运流程可继续调试。

这不是纯物理夹持，而是 suction-like / sticky-contact 近似。它比刚性把手更接近
“碰到贴片角即抓住”的任务语义，也为多层贴片保留了可扩展性。

新增阶段日志和可控断点：

```bash
python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after flat

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after attach_approach

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after attach_touch

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after attach_lift
```

旧的 direct-contact 断点仍保留给 `grasp.mode: physical_pinch` 实验：

```bash
python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_close

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_approach

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_descend

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_release

python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose \
  --debug-stop-after corner_sweep
```

如果某个断点前已经 segfault，崩溃点就在上一阶段内部；如果某个断点正常
SystemExit，则该阶段之前都不是 native crash 根因。

## 定位顺序

默认 attachment 模式下：

1. 先跑 `--debug-stop-after flat`，确认 flat scene + viewer 稳定。
2. 再跑 `attach_approach`，判断无接触 approach 是否触发。
3. 再跑 `attach_touch`，判断接近角点但保持 clearance 是否触发。
4. 再跑 `attach_lift`，判断脚本 attachment 驱动 PBD 角点是否触发。

旧 direct-contact 模式下：

1. 跑 `corner_close`，判断闭合 gripper 是否触发。
2. 跑 `corner_approach`，判断第一段 IK/PD 运动是否触发。
3. 跑 `corner_descend`，判断靠近贴片但未释放胶黏时是否触发。
4. 跑 `corner_release`，判断 `release_particle()` 是否触发。
5. 跑 `corner_sweep`，判断真实 PBD-rigid 扫角接触是否触发。

## 可能修复方向

- 如果崩在 `corner_close`：先不要在 home 位姿闭合夹爪，改成到位后再闭合，
  或降低 `gripper_steps`/PD 接触刚度。
- 如果崩在 `corner_approach`：检查 IK target 与姿态，必要时先用默认竖直姿态
  和更高 approach z 做纯运动。
- 如果崩在 `corner_release`：把角部释放提前到 scene build 后，避免运动中释放。
- 如果崩在 `corner_sweep`：降低 PBD-rigid 接触风险，例如先禁用 no-slip
  iterations、增大角部自由区、减小 sweep 深度，或改成更稳定的“薄片边缘
  starter fixture”近似。
