# untangle_continuous 两根绳互相穿模 debug log

> 状态：**未解决**。
>
> `segment_length` 由 9mm 改到 4mm 后，两根绳静止时的中心线间距由 2.4mm 提升到 8.7mm，
> **静止状态下两管不再重叠**（§3.4）。但接触测试（§5）显示，机械臂拽住下面那根绳抬升时，
> 它仍然穿过了上面那根，穿透发生在 `move1_carry_up` 的 step 1177。
>
> 结论：**静止屏障成立，动态屏障不成立。** 屏障从 12mm 一路抵抗到约 7.4mm，
> 之后 7 步内被完全推穿。
>
> 相关：[`untangle_continuous_solver_divergence_zh.md`](untangle_continuous_solver_divergence_zh.md)
> §4 的 H2 记录了这个现象，此前标为"与求解发散无关"未处理；求解发散于 2026-08-04 解决后，
> 它成为主要问题。
>
> 原始 trace：本目录 `run10_2026-08-04_seg4mm_contact_test_trace.log`。
>
> 2026-08-05 的两段录像运行记录到第二种失效形态（两绳长时间并置），见 §9。

---

## 1. 现象

viewer 中夹爪抓住一根绳抬升时，那根绳穿过另一根到上面，两根绳的上下关系改变。

## 2. 机理

### 2.1 正确的静止间距是 12mm

PBD 的碰撞把粒子**中心**推开到 `particle_size`，而每根绳的表面粒子位于中心线外
一个半径处。所以两根叠放的绳，中心线应相距

```
2 × 绳半径 + particle_size = 2 × 4 + 4 = 12mm
```

（`topogym/supervision/untangle_continuous.py` 的 `crossing_lines` 注释记录了这一点。）

另外两个参考值：**8mm** = 2 × 绳半径，两管表面相切；低于 8mm 就是管体重叠。

### 2.2 屏障有洞

绳表面的粒子沿绳方向每 `segment_length` 一圈，环向每
`2 × 半径 × sin(π / radial_segments)` 一个。PBD 只在粒子中心距小于 `particle_size` = 4mm
时排斥。`segment_length` = 9mm 时，另一根绳的粒子落在两圈正中，离两侧各 4.5mm，
都在 4mm 之外，没有约束把它推出去。

### 2.3 三个后果

| 后果 | 说明 |
|---|---|
| 抓一根会带动另一根 | 重叠的两根绳永久处于接触状态，碰撞求解器把每次运动都传给对方。属于几何互锁，与摩擦系数无关 |
| over/under 判定不可靠 | 检测器按实测中心线 z 判上下（`untangle_continuous_verifier.py` 的 `count_crossings`），2.5mm 的高差发生在直径 8mm 的两根绳之间 |
| 穿过去只需爬 2.5mm | 而非 12mm |

---

## 3. 取值扫描

### 3.1 两个量相互制约

加密网格能堵洞，但会让绳自己的粒子对进入碰撞检测。规则（求解发散文档 §1.2 第 2 步记录）：
静止距离 ≤ `particle_size` 的同体粒子对被永久排除，其余参与检测；绳弯曲时内侧纤维的
轴向间距按 `(R − r)/R` 收缩，跌破 `particle_size` 就产生本不应存在的排斥。

设 `p` = `particle_size` = 4mm、`r` = 半径 = 4mm，一对粒子的静止距离分解为轴向分量 `d`
与环向分量 `w`：

- `√(d² + w²) ≤ p`：永久排除
- `w ≥ p`：参与检测，但收缩下限就是 `w`，永不跌破阈值
- 其余：触发曲率半径 `R < d·r / (d − √(p² − w²))`

### 3.2 推算的候选取值

| 方案 | radial_segments | segment_length | 环向间距 | 屏障漏隙 | 误触发曲率半径 |
|---|---|---|---|---|---|
| A（原值） | 8 | 9mm | 3.06mm | 9mm | 7.2mm |
| B | 8 | 4mm | 3.06mm | 4mm | 11.2mm |
| C | 6 | 4mm | 4.00mm | 4mm | 8.0mm |
| D | 6 | 5mm | 4.00mm | 5mm | 20.0mm |

按推算，工作曲率半径 11.8mm 时 B 的裕度只有 0.6mm、C 的裕度 3.8mm，所以 C 是首选。
**实测结果相反：B 有效，C 无效。** 推算依据的排除规则来自记录而非 Genesis 源码，
且 `tube_morph` 用 `force_retet=True` 加 `maxvolume`，tetgen 可能在表面插入额外顶点，
真实粒子间距未必等于 `segment_length`。

### 3.3 跑法

```bash
cd /projects/bfuo/jlyu3/topogym
source .venv-gs110/bin/activate
export LD_LIBRARY_PATH=/usr/lib/wsl/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
bash bash_scripts/tests/rope_contact_sweep.sh
```

每格只做生成加沉降（`untangle_continuous_inspect_demo`，不带机械臂运动）。
输出四个字段：`gap`（交叉处静止中心线间距，目标 12mm）、`overlap`（互嵌深度，目标 0）、
`self_viol`（出现 `SELF-COLLISION ALWAYS VIOLATED` 的绳数）、
`gt`（检测器与 braid ground truth 是否一致）。

### 3.4 扫描结果（2026-08-04）

seed 0~3，2 根绳。gap 取各 seed 的范围。

| radial_segments | segment_length | gap | overlap | self_viol | gt |
|---|---|---|---|---|---|
| 8 | **4mm** | **8.4 ~ 8.7mm** | 3.3 ~ 3.6mm | 2 | True |
| 8 | 5mm | 0.3 ~ 0.7mm | 11.3 ~ 11.7mm | 2 | 部分 False |
| 6 | 4mm | 0.2 ~ 1.1mm | 10.9 ~ 11.8mm | 2 | 部分 False |
| 6 | 5mm | 0.1 ~ 1.0mm | 11.0 ~ 11.9mm | 2 | True |
| 6 | 6mm | 0.1 ~ 0.2mm | 11.8 ~ 11.9mm | 2 | True |
| 6 | 9mm | 2.0 ~ 2.4mm | 9.6 ~ 10.0mm | 2 | True |
| 8 | 9mm（原值） | 2.4mm（物理 demo 实测） | 9.6mm | 2 | True |

**n=8 / s=4mm 是一个尖锐的最优点**，其余取值都不比原值好。这与 §3.2 的推算不一致
（推算首选 C = n6/s4mm，实测该格 0.2~1.1mm）。

按推算的两个失效模式解释三个区域：

| 区域 | 失效模式 |
|---|---|
| s = 5、6mm | 轴向粒子对参与检测，且触发曲率半径（20mm、12mm）高于绳的工作曲率，绳在正常弯曲下持续自己推自己 |
| s = 9mm | 轴向对触发半径 7.2mm 低于工作曲率，不误触发；但屏障漏隙 9mm 大于排斥半径 4mm |
| n=8 / s = 4mm | 轴向静止距离正好等于 `particle_size`，被排除规则挡在检测之外；两个方向的漏隙（4mm、3.06mm）都在排斥半径以内 |

n=6 / s=4mm 未能跟上，**原因未查明**。它的环向间距正好 4.000mm，卡在排除阈值上，
而 n=8 的 3.06mm 有余量；两者的差别只有这一处，但该差别为何造成一个量级的结果差异
尚未验证。

`self_viol` 在全部格子中均为 2，即两根绳的粒子间距在所有取值下都被判为违反碰撞约束。
这一列没有区分度，不能用来选参数。

---

## 4. 接触测试的设计

拽**下面**那根绳。这不是一个解题动作——拖动下面的绳不能解开交叉——它是接触测试：
被拽的绳无论被拖多远，都不允许穿过压在它上面的那根。

```bash
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --viewer --keep-open --verbose \
  --seed 0 --grasp-strand 1 --max-moves 1 \
  --segment-length 0.004 --trace
```

seed 0 的 braid 是 s0（红）在上、s1（绿）在下，`--grasp-strand 1` 抓绿。

判读用 trace 的三列：

| 列 | 通过判据 |
|---|---|
| `over_z` | 被拽那根全程保持同号；符号翻转即穿透 |
| `pair_gap` | 全程 ≥ 8mm（两管不重叠） |
| `bend_free` | 不出现持续下降 |

`over_z` 是该绳在两根绳最接近处高出另一根多少，带符号。它的**符号**是可靠的；
数值可能在最接近点沿绳移动时跳变，不要按连续量读。

---

## 5. 接触测试结果（2026-08-04，未通过）

原始文件：本目录 `run10_2026-08-04_seg4mm_contact_test_trace.log`。
seed 0，word=(1,)，2 根绳，`segment_length` = 4mm，`radial_segments` = 8，抓 s1（绿，下方）。

初始状态正常：检测器与 braid ground truth 一致，s0 over s1，z_gap 8.7mm，与 §3.4 的扫描一致。

### 5.1 时间线（s1，被拽的绿绳）

| step | phase | pair_gap | over_z | 说明 |
|---|---|---|---|---|
| 1 ~ 1120 | grasp → carry_up | 9.1 ~ 9.4mm | −8.6mm | 绿在红下方，两管不重叠 |
| 1150 ~ 1169 | carry_up | 9.39 → 7.39mm | −8.85 → −7.16mm | 间距被逐步压缩，约 step 1160 跌破 8mm |
| 1170 ~ 1176 | carry_up | 7.07 → 1.72mm | −6.80 → −0.30mm | 7 步内塌陷；`jump` 由 0.47 升到 2.0mm/step |
| **1177** | carry_up | 2.06mm | **+1.53mm** | **符号翻转，绿已在红之上** |
| 1178 ~ 1184 | carry_up | 3.49 → 9.62mm | +3.25 → +9.51mm | 在另一侧分开 |

`bend_free` 全程保持 5.4 ~ 5.7mm，无持续下降；`parked` 恒为 0。求解发散的特征均未出现，
本次属于接触失效。

### 5.2 读数

- 屏障从 12mm 抵抗到约 **7.4mm**，此后 7 步内被完全推穿。7.4mm 已低于 8mm，
  即在屏障失效前两管已经重叠了 0.6mm。
- 穿透过程持续 26 步（1150 → 1176），不是单步穿隧。
- 静止时屏障能维持 8.7 ~ 9.4mm，说明 §3.4 的取值改进是真实的，只是不足以承受抬升。

### 5.3 原因（2026-08-05 读 Genesis 源码后）

源码位置：`.venv-gs110/lib/python3.11/site-packages/genesis/engine/solvers/pbd_solver.py`、
`engine/couplers/legacy_coupler.py`。

#### 从源码直接读到的

**接触每个子步只解一次，且没有迭代次数参数。** `substep_pre_coupling` 的顺序是：

```
store_initial_pos -> apply_external_force
  -> solve_stretch   (max_stretch_solver_iterations   = 16)
  -> solve_bending   (max_bending_solver_iterations   = 12)
  -> solve_volume    (max_volume_solver_iterations    =  6)
  -> reorder_particles（空间哈希）
  -> solve_density / solve_viscosity
  -> solve_collision （无迭代循环）
  -> compute_velocity
```

`_kernel_solve_stretch` / `bending` / `volume` / `density` / `viscosity` 都用
`for _ in qd.static(range(self._max_*_solver_iterations))` 包着，`_kernel_solve_collision`
没有。`PBDOptions` 也没有暴露接触迭代数的字段。

本任务 `sim.substeps` = 4，所以每个 `scene.step`：接触求解 4 次，拉伸 64 次，
弯曲 48 次，体积 24 次。**单个子步内是 34 次形状约束迭代对 1 次接触求解，且接触在最后。**

**接触是 Jacobi 式。** 所有粒子对的修正累加进 `dpos`，全部算完后统一加到 `pos`。

**单个粒子对的修正一次到位。** `dpos += wi/(wi+wj) * (target_dist - cur_dist) * n`，
直接补到 `target_dist`，不是每次推一点。

**排除规则确认，H1 的记录正确：**

```python
if cur_dist < target_dist and rest_dist > target_dist:
```

`target_dist = particle_size`，`rest_dist` 由 `pos_rest`（出生位置）算。

**邻居搜索不是限制。** `hash_grid_cell_size = 1.25 × particle_size` = 5mm，
3×3×3 的 stencil 覆盖范围大于 `particle_size`。

**两端的约束方式不同：**

| 端 | 机制 | 接触能否推动它 |
|---|---|---|
| 锚定端 | `fix_particles` -> `_kernel_fix_particles` 设 `free = False` | 否。`wi = free/mass = 0`，修正权重为 0 |
| 自由端（接头） | `fix_particles_to_link` -> 耦合器的速度控制，**不设** `free = False` | 能 |

**自由端是速度控制，不是位置写入：**

```python
corrective_vel = (target_world_pos - particle_pos) * clamped_inv_dt
particles_reordered[i_rp, i_env].vel = corrective_vel + target_world_vel
```

`clamped_inv_dt = min(1/dt, 50)` = 50。该 kernel 在 PBD 求解**之后**执行，
**覆写**粒子速度，PBD 自己算出的速度（含接触修正的贡献）被丢弃。

#### 由此推出的机制（推断，非源码直述）

接触在一个子步内把两根绳分开的位置修正会保留，但被拖动那一端的速度随后被耦合器覆写为
"指向目标位置、增益 50/s"。下一个子步，形状约束先跑 34 次把压力沿绳传递，接触最后才有
1 次机会。两根绳被持续压紧时，这个比例决定了接触守不住。

#### 结论

穿模不属于异常，也不是绝对不可避免。它是该求解器把接触作为"每子步一次的收尾投影"这一
设计的直接后果，而本任务的场景是它的不利情形：一根绳被外部以速度控制拖动，另一根必须
完全让开。

### 5.4 可调的量

以下三项都在配置层，方向由 §5.3 的结构推出，**均未验证**：

| 量 | 现值 | 方向 | 代价 |
|---|---|---|---|
| `sim.substeps`（`configs/env_configs/world_tabletop_v1.yaml`） | 4 | 提高。每单位拖动位移对应更多次接触求解 | 每步耗时按比例增加 |
| `rope.pbd.max_stretch_solver_iterations` | 16 | 降低。形状约束撤销接触修正的能力下降 | 绳更容易被拉长 |
| `pinch.move_steps` | 260 | 提高。每步的拖动位移下降 | 单次搬运的墙钟时间增加 |

不可调的：接触迭代次数没有暴露；`CLAMPED_INV_DT` 是 `legacy_coupler.py` 的模块级常量 50。

要保证不穿透需要带非穿透势垒的求解器（FEM + IPC，见 untangle_continuous_solver_divergence_zh.md §14）。PBD 的位置投影不提供该保证。


---

## 6. 已落地的诊断

| 改动 | 文件 |
|---|---|
| trace 新增 `pair_gap(mm)` 列：每步记录该绳与最近的另一根绳之间中心线的最小距离 | `topogym/supervision/rope_trace.py` |
| trace 新增 `over_z(mm)` 列：带符号的高度差，符号即上下关系 | 同上 |
| trace header 记录 12mm / 8mm 两个参考值、centerline 采样数与间距 | 同上 |
| trace header 记录检测器与 braid ground truth 的比对结果、每个 crossing 的 over/under 与 z_gap | `demos/entangle/untangle_continuous_physical_pinch_demo.py` |
| z_gap 低于静止间距一半时输出提示：over/under 的判定裕度不足 | 同上 |
| `--grasp-strand`：强制抓指定的绳，用于接触测试 | 同上 + `topogym/planning/untangle_continuous_planner.py` |
| `--segment-length` 覆盖（两个 demo） | 同上 + `demos/entangle/untangle_continuous_inspect_demo.py` |
| 扫描脚本 | `bash_scripts/tests/rope_contact_sweep.sh` |

`pair_gap` 与 `over_z` 都用点到线段距离计算。centerline 采样间距在 5.5 ~ 7.5mm 量级
（随 `braid.length` 与 `segment_length` 变化，trace header 记录实际值），
而关心的距离在 8 ~ 12mm 量级，最近点通常落在采样点之间，用最近采样点会高估。

---

## 7. 顺带发现：`min_separation` 的测量方式会高估

`untangle_continuous_verifier.py` 的 `min_inter_strand_distance` 用的是**最近采样点**距离，
不是点到线段距离。离线核对（采样间距 7.5mm）：

| 真实间距 | 最近采样点测得 | 高估 |
|---|---|---|
| 12.0mm | 12.57mm | +4.8% |
| 2.5mm | 4.51mm | +80% |

越近高估越多，而近的时候正是它要起作用的时候。这个量是成功判据
（`success.separation_threshold` = 16mm）的输入，所以判据偏松。

**未改动**：改了会让 `min_separation` 变小、判据变严，属于评测口径变化，需要单独决定。

---

## 8. 顺带修掉的两处

| 问题 | 说明 |
|---|---|
| `before_release` 签名不匹配 | `PBDHandleDragPrimitive` 以 `before_release(pre_release_pos, final_target)` 调用并读返回值，demo 的 `release_grasp_attachment()` 不收参数，每次运行都在第一个 move 的最后一步抛 `TypeError`。这也是此前 trace 里从未出现"attachment released"那一行的原因。2026-08-04 修 |
| `--difficulty` 的 easy 档与配置不一致 | 配置 `braid.length: 1`，而 `_DIFFICULTY_LENGTH["easy"]` 是 2、`["default"]` 是 3。传 `--difficulty default` 会把一处交叉的配置覆盖成三处。easy 改为 1，配置 `task.difficulty` 改为 `easy`。2026-08-04 修 |

---

## 9. 两段录像运行的 trace 读数（2026-08-05）

### 9.1 运行与文件对应

两次运行的参数只差 `--grasp-strand`：seed 0、word=(1,)、2 根绳、`segment_length` = 4mm、
`radial_segments` = 8、`substeps` = 4、`rope_static_friction` = 0.05、`rope_kinetic_friction` = 0.02。
初始状态两次一致：检测器与 braid ground truth 相符，s0（红）over s1（绿），z_gap 8.7mm。

| 运行 | `--grasp-strand` | 被抓的绳 | 录像 | 原始 trace |
|---|---|---|---|---|
| A | 1 | s1（绿，下方） | `runs/untangle_fail_pull_under_strand.mp4` | 本目录 `run11_2026-08-05_grasp_under_strand_trace.log` |
| B | 0 | s0（红，上方） | `runs/untangle_solve_pull_over_strand.mp4` | 本目录 `run12_2026-08-05_grasp_over_strand_trace.log` |

四个阶段的步区间两次相同：`move1_grasp` 1~920、`move1_carry_up` 921~1200、
`move1_cross_over` 1201~1480、`move1_place_down` 1481~2060。

### 9.2 运行 A：穿越

| step | phase | pair_gap | s1 的 over_z | 说明 |
|---|---|---|---|---|
| 1 ~ 920 | grasp | 8.54 ~ 9.16mm | −8.73 ~ −8.33mm | 920 步中无一步低于 8mm |
| 1160 | carry_up | 7.98mm | −7.04mm | 首次跌破 8mm |
| 1170 | carry_up | 6.75mm | −6.45mm | |
| 1174 | carry_up | 3.77mm | −3.17mm | |
| 1176 | carry_up | 1.58mm | +0.48mm | 符号改变，绿在红之上 |
| 1184 | carry_up | 9.59mm | +9.48mm | 在另一侧分开 |

与 §5 记录的 run10 对照：run10 同样在 step 1176 变号，该步 gap 1.72mm（本次 1.58mm）。
两次运行相隔一天、run10 无录像，塌陷步号相同。

`move1_place_down` 段 s0 另有 14 次变号，对应 pair_gap 10 ~ 40mm，见 §9.6。

### 9.3 运行 B：长时间并置

| step | phase | pair_gap | s0 的 over_z | 每步 gap 变化 |
|---|---|---|---|---|
| 850 | grasp | 8.77mm | +8.68mm | 静止值 |
| 862 ~ 869 | grasp | 8.40 → 7.43mm | +8.37 → +7.44mm | 0.13mm/step |
| 870 ~ 877 | grasp | 7.05 → 4.22mm | +7.07 → +4.17mm | 0.40mm/step |
| 878 ~ 894 | grasp | 4.04 → 3.53mm | +3.99 → +3.45mm | 0.02 ~ 0.04mm/step |
| 895 ~ 899 | grasp | 3.28 → 1.60mm | +3.21 → +0.10mm | 0.42mm/step |
| 900 | grasp | 1.60mm | −0.42mm | 符号第一次改变 |
| 900 ~ 1113 | grasp → carry_up | 1.60 ~ 2.46mm（均值 1.77mm） | −1.77 ~ +2.34mm | 214 步 |
| 1110 | carry_up | 1.77mm | +0.22mm | 符号第二次改变 |
| 1114 ~ 1120 | carry_up | 3.08 → 10.34mm | +3.13 → +9.37mm | 分开，红在上 |

pair_gap 低于 4mm 持续 233 步（879 ~ 1115），其中低于 2.5mm 持续 217 步。
均值 1.77mm 对应两根直径 8mm 的管重叠 6.2mm。

塌陷起始于 `move1_grasp` 段的第 862 步，此时机械臂尚未抬升。

### 9.4 两种形态

| 形态 | 出现 | pair_gap 轨迹 | over_z 符号 |
|---|---|---|---|
| 穿越 | 运行 A | 单调下降到 1.58mm，随后在另一侧恢复到 9.6mm | 改变一次并保持 |
| 并置 | 运行 B | 下降到 1.6 ~ 1.8mm 后维持 214 步，随后回到原侧 10.3mm | 在 ±2mm 区间内改变两次 |

录像 B 中"绿绳到红绳上方、随后红绳回到绿绳上方"对应并置区间内的两次变号。
该区间两根管的中心线相距 1.6 ~ 2.5mm，over_z 的量级为 0.1 ~ 2mm，落在 §9.6 给出的不可读区间。

### 9.5 与摩擦系数的关系

`_func_solve_collision`（`.venv-gs110/lib/python3.11/site-packages/genesis/engine/solvers/pbd_solver.py`）
的两项修正：

| 修正 | 表达式 | 含摩擦系数 |
|---|---|---|
| 法向 | `wi/(wi+wj) · (target_dist − cur_dist) · n` | 否 |
| 切向 | `dpos = −(dv − n·(n·dv))`，上限 `mu_s·d`（静）或按 `mu_k·d/‖dpos‖` 缩放（动） | 是 |

`d = target_dist − cur_dist` 为侵入深度，取值范围 0 ~ `particle_size` = 4mm。
两根绳刚接触时 `d` = 0，摩擦项上限同为 0。

两段 trace 中减小的量是 pair_gap，即两条中心线之间的距离，方向为法向。
`rope_static_friction` 与 `rope_kinetic_friction` 的取值不进入法向修正的表达式。

提高绳↔绳摩擦这一方向另有三项约束：

| 约束 | 依据 |
|---|---|
| `_func_solve_collision` 对同一根绳内部的粒子对同样生效（判定只看 `rest_dist > target_dist`），提高摩擦会在绳内增加切向修正，与拉伸、弯曲约束叠加 | §3.1、§3.2 记录的同体粒子对判定规则 |
| prefab 原值 0.35/0.25 会出现一根绳移动时带动被压住的另一根 | `configs/task_configs/untangle_continuous_topogym_tabletop_v1.yaml` 第 216 行起的注释；离散版 untangle 同值同理由 |
| 2026-07-29 曾抬到 0.18/0.12，结论为误诊并回退，当时的现象是重现了"带动另一根" | 同上，该文件的留档段 |

§2.3 已记录"抓一根会带动另一根"属于几何互锁，与摩擦系数无关。

### 9.6 over_z 的可读区间

`move1_place_down` 段 s0 一列两次运行合计出现 23 次符号改变（运行 A 14 次、运行 B 9 次），
对应的 pair_gap 为 10.8 ~ 41.3mm，`|over_z|` 为 0.01 ~ 5.92mm。该段两绳已分开，最近点位置在中心线采样点之间移动
（采样间距 5.5mm，见 §6）。

据此修正 §4 的判读方式：

| pair_gap 区间 | over_z 符号 |
|---|---|
| < 4mm | 两管重叠，符号由 0.1 ~ 2mm 的差值决定 |
| 6 ~ 15mm | 可读 |
| > 20mm | 最近点位置不稳定，符号随采样点跳变 |

### 9.7 塌陷速率

运行 B 的平台段（878 ~ 894 步）pair_gap 每步下降 0.02 ~ 0.04mm，折合每子步
0.005 ~ 0.01mm，而 `particle_size` = 4mm。重叠在该速率下仍单调增加。

由此对 §5.4 的三项可调量补充一条推断（**未验证**）：

| 量 | 对单子步内"34 次形状约束迭代 : 1 次接触求解"这一比例的作用 |
|---|---|
| `sim.substeps` | 不改变。接触求解次数与形状约束迭代次数同比例增加，只降低每子步位移 |
| `pinch.move_steps` | 不改变。只降低每步位移 |
| `max_stretch_solver_iterations` | 直接改变该比例 |

若重叠的增加与每步位移量无关，前两项能提供的改善幅度有限。三项均未做对照实验。

### 9.8 两处未查明的观测

**平台位置与 `particle_size` 相同。** 运行 B 在 pair_gap ≈ 4.0mm 停留 17 步
（878 ~ 894）。`tube_morph` 用 `force_retet=True` 配 `maxvolume`，管内存在内部粒子；
pair_gap = 4mm 时两条中心线附近的内部粒子进入 `cur_dist < particle_size` 的判定分支。
该对应关系未验证，确认方式为统计该时刻进入碰撞分支的粒子对位置分布。

**并置状态维持 214 步。** pair_gap 稳定在 1.6 ~ 1.8mm，构成第二个平衡位置。
一种可能是重叠达到该深度后，一根绳的粒子被另一根绳的粒子在各方向包围，
逐对修正在 Jacobi 累加后净分离量下降。未验证，确认方式为统计该时刻各粒子对修正向量的方向分布。

### 9.9 录像路径与步进的关系

`recording_session`（`topogym/utils/recording.py`）在 `scene.step` 外包一层取帧，
不改变步进顺序与参数。

三次同参数运行（seed 0、`--grasp-strand 1`、`segment_length` = 4mm）在同一 step 1176 变号：

| 运行 | 日期 | 渲染方式 | 该步 pair_gap | trace |
|---|---|---|---|---|
| run10 | 2026-08-04 | 无窗口、无录像 | 1.72mm | 本目录 `run10_2026-08-04_seg4mm_contact_test_trace.log` |
| 运行 A | 2026-08-05 | 无窗口、录像 | 1.58mm | 本目录 `run11_2026-08-05_grasp_under_strand_trace.log` |
| run13 | 2026-08-06 | `--viewer` | 2.13mm | 本目录 `run13_2026-08-06_viewer_grasp_under_strand_trace.log` |

viewer 运行同样发生穿模，穿模步号与另外两次相同。此前"viewer 中不出现穿模"的印象不成立。

`--record-every-n-steps 4` 配 `--record-fps 30`：运行 A 的塌陷区间 1150 ~ 1184 共 34 步，
在录像中为 9 帧、约 0.3 秒。

比较 viewer 与录像时，两者用同一组参数各跑一次并比对 trace：

```bash
# 录像
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --verbose --seed 0 --grasp-strand 0 --segment-length 0.004 \
  --record-video runs/untangle_solve_pull_over_strand.mp4 \
  --record-camera oblique --record-res 960 720 \
  --record-every-n-steps 4 --record-fps 30 --trace

# viewer，同参数
python -m demos.entangle.untangle_continuous_physical_pinch_demo \
  --viewer --verbose --seed 0 --grasp-strand 0 --segment-length 0.004 --trace
```

判读依据为 trace 的 `pair_gap` 列，不依赖画面。

### 9.10 日志措辞

`demos/entangle/untangle_continuous_physical_pinch_demo.py` 第 388 行的
`(over s{command.under_strand}, ...)` 中 "over" 为固定文本。用 `--grasp-strand` 指定下方那根时，
该行（运行 A：`grasping s1 (over s0, ...)`）与同一 header 的
`measured crossings: s0 over s1` 不一致。run10 的同一行写作 `over s1`，
`topogym/planning/untangle_continuous_planner.py` 第 261 行的注释记录了那次修改。未改动。
