# 2026-09-23 逐文件迁移清单

本页列出包内全部 502 个既有非缓存文件，按新职责分组；每个旧文件只出现一次。所有链接指向新位置，源码内容没有修改。

主说明：[目录重排记录](structure_move_20260923_zh.md)；596 个缓存的精确映射另见 [完整 JSON 清单](structure_move_manifest_20260923.json)。

## 根包入口

共 1 个既有文件。

- [topogym/__init__.py](../../../topogym/__init__.py) ← `topogym/__init__.py` — 声明 topogym 包入口及其职责范围；原位保留：保留包入口，内容不变。

## config/ — 配置、任务注册、episode 合同和公开规格

共 18 个既有文件。

- [topogym/config/agent_profiles.py](../../../topogym/config/agent_profiles.py) ← `topogym/agent_rollout/profiles.py` — 定义版本化的访问模式、交互方式和 reset 策略；移动：agent 访问及交互配置。
- [topogym/config/agent_suite.py](../../../topogym/config/agent_suite.py) ← `topogym/agent_rollout/suite.py` — 冻结评测变体及来源哈希并按相同输入重载；移动：固定评测实例的准备和加载。
- [topogym/config/catalog.py](../../../topogym/config/catalog.py) ← `topogym/tasks/catalog.py` — 读取并校验 13 项任务卡及固定 baseline 清单；移动：任务身份和任务卡清单。
- [topogym/config/config.py](../../../topogym/config/config.py) ← `topogym/core/config.py` — 保存展开后的 Hydra 配置及各配置组的来源；移动：公共配置展开与来源。
- [topogym/config/episode_spec.py](../../../topogym/config/episode_spec.py) ← `topogym/generation/episode_spec.py` — 定义 episode、变体、布局、运行结果与资格字段；移动：episode 身份、配置和结果合同；混合职责原样留存。
- [topogym/config/layout_randomization.py](../../../topogym/config/layout_randomization.py) ← `topogym/generation/layout_randomization.py` — 按配置指令采样并校验任务参数；移动：配置随机化指令的统一解析。
- [topogym/config/registry.py](../../../topogym/config/registry.py) ← `topogym/agent_bridge/registry.py` — 按任务名称延迟加载 agent adapter 工厂；移动：按任务身份加载 adapter 的现有工厂。
- [topogym/config/task_specs/buzz_wire_3d.py](../../../topogym/config/task_specs/buzz_wire_3d.py) ← `topogym/tasks/buzz_wire_3d/agent_spec.py` — Buzz Wire：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/cast_coil.py](../../../topogym/config/task_specs/cast_coil.py) ← `topogym/tasks/cast_coil/agent_spec.py` — Cast Coil：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/cast_keyhole.py](../../../topogym/config/task_specs/cast_keyhole.py) ← `topogym/tasks/cast_keyhole/agent_spec.py` — Cast Keyhole：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/hedgehog_in_cage.py](../../../topogym/config/task_specs/hedgehog_in_cage.py) ← `topogym/tasks/hedgehog_in_cage/agent_spec.py` — Hedgehog：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/horseshoe_ring.py](../../../topogym/config/task_specs/horseshoe_ring.py) ← `topogym/tasks/horseshoe_ring/agent_spec.py` — Horseshoe：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/interlocked_claws.py](../../../topogym/config/task_specs/interlocked_claws.py) ← `topogym/tasks/interlocked_claws/agent_spec.py` — Claws：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/knot_untying.py](../../../topogym/config/task_specs/knot_untying.py) ← `topogym/tasks/knot_untying/agent_spec.py` — Knot：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/task_specs/lock_picking.py](../../../topogym/config/task_specs/lock_picking.py) ← `topogym/tasks/lock_picking/agent_spec.py` — Lock：声明公开任务目标及机器人和相机事实；移动：现有公开目标及机器人、相机事实声明；后续拆出真正任务目标。
- [topogym/config/tasks/cast_keyhole/family_catalog.py](../../../topogym/config/tasks/cast_keyhole/family_catalog.py) ← `topogym/tasks/cast_keyhole/family_catalog.py` — Cast Keyhole：冻结家族机制库供后续实例生成；移动：任务配置或家族注册加载。
- [topogym/config/tasks/fiber_bundling/run_config.py](../../../topogym/config/tasks/fiber_bundling/run_config.py) ← `topogym/tasks/fiber_bundling/run_config.py` — Fiber：为执行和探针载入完整且不再采样的配置；移动：任务配置或家族注册加载。
- [topogym/config/variant_episode.py](../../../topogym/config/variant_episode.py) ← `topogym/generation/variant_episode.py` — 把变体配置和指令封装为 EpisodeSpec；移动：变体配置和指令封装。

## envs/ — 环境协议、任务 adapter、初态与执行循环

共 28 个既有文件。

- [topogym/envs/adapters/base.py](../../../topogym/envs/adapters/base.py) ← `topogym/agent_bridge/adapters.py` — 提供 Genesis 单 tick 回调适配器及无物理测试任务；移动：Genesis tick 回调和测试 adapter。
- [topogym/envs/adapters/buzz_wire_3d.py](../../../topogym/envs/adapters/buzz_wire_3d.py) ← `topogym/tasks/buzz_wire_3d/agent_adapter.py` — Buzz Wire：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/cast_coil.py](../../../topogym/envs/adapters/cast_coil.py) ← `topogym/tasks/cast_coil/agent_adapter.py` — Cast Coil：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/cast_keyhole.py](../../../topogym/envs/adapters/cast_keyhole.py) ← `topogym/tasks/cast_keyhole/agent_adapter.py` — Cast Keyhole：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/fem_robot.py](../../../topogym/envs/adapters/fem_robot.py) ← `topogym/agent_bridge/fem_robot_adapter.py` — 组织 FEM 绳动作、接触选择抓持及单 tick 判定；移动：FEM 动作、抓持和步进 adapter；混合职责留待拆分。
- [topogym/envs/adapters/hedgehog_in_cage.py](../../../topogym/envs/adapters/hedgehog_in_cage.py) ← `topogym/tasks/hedgehog_in_cage/agent_adapter.py` — Hedgehog：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/horseshoe_ring.py](../../../topogym/envs/adapters/horseshoe_ring.py) ← `topogym/tasks/horseshoe_ring/agent_adapter.py` — Horseshoe：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/interlocked_claws.py](../../../topogym/envs/adapters/interlocked_claws.py) ← `topogym/tasks/interlocked_claws/agent_adapter.py` — Claws：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/knot_untying.py](../../../topogym/envs/adapters/knot_untying.py) ← `topogym/tasks/knot_untying/agent_adapter.py` — Knot：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/lock_picking.py](../../../topogym/envs/adapters/lock_picking.py) ← `topogym/tasks/lock_picking/agent_adapter.py` — Lock：把任务初始化、动作和私有判定接入 bridge；移动：各任务的环境动作与判定适配集中比较。
- [topogym/envs/adapters/rigid_robot.py](../../../topogym/envs/adapters/rigid_robot.py) ← `topogym/agent_bridge/robot_adapter.py` — 组织刚体机器人动作、抓持辅助和稳定终止判定；移动：刚体机器人动作与步进 adapter。
- [topogym/envs/episode_runner.py](../../../topogym/envs/episode_runner.py) ← `topogym/runtime/episode_runner.py` — 定义整段 episode 的运行上下文、选项与结果协议；移动：公共 episode 生命周期协议。
- [topogym/envs/execution/blanket_flatten/execution.py](../../../topogym/envs/execution/blanket_flatten/execution.py) ← `topogym/tasks/blanket_flatten/execution.py` — Blanket：管理任务连续物理执行和逐步检查；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/buzz_wire_3d/robot_runtime.py](../../../topogym/envs/execution/buzz_wire_3d/robot_runtime.py) ← `topogym/tasks/buzz_wire_3d/robot_runtime.py` — Buzz Wire：管理实测机器人控制、物理步进与接触状态；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/cast_keyhole/robot_execution.py](../../../topogym/envs/execution/cast_keyhole/robot_execution.py) ← `topogym/tasks/cast_keyhole/robot_execution.py` — Cast Keyhole：推进机器人关节控制并管理接触抓持执行；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/cast_keyhole/variant_runner.py](../../../topogym/envs/execution/cast_keyhole/variant_runner.py) ← `topogym/tasks/cast_keyhole/variant_runner.py` — Cast Keyhole：通过 EpisodeRunner 运行已指定任务实例；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/cast_keyhole/variant_runtime.py](../../../topogym/envs/execution/cast_keyhole/variant_runtime.py) ← `topogym/tasks/cast_keyhole/variant_runtime.py` — Cast Keyhole：载入指定变体并执行或构建其物理运行；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/fiber_bundling/robot_sequence.py](../../../topogym/envs/execution/fiber_bundling/robot_sequence.py) ← `topogym/tasks/fiber_bundling/robot_sequence.py` — Fiber：管理任务机器人连续操纵及抓持审计；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/hedgehog_in_cage/family_guided_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/family_guided_runtime.py) ← `topogym/tasks/hedgehog_in_cage/family_guided_runtime.py` — Hedgehog：用已检查 IK 分支引导家族物理执行；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/hedgehog_in_cage/family_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/family_runtime.py) ← `topogym/tasks/hedgehog_in_cage/family_runtime.py` — Hedgehog：构造家族场景并执行、检查和记录物理任务；移动：各任务执行循环和生命周期支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py) ← `topogym/tasks/hedgehog_in_cage/inverse_runtime.py` — Hedgehog：构造反向设计场景并执行及检查机器人运动；移动：各任务执行循环和生命周期支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/envs/execution/hedgehog_in_cage/variant_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/variant_runtime.py) ← `topogym/tasks/hedgehog_in_cage/variant_runtime.py` — Hedgehog：载入指定变体并执行或构建其物理运行；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/horseshoe_ring/physical_motion.py](../../../topogym/envs/execution/horseshoe_ring/physical_motion.py) ← `topogym/tasks/horseshoe_ring/physical_motion.py` — Horseshoe：推进关节控制并读取自由物体的物理反馈；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/execution/lock_picking/runner.py](../../../topogym/envs/execution/lock_picking/runner.py) ← `topogym/tasks/lock_picking/runner.py` — Lock：组织任务建场景、机器人执行和结果输出；移动：各任务执行循环和生命周期支线，集中后再合并。
- [topogym/envs/initialization/blanket_flatten/initial_state.py](../../../topogym/envs/initialization/blanket_flatten/initial_state.py) ← `topogym/tasks/blanket_flatten/initial_state.py` — Blanket：核对材料身份并恢复指定任务初态；移动：初态恢复、受控构造与落稳机制。
- [topogym/envs/initialization/blanket_flatten/preparation.py](../../../topogym/envs/initialization/blanket_flatten/preparation.py) ← `topogym/tasks/blanket_flatten/preparation.py` — Blanket：构造受控软体初态后释放自由落稳；移动：初态恢复、受控构造与落稳机制。
- [topogym/envs/protocol.py](../../../topogym/envs/protocol.py) ← `topogym/agent_bridge/protocol.py` — 定义 describe、动作校验、单 tick、观测和判定协议；移动：环境动作、观测和判定协议。
- [topogym/envs/task_support/cast_coil/assembly_task.py](../../../topogym/envs/task_support/cast_coil/assembly_task.py) ← `topogym/tasks/cast_coil/assembly_task.py` — Cast Coil：定义分离初态、装配阶段及装配目标；移动：混合装配初态、阶段和目标支持，留待按函数拆分。

## world/ — Genesis 世界、场景支持、物理扩展与状态

共 23 个既有文件。

- [topogym/world/__init__.py](../../../topogym/world/__init__.py) ← `topogym/world/__init__.py` — 声明 topogym/world 包入口并组织导出；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/closed_band.py](../../../topogym/world/closed_band.py) ← `topogym/world/closed_band.py` — 生成闭合弹性带并计算其几何与交叉读数；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/genesis_ipc_vertex_constraints.py](../../../topogym/world/genesis_ipc_vertex_constraints.py) ← `topogym/world/genesis_ipc_vertex_constraints.py` — 为 Genesis FEM/IPC 提供顶点固定和跟随约束；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/genesis_memory.py](../../../topogym/world/genesis_memory.py) ← `topogym/recording/adapters/genesis_memory.py` — 分块上传 Genesis 碰撞查询表以降低临时显存峰值；移动：Genesis 碰撞查询表显存管理。
- [topogym/world/lab_layout.py](../../../topogym/world/lab_layout.py) ← `topogym/world/lab_layout.py` — 定义共享实验室背景的无碰撞几何布局；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/manifest.py](../../../topogym/world/manifest.py) ← `topogym/core/manifest.py` — 维护实体名称到 Genesis 句柄的唯一映射；移动：场景实体句柄注册。
- [topogym/world/nyx_lab.py](../../../topogym/world/nyx_lab.py) ← `topogym/world/nyx_lab.py` — 把共享实验室布局加入 Genesis 场景；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/physics/buzz_wire_3d/physics.py](../../../topogym/world/physics/buzz_wire_3d/physics.py) ← `topogym/tasks/buzz_wire_3d/physics.py` — Buzz Wire：构建并检查任务物理模型和求解器设置；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/fiber_bundling/contact_precision.py](../../../topogym/world/physics/fiber_bundling/contact_precision.py) ← `topogym/tasks/fiber_bundling/contact_precision.py` — Fiber：修正毫米尺度胶囊体接触最近点计算；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/fiber_bundling/numerics.py](../../../topogym/world/physics/fiber_bundling/numerics.py) ← `topogym/tasks/fiber_bundling/numerics.py` — Fiber：声明并核查物理求解器选择；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/knot_untying/ipc_compat.py](../../../topogym/world/physics/knot_untying/ipc_compat.py) ← `topogym/tasks/knot_untying/ipc_compat.py` — Knot：适配 Genesis 与 pyuipc 的关节轴表示；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/knot_untying/runtime_memory.py](../../../topogym/world/physics/knot_untying/runtime_memory.py) ← `topogym/tasks/knot_untying/runtime_memory.py` — Knot：限制 Genesis 正向执行的历史缓存占用；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/rope_threading/deformation_damping.py](../../../topogym/world/physics/rope_threading/deformation_damping.py) ← `topogym/tasks/rope_threading/deformation_damping.py` — Rope Threading：通过 FEM 原生力加入守恒动量的耗散；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/rope_threading/mesh_resolution.py](../../../topogym/world/physics/rope_threading/mesh_resolution.py) ← `topogym/tasks/rope_threading/mesh_resolution.py` — Rope Threading：选择严格更细的软体比较网格；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/rope_threading/runtime_memory.py](../../../topogym/world/physics/rope_threading/runtime_memory.py) ← `topogym/tasks/rope_threading/runtime_memory.py` — Rope Threading：限制 Genesis 正向执行的历史缓存占用；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/physics/rope_threading/table_contact.py](../../../topogym/world/physics/rope_threading/table_contact.py) ← `topogym/tasks/rope_threading/table_contact.py` — Rope Threading：实现有限桌面范围内的原生 FEM 接触；移动：任务寄宿的 Genesis 物理设置、接触或引擎兼容支持。
- [topogym/world/rope.py](../../../topogym/world/rope.py) ← `topogym/world/rope.py` — 生成弹性绳网格并提供粒子端点与桌面摩擦辅助；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/rope_backends/__init__.py](../../../topogym/world/rope_backends/__init__.py) ← `topogym/world/rope_backends/__init__.py` — 根据绳配置选择 Genesis PBD 或 FEM/IPC 实现；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/rope_backends/fem_ipc.py](../../../topogym/world/rope_backends/fem_ipc.py) ← `topogym/world/rope_backends/fem_ipc.py` — 封装 Genesis FEM/IPC 绳材料、节点和跟随约束；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/rope_backends/pbd.py](../../../topogym/world/rope_backends/pbd.py) ← `topogym/world/rope_backends/pbd.py` — 封装 Genesis PBD 绳材料、节点和端点约束；原位保留：已有公共功能归属保留，内容不变。
- [topogym/world/scenes/buzz_wire_3d/agent_scene.py](../../../topogym/world/scenes/buzz_wire_3d/agent_scene.py) ← `topogym/tasks/buzz_wire_3d/agent_scene.py` — Buzz Wire：冻结 agent 场景资产并隐藏参考解法；移动：agent 专用场景创建支线，留待合并。
- [topogym/world/signatures.py](../../../topogym/world/signatures.py) ← `topogym/recording/signatures.py` — 计算 Genesis 或 MuJoCo 运行模型的物理签名；移动：物理模型签名；Genesis/MuJoCo 混合实现暂不拆分。
- [topogym/world/tabletop.py](../../../topogym/world/tabletop.py) ← `topogym/world/tabletop.py` — 构建共享桌面、安装机器人、配置相机并完成 Genesis build；原位保留：已有公共功能归属保留，内容不变。

## robot/ — 机器人动作端口、控制器与抓持机制

共 14 个既有文件。

- [topogym/robot/__init__.py](../../../topogym/robot/__init__.py) ← `topogym/robot/__init__.py` — 声明 topogym/robot 包入口并组织导出；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/aloha.py](../../../topogym/robot/aloha.py) ← `topogym/robot/aloha.py` — 在同一个 Genesis 机器人中管理 ALOHA 左右臂控制；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/aloha_contract.py](../../../topogym/robot/aloha_contract.py) ← `topogym/agent_bridge/aloha_contract.py` — 公开 ALOHA 动作端口并校验关节和夹爪命令；移动：ALOHA 动作端口与公开本体信息。
- [topogym/robot/factory.py](../../../topogym/robot/factory.py) ← `topogym/robot/factory.py` — 统一初始化 Franka 或 ALOHA 控制器及 home 姿态；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/franka.py](../../../topogym/robot/franka.py) ← `topogym/robot/franka.py` — 实现 Franka 的 PD、夹爪、末端 IK 和关节控制；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/grasp_constraints.py](../../../topogym/robot/grasp_constraints.py) ← `topogym/robot/grasp_constraints.py` — 查询和释放 Genesis 临时焊接抓持约束；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/grasping/attachment.py](../../../topogym/robot/grasping/attachment.py) ← `topogym/primitives/attachment.py` — 管理刚体与粒子的附件关系及位姿变换；移动：共享附着、接触和抓持机制。
- [topogym/robot/grasping/cast_coil/robot_grasp.py](../../../topogym/robot/grasping/cast_coil/robot_grasp.py) ← `topogym/tasks/cast_coil/robot_grasp.py` — Cast Coil：转发共享临时抓持约束的查询和释放函数；移动：任务抓持约束与抓持兼容端口。
- [topogym/robot/grasping/connector_latch.py](../../../topogym/robot/grasping/connector_latch.py) ← `topogym/primitives/connector_latch.py` — 管理连接器端点的锁止与附着状态；移动：共享附着、接触和抓持机制。
- [topogym/robot/grasping/fem_attachment.py](../../../topogym/robot/grasping/fem_attachment.py) ← `topogym/primitives/fem_attachment.py` — 管理 FEM/IPC 绳的抓持带附件；移动：共享附着、接触和抓持机制。
- [topogym/robot/grasping/lock_picking/grasp.py](../../../topogym/robot/grasping/lock_picking/grasp.py) ← `topogym/tasks/lock_picking/grasp.py` — Lock：对任务对象建立接触触发的临时抓持约束；移动：任务抓持约束与抓持兼容端口。
- [topogym/robot/grasping/physical_contact.py](../../../topogym/robot/grasping/physical_contact.py) ← `topogym/primitives/physical_contact.py` — 配置接触摩擦并提供实体和四元数工具；移动：共享附着、接触和抓持机制。
- [topogym/robot/gripper.py](../../../topogym/robot/gripper.py) ← `topogym/robot/gripper.py` — 把夹爪开口宽度转换为关节目标并读取指垫几何；原位保留：已有公共功能归属保留，内容不变。
- [topogym/robot/panda_contract.py](../../../topogym/robot/panda_contract.py) ← `topogym/agent_bridge/panda_contract.py` — 公开 Panda/Robotiq 动作端口并读取模型限位；移动：Panda 动作端口；MuJoCo 模型读取暂不修改；直接导入 MuJoCo，未修改。

## solvers/ — FK / IK、碰撞、几何证书与可达性检查

共 28 个既有文件。

- [topogym/solvers/collision/blanket_flatten/robot_clearance.py](../../../topogym/solvers/collision/blanket_flatten/robot_clearance.py) ← `topogym/tasks/blanket_flatten/robot_clearance.py` — Blanket：从机器人位姿检查任务物体和场景间隙；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理。
- [topogym/solvers/collision/cast_keyhole/collision.py](../../../topogym/solvers/collision/cast_keyhole/collision.py) ← `topogym/tasks/cast_keyhole/collision.py` — Cast Keyhole：执行任务形状的独立几何碰撞查询；移动：任务专有碰撞查询，集中后再提取公共算法。
- [topogym/solvers/collision/horseshoe_ring/robot_clearance.py](../../../topogym/solvers/collision/horseshoe_ring/robot_clearance.py) ← `topogym/tasks/horseshoe_ring/robot_clearance.py` — Horseshoe：从机器人位姿检查任务物体和场景间隙；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/collision/interlocked_claws/collision.py](../../../topogym/solvers/collision/interlocked_claws/collision.py) ← `topogym/tasks/interlocked_claws/collision.py` — Claws：执行任务形状的独立几何碰撞查询；移动：任务专有碰撞查询，集中后再提取公共算法。
- [topogym/solvers/collision/knot_untying/robot_clearance.py](../../../topogym/solvers/collision/knot_untying/robot_clearance.py) ← `topogym/tasks/knot_untying/robot_clearance.py` — Knot：从机器人位姿检查任务物体和场景间隙；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/collision/rope_threading/robot_mesh_guard.py](../../../topogym/solvers/collision/rope_threading/robot_mesh_guard.py) ← `topogym/tasks/rope_threading/robot_mesh_guard.py` — Rope Threading：检查实测机器人网格的自交与场景碰撞；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/geometry/buzz_wire_3d/family_witness.py](../../../topogym/solvers/geometry/buzz_wire_3d/family_witness.py) ← `topogym/tasks/buzz_wire_3d/family_witness.py` — Buzz Wire：计算完整工具路线的独立几何见证；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/cast_coil/solvability.py](../../../topogym/solvers/geometry/cast_coil/solvability.py) ← `topogym/tasks/cast_coil/solvability.py` — Cast Coil：检查任务几何可解性并生成构造性见证；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/cast_keyhole/instance_solution.py](../../../topogym/solvers/geometry/cast_keyhole/instance_solution.py) ← `topogym/tasks/cast_keyhole/instance_solution.py` — Cast Keyhole：验证当前精确初始位姿下的脱离路线；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/cast_keyhole/solution.py](../../../topogym/solvers/geometry/cast_keyhole/solution.py) ← `topogym/tasks/cast_keyhole/solution.py` — Cast Keyhole：加载并验证具有碰撞证据的任务路线；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/horseshoe_ring/independent_motion.py](../../../topogym/solvers/geometry/horseshoe_ring/independent_motion.py) ← `topogym/tasks/horseshoe_ring/independent_motion.py` — Horseshoe：连续检查任务零件独立运动的碰撞；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/horseshoe_ring/solvability.py](../../../topogym/solvers/geometry/horseshoe_ring/solvability.py) ← `topogym/tasks/horseshoe_ring/solvability.py` — Horseshoe：检查任务几何可解性并生成构造性见证；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/geometry/lock_picking/certificate.py](../../../topogym/solvers/geometry/lock_picking/certificate.py) ← `topogym/tasks/lock_picking/certificate.py` — Lock：计算任务机构路径的必要动作和区间证据；移动：几何可解性、路线证书与连续碰撞计算。
- [topogym/solvers/kinematics/blanket_flatten/bimanual_kinematics.py](../../../topogym/solvers/kinematics/blanket_flatten/bimanual_kinematics.py) ← `topogym/tasks/blanket_flatten/bimanual_kinematics.py` — Blanket：求解双臂 FK/IK 并进行采样碰撞检查；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py](../../../topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py) ← `topogym/tasks/buzz_wire_3d/robot_plan.py` — Buzz Wire：求解任务机器人 IK 路线并检查碰撞；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/cast_coil/robot_plan.py](../../../topogym/solvers/kinematics/cast_coil/robot_plan.py) ← `topogym/tasks/cast_coil/robot_plan.py` — Cast Coil：求解任务机器人 IK 路线并检查碰撞；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/cast_keyhole/robot_motion.py](../../../topogym/solvers/kinematics/cast_keyhole/robot_motion.py) ← `topogym/tasks/cast_keyhole/robot_motion.py` — Cast Keyhole：生成机器人运动学路线和末端对应关系；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/hedgehog_in_cage/plan_robot.py](../../../topogym/solvers/kinematics/hedgehog_in_cage/plan_robot.py) ← `topogym/tasks/hedgehog_in_cage/plan_robot.py` — Hedgehog：在独立运动学场景中求解机器人抓持；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理。
- [topogym/solvers/kinematics/horseshoe_ring/robot_motion.py](../../../topogym/solvers/kinematics/horseshoe_ring/robot_motion.py) ← `topogym/tasks/horseshoe_ring/robot_motion.py` — Horseshoe：生成机器人运动学路线和末端对应关系；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/knot_untying/control.py](../../../topogym/solvers/kinematics/knot_untying/control.py) ← `topogym/tasks/knot_untying/control.py` — Knot：求解带关节限位的 ALOHA 目标和坐标变换；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/orbits/robot_retarget.py](../../../topogym/solvers/kinematics/orbits/robot_retarget.py) ← `topogym/tasks/orbits/robot_retarget.py` — Orbits：在双臂接管前检查整个参考路线可达性；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/orbits/workspace.py](../../../topogym/solvers/kinematics/orbits/workspace.py) ← `topogym/tasks/orbits/workspace.py` — Orbits：检查机器人在指定场景摆放下的有限工作空间；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/rope_threading/feedback_ik_plan.py](../../../topogym/solvers/kinematics/rope_threading/feedback_ik_plan.py) ← `topogym/tasks/rope_threading/feedback_ik_plan.py` — Rope Threading：从失败快照规划并检查 R2 交接 IK；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/rope_threading/feedback_paths.py](../../../topogym/solvers/kinematics/rope_threading/feedback_paths.py) ← `topogym/tasks/rope_threading/feedback_paths.py` — Rope Threading：由实测状态生成局部交接路径并筛查可达性；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/rope_threading/ik_plan.py](../../../topogym/solvers/kinematics/rope_threading/ik_plan.py) ← `topogym/tasks/rope_threading/ik_plan.py` — Rope Threading：生成完整离线 IK 计划及几何检查；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理；直接导入 MuJoCo，未修改。
- [topogym/solvers/kinematics/rope_threading/reference_ik.py](../../../topogym/solvers/kinematics/rope_threading/reference_ik.py) ← `topogym/tasks/rope_threading/reference_ik.py` — Rope Threading：计算参考路径 IK 及受限末端姿态松弛；移动：现有 FK/IK 或碰撞求解器；保留全部后端依赖待后续处理。
- [topogym/solvers/validation/knot_untying/family_preflight.py](../../../topogym/solvers/validation/knot_untying/family_preflight.py) ← `topogym/tasks/knot_untying/family_preflight.py` — Knot：筛查家族初始抓取和首段动作可达性；移动：运动学和场景可达性预检；直接导入 MuJoCo，未修改。
- [topogym/solvers/validation/rope_threading/reference_preflight.py](../../../topogym/solvers/validation/rope_threading/reference_preflight.py) ← `topogym/tasks/rope_threading/reference_preflight.py` — Rope Threading：筛查参考动作的运动学与场景约束；移动：运动学和场景可达性预检；直接导入 MuJoCo，未修改。

## sensors/ — 相机、标定、观测及 RGB 渲染支持

共 8 个既有文件。

- [topogym/sensors/aloha_cameras.py](../../../topogym/sensors/aloha_cameras.py) ← `topogym/world/aloha_cameras.py` — 转换固定的 ALOHA 光学坐标并生成四路相机配置；移动：ALOHA 相机布局与坐标变换。
- [topogym/sensors/camera_info.py](../../../topogym/sensors/camera_info.py) ← `topogym/agent_bridge/camera_info.py` — 输出针孔相机内外参与公开标定说明；移动：公共相机标定与姿态说明。
- [topogym/sensors/cameras.py](../../../topogym/sensors/cameras.py) ← `topogym/recording/cameras.py` — 在观测前更新挂载相机的动态位姿；移动：相机挂载及动态位姿。
- [topogym/sensors/hud.py](../../../topogym/sensors/hud.py) ← `topogym/utils/hud.py` — 为诊断图像绘制文本状态覆盖层；移动：图像诊断文字叠加工具。
- [topogym/sensors/lighting.py](../../../topogym/sensors/lighting.py) ← `topogym/world/lighting.py` — 从配置构造共享灯光和可视化选项；移动：统一光照配置。
- [topogym/sensors/materials.py](../../../topogym/sensors/materials.py) ← `topogym/world/materials.py` — 提供共享表面材质及纹理兼容检查；移动：传感器渲染材质。
- [topogym/sensors/nyx.py](../../../topogym/sensors/nyx.py) ← `topogym/world/nyx.py` — 把 Nyx RGB 传感器适配为公共相机接口；移动：Nyx 传感器适配。
- [topogym/sensors/presentation.py](../../../topogym/sensors/presentation.py) ← `topogym/world/presentation.py` — 在 build 前组合背景、材质和 RGB 渲染配置；移动：RGB 渲染外观配置。

## tasks/ — 每个任务一个现有场景入口文件

共 14 个既有文件。

- [topogym/tasks/__init__.py](../../../topogym/tasks/__init__.py) ← `topogym/tasks/__init__.py` — 声明 topogym/tasks 包入口及其职责范围；原位保留：保留任务包标记。
- [topogym/tasks/blanket_flatten.py](../../../topogym/tasks/blanket_flatten.py) ← `topogym/tasks/blanket_flatten/scene.py` — Blanket：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/buzz_wire_3d.py](../../../topogym/tasks/buzz_wire_3d.py) ← `topogym/tasks/buzz_wire_3d/scene.py` — Buzz Wire：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/cast_coil.py](../../../topogym/tasks/cast_coil.py) ← `topogym/tasks/cast_coil/scene.py` — Cast Coil：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/cast_keyhole.py](../../../topogym/tasks/cast_keyhole.py) ← `topogym/tasks/cast_keyhole/scene.py` — Cast Keyhole：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/fiber_bundling.py](../../../topogym/tasks/fiber_bundling.py) ← `topogym/tasks/fiber_bundling/scene.py` — Fiber：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/hedgehog_in_cage.py](../../../topogym/tasks/hedgehog_in_cage.py) ← `topogym/tasks/hedgehog_in_cage/scene.py` — Hedgehog：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/horseshoe_ring.py](../../../topogym/tasks/horseshoe_ring.py) ← `topogym/tasks/horseshoe_ring/scene.py` — Horseshoe：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/interlocked_claws.py](../../../topogym/tasks/interlocked_claws.py) ← `topogym/tasks/interlocked_claws/scene.py` — Claws：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/knot_untying.py](../../../topogym/tasks/knot_untying.py) ← `topogym/tasks/knot_untying/scene.py` — Knot：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/lock_picking.py](../../../topogym/tasks/lock_picking.py) ← `topogym/tasks/lock_picking/scene.py` — Lock：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/orbits.py](../../../topogym/tasks/orbits.py) ← `topogym/tasks/orbits/scene.py` — Orbits：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/rope_threading.py](../../../topogym/tasks/rope_threading.py) ← `topogym/tasks/rope_threading/scene.py` — Rope Threading：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。
- [topogym/tasks/slotted_post_ring.py](../../../topogym/tasks/slotted_post_ring.py) ← `topogym/tasks/slotted_post_ring/scene.py` — Slotted Post Ring：构建任务场景、实体和初始布局；移动：现有场景声明暂作任务入口；尚未合并目标、判据或公共基类。

## assets/ — 机器人模型、任务几何、变体生成与资产加载

共 63 个既有文件。

- [topogym/assets/generators/blanket_flatten/gathered_geometry.py](../../../topogym/assets/generators/blanket_flatten/gathered_geometry.py) ← `topogym/tasks/blanket_flatten/gathered_geometry.py` — Blanket：生成连续褶皱及整体扭转的布料目标；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/blanket_flatten/geometry.py](../../../topogym/assets/generators/blanket_flatten/geometry.py) ← `topogym/tasks/blanket_flatten/geometry.py` — Blanket：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/braid.py](../../../topogym/assets/generators/braid.py) ← `topogym/generation/braid.py` — 生成绳编织词、中心线布局与几何检查结果；移动：编织初态的参数化几何生成。
- [topogym/assets/generators/buzz_wire_3d/appearance.py](../../../topogym/assets/generators/buzz_wire_3d/appearance.py) ← `topogym/tasks/buzz_wire_3d/appearance.py` — Buzz Wire：生成任务外观并保持碰撞几何边界；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/buzz_wire_3d/family_geometry.py](../../../topogym/assets/generators/buzz_wire_3d/family_geometry.py) ← `topogym/tasks/buzz_wire_3d/family_geometry.py` — Buzz Wire：生成固定任务家族的几何结构；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/buzz_wire_3d/geometry.py](../../../topogym/assets/generators/buzz_wire_3d/geometry.py) ← `topogym/tasks/buzz_wire_3d/geometry.py` — Buzz Wire：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/buzz_wire_3d/supports.py](../../../topogym/assets/generators/buzz_wire_3d/supports.py) ← `topogym/tasks/buzz_wire_3d/supports.py` — Buzz Wire：定义木支撑、机构盒体和端点支撑位姿；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/buzz_wire_3d/templates.py](../../../topogym/assets/generators/buzz_wire_3d/templates.py) ← `topogym/tasks/buzz_wire_3d/templates.py` — Buzz Wire：定义可复现的参考路径控制点；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/cast_coil/appearance.py](../../../topogym/assets/generators/cast_coil/appearance.py) ← `topogym/tasks/cast_coil/appearance.py` — Cast Coil：生成任务外观并保持碰撞几何边界；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/cast_coil/geometry.py](../../../topogym/assets/generators/cast_coil/geometry.py) ← `topogym/tasks/cast_coil/geometry.py` — Cast Coil：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/cast_keyhole/geometry.py](../../../topogym/assets/generators/cast_keyhole/geometry.py) ← `topogym/tasks/cast_keyhole/geometry.py` — Cast Keyhole：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/fiber_bundling/anchored_geometry.py](../../../topogym/assets/generators/fiber_bundling/anchored_geometry.py) ← `topogym/tasks/fiber_bundling/anchored_geometry.py` — Fiber：定义固定端、松弛引线和开放线缆支架；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/fiber_bundling/geometry.py](../../../topogym/assets/generators/fiber_bundling/geometry.py) ← `topogym/tasks/fiber_bundling/geometry.py` — Fiber：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/fiber_bundling/prepare_assets.py](../../../topogym/assets/generators/fiber_bundling/prepare_assets.py) ← `topogym/tasks/fiber_bundling/prepare_assets.py` — Fiber：离线生成任务网格、模型和几何证据；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/fiber_bundling/ring_mount.py](../../../topogym/assets/generators/fiber_bundling/ring_mount.py) ← `topogym/tasks/fiber_bundling/ring_mount.py` — Fiber：生成承重环支撑及其碰撞几何；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/hedgehog_in_cage/appearance.py](../../../topogym/assets/generators/hedgehog_in_cage/appearance.py) ← `topogym/tasks/hedgehog_in_cage/appearance.py` — Hedgehog：生成任务外观并保持碰撞几何边界；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/hedgehog_in_cage/family_geometry.py](../../../topogym/assets/generators/hedgehog_in_cage/family_geometry.py) ← `topogym/tasks/hedgehog_in_cage/family_geometry.py` — Hedgehog：生成固定任务家族的几何结构；移动：模型几何、外观与离线资产构造；直接导入 MuJoCo，未修改。
- [topogym/assets/generators/hedgehog_in_cage/geometry.py](../../../topogym/assets/generators/hedgehog_in_cage/geometry.py) ← `topogym/tasks/hedgehog_in_cage/geometry.py` — Hedgehog：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/hedgehog_in_cage/prepare_assets.py](../../../topogym/assets/generators/hedgehog_in_cage/prepare_assets.py) ← `topogym/tasks/hedgehog_in_cage/prepare_assets.py` — Hedgehog：离线生成任务网格、模型和几何证据；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/hedgehog_in_cage/prepare_prototypes.py](../../../topogym/assets/generators/hedgehog_in_cage/prepare_prototypes.py) ← `topogym/tasks/hedgehog_in_cage/prepare_prototypes.py` — Hedgehog：把已验证原型冻结为生成器的输入库；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/horseshoe_ring/geometry.py](../../../topogym/assets/generators/horseshoe_ring/geometry.py) ← `topogym/tasks/horseshoe_ring/geometry.py` — Horseshoe：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/interlocked_claws/family_models.py](../../../topogym/assets/generators/interlocked_claws/family_models.py) ← `topogym/tasks/interlocked_claws/family_models.py` — Claws：描述家族刚体形状和相对运动；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/interlocked_claws/geometry.py](../../../topogym/assets/generators/interlocked_claws/geometry.py) ← `topogym/tasks/interlocked_claws/geometry.py` — Claws：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/knot_untying/geometry.py](../../../topogym/assets/generators/knot_untying/geometry.py) ← `topogym/tasks/knot_untying/geometry.py` — Knot：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/knot_untying/prepare_assets.py](../../../topogym/assets/generators/knot_untying/prepare_assets.py) ← `topogym/tasks/knot_untying/prepare_assets.py` — Knot：离线生成任务网格、模型和几何证据；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/lock_picking/_aperture_outline.py](../../../topogym/assets/generators/lock_picking/_aperture_outline.py) ← `topogym/tasks/lock_picking/_aperture_outline.py` — Lock：绘制机构盘片开口轮廓；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/lock_picking/_staged_lock_geometry.py](../../../topogym/assets/generators/lock_picking/_staged_lock_geometry.py) ← `topogym/tasks/lock_picking/_staged_lock_geometry.py` — Lock：生成被动锁盘、自由钥匙和支座几何；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/lock_picking/_staged_lock_limits.py](../../../topogym/assets/generators/lock_picking/_staged_lock_limits.py) ← `topogym/tasks/lock_picking/_staged_lock_limits.py` — Lock：生成双面弧形限位槽及碰撞止挡；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/lock_picking/_staged_lock_ring.py](../../../topogym/assets/generators/lock_picking/_staged_lock_ring.py) ← `topogym/tasks/lock_picking/_staged_lock_ring.py` — Lock：生成固定环形框架和真实贯穿弧槽；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/orbits/geometry.py](../../../topogym/assets/generators/orbits/geometry.py) ← `topogym/tasks/orbits/geometry.py` — Orbits：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/rope_threading/geometry.py](../../../topogym/assets/generators/rope_threading/geometry.py) ← `topogym/tasks/rope_threading/geometry.py` — Rope Threading：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/rope_threading/prepare_assets.py](../../../topogym/assets/generators/rope_threading/prepare_assets.py) ← `topogym/tasks/rope_threading/prepare_assets.py` — Rope Threading：离线生成任务网格、模型和几何证据；移动：模型几何、外观与离线资产构造。
- [topogym/assets/generators/slotted_post_ring/geometry.py](../../../topogym/assets/generators/slotted_post_ring/geometry.py) ← `topogym/tasks/slotted_post_ring/geometry.py` — Slotted Post Ring：定义任务几何、坐标与资产生成；移动：模型几何、外观与离线资产构造。
- [topogym/assets/loaders/cast_keyhole/variant_assets.py](../../../topogym/assets/loaders/cast_keyhole/variant_assets.py) ← `topogym/tasks/cast_keyhole/variant_assets.py` — Cast Keyhole：按已有实体坐标加载已检查变体资产；移动：参考资产、动作或变体来源加载。
- [topogym/assets/loaders/interlocked_claws/reference.py](../../../topogym/assets/loaders/interlocked_claws/reference.py) ← `topogym/tasks/interlocked_claws/reference.py` — Claws：加载固定参考几何、坐标及来源身份；移动：参考资产、动作或变体来源加载。
- [topogym/assets/loaders/rope_threading/reference.py](../../../topogym/assets/loaders/rope_threading/reference.py) ← `topogym/tasks/rope_threading/reference.py` — Rope Threading：加载固定参考几何、坐标及来源身份；移动：参考资产、动作或变体来源加载。
- [topogym/assets/loaders/rope_threading/reference_motion.py](../../../topogym/assets/loaders/rope_threading/reference_motion.py) ← `topogym/tasks/rope_threading/reference_motion.py` — Rope Threading：读取外部参考动作并与新物理证据分离；移动：参考资产、动作或变体来源加载。
- [topogym/assets/manifests/lock_picking/source_manifest.json](../../../topogym/assets/manifests/lock_picking/source_manifest.json) ← `topogym/tasks/lock_picking/source_manifest.json` — 声明 source_manifest 的顶层数据或包标记；移动：原资产来源清单原样归入资产模块。
- [topogym/assets/robot.py](../../../topogym/assets/robot.py) ← `topogym/robot/assets.py` — 选择机器人资产并生成桌面 ALOHA 与 Panda/Robotiq 模型；移动：机器人资产选择、模型生成和缓存。
- [topogym/assets/textures.py](../../../topogym/assets/textures.py) ← `topogym/world/textures.py` — 生成织物、颜色标记及其他程序化纹理；移动：公共程序化纹理生成。
- [topogym/assets/variants/buzz_wire_3d/compact.py](../../../topogym/assets/variants/buzz_wire_3d/compact.py) ← `topogym/tasks/buzz_wire_3d/compact.py` — Buzz Wire：生成统一缩放的固定任务配置和资产；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_coil/inverse_design.py](../../../topogym/assets/variants/cast_coil/inverse_design.py) ← `topogym/tasks/cast_coil/inverse_design.py` — Cast Coil：从成功运动路线反推任务几何变体；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_coil/variants.py](../../../topogym/assets/variants/cast_coil/variants.py) ← `topogym/tasks/cast_coil/variants.py` — Cast Coil：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/eccentric_window.py](../../../topogym/assets/variants/cast_keyhole/eccentric_window.py) ← `topogym/tasks/cast_keyhole/eccentric_window.py` — Cast Keyhole：从可行运动推导偏心转向窗口；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/family_variants.py](../../../topogym/assets/variants/cast_keyhole/family_variants.py) ← `topogym/tasks/cast_keyhole/family_variants.py` — Cast Keyhole：生成固定机制家族及种子化连续外观变化；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/inverse_variants.py](../../../topogym/assets/variants/cast_keyhole/inverse_variants.py) ← `topogym/tasks/cast_keyhole/inverse_variants.py` — Cast Keyhole：从机器人运动路线生成并校验反向设计变体；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/long_stroke.py](../../../topogym/assets/variants/cast_keyhole/long_stroke.py) ← `topogym/tasks/cast_keyhole/long_stroke.py` — Cast Keyhole：从可行运动推导较长的错齿槽；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/turnback.py](../../../topogym/assets/variants/cast_keyhole/turnback.py) ← `topogym/tasks/cast_keyhole/turnback.py` — Cast Keyhole：设计并检查推进、旋转和回退机构；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/cast_keyhole/variants.py](../../../topogym/assets/variants/cast_keyhole/variants.py) ← `topogym/tasks/cast_keyhole/variants.py` — Cast Keyhole：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/fiber_bundling/generation.py](../../../topogym/assets/variants/fiber_bundling/generation.py) ← `topogym/tasks/fiber_bundling/generation.py` — Fiber：生成和重载带身份与来源信息的任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/fiber_bundling/variants.py](../../../topogym/assets/variants/fiber_bundling/variants.py) ← `topogym/tasks/fiber_bundling/variants.py` — Fiber：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/hedgehog_in_cage/classic_families.py](../../../topogym/assets/variants/hedgehog_in_cage/classic_families.py) ← `topogym/tasks/hedgehog_in_cage/classic_families.py` — Hedgehog：构建固定棘刺的侧窗及轴向孔原型；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/hedgehog_in_cage/inverse_window.py](../../../topogym/assets/variants/hedgehog_in_cage/inverse_window.py) ← `topogym/tasks/hedgehog_in_cage/inverse_window.py` — Hedgehog：改变可行 IK 路线并反推出偏心笼窗口；移动：任务实例采样、逆向设计及参数化资产生成；直接导入 MuJoCo，未修改。
- [topogym/assets/variants/hedgehog_in_cage/variants.py](../../../topogym/assets/variants/hedgehog_in_cage/variants.py) ← `topogym/tasks/hedgehog_in_cage/variants.py` — Hedgehog：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/horseshoe_ring/fixed_trace_variants.py](../../../topogym/assets/variants/horseshoe_ring/fixed_trace_variants.py) ← `topogym/tasks/horseshoe_ring/fixed_trace_variants.py` — Horseshoe：在固定轨迹下检查精确链几何变体；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/horseshoe_ring/shape_neighborhood.py](../../../topogym/assets/variants/horseshoe_ring/shape_neighborhood.py) ← `topogym/tasks/horseshoe_ring/shape_neighborhood.py` — Horseshoe：围绕参考解构造可继承几何证据的形状邻域；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/horseshoe_ring/shape_sampler.py](../../../topogym/assets/variants/horseshoe_ring/shape_sampler.py) ← `topogym/tasks/horseshoe_ring/shape_sampler.py` — Horseshoe：对耦合形状邻域采样并进行连续几何检查；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/horseshoe_ring/trace_scene_variants.py](../../../topogym/assets/variants/horseshoe_ring/trace_scene_variants.py) ← `topogym/tasks/horseshoe_ring/trace_scene_variants.py` — Horseshoe：从兼容末端轨迹反解场景参数；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/horseshoe_ring/variant_generator.py](../../../topogym/assets/variants/horseshoe_ring/variant_generator.py) ← `topogym/tasks/horseshoe_ring/variant_generator.py` — Horseshoe：生成与视频数据无关的固定任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/interlocked_claws/variants.py](../../../topogym/assets/variants/interlocked_claws/variants.py) ← `topogym/tasks/interlocked_claws/variants.py` — Claws：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/knot_untying/families.py](../../../topogym/assets/variants/knot_untying/families.py) ← `topogym/tasks/knot_untying/families.py` — Knot：定义固定结型家族模板与显式外观配置；移动：任务实例采样、逆向设计及参数化资产生成。
- [topogym/assets/variants/lock_picking/inverse_variants.py](../../../topogym/assets/variants/lock_picking/inverse_variants.py) ← `topogym/tasks/lock_picking/inverse_variants.py` — Lock：从机器人运动路线生成并校验反向设计变体；移动：任务实例采样、逆向设计及参数化资产生成；直接导入 MuJoCo，未修改。
- [topogym/assets/variants/lock_picking/variants.py](../../../topogym/assets/variants/lock_picking/variants.py) ← `topogym/tasks/lock_picking/variants.py` — Lock：按种子生成并检查参数化任务实例；移动：任务实例采样、逆向设计及参数化资产生成。

## policies/ — 动作原语、专家策略与任务路线编排

共 50 个既有文件。

- [topogym/policies/primitives/axial_insert.py](../../../topogym/policies/primitives/axial_insert.py) ← `topogym/primitives/axial_insert.py` — 沿固定轴抓取并插入零件；移动：组合机器人动作原语。
- [topogym/policies/primitives/cloth_link_attach_drag.py](../../../topogym/policies/primitives/cloth_link_attach_drag.py) ← `topogym/primitives/cloth_link_attach_drag.py` — 把布料局部附着到机器人并沿路径搬运；移动：组合机器人动作原语。
- [topogym/policies/primitives/gated_insert.py](../../../topogym/policies/primitives/gated_insert.py) ← `topogym/primitives/gated_insert.py` — 抓住板件并在触发条件满足时插入槽口；移动：组合机器人动作原语。
- [topogym/policies/primitives/gateway_extract.py](../../../topogym/policies/primitives/gateway_extract.py) ← `topogym/primitives/gateway_extract.py` — 对齐开口后沿通道抽出被抓持零件；移动：组合机器人动作原语。
- [topogym/policies/primitives/handle_drag.py](../../../topogym/policies/primitives/handle_drag.py) ← `topogym/primitives/handle_drag.py` — 抓取实体把手并执行拖动路线；移动：组合机器人动作原语。
- [topogym/policies/primitives/pbd_particle_pinch.py](../../../topogym/policies/primitives/pbd_particle_pinch.py) ← `topogym/primitives/pbd_particle_pinch.py` — 通过 PBD 粒子夹持执行提升和拖动原语；移动：组合机器人动作原语。
- [topogym/policies/primitives/pick_place.py](../../../topogym/policies/primitives/pick_place.py) ← `topogym/primitives/pick_place.py` — 执行抓取、搬运、放置及其检查；移动：组合机器人动作原语。
- [topogym/policies/primitives/pivot_lever.py](../../../topogym/policies/primitives/pivot_lever.py) ← `topogym/primitives/pivot_lever.py` — 抓住旋钮并沿圆弧转动杠杆；移动：组合机器人动作原语。
- [topogym/policies/primitives/rim_rotate.py](../../../topogym/policies/primitives/rim_rotate.py) ← `topogym/primitives/rim_rotate.py` — 沿轮缘抓持点执行旋转动作；移动：组合机器人动作原语。
- [topogym/policies/primitives/rope_endpoint_drag.py](../../../topogym/policies/primitives/rope_endpoint_drag.py) ← `topogym/primitives/rope_endpoint_drag.py` — 管理绳端抓持并执行端点拖动；移动：组合机器人动作原语。
- [topogym/policies/script_policy.py](../../../topogym/policies/script_policy.py) ← `topogym/agent_bridge/policy.py` — 校验并解释有限的 Python 动作脚本子集；移动：受限动作脚本解释器。
- [topogym/policies/subgoal.py](../../../topogym/policies/subgoal.py) ← `topogym/planning/subgoal.py` — 定义带阶段标识的规划子目标；移动：策略子目标数据结构。
- [topogym/policies/tasks/blanket_flatten/bimanual.py](../../../topogym/policies/tasks/blanket_flatten/bimanual.py) ← `topogym/tasks/blanket_flatten/bimanual.py` — Blanket：执行接触触发的 ALOHA 双臂细化控制；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/blanket_flatten/bimanual_full.py](../../../topogym/policies/tasks/blanket_flatten/bimanual_full.py) ← `topogym/tasks/blanket_flatten/bimanual_full.py` — Blanket：从指定落稳初态尝试连续双臂完整任务；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/blanket_flatten/grasp_sites.py](../../../topogym/policies/tasks/blanket_flatten/grasp_sites.py) ← `topogym/tasks/blanket_flatten/grasp_sites.py` — Blanket：从可见材料边界选择抓持与细化位置；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/blanket_flatten/robot_demo.py](../../../topogym/policies/tasks/blanket_flatten/robot_demo.py) ← `topogym/tasks/blanket_flatten/robot_demo.py` — Blanket：组织任务机器人动作、验收及录制入口；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/buzz_wire_3d/family_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/family_plan.py) ← `topogym/tasks/buzz_wire_3d/family_plan.py` — Buzz Wire：构造家族路线并搜索连续抓持 IK；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/buzz_wire_3d/home_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/home_plan.py) ← `topogym/tasks/buzz_wire_3d/home_plan.py` — Buzz Wire：为冻结路线添加经碰撞检查的 home 接近段；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/buzz_wire_3d/supported_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/supported_plan.py) ← `topogym/tasks/buzz_wire_3d/supported_plan.py` — Buzz Wire：把任务穿行路线扩展为受支撑拾取与放置；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/cast_coil/robot_demo.py](../../../topogym/policies/tasks/cast_coil/robot_demo.py) ← `topogym/tasks/cast_coil/robot_demo.py` — Cast Coil：组织任务机器人动作、验收及录制入口；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/cast_keyhole/aloha_demo.py](../../../topogym/policies/tasks/cast_keyhole/aloha_demo.py) ← `topogym/tasks/cast_keyhole/aloha_demo.py` — Cast Keyhole：组织 ALOHA 任务执行或既有轨迹回放入口；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/cast_keyhole/family_pipeline.py](../../../topogym/policies/tasks/cast_keyhole/family_pipeline.py) ← `topogym/tasks/cast_keyhole/family_pipeline.py` — Cast Keyhole：编排家族验证、执行、渲染和归档流程；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/cast_keyhole/variant_pose.py](../../../topogym/policies/tasks/cast_keyhole/variant_pose.py) ← `topogym/tasks/cast_keyhole/variant_pose.py` — Cast Keyhole：联合重定向双手并保持物体与关节一致；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/fiber_bundling/sequential.py](../../../topogym/policies/tasks/fiber_bundling/sequential.py) ← `topogym/tasks/fiber_bundling/sequential.py` — Fiber：利用固定环外侧整理线束后执行送入；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/hedgehog_in_cage/extract.py](../../../topogym/policies/tasks/hedgehog_in_cage/extract.py) ← `topogym/tasks/hedgehog_in_cage/extract.py` — Hedgehog：通过接触触发抓持执行机器人取出及共享录制；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/hedgehog_in_cage/family_motion.py](../../../topogym/policies/tasks/hedgehog_in_cage/family_motion.py) ← `topogym/tasks/hedgehog_in_cage/family_motion.py` — Hedgehog：为固定机制家族生成代表路线；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/hedgehog_in_cage/plan_escape.py](../../../topogym/policies/tasks/hedgehog_in_cage/plan_escape.py) ← `topogym/tasks/hedgehog_in_cage/plan_escape.py` — Hedgehog：搜索已检查碰撞的刚体脱离路线；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/hedgehog_in_cage/plan_release.py](../../../topogym/policies/tasks/hedgehog_in_cage/plan_release.py) ← `topogym/tasks/hedgehog_in_cage/plan_release.py` — Hedgehog：搜索脱离后可达且稳定的放置位置；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/aloha_demo.py](../../../topogym/policies/tasks/horseshoe_ring/aloha_demo.py) ← `topogym/tasks/horseshoe_ring/aloha_demo.py` — Horseshoe：组织 ALOHA 任务执行或既有轨迹回放入口；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/family_routes.py](../../../topogym/policies/tasks/horseshoe_ring/family_routes.py) ← `topogym/tasks/horseshoe_ring/family_routes.py` — Horseshoe：规划与执行空载机械手的无碰撞接近走廊；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/physical_demo.py](../../../topogym/policies/tasks/horseshoe_ring/physical_demo.py) ← `topogym/tasks/horseshoe_ring/physical_demo.py` — Horseshoe：运行带重力及接触的完整机器人任务；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/physical_extraction.py](../../../topogym/policies/tasks/horseshoe_ring/physical_extraction.py) ← `topogym/tasks/horseshoe_ring/physical_extraction.py` — Horseshoe：规划相对抽取动作并求解冗余双臂 IK；移动：专家策略、路线与动作编排，位于环境之上；直接导入 MuJoCo，未修改。
- [topogym/policies/tasks/horseshoe_ring/physical_place.py](../../../topogym/policies/tasks/horseshoe_ring/physical_place.py) ← `topogym/tasks/horseshoe_ring/physical_place.py` — Horseshoe：规划脱离物体的放置、释放和落稳；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/physical_plan.py](../../../topogym/policies/tasks/horseshoe_ring/physical_plan.py) ← `topogym/tasks/horseshoe_ring/physical_plan.py` — Horseshoe：从实测物理状态生成接触感知动作计划；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/shape_bridge.py](../../../topogym/policies/tasks/horseshoe_ring/shape_bridge.py) ← `topogym/tasks/horseshoe_ring/shape_bridge.py` — Horseshoe：修复候选形状路线中的障碍物脱离不连续段；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/variant_pipeline.py](../../../topogym/policies/tasks/horseshoe_ring/variant_pipeline.py) ← `topogym/tasks/horseshoe_ring/variant_pipeline.py` — Horseshoe：编排有界变体资格检查及实例执行；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/horseshoe_ring/witness_motion.py](../../../topogym/policies/tasks/horseshoe_ring/witness_motion.py) ← `topogym/tasks/horseshoe_ring/witness_motion.py` — Horseshoe：定义验证和位姿回放共用的几何见证运动；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/interlocked_claws/physical.py](../../../topogym/policies/tasks/interlocked_claws/physical.py) ← `topogym/tasks/interlocked_claws/physical.py` — Claws：沿固定路线执行有界机器人控制及可移除抓持；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/knot_untying/family_actions.py](../../../topogym/policies/tasks/knot_untying/family_actions.py) ← `topogym/tasks/knot_untying/family_actions.py` — Knot：执行新结型家族的状态反馈抓持路线；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/knot_untying/home_start.py](../../../topogym/policies/tasks/knot_untying/home_start.py) ← `topogym/tasks/knot_untying/home_start.py` — Knot：规划并实际执行默认姿态到抓取悬停的前缀；移动：专家策略、路线与动作编排，位于环境之上；直接导入 MuJoCo，未修改。
- [topogym/policies/tasks/knot_untying/untying.py](../../../topogym/policies/tasks/knot_untying/untying.py) ← `topogym/tasks/knot_untying/untying.py` — Knot：规划并执行持尾条件下的下层绳段抽出；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/lock_picking/oracle.py](../../../topogym/policies/tasks/lock_picking/oracle.py) ← `topogym/tasks/lock_picking/oracle.py` — Lock：用实测状态执行任务参考策略；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/lock_picking/planner.py](../../../topogym/policies/tasks/lock_picking/planner.py) ← `topogym/tasks/lock_picking/planner.py` — Lock：根据当前机构状态生成下一步任务动作；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/orbits/continuous_motion.py](../../../topogym/policies/tasks/orbits/continuous_motion.py) ← `topogym/tasks/orbits/continuous_motion.py` — Orbits：规划无碰撞笛卡尔运动并衔接同一物理状态；移动：专家策略、路线与动作编排，位于环境之上；直接导入 MuJoCo，未修改。
- [topogym/policies/tasks/orbits/robot_pickup.py](../../../topogym/policies/tasks/orbits/robot_pickup.py) ← `topogym/tasks/orbits/robot_pickup.py` — Orbits：从默认姿态连续接近并拾取绳体；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/orbits/rope_route.py](../../../topogym/policies/tasks/orbits/rope_route.py) ← `topogym/tasks/orbits/rope_route.py` — Orbits：在新绳场景执行记录的材料点路线；移动：专家策略、路线与动作编排，位于环境之上；直接导入 MuJoCo，未修改。
- [topogym/policies/tasks/orbits/solution_plan.py](../../../topogym/policies/tasks/orbits/solution_plan.py) ← `topogym/tasks/orbits/solution_plan.py` — Orbits：描述参考视频中的绳折返解法阶段；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/rope_threading/feedback_actions.py](../../../topogym/policies/tasks/rope_threading/feedback_actions.py) ← `topogym/tasks/rope_threading/feedback_actions.py` — Rope Threading：以观测驱动的交接动作替换参考路线局部阶段；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/tasks/rope_threading/reference_actions.py](../../../topogym/policies/tasks/rope_threading/reference_actions.py) ← `topogym/tasks/rope_threading/reference_actions.py` — Rope Threading：用接触触发抓持执行参考引导的机器人运动；移动：专家策略、路线与动作编排，位于环境之上。
- [topogym/policies/waypoint.py](../../../topogym/policies/waypoint.py) ← `topogym/planning/waypoint.py` — 定义路径点和 episode 计划并生成弧线与螺旋路线；移动：路径点计划及路线计算；混合职责原样留存。

## agents/ — 外层 agent 传输、会话、预算与 rollout 编排

共 21 个既有文件。

- [topogym/agents/bridge/__init__.py](../../../topogym/agents/bridge/__init__.py) ← `topogym/agent_bridge/__init__.py` — 声明 topogym/agent_bridge 包入口并组织导出；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/__main__.py](../../../topogym/agents/bridge/__main__.py) ← `topogym/agent_bridge/__main__.py` — 提供 bridge 命令行启动入口；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/budget.py](../../../topogym/agents/bridge/budget.py) ← `topogym/agent_bridge/budget.py` — 记录并校验可信 harness 的 token 使用量；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/client.py](../../../topogym/agents/bridge/client.py) ← `topogym/agent_bridge/client.py` — 提供可复用的 bridge HTTP 客户端；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/dashboard.html](../../../topogym/agents/bridge/dashboard.html) ← `topogym/agent_bridge/dashboard.html` — 提供 bridge 的浏览器控制与状态面板；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/local.py](../../../topogym/agents/bridge/local.py) ← `topogym/agent_bridge/local.py` — 启动持久 worker 并处理本地文件队列传输；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/openai_harness.py](../../../topogym/agents/bridge/openai_harness.py) ← `topogym/agent_bridge/openai_harness.py` — 通过可选 Responses 客户端驱动 agent 交互；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/package.py](../../../topogym/agents/bridge/package.py) ← `topogym/agent_bridge/package.py` — 导出不含参考解法的求解器输入包；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/server.py](../../../topogym/agents/bridge/server.py) ← `topogym/agent_bridge/server.py` — 把单线程环境会话公开为本地 HTTP 服务；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/session.py](../../../topogym/agents/bridge/session.py) ← `topogym/agent_bridge/session.py` — 管理不可回滚 episode 的分段执行、计数与媒体；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/bridge/tool_policy.py](../../../topogym/agents/bridge/tool_policy.py) ← `topogym/agent_bridge/tool_policy.py` — 声明求解 agent 的工具访问边界；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/__init__.py](../../../topogym/agents/rollout/__init__.py) ← `topogym/agent_rollout/__init__.py` — 声明 topogym/agent_rollout 包入口及其职责范围；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/__main__.py](../../../topogym/agents/rollout/__main__.py) ← `topogym/agent_rollout/__main__.py` — 提供 prepare、evaluate 和 worker 命令行入口；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/agents.py](../../../topogym/agents/rollout/agents.py) ← `topogym/agent_rollout/agents.py` — 选择 replay、command 或 Codex agent 传输实现；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/budget_proxy.py](../../../topogym/agents/rollout/budget_proxy.py) ← `topogym/agent_rollout/budget_proxy.py` — 代理模型请求并校验预留额度和实际用量；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/env_sdk.py](../../../topogym/agents/rollout/env_sdk.py) ← `topogym/agent_rollout/env_sdk.py` — 提供 agent 可调用的轻量环境查询与动作 SDK；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/episode.py](../../../topogym/agents/rollout/episode.py) ← `topogym/agent_rollout/episode.py` — 管理独立物理 worker 的启动、调用和关闭；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/isolation.py](../../../topogym/agents/rollout/isolation.py) ← `topogym/agent_rollout/isolation.py` — 构造 agent 的文件系统隔离启动命令；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/runtime.py](../../../topogym/agents/rollout/runtime.py) ← `topogym/agent_rollout/runtime.py` — 运行旧分段交互并路由工具驱动 rollout；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/token_budget.py](../../../topogym/agents/rollout/token_budget.py) ← `topogym/agent_rollout/token_budget.py` — 管理单次模型请求的 token 预留及结算；移动：agent 会话、传输或试验编排，位于本地 Env 之外。
- [topogym/agents/rollout/tool_runtime.py](../../../topogym/agents/rollout/tool_runtime.py) ← `topogym/agent_rollout/tool_runtime.py` — 管理 trial、环境服务、同预设 reset 和累计预算；移动：agent 会话、传输或试验编排，位于本地 Env 之外。

## recording/ — 公共录制与集中后的任务录制、归档支线

共 59 个既有文件。

- [topogym/recording/__init__.py](../../../topogym/recording/__init__.py) ← `topogym/recording/__init__.py` — 声明 topogym/recording 包入口并组织导出；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/__main__.py](../../../topogym/recording/__main__.py) ← `topogym/recording/__main__.py` — 提供录制预检、回放、验证和归档命令行；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/adapters/__init__.py](../../../topogym/recording/adapters/__init__.py) ← `topogym/recording/adapters/__init__.py` — 声明 topogym/recording/adapters 包入口及其职责范围；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/adapters/genesis.py](../../../topogym/recording/adapters/genesis.py) ← `topogym/recording/adapters/genesis.py` — 将 Genesis 步进、相机和显式刚体恢复接入录制；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/agent_media.py](../../../topogym/recording/agent_media.py) ← `topogym/agent_rollout/media.py` — 发布同步 segment 视频及供 agent 查看用的抽帧；移动：agent 观测片段的同步媒体发布。
- [topogym/recording/archive.py](../../../topogym/recording/archive.py) ← `topogym/recording/archive.py` — 校验收录条件并事务发布整个变体的视频和证据；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/config.py](../../../topogym/recording/config.py) ← `topogym/recording/config.py` — 组合录制外观与相机配置并冻结独立配置副本；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/contracts.py](../../../topogym/recording/contracts.py) ← `topogym/recording/contracts.py` — 定义录制身份、计划、帧、结果和引擎绑定协议；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/demo_paths.py](../../../topogym/recording/demo_paths.py) ← `topogym/utils/demo_paths.py` — 生成 task、varaition、camera 的视频发布路径；移动：视频输出路径规则。
- [topogym/recording/encoding.py](../../../topogym/recording/encoding.py) ← `topogym/recording/encoding.py` — 封装流式视频编码、ffmpeg 与解码检查；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/media.py](../../../topogym/recording/media.py) ← `topogym/recording/media.py` — 提供视频编码、抽帧和多视角拼图操作；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/migration.py](../../../topogym/recording/migration.py) ← `topogym/recording/migration.py` — 静态检查私有编码调用和共享录制接入清单；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/replay.py](../../../topogym/recording/replay.py) ← `topogym/recording/replay.py` — 按来源状态和时间线执行零积分回放；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/session.py](../../../topogym/recording/session.py) ← `topogym/recording/session.py` — 管理在线或保存状态录制的生命周期和结束结果；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/sources.py](../../../topogym/recording/sources.py) ← `topogym/recording/sources.py` — 冻结录制来源并发现和复制模型资产依赖；原位保留：已有公共功能归属保留，内容不变；直接导入 MuJoCo，未修改。
- [topogym/recording/task_adapters/blanket_flatten.py](../../../topogym/recording/task_adapters/blanket_flatten.py) ← `topogym/tasks/blanket_flatten/recording_adapter.py` — Blanket：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/buzz_wire_3d.py](../../../topogym/recording/task_adapters/buzz_wire_3d.py) ← `topogym/tasks/buzz_wire_3d/recording_adapter.py` — Buzz Wire：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/cast_coil.py](../../../topogym/recording/task_adapters/cast_coil.py) ← `topogym/tasks/cast_coil/recording_adapter.py` — Cast Coil：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/cast_keyhole.py](../../../topogym/recording/task_adapters/cast_keyhole.py) ← `topogym/tasks/cast_keyhole/recording_adapter.py` — Cast Keyhole：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/fiber_bundling.py](../../../topogym/recording/task_adapters/fiber_bundling.py) ← `topogym/tasks/fiber_bundling/recording_adapter.py` — Fiber：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/hedgehog_in_cage.py](../../../topogym/recording/task_adapters/hedgehog_in_cage.py) ← `topogym/tasks/hedgehog_in_cage/recording_adapter.py` — Hedgehog：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/horseshoe_ring.py](../../../topogym/recording/task_adapters/horseshoe_ring.py) ← `topogym/tasks/horseshoe_ring/recording_adapter.py` — Horseshoe：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/interlocked_claws.py](../../../topogym/recording/task_adapters/interlocked_claws.py) ← `topogym/tasks/interlocked_claws/recording_adapter.py` — Claws：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并；直接导入 MuJoCo，未修改。
- [topogym/recording/task_adapters/knot_untying.py](../../../topogym/recording/task_adapters/knot_untying.py) ← `topogym/tasks/knot_untying/recording_adapter.py` — Knot：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/lock_picking.py](../../../topogym/recording/task_adapters/lock_picking.py) ← `topogym/tasks/lock_picking/recording_adapter.py` — Lock：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/orbits.py](../../../topogym/recording/task_adapters/orbits.py) ← `topogym/tasks/orbits/recording_adapter.py` — Orbits：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并；直接导入 MuJoCo，未修改。
- [topogym/recording/task_adapters/rope_threading.py](../../../topogym/recording/task_adapters/rope_threading.py) ← `topogym/tasks/rope_threading/recording_adapter.py` — Rope Threading：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并。
- [topogym/recording/task_adapters/slotted_post_ring.py](../../../topogym/recording/task_adapters/slotted_post_ring.py) ← `topogym/tasks/slotted_post_ring/recording_adapter.py` — Slotted Post Ring：适配任务状态、录制绑定和共享回放来源；移动：各任务状态与录制适配集中比较，尚未合并；直接导入 MuJoCo，未修改。
- [topogym/recording/tasks/blanket_flatten/archive.py](../../../topogym/recording/tasks/blanket_flatten/archive.py) ← `topogym/tasks/blanket_flatten/archive.py` — Blanket：核验并复制任务视频和完整证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/buzz_wire_3d/archive.py](../../../topogym/recording/tasks/buzz_wire_3d/archive.py) ← `topogym/tasks/buzz_wire_3d/archive.py` — Buzz Wire：核验并复制任务视频和完整证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/buzz_wire_3d/robot_archive.py](../../../topogym/recording/tasks/buzz_wire_3d/robot_archive.py) ← `topogym/tasks/buzz_wire_3d/robot_archive.py` — Buzz Wire：校验并发布机器人执行视频和证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_coil/robot_archive.py](../../../topogym/recording/tasks/cast_coil/robot_archive.py) ← `topogym/tasks/cast_coil/robot_archive.py` — Cast Coil：校验并发布机器人执行视频和证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/archive_demo.py](../../../topogym/recording/tasks/cast_keyhole/archive_demo.py) ← `topogym/tasks/cast_keyhole/archive_demo.py` — Cast Keyhole：归档任务完整物理演示和相机视频；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/eccentric_window_archive.py](../../../topogym/recording/tasks/cast_keyhole/eccentric_window_archive.py) ← `topogym/tasks/cast_keyhole/eccentric_window_archive.py` — Cast Keyhole：校验并归档 eccentric_window 对应变体证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/family_variants_archive.py](../../../topogym/recording/tasks/cast_keyhole/family_variants_archive.py) ← `topogym/tasks/cast_keyhole/family_variants_archive.py` — Cast Keyhole：校验并归档 family_variants 对应变体证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/long_stroke_archive.py](../../../topogym/recording/tasks/cast_keyhole/long_stroke_archive.py) ← `topogym/tasks/cast_keyhole/long_stroke_archive.py` — Cast Keyhole：校验并归档 long_stroke 对应变体证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/physical_recording.py](../../../topogym/recording/tasks/cast_keyhole/physical_recording.py) ← `topogym/tasks/cast_keyhole/physical_recording.py` — Cast Keyhole：为通过审计的物理轨迹生成共享回放描述；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/turnback_archive.py](../../../topogym/recording/tasks/cast_keyhole/turnback_archive.py) ← `topogym/tasks/cast_keyhole/turnback_archive.py` — Cast Keyhole：校验并归档 turnback 对应变体证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/cast_keyhole/variant_archive.py](../../../topogym/recording/tasks/cast_keyhole/variant_archive.py) ← `topogym/tasks/cast_keyhole/variant_archive.py` — Cast Keyhole：发布已资格检查的变体完整演示；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/fiber_bundling/archive_variant.py](../../../topogym/recording/tasks/fiber_bundling/archive_variant.py) ← `topogym/tasks/fiber_bundling/archive_variant.py` — Fiber：归档单个经过独立复核的变体执行；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/fiber_bundling/render_ready.py](../../../topogym/recording/tasks/fiber_bundling/render_ready.py) ← `topogym/tasks/fiber_bundling/render_ready.py` — Fiber：在独立物理复核期间生成已完成运行的回放；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/hedgehog_in_cage/family_archive.py](../../../topogym/recording/tasks/hedgehog_in_cage/family_archive.py) ← `topogym/tasks/hedgehog_in_cage/family_archive.py` — Hedgehog：归档任务家族的独立视频及资格证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/hedgehog_in_cage/inverse_archive.py](../../../topogym/recording/tasks/hedgehog_in_cage/inverse_archive.py) ← `topogym/tasks/hedgehog_in_cage/inverse_archive.py` — Hedgehog：校验并发布反向设计实例的执行证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/hedgehog_in_cage/prepare_classic_prototypes.py](../../../topogym/recording/tasks/hedgehog_in_cage/prepare_classic_prototypes.py) ← `topogym/tasks/hedgehog_in_cage/prepare_classic_prototypes.py` — Hedgehog：归档原型物理视频并登记替换家族；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/horseshoe_ring/archive_physical.py](../../../topogym/recording/tasks/horseshoe_ring/archive_physical.py) ← `topogym/tasks/horseshoe_ring/archive_physical.py` — Horseshoe：归档经过资格检查的物理任务录像；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/horseshoe_ring/archive_timestep.py](../../../topogym/recording/tasks/horseshoe_ring/archive_timestep.py) ← `topogym/tasks/horseshoe_ring/archive_timestep.py` — Horseshoe：为已有记录保存同代码步长比较证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/horseshoe_ring/variant_video.py](../../../topogym/recording/tasks/horseshoe_ring/variant_video.py) ← `topogym/tasks/horseshoe_ring/variant_video.py` — Horseshoe：校验任务视频、哈希及其链接；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/interlocked_claws/archive.py](../../../topogym/recording/tasks/interlocked_claws/archive.py) ← `topogym/tasks/interlocked_claws/archive.py` — Claws：核验并复制任务视频和完整证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/interlocked_claws/family_archive.py](../../../topogym/recording/tasks/interlocked_claws/family_archive.py) ← `topogym/tasks/interlocked_claws/family_archive.py` — Claws：归档任务家族的独立视频及资格证据；移动：任务录制、回放和发布支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/recording/tasks/interlocked_claws/family_render.py](../../../topogym/recording/tasks/interlocked_claws/family_render.py) ← `topogym/tasks/interlocked_claws/family_render.py` — Claws：把家族历史渲染入口转接到共享回放；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/knot_untying/archive_demo.py](../../../topogym/recording/tasks/knot_untying/archive_demo.py) ← `topogym/tasks/knot_untying/archive_demo.py` — Knot：归档任务完整物理演示和相机视频；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/lock_picking/demo_archive.py](../../../topogym/recording/tasks/lock_picking/demo_archive.py) ← `topogym/tasks/lock_picking/demo_archive.py` — Lock：发布各相机独立任务演示视频；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/orbits/motion_render.py](../../../topogym/recording/tasks/orbits/motion_render.py) ← `topogym/tasks/orbits/motion_render.py` — Orbits：从实测机器人和绳状态生成共享回放；移动：任务录制、回放和发布支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/recording/tasks/orbits/robot_recording.py](../../../topogym/recording/tasks/orbits/robot_recording.py) ← `topogym/tasks/orbits/robot_recording.py` — Orbits：把机器人及软体状态接入公共录制；移动：任务录制、回放和发布支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/recording/tasks/rope_threading/archive.py](../../../topogym/recording/tasks/rope_threading/archive.py) ← `topogym/tasks/rope_threading/archive.py` — Rope Threading：核验并复制任务视频和完整证据；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/tasks/slotted_post_ring/archive.py](../../../topogym/recording/tasks/slotted_post_ring/archive.py) ← `topogym/tasks/slotted_post_ring/archive.py` — Slotted Post Ring：核验并复制任务视频和完整证据；移动：任务录制、回放和发布支线，集中后再合并；直接导入 MuJoCo，未修改。
- [topogym/recording/tasks/slotted_post_ring/curate_demos.py](../../../topogym/recording/tasks/slotted_post_ring/curate_demos.py) ← `topogym/tasks/slotted_post_ring/curate_demos.py` — Slotted Post Ring：迁移被替代的视频并修复展示引用；移动：任务录制、回放和发布支线，集中后再合并。
- [topogym/recording/timeline.py](../../../topogym/recording/timeline.py) ← `topogym/recording/timeline.py` — 按仿真时间计算视频采样点并匹配来源状态；原位保留：已有公共功能归属保留，内容不变。
- [topogym/recording/validation.py](../../../topogym/recording/validation.py) ← `topogym/recording/validation.py` — 检查录制证据、视频完整性及公共时间线；原位保留：已有公共功能归属保留，内容不变。

## data/ — 数据格式、episode 写入与轨迹导出

共 5 个既有文件。

- [topogym/data/__init__.py](../../../topogym/data/__init__.py) ← `topogym/data/__init__.py` — 声明 topogym/data 包入口并组织导出；原位保留：已有公共功能归属保留，内容不变。
- [topogym/data/episode_dataset_writer.py](../../../topogym/data/episode_dataset_writer.py) ← `topogym/data/episode_dataset_writer.py` — 采集观测与派生动作标签并写入 episode HDF5；原位保留：已有公共功能归属保留，内容不变。
- [topogym/data/exporters/horseshoe_ring/ik_trace.py](../../../topogym/data/exporters/horseshoe_ring/ik_trace.py) ← `topogym/tasks/horseshoe_ring/ik_trace.py` — Horseshoe：导出已保存运动学命令而不重新求解；移动：轨迹与执行指标导出。
- [topogym/data/exporters/knot_untying/execution_metrics.py](../../../topogym/data/exporters/knot_untying/execution_metrics.py) ← `topogym/tasks/knot_untying/execution_metrics.py` — Knot：导出实测手臂轨迹和阶段指标；移动：轨迹与执行指标导出。
- [topogym/data/h5_schema.py](../../../topogym/data/h5_schema.py) ← `topogym/data/h5_schema.py` — 声明 HDF5 观测、动作、信息字段及版本；原位保留：已有公共功能归属保留，内容不变。

## evaluation/ — 任务判据、验收、诊断和跨试验评测

共 56 个既有文件。

- [topogym/evaluation/agents/evaluate.py](../../../topogym/evaluation/agents/evaluate.py) ← `topogym/agent_rollout/evaluate.py` — 执行变体和重复试验并汇总各条件结果；移动：跨 agent、变体及重复试验统计。
- [topogym/evaluation/agents/initial.py](../../../topogym/evaluation/agents/initial.py) ← `topogym/agent_rollout/initial.py` — 审计物理初态一致性并区分图像光栅差异；移动：物理初态一致性审计。
- [topogym/evaluation/diagnostics/pbd_probe.py](../../../topogym/evaluation/diagnostics/pbd_probe.py) ← `topogym/supervision/pbd_probe.py` — 读取 PBD 粒子并安装逐步诊断探针；移动：共享物理状态诊断和稳定性检查。
- [topogym/evaluation/diagnostics/rope_stability.py](../../../topogym/evaluation/diagnostics/rope_stability.py) ← `topogym/supervision/rope_stability.py` — 检测绳粒子间距异常及数值爆炸；移动：共享物理状态诊断和稳定性检查。
- [topogym/evaluation/diagnostics/rope_trace.py](../../../topogym/evaluation/diagnostics/rope_trace.py) ← `topogym/supervision/rope_trace.py` — 记录逐步绳形、弯曲和间隙供离线诊断；移动：共享物理状态诊断和稳定性检查。
- [topogym/evaluation/diagnostics/stability.py](../../../topogym/evaluation/diagnostics/stability.py) ← `topogym/supervision/stability.py` — 依据通用阈值判定状态稳定性及软中止原因；移动：共享物理状态诊断和稳定性检查。
- [topogym/evaluation/tasks/blanket_flatten/bimanual_review.py](../../../topogym/evaluation/tasks/blanket_flatten/bimanual_review.py) ← `topogym/tasks/blanket_flatten/bimanual_review.py` — Blanket：离散审查双臂关节、相机和布料轨迹；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/blanket_flatten/diagnostics.py](../../../topogym/evaluation/tasks/blanket_flatten/diagnostics.py) ← `topogym/tasks/blanket_flatten/diagnostics.py` — Blanket：测量任务状态并执行数值或表面诊断；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/blanket_flatten/review_preparation.py](../../../topogym/evaluation/tasks/blanket_flatten/review_preparation.py) ← `topogym/tasks/blanket_flatten/review_preparation.py` — Blanket：检查初态构造后的网格及端部转角；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/buzz_wire_3d/qualification.py](../../../topogym/evaluation/tasks/buzz_wire_3d/qualification.py) ← `topogym/tasks/buzz_wire_3d/qualification.py` — Buzz Wire：汇总输入身份和物理验收证据；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/buzz_wire_3d/robot_verify.py](../../../topogym/evaluation/tasks/buzz_wire_3d/robot_verify.py) ← `topogym/tasks/buzz_wire_3d/robot_verify.py` — Buzz Wire：比较标称与减半步长的机器人完整执行；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/buzz_wire_3d/verification.py](../../../topogym/evaluation/tasks/buzz_wire_3d/verification.py) ← `topogym/tasks/buzz_wire_3d/verification.py` — Buzz Wire：验证任务几何或实测执行证据；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/buzz_wire_3d/verify_physics.py](../../../topogym/evaluation/tasks/buzz_wire_3d/verify_physics.py) ← `topogym/tasks/buzz_wire_3d/verify_physics.py` — Buzz Wire：比较两种积分步长的完整物理对照；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/cast_coil/qualify.py](../../../topogym/evaluation/tasks/cast_coil/qualify.py) ← `topogym/tasks/cast_coil/qualify.py` — Cast Coil：汇总物理对照结果并判定当前任务资格；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/cast_coil/verification.py](../../../topogym/evaluation/tasks/cast_coil/verification.py) ← `topogym/tasks/cast_coil/verification.py` — Cast Coil：验证任务几何或实测执行证据；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/cast_keyhole/family_suite.py](../../../topogym/evaluation/tasks/cast_keyhole/family_suite.py) ← `topogym/tasks/cast_keyhole/family_suite.py` — Cast Keyhole：核对家族库清单和固定种子复现；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/cast_keyhole/physical_audit.py](../../../topogym/evaluation/tasks/cast_keyhole/physical_audit.py) ← `topogym/tasks/cast_keyhole/physical_audit.py` — Cast Keyhole：独立检查保存的物理状态及导出资格；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/cast_keyhole/qualify.py](../../../topogym/evaluation/tasks/cast_keyhole/qualify.py) ← `topogym/tasks/cast_keyhole/qualify.py` — Cast Keyhole：汇总物理对照结果并判定当前任务资格；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/anchored_verifier.py](../../../topogym/evaluation/tasks/fiber_bundling/anchored_verifier.py) ← `topogym/tasks/fiber_bundling/anchored_verifier.py` — Fiber：检查固定连接线缆的方向性穿环目标；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/fiber_bundling/assess_anchored.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_anchored.py) ← `topogym/tasks/fiber_bundling/assess_anchored.py` — Fiber：比较并验收 anchored 的独立执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/assess_ik.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_ik.py) ← `topogym/tasks/fiber_bundling/assess_ik.py` — Fiber：比较并验收 ik 的独立执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/assess_passage.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_passage.py) ← `topogym/tasks/fiber_bundling/assess_passage.py` — Fiber：比较并验收 passage 的独立执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/assess_sequence.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_sequence.py) ← `topogym/tasks/fiber_bundling/assess_sequence.py` — Fiber：比较并验收 sequence 的独立执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/assess_stability.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_stability.py) ← `topogym/tasks/fiber_bundling/assess_stability.py` — Fiber：比较并验收 stability 的独立执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/audit_robot_contacts.py](../../../topogym/evaluation/tasks/fiber_bundling/audit_robot_contacts.py) ← `topogym/tasks/fiber_bundling/audit_robot_contacts.py` — Fiber：在保存位姿重算机器人接触以供诊断；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/contact_guard.py](../../../topogym/evaluation/tasks/fiber_bundling/contact_guard.py) ← `topogym/tasks/fiber_bundling/contact_guard.py` — Fiber：检测并锁存夹爪与细线禁碰失败；移动：任务禁碰失败判据。
- [topogym/evaluation/tasks/fiber_bundling/summarize_ik.py](../../../topogym/evaluation/tasks/fiber_bundling/summarize_ik.py) ← `topogym/tasks/fiber_bundling/summarize_ik.py` — Fiber：汇总 ik 的实际执行结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/validation.py](../../../topogym/evaluation/tasks/fiber_bundling/validation.py) ← `topogym/tasks/fiber_bundling/validation.py` — Fiber：检查有限半径绳或线束模型的数值稳定性；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/fiber_bundling/variant_progress.py](../../../topogym/evaluation/tasks/fiber_bundling/variant_progress.py) ← `topogym/tasks/fiber_bundling/variant_progress.py` — Fiber：汇总已录制变体的实际进度；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/hedgehog_in_cage/audit.py](../../../topogym/evaluation/tasks/hedgehog_in_cage/audit.py) ← `topogym/tasks/hedgehog_in_cage/audit.py` — Hedgehog：审计已保存执行及其证据一致性；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/hedgehog_in_cage/variant_validation.py](../../../topogym/evaluation/tasks/hedgehog_in_cage/variant_validation.py) ← `topogym/tasks/hedgehog_in_cage/variant_validation.py` — Hedgehog：验证采样实例的几何与机器人预检；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/horseshoe_ring/trace_scene_verification.py](../../../topogym/evaluation/tasks/horseshoe_ring/trace_scene_verification.py) ← `topogym/tasks/horseshoe_ring/trace_scene_verification.py` — Horseshoe：核对导出逆场景与认证几何相似变换；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/horseshoe_ring/variant_audit.py](../../../topogym/evaluation/tasks/horseshoe_ring/variant_audit.py) ← `topogym/tasks/horseshoe_ring/variant_audit.py` — Horseshoe：去除尺度和时间影响后比较变体路线；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/horseshoe_ring/verify_gravity.py](../../../topogym/evaluation/tasks/horseshoe_ring/verify_gravity.py) ← `topogym/tasks/horseshoe_ring/verify_gravity.py` — Horseshoe：用自由落体、零重力和步长对照检查重力行为；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/horseshoe_ring/verify_physical.py](../../../topogym/evaluation/tasks/horseshoe_ring/verify_physical.py) ← `topogym/tasks/horseshoe_ring/verify_physical.py` — Horseshoe：验收重力完整执行并比较复现实验；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/interlocked_claws/reference_audit.py](../../../topogym/evaluation/tasks/interlocked_claws/reference_audit.py) ← `topogym/tasks/interlocked_claws/reference_audit.py` — Claws：审计参考动作与测得物理路径的一致性；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/interlocked_claws/reliability.py](../../../topogym/evaluation/tasks/interlocked_claws/reliability.py) ← `topogym/tasks/interlocked_claws/reliability.py` — Claws：汇总任务成功、失败与未完成试验的证据；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/interlocked_claws/verification.py](../../../topogym/evaluation/tasks/interlocked_claws/verification.py) ← `topogym/tasks/interlocked_claws/verification.py` — Claws：验证任务几何或实测执行证据；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/knot_untying/diagnostics.py](../../../topogym/evaluation/tasks/knot_untying/diagnostics.py) ← `topogym/tasks/knot_untying/diagnostics.py` — Knot：测量任务状态并执行数值或表面诊断；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/knot_untying/physics_review.py](../../../topogym/evaluation/tasks/knot_untying/physics_review.py) ← `topogym/tasks/knot_untying/physics_review.py` — Knot：汇总已完成与未完成物理检查为报告；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/knot_untying/rigid_diagnostics.py](../../../topogym/evaluation/tasks/knot_untying/rigid_diagnostics.py) ← `topogym/tasks/knot_untying/rigid_diagnostics.py` — Knot：检查 FEM 与实际 IPC 刚体表面的扫掠接触；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/lock_picking/evaluator.py](../../../topogym/evaluation/tasks/lock_picking/evaluator.py) ← `topogym/tasks/lock_picking/evaluator.py` — Lock：判断任务目标及实测执行有效性；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/lock_picking/verify_variants.py](../../../topogym/evaluation/tasks/lock_picking/verify_variants.py) ← `topogym/tasks/lock_picking/verify_variants.py` — Lock：检查变体生成器的复现和几何不变量；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/orbits/grasp_audit.py](../../../topogym/evaluation/tasks/orbits/grasp_audit.py) ← `topogym/tasks/orbits/grasp_audit.py` — Orbits：核查录制抓持辅助期间的真实手指接触；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/orbits/passage_audit.py](../../../topogym/evaluation/tasks/orbits/passage_audit.py) ← `topogym/tasks/orbits/passage_audit.py` — Orbits：区分材料真实穿孔与从孔外绕过；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/orbits/reference_audit.py](../../../topogym/evaluation/tasks/orbits/reference_audit.py) ← `topogym/tasks/orbits/reference_audit.py` — Orbits：审计参考动作与测得物理路径的一致性；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/orbits/rope_audit.py](../../../topogym/evaluation/tasks/orbits/rope_audit.py) ← `topogym/tasks/orbits/rope_audit.py` — Orbits：检查实测绳状态及保守脱离条件；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/orbits/trajectory_audit.py](../../../topogym/evaluation/tasks/orbits/trajectory_audit.py) ← `topogym/tasks/orbits/trajectory_audit.py` — Orbits：审计记录轨迹中的离散物理状态；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/orbits/verification.py](../../../topogym/evaluation/tasks/orbits/verification.py) ← `topogym/tasks/orbits/verification.py` — Orbits：验证任务几何或实测执行证据；移动：任务几何、成功或穿越判据，留待回接任务入口。
- [topogym/evaluation/tasks/rope_threading/diagnostics.py](../../../topogym/evaluation/tasks/rope_threading/diagnostics.py) ← `topogym/tasks/rope_threading/diagnostics.py` — Rope Threading：测量任务状态并执行数值或表面诊断；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/rope_threading/physics_review.py](../../../topogym/evaluation/tasks/rope_threading/physics_review.py) ← `topogym/tasks/rope_threading/physics_review.py` — Rope Threading：汇总已完成与未完成物理检查为报告；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/rope_threading/qualification.py](../../../topogym/evaluation/tasks/rope_threading/qualification.py) ← `topogym/tasks/rope_threading/qualification.py` — Rope Threading：汇总输入身份和物理验收证据；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/rope_threading/startup_diagnostics.py](../../../topogym/evaluation/tasks/rope_threading/startup_diagnostics.py) ← `topogym/tasks/rope_threading/startup_diagnostics.py` — Rope Threading：记录初始化阶段的额外状态观测；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/rope_threading/startup_review.py](../../../topogym/evaluation/tasks/rope_threading/startup_review.py) ← `topogym/tasks/rope_threading/startup_review.py` — Rope Threading：汇总初始化与弹性实验结果；移动：任务验收、诊断或评测汇总。
- [topogym/evaluation/tasks/slotted_post_ring/review_fem.py](../../../topogym/evaluation/tasks/slotted_post_ring/review_fem.py) ← `topogym/tasks/slotted_post_ring/review_fem.py` — Slotted Post Ring：审查 FEM 形变和保存证据的一致性；移动：任务验收、诊断或评测汇总；直接导入 MuJoCo，未修改。
- [topogym/evaluation/tasks/slotted_post_ring/topology.py](../../../topogym/evaluation/tasks/slotted_post_ring/topology.py) ← `topogym/tasks/slotted_post_ring/topology.py` — Slotted Post Ring：读取沿实测绳的有序孔洞穿越关系；移动：任务几何、成功或穿越判据，留待回接任务入口。

## utils/ — 公共 I/O、随机流和几何数学工具

共 5 个既有文件。

- [topogym/utils/__init__.py](../../../topogym/utils/__init__.py) ← `topogym/utils/__init__.py` — 声明 topogym/utils 包入口并组织导出；原位保留：已有公共功能归属保留，内容不变。
- [topogym/utils/geometry/rigid_geometry.py](../../../topogym/utils/geometry/rigid_geometry.py) ← `topogym/tasks/_rigid_geometry.py` — 提供任务间共享的刚体网格、环几何和链接数工具；移动：共享网格、刚体几何和数学工具。
- [topogym/utils/geometry/rope_crossings.py](../../../topogym/utils/geometry/rope_crossings.py) ← `topogym/planning/rope_crossings.py` — 计算绳交叉、顺序编码及其变化；移动：公共绳交叉数学和解析工具。
- [topogym/utils/io.py](../../../topogym/utils/io.py) ← `topogym/recording/io.py` — 提供 JSON、哈希、来源版本和受限路径工具；移动：JSON、哈希、来源和路径公共工具。
- [topogym/utils/variant_rng.py](../../../topogym/utils/variant_rng.py) ← `topogym/generation/variant_rng.py` — 由 seed 和名称派生独立且可重复的随机流；移动：公共确定性随机流工具。

## redundants/ — 后端隔离、兼容层、实验、展示和旧目录标记

共 109 个既有文件。

- [topogym/redundants/benchmarks/step_bench.py](../../../topogym/redundants/benchmarks/step_bench.py) ← `topogym/supervision/step_bench.py` — 测量物理单步开销或在正式执行前停止；移动：构建与物理单步性能检查。
- [topogym/redundants/checks/fiber_bundling/contact_rule_probe.py](../../../topogym/redundants/checks/fiber_bundling/contact_rule_probe.py) ← `topogym/tasks/fiber_bundling/contact_rule_probe.py` — Fiber：回归检查机器人禁碰与终止规则；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/compatibility/recording/compatibility.py](../../../topogym/redundants/compatibility/recording/compatibility.py) ← `topogym/recording/compatibility.py` — 把公共录制结果导出到旧开发视频布局；移动：旧目录布局兼容导出。
- [topogym/redundants/compatibility/recording/compatibility_recorder.py](../../../topogym/redundants/compatibility/recording/compatibility_recorder.py) ← `topogym/recording/compatibility_recorder.py` — 保留旧按步长采帧的兼容录制实现；移动：旧采帧循环兼容实现。
- [topogym/redundants/compatibility/utils/franka.py](../../../topogym/redundants/compatibility/utils/franka.py) ← `topogym/utils/franka.py` — 通过旧接口初始化共享 Franka 控制器；移动：旧机器人初始化兼容转发。
- [topogym/redundants/compatibility/utils/recording.py](../../../topogym/redundants/compatibility/utils/recording.py) ← `topogym/utils/recording.py` — 转发历史录制名称到共享 recording 模块；移动：旧录制名称兼容转发。
- [topogym/redundants/documentation/tasks_README.md](../../../topogym/redundants/documentation/tasks_README.md) ← `topogym/tasks/README.md` — 声明 README 的顶层数据或包标记；移动：保留旧任务目录说明，避免与新结构混淆。
- [topogym/redundants/experiments/blanket_flatten/preview.py](../../../topogym/redundants/experiments/blanket_flatten/preview.py) ← `topogym/tasks/blanket_flatten/preview.py` — Blanket：生成资产并检查初始场景及落稳状态；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/blanket_flatten/virtual_hands.py](../../../topogym/redundants/experiments/blanket_flatten/virtual_hands.py) ← `topogym/tasks/blanket_flatten/virtual_hands.py` — Blanket：使用外部驱动的两个材料抓持点执行操纵；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/buzz_wire_3d/preview.py](../../../topogym/redundants/experiments/buzz_wire_3d/preview.py) ← `topogym/tasks/buzz_wire_3d/preview.py` — Buzz Wire：生成资产并检查初始场景及落稳状态；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/buzz_wire_3d/probe.py](../../../topogym/redundants/experiments/buzz_wire_3d/probe.py) ← `topogym/tasks/buzz_wire_3d/probe.py` — Buzz Wire：构建或执行任务物理探针；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_coil/demo.py](../../../topogym/redundants/experiments/cast_coil/demo.py) ← `topogym/tasks/cast_coil/demo.py` — Cast Coil：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_coil/official_trial.py](../../../topogym/redundants/experiments/cast_coil/official_trial.py) ← `topogym/tasks/cast_coil/official_trial.py` — Cast Coil：搜索参考解法的尺度解释及可行区间；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_coil/physics_probe.py](../../../topogym/redundants/experiments/cast_coil/physics_probe.py) ← `topogym/tasks/cast_coil/physics_probe.py` — Cast Coil：运行任务物理稳定性和接触对照实验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_keyhole/demo.py](../../../topogym/redundants/experiments/cast_keyhole/demo.py) ← `topogym/tasks/cast_keyhole/demo.py` — Cast Keyhole：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_keyhole/physics_probe.py](../../../topogym/redundants/experiments/cast_keyhole/physics_probe.py) ← `topogym/tasks/cast_keyhole/physics_probe.py` — Cast Keyhole：运行任务物理稳定性和接触对照实验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_keyhole/route_probe.py](../../../topogym/redundants/experiments/cast_keyhole/route_probe.py) ← `topogym/tasks/cast_keyhole/route_probe.py` — Cast Keyhole：探索局部几何路线并报告未通过条件；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/cast_keyhole/trajectory_probe.py](../../../topogym/redundants/experiments/cast_keyhole/trajectory_probe.py) ← `topogym/tasks/cast_keyhole/trajectory_probe.py` — Cast Keyhole：以公开外力对照跟踪完整任务路线；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/anchored_probe.py](../../../topogym/redundants/experiments/fiber_bundling/anchored_probe.py) ← `topogym/tasks/fiber_bundling/anchored_probe.py` — Fiber：检查固定端连接和支撑受力；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/capsule_contact_probe.py](../../../topogym/redundants/experiments/fiber_bundling/capsule_contact_probe.py) ← `topogym/tasks/fiber_bundling/capsule_contact_probe.py` — Fiber：检查隔离胶囊体接触计算；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/demo.py](../../../topogym/redundants/experiments/fiber_bundling/demo.py) ← `topogym/tasks/fiber_bundling/demo.py` — Fiber：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/ik_search.py](../../../topogym/redundants/experiments/fiber_bundling/ik_search.py) ← `topogym/tasks/fiber_bundling/ik_search.py` — Fiber：探索完整线束的 IK 与接触反馈策略；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/ik_turn_probe.py](../../../topogym/redundants/experiments/fiber_bundling/ik_turn_probe.py) ← `topogym/tasks/fiber_bundling/ik_turn_probe.py` — Fiber：从保存状态检查不同转向 IK；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/parallel_recheck.py](../../../topogym/redundants/experiments/fiber_bundling/parallel_recheck.py) ← `topogym/tasks/fiber_bundling/parallel_recheck.py` — Fiber：独立复核尚在运行的基线控制器；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/probe.py](../../../topogym/redundants/experiments/fiber_bundling/probe.py) ← `topogym/tasks/fiber_bundling/probe.py` — Fiber：构建或执行任务物理探针；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/refined_variant_trial.py](../../../topogym/redundants/experiments/fiber_bundling/refined_variant_trial.py) ← `topogym/tasks/fiber_bundling/refined_variant_trial.py` — Fiber：以更小步长复核同一变体控制器；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/single_strand.py](../../../topogym/redundants/experiments/fiber_bundling/single_strand.py) ← `topogym/tasks/fiber_bundling/single_strand.py` — Fiber：仅通过粗线根部动作整理单根被动细线；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/snapshot_trial.py](../../../topogym/redundants/experiments/fiber_bundling/snapshot_trial.py) ← `topogym/tasks/fiber_bundling/snapshot_trial.py` — Fiber：从 baseline/source 动态加载冻结代码执行复核；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/variant_demo.py](../../../topogym/redundants/experiments/fiber_bundling/variant_demo.py) ← `topogym/tasks/fiber_bundling/variant_demo.py` — Fiber：编排单变体执行、复核与归档；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/fiber_bundling/variant_trial.py](../../../topogym/redundants/experiments/fiber_bundling/variant_trial.py) ← `topogym/tasks/fiber_bundling/variant_trial.py` — Fiber：以指定步长运行固定变体；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/hedgehog_in_cage/demo.py](../../../topogym/redundants/experiments/hedgehog_in_cage/demo.py) ← `topogym/tasks/hedgehog_in_cage/demo.py` — Hedgehog：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/hedgehog_in_cage/side_window_probe.py](../../../topogym/redundants/experiments/hedgehog_in_cage/side_window_probe.py) ← `topogym/tasks/hedgehog_in_cage/side_window_probe.py` — Hedgehog：扫描固定棘刺经过圆角侧窗的几何宽度；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/hedgehog_in_cage/stability.py](../../../topogym/redundants/experiments/hedgehog_in_cage/stability.py) ← `topogym/tasks/hedgehog_in_cage/stability.py` — Hedgehog：执行自由体稳定性与受力对照；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/chain_probe.py](../../../topogym/redundants/experiments/horseshoe_ring/chain_probe.py) ← `topogym/tasks/horseshoe_ring/chain_probe.py` — Horseshoe：构造三个仅通过几何接触连接的闭环；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/demo.py](../../../topogym/redundants/experiments/horseshoe_ring/demo.py) ← `topogym/tasks/horseshoe_ring/demo.py` — Horseshoe：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/experiments.py](../../../topogym/redundants/experiments/horseshoe_ring/experiments.py) ← `topogym/tasks/horseshoe_ring/experiments.py` — Horseshoe：执行环尺寸等几何控制例扫描；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/family_space.py](../../../topogym/redundants/experiments/horseshoe_ring/family_space.py) ← `topogym/tasks/horseshoe_ring/family_space.py` — Horseshoe：展示并审计家族参数空间和代表候选；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/gravity_demo.py](../../../topogym/redundants/experiments/horseshoe_ring/gravity_demo.py) ← `topogym/tasks/horseshoe_ring/gravity_demo.py` — Horseshoe：执行启用重力的双臂保持及旧轨迹物理检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/shape_variants.py](../../../topogym/redundants/experiments/horseshoe_ring/shape_variants.py) ← `topogym/tasks/horseshoe_ring/shape_variants.py` — Horseshoe：探索形状、链长和目标椭圆的耦合变体；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/horseshoe_ring/witness_demo.py](../../../topogym/redundants/experiments/horseshoe_ring/witness_demo.py) ← `topogym/tasks/horseshoe_ring/witness_demo.py` — Horseshoe：在共享场景检查几何控制例端点；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/interlocked_claws/contact_probe.py](../../../topogym/redundants/experiments/interlocked_claws/contact_probe.py) ← `topogym/tasks/interlocked_claws/contact_probe.py` — Claws：运行特定接触、滑动与释放对照试验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/interlocked_claws/demo.py](../../../topogym/redundants/experiments/interlocked_claws/demo.py) ← `topogym/tasks/interlocked_claws/demo.py` — Claws：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/interlocked_claws/family_space.py](../../../topogym/redundants/experiments/interlocked_claws/family_space.py) ← `topogym/tasks/interlocked_claws/family_space.py` — Claws：展示并审计家族参数空间和代表候选；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/contact_probe.py](../../../topogym/redundants/experiments/knot_untying/contact_probe.py) ← `topogym/tasks/knot_untying/contact_probe.py` — Knot：运行特定接触、滑动与释放对照试验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/demo.py](../../../topogym/redundants/experiments/knot_untying/demo.py) ← `topogym/tasks/knot_untying/demo.py` — Knot：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/physics_probe.py](../../../topogym/redundants/experiments/knot_untying/physics_probe.py) ← `topogym/tasks/knot_untying/physics_probe.py` — Knot：运行任务物理稳定性和接触对照实验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/physics_suite.py](../../../topogym/redundants/experiments/knot_untying/physics_suite.py) ← `topogym/tasks/knot_untying/physics_suite.py` — Knot：运行物理检查矩阵并在失败门槛停止；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/probe_actions.py](../../../topogym/redundants/experiments/knot_untying/probe_actions.py) ← `topogym/tasks/knot_untying/probe_actions.py` — Knot：声明局部加载和卸载实验的软抓持动作；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/knot_untying/robot_probe.py](../../../topogym/redundants/experiments/knot_untying/robot_probe.py) ← `topogym/tasks/knot_untying/robot_probe.py` — Knot：测试机器人抓持、提升、双手交接与释放；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/lock_picking/family_space.py](../../../topogym/redundants/experiments/lock_picking/family_space.py) ← `topogym/tasks/lock_picking/family_space.py` — Lock：展示并审计家族参数空间和代表候选；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/orbits/bimanual_bight_demo.py](../../../topogym/redundants/experiments/orbits/bimanual_bight_demo.py) ← `topogym/tasks/orbits/bimanual_bight_demo.py` — Orbits：实验性执行双臂绳折返段展开；移动：专用实验、展示或研究检查；原样保留待筛选；直接导入 MuJoCo，未修改。
- [topogym/redundants/experiments/orbits/grasp_demo.py](../../../topogym/redundants/experiments/orbits/grasp_demo.py) ← `topogym/tasks/orbits/grasp_demo.py` — Orbits：从明确预抓取初态执行双臂抓持提升；移动：专用实验、展示或研究检查；原样保留待筛选；直接导入 MuJoCo，未修改。
- [topogym/redundants/experiments/orbits/preview.py](../../../topogym/redundants/experiments/orbits/preview.py) ← `topogym/tasks/orbits/preview.py` — Orbits：生成资产并检查初始场景及落稳状态；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/orbits/rope_only_demo.py](../../../topogym/redundants/experiments/orbits/rope_only_demo.py) ← `topogym/tasks/orbits/rope_only_demo.py` — Orbits：执行无机器人的完整材料点驱动路线；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/orbits/two_control_route.py](../../../topogym/redundants/experiments/orbits/two_control_route.py) ← `topogym/tasks/orbits/two_control_route.py` — Orbits：以两个外部控制点适配完整参考路线；移动：专用实验、展示或研究检查；原样保留待筛选；直接导入 MuJoCo，未修改。
- [topogym/redundants/experiments/rope_threading/contact_probe.py](../../../topogym/redundants/experiments/rope_threading/contact_probe.py) ← `topogym/tasks/rope_threading/contact_probe.py` — Rope Threading：运行特定接触、滑动与释放对照试验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/rope_threading/demo.py](../../../topogym/redundants/experiments/rope_threading/demo.py) ← `topogym/tasks/rope_threading/demo.py` — Rope Threading：加载任务初态并进行静态或短程检查；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/rope_threading/physics_probe.py](../../../topogym/redundants/experiments/rope_threading/physics_probe.py) ← `topogym/tasks/rope_threading/physics_probe.py` — Rope Threading：运行任务物理稳定性和接触对照实验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/rope_threading/physics_suite.py](../../../topogym/redundants/experiments/rope_threading/physics_suite.py) ← `topogym/tasks/rope_threading/physics_suite.py` — Rope Threading：运行物理检查矩阵并在失败门槛停止；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/rope_threading/startup_study.py](../../../topogym/redundants/experiments/rope_threading/startup_study.py) ← `topogym/tasks/rope_threading/startup_study.py` — Rope Threading：串行执行受控初始化实验；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/experiments/slotted_post_ring/preview.py](../../../topogym/redundants/experiments/slotted_post_ring/preview.py) ← `topogym/tasks/slotted_post_ring/preview.py` — Slotted Post Ring：生成资产并检查初始场景及落稳状态；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/mujoco/recording/adapters/mujoco.py](../../../topogym/redundants/mujoco/recording/adapters/mujoco.py) ← `topogym/recording/adapters/mujoco.py` — 恢复 MuJoCo 状态并使用其渲染器生成回放帧；移动：MuJoCo 专属渲染与状态恢复；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/interlocked_claws/family_balanced_robot.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_balanced_robot.py) ← `topogym/tasks/interlocked_claws/family_balanced_robot.py` — Claws：规划两臂顺序释放并构建家族执行模型；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/interlocked_claws/family_physics.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_physics.py) ← `topogym/tasks/interlocked_claws/family_physics.py` — Claws：在 MuJoCo 中运行家族接触和落稳试验；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/interlocked_claws/family_robot.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_robot.py) ← `topogym/tasks/interlocked_claws/family_robot.py` — Claws：构造并执行家族机器人 IK 和受力限制流程；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/orbits/dynamics.py](../../../topogym/redundants/mujoco/tasks/orbits/dynamics.py) ← `topogym/tasks/orbits/dynamics.py` — Orbits：构造 MuJoCo 绳模型并推进和保存物理状态；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/orbits/robot_dynamics.py](../../../topogym/redundants/mujoco/tasks/orbits/robot_dynamics.py) ← `topogym/tasks/orbits/robot_dynamics.py` — Orbits：构造带 ALOHA 驱动器的 MuJoCo 任务模型；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/orbits/robot_runtime.py](../../../topogym/redundants/mujoco/tasks/orbits/robot_runtime.py) ← `topogym/tasks/orbits/robot_runtime.py` — Orbits：管理实测机器人控制、物理步进与接触状态；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/fem.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem.py) ← `topogym/tasks/slotted_post_ring/fem.py` — Slotted Post Ring：构造 MuJoCo 体积 FEM 绳模型并校验材料；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_fixture.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_fixture.py) ← `topogym/tasks/slotted_post_ring/fem_fixture.py` — Slotted Post Ring：运行外力 FEM 流程并记录体积验收数据；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_grasp.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_grasp.py) ← `topogym/tasks/slotted_post_ring/fem_grasp.py` — Slotted Post Ring：以材料截面受力约束引导抓持而非写入位姿；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_probe.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_probe.py) ← `topogym/tasks/slotted_post_ring/fem_probe.py` — Slotted Post Ring：运行无外力 FEM 稳定性诊断；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/fixture.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fixture.py) ← `topogym/tasks/slotted_post_ring/fixture.py` — Slotted Post Ring：运行外力驱动的任务解法或对照实验；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py) ← `topogym/tasks/slotted_post_ring/physics.py` — Slotted Post Ring：构建并检查任务物理模型和求解器设置；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/probe.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/probe.py) ← `topogym/tasks/slotted_post_ring/probe.py` — Slotted Post Ring：构建或执行任务物理探针；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/robot.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/robot.py) ← `topogym/tasks/slotted_post_ring/robot.py` — Slotted Post Ring：在 MuJoCo 中试验 ALOHA 物理抓持与接触；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py) ← `topogym/tasks/slotted_post_ring/robot_sequence.py` — Slotted Post Ring：管理任务机器人连续操纵及抓持审计；移动：明确的 MuJoCo 模型、积分或专属驱动实现；仅隔离，不改代码；直接导入 MuJoCo，未修改。
- [topogym/redundants/mujoco/world/mujoco_presentation.py](../../../topogym/redundants/mujoco/world/mujoco_presentation.py) ← `topogym/world/mujoco_presentation.py` — 把实验室布局和相机写入 MuJoCo XML；移动：MuJoCo 专属 XML 外观生成。
- [topogym/redundants/package_markers/core/__init__.py](../../../topogym/redundants/package_markers/core/__init__.py) ← `topogym/core/__init__.py` — 声明 topogym/core 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/generation/__init__.py](../../../topogym/redundants/package_markers/generation/__init__.py) ← `topogym/generation/__init__.py` — 声明 topogym/generation 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/planning/__init__.py](../../../topogym/redundants/package_markers/planning/__init__.py) ← `topogym/planning/__init__.py` — 声明 topogym/planning 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/primitives/__init__.py](../../../topogym/redundants/package_markers/primitives/__init__.py) ← `topogym/primitives/__init__.py` — 声明 topogym/primitives 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/runtime/__init__.py](../../../topogym/redundants/package_markers/runtime/__init__.py) ← `topogym/runtime/__init__.py` — 声明 topogym/runtime 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/supervision/__init__.py](../../../topogym/redundants/package_markers/supervision/__init__.py) ← `topogym/supervision/__init__.py` — 声明 topogym/supervision 包入口并组织导出；移动：已分流旧模块的包标记原样留存。
- [topogym/redundants/package_markers/tasks/blanket_flatten/__init__.py](../../../topogym/redundants/package_markers/tasks/blanket_flatten/__init__.py) ← `topogym/tasks/blanket_flatten/__init__.py` — 声明 topogym/tasks/blanket_flatten 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/buzz_wire_3d/__init__.py](../../../topogym/redundants/package_markers/tasks/buzz_wire_3d/__init__.py) ← `topogym/tasks/buzz_wire_3d/__init__.py` — 声明 topogym/tasks/buzz_wire_3d 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/cast_coil/__init__.py](../../../topogym/redundants/package_markers/tasks/cast_coil/__init__.py) ← `topogym/tasks/cast_coil/__init__.py` — 声明 topogym/tasks/cast_coil 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/cast_keyhole/__init__.py](../../../topogym/redundants/package_markers/tasks/cast_keyhole/__init__.py) ← `topogym/tasks/cast_keyhole/__init__.py` — 声明 topogym/tasks/cast_keyhole 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/fiber_bundling/__init__.py](../../../topogym/redundants/package_markers/tasks/fiber_bundling/__init__.py) ← `topogym/tasks/fiber_bundling/__init__.py` — 声明 topogym/tasks/fiber_bundling 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/hedgehog_in_cage/__init__.py](../../../topogym/redundants/package_markers/tasks/hedgehog_in_cage/__init__.py) ← `topogym/tasks/hedgehog_in_cage/__init__.py` — 声明 topogym/tasks/hedgehog_in_cage 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/horseshoe_ring/__init__.py](../../../topogym/redundants/package_markers/tasks/horseshoe_ring/__init__.py) ← `topogym/tasks/horseshoe_ring/__init__.py` — 声明 topogym/tasks/horseshoe_ring 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/interlocked_claws/__init__.py](../../../topogym/redundants/package_markers/tasks/interlocked_claws/__init__.py) ← `topogym/tasks/interlocked_claws/__init__.py` — 声明 topogym/tasks/interlocked_claws 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/knot_untying/__init__.py](../../../topogym/redundants/package_markers/tasks/knot_untying/__init__.py) ← `topogym/tasks/knot_untying/__init__.py` — 声明 topogym/tasks/knot_untying 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/lock_picking/__init__.py](../../../topogym/redundants/package_markers/tasks/lock_picking/__init__.py) ← `topogym/tasks/lock_picking/__init__.py` — 声明 topogym/tasks/lock_picking 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/orbits/__init__.py](../../../topogym/redundants/package_markers/tasks/orbits/__init__.py) ← `topogym/tasks/orbits/__init__.py` — 声明 topogym/tasks/orbits 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/rope_threading/__init__.py](../../../topogym/redundants/package_markers/tasks/rope_threading/__init__.py) ← `topogym/tasks/rope_threading/__init__.py` — 声明 topogym/tasks/rope_threading 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/package_markers/tasks/slotted_post_ring/__init__.py](../../../topogym/redundants/package_markers/tasks/slotted_post_ring/__init__.py) ← `topogym/tasks/slotted_post_ring/__init__.py` — 声明 topogym/tasks/slotted_post_ring 包入口及其职责范围；移动：原任务子包标记；任务目录改为单文件后原样留存。
- [topogym/redundants/presentation/cast_coil/solvability_view.html](../../../topogym/redundants/presentation/cast_coil/solvability_view.html) ← `topogym/tasks/cast_coil/solvability_view.html` — 提供 solvability_view 的静态检查或展示页面；移动：历史静态展示页面。
- [topogym/redundants/presentation/cast_keyhole/review.py](../../../topogym/redundants/presentation/cast_keyhole/review.py) ← `topogym/tasks/cast_keyhole/review.py` — Cast Keyhole：汇总任务证据并生成检查材料；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/cast_keyhole/solution_diagnostics.py](../../../topogym/redundants/presentation/cast_keyhole/solution_diagnostics.py) ← `topogym/tasks/cast_keyhole/solution_diagnostics.py` — Cast Keyhole：绘制被拒绝路线区间以供诊断；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/fiber_bundling/plot_variants.py](../../../topogym/redundants/presentation/fiber_bundling/plot_variants.py) ← `topogym/tasks/fiber_bundling/plot_variants.py` — Fiber：为 variants 生成检查图和报告；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/fiber_bundling/review.py](../../../topogym/redundants/presentation/fiber_bundling/review.py) ← `topogym/tasks/fiber_bundling/review.py` — Fiber：汇总任务证据并生成检查材料；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/hedgehog_in_cage/family_review.py](../../../topogym/redundants/presentation/hedgehog_in_cage/family_review.py) ← `topogym/tasks/hedgehog_in_cage/family_review.py` — Hedgehog：为 family 生成检查图和报告；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/horseshoe_ring/inverse_review.py](../../../topogym/redundants/presentation/horseshoe_ring/inverse_review.py) ← `topogym/tasks/horseshoe_ring/inverse_review.py` — Horseshoe：为 inverse 生成检查图和报告；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/horseshoe_ring/shape_review.py](../../../topogym/redundants/presentation/horseshoe_ring/shape_review.py) ← `topogym/tasks/horseshoe_ring/shape_review.py` — Horseshoe：为 shape 生成检查图和报告；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/horseshoe_ring/shape_viewer.html](../../../topogym/redundants/presentation/horseshoe_ring/shape_viewer.html) ← `topogym/tasks/horseshoe_ring/shape_viewer.html` — 提供 shape_viewer 的静态检查或展示页面；移动：历史静态展示页面。
- [topogym/redundants/presentation/horseshoe_ring/trace_review.py](../../../topogym/redundants/presentation/horseshoe_ring/trace_review.py) ← `topogym/tasks/horseshoe_ring/trace_review.py` — Horseshoe：为 trace 生成检查图和报告；移动：专用实验、展示或研究检查；原样保留待筛选。
- [topogym/redundants/presentation/lock_picking/inverse_variants_review.html](../../../topogym/redundants/presentation/lock_picking/inverse_variants_review.html) ← `topogym/tasks/lock_picking/inverse_variants_review.html` — Lock：为 inverse_variants 生成检查图和报告；移动：历史静态展示页面。
- [topogym/redundants/presentation/slotted_post_ring/review.py](../../../topogym/redundants/presentation/slotted_post_ring/review.py) ← `topogym/tasks/slotted_post_ring/review.py` — Slotted Post Ring：汇总任务证据并生成检查材料；移动：专用实验、展示或研究检查；原样保留待筛选；直接导入 MuJoCo，未修改。
