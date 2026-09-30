# VLA 零样本评测

在 TopoGym 上用各模型的官方 checkpoint 做零样本评测（不微调）。计划与设计见 [`docs/IMPL_PLAN.md`](docs/IMPL_PLAN.md)、[`docs/DESIGN.md`](docs/DESIGN.md)。

两个进程、两个 Python 环境，本机 TCP 一对一连接：

```text
评测进程（.venv-gs121-nyx）                                  模型进程（vla/.envs/<model>）
run_eval ─ Env ─ VLAAgent ─ Adapter ─ RemoteClient ⇄ TCP ⇄ serve ─ BaseVLA 子类 ─ 官方推理代码
```

评测进程负责 reset、seed、step、录像和打分；模型进程只回答"观测 → 动作块"，同一时间只接一个连接。

| 路径 | 运行环境 | 内容 |
|---|---|---|
| `protocol.py` | 两侧 | `PolicySpec` / `Observation` / `ActionChunk`，线协议编解码（标准库 + numpy） |
| `gym/adapter.py` | TopoGym | TopoGym 观测 / 动作 ⇄ 标准向量（由 `action_spec` 驱动） |
| `gym/agent.py` | TopoGym | `VLAAgent`：每 `execute_steps` 步推理一次，检查动作块形状与有限性 |
| `gym/client.py` | TopoGym | `RemoteClient`、`LocalClient`、`PolicyError` |
| `gym/run_eval.py` | TopoGym | 评测入口 |
| `models/serve.py` | 模型环境 | 服务入口：按 `class_path` 加载模型 |
| `models/<model>/model.py` | 模型环境 | 每个模型一个 `BaseVLA` 子类；docstring 写明官方入口、输入输出与单位 |
| `configs/models/*.yaml` | — | 一个 checkpoint 一个文件：`class_path`、`checkpoint`、`port`、`spec`、`model` |
| `configs/eval/*.yaml` | — | 一次评测一个文件：`policy`、`task`、`run`、`env` |
| `configs/instructions.yaml` | — | 每个任务的英文指令（带版本号） |
| `setup.sh` | — | 建模型环境：`bash vla/setup.sh <pi05\|groot\|molmoact2\|xvla>` |

## 1. 环境

TopoGym 环境（仓库根目录执行一次；Nyx 渲染资源放 `.external/nyx-assets`）：

```bash
CUDA_TAG=cu126 INSTALL_NYX=1 VENV_DIR=.venv-gs121-nyx OPTIONAL_GROUPS="video test" bash env_setup_gs121.sh
TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets" .venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py
```

模型环境（每个模型一次）：克隆官方仓库到 `vla/third_party/<model>` 并检出固定 commit，用 uv 建 `vla/.envs/<model>`，按官方说明安装，下载 checkpoint 到官方默认缓存（openpi：`~/.cache/openpi`；其余：`~/.cache/huggingface`），最后做导入检查。

```bash
bash vla/setup.sh pi05        # openpi 215abfb；pi05_droid_jointpos + pi05_base，各 12.4 GB
bash vla/setup.sh molmoact2   # molmoact2 66b87e6；MolmoAct2-DROID 21.8 GB（bf16 运行约 10 GiB 显存）
bash vla/setup.sh xvla        # X-VLA 6bc2513；X-VLA-RoboTwin2 3.5 GB
bash vla/setup.sh groot       # Isaac-GR00T 51d4c89；GR00T-N1.7-DROID 6.9 GB，backbone 需要 HF 权限（见第 6 节）
```

每次运行前：

```bash
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
# 机器上有多个 Vulkan 设备（如 AMD 核显 + NVIDIA）时必须只加载 NVIDIA ICD，否则 Nyx 在建场景时 abort：
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
```

## 2. 快速上手

两个命令都在仓库根目录运行。先起模型服务，看到 `Serving <name> on (...)` 后再跑评测：

```bash
vla/.envs/pi05/bin/python -m vla.models.serve --config vla/configs/models/pi05_droid_jointpos.yaml
.venv-gs121-nyx/bin/python -m vla.gym.run_eval --config vla/configs/eval/buzz_wire_3d.yaml \
    task.seeds=[0] task.sim_seconds=10          # OmegaConf 命令行覆盖
```

换模型只改 `policy.address`（每个模型配置有自己的端口），例如 MolmoAct2：

```bash
vla/.envs/molmoact2/bin/python -m vla.models.serve --config vla/configs/models/molmoact2_droid.yaml
.venv-gs121-nyx/bin/python -m vla.gym.run_eval --config vla/configs/eval/buzz_wire_3d.yaml policy.address=localhost:8003
```

不连服务、在评测进程内跑占位策略（`HoldVLA` 把当前状态重复成动作块，用于检查链路）：

```bash
.venv-gs121-nyx/bin/python -m vla.gym.run_eval --config vla/configs/eval/smoke_hold_cast_coil.yaml
```

## 3. 模型

| 模型配置 | 端口 | 机器人 | 相机 → 模型槽位 | 状态 / 动作 | 频率 → decimation | 块长 / 执行 |
|---|---|---|---|---|---|---|
| `pi05_droid_jointpos` | 8000 | Panda | agentview → exterior_1，wrist → wrist | 关节 / 绝对关节 | 15 Hz → 27 | 15 / 8 |
| `pi05_base_trossen` | 8001 | ALOHA | cam_high、cam_left_wrist、cam_right_wrist | 关节 / 绝对关节 | 50 Hz → 8 | 50 / 25 |
| `groot_n17_droid` | 8002 | Panda | agentview → exterior_1，wrist → wrist | 关节（eef_9d 由正运动学算）/ 绝对关节 | 15 Hz → 27 | 40 / 8 |
| `molmoact2_droid` | 8003 | Panda | agentview、front_oblique、wrist → exterior_1、exterior_2、wrist | 关节 / 绝对关节 | 15 Hz → 27 | 15 / 15 |
| `xvla_robotwin2` | 8004 | ALOHA | cam_high、cam_left_wrist、cam_right_wrist → head、左腕、右腕 | 末端 / 绝对末端（`ee_abs`） | 16.7 Hz → 24 | 30 / 30 |

- 块长、执行步数、夹爪阈值都取各模型官方示例或评测客户端的值；执行步数可在评测配置 `run.execute_steps` 覆盖。
- 夹爪：π0.5 DROID 与 GR00T 按官方客户端在 0.5 处二值化；X-VLA 在 0.7 处二值化；MolmoAct2 与 π0.5 ALOHA 保持连续值。
- X-VLA 的末端位姿按"每臂相对自身基座"映射到 RoboTwin 世界系，并复现其训练时的四元数读取约定（`models/xvla/frames.py`）。

## 4. 配置

评测配置（`configs/eval/*.yaml`）：

| 键 | 含义 |
|---|---|
| `policy.address` | 模型服务 `host:port` |
| `policy.local` | 模型配置路径；非 null 时在评测进程内用 `LocalClient` 运行（只用于 `HoldVLA`） |
| `task.id` / `variation` / `seeds` / `sim_seconds` | 任务、变体、seed 列表、每个 episode 的仿真时长 |
| `run.execute_steps` | null 表示用 `PolicySpec.execute_steps` |
| `run.record` | 每个 episode 每路相机录一个 MP4 |
| `run.output` | null 表示 `runs/test_results/<YYYYMMDD>_vla_<模型>_<任务>`；目录必须尚不存在 |
| `env` | 透传给 `topogym.make`；辅助抓持默认关闭 |

`control_mode`、`observation_mode`、`control_decimation = round(1 / (control_hz × 0.0025))` 与 `max_physics_steps` 由 `PolicySpec` 和 `sim_seconds` 推出。

## 5. 输出

- `results.jsonl`：每个 episode 一行，字段为 `task`、`variation`、`seed`、`model`、`instruction_version`、`outcome`、`task_success`、`failure_code`、`sim_time_s`、`control_steps`、`inference_calls`、`tracking_error_mean`、`tracking_error_max`、`clipped_actions`、`reset_wall_s`、`rollout_wall_s`、`error`、`execute_steps`、`control_decimation`、`control_hz_actual`。
- `outcome`：`success`、`task_failure`、`time_limit`、`unevaluated`、`unfinished`、`invalid_action`（IK 失败等，物理未推进）、`policy_error`（模型出错、动作块形状不对或含 NaN、超时 600 s、断开）、`env_error`。
- 跟踪误差：每步取各臂"发出的臂目标 − 下一次观测"的 L2 范数的最大值（关节 rad 或 TCP 位置 m，不含夹爪）。
- `clipped_actions`：关节超限或开度超出 [0, 1] 而被截断的动作行数。
- `summary.json`：成功率、各类结果计数、`PolicySpec`、指令与版本、完整配置快照、`git rev-parse HEAD`。
- 录像：`seed_<seed>/videos/<相机>.mp4`（30 fps）、`frame_map.jsonl`、`recording_manifest.json`。

## 6. 已知问题

- **GR00T**：所有 GR00T checkpoint 都要加载 gated 的 `nvidia/Cosmos-Reason2-2B`；当前 HF 账号返回 403。在该模型页面申请权限后重跑 `bash vla/setup.sh groot` 即可。
- **ALOHA 夹爪初值**：TopoGym ALOHA 的 home 夹爪开度约 0.18（接近闭合）；openpi 的 ALOHA 变换会把它编码成训练中没有的状态 token。按官方变换原样保留。
- **仿真速度**：实测每控制步墙钟见 `docs/IMPL_PLAN.md` 第 13 节。

## 7. 测试

```bash
.venv-gs121-nyx/bin/python -m pytest vla/tests -q     # 不需要 GPU
```
