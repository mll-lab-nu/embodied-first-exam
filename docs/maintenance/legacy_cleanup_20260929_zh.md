# 旧 Harbor / research 归档与快速检查 — 2026-09-29

已按用户确认的候选清单，将 **128 项文件／目录** 全部移入 [`legacy/cleanup_20260929/`](../../legacy/cleanup_20260929/README.md)。共 **303,859 个普通文件，约 31.27 GiB**；旧源码、研究来源、原始状态和失败记录均保留。当前任务、仿真资产、正式 demo、可解性证明和本地有效 rollout 证据保留在原位。

## 归档与联动修改

- [迁移清单](../../legacy/cleanup_20260929/manifest.json)逐项记录原路径和新路径；`legacy/cleanup_20260929/files.jsonl` 保存逐文件 SHA-256、inode、大小、mtime、权限及软链接目标。
- 同一文件系统内 rename，避免复制大产物。移动后重新核对全部 303,859 个文件的元数据，并重新计算 223 个文档、源码、配置与 research 文件的哈希；均一致。
- 从旧 manifest 提取 37 项旧变体名称与默认入口映射，保存到 [`tests/fixtures/retired_variations.json`](../../tests/fixtures/retired_variations.json)。[现行回归测试](../../tests/unit/test_task_variations.py)不再读取 legacy，也不导入旧源码。
- 更新活动文档中的 135 个迁移链接，全部目标存在；同时清理入口 README 中旧 runner 命令，当前 Harbor 指向 [`docs/rcb/`](../rcb/README.md)。归档原件正文和历史 manifest 不改写，通过外层迁移清单定位。
- `.gitignore` 继续保留归档源码和文档的版本化能力，排除本轮归档的生成任务、报告、运行产物及 122 MiB 逐文件清单。没有执行提交、暂存或 `git rm --cached`。
- 归档前发现的 5 个旧 worker、1 个周报 shell 和 1 个 HTTP server 都已处于 stopped 状态；本轮没有恢复或终止这些进程。它们不再应使用原路径恢复旧服务。

## 快速检查结果

| 检查 | 结果 |
|---|---|
| 迁移前旧变体回归 | 1 passed |
| 当前 Harbor 全任务 CI | `bash ci_checks/run_all.sh` 通过，覆盖 28 个任务、独立 verifier、任务清单和共享工具一致性 |
| Harbor 原生 Task 加载 | 28/28 通过，均配置独立 verifier |
| 当前 Harbor 交付内容哈希 | tasks、images、harbor_agents、ci_checks 共 446 个文件与迁移前完全一致 |
| Agent 类导入 | Codex、Claude Code、oracle、nop、CodexChatGPT、CodexOpenRouter 共 6 个入口通过 |
| CLI 配置解析 | unlimited/Codex 与 limited/CodexChatGPT 的 `harbor run --print-config` 均通过，没有请求模型 |
| 当前 Python 静态语法 | 555 个文件通过 AST 解析 |
| 当前 task tooling | unlimited Session 导入、limited 真实 spec 校验、RCB1 图像/本体/时间轴编解码与客户端 Result 解码通过；错误帧被拒绝 |
| 本地 Env / SegmentRunner / policy / 权限 / 回溯及选定单元检查 | **159 passed，1 deselected** |
| 归档完整性和引用 | 128 项原路径已移走、新路径存在；303,859 个文件元数据、223 个文件哈希、135 个链接、13 项 ignore 行为通过 |

未纳入的 1 项是 `test_task_names_are_files_in_functional_modules`：其旧目录断言不允许当前 planning 下的任务子目录。此问题在归档前的[旧迁移实施记录](../../legacy/cleanup_20260929/docs/develop/modules/rcb_harbor_implementation_20260929_zh.md)已有记录，本轮没有改弱断言或把它计为通过。

最初在 simulator venv 导入 limited 客户端时因缺少 `requests` 失败；该客户端的 Dockerfile 已声明 requests。改用现有 Harbor venv 后检查通过，未安装依赖、未改 task 工具。初次失败日志保留。

**验证边界：**本轮验证代码、配置、序列化及使用轻量 world 夹具的本地 rollout 合同。没有启动 Docker/GPU 物理 rollout 或模型调用，不能据此宣称重新通过了完整容器任务、真实机器人解题或模型成功。

## CPU / 内存监控

归档、链接处理及所有检查均由临时 supervisor 每秒采样整机 CPU 与内存使用率；内存按 `1 - MemAvailable / MemTotal` 计算。工作子进程限制在 2 个 CPU，数值库线程上限为 2。CPU 或内存达到 **90%** 时停止本轮子进程组，不终止其他会话。

本轮记录的整机峰值：**CPU 84.52%、内存 16.23%**；没有触发阈值停止。完整日志、采样、命令和检查脚本快照见 [检查报告目录](../../runs/test_results/legacy_cleanup_20260929/README.md)，[机器可读报告](../../runs/test_results/legacy_cleanup_20260929/report.json)。
