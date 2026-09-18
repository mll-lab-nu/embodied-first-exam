# 模块 B — Task（任务定义）

> "这个任务到底想干嘛"的唯一权威——什么算成功、每步给多少奖励、什么时候结束、初始状态怎么随机。
>
> B 是**纯逻辑层**：不碰 Genesis API，只读 Scene 状态、做计算、产出 reward / done / info。

---

## 1. 输入

**构造期**
- **TaskSpec**：任务 ID + 难度档 + reward 权重表（来自 config）

**每步**
- **Scene 物理状态**（通过 Scene 句柄读取，由 A 提供）
  - 机器人关节状态
  - 任务 props 的世界坐标（绳子顶点、tile 朝向、棋子位置…）
- **当前 step_index**（来自 F）

**Episode 边界（reset 时）**
- **reset 信号** + **episode seed**

---

## 2. 输出

**构造期**
- **TaskMeta**：注册到 runtime 的元信息（成功判定函数、reward 项清单、最大步数、拓扑指标列表）

**每步**
- `reward[B]`：B 路并行环境的奖励张量
- `terminated[B]`：哪些 env 自然终止（成功 / 不可恢复失败）
- `truncated[B]`：哪些 env 超步数截断
- `info` dict（按 env 分），至少包含：
  - `success[B]`（bool）
  - `topology_state`（B 路并行的"任务侧拓扑表达"，例如绳子交叉数、置换距离、连通图）
  - `reward_terms`（各分项原始值，便于 debug）

**Episode 边界**
- **初始配置 dict**（一批 N 份）—— 交给 A 落到场景

---

## 3. 与其他模块的连接

- **被谁调**：F 在 step 路径每步调；在 reset 路径每 episode 开头调一次
- **它读谁**：A 提供的 Scene 句柄 + Entity Manifest（读物体状态）
- **谁读它**：
  - F 把 reward / done / info 打包进 TimeStep 流
  - D 可以在 obs 里复用 B 计算的 `topology_state`（避免重复算）
  - G3（Eval）把 `topology_state` 当作 scoring 的核心信号
- **不连接**：B 不直接和 C / E 通信，也不知道 policy 是什么

---

## 4. 内部逻辑概述

**构造期**
1. 解析 TaskSpec → 决定该 task 用哪些 reward 项（sparse-success / topology-shaping / collision-penalty / time-penalty / 子目标 …）
2. 注册**拓扑指标计算器**（task-specific）：
   - knots：从绳顶点序列 → 投影到 2D → 交叉数
   - pipe：从 tile 朝向 → 邻接图 → BFS 连通分量
   - swap：从 tile 序列 → 与目标置换的 Cayley 距离
   - chat_noir：从棋盘占据 → 猫的最短到边界路径
3. 注册**初始配置采样器**（按难度档定义参数分布）

**每步**
1. 读 Scene 状态 → 算出 `topology_state[B]`
2. 算每个 reward 项（向量化，输入是 batch 状态）
3. 加权求和 → `reward[B]`
4. `success[B] = success_fn(topology_state)`；`terminated[B] = success | unrecoverable_failure`
5. 组装 `info`（包含 `topology_state` 以供 D 复用）

**Reset 时**
1. 用 episode seed → 调初始配置采样器，产 N 份初始配置
2. 把这 N 份 dict 返回给 F（F 转交给 A 落地）

**关键纪律**
- B **不知道**机器人长什么样、policy 是什么、obs 怎么拼——它只看 Scene 物体状态
- `topology_state` 的计算结果应该**缓存一帧**，D 直接复用，不重复算
- reward shaping 必须按 task 内的"拓扑距离"来定义（距离成功的拓扑差距），不允许引入与拓扑无关的 hack 项

**外部依赖**：无（纯逻辑层）。
