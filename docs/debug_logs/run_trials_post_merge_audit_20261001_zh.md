# 合并后的 Run trials 问题复核

日期：2026-10-01（Chicago；复核结束时 UTC 已为 2026-10-02）。对象为当前合并工作树、新生成的 tooling v4 privileged/standard 任务，以及 `0.2.5-cu128` 镜像。

**结论：合并修复了镜像交付、Knot 判据热点和 standard 生命周期中的多项问题，但上一轮动作、评分、时间统计及录像输出问题没有全部消失。** 本轮重新执行了 CPU 回归和针对性复现，没有仅根据合并说明判断。

后续修复的修改范围、依赖顺序、合同与验收标准见[修复工程计划](../rcb/run_trials_post_merge_repair_plan_zh.md)。计划制定时合并已提交到 `6a7c755`，相关 97 个源码文件与本次审查基线一致；下文保留审查当时的状态与证据，不代表修复已完成。

当前 Git 仍是合并待提交状态：HEAD 为 `c8d1f8ff7d8d161197a8be588b801ecaa74713f7`，MERGE_HEAD 为 `8ad74b46f1b4960ef91bd7476a7c90dca0f7977b`，未解决冲突为空。本报告的源码身份以[本轮基线](../../runs/test_results/run_trials_post_merge_audit_20261001/baseline.json)为准。本轮没有修改生产代码、任务包或 Git 暂存区，也没有 commit/push。

## 1. 本轮实际验证

- **106 个现有任务包和 4 个新 v4 包的静态检查通过**；协议检查仍有历史迁移警告，不能理解为 strict migration 零警告。
- **15 组 CPU 回归共 160 项通过**，包括合并工具、builder、difficulty、结果收集和 HF 测试。
- **standard 协议恢复测试 14/14 通过**，使用本机 toy server、真实共享协议和客户端，不使用 GPU。
- 对实际 Session、Env、grader、standard dump/replay 和请求处理函数做替身复现；重新测量 Knot 与 Blanket 的纯 CPU 几何函数。
- 从未启动的临时容器读取 `0.2.5-cu128` 中的 IPC 源码，核对后移除该临时容器。
- 复核[合并验证记录](../../runs/test_results/merge_local_remote_20261001/README.md)的 GPU 报告和对应源码哈希。**本轮新增 GPU rollout 为 0**，没有恢复暂停的长跑或模型评估。

[验证汇总](../../runs/test_results/run_trials_post_merge_audit_20261001/verification_summary.json)记录了范围与资源。受监控 CPU suite/协议运行的系统 CPU 峰值 36.8%、内存峰值 17.7%，没有资源阈值终止。2257 个基线文件中，复核期间检测到 `topogym/planning/fiber_bundling/stages.py` 有本轮未写入的并行改动；本轮没有覆盖它，也不为新 planner 行为补发通过结论。本文检查的 runtime、模板、评分及几何指标文件未在验证期间变化。[并行变更记录](../../runs/test_results/run_trials_post_merge_audit_20261001/concurrent_source_changes.json)

## 2. 截图中的合并项是否落实

| 合并项 | 当前结论 | 已有证据及边界 |
| --- | --- | --- |
| hold 宽度换算导致夹爪张开 | **修复保留** | 本轮 builder 16 项回归通过；合并 GPU 记录中 Interlocked hard 保持 40 控制步/400 tick，抓持及 reset 后保持通过。与 B06 的动作日志问题不同。 |
| 初态权限、Blanket v2 profile/布局兼容 | **修复保留** | CPU 合同通过；合并记录验证镜像内 6 个 v2 资产哈希和 easy 非 root 恢复/接续。medium/hard 只核对资产，未重跑物理接续。 |
| 预检工具不一致、过期预检继续运行 | **修复保留** | difficulty 27 项通过；新包使用 v4 公共工具，并适配 standard client、run/finalize、fresh-process replay。 |
| 固定镜像缺 IPC 修正 | **对新默认 0.2.5 已解决** | 本轮直接核对镜像内 `ipc.py` 与工作树逐字节相同。旧 tag 不会因此改变。 |
| IPC 旋转轴方向与 Genesis 相反 | **修正保留，完整物理覆盖仍不足** | 合并 Knot 前缀的最大连杆偏差约 `4.45e-6 m`；只完成 19 个控制步，不是全族或双向长跑验收。 |
| FEM 梯度 checkpoint 累积 | **当前公共工具已限制增长** | 合并回归验证保留原 save 调用、关闭梯度时只留一个 checkpoint、重复安装无叠加；Knot 19 步 GPU 样本均为 1 个 checkpoint。没有长期总显存稳定性证明。 |
| Knot Python 判据慢 | **v4 Session 热路径已优化** | 本轮同一合成输入比对，802 点从 6.724 s 降至 0.0702 s，约 96 倍；详见 §4。 |
| standard 恢复、尾部动作评分、回放收尾 | **协议恢复与正式回放前缀已验证；输出统计仅部分解决** | 本轮 14/14 协议恢复通过；正式 replay 只执行 live_rows。原始 NPZ 仍保存全部行，时钟仍按行数推算，见 B06。 |
| privileged/standard 命名、固定 client 依赖 | **已接入当前生成与收集流程** | 106 个现有包及 4 个 v4 新包检查通过；收集器支持新旧后缀。旧报告的 unlimited/limited 分别对应新 privileged/standard。 |
| infra_error / gpu_lost 被记成未解任务 | **已修复对应分类** | 当前收集器和预检显式识别这两个字段；本轮合并回归通过。它不解决 B04 的畸形提交被误归 infra。 |

`0.2.5-cu128` 的实际镜像 ID 为 `sha256:9a8c7f1c2ca0a2f26c2f36dd30cd1fd07c7a81f31ccbd0e7a7e8f4edbdc6ee80`。IPC 源码哈希为 `de90e56959e32aade772d9b5093e4b5366d3577e8703da68060f7bca6d481140`，包含轴方向修正和同步 guard。[本轮镜像核对](../../runs/test_results/run_trials_post_merge_audit_20261001/image_verification.json)

注意：**checkpoint 限制和 Knot 向量化位于公共任务工具 `rcb_topogym.py` 中，不仅是 simulator 镜像内容。** 新生成器采用 v4；只换基础镜像而保留旧任务工具，不等于获得全部 v4 修复。现有 106 个冻结包中，24 个 IPC 包已有远端专用工具中的优化，但仍不能当作全部包已统一采用当前 v4。

## 3. 上一轮 B04–B13 的逐项状态

编号继续对应[合并前报告](run_trials_full_audit_20261001_zh.md)。按原条目归类，6 项仍存在、3 项有改善但未完全解决，另 1 项是仍未补齐的过程观测合同；这不是说合并没有修复其他问题。

| 编号 | 当前状态 | 合并后重新核对的结果 |
| --- | --- | --- |
| B04 畸形提交误判基础设施故障 | **仍存在，CPU 复现** | 缺少 `actions` 的 NPZ 得到 `success=0, grader_error=1`。收集器会记为 infra_failed，编排仍会停止后续队列。 |
| B05 录像故障影响 reward 收尾 | **部分改善，残留已复现** | 正常路径已由 3 次回放减为 2 次，在最后一次评分时录视频；普通 Exception 能回退。但两次 replay 均已成功后，在 `stop_video()` 发生进程级中断，reward.json/txt 仍均不存在。 |
| B06 动作记录、执行前缀及时间统计 | **部分改善，残留已复现** | standard fresh replay 正确截取 live_rows；拒绝动作仍先入记录，终态后仍计步，NPZ 仍含未执行尾部，physics_steps 仍由控制计数推算。 |
| B07 非整数控制周期 dt | **仍存在，CPU 复现** | 40 Hz 下 2 行 `dt=0.0375`，请求 0.075 s，实际执行 4 步即 0.1 s，仍返回 ok。 |
| B08 privileged 初态不匹配仍可成功 | **仍存在，CPU 复现** | 两次成功、`instance_matches=False` 时仍得到 `success=1, instance_ok=0`；standard 创建 Session 使用 strict=True，约束继续不一致。 |
| B09 视频首尾帧与播放时间 | **仍存在，CPU 复现** | privileged 最后一轮录像仍在 reset 前取首帧；5 步只捕获上一轮终态与 action_3，最终 action_5 未入视频。40→15 fps 的 round 采样仍有速度偏差。 |
| B10 物理步内短暂事件覆盖 | **合同缺口仍存在** | 刚体公共判据仍看 tick 末 contacts；合成早期穿透事件在末尾 contacts 为空时未触发 failure。未新增真实短暂接触漏检的 GPU 证明。 |
| B11 长请求与客户端超时 | **部分改善** | 新增逐控制步 journal、断连检测和 900 s 请求上限；但 observe 客户端仍为 600 s，单步内部不能及时取消。复现无断连信号时 601 s 不停、901 s 才触发上限。 |
| B12 Blanket 不完整 prepare 无法继续 | **仍存在，静态确认** | blanket 目录已存在但缺 manifest 时仍直接 continue；重复 resume 仍跳过，没有独立新 attempt。 |
| B13 local 清理容器范围过宽 | **仍存在，静态确认** | 非 delivery 的兼容路径仍仅按 run_id label 执行清理，未增加 workspace/owner 约束；默认 Docker delivery 不受这个具体分支结论影响。 |

控制流、输入、视频帧和时间的结果见 [cpu_probes.json](../../runs/test_results/run_trials_post_merge_audit_20261001/cpu_probes.json)。这些探针执行真实函数，但显式替换物理与 writer；不会被记为真实物理成功或真实 native crash。

### B05 的剩余边界

当前 [privileged grader](../../harbor_templates/topogym/unlimited/tests/grade.py) 在第二次 `s.replay()` 返回并加入 `outs` 后调用 `s.stop_video()`，最后才写 reward。本轮在 `stop_video()` 注入 `KeyboardInterrupt`，确认 **2 次成功 replay 已完成，reward 文件仍为 0 份**。[独立复现记录](../../runs/test_results/run_trials_post_merge_audit_20261001/video_verdict_boundary.json)

因此不能继续使用旧报告“必有第三次录像回放”的描述，也不能把此次优化当作评分已经与编码收尾隔离。建议在评分结果齐备后先原子保存 verdict，单独保存媒体收尾状态。standard 的新 finalize.sh 也依赖 replay 进程返回 JSON；它现在能识别 replay/基础设施失败，但不是媒体中断后仍能独立保留已完成评分的证明。

### B06 中已经正确的部分与剩余部分

本轮调用当前 [standard dump](../../harbor_templates/topogym/limited/environment/sim/server.py) 和 [fresh replay](../../harbor_templates/topogym/limited/environment/sim/replay.py)，确认：保存了 5 行动作、`live_rows=1`，正式 replay 只执行了 1 行。这一评分前缀行为正确，合并合同测试也覆盖它。

未解决的是输出与时钟：

- [Session.step](../../harbor_templates/topogym/common/rcb_topogym.py) 拒绝动作时仍留下 1 行记录，执行计数为 0。
- 终态后的 5 次调用留下 5 行/5 个计数，但 Env 实际只被调用 1 次。
- standalone 通用 replay 仍读取完整 actions；它和读取 episode.json/live_rows 的 standard 正式 replay 不具有相同输入语义。
- [Env.step](../../topogym/simulator/env.py) 在控制步内实际执行 3 tick、0.0075 s，服务按 1 个完整控制步上报 10 tick、0.025 s。

这与截图中的 hold 目标修复不是同一问题。建议分别保存 requested/accepted/executed 信息，导出明确的执行前缀，并从 Env/world 取真实 tick 与模拟时间。

### B11 不再适用的旧说法

旧报告“HTTP 超时后服务可能一直执行完整长 chunk”的描述需要收窄。新 [Episode.journal](../../harbor_templates/topogym/limited/environment/sim/rcb_limited.py) 会在下一控制步边界检查客户端断开并停下，本轮断连和长请求协议测试已通过。

剩余问题是服务统一 900 s 上限高于 [get_obs 的 600 s 超时](../../harbor_templates/topogym/limited/environment/rcb_client.py)，以及检查只能发生在控制步返回之后。建议让服务器预算早于对应客户端截止，并保留可查询的执行进度；本轮不再将“完全没有断连处理”列为现状。

## 4. 性能项复核

### Knot 的慢循环在 v4 热路径中已替换

相同 Python 环境、合成 1 m 无相交直绳、相同参数，各实现单次调用：

| 采样点 | 原 Python 循环 | 当前向量化函数 | 本次函数加速比 |
| ---: | ---: | ---: | ---: |
| 200 | 0.4076 s | 0.00453 s | 90.0× |
| 802 | 6.7242 s | 0.07023 s | 95.7× |
| 987 | 10.2552 s | 0.10490 s | 97.8× |

本轮这三组的布尔结果与最小距离一致；合并的 CPU 回归另外覆盖随机曲线、交叉、退化和无效输入。这是**函数微基准，不是整个 simulator 的 96 倍加速证明**。

优化通过 [Session 初始化](../../harbor_templates/topogym/common/rcb_topogym.py)安装到 Knot task 模块；通用 [passage.planar_clearance](../../topogym/utils/geometry/passage.py)本身未改。首次 `Env.reset()` 发生在安装之前，纯 Env 调用方也不能自动继承此 Session 优化。新函数仍枚举 O(N²) 线段对，内存和更大规模性能需另测。合并记录中的 Knot 长跑被中断，不能据此宣称整个 rollout 已满足时间预算。

### 其他性能方向

| 原项 | 合并后状态 |
| --- | --- |
| O02 Blanket 投影并集 | 实现未变；15,842 三角形的本次单次计算为 0.2168 s，原审查为 0.2114 s，同量级，不能认定已优化。 |
| O03 渲染及多次回放 | 正常评分由 3 遍降至 2 遍，减少了一次物理回放；但无视频评分仍启用 RGB，standard video=none 仍采集帧并准备 stack。剩余渲染/内存热点保留。 |
| O04 状态、历史与显存 | 新修复限制的是 FEM 的梯度 checkpoint 缓存；逐 tick 的 world 状态读取、Task/RNG 历史与复制仍存在。不能将两类存储混为一谈。 |
| O05 prepare/建场景冷启动 | 多阶段建场景仍存在。合并 Rope easy 在 300 s 以上初始化后主动中断，并出现 Newton 上限警告；瓶颈仍需定位，尚无合并前后对照来判定回归归因。 |
| O06 镜像构建 | 原有缓存/分层保留，0.2.5-cu128 已构建；没有本轮冷构建计时，也没有新的构建加速比。 |

[源码哈希对照](../../runs/test_results/run_trials_post_merge_audit_20261001/unchanged_simulator_files.json)确认 Env、任务基类、Blanket 判据、cloth metrics、原 passage、IPC 与 GenesisWorld 相对上次审查未变化。IPC 的变化是修正版现在进入了新镜像；Knot/FEM 的变化主要在公共工具层。

## 5. 镜像和任务流程的边界

- 当前单独生成器默认镜像版本变为 **0.2.5-cu128**；新工具版本变为 **v4**；新包命名采用 **privileged/standard**。
- 根 `tasks/` 仍有 106 个冻结包，只是按合并内容更新了名字/协议等文件：28 个仍引用 0.1.0、78 个仍引用 0.2.3-cu128，没有自动改到 0.2.5。[本轮逐包清单](../../runs/test_results/run_trials_post_merge_audit_20261001/task_inventory.json)
- 因此 B01、B03 仍是旧入口问题，继续排除在当前新 run-trials 的 bug 数之外；B02 中“新默认镜像缺 IPC 修正”已关闭，对旧 tag 的历史事实不改写。
- standard 已改为 live 服务退出后，在同一 GPU 上启动独立 replay 进程。这比旧的同 Session 收尾边界更清楚，普通路径两遍完成评分及视频。
- 正式 Harbor 视频仍走公共工具中的自有 writer 和 shared standard Recorder；合并 GPU 检查使用共享录制模块，不代表 Harbor 录像已完全迁移到 `topogym.recording`。B09 与这项流程差异仍需处理。

## 6. 尚不能标记完成的 GPU 验证

这些结果引用合并验证的原始报告，本轮未重跑：

| 项目 | 当前证据 | 不能据此声称的结论 |
| --- | --- | --- |
| [Interlocked hard](../../runs/test_results/merge_local_remote_20261001/interlocked_hard/report.json) | hold/reset 后 hold，40 控制步/400 tick 通过 | 完整放置/分离路径可解 |
| [standard 收尾](../../runs/test_results/merge_local_remote_20261001/build/topogym-merge-interlocked-claws-i00/limited/final.json) | 1 个控制步，超时正常结束，fresh replay/视频完成，live/replay SHA 相同 | 长 episode、所有终态、所有任务的完整成功 |
| [Knot hard](../../runs/test_results/merge_local_remote_20261001/knot_hard_ipc/report.json) | 保留 19 控制步/193 tick 前缀，checkpoint 样本恒为 1，连杆误差很小 | 160 步长跑通过、全程双向运动通过、长期无显存泄漏 |
| [Rope Threading easy](../../runs/test_results/merge_local_remote_20261001/rope_easy_ipc/report.json) | 初始化超时中断，控制动作 0 步 | 可运行性及双向同步检查通过；也不能无对照归因为此次合并引入 |
| [Blanket easy v2](../../runs/test_results/merge_local_remote_20261001/blanket_v2_easy/report.json) | 非 root 恢复、接续与 reset hold 通过 | medium/hard 接续也通过，或跨任意 GPU 存档兼容 |

四类 IPC 的完整验证、39×两模式完整矩阵、cu130 与完整任务成功仍未完成。下一轮优先处理 B04/B05/B06/B07/B08 的结果可信度，再针对 Rope 启动和 Knot 整体耗时补 profiler/受控 GPU 验证。短流程成功与完整任务可解继续分开记录。

## 7. 复现材料

证据目录：[run_trials_post_merge_audit_20261001](../../runs/test_results/run_trials_post_merge_audit_20261001/README.md)。目录含基线身份、静态与 unittest 日志、standard 协议记录、适配合并代码的 CPU 探针、独立视频收尾探针及镜像 IPC 文件。

旧探针中的 `finalize()` 已随合并拆成 dump/fresh replay，本轮改用新的实际函数复现，未把旧探针因函数不存在而失败算作产品 bug。全部探针使用单独输出目录，不覆盖合并前或合并操作产生的证据。
