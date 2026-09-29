# Simulator 测试逐脚本说明与运行入口

日期：2026-09-24。本次接口验收快照有 **32 个 test_*.py 脚本**，另有 conftest.py 与 runtime_evidence.py 支持。并行场景会话随后增加1个测试与3个辅助文件，当前 tests/ 合计 **33 个测试脚本、5个辅助文件**，另见末节。脚本数量不是 pytest 参数化用例数量；实际通过/失败/未运行以[本轮实施报告](simulator_public_api_implementation_20260924_zh.md)为准。GPU 验收现按用户要求暂停，不能把下列测试已存在当作已通过。

测试区分非引擎合同和真实物理。替身测试不能证明物理有效；真实运行必须保留配置、源码身份、状态数组、日志、原始图像和实际 MP4。agent/网络实验不在范围内。

## 1. 公共支持

- [`tests/conftest.py`](../../../tests/conftest.py)：可控的假 World/Robot/Task 驱动真实 Env 编排，注入异常并测试权限与 tick 历史。
- [`tests/runtime_evidence.py`](../../../tests/runtime_evidence.py)：逐阶段报告、NPZ 状态、物理诊断、真实 Nyx/compact_lab/4或3视角检查、原始 PNG、公共录制、媒体解码和 rewind 失效事件。
- [`scripts/test_base_tasks.py`](../../../scripts/test_base_tasks.py)：串行独立进程运行选择的真实用例，保存每项源码哈希/快照、JUnit/日志、超时/失败以及可点击结果索引；源码运行中变化标为 source_changed。

## 2. 架构

- [`tests/architecture/test_module_boundaries.py](../../../tests/architecture/test_module_boundaries.py)：静态检查 Genesis 唯一后端、World 唯一物理时钟、Task 不接管输出以及公共模块命名/目录边界。

## 3. 本地接口与历史合同

- [`tests/contracts/test_env_lifecycle.py](../../../tests/contracts/test_env_lifecycle.py)：替身 World 验证动作/物理时间、动作中途终止、时间截断、非法动作、分阶段异常、关闭失败和恢复条件。
- [`tests/contracts/test_episode_rewind.py](../../../tests/contracts/test_episode_rewind.py)：验证每个 tick 的保存、回溯后旧未来永久失效、ID 不复用、同 tick/动作中途回溯以及终态和时限恢复。
- [`tests/contracts/test_privileged_access.py](../../../tests/contracts/test_privileged_access.py)：验证未授权不能取得特权、白名单数据不可变、管理方相同/不同 seed reset 和 episode 身份边界。
- [`tests/contracts/test_public_api.py](../../../tests/contracts/test_public_api.py)：验证惰性 env_list、13 任务 × 两种观察规格、未知任务拒绝；普通/特权操作方都无 reset，管理方 reset 后句柄失效。

## 4. 配置、资产与纯数值

- [`tests/unit/test_asset_library.py](../../../tests/unit/test_asset_library.py)：核对资源 catalog、生成资产内容哈希、路径越界和文件篡改；允许不生成网格的 primitive 任务。
- [`tests/unit/test_collision_certificates.py](../../../tests/unit/test_collision_certificates.py)：检查盒/凸体的分离与包含、连续运动中途碰撞、材料位移界和无法确定时不能报告安全。
- [`tests/unit/test_configuration.py](../../../tests/unit/test_configuration.py)：检查配置范围/类型、不可变参数、单/双臂默认选择、唯一 compact_lab 和 CPU 显式关闭 RGB。
- [`tests/unit/test_control_modes.py](../../../tests/unit/test_control_modes.py)：以窄 Robot/IK 替身验证实测增量、世界轴左乘旋转、TCP 偏移和全动作校验；不证明真实 IK 收敛。
- [`tests/unit/test_material_specs.py](../../../tests/unit/test_material_specs.py)：验证 PBD/FEM 材料声明参数及非法输入；材料合法不等于物理积分已经通过。
- [`tests/unit/test_robot_descriptions.py](../../../tests/unit/test_robot_descriptions.py)：验证两种机器人关节/驱动/夹爪单位、home 和原子命令提交及完整控制目标恢复。
- [`tests/unit/test_seed_streams.py](../../../tests/unit/test_seed_streams.py)：验证命名随机子流不依赖调用顺序，以及 Python/NumPy/Torch 的 A→B→A 设种子复现。
- [`tests/unit/test_task_definitions.py](../../../tests/unit/test_task_definitions.py)：遍历 13 项任务生成实体，检查名称、资源、数值和参数；包括 Blanket 织纹、UV 与哈希声明。
- [`tests/unit/test_task_state.py](../../../tests/unit/test_task_state.py)：验证稳定判据只随物理 tick 更新、首次达标不多算时间、失败优先，以及判据/RNG 回溯。
- [`tests/unit/test_task_support.py](../../../tests/unit/test_task_support.py)：核对 13 项能力清单，未完成判据不得发成功奖励，FEM CPU 提前拒绝；缺 assist 与不能运行分开。
- [`tests/unit/test_task_variations.py](../../../tests/unit/test_task_variations.py)：遍历 base 和具名变体的参数合并、输入隔离及未知变体拒绝。
- [`tests/unit/test_world_diagnostics.py](../../../tests/unit/test_world_diagnostics.py)：检查 NaN/Inf 定位到实体与字段、空接触合法；压缩状态保留 signed zero、NaN payload 和结构化数组。

## 5. 数据与录制合同

- [`tests/recording_data/test_dataset_transitions.py](../../../tests/recording_data/test_dataset_transitions.py)：验证原命令与实测运动分离、JSONL/HDF5 读回、连续时间和分段关系；回溯使已关闭/未关闭数据的旧未来索引作废。
- [`tests/recording_data/test_recording_branches.py](../../../tests/recording_data/test_recording_branches.py)：用编码器替身检查多视角同源、重复帧身份、跨回溯必须新开录制段以及失败不发布完整视频。
- [`tests/recording_data/test_snapshot_isolation.py](../../../tests/recording_data/test_snapshot_isolation.py)：检查数组深拷贝/只读、Transition 隔离以及同 tick 回溯后旧图像缓存不被复用。

## 6. 真实引擎与多视角录像

- [`tests/integration/test_base_task_runtime.py](../../../tests/integration/test_base_task_runtime.py)：逐项运行 13 个基础任务：真实 reset/机器人响应/step、每 tick 保存、动作中途回溯与续跑、旧未来拒绝、初态回溯和 seed A→B→A（资产、物理数组、原始 RGB）。
- [`tests/integration/test_genesis_fem_ipc.py](../../../tests/integration/test_genesis_fem_ipc.py)：小型真实 FEM/IPC 探针：体变形、端约束、原生 checkpoint、释放/重建和继续积分，并保留诊断视频。
- [`tests/integration/test_task_switch_runtime.py](../../../tests/integration/test_task_switch_runtime.py)：同进程切换多类任务，检查引擎参数/场景资源/注册入口不会相互污染，保存每个场景的录像。
- [`tests/integration/test_interface_modes.py](../../../tests/integration/test_interface_modes.py)：两种机器人分别运行 JOINT/EE 观察 × 四种控制：真实可达小幅 EE/关节运动、夹爪动作、不可达输入原子拒绝、回溯和操作方权限。
- [`tests/integration/test_lifecycle_stability.py](../../../tests/integration/test_lifecycle_stability.py)：G2：每种机器人十轮 reset、10+7 tick 时限、终止后拒绝 step、实际积分后异常注入、回溯恢复与继续；记录内存/句柄，并检查预热后的有界增长。
- [`tests/integration/test_observation_rig.py](../../../tests/integration/test_observation_rig.py)：两种机器人真实 Nyx 图像：彩色实体中心的内外参投影误差≤3像素，腕部相机随关节运动的安装变换正确，多视角848×480。
- [`tests/integration/test_output_invariance.py](../../../tests/integration/test_output_invariance.py)：比较无 RGB/视频/数据消费者与启用全部被动消费者的相同输入轨迹；重复 observe/render 不推进物理，逐状态比较容差2e-6。
- [`tests/integration/test_installed_simulator.py](../../../tests/integration/test_installed_simulator.py)：构建 wheel、安装到新 venv、从仓库外导入并执行 make/reset/step/render/close；复用已固定引擎依赖和显式外部资产。
- [`tests/integration/test_genesis_robot.py](../../../tests/integration/test_genesis_robot.py)：较窄的真实机器人命令原子性、目标/状态恢复、FK/IK 不移动机器人检查；当前只写断言，未接入统一录像驱动。
- [`tests/integration/test_genesis_seed_reset.py](../../../tests/integration/test_genesis_seed_reset.py)：较窄的真实引擎初态 seed A→B→A 检查；当前未接入统一录像驱动，完整 base 用例覆盖其关键路径。
- [`tests/integration/test_genesis_world_history.py](../../../tests/integration/test_genesis_world_history.py)：直接 World 层检查重力接触、随机状态、空间哈希恢复、非本 World checkpoint 拒绝与能力缺失；当前未接入统一录像驱动。
- [`tests/integration/test_task_lifecycle.py](../../../tests/integration/test_task_lifecycle.py)：早期 Task/World 生命周期、PBD 布形变与图像缓存检查；当前未接入统一录像驱动，其重合路径由 base 验收执行。

## 7. 运行命令与证据范围

从仓库根目录执行；输出目录必须尚不存在。默认 pytest 排除 Genesis/HDF5，下面第一条显式包含已安装 HDF5 的读回检查。

```bash
.venv-gs121-nyx/bin/python -m pytest -q -m "not genesis"

# 13 个基础任务和 FEM/同进程切换机制；200动作 = 5秒主连续物理片段
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py --steps 200 --timeout 3600 \
  --output runs/test_results/simulator_base_local

# 新接口、G2、相机、输出一致性与 wheel 安装
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --checks interfaces stability cameras outputs installation --timeout 3600 \
  --output runs/test_results/simulator_contract_local
```

- GPU 验收默认使用 `.external/nyx-assets`，可通过 `--visual-asset-root` 指定资源目录；缺少设备/资源明确失败。
- 每 tick 全状态快照成本显著。`--steps 20` 仅表示0.5秒主段的短程 smoke，不能当作长时稳定性；接口/G2等用例有自己的明确步数。
- G2 资源门限：第4轮之后 RSS增长≤1GiB、FD增长≤8、Torch CUDA allocated/reserved增长≤256MiB；这是有界 smoke，不能排除更慢的泄漏，也不是原生 CUDA 总占用计量。
- 输出一致性关闭 RGB 的对照组保存物理数组；启用组保存真实视频，没有为无图像组伪造视频。
- 未纳入统一证据驱动的4个旧真实脚本本轮不直接运行，不计通过。更长接触轨迹、大范围seed和全部Task成功正反例仍需独立验收。

## 8. 并行场景会话新增的测试与工具

以下文件已纳入当前全仓脚本清单，由场景会话负责；本会话只读登记，没有修改或运行它们，不能将174项非引擎通过数套用到这些新增测试。

- [`tests/unit/test_scene_presets.py`](../../../tests/unit/test_scene_presets.py)：检查场景声明中的自由环、实体支撑、URDF跨目录复现，以及视觉修复不改变物理网格、关节和连接。
- [`tests/scene_preset_evidence.py`](../../../tests/scene_preset_evidence.py)：扩展公共 RuntimeEvidence，保存场景预设验收和源码身份。
- [`tests/scene_preset_diagnostics.py`](../../../tests/scene_preset_diagnostics.py)：构造单独的重力诊断场景，并检查自由环的实际下落。
- [`tests/scene_preset_pickup.py`](../../../tests/scene_preset_pickup.py)：基于实际碰撞几何查询并通过公共动作执行接近、抓持、抬升、放回与释放的专门验收。
- [`scripts/test_scene_presets.py`](../../../scripts/test_scene_presets.py)：运行场景预设和诊断记录，使用现有 Env 与公共录制模块。
