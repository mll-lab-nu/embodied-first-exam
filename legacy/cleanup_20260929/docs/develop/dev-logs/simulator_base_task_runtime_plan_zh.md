# 两项共享功能恢复与 13 个基础 Task 的统一运行计划

日期：2026-09-23。

> 本页保留实施前计划和当时状态；后续实现与测试结果见[基础环境运行实测记录](simulator_base_runtime_implementation_zh.md)。

**计划编写时的状态：已恢复纹理和 FEM 两个脚本、接回 Blanket 纹理声明、补写对应测试检查。当时下文其余 FEM/IPC、任务运行与测试扩展尚未实施，全部测试未运行；后续实施和实测结果以上方链接为准。**

## 1. 本轮实际恢复了什么

### 1.1 `assets/textures.py` 与 Blanket 调用

- [assets/textures.py](../../../topogym/assets/textures.py)：从删除前备份恢复 `fabric_weave` 及其辅助函数；织纹、格纹/条纹、角点颜色和 seed 算法保留，更新了过时的模块说明。
- [tasks/blanket_flatten.py](../../../topogym/tasks/blanket_flatten.py)：默认使用格纹，尺寸来自当前布料布局，颜色来自任务参数，seed 与实例一致；生成 `blanket_diffuse.png`。
- Task 的 `EntitySpec.surface` 声明 `diffuse_texture_path`，不构造 Genesis 对象。网格仍携带原有 UV。
- [world/visuals/surfaces.py](../../../topogym/world/visuals/surfaces.py) 的 `from_spec()`：解析纹理路径并创建实际 Genesis 表面；拒绝同时声明纹理路径与纯色/另一 diffuse texture。
- [GenesisWorld.add_entities()](../../../topogym/world/genesis_world.py) 统一调用这个表面入口。其他任务没有声明纹理路径时，仍按原有参数创建 Default surface。
- 纹理 PNG 由现有 `describe_build()` 自动纳入资产文件清单及哈希；它属于本 episode 的生成资产，不依赖旧 runs。显式 `texture=None` 可选择纯色。

```text
Blanket 参数、seed、布局尺寸
    → assets/textures.fabric_weave
    → blanket_diffuse.png + 带 UV 的 blanket.obj
    → EntitySpec.surface 声明
    → World / visuals.from_spec
    → Genesis 表面 → Sensors 图像
```

这完成的是调用接线，不是渲染验收；未据此声明图像效果已通过检查。

### 1.2 `world/physics/fem.py`

[world/physics/fem.py](../../../topogym/world/physics/fem.py) 的 19 行原实现按删除前内容恢复：

- `material(parameters)`：校验 FEM 材料参数并构造 Genesis FEM Elastic。
- `read_vertices(entity)`：读取顶点位置/速度并复制到 NumPy。

它仍是待接入的共享实现起点；**没有因为恢复这个文件就解除四项任务的 reset 阻塞**。参考构形、体网格材料坐标、刚柔连接、IPC 全状态恢复仍需按下文完成。其他 24 个被删文件本轮没有恢复，variation 脚本也未改动。

### 1.3 本轮写入的测试变化

- `tests/unit/test_task_definitions.py`：在原有 Task 声明检查中增加纹理文件存在、非纯色 RGB、网格 UV、纹理哈希记录和避免 color/texture 冲突的检查；要求默认 Blanket 确实声明纹理。
- `tests/integration/test_task_lifecycle.py`：原来只对 Coil 检查 render/回溯，现在另加入 Blanket；检查引擎解析到 ImageTexture、纹理纳入 episode 资产记录，再检查共享帧与回溯身份。

没有新增测试脚本，仍为 **19 个测试脚本和 1 个公共夹具**；这些新增检查也没有运行。

## 2. 下一阶段目标：13 项基础环境可运行

目标限定为每个 Task 的 **`variation_id="base"`**，使用默认的机器人和同一个 compact_lab。统一完成：

1. 通过 `SimulatorConfig(task_id=...)` 与同一个 `Env` 创建。
2. `reset(seed=...)` 建出真实初态、返回合法 observation/info，并保存 state 0。
3. 通过公共 Robot 动作合同提交保持或小幅有效动作，`Env.step()` 推进真实物理并返回一致的结果结构。
4. `observe()` / `render()` 不额外推进物理，读取的实体状态来自当前引擎。
5. `reset(state_id=...)` 能回到当前 episode 任意已保存 tick，包括控制动作中间 tick；分支保留，恢复后能继续积分。
6. `close()` 释放场景、相机、IPC 原生资源及临时快照；随后可创建另一个 Task。

本里程碑不要求 planner 就绪、不要求成功 demo，也不要求证明每个实例可解。目标判据未完成的 Task 可以返回 `goal_evaluation_complete=False`、零成功奖励和可用的诊断信息；数值异常、无效状态与时间上限仍必须有明确处理。

**环境一致性**指生命周期、物理时钟、配置来源、坐标/单位、状态身份和 observation/result 合同一致；不是要求 ALOHA 与 Panda＋Robotiq 有相同动作维度，也不是要求刚体、PBD、FEM 有相同数量的状态点。核心实体的连接和接触应真实存在，不能把软绳换成固定装饰、禁用耦合或播放轨迹来满足“能 step”。

## 3. 当前 13 项的接入状态

“已有路径”仅表示源码中有构造与生命周期路径，**尚未运行验证**。

| 基础 Task | 默认机器人 | 当前物理声明 | 下一阶段重点 |
|---|---|---|---|
| Cast Coil | ALOHA | 刚体 | 验证共享 reset/step/状态回溯与初态接触 |
| Cast Keyhole | ALOHA | 刚体 | 同上；核对模型分块、坐标及间隙 |
| Horseshoe Ring | ALOHA | 刚体 | 同上；保留真实链环关系，不用参考摆位替代动力学 |
| Hedgehog in Cage | Panda＋Robotiq | 刚体 | 验证正确机器人、初态净空与共享动作合同 |
| Interlocked Claws | ALOHA | 刚体 | 验证两实体的真实互锁/接触及状态恢复 |
| Buzz Wire 3D | Panda＋Robotiq | 刚体 | 基础路径已有；判据未完成不阻止运行，不允许假成功 |
| Lock Picking | Panda＋Robotiq | 刚体（含三个独立被动旋转锁盘） | 基础路径已有；核对转子关节/必要限位，判据与参考路线后置 |
| Fiber Bundling | Panda＋Robotiq | 被动关节链 | 核对纤维连接、环/接触与机器人选择；完成策略后置 |
| Blanket Flatten | ALOHA | PBD Cloth | 验证布料变形、纹理观察与中途回溯续跑；复杂初态/抓取策略后置 |
| Rope Threading | ALOHA | FEM＋IPC | 解开公共运行阻塞；直绳参考形、材料坐标和环接触 |
| Knot Untying | ALOHA | FEM＋IPC | 解开公共运行阻塞；结型初态与参考直绳分离、自接触 |
| Orbits | ALOHA | FEM＋IPC | 公共支持之外，必须接通绳端与活动把手连接 |
| Slotted Post Ring | ALOHA | FEM＋IPC | 公共支持之外，必须接通绳端/盘、止挡与珠绳接触 |

当前统计为 8 项刚体/关节链、1 项 PBD、4 项受阻 FEM/IPC。**不能把“13 个类都注册了”写成“13 个环境都能运行”。**

## 4. 建议实施顺序与具体脚本

### 第一步：固定共同合同，先审查 IPC 回溯是否有完整实现途径

涉及 `config/registry.py`、`config/simulator.py`、`env.py`、`episode.py`、`world/state.py`、`world/physics/ipc.py`。

- 以固定的 13 个基础 Task 名单作为覆盖目标。分别记录构造/step、rewind、RGB、assist、solve 与验证状态，未完成 solve 不能顺带挡住已实现的生命周期。
- 保持 `reset(state_id)` 要求。普通“回到第 0 帧”是其中一个用例，不能取代任意保存状态恢复。
- 审查当前原生 IPC checkpoint 的可保存内容、文件格式、frame 定位和可恢复状态；逐项列出 Genesis Python 包装器状态、原生状态、控制/约束目标与缓存的拥有者。
- 明确当前实现支持的设备/版本，在申请场景和写出资产前报告不满足的条件。设备可有差异，物理引擎始终是 Genesis。

本轮只读本地安装的 Genesis 源码，得到两个具体约束：

1. `engine/couplers/ipc_coupler/coupler.py` 使用 `Engine("cuda", workspace)`；现阶段不能设计一个默认 CPU 的全 13 项测试就宣称覆盖了 FEM/IPC。
2. `_finalize_ipc()` 调用 `dump()` 保存初态，`reset()` 调用 `recover(0)` 和 `retrieve()`。这证明当前包装器提供了初态恢复路径，**不能据此推定任意历史分支恢复已可用，也不能据此断言原生库绝对不支持其他帧**。

优先确定原生状态的完整保存/恢复路径，再展开四份 Task 的接线。如果上游绑定缺少必要能力，应补明确、可维护的绑定或适配，并列出缺失项；不能通过放宽 `_check_checkpoint_support()` 或只回写顶点来绕过。

### 第二步：打通公共 FEM/IPC 构造与观测

涉及 `world/genesis_world.py`、`world/tabletop.py`、`world/physics/fem.py`、`world/physics/ipc.py`、`assets/materials.py`、`tasks/base.py`。

1. 将 `TaskSpec.physics_options` 中的 `fem`、`ipc` 转换为 Genesis 参数。当前 `StandardTabletopSceneBuilder` 已有通用 `scene_options` 通道，可用于传递，避免创建 FEM 专用 SceneBuilder。
2. FEM 实体分支真正调用 `physics/fem.material()`；所有实体仍由 World 加入同一个 Scene，所有积分仍由 `World.advance()` 执行。
3. 迁移直绳参考构形、体网格/材料坐标与实体索引映射。初态弯曲形状和无应力参考形必须分开，不能把结型网格直接当成天然无应力的结。
4. 让 `World.read_state()` 显式读取 FEM 数据；当前只区分 PBD 粒子和刚体的分支不能遗漏 FEM 顶点、速度和活动状态。
5. 保持 observation 外层 `world / robot / task / rgb`；为 FEM 规定有类型、单位和材料索引的顶点记录。建议在现有 PBD `world.particles` 之外增加明确的 `world.fem`，避免将 FEM 顶点冒充 PBD 粒子；没有 FEM 的任务返回空映射即可。
6. 统一几何/接触/机器人坐标与受力回传，核对机器人是否真实参与刚柔耦合；观察数据不能来自未同步的原生缓存。
7. FEM `get_state()` 的查询对象会进入引擎查询列表；接入连续 observation 时应处理其生命周期，防止每次只读观测累积内部对象。恢复的两函数文件尚未解决此问题。

### 第三步：接通基础任务不可缺的物理连接

涉及 `tasks/base.py` 的声明、各 FEM Task、`world/physics/constraints.py` 的后续实现和 Robot 抓持请求合同。

- 给实体间连接明确名称、端点/材料区间、参考参数及恢复身份；声明由 Task 提供，运行时实现由 World 持有。
- Orbits 的绳端到把手、Slotted 的绳端到盘与末端止挡属于模型组成，不能以“planner 尚未就绪”为由省去。
- Rope/Knot 的自由绳、环/自接触与正确参考材料必须能随物理演化；基础运行不依赖已有完整穿环/解结策略。
- 机器人主动抓取/释放接口与模型永久连接区分处理。若基础运行用例没有使用 assist，可以单独报告未支持；若启用了 assist，则创建、释放和回溯必须一并支持。
- Blanket 继续走共享 PBD 路径。物理预备得到的复杂初态以后仍由 World 执行，不恢复任务私有 `scene.step` 循环。

这一阶段会按明确职责引入约束支持；不是本轮已恢复第三个旧脚本。

### 第四步：接入完整快照、分支回溯和资源释放

涉及 `world/state.py`、`world/physics/ipc.py`、`world/physics/fem.py`、约束管理、`episode.py`、`env.py`、`sensors/observation.py`。

- 保存并恢复 FEM 原生求解状态、IPC 状态、刚柔同步数据、活动标记、约束目标、机器人控制目标、Task 判据历史、RNG 和所有相关时钟。
- 给 checkpoint 独立身份；物理 tick 相同但分支不同，原生存储不能覆盖。回溯生成新分支后，旧分支的未来状态仍可选。
- 显式记录 Env state_id、World tick、Genesis 子步与 IPC 原生 frame 的映射，不假设这些计数天然相等。
- 不把原生对象句柄当成不可变快照；现有 Torch/NumPy 缓冲扫描无法自动保证 C++ 原生状态也被覆盖。
- 恢复顺序要明确：原生求解器/耦合状态、包装层缓存及控制状态、Task 历史、Sensors 缓存失效。恢复过程不推进一个“补偿物理步”。
- 不用从头重放动作来冒充已保存状态恢复，也不在内存紧张时静默丢弃已有 state。可明确管理磁盘快照及资源预算，但历史保留语义必须不变。
- `close()` 和失败清理释放原生资源、文件与查询对象；随后在同设备/精度的进程里切换另一个 Task，旧实体/相机/状态不可泄漏。

应先用小型 FEM/IPC 场景和确定约束完成续跑对照，再将同一机制用于四项完整场景。没有原生 checkpoint 能力时保留具体错误，不把 reset 写成表面成功。

### 第五步：让全部基础 Task 走同一条路径并分离能力状态

涉及 13 个 Task、`config/registry.py`、统一测试和文档清单。

- 对每个 base 核对实体、材料、关节、初态和必要连接；修复共性问题时优先修改共享模块。
- 判据未完成时保留 `goal_complete=False`。基础任务运行用例不要求 reward=1，但不能允许非有限状态、错误坐标或缺实体悄悄继续。
- 不要求同一机器人适配全部任务；默认机器人与任务匹配。动作由公共 `action_spec` 和机器人关节组描述产生，不在测试中为每项任务写一套控制协议。
- 当某项运行阻塞对应的完整实现已接通时，逐项移除该阻塞，并调整对应测试。实现状态与实际测试结果仍分开；没有获准运行前只能标“实现待验证”，不能声称可运行已验收。
- 最后刷新全部脚本清单和支持矩阵；planner、变体家族扩展、数据录制与 agent 不作为这一步验收条件。

## 5. 现有测试能覆盖什么，还缺什么

**现有测试有相关检查，但没有任何本轮运行结果。** 此外，默认 pytest 配置排除了 `genesis` 和 `hdf5`；即便以后默认集合全部通过，也不能据此宣称真实 simulator 或全部 Task 可用。

### 5.1 已有脚本：公共合同与环境一致性

| 现有脚本（相对 `tests/`） | 当前检查 | 对本目标的限制/拟改动 |
|---|---|---|
| `architecture/test_module_boundaries.py` | 单一引擎、唯一物理推进、Task 不拥有引擎/录制、目录边界 | 保留；增加 FEM/约束也必须从公共 World 接入的约束，静态检查不代替物理 |
| `unit/test_configuration.py` | 配置校验、13 项登记、两项单臂默认值、两机器人共用 compact_lab | 扩展到全部默认机器人、全部 Task 的共同 dt/重力/桌面/背景来源和设备能力错误 |
| `unit/test_task_definitions.py` | 13 项生成实体、资产存在、姿态合法；本轮增加纹理/UV/哈希 | 仅离线声明；增加约束引用有效、FEM 材料坐标与实体映射检查 |
| `unit/test_task_support.py` | 13 项定义/判据状态；四 FEM **必须在 reset 前拒绝**；未完成判据不可假成功 | 当前是在验证拒绝，不是验证 FEM 可用。接通后改为操作能力检查，并保留对确实缺失的设备/codec 的拒绝用例 |
| `unit/test_material_specs.py` | 材料参数合法，明确 FEM 声明不等于运行支持 | 后续扩展 FEM/IPC 配置转换，不用材料构造成功代替积分验证 |
| `unit/test_robot_descriptions.py` | 两机器人关节组、单位、原子动作校验和控制状态 | 保留；与真实各 Task 的 action_spec 对照 |
| `unit/test_task_state.py` | 稳定计时、重复查询不累加、任务 RNG/结果恢复、失败优先 | 使用测试 Task；补实际 Task 的有状态判据后再逐项验证 |
| `unit/test_task_variations.py` | 13 项 base 参数解析、具名覆盖与错误名称 | 保留 base 覆盖；本里程碑不展开所有变体 |
| `unit/test_asset_library.py` | 资源哈希、越界与生成清单 | 保留；FEM 参考资产和生成材料映射也需纳入记录 |
| `unit/test_collision_certificates.py` | 刚体盒/凸体运动间隙证书 | 不能证明 FEM 自接触/穿透或 task 可运行；本阶段保持范围明确 |
| `contracts/test_env_lifecycle.py` | 公共 Env 的步数、非法动作、截断、故障和关闭 | 假 World 验证编排；真实各 Task 还需下面的统一用例 |
| `contracts/test_episode_rewind.py` | 所有 tick、旧分支未来、非法恢复、终态、时间上限 | 假 World；不覆盖 native IPC 数据，需要真实 FEM 续跑测试 |

### 5.2 已有真实引擎脚本

| 现有脚本 | 当前实际用例范围 | 拟补齐 |
|---|---|---|
| [test_task_lifecycle.py](../../../tests/integration/test_task_lifecycle.py) | 8 项刚体各 reset/保持动作/回 state 0；Blanket 三次动作后回 state 0；Coil 和本轮新增 Blanket 的 RGB 检查 | 扩展为固定 13 项 base 的共同生命周期、非初态回溯、真实状态恢复及任务切换 |
| [test_genesis_world_history.py](../../../tests/integration/test_genesis_world_history.py) | 刚体方块重力/接触/多中间点续跑、RNG、缓冲；IPC 情况目前要求拒绝 | 保留刚体测试；增加完整 FEM/IPC 测试，不能仅把“拒绝”断言反过来 |
| [test_genesis_robot.py](../../../tests/integration/test_genesis_robot.py) | 两机器人真实关节/夹爪目标、恢复续跑、FK/IK 只读 | 与 FEM/IPC 耦合后的运动及力反馈另需检查；基础用例不要求抓住物体 |
| [test_genesis_seed_reset.py](../../../tests/integration/test_genesis_seed_reset.py) | Coil 分别使用两机器人做 seed A/B/A 和 state 0 回溯 | 扩展到全部 Task 的默认机器人、FEM 顶点/速度/连接初态及 PBD 初态 |

另有 `recording_data/test_snapshot_isolation.py`、`test_dataset_transitions.py`、`test_recording_branches.py`，检查不可变快照、动作/观测转移和录制分支。这些可继续保留，但录制/HDF5 通过不是本里程碑前提，也不覆盖四项 FEM 的真实可运行性。

## 6. 下一步测试改动计划

以下只列设计，除第 1.3 节纹理检查之外尚未编写。

### A. 扩展 `integration/test_task_lifecycle.py`：共同生命周期与切换

- 用固定 13 项名单与 Registry 做集合对账，防止少登记/少参数化一项仍得到“全通过”。
- 每项都检查 reset、保持与小幅合法动作、observation/result 类型、正确任务实体与默认机器人、实际 tick/dt、非法动作不产生部分写入、close。
- 检查同一个 compact_lab、桌面、重力与共享配置；任务新增对象和相机视角差异允许按能力声明体现。
- 对模型适合的刺激验证真实动态响应，不能只检查 Python tick 变大。例如 PBD/FEM 的点状态有限且会对重力或已声明约束输入响应，关节命令有真实关节响应。
- 增加不同 Task 顺序构造/关闭及 A→B→A，核对实体、相机、缓存、RNG 与旧状态隔离。当前单进程仍只允许一个活动 Env，不借此宣称多环境并行。

### B. 新增 `integration/test_genesis_fem_ipc.py`：共享机制的真实最小场景

- FEM 创建/真实变形、参考材料一致、刚柔与自接触基础检查。
- 固定/动态连接的约束残差，运动刚体端点向绳传递运动及需要时的反向受力。
- 保存初态、非零速度、接触和约束状态，乱序恢复；改变动作产生另一分支后还能回到旧未来。
- 相同状态施加相同后续动作，对比位置、速度、活动标记、约束和后续轨迹；只比较恢复瞬间的外形不够。
- 观察/快照不额外积分，原生文件不被同 tick 的不同分支覆盖；close/失败路径释放资源。
- 使用明确的 CUDA/native IPC 条件；缺硬件或依赖时报告未执行/环境不满足，不算通过、不退化为刚体或另一后端。
- 同步在 `pyproject.toml` 登记 FEM/IPC 测试 marker 和设备选择规则；新增脚本仍受“先编写、等待指示再运行”约束。

### C. 扩展历史和 seed 测试：每项 Task 的真实恢复

- `test_task_lifecycle.py` 增加 state 0、非初态、控制动作中间 tick 的恢复与续跑对照。
- `test_genesis_seed_reset.py` 覆盖 13 个 base 的 seed A/B/A，按模型核对刚体/关节/PBD/FEM 数据；相同 seed 仍要保证独立 episode。
- 选择固定设备、精度与明确容差；不同设备分别出结果，不承诺 CPU/CUDA 逐位相同。
- 四项 FEM 的任何硬连接/约束如果缺快照，测试应暴露缺口，不能默认不启用该连接来缩小测试对象。

### D. 扩展观察检查：统一结构与可选 RGB

- 验证 `world / robot / task / rgb` 外层结构、SI 单位和状态身份；数据尺寸根据实体/机器人声明检查。
- FEM 观测带明确的顶点/材料索引，不以零数组填补未接入状态；旧观测不能随引擎缓冲复用而变化。
- 重复 observe/render 不推进物理；回溯到同 tick 的不同 state/branch 要使图像缓存失效。
- 无 RGB 的核心测试覆盖所有 13 项；获准渲染后，再对每项 base 验证至少一套默认相机、标定和帧身份。两种 renderer 可分别报告，不要求一轮同时完成全部视觉质量实验。

## 7. 完成条件与执行边界

| 层次 | 完成条件 | 当前情况 |
|---|---|---|
| 本轮恢复 | 两脚本在功能目录，Blanket 纹理通过公共表面声明接线 | 已写入，静态核对；未运行验证 |
| 全部 base 实现 | 13 项通过同一 Env，FEM/IPC/必要连接与完整回溯实现接通 | 尚未完成，按第 4 节实施 |
| Simulator 可用性验收 | 获准后执行共同生命周期、真实物理、任意状态续跑、跨任务一致性测试 | 未执行，不能报告通过 |
| 任务可解/策略/demo | 正确成功判据与策略完成对应任务 | 后续目标，不阻塞本阶段基础环境实现 |

默认运行命令不会覆盖所有真实引擎用例。将来获准执行时，需要显式选择设备和物理/RGB测试，并逐项记录“通过/失败/未执行”；不能将四项受阻或硬件缺失的测试跳过后仍称 13/13 可用。本轮没有执行这些命令。

参考：[删除复核与 Variation 设计](simulator_deleted_code_review_and_variations_zh.md) · [当前测试逐脚本说明](simulator_test_scripts_zh.md) · [全项目脚本清单](script_inventory_zh.md)。
