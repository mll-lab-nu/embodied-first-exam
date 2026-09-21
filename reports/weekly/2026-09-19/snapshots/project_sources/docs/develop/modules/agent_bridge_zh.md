# Coding agent 分段交互协议 v1

实现位于 [`topogym/agent_bridge/`](../../../topogym/agent_bridge/)，独立于具体任务、模型和 harness。
包含 Python 客户端、可选 HTTP API、无 HTTP 的本地文件队列、OpenAI Responses 参考 harness，以及 Cast Coil / Horseshoe Ring / Cast Keyhole / Interlocked Claws / Hedgehog in Cage / Lock Picking 的真实 Genesis 接入。
机器人运行代码已拆为公共模块，见 [adapter 分层](agent_adapter_architecture_zh.md) 与 [Keyhole 接入](cast_keyhole_agent_adapter_zh.md)。
Horseshoe 的本地创建、初态和验证范围见 [adapter 说明](horseshoe_agent_adapter_zh.md)；本地交互不需要端口或浏览器。
[Hedgehog 接入说明](hedgehog_agent_adapter_zh.md) 包含 Panda 七关节／夹爪半开口接口、本轮三视角、创建命令和可复制给 Codex 的 prompt。
[Lock Picking 接入说明](lock_picking_agent_adapter_zh.md) 使用同一 Panda 接口，从承托架抓取到 END 释放，支持本地创建和自动迭代。
[Interlocked Claws 接入说明](interlocked_claws_agent_adapter_zh.md) 复用 ALOHA 接口，从基础双手辅助预抓持初态开始，目标为分离后落架释放静置。
[Buzz Wire 3D 接入说明](buzz_wire_agent_adapter_zh.md) 复用 Panda 和公共刚体执行循环，以真实摩擦抓持完成沿线通行和末端松手；提供三路观测、本地命令与 solver prompt，完整自主通行尚未验证。
默认累计预算 **2,000,000 tokens**，可调低，v1 不允许调高。这是整个 episode 的累计用量，不是单次模型上下文长度。

[Knot Untying 接入](knot_untying_agent_adapter_zh.md) 提供 CUDA FEM/IPC、整绳接触选带、四路观测和本地 solver prompt；不沿用刚体焊接抓持。

要使用 `runs/agent_test_demos/{states,agent_solutions}` 并另开 Codex 会话做求解测试，按 [新会话操作指南](agent_test_demos_zh.md) 启动；其中明确区分原生 Codex 的能力试测和当前 API harness 的严格 token 计量。

## 工具与参考资料权限

当前策略为 **工具开放、从头求解**。外部终端、通用 Python 库、图像/视频分析、数值优化和自行建立的离线规划均允许；
任务输入限于公开任务包、当前 episode 观测和通用机器人知识。不得读取仓库实现源码、已有 demo 视频/解法、其他运行轨迹、私有资产或 simulator state。
物体构型由 agent 从本轮相机观测与动作反馈推断；不提供或允许外部物体参考图、成品图、CAD、预计算形状与目标相对变换。
允许 agent 基于本轮观测自行重建、建立几何假设和验证，不把缺少参考图当成接口信息缺失。
这同样约束搜索、远程工具和委派：不能借另一种工具取得受限资料。保留不可回滚、不得修改评测器等执行契约。

`--allow-internet` 默认开启，允许查通用资料/工具文档和下载通用依赖；`--no-allow-internet` 关闭外网工具使用。
两者均不允许搜索本任务的现成解法。本机 bridge 与宿主管理的模型通信不属于此开关限制的联网研究。
策略写入 `session.tool_policy` 和每轮 prompt；同一轮不由 solver 修改。
声明的 `enforcement=prompt_policy` 表示提示词约束，强制工具/网络访问边界须由宿主 harness 实施。
开放权限不自动增加 harness 的能力；当前 `openai_harness` 仍只有 segment/inspect/stop，未增加终端或联网工具。

## 执行契约

1. 评测器创建唯一环境实例、完成初始化，保存 `initial/` 多视角观测。
2. agent 读取观测和带剩余预算的 prompt，编写 action segment。
3. harness 提交代码、唯一 `request_id`、`expected_segment`；正式模式另附已结算的 `call_id`。
4. 服务预检查完整脚本及全部动作，然后在同一个环境实例上执行，每步保存全部相机反馈。
5. 返回 manifest 地址。agent 自行决定查看哪些历史 frames、如何分析。
6. 重复直到 evaluator 判定成功/失败、agent 放弃或预算耗尽。

**已执行的动作不能撤销，不能恢复 simulator state。** 没有 reset、restore、fork 或继续旧运行的 API。
每个服务进程只持有一个 episode，同一输出目录不能再次打开。进程崩溃后保留证据，新试验必须使用新的目录和预算。
状态停留在 `executing` 的旧目录应视为中断证据，不能重建现场并继续计为同一次试验。

相同 `request_id` / 内容重复提交返回原结果，不再步进；同 ID 不同内容报错。
`expected_segment` 拒绝依据旧观测提交的新动作。终态之后不再接受动作。
代码/动作预检查失败不推进环境；执行或录制中出错会终止 episode，保留已有反馈，不回滚。

每段保存开始帧和每个成功 control tick 后的帧；N 步正常执行得到每相机 N+1 帧，初始观测另存一份。
当前 Genesis adapter 的一个 tick 等于一次 `scene.step()`，内部物理 substeps 不单独渲染。
终止条件在每个 tick 后检查，可能提前结束长段。manifest 区分 `requested_steps / attempted_steps / executed_steps`。
求解器在一步中途报错时，尝试步数可能大于完成步数，不能假定失败步没有改变状态；相机报错后不补造缺失帧。

v1 使用无损 **PNG frames** 作为完整反馈，页面提供同步回放，不强制压成 MP4 或自动丢帧。
完整机器人 demo 的归档仍按仓库 `AGENTS.md` 单独执行，接口冒烟试验不属于完整 demo。

## 直接与 ChatGPT 手动测试

先运行不依赖 Genesis/API key 的小任务，在仓库根目录执行：

```bash
python -m topogym.agent_bridge --task counter --mode manual \
  --output runs/agent_bridge/manual_counter_001
```

打开 <http://127.0.0.1:8765>。smoke task 只要求把标记从 x=0 移到 x=3，不代表拓扑求解能力。

1. 复制页面中的下一轮 prompt，选择初始或历史图片，发给 ChatGPT。
2. 将返回的纯动作代码粘贴到页面，如 `env.step({"dx": 1}, steps=2)`。
3. 填写本轮 token 估算并执行，通过时间轴回看完整同步视角。
4. 复制更新后的 prompt 和选择的反馈图片，继续下一段。

页面每秒刷新累计用量曲线、已记账、预留量、剩余预算和状态。
manual 模式不填写 token 字段时，仅按当前 prompt/代码字符数除以 4 粗估，不涵盖完整聊天历史、图像或隐藏推理。
manual 没有任何用量上报时，prompt 和页面显示“未测量、真实余额未知”；有上报时显示“估算剩余”，不会宣称精确余额。
可以填写自己的完整估算，但始终标记 `manual`，`success_within_budget` 始终为 false。
**手动路径用于测试流程，不能证明 ChatGPT 严格在 2M tokens 内完成任务。** 可审计预算试验使用 metered harness。
本地页面不自动连接 ChatGPT 网页，使用复制 prompt、附加图片、粘贴代码的人工桥接。

真实 Cast Coil 装配环境（默认 CUDA / Nyx）：

```bash
.venv-gs121-nyx/bin/python -m topogym.agent_bridge \
  --task cast_coil --objective assemble --mode manual \
  --output runs/agent_bridge/manual_cast_coil_001
```

CPU 显式选择光栅渲染：

```bash
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 \
  .venv-gs121-nyx/bin/python -m topogym.agent_bridge \
  --task cast_coil --backend cpu --renderer rasterizer --mode manual \
  --output runs/agent_bridge/manual_cast_coil_cpu_001
```

该 adapter 使用 ALOHA 2 双臂（ViperX 300 6DOF 衍生型号、原生 ALOHA 2 夹爪）和四路相机，初始化为 home 与桌面自由物体，没有自动抓取或抓持辅助。
支持 `--objective disassemble`。动作可同时设置两臂的六个关节角及夹爪滑轨位移，`{}` 表示保持控制目标。
单位、限位、关节/末端观测随 prompt 提供，以下是实际动作语法，不是解法：

```python
env.step({"left": {"gripper": 0.037}, "right": {"gripper": 0.037}}, steps=20)
q = obs["robot"]["left"]["arm_qpos"]
for i in range(10):
    env.step({"left": {"qpos": [q[0]+0.001*i, q[1], q[2], q[3], q[4], q[5]]}})
```

`task_spec_version=3` 提供文字任务目标、成功条件、关节顺序/限位、夹爪滑轨含义、
末端与抓取中心区别、世界/桌面坐标系，以及 `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 的作用与标定。
全部相机默认 320×180；内参来自当前模拟器 FOV，不能当作实机内参。腕相机挂在 `gripper_base`，不是 `hand_pos` 对应的 `gripper_link`。
新运行逐帧保存 `observation.camera_poses`，使随动外参与 RGB 对齐；旧运行没有这个字段时不补造。
不提供物体参考图、尺寸/几何模型、预先解释的层次构型或目标相对变换；任务物体的实时真值位姿也不作为观测公开。

Cast Coil 当前是 **pilot evaluator**：装配相对位姿误差 <1 mm / 0.02 rad，或拆解世界坐标 AABB 间隙 >10 mm；
脱离机器人接触、线速度 <1 mm/s、角速度 <0.02 rad/s，并维持 0.5 秒。件间接触穿透 >1 mm 或掉落则失败。
它尚未覆盖完整 demo 的全部机器人碰撞、连续几何和跨时间步验收，明确标记 `physics_qualified=false`。
`success_within_budget` 仅表示当前 evaluator 通过且计量在预算内，不能等同于正式物理验收。

## GPT 自动闭环与 2M 计量

启动正式计量服务：

```bash
.venv-gs121-nyx/bin/python -m topogym.agent_bridge \
  --task cast_coil --mode metered --token-limit 2000000 \
  --output runs/agent_bridge/gpt_cast_coil_001
```

另一个终端设置自己的 `OPENAI_API_KEY` 环境变量后，显式选择可用视觉模型：

```bash
python -m topogym.agent_bridge.openai_harness \
  --model YOUR_VISION_MODEL --url http://127.0.0.1:8765 \
  --max-output-tokens 8192 --history-turns 8
```

仅运行此 harness 才会发起付费 API 调用；浏览器不接收 key。使用标准库，不需额外安装 OpenAI SDK。
模型输出 `segment / inspect / stop` JSON。`inspect` 可读取任意保存的 PNG 或 manifest，不推进环境。
参考 harness 默认提供全部相机最新一帧和最近 8 轮对话；这是可替换的 harness 策略，benchmark 保存的完整历史不受影响。
provider 原始响应、当前 prompt、输入摘要哈希、选择的历史路径及 harness 参数存于 `private_usage/`。

- 消耗按所有调用的 `input_tokens + output_tokens` 累计，包括重送历史、图像、分析、回看和代码修复。
- cached tokens 已包含在 input 内，reasoning tokens 已包含在 output 内，不重复相加。
- 调用前通过官方 input-token count 接口计算完整请求，预留 `input + max_output`；输出上限裁到剩余预算。
- 完成后按 usage 结算并释放未用预留；实际 input/output 超过各自预留时记录实际值并终止为协议失败。
- 流式期间显示预留量和收到的字符数；精确累计在 usage 到达后更新，不将字符数冒充 token 数。
- 模型请求中的预算文本取调用开始前余额，下一段 prompt 包含结算后余额；用尽后不再执行动作。
- 流中断且没有 usage 时保留预留并终止，`exact=false`；不自动重试计费请求，不将未知用量当零。
- 剩余预算连下一次输入都无法容纳时，以 `budget_exhausted` 结束；2M 不扩展单次上下文窗口。

官方依据：[usage](https://developers.openai.com/api/reference/python/resources/responses/methods/retrieve)、
[输入 token 计数](https://developers.openai.com/api/docs/guides/token-counting)、
[流式事件](https://developers.openai.com/api/docs/guides/streaming-responses)。
模型可用性和 count 支持需账户实际验证；本次开发未发起付费 GPT 求解试验。

## 外部 coding agent / harness API

基础地址为 `http://127.0.0.1:8765`，所有 POST 使用 JSON 和 `X-TopoGym: 1` 请求头。
服务只监听 loopback，拒绝跨域写入和异常 Host，面向本机受信任 harness，不是公共多租户服务。
usage 由受信任 harness 上报；v1 不独立校验 provider receipt 签名，不应把计量端点交给受测模型任意修改。
动作脚本无法调用 HTTP、导入模块、读写文件或修改计量。

| 路由 | 用途/JSON 字段 |
| --- | --- |
| `GET /v1/session` | 状态、预算、观测、全部 segment 清单 |
| `GET /v1/prompt` | 含当前 token 余额的 prompt |
| `GET /artifacts/<path>` | 公开 frames、manifest、代码、段开始 prompt，以及 adapter 明确发布的基础文字参数；不提供物体参考图、私有资产/usage 日志 |
| `POST /v1/usage/reserve` | `{call_id,input_tokens,max_output_tokens,model}`，调用前预留 |
| `POST /v1/usage/progress` | `{call_id,output_chars}`，累计流式字符数 |
| `POST /v1/usage/complete` | `{call_id,usage,response?}`，usage 至少含 input/output/total_tokens |
| `POST /v1/usage/estimate` | `{call_id,input_tokens,output_tokens}`，仅 manual |
| `POST /v1/segments` | `{request_id,expected_segment,code,call_id?}` |
| `POST /v1/finish` | `{reason,outcome?}`，failed 或 budget_exhausted，不允许 agent 声明成功 |

正式模式每段需要一个未被动作段消费的非零、已结算 receipt；存在未结算调用时拒绝执行。
所有分析调用也要结算，即使没有产生动作。重复 receipt 幂等，冲突用量拒绝。
HTTP 409 表示协议/输入拒绝；运行中物理/相机错误返回已保存的失败 segment manifest。
请求超时后使用相同 `request_id` 和内容重试，不生成新 ID；进程丢失后不能重建旧 episode。

```python
from topogym.agent_bridge.client import Client

client = Client()
state = client.state()
print(client.request("/v1/prompt")["prompt"])
result = client.submit(
    'env.step({}, steps=20)',
    request_id="unique-request-001",
    expected_segment=state["next_segment"],
    call_id="finalized-provider-call-001",  # manual 可省略
)
feedback = client.request("/artifacts/" + result["manifest"])
```

执行语言是有界 Python 子集：赋值、`for/range`、有限数值加减乘除、列表/字典/索引、`env.step`。
`obs` 固定为段开始时的公开观测。不支持 exec/eval、import、函数定义、while、任意属性访问或段内新视觉读取。
默认每段最多 1000 ticks（服务可配置到 10000），代码最多 64 KiB，另有限制运算量和嵌套深度。
复杂 Python/规划库/文件分析在外部 harness 自己的隔离环境执行，再生成动作段提交。
v1 不提供通用 shell sandbox 或任意 Python 的安全执行器，不将 simulator 对象交给模型。

## 接入其他任务与产物

实现 [`TaskAdapter`](../../../topogym/agent_bridge/protocol.py) 六个方法：
`describe / validate_action / step / observe / render / evaluate`。
任务负责合法控制、允许的传感器和判定；会话层负责预算、序列、存档和协议。
`render` 返回全部声明相机的 PNG bytes，不步进；`validate_action` 不改变状态；`step` 只推进一个明确的 tick。
`evaluate` 应锁存失败，不让后续恢复抹去违规历史。
`describe` 应包含文字目标、机器人与传感器基础说明；可通过可选 `public_assets` 映射发布基础 JSON/Markdown 参数，
Session 复制到 `public_assets/` 并记录 SHA-256，只允许 API 读取映射中明确公开的文字文件。
图片只能来自本轮 `initial/` / `segment_*/` 的观测；Session 拒绝参考图片发布及旧 `goal_reference` 描述，导出工具也拒绝带有旧参考数据的任务包。

现有 Genesis 场景可用 [`GenesisAdapter`](../../../topogym/agent_bridge/adapters.py)，
传入 scene、cameras、只设置控制目标的回调、公开观测和 evaluator。
自定义 factory 签名为 `factory(asset_dir) -> TaskAdapter`，通过 `--factory your_package.your_task:create` 接入。
Cast Coil 专用逻辑在 [`tasks/cast_coil/agent_adapter.py`](../../../topogym/tasks/cast_coil/agent_adapter.py)，不放进通用模块。

```text
episode/
  session.json              # 状态、计量、是否在预算内成功
  next_prompt.txt           # 下一轮提示
  events.jsonl              # 用量和段开始/结束事件
  requests.json             # 已完成请求幂等记录
  public_assets/            # 可选基础文字参数；不含物体图片或几何数据
  initial/manifest.json
  initial/<camera>/000000.png
  segment_001/policy.py
  segment_001/prompt.txt
  segment_001/manifest.json # 逐帧 tick/time、各相机路径及 SHA-256
  segment_001/<camera>/000000.png
  segment_001/<camera>/000001.png
  segment_002/...
  private_assets/            # 不通过公开 API 提供
  private_usage/             # provider 响应及请求摘要
```

验证入口：`python -m unittest tests.check_agent_bridge -v`。
27 项检查覆盖脚本限制、预算、用量/动作幂等、过期段号、预检查、部分执行/录制失败、完整多视角反馈、
HTTP 约束、历史读取、独立 solver 客户端、模拟 provider 闭环、工具/联网策略、公开资产白名单及干净任务包导出。HTTP 检查需要本机临时端口。
另有 `.venv-gs121-nyx/bin/python -m unittest tests.check_agent_task_spec -v`，4 项离线检查文字目标、机器人接口、相机投影/外参及物体真值不泄漏，均不启动 Genesis。
已在 CPU / rasterizer 真实 Cast Coil 连续执行两个 segment（2 步保持、10 步双夹爪控制），验证四路初态/全段 frames、跨段状态连续及重试不重复执行；不是任务求解结果。
首轮相关检查共运行 37 项，36 项通过；当时唯一失败为既有 `fiber_bundling` 任务卡的非 candidate 参数轴，与此模块无关。
