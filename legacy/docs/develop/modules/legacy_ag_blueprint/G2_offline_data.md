# 模块 G2 — Offline Data Generation（离线数据生成）

> 用**固定的** policy（scripted / oracle / 训好的 TorchPolicy）在 batched env 上跑 N 个 episode，把所有轨迹落盘成可被 LeRobot / RLDS / 自研下游消费的数据集。
>
> G2 自己写循环（rsl-rl 不参与），核心是 Recorder + 存储后端。

---

## 1. 输入

**启动期**
- **F 实例**（带 env + 固定 E）
- **E 必须是不更新参数的 policy**：ScriptedPolicy / OraclePolicy / 加载好权重的 TorchPolicy / OpenVLAPolicy（罕见）
- **TrajectorySchema**：每帧记录哪些字段 + 用什么 codec（`rgb` 用 JPEG / PNG，`joints` 用 float32 …）
- **DataConfig**：目标 episode 数 / 每条最大步数 / 是否过滤失败 episode / 输出路径 / 数据集格式选择（HDF5 / Zarr / LeRobot / RLDS）
- **(可选) MetadataTemplate**：DatasetCard 的 README 模板

**运行期**：无外部输入

---

## 2. 输出

**数据集文件**
- 主数据：按选定格式落盘（per-episode 文件或单一容器）
- 每条 episode 含：`obs / action / reward / done` 序列 + episode metadata（seed、success、长度、final topology_state）

**辅助产物**
- **DatasetCard**（README）：任务说明、生成方式、字段 schema、split 信息
- **index 文件**：episode 列表 + 索引信息
- **生成日志**：每条 episode 的耗时、成功与否、被丢弃原因

---

## 3. 与其他模块的连接

- **核心调用**：自己写的简单 batched 循环 → 反复调 `F.step()` + `Recorder.append()`
- **可消费**：G1 训出来的 checkpoint（把它加载进一个 TorchPolicy，然后用 G2 生成专家数据）
- **下游**：产出的数据集可以喂给 BC / IL / 离线 RL 训练（在 G1 之外的另一条 path，本框架后续模块）
- **不和 G3 交互**：G3 是评测，G2 是采数据，独立运行

---

## 4. 内部逻辑概述

**主流程**
1. **加载配置**：Hydra/OmegaConf 合并 TrajectorySchema + DataConfig
2. **建 env + policy**：和 G1 一样的方式建 F 和 E，但 E 设成 eval/frozen 模式（不算梯度）
3. **建 Recorder**：
   - 按 TrajectorySchema 决定每帧记什么
   - 按 DataConfig 选存储后端（h5py / zarr / LeRobot writer / RLDS writer 之一）
   - 预开输出目录 + index 文件
4. **主循环**：
   ```
   completed = 0
   while completed < target_episodes:
       obs = F.reset()
       per_env_buffers = [empty list for each of n_envs]
       active = [True] * n_envs
       while any(active):
           action, aux = E.act(obs)
           step = F.step(action)   # 含 obs', reward, done, info
           for i in env_ids_active:
               per_env_buffers[i].append(record_frame(step, i))
               if step.done[i]:
                   recorder.commit_episode(
                       buffer=per_env_buffers[i],
                       metadata=summarize(step.info[i]),
                   )
                   per_env_buffers[i] = []
                   active[i] = (B 总 episode 还没攒够 N → True，否则 False)
                   completed += 1
           obs = step.obs
   recorder.finalize()
   ```
5. **可选过滤**：丢弃失败 episode、按 success/fail 平衡、剔除超时 episode
6. **DatasetCard 写出**：把 task 元信息 + 字段 schema + 生成命令 + 总数 / 成功率写进 README

**关键纪律**
- G2 的**循环本身极简**——所有重活在 F 内部（物理 + policy 推理）；G2 只负责帧的整理 + 落盘
- 帧落盘是**逐 env、逐帧 buffer**，每条 episode 结束统一 commit（避免半截 episode 留盘上）
- 数据格式 first-class 选择**先 stub 一个内部 HDF5/Zarr**，LeRobot/RLDS converter 后接
- 并行 n_envs 自然加速数据生成：n_envs=128 时，128 条 episode 在 N 步内同时产生

**外部依赖**
- 存储后端：`h5py` / `zarr` / `lerobot.dataset.LeRobotDatasetWriter` / RLDS writer 之一
- 可选图像 codec：Pillow / imageio
