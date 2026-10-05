# TopoGym helper 执行与结果交付工程计划

2026-10-04 方向更新：用户要求对齐原 helper 说明的 `run_agent_batch.sh`、`jobs/agents` 与标准 tar/网站流程。后续实施以[标准 helper 流程核对与修复计划](standard_helper_pipeline_engineering_plan_zh.md)为准。本文保留上一版 difficulty/helper-bundle 设计和已实现记录，不能据此认为标准命令已全部接通。

2026-10-04。状态：仓库内 W1–W6 的单队列能力已实现，W7 的 CPU 合同测试和中英文操作手册已补齐；W0 实际评测网站探针、W7 独立 GPU 主机交付演练及真实目标 HF 上传尚未验收。本轮没有启动真实模型评测或向外部上传结果。操作见 [Helper 手册](helper_quickstart_zh.md)、[异机验收手册](helper_import_zh.md)。下文保留原设计与正式放行门槛。

> 2026-10-04 对齐：helper 手册只保留一份，即本目录的 [`SHARING_RUNS.md`](SHARING_RUNS.md)（英文，所有基准共用；与 robot_coding_bench `dev/qineng` 的 `docs/SHARING_RUNS.md` 逐字相同，两处一起改）。本计划的派单、结果包和导入实现后，W7 把已验收的命令写入该手册（§3b），不再新增 `helper_quickstart_zh.md` / `helper_import_zh.md`。

目标：维护方提供固定任务单和发行版本，helper 在自己的 GPU 主机上执行，交回经过脱敏和校验的完整记录包；维护方在不同机器、不同目录下，仅凭交付包和对应的读取工具即可重建汇总与审查材料。helper 不需要访问评测网站或维护方机器。

推荐继续使用 `bash_scripts/run_difficulty_trials.sh` 作为唯一评测入口，复用现有 Docker、认证、预检、执行和恢复能力。首版完成单 lane 的全流程，随后增加多 lane。原始 job 名称和内部目录保持原样，新增版本化交付格式及接收端适配。现有 HF 指标导出继续使用自己的格式。

## 1 当前基线和已确认缺口

审查对象是 `dev/jianwen` 当前工作区，HEAD 为 `4aac2a4e6ab7cc6c4b04ed92c1d1e0cda838938b`，包含其他工作尚未提交的改动。该 HEAD 不能单独代表工作区全部字节；正式派单前需要另行冻结交付版本和源码清单。

| 环节 | 当前支持 | 本计划补充 |
| --- | --- | --- |
| 新机器启动 | Docker 自动构建、环境检查、GPU 选择、订阅/API 认证 | 固定发行身份，helper 专用流程及冷机器验收 |
| 任务确定 | 本地抽样、源码快照、manifest、恢复一致性校验 | 维护方冻结具体实例和 trial，helper 首次启动也验证任务单 |
| 执行与恢复 | 单 lane、双模式、canary、失败分类、旧 attempt 保留 | 按派单列表执行，显式重跑清单，交付时保留全部状态 |
| 记录保全 | 原始 Harbor jobs、任务包、逐项日志和汇总 | difficulty runner 接入独立 agent 日志备份 |
| 脱敏 | job 完成后的已知凭据替换、HF 白名单字段清洗 | 实际交付集合复扫；残留密钥、不可读文件均阻断封包 |
| 结果导出 | HF 指标、评分、轨迹和录像白名单 | 完整 job、生成任务、身份文件和诊断日志的结果包 |
| 异机导入 | 本地报告依赖 Harbor 记录的原绝对任务路径 | 包内相对路径索引、内容校验、网站 importer 适配 |
| 交付信息 | 源码、实验参数、部分镜像身份 | helper、主机、软件、时间、异常、文件清单与压缩包校验 |

审查已复现：`scan_secrets.py` 检出密钥仍返回 0，文件不可读时静默跳过；默认只选择 `OPENROUTER_API_KEY`。difficulty runner 显式选择两种 API key，但仍继承前两个问题。另将合成 job 搬到不同路径后，`write_task_results.py` 因原任务目录不存在而失败。

现有三组 CPU 合同测试共 61 项，最终 60 项通过；HF socket 测试解除沙箱限制后单项通过，剩余一项是旧测试夹具未提供 `gripper_space`。这不构成真实物理、模型、HF 实网上传或异机网站导入的验收。

参考实现：[调度器](../../scripts/difficulty_eval.py)、[抽样与冻结](../../scripts/sample_difficulty_instances.py)、[收集器](../../scripts/collect_batch_results.py)、[HF 导出](../../scripts/difficulty_results_hf.py)、[扫描器](../../scripts/scan_secrets.py)、[本地报告](../../scripts/write_task_results.py)。已有工程说明：[Docker 交付](difficulty_sweep_delivery_plan_zh.md)、[HF 上传](difficulty_results_hf_plan_zh.md)。

## 2 首版边界和兼容决策

首版交付称为 `helper-bundle-v1`。维护方任务单直接冻结现有 difficulty 实例生成器能够支持的实例参数与 trial 列表；helper 不重新抽样、不替换 seed、不自行改变任务、模式、预算、模型或 effort。任务包仍由受固定版本约束的 prepare 阶段生成，随后冻结实际文件哈希。

每个 trial 明确列出实例和模式，允许派发某些任务、难度或模式的子集。首版不增加新的任务家族、开发中的难度档位或任意外部任务包执行协议。若要求直接运行参考仓库的一组预生成 task-base，须增加经过验收的任务包输入适配，不能将 task-base 字符串传给当前 `--tasks` 后声称等价。

| 决策 | 首版做法 |
| --- | --- |
| 运行入口 | 扩展 `run_difficulty_trials.sh`，实验状态机保留在 Python |
| 并发 | 每个 batch 一个 lane、一张指定 GPU；重复命令拒绝重复持有 |
| batch 与 run ID | helper 模式下 `run-id = batch`；模型身份单独存储，不把二者混用 |
| 原始结果布局 | 保留 `jobs/difficulty_trials/<batch>/` 和原 job 名称 |
| 重跑 | 同 batch 增加 attempt，记录前序 attempt 与维护方重跑指令；保留全部旧记录 |
| 文件变换 | job 内只允许有记录的凭据脱敏；不改名、扁平化、重编码或裁剪记录 |
| 指标 HF 上传 | 原有 `--results_to_hf` 语义保持；完整包使用独立导出和上传命令 |
| 镜像获取 | 支持固定配方本地构建；已发布镜像可用 digest。公开镜像发布不是首版前置条件 |
| 历史数据 | 旧 run、任务包和 manifest 不原地迁移；通过版本化读取器兼容 |

原 helper 文档的 `agents/<batch>-*`、`<batch>-rerun` 和“再次运行命令增加 lane”不适用于此首版。必须同时提供更新后的 helper 手册和接收端适配，才可以发给 helper 使用。若网站端强制保留旧格式且无法扩展，W0 阶段应改为让新 helper job 从创建时就采用旧约定；不得在导出时重命名历史 job 来伪装兼容。

## 3 任务单和运行身份

新增版本化任务单 `assignment.json`，由维护方在冻结的发行版本上生成，再通过约定渠道发给 helper。任务单不包含任何密钥。摘要用于完整性和一致性校验；接收端还要与维护方保存的原任务单比对，不能将 helper 自行重算的摘要当成派单授权。

| 字段组 | 必须记录的内容 |
| --- | --- |
| 派单身份 | schema、batch、helper ID、创建时间、任务单摘要 |
| 版本 | 仓库、branch、commit、完整源码清单摘要、tooling/release 身份、CUDA 配方、依赖和镜像约束 |
| 实例 | 稳定 instance ID、任务类别、难度、seed、解析后的参数和资源引用、实例定义摘要 |
| Trial | 稳定 trial ID、instance ID、mode、agent/sim/verifier/collection 预算 |
| Agent | agent、model、reasoning effort、CLI version、允许的认证方式和 canary 预算 |
| 执行策略 | 单 lane、GPU 选择规则、失败停止规则、重跑策略、mirror 必需或可选 |
| 交付目的地 | 私有 HF dataset 和目录前缀，或共享文件夹标识；不放 token 或带凭据的 URL |

helper 可以指定工作目录、GPU、凭据来源和允许范围内的资源等待参数。与任务单冲突的实验参数在模型 canary 前拒绝；不静默采用命令行覆盖值。镜像准备和 CPU 校验可先执行，但派单身份不通过时不得启动模型。

计划实例直接来自任务单，不能重新调用随机抽样推导替代列表。prepare 记录实际生成包、初态资源、镜像和运行绑定的哈希。GPU UUID、宿主路径等部署信息单独记录；不能为了“可迁移”任意删除 runtime binding 中参与身份验证的字段。硬件相关初态继续遵守现有生成和预检合同，不能仅凭同 seed 声称跨硬件字节相同。

维护方的重跑清单引用原 assignment 摘要，列出获准重跑的 trial 和原因。`--resume` 只继续未启动项；helper 模式下，仅有 `--rerun-incomplete` 不能绕过重跑清单。新的 attempt 不复用旧 limited episode，不覆盖旧 verdict。

## 4 结果包合同

单次交付目录仍为三个文件，便于 helper 手工上传到共享文件夹。文件名加入 bundle ID，允许同一 batch 先交部分结果、之后补交，且不覆盖前一次证据。

```text
upload_<batch>/
  <batch>__<helper>__<bundle-id>.tar.gz
  <batch>__<helper>__<bundle-id>.tar.gz.sha256
  MANIFEST.md
```

压缩包内部按原工作目录的相对路径保存。下面是拟定布局，属于待实现合同：

```text
BUNDLE.json
inventory.json
delivery/
  assignment.json
  helper_manifest.json
  scan-report.json
  redaction-report.json
  path-map.json
  retry-plans/                         # 若有获准重跑
runs/difficulty_trials/<batch>/
  manifest.lock.json
  source_identity.json
  execution.lock.json
  controller.json / image.json / cuda-profile.json
  tasks/                              # 实际执行所用的冻结任务包
  instances/                          # 该批实例身份及所需资源
  build/                              # 与身份、预检和故障定位有关的明确文件集合
  trials.jsonl / summary.csv / summary.md
  <该批逐 job 与 canary 日志>
jobs/difficulty_trials/<batch>/
  <原 job 名>/<原 Harbor trial 目录>/...
jobs/difficulty_trials_mirror/<batch>/ # 若存在独立记录备份
```

`BUNDLE.json` 记录格式版本、assignment 身份、batch/helper、导出工具身份、封包时间、完整性状态和 inventory 摘要。`inventory.json` 列出有效负载文件的相对路径、大小、类型和 SHA256，明确排除自身等控制文件，避免递归哈希。最外层 `.sha256` 校验压缩包最终字节；导入时同时校验包内文件。

job 目录保留所有成功、失败、中断、canary 和重跑记录，包括 `agent/`、`artifacts/`、Harbor `config.json/result.json`、verifier 输出、提交代码及其他已收集文件。生成任务和配套资源通过显式清单加入，不能笼统把整个 work-dir 打包。若只保存了失败日志且从未生成完整任务包，交付中如实标注缺失，仍允许回收故障证据。

不包含完整源码快照、构建缓存、Docker 镜像、其他 batch、HF staging 副本和宿主凭据目录。任务中确实用到的非受限实例资源按清单带回；受限数据集不进入结果包。构建和 controller 日志从实际执行引用中选取，不用通配符带上其他批次。原文“只上传 jobs”需在新手册中明确扩展为“该批 jobs 与列出的任务及身份附件”。

封包先获取运行锁、核对本批仍存活的工作容器和写入者、完成 mirror 最终同步，再复制到独立 staging。复制前后检查源文件身份；若仍在变化则停止封包，不产生可上传标记。封包过程中断只留下临时产物；校验通过后原子发布成品。同一内容重试复用已封存包，不能覆盖已经交付的包。

## 5 脱敏和证据保全

复用现有扫描逻辑，抽出可供 CLI 和封包器共用的扫描核心，统一 exit code 和结构化报告。只更改 helper 封包器而保留旧扫描器错误语义，会让人工流程继续误判，必须同时修正现有调用方。

1. 显式读取实际使用的 API key、订阅 token 及保留的刷新前 token；兼容 `--var` 额外凭据。没有加载到所需凭据、目标不存在、扫描范围为空或文件不可读，均不能报告扫描通过。
2. 检出残留密钥返回非零；执行脱敏后必须重新扫描。报告只包含规则、相对路径、计数和覆盖范围，不包含密钥值。疑似含凭据的路径也不得原样写进报告。
3. 先对 staging 执行脱敏，保留文件名和结构，并记录原始/导出文件哈希与脱敏规则。原始 job 的运行期脱敏继续保留；mirror 的原始追加记录不就地改写。
4. 不再把跳过二进制后得到的结果称为全部文件已扫描。已知凭据匹配采用有界内存流式扫描；支持的压缩文本和结构化元数据按类型检查，NPZ 不启用 pickle。报告列出范围和限制；包含无法安全处理的可疑凭据载体时阻断交付。
5. 凭据专用文件、指向凭据或其他 batch 的链接不能悄悄忽略后声称原始记录完整。拒绝不支持的文件类型和越界引用，给出可定位原因。
6. 账号 ID/邮箱采用任务单明确的交付策略。私有接收与后续公开发布分开处理；helper 可以要求在私有交付前也清除这类字段。

mirror 复用 `scripts/log_mirror.py` 的增量备份和改写记录能力，增加 workspace/batch/owner 归属，避免全局固定容器名。启动模型前确认可用，作业结束后最终同步；默认按任务单要求收集。不可读时由可信的受限读取过程复制到导出 staging，不给 agent 额外权限。任务单允许缺失 mirror 时才可降级，清单记录原因和证据缺口。

凭据检测结果只证明所声明规则和覆盖范围内的扫描通过，不承诺能够识别任意未知秘密。已封存包的上传无需再次提供模型凭据或登录模型服务。

## 6 接收端和完成状态

`path-map.json` 将 trial ID、job 相对路径、任务包相对路径及内容哈希关联起来。原 Harbor JSON 中的宿主绝对路径保留为原始记录；新增读取层优先通过包内映射定位，并验证 task/release/runtime binding 身份，不能按同名目录猜测或全局字符串替换。

导入到接收端独立目录，先验证压缩包摘要、允许的归档路径、重复条目、文件类型、大小边界和包内哈希，再原子登记。拒绝目录穿越、越界链接和会覆盖既有包的归档；导入不执行包内 agent 代码或 shell 脚本。重复导入同 bundle ID 幂等，同 batch 的后续包按明确 attempt 身份合并，冲突证据报错。

`write_task_results.py` 和报告读取器采用共用的任务定位接口。需要物理重评分的 `regrade_trials.py` 可以复用定位，但必须另行满足原镜像和运行绑定要求；完成离线导入不代表异机重评分已经可用。

评测网站 importer 所在仓库和扩展接口尚未核对，W0 必须取得其代码并完成最小导入探针。仓库本地可以先建设验包、读取和报告层；网站注册与页面重建必须在真正接收端验收，不能用本地 summary 成功代替。导入时无需 helper 的模型凭据、原绝对路径或 GPU。

| 状态 | 定义 |
| --- | --- |
| `evaluation_complete` | 每个计划 trial 的最新 attempt 达到现有收集器定义的完成状态；infra/pending 不能伪造成 verdict |
| `delivery_ready` | 原始记录及必要身份附件已冻结；缺失项和异常已列明，脱敏与封包校验通过 |
| `upload_complete` | 接收目标中的文件及摘要已核验，产生上传回执 |
| `import_complete` | 接收端验包、登记和材料重建成功，产生导入回执 |

允许 `evaluation_complete=false` 的部分交付，回收中断和失败证据；不得因此显示“实验全部完成”。收集器、MANIFEST、上传回执和网站都显示计划数、已尝试数、已完成数、infra/中断/未开始数及全部 attempts。成功率沿用当前定义，不能把未完成 trial 悄悄从计划数中消失。

## 7 工作包和实施顺序

以下文件名和接口是拟新增项，尚未实现。W0–W7 构成首版发布范围，W8 是后续扩展。

| 工作包 | 主要改动 | 依赖 | 验收标志 |
| --- | --- | --- | --- |
| W0 固定合同与接收端探针 | 本计划、assignment/bundle schema、网站 importer 接口核对 | 无 | 完成现有格式的小样探针，确认适配位置、字段要求和格式策略 |
| W1 维护方派单 | 新增 `helper_assignment.py`；修改 sampling、eval、collector 和 HF 读取器 | W0 | 实例和 trial 列表冻结；错误版本、参数、预算在模型启动前拒绝 |
| W2 运行记录和恢复 | eval、delivery、release 元数据、log_mirror | W1 | helper 主机信息、时间和异常可追踪；失败记录与旧 attempt 保留；mirror 正常或明确降级 |
| W3 严格扫描 | scan_secrets 及共用扫描核心；修复 run_agent_batch 等调用方 | W0 | 残留密钥、不可读文件、无扫描输入均可靠失败；脱敏后复扫通过 |
| W4 封包与离线验包 | 新增 `helper_bundle.py`、helper CLI；launcher 增加文件挂载和无 GPU 路由 | W1–W3 | 生成三个交付文件；无跨 batch 文件；源变化或损坏不能发布成品 |
| W5 异机导入 | 新增 `helper_import.py`、共用任务定位器；报告与网站 adapter | W0、W4 | 接收端删除对原路径的依赖，重建页面所需材料，重复导入幂等 |
| W6 上传和回执 | 新增完整包上传协调层，复用 HF auth 与传输模块 | W4 | 私有目标三文件交付、断点补传和远端校验；共享目录可手工交付 |
| W7 集成验收与手册 | CI、发行元数据、helper/接收方手册、版本发布记录 | W1–W6 | 独立 GPU 主机执行，另一机器导入；明确发布任务范围与剩余限制 |
| W8 多 lane | trial claims、GPU 调度、订阅认证并发、汇总与导出锁 | 首版稳定 | 多 lane 无重复领取，无跨 GPU 清理，死 owner 可恢复，封包不遗漏运行中 job |

推荐提交顺序：W0 → W1/W3 → W2 → W4 → W5/W6 → W7。这里表示依赖和提交边界，不要求启动并行 agent。优先完成扫描修复和异机导入最小探针，尽早暴露阻断交付的问题。

W1 必须收敛所有消费者对计划 trial 的读取。当前 `sampling.MODES`、`trial_count = 2 * instances`、collector 双模式循环、HF `load_results` 的 planned 集合均有固定展开逻辑；只修改 CLI 会导致漏跑、误判完成或拒绝上传。新增纯数据的共用 `planned_trials` 读取接口，旧 schema 通过只读适配得到等价的 78-trial 默认计划，新 schema 读取显式列表。

W2 将 helper 信息、CPU/RAM、GPU/driver/CUDA、Docker/Harbor/agent 版本、镜像 ID/digest、实际 lane/GPU、带时区的起止时间和异常事件写入机器可读 manifest，再生成 `MANIFEST.md`。容器中无法直接取得的宿主值由 launcher 采集后传入；未知值标为 unknown，不用控制容器的内核/软件信息冒充宿主信息。

W3 修改扫描 exit code 后检查现有 shell 管道是否吞掉失败；不能只增加 `sys.exit(1)`，却让 `tail | tee` 把错误变回成功。维持失败 job 的收集，不因扫描异常删除记录。

W4/W6 的 helper 子命令在现有 Docker launcher 上增加独立路由，不落入默认的 GPU、订阅认证、运行镜像构建或旧 release 执行验证分支。导出需要本批状态检查；已封存包的验包和上传只需要 CPU。发行包携带完整工具及 schema，不要求宿主安装项目 venv。

W6 复用 `difficulty_hf_auth.py` 和已有 HF 传输能力，不复用指标导出的筛选逻辑。目的地由 assignment 指定，上传目录包含 helper、batch、bundle ID。远端已有相同内容则跳过，冲突则停止；最终成功标记必须晚于文件校验。共享文件夹路径保留人工上传三个文件的方式，生成可复制的 batch、文件名和 SHA256 回执，不自动给别人发送消息。

W7 新增面向 helper 的 `docs/rcb/helper_quickstart_zh.md` 和面向接收方的 `docs/rcb/helper_import_zh.md`，分别给出完整命令、文件位置、失败处理和回执示例；同步更新原始英文 helper 说明。手册只能列出已实现且验收过的命令，不能继续保留首版不支持的旧目录、rerun batch 和多 lane 承诺。

## 8 拟提供的操作接口

下列命令仅描述目标使用体验，当前不可执行。具体参数在 W0 冻结；认证登录继续使用现有入口。

```bash
# 维护方在固定发行版本中生成任务单，明确实例选择及 agent 配置。
bash bash_scripts/run_difficulty_trials.sh helper assign \
  --spec /path/helper-spec.json --work-dir /data/dispatch

# helper 使用任务单执行；batch、实例、预算和模型从任务单读取。
bash bash_scripts/run_difficulty_trials.sh \
  --assignment /path/assignment.json --phase all \
  --work-dir /data/topogym-work --gpu-device 0 --auth subscription

# helper 可先交回部分结果；封包会明确标记完成情况。
bash bash_scripts/run_difficulty_trials.sh helper export \
  --run-id '<batch>' --work-dir /data/topogym-work

# 上传已经封存的结果包；不重新运行实验。
bash bash_scripts/run_difficulty_trials.sh helper upload \
  --archive /path/upload_batch/batch__helper__bundle.tar.gz \
  --hf-token-file /path/private-hf-token

# 接收方先验包，再按包内映射导入；不读取 helper 原路径。
bash bash_scripts/run_difficulty_trials.sh helper import \
  --archive /path/received/batch__helper__bundle.tar.gz \
  --work-dir /data/helper-imports
```

导出输出路径固定落在本工作目录的 outgoing 区域，launcher 显示绝对路径。扫描需要的额外凭据源可显式指定，不能将密钥值嵌入命令；凭据不进入成品。归档、任务单、重跑清单与 HF token 的宿主文件挂载分别处理，避免把完整目录暴露给 agent。

## 9 验收矩阵

| 场景 | 必须通过的检查 | 验收层级 |
| --- | --- | --- |
| 默认与子集派单 | 旧默认仍为 78 trials；新任务单任意受支持子集精确一致，单模式不被自动扩成双模式 | CPU |
| 首次执行参数冲突 | 改 model/effort、seed、预算、source/release、派单 helper 后，在模型启动前失败 | CPU 与假 Harbor |
| 中断和显式重跑 | SIGTERM、强杀残留、infra 无 verdict；旧 attempt 保留，只有指定项生成新 attempt | CPU 与 Docker 边界 |
| 原始记录完整 | agent 对话、提交代码、Harbor JSON、verifier、canary、失败目录均进入结果包 | 合成归档 |
| 扫描异常 | 已知密钥、轮换 token、不可读文件、缺凭据来源、空扫描、二进制/压缩覆盖和路径异常 | 合成文件 |
| 包损坏与并发 | 复制中源变化、归档截断、哈希不符、目录穿越、重复文件、越界链接、运行中导出 | 合成归档 |
| 异机恢复 | 改用户名和工作根目录，原路径不可访问；无需 GPU/模型凭据即可重建记录和汇总 | 两个隔离目录及接收机器 |
| 上传恢复 | 断网、权限拒绝、提交响应丢失、重复上传和远端冲突；不重跑模型、不误报成功 | 假 Hub 后再实网 |
| 页面导入 | 真实 importer 登记 batch/attempt，页面包含 agent 记录、提交、评分、录像与缺失说明 | 评测网站接收端 |
| 冷机器试跑 | 不复用开发 venv、原任务绝对路径或旧 run；完成预检、真实模型动作和双模式评分 | 独立 GPU 主机 |

新增测试按真正的边界验证，建议分别放入 `ci_checks/test-helper-assignment.py`、`test-helper-bundle.py`、`test-helper-import.py`、`test-scan-secrets.py`，并扩展现有 difficulty 工作流、delivery 和 HF 测试。修复旧测试夹具缺失 `gripper_space` 后恢复基线，不能把该修复记成 helper 物理成功证据。

首次真实演练至少选择已具备运行资格的一个刚体任务和一个柔性任务，覆盖 privileged/standard、一个正常结束 trial、一次中断及获准重跑。订阅和 API 两种认证分别验证；使用单独的小预算验收任务单，不改正式任务单预算。发布更多任务前，逐项确认派单集合的 prepare/preflight 与证据资格；少量试跑不能代表全部 13 类任务合格。

实施与验收继续遵守仓库资源约束：CPU 记录但不因超过 90% 停止；系统内存达到 90% 时只停止本轮拥有的相关进程。所有 GPU/模型运行、网络上传和冷机验收单独记录实际身份与结果，不从 CPU 合同测试推断。

## 10 发布门槛和外部依赖

首版可以发给 helper 的条件是：固定发行版本和正式 assignment 已生成；严格扫描、完整封包、跨路径导入通过；真实接收端能够重建审查材料；至少一份独立 GPU 主机结果包完成交付演练。需要实际启用 HF 路线时，再验证目标私有 dataset 的真实写入与回执。共享文件夹路线也需验证三文件下载后可正常导入。

实施前需要落实的外部输入只有实际工作所需的几项：网站 importer 仓库与接口、首批任务和模型配置、交付目标、可用的独立 GPU 主机及验收账号。任务单 schema、扫描修复、封包和本地异机导入测试可以先进行。缺少网站代码时，W5 的网站部分保持未验收，不能将首版标为全部完成。

多 lane、原文 task-base 直接执行适配、公开镜像发布以及异机物理重评分分别作为后续能力验收。W8 尤其需要同时处理同 work-dir 的全局 GPU 锁和订阅 token 串行锁；只把 `concurrency` 改大，无法满足文档中“一条命令增加一个 lane”的承诺。

本计划的完成标志是一份可从维护方任务单追溯到 helper 原始记录、再追溯到接收端页面的实际交付证据，包含明确的完成状态、异常记录和文件校验。


## 12 实施结果与验收边界（2026-10-04）

- 实现六个 helper 子命令，保留原 difficulty runner；schema 2 显式 trial 列表贯穿执行、收集和旧 HF 读取器。派单与源摘要在首次运行和恢复时均检查。
- 镜像功能通过 `helper_log_mirror.py` 适配固定上游 `log_mirror.py`，不破坏 vendor 字节一致性。模型 job 写入者停止后才最终同步；每次记录由独立容器收集。mirror 是轮询备份，不保证捕获轮询间每次变化。
- 完整 bundle 与旧 HF 指标格式独立。接收端具备纯标准库验包、相对任务映射、汇总重算、Markdown 文件审查入口、幂等导入、终态证据不可覆盖检查。`site-input.json` 是 adapter 输入协议，不代表外部网站已接通。
- 凭据扫描覆盖原文及 ZIP/NPZ/gzip，保留文本脱敏审计；未知密钥及嵌套压缩不能据此得到全覆盖保证。staging 失败不发布成品；需保留私有目录供诊断。
- 自动测试合并到 `ci_checks/test-helper-delivery.py`，扩展现有 eval/delivery/HF 回归，使用 synthetic Harbor/Hub/daemon 文件与真实 CPU 抽样；未把这些结果计为物理解题成功。
- 仍未具备外部网站仓库入口、独立 GPU host 和正式私有 HF 目标/凭据，故正式放行门槛未全部满足。helper 可以使用已实现流程，但首次实际交付应作为演练验收，不能宣称跨主机模型/网站全链路已通过。


本轮验证记录：

| 范围 | 结果 | 证据 |
|---|---|---|
| helper 扫描/派单/队列/封包/导入/模拟上传 | 25/25 | `runs/test_results/helper_delivery_20261004_112218/` |
| 现有 difficulty eval | 27/27 | `runs/test_results/helper_delivery_20261004_111917/` |
| 现有 Docker delivery | 10/10 | 同上 |
| 现有 HF 与新增 helper launcher 边界 | 24/24 | 同上；Unix socket 用本机假 daemon |
| 真实 Docker、root 私有原始文件、mirror、脱敏封包、Python 3.10 标准库异路径导入 | 通过，synthetic records，无 GPU/模型/网络 | `runs/test_results/helper_docker_smoke_20261004_111827/` |
| 源码发行包解压、真实 CPU 抽样派单、plan/恢复、部分封包、异路径导入及 complete 门槛 | 通过，无物理/模型执行 | `runs/test_results/helper_release_smoke_20261004_111912/` |

共 86 项 CPU 合同回归通过。资源监控的上述成功运行峰值 CPU 为 61.2%、内存为 16.9%，未触发内存 90% 停止阈值。总索引与最终工具文件摘要：[验收记录](../../runs/test_results/helper_delivery_acceptance_20261004/summary.json)。源码发行演练保存当时的独立源码包与 source SHA；其他会话继续修改的工作区不等同于该快照。测试中的 solved 是合成 fixture 状态，不能当成真实模型解题成功。
