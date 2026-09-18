# 项目目录整理记录 · 2026-09-16

已按“当前主线保留、旧项目只读归档、探索/开发中间产物删除”完成整理。
旧版不再维护运行入口；没有为 `legacy/` 增加兼容 import 或 Hydra 搜索路径。

## 分类与结果

| 类别 | 处理 |
| --- | --- |
| 当前十项任务 | 保留 `topogym/tasks/`、任务卡、现行配置、bootstrap 入口与当前进度文档 |
| 当前共享能力 | 保留 world / robot / primitives / data / runtime；planning / generation / supervision 移除旧任务专用部分 |
| 旧项目源码与配套 | `legacy/topogym/`、`legacy/demos/`、`legacy/configs/`、`legacy/tests/`、`legacy/bash_scripts/` |
| 旧项目说明 | `legacy/docs/`：旧任务实现、旧架构/A–G 蓝图、历史开发日志和进度表；入口说明改写前保存快照 |
| 旧实验与已交付周报 | `legacy/runs/` 与 `legacy/reports/weekly/` 原样保留 |
| 中间产物 | 删除 spike / study / diagnose 一次性脚本及专用配置、临时日志/缓存、废弃草稿和旧配图脚本 |
| 环境与资产 | 保留 `.venv-gs121*`、uv/OpenPI/HF 依赖缓存、`.external/nyx-assets` / `openpi`、机器人与任务源资产/许可证 |

归档动作 340 项，另有 17 份说明/公共入口快照。
`legacy/` 当前含 381 个源码、配置、文档等非实验媒体文件；
实验与周报按整目录移动，约 8.24 GiB（归档总逻辑文件大小）。
删除动作 99 项，包含目录级清理；它们不等于同数量文件。
详细清单见 [cleanup_20260916.json](cleanup_20260916.json)，其中有原路径、新路径、原因、文件数、大小；单文件条目含清理前 SHA-256。

## 删除的主要中间产物

- `tests/*_spike.py`：球滚动、闭合带、FEM 绳、PBD 布、褶皱、环转移、卷展、焊接的开发探针，以及对应的顶层/run 配置。
- `tests/study_*_feasibility.py`、`tests/diagnose_swap_crossing_sign_feasibility.py`：旧策略探索脚本。
- `bash_scripts/tests/{genesis_cloth_api_probe,pbd_cloth_spike,pleat_stability_sweep}.sh`。
- `scripts/docs/`：结构任务候选配图与 interlocking 展示；`scripts/nyx_official_demo.py`：安装阶段官方示例包装。
- `cli_commands.txt`：旧任务开发命令流水账。当前入口写入根目录 README。
- 候选分类/研究稿：`capability_taxonomy_proposal_zh.md`、`structurally_constrained_research_assessment_zh.md`、`task_family_requirements_and_examples_zh.md`。十项任务方案与已批准施工计划保留。
- 过渡方案：`genesis_scenario_rendering_assessment_20260913_zh.md`、`render_config_and_env_delivery_goals_zh.md`、初版依赖盘点 `framework/env.md`。当前 Nyx 默认说明和实际安装脚本保留。
- `docs/develop/physics/untangle/debug-log/*.log` 原始调试输出；有结论的旧开发文档归档。
- `runs/hydra`、`runs/nyx_official`、`runs/interlocking_level6_demo`、`runs/generated_meshes`，以及 `.cache/nyx-audit`、`.cache/interlocking_reference`、`.external/nyx-official`、空原型包与字节码缓存。

价值或用途仍需历史证据判断的旧试验结果采用归档；没有把所有 `runs/` 或 `.cache/` 一律删除。
`runs/environment_bootstrap/`、共享机器人标定与渲染性能结果继续留在当前 `runs/`。

## 为解除旧版依赖做的调整

- 开锁仍在使用的执行器、review 生成器、planner、回退证书、抓持、oracle、evaluator 迁入 `topogym/tasks/lock_picking/`；原件归档。
- 两组开锁几何/证书测试迁为 `check_lock_picking_geometry.py` 和 `check_lock_picking_certificate.py`。
- `lock_picking_baseline.yaml` 独立加载当前 task/run 组，取消 staged-lock 的旧配置继承链；加宽间距配置继续继承当前基线。
- `config.yaml` 只组合公共默认；共享渲染预览改用独立 `presentation_preview.yaml`，取消对旧 bar-through-hole 的借用。
- 清理公共包的旧任务集中导出；新增当前导入和参数卡资产路径检查。Nyx 与封闭实验室默认不变。
- 更新 README、当前文档链接、参数卡、安装器提示、H5 查看工具和现行 review 页。历史报告的配置/哈希不被改写为“本次运行”。
- 旧版源码/文档可纳入 Git；大体积 `legacy/runs/`、`legacy/reports/` 继续忽略。Ruff 默认排除只读归档。

## 验证

- 当前 42 项单元检查通过，覆盖所有主配置、双世界预设、卡片路径、开锁几何/证书/松手门槛、机器人与共享相机接口。
- 96 个当前模块实际导入，未加载旧任务或 `legacy`。
- 开锁基线、加宽预览、刺猬预览三份配置的完整解析结果与整理前逐项一致。
- 380 个归档源码/配置/文档与整理前的实际工作区快照逐字节相同，保留原有未提交修改。
- [GPU 共享渲染报告](../../runs/environment_bootstrap/cleanup_validation/presentation/report.json)：Nyx + compact_lab、腕部跟随、每路 2 帧录像、2 帧 HDF5，背景碰撞几何为 0；H5 值级检查通过。
- [开锁初态支撑检查](../../runs/environment_bootstrap/cleanup_validation/lock_initial/initial_support.json)：当前代码实际建场，钥匙为 6 自由度，实体接触支撑重量；已生成三路初态图。
- 通用绳 tube OBJ 检查、未定义名称检查通过。没有重新执行开锁完整 oracle 或把局部验证扩大为十项任务验收。

## 恢复与工作区边界

整理前的源码/config/doc 快照、Git 工作区/暂存区 diff、删除项临时恢复副本在：

`/tmp/topogym-cleanup-20260916-121716`

这是仓库外的临时恢复目录，不保证长期保留；项目中的中间产物已经移除。
归档使用当前工作区文件，没有用 HEAD 覆盖尚未提交的修改，也没有恢复本次整理前已删除的文件。
未创建提交。既有 `runs/environment_bootstrap/index.html` 保持原位置。
