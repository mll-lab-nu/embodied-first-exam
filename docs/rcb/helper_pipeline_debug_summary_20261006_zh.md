# Helper sweep 问题、修复与待查事项（2026-10-06）

> 2026-10-06 回退说明：本文记录的是扩展 helper runner 的历史方案或发布状态。当前开发仓库已恢复原版 `run_agent_batch.sh`，新增派单/自动准备/封存入口已归档；下文命令不再直接适用于当前 checkout。已有固定 helper release 和实验记录未修改。

本页整理这一轮 helper 机器上的 Muse/OpenRouter 调试结果，区分已经修复的代码问题、尚未调整的判定逻辑，以及缺少证据的原因。操作命令仍以 [helper 运行手册](rigid_sweep_helper_runbook_zh.md) 为准。

**当前结论：运行控制、失败恢复和诊断日志已有修复并已发布，但尚未取得新版在 helper 机器上完整跑通的结果。** 旧批次封存成功、模型连通检查通过或 GPU 检查通过，都不能单独证明正式实验完成。

## 1. 本轮范围与版本

| 项目 | 当前设置 |
| --- | --- |
| Helper 仓库 | <https://github.com/LUIGIVAMPER/topogym-sweep-release-v1> |
| 本次诊断版本 tag | `rigid-v17-20261006-diagnostics01` |
| 对应 commit | `cd6138070a9fdf0185c37fa00af2e03d0caa1989` |
| 冻结任务环境 | merged-v17 / tooling 17 / 镜像 0.2.15-dev |
| 本轮测试模型 | `AGENT=muse-openrouter`、`MODEL=openrouter/meta/muse-spark-1.3-contributor`、`EFFORT=default` |
| 正式 sweep | 8 个任务 × 3 个难度 × 2 个模式 × K=3，共 144 个 trial |
| 小测试 | Interlocked Claws easy × 2 个模式 × K=3，共 6 个 trial |
| 实例选择 | 每个难度固定 oracle 参考 seed 0，同一实例重复 3 次 |
| 每个 trial 的预算 | 12 小时、150M input tokens、10M output tokens |

8 个任务为：Interlocked Claws、Lock Picking、Hedgehog in Cage、Fiber Bundling、Horseshoe Ring、Cast Coil、Cast Keyhole、Buzz Wire 3D。难度为 easy、medium、hard；模式为 privileged、standard。

本次发布更新的是主机上的 runner、适配层和诊断工具。与上一版相比，1414 个任务及镜像材料文件保持不变，**此次诊断更新不要求重新构建任务镜像**，也没有将冻结的 v17 实验升级为 v18。

注意：当前 token 超限在运行后判分，不能将 150M / 10M 理解成达到额度立即停止付费请求的实时开关。

## 2. 已修复的代码问题

这里的“已修复”指代码已更新并有对应验证；不表示旧失败 trial 被改成成功，也不表示所有 helper 主机问题都已解决。

| 编号 | 问题及影响 | 已实施的修复 | 仍需注意的边界 |
| --- | --- | --- | --- |
| F1 | Harbor 记录了 trial 异常，却可能返回进程退出码 `0`；外层只看退出码，导致同一个基础设施故障被整批重复执行 | 每个 job 结束后检查全部 K 次 trial 的实际结果；基础设施异常或缺少结果时停止后续 job | 检查发生在 job 边界；一个 K=3 job 内仍可能先出现 3 次失败，不是每出现一次异常就立即中断所有进程 |
| F2 | 只确认 Docker/宿主机存在 GPU，不足以确认正式任务容器能使用 GPU | 启动前用任务绑定的镜像和 Compose GPU 配置检查容器启动、GPU 身份和最小 CUDA 运算 | 不代表完整物理、Vulkan 渲染或录像已经通过；没有重新加入显存门槛和等待逻辑 |
| F3 | 独立运行 `scan_secrets.py` 等 CLI 时，导入 `harbor_agents` 失败 | 修正仓库模块搜索路径，使这些入口不依赖特定工作目录或额外 `PYTHONPATH` | 这修复的是导入问题；缺少封存清单仍会阻止交付 |
| F4 | 运行中断后留下部分 mirror，恢复时直接被拒绝；缺少 inventory 又进一步阻止扫描 | `finish_agent_batch.py --recover` 保留旧副本，补充恢复副本、扫描并生成封存清单 | 恢复不能重建没有记录过的历史数据；交付不完整时仍标记 `delivery_complete=false` |
| F5 | 镜像复制/收尾命令超时后，复制容器可能继续写文件，影响后续恢复 | 为收尾容器命名并记录归属；超时清理本次拥有的容器，恢复前检查旧写入进程 | 不终止无关任务；不能据此断言旧 `TimeoutExpired` 的原因就是复制超时 |
| F6 | 启动检查没有覆盖 Buildx，直到评分侧镜像构建时才暴露构建工具问题 | 模型请求前检查 `docker buildx version` 和 `docker buildx build --help`，记录版本 | helper 本机究竟缺少还是损坏了 Buildx，仍需该机输出确认；这也不保证所有后续镜像构建必然成功 |
| F7 | 外层只显示 `ValueError` / `TimeoutExpired`，不能区分模型、Harbor、镜像复制和清理阶段 | 增加逐请求日志、原生 Muse/包装层退出状态，以及 runner 阶段、超时和异常日志 | 新日志只覆盖新版运行，无法补造旧运行缺失的调用栈 |

相关实现：

- [任务结果检查与运行控制](../../scripts/agent_batch_runtime.py)
- [Docker、Buildx 与任务 GPU 容器检查](../../scripts/agent_batch_host.py)
- [独立 CLI 的合同与导入逻辑](../../scripts/agent_batch_contract.py)
- [mirror 恢复复制](../../scripts/agent_batch_mirror_copy.py)、[恢复封存入口](../../scripts/finish_agent_batch.py)
- [runner 诊断记录](../../scripts/agent_batch_diagnostics.py)

## 3. 已确认存在、但尚未调整的判定逻辑

**Muse 是否完成执行，与 token 是否完整计量，目前仍会相互影响最终退出状态。**

旧证据里，一次 Muse 运行记录了 `run.terminal.completed`，但 usage 报告保留了历史请求错误，因此 `complete=false`，包装层仍以失败退出。当前适配层的历史错误不会因为后续请求成功而自动清除。

这说明现有判定可能过严，**不等于已经证明 token 加法有误或一定发生漏计**。需要分别回答三个问题：

| 要判断的事情 | 应查看的证据 |
| --- | --- |
| Muse 原生执行是否正常完成 | 原生进程退出码、原生终态事件 |
| 模型用量是否完整 | 每次请求的 generation ID、usage，以及失败请求是否可能已产生计费 |
| 任务是否真正解出 | 正式 verifier 的 verdict 和评分证据；agent 自述不替代评分 |

新版 `agent/muse-run-status.json` 将原生退出码、终态、包装层退出码及原因、当时的计量状态分别记录。**本次只补齐证据，没有放宽退出、计量完整性或正式评分规则。** 是否调整规则，要结合新日志和服务商计费记录决定。

相关实现：[OpenRouter 请求与计量](../../harbor_agents/muse_transport/bridge.py)、[Muse 启动和退出判定](../../harbor_agents/muse_transport/launch.py)。

## 4. 尚未搞清楚的原因，以及需要什么证据

| 编号 | 待查问题 | 目前已有的证据 | 还需要什么才能下结论 |
| --- | --- | --- | --- |
| U1 | 为什么有请求返回模型不存在的 404？ | 真实响应包含 `The requested model was not found`；同轮也有成功请求 | 同次请求的时间、HTTP 状态、请求 ID、返回模型、服务商信息；必要时由 OpenRouter 根据 ID 查询。不能只凭 404 断言 key 错误或账户没钱 |
| U2 | `BrokenPipeError` 是哪一端先断开？ | 旧报告记有 BrokenPipe，但缺少方向和阶段 | 是读上游响应还是写给 Muse 时失败、终态/usage 是否已收到、Muse 是否取消或退出；新版逐请求日志与原生日志联合判断 |
| U3 | 外层 `TimeoutExpired` 到底是哪条操作超时？ | 旧 lane 在收尾附近退出，但没有保存具体命令和完整栈 | 新版 runner 的阶段、操作类别、期限、耗时、容器名、异常栈。历史事件无法仅靠新代码还原 |
| U4 | helper 的 Buildx 究竟是什么问题？ | 评分侧构建报 `unknown flag: --file`，之后出现 Compose 配置连带错误 | 同一用户和终端下的 Docker/Compose/Buildx 版本与命令检查输出；没有这些证据，不能确定是未安装、版本问题还是命令解析异常 |
| U5 | 是否有真实 token 漏计或重复计数？ | 已有部分 generation usage，但请求错误后计量标记不完整；尚无算术错误证据 | request → generation → usage 对应关系，重复 ID 是否只计入一次，以及服务商按 generation ID 的计费记录。没有收到 usage 不代表没有产生费用 |
| U6 | Vulkan/渲染是否真的失败？ | agent 曾自述 Vulkan SIGABRT，并改用纯物理方式 | 原始模拟器 stderr、崩溃栈、渲染配置、Vulkan 驱动/ICD 信息和实际镜像身份。CUDA 检查成功不能排除渲染问题 |
| U7 | 冻结资产是否发生了 hash 不一致？ | agent 曾描述 URDF / model JSON hash 差异 | 明确的文件路径、预期与实际 SHA-256、实例身份、使用的镜像和校验程序输出；目前不能认定是任务包损坏 |
| U8 | 会话目录权限/Bubblewrap 警告是否影响执行？ | stderr 有目录权限和 Bubblewrap 警告 | 同次运行 UID/GID、目录权限、原生退出码和终态，以及对应失败栈。警告本身不足以解释整个 trial 失败 |

目前没有证据支持把所有问题统一归结为“helper 没有 GPU”“API key 无效”“账户额度耗尽”或“Windows 换行符”。helper 已展示宿主机和 Docker 中的 `nvidia-smi` 成功；这证明相应检查下 GPU 可见，但不能替代实际任务容器和渲染检查。

## 5. 新版会留下哪些诊断材料

无需另写测试脚本，仍从正式的 `scripts/run_agent_batch.sh` 入口运行。

| 文件 | 用途 |
| --- | --- |
| `$JOBS/$B-lane-<id>-diagnostics.jsonl` | 区分 job、Harbor、mirror 和清理阶段；记录超时、耗时、退出码及异常栈帧 |
| 每个 trial 的 `agent/openrouter-requests.jsonl` | 将请求、HTTP 状态、generation ID、usage、断流方向关联起来 |
| 每个 trial 的 `agent/muse-run-status.json` | 分开记录原生 Muse 执行状态、包装层判定和 token 计量状态 |
| 每个 trial 的原生 agent、模拟器和 verifier 日志 | 核对原生失败、真实物理/渲染错误及评分结果 |
| `$JOBS/$B.summary.md` 和逐 job 检查结果 | 查看计划数量、实际结果、失败分类和是否完整 |

新增诊断避免记录 key、请求正文、完整模型输出和原始环境变量；仍需按手册执行两次密钥扫描后再打包上传。模型连通检查另有私有诊断目录，不能把整个私有凭据目录直接当作结果包上传。

对于旧 smoke，`JOBS` 曾实际指向 `/mnt/c/Work/topogym/jobs/agents`，在仓库目录外。查旧日志时须使用它当时的真实路径，不能默认改成 `$REPO/jobs/agents`；之前的 `tail: No such file` 就需要先区分路径错误与任务未启动。

## 6. 如何解读旧批次的状态

| 输出 | 实际含义 |
| --- | --- |
| `lane ... finished rc=0` | lane 进程退出成功；旧版不能据此证明 trial 没有异常 |
| `observed: 144` | 发现了 144 次 trial 记录，不表示取得了 144 个有效成绩 |
| `infra_failed` | 执行基础设施或适配层异常，不能当作模型正常尝试后未解出 |
| `Sealed; evaluation_complete=False; delivery_complete=False` | 恢复封存完成，但实验/交付仍不完整；不是恢复命令再次失败 |
| HF `remote_verified=true` | 上传文件与校验记录核对通过；不表示包内实验完整或解题成功 |
| 模型 canary passed | 小型模型连通检查通过；不覆盖完整 trial、评分容器和结果交付 |

同一次尝试可能同时出现 agent 请求异常、评分侧 Buildx 错误和收尾超时。需要分别定位，不能任选其中一项解释全部错误。

## 7. 已完成验证与剩余验证

本次诊断发布的[本地验证报告](../../runs/test_results/helper_diagnostics_20261006/summary.json)记录：

- 76 项回归中 74 项通过，2 项原生 Muse 二进制测试跳过，无失败。
- 测试使用合成凭据和本地模拟 provider，真实模型调用为 0；最终 8 项诊断专项复查也通过。
- release 校验、变更文件密钥扫描和 README Bash 语法检查通过，远端 commit/tag 已核对。
- 未新增真实物理/渲染验收，未完成 helper 端新版全流程实跑，未证明全部 144 个 trial 可完成。

下一步按手册使用新的小测试任务单：

```text
topogym-claws-muse-jianwen-smoke-20261006-diagnostics01
```

先确认同一运行账户的 Python/venv、Docker、Compose v2、Buildx 和 Docker GPU 支持，再跑 Claws easy 的 6 个 trial。新版入口会自动记录上述日志；发生错误后，根据日志定位具体阶段，保留旧批次和原始 assignment。

这轮小测试需要分别确认：模型请求与计量、任务运行、正式评分、收尾封存、密钥扫描、HF 上传和独立下载验收。小测试全部通过后，可以证明这套配置下的完整链路已经跑通；仍不能替其他任务、更高难度或长时间运行作成功保证。

对于确认为需要修改的判定或运行逻辑，修复后应发布新的 runner/assignment，再验证受影响路径。不能通过删除失败记录、覆盖已封存任务单或把 agent 的完成描述改记为正式成功来关闭问题。
