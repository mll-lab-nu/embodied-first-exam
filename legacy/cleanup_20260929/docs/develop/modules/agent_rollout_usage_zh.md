# Agent rollout 实用手册：RGB / Simulator API 两种模式

更新：2026-09-21，适用于当前 Linux / Bash 实现。
完整契约见 [pipeline 说明](agent_rollout_pipeline_zh.md)，设计背景见 [目标与差距分析](agent_rollout_target_gap_review_zh.md)。

当前先支持 Cast Coil 与合成 counter；其他任务仍需接入冻结 preset 和 simulator state adapter。
**真实 Cast Coil 的查询、动作、固定初态 reset、视频与权限检查已跑通；真实付费模型的自主装配成功尚未验证。**

教程中的重复操作集中在 `tests/`，按下面顺序运行即可：

| 步骤 | 脚本 | 自动完成的内容 | 模型 API 费用 |
| --- | --- | --- | --- |
| 本地检查 | `check_agent_rollout_setup.sh` | 依赖、隔离、CLI、可选离线回归 | 无 |
| 固定动作检查 | `run_agent_rollout_tools_smoke.sh` | prepare、两种访问条件、短程动作/reset、结果断言 | 无 |
| 准备实验 | `run_agent_rollout.sh prepare` | 创建目录、生成/复制 agent 配置、冻结变体、保存预算 | 无 |
| 运行实验 | `run_agent_rollout.sh evaluate` | 读取凭据、启动环境与 agent、执行保存的预算、汇总结果 | 使用真实模型时有 |
| 查看结果 | `run_agent_rollout.sh report` | 状态、错误原因、各相机视频目录、日志位置 | 无 |
| 监测 token | `run_agent_rollout.sh watch` | 自动定位所有 trial 的公开 token 账本并刷新 | 无 |

统一入口是 [`tests/run_agent_rollout.sh`](../../../tests/run_agent_rollout.sh)，Python 实现在
[`tests/agent_rollout_workflow.py`](../../../tests/agent_rollout_workflow.py)。
创建 API key、开通模型权限/计费和选择实验参数仍需由操作者完成。
脚本相对路径均按仓库根目录解释；`--output` 始终指整个 run 目录，不是其中的 `evaluation/`。
任一命令加 `--help` 可查看参数；`--python` 可放在子命令前或后，省略时使用环境变量 `TOPOGYM_PY`
或仓库的 `.venv-gs121-nyx/bin/python`。

## 1. 先选择访问条件

| 配置 | agent 可以做什么 | 默认 reset |
| --- | --- | --- |
| `access_mode: "rgb"`、`interaction: "tools"` | 读取多视角 RGB，写 Python，调用机器人控制和视频反馈接口 | 禁止 |
| `access_mode: "simulator"`、`interaction: "tools"` | 上述能力 + 查询物体 pose、机器人状态、相机 pose 和刚体接触 | 回到同一个冻结初态 |

reset 不改变变体，不清空 agent 会话、scratch、历史或累计预算。`repeat` 则会创建新 agent 会话。
当前正式接口不提供物体传送、改物理参数或改 evaluator；支持的状态字段以 `capabilities.json` 为准。
老配置只写 `mode: "rgb"` 时仍走旧的 segment 协议；新实验请显式填写 `interaction: "tools"`。
`rgb_privileged` 保留为旧的“RGB + 静态构建资料”条件，不等同于 simulator。

## 2. 无 API key 的本地检查

在 Linux 终端进入仓库，设置 Python：

```bash
cd /home/jianwen/topogym
TOPOGYM_PY="$PWD/.venv-gs121-nyx/bin/python"
bash tests/check_agent_rollout_setup.sh --python "$TOPOGYM_PY" --regression
```

这会检查 Codex、bwrap、ffmpeg/ffprobe、Python 依赖，并运行离线回归。
包括真实 Codex CLI 调用本地 SDK 的检查，但模型响应由本地模拟服务提供，不使用真实 API key，不产生模型费用。
它需要本机 localhost 端口、子进程和 Linux namespace 权限。

Python 环境安装见 [项目环境说明](../visual/nyx_gs121_setup_zh.md)。Codex 及其依赖需要位于隔离可见的
`/usr`、`/bin`、`/lib` 等系统路径；只有 `~/.nvm` 或 `~/.local` 下的安装可能无法在隔离环境运行。

再用固定检查脚本跑真实 Cast Coil：

```bash
bash tests/run_agent_rollout_tools_smoke.sh \
  --python "$TOPOGYM_PY" --task cast_coil \
  --output runs/agent_rollouts/cast_coil_sdk_check_01
```

输出目录必须全新；重复检查换成 `_02` 等新名字。这个脚本自动 prepare、运行两种条件并检查结果：

- simulator：读状态 → 执行 3 步 → reset → 核对初态 → 再执行 2 步，总账为 5 步。
- RGB：确认状态查询/reset 被拒绝 → 执行两段共 5 步 → 保留四路视频。

它会真正初始化 Genesis 和录制 MP4，但使用固定 replay 程序，只验证接口与短程物理运行。
**这是接线检查，不是模型求解或完整装配。** 想先不启动 Genesis，可将 `--task` 改成 `counter`。

<a id="api-key"></a>

## 3. 配置模型服务凭据

API key 属于提供模型推理的服务商。先在所选服务商的平台确认凭据有效、模型访问权限和计费可用。
**推荐直接在第 6 步运行 `evaluate`，脚本会在终端隐藏输入 key；无需提前设置变量。**
只有 `evaluate` 读取凭据，prepare、report、watch 和离线检查均不需要 key。

若要在同一终端连续启动多个实验，也可以提前提供通用环境变量：

```bash
read -r -s -p 'Model service API key: ' TOPOGYM_MODEL_API_KEY
printf '\n'
export TOPOGYM_MODEL_API_KEY
```

非交互任务必须通过进程环境注入该变量，缺少时立即报错。不要把 key 写到命令行参数或脚本文件中。

这里需要区分三个概念：

| 项目 | 含义 | 本文可运行示例 |
| --- | --- | --- |
| agent 执行后端 | 负责会话、编写代码和调用工具；当前 `provider` 字段选择这一层 | `provider: "codex"` |
| 模型服务 | 提供推理接口、认证和计费 | OpenAI Responses API |
| 模型 | 该服务实际允许访问的 model ID | `model: "gpt-6-astra"` |

**当前后续命令以 OpenAI API + Codex 执行后端为例，因此本次需输入 OpenAI Platform key。**
脚本启动时会把输入的 key 或 `TOPOGYM_MODEL_API_KEY` 映射到当前适配器读取的 `CODEX_API_KEY`；
这个变量名不代表另一种独立的 key。此映射由教程脚本完成，直接运行底层 Python CLI 时仍需自行传入适配器变量。

这个接入示例还需满足：

- Platform API key 与通过 ChatGPT 登录 Codex 的订阅额度分开，见 [官方认证说明](https://learn.chatgpt.com/docs/auth)。
- 当前严格预算代理固定连接 OpenAI，使用 `POST /v1/responses/input_tokens` 和 `POST /v1/responses`；受限 key 要允许这两个端点。
- 接入其他服务需要对应的认证、请求/响应、图片/工具调用及 token 计数适配，不能仅替换 key 或模型名。
  通用服务配置的设计见 [模型服务设计文档](model_service_design_zh.md#model-service-config)。

key 不写入配置文件或 prompt。后面的命令将它临时传给 trusted trial 的预算代理；
在当前预算模式下，Codex 只收到本次临时代理凭据和环境服务凭据。无需改变 IDE 登录方式。

<a id="configure-agent"></a>

## 4. 自动创建配置并准备短实验

以下沿用第 3 节的 OpenAI + Codex 示例，先用 simulator 条件检查新工具流程。
`--output` 必须是全新目录；脚本自动创建父目录，已有目录会被拒绝，不覆盖历史实验：

```bash
TOPOGYM_RUN_ROOT=runs/agent_rollouts/cast_coil_astra_tools_01
bash tests/run_agent_rollout.sh prepare --python "$TOPOGYM_PY" \
  --output "$TOPOGYM_RUN_ROOT" --task cast_coil \
  --agent-id astra --model gpt-6-astra --access-mode simulator
```

这个命令同时生成：

- `agents.json`：`provider: codex`、指定模型、`interaction: tools`、simulator 的 `reset_policy: same_preset`。
- `presets/suite.json` 与 preset 文件：默认 1 个变体，seed 为 `20260921`，CPU / rasterizer / 320×180，目标为 assemble。
- `run.json`：冻结 suite 的路径、预计 trial 数和 evaluation 参数；默认 1 次 repeat、3M token，以及第 6 节表中的短程预算。

可在 IDE 中检查这些 JSON。预算参数统一传给 **prepare**，后续 evaluate 读取保存值，避免两个阶段参数不一致。
`--timeout-s 600` 是单个 Codex 回合的最长墙钟时间；一个回合可以多次调用模型和环境工具。
模型使用完整英文目标、API/目录说明、初始四路图片，在自己的终端工具里编写 Python 并调用环境。
最终返回 `stop` decision 结束会话；动作不必等到最终 JSON 才执行。

要跑严格 RGB，将 prepare 的参数改成 `--access-mode rgb`，自动使用 `reset_policy: disabled`。
同时生成两种条件用 `--access-mode both`。reset 消融可用 `--reset-policy disabled` 或 `same_preset`，覆盖所选条件的默认值。
同一个 agent ID 的同一模式在配置中只能出现一次；比较不同 reset 策略时换一个 ID。
若已有配置，用 `--agents /path/to/agents.json` 替代 `--model`、`--agent-id` 和访问模式参数，脚本将其复制到新 run。
这只是复用已有适配器的入口，不能让尚未实现的服务协议自动兼容。

<a id="prepare-suite"></a>

## 5. 确认冻结变体（上一步已自动完成）

无需再单独运行一次 prepare。第 4 步不调用模型，也不启动 Genesis；它冻结解析配置、初态构建输入、资产和源码哈希。
场景随后在 evaluate 中构建；reset 使用同一个 preset 在新物理进程中重建，并重新核对初态。
源码或资产变动后必须新建 suite；不要修改旧 suite 的哈希来强行复用。
新教程把 preset 放在本次 run 的 `presets/` 中；旧教程位于 `runs/agent_rollouts/presets/<run_id>/` 的 suite 仍可用。
需要与已有实验严格共享变体时，在新 run 的 prepare 命令中加 `--suite /path/to/suite.json`。
此时会校验并引用原 suite，不重新随机，也不复制场景；`--task`、`--variants`、`--seed` 和场景生成参数不再生效。

<a id="run-evaluation"></a>

## 6. 启动短 evaluation（开始产生模型 API 费用）

```bash
bash tests/run_agent_rollout.sh evaluate --python "$TOPOGYM_PY" --output "$TOPOGYM_RUN_ROOT"
```

脚本自动读取 `run.json` 和 `agents.json`，校验 suite、读取凭据，然后运行 evaluation。
默认设置 `PYOPENGL_PLATFORM=egl`、`LIBGL_ALWAYS_SOFTWARE=1`；若启动前已设定这两个环境变量，会保留你的值。
结束后自动显示结果摘要、每路视频目录和日志位置。
已有 `evaluation/` 时拒绝重跑；应准备新的 run，必要时通过 `--suite` 复用原变体。
底层命令执行失败或结果中有 `pipeline_error` 时脚本返回非零退出码；任务未成功但正常结束不会被算作脚本故障。

环境服务由 runner 自动启动，无需另开服务终端。Codex 在一个回合内就可以完成多次“动作—反馈—reset”。
`--max-calls 4` 限制外层 agent 回合，不是 4 次模型请求，也不是 4 次环境调用。
agent 可以提前停止；允许一次 reset 不代表它一定会使用。

以下均为 `run_agent_rollout.sh prepare` 的参数，默认值用于短实验：

| 参数 | 默认值 | 当前含义 |
| --- | --- | --- |
| `--repeats` | 1 | 每个 agent、条件、变体的独立重复次数 |
| `--max-calls` | 4 | 外层 agent 回合数 |
| `--max-steps` | 100 | 单次 `env.step` 最多执行的控制 tick |
| `--max-total-steps` | 300 | 整个 trial、所有 episode 累计的控制 tick |
| `--max-segments` | 6 | 所有 episode 累计的动作段数；一次 `env.step` 对应一个 segment |
| `--max-resets` | 1 | `same_preset` 条件下最多 reset 次数；disabled 条件为 0 |
| `--max-api-calls` | 100 | 整个 trial 的环境调用次数，查询和被拒绝的有效请求也计数；重复 request ID 不重复执行 |
| `--token-limit` | 3000000 | 所有底层模型请求累计 input + output；reset 不清零 |
| `--max-output-tokens` | 8192 | 每次底层模型请求的输出上限，还会按剩余额度缩小 |
| `--samples-per-camera` | 2 | 每路相机提供的采样帧数 |
| `--worker-timeout-s` | 3600 | trial 的总墙钟预算，包括初始化、模型、动作、录像和 reset；退出回收另有短暂宽限 |

Cast Coil 当前 `dt=0.0025 s`，300 步总模拟跨度仅 0.75 秒，reset 前后的步数合计计算。
短实验用于检查模型是否能使用工具、看到反馈，不能据此判断它是否能完成完整装配。
3M 是消耗上限，不是 API 账户余额或美元费用上限。

## 7. 查看结果、视频和 token 使用量

```bash
bash tests/run_agent_rollout.sh report --python "$TOPOGYM_PY" --output "$TOPOGYM_RUN_ROOT"
```

evaluate 结束时已自动执行一次 report；之后可以重复查看。加 `--json` 输出完整 summary 和 results。
report / watch 也可读取旧实验或 smoke 的 run 目录，不要求它们有新脚本生成的 `run.json`。
运行中 report 显示已经写出的 trial 结果；`recorded trials` 尚未达到总数时不能当作完整评测结论。

新目录包含 episode 层，旧的 `segment_0` 不会被 reset 覆盖：

```text
evaluation/
  agent_astra_simulator_rollouts/cast_coil/rollout_1/repeat_1/
    task_spec.json
    capabilities.json
    topogym_env.py
    trial.json
    token_budget.json
    events.jsonl
    trajectory.json
    scratch/
    episodes/episode_0/
      segment_0.mp4
      segment_1.mp4
      segment_1.json
      cam_high/segment_1.mp4
      cam_low/segment_1.mp4
      cam_left_wrist/segment_1.mp4
      cam_right_wrist/segment_1.mp4
      inputs/segment_1/<camera>/...
    episodes/episode_1/       # 只有发生 reset 才会产生
      segment_0.mp4
      ...
  _private/agent_astra_simulator_rollouts/cast_coil/rollout_1/repeat_1/
    call_1.request.json
    call_1.events.jsonl
    call_1.decision.json
    episodes.json
    episodes/episode_0/worker.log
    episodes/episode_0/initial_audit.json
    result.json
    token_budget.json
  _jobs/job_1.log
```

运行期间在第二个终端监测，脚本自动发现所有 agent / 变体 / repeat，无需手写 trial 路径：

```bash
cd /home/jianwen/topogym
bash tests/run_agent_rollout.sh watch --output runs/agent_rollouts/cast_coil_astra_tools_01
```

默认每 2 秒刷新，`--interval 5` 可调整；`--once` 只查看一次，持续监测用 Ctrl-C 退出。
初始化时还没有账本会显示等待；已完成 trial 的账本仍会列出，因此 watch 不会自动退出。
`used` 是已结算实际 token，`reserved` 是未结算请求的最大预留；worker 日志也有 `[tokens]` 行。
每次环境 API 返回最新账本快照。完整模型事件在该回合结束后保存；实时环境事件写入 `events.jsonl`。
`trajectory.json` 是我们的工具事件/decision 格式，不是完整模型对话或 Harbor ATIF；原始 agent 事件在私有 call 日志中。

判断工具闭环是否成立，检查 `tool_completed` 的 method、对应 episode/segment 媒体，以及 Codex 工具结果。
一个回合内完成闭环时可能只有 `call_1`，不必出现 `call_2`。
视频文件存在不代表模型已实际查看像素；agent 需使用 image viewer 查看返回路径，或自行分析图像。

`succeeded` 才代表 evaluator 判成功；`agent_stopped` 是主动结束，`limit_reached` 是动作/调用/时间预算结束，
`task_failed` 是无法继续重试的任务失败，`token_budget_exhausted` 是模型预算耗尽，`pipeline_error` 是基础设施或执行错误。
某个 episode 失败而 reset 次数仍有剩余时，trial 可以继续。
`first_episode_success_rate` 与允许 reset 的总成功率分开，`total_resets`、`total_ticks` 和耗时也进入 summary。

## 8. agent 实际调用的 SDK

此示例供理解接口，在 runner 提供的 agent 工作区中运行；宿主新终端没有该 trial 的临时连接凭据。
agent 无需导入 Genesis 或阅读场景构建源码：

```python
from topogym_env import connect

env = connect()
description = env.describe()
state = env.get_state(fields=["robot", "bodies"])  # simulator only
gold = env.get_pose("coil_gold", frame="world")
feedback = env.step({}, steps=20)                  # hold control targets
print(feedback["images"], feedback["latest_manifest"])
restored = env.reset()                            # only if reset is permitted
assert restored["total_ticks"] == feedback["total_ticks"]
```

返回 `data` 中放本次调用的数据，其余字段提供 episode、revision、累计预算和图像路径。
`observe()` / `render()` 返回当前暂停 tick 的最新同步材料，不推进物理；RGB 的 `data.observation` 为 `{}`。
Cast Coil `get_pose` 支持 `coil_gold`、`coil_silver`、`left_hand`、`right_hand`，当前只支持 world 坐标，
单位 metres、四元数 wxyz。机器人手的 pose 指 gripper_link，不是指尖中心。
动作仍为关节/夹爪位置目标，完整参数看 `task_spec.json`；未新增隐式抓取或物体传送能力。

普通 Python 的函数、循环和数值计算都在 agent 工作区执行；每次 `env.step` 进入可信执行器并被记录。
多个脚本连接同一环境，状态不会因 Python 进程退出而丢失。SDK 发送 revision 防止旧动作在 reset 后执行。
遇到 stale revision 时先 `observe()` 检查新状态，再决定是否重做计划；不要盲目重发旧动作。

## 9. 扩大到共享变体与三次重复

换一个全新目录，用 `--access-mode both` 自动生成两种配置，`--variants` 设置 x、`--repeats` 设置 3：

```bash
bash tests/run_agent_rollout.sh prepare --python "$TOPOGYM_PY" \
  --output runs/agent_rollouts/cast_coil_astra_compare_01 \
  --agent-id astra --model gpt-6-astra --access-mode both --variants 10 --repeats 3
```

这条命令只做准备，不启动付费模型。它仍使用短程预算；开展正式实验时，需在 prepare 命令中按实验需求增加
`--max-total-steps`、`--max-segments`、`--max-api-calls` 和总墙钟预算，并在开始比较前固定这些值。
之后对这个新目录执行第 6 节的 evaluate 命令。两种模式使用同一 suite；x=10 时共 60 个 trial，
每个 trial 的 3M token 上限独立，内部 reset 不增加 trial 数量。
当前执行器顺序运行 trial；跨 repeat 不复用模型 thread 或 scratch。

比较另一个已接入的模型时，新建 run 并使用 `--suite runs/agent_rollouts/cast_coil_astra_compare_01/presets/suite.json`，
同时保持相同的 repeats 和预算参数；不要只靠相同 seed 重新生成来代替共享冻结 suite。

这两档同时改变状态信息和 reset 权限，不能把成绩差异只解释为视觉与真值信息差异。
当前布局随机化和 pilot evaluator 也尚未构成已完成物理资格验收的正式 benchmark，`physics_qualified=false` 保留。

## 10. 常见故障

| 现象 | 处理 |
| --- | --- |
| `You have no credits remaining` / API quota | 检查所用模型服务的 API 额度；本文 OpenAI 示例需检查 Platform key 所属组织/项目的 API 计费，当前聊天可用不说明该 key 有 API 余额 |
| 缺 key / 模型无权限 | 检查环境变量是否在本次启动命令中传入、模型名与项目权限；不打印 key |
| `bwrap` 或工具不可见 | 先运行 preflight，核对系统工具路径、namespace 和 localhost 权限 |
| `Episode initialization/transport failed` | 查看 `_private/.../episodes/episode_N/worker.log`；其中保留 Genesis 或初态审计的具体错误 |
| pose / state 被拒绝 | 检查 access mode 和 `capabilities.json`；RGB 条件的拒绝是预期行为 |
| reset 被拒绝 | 检查 reset_policy、max_resets、trial 是否成功或预算已用尽 |
| `Stale state revision` | 当前状态已被另一个脚本或 reset 改变；先重新观察再规划 |
| 只有初态、没有动作视频 | 查看 API/模型错误和 tool 事件；不能据初态视频判断模型接入成功 |
| 依赖哈希变化 / 目录已存在 | 新建 run ID 和 suite，保留历史记录；当前没有原目录自动续跑 |

完成本终端操作后可运行 `unset TOPOGYM_MODEL_API_KEY`。
