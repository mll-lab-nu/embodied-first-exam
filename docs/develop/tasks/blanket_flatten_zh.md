# 杂乱被子展平（blanket_flatten）

**2026-10-06 v18 初态与候选：** 用户确认资源可用后恢复持续 goal，两档匹配 v18 运行栈的新初态均已生成并安装到 `cuda_sm89_mp128_87407517a32a` 资源组，原运行栈资源保留。`very_easy_initial_02` 连续完成 6,081 ticks，覆盖率 86.03%、最高点 14.19 mm、最大速度 5.73 mm/s，撤控后稳定 0.6 s。`easier_initial_01` 完成 10,201 ticks，覆盖率 41.12%、最高点 30.47 mm，材料、视觉、桌内及构形检查通过；最大局部速度 0.284 m/s，仍仅具 `scene_layout` 资格，**静稳未通过**。两次准备均未写粒子位置、材料静长或视觉支撑，未加固定粒子，显存峰值均为 1,988 MiB；四路 848×480 / 30 fps 录像完整解码与同步通过。独立 v18 镜像与四个双模式任务包已构建，两档独立进程精确恢复均通过；安装包包含两组运行栈的八个初态资源文件且哈希一致。`very_easy` 已在该 v18 Harbor 环境连续执行 15.905 s / 6,362 ticks 并原生成功，覆盖率 97.5845%、最高点 27.1447 mm、最大速度 0.0183 mm/s，已释放撤手并稳定 0.5 s；637 行动作未被改写，状态为 `native_success_pending_harbor_verifier`，**privileged 的独立 v18 grading 已 `solved=1`**：两次重放末态哈希均为 `fafc54ec0413b16b`，均在原严格门槛内成功，无额外静置、容差使用、待复核或 forcing 事件；评分视频完整解码通过。standard 首次执行至 379 行时，共享 GPU 空闲显存降至 2,046 MiB，触发本任务 2 GiB 保护线而中断；该次原始评分为 `success=0, infra_error=1, finalized=0`，不具完整策略验收资格。已保留全部证据，并重新排队只重试 standard；随后串行验证 `easier` 两种模式。每个模式启动前须连续三次确认至少 8 GiB 空闲显存。见[原始评分](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/continuation_03/grading_very_easy/jobs/001-oracle/topogym-blanket-flatten-very-eas__Xq23Nex/verifier/reward.json)与[评分回放 MP4](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/continuation_03/grading_very_easy/jobs/001-oracle/topogym-blanket-flatten-very-eas__Xq23Nex/verifier/replay.mp4)。运行保留至少 2 GiB 空闲显存，系统内存达到 90% 时只停止本任务拥有的工作进程与容器。见 [very_easy 准备报告](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/very_easy_initial_02/report.json)、[easier 准备报告](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/easier_initial_01/report.json)与[候选执行状态](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/continuation_04/status.json)。

**2026-10-05 用户追加验收要求：** 两档变体完成后开发对应 oracle，后续正式验收使用 tooling **v18 或更新版本**的 Harbor grading，分别检查 `very_easy`、`easier` 的 `solved=1`。直接 Env 的 Task success、独立审计与打包检查各自保留范围，不能代替该评分结果。镜像、实例和私有策略必须来自明确冻结的同一版本；不重写旧运行身份。

**2026-10-07 easier 改为远侧半张对折（用户决定）：** 实测（夹爪竖直朝下）两臂以布的中心线 x = −0.136 为镜像，桌面高度各自只能越过这条线 9–11 cm；左右对折的折痕正落在这条线上，翻回上层时抓点要从折痕一侧 28 cm 带到另一侧 28 cm，一只手做不完。现在把远离两臂的半张（y 0.15–0.39）翻过来盖在近侧半张上，近侧半张留在原位（`corner_fold_profile.far_half_fold=true`，只有 easier 带此字段），再只翻上层自由边靠右的角（两条直角边 18 cm，叠好的布只有 24 cm 宽，放不下原来的 22 cm）。oracle：右手翻回翻角；两只手各在自己一侧抓上层自由边（相距 22 cm），一起越过折痕放回原位；之后最多三次残留折角整理。准备初态时机器人停在 home、碰撞开着，原地翻这半张时自由边会在离桌约 32 cm 处扫过两只夹爪，所以先在空中把布往远处挪 15 cm 再折，折完从夹爪下方挪回。下面 10-07 "不再居中" 的左右对折已被取代。

**2026-10-07 easier 对折不再居中，oracle 改为逆折叠两段（用户提议）：** 原来对折后整叠布被平移 15 cm 回到布中心，按逆过程打开时布会比原平铺位置偏左 15 cm、压到左臂底座一带，路线只能先平移整叠布，实测会挤皱或转动。现在对折时下层留在原位（`corner_fold_profile.recenter_half_fold=false`，只有 easier 带此字段；very_easy 参数与身份不变，旧 easier 初态因参数不符被拒绝）。oracle 只做两段逆折叠：右手把上层翻角翻回上层，左手把上层绕折痕翻回原位；之后最多三次"测量残留折角再整理"（`fold_layout.max_stages=3`）。拉伸门槛 1.5（与 medium / hard 一致）。初态准备：机器人停在 home、碰撞开着，原地翻书式对折时翻起的半张会扫过右手手指（离桌约 31 cm）被挂住，所以先按原居中方式对折，两层布在空中右移 15 cm 回到原右半张位置，再原地翻上层的角（`corner_preparation.py`）；10-07 按"场景构形"验收的初态已安装。

**2026-10-06 easier 场景改为只翻上层的角（用户决定）：** 原 easier 把两层一起翻角，下层的角翻到最上面、把上层的角夹在中间，四层布压到 7.94 mm（粒径 8 mm）且初态不静止，oracle 的两段动作都卡在 1.3 拉伸保护线上，且不同机器准备的初态结果不同（诊断见 [证据](../../../runs/test_results/blanket_easier_scene_diag_20261006/README.md)）。现在 easier 对折后只把上层自由边的右前角翻到上层上，下层保持平放，角上最多三层。折法参数 `corner_fold_profile` 新增 `upper_corner_only=true`，只有 easier 带此字段，very_easy 的参数与冻结初态身份不变；旧的两层翻角初态因参数不符被拒绝，需按新几何重新准备。oracle 路线改为先翻回上层的角，再打开对折，再把下层远、近两角拉回原位（`topogym/planning/blanket_flatten/below_easy_routes.py`）。

**2026-10-05 very_easy / easier 折角变体：** 新增具名变体入口 `blanket_flatten_very_easy` / `blanket_flatten_easier`，也可使用 `variation_id="very_easy"` / `"easier"`。`very_easy` 是平铺布的右前角向内翻折，折角两边各 28 cm；`easier` 先沿 60 cm 方向对折为约 30 × 48 cm 的双层长方形，再将自由边的右前角连同两层一起翻折，折角两边各 22 cm（10-06 起改为只翻上层的角，见上条）。两档沿用 easy–hard 的 60 × 48 cm 布料、12 mm 网格、8 mm 粒径、材料、蓝色方格纹理、桌面摩擦和中心 XY=(-0.1356786, 0.15) m，使用共享 ALOHA home、compact_lab / Nyx 四相机。核对旧三档没有黄色抓点，已按用户要求去除设计预览里的黄色角标；正式任务不添加抓点提示。

[折角生成器](../../../topogym/assets/geometry/blanket_corner_folds.py)提供连续构形目标；[任务定义](../../../topogym/tasks/blanket_flatten/corner_folds.py)和[准备控制器](../../../topogym/tasks/blanket_flatten/corner_preparation.py)复用旧三档的平坦材料出生、速度控制、落桌、撤控及冻结恢复。准备不写粒子位置，不改材料静长或视觉绑定，不添加固定粒子。设计层间距 16 mm，双层折角使用同心弯曲并允许自由边自然错开；落桌后的实际间距由物理自接触决定。冻结状态是完整 `rigid_pbd_numeric_v2` 数值包，独立资源版本为 `corner_folds_archive_v1`，按运行栈／GPU profile、档位及 seed 登记到包内 catalog，不依赖开发 runs 目录。

原生 Task 默认要求投影覆盖率 ≥90%、最高点 ≤30 mm、材料边长比 ≤1.15、最大速度 ≤30 mm/s，并满足释放撤手与 0.5 s 静稳窗口。v18 Harbor 候选与原三档使用同一 release profile，将覆盖率设为 **95%**，其他门槛不放宽；准备资源通过公共重键工具生成副本，数值数组保持原字节。准备阶段的非展平覆盖率上限为 89%，适应单角折叠约 86% 的初态，区别于旧聚褶初态的 82% 准备上限。`base` 和原三档 seeded 采样保持原含义，新两档暂作为独立具名入口。

复现准备和验收（每次使用新输出目录，easier 替换档位；缺失的 seed / 运行栈须重新准备，不能借用其他初态）：

```bash
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
export PYOPENGL_PLATFORM=egl OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
.venv-gs121-nyx/bin/python scripts/prepare_blanket_initial_states.py \
  --tier very_easy --seed 0 --acceptance scene_layout --output <候选目录>
.venv-gs121-nyx/bin/python scripts/install_blanket_initial_state.py --candidate <候选目录>
.venv-gs121-nyx/bin/python scripts/check_blanket_corner_initial_states.py \
  --variation very_easy --candidate <候选目录> --output <恢复验收目录>
.venv-gs121-nyx/bin/python scripts/check_blanket_corner_initial_states.py \
  --variation very_easy --compare <恢复验收目录>/particle_checks.npz --output <独立进程验收目录>
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_blanket_oracle.py \
  --variation very_easy --record --output <机器人尝试目录>
```

截至初态验收，seed 0 的实测结果如下：

下表为旧运行栈的直接 Env 检查；当前 v18 初态、恢复及 Harbor 评分见本文开头，二者不混用资格。

| 检查 | very_easy | easier |
| --- | --- | --- |
| 撤控初态覆盖率 | 86.03% | 41.12% |
| 材料／视觉完整、桌内、落桌、自接触粒子间距 | 通过 | 通过 |
| 准备撤控后静稳资格 | 通过 | 未通过，按 `scene_layout` 保存 |
| 从准备资源恢复全部粒子位置／速度 | 逐值一致 | 逐值一致 |
| 再次 reset 到冻结初态 | 逐值一致 | 逐值一致 |
| home 静置 2.5 s 最大粒子位移 | 0.0203 mm | 2.7191 mm |
| home 静置末态最大速度 | 0.00558 m/s | 0.17818 m/s |
| 回退后 5 个控制步精确重放 | 未通过，最大位置差 0.00344 mm | 未通过，最大位置差 1.46754 mm |

短时静置中两档均未触发成功或失败。回退起点恢复精确，随后动力学重放产生差异；报告保留逐步位置／速度误差，状态为 `replay_mismatch`，不授予精确重放或 Harbor 评分资格。未修改共享求解器或放宽比较容差。安装包构建已核对两档任务模块、四个资源文件和 catalog 哈希；这只证明资源被打包。

准备与验收证据位于 [本轮运行目录](../../../runs/test_results/blanket_below_easy_20261005/)。各子目录保留实际源码快照、配置、资源使用日志、报告及共享录像。初态准备、短时静置与机器人完整解题分别报告，不能互相替代。当前已在匹配新源码和资源的独立 v18 镜像中重新冻结四个双模式候选包；旧包不继承新变体，候选的实际评分进度见本文开头。

历史设计截图保留在 [预览清单](../../../runs/test_results/blanket_corner_preview_20261005/preview_manifest.json)，其中黄色角标已被本轮要求撤销；该静态预览曾一次性写入设计位置，只用于确认折法，不能作为正式冻结状态。`below_easy_preview` 仍是独立设计工具，正式 Env 不调用它。

**本地参考动作实测：** `very_easy_oracle_03` 从 ALOHA home 连续运行 **15.905 s / 6362 ticks**，原生 Task success；覆盖率 **97.728%**、最高点 **27.049 mm**、最大速度 **0.0285 mm/s**、最大材料边长比 **1.0771**，已释放撤手并连续稳定 0.5 s。沿用 `pbd_local_patch_v1` 局部辅助抓持。见[运行报告](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03/oracle_report.json)和四路连续录像：[全景](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03/recording/videos/cam_high.mp4) · [低位](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03/recording/videos/cam_low.mp4) · [左腕](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03/recording/videos/cam_left_wrist.mp4) · [右腕](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03/recording/videos/cam_right_wrist.mp4)。[独立审计](../../../runs/test_results/blanket_below_easy_20261005/very_easy_oracle_03_audit/execution_audit.json)逐 tick 核对 6,363 个状态，通过且在同一 tick 确认成功；持抓峰值边长比 1.2441，未丢失抓持，关节越限和机器人／桌面接触力均为零。审计不涵盖所有子步或机器人／布料穿透。此前两次尝试分别因拉伸保护、稳定褶皱高于 30 mm 而未通过；第二次静置被主动中断，末尾证据不完整，保留 `.part.mp4` 和中断记录，不算完整执行。

`easier` 首次从四层角抓取时，抬升触发未抓持下层的拉伸保护；第二次从普通双层区接近后，下降 IK 检查拒绝远端位姿。当前候选将左手材料抓点移到 UV=(-0.17, 0.06)，先打开对折，再展开右前角和整理远边；完整成功尚未验证。后续 oracle 进入 v18+ Harbor Session 运行与独立 grading，本地成功不会直接登记为 `solved=1`。新版本准备记录见 [v18 工作目录](../../../runs/test_results/blanket_below_easy_20261005/harbor_v18/plan.json)。

**2026-10-03 三档 oracle 交接集成：** 已将交接最终源码接入
[planning/blanket_flatten/](../../../topogym/planning/blanket_flatten/routes.py)，包括共享路线、
虚拟手见证、从默认 ALOHA home 执行的 JOINT_ABS 机器人策略及独立逐 tick 审计。
运行入口与参数见 [oracle runner](../../../scripts/oracle_runners/README.md#blanket-easy--medium--hard-双手展平路线)。
交接报告称 easy / medium / hard 的 seed 0、`gathered_archive_v2` 均达到原生 Task success
且独立审计 `accepted_proof=true`，分别为 tick 7156 / 15657 / 33687
（17.9 / 39.1 / 84.2 s），终态覆盖率 100.0% / 99.98% / 93.2%。
easy / medium 各一段，hard 先两端翻页解扭，再重新抓取并旋转拉展；持抓峰值材料边长比
1.247 / 1.292 / 1.293，声明 guard 为 1.3 / 1.5 / 1.5。三档虚拟手见证也在同一初态通过。

上述成功数据来自用户提供的外部交接材料（导出基线 `e49b116e`），完整逐 tick 证据未随文本迁入。
本次集成保留其算法和参数，21 项 CPU 回归通过（Blanket 5 项，通用 runner 16 项），
覆盖审计、三档配置／预算、原生失败退出、CLI 和源码快照；三档冻结资源的哈希校验也通过。
检查记录见 [集成报告](../../../runs/test_results/blanket_oracle_integration_20261003_075624/report.json)。
当前 NVIDIA 驱动不可用，本地 torch 2.12.0+cu126 也不同于交接冻结栈 2.11.0+cu128，
未新增本地物理重跑，未将外部记录登记为本地 `solvability_proof/`。
证明范围限于三个冻结实例、默认参数、CUDA float64 和 `pbd_local_patch_v1` 双指接近准入的
局部辅助抓持；不是纯摩擦抓持，不涵盖任意 seed、难度排序或机器人与布料穿透审计。
外部运行未录视频，现有历史视频的范围不变；hard 覆盖率距 90% 门槛约 3%。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**2026-09-29 三档场景布设（seed=0 已验收）：** easy / medium / hard 已统一为相同八面板纵向聚褶，目标扭转角分别为 **0° / 135° / 270°**，实现见 [gathered.py](../../../topogym/tasks/blanket_flatten/gathered.py)。布料尺寸 0.60 × 0.48 m、粒径 8 mm、网格 12 mm、褶角 72°、轴向比例 0.92、中心 XY=(-0.1356786, 0.15) m，材质和桌面摩擦共用。难度标签仍是设计目标，不能从目标角度推导实际解题难度。旧五折保留为 `simple_folds` / `five_folds`，旧折卷保留为 `fold_roll`；历史视频与物理身份不改。

按本轮用户要求先补布设、暂缓粒子运动问题，新三档采用显式 `scene_layout` 初态范围：仍从平坦材料出生建立真实绑定，使用现有速度控制物理聚褶、扭转、放桌和撤控，保存包含实际速度的完整数值状态。材料完整性、视觉完整性、桌内位置、落桌高度、非局部粒子间隙及非展平形状必须通过；仅静稳速度／漂移资格待验。`qualification.passed=false` 的场景包不会被默认 `released_stable` 接口接受，任务终态也不放宽。准备过程不是机器人解法。**0°/135°/270° 是受控构形目标，释放后会松弛，不能作为最终保存形态的实测扭转角；实际形态以三档初始画面和粒子状态为准。**

固定代表用 `configs/task_variants/blanket_flatten/{easy,medium,hard}_scene.json`，标准入口为 `topogym.make("blanket_flatten", variation_id="easy", seed=0)`（另两档替换 variation_id）。正式 reset 导入初态后从 tick 0 开始，不执行准备步，也不清零布料速度。未准备的 seed 明确要求生成对应状态包，不能静默改 seed 或借用 seed=0。状态严格绑定 CUDA、float64、2.5 ms、4 子步、ALOHA 和源码／资产身份；变更物理配置需要重新准备。

复现时在仓库根目录执行，输出目录必须不存在，建议固定数值库线程数：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONPATH=. TOPOGYM_ASSET_ROOT="$PWD/assets" PYOPENGL_PLATFORM=egl \
.venv-gs121-nyx/bin/python scripts/prepare_blanket_initial_states.py \
  --tier easy --seed 0 --acceptance scene_layout --output <新候选目录>

PYTHONPATH=. .venv-gs121-nyx/bin/python scripts/install_blanket_initial_state.py \
  --candidate <候选目录>

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. \
.venv-gs121-nyx/bin/python scripts/test_blanket_initialization.py \
  --candidate <候选目录> --checks scene-layout --output <新验收目录>
```

默认准备仍要求完整 `released_stable` 资格；`scene_layout` 是本轮显式选择。新状态包不能覆盖已冻结同版本／档位／seed。三档 CUDA/Nyx 的零推进恢复、动作／回溯检查各 1 passed，相关回归 46 passed。初态覆盖率依次为 64.13% / 48.09% / 27.77%。RGB 重复 reset 仍有像素差异，未声明逐像素一致；粒子位置／速度精确恢复。运行证据集中在 [三档布设验收](../../../runs/test_results/blanket_three_tiers_20260929_01/README.md)，下述 2026-09-26 及更早进展为历史记录。

**2026-09-26 当前框架进展：** 已实现平坦出生绑定、离线准备与冻结初态导入。单折工程候选通过撤控稳定性检查，完整恢复和录像见[验收证据](../../../runs/test_results/blanket_initialization_20260926_01/README.md)及[工程计划实施记录](blanket_frozen_initialization_plan_20260926_zh.md#8-本轮实现与真实证据)。八面板聚褶仍有局部接触抖动，默认 easy/medium/hard 尚未切换。下文旧场景、命令、静置门槛和 Rasterizer 录像属于历史实现，不能当作当前标准 Env 的行为或本轮通过结果。

目标是让机械臂把刚掀起、落桌后杂乱堆叠的被子展开并整理平整。初始化先构造悬空复杂布面，确保材料与视觉绑定可靠，再完全释放给重力落桌。基础版直接以层间分离的布面出生；交叉折叠与整团扭转版先在展开状态建立绑定，再受控构造叠层。**机械臂任务从落桌静置验收之后开始。**

当前实现包括新任务参数卡、独立几何与场景、实际绑定审计、三视角重力过程录制、初态验收、机器人抓角展开控制器和释放后展平判据。完整成功执行以实际运行报告为准，初始化预览仍让机器人停在初始姿态。当前材料是 PBD 单层布面近似，尚不模拟有填充物被芯的体积与压缩特性。

**已归档的基础初态完整演示：**[全景 MP4](../../../demos/blanket_flatten/varaition_simple_folds/agentview/2026-09-18_single_arm_clear_home_v1_agentview.mp4) · [斜侧 MP4](../../../demos/blanket_flatten/varaition_simple_folds/front_oblique/2026-09-18_single_arm_clear_home_v1_front_oblique.mp4) · [腕部 MP4](../../../demos/blanket_flatten/varaition_simple_folds/wrist/2026-09-18_single_arm_clear_home_v1_wrist.mp4)。包含悬空出生、重力落桌、机器人辅助抓角展开、释放与撤手静置；这份成功记录使用较简单初态，不代表下述复杂麻花版已完成展平。配套证据保存在 `runs/demo_metadata/blanket_flatten/2026-09-18_single_arm_clear_home_v1/`，原 `runs/demos/blanket_flatten/` 副本保留备份。

**复杂麻花初态的无机械臂展平已通过：**`gathered_virtual_hands_v9` 用最多两个理想抓区完成解扭、展开、铺放与松手静置，末态覆盖率约 100%。详见文末「无机械臂双抓点」的物理证据与三视角视频；这不增加机器人成功实例数。

**七次抓放后的后续整理也已通过：**`gathered_two_hand_relay_v2` 用两个局部角点抓区悬垂展开、重新铺放，覆盖率从 75.70% 提高到 99.988%，松手后自由静置 10 s。可直接看[斜侧视频](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/detail.mp4)；下文「七次抓放后的继续整理」列出三路视频与验证范围。这是从保存形状开始的新无臂物理运行。

**此前 ALOHA 视频只是七次抓放后的局部整理试验，尚未展平。** `aloha_refinement_v4` 已实际执行双臂接近、夹取、掀层、空中平移、释放和失败后的静置，公共 `topogym.recording.prepare/session` 在线录制四路。当前瓶颈是第二个角仍被覆盖，见下文「ALOHA 双臂与公共录制」。可先看[全景视频](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/cam_high.mp4)。

**从指定原始麻花落桌状态开始的 ALOHA 两轮尝试也已完成录制，但都未跑通。** 两轮均从默认 neutral pose 连续接近，公共 record 保存四路。第二轮把整张布抬离桌面后仍触发解扭拉伸保护，尚未进入解折层、铺平和最终静置；当前推荐看[第二轮全景](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v2/recording/videos/cam_high.mp4)，细节见「从原始拧转落桌状态开始的 ALOHA 尝试」。这些失败录像不放入正式 `demos/`。

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

# 只检查物理，不录制或放置机器人
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.preview \
  run.render=false run.include_robot=false \
  task.geometry.seed=1 run.output=runs/environment_bootstrap/blanket_flatten/seed_1_probe

.venv-gs121-nyx/bin/python -m unittest tests.check_blanket_flatten tests.check_configs_compose -v
```

默认产物在 `runs/environment_bootstrap/blanket_flatten/seed_0_soft_drop/`：`report.json`、解析配置、带材料坐标及绑定表的 `particle_trace.npz`、出生 OBJ 和材质，以及由共享录制模块 `topogym.recording` 在 `recording/` 下生成的 `agentview / front_oblique / wrist` 三路同步视频、逐步状态、事件（`birth`、`initial_state_accepted/rejected`）和验证抽样图。落桌是真实物理步进，录制走 `lab_default_v1` 实验室预设，`task_result.execution_kind=gravity_settle_preview`，不计为机器人任务。预览采用 Genesis rasterizer，直接检查 PBD 的原生 visual 网格，并复用实验室内部点光源照亮褶皱。`task.vis_mode=particle` 可生成粒子诊断版本，使用单独输出目录保留对照。

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

# 冻结该次物理状态为共享回放来源，并经公共 replay 生成三路同步视频（输出 <run>/render，来源在 <run>/render_source）。
# 失败运行须显式传 --allow-failed，仅供诊断。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.recording_adapter \
  runs/environment_bootstrap/blanket_flatten/robot_example

# 仅当完整执行、独立静置和全部视频通过后才可正式收录。
.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.archive \
  runs/environment_bootstrap/blanket_flatten/robot_example \
  --stability runs/environment_bootstrap/blanket_flatten/stability_example --run-id single_arm_v1
```

物理运行保存解析配置、源码快照、逐步报告和 `physical_trace.npz`。`recording_adapter.snapshot` 把粒子、全部关节状态和验收报告冻结成带 SHA-256 的 `source_manifest.json`，`BlanketBinding.restore` 逐帧恢复并返回重建误差，公共 `replay(restore_tolerance=1e-6)` 负责取帧、编码与验证，`replay_report.json` 记录零积分与恢复误差；机械臂 0–7 连杆与布面的净空在恢复时按每秒和阶段切换抽样，写入 `robot_motion_review.json`。三路 `agentview / front_oblique / wrist` 来自 `lab_franka_v1` 预设，[`blanket_flatten_recording.yaml`](../../../configs/camera_configs/blanket_flatten_recording.yaml) 只抬高斜视机位；不重建夹爪被动关节，不改写物理来源配置。这是已有物理执行的呈现，不代表又完成了一次动力学运行。

正式归档入口会拒绝失败、未松手、动作缺帧、粒子瞬移、少于三路相机或静置不足的记录，并完整解码视频、校验帧数/时长与副本哈希。视频独立复制到 `demos/blanket_flatten/varaition_<id>/<camera>/`，报告和 Markdown 记录复制到 `runs/demo_metadata/blanket_flatten/`；不新建或更新 HTML。未通过的尝试留在原始运行目录，不能计为完整 demo。

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

# 来源 report.mode=stability 时自动使用初态资格检查；视角固定为共享三路。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.recording_adapter \
  runs/environment_bootstrap/blanket_flatten/spiral_example
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
  -m topogym.tasks.blanket_flatten.recording_adapter \
  runs/environment_bootstrap/blanket_flatten/cross_twist_example
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

**独立物理稳定性复核通过；复杂初态的完整机器人展平尚未通过。下节双抓点外力版已完成展平。** `gathered_selected_stability_v1` 在 2.4 s 初态验收后自由静置 10.0 s，稳定窗口最大位移 0.1431 mm；全程最大材料 / 视觉边长比为 1.09435 / 1.01251，没有桌外粒子或非有限位置。125 个保存帧的三角面自交检查未检出相交。末态覆盖率 19.3335%，最高点 53.881 mm。见[稳定性报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_selected_stability_v1/report.json)和[逐帧自交检查](../../../runs/environment_bootstrap/blanket_flatten/gathered_selected_stability_v1/self_intersection_review.json)。离散帧检查不是连续碰撞证明。

现在可看的较长动作诊断为 `gathered_robot_v8`：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/wrist.mp4)。三路各 1742 帧、10 fps、174.2 s，均已完整解码、核对同步和 SHA-256。它连续记录七次抓放，包括两次拉伸保护释放，覆盖率达到 75.7%，仍有被覆盖的角；第八次接近时因重复选回已展开的角而主动结束，**属于未完成诊断，不计为成功 demo**。3510 个保存帧未检出布面自交；臂部 link0–7 的离散复核最小净空 81.71 mm。详情见[执行报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/report.json)、[臂部复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/robot_motion_review.json)及[视频核验](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v8/render/video_verification.json)。

抓取采用双侧指垫接近检查后的局部粒子附着辅助，刚体–布料 PBD 耦合关闭，因此不能宣称纯摩擦抓持。布角及替代布边都要求 8 mm XY 邻域内上方高度差不超过 3 mm，到达后和闭爪后再次检查。每次释放后通过真实关节控制回位；动作中不写粒子位置、不重置机器人姿态。材料边长比达到 1.20 时主动松手，原有 1.30 硬失败门槛保持不变；保护松手不等同于目标放置完成。

`initial_state.py` 先核对材料坐标、面索引与视觉支撑表，在首次物理步进前设置一次选定位置和零速度，保留材料静长并保存独立 `selected_initial_state.npz`。由于原记录没有完整动力学状态，本次是**从选定形状开始的新物理运行**，不是原轨迹续接。源快照内容哈希、帧号及初始速度必须与独立稳定性运行一致。

高抬试验 `gathered_robot_v9` 使用 [`blanket_flatten_gathered_peel_robot.yaml`](../../../configs/blanket_flatten_gathered_peel_robot.yaml)，布边抬升 160 mm、悬垂 0.6 s、搜索范围 240 mm，并循环处理各端。三次抓放后覆盖率 73.2%，第四次回落到 67.8%，随后因剩余角点受工作区限制而在完整物理外步边界中止；末态覆盖率 68.0%，无活动抓持。三路各 1199 帧 / 10 fps / 119.9 s，完整解码通过：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/render/wrist.mp4)。2425 个保存帧未检出自交，臂部离散复核最小净空 70.74 mm。它同样未完成展平。

`gathered_robot_v10` 使用 [`blanket_flatten_gathered_crosswise_robot.yaml`](../../../configs/blanket_flatten_gathered_crosswise_robot.yaml)，目标中心 `[-0.15, 0] m`、平铺方向 90°，四角水平半径 0.347 / 0.714 m；旧目标为 0.292 / 0.797 m。跨侧搬运的直线路径若进入底座附近禁区，会经过前侧通道。静态端点与 104 姿态绕行检查分别最大误差 0.456 / 0.215 mm，但实际展开仍失败：八次均触发保护释放，180.235 s 时因持续拉伸与重复释放主动中止；末态覆盖率 45.4%、最高点 60.09 mm、95 分位高度 44.77 mm、材料边长比 1.26378，均未达到展平要求。峰值材料边长比 1.29754，未超过 1.30 硬上限；未出现非有限位置、桌外粒子或穿桌。3606 个保存帧未检出自交。详情见[执行报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/report.json)和[本次结果记录](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_study/result.md)。该版未通过最终自由静置验收，也不计为完整成功 demo。

v10 的三路采样诊断也已完成：[全景](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/agentview.mp4) · [斜侧](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/front_oblique.mp4) · [腕部](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v10/render/wrist.mp4)。每路 359 帧、2 fps、179.5 s，覆盖动作前一秒至停止时刻，完整解码、同步及哈希核验通过；粒子和关节回读误差为 0，臂部离散复核最小净空 124.80 mm。它是失败诊断，低帧率也不适合判断快速瞬间的接触细节；原始 20 fps 状态轨迹仍完整保留。

上述机器人试验已完成所选初态的独立稳定性验证，并保留实际动作诊断；**仍未生成成功的复杂初态完整机器人展平 demo**。相关自动检查共 34 项测试、142 个子检查通过，不能替代实际任务成功。

各版视频分别由同一次实测粒子及全部关节状态重渲染，渲染不推进物理。源轨迹 20 fps，v8 / v9 视频规则采样为 10 fps，v10 为 2 fps，均保留末帧并覆盖整段执行时间。归档要求完整动作通过、松手后的终态稳定、独立初态稳定性一致、逐帧自交检查完整、臂部复核通过、画面复核通过，以及三视角解码与同步通过。成功视频写入 `demos/blanket_flatten/varaition_<id>/<camera>/`，其他证据写入 `runs/demo_metadata/blanket_flatten/`；本次未覆盖既有简单初态的成功副本。

## 从原始拧转落桌状态开始的 ALOHA 尝试

`blanket_flatten_aloha_full` / `bimanual_full.py` 单独接入完整流程尝试，起点固定为 `photo_gathered_twist_v1/physical_trace.npz` 第 234 帧，并核对源 SHA-256。仅在初始化时把原始布形平移到 ALOHA 两臂之间；材料、拓扑、视觉绑定和高度不变，布速归零，之后由物理与实际关节伺服推进。它不是旧 `gathered_robot_v8` 局部整理录像的延长或拼接。

机器人采用上游 ALOHA neutral pose，公共 `recording.prepare(preset="lab_default_v1")` / `session` 连续记录默认姿态、接近及后续动作，保留 `cam_high / cam_low / cam_left_wrist / cam_right_wrist`。阶段规划是两端局部抓取、抬升解扭、释放重抓、逐层展开、铺放、全部松手后 10 s 静置。每次抓取仍使用双侧指垫距离门控的局部 link 附着，不能称为纯摩擦夹持。

初始 CPU 检查找到一组可达解：布中心平移到 `[-0.1356786, 0.20]`，长轴沿世界 X；沿长轴方向接近两端最高的可见局部布片，抬高 20 cm，两端计划转角约 +197° / −135°。两端共同增加 30°，保留相对解扭量并避开右腕限位。默认姿态到解扭末端共 1303 个采样状态通过 IK、关节限位和机器人碰撞检查；接近阶段非手指与初始布面的离散最小净空约 72 mm。这只验证运动学，不能证明局部抓点足以带动整束布解扭。

第一轮 `aloha_full_twist_v1` 连续执行 **36.865 s**，完成默认姿态接近、两端局部抓取、20 cm 抬升及大部分反向转腕，未进入解折层阶段。36.595 s 时材料边长比升至 1.268814，触发 1.25 的释放保护；随后自由下落在 36.865 s 达到 1.302076，超过原有 1.30 完整性上限，停止。不能称为物理稳定或完整任务成功。

[全景 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v1/recording/videos/cam_high.mp4) · [低位 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v1/recording/videos/cam_low.mp4) · [左腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v1/recording/videos/cam_left_wrist.mp4) · [右腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v1/recording/videos/cam_right_wrist.mp4)。四路均为 640×360、5 fps、185 帧、37.0 s，公共校验通过完整解码与同步。186 个保存布网格未检出三角面自交，非手指机器人/布面离散最小净空 69.879 mm；这些检查不能抵消材料拉伸超限。

低位图像和轨迹确认，抬升后仍有布层处于桌面接触高度。22.4–36.4 s 内，实际左右腕绕长轴分别转约 +169.1° / −115.6°，整个端部截面的拟合转角只变化约 8.4° / 9.3°。当前抓到的是表面局部布片，不能把理想双手的整条、多层端带约束等同于实际夹爪；截面拟合只是形状统计，不是精确扭转量。证据见同目录 `untwist_diagnostic.json`。

第二轮 `aloha_full_twist_v2` 连续执行 **34.655 s**，仍从相同原始布形及默认 home 开始，抬升改为 36 cm。27.875 s 时整张布的最低点离桌 **76.80 mm**，通过至少 15 mm 的离桌门槛；根据实测悬空形状重规划为约 **+183.39° / −88.49°**，绕实际局部夹点反向转腕。这次在 34.26 s 达到边长比 1.250215 并释放；下落又在 34.655 s 达到 1.301460，停止。仍未进入解折层、铺平与最终自由静置，不能标为稳定或成功。末帧覆盖率 16.88%，布料仍在下落，不是稳定末态。

[第二轮全景 MP4（推荐）](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v2/recording/videos/cam_high.mp4) · [低位 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v2/recording/videos/cam_low.mp4) · [左腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v2/recording/videos/cam_left_wrist.mp4) · [右腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_full_twist_v2/recording/videos/cam_right_wrist.mp4)。四路均为 640×360、5 fps、174 帧、34.8 s，解码和同步检查通过。高举阶段低位镜头会裁到夹爪，`visual_review.json` 如实标记该取景限制；全景可看到完整布面。

第二轮 175 个保存网格未检出自交，非手指机器人/布面离散最小净空 70.396 mm，最高已完成段的 TCP 误差 0.286 mm。独立 `initial_identity_review.json` 核对原始布形第 234 帧、刚性平移、默认关节姿态和视频第 0 步，粒子首帧坐标误差仅 1.48e-8 m，关节误差为零。实际腕部转角与整个端部截面拟合角仍明显不同，说明两处表面局部抓持不能直接等同于此前理想双手的整条多层端带抓持。该结果只否定当前抓法与动作策略，没有证明 ALOHA 硬件无法完成任务。

实现已经接入后续逐层抓取、展开、铺放和 10 s 最终静置，但这两轮都没有走到这些阶段，尚无本初态的实际验证。松手后的关节伺服撤手已加入并通过模型预检，同样没有在本轮执行到。下一步需要改变多层布束的抓取/分段换抓策略。45 项相关自动检查通过；失败录像、完整轨迹及检查证据均留在各自 `runs` 目录。

复现时必须指定新目录：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.bimanual_full \
  --config-name blanket_flatten_aloha_full_high_lift \
  run.output=runs/environment_bootstrap/blanket_flatten/aloha_full_twist_new
```

## ALOHA 双臂与公共录制

入口为 [`bimanual.py`](../../../topogym/tasks/blanket_flatten/bimanual.py) 与 [`blanket_flatten_aloha_refine.yaml`](../../../configs/blanket_flatten_aloha_refine.yaml)。本次从 `gathered_robot_v8` 七次抓放后的保存形状开始新仿真，布初速度为零；初始摆位在桌面内整体转 **90°**，参考中心从 `[-0.10, 0]` 移到 `[-0.1356786, 0.10]`，变换矩阵写入报告。出生网格、粒子材料身份和视觉支撑保持原样，只在首次物理步前恢复一次转向后的布形。机器人从配置中已检查的桌面上方 **12 cm** 开爪待机姿态开始。这不是旧单臂运行的动力学续接，也不代表原始麻花初态的完整机器人流程。

左右臂先同时提交关节目标，再推进共同物理步。每段运动先检查采样 IK、限位和模型碰撞，执行后核对实际末端误差。抓取点使用材料坐标候选和实测遮挡检查；夹爪必须接近、闭合，两侧指面距离和局部材料范围通过后，才将小块布绑定到**实际夹爪连杆**。运行中不写机器人关节位置或布粒子位置，不修改材料静长。PBD 的机器人软体接触力耦合仍关闭，因此这是**局部绑定辅助抓持**，不是纯摩擦夹持或视觉策略验证。

`aloha_refinement_v4` 的 **19.55 s / 3910 步**连续试验完成：右臂夹住外露角附近 10 个粒子，左臂夹住覆盖层附近 28 个粒子；左臂抬起约 7 cm，保持高度向内继续平移约 3.5 cm，松开覆盖层，再检查目标角。目标角的顶部遮挡由 **9.63 mm** 变成 **27.51 mm**，仍不能按当前从上向下接近的策略夹取；17.55 s 时结束换抓尝试，释放剩余抓持并自由仿真 **2 s**。最终覆盖率 **74.206%**，低于初始约 **75.71%**，最高点 **27.919 mm**，没有达到平整目标，也未进入后续悬垂展开和反馈铺放阶段。配置中的后续动作实现尚未通过机器人完整执行验证。

本轮全程最大材料 / 视觉边长比分别为 **1.151315 / 1.018848**，没有非有限位置、桌外粒子或穿桌；99 个保存粒子网格未检出自交。已完成运动段的最大末端位置误差 **0.756 mm**，最大姿态误差 **0.110°**；782 次实测关节姿态的模型碰撞检查未触发停止，模型测得非基座几何离桌最小 **2.663 mm**。这些都是该次诊断的离散检查，不构成连续碰撞证明或完整物理资格。见[物理报告](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/report.json)、[自交复核](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/self_intersection_review.json)和[双臂运动复核](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/bimanual_motion_review.json)。

前置试验均保留：v1 因改变出生参考位置导致支撑索引不一致，在执行前被拒绝；v2 在闭合时检测到两指约 0.334 mm 穿入，随后按原模型指面几何将本任务的闭合导轨位置改为 **0.0105 m**，没有放宽碰撞门槛；v3 成功双臂抓取和掀层，但主动回落覆盖层时在材料边长比 **1.265618** 触发释放。v4 改为空中移开后释放，避免了该次拉伸停止，仍未解决被覆盖角的换抓。

视频目录是 `runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/`：

- [高位全景 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/cam_high.mp4)
- [低位侧视 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/cam_low.mp4)
- [左腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/cam_left_wrist.mp4)
- [右腕 MP4](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/videos/cam_right_wrist.mp4)

四路均为 **640×360、5 fps、98 帧、19.6 s**，来自同一次在线执行，通过公共模块的完整解码、同步、时间映射和哈希核验。共享实验室和桌面兼容，保留该 PBD 任务原有光栅渲染器；使用公共 `prepare/session`，没有任务私有视频 writer。阶段事件和全部机器人关节状态在公共录制目录，布粒子状态另存 `physical_trace.npz`。默认 binding 明确保留 `render_state_complete=false`、`physics_resume_supported=false`，不冒充通用软体离线恢复。见[录制验收](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/validation.json)和[画面复核](../../../runs/environment_bootstrap/blanket_flatten/aloha_refinement_v4/recording/visual_review.json)。本次没有进入正式 `demos/`，已有简单版不变。

相关控制、初态恢复、双臂配置和公共录制检查共 **40 项通过**。用新目录重试：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYOPENGL_PLATFORM=egl \
  .venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.bimanual \
  run.output=runs/environment_bootstrap/blanket_flatten/aloha_refinement_new
```

## 七次抓放后的继续整理（2026-09-21）

**后续双角点整理已通过。** `gathered_two_hand_relay_v2` 从 `gathered_robot_v8` 七次抓放后的保存形状开始，用两个半径 **18 mm** 的局部角区完成悬垂展开、重新铺放与松手静置。全程 **37.02 s**，27.02 s 释放全部抓持，再自由静置 **10 s**；覆盖率从 **75.70% 提高到 99.988%**，高度 95 分位 **2.00 mm**，最高点 **5.963 mm**。全程最大材料 / 视觉边长比分别为 **1.20742 / 1.04006**，无非有限位置、桌外粒子或穿桌，视觉绑定的非局部支撑数为 0。372 个保存网格均未检出自交；最终稳定窗持续 8.52 s，最大位移 **3.303 mm**。这是一次固定形状的通过记录，离散自交复核不是连续碰撞证明。

入口是 [`blanket_flatten_virtual_hands_relay.yaml`](../../../configs/blanket_flatten_virtual_hands_relay.yaml)。动作依次为：抓同一短边的两个角 → 提至约 65 cm 高，让整片布脱离桌面 → 配合抓区转向展开宽度 → 按自由下边缘的实测位置逐步铺回桌面 → 松手静置。全过程只有两个局部抓区，**没有整条边夹持或粒子位置动画**。抓区仍按材料坐标直接选择，未验证手指接近、夹取或机器人可达；这验证了理想双手操作下的后续可展平性，不能计为完整机器人成功。见[物理报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/report.json)、[外力复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/external_review.json)及[逐帧自交检查](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/self_intersection_review.json)。

视频目录：`runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/`。三视角：[全景 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/overview.mp4) · [斜侧 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/detail.mp4) · [俯视 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/topdown.mp4)。每路 **187 帧 / 5 fps / 37.4 s**，覆盖同一次后续整理的全部物理记录，完整解码、同步与哈希核验通过，粒子回读误差为 0，初态、悬垂、铺放、松手和三视角终态画面复核通过。见[视频核验](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/video_verification.json)及[画面复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_two_hand_relay_v2/render/visual_review.json)。本次从旧记录第 3509 帧形状、零初速度开始，**不是旧七次抓放的动力学续接，也未拼接旧视频**。它保留在开发运行目录，没有替换正式机器人 demo。

七次抓放只完成粗展开，不能作为平整终态。新增试验配置 [`blanket_flatten_gathered_refine_robot.yaml`](../../../configs/blanket_flatten_gathered_refine_robot.yaml) 在七次粗拉之后继续根据布形选点，最多允许 32 次动作；已放好的角不再反复优先选取。后续目标收紧为覆盖率至少 **98%**、高度 95 分位不超过 **6 mm**、最高点不超过 **12 mm**，最后释放全部抓区、自由静置 **10 s**。材料、重力、1.20 拉伸保护释放和 1.30 硬失败门槛不变。这仍是试验策略，未取得完整机器人成功记录。

`gathered_refinement_probe_v1` 从 `gathered_robot_v8` 七次抓放后的末帧形状重新开始：第一次追加布边整理将覆盖率从 **75.71% 提高到 88.99%**，最高点降至 **15.16 mm**，但仍有两个角被覆盖；第二次抬拉内部褶皱没有继续改善。1145 个保存网格未检出自交。`probe_v2` 改抓附近边带后仍约 88.5%，两个角未露出；704 个保存网格未检出自交。`probe_v3` 试着把覆盖层向内掀起 8 cm，回落时在材料边长比 **1.20084** 触发保护释放，覆盖率降至 **82.44%**，两个角仍未露出；536 个保存网格未检出自交。不能把这些局部试验记为成功展平。

上述单臂局部试验恢复的是粒子形状和零初速度，机械臂另从 home 开始，**不是旧七次抓放轨迹的动力学续接**，也没有与旧视频拼接。运行报告标记 `execution_scope=refinement_diagnostic`，即使局部平整条件通过，也不能自动成为复杂麻花初态的完整机器人 demo。

[`blanket_flatten_virtual_hands_refine.yaml`](../../../configs/blanket_flatten_virtual_hands_refine.yaml) 保留双抓区局部掀层试验：一手抬住覆盖层，再抓住反折角展开。`gathered_two_hand_refinement_v1` 因翻转方向导致材料边长比 1.30040 而停止；修正方向后的 v2 在持续悬空张力下回落超时；v3 改为边展开边落桌后完成第一处折角，但第二处在边长比 1.30146 时被拒绝。它们均未通过，最终采用上面的整片悬垂、反馈铺放流程。相关自动检查共 **50 项测试、153 个子检查通过**。

## 无机械臂双抓点：先解扭，再展开折层（2026-09-21）

**`gathered_virtual_hands_v9` 已完成选定复杂初态的双抓点外力展平。** 同一次连续物理运行共 54.38 s，44.38 s 时释放全部抓区，再自由静置 10 s。最终覆盖率从 19.33% 提升至约 100%，最高点与 95 分位高度均为 2.00 mm；最大材料 / 视觉边长比均收敛至约 1.000。全程最大材料边长比 1.25657，低于原有 1.30 硬门槛；最大视觉边长比 1.05533，未出现非有限位置、桌外粒子或穿桌。稳定窗持续 9.38 s，窗内最大位移 6.526 mm，小于 8 mm 门槛。545 个保存网格均未检出三角面自交。见[物理报告](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/report.json)、[外力资格复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/external_review.json)及[逐帧自交检查](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/self_intersection_review.json)。这是该实例的一次通过记录，尚未完成重复执行、半步长或随机初态的资格验证；离散自交检查不构成连续碰撞保证。

视频目录：`runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/`。三视角：[全景 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/overview.mp4) · [斜侧 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/detail.mp4) · [俯视 MP4](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/topdown.mp4)。每路 273 帧、5 fps、54.6 s，完整解码、同组同步、源文件和视频 SHA-256 核验均通过，粒子状态回读误差为 0。已复核初态、解扭、悬垂展开、释放和三视角终态关键帧，未见撕裂或绑定错位；松手后抓区标记消失。见[视频核验](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/video_verification.json)和[关键帧画面复核](../../../runs/environment_bootstrap/blanket_flatten/gathered_virtual_hands_v9/render/visual_review.json)。这些是外力操作视频，未替换正式机器人 demo。

入口为 [`virtual_hands.py`](../../../topogym/tasks/blanket_flatten/virtual_hands.py) 与 [`blanket_flatten_virtual_hands.yaml`](../../../configs/blanket_flatten_virtual_hands.yaml)。沿用选定的 `photo_gathered_twist_v1` 落桌形状，首次步进前恢复一次位置并设零速度。开始后仅给抓区施加受限速度，未再次写入布粒子位置；重力、PBD 材料、静长、拓扑及视觉绑定均保持原样。

任意时刻最多两个抓区。首先夹持两端各 15 mm 的材料带，包含折叠后多个层；随后换成同一短边上两个半径 18 mm 的局部角区。抓区是外部驱动的固定粒子约束，按材料坐标直接选择，换抓没有模拟手指接近和接触。这验证理想双手操作下的可展开性，**不能计为机器人或纯摩擦抓持成功**。

动作顺序为：

1. 抬高两端约 30 cm，两端分别反向旋转约 168° / 166°，先消除整束扭转。
2. 保持两端支撑将长条转为竖直，再松开下端，避免直接释放水平布束造成下坠冲击。
3. 在空中换抓上边两个角；一边纠正角区朝向，一边向两侧展开折层。
4. 将展开的布移到铺放区域，依据自由下边缘的实测位置调整落桌轨迹，避免固定轨迹在布边滑动后重新堆出褶皱。
5. 松开所有抓区，继续自由仿真 10 s，按原有覆盖率、高度、材料完整性和稳定窗口验收。

物理状态以 10 fps 保存。三视角由同一次状态记录重渲染，渲染不推进物理；橙色、绿色箭头仅标示两个抓区。外力结果单独写入 `external_review.json`，始终保留 `full_robot_task_verified=false`；逐帧自交检查、MP4 完整解码和同步检查与动作验收分别记录。

对照试验解释了本版动作顺序：水平布束直接松开一端会产生下坠冲击；固定角区朝向单独外拉，或先原地转角再外拉，都会使局部边过度拉伸。v8 将转向和外拉同步后已能悬垂展开，但固定铺放轨迹因下边缘滑动而重新堆出褶皱，在材料边长比 1.31596 时停止；v9 改用下边缘位置反馈后通过全部原有门槛。此前记录均保留为失败诊断，不计成功次数。相关自动检查共 **42 项测试、150 个子检查通过**。

复现时使用新的输出目录：

```bash
OPENBLAS_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.virtual_hands \
  run.output=runs/environment_bootstrap/blanket_flatten/virtual_hands_example

.venv-gs121-nyx/bin/python -m topogym.tasks.blanket_flatten.review_preparation \
  runs/environment_bootstrap/blanket_flatten/virtual_hands_example

# 无机器人外力运行没有腕相机，当前共享 Franka 预设无法回放；保留物理轨迹与报告，视频待单独预设。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  -m topogym.tasks.blanket_flatten.recording_adapter \
  runs/environment_bootstrap/blanket_flatten/virtual_hands_example --fps 5
```
