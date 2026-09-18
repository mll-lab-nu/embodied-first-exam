# 刺球出笼：三个动作 family 的代表实例

2026-09-17。已完成 A/B/C 各一个代表的完整物理 demo，外观九宫格与随机实例采样仍属于后续工作。本页记录最终实例、复现方法和验收结果。

[打开三个 family 对照页](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_representatives_v1/index.html)。

| 代表 | 三视角播放页 | 视频时长 |
| --- | --- | --- |
| A 单斜窗绕出 | [打开 A](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/index.html) | 82.58 s |
| B 双门槛换层 | [打开 B](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_b_staggered_gates_v1/index.html) | 113.00 s |
| C 螺旋导向 | [打开 C](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_c_helical_guide_v1/index.html) | 90.58 s |

12 个独立 MP4 保存在 `runs/demos/hedgehog_in_cage/`，文件名前缀为上表的日期与 family 实例 ID；每类包含三个同步视角及一个合成视频。播放页、完整资产、状态、报告及 SHA-256 清单放在对应的 `runs/demo_metadata/hedgehog_in_cage/` 目录。

## 实例与动作

| family | 实际结构 | 相对运动变化 |
| --- | --- | --- |
| A `oblique_gate` | 高 240 mm、外径 135 mm 的直壁笼，主出口边缘为偏置斜窗 | 对已解路径增加最大 10 mm 侧移和 −4° 配合倾角 |
| B `staggered_gates` | 直壁笼外连接一道位于 X≈220 mm 的错位挡板，构成第二门槛 | 先穿出笼窗，再升高并侧移，经过第二门槛后退出 |
| C `helical_guide` | 高 240 mm、外径 156 mm，笼条在全高扭转约 104°，形成连续导向窗 | 导向段的位置和姿态共同累计增加 36° 转向，最后沿新方向退出 |

三者保持同一十刺球、S2 抓点、固定笼和单臂。B 的第二结构是开口挡板，不是封闭圆环；生成时保留可达运动与材料连通，最终外形以导出的网格为准。它与 A 的单窗、C 的扭转笼条均有实体形状区别。窗口的 3 mm 阶梯来自保守体素工程表示，尚未做外观圆滑化。

实例顺序为：已解相对位姿路径 → family 动作变形 → 连续机器人 IK → 刺球及完整夹爪的扫掠空间 → 保留空间外的连通笼体 → 实体碰撞与机器人检查 → 完整物理执行。没有通过改变视频速度、颜色或肘部姿态来定义动作 family。

## 证据范围

每个实例检查原路线、直拉、直升、直降和删去关键动作的有限对照。B 的删去第二门槛对齐动作的碰撞见证位于 X=214.003 mm 的外挡板上，而非笼内第一出口。三条完整运动在三种笼体的 3×3 交叉检查中，对角线可通过，六条跨 family 路线均发生物体与笼体碰撞。这些结果没有证明全局唯一解，也没有证明所有捷径均被排除。

规划证书使用实际导出的凸实体，0.1 mm 材料运动采样界给出物体路径连续间隙下界。机器人全身另查自碰撞、笼体、底座和桌面。生成阶段还保护完整 Robotiq 机构的扫掠空间，不能只保护两块指垫。

执行从预抓取位开始，双指实际接触后启用辅助抓持；通过所有约束、搬运落桌后解除辅助、张爪撤离，并自由静置 5 秒。该范围仍不包括从任意初态自主抓取，也没有验证纯摩擦抓持。

A 使用连续在线 IK。B/C 首次在线 IK 在冗余关节分支上逐步偏离已验证路径，失败记录保留在工作目录的 `attempts/live_ik_branch/`。最终执行改为以离线认证分支作 IK 初值，并根据实际接触抓持变换修正末端目标；仍只向物理机器人发送关节位置控制指令，运行中不覆写物体或机器人的位姿。实际状态检查独立于这套控制求解器。

物理使用 Genesis、CPU、64 位，外层步长 5 ms；分别以 10/20 个子步完成全流程。CPU 是本次 GPU 显存不足时的运行后端。录制将同一次物理执行保存的真实状态送入 Mesa EGL 软件光栅渲染，12 fps、960×720 三视角，并保留 1440×360 合成视频；渲染过程不再推进物理。光照质量与 Nyx 路径追踪不同，不影响执行证据。

## 复现入口

在仓库根目录使用 `.venv-gs121-nyx/bin/python`，新输出根目录必须为空，避免覆盖任何已验证副本。

```bash
# A/C 可由默认运动生成；B 必须使用本次验收的明确预设。
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.family_motion oblique_gate --output /tmp/hedgehog_families_rebuild
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.family_motion staggered_gates --output /tmp/hedgehog_families_rebuild --motion-file configs/task_variants/hedgehog_in_cage/family_b_motion_v1.json
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.family_motion helical_guide --output /tmp/hedgehog_families_rebuild
```

对各 family 顺序运行 `family_geometry sweep`、`family_geometry geometry`、`family_geometry certify`、`family_runtime plan-audit`，均传入 family 与同一个 `--output`。`family_motion` 的 B 默认值属于探索提议，不能代替上面的最终预设。

A 用 `family_runtime physics oblique_gate --backend cpu`；B/C 用 `family_guided_runtime <family> --backend cpu`。每个实例分别执行默认子步和 `--substeps 20`，并用 `family_runtime audit <family>` 检查对应两次实际轨迹；上述命令也需要相同的 `--output`。

软件渲染环境：

```bash
PYOPENGL_PLATFORM=egl __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=4 .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.family_runtime render oblique_gate --backend cpu --output /tmp/hedgehog_families_rebuild
```

另外两类只替换 family 名。最终运行 `family_review cross-check`、`family_review figures`。`family_archive` 会检查两次物理报告与源码/资产哈希、视频完整解码、三视角帧数/时长、实际状态逐帧一致性和独立副本。当前归档入口的日期与 run ID 固定；另一次正式归档应先选择新 run ID。

六个本任务几何/证书回归测试及源码导入检查通过。额外的全项目任务卡检查被现有 `fiber_bundling.yaml` 的轴状态与校验器规则不一致阻断；本任务没有修改该任务卡，原始测试输出随实例保留。

## 代表实例的实际执行结果

| 指标 | A 单斜窗 | B 双门槛 | C 螺旋导向 |
| --- | --- | --- | --- |
| 完整物理时长 | 82.525 s | 112.985 s | 90.505 s |
| 规划物体连续间隙下界 | 2.334 mm | 2.250 mm | 2.509 mm |
| 实际保存状态插值的间隙下界 | 2.421 mm | 2.095 mm | 2.455 mm |
| 实际机器人状态检查数 | 8,254 | 11,300 | 9,052 |
| 仿真报告的刺球/笼体最大穿透 | 0 | 0 | 0 |
| 仿真报告的机器人/场景最大穿透 | 0 | 0 | 0 |
| 0.5 ms / 0.25 ms 两档物理子步 | 两次通过 | 两次通过 | 两次通过 |
| 两档执行的最终位置差 | 0.0349 mm | 0.0182 mm | 0.0413 mm |
| 两档执行的最终姿态差 | 0.0669° | 0.1455° | 0.0967° |

表中的时长、间隙、状态数与穿透数值对应录制用的 10 子步执行。间隙下界的连续性范围是相邻保存状态间的指定 SE(3) 插值；不能据此声称覆盖任意未记录的子步轨迹。仿真本身另在运行中持续检查接触，完整机器人碰撞在每个保存状态复核。

两档子步的六次执行均通过独立实际状态检查，且最终两秒满足平移漂移 <0.2 mm、线速度 <1 mm/s、角速度 <0.5°/s。子步复测针对这三个确定实例，不代表随机初态、摩擦变化或更大参数空间已经通过稳定性测试。

原版与 `eccentric_window_v1` 的已有完整视频、元数据和证书保持不变。
