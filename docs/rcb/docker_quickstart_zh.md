# Difficulty Eval：Docker 启动

入口默认使用 Docker。宿主不需要安装 Python、Harbor、Codex、Node 或项目虚拟环境。需要 Linux x86_64、可访问的本机 Docker Engine/CLI（含 Buildx）、NVIDIA 驱动与已配置的 NVIDIA Container Toolkit，以及可访问依赖源/模型服务的网络。首版不支持远程 daemon、rootless 或 Docker Desktop。

在仓库根目录运行；源码归档不需要 `.git`。默认在**启动命令时的当前目录**创建 `topogym-work`。所有实验数据保存在该目录，脚本会打印绝对路径；用 `--work-dir /data/topogym-work` 可覆盖。

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
