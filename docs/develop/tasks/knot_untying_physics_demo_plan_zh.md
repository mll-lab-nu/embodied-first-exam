# 单结物理验收与三视角全过程 demo 计划

状态：已完成并归档 75 s、五路同步视角的完整实验机器人解结。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。按用户要求，不设独立的数学可解性证明阶段。

[完整录像播放](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)。最新录制进展见 [机器人抓持与录制复测](knot_untying_recording_attempt_zh.md)。上一轮的 `trefoil_initial/preview.mp4` 是初态预览，不覆盖抓取、解结和释放。

## 本轮结果

候选配置的 [验收页面](../../../runs/environment-stability/knot_untying/trefoil_v1_eps1mm/index.html) 与 [汇总 JSON](../../../runs/environment-stability/knot_untying/trefoil_v1_eps1mm/result.json) 已生成。P1–P3 的 16 个独立实验累计模拟 209 s，检查 191,200 个 IPC 子步：全部收敛，未检出表面穿越、四面体反转或超限桌面穿透。局部实验通过，但网格加密后的关键状态差异超限，因此 P3 整体失败。

| 阶段 | 实际结果 | 主要证据 |
| --- | --- | --- |
| P1 | 通过 | 3 次独立 10 s 静置，最后 2 s 最大材料点漂移均小于 0.670 mm，低于 2 mm 门槛 |
| P2 | 通过 | 交叉接触阻挡、往返滑动、抬起落回和三轮送绳均通过；实际切向滑动 25.42 mm，释放后观察 5 s |
| P3 | 未通过 | 半步长、更严求解容差和 4 个小扰动通过；网格加密对照失败，详见下表 |
| P4 | 通用交接未通过验收 | 本次完整解结中的两处实体抓取、辅助抓持、释放与自由静置检查通过；通用双手交接尚未验收 |
| 同步全过程录像 | 本次完整轨迹通过 | 75 s、四路 ALOHA 相机加近景；末态及释放后观察窗无交叉，视频已独立归档 |

网格对照按相同物理时间和初始材料弧长对齐，保留原定 RMS < 2 mm、最大差 < 5 mm 的阈值：

| 对照 | 末态 RMS 差 | 末态最大差 | 所有关键状态的最大差 |
| --- | --- | --- | --- |
| 自由静置：基线 / 加密 | 2.350 mm | 8.015 mm | 8.015 mm |
| 送绳释放：基线 / 加密 | 2.691 mm | 8.149 mm | 9.860 mm |

[差异图](../../../runs/environment-stability/knot_untying/trefoil_v1_eps1mm/refinement_comparison.png) 显示最大差异位于自由尾端，但送绳末态去掉两端各 180 mm 后，结区 RMS 仍为 2.119 mm；不能用忽略尾端来声明通过。P3 后续需定位空间离散和自由尾端接触对结果的影响，修正后重跑受影响矩阵。机器人接近、关节轴接口和接触判定已修正，新的单手及双手运行均未出现局部单元翻转；当前录像尝试需完成自由端的抽出。冻结的物理验收门槛不变。

## 实施入口与证据

已接入任务专属逐子步诊断、原生 IPC 速度读取、独立表面 CCD、原生求解收敛日志与加载/释放夹具。
原始参数与接入试跑保留在 [原始配置页面](../../../runs/environment-stability/knot_untying/trefoil_v1/index.html)，候选配置结果见上方本轮报告。
每次实验独立保存配置、网格哈希、阈值、轨迹与报告。页面的 `not_run` 不计为通过。

```bash
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-fem-validation.txt
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_physics tests.check_knot_untying
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --friction-eps 0.001 --seconds 10 --extend-to 30 \
  --output runs/environment-stability/knot_untying/trefoil_repeat_eps1mm/free_settle_0
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --friction-eps 0.001 --mode contact_slide --seconds 15 \
  --output runs/environment-stability/knot_untying/trefoil_repeat_eps1mm/contact_slide_0
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --friction-eps 0.001 --mode lift_release --seconds 14 \
  --output runs/environment-stability/knot_untying/trefoil_repeat_eps1mm/lift_release_0
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --friction-eps 0.001 --mode feed_release --seconds 20 \
  --output runs/environment-stability/knot_untying/trefoil_repeat_eps1mm/feed_release_0
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --friction-eps 0.001 --mode robot_grasp --seconds 48 \
  --output runs/environment-stability/knot_untying/trefoil_repeat_eps1mm/robot_grasp
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_review \
  runs/environment-stability/knot_untying/trefoil_v1_eps1mm
```

`trefoil_repeat_eps1mm` 是单项复跑的新目录示例；已有完整报告不能覆盖。机器人入口现使用有界 IK 与关节空间接近路径，单手短程抓持复测已通过，P4 双手交接仍未通过验收。

`--extend-to` 在同一次连续 rollout 中延长静置，不重置节点、速度或参考态。
P3 使用 `--dt 0.0025`、`--refined`、`--tighter`；扰动使用 `--x-offset` 与 `--yaw`。
实际动作按物理时间取值。局部软目标记录被约束的材料点、释放时刻及跟随误差，不能计为 P4。

实现时发现的接口问题：

- Genesis 的 IPC FEM 状态回传只更新位置；稳定性速度改为通过 libuipc 原生 CUDA buffer accessor 读取。
- pyuipc 与 ipctk 的 pybind 枚举注册冲突，因此独立 CCD 在仅加载 ipctk 的 CPU 子进程中执行。
- ALOHA 默认碰撞网格简化使四个指爪凸包出现缺口；该任务的 ALOHA 配置显式关闭机器人网格简化，并复查闭合性。机器人碰撞保持开启，完整耦合与抓持仍需验收。
- 原始 IPC `contact/eps_velocity=0.01 m/s`，10 s 静置末期漂移 3.157 mm，超过 2 mm 门槛。候选配置改为 `0.001 m/s` 后，三次独立 10 s 静置均通过，最大漂移 0.669 mm。材料与验收阈值不变；原始实验独立保留，候选配置尚未替换默认预览配置。[IPC 摩擦模型](https://ipc-sim.github.io/file/IPC-paper-fullRes.pdf) 第 5.3 节说明该参数控制静摩擦近似的平滑速度区间。

长时矩阵可用 `physics_suite` 串行执行，避免 GPU 显存不足；遇到失败关卡会停止，保留原始记录。
新参数必须使用新的输出根目录；恢复同一矩阵时只复用完整且通过的报告。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_suite \
  --friction-eps 0.001 --through P3 \
  --output runs/environment-stability/knot_untying/trefoil_v1_eps1mm
```

该入口覆盖局部 P1–P3；没有将机器人单步接入试跑计作 P4，也不会据此自动宣称全过程 demo 通过。

## 当前证据与验收边界

[初态预览记录](../../../runs/environment_bootstrap/knot_untying/trefoil_initial/inspection_report.json) 只运行了 0.2 s：无反转四面体，末态三个交叉及上下关系正确，但最大顶点位移为 37.27 mm。该记录仅用于建场检查；长时和加载证据以本轮独立验收报告为准。

绳为 8 mm 直径的 FEM 体，总长约 1.074 m；直绳参考态、正常重力、两端自由。初态及末态的中心线间距检查不能代替实际变形表面的碰撞检查。`contact_d_hat=0.8 mm` 是接触势垒作用距离，不是允许穿透深度。

验收针对声明的材料、网格、求解器和动作速度范围。通过后表示这套仿真配置可用于当前 demo，不宣称真实编织绳材料已标定或所有结型都稳定。[IPC 原始方法](https://ipc-sim.github.io/) 将动力学精度与接触几何精度分开处理；本项目的接口、有限迭代预算和抓持耦合仍须实测。

## 1. 先补齐诊断与固定实验条件

每个实验在运行前保存 `validation_spec.json`，包含阈值、动作时间表、材料参数、实际网格哈希、dt / 子步、接触参数、求解迭代预算和抓持模型。初轮先用 1 s 无渲染试跑估算耗时；完整验收先不录高分辨率视频。

记录实际物理状态：

- 每个物理子步的有限值检查、速度、四面体相对参考态的体积比 `J=det(F)`、反转和退化单元。
- 材料坐标对齐的中心线、弧长与局部轴向伸长；结区形状、自由端位置、末期漂移。
- 实际 FEM 边界面的自接触、桌面及夹爪接触；相邻共顶点面按网格邻接排除，不能按空间距离随意跳过接触候选。
- 自接触的连续碰撞信息、交叉滑动方向、求解收敛 / 迭代上限事件。输出视频帧之间也可能发生错误，录制频率不作为物理检查频率。
- 抓持开关、被约束的材料段、实际夹爪位姿、目标跟随误差；力或冲量只在后端确实提供时记录，不能用目标轨迹冒充接触力。

如果后端不暴露逐子步状态或连续碰撞信息，先接出诊断接口，或在最小接触片段上增加独立表面扫掠检查；缺失的证据不能写成通过。中心线距离和投影交叉数保留为辅助观察。

加一个隔离的检测器反例：向诊断函数提供已知相交的表面与反转单元，确认它会拒绝；不会把人为破坏后的数据用于正式物理或视频。正常运行期间不清零速度、不写回绳顶点、不切换参考态、不临时关闭碰撞。

## 2. 分级物理实验

| 顺序 | 实验 | 动作与时长 | 主要验收内容 |
| --- | --- | --- | --- |
| P1 | 自由静置 | 正常重力下运行 10 s；若末期仍在松弛，则延长至 30 s；基线独立重建 3 次 | 有限状态、无表面自穿越 / 单元反转；末期速度与漂移降低到阈值；保留可操作的单结与自由端 |
| P2a | 交叉接触滑动 | 单独构造两段同材质绳的交叉接触，施加有界加载，往返切向滑动 30 mm，随后卸载 | 接触能阻挡法向穿过，又允许切向滑动；停动后不振荡发散，不能把一动不动的数值锁死当成稳定 |
| P2b | 抬起—落回—释放 | 夹持一个尾端，抬升 30 mm，平移 30 mm，放回并释放；运动约 3–5 s，释放后观察 5 s | 抓持附近不撕裂、异常拉长或翻转；绳与桌面接触正确；释放后没有残余固定点 |
| P2c | 两点持绳、送绳与卸载 | 一点保持，另一点缓慢送绳 / 扩圈 10–30 mm，回撤，再依次释放；重复 3 个循环 | 自接触能够重排；松结不会因数值黏连完全卡死；抓点切换与释放不注入异常能量 |
| P3 | 时间步、空间分辨率与求解精度对照 | 重做静置及 P2 中接触最密集的片段；同一物理时长和连续控制轨迹 | 接触合法性与动作结果一致，关键形状和载荷指标没有随数值精度发生实质性变化 |
| P4 | 实际机器人抓持 | 在拟用于 demo 的机器人上做抓取、持绳、交接、释放，覆盖计划用到的每个抓持段 | 夹爪实体、绳、桌面和双臂互碰均有效；没有用虚拟夹持点跳过真实机器人交互 |

P2 的局部测试可先用可见测试夹具或显式软抓持目标驱动，用来隔离绳模型；P4 必须接真实场景中的机器人。局部夹具通过，不直接认证机器人全过程。

若自由端在长时静置中沿合法通路自行退出，记为“初始化未保留任务”，而非数值爆炸。应通过真实的低速准备 / 轻预紧过程得到较稳定的松结初态，保存准备轨迹与物理状态，再重跑 P1；不加隐藏固定点维持结。可以调整初始松紧，不能把结形改为无应力参考态。

## 3. 首版候选阈值

以下是本任务的工程验收阈值，并非材料标准。已在第一批验收前冻结并保存于每次实验的 `validation_spec.json`；如果修改，保留旧实验及修改依据，重新验证相关项目。

| 指标 | 首版要求 |
| --- | --- |
| 状态 / 单元 / 接触 | NaN / Inf、四面体反转、确认的非相邻表面穿越均为 0；正常实验不得持续触及求解迭代上限 |
| 近退化单元 | `min J > 0.2`，同时保存 J 分布；这是温和载荷范围的网格质量门槛，不用于模拟压溃 |
| 桌面穿透测量 | 几何容差候选 0.05 mm；超过即失败；容差不豁免确认的穿越事件 |
| 静置末期 | 最后 2 s 顶点 RMS 速度 < 1 mm/s、最大速度 < 5 mm/s；材料点最大净漂移 < 2 mm |
| 轴向伸长 | 静置总弧长变化 < 2%，温和加载片段 < 5%；另查局部轴向伸长分布，候选上限 20%，防止总长掩盖局部撕长 |
| 松手后的行为 | 抓持约束完全解除；5 s 内回到上述静置阈值，无持续增大的速度 / 机械能趋势；不要求回到原来的结形 |
| 步长减半 / 网格加密 | 同一材料坐标的关键停留态中心线 RMS 差 < 2 mm、最大差 < 5 mm；阻挡 / 滑动 / 松手结果一致 |
| 载荷对照 | 若实际力可用，比较低通后的力与接触冲量，候选相对差 < 20%；近零量采用单独绝对容差，不比较无意义的相对误差 |

P3 的初始对照：

- 时间步：`dt=0.005, substeps=4` 对 `dt=0.0025, substeps=4`，实际接触子步由 1.25 ms 降为 0.625 ms。控制轨迹按物理时间取值，不能按步号复制导致速度变化。
- 空间分辨率：轴向间距 2.5 → 1.75 mm、圆周 12 → 16 段、四面体最大体积 2e-8 → 1e-8 m³。物理几何、E、ν、ρ、摩擦与接触作用距离保持一致，并重查网格自身接触间距。
- 求解预算：关键片段将 Newton 上限 100 → 200、容差 0.01 → 0.005；若原预算未收敛，则修正基线并重跑，而非只因画面可看就通过。

最后补 4 个小扰动实例：x 偏移 ±5 mm、平面角度 ±5°。它们用于检查轻微装配变化，不扩大到未知结型。当前右手结先通过；镜像左手结单独登记结果。

## 4. 通过物理验收后制作全过程

建议采用“放松结区 → 撑开通路 → 自由端退穿一次 → 展开 → 松手”的脚本状态机。普通 overhand 的系法包含成圈和尾端穿圈，可以据此反向构造当前松结的候选解法：[Animated Knots 原始演示](https://www.animatedknots.com/overhand-knot)。这是动作设计依据；每段仍由物理仿真实际执行。

机器人优先复用仓库现有 ALOHA 双臂，一只手稳定局部绳段，另一只手送绳 / 抽端；需要交接时显式换抓点。[SGTM 2.0](https://arxiv.org/abs/2209.13706) 提供了双臂处理 overhand 结的研究先例，但这里首版只做已知状态的固定实例脚本，不实现其完整感知系统。

初态预览默认仍是单 Panda。物理探针已接入通用机器人初始化器和 ALOHA 控制器，保留夹爪、桌面和双臂碰撞，并检查实际 IPC 刚体表面与绳的连续碰撞。P4 接近阶段的 IK 限位错误已修正，后续修复关节轴及接触判定的 18 s 抓持复测已通过，完整双手交接集成仍未通过验收。

| 阶段 | 实际动作 | 进入下一阶段的观察条件 |
| --- | --- | --- |
| 0 | 经验证的准备与松弛；机器人接近 | 初态满足 P1，双方抓点可达且未碰绳 |
| 1 | 一手抓住支撑段，另一手靠近自由端 | 接触与闭爪已发生，材料段选择正确 |
| 2 | 沿局部绳方向送入少量余量，打开绳圈 | 所需通路出现，绳与夹爪扫掠包络有真实净空 |
| 3 | 工作端沿逆系结方向退出绳圈，必要时交接 | 尾端确实越过目标圈口，相关自接触顺序改变，过程没有自穿越 |
| 4 | 继续抽出余绳并整理成开放曲线 | 结区完全散开；在多个观察方向及实际中心线中核对剩余绕缠 |
| 5 | 放回桌面，双手松开、退出，继续模拟 5 s | 无剩余抓持约束；绳处于无结状态，满足释放后稳定性要求 |

每段初始速度候选 10–20 mm/s，采用平滑加减速，并以接触、局部伸长、抓持误差等反馈决定推进 / 暂停。可达性失败、夹爪碰撞和轨迹错误归为控制问题，不因此改变绳材料参数。

先沿用项目已声明的辅助抓持约定：只有实体夹爪接触并闭合后才启用 FEM 软抓持；目标跟随实测末端位姿，开爪即解除，报告明确标为 `assisted_grasp`。这不等于纯摩擦夹持验收。现有 `FEMRopeAttachment` 仅支持平移；本任务的机器人探针已实现预声明材料段及完整位姿跟随，最新短程试跑实际完成接触抓持、抬升和释放；双手旋转与交接尚未完成验证。

夹爪不能默认穿过只有绳能通过的缝隙。如果净空不足，先物理扩圈，或送出尾端再换手接取。绳的运动始终由接触、弹性和显式抓持作用产生，禁止逐帧改写节点完成解结。

初轮完整执行包含所有接触诊断，以相同动作验证基线和半步长。全过程通过后，用同一配置录制四路 ALOHA 标准相机及近景；录制运行也保留物理检查，不能把先前成功的状态序列硬写成动画。

## 5. 三视角录制与交付

按当前 [项目归档规则](../../../AGENTS.md)，ALOHA 保留四路标准相机，并补充绳结近景：

| 相机 | 绳结任务中的作用 |
| --- | --- |
| `cam_high` | 固定的较高外部视角，观察双臂和整段绳 |
| `cam_low` | 固定的侧前视角，观察抬升、绳段上下关系与桌面接触 |
| `cam_left_wrist` / `cam_right_wrist` | 分别随左右腕运动，观察对应夹持段，运行中不切换所挂的手 |
| `detail` | 绳结尺度的固定斜上方近景，补足标准相机中绳太小的问题 |

五路来自同一次连续 rollout，使用同一组物理时间戳；每次先完成状态步进，再一次性采集全部相机，采集之间不推进仿真。正式录制建议 20 fps，对应 5 ms 控制步每 10 步采一帧，半步长每 20 步采一帧；当前诊断录像为 10 fps、640 × 360。所有相机保存内外参与腕部安装变换。

交付五个独立 MP4、同步播放 / 暂停 / 关键阶段跳转的网页，以及逐帧时间和阶段索引。物理过程视频覆盖抓取、送绳、退穿、展开、松手和最后静置；相机环绕只保留在现有初态预览中。关键退穿段至少在一个外部视角持续可见。

完整 demo 的视频归档统一放在 `runs/demos/knot_untying/`，按 `<date>_<run_id>_<camera>.mp4` 命名。依照 [项目归档规则](../../../AGENTS.md)，该目录只保存独立 MP4 文件；播放页、报告、相机标定、轨迹与归档清单放在 `runs/demo_metadata/knot_untying/<date>_<run_id>/`。本轮完整实验录像已独立归档，见上方完整录像链接；P3 与通用交接验收状态不变。

产物目录：

```text
runs/environment-stability/knot_untying/trefoil_v1/
  validation_spec.json
  free_settle/  contact_slide/  lift_release/  feed_release/
  half_step/  refined_mesh/  tighter_solver/  robot_grasp/  perturbations/
  result.json  index.html
runs/demos/knot_untying/
  <date>_trefoil_untying_v1_cam_high.mp4
  <date>_trefoil_untying_v1_cam_low.mp4
  <date>_trefoil_untying_v1_cam_left_wrist.mp4
  <date>_trefoil_untying_v1_cam_right_wrist.mp4
  <date>_trefoil_untying_v1_detail.mp4
runs/demo_metadata/knot_untying/<date>_trefoil_untying_v1/
  camera_rig.json  frames.json  trajectory.npz  report.json  index.html
  archive_manifest.json
```

归档时复制视频与配套证据，记录原始目录和 SHA-256，核对视频可解码、各路帧数与时长一致、页面链接有效，并更新 `runs/demo_metadata/` 的 `index.html`、`README.md` 和 `catalog.json`。

## 实施顺序

1. 新增任务专属 `diagnostics.py` 与无渲染 `physics_probe.py`，先把 P1 和 P2 跑通。
2. 完成 P3、小扰动复查和基线汇总；物理异常定位到材料、初态、网格或求解器，不在调 demo 时混改。
3. 接入 ALOHA 与显式抓持，完成 P4；再用 `oracle.py` 组织动作状态机，`execute.py` 连续执行，按真实状态转阶段。
4. 全过程和半步长复核通过后，输出四路 ALOHA 标准相机及近景的同步 demo 与 `review.py` 页面，登记实际通过范围。

完整验收状态以运行汇总为准。本轮已完成诊断和局部 P1–P3 实验；P3 网格对照及 P4 抓持验收仍未通过，当前完整解结试录仅用于实验，不能据此宣称 P3 或双手交接通过；正式物理验收仍需完成这两项。
