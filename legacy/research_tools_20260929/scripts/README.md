# 辅助工具

2026-09-29：Harbor 层已按 robot_coding_bench 重建，用法、生成器（`topogym_mk_task.py`、`topogym_mk_limited.py`）和批量脚本见 [Harbor 手册](../docs/rcb/README.md)。更早的两版 Harbor 层在 `legacy/harbor_20260929/` 和 `legacy/harbor_native_20260929/`，不再使用。

- `record_initial_scenes.py`：固定当前源码快照，按注册表串行调用共享场景验收入口，录制所有已接入变体的短程初态；`--index` 更新统一 PNG/MP4 索引，未开发变体留空，失败保留报告。默认 4 个控制步，使用 Genesis CUDA + Nyx，不执行解题策略。
- `prepare_nyx_studio.py`：显式下载并核验 Nyx 所需 HDRI/纹理；无 RGB 的核心使用不需要运行它。
- `prepare_blanket_initial_states.py`：管理侧离线制作 Blanket 初态；平坦绑定、受控聚褶／扭转、放桌、撤控静置，经标准 World 和 Nyx 录制。`--tier easy|medium|hard` 选择统一聚褶 0°/135°/270°；默认要求完整静稳资格，显式 `--acceptance scene_layout` 只暂缓运动资格，保留材料、绑定和落桌检查，不将 `qualification.passed` 改为 true。准备时建议设置 `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`，避免稀疏投影的数值库线程争用。
- `install_blanket_initial_state.py --candidate <目录>`：核验准备完成的三档代表，将其完整数值包注册为包内资源；不覆盖已有版本或借用其他 seed。新增 seed 需先独立准备。机器人解法及难度排序未因此获得资格。
- `prepare_blanket_initial_states.py --particle-diagnostics`：可选只读逐 tick 粒子诊断；保存原始粒子 ID、材料条带、真实 visual 支持表与权重、free 标志、速度热点、约束拉伸及几何接触候选，不改变准备或物理参数。
- `inspect_blanket_preparation.py --run <run> --output <new_dir> --last-seconds 2`：分析已有平坦出生准备轨迹并生成材料坐标热点图。旧日志没有保存的真实 binding／接触力明确标为不可用，不从当前位置猜测绑定。
- `test_blanket_initialization.py`：复制独立源码快照，以新进程验证冻结初态的零推进 reset、状态／RGB 对照、两段连续执行与回溯。`--checks scene-layout` 验证三档场景的精确粒子恢复、短程自由运行、关节动作与回溯，并记录 RGB 差异，不宣称静稳或解题成功。
- `inventory_sources.py`：只读取文本、AST 和哈希，生成全仓脚本清单；不导入项目或执行测试。
- `test_policy_cube_transfer.py`：复制独立源码快照后运行低层 segment 真实验收，包含方块搬运、空抓反例及两机器人四模式接口矩阵；每例保存 Nyx 视频、日志和报告。命令与时序区别见[测试说明](../tests/README.md#segment-与低层方块-policy-验收)。
- `test_scripted_policy_rollout.py`：新 `act(obs)` 样板的管理方入口；分配 `task_rollouts/<experiment_content>_<experiment_date>/<task_name>/rollout_<编号>/`，冻结源码后执行原位拾起放下、横向搬运、两段衔接或空抓对照。`--suite` 串行运行完整清单；不覆盖旧编号。用法见[样板说明](../topogym/planning/README.md)。
- `import_rope_threading_reference.py`：离线读取外部示例的 `geometry.json`、`manifest.json`、`phase-000.bin`，校验哈希，从几何和首帧位姿提取有序绳节点、环/支架参数及来源，输出参考 JSON。

Rope 工具仅在重新提取或更新来源数据时手动使用，不自动下载、不运行来源引擎、不生成完整轨迹或 Genesis checkpoint。正常任务读取包内已有 `topogym/assets/resources/templates/rope_threading_reference.json`，不调用转换工具。若更新该包资源，还需同步维护 catalog 哈希。

调用格式如下，**本轮未执行**：

```bash
python scripts/import_rope_threading_reference.py \
  --geometry /path/to/geometry.json \
  --manifest /path/to/manifest.json \
  --phase /path/to/phase-000.bin \
  --output /path/to/reference.json
```

[转换含义与当前精简范围](../docs/develop/dev-logs/simulator_simplification_20260923_zh.md)。旧 OpenPI/API 工具已归档到 `legacy/cleanup_20260929/topogym/agents/deferred/tools/`，当前不接入或运行。

- 当前 Harbor 的安装、镜像、任务生成和检查统一见[使用手册](../docs/rcb/README.md)；旧 runner 脚本已归档，不再作为可执行入口。

- `test_grasp_assist.py`：同一快照验收入口支持 `mechanism`、`robot-cube`、`pbd-mechanism`、`fem-mechanism`、`pbd-robot`、`fem-robot`；柔体 case 使用独立材料夹具和已有 scripted policy/SegmentRunner。FEM 与 RGB 要求 CUDA，GPU case 串行；配置、源码、生成资产哈希和真实失败日志落盘。详见[用法与模型限制](../docs/develop/modules/grasp_assist_zh.md)。
  `fem-robot` 默认使用共享 `v13_material_mesh` 软绳材料和细网格，与四类正式 FEM 绳任务一致；`--fem-rope-profile baseline` 显式保留旧粗硬试件作对照。历史专用形变阻尼未迁入。
