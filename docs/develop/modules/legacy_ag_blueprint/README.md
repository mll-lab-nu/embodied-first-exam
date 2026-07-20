# 这是一份已过期的早期蓝图

这份 A-G 文档写在 `topogym/core / world / tasks / generation / planning / primitives / robot / supervision / runtime / utils / envs` 这套实际代码结构定型**之前**，描述的是一套更理想化的模块划分：

```text
A World Builder / B Task / C Embodiment / D Observation / E Policy
/ F Runtime / G1 Online RL / G2 Offline Data / G3 Eval
```

这套划分和当前代码**不是一一对应关系**，例如：

- 没有任何代码模块叫 `embodiment` 或 `policy`；对应的职责分散在 `topogym/robot`、`topogym/primitives`、`topogym/envs` 里。
- F 设想的是"批量 N 路并行 + Gymnasium VectorEnv + rsl-rl 双适配器"的通用 runtime；而当前 `topogym/runtime/episode_runner.py` 只是单 episode 的 build/plan/execute/verify 流程。
- G1/G2/G3（在线 RL 训练 / 离线数据生成 / 评测）目前在代码里完全不存在，`topogym/envs/*_mdp.py` 只是给个别任务（swap / onestroke / maze_wall_removal / untangle）手写的单进程 Gym 环境壳，reward/obs/action 都写在同一个类里，还没有按 A-G 设想的分层落地。

保留这几份文件，只是因为它们里面关于"未来要不要做在线 RL / 离线数据集 / 评测报告"的设想仍然有参考价值。**如果想了解当前代码到底长什么样，请去看上一级目录 `../overall_module_dict_zh.md` 和各个 `module_*.md`，不要以这几份文件为准。**
