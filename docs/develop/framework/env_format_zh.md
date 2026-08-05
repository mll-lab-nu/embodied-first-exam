# TopoGym 环境接口合约（env_format）

> 日期：2026-07-22
> 性质：**对外接口合约**——把 obs / action / 结果状态 / 坐标系当成对外承诺写下来（对标 RoboMME 的 `doc/env_format.md`）。
> 关系：数据集落盘格式见 `../data_pipeline/h5_data_format_zh.md`；坐标系细节见 `genesis_world_coordinates_zh.md`；终态语义见 `mdp_state_terminal_zh.md`。
> 诚实声明：本文写**当前真实形态**，不是理想形态。与 RoboMME 的差距在每节的「差异」里显式标出——写下来是为了让缺口可见、可闭合，而不是假装已对齐。

---

## 0. 当前有两个接口面（关键）

TopoGym 现在**同时**存在两套接口，服务不同下游，形态还没统一：

| 接口面 | 代码 | 覆盖任务 | obs 形态 | action 形态 | 主要下游 |
| --- | --- | --- | --- | --- | --- |
| **A. Gymnasium MDP 环境** | `topogym/envs/*_mdp.py` | swap / onestroke / maze_wall_removal / untangle | 扁平 `Box` 向量 | 4 维**相对** ee 增量 | RL（rsl-rl 适配器） |
| **B. H5 数据集录制** | `topogym/data/`（`EpisodeDatasetWriter`） | swap / untangle / cable_routing | RGB 图像字典 + 本体 | 7 维**绝对** ee 位姿 | IL / VLA（如 π0.5） |

RoboMME 是**单一**接口（obs 字典含图像+本体、动作四选一且全绝对）。我们把两面都如实写在这里；统一成 RoboMME 那种单接口是后续工作。**本节以下的「1. 」写接口面 A（Gym 环境），「2. 」写结果状态（两面共用），数据集面 B 独立成文在 `h5_data_format_zh.md`。**

---

## 1. 接口面 A：Gymnasium MDP 环境

参考实现：`topogym/envs/swap_mdp.py`（`SwapMdpEnv`）。onestroke / maze_wall_removal / untangle 同构，obs 组成各自任务相关。

### 1.1 Gym 风格 API

```python
obs, info = env.reset(seed=..., options=None)
obs, reward, terminated, truncated, info = env.step(action)
```

- 单环境、`gymnasium.Env` 子类；`reset` 返回 `(obs, info)`，`step` 返回标准 5 元组。
- `terminated`：任务**拓扑终态**达成（如 swap 排列正确）——只看任务状态，不看机械臂姿态（见 `mdp_state_terminal_zh.md`）。
- `truncated`：`step_index >= max_episode_steps`（swap 默认 150）。
- 另有 rsl-rl 适配器 `RslRlSwapAdapter`（`num_envs=1` 的 VecEnv 壳）。

### 1.2 动作空间

```
action = [dx, dy, dz, gripper]           # spaces.Box(-1, 1, shape=(4,), float32)
```

- `dx,dy,dz`：**归一化末端增量**，∈[-1,1]，乘以 `robot_control.action_protocol.max_delta_xyz` 得世界系位移；结果 ee 目标裁剪进 workspace，再由 IK 控制器执行 `steps_per_action` 个物理步。
- `gripper`：连续量，`-1`=闭合、`+1`=张开（线性映射到 `[closed_qpos, open_qpos]`）。

> **差异 vs RoboMME**：RoboMME 同一环境支持 `joint_angle / ee_pose / waypoint / multi_choice` 四种、且**全为绝对量**；我们目前只有单一**相对** ee 增量。waypoint 的原料已在 `topogym/planning/waypoint.py`，但没作为动作空间暴露。

### 1.3 观测空间

```
observation_space = spaces.Box(-inf, +inf, shape=(num_obs,), float32)
```

**扁平向量，任务相关拼接**。以 swap 为例（`SwapMdpEnv._build_obs`）按序拼：

| 段 | 维度 | 含义 |
| --- | --- | --- |
| hand | 3 | 末端 xyz |
| gripper | 1 | 当前 gripper qpos / open_qpos |
| block_positions | 3×N | 各方块 xyz（N=任务方块数） |
| target−hand | 3 | 目标方块相对手的位移 |
| center−target | 3 | 目标槽位相对目标方块的位移 |
| center_xy−hand_xy | 2 | 目标槽位相对手的平面位移 |
| is_lifted | 1 | 目标方块是否抬起（0/1） |

`num_obs` 在构造时由 `len(_build_obs())` 动态确定。onestroke / maze / untangle 各有自己的组成，见对应 `*_mdp.py`。

> **差异 vs RoboMME**：RoboMME 的 obs 是**字典**：`front_rgb`/`wrist_rgb`(uint8 256²)、`joint_state`(7)、`eef_state`(xyz+rpy)、`gripper_state`、`is_gripper_close` 等，每个值是 list、`obs[k][-1]` 取当前帧。我们的 Gym obs 是**扁平状态向量、无图像**。图像+本体的字典形态只在数据集面 B（H5 录制）里存在。

### 1.4 info 字典（step / reset 返回）

swap 的 `_build_info` 给出：`success`、`terminal`、`is_lifted`、`target_block_pos`、`target_center`、`reward_terms`、`topology_state`、`step_index`。

> **差异 vs RoboMME**：RoboMME 的 `info` 稳定输出 `task_goal`（语言指令）、oracle 子目标（`simple/grounded_subgoal_online`）、`status` 枚举。我们的 Gym `info` **还没有 `task_goal` / status 枚举**（`task_goal` 目前在 spec 参数与 H5 的 setup 里，不由 `env.step` 的 info 给）。

### 1.5 覆盖度

有 `*_mdp.py`：**swap / onestroke / maze_wall_removal / untangle**（4/7）。
**没有**：`stacked_plate` / `cable_routing` / `peeling`——这三个目前只有物理 demo + H5 录制，没有 RL 环境壳。

---

## 2. 结果状态枚举（两面共用）

`topogym/generation/episode_spec.py`：

```python
class EpisodeStatus(str, Enum):
    SUCCESS = "success"
    FAIL    = "fail"
    TIMEOUT = "timeout"
    ERROR   = "error"     # 物理崩溃（PBD soft abort）收编为合法结果，不是 segfault/流程事故
    ONGOING = "ongoing"
```

`EpisodeResult(key, success: bool, failure_reason, status=ONGOING, ...)`，`EpisodeResult.ok(...)` / `EpisodeResult.failed(..., status=ERROR)`。这个 `status` 会落进 H5 的 `setup`/`info`（见 `h5_data_format_zh.md`）。

> 与 RoboMME 一致：把成功/失败/超时/**物理异常**都做成可上报的枚举，而不是 log 里的一行字。`error` 让"物理崩了"成为一种数据点，而非事故。

---

## 3. 坐标系

右手系、+x 朝物体、桌面 z=0、Panda 基座固定；尺寸/位置怎么算见 `genesis_world_coordinates_zh.md`（本目录），tabletop 基线的表面/相机/时基见 `tabletop_baseline_v1_zh.md`。

---

## 4. 已知差距（一句话清单）

1. 两个接口面未统一（Gym 扁平状态 vs H5 图像字典）。
2. 动作：单一相对增量 ↔ RoboMME 四种绝对动作空间。
3. Gym `info` 无 `task_goal` / 无 status 枚举输出。
4. RL 环境只覆盖 4/7 任务。

这些都不阻塞数据集生成（面 B 已可产 IL 数据），但要成为 RoboMME 式 benchmark 需逐条闭合。
