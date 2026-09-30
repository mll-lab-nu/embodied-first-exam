# 2026-09-29 研究工具与独立测试归档

用户在确认全仓清单后授权迁移。本轮将列出的独立研究、诊断、场景预览、验收、兼容代码与历史规划源码
统一移入 [legacy/research_tools_20260929/](../../legacy/research_tools_20260929/README.md)。
原有 `legacy/` 归档不重新整理，原运行产物和源码快照不迁移。

## 范围与完整性

- 42 项文件／目录，270 个文件，其中 Python／Shell 源码 157 个：`scripts` 20、活动包 6、独立测试与证据工具 117、历史 Buzz Wire 源码 14。
- 包含用户清单中的 `unit`、`contracts`、`architecture`、`recording_data`；依赖已归档证据工具的独立 integration 测试和公共 conftest 一并归档，避免在活动测试目录留下断开的导入。
- `scripts/README.md`、`tests/README.md` 原文归档，活动位置改为保留入口的索引。
- 全部文件通过同文件系统 rename 迁移，核对原 inode、大小、mtime，以及普通文件 SHA-256／软链接目标。
- 原有未提交的 `tests/unit/test_initial_scene_feedback.py`、`tests/unit/test_terminal_fiber_bundling.py` 修改，以及尚未跟踪的 `scripts/render_seeded_initial_frames.py`，均按迁移时原字节保存。
- 映射见 [manifest.json](../../legacy/research_tools_20260929/manifest.json)，逐文件原始哈希见 [files.jsonl](../../legacy/research_tools_20260929/files.jsonl)。

## 保留流程与依赖修复

保留初态／资源准备、Buzz 动作编译、所有活动本地 rollout 入口、`topogym/planning/`、
`topogym/simulator/rollout_simulation/`、Harbor 任务／镜像／agent／CI／结果工具，以及 `tests/fixtures/`。
`tasks/*/tests/` 是 Harbor verifier 输入，本轮没有改动。

`scripts/test_policy_cube_transfer.py` 原来从 `integration.test_policy_action_receiver` 导入控制目标辅助函数。
将 `rotation()`、`targets_and_action()` 原样提取到 [tests/fixtures/control_targets.py](../../tests/fixtures/control_targets.py)，
修改调用方直接导入夹具，两个函数的 AST 与原实现完全相同。活动运行代码不导入 legacy 或已归档的测试套件。

修改了 IPC 缺 CUDA 的错误提示，移除已归档 CLI 的运行建议；simulator 的默认历史模式仍是 `segment`。
研究审计相关源码注释标明历史位置。活动索引和文档中的 90 个链接已改为归档位置；历史命令附归档提示，
不把简单替换成 legacy 路径的命令当成可运行入口。受并行会话边界保护的场景恢复计划正文未修改，
开发记录索引提供统一映射入口。

## 验证

实际日志与机器可读报告在 [runs/test_results/research_tools_archive_20260929/](../../runs/test_results/research_tools_archive_20260929/)。

| 检查 | 结果 |
| --- | --- |
| 迁移完整性 | 270 个文件的哈希／元数据核对通过 |
| 控制目标辅助函数 | 两个函数 AST 等价 |
| 活动 Python 语法与退役导入检查 | 通过；未发现运行代码导入 legacy 或已移走模块 |
| CPU 回归 | 215 passed、1 deselected；8 条第三方库 warning |
| Harbor 静态检查 | `ci_checks/run_all.sh` 全部通过，覆盖 28 个任务 |
| 保留入口 CLI | 14 个准备／rollout 脚本 `--help` 通过 |
| 活动导入与夹具注册 | Env／SegmentRunner／共享控制目标导入通过，cube 两类临时任务注册通过，默认历史模式仍为 `segment` |
| 文档新归档链接与 diff 格式 | 链接目标存在，`git diff --check` 通过 |

CPU 回归使用迁移前保存的测试源码临时副本，加载迁移后的活动包：包括 contracts、recording_data，
以及配置、控制模式、机器人描述、检查点缓存、Task 状态和分段可解性工作流的单元测试。
它们不是当前活动 rollout 对 legacy 的依赖。未选择的 HDF5 测试不计入通过数。
本轮未创建 Genesis 场景、运行 GPU 物理／Nyx、调用模型或重建 Docker 镜像。

迁移前未发现使用候选脚本的进程。验证子进程持续监控 CPU／内存，90% 阈值只会停止本轮启动的进程；
本轮记录的 CPU 峰值 26.37%、内存峰值 23.34%，未触发停止，也未干预其他会话进程。
