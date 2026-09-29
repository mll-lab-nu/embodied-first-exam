# TopoGym 模拟器模块

当前已接通标准生命周期与 FEM/IPC；[真实运行结果与证据](../docs/develop/dev-logs/simulator_base_runtime_implementation_zh.md)单独记录。

- `simulator/`：make/env_list、SimulatorConfig、管理方 Env、无 reset 的操作句柄、特权查询、逐 tick 历史和 transition。
- `config/`：共享场景/相机/机器人配置、13 项任务身份和操作缺口；SimulatorConfig 的兼容导出来自 simulator/config.py。
- `world/`：Genesis 场景、唯一物理推进及状态恢复；`lab.py` 构建唯一 compact_lab，`visuals/` 接线外观与渲染。
- `robot/`：ALOHA 双臂与 Panda＋Robotiq 单臂的描述、TCP、JOINT/EE 控制模式和共享关节执行；不推进物理。
- `solvers/`：Genesis FK/IK 与独立碰撞、间隙查询。
- `sensors/`：EE/JOINT 观察、Nyx RGB、缓存和标定；默认双臂 4 路/单臂 3 路，848×480；录制默认 30 fps，共用 compact_lab。
- `tasks/`：13 个任务子目录、`common.py` 共用逻辑及 `<task>_easy/medium/hard.py` 具体设置；缺失档位有明确拒绝运行的占位文件；没有独立场景循环。
- `assets/`：任务几何和专属外观、物理材料声明、共享表面工具、机器人加载和必要资源。
- `planning/motions/`：当前被使用的 Coil 纯参考运动；不执行场景。
- `recording/`、`data/`：共享帧与真实 transition 的被动消费者。
- `evaluation/`：布面测量与连续运动间隙证书；Task 定义成功语义。
- `utils/`：通用数学、随机流、快照、数组和 I/O。
- `../legacy/cleanup_20260929/topogym/agents/deferred/`：已归档的 agent/API/rollout 源码参考，不接入、不测试、不发行。

此前 13 项基础设置有 CUDA 短程证据；本轮公共接口与回溯语义已改变，结果见[新实施报告](../docs/develop/dev-logs/simulator_public_api_implementation_20260924_zh.md)。七项未完成判据不能声明成功。`redundants/` 已删除，活动代码只有 Genesis 物理途径。

管理方可以 reset(seed=...) 切换场景。操作方只取得 `env.interaction(privileged=False/True)`，两种模式均没有 reset；特权可 rewind 当前 episode，回溯后旧未来失效。管理方 reset 使旧句柄失效，且不维护旧 episode 存档。

[本轮精简记录](../docs/develop/dev-logs/simulator_simplification_20260923_zh.md) · [当前脚本清单](../legacy/cleanup_20260929/docs/develop/dev-logs/script_inventory_zh.md) · [逐测试脚本说明](../docs/develop/dev-logs/simulator_test_scripts_zh.md)。

变体用 `make("cast_coil", variation_id="cast_coil_medium")` 选择，亦支持 `"medium"` 别名。`env_list(details=True)` 提供 `variation_details`（含占位原因）和 `base_variation`；部署状态见[实施记录](../docs/develop/tasks/variation_deployment_implementation_20260925_zh.md)。
