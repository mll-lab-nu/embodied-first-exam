# Run trials 全链路审查报告

**合并后状态见[合并后的 Run trials 问题复核](run_trials_post_merge_audit_20261001_zh.md)。** 本文保留合并前的源码、镜像及复现证据；其中新镜像缺 IPC 修正、Knot 慢循环和 standard 生命周期的部分结论已被后续修复或收窄，不应直接作为合并工作树的现状。

日期：2026-10-01。范围：当前新 run-trials 的启动与 prepare、动作接收、物理步进、终态、回放评分、输出、性能，以及 13 类正式任务的流程一致性。固定旧镜像及冻结任务包的问题另列为历史兼容记录。

## 1. 结论与检查边界

**当前新 run-trials 仍有动作、评分和输出问题需要处理。** 本轮在当前公共模板中复现了动作记录、时间统计、输入错误分类、评分身份约束和录像输出问题。Knot 的终态计算还存在足以影响运行预算的 CPU 热点。旧镜像的缺陷不再计入这条新流程的当前 bug 清单。

本报告对应用户所说的 run-trials，实际入口为 [run_difficulty_trials.sh](../../bash_scripts/run_difficulty_trials.sh)，编排主体为 [difficulty_eval.py](../../scripts/difficulty_eval.py)。经本日补查，新 run 会冻结源码、按输入身份准备独立镜像和新任务，不直接使用 `0.1.0`、`0.2.3-cu128` 或单独生成器默认的 `0.2.4-cu128`。恢复旧 run、指定旧 controller/release、或直接执行 `harbor run -p tasks/...` 属于另一条版本固定的路径。

**范围调整：B04–B13 共 10 项保留在当前问题与风险清单；B01–B03 移到历史/其他入口记录，不计入当前新 run-trials 的 bug 数。** B02 对已有固定镜像的事实仍成立，但不能据此断言新流程会执行旧 IPC 代码。旧镜像是否能删除与审查范围是两件事，实际依赖核对及本次保留原因见 [旧镜像使用核查](../../runs/test_results/run_trials_audit_20261001/image_usage_followup/README.md)。

本轮完成：

- 清点 **106 个任务包**：13 类正式任务 × 3 档 × 2 模式，共 78 个；另有 28 个原始 i00 包，包含 Cube sanity fixture。
- 检查公共 Session、limited 服务与客户端、unlimited/limited grader、收集器、difficulty 编排、镜像构建与初态准备，以及各任务的终态实现。
- **106 个任务包静态检查通过；14 组 CPU 回归共 154 项通过。** 另用真实 Python 函数和显式模拟器替身复现控制流问题，并测量两个纯 CPU 几何函数。
- 检查本地镜像身份；从未启动的临时容器复制镜像内源码比较，随后删除本轮创建的临时容器。
- 复核既有 GPU 短流程和物理证明。**本轮新增 GPU 物理 rollout 为 0，未运行真实模型 trial，未构建或推送新镜像。** 先前明确暂停的 GPU 队列保持暂停。

源码基点为 `c0a35177c5fe534f1993ca78cbedadcbc987f81f`，但工作树有既存改动，因此结论以 [baseline.json](../../runs/test_results/run_trials_audit_20261001/baseline.json) 的文件哈希为准，不能仅用 commit 表示。工作树原状见 [git_status_before.txt](../../runs/test_results/run_trials_audit_20261001/git_status_before.txt)。本轮只增加报告与审查证据，没有修复生产代码。

证据等级在下文明确区分：**实测**表示本轮实际执行；**静态确认**表示分支或配置明确存在；**历史实测**表示复用已有记录；**待物理验证**表示尚不能据此判定真实轨迹失败或任务不可解。替身复现证明控制流，不证明 CUDA 物理行为。审查覆盖全部任务族，但不等于穷尽全部运行时故障。

优先级：P1 为结果可信度、动作语义、运行完成性问题；P2 为恢复、输出表现和效率改进。历史记录中的 P0 仅表示其旧运行路径上的阻断，不是当前新 run-trials 的优先级。

| 优先处理项 | 影响 | 证据与范围 |
| --- | --- | --- |
| B04、B05 输入错误与录像故障影响评分收尾 | 一次坏提交可停后续队列；评分完成后仍可能丢 reward | 当前 grader 替身复现 |
| B06、B07 动作记录和时钟不一致 | 轨迹包含未执行动作；报告时间偏大；非整周期 dt 被静默舍入 | 当前 Session/limited/Env 函数复现 |
| B08 初态不匹配仍可评分成功 | 两种模式对同一实例身份的约束不同 | 当前 unlimited grader 替身复现 |
| O01 Knot 终态几何计算 | 单个控制步可能仅终态计算就耗时约一分钟或更多 | 纯函数单次计时；不是整机 rollout 基准 |
| B10、D01 物理步内事件和流程约定未完全统一 | 短暂接触覆盖范围不同，历史证明不能直接转为正式 trial 证明 | 源码确认，真实漏检范围待 GPU 验证 |

## 2. 实际运行的是哪一版

### 2.1 冻结任务包、公共模板、镜像分别有身份

完整清单见 [task_inventory.json](../../runs/test_results/run_trials_audit_20261001/task_inventory.json)。

| 任务包组 | 数量 | 固定 simulator 镜像 | 公共工具 SHA-256 前缀 | 本机镜像情况 |
| --- | ---: | --- | --- | --- |
| 原始 i00，含 Cube | 28 | `0.1.0` | `4b3d078c9cad5752` | 存在，但有 B01、B02 |
| 三档，除 Interlocked Claws | 72 | `0.2.3-cu128` | `fd19e5191e14f5bc` | 本地不存在 |
| 三档 Interlocked Claws | 6 | `0.2.3-cu128` | `493ece29325f37c3` | 本地不存在 |
| 当前生成器的新包 | 本次未新增 | 由本次构建/配置确定 | 当前公共模板，tooling v3 | 不能继承上面三组的验收结论 |

冻结工具并非意外：`check-tooling-identity.sh` 明确保留历史版本。因此静态检查全部通过，只能说明这些包符合各自冻结规则，不能说明它们都使用最新修复。

本地镜像 ID：

- `0.1.0`：`sha256:7660ebca515ac68120f312414e42f7124d900110cac3b5e7954517284dd2ab90`。
- `0.2.4-cu128`：`sha256:5351d624281f4418f8d9b534b44e0d85793364ab17a32b1ea4fc5b060ef199ae`。

镜像检查原文见 [images.json](../../runs/test_results/run_trials_audit_20261001/images.json)。未查询 registry，所以“不在本地”不代表远端不存在。也不能把 `0.2.3` 静默换成 `0.2.4` 后仍称原实例的原版本结果。

补查确认：这三种固定版本在核查时均没有运行中的直接消费者；本机存在的 `0.1.0` 与 `0.2.4-cu128` 也没有停止容器直接引用。但 `0.1.0` 仍是 28 个原始任务包的构建依赖，`0.2.4-cu128` 仍是单独生成器默认值，二者尚未完全退役，不能仅因没有容器运行就删掉。新入口根据当前源码计算的 runtime tag 为 `topogym-local/difficulty-runtime:79cc20a56fe24c367ee8e54f59eb865ff13f3fc189ebb306074c40f6ee189979`，本地尚未构建；其输入包括当前 IPC 修正的文件哈希。此处只计算身份，没有启动 prepare 或构建镜像。

### 2.2 已有 GPU 证据能覆盖什么

[builder feedback 实测矩阵](../../runs/test_results/rcb_builder_feedback_20261001/run_151751/test_matrix_zh.md) 使用候选镜像 `topogym-local/builder-feedback:20261001-v3`：

- 公共 Session：39/39 个任务档位通过建场景、短步进、reset、Nyx 视觉检查。
- limited：32/39 通过短保持、超时终止、回放和录像；Orbits medium 暂停，Rope Threading 三档和 Slotted Post Ring 三档未运行。
- 两类代表性新生成包（Interlocked Claws、Blanket，两种模式）有非 root verifier / finalize 验证。
- Blanket 使用本机 RTX 4090/cu128 新准备的 v2 初态身份，不能当作原 Blackwell 存档逐状态复现。

这些是短流程证据。剩余 7 个 limited 项、1 个最大 uint32 seed 的 limited 项、2 个正式镜像 GPU 检查仍是暂停/未完成；并且当前 IPC 源码又与候选镜像不同，四类 IPC 任务需要对最终发布身份重新验收。不能由 39/39 推导“39 个完整任务均可解且评分正确”。

## 3. 按运行路径区分的问题记录

### 历史及其他入口记录 B01–B03

以下三项保留证据和原编号，便于追踪旧数据集；不计入当前新 run-trials 的问题数。

### B01 · P0 · 原始 i00 使用的旧镜像关闭 8 类任务成功判定

**静态确认，作用于旧镜像运行路径。** 从 `0.1.0` 复制的 [placement.py](../../runs/test_results/run_trials_audit_20261001/image_sources/0.1.0/topogym/tasks/placement.py)、[Lock Picking](../../runs/test_results/run_trials_audit_20261001/image_sources/0.1.0/topogym/tasks/lock_picking/common.py)、[Knot Untying](../../runs/test_results/run_trials_audit_20261001/image_sources/0.1.0/topogym/tasks/knot_untying/common.py)、[Rope Threading](../../runs/test_results/run_trials_audit_20261001/image_sources/0.1.0/topogym/tasks/rope_threading/common.py) 仍有 `goal_complete=False`。

受影响的是 Hedgehog、Horseshoe、Interlocked Claws、Orbits、Slotted Post Ring、Lock Picking、Knot Untying、Rope Threading，共 8 类 × 2 模式 = **16 个原始包**。当前源码已启用判定，旧镜像不会因此更新。

**建议**：为修复后的 runtime 生成新的任务版本和不可变镜像身份；保留原包与历史结果。验收应包含每类至少一个真实成功轨迹的独立评分，以及对应失败反例，不能只检查 `goal_complete=True`。

### B02 · P0 · 当前 IPC 同步修正未进入本轮检查的两个镜像

**镜像差异已确认；错误的物理量级引用历史实测。** 当前 [ipc.py:267](../../topogym/world/physics/ipc.py) 已有 `ForwardAxisRevoluteJoint` 和逐子步 articulation 同步检查；本地 `0.1.0`、`0.2.4-cu128` 均没有。哈希对照见 [image_comparison.json](../../runs/test_results/run_trials_audit_20261001/image_comparison.json)。

这影响 Knot、Rope Threading、Orbits、Slotted Post Ring。之前的[评分链审查](harbor_grading_reachability_audit_20261001_zh.md)记录了机器人与 IPC 碰撞体偏离及修正后的对照；本轮未重新测量偏离幅度。仅验证可建场景或保持不动，不能覆盖关节转动时的同步。

**建议**：发布包含修正的新镜像；对四类任务做关节运动、接触、reset、独立回放测试，并检查同步误差随时间的最大值。新增的 2 mm guard 也要在真实接触下验证误报率，不能仅因它会抛异常就视为验证完成。

**范围说明**：这里的发布建议针对单独生成器/固定镜像入口。当前新 difficulty 会把 `ipc.py` 纳入 runtime 输入哈希，已有旧 runtime 不能按相同身份直接复用；对新镜像的物理验证仍待完成，但这是验证缺口，不是“旧 IPC 必然进入新 run”的已确认 bug。

### B03 · P1 · 三档冻结包引用的镜像在本地缺失

**环境条件确认。** 78 个三档包固定引用 `0.2.3-cu128`，本机没有这个 tag。直接 Harbor 运行会依赖远端拉取；拉取失败或无权限时会在建环境阶段失败。本轮没有证明远端拉取失败。

新 difficulty 的 prepare 会构建/验证自己的镜像，因此这不是新流程必然失败的证据。**建议**：在启动批量 trial 前，对所选数据集的所有镜像身份做存在性、可拉取性和摘要检查，输出对应任务列表；不要先运行一部分后才发现某组镜像缺失。

### 当前新 run-trials 的问题与风险 B04–B13

### B04 · P1 · 畸形轨迹被当作 grader 故障，可能停止后续 trial

**CPU 复现。** [unlimited grade.py:56](../../harbor_templates/topogym/unlimited/tests/grade.py) 把读取 NPZ、读取 `actions`、转 dtype 和物理执行放在同一大 `try` 中。缺少 `actions` 的合法 NPZ 会进入外层 `except`，得到 `grader_error=1`，而不是 `bad_trajectory`。

[collect_batch_results.py:54](../../scripts/collect_batch_results.py) 将 `grader_error` 归类为基础设施问题；[difficulty_eval.py:947](../../scripts/difficulty_eval.py) 遇到未完成类状态会保留队列并停止。因此一次应记作无效提交的输入，可能阻断后续实例。

**建议**：在初始化模拟器之前单独校验容器格式、必要字段、dtype、维度、长度与有限性，将明确由提交导致的错误记为 `invalid_submission`；真实建场景、solver、I/O 异常保留基础设施分类。验收包含缺 key、损坏 zip、字符串数组、NaN、空数组及正常失败轨迹，不应把所有 `ValueError` 一律算 agent 失败。

### B05 · P1 · unlimited 的 reward 在录像之后写入

**CPU 中断复现。** [grade.py:69–89](../../harbor_templates/topogym/unlimited/tests/grade.py) 先做两次评分回放，再做第三次录像回放，最后写 `reward.json` / `reward.txt`。普通录像 `Exception` 会被捕获，但 kill、native abort、进程级中断不会。替身在 `start_video` 抛出 `KeyboardInterrupt` 后，两次评分已成功却没有任何 reward 文件。

limited 的 [finalize():74](../../harbor_templates/topogym/limited/environment/sim/server.py) 已在录像前写 `final.json`，这一点更稳健；但收集过程仍需等待录像完成，不能据此推断任意收集超时都会保留完整产物。

**建议**：两种模式均先原子落盘评分结果，再独立记录录像状态、耗时与失败原因；录像有单独预算。验收应在录像开始后终止录像进程，确认 reward、轨迹和 manifest 仍可收集，不能只测正常 Python 异常。

### B06 · P1 · 记录的动作、实际执行前缀和报告时钟不一致

**四个相关行为均用真实函数复现，物理执行由替身控制。**

1. [Session.step():841](../../harbor_templates/topogym/common/rcb_topogym.py) 在 `robot.command()` / `env.step()` 成功前写入 recording。动作被拒绝时，出现 **记录 1 行、执行计数 0**。若物理执行一半出错，简单重放该整行同样不能代表原执行。
2. 成功或失败锁存后继续调用 `Session.step()`，仍追加动作并增加 `n_steps`。复现为 **记录 5 行、计数 5，Env 实际只调用 1 次**。limited 成功通常在一个 chunk 结束时才调用 `finish()`，因此正常成功也能出现此尾部。
3. limited [finalize():80–85](../../harbor_templates/topogym/limited/environment/sim/server.py) 正确用 `end_row` 截断评分/录像回放，但导出 `trajectory.npz` 时仍保存全部 `acts`。复现为 **导出 5 行，评分与录像各重放 1 行**。文件带有 `meta.live_rows`，但通用 replay 入口读取完整 `actions`，所以不同消费者会执行不同内容。
4. [Env.step():430](../../topogym/simulator/env.py) 能在控制周期内部终止，并返回实际 `physics_steps` 和 `action_duration_s`；limited 的 `write_final`、`meta_common`、chunk/watch 输出却用 `n × SUBSTEPS` 与 `n / CTRL_HZ` 推算。复现为 **3 个物理 tick、0.0075 s，被报告成 10 个 tick、0.025 s**。终态后空调用会进一步放大误差。

**建议**：分开记录提交行、接收动作、实际执行控制调用、实际物理 tick 和终止点；时间取 Env/world 的真实时钟。明确处理“拒绝前无状态改变”和“执行中发生故障”。对外 canonical trajectory 保存实际执行前缀，完整请求作为另一份诊断证据。不要只修改一个展示字段，否则评分、视频时间轴、回放仍会分歧。

### B07 · P1 · limited 接受非控制周期整数倍的 dt 并静默改变时长

**CPU 复现。** 服务 SPEC 明确写 `dt` 是 `1 / control_hz` 的整数倍；[do_submit():303](../../harbor_templates/topogym/limited/environment/sim/server.py) 只检查范围，[run_joint_position():259](../../harbor_templates/topogym/limited/environment/sim/server.py) 使用 `round(dt * CTRL_HZ)`。

40 Hz 下提交两行、`dt=0.0375`，请求时长 0.075 s；实际执行 4 个控制步，即 0.1 s，仍返回 `ok=True`。这直接影响动作插值、速度和到达时机。

**建议**：在任何状态改变之前校验整数倍及浮点容差；若协议决定允许量化，则必须返回 `effective_dt` 并据此校验 chunk 长度，更新客户端和说明。验收覆盖半周期附近、合法浮点表示和上限附近输入。

### B08 · P1 · unlimited 可以在冻结初态不匹配时判成功

**CPU 复现，未声称已出现真实错误场景的成功记录。** [grade.py:67–74](../../harbor_templates/topogym/unlimited/tests/grade.py) 创建非 strict Session，然后固定 `gpu=True`，使成功条件 `all_success and (gpu or (... instance_ok ...))` 跳过 `instance_ok`。替身两次成功但 `instance_matches=False`，实际输出 `success=1, instance_ok=0`。

limited 启动使用 `Session(..., strict=True)`，两种模式要求不同。当前 [Session._poses_match():777](../../harbor_templates/topogym/common/rcb_topogym.py) 对无姿态四元数的粒子/FEM 对象只比较质心，也不足以证明布或绳的形状相同。

**建议**：允许 CUDA 在合理容差内非逐位一致，同时必须验证资产/拓扑/初态兼容身份及关键几何；超过容差归为 `not_evaluable`，不能因使用 GPU 就免除实例一致性约束。软体形状检查需要覆盖形变、连接和任务相关初态，不能只看质心。

### B09 · P2 · replay 视频的首帧、末帧和播放时长可能不正确

**CPU 帧序列复现。** [Session.start_video():951](../../harbor_templates/topogym/common/rcb_topogym.py) 立即记录当前帧；grader 随后才调用会 reset 的 `replay()`。因此首帧来自上一次回放终态。`stop_video()` 不强制记录最终状态，`replay.last.png` 只是最后一次采样帧。

复现 5 个控制步、40 Hz、15 fps 时，视频帧为 `previous_replay_terminal, action_3`，实际最终状态是 `action_5`。采样间隔 `round(40/15)=3` 个控制步，即 0.075 s，编码间隔却是 1/15 s，长片段名义速度约 **1.125 倍**；这还未计首尾帧偏差。

**建议**：reset 后记录起点，按真实模拟时间取样，终止后强制终帧；`last.png` 明确来自最终状态。应接入仓库要求的共享录制流程，并在非整除帧率、短轨迹、控制周期内终止三种情况检查视频时间轴。

### B10 · P1 · “物理步内发生过什么”的观测范围不统一

**静态确认与合成状态复现；属于相对用户预期的合同覆盖缺口。** 正式 13 类 Harbor 任务目前通常是：一个控制步 25 ms → 10 个物理 tick，每 tick 2.5 ms → 每 tick 4 个 solver 子步。Task 在每个物理 tick 结束后评估，并非每个 solver 子步都更新终态。

- Buzz、Fiber 的接触收集器覆盖 solver 子步，并对相关几何的覆盖缺失采取不可评估/失败处理；这仍不是连续时间的数学保证。
- Coil、Keyhole、Hedgehog、Horseshoe、Claws 的公共 [RigidTaskDefinition.rigid_measurements():421](../../topogym/tasks/base.py) 读取 tick 末 `contacts`。若接触在前一子步出现、末尾消失，这个函数不看其过程历史。合成状态中放入早期 10 mm 穿透事件和空的末尾接触，函数返回无 failure。
- IPC 任务的形变完整性与终态主要由 tick 末状态判断；不能把 rigid 子步收集器的覆盖结论直接套到 IPC。

已有说明中有“tick 末检查”的限定，因此不能把上述全部叫作违反现有实现合同；但若总体要求是“任一子步发生违规即失败”，当前覆盖确实不齐。增加 solver 子步数本身不会让 Task 自动看见中间事件。

**建议**：先在统一协议里分别定义子步接触事件、tick 状态条件、稳定持续时间的采样语义，再补相应收集与消费。验收需构造“中间违规、末尾恢复”的真实接触轨迹，并验证 reset/replay 不丢事件；不能只靠终帧截图。

### B11 · P1 · 长请求可能超过客户端超时，服务端仍在执行

**静态条件成立，触发频率待真实运行统计。** [rcb_client.py:145](../../harbor_templates/topogym/limited/environment/rcb_client.py) 的 submit 响应超时为 1800 s，observe 为 600 s。服务默认允许 10 s 动作 chunk 和 30 s watch；请求在服务端同步执行到返回，没有可用于重试去重的操作身份。

O01 表明 Knot 近终态几何可让单个控制步的 CPU 判定达到数十秒，因此合法 watch/chunk 存在远超上述超时的条件。HTTP 客户端超时不会撤销已排队或执行中的物理动作，盲目重试可能再次执行。服务预算在控制步边界检查，单步内部慢计算也会导致预算超出。

**建议**：基于实际耗时限制同步请求长度，或采用返回 operation ID、轮询进度和去重的异步协议；输出最后已执行动作/物理 tick。仅把 HTTP timeout 增大不能解决执行状态不明的问题。

### B12 · P2 · Blanket 的不完整 prepare 目录会让 resume 一直跳过

**静态确认。** [difficulty_eval.py:643–647](../../scripts/difficulty_eval.py) 遇到 `build/blanket/` 已存在而 `state/manifest.json` 不存在时，记录 `Preserving incomplete Blanket preparation` 后 `continue`。下次 resume 仍会走同一分支，没有新的准备尝试。

保留失败证据是正确的，但当前没有与保留动作配套的恢复流程。**建议**：将不完整目录保留为带 attempt 身份的历史目录，在新目录继续准备，或者明确输出可执行恢复指令。验收在准备中途终止后重启，要求不覆盖旧证据且最终能完成新尝试。

### B13 · P1 · local 兼容后端的容器清理范围只有 run_id

**静态条件风险，未执行破坏性复现。** [difficulty_eval.py:524–533](../../scripts/difficulty_eval.py) 在没有 delivery 对象的兼容路径，只按 `topogym.difficulty-run=<run_id>` 查找并 `docker rm -f`。不同工作目录/作业若复用 run_id，可能匹配另一作业的容器。持有本作业的 GPU 锁不等于拥有这些匹配容器。

默认 Docker delivery 已有更完整的身份处理；此结论限定于该 fallback。**建议**：统一按 workspace 身份、run 身份、owner token 清理，并记录精确的本次 container ID；用假 Docker 命令验证筛选即可，无需删除真实其他容器。

## 4. Simulator 与 prepare/image 的耗时和优化

### O01 · 高优先级 · Knot 的逐 tick Python 二次复杂度几何检查

[Knot.evaluate_state():92](../../topogym/tasks/knot_untying/common.py) 在每个物理 tick 调用 [planar_clearance():112](../../topogym/utils/geometry/passage.py)，后者对线段做 Python 双层循环和精确距离计算，再检查速度、桌面范围等较便宜条件。

本轮在同一项目 Python 环境内，对合成、有效、无相交的 1 m 直绳做一次调用计时：

| 采样点数 | 单次函数耗时 | 每控制步调用 10 次的算术估计 |
| ---: | ---: | ---: |
| 200 | 0.405 s | 4.05 s |
| 802 | 6.566 s | 65.66 s |
| 987 | 9.973 s | 99.73 s |

这是 **CPU 微基准，不是完整物理 rollout 的平均/P95**。绕结、退化等状态可能提前返回，因此不同状态差异很大。恰好在接近成功、没有交叉的状态，函数需要扫描大量线段对，慢路径与稳定窗口重合。

仅按 0.5 s 稳定窗口约 200 个物理 tick 计算，802/987 点案例的此项判定成本约 **22/33 分钟**，尚未包含 solver、读取状态、渲染、历史保存和其他任务逻辑。两次评分及录像重放还会重复计算。

**优化方向**：使用分块向量化、空间候选筛选和精确线段距离；保留材料邻接豁免、真实相交、退化条件和最小距离诊断的语义。在不影响状态历史的前提下先做便宜的否定条件。用相交、相切、近阈值、反向共线、短材料间距等案例做新旧实现对照。不能通过降低检查频率、减少到少数采样点或跳过稳定窗口来“提速”。本轮未实施优化，也没有声称取得加速比。

### O02 · Blanket 每 tick 对全部投影三角形做几何并集

[Blanket.evaluate_state](../../topogym/tasks/blanket_flatten/common.py) 调用 [footprint_area](../../topogym/evaluation/cloth_metrics.py)，通过 Shapely 计算投影三角形并集。本轮合成平布 90×90 网格、15,842 个三角形，单次 **0.211 s**；10 次/控制步约 **2.11 s** 的 CPU 指标开销，仍不含物理和渲染。真实褶皱的重叠结构可能改变耗时。

**优化方向**：先检查不满足高度/速度/伸长等便宜条件；缓存不变拓扑，研究局部更新或空间分块的精确并集。不能用凸包面积替代投影并集，凸包会掩盖孔洞和折叠并改变成功条件。需要同时核对 coverage 与 stretch/height/release 稳定条件。

### O03 · 无视频评分仍在取 RGB；limited 的 video=none 仍有采集和数组成本

公共配置开启 RGB，[Env.step](../../topogym/simulator/env.py) 在控制步前后获取 observation，传感器会对新的状态生成帧。`--no-video` 只关 writer，没有关闭这些传感器工作；unlimited 两次评分回放都承担该成本。相同 state 的缓存已经存在，不能把同一状态的每次 `render_frame` 都当成重新完整渲染。

limited [Recorder:105](../../harbor_templates/topogym/limited/environment/sim/rcb_limited.py) 在请求期间保存采样帧，`parts()` 即使 video=none 也会走帧栈准备逻辑。以 30 s watch、10 fps、4 路 848×480 RGB 为例，约 301 帧的原始 RGB 就约 **1.47 GB**，尚未包含 stack 副本、depth 和编码缓冲。这是容量估算，不是本轮测得的内存峰值。

**优化方向**：评分 replay 可显式使用纯物理观察配置，视频阶段再按同一实例和动作录制；必须先验证关闭 RGB 不改变任务物理和判据。limited 按用户实际选择采集，video=none 仅保留协议必需的末帧/状态；需要帧序列时采用流式编码或有界缓冲。

### O04 · 每 tick 状态读取、完整性诊断与历史复制还有成本

[GenesisWorld.read_state():341](../../topogym/world/genesis_world.py) 按对象/链接读取位姿与速度，可能产生大量设备到主机同步。[IPC diagnostics():524](../../topogym/world/physics/ipc.py) 还会读取 FEM 数据和计算参考/当前单元行列式；已有 world 状态中的相同数据可以考虑共享。

[Env._save_state](../../topogym/simulator/env.py) 即便采用 segment history，也仍保存逐 tick 的机器人、任务和 RNG 等状态；Task 状态中有复制操作，不能把 segment 等同于“历史无内存增长”。长 episode 需要测量历史增长率。

**优化方向**：合并读取、缓存不可变参考量、共享同一 tick 的诊断输入，减少重复 deepcopy；区分不可变配置与随时间变化的任务状态。保留 rewind、分支失效、RNG 和逐 tick 证据语义。以上是源码热点候选，本轮没有 GPU profiler 分解，不能预先给出收益百分比。

### O05 · prepare 的多次冷启动与 JIT 缓存可再优化

当前 prepare 包含 make-instance、describe，以及 preflight 的 smoke、独立 replay、limited 验证等多次新进程/容器建场景。它们的目的不同，不能只因慢就删除独立重放验证。新进程还可能重复触发 Genesis/JIT 初始化；当前 docker 调用未给这些所有阶段提供统一、明确的持久编译缓存。

**优化方向**：为 runtime 摘要、CUDA/驱动兼容身份、GPU 架构和编译输入建立受控缓存；管理方 prepare/verifier 缓存不应由 agent 任意写入。可以合并同身份的只读描述与实例准备，保留独立 replay 的新进程边界。分别记录 `image lookup/build/pull`、首次 JIT、资产加载、初态准备、preflight、编码耗时，才能确定哪部分值得优先处理。

### O06 · 镜像构建已有缓存与分层，优化应针对剩余失效点

[Dockerfile](../../images/topogym/Dockerfile) 已拆分 uipc 编译与 runtime，使用构建缓存；Nyx 资源准备位于复制任务源码之前。[difficulty_release.py](../../scripts/difficulty_release.py) 对 runtime 输入有筛选，[difficulty_eval.py](../../scripts/difficulty_eval.py) 验证镜像输入身份。源码普通修改不应被简单描述成“每次都重编整个 uipc”。

本地检查的 simulator 镜像体积约 10.33 GB / 11.16 GB，冷拉取、导入和导出可能明显耗时，但本轮未测网络传输与冷编译。**建议**：保留现有锁定依赖与缓存设计，检查实际 cache miss 原因、远端构建缓存与层复用，再决定瘦身；不要为缩镜像删除运行必需 CUDA/Nyx 资源。Blanket 中断恢复先解决 B12，避免人工重建整轮来绕过单实例失败。

## 5. 每个任务的终态与 rollout 约定

下面是**当前源码**的合同摘要，不能用于描述 B01 的旧镜像。`U/L` 列复用 §2.2 的历史短流程矩阵，各自满分为三档；不是完整成功数。稳定窗口指任务条件持续满足所需的模拟时间，具体容差仍以链接中的实现/配置为准。

| 任务与源码 | 成功过程中的特殊约定 | 稳定窗口 | 历史短流程 U/L | 本次重点与完整验证缺口 |
| --- | --- | ---: | --- | --- |
| [Blanket Flatten](../../topogym/tasks/blanket_flatten/common.py) | 投影覆盖、高度、伸长、释放/稳定状态共同满足；初态资产需匹配 runtime/GPU profile | 0.5 s | 3/3；3/3 | O02；新 v2 初态不能继承旧存档身份；短保持不能证明能展开到成功 |
| [Buzz Wire 3D](../../topogym/tasks/buzz_wire_3d/common.py) | 按路线通过，子步金属接触约束，最后在终点台面释放并稳定 | 1 s | 3/3；3/3 | 历史 easy 有完整连续成功；medium 终态未通过，hard 局部终态检查不能当完整 Task 成功 |
| [Cast Coil](../../topogym/tasks/cast_coil/common.py) | 完成装配/分离目标，物体在桌上，释放且安静 | 0.5 s | 3/3；3/3 | 旧 CPU/抓取辅助证明要与正式 CUDA、无辅助配置重新对齐；接触检查范围见 B10 |
| [Cast Keyhole](../../topogym/tasks/cast_keyhole/common.py) | silver 整体进入目标区域，分离关系满足；允许持有的合同不能误加“必须释放” | 0.5 s | 3/3；3/3 | 初生稳定与目标阶段均需完整轨迹；历史证明不等于当前 Harbor 验收 |
| [Fiber Bundling](../../topogym/tasks/fiber_bundling/common.py) | 线端先行、有序穿越，弯曲/方向条件与子步夹爪接触限制 | 0.5 s | 3/3；3/3 | 历史辅助抓取 proof 与 trial 的 assist=none 不同；旧镜像判据版本也不同 |
| [Hedgehog in Cage](../../topogym/tasks/hedgehog_in_cage/common.py) | 刚体目标区域与 cage 分离约束，稳定持有规则按当前配置 | 2 s | 3/3；3/3 | 最长刚体稳定窗口；hard 的初态/狭窄接触风险需真实轨迹验证，不能断言不可解 |
| [Horseshoe Ring](../../topogym/tasks/horseshoe_ring/common.py) | ring 整体进入目标区域，链条拓扑/连接约束继续成立 | 0.5 s | 3/3；3/3 | 局部 route、prefix replay 与完整 Harbor 成功分开记录 |
| [Interlocked Claws](../../topogym/tasks/interlocked_claws/common.py) | 整体放入固定目标区域并满足分离关系，可持有 | 0.5 s | 3/3；3/3 | hold 宽度修复已有证据；hard 有 IK 局部进展但没有完整解，不应假定必须先下降某个固定距离 |
| [Knot Untying](../../topogym/tasks/knot_untying/common.py) | 绳的平面投影无非法重叠、桌面范围、释放稳定与体积完整性 | 0.5 s | 3/3；3/3 | B02、O01；速度阈值很低，材料/摩擦校准和整个稳定窗口仍需实测 |
| [Lock Picking](../../topogym/tasks/lock_picking/common.py) | 钥匙插入各 bore 的位置/深度及转子角等同时满足，不能擅自替换为释放判据 | 0.5 s | 3/3；3/3 | 初始钥匙并非锁死；短距离抬升未复现掉落不代表插入/旋转阶段验证完毕 |
| [Orbits](../../topogym/tasks/orbits/common.py) | cord 与 handle 的整体目标区域、连接关系及完整性 | 0.5 s | 3/3；2/3 | B02；medium limited 暂停；绳长和工作空间限制仅为待验证可达性风险 |
| [Rope Threading](../../topogym/tasks/rope_threading/common.py) | 逐个 ring 的顺序、方向及有限厚度通孔约束，绳安静且完整；不能统一强加释放 | 0.5 s | 3/3；0/3 | B02；通孔几何判据的保守性需与真实环面/绳接触对照；三档 limited 未验收 |
| [Slotted Post Ring](../../topogym/tasks/slotted_post_ring/common.py) | ring 到目标区域，其他物体保留分隔/连接关系，软体完整 | 0.5 s | 3/3；0/3 | B02；缝隙与绳截面/形变可达性没有完整物理证明；三档 limited 未验收 |

Cube Pick Place 是流水线 sanity fixture，另有两个模式的任务包；它不能代表上述 13 类任务已具备完整 oracle。清点中 **104/106 个包没有可执行成功 oracle，而是占位退出**，只有两个 Cube 包有实际 oracle。因此批量跑 oracle 不能被用来声称完整任务验收。

[Buzz 三档证据](../../runs/test_results/buzz_three_tier_component_proof_20260929_01/README.md) 已明确区分 easy 连续成功、medium 失败与 hard 局部结果，应沿用这种区分。其他历史 CPU、带辅助抓取、改变初态或仅离线重新判分的证明，也应保留原身份，不升级为当前正式 CUDA trial 成功。

对于先前[评分链/可达性报告](harbor_grading_reachability_audit_20261001_zh.md)中的机器人可达性推断，本报告采用更窄结论：几何间隙、目标区域位置、绳长或一次 IK 成败，都不足以证明完整任务可解/不可解。目标区域生成本身也不能替代连续机器人路径和真实接触验证。

## 6. Overall rollout 与 output procedure 的对齐情况

模式差异本身不全是 bug：unlimited 允许 agent 自行试验、reset 后提交轨迹；limited 是服务持有的单次 episode。需要统一的是可比的物理、实例、动作、终态及证据语义。

| 项目 | 当前状态 | 需要对齐的内容 |
| --- | --- | --- |
| D01 时间层级 | 控制步、physics tick、solver 子步命名混用，`physics_substeps` 在服务中实际表示控制 decimation | 明确三个时间层级及各自步数；报告实际执行时间，修 B06/B07/B10 |
| D02 初态身份 | 新 prepare 有源码/镜像身份；旧包冻结；unlimited 宽松、limited strict | 同一数据集的兼容初态检查规则统一；软体不能只比较质心，修 B08 |
| D03 动作事实 | limited 内部按 live prefix 回放，但 NPZ 留完整请求 | 统一 canonical 执行动作和请求日志的含义，导出消费者不得各自猜测，修 B06 |
| D04 成功判定 | 当前源码 13 类已启用；旧镜像部分关闭；不同任务有不同释放/稳定/接触规则 | 以 Task 判据为唯一来源生成说明，不能统一加“全部释放”或拿 planner 子目标当成功 |
| D05 回放策略 | unlimited 默认两次独立 reset replay；limited live 结果加 finalize replay | 差异可以保留，但报告说明成功门槛、非确定性与实际执行前缀，不能只呈现一个无上下文 success |
| D06 录制流程 | 当前 Harbor 公共工具有独立 imageio writer，limited 另有 Recorder/ffmpeg 路径 | 与仓库要求的 `topogym.recording` prepare → session/replay → validate → archive 对齐；仅调用兼容 writer 不算完成 |
| D07 reward 与录像 | unlimited 后写 reward，limited 先写 final 但收集仍依赖收尾 | 评分原子落盘、录像状态独立、失败仍保留已有证据，修 B05/B09 |
| D08 错误分类 | 收集器已把 `missing_log`、未 finalized 当作 infra；畸形 NPZ 却被 grader 错归 infra | 区分 invalid_submission、task_failed、not_evaluable、infrastructure_error，不把 solver 异常一概判 agent 失败 |
| D09 时间预算 | 原始包 5400 s；三档通常 21600 s，Knot 36000 s；新 sampler 上限统一 21600 s | 比较结果必须带实际预算；统一 sweep 预算是设计选择，但不能无说明地与 Knot 10 h 历史结果比较 |
| D10 说明中的性能估计 | 生成器以短描述运行估计 sec/step，且仍写“每物理步 full checkpoint” | 说明 segment history；初态三步耗时不代表近终态或最慢阶段，给分阶段成本与测量身份 |
| D11 验收等级 | 静态包检查、短流程、局部 planner、完整成功目前分散在多个报告 | 每个 task/tier/mode/runtime 分列静态、短流程、完整终态、独立评分、输出验证，避免继承不存在的通过项 |

共享录制要求的原文及用法见 [AGENTS.md](../../AGENTS.md) 与[录制模块文档](../develop/modules/recording_module_usage_zh.md)。本轮未创建新 GPU 录像，因此没有新增另一套正式录制实现；CPU 帧替身仅用于复现 B09。

建议统一的交付顺序是：**冻结源/镜像/资产/实例身份 → prepare 与初态兼容检查 → 接收并校验动作 → 保存实际执行与过程事件 → 锁存终态 → 独立 replay 与评分 → 原子保存评分 → 生成并验证视频/末帧 → archive/collect**。任一阶段失败，都应保留已完成阶段及明确错误分类。

## 7. 已修复项与本轮仍未关闭的验证

### 7.1 不应重复计为“当前源码仍坏”的问题

[builder 修复计划](../rcb/builder_feedback_repair_plan_zh.md)及[执行报告](../../runs/test_results/rcb_builder_feedback_20261001/run_151751/report_zh.md)中，下列修复已进入当前源码，并有不同层级证据：

- hold 时保留已接收的 native gripper 目标，避免宽度反算让手指意外张开；有 CPU 与三档短 GPU 保持/回放证据。
- 当前工具的 float32 关节边界处理；不能把旧冻结工具行为自动归到新模板。
- Blanket 初态 manifest 可读权限及可读目录树；v2 存档增加 profile 兼容身份，但不承诺任意 GPU 之间直接恢复。
- engine seed 的 int32 范围映射；已有边界值普通模式证据，最大 seed 的 limited 项仍待完成。
- 工具选择、preflight 客户端依赖、镜像版本/身份解析等 builder 问题。

这些“源码已修复”仍需和实际投产镜像/新任务版本绑定。B02 描述的是单独生成器使用的固定镜像尚未同步，不是当前新 difficulty 的源码哈希构建会遗漏修正。历史 Nyx 退出阶段出现过 `Failed to export shader library`，已有对应 0 退出码和通过视频验证的记录；目前不能据该字符串单独判 trial 失败，根因仍未关闭。

### 7.2 需要下一轮补齐的验证

1. **先稳定评分与动作协议**：B04–B09 用针对性合同测试即可先验收；测试实际消费者能否重放导出的执行前缀，并检查 reward 中断恢复。
2. **验证最终 runtime**：当前源码生成的新不可变镜像需补四类 IPC 任务的运动同步、接触、reset/replay。只有继续支持历史冻结包时，才另行安排其新 revision；这不作为当前新 run-trials 的前置修复。
3. **优化判据热点后重新定预算**：Knot、Blanket 做真实 scene 的分阶段 profiler，记录初态、操作中、近终态、稳定窗口的 P50/P95；先确认判据等价，再比较性能。
4. **恢复尚未完成的短流程矩阵时保持原任务状态**：先前暂停项仍标暂停/未运行。需要执行时以最终源码、镜像与初态重新建立 run 身份，不直接把旧矩阵改成通过。
5. **建立完整终态证据**：每类每档在正式配置下，从规定初态连续执行，提供执行轨迹、过程违规证据、稳定窗口、独立评分与验证后视频。无法完成的任务明确标 `not_proven`，不要以静态或局部 proof 填补。

当前新 run-trials 建议优先处理 B04–B08 的结果可信度和 O01/O02 的时间瓶颈，再补 B09/B10 与整体过程证据。B11–B13 可与编排维护一并处理。B01–B03 仅在继续支持旧任务包、旧 run 或单独固定镜像入口时处理，不占用本次当前流程的 bug 修复优先级。本轮交付的是问题审查与证据，以上建议尚未实施。

## 8. 本轮验证记录与复现

统一证据目录：[run_trials_audit_20261001](../../runs/test_results/run_trials_audit_20261001/README.md)。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 106 个任务包静态检查 | 通过 | [static_tasks_correct_python.log](../../runs/test_results/run_trials_audit_20261001/static_tasks_correct_python.log) |
| 14 组 CPU unittest | 154 项通过 | [verification_summary.json](../../runs/test_results/run_trials_audit_20261001/verification_summary.json) 与同目录各 suite 日志 |
| 控制流、动作/时间、视频边界复现 | 复现本文所述行为 | [cpu_probes.json](../../runs/test_results/run_trials_audit_20261001/cpu_probes.json) |
| Knot / Blanket 纯函数计时 | 单次微基准已记录 | 同上 `cpu_metric_timings` |
| 本地镜像与源码对照 | 完成，无构建/推送 | [images.json](../../runs/test_results/run_trials_audit_20261001/images.json)、[image_comparison.json](../../runs/test_results/run_trials_audit_20261001/image_comparison.json) |
| Docker delivery 集成 | 未执行；启动脚本要求 work-dir/controller 上下文 | `test-difficulty-docker.log` 仅参数校验失败，不算产品运行 bug |
| 新完整 GPU / 模型 trials | 未执行 | 新增物理 rollout 数为 0 |

首次静态检查误用了缺少 `tomllib` 的宿主 Python，已切项目 Python 后通过；HF CPU suite 首次因沙箱禁止本地 Unix socket 失败，允许该本地测试能力后 22 项通过。这两项不能计入 run-trials 产品缺陷。测试没有进行真实 HF 上传。

主 CPU suite 执行器每 0.5 s 采样资源，记录的系统 CPU 峰值 21.7%、内存峰值 16.1%，无资源阈值终止；该数字不是全会话、GPU workload 或每个补充微基准的峰值。机器 GPU 经权限内检查可见为 RTX 4090，不能把最初沙箱内的 NVML 访问失败写成机器没有 GPU。

可在相同工作树/依赖环境复现静态检查和控制流探针：

```bash
cd /home/jianwen/topogym
PATH="$PWD/.venv-gs121-nyx/bin:$PATH" bash ci_checks/run_all.sh
.venv-gs121-nyx/bin/python runs/test_results/run_trials_audit_20261001/topogym_audit_probes_20261001.py
```

探针使用真实 Session/Env/grader/服务函数，但替换物理和视频 writer；会重写本证据目录的 `cpu_probes.json`，复验时应复制脚本并改到新的输出目录，以保存本次证据。具体边界见同目录 README。没有任何一个通过项可以替代最终镜像下的完整物理和模型 trial 验收。
