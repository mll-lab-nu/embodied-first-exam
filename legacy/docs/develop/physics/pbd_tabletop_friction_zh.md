# PBD 绳索的桌面摩擦：为什么现在没有，以及怎么补

> 日期：2026-08-02
> 适用：所有 PBD 绳索任务（untangle / untangle_continuous / cable_routing）
> 触发问题：untangle_continuous 里绳子被扰动后**持续摆动不停**、以及绳子在桌面上乱滑。

---

## 1. 症状

在 `untangle_continuous` 的 viewer 里观察到两件事：

- 机械臂搬走一根绳时，**下面那根被扰动后一直摆动**，不会停下来；
- 绳子在桌面上**滑来滑去**，没有"躺在桌上"的手感。

两者是同一个原因：**绳子和桌面之间几乎没有摩擦耗散**。

一个反直觉的事实是：把 `coup_friction` 从 Genesis 默认的 0.1 提到 0.8 **对这两个现象基本无效**。
原因见下。

---

## 2. 根因：Genesis 的绳↔刚体摩擦是"冲击式"的

`genesis/engine/couplers/legacy_coupler.py::_func_collide_in_rigid_geom`：

```python
if rvel_normal_magnitude < 0:  # colliding
    rvel_tan = rvel - rvel_normal_magnitude * normal_rigid
    rvel_tan_norm = rvel_tan.norm(gs.EPS)
    rvel_tan = (
        rvel_tan / rvel_tan_norm
        * qd.max(0, rvel_tan_norm + rvel_normal_magnitude * geoms_info.coup_friction[geom_idx])
    )
```

两个关键点：

1. **只在 `rvel_normal_magnitude < 0`（正在撞进表面）时才处理。**
   一根静止躺在桌上的绳，法向相对速度 ≈ 0，这个分支基本不进。
2. **切向速度的削减量正比于法向速度**，而不是正比于法向力/穿透深度。
   静止接触时法向速度 ≈ 0 → 削减量 ≈ 0 → **摩擦 ≈ 0，与 `coup_friction` 的取值无关**。

也就是说这是一个**碰撞时刻**的摩擦模型（适合"球砸到地上蹭一下"），不是**持续接触**的库仑摩擦
（适合"物体躺在桌上"）。

### 对照：绳↔绳摩擦反而是对的

`genesis/engine/solvers/pbd_solver.py::_func_solve_collision`：

```python
d = target_dist - cur_dist          # 穿透深度
mu_s = max(particles_info[i].mu_s, particles_info[j].mu_s)
if dpos.norm() < mu_s * d:
    ...                              # 静摩擦：完全抵消切向位移
else:
    ... mu_k * d / dpos.norm(...)    # 动摩擦
```

这是标准的**位置式**摩擦，正比于穿透深度，**静止接触照样有效**。

所以本仓两种摩擦的能力是不对称的：

| 接触 | 参数 | 模型 | 静止时有效？ |
|---|---|---|---|
| 绳 ↔ 绳 | `rope.elastic.static/kinetic_friction` | 位置式，∝ 穿透深度 | ✓ |
| 绳 ↔ 桌面/刚体 | 桌子 geom 的 `coup_friction` | 速度式，∝ 法向速度 | ✗ |

**这两个是独立旋钮**（详见 `configs/task_configs/untangle_continuous_*.yaml` 的注释），
不要指望调其中一个去解决另一个的问题。

---

## 3. 为什么"调高绳↔绳摩擦"也治不好

一个自然的想法是：既然绳↔桌不行，那就调高绳↔绳摩擦，靠绳子之间的接触耗散。

不行，两个理由：

1. **接触面积不对**。摆动的绳大部分身体压在**桌面**上，和另一根绳只在交叉处那一小块接触。
   耗散主要该发生在桌面接触上。
2. **有明确副作用**。离散版 untangle 的 config 注释里记着：绳↔绳摩擦调高会让被搬运的绳
   **把压着的另一根拖着走**（"拖着走"）。这正是我们要避免的。

---

## 4. PBD 本身也没有阻尼

`PBD.Elastic` 的全部参数：`rho` / `static_friction` / `kinetic_friction` /
`*_compliance` / `*_relaxation`。**没有一个是速度阻尼** —— `relaxation` 是约束求解的松弛因子，
不是耗散项。

值得注意的是 `PBD.Cloth` **有** `air_resistance`（默认 1e-3），而且在
`_kernel_apply_external_force` 里只对 `material_type == CLOTH` 生效。也就是说 Genesis 的作者
认为可变形体需要耗散，但只给了 cloth，没给 elastic。

结论：**这套配置下，一根被推动的绳没有任何机制让它停下来。**

---

## 5. 解法：自己补一个库仑摩擦，且只改速度

### 5.1 为什么"只改速度"是安全的

PBD 每个 substep 的顺序（`pbd_solver.substep_pre_coupling`）：

```
_kernel_store_initial_pos          记下 ipos
_kernel_apply_external_force       vel += g*dt;  pos += vel*dt      <- 用速度做预测
stretch / bending / volume         约束投影，改 pos
_kernel_solve_collision            碰撞投影，改 pos
_kernel_compute_velocity           vel = (pos - ipos) / dt          <- 从位置反推速度
```

- **改位置很危险**：末尾会用 `(pos - ipos)/dt` 反推速度，所以任何外部写入的位置突变都会被
  换算成巨大速度。本仓的绳子爆解（粒子被弹到求解域角点 `(100,100,100)`、蒙皮拉成直梁）
  基本都属于这一类。
- **改速度是安全的**：它只是给下一个 substep 的预测一个新初值，完全在求解器的正常语义内，
  不会被反推放大。

所以补摩擦要做成**纯速度修改**。

### 5.2 库仑模型

对一个被桌面支撑的粒子，法向支持力 N = m·g，所以减速度 a = μ·g，**与速度无关**（这正是库仑
摩擦与 Genesis 那个速度式模型的本质区别）。每个 scene step 后：

```
找出贴着桌面的粒子：z < 桌面高度 + 接触带
对其水平速度 v_xy：
    Δv = μ_k · g · dt
    若 |v_xy| <= μ_s · g · dt   ->  v_xy = 0          （静摩擦：停住）
    否则                        ->  v_xy 减少 Δv       （动摩擦：匀减速）
垂直分量 v_z 不动（那是重力和碰撞的事）
```

μ=0.5、dt=0.01 时每步减 4.9 cm/s —— 一根被推动的绳几步内停下，和真实桌面一致。

### 5.3 一个附带的好处：自动排除被抓起来的绳

接触判据是"z 低于桌面+接触带"。被机械臂提起来的那段绳 z 很高，**自然不在接触带里**，
不会被摩擦干扰。不需要额外去区分"哪根正在被搬运"。

---

## 6. 边界与未决

- **不解决绳↔绳穿模**。那是另一个问题（碰撞屏障的粒子密度，见
  `untangle_continuous` config 里 `rope.mesh` 的注释：粒子间距必须 ≤ `particle_size`）。
- **不是完整的接触力学**。没有法向力的真实计算（假设 N = m·g），所以斜面、堆叠、绳压绳的
  法向力都不对。对"绳子躺在水平桌面上"这个场景足够。
- **根治方案是换 FEM + IPC coupler**。IPC（Incremental Potential Contact）用能量势垒保证
  不穿透，摩擦是变分式的、静止有效，`FEMOptions` 还有 Rayleigh 阻尼。但 IPC coupler 只支持
  rigid + FEM（不支持 PBD），需要 `pip install pyuipc`，且 Newton 求解通常比 PBD 慢一个量级 ——
  对需要批量生成数据的 benchmark 是个真实风险。**建议先做性能 spike 再决定**，本文的方案是
  在 PBD 上的务实补丁。

---

## 7. 相关文件

| 文件 | 关系 |
|---|---|
| `topogym/world/rope.py` | PBD 绳索物理的公共模块，摩擦助手应放这里（三个绳索任务共用） |
| `topogym/world/tabletop.py` | `create(table_material=...)` 可覆写桌子的 `coup_friction`（已有，但如上所述对静止摩擦无效） |
| `docs/develop/physics/pbd_physical_handle_interaction_zh.md` | PBD 绳索的机械臂物理夹持 |
| `docs/develop/physics/untangle/untangle_connector_flyout_debug_zh.md` | 位置突变导致粒子飞出求解域的历史案例 |
