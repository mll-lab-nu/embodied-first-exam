# 第 12 项的体积 FEM 绳

> **2026-09-29 当前入口：** 三档已迁移到 Genesis FEM/IPC，共享 50 kPa 材料与 v13 细网格；尺寸、场景稳定性门槛和当前结果见[任务主页](slotted_post_ring_zh.md#当前三档场景与稳定性验收)。本页下文保留 2026-09-21 的 MuJoCo FEM 开发记录，旧脚本不再是当前运行入口，也不授予新场景资格。

用户要求用 FEM 提升绳索拟真性。原版并非铰接刚杆链，而是 MuJoCo 一维 flex：节点各有三个平移自由度，线段提供碰撞，长度等式约束控制伸长。它没有三维连续体材料响应。此前 147 秒解环录像的物理结论仅适用于该旧模型。

新入口是 [`fem_probe.py`](../../../topogym/tasks/slotted_post_ring/fem_probe.py)，模型由 [`fem.py`](../../../topogym/tasks/slotted_post_ring/fem.py) 构造。绳体换为 3D 四面体 FEM，移除全部绳段长度等式约束；珠子、木环、圆片、长槽和基座沿用原先几何。两端只保留绳中心节点到圆片绳结锚点的双向位置连接，允许相对转动。该连接仍是绳结的近似，不是实体绳结。

按最新目录约定，历史和实验录像均放入 `runs/environment_bootstrap/slotted_post_ring/`；`demos/slotted_post_ring/varaition_<id>/` 每个变体只保留最新正式完整流程的独立 MP4。当前 `varaition_clearance36` 的三路仍为旧一维绳外力完整流程，新 FEM 局部试验不替换它。新 FEM 录像使用公共 `topogym.recording` 的 `prepare/replay/validate/archive`；仅完整连续解环、全部释放落稳、逐步审计及独立全四面体分离检查通过后，才能使用单独的 `external_physics_v1` 策略更新当前展示。它不授予机器人执行资格。

## 当前结果：FEM 全流程开发中，正式视频仍为旧模型

本轮 FEM 完整流程开发尚未获得最终通过状态。新增连续外力执行器支持逐阶段交互输入，同一个物理状态跨阶段保留，不以检查点拼接完整录像。当前 36 mm 槽宽试验使用 E = 500 kPa、0.5 ms `discrete` 步长、3 ms Rayleigh 阻尼和 1000 次 Newton/有效矩阵迭代预算，网格包含 1206 个节点、3192 个四面体。1 ms 完整运行对照因接触深度超限而停止，不能宣称完整流程步长收敛；材料参数尚未标定。

可查看最新连续运行的 [49 秒正面](../../../runs/environment_bootstrap/slotted_post_ring/fem_full_20260921/progress_continuous_fem_49s_v9/recording/front_oblique.mp4)、[背面](../../../runs/environment_bootstrap/slotted_post_ring/fem_full_20260921/progress_continuous_fem_49s_v9/recording/rear_oblique.mp4)、[俯视](../../../runs/environment_bootstrap/slotted_post_ring/fem_full_20260921/progress_continuous_fem_49s_v9/recording/topdown.mp4)：覆盖装配初态到穿槽、穿珠，980 帧、20 fps，三路完整解码、同步及哈希检查通过。独立录制帧复核的最小体积比为 0.3708，最小 / 最大主伸长为 0.3199 / 1.3239；存在明显局部压缩，大压缩下的材料响应未标定。数值门槛通过不表示实物精度，也不表示完整解环成功。最后脱环和释放仍在验证，视频保留在开发目录。

急弯诊断分别检查了圆片绳端、珠孔姿态、双端托举及珠子后移。珠子姿态控制使用按其转动惯量设置的阻尼，不能直接使用圆片的角速度阻尼。另提供默认关闭的 `--bead-mouth-fillet .00125` 圆角候选：中心孔径不变，最小轴向厚度 37.141 mm；不足以阻挡长槽的圆角尺寸会被构建器拒绝。圆角试验改变了几何，不能继承原孔口运行的验证结果；当前正式视频未采用该候选。

圆角候选的 0.5 ms 连续运行通过了前 35.8 秒逐步物理检查，之后放下左圆片时局部轴向应变达到 21.6%，超过 20% 门槛，该次完整运行保持未通过。后续试验向内调整圆片落点，并重新从装配初态执行；当前保留的连续主运行已通过 74.6 秒，但绳弯仍未完全脱环。局部检查点续跑只用于调试，归档器拒绝将它们发布为完整 demo。该主运行仅对木环、右珠与两枚圆片施加外力，最多同时控制四个刚体。局部逐节点定位抓持因自接触或体积门槛失败，未应用到主运行。录制元数据根据真实动作表区分木件导引与 FEM 节点受力。这不是双臂机器人执行。

新增 [`fem_grasp.py`](../../../topogym/tasks/slotted_post_ring/fem_grasp.py) 作为待验证的外力抓持近似：`fem_section_<截面编号>` 控制该截面的质量中心，将合力按节点质量分配，允许截面自行旋转和变形，不逐点固定截面形状。合力上限为每截面 4 N，反馈频率受积分步长限制；使用材料被动力与重力前馈，不抵消接触反力、不修改 FEM 材料或实体位姿，也不模拟实际夹爪接触。力平衡、零附加力矩、不同步长的控制稳定性及录制边界共 14 项回归通过；完整材料下的绕绳与脱环仍待验证。该控制器不能热替换已经运行的旧主进程，采用它的正式完整版必须从装配初态重新连续执行。

逐步验收保持：无非有限状态或引擎警告、最小四面体体积比 > 0.2、接触与端点误差 < 0.5 mm、局部轴向应变 < 20%、总轴向应变 < 5%、位置跟踪误差 < 5 mm。最后两秒必须全部释放，FEM 顶点最大 / RMS 速度 < 5 / 1 mm/s，刚体线速度 < 2 mm/s、角速度 < 0.03 rad/s。独立录像帧复核另计算主伸长、弹性能及全四面体到木环的保守分离距离；它不能替代逐步审计或材料标定。

[`recording_adapter.py`](../../../topogym/tasks/slotted_post_ring/recording_adapter.py) 从完整 `qpos/qvel` 恢复三维 FEM 网格，逐帧核对全部顶点与独立记录的中心线。20 帧三视角诊断已通过公共验证：中心线误差为零、全部顶点误差小于 `5e-13 m`、物理模型签名一致、零积分。回放采用共享 `compact_lab` 背景，保留原平面桌面和外力执行身份，不改变源物理模型。新适配与公共归档边界共 13 项回归通过；这些检查不代表完整任务已经成功。

当前 25 项任务、材料与录制门槛回归通过，包括交互命令空行不会中断同一个连续物理状态的回归。新启动的试验对任何累计物理或跟踪超限立即保存现场并停止；这些最大值不会因后续恢复而重新合格。运行开始时的源码快照与后处理源码分别保留。

### 较早的独立重力探针

22 项材料与回归测试通过。Newton 版主步长和半步长均完成 6 秒独立重力运行，接触、体积、绳端、应变及每步求解器收敛检查通过；**两次落稳速度检查均未通过**，因此尚未提升稳定性或完整解环资格。

- [正面 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_fem_gravity_attempt_v2_front_oblique.mp4)
- [背面 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_fem_gravity_attempt_v2_rear_oblique.mp4)
- [俯视 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_fem_gravity_attempt_v2_topdown.mp4)

三路为同一次主步长实测状态重渲染，6.05 秒、121 帧、20 fps，已验证完整解码、同步和哈希。主 / 半步长最大穿透为 0.2097 / 0.1256 mm，最小四面体体积比为 0.8207 / 0.8191；末两秒最大顶点速度为 181.83 / 85.18 mm/s，高于 5 mm/s 门槛。两次最终形状最大差异为 1.1024 mm，但形状对照通过不能替代速度验收。[完整报告、参数与独立模型](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_fem_gravity_attempt_v2/README.md)保留所有通过与未通过项。

## 材料与网格

采用 [MuJoCo 原生 Saint Venant–Kirchhoff 有限元](https://mujoco.readthedocs.io/en/stable/XMLreference.html#deformable-flex-elasticity)：分片线性四面体，大转动、小应变材料模型。具备拉伸、剪切和体积响应；弯曲来自整个体积网格的变形。它仍是均质各向同性等效材料，没有编织纤维、股间滑移和摩擦滞回。

| 参数 | 较早 28 mm 重力探针参数（非当前全流程配置） |
| --- | ---: |
| 物理杨氏模量 E | 100,000 Pa |
| 物理泊松比 ν | 0.30 |
| 密度 | 700 kg/m³ |
| 绳半径 | 3.5 mm |
| 轴向网格间隔上限 | 6 mm |
| 截面周向节点数 | 8，另有一个中心节点 |
| 全绳节点 / 四面体 | 1,197 / 3,168（28 mm 槽宽） |
| 刚度比例 Rayleigh 阻尼 | 0.00001 s |
| 质量比例阻尼 α | 2 s⁻¹，逐节点阻尼系数为 α × 节点质量 |
| 接触摩擦系数 | 0.35 |
| 接触参考时间 | 0.0003 s |
| 主步长 / 半步长 | 0.1 / 0.05 ms |

以上均为可配置的建模参数，尚未通过实物拉伸、弯曲、回弹及摩擦测量标定。不能仅凭“用了 FEM”宣称已达到实物拟真度。

质量比例阻尼会耗散绳体整体运动，是等效黏性阻尼假设，不等同于已标定的纤维内部摩擦；运行时没有速度清零或位置钳制。可用 `--mass-damping 0` 做无质量阻尼对照。

材料无应力参考态是直且无扭转的绳。穿槽的弯曲装配态另存为 `assembled` keyframe，初始化时加载；不会把原始穿槽曲线当作自然形状。XML、MJB、四面体连接关系、参考与装配顶点均保存，初始化后不写入实体位姿。

截面为内接八边形，质量按真实离散体积积分；其面积小于理想圆截面，未偷偷增加密度补偿。网格细化收敛尚未验证。

## 材料反力校核

不能只检查 XML 中出现 `young` 字段。单元测试用均匀轴向拉伸和剪切的标准解析应力核对模型反力，并检查刚体旋转不产生弹性恢复力、网格封闭、四面体正体积和 XML/MJB 重载一致性。

当前 MuJoCo 3.13.0 全自由度 flex 的原生边度量在体积 Lamé 项上采用不同系数约定；直接填写 E = 100 kPa、ν = 0.3 时，零侧向应变下的轴向反力比标准公式大约 42.86%。实现依据[官方刚度组装源码](https://github.com/google-deepmind/mujoco/blob/main/src/user/user_mesh.cc)转换输入，保持物理剪切模量，并将传给原生模型的 Lamé λ 减半：

`ν_native = ν / [2(1−ν)]`，`E_native = E(1+ν_native)/(1+ν)`。

以 100 kPa 的旧重力配置为例，XML 记录 E_native ≈ 93,406.5934 Pa、ν_native ≈ 0.2142857143；当前 500 kPa 全流程候选对应 E_native ≈ 467,032.9670 Pa，报告仍记录物理 E = 500 kPa、ν = 0.3。每次构建都执行轴向与剪切反力校核，相对误差需小于 10⁻⁶；若升级后原生约定改变，构建失败，不会静默继续。

## 验证范围与复现

材料、网格及重载检查已通过，主步长和半步长运行的落稳验收未通过。逐积分步审计四面体体积比、绳端误差、局部与总轴向应变、引擎接触穿透、全部 FEM 顶点速度及刚体速度；最后两秒还检查自然落稳。材料应变允许弹性变化，不沿用一维不可伸长模型的 0.5% 绳长门槛。

当前使用 Newton 接触求解器，并逐步记录迭代次数；耗尽迭代预算会使验收失败。早期 CG 配置在已保存的末态连续 200 个积分步均耗尽 100 次预算，Newton 在同一诊断中用 9–26 次迭代收敛。早期 CG + Euler 隐式节点阻尼组合发生翻转，当前 Euler 配置显式积分节点阻尼；没有把这些失败配置提升为合格参数。

已归档[第一轮 6 秒 FEM 试跑](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_fem_underdamped_attempt_v1/README.md)：[正面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_fem_underdamped_attempt_v1_front_oblique.mp4)、[背面](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_fem_underdamped_attempt_v1_rear_oblique.mp4)、[俯视](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_fem_underdamped_attempt_v1_topdown.mp4)。此版无质量比例阻尼，接触和体积检查通过，最后两秒顶点速度未达标，原始总验收保持 false。

重力探针的接触检查来自 MuJoCo 接触检测，尚无独立扫掠表面 CCD 认证。没有以内部防翻转接触掩盖四面体翻转；翻转、非有限状态或引擎警告会中止运行并保留失败报告。

```bash
# 材料解析反力、网格和重载测试。
.venv-gs121-nyx/bin/python -m unittest tests.check_slotted_post_ring_fem

# 原版 28 mm 槽宽的 FEM 重力探针，输出目录必须是新目录。
.venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.fem_probe \
  --output runs/environment_bootstrap/slotted_post_ring/my_fem_main --seconds 6
.venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.fem_probe \
  --output runs/environment_bootstrap/slotted_post_ring/my_fem_half --seconds 6 --dt .00005

# 参数扫描可用 --young、--poisson、--rayleigh、--mass-damping、--segment、--radial-segments；
# 36 mm 候选必须显式加 --slot-width .036，不能继承旧录像的通过状态。
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.recording_adapter \
  --run runs/environment_bootstrap/slotted_post_ring/my_fem_main \
  --output runs/environment_bootstrap/slotted_post_ring/my_fem_recording --diagnostic
```

历史 `fixture.py` 和机器人执行器仍明确拒绝 FEM 输入。新增 [`fem_fixture.py`](../../../topogym/tasks/slotted_post_ring/fem_fixture.py) 单独执行体积 FEM 的完整动作表：刚体外力驱动、逐步体积/应变/接触审计、阶段检查点和实测状态录像，运行中不改写实体位姿。它的最终通过状态取决于该次完整操作和释放结果，不继承旧版资格。

`discrete` 积分器中的 FEM 有效质量矩阵求解也受 `solver_iterations` 和 `solver_tolerance` 控制；早期大步长试跑的惯性警告来自迭代预算耗尽。配置项依据 [MuJoCo 官方有效矩阵求解实现](https://github.com/google-deepmind/mujoco/blob/main/src/engine/engine_derivative.c) 显式暴露，警告仍使验收失败。试验参数、失败报告和运行开始时源码保留于 `runs/environment_bootstrap/slotted_post_ring/fem_full_20260921/`。机器人操作、网格细化及材料实测标定尚未完成。
