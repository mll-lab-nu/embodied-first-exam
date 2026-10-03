# calibration_tools 控制步跟踪与规划缓存计划

日期：2026-10-02。状态：工具接口已实现，工具合同与任务物理接入分别验证。对应 [支持需求 SUP-004 与 SUP-008](oracle_tooling_support_zh.md)，实现集中在 `topogym/planning/calibration_tools/`，实际接口见 [工具 README](../../../topogym/planning/calibration_tools/README.md)。按用户最新范围，本轮不定位或修复反馈中的仿真 bug，不开展原任务的求解调试。

## 本轮工具交付

| 开发需求 | 已提供的工具支持 | 使用边界 |
| --- | --- | --- |
| 按步对照目标与实测状态 | `start_tracking`／`tracking_report`／`stop_tracking`、忙碌时 `status` 摘要和离线 `read_tracking_report`。 | 实测来自已提交 World tick，初态、拒绝和部分执行分开记录。 |
| 查看本动作采用的物体目标 | 可选 `debug_reference()` 和开发目录中的 Keyhole generator 包装器。 | 按本动作参考配对，不做自动时间插值或路线最近点猜测。 |
| 复用昂贵规划结果 | `cache_plan`／`check_cached_plan`／`prepare_plan` 与 JSON／NPZ 内容哈希存储。 | 按当前身份、起点和检查覆盖返回 reuse／repair／seed_only／miss。 |
| 接入任务自己的规划器 | 只读查询适配协议，以及复用现有原生 IK 的 `keyhole_tcp` 路点适配器。 | 内置适配器接受已有 TCP 路线，不搜索谜题解法，按预算修正短路线并回退完整 IK。 |

与原方案的首版差异：不提供任意连续时间参考 provider；JOINT 模式自动跟踪关节误差，目标 TCP 的额外 FK 可继续用现有路径查询；缓存内置适配限定已给定的 Keyhole TCP 路线，Claws、FEM 和完整任务规划器需各自接入。原生碰撞查询仍是采样范围，不能作为连续证书。

验证入口为 `ci_checks/test-calibration-tracking-cache.py`，使用记录状态夹具检查配对、分支、缓存和回退合同；本轮不将这些检查表述为任务物理验收或提速测量。下面保留原设计依据与后续验收合同。

本轮结果：新增 23 项工具合同、既有 12 项会话／几何合同与 9 项观测计时合同通过；静态发布隔离检查通过，原生物理接入、GPU 性能与任务成功未在本轮运行。

先交付不要求修改 scripted policy 的控制步跟踪：将实际生效的关节目标与同一步实测状态自动配对。物体目标作为可选开发信息接入。规划缓存另存物体路线、IK 结果和适用条件，经过当前实测状态检查后复用或修正；缓存不是物理 checkpoint，也不保存可继承的成功资格。

## 现有执行语义

[policy runner](../../../topogym/simulator/rollout_simulation/policy.py) 每次调用 `act(observation)` 得到一个 action，交给标准 step，完成后再取观测调用下一次 `act()`；返回 `None` 表示策略结束。没有另一套绕过控制步推进的规划器时钟。

[Env.step](../../../topogym/simulator/env.py) 编译并施加 action，然后推进 `control_decimation` 个 World tick。正常控制周期为 `physics_dt_s × control_decimation`，每个 World tick 内还有求解器子步；提前终止时以实际执行 tick 数和 `action_duration_s` 为准。策略计算或 CPU 物理变慢增加墙钟耗时，不自动推进仿真时间。

[动作编译](../../../topogym/robot/control.py) 区分四种输入：

| 模式 | policy 提交什么 | Env 实际执行什么 |
| --- | --- | --- |
| `JOINT_ABS` | 关节位置目标 | 验证后的关节目标，无需再做 IK。 |
| `JOINT_DELTA` | 关节增量 | 相对动作前实测状态求出的绝对关节目标。 |
| `EE_ABS` | 世界系 TCP 位置和朝向 | 经公共 IK 编译的关节目标。 |
| `EE_DELTA` | TCP 平移／旋转增量 | 相对动作前实测 TCP 的目标，再经公共 IK 编译。 |

所以 action 不一定是 IK 的输出，但最终都由关节控制器在物理中执行。省略某臂或空 action 保持已有目标；目标值不能当作已经到达的实际值。

“控制步编号”与“路线采样编号”也不同。[Keyhole `follow_bodies`](../../../topogym/planning/cast_keyhole/policy.py) 每步都返回 action，但只有跟踪误差符合门槛才增加内部 `progress`；误差较大时可连续几步保持同一物体目标并修正机器人命令。其 `move()` 则按仿真时间插值并增加稳定等待段。这两种策略都遵守同一个 runner 控制周期。

首版据此统一按控制步对照，不做轨迹最近点匹配、时间扭曲或事后重配对。仅当 policy 要额外解释几何路线时，记录这一步实际采用的路点／进度；它是动作注释，不是独立的执行时钟。

## 控制步跟踪工具

### 已有数据与新增输出

[Env.tick_record](../../../topogym/simulator/env.py) 已携带状态身份、实测 world／robot、当时生效的 `targets` 和 Task 状态；[SegmentEvidence](../../../topogym/simulator/rollout_simulation/evidence.py) 已写入 `execution/private/physics_states.jsonl`，大数组另存 NPZ。步完成回执还包含 `executed_joint_targets`。因此实测轨迹直接来自已有物理记录，不通过 RGB 推测，也不重新求 IK 生成一条替代命令轨迹。

以下开发 API 已接入；首版使用示例与支持范围以工具 README 为准：

| 拟议接口 | 使用与输出 |
| --- | --- |
| `start_tracking(entities=(), relative_pairs=(), thresholds=None, reference_provider=None)` | 空闲时开启；默认每控制步采样，返回 `tracking_id`；不改变 action 或推进物理。 |
| `tracking_report(tracking_id)` | 返回已提交样本数、各项误差摘要、首次越界位置、覆盖范围与详细产物路径。 |
| `stop_tracking(tracking_id)` | 空闲边界结束采集，写完整摘要；不停止或重置物理世界。 |

运行中的轻量进展从 supervisor 的 `status()` 获取已提交摘要，不向正忙的 worker 插入同步查询。离线分析复用已有执行记录，不依赖重新运行策略。

每条记录包含 `episode_id`、`branch_id`、`state_ref`、`segment_id`、`action_index`、`control_step`、World tick／仿真时间区间，以及提交的 action、生效关节目标、实测关节／TCP／选定物体位姿。初态单列，不错配到第一个 action；action 编号允许跨段重新起算，必须结合 segment 和状态身份使用。

### 如何自动配对

1. 开发 wrapper 在提交动作前生成唯一尝试编号，冻结 action 及可选参考信息，并记录动作前的状态；计数不直接当作“已完成步骤数”。
2. 复用 owner 的 state sink 读取每个已提交 tick。以记录中的控制步、分支和当时生效 `targets` 归属动作；正常步结束再用 transition 校核实际 tick 数及结束状态。
3. 默认报告步末误差；已有 tick 记录可用于该控制步内的最大误差和首次越界定位，明确覆盖 World tick，不能声称覆盖全部求解器子步。实际关节与该 tick 生效目标比较，不能与下一条动作比较。
4. 被拒绝的 action 只有尝试记录，不产生已执行样本；提前终止记录较短周期；发生异常且没有完整 transition 时，只保留真实已提交 tick，标记部分执行或未完成，不补造末态。

`JOINT_DELTA` 和 `EE_DELTA` 使用实际编译后的绝对目标；空 action／省略臂使用继续保持的目标。EE 输入另外保留原始 TCP 目标与动作前测量，计算 TCP 请求误差；关节模式下若需要目标 TCP，可选择只读 FK 派生，并标明是 FK 预测。关节误差与 TCP 请求误差分别报告，避免把 IK 编译误差和执行误差混成一个数。

### 物体参考只作为可选信息

仅查看关节／TCP 跟踪不要求 planner 改接口。需要比较物体期望路线时，开发 policy 可提供可选只读方法 `debug_reference()`，或配置任务适配器作为 `reference_provider`；由开发 wrapper 在 `act()` 返回后、action 执行前读取，正式 `act()` 仍只返回标准 action。

参考信息绑定刚刚生成的 action，包括 `plan_id`、计划版本、阶段、可选 `sample_index`／`progress_used`，以及世界系物体目标或明确参照物的相对目标。位置单位 m、旋转使用单位 wxyz 四元数；坐标系、物体原点与冻结网格一致。

关键约定是返回“本次 action 生成时使用的目标”，而非 policy 已经准备的下一点。例如当前 Keyhole `follow_bodies()` 先计算 `pose_at(progress)`，再可能递增 `progress`，最后 `yield action`；适配时应在递增前保存目标及 `progress_used`，不能直接把 yield 后的 `diagnostics.progress` 当作本步参考。

物体参考分为本步明确目标、可选连续时间参考两类，首版优先前者。只有完整提供时间插值合同才生成 tick 内参考，不自动给路点补运动规律。没有物体参考时仍输出实测轨迹与机器人跟踪，物体误差明确 `reference_unavailable`；不会从实际运动反猜期望位置，也不会把已加反馈补偿的关节命令当作原始物体目标。

对 Claws 等双物体任务，同时记录各件世界位姿误差和两件相对位姿误差。只有提供同一坐标约定、几何身份与采样位置对应的净空时才计算风险提示；旋转误差需结合物体尺寸换算表面位移界，不能把 rad 与 m 直接比较。风险提示不是独立碰撞证书，缺少净空时仅报告误差。

### 回溯和产物

暂停期间无新物理 tick 就不新增运动样本。恢复 checkpoint 后保留旧分支记录并标记失效未来，新样本绑定新分支；参考游标、积分器及活动计划版本随显式策略状态一起恢复。没有 `save_debug_state/load_debug_state` 的 generator 不因跟踪工具而自动变成可恢复策略。

每次重规划产生新的不可变 `plan_id`／版本，历史动作继续引用旧计划；计划名称相同不能覆盖旧内容。worker 重启沿用现有动作前缀回放规则，不假定 policy 内部进度或物体参考已恢复。

拟议产物为 `tracking/<tracking_id>/samples.jsonl` 与 `summary.json`，保存紧凑指标和原始证据引用；复用已有 world／robot 采样，不每步额外 `inspect()`，不重复保存全部 FEM 数组，不默认渲染。摘要接入现有 `export_report()`，并用现有 profiler 对照跟踪关闭／开启的耗时和输出体积。

## 规划缓存工具

### 缓存内容与适用范围

缓存重点是抓持前预检或先前规划中昂贵的结果，而非每个控制步的测量快照。

| 内容 | 必要信息 |
| --- | --- |
| 物体路线 | 物体／相对坐标系、位置与朝向路点、阶段；时间律和速度限制若有则单列。 |
| 双臂 IK 结果 | 关节名与顺序、完整 robot qpos 采样、对应物体路点、抓持变换；可选 TCP/FK 结果。 |
| 规划起点假设 | 双臂状态、物体状态、手物变换、接触／抓持模式及允许接触对。 |
| 依赖身份 | 任务／实例、机器人模型和限位、冻结碰撞网格及尺度、相关源码／规划器版本、参数与坐标约定。 |
| 历史检查 | 检查器版本、采样分辨率、覆盖范围、IK 残差、关节余量与净空；仅作为来源记录。 |

物体几何路线、关节路线和带时序的执行轨迹分别声明依赖。修改速度或控制周期不必丢弃几何路点，但带时序动作及其检查需重新生成；修改几何、机器人或抓姿则使相关检查失效。后端、精度和控制配置变化也必须重新评估执行相关结果，不能从资产哈希相同推断完全可复用。

默认缓存位于源码开发侧 `runs/oracle_dev/plan_cache/`，可显式指定共享开发目录；不进入正式镜像。每个条目用内容哈希标识，包含 JSON manifest 和不含可执行对象的 NPZ 数组，临时写入完成后原子提交。并发同键写入只复用完整且校验通过的条目；损坏或缺失条目返回 miss，不能覆盖旧运行证据。

### 拟议 API 与任务适配

| 拟议接口 | 合同 |
| --- | --- |
| `cache_plan(plan_bundle)` | 检查格式与依赖后存储规划结果，返回 `plan_id`、manifest 路径和覆盖范围；保存本身不授予复用资格。 |
| `check_cached_plan(plan_id, tolerances, adapter)` | 读取当前实测抓持状态，执行身份、起点和路径复核，返回结构化决定及原因；不推进物理。 |
| `prepare_plan(request, adapter, use_cache=True)` | 按请求查缓存，依次尝试可用路线、局部修正、完整规划；返回选中的计划及各阶段计时。 |

任务适配器由可信开发配置指定，提供 `plan`、`repair`、`validate` 三个入口，可声明不支持局部修正。公共工具负责缓存、调用顺序、记录和预算，任务 planner 负责物体路线及连接约束，不把完整求解器复制进工具目录。

适配器在当前 worker 内使用只读查询上下文，不通过同一个忙碌 `CalibrationSession` 再提交嵌套请求。操作采用既有异步回执、超时和取消边界。返回的复用决定绑定当前 episode／branch／state、抓持状态及有效期；一旦推进物理、回溯或换计划，在消费前重新检查相关前提，旧决定不能直接当作新的放行结果。

### 复用决定和回退

| 决定 | 条件与处理 |
| --- | --- |
| `reuse` | 身份适用、起点可接入，并完成当前实例所需检查；返回路线作为执行候选，仍非物理成功证明。 |
| `repair` | 几何路线仍适用，实测起点／抓姿有可修正差异；旧 qpos 作为 IK 初值，修正接入段和受影响路段后复核。 |
| `seed_only` | 缺少充分复用检查或不支持某项验证；兼容的旧 IK 解仅作为新规划初值，不能直接执行旧路线。 |
| `miss` | 无匹配条目、文件损坏、关键身份不兼容或修正失败；调用任务完整 planner 并记录原因。 |

阈值由任务净空和跟踪误差预算决定，配置中注明来源；至少比较物体平移／旋转、两件相对姿态、双臂关节分支、手物变换及接触状态。单一“起点差小于 1 mm”不足以判断复用。

局部修正流程为：从实测状态构造连续接入段，以缓存各点为 IK seed 解受影响目标，检查限位、分支跳变、机器人碰撞及随手运动的持件碰撞，并按任务规则重新认证物体路线。修正前后采用同一验证范围，不能只检查修改点而忽略连接处；超出局部修正预算则转完整规划，失败保留诊断。

现有 `check_robot_path()` 只检查提交的采样，不能自动证明连续路径，也未形成完整的随动持件／FEM 形变路径验证。首版复用验收需要任务适配器明确补齐所需覆盖；能力缺失时返回 `seed_only`／`miss`。几何 probe 目前仅适配 Keyhole，Claws 需先对齐来源代码，FEM／IPC 完整缓存复用不纳入首批验收。

缓存与执行模式保持一致：EE policy 即使复用了离线 IK 路线，每步 EE action 仍经公共 IK，不能为加速偷偷切成 JOINT 或跳过动作编译。首批性能收益核算只计算实际省掉的规划工作；若另选 JOINT 路线执行，需显式配置及单独执行验收。

### 与跟踪工具的连接

`prepare_plan()` 返回的 `plan_id` 可直接作为物体参考来源。执行每一步仍由 policy 产生标准 action；跟踪记录自动保存该步生效命令，可选引用计划采样。规划缓存存“准备执行的候选”，跟踪产物存“本次实际执行了什么”，二者通过计划身份关联，不互相覆盖。

用户最小工作流为：先调用 `start_tracking()` 即可看机器人跟踪；需要物体误差时再接入 `debug_reference()`；已有 planner 输出接入 `cache_plan()` 后，通过 `check_cached_plan()` 看能否复用；最后用 `prepare_plan()` 自动串起任务已提供的修正／完整规划入口。每阶段都能独立使用，不以全部任务完成适配为前置条件。

## 文件范围与交付顺序

| 位置 | 拟议改动 |
| --- | --- |
| `calibration_tools/tracking.py` | 新增控制步配对、误差计算、参考合同及紧凑产物。 |
| `calibration_tools/plan_cache.py` | 新增计划存储、依赖匹配、决定与回退调度。 |
| `calibration_tools/adapters/` | 增加明确的规划适配协议，首批接已有 Keyhole planner；其他任务逐项接入。 |
| `calibration_tools/worker.py`、`api.py`、`contracts.py` | 接入拟议方法、可选参考 provider、既有 tick／transition 回调和异步回执。 |
| `calibration_tools/checkpoints.py`、`evidence.py`、`supervisor.py` | 保存跟踪分支／参考游标、导出摘要及传递运行中轻量状态。 |
| 工具 README、支持需求表、`ci_checks/` | 新增使用示例与能力覆盖，补有意义的合同和短物理验收。 |

默认复用 Env、SegmentRunner 和现有 state sink，不修改公开 action 格式、正式 RPC、Task 判据或物理时钟。仅在实现证明现有事件缺少必要信息时，单列最小共享扩展；参考 provider 优先在开发适配层实现。现有 profiling／watch 等并行改动保持原样接入，不整文件覆盖。

| 批次 | 可交付结果 | 关键验收 |
| --- | --- | --- |
| A 控制步跟踪 | 零 policy 改动即可对照命令与实测关节／TCP，支持报告导出。 | JOINT／EE 及 delta、空动作／省略臂、多个 tick、提前终止和动作拒绝均正确配对；开启工具不改变动作或物理步数。 |
| B 物体参考与分支 | Keyhole 可选物体目标、相对误差与净空提示；回溯不串记录。 | 同一路点多步保持、反馈补偿、目标与下一点进度错位、暂停／回溯／重规划均可区分；无参考时仍可用。 |
| C 缓存与人工检查 | 计划可存储、查找并输出复用／修正／seed／miss 决定。 | 资产／机器人／抓姿／时序依赖变化、损坏缓存、并发写入、缺验证能力和过期决定均有明确处理。 |
| D 局部修正与回退 | Keyhole 的 `prepare_plan()` 可实际节省重复规划。 | 代表性的可复用、可修正和必须完整规划案例，比较检查覆盖、规划耗时及短物理跟踪结果；完整 oracle 成功另行验收。 |

验收使用冻结源码、同实例和同输入比较缓存关闭／开启；分别记录命中、检查、局部修正、完整规划耗时，不把少做检查或少执行物理当加速。已有目标／实测日志足够完成批次 A，先解决最直接的问题，再接物体意图和任务缓存流程。
