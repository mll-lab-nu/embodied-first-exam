# TopoGym 模块连接图 — 输入/输出 + 外部依赖布线

> 状态：**承接 `overall_gramework.md` 的 8 盒子拆解**（A-F 是 6 个功能模块、G1-G3 是 3 种启动方式、H 是配套设施，本文先放下不讲）。
>
> 本文只回答两件事：**(1)** 每个模块**对外看到的输入和输出是什么**；**(2)** 这些模块如何通过这些输入输出，**加上 Genesis / rsl-rl / VLA 模型库等外部依赖**，串成一个跑得起来的系统。
>
> 全文不写任何 class 名 / 函数签名，只给"管什么数据进、什么数据出、谁调谁"的概念图。

---

## 0. 先把外部依赖看清楚（我们站在谁肩膀上）

| 外部库 | 我们用它做什么 | **谁直接调用它**（仅这些模块碰它，其它模块不知道它存在） |
| --- | --- | --- |
| **Genesis** | 物理仿真、N 路并行 step、相机渲染、机器人加载 | **A**（建场景）、**C**（发关节命令）、**D**（读状态+渲染） |
| **rsl-rl** | PPO/SAC 算法 + 训练循环 | **G1**（在线 RL 训练） |
| **HuggingFace + OpenVLA / RT-2 / π₀ 等 VLA 模型** | 加载预训练权重、本地推理 | **E**（policy 的某个子类） |
| **OpenAI / Anthropic / Google AI 等 HTTP API** | VLM 远端推理（GPT-4V / Claude / Gemini） | **E**（policy 的另一个子类） |
| **存储后端**（h5py / zarr / LeRobot writer …） | 把轨迹落盘 | **G2**（离线数据生成） |
| **PyTorch** | 神经网络的张量计算 / 优化器 | **E**（学的 policy）+ **G1**（训练器） |

→ **关键纪律**：只有上表列出的模块直接 `import` 对应外部库。其它模块通过本框架内部的接口拿东西，不知道底下是 Genesis 还是别的。

---

## 1. 六个核心模块（A-F）的输入 / 输出

每个模块按三段时序拆：**构造期**（启动时调一次）、**每步**（policy 决策一次的频率）、**episode 边界**（reset 时）。

### A. World Builder — 造世界
| 时机 | 消费 (输入) | 产出 (输出) |
| --- | --- | --- |
| **构造期** | TaskSpec（任务 ID + 难度 + seed）+ AssetRef（URDF / mesh 路径）+ SimConfig（n_envs / dt / device） | 已 `build(n_envs)` 的 Scene 句柄 + 命名实体表（"robot" / "rope_0" / "tile_grid" / "topdown_cam" …） |
| **每步** | — | — |
| **Episode 边界** | 来自 B 的初始拓扑配置（"这局绳子的初始连法 / 方块的初始排列"） | 把场景里的实体物理状态重置到该配置 |
| **外部直接调用** | **Genesis**：`gs.init / gs.Scene / add_entity / build / set_qpos` | |

### B. Task — 任务定义
| 时机 | 消费 | 产出 |
| --- | --- | --- |
| **构造期** | TaskSpec | 该 task 的 reward / success / 终止规则注册到 runtime |
| **每步** | 当前 Scene 物理状态（通过 D 或直接读 Scene）| `reward[B]` + `terminated[B]` + `truncated[B]` + info（含 `success`、`topology_state`、子奖励拆解） |
| **Episode 边界** | reset 信号 + episode seed | 初始拓扑配置（交给 A 落地） |
| **外部直接调用** | 无（纯逻辑层）| |

### C. Embodiment & 动作接口
| 时机 | 消费 | 产出 |
| --- | --- | --- |
| **构造期** | 机器人 AssetRef + 动作模式选择（joint / EE-pose / primitive）+ 控制器配置 | **ActionSpace 声明**（告诉上游 E："你必须输出形如 \[B, 7\] 的 EE 增量" 之类）+ 把机器人加进 Scene |
| **每步** | `action[B, action_dim]`（E 输出的、符合 ActionSpace 的张量）| 关节命令（位置/速度/力矩目标）发给 Genesis；可选返回 `action_ok[B]` 标记（例如 IK 失败、超出工作空间）|
| **Episode 边界** | reset 信号 | 把机器人摆回 home pose |
| **外部直接调用** | **Genesis**（`set_dofs_kp / control_dofs_position / ...`）；可选 IK 库 | |

### D. Observation — 观测打包
| 时机 | 消费 | 产出 |
| --- | --- | --- |
| **构造期** | ObservationSpec（要哪些相机 / 哪些 proprio / 要不要符号 state）| 在 Scene 里注册需要的相机；声明 obs 形状给 E |
| **每步** | Scene 状态 + Genesis 渲染的相机帧（多个） | `obs[B] = {"rgb_topdown": [B,H,W,3], "rgb_wrist": [B,...], "joints": [B,7], "ee_pose": [B,7], "topo_state": [B,...]}`（具体字段按 spec） |
| **Episode 边界** | reset 后的初帧 | 同上格式的初始 obs |
| **外部直接调用** | **Genesis**（相机 `render` + 状态读取） | |

### E. Policy — 策略
| 时机 | 消费 | 产出 |
| --- | --- | --- |
| **构造期** | 模型/权重/规则（HF checkpoint 路径 / .pt 文件 / API key / 脚本规则）+ ObservationSpec + ActionSpace（用来知道 I/O 形状） | 一个可调用的 policy 对象 |
| **每步** | `obs[B]`（来自 D）+（可选）info | `action[B, action_dim]`（满足 ActionSpace）+（可选）`log_prob[B]` / `value[B]` 等 RL 训练需要的辅助量 |
| **Episode 边界** | reset 信号（清空 RNN hidden state / 重置 OpenVLA 的 action chunk 缓存等）| — |
| **外部直接调用**（按子类不同） | HuggingFace `from_pretrained`、`torch.nn.Module`、OpenAI/Anthropic HTTP SDK | |

### F. Runtime — 批量交互循环
| 时机 | 消费 | 产出 |
| --- | --- | --- |
| **构造期** | 已组装的 env（= A+B+C+D 打包）+ E 的实例 + RunConfig（n_envs / max_steps / auto_reset 策略） | 一个可被 G1/G2/G3 调用的"批量 rollout 引擎" |
| **每步** | 自循环（内部驱动 D→E→C→Genesis→B 那条链） | `TimeStep` 流：`(obs[B], action[B], reward[B], done[B], info[B])` |
| **Episode 边界** | 自动调 A+B 的 reset hook | episode 级 summary：`return[ended]` / `length[ended]` / `success[ended]` |
| **对外接口契约** | 同时满足两套形状：(a) Gymnasium `VectorEnv`（`step / reset / action_space / observation_space`）；(b) rsl-rl 期望的 `GenesisEnv` 形状（`get_observations / step / reset` 的具体签名） | |
| **外部直接调用** | 无（这一层不碰外部库，只把内部模块编排起来） | |

---

## 2. 三种启动方式（G1-G3）的输入 / 输出

这三条都建在 F 之上，**核心区别只是"谁来驱动循环、产出什么"**。

### G1. Online RL Training — 在线 RL 训练
| 项 | 内容 |
| --- | --- |
| **消费** | F 实例 + 一个**待训练的** E（典型是 TorchPolicy，里头是一个 actor-critic 网络）+ 算法超参（lr / ppo_clip / 总训练步数 / ...）|
| **产出** | 训练好的 policy checkpoint（`.pt`）+ TensorBoard/wandb 日志 + 训练曲线 |
| **谁驱动循环** | **rsl-rl 的 `OnPolicyRunner`**——它在内部循环里反复调 `F.step()`，收集 rollout、算 advantage、做梯度更新 |
| **我们要写的连接代码** | 把 F 包装成 rsl-rl 期望的 env 形状（这部分已经是 F 的契约之一），把 E 的网络注入 rsl-rl 的 policy 接口，配 RunnerCfg/AlgoCfg/PolicyCfg 三件套 |
| **外部依赖** | rsl-rl + PyTorch |

### G2. Offline Data Generation — 离线数据生成
| 项 | 内容 |
| --- | --- |
| **消费** | F 实例 + 一个**已经能跑通**的 E（典型是 ScriptedPolicy / OraclePolicy / 训练好的 TorchPolicy）+ 数据规格（保存路径 / 字段列表 / codec / 目标 episode 数）|
| **产出** | 落盘的轨迹数据集（HDF5 / Zarr / LeRobot / RLDS）+ DatasetCard（README + 元数据 + split 信息）|
| **谁驱动循环** | **我们自己写的简单循环**：`for ep in range(N): obs = F.reset(); while not done: step = F.step(policy(obs)); recorder.append(step)` |
| **我们要写的连接代码** | Recorder（把 TimeStep 流压成数据集格式）+ DatasetCard 写出 |
| **外部依赖** | 存储后端（h5py / zarr / ...）|

### G3. Eval — 评测
| 项 | 内容 |
| --- | --- |
| **消费** | F 实例 + 一个**任意类型的 trained** E（OpenVLA / 训完的 PPO / VLM / scripted baseline）+ eval 配置（哪些难度、每档多少 episode、是否确定性）|
| **产出** | 每 episode JSONL（success / 步数 / return）+ 聚合 metric 报告 + 可选 GIF |
| **谁驱动循环** | **我们自己写的简单循环**：和 G2 同款，但消费的是 Scorer 而不是 Recorder |
| **我们要写的连接代码** | Scorer（聚合 success rate / 拓扑指标）+ Report（出 JSON + 图）|
| **外部依赖** | 无（用 F + E 就够）|

→ **关键对称**：G2 和 G3 在循环结构上**几乎一样**，区别只是末端消费者（写盘 vs. 算指标）。G1 用 rsl-rl 接管循环，所以**唯一**它和 G2/G3 不一样的地方在"谁在外面套循环"。

---

## 3. 数据流连接图

### 3.1 一个 step 内（policy 决策一次 = 一个 `F.step` 调用）

```
                  ┌─────────────────────────────┐
                  │  Genesis Scene (state at t) │
                  └──────────────┬──────────────┘
                                 │
                    (reads state + cameras)
                                 │
                  ┌──────────────▼──────────────┐
                  │      D  Observation         │   ←──── Genesis 渲染 API
                  │  打包 obs[B] = {rgb, ...}   │
                  └──────────────┬──────────────┘
                                 │  obs[B]
                                 ▼
                  ┌─────────────────────────────┐
                  │      E  Policy              │   ←──── HF / VLM API / torch
                  │   act(obs) → action[B]      │        (因子类而异)
                  └──────────────┬──────────────┘
                                 │  action[B]   ← ActionSpace 规定的形状
                                 ▼
                  ┌─────────────────────────────┐
                  │   C  Embodiment             │   ←──── Genesis 关节控制 API
                  │  action → 关节命令          │        (+ 可选 IK 库)
                  └──────────────┬──────────────┘
                                 │  joint cmd
                                 ▼
                  ┌─────────────────────────────┐
                  │  Genesis 物理 step (dt)     │
                  └──────────────┬──────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │  Scene (state at t+1)       │
                  └──────────────┬──────────────┘
                                 │
                    (reads new state)
                                 │
                  ┌──────────────▼──────────────┐
                  │      B  Task                │
                  │ → reward[B], done[B], info  │
                  └──────────────┬──────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │   F  Runtime 打包 TimeStep  │
                  │ (obs, action, reward, done, │
                  │   info)                     │
                  └─────────────────────────────┘
```

**注意几个细节**：

- 所有箭头上的张量都带 `B` 维（n_envs）。Genesis 的批量是 **GPU 上 N 个场景同步演化**，不是 N 个进程。
- 如果 C 的动作模式是"高层原语"（比如"pick at (x,y)"），那一次 `F.step` 内部 C 会**驱动多个 Genesis 物理 step** 直到原语执行完，**但外层 policy 看到的还是一次决策**。这点要写进 F 的约定里。
- B 计算 `topology_state` 时可能要看物体世界坐标（在 Scene 里读）——所以 B 也间接读 Scene，但不直接调 Genesis API。

### 3.2 一个 episode 的生命周期

```
G_x.run():
   │
   ├─ F.reset()
   │     ├─ B 生成初始拓扑配置 (e.g. 随机一个置换 / 随机一根纠缠绳)
   │     ├─ A 把该配置落到 Scene (set_qpos / 重新摆放刚体)
   │     ├─ C 把机器人摆回 home
   │     ├─ E 清自己的内部状态
   │     └─ D 渲染初帧 → 返回 obs[B]
   │
   ├─ while not all_done:
   │     └─ F.step(action)  ← (见 §3.1)
   │
   └─ F emit episode summary  → 交给 G_x 的下游 (训练 / 落盘 / 打分)
```

### 3.3 三种启动方式如何复用 F

```
                     ┌───────────────────────────────────────────────┐
                     │             G1   Online RL                    │
                     │  rsl-rl OnPolicyRunner.learn()                │
                     │     ↳ 内部反复调 F.step()                     │
                     │     ↳ 同步更新 E 里的网络权重                 │
                     │     ↳ 周期性 save checkpoint                  │
                     └────────────────────┬──────────────────────────┘
                                          │
                     ┌────────────────────┴──────────────────────────┐
                     │             G2   Offline Data Gen             │
                     │  for ep: while not done: F.step(); recorder ← │
                     │     ↳ E 是固定的 (scripted / oracle / 训好的) │
                     │     ↳ 末端写 HDF5/Zarr/LeRobot                │
                     └────────────────────┬──────────────────────────┘
                                          │
                     ┌────────────────────┴──────────────────────────┐
                     │             G3   Eval                         │
                     │  for ep: while not done: F.step(); scorer ←   │
                     │     ↳ E 是固定的 trained policy               │
                     │     ↳ 末端出 metric 报告                      │
                     └────────────────────┬──────────────────────────┘
                                          │
            ═══════════ 三条路径都消费同一个 F ═══════════
                                          │
                                          ▼
                              ┌──────────────────────┐
                              │   F  Runtime         │
                              │ (env + policy 编排)  │
                              └──┬─────────────┬─────┘
                                 │             │
                                 ▼             ▼
                       ┌─────────────────┐  ┌──────────────────┐
                       │ env = A+B+C+D   │  │  E (Policy)      │
                       └─────┬───────────┘  └────────┬─────────┘
                             │                       │
                             ▼                       ▼
                       ┌──────────┐         ┌────────────────────┐
                       │ Genesis  │         │ HF / VLM HTTP /    │
                       └──────────┘         │ torch / 脚本       │
                                            └────────────────────┘
```

---

## 4. 关键接口契约（哪两个模块的接口必须严格对齐）

| 必须对齐的两个面 | 怎么对齐 |
| --- | --- |
| **C 声明的 ActionSpace** ↔ **E 输出的 action 形状** | C 在构造期就把 ActionSpace 暴露出来；E 在构造期吃这个 spec 来配置自己（OpenVLAPolicy 要做反归一化时需要知道目标范围；TorchPolicy 要据此决定输出头的大小）|
| **D 声明的 ObservationSpec** ↔ **E 期望的 obs 输入** | 同上反方向；如果 OpenVLA 要 224×224 RGB，就在 ObservationSpec 里指定 `rgb_wrist: (224, 224)`；其它字段不要白渲染 |
| **F 的对外接口** ↔ **rsl-rl 期望的 env 形状** | F 必须实现 rsl-rl 的 `step / reset / get_observations / num_envs / num_obs / num_actions` 等约定；这是 G1 能开箱用 PPO 的关键 |
| **F 的对外接口** ↔ **Gymnasium VectorEnv 形状** | 兼容 Gymnasium 让 G2/G3 的简单循环也可以走标准 API，方便引入第三方算法库 |
| **A 命名实体表** ↔ **B/C/D 引用实体的名字** | 字符串 ID 要全局一致（例如 `"robot"`, `"target_grid"`）；建议在 A 构造完后输出一份 entity manifest 给其它模块查 |
| **B 的初始拓扑配置 schema** ↔ **A 的 reset 输入 schema** | 这是 reset 路径的"协议"：B 输出 dict，A 知道怎么按 dict 摆场景；一份 schema 写在两侧之间共享 |

---

## 5. 几个需要明确约定的边角细节

> 这些点在写每个模块的 design doc 前最好先共识一下，避免后期反复改接口。

1. **拓扑状态归谁算**：B 计算 `topology_state`（任务侧权威）；D 在 obs 里**复用** B 的结果，不重复计算。
2. **谁决定 reset 时机**：F 看 `done[B]` 自动 reset 单个 env（auto-reset 是 VecEnv 的标准做法）；外层 G1/G2/G3 不用关心。
3. **高层原语的多物理步执行**：如果 C 的 ActionSpace 是 primitive（如 pick-place），单次 `F.step` 内部 C 驱动多次 Genesis 物理 step；这层"内 loop"对上层完全透明。
4. **VLA 的 action chunking**：OpenVLA / π₀ 等会一次输出多步 action chunk；放在 E 内部缓存，对上层依然表现为"每步问一次"。这是 E 的内部状态，不污染 F 的接口。
5. **G1 训练时的 deterministic vs. stochastic**：E 必须支持模式切换（rollout 时采样、eval 时贪心），通过 RunConfig 注入。
6. **n_envs 的边界**：A 在 `build(n_envs)` 时固定 n_envs，之后不能动态变更；G1/G2/G3 在 RunConfig 里声明，由 F 透传到 A。

---

## 6. 一句话总结连接关系

> **A 搭场景、B 定规则、C 译动作、D 拼观测**——这四个一起组成 **env**；
> **E 是 policy**，独立存在；
> **F 把 env 和 policy 串成批量循环**，对外暴露统一接口；
> **G1/G2/G3 在 F 外面套不同的"消费方式"**，分别交给 rsl-rl / Recorder / Scorer。
>
> 外部依赖只在四个位置接入：**A/C/D 用 Genesis**，**G1 用 rsl-rl**，**E（按子类）用 HuggingFace 或 VLM HTTP**，**G2 用存储后端**。其它所有模块只跟"框架内部张量+协议"打交道。

---

## 7. 下一步建议

把"最瘦版"的每个模块各写一个 stub 跑通端到端（推荐挑 `order_swap_puzzle` 的物理版做 MVP，纯刚体最容易），验证：

1. F 的两套接口（Gymnasium VectorEnv + rsl-rl GenesisEnv 形状）都能立得住。
2. 同一个 env + 三种 policy（随机 / scripted / 一个微型 PPO）都跑得通。
3. G1（rsl-rl PPO 训练能跑 10 个 iteration）、G2（能写出 100 episode HDF5）、G3（能出 success rate 报告）都端到端走通。

一旦这条骨架立起来，knot / pipe / chat_noir 等任务就只是往 A/B 里填血肉。
