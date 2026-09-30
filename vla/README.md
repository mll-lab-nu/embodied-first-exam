# VLA 零样本评测

在 TopoGym 上用各模型的官方 checkpoint 做零样本评测（不微调）。计划与设计见 [`docs/IMPL_PLAN.md`](docs/IMPL_PLAN.md)、[`docs/DESIGN.md`](docs/DESIGN.md)。

评测和模型各用一个进程、一个 conda 环境，通过本机 TCP 一对一连接：

```text
评测进程（conda env topogym）                         模型进程（conda env vla-<model>）
run_eval ─ Env ─ VLAAgent ─ Adapter ─ RemoteClient ⇄ TCP ⇄ serve ─ BaseVLA 子类 ─ 官方推理代码
```

评测进程负责 reset、seed、step、录像和打分；模型进程只回答"观测 → 动作块"，同一时间只服务一个连接。

## 1. 安装（每台机器一次）

需要 conda 和 uv（`pip install uv`）。在仓库根目录执行：

```bash
bash vla/setup.sh topogym      # 评测环境：TopoGym + Nyx（仓库的 env_setup_gs121.sh），并准备 .external/nyx-assets
bash vla/setup.sh pi05         # 模型环境 vla-pi05；其余同理：groot、molmoact2、xvla
```

模型环境会把官方仓库克隆到 `vla/third_party/<model>` 并检出固定 commit，按官方说明安装，再把 checkpoint 下载到官方默认缓存。GR00T 需要先在 Hugging Face 上获得 [`nvidia/Cosmos-Reason2-2B`](https://huggingface.co/nvidia/Cosmos-Reason2-2B) 的访问权限。所有 GR00T checkpoint 都以它作为视觉语言主干。

## 2. 运行

两个终端，都在仓库根目录：

```bash
# 终端 1：模型服务。看到 "Serving ..." 后再启动评测
conda activate vla-pi05
python -m vla.models.serve --config vla/configs/models/panda_robotiq/pi05_droid_jointpos.yaml   # 默认端口 8000

# 终端 2：评测；等号形式的参数覆盖配置中的任意键
conda activate topogym
python -m vla.gym.run_eval --config vla/configs/eval/buzz_wire_3d.yaml task.seeds=[0] task.sim_seconds=10
```

- 端口在运行时指定，模型配置里没有端口。同时跑两个模型时，第二个服务加 `--port 8001`，对应的评测加 `policy.address=localhost:8001`。
- 不启动模型服务、只检查评测链路：加 `policy.local=vla/configs/models/aloha/hold_aloha.yaml`。`HoldVLA` 会把当前状态重复成动作块。
- 渲染用到的环境变量由 `run_eval` 自动补上，不需要 export：`TOPOGYM_VISUAL_ASSET_ROOT` 默认为 `.external/nyx-assets`；只要装了 NVIDIA 的 Vulkan 驱动，`VK_ICD_FILENAMES` 就只加载它。已经手动设置的值不会被覆盖。

## 3. 模型（按机器人）

`控制频率 → decimation`：模型训练数据的频率换算成每个动作保持的物理步数，`decimation = round(1 / (频率 × 0.0025 s))`；实际频率为 `1 / (decimation × 0.0025 s)`。`块长 / 执行`：每次推理预测的动作数，以及执行其中前几个后再推理。

**Panda + Robotiq**（如 `buzz_wire_3d`）：三个都是 DROID 训练的 checkpoint，输入关节状态，输出绝对关节目标，15 Hz → 27（实际 14.8 Hz）。

| 模型配置 `configs/models/panda_robotiq/` | conda env | TopoGym 相机 → 模型图像输入 | 块长 / 执行 |
|---|---|---|---|
| `pi05_droid_jointpos` | `vla-pi05` | agentview → 外部相机，wrist → 腕部相机 | 15 / 8 |
| `groot_n17_droid` | `vla-groot` | 同上；末端位姿输入由关节正运动学算出 | 40 / 8 |
| `molmoact2_droid` | `vla-molmoact2` | agentview、front_oblique → 两个外部相机，wrist → 腕部相机 | 15 / 15 |

**ALOHA**（如 `cast_coil`）：两条 vx300s 手臂，相机为 cam_high、cam_left_wrist、cam_right_wrist（俯视、左腕、右腕）。

| 模型配置 `configs/models/aloha/` | conda env | 状态 → 动作 | 控制频率 → decimation | 块长 / 执行 |
|---|---|---|---|---|
| `pi05_base_trossen` | `vla-pi05` | 关节 → 绝对关节 | 50 Hz → 8 | 50 / 25 |
| `xvla_robotwin2` | `vla-xvla` | 末端位姿 → 绝对末端位姿（TopoGym 用 IK 求关节） | 16.7 Hz → 24 | 30 / 30 |

块长、执行步数和夹爪阈值都取自各模型的官方推理示例或评测客户端。执行步数可以用 `run.execute_steps` 覆盖。每个包装层的 docstring 写明了官方入口、输入输出和单位。

## 4. 配置

```text
configs/eval/base.yaml                 评测默认值；configs/eval/<task>.yaml 继承它，只写 task.id
configs/models/<robot>/base.yaml       同一机器人的共同部分（embodiment、相机等）
configs/models/<robot>/<name>.yaml     一个 checkpoint 一个文件：class_path、checkpoint、spec、model
gym/instructions.py                    每个任务的英文指令与 VERSION（改动任何文本都要递增）
```

- 继承：`_base_: base.yaml`，也可以写成列表，路径相对当前文件。先按顺序合并各 base，再合并本文件。映射按键合并，其余值（包括列表）整体替换。
- 引用：OmegaConf 插值，例如 `${task.id}`，在合并后解析。
- 命令行：`run_eval` 之后的 `key=value` 最后生效。键名必须已存在，拼错会报错；只有 `env.*` 可以新增，这些键原样传给 `topogym.make`。

| 评测键 | 含义 |
|---|---|
| `policy.address` / `policy.local` | 模型服务 `host:port`（默认 `localhost:8000`），或在评测进程内运行的模型配置（仅 `HoldVLA`） |
| `task.id` / `variation` / `seeds` / `sim_seconds` | 任务、变体、seed 列表、每个 episode 的仿真时长 |
| `run.execute_steps` / `record` / `output` | 执行步数（null 表示用模型的值）、是否录像、输出目录（null 表示 `runs/test_results/<YYYYMMDD>_vla_<模型>_<任务>`，目录必须尚不存在） |
| `env` | 原样传给 `topogym.make`；辅助抓持默认关闭 |

## 5. 输出

每次评测（一个模型 × 一个任务）写一个目录：

```text
results.jsonl              每个 episode 一行：outcome、仿真时长、控制步、推理次数、跟踪误差、截断行数、墙钟等
summary.json               成功率、各类结果计数、PolicySpec、指令与版本、完整配置、git commit
report.md                  一行 Markdown 汇总
seed_<seed>/videos/*.mp4   每路相机一个 MP4（30 fps），另有 frame_map.jsonl、recording_manifest.json
```

多次评测的对比表：`python -m vla.gym.report runs/test_results/<目录> ...`。

- `outcome` 取值：`success`、`task_failure`、`time_limit`（到时限，任务判定未成功）、`unevaluated`（到时限，任务无法判定）、`unfinished`、`invalid_action`（如末端目标超出 IK 容差，物理未推进）、`policy_error`（模型出错、动作块形状不对或含 NaN、连接断开）、`env_error`。
- 跟踪误差：每一步取"发出的手臂目标 − 下一次测量"的 L2 范数，多条手臂取最大值，不含夹爪。单位由 `tracking_error_unit` 给出：关节动作为 rad，末端动作为 m。
- `clipped_actions`：关节超出限位、或夹爪开度超出 [0, 1] 而被截断的动作行数。

## 6. 测试

```bash
conda activate topogym && python -m pytest vla/tests -q     # 不需要 GPU
```

## 7. 已知问题

- ALOHA 夹爪初值：TopoGym ALOHA 的 home 夹爪开度约 0.18（接近闭合），openpi 的 ALOHA 变换会把它编码成训练中没有的状态 token。这里按官方变换原样保留。
- 仿真速度：每控制步的墙钟时间见 `docs/IMPL_PLAN.md` 第 13 节。
