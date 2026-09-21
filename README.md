# TopoGym

机器人拓扑操作环境，当前登记 13 项任务。几何/场景、完整机器人流程、随机变体和物理资格分别验收；当前有 10 项任务的实例级完整机器人流程证据，具体限制见[当前进度](docs/progress/current_zh.md)。

- [文档入口](docs/README.md)：架构、模块、任务和进度。
- [当前 Demo 视频](demos/README.md)：每个视角目录一份 MP4，标明完整执行、外力流程或静态预览。
- [Agent rollout 实用手册](docs/develop/modules/agent_rollout_usage_zh.md)：环境检查、冻结 suite、工具交互与预算。

| 目录 | 职责 |
| --- | --- |
| `topogym/tasks/` | 任务几何、场景、控制/规划和判定 |
| `topogym/world/`、`robot/`、`primitives/` | 共享物理、渲染、机器人与动作 |
| `topogym/agent_bridge/`、`agent_rollout/` | 分段交互及固定变体评测 |
| `configs/`、`assets/` | 当前参数卡、配置与复现必需资产 |
| `demos/<task>/<camera>/` | 当前视频；叶子目录仅一份独立 MP4 |
| `demos/environment_bootstrap/` | 场景运行入口代码 |
| `runs/demo_metadata/` | 视频配套证据；[当前清单](runs/demo_metadata/catalog.json) |
| `runs/` 其他目录 | 开发中进展、运行依赖和必要验证记录 |
| `tests/`、`scripts/`、`bash_scripts/` | 回归检查与可复用工具 |
| `docs/` | 当前架构、模块接口、任务说明及精简进度 |
| `legacy/` | 旧实现；不被当前模块导入，本轮未整理 |

在仓库根目录执行：

```bash
bash env_setup_gs121.sh
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview
.venv-gs121-nyx/bin/python -m tests.check_configs_compose
```

默认 Genesis 任务采用 Nyx + `compact_lab`，部分任务动力学使用 MuJoCo；后端和验收范围以任务说明为准。
开发约定见 [AGENTS.md](AGENTS.md)。新增任务先登记任务卡；一次性脚本放仓库外临时目录，确认需要维护后再归入代码。
