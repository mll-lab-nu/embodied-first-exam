# 默认场景恢复实施报告

**最新状态（2026-09-25）：三项后续修正已完成快速补验：21 项单元检查通过，三个新场景均完成 0.075 s 真实物理推进与 Nyx 录像，Orbits home/张爪与 5/5 代表性接近路径的几何检查通过。** 新安装包的独立导入与资产生成也通过；数秒稳定性、连续操作与完整公共生命周期尚未复验。下文 2026-09-24 的通过数及长录像仍对应前一轮源码。

<a id="scene-refinements-20260925"></a>

## 三项后续修正：代码交付与待验证清单

范围按[已确认的第 11 节计划](scene_preset_restoration_20260924_zh.md#11-三项后续修正计划2026-09-25代码已改待验证)实施。代码交付那一轮按用户要求未运行测试；随后用户授权耗时不多的追加检查，已执行下述快速补验。追加验证没有再修改产品代码。

| 修改文件 | 实际变更 |
|---|---|
| [`topogym/tasks/scene_presets.py`](../../../topogym/tasks/scene_presets.py) | Horseshoe 默认目标圆环用 `copper`；Lock 默认开启 0.8 mm 黄色孔缘线；Orbits 默认底座中心 `[-0.1356786, 0.0] m`、绕 Z 轴 +90°、保持 0.85 缩放 |
| [`topogym/tasks/horseshoe_ring.py`](../../../topogym/tasks/horseshoe_ring.py) | 仅对 `target_ring` 的 URDF visual 应用现有铜色 PBR 工具并记录外观元数据；马蹄与链条保留原色；物理声明未调整 |
| [`topogym/tasks/lock_picking.py`](../../../topogym/tasks/lock_picking.py) | 三块转盘和终点板接入已有 `paint_aperture_outline`；正反面沿孔外实体侧描线，随所属盘运动；生成报告的资产引用转为相对路径 |
| [`topogym/tasks/orbits.py`](../../../topogym/tasks/orbits.py) | 区分底座中心与整体 AABB 中心；对各零件的视觉/碰撞资产、合并预览、绳中心线及 FEM 初始顶点使用同一旋转；保留材料坐标、四面体连接及端点身份；记录两种中心、长轴和世界包围盒，刷新生成资产哈希 |
| [`tests/unit/test_scene_presets.py`](../../../legacy/research_tools_20260929/tests/unit/test_scene_presets.py) | 更新 Orbits 默认布局断言，增加整套网格/FEM 同步变换及旧中心参数兼容用例；现有跨目录资产复现检查加入 Horseshoe、Orbits。**该文件 21 项检查全部通过** |
| 本报告、原计划及[视频 README](../../../runs/test_results/base_acceptance_final/README.md) | 记录实际验证结果；README 新增三项新预设的短程录像和 PNG，原较长视频链接按历史版本保留 |

改动限于 **4 个产品文件、1 个测试文件和 3 个文档文件**。复用现有材质工具及 Lock 几何描线函数，未改公共 API、机器人、世界/物理模块或几何生成器。

Orbits 使用双臂固定安装的世界中线：profile 安装位置 X 为 `-0.1356786 m`，模型中左右底座局部 X 分别为 `-0.469/+0.469 m`。底座中心 Y=0 已用于新截图；加载后的 home/完全张爪几何检查通过，但连续真实操作尚未验收。

新定位参数为 `placement_anchor="base_center"` 与 `base_center_xy_m`。旧 `center_xy_m` 仍指整体包围盒中心：显式选择 `placement_anchor="assembly_center"` 可使用；若旧调用只传 `center_xy_m` 而未指定新定位模式，也会选择整体中心模式。要重建旧横向布局，还需传 `yaw_deg=0`。同时传两种中心却不指定模式时明确报错，避免含糊选位。`geometry_report` 保留模板坐标，新的世界坐标指标单独记录。

### 快速补验的实测结果与耗时

从单元检查开始到最后一项接近路径筛选结束，实测时间窗口为 **595.59 s，约 10 分钟**；部分 CPU 检查与 GPU 运行并行。全部正式补验结果、源码一致性和剩余范围见[汇总 JSON](../../../runs/test_results/scene_refinements_20260925_checks_01/summary.json)。核对了 86 个受保护源文件，未发现变动；本次验证没有触及另一会话的公共实现。

最初估计完整短视频测试需 10–20 分钟，读取旧报告后已及时纠正：三个场景各 3 s 的旧运行分别耗时约 22.0、19.5、34.9 分钟，合计 **76.5 分钟**，尚不含新的路径和生命周期检查。因此本轮采用明确标注的 0.075 s 冒烟验证，不把旧 3 s 结果算作新代码通过。

| 验证 | 结果 | 实测墙钟耗时 / 证据 |
|---|---|---|
| 场景单元回归 | **21/21 通过**，包含 Orbits 整套变换、材料坐标和旧中心参数兼容、资产复现 | **106.17 s**；[JUnit](../../../runs/test_results/scene_refinements_20260925_checks_01/unit.xml)、[日志](../../../runs/test_results/scene_refinements_20260925_checks_01/unit.log) |
| Horseshoe / Lock 物理资产对照 | 实体物理声明、质量/惯量、碰撞形状、关节及附件与改动前相同 | **6.26 s**；[报告](../../../runs/test_results/scene_refinements_20260925_checks_01/physics_assets_02/report.json) |
| 独立安装新 wheel | 在独立 venv 导入安装包、生成三项 Task 资产通过；102 个 Python 源文件与构建快照一致 | **18.25 s**；[报告](../../../runs/test_results/scene_refinements_20260925_checks_01/installed_assets/report.json)。此项不含安装包 Env 运行 |
| Horseshoe 真实初态/短程推进 | 通过；固定高位图中铜色圆环与银灰马蹄清晰区分 | **72.0 s**，推进 0.075 s；[报告](../../../runs/test_results/scene_refinements_20260925_smoke_01/horseshoe_ring/report.json) |
| Lock 真实初态/短程推进 | 通过；斜视角可见转盘黄线，主视角可见目标孔黄线 | **57.7 s**，推进 0.075 s；[报告](../../../runs/test_results/scene_refinements_20260925_smoke_01/lock_picking/report.json) |
| Orbits 真实初态/短程推进 | 通过；整套纵向位于双臂之间，高位图覆盖底座、木环、绳子与木柄 | **153.39 s**，推进 0.075 s；[报告](../../../runs/test_results/scene_refinements_20260925_smoke_01/orbits/report.json) |
| Orbits home/张爪几何扫描 | 16 个开合采样全部通过；包含加载后的刚体和 FEM 表面，最小间隙 **76 mm**，门槛 10 mm | **36.68 s**；[报告](../../../runs/test_results/scene_refinements_20260925_home_01/orbits/report.json)。最近对为肩部与桌面，不是仅测量夹爪至木环 |
| Orbits 代表性接近路径 | 木柄及四个环口 **5/5 通过**，检查 home 到目标的连续 IK、夹具/对侧机械臂间隙及关节余量 | **151.6 s**；[报告](../../../runs/test_results/scene_refinements_20260925_reach_01/orbits/report.json) |

接近路径筛选本次选中的 **5 条路径均使用左臂**，没有分别证明右臂也能完成所有接近。木柄路径最小间隙约 34.22 mm；四个环口依次约 **1.75、6.96、7.01、7.02 mm**，均超过现有几何门槛 0.5 mm，最小关节余量约 0.458 rad。第一环路径余量较窄，仍需连续真实动作、抓取及误差容忍度验证。该筛选不检查同侧机械臂自碰撞，也不证明软绳接触/抓取可行；不能把它写成完整双臂操作通过。

三项冒烟运行共保存 **11 路同步视频**，每路 3 帧 / 0.100 s、848×480、30 fps，并完成解码检查。它们适合证明新预设实际加载和短程有限状态；观察外观优先打开[README 中的新 PNG](../../../runs/test_results/base_acceptance_final/README.md)。[人工图像审阅](../../../runs/test_results/scene_refinements_20260925_smoke_01/visual_review.json)只覆盖列明的固定视角，尚未覆盖所有盘面近照、转盘旋转和操作中的腕部视角。

物理资产对照的第一次临时工具调用错误引用了 `TaskSpec.solver_options`，未形成场景结论；修正为真实字段 `physics_options` 后完整重跑通过，初次失败记录保留在 `checks_01/physics_assets/`。没有为通过检查修改产品代码。

### 完整验收清单（按上述结果区分已测与剩余范围）

| 优先级 / 范围 | 要确认的具体内容 | 需要的证据 |
|---|---|---|
| P0：加载与复现 | 三个 Task 能正常生成资产、make/reset；相对资源可解析；同 seed 跨目录资产一致；重新构建的安装包也加载新默认值 | 针对性单元检查、实际重建及独立安装加载记录 |
| P0：Horseshoe 物理保持 | 铜色处理未改变质量、惯量、碰撞体或自由状态；重力补偿仍为零，无附着或运行时矫正 | 修改前后物理描述比对、已有自由圆环合同检查；短程实际推进，必要时复用自由落体诊断 |
| P0：Lock 几何保持 | 所有孔的净空、碰撞件、惯量、限位、支架及钥匙姿态保持；描线只是贴图 | 描线开/关的物理资产对照、转盘旋转检查及短程运行 |
| P0：Orbits 变换一致 | 底座确实纵向居中；所有刚体、碰撞、FEM 初态和两个连接端点一起转动；材料坐标/拓扑未变，没有重复变换或四面体翻转 | 新增几何回归、加载后的实体位置/连接残差及至少数秒真实推进 |
| P0：Orbits 操作空间 | home、张爪过程与装置无非预期相交；双臂能从 home 连续接近木柄和代表性环口，关节及碰撞余量合格 | `home_clearance`、`layout_reach` 几何筛选与后续连续动作实测；旧横向结果不能继承 |
| P1：实际外观 | 铜色圆环与银灰马蹄清晰区分；0.8 mm 黄线准确贴合真实孔形，正反面、旋转后和腕部近景都正常；Orbits 符合用户纵框方向且各部件完整可见 | Nyx + compact_lab 默认相机、必要的近景与俯视实际 PNG；黄线最终宽度以真实像素可辨性确认 |
| P1：生命周期与交付 | reset 后仍加载这些默认值；改动任务的状态保存/回溯与录制一致；源码/资产身份明确 | 针对性公共合同回归、新批次多视角视频、解码/同步检查及更新后的 README |

后续完整补验仍使用以下入口。本轮已执行 pytest、home 和 layout_reach 检查；场景短片采用 `--seconds 0.075`，**下列 3 s 长度尚未执行**：

```bash
.venv-gs121-nyx/bin/python -m pytest tests/unit/test_scene_presets.py
.venv-gs121-nyx/bin/python scripts/test_scene_presets.py --tasks horseshoe_ring lock_picking orbits --seconds 3 --output runs/test_results/scene_refinements_20260925_scene_01
.venv-gs121-nyx/bin/python scripts/test_scene_presets.py --tasks orbits --seconds 0 --probe home_clearance --output runs/test_results/scene_refinements_20260925_home_01
.venv-gs121-nyx/bin/python scripts/test_scene_presets.py --tasks orbits --seconds 0 --probe layout_reach --output runs/test_results/scene_refinements_20260925_reach_01
```

布局 probe 是几何筛选，不能替代连续物理动作；默认短片也不能替代完整任务成功验证。前一轮公共生命周期失败和 Buzz 操作缺口仍属于原报告范围，本轮没有重测或宣称解决。

## 前一轮交付记录（2026-09-24 源码与录像）

日期：2026-09-24。**已交付九项默认场景修复、13 项当时场景录像及逐文件报告；Buzz 实际拾取/终点放置仍未通过，不能宣称前一轮全部操作条件已完成。** 原批准方案与历史 demo 参考截图见[场景恢复计划](scene_preset_restoration_20260924_zh.md)。视频入口为[基础环境 README](../../../runs/test_results/base_acceptance_final/README.md)，以下保留前一轮实际记录。

## 与 API 会话交接核对

用户通知 API 会话结束后，重新读取其最终报告、项目规则并逐文件比较现场源码。结论：**未发现相互覆盖，场景代码无需回滚或迁回旧 API。**

- 本轮开始快照已含新 API：管理方 reset、episode 绑定 interaction、单条有效 tick 历史、四种控制、Nyx 统一观察/录制。本轮直接消费这些接口。
- 起点以来的已有文件差异为本轮 12 个场景文件，以及对方 `tests/integration/test_installed_simulator.py` 的 wheel 构建修复。后者改为直接调用 setuptools build backend，解决运行 venv 不含 pip 的问题，与场景实现无冲突。
- 本轮未修改 `simulator/`、`config/`、`world/`、`robot/`、`sensors/`、`recording/`、公共运行测试、`pyproject.toml` 或 `assets/geometry/lock_picking.py`。最初计划表中跨模块候选已被任务内预设方案取代。
- 最终安装包为 wheel09，产品源码与当前主项目一致；wheel09 与 wheel08 的产品代码相同，只更新测试消费者。最新默认视频分别保留真实运行版本：Buzz 使用 wheel08，Lock 使用未改变其产品代码的早期版本，其余任务按各自冻结批次记录。旧 Buzz 木柄托架证据已被新银杆托架版本替代；参数相等不代表资产或物理等价。版本、哈希与逐任务适用范围见[批次核对](../../../runs/scene_preset_restoration_20260924_work/final_source_equivalence.json)。[最终边界复查](../../../runs/scene_preset_restoration_20260924_work/final_boundary_review.json)仍只有对方 wheel 测试脚本这一项外部差异，未发现相互覆盖。
- 对方交付的是“接口代码已完成、GPU 验收未全部完成”：仍有 6 项公共机制用例及合并后的 13 项基础场景待验收，Panda Nyx 生命周期崩溃原因未定。[API 实施报告](simulator_public_api_implementation_20260924_zh.md)。本轮结果不会替这些缺口宣告通过。

合并后补验进一步发现公共合同缺口：Cast Coil、Blanket、Rope 的 seed A→B→A 严格 RGB 逐像素复现失败。三项的前序物理推进、回溯阶段已通过，生成资产哈希检查已通过；对保存的 A / A 再次初态分别复核 720 / 702 / 795 个物理数组，最大绝对差均为 0。当前失败定位到图像复现检查，不能据此把生命周期测试标为通过，也不能把差异归因于场景文件互相覆盖。[失败与独立状态对比](../../../runs/test_results/scene_presets_20260924_lifecycle_01/failed_case_analysis.json)。共享传感器/渲染代码未作修改；场景外观视频与严格公共接口资格分别报告。最终本批次基础生命周期为 **10/13 通过**，FEM checkpoint 专项通过；跨任务切换在第 4 个场景 Hedgehog 阶段发生原生段错误（退出码 -11，源码未变化），因此该专项未通过，根因尚未定位。[公共补验完整索引](../../../runs/test_results/scene_presets_20260924_lifecycle_01/README.md)。后续正式场景录像仍使用逐项独立进程。

API 会话完成带来的调整在验收衔接：不再等待另一 session；使用最新接口和真实安装包，逐任务独立进程串行运行 GPU。此前双方曾有 GPU 资源重叠，属于运行排期问题；本次没有发现源码覆盖。冻结版本的每个批次保存源码身份，不能将不同版本的通过结果合并成一份完整资格。

## 已落实的默认场景

新增包内 `lab_tasks_v1` 预设，由 Task 默认值直接消费。普通 `topogym.make(task_id)` 后 `reset(seed=...)` 会加载；不依赖 demos 目录或录制脚本。显式 task_parameters 仍可覆盖允许的几何参数，episode 资产目录保存 `scene_preset.json`。

| 任务 | 当前默认效果与结构 | 物理边界 |
|---|---|---|
| Horseshoe | 保留金属马蹄与自由圆环 | 环正质量、无附件、重力补偿 0；无运行时位置纠正 |
| Hedgehog | 深木笼、浅木刺球，保留木纹；完整支撑座 | 原碰撞形状和固定/自由关系保持 |
| Buzz Wire | 木底座/支撑/柄，铜 wire，银环/杆；原路线线性缩放 0.60 | visual、collision 与路线一致缩放；自由工具，实体首尾托座；原 spatial_maze_v2 路线及方向见证保留 |
| Lock Picking | 底板、三盘支架、限位环、钥匙开放 V 托架完整；框架与托架灰白工程塑料，钥匙金属 | 三盘被动、钥匙自由；完整机械止挡/开锁资格仍单独保留缺口 |
| Fiber Bundling | 深蓝灰箱体、黑色主缆/护套、彩色绝缘子线与铜端头 | 增加仅视觉网格；原关节、质量和碰撞 primitive 保持 |
| Rope Threading | 麻绳色哑光绳；青/绿/紫环；整套装配旋转并平移 | 原绳与三环相对关系保持；FEM 不被静态 GLB 替换 |
| Knot Untying | 暖橙非金属绳，与桌面区分 | 结型、网格、FEM 材料及初始拓扑保持 |
| Orbits | 深浅木质刚体、金黄非金属绳；横向缩放并居中 | 线性 0.85；保留绳与木柄的两处永久端点连接 |
| Slotted Post Ring | 木质底板/柱/环/珠/端片，自然黄褐绳；整套平移避开右夹爪 | 真实槽孔、自由部件和 FEM 端点关系保持 |

### 尺寸与位置

坐标单位为米，XY 是当前实验室世界坐标；Z 随统一桌面高度加载。位置固定在初始化时，不追随机器人。

| 项目 | 最终参数 |
|---|---|
| Buzz 底板长×宽×厚 | 0.4956 × 0.3444 × 0.027（原尺寸逐轴 ×0.60） |
| Buzz wire 半径；环中心线/管半径 | 0.0021；0.0156 / 0.0018 |
| Buzz 柄长/宽/厚 | 0.042 / 0.0108 / 0.006 |
| Buzz 底板中心 XY；额外抬升 | (-0.08, -0.27)；0.04 |
| Buzz 明示的支撑例外 | 首尾 mount 0.032×0.032×0.016，端挡半径 0.026；这些功能支撑不机械缩至 60% |
| Lock 首盘 X；轴线 Y | 0.0；-0.26；钥匙另有实体初始托架 |
| Rope 整体旋转/平移 | Z 轴 75°；(-0.1156786, 0.03, 0.0015)，再加桌面高度 |
| Orbits 比例；全装配 AABB 中心 XY | 0.85；(-0.1356786, -0.24)，长轴沿双夹爪横向 |
| Slotted 整装配/底板原点 XY | (-0.02, +0.04)，全部刚体与 FEM 同步平移 |

Rope 的 y=0.15、0.08、以及 90°/y=0.03 均为中间候选。90° 的版本虽然通过 3 s 原生状态检查，独立实际碰撞网格查询发现 home 夹爪与 R2 相交，故撤销该布局资格。新默认为 75°，X 再增加 20 mm；home 净空 43.96 mm，全开爪扫掠净空 18.27 mm，两个绳端与三个环口全部存在连续 IK 路径，最小路径净空 2.95 mm、最小关节余量 0.318 rad。见 [layout_07](../../../runs/test_results/scene_presets_20260924_layout_07/rope_threading/report.json)。这是实际网格几何筛选，尚不等于物理执行或穿绳成功。新默认已完成 final_02 的 3 s 检查；旧视频保留，不再列作最终布局通过。新初帧完整可见；自然松弛后一个绳端在高位末帧略超出画面、低位接近下边缘，故不宣称全过程双端完整取景。最大顶点位移约 59.85 mm，末半秒运动范围约 2.16 mm。

Orbits 原摆位不需再改。较早的几何诊断用固定姿态直线接近，被挡球或上层环拦住；改为先平移再调整末端姿态后，木柄和四个环上方接近点全部通过，见 [layout_09](../../../runs/test_results/scene_presets_20260924_layout_09/orbits/report.json)。home/开爪净空 76 mm，木柄路径 30.68 mm；三个环口路径最小仅 0.614 mm，属于窄间隙几何路径，尚未验证动态执行余量，不能称完整操作已合格。所有失败路径与原阈值仍保留。

Slotted 的旧原点 (0,0) 在 home 只有 2.44 mm 净空，右夹爪张开时与立柱相交。CPU 装载的机器人逐 link 位姿与实际 GPU 初帧相符（位置/姿态误差低于 4e-16），独立开爪查询发现了此问题：[失败证据](../../../runs/scene_preset_restoration_20260924_work/slotted_home_cpu_02/report.json)。旧长测试在 0.85 s 主动中断，录像保留。新原点 (-0.02,+0.04) 的刚体开爪筛选净空为 24.06 mm，所有刚体/FEM 顶点进入标准高位画面，真实新场景中的刚体与 FEM 绳表面查询亦通过，最小净空 24.06 mm：[报告](../../../runs/test_results/scene_presets_20260924_slotted_home_01/slotted_post_ring/report.json)。3 s 物理检查已在独立 final_03 批次通过，其余未变更任务继续使用冻结 wheel04；逐任务参数/源码等价关系另存。

### 本轮实际画面

Buzz 新默认场景（home 保持，非穿行演示）：[主视角 MP4](../../../runs/test_results/scene_presets_20260924_final_04/buzz_wire_3d/branch_000/videos/agentview.mp4)。

![Buzz 新银杆托座、木底板、铜 wire 与银色环](../../../runs/test_results/scene_presets_20260924_final_04/buzz_wire_3d/last_frames/agentview.png)

Lock 从 home 接近并实际拾取（当前机器人模型下通过，非开锁演示）：[侧视 MP4](../../../runs/test_results/scene_presets_20260924_pickup_lock_03/lock_picking/branch_000/videos/front_oblique.mp4)。

![Lock 钥匙离开灰白色托架](../../../runs/test_results/scene_presets_20260924_pickup_lock_03/lock_picking/last_frames/front_oblique.png)

## 修改了哪些脚本

共 14 个产品源码文件：9 个 Task、3 个几何模块及2个新预设/外观模块。另有5个独立验收脚本。[逐文件差异 patch](../../../runs/scene_preset_restoration_20260924_work/scene_owned_changes.patch) 与[当前文件哈希清单](../../../runs/scene_preset_restoration_20260924_work/scene_owned_files.json)可直接核对。完整起点哈希和边界分别见 [baseline](../../../runs/scene_preset_restoration_20260924_work/baseline.json) 与 [ownership](../../../runs/scene_preset_restoration_20260924_work/ownership.json)。

| 文件（相对项目根目录） | 改动 |
|---|---|
| `topogym/tasks/scene_presets.py`（新增） | 默认参数、预设身份、生成资产的确定性记录 |
| `topogym/assets/scene_visuals.py`（新增） | PBR 材质角色、工程塑料 visual、URDF 相对引用、视觉 GLB/碰撞 OBJ 分离 |
| `topogym/tasks/horseshoe_ring.py` | 接入预设，显式记录自由环/重力属性 |
| `topogym/tasks/hedgehog_in_cage.py` | 使用已有深浅木质资产，补支座外观 |
| `topogym/tasks/buzz_wire_3d.py` | 一致缩放、抬升、布局、自由环起点与实体支撑 |
| `topogym/tasks/lock_picking.py` | 调用既有生成器补底板、盘架、限位和钥匙托架；视觉后处理与相对资产路径 |
| `topogym/tasks/fiber_bundling.py` | 统一预设身份并消费生成器材质修复 |
| `topogym/tasks/rope_threading.py` | 整装配变换、正确 Z-up、分色环和 FEM 绳材质 |
| `topogym/tasks/knot_untying.py` | 显式非金属暖橙 FEM 表面 |
| `topogym/tasks/orbits.py` | 缩放、居中、刚体 GLB visual/OBJ collision、绳颜色与原端约束 |
| `topogym/tasks/slotted_post_ring.py` | 木质视觉与闭合碰撞体分离、麻绳色动态表面、整装配平移 |
| `topogym/assets/geometry/buzz_wire_3d.py` | 路线抬升参数；单 URDF visual 内保存多个独立 PBR primitive |
| `topogym/assets/geometry/rope_threading.py` | 全部网格、环基向量、支架与绳中心线一致旋转；唯一材质名 |
| `topogym/assets/geometry/fiber_bundling.py` | 动态链增加带 OBJ/MTL 的零质量视觉副本，原碰撞组与质量不变 |
| `scripts/test_scene_presets.py`（新增） | 冻结源码的逐任务验收、独立诊断、主步长/半步长入口 |
| `tests/scene_preset_evidence.py`（新增） | 复用 RuntimeEvidence 和 RecordingSession，增加场景实体清单 |
| `tests/scene_preset_diagnostics.py`（新增） | 自由落体与 Buzz 终点初态诊断，显式区分默认场景 |
| `tests/scene_preset_pickup.py`（新增） | 实体碰撞网格 IK 筛选、连续控制拾取/退出/释放检查 |
| `tests/unit/test_scene_presets.py`（新增） | 材质通道、质量/碰撞、约束、资产复现、整体变换和取景回归 |

```text
topogym/
├── topogym/
│   ├── simulator/                 # 保留 API 会话实现
│   ├── tasks/scene_presets.py      # 包内默认预设
│   ├── tasks/<九项任务>.py
│   └── assets/
│       ├── scene_visuals.py
│       └── geometry/<三项生成器>.py
├── scripts/test_scene_presets.py
├── tests/scene_preset_*.py
├── tests/unit/test_scene_presets.py
├── docs/develop/dev-logs/scene_preset_restoration*.md
└── runs/
    ├── scene_preset_restoration_20260924_work/ # 哈希、wheel、静态测试
    └── test_results/
        ├── scene_presets_20260924_*/          # 实际录像/状态/报告
        └── base_acceptance_final/README.md   # 用户原视频入口
```

## 为什么之前会丢失，修复中又发现了什么

1. 重构优先迁移基础物理生命周期，历史 demo 配置不再自动进入 Task.defaults；材质和夹具迁移不完整。旧测试的图像非空、三步推进、可回溯不能拦住这类视觉/操作回归。
2. OBJ 与 GLB 选错：Orbits/Slotted 原先跳过带木纹的 GLB；动态 FEM 也不会自动继承另存 GLB 的颜色。现在刚体视觉、物理碰撞和软体 surface 分开指定。
3. Buzz 同 link 多个 URDF visual 在实际 Nyx 路径下丢失细件。首次直接拼接纹理网格又丢失 metallic/roughness，现用单 visual、多个 PBR primitive 保留铜/银/木各自通道。
4. Fiber 的 primitive rgba 未在实际 Nyx 画面保持。修复位于资产生成层，视觉副本零质量且不参与碰撞，避免整体染黑子线。
5. 新恢复的 GLB 默认轴解释与生成器 Z-up 不同，造成 Rope 环倾倒/埋桌；显式指定 Z-up 后纠正。带 UV 接缝的 GLB 又不适合直接当 IPC 闭合碰撞体，Orbits/Slotted 改用原闭合 OBJ 作 collision。
6. Lock URDF 绝对路径破坏跨目录资产字节复现；新增局部引用规范化，同时修复工具对相对输出目录的处理。未降低对方的严格 seed 检查。
7. Rope 候选平移与机器人脚座冲突被原生 IPC 检查拦截；随后旋转整个装配，最终再按默认视角调整取景。没有关闭碰撞检查。

以上属于配置迁移和资产加载问题；本次交接未发现两个 session 相互覆盖造成的源码丢失。

## 已完成场景的实际运动

Orbits 已完成 3 s、121 个状态样本、四路各 91 帧视频。木柄碰撞网格质心自然松弛后相对初态移动 51.72 mm，末 0.5 s 位置跨度 0.041 mm；刚体原点的对应数值是 52.27 / 0.159 mm，二者未混用。见 [质心运动量](../../../runs/test_results/scene_presets_20260924_final_02/orbits/handle_centroid_motion.json)。绳仍有小幅振动，末窗口最大顶点跨度 4.18 mm、最大顶点速度 0.0561 m/s。因此可以报告短程物理/连接检查通过，不能报告整个绳系统已经完全停稳。见 [运动量](../../../runs/test_results/scene_presets_20260924_final_02/motion_measurements.json) 和[实际末帧](../../../runs/test_results/scene_presets_20260924_final_02/orbits/last_frames/cam_high.png)。

Knot 的暖橙绳在 3 s 后仍完整可见，原生 FEM 状态检查通过；但首末帧显示无机器人动作时形状明显松弛，最大顶点位移约 0.229 m。末 0.5 s 最大顶点运动范围约 0.97 mm。此次产品差异仅为表面颜色/预设标识，未修改结型、网格、FEM 参数；该录像不能证明初始结型在重力下保持，也不能证明解结成功。[首帧](../../../runs/test_results/scene_presets_20260924_final_02/knot_untying/initial_frames/cam_high.png) · [末帧](../../../runs/test_results/scene_presets_20260924_final_02/knot_untying/last_frames/cam_high.png)。

实际拾取初次复验（pickup_02）未通过：Buzz 已建立双侧接触，但 60 mm 抬升过程中抓持点相对 TCP 滑移 18.1 mm，双侧接触只覆盖 42.9% 的抬升样本；不能以抓持点升高 50.5 mm 作为成功。Lock 在动作执行前被速度检查拦截：原始 IK 单步 0.030436 rad 略大于 0.025 s 内 1.2 rad/s 的上限。本轮新增的测试消费者已补 IK 步长细分与实际网格复查、稳定夹持等待和较慢抬升；没有改变机器人增益、力上限或物体质量/摩擦。当时 15 项场景回归通过（含 2 项新增步长回归）；随后新增银杆支撑回归，当前为 16 项。旧终点诊断主动中断并保留记录，Lock 已重录通过，Buzz 的后续结果见下文。

CPU 无 RGB 定位又发现 Lock 原检查的测量基准有误：钥匙 URDF 原点在尖端，抬升时钥匙会俯仰；该点只升高约 0.084 mm，但实际惯性质心升高 41.85 mm、抓持点升高 58.11 mm。独立复核测得抓持点相对 TCP 最大滑移 3.48 mm，抬升期间双侧接触覆盖率 100%，最终已脱离全部环境支撑。原失败报告保留，不能追改为通过；测试消费者现从 URDF 惯性原点计算真实质心，并同时检查质心和抓持点各抬升至少 35 mm，已以相同物理轨迹完成正式 Nyx 复录 `pickup_lock_03`，原测试与独立接触/位移复核均通过（6.325 s 连续物理执行）。该检查只证明拾取，不证明钥匙姿态固定或完成开锁。

Buzz 的 CPU 诊断中，原垂直夹持及 45° 夹持都未建立稳定双侧接触；沿柄方向的候选接近路径又触发关节余量或夹具碰撞检查。原阈值保留，没有提高摩擦、修改机器人增益或增加工具附件来强行通过。已完成更靠近柄根、加深夹持和倾斜夹持等诊断；靠近柄根/倾斜候选发现托架阻挡，随后按下文修正为银杆支撑。动作候选未进入产品控制器。CPU 诊断均显式关闭 RGB，不当作 Nyx 视频资格。

Buzz 托架阻挡已由实际保存状态定位，而非根据视频猜测：在倾斜抓取的 4.175 s 状态，实际关节位置的独立网格查询得到 `right_finger` 与 `wire_base/32` 接触；该几何的包围盒对应木柄根部托架，不是大底板。[实际网格复查](../../../runs/scene_preset_restoration_20260924_work/buzz_contact_query_17/result.json)。支撑修正仅在 Buzz Task 和几何模块：新增可选 `endpoint_support_part`，历史生成器仍默认 handle，本任务采用 stem；两端支撑从局部 x=41.4 mm 移到 x=21.3 mm，托住半径 1.8 mm 的银杆，完整木柄保持自由。支撑实体上沿从工具中心下 3 mm 调整为下 1.8 mm；原工具、wire、底板、尺度、质量、摩擦与无附件关系不变。新增回归检查首尾支撑接触位置、与木柄至少 10 mm 的几何间距；16 项场景回归通过。在新托架下复查此前被卡住的真实夹爪姿态，净空恢复为 6.00 mm、无相交：[修正后网格检查](../../../runs/scene_preset_restoration_20260924_work/buzz_contact_query_stem_18/result.json)。同 seed 的安装包资产逐字节对比确认 wand/wire 的 URDF、visual 与参考路线不变，仅两座支撑的碰撞 OBJ、底座视觉及相关哈希/报告改变：[资产差异](../../../runs/scene_preset_restoration_20260924_work/support_revision_asset_diff_08.json)。新布局已在 final_04 通过 3 s 物理状态检查与三路录像解码；首尾两组 0.1 s 主步长/半步长支撑对比也通过：[最新量化对比](../../../runs/test_results/scene_presets_20260924_half_step_comparison_08.json)。3 s 记录中，工具刚体原点相对初态位移约 0.184 µm，末 0.5 s 位置跨度约 0.012 µm；这只证明短程支撑保持，不代表真实拾取或终点放置成功。旧 Buzz 通过不沿用。

最新银杆支撑的实际倾斜夹持试验在 **7.7 s** 结束，未达到稳定双侧夹持条件，最后两侧接触力约 0.065 / 0.056 N；没有进入抬升阶段，不能作为抓取成功：[headless_stem_18](../../../runs/test_results/scene_presets_20260924_headless_stem_18/buzz_wire_3d/report.json)。这是显式 CPU / 无 RGB 诊断。与此同时，新默认的三路 Nyx 场景录像已完成，故“场景可见且能运行”与“机器人能稳定拾取”分别报告。

## 公共机器人模型的新增审查发现（只读，未修改）

Buzz 的拾取失败还不能全部归因于托座。只读核查确认，原 Robotiq MJCF 两个 `spring_link` 的弹簧参考角均为 **2.62 rad**、刚度 **0.05 N·m/rad**；当前安装的 Genesis 1.2.1 导入了刚度，但弹簧恢复力使用 `q - qpos0`，实际载入参考角为 **0 rad**，没有使用 MJCF 的 `springref`。因此在本次加载的 q=0 初态，原模型弹簧项应为 +0.131 N·m，当前引擎该项为 0。两侧实际导入值及源码哈希见[只读诊断](../../../runs/scene_preset_restoration_20260924_work/robotiq_spring_import_review/report.json)。这证明了模型语义差异，**尚未证明它是 Buzz 抓取失败的唯一原因**；四连杆连接残差较小也不能排除此弹簧预载差异。没有证据表明这是另一 API 会话新增的问题。

若扩展修复，应单独处理公共机器人兼容层，而不是在 Buzz 上加附件、改质量/摩擦或每帧修正物体位置。可审阅的实施范围：新增 `topogym/robot/genesis_passive_springs.py`，在 `topogym/robot/joint_position.py` 的模型初始化处接入；按原 MJCF 参数补偿缺失的恒定弹簧项 `k*(springref-qpos0)`，保留 Genesis 已有 `-k*(q-qpos0)` 项，避免重复加弹簧。该方向仍需确认控制模式/原生 checkpoint 是否完整保存被动项；本轮没有写入这两个公共文件，也没有修改安装环境里的 Genesis。

这会改变四个 Panda 场景的机器人动力学：Hedgehog、Buzz、Lock、Fiber。进入修复前应明确扩大范围；之后至少重验弹簧力曲线、无物体闭爪、真实薄柄/钥匙抓取、reset/rewind 和这四项场景录像，当前 Lock 的通过不能直接沿用到修正后的机器人模型。其余场景外观与 API 文件交接结果可独立交付。

Buzz 的终点路径仍有独立缺口：已检查直上直下、沿柄方向侧向接近、夹持方向严格垂直于木柄，以及终点木柄转向外侧的诊断候选；这些候选均有路径碰撞或关节余量不足，不能写成“终点放置已可执行”，也不能据此宣称不存在其他可行路径。外向候选只存在于诊断参数文件，未合入默认预设。默认方向的精确垂直夹持检查见 [terminal_reach_21](../../../runs/test_results/scene_presets_20260924_terminal_reach_21/buzz_wire_3d/report.json)。当前测试消费者已支持非坐标轴方向的木柄，并在动作过程中拒绝夹指对非目标夹具大于 0.05 N 的接触；不会把顶住托架误当作夹紧工具。

## 已有证据与待完成项

| 检查 | 当前结论与范围 |
|---|---|
| 合并后的非引擎测试 | **190 项通过、49 项真实引擎用例未选中**：[JUnit](../../../runs/scene_preset_restoration_20260924_work/merged_non_engine_contracts_08.xml)，含 API 合同、配置/资产、数据/HDF5 与本轮 16 项场景回归（包含 IK 步长细分与银杆支撑净空）；不代替 GPU 验收 |
| 真实非 editable wheel | 构建、安装、仓库外九项声明通过；当前最终录像直接运行该安装包。[manifest](../../../runs/scene_preset_restoration_20260924_work/installed_scene_09/manifest.json) |
| 同 seed 资产字节 | 九项跨目录检查通过；Lock/Buzz 最新材质与相对路径另有回归覆盖 |
| Horseshoe 自由落体 | 0.1 s 测得 -9.810000000000016 m/s²，下落 0.0493565625 m；诊断初态抬环 0.35 m，正常 step 无位姿写入。[报告](../../../runs/test_results/scene_presets_20260924_gravity_01/horseshoe_ring/report.json) |
| Buzz/Lock 初始接近 IK | 旧同物理布局的开爪路径通过，最小夹具间隙 13.185/3.561 mm；不等于真实抓取。计划中的 10 mm 筛选目标并非 Lock 已达到的结果 |
| 13 项最终录像 | **13/13 最新默认场景录像已完成**：Buzz 使用修正托架后的 `final_04`，Lock 使用 `final_01`，Slotted 使用 `final_03`，其余使用 `final_02`；九项变更场景各 3 s，未变更四项各 0.075 s。Knot/Blanket/Rope 的资格与取景限制如上文；不是 13 项任务 solved |
| 真实拾取、Buzz 终点放置 | Lock 最新 pickup_lock_03 正式录像及独立复核通过：质心 +41.85 mm、抓持点 +58.11 mm、相对滑移 3.48 mm、双侧接触 100%、最终无环境支撑；Buzz 拾取/终点放置尚未通过。原失败和中断不计作通过 |
| Rope/Orbits 代表点 | 两项各 5 个连续 IK 接近路径均通过实际网格筛选；没有执行绳操作，Orbits 部分路径间隙较窄，见上文 |
| 半步长、生命周期 | Buzz 起点、Lock 支架、Buzz 终点三组 0.1 s 主步长/半步长对比均通过；公共生命周期在银杆托座修改前的产品源码冻结副本上为 10/13 通过，FEM 专项通过，任务切换原生崩溃；详见上文 |

逐图审阅记录见 [visual_review_04](../../../runs/scene_preset_restoration_20260924_work/visual_review_04.json)。未改动的 Blanket 下落初态在两个固定视角首帧均有裁切，已单独标注；没有将其短程物理通过写成完整视觉验收。

标准录像均为实际 Genesis + Nyx + compact_lab、848×480、30 fps，默认从机器人 home 开始。预览、首尾独立诊断和完整任务 demo 分别标注，当前场景测试不写入 `demos/` 的正式完整流程目录。

早期失败和中断保留：`initial_01` 缺视觉资源根目录；`initial_04` GLB IPC 碰撞网格失败；`initial_05` Rope 碰撞脚座；`physics_01` 资源重叠时 CUDA OOM；`pickup_01` 主动中止旧视觉/旧慢速诊断。此前诊断记录见[保留记录](../../../runs/scene_preset_restoration_20260924_work/implementation_notes_before_handoff.md)。

Buzz、Lock、Fiber、Rope、Knot、Orbits、Slotted 的完整成功判据仍未完成，本轮不会把场景可见或短程稳定写成 task solved。实际操作失败已保留；场景外观交付不等于全部操作验收完成。共享机器人修复作为独立范围待办，不通过修改公共模型或降低判据来掩盖本轮失败。

验收队列已收尾，GPU 测试均使用冻结源码并逐项独立进程串行运行：[主批次记录](../../../runs/scene_preset_restoration_20260924_work/validation_queue_04/planned_jobs.json) · [新银杆托座补验结果](../../../runs/scene_preset_restoration_20260924_work/support_followup_08/status.json)。失败和中断证据保留；原 README 只链接已收尾并完成解码的视频。

### 复现当前预设

在项目根目录使用当前引擎环境执行（输出目录必须不存在）：

```bash
.venv-gs121-nyx/bin/python scripts/test_scene_presets.py \
  --tasks rope_threading orbits --seconds 3 \
  --output runs/test_results/scene_presets_manual
```

不传 `--task-parameters` 即加载包内默认预设；候选参数诊断会在报告单列覆盖值。真实拾取诊断使用 `--probe pickup --tasks buzz_wire_3d lock_picking`；这是测试入口，当前 Buzz 抓放尚未通过，并非已验收的操作 demo。Buzz 首尾分开诊断，不将终点初态检查说成沿整段 wire 穿行。普通产品入口仍是 `topogym.make(task_id)` 与管理方 `env.reset(seed=...)`。

Slotted 新默认布局已完成 **3 s 连续物理验证**（final_03，121 次状态采样，四路 91 帧 / 3.033 s 录像）。高、低位末帧都覆盖完整木质组件与自然绳索；目标圆环最后 0.5 s 的刚体原点位移范围约 7×10⁻¹³ m，绳索顶点最大运动范围约 0.75 mm、最大采样速度 2.31 mm/s。此为有限时长运行证据，不是完整解环证明。[实测运动数据](../../../runs/test_results/scene_presets_20260924_final_03/motion_measurements.json) · [高位末帧](../../../runs/test_results/scene_presets_20260924_final_03/slotted_post_ring/last_frames/cam_high.png)。

<!-- LIVE_SCENE_RESULTS -->

## 最终默认场景批次进度

实际已通过 13/13，失败 0，运行中 0，待运行 0。

当前逐项状态、首帧和已收尾的多视角 MP4 见[原 README 视频入口](../../../runs/test_results/base_acceptance_final/README.md)。上述计数只覆盖默认场景批次；拾取、终点释放、半步长和生命周期仍须分别读取专项结果。
