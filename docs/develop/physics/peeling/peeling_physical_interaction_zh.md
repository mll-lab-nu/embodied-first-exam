# Peeling 单膜物理交互第一版

## 建模范围

第一版只验证一张薄膜，保留原有三膜语义 oracle 作为对照。新 demo 使用：

- `13 x 9` 三角网格的 Genesis PBD Cloth；
- 初始完全平整、没有预制翘角的单张薄膜；
- 默认使用 contact attachment：Franka 接近右下自由角到容差内，即视为吸附/
  粘住该角；
- 角部 PBD 粒子随后随末端运动，避免 Genesis 1.1.0 中不稳定的 rigid-PBD
  硬接触；
- 按列固定的布料粒子，近似薄膜与基底之间的胶黏；
- 随机械臂拉动逐列调用 `release_particle()`，形成移动的剥离前沿。
- 完全揭开后将薄膜搬运到新的桌面坐标并松爪。

场景中只有一张橙色薄膜和其下方的蓝灰色基底，不再显示目标贴片，
也没有独立刚性把手。执行阶段没有 gripper attachment，不会使用
`set_pos` 搬运薄膜。

这里的 `13 x 9` 是输入 OBJ 的控制网格。Genesis 1.1.0 会按照
`PBDOptions.particle_size` 对它进行各向同性重网格化，因此实际仿真粒子数
通常大于 117。当前实现直接读取重网格化后的粒子坐标，再将所有粒子完整
分配到角部夹持区或 13 个胶黏释放组，不依赖输入顶点编号。

## 胶黏近似

Genesis 1.1.0 没有直接的胶层或断裂传播材料。当前实现把除角部夹持区
以外的粒子按 X 方向分组并固定在初始位置。

机械臂每完成一小段回拉前，仅释放下一组粒子。仍未释放的粒子构成当前剥离前沿，已释放部分由 PBD 拉伸和弯曲约束自由变形。这是确定性的混合物理模型，不等同于真实胶黏力模型。

输入薄膜所有顶点起始时具有相同高度。右下小块角部粒子保持自由，周围
胶黏粒子固定。起角动作先释放角部附近两条胶黏带，然后让闭合指尖在薄膜
表面从内向外扫过基底边缘，并同时抬高。默认 attachment 模式下，只要
末端到角点的误差小于 `attach_tolerance`，就建立临时吸附约束；随后
角部粒子的高度变化由 attachment lift 阶段产生。

这一步不使用 `set_particles_pos`。但胶黏带何时断开仍由脚本调用
`release_particle()` 决定，因此是“真实接触起角 + 确定性胶黏断裂”的
混合模型。

## 动作阶段

1. `flat_hold`：保持平整初态，便于观察和录制。
2. `attach_touch`：末端接近自由角，建立 suction-like attachment。
3. `attach_lift`：通过 attachment 抬起角部。
4. `peel_group_*`：回拉时逐组释放胶黏粒子。
5. `transport_to_target`：完全揭开后高位搬运。
6. `place_on_target`：下降到目标区域，松爪并等待薄膜沉降。

## 成功判定

剥离阶段检查：

- 所有胶黏粒子组均已释放；
- 足够比例的布料粒子高于基底；
- 布料质心在 XY 平面产生了足够位移；
- 角部粒子质心在整条轨迹中持续跟随夹爪。

松爪沉降后另外检查：

- 薄膜质心靠近 `placement.center`；
- 足够比例的粒子已经落到目标表面附近。

## 运行

```bash
python -m prototypes.peeling_physical_single_demo \
  --viewer --keep-open --verbose
```

录制：

```bash
python -m prototypes.peeling_physical_single_demo \
  --record-video runs/demo_peeling_physical_single.mp4 \
  --record-fps 30 --record-every-n-steps 2 \
  --record-camera oblique --record-res 640 640 --verbose
```

## V1 训练一致性约定

当前默认路径已经从“只拖动角点 particles”升级为 sticky-tip +
kinematic sheet driver。也就是说，末端接触角点仍然负责触发 attachment，
但已释放的贴片区域会作为连续薄片随末端移动，未释放区域保持平整贴附。

后续 demo、IL 数据采集和 RL 实时训练必须复用同一套环境内部逻辑：

- action 只控制机器人末端/夹爪/吸附命令；
- attachment 由环境根据接触容差判定；
- `released_groups` 和 peel front 是环境内部状态，可以用于 reward/info，
  但默认不作为普通视觉 policy 的 observation；
- 不允许在 demo 中额外 teleport 贴片，而训练时不用同样机制。

详细公约见 `docs/develop/physics/peeling/peeling_sticky_tip_contract_zh.md`。
