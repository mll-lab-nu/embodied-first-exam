# HumanCLAW 动作参数解析修复

执行解析器版本：`humanclaw-action-parser-v2`。

旧解析器只从 `<...>` 中读取部分参数。纯文本输入可能被静默改写，例如
`Walk forward normal` 变成 slow，`Turn right 90` 变成 left。未识别动作还会
默认成终止动作。这个错误位于公共环境适配层，会干扰 harness 的对比结果。

## 新行为

所有 HumanCLAW harness 使用同一个解析器：

| 请求 | 执行结果 |
| --- | --- |
| `Walk forward normal` 或 `Walk<forward><normal>` | `Walk<forward><normal>`，condition `[0, 0.4, 0]` |
| `Turn right 90` 或 `Turn<right><90>` | `Turn<right><90>`，condition `-90` |
| `Turn left 45.5` | `Turn<left><45.5>`，不把日志里的角度四舍五入成 46 |
| `Turn 90`、`Walk<forward>`、未知速度／方向 | 拒绝，不猜参数 |
| `turn` 工具传入 `Walk forward normal` | 拒绝，不让工具名覆盖动作含义 |
| 未识别动作、额外参数／说明文字、破损或混合格式 | 拒绝，不默认 Stop 或忽略多余内容 |

八种动作均支持完整尖括号写法和等价的空格写法，忽略大小写及分隔处空白。
保留明确的旧别名（如 `Stop`、`Stand`、`Sidestep`），不使用子串猜测动作。
action ID 省略时，从完整动作语法识别；给出 ID 时必须合法且与动作一致。

Turn、Sit、Step back、Side step 的正数仍按已有接口声明限幅；例如
`Turn right 999` 的执行结果仍是右转 120°。零、负值、NaN 和无穷值拒绝执行。
这些范围规则没有扩展控制器能力。日志中的规范动作名准确表示实际 condition，
不因显示精度丢失小数参数。

Codex／Pi 的无效调用返回工具错误，不调用环境，不消耗动作步数，不推进观察
编号，不缓存成已执行，也不把 session 标成基础设施故障。原生 agent 可以自行
根据错误修正参数。已成功执行的请求继续遵守原有去重与过期观察检查。
PSV／Bare API 也使用同一验证规则；不新增重规划、模型重试或替代动作。

2026-10-21 复核还修复了运动执行层的同类兜底：请求的技能未加载时明确报错，
不再偷偷换成 stand；Walk、Step back、Sit 的参数数组长度错误时拒绝，
不再截断数组或只读取第一个值。运动网络入口也拒绝非有限数值及布尔值。
已训练网络的坐标／尺度编码保持原样，例如右转 90° 在 turn 网络中编码为
`-90 / 75 = -1.2`，不会因规范化而改成左转。

## 记录与实验版本

- `action.normalize` 的输入保留原始动作及 ID，输出保存规范动作和实际 condition。
- 被拒绝的 native 请求保留原始参数、错误和 `tool.rejected` 事件。
- run metadata、native `environment.protocol`、规范化 span 记录解析器版本。
- 现有 native-actions-v2 工具说明、初始 prompt、PSV prompt、Codex/Pi 原生决策、
  上下文管理和恢复流程没有修改。

## 历史结果

修复只影响使用新版代码的新执行。历史轨迹的动作与指标必须保留原样，不能把
旧日志中的 slow/left 替换成 normal/right 后视为重新评测：实际环境、后续观察
和模型决策已经不同。受影响 episode 的修正成功率需要重新运行才能确定；
按旧轨迹做动作回放仍应执行当时真正保存的动作。

在服务器 coauthor 的 `humanclaw-codex-copilot-astra-fullval-r2-20261018`
结果中，`shard-0188/102816600_ep10_couch/rollout_00/experiment_runs/`
`run_ce12639dfa6842aaa82b35637b02f38e/events.jsonl` 第 0 步的同一 span
`span_b48dcc16a2754e7eafbe854b7b448aa2` 保存了请求 `Turn right 120`，
输出却是 `Turn<left><120>`、condition `120.0`。这是抽样确认，未据此推算
全部受影响 episode 数量。

本地回归入口（不需要模型 API 或 GPU）：

```bash
python -m pytest tests/test_action_parsing.py tests/test_native_harnesses.py \
  tests/test_prompt_contract.py tests/test_experiment_integration.py -q
```

安装 Torch 的运行环境还应执行 `python -m pytest tests/test_motion_conditioning.py -q`，
验证实际网络条件张量，以及技能缺失时不会产生替代动作。这些测试使用 CPU，
不加载权重、不申请 GPU、不调用模型 API。

2026-10-21 复核：项目环境全套测试 441 通过、5 跳过（其中运动条件测试因
该环境未安装 Torch 而跳过）；另在隔离的 Torch CPU 测试环境中运行动作解析、
运动条件、prompt 合约和 rollout 集成测试，共 160 项全部通过，包含 32 项
运动条件检查。本次修改不替换服务器的历史实验快照。
