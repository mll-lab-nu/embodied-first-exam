# 历史兼容协议：固定变体的 segment rollout

本文保留旧 `interaction: segments` 的行为与验证记录。新实验请使用
[当前工具驱动 pipeline](agent_rollout_pipeline_zh.md) 和 [实用手册](agent_rollout_usage_zh.md)。
本页“没有 reset”等约束仅适用于旧 segment 模式。

实现：[`topogym/agent_rollout/`](../../../topogym/agent_rollout/)。它复用
`agent_bridge.Session` 的动作校验和连续物理执行；模型只访问新的 rollout 输入包。
旧 bridge 的 HTTP、本地队列、计量和任务接口保持兼容。

已有 OpenAI API key 时，从[API key 接入与 evaluation 分步教程](model_service_design_zh.md#openai-api-evaluation)开始：
使用现有 Codex provider 完成环境检查、认证、一次短评测及共享变体的重复评测。
[独立模型服务与 Prompt 设计草案](model_service_design_zh.md)另行整理模块边界与后续接口；其中拟议的模型服务入口尚未实现。

## 实验单位与输入条件

一次准备产生一个共享的 **suite**：每个任务预先采样 x 个场景变体，保存解析后的配置、
随机种子、构建入口、静态知识及依赖哈希。所有 agent 和输入条件使用同一组变体，
避免模型差异和场景差异混杂。`rollout_i` 是第 i 个变体，`repeat_j` 是它的第 j 次独立尝试。
默认每变体重复 3 次。scene seed 与 agent 随机性分开；Codex 的采样随机性不声明为可设 seed。

| 条件 | 实时状态 | 额外材料 |
| --- | --- | --- |
| `rgb` | 所有 3/4 个视角的 RGB | 通用任务目标、机器人控制接口、单位及相机说明 |
| `rgb_privileged` | 同样的 RGB | `privileged.json`：该变体冻结的场景配置和构建知识 |

两种条件的 `obs` 都是 `{}`，不附带实时物体或机器人关节真值。这里严格落实“初始只知道 RGB”：
机器人接口文档是操作 API 的公共说明，不是传感器测量。静态 privileged knowledge 不包括现成解法，
也不意味着开放运行中的 simulator state。后续若研究需要 proprioception，应作为另一个明确条件实现。

模型侧的 prompt 与任务文字统一使用英文，响应的自然语言及 `decision.reason` 也要求英文。
当前 Cast Coil 已包含明确的终态：两件充分嵌合、外缘对齐，形成具有方形外轮廓和中央开口的紧凑盒状整体，
放到桌面并释放，稳定保持至少 0.5 秒模拟时间。形状描述参考
[Hanayama 官方说明](https://hanayama-toys.com/product/cast-coil/)，结合本项目保留孔洞和设计间隙的几何；
不要求将零件压成无缝实心正方体。两种观测条件共用这段目标说明。英文示例见
[模型服务设计草案](model_service_design_zh.md)。

## 两阶段生命周期

1. `prepare` 为全部任务采样并冻结全部变体；在 `suite.json` 完成前不能开始评测。
2. `evaluate` 只读取 suite；每个 repeat 用新模拟器进程从同一预设重建初态，用全新的 agent 会话求解。
3. 开始时渲染全部视角，不推进物理；生成静止一秒的 `segment_0.mp4`。
4. 模型生成 Python action segment，指定自己的步数；服务预检查整个脚本，再执行。
5. 同一个环境实例执行完该段后暂停，记录 MP4；视频解码出的图片作为下一轮附件。
6. agent 可以检查任意历史图片/manifest，或者在自己的工具里从 MP4 提取帧，再生成下一段。
7. evaluator 成功/失败、agent 停止、调用/动作预算到达或基础设施错误时结束。

**只在 repeat 之间重建初态。repeat 内没有 reset、回滚、重新随机化、失败重启或恢复旧现场。**
无效脚本消耗一次模型调用，但不执行动作；开始执行后失败则保留已有证据，不撤销动作。

实现冻结的是完整解析配置与构建输入，而非通用 Genesis solver checkpoint。
初始化前固定 `gs.init(seed=...)`，不再调用变体生成器。程序会严格比较同一变体各 repeat / 各 agent 的
物理初态哈希，不一致则在首次模型调用前拒绝本次尝试。Cast Coil 审计两件物体的位姿、线/角速度和机器人状态；
通用 adapter 可提供仅供 operator 使用的 `initial_state()`，否则只能检查 `observe()`，并在结果中标注范围。
RGB 另作比较：默认要求逐字节一致；Cast Coil 在准备文件中明确冻结容差，8-bit 通道均值绝对差 ≤0.01、
最大通道差 ≤32、变化像素比例 ≤0.001，处理光栅边缘极少数像素的非确定性。实际差异逐相机保存，
绝不使用图像容差放宽物理初态检查。这个检查不宣称覆盖所有隐藏 solver buffer 或跨 GPU 的位级确定性。
源文件在准备后改变会拒绝执行，应以新名字重新准备 suite。

## 目录

专用空间为 `runs/agent_rollouts/`，不混入 `demos/` 的完整成功机器人演示目录。

```text
runs/agent_rollouts/
  presets/my_suite/
    suite.json
    cast_coil/rollout_1.json
    cast_coil/rollout_2.json
  my_evaluation/
    evaluation.json
    results.json
    summary.json
    agent_codex_rgb_rollouts/
      cast_coil/
        rollout_1/
          repeat_1/
            task_spec.json
            segment_0.mp4
            segment_0.json
            segment_1.mp4
            segment_1.json
            policy_1.py
            segment_2.mp4
            cam_high/segment_0.mp4
            cam_high/segment_1.mp4
            cam_low/...
            cam_left_wrist/...
            cam_right_wrist/...
            frames/segment_0/<camera>/000000.png
            frames/segment_1/<camera>/000000.png
            inputs/segment_1/<camera>/000000.png
            scratch/
          repeat_2/...
          repeat_3/...
        rollout_2/...
    agent_codex_rgb_privileged_rollouts/...
    _private/<agent>/<task>/<variant>/<repeat>/
      episode/             # bridge 原始记录、隐藏状态、私有资产
      call_1.request.json  # 实际 prompt 和图片列表
      call_1.events.jsonl  # Codex 原始事件及 usage
      call_1.decision.json
      result.json
    _jobs/                 # 进程任务和 operator 日志
```

`rgb_privileged` 的 repeat 根目录另外有 `privileged.json`。
每个根目录 MP4 是固定顺序的 2×2 总览；单视角 MP4 完整保留，三视角时第四格为黑色。
初始静止片段不产生物理动作。动作片段保留段开始帧和每个完成的控制 tick，
视频帧率为 `1 / control_dt_s`，因此 N 步对应 N+1 帧。播放时长 `(N+1)*dt` 与
实际模拟跨度 `N*dt` 在 manifest 中分开记录。内部 physics substeps 不作为独立相机帧。

每份公开 manifest 保存相机顺序、各视频路径/哈希、帧数、每帧 tick/time、原始 PNG 路径、
请求/尝试/完成的步数及模型默认输入图片索引。它不包含旧 bridge 的 `observation`。
默认每相机抽取 4 张图片，始终包含起点和终点；初始状态只需每相机一张。
这些默认附件从归档 MP4 解码，完整视频和逐 tick PNG 仍可回看，不把抽帧当作完整视频理解。

## 运行

真实 OpenAI 调用的完整复制执行步骤见[用户教程](model_service_design_zh.md#openai-api-evaluation)。
关键接入点是把 Platform API key 作为 `CODEX_API_KEY` 传给 `evaluate` 进程，
并在 agents JSON 中明确填写 `provider: "codex"` 和 `model: "gpt-6-astra"`。
下面保留通用命令与无模型 smoke test。

只测试管线，无 Genesis、无模型调用：

```bash
python -m topogym.agent_rollout prepare \
  --task counter --variants 2 --seed 20260920 \
  --output runs/agent_rollouts/presets/counter_example

python -m topogym.agent_rollout evaluate \
  --suite runs/agent_rollouts/presets/counter_example/suite.json \
  --agents configs/agent_rollout/counter_smoke.json \
  --output runs/agent_rollouts/counter_example --repeats 3
```

真实 Genesis 接入首先提供 Cast Coil。准备时预采样桌面中心 ±15 mm、yaw ±5°，
保存 inline 几何模板、全部解析配置和机器人资产/源码哈希。这是布局随机化，不是已通过 IK
与可解性资格验证的几何变体生成器。底层 adapter 的 `physics_qualified=false` 保留到结果中。

```bash
.venv-gs121-nyx/bin/python -m topogym.agent_rollout prepare \
  --task cast_coil --variants 10 --seed 20260920 \
  --backend cpu --renderer rasterizer \
  --output runs/agent_rollouts/presets/cast_coil_example
```

复制 [`codex_segments.example.json`](../../../configs/agent_rollout/codex_segments.example.json)，
将 `model` 换成账户可用的明确模型名。不要在配置文件里保存 API key。

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 \
.venv-gs121-nyx/bin/python -m topogym.agent_rollout evaluate \
  --suite runs/agent_rollouts/presets/cast_coil_example/suite.json \
  --agents /path/to/my_agents.json \
  --output runs/agent_rollouts/cast_coil_my_model --repeats 3
```

`prepare` 不调用模型。只有使用 `provider=codex` 或实际模型 command 的 `evaluate` 才发起模型请求。
`replay` 是固定脚本测试传输，不是模型评测。输出目录必须全新，禁止覆盖或自动续跑。

公共限制：`--max-steps 1000` 每段、`--max-total-steps 10000` 每次尝试、
`--max-segments 50`、`--max-calls 100`、`--worker-timeout-s 3600`。
模型自主选择这些上限以内的任意段长度；三个 repeat 的这些预算相同。

## Code agent 接口与读取边界

第一版通过官方 `codex exec --json` 驱动编码 agent；同一 repeat 后续调用使用明确 thread ID 的
`codex exec resume`，不同 repeat 不复用 thread。模型收到真实的 `--image` 附件与目录读取说明。
输出由 JSON Schema 约束为 `segment / inspect / stop`，然后由已有受限脚本执行器执行。
可用任意 Python/数值库在 agent 的 scratch 中做规划，再把控制命令提交给环境；不向模型暴露 Genesis 对象。

官方接口依据：[OpenAI 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、
[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)。
这里使用可替换的 CLI JSONL transport，不要求给 Python 项目安装 Node SDK。

Linux Codex provider 强制使用 `bwrap`：只读挂载本 repeat 到 `/workspace`，仅 `scratch/` 可写，
提供系统工具、独立临时 Codex home 和输出目录。仓库、其他 repeat、私有记录、用户配置/插件/记忆均不挂载。
默认预算模式下，真实 API key 仅由 worker 的本地计量代理持有，agent 仅收到临时代理凭据，
不挂载个人认证文件；无预算模式才沿用原来的只读认证挂载和 API 环境变量。
保留网络以连接模型服务。这个实现隔离本机文件输入，不宣称是防止网络搜索现成解法的网络防火墙。
依赖 `bwrap` 和当前支持 `--ignore-user-config / --output-schema / --image` 的 Codex CLI；缺失时明确失败，不降级为无隔离。

另有 `provider=command`：配置 `command` 为 argv 列表，stdin 接收
`{prompt, images, public_dir, call}` JSON，stdout 返回 decision 或 `{decision, usage}`。
它便于接其他供应商/远程容器，但本地裸 command 只标记 `observation_isolation=prompt_policy`，
不能自动视为与隔离 Codex 同等的严格输入条件。

Codex 默认启用每个 repeat 独立的 `--token-limit 3000000`，每个底层请求先经官方 input count，
持久化预留，再以缩减后的 `max_output_tokens` 请求模型。`--max-output-tokens` 默认 8192，包含推理输出。
每个底层请求结算后更新实际用量和英文余额提示；`token_budget.json` 与 worker 日志提供监测。
用量未知时保留预留并停止，禁止自动重试；未接入的计费端点不转发。完整说明见
[3M 预算与监测](model_service_design_zh.md#token-budget)。原始 Codex usage 保留用于审计，不重复相加。
`--token-limit 0` 显式关闭限制；`command` 暂不支持默认的逐请求预算，replay 不调用模型。

## 评测结果

主要指标是每个 agent/输入条件/任务的 trial success rate，以及各变体 repeat 成功率的平均值。
`any_repeat_success_rate` 单独报告，不把三次里任一次成功当作三次都成功。
基础设施错误保留在分母并单列 `pipeline_errors`，不静默丢弃；原始逐次结果保留全部状态。
`success_physics_qualified` 同时要求 evaluator 成功和 adapter 已完成物理资格验证。
当前 pilot evaluator 的成功不能直接替代正式物理验收。

## 其他任务接入

`--preparer task_id=package.module:prepare` 接收一个 `prepare(seed, options) -> dict`：

```python
{
    "factory": "package.module:create",
    "kwargs": {"resolved_config": frozen_json_config},
    "knowledge": {"construction": "...", "resolved_config": frozen_json_config},
    "sources": {"/absolute/dependency/path.py": "sha256..."}
}
```

preparer 必须一次性完成所有随机抽样并把数据嵌入 `kwargs`；依赖文件必须记录 hash。
`create(asset_dir, **kwargs)` 只从冻结参数构建环境，返回已有 `TaskAdapter`，不重新采样。
已有任务的 variant generator 可以在 prepare 中调用，其解析配置/几何/初态要接到对应 create。
不能只传一个 seed 给不读取这个 seed 的旧 adapter，或者复制基础环境后声称得到 x 个随机变体。
目前其他任务已有 agent_bridge adapters，但尚未自动接通这个冻结变体协议；解绳结在项目里的 task ID 为 `knot_untying`。

运行前先执行 `bash tests/check_agent_rollout_setup.sh` 检查 Linux 依赖与隔离 Codex 接口；
加 `--regression` 可同时运行 rollout、task-spec 和 token-budget 回归检查，需允许本机临时 HTTP 端口，
全程使用模拟 API 响应，不调用真实模型。
单独的管线回归入口仍为 `python -m unittest tests.check_agent_rollout -v`。

2026-09-20 验证记录：

- 新管线与原 bridge/task-spec 检查联合通过；provider 使用模拟响应，没有发起模型请求。
- [合成任务评测](../../../runs/agent_rollouts/20260920_counter_v2/summary.json)：2 个冻结变体 × 2 种输入条件 × 3 次重复，共 12 次；跨片段连续性、跨 repeat 初态及视频反馈通过。这是 replay 流程检查，不是模型成功率。
- [真实 Cast Coil 短程检查](../../../runs/agent_rollouts/20260920_cast_coil_v3/summary.json)：同一固定变体三次独立重建，物理初态哈希完全一致，每次 2 段共 5 个控制 tick，无 pipeline error。脚本只保持目标，不构成装配/拆解成功。
- 真实片段：[初态总览](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/segment_0.mp4)、[第 1 段](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/segment_1.mp4)、[第 2 段](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/segment_2.mp4)。
- 第 1 段原始视角：[cam_high](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/cam_high/segment_1.mp4)、[cam_low](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/cam_low/segment_1.mp4)、[左腕](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/cam_left_wrist/segment_1.mp4)、[右腕](../../../runs/agent_rollouts/20260920_cast_coil_v3/agent_hold_smoke_rgb_rollouts/cast_coil/rollout_1/repeat_1/cam_right_wrist/segment_1.mp4)。

历史 suite 记录执行当时源码哈希，后续实现变化后不能直接重用；按上述 `prepare` 命令新建 suite 即可。
