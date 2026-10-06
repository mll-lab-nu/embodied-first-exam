# Oracle 执行入口

从仓库根目录执行 `python scripts/oracle_runners/<脚本名>.py --help`。原有参数不变；每个管理入口冻结当前源码，然后从快照中的同一子目录启动 worker。目录迁移不修改 `runs/`、`task_rollouts/`、`solvability_proof/` 的源码快照、历史命令、哈希或结果。

跨机器的三档 Harbor oracle grading 使用
[完整交接流程](../../topogym/planning/harbor_bridge/README.md#逐项实机-grade-交接easyhard)。
先运行 `python ci_checks/check-oracle-portability.py --check-git`；所需参考输入已放入
`topogym/planning/harbor_bridge/reference_data/`，应与代码一起提交。
此交付范围是 Harbor 的 Session 回调；下文历史独立审计／重渲染命令仍需要其原始证据目录。

| 脚本 | 职责 |
| --- | --- |
| `run_slotted_post_ring_oracle.py` | 迁入的 12 阶段候选，经本地 v15 Session 执行；保留本地环境，平放端盘抓取待适配，当前仅首阶段开发入口；[差异与未验证边界](../../topogym/planning/slotted_post_ring/README.md) |
| `harbor_oracle.py` | 跨任务的冻结实例检查、私有 oracle 候选打包和 Harbor oracle/nop 批量执行；[接入说明](../../topogym/planning/harbor_bridge/README.md) |
| `run_lock_picking_policy.py` | 两档双片 simplified、原三档 reindex 及历史 medium 策略；标准 Env 执行，可录制逐动作 IK/FK |
| `run_cast_coil_policy.py` | Coil 原三档策略，以及 very_easy 大齿直插、easier 挡板加横移装配策略 |
| `run_cast_keyhole_policy.py` | Keyhole 拾取、换抓和放置策略 |
| `run_fiber_bundling_policy.py` | Fiber 两档对称分叉，从 home 连续抓护套、逐根收拢、完整穿环；独立审计和录像入口见下文 |
| `run_buzz_wire_policy.py` | Buzz 策略及已编译参考动作执行 |
| `run_buzz_wire_simplified_policy.py` | Buzz very_easy / easier 的源码冻结、home 抓取、走线与终点释放验证 |
| `run_hedgehog_oracle.py` | 从 home 执行带显式辅助抓持选项的 Hedgehog oracle |
| `run_horseshoe_policy.py` | Horseshoe 几何、IK 和机器人分阶段诊断 |
| `run_horseshoe_oracle.py` | Horseshoe 从默认 home 的反馈 IK 完整执行，校验模型及规划输入哈希，冻结源码并自动独立审计；正式运行不加载 calibration-tools |
| `run_interlocked_claws_policy.py` | Claws very_easy / easier 的辅助抓持参考策略；旧三档仍调用原几何及摩擦抓持诊断 |
| `run_interlocked_claws_simplified_policy.py` | 两档简化 Claws 的源码冻结、连续几何检查、双臂预检和 SegmentRunner 执行 |
| `run_claws_oracle.py` | 原三档 Claws 的交接路线重认证、实测抓持 IK、JOINT_ABS 分离与停稳 |
| `run_blanket_oracle.py` | Blanket easy / medium / hard 从默认 home 双臂接近、局部辅助抓持、按路线拖展、释放撤手和原生展平判定 |
| `run_knot_oracle.py` | Knot 冻结实例的纯摩擦抓取、实测选点、JOINT_ABS 记录及原生成功收尾 |
| `run_knot_branching.py` | Knot 决策存档、失败后回溯上游换候选和经前缀回放验证的续跑 |
| `run_hedgehog_policy.py` | Hedgehog 旧几何／反馈诊断入口，保留其原有阶段限制 |
| `run_rigid_reference_policy.py` | Hedgehog／Claws 共用的几何、抓持诊断管理器 |
| `run_solvability_workflow.py` | 按任务提供的 stage factory 执行诊断或连续证明候选 |
| `run_rope_threading_relay.py` | Wang 0° easy / medium / hard 接力 IK 样本执行；JOINT_ABS、v12 IPC 选项、calibration 诊断和原生 Task 判定 |
| `run_rope_threading_policy.py` | very_easy / easier 的搭绳和单环双手交接开发策略 |

只读规划器 `scripts/plan_*`、独立审计器 `scripts/audit_*`、通用接口测试及源码快照工具 `scripts/test_*` 继续放在上级目录。difficulty trials 使用独立的 Harbor 执行链，不调用这些 oracle runner。

Knot 的 easy／medium／hard 配方、实例重建、分支续跑及正式回放命令见
[Knot oracle](../../topogym/planning/knot_untying/README.md)。默认夹爪开口 5 mm、端部抓点偏移 35 mm；
hard 默认完整拉 0.55 m。执行器返回 0 只表示原生成功，正式轨迹须再通过 `scripts/audit_knot_oracle.py`。

## Horseshoe 完整反馈 IK oracle

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_horseshoe_oracle.py \
  --variant medium --seed 0 --output runs/test_results/horseshoe_medium_new
```

默认读取[已验收配方索引](../../solvability_proof/horseshoe_ring/recipes.json)；各档资格见[证明目录](../../solvability_proof/horseshoe_ring/README.md)。输出目录必须尚不存在。入口核对安装模型、原生判据和五份规划输入的哈希，冻结源码，从标准 ALOHA home 执行反馈 IK，原生成功后自动进行独立逐 tick 审计；只有实例一致且审计接受时返回 0。

`oracle_result.json` 是最终结果，`independent_audit.json` 保留审计细节；底层 `run_report.json` 的成功报告仍含审计前 pending 状态。使用显式 CPU float64、25 ms / 40 子步、`use_contact_island=False` 和接触触发辅助抓持。正式策略没有 calibration-tools 导入或调用；开发候选可用 `--recipe <路径>` 指定，但只有完整运行并通过审计才有资格。

## Claws easy / medium / hard 交接路线

```bash
.venv-gs121/bin/python scripts/plan_claws_object_oracle.py \
  --variation easy --output runs/test_results/claws_easy_object_new
.venv-gs121/bin/python scripts/oracle_runners/run_claws_oracle.py \
  --variation easy --witness runs/test_results/claws_easy_object_new/object_witness.json \
  --output runs/test_results/claws_easy_run_new
.venv-gs121/bin/python scripts/audit_claws_oracle.py \
  --run runs/test_results/claws_easy_run_new --require-native-success \
  --output runs/test_results/claws_easy_audit_new
```

将 `easy` 和输出路径改为 `medium` / `hard` 可运行另两档。默认物体证书余量为
1 / 4 / 4 mm，关节速度为 0.2 / 0.1 / 0.08 rad/s。hard 当前为
`pregrasp_scaled_inset3mm_weld_v4`：两件原三角表面沿顶点法线内移 3 mm，
原尺寸握持块保留。旧 hard 证书不能用于新版；每次执行前都会重建资产并复核证书。

这三档按项目约定在完整分离后双件停稳 0.5 s 即结束，允许保持抓持；
very_easy / easier 已验收的入区判据保持其原版本。当前 oracle 从任务预抓姿态开始，
通过双指接触取得 `contact_weld_v1`，不含标准 home 接近段。采用 CPU float64、
25 ms tick、40 子步、每 tick 一次普通 JOINT_ABS，保留原机器人模型及增益。
物体路径、IK、原生 success 和独立逐 tick 审计分别记录；原生成功不能代替审计。

`scripts/plan_claws_ik.py --variation <档位> --witness <证书> --output <新目录>`
可单独检查出生姿态的 IK；实际执行仍从取得辅助抓持后的实测状态重新规划。
hard 的成功执行有三次轻微件间接触；审计时加
`--tolerate-piece-contact --piece-force-n 8 --contact-depth-mm .5`。
这是独立审计的显式滑动接触选项，不修改 Task 的 1 mm 普通接触／2 mm
持件手指穿透阈值。easy / medium 使用不允许持续件间接触的默认审计。

有 Nyx/CUDA 时可从完整记录重渲染四路视频，不推进物理、不增加成功次数：

```bash
TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets" \
  .venv-gs121-nyx/bin/python scripts/render_claws_oracle.py \
  --run runs/test_results/claws_easy_run_new \
  --output runs/test_results/claws_easy_video_new
```

重渲染校验冻结源码、实例和资产，通过共享 `record_rigid_history` / `RecordingSession`
恢复全部关节（含被动手指）。本地本轮 GPU 驱动不可用，尚未验证这个视频入口的实际渲染。
完整结果与边界见 [Claws 任务页](../../docs/develop/tasks/interlocked_claws_zh.md)。

Rope Threading 的显式开发参考可用
`python -m topogym.planning.rope_threading.profiles --variation easy|medium|hard --execute-reference --output <新目录>`
从 home 执行，三档均已取得 seed 0 原生成功。入口校验参考轨迹字节、模型及完整原生成功证据，
自动带上已记录的加速与接触配置，默认无 RGB。
重新规划常规场景时，先通过 `scripts/plan_rope_threading_oracle.py --variation easy|medium|hard`
生成物体路径，再用 `scripts/plan_rope_threading_ik.py --witness <object_witness.json>` 生成对应轨迹。
执行：`run_rope_threading_relay.py --variant easy|medium|hard --seed 0 --samples <relay_samples.npz> --output <新目录>`。
三档各自的默认配方、完整命令和证据边界见
[Rope Threading oracle](../../topogym/planning/rope_threading/README.md)。默认 Nyx 四视角，`--no-rgb` 可关闭；
导入的 IK 证据不等于完整物理成功。

## Blanket easy / medium / hard 双手展平路线

入口也支持 `--variation very_easy` 和 `--variation easier` 的折角路线；新路线独立验证，不能继承原三档成功资格。增加 `--record` 会通过共享 RecordingSession 保存从默认 home 开始的连续四路录像和首末帧，包括失败时实际执行的前缀。新两档的初态准备、资源及验收见 [Blanket 任务说明](../../docs/develop/tasks/blanket_flatten_zh.md)。

从仓库根目录执行，输出目录必须尚不存在。Nyx 资源先按 `scripts/prepare_nyx_studio.py` 准备；
下面的资源路径沿用交接环境，已有资源放在别处时设置为对应目录。

```bash
export XDG_CACHE_HOME="$PWD/.cache" TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.cache/topogym/visuals/nyx"
.venv-gs121-nyx/bin/python scripts/plan_blanket_object_oracle.py \
  --variation easy --seed 0 --output runs/test_results/blanket_easy_object_new
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_blanket_oracle.py \
  --variation easy --seed 0 --output runs/test_results/blanket_easy_run_new
.venv-gs121-nyx/bin/python scripts/audit_blanket_oracle.py \
  --run runs/test_results/blanket_easy_run_new --require-native-success \
  --output runs/test_results/blanket_easy_audit_new
```

将 `easy` 和输出目录改为 `medium` / `hard` 可运行另两档。虚拟手见证分别需加
`--settle-s 40` / `--settle-s 60`；默认 4 s 只够 easy。机器人 runner 按路线自动选择静置时间，
物理步上限默认 easy / medium 28000、hard 40000，可用 `--max-physics-steps` 显式覆盖。

路线和抓点见 [routes.py](../../topogym/planning/blanket_flatten/routes.py)，对应冻结初态
`gathered_archive_v2`。见证与机器人读取相同路线：虚拟手只移动两个夹爪大小的局部 patch，
机器人停在 home，不算机器人证明。机器人 oracle 通过 `SegmentRunner` 发送 JOINT_ABS，
以 `pbd_local_patch_v1` 双指表面接近准入取得局部抓持，执行拖展、释放、上撤 8 cm，
再等待原生 Task 判定。easy / medium 一段，hard 两段，包含重新抓取。

冻结初态绑定 CUDA float64、2.5 ms tick、4 子步、每控制步 10 tick，以及硬件／依赖栈；
`resource_profile()` 须与 `gathered_archive_v2/` 下的目录一致。交接的成功环境使用
RTX 4090、torch 2.11.0+cu128、numpy 2.3.5、quadrants 1.0.2，profile 为
`cuda_sm89_mp128_87407517a32a`；不能用其他 profile 的初态替代。
场景身份包含相机，因此 RGB 保持启用；runner 设置 `env.defer_rgb = True` 并选择空相机列表，
不渲染也不录视频。`assist_support.enable()` 只在 oracle 进程内登记出生材料坐标，
并将常量材料映射设为只读，使冻结状态恢复的缓冲区清单保持一致。

机器人执行产出 `oracle_report.json` 和 `trail/`，原生成功时 runner 返回 0；
独立审计另行执行，产出 `execution_audit.json`，完整证明须检查其 `accepted_proof=true`。
审计重算展平五门槛，并按密封的 `static_model.json` 重算释放、机器人碰撞包围盒距布
至少 5 mm、速度至多 0.03 m/s、窗口内漂移至多 3 mm，以及连续 0.5 s 稳定窗口。
独立成功 tick 必须与原生一致；另核对默认 home、冻结布料初态、连续 tick、每手每段一次抓放、
无丢抓、持抓应变 guard、机器人与桌面接触和关节限位。

交接材料报告的结果（2026-10-03，三档 seed 0，默认时序，无回溯）：

| 档位 | 原生成功 tick / 仿真时长 | 独立审计 | 持抓峰值边长比 / guard | 终态覆盖率 |
| --- | --- | --- | --- | --- |
| easy | 7156 / 17.9 s | passed，成功 tick 一致 | 1.247 / 1.3 | 100.0% |
| medium | 15657 / 39.1 s | passed，成功 tick 一致 | 1.292 / 1.5 | 99.98% |
| hard | 33687 / 84.2 s | passed，每手两次抓放 | 1.293 / 1.5 | 93.2% |

easy 另一次运行成功于 tick 7309，审计也通过；GPU PBD 运行间数值差异可能改变接触和成功时刻。
这些是外部交接结果，原 `runs/test_results/blanket_*_20261003*` 的完整证据未随文本迁入，
本次集成未新增物理成功记录或 `solvability_proof/` 归档。交接运行没有视频，单次逐 tick 证据约
20 / 28 / 58 GB。范围限于这三个冻结实例和辅助局部抓持；不涵盖纯摩擦抓持、任意 seed、
连续子步碰撞证明或机器人与布料穿透审计。任务状态见 [Blanket 任务页](../../docs/develop/tasks/blanket_flatten_zh.md)。

CPU 回归：`.venv-gs121-nyx/bin/python ci_checks/test-blanket-oracle.py`；
通用入口、CLI 和源码快照回归：`.venv-gs121-nyx/bin/python ci_checks/test-oracle-runners.py`。

## Fiber 原三档独立审计

easy / medium / hard 的 seed 0 已有完整连续运行，2026-10-03 独立审计通过，正式 3/3；[证明与复核命令](../../solvability_proof/fiber_bundling/2026-10-03/README.md)。使用原 `.venv-gs121`（trimesh 4.12.2、numpy 2.4.4）复核归档；不要将本节的依赖要求套到下方另有冻结身份的简化变体。

```bash
.venv-gs121/bin/python scripts/audit_fiber_bundling_robot.py \
  --run solvability_proof/fiber_bundling/2026-10-03/evidence/runs/medium_full_01 \
  --output runs/test_results/fiber_medium_independent_reaudit
```

该命令按运行的冻结 Task 检查；当前 v4 和封存 world／动作交叉核对命令见证明页。easy 原执行使用 v3，同一完整轨迹另通过 v4；复核不增加物理成功次数。三档资格限于 CPU64、25 ms／40 子步、接触辅助护套抓持；本次未复跑物理或新增视频。

## Fiber 两档简化变体

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_fiber_bundling_policy.py \
  --variant very_easy --seed 0 --no-rgb \
  --output runs/test_results/fiber_very_easy_new
.venv-gs121-nyx/bin/python scripts/audit_fiber_bundling_robot.py \
  --run runs/test_results/fiber_very_easy_new \
  --output runs/test_results/fiber_very_easy_new_audit
.venv-gs121-nyx/bin/python scripts/render_fiber_bundling_run.py \
  --run runs/test_results/fiber_very_easy_new \
  --output runs/test_results/fiber_very_easy_new_video
```

`--variant easier` 使用三根三角排列细线。默认 proof 禁止回溯，CPU float64、
2.5 ms tick、4 子步、每控制步 10 tick，与新任务包动力学配置一致。
接触触发的 `contact_weld_v1` 只作用于护套；细线禁碰和完整穿环判据保持启用。
每次从标准 home 开始，通过 SegmentRunner 执行；原生 success 后仍须运行
独立审计，不能把 `accepted_proof=False` 的初步结果当成数据资格。
`--mode diagnostic` 可诊断候选，`--selection` 可固定已选参数。

`--replay-run <成功的连续运行>` 从 home 重执行保存的普通关节目标；可搭配
`--config` 比较另一物理时序，但必须保持同一变体和控制周期。最后最多追加
2 s 原目标保持以覆盖稳定窗口差异，真实终态会提前停止。它是新物理执行，
需要新的独立审计；完整 World 仍逐 tick 保存到 private evidence。

省略 `--no-rgb` 会在执行时录制三视角；上例最后一条从已保存状态重渲染，
不执行新物理，也不增加成功次数。需要 Nyx/CUDA；输出目录必须尚不存在。
长时间逐 tick 证据会占数 GB，运行前留足空间。审计器同时支持经逐字节哈希
核对后无损压缩的 `.jsonl.gz`。实际实例资格、录像及四个包见
[Fiber 任务页](../../docs/develop/tasks/fiber_bundling_zh.md)。

## Buzz Wire 原 medium / hard

两档的完整 IK 动作已从默认 home 无回溯复验成功，并通过独立接触审计。
`run_buzz_wire_policy.py --compiled-actions <动作文件> --v12-performance`
使用正式 `CompiledJointPolicy` 执行普通关节目标；运行时不调用 calibration tools。
两档的动作文件、具体命令、冻结源码与 RTX 4090 生成的三路 Nyx 视频见
[Buzz policy 说明](../../topogym/planning/buzz_wire_3d/README.md)。
资格限于各自冻结 seed 0、接触辅助抓持、CPU64 / 25 ms / 40 子步配置；
每次重新执行后仍须运行 `python -m topogym.planning.buzz_wire_3d.audit <输出目录>`。

## Buzz Wire 两档简化变体

这是 [planning/buzz_wire_3d/simplified_policy.py](../../topogym/planning/buzz_wire_3d/simplified_policy.py) 的管理侧执行入口。每段按实际观测重新规划；常规执行不依赖历史 run。两档新版 oracle 均已从默认 home 无回溯完整成功，并通过独立审计。任务包默认时序的正分资格仍单独记录，详见任务页。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_buzz_wire_simplified_policy.py \
  --variant very_easy --regrasp --finish-mode low_slide_regrasp --seed 0 \
  --compute-backend cpu --no-rgb \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40 \
  --episode-seconds 450 \
  --output runs/test_results/buzz_very_easy_new
```

`easier` 选择已确认的横弯接下凹弯。两档沿用 easy 的默认 home、工具尺寸与原生完整判据；`--regrasp` 使用已有的起点换抓动作，随后等待夹爪被动关节稳定，再执行只读 IK/碰撞采样得到的关节参考。所有动作仍通过公共控制接口执行。默认 `--part solve` 必须获得原生 Task success；`pickup` / `plan` 只证明各自阶段。此 oracle 入口默认 CPU 64 位、25 ms、1 倍控制降采样、40 子步；公共 simulator / 任务包默认仍为 2.5 ms、10 倍、4 子步，二者验证范围不能混用。

执行完成后运行 `.venv-gs121-nyx/bin/python -m topogym.planning.buzz_wire_3d.audit <输出目录>`，独立核对原生成功、出生到终点的连续谱系、普通 action 覆盖以及工具/机器人无触线。审计支持原始 JSONL 与经过字节哈希验证的无损 gzip 日志。

`--replay-run <已成功的输出目录>` 从默认 home 重新执行该次记录的普通关节动作，继承其物理配置并核对运行源码。省略 `--no-rgb` 会通过公共 SegmentRunner / RecordingSession 录制三路 Nyx 视频；这是一轮新物理执行，不是状态重渲染。输出目录必须尚不存在。报告包含源码身份、逐 tick 证据、辅助抓持事件、规划采样及原生判定；达到系统内存 90% 时只停止本轮 worker。实际验证范围见 [Buzz Wire 任务页](../../docs/develop/tasks/buzz_wire_3d_zh.md)。

默认启用起点换抓及低位终点释放。`--prefix-run <输出目录>` 可复用已完成的 `traverse` / `prepare_finish_slide` / `finish_recipe_0` 段之前的动作序列，仍从 home 真实重跑，不恢复物体状态；报告记录截断 tick 和实际动作指纹。两种重跑均继承来源冻结的运行源码，避免其他任务的并行修改改变物理身份；允许用 `--episode-seconds` 延长运行时限，不改变物理步长。每次全程逐 tick 记录会占用数 GB，运行前应留足磁盘空间。

`--terminal-contact-close` 保留慢速闭爪实验开关；历史尝试未取得完整成功。默认已验收流程使用原闭爪动作配合抓取朝向调整和环居中，该开关未随新流程独立验收。

## Claws 两档简化变体

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_interlocked_claws_policy.py \
  --variant very_easy --seed 0 \
  --output runs/test_results/claws_very_easy_new

.venv-gs121-nyx/bin/python scripts/oracle_runners/run_interlocked_claws_policy.py \
  --variant easier --seed 0 \
  --output runs/test_results/claws_easier_new
```

默认从任务已确认的双臂预抓姿态开始，使用原 ALOHA、`contact_weld_v1`、CUDA、Nyx 四视角和默认物理时序。策略先通过双指接触取得辅助抓持，再执行两件相对通路，最后让棕色件整体进入绿色目标区并满足当前 Task 的低速保持条件。该流程不包含 home 到预抓姿态的接近动作，也不以“已分离”代替 Task success。

`--part geometry` 只检查物体通路，`--part acquire` 只执行辅助抓持准入，默认 `--part solve` 要求 Task success 且执行证据完整。`--no-rgb` 显式关闭录像；若使用非默认 `--physics-dt` / `--control-decimation` / `--solver-substeps`，结果仅代表所记录的时序。输出目录必须尚不存在。

输出保存源码快照和哈希、几何报告、原生 IK／网格碰撞预检、逐 tick 状态、资源占用、阶段误差、Task 结果及公共录制产物。物体通路做连续检查；机械臂预检是采样检查，二者不能混称连续机器人无碰撞证明。系统内存达到 90% 时仅停止本次 worker，保留失败证据。

回归入口：`.venv-gs121-nyx/bin/python ci_checks/test-interlocked-claws-simplifications.py`。实际验收状态和形状说明见 [Claws 任务页](../../docs/develop/tasks/interlocked_claws_zh.md)。两档先作为独立具名入口接入，保留旧 `base` / `seeded` 三档含义。

2026-10-02 两档 seed 0 的完整参考求解在以下显式配置下通过；将 `easier` 换为 `very_easy` 可复现另一档。去掉 `--no-rgb` 会使用 CUDA Nyx 录制，物理仍在 CPU；very_easy 已完成这一录制复验。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_interlocked_claws_policy.py \
  --variant easier --seed 0 --compute-backend cpu --no-rgb \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40 \
  --output runs/test_results/claws_easier_cpu_new
```

## Coil 正方体变体

`--variant very_easy` 和 `--variant easier` 选择两套已确认形状。102 mm 的源模型等比缩为 51 mm，供 ALOHA 从两侧外壁抓取；easier 的 18 mm 横移随之缩为 9 mm。两者要求 `--policy feedback`（默认值），保留原任务的落桌、释放、撤手与稳定判据。`base` / `seeded` 仍选择原三档。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_cast_coil_policy.py \
  --variant very_easy --seed 0 \
  --output runs/test_results/cast_coil_very_easy_new

.venv-gs121-nyx/bin/python scripts/oracle_runners/run_cast_coil_policy.py \
  --variant easier --seed 0 --compute-backend cpu --no-rgb \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40 \
  --output runs/test_results/cast_coil_easier_cpu_new
```

第一条使用默认时序、CUDA 和 Nyx 四视角录制；第二条显式选择 CPU 无 RGB 及 25 ms tick，不能将其结果称为默认时序或录像验收。输出目录必须尚不存在。入口冻结源码、记录资源占用，并在系统内存达到 90% 时只停止本轮 worker。`run_report.json` 包含实例、资产哈希、抓持事件、阶段到位误差和 Task 结果；实际执行资格见 [Coil 任务页](../../docs/develop/tasks/cast_coil_zh.md)。

回归：`python ci_checks/test-cast-coil-simplifications.py` 与 `python ci_checks/test-cast-coil-variants.py`。这些检查覆盖几何、连续平移通路、夹爪尺寸、注册和终态反例，不代替完整物理执行。

## Lock 的结束规则

`--part solve` 以原生 Task 的 `task_success=True` 且 `terminated=True` 为完成标准。正常 `env_terminal` 会收尾并记录 `status="task_success"`；不再等待 policy 发出最后的松手／撤离动作，也不在终止后继续 step。任务失败、超时、策略错误或证据不完整仍会失败。

`policy_done` 只表示策略动作结束，不能代替 Task success。`--part pickup` 可以独立得到 `pickup_passed`，此时报告仍明确记录 `task_success=False`。`policy_completed` 和 `released_at_end` 分别记录动作完成和释放状态；成功时二者可以为 false。原先独立的 0.2 mm 释放验收不再作为 runner 的成功标准，几何判定统一使用当前 Task 的孔壁接触规则。

例如，使用已有 easy 参考流程的执行参数启动一个新实验：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_lock_picking_policy.py \
  --variation easy --route-mode reindex --part solve \
  --grasp-style side --grasp-roll-deg -45 \
  --physics-dt .1 --solver-substeps 160 --control-decimation 1 \
  --compute-backend cpu --no-rgb --audit-ik \
  --output runs/lock_oracle_success_new

.venv-gs121-nyx/bin/python scripts/audit_lock_picking_robot.py \
  --run runs/lock_oracle_success_new --output runs/lock_oracle_success_new_audit
```

medium 使用 `--variation medium`；hard 使用 `--variation hard --endpoint-depth 4.10`。这些参数来自历史物理流程，目录迁移及收尾回归不代表新增了三档真实执行验收。

两档双片变体使用 `--route-mode simplified`：`very_easy` 抓起后直接插入，`easier` 先让前齿进入第一片槽内，转动钥匙消除槽齿间隙、以真实接触带动第一片对齐，再插入。沿用默认物理时序与短柄抓持区域，不设置物体位姿、盘片角度或人工绑定；成功时允许保持抓持，不要求换抓或释放。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_lock_picking_policy.py \
  --variation very_easy --route-mode simplified --part solve \
  --grasp-style side --grasp-roll-deg -45 \
  --physics-dt .0025 --solver-substeps 4 --control-decimation 10 \
  --compute-backend cuda --audit-ik \
  --output runs/test_results/lock_very_easy_oracle_new

.venv-gs121-nyx/bin/python scripts/audit_lock_picking_robot.py \
  --run runs/test_results/lock_very_easy_oracle_new \
  --output runs/test_results/lock_very_easy_oracle_new_audit
```

easier 将 variation 换成 `easier`，并使用新的输出目录；默认最终插入深度为 3.08 个片距。双片审计核对一次自动抓持、零回退，以及 easier 的实际转片阶段；按当前 `contact_weld_v1` 合同核验两指在同一原生接触快照内位于握柄区域且穿透非负，零力接触不自动视为未接触。实际通过范围和录像见 [Lock Picking 任务文档](../../docs/develop/tasks/lock_picking_zh.md)。

新报告标记 `completion_contract="task_success"`。审计会从保存的每个 tick 重算 Task 稳定窗口并核对原生结果，同时保留 home 起点、连续性、IK/FK、双指接触、必要回退和碰撞检查；末次释放不是必需项。旧报告没有该字段，仍按原 `route_completed`、完整释放阶段和释放后静置规则审计，不追溯改判。复现旧流程应使用旧 run 自己的 `source_snapshot/scripts/...` 入口。

CPU 回归：`python ci_checks/test-oracle-runners.py`，覆盖成功时在松手前正常停止、失败／超时、未完成稳定窗口、仅拾取、历史审计边界，以及迁移入口与快照路径；不运行新的物理仿真。

## Rope Threading 简化任务开发

`run_rope_threading_policy.py --variant very_easy|easier --part pickup|solve --output <新目录>`
从 ALOHA 标准 home 开始，经实际碰撞网格预检和接触触发 FEM 辅助抓持执行候选动作。
使用共享 SegmentRunner 和 Nyx 四路录像；`--no-rgb` 明确选择纯物理。
默认 dt=2.5 ms、4 子步；可显式设置 `--physics-dt`、`--solver-substeps`、`--speed-scale` 做开发试验。
尚不是已验收 oracle，报告分别记录局部 `pickup_passed` 与原生 `task_success`，物理资格仍为 unqualified。
场景、判据与实际验证范围见 [Rope Threading 任务页](../../docs/develop/tasks/rope_threading_zh.md)。
