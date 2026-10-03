# 双爪互锁

## 2026-10-03：接续 easy / medium / hard 交接工作

已导入交接中的三档物体路线、耦合双臂 IK、带积分补偿的普通 JOINT_ABS 策略和独立审计。
没有导入缺失原始证据的旧 `qualification.py` 成功声明，也没有用旧任务文件覆盖本地实现。
来源全文及逐文件 SHA-256 位于 [本轮目录](../../../runs/test_results/claws_handoff_integration_20261003/)
的 `handoff.txt` / `import_manifest.json`。各次运行另存完整源码快照与 manifest。

本轮 easy / medium / hard 的目标按根目录约定统一为：两件完整几何可由一个平面分开，
平面间隙至少 10 mm，双件线速度不超过 1 mm/s、角速度不超过 0.02 rad/s，保持 0.5 s；
允许继续抓持，终态版本为 `claws_separation_v1_grasp_contact_2mm`。正的三角表面间隙本身
不足以认定解锁。绿色区域保留作场景标记，不再要求搬运。已验收的 very_easy / easier
保持下面记录的入区目标、几何和终态版本。

hard 采用 `pregrasp_scaled_inset3mm_weld_v4`：保留 0.68 整体尺度与原尺寸
30 × 28 × 24 mm 握持块，两件三角网格顶点沿内法线移 3 mm；显示与碰撞共用该实体。
两件均为单连通水密实体，质量分别约 83.27 / 83.19 g，初始表面间隙约 9.43 mm。
原 Wang 路线在新几何上重新获得 **4 mm 连续净空证书**（旧 hard 为 0.5 mm）；
[六轴直拉反例](../../../runs/test_results/claws_handoff_integration_20261003/hard_inset3_controls/straight_pull_controls.json)
均在 10–197.5 mm 位移内发生真实网格碰撞。未修改摩擦、机器人增益或 Task 的
1 mm 普通接触／2 mm 已持件手指穿透阈值；旧 hard 的成功或失败资格不转移到新版本。

| 档位 | 当前物体证书 | 本地连续物理执行 | 独立审计 |
| --- | --- | --- | --- |
| easy，原几何 | 1 mm | 18.55 s / 742 ticks，原生成功 | 通过 |
| medium，原几何 | 4 mm | 31.275 s / 1,251 ticks，原生成功 | 通过 |
| hard，3 mm 收薄版本 | 4 mm | 208.225 s / 8,329 ticks，原生成功 | 有界滑动接触审计通过 |

hard 的实际路线有 3 个件间接触 tick，最大力 3.412 N，引擎穿透最大 0.173 mm。
因此不将其标为全程无接触：保留严格审计的拒绝记录，另以显式
`--tolerate-piece-contact --piece-force-n 8 --contact-depth-mm .5` 做有界滑动审计。
该模式继续逐 tick 检查独立三角穿透、机器人／桌面／错误持件禁碰、关节限位、
双手取得与持件漂移；没有关闭 Task 的物理失败判据。
全程独立网格复核发现 5 个件间表面交叠 tick，最大三角接触深度 0.429 mm，
低于显式的 0.5 mm 审计上限；其中 3 tick 有引擎件间接触。全场景最大引擎接触
穿透 0.534 mm（包含手指夹持），最小实测臂关节限位余量 0.135 rad，所有禁碰通过。
easy / medium 的默认审计保留交接方案中的 1 s 抓持后脱离窗口：该窗口内可以消除
取得辅助抓持时形成的接触，窗口后禁止件间接触；原生穿透阈值在窗口内也保持启用。

上述运行均为 seed 0、CPU float64、25 ms tick / 40 子步 / control decimation 1，
从任务预抓姿态出发，真实双指接触后取得双手 `contact_weld_v1`，只发送普通机器人动作。
不含标准 home 到预抓姿态的接近段，不证明纯摩擦抓持、多 seed、任务包默认时序或难度排名。
原生 success 与物理审计分别留证；审计覆盖逐 tick 接触、几何、抓持、关节及稳定窗口，
不声称覆盖所有子步的独立三角检查。当前 GPU 驱动不可用，因此没有新增 Nyx 视频。

easy 第一轮因磁盘耗尽导致证据写入失败，保留为 `easy_run01`，不计成功；
恢复空间后从出生状态完整重跑为 `easy_run02`。本轮已完成的早期快照若压缩为
`source_snapshot.tar.gz`，均先逐文件与 `source_manifest.json` 核验；历史运行与其他任务产物未删除。

入口和重渲染命令见 [Oracle 使用说明](../../../scripts/oracle_runners/README.md#claws-easy--medium--hard-交接路线)。
完整三档证据、配置、源码及审计已收录 [正式证明目录](../../../solvability_proof/interlocked_claws/README.md)，
逐文件真实复制并验证 SHA-256，保留原始运行和 hard 严格审计拒绝记录。
新增 [原三档回归](../../../ci_checks/test-interlocked-claws-oracle.py) 验证互锁初态不能成功、
完整分离及双件静稳、hard 连通性／尺寸对等、六轴阻挡和旧证书拒绝；
[原低档回归](../../../ci_checks/test-interlocked-claws-simplifications.py) 的 10 项保持通过。

## 2026-10-02：very_easy / easier 实现

按用户修正建立两个可单独选择的 `experimental` 入口：`interlocked_claws_very_easy` / `very_easy` 和 `interlocked_claws_easier` / `easier`。沿用当前 Claw 的真实 ALOHA、双臂预抓持、共享终态和 `contact_weld_v1` 推荐配置；以 easy 的 260 mm TCP 间距和安装坐标中的 305.28805 mm 高度为基准，仅为几何连接关系调整两手的局部位置并重求 IK。握持块参考 medium/hard，为 30 × 28 × 24 mm。旧三档和 `base` / `seeded` 映射保持原含义。

- **very_easy（v2）：**两件 L 分别位于 xz / xy 平面，两个 40 mm 短边沿 z / −y，彼此垂直交错卡住。两根长杆在高度和侧向各错开 22 mm；短边表面沿 x 留 4 mm 间隙，各短端越过另一短边的投影边缘 6 mm。沿长杆向外拉动 5 mm 时已有短边碰撞见证。版本为 `perpendicular_short_legs_pregrasp_candidate_v2`；原平行短边 v1 的截图和证据保留在旧预览目录。
- **easier：**十字两臂沿 y/z，握杆沿 x，三轴互相垂直。十字总跨度 120 mm，方框外边长 132 mm、净开口 88 mm；框侧沿 y 伸出 28 mm，再接沿 x 的握杆。两握杆横向错开 94 mm。十字头初始位于方框后方，杆穿过开口；初始最小件间净空约 8 mm。沿杆直拉有碰撞见证；仅在框平面内旋转时，十字的最小正方形包络约 94.75 mm，大于开口，需要倾斜并调整位置。

截图使用统一 `topogym.make → Env.reset → SensorFrame`、Nyx + compact_lab，保留原机器人模型；仅在预览进程中增加局部相机。截图位于第 0 个物理步，不能作为抓持稳定、完整解锁或难度通过的证据。

| 变体 | 实际场景截图 | 构建与截图记录 |
| --- | --- | --- |
| very_easy v2 | [垂直短边卡合近景](../../../runs/test_results/claws_simplified_preview_20261002_v2/very_easy/detail.png) · [反向斜视](../../../runs/test_results/claws_simplified_preview_20261002_v2/very_easy/oblique.png) · [卡合处特写](../../../runs/test_results/claws_simplified_preview_20261002_v2/very_easy/joint_closeup.png) · [标准高位相机](../../../runs/test_results/claws_simplified_preview_20261002_v2/very_easy/cam_high.png) | [预览报告](../../../runs/test_results/claws_simplified_preview_20261002_v2/very_easy/preview_report.json) |
| easier | [十字与方框近景](../../../runs/test_results/claws_simplified_preview_20261002/easier/detail.png) · [横向连接俯视](../../../runs/test_results/claws_simplified_preview_20261002/easier/top.png) · [标准高位相机](../../../runs/test_results/claws_simplified_preview_20261002/easier/cam_high.png) | [预览报告](../../../runs/test_results/claws_simplified_preview_20261002/easier/preview_report.json) |

几何源码：[claws_simplified.py](../../../topogym/assets/geometry/claws_simplified.py)。两件均由长方体实体求并生成可视模型，复用现有 `FamilyModel.save` 输出等价的原生长方体碰撞组和实体惯量。几何检查包括单件连通／水密、正惯量、件间初始无穿透、预抓持 IK 和轴向直拉反例。very_easy v2 调整后按相同场景配置重新生成 easier，其全部 8 个场景资产文件与用户认可的上一版逐字节一致。

### 参考策略与代码位置

两档沿用当前 `placement_region_v3_grasp_contact_2mm`：棕色件整体进入绿色目标区、蓝色件留在系统侧，两件低速保持 0.5 s，允许继续抓持。下文历史“分离即完成”的描述不适用于这两个新入口。策略从已确认的任务预抓姿态开始，通过真实双指接触取得 `contact_weld_v1`，不包含 home 到预抓姿态的接近过程。

| 文件 | 职责 |
| --- | --- |
| [claws_simplified.py](../../../topogym/assets/geometry/claws_simplified.py) | 两种实体、尺寸、连接、碰撞模型、惯量和初始抓持 IK |
| [simplified.py](../../../topogym/tasks/interlocked_claws/simplified.py)、[interlocked_claws_very_easy.py](../../../topogym/tasks/interlocked_claws/interlocked_claws_very_easy.py)、[interlocked_claws_easier.py](../../../topogym/tasks/interlocked_claws/interlocked_claws_easier.py) | 共享场景接入及独立变体身份 |
| [simplified_routes.py](../../../topogym/planning/interlocked_claws/simplified_routes.py)、[easier_reference_route.json](../../../topogym/planning/interlocked_claws/easier_reference_route.json) | 连续几何通路、实测初态连接、双手分担分离位移及入区路线 |
| [simplified_preflight.py](../../../topogym/planning/interlocked_claws/simplified_preflight.py) | 原生 IK、关节限位、采样机械臂／夹爪／物体／桌面碰撞检查 |
| [simplified_policy.py](../../../topogym/planning/interlocked_claws/simplified_policy.py) | 实测抓持偏移、误差门控、速度阻尼及普通 EE_ABS 动作 |
| [run_interlocked_claws_policy.py](../../../scripts/oracle_runners/run_interlocked_claws_policy.py)、[run_interlocked_claws_simplified_policy.py](../../../scripts/oracle_runners/run_interlocked_claws_simplified_policy.py) | 兼容旧三档入口；新两档源码冻结、资源监控、共享执行与录制 |
| [test-interlocked-claws-simplifications.py](../../../ci_checks/test-interlocked-claws-simplifications.py) | 结构、可解通路、直拉阻挡、终态反例和旧三档注册回归 |

登记在 [variation_records.py](../../../topogym/config/variation_records.py)，规划 JSON 由 [pyproject.toml](../../../pyproject.toml) 随开发安装包提供。参考路线放在规划模块中，现有镜像裁剪会将其排除；任务几何不依赖该参考解法。旧 easy / medium / hard 的场景代码未修改，`base` 与 `seeded` 仍沿用原三档。

very_easy 参考动作是约 12° 小角度解钩后拉开；easier 使用十段相对旋转／平移通路退出方框。两者的物体间连续净空证书均使用 1.5 mm 余量；双臂预检通过不等于连续机器人碰撞证明，也不代表物理执行成功或难度排名已校准。

### 验收结果

运行命令见 [Oracle 入口说明](../../../scripts/oracle_runners/README.md#claws-两档简化变体)。本轮独立证据保存在 [开发运行目录](../../../runs/test_results/claws_simplified_development_20261002/)，保留各次失败尝试、源码哈希及实际时序。

| 变体 | 完整真实执行 | 媒体与证据 |
| --- | --- | --- |
| very_easy | seed 0，CPU float64，108.775 s / 4,351 ticks；`task_success=True`，低速保持 0.5 s | [无 RGB 报告](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt04_cpu/run_report.json) · [Nyx 录制运行报告](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/run_report.json) |
| easier | seed 0，CPU float64，517.675 s / 20,707 ticks；`task_success=True`，低速保持 0.5 s | [完整运行报告](../../../runs/test_results/claws_simplified_development_20261002/easier_attempt04_cpu/run_report.json) · [实际逐 tick 状态](../../../runs/test_results/claws_simplified_development_20261002/easier_attempt04_cpu/private/physics_states.jsonl)；本次完整执行未开 RGB |

完整执行使用显式 25 ms World tick × 40 solver substeps、40 Hz 控制、终态合同 1，以及声明的预抓持辅助。very_easy 的无 RGB 与 Nyx 运行均成功，物理步数、用时和最大采样接触深度相同。四路解锁／搬运录像来自同一录制运行的 segment 2：[cam_high](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_high.mp4) · [cam_low](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_low.mp4) · [左腕](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_left_wrist.mp4) · [右腕](../../../runs/test_results/claws_simplified_development_20261002/very_easy_attempt05_cpu_rgb/segments/segment_2/videos/cam_right_wrist.mp4)。取得抓持的前 0.2 s 单独保存在该运行的 segment 1，未拼接成新视频。

[交付审计](../../../runs/test_results/claws_simplified_development_20261002/delivery_audit.json)核对了全部 tick 连续性、执行证据完整性、当前 Claws 源码与成功快照一致，以及两手全程未丢失抓持。采样件间最大穿透为 very_easy 0、easier 约 0.000436 mm；包含握持接触的任务件最大穿透分别约 0.881 / 0.626 mm。记录范围是 World tick，未据此声称连续子步接触、完整机器人自碰撞或驱动力资格。上述用时含保守等待，不是难度排名；完整默认 CUDA 物理时序、更多 seed 和全族资格尚未认证。

新增 10 项回归、现有 Oracle 16 项回归、[最终源码的独立 wheel 检查](../../../runs/test_results/claws_simplified_development_20261002/package_check04_final/report.json)通过。几何与参考 JSON 在独立安装中可用，评测镜像排除了规划解法。

### 冻结任务包

通过公共生成器生成并登记到 [tasks/dataset.toml](../../../tasks/dataset.toml)：

- [very_easy privileged](../../../tasks/topogym-interlocked-claws-very-easy-i00-privileged/) / [standard](../../../tasks/topogym-interlocked-claws-very-easy-i00-standard/)
- [easier privileged](../../../tasks/topogym-interlocked-claws-easier-i00-privileged/) / [standard](../../../tasks/topogym-interlocked-claws-easier-i00-standard/)

本地镜像 `topogym-local/interlocked-claws-variants:20261002-01`，源码身份 `8f919bfd6ac1017c46e58724863bd190a163f1eded5ae7b0ffcb1ad05d04f9e1`，见[镜像记录](../../../runs/test_results/claws_simplified_development_20261002/harbor_image/report.json)。两个模式的实例文件逐字节一致。任务包保留工具冻结的 CPU、2.5 ms tick × 4 substeps、40 Hz 和终态合同 1；该时序与上方完整参考求解不同。

两档完成真实三步保持、重置和 Nyx 录像，以及独立 privileged verifier 两遍重放：均 `instance_exact=1`、`deterministic=1`、`grader_error=0`，未解题前缀正确得到 0 分，媒体完整，见[评分验收](../../../runs/test_results/claws_simplified_development_20261002/harbor_verifier_retry02/report.json)。初次验证命令的不可写工作目录导致 Nyx 缓存错误，失败记录保留；修正的是验证命令。四包结构／字段检查、数据集清单检查和全库 110 包 tooling v10 身份检查通过。此处没有宣称 standard live 服务全链路、Harbor 完整正例评分或远端镜像发布已经完成。

2026-09-30：medium 与 easy/hard 统一声明 `pregrasp_weld=True`，新评测实例通过 `recommended_grasp_assist()` 启用 `contact_weld_v1`。两只手分别对各自零件取得辅助抓持，保持取得时零件相对 hand link 的位置与朝向；两件之间的相对运动和碰撞仍由物理求解器处理。闭合预抓初态使用 `initial_intent="close"`，仍需双指接触连续满足准入 0.02 s，张开夹爪即解除该手约束。实际启用以实例的 `simulator.grasp_assist` 为准，旧实例不会自动开启；此配置调整不新增完整物理成功记录。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

下一轮开发要求：[medium 锐角双窗 scripted policy 与全流程验收](hedgehog_claws_scripted_policy_plan_20260927_zh.md)。沿用原夹爪已持件且中央互锁的 segment0，验证两窗连续通路与两次定向机制；完整验收区分分离里程碑和当前目标区终态，尚未新增完整成功记录。

> **2026-09-27 更新：** 三档 segment0 已由原 ALOHA 夹爪分别夹住独立 claw，并保持中央互锁；medium 为相对夹爪、55° 锐角双窗和 J 钩；hard 增加平整握柄面。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


更新：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

两件互锁刚体由 ALOHA 双臂完全拆开并短暂停稳即完成，允许继续抓持，不要求搬运、落桌或松爪。新建 agent 任务包采用 spec v5 / `pilot_claw_separation_v2`；历史任务包和结果不追溯改变。当前 A0 为 Genesis 原始爪；B0 同形双螺旋爪和 C0 等尺寸双窗为 MuJoCo 固定原型。

源码：[geometry.py](../../../topogym/tasks/interlocked_claws/geometry.py) · [scene.py](../../../topogym/tasks/interlocked_claws/scene.py) · [variants.py](../../../topogym/tasks/interlocked_claws/variants.py) · [agent_adapter.py](../../../topogym/tasks/interlocked_claws/agent_adapter.py)。
参数入口：[任务卡](../../../configs/task_cards/interlocked_claws.yaml)；场景入口：`python -m demos.environment_bootstrap.interlocked_claws`（仓库根目录的 `.venv-gs121-nyx/bin/python`）。

## 当前状态与边界

B0 已替换为两件完全同形的三爪螺旋结构，单件约 15.06 × 15.06 × 19.17 cm、158.58 g。两边均有三条长螺旋爪臂、基环、辐条和轴向握持杆；双臂反向各转约 100°并拉开，分离后只保持 1.5 s。新视频 16.55 秒、五视角；dt 0.5 / 0.25 ms 的完整机器人执行均通过，无两件穿透或机器人禁碰，最大跟踪误差 0.694 mm。详见[本版证据与视频](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2/README.md)。

七项受力错误动作对照均被阻挡；初态另测 128 个固定姿态直拉方向，均有碰撞见证。旧 B0 到 6 s 已可直接沿轴抽出，新版在 8 s 仍被挡住。连续配合旋转／平移路径通过几何证书；这些检查不等于证明全局最短解或任意绕行动作的难度。单件侧放 20 s 静置在两个时间步下通过；5 s 的竖直握杆与侧放测试未稳定，失败记录也保存在本版归档。

C0 保留之前的 62.05 秒完整执行及半步长复验，A0 保留 158.60 秒参考执行；二者现有视频仍含旧放置／释放流程。三类共 15 路视频，B0 本轮重新执行和录制，A0/C0 未重录。均明确使用预抓取、理想辅助抓持；A0 的独立接触资格仍有缺口。九点外观代表规划尚未全部完成。

## 变体与下一步

`claw_seed_v1` 支持 A0 的共享 seed / EpisodeSpec、保存与恢复；当前接口仍拒绝 B/C。新固定原型完成不等于三族随机物理闭环完成。

## C0 两件结构对等的改造计划

状态：2026-09-21 制定，待实施。以下结构、尺寸区间、动作与检查均为设计目标，尚未建立新版模型或验证可解性。B0 当前结构保留；本计划只改造 C0，并采用“分离后短暂停稳”的任务目标。

### 结构方向与尺度

首选候选是**成对的正交回钩框**：从同一参数模板生成两件，通过相对朝向和交错初态形成互锁。每件具有两组互成约 90° 的开口回钩框、一段错层连接桥、相同数量的内折钩端和尺寸匹配的握持部。两件都承担两阶段的几何约束，保留 C 的明显换轴动作。开口框必须由有厚度、连通、水密的实体构成，避免把两个不可分离的闭环直接做成拓扑套链。

首轮尺度目标为单件含握持部最长边约 20–25 cm，上限约 26.4 cm，以基础 A0 为参照；不能靠延长手柄或放大其中一件补可达性。优先让两件完全同形；若全等方案确实妨碍可解性，只调整成对的局部间隙或钩端，保持相同结构数量，主体尺寸与体积差异目标均不超过 10%。尺寸比较使用各自局部坐标下的主体包络和完整包络，不用不同朝向的世界 AABB 判断大小。

具体参数包括框跨度、框深度、杆件截面、钩端回折长度、开口宽度、连接桥错层量和握持位置。先保留少量参数，结构轮廓通过验证后再细化圆角与材质；圆角进入实体及碰撞几何，不能只修改可视网格。

### 预期动作及有效约束

| 阶段 | 候选相对动作 | 必须验证的结构作用 |
| --- | --- | --- |
| 初态 | 两组回钩交错嵌合，双臂分别抓持一件 | 多方向直接平移被阻挡；无初始穿透 |
| 第一组解锁 | 绕第一轴明显转动并短距离移位；角度先搜索约 60–100° | 一组钩端找到通过开口的姿态；省略转动不能按同一路线退出 |
| 中间转移 | 将连接桥或钩端移入第二组约束允许的空间 | 第一组已让开，另一组仍阻挡直接分离，不能此时提前完成任务 |
| 第二组解锁 | 绕与第一轴近似垂直的另一轴明显转动 | 第二组钩端获得退出姿态；单轴持续转动或省略第二次转动应有实际阻挡 |
| 结束 | 短距离拉开并停稳 | 完全分离，连续保持 1 s；允许继续抓持，不追加搬运、落桌或松爪 |

这只是用于联合搜索结构与运动的候选顺序，不预先认定一定有解，也不宣称必须恰好转 90°。不以视频长度衡量难度；若发现更早即可直接退出，须缩短动作或重新设计尚未发挥作用的结构。

### 实施顺序与验收

| 步骤 | 工作与产物 | 进入下一步的条件 |
| --- | --- | --- |
| C1 旧版诊断与候选结构 | 检查旧 C0 每个阶段的直接退出可能性；生成新成对模型的单件、互锁初态及两次换轴关键姿态图，附尺寸和结构对应表；做少量关键姿态的粗 IK 预筛 | 两件肉眼可见地对等；初态无碰撞；握持位置有初步可达解。图仅标为结构候选 |
| C2 几何与路线联合验证 | 联合调整回钩、开口、错层量和相对路线；保存参数、实体、初态、路线、连续物体间碰撞检查报告 | 实体连通水密、质量/惯量有效；完整相对路线通过连续检查；有可量化的间隙余量，正向解法不是仅靠离散帧看似无碰撞 |
| C3 提前退出与换轴必要性检查 | 在初态及中间阶段测试多方向直拉、反向退出、只用第一轴、跳过第二轴、改变动作次序；用多起点的受限运动规划搜索替代路线，并逐侧检查主要钩端是否真正产生阻挡 | 第二阶段仍有作用；任何找到的单轴或提前分离捷径都作为改型依据。搜索未找到捷径只记为有限预算结果，不视作全局不可行证明 |
| C4 双臂与物理验证 | 在共享实验室桌面坐标下建立新物理场景；完成整条路线的双臂 IK、关节限位/连续性、夹爪与物体/桌面禁碰检查；运行完整机器人执行、半时间步复验及受力错误动作对照 | 各项分别通过才认定固定新版可用。沿用原驱动力上限；明确理想辅助预抓持；不通过直接写位姿、关闭碰撞或放宽阈值解决失败 |
| C5 正式录制与替换 | 用公共录制模块、默认 compact_lab 和匹配的共享桌面/ALOHA 相机预设，输出五路连续视频及自包含证据 | 模块的 MuJoCo 适配及场景检查可用；物理、来源、全程解码、同步和背景实际加载检查通过后，才替换旧 C0 |

几何间隙需结合实测双臂跟踪误差留出余量，而非无限压小开口增加难度。物理检查至少包括非有限状态/引擎告警、原驱动力上限、抓持跟踪、两件接触、机器人禁碰、末段分离与静稳。首轮以现有 C0 的 dt 0.25 / 0.125 ms 为起点；若变更接触参数或时间步，保存原因并对同一新版结构重做相关检查。

沿用现有固定原型的检查上限作为起点：持物跟踪误差 <4 mm / 0.04 rad，两件接触穿透 <0.3 mm，机器人禁碰穿透 <0.5 mm；两次时间步终态差 <3 mm / 0.03 rad。成功要求最后连续 1 s 的分离距离 >20 mm，物理 demo 的线/角速度 <1 mm/s / 0.02 rad/s。比较实测物体间间隙与误差预算，必要时增大几何间隙；这些数值不是新版已经通过的结果。

### 与录制模块和变体生成的关系

公共录制模块目前仍是[待实施的工程计划](../../../legacy/cleanup_20260929/docs/develop/modules/recording_module_plan_zh.md)。C1–C4 可以先开展；从 C1 开始按共享桌面、机器人安装和相机工作空间设计，避免物理验证后再迁移坐标。正式 C5 依赖该模块的配置检查、MuJoCo 适配、同步录制和归档能力；若依赖未完成，先保存实测状态和开发证据，不再另写一套正式录制器。B0 的实验室重渲染属于录制模块接入工作，不在此计划中修改 B0 几何。

新 C0 仍属于 `orthogonal_gate` 宏观家族，只新增模型 revision，不把它计作第四家族，也不覆盖旧资产的含义。首个固定基型通过后，冻结共享结构参数、握持定义与验证报告，再规划族内尺寸/开口/错层微调。几何参数应成对联合采样；位置变化先采用两件整体的共同变换，不独立扰乱互锁初态。记录 family、model revision、seed、实际参数和拒绝原因，未验证范围不进入随机可用池。本计划不生成数据集或 H5。

最终交付：新版成对 CAD/碰撞实体、明确的结构参数与抓持定义、可解路径与 IK、连续几何及错误动作检查、两次时间步的机器人执行证据，以及 `demos/interlocked_claws/varaition_c0_orthogonal_gate/<camera>/` 下 cam_high、cam_low、cam_left_wrist、cam_right_wrist、detail 五个独立 MP4。新实例不继承旧 C0 的通过标签。

## 当前证据

当前正式视频按变体分组：`demos/interlocked_claws/varaition_a0_original/<camera>/`、`varaition_b0_helical_crown/<camera>/`、`varaition_c0_orthogonal_gate/<camera>/`，每组五路完整视频。[当前全部直链](../../../demos/README.md)。旧 B0 视频移到旧归档的 `b0_render/retired_videos` 用于本次前后对照，不再作为当前正式结构。


- [2026-09-19_orthogonal_gate_balanced_physical_v1](../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1)
- [2026-09-21_balanced_helical_separation_v2](../../../runs/demo_metadata/interlocked_claws/2026-09-21_balanced_helical_separation_v2)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 2026-09-27 Scripted policy 首轮实施

新 medium 的反馈执行器、双窗几何搜索及三档摩擦持件诊断已接入，完整机器人路线尚未建立。2 s CPU 基线中 medium 蓝钩相对 TCP 转动约 4.16°，超过固定的 3° 门槛；调整初始指距和半时间步复核仍未消除这一问题。三档 segment0 恢复检查通过不等于抓持或解题通过。当前目标物仍为 Task 指定的棕色件，要求完整入区并低速保持 0.5 s；未开启终态资格。详见[实施、失败诊断和录像](../../../runs/test_results/hedgehog_claws_policy_20260927/README.md)。
