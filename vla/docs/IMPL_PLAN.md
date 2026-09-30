# VLA 接入实施计划

| 项 | 值 |
|---|---|
| 状态 | P0–P4 已完成；P5 首批（每模型 3 seed × 30 s）已跑完，四个可运行模型成功率均为 0/3；GR00T 等待 HF 权限，D3 与完整预算待确认 |
| 目标 | 只评测（零样本）：用各模型官方 checkpoint，不微调 |
| 分支 | `dev/pingyue`；不提交 `main`；不 push（除非用户要求） |
| 范围 | 只改仓库根 `vla/` |
| 背景 | [`DESIGN.md`](DESIGN.md)：设计背景与模型调研（各模型输入输出见 4.5）；[`index.html`](index.html)：可视化版本 |
| 更新 | 2026-09-30（实施） |

**给实现者**：新 session 从本文件开始。本文件是实现的唯一依据，与 `DESIGN.md` 不一致时以本文件为准。先读第 0–8 节，再按第 10 节做。每完成一项就勾选，并在该项后写 `证据：<路径 / 命令 / commit>`，没有证据不勾。改计划时在第 13 节追加记录。标"待确认"的事项先问用户。

---

## 0. 开始前

1. `git branch --show-current` 必须是 `dev/pingyue`。
2. 读仓库根的 `CLAUDE.md` 和 `AGENTS.md`，照做：先读后写、最小改动、不过度抽象、用测试验证。
3. **TopoGym 环境**：conda env `topogym`（Genesis 1.2.1 + Nyx，Python 3.11），由 `bash vla/setup.sh topogym` 建立：仓库的 `env_setup_gs121.sh` 装进该 conda 环境，渲染资源放 `.external/nyx-assets`。
   - 2026-09-30 最初按 tests/README 建的是 `.venv-gs121-nyx`；同日按用户要求改为 conda（第 13 节）。
   - 本机 Vulkan 可见 AMD 核显、llvmpipe 和 RTX 4090，只加载 NVIDIA ICD 时 Nyx 才能建场景。`run_eval` 启动时自动补上 `VK_ICD_FILENAMES`（装了 NVIDIA Vulkan 驱动时）和 `TOPOGYM_VISUAL_ASSET_ROOT`，已设置的值不覆盖。
   - P0 的适配器测试需要 `import topogym` 并构建 `action_spec`，不需要 GPU；CPU 版 `.venv-gs121`（`bash env_setup_gs121.sh`）就够。协议、agent、服务的测试只依赖 numpy。
4. **硬件**：本机 1 张 RTX 4090（24 GB）。刚体任务的仿真约占 2–3 GB 显存，模型与仿真同卡。显存不够时不要启动，把命令交给用户。

## 1. 原则

1. **只改 `vla/`**。仓库其他目录（`topogym/`、`tasks/`、`tests/`、`configs/`、`scripts/`、`docs/` 等）一律不改。确需改动时停下来，列出文件和原因，问用户。
2. **复用已有代码**（第 8 节）：环境循环、动作校验、观测、录像都不重写。
3. **Simple**：
   - 协议只有 3 个数据类；Gym 侧一个通用适配器；每个模型一个子类。
   - 事实写在配置里，逻辑写在代码里。
   - 没有注册表、插件框架或用不到的配置项。
   - 代码风格跟 `topogym/` 一致：短 docstring、dataclass、直接的函数。
4. **依赖隔离**：
   - TopoGym 环境不装任何新包，传输只用标准库。
   - 每个模型一个独立 conda 环境 `vla-<model>`；所有 conda 环境设 `PYTHONNOUSERSITE=1`，不读 `~/.local` 里的包。
   - 不装 `openpi-client`：它要求 `numpy<2`，TopoGym 是 `numpy==2.4.4`。
5. **证据**：
   - 真实运行的产物放 `runs/test_results/<YYYYMMDD>_vla_<名称>/`（`runs/` 已被 git 忽略）。
   - 单测和静态检查不能作为"模型能跑 / 评测成功"的证据。
   - CPU 或内存到 90% 时，停止本轮启动的进程。

## 2. 完成标准

- 换模型只需起另一个模型服务；端口在运行时指定（`serve --port`，评测侧 `policy.address`），不写在模型配置里。
- 每个 episode 在 `results.jsonl` 里写一行（字段见第 6 节）；开录像时，每路相机一个 MP4。
- `pytest vla/tests -q` 全部通过。
- 首批矩阵（第 9 节）跑完并出对比表。零样本成功率预期接近 0，结论只写测到的数字。

## 3. 架构

两个进程、两个 Python 环境，用本机 TCP 一对一连接：

```text
评测进程 · conda env topogym                              模型进程 · conda env vla-<model>
run_eval ─ Env ─ VLAAgent ─ Adapter ─ RemoteClient ⇄ TCP ⇄ serve ─ BaseVLA 子类 ─ 官方推理代码
```

- **评测进程是客户端**，驱动循环：reset、seed、step、录像、打分都在这里。
- **模型进程是服务端**，只回答"观测 → 动作块"。它同一时间只接受一个连接；评测进程断开后，等待下一个连接。
- `LocalClient` 在评测进程内直接调用 `BaseVLA`，只用于测试和 `HoldVLA`。

## 4. 目录

```text
vla/
├── README.md              快速上手：装环境 → 下 checkpoint → 起服务 → 跑评测
├── setup.sh               建 conda 环境：bash vla/setup.sh <topogym|pi05|groot|molmoact2|xvla>
├── .gitignore             third_party/  .envs/（旧 uv 环境，删除前保留）
├── __init__.py
├── protocol.py            PolicySpec / Observation / ActionChunk、encode / decode（标准库 + numpy）
├── config.py              load_yaml：YAML 配置 + _base_ 继承（两侧共用，只依赖 OmegaConf）
├── gym/                   只在 TopoGym 环境运行；可 import topogym
│   ├── adapter.py         Adapter：TopoGym 观测 / 动作 ⇄ 标准向量
│   ├── agent.py           VLAAgent：动作块队列
│   ├── client.py          RemoteClient、LocalClient、PolicyError
│   ├── instructions.py    每个任务的英文指令与 VERSION
│   ├── report.py          输出目录 → Markdown 汇总表
│   └── run_eval.py        入口：读配置 → 评测 → results.jsonl / summary.json / report.md / MP4
├── models/                只在模型环境运行；不 import topogym
│   ├── base.py            BaseVLA
│   ├── serve.py           入口：读模型配置 → 加载 → TCP 服务
│   ├── dummy.py           HoldVLA：把当前 state 重复成动作块，用于测试链路
│   └── pi05/ groot/ molmoact2/ xvla/      每个目录一个 model.py
├── configs/
│   ├── models/<robot>/    base.yaml + 一个 checkpoint 一个文件（第 7 节）
│   └── eval/              base.yaml + 一个任务一个文件（第 7 节）
├── tests/                 不需要 GPU
└── docs/                  本文件、DESIGN.md、index.html + img/
```

**`setup.sh`** 每个目标建一个 conda 环境（已存在则复用）。`topogym`：用仓库的 `env_setup_gs121.sh` 装进 conda 环境，再准备 nyx-assets。模型走同样的步骤：
1. 把官方仓库克隆到 `vla/third_party/<model>`，检出固定 commit；
2. 建 conda 环境 `vla-<model>`（设 `PYTHONNOUSERSITE=1`）；
3. 按官方 README 安装（有 lock 文件时 `uv sync` 装进该 conda 环境），再装 `omegaconf`；
4. 下载 checkpoint 到官方默认缓存目录；
5. 做一次 import 冒烟检查。

每个目标在 `case` 分支里只写：环境名、仓库、commit、Python 版本、安装命令、checkpoint。

## 5. 接口

```python
# vla/protocol.py —— 两侧共用
PROTOCOL_VERSION = 2

@dataclass(frozen=True)
class PolicySpec:              # 服务端连接后第一条消息；内容来自模型配置的 spec 段
    name: str                  # checkpoint 名，如 "pi05_droid_jointpos"
    embodiment: str            # TopoGym robot_id："aloha" | "panda_robotiq"
    cameras: tuple[str, ...]   # 需要的 TopoGym 相机名，顺序对应子类里官方图像键的顺序
    state_keys: tuple[str, ...]  # ("joint",) | ("ee",) | ("joint", "ee")
    action_space: str          # "joint_abs" | "ee_abs"
    control_hz: float          # 训练数据的控制频率
    chunk_size: int            # H：每次推理预测的目标数
    execute_steps: int         # k：执行前 k 个目标后重新推理，其余丢弃；取官方示例值
    reach_tolerance_m: float = 0.0  # ee_abs：每个目标保持到各 TCP 进入该距离内（最多多 10 步）；0 = 每个目标一步
    protocol_version: int = PROTOCOL_VERSION

@dataclass(frozen=True)
class Observation:
    images: dict[str, np.ndarray]   # 相机名 → (480, 848, 3) uint8，原始分辨率；缩放等预处理在模型子类里用官方代码做
    state: dict[str, np.ndarray]    # state_keys 中每个键 → 标准向量（float32，当前实测值）
    instruction: str
    episode_id: str
    step: int                       # 控制步序号，从 0 开始

@dataclass(frozen=True)
class ActionChunk:
    actions: np.ndarray             # (H, D) float32，绝对目标，按 action_space 的标准向量排列
```

```python
# vla/models/base.py
class BaseVLA(ABC):
    def __init__(self, config): ...                   # 模型配置（第 7 节）；self.spec = PolicySpec(**config.spec)
    @abstractmethod
    def load(self) -> None: ...                       # 加载 checkpoint 到 GPU
    @abstractmethod
    def infer(self, obs: Observation) -> ActionChunk: ...
    def reset(self, seed: int) -> None: ...           # 清空历史帧，设随机种子

# vla/gym/*
Adapter(action_spec, spec)
    .observation(rgb, robot, instruction, episode_id, step) -> Observation
    .action(row) -> dict                              # 一行标准向量 → TopoGym 动作字典（先截断）
VLAAgent(client, adapter, execute_steps)
    .reset(seed, instruction, episode_id)             # 调 client.reset(seed)，清空队列；episode_id 用 Env 的
    .act(rgb, robot) -> dict                          # 队列为空时推理一次；检查块形状 (H, D) 且全部有限
RemoteClient(address) / LocalClient(model)            # 都有 .spec、.reset(seed)、.infer(obs)、.close()
```

**标准向量**：臂的顺序取 `action_spec["arms"]`（ALOHA 为 `left, right`）。

| 键 / action_space | 每臂布局 | ALOHA | Panda |
|---|---|---|---|
| `joint` / `joint_abs` | `[q₁ … qₙ, 开度]`，单位 rad | 14 | 8 |
| `ee` / `ee_abs` | `[x, y, z, r₁ … r₆, 开度]`，TopoGym 世界系，单位 m | 20 | 10 |

- `r₁…r₆`：旋转矩阵前两列按列展开，即 `[R11, R21, R31, R12, R22, R32]`。转回时先 Gram–Schmidt 正交化，再转成 `orientation_wxyz`。
- **开度** ∈ [0, 1]，1 = 全开。计算方法：`clip((原生值 − 全闭) / (全开 − 全闭), 0, 1)`。
  - 观测的原生值取 `finger_position_*[0]`。
  - 全开 / 全闭沿用 `vla_eval_demo.py` 的 `GRIPPER_OPEN_CLOSED`：aloha `(0.037, 0.002)` m，panda_robotiq `(0.0, 0.8)` rad。
- **动作截断**：关节截断到 `joint_limits_rad`，开度截断到 [0, 1]；`ee` 不截断。末端目标超出 Env 的 IK 容差时，按 RoboTwin 的做法逐臂跳过：先试只让一条臂保持实测位姿，再试所有臂，计入 `skipped_actions`。截断次数写进结果。
- 模型自己的约定由模型子类换算，包括相对 / 绝对、夹爪方向、坐标系。

**线协议**（标准库 `multiprocessing.connection`，`Listener` / `Client`，不设 authkey，默认只监听 localhost）：
- 每条消息用一次 `send_bytes` 发送，格式为 `[4 字节大端 header 长度][header：UTF-8 JSON][数组 1 原始字节][数组 2]…`。
- header 为 `{"msg": <消息，数组位置换成 {"__array__": i}>, "arrays": [{"dtype": "uint8", "shape": [480, 848, 3]}, …]}`。
- 数组先转成 C 连续。只收发字节，不用 `send` / `recv`（它们走 pickle）。

| 方向 | `type` | 内容 |
|---|---|---|
| 服务端 → 客户端 | `spec` | PolicySpec 字段；客户端校验 `protocol_version` |
| 客户端 → 服务端 | `reset` → 回 `ok` | `seed` |
| 客户端 → 服务端 | `infer` → 回 `chunk` | Observation 字段 → `actions` |
| 服务端 → 客户端 | `error` | `message`（traceback 文本）；客户端抛 `PolicyError` |

客户端等待回复不设时限（2026-09-30 用户决定）：服务端退出时连接断开，立即抛 `PolicyError`；服务端忙于另一个客户端时，排队等它断开。

## 6. 评测循环

```python
# vla/gym/run_eval.py（示意）
client = RemoteClient(cfg.policy.address)             # 测试时换成 LocalClient(HoldVLA(config))
spec = client.spec
dt = SimulatorConfig.physics_dt_s                     # 0.0025 s
make_args = dict(variation_id=cfg.task.variation,
                 control_mode={"joint_abs": "JOINT_ABS", "ee_abs": "EE_ABS"}[spec.action_space],
                 observation_mode="EE" if spec.state_keys == ("ee",) else "JOINT",
                 control_decimation=round(1 / (spec.control_hz * dt)),
                 max_physics_steps=round(cfg.task.sim_seconds / dt), **cfg.env)
with topogym.make(cfg.task.id, **make_args) as env:
    for seed in cfg.task.seeds:
        env.reset(seed=seed)
        actor = env.interaction()
        # 先检查 actor.action_spec["robot_id"] == spec.embodiment，不一致就停
        agent = VLAAgent(client, Adapter(actor.action_spec, spec), execute_steps)
        agent.reset(seed, instruction, obs["state"]["episode_id"])    # episode id 用 Env 的
        # 录像：RecordingSession(out / f"seed_{seed}", fps=30, metadata=...) 进入后 append(env.sensor_frame())，
        #       再 stop = env.add_frame_sink(rec.append)
        obs = actor.observe()
        while True:
            robot = env.tick_record()["robot"] if needs_joint_and_ee else obs["robot"]
            action = agent.act(obs["rgb"], robot)              # PolicyError → policy_error
            obs, _, terminated, truncated, info = actor.step(action)
            # ValueError：ee_abs 时 agent.skip(robot, actor.step) 逐臂保持实测位姿后重试；关节动作记 invalid_action
            # RuntimeError → env_error
            # 跟踪误差：发出的臂目标 − 下一次观测的实测值（关节 rad 或 TCP 位置 m），不含夹爪
            if terminated or truncated:
                outcome = classify(info); break                # classify 照搬 vla_eval_demo.py
        # 录像：stop()；若 Env 未故障则 append_final(env.sensor_frame())；finish(row)；以 commit=True 关闭
```

- **输出目录**：必须尚不存在，不覆盖旧结果。
- **`results.jsonl` 每行字段**：
  - 任务：`task`、`variation`、`seed`、`model`（spec.name）、`instruction_version`；
  - 结果：`outcome`、`task_success`、`failure_code`、`sim_time_s`；
  - 控制：`control_steps`、`inference_calls`、`execute_steps`、`control_decimation`、`control_hz_actual`；
  - 诊断：`tracking_error_mean`、`tracking_error_max`、`tracking_error_unit`（rad / m）、`clipped_actions`、`skipped_actions`、`reset_wall_s`、`rollout_wall_s`、`error`。
- **`outcome` 取值**：`success`、`task_failure`、`time_limit`、`unevaluated`、`unfinished`、`invalid_action`、`policy_error`、`env_error`。
- **`summary.json`**：成功率、各类结果计数、完整配置快照、`git rev-parse HEAD`。
- **`report.md`**：一行 Markdown 汇总；`python -m vla.gym.report <目录>...` 把多个输出目录汇成对比表。

## 7. 配置

配置文件可以用 `_base_` 继承（路径相对本文件，按顺序合并，映射按键合并、其余值整体替换），用 `${a.b}` 引用，`run_eval` 的命令行 `key=value` 最后生效（键名必须存在，`env.*` 除外）。端口不写在模型配置里。

```yaml
# vla/configs/models/panda_robotiq/base.yaml：同一机器人的共同部分
spec:
  embodiment: panda_robotiq
  cameras: [agentview, wrist]
  state_keys: [joint]
  action_space: joint_abs
  control_hz: 15
```

```yaml
# vla/configs/models/panda_robotiq/pi05_droid_jointpos.yaml
_base_: base.yaml
class_path: vla.models.pi05.model.Pi05      # serve.py 用 importlib 按此加载，不设注册表
checkpoint: gs://openpi-assets/checkpoints/pi05_droid_jointpos
spec:
  name: pi05_droid_jointpos
  chunk_size: 15
  execute_steps: 8
model:                                      # 子类专属参数
  train_config: pi05_droid_jointpos_polaris
```

```yaml
# vla/configs/eval/base.yaml（节选）；vla/configs/eval/<task>.yaml 只写 _base_ 和 task.id
policy:
  address: localhost:8000        # 模型服务的端口在运行时指定
task:
  id: ???
  variation: base
  seeds: [0, 1, 2]
  sim_seconds: 60
run:
  execute_steps: null            # null = 用 PolicySpec.execute_steps
  record: true
  output: null                   # null = runs/test_results/<YYYYMMDD>_vla_<模型>_<任务>
env: {}                          # 透传给 topogym.make；辅助抓持默认关闭，这里不设
```

```bash
bash vla/setup.sh pi05                                                          # 一次性

# 终端 1
conda activate vla-pi05
python -m vla.models.serve --config vla/configs/models/panda_robotiq/pi05_droid_jointpos.yaml   # --port 默认 8000

# 终端 2
conda activate topogym
python -m vla.gym.run_eval --config vla/configs/eval/buzz_wire_3d.yaml task.seeds=[0] run.record=false
```

两个命令都从仓库根运行，所以两边都能 `import vla`。指令在 `vla/gym/instructions.py`（`INSTRUCTIONS`、`VERSION`），不放 YAML。

## 8. 复用（2026-09-30 已在代码中核对）

| 已有代码 | 用法 |
|---|---|
| `topogym.make(task_id, **SimulatorConfig 字段)`，`with` 管理生命周期 | 参数：`variation_id`、`control_mode`、`observation_mode`、`control_decimation`、`max_physics_steps`、`grasp_assist`（默认关闭） |
| `env.reset(seed=)`、`env.interaction()` → `actor.step / observe / action_spec` | 评测进程是管理方，只把观测交给 agent；`actor.step` 返回公开 info |
| `actor.action_spec`：`robot_id`、`arms`、`groups[arm]`（`arm_joint_names`、`joint_limits_rad`、`gripper_field`、`gripper_limits`、`fields`） | 驱动 Adapter，不另写机器人描述 |
| 观测 `obs["rgb"][相机]`（480×848×3 uint8）、`obs["robot"][arm]` | JOINT 模式有 `joint_position_rad`、`joint_velocity_rad_s`、`finger_position_*`；EE 模式有 `tcp_position_world_m`、`tcp_orientation_wxyz`、`finger_position_*` |
| `env.tick_record()["robot"]` | 同时需要关节和 TCP 时使用（GR00T）；它会读取整个世界状态，P1 实测开销 |
| `docs/vla_doc/vla_eval_demo.py`：`GRIPPER_OPEN_CLOSED`、`CAMERAS`、`classify`、`run_episode`、`VLAPolicy.state / to_action` | 移植到 adapter / agent / run_eval，字段约定保持一致（不 import docs 下的文件） |
| `RecordingSession(output, fps=30, metadata=)` + `env.add_frame_sink` + `env.sensor_frame()`；用法参考 `topogym/recording/segment.py` 的 `SegmentMedia` | 录像；Env 每个控制步把帧推给 sink |
| 指令：5 个任务有 `instruction` 类属性（buzz_wire_3d、rope_threading、lock_picking、fiber_bundling、knot_untying）；6 个 placement 任务在 reset 后从 `obs["task"]["instruction"]` 读（orbits、hedgehog_in_cage、horseshoe_ring、cast_keyhole、slotted_post_ring、interlocked_claws） | 生成 `instructions.yaml` 的初始内容；cast_coil、blanket_flatten 没有指令，需要起草（D3） |
| 相机：aloha `cam_high`、`cam_low`、`cam_left_wrist`、`cam_right_wrist`；panda_robotiq `agentview`、`front_oblique`、`wrist` | 供 `spec.cameras` 选用 |
| OmegaConf（TopoGym 依赖中已有 `omegaconf==2.3.0`） | 读配置、命令行覆盖 |

## 9. 首批矩阵（零样本）

| 机器人 · 任务 | checkpoint | 数据频率 → `control_decimation`（实际频率） |
|---|---|---|
| Panda · `buzz_wire_3d` | π0.5 `pi05_droid_jointpos`；GR00T `GR00T-N1.7-DROID`；MolmoAct2 `MolmoAct2-DROID` | 15 Hz → 27（14.81 Hz） |
| ALOHA · `cast_coil` | π0.5 `pi05_base` + trossen 归一化统计量 | 50 Hz → 8（50 Hz） |
| ALOHA · `cast_coil` | X-VLA `X-VLA-RoboTwin2`（`ee_abs`） | 16.7 Hz → 24（16.67 Hz）；原写 30 Hz → 13，见第 13 节 |

`control_decimation = round(1 / (control_hz × 0.0025))`。各模型的输入输出细节见 `DESIGN.md` 4.5；P3 按官方代码核对后的最终数值以 `vla/configs/models/<robot>/*.yaml` 和 `vla/README.md` 第 3 节为准（GR00T 执行 8 步、只用当前帧；X-VLA 执行 30 步）。

## 10. TODO

**P0 骨架（无 GPU）** — 验收：在 TopoGym 环境里 `pytest vla/tests -q` 全部通过
- [x] 包结构、`vla/.gitignore`。证据：commit 43c2422
- [x] `protocol.py` + 测试（`vla/tests/test_protocol.py`，5 项）。证据：commit 43c2422
  - 嵌套 dict 中的 uint8、float32、float64 数组编解码往返逐位相等；
  - 协议版本不一致时报错。
- [x] `gym/adapter.py` + 测试（`vla/tests/test_adapter.py`，20 项）。证据：commit fe5f00e、9c10d9f
  - 用 `topogym.make("cast_coil")` 和 `topogym.make("buzz_wire_3d")` 的真实 `action_spec`；
  - 检查 state 排列、开度换算、截断，以及 rot6d ↔ 四元数往返；
  - 检查动作字典的键与 `action_spec` 的 `fields` 一致。
- [x] `gym/agent.py` + 测试（`vla/tests/test_agent.py`）。证据：commit bb34e51
  - H=15、k=8 时，20 次 `act` 只推理 3 次；
  - `reset` 清空队列；
  - 块的形状不对或含 NaN 时抛 `PolicyError`。
- [x] `models/base.py`、`models/dummy.py`（HoldVLA）、`gym/client.py` 中的 `LocalClient`。证据：`vla/tests/test_models.py`，commit 61cea7d
- [x] `tests/test_boundaries.py`：用 AST 检查（放入临时违规文件时两项均失败）。证据：commit 7bd29f0
  - `protocol.py` 和 `models/**` 不 import `topogym`；
  - `gym/**` 不 import `torch`、`jax`、`transformers`、`openpi`、`gr00t`。
- [x] `setup.sh` 公共部分、`README.md` 初版。证据：commit 9869142；完整版 e9b6ca6

**P1 评测循环（GPU，TopoGym 环境）**
- [x] `configs/instructions.yaml` v1：从代码取 11 个任务的现有指令，起草 cast_coil、blanket_flatten 两条，交用户确认（D3）。证据：`vla/tests/test_configs.py` 核对 13 个任务和 5 条类属性；6 条 placement 指令由各任务 base 变体的 `declare` 生成；两条草稿待确认
- [x] `gym/run_eval.py`：按第 6 节实现。证据：commit 0119d59、010b66b；`vla/tests/test_run_eval.py`
- [x] 冒烟：HoldVLA（LocalClient）在 `cast_coil`、`buzz_wire_3d` 上各跑 seed 0，`sim_seconds: 2`。证据：`runs/test_results/20260930_vla_smoke_hold_{cast_coil,buzz_wire}`（`time_limit`、80 步、8 次推理、跟踪误差 < 1e-7、每路相机一个 61 帧 MP4）；对照 `runs/test_results/20260930_vla_smoke_demo_{cast_coil,buzz_wire}`（`time_limit`、80 步）
  - 预期：`outcome=time_limit`，结果字段齐全，每路相机一个 MP4，跟踪误差已记录。
  - 同一 decimation 和步数下，与 `vla_eval_demo.py` 的 `outcome`、`control_steps` 一致。
- [x] 实测并写入第 13 节。证据：`runs/test_results/20260930_vla_p1_timing`
  - decimation 为 8 / 13 / 27 时每个控制步的墙钟时间；
  - 显存峰值；
  - `tick_record()` 的开销。

**P2 服务**
- [x] `models/serve.py`：按 `class_path` 加载 → `load()` → 监听；一次只接一个连接；`infer` 出错时回 `error`，服务不退出。证据：commit c35e51c
- [x] `gym/client.py` 中的 `RemoteClient`：版本校验、超时、`PolicyError`。证据：commit c35e51c
- [x] 测试（无 GPU）：在子进程里用 serve 起 HoldVLA，`RemoteClient` 拿到的动作块与 `LocalClient` 逐位相等。证据：`vla/tests/test_serve.py`
- [x] 冒烟（GPU）：P1 的冒烟改用 `RemoteClient`，结果不变。证据：`runs/test_results/20260930_vla_smoke_remote_hold_{cast_coil,buzz_wire}`（outcome、步数、推理次数相同，跟踪误差前 15 位有效数字相同）

**P3 模型**（按下列顺序，每个模型一项）
- 每项的步骤：
  1. 先读官方推理示例，把入口函数、输入键、输出含义和单位写进 `model.py` 的 docstring；
  2. 加 `setup.sh` 分支和 `configs/models/<robot>/<checkpoint>.yaml`；
  3. 跑 1 个 seed 的冒烟（`sim_seconds: 10`）；
  4. 检查输出形状和数值范围，记录推理延迟和显存。
- [x] π0.5 · Panda `pi05_droid_jointpos`。证据：`runs/test_results/20260930_vla_smoke_pi05_droid_buzz_wire`（`time_limit`、149 步、19 次推理、跟踪误差均值 0.043 rad，服务显存 12.4 GB）
- [x] π0.5 · ALOHA `pi05_base` + trossen 统计量（增量由 openpi 自身的 `AbsoluteActions` 加回 state）。证据：`runs/test_results/20260930_vla_smoke_pi05_base_cast_coil`（`time_limit`、500 步、20 次推理、跟踪误差均值 0.46 rad、475 行截断）
- [ ] GR00T N1.7 · Panda `GR00T-N1.7-DROID`：代码、配置、环境、checkpoint 已就绪；DROID checkpoint 只用当前帧（无 1 s 历史帧），`state_keys: [joint]`，eef_9d 由 Franka 正运动学计算。**阻塞**：backbone `nvidia/Cosmos-Reason2-2B` 为 gated 仓库，当前 HF 账号 403，未冒烟
- [x] MolmoAct2 · Panda `MolmoAct2-DROID`（3 路相机：agentview、front_oblique、wrist）。证据：`runs/test_results/20260930_vla_smoke_molmoact2_buzz_wire`（`time_limit`、149 步、10 次推理、跟踪误差均值 0.018 rad）
- [x] X-VLA · ALOHA `X-VLA-RoboTwin2`（`ee_abs`；坐标系换算见第 11 节第 4 条）。证据：`runs/test_results/20260930_vla_smoke_xvla_cast_coil`（`time_limit`、167 步、6 次推理、TCP 跟踪误差均值 9.5 mm、无 IK 失败；该次运行时基座高度仍为修正前的 0.9396）；单次推理 0.15 s、显存峰值 3.46 GiB

**P4 约定核对**（每条写明结论和证据；影响零样本结果）
- [x] 第 11 节第 1–5 条：结论写在第 11 节各条后。证据：`runs/test_results/20260930_vla_p4_checks`

**P5 首批评测**
- [ ] 按 P1 实测的吞吐算预算，与用户确认 seed 数和 `sim_seconds`：用户未确认；先按 3 seed × 30 s 跑首批（第 13 节）
- [ ] 跑第 9 节矩阵，出对比表（附 `execute_steps`、实际控制频率、指令版本）：首批已跑除 GR00T 外的 4 行，对比表见 `runs/test_results/20260930_vla_batch1_logs/comparison.md` 与第 13 节；GR00T 与完整预算待定

**之后（等用户决定）**
- 过程指标。
- 微调：设计见 `DESIGN.md` 3.8，接口不变。
- 多个仿真进程共用一个模型服务：只需修改 `serve.py`。

## 11. 风险与待核对

1. **ALOHA 关节约定**：TopoGym ALOHA 的关节零位、正方向与 openpi 的 ALOHA 约定是否一致（openpi 用 `adapt_to_pi` 做转换）。
   - 结论：一致。TopoGym ALOHA 取自 mujoco_menagerie `aloha.xml`（rev 8161bba），关节轴（waist z；shoulder、elbow、wrist_angle y；两个 roll x）、连杆偏移和限位与 Interbotix vx300s 相同，home 等于 ACT 的 START_ARM_POSE `[0, -0.96, 1.16, 0, -0.3, 0]`，属于标准 ALOHA 约定，`adapt_to_pi=True` 与之匹配。
   - 另：home 夹爪开度约 0.18（接近闭合），openpi 的变换会把它编码成训练中没有的状态 token（-1）；按官方变换保留，未截断。
2. **夹爪**：各数据集夹爪值的范围和方向（DROID、X-VLA 是 1 = 闭合）。
   - 结论：π0.5 DROID、GR00T、MolmoAct2 的输入输出都是闭合度 [0, 1]（1 = 闭合），子类用 `1 − 开度`；π0.5 DROID 与 GR00T 按官方客户端在 0.5 处二值化，MolmoAct2 截到 [0, 1] 后保持连续。π0.5 ALOHA 用归一化手指位置（1 = 全开），与标准开度同义，输出实际范围约 0.55–1.03，由适配器截到 [0, 1]。X-VLA 输出 g（1 = 闭合），按官方客户端 g > 0.7 为闭合。
   - TopoGym Robotiq 的开度按驱动关节角换算（0 rad 全开、0.8 rad 全闭），DROID 按开口宽度换算，两者只近似线性。
3. **相机**：TopoGym 的 agentview / wrist 与 DROID 真机相机的位置和视角差异。零样本对此敏感，只记录，不调整。
   - 记录：TopoGym 各相机 848×480（16:9）。DROID 训练图像 320×180（16:9），GR00T、MolmoAct2 的官方客户端先缩放到该尺寸，子类照做；π0.5 由自身流程加黑边缩到 224。RoboTwin 训练图像 320×240（4:3），X-VLA 处理器直接压缩成 224×224。相机位置与视角未调整。
4. **X-VLA 坐标系**：标准 `ee` 用 TopoGym 世界系，X-VLA 训练数据用什么坐标系要核对。若需要各臂基座在世界系的位姿，`action_spec` 里没有，需找来源；若需要改 `vla/` 以外的代码，先问用户。
   - 结论：X-VLA 用 RoboTwin 世界系中 URDF link6 原点的位姿（RoboTwin TCP 在其 x 方向 0.12 m 处），rot6d 为 X-VLA 约定且训练和官方客户端都把 wxyz 四元数按 xyzw 读取。TopoGym 两臂相对放置，RoboTwin 两臂并排，所以每臂按自身基座映射（`vla/models/xvla/frames.py`；第二轮起高度改为相对桌面，见第 13 节）。TopoGym 基座位姿在仿真中实测：左 (−0.6047, −0.019, 0.9196)、偏航 0°，右 (0.3333, −0.019, 0.9196)、偏航 180°，写入 `xvla_robotwin2.yaml`；手爪坐标轴（x 前向、y 基座左、z 上）与 link6 一致。未改 `vla/` 以外的代码。
5. **跟踪特性**：P1 / P3 测到的"目标 − 实测"与真机数据集中的量级对比。ALOHA 用源 MJCF 的位置执行器增益；Panda 的增益与 DROID 真机控制器是否一致尚未核对。
   - 实测（每步各臂 L2 范数的最大值，均值）：HoldVLA 约 1e-8；π0.5 DROID 0.043 rad；MolmoAct2 0.018 rad；π0.5 ALOHA 0.46 rad；X-VLA 9.5 mm。DROID 数据中 `action.joint_position[t]` 与 `state[t+1]` 的逐关节平均绝对差为 0.012–0.043 rad（GR00T 调研，DROID 样例）。两者口径不同，只能比较量级。Panda 增益与 DROID 控制器的对应关系未核对。
6. **仿真速度**：已知控制步墙钟为秒级。episode 时长和 seed 数由 P1 实测决定。
   - 实测见第 13 节：cast_coil 每物理 tick 约 0.042 s，buzz_wire_3d 约 0.077 s（独占 GPU）。

## 12. 决定

| # | 问题 | 结论 |
|---|---|---|
| D1 | 辅助抓持 | 关闭（`SimulatorConfig` 默认即关闭），整批统一 |
| D2 | 数据频率不能整除 400 Hz 时怎么办 | `control_decimation` 取整（第 9 节），不做时间重采样；结果记录实际频率 |
| D3 | cast_coil、blanket_flatten 的英文指令 | **待确认**：P1 起草，交用户确认 |
| D4 | `execute_steps` | 用各模型官方示例值，写进模型配置；评测配置可以覆盖 |
| D5 | 设计文档放哪 | `vla/docs/` |
| D6 | 传输 | 标准库 TCP，一对一；TopoGym 环境不装新包 |
| D7 | 图像预处理放哪 | 发原始分辨率，缩放等预处理由模型子类用官方代码做；本机传输约 3.7 MB / 次 |
| D8 | PolicySpec 的来源 | 模型配置的 `spec` 段，子类不硬编码 |

## 13. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 创建；阶段目标为只评测 |
| 2026-09-29 | 精简为高层计划；只改 `vla/`；一个通用适配器；`run_eval` 配置驱动；`vla/README.md` 与 `setup.sh` |
| 2026-09-29 | 去掉 SegmentRunner；一对一连接；安装合并为 `vla/setup.sh`；记录跟踪误差 |
| 2026-09-29 | 传输改为标准库 TCP；文档移入 `vla/docs/`；D1、D2、D4、D5 定稿 |
| 2026-09-30 | 定稿：所有复用接口已在代码中核对；补充开始前检查（TopoGym 环境本机缺失）；接口签名、线协议格式、评测循环、结果字段、配置格式写全；指令来源更正为 5 个类属性 + 6 个 placement 任务；PolicySpec 改为 `state_keys`、去掉 `image_size`（D7、D8） |
| 2026-09-30 | 实施 P0–P4（commit 43c2422 至 e9b6ca6，`pytest vla/tests -q` 76 项通过）。GR00T 因 gated backbone 未冒烟 |
| 2026-09-30 | P1 实测（独占 GPU，保持动作，20 步均值）：cast_coil decimation 8 / 13 / 24 每控制步 0.35 / 0.57 / 1.00 s；buzz_wire_3d decimation 27 为 2.07 s、10 为 0.76 s；reset 17 s（cast_coil）、40 s（buzz_wire_3d）；`tick_record()` 0.03–0.08 s；仿真显存 cast_coil 2.0 GB、buzz_wire_3d 4.5 GB。模型：π0.5 服务 12.4 GB（`XLA_PYTHON_CLIENT_MEM_FRACTION=0.5`），MolmoAct2 约 9.4 GB，X-VLA 3.5 GB、单次推理 0.15 s |
| 2026-09-30 | X-VLA 频率改为 16.7 Hz（decimation 24）、执行 30 步：RoboTwin 每 15 个 1/250 s 仿真步存一帧，官方客户端执行整个动作块；"30 Hz" 只是标签 |
| 2026-09-30 | GR00T：DROID checkpoint 只用当前帧（`delta_indices=[0]`），去掉 1 s 历史帧；`state_keys` 改为 `[joint]`，eef_9d 由 Franka 正运动学计算（与 TopoGym 手爪位姿的相对变换在 4 个构型下恒定）；执行步数取 RoboLab 仿真验证值 8 |
| 2026-09-30 | 评测配置按任务各一份（`buzz_wire_3d.yaml`、`cast_coil.yaml`），`run.output: null` 时自动取 `runs/test_results/<YYYYMMDD>_vla_<模型>_<任务>`，各模型配置用不同端口（8000–8004），换模型只改 `policy.address` |
| 2026-09-30 | P5 首批：用户未确认预算，先按每模型 3 seed × 30 s 顺序运行 π0.5 DROID、MolmoAct2（buzz_wire_3d）与 X-VLA、π0.5 ALOHA（cast_coil），结果见 `runs/test_results/20260930_vla_batch1_*` |
| 2026-09-30 | 独立审查（969eee7..e9b6ca6）：无 Critical；修复 4 项（`env_error` 记录故障原因；录像失败不再中止后续 seed；命令行覆盖项拼错时报错；服务端回复编码失败时回 `error` 而不退出），commit c8f06ce，`pytest vla/tests -q` 80 项通过；其余 Minor 记入实施总结 |
| 2026-09-30 | P5 首批（每模型 3 seed × 30 s，commit 061a9ef 起）：π0.5 DROID 与 MolmoAct2（buzz_wire_3d）均 0/3（`time_limit` 1、`unevaluated` 2，seed 1、2 在超时时判据不可用）；X-VLA（cast_coil）0/3（`time_limit` 2、`invalid_action` 1：IK 残差 0.26 mm 超出容差）；π0.5 ALOHA（cast_coil）0/3（`time_limit` 3）。跟踪误差均值 0.049 rad / 0.015 rad / 9.8 mm / 0.59 rad。π0.5 ALOHA 每个 episode 平均 1475/1500 行截断，150 步诊断中全部来自关节限位（shoulder、elbow、wrist_angle），开度未越界。cast_coil 使用 D3 草稿指令，结果暂定 |
| 2026-09-30 | 推理延迟（首次调用含 JIT / 之后每次）：π0.5 DROID 10.2 s / 0.078 s，π0.5 ALOHA 10.7 s / 0.080 s，进程显存 11.3 GB；MolmoAct2 0.45 s / 0.31 s，12.5 GB；X-VLA 0.78 s / 0.15 s，3.5 GiB。证据：`runs/test_results/20260930_vla_p3_latency` |
| 2026-09-30 | 按用户第二轮意见：环境改为 conda（`topogym`、`vla-<model>`，设 `PYTHONNOUSERSITE=1`）；端口改为运行时参数；配置按机器人分目录，用 `_base_` 继承；指令移到 `gym/instructions.py`；episode id 用 Env 的；RemoteClient 不设超时；`run_eval` 自动补渲染环境变量；新增 `report.md` 与 `python -m vla.gym.report`；`BaseVLA.camera_images` 统一相机顺序和缩放 |
| 2026-09-30 | 四个模型的调用方式逐项对照官方代码复查（`runs/test_results/20260930_vla_round2_audit/audit.md`）：调用路径一致。修正两处与训练机器人的对应关系：DROID 模型的关节 7 按 45° 安装差换算（`models/droid.py`）；X-VLA 高度改为相对桌面。其余差异（π0.5 ALOHA 夹爪标定与起始姿态、GR00T eef_9d 欧拉角约定、X-VLA 的 IK 失败处理与 proprio 来源）待用户决定 |
| 2026-09-30 | 按用户第三轮决定：π0.5 ALOHA 夹爪改为按 openpi 的连杆模型换算，模型全闭/全开对应 TopoGym 全闭/全开（`models/pi05/gripper.py`）；X-VLA 按 RoboTwin 官方评测执行，每个目标保持到 TCP 进入 5 mm 以内（最多多 10 步；实测 TopoGym ALOHA 稳态误差 1.6–4.5 mm），IK 达不到容差的目标跳过并计数；`PolicySpec` 增加 `reach_tolerance_m`，协议版本升为 2；删除 `.venv-gs121-nyx` |
| 2026-09-30 | 第三轮独立审查：跳过改为逐臂（与 RoboTwin 相同，另一条臂照常执行）；末端相关测试改用 ALOHA 双臂并按内容拒绝，审查列出的 4 种错误都能被测出；每个目标只换算一次动作（截断按行计）；`PolicySpec` 拒绝缺少 ee 状态的 `ee_abs` / `reach_tolerance_m`；夹爪超过连杆最大角时保持全开；报告中跳过数保留两位有效数字 |
