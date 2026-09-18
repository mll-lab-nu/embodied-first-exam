# 绳穿三环：基础场景

目标参考为 [Wang 的三环演示](https://qinengwang-aiden.github.io/demos/constraint_demos/?demo=threading)。
已提供离线资产、共享 ALOHA 双臂实验室与原生子步物理审计入口。
公开动作参考与接触触发的机器人执行入口已接入。当前时间步对照未通过，
机器人抓取验收和完整 demo 尚未启动。

## 几何与坐标

原绳长 1.1 m，半径 4 mm，共 80 个相连胶囊、81 个有序节点。
初态为桌面上的 U 形，两端未抓持，三个环的初始穿越计数均为零。
节点直接取自公开首帧，保留从 `v4_rope_link_0` 到第 79 段远端的材料方向。
目标材料顺序为 `R1- / R2+ / R3+`；`route_crossings` 仅返回有向几何穿越观测，
不将瞬时计数作为连续无穿透或任务成功的证书。

| 环 | 原参考中心（m） | 有向法线 | 颜色 |
| --- | --- | --- | --- |
| R1 | (0.075, -0.019, 0.331) | (1, 0, 0) | 青 |
| R2 | (0.010, 0.170, 0.310) | (0.8, 0.6, 0) | 绿 |
| R3 | (0.090, 0.315, 0.280) | (0.3, 0.9, √0.1) | 紫 |

三环中心线半径均为 75 mm，管半径为 6 mm，净孔径 138 mm。
每根竖直支柱半径 5 mm，与环的侧面连接；底座完整尺寸为 50 × 80 × 8 mm。
这些参数、支柱长度与定位来自公开几何，而非目测建模。

独立 `model/assembly.glb` 的原参考坐标整体增加 `(0, 0, 0.0009)`，桌面顶面为 z=0。
默认仿真转换为 `p_world = p_source + (-0.1356786, 0, 0.9205429)`，
将原桌面顶面 z=-0.0009 对齐到共享桌面 z=0.9196429。
三环相对绳子的布局不变。场景配置中的 `task.origin_xy_m` 可整体平移任务。
共享桌面为 1.5 × 1.4 m。严格初态碰撞审计发现：原共享 ALOHA 适配器相对任务坐标
降低了 20.9 mm，使底座法兰与初始绳端相交。此任务使用 `base_riser_height_m=0.0209`
和两个实体垫座恢复原参考的机器人/桌面相对高度；其他任务的默认安装高度不变。
建场时在原生 IPC 初始化之前设置参考 home 姿态，避免渲染位姿与原生碰撞体不一致。

## 物理模型与资产

源码入口：`topogym/tasks/rope_threading/`，职责为 `ThreadingLayout → ThreadingSceneBuilder → ThreadingScene`。
`reference.py` 从用户给定的公开文件提取首帧并校验哈希；建场不联网。
`prepare_assets.py` 生成可在 Blender 等工具中继续编辑的独立 OBJ/GLB。
`pre_build` 回调可为后续接触触发抓持接入声明；本初态没有端点约束。

- 环：64 × 24 的闭合三角网格，`convexify=False`，通孔真实保留。
  对原 64 段胶囊环的保守离散误差界约 0.142 mm。
- 绳：原中心线每段细分 4 次，321 截面、每截面 12 点，体网格由 TetGen 生成。
  使用连续 FEM+IPC、自接触、桌面/环/支架/机器人接触和直绳材料参考态。
  直绳参考态若导致四面体翻转则拒绝建场，不能悄悄改用弯曲初态作为无应力参考。
- 固定支架与环、底座存在设计连接处的静态重叠；关闭固定刚体间 IPC 接触和全场景交叠检查，
  单独检查绳子与全部夹具的初态正间隙。绳子不使用重力补偿。
- 默认 `E=100 kPa, nu=0.45, rho=650 kg/m³, mu=0.3`，接触距离 0.8 mm，
  摩擦速度正则化 1 mm/s，外步长 5 ms、4 子步；与原演示 MuJoCo 胶囊链的动力学不等价。
- 机器人采用原 ALOHA 双夹爪和 16 个自由度；保留未简化碰撞网格，
  严格执行测试采用 `external_articulation` 与机器人重力补偿。机器人接触操作尚未验收。

## 运行与检查

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.prepare_assets
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.rope_threading
.venv-gs121-nyx/bin/python -m unittest tests.check_rope_threading tests.check_configs_compose
```

默认输出 `runs/environment_bootstrap/rope_threading/wang_initial/index.html`。
保存三路展示视角、ALOHA 四路相机初态、相机环绕视频、静置前后状态、
解析后的配置、世界坐标资产及 JSON 报告。环绕只移动相机，不能当作机器人执行。
可用 `run.record_video=false` 省略视频，`run.settle_steps=0` 仅建场，
`run.output=<新目录>` 保留多次运行。

几何回归包含原尺寸与材料顺序、坐标变换、源布局正间隙、封闭体网格、
三种倾角的中心射线通孔检查、环壁命中对照、有向穿越和切触排除。
默认 40 步 / 0.2 s 自由静置检查有限状态、无翻转、桌面穿透小于 1 mm、
最大绳体位移小于 40 mm、仍未穿环和双臂待命漂移。
这只验证初态初始化与短时接触，不构成长时稳定性或穿环任务验收。

2026-09-17 的 `wang_initial` 实际运行已通过上述 0.2 s 检查；
七路初态图、两路静置后图和 45 帧 / 3 s 初态环绕视频均已生成。
资产、几何、配置组合、项目导入及参数卡相关的 13 项回归检查通过。

## 严格物理审计（2026-09-17）

早期 `wang_initial` 的 0.2 s 检查未覆盖原生机器人底座穿插，不能据此判断场景物理可靠。
`physics_v1/v2` 保存初态穿插失败；`v3` 为明确中止的短试跑；`v4` 完成五秒但末尾两秒
漂移 2.567 mm，超过 2 mm 门槛。修正高度并将低速摩擦参数恢复到项目已校验的 1 mm/s 后，
`physics_v5/free_baseline` 的 4000 个原生子步全部通过：无表面穿透、无四面体翻转，
最大绳长变化 0.208%，末尾两秒漂移 0.416 mm，最大速度 0.210 mm/s，全部 Newton 帧收敛。
`physics_v5/ring_contact` 随后完成 20 s / 16000 个原生子步，抬升、穿入 R1、持续接触滑动、
完全释放和落桌后静置全部通过。100 个接触样本中的穿越点移动 10.156 mm；最大绳长变化
0.872%，最大局部轴向应变 7.285%，最小体积比 0.694；末两秒漂移 1.457 mm，
最大速度 0.799 mm/s，全部 Newton 帧收敛。该试验使用显式软抓持夹具，不能算机器人执行。
时间步/网格对照和机器人接触资格仍须分别通过，不能从前两项推断完整可靠性。

初次并发启动 `free_halfdt` 在 CUDA 初始化时以退出码 134 终止，未产生物理轨迹；
这是运行时初始化失败，不提供机械结论。串行流程将其保留，并为重试新建 `free_halfdt_attempt_2`。

### 当前结论：未通过，未录制完整 demo

`free_halfdt_attempt_2` 将外步长减半到 2.5 ms，原生子步从 1.25 ms 减到 0.625 ms，
其余场景、材料和求解参数保持一致。运行在 2.498125 s / 3997 子步处因 GPU 显存不足中断；
此前所有原生子步收敛，没有表面穿透或四面体翻转。这不是一份完整的五秒对照。

但是，已保存的共同前 2.48 s 足以构成数值超差反例：直接匹配 124 个相同采样时刻、
不进行时间插值，在 0.06 s 的 81 个原始材料节点的 RMS 位置差为 **7.759 mm**
（门槛 2 mm），最大单点差为 **8.028 mm**（门槛 5 mm）。
竖直方向的整体弹起主导该差异；此项失败发生在显存中断之前，
不能归因于后续运行时错误。后续模拟也不能消除已经观察到的峰值超差。

初始绳表面离桌面 0.3 mm，位于 0.8 mm 的 IPC 接触作用范围内；初始化接触预载是后续
需要排查的方向，目前未声称已经确定全部因果。应先消除初始接触的时间步敏感性，再重新
完成时间步对照、网格细化、实际机器人抓取和四路完整录制。不能通过删掉起始帧或放宽门槛来计为通过。

可视化报告：`runs/environment-solvability/rope_threading/physics_v5/index.html`。
`qualification.json` 明确标注“不完整共同前缀”与超差，包含各次运行的配置和轨迹哈希。
未运行的 `ring_halfdt / ring_refined / robot_prefix` 保持待验收；没有生成或归档完整 MP4。

相关回归检查通过；全仓检查另在 `fiber_bundling` 参数卡处报
`Unqualified axes must remain candidate`，详见同目录的 `project_regression.log`。
它与本次绳穿环的数值超差是不同问题。

完整复测入口（新目录保留所有历史失败）：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_suite \
  runs/environment-solvability/rope_threading/new_suite --reference-speed 4 \
  --record-to runs/environment-solvability/rope_threading/new_full_reference
```

只有全部试验、数值比较、配置一致性和参考输入校验通过，流程才会启动录制。
`archive.py` 另行要求完整执行成功、四路同步视频可解码及资格证据有效，才可归档为完整 demo。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --output runs/environment-solvability/rope_threading/new_free
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --mode ring_contact --output runs/environment-solvability/rope_threading/new_ring
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.physics_probe \
  --mode reference_prefix --reference-speed 4 \
  --output runs/environment-solvability/rope_threading/new_robot_prefix
```

`ring_contact` 是显式辅助约束的局部加载试验，不是机器人 demo。
每个原生 IPC 子步读取真实 FEM 顶点、速度和刚体表面；执行连续碰撞检查，或以
“测得间隙大于两倍最大顶点位移”给出该子步全区间的保守分离证明。
证据包含初态交叠检查、原生配置、实现哈希、压缩求解日志、轨迹和独立报告。
这些检查不包含完整弹性能量、真实硬件参数标定或实验误差认证。

`reference_motion.py` 校验公开 51 段二进制及各数组 SHA-256，再提取 18712 个唯一时间样本。
这些文件明确标注为原参考数据，不能当作本地执行结果。
机器人执行只使用关节/手部目标；绳体由 FEM+IPC 重新计算，禁止回写参考绳节点。
两侧原生指面均在接触距离内才启用辅助抓持，目标跟随实测夹爪变换，松手时解除。
完整执行要求单次连续模拟完成参考动作序列，并在释放后保持材料顺序 `R1-/R2+/R3+`。
