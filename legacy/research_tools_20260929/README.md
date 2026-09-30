# 2026-09-29 研究、诊断与独立测试归档

按用户本轮授权，将不参与当前 rollout 准备、rollout 执行及 Harbor 流程的已列代码归入统一 `legacy/`。
目录保留迁移前相对路径：`<原路径>` → `legacy/research_tools_20260929/<原路径>`。

- [迁移清单](manifest.json)：42 项文件／目录映射、分类、迁移前工作区状态及保留范围。
- [逐文件记录](files.jsonl)：270 个文件的路径、SHA-256（软链接记录目标）、大小、inode 和修改时间。
- 其中 157 个 Python / Shell 源码文件；其余是原说明及随目录保留的缓存。
- 使用同一文件系统内的 rename，迁移后逐文件核对哈希和元数据；迁移前未提交的修改也按原样保存。

## 内容

| 目录 | Focus |
| --- | --- |
| `scripts/` | 20 个独立审计、诊断、场景预览、验收及源码盘点入口；附原说明 |
| `topogym/recording/sequence.py` | 未接入当前调用链的逐帧落盘缓存 |
| `topogym/solvers/collision/convex_compounds.py` | 仅由历史单元测试调用的凸组合 SAT 碰撞查询 |
| `topogym/tasks/task_variations/` | 旧变体访问接口的兼容导出 |
| `tests/` | 前述独立回归套件、研究证据工具，以及依赖它们的 integration 测试 |
| `assets/tasks/buzz_wire_3d/*/planning/implementation/` | 两套历史 Buzz Wire 规划源码，每套七个文件 |

当前仍复用的控制目标辅助函数已逐函数提取至 `tests/fixtures/control_targets.py`，
活动 rollout 直接导入该夹具，不依赖本归档。`tests/fixtures/`、`topogym/planning/`、
`simulator/rollout_simulation/`、任务资产、初态准备、动作编译和 Harbor 全流程保留。
`runs/`、`task_rollouts/`、`solvability_proof/` 中的冻结源码和运行证据未迁移。

本目录保留原始正文，供历史审阅与复现研究；其中相对导入、命令和路径仍按原仓库布局书写，
不构成可直接运行的当前发行版本。不要把本目录加入当前 `PYTHONPATH`，也不要直接把旧 CLI 的路径改成归档路径运行。
迁移验证结果见 [维护记录](../../docs/maintenance/research_tools_archive_20260929_zh.md)。
