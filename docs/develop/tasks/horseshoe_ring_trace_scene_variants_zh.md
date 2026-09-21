# Horseshoe Ring：由解法轨迹生成可解场景变体

目标改为让参考动作和场景共同变化。已有种子是完整几何解法及 ALOHA 运动学预演，
不包含力驱动抓取执行的成功证据。新方法保留解法阶段与手物约束，允许 IK 关节序列、
夹爪开合、抓点和空手避障路径变化，再从生成的轨迹恢复对应场景。

查看 `runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/index.html`。
页面提供种子与新末端轨迹的交互对比、逐实例 CSV / JSON、反推场景、阶段截图和证据。
完整录像归档后，页面通过 `video_demos.json` 加入原版与三组变体的同步动态对照及各组独立播放入口。

## 完整动态录像

三组均使用原有、已验证的全部 829 帧，12 FPS，时长 69.083 秒。每组从预置抓持开始，
覆盖翻转、折合、双臂交接、左臂换抓、取环和最终分离。录像逐帧检查 Genesis 指垫与已验证 IK 的位置一致性。
每组保存高位、低位、左腕、右腕、全景、近景，以及四视角拼图共 7 个 MP4。

首尾相近是同一解法族的设计结果：尺度仅改变约 ±4%，初始偏航变化几度。
观察动作差异可定位至约 29.7 秒的右臂转移和 45.3 秒的左臂换抓。
额外的四格对照由原版和三组独立完整录像按相同时间轴拼接，不计为一次新的机器人执行。

归档使用 `runs/demos/horseshoe_ring/<variant_id>/<run_id>_kinematic_<camera>.mp4`，
配套播放页、轨迹、配置、资产与几何证据位于 `runs/demo_metadata/horseshoe_ring/<run_id>/`。
最初的 `tutorial_solvable_v3` 演示也作为一个变体，视频位于 `original/`；
三个新变体分别位于 `compact_roll_planned/`、`wide_roll_planned/`、`longer_regrasp_planned/`，
跨变体的四格同步对照位于 `comparisons/`。整理目录不改变 MP4 内容或播放页地址。
`archive_manifest.json` 记录视频和证据的 SHA-256；`archive_validation.json` 记录全视频解码、
帧数/帧率、Genesis 跟踪误差、独立副本和归档数据的几何验证。

## 从轨迹到场景

1. 从归档的 829 帧、12 Hz 轨迹得到双臂指垫中心的位姿及抓持阶段。FK 用于还原已有动作，
   不把关节数据再次求解为另一条种子。
2. 在接触相容的轨迹族中提案：改变双手目标路径的尺度、初态偏航/偏移、折合中的摆动，
   以及左手在目标圆环上的抓持角。以种子对应帧的关节解为 IK 初值，保留同一解支的约束。
3. 从新 trace 的两只初始夹爪位置和朝向拟合场景的正尺度、旋转和平移。两臂的拟合结果必须一致，
   不能把互相冲突的手位姿解释为同一个装配。
4. 从独立验证过的链环几何族选择尺寸，建立反推场景。几何族并非从 IK 唯一推断出来；
   IK 不足以唯一确定物体的 CAD、材料或摩擦。
5. 空手换抓段重新做关节避障规划。单纯扭曲末端路径可能在腕部奇异位置产生关节解跳变，
   这些段允许重规划；抓持段始终检查手物相对位姿。
6. 脱环后段将左指垫路径逐渐约束回已知可达的种子路径，由右手和装配的位置/朝向补偿新的尺度及抓点。
   这样保留新场景与抓持配置，同时避免末段进入腕部限位。

对一个抓持中的物体，末端和物体满足 `T_TCP = T_object · G_grasp`。
`G_grasp` 在固定抓持段内不变，缩放时只按尺度改变其中的接触位置，机器人本身不缩放。
双臂一起约束装配时，分别恢复的物体位姿必须一致。

## 本批参数

尺度比相对于种子；种子场景的模板放大倍数为 2。下列值是离散提案，
只有实例 `result.json` 中 `passed=true` 才计入可解场景与轨迹对。

| 实例 | 尺度比 | 初始偏航 | 折合摆角 | 圆环抓点角变化 | 链环族 |
| --- | --- | --- | --- | --- | --- |
| compact_roll_planned | 0.96 | -3° | +2° | -1° | compact：半轴 17.7 / 4.8 mm、线半径 0.7 mm |
| wide_roll_planned | 1.04 | -3° | -2° | +1° | wider：半轴 18 / 5.3 mm、线半径 0.7 mm |
| longer_regrasp_planned | 1.00 | -4° | +3° | -2° | longer：半轴 18.5 / 5 mm、线半径 0.7 mm |

表中链环尺寸是模板 mm；乘以实例 `scene_scale` 才是场景尺寸。
马蹄和圆环也随统一尺度改变，四个手指滑轨值按实际指垫间隙调整，不能把关节滑轨值直接乘尺度。
不同实例的关节命令哈希必须不同。每个实例都保留完整阶段，而非换色或只改变相机。

## 可解性为什么能保持

链环族在独立刚体的完整见证上已有数值证书。新实例对五个谜题部件同时使用相同的正尺度和
随时间变化的刚体变换，因此任何时刻的部件间距离等于原距离乘尺度。
验证器核对实际碰撞覆盖网格确实为该缩放，确认导出的每一帧都与公共变换一致，
并重新检查目标圆环最终完全分离。整体运动不是任意改变各部件的相对位姿。

连续路径由 `geometry_evidence/body_poses.json` 中的完整密集见证、`source_index` 时间映射及
`common_transforms.json` 定义。公共中心线性插值、公共四元数最短 SLERP，再映射原密集路径。
**不能直接对导出的少量物体 COM 关键帧做另一种插值，然后沿用此证书。**

新尺度下正间隙下界随尺度改变，不机械声称仍是种子的 0.1 mm。
初态沿装配长轴正反方向的直接拉环失败也随相似变换保留；这排除已有的大环直滑正对照，
并非已穷尽所有更简单的解法。

对机器人另查关节限位、相邻帧跳变、全程手物重建一致性、逐帧机器人/谜题/桌面穿透和谜题离桌间隙。
机器人碰撞检查是 12 Hz 采样，不是全连续机器人碰撞证书。
原始抓持和交接支撑仍为运动学假设，物理步数为 0；新变体也不能计为动力学成功。

这是同一解法族中的几何与动作变体。它还不支持从任意随机关节曲线恢复任意可解谜题，
也不证明参数区间、参数笛卡尔积或未经验证的随机组合全部成立。

## 文件与复现

- `ik_trace.json / ik_trace.csv`：逐帧双臂 16 个关节位置、夹爪滑轨、指垫世界位姿、阶段及时间。
- `inferred_scene.json / config.yaml / template.json`：由轨迹恢复的位姿与尺度、选定的几何参数。
- `robot_motion.json`：新关节及物体预演轨迹，含抓持段重建误差与采样碰撞结果。
- `geometry_certificate.json / geometry_evidence/ / common_transforms.json`：相似变换继承的连续几何证据。
- `verification.json`：对导出场景、命令哈希、密集路径、网格缩放及终态的独立复核。
- `inspection/`：Genesis 实际阶段截图。
- `full_demo_v1/`：每个变体首次完整录像及输入证据快照；独立保留副本在标准归档目录。
- `video_demos.json`：已验证录像归档与同步对照的页面入口。

```bash
# 从已验证种子生成本批轨迹与场景；先保证固定轨迹几何族的证据已存在。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m topogym.tasks.horseshoe_ring.trace_scene_variants \
  --proposals assets/tasks/horseshoe_ring/trace_scene_v1/proposals.json

# 复核一个实例的导出数据和几何证明映射
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m topogym.tasks.horseshoe_ring.trace_scene_verification \
  runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned

# 场景阶段截图
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.aloha_demo \
  --backend cpu --renderer rasterizer --keyframes-only \
  --config-path runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/config.yaml \
  --motion runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/robot_motion.json \
  --output runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/inspection
```

完整录像及归档示例（重跑时给输出目录和归档 ID 使用新版本，已有目录会拒绝覆盖）：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.aloha_demo \
  --mode kinematic --backend cpu --renderer rasterizer \
  --config-path runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/config.yaml \
  --motion runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/robot_motion.json \
  --output runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/full_demo_v1

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m topogym.tasks.horseshoe_ring.variant_video \
  --source runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/compact_roll_planned/full_demo_v1 \
  --run-id 2026-09-17_compact_roll_planned_v1
```

先前冻结关节的 8 个通过变体保留为几何族和对照，位于 `fixed_ik_trace_v1/`。
它们不再是本轮主要目标；新生成器会实质改变参考动作。
