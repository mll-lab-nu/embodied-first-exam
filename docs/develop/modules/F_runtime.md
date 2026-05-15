# 模块 F — Runtime（批量交互循环）

> 整个框架的**承重墙**：把 A+B+C+D 组装成的 env 和 E 这个 policy 串起来，跑那条 `obs → action → step → reward → done` 循环，并且 **N 路并行**。
>
> F 自身**不调用任何外部库**，只编排内部模块；它的对外接口必须同时满足两套规范，让 G1/G2/G3 都能无障碍消费。

---

## 1. 输入

**构造期**
- **env**：由 A + B + C + D 组装好的对象（F 内部知道怎么调它们的 step/reset hook）
- **policy**：E 实例
- **RunConfig**：`n_envs`（透传到 A 的 build）、`max_episode_steps`、`auto_reset` 策略、`deterministic`（影响 E 模式）

**每步（外部驱动者调）**
- `action[B, action_dim]`：来自 E（典型场景下 F 自己内部调 E 得到，外部驱动者只调 `F.step()` 不显式传 action）

**Episode 边界**
- F 自动管：哪个 env 的 `done=True` 就立刻 reset 该 env

---

## 2. 输出

**构造期**
- 一个**双面接口**的 runtime 对象：
  - 面 A：Gymnasium `VectorEnv` 形状（`step / reset / action_space / observation_space`）
  - 面 B：rsl-rl 期望的 `GenesisEnv` 形状（`step / reset / get_observations`、属性 `num_envs / num_obs / num_actions`）

**每步**
- `TimeStep`：`(obs[B], action[B], reward[B], terminated[B], truncated[B], info)`
- 注意：在 auto-reset 语义下，刚 reset 的 env 在同一帧返回的是**新 episode 的初 obs**（VecEnv 标准做法）

**Episode 级**
- 每当某个 env 的 episode 结束，emit 一个 `EpisodeSummary`：`return / length / success / termination_reason`
- G1（rsl-rl）通过 info 拿；G2/G3 通过 hook 拿

---

## 3. 与其他模块的连接

- **被谁调**：G1（rsl-rl runner 在内部循环里调 step/reset）/ G2 / G3（我们自己的简单循环调）
- **它编排谁**（每个 step 内部按顺序）：
  1. D（拼 obs）
  2. E（出 action）
  3. C（落到 Genesis 命令）
  4. Genesis 物理推进 dt
  5. B（算 reward / done / info）
  6. 自动 reset 已 done 的 env（调 A 重置 + D 重新拼 obs）
- **对外暴露的 ActionSpace / ObservationSpec**：透传 C 和 D 的声明（保证下游算法看到一致的接口）

---

## 4. 内部逻辑概述

**构造期**
1. 接收 env（A+B+C+D 已组装好）+ E + RunConfig
2. 让 A 完成 `scene.build(n_envs)`（如果 A 还没 build）
3. 初始化 per-env 状态 buffer：步数计数器、累积 return、上次 reset 时间
4. 暴露**两套 adapter**：
   - `as_gym_vec_env()` 返回符合 Gymnasium 的视图
   - `as_rsl_rl_env()` 返回符合 rsl-rl 的视图
   - 同一个底层 runtime，两个壳

**每步（`step(action)` 路径）**
1. 把 action 喂给 C → C 译成关节命令 → Genesis tick
2. （可选）等 substep 完成（高层 primitive 模式下 C 内部已跑完子循环）
3. 调 B 算 reward / done / info
4. 调 D 拼新 obs
5. 检查 `done = terminated | truncated`；对每个 done 的 env：
   - 让 B 采样新初始配置
   - 让 A 落到场景
   - 让 C 把机器人摆 home
   - 让 D 渲染新初帧
   - **该 env 的 obs 直接替换成新 episode 的初 obs**（VecEnv auto-reset 标准）
   - emit EpisodeSummary
6. 打包 TimeStep 返回

**`reset()` 路径**
- 强制对所有 env reset，返回初帧 obs

**关键纪律**
- F 不知道 policy 是 OpenVLA 还是 PPO，也不知道 Genesis 在底下；只编排
- **n_envs 是 GPU native batching**：B 路并行的 step 是 Genesis 内部一次 GPU kernel，**不是** Python 多进程
- 双 adapter 保证：G1 的 rsl-rl 可以直接用，G2/G3 也可以走 Gymnasium 标准接口（方便引入第三方算法库）
- 失败可恢复：暴露 checkpoint hook（保存 RNG 状态 + per-env 步数），G1 训练长跑断了能恢复

**外部依赖**
- 无（F 自身不 import 任何外部库；它依赖的所有能力都通过 A/B/C/D/E 提供）
