# VLA 接入实施计划（IMPL_PLAN）

| 项 | 值 |
|---|---|
| 状态 | P0 未开始 |
| 当前阶段目标 | **只评测（zero-shot）**：用各模型官方发布的 checkpoint，不微调 |
| 工作分支 | `dev/pingyue`（或从它拉出的 feature 分支）；**不要提交到 `main`** |
| 设计文档 | [`README.md`](README.md)（完整设计与选型）、[`index.html`](index.html)（可视化版） |
| 最后更新 | 2026-09-29 |

## 这个文件怎么用

- 本文件是 VLA 接入工作的**唯一任务清单**。开始任何 VLA 相关实现前先读完第 0–3 节。
- 完成一项就把 `- [ ]` 改成 `- [x]`，并在该项下补一行 `证据：<路径或命令>`（测试输出、`runs/test_results/...` 目录、commit hash）。没有证据的项不能勾选。
- 发现计划与代码不符、或需要改计划时：在第 9 节"变更记录"追加一条（日期、改了什么、为什么），不要删除旧内容。
- 标"待确认"的决策需要用户拍板，不要自行决定；在第 6 节记录问题并停下来问。

---

## 0. 必须遵守的规则

1. **分支**：只在 `dev/pingyue` 或其子分支上工作；不 push、不开 PR，除非用户明确要求。
2. **不改仿真器**：不修改 `topogym/simulator/`、`topogym/tasks/`、`tasks/`、`harbor_agents/`、`ci_checks/`（见 [`docs/vla_doc/README.md`](../vla_doc/README.md) §9 与根目录 `AGENTS.md`）。确实需要改仿真器时，先列出具体文件/函数和原因，问用户。
3. **代码位置**：所有新代码放在仓库根 `vla/`。不放进 `topogym/` 包（`tests/architecture/test_module_boundaries.py` 禁止 `topogym.policies` 等退役模块）；不 import `legacy/`。
4. **依赖隔离**：
   - Gym 环境（Genesis 1.2.1 + Nyx，numpy 2.x）只安装 `vla/protocol` 与 `vla/gym` 的依赖：`numpy`、`msgpack`、`websockets`、`Pillow`。
   - **不要**把 `openpi-client` 装进 Gym 环境：它要求 `numpy<2`，与 Genesis 环境的 numpy 2.3.5 冲突。msgpack 的 numpy 编解码在 `vla/protocol/wire.py` 自己实现。
   - 每个模型一个独立环境（uv venv 或 Docker），只在其中 import 该模型的官方库。
5. **进程约束**：一个进程只能有一个活跃 `Env`（Genesis 全局状态）。多任务评测要么逐个 `with topogym.make(...)`，要么开多个进程。
6. **GPU 与资源**：
   - 本机只有 1 张 RTX 4090（24 GB），而且可能有其他任务在用。启动前用 `nvidia-smi` 看剩余显存；仿真（刚体 2–3 GB，FEM 最高约 10 GB）加上模型推理显存超过剩余量时，不要启动，改为给用户可执行的 CLI。
   - 按 `AGENTS.md`：CPU 或内存达到 90% 时，停止本轮启动的进程，不终止无关进程。
7. **证据**：真实运行产物放 `runs/test_results/<YYYYMMDD>_vla_<name>/`（含 `results.jsonl`、`summary.json`、视频、所用命令与源码 hash）。不能用静态检查或单元测试推断"模型在任务上可运行 / 成功"。
8. **代码风格**：遵守根目录 `CLAUDE.md`：先读再写、最小实现、不加推测性抽象、改 bug 先写复现测试。协议只有 3 个数据类，不引入插件框架。

---

## 1. 目标与范围

**本阶段（只评测）**：
- 在 TopoGym 的 13 个任务中选首批任务，用 3–4 个 VLA 的官方 checkpoint 做零样本评测。
- 交付评测结果（成功率、结果分布、每 episode 视频），同时验证整条接入链路可用。

**不在本阶段**：微调、数据导出（放在 P7，等用户决定）；Harbor 相关的任何改动。

**成功标准**：
1. 同一条 `run_eval` 命令只改 `--policy` 参数，就能切换模型。
2. 每个 episode 有 `results.jsonl` 一行、每路相机一个 MP4；失败原因可区分（`success / task_failure / time_limit / unevaluated / invalid_action / policy_error / env_error`）。
3. 首批评测矩阵跑完，出具对比表。

**预期**：拓扑类任务对现有模型是全新任务，零样本成功率大概率接近 0。因此 P6 的过程指标用于区分模型；0 分本身不能说明模型强弱。

---

## 2. 架构摘要

```text
Gym 进程（Genesis 环境）                                  模型进程（每个模型独立环境）
┌──────────────────────────────────────────────┐         ┌──────────────────────────────┐
│ run_eval.py（管理方：make / reset / 记结果）     │         │ serve.py                      │
│   └ Env ── interaction() ──▶ VLAAgent.act(obs) │  ws +   │   └ BaseVLA 子类.infer(obs)    │
│        EmbodimentAdapter（aloha / panda）      │ msgpack │     官方推理对象（openpi /      │
│        动作块队列                               │◀───────▶│     Isaac-GR00T / X-VLA / …） │
│        PolicyClient（Websocket / Local）       │         │                              │
│   录像：RecordingSession + env.add_frame_sink  │         └──────────────────────────────┘
└──────────────────────────────────────────────┘
共享：vla/protocol（types.py + wire.py，只依赖 numpy + msgpack）
```

- 机器人相关的转换只在 `EmbodimentAdapter`（Gym 侧，2 个：`aloha`、`panda_robotiq`）。
- 模型相关的转换只在 `BaseVLA` 子类（模型侧，每个模型 1 个）。
- VLA 只在评测循环的 `agent.act(obs)` 处介入；其余都是 TopoGym 已有接口。

目录（目标状态）：

```text
vla/
├── protocol/        types.py（PolicySpec / Observation / ActionChunk）、wire.py（msgpack 编解码）
├── gym/             embodiment.py、agent.py、client.py、run_eval.py、recorder.py、instructions.yaml
├── models/          base.py、serve.py、registry.py；每个模型一个子目录（含依赖文件与 README）
│   ├── pi05/  groot/  molmoact2/  xvla/  dummy/
└── tests/           单元测试（不需要 GPU）
```

---

## 3. 接口契约（规范性，实现必须一致）

### 3.1 数据类（`vla/protocol/types.py`）

```python
PROTOCOL_VERSION = 1

@dataclass(frozen=True)
class PolicySpec:
    protocol_version: int
    name: str                      # 例："pi05_droid_jointpos"
    embodiment: str                # "aloha" | "panda_robotiq"
    cameras: tuple[str, ...]       # TopoGym 相机名，顺序即模型槽位顺序
    image_size: tuple[int, int]    # (H, W)，Gym 侧缩放
    action_space: str              # "joint_abs" | "ee_abs"
    control_hz: float              # 训练数据的控制频率
    chunk_size: int                # 模型每次输出的步数 H
    execute_steps: int             # 默认每块执行的步数，可被 run_eval 覆盖

@dataclass(frozen=True)
class Observation:
    images: dict[str, np.ndarray]  # 相机名 → (H, W, 3) uint8
    state: np.ndarray              # (D,) float32，排列见 3.2
    instruction: str
    episode_id: str
    step: int                      # 控制步序号

@dataclass(frozen=True)
class ActionChunk:
    actions: np.ndarray            # (H, D) float32，与 state 同一排列，绝对目标
```

### 3.2 标准向量排列

| embodiment | action_space | D | 排列 |
|---|---|---|---|
| `aloha` | `joint_abs` | 14 | `[左臂 6 关节, 左开度, 右臂 6 关节, 右开度]`，关节顺序 = `action_spec["groups"][arm]["arm_joint_names"]` |
| `panda_robotiq` | `joint_abs` | 8 | `[7 关节, 开度]` |
| `aloha` | `ee_abs` | 20 | 每臂 `[xyz 3, rot6d 6, 开度 1]` × 2（左在前） |
| `panda_robotiq` | `ee_abs` | 10 | `[xyz 3, rot6d 6, 开度 1]` |

约定：
- 关节角单位 rad；`xyz` 为 TopoGym 世界系下 TCP 位置（米）；`rot6d` = 旋转矩阵前两列按列展开（与 X-VLA `R[..., :, :2].reshape(6)` 一致）。
- **开度** ∈ [0, 1]，**1 = 全开**。换算：
  - ALOHA：`开度 = (finger₀ − 0.002) / 0.035`；反向 `gripper_position_m = 0.002 + 0.035 × 开度`（`finger_position_m[0]` 是被驱动的那根手指）。
  - Panda：`开度 = 1 − finger₀ / 0.8`；反向 `gripper_position_rad = 0.8 × (1 − 开度)`。
  - 数值以 `action_spec["groups"][arm]["gripper_limits"]` 为准，不要硬编码；上面只是说明。
- `ActionChunk` 一律是**绝对目标**。模型内部的相对量（关节增量、相对末端位姿）由子类换算后返回。
- 适配器在转换成动作字典前按 `joint_limits_rad` 与夹爪范围截断；TopoGym 越界会抛 `ValueError`，不会自动截断。

### 3.3 线协议（`vla/protocol/wire.py`）

- 传输：WebSocket，一条连接对应一个评测客户端。
- 编码：msgpack；`np.ndarray` 编成 ext 类型，载荷为 `{dtype, shape, bytes}`（C 连续）。不依赖 `openpi-client`。
- 消息（都是 dict，有 `type` 字段）：

| 方向 | type | 其余字段 |
|---|---|---|
| 服务端 → 客户端（连接后第一条） | `spec` | `spec`：PolicySpec 字段 |
| 客户端 → 服务端 | `reset` | `seed: int`、`episode_id: str` |
| 服务端 → 客户端 | `ok` | — |
| 客户端 → 服务端 | `infer` | `obs`：Observation 字段 |
| 服务端 → 客户端 | `chunk` | `actions: ndarray (H, D) float32`、`infer_ms: float` |
| 服务端 → 客户端 | `error` | `message: str`（含 traceback 摘要）；连接保持 |

- 客户端收到 `spec` 后校验 `protocol_version`，不一致立即报错。
- `infer` 超时（默认 60 s，可配置）或收到 `error` → 客户端抛 `PolicyError`；`run_eval` 把该 episode 记为 `policy_error`，不计为任务失败。
- 服务端提供 `GET /healthz`（或等价就绪检查），`run_eval` 启动时等待就绪。

### 3.4 `run_eval` 如何按 PolicySpec 设置 `topogym.make`

| PolicySpec | make 参数 | 规则 |
|---|---|---|
| `embodiment` | `robot_id` | 必须等于任务默认机器人，否则报错退出 |
| `action_space` | `control_mode` | `joint_abs → JOINT_ABS`，`ee_abs → EE_ABS` |
| `control_hz` | `control_decimation` | `400 / control_hz`（物理 tick 2.5 ms）。整数直接用；非整数（如 15 Hz → 26.67）取最近整数并在结果里记录实际频率（15 Hz → 27，即 14.81 Hz），或由子类按时间重采样，二选一见第 6 节 |
| `cameras` | — | 必须是 `actor.observation_spec["rgb"]` 的子集 |
| — | `max_physics_steps` | 由 `--sim-seconds` 换算，写进结果 |
| — | `grasp_assist` | 待确认（第 6 节），整批评测统一 |

### 3.5 同时需要关节角与 TCP 位姿的问题

- TopoGym 的 `observation_mode` 二选一：`JOINT` 给关节角 + 角速度，`EE` 给 TCP 位姿，**不同时给**。
- 需要两者的模型：GR00T-N1.7-DROID（state = 末端 9 维 + 夹爪 + 7 关节）；X-VLA（末端）配合关节截断检查。
- 方案（不改仿真器）：`run_eval` 是管理方，可调用 `env.tick_record()["robot"]`（owner-only 公开方法，内部是 `robot.observe()`，包含 `joint_position_rad`、`tcp_position_world_m`、`tcp_orientation_wxyz`），在调用 `agent.act` 前把完整本体感知一起传给适配器。
- **先实测** `tick_record()` 的开销（它还会读取整个 world state）。如果开销明显（> 单步墙钟的 5%），在第 6 节记录，问用户是否请 simulator 维护方加一个只读本体感知接口。

### 3.6 Gym 侧类（`vla/gym/`）

```python
class EmbodimentAdapter:                      # embodiment.py，纯 numpy，无模型依赖
    def __init__(self, action_spec: dict, spec: PolicySpec): ...
    def observation(self, obs: dict, proprio: dict, instruction: str, step: int) -> Observation: ...
    def action(self, row: np.ndarray) -> dict: ...      # (D,) → TopoGym 动作字典（已截断）

class VLAAgent:                               # agent.py；实现 TopoGym 已有策略协议
    def initialize(self, context: dict) -> None: ...    # 建适配器、清队列、client.reset(seed)
    def act(self, obs: dict) -> dict: ...               # 队列空时 client.infer；否则出队

class PolicyClient(Protocol):                 # client.py
    spec: PolicySpec
    def reset(self, seed: int, episode_id: str) -> None: ...
    def infer(self, obs: Observation) -> ActionChunk: ...
# 实现：WebsocketClient(url)；LocalClient(vla: BaseVLA)（同进程，单测与占位策略用）
```

- `VLAAgent` 要能原样交给 `SegmentRunner.run_policy`（它调用 `initialize(context)` 和 `act(obs)`）。
- 现有参考实现：[`docs/vla_doc/vla_eval_demo.py`](../vla_doc/vla_eval_demo.py) 的 `VLAPolicy`、`classify`、`run_episode`。拆分它，字段约定保持一致。

### 3.7 模型侧类（`vla/models/`）

```python
class BaseVLA(ABC):                           # base.py；不 import topogym / genesis
    spec: PolicySpec
    @abstractmethod
    def load(self, checkpoint: str, device: str) -> None: ...
    @abstractmethod
    def infer(self, obs: Observation) -> ActionChunk: ...
    def reset(self, seed: int) -> None: ...   # 清内部状态、设随机种子（flow matching 采样噪声）
```

- `registry.py`：`{"pi05": "vla.models.pi05.model:Pi05VLA", ...}`，字符串路径，import 注册表不加载任何模型库。
- `serve.py`：`python -m vla.models.serve --model pi05 --checkpoint <ckpt> --config <name> --port 8000`。
- 每个子类只做三件事：标准 `Observation` → 官方输入格式；调用官方推理对象；官方输出 → 标准 `ActionChunk`（切片、反归一化、相对 → 绝对、夹爪换算）。**不连官方自带的服务**（各家协议不同），直接 import 官方推理对象。

---

## 4. 首批评测矩阵（零样本）

TopoGym 的 Panda + Robotiq 2F-85 与 DROID 数据集硬件相同，Panda 任务的零样本评测最有意义；ALOHA 任务没有同型号臂的任务级 checkpoint，预期更低。

| 机器人 | 模型 / checkpoint | action_space | 相机映射 | 频率 / H | 备注 |
|---|---|---|---|---|---|
| Panda | π0.5 `pi05_droid_jointpos` | joint_abs（8） | agentview → base，wrist → left_wrist | 15 Hz / 15 | openpi 权重桶里有；仓库示例未直接给配置，参考 `pi05_droid_jointpos_polaris`（待核实） |
| Panda | GR00T `nvidia/GR00T-N1.7-DROID` | joint_abs（执行其 `joint_position` 输出） | exterior ← agentview，wrist ← wrist；每路 2 帧（当前 + 15 步前） | 15 Hz / 40，执行 15 | 需要末端 9 维 + 关节，见 3.5 |
| Panda | MolmoAct2 `allenai/MolmoAct2-DROID` | joint_abs（8） | [agentview, front_oblique, wrist] | 15 Hz / 15 | 全开源 |
| ALOHA | π0.5 `pi05_base` + `trossen` 统计量（openpi `pi05_aloha` 推理配置） | joint_abs（14） | cam_high → base，两腕 → 两腕槽 | 50 Hz / 50 | 与 TopoGym 同型号臂（ViperX）；需确认 `adapt_to_pi` |
| ALOHA | X-VLA `2toINF/X-VLA-RoboTwin2`（domain 6） | ee_abs（20） | image0 = cam_high，image1/2 = 两腕 | 30 Hz / 30 | 末端空间；已知 issue #91（0% 回放）、#93（四元数顺序），接入前先复现官方 RoboTwin 客户端的约定 |

首批任务：Panda — `buzz_wire_3d`；ALOHA — `cast_coil`（均为刚体、有参考解、显存小）。每格先 1 个 seed 冒烟，再扩到 N 个 seed（N 由 P1 实测吞吐决定）。

---

## 5. 任务清单

### P0 协议与适配（无 GPU）

- [ ] `vla/protocol/types.py`：三个数据类 + `PROTOCOL_VERSION`；构造时校验形状与 dtype
- [ ] `vla/protocol/wire.py`：msgpack 编解码（ndarray ext），不依赖 openpi-client
- [ ] `vla/gym/embodiment.py`：`aloha`、`panda_robotiq` 两个适配器（`joint_abs`；`ee_abs` 留接口，P3 用到时实现）
- [ ] `vla/gym/agent.py`：`VLAAgent`（队列、`execute_steps`、`initialize` / `act`）
- [ ] `vla/gym/client.py`：`PolicyClient` 协议、`LocalClient`
- [ ] `vla/models/base.py`、`vla/models/dummy/`：`HoldVLA`（输出当前 state 重复 H 次）、`ReplayVLA`（按给定轨迹回放）
- [ ] 单元测试 `vla/tests/`：
  - [ ] wire 往返：各 dtype / 形状的数组编码后解码逐位相等
  - [ ] 适配器：构造的假 obs → state 排列、开度换算正确；动作字典字段名、截断、夹爪反换算正确（ALOHA 与 Panda 各一组）
  - [ ] 开度往返：原生值 → 开度 → 原生值误差 < 1e-9
  - [ ] VLAAgent：H=50、execute=10 时 25 次 `act` 只调用 3 次 `infer`
- 验收：`pytest vla/tests` 全部通过，且不 import genesis。证据：测试输出

### P1 评测循环与录像（需要 GPU）

- [ ] `vla/gym/instructions.yaml`：13 个任务的英文指令（5 个取自任务类 `instruction` 属性，8 个新写，**新写的交用户确认**），带版本号
- [ ] `vla/gym/run_eval.py`：参数 `--task --variation --seeds --policy --sim-seconds --execute-steps --record --output`；按 3.4 设置 make；逐 seed 写 `results.jsonl`，最后写 `summary.json`
- [ ] 结果分类沿用 `vla_eval_demo.py` 的 `classify`，并加上 `invalid_action`、`policy_error`、`env_error`
- [ ] 每行结果记录：task、variation、seed、model、checkpoint、instruction 版本、control_hz 实际值、execute_steps、sim 秒数、墙钟、git commit
- [ ] `vla/gym/recorder.py`：`RecordingSession` + `env.add_frame_sink`，每 episode 每相机一个 MP4
- [ ] 冒烟：`HoldVLA` 经 `LocalClient` 跑 `cast_coil`（ALOHA）与 `buzz_wire_3d`（Panda）各 1 seed、40 控制步，带录像
- [ ] 对照：同配置下结果与 `docs/vla_doc/vla_eval_demo.py` 一致（都是 `time_limit`）
- [ ] 实测：每控制步墙钟、reset 墙钟、显存峰值、`tick_record()` 开销（见 3.5），写入证据目录 README
- 验收：两个冒烟都有 `results.jsonl`、`summary.json`、MP4。证据：`runs/test_results/<date>_vla_p1_smoke/`

### P2 服务与客户端

- [ ] `vla/models/serve.py`：WebSocket 服务，按 3.3 实现 `spec / reset / infer / error`，加就绪检查
- [ ] `vla/models/registry.py`
- [ ] `vla/gym/client.py`：`WebsocketClient`（握手校验版本、超时、`PolicyError`）
- [ ] 测试：`HoldVLA` 起服务，`WebsocketClient` 往返结果与 `LocalClient` 逐位一致；服务端抛异常时客户端收到 `PolicyError` 且连接可继续
- [ ] 冒烟：P1 的两个冒烟改走 `--policy ws://localhost:8000`，结果一致
- 验收：证据目录 `runs/test_results/<date>_vla_p2_server/`

### P3 模型子类（零样本 checkpoint）

每个模型都按同一流程做，逐项勾选：

- **π0.5（`vla/models/pi05/`）**
  - [ ] 独立环境安装 openpi（按其 README；JAX 或 PyTorch 版任选其一并记录）
  - [ ] `Pi05VLA`：Panda 用 `pi05_droid_jointpos`，ALOHA 用 `pi05_base` + trossen 统计量
  - [ ] 输入映射：图像转 CHW、相机槽位、state 排列（ALOHA `[L6, Lg, R6, Rg]`）、prompt
  - [ ] 输出：切前 14 / 8 维、反归一化由 openpi 输出变换完成、增量 → 绝对（确认 openpi `AbsoluteActions` 已处理）、夹爪换算到开度
  - [ ] `adapt_to_pi` 决策（依赖 P4 的关节约定检查）
  - [ ] 离线检查：给一帧 TopoGym 观测，输出形状、数值范围合理（关节在限位内、夹爪 ∈ [0, 1]）
  - [ ] 冒烟：每个机器人 1 seed、带录像
- **GR00T N1.7（`vla/models/groot/`）**
  - [ ] 独立环境安装 Isaac-GR00T；申请 `nvidia/Cosmos-Reason2-2B` 访问权限（HF gated）
  - [ ] `GR00TVLA`：`GR00T-N1.7-DROID`，embodiment tag `OXE_DROID_RELATIVE_EEF_RELATIVE_JOINT`
  - [ ] 输入：两路相机 × 2 帧历史（子类内部缓存前帧）；state = 末端 9 维（按 `gr00t/data/state_action/droid_frame.py` 的 DROID 约定）+ 夹爪 + 7 关节
  - [ ] 输出：取 `joint_position` 与夹爪，得到绝对 8 维
  - [ ] 离线检查 + 冒烟（Panda 1 seed）
- **MolmoAct2（`vla/models/molmoact2/`）**
  - [ ] 独立环境安装 molmoact2 仓库
  - [ ] `MolmoAct2VLA`：`MolmoAct2-DROID`，norm tag `franka_droid`，control mode 文本 "absolute joint pose"
  - [ ] 输入：相机顺序 [agentview, front_oblique, wrist]、378×378；8 维 state；夹爪方向按 DROID 约定核实
  - [ ] 离线检查 + 冒烟（Panda 1 seed）
- **X-VLA（`vla/models/xvla/`）**
  - [ ] 独立环境安装 X-VLA 仓库
  - [ ] 先读官方 `evaluation/robotwin-2.0/client.py`，照抄其 proprio 构造（四元数 → rot6d、夹爪 `1 − 2g`）与动作执行约定；确认 issue #93 的四元数顺序
  - [ ] `XVLAVLA`：`X-VLA-RoboTwin2`、`domain_id=6`；`action_space="ee_abs"`；夹爪二值输出 → 开度
  - [ ] 实现 `aloha` 适配器的 `ee_abs` 分支（TCP 世界系位姿 ⇄ 20 维；`EE_ABS` 动作字典）
  - [ ] 离线检查 + 冒烟（ALOHA 1 seed）
- 验收：每个模型的冒烟证据目录；单元测试覆盖各子类的输入输出转换（用固定假数据，不需要加载权重的部分）

### P4 约定对齐（影响零样本结果的关键项）

- [ ] ALOHA 关节约定：TopoGym `aloha.xml` 的关节零位、正方向 vs openpi Trossen 约定（`aloha_policy.py` 的 `_joint_flip_mask`）；结论写入本文件第 6 节并决定 `adapt_to_pi`
- [ ] ALOHA 夹爪：TopoGym 指轨位置 0.002–0.037 m vs openpi 的 ALOHA 夹爪归一化范围
- [ ] Panda / DROID 相机：TopoGym `agentview` / `front_oblique` / `wrist` 的位置与视角 vs DROID（两个外部相机 + 腕部相机）；记录差异（**不改仿真器相机配置**）
- [ ] 末端坐标系：TopoGym 世界系、TCP 定义 vs GR00T DROID 约定、X-VLA RoboTwin2 约定
- [ ] 每项结论附一张对比截图或一段数值检查输出
- 验收：本节全部勾选，第 6 节相关决策已由用户确认

### P5 首批评测

- [ ] 按第 4 节矩阵跑 1 seed 冒烟，全部模型通过
- [ ] 用 P1 实测吞吐算预算，和用户确认 seed 数与 `--sim-seconds`
- [ ] 正式评测；每格结果、视频归档到 `runs/test_results/<date>_vla_eval_batch1/`
- [ ] 对比表：成功率、结果分布、平均墙钟、每次推理耗时；同时列出 `execute_steps`、实际控制频率、instruction 版本、grasp_assist 设置
- 验收：对比表与证据目录；结论只陈述测得的结果

### P6 过程指标（可选，需要任务维护方同意）

- [ ] 与任务维护方确认每个首批任务可用的过程量（例如是否抓住工具、与目标的距离、穿过的环数）
- [ ] 在 `vla/gym/` 中从 `env.tick_record()` 读取并计算，**不改任务代码**
- [ ] 写入 `results.jsonl`

### P7 微调数据（后续，等用户决定）

- [ ] 用 `topogym/planning/` 参考解在评测配置下生成带 RGB 的演示
- [ ] `vla/gym/export_lerobot.py`：复用 `EmbodimentAdapter`，导出 LeRobot v2.1（关节与 TCP 两列）
- [ ] 各模型格式转换（GR00T `modality.json`、DM0.5 JSONL 等）

---

## 6. 待确认的决策（需要用户拍板）

| # | 问题 | 当前建议 | 状态 |
|---|---|---|---|
| D1 | 辅助抓持 `grasp_assist` 在评测中开还是关 | 整批统一；零样本先关（模型未见过该机制） | 待确认 |
| D2 | 15 Hz 模型的控制频率：取 `control_decimation=27`（14.81 Hz）还是在子类里按时间重采样 | 取 27，并在结果里记录实际频率 | 待确认 |
| D3 | 8 个缺失任务的英文指令文本 | P1 起草后交用户确认 | 待确认 |
| D4 | `execute_steps` 取值 | 先用各模型官方示例值（π0.5 DROID 8、ALOHA 25；GR00T 15；MolmoAct2 15；X-VLA 30），再做一次减半对照 | 待确认 |
| D5 | 每个 episode 的仿真时长 `--sim-seconds` | 按任务参考解时长 × 1.5 | 待确认 |
| D6 | `tick_record()` 开销过大时，是否请 simulator 维护方加只读本体感知接口 | 视 P1 实测 | 待实测 |
| D7 | ALOHA 的 `adapt_to_pi` | 视 P4 结论 | 待实测 |

---

## 7. 风险与已知问题

- 零样本成功率大概率接近 0：拓扑任务是新任务，存在仿真渲染与真实图像的差异，相机位置和关节约定也可能不同。
- 仿真慢（每控制步 6–10 s，GPU 共用时测得），评测预算主要花在仿真上。
- 单卡 24 GB：模型推理与仿真同卡时，GR00T（≥ 16 GB）+ FEM 任务（最高约 10 GB）会超出；首批只选刚体任务。
- X-VLA RoboTwin2 checkpoint 有未解决 issue（#91 回放 0%、#93 四元数顺序）。
- GR00T N1.7 的许可证在 GitHub 与 HF 上表述不一致；只用于研究评测，商用前需确认。
- G0.5（非商用许可、需申请）与 DM0.5（无真机 DROID checkpoint）不在首批零样本矩阵中。

## 8. 参考

- 仿真器调用：[`docs/vla_doc/README.md`](../vla_doc/README.md)、[`topogym/simulator/env.py`](../../topogym/simulator/env.py)、[`topogym/simulator/interaction.py`](../../topogym/simulator/interaction.py)、[`topogym/robot/control.py`](../../topogym/robot/control.py)、[`topogym/sensors/observation.py`](../../topogym/sensors/observation.py)
- 录像：[`topogym/recording/session.py`](../../topogym/recording/session.py)
- 策略协议：[`topogym/simulator/rollout_simulation/policy.py`](../../topogym/simulator/rollout_simulation/policy.py)
- openpi：https://github.com/Physical-Intelligence/openpi （`policies/aloha_policy.py`、`policies/droid_policy.py`、`training/config.py`）
- Isaac-GR00T：https://github.com/NVIDIA/Isaac-GR00T （`getting_started/policy.md`、`gr00t/data/state_action/droid_frame.py`、`examples/DROID/`）
- MolmoAct2：https://github.com/allenai/molmoact2 ；X-VLA：https://github.com/2toinf/X-VLA （`evaluation/robotwin-2.0/client.py`）

## 9. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-09-29 | 创建。阶段目标定为只评测；首批矩阵：Panda 用 π0.5-DROID-jointpos / GR00T-N1.7-DROID / MolmoAct2-DROID，ALOHA 用 π0.5-base / X-VLA-RoboTwin2 |
