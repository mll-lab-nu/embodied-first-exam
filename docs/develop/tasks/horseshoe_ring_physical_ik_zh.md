# Horseshoe Ring：重力下的双臂 IK 与验收

此入口针对 `tutorial_solvable_v3` 的精确模板、2 倍尺度和 ALOHA 配置。
其他外观变体需要重新规划和物理执行，不能继承本实例的成功结论。

## 已通过的连续执行（2026-09-18）

`runs/environment-solvability/horseshoe_ring/physical_replan_20260918/continuous03/`
从原始预抓持初态连续完成折合、交接、抓环、取出、松爪和自由落桌。
仿真时间 113.65 秒，2 ms 步长、4 子步，共 56,825 次物理步进。
独立验收 26 项全部通过；圆环初始自由下落 55.01 mm，最终与装配的包围盒间距为 300.33 mm。
最大谜题接触穿透 0.397 mm，最大关节跟踪误差 0.0101 rad；
圆环最终仅接触桌面，线速度约 0.0052 mm/s。

这份通过记录包含辅助抓持，不能解释为纯摩擦解法；下文列出具体边界。
后续同代码 2 ms / 1 ms 完整复验已通过；此前未完成的尝试作为历史记录保留。

[五路完整视频目录](../../../demos/horseshoe_ring/) ·
[同步播放与验收](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1/index.html)。
每路为同一次成功执行的完整 113.7 秒视频；视频目录只放 MP4，其他材料保存在配套目录。

## 半时间步复验通过（2026-09-18）

使用同一版执行代码、原始初态、几何与控制参数，分别独立重规划和执行：

| 运行 | 步长 | 仿真时长 | 物理步数 | 最大谜题穿透 | 最终分离间距 |
| --- | --- | --- | --- | --- | --- |
| 新对照 `timestep_baseline01` | 2 ms | 119.30 s | 59,650 | 0.505 mm | 330.49 mm |
| 半步长 `continuous_halfdt06` | 1 ms | 126.95 s | 126,950 | 0.428 mm | 491.44 mm |

两次各自通过 26 项独立执行检查，并通过 9 项对照检查；123 个实际生成的模型文件哈希一致。
两次机器人自碰撞和机器人与桌面的最大穿透均为 0，圆环最终解除辅助抓持、仅接触桌面并静置。
终态圆环高度差为 **0.0000102 mm**，小于 0.5 mm 验收门槛。
这说明此基础实例在两种步长下都能完成任务，不是对任意扰动、所有变体或固定轨迹数值收敛的证明。

[对照报告与两次完整状态记录](../../../runs/demo_metadata/horseshoe_ring/2026-09-18_timestep_validation_v1/index.html)。
已有五路视频来自此前的 113.65 秒成功执行；本次两次新运行作为独立复验证据关联到该 demo。

## 动作与约束

1. 从声明的双手预抓持初态开始，用关节位置控制执行翻转和折合。
   圆环和两只链环均为受重力、参与碰撞的自由刚体。
2. 把两只马蹄转成水平叠放。释放上方马蹄，让下方马蹄和左指垫实际承载；
   检查接触载荷、上下位置和法向对齐，再撤回右手。
3. 右手换成共同夹持两只马蹄。只有存在有载荷的
   `右指垫 → 马蹄 → 马蹄 → 另一右指垫` 路径时，才启用新的辅助抓持。
   仅仅“另一只马蹄碰到了已夹住的马蹄”不足以通过。
4. 左手保持窄指间距，通过避障关节路径撤离，再张开。
   根据圆环实际下垂位置和世界重力方向选择抓点，跟踪圆环完成接近和闭合。
   两个指垫都有承载接触后才能辅助抓持圆环。
   若圆环停在单侧指垫边缘，先停止跟随并静置，再按 1 mm 步长沿指垫深度方向微调，
   最多 6 mm；所有微调仍经过真实关节控制、重力接触和运行时碰撞检查。
   双侧承载条件始终不满足时，此次运行判失败。
5. 规划圆环相对马蹄的平移、平面转向和自身相位，同时检查两只完整夹爪的实体几何。
   双臂联合 IK 分担相对运动，并优化前臂之间和桌面的距离。
   避障优化后再校正抓持相对位姿，随后重新做碰撞检查。
   受载初态偏离旧几何里程碑时，在其各坐标轴 ±4 mm 内寻找无碰撞的新目标，
   同时调整圆环相位；实际选择的偏移保存在计划中。
   失败的候选路径重新规划，不放宽检查、不写入谜题位姿。
6. 圆环取出后转为水平，移到桌面上方，解除圆环辅助抓持并张爪。
   圆环在重力下落桌，继续仿真静置。两只马蹄末态仍由右手保持。

初始化之后的动作只有关节目标、抓持约束切换和 `scene.step()`；
不逐帧设置机器人关节状态或谜题位姿。抓持约束是明确记录的辅助机制，
不等于纯摩擦抓取，也没有验证从桌面自主拾取两只马蹄。

## 实现与证据

- `physical_motion.py`：动力学推进、接触门槛、实测状态和失败保护。
- `physical_plan.py`：水平叠放、交接、空手避障和跟踪抓环。
- `physical_extraction.py`：带夹爪的相对路径搜索、双臂 IK、桌面约束及精确抓持位姿校正。
- `physical_place.py`：附带圆环的避障落桌动作、释放与静置。
- `physical_demo.py`：一次不间断的完整执行入口。
- `verify_physical.py`：独立复核初态、重力下落、抓持接触证据、链眼连接和自由落桌终态。
- `render_physical.py` / `archive_physical.py`：从已通过验收的同一次执行输出和保留同步 MP4。

`assets/tasks/horseshoe_ring/tutorial_solvable_v3/physical_seed.json` 仅保存初态、
折合关节种子和原几何解法的取环里程碑；它不是物理成功证书。
执行器检查模板哈希和尺度，不接受换了尺寸却沿用旧种子的做法。

每次执行使用新目录。`physical_states.jsonl` 保存 20 Hz 的实测关节、目标关节、
刚体位姿、速度、接触力、链眼连接数及实际辅助约束。
`planned_extraction.json` 是取环 IK 计划，不能代替实测轨迹。
检查点试验必须标记 `checkpoint_start=true`，即使分段取环成功也不计为完整任务成功。

最终成功必须同时满足：圆环与装配包围盒分离超过 20 mm、圆环不再有辅助约束、
圆环承载接触桌面、线速度小于 10 mm/s、角速度小于 0.2 rad/s。
运行中还检查谜题穿透、机器人自碰撞、机器人与桌面碰撞、持续关节跟踪失败和链眼连接丢失。
上述检查是本仿真和离散步长下的执行证据，不是任意扰动或任意尺寸下的可解性证明。

半时间步对照另外要求两次执行的代码、初态种子、模板、实际生成的网格与机器人模型、
控制和仿真参数一致，仅时间步及输出路径不同；一次使用 2 ms，另一次使用 1 ms，均保持 4 子步。
两次必须分别从原始初态完整执行并通过独立验收，圆环落桌后的高度差小于 0.5 mm。
各运行允许按实测状态独立重新规划，因此这验证的是任务在两种步长下完成，
不是固定关节轨迹的数值收敛。`verify_physical.compare_runs` 会核对上述一致性。

## 运行

在仓库根目录、已有 `.venv-gs121-nyx` 环境中执行；无需启动网页服务器。
以下输出目录必须尚不存在。

```bash
# 原始初态出发的完整物理执行
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.physical_demo \
  --output runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN

# 半时间步独立重规划、完整执行
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.physical_demo --dt 0.001 \
  --output runs/environment-solvability/horseshoe_ring/MY_HALF_STEP

PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.verify_physical \
  runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN \
  --half-step runs/environment-solvability/horseshoe_ring/MY_HALF_STEP \
  --output runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN/verification.json

# 四路 ALOHA 加近景；所有视角来自上面同一次已通过的完整执行
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.render_physical \
  runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN \
  --output runs/environment_bootstrap/horseshoe_ring/MY_PHYSICAL_RECORDING --fps 10

PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.archive_physical \
  runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN \
  runs/environment_bootstrap/horseshoe_ring/MY_PHYSICAL_RECORDING \
  runs/environment-solvability/horseshoe_ring/MY_HALF_STEP \
  --run-id YYYY-MM-DD_MY_PHYSICAL_RUN
```

归档的第三个位置参数仅用于已通过的完整半步长执行；仅归档已验收基础运行时省略它。
未完成的额外复验可通过 `--incomplete-half-step <目录>` 单独保留，不能计入时间步验证成功。

若已有完整视频，后续同代码复验通过后使用 `archive_timestep` 保存两次新运行并更新原 demo 的验收链接：

```bash
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.archive_timestep \
  runs/environment-solvability/horseshoe_ring/MY_PHYSICS_RUN \
  runs/environment-solvability/horseshoe_ring/MY_HALF_STEP \
  --demo runs/demo_metadata/horseshoe_ring/2026-09-18_gravity_replanned_v1 \
  --run-id YYYY-MM-DD_MY_TIMESTEP_CHECK
```

此入口独立保存复验运行、原验收历史和新的对照报告，原 MP4 的来源与内容保持不变。

视频不加 UI；按 10 Hz 抽取原 20 Hz 状态，不对物体或关节插值。
固定相机保留 ALOHA 上游安装位置，根据整条实测轨迹的包围盒扩展视场；
腕部相机保持已有绑定。实际内参、每帧位姿、源帧索引和文件哈希随录像保存。
镜头覆盖检查不能保证没有遮挡，仍需要查看关键帧。

按用户最新要求，基础版归档视频位于 `demos/horseshoe_ring/<camera>/`，
包含四路 ALOHA 视角和 `detail` 近景，各目录一份完整 MP4。
页面与完整物理证据位于 `runs/demo_metadata/horseshoe_ring/<run-id>/`。
旧运动学视频保留为独立历史对照，不覆盖最后一份已验证副本。
