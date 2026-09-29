# 命名统计附录：完整路径与声明索引

[主报告与建议命名系统](simulator_naming_audit_zh.md)。本页是静态名称索引，不把出现频次直接当作设计错误。

扫描时间：`2026-09-23T15:28:27.206360+00:00`。覆盖当前包 496 个 Python 文件、4 个 HTML 文件、1 个资产来源 JSON；含 redundants，不含字节码、运行快照及第三方包。

Python AST 共 3,326 处 class/def 声明；其中 2,528 处不嵌套在函数内且名称及所属作用域均不以下划线开头。这里的“公开”只是命名口径，不等同于实际 __all__ 导出。

## 1. 名称族统计

按 snake_case / CamelCase 拆词并归一常见复数；路径统计含目录名，定义统计只看声明自己的名称，不累计 import、变量、注释或调用次数；每个名称族内部按文件或声明去重，名称族之间可重叠。字段与字符串的语义冲突由主报告单独检查。

| 名称族 | 功能目录路径命中 | redundants 路径命中 | 公开类定义 | 公开函数/方法定义 |
|---|---:|---:|---:|---:|
| adapter | 26 | 1 | 13 | 0 |
| binding | 0 | 0 | 15 | 4 |
| scene / world / env / task | 206 | 29 | 32 | 69 |
| runtime / runner / execution / session | 20 | 2 | 7 | 9 |
| config / spec / schema / contract / protocol | 24 | 0 | 2 | 29 |
| registry / catalog / factory / builder | 4 | 0 | 11 | 10 |
| policy / planner / controller / solver | 79 | 0 | 6 | 9 |
| variant / variation / family / instance | 57 | 13 | 12 | 37 |
| preset / profile / template / layout | 4 | 0 | 15 | 24 |
| episode / run / rollout / trial / segment | 15 | 4 | 17 | 63 |
| step / tick / frame | 0 | 1 | 4 | 49 |
| state / snapshot / checkpoint / restore | 1 | 1 | 1 | 66 |
| replay / resume / render / record | 59 | 4 | 7 | 59 |
| validate / verify / audit / review / qualify | 35 | 8 | 7 | 109 |
| geometry / model / asset | 72 | 0 | 4 | 58 |
| manifest / source / signature | 3 | 0 | 2 | 48 |
| demo / probe / preview | 10 | 39 | 5 | 18 |
| result / status / verdict / success | 0 | 0 | 14 | 1 |
| backend / device / engine | 3 | 0 | 2 | 1 |

## 2. 同名公开类：全部 10 组

不同模块的同名类在 Python 中可以合法共存；以下是审查候选，不是自动删除清单。

- **Kinematics**：5 处。
  - [topogym/assets/variants/hedgehog_in_cage/inverse_window.py:41](../../../topogym/assets/variants/hedgehog_in_cage/inverse_window.py#L41)。
  - [topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py:32](../../../topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py#L32)。
  - [topogym/solvers/kinematics/cast_coil/robot_plan.py:32](../../../topogym/solvers/kinematics/cast_coil/robot_plan.py#L32)。
  - [topogym/solvers/kinematics/cast_keyhole/robot_motion.py:33](../../../topogym/solvers/kinematics/cast_keyhole/robot_motion.py#L33)。
  - [topogym/solvers/kinematics/horseshoe_ring/robot_motion.py:26](../../../topogym/solvers/kinematics/horseshoe_ring/robot_motion.py#L26)。
- **RobotAudit**：3 处。
  - [topogym/envs/execution/hedgehog_in_cage/family_runtime.py:41](../../../topogym/envs/execution/hedgehog_in_cage/family_runtime.py#L41)。
  - [topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py:39](../../../topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py#L39)。
  - [topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py:127](../../../topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py#L127)。
- **CompoundCollision**：2 处。
  - [topogym/evaluation/tasks/cast_coil/verification.py:29](../../../topogym/evaluation/tasks/cast_coil/verification.py#L29)。
  - [topogym/solvers/collision/cast_keyhole/collision.py:16](../../../topogym/solvers/collision/cast_keyhole/collision.py#L16)。
- **Episode**：2 处。
  - [topogym/agents/rollout/episode.py:101](../../../topogym/agents/rollout/episode.py#L101)。
  - [topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py:49](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py#L49)。
- **ForwardOnlyMemory**：2 处。
  - [topogym/world/physics/knot_untying/runtime_memory.py:11](../../../topogym/world/physics/knot_untying/runtime_memory.py#L11)。
  - [topogym/world/physics/rope_threading/runtime_memory.py:5](../../../topogym/world/physics/rope_threading/runtime_memory.py#L5)。
- **GenerationRejected**：2 处。
  - [topogym/assets/variants/fiber_bundling/generation.py:50](../../../topogym/assets/variants/fiber_bundling/generation.py#L50)。
  - [topogym/assets/variants/hedgehog_in_cage/variants.py:357](../../../topogym/assets/variants/hedgehog_in_cage/variants.py#L357)。
- **Motion**：2 处。
  - [topogym/evaluation/tasks/cast_coil/verification.py:60](../../../topogym/evaluation/tasks/cast_coil/verification.py#L60)。
  - [topogym/solvers/collision/cast_keyhole/collision.py:62](../../../topogym/solvers/collision/cast_keyhole/collision.py#L62)。
- **PhysicsSettings**：2 处。
  - [topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py:39](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py#L39)。
  - [topogym/world/physics/buzz_wire_3d/physics.py:39](../../../topogym/world/physics/buzz_wire_3d/physics.py#L39)。
- **RobotClearance**：2 处。
  - [topogym/solvers/collision/horseshoe_ring/robot_clearance.py:12](../../../topogym/solvers/collision/horseshoe_ring/robot_clearance.py#L12)。
  - [topogym/solvers/kinematics/cast_keyhole/robot_motion.py:83](../../../topogym/solvers/kinematics/cast_keyhole/robot_motion.py#L83)。
- **StabilityLimits**：2 处。
  - [topogym/evaluation/diagnostics/stability.py:8](../../../topogym/evaluation/diagnostics/stability.py#L8)。
  - [topogym/evaluation/tasks/knot_untying/diagnostics.py:15](../../../topogym/evaluation/tasks/knot_untying/diagnostics.py#L15)。

## 3. 所有 Adapter / Binding 类声明

Adapter 共 13 处；Binding 共 15 处（含 RecordingBinding 协议与 redundants 中的 MuJoCoBinding），两种后缀不能相加当作“28 个 adapter”。

- [VisualAdapter — topogym/agents/rollout/runtime.py:16](../../../topogym/agents/rollout/runtime.py#L16)。
- [GenesisAdapter — topogym/envs/adapters/base.py:59](../../../topogym/envs/adapters/base.py#L59)。
- [BuzzWireAdapter — topogym/envs/adapters/buzz_wire_3d.py:92](../../../topogym/envs/adapters/buzz_wire_3d.py#L92)；基类：`RigidRobotAdapter`。
- [KeyholeAdapter — topogym/envs/adapters/cast_keyhole.py:16](../../../topogym/envs/adapters/cast_keyhole.py#L16)；基类：`AlohaRigidAdapter`。
- [FEMRobotAdapter — topogym/envs/adapters/fem_robot.py:94](../../../topogym/envs/adapters/fem_robot.py#L94)；基类：`GenesisAdapter`。
- [HedgehogAdapter — topogym/envs/adapters/hedgehog_in_cage.py:39](../../../topogym/envs/adapters/hedgehog_in_cage.py#L39)；基类：`RigidRobotAdapter`。
- [HorseshoeAdapter — topogym/envs/adapters/horseshoe_ring.py:16](../../../topogym/envs/adapters/horseshoe_ring.py#L16)；基类：`AlohaRigidAdapter`。
- [ClawsAdapter — topogym/envs/adapters/interlocked_claws.py:41](../../../topogym/envs/adapters/interlocked_claws.py#L41)；基类：`AlohaRigidAdapter`。
- [KnotAdapter — topogym/envs/adapters/knot_untying.py:54](../../../topogym/envs/adapters/knot_untying.py#L54)；基类：`FEMRobotAdapter`。
- [LockPickingAdapter — topogym/envs/adapters/lock_picking.py:35](../../../topogym/envs/adapters/lock_picking.py#L35)；基类：`RigidRobotAdapter`。
- [RigidRobotAdapter — topogym/envs/adapters/rigid_robot.py:60](../../../topogym/envs/adapters/rigid_robot.py#L60)；基类：`GenesisAdapter`。
- [AlohaRigidAdapter — topogym/envs/adapters/rigid_robot.py:174](../../../topogym/envs/adapters/rigid_robot.py#L174)；基类：`RigidRobotAdapter`。
- [TaskAdapter — topogym/envs/protocol.py:5](../../../topogym/envs/protocol.py#L5)；基类：`Protocol`。
- [GenesisBinding — topogym/recording/adapters/genesis.py:16](../../../topogym/recording/adapters/genesis.py#L16)。
- [RecordingBinding — topogym/recording/contracts.py:58](../../../topogym/recording/contracts.py#L58)；基类：`Protocol`。
- [BlanketBinding — topogym/recording/task_adapters/blanket_flatten.py:102](../../../topogym/recording/task_adapters/blanket_flatten.py#L102)；基类：`GenesisBinding`。
- [KeyholeBinding — topogym/recording/task_adapters/cast_keyhole.py:133](../../../topogym/recording/task_adapters/cast_keyhole.py#L133)；基类：`GenesisBinding`。
- [FiberBinding — topogym/recording/task_adapters/fiber_bundling.py:148](../../../topogym/recording/task_adapters/fiber_bundling.py#L148)；基类：`GenesisBinding`。
- [HedgehogBinding — topogym/recording/task_adapters/hedgehog_in_cage.py:26](../../../topogym/recording/task_adapters/hedgehog_in_cage.py#L26)；基类：`GenesisBinding`。
- [HorseshoeBinding — topogym/recording/task_adapters/horseshoe_ring.py:29](../../../topogym/recording/task_adapters/horseshoe_ring.py#L29)；基类：`GenesisBinding`。
- [KnotBinding — topogym/recording/task_adapters/knot_untying.py:35](../../../topogym/recording/task_adapters/knot_untying.py#L35)；基类：`GenesisBinding`。
- [LockBinding — topogym/recording/task_adapters/lock_picking.py:83](../../../topogym/recording/task_adapters/lock_picking.py#L83)；基类：`GenesisBinding`。
- [RopeBinding — topogym/recording/task_adapters/orbits.py:30](../../../topogym/recording/task_adapters/orbits.py#L30)；基类：`MuJoCoBinding`。
- [ThreadingBinding — topogym/recording/task_adapters/rope_threading.py:64](../../../topogym/recording/task_adapters/rope_threading.py#L64)；基类：`GenesisBinding`。
- [FEMBinding — topogym/recording/task_adapters/slotted_post_ring.py:121](../../../topogym/recording/task_adapters/slotted_post_ring.py#L121)；基类：`MuJoCoBinding`。
- [OrbitsCordBinding — topogym/recording/tasks/orbits/motion_render.py:39](../../../topogym/recording/tasks/orbits/motion_render.py#L39)；基类：`GenesisBinding`。
- [RobotRopeBinding — topogym/recording/tasks/orbits/robot_recording.py:77](../../../topogym/recording/tasks/orbits/robot_recording.py#L77)；基类：`RopeBinding`。
- [MuJoCoBinding — topogym/redundants/mujoco/recording/adapters/mujoco.py:9](../../../topogym/redundants/mujoco/recording/adapters/mujoco.py#L9)。

## 4. 常见同名函数/方法

统计不嵌套且公开的函数/方法；main 不列入排行，避免 CLI 约定名掩盖主要语义；同一接口的多个实现会重复计数，这是正常现象。

| 名称 | 定义处数 |
|---|---:|
| `run` | 34 |
| `render` | 25 |
| `step` | 22 |
| `audit` | 20 |
| `report` | 20 |
| `observe` | 19 |
| `build` | 19 |
| `close` | 18 |
| `sha` | 17 |
| `save` | 17 |
| `pose` | 16 |
| `update` | 16 |
| `archive` | 16 |
| `snapshot` | 15 |
| `generate` | 13 |
| `execute` | 13 |
| `specification` | 13 |
| `scene_report` | 13 |
| `restore` | 13 |
| `scene` | 13 |
| `release` | 12 |
| `from_source` | 12 |
| `manifest` | 12 |
| `cameras` | 12 |
| `validate` | 11 |
| `generate_assets` | 11 |
| `solve` | 11 |
| `create` | 11 |
| `build_scene` | 11 |
| `prepare` | 10 |
| `sample` | 9 |
| `configuration` | 9 |
| `declare` | 9 |
| `array` | 9 |
| `write_review` | 9 |
| `configure` | 9 |
| `export_state` | 9 |
| `digest` | 8 |
| `metadata_dict` | 8 |
| `describe_task` | 8 |

## 5. 逐文件完整声明清单

以下 501 个文件每个出现一次；L 为当前源码行号。列出私有声明和局部声明以保证覆盖，统计表的公开计数则不包含它们；不记录第三方继承成员或动态创建名称。没有 Python 定义的文件仍列出。

### [topogym/__init__.py](../../../topogym/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/agents/bridge/__init__.py](../../../topogym/agents/bridge/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/agents/bridge/__main__.py](../../../topogym/agents/bridge/__main__.py)

- 模块函数：`main`（L8）。

### [topogym/agents/bridge/budget.py](../../../topogym/agents/bridge/budget.py)

- 类：`Budget`（L7）。
- 类方法：`Budget.__init__`（L8，私有）；`Budget.snapshot`（L14）；`Budget.reserve`（L22）；`Budget.progress`（L40）；`Budget.complete`（L47）；`Budget.estimate`（L66）。

### [topogym/agents/bridge/client.py](../../../topogym/agents/bridge/client.py)

- 类：`Client`（L7）。
- 模块函数：`main`（L86）。
- 类方法：`Client.__init__`（L8，私有）；`Client.request`（L11）；`Client._local_request`（L24，私有）；`Client.state`（L78）；`Client.submit`（L81）。
- 函数内局部声明：`Client._local_request.alive`（L34，私有）；`main.local_brief`（L117）；`main.save_json`（L128）；`main.download`（L131）。

### [topogym/agents/bridge/dashboard.html](../../../topogym/agents/bridge/dashboard.html)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/agents/bridge/local.py](../../../topogym/agents/bridge/local.py)

- 模块函数：`dispatch`（L19）；`heartbeat_worker`（L38）；`worker`（L54）；`main`（L111）。
- 函数内局部声明：`worker.publish`（L60）；`worker.interrupted`（L71）。

### [topogym/agents/bridge/openai_harness.py](../../../topogym/agents/bridge/openai_harness.py)

- 类：`OpenAIResponses`（L33）。
- 模块函数：`artifact_content`（L69）；`run`（L86）；`main`（L153）。
- 类方法：`OpenAIResponses.__init__`（L34，私有）；`OpenAIResponses._request`（L37，私有）；`OpenAIResponses.count`（L41）；`OpenAIResponses.generate`（L45）。

### [topogym/agents/bridge/package.py](../../../topogym/agents/bridge/package.py)

- 模块函数：`export_package`（L13）；`main`（L75）。

### [topogym/agents/bridge/server.py](../../../topogym/agents/bridge/server.py)

- 类：`BridgeServer`（L13）；`Handler`（L35）。
- 类方法：`BridgeServer.__init__`（L16，私有）；`BridgeServer.server_close`（L29）；`Handler.log_message`（L36）；`Handler.send_data`（L39）；`Handler.local_request`（L50）；`Handler.do_GET`（L58）；`Handler.do_POST`（L83）。

### [topogym/agents/bridge/session.py](../../../topogym/agents/bridge/session.py)

- 类：`Session`（L27）。
- 模块函数：`write_json`（L16）。
- 类方法：`Session.__init__`（L28，私有）；`Session.snapshot`（L85）；`Session.prompt`（L96）；`Session._persist`（L123，私有）；`Session._event`（L128，私有）；`Session._capture`（L134，私有）；`Session._verdict`（L154，私有）；`Session.usage`（L162）；`Session.finish`（L190）；`Session.submit`（L202）；`Session.artifact`（L282）。

### [topogym/agents/bridge/tool_policy.py](../../../topogym/agents/bridge/tool_policy.py)

- 模块函数：`tool_policy`（L4）；`policy_prompt`（L16）。

### [topogym/agents/rollout/__init__.py](../../../topogym/agents/rollout/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/agents/rollout/__main__.py](../../../topogym/agents/rollout/__main__.py)

- 模块函数：`main`（L7）。

### [topogym/agents/rollout/agents.py](../../../topogym/agents/rollout/agents.py)

- 类：`ReplayAgent`（L27）；`CommandAgent`（L51）；`CodexAgent`（L79）。
- 模块函数：`validate_decision`（L16）；`create_agent`（L208）。
- 类方法：`ReplayAgent.__init__`（L31，私有）；`ReplayAgent.decide`（L35）；`CommandAgent.__init__`（L59，私有）；`CommandAgent.decide`（L64）；`CodexAgent.__init__`（L87，私有）；`CodexAgent.decide`（L115）；`CodexAgent.close`（L202）。

### [topogym/agents/rollout/budget_proxy.py](../../../topogym/agents/rollout/budget_proxy.py)

- 类：`NoRedirect`（L23）；`BudgetProxy`（L28）。
- 类方法：`NoRedirect.redirect_request`（L24）；`BudgetProxy.__init__`（L29，私有）；`BudgetProxy._open`（L44，私有）；`BudgetProxy.prepare`（L51）；`BudgetProxy._handler`（L84，私有）；`BudgetProxy.close`（L174）。
- 函数内局部声明：`BudgetProxy.prepare.check_tools`（L61）；`BudgetProxy._handler.Handler`（L87，私有）；`BudgetProxy._handler.Handler.log_message`（L88，私有）；`BudgetProxy._handler.Handler.fail`（L91，私有）；`BudgetProxy._handler.Handler.do_GET`（L99，私有）；`BudgetProxy._handler.Handler.do_POST`（L102，私有）。

### [topogym/agents/rollout/env_sdk.py](../../../topogym/agents/rollout/env_sdk.py)

- 类：`EnvironmentError`（L10）；`Environment`（L14）。
- 模块函数：`connect`（L65）。
- 类方法：`Environment.__init__`（L15，私有）；`Environment._call`（L23，私有）；`Environment.describe`（L38）；`Environment.observe`（L41）；`Environment.list_entities`（L46）；`Environment.get_state`（L49）；`Environment.get_pose`（L52）；`Environment.step`（L55）；`Environment.reset`（L58）；`Environment.finish`（L61）。

### [topogym/agents/rollout/episode.py](../../../topogym/agents/rollout/episode.py)

- 类：`Episode`（L101）。
- 模块函数：`_worker`（L11，私有）。
- 类方法：`Episode.__init__`（L102，私有）；`Episode._receive`（L121，私有）；`Episode.call`（L132）；`Episode.close`（L136）。
- 函数内局部声明：`_worker.publish`（L37，私有）。

### [topogym/agents/rollout/isolation.py](../../../topogym/agents/rollout/isolation.py)

- 模块函数：`sandbox_command`（L6）。

### [topogym/agents/rollout/runtime.py](../../../topogym/agents/rollout/runtime.py)

- 类：`VisualAdapter`（L16）。
- 模块函数：`prompt`（L46）；`inspect_paths`（L87）；`run_repeat`（L105）。
- 类方法：`VisualAdapter.__init__`（L18，私有）；`VisualAdapter.describe`（L21）；`VisualAdapter.observe`（L30）；`VisualAdapter.render`（L33）；`VisualAdapter.validate_action`（L36）；`VisualAdapter.step`（L39）；`VisualAdapter.evaluate`（L42）。

### [topogym/agents/rollout/token_budget.py](../../../topogym/agents/rollout/token_budget.py)

- 类：`TokenBudgetExhausted`（L9）；`TokenBudget`（L19）。
- 模块函数：`natural`（L13）。
- 类方法：`TokenBudget.__init__`（L20，私有）；`TokenBudget.snapshot`（L27）；`TokenBudget._persist`（L38，私有）；`TokenBudget.stop`（L43）；`TokenBudget.require_ready`（L49）；`TokenBudget.reserve`（L58）；`TokenBudget.complete`（L77）；`TokenBudget.usage_since`（L102）；`TokenBudget.notice`（L110）。

### [topogym/agents/rollout/tool_runtime.py](../../../topogym/agents/rollout/tool_runtime.py)

- 类：`Trial`（L22）；`EnvironmentServer`（L237）。
- 模块函数：`tool_prompt`（L289）；`run_tool_repeat`（L316）。
- 类方法：`Trial.__init__`（L23，私有）；`Trial.start`（L39）；`Trial._start_episode`（L47，私有）；`Trial.capabilities`（L59）；`Trial.snapshot`（L69）；`Trial._event`（L83，私有）；`Trial._update_status`（L92，私有）；`Trial._check_limits`（L100，私有）；`Trial.dispatch`（L118）；`Trial.close`（L213）；`EnvironmentServer.__init__`（L238，私有）；`EnvironmentServer.close`（L283）。
- 函数内局部声明：`EnvironmentServer.__init__.Handler`（L242，私有）；`EnvironmentServer.__init__.Handler.setup`（L243，私有）；`EnvironmentServer.__init__.Handler.log_message`（L247，私有）；`EnvironmentServer.__init__.Handler.do_POST`（L250，私有）；`EnvironmentServer.__init__.Handler.reply`（L266，私有）。

### [topogym/assets/generators/blanket_flatten/gathered_geometry.py](../../../topogym/assets/generators/blanket_flatten/gathered_geometry.py)

- 模块函数：`gathered_target`（L11）。

### [topogym/assets/generators/blanket_flatten/geometry.py](../../../topogym/assets/generators/blanket_flatten/geometry.py)

- 类：`BlanketLayout`（L14）。
- 模块函数：`rotation`（L65）；`_fold`（L73，私有）；`_mesh`（L87，私有）；`panel_clearance`（L111）；`generate`（L132）；`material_coordinates`（L186）；`generate_flat_binding`（L196）；`write_obj`（L215）。
- 类方法：`BlanketLayout.validate`（L38）。

### [topogym/assets/generators/braid.py](../../../topogym/assets/generators/braid.py)

- 类：`BraidLayout`（L45）；`BraidCrossing`（L78）；`BraidSpec`（L89）；`BraidVerification`（L120）。
- 模块函数：`reduce_braid_word`（L133）；`sample_braid_word`（L153）；`crossing_window`（L191）；`crossing_position_frac`（L205）；`crossing_window_at`（L228）；`channel_y_positions`（L255）；`braid_to_control_points`（L265）；`build_braid_spec`（L348）；`verify_braid_spec`（L387）。
- 类方法：`BraidSpec.inverse_word`（L99）；`BraidSpec.optimal_sequence`（L105）；`BraidVerification.__str__`（L127，私有）。

### [topogym/assets/generators/buzz_wire_3d/appearance.py](../../../topogym/assets/generators/buzz_wire_3d/appearance.py)

- 模块函数：`wood`（L22）；`metal`（L32）；`replace_visuals`（L45）；`restore_renderer_materials`（L57）；`finish_assets`（L80）；`toy_wood`（L129）；`plinth_layers`（L159）；`finish_toy_assets`（L202）。
- 函数内局部声明：`plinth_layers.outline`（L164）；`plinth_layers.tier`（L179）。

### [topogym/assets/generators/buzz_wire_3d/family_geometry.py](../../../topogym/assets/generators/buzz_wire_3d/family_geometry.py)

- 模块函数：`clean`（L10）；`line`（L15）；`vertical_wave_controls`（L19）；`comb`（L57）；`eight`（L76）；`w_valleys`（L87）；`omega`（L106）；`coil`（L118）；`join`（L133）；`compose`（L150）。

### [topogym/assets/generators/buzz_wire_3d/geometry.py](../../../topogym/assets/generators/buzz_wire_3d/geometry.py)

- 类：`BuzzWireLayout`（L24）；`SpatialWire`（L378）。
- 模块函数：`transported_frames`（L580）；`front_facing_frames`（L609）；`capsule_mesh`（L620）；`_add_capsule`（L634，私有）；`_write_xml`（L641，私有）；`generate_assets`（L653）。
- 类方法：`BuzzWireLayout.validate`（L72）；`BuzzWireLayout.control_points`（L305）；`BuzzWireLayout._slalom_controls`（L328，私有）；`BuzzWireLayout.tool_capsules`（L347）；`SpatialWire.__init__`（L379，私有）；`SpatialWire.pose`（L544）；`SpatialWire.fixed_capsules`（L552）。

### [topogym/assets/generators/buzz_wire_3d/supports.py](../../../topogym/assets/generators/buzz_wire_3d/supports.py)

- 模块函数：`endpoint_pose`（L7）；`support_spheres`（L50）；`support_boxes`（L100）；`fixture_boxes`（L199）。
- 函数内局部声明：`support_spheres.cradle`（L62）。

### [topogym/assets/generators/buzz_wire_3d/templates.py](../../../topogym/assets/generators/buzz_wire_3d/templates.py)

- 模块函数：`reference_maze_controls`（L10）；`_vertical_controls`（L96，私有）。
- 函数内局部声明：`reference_maze_controls.add`（L14）；`reference_maze_controls.line`（L19）；`reference_maze_controls.arc`（L29）。

### [topogym/assets/generators/cast_coil/appearance.py](../../../topogym/assets/generators/cast_coil/appearance.py)

- 模块函数：`coordinate_scale`（L35）；`appearance_route`（L41）；`corner_cuts`（L63）；`create_template`（L84）；`generate`（L134）。

### [topogym/assets/generators/cast_coil/geometry.py](../../../topogym/assets/generators/cast_coil/geometry.py)

- 类：`CoilBody`（L103）；`CoilAssembly`（L110）。
- 模块函数：`load_template`（L25）；`box`（L29）；`occupied`（L33）；`partition_solid`（L39）；`merge_cells`（L76）；`clearance`（L171）；`geometry_report`（L181）；`write_body`（L211）；`generate_assets`（L243）。
- 类方法：`CoilAssembly.__init__`（L111，私有）。

### [topogym/assets/generators/cast_keyhole/geometry.py](../../../topogym/assets/generators/cast_keyhole/geometry.py)

- 类：`KeyholeBody`（L118）；`KeyholeAssembly`（L126）。
- 模块函数：`load_template`（L25）；`arc`（L29）；`outlines`（L37）；`polygon_slabs`（L47）；`extrude_slabs`（L71）；`mesh_clearance`（L159）；`geometry_report`（L171）；`write_body`（L196）；`generate_assets`（L227）。
- 类方法：`KeyholeAssembly.__init__`（L127，私有）。

### [topogym/assets/generators/fiber_bundling/anchored_geometry.py](../../../topogym/assets/generators/fiber_bundling/anchored_geometry.py)

- 类：`AnchoredLayout`（L29）。
- 模块函数：`part_color`（L96）；`write_anchored_bundle`（L100）；`generate_anchored_assets`（L140）。
- 类方法：`AnchoredLayout.from_task_config`（L38）；`AnchoredLayout.spacing`（L45）；`AnchoredLayout.lead`（L52）；`AnchoredLayout.terminal_parts`（L65）；`AnchoredLayout.cradle_parts`（L85）。

### [topogym/assets/generators/fiber_bundling/geometry.py](../../../topogym/assets/generators/fiber_bundling/geometry.py)

- 类：`FiberLayout`（L31）。
- 模块函数：`segment_distance`（L122）；`minimum_fiber_clearance`（L137）；`frame`（L143）；`shape_in_root_frame`（L150）；`write_bundle`（L167）；`generate_assets`（L245）。
- 类方法：`FiberLayout.__post_init__`（L51，私有）；`FiberLayout.ring`（L80）；`FiberLayout.minimum_aperture_radius`（L85）；`FiberLayout.fibers`（L89）。
- 函数内局部声明：`generate_assets.finish`（L250）。

### [topogym/assets/generators/fiber_bundling/prepare_assets.py](../../../topogym/assets/generators/fiber_bundling/prepare_assets.py)

- 模块函数：`main`（L7）。

### [topogym/assets/generators/fiber_bundling/ring_mount.py](../../../topogym/assets/generators/fiber_bundling/ring_mount.py)

- 类：`RingMount`（L17）。
- 模块函数：`require_fixture_evidence`（L67）；`export_fixture`（L82）。
- 类方法：`RingMount.__post_init__`（L21，私有）；`RingMount.from_task_config`（L28）；`RingMount.signature`（L31）；`RingMount.parts`（L36）；`RingMount.add_to_scene`（L55）。

### [topogym/assets/generators/hedgehog_in_cage/appearance.py](../../../topogym/assets/generators/hedgehog_in_cage/appearance.py)

- 模块函数：`wood_visual`（L11）。

### [topogym/assets/generators/hedgehog_in_cage/family_geometry.py](../../../topogym/assets/generators/hedgehog_in_cage/family_geometry.py)

- 类：`Sweep`（L29）。
- 模块函数：`union64`（L19）；`make_sweep`（L41）；`boxes_from_mask`（L101）；`annular_cells`（L116）；`rectangular_gate_cells`（L153）；`geometry`（L170）；`evaluate`（L220）；`certify`（L230）；`main`（L262）。
- 类方法：`Sweep.__init__`（L30，私有）；`Sweep.distance`（L35）。

### [topogym/assets/generators/hedgehog_in_cage/geometry.py](../../../topogym/assets/generators/hedgehog_in_cage/geometry.py)

- 类：`HedgehogLayout`（L49）。
- 模块函数：`load_template`（L24）；`band_mesh`（L75）；`cage_meshes`（L97）；`hedgehog_meshes`（L147）；`write_body`（L163）；`clearance_samples`（L212）；`pose_clearance`（L225）；`choose_initial_pose`（L231）；`generate_assets`（L267）。
- 类方法：`HedgehogLayout.__post_init__`（L53，私有）；`HedgehogLayout.unit`（L58）；`HedgehogLayout.spike_segments`（L61）。

### [topogym/assets/generators/hedgehog_in_cage/prepare_assets.py](../../../topogym/assets/generators/hedgehog_in_cage/prepare_assets.py)

- 模块函数：`main`（L6）。

### [topogym/assets/generators/hedgehog_in_cage/prepare_prototypes.py](../../../topogym/assets/generators/hedgehog_in_cage/prepare_prototypes.py)

- 模块函数：`sha`（L19）；`save`（L23）；`prepare`（L27）。

### [topogym/assets/generators/horseshoe_ring/geometry.py](../../../topogym/assets/generators/horseshoe_ring/geometry.py)

- 类：`Loop`（L58）；`Body`（L85）；`HorseshoeAssembly`（L149）。
- 模块函数：`load_template`（L25）；`ellipse`（L29）；`tube_mesh`（L34）；`band_centerline`（L94）；`horseshoe_band`（L116）；`sample_segments`（L279）；`point_segment_distance`（L287）；`geometry_report`（L295）；`write_body`（L348）；`generate_assets`（L392）。
- 类方法：`Loop.points`（L67）；`Loop.linking`（L70）；`HorseshoeAssembly.__init__`（L150，私有）；`HorseshoeAssembly.topology_report`（L248）。

### [topogym/assets/generators/interlocked_claws/family_models.py](../../../topogym/assets/generators/interlocked_claws/family_models.py)

- 类：`Part`（L43）；`Segment`（L53）；`FamilyModel`（L71）。
- 模块函数：`pose`（L21）；`rot`（L29）；`box`（L33）；`box_mesh`（L38）；`geometry_audit`（L283）。
- 类方法：`Segment.at`（L59）；`Segment.rotation_angle`（L67）；`FamilyModel.__init__`（L72，私有）；`FamilyModel._helical_crown`（L95，私有）；`FamilyModel._orthogonal_gate`（L127，私有）；`FamilyModel._helical_claws_balanced_v2`（L156，私有）；`FamilyModel._orthogonal_gate_balanced_v2`（L193，私有）；`FamilyModel.relative_pose`（L218）；`FamilyModel.negative_paths`（L226）；`FamilyModel.save`（L247）。
- 函数内局部声明：`FamilyModel._helical_crown.center`（L105，私有）；`FamilyModel._helical_claws_balanced_v2.center`（L172，私有）；`geometry_audit.gap`（L291）；`geometry_audit.bound`（L297）。

### [topogym/assets/generators/interlocked_claws/geometry.py](../../../topogym/assets/generators/interlocked_claws/geometry.py)

- 类：`ClawBody`（L55）；`ClawAssembly`（L63）。
- 模块函数：`load_reference`（L23）；`reference_body_poses`（L27）；`geometry_report`（L97）；`generate_assets`（L129）。
- 类方法：`ClawAssembly.__init__`（L64，私有）；`ClawAssembly.world_meshes`（L93）。

### [topogym/assets/generators/knot_untying/geometry.py](../../../topogym/assets/generators/knot_untying/geometry.py)

- 类：`KnotLayout`（L23）。
- 模块函数：`projected_crossings`（L108）；`minimum_nonlocal_distance`（L131）；`template_diagram_matches`（L165）；`inspect_geometry`（L180）；`generate_assets`（L226）。
- 类方法：`KnotLayout.__post_init__`（L35，私有）；`KnotLayout.centerline`（L54）。
- 函数内局部声明：`KnotLayout.centerline.tail`（L79）；`projected_crossings.cross`（L111）。

### [topogym/assets/generators/knot_untying/prepare_assets.py](../../../topogym/assets/generators/knot_untying/prepare_assets.py)

- 模块函数：`main`（L8）。

### [topogym/assets/generators/lock_picking/_aperture_outline.py](../../../topogym/assets/generators/lock_picking/_aperture_outline.py)

- 模块函数：`disc_colors`（L19）；`paint_aperture_outline`（L27）。

### [topogym/assets/generators/lock_picking/_staged_lock_geometry.py](../../../topogym/assets/generators/lock_picking/_staged_lock_geometry.py)

- 类：`LockGeometry`（L21）。
- 模块函数：`angle_error`（L16）；`variant_geometry`（L94）；`annulus`（L116）；`sector`（L133）；`rounded_square_radius`（L139）；`disc_assets`（L150）；`inertial`（L182）；`mesh_xml`（L186）；`write_disc`（L191）；`write_endpoint`（L215）；`goal_mark_assets`（L224）；`write_key`（L266）；`key_rest_layout`（L315）；`write_key_cradle`（L325）。
- 类方法：`LockGeometry.from_config`（L43）；`LockGeometry.validate`（L51）；`LockGeometry.tip_x`（L64）；`LockGeometry.disc_x`（L67）；`LockGeometry.grip_pos`（L70）；`LockGeometry.slot_margin`（L73）；`LockGeometry.clearance`（L76）。
- 函数内局部声明：`disc_assets.inner`（L152）；`disc_assets.outer`（L155）。

### [topogym/assets/generators/lock_picking/_staged_lock_limits.py](../../../topogym/assets/generators/lock_picking/_staged_lock_limits.py)

- 模块函数：`limit_assets`（L12）。
- 函数内局部声明：`limit_assets.add`（L33）；`limit_assets.arc`（L39）；`limit_assets.visual_xml`（L71）。

### [topogym/assets/generators/lock_picking/_staged_lock_ring.py](../../../topogym/assets/generators/lock_picking/_staged_lock_ring.py)

- 模块函数：`slot_profile`（L13）；`ring_limit_assets`（L34）。
- 函数内局部声明：`ring_limit_assets.visual`（L46）；`ring_limit_assets.collision`（L50）；`ring_limit_assets.solid`（L57）；`ring_limit_assets.profile`（L60）；`ring_limit_assets.export`（L122）。

### [topogym/assets/generators/orbits/geometry.py](../../../topogym/assets/generators/orbits/geometry.py)

- 类：`OrbitsLayout`（L23）。
- 模块函数：`tube_mesh`（L111）；`cord_centerline`（L138）；`make_meshes`（L169）；`winding_numbers`（L196）；`geometry_report`（L208）；`finish`（L266）；`generate_assets`（L290）。
- 类方法：`OrbitsLayout.post_x`（L47）；`OrbitsLayout.ring_x`（L51）；`OrbitsLayout.ring_z`（L55）；`OrbitsLayout.ball_z`（L59）；`OrbitsLayout.eyes`（L63）；`OrbitsLayout.scaled`（L67）；`OrbitsLayout.validate`（L77）。

### [topogym/assets/generators/rope_threading/geometry.py](../../../topogym/assets/generators/rope_threading/geometry.py)

- 类：`ThreadingLayout`（L14）。
- 模块函数：`route_crossings`（L86）；`surface_intersects_ring_disk`（L114）；`ring_mesh`（L149）；`_material`（L157，私有）；`inspect_geometry`（L164）；`generate_assets`（L205）。
- 类方法：`ThreadingLayout.__post_init__`（L22，私有）；`ThreadingLayout.reference`（L35）；`ThreadingLayout.radius`（L39）；`ThreadingLayout.rope_radius_m`（L43）；`ThreadingLayout.transform`（L47）；`ThreadingLayout.centerline`（L50）；`ThreadingLayout.rings`（L81）。
- 函数内局部声明：`surface_intersects_ring_disk.segment_distance`（L126）。

### [topogym/assets/generators/rope_threading/prepare_assets.py](../../../topogym/assets/generators/rope_threading/prepare_assets.py)

- 模块函数：`main`（L9）。

### [topogym/assets/generators/slotted_post_ring/geometry.py](../../../topogym/assets/generators/slotted_post_ring/geometry.py)

- 类：`SlottedPostLayout`（L23）。
- 模块函数：`_extrude_xz`（L111，私有）；`centerline`（L119）；`tube_mesh`（L134）；`_bead`（L162，私有）；`make_meshes`（L176）；`geometry_report`（L206）；`_finish`（L258，私有）；`generate_assets`（L286）。
- 类方法：`SlottedPostLayout.ring_inner_radius`（L43）；`SlottedPostLayout.ring_z`（L47）；`SlottedPostLayout.validate`（L50）；`SlottedPostLayout.post_polygon`（L81）；`SlottedPostLayout.cord_controls`（L90）。

### [topogym/assets/loaders/cast_keyhole/variant_assets.py](../../../topogym/assets/loaders/cast_keyhole/variant_assets.py)

- 模块函数：`require_variant`（L16）；`generate_variant_assets`（L37）。

### [topogym/assets/loaders/interlocked_claws/reference.py](../../../topogym/assets/loaders/interlocked_claws/reference.py)

- 类：`ReferenceMotion`（L15）。
- 类方法：`ReferenceMotion.__init__`（L16，私有）；`ReferenceMotion.control`（L33）；`ReferenceMotion.sample`（L47）。

### [topogym/assets/loaders/rope_threading/reference.py](../../../topogym/assets/loaders/rope_threading/reference.py)

- 模块函数：`extract`（L17）；`main`（L85）。
- 函数内局部声明：`extract.array`（L25）。

### [topogym/assets/loaders/rope_threading/reference_motion.py](../../../topogym/assets/loaders/rope_threading/reference_motion.py)

- 模块函数：`load_motion`（L11）；`main`（L51）。
- 函数内局部声明：`load_motion.array`（L26）。

### [topogym/assets/manifests/lock_picking/source_manifest.json](../../../topogym/assets/manifests/lock_picking/source_manifest.json)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/assets/robot.py](../../../topogym/assets/robot.py)

- 模块函数：`tool_model`（L18）；`robot_asset`（L22）；`build_tabletop_aloha`（L41）；`build_robotiq_panda`（L85）。

### [topogym/assets/textures.py](../../../topogym/assets/textures.py)

- 模块函数：`fabric_weave`（L33）；`_base_colour`（L135，私有）；`_paint_corners`（L172，私有）；`_cells`（L209，私有）；`_smooth_noise`（L216，私有）；`_bilinear`（L236，私有）；`_write_png`（L250，私有）。

### [topogym/assets/variants/buzz_wire_3d/compact.py](../../../topogym/assets/variants/buzz_wire_3d/compact.py)

- 模块函数：`scaled_layout`（L17）；`prepare`（L56）；`main`（L132）。

### [topogym/assets/variants/cast_coil/inverse_design.py](../../../topogym/assets/variants/cast_coil/inverse_design.py)

- 类：`ScrewMotion`（L55）。
- 模块函数：`family_parameter`（L40）；`variant_route`（L66）；`sample_route`（L124）；`synthesize`（L136）。
- 类方法：`ScrewMotion.pose`（L58）；`ScrewMotion.point_speed_bound`（L62）。

### [topogym/assets/variants/cast_coil/variants.py](../../../topogym/assets/variants/cast_coil/variants.py)

- 模块函数：`canonical`（L34）；`fingerprint`（L38）；`catalog`（L42）；`profile_cuts`（L53）；`_profile`（L90，私有）；`derive`（L119）；`validate_parameters`（L197）；`_base_config`（L224，私有）；`sample`（L231）；`check_geometry`（L313）；`generate`（L422）；`load_instance`（L515）。

### [topogym/assets/variants/cast_keyhole/eccentric_window.py](../../../topogym/assets/variants/cast_keyhole/eccentric_window.py)

- 模块函数：`propose`（L23）；`infer`（L54）；`generate`（L116）；`main`（L145）。

### [topogym/assets/variants/cast_keyhole/family_variants.py](../../../topogym/assets/variants/cast_keyhole/family_variants.py)

- 模块函数：`ellipse`（L39）；`envelope`（L43）；`parameters`（L60）；`normalize_outer_stock`（L69）；`family_seed`（L79）；`build`（L100）；`qualify_geometry`（L189）；`overview`（L212）；`main`（L236）。

### [topogym/assets/variants/cast_keyhole/inverse_variants.py](../../../topogym/assets/variants/cast_keyhole/inverse_variants.py)

- 模块函数：`save`（L35）；`sha`（L40）；`pack`（L43）；`polygon_record`（L46）；`geometry_from_record`（L50）；`proposal`（L66）；`plan_ik`（L104）；`motions_from_trace`（L137）；`sweep_polygons`（L144）；`inverse_geometry`（L179）；`certify_variant`（L224）；`check_robot`（L264）；`overview`（L286）；`generate`（L298）；`main`（L309）。

### [topogym/assets/variants/cast_keyhole/long_stroke.py](../../../topogym/assets/variants/cast_keyhole/long_stroke.py)

- 模块函数：`relative`（L24）；`propose`（L30）；`plan`（L58）；`infer`（L93）；`main`（L141）。

### [topogym/assets/variants/cast_keyhole/turnback.py](../../../topogym/assets/variants/cast_keyhole/turnback.py)

- 模块函数：`propose`（L25）；`infer`（L68）；`controls`（L115）；`generate`（L142）；`main`（L171）。
- 函数内局部声明：`controls.sampled`（L123）；`controls.shortcut`（L129）。

### [topogym/assets/variants/cast_keyhole/variants.py](../../../topogym/assets/variants/cast_keyhole/variants.py)

- 模块函数：`canonical`（L39）；`digest`（L43）；`file_sha`（L47）；`save`（L51）；`_base_config`（L56，私有）；`catalog`（L62）；`validate_parameters`（L74）；`_integer`（L88，私有）；`implementation`（L94）；`sample`（L100）；`check_spec`（L161）；`_new_output`（L179，私有）；`prepare`（L188）；`generate`（L217）；`main`（L241）。

### [topogym/assets/variants/fiber_bundling/generation.py](../../../topogym/assets/variants/fiber_bundling/generation.py)

- 类：`GenerationRejected`（L50）。
- 模块函数：`digest`（L26）；`file_sha`（L31）；`configuration`（L35）；`generator_sources`（L42）；`build_episode`（L56）；`save_instance`（L124）；`load_instance`（L147）；`main`（L176）。
- 类方法：`GenerationRejected.__init__`（L51，私有）。

### [topogym/assets/variants/fiber_bundling/variants.py](../../../topogym/assets/variants/fiber_bundling/variants.py)

- 模块函数：`rules`（L18）；`sample_parameters`（L22）；`candidate_config`（L42）；`validate_parameters`（L52）；`inspect_candidate`（L74）；`generate_candidate`（L103）；`main`（L123）。

### [topogym/assets/variants/hedgehog_in_cage/classic_families.py](../../../topogym/assets/variants/hedgehog_in_cage/classic_families.py)

- 模块函数：`gen_cage`（L27）；`assets`（L60）；`plan`（L111）；`robot_plan`（L145）；`stable_release`（L189）；`controls`（L217）；`certify`（L226）。

### [topogym/assets/variants/hedgehog_in_cage/inverse_window.py](../../../topogym/assets/variants/hedgehog_in_cage/inverse_window.py)

- 类：`Kinematics`（L41）；`SolidOracle`（L271）。
- 模块函数：`sha`（L27）；`save`（L31）；`config`（L37）；`propose`（L93）；`inverse_profile`（L127）；`inferred_cells`（L217）；`export_geometry`（L245）；`certify`（L295）；`main`（L326）。
- 类方法：`Kinematics.__init__`（L42，私有）；`Kinematics.forward`（L59）；`Kinematics.ball_pose`（L64）；`Kinematics.solve`（L70）；`SolidOracle.__init__`（L272，私有）；`SolidOracle.distance`（L286）。
- 函数内局部声明：`Kinematics.solve.error`（L75）。

### [topogym/assets/variants/hedgehog_in_cage/variants.py](../../../topogym/assets/variants/hedgehog_in_cage/variants.py)

- 类：`GenerationRejected`（L357）。
- 模块函数：`canonical`（L37）；`fingerprint`（L41）；`file_sha`（L45）；`save`（L49）；`inside`（L53）；`_json_content`（L61，私有）；`prototype`（L68）；`rules`（L87）；`generator_version`（L94）；`families_for_version`（L98）；`derive`（L104）；`validate_parameters`（L125）；`choose_family`（L140）；`configuration`（L150）；`identity`（L159）；`sample`（L164）；`_validate_spec`（L236，私有）；`materialize`（L271）；`_spec_from_dict`（L312，私有）；`load_instance`（L322）；`generate`（L363）。
- 类方法：`GenerationRejected.__init__`（L358，私有）。

### [topogym/assets/variants/horseshoe_ring/fixed_trace_variants.py](../../../topogym/assets/variants/horseshoe_ring/fixed_trace_variants.py)

- 模块函数：`variant_template`（L28）；`verify_immutable_geometry`（L39）；`write_json`（L51）；`screen`（L55）；`evaluate`（L77）；`run`（L129）；`main`（L174）。

### [topogym/assets/variants/horseshoe_ring/shape_neighborhood.py](../../../topogym/assets/variants/horseshoe_ring/shape_neighborhood.py)

- 类：`ShapeNeighborhood`（L39）。
- 模块函数：`digest`（L19）；`body_change_bound`（L23）。
- 类方法：`ShapeNeighborhood.__init__`（L40，私有）；`ShapeNeighborhood.assess`（L64）；`ShapeNeighborhood.materialize`（L89）。

### [topogym/assets/variants/horseshoe_ring/shape_sampler.py](../../../topogym/assets/variants/horseshoe_ring/shape_sampler.py)

- 模块函数：`load_references`（L25）；`propose`（L54）；`sample`（L73）；`main`（L120）。

### [topogym/assets/variants/horseshoe_ring/trace_scene_variants.py](../../../topogym/assets/variants/horseshoe_ring/trace_scene_variants.py)

- 模块函数：`legacy_hash`（L31）；`inverse_initial_similarity`（L35）；`relative_pose`（L51）；`infer_body_from_grasp`（L56）；`wave`（L61）；`placement_weight`（L65）；`scale_fingers`（L71）；`adjusted_tips`（L76）；`common_pose`（L89）；`load_seed`（L100）；`generate`（L130）；`main`（L340）。

### [topogym/assets/variants/horseshoe_ring/variant_generator.py](../../../topogym/assets/variants/horseshoe_ring/variant_generator.py)

- 模块函数：`digest`（L29）；`file_hash`（L34）；`derive`（L38）；`validate_parameters`（L69）；`create_instance`（L91）；`validate_instance`（L154）；`retarget_seed`（L179）；`main`（L218）。
- 函数内局部声明：`derive.delta`（L41）；`derive.around`（L49）。

### [topogym/assets/variants/interlocked_claws/variants.py](../../../topogym/assets/variants/interlocked_claws/variants.py)

- 类：`FamilyUnavailable`（L44）；`DatasetNotReady`（L48）。
- 模块函数：`canonical`（L52）；`fingerprint`（L56）；`sha`（L60）；`_integer`（L64，私有）；`catalog`（L70）；`family_record`（L77）；`verify_sources`（L81）；`derive`（L90）；`validate_parameters`（L105）；`_base_config`（L127，私有）；`_identity`（L137，私有）；`_spec_digest`（L143，私有）；`sample`（L149）；`load_instance`（L203）；`assert_runtime_supported`（L232）；`transform_pose`（L243）；`ideal_pair_certificate`（L253）；`materialize`（L274）；`motion_targets`（L329）；`prepare_episode`（L337）；`generate`（L351）；`main`（L393）。

### [topogym/assets/variants/knot_untying/families.py](../../../topogym/assets/variants/knot_untying/families.py)

- 模块函数：`template_variant`（L33）；`template_config`（L41）；`apply_family`（L50）。

### [topogym/assets/variants/lock_picking/inverse_variants.py](../../../topogym/assets/variants/lock_picking/inverse_variants.py)

- 类：`ArmIK`（L147）。
- 模块函数：`dump`（L38）；`motion_variant`（L42）；`infer_geometry`（L82）；`analytic_route_check`（L99）；`export_assets`（L224）；`build`（L239）。
- 类方法：`ArmIK.__init__`（L148，私有）；`ArmIK.solve`（L171）；`ArmIK.route`（L194）。
- 函数内局部声明：`motion_variant.append`（L48）。

### [topogym/assets/variants/lock_picking/variants.py](../../../topogym/assets/variants/lock_picking/variants.py)

- 模块函数：`plain`（L43）；`canonical`（L47）；`fingerprint`（L51）；`sha`（L55）；`save`（L59）；`catalog`（L63）；`prototype`（L67）；`derive`（L73）；`validate_parameters`（L114）；`base_config`（L134）；`sample`（L139）；`check_geometry`（L201）；`check_ik`（L220）；`generate`（L230）；`write_instance`（L253）；`load_instance`（L288）；`metadata_path`（L314）；`main`（L321）。

### [topogym/config/agent_profiles.py](../../../topogym/config/agent_profiles.py)

- 模块函数：`profile`（L4）。

### [topogym/config/agent_suite.py](../../../topogym/config/agent_suite.py)

- 模块函数：`digest`（L14）；`file_hash`（L19）；`identifier`（L23）；`resolve`（L29）；`prepare`（L34）；`load_suite`（L69）；`load_preset`（L91）；`source_hashes`（L101）；`prepare_counter`（L111）；`create_counter`（L118）；`prepare_cast_coil`（L141）。
- 函数内局部声明：`create_counter.ThreeViewCounter`（L121）；`create_counter.ThreeViewCounter.describe`（L122）；`create_counter.ThreeViewCounter.render`（L125）；`create_counter.ThreeViewCounter.evaluate`（L129）。

### [topogym/config/catalog.py](../../../topogym/config/catalog.py)

- 模块函数：`_lookup`（L23，私有）；`validate_card`（L29）；`load_card`（L68）；`baseline_manifest`（L78）；`main`（L89）。
- 函数内局部声明：`validate_card.finite`（L52）。

### [topogym/config/config.py](../../../topogym/config/config.py)

- 模块函数：`save_resolved_config`（L9）；`hydra_config_sources`（L49）。

### [topogym/config/episode_spec.py](../../../topogym/config/episode_spec.py)

- 类：`EpisodeStatus`（L9）；`EpisodeKey`（L29）；`ScenePreset`（L45）；`TaskVariant`（L60）；`TaskLayout`（L84）；`ExecutionProfile`（L101）；`EpisodeSpec`（L114）；`EpisodeArtifact`（L140）；`EpisodeResult`（L152）。
- 模块函数：`_frozen_dict`（L24，私有）。
- 类方法：`EpisodeKey.stable_id`（L37）；`ScenePreset.metadata_dict`（L55）；`TaskVariant.parameters_dict`（L79）；`TaskLayout.objects_dict`（L93）；`TaskLayout.metadata_dict`（L96）；`ExecutionProfile.parameters_dict`（L109）；`EpisodeSpec.task_id`（L125）；`EpisodeSpec.seed`（L129）；`EpisodeSpec.stable_id`（L132）；`EpisodeSpec.resolved_config_dict`（L135）；`EpisodeArtifact.metadata_dict`（L147）；`EpisodeResult.ok`（L165）；`EpisodeResult.failed`（L184）；`EpisodeResult.metrics_dict`（L205）。

### [topogym/config/layout_randomization.py](../../../topogym/config/layout_randomization.py)

- 类：`_ChoiceJitter`（L81，私有）；`_ScalarJitter`（L89，私有）；`_DistinctChoiceJitter`（L98，私有）；`_SpacedPairJitter`（L110，私有）；`_Derived`（L126，私有）；`_Validate`（L138，私有）。
- 模块函数：`_plain`（L159，私有）；`_parse_directives`（L166，私有）；`_resolve_fn`（L195，私有）；`has_variation`（L207）；`sampled_leaves`（L212）；`_get_node`（L230，私有）；`_set_node`（L238，私有）；`_same_type`（L245，私有）；`_apply`（L261，私有）；`_unlocked_copy`（L291，私有）；`randomize_task_cfg`（L299）。

### [topogym/config/registry.py](../../../topogym/config/registry.py)

- 模块函数：`factory_for`（L8）。

### [topogym/config/task_specs/buzz_wire_3d.py](../../../topogym/config/task_specs/buzz_wire_3d.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/cast_coil.py](../../../topogym/config/task_specs/cast_coil.py)

- 模块函数：`describe_task`（L4）。

### [topogym/config/task_specs/cast_keyhole.py](../../../topogym/config/task_specs/cast_keyhole.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/hedgehog_in_cage.py](../../../topogym/config/task_specs/hedgehog_in_cage.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/horseshoe_ring.py](../../../topogym/config/task_specs/horseshoe_ring.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/interlocked_claws.py](../../../topogym/config/task_specs/interlocked_claws.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/knot_untying.py](../../../topogym/config/task_specs/knot_untying.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/task_specs/lock_picking.py](../../../topogym/config/task_specs/lock_picking.py)

- 模块函数：`describe_task`（L5）。

### [topogym/config/tasks/cast_keyhole/family_catalog.py](../../../topogym/config/tasks/cast_keyhole/family_catalog.py)

- 模块函数：`design`（L18）；`freeze`（L42）；`main`（L74）。

### [topogym/config/tasks/fiber_bundling/run_config.py](../../../topogym/config/tasks/fiber_bundling/run_config.py)

- 模块函数：`load_run_config`（L7）。

### [topogym/config/variant_episode.py](../../../topogym/config/variant_episode.py)

- 模块函数：`_plain`（L73，私有）；`_get`（L79，私有）；`_path_text`（L86，私有）；`_flat_leaves`（L93，私有）；`resolve_instruction`（L116）；`resolve_goal_id`（L142）；`variant_parameters`（L165）；`build_variant_episode`（L180）。

### [topogym/data/__init__.py](../../../topogym/data/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/data/episode_dataset_writer.py](../../../topogym/data/episode_dataset_writer.py)

- 类：`EpisodeDatasetWriter`（L76）。
- 模块函数：`_as_numpy`（L15，私有）；`_grab_rgb`（L22，私有）；`_proprio`（L32，私有）；`_quat_to_rot6d`（L54，私有）；`dataset_writer_or_null`（L396）。
- 类方法：`EpisodeDatasetWriter.__init__`（L90，私有）；`EpisodeDatasetWriter.__enter__`（L131，私有）；`EpisodeDatasetWriter.__exit__`（L145，私有）；`EpisodeDatasetWriter.finalize`（L151）；`EpisodeDatasetWriter.start_capture`（L155）；`EpisodeDatasetWriter.stop_capture`（L169）；`EpisodeDatasetWriter._default_subgoal`（L179，私有）；`EpisodeDatasetWriter._capture`（L184，私有）；`EpisodeDatasetWriter._write`（L206，私有）；`EpisodeDatasetWriter._write_setup`（L262，私有）；`EpisodeDatasetWriter._write_variant`（L312，私有）；`EpisodeDatasetWriter._write_readings`（L332，私有）；`EpisodeDatasetWriter._write_timestep`（L351，私有）。
- 函数内局部声明：`EpisodeDatasetWriter.__enter__.wrapped_step`（L134，私有）。

### [topogym/data/exporters/horseshoe_ring/ik_trace.py](../../../topogym/data/exporters/horseshoe_ring/ik_trace.py)

- 模块函数：`canonical_hash`（L21）；`command_hash`（L26）；`export_trace`（L31）；`main`（L95）。

### [topogym/data/exporters/knot_untying/execution_metrics.py](../../../topogym/data/exporters/knot_untying/execution_metrics.py)

- 模块函数：`export_motion`（L12）。

### [topogym/data/h5_schema.py](../../../topogym/data/h5_schema.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/envs/adapters/base.py](../../../topogym/envs/adapters/base.py)

- 类：`CounterTask`（L15）；`GenesisAdapter`（L59）。
- 模块函数：`_png`（L8，私有）；`finite_vector`（L101）。
- 类方法：`CounterTask.__init__`（L17，私有）；`CounterTask.describe`（L20）；`CounterTask.validate_action`（L26）；`CounterTask.step`（L30）；`CounterTask.observe`（L33）；`CounterTask.render`（L36）；`CounterTask.evaluate`（L54）；`GenesisAdapter.__init__`（L65，私有）；`GenesisAdapter.observe`（L73）；`GenesisAdapter.describe`（L79）；`GenesisAdapter.step`（L82）；`GenesisAdapter.render`（L86）。
- 函数内局部声明：`_png.chunk`（L9，私有）。

### [topogym/envs/adapters/buzz_wire_3d.py](../../../topogym/envs/adapters/buzz_wire_3d.py)

- 类：`RailTraversal`（L47）；`BuzzWireAdapter`（L92）。
- 模块函数：`configuration`（L17）；`create`（L181）。
- 类方法：`RailTraversal.__init__`（L49，私有）；`RailTraversal.crossings`（L68）；`RailTraversal.update`（L77）；`BuzzWireAdapter.__init__`（L93，私有）；`BuzzWireAdapter._failure_and_goal`（L114，私有）。

### [topogym/envs/adapters/cast_coil.py](../../../topogym/envs/adapters/cast_coil.py)

- 模块函数：`create`（L5）。
- 函数内局部声明：`create.validate`（L44）；`create.apply`（L60）；`create.arr`（L67）；`create.evaluate`（L76）；`create.get_pose`（L130）；`create.get_state`（L140）。

### [topogym/envs/adapters/cast_keyhole.py](../../../topogym/envs/adapters/cast_keyhole.py)

- 类：`KeyholeAdapter`（L16）。
- 模块函数：`create`（L51）。
- 类方法：`KeyholeAdapter.__init__`（L17，私有）；`KeyholeAdapter._failure_and_goal`（L27，私有）。

### [topogym/envs/adapters/fem_robot.py](../../../topogym/envs/adapters/fem_robot.py)

- 类：`RopeGraspBank`（L20）；`FEMRobotAdapter`（L94）。
- 模块函数：`rotation`（L16）。
- 类方法：`RopeGraspBank.__init__`（L21，私有）；`RopeGraspBank.declare`（L26）；`RopeGraspBank.release`（L32）；`RopeGraspBank.drive`（L38）；`RopeGraspBank.try_attach`（L43）；`RopeGraspBank.close`（L88）；`FEMRobotAdapter.__init__`（L95，私有）；`FEMRobotAdapter._apply`（L107，私有）；`FEMRobotAdapter._public_observation`（L126，私有）；`FEMRobotAdapter._failure_and_goal`（L130，私有）；`FEMRobotAdapter.step`（L133）；`FEMRobotAdapter._evaluate`（L152，私有）；`FEMRobotAdapter.close`（L155）。

### [topogym/envs/adapters/hedgehog_in_cage.py](../../../topogym/envs/adapters/hedgehog_in_cage.py)

- 类：`HedgehogAdapter`（L39）。
- 模块函数：`configuration`（L18）；`create`（L101）。
- 类方法：`HedgehogAdapter.__init__`（L40，私有）；`HedgehogAdapter._failure_and_goal`（L58，私有）。

### [topogym/envs/adapters/horseshoe_ring.py](../../../topogym/envs/adapters/horseshoe_ring.py)

- 类：`HorseshoeAdapter`（L16）。
- 模块函数：`create`（L62）。
- 类方法：`HorseshoeAdapter.__init__`（L17，私有）；`HorseshoeAdapter._failure_and_goal`（L25，私有）。

### [topogym/envs/adapters/interlocked_claws.py](../../../topogym/envs/adapters/interlocked_claws.py)

- 类：`ClawsAdapter`（L41）。
- 模块函数：`configuration`（L17）；`create`（L108）。
- 类方法：`ClawsAdapter.__init__`（L42，私有）；`ClawsAdapter._failure_and_goal`（L55，私有）。

### [topogym/envs/adapters/knot_untying.py](../../../topogym/envs/adapters/knot_untying.py)

- 类：`KnotAdapter`（L54）。
- 模块函数：`configuration`（L16）；`planar_clear`（L43）；`create`（L109）。
- 类方法：`KnotAdapter.__init__`（L55，私有）；`KnotAdapter._failure_and_goal`（L59，私有）。
- 函数内局部声明：`create.observed`（L141）。

### [topogym/envs/adapters/lock_picking.py](../../../topogym/envs/adapters/lock_picking.py)

- 类：`LockPickingAdapter`（L35）。
- 模块函数：`configuration`（L12）；`create`（L102）。
- 类方法：`LockPickingAdapter.__init__`（L36，私有）；`LockPickingAdapter._failure_and_goal`（L50，私有）。

### [topogym/envs/adapters/rigid_robot.py](../../../topogym/envs/adapters/rigid_robot.py)

- 类：`StableVerdict`（L40）；`RigidRobotAdapter`（L60）；`AlohaRigidAdapter`（L174）。
- 模块函数：`array`（L14）；`supported_bodies`（L18）。
- 类方法：`StableVerdict.__init__`（L42，私有）；`StableVerdict.update`（L47）；`RigidRobotAdapter.__init__`（L61，私有）；`RigidRobotAdapter._failure_and_goal`（L90，私有）；`RigidRobotAdapter._contacts`（L95，私有）；`RigidRobotAdapter._replace`（L100，私有）；`RigidRobotAdapter._apply`（L116，私有）；`RigidRobotAdapter._public_observation`（L135，私有）；`RigidRobotAdapter.step`（L142）；`RigidRobotAdapter._evaluate`（L167，私有）。
- 函数内局部声明：`supported_bodies.visit`（L29）。

### [topogym/envs/episode_runner.py](../../../topogym/envs/episode_runner.py)

- 类：`EpisodeRunOptions`（L12）；`EpisodeRunContext`（L22）；`EpisodeRunner`（L30）。
- 类方法：`EpisodeRunner.run`（L33）。

### [topogym/envs/execution/blanket_flatten/execution.py](../../../topogym/envs/execution/blanket_flatten/execution.py)

- 类：`Execution`（L16）。
- 模块函数：`array`（L12）。
- 类方法：`Execution.__init__`（L17，私有）；`Execution.time`（L48）；`Execution.label`（L51）；`Execution.capture`（L56）；`Execution.step`（L63）；`Execution.wait`（L118）；`Execution.initialize`（L122）；`Execution.verify_passive_stability`（L141）；`Execution.check_robot_clearance`（L163）；`Execution.tcp`（L177）；`Execution.move`（L182）；`Execution.hold_tcp`（L204）；`Execution.select_corner`（L211）；`Execution.recenter`（L216）；`Execution.pull`（L239）；`Execution.flatten`（L347）；`Execution.refine`（L423）；`Execution.final_check`（L461）；`Execution.save`（L479）。

### [topogym/envs/execution/buzz_wire_3d/robot_runtime.py](../../../topogym/envs/execution/buzz_wire_3d/robot_runtime.py)

- 模块函数：`execute`（L22）；`main`（L882）。
- 函数内局部声明：`execute.pose`（L219）；`execute.mechanical_energy`（L224）；`execute.record`（L234）；`execute.step`（L265）；`execute.free_motion`（L393）；`execute.update_feedback`（L536）；`execute.held_motion`（L571）。

### [topogym/envs/execution/cast_keyhole/robot_execution.py](../../../topogym/envs/execution/cast_keyhole/robot_execution.py)

- 模块函数：`run`（L26）；`main`（L128）。
- 函数内局部声明：`run.state`（L70）。

### [topogym/envs/execution/cast_keyhole/variant_runner.py](../../../topogym/envs/execution/cast_keyhole/variant_runner.py)

- 类：`KeyholeVariantRunner`（L27）。
- 模块函数：`load_spec`（L17）；`main`（L82）。
- 类方法：`KeyholeVariantRunner.__init__`（L28，私有）；`KeyholeVariantRunner.run`（L32）。

### [topogym/envs/execution/cast_keyhole/variant_runtime.py](../../../topogym/envs/execution/cast_keyhole/variant_runtime.py)

- 模块函数：`load_instance`（L29）；`configuration`（L49）；`build_scene`（L56）；`set_objects`（L95）；`actual_objects`（L103）；`execute`（L112）；`audit`（L181）；`recording_motion`（L214）；`render`（L231）；`main`（L240）。

### [topogym/envs/execution/fiber_bundling/robot_sequence.py](../../../topogym/envs/execution/fiber_bundling/robot_sequence.py)

- 类：`RobotSequence`（L64）。
- 模块函数：`smooth`（L25）；`bundle_fit`（L29）；`grasp_health`（L45）；`touching_grasp_fingers`（L56）；`main`（L544）。
- 类方法：`RobotSequence.__init__`（L65，私有）；`RobotSequence.record`（L171）；`RobotSequence.save`（L182）；`RobotSequence.step`（L189）；`RobotSequence.finish_phase`（L263）；`RobotSequence.hold`（L274）；`RobotSequence.command_hand`（L280）；`RobotSequence.move_hand`（L296）；`RobotSequence.close_and_attach`（L312）；`RobotSequence.calibrate_grasp`（L340）；`RobotSequence.grasp`（L350）；`RobotSequence.move_cable`（L380）；`RobotSequence.prepare`（L414）；`RobotSequence.prepare_orbit`（L439）；`RobotSequence.record_preparation`（L468）；`RobotSequence.align_and_check_bundle`（L482）；`RobotSequence.run`（L496）；`RobotSequence.finish_report`（L524）。

### [topogym/envs/execution/hedgehog_in_cage/family_guided_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/family_guided_runtime.py)

- 模块函数：`execute`（L10）；`main`（L164）。
- 函数内局部声明：`execute.pose`（L43）；`execute.record`（L44）；`execute.step`（L50）；`execute.drive_hand`（L65）；`execute.drive_hand.residual`（L71）；`execute.move`（L89）。

### [topogym/envs/execution/hedgehog_in_cage/family_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/family_runtime.py)

- 类：`RobotAudit`（L41）。
- 模块函数：`admitted`（L25）；`plan_audit`（L103）；`build_scene`（L121）；`execute`（L178）；`audit`（L303）；`render`（L344）；`main`（L350）。
- 类方法：`RobotAudit.__init__`（L42，私有）；`RobotAudit.depth`（L70）；`RobotAudit.check`（L75）。
- 函数内局部声明：`execute.pose`（L209）；`execute.record`（L210）；`execute.step`（L216）；`execute.drive_hand`（L231）；`execute.move`（L239）。

### [topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/inverse_runtime.py)

- 类：`RobotAudit`（L39）。
- 模块函数：`admitted`（L23）；`plan_audit`（L101）；`build_scene`（L119）；`execute`（L170）；`audit`（L293）；`render`（L333）；`main`（L339）。
- 类方法：`RobotAudit.__init__`（L40，私有）；`RobotAudit.depth`（L68）；`RobotAudit.check`（L73）。
- 函数内局部声明：`execute.pose`（L199）；`execute.record`（L200）；`execute.step`（L206）；`execute.drive_hand`（L221）；`execute.move`（L229）。

### [topogym/envs/execution/hedgehog_in_cage/variant_runtime.py](../../../topogym/envs/execution/hedgehog_in_cage/variant_runtime.py)

- 模块函数：`build_scene`（L23）。

### [topogym/envs/execution/horseshoe_ring/physical_motion.py](../../../topogym/envs/execution/horseshoe_ring/physical_motion.py)

- 类：`PhysicalMotion`（L22）。
- 类方法：`PhysicalMotion.__init__`（L23，私有）；`PhysicalMotion.body_pose`（L121）；`PhysicalMotion.hand_pose`（L125）；`PhysicalMotion.contacts`（L130）；`PhysicalMotion.grasp_connected`（L134）；`PhysicalMotion.replace_grasps`（L158）；`PhysicalMotion.capture`（L183）；`PhysicalMotion.step`（L206）；`PhysicalMotion.joint_segment`（L241）；`PhysicalMotion.hold`（L252）；`PhysicalMotion.cartesian`（L255）；`PhysicalMotion.follow_old_fold`（L273）；`PhysicalMotion.transform_pair`（L283）；`PhysicalMotion.goal_state`（L300）；`PhysicalMotion.finish`（L320）。
- 函数内局部声明：`PhysicalMotion.grasp_connected.visit`（L148）。

### [topogym/envs/execution/lock_picking/runner.py](../../../topogym/envs/execution/lock_picking/runner.py)

- 模块函数：`move`（L35）；`open_before_withdrawal`（L49）；`execute`（L81）；`run`（L163）；`main`（L404）。
- 函数内局部声明：`run.snapshot`（L198）；`run.frame_bounds`（L204）；`run.arm_framing`（L224）；`run.mechanism_framing`（L227）；`run.aperture_framing`（L231）；`run.step`（L292）。

### [topogym/envs/initialization/blanket_flatten/initial_state.py](../../../topogym/envs/initialization/blanket_flatten/initial_state.py)

- 模块函数：`restore_selected_shape`（L12）。

### [topogym/envs/initialization/blanket_flatten/preparation.py](../../../topogym/envs/initialization/blanket_flatten/preparation.py)

- 类：`MaterialVelocityProjection`（L14）。
- 模块函数：`rotate_vectors`（L71）；`fold_target`（L79）；`arc_fold_target`（L93）；`twist_target`（L118）；`prepare`（L132）。
- 类方法：`MaterialVelocityProjection.__init__`（L21，私有）；`MaterialVelocityProjection.project`（L28）。
- 函数内局部声明：`prepare.servo`（L157）；`prepare.drive`（L173）；`prepare.target`（L213）。

### [topogym/envs/protocol.py](../../../topogym/envs/protocol.py)

- 类：`TaskAdapter`（L5）。
- 类方法：`TaskAdapter.describe`（L6）；`TaskAdapter.validate_action`（L14）；`TaskAdapter.step`（L17）；`TaskAdapter.observe`（L20）；`TaskAdapter.render`（L23）；`TaskAdapter.evaluate`（L26）。

### [topogym/envs/task_support/cast_coil/assembly_task.py](../../../topogym/envs/task_support/cast_coil/assembly_task.py)

- 类：`ReverseMotion`（L56）。
- 模块函数：`assembly_phase_name`（L20）；`required_assembly_phases`（L26）；`route_lift`（L34）；`initial_poses`（L76）；`xy_surface_gaps`（L94）；`motions`（L103）；`goal_metrics`（L126）。
- 类方法：`ReverseMotion.duration_s`（L61）；`ReverseMotion.pose`（L64）；`ReverseMotion.point_speed_bound`（L67）；`ReverseMotion.to_dict`（L70）。

### [topogym/evaluation/agents/evaluate.py](../../../topogym/evaluation/agents/evaluate.py)

- 模块函数：`summarize`（L12）；`evaluate`（L44）。

### [topogym/evaluation/agents/initial.py](../../../topogym/evaluation/agents/initial.py)

- 模块函数：`audit_initial`（L8）。

### [topogym/evaluation/diagnostics/pbd_probe.py](../../../topogym/evaluation/diagnostics/pbd_probe.py)

- 类：`StepProbe`（L77）。
- 模块函数：`probe_particles`（L30）；`probe_velocities`（L42）；`ejected_mask`（L59）；`max_particle_jump`（L65）。
- 类方法：`StepProbe.__init__`（L88，私有）；`StepProbe._wrapped_step`（L101，私有）；`StepProbe._sample`（L108，私有）；`StepProbe.uninstall`（L111）；`StepProbe.__enter__`（L118，私有）；`StepProbe.__exit__`（L121，私有）。

### [topogym/evaluation/diagnostics/rope_stability.py](../../../topogym/evaluation/diagnostics/rope_stability.py)

- 类：`ParticleSpacingReport`（L21）；`RopeBlowUp`（L82）。
- 模块函数：`particle_spacing_reports`（L58）；`rope_blow_ups`（L97）。
- 类方法：`ParticleSpacingReport.is_consistent`（L45）；`ParticleSpacingReport.__str__`（L48，私有）；`RopeBlowUp.__str__`（L90，私有）。

### [topogym/evaluation/diagnostics/rope_trace.py](../../../topogym/evaluation/diagnostics/rope_trace.py)

- 类：`RopeTrace`（L114）。
- 模块函数：`min_bend_radius`（L41）；`_points_to_segments`（L65，私有）；`polyline_gap`（L77）；`height_over`（L91）。
- 类方法：`RopeTrace.__init__`（L130，私有）；`RopeTrace._centerline_scale_lines`（L184，私有）；`RopeTrace.note`（L224）；`RopeTrace._write`（L230，私有）；`RopeTrace._sample`（L238，私有）；`RopeTrace._check_tightening`（L363，私有）；`RopeTrace.close`（L380）；`RopeTrace.__exit__`（L386，私有）。

### [topogym/evaluation/diagnostics/stability.py](../../../topogym/evaluation/diagnostics/stability.py)

- 类：`StabilityLimits`（L8）；`StabilitySample`（L19）；`StabilityDecision`（L35）。
- 模块函数：`evaluate_stability_sample`（L48）；`format_stability_decision`（L124）。
- 类方法：`StabilitySample.metadata_dict`（L30）；`StabilityDecision.should_abort`（L44）。

### [topogym/evaluation/tasks/blanket_flatten/bimanual_review.py](../../../topogym/evaluation/tasks/blanket_flatten/bimanual_review.py)

- 模块函数：`review_initial_identity`（L14）；`review`（L44）。
- 函数内局部声明：`review.set_qpos`（L55）。

### [topogym/evaluation/tasks/blanket_flatten/diagnostics.py](../../../topogym/evaluation/tasks/blanket_flatten/diagnostics.py)

- 类：`AcceptanceWindow`（L125）。
- 模块函数：`binding_audit`（L8）；`footprint_area`（L49）；`measure`（L68）；`health_gates`（L90）；`settled`（L99）；`initial_gates`（L105）；`flatten_gates`（L114）。
- 类方法：`AcceptanceWindow.__init__`（L128，私有）；`AcceptanceWindow.update`（L135）。

### [topogym/evaluation/tasks/blanket_flatten/review_preparation.py](../../../topogym/evaluation/tasks/blanket_flatten/review_preparation.py)

- 模块函数：`review`（L9）。

### [topogym/evaluation/tasks/buzz_wire_3d/qualification.py](../../../topogym/evaluation/tasks/buzz_wire_3d/qualification.py)

- 模块函数：`sha`（L15）；`physics_signature`（L19）；`physical_assets_signature`（L32）；`select_frames`（L47）。
- 函数内局部声明：`physics_signature.node`（L26）。

### [topogym/evaluation/tasks/buzz_wire_3d/robot_verify.py](../../../topogym/evaluation/tasks/buzz_wire_3d/robot_verify.py)

- 模块函数：`compare`（L17）；`main`（L239）。

### [topogym/evaluation/tasks/buzz_wire_3d/verification.py](../../../topogym/evaluation/tasks/buzz_wire_3d/verification.py)

- 类：`ClearanceOracle`（L19）。
- 模块函数：`sample_capsules`（L10）；`verify_route`（L77）。
- 类方法：`ClearanceOracle.__init__`（L20，私有）；`ClearanceOracle.clearance`（L46）。
- 函数内局部声明：`verify_route.refine`（L92）。

### [topogym/evaluation/tasks/buzz_wire_3d/verify_physics.py](../../../topogym/evaluation/tasks/buzz_wire_3d/verify_physics.py)

- 模块函数：`plot_results`（L16）；`verify`（L75）；`main`（L170）。

### [topogym/evaluation/tasks/cast_coil/qualify.py](../../../topogym/evaluation/tasks/cast_coil/qualify.py)

- 模块函数：`compare_profiles`（L27）；`failure_diagnostics`（L54）；`release_rotation_diagnostics`（L86）；`export_variants`（L113）；`evidence_matches_geometry`（L131）；`write_review`（L147）；`plot_diagnostics`（L217）；`summarize`（L267）；`main`（L314）。

### [topogym/evaluation/tasks/cast_coil/verification.py](../../../topogym/evaluation/tasks/cast_coil/verification.py)

- 类：`CompoundCollision`（L29）；`Motion`（L60）。
- 模块函数：`box_corners`（L54）；`prototype_route`（L88）；`assembly_route`（L100）；`certify_motion`（L113）；`geometric_audit`（L155）；`write_geometric_audit`（L190）；`shape_sensitivity_audit`（L200）。
- 类方法：`CompoundCollision.__init__`（L30，私有）；`CompoundCollision.gap`（L41）；`Motion.pose`（L70）；`Motion.point_speed_bound`（L76）；`Motion.to_dict`（L84）。

### [topogym/evaluation/tasks/cast_keyhole/family_suite.py](../../../topogym/evaluation/tasks/cast_keyhole/family_suite.py)

- 模块函数：`verify_manifest`（L24）；`reproducibility`（L36）；`main`（L52）。
- 函数内局部声明：`main.catalog`（L135）。

### [topogym/evaluation/tasks/cast_keyhole/physical_audit.py](../../../topogym/evaluation/tasks/cast_keyhole/physical_audit.py)

- 模块函数：`audit`（L19）；`main`（L76）。

### [topogym/evaluation/tasks/cast_keyhole/qualify.py](../../../topogym/evaluation/tasks/cast_keyhole/qualify.py)

- 模块函数：`compare_reports`（L20）；`qualify`（L84）；`main`（L94）。

### [topogym/evaluation/tasks/fiber_bundling/anchored_verifier.py](../../../topogym/evaluation/tasks/fiber_bundling/anchored_verifier.py)

- 类：`AnchoredThreadingVerifier`（L20）。
- 模块函数：`plane_crossings`（L9）。
- 类方法：`AnchoredThreadingVerifier.__init__`（L26，私有）；`AnchoredThreadingVerifier.update`（L38）。

### [topogym/evaluation/tasks/fiber_bundling/assess_anchored.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_anchored.py)

- 模块函数：`assess`（L13）。

### [topogym/evaluation/tasks/fiber_bundling/assess_ik.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_ik.py)

- 模块函数：`comparable_plan`（L14）；`difference`（L20）；`assess`（L27）；`main`（L102）。
- 函数内局部声明：`assess.within`（L84）。

### [topogym/evaluation/tasks/fiber_bundling/assess_passage.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_passage.py)

- 模块函数：`final_crossings`（L19）；`assess`（L37）；`main`（L83）。

### [topogym/evaluation/tasks/fiber_bundling/assess_sequence.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_sequence.py)

- 模块函数：`publish_summary`（L13）；`assess`（L35）。

### [topogym/evaluation/tasks/fiber_bundling/assess_stability.py](../../../topogym/evaluation/tasks/fiber_bundling/assess_stability.py)

- 模块函数：`assess`（L13）。

### [topogym/evaluation/tasks/fiber_bundling/audit_robot_contacts.py](../../../topogym/evaluation/tasks/fiber_bundling/audit_robot_contacts.py)

- 模块函数：`main`（L8）。

### [topogym/evaluation/tasks/fiber_bundling/contact_guard.py](../../../topogym/evaluation/tasks/fiber_bundling/contact_guard.py)

- 类：`GripperFineContactGuard`（L34）。
- 模块函数：`_numpy`（L8，私有）；`gripper_link_names`（L12）。
- 类方法：`GripperFineContactGuard.__init__`（L41，私有）；`GripperFineContactGuard.observe`（L50）；`GripperFineContactGuard.install`（L72）；`GripperFineContactGuard.report`（L89）。
- 函数内局部声明：`GripperFineContactGuard.install.tracked_substep`（L80）。

### [topogym/evaluation/tasks/fiber_bundling/summarize_ik.py](../../../topogym/evaluation/tasks/fiber_bundling/summarize_ik.py)

- 模块函数：`summarize`（L12）；`main`（L86）。

### [topogym/evaluation/tasks/fiber_bundling/validation.py](../../../topogym/evaluation/tasks/fiber_bundling/validation.py)

- 类：`FixtureExperiment`（L58）。
- 模块函数：`pair_clearances`（L26）；`run_validation`（L179）。
- 类方法：`FixtureExperiment.__init__`（L60，私有）；`FixtureExperiment.state`（L99）；`FixtureExperiment.record`（L102）；`FixtureExperiment.monitor`（L111）；`FixtureExperiment.phase`（L131）；`FixtureExperiment.save`（L173）。

### [topogym/evaluation/tasks/fiber_bundling/variant_progress.py](../../../topogym/evaluation/tasks/fiber_bundling/variant_progress.py)

- 模块函数：`live_progress`（L9）；`summarize`（L35）。

### [topogym/evaluation/tasks/hedgehog_in_cage/audit.py](../../../topogym/evaluation/tasks/hedgehog_in_cage/audit.py)

- 模块函数：`main`（L15）。

### [topogym/evaluation/tasks/hedgehog_in_cage/variant_validation.py](../../../topogym/evaluation/tasks/hedgehog_in_cage/variant_validation.py)

- 类：`InstanceKinematics`（L114）；`InstanceAudit`（L130）。
- 模块函数：`frame`（L28）；`build_assets`（L33）；`negative_paths`（L168）；`qualify`（L203）。
- 类方法：`InstanceKinematics.__init__`（L116，私有）；`InstanceAudit.__init__`（L131，私有）。

### [topogym/evaluation/tasks/horseshoe_ring/trace_scene_verification.py](../../../topogym/evaluation/tasks/horseshoe_ring/trace_scene_verification.py)

- 模块函数：`verify`（L15）；`main`（L73）。

### [topogym/evaluation/tasks/horseshoe_ring/variant_audit.py](../../../topogym/evaluation/tasks/horseshoe_ring/variant_audit.py)

- 模块函数：`audit`（L15）；`main`（L50）。

### [topogym/evaluation/tasks/horseshoe_ring/verify_gravity.py](../../../topogym/evaluation/tasks/horseshoe_ring/verify_gravity.py)

- 模块函数：`verify`（L11）。

### [topogym/evaluation/tasks/horseshoe_ring/verify_physical.py](../../../topogym/evaluation/tasks/horseshoe_ring/verify_physical.py)

- 模块函数：`verify_run`（L13）；`compare_runs`（L99）；`main`（L142）。
- 函数内局部声明：`compare_runs.parameters`（L108）；`compare_runs.geometry_hashes`（L121）。

### [topogym/evaluation/tasks/interlocked_claws/reference_audit.py](../../../topogym/evaluation/tasks/interlocked_claws/reference_audit.py)

- 模块函数：`point_motion_radii`（L14）；`audit`（L32）。
- 函数内局部声明：`audit.sample`（L40）；`audit.interval`（L46）。

### [topogym/evaluation/tasks/interlocked_claws/reliability.py](../../../topogym/evaluation/tasks/interlocked_claws/reliability.py)

- 模块函数：`assemble`（L11）。

### [topogym/evaluation/tasks/interlocked_claws/verification.py](../../../topogym/evaluation/tasks/interlocked_claws/verification.py)

- 模块函数：`sha`（L14）；`validate_physical`（L18）；`compare`（L44）；`reference_tracking`（L77）。

### [topogym/evaluation/tasks/knot_untying/diagnostics.py](../../../topogym/evaluation/tasks/knot_untying/diagnostics.py)

- 类：`StabilityLimits`（L15）；`SurfaceCCD`（L85）；`FemDiagnostics`（L138）。
- 模块函数：`signed_tet_volumes`（L32）；`_ccd_worker`（L38，私有）。
- 类方法：`SurfaceCCD.__init__`（L86，私有）；`SurfaceCCD._receive`（L101，私有）；`SurfaceCCD.step`（L109）；`SurfaceCCD.step_between`（L116）；`SurfaceCCD.minimum_distance`（L124）；`SurfaceCCD.close`（L129）；`FemDiagnostics.__init__`（L140，私有）；`FemDiagnostics.native_state`（L212）；`FemDiagnostics.install`（L219）；`FemDiagnostics.observe`（L231）；`FemDiagnostics.report`（L276）；`FemDiagnostics.close`（L308）。
- 函数内局部声明：`FemDiagnostics.install.observed`（L225）。

### [topogym/evaluation/tasks/knot_untying/physics_review.py](../../../topogym/evaluation/tasks/knot_untying/physics_review.py)

- 模块函数：`evidence_satisfies_case`（L17）；`compare_centerlines`（L24）；`plot_trace`（L66）；`plot_refinement`（L107）；`write_review`（L140）。
- 函数内局部声明：`compare_centerlines.normalized_arc`（L33）。

### [topogym/evaluation/tasks/knot_untying/rigid_diagnostics.py](../../../topogym/evaluation/tasks/knot_untying/rigid_diagnostics.py)

- 类：`NativeRigidSurfaceCCD`（L18）。
- 模块函数：`swept_aabbs_overlap`（L11）。
- 类方法：`NativeRigidSurfaceCCD.__init__`（L19，私有）；`NativeRigidSurfaceCCD.__getattr__`（L47，私有）；`NativeRigidSurfaceCCD._create_checker`（L50，私有）；`NativeRigidSurfaceCCD.step`（L56）；`NativeRigidSurfaceCCD.close`（L80）；`NativeRigidSurfaceCCD.surface`（L86）。

### [topogym/evaluation/tasks/lock_picking/evaluator.py](../../../topogym/evaluation/tasks/lock_picking/evaluator.py)

- 类：`StagedLockEvaluator`（L4）。
- 类方法：`StagedLockEvaluator.evaluate`（L5）。

### [topogym/evaluation/tasks/lock_picking/verify_variants.py](../../../topogym/evaluation/tasks/lock_picking/verify_variants.py)

- 模块函数：`audit`（L16）。
- 函数内局部声明：`audit.fresh`（L65）。

### [topogym/evaluation/tasks/orbits/grasp_audit.py](../../../topogym/evaluation/tasks/orbits/grasp_audit.py)

- 模块函数：`audit`（L17）。
- 函数内局部声明：`audit.close_gap`（L34）。

### [topogym/evaluation/tasks/orbits/passage_audit.py](../../../topogym/evaluation/tasks/orbits/passage_audit.py)

- 模块函数：`audit`（L14）。

### [topogym/evaluation/tasks/orbits/reference_audit.py](../../../topogym/evaluation/tasks/orbits/reference_audit.py)

- 模块函数：`handle_footprint_clearance`（L18）；`audit`（L27）。

### [topogym/evaluation/tasks/orbits/rope_audit.py](../../../topogym/evaluation/tasks/orbits/rope_audit.py)

- 模块函数：`audit`（L14）。

### [topogym/evaluation/tasks/orbits/trajectory_audit.py](../../../topogym/evaluation/tasks/orbits/trajectory_audit.py)

- 模块函数：`audit`（L15）。

### [topogym/evaluation/tasks/orbits/verification.py](../../../topogym/evaluation/tasks/orbits/verification.py)

- 模块函数：`material_passages`（L6）；`threading_signature`（L49）。

### [topogym/evaluation/tasks/rope_threading/diagnostics.py](../../../topogym/evaluation/tasks/rope_threading/diagnostics.py)

- 类：`ClearanceSurfaceCCD`（L22）；`CertifiedRigidSurfaceCCD`（L53）。
- 模块函数：`displacement_certificate`（L14）。
- 类方法：`ClearanceSurfaceCCD.__init__`（L23，私有）；`ClearanceSurfaceCCD._clearance`（L30，私有）；`ClearanceSurfaceCCD.step`（L36）；`ClearanceSurfaceCCD.step_between`（L39）；`CertifiedRigidSurfaceCCD.__init__`（L54，私有）；`CertifiedRigidSurfaceCCD._create_checker`（L62，私有）；`CertifiedRigidSurfaceCCD.statistics`（L68）。

### [topogym/evaluation/tasks/rope_threading/physics_review.py](../../../topogym/evaluation/tasks/rope_threading/physics_review.py)

- 模块函数：`build`（L11）；`main`（L154）。

### [topogym/evaluation/tasks/rope_threading/qualification.py](../../../topogym/evaluation/tasks/rope_threading/qualification.py)

- 模块函数：`runtime_sources`（L26）；`digest`（L31）；`implementation_equivalence`（L35）；`physical_profile`（L71）；`paired_material_samples`（L81）；`compare_trajectories`（L97）；`identical_input_mesh`（L118）；`summarize`（L128）；`verify_for_execution`（L219）；`main`（L240）。
- 函数内局部声明：`implementation_equivalence.NonrobotDriver`（L51）；`implementation_equivalence.NonrobotDriver.visit_If`（L52）。

### [topogym/evaluation/tasks/rope_threading/startup_diagnostics.py](../../../topogym/evaluation/tasks/rope_threading/startup_diagnostics.py)

- 类：`StartupDiagnostics`（L7）。
- 类方法：`StartupDiagnostics.__init__`（L8，私有）；`StartupDiagnostics.observe`（L14）；`StartupDiagnostics.report`（L24）。

### [topogym/evaluation/tasks/rope_threading/startup_review.py](../../../topogym/evaluation/tasks/rope_threading/startup_review.py)

- 模块函数：`build`（L19）。

### [topogym/evaluation/tasks/slotted_post_ring/review_fem.py](../../../topogym/evaluation/tasks/slotted_post_ring/review_fem.py)

- 模块函数：`tetrahedral_ring_clearance`（L10）；`review`（L28）。

### [topogym/evaluation/tasks/slotted_post_ring/topology.py](../../../topogym/evaluation/tasks/slotted_post_ring/topology.py)

- 模块函数：`cord_chain`（L13）；`reduced_chain`（L37）。

### [topogym/policies/primitives/axial_insert.py](../../../topogym/policies/primitives/axial_insert.py)

- 类：`AxialInsertResult`（L141）；`AxialInsertPrimitive`（L157）。
- 模块函数：`_as_numpy`（L29，私有）；`_entity_pos`（L35，私有）；`_entity_quat`（L39，私有）；`_quat_slerp`（L43，私有）；`_quat_mul`（L63，私有）；`_rotate`（L77，私有）；`_rotation_between`（L85，私有）；`_axis_tilt`（L107，私有）。
- 类方法：`AxialInsertPrimitive.run`（L213）；`AxialInsertPrimitive._move_linear`（L464，私有）；`AxialInsertPrimitive._log`（L478，私有）。

### [topogym/policies/primitives/cloth_link_attach_drag.py](../../../topogym/policies/primitives/cloth_link_attach_drag.py)

- 类：`ClothAttachDragResult`（L54）；`ClothLinkAttachDragPrimitive`（L148）。
- 模块函数：`_as_numpy_qpos`（L45，私有）；`_quat_angle`（L78，私有）；`attached_indices`（L88）。
- 类方法：`ClothLinkAttachDragPrimitive.run`（L304）；`ClothLinkAttachDragPrimitive._hand_for_pad`（L649，私有）；`ClothLinkAttachDragPrimitive._pad_for_hand`（L654，私有）；`ClothLinkAttachDragPrimitive._hold`（L658，私有）；`ClothLinkAttachDragPrimitive._glide`（L702，私有）；`ClothLinkAttachDragPrimitive._retreat`（L723，私有）；`ClothLinkAttachDragPrimitive._notify`（L729，私有）。
- 函数内局部声明：`ClothLinkAttachDragPrimitive.run.lowest_pad_z`（L345）。

### [topogym/policies/primitives/gated_insert.py](../../../topogym/policies/primitives/gated_insert.py)

- 类：`GatedInsertResult`（L85）；`GatedInsertPrimitive`（L100）。
- 模块函数：`_as_numpy`（L37，私有）；`_entity_pos`（L43，私有）；`_entity_quat`（L47，私有）；`_quat_slerp`（L51，私有）；`_plate_yaw`（L71，私有）。
- 类方法：`GatedInsertPrimitive.approach_move_steps`（L157）；`GatedInsertPrimitive.time_to_station`（L160）；`GatedInsertPrimitive.insert_duration`（L179）；`GatedInsertPrimitive.run`（L188）；`GatedInsertPrimitive._abort`（L353，私有）；`GatedInsertPrimitive._move`（L379，私有）；`GatedInsertPrimitive._log`（L401，私有）。

### [topogym/policies/primitives/gateway_extract.py](../../../topogym/policies/primitives/gateway_extract.py)

- 类：`_Tracking`（L100，私有）；`GatewayExtractResult`（L130）；`GatewayExtractPrimitive`（L169）。
- 模块函数：`_as_numpy`（L68，私有）；`_matrix`（L74，私有）；`_quat_angle`（L86，私有）；`tool_offset`（L93）。
- 类方法：`GatewayExtractPrimitive.run`（L233）；`GatewayExtractPrimitive._move_hand`（L577，私有）；`GatewayExtractPrimitive._move_part`（L591，私有）；`GatewayExtractPrimitive._command`（L618，私有）；`GatewayExtractPrimitive._ease`（L639，私有）；`GatewayExtractPrimitive._abort`（L644，私有）；`GatewayExtractPrimitive._log`（L686，私有）。

### [topogym/policies/primitives/handle_drag.py](../../../topogym/policies/primitives/handle_drag.py)

- 类：`HandleDragResult`（L59）；`HandleDragPrimitive`（L73）。
- 模块函数：`_as_numpy`（L12，私有）；`_entity_pos`（L18，私有）；`_quat_yaw`（L22，私有）；`_entity_yaw`（L31，私有）；`_yaw_text`（L38，私有）；`_vec_text`（L42，私有）；`_follow_state`（L47，私有）；`_ease`（L53，私有）；`_quat_slerp`（L702，私有）。
- 类方法：`HandleDragPrimitive.run`（L131）；`HandleDragPrimitive._move_hand`（L476，私有）；`HandleDragPrimitive._log`（L616，私有）；`HandleDragPrimitive._log_segment`（L637，私有）；`HandleDragPrimitive._log_segment_progress`（L668，私有）。

### [topogym/policies/primitives/pbd_particle_pinch.py](../../../topogym/policies/primitives/pbd_particle_pinch.py)

- 类：`PBDCornerLiftResult`（L17）；`PBDCornerLiftPrimitive`（L26）；`PBDParticlePinchResult`（L202）；`PBDParticleAttachmentDragPrimitive`（L216）；`PBDParticlePinchDragPrimitive`（L690）。
- 模块函数：`_ease`（L11，私有）；`_quat_slerp`（L1015，私有）。
- 类方法：`PBDCornerLiftPrimitive.run`（L44）；`PBDCornerLiftPrimitive._log_phase`（L161，私有）；`PBDCornerLiftPrimitive._maybe_stop`（L167，私有）；`PBDCornerLiftPrimitive._move_hand`（L173，私有）；`PBDParticleAttachmentDragPrimitive.run`（L244）；`PBDParticleAttachmentDragPrimitive._hand_for_grasp`（L532，私有）；`PBDParticleAttachmentDragPrimitive._grasp_for_hand`（L537，私有）；`PBDParticleAttachmentDragPrimitive._attached_center`（L542，私有）；`PBDParticleAttachmentDragPrimitive._follow_error`（L550，私有）；`PBDParticleAttachmentDragPrimitive._retreat`（L558，私有）；`PBDParticleAttachmentDragPrimitive._move_hand`（L568，私有）；`PBDParticleAttachmentDragPrimitive._sync_attachment`（L634，私有）；`PBDParticleAttachmentDragPrimitive._log`（L646，私有）；`PBDParticleAttachmentDragPrimitive._log_segment`（L660，私有）；`PBDParticleAttachmentDragPrimitive._maybe_stop`（L682，私有）；`PBDParticlePinchDragPrimitive.run`（L718）；`PBDParticlePinchDragPrimitive._follow_error`（L934，私有）；`PBDParticlePinchDragPrimitive._retreat`（L940，私有）；`PBDParticlePinchDragPrimitive._move_hand`（L950，私有）；`PBDParticlePinchDragPrimitive._log`（L977，私有）；`PBDParticlePinchDragPrimitive._log_segment`（L992，私有）。

### [topogym/policies/primitives/pick_place.py](../../../topogym/policies/primitives/pick_place.py)

- 类：`PickPlaceResult`（L33）；`PickPlacePrimitive`（L51）。
- 模块函数：`_as_numpy`（L22，私有）；`_entity_pos`（L28，私有）；`_entity_yaw`（L357，私有）；`_entity_tilt`（L366，私有）；`_periodic_angle_delta`（L379，私有）；`_quat_slerp`（L386，私有）。
- 类方法：`PickPlacePrimitive.run`（L97）；`PickPlacePrimitive._move_linear`（L316，私有）；`PickPlacePrimitive._log`（L335，私有）。

### [topogym/policies/primitives/pivot_lever.py](../../../topogym/policies/primitives/pivot_lever.py)

- 类：`PivotLeverResult`（L108）；`PivotLeverPrimitive`（L127）。
- 模块函数：`_as_numpy`（L45，私有）；`_quat_slerp`（L51，私有）；`_wrap_angle`（L71，私有）；`knob_point_world`（L77）；`hand_angle_about`（L95）。
- 类方法：`PivotLeverPrimitive.run`（L168）；`PivotLeverPrimitive._move`（L326，私有）；`PivotLeverPrimitive._angle`（L338，私有）；`PivotLeverPrimitive._finger_qpos`（L342，私有）；`PivotLeverPrimitive._log`（L354，私有）。

### [topogym/policies/primitives/rim_rotate.py](../../../topogym/policies/primitives/rim_rotate.py)

- 类：`RimRotateResult`（L53）；`RimRotatePrimitive`（L71）。
- 模块函数：`_as_numpy`（L12，私有）；`_wrap_angle`（L18，私有）；`rim_point_world`（L23）；`signed_rotation`（L37）；`_quat_slerp`（L287，私有）。
- 类方法：`RimRotatePrimitive.run`（L110）；`RimRotatePrimitive._move_linear`（L258，私有）；`RimRotatePrimitive._disk_angle`（L270，私有）；`RimRotatePrimitive._log`（L274，私有）。

### [topogym/policies/primitives/rope_endpoint_drag.py](../../../topogym/policies/primitives/rope_endpoint_drag.py)

- 类：`EndpointAttachment`（L80）；`EndpointAttachmentManager`（L116）；`RopeEndpointDragPrimitive`（L170）。
- 模块函数：`_as_numpy`（L14，私有）；`_xyz`（L24，私有）；`_lerp`（L28，私有）；`_ease`（L32，私有）；`_endpoint_indices`（L37，私有）；`_endpoint_pin`（L45，私有）；`_entity_pos`（L49，私有）；`current_endpoint_center`（L53）；`sync_endpoint_pin`（L61）。
- 类方法：`EndpointAttachment.__init__`（L89，私有）；`EndpointAttachment.drive_to`（L110）；`EndpointAttachmentManager.__init__`（L119，私有）；`EndpointAttachmentManager.create`（L124）；`EndpointAttachmentManager.sync`（L145）；`EndpointAttachmentManager.__enter__`（L149，私有）；`EndpointAttachmentManager.__exit__`（L163，私有）；`RopeEndpointDragPrimitive.run`（L183）；`RopeEndpointDragPrimitive._move_hand`（L289，私有）。
- 函数内局部声明：`EndpointAttachmentManager.__enter__.wrapped_step`（L154，私有）。

### [topogym/policies/script_policy.py](../../../topogym/policies/script_policy.py)

- 类：`PolicyError`（L13）。
- 模块函数：`integer`（L17）；`compile_policy`（L23）。
- 函数内局部声明：`compile_policy.spend`（L47）；`compile_policy.expr`（L53）；`compile_policy.assign`（L80）；`compile_policy.block`（L85）。

### [topogym/policies/subgoal.py](../../../topogym/policies/subgoal.py)

- 类：`PlannedSubgoal`（L8）。
- 类方法：`PlannedSubgoal.label`（L19）；`PlannedSubgoal.metadata_dict`（L24）。

### [topogym/policies/tasks/blanket_flatten/bimanual.py](../../../topogym/policies/tasks/blanket_flatten/bimanual.py)

- 类：`BimanualRefinement`（L36）。
- 模块函数：`array`（L27）；`exposure`（L31）；`main`（L323）；`run`（L327）。
- 类方法：`BimanualRefinement.__init__`（L37，私有）；`BimanualRefinement.label`（L53）；`BimanualRefinement.capture`（L58）；`BimanualRefinement.tcp_pose`（L62）；`BimanualRefinement.step`（L67）；`BimanualRefinement.wait`（L81）；`BimanualRefinement.move`（L85）；`BimanualRefinement.contact_distances`（L131）；`BimanualRefinement.acquire`（L148）；`BimanualRefinement.release_side`（L194）；`BimanualRefinement.release`（L204）；`BimanualRefinement.reveal_and_acquire`（L208）；`BimanualRefinement.follow_patches`（L239）；`BimanualRefinement.spread_and_lay_robot`（L253）；`BimanualRefinement.save_robot`（L286）；`BimanualRefinement.execute_plan`（L317）。
- 函数内局部声明：`BimanualRefinement.spread_and_lay_robot.world`（L264）；`BimanualRefinement.spread_and_lay_robot.laying`（L277）。

### [topogym/policies/tasks/blanket_flatten/bimanual_full.py](../../../topogym/policies/tasks/blanket_flatten/bimanual_full.py)

- 类：`BimanualFull`（L38）。
- 模块函数：`end_groups`（L23）；`end_unwind_angles`（L27）；`main`（L308）。
- 类方法：`BimanualFull.__init__`（L39，私有）；`BimanualFull.step`（L58）；`BimanualFull.stage_done`（L77）；`BimanualFull.untwist`（L81）；`BimanualFull.retreat`（L170）；`BimanualFull.unfold_layers`（L209）；`BimanualFull.execute_plan`（L282）；`BimanualFull.save_robot`（L293）。

### [topogym/policies/tasks/blanket_flatten/grasp_sites.py](../../../topogym/policies/tasks/blanket_flatten/grasp_sites.py)

- 模块函数：`carry_waypoints_xy`（L6）；`reachable_target_xy`（L27）；`exposed_boundary_site`（L41）；`refinement_sites`（L65）；`corner_exposure`（L119）；`corner_layer_sites`（L133）。
- 函数内局部声明：`carry_waypoints_xy.minimum_radius`（L11）；`corner_layer_sites.visible`（L150）；`corner_layer_sites.site`（L153）。

### [topogym/policies/tasks/blanket_flatten/robot_demo.py](../../../topogym/policies/tasks/blanket_flatten/robot_demo.py)

- 模块函数：`main`（L12）。

### [topogym/policies/tasks/buzz_wire_3d/family_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/family_plan.py)

- 模块函数：`construct`（L29）；`handle_guide`（L126）；`search`（L191）；`main`（L902）。
- 函数内局部声明：`search.physical`（L358）；`search.evaluate`（L542）；`search.objective`（L593）；`search.eq`（L614）；`search.inequality`（L619）；`search.feasible`（L690）；`search.FeasibleIterate`（L706）；`search.accept_feasible`（L763）。

### [topogym/policies/tasks/buzz_wire_3d/home_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/home_plan.py)

- 模块函数：`extend`（L18）。
- 函数内局部声明：`extend.valid`（L47）；`extend.edge`（L51）。

### [topogym/policies/tasks/buzz_wire_3d/supported_plan.py](../../../topogym/policies/tasks/buzz_wire_3d/supported_plan.py)

- 模块函数：`verify_supported_paths`（L20）；`refresh_supported_plan`（L187）；`solve_audited`（L231）；`measured_retreat`（L288）；`build`（L340）；`main`（L667）。
- 函数内局部声明：`verify_supported_paths.pose`（L41）；`verify_supported_paths.same_pose`（L46）；`solve_audited.check`（L236）；`build.pose`（L415）；`build.row`（L420）；`build.solve_path`（L427）；`build.solve_path.advance`（L430）；`build.interpolate`（L511）。

### [topogym/policies/tasks/cast_coil/robot_demo.py](../../../topogym/policies/tasks/cast_coil/robot_demo.py)

- 模块函数：`main`（L16）。
- 函数内局部声明：`main.arr`（L125）；`main.rot`（L128）；`main.pose`（L179）；`main.capture_physical_frame`（L183）；`main.step`（L193）；`main.phase_to`（L295）；`main.wait`（L303）；`main.command`（L307）；`main.execute`（L311）；`main.adjust_plan`（L333）。

### [topogym/policies/tasks/cast_keyhole/aloha_demo.py](../../../topogym/policies/tasks/cast_keyhole/aloha_demo.py)

- 模块函数：`canonical_to_entities`（L15）；`main`（L30）。

### [topogym/policies/tasks/cast_keyhole/family_pipeline.py](../../../topogym/policies/tasks/cast_keyhole/family_pipeline.py)

- 模块函数：`command`（L20）；`geometry`（L32）；`physics`（L37）；`audit`（L46）；`qualify_physics`（L52）；`parallel`（L88）；`validate`（L101）；`render`（L126）；`sampled_family_seed`（L135）；`sample`（L151）；`main`（L186）。

### [topogym/policies/tasks/cast_keyhole/variant_pose.py](../../../topogym/policies/tasks/cast_keyhole/variant_pose.py)

- 模块函数：`retarget`（L14）。
- 函数内局部声明：`retarget.residual`（L35）。

### [topogym/policies/tasks/fiber_bundling/sequential.py](../../../topogym/policies/tasks/fiber_bundling/sequential.py)

- 模块函数：`local_metrics`（L19）；`execute`（L27）。
- 函数内局部声明：`execute.observe`（L51）；`execute.check_physics`（L66）；`execute.phase`（L75）。

### [topogym/policies/tasks/hedgehog_in_cage/extract.py](../../../topogym/policies/tasks/hedgehog_in_cage/extract.py)

- 模块函数：`main`（L22）。
- 函数内局部声明：`main.pose`（L108）；`main.enter`（L110）；`main.step`（L115）；`main.drive_hand`（L149）；`main.move_ball`（L159）。

### [topogym/policies/tasks/hedgehog_in_cage/family_motion.py](../../../topogym/policies/tasks/hedgehog_in_cage/family_motion.py)

- 模块函数：`proposal`（L16）；`generate`（L51）；`main`（L89）。

### [topogym/policies/tasks/hedgehog_in_cage/plan_escape.py](../../../topogym/policies/tasks/hedgehog_in_cage/plan_escape.py)

- 类：`CollisionOracle`（L15）。
- 模块函数：`interpolate`（L38）；`search`（L48）；`main`（L82）。
- 类方法：`CollisionOracle.__init__`（L16，私有）；`CollisionOracle.distance`（L31）。
- 函数内局部声明：`search.values`（L58）；`search.valid`（L61）。

### [topogym/policies/tasks/hedgehog_in_cage/plan_release.py](../../../topogym/policies/tasks/hedgehog_in_cage/plan_release.py)

- 模块函数：`main`（L14）。
- 函数内局部声明：`main.check`（L40）。

### [topogym/policies/tasks/horseshoe_ring/aloha_demo.py](../../../topogym/policies/tasks/horseshoe_ring/aloha_demo.py)

- 模块函数：`main`（L19）；`initial_stills`（L60）。

### [topogym/policies/tasks/horseshoe_ring/family_routes.py](../../../topogym/policies/tasks/horseshoe_ring/family_routes.py)

- 模块函数：`plan`（L19）；`execute`（L38）。

### [topogym/policies/tasks/horseshoe_ring/physical_demo.py](../../../topogym/policies/tasks/horseshoe_ring/physical_demo.py)

- 模块函数：`extract_ring`（L15）；`run`（L64）；`main`（L84）。

### [topogym/policies/tasks/horseshoe_ring/physical_extraction.py](../../../topogym/policies/tasks/horseshoe_ring/physical_extraction.py)

- 类：`RelativeExtraction`（L25）。
- 类方法：`RelativeExtraction.__init__`（L26，私有）；`RelativeExtraction.ring_pose`（L75）；`RelativeExtraction.overlap`（L82）；`RelativeExtraction.valid`（L85）；`RelativeExtraction.guide`（L97）；`RelativeExtraction.plan_segment`（L118）；`RelativeExtraction.samples`（L177）；`RelativeExtraction.solve`（L184）。
- 函数内局部声明：`RelativeExtraction.solve.residual`（L193）；`RelativeExtraction.solve.exact_relative`（L228）。

### [topogym/policies/tasks/horseshoe_ring/physical_place.py](../../../topogym/policies/tasks/horseshoe_ring/physical_place.py)

- 模块函数：`plan_release`（L12）；`release_ring`（L110）。
- 函数内局部声明：`plan_release.carried_frame`（L30）；`plan_release.valid`（L38）。

### [topogym/policies/tasks/horseshoe_ring/physical_plan.py](../../../topogym/policies/tasks/horseshoe_ring/physical_plan.py)

- 模块函数：`body_frame`（L10）；`horizontal_support`（L15）；`combine_horseshoes`（L24）；`transfer`（L92）；`ring_grasp_frame`（L109）；`tracked_ring_grasp_frame`（L122）；`ring_candidates`（L140）；`grasp_ring`（L184）。
- 函数内局部声明：`grasp_ring.attach_if_loaded`（L192）。

### [topogym/policies/tasks/horseshoe_ring/shape_bridge.py](../../../topogym/policies/tasks/horseshoe_ring/shape_bridge.py)

- 模块函数：`segment_clear`（L11）；`plan_bridge`（L28）；`repair_extraction`（L81）。
- 函数内局部声明：`segment_clear.check`（L13）；`plan_bridge.pose`（L42）；`plan_bridge.valid`（L44）。

### [topogym/policies/tasks/horseshoe_ring/variant_pipeline.py](../../../topogym/policies/tasks/horseshoe_ring/variant_pipeline.py)

- 模块函数：`corridor_frames`（L20）；`family_gate`（L37）；`qualify`（L57）；`execute_instance`（L110）；`generate_validated`（L124）；`main`（L166）。

### [topogym/policies/tasks/horseshoe_ring/witness_motion.py](../../../topogym/policies/tasks/horseshoe_ring/witness_motion.py)

- 模块函数：`fold_transforms`（L6）；`interpolate`（L26）。

### [topogym/policies/tasks/interlocked_claws/physical.py](../../../topogym/policies/tasks/interlocked_claws/physical.py)

- 模块函数：`run`（L22）。
- 函数内局部声明：`run.poses_and_state`（L82）；`run.capture`（L93）。

### [topogym/policies/tasks/knot_untying/family_actions.py](../../../topogym/policies/tasks/knot_untying/family_actions.py)

- 类：`FamilyRoute`（L19）；`FamilyUntyingActions`（L170）。
- 模块函数：`route_for_config`（L53）；`material_arc`（L97）；`support_material_site`（L101）；`first_under_grasp`（L126）；`initial_grasp_sites`（L146）；`configure_family_start`（L158）。
- 类方法：`FamilyUntyingActions.__init__`（L171，私有）；`FamilyUntyingActions.specification`（L207）；`FamilyUntyingActions.declare`（L263）；`FamilyUntyingActions.configure`（L283）；`FamilyUntyingActions.move`（L293）；`FamilyUntyingActions.approach`（L297）；`FamilyUntyingActions.release`（L303）；`FamilyUntyingActions._transition`（L308，私有）；`FamilyUntyingActions._hold`（L315，私有）；`FamilyUntyingActions._record_motion`（L320，私有）；`FamilyUntyingActions._pull_band_candidates`（L324，私有）；`FamilyUntyingActions._choose_pull_band`（L341，私有）；`FamilyUntyingActions._finish_or_extend_opening`（L350，私有）；`FamilyUntyingActions._choose_support_band`（L406，私有）；`FamilyUntyingActions._start_lateral_clearance`（L417，私有）；`FamilyUntyingActions._checked_regrasp_candidate`（L446，私有）；`FamilyUntyingActions._prepare_grasp`（L477，私有）；`FamilyUntyingActions._track_regrasp_translation`（L520，私有）；`FamilyUntyingActions._begin_support_reanchor_if_needed`（L545，私有）；`FamilyUntyingActions._start_draw`（L575，私有）；`FamilyUntyingActions._held_band_reached_underpass`（L627，私有）；`FamilyUntyingActions._begin_regrasp`（L639，私有）；`FamilyUntyingActions._begin_release`（L683，私有）；`FamilyUntyingActions._preserve_support_height`（L702，私有）；`FamilyUntyingActions._check_support_clearance`（L710，私有）；`FamilyUntyingActions._advance`（L716，私有）；`FamilyUntyingActions.update`（L900）；`FamilyUntyingActions.observe`（L980）；`FamilyUntyingActions.finished`（L1028）；`FamilyUntyingActions.report`（L1031）。

### [topogym/policies/tasks/knot_untying/home_start.py](../../../topogym/policies/tasks/knot_untying/home_start.py)

- 类：`HomeFamilyUntyingActions`（L108）。
- 模块函数：`plan_home_prefix`（L19）。
- 类方法：`HomeFamilyUntyingActions.__init__`（L109，私有）；`HomeFamilyUntyingActions.specification`（L116）；`HomeFamilyUntyingActions.configure`（L121）；`HomeFamilyUntyingActions.update`（L134）；`HomeFamilyUntyingActions.report`（L168）。
- 函数内局部声明：`plan_home_prefix.candidates`（L37）。

### [topogym/policies/tasks/knot_untying/untying.py](../../../topogym/policies/tasks/knot_untying/untying.py)

- 类：`UntyingFixtureActions`（L66）；`RobotUntyingActions`（L124）。
- 模块函数：`grasp_indices`（L25）；`declare_bands`（L30）；`initial_centerline`（L36）；`configure_untying_start`（L48）。
- 类方法：`UntyingFixtureActions.__init__`（L70，私有）；`UntyingFixtureActions.specification`（L74）；`UntyingFixtureActions.declare`（L81）；`UntyingFixtureActions.update`（L84）；`UntyingFixtureActions.observe`（L108）；`UntyingFixtureActions.report`（L114）；`RobotUntyingActions.__init__`（L126，私有）；`RobotUntyingActions.draw_distance`（L160）；`RobotUntyingActions.start_spread`（L201）；`RobotUntyingActions.right_displacement`（L221）；`RobotUntyingActions.finished`（L225）；`RobotUntyingActions.specification`（L228）；`RobotUntyingActions.declare`（L262）；`RobotUntyingActions.update`（L267）；`RobotUntyingActions.observe`（L329）；`RobotUntyingActions.report`（L334）。

### [topogym/policies/tasks/lock_picking/oracle.py](../../../topogym/policies/tasks/lock_picking/oracle.py)

- 模块函数：`execute_reindex`（L10）。
- 函数内局部声明：`execute_reindex.command`（L25）；`execute_reindex.common`（L72）。

### [topogym/policies/tasks/lock_picking/planner.py](../../../topogym/policies/tasks/lock_picking/planner.py)

- 模块函数：`next_entry_angle`（L6）；`insertion_window`（L15）。

### [topogym/policies/tasks/orbits/continuous_motion.py](../../../topogym/policies/tasks/orbits/continuous_motion.py)

- 模块函数：`continue_run`（L20）；`cartesian_path`（L53）；`move`（L104）；`joint_transfer_path`（L124）；`paired_cartesian_path`（L224）；`move_pair`（L283）；`acquire_strand`（L290）；`handover_probe`（L310）。
- 函数内局部声明：`joint_transfer_path.valid`（L151）；`joint_transfer_path.edge`（L155）；`joint_transfer_path.extend`（L168）；`joint_transfer_path.branch`（L181）。

### [topogym/policies/tasks/orbits/robot_pickup.py](../../../topogym/policies/tasks/orbits/robot_pickup.py)

- 模块函数：`command_pose`（L25）；`pickup_pose`（L33）；`acquire_from_table`（L51）；`run`（L108）。

### [topogym/policies/tasks/orbits/rope_route.py](../../../topogym/policies/tasks/orbits/rope_route.py)

- 模块函数：`execute`（L23）。
- 函数内局部声明：`execute.callback`（L138）。

### [topogym/policies/tasks/orbits/solution_plan.py](../../../topogym/policies/tasks/orbits/solution_plan.py)

- 模块函数：`run_prefix`（L20）。

### [topogym/policies/tasks/rope_threading/feedback_actions.py](../../../topogym/policies/tasks/rope_threading/feedback_actions.py)

- 类：`FeedbackThreadingActions`（L15）。
- 类方法：`FeedbackThreadingActions.__init__`（L18，私有）；`FeedbackThreadingActions.specification`（L33）；`FeedbackThreadingActions.release_aperture`（L54）；`FeedbackThreadingActions.task_clearance`（L61）；`FeedbackThreadingActions.configure`（L67）；`FeedbackThreadingActions._qpos`（L72，私有）；`FeedbackThreadingActions._model_point`（L77，私有）；`FeedbackThreadingActions._snapshot`（L80，私有）；`FeedbackThreadingActions._record`（L91，私有）；`FeedbackThreadingActions._begin_path`（L100，私有）；`FeedbackThreadingActions._command`（L112，私有）；`FeedbackThreadingActions._settled`（L119，私有）；`FeedbackThreadingActions._expect_event`（L131，私有）；`FeedbackThreadingActions._follow_bands`（L137，私有）；`FeedbackThreadingActions._join_qpos`（L143，私有）；`FeedbackThreadingActions._next_stage`（L151，私有）；`FeedbackThreadingActions.update`（L242）；`FeedbackThreadingActions.report`（L308）；`FeedbackThreadingActions.close_contact_monitors`（L321）；`FeedbackThreadingActions.observe`（L329）。

### [topogym/policies/tasks/rope_threading/reference_actions.py](../../../topogym/policies/tasks/rope_threading/reference_actions.py)

- 类：`ReferenceThreadingActions`（L24）。
- 模块函数：`ending_lift`（L19）。
- 类方法：`ReferenceThreadingActions.__init__`（L25，私有）；`ReferenceThreadingActions.specification`（L65）；`ReferenceThreadingActions.configure`（L87）；`ReferenceThreadingActions.release`（L93）；`ReferenceThreadingActions.declare`（L112）；`ReferenceThreadingActions._sample`（L119，私有）；`ReferenceThreadingActions._acquire`（L136，私有）；`ReferenceThreadingActions.release_aperture`（L168）；`ReferenceThreadingActions.task_clearance`（L172）；`ReferenceThreadingActions.update`（L175）；`ReferenceThreadingActions.observe`（L242）；`ReferenceThreadingActions.finished`（L260）；`ReferenceThreadingActions.report`（L263）。

### [topogym/policies/waypoint.py](../../../topogym/policies/waypoint.py)

- 类：`WaypointTarget`（L232）；`WaypointPlan`（L269）；`EpisodePlan`（L294）。
- 模块函数：`arc_route_points`（L11）；`helix_route_points`（L76）；`lead_in_route_point`（L145）；`plug_spawn_point`（L168）；`tail_arc_route_points`（L195）。
- 类方法：`WaypointTarget.from_sequence`（L243）；`WaypointTarget.metadata_dict`（L264）；`WaypointPlan.limited`（L276）；`WaypointPlan.labels`（L286）；`WaypointPlan.metadata_dict`（L289）；`EpisodePlan.waypoints`（L304）；`EpisodePlan.metadata_dict`（L309）。

### [topogym/recording/__init__.py](../../../topogym/recording/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/recording/__main__.py](../../../topogym/recording/__main__.py)

- 模块函数：`main`（L6）。

### [topogym/recording/adapters/__init__.py](../../../topogym/recording/adapters/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/recording/adapters/genesis.py](../../../topogym/recording/adapters/genesis.py)

- 类：`GenesisBinding`（L16）。
- 模块函数：`array`（L9）；`from_source`（L157）。
- 类方法：`GenesisBinding.__init__`（L17，私有）；`GenesisBinding.from_scene`（L27）；`GenesisBinding.from_task`（L32）；`GenesisBinding.clock`（L36）；`GenesisBinding.subscribe`（L40）；`GenesisBinding.render`（L64）；`GenesisBinding.scene_report`（L73）；`GenesisBinding.camera_poses`（L111）；`GenesisBinding.export_state`（L114）；`GenesisBinding.restore`（L127）；`GenesisBinding.close`（L153）。
- 函数内局部声明：`GenesisBinding.subscribe.step`（L46）。

### [topogym/recording/agent_media.py](../../../topogym/recording/agent_media.py)

- 模块函数：`publish_segment`（L14）。

### [topogym/recording/archive.py](../../../topogym/recording/archive.py)

- 模块函数：`variant_lock`（L17）；`formal_eligibility`（L25）；`external_eligibility`（L74）；`_catalog_entry`（L140，私有）；`_legacy_entries_for_paths`（L146，私有）；`_set_catalog_entry`（L156，私有）；`_update_catalog`（L197，私有）；`_restore_catalog`（L203，私有）；`archive`（L209）；`recover`（L312）。

### [topogym/recording/config.py](../../../topogym/recording/config.py)

- 模块函数：`plain`（L17）；`physics_description`（L21）；`physics_signature`（L29）；`_load`（L33，私有）；`default_recording_config`（L41）；`prepare`（L45）；`preflight`（L147）。

### [topogym/recording/contracts.py](../../../topogym/recording/contracts.py)

- 类：`RunIdentity`（L17）；`RecordingPlan`（L32）；`FrameSet`（L42）；`RecordingResult`（L53）；`RecordingBinding`（L58）。
- 模块函数：`identifier`（L10）。
- 类方法：`RunIdentity.__post_init__`（L24，私有）；`RecordingBinding.clock`（L60）；`RecordingBinding.render`（L61）；`RecordingBinding.scene_report`（L62）；`RecordingBinding.export_state`（L63）；`RecordingBinding.restore`（L64）；`RecordingBinding.subscribe`（L65）。

### [topogym/recording/demo_paths.py](../../../topogym/recording/demo_paths.py)

- 模块函数：`demo_video_root`（L46）。

### [topogym/recording/encoding.py](../../../topogym/recording/encoding.py)

- 类：`VideoWriter`（L36）。
- 模块函数：`command`（L15）；`probe`（L22）；`get_writer`（L123）。
- 类方法：`VideoWriter.__init__`（L37，私有）；`VideoWriter.append_data`（L52）；`VideoWriter.close`（L83）；`VideoWriter.__enter__`（L112，私有）；`VideoWriter.__exit__`（L115，私有）。

### [topogym/recording/media.py](../../../topogym/recording/media.py)

- 模块函数：`encode_sequence`（L7）；`extract_frame`（L25）；`mosaic`（L33）。

### [topogym/recording/migration.py](../../../topogym/recording/migration.py)

- 模块函数：`operations`（L17）；`inventory`（L43）；`audit`（L49）。

### [topogym/recording/replay.py](../../../topogym/recording/replay.py)

- 类：`StateSource`（L18）。
- 模块函数：`load_factory`（L77）；`replay`（L84）。
- 类方法：`StateSource.__init__`（L20，私有）；`StateSource.verify`（L62）；`StateSource.row`（L67）。

### [topogym/recording/session.py](../../../topogym/recording/session.py)

- 类：`RecordingSession`（L16）。
- 模块函数：`session`（L192）。
- 类方法：`RecordingSession.__init__`（L17，私有）；`RecordingSession.__enter__`（L35，私有）；`RecordingSession._write_status`（L77，私有）；`RecordingSession._after_step`（L81，私有）；`RecordingSession.append`（L103）；`RecordingSession.finish`（L123）；`RecordingSession.event`（L130）；`RecordingSession._abort`（L134，私有）；`RecordingSession.__exit__`（L143，私有）。
- 函数内局部声明：`RecordingSession.__exit__.entry`（L164，私有）。

### [topogym/recording/sources.py](../../../topogym/recording/sources.py)

- 模块函数：`snapshot_mjcf_model`（L11）；`snapshot_config_inputs`（L60）；`mjcf_dependencies`（L100）；`source_from_recording`（L136）。
- 函数内局部声明：`mjcf_dependencies.visit`（L109）。

### [topogym/recording/task_adapters/blanket_flatten.py](../../../topogym/recording/task_adapters/blanket_flatten.py)

- 类：`BlanketBinding`（L102）。
- 模块函数：`approval`（L21）；`snapshot`（L36）；`from_source`（L175）；`render`（L200）；`main`（L225）。
- 类方法：`BlanketBinding.__init__`（L104，私有）；`BlanketBinding.scene_report`（L117）；`BlanketBinding.export_state`（L124）；`BlanketBinding.restore_time`（L127）；`BlanketBinding.restore`（L130）；`BlanketBinding.sample_clearance`（L150）；`BlanketBinding.motion_review`（L165）。

### [topogym/recording/task_adapters/buzz_wire_3d.py](../../../topogym/recording/task_adapters/buzz_wire_3d.py)

- 模块函数：`build_scene`（L29）；`recording_plan`（L55）；`snapshot`（L75）；`main`（L240）。
- 函数内局部声明：`build_scene.assets`（L33）。

### [topogym/recording/task_adapters/cast_coil.py](../../../topogym/recording/task_adapters/cast_coil.py)

- 模块函数：`qualify`（L11）；`main`（L49）。

### [topogym/recording/task_adapters/cast_keyhole.py](../../../topogym/recording/task_adapters/cast_keyhole.py)

- 类：`KeyholeBinding`（L133）。
- 模块函数：`identifier`（L33）；`configuration`（L37）；`frozen_motion`（L46）；`snapshot`（L60）；`canonical_from_entities`（L119）；`from_source`（L186）；`render`（L225）；`render_motion`（L232）；`record_physical_run`（L242）；`load_recording`（L253）；`rendered_source_indices`（L272）；`verify_frames`（L279）；`main`（L300）。
- 类方法：`KeyholeBinding.__init__`（L136，私有）；`KeyholeBinding.pads`（L142）；`KeyholeBinding.export_state`（L149）；`KeyholeBinding.restore`（L157）；`KeyholeBinding.scene_report`（L179）。

### [topogym/recording/task_adapters/fiber_bundling.py](../../../topogym/recording/task_adapters/fiber_bundling.py)

- 类：`FiberBinding`（L148）。
- 模块函数：`label`（L30）；`replay_configuration`（L64）；`snapshot`（L85）；`build_scene`（L142）；`from_source`（L184）；`render`（L202）；`load_recording`（L215）；`main`（L231）。
- 类方法：`FiberBinding.__init__`（L151，私有）；`FiberBinding.export_state`（L155）；`FiberBinding.restore`（L161）；`FiberBinding.scene_report`（L178）。

### [topogym/recording/task_adapters/hedgehog_in_cage.py](../../../topogym/recording/task_adapters/hedgehog_in_cage.py)

- 类：`HedgehogBinding`（L26）。
- 模块函数：`_runtime`（L41，私有）；`snapshot`（L51）；`from_source`（L112）；`render`（L130）；`main`（L145）。
- 类方法：`HedgehogBinding.__init__`（L28，私有）；`HedgehogBinding.restore`（L33）。

### [topogym/recording/task_adapters/horseshoe_ring.py](../../../topogym/recording/task_adapters/horseshoe_ring.py)

- 类：`HorseshoeBinding`（L29）。
- 模块函数：`recording_cameras`（L51）；`camera_coverage`（L58）；`snapshot`（L94）；`from_source`（L168）；`render`（L186）；`main`（L197）。
- 类方法：`HorseshoeBinding.__init__`（L31，私有）；`HorseshoeBinding.restore`（L38）。

### [topogym/recording/task_adapters/interlocked_claws.py](../../../topogym/recording/task_adapters/interlocked_claws.py)

- 模块函数：`family_cameras`（L16）；`snapshot_family`（L29）；`render_family`（L109）；`genesis_binding`（L119）；`main`（L124）。

### [topogym/recording/task_adapters/knot_untying.py](../../../topogym/recording/task_adapters/knot_untying.py)

- 类：`KnotBinding`（L35）；`SharedKnotRecorder`（L44）。
- 模块函数：`prepare_recording`（L17）；`archive_shared`（L103）。
- 类方法：`KnotBinding.scene_report`（L36）；`SharedKnotRecorder.__init__`（L45，私有）；`SharedKnotRecorder.capture`（L57）；`SharedKnotRecorder.checkpoint`（L65）；`SharedKnotRecorder.close`（L69）。

### [topogym/recording/task_adapters/lock_picking.py](../../../topogym/recording/task_adapters/lock_picking.py)

- 类：`LockBinding`（L83）。
- 模块函数：`load_source`（L40）；`physics_signature`（L60）；`rotation_error`（L77）；`from_source`（L132）；`snapshot`（L169）；`render`（L220）；`main`（L238）。
- 类方法：`LockBinding.attach`（L86）；`LockBinding.restore`（L95）；`LockBinding.scene_report`（L123）。

### [topogym/recording/task_adapters/orbits.py](../../../topogym/recording/task_adapters/orbits.py)

- 类：`RopeBinding`（L30）。
- 模块函数：`model_signature`（L23）；`from_source`（L96）；`snapshot`（L132）；`render`（L188）。
- 类方法：`RopeBinding.__init__`（L31，私有）；`RopeBinding.export_state`（L44）；`RopeBinding.restore`（L47）；`RopeBinding.render`（L64）；`RopeBinding.scene_report`（L87）。

### [topogym/recording/task_adapters/rope_threading.py](../../../topogym/recording/task_adapters/rope_threading.py)

- 类：`ThreadingBinding`（L64）；`SharedThreadingRecorder`（L73）。
- 模块函数：`stage_label`（L26）；`prepare_recording`（L45）。
- 类方法：`ThreadingBinding.scene_report`（L65）；`SharedThreadingRecorder.__init__`（L74，私有）；`SharedThreadingRecorder.capture`（L84）；`SharedThreadingRecorder.abort`（L93）；`SharedThreadingRecorder.close`（L97）。

### [topogym/recording/task_adapters/slotted_post_ring.py](../../../topogym/recording/task_adapters/slotted_post_ring.py)

- 类：`FEMBinding`（L121）。
- 模块函数：`model_signature`（L34）；`qualification_passed`（L47）；`verify_complete_trace`（L63）；`controller_assistance`（L84）；`from_source`（L210）；`snapshot`（L239）；`render`（L307）。
- 类方法：`FEMBinding.__init__`（L122，私有）；`FEMBinding._equality`（L148，私有）；`FEMBinding.export_state`（L151）；`FEMBinding.restore`（L159）；`FEMBinding.render`（L189）；`FEMBinding.scene_report`（L200）。

### [topogym/recording/tasks/blanket_flatten/archive.py](../../../topogym/recording/tasks/blanket_flatten/archive.py)

- 模块函数：`sha`（L23）；`qualify`（L27）；`qualify_mesh_review`（L77）；`render_summary`（L86）；`main`（L114）。

### [topogym/recording/tasks/buzz_wire_3d/archive.py](../../../topogym/recording/tasks/buzz_wire_3d/archive.py)

- 模块函数：`archive`（L20）；`main`（L238）。

### [topogym/recording/tasks/buzz_wire_3d/robot_archive.py](../../../topogym/recording/tasks/buzz_wire_3d/robot_archive.py)

- 模块函数：`archive`（L21）；`main`（L341）。

### [topogym/recording/tasks/cast_coil/robot_archive.py](../../../topogym/recording/tasks/cast_coil/robot_archive.py)

- 模块函数：`sha`（L42）；`demo_title`（L46）；`qualify_report`（L57）；`verified_frames`（L105）；`read_trace`（L135）；`audit`（L142）；`archive`（L342）；`update_catalog`（L444）。

### [topogym/recording/tasks/cast_keyhole/archive_demo.py](../../../topogym/recording/tasks/cast_keyhole/archive_demo.py)

- 模块函数：`sha`（L22）；`archive`（L25）；`main`（L115）。

### [topogym/recording/tasks/cast_keyhole/eccentric_window_archive.py](../../../topogym/recording/tasks/cast_keyhole/eccentric_window_archive.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/recording/tasks/cast_keyhole/family_variants_archive.py](../../../topogym/recording/tasks/cast_keyhole/family_variants_archive.py)

- 模块函数：`archive_one`（L9）。

### [topogym/recording/tasks/cast_keyhole/long_stroke_archive.py](../../../topogym/recording/tasks/cast_keyhole/long_stroke_archive.py)

- 模块函数：`update_text`（L20）；`archive`（L32）；`main`（L121）。
- 函数内局部声明：`archive.catalog_update`（L108）。

### [topogym/recording/tasks/cast_keyhole/physical_recording.py](../../../topogym/recording/tasks/cast_keyhole/physical_recording.py)

- 模块函数：`prepare`（L17）；`main`（L50）。

### [topogym/recording/tasks/cast_keyhole/turnback_archive.py](../../../topogym/recording/tasks/cast_keyhole/turnback_archive.py)

- 模块函数：`verify_maneuver`（L14）。

### [topogym/recording/tasks/cast_keyhole/variant_archive.py](../../../topogym/recording/tasks/cast_keyhole/variant_archive.py)

- 模块函数：`qualify`（L32）；`archive`（L79）；`main`（L141）。

### [topogym/recording/tasks/fiber_bundling/archive_variant.py](../../../topogym/recording/tasks/fiber_bundling/archive_variant.py)

- 模块函数：`sha`（L23）；`main`（L27）。

### [topogym/recording/tasks/fiber_bundling/render_ready.py](../../../topogym/recording/tasks/fiber_bundling/render_ready.py)

- 模块函数：`render_lock`（L16）；`main`（L22）。

### [topogym/recording/tasks/hedgehog_in_cage/family_archive.py](../../../topogym/recording/tasks/hedgehog_in_cage/family_archive.py)

- 模块函数：`read`（L24）；`require`（L25）；`run_id`（L27）；`verify_physics`（L30）；`archive_one`（L64）；`comparison_archive`（L101）；`register`（L110）；`archive_all`（L124）。

### [topogym/recording/tasks/hedgehog_in_cage/inverse_archive.py](../../../topogym/recording/tasks/hedgehog_in_cage/inverse_archive.py)

- 模块函数：`read`（L31）；`require`（L35）；`verify_execution`（L40）；`verify_recording`（L74）；`profile_plot`（L116）；`update_catalog`（L135）；`archive`（L149）；`main`（L198）。

### [topogym/recording/tasks/hedgehog_in_cage/prepare_classic_prototypes.py](../../../topogym/recording/tasks/hedgehog_in_cage/prepare_classic_prototypes.py)

- 模块函数：`archive`（L21）；`prepare`（L49）。

### [topogym/recording/tasks/horseshoe_ring/archive_physical.py](../../../topogym/recording/tasks/horseshoe_ring/archive_physical.py)

- 模块函数：`archive`（L23）；`main`（L134）。

### [topogym/recording/tasks/horseshoe_ring/archive_timestep.py](../../../topogym/recording/tasks/horseshoe_ring/archive_timestep.py)

- 模块函数：`file_manifest`（L17）；`retain`（L23）；`main`（L127）。

### [topogym/recording/tasks/horseshoe_ring/variant_video.py](../../../topogym/recording/tasks/horseshoe_ring/variant_video.py)

- 模块函数：`sha`（L9）；`save`（L13）；`check_video`（L17）；`check_links`（L25）。
- 函数内局部声明：`check_links.Links`（L28）；`check_links.Links.__init__`（L29，私有）；`check_links.Links.handle_starttag`（L32）。

### [topogym/recording/tasks/interlocked_claws/archive.py](../../../topogym/recording/tasks/interlocked_claws/archive.py)

- 模块函数：`sha`（L20）；`video_info`（L24）；`archive`（L30）；`update_catalog`（L78）。

### [topogym/recording/tasks/interlocked_claws/family_archive.py](../../../topogym/recording/tasks/interlocked_claws/family_archive.py)

- 模块函数：`archive`（L17）。

### [topogym/recording/tasks/interlocked_claws/family_render.py](../../../topogym/recording/tasks/interlocked_claws/family_render.py)

- 模块函数：`camera`（L21）；`render`（L25）。

### [topogym/recording/tasks/knot_untying/archive_demo.py](../../../topogym/recording/tasks/knot_untying/archive_demo.py)

- 模块函数：`digest`（L19）；`refresh_catalog`（L25）；`archive`（L44）；`main`（L117）。

### [topogym/recording/tasks/lock_picking/demo_archive.py](../../../topogym/recording/tasks/lock_picking/demo_archive.py)

- 模块函数：`archive`（L27）；`main`（L136）。

### [topogym/recording/tasks/orbits/motion_render.py](../../../topogym/recording/tasks/orbits/motion_render.py)

- 类：`OrbitsCordBinding`（L39）。
- 模块函数：`_frame`（L29，私有）；`build_scene`（L109）；`from_source`（L146）；`snapshot`（L162）；`render`（L224）。
- 类方法：`OrbitsCordBinding.__init__`（L42，私有）；`OrbitsCordBinding.export_state`（L63）；`OrbitsCordBinding.restore`（L66）；`OrbitsCordBinding.scene_report`（L100）。
- 函数内局部声明：`OrbitsCordBinding.__init__.upload`（L58，私有）。

### [topogym/recording/tasks/orbits/robot_recording.py](../../../topogym/recording/tasks/orbits/robot_recording.py)

- 类：`RobotRopeBinding`（L77）。
- 模块函数：`task_frame`（L25）；`install_presentation`（L30）；`from_source`（L104）；`snapshot`（L117）；`render`（L174）。
- 类方法：`RobotRopeBinding.scene_report`（L78）；`RobotRopeBinding.camera_poses`（L95）。

### [topogym/recording/tasks/rope_threading/archive.py](../../../topogym/recording/tasks/rope_threading/archive.py)

- 模块函数：`digest`（L20）；`save`（L24）；`archive`（L28）；`main`（L215）。

### [topogym/recording/tasks/slotted_post_ring/archive.py](../../../topogym/recording/tasks/slotted_post_ring/archive.py)

- 模块函数：`sha`（L18）；`check_relocated_model`（L22）；`copy_render_metadata`（L30）；`publication_allowed`（L40）；`archive`（L46）。

### [topogym/recording/tasks/slotted_post_ring/curate_demos.py](../../../topogym/recording/tasks/slotted_post_ring/curate_demos.py)

- 模块函数：`sha`（L14）；`curate`（L18）。

### [topogym/recording/timeline.py](../../../topogym/recording/timeline.py)

- 类：`SimulationTimeline`（L15）。
- 模块函数：`positive`（L8）；`replay_samples`（L38）。
- 类方法：`SimulationTimeline.__init__`（L16，私有）；`SimulationTimeline.advance`（L24）。

### [topogym/recording/validation.py](../../../topogym/recording/validation.py)

- 模块函数：`verify_evidence`（L11）；`validate`（L30）。

### [topogym/redundants/benchmarks/step_bench.py](../../../topogym/redundants/benchmarks/step_bench.py)

- 模块函数：`stop_before_physics`（L41）。
- 函数内局部声明：`stop_before_physics.timed`（L54）。

### [topogym/redundants/checks/fiber_bundling/contact_rule_probe.py](../../../topogym/redundants/checks/fiber_bundling/contact_rule_probe.py)

- 模块函数：`main`（L10）。

### [topogym/redundants/compatibility/recording/compatibility.py](../../../topogym/redundants/compatibility/recording/compatibility.py)

- 模块函数：`camera_trace`（L11）；`export_video_set`（L21）。

### [topogym/redundants/compatibility/recording/compatibility_recorder.py](../../../topogym/redundants/compatibility/recording/compatibility_recorder.py)

- 模块函数：`apply_recording_camera_overrides`（L23）；`_recording_camera_names`（L42，私有）；`select_recording_cameras`（L72）；`select_recording_camera_items`（L80）；`recording_session_from_config`（L87）；`print_recording_saved`（L100）；`recording_session`（L110）；`_normalize_camera_entry`（L174，私有）；`recording_camera_output_path`（L184）。
- 函数内局部声明：`recording_session.wrapped_step`（L148）。

### [topogym/redundants/compatibility/utils/franka.py](../../../topogym/redundants/compatibility/utils/franka.py)

- 模块函数：`initialize_franka_controller`（L8）。

### [topogym/redundants/compatibility/utils/recording.py](../../../topogym/redundants/compatibility/utils/recording.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/experiments/blanket_flatten/preview.py](../../../topogym/redundants/experiments/blanket_flatten/preview.py)

- 模块函数：`main`（L18）。
- 函数内局部声明：`main.settle`（L61）；`main.save_report`（L86）。

### [topogym/redundants/experiments/blanket_flatten/virtual_hands.py](../../../topogym/redundants/experiments/blanket_flatten/virtual_hands.py)

- 类：`VirtualHands`（L115）。
- 模块函数：`corner_patch`（L24）；`bounded_grip_velocity`（L32）；`upright_grip_targets`（L38）；`corner_material_rotation`（L54）；`edge_following_lay_targets`（L68）；`supported_patch_rotations`（L82）；`main`（L490）。
- 类方法：`VirtualHands.__init__`（L116，私有）；`VirtualHands.time`（L134）；`VirtualHands.label`（L137）；`VirtualHands.capture`（L143）；`VirtualHands.step`（L153）；`VirtualHands.grasp`（L181）；`VirtualHands.release`（L198）；`VirtualHands.release_one`（L206）；`VirtualHands.drive`（L213）；`VirtualHands.settle`（L236）；`VirtualHands.unfold`（L255）；`VirtualHands.spread_and_lay`（L322）；`VirtualHands.refine_corners`（L388）；`VirtualHands.save`（L462）。

### [topogym/redundants/experiments/buzz_wire_3d/preview.py](../../../topogym/redundants/experiments/buzz_wire_3d/preview.py)

- 模块函数：`tube_mesh`（L16）；`meshes`（L51）；`write_inspection`（L80）；`main`（L297）。
- 函数内局部声明：`write_inspection.draw_view`（L110）；`write_inspection.trace`（L158）。

### [topogym/redundants/experiments/buzz_wire_3d/probe.py](../../../topogym/redundants/experiments/buzz_wire_3d/probe.py)

- 类：`BuzzProbeLayout`（L19）。
- 模块函数：`build_buzz_probe`（L50）。
- 类方法：`BuzzProbeLayout.pose`（L27）；`BuzzProbeLayout.validate`（L43）。

### [topogym/redundants/experiments/cast_coil/demo.py](../../../topogym/redundants/experiments/cast_coil/demo.py)

- 模块函数：`as_numpy`（L18）；`check_settling`（L22）；`main`（L59）。

### [topogym/redundants/experiments/cast_coil/official_trial.py](../../../topogym/redundants/experiments/cast_coil/official_trial.py)

- 类：`PoseFamily`（L42）；`PrefixFamily`（L78）。
- 模块函数：`_path_gaps`（L27，私有）；`audit_candidate`（L125）；`boundary_trials`（L139）；`independent_witness`（L165）；`search`（L203）；`write_review`（L276）；`main`（L355）。
- 类方法：`PoseFamily.__init__`（L44，私有）；`PoseFamily.gaps`（L66）；`PoseFamily.separating_plane_gaps`（L69）；`PrefixFamily.__init__`（L79，私有）；`PrefixFamily.decode`（L92）；`PrefixFamily.translations`（L101）；`PrefixFamily.sampled_metrics`（L107）；`PrefixFamily.motions`（L113）。
- 函数内局部声明：`boundary_trials.objective`（L149）；`search.objective`（L233）。

### [topogym/redundants/experiments/cast_coil/physics_probe.py](../../../topogym/redundants/experiments/cast_coil/physics_probe.py)

- 模块函数：`array`（L22）；`target_at`（L26）；`specifications`（L45）；`build_probe`（L59）；`run_probe`（L112）；`main`（L270）。

### [topogym/redundants/experiments/cast_keyhole/demo.py](../../../topogym/redundants/experiments/cast_keyhole/demo.py)

- 模块函数：`as_numpy`（L14）；`check_settling`（L18）；`main`（L79）。

### [topogym/redundants/experiments/cast_keyhole/physics_probe.py](../../../topogym/redundants/experiments/cast_keyhole/physics_probe.py)

- 模块函数：`array`（L22）；`evidence_fingerprint`（L26）；`specifications`（L32）；`build_probe`（L59）；`run_probe`（L108）；`main`（L268）。

### [topogym/redundants/experiments/cast_keyhole/route_probe.py](../../../topogym/redundants/experiments/cast_keyhole/route_probe.py)

- 类：`PoseSegment`（L18）。
- 模块函数：`candidates`（L36）；`probe`（L65）；`main`（L110）。
- 类方法：`PoseSegment.pose`（L25）；`PoseSegment.speed_bound`（L30）。

### [topogym/redundants/experiments/cast_keyhole/trajectory_probe.py](../../../topogym/redundants/experiments/cast_keyhole/trajectory_probe.py)

- 模块函数：`schedule`（L24）；`target`（L39）；`run`（L57）；`main`（L170）。

### [topogym/redundants/experiments/fiber_bundling/anchored_probe.py](../../../topogym/redundants/experiments/fiber_bundling/anchored_probe.py)

- 模块函数：`main`（L15）。
- 函数内局部声明：`main.state`（L85）。

### [topogym/redundants/experiments/fiber_bundling/capsule_contact_probe.py](../../../topogym/redundants/experiments/fiber_bundling/capsule_contact_probe.py)

- 模块函数：`main`（L9）。

### [topogym/redundants/experiments/fiber_bundling/demo.py](../../../topogym/redundants/experiments/fiber_bundling/demo.py)

- 模块函数：`main`（L13）。

### [topogym/redundants/experiments/fiber_bundling/ik_search.py](../../../topogym/redundants/experiments/fiber_bundling/ik_search.py)

- 类：`BundleIKTrial`（L18）。
- 模块函数：`main`（L498）。
- 类方法：`BundleIKTrial.__init__`（L19，私有）；`BundleIKTrial.probe_root_move`（L36）；`BundleIKTrial.command_hand`（L75）；`BundleIKTrial.finish_phase`（L100）；`BundleIKTrial.initialize_root_control`（L119）；`BundleIKTrial.move_root`（L126）；`BundleIKTrial.park`（L154）；`BundleIKTrial.feed`（L163）；`BundleIKTrial.axial`（L171）；`BundleIKTrial.spiral`（L174）；`BundleIKTrial.side_sweep`（L194）；`BundleIKTrial.adaptive_sweep`（L214）；`BundleIKTrial.contact_sweep`（L232）；`BundleIKTrial.tug`（L264）；`BundleIKTrial.greedy_rim`（L273）；`BundleIKTrial.greedy_orbit`（L355）；`BundleIKTrial.prepare_orbit`（L372）；`BundleIKTrial.greedy_hybrid`（L425）；`BundleIKTrial.press_protrusion`（L451）；`BundleIKTrial.run`（L476）。

### [topogym/redundants/experiments/fiber_bundling/ik_turn_probe.py](../../../topogym/redundants/experiments/fiber_bundling/ik_turn_probe.py)

- 模块函数：`main`（L18）。

### [topogym/redundants/experiments/fiber_bundling/parallel_recheck.py](../../../topogym/redundants/experiments/fiber_bundling/parallel_recheck.py)

- 模块函数：`main`（L19）。

### [topogym/redundants/experiments/fiber_bundling/probe.py](../../../topogym/redundants/experiments/fiber_bundling/probe.py)

- 模块函数：`main`（L17）。

### [topogym/redundants/experiments/fiber_bundling/refined_variant_trial.py](../../../topogym/redundants/experiments/fiber_bundling/refined_variant_trial.py)

- 模块函数：`main`（L8）。

### [topogym/redundants/experiments/fiber_bundling/single_strand.py](../../../topogym/redundants/experiments/fiber_bundling/single_strand.py)

- 模块函数：`default_plan`（L17）；`strand_metrics`（L32）；`main`（L55）。
- 函数内局部声明：`main.sample`（L98）。

### [topogym/redundants/experiments/fiber_bundling/snapshot_trial.py](../../../topogym/redundants/experiments/fiber_bundling/snapshot_trial.py)

- 模块函数：`maybe_run_snapshot`（L14）。

### [topogym/redundants/experiments/fiber_bundling/variant_demo.py](../../../topogym/redundants/experiments/fiber_bundling/variant_demo.py)

- 模块函数：`main`（L15）。
- 函数内局部声明：`main.save`（L38）；`main.run`（L43）。

### [topogym/redundants/experiments/fiber_bundling/variant_trial.py](../../../topogym/redundants/experiments/fiber_bundling/variant_trial.py)

- 模块函数：`main`（L12）。

### [topogym/redundants/experiments/hedgehog_in_cage/demo.py](../../../topogym/redundants/experiments/hedgehog_in_cage/demo.py)

- 模块函数：`as_numpy`（L21）；`main`（L26）。

### [topogym/redundants/experiments/hedgehog_in_cage/side_window_probe.py](../../../topogym/redundants/experiments/hedgehog_in_cage/side_window_probe.py)

- 类：`Oracle`（L88）。
- 模块函数：`template`（L23）；`cage_meshes`（L38）；`check`（L112）；`run`（L126）。
- 类方法：`Oracle.__init__`（L89，私有）；`Oracle.distance`（L102）。

### [topogym/redundants/experiments/hedgehog_in_cage/stability.py](../../../topogym/redundants/experiments/hedgehog_in_cage/stability.py)

- 模块函数：`array`（L14）；`main`（L18）。

### [topogym/redundants/experiments/horseshoe_ring/chain_probe.py](../../../topogym/redundants/experiments/horseshoe_ring/chain_probe.py)

- 类：`ChainProbeLayout`（L12）。
- 模块函数：`build_chain_probe`（L38）。
- 类方法：`ChainProbeLayout.poses`（L17）；`ChainProbeLayout.linking`（L22）；`ChainProbeLayout.validate`（L27）。

### [topogym/redundants/experiments/horseshoe_ring/demo.py](../../../topogym/redundants/experiments/horseshoe_ring/demo.py)

- 模块函数：`as_numpy`（L21）；`current_loops`（L25）；`check_settling`（L41）；`main`（L83）。

### [topogym/redundants/experiments/horseshoe_ring/experiments.py](../../../topogym/redundants/experiments/horseshoe_ring/experiments.py)

- 模块函数：`tutorial_section`（L22）；`straight_path`（L42）；`run_sweep`（L47）；`main`（L113）。

### [topogym/redundants/experiments/horseshoe_ring/family_space.py](../../../topogym/redundants/experiments/horseshoe_ring/family_space.py)

- 模块函数：`hash_json`（L29）；`normalized_trace`（L33）；`arc_sample`（L55）；`route_distance`（L63）；`build`（L74）；`appearance_checks`（L174）；`draw_routes`（L188）；`draw_appearances`（L203）；`write_page`（L223）。

### [topogym/redundants/experiments/horseshoe_ring/gravity_demo.py](../../../topogym/redundants/experiments/horseshoe_ring/gravity_demo.py)

- 模块函数：`array`（L25）；`sha`（L29）；`run`（L33）；`main`（L230）。
- 函数内局部声明：`run.replace_grasps`（L99）；`run.bilateral`（L130）；`run.handovers`（L138）。

### [topogym/redundants/experiments/horseshoe_ring/shape_variants.py](../../../topogym/redundants/experiments/horseshoe_ring/shape_variants.py)

- 类：`TargetRepair`（L93）。
- 模块函数：`seed`（L22）；`make_template`（L26）；`retarget_frames`（L56）；`probe`（L74）；`repair_path`（L142）；`frames_from_edits`（L180）；`polish_path`（L191）。
- 类方法：`TargetRepair.__init__`（L95，私有）；`TargetRepair.set_frame`（L102）；`TargetRepair.gaps`（L109）；`TargetRepair.solve`（L123）。

### [topogym/redundants/experiments/horseshoe_ring/witness_demo.py](../../../topogym/redundants/experiments/horseshoe_ring/witness_demo.py)

- 模块函数：`main`（L22）。
- 函数内局部声明：`main.pose`（L50）。

### [topogym/redundants/experiments/interlocked_claws/contact_probe.py](../../../topogym/redundants/experiments/interlocked_claws/contact_probe.py)

- 模块函数：`run`（L14）。

### [topogym/redundants/experiments/interlocked_claws/demo.py](../../../topogym/redundants/experiments/interlocked_claws/demo.py)

- 模块函数：`write_review`（L16）；`main`（L45）。

### [topogym/redundants/experiments/interlocked_claws/family_space.py](../../../topogym/redundants/experiments/interlocked_claws/family_space.py)

- 模块函数：`audit`（L17）；`export`（L82）。
- 函数内局部声明：`export.relative`（L91）。

### [topogym/redundants/experiments/knot_untying/contact_probe.py](../../../topogym/redundants/experiments/knot_untying/contact_probe.py)

- 类：`CrossedStrandActions`（L11）。
- 模块函数：`build_contact_scene`（L76）。
- 类方法：`CrossedStrandActions.__init__`（L12，私有）；`CrossedStrandActions.declare`（L15）；`CrossedStrandActions.specification`（L20）；`CrossedStrandActions.update`（L30）；`CrossedStrandActions.observe`（L49）；`CrossedStrandActions.report`（L58）。

### [topogym/redundants/experiments/knot_untying/demo.py](../../../topogym/redundants/experiments/knot_untying/demo.py)

- 模块函数：`inspect_settled_centerline`（L11）；`write_review`（L23）；`main`（L49）。

### [topogym/redundants/experiments/knot_untying/physics_probe.py](../../../topogym/redundants/experiments/knot_untying/physics_probe.py)

- 类：`SolverLog`（L25）。
- 模块函数：`make_config`（L81）；`main`（L123）。
- 类方法：`SolverLog.__init__`（L27，私有）；`SolverLog.__enter__`（L33，私有）；`SolverLog.update`（L47）；`SolverLog.__exit__`（L60，私有）；`SolverLog.report`（L75）。

### [topogym/redundants/experiments/knot_untying/physics_suite.py](../../../topogym/redundants/experiments/knot_untying/physics_suite.py)

- 模块函数：`cases`（L17）；`main`（L34）。

### [topogym/redundants/experiments/knot_untying/probe_actions.py](../../../topogym/redundants/experiments/knot_untying/probe_actions.py)

- 类：`ProbeActions`（L10）。
- 模块函数：`smoothstep`（L5）。
- 类方法：`ProbeActions.__init__`（L11，私有）；`ProbeActions.specification`（L19）；`ProbeActions.declare`（L33）；`ProbeActions.update`（L41）；`ProbeActions.observe`（L73）；`ProbeActions.release`（L83）；`ProbeActions.report`（L89）。

### [topogym/redundants/experiments/knot_untying/robot_probe.py](../../../topogym/redundants/experiments/knot_untying/robot_probe.py)

- 类：`RobotGraspActions`（L28）；`RobotContactActions`（L320）。
- 模块函数：`rotation`（L15）；`configure_contact_start`（L19）。
- 类方法：`RobotGraspActions.__init__`（L29，私有）；`RobotGraspActions.specification`（L44）；`RobotGraspActions.declare`（L60）；`RobotGraspActions.configure`（L67）；`RobotGraspActions.tool_position`（L86）；`RobotGraspActions.band_pose`（L89）；`RobotGraspActions.move`（L106）；`RobotGraspActions.approach`（L110）；`RobotGraspActions.interpolate`（L124）；`RobotGraspActions.gaps`（L129）；`RobotGraspActions.close_contact_monitors`（L146）；`RobotGraspActions.close`（L150）；`RobotGraspActions.release`（L174）；`RobotGraspActions.update`（L184）；`RobotGraspActions.observe`（L245）；`RobotGraspActions.report`（L294）；`RobotContactActions.specification`（L322）；`RobotContactActions.update`（L330）；`RobotContactActions.report`（L362）。

### [topogym/redundants/experiments/lock_picking/family_space.py](../../../topogym/redundants/experiments/lock_picking/family_space.py)

- 模块函数：`candidate`（L28）；`sector_path`（L63）；`gallery`（L69）；`review`（L108）；`build`（L137）。

### [topogym/redundants/experiments/orbits/bimanual_bight_demo.py](../../../topogym/redundants/experiments/orbits/bimanual_bight_demo.py)

- 模块函数：`run`（L20）。

### [topogym/redundants/experiments/orbits/grasp_demo.py](../../../topogym/redundants/experiments/orbits/grasp_demo.py)

- 模块函数：`run`（L19）。

### [topogym/redundants/experiments/orbits/preview.py](../../../topogym/redundants/experiments/orbits/preview.py)

- 模块函数：`_array`（L13，私有）；`main`（L19）。

### [topogym/redundants/experiments/orbits/rope_only_demo.py](../../../topogym/redundants/experiments/orbits/rope_only_demo.py)

- 模块函数：`run_prefix`（L13）；`run`（L76）。

### [topogym/redundants/experiments/orbits/two_control_route.py](../../../topogym/redundants/experiments/orbits/two_control_route.py)

- 模块函数：`orient_held_handle_flat`（L25）；`run`（L40）；`audit`（L152）。
- 函数内局部声明：`run.motion`（L69）。

### [topogym/redundants/experiments/rope_threading/contact_probe.py](../../../topogym/redundants/experiments/rope_threading/contact_probe.py)

- 类：`RingContactActions`（L11）。
- 类方法：`RingContactActions.__init__`（L12，私有）；`RingContactActions.declare`（L27）；`RingContactActions.specification`（L36）；`RingContactActions.configure`（L50）；`RingContactActions.update`（L58）；`RingContactActions.observe`（L90）；`RingContactActions.report`（L103）。

### [topogym/redundants/experiments/rope_threading/demo.py](../../../topogym/redundants/experiments/rope_threading/demo.py)

- 模块函数：`write_review`（L11）；`main`（L41）。
- 函数内局部声明：`main.capture`（L81）。

### [topogym/redundants/experiments/rope_threading/physics_probe.py](../../../topogym/redundants/experiments/rope_threading/physics_probe.py)

- 模块函数：`validate_execution_mode`（L21）；`classify_execution`（L35）；`make_config`（L50）；`main`（L84）。
- 函数内局部声明：`main.observe_with_table_bounds`（L237）。

### [topogym/redundants/experiments/rope_threading/physics_suite.py](../../../topogym/redundants/experiments/rope_threading/physics_suite.py)

- 模块函数：`wait_for_gpu_memory`（L13）；`main`（L30）。

### [topogym/redundants/experiments/rope_threading/startup_study.py](../../../topogym/redundants/experiments/rope_threading/startup_study.py)

- 模块函数：`summarize`（L26）；`main`（L72）。

### [topogym/redundants/experiments/slotted_post_ring/preview.py](../../../topogym/redundants/experiments/slotted_post_ring/preview.py)

- 模块函数：`_array`（L13，私有）；`main`（L19）。

### [topogym/redundants/mujoco/recording/adapters/mujoco.py](../../../topogym/redundants/mujoco/recording/adapters/mujoco.py)

- 类：`MuJoCoBinding`（L9）。
- 模块函数：`from_source`（L134）。
- 类方法：`MuJoCoBinding.__init__`（L10，私有）；`MuJoCoBinding.clock`（L29）；`MuJoCoBinding.subscribe`（L33）；`MuJoCoBinding.export_state`（L59）；`MuJoCoBinding.restore_time`（L62）；`MuJoCoBinding.restore`（L69）；`MuJoCoBinding.render`（L87）；`MuJoCoBinding.scene_report`（L100）；`MuJoCoBinding.camera_poses`（L120）；`MuJoCoBinding.close`（L128）。
- 函数内局部声明：`MuJoCoBinding.subscribe.step`（L41）。

### [topogym/redundants/mujoco/tasks/interlocked_claws/family_balanced_robot.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_balanced_robot.py)

- 模块函数：`build_plan`（L23）。
- 函数内局部声明：`build_plan.append`（L28）。

### [topogym/redundants/mujoco/tasks/interlocked_claws/family_physics.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_physics.py)

- 模块函数：`values`（L21）；`quat`（L25）；`save`（L29）；`sha`（L33）；`contact_time`（L37）；`base_xml`（L41）；`add_part`（L55）；`body_pose`（L73）；`contact_metrics`（L77）；`_run_drop`（L93，私有）；`_run_drive`（L127，私有）；`bench`（L195）。

### [topogym/redundants/mujoco/tasks/interlocked_claws/family_robot.py](../../../topogym/redundants/mujoco/tasks/interlocked_claws/family_robot.py)

- 模块函数：`assembly_poses`（L23）；`xml_scene`（L54）；`set_initial`（L90）；`contacts`（L98）；`robot_support_contacts`（L118）；`build_plan`（L130）；`execute`（L217）。

### [topogym/redundants/mujoco/tasks/orbits/dynamics.py](../../../topogym/redundants/mujoco/tasks/orbits/dynamics.py)

- 类：`Probe`（L218）。
- 模块函数：`vector`（L18）；`resample`（L22）；`working_cord`（L28）；`natural_working_state`（L57）；`build_probe`（L104）。
- 类方法：`Probe.__init__`（L219，私有）；`Probe.points`（L237）；`Probe.grasp_nodes`（L240）；`Probe.grasp_midpoint`（L253）；`Probe.grasp_node`（L256）；`Probe.pin_node`（L267）；`Probe.restore`（L278）；`Probe.move`（L310）；`Probe.save_checkpoint`（L408）；`Probe.save`（L421）。
- 函数内局部声明：`natural_working_state.shaped`（L84）；`natural_working_state.excess`（L91）。

### [topogym/redundants/mujoco/tasks/orbits/robot_dynamics.py](../../../topogym/redundants/mujoco/tasks/orbits/robot_dynamics.py)

- 模块函数：`build_robot_model`（L19）。

### [topogym/redundants/mujoco/tasks/orbits/robot_runtime.py](../../../topogym/redundants/mujoco/tasks/orbits/robot_runtime.py)

- 类：`RobotRuntime`（L20）。
- 模块函数：`pickup_probe`（L307）。
- 类方法：`RobotRuntime.__init__`（L21，私有）；`RobotRuntime.points`（L41）；`RobotRuntime.record`（L44）；`RobotRuntime.joint_move`（L49）；`RobotRuntime.joint_path`（L52）；`RobotRuntime.ik`（L155）；`RobotRuntime.grasp_contacts`（L169）；`RobotRuntime.engage_grasp`（L199）；`RobotRuntime.release_grasp`（L226）；`RobotRuntime.save_checkpoint`（L241）；`RobotRuntime.restore_checkpoint`（L257）；`RobotRuntime.save`（L284）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/fem.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem.py)

- 类：`FEMSettings`（L21）。
- 模块函数：`rounded_bead_sections`（L60）；`apply_bead_mouth_fillet`（L81）；`signed_volumes`（L103）；`native_moduli`（L109）；`check_constitutive_response`（L123）；`tube_tetrahedra`（L158）；`build_model`（L191）。
- 类方法：`FEMSettings.validate`（L37）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_fixture.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_fixture.py)

- 类：`VolumeAudit`（L42）。
- 模块函数：`minimum_jerk`（L27）；`rotational_gains`（L33）；`execute`（L113）。
- 类方法：`VolumeAudit.__init__`（L43，私有）；`VolumeAudit.observe`（L59）；`VolumeAudit.solved`（L89）；`VolumeAudit.tail_checks`（L94）；`VolumeAudit.checks`（L102）。
- 函数内局部声明：`execute.record`（L159）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_grasp.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_grasp.py)

- 类：`CrossSectionGrasp`（L19）。
- 模块函数：`is_grasp_channel`（L15）；`configure_grasps`（L75）。
- 类方法：`CrossSectionGrasp.__init__`（L20，私有）；`CrossSectionGrasp.position`（L59）；`CrossSectionGrasp.velocity`（L62）；`CrossSectionGrasp.forces`（L65）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/fem_probe.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fem_probe.py)

- 模块函数：`settle`（L17）；`main`（L135）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/fixture.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/fixture.py)

- 模块函数：`pose`（L18）；`cord_disk_crossings`（L22）；`route`（L35）；`execute`（L115）；`interactive_stages`（L273）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/physics.py)

- 类：`PhysicsSettings`（L39）。
- 模块函数：`values`（L22）；`wxyz`（L26）；`capture_sources`（L30）；`build_model`（L52）；`node_positions`（L223）；`contact_summary`（L228）。
- 函数内局部声明：`build_model.visual_mesh`（L109）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/probe.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/probe.py)

- 模块函数：`settle`（L15）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/robot.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/robot.py)

- 模块函数：`rotation`（L19）；`robot_contacts`（L25）；`execute`（L42）。

### [topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py](../../../topogym/redundants/mujoco/tasks/slotted_post_ring/robot_sequence.py)

- 类：`Episode`（L49）。
- 模块函数：`static_collisions`（L30）；`main`（L278）。
- 类方法：`Episode.__init__`（L50，私有）；`Episode.body_pose`（L92）；`Episode.tcp`（L96）；`Episode.relative_grasp`（L100）；`Episode.contacts`（L104）；`Episode.audit`（L116）；`Episode.move`（L141）；`Episode.grasp`（L222）；`Episode.release`（L240）；`Episode.finish`（L246）。

### [topogym/redundants/mujoco/world/mujoco_presentation.py](../../../topogym/redundants/mujoco/world/mujoco_presentation.py)

- 模块函数：`physics_xml_signature`（L10）；`add_lab`（L22）；`add_camera`（L60）。

### [topogym/redundants/package_markers/core/__init__.py](../../../topogym/redundants/package_markers/core/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/generation/__init__.py](../../../topogym/redundants/package_markers/generation/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/planning/__init__.py](../../../topogym/redundants/package_markers/planning/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/primitives/__init__.py](../../../topogym/redundants/package_markers/primitives/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/runtime/__init__.py](../../../topogym/redundants/package_markers/runtime/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/supervision/__init__.py](../../../topogym/redundants/package_markers/supervision/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/blanket_flatten/__init__.py](../../../topogym/redundants/package_markers/tasks/blanket_flatten/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/buzz_wire_3d/__init__.py](../../../topogym/redundants/package_markers/tasks/buzz_wire_3d/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/cast_coil/__init__.py](../../../topogym/redundants/package_markers/tasks/cast_coil/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/cast_keyhole/__init__.py](../../../topogym/redundants/package_markers/tasks/cast_keyhole/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/fiber_bundling/__init__.py](../../../topogym/redundants/package_markers/tasks/fiber_bundling/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/hedgehog_in_cage/__init__.py](../../../topogym/redundants/package_markers/tasks/hedgehog_in_cage/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/horseshoe_ring/__init__.py](../../../topogym/redundants/package_markers/tasks/horseshoe_ring/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/interlocked_claws/__init__.py](../../../topogym/redundants/package_markers/tasks/interlocked_claws/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/knot_untying/__init__.py](../../../topogym/redundants/package_markers/tasks/knot_untying/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/lock_picking/__init__.py](../../../topogym/redundants/package_markers/tasks/lock_picking/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/orbits/__init__.py](../../../topogym/redundants/package_markers/tasks/orbits/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/rope_threading/__init__.py](../../../topogym/redundants/package_markers/tasks/rope_threading/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/package_markers/tasks/slotted_post_ring/__init__.py](../../../topogym/redundants/package_markers/tasks/slotted_post_ring/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/presentation/cast_coil/solvability_view.html](../../../topogym/redundants/presentation/cast_coil/solvability_view.html)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/presentation/cast_keyhole/review.py](../../../topogym/redundants/presentation/cast_keyhole/review.py)

- 模块函数：`build_review`（L14）；`main`（L129）。

### [topogym/redundants/presentation/cast_keyhole/solution_diagnostics.py](../../../topogym/redundants/presentation/cast_keyhole/solution_diagnostics.py)

- 模块函数：`draw`（L13）；`main`（L53）。

### [topogym/redundants/presentation/fiber_bundling/plot_variants.py](../../../topogym/redundants/presentation/fiber_bundling/plot_variants.py)

- 模块函数：`diagram`（L9）；`main`（L43）。

### [topogym/redundants/presentation/fiber_bundling/review.py](../../../topogym/redundants/presentation/fiber_bundling/review.py)

- 模块函数：`write_review`（L11）。

### [topogym/redundants/presentation/hedgehog_in_cage/family_review.py](../../../topogym/redundants/presentation/hedgehog_in_cage/family_review.py)

- 模块函数：`cross_check`（L13）；`figures`（L31）；`main`（L56）。

### [topogym/redundants/presentation/horseshoe_ring/inverse_review.py](../../../topogym/redundants/presentation/horseshoe_ring/inverse_review.py)

- 模块函数：`write_review`（L9）。
- 函数内局部声明：`write_review.compact`（L34）。

### [topogym/redundants/presentation/horseshoe_ring/shape_review.py](../../../topogym/redundants/presentation/horseshoe_ring/shape_review.py)

- 模块函数：`build_review`（L13）；`plot_outlines`（L51）。

### [topogym/redundants/presentation/horseshoe_ring/shape_viewer.html](../../../topogym/redundants/presentation/horseshoe_ring/shape_viewer.html)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/presentation/horseshoe_ring/trace_review.py](../../../topogym/redundants/presentation/horseshoe_ring/trace_review.py)

- 模块函数：`write_review`（L7）。

### [topogym/redundants/presentation/lock_picking/inverse_variants_review.html](../../../topogym/redundants/presentation/lock_picking/inverse_variants_review.html)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/redundants/presentation/slotted_post_ring/review.py](../../../topogym/redundants/presentation/slotted_post_ring/review.py)

- 模块函数：`review`（L13）。

### [topogym/robot/__init__.py](../../../topogym/robot/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/robot/aloha.py](../../../topogym/robot/aloha.py)

- 类：`AlohaArmController`（L18）；`AlohaDualArmController`（L107）。
- 模块函数：`_numpy`（L12，私有）。
- 类方法：`AlohaArmController.__init__`（L19，私有）；`AlohaArmController.configure`（L32）；`AlohaArmController.reset_home`（L38）；`AlohaArmController.step`（L45）；`AlohaArmController.set_arm_qpos`（L49）；`AlohaArmController.set_gripper`（L59）；`AlohaArmController.open_gripper`（L67）；`AlohaArmController.close_gripper`（L70）；`AlohaArmController.move_ee_to`（L73）；`AlohaArmController.arm_qpos`（L86）；`AlohaArmController.gripper_qpos`（L89）；`AlohaArmController._qpos`（L93，私有）；`AlohaArmController.hand_pos`（L96）；`AlohaArmController.hand_quat`（L99）；`AlohaArmController.grasp_center_pos`（L102）；`AlohaDualArmController.__init__`（L108，私有）；`AlohaDualArmController.configure`（L114）；`AlohaDualArmController.reset_home`（L118）；`AlohaDualArmController.step`（L124）；`AlohaDualArmController.state`（L128）。

### [topogym/robot/aloha_contract.py](../../../topogym/robot/aloha_contract.py)

- 模块函数：`contract`（L5）；`validate_action`（L46）。

### [topogym/robot/factory.py](../../../topogym/robot/factory.py)

- 模块函数：`initialize_robot_controller`（L6）。

### [topogym/robot/franka.py](../../../topogym/robot/franka.py)

- 类：`FrankaPositionIKController`（L33）。
- 模块函数：`_array`（L12，私有）；`_as_numpy`（L18，私有）；`_xyz`（L24，私有）；`_quat`（L28，私有）。
- 类方法：`FrankaPositionIKController.__post_init__`（L40，私有）；`FrankaPositionIKController.configure`（L55）；`FrankaPositionIKController.reset_home`（L82）；`FrankaPositionIKController.step`（L114）；`FrankaPositionIKController.open_gripper`（L118）；`FrankaPositionIKController.close_gripper`（L125）；`FrankaPositionIKController.set_gripper`（L132）；`FrankaPositionIKController.move_ee_to`（L142）；`FrankaPositionIKController.hand_pos`（L227）；`FrankaPositionIKController.hand_quat`（L230）；`FrankaPositionIKController.gripper_qpos`（L233）；`FrankaPositionIKController._control_gripper`（L248，私有）；`FrankaPositionIKController.arm_qpos`（L258）；`FrankaPositionIKController.grasp_center_pos`（L265）；`FrankaPositionIKController.pad_half_height`（L276）；`FrankaPositionIKController.lowest_pad_z`（L279）；`FrankaPositionIKController.gripper_settle_steps`（L282）；`FrankaPositionIKController.oracle_motion_time_scale`（L297）。
- 函数内局部声明：`FrankaPositionIKController.move_ee_to.budget`（L169）。

### [topogym/robot/grasp_constraints.py](../../../topogym/robot/grasp_constraints.py)

- 模块函数：`active_grasps`（L12）；`release_grasps`（L27）。
- 函数内局部声明：`active_grasps.values`（L15）。

### [topogym/robot/grasping/attachment.py](../../../topogym/robot/grasping/attachment.py)

- 类：`RigidAttachment`（L81）；`ParticleAttachment`（L330）；`AttachmentManager`（L462）。
- 模块函数：`_quat_conj`（L11，私有）；`_quat_rotate`（L16，私有）；`_as_numpy`（L25，私有）；`_xyz`（L31，私有）；`yaw_quat`（L35）；`rotate_z`（L40）；`parent_pos_for_child`（L54）；`slerp`（L58）。
- 类方法：`RigidAttachment.attach`（L178）；`RigidAttachment.set_yaw`（L193）；`RigidAttachment.ramp_to`（L196）；`RigidAttachment.ramping`（L236）；`RigidAttachment.commanded_quat`（L239）；`RigidAttachment.sync`（L269）；`RigidAttachment._clamped`（L295，私有）；`RigidAttachment._advance_ramp`（L302，私有）；`RigidAttachment.release`（L324）；`ParticleAttachment.__init__`（L353，私有）；`ParticleAttachment.particles`（L389）；`ParticleAttachment.center`（L395）；`ParticleAttachment.attach`（L400）；`ParticleAttachment.drive_to`（L408）；`ParticleAttachment._particles_at`（L438，私有）；`ParticleAttachment._velocities_at`（L444，私有）；`ParticleAttachment.sync`（L450）；`ParticleAttachment.release`（L456）；`AttachmentManager.__init__`（L465，私有）；`AttachmentManager.create`（L470）；`AttachmentManager.sync`（L497）；`AttachmentManager.__enter__`（L501，私有）；`AttachmentManager.__exit__`（L515，私有）。
- 函数内局部声明：`AttachmentManager.__enter__.wrapped_step`（L506，私有）。

### [topogym/robot/grasping/cast_coil/robot_grasp.py](../../../topogym/robot/grasping/cast_coil/robot_grasp.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/robot/grasping/connector_latch.py](../../../topogym/robot/grasping/connector_latch.py)

- 类：`ConnectorLatch`（L32）。
- 模块函数：`_as_numpy`（L11，私有）；`_local_z_axis`（L17，私有）。
- 类方法：`ConnectorLatch.__post_init__`（L60，私有）；`ConnectorLatch.install`（L79）；`ConnectorLatch.uninstall`（L100）；`ConnectorLatch.try_engage`（L110）；`ConnectorLatch.sync`（L144）。
- 函数内局部声明：`ConnectorLatch.install.wrapped_step`（L86）。

### [topogym/robot/grasping/fem_attachment.py](../../../topogym/robot/grasping/fem_attachment.py)

- 类：`FEMRopeAttachment`（L32）。
- 模块函数：`_positions`（L27，私有）。
- 类方法：`FEMRopeAttachment.__init__`（L40，私有）；`FEMRopeAttachment.indices`（L47）；`FEMRopeAttachment.attach`（L50）；`FEMRopeAttachment.drive_to`（L65）；`FEMRopeAttachment.band_center`（L71）；`FEMRopeAttachment.release`（L74）。

### [topogym/robot/grasping/lock_picking/grasp.py](../../../topogym/robot/grasping/lock_picking/grasp.py)

- 类：`StagedLockGrasp`（L22）。
- 模块函数：`hand_pose`（L6）；`actual_hand_pose`（L12）。
- 类方法：`StagedLockGrasp.__init__`（L23，私有）；`StagedLockGrasp.attach`（L28）；`StagedLockGrasp.detach`（L59）。

### [topogym/robot/grasping/physical_contact.py](../../../topogym/robot/grasping/physical_contact.py)

- 模块函数：`print_collision_il_contract`（L6）；`entity_pos`（L34）；`entity_quat`（L41）；`ee_quat_for_yaw`（L50）；`validate_rigid_friction`（L58）；`configure_gripper_contact_friction`（L67）；`configure_finger_contact_friction`（L85）；`quat_mul`（L99）；`quat_about_axis`（L118）。

### [topogym/robot/gripper.py](../../../topogym/robot/gripper.py)

- 模块函数：`calibration`（L11）；`robotiq_joint_targets`（L16）；`as_numpy`（L31）；`robotiq_pad_centres`（L35）；`pad_vertices`（L48）。

### [topogym/robot/panda_contract.py](../../../topogym/robot/panda_contract.py)

- 类：`PandaPort`（L65）。
- 模块函数：`contract`（L7）；`validate_action`（L46）。
- 类方法：`PandaPort.__init__`（L67，私有）；`PandaPort.current_gripper_qpos`（L72）；`PandaPort.arm_qpos`（L75）；`PandaPort.set_arm_qpos`（L78）；`PandaPort.set_gripper`（L81）；`PandaPort.state`（L84）。

### [topogym/sensors/aloha_cameras.py](../../../topogym/sensors/aloha_cameras.py)

- 模块函数：`optical_pose`（L21）；`make_aloha_rig`（L27）；`configure_aloha_rig`（L68）。

### [topogym/sensors/camera_info.py](../../../topogym/sensors/camera_info.py)

- 模块函数：`optical_transform`（L5）；`pose_metadata`（L19）；`camera_contract`（L29）。

### [topogym/sensors/cameras.py](../../../topogym/sensors/cameras.py)

- 模块函数：`update_dynamic_camera`（L4）。

### [topogym/sensors/hud.py](../../../topogym/sensors/hud.py)

- 模块函数：`hud_lines`（L12）；`draw_hud_overlay`（L23）。

### [topogym/sensors/lighting.py](../../../topogym/sensors/lighting.py)

- 模块函数：`_plain`（L35，私有）；`_get`（L41，私有）；`_vec3`（L48，私有）；`vis_options`（L53）。

### [topogym/sensors/materials.py](../../../topogym/sensors/materials.py)

- 模块函数：`plastic`（L37）；`texture_reaches_renderer`（L88）。

### [topogym/sensors/nyx.py](../../../topogym/sensors/nyx.py)

- 类：`NyxCamera`（L149）。
- 模块函数：`asset_path`（L19）；`apply_finishes`（L25）；`camera_kwargs`（L86）；`add_camera`（L109）；`rgb`（L138）。
- 类方法：`NyxCamera.__init__`（L157，私有）；`NyxCamera.__getattr__`（L165，私有）；`NyxCamera.render`（L168）；`NyxCamera._rgb`（L206，私有）。

### [topogym/sensors/presentation.py](../../../topogym/sensors/presentation.py)

- 模块函数：`default_presentation_config`（L7）；`prepare_presentation`（L13）；`add_preview_camera`（L58）。

### [topogym/solvers/collision/blanket_flatten/robot_clearance.py](../../../topogym/solvers/collision/blanket_flatten/robot_clearance.py)

- 模块函数：`surface_clearance`（L6）；`robot_clearance`（L14）。

### [topogym/solvers/collision/cast_keyhole/collision.py](../../../topogym/solvers/collision/cast_keyhole/collision.py)

- 类：`CompoundCollision`（L16）；`Motion`（L62）。
- 模块函数：`directions`（L9）；`certify_motion`（L84）。
- 类方法：`CompoundCollision.__init__`（L23，私有）；`CompoundCollision._data`（L30，私有）；`CompoundCollision.gap`（L36）；`Motion.pose`（L71）；`Motion.speed_bound`（L77）。

### [topogym/solvers/collision/horseshoe_ring/robot_clearance.py](../../../topogym/solvers/collision/horseshoe_ring/robot_clearance.py)

- 类：`RobotClearance`（L12）。
- 类方法：`RobotClearance.__init__`（L13，私有）；`RobotClearance.violations`（L41）；`RobotClearance.joint_transfer`（L82）。
- 函数内局部声明：`RobotClearance.joint_transfer.valid`（L89）。

### [topogym/solvers/collision/interlocked_claws/collision.py](../../../topogym/solvers/collision/interlocked_claws/collision.py)

- 类：`ClawCollision`（L6）。
- 类方法：`ClawCollision.__init__`（L7，私有）；`ClawCollision.clearance`（L16）；`ClawCollision.contact_depth`（L24）。

### [topogym/solvers/collision/knot_untying/robot_clearance.py](../../../topogym/solvers/collision/knot_untying/robot_clearance.py)

- 模块函数：`measured_robot_data`（L11）；`measured_robot_overlap`（L21）；`gripper_geometry`（L36）；`gripper_floor_clearance`（L55）；`checked_cartesian_withdrawal`（L61）；`checked_grasp_approach`（L104）；`checked_support_grasp_approach`（L161）。
- 函数内局部声明：`checked_cartesian_withdrawal.check`（L77）；`checked_grasp_approach.check`（L121）。

### [topogym/solvers/collision/rope_threading/robot_mesh_guard.py](../../../topogym/solvers/collision/rope_threading/robot_mesh_guard.py)

- 类：`MeasuredRobotMeshGuard`（L39）。
- 模块函数：`_triangle_worker`（L12，私有）。
- 类方法：`MeasuredRobotMeshGuard.__init__`（L40，私有）；`MeasuredRobotMeshGuard._triangle_intersection`（L47，私有）；`MeasuredRobotMeshGuard.close`（L80）；`MeasuredRobotMeshGuard.check`（L95）；`MeasuredRobotMeshGuard.report`（L128）。

### [topogym/solvers/geometry/buzz_wire_3d/family_witness.py](../../../topogym/solvers/geometry/buzz_wire_3d/family_witness.py)

- 模块函数：`witness`（L20）。
- 函数内局部声明：`witness.evaluate`（L69）；`witness.objective`（L73）；`witness.constraint`（L80）。

### [topogym/solvers/geometry/cast_coil/solvability.py](../../../topogym/solvers/geometry/cast_coil/solvability.py)

- 模块函数：`minimum_height`（L26）；`table_audit`（L64）；`exported_boxes_match`（L82）；`mesh_crosscheck`（L109）；`cached_physics`（L139）；`write_view`（L159）；`plot_steps`（L169）；`run`（L207）。
- 函数内局部声明：`exported_boxes_match.canonical`（L100）。

### [topogym/solvers/geometry/cast_keyhole/instance_solution.py](../../../topogym/solvers/geometry/cast_keyhole/instance_solution.py)

- 模块函数：`initial_relative_pose`（L21）；`fingerprints`（L41）；`certify`（L48）；`require_current_instance_certificate`（L90）；`main`（L111）。

### [topogym/solvers/geometry/cast_keyhole/solution.py](../../../topogym/solvers/geometry/cast_keyhole/solution.py)

- 模块函数：`source_fingerprints`（L29）；`canonical_geometry`（L36）；`unpack_pose`（L48）；`read_motion`（L56）；`load_solution`（L71）；`certify`（L83）；`require_current_full_certificate`（L132）；`main`（L154）。

### [topogym/solvers/geometry/horseshoe_ring/independent_motion.py](../../../topogym/solvers/geometry/horseshoe_ring/independent_motion.py)

- 类：`IndependentWitness`（L29）。
- 模块函数：`interpolate`（L18）；`main`（L139）。
- 类方法：`IndependentWitness.__init__`（L30，私有）；`IndependentWitness.validate`（L42）；`IndependentWitness.distances`（L52）；`IndependentWitness.motion_bounds`（L60）；`IndependentWitness.goal`（L65）；`IndependentWitness.certify`（L77）。
- 函数内局部声明：`IndependentWitness.certify.check`（L92）。

### [topogym/solvers/geometry/horseshoe_ring/solvability.py](../../../topogym/solvers/geometry/horseshoe_ring/solvability.py)

- 类：`WitnessModel`（L70）。
- 模块函数：`outer_collision_mesh`（L36）；`collision_object`（L62）；`certify_path`（L130）；`export_body_poses`（L197）；`write_artifacts`（L208）；`main`（L221）。
- 类方法：`WitnessModel.__init__`（L71，私有）；`WitnessModel.distances`（L84）；`WitnessModel.initial_internal_clearance`（L91）；`WitnessModel.motion_bounds`（L100）；`WitnessModel.separated_goal`（L117）。
- 函数内局部声明：`certify_path.check`（L152）。

### [topogym/solvers/geometry/lock_picking/certificate.py](../../../topogym/solvers/geometry/lock_picking/certificate.py)

- 模块函数：`certificate`（L12）；`measured_retreat_cycles`（L91）。
- 函数内局部声明：`certificate.overlap`（L23）。

### [topogym/solvers/kinematics/blanket_flatten/bimanual_kinematics.py](../../../topogym/solvers/kinematics/blanket_flatten/bimanual_kinematics.py)

- 类：`AlohaKinematics`（L20）。
- 模块函数：`rigid_fit`（L10）。
- 类方法：`AlohaKinematics.__init__`（L21，私有）；`AlohaKinematics.sync`（L51）；`AlohaKinematics.forward`（L57）；`AlohaKinematics.pose`（L61）；`AlohaKinematics.solve`（L68）；`AlohaKinematics.collision_check`（L84）。
- 函数内局部声明：`AlohaKinematics.solve.residual`（L70）。

### [topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py](../../../topogym/solvers/kinematics/buzz_wire_3d/robot_plan.py)

- 类：`Kinematics`（L32）；`RobotAudit`（L127）。
- 模块函数：`config`（L27）；`capsule`（L110）；`manager`（L120）；`plan`（L290）；`main`（L548）。
- 类方法：`Kinematics.__init__`（L33，私有）；`Kinematics.set_gap`（L54）；`Kinematics.forward`（L62）；`Kinematics.solve`（L71）；`RobotAudit.__init__`（L128，私有）；`RobotAudit.distance`（L216）；`RobotAudit.check`（L245）。
- 函数内局部声明：`Kinematics.solve.residual`（L84）；`RobotAudit.distance.overlap_distance`（L230）。

### [topogym/solvers/kinematics/cast_coil/robot_plan.py](../../../topogym/solvers/kinematics/cast_coil/robot_plan.py)

- 类：`Kinematics`（L32）；`RobotCollision`（L83）。
- 模块函数：`build`（L168）。
- 类方法：`Kinematics.__init__`（L33，私有）；`Kinematics.pose`（L47）；`Kinematics.solve`（L56）；`RobotCollision.__init__`（L84，私有）；`RobotCollision.violations`（L123）。
- 函数内局部声明：`Kinematics.solve.residual`（L62）；`build.segment`（L232）；`build.pose_at`（L269）。

### [topogym/solvers/kinematics/cast_keyhole/robot_motion.py](../../../topogym/solvers/kinematics/cast_keyhole/robot_motion.py)

- 类：`Kinematics`（L33）；`RobotClearance`（L83）。
- 模块函数：`balanced_pose`（L63）；`bodies_from_fk`（L74）；`solve_frame`（L134）；`solve_coupled`（L144）；`main`（L160）。
- 类方法：`Kinematics.__init__`（L34，私有）；`Kinematics.pose`（L43）；`Kinematics.solve`（L50）；`RobotClearance.__init__`（L85，私有）；`RobotClearance.convex`（L103）；`RobotClearance.violations`（L107）。
- 函数内局部声明：`Kinematics.solve.residual`（L52）；`solve_coupled.residual`（L148）。

### [topogym/solvers/kinematics/hedgehog_in_cage/plan_robot.py](../../../topogym/solvers/kinematics/hedgehog_in_cage/plan_robot.py)

- 模块函数：`hand_in_ball`（L13）；`main`（L21）。
- 函数内局部声明：`main.forbidden_contacts`（L62）。

### [topogym/solvers/kinematics/horseshoe_ring/robot_motion.py](../../../topogym/solvers/kinematics/horseshoe_ring/robot_motion.py)

- 类：`Kinematics`（L26）。
- 模块函数：`balanced_frame`（L59）；`point_pose`（L76）；`build_motion`（L82）；`main`（L290）。
- 类方法：`Kinematics.__init__`（L27，私有）；`Kinematics.pose`（L36）；`Kinematics.solve`（L43）。
- 函数内局部声明：`Kinematics.solve.residual`（L47）；`build_motion.solve`（L119）；`build_motion.begin`（L125）；`build_motion.transfer`（L128）；`build_motion.append`（L139）；`build_motion.follow_shoes`（L144）。

### [topogym/solvers/kinematics/knot_untying/control.py](../../../topogym/solvers/kinematics/knot_untying/control.py)

- 类：`BoundedAlohaIK`（L15）。
- 模块函数：`configure_initial_hover`（L78）。
- 类方法：`BoundedAlohaIK.__init__`（L16，私有）；`BoundedAlohaIK.pose`（L50）；`BoundedAlohaIK.solve`（L57）。
- 函数内局部声明：`BoundedAlohaIK.solve.residual`（L60）。

### [topogym/solvers/kinematics/orbits/robot_retarget.py](../../../topogym/solvers/kinematics/orbits/robot_retarget.py)

- 模块函数：`inventory`（L27）；`audit`（L80）。

### [topogym/solvers/kinematics/orbits/workspace.py](../../../topogym/solvers/kinematics/orbits/workspace.py)

- 类：`WorkspaceAudit`（L40）。
- 模块函数：`approach_points`（L27）；`audit`（L153）；`main`（L202）。
- 类方法：`WorkspaceAudit.__init__`（L41，私有）；`WorkspaceAudit.forward`（L88）；`WorkspaceAudit.pose`（L92）；`WorkspaceAudit.solve`（L97）；`WorkspaceAudit.violations`（L108）；`WorkspaceAudit.find_pose`（L130）。
- 函数内局部声明：`WorkspaceAudit.solve.residual`（L99）。

### [topogym/solvers/kinematics/rope_threading/feedback_ik_plan.py](../../../topogym/solvers/kinematics/rope_threading/feedback_ik_plan.py)

- 模块函数：`smoothstep`（L31）；`pivot_pose`（L35）；`grasp_pose`（L42）；`carry_tip`（L64）；`snapshot_from_run`（L70）；`plan_handoff`（L88）；`screen_plan`（L187）；`build`（L245）。
- 函数内局部声明：`plan_handoff.segment`（L119）；`plan_handoff.joints`（L128）；`plan_handoff.cartesian`（L132）；`plan_handoff.pivot`（L139）；`plan_handoff.carry`（L169）。

### [topogym/solvers/kinematics/rope_threading/feedback_paths.py](../../../topogym/solvers/kinematics/rope_threading/feedback_paths.py)

- 类：`LocalPath`（L22）；`PathBuilder`（L32）；`MeasuredHandoffPlanner`（L58）。
- 类方法：`LocalPath.sample`（L28）；`PathBuilder.__init__`（L33，私有）；`PathBuilder.add`（L37）；`PathBuilder.joints`（L46）；`PathBuilder.pose`（L50）；`PathBuilder.finish`（L54）；`MeasuredHandoffPlanner.__init__`（L59，私有）；`MeasuredHandoffPlanner.gap`（L65）；`MeasuredHandoffPlanner.screen`（L74）；`MeasuredHandoffPlanner.pivot`（L94）；`MeasuredHandoffPlanner.approach`（L101）；`MeasuredHandoffPlanner.unpinch`（L144）；`MeasuredHandoffPlanner.withdraw`（L149）；`MeasuredHandoffPlanner.join_arm`（L156）；`MeasuredHandoffPlanner.return_left`（L164）；`MeasuredHandoffPlanner.carry`（L170）。

### [topogym/solvers/kinematics/rope_threading/ik_plan.py](../../../topogym/solvers/kinematics/rope_threading/ik_plan.py)

- 模块函数：`offline_controller`（L25）；`target_position`（L39）；`goal_evidence`（L47）；`write_figures`（L65）；`build`（L115）。

### [topogym/solvers/kinematics/rope_threading/reference_ik.py](../../../topogym/solvers/kinematics/rope_threading/reference_ik.py)

- 类：`MarginAwareThreadingIK`（L45）。
- 模块函数：`free_hand_clearance`（L19）；`relaxed_roll`（L34）。
- 类方法：`MarginAwareThreadingIK.__init__`（L46，私有）；`MarginAwareThreadingIK.reference_target`（L62）；`MarginAwareThreadingIK.solve_reference`（L69）。

### [topogym/solvers/validation/knot_untying/family_preflight.py](../../../topogym/solvers/validation/knot_untying/family_preflight.py)

- 模块函数：`check_initial_route`（L22）；`main`（L186）。
- 函数内局部声明：`check_initial_route.solve_pose`（L59）。

### [topogym/solvers/validation/rope_threading/reference_preflight.py](../../../topogym/solvers/validation/rope_threading/reference_preflight.py)

- 模块函数：`model_with_fixtures`（L17）；`screen`（L46）。

### [topogym/tasks/__init__.py](../../../topogym/tasks/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/tasks/blanket_flatten.py](../../../topogym/tasks/blanket_flatten.py)

- 类：`BlanketScene`（L13）；`BlanketSceneBuilder`（L45）。
- 类方法：`BlanketScene.scene`（L31）；`BlanketScene.measure`（L34）；`BlanketSceneBuilder.__init__`（L46，私有）；`BlanketSceneBuilder.build`（L49）。

### [topogym/tasks/buzz_wire_3d.py](../../../topogym/tasks/buzz_wire_3d.py)

- 类：`BuzzWireScene`（L16）；`BuzzWireSceneBuilder`（L54）。
- 类方法：`BuzzWireScene.scene`（L28）；`BuzzWireScene.manifest`（L32）；`BuzzWireScene.cameras`（L36）；`BuzzWireScene.bodies`（L40）；`BuzzWireScene.reference_pose`（L43）；`BuzzWireSceneBuilder.__init__`（L55，私有）；`BuzzWireSceneBuilder.build`（L58）。

### [topogym/tasks/cast_coil.py](../../../topogym/tasks/cast_coil.py)

- 类：`CoilScene`（L16）。
- 模块函数：`build_scene`（L37）。
- 类方法：`CoilScene.scene`（L25）；`CoilScene.cameras`（L29）；`CoilScene.manifest`（L33）。

### [topogym/tasks/cast_keyhole.py](../../../topogym/tasks/cast_keyhole.py)

- 类：`KeyholeScene`（L15）。
- 模块函数：`build_scene`（L36）。
- 类方法：`KeyholeScene.scene`（L24）；`KeyholeScene.cameras`（L28）；`KeyholeScene.manifest`（L32）。

### [topogym/tasks/fiber_bundling.py](../../../topogym/tasks/fiber_bundling.py)

- 类：`FiberScene`（L60）；`FiberSceneBuilder`（L119）。
- 模块函数：`as_numpy`（L11）；`apply_cable_colors`（L15）；`cable_state`（L32）。
- 类方法：`FiberScene.scene`（L73）；`FiberScene.cameras`（L77）；`FiberScene.manifest`（L81）；`FiberScene.grasp_target`（L84）；`FiberScene.state`（L90）；`FiberScene.step`（L113）；`FiberSceneBuilder.__init__`（L120，私有）；`FiberSceneBuilder.build`（L123）。
- 函数内局部声明：`cable_state.pose`（L37）；`FiberSceneBuilder.build.tracked_step`（L198）。

### [topogym/tasks/hedgehog_in_cage.py](../../../topogym/tasks/hedgehog_in_cage.py)

- 类：`HedgehogScene`（L17）；`HedgehogSceneBuilder`（L38）。
- 类方法：`HedgehogScene.scene`（L26）；`HedgehogScene.manifest`（L30）；`HedgehogScene.cameras`（L34）；`HedgehogSceneBuilder.__init__`（L39，私有）；`HedgehogSceneBuilder.build`（L42）。

### [topogym/tasks/horseshoe_ring.py](../../../topogym/tasks/horseshoe_ring.py)

- 类：`HorseshoeScene`（L15）。
- 模块函数：`build_scene`（L36）。
- 类方法：`HorseshoeScene.scene`（L24）；`HorseshoeScene.cameras`（L28）；`HorseshoeScene.manifest`（L32）。

### [topogym/tasks/interlocked_claws.py](../../../topogym/tasks/interlocked_claws.py)

- 类：`ClawScene`（L20）。
- 模块函数：`as_numpy`（L15）；`build_scene`（L42）。
- 类方法：`ClawScene.scene`（L30）；`ClawScene.cameras`（L34）；`ClawScene.manifest`（L38）。

### [topogym/tasks/knot_untying.py](../../../topogym/tasks/knot_untying.py)

- 类：`KnotScene`（L21）；`KnotSceneBuilder`（L43）。
- 模块函数：`scene_options`（L12）。
- 类方法：`KnotScene.scene`（L31）；`KnotScene.cameras`（L35）；`KnotScene.manifest`（L39）；`KnotSceneBuilder.__init__`（L44，私有）；`KnotSceneBuilder.build`（L47）。
- 函数内局部声明：`KnotSceneBuilder.build.build_at_neutral`（L122）。

### [topogym/tasks/lock_picking.py](../../../topogym/tasks/lock_picking.py)

- 类：`StagedLockScene`（L22）；`LockPickingSceneBuilder`（L109）。
- 模块函数：`numpy`（L17）。
- 类方法：`StagedLockScene.scene`（L38）；`StagedLockScene.manifest`（L40）；`StagedLockScene.cameras`（L42）；`StagedLockScene.state`（L44）；`StagedLockScene.actual_grip_pos`（L58）；`StagedLockScene.support_state`（L63）；`StagedLockScene.install_contact_guard`（L77）；`LockPickingSceneBuilder.__init__`（L110，私有）；`LockPickingSceneBuilder.build`（L113）。
- 函数内局部声明：`StagedLockScene.install_contact_guard.guarded_step`（L85）；`LockPickingSceneBuilder.build.box`（L176）。

### [topogym/tasks/orbits.py](../../../topogym/tasks/orbits.py)

- 类：`OrbitsScene`（L14）；`OrbitsSceneBuilder`（L38）。
- 类方法：`OrbitsScene.scene`（L23）；`OrbitsScene.cameras`（L27）；`OrbitsScene.manifest`（L31）；`OrbitsScene.step`（L34）；`OrbitsSceneBuilder.__init__`（L39，私有）；`OrbitsSceneBuilder.build`（L42）。

### [topogym/tasks/rope_threading.py](../../../topogym/tasks/rope_threading.py)

- 类：`ThreadingScene`（L12）；`ThreadingSceneBuilder`（L41）。
- 类方法：`ThreadingScene.scene`（L25）；`ThreadingScene.cameras`（L29）；`ThreadingScene.manifest`（L33）；`ThreadingScene.centerline`（L37）；`ThreadingSceneBuilder.__init__`（L42，私有）；`ThreadingSceneBuilder.build`（L45）。
- 函数内局部声明：`ThreadingSceneBuilder.build.build_at_neutral`（L154）。

### [topogym/tasks/slotted_post_ring.py](../../../topogym/tasks/slotted_post_ring.py)

- 类：`SlottedPostScene`（L14）；`SlottedPostSceneBuilder`（L38）。
- 类方法：`SlottedPostScene.scene`（L23）；`SlottedPostScene.cameras`（L27）；`SlottedPostScene.manifest`（L31）；`SlottedPostScene.step`（L34）；`SlottedPostSceneBuilder.__init__`（L39，私有）；`SlottedPostSceneBuilder.build`（L42）。

### [topogym/utils/__init__.py](../../../topogym/utils/__init__.py)

- 无 Python class/def 声明；为包标记、导入转发、HTML 或来源清单。

### [topogym/utils/geometry/rigid_geometry.py](../../../topogym/utils/geometry/rigid_geometry.py)

- 类：`RingGeometry`（L14）。
- 模块函数：`vector_text`（L36）；`primitive`（L40）；`cylinder_between`（L51）；`write_ring`（L61）；`world_ring`（L100）；`disk_linking_number`（L106）。
- 类方法：`RingGeometry.__post_init__`（L20，私有）；`RingGeometry.mass_kg`（L28）；`RingGeometry.points`（L31）。

### [topogym/utils/geometry/rope_crossings.py](../../../topogym/utils/geometry/rope_crossings.py)

- 类：`RopeCrossing`（L35）。
- 模块函数：`arclength`（L57）；`segment_hits`（L64）；`_merge`（L88，私有）；`find_crossings`（L104）；`crossing_code`（L147）；`flip_code`（L163）；`pair_tops`（L169）；`relation_flipped`（L178）；`failure_label`（L202）；`code_text`（L222）。
- 类方法：`RopeCrossing.over_strand`（L49）；`RopeCrossing.under_strand`（L53）。

### [topogym/utils/io.py](../../../topogym/utils/io.py)

- 模块函数：`code_provenance`（L11）；`sha256`（L30）；`canonical_hash`（L38）；`write_json`（L43）；`read_json`（L59）；`relative_file`（L63）。

### [topogym/utils/variant_rng.py](../../../topogym/utils/variant_rng.py)

- 类：`VariantRng`（L55）。
- 模块函数：`_spawn_key`（L50，私有）。
- 类方法：`VariantRng.__init__`（L60，私有）；`VariantRng.seed`（L64）；`VariantRng.stream`（L67）；`VariantRng.tier`（L83）；`VariantRng.__repr__`（L89，私有）。

### [topogym/world/__init__.py](../../../topogym/world/__init__.py)

- 模块函数：`__getattr__`（L6，私有）。

### [topogym/world/closed_band.py](../../../topogym/world/closed_band.py)

- 类：`Crossing`（L49）；`BandFrames`（L65）。
- 模块函数：`_unit`（L78，私有）；`_rotate_about`（L86，私有）；`closed_arc_length`（L95）；`closed_transport_frames`（L103）；`closed_tube_mesh`（L191）；`pegged_band_centerline`（L230）；`band_reach`（L341）；`_segment_hit`（L354，私有）；`_project`（L370，私有）；`_crossings`（L374，私有）；`_merge_nearby`（L429，私有）；`band_self_crossings`（L451）；`crossings_between`（L475）；`linking_number`（L494）。
- 函数内局部声明：`closed_transport_frames._transport`（L138，私有）；`closed_transport_frames._framing`（L161，私有）；`pegged_band_centerline._shape`（L282，私有）；`pegged_band_centerline._shape._line`（L285，私有）；`pegged_band_centerline._shape._cap`（L290，私有）。

### [topogym/world/genesis_ipc_vertex_constraints.py](../../../topogym/world/genesis_ipc_vertex_constraints.py)

- 类：`_EntitySpec`（L50，私有）；`FollowHandle`（L72）。
- 模块函数：`pin_near`（L106）；`follow_near`（L114）；`rest_shape_straight`（L130）；`resolved_pins`（L144）；`_inverted_tets`（L151，私有）；`_straighten_positions`（L171，私有）；`reset`（L185）；`_select`（L191，私有）；`_resolve_spec`（L204，私有）；`_animate_fem_follow`（L225，私有）；`install`（L254）。
- 类方法：`FollowHandle._spec`（L79，私有）；`FollowHandle.verts`（L83）；`FollowHandle.engage`（L92）；`FollowHandle.update_targets`（L96）；`FollowHandle.release`（L102）。
- 函数内局部声明：`_inverted_tets.signed`（L162，私有）；`install._substep_aware_build_cfg`（L275，私有）；`install.VertexConstraintIPCCoupler`（L295）；`install.VertexConstraintIPCCoupler._add_fem_entities_to_ipc`（L299，私有）。

### [topogym/world/genesis_memory.py](../../../topogym/world/genesis_memory.py)

- 模块函数：`_copy_support_chunk`（L19，私有）；`upload_support_chunks`（L34）；`bounded_support_upload`（L48）。
- 函数内局部声明：`bounded_support_upload.upload`（L58）。

### [topogym/world/lab_layout.py](../../../topogym/world/lab_layout.py)

- 模块函数：`lab_layout`（L9）；`compact_lab_layout`（L51）。
- 函数内局部声明：`lab_layout.box`（L18）；`compact_lab_layout.box`（L60）。

### [topogym/world/manifest.py](../../../topogym/world/manifest.py)

- 类：`EntityManifest`（L8）。
- 类方法：`EntityManifest.add`（L13）；`EntityManifest.get`（L19）；`EntityManifest.as_dict`（L26）。

### [topogym/world/nyx_lab.py](../../../topogym/world/nyx_lab.py)

- 模块函数：`add_lab`（L5）；`add_compact_lab`（L19）。

### [topogym/world/physics/buzz_wire_3d/physics.py](../../../topogym/world/physics/buzz_wire_3d/physics.py)

- 类：`PhysicsSettings`（L39）。
- 模块函数：`array`（L28）；`save`（L34）；`load_config`（L57）；`setup`（L73）；`phase_plan`（L89）；`reference`（L110）；`wrench_command`（L130）；`run`（L166）；`main`（L413）。
- 函数内局部声明：`run.measured`（L204）。

### [topogym/world/physics/fiber_bundling/contact_precision.py](../../../topogym/world/physics/fiber_bundling/contact_precision.py)

- 模块函数：`install_capsule_contact_fix`（L12）。
- 函数内局部声明：`install_capsule_contact_fix.closest_points`（L21）。

### [topogym/world/physics/fiber_bundling/numerics.py](../../../topogym/world/physics/fiber_bundling/numerics.py)

- 模块函数：`constraint_solver_name`（L4）；`require_solver_evidence`（L11）。

### [topogym/world/physics/knot_untying/ipc_compat.py](../../../topogym/world/physics/knot_untying/ipc_compat.py)

- 模块函数：`matching_revolute_axes`（L13）。
- 函数内局部声明：`matching_revolute_axes.ForwardAxisRevoluteJoint`（L20）；`matching_revolute_axes.ForwardAxisRevoluteJoint.apply_to`（L21）。

### [topogym/world/physics/knot_untying/runtime_memory.py](../../../topogym/world/physics/knot_untying/runtime_memory.py)

- 类：`ForwardOnlyMemory`（L11）。
- 类方法：`ForwardOnlyMemory.__init__`（L12，私有）；`ForwardOnlyMemory._query_count`（L28，私有）；`ForwardOnlyMemory.save_checkpoint`（L31）；`ForwardOnlyMemory.query_state`（L38）；`ForwardOnlyMemory.report`（L46）。

### [topogym/world/physics/rope_threading/deformation_damping.py](../../../topogym/world/physics/rope_threading/deformation_damping.py)

- 类：`DeformationDamping`（L38）。
- 模块函数：`dissipative_forces`（L13）。
- 类方法：`DeformationDamping.__init__`（L39，私有）；`DeformationDamping.specification`（L56）；`DeformationDamping._add_force_constitution`（L65，私有）；`DeformationDamping._animate_force_and_grasps`（L93，私有）；`DeformationDamping.start`（L114）；`DeformationDamping.report`（L141）。
- 函数内局部声明：`DeformationDamping.start.step`（L125）。

### [topogym/world/physics/rope_threading/mesh_resolution.py](../../../topogym/world/physics/rope_threading/mesh_resolution.py)

- 模块函数：`refinement_settings`（L4）。

### [topogym/world/physics/rope_threading/runtime_memory.py](../../../topogym/world/physics/rope_threading/runtime_memory.py)

- 类：`ForwardOnlyMemory`（L5）。
- 类方法：`ForwardOnlyMemory.__init__`（L14，私有）；`ForwardOnlyMemory._retained_queries`（L32，私有）；`ForwardOnlyMemory.save_checkpoint`（L35）；`ForwardOnlyMemory.query_state`（L42）；`ForwardOnlyMemory.report`（L48）。

### [topogym/world/physics/rope_threading/table_contact.py](../../../topogym/world/physics/rope_threading/table_contact.py)

- 类：`AnalyticTableContact`（L11）。
- 类方法：`AnalyticTableContact.__init__`（L12，私有）；`AnalyticTableContact._register`（L24，私有）；`AnalyticTableContact.finish_build`（L63）；`AnalyticTableContact.observe`（L66）；`AnalyticTableContact.specification`（L75）；`AnalyticTableContact.report`（L83）。

### [topogym/world/rope.py](../../../topogym/world/rope.py)

- 类：`RopeMesh`（L26）；`RopeEndpointHandle`（L35）；`TabletopParticleFriction`（L442）。
- 模块函数：`_repo_root`（L46，私有）；`resolve_mesh_dir`（L50）；`safe_asset_name`（L57）；`tensor_to_numpy`（L61）；`sample_polyline`（L71）；`catmull_rom_centerline`（L93）；`reserve_endpoint_footprint`（L141）；`parallel_transport_frames`（L181）；`tube_material_coords`（L246）；`make_elastic_tube_mesh`（L315）；`self_contact_clearance`（L365）；`check_self_contact_clearance`（L387）；`write_obj`（L418）；`endpoint_particle_indices`（L428）；`pbd_options`（L592）；`elastic_material`（L603）；`tube_morph`（L620）；`unit_xy`（L636）；`revolve_profile`（L644）；`connector_grasp_height`（L695）；`connector_cap_top`（L702）；`connector_mesh`（L710）；`connector_obj_path`（L761）；`connector_anchor_indices`（L784）；`with_end_entries`（L819）；`connector_entry_heights`（L896）；`with_connector_entries`（L907）；`fixed_terminal_mesh`（L925）；`fixed_terminal_heights`（L952）；`fixed_terminal_obj_path`（L963）；`routing_post_base_mesh`（L971）；`routing_post_base_obj_path`（L993）。
- 类方法：`TabletopParticleFriction.__init__`（L491，私有）；`TabletopParticleFriction.apply`（L515）；`TabletopParticleFriction.install`（L571）；`TabletopParticleFriction.uninstall`（L586）。
- 函数内局部声明：`catmull_rom_centerline._tj`（L120，私有）；`parallel_transport_frames._unit`（L195，私有）；`TabletopParticleFriction.install.wrapped_step`（L578）。

### [topogym/world/rope_backends/__init__.py](../../../topogym/world/rope_backends/__init__.py)

- 模块函数：`rope_backend`（L43）。

### [topogym/world/rope_backends/fem_ipc.py](../../../topogym/world/rope_backends/fem_ipc.py)

- 类：`_FollowSync`（L74，私有）；`FemIpcRopeBackend`（L170）。
- 模块函数：`_fem_value`（L31，私有）；`_quat_to_mat`（L60，私有）。
- 类方法：`_FollowSync.__init__`（L77，私有）；`_FollowSync.add`（L88，私有）；`_FollowSync.sync`（L102，私有）；`_FollowSync.turned_turns`（L113，私有）；`_FollowSync._spun`（L123，私有）；`FemIpcRopeBackend.__init__`（L173，私有）；`FemIpcRopeBackend.pre_scene`（L185）；`FemIpcRopeBackend.scene_options`（L203）；`FemIpcRopeBackend.material`（L238）；`FemIpcRopeBackend.static_rigid_material`（L249）；`FemIpcRopeBackend.decoration_rigid_material`（L261）；`FemIpcRopeBackend.declare_anchor`（L275）；`FemIpcRopeBackend.declare_rest_straight`（L278）；`FemIpcRopeBackend.declare_follow`（L288）；`FemIpcRopeBackend.resolve_indices`（L304）；`FemIpcRopeBackend.anchor`（L315）；`FemIpcRopeBackend.follow_link`（L326）；`FemIpcRopeBackend.nodes`（L350）；`FemIpcRopeBackend.swivel_turns`（L354）；`FemIpcRopeBackend.node_velocities`（L359）；`FemIpcRopeBackend.zero_node_velocities`（L363）。
- 函数内局部声明：`_FollowSync.add.step_with_follow_sync`（L96，私有）。

### [topogym/world/rope_backends/pbd.py](../../../topogym/world/rope_backends/pbd.py)

- 类：`PBDRopeBackend`（L22）。
- 类方法：`PBDRopeBackend.__init__`（L25，私有）；`PBDRopeBackend.pre_scene`（L33）；`PBDRopeBackend.scene_options`（L36）；`PBDRopeBackend.material`（L39）；`PBDRopeBackend.static_rigid_material`（L42）；`PBDRopeBackend.decoration_rigid_material`（L47）；`PBDRopeBackend.declare_rest_straight`（L54）；`PBDRopeBackend.declare_anchor`（L59）；`PBDRopeBackend.declare_follow`（L64）；`PBDRopeBackend.resolve_indices`（L74）；`PBDRopeBackend.anchor`（L79）；`PBDRopeBackend.follow_link`（L96）；`PBDRopeBackend.nodes`（L114）；`PBDRopeBackend.node_velocities`（L118）；`PBDRopeBackend.zero_node_velocities`（L122）。

### [topogym/world/scenes/buzz_wire_3d/agent_scene.py](../../../topogym/world/scenes/buzz_wire_3d/agent_scene.py)

- 类：`StaticWire`（L27）。
- 模块函数：`load_seed`（L15）；`prepare_scene`（L35）。

### [topogym/world/signatures.py](../../../topogym/world/signatures.py)

- 模块函数：`array_hash`（L9）；`mujoco_signature`（L17）；`genesis_signature`（L32）。

### [topogym/world/tabletop.py](../../../topogym/world/tabletop.py)

- 类：`TabletopFrames`（L52）；`RobotFootprintCheck`（L66）；`TabletopBaseScene`（L76）；`StandardTabletopSceneBuilder`（L115）。
- 模块函数：`_vec3`（L24，私有）；`_vec2`（L31，私有）；`_matrix4`（L38，私有）；`_plain_config`（L45，私有）；`tabletop_frames_from_config`（L89）。
- 类方法：`TabletopFrames.task_to_world`（L58）；`TabletopFrames.task_z_to_world`（L61）；`TabletopBaseScene.recording_binding`（L84）；`StandardTabletopSceneBuilder.__init__`（L118，私有）；`StandardTabletopSceneBuilder._debug`（L139，私有）；`StandardTabletopSceneBuilder.create`（L143）；`StandardTabletopSceneBuilder._add_table_frame`（L334，私有）；`StandardTabletopSceneBuilder.finalize`（L417）；`StandardTabletopSceneBuilder._attach_camera`（L428，私有）；`StandardTabletopSceneBuilder._frames`（L464，私有）；`StandardTabletopSceneBuilder._select_renderer`（L467，私有）；`StandardTabletopSceneBuilder._validate_locked_preset`（L514，私有）；`StandardTabletopSceneBuilder._require_close`（L621，私有）；`StandardTabletopSceneBuilder._validate_geometry`（L635，私有）。
- 函数内局部声明：`StandardTabletopSceneBuilder._add_table_frame._cfg`（L347，私有）。
