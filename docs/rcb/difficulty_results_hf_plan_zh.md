# Difficulty trials 结果上传 Hugging Face 工程计划

2026-09-30。状态：待实施。本次只核对现有代码并制定方案，未修改评测逻辑、运行实验或上传结果。

可以为 `bash_scripts/run_difficulty_trials.sh` 增加 `--results_to_hf`，默认目标为用户提供的 dataset 仓库 `LGVamper/toponym_evaluation_results`。建议在现有结果收集之后增加独立导出和上传步骤，继续由 Python 调度；Bash 负责参数及凭据跨 Docker 边界的传递。

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
| `--hf-token-env` | `HF_TOKEN`；可指定宿主环境变量名称；未提供凭据时进入下文的自动登录流程，不接受 token 字面值 |
| `--hf-exp-date` | 新 run 使用首次创建的 UTC 日期；格式 YYYY-MM-DD，首次确定后持久化 |
| `--hf-artifacts` | `standard`；另支持 `metrics`，内容见下文 |
| `--hf-dry-run` | 只生成本地导出、清单和大小报告；不访问 HF，不需要 token |
| `--phase upload` | 只发布已有收集结果，不重新收集、不启动 GPU 或模型 |

以下均为实施后的目标命令，当前版本尚不支持新参数。

正常跑实验并上传，沿用现有模型认证参数：

```bash
# 首次会隐藏提示输入 HF token，验证后保存；后续复用，也可预先提供 HF_TOKEN。
bash bash_scripts/run_difficulty_trials.sh \
  --run-id difficulty-eval-20260930 \
  --tasks 1-13 --samples-per-difficulty 1 \
  --auth api-key --model '<现有支持的模型 ID>' \
  --results_to_hf
```

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

1. **启动前检查**：run/all 开启上传时，在昂贵的模型运行和 GPU 锁获取之前完成自动登录，检查 SDK、token、目标 dataset 和写权限。权限或配置错误直接终止该次启动；网络错误有限重试后报错，明确本次实验尚未启动，可修复后重试或去掉上传开关先在本地运行。dry run 跳过全部 HF 调用。只验证身份登录成功不能代表仓库可写；选择锁定 SDK 支持的写权限检查接口。
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

## HF 凭据和外部参与者

### 首次登录自动并入上传入口

按用户补充要求，首版直接包含自动登录。用户创建一次 token 后，首次运行带 `--results_to_hf` 的命令即可输入，不再要求另装宿主 HF CLI 或预先执行 `hf auth login`。本方案自动处理凭据验证、保存和复用；token 的创建及初次提供仍由用户完成。

解析优先级固定为：指定环境变量中的非空 token → TopoGym 已保存凭据 → 宿主 HF CLI 已保存的当前 token → 终端隐藏输入。显式指定非默认 `--hf-token-env` 却未设置该变量时直接报错，不暗中换身份。宿主已有登录按 `HF_TOKEN_PATH`、`HF_HOME` 及 HF 默认缓存位置解析，只读取当前 token 文件，不挂载整个用户缓存。SDK 的环境配置须在导入前确定。[HF 环境变量说明](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables)。

| 场景 | 目标行为 |
| --- | --- |
| 首次交互运行，无可用凭据 | 显示目标仓库，用隐藏输入读取一次 token；验证身份及仓库读写权限后保存并继续 |
| 已有有效登录 | 自动复用；提示身份、凭据来源和目标仓库，不打印 token |
| 环境变量提供 token | 验证后用于本次调用；默认不落盘，适合无人值守任务 |
| 无 TTY 且无凭据 | 立即给出设置 HF_TOKEN 或提前登录的说明，不尝试 getpass 回显、不挂起等待 |
| 已保存或导入的 token 认证失效 | 启动阶段有 TTY 时允许一次隐藏输入替换；新凭据验证成功后原子保存；无人值守时明确失败 |
| 显式环境变量中的 token 无效 | 直接报错，不回退其他账号；仓库权限不足也不循环重试登录 |
| 实验结束时 token 已失效或被撤销 | 保留结果与发布状态，返回上传错误和补传命令，不在收尾时等待新 token |
| dry run、关闭上传、plan/prepare/preflight | 不提示登录、不校验 HF 权限、不读写凭据缓存 |

增加以下可选维护命令，沿用同一个入口。它们不要求 run-id、模型凭据或 GPU；Docker 模式使用控制镜像中的 SDK，local 模式调用相同认证模块。既有 `auth login` 继续表示 Codex 登录，新增 `auth hf` 分支避免混淆。

```bash
# 以下为待实现命令；login 显式更新保存的 HF 登录。
bash bash_scripts/run_difficulty_trials.sh auth hf login
bash bash_scripts/run_difficulty_trials.sh auth hf status
bash bash_scripts/run_difficulty_trials.sh auth hf logout
```

`login` 和 `status` 接受 `--hf-repo-id`、`--hf-token-env`，默认目标与上传一致；login 可从环境变量导入并保存，或终端隐藏输入。status 只检查并报告身份、来源及目标读写权限，不触发交互或保存。logout 只清除 TopoGym 的 HF 登录文件，不删除实验数据、不影响 Codex 登录或用户全局 HF 登录，也不会撤销服务器端 token。若环境变量或全局 HF 登录仍可提供凭据，logout 的输出需明确提示其仍然有效。

### 保存位置和 Docker 传递

独立认证模块拟放在 `scripts/difficulty_hf_auth.py`，由 uploader 和 `auth hf` 命令共用。隐藏输入后显式调用 SDK 验证和登录接口，禁用写入 Git credential helper；不要通过命令行拼接 `hf auth login --token ...`。程序化登录与保存是 SDK 已有能力，适配时验证项目锁定版本的接口。[HF 认证接口](https://huggingface.co/docs/huggingface_hub/package_reference/authentication)。

TopoGym 凭据默认保存在 `${XDG_CONFIG_HOME:-$HOME/.config}/topogym/huggingface/`，可通过 `TOPOGYM_HF_AUTH_DIR` 覆盖；目录 0700、文件 0600，使用独立认证锁和原子替换。Docker/local 共用这份宿主目录，不随控制器删除或 work-dir 切换丢失。SDK 的 token 与 stored_tokens 如均被使用，须纳入同一保存和清除范围；不假设单删一个 token 文件就退出全部登录。

HF token 与模型 API key 是两套独立凭据。Bash 仅在实际上传或 HF 登录操作时读取选定的宿主凭据，将环境或全局登录导入值放进现有私有临时目录的 0600 文件，通过 `/run/topogym-launch` 只读传入。项目认证目录仅挂载给可信控制器，输入和保存由认证模块负责；独立 HF 登录不需要 Docker socket、Codex 凭据目录或 GPU 挂载。status 使用只读凭据挂载；需要保存或清除凭据的调用使用可写挂载。拒绝跟随认证文件 symlink。

不要使用 `docker -e HF_TOKEN=...`，token 不放入 argv、Docker Config.Env、运行配置、日志或发布清单。控制器仅向认证与上传模块提供 token；local 模式也在创建评测子进程前抽离 HF_TOKEN 和用户指定变量。HF token、认证目录以及可定位该目录的配置不传给 Harbor、agent、sim、verifier 或构建进程。认证/上传进程显式指定自己的 SDK 缓存，其他进程不能通过 SDK 默认搜索重新发现它；现有 AUTH_VARIABLES、环境净化和容器挂载必须共同覆盖这条路径。

本次用途预期只有几天，不引入后台刷新、自动签发或固定天数清理任务。结束后可运行 `auth hf logout` 清除本机项目登录，并在 HF token 管理页面撤销该 token；本机退出和服务器端撤销是不同动作，不把“打算使用几天”当作自动到期设置。[HF token 管理说明](https://huggingface.co/docs/hub/security-tokens)。

### 外部参与者权限

直传要求所用凭据对目标 dataset 有写权限。公开可读和 token 类型为 write，都不能单独证明对该仓库有写权限。建议维护方及受信执行环境使用仅限目标仓库的 fine-grained token，按用途分开签发；HF 权限通常以仓库为单位，本文目录隔离不能代替服务端逐参与者写入授权。[HF token 权限说明](https://huggingface.co/docs/hub/security-tokens)。

首版直传适用于维护方机器或已经获得目标仓库写权限的运行方。面向外部参与者分发脚本时，不随启动包附带维护方 token；后续增加 `--hf-create-pr`，参与者用自己的身份提交，维护者合并。该目标为私有仓库，PR 也不能绕过访问权限；参与者须先获得相应访问授权。HF 提供通过上传创建 PR 的接口，但账号权限、大文件和断点恢复需要独立验收；恢复同一 PR 时记录并复用其 revision，不能每次重传创建新 PR。[HF 贡献接口](https://huggingface.co/docs/huggingface_hub/guides/community)。无法获得私有仓库访问权的参与者，首版可交回本地导出结果，由维护方统一补传。如需要无账号、无需人工合并的公开收集，再另建接收服务，超出首版上传开关的范围。

## 文件改动与实施顺序

| 阶段 | 文件和工作 | 完成标准 |
| --- | --- | --- |
| 1 导出合同 | 新增 `scripts/difficulty_results_hf.py`；定义 sidecar、逐行 schema、路径映射、artifact 模式和 staging | 既有 fixture 可离线生成完整目录与清单；不重新判分 |
| 2 认证和上传实现 | 新增 `scripts/difficulty_hf_auth.py` 管理自动登录；上传模块封装固定 SDK、权限检查、分批提交、哈希对账、收据和恢复 | mock Hub 下覆盖认证、故障与并发；真实测试仓库补传成功 |
| 3 调度接入 | 修改 `scripts/difficulty_eval.py`，增加别名、upload 阶段、收尾调用和退出码合成 | 默认行为不变；纯补传不要求模型或 GPU；失败记录保留 |
| 4 Docker 交付 | 修改 Bash 和 `scripts/difficulty_delivery.py`，增加 auth hf 分支、独立凭据挂载与环境隔离；控制器 `.in/.lock` 显式声明 SDK | 自动登录无需宿主 HF CLI；HF 凭据仅到认证和上传模块；upload 不申请 GPU；固定镜像能补传 |
| 5 文档与发行 | 更新 Docker quickstart、RCB README、脚本说明；构建新 controller 并记录 release 身份 | 外部用户能完成运行上传、预览、补传三条路径 |

导出器可以复用收集后的 JSONL 和 results 文件；首版尽量保持 `collect_batch_results.py` 的判分和本地目录合同。新脚本、依赖锁和相关资源须核对已被 `difficulty_release.py`、控制器 Dockerignore 与 source_hash 纳入。现有白名单已包含 scripts/requirements，通常无需扩大到整个工作区。

历史 run 的执行恢复继续遵守原 release/source 身份校验。新的 upload 分支只读取历史 manifest 与已收集结果，记录原实验身份和当前 exporter 身份，不要求历史 release 等于新 controller；不能为补传放宽正常 run 的源码校验。若历史结果缺失，先用匹配的旧执行环境 collect，再用新 uploader 发布。

首版先完成自动登录、standard/metrics 两档、结束上传和补传。持续增量上传、PR 模式、全局 Parquet 索引及可视化统计作为后续独立增量，不阻塞受信运行方集中回传结果。

## 验收计划

新增 `ci_checks/test-difficulty-results-hf.py`，使用小型合成结果和 mock Hub，不为了上传测试启动真实模型或物理仿真。必要场景包括：

- 同日同 seed 的两个 run、双模式、多 attempt 各有独立路径；resume 保留 UUID 和日期；scene_seed 映射正确。
- solved、unsolved、not_evaluable、未完成及基础设施失败全部保留；最新 attempt 的分母与原收集器一致。
- standard/metrics 白名单、缺文件、越界和 symlink 检查；宿主路径与植入的假 token 不出现在导出或日志中。
- 缺 token、无写权限、404、限流、上传中断、响应丢失、父 commit 冲突、内容冲突、重复补传及最后标记失败。
- 不带上传开关时无 HF 调用；dry run 不联网；upload 不启动 Harbor/模型、不获得 GPU 锁、不新建实验。
- Docker 命令和容器 inspect 中不出现 token；评测子进程环境不继承 HF token；上传故障与实验退出码组合正确。
- 自动登录覆盖首次隐藏输入、重复运行无提示、容器重建和 work-dir 切换后复用、既有 HF_HOME/HF_TOKEN_PATH 导入、环境变量优先及默认不落盘、无 TTY 立即失败；全程使用假 token 检查无回显和无日志泄漏。
- 认证失败、仓库无权限、网络失败分别处理；替换失败保留原凭据，两个启动进程竞争认证锁时不损坏缓存；收尾阶段失效不挂起。auth hf status 无写入；logout 仅清项目凭据，既有 Codex auth 路由保持原语义。
- 历史 frozen manifest 和新 exporter 能共存；正常 run 的原 release 校验仍有效。

修改后运行现有 difficulty eval/delivery/docker 的相关合同检查。实网先在指定测试 dataset 上传小型 fixture，断开后恢复并下载按 SHA-256 核对；随后对一份已有真实结果进行 standard 上传，确认浏览器目录和回放文件可访问。测试记录 repo、revision、文件数、总字节及验证结论；上传成功不表示场景、模型或任务成功已重新验收。

当前完成范围是这份计划及 README 导航。实现、自动化测试、实网写权限核验和上传验收均待后续实施。
