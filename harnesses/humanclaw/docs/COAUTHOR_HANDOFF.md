# Coauthor rollout handoff — 在另一台 GPU 服务器运行

核对日期：2026-10-15（America/Los_Angeles）。本指南面向有独立 Linux GPU
服务器的合作者，先跑通 `API + HumanCLAW`，再接收明确分配的评测任务。

## 1. 交接状态与正确版本

实验代码仓库是 `https://github.com/HenryLiu0405/HumanCLAW-PRO.git`，分支为
`codex/pipeline-evaluation`。核对时远端该分支为
`0f3d4731d5160005f6796995806b82af2f955671`；远端默认 `main` 仍为
`6323d938795afd27d66ab926216bf4ba7b003ee6`，不包含新增实验框架。
先确认自己的 GitHub 账号能够访问实验仓库。

| 内容 | 当前可交付范围 |
| --- | --- |
| HumanCLAW PSV | 已有真实 GPU episode 的完整运行、记录、指标和回放验证；新机器仍需验证自己的环境 |
| Codex / Pi | 适配层、统一事件和原始日志保留已提交；本机路径、原生运行时和服务器隔离配置需要另行部署 |
| Bare API | 使用 coauthor 已有外部结果；不要用仓库里的历史 `bare_api` 诊断入口代替 |
| 当前 1,218 例 fullval | 使用此前冻结的源码与配置；不能直接用最新分支的结果补入 |
| 跨服务器协作 | 支持传入 episode 清单；尚无跨服务器任务认领、结果同步与路径重定位的一键流程 |

**独立验证与接力当前 fullval 是两件事。** 下面的安装和单例命令用于验证新
服务器。正式接力须先完成第 6 节的版本和任务交接；未分配任务时不要启动
`--episodes fullval`。

当前 fullval 的 `snapshot_manifest.json` 标记了
`includes_uncommitted_changes: true`；仅 checkout 它的 `base_git_revision`
不能还原该快照。核对时，最新分支与冻结快照在 planner、公共动作转换、
evaluator、batch 等 8 个既有源码文件上不同，另有新增 native harness 文件。
这不证明行为必然不同，但源码身份不相同，现有严格匹配检查会拒绝直接合并。

## 2. 新服务器准备

需要 Linux、NVIDIA GPU、Python 3.10+（现有 Klone 环境使用 3.11）、CUDA
PyTorch、带指定补丁的 Habitat-Sim/Bullet、场景与运动权重，以及可访问的
模型 endpoint。只有 Python 包和 API key 还不能执行仿真。

以下命令假设从空目录安装。将 `/absolute/path/to/humanclaw-work` 改为自己的
大容量工作目录；不要复制现有 Klone 的个人路径或 Slurm 账号。

```bash
git clone --branch codex/pipeline-evaluation --single-branch \
  https://github.com/HenryLiu0405/HumanCLAW-PRO.git HumanCLAW
cd HumanCLAW
git checkout --detach 0f3d4731d5160005f6796995806b82af2f955671

export HC_REPO="$PWD"
export HC_WORK_ROOT=/absolute/path/to/humanclaw-work
export HC_AUTHOR=coauthor_a
export HUMANCLAW_BENCH_HOME="$HC_REPO"
mkdir -p "$HC_WORK_ROOT/data" "$HC_WORK_ROOT/outputs/$HC_AUTHOR"

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install torch==2.6.0 \
  --index-url https://download.pytorch.org/whl/cu124
python -m pip install -c constraints/eval-cu124.txt -e '.[rollout,video,test]'
```

CUDA 12.4 是已验证的安装路径，需与该服务器驱动兼容。若需要使用不同的依赖
版本，保留环境记录并单独验证；不要在安装失败后静默换掉物理引擎或补丁。
如果已有环境，可以复用符合要求的环境，省去重复安装。

按 [Habitat-Sim 构建指南](../patches/habitat-sim/README_zh.md) 安装：

- Habitat-Sim revision：`acbe6f4922e68145e401e55c30f9dfea460a3f24`。
- Bullet revision：`2c204c49e56ed15ec5fcfa71d199ab6d6570b3f5`。
- 应用仓库的 `patches/habitat-sim/humanclaw_halfphysics.patch`。
- 使用 headless、CUDA、Bullet 构建选项，并安装 Magnum Python bindings。
- C++ 编译器、CUDA toolkit 和 OpenGL/EGL 开发库的安装方式由服务器环境决定。

`tools/klone_*.sbatch` 和 `tools/klone_env.sh` 是原 Klone 环境的模板，含个人
目录、集群模块、partition/account；不要在另一台服务器原样提交。
这里的运行命令可放入合作者自己的 Slurm/PBS 作业或在其 GPU 工作机执行。

## 3. 资产、模型配置与凭据

**资产没有随 Git 提交。** 需要官方 HSSD 输入、HumanCLAW HSSD 补充包，以及
9 个 motion checkpoint。每位接收者先取得
[HumanCLAW HSSD 补充包](https://huggingface.co/datasets/HumanCLAW/HumanCLAW-HSSD)
的访问权限；HF 登录成功不等于已获 gated dataset 授权。

在项目根目录创建 `.env`，不要覆盖已有密钥文件：

```bash
test -f .env || cp .env.example .env
chmod 600 .env
```

在编辑器中填写 `AZURE_OPENAI_API_KEY=...`，如需下载资产再添加 `HF_TOKEN=...`。
项目会自动加载 `.env`，已有终端环境变量优先。不要把凭据放进共享配置、
结果包或聊天。`hf` CLI 自身不会因项目 `.env` 而自动登录；它需要认证时使用
`hf auth login`。

若尚未准备资产，可以使用仓库已有的固定版本下载与校验工具：

```bash
mkdir -p "$HC_WORK_ROOT/data/downloads/humanclaw-weights"
hf download HumanCLAW/HumanCLAW \
  HumanCLAW_pretrained_weights_paper_fullval_v1_20260816.tar.gz \
  --local-dir "$HC_WORK_ROOT/data/downloads/humanclaw-weights"
python tools/klone_prepare_public_assets.py weights \
  --root "$HC_WORK_ROOT" --repo "$HC_REPO"

python tools/klone_prepare_public_assets.py hssd \
  --root "$HC_WORK_ROOT" --repo "$HC_REPO" --use-hf-token --workers 4
python -m humanclaw_bench prepare-hssd \
  --hssd-root "$HC_WORK_ROOT/data/datasets/hssd-hab-4369cb987621" \
  --output "$HC_WORK_ROOT/data/humanclaw-hssd-val41" --workers 4

export HC_SCENE_CONFIG="$HC_WORK_ROOT/data/humanclaw-hssd-val41/hssd-hab.scene_dataset_config.json"
python -m humanclaw_bench assets --weights-root weights/paper_fullval_v1
```

`weights` helper 负责校验和安装已下载的归档，不负责下载该归档；上述第一步
不可省略。`hssd` helper 的名称含 Klone，但显式传入 `--root` 和 `--repo`
后不依赖 Klone。它使用固定的官方 HSSD revision 并校验文件哈希。
`prepare-hssd` 自动获取已授权的补充包，也支持 `--supplement` 指向已有副本。
准备目录包含符号链接，必须保留其原始资产目标。所有哈希校验应通过。

为独立验证复制模型配置到未跟踪的目录，编辑其中的 `base_url`、部署名
`model` 和 `api_key_env`：

```bash
mkdir -p outputs/handoff-local
cp configs/models/azure_gpt6_astra.json outputs/handoff-local/model.json
export HC_MODEL_CONFIG="$HC_REPO/outputs/handoff-local/model.json"
```

模板默认指向原实验的 Azure 资源，并不代表合作者有权访问。采用 Azure
OpenAI v1 接口时，使用该资源的 `/openai/v1/` base URL，不直接使用 Foundry
的 `/models` 地址。正式接力时使用协调者确认的配置；若换了模型、模型版本、
生成参数或部署，应记录差异，不默认视为同一实验条件。

确认配置后执行一次图文 API 检查；**这一步会调用真实模型并消耗额度**：

```bash
python -m humanclaw_bench api-check --model-config "$HC_MODEL_CONFIG"
```

`passed: true` 才通过这项检查。API 检查不证明仿真或 native Responses
工具调用协议可用，具体边界见 [实验指南](EXPERIMENTS.md)。

## 4. 首个完整 episode

下面的 GPU 检查和 rollout 要在分配到的计算节点运行，不能在集群登录节点
运行。多终端/作业之间需重新设置上述路径并激活同一个环境。

```bash
cd "$HC_REPO"
python -c 'import torch, habitat_sim; assert torch.cuda.is_available(); assert habitat_sim.built_with_bullet; print(torch.__version__, torch.cuda.get_device_name(0))'

export HC_RUN_ROOT="$HC_WORK_ROOT/outputs/$HC_AUTHOR/psv-pilot-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$HC_RUN_ROOT"
python -m pip freeze > "$HC_RUN_ROOT/environment.txt"
git rev-parse HEAD > "$HC_RUN_ROOT/checkout-commit.txt"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv \
  > "$HC_RUN_ROOT/gpu.csv"

python -m humanclaw_bench run --episodes one \
  --profile paper_fullval_v1 --harness humanclaw_psv \
  --model-config "$HC_MODEL_CONFIG" \
  --scene-dataset-config "$HC_SCENE_CONFIG" \
  --seed 0 --trace --metrics --video \
  --gpus auto --workers-per-gpu 1 --output "$HC_RUN_ROOT"

python tools/validate_episode_run.py "$HC_RUN_ROOT" \
  --replay --validation-output "$HC_RUN_ROOT-validation"
```

`--gpus auto` 使用分配给该进程的可见 GPU。正式协议的上限是 100 个环境
步骤，固定 `seed=0`，开启 trace、metrics 和 video，使用默认 paper 人体。
不要用 `--max-steps 2` 的短 smoke 结果代替完整 episode。这个 pilot 用于环境
验收，不能未经分配就计入正在运行的 fullval。

验收看 `validation.json` 的检查结果：真实模型调用和 token 有记录，工具动作
与模块可追踪，轨迹和 ego/exo 视频存在，日志与物理/渲染回放可检查。
任务本身成功与否看 benchmark 判据；任务失败仍可通过框架验证。
缺失的 token usage 或基础设施失败要保留，不能改成零或删除失败 attempt。
单例验证工具要求目录里恰有一个 attempt；多个 episode 的目录不能整体传给它。

物理和视频回放最好在原运行机器完成后再传结果。现有回放保留资产路径，
没有通用的异机路径重映射入口；日志回放和汇总不需要 GPU 或场景资产。

## 5. 接收已分配的 episode 清单后运行

协调者提供 JSON 文件，其中 `episodes` 的每行包含 `scene_id`、`episode_id`
和 `object_category`。例如下面仅说明格式，**并非实际任务分配**：

```json
{
  "episodes": [
    {"scene_id": "102343992", "episode_id": "0", "object_category": "bed"}
  ]
}
```

只有完成第 6 节的正式交接后，才把下述路径替换成收到的清单并启动：

```bash
export HC_EPISODES=/absolute/path/to/assigned-episodes.json
export HC_BATCH_OUTPUT="$HC_WORK_ROOT/outputs/$HC_AUTHOR/assigned-batch-001"
python -m humanclaw_bench run --episodes "$HC_EPISODES" \
  --profile paper_fullval_v1 --harness humanclaw_psv \
  --model-config "$HC_MODEL_CONFIG" \
  --scene-dataset-config "$HC_SCENE_CONFIG" \
  --seed 0 --trace --metrics --video --resume \
  --gpus auto --workers-per-gpu 1 --output "$HC_BATCH_OUTPUT"
```

每个 worker 使用不同输出目录。`--resume` 只会跳过当前目录中已完成、trace
有效且配置严格匹配的 episode；中断的 episode 从头再跑并保留旧 attempt。
它不是跨机器任务锁，也不支持从任意中间动作继续执行。

## 6. 接力当前 fullval 前，协调者需要完成的交接

当前 suite 是 `humanclaw-psv-astra-fullval-20261014`，总分母为 1,218，按每
shard 最多 4 个 episode 分成 305 份。各 shard 不能依据过期进度截图认领。

1. **交付同一份冻结源码。** 从现有 suite 导出 `source/`、
   `snapshot_manifest.json`、`suite.json` 和分配的 `episodes/shard-N.json`。
   依据 manifest 逐文件校验，另提供归档 SHA-256。排除 `.env`、密钥、个人
   运行时目录和结果；资产按许可单独准备。该完整 bundle 不在 Git 仓库中。
   从冻结 `source/` 安装并运行，重新设置 `HC_REPO`、`HUMANCLAW_BENCH_HOME`
   和 Python 导入路径，避免加载另一份 editable checkout。
2. **转交尚未启动的任务。** 记录 shard、episode 身份、负责人、机器、输出
   目录、源码/配置哈希与状态。先从原 Slurm 待运行任务中撤下被转交的 shard，
   再确认交接，处理期间重新核对是否已启动。已运行和已完成任务保留原归属。
   不能让两边都运行全部 fullval，也不按“哪次结果成功”选择重复 attempt。
3. **确认相同实验协议。** 当前为 `humanclaw_psv`、`gpt-6-astra`、
   `paper_fullval_v1`、seed 0、100 步、trace/metrics/video 全开。模型与
   profile、权重、物理补丁的内容身份保持一致；每台机器记录实际 GPU、CPU、
   内存、驱动、依赖版本、并发和调度等待。跨硬件时延须分组解释。
4. **先验收异机结果，再批量接力。** 当前 `_trace_matches` 还严格比较场景
   绝对路径；`tools/klone_suite.py report` 面向原 suite 目录。不同路径即使
   资产相同也不会自动被接纳。跨机器汇总需要显式的路径/资产身份映射与任务
   对账，尚未实现通用导入命令；保留原始记录，不能篡改 `run.json` 或删除
   源码/配置检查来绕过。先交回一个 pilot 验证合并口径。

本 handoff 没有分配或撤销任何现有作业，没有生成冻结源码分发包，也没有
改变当前 fullval 的配置。它明确了独立部署入口和正式接力前仍需完成的工作。

新增机器能否提高吞吐还取决于 Azure：若仍共用同一部署，全部 worker 会共用
其请求/token 配额。增加 GPU 数后观察限流、重试和每步时延，再提高并发。
原用户的“无预算上限”不自动作为其他账号的费用授权；各运行者自行确认额度。

## 7. 结果核查与交回

批次结束或需要查看中间状态时，可以离线重新汇总：

```bash
python -m humanclaw_bench trace summarize "$HC_BATCH_OUTPUT" --write-json
```

单个 run 的核查入口：

```bash
export HC_TRACE_RUN=/absolute/path/to/experiment_runs/run_ID
python -m humanclaw_bench trace validate "$HC_TRACE_RUN"
python -m humanclaw_bench trace inspect "$HC_TRACE_RUN"
python -m humanclaw_bench replay "$HC_TRACE_RUN" --mode log
```

先交回小型报告、任务清单、实际配置与环境记录；完整轨迹和视频按约定保存在
服务器或共享存储。没有自动同步回 Henry 笔记本的进程。

需要保留的结果：

- 分配清单、归属记录与配置/源码/资产哈希；作业退出状态、日志和硬件信息。
- `batch_attempts/`：包括没能生成 trace 的初始化失败。
- 每个 `experiment_runs/run_*/` 的 `run.json`、`events.jsonl`、`summary.json`、
  `artifacts/` 和 `replay/`，以及 native harness 的原始 session/event 文件。
- episode 目录中的 `metrics.json`、ego/exo 视频与原有轨迹文件；独立验证报告。
- `experiment_summary.json` 和环境版本记录。保留失败和重试，不只传成功结果。

目录级汇总包含所有 attempt，不能直接把其平均成功率当成去重后的 fullval
成绩。最终按固定 episode 清单对账，每例只选定一个符合协议的完成结果，
重复完成标为待核查；基础设施错误和未评分 episode 单独报告。token/费用
统计保留所有 attempt，缺失用量保持未知。费用需要明确的计价配置；未配置
时显示未知，不是免费。嵌套的模型、工具、模块时长不直接相加。

## 8. Codex / Pi 的额外交接

先把 PSV 在新机器跑通。部署 native harness 时再按
[Codex / Pi 指南](NATIVE_HARNESSES.md) 配置并执行 `harness-check`：该检查
使用真实 harness 加模拟环境/供应商，不产生 Azure 模型调用。

`configs/harnesses/local_native.json` 中含原作者 macOS 路径，不适合作为新
Linux 主机的直接启动配置。还需提供匹配版本的 Codex 可执行文件或 Pi 源码、
Node/dependencies、显式 Responses 配置，以及不能读取 benchmark 答案和
provider key 的进程/容器边界。原始 native session 与工具/模型事件均需保留。
原 Klone 的 native 隔离 launcher 和安装包位于未跟踪的操作目录，未随本
Git 分支完整发布；只有替换路径不能证明已经复现其部署。

对 Pi/shared filesystem 可将 `startup_timeout_seconds` 显式设为 180，仍受
整体 episode timeout 限制；把实际配置和 runtime identity 一起记录。
完成 mock、真实 Responses 图像/工具往返、一个真实 episode 和回放验收后，
再分配 native 批量评测。LIBERO-Pro 不在本次交接范围。
