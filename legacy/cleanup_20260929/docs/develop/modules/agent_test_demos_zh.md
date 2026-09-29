# 用新 Codex 会话进行 agent solve 测试

这份说明对应 `runs/agent_test_demos/`。环境由操作者启动并持续运行，新 Codex 会话作为受测 solver，只读取公开观测、编写代码、提交动作和分析反馈。
`manual` 在这里指 **token 计量方式**；Codex 仍可自动调用 HTTP 执行整个闭环，不需要人手动逐段点击。

当前直接可测的真实任务是 `cast_coil`（装配/拆解），另有 `counter` 协议小任务。
其他任务即使已有场景、解法或 demo，也尚未接入本模块，不能直接把 `--task` 换成它们的名字。
先由开发者实现对应 `TaskAdapter`、核验动作/相机/判定，再开启独立 solver 会话，避免受测 agent 同时改环境和做题。

## 目录约定

```text
runs/agent_test_demos/
  START_cast_coil_codex_001.sh       # 操作者启动脚本
  README.md                        # 指向本说明
  states/
    cast_coil_codex_001/            # bridge 自动创建，启动前不要预建
      initial/<camera>/000000.png
      initial/manifest.json
      segment_001/policy.py         # 实际执行代码的服务端副本
      segment_001/prompt.txt
      segment_001/<camera>/*.png
      segment_001/manifest.json
      session.json
      next_prompt.txt
      events.jsonl
      private_assets/              # 仅环境端使用
  agent_solutions/
    cast_coil_codex_001/            # 新 Codex 会话的工作目录
      SOLVER_INSTRUCTIONS.md       # 公开规则，不含任务解法
      bridge_client.py             # 独立标准库客户端，无需导入仓库
      bridge_config.json           # URL、任务、计量方式
      TASK_BRIEF.md                # 目标、场景、机械臂和四路相机的基础说明
      task_spec.json               # 机器可读基础参数
      public_assets/              # 可选基础文字参数；不含物体参考图或几何模型
      policies/segment_001.py       # agent 编写，含未执行/被拒绝的草稿
      observations/<id>/           # 每次读取的公开状态和 prompt
      feedback/initial/...         # agent 请求下载的图片/manifest
      feedback/segment_001/...
      requests/<request_id>.json   # 网络发送前保存的不可变请求
      requests/<request_id>.result.json
      notes.md
      result.md
```

`states` 表示观测与执行记录，不是允许恢复的 simulator checkpoint。
同一个 `run_id` 把环境输入输出和 agent 代码关联起来。失败试验也保留，新试验另取 ID，不能覆盖或在旧目录重启。
solver 通过 HTTP 读取公开文件，不需要直接访问 `states/`，尤其不能读写 `private_assets/`。
服务端始终保存完整 frames；客户端默认下载最新帧，agent 可选择 `--all-frames` 或按 manifest 路径取历史。

## 当前记录与下一轮

`cast_coil_codex_001` 已结束：11 段、3320 ticks，最终 failed，真实 token 未计量。
原目录现已更新 v3 基础说明与工具规则，移除上次补充的参考图、几何尺寸和目标相对变换；旧 result/观测/动作证据保持原样。新增说明不能视为旧 agent 当时收到的输入。
旧启动脚本和旧 `states` 只作记录，不能重启或接着提交第 12 段。
原输入文件备份及核对清单位于 `package_history/cast_coil_codex_001/`，不作为新 solver 的输入。
下面以**全新** `cast_coil_codex_002` 为例，不复用上一轮的策略、笔记或反馈。

1. 操作者在独立终端启动环境，保持终端运行：

   ```bash
   cd /home/jianwen/topogym
   .venv-gs121-nyx/bin/python -m topogym.agent_bridge \
     --task cast_coil --objective assemble --backend cuda --renderer nyx \
     --mode manual --token-limit 2000000 --port 8771 --allow-internet \
     --output runs/agent_test_demos/states/cast_coil_codex_002
   ```

   默认 CUDA / Nyx，页面为 <http://127.0.0.1:8771>。如需 CPU 光栅模式，在启动前改 backend/renderer，
   并在命令前设置 `PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1`；不要在运行中切换或重建环境。
   `--no-allow-internet` 可禁止联网查资料；默认允许通用资料，仍禁止现成解法。选择在本轮开始前固定。
   如果端口已被其他任务占用，另选空闲端口；不要复用未知运行的服务。

   服务就绪后，在另一个终端导出干净任务包。此命令只读公开接口，不执行动作；输出目录必须尚不存在：

   ```bash
   cd /home/jianwen/topogym
   python -m topogym.agent_bridge.package \
     --url http://127.0.0.1:8771 --run-id cast_coil_codex_002 \
     --output runs/agent_test_demos/agent_solutions/cast_coil_codex_002
   ```

2. 新建 Codex 会话，仅把以下文件夹作为工作目录，关闭其他项目文件的 IDE 上下文：

   ```text
   /home/jianwen/topogym/runs/agent_test_demos/agent_solutions/cast_coil_codex_002
   ```

3. 给新会话发送：

   ```text
   你现在是受测的机器人任务 solver。工作目录是
   /home/jianwen/topogym/runs/agent_test_demos/agent_solutions/cast_coil_codex_002。
   先读这里的 SOLVER_INSTRUCTIONS.md、bridge_config.json、TASK_BRIEF.md、task_spec.json。
   根据本轮实时多视角观测自行判断物体构型与配合关系，不使用外部参考图、物体几何模型或目标相对变换。
   允许终端、通用库、图像分析和自行编写的规划代码；联网按 tool_policy.allow_internet。
   任务信息只用本包、当前运行观测和通用知识，不读取已有 demo、解法、仓库源码或其他试验，不搜索现成答案。
   环境由操作者启动。先运行 python bridge_client.py observe，读取返回的 prompt，
   用图像查看工具实际查看下载的多视角图片，再自行规划并编写第一个动作段。
   持续执行“观察→编写→提交→观察”，直到服务端终态或明确无法继续。
   每段前后记录依据和结果，不要只给方案，不要读取仓库已有解法，不要修改或重启环境。
   当前是 manual 计量；没有真实 usage 时明确标记 token 未测量，不能宣称通过 2M 预算验收。
   ```

4. 操作者可在浏览器旁观，也可检查 `states/<run_id>/session.json`。试验中只保留一个动作提交者；
   不要在 solver 执行时从浏览器另发动作。agent 以服务端 `succeeded/failed/budget_exhausted` 为结论，写 `result.md`。

如果连接拒绝/超时，先由操作者检查服务和本机端口访问权限；受测 agent 不应自行重新启动环境。
一次请求结果不明时使用 `retry` 原 ID，而不是新建 ID 重做同一动作。

## 给 solver 的工具

下面命令均在该轮 `agent_solutions/<run_id>/` 执行：

```bash
python bridge_client.py status
python bridge_client.py brief
python bridge_client.py observe
python bridge_client.py observe --all-frames
python bridge_client.py fetch segment_001/manifest.json
python bridge_client.py fetch segment_001/cam_high/000010.png
python bridge_client.py submit policies/segment_001.py \
  --expected-segment 1 --request-id seg001_attempt01
python bridge_client.py retry --request-id seg001_attempt01
python bridge_client.py stop --reason "无法继续的具体原因"
```

客户端在发送前把代码和段号存入 `requests/`，重试读取原请求；同一 ID 不允许绑定不同代码。
代码被预检查拒绝时环境未推进，可修复后用新 ID，但 `expected_segment` 仍按最新观测填写。
成功提交后再次 `observe`，不要把 `state=ready` 误认成任务成功；它只表示能继续提交。

代码是有界 Python 子集：赋值、for/range、列表/字典/索引、数值加减乘除和 `env.step(action, steps=N)`。
复杂规划/数值运算可以在 agent 自己的工作目录完成，最终只提交合法动作脚本。
默认每段最多 1000 ticks；当前 Cast Coil 一个 tick 为 0.0025 秒，10 ticks 只有 25 毫秒。
必须从实际 prompt 的 `control_dt_s` 核对时长；少量步进不足以等关节到位，不应把控制目标当成已达到的位置。

## 两类结果要分开

**现在的新 Codex 会话：** 可以验证观察、规划、驱动和纠错能力；现有客户端没有接入 Codex IDE 的真实用量事件。
`--token-limit 2000000` 只限制 bridge 已记账用量；没有 usage 上报时，真实用量和余额未知。v2 prompt/页面会明确显示未测量。
不能把它当作已启用原生 Codex 的 2M 硬限额。此时 `usage_measured=false`、`success_within_budget=false`。
`states` 与 `agent_solutions` 保存物理交互和提交代码，不自动保存完整 Codex 聊天、内部推理或所有工具事件。

**严格 2M 试验：** 当前已经实现的是 `openai_harness` 的 Responses API 计量闭环；它调用所选模型，不等同于测量一个原生 Codex IDE 会话。
若必须测试原生 Codex，需要再接 Codex harness：采集模型/工具事件和 usage、在下一次模型调用与动作提交前由控制器执行预算检查。
官方 [非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode) 的 `codex exec --json` 提供事件流和 `turn.completed.usage`；
[App Server](https://learn.chatgpt.com/docs/app-server) 提供 `thread/tokenUsage/updated`。
这些是可接入的计量源，**当前仓库还没有该连接器**；只在一个很长的 turn 完成后读取总用量，也不足以保证每个 segment 前实时检查或严格不超预算。
后续连接器必须核对累计/增量口径、cached/reasoning 子项和中断调用，不能让 solver 自报一个“准确”数字替代。

另外，当前 Cast Coil adapter 是 home 起点、自由物体、无抓持辅助；既有完整 demo 的预抓取/辅助条件不同。
它的 pilot evaluator 尚未等价于正式物理验收。报告应分别记录任务是否通过、计量是否完整、环境判定是否正式验收。

## 保持测试可解释

对当前共用文件系统的操作包，访问范围靠提示词约定，不是操作系统隔离；记录为 `tools_open_reference_restricted_pilot`。
工具类型开放不等于资料开放；禁止通过工具或委派绕过信息边界。联网开启时仅允许通用知识、规格及库文档，不允许本题解法。
不要给新会话附上带既有解法的任务文档、robot_plan、成功 demo、轨迹或私有资产。允许公开的任务目标、机器人接口和本轮观测。
正式盲测应由操作者把同样操作包放在独立用户/容器，只暴露公开观测与动作代理，隐藏仓库和计量写入端点。
“另开一个 Codex 会话”本身不会隔离仓库文件或阻止读取既有答案。

下一轮通过上面的导出命令创建干净任务包，自动同步当前文字任务说明、机器人/相机基础参数与联网策略；不要整目录复制已完成的 solver 工作区。
公共 solver 提示词模板见 [agent_solver_prompt_zh.md](agent_solver_prompt_zh.md)，完整协议见 [agent_bridge_zh.md](agent_bridge_zh.md)。
