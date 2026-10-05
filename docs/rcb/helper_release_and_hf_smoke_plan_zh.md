# Helper 独立 release、HF 交付与小测试计划

2026-10-04。根据用户转述的最新上游安排制定。本页是下一阶段开发计划，**不表示已发布 helper 仓库、已使用真实凭据测试 HF，或已启动模型实验**。现有功能和历史验证见 [native helper 操作说明](standard_helper_operations_zh.md)；更早的修复背景见 [标准流程工程计划](standard_helper_pipeline_engineering_plan_zh.md)。

实施更新：已增加 native release 导出/验证、仅 HF 权限检查、私有凭据隐藏输入、helper 配置生成、独立 HF 下载/验收与上传重试。最新用户要求小测试直接走正规流程，因此下文 B 的“合成包真实上传”方案不执行；只做权限检查，真实数据由正式 Coil easy 双模式 K=1 产生。执行步骤及当前阻塞见 [正式入口 CLI](helper_native_cli_zh.md)。已有回归夹具只验证代码，不上传为实验结果。官方手册原文尚未取得，独立完整 release 仍需它；工具导出已实测，正式 prepare 被现有 GPU 显存门槛拦住。

## 1. 新信息确定了什么

| 项目 | 本轮采用的约定 |
|---|---|
| 静态手册 | 上游 `docs/SHARING_RUNS.md`；据上游说明，`dev/jianwen` 中的同文副本为 `docs/rcb/SHARING_RUNS.md`。取得原文后随 helper release 分发，TopoGym 命令补入 §3b |
| 每批任务单 | 维护方单独提供 release commit、assignment、任务、batch、镜像和交付目标；机器读取的 assignment 不含凭据。凭据通过私下渠道交付 |
| 代码来源 | `robot_coding_bench` 是私有仓库，不能要求第三方 helper 克隆它；另提供 helper 有权访问的固定 release |
| HF 接收库 | 上游已确认建好私有 dataset `eai-v2-internal/helper-uploads`，并实测过上传、下载；我们尚未用现有工具对其认证实测 |
| HF 路径 | `helpers/<helper>/<batch>/`，helper ID 小写，batch 由派活者指定 |
| 权限 | 每个 helper 一个限定该库的 fine-grained 写 token，交付后吊销；接收方使用自己的有读权限账号 |
| 网站 | 私有原始结果先验收，网站发布是接收方后续独立流程；原始归档不直接上传公开的 `agent-runs` |

用户已经单独提供小测试凭据。本文和代码中不记录其值、截图、前后缀或指纹；本轮不使用它发请求。后续由测试进程从仓库外的私有文件读取，文件权限 0600，不放入 shell 命令参数、环境示例、assignment、MANIFEST 或交付包。截图称该凭据拟供 Reuben 使用；这不自动确定正式 helper ID、batch 或实际测试目录。

这里的 release 指**我们提前冻结并交付的源码、任务树及运行依赖清单**，不是让 helper 从开发中的源码重新生成实例。镜像另行交付，引用和内容身份也必须锁定。

## 2. 实验范围保持不变

正式实验沿用 [helper_oracle_reference.yaml](../../configs/sweeps/helper_oracle_reference.yaml)：

- 排除 `knot_untying`、`slotted_post_ring`、`orbits`，剩余 10 个任务。
- 每个任务 easy / medium / hard，各档使用 oracle 参考实例的 named variation 和 seed 0；还需核对配置、资产和冻结状态，不能仅凭 seed 相同认定同实例。
- privileged / standard 双模式，即 unlimited / limited；同一实例每模式重复 `K=3`。
- 合计 **30 个实例、60 个任务包、60 个 jobs、180 个 trials**。
- 模型 `openai/gpt-6-sol`，effort `xhigh`，由维护方 assignment 指定。上游 batch 示例里的 Luna 不改变此选择。
- 每 trial：agent 12 小时，input 150M、output 10M。token 阈值沿用当前运行后判分规则，**不是实时消耗截止开关**；缺用量不能通过完整验收。

正式包和原始 assignment 应由我们留存。当前 active v15 仍是 source candidate，没有完成本次 60 包发布；历史根目录 `tasks/` 和旧 oracle 成功记录不代表新实验已经合格。

## 3. 当前代码具备什么，还缺什么

| 环节 | 已有支持 | 本阶段缺口 |
|---|---|---|
| 统一 helper 入口 | [run_helper_batch.sh](../../bash_scripts/run_helper_batch.sh) → [helper_batch.py](../../scripts/helper_batch.py)，调 native runner、认证、镜像检查、运行、封包、HF 上传 | 尚未在只持有 helper release 的干净环境中跑通 |
| 原生批量执行 | [run_agent_batch.sh](../../scripts/run_agent_batch.sh)，assignment、K、双模式、lane 认领、mirror、严格 verdict | 真实任务、真实模型与全部预算记录仍待小样 |
| 任务发布 | [publish_agent_batch.py](../../scripts/publish_agent_batch.py) 将预检后的包发布到标准 `tasks/` 和派单 | 不是独立 helper 仓库导出器；新 v15 包尚待准备和预检 |
| 源码导出 | [difficulty_release.py](../../scripts/difficulty_release.py) 有旧 difficulty source bundle | 未包含 native 冻结任务树和新手册；整目录收集 `topogym/`、`scripts/` 等，不能直接视为审查过的 helper 分发清单 |
| 官方手册 | 上游已告知具体路径 | 本机文件和已缓存分支尚无该文件；更新分支遭遇 SSH 公钥认证失败，需要取得最新原文 |
| HF 交付 | 固定三文件上传、目标私有性、权限和远端哈希检查；重复同内容可跳过上传 | 当前证据使用测试替身；缺独立的“只查访问权限”入口和真实传输测试 |
| 接收验收 | [agent_batch_delivery.py](../../scripts/agent_batch_delivery.py) 安全解包、核对我们留存的 assignment、逐 trial 检查和报告 | 缺从固定 HF revision 下载三文件并接续验收的统一入口 |
| 网站 | 离线结果布局和接收报告可保留 | 尚无网站仓库、导入接口和发布配置；继续独立暂缓 |

有一个容易漏掉的依赖：native runner 调用 `topogym_versions.require_task()`，它不仅检查包，还根据源码、工具、镜像配方计算身份，并导入 `topogym.planning.harbor_bridge.binding` 等模块。只复制几个脚本会缺模块；把整个开发树复制过去又会夹带不需要分发的内容。必须核对运行时实际依赖和哈希计算范围。

现有 CPU 合同与真实 Docker mirror 测试验证过多 lane、K=3、归档和离线接收，但模型、物理和 HF 用了替身。它们不等于真实 helper 主机验收。详细证据路径保留在操作说明第 10 节。

## 4. 开发工作与交付物

### P0：取得官方手册，固定发布输入

1. 从可访问的最新上游 commit 取得 `SHARING_RUNS.md`，核对上游两份副本的内容和来源 commit。当前 fetch 的具体问题是 `Permission denied (publickey)`；不能据本地旧引用断言远端不存在文件。
2. 保留原扫描、原样归档和上传约定，仅补 §3b 的 TopoGym 入口及其前置条件；将修改回馈到官方手册，避免长期维护两套互相矛盾的 helper 指令。
3. 每批变化放任务单，静态手册只放变量、配置项解释及固定命令。模型凭据和 HF 凭据分别交付，不写入机器 assignment。
4. 从正在变化的工作区挑选明确源码快照，记录真实文件哈希。现有未提交 Task/oracle 改动属于其他开发内容，不通过整目录复制或一次全量提交混入发布。

交付物：有来源记录的手册、§3b 补丁、任务单模板、发布输入清单。没有原文时可以推进其他代码开发，但不能声称手册已逐字对齐。

### P1：制作可独立使用的 native helper release

拟新增 `scripts/export_native_helper_release.py`；这是计划中的入口，当前尚不存在。

导出内容采用明确清单：

- native runner、统一 helper 入口、固定安装器、认证/扫描/交付模块，以及它们实际导入的共享模块。
- `require_task` 所需公共源码、版本文件、模板、镜像配方和依赖锁；逐项核对完整依赖，避免依赖本机原 checkout。
- 本 release 选定的冻结 `tasks/<base>-<mode>/`、对应 dataset/catalog、发布清单；任务包保持原始字节和 binding。
- 官方手册、§3b、配置模板、必要的许可证和来源说明。

导出不携带原私有仓库的 `.git` 历史、个人认证、开发日志、结果目录或额外 oracle 开发/解题代码。冻结任务包内合同必需的文件和镜像内容另行审查，不能导出后随意删文件造成身份失配。若通用校验代码与 oracle 模块耦合，先提取共享校验模块，再重新生成相应工具身份和派单；不降低校验强度。

在独立暂存目录制作候选 release，记录上游源码 commit、真实源码哈希、任务/工具清单及 image Id/digest。helper 仓库自己的 commit 在发布完成后写入外部任务单，避免让清单包含自身 commit 的循环依赖。运行时记录 helper checkout 的 commit，维护方通过 release 清单追溯原源码。

镜像需要独立的分发安排：可访问 registry，或 `docker save/load` 文件加 checksum。覆盖 assignment 列出的全部角色，不能只提供准备机上的本地 tag。镜像不放进 HF 的结果三文件目录。若更换镜像引用会改变包内容，应在冻结发布前完成，不能发给 helper 后手改包。

交付物：可审查的 helper release 目录、文件哈希清单、镜像交付清单。随后在约定 helper 仓库发布固定 commit；helper 的克隆权限也属于验收项目。

### P2：补齐 helper 端独立运行与 HF 小测试入口

沿用 `bash_scripts/run_helper_batch.sh`，不重写调度器。重点补以下缺口：

1. 干净环境安装：Python/Node/Docker/GPU 的检查可读、固定版本依赖可安装；运行路径不引用维护方 home 或原私有仓库。私有模型网关或私有镜像若实际需要，必须列为显式配置。
2. 为 `check_agent_batch_hf.py` 增加只查目标与访问权限的模式。当前 CLI 必须有本地交付文件，统一入口的 prepare 又包含镜像/模型检查；应允许不启动 GPU、不访问模型就先验证 HF。
3. 凭据仅在主机私有文件中使用，日志错误脱敏；仓库导出、普通结果、mirror 历史和最终三文件都经过扫描。用合成秘密测试泄漏路径，不把真实 token 放进测试夹具。
4. 实测三文件提交、失败重试与同内容幂等；同路径不同内容应拒绝。上传中断后只重试交付，不重跑 trial。
5. MANIFEST 分别记录真实实验、合成传输测试、主机/镜像和异常，不能把合成 fixture 当实验结果。

库级写 token 并非只能写一个 helper 子目录；本工具按 assignment 限制路径。本阶段只访问分配的 smoke 目录，不遍历、覆盖或清理其他 helper 的数据。

### P3：实现独立接收入口

拟新增 `bash_scripts/import_helper_results.sh` 和对应 Python 编排，复用已有安全解包与 verdict 检查；它们当前尚不存在。此入口属于我们，不加入 helper 的执行步骤。

输入：我们保存的原始 assignment、HF repo/prefix、接收目录、接收方只读凭据来源。流程：

1. 将远端 revision 固定为一个 commit，再按该 revision 下载指定 archive、`.sha256`、`MANIFEST.md`，不下载整个 dataset。
2. 下载到临时目录，完成后核对长度、checksum 和三文件对应关系；失败保留诊断，不把半份下载当完成包。
3. 调用 `agent_batch_delivery.py import`，以维护方原始 assignment 检查计划、任务身份、K、verdict、token 用量、mirror 和 inventory；不信任归档自己声明的“完整”。
4. 输出包含 HF revision、文件哈希、批次身份、完整性和逐 trial 结果的接收回执与审查报告。失败任务可以是已完成的有效结果；缺 trial、缺用量、基础设施中断不能伪装成完整。
5. 接收机只需接收工具及其依赖；普通离线验收不要求 GPU、Harbor、模型账号或原私有开发 checkout。将来要物理重评分时，另提供匹配任务和镜像。

首次传输小测试可验证所供测试凭据实际具备的读取能力；正式接收必须另测我们自己的账号读权限，不能将“helper 的写 token 能读”当作接收账号已经就绪。

## 5. 小测试顺序与验收标准

先做不消耗模型额度的测试，再启动极小真实实验。所有测试使用单独 batch，并记录它们的性质，不混入正式 180 trials。

| 阶段 | 范围 | 必须证明什么 |
|---|---|---|
| A：离线与干净环境 | 本地独立 release；合成双模式 K=3 六份结果；新环境安装和导入 | 不借用原 checkout/PYTHONPATH/凭据缓存；依赖齐全、严格身份检查通过；K 缺失能拦住，重复启动不多跑 |
| B：真实 HF 传输 | 独立 smoke batch，标准三文件的小型合成包，目标总量不超过 5 MiB；无 GPU/模型 | 实际认证、private 状态、指定目录上传、固定 revision 下载、逐文件哈希及离线导入全部通过 |
| C：真实 rollout | Cast Coil easy、oracle seed 0、双模式、K=1，共两个真实 agent trials | 真 GPU、真 Harbor、真模型、真实用量与 verifier、mirror、封包、HF 上传及接收均可衔接 |
| D：异机验收与正式放行 | 在另一台机器接收 C 的包；随后验证正式全部任务包 | 异机接收不借用 helper 磁盘；正式 30 实例/60 包逐包准备和预检合格，才发 180-trial assignment |

### A：隔离条件不能省略

先用独立目录检查，再在干净容器或另一台机器安装。不要挂载原开发树、`.venv`、`.tools` 或个人 auth 来掩盖缺依赖。镜像只通过 release 声明的渠道取得。检验 `require_task`、dispatch 工具哈希和实际镜像，不能只验证 `--help` 能打印。

已有六份合成结果的多 lane 测试可以复用，但应在导出后的代码上再执行。若正式实验要并发运行订阅 lane，需独立的认证缓存；共用同一缓存当前会串行。单个 GPU 的能力也不能据此推定能同时承载多个真实 trial。

### B：先单独把 HF 传输跑通

派活者确定实际小写 helper ID 与包含 `transport-smoke` 的 batch。路径严格为 `helpers/<helper>/<batch>/`，不借用正式结果目录。小包使用标准目录结构和完整性合同，但 MANIFEST 明确标为 synthetic / transport-only。

第一次上传成功后，再上传完全相同的三文件，确认不覆盖、不产生重复提交；改变文件内容的冲突测试使用替身或独立测试目录，不能破坏已留存的小样。用另一个空目录从固定 HF commit 下载，再导入并比较本地、远端、接收端哈希。输出报告仅含非敏感身份、revision、大小、哈希与结论。

网络中断、缺文件、错 checksum、错 assignment 等故障先用离线夹具覆盖。真实 HF 小样只做必要的成功和幂等验证，避免为测试大量制造远端垃圾。测试产物保留为证据，不自动删除远端目录。

### C：真实 rollout 只先跑两个

先针对具体冻结包执行 GPU prepare/preflight 和真实 Harbor nop 检查，再执行模型可用性 canary，最后跑两个 agent trials。nop 只证明基础设施/评分可执行，不能证明模型会解题。

默认沿用正式任务包的 12 小时上限、150M/10M 预算，仅将 smoke assignment 的 K 改为 1，因此通过的包可以原样复用。**两个 trial 并不保证几分钟内结束。** 若另需短时诊断，应制作明确标识的独立 smoke 包与较短超时；它不能直接作为正式预算包的验收证据，也不能偷偷修改本次正式预算。

HF token 只负责结果交付，不提供模型访问权限。这个阶段仍需要能够调用 Sol 的订阅认证或 API 凭据，以及可用 GPU/镜像。失败得分不阻止流程验收；缺真实终态、缺用量或基础设施错误必须如实报告。基础设施失败原目录保留，rerun 只通过授权的新派单进行。

### D：正式实验的放行条件

Coil 两个 trial 的通过只验证工程流程，不代表其他九类任务、其他难度或新 v15 物理环境已验证。正式派单前，需对全部目标实例完成准备、冻结、预检，并核对 oracle 参考配置与证据。最终维护方保存 release commit、镜像清单、全部包哈希和原始 assignment，再让 helper 开始 180 次运行。

真实测试的证据放 `runs/test_results/<test-id>/`：非敏感配置、release/镜像身份、阶段结果、HF 回执、接收报告、真实物理执行的录像路径和资源监控。CPU 仅监控；主机内存达到 90% 时停止本轮拥有的相关工作，不终止其他会话进程。

## 6. Helper 最终看到的稳定命令

以下是**取得并发布独立 release 后**拟放入官方 §3b 的命令骨架；不是说当前就已有可克隆的发布仓库。

```bash
# HELPER_REPO 和 RELEASE_COMMIT 来自每批任务单。
git clone "$HELPER_REPO" helper-release
cd helper-release
git checkout "$RELEASE_COMMIT"

cp configs/helpers/native_helper.example.json "$HOME/helper.local.json"
chmod 600 "$HOME/helper.local.json"
# 一次填写 assignment、本机 jobs 路径、GPU、模型认证和 HF token 文件路径。
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json"
```

首次安装/登录在前台进行，通过后脚本转后台。状态检查和只重试上传沿用已有命令：

```bash
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json" --phase status
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json" --phase upload
```

模型、种子、模式、K 和预算不由 helper 重新填写。`assignment` 可以指向任务单单独提供的本机文件；手册不需要随 batch 改写。helper 仍负责提供宿主 GPU/Docker、完成自己的模型认证、保存私有凭据和说明异常。

统一脚本执行官方步骤对应的运行、扫描、封包、校验、MANIFEST 和上传；命令拼写与旧手工流程不完全相同。等取得官方手册后逐条核对，并把自动入口放入 §3b，保留手工诊断方式，不能先宣称“原文每条命令已经原样实测”。

## 7. 还需要落实的信息

| 信息 | 谁提供 | 影响 |
|---|---|---|
| 最新 `SHARING_RUNS.md` 原文及来源 commit，或可用的上游读取方式 | 上游维护方/我们 | 官方文档同步；当前 SSH 无法 fetch |
| helper release 仓库地址、归属、可见性和第三方访问方式 | 我们与上游确认 | 固定 commit 实际可取得；不能默认允许公开整个私有源码树 |
| 镜像分发位置或可传输文件 | 我们 | helper 干净机器能获得所有绑定镜像 |
| 我们用于接收的 HF 用户名及组织读权限 | 我们提供用户名，上游邀请 | 验证独立接收；库名和上传目录规则已确定，不再待定 |
| 此次 smoke 的 helper ID 和 batch | 派活者 | 生成准确 assignment 与上传路径；不自动采用示例名字 |
| 真实 smoke 的 GPU 与 Sol 模型认证 | 测试机器提供 | HF 传输测试不依赖它们，两个真实 trial 依赖 |

网站信息继续暂缓，不阻塞 A/B/C 和离线接收。以后需要网站仓库/commit、benchmark 名、实际 importer/schema、审核后哪些数据可公开、公开数据写入权限及发布入口。到时在接收流程后增加网站导入，不把网站账号或发布操作加给 helper。

建议执行顺序：**P0/P1 准备可分发 release，同时补 P2 的独立 HF 检查 → P3 下载验收 → A/B 无模型小测试 → C 两个真实 trial → D 异机和全量放行**。真实小样完成后再报告通过/失败证据与剩余问题，不用旧替身测试替代它们。
