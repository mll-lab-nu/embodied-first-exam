# 杂乱被子展平（blanket_flatten）

目标是让机械臂把刚掀起、落桌后杂乱堆叠的被子展开并整理平整。初始化先构造悬空复杂布面，确保材料与视觉绑定可靠，再完全释放给重力落桌。基础版直接以层间分离的布面出生；交叉折叠与整团扭转版先在展开状态建立绑定，再受控构造叠层。**机械臂任务从落桌静置验收之后开始。**

当前实现包括新任务参数卡、独立几何与场景、实际绑定审计、三视角重力过程录制、初态验收、机器人抓角展开控制器和释放后展平判据。完整成功执行以实际运行报告为准，初始化预览仍让机器人停在初始姿态。当前材料是 PBD 单层布面近似，尚不模拟有填充物被芯的体积与压缩特性。

**已归档的基础初态完整演示：**[全景 MP4](../../../demos/blanket_flatten/agentview/2026-09-18_single_arm_clear_home_v1_agentview.mp4) · [斜侧 MP4](../../../demos/blanket_flatten/front_oblique/2026-09-18_single_arm_clear_home_v1_front_oblique.mp4) · [腕部 MP4](../../../demos/blanket_flatten/wrist/2026-09-18_single_arm_clear_home_v1_wrist.mp4)。包含悬空出生、重力落桌、机器人辅助抓角展开、释放与撤手静置；这份成功记录使用较简单初态，不代表下述复杂麻花版已完成展平。配套证据保存在 `runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/`，原 `runs/demos/blanket_flatten/` 副本保留备份。

**新增低高度折叠与卷转初态：**[两档三视角对比播放页](../../../runs/environment_bootstrap/blanket_flatten/fold_roll_comparison_v2/index.html)。包含 3 次交替折叠后接 278° / 382° 连续卷曲，最低点离桌 2.5 / 2 cm。两档已通过初态与额外 10 s 静置复核；尚未在这两种新初态上验证机器人完整展平，不能计为新的完整机器人 demo。

**斜折角、纵横交叉折叠与整团扭转试验：**[两版三视角对照](../../../runs/environment_bootstrap/blanket_flatten/cross_twist_comparison_v3/index.html) · [8 mm 版直接播放](../../../runs/environment_bootstrap/blanket_flatten/corner_cross_twist_v8/render/index.html)。8 mm 版通过初态与额外 10 s 静置复核；6 mm 版仅因末态高度超过原门槛而未验收。实际端部相对转角均约 120°，横折、再次纵折和扭转仍未完全到位，尚未形成预期的紧密麻花。

## 为什么出生时必须松、落桌后可以紧

依据 [legacy cloth-unroll 第 3、4、9.12 节](../../../legacy/docs/develop/tasks/cloth_unroll_zh.md)：旧任务中相邻卷层距离接近粒子间距，视觉顶点选到了另一层的粒子，展开后呈现撕裂状。绑定只在出生时建立，因而可以先按较大间距建绑定，再让自由材料受重力压实。该历史文档中的“约三倍粒距”是经验门槛，不作为任意几何与求解器设置的绝对保证。

本任务还检查了本地 Genesis 1.2.1 的实际实现：`ParticleEntity._add_vverts_to_solver` 在出生时按空间距离选支撑粒子，再计算线性权重。当前场景每个视觉顶点使用 **12** 个支撑粒子。因此既要查不同层的间距，也要查尖锐折线两侧的混选。

## 连续布面与出生几何

- 材料尺寸 **0.60 × 0.48 m**，五道交替折叠；折线有随机偏移和不同倾斜方向。
- 折线均穿过整张材料，彼此不相交。每道折叠都是绕当前空间折线的刚体旋转，网格沿折线分区，因此所有三角面和边的材料尺寸保持不变。
- 基准折角 **105° ± 10°**，整体倾斜 **40°**、偏航 **18°**；最低点在桌面上方 **100 mm**。这里是绕折线的旋转角，0° 表示未折。
- 粒径 **8 mm**、控制网格目标间距 **12 mm**。非相邻面板的三角面最小间距必须至少为 **32 mm**，使用 FCL 的面间距离与相交检查；不能只比较顶点距离。
- 随机性由 `task.geometry.seed` 控制，拒绝不合法样本，记录实际折线、角度和接受的 attempt；超出尝试次数就报错，不用更小间距兜底。
- 相邻面板共用折线，几何最小间距必然为零。这些位置通过实际绑定的材料坐标距离检查，不能错误要求折线上也留缝。

`SceneBuilder` 创建后不会瞬移布料或重新生成网格；初始速度为零，无出生固定点、隐形支撑或按时间解除的折叠约束。桌面采用共享 `TabletopParticleFriction`，仅调整接触区切向速度。它是现有 PBD 桌面摩擦补偿，不是强制落地/压平操作。

## 实际绑定审计

重网格化可能改变粒子数及索引，不能把控制网格索引直接当作粒子索引。代码把实际粒子和实际视觉顶点投影回出生面板，恢复材料坐标，再读取实际 `support_idxs` / `support_weights`：

1. 支撑必须属于该块被子。
2. 支撑与视觉顶点在材料上的距离不超过四倍名义粒径，即 **32 mm**。
3. 出生位置重建误差、粒子到出生面的投影距离均小于一个粒径。
4. 保持同一张绑定表，把材料坐标假想映射到平面，检查视觉顶点能否回到对应材料位置，最大误差小于一个粒径。此为离线绑定一致性检查，不是物理展开成功证据。

初版曾使用 **125° ± 16°**：虽然不同层最小距离约 55 mm，但有 **107** 个支撑跨过尖折线后在材料上超过 32 mm，最大约 42 mm，被审计拒绝。张开至 105° ± 10° 后该计数为零。后续改变粒径、折角或折数时要重做审计，不能仅沿用这次的通过结果。

## 落桌、静置与展平判据

初始化按 5 ms 外步长、8 子步、24 次拉伸约束迭代运行。每 **50 ms** 采样一次物理与视觉诊断，从至少 2 s 开始寻找连续 0.4 s 的通过窗口，最长运行 6 s。失败返回非零退出码并保留报告和轨迹。

初态要求全部粒子仍在桌面范围内、没有超过 1 mm 容差的桌面穿透、拉伸与视觉边长正常、最大高度不超过 120 mm，投影覆盖率介于 **12%–80%**。覆盖面积是实际仿真三角面在桌面的投影**并集**，不是包围盒或凸包；孔洞和叠层不会被错误计入。

静置同时约束平均速度 ≤15 mm/s、99 分位速度 ≤50 mm/s、最大速度 ≤400 mm/s，并要求窗口内各粒子相对窗口起点的最大位移 ≤8 mm。较宽的瞬时最大速度上限用于容纳 PBD 少数接触粒子的抖动，必须与位移窗口同时使用；单独放宽最大速度不能表示稳定。采样检查不等于逐子步的连续碰撞证明。

候选展平成功条件为：释放抓持后连续 0.5 s 满足覆盖率 ≥90%、95 分位离桌高度 ≤14 mm、最高点 ≤25 mm、最大材料边长比 ≤1.15，并通过相同的完整性、桌面范围与静置检查。压成两层的布、拉到空中的布、只把整团移走，以及靠拉伸增大面积均有对应拒绝条件。`flatten_gates` 需与 `AcceptanceWindow` 配合使用；单帧通过不能记成功。最终机器人验收还要核对撤手与接触模型。

## 运行与文件

从仓库根目录执行：

```bash
# 已有 Genesis 环境另需三角面距离与投影面积依赖（当前工作环境已安装）。
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-blanket.txt

PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.blanket_flatten

# 只检查物理，不渲染或放置机器人
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.preview \
  run.render=false run.record_video=false run.include_robot=false \
  task.geometry.seed=1 run.output=runs/environment_bootstrap/blanket_flatten/seed_1_probe

.venv-gs121-nyx/bin/python -m unittest tests.check_blanket_flatten tests.check_configs_compose -v
```

默认产物在 [`runs/environment_bootstrap/blanket_flatten/seed_0_soft_drop/`](../../../runs/environment_bootstrap/blanket_flatten/seed_0_soft_drop/index.html)：`birth_*` / `settled_*` 静帧、三路同步 `drop_*.mp4`、`report.json`、解析配置、带材料坐标及绑定表的 `particle_trace.npz`、出生 OBJ 和材质。预览采用 Genesis rasterizer，直接检查 PBD 的原生 visual 网格，并复用实验室内部点光源照亮褶皱。`task.vis_mode=particle` 可生成粒子诊断版本，使用单独输出目录保留对照。

这些是初始化过程视频，不是完整机器人 demo，不归入正式机器人视频档案。新版本请指定新的 `run.output`，以保留已有检查结果。

实现入口：[`geometry.py`](../../../topogym/tasks/blanket_flatten/geometry.py)、[`scene.py`](../../../topogym/tasks/blanket_flatten/scene.py)、[`diagnostics.py`](../../../topogym/tasks/blanket_flatten/diagnostics.py)、[`preview.py`](../../../topogym/tasks/blanket_flatten/preview.py)。无 `legacy` 运行时依赖。

## 完整机器人执行与三视角录制

`blanket_flatten_robot.yaml` 沿用初始化材料与几何，选择 seed 1，使用 **64 位精度、5 ms 外步长、16 子步**，给机械臂启用重力补偿。采用共享 home 的其余关节角，将第一关节转到 −0.9 rad，把手臂停在悬空布面之外。原始 32 位、8 子步的短预览不能替代延长静置复核。控制器使用实际 Robotiq 指垫位置进行 TCP 反馈，依次执行接近、下降、闭合、抬起、展开、放下、释放和撤手。材料角点由审计恢复的材料坐标选择，不依赖重网格后的固定索引。机器人只在启动时设置 home，此后由关节控制和物理步进运动。

抓取采用**局部辅助抓持**：两侧实际指垫表面均须接近布角至 8 mm 内、TCP 距布角不超过 12 mm，且角点未埋在其他层下，才允许把空间半径 14 mm、材料半径 24 mm 内的粒子附着到手部 link。闭爪等待 3 s，记录双侧实际间距及附着粒子。机器人与布料的 PBD 碰撞耦合关闭；此流程不是纯接触摩擦夹取。桌面、自接触、重力和布料约束仍由物理求解器处理。机器人动作期间不直接写粒子位置，不固定远端布角，也不按目标平面重建布面。

每个 5 ms 外步检查材料边长、粒子位置有限性、桌面范围和指垫高度；每 50 ms 记录覆盖率、速度、高度和视觉边长。独立静置测试至少持续 10 s，再要求末尾连续 0.4 s 通过，最多额外等待 4 s；完整动作结束则必须全部松手、撤离，再经过 3 s 自由静置且末尾连续 0.5 s 通过展平条件。这里的检查仍不是逐子步连续碰撞证书。

出生时以及落桌/被动静置阶段每 50 ms，另外读取机械臂实际碰撞几何的世界顶点，通过 FCL 检查布料三角面与所有机器人碰撞面的净空 ≥8 mm，不能只测顶点间距。归档同时要求这项检查通过。`robot_sub16_fp64_v3` 虽然通过了数值展平判据，但画面复核发现悬空布面与原始共享 home 手臂交叠，已用 `review.json` 标记不可收录；不能把该次结果作为正式完整 demo。该发现促成了停放位修正和新增三角面穿越反例测试。

```bash
# 独立静置复核；始终使用新的输出目录保存失败和重复运行。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.robot_demo \
  task.geometry.seed=1 run.mode=stability run.output=runs/environment_bootstrap/blanket_flatten/stability_example

# 同一次连续物理执行，记录粒子与机器人全部关节（含被动关节）。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.robot_demo \
  task.geometry.seed=1 run.output=runs/environment_bootstrap/blanket_flatten/robot_example

# 从该次物理状态生成三路同步视频。失败运行须显式传 --allow-failed，仅供诊断。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.render_execution \
  runs/environment_bootstrap/blanket_flatten/robot_example \
  --camera-overrides configs/camera_configs/blanket_flatten_recording.yaml

# 仅当完整执行、独立静置和全部视频通过后才可正式收录。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.archive \
  runs/environment_bootstrap/blanket_flatten/robot_example \
  --stability runs/environment_bootstrap/blanket_flatten/stability_example --run-id single_arm_v1
```

物理运行保存解析配置、源码快照、逐步报告和 `physical_trace.npz`。三路 `agentview / front_oblique / wrist` 逐帧回放**同一次真实物理执行**的完整关节与粒子状态，不重建夹爪被动关节；渲染阶段不推进仿真，检查状态误差 ≤1 µm 并记录来源 SHA-256。相机覆盖文件仅调整画面，解析后的机位单独保存为 `render_config.yaml`，不改写物理来源配置。这是已有物理执行的呈现，不代表又完成了一次动力学运行。

正式归档入口会拒绝失败、未松手、动作缺帧、粒子瞬移、少于三路相机或静置不足的记录，并完整解码视频、校验帧数/时长与副本哈希。视频独立复制到 `demos/blanket_flatten/<camera>/`，报告和 Markdown 记录复制到 `runs/demo_metadata/blanket_flatten/`；不新建或更新 HTML。未通过的尝试留在原始运行目录，不能计为完整 demo。

## 2026-09-18 基准实测

RTX 4090 / Genesis 1.2.1，机器人在场但未操纵。三路视频来自同一次连续重力执行，均为 49 帧、20 fps、2.45 s，覆盖出生、下落和最终验收。

| 读数 | `seed_0_soft_drop` |
| --- | --- |
| 出生非相邻面板最小间距 | 72.76 mm，约实测粒距的 10.18 倍 |
| 仿真粒子 / 视觉顶点 / 每顶点支撑数 | 5332 / 2542 / 12 |
| 超过材料距离门槛的支撑 | 0 |
| 假想平铺绑定最大位置误差 | 0.497 mm |
| 通过初始化的模拟时间 | 2.4 s |
| 连续验收窗口 / 最大位移 | 0.4 s / 2.89 mm |
| 覆盖率 / 最大离桌高度 | 31.65% / 81.25 mm |
| 平均 / 99 分位 / 最大速度 | 2.52 / 37.68 / 159.80 mm/s |
| 最低粒子离桌高度 / 桌外粒子 | +4.00 mm / 0 |
| 最大材料边长比 / 视觉边长比 | 1.120 / 1.442 |
| 展平终态条件 | 覆盖率、平整度、最高点均未通过，说明初态尚需整理 |

人工查看出生、最终侧视与俯视图，布面连续，未见孔洞或撕裂。最终形态仍带有出生褶叠的方向性；更紧密、更多方向的乱团可作为后续几何 family，不能把当前基准称为任意随机揉皱分布。

第二个 seed 的独立无机器人、无渲染物理复核也通过：[`seed_1_probe/report.json`](../../../runs/environment_bootstrap/blanket_flatten/seed_1_probe/report.json)，2.4 s 验收、覆盖率 44.64%、最高点 58.30 mm、窗口最大位移 4.82 mm，非局部绑定计数为零。这验证了两个具体初态，不代表整个候选参数范围已完成物理验收。新增任务与配置解析共 **9 项检查通过**。

保留了被拒绝的对照：68° 倾角 / 12 次迭代在落地时材料边长比达到 1.356；55° / 12 次迭代达到 1.365；55° 的半步长对照和 24 次迭代对照仍有少量粒子速度超限，均未通过静置。这些形态未作为默认基准，也未放宽完整性或静置门槛来通过它们。

离线检查覆盖 12 个几何 seed、材料坐标重建、实际支撑表反例、三角面相交、压成双层/抬起角点/未松手的判负及持续窗口；物理验收范围仍以各 run 报告为准。现有 `tests.check_task_baseline_catalog` 的全量运行因 `fiber_bundling` 参数卡轴状态不符合现有校验规则而失败；新增被子参数卡及配置解析检查通过，未修改那项任务的卡或校验规则。

## 2026-09-18 延长静置复核

短预览通过后，32 位 / 8 子步的独立重跑仍暴露了初态抖动及个别落桌瞬间过伸：`stability_v1` 在 6 s 时最大速度 0.513 m/s；`stability_seed1_v1` 延长到 12.4 s 后瞬时最大速度 0.406 m/s，仍超过 0.4 m/s 门槛；两个 seed 1 重跑在落桌时边长比达到 1.313 / 1.329。增加空气阻力或拉伸迭代的部分对照也被拒绝，报告均保留，未扩大门槛。

采用 **64 位 / 16 子步 / seed 1** 后，[`stability_sub16_fp64/report.json`](../../../runs/environment_bootstrap/blanket_flatten/stability_sub16_fp64/report.json) 通过独立静置复核：

| 读数 | 结果 |
| --- | --- |
| 总物理时间 / 初态验收后继续静置 | 12.75 s / 10.00 s |
| 最末连续通过窗口 / 最大位移 | 3.90 s / 5.17 mm |
| 最终平均 / 99 分位 / 最大速度 | 0.180 / 0.512 / 6.613 mm/s |
| 全程最大材料边长比 / 视觉边长比 | 1.154 / 1.638 |
| 最低粒子离桌高度 / 桌外粒子 / 非有限步 | +4.00 mm / 0 / 0 |
| 最终覆盖率 / 最大高度 | 49.20% / 82.82 mm，仍需要机器人整理 |

10 s 内一直执行完整性检查，速度与窗口位移要求在末尾持续满足；不能将其描述为从静置起点开始的整整 10 s 都已经静止。此结果验证这一具体设置与实例，并不把候选参数空间升级为物理合格。完整机器人抓持与展开还必须单独通过 `robot_demo` 的最终验收。

## 首个完整物理执行：避让出生区域的停放位

[`robot_clear_home_v1/report.json`](../../../runs/environment_bootstrap/blanket_flatten/robot_clear_home_v1/report.json) 已完成同一次连续 **32.50 s / 6500 步** 物理执行：悬空出生 → 自由落桌 → 静置验收 → 接近布角 → 闭爪并通过双指接近检查 → 局部辅助抓持 → 抬起与向外展开 → 放下、完全释放 → 撤手 → 3 s 自由静置。第一角展开已达到全部终态门槛，因此控制器正常停止，没有继续多余的抓取。

| 验收项 | 本次结果 |
| --- | --- |
| 出生及落桌阶段机器人净空 | 67 次采样，最小 173.90 mm |
| 抓取前双侧指垫到布角距离 / 附着粒子 | 2.322 / 2.343 mm；5 个局部粒子 |
| 全程最大 TCP 误差 | 0.525 mm |
| 全程最大材料边长比 / 视觉边长比 | 1.144 / 1.531 |
| 最低粒子离桌高度 / 桌外粒子 / 非有限位置步 | +4.00 mm / 0 / 0 |
| 最终覆盖率 / 最大材料边长比 | 99.856% / 1.002 |
| 最终 95 分位高度 / 最高残余边角 | 4.00 / 14.52 mm |
| 撤手后的连续通过窗口 / 最大位移 | 2.95 s / 0.00270 mm |
| 抓持是否全部释放 / 非局部视觉支撑 | 是 / 0 |

同一新停放位的独立复核 [`stability_clear_home_v1/report.json`](../../../runs/environment_bootstrap/blanket_flatten/stability_clear_home_v1/report.json) 也通过：总时间 13.85 s，其中初态验收后继续静置 10 s；机器人净空检查共 278 次，最小同为 173.90 mm；末尾连续通过窗口 1.45 s，最大位移 0.705 mm，最终最大速度 0.516 mm/s。

画面已复核出生、接近、闭爪、抬起、展开、松手和撤离后的终态。当前仍是 **PBD 单层布面与局部辅助抓持**，不等同于带填充物的真实被芯，也不是纯摩擦夹取；验证范围为这个 seed 1 实例。布面末尾保留轻微边角翘起，符合事先声明的 25 mm 最高点门槛，没有修改门槛来接受该结果。

三路正式视频各 **651 帧、20 fps、32.55 s**，来自相同的 32.50 s 物理轨迹，时长包含初始帧的展示周期。全部帧的粒子与完整关节状态回读误差均为 0；未重建被动关节，也未重新执行动力学。归档前已完整解码三路 MP4、核对帧数/时长、独立副本与配套文件的 SHA-256，以及播放页本地链接。播放页、物理报告、独立静置报告、轨迹、出生资产、配置与清单均有独立保留副本，统一索引已更新。

真实场景负例 [`birth_overlap_negative/report.json`](../../../runs/environment_bootstrap/blanket_flatten/birth_overlap_negative/report.json) 使用原来的交叠停放位，在第 **0** 个物理步就因表面距离 −1.863 mm 被拒绝；失败报告完整保存。几何、绑定、终态反例、出生面穿越、归档拒绝和配置解析共 **12 项检查通过**。

## 低高度折叠与卷转初态（2026-09-18）

新增 `suspended_fold_and_roll_v2`，材料尺寸仍为 60 × 48 cm。先设置 3 道正负交替的折线，再接 5 或 7 道同向转动的折线，形成折叠段与卷曲段组合。各面板宽度和折线倾角有变化；每个面板依然是刚体旋转后的材料片，连续网格保持面积和边长。这里不是把一个有厚度的折叠包再用任意坐标变换强行卷弯，也不是任意多方向揉团分布。

`roll_fold_count` 控制同向卷曲折线数，`roll_angle_deg / roll_angle_jitter_deg` 控制逐道角度，`roll_direction` 控制卷向，`panel_width_jitter` 控制各段宽度变化，`pitch_deg` 调整横截面的落桌朝向。保留旧配置的随机序列；旧 seed 1 出生顶点重建误差小于 3e-16 m。出生几何报告新增交替折数、卷曲折数、累计卷角和最低/最高高度，不能只用最低点来描述整块布的落差。

| 项目 | 折叠 + 局部卷曲 | 折叠 + 整圈卷转 |
| --- | --- | --- |
| 配置 | [`blanket_flatten_fold_roll.yaml`](../../../configs/blanket_flatten_fold_roll.yaml) | [`blanket_flatten_fold_spiral.yaml`](../../../configs/blanket_flatten_fold_spiral.yaml) |
| 物理记录 | [`fold_roll_low_seed2_v2`](../../../runs/environment_bootstrap/blanket_flatten/fold_roll_low_seed2_v2/report.json) | [`fold_spiral_low_seed2_v1`](../../../runs/environment_bootstrap/blanket_flatten/fold_spiral_low_seed2_v1/report.json) |
| 交替折数 + 卷曲折数 / 累计卷角 | 3 + 5 / 278.21° | 3 + 7 / 382.35° |
| 最低—最高出生离桌高度 | 2.50–19.54 cm | 2.00–19.89 cm |
| 名义粒径 / 实际粒子数 | 8 mm / 5292 | 6 mm / 9379 |
| 非相邻层最小净空 / 要求 | 43.35 / 32 mm | 30.76 / 24 mm |
| 非局部视觉支撑数 | 0 | 0 |
| 总时间 / 初态验收后继续静置 | 12.4 / 10.0 s | 12.4 / 10.0 s |
| 全程最大材料边长比 / 视觉边长比 | 1.073 / 1.300 | 1.196 / 1.607 |
| 最末通过窗口 / 窗口最大位移 | 8.5 s / 3.49 mm | 7.0 s / 4.16 mm |
| 末态覆盖率 / 最大高度 | 55.42% / 45.55 mm | 42.48% / 41.84 mm |
| 末态平均 / 99 分位 / 最大速度 | 0.0109 / 0.0915 / 4.36 mm/s | 0.0771 / 1.155 / 84.29 mm/s |
| 全程最低高度 / 桌外粒子 / 非有限位置步 | +4.00 mm / 0 / 0 | +3.00 mm / 0 / 0 |
| 最小机器人净空 | 301.17 mm | 279.36 mm |

旧完整 demo 的出生高度为 **10.0–61.65 cm**。新版本同时降低最低点和最高点。整圈版本使用更细的粒子容纳卷层，仍要求至少四倍名义粒径的层间净空，并重新审计实际 12 支撑绑定；没有放宽绑定、完整性或静置门槛。两档沿用 float64、5 ms 外步长、16 子步、24 次拉伸迭代，无出生固定点，物理过程中没有粒子位置写入。末态仍有叠层与翘起，不满足展平条件。整圈版本较紧凑，但覆盖率不能替代实际机器人难度测试。

保留了被拒绝的尖折角尝试：`fold_roll_low_seed2_v1` 使用 118° ± 12° 交替折角，几何净空通过，但实际绑定有 2 个支撑的材料距离超过 32 mm，最大 36.49 mm，在物理步进之前被拒绝。其解析配置、出生资产、`assets/binding_report.json` 与 `geometry_study_v2/stability_seed2.log` 均保留。后续采用 105° ± 8°，两档绑定均通过。

```bash
# 新目录保存一次完整初态与静置运行。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.robot_demo \
  --config-name blanket_flatten_fold_spiral \
  run.output=runs/environment_bootstrap/blanket_flatten/spiral_example

# --initialization 明确使用初态资格检查与全景/近景/俯视相机。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.render_execution \
  runs/environment_bootstrap/blanket_flatten/spiral_example --initialization \
  --camera-overrides configs/camera_configs/blanket_flatten_initialization.yaml
```

三路初态视频使用同一次连续物理运行的真实粒子和全部关节轨迹，渲染不推进仿真；粒子和关节逐帧回读误差均为 0。每路为 249 帧、20 fps、12.45 s，包含出生帧展示周期。两档分别完整解码三路视频，核对帧数、时长及 SHA-256；播放页支持方案切换、同步播放、慢放、拖动和出生/静置末帧对照。这些产物保留在初态运行目录，不覆盖根目录 `demos/blanket_flatten/` 中已验证的旧版完整机器人 demo。几何、绑定、执行反例与配置解析共 **14 项检查通过**。

## 斜折角、纵横交叉折叠与整团扭转

按用户进一步明确的顺序，新候选 `staged_corner_cross_twist_v3` 使用 [`blanket_flatten_cross_twist.yaml`](../../../configs/blanket_flatten_cross_twist.yaml)：先沿斜线折起一角，再纵折、横折、再次纵折，最后让折好结构的两端反向转动，中段自行弯曲与起皱。它不再用一串同向折线代替整团扭转。各角度是预整形控制目标，不能直接当作布面实际达到的折角或扭角；每阶段保存实际网格与目标偏差。

跨方向折叠需要让已有叠层滑移、起皱，不能把每层都刚性塞入同一个折叠变换。实现先在展开的 60 × 48 cm 布面上建立材料静长、重网格后的材料坐标和实际视觉支撑，随后关闭**布料求解器**的重力，以有上限的速度控制逐步预整形。前面的角部与纵向目标引导整片材料；交叉折叠只引导折起一侧的边缘，另一侧可滑移，扭转引导两端，给中间折带留下形变自由度。速度控制同时抑制材料边长变化和非局部层间的过快接近，并在拉伸升高时自动减慢动作；原生 PBD 继续求解材料约束与自接触。

这一阶段属于**程序化受控初态构造**，不是机械臂操作或无外力的自由仿真。整个构造阶段没有直接写入粒子位置、重定义材料静长、重建视觉绑定或固定粒子。整形后将布面缓慢降到低处，撤除全部预整形控制，恢复重力，再重新计时检查下落、静置与额外 10 s 稳定性。已有全流程归档保留，新的候选须以自己的实际报告和画面审查为准。

`preparation.py` 将速度目标投影到材料边约束，并在预整形时为靠近的非局部材料点增加接近速度约束。这是初始化控制的一部分，释放后不再调用。展开状态绑定的支撑始终跟随同一材料邻域，因此不在紧密交叉层间重新寻找最近粒子。配置保持原有 1.30 材料边长比门槛；当前候选将拉伸迭代增加至 48 次，精度仍为 float64、外步长 5 ms、16 子步。

前三次尝试在横折阶段被完整性门槛拒绝，报告均保留于 `corner_cross_twist_v1/v2/v3`：对应触发边长比分别为 1.3011、1.3038、1.3029。它们没有完成整团扭转或落桌验收，不能作为成功初态。对各失败末帧以及第三次尝试的已完成斜折、纵折状态进行了 MeshLab 三角面自交检查，所检查状态的相交面数均为 0；这项离散帧检查不替代连续碰撞保证。

第四次尝试 `corner_cross_twist_v4` 改为引导两侧边缘、使用 48 次拉伸迭代，在横折收拢末段仍因边长比 1.3006 被拒绝。后续改为仅引导折起一侧，避免把整个厚叠层两端同时限制在互不相容的弯曲弧长上；还加入逐步减速和阶段间卸载，仍沿用原始 1.30 的完整性判据。阶段结束表示该段控制已执行，不能据此宣称所有粒子精确达到了目标位置或设定角度。

第五次尝试进入扭转与降低高度阶段，但端部材料点的平面旋转拟合只得到约 57° 相对转动，未形成预期的充分拧转。随后投影面积求并集发生 GEOS 数值异常；保留了原日志、轨迹及明确标记为恢复记录的失败报告。面积计算现对这一异常使用 10 nm 精度网格回退，不修改物理状态或验收门槛。

新的 [`blanket_flatten_cross_twist_arcs.yaml`](../../../configs/blanket_flatten_cross_twist_arcs.yaml) 使用嵌套圆弧目标：让不同高度的叠层具有不同弯曲半径和折痕带宽，保留各水平材料线的弧长，避免将厚叠层直接套入同一个转动。斜角、纵折、横折、再纵折都引导全片；最终拧转仍只引导两端，内部由 PBD 形成褶皱。`corner_cross_twist_v7` 是采用此目标的早期中止记录，`v8` 使用相同目标及更快的诊断实现重新运行。

`corner_cross_twist_v6` 在自由落桌时因材料边长比 1.3066 被拒绝，不能作为稳定初态。`v8` 完成了 40.45 s 连续记录，并通过释放后 2.40 s 初态验收与额外 10 s 静置；这不表示所有折叠目标都已精确达到。尤其是端部相对转角拟合约 **118.56°**，小于设定的 240°，横折与再次纵折还存在明显目标偏差。这是可以查看的交叉折叠、部分整团扭转初态试验，尚不是多圈紧密麻花或完整机器人整理。

| v8 复核项 | 实测 |
| --- | --- |
| 受控预整形后开始自由落桌 | 28.05 s |
| 释放时最低—最高点离桌 | 2.76–28.71 cm |
| 全程最大材料 / 视觉边长比 | 1.2761 / 1.0512 |
| 非局部视觉支撑 / 桌外粒子 / 非有限位置步 | 0 / 0 / 0 |
| 机器人最小净空 | 147.17 mm |
| 末态覆盖率 / 最高点 | 45.743% / 90.55 mm |
| 最后连续通过窗口 / 最大位移 | 9.95 s / 0.152 mm |
| 810 个记录帧的粒子网格自交检查 | 未检出相交面；非连续碰撞保证 |

另设 [`blanket_flatten_cross_twist_fine.yaml`](../../../configs/blanket_flatten_cross_twist_fine.yaml) 作为 v9 对照：名义粒径改为 6 mm，弯折各层采用共同起始切线，避免旧目标的不同层圆弧相互越过；交叉折叠只控制折起侧的边缘。材料完整性仍逐外步检查，完整指标和机器人净空以 0.1 s 间隔记录。目标几何的分层弧长与不相交检查、投影控制、旧版几何/执行/配置检查共 **22 项通过**；实际物理结果仍以各自报告为准。

v9 连续记录 34.05 s，在释放后 6 s 因初态验收超时而结束。末态仅 `landed` 高度项未通过：最高点 **13.52 cm > 12 cm**；其余末态完整性、速度、覆盖率与桌面边界指标均通过。没有更改门槛或把它改记为成功，也没有执行额外 10 s 静置。实际端部相对转角估计 **122.11°**，释放最低—最高点 **1.17–31.52 cm**，末态覆盖率 **28.933%**；全程最大材料/视觉边长比 **1.2588 / 1.0362**，非局部视觉支撑、桌外粒子、非有限位置步均为 0。682 个记录帧的网格自交复核未检出相交面。

两版目前都是**部分达到形态目标的试验**。v9 再次纵折阶段的受控点目标偏差为 20.54 cm，不能把阶段执行完毕等同于折叠到位；v8 的交叉折叠也有明显偏差。两者都已尝试折后整团扭转，但不能宣称生成了完整紧密、多圈的麻花结构。实际转角统计采用对应端部材料点的二维刚性旋转拟合，端部自身变形使它只是近似指标。

两版均保存全景、斜侧近景、俯视三路同步 MP4：v8 每路 810 帧 / 20 fps / 40.50 s，v9 每路 682 帧 / 20 fps / 34.10 s。全片粒子与全部关节状态回读误差均为 0，三路均完整解码并核对帧数、时长和 SHA-256。播放页默认停在整团扭转后的结构，可从头播放或跳转到拧转与自由落桌阶段；旧折叠卷曲对照页顶部也增加了新试验入口。视频是同一次实际记录的状态重渲染，未执行新的动力学或添加机器人整理动作。

v9 的重渲染避免逐相机重复更新相同场景。39 张共同关键帧与优化前比较：近景和俯视逐像素一致，全景仅极少桌边背景像素有差异，最大平均通道差 0.000339 / 255；详细记录见 `render_optimization_review.json`。中止的旧渲染片段在 `render_attempt_redundant_updates/` 中明确标记为不完整，不参与对照页或视频验证。

```bash
# 避免小规模稀疏速度投影受到多线程 BLAS 调度开销影响。
OPENBLAS_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.robot_demo --config-name blanket_flatten_cross_twist_arcs \
  run.output=runs/environment_bootstrap/blanket_flatten/cross_twist_example

OPENBLAS_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.review_preparation \
  runs/environment_bootstrap/blanket_flatten/cross_twist_example

PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.render_execution \
  runs/environment_bootstrap/blanket_flatten/cross_twist_example --initialization \
  --camera-overrides configs/camera_configs/blanket_flatten_preparation.yaml
```

阶段播放页提供从头查看、跳到整团扭转后、从自由落桌开始，以及三视角同步和慢放；关键静帧对应斜折、两次纵折、横折、整团扭转及释放。失败记录只能通过 `--allow-failed` 明确标为诊断预览。

## 照片参考：保留长轴的纵褶与整束扭转

根据用户的长条状揉皱照片，新增 `staged_gathered_twist_v4`。入口是[两版图像与视频对照](../../../runs/environment_bootstrap/blanket_flatten/photo_gathered_comparison/index.html)，各版另有可拖动旋转的实测粒子网格和空中构型图。**已验证的是长条收褶与整束扭转；当前不能声称照片那样不均匀、细碎的随机揉皱已经稳定复现。** 单张照片也不能唯一确定原始折法或扭角。

[`blanket_flatten_gathered_twist.yaml`](../../../configs/blanket_flatten_gathered_twist.yaml) 沿 48 cm 宽度收成 8 个不等宽纵向面板（7 道圆滑折痕），保留 60 cm 长轴；中央面板倾角目标 78°，两端约 68°，折痕过渡宽度 6 mm。整个横截面沿长轴逐段转动，相对扭角目标 270°，长轴尺度目标 0.92，中心线有 6 mm 的轻微侧摆。`gathered_geometry.py` 按材料宽度弧长积分生成连续目标，再由保持材料约束的速度控制引导实际 PBD 布料；这些是目标坐标，不能替代实际状态。31 个目标采样的最大材料边长比 1.257，未检出三角面自交；这不等于物理运行已经通过。

展开时建立的材料静长、材料坐标与 12 支撑视觉绑定始终保留，后续没有重新绑定或直接写入粒子位置。采用 4 mm 名义粒径，共 18406 个实际粒子；float64、5 ms 外步长、16 子步、48 次拉伸迭代。材料边长、有限位置和桌面范围逐外步检查，完整指标及机器人净空每 0.2 s 检查；视频以 10 fps 采样。

| 实测项 | 长褶扭转 v1 | 非对称推挤 v2 |
| --- | --- | --- |
| 配置 | [`gathered_twist`](../../../configs/blanket_flatten_gathered_twist.yaml) | [`gathered_bunched`](../../../configs/blanket_flatten_gathered_bunched.yaml) |
| 实测空中结构 | 57.0 × 17.1 × 17.8 cm | 51.8 × 18.2 × 17.9 cm |
| 空中端部相对转角拟合 | 258.34° | 267.07°（推挤后） |
| 释放时最低—最高点离桌 | 1.93–20.06 cm | 1.66–20.17 cm |
| 全程最大材料 / 视觉边长比 | 1.1278 / 1.0135 | 1.3335 / 1.0235 |
| 非局部视觉支撑 / 桌外粒子 / 非有限位置步 | 0 / 0 / 0 | 0 / 0 / 0 |
| 所有采样帧的网格自交检查 | 235 帧，未检出 | 156 帧，未检出 |
| 物理结论 | 23.40 s；初态通过，额外静置 10.20 s | 15.475 s；下落时材料过伸停止 |
| 视频 | 三路，各 235 帧 / 23.50 s | 三路，各 156 帧 / 15.60 s，失败诊断 |

v1 收褶与扭转的受控位置 RMS 误差分别为 2.57 / 10.03 mm，均达到原有 15 mm 控制门槛。释放后 2.55 s 接受初态，最终覆盖率 19.334%，最高点 5.388 cm，最后连续 10 s 窗口最大粒子位置变化 0.0672 mm。末态平均 / 99 分位 / 最大速度分别约 0.535 / 8.31 / 233.8 mm/s，存在局部数值速度，不能把稳定窗口等同于所有粒子速度为零。相对转角是材料端部二维旋转拟合，受端部形变与角度包裹影响，不是精确扭转测量。

v2 在扭转之后增加沿长轴的非对称推挤：仅引导两端与中段，余下材料自由变形。目标是左侧缩短 32%、右侧缩短 4%；按同一材料端部与中段的轴向距离，实际约为 **19.73% / 3.36%**。推挤阶段受控 RMS 误差 **25.65 mm**，超过原有 15 mm 门槛，因此未完全达到形状目标。释放后 0.175 s，最大材料边长比 **1.3335 > 1.30**，执行被原有完整性判据停止；没有完成落桌验收或额外静置，不能作为稳定初态，也不能把它的最后一帧称为落桌末态。失败记录、真实空中网格和视频均保留。

两版三视角均由各自同一次实测粒子和全部机器人关节状态同步重渲染，渲染不推进物理；位置和关节回读误差均为 0。六个 MP4 均完整解码，核对帧数、时长与 SHA-256；关键帧、物理报告和目标追踪误差与视频对应。三角面自交检查仅覆盖保存的离散帧，不是连续碰撞保证。交互页显示实测粒子网格，色带帮助追踪同一材料面板；原生材质与场景以三视角视频为准。本组为程序控制的初态实验，未新增机械臂整理动作，未替换 `demos/blanket_flatten/` 的既有完整机器人 demo。

```bash
OPENBLAS_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.robot_demo --config-name blanket_flatten_gathered_twist \
  run.output=runs/environment_bootstrap/blanket_flatten/gathered_example
```

## 2026-09-19：用户选定麻花初态的动作验证

选定的是 `photo_gathered_twist_v1` 的落桌形状：[初态全景](../../../runs/environment_bootstrap/blanket_flatten/photo_gathered_twist_v1/render/overview.mp4) · [初态侧视](../../../runs/environment_bootstrap/blanket_flatten/photo_gathered_twist_v1/render/detail.mp4) · [初态俯视](../../../runs/environment_bootstrap/blanket_flatten/photo_gathered_twist_v1/render/topdown.mp4)。它保留 8 个不等宽纵向面板和整束扭转，与此前已归档的简单初态完整 demo 不同。

**独立物理稳定性复核通过；复杂初态的完整展平目前尚未通过。** `gathered_selected_stability_v1` 在 2.4 s 初态验收后自由静置 10.0 s，稳定窗口最大位移 0.1431 mm；全程最大材料 / 视觉边长比为 1.09435 / 1.01251，没有桌外粒子或非有限位置。125 个保存帧的三角面自交检查未检出相交。末态覆盖率 19.3335%，最高点 53.881 mm。见[稳定性报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_selected_stability_v1/report.json)和[逐帧自交检查](../../../runs/environment_bootstrap/blanket_flatten/gathered_selected_stability_v1/self_intersection_review.json)。离散帧检查不是连续碰撞证明。

现在可看的较长动作诊断为 `gathered_robot_v8`：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/wrist.mp4)。三路各 1742 帧、10 fps、174.2 s，均已完整解码、核对同步和 SHA-256。它连续记录七次抓放，包括两次拉伸保护释放，覆盖率达到 75.7%，仍有被覆盖的角；第八次接近时因重复选回已展开的角而主动结束，**属于未完成诊断，不计为成功 demo**。3510 个保存帧未检出布面自交；臂部 link0–7 的离散复核最小净空 81.71 mm。详情见[执行报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/report.json)、[臂部复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/robot_motion_review.json)及[视频核验](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/video_verification.json)。

抓取采用双侧指垫接近检查后的局部粒子附着辅助，刚体–布料 PBD 耦合关闭，因此不能宣称纯摩擦抓持。布角及替代布边都要求 8 mm XY 邻域内上方高度差不超过 3 mm，到达后和闭爪后再次检查。每次释放后通过真实关节控制回位；动作中不写粒子位置、不重置机器人姿态。材料边长比达到 1.20 时主动松手，原有 1.30 硬失败门槛保持不变；保护松手不等同于目标放置完成。

`initial_state.py` 先核对材料坐标、面索引与视觉支撑表，在首次物理步进前设置一次选定位置和零速度，保留材料静长并保存独立 `selected_initial_state.npz`。由于原记录没有完整动力学状态，本次是**从选定形状开始的新物理运行**，不是原轨迹续接。源快照内容哈希、帧号及初始速度必须与独立稳定性运行一致。

高抬试验 `gathered_robot_v9` 使用 [`blanket_flatten_gathered_peel_robot.yaml`](../../../configs/blanket_flatten_gathered_peel_robot.yaml)，布边抬升 160 mm、悬垂 0.6 s、搜索范围 240 mm，并循环处理各端。三次抓放后覆盖率 73.2%，第四次回落到 67.8%，随后因剩余角点受工作区限制而在完整物理外步边界中止；末态覆盖率 68.0%，无活动抓持。三路各 1199 帧 / 10 fps / 119.9 s，完整解码通过：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/wrist.mp4)。2425 个保存帧未检出自交，臂部离散复核最小净空 70.74 mm。它同样未完成展平。

`gathered_robot_v10` 使用 [`blanket_flatten_gathered_crosswise_robot.yaml`](../../../configs/blanket_flatten_gathered_crosswise_robot.yaml)，目标中心 `[-0.15, 0] m`、平铺方向 90°，四角水平半径 0.347 / 0.714 m；旧目标为 0.292 / 0.797 m。跨侧搬运的直线路径若进入底座附近禁区，会经过前侧通道。静态端点与 104 姿态绕行检查分别最大误差 0.456 / 0.215 mm，但实际展开仍失败：八次均触发保护释放，180.235 s 时因持续拉伸与重复释放主动中止；末态覆盖率 45.4%、最高点 60.09 mm、95 分位高度 44.77 mm、材料边长比 1.26378，均未达到展平要求。峰值材料边长比 1.29754，未超过 1.30 硬上限；未出现非有限位置、桌外粒子或穿桌。3606 个保存帧未检出自交。详情见[执行报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/report.json)和[本次结果记录](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_study/result.md)。该版未通过最终自由静置验收，也不计为完整成功 demo。

v10 的三路采样诊断也已完成：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/wrist.mp4)。每路 359 帧、2 fps、179.5 s，覆盖动作前一秒至停止时刻，完整解码、同步及哈希核验通过；粒子和关节回读误差为 0，臂部离散复核最小净空 124.80 mm。它是失败诊断，低帧率也不适合判断快速瞬间的接触细节；原始 20 fps 状态轨迹仍完整保留。

本次已完成所选初态的独立稳定性验证，并保留实际动作诊断；**仍未生成成功的复杂初态完整展平 demo**。后续需要单独解决解扭、覆盖层打开与释放前拉伸控制。相关自动检查共 34 项测试、142 个子检查通过，不能替代实际任务成功。

各版视频分别由同一次实测粒子及全部关节状态重渲染，渲染不推进物理。源轨迹 20 fps，v8 / v9 视频规则采样为 10 fps，v10 为 2 fps，均保留末帧并覆盖整段执行时间。归档要求完整动作通过、松手后的终态稳定、独立初态稳定性一致、逐帧自交检查完整、臂部复核通过、画面复核通过，以及三视角解码与同步通过。成功视频只写入 `demos/blanket_flatten/{agentview,front_oblique,wrist}/`，其他证据写入 `runs/demo_metadata/blanket_flatten/`；本次未覆盖既有简单初态的成功副本。
