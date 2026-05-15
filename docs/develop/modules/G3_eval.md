# 模块 G3 — Eval（评测）

> 用**任意 trained policy**（OpenVLA / 训完的 PPO / VLM / scripted baseline）在 batched env 上跑 N 个 episode，按拓扑感知 metric 打分并出报告。
>
> 结构上和 G2 几乎一样：自己写循环，区别只是末端消费者从 Recorder 换成 Scorer。

---

## 1. 输入

**启动期**
- **F 实例**（带 env + frozen E）
- **E 可以是任意已加载/训好的 policy 子类**
- **EvalConfig**：哪些任务、哪些难度档、每档多少 episode、是否 deterministic、是否存 GIF、并行 n_envs
- **MetricSpec**：要算哪些指标（success_rate / avg_steps_on_success / avg_topology_distance / illegal_action_rate …）

**运行期**：无外部输入

---

## 2. 输出

**主产物**
- **episode JSONL**：每条 episode 一行，含 `(task, difficulty, seed, success, length, return, final_topology_state, final_reason)`
- **聚合 summary.json**：按 task × difficulty × policy 分组的 metric 汇总（success_rate、置信区间、avg_length on success、failure mode breakdown）

**可选产物**
- 重点 episode 的 **rollout GIF**（最难、最快、典型失败各几条）
- 比较表（同一 task 多个 policy 的对照）
- TensorBoard 写出（如果是训练侧 G1 的中段评测调用 G3）

---

## 3. 与其他模块的连接

- **核心调用**：自己写的 batched 循环（结构和 G2 同款）+ Scorer
- **被谁调**：
  - 命令行入口（`topogym-eval`）独立调
  - G1 训练中段周期性调（在某个 iter 间隔做一次"中场评测"）
- **可消费**：
  - G1 的 checkpoint（把它装进 TorchPolicy 评）
  - 任何 E 子类（OpenVLA / VLM / scripted baseline 都能直接评）
- **不写盘任何完整轨迹**（那是 G2 的事）；只写摘要 + 可选 GIF

---

## 4. 内部逻辑概述

**主流程**
1. **加载配置**：EvalConfig + MetricSpec + 要评的 task 列表
2. **建 env + policy**：和 G1/G2 同款；E 设成 eval/deterministic 模式
3. **建 Scorer**：
   - 按 MetricSpec 决定要算哪些指标
   - 每个 metric 是一个累加器（success_rate = 成功 episode 数 / 总数）
4. **建 Reporter**：负责把累加器的最终值序列化成 JSONL + summary
5. **主循环（按 task / difficulty 分组）**：
   ```
   for task, difficulty in eval_matrix:
       reconfigure F to (task, difficulty)
       completed = 0
       while completed < target_per_combination:
           obs = F.reset()
           per_env_active = [True] * n_envs
           per_env_trace = [empty list for each]  # 仅留 GIF 候选时记
           while any(active):
               action = E.act(obs)
               step = F.step(action)
               obs = step.obs
               for i in active_envs:
                   if config.save_gif: per_env_trace[i].append(step.obs.rgb)
                   if step.done[i]:
                       scorer.update_episode(task, difficulty, step.info[i])
                       if eligible_for_gif(step.info[i]):
                           save_gif(per_env_trace[i], step.info[i])
                       per_env_trace[i] = []
                       active[i] = False
                       completed += 1
   reporter.finalize(scorer.aggregate())
   ```
6. **聚合输出**：调 Reporter 写 JSONL + summary + plots

**与 G2 的区别**
- G2 关心"每一帧记下来"（数据集）；G3 关心"每一条 episode 的最终成败 + 路径长度"（指标）
- G3 只缓存少量帧用于 GIF；G2 把每帧落盘

**关键纪律**
- E 在评测时必须 deterministic（rollout 时贪心 / 关闭采样噪声）—— 这由 RunConfig 注入到 F、F 透传到 E
- 评测必须**多 seed**（避免单 seed 走运）；MetricSpec 暴露置信区间字段
- **拓扑感知 metric** 是核心卖点：success_rate 只是入门，真正有意义的是 "距离成功的拓扑距离"（crossing 数差、permutation 距离、连通分量差等）

**外部依赖**
- 无（用 F + E 就够）；可选 imageio / Pillow 写 GIF
