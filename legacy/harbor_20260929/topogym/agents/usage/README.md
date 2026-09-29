# Trial usage：计量、预算与停止

共享核心为每个 trial 维护权威账本，接收 Chat Completions、Messages、Responses 回执；不依赖 Harbor、OpenCode 或 simulator。生产接入固定 OpenCode，绑定在 `harbor_runners/agents/opencode.py`，路由在 `configs/harbor/providers.yaml`；已移除多 harness adapters/profile。

当前命令见 [Harbor 全参数与 Muse Spark 30k/10k 方块流程](../../../harbor_runners/README.md)，测试资格见[实施报告](../../../docs/develop/modules/opencode_model_key_implementation_20260928_zh.md)。

## 计量合同

- input/output 分别限额，每 trial 独立；主/辅助请求、重复上下文和重试共用账本。这不是美元预算。
- input 包含缓存读写，output 包含 reasoning；不把总量与 details 重复累加。原生 agent 日志只辅助对账。
- 默认 observed，按 provider 回执结算；未知用量失败，不按 0 或字符估计作为精确计数。
- 普通生成限制 output cap；缺省 cap 8192，按剩余额度收紧。Responses compact 无可用 output cap，按回执判定。
- observed 不保证服务端零超额；在途 input 可能到响应时才发现超限，断开 HTTP 也不证明服务端立即停止计费。
- strict 核心支持原子预留，但现有连接没有已验证的 input 上界，prepare 明确拒绝 strict，不自动降级。
- 未验证的托管工具、后台生成、n != 1、未知端点明确拒绝；gateway 不做跨协议互转。

## 生命周期

UsagePipeline 管理 gateway/service/ledger/publisher，保留公共多路由共账能力。当前 OpenCode 使用 primary 一条路由；主模型和 small_model 固定为用户输入，其他模型请求在转发前失败。

真实 key 只在宿主 Harbor 子进程，OpenCode 使用容器 relay URL 与 trial token。安装阶段可联网，运行/验证阶段 no-network；relay 经只读 Unix socket 挂载接入宿主。本方案只支持本机 Linux Docker。

每个 usage 事件同步判定，默认 100ms watchdog 观察调额与故障，公开 budget.json 连续刷新。停止时终止 agent，并用 root admin socket 取消 policy；无法确认停止则升级关闭本 trial 容器。计算停止与录像封存分开，容器丢失不伪造完整证据。

权威数据为 usage/ledger.sqlite；snapshot.json 和 events.jsonl 是导出。usage-update 原子检查 revision；失败后提高额度不会复活 trial。公开 JSON 和 frozen YAML 不是调额入口。

## 测试

```bash
.venv-harbor/bin/python -m pytest --confcutdir=tests/harbor tests/usage tests/harbor -q
```

本地覆盖三协议、流式回执、缓存/reasoning、并发预留、HTTP/Unix socket、停止与归档资格。真实 OpenCode CLI 另连本地模拟 provider，不能代替远端模型和 Docker/GPU 验收。

完成部署后，真实输入/输出强停负例可用：

```bash
.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case budget-input --allow-api \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --input-token-limit 1 --output-token-limit 10000 --gpu-devices 0

.venv-harbor/bin/python scripts/test_harbor_pipeline.py \
  --case budget-output --allow-api \
  --model-name 'openrouter/meta/muse-spark-1.3-contributor' \
  --input-token-limit 3000000 --output-token-limit 1024 --gpu-devices 0
```

这两条会调用真实模型，交互式终端提示 key；也支持 api-key-stdin。负例须匹配目标维度、失败 reward、归档和停止时间才报告通过；提前正常结束或 provider 拒绝 cap 不算预算负例成功。

budget_success_rate 以所有计划 task trials 为分母；预算失败、未完成 trial 不会消失。confirmed_usage 需结合 usage_complete 与失败状态阅读。
