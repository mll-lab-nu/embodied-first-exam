# Difficulty Eval：Docker 启动

入口默认使用 Docker。宿主不需要安装 Python、Harbor、Codex、Node 或项目虚拟环境。需要 Linux x86_64、可访问的本机 Docker Engine/CLI（含 Buildx）、NVIDIA 驱动与已配置的 NVIDIA Container Toolkit，以及可访问依赖源/模型服务的网络。首版不支持远程 daemon、rootless 或 Docker Desktop。

运行配方提供 `cu128`（默认）和 `cu130` 两套配置，均使用 torch 2.11 / torchvision 0.26，并补编译原始 pyuipc 0.0.25，包含 `sm_89` / `sm_120` 内核。`cu130` 面向采用 R580+ 驱动的 Blackwell 等新机器；`cu128` 同样以 Blackwell 为编译目标。两套构建与实机验收状态见 [Blackwell 工程计划](cuda_blackwell_delivery_plan_zh.md#10-双-cuda-配置实施)。配置存在不等于 RTX PRO 6000 实机已验收。

在仓库根目录运行；源码归档不需要 `.git`。默认在**启动命令时的当前目录**创建 `topogym-work`。所有实验数据保存在该目录，脚本会打印绝对路径；用 `--work-dir /data/topogym-work` 可覆盖。

下列默认命令使用 `cu128`。RTX PRO 6000 Blackwell 的 `cu130` 候选配置：检查时用 `check --cuda-flavor cu130`，实验命令中也加 `--cuda-flavor cu130`，并使用新的 run ID（例如 `luna-all-tasks-cu130`）。订阅登录共用，不需要重复。选择会同时决定编译镜像、IPC wheel 和运行依赖锁；不能对同一个 run ID 切换 CUDA 配置。宿主驱动低于 R580 时会停止；脚本不自动升级宿主驱动。

首次使用需要从源码编译 IPC，预计每套约 30–90 分钟；网络或无依赖缓存时可能更长。后续相同配方复用本机镜像缓存，选用另一套配置会另建镜像。

```bash
# 可选：检查 Docker、共享路径、权限、CUDA/Vulkan、机器人与视觉资产；不调用模型。
# 首次执行会自动构建所需镜像；all 本身也执行这些检查。
bash bash_scripts/run_difficulty_trials.sh check

# 首次订阅登录：在容器内执行，按终端提示完成浏览器授权。
bash bash_scripts/run_difficulty_trials.sh auth login --device-auth

# 全部 13 个任务 × 三难度 × 每档一个样本 × 两种模式 = 78 个正式 trials。
# 每个 trial 的 agent 阶段最多 6 小时。
bash bash_scripts/run_difficulty_trials.sh \
  --phase all --run-id luna-all-tasks \
  --tasks 1-13 --samples-per-difficulty 1 \
  --agent-wall-clock-s 21600 \
  --auth subscription --agent codex --model openai/gpt-6-luna \
  --agent-arg version=0.157.0 --agent-arg reasoning_effort=max
```

上例显式写出默认值：全部 13 个任务、每难度 1 个样本、单个 agent 阶段 21600 秒（6 小时）；省略这些选项时使用相同设置。`--samples-per-difficulty` 支持覆盖为 3、5 等。固定 easy/medium/hard 和 unlimited/limited；认证 canary 独立于正式 trial 数。6 小时不是整个实验的总时限，镜像构建、初始化、预检、收集和评分另计。仅做短试跑时，可改为 `--tasks 8,9 --agent-wall-clock-s 432`，对应 Cast Coil 和 Cast Keyhole，共 12 个正式 trials。

首次构建需要下载依赖和资产，进度与日志位置会显示在终端。以后复用按输入哈希标识的镜像；更换任务子集、抽样 seed 或样本数不重新安装基础依赖。运行时全部所选实例通过 prepare/preflight 后才会启动模型。

当前源码生成的新实验对七类纯刚体任务的 easy/medium/hard 统一启用接触辅助抓持 `contact_weld_v1`：Lock Picking、Interlocked Claws、Buzz Wire、Cast Coil、Cast Keyhole、Hedgehog、Horseshoe。Fiber 按柔性线缆处理，与 Blanket、Knot、Rope Threading、Orbits、Slotted Post Ring 一起保持 assist 关闭。此设置作用于模型评测的 limited/unlimited，两种模式共享 `instance.json` 中的 `simulator.grasp_assist`。辅助抓持仍要求真实双指接触；张开夹爪解除约束，任务的释放、碰撞和成功条件继续生效。

采用此更新须使用新源码／控制镜像和新的 run ID，由 prepare 重新生成实例和任务说明。已冻结的实例、旧镜像和 `--resume` 实验保留原配置；不能只修改 instruction 或沿用旧 describe.json 来开启 assist。新配置的接入不表示所有难度均已获得完整解题成功证明。

API 模式使用自己的 key 和模型名，不需要订阅登录，也不必配置环境变量：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase all --run-id api-all-tasks \
  --tasks 1-13 --samples-per-difficulty 1 \
  --agent-wall-clock-s 21600 \
  --agent codex --model '<model-id>' --api-key
```

`--api-key` 不带值时在终端隐藏输入；也接受显式值、`--env-file` 和 `--api-key-env`。显式 key 可能出现在调用方 shell 历史与进程参数中；启动器不把它加入 Docker 的 `Config.Cmd` / `Config.Env`。启动参数与选中的凭据通过临时私有目录只读挂载，退出后清理。`--env-file` 按数据解析，不执行 shell 内容。

订阅登录保存在 `${XDG_CONFIG_HOME:-$HOME/.config}/topogym/codex`，可用 `TOPOGYM_AUTH_DIR` 覆盖；它独立于 work-dir。`auth status` 查看登录状态。`--auth-json /path/auth.json` 将现有登录只读导入工具管理的私有存储，不修改原文件。控制器序列化同一用户的订阅实验，保留 agent 刷新后的 token；当前 Harbor 0.23.0 的这项小补丁在镜像构建时按源码 SHA 校验，不修改宿主 Harbor。

结果位置：

- `topogym-work/runs/difficulty_trials/<run-id>/`：manifest、源码/镜像身份、任务包、逐实例日志、summary。
- `topogym-work/jobs/difficulty_trials/<run-id>/`：原始 Harbor jobs、评分与录像。
- `topogym-work/logs/`：控制器、环境检查和镜像构建日志。
- `topogym-work/check.json`：最近一次环境检查状态；旧检查记录保留。

恢复使用相同 work-dir、run-id、发行版本及实验配置，追加 `--resume`。需要为中断/基础设施失败创建新 attempt 时，再加 `--rerun-incomplete`；旧证据保留。切换启动目录时，显式传入原 work-dir 的绝对路径。升级源码后不要直接恢复旧 run：使用原源码包或 `--controller-image sha256:<原控制镜像ID>`。镜像必须还在本机；发布镜像可使用 `--controller-image registry/name@sha256:<digest>`。

`--gpu-device 0` 是默认 GPU，可指定其他宿主索引或 `GPU-...` UUID。控制器将其解析为 UUID，统一用于准备、仿真和评分；daemon 内的 GPU 锁覆盖不同 work-dir。Ctrl-C/TERM 会停止本次工作并保留证据；强杀或主机重启后，下次启动核对失效 owner，仅回收它标记的工作容器和网络。控制容器挂载 Docker socket，具有宿主 Docker 管理能力；只运行可信发行代码。agent/sim/verifier 不挂载该 socket。

仅查看任务列表或生成计划也走容器，但不需要 GPU 或运行镜像：

```bash
bash bash_scripts/run_difficulty_trials.sh --list-tasks
bash bash_scripts/run_difficulty_trials.sh --phase plan --run-id sample-plan
```

已有控制镜像时，也可直接调用 Docker。下面是无模型、无 GPU 的计划生成示例；镜像 ID 可从构建日志或 run 的 `controller.json` 获取：

```bash
RAW_EVAL_WORK_DIR="$PWD/topogym-work"
mkdir -p "$RAW_EVAL_WORK_DIR"
docker run --rm --init --stop-timeout 180 \
  --name topogym-controller-manual \
  --user "$(id -u):$(id -g)" --group-add "$(stat -c %g /var/run/docker.sock)" \
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
  --mount type=bind,src=/proc,dst=/host/proc,readonly \
  --mount "type=bind,src=$RAW_EVAL_WORK_DIR,dst=$RAW_EVAL_WORK_DIR" \
  -e HOME=/tmp/topogym-home -e TOPOGYM_CONTROLLER=topogym-controller-manual \
  'sha256:<控制镜像ID>' \
  --phase plan --run-id raw-docker-plan --work-dir "$RAW_EVAL_WORK_DIR"
```

正式实验推荐统一 Bash 入口，它同时处理 GPU、凭据和信号转发等启动细节。上面的原生示例仅生成计划。

开发者可显式用 `--backend local` 保留旧宿主环境与 `runs/`、`jobs/` 布局，或直接运行 `scripts/difficulty_eval.py`。Docker 出错时不会自动切回本地环境。

维护方使用 `python scripts/difficulty_release.py bundle --output /path/topogym-source.tar.gz` 生成带固定配方和依赖锁的源码发行包。解压后运行根目录 `run_difficulty_trials.sh`，参数与仓库版相同。此命令不推送镜像；Nyx 镜像的现有发布限制保留。公开镜像还需要维护方明确分发条件、推送后记录真实 digest；当前本地镜像不代表已对外发布。有固定控制镜像时，最小启动包只需 `run_difficulty_trials.sh` 和一行镜像引用的 `controller-image.txt`；可另附 `release.lock.json` 固定全部已发布运行镜像。没有 release.lock 时，控制镜像携带配方并自动构建运行镜像。

环境 `check`、CPU 测试和两个任务的试跑覆盖不同范围。全任务物理预检、真实订阅/API 工具调用与轨迹评分，以及独立新机器的冷启动结果，须分别有证据才能宣称验收完成；参见 [交付实施计划](difficulty_sweep_delivery_plan_zh.md)。

资源保护按系统内存占用执行：达到 90% 时停止本次工作并保留证据；CPU 即使超过 90% 也继续运行，只记录使用情况。

## 上传结果到私有 HF dataset

在原评测命令后添加 `--results_to_hf`，默认提交到 `LGVamper/toponym_evaluation_results`。已支持的别名为 `--results-to-hf`。token 通过 `HF_TOKEN` 环境变量或 `--hf-token-file` 注入，不需要 HF CLI、登录或人工确认；账号必须对目标 dataset 有写权限。

推荐使用仓库根目录的 `.secrets/hf-token`：文件中只放 token 本身一行，不写 `export`、变量名或引号，并执行 `chmod 600 .secrets/hf-token`。本次本机实施已准备该空文件；其他机器自行创建。也可将文件放在仓库外。不要将凭据文件放进 scripts 等源码目录：源码会被冻结和构建进镜像，入口会拒绝这类位置。`.secrets/` 已被 Git、源码发行清单和镜像构建白名单排除。

运行示例沿用你选择的模型参数：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --run-id difficulty-hf-20260930 \
  --auth api-key --model '<model-id>' --api-key \
  --results_to_hf --hf-token-file "$PWD/.secrets/hf-token"
```

这里 `--api-key` 是模型凭据，HF token 是另一份凭据。已有模型配置时只追加最后一行的两个选项即可。使用环境变量 HF_TOKEN 时省略 `--hf-token-file`；指定其他变量用 `--hf-token-env VARIABLE_NAME`。两个显式凭据来源参数互斥，指定来源无效时直接报错，不切换账号或提示登录。Docker 通过私有临时文件只读接收 token，退出清理临时副本，不将其放入容器 Config.Env 或传给 agent/sim/verifier。

上传默认包含指标、评分、已收集的视频和轨迹；`--hf-artifacts metrics` 只传指标和评分。远端按 `日期/run-id--UUID/task/difficulty/seed_x/mode/trial_01/attempt_001/` 隔离；同一发布身份锁定仓库、日期和 artifact 模式。更换 token 不改变实验身份。

对已有结果离线预览，无需 token、HF SDK 或 GPU：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase upload --run-id '<已有 run-id>' --work-dir /data/topogym-work \
  --results_to_hf --hf-dry-run
```

单独补传，无需模型凭据或重新运行实验：

```bash
bash bash_scripts/run_difficulty_trials.sh \
  --phase upload --run-id '<已有 run-id>' --work-dir /data/topogym-work \
  --results_to_hf --hf-token-file "$PWD/.secrets/hf-token"
```

历史 run 可以使用新控制器进行 upload；它验证保存的 manifest 与收集结果，不加载旧模拟器或要求原 release。若尚无 `trials.jsonl`，先在匹配的原环境执行 `--phase collect --resume`。local 后端使用相同参数和原工作目录，实际上传要求该 Python 环境安装 `huggingface-hub==1.33.0`；Docker 镜像已锁定此依赖。已存在的旧控制镜像不会自动获得新功能，需使用本次源码构建的新镜像。

若历史 unlimited 结果漏收 `trajectory.npz`，在该 run 已停止后，从当前仓库直接运行新版收集器：

```bash
.venv-gs121-nyx/bin/python scripts/collect_batch_results.py \
  --manifest '/data/topogym-work/runs/difficulty_trials/<run-id>/manifest.lock.json' \
  --jobs-dir '/data/topogym-work/jobs/difficulty_trials/<run-id>'
```

新版按模式取轨迹：unlimited 从 Harbor 的 `artifacts/app/output/trajectory.npz` 读取，limited 从 `verifier/trajectory.npz` 读取；奖励和回放视频仍取 verifier 产物。源文件或其目录是符号链接时不收集。只要原始 jobs 产物仍在，即可补齐本地 results 并供后续 HF standard 导出，无需重跑物理或模型。普通 `--phase collect` 加载 run 冻结的收集器，不会自动获得此修复；不要修改旧源码快照。此命令仅重新整理结果，不向 HF 写入，也不覆盖已发布的完成 attempt。

终端使用 `[hf-upload]` 显示权限检查、快照文件数/大小、远端复用数、传输批次、commit、重试和完成链接；长操作每 15 秒显示状态。SDK 未提供可靠字节进度时明确标注速率和 ETA 不可用。`hf_upload/upload.log`、`events.jsonl`、`state.json` 与 staging 位于原 run 下；日志不上传。完成标记提交前不会报告 Upload complete，且 evaluation_complete 与 upload_status 分别显示。

上传失败保留本地结果，打印补传命令；评测已正常完成而上传失败返回 3，评测自身已有非零码则保留其原码。pure upload 的成功只表示结果发布成功，不改变历史评测状态。补传先完成上次保留的上传快照；如本地结果又有更新，旧快照完成后再运行一次 upload 发布新版本。已发布完成 attempt 的证据不可覆盖。

首次 run/all 会提前验证 HF 写权限，凭据或网络不通时不启动昂贵评测。若先运行本地实验，可省略上传开关，完成后再补传。plan/prepare/preflight 和 dry run 不读取 HF 凭据。交互 `auth hf`、PR 投稿与持续增量上传仍为后续可选功能，当前首版使用显式凭据注入。
