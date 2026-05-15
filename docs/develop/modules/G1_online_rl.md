# 模块 G1 — Online RL Training（在线强化学习训练）

> 用 rsl-rl（PPO/SAC 等）在 batched env 上**从头训练**或**继续训练**一个 TorchPolicy。
>
> G1 自己**不写训练循环**——循环由 rsl-rl 提供；G1 只负责把 F 包出来、配好超参、把 rsl-rl 启起来。

---

## 1. 输入

**启动期（一次性配置）**
- **F 实例**（已组装好 A+B+C+D+E 的 runtime）
- **E 必须是 TorchPolicy** 子类（带可训练的 `nn.Module`）
- **AlgorithmConfig**：选哪个算法（`ppo / sac / ...`）+ 超参（lr / clip / gamma / lambda / batch_size / ...）
- **TrainConfig**：总迭代数 / 每 iter rollout 长度 / save 间隔 / log 间隔 / 是否 resume
- **OutputDir**：checkpoint 落盘路径 + TensorBoard 日志路径

**训练期（rsl-rl 内部驱动）**：无外部输入；rsl-rl 自己循环 `F.step / F.reset`

---

## 2. 输出

**训练过程中（周期性）**
- **policy checkpoint**：`.pt` 文件（含 network state + optimizer state + iteration count）
- **训练日志**：TensorBoard / wandb / stdout（return / success rate / value loss / policy loss / KL）

**训练完成后**
- 最终 checkpoint + 训练曲线 + 配置快照（reproducibility）

---

## 3. 与其他模块的连接

- **核心调用**：把 F 喂给 **rsl-rl 的 `OnPolicyRunner`**，把 E 的网络注入 rsl-rl 的 policy 适配器
  - rsl-rl `OnPolicyRunner.learn()` 内部反复调 `F.step()`（rsl-rl env 接口面）
  - 反向梯度更新落到 E 内的 `nn.Module`
- **不和 G2/G3 交互**：G1 产出的 checkpoint 后续可以喂给 G2（生成专家数据）或 G3（评测），但那是流程顺序，运行时无依赖
- **依赖 F 的"rsl-rl 接口面"**：这是 F 构造期暴露的两个 adapter 之一

---

## 4. 内部逻辑概述

**主流程**
1. **加载配置**：用 Hydra/OmegaConf 把 AlgorithmConfig + TrainConfig 合并
2. **建 env**：让 A+B+C+D 组装出 env，让 F 包好（n_envs 从 config 读）
3. **建 policy**：实例化 TorchPolicy（如果 resume，加载 checkpoint）
4. **配 rsl-rl runner**：
   - 用 F 的 rsl-rl 接口面创建 env handle
   - 构建 `OnPolicyRunner(env=F, train_cfg=..., log_dir=...)`
   - 算法（PPO/SAC）和 actor-critic 网络通过 train_cfg 注入
5. **调 `runner.learn(num_learning_iterations=K, init_at_random_ep_len=True)`**
   - rsl-rl 内部循环：
     a. 用当前 policy rollout 收集 trajectories（调 F.step × N 步）
     b. 计算 advantage（GAE）
     c. PPO/SAC 更新 policy + value 网络
     d. 周期性 save checkpoint
     e. 写日志
6. **训练完成**：dump 最终 checkpoint + 训练 metric 总结

**Resume 路径**
- 启动时检测 `--resume <path>` → 加载 checkpoint 到 E + optimizer + iter counter → 继续 learn

**关键纪律**
- G1 **不重写** rsl-rl 的训练循环；只配置 + 启动 + 监听
- 算法侧的所有 hyperparameter 都在 config 里（不允许在代码里写魔法数）
- **`Algorithm` 抽象**：虽然 MVP 走 rsl-rl，但接口层留 `Algorithm` 协议（`init / learn / save / load`），将来可加 RLinf / TorchRL / 自研实现而不改 G1 入口

**关于 rsl-rl 已知坑**
- Issue #757 报告官方 example 曾因 rsl-rl 升级 v2 broken；MVP 阶段先验证 F 的 rsl-rl 接口面在最新 rsl-rl-lib 上能跑通（dummy task + 10 iter PPO）

**外部依赖**
- rsl-rl-lib (>= 5.0.0)
- PyTorch（优化器 + 反向）
- TensorBoard / wandb（日志后端，可选）
