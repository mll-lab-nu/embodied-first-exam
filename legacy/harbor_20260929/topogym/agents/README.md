# Agent 接入

`rollout/` 是活动的薄接入层：worker 保持唯一 Env，client 提交 passive policy，
独立进程代理调用已有 SegmentRunner.run_policy，逐段发布公开产物并封存证据。
不另建仿真、录制循环；simulator 核心不依赖此目录。Harbor 编排在仓库根目录
`harbor_runners/`，使用与 GPU/API 验收命令见 [runner README](../../harbor_runners/README.md)。
`usage/` 提供独立双额度账本、协议 usage 解析、受控请求网关与管理更新，默认
input 50M / output 20M。已接入 Codex / Claude Code / OpenCode 的 observed 路径；
真实容器、GPU/API 预算验收待运行，strict 的实际 provider 能力仍关闭。
口径和手动验收命令见 [usage README](usage/README.md)。

`deferred/` 保存此前的 bridge、rollout、访问规则和 agent 媒体代码供后续
逐项审查。它们依赖已退出的旧路径，不是可运行或兼容的新 API；安装包应排除
该目录。活动接入使用公共 Env，不恢复第二套环境工厂、时钟和截图流程。
