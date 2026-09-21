# 第 12 项的体积 FEM 绳

用户要求用 FEM 提升绳索拟真性。原版并非铰接刚杆链，而是 MuJoCo 一维 flex：节点各有三个平移自由度，线段提供碰撞，长度等式约束控制伸长。它没有三维连续体材料响应。此前 147 秒解环录像的物理结论仅适用于该旧模型。

新入口是 [`fem_probe.py`](../../../topogym/tasks/slotted_post_ring/fem_probe.py)，模型由 [`fem.py`](../../../topogym/tasks/slotted_post_ring/fem.py) 构造。绳体换为 3D 四面体 FEM，移除全部绳段长度等式约束；珠子、木环、圆片、长槽和基座沿用原先几何。两端只保留绳中心节点到圆片绳结锚点的双向位置连接，允许相对转动。该连接仍是绳结的近似，不是实体绳结。

按最新目录约定，历史和实验录像均放入 `runs/environment_bootstrap/slotted_post_ring/`；`demos/slotted_post_ring/` 只保留一版通过完整流程检查的三视角录像。归档器默认写入开发目录，显式 `--publish` 也必须通过完整流程资格检查。迁移工具会核对哈希、完整解码并更新引用，保留配套证据。

## 当前结果：材料接入完成，落稳未通过

22 项材料与回归测试通过。Newton 版主步长和半步长均完成 6 秒独立重力运行，接触、体积、绳端、应变及每步求解器收敛检查通过；**两次落稳速度检查均未通过**，因此尚未提升稳定性或完整解环资格。

- [正面 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/front_oblique/2026-09-21_fem_gravity_attempt_v2_front_oblique.mp4)
- [背面 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/rear_oblique/2026-09-21_fem_gravity_attempt_v2_rear_oblique.mp4)
- [俯视 FEM 录像](../../../runs/environment_bootstrap/slotted_post_ring/historical_demos/topdown/2026-09-21_fem_gravity_attempt_v2_topdown.mp4)

三路为同一次主步长实测状态重渲染，6.05 秒、121 帧、20 fps，已验证完整解码、同步和哈希。主 / 半步长最大穿透为 0.2097 / 0.1256 mm，最小四面体体积比为 0.8207 / 0.8191；末两秒最大顶点速度为 181.83 / 85.18 mm/s，高于 5 mm/s 门槛。两次最终形状最大差异为 1.1024 mm，但形状对照通过不能替代速度验收。[完整报告、参数与独立模型](../../../runs/demo_metadata/slotted_post_ring/2026-09-21_fem_gravity_attempt_v2/README.md)保留所有通过与未通过项。

## 材料与网格

采用 [MuJoCo 原生 Saint Venant–Kirchhoff 有限元](https://mujoco.readthedocs.io/en/stable/XMLreference.html#deformable-flex-elasticity)：分片线性四面体，大转动、小应变材料模型。具备拉伸、剪切和体积响应；弯曲来自整个体积网格的变形。它仍是均质各向同性等效材料，没有编织纤维、股间滑移和摩擦滞回。

| 参数 | 当前候选值 |
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

当前 XML 因此记录 E_native ≈ 93,406.5934 Pa、ν_native ≈ 0.2142857143；参数卡与报告中的物理 E、ν 仍为 100 kPa、0.3。每次构建都执行轴向与剪切反力校核，相对误差需小于 10⁻⁶；若升级后原生约定改变，构建失败，不会静默继续。

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
MUJOCO_GL=egl .venv-gs121-nyx/bin/python -m topogym.tasks.slotted_post_ring.render_physics \
  --run runs/environment_bootstrap/slotted_post_ring/my_fem_main
```

目前完整解环外力执行器和机器人执行器仍是历史一维模型专用；它们明确拒绝 FEM 输入，避免在缺少体积审计时产生错误的通过结果。完整 FEM 解环、机器人操作、网格细化及材料实测标定尚未完成。旧版录像和证据保留为对照。
