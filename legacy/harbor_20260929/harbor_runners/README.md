# Harbor runner：固定 OpenCode 的使用与验收

正式入口固定使用 OpenCode。用户输入完整 `provider_id/model_id` 和对应 provider 的 API key；默认实验、镜像与版本由部署配置提供。模型调用统一经过 observed usage gateway，不需要 agent profile。

`topogym-harbor` 是本项目命令，等价于 `python -m harbor_runners.run`；内部仍调用 Harbor 0.23.0 的 `harbor run --config <生成的 job.json>`。本文参数不能直接传给第三方 `harbor run`。

[设计与迁移记录](../docs/develop/modules/opencode_model_key_rollout_plan_20260928_zh.md)；[实施与测试报告](../docs/develop/modules/opencode_model_key_implementation_20260928_zh.md)。

流程速览：[policy ↔ Env](../docs/develop/modules/project_three_flows_20260928_zh.md#flow-1)、[run 命令与参数去向](../docs/develop/modules/project_three_flows_20260928_zh.md#flow-2)、[生成的 run 目录](../docs/develop/modules/project_three_flows_20260928_zh.md#flow-3)。

## 1. 配置与最小用法

```text
configs/harbor/
├── defaults.yaml                  # 默认实验、镜像、OpenCode 版本、GPU 分配
├── providers.yaml                 # provider URL 与协议，不含 key
├── credentials.env.example        # 可选统一凭据变量
└── experiments/
    ├── cube_pick_place_rollout.yaml
    ├── fiber_bundling_rollout.yaml
    ├── cast_coil_rollout.yaml
    ├── <task_id>_rollout.yaml      # 其余基础任务，每个文件默认单次 rollout
    ├── smoke_api.yaml
    └── smoke_scripted.yaml         # 仅无 API 验收入口
```

当前默认实验是 `cube_pick_place_rollout`，镜像 `topogym-rollout:opencode-v1`，OpenCode `1.18.33`，GPU 数量 1。抓方块预设默认 input 3M / output 1M；下面的用户示例显式改为 **30k / 10k**。

### 1.1 单次 rollout 作为配置单位

13 个基础任务各有一份 `<task_id>_rollout.yaml`，另有方块验收 fixture 和两个 smoke 预设。每份基础配置只有一个 instance，默认 seed 0、attempts 1、concurrency 1；包含任务说明、观察权限、控制方式、仿真时域、agent 时限与 trial token 预算。镜像/OpenCode/GPU 默认值仍来自 defaults.yaml，provider 路由来自 providers.yaml，模型与 key 在启动时提供。prepare 将合并结果写入 experiment.resolved.json；不会复制共享部署设置或保存 key。

任务文字仅从 `instances[].instruction` 填入公共模板 `harbor_runners/templates/instruction.md`，形成 `harbor_tasks/<instance>/instruction.md`。必须提供非空文字，缺失时 prepare/run 在提示 key 前失败。模板补充操作教程和按最终 mode/state_fields 生成的权限说明。任务文字不写死难度尺寸、数量或 world 授权。

- `instruction.md`：任务目标、完成要求、任务约束和操作教程。
- `/rollout/spec.json`：动作、单位、时间、观察字段与权限；与 policy.initialize(context) 同源。
- 每步 policy obs：RGB、实测机器人关节/TCP/夹爪、state 和执行回执，及明确授权的 privileged 字段；limited 仍有机器人本体状态。

spec/context 与 observation profile 格式升为 schema_version 2；不再含 task_instruction，obs 不再含普通 task 字段。移除了 observation_profile.task_instruction 配置。模拟器 Task 自身的说明方法与私有状态不受这次 Harbor 组织调整影响。

| 基础预设 | 默认难度 | 默认观察权限 | 仿真时域 / agent 墙钟 | trial input / output |
| --- | --- | --- | --- | --- |
| cast_coil、cast_keyhole、blanket_flatten、buzz_wire_3d、hedgehog_in_cage、horseshoe_ring、interlocked_claws、knot_untying、lock_picking、rope_threading | medium | limited | 25 s / 3600 s | 10M / 3M |
| orbits、slotted_post_ring | hard | limited | 25 s / 3600 s | 10M / 3M |
| fiber_bundling | medium | unlimited + world | 200 s / 7200 s | 1M / 0.3M |
| cube_pick_place（fixture） | base | unlimited + world | 25 s / 1800 s | 3M / 1M |

表中每个任务名对应 `<task_id>_rollout.yaml`。Orbits/Slotted 目前仅 hard 接入，Rope Threading 仅 medium；Blanket hard 仍 blocked。选择未接入难度会被 catalog 校验拒绝。配置存在、prepare 通过并不代表 GPU 运行或任务可解已经验收；成功判据状态仍以任务实现为准。Rope Threading 的目标方向描述对应当前预设场景，若自定义旋转或目标，必须同时修改任务说明。

单次运行与 sweep 使用同一配置；例如下面只冻结 3 难度 × 3 seed × 2 attempts = 18 trials，不调用模型或 GPU：

```bash
.venv-harbor/bin/python -m harbor_runners.run prepare \
  --experiment cast_coil_rollout --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --difficulty easy medium hard --seeds 0 1 2 --attempts 2 \
  --run-id coil_sweep_prepare
```

把 prepare 换成 run 即按该组合启动。每 trial 独立使用完整预算；instruction 在 sweep 中复用。跨任务要选择对应任务预设，不能仅替换 task_id 沿用别的任务说明。

迁移：`pick_cube_budget` → `cube_pick_place_rollout`，`fiber_bundling_medium` → `fiber_bundling_rollout`，`cast_coil_sweep` → `cast_coil_rollout --difficulty easy medium hard`。旧配置文件已移除，已冻结的历史产物不修改。本次有容器内观察接口变更，运行新配置前重建镜像并重新 prepare；已冻结实验不能混用新旧源码。

部署完成后，最小运行命令：

```bash
.venv-harbor/bin/python -m harbor_runners.run run \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor'
```

没有已保存的统一凭据时，交互式终端会隐藏输入 API key。程序自动选择实验、生成唯一 run-id，完成 prepare、preflight、launch、collect 和 summary。非交互调用必须显式传 key 或提供保存的凭据，不等待输入。

凭据优先级：本次 `--api-key` / `--api-key-stdin` > `TOPOGYM_MODEL_API_KEY` 环境变量 > 私有 dotenv。不同 launch 使用独立子进程环境，不修改服务进程的全局环境。终端推荐隐藏输入/stdin；明文 `--api-key` 仍可能出现在调用方的 shell 历史和进程参数里。

可选保存方式：

```bash
mkdir -p .secrets
cp configs/harbor/credentials.env.example .secrets/harbor.env
chmod 600 .secrets/harbor.env
# 在本地编辑器中填写 TOPOGYM_MODEL_API_KEY；不需要 provider 专属变量名。
```

完整名称按第一个 `/` 拆分，剩余 model ID 原样保留。`openrouter/anthropic/...` 配 OpenRouter key，`anthropic/...` 配 Anthropic key，不会自动换服务。接入表已有 OpenRouter Chat Completions、Anthropic Messages、OpenAI Responses；本地接线测试不等于所有远端模型/账号已验收。自定义 provider 由维护方登记 URL、协议与受支持的 npm SDK。

## 2. run 全参数

下面是参数语法示意；尖括号是占位值，方括号表示可选项：

```text
topogym-harbor run
  --model-name <provider_id/model_id>
  [--api-key <key> | --api-key-stdin]
  [--experiment <preset-name> | --config <experiment.yaml>]
  [--defaults <deployment-defaults.yaml>]
  [--root <output-workspace>]
  [--env-file <private.env>]
  [--run-id <unique-id>]
  [--image <docker-tag-or-digest>]
  [--opencode-version <x.y.z>]
  [--attempts <positive-int>]
  [--concurrency <positive-int>]
  [--difficulty <variation> [<variation> ...]]
  [--seeds <seed> [<seed> ...]]
  [--mode limited|unlimited]
  [--state-fields [robot world task]]
  [--gpus <count> | --gpu-devices <id> [<id> ...]]
  [--timeout-sec <seconds>]
  [--input-token-limit <tokens>]
  [--output-token-limit <tokens>]
  [--initial-observation-steps <steps>]
  [-h | --help]
```

| 参数 | 默认值与作用 |
| --- | --- |
| `--model-name` / `--model` | 必填，完整 OpenCode 模型名；两者是别名 |
| `--api-key` / `--api-key-stdin` | 互斥；stdin 读一行；不填时使用保存凭据或隐藏输入 |
| `--experiment` | experiments/ 内预设名，省略 .yaml；默认由 defaults 选择 |
| `--config` | 自定义实验 YAML 路径，与 experiment 互斥 |
| `--defaults` | 默认 configs/harbor/defaults.yaml；其中相对路径以该文件目录为基准 |
| `--root` | 默认项目根目录；控制 runs/ 与 task_rollouts/ 的输出位置 |
| `--env-file` | 默认可选 <root>/.secrets/harbor.env；显式指定时必须存在且权限为 600 |
| `--run-id` | 默认 UTC 时间加随机后缀；已有目录不会覆盖 |
| `--image` | 默认部署镜像；必须先构建/拉取，preflight 核验 image ID 与源码 |
| `--opencode-version` | 默认 1.18.33；精确版本，不接受 latest；更换版本需要重新验收 |
| `--attempts` | 每实例重复次数，默认预设或 1；不会自动改变 seed |
| `--concurrency` | Harbor 同时运行的 trial 数，默认预设或 1 |
| `--difficulty` | 当前预设任务的 variation ID/别名，多值展开实例 |
| `--seeds` | 默认预设 seed；多 seed 展开实例，每 trial 各自拥有完整预算 |
| `--mode` | 默认保留各实例模式；显式 limited/unlimited 覆盖所有实例，并同步 enable_privileged；limited 清空原有特权字段，与 token 预算无关 |
| `--state-fields` | unlimited 的特权白名单，可选 robot/world/task；省略保留预设，单独传参数不带值清空；limited 不能指定非空白名单 |
| `--gpus` / `--gpu-devices` | 数量或具体 ID，互斥；默认部署分配；不静默降为 CPU |
| `--timeout-sec` | agent 墙钟限额；预设优先，否则 1800 秒；大于 0、最多 86400 |
| `--input-token-limit` | 每 trial 累计 input，含缓存/重复上下文；方块预设默认 3,000,000 |
| `--output-token-limit` | 每 trial 累计 output，含 reasoning；方块预设默认 1,000,000 |
| `--initial-observation-steps` | 默认 5，允许 0–1000；初始真实控制步，不是图片张数 |
| `--help` | 查看当前安装版本的实际参数 |

`--root` / `--env-file` 可放在子命令之前或之后。已移除 agent-profile、任意 harness name/import_path、agents 子命令。普通 run 不提供 usage-mode，固定 observed；strict 配置明确拒绝，Scripted 验收才允许 off。旧 `--task` 由 `--experiment` / `--config` 替代，避免更换 task_id 时误继承另一任务的物理设置。

trial 数量 = 展开后的实例数 × attempts；concurrency 只控制调度。例如一个方块实例、seed 0、attempts 1，就是 **1 trial**。

## 3. Muse Spark：完整流程，1 trial，input 30k / output 10k

模型全名使用 `openrouter/meta/muse-spark-1.3-contributor`，见 [OpenRouter 模型页面](https://openrouter.ai/meta/muse-spark-1.3-contributor)，需要账号具有访问权限。

方块预设的任务是抓起、持稳、原位放回、松爪、撤离并稳定。它允许 world 观察和复用参考 policy，是集成验收，不用于宣称纯视觉推理或从零编写抓取算法。

### 3.1 一次性部署

在有 Docker 权限的 Linux 终端执行：

```bash
cd /home/jianwen/topogym
bash scripts/setup_harbor_runner.sh
docker info
docker compose version
nvidia-smi
bash scripts/build_harbor_image.sh topogym-rollout:opencode-v1
```

需要 NVIDIA Container Toolkit。不要在 build 时传 key。代码改动后应重建镜像，不能跳过 host/container 源码哈希检查。

先做无模型调用的容器权限、真实 GPU 抓放验收：

```bash
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case isolation --image topogym-rollout:opencode-v1

.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case pick-cube-scripted --image topogym-rollout:opencode-v1 \
  --gpu-devices 0 --attempts 1 --concurrency 1 --seed 0
```

### 3.2 启动模型实验

```bash
read -r -s -p 'OpenRouter API key: ' TOPOGYM_RUN_KEY
printf '\n'
printf '%s\n' "$TOPOGYM_RUN_KEY" | \
  .venv-harbor/bin/python -m harbor_runners.run run \
    --experiment cube_pick_place_rollout \
    --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
    --api-key-stdin \
    --image topogym-rollout:opencode-v1 \
    --gpu-devices 0 \
    --attempts 1 --concurrency 1 --seeds 0 \
    --input-token-limit 30000 --output-token-limit 10000 \
    --timeout-sec 1800 --initial-observation-steps 5 \
    --run-id muse_pickup_30k_10k_01
unset TOPOGYM_RUN_KEY
```

重跑请换 run-id，或省略它自动生成。run 表示启动真实模型实验，不需要额外 allow-api。

执行顺序：冻结任务 → preflight → worker 初始化、发布 segment_0 → OpenCode 读取历史和视频抽帧 → 写/提交 policy → simulator 连续执行 → 返回新 segment → 继续或结束 → verifier → collect/summary。主模型与标题等辅助模型固定为用户指定模型，其他模型请求会被网关拒绝。

**30k / 10k 是预算设置，不保证任务能在该额度内完成。** observed 依据回执结算 input，在途请求可能使 input 超过 30k 后才触发停止。旧成功记录用过 444,149 input / 5,940 output，不能当作 30k input 足够的证据。普通生成的 output cap 会按剩余额度收紧，缺失 usage 会失败。

### 3.3 查看任务与预算结果

`run` / `launch` 结束后，会在 Harbor 表格后自动打印每个 episode 的摘要：任务和 seed、观察/控制模式、task success 与 reward、停止原因、实际 token/最终限额、模型请求数、policy 段数、初始/policy 控制步数、仿真时长、预算停止耗时及归档路径。缺失证据显示 unknown；usage off 不记为 0 token。详细内容也写入 `summary.json` 的 `episodes`。

已有结果可以直接重显，不启动模型或仿真：

```bash
.venv-harbor/bin/python -m harbor_runners.rollout_output_report \
  --run runs/harbor/muse_pickup_30k_10k_01 --format text
```

省略 `--format text` 保留原 JSON 输出。此次真实运行摘要中的核心结果为：

```text
Task success: no | Reward: 0 | Pipeline: FAIL
Stop reason: budget_exceeded [input_tokens]
Token budget: FAIL (observed; per trial)
  Input: 32,840 / 30,000 (over by 2,840)
  Output: 704 / 10,000
Usage complete: yes | Model requests: 4 | In flight: 0
Policy segments: 0 | Control steps: 5 (initial=5, policy=0) | Simulated: 0.125s
Stop confirmed after decision: agent +140.0ms | execution +255.8ms
```

这验证了真实 input 超额检测、agent 强停和失败评分。模型在读取初始资料时耗尽额度，尚未提交 policy；不构成抓取成功、执行中的 policy 取消或 output 超额强停的真实验收。Harbor `Exceptions: 0` 仅表示未处理异常为零。input 按整个 trial 多次请求累加，包括重复/缓存上下文；不是单次请求的上下文窗口大小。[账本与归档核对报告](../runs/test_results/muse_pickup_30k_10k_01_budget_review/report.json)。

需要编程检查时：

```bash
.venv-harbor/bin/python - <<'PY'
import json
from pathlib import Path
run = Path("runs/harbor/muse_pickup_30k_10k_01")
index = json.loads((run / "rollout_index.json").read_text())
print("expected_trials =", index["expected_trials"])
for trial, item in index["trials"].items():
    verdict = item.get("verification", {})
    print(trial, {
        "task_success": verdict.get("task_success"),
        "reward": verdict.get("reward"),
        "budget_qualified": item.get("budget_qualified"),
        "failure_reason": item.get("failure_reason"),
        "archive": item.get("archive"),
    })
PY
```

run 退出码 0 表示运行/采集/预算链路通过；任务是否完成还要检查 task_success 与 reward。若希望命令必须在方块成功且预算合格时返回 0，可改用下列**独立新实验**验收入口；两条命令不是同一个 trial，不要重复执行后算作一次：

```bash
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case pick-cube --allow-api \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --input-token-limit 30000 --output-token-limit 10000 \
  --gpu-devices 0 --attempts 1 --concurrency 1 --seed 0 \
  --run-id muse_pickup_30k_10k_acceptance_01
```

该脚本在交互式终端提示 key，也支持 api-key-stdin。加 prepare-only 时不调用 Docker 或模型、不要求 key。

### 3.4 Cast Coil：limited，单 trial，input 10M / output 3M

下面固定 medium、seed 0、attempts 1，所以整个 job 只有一个 trial。模型名沿用本文示例，可替换成实际 provider/model；需要该 provider 的 key。先按 3.1 安装宿主依赖。新增模式 CLI 后应重建共享镜像，因为 preflight 会比对包括 runner 在内的源码哈希。

```bash
cd /home/jianwen/topogym
bash scripts/build_harbor_image.sh topogym-rollout:opencode-v1

.venv-harbor/bin/python -m harbor_runners.run run \
  --experiment cast_coil_rollout \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --mode limited \
  --difficulty medium --seeds 0 \
  --attempts 1 --concurrency 1 \
  --input-token-limit 10000000 --output-token-limit 3000000 \
  --timeout-sec 86400 --initial-observation-steps 5 \
  --gpu-devices 0 --image topogym-rollout:opencode-v1
```

交互终端会隐藏提示 key；已有 `TOPOGYM_MODEL_API_KEY` 或私有 dotenv 时直接使用。run-id 自动生成，结束自动打印 task success、reward、预算实际用量和归档位置。

切换 unlimited 时，将命令中的 `--mode limited` 替换为以下参数，其他参数保持相同：

```bash
--mode unlimited --state-fields robot world task
```

也可只授权 `--state-fields world`。`--mode unlimited` 本身保留预设白名单，Cast Coil 预设白名单为空，因此单改 mode 不会自动发布全部真值。切回 `--mode limited` 并移除非空 `--state-fields` 即可；limited 提供 RGB 与基础机器人本体感知，不提供物体/Task 真值。两种观察模式均沿用 observed token 计量。

- **额度范围**：每 trial input 10,000,000 / output 3,000,000；把 difficulty 改为 `easy medium hard` 会产生 3 个 trial，各自获得完整额度。input 含缓存/重复上下文，output 含 reasoning。
- **停止语义**：observed 根据 provider 回执结算，在途 input 可能超额后才触发停止；不能承诺严格零超额，当前 OpenCode 接线拒绝 strict。预算是上限，不要求模型花完，成功与否由真实运行确定。
- **独立时限**：此命令将 agent 墙钟限额设为当前允许的最大值 86400 秒（24 小时）；Cast Coil 原预设是 3600 秒。simulator 仍默认 `max_physics_steps=10000`、`physics_dt_s=0.0025`、`control_decimation=10`，即最多 25 秒仿真 / 1000 个控制步，包含初始 5 步。延长物理时域需要复制该实验 YAML，在各 instance 的 simulator 下显式设置 `max_physics_steps`，再使用 `--config`。这两类时限均不由 token 预算自动延长。

需要先检查再启动时，把上述子命令 `run` 改成 `prepare`，可另加 `--run-id coil_limited_10m_3m_01`；prepare 不需要 key、不调用 Docker/模型。检查生成的 `experiment.resolved.json`、每任务 `environment/instance.json` 与 `environment/usage.json`，之后启动同一个冻结实验：

```bash
.venv-harbor/bin/python -m harbor_runners.run launch \
  --run-dir runs/harbor/coil_limited_10m_3m_01
```

上述模式和预算参数属于项目入口，不能直接附加到第三方 `harbor run`。项目的 launch 会完成 preflight、凭据处理、Harbor 调用和结果采集。

## 4. 分步启动、预算管理、恢复

只冻结配置，不需要 key / Docker / GPU：

```bash
.venv-harbor/bin/python -m harbor_runners.run prepare \
  --experiment cube_pick_place_rollout \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --attempts 1 --seeds 0 \
  --input-token-limit 30000 --output-token-limit 10000 \
  --run-id muse_pickup_prepare_01
```

稍后启动并在交互式终端输入 key：

```bash
.venv-harbor/bin/python -m harbor_runners.run launch \
  --run-dir runs/harbor/muse_pickup_prepare_01
```

launch 包含 preflight。可单独用 `preflight --run-dir ...` 核对冻结文件、凭据、Docker/Compose、镜像、配置与源码；它不调用模型、不执行 GPU 仿真，也不能证明远端 key 有权限。改 providers/defaults 不会改变已冻结路由；源码变化时应重新 prepare。

已有 Job 不能重新 launch；采集失败保留唯一容器副本，可重试：

```bash
.venv-harbor/bin/python -m harbor_runners.run collect \
  --run-dir runs/harbor/muse_pickup_30k_10k_01 --recover
```

collect 只恢复采集，不重启模型/仿真。旧结果仍可 collect/report；旧未启动任务使用原 checkout/image，或新建 run 重新 prepare。

预算管理使用实际 trial 目录：

```bash
.venv-harbor/bin/python -m harbor_runners.run usage-status \
  --trial-dir 'runs/harbor/<run-id>/jobs/job/<trial-name>'

.venv-harbor/bin/python -m harbor_runners.run usage-update \
  --trial-dir 'runs/harbor/<run-id>/jobs/job/<trial-name>' \
  --input-token-limit 30000 --output-token-limit 10000 \
  --revision 1 --reason 'set trial budget'
```

revision 取最新 status。失败后提高额度不会复活 trial；公开 budget.json 与 frozen YAML 不是调额入口。

<a id="fiber-medium"></a>
### 4.1 Fiber Bundling medium：Muse Spark，input 1M / output 0.3M

使用 [experiments/fiber_bundling_rollout.yaml](../configs/harbor/experiments/fiber_bundling_rollout.yaml)，不是默认的抓方块实验。该预设已适配固定 OpenCode；不需要 profile 或模板，普通入口固定 observed，不再接受 `--agent-profile`、`--usage-mode`。URL/协议来自 [providers.yaml](../configs/harbor/providers.yaml)，版本来自 [defaults.yaml](../configs/harbor/defaults.yaml)，当前 OpenCode 为 1.18.33。

保留本实验 input **1,000,000** / output **300,000**，不会继承上文方块测试的 30k/10k。主模型和 small_model 均绑定 `openrouter/meta/muse-spark-1.3-contributor`；辅助调用仍累计 token，但不会自动改用 Gemini。input 包含重复/缓存上下文，output 包含 reasoning；普通生成的 output cap 按剩余额度收紧。observed 仍按 usage 回执判断，在途请求可能造成超额，不是消费前的严格保证。

其余预设：medium 8 芯、环内半径 13.5 mm；seed 0、单 trial、GPU 0；unlimited + world、EE_ABS、CUDA/Nyx；仿真时间上限 200 s，agent 墙钟上限 7200 s。instruction 按正常目标求解，不提示“可能无解”。当前 Task 的 `terminal_v3_fiber_contacts` 已启用自动 solved 判断，夹爪接触细芯直接失败；成功还要求材料顺序穿环、前护套清出、弯折合规、稳定窗口和完整接触覆盖。真实完整机器人解题仍需单独核验，详见 [Fiber 任务说明](../docs/develop/tasks/fiber_bundling_zh.md#当前自动终态)。

在同一 Bash 终端按顺序执行，每步成功后继续。先从当前代码构建新标签，确保装入新的 OpenCode 接线和 Fiber 判据；镜像构建不调用模型或运行仿真。

```bash
cd /home/jianwen/topogym
export TOPOGYM_FIBER_TAG="$(date -u +%Y%m%dT%H%M%S%NZ)"
export TOPOGYM_FIBER_RUN_ID="fiber_muse_medium_${TOPOGYM_FIBER_TAG}"
export TOPOGYM_FIBER_IMAGE="topogym-rollout:fiber-opencode-${TOPOGYM_FIBER_TAG}"
export TOPOGYM_FIBER_RUN="$PWD/runs/harbor/${TOPOGYM_FIBER_RUN_ID}"
bash scripts/build_harbor_image.sh "${TOPOGYM_FIBER_IMAGE:?请先设置本轮变量}"
```

prepare 不读取 key，也不启动 Docker/GPU/API。medium、seed 已在预设中指定，不必再次传 difficulty/seeds。

```bash
.venv-harbor/bin/python -m harbor_runners.run prepare \
  --experiment fiber_bundling_rollout \
  --model-name openrouter/meta/muse-spark-1.3-contributor \
  --image "${TOPOGYM_FIBER_IMAGE:?请先构建本轮镜像}" \
  --input-token-limit 1000000 --output-token-limit 300000 \
  --gpu-devices 0 --attempts 1 --concurrency 1 \
  --run-id "${TOPOGYM_FIBER_RUN_ID:?请先设置本轮变量}"
```

检查 `experiment.resolved.json` 的 execution.harness、model_connection、usage.limits，以及生成的任务说明：

```bash
.venv-harbor/bin/python -m json.tool "${TOPOGYM_FIBER_RUN:?请先 prepare}/experiment.resolved.json"
cat "${TOPOGYM_FIBER_RUN}/harbor_tasks/fiber-bundling-medium-seed0/instruction.md"
```

launch 自动 preflight，随后真正调用 API 和 GPU。保存凭据必须使用 `.secrets/harbor.env` 的 **TOPOGYM_MODEL_API_KEY**，旧 OPENROUTER_META_SPARK_API_KEY 不再自动映射；也可在交互式终端按提示隐藏输入 OpenRouter key。不要用上文 `cp credentials.env.example` 覆盖已有凭据文件。

```bash
.venv-harbor/bin/python -m harbor_runners.run launch \
  --env-file /home/jianwen/topogym/.secrets/harbor.env \
  --run-dir "${TOPOGYM_FIBER_RUN:?请先 prepare}"
```

预算已在 prepare 冻结，launch 不重复填写 limit。旧 schema 1 未启动 run 需重新 prepare；已有 job 不能重启。重跑先设置新 tag；不要修改冻结文件。结束后终端自动打印 episode 摘要，也可读取：

```bash
.venv-harbor/bin/python -m json.tool "${TOPOGYM_FIBER_RUN}/summary.json"
.venv-harbor/bin/python -m json.tool "${TOPOGYM_FIBER_RUN}/rollout_index.json"

while IFS= read -r -d '' ledger; do
  trial_dir="${ledger%/usage/ledger.sqlite}"
  .venv-harbor/bin/python -m harbor_runners.run usage-status --trial-dir "$trial_dir"
done < <(find "${TOPOGYM_FIBER_RUN}/jobs/job" -type f -path '*/usage/ledger.sqlite' -print0)
```

`rollout_index.json` 指向实际 `task_rollouts/<run-id>/fiber_bundling/rollout_*/`，内有 verification.json、session_final.json、segments 的视频和逐步日志。usage-status 在运行中也可使用；另开终端时先设置真实 run 路径，账本未创建时无输出不表示 token 为零。任务成功、预算通过和证据完整分别查看，reward=1 要求它们同时满足。

2026-09-28 迁移核对已通过独立快照 prepare、冻结配置与 instruction 检查，以及 79 项模型绑定/路由/预算配置/计量账本回归；[检查报告](../runs/test_results/fiber_opencode_migration_20260928/report.json)记录实际源码与范围。本次核对未构建镜像、未执行 Docker preflight、未调用真实模型或运行 Fiber GPU 仿真。

## 5. 产物与运行边界

- `runs/harbor/<run-id>/`：experiment/job/manifest、冻结 provider/源码、镜像身份、Harbor trial、summary 和清理记录。
- `runs/harbor/<run-id>/jobs/job/<trial>/usage/`：权威 SQLite、连续 JSONL、快照及停止记录。
- `task_rollouts/<run-id>/cube_pick_place/rollout_*/`：历史、segment 视频、逐 tick 日志、policy、评分与私有证据。
- `runs/test_results/<run-id>/report.json`：验收脚本的独立报告。

一个 trial 的 worker 只初始化一个 Env；policy 沿连续状态运行，操作方无 reset/make/close。segment_0 默认保持 5 个真实控制步，后续 policy 从其终态继续。agent 用 history/logs/video/frames 读取已发布历史，抽帧后再调用读图工具。

真实 key 留在宿主 gateway，OpenCode 只得到 trial token。agent/验证阶段使用 no-network，relay 经只读 Unix socket 挂载通信；只支持本机 Linux Docker。agent、policy、root worker 保持已有权限边界。归档完整后只清理本 run 标签下的停止容器/网络；镜像保留。

## 6. 本地测试

```bash
.venv-harbor/bin/python -m pytest --confcutdir=tests/harbor tests/harbor tests/usage -q
.venv-gs121-nyx/bin/python -m pytest \
  tests/contracts/test_rollout_service.py \
  tests/contracts/test_cube_pick_place_policy.py \
  tests/contracts/test_cube_transfer_task.py -q
```

需要允许本地 TCP/Unix socket 与子进程，不调用付费模型。设置 `TOPOGYM_TEST_OPENCODE=/absolute/path/to/opencode` 后，test_opencode_cli.py 会用固定 1.18.33 真实 CLI 与本地模拟 provider 做三协议测试；未设置时这三项明确 skip。它不替代 Docker/GPU/真实模型 rollout 验收。
