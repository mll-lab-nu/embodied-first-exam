# `topogym/robot` — 机器人控制

| 文件 | 提供什么 |
| --- | --- |
| `franka.py` | `FrankaPositionIKController` —— Franka 的关节 PD 增益配置、home 复位、末端 IK 移动、夹爪开合。是所有任务 demo 用来"发动作"的统一控制器 |

`topogym/utils/franka.py` 里的 `initialize_franka_controller` 只是一层薄封装：从 `EntityManifest` 里取出机器人实体，创建并 `configure()` 好一个 `FrankaPositionIKController`，本身不包含新的控制逻辑——真正的控制实现只在这一个模块里。

**不负责**：任务成功判定（`tasks`）；任务几何/布局生成（`generation`）。
