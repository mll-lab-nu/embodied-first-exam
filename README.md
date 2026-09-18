# TopoGym

当前主线是十项拓扑操作任务的环境搭建，默认采用 **Nyx + 完整封闭实验室 `compact_lab`**。
各任务的基线、资产状态与验证范围见 [任务目录](topogym/tasks/README.md)；参数卡存在不等于任务已通过物理验收。

| 目录 | 用途 |
| --- | --- |
| `topogym/tasks/` | 当前任务自身的几何、场景、执行与判定 |
| `topogym/world/`、`robot/`、`primitives/` 等 | 共享物理环境、渲染、机器人、动作及数据工具 |
| `configs/` | 当前 Hydra 配置与十项任务参数卡 |
| `demos/environment_bootstrap/` | 当前任务及共享场景的运行入口 |
| `tests/`、`scripts/`、`bash_scripts/` | 当前回归检查与可复用工具 |
| `docs/` | 当前方案、接口说明、进度与维护记录 |
| `runs/environment_bootstrap/` | 当前场景、图片、视频、配置快照和验证报告 |
| [`runs/demos/`](runs/demos/) | 按任务存放的独立 MP4 副本，任务目录只含视频；运动学预演文件名含 `kinematic` |
| [`runs/demo_metadata/`](runs/demo_metadata/index.html) | Demo 播放页、配置、报告、状态、资产及来源清单 |
| [`legacy/`](legacy/README.md) | 旧版代码、配置、测试、文档、实验结果及周报；只读历史资料 |

准备与预览（在仓库根目录执行）：

```bash
bash env_setup_gs121.sh
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking_inspect
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.hedgehog_in_cage
```

本机已生成的 [环境汇总页](runs/environment_bootstrap/index.html) 保持原位置。
完整演示统一从 [demo 汇总页](runs/demo_metadata/index.html) 查看；每个已完成环境至少保留一份，具体要求见 [项目规则](AGENTS.md)。
渲染约束及显式光栅选择见 [默认渲染说明](docs/develop/visual/default_nyx_lab_zh.md)。

```bash
.venv-gs121-nyx/bin/python -m unittest discover -s tests -p 'check_*.py'
.venv-gs121-nyx/bin/python -m tests.check_configs_compose
```

新增任务先登记 `configs/task_cards/`，实现放入 `topogym/tasks/<task_id>/`。
当前模块不导入 `legacy/`；需要复用历史代码时，迁入具体任务或共享模块并补充相应验证。
开发时的一次性脚本放在仓库外临时目录，试验结果放 `runs/`；确认需长期维护后再纳入 `scripts/` 或 `tests/`。

2026-09-16 的整理范围、分类依据和逐项清单见 [整理记录](docs/maintenance/repository_cleanup_20260916.md)。
