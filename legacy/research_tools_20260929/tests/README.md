# 模拟器核心测试

2026-09-29：Harbor 层的检查不在这里，在 `ci_checks/`（`bash ci_checks/run_all.sh`），用法见 [Harbor 手册](../docs/rcb/README.md)。更早两版 Harbor 层的测试（`tests/harbor`、`tests/usage`、`tests/benchmark`、`tests/benchmark_host`）已移入 `legacy/`。本地 SegmentRunner 合同测试保留。

用户已授权核心环境验收及实际录像。当前新合同为管理方 reset、操作方无 reset、特权仅在当前 episode 截断回溯，以及 Nyx + compact_lab、双臂 4 路/单臂 3 路、848×480、30 fps。实际结果见[本轮报告](../docs/develop/dev-logs/simulator_public_api_implementation_20260924_zh.md)。

逐文件目的和设备条件见 [测试脚本说明](../docs/develop/dev-logs/simulator_test_scripts_zh.md)。

默认配置排除 `genesis` 和 `hdf5` 标记，用于后续按层选择；未选择的能力不算验证通过。真实物理集合使用下面的入口，逐任务保存报告、源码快照和实际场景 MP4。

- `architecture/`：活动包边界、单一物理时钟、任务登记、延期代码隔离。
- `unit/`：配置、任务定义、判据和可恢复任务状态。
- `contracts/`：使用假 World 检查真正 Env 的生命周期和当前 episode 的单条有效 tick 历史；不证明物理有效性。
- `integration/`：真实 Genesis 世界、机器人、任务接入、PBD、FEM/IPC、任意历史状态续跑和渲染；需要明确的运行设备。
- `recording_data/`：不可变观测、分支视频时间线、真实命令与数据连接。
- `conftest.py`：公共假 World / Robot / Task 夹具，无 agent fixture。

旧 agent 相关测试保存在 `legacy/cleanup_20260929/topogym/agents/deferred/tests/`，不在默认测试范围内。历史 demo 成功不能替代新核心测试证据。

```bash
# 本仓库已准备过的 HDRI/木纹资源；全新安装也可用 prepare_nyx_studio.py 下载至默认缓存。
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py --device cuda --steps 200 \
  --output runs/test_results/nyx_base_acceptance_local
```

从仓库根目录执行，输出目录必须尚不存在。Nyx 要求 CUDA、gs-nyx 0.1.3、gs-nyx-plugin 0.1.4；FEM 另要求 Genesis 1.2.1、pyuipc 0.0.25、TetGen 0.8.2（`fem` 安装组）。可用 `CUDA_TAG=cu126 INSTALL_NYX=1 VENV_DIR=.venv-gs121-nyx OPTIONAL_GROUPS="video test" bash env_setup_gs121.sh` 准备依赖。

默认 200 个控制步对应 5 秒主连续片段，另有多次回溯、续跑与 seed 重建片段；不代表完整任务成功。`runtime_evidence.py` 检查实际相机为 `NyxCamera`，在 report 和录像 manifest 记录 renderer、background、材质应用结果及相机类型。只跑少量代表任务可加 `--steps 3 --tasks cast_coil blanket_flatten rope_threading`。纯 CPU 物理测试应关闭 RGB；本入口始终生成真实 Nyx 录像，因此只接受 CUDA。


接口、G2 生命周期、相机标定、输出一致性和 wheel 安装验证使用同一证据驱动：

```bash
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --checks interfaces stability cameras outputs installation --timeout 3600 \
  --output runs/test_results/simulator_interfaces_local
```

`--visual-asset-root` 指定 HDRI/材质目录；本仓库驱动默认 `.external/nyx-assets`。每种机制逐 tick 完整保存会产生较大内存与时间成本。快速回归可显式缩短 steps，报告会保留真实物理时长；短程通过不能替代长时稳定性验证。

## Scripted policy 管理调度验收

首选流程为 `obs → policy.act(obs) → env.step(action)`，由 `SegmentRunner.run_policy()` 管理段。新增合同测试位于 `test_scripted_policy_execution.py`、`test_policy_observation_access.py`、`test_cube_pick_place_policy.py`；真实集成入口 `integration/test_policy_cube_transfer.py` 导入同一个冻结运行驱动，不复制策略逻辑。

```bash
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --experiment scripted_policy_pick_place_20260926 --case pick_place --seed 0
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --experiment scripted_policy_suite_20260926 --suite
```

每次新建 `task_rollouts/<experiment_content>_<experiment_date>/<task_name>/rollout_0001/` 等递增目录，runner 直接写入该目录。包含源码与资产哈希、初末帧、三视角及拼屏 MP4、逐 tick／控制步／policy 日志和报告。样板使用 unlimited 的 `world` 观测；成功表示独立 Task 判据通过，不表示 limited 视觉策略通过。长流程默认使用显式 25 ms tick／decimation 1／40 solver substeps，不改变库默认值。实际结果见[本轮实施记录](../docs/develop/dev-logs/scripted_policy_execution_implementation_20260926_zh.md)。

## Segment 与低层方块 policy 验收

`tests/contracts/test_segment_execution.py` 与 `test_segment_artifact_access.py` 验证真实 Env 编排的段边界、终态、幂等、异常前缀、重入与权限；`tests/recording_data/test_segment_recording.py` 使用合成 RGB 和真实编码器验证短段、零步、末帧与合成视频，不计为 Genesis/Nyx 渲染验收。`tests/contracts/test_cube_transfer_task.py` 独立验证物体历史判据。

```bash
.venv-gs121-nyx/bin/python -m pytest tests/contracts tests/recording_data -q
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/cube_transfer_new --seeds 0 1 2 3 4 \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/cube_transfer_split_new --seeds 0 --split \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/segment_panda_joint_new --case interfaces \
  --seeds 0 --robot panda_robotiq --mode JOINT_ABS
```

输出路径必须不存在。脚本先复制源码/配置/资源为独立快照并记录哈希，再从快照启动子进程，建场景前就写报告；保留失败证据，不自动以原工作树覆盖快照。完整接口矩阵对应 ALOHA/Panda × 四种 control_mode，集成测试见 `tests/integration/test_simulator_segments.py`。方块测试见 `test_policy_cube_transfer.py`，测试 Task 仅在测试进程临时注册，不进入生产任务列表。Nyx 资产使用既有 `scripts/prepare_nyx_studio.py` 准备；CPU 合同/编码通过不代表 GPU 物理闭环通过。正式结果见 segment 实施记录。

方块长流程命令显式采用 25 ms physics tick / decimation 1 / solver_substeps 40，以保留 40 Hz 控制和 0.625 ms 求解子步，同时减少完整快照次数；这不改变库默认值，也不把该配置的通过结果称为默认 2.5 ms tick 的通过结果。默认时序由短程接口测试单独验收。

可一次展开完整清单；`--jobs` 表示独立 simulator 进程数，需要为每个进程预留 GPU/内存。默认单进程串行，各进程仍只创建一个 Env：

```bash
# 五个 seed、单段/两段、空抓反例、两机器人四模式；这里所有 case 使用显式长流程时序。
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/segment_suite_new --suite --jobs 1 \
  --physics-dt .025 --control-decimation 1 --solver-substeps 40
# 默认时序的原 20 控制步/0.5 秒接口矩阵，保留原跟踪容差。
.venv-gs121-nyx/bin/python scripts/test_policy_cube_transfer.py \
  --output runs/test_results/segment_default_matrix_new --matrix --jobs 1 \
  --tracking-hold-seconds 0
```

接口测试独立保存 `segment_checks_passed`、`original_short_tracking_passed` 与 `tracking_passed`。默认最多另执行 2.5 秒由测试 policy 提交的 `{}` 保持动作以检查最终跟踪；新增保持段不会改变原 0.5 秒测量结果，`--tracking-hold-seconds 0` 禁用它。原始失败和阈值始终保留，不能用后续收敛冒充原短程测试通过。suite 还比较 seed 0 的单段/两段运行初始物理状态哈希。

已完成验收采用单进程串行。多批同时启动时，显存需求按全部活跃 worker 累加；本次六个实例并发曾发生显存不足，失败记录保留。默认时序的完整原短程矩阵命令可能因 Panda 夹爪未在 0.5 秒内到位而返回失败，该资格与段执行/日志/录像分别报告。
# Blanket 冻结初态验收

`test_pbd_initial_state.py` 检查数值格式、损坏与布局拒绝；`test_env_initial_state.py` 检查零预运行导入顺序、失败不发布 episode、权限和 reset warmup 冲突。真实 Genesis/Nyx 检查由以下入口复制源码快照后执行；它不等于机器人可解性验证。

已通过离线稳定检查的单折对照配置、完整录像与跨进程验收见[2026-09-26 证据](../runs/test_results/blanket_initialization_20260926_01/README.md)。八面板默认准备参数尚未合格；需要复现正例时使用该说明中的完整参数，不能把下方通用 CLI 示例当成稳定候选。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  TOPOGYM_ASSET_ROOT=/home/jianwen/topogym/assets PYTHONPATH=. \
  .venv-gs121-nyx/bin/python scripts/prepare_blanket_initial_states.py \
  --output runs/test_results/blanket_candidate_new

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python scripts/test_blanket_initialization.py \
  --candidate runs/test_results/blanket_candidate_new \
  --output runs/test_results/blanket_acceptance_new
```

准备参数默认值只代表候选，不保证释放后保持褶皱；只有生成 `state/manifest.json` 且准备报告通过，才运行恢复验收。输出目录必须不存在，GPU 测试串行。开发探索中的 CLI 参数、结果和失败录像保存在各次 `report.json`；三档默认值不由该脚本自动切换。

Harbor 任务检查使用 `.venv-harbor/bin` 中的 Python/CLI，执行 `bash ci_checks/run_all.sh`；当前协议和运行方式见[Harbor 手册](../docs/rcb/README.md)。本地 SegmentRunner 合同测试仍在 `tests/contracts/`。两版旧 Harbor 专属测试和运行记录均已归档。

## 自动柔体 grasp assist

新增 `unit/test_soft_grasp.py`、`unit/test_grasp_geometry.py`；真实材料机制测试在 `integration/test_soft_grasp_mechanism.py`，Panda 两段抓放在 `integration/test_grasp_pbd.py` 与 `test_grasp_ipc.py`。机制使用标准 Env/SegmentRunner 的独立双夹爪场景；机器人使用 Nyx 与默认 home。它们不声明任何正式拓扑 Task solved。

```bash
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cpu --case pbd-mechanism --output runs/test_results/pbd_assist_new
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-mechanism --output runs/test_results/fem_assist_new
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case pbd-robot --output runs/test_results/pbd_robot_new
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-robot --output runs/test_results/fem_robot_new
.venv-gs121-nyx/bin/python scripts/test_grasp_assist.py --device cuda --case fem-robot --fem-rope-profile v13_material_mesh --output runs/test_results/fem_v13_robot_new
```

输出目录须不存在；GPU case 串行运行。每次保存源码快照、引擎版本/哈希、生成资产、报告与 rollout 证据；原生异常不会被后续成功覆盖。模型限制和实际通过范围见 [grasp 用法](../docs/develop/modules/grasp_assist_zh.md)及[实施记录](../docs/develop/modules/soft_grasp_assist_engineering_plan_20260927_zh.md)。

`v13_material_mesh` 现为四类 FEM 绳任务及 `fem-robot` 的共享默认配方。独立机器人夹具保留 160 mm 长、8 mm 直径，采用历史 Rope Threading v13 的 `E=50 kPa / nu=.30 / rho=650`、24 边表面采样、约 1.375 mm 轴向间隔、TetGen 请求体积 `2.5e-9 m³` 与 0.2 mm IPC 接触距离。资产报告记录实际四面体体积与数量；历史专用 20/s 形变阻尼未移植，因此不是原 1.1 m 场景的完整复现。机器人策略和 assist 配置相同，但细网格下实际选区长度需从绑定索引实测。

柔体机器人 case 可加 `--lift-height-m .10`，将默认 55 mm 抬升改为 100 mm，以检查下垂绳端完全离桌时的行为；策略参数进入报告与 submission hash。不同抬升高度不能混称为相同动作的单变量对照。

## Orbits 三档初态稳定性

```bash
.venv-gs121-nyx/bin/python scripts/test_orbits_stability.py \
  --tiers easy medium hard --duration 10 --window 2 \
  --output runs/test_results/orbits_stability_new
```

固定源码快照、独立进程串行执行，默认等待至少 12 GiB 空闲显存（可用 `--min-free-gib`、
`--gpu-wait-timeout` 指定）。标准 Env、ALOHA home、FEM/IPC、Nyx/compact_lab；
共享录制保存四路实际视频，逐 tick 检查连接、形变、支撑和受困关系，末 2 s 检查静稳。
`--dt .00125` 可进行半步长复验。构造失败、原生进程中止、资源等待超时均保存并如实标记，
不视为静稳通过。静稳结论独立于任务解法及难度资格。三档当前证据见[任务说明](../docs/develop/tasks/orbits_zh.md)。
