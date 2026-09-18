# untangle_continuous 抓取时的 PBD 求解发散 debug log

> 状态：**已解决**（2026-08-04，run #9 确认）。起作用的是 §11 的 quat 修复：
> `RigidAttachment.sync()` 原先写入纯 yaw 四元数，把躺平的接头一步转成直立，
> 焊在其 link 上的绳末粒子被带着转 90°，构成 §1.2 第 4 步的外部位置写入。
> 修复后 `on_close` 处的单步位移由 11.79mm 降到 0.012mm，握持与搬运全程
> `bend_r` 保持 11.8mm，`parked` 恒为 0，无 EVENT。详见 §13.5。
>
> H9（水平握持的插头产生 90 度转角）**已否定**，见 §13.5。
> 因此 §13.2 的插头俯仰机制没有作用对象，`pinch.carry_pitch_deg` 保持 0。
>
> 本文持续更新，每轮修改后记录结果。
>
> 相关：[`../untangle_connector_flyout_debug_zh.md`](../untangle_connector_flyout_debug_zh.md)（离散版同类现象）、
> [`../../pbd_tabletop_friction_zh.md`](../../pbd_tabletop_friction_zh.md)（桌面摩擦）。
>
> 本目录同时保存原始 trace：`run08_2026-08-03_trace.log`（发散）、
> `run09_2026-08-04_trace.log`（修复后，未发散）。
> `RopeTrace` 以 `"w"` 打开，旧版使用固定文件名，每次运行覆盖上一次的记录
> （§13.1 起带时间戳）。需要保留的 trace 复制到本目录。

---

## 1. 现象与机理

### 1.1 现象

机械臂抓起某根绳、抬升过程中，该绳的粒子被钳制到 PBD 求解域角点 `(100,100,100)`，
蒙皮网格的顶点跟随这些粒子，渲染成一条贯穿画面的三角形带。发生这一现象的始终是被抓取的
那根绳，未被抓取的绳的粒子位移保持在 1mm/step 以下。

### 1.2 机理

以下六步是本文档全部分析所依据的链条，后续章节引用本节，不再重复说明。

**第 1 步：绳的表示。** PBD 把每根绳表示为一组粒子，加上四类约束：拉伸、弯曲、体积，
以及粒子之间的自碰撞。每步先按外力积分出预测位置，再迭代求解各类约束把位置投影回可行域。

**第 2 步：自碰撞的判定方式。** Genesis 的自碰撞按**静止距离**筛选粒子对：
同一物体内静止距离 ≤ `particle_size` 的粒子对被永久排除（否则绳内相邻粒子每步都在互相排斥）；
静止距离 > `particle_size` 的粒子对参与检测，当前距离小于 `particle_size` 时产生排斥。
本任务 `particle_size` = 4mm，沿绳的网格段长 `segment_length` = 9mm，
因此轴向相邻的粒子对（静止距离 9mm）**参与**自碰撞检测。

**第 3 步：弯曲使内侧纤维压缩。** 绳弯曲时，中心线曲率半径为 `R`，
距中心线 `r` 的纤维其轴向间距按 `(R − r)/R` 收缩。代入 `r` = 绳半径 4mm、
轴向静止距离 9mm、阈值 4mm：

```
9 · (R − 4)/R < 4    =>    R < 7.2mm
```

即中心线曲率半径小于约 7.2mm 时，内侧表面的轴向邻居距离跌破 `particle_size`，
产生本不应存在的排斥约束。该排斥与拉伸约束方向相反，两者在同一批粒子上反复迭代。

**第 4 步：耦合器覆写速度。**（2026-08-05 按 Genesis 源码更正，原先记的"外部写入位置 +
按 `1/dt` 反推速度"不准确。）被 `fix_particles_to_link` 约束的粒子由
`legacy_coupler.kernel_pbd_rigid_solve_animate_particles_by_link` 驱动：

```python
corrective_vel = (target_world_pos - particle_pos) * clamped_inv_dt
particles_reordered[i_rp, i_env].vel = corrective_vel + target_world_vel
```

`clamped_inv_dt = min(1/dt, CLAMPED_INV_DT)`，`CLAMPED_INV_DT` 是模块级常量 50，
本任务 `dt` = 0.01 所以取 50。即：位置误差每 1mm 产生 0.05m/s 的修正速度，
且该速度是**覆写**而非叠加，PBD 自己算出的速度被丢弃。

该 kernel 在 PBD 求解**之后**执行（源码注释写明"hence the corrective velocity is off by
a frame"）。所以 §11 的 quat 快照把接头转 90 度时，带内粒子的目标位置一次移动最多约 17mm，
对应修正速度最高约 0.85m/s，在一个 10ms 步内约 8.5mm —— 与实测的 11.79mm 同量级。

PBD 自身的速度重建 `vel = (pos − ipos) / substep_dt`（`_kernel_compute_velocity`）
用的是**子步**步长。本任务 `substeps` = 4，`substep_dt` = 2.5ms。

**第 5 步：不收敛。** 第 3 步的约束冲突与第 4 步的速度放大同时作用在接头附近的同一批粒子上，
迭代次数（`max_stretch_solver_iterations` = 16、`max_bending_solver_iterations` = 12）
不足以收敛，残差逐步累积。

**第 6 步：钳制。** 位置发散后超出求解域范围，被钳制到域角点 `(100,100,100)`。
蒙皮网格顶点绑定到这些粒子，于是渲染出贯穿画面的三角形。

### 1.3 关于 7.2mm 这条线

第 3 步算出的 7.2mm 是排斥约束**开始参与**的曲率半径，不是发散的阈值。
run #8 中 `bend_r` 在 4.6~4.9mm 维持 380 步未发散（§12.4），说明约束参与之后仍可能收敛。
两者的关系尚未验证。目前可用的判据是 `bend_r` 的持续下降（§12.4、§13.1）。

---

## 2. trace 的读取方式

运行：

```bash
cd /projects/bfuo/jlyu3/topogym
source .venv-gs110/bin/activate
export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --viewer --keep-open --max-moves 1 --verbose --strands 2 --trace
```

这个 demo 用 `--keep-open`（`--viewer` 本身也会保持窗口）。
`--close-on-finish` 是 `untangle_physical_handle_demo` 与
`cable_routing_physical_handle_demo` 的参数，这里不接受。

trace 写入 `runs/untangle_continuous_trace_<时间戳>.log`，每行 flush，进程崩溃后记录仍完整。
列：

```
step  phase  strand  max_v  jump(mm/step)  offset(mm)  bend_r(mm)  bend_at(s)  bend_free(mm)  minz(mm)  parked
```

文件头记录该次运行的配置、centerline 采样数与采样间距 `L`、以及
`bend_r → 转角` 的换算式（§12.1）。

`bend_at` 是最小弯曲半径在绳上的归一化位置，与文件头记录的抓取弧长对比即可定位：

| `bend_at` | 位置 |
|---|---|
| ≈ 抓取弧长 | 固定粒子带 |
| < 0.15 | 锚定端（`fix_particles` 硬约束） |
| > 0.93 | 自由端 |
| 其他 | 中段，通常在交叉处 |

`bend_free` 是排除两端固定粒子带之后的最小弯曲半径。与 `bend_r` 接近时，
转角位于自由段；明显大于 `bend_r` 时，`bend_r` 的读数来自刚性段与自由段的接缝，
不代表任何一段的实际曲率。

EVENT 行记录的是发散被检出的时刻，起因在其上方数十行。
WARN 行记录 `bend_r` 开始持续下降的时刻，通常远早于 EVENT。

---

## 3. 各轮记录

| # | 日期 | 实验设置 | bend_r 最小 | bend_at | 结果 |
|---|---|---|---|---|---|
| 1 | 08-02 | seg=4mm，无 taper | 4.6mm | 未记录 | 发散（3 绳，s1） |
| 2 | 08-02 | seg=9mm（回滚），无 taper | 6.1mm | 未记录 | 发散（2 绳，s0） |
| 3 | 08-03 | seg=9mm，taper=0.6 | 4.7mm | 未记录 | 发散（2 绳，s0）；taper 无效 |
| 4 | 08-03 | seg=9mm，taper=0.6，新增 bend_at 列 | 4.4mm | 0.875（抓取弧长 0.838） | 发散（step 898） |
| 5 | 08-03 | 新增 tail_clearance: -0.030（H7 实验） | 5.2mm | 全部位于固定粒子带 | 发散（cross_over，step 1248）；H7 否定 |
| 6 | 08-03 | 刚体接头 + fix_particles_to_link + PBDHandleDragPrimitive | 未记录 | 未记录 | 已运行，未记录 bend_r；视觉问题见 §7 |
| 7 | 08-03 | over_lift 16→12mm（视觉修正） | 未记录 | 未记录 | 已运行 |
| 8 | 08-03 | 新增 assisted grasp | 4.1mm | 0.986 | 发散（carry_up，step 1058）；完整分析见 §12 |
| 9 | 08-04 | §11 的 quat 修复 + 诊断补齐，`carry_pitch_deg` = 0 | 11.8mm（`bend_free` 相同） | 0.343 | **未发散**；见 §13.5 |

run #4 的位置分布（s0，发散前全部样本）：

```
carry_up 阶段 78 个样本：
  固定粒子带  76 次 (97%)
  中段         2 次 ( 3%)
  bend_at 中位数 0.875，bend_r 最小 4.40mm

抓取之前（step 1~780）：最小弯曲半径位于中段 s=0.347（交叉处），bend_r 稳定 10.5mm
step 800 起（首次 lift_test）：位置移至 0.875 并保持，bend_r 下降至 4.4mm
```

最小弯曲半径的位置在固定粒子带边缘外侧，出现在抬升动作之后。

---

## 4. 假设与确认程度

| # | 假设 | 确认程度 | 依据 |
|---|---|---|---|
| H1 | 自碰撞永久违反（环上粒子间距 < particle_size） | 已否定 | `pbd_solver._func_solve_collision` 的 `rest_dist > particle_size` 判据已排除同体近邻，见 §1.2 第 2 步 |
| H2 | 网格过稀导致碰撞屏障存在间隙，绳与绳相互嵌入 | 成立，与求解发散无关 | 沿绳间距 9mm > 碰撞直径 4mm，实测嵌入 4~5mm。降到 4mm 会触发 H3 |
| H3 | 网格过密使对角邻居接近阈值，弯曲时产生不应存在的自碰撞 | 成立 | seg=4mm 时对角静止距离 5.04mm，记录的触发弯曲半径为 19.4mm（推导方式未记录）；该配置下必然发散。已回滚到 9mm |
| H4 | 夹爪刚体接触压迫 PBD 粒子 | 已排除 | `pinch.robot_rope_contact: false`（`needs_coup=False`），机器人不参与 PBD 耦合 |
| H5 | 桌面摩擦干扰 | 已排除 | 摩擦只作用于 z 低于「桌面 + 5mm」的粒子，被抬起的绳段不在该范围内 |
| H6 | 固定粒子带刚性导致边缘应力集中 | 位置已确认，taper 无效 | bend_at=0.875 稳定落在带边缘；`grasp_taper: 0.6` 之后 bend_r 由 6.1 降至 4.4mm |
| H7 | 抬升高度超过尾段弧长，尾段悬空，抓取点转角增大 | 已否定 | 尾段搭回桌面后 bend_r 由 4.4 升至 5.2mm，最小弯曲半径仍全部位于固定粒子带，仍发散 |
| H8 | 自制固定粒子带按世界坐标保存偏移，姿态被固定为水平，抬起时带边缘必须完成 90 度转向 | 已确认 | 见 §6、§11 |
| H9 | 水平握持的插头使出线口产生约 90 度转角 | 已否定 | run #9 中接头全程水平握持，grasp 与 carry_up 全程 `bend_r` = 11.8mm、`bend_free` 与之相等，出线口无紧弯。原推理把绳当作自由垂挂，实际绳长 526mm、另一端锚定在 425mm 外，`max_taut_ratio` 又把路点收在 0.90 以内，绳沿弦方向离开接头 |

### H7 的推导

抓取弧长 0.838 把绳分为两段：

```
锚定侧 373mm，水平跨度约 350mm  -> 以约 19 度上升
自由侧（尾段）72mm
```

planner 的抬升高度取 `max(跨过其他绳所需, 尾段弧长 + tail_clearance)`，约 82mm 以上
（实测 lift_z 120~162mm）。尾段 72mm 小于抬升高度，因此尾段接触不到桌面，接近竖直悬空。

抓取点两侧的方向相差约 161 度（一侧上升 19°，一侧下垂 90°），且必须在很短的弧上完成。
绳半径 4mm，实测 bend_r 4.4mm。

该几何由 08-02 加入 `tail_clearance` 引入。当时是为处理「绳尾拖地推动下方的绳」，
抬升高度由 59mm 提高到 120~162mm；59mm 小于尾段 92mm 时尾段仍搭在桌面上，
抓取点两侧的方向差小得多。两项需求相互制约：

- 抬升 < 尾段：尾段拖地，扫到下方的绳（08-02 记录）
- 抬升 > 尾段：尾段竖直悬空，抓取点转角增大，随后发散（本轮）

---

## 5. 相关代码

### 诊断（`topogym/supervision/`）

| 文件 | 符号 | 作用 |
|---|---|---|
| `rope_trace.py` | `RopeTrace`, `min_bend_radius` | 每步流式写 trace 文件；返回弯曲半径与其位置 |
| `pbd_probe.py` | `StepProbe`, `probe_particles`, `ejected_mask`, `max_particle_jump`, `DOMAIN_CORNER` | 包装 `scene.step` 的公共骨架与 PBD 基础量测 |
| `rope_stability.py` | `particle_spacing_reports`, `rope_blow_ups` | 粒子间距与碰撞直径的对比；粒子偏离中心线的检测 |
| `untangle_continuous.py` | `rope_health_lines`, `crossing_lines` | 两个 demo 共用的日志行，含相互嵌入的标注 |

### 物理

| 文件 | 符号 | 作用 |
|---|---|---|
| `topogym/world/rope.py` | `TabletopParticleFriction` | 自实现库仑摩擦（Genesis 的绳与刚体摩擦为冲量式，静止时归零）。只修改速度，不写入位置 |
| `topogym/primitives/attachment.py` | `ParticleAttachment`（`weights=`） | 自制固定粒子带与渐变。run #6 起本任务不再使用（H8），保留给其他调用方 |
| `topogym/tasks/entangle/untangle_continuous.py` | `_add_free_end_connectors` | 自由端刚体接头与 `fix_particles_to_link` |
| 同上 | `_robot_material` | 机器人 `needs_coup=False`，排除夹爪与 PBD 的接触 |
| 同上 | `_table_material` / `_install_table_friction` | 桌子 `coup_friction` 覆写与库仑摩擦安装 |
| 同上 | `settle_scene`（`damp_every`） | 速度清零式阻尼，现已关闭，由摩擦取代 |
| 同上 | `rope_mesh` 的 z-clamp | 防止样条下冲把绳管插入桌面 |

### 规划

| 文件 | 内容 |
|---|---|
| `topogym/planning/untangle_continuous_planner.py` | run #6 起抓取自由端（`grasp_s=1.0`）；抬升高度取「跨过其他绳」与「尾段离地」的较大值（尾段现为 0）；`place_pullback` 降低绷紧比 |

### 关键配置（`configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml`）

| 键 | 现值 | 说明 |
|---|---|---|
| `rope.mesh.segment_length` | 0.009 | 不可下调，见 H2/H3 的相互制约（配置注释中有完整曲线） |
| `pinch.grasp_half_width` | 0.02 | 固定粒子带 ±8.9mm |
| `pinch.grasp_taper` | 0.6 | H6 遗留，run #6 起不再生效 |
| `pinch.tail_clearance` | -0.030 | H7 实验遗留。抓取自由端后尾段为 0，该值无作用 |
| `pinch.robot_rope_contact` | false | 排除 H4 |
| `pinch.carry_pitch_deg` | 0.0 | 插头俯仰，默认关闭，见 §13.2 |
| `rope.tabletop_friction.*` | enabled | 见 `pbd_tabletop_friction_zh.md` |

---

## 6. H8：改用刚体接头（run #6）

### 诊断

自制固定粒子带 `ParticleAttachment` 保存的是 attach 时刻捕获的世界坐标偏移：

```python
positions = center + self.particle_offsets   # offsets 不随姿态旋转
```

attach 发生在绳平躺时，因此这条 18mm 的带被固定为水平姿态，不允许旋转。
手上抬时带内不产生弯曲，带两侧的绳需要下垂，转向必须在带边缘几毫米内完成，
半径 4mm 的绳被弯到 5~7mm 曲率半径，进入 §1.2 第 3 步与第 4 步的机制。

在此之前各项修改无效的原因：taper 改变的是带的刚度分布，未改变强制水平这一点；
`segment_length` 改变的是自碰撞的触发阈值；`tail_clearance` 改变的是尾段几何。
三者均在链条的下游。

### 本轮改动

采用离散版 untangle / cable_routing 已验证的机制：

| 环节 | 改动 |
|---|---|
| 抓取对象 | 自由端的刚体接头（`rope.free_end_connector`，竖立圆柱 R8.5×H32mm，不插入任何插孔） |
| 绳的跟随方式 | Genesis 原生 `fix_particles_to_link`，保存相对 link 的位姿，跟随其姿态，在求解器内部推进，不经过外部写入位置 |
| 夹爪的抓取方式 | `PBDHandleDragPrimitive`（刚体与刚体接触，完整约束求解），替代 `PBDParticleAttachmentDragPrimitive` |
| 抓取位置 | planner 改为抓取自由端（`grasp_s = 1.0`） |

抓取自由端使尾段长度为 0，H7 中记录的两项相互制约的需求同时消失。

### 判读

- `bend_r` 回到 10mm 量级且不发散：H8 成立
- 仍发散：查看 `bend_at`。仍在自由端附近说明接头与绳的交界仍是硬边界；
  移到锚定端则是另一处约束边界

回退方式：`rope.free_end_connector.enabled: false`。planner 已改为抓取自由端，
需同时回退 `grasp_s`。

---

## 7. 两绳间距过大（视觉问题，run #6 → #7）

现象：viewer 中两根绳在竖直方向的间距明显大于预期。

诊断：间距来自 spawn 时刻，而非静止之后。run #6 的 trace 中 planner 报告
`centreline gap 1.8mm of a possible 12mm`，即静止后交叉处仍相互嵌入（H2，未变）。

原因是 08-02 把 `braid.verify_braid_spec` 的门槛由 `2R + particle_size` 提高到
`2R + 2*particle_size`，并把 `over_lift` 设为 16mm，取值过大：

```
两绳 spawn 时不相互作用的充要条件：
  表面粒子位于半径 R 处，碰撞只在粒子中心距 < particle_size 时触发
  => 中心线间距 >= 2R + particle_size = 12mm
```

12mm 同时等于碰撞生效时的静止间距，取该值使 spawn 位置等于静止位置，
沉降过程缩短，也不再向 settle 注入额外动能。

改动：`verify_braid_spec` 门槛回到 `2R + PS`；`braid.over_lift` 由 16mm 改为 12mm。
可见间隙由 8mm 变为 4mm。60 组（2/3 绳 × 3 难度 × 10 seed）复验：verify 全部通过、
检测器与 braid ground truth 全部一致、spawn 表面间隙 4.00mm。

静止后交叉处 1.8mm 的相互嵌入属于 H2，与 `segment_length` 的取值相互制约，本轮未处理。

---

## 8. 抬放后交叉关系未改变（2026-08-03）

demo 把绳抬起、横移、放下之后，两绳的上下关系不变。

### 原因

`lift_z` 只保证抓取点越过其他绳的顶部。抓取位置是自由端，而交叉点在距自由端
135~156mm 弧长处，抬升 63mm 时交叉点仍压在下方的绳上，放下后恢复原状。

把交叉点本身抬离桌面需要约 198~220mm。

> §10 更正：此处原写「锚点到自由端 425mm，抬到 220mm 的弦长约 475mm 超过绳长 445mm，
> 因此这条路径不可行」。445mm 有误，实测弧长为 525mm，该结论作废。

### 处理方式：改为摊直

用绳自身的长度作为约束：525mm 的绳两端在同一车道内相距 400mm 时，
没有多余长度绕到其他车道。

`pinch.place_pullback: 0.120 -> 0.025`。放置点 = `braid.x_end - place_pullback`，
锚点到放置点 400mm，绷紧比 0.899，松弛 45mm。

原值 120mm 是抓取中段时期的取值，当时靠回收提高绷紧比；改为抓取自由端后，
它在 305mm 跨度内留下 140mm 松弛，绳会重新跨回其他车道。

### 离线验证（几何检测器，无 GPU）

把被移动的那根替换为沿自己车道的直线，统计剩余交叉：

| n_strands | 组合数 | 交叉数减少 |
|---|---|---|
| 2 | 18 | 18 / 18 |
| 3 | 18 | 12 / 18（`len=5 seed=2` 由 5 增至 7） |

反复执行 planner 至收敛（2 根绳，难度 2/3/5 × 8 seed）：24/24 解开，每次 2 步。

### 已知限制：`--strands 3` 不保证交叉数单调下降

三条车道时，把一根摊直到自己车道需要横穿中间那条车道，可能产生新的交叉。
这是摊直策略本身的边界。两根绳的两条车道互不相交，没有这一限制，
也是 `braid.n_strands` 在 2026-08-03 定为 2 的原因之一。

三根绳需要 planner 改为按车道顺序处理（先处理最外侧），本轮未做。

### 自由端接头改为侧躺的工业插头（同日）

原先是直立圆柱（占位）。改为使用离散版 untangle 的同一几何
`prefabs.rope_endpoint_connector`（销、法兰、环槽抓取柱、圆帽），不插入任何插孔，
`euler=(0, -90, 0)` 侧躺在桌面上：local +z → world -x，圆帽（线缆进入端）朝向锚定端，
销朝外悬空。

躺平时最粗的法兰接触桌面，轴心离桌 = `flange_radius` = 11mm。沿 x 总长 34mm，
抓取柱 Ø15mm 跨 x=±7mm，`pinch.grasp_qpos_handle` 引用
`${prefabs.rope_endpoint_connector.column_radius}` = 7.5mm。法兰边缘距夹爪中心 7mm。

改动文件：
- `topogym/tasks/entangle/untangle_continuous.py` `_add_free_end_connectors()`：`gs.morphs.Cylinder` → `gs.morphs.Mesh(connector_obj_path(...), euler=(0,-90,0))`
- `topogym/planning/untangle_continuous_planner.py`：`place_xy` 改为车道末端
- `configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml`：`free_end_connector` 转引 prefab；`place_pullback` 0.120→0.025；`n_strands` 3→2

---

## 9. 抓取失败（2026-08-03）

trace 中 1772 步全部停留在 `move1_grasp`，`minz` 恒为 921.6mm（桌面高度）、
`bend_r` 恒为 11mm。绳的状态正常，未发生发散，只是未被抓起。
primitive 的 `lift_test` 未通过，走了 `recovery_open` 退出。

### 原因：缺少另外两个 demo 具备的机制

`pinch.grasp_qpos_handle` 等于抓取柱半径，手指闭合到正好贴合柱面，预紧为零，
因而摩擦力为零。这是仓库的既定约定（prefab 注释：`grasp_qpos 应取 =column_radius`），
因为使用该插头的另外两个任务不依赖摩擦：

| demo | `ee_quat` 转腕 | `on_close` assisted attachment |
|---|---|---|
| `untangle_physical_handle_demo` | 有 | 有（socket latch → 手） |
| `cable_routing_physical_handle_demo` | 有 | 有 |
| `untangle_continuous_physical_pinch_demo`（改前） | 无 | 无 |

`PBDHandleDragPrimitive` 的 lift 检查在 `runtime_attachment` 之前执行，
因此只有在 `on_close` 中装上的 attachment 能通过该检查。连续版两者都没有，
相当于用零预紧接触的摩擦力完成抬升。

改动：`demos/entangle/untangle_continuous_physical_pinch_demo.py` 加入
`AttachmentManager`、`on_close=engage_grasp_attachment`、`before_release=`，
以及 `ee_quat=ee_quat_for_yaw(default, 插头轴向)`（转腕理由同离散版：
避免指垫压在线缆下垂的方向上）。

### 同时：接头放大 1.35 倍（本任务局部覆盖，不改 prefab）

躺平姿态下存在两项直立姿态没有的几何问题，放大同时处理：

| 项目 | 放大前 | 放大后 |
|---|---|---|
| 轴心离桌（= flange_radius，指垫中心位于该高度） | 11mm | 15mm |
| 指垫底缘离桌（指垫半高约 8.5mm） | 2.5mm | 6.5mm |
| 抓取柱沿轴半长（指垫为 ±7.5mm） | ±7mm，指垫超出到法兰上 | ±10mm，指垫完全落在柱面内 |

法兰 Ø22mm 大于柱 Ø15mm，躺平时位于指垫正下方的 x 范围内，会先于抓取柱接触指垫。
直立姿态下法兰位于柱下方，顶部抓取接触不到，轴心高度也不由它决定。

`prefabs.rope_endpoint_connector` 保持不变（离散 untangle 与 cable_routing 共用），
放大值写在 `configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml` 的
`rope.free_end_connector` 中，`pinch.grasp_qpos_handle` 同步由 0.0075 改为 0.010。

---

## 10. 横移时穿过另一根绳（2026-08-03）

### 更正 §8 的一处数据

§8 原写「抬到 220mm 会超过绳长 445mm」。445mm 有误，实测弧长 525mm。
两端相距 433mm，spawn 时已伸展 82%，可用余量约 92mm。因此抬高这条路径可行，
§8 中「这条路径不可行」的结论作废（已在 §8 就地标注）。

### 原因：lift 只按抓取点计算

`lift_z` 取 `obstacle_top + lift_clearance` = 63mm，只保证手越过其他绳的顶部。
绳从手上垂下，交叉点在 120~156mm 弧长之外，横移时该段仍在桌面上，
于是被横向拖过下方的绳。

改动：lift 改为按交叉点到自由端的弧长计算：
`lift_z = obstacle_top + max(lift_clearance, crossing_arc + lift_clearance, tail_arc + tail_clearance)`。
绳大致竖直垂下时，把交叉点抬到 clearance 高度，手需位于 `crossing_arc + clearance`。

### 同时加入 `max_taut_ratio` 限制

在自由端原地抬到 219mm，最短的 braid（length=2）需要 101% 的绳长。
向锚定端收 x 可以换回高度，因此每个路点沿「锚点 → 目标」方向收回可达范围
（`pinch.max_taut_ratio: 0.90`，只向内收）。

该限制放在 planner 中，收回后的三个路点通过 `command.carry/cross/settle` 传给 demo；
demo 不再从 `grasp_xy/place_xy/lift_z` 重建路点（重建会撤销该限制）。

### 离线验证（2 根绳，难度 2/3/5 × 4 seed）

| length | lift | carry 收回 | 最大绷紧比 | 横移时交叉点高出其他绳顶 |
|---|---|---|---|---|
| 2 | 219mm | 56mm | 0.900 | +40mm |
| 3 | 198mm | 1mm | 0.900 | +40mm |
| 5 | 183mm | 0mm | 0.712 | +40mm |

三个路点（carry / cross / place）的绷紧比全部 ≤ 0.90。

### 改动文件

- `topogym/planning/untangle_continuous_planner.py`：`crossing_arc` 与 `within_reach()`；command 新增 `crossing_arc` / `carry` / `cross` / `settle`
- `demos/entangle/untangle_continuous_physical_pinch_demo.py`：改用 `command.carry/cross/settle`；日志加 `crossing_arc` / `pulled_back`
- `configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml`：新增 `pinch.max_taut_ratio: 0.90`

---

## 11. run #8：加入 assisted grasp 之后的求解发散（2026-08-03）

`runs/untangle_continuous_trace.log`，seed=0 word=(1,1,1)，2 根绳。

抓取环节通过：phase 依次为 `move1_grasp`(1840 行) → `move1_carry_up`(560 行) →
`move1_cross_over`(44 行)，§9 的 assisted grasp 生效。

随后发散：`EVENT step=1058 phase=move1_carry_up offset grew 172647.6mm`，
粒子被钳制到求解域角点。

### 两根绳的对比

| 列 | 未被抓取的 s1 | 被抓取的 s0 |
|---|---|---|
| `bend_r` | 全程 11~14mm | 前 660 步 11.9mm，之后 5.8 → 4.8 → 4.1mm |
| `bend_at` | 0.34 / 0.61，位于中段 | 前 660 步位于中段，之后移至 0.971 → 0.986 |
| `jump` | < 0.8mm/step | 0.03 → 0.9 → 9.0 → 172671 |

`bend_at ≈ 0.986` 对应接头位置。绳半径 4mm，弯曲半径降至 4.1mm，
低于 §1.2 第 3 步算出的 7.2mm。

时间上，该弯折在 step 660 前后形成，此时仍在 `move1_grasp` 阶段，即 `lift_test` 抬升期间；
`carry_up` 阶段是在已有弯折的基础上继续收紧。因此 §10 提高抬升高度的改动与本次发散无关。

### 原因：`RigidAttachment.sync()` 写入纯 yaw 四元数

```python
self.entity.set_quat(yaw_quat(self.yaw + self.child_yaw_offset), ...)   # 仅 yaw
```

`yaw_quat` 的 pitch 与 roll 恒为 0。该默认值对仓库中其他刚体成立
（方块、盘、直立插入插孔的插头），对它们 `set_quat` 不改变姿态。

连续版的插头是 `euler=(0,-90,0)` 躺平的。attachment 装上后，`sync()` 在一步之内
把它旋转到直立姿态；绳末粒子通过 `fix_particles_to_link` 绑定在该 link 上，
随之旋转 90 度，进入 §1.2 第 4 步的机制。

即 §9 加入 assisted grasp 时同时引入了一次姿态突变。

### 改动

`RigidAttachment` 增加可选的 `quat` 字段：给定时按该值保持，未给定时走原有的 yaw-only 路径
（未给定时调用序列不变，已离线验证）。demo 在 `on_close` 中传入接头当时的实际姿态。

- `topogym/primitives/attachment.py`：`RigidAttachment.quat`、`sync()` 分支、`AttachmentManager.create(quat=)`
- `topogym/primitives/physical_contact.py`：新增 `entity_quat()`
- `topogym/primitives/__init__.py`：导出 `entity_quat`
- `demos/entangle/untangle_continuous_physical_pinch_demo.py`：`quat=entity_quat(_connector)`

### 未处理：抬升后绳在接头处仍需转约 90 度（H9）

即使不再有姿态突变，插头被水平握持而绳需要竖直垂下时，出线口处仍存在约 90 度转角。
trace 中 step 680~920（已 settle，仅握持）`bend_r` 稳定在 4.8~4.6mm。

离散版没有这一问题：其插头直立，绳从顶端竖直出线，方向与吊起时的垂挂方向一致。

下一次 trace 的判据：`bend_at` 仍在 0.986 附近且 `bend_r` < 8mm 时，H9 成立，
处理方式是让插头在被吊起时绕水平轴旋转使圆帽朝下。本轮只改姿态突变一处。

> §12 修正了本节最后一段的推论：`bend_r` 在 step 680~920 稳定在 4.6~4.8mm，
> 不足以证明该弯折与姿态突变无关。见 §12.5。

---

## 12. run #8 trace 的完整分析（2026-08-03）

原始文件：本目录 `run08_2026-08-03_trace.log`（`runs/untangle_continuous_trace.log` 在
08-03 13:52 的副本，2453 行，seed=0 word=(1,1,1)，2 根绳）。

### 12.0 trace 的时间归属

| 事件 | 时间 |
|---|---|
| trace 写入完成 | 08-03 13:52 |
| §11 的 quat 修复落地（`attachment.py` / demo） | 08-03 13:55 / 13:56 |

该 trace 记录的是修复之前的运行。§12.1~12.5 是对 run #8 的分析，适用范围仅限于此；
修复之后的行为需要新的 trace，判读方式见 §12.6。
（`runs/` 下只有这一个文件，且 `RopeTrace` 以 `"w"` 打开，修复之后那次运行要么未开
`--trace`，要么记录已被覆盖。）

### 12.1 bend_r 与转角的换算

`bend_r` 是 centerline 上连续三点的外接圆半径。该值同时取决于采样间距，单独读取无法判断
弯折程度：同一个 90 度转角，采样间距 1mm 时半径为 0.7mm，间距 7.5mm 时为 5.3mm。

设相邻采样点间距为 `L`、中间点处的转角为 θ（θ=0 表示共线）：

```
bend_r = L / (2 sin(θ/2))        <=>        θ = 2 · arcsin( L / (2 · bend_r) )
```

`L` 需要单独确定。`strand_centerline` 将粒子按弧长分入 80 个区间取均值，空区间跳过，
因此 `L` 既不等于区间宽度也不等于网格段长。从 `bend_at` 反解
（`bend_at = (worst+1)/(N-1)`，结果必须为整数）：

```
s0 的 0.629 / 0.343 / 0.971 / 0.986  ->  N-1 = 70  （71 个采样点）
s1 的 0.606 / 0.887 / 0.338          ->  N-1 = 71  （72 个采样点）
```

弧长实测 525mm（§10），因此 **L ≈ 525/70 ≈ 7.5mm**（区间宽度 6.6mm 为下界，
跨过一个空区间时可达 9mm）。

| `bend_r` | θ（L=7.5mm） | θ 下界（L=6.6mm） |
|---|---|---|
| 11.8mm | 37° | 33° |
| 8.0mm | 56° | 49° |
| 4.7mm | 106° | 89° |
| 4.1mm | 132° | 107° |
| 3.8mm | 161° | 120° |

`L` 的不确定性影响绝对角度，不影响以下结论：`bend_r` = 4.7mm 在任何合理的 `L` 下
对应转角均 ≥ 89°。转角 ≤ 45° 要求 `bend_r ≥ L/(2·sin22.5°) ≈ 10~12mm`，
与健康状态实测的 11.8mm 一致。**修复的判据取 `bend_r ≥ 10mm`。**

该换算已写入 `RopeTrace` 的 header（§13.1），后续 trace 不需要再反解。

### 12.2 时间线（s0 为被抓取的绳）

| step | phase | jump(mm/step) | bend_r | bend_at | 现象 |
|---|---|---|---|---|---|
| 1~670 | move1_grasp | < 0.024 | 11.8mm | 0.629 → 0.343 | 最小弯曲半径位于中段交叉处 |
| 671 | move1_grasp | 11.79 | 11.8 → 8.5 | 0.343 → 0.986 | 单步位移 11.79mm；最小弯曲半径位置移至接头 |
| 672~674 | move1_grasp | 12.9 → 8.5 | 5.4 → 6.1 | 0.986 | 震荡 |
| 675~920 | move1_grasp | 6.9 衰减至 0.025 | 4.6~5.2 | 0.971 / 0.986 | 运动衰减至准静态，弯折保持 |
| 921~1056 | move1_carry_up | 0.30~0.97 | 4.7 → 3.8（单调） | 0.986 | 搬运期间弯折持续收紧 |
| 1057 | move1_carry_up | 9.04 | 3.8 | 0.986 | 位移出现尖峰 |
| 1058 | move1_carry_up | 172671 | — | — | 503 个粒子被钳制到 (100,100,100) |
| 1059 | move1_carry_up | 172823 | 2.9e8 | — | 1074 个粒子被钳制，运行结束 |

s1（未被抓取）全程 `bend_r` 13.4~13.7mm、`jump` < 1.05mm/step、`parked` 0；
发散发生时 `jump` 短暂升至 2.0mm/step。

`minz` 全程恒为 921.64mm，即绳的最低点始终位于桌面高度，与仅接头一端被抬起一致。

### 12.3 step 671 的单步位移

前后各 600 步的 `jump` 均在 0.01mm/step 量级，该步为 11.79mm，属于外部写入位置。

量级核对：绕转轴半径 `d` 的粒子旋转 90 度，位移为 `d·√2`。11.79mm 对应 d ≈ 8.3mm。
固定粒子带为"距自由端中心 12mm 球内的粒子"，绳半径 4mm，带内粒子距转轴 0~12.6mm，
8.3mm 在此范围内。

另有两项一致的观测：

- 同一步 `bend_at` 从 0.343（中段交叉处）变为 0.986（接头），无中间过渡值；
- 此后 250 步 `jump` 衰减至 0.025mm/step，`bend_at` 保持在接头位置。

结论：§11 的诊断（`RigidAttachment.sync()` 使用纯 yaw 四元数，将躺平的插头旋转至直立）
成立。该 trace 中仅此一处出现外部写入位置造成的单步位移。

### 12.4 发散步的分解

```
1056   jump 0.97      bend_r 3.8
1057   jump 9.04      bend_r 3.8
1058   jump 172671    parked 503
1059   jump 172823    parked 1074
```

step 921~1056 共 136 步，`jump` 稳定在 0.3~0.97mm/step（对应搬运速度），
`bend_r` 从 4.7 单调下降至 3.8mm，即转角从 106° 增至 161°。发散在单步内完成。

`bend_r` 在 4.6~4.9mm（90~106°）维持 380 步未发生发散。`bend_r` 的单调下降与发散相关；
最小值与发散之间无对应关系——§3 记录中 run #2 的最小值为 6.1mm，同样发生发散。

### 12.5 §11 关于 H9 的推论

§11 的推论：step 680~920 处于准静态，`bend_r` 稳定在 4.6~4.8mm，因此该弯折与姿态突变无关。

该推论未考虑 `sync()` 的行为：`sync()` 每步写入 `set_quat(yaw_quat(...))`，
因此 step 671 之后插头持续被约束在直立姿态。step 680~920 测得的稳态对应
"插头直立、绳躺在桌面"这一构型，其转角为 90 度（实测 106°）。该稳态仍处于姿态突变的影响下。

| 命题 | run #8 的支持程度 |
|---|---|
| quat 快照造成 step 671 的单步位移 | 已确认 |
| quat 快照造成此后 380 步的持续弯折 | 已确认（插头被约束在直立姿态） |
| 水平握持的插头同样产生 ~90 度转角（H9） | 该 trace 无法判断 |

H9 的依据是：松弛的绳从支点垂下时出线方向接近垂直，插头水平握持时出线口即为 90 度转角。
该机制尚未验证。

### 12.6 新 trace 的判读表

运行方式（trace 现已带时间戳，见 §13.1）：

```bash
export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --viewer --keep-open --max-moves 1 --verbose --strands 2 --trace
```

首先检查夹爪闭合前后是否存在单步 >5mm 的 `jump`：

| trace 特征 | 结论 | 后续处理 |
|---|---|---|
| 闭合处仍有单步 >5mm 位移，`bend_at` 变为 ~0.986 | quat 修复未生效 | 检查 `entity_quat()` 的分量顺序（wxyz）与 batch 维；检查是否有其他位置调用 `set_quat` |
| 无单步位移，握持后 `bend_free` 降至 4~6mm 并保持在 ~0.986 | H9 成立 | 以运行 2（`carry_pitch_deg: 60`）的结果为准 |
| 无单步位移，`bend_free` ≥ 10mm 而 `bend_r` 为 4~6mm | 读数来自刚性段与自由段的接缝，不是绳的实际曲率 | 俯仰不会改变该读数，转向 §14 的可调项 |
| 无单步位移，握持时 `bend_free` ≥ 10mm，`carry_up` 期间单调下降 | H10：抬升/回收路径产生弯折 | 调整 `max_taut_ratio` 或路点顺序 |
| 无单步位移，`bend_at` < 0.15 | 问题位于锚定端（`fix_particles` 硬约束） | 与自由端无关，另行处理 |
| 未发生发散 | §11 的 quat 修复已解决该问题 | 记录并结束 |

判读依据为 `bend_r` 的变化趋势（§12.4），以及 `bend_free` 与 `bend_r` 的差（§13.1）。

### 12.7 诊断缺口

| 问题 | 影响 |
|---|---|
| `max_v` 全程为 `nan`：`RopeTrace._sample` 中 `entity.get_particles_vel()` 的异常被 `except Exception` 捕获后未记录 | 该列 2453 行无数据。速度是"外部写入位置 → `vel=(pos-ipos)/dt` 放大"的直接观测量，只能改用 `jump` 间接推断。原因已由 run #9 查明（GPU 张量缺 `.cpu()`），见 §13.5 |
| trace 以固定文件名 `open(..., "w")` 打开 | 每次运行覆盖上一次的记录 |
| trace 中无事件标记：`on_close` / `lift_test` / 释放均不写入文件 | §12.3 中"该步对应哪个动作"需要通过 `jump` 尖峰推断。`RopeTrace.note()` 已存在，demo 在这些时刻调用即可 |

以上三项已在 §13.1 处理。

---

## 13. run #9：改动与结果（2026-08-04）

§12.7 的三项已处理；同时落地插头俯仰机制，默认关闭，用于对照两次运行的结果。

### 13.1 诊断

| 文件 | 改动 |
|---|---|
| `topogym/supervision/rope_trace.py` | header 增加 `bend_r → 转角` 换算行（每根绳的 centerline 采样数、中位采样间距 L、直角对应的 bend_r）；`get_particles_vel()` 的异常首次写入文件（`# NOTE`）；新增 `_check_tightening` 检查；新增 `bend_free` 列 |
| `demos/entangle/untangle_continuous_physical_pinch_demo.py` | `--trace` 默认路径带时间戳；`on_close` / lift 前 / 释放三处调用 `trace.note` |

`_check_tightening` 的判据：`bend_r` 低于 8mm（`WARN_BEND_R`）且相对最近 40 个样本
（`WARN_WINDOW`）的最大值下降超过 5%（`WARN_DROP`）时写入一行 `# WARN`。
每根绳只写一次，不中断运行。逐样本比较不适用，因为相邻样本存在抖动
（4.1、4.2、4.1、4.0……）。

用 run #8 的 `bend_r` 列回放验证：

```
s0（被抓取）：# WARN step=672
s1（未被抓取）：无输出
```

发散发生在 step 1059，该检查的触发点早于发散 387 步，位置对应 §12.3 的 quat 快照。

**`bend_free` 列**：`bend_at` 稳定在 0.986，而固定粒子带的范围是"距自由端中心 12mm 球内"，
约占弧长的 0.023，即 `s ∈ [0.977, 1.0]`，0.986 落在该区间内部。因此 run #8 无法区分两种情况：

| 情况 | 说明 |
|---|---|
| 自由段的实际弯折 | 转角发生在带外的自由粒子上 |
| 刚性段与自由段接缝处的读数 | centerline 采样同时平均了受约束粒子与自由粒子，外接圆半径不代表任何一段的曲率 |

`bend_free` 是排除两端固定粒子带之后的最小弯曲半径（两端都排除：锚定端由 `fix_particles`
约束，自由端由 `fix_particles_to_link` 约束）。排除的采样点数由
`rope.anchor_radius` 除以实测采样间距得到，写在 trace 文件头。

### 13.2 插头俯仰

抬起后将插头绕水平轴旋转，使出线口（圆帽）转向下方，减小出线方向与绳垂挂方向的夹角。

#### 取值推导

设绳的出线方向与竖直方向夹角为 `a`，俯仰角为 `p`，则出线口处的转角为 `|(90° − p) − a|`。

`a` 的上界是锚点到插头的弦方向。用 §10 的三组路点数据（弧长 525mm）：

| braid length | 抬升高度 | 绷紧比 | 弦长 | 水平距离 | 弦与竖直方向夹角 |
|---|---|---|---|---|---|
| 2 | 219mm | 0.900 | 472mm | 419mm | 62° |
| 3 | 198mm | 0.900 | 472mm | 429mm | 65° |
| 5 | 183mm | 0.712 | 374mm | 326mm | 61° |

绳存在松弛，实际出线方向比弦更接近竖直，因此 `a ∈ [0°, ~62°]`。
`lift_test` 阶段松弛量最大，`a` 接近 0；`carry` / `cross` 路点绷紧比最高，`a` 接近上界。

| `carry_pitch_deg` | a=0°（lift_test） | a=62°（carry/cross） | 最大转角 | 对应最小 bend_r |
|---|---|---|---|---|
| 0（默认） | 90° | 28° | 90° | 5.3mm |
| 60 | 30° | 32° | 32° | 13.6mm |
| 90 | 0° | 62° | 62° | 7.3mm |

`p ≈ 59°` 使最大转角最小（约 31°）。对照运行取 60。
90° 在 `lift_test` 阶段最优，但在绷紧的 `carry` / `cross` 路点上转角回到 62°，
对应 bend_r 7.3mm，低于 10mm 的判据。

#### 实现

| 文件 | 改动 |
|---|---|
| `topogym/primitives/attachment.py` | 新增 `slerp()`；`RigidAttachment.ramp_to(quat, steps)` 与 `ramping()`，`sync()` 每次推进一个增量。未调用 `ramp_to` 时调用序列不变 |
| `topogym/primitives/physical_contact.py` | `_quat_mul` 公开为 `quat_mul`（旧名保留为别名）；新增 `quat_about_axis` |
| `topogym/primitives/pbd_handle_drag.py` | 新增可选回调 `on_lift`，在 `lift_test` 之前触发，默认 `None` |
| demo | `on_lift` 时开始旋转，`place_down` 段开始时旋转回原姿态；释放时若旋转未完成则输出 warning |
| task config | `pinch.carry_pitch_deg: 0.0`（默认关闭）、`pinch.carry_pitch_steps: 260` |

旋转由 attachment 执行，手腕姿态不变。依据：插头姿态由 `RigidAttachment.sync()` 每步写入，
夹爪为零预紧（`grasp_qpos_handle` == `column_radius`）；且 `RigidAttachment.offset` 为世界系
偏移，手腕旋转不会带动插头，改为手系会影响所有使用该类的任务。
影响：viewer 中插头在静止的指垫之间旋转，手指不跟随。指垫夹持的是回转体，绕指垫法线的
旋转在几何上成立，但与实际抓取的视觉表现不一致。视觉部分另行处理。

速率核对：60° / 260 次 sync，固定粒子带最外圈粒子（距转轴 12mm）每次位移 0.05mm，
低于搬运本身的 0.85mm/step。

`carry_pitch_steps` 的单位是 sync 调用数。`AttachmentManager` 在每个物理步前后各 sync 一次，
260 次对应 130 个物理步，即 `lift_test` 的时长（`move_steps // 2`）。

### 13.3 离线验证（无 GPU，已完成）

| 检查项 | 结果 |
|---|---|
| yaw-only / fixed-quat 两条既有路径的调用序列 | 与改动前一致 |
| ramp 的角度序列 | 单调；末态与目标的差 < 1e-9；超出 steps 后的 sync 不改变姿态 |
| 单次 sync 的粒子位移（r=12mm，90°/260 次） | 0.0725mm |
| 圆帽朝向 | 起始 -x（锚定端方向）；45° 与 60° 时分别低于水平面 45° 与 60°；90° 时为 -z |
| 各俯仰角的最大转角（a ∈ [0°, 62°]） | p=0 → 90°（bend_r 5.30mm）；p=60 → 32°（13.60mm）；p=90 → 62°（7.28mm） |
| `bend_free` 排除固定粒子带 | 带内人为折角使 `bend_r` 读到 12.5mm，`bend_free` 报无限大；自由段的折角两者一致 |
| `bend_r` 换算表与 `min_bend_radius` | 37°→11.82mm，90°→5.30mm，106°→4.70mm，120°→4.33mm |
| `_check_tightening` 对 run #8 数据的输出 | 与 §13.1 一致，不受本轮改动影响 |

倒数第二行与 §12.1 的实测值一致（正常状态 11.8mm、发散前 4.7mm）。

### 13.4 后续：两次 GPU 运行

```bash
export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

# 运行 1：carry_pitch_deg = 0（默认），仅含 §11 的 quat 修复
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --viewer --keep-open --max-moves 1 --verbose --strands 2 --trace

# 运行 2：将 carry_pitch_deg 改为 90，命令相同
```

运行 1 按 §12.6 判读。运行 2 相对运行 1，若握持时 `bend_r` 由 4~6mm 升至 ≥10mm 且未发生
发散，则 H9 成立、俯仰有效，将 `carry_pitch_deg: 60` 设为默认值。

每次运行的 trace 文件名不同，需要保留的复制到本目录。

### 13.5 运行 1 的结果：已解决

原始文件：本目录 `run09_2026-08-04_trace.log`（3535 行，seed=0 word=(1,1,1)，2 根绳，
`carry_pitch_deg` = 0，即只含 §11 的 quat 修复）。

| 观测 | run #8 | run #9 |
|---|---|---|
| `on_close`（step 670）处的单步位移 | 11.79mm | 0.012mm，与前后相邻步无差别 |
| grasp 与 carry_up 期间 `bend_r` | 4.6~4.9mm | 11.8~11.9mm |
| `bend_at` | 移至 0.986（接头） | 保持 0.343（绳中段交叉处） |
| `parked` | 1074 | 0 |
| EVENT | step 1058 | 无 |

step 670 与 §12.3 按 primitive 步数推算的 `on_close` 位置一致（120 open + 280 approach
+ 150 descend + 120 close = 670），trace 中的 `# step 670: fingers closed` 标记直接确认。

**`euler` 的行为已确定**：`gs.morphs.Mesh(euler=...)` 写进实体姿态，不烘焙进顶点。
推理：若烘焙进顶点，实体 quat 恒为单位四元数，`quat=entity_quat(...)` 就是空操作，
step 670 的单步位移不会消失。它消失了。

**H9 已否定。** 接头全程水平握持，而 `bend_r` 与 `bend_free` 在 grasp 和 carry_up 全程
都是 11.8mm，出线口没有紧弯。原推理的错误在于把绳当作从支点自由垂挂；实际绳长 526mm、
另一端锚定在 425mm 外，`max_taut_ratio` 把路点收在 0.90 以内，绳沿弦方向离开接头。
§13.2 的俯仰机制因此没有作用对象。

**`bend_free` 列生效。** place_down 末段 `bend_r` 降到 4.8mm（`bend_at` 0.971），
而 `bend_free` 是 9.6mm，且未发散。该读数来自刚性段与自由段的接缝，不是绳的实际曲率。

**`max_v` 为 nan 的原因已查明并修复。** trace 记下：

```
get_particles_vel() raised TypeError: can't convert cuda:0 device type tensor to numpy.
```

速度张量在 GPU 上，缺 `.detach().cpu()`。`probe_particles` 有这一步，速度路径是内联写的、
漏了。已抽出 `topogym/supervision/pbd_probe.py` 的 `probe_velocities()`，与
`probe_particles()` 同一处理，`RopeTrace` 改为调用它。

**看门狗有误报。** step 1631（`move1_place_down`）触发 WARN，`bend_r` 由 11.3 降到 7.9mm，
其后未发散。当前判据（低于 8mm 且相对 40 样本最大值下降超过 5%）在 place_down 阶段
偏敏感。仅写日志、不中断运行，暂不调整。

### 13.6 遗留：dead code

H9 否定后，§13.2 落地的这些没有作用对象：`RigidAttachment.ramp_to()` / `ramping()`、
`slerp()`、`PBDHandleDragPrimitive.on_lift`、`quat_about_axis()`、
demo 的 `pitch_nose_down` / `lay_plug_flat`、config 的 `carry_pitch_deg` /
`carry_pitch_steps`。`quat_mul` 是既有 `_quat_mul` 的公开化，与本机制无关，保留。
是否删除待定。
---

## 14. 其他候选方案（未实施）

- 改用 FEM + IPC（见 [`../../pbd_tabletop_friction_zh.md`](../../pbd_tabletop_friction_zh.md) §6）。
  IPC 用能量势垒保证不穿透，静摩擦在静止状态下有效，抓取有原生的
  `set_vertex_constraints(link=...)`，本文档中由自制固定粒子带引发的各项问题不再存在。
  需要 `pip install pyuipc`，Newton 求解通常慢一个量级，对批量生成数据构成风险，
  需先做性能测量。
- 下调 `rope.elastic.bending_compliance`（现 0.0030，来自 `prefabs.rope_pbd`）。
  该值是弯曲刚度的倒数，下调使转角分布到更长的绳段上，降低单点转角。
  影响绳的静止形状与 braid 沉降结果，可能改变交叉检测。
- 上调 `rope_pbd.pbd.max_bending_solver_iterations`（现 12）。
  迭代次数不足时约束残差累积，上调提高收敛程度，代价是每步耗时增加。
- 把固定粒子带改为分级约束：内核刚性，外圈只修改速度不写入位置，
  沿用 `TabletopParticleFriction` 的做法。属于新增机制。

---

## 15. 已排除的方向

| 方向 | 说明 |
|---|---|
| 绳与绳相互嵌入 4~5mm | H2，与求解发散无关，且与 H3 相互制约，当前取值是有意选择 |
| 未被抓取的绳的干扰 | 每轮 trace 均确认其 `jump` < 2.5mm/step |
| 夹爪与 PBD 粒子的接触 | 已关闭（`needs_coup=False`） |
| `StepProbe.uninstall()` 失效 | 曾因 `scene.step is self._wrapped_step` 恒为假而失效（Python 每次访问 `obj.method` 生成新的绑定方法对象），导致 trace 关闭后仍被调用。已修复 |
