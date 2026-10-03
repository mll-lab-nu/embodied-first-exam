# Oracle 内测工具集合：calibration_tools 工程计划

日期：2026-10-02。状态：首版已实现并完成所列范围的验收。原计划保留作为设计依据；实际入口、已支持能力和限制见 [工具 README](../../../topogym/planning/calibration_tools/README.md)，结果见 [验收记录](../../../runs/test_results/calibration_tools_20261002_01/README.md)。

首版物体移动、固定和探查抓持作用于独立几何场景；真实动力学热编辑／约束、跨进程精确恢复等未开放。按需 Nyx 已通过 Env 的可选 owner `sensor_factory` 接入，默认传感器行为保持不变。实现没有给正式 Interaction 或 Harbor RPC 增加开发权限。

需求来源：[Oracle 开发专用工具](oracle_development_tools_zh.md)。目录统一采用 **`topogym/planning/calibration_tools/`**，不另外建立 `devtools/` 或 `calibtation_tools/`。

首版之后的多任务支持需求集中跟踪于 [Oracle 工具与环境支持需求汇总](oracle_tooling_support_zh.md)，包含任务反馈、环境依赖、待补能力和验收条件；本计划保留首版设计范围。

控制步目标／实测跟踪及规划缓存的增量实现见 [控制步跟踪与规划缓存计划](calibration_tools_tracking_cache_plan_zh.md)，工具接口已接入，其合同检查与原生任务适配单独列明，不继承首版物理验收。

**结论：工具函数、开发会话、后台进程、任务适配和命令行入口都集中到这个新目录。完整交付还需要目录外的打包排除、隔离测试和文档接入；共享模拟器只在缺少必要扩展点时小范围修改，不能预先保证所有需求都零外部改动。**

## 1. 使用身份：只有 oracle 开发会话可调用

`oracle_development` 是可信开发进程的身份，不是新增的 benchmark 模式，也不是现有 privileged 权限的升级。

| 调用方 | 能否调用 calibration_tools |
| --- | --- |
| 开发者从受信源码工作区启动的 oracle 内测会话 | 可以，按后端能力提供工具。 |
| 正式 limited / standard 模型 agent | 不可以。 |
| 正式 unlimited / privileged 模型 agent | 不可以，原有读状态与 rewind 合同不因此扩大。 |
| 正式 Harbor oracle 的参考解执行 | 不可以；正式参考解也通过正常动作完成任务。 |
| 正式 sim 服务与 verifier | 不加载、不提供这些接口。 |

开发会话内部可以复用 SegmentRunner 的 `unlimited` 观测配置来读取真值；这只是内部数据通道，不表示正式 unlimited 模型获得开发身份。权限判断不能只看 `enable_privileged` 或 `mode="unlimited"`。

隔离分三层：

1. **交付隔离。** 正式 agent、sim、verifier 镜像中不包含工具包、开发配置和私有资源；正式任务不挂载开发源码、运行目录或控制 socket。现有 `.dockerignore` 和镜像清理已排除整个 planning，继续沿用并做实际镜像检查。可信控制器可能持有源码，不能因此把整份源码挂给模型。
2. **进程隔离。** 开发入口单独启动 supervisor 和 worker，通过私有管道或权限为 0600 的本地 socket 通信；不接入正式 `rcb_client`、server RPC 或 Interaction。会话句柄绑定 worker、episode 和场景版本，重建后旧句柄失效。
3. **调用检查。** 对外函数需要开发会话句柄，禁止通过普通／privileged Interaction 转换出开发会话。字符串、环境变量或 `oracle_dev=True` 不作为取得权限的依据；内部会话令牌只用于误用检查和请求绑定。

Python 同进程内的私有属性和令牌不构成安全沙箱。这里的保证是：正式评测接触不到这套工具及管理进程；不能声称在允许任意 Python 的环境里，仅靠一个布尔判断就能阻止所有等价代码。

## 2. 函数接口与需求对应

统一从 `CalibrationSession` 调用，返回结构化结果及产物路径。以下是拟议 API，不是已实现接口。长任务返回 `operation_id`，通过 `status()` 查询，可暂停／取消；同步工具设置明确超时。

| 需求 | 拟议接口 | 主要返回内容或约束 |
| --- | --- | --- |
| 启动、关闭、查询支持范围 | `open_session(config, output)`、`capabilities()`、`close()` | 会话、后端、支持的操作；不自动打开正式评测权限。 |
| 查看物体／机器人／抓持 | `inspect(entity=None, near=None)` | 实际位姿、目标与实测夹爪开度、抓持阶段、接触摘要。 |
| 看清谁碰到谁 | `contacts(entities=None)` | 实体／link 名称、力、穿透、采样 tick、覆盖范围；缺少接触点位置时明确标为不可用。 |
| 按需近景和叠加图 | `capture_frame(camera, near=None, overlays=())` | 原始 Nyx 图和独立诊断叠加图、相机参数、源状态身份；不隐式推进物理。 |
| 事件触发留证 | `watch(events, before_steps, after_steps)`、`unwatch(id)` | 接触变化、夹爪异常、跟踪误差等事件，前后数值窗口及可用关键帧。 |
| 单步、短段与条件停止 | `step(action)`、`step_until(event, max_control_steps)`、`run_policy(policy, limits)` | 实际执行步数、物理时间、停止原因；动作仍走 Env／SegmentRunner。 |
| 暂停、取消、查询进度 | `pause()`、`cancel(operation_id)`、`status()` | 已提交状态、当前阶段、是否仍在原生调用内部。 |
| 阶段保存与恢复 | `checkpoint(name)`、`restore(name)`、`restart(replay_to=None)` | 世界与策略状态、可恢复范围、重建／回放结果。 |
| 直接移动物体 | `set_object_pose(entity, pose, frame, velocity_policy)`、`set_relative_pose(entity, reference, pose)` | 仅探索场景；姿态、速度、约束处理与新的状态身份。 |
| 暂时固定／模拟抓持 | `pin_object(entity)`、`unpin_object(entity)`、`set_probe_grasp(hand, entity, transform)` | 探索约束句柄；清楚标记它不是由真实双指接触取得的抓持。 |
| 验证物体通路 | `sweep_object(entity, poses, obstacles, resolution)` | 首次碰撞、最小间隙、失败姿态；注明离散采样，不冒充连续无碰撞证明。 |
| 抓姿及 IK 试验 | `solve_ik(targets, seeds)`、`check_robot_path(path)`、`rank_grasps(candidates)` | 位姿误差、关节余量、整臂／手指／腕部相机／桌面碰撞和候选排序。 |
| 微调建模 | `preview_geometry(parameters)`、`compare_geometry(a, b)`、`export_geometry_patch(candidate)` | 新版本预览、截面／净空／质量变化、可审查补丁；不直接覆盖正式资源。 |
| 性能与复现 | `timings()`、`export_report()` | 导入、建场、IK、物理、观察、渲染、记录、收尾的耗时与源码／配置／资产身份。 |

共用约定：位置统一 m、角度统一 rad、四元数使用 wxyz，必须声明坐标系。所有结果携带 `session_id`、适用的 `episode_id/state_ref`、`scene_revision` 和操作身份。修改类请求具备 `request_id`，超时后先查询结果，重复请求不能重复移动物体或修改模型。

后端不支持的操作返回 `UnsupportedCapability`，不能静默换后端或返回看似成功的空结果。首版先完整覆盖 **刚体任务＋ALOHA＋Cast Keyhole 两档**；软体的直接编辑、跨后端约束和完整节点重渲染逐项适配，不声称同一函数已支持全部任务。

## 3. 集中目录与调用方式

建议目录如下，可在实施时合并较小模块，但不把完整工具复制到各任务下面：

```text
topogym/planning/calibration_tools/
  __init__.py             # 导出开发 API；导入时不建场、不启动进程
  __main__.py             # python -m 入口
  api.py                  # CalibrationSession：函数调用、请求身份、结果查询
  contracts.py            # 参数／返回结构、能力列表、错误类型
  supervisor.py           # worker 生命周期、超时、资源监控、取消与重启
  worker.py               # 可信 owner；复用 Env 和 SegmentRunner
  inspection.py           # 状态、接触、事件摘要及触发条件
  rendering.py            # 单路关键帧、近景、叠加、重渲染适配
  checkpoints.py          # 阶段检查点、策略状态、回放恢复
  manipulation.py         # 位姿编辑、临时固定、探查抓持
  geometry.py             # 物体扫掠、模型预览与差异、参数补丁
  kinematics.py           # IK/FK、整机碰撞和抓姿筛选的统一包装
  evidence.py             # 操作日志、探索标记、计时和导出
  adapters/
    base.py               # 任务／后端适配协议
    rigid.py              # 刚体支持
    cast_keyhole.py        # 复用现有 Keyhole 几何及运动学代码
  README.md               # 使用示例和能力边界
```

不另加 `scripts/oracle_runners/dev_session.py`。开发命令和 Python 调用都走同一组函数，例如：

```python
# 拟议示例；当前尚不可运行。
from topogym.planning.calibration_tools import open_session

with open_session(config, output="runs/test_results/calibration_keyhole_trial") as dev:
    dev.inspect(near="right_gripper")
    dev.capture_frame(camera="cam_high", near="keyhole_silver", overlays=("contacts",))
    mark = dev.checkpoint("before_turn")
    result = dev.sweep_object("keyhole_silver", poses=poses,
                              obstacles=("keyhole_gold",), resolution=resolution)
    dev.restore(mark)
```

同一个 worker 只拥有一个活动 Env，符合 Genesis 当前进程约束。渲染或几何探查需要第二个场景时另开进程。工具负责调度与包装，不复制 `Env.step()`、物理时钟、Task 判据或视频 writer。

## 4. 几项容易影响正确性的实现选择

### 按需 RGB

当前 `SensorSuite.sample()` 在 RGB 开启时会渲染所有相机；仅少写几张图片不能消除这部分成本。

首版先支持两条明确路径：已有 RGB 场景中选取近景和关键帧；无 RGB 执行时保存数值窗口，在独立 Nyx 场景中重建／回放需要看的状态。后者可以集中在新目录，但其重建成本需要实测，不承诺实时显示。

若要求同一物理场景真正做到“未请求就不渲染、只渲染一台相机”，需评估给 `SensorSuite` 增加通用的按需取帧扩展，并让开发适配器使用。默认正式 observe/render/RecordingSession 的一致性不变，不把旧图当当前观测。事件前的画面若没录过，只能从完整状态重渲染，不能凭空恢复。原帧与叠加图分开保存，录像仍复用共享 RecordingSession。

### 暂停与原生调用卡死

首版暂停保证在**控制步边界**生效，`run_policy` 通过有界段／策略包装器交回控制，记录 `paused/cancelled`，不能当作任务完成。不会为了暂停而改变正式时序。逐原生 tick 的协作式暂停需要额外 owner 扩展，暂不承诺。

supervisor 独立于物理进程，通过已提交 tick、当前阶段和调用耗时判断进度；首次编译、建场、物理步、渲染分别设预算。原生调用挂住时终止本次 worker，未提交的半步丢弃，从可靠边界重建／回放；不承诺 Python 能中断 CUDA 内核，也不重启整机。CPU 只监控，系统内存达到 90% 停止本轮拥有的相关进程。

### 检查点

复用同 episode 的 rewind：segment 历史只保留初态／段起点的完整 checkpoint，工具需先结束当前段，并为请求的阶段保存完整状态。策略提供 `save_debug_state()/load_debug_state()` 或显式阶段状态适配，覆盖路点索引、积分器和随机数；普通 Python generator 不自动变成可恢复对象。

原生 checkpoint 仅对当前进程／场景有效。重启 worker 首版使用同一冻结实例＋已提交动作前缀重放；如果前缀包含开发位姿编辑，要重放对应开发操作且保持探索标记。跨进程精确 checkpoint 不在首版保证内。

### 直接编辑和模型微调

只允许在暂停的开发探索场景操作。编辑必须统一处理位姿、速度、已有抓持／固定约束、接触缓存、传感器缓存和历史身份；不得只调用原生 `set_pos()` 后继续沿用旧状态 ID。失败时恢复到有效检查点，无法恢复则销毁该 probe，不留下半更新场景。

首版优先提供快速网格／运动学 probe；需要动力学、固定属性或不支持安全修改的约束时，建立新的探索 episode，再按覆写后的声明建场。接口返回 `requires_rebuild` 等明确状态，不承诺所有编辑都能原地热更新。几何变更必须同步碰撞、质量惯量、哈希和版本，令旧路径／IK 缓存失效。参数预览生成 run 目录内的候选资产，`export_geometry_patch()` 只导出补丁，正式任务素材另行纳入开发变更。

每次直接编辑或人工探查抓持写入不可忽略的探索记录；回溯也不把该运行重新标成未经干预。完整机器人成功验证由普通 runner 重新从原场景执行，不能由 `export_report()` 将探索运行升级为正式成功。

## 5. 新目录之外，预计改哪些地方

| 文件／范围 | 是否预计改动 | 原因与边界 |
| --- | --- | --- |
| `pyproject.toml` | **需要** | 当前 package discovery 包含 `topogym*`，尚未排除新工具。将 `topogym.planning.calibration_tools*` 排除出普通发布 wheel，检查包数据也未夹带。开发从受信源码工作区运行。 |
| `MANIFEST.in`／现有发布配置 | 按实际 sdist 构建结果决定 | 如对外发布源码包，同样排除工具及私有产物；只改 wheel 的包发现规则不能直接保证 sdist。 |
| `.dockerignore`、`images/topogym/prune.py` | 默认无需增加排除规则，需回归 | 已排除／清理整个 planning。检查实际构建链；存在另一条遗漏路径时才补规则，不将开发包放回正式镜像。 |
| `ci_checks/test-calibration-tools.py`（新） | **需要** | 接口与任务适配、实际步数、请求去重、回溯、编辑一致性、超时和失败保留检查。真实物理测试单独显式运行。 |
| `ci_checks/check-calibration-isolation.sh`（新） | **需要** | 检查正式 wheel、镜像、挂载和公开接口；limited 与 privileged 均不可导入／调用开发工具。 |
| `ci_checks/run_all.sh` | **需要小改** | 接入轻量静态隔离检查；实际镜像／GPU检查显式指定环境运行，缺环境记未验收，不静默跳过后称通过。 |
| `topogym/simulator/env.py` | **条件性小改** | 若现有 owner 入口无法干净接入探查 Task 声明／传感器适配，可增加默认行为不变的 owner 工厂扩展点。具体开发实现仍在新目录；不新增公共 `dev_mode`、teleport 或任意执行接口。 |
| `topogym/sensors/observation.py` | **条件性小改** | 同场景按需、单相机渲染若无法通过现有接口实现，增加通用取帧能力及对应一致性测试。独立重渲染方案先行时可不改。 |
| `scripts/oracle_runners/run_cast_keyhole_policy.py` | 可选小改 | 需要开发快捷入口或可恢复策略适配时接入；也可由新目录的模块入口直接调现有策略，首版不强制修改。正式运行默认不导入工具。 |
| `topogym/planning/cast_keyhole/simplified_policy.py` | 按阶段恢复需要修改 | 如要恢复策略进度，显式保存阶段状态；不能仅保存世界然后继续使用已前进的 generator。 |
| 原需求文档、工具 README | **需要** | 指向本计划，注明已实现能力和验收范围。 |

默认不改 `World.advance()`、原生求解器、Task 成功条件、正式 Interaction／PrivilegedAccess、Harbor 客户端／RPC、根目录生成的任务包或现有场景素材。接触点／软体支持不足时先报能力缺口，不为补一个工具默认扩大共享改动。

因此，**可以把全部开发功能的实现集中管理，不能把打包隔离、测试接入也藏在新目录里便声称完成隔离。** 必要的共享扩展点独立列出并做旧行为回归；不为追求“全部在一个目录”而复制 Env、全局 monkeypatch，或绕开缓存／历史一致性。

## 6. 实施批次与验收

1. **目录骨架与隔离先行。** 完成 session／协议／能力表、模块入口、发布排除和隔离检查；新目录普通 import 无建场副作用。此时不宣称物理工具可用。
2. **观测和进程控制。** 接入 inspect、contacts、关键帧、watch、step／短段、pause／cancel、watchdog 和计时。用可控阻塞的测试 worker 验证超时处理，不故意挂死真实 GPU。
3. **回溯与物体探查。** 实现 checkpoint、策略状态恢复、位姿编辑、固定／探查抓持和完整物体扫掠，验证编辑后缓存与身份没有混用。
4. **IK 与建模工具。** 接入 Keyhole 适配，提供 IK／整机路径检查、抓姿筛选、几何预览和补丁导出；冻结必要的共享扩展点并回归。
5. **双层验收。** 在 oracle 开发环境逐项调用全部首版接口；另在实际 limited、privileged、sim、verifier 环境检查没有模块、入口、socket 或开发目录可访问。Harbor 的正式 oracle 同样不附带这些工具。

验收至少包括：

- 读取／截图不推进物理；关键帧对应真实 state_ref，近景不会污染原相机帧；软体数据不足时拒绝重渲染。
- step 数量按实际推进记录；暂停／取消不会产生虚假成功，超时重试不会重复执行。
- 恢复后世界与策略一致，旧未来失效，重建场景后旧句柄失效；无法跨进程恢复的状态明确拒绝。
- 编辑／固定／探查抓持均带探索记录，不能混入未经干预的成功证据；失败的几何预览不覆盖原资产。
- 正式镜像内在不挂源码的干净工作目录执行导入和入口检查，避免宿主 checkout 让“隔离测试”测错对象；修改环境变量也不能获得开发服务。
- 固定源码快照运行 Keyhole 两档的短程真实物理与 Nyx 取帧检查，回归原 easy–hard 的默认配置、观测和正常执行路径。完整 oracle 成功单独验收，不由工具测试代替。

报告、配置、资源采样及实际录像放 `runs/test_results/calibration_tools_<run-id>/`；日常探索可放 `runs/oracle_dev/`。每项能力分别记录已实现／已验收／后端不支持，不用一个总的“完成”覆盖缺项。

参考现有基础：[Env](../../../topogym/simulator/env.py)、[Interaction](../../../topogym/simulator/interaction.py)、[PrivilegedAccess](../../../topogym/simulator/privileged.py)、[SensorSuite](../../../topogym/sensors/observation.py)、[RecordingSession](../../../topogym/recording/session.py)、[打包配置](../../../pyproject.toml)、[镜像清理](../../../images/topogym/prune.py)。
