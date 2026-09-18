# Cast Coil 基础场景

2026-09-17：当前 3 倍原型的完整双臂物理 demo 已通过验收并归档。
[打开五视角播放页](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/index.html)，
MP4 独立副本位于 [`runs/demos/cast_coil/`](../../../runs/demos/cast_coil/)。
这是预抓取起点、接触后辅助抓持的三段原型解法；完整执行包含解除辅助、撤手和自由静置，不宣称复现商业谜题官方八步。

本次接续已有 `configs/task_cards/cast_coil.yaml`，新增几何、资产导出、共享桌面场景和检查入口。
此前参数卡中的精确资产与初态均为空，没有可以继续使用的 Cast Coil 场景实现。

## 参考与范围

[Hanayama](https://hanayama-toys.com/product/cast-coil/) 将该谜题描述为两个近似同形的卷绕件，通过滑动和旋转分开。
[官方商店](https://store.hanayamatoys.co.jp/items/55630234) 有装配和分离照片；
[官方分解示意](https://www.eureka-puzzle.eu/wp-content/uploads/2022/09/515056-Huzzle-Cast-Coil-Oct-2017.pdf) 提供滑转顺序，但没有尺寸或连续位姿。

当前 `cast_coil_photo_prototype_v1` 保留方形回折、交替四层、中央通孔、侧边跨层连接和内侧凹口。
尺寸、槽位与桥接形状为照片推断，矩形缺口尚不能代替精确圆弧转动窗口。
这是一套可加载、可检查的基础原型，尚不承诺实物解法可执行。

## 实现

- `topogym/tasks/cast_coil/geometry.py`：参数校验、正交实体布尔构造、网格和碰撞体、质量惯量、资产导出。
- `topogym/tasks/cast_coil/scene.py`：两个 6 自由度单 link 刚体，载入共享 Nyx / compact_lab 场景。
- `configs/cast_coil_preview.yaml`：3 倍原型，固定初始装配和四个检查相机；机器人只作尺度参照。
- `topogym/tasks/cast_coil/demo.py`：装配图、背面图、全景、拆件检查图、相机绕行视频和可选落桌检查。
- `topogym/tasks/cast_coil/verification.py`：连续几何路径证书、错误路径和截面变化对照。
- `topogym/tasks/cast_coil/physics_probe.py`：真实刚体步进的静置、有限受力及撤去驱动检查。
- `topogym/tasks/cast_coil/qualify.py`：两个时间步的证据汇总、失败解释、变体配置与审查页。
- `topogym/tasks/cast_coil/solvability.py`：当前原型完整解法的复核、解析桌面余量和交互说明页。

坐标约定：x/z 是方形正面，y 是四层排列方向；布局 yaw 绕世界 z 轴。
桌面高度由共享环境读取，底面距离桌面 0.5 mm。初始无穿透检查在装配坐标系做精确盒间计算，布局为整体刚性变换。
局部接触采用显式 13 / 15 个盒体，避免整件凸包填孔。视觉和碰撞使用同一正交实体，未用装饰网格遮掩碰撞轮廓。

## 运行

在仓库根目录执行：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.cast_coil
```

默认生成 `runs/environment_bootstrap/cast_coil/assembly_initial/index.html`，并运行 0.5 秒自由落桌检查。
用 `run.settle_seconds=0` 只展示初态；`run.record_video=false` 跳过绕行视频。
CPU 环境可显式选择光栅渲染：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.cast_coil \
  env.genesis.backend=cpu env.renderer.type=rasterizer run.record_video=false
```

相机视频期间没有物理步进或零件位姿修改。拆件检查图是显式重置后的独立展示，保存图片后恢复装配位姿并清零速度，再进行落桌检查；不能据此判定拆解成功。
落桌期间只有重力、桌面及件间接触，不重设零件位姿。

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_cast_coil tests.check_configs_compose tests.check_task_baseline_catalog tests.check_project_layout
.venv-gs121-nyx/bin/python -m scripts.build_bootstrap_review
```

检查覆盖：单件连通和封闭、中央孔与局部缺口、桥接连续性、初态间隙、错误重叠、退化参数、无重复体积的质量惯量缩放、URDF 分块和配置一致性。
报告独立记录原型几何检查、自由落桌检查、实际求解器参数；参数卡仍保持 `unqualified`。

2026-09-16 的默认 CUDA / Nyx 运行已生成装配正反面、全景、拆件检查图及 6 秒 / 120 帧视频。
14 项相关回归检查通过；0.5 秒落桌检查的最大接触穿透约 0.021 mm，最大质心位移约 0.520 mm（包含初始 0.5 mm 下落），姿态保持稳定。
实际数值和检查阈值见 [场景报告](../../../runs/environment_bootstrap/cast_coil/assembly_initial/inspection_report.json)，
图片和视频见 [检查页面](../../../runs/environment_bootstrap/cast_coil/assembly_initial/index.html)。

商业实物复现仍需要实测槽口 / 可靠 CAD，恢复准确圆弧和倒角，并核验官方滑转顺序及应通 / 应阻对照。
现有原型的双臂执行入口与验证范围见下文“完整双臂物理执行与录制”。

## 物理可靠性与可解性审查

入口为 `topogym/tasks/cast_coil/qualify.py`，产物在
[`runs/environment-solvability/cast_coil/photo_reference_v1/`](../../../runs/environment-solvability/cast_coil/photo_reference_v1/index.html)。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.qualify --run-physics
```

不加 `--run-physics` 时，只重新生成几何证书并汇总已有报告，不补算或假定缺失的物理检查通过。
默认时间步为 1 ms / 4 substeps；对照为 0.5 ms / 4 substeps，两者均运行 8.5 秒，保持摩擦、求解迭代及控制器相同。

每份物理检查包括 15 项：三个实例分别自由静置和完整原型路径、两个方向允许滑动、六个方向受阻强拉，以及反向转动负对照。
静置时两件均自由且受重力。运动台架显式固定金件，银件为六自由度刚体，补偿重力并接受有界外力 / 力矩，结束后撤去驱动力；没有机器人、焊接抓取或运动件位姿覆写。
力上限 60 N、力矩上限 3 Nm。接触穿透和实际位姿下的 OBB 相交分别检查，防止只看目标轨迹或只看求解器接触记录。
路径跟踪及撤去驱动后的保持窗口要求位置误差小于 0.5 mm、姿态误差小于 0.01 rad，最终分离面间距大于 10 mm。
受阻检查同时要求触发接触、目标未能到达、停止位置与姿态符合预设；受力偏转导致这一判据失败时，不等于发生穿模。
半时间步比较另要求最终相对位置差小于 0.5 mm、姿态差小于 0.01 rad，且两轮各自检查均通过。
报告还由 25 ms 的物理位姿采样计算撤去驱动后的角速率，避免把质心停稳误读为刚体已完全静止；该差分不是瞬时角速度的上界。

默认控制器使用相同的 6000 N/m 位置刚度、190 Ns/m 阻尼、30 Nm/rad 姿态刚度和 1 Nms/rad 姿态阻尼。
缩放会改变闭环表现：2 倍实例相对 3 倍实例的质量为 `(2/3)^3`，转动惯量为 `(2/3)^5`。
因此几何相似并不能保证相同控制增益、时间步下也可靠；需查看每个实例的实测状态。

几何检查发现当前原型有一条三段路径：先左移 7.25 mm，绕局部 y 轴、轴心 `(1.5, 0, -10.5) mm` 转 −90°，再右移到完全分离。以上数值是缩放前的原型坐标。
此路径使用完整分块碰撞体，SAT 分离轴检查配合材料点位移上界对整段轨迹做自适应认证，而不是只检查关键帧。
反方向转动和六条直接拉出路径作为负对照；基于几何的拒绝并不构成“无任何其他解法”的证明。

这条路径与官方八步示意不同。官方图没有毫米尺寸、转轴位置或连续位姿；因此当前只能证明**本地原型**的路径，不宣称复现官方教程，也不据较短路径断言实物有同样解法或设计错误。
单臂 demo 的默认机位为 `agentview / wrist / front_oblique`。发布“官方解法复现”demo 仍需验证官方路线及机器人执行；
当前原型的三段解法可以独立录制，但必须明确其范围。台架力控和位姿回放不充当机器人执行。

### 变体

维护的预设见 [`variants.json`](../../../assets/tasks/cast_coil/photo_reference_v1/variants.json)：

| 预设 | 倍率 | 桌面 yaw | 几何变化 |
| --- | --- | --- | --- |
| `baseline_3x` | 3 | −12° | 原基线 |
| `rotated_30deg` | 3 | 30° | 整体旋转 |
| `compact_2x` | 2 | −12° | 等比例缩放；质量和惯量同步变化 |

以上均为可复现候选配置，列出配置不表示通过验收。
每个实例的连续几何、受力台架与时间步对照状态独立记录在 `result.json` 中；完整报告不能由两项试跑代替，缓存资产与当前模板不一致时拒绝通过。
未提供槽口、截面或圈数的“可靠难度范围”，因为这些变化会重新定义解锁路径。
已额外检查截面宽从 7 mm 增至 7.5 / 8 / 9 mm 的三个候选，并相应缩短侧桥以保留合法初态。
三者初态都通过，但现有 −90° 转动路径分别出现碰撞；这些候选不作为已验证变体发布，也不宣称不存在别的解法。
检查入口导出可直接运行的配置，例如：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.cast_coil \
  --config-path /home/jianwen/topogym/runs/environment-solvability/cast_coil/photo_reference_v1/variants \
  --config-name compact_2x
```

该命令仍是初态预览，不是官方解法演示。

### 2026-09-16 实测结论

两轮均完成 8.5 秒仿真，共 25,500 次物理步进；默认时间步通过 12 / 15 项，半时间步通过 13 / 15 项。
22 项相关代码回归检查通过。代码检查与物理验收分别统计。

| 实例 | 连续几何路径 | 1 ms 静置及路径 | 0.5 ms 静置及路径 | 时间步对照 |
| --- | --- | --- | --- | --- |
| `baseline_3x` | 通过 | 通过 | 通过 | 通过 |
| `rotated_30deg` | 通过 | 通过 | 通过 | 通过 |
| `compact_2x` | 通过 | 路径未通过 | 通过 | 未通过 |

默认 3 倍实例的完整路径两轮均没有观察到接触穿透；最大位置偏差分别约 0.164 / 0.096 mm，
最终分离面间距约 78 mm，两轮最终相对位置差约 0.0049 mm。
这些结果证明本地原型路径可在明确的台架条件下执行，不等于官方八步或机器人抓持通过。

2 倍实例在 1 ms 下出现姿态振荡，撤去驱动后末段采样角速率约 5.16 rad/s，
全观察窗口最大姿态偏差约 143.8°；0.5 ms 下路径通过。该实例对控制周期敏感，不列为跨时间步可靠变体。
相同控制增益与缩小后的惯量不匹配是后续需要处理的因素；本轮保留原参数及失败证据，没有放宽阈值。

两个 z 方向受阻检查在两轮均因姿态偏转及停止位置超出预设范围而失败；接触检查本身通过，不能把它们称为穿模。
反向转动在两轮都被阻挡，但撤去驱动后最终位置相差约 1.281 mm、姿态相差约 1.162°，超过时间步一致性阈值。
因此完整台架验收及整体时间步对照均未通过。

这轮台架审查的结果为 `formal_demo_qualified=false`、`formal_demo_generated=false`。
该轮未生成正式拆解视频；精确转动窗口、官方八步路径及纯摩擦抓持仍待验证。

### 完整 demo 归档

完整机器人 demo 生成后，视频副本统一保存到 `runs/demos/cast_coil/`，文件名使用
`<date>_<run_id>_<camera>.mp4`；ALOHA 保留同一次完整执行的
`cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路同步视频，并补充 `front_oblique` 近景。
播放页、报告、配置、状态与资产放在 `runs/demo_metadata/cast_coil/<date>_<run_id>/`，按仓库 `AGENTS.md` 完成归档检查并更新总目录。

2026-09-16 时尚无可收录的完整 demo。另有[机械臂拆解尝试](../../../runs/environment-solvability/cast_coil/assembly_initial/index.html)，
其结果为 `success=false`：抓持滑移，零件尚未分离。该尝试及初态绕行视频保留在原实验目录，尚不创建完整 demo 的视频副本。

### 按官方指导进行的解法试验

入口 `topogym/tasks/cast_coil/official_trial.py` 把官方前四步解释为相对平移、固定轴 90° 转动、下移、固定轴 90° 翻转。
保持原 3 倍实体、金件固定、银件移动，未修改槽口、质量、惯量或碰撞体。
图示没有公制位姿；转轴和数值边界是本次明确记录的候选解释，不能当作厂家提供的 CAD 数据。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.official_trial \
  --output runs/environment-solvability/cast_coil/official_guided_new
```

首次试验保存在[官方指导解法试验页](../../../runs/environment-solvability/cast_coil/official_guided_v1/index.html)。
搜索包含初始滑动正反方向、面内转动正反方向、两种出平面翻转轴及其正反方向，每组使用 3 个随机种子，
共 48 次搜索；另加 4 次保留包围盒重叠余量的诊断搜索，总计 52 次。
位姿搜索采用分块 OBB 的分离轴检查，候选再经连续运动证书与 361 个采样位姿复核。

**没有找到通过条件的四步前缀。** 选定的诊断候选前三步连续几何证书通过，第 4 步翻转失败：
约转过 4.375° 时首次采样到相交，整段最深采样 SAT 间隙约 −1.347 mm（3 倍场景）。
独立 FCL 三角网格检查也确认相交。因此本次没有进入步骤 5–8、机器人执行或正式 demo 录制。

未限制过早退出时，搜索可以在第 3 步直接将银件完全移出，再在空中完成转动。
程序显式拒绝这种候选，不能用它充当官方八步复现。
提前分离判据采用坐标轴分离平面；通过该必要条件也不单独证明零件仍机械互锁。

这是有边界的固定转轴路径试验，不是所有连续运动的穷尽搜索，也不证明原型或商业谜题全局无解。
后续需要进一步核对图示的转轴映射、实际转动槽口，并考虑翻转过程中转轴变化的路径；不能仅凭此失败就任意削薄零件。

### 当前模型到底有没有解、怎么解

**当前原型有解。** 官方指导试验中某类前缀失败，与现有三段完整路径已通过检查并不矛盾。
新增的[完整解法说明与交互路径](../../../runs/environment-solvability/cast_coil/solvability_explanation_v1/index.html)
重新检查当前实体、默认预览实际导出的 URDF 碰撞盒、三段连接连续性和终点分离平面。
独立 FCL 三角网格复核 3,003 个采样位姿，未发生相交；连续性仍由 SAT / 材料点位移证书保证。
该页面是几何说明，不是物理录像，不计入正式 demo。

当前默认 3 倍模型的操作如下。所有坐标均为装配坐标系毫米，x / z 在方形正面、y 沿四层排列；
不是世界坐标，也不是 URDF 质心平移。金件固定，银件移动。

1. 保持两件相对初态一起抬高 **70 mm**，通过合适抓持或支撑维持金件。
2. 银件沿 −x 滑动 **21.75 mm**。
3. 绕经过 **(4.5, 0, −31.5) mm**、平行 y 的轴按右手规则转 **−90°**，不是绕自身质心转动。
   此时银件装配原点相对平移为 **(−27, 0, −57.75) mm**。
4. 保持姿态，沿 +x 再移 **207 mm** 到 **(180, 0, −57.75) mm**，最终分离面间距 **78 mm**。
   207 mm 是已验证路径的行程，并不宣称是最短解锁行程。

整体抬高是桌面约束的补充，不改变件间相对路径。对所有实体角点的旋转正弦曲线解析求极值发现，
转动约完成 84.26% 时最低点比初态底面低 **60.173 mm**；仅检查关键帧会漏掉这个极值。
默认初始离桌 0.5 mm，所以至少抬高 **59.673 mm** 才不穿桌，70 mm 留出 **10.327 mm** 几何余量。
此结论只检查水平桌面，不包含机器人可达性、夹爪或支撑物碰撞，也没有证明抬升抓持稳定。
若已自然落桌至零间隙，70 mm 抬升仍有约 9.827 mm 余量。

默认 1 ms / 半时间步 0.5 ms 的既有受力台架证据均支持这条完整路径，缓存碰撞盒已与当前模型核对一致。
这轮解法复核没有重跑物理步进；全套台架负对照及纯摩擦抓持仍有未通过项，不能把局部路径通过写成整体物理验收通过。

官方八步图是投影视图，图上的“向下 / 向右”不能直接等同于世界 z / x 轴。
当前矩形槽口、跨层桥接及银件额外凹口仍是工程假设；本地三段解不能证明商业实物存在同样捷径。
可以沿已知三段路径继续验证原型的真实抓持，但若目标是复现商业谜题，仍须校准槽口和官方转轴映射。

复核入口（使用新目录保留旧证据）：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.solvability \
  --output runs/environment-solvability/cast_coil/solvability_explanation_new
```

## 完整双臂物理执行与录制

已验收版本为 `2026-09-17_aloha_full`，原始录制为 `aloha_full_20260917_float64_v4`。
默认 2.5 ms / 半时间步 1.25 ms 两轮均完成 30.1025 秒物理执行，分别为 12,041 / 24,082 步，均为双精度、10 子步。
正式副本保留同一次运行的五路视频，各 603 帧、20 fps、30.15 秒；已完整解码并核对相机时间戳。

| 验收项 | 实测结果 |
| --- | --- |
| 最终两件分离面间距 | 默认 77.9452 mm；半时间步 77.9437 mm |
| 终态时间步一致性 | 最大位置差 0.001592 mm，最大姿态差 0.000001312 rad；通过 0.5 mm / 0.01 rad 门槛 |
| 件间 / 非抓持机器人 / 双臂接触穿透 | 两轮记录的最大值均为 0 |
| 默认运行的实际件间几何采样 | 最小 SAT 间隙 0.1936 mm；不是实际运动的连续几何证书 |
| 默认运行的桌面几何采样 | 最大穿入约 0.00130 mm，小于 0.15 mm 门槛 |
| 释放与撤手 | 两轮真实辅助约束列表均为空，最终无夹指接触，撤手期间零件未随手移动 |
| 默认运行的最终 0.5 秒静置窗口 | 最大线速度约 0.000295 mm/s、最大角速度约 0.00000548 rad/s |

完整报告、半时间步状态、执行源码快照、相机参数、资产和 SHA-256 清单均随视频独立保留在
[`runs/demo_metadata/cast_coil/2026-09-17_aloha_full/`](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/index.html)。
28 项相关回归检查通过。此次验收仅覆盖该原型、布局和辅助抓持流程，旧台架的未通过负对照及官方八步复现仍保留原结论。

`configs/cast_coil_aloha.yaml` 保留 3 倍原型几何、质量与惯量，将整体 yaw 调整为 90°、放在 ALOHA 双臂之间。
从两侧夹爪已张开的预抓取状态开始；左臂操作银件、右臂操作金件。不是从机器人 home 寻找抓取的策略。
流程覆盖闭合夹爪、整体抬升 70 mm、三段拆解、分别放置、解除辅助抓持、松爪、双臂撤回和 2 秒自由静置。

采用明确的辅助抓持：四个夹指在两件上分别形成双侧接触并持续 20 ms 后，启用两条 hand/body weld 约束。
约束只辅助抓持，零件仍由物理解算推进，没有执行期间的位姿覆写；放置后必须读取求解器确认约束全部清空。
这不证明纯摩擦抓持或真实 ALOHA 的硬件负载能力。控制增益为重型 3 倍原型重新设置，保留原模型力矩上限。

- `robot_plan.py`：连续原型路径证书、双臂 IK 和 10 Hz 的机器人 / 零件 / 桌面采样检查。
- `robot_demo.py`：关节控制、接触门控、实际刚体轨迹、每步接触检查、同步相机与释放验收。
- `robot_grasp.py`：逆注册顺序解除辅助约束，并读取求解器中的真实约束列表。
- `robot_archive.py`：终态与时间步对照、视频完整解码及帧数、独立副本和归档目录更新。

复现时使用新的输出目录，避免覆盖已有结果：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_plan \
  --output runs/environment-solvability/cast_coil/new_robot_plan.json
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_demo \
  --plan runs/environment-solvability/cast_coil/new_robot_plan.json \
  --output runs/environment-solvability/cast_coil/new_half_dt --dt 0.00125
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_demo \
  --plan runs/environment-solvability/cast_coil/new_robot_plan.json \
  --output runs/environment_bootstrap/cast_coil/new_aloha_full --record
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.robot_archive \
  --source runs/environment_bootstrap/cast_coil/new_aloha_full \
  --reference runs/environment-solvability/cast_coil/new_half_dt \
  --run-id NEW_DATE_NEW_RUN_ID
```

默认步长 2.5 ms、10 子步；对照步长 1.25 ms、仍为 10 子步。五路视频为
`cam_high / cam_low / cam_left_wrist / cam_right_wrist / front_oblique`，同一物理运行、20 fps。
ALOHA 四路为 960×540，补充近景为 960×720；低位相机为覆盖抬升动作额外上仰 20°，差异记录在 `camera_report.json`。
归档必须包含解除约束后的静置窗口、撤手时零件不跟随、实际约束为空和最终没有夹指接触的证据。
双臂配置启用求解器已有的 `noslip_iterations=5` 静摩擦修正，以抑制释放后桌面接触的缓慢数值滑移；
默认预览和旧台架的求解设置不变。零件摩擦系数仍为 0.35，几何、质量和惯量均未修改。
双臂执行同时使用 `precision="64"`。单精度的两个完整释放版本虽然都完成拆解，
默认 / 半时间步的最终位置最大差分别达到 0.687 / 0.712 mm，未通过 0.5 mm 的归档门槛；
开启静摩擦修正本身未解决这一问题。半时间步静置轨迹每 20 ms 出现固定 2.384 µm 的位置步进，
因此改用双精度检查数值量化的影响。旧运行的 `timestep_comparison.json` 保留失败对照，不作为验收通过的副本。
双精度版本将最终时间步位置差降至 0.001592 mm，按原阈值通过，无需放宽归档门槛。

### 多抓持约束释放的修正

视频复核发现早期完整拆解尝试中金件仍跟随撤回的手。当前安装的 Genesis 在删除非末尾动态 weld 时只移动
`eq_type`，未同步移动对象 ID 和约束数据；按添加顺序删除两条约束会留下第一条。
任务入口改为逆注册顺序删除，绕开该分支，并用 `get_weld_constraints` 确认真实清空；未修改求解器安装包。
还增加了撤手阶段每件位移必须小于 2 mm、终态无夹指接触的独立检查。
旧运行的原始报告保存在 `reported_result_before_release_review.json`，其 `result.json` 已标记释放验收失败，不进入完整 demo 归档。

## 从已解运动反推结构：三个完整变体 Demo

后续家族化规划见[三个 IK 家族与九个可见代表点](cast_coil_family_space_zh.md)，包含可区分的家族轮廓、对应机制尺寸及联合采样规则。九个新可见代表点已检查几何和双臂 IK，尚未替代本节的三个完整物理 Demo。

三个变体保留原版银件和抓持面，先改变已解相对运动，再在金件设计包络内添加材料、扣除带余量的运动扫掠体，最后重新求完整双臂 IK 并进行物理执行。
模板和生成阶段证据保存在 [`assets/tasks/cast_coil/inverse_variants_v1/`](../../../assets/tasks/cast_coil/inverse_variants_v1/README.md)，
可复现生成器为 `topogym.tasks.cast_coil.inverse_design`。

| 变体 | 实例实际运动 | 完整视频 |
| --- | --- | --- |
| `eccentric_turn` | 滑开 27.75 mm，转轴沿 x 偏移 3 mm，转动 90°，移出 207 mm | 30.15 秒，603 帧 |
| `split_turn_offset` | 滑开 21.75 mm，45° → z 向错位 6 mm → 绕移动后的轴再转 45°，移出 207 mm | 32.15 秒，643 帧 |
| `axial_screw_turn` | 滑开 21.75 mm，转动 90°同时沿 y 推进 6 mm，移出 207 mm | 30.15 秒，603 帧 |

方向均在零件局部坐标中；场景整体 yaw 为 90°。三者整体抬升 80 mm，均完成闭爪、解锁、分别落桌、解除辅助、松爪、撤手及 2 秒自由静置。
每个变体保留 ALOHA 四路加 `front_oblique`，共十五路新视频：

- 对照入口：[`runs/demo_metadata/cast_coil/2026-09-17_inverse_variants_v1/index.html`](../../../runs/demo_metadata/cast_coil/2026-09-17_inverse_variants_v1/index.html)。
- 独立 MP4：`runs/demos/cast_coil/2026-09-17_inverse_<kind>_<camera>.mp4`。
- 每个变体的独立证据和完整播放页：`runs/demo_metadata/cast_coil/2026-09-17_inverse_<kind>/`。

三个金件均为水密、单一连通组件，中央贯通孔宽 36 mm，外包络保持 102 × 74.25 × 102 mm。
最终金件分别由 16、24、97 个精确碰撞盒组成；同一实体用于显示、碰撞、质量和惯量计算，执行中不再改变几何。
第三个是正交阶梯通道，尚未验证平滑螺旋面或制造公差版本。

指定相对路径均通过连续 SAT 加材料点位移界证书，保守余量 60 μm。
原版三段路径和六个坐标轴正负方向的直拉均出现真实重叠见证；第三个的“先轴向推进 6 mm 再转动”也被阻挡。
这些测试说明变体改变了结构约束，但不证明路径唯一，也不证明商业 Cast Coil 的官方结构。

物理执行使用 CPU 双精度、2.5 ms 步长、10 子步；另以 1.25 ms 步长和相同子步数完整重跑。
两轮均保留碰撞、重力、质量惯量与机器人力矩上限，使用接触门控辅助抓持；真实释放后辅助约束列表为空，最终没有夹指接触。

| 实测指标 | 偏心转动 | 两段错位 | 旋转推进 |
| --- | --- | --- | --- |
| 默认实际轨迹的最小采样 SAT 间隙 | 0.1675 mm | 0.1547 mm | 0.2767 mm |
| 最终两件分离面间距 | 80.8939 mm | 77.8966 mm | 77.8727 mm |
| 两时间步终态最大位置差 | 0.003401 mm | 0.001609 mm | 0.000968 mm |
| 件间、非抓持机器人、双臂的最大接触穿透 | 0 | 0 | 0 |
| 夹指抓持接触最大数值穿透 | 0.3437 mm | 0.3438 mm | 0.3423 mm |

夹指接触单列，不将其混入非抓持碰撞的零值。实际状态的采样间隙不等同于对实际轨迹的连续证书；连续证书针对理想相对路径。
原始物理报告、独立审计轨迹、半时间步报告、源计划、结构生成负对照、源码和资产均随归档保留。

为避免完整物理解算与五路光追争用 GPU，物理执行中按 20 Hz 保存精确状态，再由 `render_physical_trace.py` 离线 Nyx 渲染。
它核对状态哈希、物理步号、终态释放和恢复后的位姿误差，不插值、不根据 IK 重新生成动作；渲染场景不做物理步进，也不分配动态实体的碰撞几何。
归档进一步将视频帧、相机时间戳与独立物理审计轨迹交叉核对。视频字幕与播放页均明确标注离线渲染及辅助抓持。
这仍是已完成物理执行的可视化证据，范围不包括纯摩擦抓持、真实硬件能力或其他物理后端。

35 项相关检查通过，包含新结构的连续路径、旧路径阻挡、变体中间步骤完整性、原始状态哈希及物理帧对应关系；五路视频还需分别完整解码、检查帧数和独立副本哈希后才允许归档。

## 基础版的三个单参数外观 Demo

按后续实验要求，以最初 `2026-09-17_aloha_full` 基础版为种子，分别只改变一个外观参数。
本轮不叠加上述三种运动反推结构，也不联合随机化参数。新模板位于
[`assets/tasks/cast_coil/appearance_single_v1/`](../../../assets/tasks/cast_coil/appearance_single_v1/README.md)，入口为 `topogym.tasks.cast_coil.appearance`。

| 实例 | 唯一外观参数变化 | 包络宽 × 深 × 高 | 完整视频 |
| --- | --- | --- | --- |
| `face_small` | 正面同比缩小 5%：s=0.95 | 96.9 × 74.25 × 96.9 mm | 30.20 秒，604 帧 |
| `depth_thick` | 叠层厚度、间距同比增加 10%：d=1.10 | 102 × 81.675 × 102 mm | 30.15 秒，603 帧 |
| `corner_cut` | 外角切角比例 q=0.25，切去 5.25 mm | 102 × 74.25 × 102 mm | 30.15 秒，603 帧 |

切角仍为 0.75 mm 正交阶梯近似。两个缩放参数的其他维度、切角参数不变；切角实例不缩放尺寸。
三者都继承基础版三段动作，尺寸变化仅派生转轴、位移、抓点、初始高度和抬升量调整，关节角重新求 IK。
前者抬升 66.5 mm，其余抬升 70 mm。原密度、控制增益、力矩上限、摩擦和辅助抓持流程保持不变；新质量惯量由实体生成。

三者指定理想路径均通过 0.20 mm 余量的连续证书，六方向直拉均保留真实重叠见证。
直拉证书遇到零间隙相切会立即停止，因此额外采样找到内部穿透见证，避免仅凭一次相切就宣称该路径被阻挡。
每个实例均完成 1,175 帧双臂 IK 计划和 235 帧机器人碰撞采样，并分别执行默认/半时间步的完整物理流程。

| 默认执行实测 | 正面缩小 | 叠层加厚 | 外角切角 |
| --- | --- | --- | --- |
| 最小采样 SAT 间隙 | 0.2479 mm | 0.2189 mm | 0.1988 mm |
| 最终分离间隙 | 74.0518 mm | 77.9414 mm | 77.9459 mm |
| 两时间步终态最大位置差 | 0.001087 mm | 0.005492 mm | 0.004494 mm |
| 件间 / 非抓持机器人 / 双臂最大接触穿透 | 0 | 0 | 0 |
| 夹指最大接触穿透 | 0.0156 mm | 0.0254 mm | 0.0254 mm |

上述执行均为 CPU 双精度，默认 2.5 ms / 对照 1.25 ms、10 子步。从张爪预抓取开始，真实解除接触门控辅助约束后松手，撤回 80 mm 并自由静置 2 秒。
五路视频用每次完整物理执行的精确状态离线 Nyx 渲染；未把 IK 目标当作物理状态。38 项相关检查通过。

四格对照入口：[`基础版与三个单参数外观 Demo`](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_single_v1/index.html)，可按抬升、转动、移出、松手和静置阶段分别对齐。
新增独立 MP4 位于 `runs/demos/cast_coil/2026-09-17_appearance_<kind>_<camera>.mp4`；每个实例的报告、半时间步、状态、源代码、资产与哈希清单位于对应 `runs/demo_metadata/cast_coil/2026-09-17_appearance_<kind>/`。
基准栏复用已验证的原录像，其运行后端为 CUDA；新增实例分别完成 CPU 物理复核，不把基准与新录像的数值差异归因于唯一外观参数。

本轮只证明这三个单独变化的指定实例可执行，不证明此前三种运动反推结构的外观随机化，也不证明三个参数联合随机生成的通过率、纯摩擦抓持或实际机器人负载能力。
