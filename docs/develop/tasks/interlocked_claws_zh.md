# Claw 互锁件：原始模型、完整参考动作与物理验收

后续变体设计见 [三个动作 family、九个代表构型与随机空间规划](interlocked_claws_family_space_zh.md)。
该规划区分已有参考执行证据、候选结构和尚未通过的接触可靠性门槛。

本轮对应用户链接第一段 **Unlocking the Claw** 中的两个复杂零件。
采用[作者网页](https://qinengwang-aiden.github.io/demos/constraint_demos/)公开的原始 OBJ，
不是根据视频外形近似建模。来源、哈希和坐标约定见
[资产说明](../../../assets/tasks/interlocked_claws/cspace_claw_wang_v1/README.md)。

## 运行与产物

在仓库根目录执行：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.interlocked_claws
# 仅静态图片，跳过相机绕行视频：
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.interlocked_claws run.record_video=false
# 显式使用 CPU 光栅：
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.interlocked_claws \
  env.genesis.backend=cpu env.renderer.type=rasterizer run.record_video=false
```

默认输出 [审阅页面](../../../runs/environment_bootstrap/interlocked_claws/reference_initial/index.html)，
含全景、装配近景、背面、拆件检查、初态相机绕行视频，以及两件米制 OBJ / URDF、
装配和拆件 GLB、配置快照及几何／加载报告。`run.output` 可改到新运行目录。
这不是完整机器人 demo，故不归档到 `runs/demos/`。

## 完整流程与验收入口

已保留 [158.6 秒完整五路播放页](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/index.html)
及 [物理验收报告](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/reliability.html)。
主运行和半时间步运行均完成全部阶段、解除双侧约束并稳定落架。10 Hz 对齐状态的最大位置差
为 **0.263887 mm**；主运行与参考动作同一时刻的抓持位置最大偏差 **0.418765 mm**，
最大姿态偏差 **0.001225 rad**。末态两件间距约 **253.085 mm**。
独立接触对照仍未通过，具体失败与更细 SDF 预处理未完成的记录一并归档，不能将流程完成解释成通用接触可靠性通过。

动作文件 `assets/tasks/interlocked_claws/cspace_claw_wang_v1/recorded_motion.json`
固定作者公开的 3,084 帧、156.513 秒关节轨迹，保留全部 12 个动作阶段。
阶段依次为协同脱困、橙色件搬运与落架、蓝色件搬运与落架、左手解除抓持／张爪／撤回、
右手解除抓持／张爪／撤回及静置。文件字节哈希受到校验，不能悄悄替换轨迹。

```bash
# 精确原网格的连续参考路径检查（自适应区间界，不依赖 SDF）
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.reference_audit \
  --output runs/environment-solvability/interlocked_claws/new_reference_audit

# 真实受力执行：原电机力矩上限、重力、接触、可解除抓持约束
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.physical \
  --output runs/environment-solvability/interlocked_claws/new_physics_dt2ms
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.physical --dt .001 \
  --output runs/environment-solvability/interlocked_claws/new_physics_dt1ms

# 独立直拉阻挡／自由短移／重力落地对照；失败会返回非零状态
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.contact_probe --dt .001 \
  --output runs/environment-solvability/interlocked_claws/new_contact_controls

# 完整运行的半时间步对照
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.verification \
  --first runs/environment-solvability/interlocked_claws/new_physics_dt2ms \
  --second runs/environment-solvability/interlocked_claws/new_physics_dt1ms \
  --output runs/environment-solvability/interlocked_claws/new_timestep_comparison.json

# 同次完整物理执行的精确状态，离线生成四路 ALOHA + detail 视频
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.recording \
  --physical-source runs/environment-solvability/interlocked_claws/new_physics_dt2ms \
  --output runs/environment_bootstrap/interlocked_claws/new_full_recording
```

动力学默认在 CPU 运行，渲染在 GPU 运行。输出目录必须用新版本名，保留既有证据。
`--start-time` / `--duration` 只供局部诊断，不能计为完整执行。
录制入口不带 `--physical-source` 时生成显式标记的 **运动学预演**，物理步数为零。
物理录像必须通过完整性、源轨迹哈希、状态哈希、全部阶段和解除抓持检查，不能以局部片段拼接。

## 实现约定

- 原始三角面数 14,780 / 14,480，文件哈希与作者清单相同；各为单个封闭非凸实体。
- 精确沿用作者的源原点、0.1 米缩放、初始关节值及抓持变换；只整体平移到共享实验室。
- 早期静态预览：共享 ALOHA 资产已去掉源场景的 20 mm 基座抬升。零件与机器人同步采用
  `robot_mount.pos - [0, 0, 0.02]` 的参考坐标平移，保留两件与双手的相对关系；
  放置支架单独沿桌面平移到 `robot_mount.pos`，其相对工作区高度因此比原参考高 20 mm。
  **这套旧高度仅用于初态预览，不适合直接执行原动作。** 原始轨迹的最低顶点距源桌面
  约 17.797 mm，直接下移 20 mm 会碰桌。
- 完整流程配置 `interlocked_claws_physics.yaml` 用 `base_riser_height_m: 0.02`
  及两块实体垫座恢复原机器人高度；物体、支架接触点、双臂与外部相机采用同一源坐标系。
  不缩放物体，不修改轨迹以绕开桌面。
- 使用已有完整 ALOHA 2 资产。通过命名关节映射设置初态；独立 MuJoCo FK 测试和实际 Genesis
  末端 FK 检查确认一致。静态预览不安装抓持约束；完整物理执行明确采用源演示的理想预抓取约束。
- 15 个固定放置支架几何沿用原始尺寸和位姿。底座底面在原参考平面下约 0.9 mm，
  沿用源场景的固定底座嵌入。支架用于将来放置阶段，不承托当前悬空互锁件。
- 每件为独立单 link、6 自由度刚体，无零件间关节。视觉与碰撞引用同一原始三角网格；
  显式关闭 `convexify` 与 `decimate`，加载后复核面数和顶点位置。
- Nyx + `compact_lab` 渲染。橙色／青蓝色沿用源查看器，背景使用 TopoGym 共享实验室。
- 初态最小三角表面间隙约 **5.0577566 mm**，无相交／包含。这个数值只检查当前初态。

## 验证边界

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_interlocked_claws \
  tests.check_configs_compose tests.check_task_baseline_catalog tests.check_project_layout
```

测试覆盖原始资产完整性、正向碰撞对照、初态间隙、独立机器人 FK、导出后三角形一致性、
无关节的双实体结构和配置。实际建场另检查 Genesis 未将几何凸化或简化，以及机器人 FK。

预览物理步数为 **0**。绕行只移动相机；拆件图为显式展示位姿重置，之后恢复初态。
保持悬空是静态观察方式，不是验证过的抓取或稳定平衡。
Genesis 非凸接触使用采样 SDF，默认请求 1.5 mm 网格、最大 256 分辨率；
保留原三角形不代表 SDF 接触误差为零。密度 600 kg/m³、摩擦系数 0.3 为当前场景假设。

连续参考轨迹的两件几何间隙界检查已经通过：3,083 个原始插值区间、94,281 个认证子区间，
采样最小间隙约 0.115109 mm；六个坐标方向的纯直拉都遇到碰撞。
这仅证明源关节插值下的两件分离性，不证明机器人可承载或任意接触的数值可靠性。

独立向下直拉对照暴露非凸接触数值失稳；降低外力并提高姿态控制刚度仍未通过。
向上直拉能产生阻挡，但原生引擎报告约 0.008 mm 穿透时，独立三角接触深度诊断达到约
0.954 mm，超过 0.15 mm 阈值；这说明只看引擎的 SDF 接触深度不够。
因此参数卡继续保持 `unqualified`。完整参考动作即使在理想辅助抓持下通过，
也不能作为纯摩擦抓取、硬件可执行性或通用接触鲁棒性的证明。

物理运行初始化之后只发送限力的位置／速度控制命令和解除抓持约束，不再设置位姿。
原生碰撞逐步监测，独立 FCL 三角表面每 20 ms 检查；接触深度阈值 0.15 mm，
原生非抓持接触阈值 1 mm。三角形深度是局部诊断，不能当成完整体积穿透的精确距离。
最终要求两件分别受到支架向上承托、无残余抓持、间距大于 20 mm，静置尾段
线速度小于 5 mm/s、角速度小于 0.05 rad/s。
