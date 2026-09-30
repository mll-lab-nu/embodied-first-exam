# VLA 接入实施计划

| 项 | 值 |
|---|---|
| 状态 | P0 未开始 |
| 目标 | 只评测（零样本）：用各模型官方 checkpoint，不微调 |
| 分支 | `dev/pingyue`；不提交 `main`，不 push（除非用户要求） |
| 设计文档 | [`README.md`](README.md)、[`index.html`](index.html) |
| 更新 | 2026-09-29 |

**用法**：开始前读第 1–5 节。完成一项就勾选，并在该项后写 `证据：<路径 / 命令 / commit>`；没有证据不勾。改计划时在第 10 节追加记录。"待确认"的事项先问用户。

---

## 1. 原则

1. **只改 `vla/`**。不改仓库其他目录（`topogym/`、`tasks/`、`tests/`、`configs/`、`scripts/` 等）。确需改动时停下来，列出文件和原因，问用户。
2. **复用已有代码**（第 3 节）。仿真器已有的功能（环境循环、动作校验、观测、录像）不重写。
3. **Simple**：协议 3 个数据类；Gym 侧一个通用适配器；每个模型一个子类；不加插件框架和用不到的配置项。
4. **依赖隔离**：模型不装进 TopoGym 环境（`env_setup_gs121.sh` 建的 `.venv-gs121`），每个模型一个独立环境。TopoGym 环境只额外装 `msgpack`、`websockets` 两个纯 Python 包。不装 `openpi-client`，它要求 `numpy<2`，与 TopoGym 的 `numpy==2.4.4` 冲突。
5. **证据**：真实运行的产物放 `runs/test_results/<日期>_vla_<名称>/`。静态检查和单测不能当作"模型能跑 / 成功"的证据。显存不够时不要启动，给用户 CLI。CPU 或内存到 90% 时停止本轮启动的进程。

## 2. 完成标准

- 换模型只改评测配置里的 `policy.url`。
- 每个 episode 在 `results.jsonl` 里有一行、每路相机一个 MP4。结果分为 `success / task_failure / time_limit / unevaluated / invalid_action / policy_error / env_error`。
- 首批矩阵（第 7 节）跑完，出对比表。零样本成功率预期接近 0，结论只写测得的数字。

## 3. 复用什么

| 已有代码 | 用法 |
|---|---|
| `topogym.make` / `Env` / `env.interaction()` | 直接用：管理方 reset，策略只拿操作句柄 |
| `actor.action_spec`（臂顺序、关节名、限位、夹爪字段和范围） | 驱动通用适配器，不另写机器人描述 |
| `docs/vla_doc/vla_eval_demo.py`：`VLAPolicy`、`classify`、`run_episode`、`GRIPPER_OPEN_CLOSED` | 拆成 adapter / agent / run_eval，字段约定保持一致 |
| `topogym.recording.session.RecordingSession` + `env.add_frame_sink` | 录像，不写视频代码 |
| `env.tick_record()["robot"]`（即 `robot.observe()`） | 完整本体感知：关节 + TCP 位姿（GR00T 需要，先实测开销）；`joint_position_target_rad`（算跟踪误差） |
| 任务类的 `instruction` 属性 | 5 个任务的指令来源 |
| OmegaConf（hydra-core 已是项目依赖） | 读评测配置和命令行覆盖 |

## 4. 结构

```text
Gym 进程（TopoGym 环境）= 客户端                     模型进程（每个模型独立环境）= 服务端
run_eval ─ Env ─ VLAAgent ─ Adapter ─ Client ⇄ ws ⇄ serve ─ BaseVLA 子类 ─ 官方推理代码
```

```text
vla/
├── README.md                 快速上手：装环境 → 下 checkpoint → 起服务 → 跑评测
├── setup.sh                  唯一安装入口：setup.sh gym | pi05 | groot | molmoact2 | xvla
├── protocol.py               PolicySpec / Observation / ActionChunk + msgpack 编解码（两侧共用）
├── gym/                      只在 TopoGym 环境使用
│   ├── adapter.py            通用适配器：TopoGym obs ⇄ 标准向量（由 action_spec 驱动）
│   ├── agent.py              VLAAgent：initialize / act + 动作块队列
│   ├── client.py             WebsocketClient、LocalClient
│   └── run_eval.py           读配置 → 评测 → results.jsonl / summary.json / MP4
├── models/                   只在各模型环境使用
│   ├── base.py  serve.py     BaseVLA；WebSocket 服务
│   ├── dummy.py              HoldVLA（重复当前 state，用于测试链路）
│   └── pi05/ groot/ molmoact2/ xvla/     每个目录一个 model.py
├── configs/
│   ├── eval/*.yaml           评测配置
│   ├── models/*.yaml         服务配置（模型、checkpoint、端口）
│   └── instructions.yaml     每个任务的英文指令（带版本号）
└── tests/                    不需要 GPU 的单测
```

**`setup.sh`**：`gym` 分支给 TopoGym 环境（默认 `.venv-gs121`）装 `msgpack`、`websockets`。模型分支走同样 4 步：克隆官方仓库到固定 commit → 建 `vla/.envs/<model>/` → 按官方 README 安装，再装 `msgpack`、`websockets` → 下载 checkpoint。每个模型在 `case` 里只写 4 项：仓库、commit、安装命令、checkpoint。`vla/.gitignore` 忽略 `.envs/` 和克隆的仓库。

## 5. 接口要点

**术语**：policy 指任意"观测 → 动作"的映射，VLA 是其中一种。接口层按 policy 命名（`PolicySpec`、`policy.url`、`policy_error`），模型层按 VLA 命名（`BaseVLA`、`HoldVLA`）。

**数据类**（`vla/protocol.py`）：

| 类 | 字段 |
|---|---|
| `PolicySpec`（服务端连接时发送） | `protocol_version`、`name`、`embodiment`（aloha / panda_robotiq）、`cameras`、`image_size`、`action_space`（joint_abs / ee_abs）、`control_hz`、`chunk_size`、`execute_steps` |
| `Observation` | `images`（相机名 → HWC uint8）、`state`（当前实测本体感知，扁平向量）、`instruction`、`episode_id`、`step` |
| `ActionChunk` | `actions`（H × D，绝对目标） |

**标准向量**：ALOHA `joint_abs` 14 维 `[左 6, 左开度, 右 6, 右开度]`；Panda 8 维 `[7, 开度]`。`ee_abs` 每臂 `[xyz, rot6d, 开度]`（ALOHA 20 维，Panda 10 维）。开度 ∈ [0, 1]，1 = 全开。相对量在模型子类里换算成绝对值。

**适配器**：一个类，两种机器人共用。臂顺序、关节名、限位、夹爪字段都从 `action_spec` 读取。每种机器人只有一行常量：夹爪开 / 合值（沿用 `GRIPPER_OPEN_CLOSED`）和默认相机。越界先截断再交给 `step`。

**消息**（msgpack，WebSocket）：服务端先发 `spec`；客户端发 `reset(seed)` → `ok`；`infer(obs)` → `chunk(actions)`；出错回 `error`，客户端记为 `policy_error`。一对一：一个评测进程连一个模型服务，服务端同一时间只接受一个连接；`reset` 清空模型内部状态（历史帧、随机种子）。

**PolicySpec → `topogym.make`**：`embodiment → robot_id`；`action_space → control_mode`（`JOINT_ABS` / `EE_ABS`）与 `observation_mode`；`control_hz → control_decimation = 400 / control_hz`（非整数时见 D2）。

## 6. 评测配置

```yaml
# vla/configs/eval/pi05_droid_buzz_wire.yaml
policy:
  url: ws://localhost:8000          # 换模型只改这里
task:
  id: buzz_wire_3d
  variation: base
  seeds: [0, 1, 2]
  sim_seconds: 60
run:
  execute_steps: null               # null = 用 PolicySpec 默认值
  record: true
  output: runs/test_results/20261001_vla_pi05_buzz_wire
env: {}                             # 额外透传给 topogym.make 的参数（如 grasp_assist）
```

```bash
bash vla/setup.sh gym                                                                  # 一次性
bash vla/setup.sh pi05                                                                 # 一次性
vla/.envs/pi05/bin/python -m vla.models.serve --config vla/configs/models/pi05_droid_jointpos.yaml
python -m vla.gym.run_eval --config vla/configs/eval/pi05_droid_buzz_wire.yaml \
    task.seeds=[0] run.record=false                                                  # TopoGym 环境，命令行覆盖
```

## 7. 首批矩阵（零样本）

| 机器人 · 任务 | 模型 · checkpoint |
|---|---|
| Panda · `buzz_wire_3d` | π0.5 `pi05_droid_jointpos`；GR00T `GR00T-N1.7-DROID`；MolmoAct2 `MolmoAct2-DROID` |
| ALOHA · `cast_coil` | π0.5 `pi05_base`（trossen 统计量）；X-VLA `X-VLA-RoboTwin2`（`ee_abs`） |

## 8. TODO

**P0 骨架（无 GPU）**
- [ ] `protocol.py` + 单测：编解码往返逐位相等
- [ ] `gym/adapter.py` + 单测：两种机器人的 state 排列、开度换算、截断、动作字典
- [ ] `gym/agent.py` + 单测：H=50、execute=10 时，25 次 `act` 只推理 3 次
- [ ] `gym/client.py`（LocalClient）、`models/base.py`、`models/dummy.py`
- [ ] `setup.sh`（`gym` 分支 + 模型分支的公共步骤）、`README.md` 初版

**P1 评测循环（GPU）**
- [ ] `configs/instructions.yaml`：5 条取自任务类，8 条新写（交用户确认）
- [ ] `gym/run_eval.py`：OmegaConf 读配置，逐 seed 写结果，可选录像；每个控制步记录跟踪误差（关节目标 − 实测），`summary.json` 写均值和最大值
- [ ] 冒烟：HoldVLA 跑 `cast_coil`、`buzz_wire_3d` 各 1 seed，结果与 `vla_eval_demo.py` 一致
- [ ] 实测并记录：每步墙钟、显存峰值、`tick_record()` 开销

**P2 服务**
- [ ] `models/serve.py`、`gym/client.py` 的 WebsocketClient（版本校验、超时、错误）
- [ ] 冒烟：同一配置改走 `ws://`，结果与 LocalClient 一致

**P3 模型**（每项：`setup.sh` 里一个分支 + `model.py` + 1 seed 冒烟）
- [ ] π0.5：Panda `pi05_droid_jointpos`；ALOHA `pi05_base`
- [ ] GR00T N1.7：Panda `GR00T-N1.7-DROID`（需要关节 + TCP，见第 3 节 `tick_record`）
- [ ] MolmoAct2：Panda `MolmoAct2-DROID`
- [ ] X-VLA：ALOHA `X-VLA-RoboTwin2`（同时实现适配器的 `ee_abs` 分支）

**P4 约定核对**（影响零样本结果）
- [ ] ALOHA 关节零位与正方向 vs openpi 约定 → 决定 `adapt_to_pi`
- [ ] 夹爪范围、相机位置（vs DROID）、末端坐标系（vs GR00T / X-VLA）
- [ ] 跟踪误差：冒烟中的"目标 − 实测"与真机数据集中的量级对比（Panda 增益与 DROID 真机控制器是否一致未核对）

**P5 首批评测**
- [ ] 按 P1 实测吞吐算预算，与用户确认 seed 数和时长
- [ ] 跑第 7 节矩阵，出对比表（附 `execute_steps`、实际控制频率、指令版本）

**之后（等用户决定）**：过程指标；微调。微调的设计见 [`README.md`](README.md) 3.8：演示经同一个适配器导出为 LeRobot 数据集，用各模型官方训练脚本训练。接口不变：模型侧只换 checkpoint 路径，Gym 侧加一个导出脚本。

## 9. 待确认

| # | 问题 | 建议 |
|---|---|---|
| D1 | 评测时是否开辅助抓持 | 零样本先关，整批统一 |
| D2 | 15 Hz 模型：`control_decimation=27`（14.81 Hz）还是在子类按时间重采样 | 取 27，结果里记录实际频率 |
| D3 | 8 个任务的英文指令 | P1 起草，用户确认 |
| D4 | `execute_steps` | 先用各模型官方示例值，再做一次减半对照 |
| D5 | 设计文档是否移入 `vla/`（让所有改动都在 `vla/` 内） | 待用户决定 |

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 创建；阶段目标为只评测 |
| 2026-09-29 | 精简为高层计划；限定只改 `vla/`；适配器改为一个通用类；`run_eval` 改为配置驱动；增加 `vla/README.md` 与各模型 `setup.sh`；`protocol` 合并为一个文件 |
| 2026-09-29 | 去掉 SegmentRunner；连接限定一对一；安装合并为 `vla/setup.sh`；P1 记录跟踪误差；补充术语和微调扩展方式 |
