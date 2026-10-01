# Difficulty trials 结果上传 Hugging Face 工程计划

2026-09-30。状态：首版已实现，凭据注入、结果导出、上传/补传、离线预览和上传日志已接入；实网写权限与真实 HF 提交仍待提供 token 后验证。本文保留设计与后续功能范围，实施记录见文末；实际使用见 [Docker quickstart](docker_quickstart_zh.md#上传结果到私有-hf-dataset)。

可以为 `bash_scripts/run_difficulty_trials.sh` 增加 `--results_to_hf`，默认目标为用户提供的 dataset 仓库 `LGVamper/toponym_evaluation_results`。建议在现有结果收集之后增加独立导出和上传步骤，继续由 Python 调度；Bash 负责参数及凭据跨 Docker 边界的传递。

认证以运行时注入维护方提供的 HF token 为主：通过 `HF_TOKEN` 环境变量或 `--hf-token-file` 指定凭据文件，控制器显式创建 `HfApi(token=token)`，自动将结果 commit 到目标 dataset。正常运行不要求执行 `hf auth login`、交互输入或保存登录；交互登录仅作为可选便利功能。

首版交付自动上传、历史结果补传、离线预览、可恢复上传和多人目录隔离。实验结果先完整保存在本地，上传失败不重跑 trial。本文保留用户提供的仓库拼写 `toponym_evaluation_results`。用户已确认该仓库为 private；本次未认证浏览无法核验其内容和写权限，实施时通过有权限的身份调用 API 核对。私有状态不影响上传设计，也不需要改成公开仓库。

## 当前代码能够复用什么

| 位置 | 已有行为 | 接入方式 |
| --- | --- | --- |
| [Bash 入口](../../bash_scripts/run_difficulty_trials.sh) | 默认 Docker；支持 local；实验参数透传；凭据通过私有只读文件挂载 | 增加 HF 凭据文件传递和 upload 阶段识别 |
| [调度器](../../scripts/difficulty_eval.py) | plan、prepare、preflight、run、collect、all；锁住 run；冻结源码；执行后收集 | collect 完成后调用发布模块；新增纯 upload 分支 |
| [抽样器](../../scripts/sample_difficulty_instances.py) | 冻结 task、difficulty、sample_id、scene_seed、双模式与源码身份 | 直接复用身份，不重新抽 seed |
| [收集器](../../scripts/collect_batch_results.py) | 生成 trials.jsonl、summary.csv、summary.md；整理每次 attempt 的评分和媒体 | 从既有结构生成上传目录，不另写评分逻辑 |
| [Docker 控制入口](../../scripts/difficulty_delivery.py) | 读取 launcher 私有输入，启动调度器 | HF token 只提供给上传模块 |
| [控制器依赖锁](../../requirements/difficulty-eval-controller.lock) | 已间接锁定 huggingface-hub 1.33.0 | 升为直接依赖并验证该版本接口，不默认升级整套依赖 |

目前整理后的证据路径是：

```text
<work-dir>/runs/difficulty_trials/<run-id>/
  manifest.lock.json
  source_identity.json
  execution.lock.json
  trials.jsonl
  summary.csv
  summary.md
  results/<task_id>/<difficulty>/<sample_id>/<mode>/trial_01/attempt_001/
    reward.json
    agent_summary.json
    replay.mp4
    replay.last.png
    trajectory.npz
    episode.jsonl
```

各证据文件仅在原 trial 实际产出时存在。原始 Harbor jobs 位于 `<work-dir>/jobs/difficulty_trials/<run-id>/`。现有汇总包含宿主绝对路径，不能整目录原样发布；需要一个只导出约定字段和文件的转换层。

## 用户接口

统一接受用户提出的 `--results_to_hf`，同时提供符合现有 CLI 风格的别名 `--results-to-hf`。两者都是布尔开关；仓库覆盖使用独立参数，避免可选位置值产生歧义。

| 拟新增参数 | 默认值与含义 |
| --- | --- |
| `--results_to_hf` / `--results-to-hf` | 默认关闭；在本次调用中启用发布 |
| `--hf-repo-id` | `LGVamper/toponym_evaluation_results`；固定 repo_type=dataset |
| `--hf-token-env` | 默认读取 `HF_TOKEN`；可指定其他宿主环境变量名称，不接受 token 字面值 |
| `--hf-token-file` | 指定只包含 token 的宿主凭据文件；Docker 下通过私有临时副本只读传入控制器；与显式 `--hf-token-env` 互斥 |
| `--hf-exp-date` | 新 run 使用首次创建的 UTC 日期；格式 YYYY-MM-DD，首次确定后持久化 |
| `--hf-artifacts` | `standard`；另支持 `metrics`，内容见下文 |
| `--hf-dry-run` | 只生成本地导出、清单和大小报告；不访问 HF，不需要 token |
| `--phase upload` | 只发布已有收集结果，不重新收集、不启动 GPU 或模型 |

以下均为实施后的目标命令，当前版本尚不支持新参数。

正常跑实验并上传，沿用现有模型认证参数：

```bash
# HF_TOKEN 由运行环境预先注入；脚本直接认证和上传，不提示登录。
bash bash_scripts/run_difficulty_trials.sh \
  --run-id difficulty-eval-20260930 \
  --tasks 1-13 --samples-per-difficulty 1 \
  --auth api-key --model '<现有支持的模型 ID>' \
  --results_to_hf
```

使用独立凭据文件运行，路径可由部署配置提供，token 内容不写入启动脚本：

```bash
# 凭据文件由维护方预先放置，并限制为仅当前用户可读。
bash bash_scripts/run_difficulty_trials.sh \
  --run-id difficulty-eval-20260930 \
  --tasks 1-13 --samples-per-difficulty 1 \
  --auth api-key --model '<现有支持的模型 ID>' \
  --results_to_hf \
  --hf-token-file /path/to/secrets/topogym-hf-token
```

以上两种认证方式二选一。文件方式也适用于下方 collect/upload 命令：每次调用附加同一个 `--hf-token-file` 路径；环境变量方式由各次运行环境持续注入。补传更换 token 不改变实验或发布身份。

网络失败后，只补传已收集的结果：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase upload --run-id difficulty-eval-20260930 \
  --results_to_hf
```

对历史 run 先按原有方式收集，再上传：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase collect --run-id difficulty-eval-20260930 --resume \
  --results_to_hf --hf-exp-date 2026-09-30
```

检查将要上传的目录、文件数量、总大小与缺失证据：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase upload --run-id difficulty-eval-20260930 \
  --results_to_hf --hf-dry-run
```

`upload` 必须指向已有 run，直接验证其 manifest、结果和导出身份，不调用会新建快照的 `prepare_manifest()`，无需 `--resume`、模型参数或模型凭据。Docker 模式仍需控制镜像；提供固定镜像时补传不构建仿真镜像。local 模式可用原工作目录补传，缺 SDK 时给出安装说明；关闭功能时不引入 HF 网络请求或新的必需依赖。

`plan`、`prepare`、`preflight` 阶段不上传或触发 HF 登录；使用上传选项时明确提示尚未发布。`--hf-dry-run` 只支持 collect/upload，避免用户把它误解成整场实验的 dry run。评测命令中的 HF 专属参数必须与上传开关一起使用；独立 `auth hf` 命令按下文规则处理，不需要上传开关。错误组合在启动实验前报错。

## 远端目录和身份

建议在用户提出的日期、任务、难度和 seed 之外，增加一个唯一的实验目录，并保留双模式和重试层级：

```text
LGVamper/toponym_evaluation_results/
  2026-09-30/
    difficulty-eval-20260930--<run_uuid>/
      _run/
        metadata.json
        manifest.export.json
        source_identity.export.json
        execution.export.json
        trials.jsonl
        summary.csv
        summary.md
        upload_manifest.json
        publication.json
      hedgehog_in_cage/
        easy/
          seed_123456/
            unlimited/trial_01/attempt_001/
              result.json
              reward.json
              replay.mp4
              replay.last.png
              trajectory.npz
              episode.jsonl
            limited/trial_01/attempt_001/
              ...
```

例中的 seed 仅示意，实际必须取 `manifest.lock.json` 的 `scene_seed`，不能用 `sampling_seed` 或 sample 序号替代。`sample_id` 仍写入结果记录。任务名使用 canonical `task_id`，不用展示名称或截断的 Harbor 目录名。

`run_uuid` 使用完整 UUID，生成一次后保存在 run 的发布 sidecar；同一实验的 resume、collect 和重传沿用它。相同日期、run-id、seed 由不同机器独立创建时，UUID 使目录分开。复制整个 run 到另一台机器补传则保留 UUID；启动新实验必须创建新 run。`mode` 隔离 limited/unlimited，`attempt` 保留失败和重跑证据。

新 run 创建时记录 UTC 时间和日期；用户可在首次发布身份锁定前显式指定实验日期。旧 run 没有可靠创建时间时，优先使用 `--hf-exp-date`；未提供则采用首次导出 UTC 日期，并标记 `exp_date_source=first_export`，不能冒充实际实验开始日期。日期跨天、重试或换机器均不重新计算目录。

发布身份写入独立 `hf_publication.lock.json`，不修改既有 immutable manifest。锁定 repo、远端前缀、UUID、日期来源、manifest 哈希与导出 schema 版本；变更目的地或发生身份冲突时明确报错。路径组件只允许约定字符，禁止绝对路径、`..` 和跨目录拼接。

## 上传内容与分析数据

| 模式 | 内容 |
| --- | --- |
| `metrics` | 运行及源码身份、规范化 manifest、执行配置、逐 attempt 记录、汇总、reward.json、文件清单 |
| `standard` | metrics 加当前收集器已整理的 replay.mp4、replay.last.png、trajectory.npz、episode.jsonl |

首版默认 standard，便于接收方查看结果并回放证据。只传指标可显式选 metrics。同一发布身份的模式先锁定；首版不在同一路径里切换模式或删除已上传媒体。

每条结果至少保存：

- schema_version、run_uuid、run_id、exp_date、task_id、difficulty、sample_id、scene_seed、mode、trial、attempt。
- 原有 status、success、evaluable_for_task_success、tokens_in/out、cost_usd_api_price 和异常类型。
- 模型、provider、agent、推理参数、agent 时间预算；源码、manifest、sample 哈希；可获得的 release 与镜像身份、CUDA 配置。
- 相对于 dataset 根目录的证据路径、文件 SHA-256 和大小、缺失文件列表，以及 planned/completed/failed 的汇总计数。

结果状态继续采用现有收集器分类，包括 pending、blocked_preflight、interrupted、infra_failed、identity_mismatch、invalid_submission、not_evaluable、solved、unsolved。只从既有汇总读取判分，上传模块不得重新把失败或缺文件解释为 success=0；成功率仍按最新 attempt 中 solved/unsolved 计算。

每个计划 trial 都有记录；没有媒体或 verifier 的失败 trial 也生成最小 `result.json`。canary 不计入正式 trial 分母。模型成本保留现有 `cost_usd_api_price` 语义，不把它称作订阅用户的实际账单。

导出器去除 `job`、`harbor_trial`、源码快照等宿主绝对路径，换成稳定 ID 和仓库相对路径。规范化后的文件用 `.export.json` 命名，同时记录原始文件哈希与导出文件哈希，避免把转换后字节冒充原 manifest。源码记录应保留完整文件哈希清单，区分 dirty 源码和 Git HEAD；上传摘要本身不代表已发布了完整复现环境。

默认只从明确白名单创建独立 staging 目录。源码树、构建缓存、原始 jobs、完整 agent 对话、任意日志、`.env`、`auth.json` 和凭据文件不在首版上传范围内。逐文件拒绝 symlink、越界引用和未知文件；大文件流式计算哈希。文本导出走结构化字段白名单并扫描已知秘密，包含 HF token；不能把现有仅匹配已知 token 的扫描器视为万能脱敏工具。

每个 run 的 `_run/trials.jsonl` 使用同一列定义，供跨实验汇总。客户端只写自己的 run 前缀；全仓库索引和 dataset card 由维护方另行维护，避免多人同时覆盖根目录 `summary.csv`。后续为 HF Dataset Viewer 增加明确的数据文件选择配置，不能让异构 metadata、reward 和 trial JSON 被自动当成同一张表。

## 调度与失败恢复

正常路径为：完成本地 collect → 生成发布快照 → 校验文件与身份 → 上传证据 → 最后发布完成标记和汇总。上传过程可以失败，本地结果及 trial 状态独立保存。

1. **启动前检查**：run/all 开启上传时，在昂贵的模型运行和 GPU 锁获取之前解析注入的凭据，检查 SDK、token、目标 dataset 和写权限，不执行交互登录。权限或配置错误直接终止该次启动；网络错误有限重试后报错，明确本次实验尚未启动，可修复后重试或去掉上传开关先在本地运行。dry run 跳过全部 HF 调用。只验证身份登录成功不能代表仓库可写；选择锁定 SDK 支持的写权限检查接口。
2. **触发点**：run/all 正常结束和显式 collect 完成后上传，包括 collect 返回“存在失败或未完成项”的情况。首版按本次调用收尾发布，不逐 step 或逐帧推送。prepare/preflight 阶段失败与 Ctrl-C 优先保留本地证据并输出补传命令，不在信号清理中启动长网络任务。
3. **锁与资源**：生成 staging 时持有原 run 锁，保证不会与 resume/collect 同时改结果；上传释放 GPU 锁后进行，并用发布锁防止同一 run 的两个 uploader 并发。保持资源监测，内存到 90% 时停止本轮拥有的上传工作并保存状态，CPU 仅记录。
4. **本地状态**：`hf_upload/state.json` 保存 staging 哈希、已完成批次、目标前缀、错误类别、重试次数和远端 commit；不保存 token、请求头或原始异常响应。`hf_upload/staging/<snapshot_sha>/` 保留稳定待传快照。磁盘不足在准备阶段报错，不移动或删除原结果。
5. **重试与幂等**：相同发布身份和快照哈希重复执行时核对远端标记，已完成则直接返回其链接；没有完整标记时校验远端文件后补齐。超时但提交可能已成功时，先读远端确认，再重试。网络、限流和服务端错误采用有界指数退避；认证、路径和内容冲突立即报错。
6. **并发和同路径更新**：不同 UUID 只写各自前缀。用持久化身份及 manifest 哈希确认同一路径属于当前 run；每批提交带预期父 commit，竞争时重新读取身份和文件哈希再重试，不盲目覆盖。若已发布完成 attempt 的证据改变，拒绝覆盖，要求检查来源或创建新的发布身份。未完成 attempt 后续补齐允许更新，但记录新快照与提交版本。
7. **完成标记**：最后单独提交 `publication.json` 与对应清单、汇总，包含快照哈希和文件数量。只有全部声明文件确认存在才记 `upload_status=complete`；另用 `evaluation_complete` 表示实验是否完成，不能把“部分实验结果上传成功”称为实验全部成功。读取端使用完成标记所在的 commit 固定读取该版本；后续发布过程中的半成品不能污染先前可用快照。

拟采用固定版本 `huggingface_hub` 的显式文件提交接口，分批上传白名单内容；小快照可一次提交，媒体先传、发布标记最后传。需要逐批控制并发条件时使用 `HfApi.create_commit` 与 `parent_commit`。官方 SDK 文档说明 `upload_folder` 也能指定 dataset 子目录；当前在线版本可能拆成多次提交，因此不能把一次函数返回之前的远端目录存在等同于完整发布。[HF 上传说明](https://huggingface.co/docs/huggingface_hub/guides/upload)、[HF API 参考](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api)。具体行为须以项目锁定的 1.33.0 源码和测试为准。

退出码建议保留当前实验语义，并新增上传专用错误：

| 本次结果 | 退出码 |
| --- | --- |
| 实验原本返回 0，上传成功或未启用 | 0 |
| 实验原本返回非零 | 保留原码；单独报告 upload_status |
| 实验返回 0，但显式要求的上传失败 | 3；本地评测结果仍有效 |
| 纯 upload 成功或 dry run 成功 | 0；不据此改变历史实验状态 |
| 纯 upload 网络或权限失败 | 3 |
| 非法参数、缺少已有结果、身份不一致 | 2 |
| 用户中断 | 保留当前 130，输出恢复位置 |

## 上传日志和进度提示

首版包含独立的 `upload` 阶段提示，沿用现有带时间戳的终端日志风格，统一使用 `[hf-upload]` 前缀和 INFO/WARN/ERROR 级别。让运行方能判断当前是在整理文件、传输数据、等待 commit 还是重试，并始终分开报告评测结果与上传状态。

| 时机 | 必须显示的内容 |
| --- | --- |
| 启动前权限检查 | `Checking Hugging Face access`、目标 dataset、凭据来源类型 env/file/cache、检查结果；此时不声称已经开始上传 |
| 正式进入上传阶段 | `Uploading results to Hugging Face`、run-id、仓库、远端前缀、standard/metrics 模式 |
| 导出与校验 | `Preparing upload snapshot`、当前步骤、已扫描文件数；完成后显示计划文件总数、总大小、缺失证据数量与本地清单位置 |
| 对账与补传 | 已验证可复用的远端文件数、仍待处理的文件数；完整快照已经存在时显示 `Already uploaded` 并返回原 commit 链接 |
| 传输中 | 当前批次/总批次、当前文件或相对目录、已用时间；SDK 提供可靠回调时显示本批传输字节、速率和预计剩余时间 |
| 提交中 | `Committing batch` 与批次编号；传输结束后仍须显示等待提交的状态 |
| 可重试故障 | WARN、经过筛选的错误类别、重试次数/上限、下次等待秒数；响应结果不明确时先显示 `Checking remote commit before retry` |
| 发布完成 | `Upload complete`、文件数、快照逻辑大小、耗时、最终 commit SHA、固定到该 commit 的结果目录链接及本地收据位置 |
| 上传失败或中断 | ERROR 或 WARN、简短原因、已确认提交的批次数、本地结果保留位置、补传命令；不把此前成功批次误报成全部失败 |
| dry run 或未启用 | 分别显示 `Dry run: no upload performed` 或 `Upload disabled`；不打印 Upload complete，关闭时只提示一次 |

进度统计区分“计划文件”“已传输但未提交”“已确认提交”和“远端已存在且校验可复用”。百分比若按文件数计算，必须标注 files；按字节计算必须有可靠数据来源，不能用文件数量推算字节进度。去重文件的逻辑大小不等于实际网络传输量，不把复用数据计算为上传带宽。SDK 没有细粒度回调时仅显示批次、状态和耗时，速率与 ETA 标为不可用，不模拟增长的进度条。

长时间哈希、上传、等待提交或退避期间，每 15 秒输出一次状态心跳，避免用户误以为卡住；阶段切换和错误立即输出并 flush。交互终端可刷新同一行；重定向、Docker 日志及 CI 使用普通追加行，不输出终端控制字符。默认不逐文件刷屏，文件清单和详细事件保存在本地日志；心跳线程或回调必须随本次上传结束，不遗留后台任务。

日志示例仅说明格式，以下数值不是实际上传记录：

```text
[2026-09-30T18:00:00Z] [hf-upload] INFO Uploading results to Hugging Face | run=difficulty-eval-20260930 | repo=LGVamper/toponym_evaluation_results | mode=standard
[2026-09-30T18:00:02Z] [hf-upload] INFO Snapshot ready | files=126 | logical_size=88.0 MiB | missing_evidence=0
[2026-09-30T18:00:03Z] [hf-upload] INFO Remote check complete | reusable=42 files | pending=84 files
[2026-09-30T18:00:18Z] [hf-upload] INFO Uploading batch 1/3 | elapsed=15s | transfer_rate=unavailable | ETA=unavailable
[2026-09-30T18:00:23Z] [hf-upload] WARN Network timeout | retry=1/3 | retry_in=5s
[2026-09-30T18:00:40Z] [hf-upload] INFO Committing batch 1/3
[2026-09-30T18:01:30Z] [hf-upload] INFO Publishing completion marker
[2026-09-30T18:01:32Z] [hf-upload] INFO Upload complete | files=126 | logical_size=88.0 MiB | elapsed=92s | commit=<commit_sha>
[2026-09-30T18:01:32Z] [hf-upload] INFO Results: https://huggingface.co/datasets/LGVamper/toponym_evaluation_results/tree/<commit_sha>/<exp_date>/<run_prefix>
[2026-09-30T18:01:32Z] [hf-upload] INFO evaluation_complete=false | upload_status=complete | incomplete_trials=2
```

上述日志省略中间批次。只有确认完成标记提交成功或远端已存在完整标记后，才能输出 Upload complete。结果链接使用实际 SHA 和经过 URL 编码的相对目录，私有仓库链接仍要求查看者有访问权限。上传的是部分实验结果时，如实显示 `evaluation_complete=false`，不把上传完成解释为 trial 全部成功。

失败时打印可直接复用的补传命令，保留原 backend、work-dir、run-id、repo-id、artifact 模式和凭据来源参数，正确引用含空格路径；使用环境变量时只提示所需变量名。示例同样为待实现行为：

```text
[hf-upload] ERROR Upload failed | reason=permission_denied | evaluation_exit_code=0 | upload_status=failed
[hf-upload] INFO Local results retained: /data/topogym-work/runs/difficulty_trials/difficulty-eval-20260930
[hf-upload] INFO Restore repository write access, then retry:
bash bash_scripts/run_difficulty_trials.sh --backend docker --work-dir /data/topogym-work --phase upload --run-id difficulty-eval-20260930 --results_to_hf --hf-repo-id LGVamper/toponym_evaluation_results --hf-artifacts standard --hf-token-file /run/secrets/hf-token
```

本地追加保存 `hf_upload/upload.log` 和 `hf_upload/events.jsonl`，每次调用记录独立 invocation_id。事件字段至少包含 timestamp、level、event、run_id、stage、batch、file_count、logical_bytes、elapsed_s、retry_count 和 error_code；尚未知晓的计数使用 null。日志不作为恢复状态的唯一来源，恢复仍读取 `state.json` 并核验远端；这些日志不进入 dataset 上传白名单。

token 值、Authorization 请求头、带签名的传输 URL、原始 HTTP 响应体和未经筛选的异常堆栈均不得输出。文件名、错误描述和其他外部字符串去除控制字符；SDK 默认进度与 debug 输出需要统一接管，避免绕过既有日志脱敏。日志落盘失败需明确提示并保留终端输出；不得因此将远端未知状态报告为成功。

## HF 凭据和外部参与者

### 运行时注入 token 并自动提交

按用户澄清，主流程是由维护方配置一次 token 的供给方式，difficulty trials 每次运行直接使用该凭据，将结果提交到私有 dataset。环境变量或文件路径可放在运行配置中，token 本身不编入脚本、镜像或发行包。自动化包含读取、权限验证和 commit，不以执行 `hf auth login` 或持久化 SDK 登录为前置条件。

凭据选择规则固定如下：

1. 显式 `--hf-token-file` 和显式 `--hf-token-env` 互斥；同时提供时在运行前报错。
2. 指定文件时只读取该文件，忽略默认 `HF_TOKEN` 和缓存；指定环境变量时只读取该变量。指定来源缺失、为空、不可读或验证失败均直接报错，不回退到其他身份。
3. 未显式指定来源时先读取 `HF_TOKEN`；变量未设置时，可复用用户通过可选 `auth hf login` 明确保存的 TopoGym 凭据。已设置但为空或无效的 HF_TOKEN 视为配置错误，不回退缓存。
4. 仍无凭据时立即报错，给出环境变量或文件注入方式；有无 TTY 都不自动弹出登录。默认不搜索或导入用户全局 HF CLI 缓存。

文件使用单行 token，允许末尾换行；拒绝空文件、嵌入换行、异常大小、不可读文件和 symlink，检查仅当前用户可读的权限。local 模式读取指定文件后显式传给 SDK；Docker 模式按下文转换为只读临时凭据文件。文件路径是输入配置，不把宿主绝对路径写入上传元数据。

```text
HF_TOKEN 或 --hf-token-file
    → Bash 私有凭据文件
    → 只读挂载到控制容器
    → HfApi(token=token)
    → 校验目标 dataset 的权限
    → 上传白名单结果并创建 commit
```

| 场景 | 目标行为 |
| --- | --- |
| 环境变量或文件提供 token | 直接验证并使用；不创建持久化登录、不需要宿主 HF CLI |
| 无注入凭据，但已通过可选命令保存 TopoGym 登录 | 按上述规则复用；仅提示身份、来源和目标仓库 |
| 无可用凭据，不论是否有 TTY | 立即报错，不调用 getpass、不等待人工输入 |
| token 无效、过期或仓库权限不足 | 明确失败，不切换其他账号、不循环登录；修改注入来源后重试 |
| 实验结束时 token 已失效或被撤销 | 保留结果与发布状态，返回上传错误和补传命令，不在收尾时等待新 token |
| dry run、关闭上传、plan/prepare/preflight | 不提示登录、不校验 HF 权限、不读写凭据缓存 |

### 可选交互登录

以下便利功能独立于首版凭据注入和上传的交付验收，不阻塞全自动运行。仅显式执行 `auth hf login` 才允许隐藏输入并保存凭据，普通 eval/collect/upload 不触发此流程。它们不要求 run-id、模型凭据或 GPU；Docker 模式使用控制镜像中的 SDK，local 模式调用相同认证模块。既有 `auth login` 继续表示 Codex 登录，新增 `auth hf` 分支避免混淆。

```bash
# 以下为待实现命令；login 显式更新保存的 HF 登录。
bash bash_scripts/run_difficulty_trials.sh auth hf login
bash bash_scripts/run_difficulty_trials.sh auth hf status
bash bash_scripts/run_difficulty_trials.sh auth hf logout
```

`login` 和 `status` 接受 `--hf-repo-id`、`--hf-token-env`、`--hf-token-file`，来源互斥规则与上传一致；login 可从环境变量或文件导入并保存，没有提供来源时通过终端隐藏输入，无 TTY 则报错。status 只检查并报告身份、来源及目标读写权限，不触发交互或保存。logout 只清除 TopoGym 的 HF 登录文件，不删除外部注入文件、不修改环境变量、不影响 Codex 或用户全局 HF 登录，也不会撤销服务器端 token。输出需明确本次只清除项目缓存，外部注入的凭据仍由供给方管理。

### 保存位置和 Docker 传递

独立认证模块拟放在 `scripts/difficulty_hf_auth.py`，负责凭据来源解析、文件校验、权限验证及向 uploader 提供 token。主流程显式构造 `HfApi(token=token)`，不调用 login、不写 Git credential helper。可选登录命令才使用 SDK 登录和保存接口；不要通过命令行拼接 `hf auth login --token ...`。[HF 认证接口](https://huggingface.co/docs/huggingface_hub/package_reference/authentication)。

仅在用户选择可选持久化登录时，TopoGym 凭据保存到 `${XDG_CONFIG_HOME:-$HOME/.config}/topogym/huggingface/`，可通过 `TOPOGYM_HF_AUTH_DIR` 覆盖；目录 0700、文件 0600，使用独立认证锁和原子替换。Docker/local 共用这份宿主目录，不随控制器删除或 work-dir 切换丢失。SDK 的 token 与 stored_tokens 如均被使用，须纳入同一保存和清除范围；普通注入流程不创建这份缓存。

HF token 与模型 API key 是两套独立凭据。Bash 仅在实际上传或显式 HF 认证操作时读取选定的宿主凭据，将环境变量值或指定文件的内容复制到现有 0700 临时目录内的 0600 文件，通过 `/run/topogym-launch` 只读传入控制器。`--hf-token-file` 要做宿主路径解析和容器路径转换，不能仅把宿主路径透传给 Python，也不需要挂载整个 secrets 目录。临时副本由退出清理负责删除，持有到本次上传结束；原注入文件不改动。该临时传递不等同于持久化登录。

普通注入流程不挂载 HF 项目认证目录；只有读取可选登录缓存或执行 auth hf 管理操作时才按需挂载。status 和读取缓存使用只读挂载，显式保存或清除凭据使用可写挂载。独立 HF 登录不需要 Docker socket、Codex 凭据目录或 GPU 挂载。dry run、plan/prepare/preflight 和未启用上传时，不读取凭据文件、检查其是否存在或创建凭据挂载。

不要使用 `docker -e HF_TOKEN=...`，token 不放入 argv、Docker Config.Env、运行配置、日志或发布清单。控制器仅向认证与上传模块提供 token；local 模式也在创建评测子进程前抽离 HF_TOKEN 和用户指定变量。HF token、认证目录以及可定位该目录的配置不传给 Harbor、agent、sim、verifier 或构建进程。认证/上传进程显式指定自己的 SDK 缓存，其他进程不能通过 SDK 默认搜索重新发现它；现有 AUTH_VARIABLES、环境净化和容器挂载必须共同覆盖这条路径。

本次用途预期只有几天，不引入后台刷新、自动签发或固定天数清理任务。供给方结束使用后移除环境注入或独立凭据文件，并在 HF token 管理页面撤销该 token；使用了可选项目登录时另行 logout 清缓存。更新凭据后重新执行 upload 即可补传。移除本地副本和服务器端撤销是不同动作，不把“打算使用几天”当作自动到期设置。[HF token 管理说明](https://huggingface.co/docs/hub/security-tokens)。

### 外部参与者权限

直传要求所用凭据对目标 dataset 有写权限。公开可读和 token 类型为 write，都不能单独证明对该仓库有写权限。建议维护方及受信执行环境使用仅限目标仓库的 fine-grained token，按用途分开签发；HF 权限通常以仓库为单位，本文目录隔离不能代替服务端逐参与者写入授权。[HF token 权限说明](https://huggingface.co/docs/hub/security-tokens)。

首版支持维护方向受信运行方单独提供这枚限定仓库的 token，通过其机器上的环境变量或只读文件注入；运行方无需另建 HF 账号或执行登录，提交使用该 token 的授权。凭据与公开脚本、镜像和发行包分开分发，接收方持有的是 token 授予的仓库权限。共用 token 时不能用 HF 提交者身份区分实验参与者；记录 run_uuid 和运行元数据，并由维护方管理凭据分发与撤销。

后续如希望参与者使用各自身份，可增加 `--hf-create-pr`，参与者提交后由维护者合并。该目标为私有仓库，PR 也不能绕过访问权限；参与者须先获得相应访问授权。HF 提供通过上传创建 PR 的接口，但账号权限、大文件和断点恢复需要独立验收；恢复同一 PR 时记录并复用其 revision，不能每次重传创建新 PR。[HF 贡献接口](https://huggingface.co/docs/huggingface_hub/guides/community)。没有可用凭据的参与者也可交回本地导出结果，由维护方统一补传。如需要无账号且不向运行方提供 HF token 的公开收集，再另建接收服务，超出首版上传开关的范围。

## 文件改动与实施顺序

| 阶段 | 文件和工作 | 完成标准 |
| --- | --- | --- |
| 1 导出合同 | 新增 `scripts/difficulty_results_hf.py`；定义 sidecar、逐行 schema、路径映射、artifact 模式和 staging | 既有 fixture 可离线生成完整目录与清单；不重新判分 |
| 2 认证和上传实现 | 新增 `scripts/difficulty_hf_auth.py` 解析环境变量和凭据文件，显式初始化 SDK；上传模块封装权限检查、分批提交、哈希对账、收据、恢复和上传日志 | 无 CLI 登录、无交互、无持久化登录也可自动提交；阶段进度、心跳、重试及完成/失败提示齐全；mock Hub 下覆盖认证、故障与并发；真实测试仓库补传成功 |
| 3 调度接入 | 修改 `scripts/difficulty_eval.py`，增加别名、upload 阶段、收尾调用和退出码合成 | 默认行为不变；纯补传不要求模型或 GPU；失败记录保留 |
| 4 Docker 交付 | 修改 Bash 和 `scripts/difficulty_delivery.py`，增加 token 文件路径转换、只读挂载、临时文件清理与环境隔离；控制器 `.in/.lock` 显式声明 SDK | 无需宿主 HF CLI；HF 凭据仅到认证和上传模块；upload 不申请 GPU；固定镜像能补传 |
| 5 文档与发行 | 更新 Docker quickstart、RCB README、脚本说明；构建新 controller 并记录 release 身份 | 外部用户能完成运行上传、预览、补传三条路径 |

导出器可以复用收集后的 JSONL 和 results 文件；首版尽量保持 `collect_batch_results.py` 的判分和本地目录合同。新脚本、依赖锁和相关资源须核对已被 `difficulty_release.py`、控制器 Dockerignore 与 source_hash 纳入。现有白名单已包含 scripts/requirements，通常无需扩大到整个工作区。

历史 run 的执行恢复继续遵守原 release/source 身份校验。新的 upload 分支只读取历史 manifest 与已收集结果，记录原实验身份和当前 exporter 身份，不要求历史 release 等于新 controller；不能为补传放宽正常 run 的源码校验。若历史结果缺失，先用匹配的旧执行环境 collect，再用新 uploader 发布。

首版先完成凭据注入、standard/metrics 两档、结束上传和补传。可选 `auth hf` 登录管理、持续增量上传、PR 模式、全局 Parquet 索引及可视化统计作为独立增量，不阻塞受信运行方集中回传结果。

## 验收计划

新增 `ci_checks/test-difficulty-results-hf.py`，使用小型合成结果和 mock Hub，不为了上传测试启动真实模型或物理仿真。必要场景包括：

- 同日同 seed 的两个 run、双模式、多 attempt 各有独立路径；resume 保留 UUID 和日期；scene_seed 映射正确。
- solved、unsolved、not_evaluable、未完成及基础设施失败全部保留；最新 attempt 的分母与原收集器一致。
- standard/metrics 白名单、缺文件、越界和 symlink 检查；宿主路径与植入的假 token 不出现在导出或日志中。
- 缺 token、无写权限、404、限流、上传中断、响应丢失、父 commit 冲突、内容冲突、重复补传及最后标记失败。
- 不带上传开关时无 HF 调用；dry run 不联网；upload 不启动 Harbor/模型、不获得 GPU 锁、不新建实验。
- Docker 命令和容器 inspect 中不出现 token；评测子进程环境不继承 HF token；上传故障与实验退出码组合正确。
- 凭据注入覆盖默认 HF_TOKEN、自定义环境变量、token 文件、含空格路径、显式来源互斥、空值及不可读文件、文件权限和 symlink；指定来源失败不得回退全局登录或另一账号。
- 在没有 HF CLI、没有登录缓存、没有 TTY 的环境下，环境变量和文件两条路径均能完整提交；普通运行不调用 login/getpass、不创建持久化凭据、不修改原 token 文件；全程用假 token 验证日志、argv、容器 inspect 和上传产物无泄漏。
- Docker 路径正确转换、凭据挂载只读、临时副本退出后清理；dry run 不读取 token 文件。替换或撤销 token 后可用新凭据补传，不更换实验身份；认证失败、仓库无权限和网络失败分别报告，收尾阶段不等待输入。
- 历史 frozen manifest 和新 exporter 能共存；正常 run 的原 release 校验仍有效。
- 日志覆盖权限检查、导出、传输、提交、重试、Already uploaded、dry run、失败和中断；模拟时钟验证 15 秒心跳与节流，TTY/重定向输出均可读。缺少 SDK 字节回调时不产生虚构的百分比、速率或 ETA。
- 完成标记失败或提交结果未知时不出现 Upload complete；实验未完成但结果成功发布时两个状态分别显示。重传跳过计数和传输量不混淆；最终链接固定到确认的 commit，补传命令保留原参数且无 token 值。
- 使用假 token、签名 URL、异常响应及控制字符验证终端日志、upload.log、events.jsonl 均无泄漏或终端注入；模拟日志写入失败，确认终端提示与远端状态核验仍有效。

可选 auth hf 功能实施时单独验收隐藏输入、无 TTY 失败、缓存跨容器复用、原子替换与认证锁；status 无写入，logout 仅清项目缓存，既有 Codex auth 路由保持原语义。这些检查不作为首版注入式上传的前置条件。

修改后运行现有 difficulty eval/delivery/docker 的相关合同检查。实网先在指定测试 dataset 上传小型 fixture，分别验证环境变量和文件注入，再断开后恢复并下载按 SHA-256 核对；随后对一份已有真实结果进行 standard 上传，确认浏览器目录和回放文件可访问。测试记录 repo、revision、文件数、总字节及验证结论；上传成功不表示场景、模型或任务成功已重新验收。

## 首版实施记录（2026-09-30）

已接入 `--results_to_hf`（别名 `--results-to-hf`）、`--phase upload`、`--hf-dry-run`、standard/metrics 两档和环境变量/文件凭据。默认仓库为 `LGVamper/toponym_evaluation_results`。维护方提供限定该仓库写权限的 token，运行方无需 `hf auth login`。

认证模块为 `scripts/difficulty_hf_auth.py`；导出、上传与日志模块为 `scripts/difficulty_results_hf.py`。Bash 负责私有临时文件、只读挂载和退出清理，调度器在收集后发布。现有 `difficulty_delivery.py` 的私有参数传输可直接复用，无需增加平行传输逻辑。控制器显式依赖已锁定的 `huggingface-hub==1.33.0`，未升级其他依赖。

快照、发布身份、SHA-256 清单和恢复状态保存在 run 内；分批提交前核对远端文件，最终标记提交成功后才输出完成链接。已完成 attempt 不可覆盖；中断结果可以后续更新。若上传中断后本地结果发生变化，先补完保存的旧快照，再执行一次 upload 发布新快照。SDK 请求在独立子进程执行，响应超时、取消或内存保护会停止本次请求进程。

日志覆盖权限校验、导出文件数/大小、上传批次、跳过已有文件、提交、重试、15 秒心跳、成功/失败和补传命令；同时写入 `hf_upload/upload.log` 与 `events.jsonl`。不把 SDK 缺失的字节进度伪造为百分比或 ETA，日志和结果中的凭据及私有路径执行过滤。

本机已准备 `.secrets/hf-token` 空文件，权限为 0600。用户将 token 本身作为唯一一行填入后，在原运行命令后追加：

```bash
--results_to_hf --hf-token-file /home/jianwen/topogym/.secrets/hf-token
```

该文件不属于脚本、Git 追踪源码、源码快照或镜像内容。其他机器也可创建同样的独立文件，或注入 `HF_TOKEN`；不要求维护方修改并重新分发脚本。

自动化验收记录在 `runs/test_results/difficulty_results_hf_20260930/`：

- 新增 HF 合同测试 21 项通过：合成结果导出、凭据隔离、Docker 启动器模拟、空仓库、Git/LFS 哈希对账、并发冲突、响应丢失、幂等补传、终态保护、旧快照恢复、日志过滤、退出码及上传子进程取消。
- 原有 difficulty eval 23 项和 delivery 10 项测试通过；本次未运行模型或物理仿真。
- 已有 run `luna-two-tasks-20260929-234519` 的收集记录副本完成本地离线导出：12 条 trial 记录、19 个导出文件；副本未携带原始媒体，因此记录缺失 artifact，不将其当作完整媒体验收。
- 最终冻结控制镜像构建成功，镜像内关闭网络运行同一套 21 项 HF 测试通过；真实 Bash/Docker 入口对上述副本执行 `--phase upload --hf-dry-run` 成功，不申请 GPU、不读取 token。证据在 `controller-build-final/build.log`、`container-contracts.log` 和 `docker-historical-dry-run.log`；本次构建/容器验证峰值 CPU 100%、系统内存 50.9%，未触发内存保护。

本机已构建的冻结镜像身份如下，未推送外部镜像仓库；其验证只覆盖该快照，不表示并行会话的其他任务改动已通过：

```text
image_id:      sha256:eeddd1f8686fd7431fd5adcc49e180ab6820b7b3c194fedaaece94fd9de86ae7
release_id:    6cf1d1031249d07858c2f6f84db8cd970db8e5d4a970819446ce20338f546b96
bootstrap_sha: 8225d0f75acc4114fa85c158ce08959a87925f01d8c6edac44be3a34da945ac4
```

如需在本机固定使用此控制镜像，可加 `--controller-image sha256:eeddd1f8686fd7431fd5adcc49e180ab6820b7b3c194fedaaece94fd9de86ae7`。默认入口仍按当前源码哈希选择/构建镜像；旧 run 的正常实验恢复继续使用原执行镜像，纯 upload 可使用此新版。

真实 HF 仓库尚未收到本轮上传；当前测试不证明该 private 仓库的实际访问权限、服务端文件一致性或视频浏览效果。提供 token 后按上方实网验收步骤核验。可选 `auth hf` 登录缓存、PR、持续增量上传与全局索引仍属于后续功能，首版不读取全局或项目登录缓存。
