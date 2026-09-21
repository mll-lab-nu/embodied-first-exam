# TopoGym

当前登记 13 项任务：原十项拓扑操作任务、[杂乱被子展平](docs/develop/tasks/blanket_flatten_zh.md)、第 12 项[长孔立柱解环](docs/develop/tasks/slotted_post_ring_zh.md)，以及第 13 项 [Orbits 四环阶梯解绳](docs/develop/tasks/orbits_zh.md)。默认采用 **Nyx + 完整封闭实验室 `compact_lab`**；第 12 项历史一维绳模型通过重力及半步长复验，36 mm 候选完成 147 秒外力驱动解环；新增三维 FEM 绳已接入，落稳检查尚未通过，完整机器人执行仍未通过；第 13 项当前为视频重建的静态基础场景。
各任务的基线、资产状态与验证范围见 [任务目录](topogym/tasks/README.md)；参数卡存在不等于任务已通过物理验收。

[3D Buzz Wire 空间电流棒](docs/develop/tasks/buzz_wire_3d_zh.md) 已增加紧凑低矮单臂版：Panda + Robotiq 操作圆环，底座 74.3 × 52.7 cm、导线最高约 26.6 cm；[三视角完整动作](runs/demo_metadata/buzz_wire_3d/2026-09-18_compact_single_arm_v1/index.html) 每路 91.84 秒，实际摩擦抓持、全迷宫通过、末端松手与静置，时间步减半复验通过。预穿环、预抓取起点；旧无机器人台架保留。

Coding agent 可通过独立的 [分段交互接口](docs/develop/modules/agent_bridge_zh.md) 接入：同一环境连续执行代码段、保存全部多视角 frames、监测 2M token 预算，并提供浏览器手动测试和 OpenAI API harness。

[固定变体视频 rollout 管线](docs/develop/modules/agent_rollout_pipeline_zh.md) 提供 RGB / privileged 两种输入、Codex 程序化接口、`segment_0.mp4` 起始的连续视频反馈，以及共享变体 × 默认三次重复的评测调度。产物独立保存在 `runs/agent_rollouts/`。

| 目录 | 用途 |
| --- | --- |
| `topogym/tasks/` | 当前任务自身的几何、场景、执行与判定 |
| `topogym/world/`、`robot/`、`primitives/` 等 | 共享物理环境、渲染、机器人、动作及数据工具 |
| `configs/` | 当前 Hydra 配置与任务参数卡 |
| `demos/<task_id>/` | 完整流程 demo 的 MP4 迭代目录；沿用已有视角子目录，视频目录只放 MP4 |
| `demos/environment_bootstrap/` | 当前任务及共享场景的运行入口 |
| `tests/`、`scripts/`、`bash_scripts/` | 当前回归检查与可复用工具 |
| `docs/` | 当前方案、接口说明、进度与维护记录 |
| `runs/environment_bootstrap/` | 当前场景、图片、视频、配置快照和验证报告 |
| `runs/agent_rollouts/` | 冻结场景变体、各 agent 的分段视频与重复评测记录 |
| [`runs/demos/`](runs/demos/) | 已有独立 MP4 历史归档与备份；运动学预演文件名含 `kinematic` |
| [`runs/demo_metadata/`](runs/demo_metadata/) | Demo 配置、报告、状态、资产及来源清单；保留历史播放页 |
| [`legacy/`](legacy/README.md) | 旧版代码、配置、测试、文档、实验结果及周报；只读历史资料 |

准备与预览（在仓库根目录执行）：

```bash
bash env_setup_gs121.sh
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking_inspect
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.hedgehog_in_cage
```

自 2026-09-19 起，新的开发进展直接提供相关 MP4 视频链接，不再创建、更新或部署 HTML 展示页。
完整流程 demo 在 `demos/<task_id>/` 对应子目录迭代，沿用已有视角目录，视频目录内只放 MP4；配套材料放在 `runs/demo_metadata/`。
本机已有的 HTML 汇总页保留为历史资料。每个已完成环境至少保留一份完整 demo，具体要求见 [项目规则](AGENTS.md)。
渲染约束及显式光栅选择见 [默认渲染说明](docs/develop/visual/default_nyx_lab_zh.md)。

```bash
.venv-gs121-nyx/bin/python -m unittest discover -s tests -p 'check_*.py'
.venv-gs121-nyx/bin/python -m tests.check_configs_compose
```

新增任务先登记 `configs/task_cards/`，实现放入 `topogym/tasks/<task_id>/`。
当前模块不导入 `legacy/`；需要复用历史代码时，迁入具体任务或共享模块并补充相应验证。
开发时的一次性脚本放在仓库外临时目录，试验结果放 `runs/`；确认需长期维护后再纳入 `scripts/` 或 `tests/`。

2026-09-16 的整理范围、分类依据和逐项清单见 [整理记录](docs/maintenance/repository_cleanup_20260916.md)。
