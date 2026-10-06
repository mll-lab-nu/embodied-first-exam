# 开锁

2026-10-05 后续结果：实际限速生成的冻结 v17 补测已完成，`very_easy`、`easier` 的
privileged／standard 四项均为 **grade=1**，见[结果汇总](../../../runs/test_results/harbor_below_easy_20261005_05/summary.json)。
按用户要求，现已纳入[独立 v18 简单档回归](../../../runs/test_results/harbor_below_easy_v18_20261005_01.supervision/state.json)，
使用新镜像、实例与轨迹；v18 尚无本轮成绩，不覆盖上述 v17 证据。

2026-10-05 Harbor 简单档补测：冻结的 merged-v16 修复批中，`very_easy`／`easier` 的 privileged 均取得
`solve=1`，两次评分均为 `deterministic=0`，且未使用 replay hold 或容差放宽。standard 两档均为 0：
源轨迹从零编号的第 171～180 行关节目标变化为 0.04021～0.04166 rad，超过服务每步 0.04 rad，
第一批 400 行被执行为 410 个控制步后，严格回放桥接中止。这 10 行都在 pickup 阶段，不能据此认定插锁策略失败。
见 [正式补测结果](../../../runs/test_results/harbor_below_easy_20261005_02/summary.json)。

两条显式转换时序的 standard 候选曾进入[追加补测](../../../runs/test_results/harbor_below_easy_20261005_04/trial/plan.json)，
后在尚未执行时由新生成方案替代，原计划和证据保留。主仓库另已合入 [生成时限速](../../../topogym/planning/standard_rate.py)，
[Harbor runner](../../../topogym/planning/lock_picking/runner.py) 使用它记录实际受限动作。
这比事后转换更适合作为新参考的生成方式：控制器能在实际受限执行后获得下一次观测。
本次 CPU 检查用该实现处理两条原始目标序列，最大相邻关节变化均小于 0.03856 rad；不计为物理通过。
主仓库已迁移至 v17，不能用上述 v16 成绩替代 v17 或新轨迹的真实验证。

补读并核对其他会话交接后，确认限速为已有提交 `5e1bfa54f`，本次沿用，不重复改写。
新增回归用原失败幅度约 0.041656 rad 验证 EE 编译后的限速输出经过真实 standard 服务循环时
逐行恰好执行一步、没有 clipping，同时检查 Session 终止时不继续提交尾部动作。
oracle merge 5 项、简化 Lock 4 项、bridge 40 项、grading replay 28 项 CPU 检查通过；不计为物理成功。
已完成[新的 v17 两档补测](../../../runs/test_results/harbor_below_easy_20261005_05.supervision/state.json)：
冻结源码，重建两个实例，在实际限速执行中重新生成 privileged 轨迹，再将该轨迹交给 standard，
共四个评分项。只覆盖 very_easy／easier，不重测 easy／medium／hard。
版本和私有代码哈希见[准备记录](../../../runs/test_results/harbor_below_easy_20261005_05.supervision/preparation.json)。
v17 的 R-hold 和固定 GPU 刚体求解分支已经存在；本次不修改判据或再放宽阈值。

鲁棒性 review：`_move_key` 在精确插入阶段以 0.15 mm／0.0003 rad 为收敛目标，固定最多 10 次修正，
超过双倍误差即退出；简化策略还以锁片距零角不超过 2° 作为阶段检查。应优先改进按误差进展驱动的
有界纠偏、基于实际孔轴／槽重叠区的阶段完成检查，以及由孔隙决定的横向／倾角误差预算。
两档杆孔径向间隙只有 1 mm，因此不能统一放宽精度或绕过碰撞检查。当前证据确认了限速兼容失败；
尚未把异机失败逐个归因于这些策略检查，也未修改其阈值。

2026-10-02 两档 oracle：已实现 [SimplifiedLockPickingPolicy](../../../topogym/planning/lock_picking/simplified_policy.py)，复用已有 home 出发的抓取动作，通过 [统一 runner](../../../scripts/oracle_runners/run_lock_picking_policy.py) 的 `--route-mode simplified` 执行。`very_easy` 抓起、抬至孔高后直线插入；`easier` 先让前齿进入第一片槽，转动钥匙，以真实接触带动被动锁片对齐，再直线插入。动作不回退、不换抓，终点允许保持抓持。沿用现有 `contact_weld_v1` 自动辅助抓持：两指接触握柄后自动取得绑定；策略仅提交普通机械臂控制，不直接设置钥匙位姿、锁片角度或绑定关系。

| 变体 | 原生 Task 结果 | 从 home 起仿真时间 | 物理 tick | 独立审计 |
| --- | --- | --- | --- | --- |
| very_easy | success，连续确认 0.5 s | 35.6325 s | 14,253 | 14,254 个保存状态、1,162 次 IK 查询通过 |
| easier | success，连续确认 0.5 s | 48.2575 s | 19,303 | 19,304 个保存状态、1,623 次 IK 查询通过 |

两档均在首个完整策略执行中成功。使用 seed 0、默认 home、CUDA float32、2.5 ms tick／4 子步／40 Hz 控制、Nyx 三视角和公共 `SegmentRunner`／`RecordingSession`；模型、物理参数、成功判据均未为 oracle 调整。每档 1,272 个生成资产与此前冻结的 Harbor 实例逐项同哈希。两次执行各只有一次自动抓持，无重新绑定或回退。easier 第一片从 20° 转至最终约 −1.205°，已在槽齿间隙允许的对齐范围内，第二片保持 0°；转片阶段测得钥匙对第一片的接触力峰值 0.277 N、穿透峰值 2.62 μm。

独立审计重算每个保存 tick 的 Task 判据及稳定窗口，检查 home 起点、动作连续性、IK/FK、关节限位、机器人禁止碰撞与抓持证据，两档均通过。接触检查覆盖每个 World tick 的末子步，不声明连续时间或所有积分子步均已审计。抓持位置取原生 binding 接触证据；World 接触记录不含位置，只能独立比对 link 对、力和穿透。最初 very_easy 审计误要求 World 保存接触位置而失败，修正字段可用性处理后复验通过，失败报告保留。新增 oracle 检查 4 项、原路线 6 项、runner 合同 16 项，共 26 项通过。

两档还分别在新进程中，从默认 home 重新执行原运行记录的原生关节目标；重新创建场景并核对实例与资产身份，不恢复旧物体状态。两次回放均再次获得原生 Task success，成功 tick 与原执行相同（14,253／19,303）。下列三视角来自各自同一次连续物理回放，包含接近、抓取、转片／插入和成功确认；三路均为 848×480、30 fps，分别 1,070／1,449 帧，已完整解码核验：

- very_easy：[主视角](../../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/agentview.mp4) · [侧视角](../../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/front_oblique.mp4) · [腕相机](../../../runs/test_results/lock_picking_oracles_20261002/very_easy_replay01/segments/segment_1/videos/wrist.mp4)。
- easier：[主视角](../../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/agentview.mp4) · [侧视角](../../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/front_oblique.mp4) · [腕相机](../../../runs/test_results/lock_picking_oracles_20261002/easier_replay01/segments/segment_1/videos/wrist.mp4)。

[验证汇总及视频哈希](../../../runs/test_results/lock_picking_oracles_20261002/oracle_validation_report.json) · [very_easy 执行报告](../../../runs/test_results/lock_picking_oracles_20261002/very_easy_attempt01/run_report.json) · [独立审计](../../../runs/test_results/lock_picking_oracles_20261002/very_easy_audit02/robot_process_audit.json) · [easier 执行报告](../../../runs/test_results/lock_picking_oracles_20261002/easier_attempt01/run_report.json) · [独立审计](../../../runs/test_results/lock_picking_oracles_20261002/easier_audit01/robot_process_audit.json)。系统内存采样峰值 44.0%，未触发 90% 停止阈值；CPU 峰值 99.8%，按现有授权仅监控记录。上述 runs 目录对应 `/data/jianwen/topogym/lock_picking_oracles_20261002`，开发证据与缓存均保留。

复现使用 [runner 中的双片命令](../../../scripts/oracle_runners/README.md#lock-的结束规则)，选择 `--variation very_easy` 或 `--variation easier`；完整源码快照、配置、动作、状态和独立审计保存在 [本地 oracle 证据目录](../../../runs/test_results/lock_picking_oracles_20261002)。验证范围限于这两个具名变体的 seed 0；未开展五档难度排序，也未把本地原生关节动作回放等同于 Harbor 公开宽度动作或 standard 服务的完整求解资格。

2026-10-02 两档简化变体：新增具名入口 `lock_picking_very_easy` / `very_easy` 和 `lock_picking_easier` / `easier`，登记在 experimental 池，不改变 `base` 或原三档 seeded 采样。两档均为 **两个被动圆锁片＋双齿钥匙杆＋原有固定 END 板**。沿用 easy 的 Panda/Robotiq 默认 home、实验室布设、160 mm 锁片直径、150 mm 片距、10 mm 片厚、7.5 mm 孔半径、36 mm 钥匙齿半径、V 型托架与物理参数；握柄偏移从 495 mm 缩至 345 mm，保留两倍片距加 45 mm 的原有余量，底座和托架随钥匙长度调整。钥匙仍先放在低于锁孔轴线的托架上，需要抓起并抬至孔高。

- `very_easy`：两片单槽均竖直对齐，初始角度 `[0°, 0°]`；两片限位为 ±3°，位于原有槽齿角间隙内，设计上可直接直线插入。
- `easier`：第二片仍对齐；第一片初始偏转 20°，限位为 −3°～23°。先将第一片转回对齐，再直线插入。保留用户确认的预览结构；后续已完成机器人接触旋转与完整求解，见页首 oracle 记录。

源码：[双片几何](../../../topogym/assets/geometry/lock_picking_simplified.py) · [共享简化参数](../../../topogym/tasks/lock_picking/simplified.py) · [very_easy](../../../topogym/tasks/lock_picking/lock_picking_very_easy.py) · [easier](../../../topogym/tasks/lock_picking/lock_picking_easier.py)。模型完全由包内 Python 构造器生成，无新增外部 Blender 素材或运行目录资产依赖。模型版本 `two_rotor_v1`，判据版本 `terminal_v5_two_rotor_bore_contact`，按两片锁片加 END 共三片板检查有限杆长和插入距离，保留原有接触容差与连续 0.5 s 确认时间，不要求最后释放。

两档接入相同的公共 simulator、观测、动作、回溯及终止流程。`contact_weld_v1` 辅助抓持由任务按实际握柄位置生成：新两档为 key 局部坐标 `(-0.345, 0, 0)`，旧三档仍为 `(-0.495, 0, 0)`；旧五个入口（easy / medium / hard / base / seeded）的 seed 0 归一化 simulator 配置核对一致。Harbor 说明同步描述两片转盘、三片板／六个表面和 365 mm 有效杆长，模板 tooling 升至 11，旧 tooling 10 的文件哈希已冻结。

本地通过 `topogym.make("lock_picking", variation_id="very_easy")` 或 `variation_id="easier"` 选择场景，再使用公共 `env.reset(seed=0)`。需要复现 Harbor 的完整配置（含抓持辅助）时，以各包的 `environment/instance.json` 或 standard 的 `environment/sim/instance.json` 为准。

场景集成阶段按用户要求暂缓 oracle；后续本地 oracle 验证见页首。此前生成的 Harbor 包仍为 `oracle="none"`、无 `solution/`，本次本地成功未改写这些冻结包或 registry 的整体验收资格。短程接口、完整机器人求解、Harbor 资格与难度排序分别记录。

预览采用公共 `Env.reset(seed=0)`、CPU 物理初始化和 Nyx RGB，零物理 tick，机器人保持默认 home；PNG 通过共享 `topogym.recording.segment.save_rgb` 导出。记录包含源码快照、资产哈希、实际初态和资源采样。初次串行渲染分别用时 48.1 / 49.6 s，整卡显存峰值 11,722 MiB / 24,564 MiB，系统内存峰值 31.3%；只证明该次共享负载下能初始化和截图，不是完整物理或机器人成功证据。补拍只改变观察机位，不改变场景或机器人姿态。

[初次预览与资源记录](../../../runs/test_results/lock_picking_simplified_preview_20261002) ·
[清晰视角预览](../../../runs/test_results/lock_picking_simplified_preview_20261002_clear_views) ·
[very_easy 场景](../../../runs/test_results/lock_picking_simplified_preview_20261002_clear_views/very_easy/overview/front_oblique.png) ·
[easier 场景](../../../runs/test_results/lock_picking_simplified_preview_20261002_clear_views/easier/overview/front_oblique.png)。

代码检查：新增双片场景 7 项、原 terminal 10 项、原 route 6 项、公开目标说明 10 项、tooling 合并 11 项，共 44 项通过。新增检查覆盖双片双齿、第一片错位阻挡、对齐后的直线路径、初态未解、三片板终态、连续确认窗口、限位失败和短柄抓持配置，不等同于动态可解证明。旧 easy / medium / hard 的 seed 0 实例身份与 5,085 个生成资产哈希全部不变。执行：`.venv-gs121-nyx/bin/python ci_checks/test-lock-picking-simplifications.py`。

生成四个 privileged / standard 包，执行包结构、字段、Dockerfile、公开说明、验证器隔离和 standard 文本六类检查，共 24 次脚本调用通过（部分按模式跳过，`check-limited-texts.sh` 尚只匹配旧 `-limited` 名称）；另人工核对新 standard 任务说明。四包均通过 Harbor Task schema 解析。全仓公共模板身份检查仍存在本轮开始前已有的 `limited/solution/oracle_replay.py` 与 robot_coding_bench 固定版本哈希不一致；本轮未修改该 oracle 文件，也未将此项计为通过。

四包已登记到 [tasks/dataset.toml](../../../tasks/dataset.toml)，登记目录与验收副本的内容哈希一致（排除运行产生的 Python 字节码）；dataset 清单及全仓 114 个任务包的 tooling 检查通过：

| 变体 | privileged | standard |
| --- | --- | --- |
| very_easy | [任务包](../../../tasks/topogym-lock-picking-very-easy-i00-privileged) | [任务包](../../../tasks/topogym-lock-picking-very-easy-i00-standard) |
| easier | [任务包](../../../tasks/topogym-lock-picking-easier-i00-privileged) | [任务包](../../../tasks/topogym-lock-picking-easier-i00-standard) |

实际运行使用冻结镜像中的 CUDA float32／Genesis 1.2.1／Nyx／compact_lab，默认 home，物理 tick 2.5 ms、4 子步、每 10 tick 一条控制动作。两档各保持 40 条控制动作（400 tick、1 s），钥匙最大漂移均为 0.101 mm、末速 0.0675 mm/s，两片角度漂移均为 0°；保持未解，无异常终止。同进程回溯重放及 privileged 评分器两次独立回放均通过，`instance_ok=1`、`grader_error=0`。standard 使用包内客户端提交 3 条保持动作，完成服务收尾、新进程回放与评分，`finalized=1`，基础设施／评分／实例不匹配错误均为 0。测试动作没有求解，两个模式评分均为预期的 0。CUDA 回放末态哈希并非全部逐位一致，按既有协议作为诊断记录，不混同于实例兼容性失败。

上述场景集成检查在诊断容器内调用生成包的原始客户端、服务和评分入口；该批未运行完整 Harbor 模型 agent 作业，也未执行抓取、接触旋转和插入全过程。12 个视频均完成解码核验；1 s 保持录像为三路 848×480、30 fps，以下合成视图便于查阅，独立视角保留在相邻 `videos/` 目录：

- very_easy：[初态稳定性录像](../../../runs/test_results/lock_picking_variants_20261002/very_easy_runtime/segments/segment_0/videos/combined.mp4) · [privileged 评分回放](../../../runs/test_results/lock_picking_variants_20261002/very_easy_privileged_verifier_retry1/replay.mp4) · [standard 评分回放](../../../runs/test_results/lock_picking_variants_20261002/very_easy_standard_retry4/replay.mp4)。
- easier：[初态稳定性录像](../../../runs/test_results/lock_picking_variants_20261002/easier_runtime/segments/segment_0/videos/combined.mp4) · [privileged 评分回放](../../../runs/test_results/lock_picking_variants_20261002/easier_privileged_verifier_retry1/replay.mp4) · [standard 评分回放](../../../runs/test_results/lock_picking_variants_20261002/easier_standard_retry4/replay.mp4)。

独立机位：[very_easy 主视角](../../../runs/test_results/lock_picking_variants_20261002/very_easy_runtime/segments/segment_0/videos/agentview.mp4) · [侧视角](../../../runs/test_results/lock_picking_variants_20261002/very_easy_runtime/segments/segment_0/videos/front_oblique.mp4) · [腕相机](../../../runs/test_results/lock_picking_variants_20261002/very_easy_runtime/segments/segment_0/videos/wrist.mp4)；[easier 主视角](../../../runs/test_results/lock_picking_variants_20261002/easier_runtime/segments/segment_0/videos/agentview.mp4) · [侧视角](../../../runs/test_results/lock_picking_variants_20261002/easier_runtime/segments/segment_0/videos/front_oblique.mp4) · [腕相机](../../../runs/test_results/lock_picking_variants_20261002/easier_runtime/segments/segment_0/videos/wrist.mp4)。

[验收汇总](../../../runs/test_results/lock_picking_variants_20261002/validation_report.json) · [视频完整解码与哈希](../../../runs/test_results/lock_picking_variants_20261002/media_validation.json)。资源采样中系统内存最高 58.0%，未触发 90% 停止阈值；CPU 峰值 93.9%，按现有授权仅记录。首次构建及验收脚本的失败尝试保留在证据目录，不计为通过。

构建使用独立本地镜像 `topogym-local/lock-picking-variants:20261002-01`，镜像 ID `sha256:6d72a5549023a2d8357cceadf1b043de62af7ee988714f95c37f7e0303b0bff9`，冻结运行源码 digest `4f0a1bd523ee4954db100990df1603e629c24afffe9d15190896ec2a4f521db6`（306 个文件）。未推送镜像；其他机器需先具备同一镜像。详细构建、源码快照、配置与运行证据位于[本轮证据目录](../../../runs/test_results/lock_picking_variants_20261002)。该目录因根盘空间不足迁至 `/data/jianwen/topogym/lock_picking_variants_20261002`，仓库内路径保留软链接；迁移前后全部文件哈希已核对一致。

2026-09-30 oracle 收尾更新：执行入口迁至 [scripts/oracle_runners/run_lock_picking_policy.py](../../../scripts/oracle_runners/run_lock_picking_policy.py)。`--part solve` 在原生 Task success 时正常结束，报告 `status="task_success"` 和 `completion_contract="task_success"`，允许尚未松手；`policy_done` 本身不足以判成功。失败、超时及证据不完整仍报错。独立审计同步重算 success 时间窗口，历史 `route_completed` 报告继续要求完整释放流程。[入口和用法](../../../scripts/oracle_runners/README.md)。此项为控制流修复，未新增三档物理执行。

2026-09-30 判据修正：v3 允许正常靠壁及几何上可穿孔的倾斜，取消额外 0.1 mm 空隙和独立 1° 倾角门槛，使用 10 μm 接触数值容差；同时要求有限钥匙杆仍贯穿全部四片板。前齿穿出 END 至少 1 mm、齿槽和转盘约束、连续 0.5 s 保留，不强制释放。三档共 4789 个已保存状态离线重算，释放后末态全部通过；没有新增物理执行。当前 `terminal_v4_bore_contact_default_success` 保留这些判据，并统一默认开启 `goal_complete=True`，不再受物理资格限制。详见[当前 success 条件](success_conditions_zh.md)和[重算结果](../../../runs/test_results/lock_contact_fix_20260930_01/replay.json)。历史报告与旧成绩不变；新实例使用新 terminal 参数，旧完整参数不能直接套用新修订。

2026-09-30 可解性补充：[三档完整机械臂流程与 IK 证明](../../../solvability_proof/lock_picking/2026-09-30_robot_process/README.md)。默认参数、seed 0 的 easy／medium／hard 已从 home 实际完成抓取、1／2／3 次回退、支撑换抓、END 插入、松手撤离与静置，仿真时间 124.7／159.2／194.7 秒，逐动作 IK 查询 972／1,270／1,571 次，独立逐 tick 复核通过。使用 CPU float32 和 `contact_weld_v1` 辅助抓持，显式无 RGB；原生 `task_success=False`，不增加正式 benchmark 成功数量。[上一批物体路径与名义 IK](../../../solvability_proof/lock_picking/2026-09-30_object_ik/README.md)及历史视频参考保留。

2026-09-29 相机：Panda 默认使用任务专属主机位，完整覆盖钥匙、三张圆盘与终点板；`front_oblique` 从机构另一侧放大圆盘孔槽区域。v2 两机位分别位于机构的 (+x, -y) 与 (-x, +y) 两侧。
[相机配置](../../../topogym/config/profiles/camera_configs/lock_picking_observation.yaml) ·
[最新两侧投影与检查](../../../runs/test_results/task_camera_study_20260929/opposite_sides_v2/README.md) ·
[Nyx 补拍命令](../../../runs/test_results/task_camera_study_20260929/README.md)。
当前通过几何取景及孔槽表面采样遮挡检查，尚未取得新机位 Nyx 初始化帧。

> 2026-09-27 用户授权恢复历史物理配置：medium 更新为 `historical_physics_v2`，保留当前实验室摆位，恢复 150 mm 盘距、495 mm 握柄偏移、7.5 mm 孔半径与历史两次回退槽形。公共机构恢复转盘／钥匙质量 0.12 kg、盘阻尼 0.03、接触摩擦 0.01、铰链附加惯量 0、接触时间常数 0.0025 s；参数计入实例身份。当前完整机器人验收以[本轮报告](../../../task_rollouts/lock_assist_20260927/README.md)为准，历史成功不自动继承。2026-09-26 的场景资产字节一致结论仅适用于当时版本。

场景入口核对：2026-09-26；下方历史演示记录：2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见[Demo 目录](../../../demos/README.md)。

## 任务与实现

Panda + Robotiq 从承托架抓起钥匙，穿过被动锁片、执行必要回退，抵达 END 后释放静置。基础版盘距 150 mm、三齿、两次必要回退。

当前源码：[common.py](../../../topogym/tasks/lock_picking/common.py) · [easy](../../../topogym/tasks/lock_picking/lock_picking_easy.py) · [medium](../../../topogym/tasks/lock_picking/lock_picking_medium.py) · [hard](../../../topogym/tasks/lock_picking/lock_picking_hard.py)。参数入口：[任务卡](../../../configs/task_cards/lock_picking.yaml)。旧 runner、planner、certificate、evaluator、variants、verify_variants、agent_adapter 模块及 `demos.environment_bootstrap.lock_picking` 入口已不在当前目录，不能沿用旧启动命令。

当前三档执行入口为 `scripts/oracle_runners/run_lock_picking_policy.py --variation easy|medium|hard --route-mode reindex --part solve --grasp-style side --grasp-roll-deg -45 --physics-dt .1 --solver-substeps 160 --control-decimation 1 --compute-backend cpu --no-rgb --audit-ik --output <new_run>`；hard 另加 `--endpoint-depth 4.10`，其余两档默认 4.08。随后使用 `scripts/audit_lock_picking_robot.py --run <run> --output <new_audit>` 独立复核。[完整可复制命令](../../../solvability_proof/lock_picking/2026-09-30_robot_process/README.md#复现)。三档策略为 `topogym/planning/lock_picking/reindex_policy.py`，复用既有拾取／换抓动作；原 medium 路线保留在默认 `--route-mode historical`。显式采用 100 ms World tick／160 子步，积分子步为 0.625 ms；不代表 simulator 默认时序资格。物理推进、自动 assist、segment 和可选录像全部使用公共模块，`--no-rgb` 不作为录像验收。

恢复后的 seed 0 已从默认 home 完成 CUDA／Nyx 连续执行，156.4 s，包含自动拾取、两次回退、支撑换抓、终点插入与释放静置：[完整视频](../../../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/full_solve.mp4) · [状态与 assist 报告](../../../task_rollouts/lock_assist_20260927/lock_picking/trail_12_medium/README.md)。独立物理观测通过，正式 terminal 的资格门仍未完成，不宣告 benchmark success。

## 历史演示状态与边界

标准外观三视角 159.35 秒来自成功物理状态重渲染；夹爪被动连杆按记录开合量重建，没有新增一次动力学成功。当时 runner、planner、certificate、grasp、oracle、evaluator 由任务包持有；该历史组织方式不代表当前目录结构。

## 历史变体证据

F1/F2/F3 为 1/2/3 次回退家族，含 S/M/L 固定代表；支持具名 seed、条件尺寸域、确定性拒绝重试和保存/重载。256 个 seed 几何/IK 通过，随机后代的机器人场景碰撞、接触动力学与完整流程仍待验收。

## 历史演示证据

2026-09-21 按 `varaition_<id>/<camera>/` 整理视频。标准外观仍保留完整三视角；F1/F3 恢复已有正斜视角 IK 预演，文件名含 `kinematic`，不计为完整物理 demo。

- [2026-09-18_standard_150mm_purple_trace_v1](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1)
- [2026-09-19_seed_generator_v1](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 历史生成入口（当前不可用）

以下为历史记录，所调用的 `variants` 模块已移除；当前场景选择请使用[三档部署记录](variation_deployment_implementation_20260925_zh.md)中的统一入口。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.lock_picking.variants --seed 42 --output runs/my_lock_instance
```
