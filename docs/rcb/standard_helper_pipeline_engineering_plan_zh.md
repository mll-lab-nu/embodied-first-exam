# 标准 helper 流程：代码核对、问题说明与修复计划

2026-10-05 更新：采用冻结材料、helper 联网构建镜像的交付方式。`run_agent_batch.sh` 自动安装固定工具并构建缺失镜像；helper 不增加 prepare/preflight 或 docker build 命令。当前范围为 **8 个刚体任务 × 3 难度 × 双模式 × K=3，共 144 trials**，固定 oracle seed 0；每 trial 12 小时、150M/10M token（运行后判分）。当前入口及唯一需要调整的 MANIFEST 镜像 Id 查询见 [在线构建与原 CLI](helper_native_cli_zh.md)。真实联网重建、首次工具安装、本地 Git clone 完整性检查已通过，报告在 `runs/test_results/helper_online_build_20261005/`；正式 144 trials 和远端 Git 推送尚未执行。下面 2026-10-04 的实施状态和数量保留为历史记录，不代表当前范围或验收状态。

2026-10-04。本文保留实施前审查和计划；下文“拟新增/待完成”是当时状态。**最新实施与可执行命令见 [固定 oracle 实例 K=3 操作手册](standard_helper_operations_zh.md)**。当前工作区 HEAD 为 `ba01d029c986bb5d6fc53dd830480be06936b6ae`，并有未提交修改，因此该 commit 不代表工作区全部实现。

实施更新：P0 的 native plan/普通 tar 合同、P1 的固定实例选择与发布工具、P2 的固定 bootstrap/认证解析/刷新/模型 canary、P3 的 K 完整性/共享停止/rerun、P4 的受保护 mirror 与交付扫描、P5 的 MANIFEST/inventory/HF 检查、P6 的安全离线接收已加入代码。现有统一 helper 入口 `bash_scripts/run_helper_batch.sh`。最新实验排除 Knot/Slotted Post Ring/Orbits：30 实例、60 包、180 trials；Sol xhigh，每 trial 12 小时和 150M/10M token 运行后评分限额。CPU 和真实 Docker mirror 小样已验证；**实际任务包发布、真实模型/GPU、小批次到独立接收主机的 P7 放行仍未完成**。P8 网站继续暂缓。下面 13 任务/78 包的原计划保留为历史口径，不能作为当前实验范围或实际验收已完成的证明。

本文以用户提供的 helper 说明为交付合同：运行入口保留 `scripts/run_agent_batch.sh <batch> <task-base> ...`，结果保留 `jobs/agents/<batch>-<mode>-<task>/`，helper 使用原文的扫描、tar、sha256sum 和上传命令。难度和 seed 的 sweep 通过维护方预先发布不同任务包实现。用户已确认：其他分支未找到网站实现时，先跳过网站接通；当前实施终点为异机离线验收，保留未来接入既有 review site 的标准布局。

本文取代[上一份工程计划](helper_delivery_engineering_plan_zh.md)中“以 difficulty runner 和新 bundle 格式作为 helper 主流程”的方向。上一轮已实现的抽样、prepare、preflight、扫描、身份校验、镜像和验包代码仍可复用；历史 difficulty 结果不改名、不迁移、不追溯修改。本文没有宣称标准流程已经接通。

HF 最新沟通更新（用户提供的上游回复）：私有 `eai-v2-internal/helper-uploads` 已创建，上游已实测上传和下载，目录为 `helpers/<helper>/<batch>/`。每位 helper 使用独立的库级 fine-grained 写 token，接收方用自己的组织账号读取；我们尚未认证实测。官方静态手册为 `SHARING_RUNS.md`，TopoGym 命令补入 §3b。私有开发仓库不可要求第三方克隆，需另行提供固定 helper release。公开的 `agent-runs` 不接收原始归档。后续依赖审查、独立 release、下载入口和真实小测试见 [下一阶段计划](helper_release_and_hf_smoke_plan_zh.md)。

该下一阶段的工具导出、配置生成、HF 权限与独立下载验收入口现已加入；同一正式 pipeline 的小样步骤见 [CLI 手册](helper_native_cli_zh.md)。真实 rollout/HF 交付尚未完成，不以安装和离线回归代替真实验收。

## 先看结论

| 问题 | 核对结论 |
| --- | --- |
| 任务树放哪里？ | 已对齐分支使用仓库根目录 `tasks/<task-base>-privileged/`、`tasks/<task-base>-standard/`，配套 `tasks/dataset.toml`。正式交付应沿用它。 |
| agent-batch 如何认证？ | 原生 Harbor 已支持订阅 auth.json 和 API key；需要统一 runner、扫描器、登录工具对同一凭据来源的解析，并固定可安装的运行环境。 |
| verdict 如何查完整？ | 按运行前冻结的全部 trial 清单检查，不能从“现在有哪些目录”反推计划，也不能只检查一个 reward 文件。 |
| sibling mirror 是什么？ | `jobs/agents_mirror/` 与 `jobs/agents/` 是同一个父目录下的两个目录；前者备份 agent 日志及历史版本。 |
| 批次身份记录有没有？ | 有。旧 runner 有 release/task 选择记录，difficulty 有更丰富的 manifest/assignment。旧 runner 的记录不完整，且标准 tar 漏收其中一些文件。 |
| MANIFEST 能否自动填？ | 已有部分自动采集和摘要生成；尚未在标准 batch 路径中生成原文要求的完整 MANIFEST。 |
| HF 只需 token 吗？ | token 可满足认证，但还必须明确有写权限的目标 dataset、目标目录、待传文件；维护方应预先建好私有 dataset。 |
| 网站怎么接？ | 接收布局应保留未来的 host/batch 注册接口；本轮未找到网站代码，按用户决定先跳过，不阻塞离线交付。 |

## 1. 其他分支的任务目录约定

本轮用 `git ls-tree`、`git show` 核对了本地 remote refs。尝试读取 GitHub 最新 branch heads 时 SSH 返回 `Permission denied (publickey)`；以下是本地已保存 commit 的事实，不声称它们仍是远端最新 HEAD。

| 分支引用 | 已核对 commit | Git 中的 `tasks/**/task.toml` 数 | 说明 |
| --- | --- | ---: | --- |
| `rcb/main` | `85cf4c6f757a61a8a4fad369cc0374c54582400b` | 915 | README 明确规定根目录 `tasks/`；含 `tasks/dataset.toml`，runner 从 `$R/tasks` 运行 |
| `rcb/dev/qineng` | `e2cb7ce6bc3e990c735823267d7019978abdc78e` | 537 | 同样使用根目录 `tasks/` 和双模式 task-base 入口 |
| `rcb/dev/pingyue` | `fc7537975361f4b67c39ae459e4e8a2404338d68` | 115 | 仍含无模式后缀和 `-limited` 的旧命名，不能把所有分支都当成已经迁移 |
| `rcb/dev/chi` | `35f71b0b54a6630e61b59bdaa3b6bc2d56aea7b7` | 183 | 有根目录 `tasks/`，包含旧命名 |
| `rcb/dev/changhe` | `ad3c5109ca6716d33521714faf5d65209a6efd85` | 0 | 此已缓存分支不是当前统一任务树的参考；不据此推断其他 changhe 专项分支 |
| 本工作区 HEAD | `ba01d029c986bb5d6fc53dd830480be06936b6ae` | 126 | 根目录已有历史包；不等于活动 v15 已完成发布 |

这里统计的是“任务包”数量，双模式各算一个，不能当作实例数。当前工作区 `tasks/dataset.toml` 列出的 126 个名称与实际 126 个任务目录一致；这仅证明名称集合对应，不证明 v15 资格、包内所有字节或镜像已验证。

`rcb/main` 的 `docs/PROTOCOL.md`、`docs/TAXONOMY.md` 和 `tasks/dataset.toml` 还规定：任务包包含自己的工具、verifier 和资源引用；以目录 digest 标识内容；运行时不能依赖维护方的临时 checkout 路径。原 helper 说明要求任务目录来自指定 commit。

因此正式目录建议如下，新增 runtime catalog 的确切文件名在 P1 实现时定稿：

```text
robot_coding_bench/
  tasks/
    dataset.toml
    topogym-cast-coil-easy-s00-privileged/
    topogym-cast-coil-easy-s00-standard/
    topogym-cast-coil-medium-s00-privileged/
    topogym-cast-coil-medium-s00-standard/
    ...
  ci_checks/
    topogym_active_release.json
    topogym_runtime_catalog.json      # 拟新增、随发布 commit 获取
  configs/helper_batches/
    <batch>.json                      # 拟新增、不含凭据的派单清单
```

正式包和 catalog 必须进入交付 commit，或者成为该 commit 明确且固定的必需资源。若改为另外下载 task archive，就增加了原文没有的任务获取步骤，不能仍宣称“仅 checkout 即获得任务”。大资产若用 LFS，需要明确 LFS 安装及 materialization，验收实际字节，不能把 pointer 当资产。

当前 v15 的 `tasks_root`、`runtime_catalog` 都是 null。`topogym_versions.py` 因此阻止启动；不是没看到历史 `tasks/`。现有 candidate pipeline 只有完整 39 实例、78 包通过规定验收后才激活。少量 sampled 包不能冒充这个全量资格。

**修复做法：**维护方先抽样、prepare、preflight，再以最终 task-base 发布并登记。默认全量 release 和一次小批 sampled 实验各自有明确资格范围；可以增加显式的 frozen batch catalog 选择，保留源码、实例、镜像和 preflight 检查，不把“取消 registered 检查”当作衔接。每个批次仍引用确定的发布定义。旧包保留；task-base 冲突时拒绝覆盖，先为新实例分配名称再构建，不能在交付时改 job/trial 名。

代码：[抽样器](../../scripts/sample_difficulty_instances.py)、[prepare/preflight](../../scripts/difficulty_eval.py)、[release 检查](../../scripts/topogym_versions.py)、[全量候选激活](../../scripts/topogym_candidate_pipeline.py)。

## 2. 新版 agent-batch 的认证准备

这里涉及三套凭据，不能混用：Git/镜像访问凭据用于取得代码和镜像，模型凭据用于 agent rollout，HF token 用于最后上传结果。接收和审查结果不需要 helper 的模型凭据。

### 2.1 现有原生入口

本机安装的 Harbor Codex agent 按以下顺序选认证：显式 `CODEX_AUTH_JSON_PATH`，其次 `CODEX_FORCE_AUTH_JSON=1` 指向 `~/.codex/auth.json`，否则走 API key。原 runner 把 `ENV_FILE` 交给 Harbor，也接受这些进程环境变量。

helper 首次准备订阅认证可使用现有 Codex CLI。以下只说明认证，不会解除当前 release 阻断，也不是本轮已执行的登录操作：

```bash
codex -c 'cli_auth_credentials_store="file"' login --device-auth
codex -c 'cli_auth_credentials_store="file"' login status

# 默认 Codex 缓存位置；若用户使用自定义位置，填写真实绝对路径。
export CODEX_FORCE_AUTH_JSON=1
export CODEX_AUTH_JSON_PATH="$HOME/.codex/auth.json"
test -r "$CODEX_AUTH_JSON_PATH"
```

无浏览器主机可使用 device-code 登录；文件存储将凭据放在 Codex 配置目录下的 `auth.json`。若组织策略强制使用另一存储方式，应如实报告，不能假设这个文件必然生成。依据：[OpenAI 认证说明](https://learn.chatgpt.com/docs/auth)。

API 认证则在 helper 自己的私有 `rcb.env` 中准备 Harbor 所需的变量，例如 `OPENAI_API_KEY`；OpenRouter 的原生 Codex 路线使用 `OPENAI_API_KEY` 和对应 `OPENAI_BASE_URL`。HF token 不写进该模型运行环境。

原文手动扫描同时指定 `rcb.env` 和 `~/.codex/auth.json`，所以两个显式输入都必须存在。纯 API helper 没有订阅 auth.json 时，当前扫描器会报错。修复应让认证准备工具生成“只含所选凭据来源”的实际扫描命令；若交付文档坚持该命令逐字不变，需要明确准备相应文件，不能由扫描器静默忽略拼错或不存在的凭据路径。

### 2.2 目前没有接好的地方

| 问题 | 代码现状 | 修复要求 |
| --- | --- | --- |
| 两套登录目录 | Docker difficulty 登录默认在 `~/.config/topogym/codex`，旧 batch 默认在 `~/.codex` | 显式选定唯一真实来源，供 Harbor 和扫描器共用；不靠复制多个缓存维持一致 |
| env-file 的解析时机 | Harbor 加载 dotenv，但 shell 在此前决定是否给 scanner 加 `--codex-auth` | 共用凭据解析器，从进程环境和 dotenv 得到相同配置；dotenv 当数据解析，不执行文件 |
| 只设置显式 auth 路径 | Harbor 支持；shell scanner 分支主要看 `CODEX_FORCE_AUTH_JSON` | 扫描器以解析后的来源为准，不漏扫实际使用的 token |
| 长批次 token 刷新 | difficulty Docker 镜像有固定 Harbor patch 和 `persistent_auth.py`；宿主 PATH 上的 Harbor不保证有它 | 新执行环境固定 Harbor 及补丁身份，记录刷新前后的私有扫描来源 |
| 多 lane 共用订阅缓存 | difficulty 目前用独占 auth lock；原 batch 没有同等管理 | 明确共享凭据的并发策略，实测两个 lane 的刷新、退出和恢复；原子写文件本身不能证明并发刷新安全 |
| 提前检测登录失败 | difficulty 有认证 canary；batch 主要在 job 后判断账号错误 | 在启动正式任务前做只读配置检查和独立、预算明确的 canary；canary 不计任务数 |

多 lane 的 rollout 并发与认证缓存的并发是两件事。支持两个 lane 认领不同 job，并不能证明同一订阅缓存可并发刷新。该组合未验收前必须明确报限制，不能声称所有认证模式都支持无限增加 lane；API 和独立凭据 profile 分别验收。

新 runner 仍以原生 Harbor agent 执行。认证维护和登录工具属于宿主调度层，不另建修改模型请求的 agent adapter。

另需解决安装问题：旧 batch 默认指向 `.venv-gs121-nyx/bin/python`，干净 clone 没有这个私有 venv；`topogym_versions.py` 直接导入 `tomllib`，仅写“有 python3”不足以满足运行条件。本机 `/usr/bin/python3` 就没有该模块。P2 需要固定 Python/Harbor/agent 版本并提供可重建的 bootstrap，原 batch 命令在准备完成后直接可用。

代码：[batch 参数与扫描入口](../../scripts/run_agent_batch.sh)、[difficulty 认证](../../scripts/difficulty_eval.py)、[认证刷新 patch](../../images/difficulty-eval/patch_harbor.py)、[私有缓存更新](../../harbor_agents/persistent_auth.py)、[Docker 登录与锁](../../scripts/difficulty_delivery.py)。

## 3. verdict 怎样才算检查完整

verdict 是 verifier 的判定记录。`success=0` 可以是有效的任务失败；它不等于基础设施失败。反过来，存在 `reward.json` 也不保证实验有效结束。

原文循环的实际含义是“对已经存在的每个 job 目录，找到至少一个 reward 文件”。它漏掉三类情况：未创建的预期 job、同 job 的 K 次重复只完成一部分、reward 虽存在但 trial 未结束或 grader 出错。上一轮实际拿掉 24 份中的一份后，这个循环仍然没有输出。

### 3.1 从计划检查，不能从输出推算计划

执行前冻结：最终 task-base、模式、实例 seed/摘要、K、模型参数、预算、允许的重跑关系。逻辑 trial 用 `(task, mode, repetition_index)` 标识。重跑 attempt 单独标识，不增加原实验的计划数。

例如 3 档 × 每档 2 个 seed × 2 模式 × K=2，应计划 24 个 trial。必须能列出全部 24 项，包括尚无目录的项。默认 `SEQ=1` 下它们落入 12 个 job；`SEQ=0` 的聚合 job 需要另一种映射，不能复用“一个 job 就是一项”的假设。标准 helper 合同优先使用 `SEQ=1`。

### 3.2 每个 trial 的检查顺序

1. 核对 job/trial 与派单的映射、task 名、包 digest、release/runtime binding、预算和 agent 设置。不能靠可能被截断的 trial 文件夹名猜身份。
2. 检查预期 repetition 是否各有一份结果；缺失、额外、重复和无法归属的 trial 分别报错。未启动项保持 pending。
3. 解析 trial 级 `result.json`、完成时间、异常、verifier 状态；job 顶层 `result.json` 在启动时就可能出现，不当完成标记。
4. 解析 `verifier/reward.json`，与 Harbor `verifier_result.rewards` 的对应值交叉核对。格式错误和不同记录互相矛盾都不能通过。
5. 区分有效成功、有效失败、非法提交、infra failure、中断和实例不可评测。模型预算正常耗尽后若 verifier 有有效负判定，可归为完成的失败；账号无权限、OOM、GPU 丢失或 grader error 不归为有效完成。
6. 按模式检查证据。standard 验证 finalization、启动与 replay 绑定；privileged 验证提交与 replay 判定。有效的“没有提交轨迹”失败不强求一份不存在的轨迹，但必须有清楚的 verifier 原因。声明成功时必须有对应绑定和评分证据。
7. 按发布合同核对该状态应有的日志、轨迹和录像；缺视频的成功记录不能默认为全部交付齐全。媒体缺失与评分失败分开呈现。

拟输出三种独立结论：`records_accounted_for`（全部计划项及 attempts 已列明）、`evaluation_complete`（每项都有合同接受的有效终态）、`delivery_complete`（要求的证据文件已交齐）。传输校验通过另记 `archive_integrity`。部分证据允许接收，但不能显示为完整实验。

当前 `helper_assignment.COMPLETE` 包含 `not_evaluable`，所以既有 helper 的 `evaluation_complete` 比上述严格定义宽。新标准格式须明确 schema 和统计口径；`not_evaluable` 默认不满足完整评测，除非派单事先明确允许。不能悄悄重解释旧 bundle。

### 3.3 复用哪些代码

- [collect_batch_results.py](../../scripts/collect_batch_results.py) 已检查完成时间、账号错误、reward、standard finalized，并按 manifest 保留 pending。
- 但它的 `classify_trial` 要求一个 job 恰好一个 trial，多个会得到 `invalid_job`。应提取“单 trial 分类器”，再增加 native batch 的 K 次重复映射。
- [check_topogym_trial.py](../../scripts/check_topogym_trial.py) 适合预期分数已知的 nop/oracle 冒烟，也要求单 trial；不能直接作为任意模型 batch 检查器。
- 缓存的 `rcb/main` 已有 `.plan/<batch>.json` 和 `live_board.py`，可以借鉴 pending 展示；该 plan 没有完整 K/身份锁，且会在启动时改写，不能直接充当不可变派单证明。

拟新增命令形态如下，尚不可执行：

```bash
# 拟新增：既由 runner 在收尾时调用，也供接收端重算。
python3 scripts/check_agent_batch.py --jobs "$JOBS" --batch "$B" --require-complete
```

原文循环可以保留为快速查看，正式验收读取严格检查结果。checker 应提供 JSON 和 Markdown：计划数、各类终态数、未开始、缺失、额外项及所有重跑关系。退出码区分完整、未完成和无法验证。

## 4. sibling agents_mirror 是什么

“sibling”只表示同级目录；正式目录名是复数 `agents_mirror`，不是一个额外 agent 或 lane。

```text
jobs/
  agents/
    B-privileged-task/
      task__trial-id/agent/codex.txt
      task__trial-id/verifier/reward.json
  agents_mirror/
    B-privileged-task/
      task__trial-id/agent/codex.txt
      task__trial-id/agent/session.json.v0
      task__trial-id/agent/session.json.v1
```

agent 可以写自己的 `agent/` 日志目录。宿主侧独立 mirror 保存观察到的追加内容、替换/截断事件和文件版本，避免只剩最后一版记录。它只镜像 agent 记录，不是完整 job 备份，也不是 Docker image。轮询镜像不能保证捕捉两次轮询之间所有瞬时变化，root-owned 也不是对拥有宿主 root/Docker 权限者的密码学防篡改证明。

当前问题有四个：全局容器名 `rcb-log-mirror` 可能对应另一个 workspace；启动失败只警告；没有按多 lane 生命周期执行可靠 final flush；扫描 `$JOBS` 不覆盖 sibling mirror。runner 末尾有一次 mirror 只读扫描，但不能替代最后封包前的同步、脱敏和复扫。原 tar 也没有收录 mirror 根目录的事件日志。

**拟定修复：**复用 [helper_runtime.py](../../scripts/helper_runtime.py) 的归属、ready/健康检查和最终同步，管理整个 batch 的 lanes。原始 mirror 在私有受保护位置继续保留；收尾时生成完整、可读、已脱敏的交付副本到标准 `agents_mirror/<job>/`，保留所有版本和分段名称。不能一边追加一边封包，也不能通过删掉含密钥的历史版本伪装完整。

这个原始镜像与交付副本的分离适用于新运行，既有 mirror 不原地搬迁。最终扫描对原文 `$JOBS` 入口识别配套交付 mirror，并扫描真正会上传的集合；显式要求的 mirror 不可读或不完整时阻止交付。跨 batch 的根事件按原记录内容引用/归档到对应的批次 sidecar，避免漏收或夹带其他批次。

## 5. 批次身份记录是什么，当前究竟有没有

可以把它理解为“这批结果的实验规格和来历”：本来派了什么、实际用了什么、每份结果属于哪一次执行。它不包含密码或 token。

| 层次 | 回答的问题 | 当前实现 |
| --- | --- | --- |
| Release 身份 | 哪份源码、公共工具、镜像配方？ | `topogym_versions.identity()`、每包 `task_release.json` |
| 实例/包身份 | 哪个 seed、参数、资产、运行镜像？ | `instance.json`、`runtime_binding.json`、包哈希 |
| 派单身份 | 这个 batch 要跑哪些 trial，用什么模型和预算？ | difficulty 的 `assignment.json`、manifest、execution lock；旧 batch 缺少同等完整的锁 |
| 执行事实 | 哪台机器、哪个 lane、时间、实际 GPU/镜像、异常？ | difficulty 的 helper runtime 和 image/controller 记录；旧 batch 分散在日志及 Harbor 输出 |
| 交付身份 | 发回哪些文件、各自哈希、是否完整？ | 自定义 helper bundle 的 inventory、BUNDLE 和回执；标准 tar 只有整体 checksum |

旧 batch 在启动检查成功后调用 `freeze-run`，写入 `$JOBS/$B.release.json`，锁定 release 和选定包。因此是“有实现，但旧 batch 记录范围不足，且标准打包漏收”。它没有锁定所有模型参数、K 和预算策略，也不能单独证明维护方派过这张单。当前启动被 release 阻断时，自然还不会生成本批这份记录。

原文 tar 的通配符是 `agents/"$B"-*`，匹配 `B-...`，不匹配 `B.release.json`。它另外只点名了 `B.log` 和 `B.summary.md`。`supervision/`、`.plan/` 中的文件也不会自动进入包。

为了保留原文命令，拟把新批次交付记录放为 **普通文件**：

```text
jobs/agents/
  B-plan.json
  B-metadata.json
  B-verdicts.json
  B-inventory.json
  B-MANIFEST.md
  B.log
  B.summary.md
  B-privileged-task/...
  B-standard-task/...
```

这些 `B-*` 文件能被原 tar 收录，又不会被原文带尾部 `/` 的 verdict 循环误当作 job 目录。网站 importer 必须只把包含 Harbor job 结构的目录当作 job，是否已有过滤需要看真实网站代码。identity 里的绝对路径仅作溯源；接收端依靠发布 commit、相对任务名和 digest 定位，不能依赖 helper 的原目录。

inventory 应明确收录集合、文件大小和内容哈希，排除自身哈希递归；它的摘要放入外部交付记录。维护方用自己保存的派单比对，不能仅验证 helper 同时发送的内容和自算摘要就视为派单真实。

原文 `B-*` 还会匹配 `B-rerun-*`，也可能匹配另一个以 `B-` 开头的无关 batch。启动、收尾和接收时须核对确切 job 集合及允许的 rerun，不能仅凭前缀认定归属。

## 6. MANIFEST 目前自动化到什么程度

原文的 `MANIFEST.md` 是给人阅读的交接单，字段包括 helper、repo、主机、软件、镜像、agent、lanes/GPUs、起止时间、异常。它与机器读取的采样 manifest 不是同一份文件。

| 字段 | 当前自动化情况 | 标准 batch 需要补齐 |
| --- | --- | --- |
| helper、batch、派单/源码身份 | assignment 和 bundle 摘要已有 | 接入 native batch 的派单 |
| CPU、内存、系统、Docker、GPU 名称/driver | Docker launcher 已写 `host-info.tsv` | batch 宿主采集；不能把 controller 信息冒充宿主信息 |
| 起止时间、认证类型、运行异常类型 | `helper_runtime.record()` 已记录 invocation | 支持多个 lane、signal/崩溃恢复和完整时间线 |
| 镜像 | image/controller/environment-check 记录实际镜像及 ID | 汇总 agent、sim、verifier 等实际角色；本地镜像没有 RepoDigest 时明确记录 Id |
| Harbor/Codex/Python/CUDA | 一部分在 build-info、镜像或预检记录 | 同时记录期望版本与实际版本；区分驱动支持的 CUDA 和镜像运行库版本 |
| lanes/GPUs | 当前 helper runtime 固定 lane_count=1 | 从每个 lane 的真实启动记录计算；记录 UUID/主机映射 |
| 异常事件 | 有 attempts、resource-stop、部分错误和日志 | 汇总结构化事件，允许 helper 补充停电/断网等人工备注；未知不能写“无异常” |

[helper_bundle.human_manifest](../../scripts/helper_bundle.py) 当前确实会生成 `MANIFEST.md`，但主要是 batch、来源、agent 和完整性摘要；主机/软件/时间/事件指向包内 `delivery/helper_manifest.json` 和其他文件，**没有把原文每一项都自动展开填全**。旧 batch 也没有接入该生成器。

P5 拟由统一的结构化 metadata 渲染原文同款 MANIFEST，生成在 `B-MANIFEST.md`，helper 整理上传目录时复制为 `MANIFEST.md`。机器字段自动填写，人工备注单独追加并注明来源；缺失关键字段时报告 unknown/采集错误，不编造版本或结束时间。checksum 不能代替这些说明。

## 7. HF 上传需要什么

变量名是 `HF_TOKEN`。如果目标已建好、helper 有网络、CLI 已安装，**认证不需要另加用户名/密码或再做交互登录**：CLI 可直接读取该环境变量。依据：[HF 环境变量](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables)。

但上传还需要四个明确输入：有权限的 `<org>/<dataset>`、`helpers/<helper>/<batch>` 路径、本地 `upload_<batch>` 目录，以及对目标有写权限的 token。组织权限和 token 权限共同决定是否可写。依据：[HF token 权限](https://huggingface.co/docs/hub/security-tokens)。

维护方预先创建并确认目标 dataset 为 private，再发目标和 token。普通 `hf upload ... --repo-type dataset` 不等于强制私有；官方 CLI 还可能为不存在的目标创建 repo，不能把 private 状态留给默认行为。命令格式见 [HF CLI](https://huggingface.co/docs/huggingface_hub/main/guides/cli)。

原文上传命令可以保留；`HF_TOKEN` 只提供给上传进程，不放到 rollout 环境或归档里。当前自定义 [helper_upload.py](../../scripts/helper_upload.py) 已有私有目标检查、远端哈希核对、重试和回执，但读取的是自定义 bundle/assignment；还不能用来验证原文普通 tar。

P5 复用其校验能力到标准归档：上传前核对派单中的目标与 private 状态，上传后由接收方下载这三个文件并验证 checksum/完整性，记录远端 revision。CLI 返回成功只是传输步骤完成，不代表模型跑完或网站已导入。共享文件夹路径使用相同三文件和接收检查。

本轮未使用真实 HF token，也未向外部上传文件。

## 8. 实验网站怎样接通

这里指原文已有的 review site，不新建另一个展示网站。当前 TopoGym、本地 RCB checkout、上述分支树中，未找到 `docs/contributing/registering-runs.md`、`data/runs/hosts.*.local.yml`、`state/runs/<benchmark>.yml` 及对应 `make runs` 实现。用户已决定先跳过这一部分，无需等待网站仓库才能继续。以下接通步骤仅作为未来取得代码后的工作边界，不是本轮执行项。

`rcb/main` 有 `scripts/live_board.py`，是直接看 jobs 的本地进度面板，不能据此认定原文 review site 已存在于本仓库。当前 `helper_import.py` 的 Markdown 和 `site-input.json` 也不等于网站注册已经完成。

接通需要两端分别完成：

1. **TopoGym 接收端：**校验 archive 与维护方派单，解包为 `~/rcb_helper_runs/<helper>/jobs/agents` 和 sibling mirror；保留收到的原始字节，生成独立验收回执。解包器预检路径、链接和重复成员，不能把 checksum 当作路径安全验证。
2. **任务定位：**接收端取得对应发布 commit 的任务树，以相对 task 名和 digest 匹配；不重写原 `result.json` 的历史绝对路径。没有模型凭据或 GPU，也应能读取所有原始结果。需要重新物理评分是另一项明确的操作。
3. **网站 host：**按实际 schema 写 gitignored 的 `hosts.<helper>.local.yml`，映射到上述 `agents/`。
4. **网站 batch：**向 `state/runs/<benchmark>.yml` 注册主 batch、授权 rerun、模型和模式；具体键名以网站实现为准，不能依据文本猜一份可运行 YAML。
5. **读取适配：**确认 importer 能发现所有 K 次 trial，能识别两种模式/额外 sidecar，能显示 pending/infra/不完整；接入 batch checker 输出。审核标准日志、privileged 提交、standard finalization、verifier 判定、录像及 mirror。
6. **页面重建：**在网站实际环境运行 `make runs RUNS="--benchmark <benchmark>"`，逐项对照计划数和文件链接。重复导入应幂等，新补交或重跑不能覆盖已接收的旧证据。

网站验收样例至少包括：正常成功、正常失败、非法提交、未启动、infra failure、K 次重复、原批次加 rerun，以及缺视频。主机 A 的原路径必须在接收主机 B 上不可访问。完整性和失败原因应与离线 checker 一致。

本轮继续开发 package 发布、batch 认证、完整性检查和标准归档读取器；网站项明确标为“按用户决定暂缓”，不计入本轮完成门槛，也不标成已接通。

## 9. 需要一起修复的其他衔接问题

| 问题 | 影响 | 修复归属 |
| --- | --- | --- |
| difficulty prepare 的结果未登记到 native batch catalog | task-base 不能直接启动 | P1 |
| prepare 的 Docker compose 固定准备机 GPU UUID/UID 和 controller 标签 | 包搬到其他主机可能启动失败或归属错误 | P1/P2：冻结任务内容；主机参数由有记录的部署覆盖层提供，不改实验参数 |
| batch 默认依赖私有 Python venv，Harbor 来源不固定 | 干净 clone 不可复现；刷新 patch 可能不存在 | P2 |
| `freeze-run` 没锁 K、完整 agent 配置及预期 trial | 同名 batch 的 lane 可能使用不同设置 | P3：启动前一致性检查，规范模式别名后锁定 |
| 把 job/result.json 存在当作已处理 | 中断 job 会跳过，不能据此报告完成 | P3：保留跳过保护，严格报告 incomplete，授权重跑到 B-rerun |
| runner 文案要求移动目录/claim 后重跑 | 与 helper 文档“不得移动记录”冲突 | P3：改文案和恢复入口；旧 claim/目录保留 |
| 多 lane 的 summary 是各进程读取快照后覆盖 | 原子 rename 防半写，但不能保证最后写入的是最新完整状态 | P3：结束时统一锁下重算，原始事实为准 |
| 部分失败只停止当前 lane，其他 lane 可能继续烧预算 | 账号/配置错误造成整批失败 | P2/P3：共享批次停止原因，保留每 lane 退出码 |
| `RESULTS=` 的 shell 函数返回值 | 当前 `finish_job` 的末尾条件表达式可返回 1，把“关闭可选报告”误判成失败 | P3：显式区分跳过报告与报告错误，补针对性测试 |
| per-task Markdown 的路径不含 K 的 repetition | 多个 trial 会写到同一报告位置，不能代表全部 K 个结果 | P3/P6：逐 trial 页面及索引；以原始 jobs 为接收来源 |
| 当前脚本与缓存 main 有差异 | main 已默认禁用 harness web search，并有额外 gateway/plan 功能；不能说完全对齐 | P2：逐项审查所需官方运行设置并固定；不整份覆盖资源保护和版本检查 |
| root-owned mirror、全局名称、缺最终同步与漏扫描 | 归档失败、漏记录或残留凭据 | P4 |
| 标准 tar 漏 release/supervision/mirror 根事件 | 来历和异常证据不完整 | P3/P4/P5：可归档的 batch sidecar 和精确 inventory |
| 自定义 helper import 与普通 tar 不同协议 | 不能用旧 `helper import` 直接接收标准 tar | P5/P6：显式格式读取器，共享底层验证；不改历史包 |
| 工作区新文件尚未全部进入 commit | helper checkout 得不到当前实现 | P7：冻结交付 commit，干净 clone 验收 |
| 现有 release 回归有提示文字断言不匹配 | 测试不是全绿 | P3：修正错误合同或断言并复跑，不能忽略失败 |

这里“修复原文命令”不表示需要照搬原文不充分的语义。保留启动、扫描、归档和上传入口；在内部增加严格校验。原 verdict 循环无法靠 shell 通配符推导缺失的计划项，应保留为粗检查，并在文档明确正式完整性以 batch checker 为准。

## 10. 工程实施顺序与验收门槛

| 阶段 | 主要交付 | 完成标准 |
| --- | --- | --- |
| P0 固定合同 | 版本化批次 schema；明确 sidecar 与 native jobs 的识别规则 | 普通 agents tar 的本地读取小样通过；网站 schema 探针按用户决定暂缓 |
| P1 发布 sampled 任务包 | 复用 sampler、prepare、preflight；根 tasks 发布、dataset digest、runtime catalog、相对资源检查 | 从干净 clone 找到所有派单包；包/seed/镜像一致；改错任何身份启动即失败；不回退 v14 |
| P2 运行环境与认证 | 保留 batch CLI 的 bootstrap；共用凭据解析；固定 Harbor/Codex；认证检查、canary、GPU 部署配置 | 无私有 venv 可安装启动；订阅/API 路径明确；刷新及多 lane 策略通过；HF token 不进入任务进程 |
| P3 计划、调度与 verdict | 不可变 plan；单 trial 分类器；K/重跑映射；严格 checker；全批停止/收尾状态 | 预期数可核对；中断/未开始/重复不丢；有效失败计完成；infra 不计完成；两 lane 不重复认领 |
| P4 mirror 与最终扫描 | 独立归属 mirror、最终同步、交付副本、真实归档集合扫描与脱敏记录 | root-only 原记录仍保留；所有历史版本纳入扫描；含合成密钥/不可读/仍写入时阻断封包 |
| P5 标准归档和 MANIFEST/HF | B-* sidecar；完整 MANIFEST；普通 tar 校验器；HF 目标核对与接收回执 | 逐字运行原扫描/tar/sha 命令可交付；三文件字段齐全；partial 明示；下载后哈希一致 |
| P6 异机离线接收 | 普通 tar 安全读取、任务定位、验收回执及完整审查索引 | 原路径不可访问、无需模型/GPU可审查全部 trials；计数/状态/文件链接与 checker 一致；重复导入无覆盖 |
| P7 真机放行 | 固定发布 commit、原文命令逐项操作手册、独立机器全流程证据 | 真实 prepare/preflight、nop、agent、传输和离线接收通过；明确网站暂缓及其他限制 |
| P8 网站接通（暂缓） | 实际网站 schema 核对、host/batch 注册、网站 adapter 和页面重建 | 取得真实网站代码后恢复；页面与离线 checker 的数目、状态和证据链接一致 |

P1 与 P2 可独立推进；P3 依赖派单和任务身份合同；P4/P5 需要 P3 的生命周期和文件集合；P6/P7 完成异机离线闭环，P8 暂缓且不阻塞前面阶段。实现期间复用成熟模块，不维护两套不同的评分规则或密钥扫描逻辑。

维护方负责生成和批准任务清单、构建发布包、规定模型和预算。helper 负责主机/凭据准备、按命令运行、补充真实异常说明和交付。接收方负责独立验包、重算完整性和网站注册。helper 不修改 task、预算或失败历史。

### 10.1 可立即做的 CPU 验证

已有隔离测试复用了真实 sampler、release guard、原版 batch、scanner 和 tar，Docker/Harbor 与运行包为替身/夹具：3 难度 × 2 seed × 2 模式产生 12 jobs；两 lane、K=2 得到 24 份测试 verdict；无重复认领，重启不重跑。还复现了 catalog 缺失、23/24 漏检、mirror 漏扫描、release sidecar 漏打包和普通 tar 导入不兼容。

证据：[标准命令测试](../../runs/test_results/standard_helper_pipeline_audit_20261004_153137/summary.json)、[分支与 dataset 名称核对](../../runs/test_results/standard_helper_plan_audit_20261004_154405/summary.json)。这些不是 GPU、模型或网站成功证据。

新增测试围绕真实风险：K 缺一份；计划 job 完全缺失；成功 reward 配错误 runtime；JSON 损坏；结果值冲突；两 lane 不同配置；异常停机后 claim 保留；授权 rerun 不覆盖旧包；原始目录已不存在；扫描遗漏历史 token；root-only mirror；额外前缀 batch；tar 路径穿越；HF 远端已有不同字节。文档修改本身只需链接、命令块语法和事实校对。

### 10.2 真机与另一台机器的验收

先用 Cast Coil easy、2 个 seed、双模式、K=1，共 4 个正式计划 trial。维护方在候选上完成真实 prepare/preflight，并直接使用 Harbor nop 做无模型的容器/verifier 接线检查；旧 batch 只接受 codex/claude-code，不能直接设置 `AGENT=nop`。

随后 helper 在干净 clone 上按原文运行真实 agent，先单 lane 验证，再在资源足够且 GPU 分配明确时验两 lane。模型没有解题成功也可以验证交付链路；应如实保留 0 分，另用经过验证的成功样本检查成功记录/录像的接收展示。

将 archive、checksum 和 MANIFEST 交给另一台机器，断开对原 helper 路径的依赖。接收端校验数量、身份、终态、媒体和 mirror，生成逐 trial 的离线审查索引。实际网站注册与重建留到 P8。单台机器另建目录只能作为搬迁测试，不能叫独立主机验收。

所有实际运行记录源码/配置身份、CPU 和内存。CPU 仅监控；系统内存达到 90% 时停止本轮拥有的工作，不终止其他会话。运行证据保留在 `runs/test_results/`；正式 helper 原始记录不得删除或移动。

## 11. 原 helper 命令的逐项承接

| 原文命令或动作 | 新标准流程如何承接 | 当前状态 |
| --- | --- | --- |
| `git clone ... && cd ... && git checkout <commit>` | commit 提供 tasks/catalog/runner；安装固定依赖和指定镜像 | P1/P2/P7 待完成 |
| `export JOBS=$PWD/jobs/agents`、`B=...` | 原样保留；派单核对 batch | runner 已支持，派单待接 |
| `sed -n 2,45p scripts/run_agent_batch.sh` | 头部列真实配置、版本、认证和 lane 限制 | 需随 P2 更新 |
| `AGENT=... MODEL=... EFFORT=... ENV_FILE=... nohup scripts/run_agent_batch.sh ...` | 原样保留 public CLI；内部执行预检、计划锁、原生 Harbor | 调度已有，P1/P2/P3 待接 |
| 同命令再启动一个 lane | 共享 batch 身份与 claims，记录实际 GPU/认证 profile | claim 已有，认证/收尾待补 |
| verdict 的 `for d in ...` | 保留粗检查；正式 verdict checker 自动生成准确状态 | 粗检查已有，P3 待补 |
| 两次 `python3 scripts/scan_secrets.py "$JOBS" ...` | 覆盖实际凭据来源及交付 mirror，扫描失败非零退出 | scanner 核心已有，P2/P4 待接 |
| `H=...; cd "$(dirname "$JOBS")"; tar ...; sha256sum ...` | 保留布局和参数；B-* sidecar 全部收录，收尾后再归档 | tar 可用，P4/P5 待补 |
| `git rev-parse HEAD; nvidia-smi ...; docker --version; harbor --version` | 保留人工核对；MANIFEST 自动展示已采集字段 | 部分采集已有，P5 待接 |
| `docker image inspect --format '{{index .RepoDigests 0}} {{.Id}}' <image>` | 自动记录所有角色镜像；空 RepoDigests 也有明确 Id | 需完善本地镜像空 digest 情况 |
| 整理 `upload_<batch>/` 下三个文件 | 自动生成 manifest 内容与封包清单，保留人工备注 | 自定义 bundle 已有，标准 tar 待接 |
| `pip install -U huggingface_hub`、`HF_TOKEN=... hf upload ... --repo-type dataset` | 保留 CLI 传输；固定已验收版本、确认私有目的地及写权限 | 外部 CLI 支持；标准归档远端验收待做 |
| 共享文件夹上传、告知 batch/文件名/checksum | 同一三文件协议；传输结果与实验完整性分别记录 | 人工步骤；不会自动替 helper 发消息 |
| 接收端 `sha256sum -c ...`、`mkdir -p ... && tar -xzf ...` | 保留标准路径；先预检归档，再验派单及内容 | 外部命令可用，严格标准读取器待接 |
| hosts 配置、state/runs 注册、`make runs RUNS="--benchmark ..."` | 后续实际网站 adapter 接入原生 jobs | 按用户决定暂缓到 P8，不阻塞本轮离线验收 |

原文在打包前已 `cd` 到 jobs 父目录，之后直接 `git rev-parse HEAD` 是否仍在 Git 工作树内取决于 JOBS 的位置；上传目录的相对路径也受当前目录影响。正式手册应让自动 metadata 记录 repo 根，并明确每段命令的工作目录，不以恰好在仓库内作为保证。

本轮计划的放行判据是：helper 在指定 commit 的干净环境中，按照标准说明完成运行和交付；维护方在另一台机器上逐项离线验收全部计划 trials。实际 review site 接通暂缓。CPU 合同测试、普通 tar 能解开、HF 上传成功都只证明其中一个环节。
