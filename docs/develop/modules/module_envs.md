# `topogym/envs` — RL 环境壳

面向未来 RL 训练的 Gym 风格环境封装，**目前只覆盖部分任务**，obs/reward/action 是直接写在同一个类里的，还没有接入 `generation`/`planning` 分层。

| 文件 | 提供什么 |
| --- | --- |
| `swap_mdp.py` | `SwapMdpEnv`（单进程 `gymnasium.Env`）+ `RslRlSwapAdapter`（`num_envs=1` 的 rsl-rl 适配器） |
| `onestroke_mdp.py` | `OneStrokeHighLevelEnv` / `OneStrokeHighLevelRewardWeights` |
| `maze_wall_removal_mdp.py` | `MazeWallRemovalHighLevelEnv` / `MazeWallRemovalRewardWeights` |
| `untangle_mdp.py` | `UntangleHighLevelEnv` / `UntangleHighLevelRewardWeights` / `UntangleTopologyState` |

**现状/缺口**：`cable_routing`、`peeling`、`stacked_plate` 目前没有对应的 `*_mdp.py`，也就是说这三个任务还没有 RL 环境壳。已有的几个 `*_mdp.py` 里，obs 拼装、reward 计算、action 执行都写在同一个类里（例如 `SwapMdpEnv._build_obs` / `_compute_reward` / `step`），这是当前"能跑起来"的实用写法，和 `overall_module_dict_zh.md` 里 `generation`/`planning` 那套分层还没有打通——这是下一步要做的整合，而不是已经完成的架构。

**不负责**：demo 专用调参和长脚本（`demos`）。
