# Oracle 内测工具

这是一套只能从可信源码工作区启动的开发工具。正式 limited、privileged、sim、verifier 镜像与发布包不提供此目录，也没有对应的公开 RPC。它复用 Env、SegmentRunner、SensorSuite 和 RecordingSession。

跨任务反馈、工具缺口、环境支持与验收要求持续记录在 [Oracle 工具与环境支持需求汇总](../../../docs/tasks_simplifications/devs/oracle_tooling_support_zh.md)。其中待实现或待验证的条目不代表本工具已提供相应能力。

控制步跟踪和规划缓存的工具接口已接入，设计与验证边界见 [控制步跟踪与规划缓存计划](../../../docs/tasks_simplifications/devs/calibration_tools_tracking_cache_plan_zh.md)；本轮只增加开发支持，不处理反馈中的仿真 bug 或调整任务参数。

## 快速使用

工作目录为仓库根目录。需要现有 Genesis 环境及 `psutil`；Nyx 使用 `.venv-gs121-nyx` 和 CUDA。`multiprocessing` 使用 spawn，因此 Python 脚本入口必须放在 `if __name__ == "__main__":` 下，不从 `python - <<'PY'` 启动会话。

```python
from topogym.planning.calibration_tools import open_session

def main():
    config = dict(task_id="cast_keyhole", variation_id="very_easy",
                  compute_backend="cuda", enable_rgb=True, seed=0)
    with open_session(config, "runs/oracle_dev/keyhole_try_01") as dev:
        print(dev.capabilities())
        dev.inspect(near="right")
        mark = dev.checkpoint("before_grasp")
        dev.watch(["contact_changed"], before_steps=3, after_steps=2,
                  camera="cam_high", near="keyhole_silver", overlays=["contacts"])
        dev.step({})  # 空动作维持当前控制目标；实际推进一个控制步
        frame = dev.capture_frame("cam_high", near="keyhole_silver")
        dev.restore(mark)
        print(frame["raw"], dev.export_report()["report"])

if __name__ == "__main__":
    main()
```

输出目录必须不存在，避免覆盖旧证据。`enable_rgb=True` 会建相机；开发传感器在普通控制步不读取 RGB，`capture_frame` 或配置了相机的 watch 才请求图像。首版“近景”是实际 Nyx 原帧的裁剪放大，不移动正式相机；Nyx 内部可能仍批量处理整个相机组。

不需要物理引擎时，显式选择几何会话：

```python
with open_session(dict(task_id="cast_keyhole", variation_id="easier",
                       compute_backend="cpu", enable_rgb=False, seed=0),
                  "runs/oracle_dev/keyhole_geometry_01", kind="geometry") as dev:
    state = dev.inspect()
    silver = state["bodies"]["keyhole_silver"]
    pose = {k: silver[k] for k in ("position_m", "quaternion_wxyz")}
    mark = dev.checkpoint("original")
    pose["position_m"][0] += .01
    dev.set_object_pose("keyhole_silver", pose)
    result = dev.sweep_object("keyhole_silver", [pose], obstacles=["keyhole_gold"])
    dev.restore(mark)
```

上例也应放在带 main guard 的脚本里。米、弧度、wxyz 是统一单位；`set_relative_pose(entity, reference, pose)` 的 pose 位于 reference 局部坐标系。默认 `kind="physics"` 不会在 GPU 缺失时自动降级。

## 当前能力与限制

| 接口 | 首版行为 |
| --- | --- |
| `inspect`、`contacts` | 真实物体／机器人状态、控制目标、抓持管理状态、命名后的刚体接触；接触点位置缺失时返回 `None`。 |
| `capture_frame` | 按需 Nyx 原图、可选裁剪与文字诊断叠加，带真实 episode／branch／state／tick。`record_video=True` 用共享 RecordingSession 保存该关键帧；不是完整过程录像。 |
| `watch`／`unwatch` | 接触变化、跟踪误差、手指位置变化或每步事件；触发时先保存数值前窗，再按需截图，后窗逐步追加。未录过的事件前画面不自动补造。 |
| `step`、`step_until` | 经标准 SegmentRunner 实际执行；`step_until` 重复指定 action（默认维持目标），在控制步边界检测事件。 |
| `run_policy` | 加载可信 policy factory，通过标准 policy 观测投影执行。设定控制步上限，返回异步 operation_id。 |
| `status`、`pause`、`cancel` | supervisor 始终可查询；暂停／取消在下一控制步或几何采样边界生效。原生调用挂住时由超时保护终止本轮 worker。 |
| `checkpoint`／`restore` | 当前进程内的世界、几何探查及显式策略状态；回溯后的旧未来作废。 |
| `restart(replay_to=N)` | 重建同配置和 seed，回放 N 个已提交动作；源码变化拒绝回放。不恢复原生 checkpoint、策略 generator 或几何编辑。默认 `restart()` 只重建初态。 |
| `sync_probe` | 将当前实测物体位姿复制到独立几何探查场景，清除该探查场景的临时固定／抓持。 |
| `set_object_pose`、`set_relative_pose` | **只编辑独立几何探查场景**，不修改 Env 中真实物体，不沿用真实世界状态 ID 表示编辑。 |
| `pin_object`、`unpin_object`、`set_probe_grasp` | 几何固定／手与物体之间的刚性变换，用于探查；不产生物理约束或真实接触抓持。清除抓持用 `set_probe_grasp(hand, None)`。 |
| `sweep_object` | 将路点按平移／旋转分辨率细分，返回首个碰撞和最小采样间隙，包括实体包含检查。只检查列明的任务物体，不默认包含机器人和桌面。 |
| `solve_ik`、`check_robot_path`、`rank_grasps` | 只读原生 IK/FK、导入碰撞网格的采样检查；包含双臂、手指及已建模的腕部相机。列出相邻刚体／固定安装的排除项；候选优先按环境净空和关节余量排序。 |
| `preview_geometry`、`compare_geometry`、`export_geometry_patch` | 生成独立 Keyhole 候选资产、截面、质量惯量、净空差和带原版本哈希的参数补丁；不应用到正式任务。 |
| `timings`、`export_report` | 分层阶段计时、源码／配置／资产身份、进程资源、动作记录和探索标记。`timings()` 由父进程读取，worker 忙碌或已失败时也可查询。 |
| `grasp_status` | 被动解释 assist 状态、后端拒绝原因、已报告的条件及阈值余量；未提供的测量为 `None`。 |
| `run_grasp_trial`、`grasp_trial_report` | 异步执行明确给出的接近／闭合／提升／持握／释放动作，保存逐 tick 测量、阶段、事件、判据及可选共享录像。 |
| `start_tracking`、`tracking_report`、`stop_tracking` | 按已提交控制步汇总关节／TCP 误差，接收可选物体参考，并保留回溯分支和不完整执行。 |
| `cache_plan`、`check_cached_plan`、`prepare_plan` | 保存不可变候选计划，按身份／实测起点／检查覆盖决定复用、局部修正或完整规划。 |
| `task_summary` | 分开显示目标进度、失败原因、判据开关与 registry 验收引用；忙碌时从 `status().progress.task_summary` 读取最后提交的摘要。 |
| `contact_details`、`gripper_geometry` | 查询可用接触位置及后端来源，测量实际碰撞面距离；指定指垫三角面后可测指垫距离。 |
| `compare_runs`、`summarize_run` | 离线对照已有运行的步数、分项耗时、缓存选择和任务摘要；记录的执行工作不一致时不给加速比。 |
| `drive_object` | 在显式准备的 FEM／IPC 开发会话中，以有界外力或位置 PD 探索物体运动；实验接口，尚无 GPU 动力学验收。 |

几何编辑与建模适配目前覆盖显式 Cast Keyhole 变体；`seeded` 场景扰动和其他任务需要额外适配。真实动力学 teleport／pin、软体节点编辑、跨进程精确 checkpoint、未记录状态的历史重渲染、精确接触点箭头尚未提供。调用不支持的能力明确报 `UnsupportedCapability`。

`check_robot_path` 的 path 是**完整 robot qpos 的列表**，只检查提交的采样，不替调用者做连续关节插值。`allowed_contacts` 是显式的 `entity/link` 名称对；结果记录所有允许项。无碰撞候选不等于机器人成功抓持或完成任务。

`check_robot_path(..., include_tcp=True)` 还返回相同采样点的原生 FK `tcp_path`（各臂的 `position_m` / `quaternion_wxyz`）。开发方可据此构造沿关节路径的 EE 接近路点，避免只在几个独立 Cartesian 目标上求 IK 而忽略中间构型。此选项不发送控制命令，也不推进物理；实际 EE 执行仍会经过公共 IK 校验。

## 状态摘要与接触／夹爪读数

```python
summary = dev.task_summary()  # 空闲时读取当前状态，不推进物理
print(summary["progress"], summary["outcome"])
print(summary["evaluation"], summary["qualification"])

op = dev.run_policy(policy_spec, max_control_steps=40)
print(dev.status(op)["progress"]["task_summary"])  # 不向忙碌 worker 发送读取请求
dev.wait(op)

contacts = dev.contact_details(entities=["robot", "piece"])
fingers = dev.gripper_geometry("right", include_surfaces=True)
```

`progress` 包含 Task 已报告的目标条件、稳定时间和指标；`outcome` 分开列出失败、终止与时间上限；`evaluation.goal_enabled` 表示原生目标判据是否启用。`qualification` 保留 registry 状态、验收引用与声明缺口，**不会从开关或 registry 状态推导已验收范围**；历史证据尚未解析时 `accepted_scope=None`。父进程摘要在控制步提交及回溯后更新，带 episode／branch／state 和仿真时间；原生步卡住时仍可读取，但不是卡住帧内部的新测量。

`contact_details()` 一次读取 Genesis 刚体接触缓冲区，返回命名接触对、可用力／穿透以及 `contact_position_world_m`，同时注明来源。缺少位置时保留 `None`；IPC 接触的命名对、力和位置尚未映射，单独以 `ipc.contacts=None` 和缺失原因说明，不把刚体缓冲区当成完整 IPC 接触。此接口不自动判定“哪个接触顶开手指”。

`gripper_geometry()` 返回实际／指令手指坐标、`finger_surface_clearance`、最近点和是否相交。默认自动选择 IPC 实际仿射碰撞面，非 IPC 场景使用 Genesis 碰撞面；可用 `source="ipc"` 或 `"genesis"` 显式选择。单指关节坐标和整根手指表面距离都不等于指垫净间距。

若已确定同一后端碰撞网格的指垫三角面，传 `pad_faces={"right": {实际左指链接名: [三角面编号], 实际右指链接名: [三角面编号]}}`，即可读取 `pad_surface_clearance`；未指定时该字段为 `None`。`include_surfaces=True` 按需返回每根手指的世界坐标顶点和三角面编号，供选择指垫面；默认不传网格。所有距离仅为当前三角表面几何量，相交时不会推断接触力或穿透深度，也不推进物理。

## 已有运行的耗时对照

```python
from topogym.planning.calibration_tools import compare_runs

comparison = compare_runs(["runs/oracle_dev/baseline", "runs/oracle_dev/candidate"])
print(comparison["comparisons"])
print(comparison["planning_by_selection"])
```

该函数离线读取已落盘的配置、源码／资产身份、动作、计时和报告，不启动仿真；也可调用 `dev.compare_runs(...)`。每次运行同时列出总执行步数和回溯后有效分支步数，耗时对应全部实际工作。对照项列出分阶段总耗时与扣除子阶段后的耗时差，以及缓存命中／修正／完整规划的分项成本。

只有配置、源码、资产、候选、动作／tick 数、回溯与外力记录一致且证据完整时，才提供控制步墙钟时间比；硬件和背景负载仍标为未核验。不同参数运行照常列出原始数据和差异，但不给加速比。`planning_by_selection` 是按缓存选择汇总的描述性统计，不把不同规划请求的成本差当成缓存带来的加速。

## 同一 FEM／IPC 模型下的外力探索

必须在新建物理会话时声明目标实体，工具才会在 native IPC 初始化前注册 libuipc 外力接口；不改正式 Task、共享 World 文件或默认物理参数。以下片段放在前述 main guard 内，`ipc_config`、实体名和节点集合由当前任务提供：

```python
with open_session(ipc_config, "runs/oracle_dev/object_force_01", kind="physics",
                  candidate={"object_drives": {fem_entity: "fem"}}) as dev:
    op = dev.drive_object(
        fem_entity, vertex_indices=selected_vertex_indices,
        control_steps=5, force_world_n=[0., 0., .1], max_force_n=.1,
    )
    print(dev.status(op)["progress"])
    result = dev.wait(op)
```

`force_world_n` 是所选 FEM 节点共同承担的**总力**，均分到明确选择的节点；示例数值只说明单位与调用方式，不是推荐任务参数。单刚体使用 `{entity: "rigid"}`，不传 `vertex_indices`；仅支持单环境、单链接、可动 `ipc_only` 任务刚体，不支持机器人和桌面。

也可将 `force_world_n` 替换为 `positions_world_m=[[x, y, z], ...]`，并提供 `kp_n_per_m`、`kd_ns_per_m`：工具从实测起点按控制步插值目标，对刚体原点或所选 FEM 节点平均位置施加有界 PD 力。`max_force_n` 必填，位置跟随不保证精确到达，不提供姿态驱动、运动学 teleport 或新积分器。

每次经现有 SegmentRunner 执行空动作、保持机器人控制目标，记录参考、施力、实测位置及状态引用；暂停／取消在控制步边界生效，原生超时沿用 supervisor 保护。完成、取消和可捕获异常后清零外力，回溯后也清零；worker 被终止时该进程中的场景随之销毁。运行永久标为探索，不能作为机器人完成证明；包含外力的动作序列拒绝 `restart(replay_to=N)`，因为仅回放机器人动作不能恢复外力历史。

验收范围：工具调用、取消／清理、真实 libuipc 几何声明及外力缓冲区读写已检查；**未完成 GPU World 中的动力学验收**。`capabilities().object_drives.physical_acceptance` 因此为 `False`，不承诺解题效果或迭代加速。

## 控制步跟踪与物体参考

```python
tracking_id = dev.start_tracking(
    entities=["keyhole_gold", "keyhole_silver"],
    relative_pairs=[["keyhole_silver", "keyhole_gold"]],
    thresholds={"joint_rad": .01, "object_m": .002},  # 示例阈值，按任务预算设置
)["tracking_id"]
operation = dev.run_policy(policy_spec, max_control_steps=100)
print(dev.status(operation)["progress"].get("tracking"))  # 忙碌时读取父进程摘要
dev.wait(operation)
report = dev.stop_tracking(tracking_id)
```

四种控制模式统一比较 tick 中已经生效的绝对关节目标，空动作保持原目标；EE 模式另比较本动作请求的 TCP 位姿，不重做 IK。采样覆盖已提交 World tick，记录步末值、步内最大值与首次越界；不包含全部 solver 子步。`tracking/<id>/samples.jsonl` 保存初态、动作尝试、tick 指标及完整／部分执行样本，`summary.json` 和 `export_report()` 提供摘要。初态、被拒绝动作和暂停时间不冒充完成步数；回溯通过追加失效记录保留旧分支，摘要默认统计全部历史。

物体参考由 policy 的可选 `debug_reference()` 在 `act()` 返回后提供，普通 action 格式不变：

```python
def debug_reference(self):
    return {
        "plan_id": self.plan_id, "version": 1, "phase": "route",
        "frame": "world", "units": "m_wxyz", "progress_used": self.progress_used,
        "objects": {"keyhole_silver": self.target_used},
        "relative_targets": [],
    }
```

`target_used` 必须是刚刚生成 action 所采用的物理物体原点位姿，字段为 `position_m` 与单位 `quaternion_wxyz`；没有参考时明确返回 `reference_unavailable`。每条参考视为本动作内保持的目标，不猜测时间律。可选 `clearances[entity] = {geometry_id, clearance_m, radius_m}` 由调用方声明同一几何／采样的净空，工具以平移误差加旋转表面位移界提示风险；它不独立认证该几何身份或净空。

Keyhole 可将 policy factory 路径设为 `adapters/keyhole_reference.py`，`kwargs` 沿用原 policy，简化变体增加 `simplified=True`；它包装原来的 `follow_bodies()`，在进度递增／lookahead 前捕获实际目标，不修改任务 policy 源码。未进入物体跟踪阶段时不生成参考。其他任务可直接实现上述方法，首版不提供任意时间插值 provider。

进程退出后可在不加载仿真的情况下分析：

```python
from topogym.planning.calibration_tools.tracking import read_tracking_report
report = read_tracking_report("runs/oracle_dev/example/tracking/<id>", valid_only=True)
```

离线读取能恢复已落盘 tick 的部分执行计数，并忽略末尾不完整 JSON；缺失的物理状态不会补造。策略参考游标仍依赖原有 `save_debug_state/load_debug_state`，generator 不会自动获得恢复能力。

## 规划结果缓存

```python
request = {"tcp_path": [targets], "phase": "approach"}  # targets 的格式同 solve_ik
tolerances = dict(
    joint_rad=.002, object_m=.0002, object_rad=.002,
    relative_m=.0002, relative_rad=.002, grasp_m=.0002, grasp_rad=.002,
    repair_multiplier=3., source="示例；运行前替换为当前任务的净空／误差预算",
)
prepared = dev.prepare_plan(request, adapter="keyhole_tcp", tolerances=tolerances)
decision = dev.check_cached_plan(prepared["plan_id"], tolerances, "keyhole_tcp")
# 仍由 policy 使用候选结果并产生标准 action；prepare_plan 不执行路线。
```

默认目录为 `runs/oracle_dev/plan_cache/`，上述三个方法均可传 `cache_dir`；长规划可显式传 `timeout_s`。条目用内容 SHA-256 标识，存 JSON manifest 与无 pickle 的 NPZ，原子提交并校验内容；损坏条目作为 miss，重新生成时原字节保留在 `.corrupt-*` 目录。`cache_plan(plan_bundle)` 接收 `identity`（geometry／joints／execution 三层）、`start`（qpos／objects／grasps／contacts）、`joint_names`、`qpos`、`request` 和 `coverage`；其他路线、阶段及对应关系字段由任务适配器保存。

`check_cached_plan()` 返回 `reuse`／`repair`／`seed_only`／`miss`、差异和原因；保存本身不授予复用资格。`prepare_plan()` 自动串起检查、预算内修正与完整规划，分别返回 `lookup_s`、`check_s`、`repair_s`、`plan_s` 和 `validate_s` 中实际执行的阶段。结果绑定当前 episode／branch／state 和抓持快照；推进物理或回溯后应重新检查。不会继承成功资格、改变控制模式或跳过 EE action 的公共 IK。

内置 `keyhole_tcp` 接收开发者给出的世界系 TCP 路点，复用已有原生 IK 求关节候选，按关节／手指步幅细分并检查接入段和连接处；它不自动搜索谜题解法。默认最多修正 8 个路点，超出 `max_repair_waypoints` 转完整规划。可选 `grasps={side: entity}` 必须对应实测 holding binding，持件随 FK 移动后重新做机器人、持件／环境及两件表面碰撞采样；`object_path` 与 TCP 路点一一对应，可复核物体目标。接触豁免使用显式 `allowed_contacts`（entity/link 对）和 `allowed_body_contacts`（实体对）。这属于原生网格采样检查，不提供连续几何证书、FEM 验证或物理解题证明；原生适配器的实机物理接入尚未验收。

其他任务传入 `{path, factory: "make_adapter", kwargs}`；factory 接收只读 `QueryContext`（inspect／solve_ik／check_robot_path／cancelled／source_identity），返回实现 `identity(request)`、`snapshot(request)`、`validate(bundle)`、`plan(request, seed=None)` 的适配器，可选 `repair(bundle, request)`。适配器声明非空 `required_coverage`；缺少要求的验证覆盖时只能 seed_only，不能直接复用。适配器负责将 `source_identity` 和自身算法版本纳入依赖；可信 Python 仍不是安全沙箱。

工具合同检查：`.venv-gs121/bin/python ci_checks/test-calibration-tracking-cache.py -v`；这些夹具检查只验证工具配对和调用流程，不调试 Task，也不代表真实物理验收。

## Policy、异步与局部恢复

策略脚本导出 `make_policy(**kwargs)`，返回实现 `act(observation)` 的对象。可选 `initialize(context)` 和 `on_segment_end(observation, result)` 与现有 runner 一致。脚本属于可信开发代码，不用于运行不可信模型生成代码。

```python
op = dev.run_policy(dict(path="/absolute/path/policy.py", factory="make_policy", kwargs={}),
                    max_control_steps=40, request_id="approach-v1")
print(dev.status(op))
result = dev.wait(op)
# 另一个调用方在运行期间可 dev.pause() 或 dev.cancel(op)。
```

限步／暂停产生 `cancelled` 段及明确 `development_stop_reason`，不伪装为 policy 自然结束或任务成功。同一脚本内容＋factory＋参数复用已初始化的策略对象。要支持带策略的检查点，策略须实现 `save_debug_state()`／`load_debug_state(state)`，保存路点进度、积分器及自己的随机数生成器等状态。只有 generator、没有显式状态的策略会被拒绝；`checkpoint(name, world_only=True)` 可只保存世界，恢复时丢弃已加载策略，须重新初始化。

worker 方法也可改用 `dev.submit("方法名", **参数)`＋`dev.wait(op)`；实时详细计时使用父进程的 `dev.timings()`，提交 `"timings"` 请求仍返回旧的操作级计时。一个 worker 同时只接收一个工作请求。`request_id` 相同且参数相同会返回既有回执；参数不同会报冲突。`wait(op, timeout_s=...)` 只是停止本次等待，操作仍可能在执行。操作本身超过预算后 worker 被终止，该请求记录失败，不自动重放不确定的半步。

`open_session(..., budgets={"startup_s": 300, "operation_s": 120, "render_s": 120, "policy_s": 600, "physics_step_s": 120})` 分别设置建场、普通操作、渲染、策略和单个 World tick 的墙钟上限。`physics_step_s` 从 `World.advance()` 进入时计时，嵌套阶段或心跳不会延长截止时间；它包括该 tick 内全部原生子步，不是每个 Newton 迭代的预算。建场内部未经过 `World.advance()` 的 IPC 原生 advance 也受同一上限约束。第一次编译也消耗墙钟预算，需要时显式提高。CPU 只监控；系统内存达到 90% 时终止本轮拥有的 worker，不停止其他作业。失败证据保留在输出目录。

## 分段计时、实时进度和失败窗口

诊断只在开发 worker 内临时包装现有调用，关闭时恢复方法；没有修改共享 Env、GenesisWorld、Task、正式 RPC 或物理配置，也没有复制物理步进循环。所有源码与测试均在本目录。

```python
op = dev.run_policy(policy_spec, max_control_steps=40)
print(dev.status(op)["progress"])  # 请求执行期间也有阶段、耗时和最后保存状态
print(dev.timings())              # 父进程统计，不向忙碌 worker 发送新请求
result = dev.wait(op)
```

阶段覆盖建场/资产、原生 IK、控制动作编译、World tick、solver、IPC 原生 advance/retrieve、状态回读、Task 更新、检查点、tick 证据写入、观测和按需渲染。后端不能包装的原生方法在 `capabilities().profiling` 中标记 `unavailable`。`ipc_native_advance` 能显示当前调用已经持续多久，但仍不提供内部 Newton 次数或收敛残差；连接位置残差不是 Newton 残差。

`timings()` 的 `seconds` 包含子阶段，`self_seconds` 扣除已计时子阶段；不能把所有 `seconds` 相加。计时采用主机单调时钟，保留引擎已有同步，不额外插入 GPU 同步，因此不是 GPU kernel 时间，异步工作的等待可能归到后续读取阶段。统计包含诊断通信开销。`operations` 可区分启动、截图及各次策略请求，未被执行的 IK/渲染阶段没有调用记录，不能据此推断其耗时为零。

父进程保存 `profile.jsonl`（逐阶段进入/退出）、`timings.json`（已完成统计与未完成阶段）和定期更新的 `progress.json`。进度分别列出最后完成 World tick、最后完成 IPC 原生帧、最后保存状态及已提交控制动作；完成物理计算不等于该步证据已经提交，状态引用也不等于跨进程可恢复的 checkpoint。

watch 在触发时先 fsync 保存 `event_window_triggered`，再尝试截图；后续样本以 `event_window_progress` 追加，最终仍有 `event_window`。带相机的 watch 现在拍摄触发边界，未录制的前窗仍只有数值。worker 超时/退出时，父进程输出 `failure_window.json`，包含最近最多 32 个已接收控制边界摘要、已落盘但未完成的 watch 窗口和最后进度。后窗不足明确记录，不生成失败后状态。逐 tick 的完整可读数值另见 `execution/private/physics_states.jsonl`；这不是 IPC 原生检查点，历史 IPC 重渲染仍未实现。

## IPC 性能探针

```bash
.venv-gs121-nyx/bin/python -m topogym.planning.calibration_tools.benchmark \
  --task slotted_post_ring --variation easy --warmup-steps 1 --steps 5 \
  --output runs/test_results/ipc_profile_slotted_01

.venv-gs121/bin/python -m topogym.planning.calibration_tools.test_observability -v
```

探针保持默认 25 ms 控制步、每控制步 10 个 2.5 ms World tick、每 tick 4 个 0.625 ms IPC 子步；不通过放大步长或放松求解条件提速。使用一个真实 SegmentRunner policy 段维持初始控制目标，默认单列第一步预热，随后报告每控制步及各阶段计时。普通控制步不取 RGB，首末关键帧按需走 Nyx/共享 RecordingSession；`--no-rgb` 可测显式纯物理路径。`benchmark.json` 列出完整配置、实际完成数、首次步与后续步、分项成本及关键帧录像。

这是初态保持的短程基线，不能代表夹持、挤压、穿槽等高接触阶段，也不证明任务成功。比较历史 9–20 s/step 前，需要对齐控制/物理步口径、任务变体、GPU/软件版本、RGB、历史存储、接触阶段及其他 GPU 负载。

本次扩展的 [验收汇总](../../../runs/test_results/calibration_ipc_profile_20261002_k74znuqy/summary.json) 保留源码快照、逐阶段轨迹、资源采样和全部失败尝试。新增 9 项 CPU 合同、原有 12 项合同和静态发布隔离检查通过。Slotted hard 的 v2 快照完成 1 个预热加 5 个测量控制步：后五步中位 26.26 s，平均 27.85 s；其中原生 advance 平均 21.37 s、状态/证据保存 5.31 s、状态回读 0.65 s。普通控制步不读取 RGB，首末 Nyx 关键帧另行保存。这是有其他 GPU 负载时的短程结果，不能据此给出相对历史的加速或退化倍数。

最终 v4 补充了保存内部的历史写入细分，以及原生帧有效性记录。其 GPU 正向复测未完成：Slotted/Rope 出现 `cudaErrorInvalidDevice` 原生初始化退出；完全不加载 calibration_tools 的原始 Env 对照也复现该错误。cu128 镜像对照另保留 Vulkan 初始化失败及无 RGB 时的原生 CUDA 失败。未诊断这些底层错误的根因，不把 v2 成功替代为最终 v4 或全部 IPC 任务的 GPU 验收。

## 命令行和验证

### 抓持解释、短程试验与参数对照

这三项属于 oracle 开发支持。`grasp_status("right")` 仅读取现有抓持管理器，不重新调用准入、取得或健康检查。每个条件返回 `value`、`threshold`、`margin`、`satisfied` 和读数来源；未知为 `None`。`reported_reason` 保留后端原始原因，`explanation` 补充已有读数可以支持的解释。`last_admission_sample`／`last_health_sample` 是后端最后一次检查的缓存，不冒充当前物理接触。assist 关闭时不能由其空状态判断纯摩擦抓取失败。

`watch` 和 `step_until` 新增 `grasp_acquired`、`grasp_lost`、`grasp_released`、`grasp_rejected`，支持 `{"name": "grasp_lost", "hand": "right"}`。原生抓持事件在每个 World tick 收集，按控制步汇总，因此一个控制步内先取得又失效仍保留两条事件。重复拒绝仅在原因变化时触发。事件身份包括 episode／branch／state／tick，写入 `events.jsonl`；原生求解子步内未上报的事件不补造。

短程试验接收已有 oracle 规划的动作，使用当前 `control_mode`。必需字段是 `hand`、`target` 和顺序固定的五个 `phases`：`approach`、`close`、`lift`、`hold`、`release`。每阶段使用非空 `actions` 列表，或 `action` 加正整数 `steps`。它从当前会话状态连续执行，不自动 reset、改物体位姿或合成通用抓姿。

```python
from topogym.planning.calibration_tools import open_session

# approach_actions、lift_actions 由任务 oracle 提供，均为当前控制模式的动作列表。
trial = dict(hand="right", target={"entity": "cord", "vertex_indices": material_region_indices},
    phases=[dict(name="approach", actions=approach_actions),
            dict(name="close", action={"right": {"gripper_position_m": .0105}}, steps=8),
            dict(name="lift", actions=lift_actions),
            dict(name="hold", action={}, steps=20),
            dict(name="release", action={"right": {"gripper_position_m": .027}}, steps=12)],
    criteria=dict(minimum_lift_m=.02, maximum_slip_m=.01, minimum_hold_s=.2),
    record_video=False)

# 放在 main guard 内；config、动作和材料区域来自当前任务。
with open_session(config, "runs/oracle_dev/grasp_01") as dev:
    print(dev.grasp_status("right"))
    dev.watch(["grasp_acquired", "grasp_lost", "grasp_rejected"], before_steps=3, after_steps=3)
    operation = dev.run_grasp_trial(trial, request_id="grasp-once")
    result = dev.wait(operation)
    print(result["metrics"], result["report"])
```

刚体 `target` 可直接写实体名，也可指定 `{"entity": "part", "link": "part_link"}`。软体可指定固定的材料顶点索引；省略索引时测整个软体的顶点质心，并明确记录这一口径。整个试验不重新选择“离夹爪最近”的顶点。提升量以提升阶段之前的位置为参考，持握滑移在 TCP 局部坐标中计算；持握判据使用实际物理时间和连续满足时长。FEM 保存参考材料边长比及可取得的原生体积比。

`status="completed"` 表示五段动作执行完毕；`metrics.criteria_passed` 单独表示所声明的提升／持握条件通过，`criteria_checks` 给出逐项结果。释放阶段记录下降量和 assist 事件，`physical_release_verified=False` 表示没有额外的接触分离认证。任务完成、真实接触力及正式资格不由这些读数推断。失败／取消保留 `grasp_trials/<id>/report.json`、逐 tick `samples.jsonl` 和共享执行证据；硬超时后的部分报告需结合会话失败回执读取。`record_video=True` 需要建场时开启 Nyx，使用共享 `RecordingSession` 录初态与控制边界，保留真实起点和采样身份。

参数候选可直接传给 `open_session(..., candidate=...)`；批量对照用独立入口，每个候选／seed 顺序创建并关闭一个新会话：

```python
from topogym.planning.calibration_tools import open_grasp_sweep, parameter_grid

grid = parameter_grid({
    "robot_material.coup_friction": [.1, .3, 1.0],
    "phase_actions.close.right.gripper_position_m": [.0105, .0115],
})
with open_grasp_sweep(config, trial, grid, "runs/oracle_dev/grasp_sweep_01", seeds=[0, 1]) as sweep:
    print(sweep.status())
    report = sweep.wait()  # 也可 wait(timeout_s=...) 或 cancel()
```

候选字段：`name`、`materials`、`primitive_masses_kg`、`robot_material`、`config`、`phase_actions`。`materials` 按实体指定摩擦／密度／FEM 材料参数，`primitive_masses_kg` 仅支持可动基本形状；`robot_material` 支持普通刚体 `friction` 与 IPC `coup_friction`。`config` 支持 `grasp_assist`（包括已有阈值和目标声明）、已有 `task_parameters`、`physics_dt_s`、`solver_substeps`、`control_decimation`。`phase_actions` 按阶段合并动作字段；若提升动作显式包含夹爪指令，应同时覆盖该阶段，工具不会猜测哪些动作需要修改。

候选参数在新场景声明时生效，退出建场作用域即恢复包装。附带冻结初态归档的任务不能直接更换材料／质量；会明确要求重建匹配归档。网格／URDF 的显式质量及未公开的网格旋钮也不做隐式替换。参数范围、模型支持和实际建场仍由现有声明／后端校验。没有新增 IPC 刚体辅助约束，也不修改正式任务默认值。

`sweep.json` 保存每个候选的配置、动作哈希、独立 episode、源码身份、结果／失败和实际材料读数；`comparison.csv` 汇总提升量、滑移、持握时长、体积比、耗时及录像路径。每个子目录沿用计时、资源和失败窗口。不同源码候选拒绝继续比较，超时或不支持的候选明确列出；`continue_on_error=False` 可在错误后停止。最多 128 次候选×seed 执行。更改控制周期会改变同样步数对应的物理时长，需结合配置和实测时长比较。

```bash
.venv-gs121-nyx/bin/python ci_checks/test-calibration-grasp-tools.py -v
.venv-gs121-nyx/bin/python ci_checks/test-calibration-grasp-physics.py \
  --backend cpu --output runs/test_results/grasp_tools_cpu_01
.venv-gs121-nyx/bin/python ci_checks/test-calibration-grasp-physics.py \
  --backend cuda --rgb --sweep --output runs/test_results/grasp_tools_gpu_01
```

最后两个命令是短程真实 Env 接口冒烟检查；它们验证试验执行和产物，不是任务抓取性能测试。

2026-10-02 工具验收：新增 16 项合同检查、原有 12 项会话检查与 9 项计时／事件检查通过；冻结源码上的 CPU 单次试验、两候选独立重建、摩擦值 `.3`／`.9` 实际建场读回、GPU/Nyx 四视角录像均通过。每次冒烟试验执行 7 个控制步／70 个 World tick；录像已检查解码、帧数及状态身份。完整记录见 [`validation.json`](../../../runs/test_results/calibration_grasp_tools_20261002_01/validation.json)，包含源码快照、最终合同补丁和各试验产物索引。验收没有声明成功夹起目标或找到最优摩擦值。

### 开发进程内的 IPC 诊断与材料候选

`ipc_diagnostics.IPCDiagnostics(env)` 对已建成的单环境 IPC 场景读取每个碰撞刚体的 Genesis／IPC 平移、旋转、仿射伸缩和同一组碰撞顶点的位置差；`sample()` 同时逐指返回关节名称、单位、指令、实际 qpos、控制范围、物理范围和越界量。ALOHA 的单指控制上限是 37 mm，物理滑轨上限是 41 mm；这两个数都不是双指净开口。`export_collision_meshes(new_directory)` 导出两侧实际指碰撞面 PLY。它不会把距离接近解释成实测接触力，也不会修正位姿或放宽原生保护。

必须在证据中标明采样阶段：IPC `couple()` 写回后与完整 `env.step()` 返回后的 Genesis 状态可能不同；Genesis 1.2.1 的刚体积分位于 `substep_post_coupling()`。现有 2 mm 保护发生在前一个阶段，且只检查平移；诊断应同时覆盖控制步边界，不能用写回瞬间的误差代替操作接口所见误差。

`material_trials.candidate_spec(spec, materials=..., primitive_masses_kg=...)` 返回独立 TaskSpec 和参数差异，可对照刚体 `friction`／`coup_friction`／`rho`、FEM `E`／`nu`／`rho`／`friction_mu`。显式质量目前仅支持可动 box／sphere／cylinder，通过体积计算密度；网格／URDF 的质量惯量需另行重建，歧义输入会拒绝。每个候选必须重新建场，并保存实际质量、接触对系数和新的证据身份。

机器人 IPC 摩擦可在独占开发进程内用 `with material_trials.robot_coupling_friction(1.0): env.reset(seed=0)` 声明候选；该上下文仅临时包装建场器，退出后恢复，不用于并发建场或修改存活求解器。Genesis 1.2.1 的接触对取几何平均：机器人 `coup_friction=0.1`、绳 `friction_mu=0.3` 对应约 0.1732。改普通 `friction` 不等于改 IPC 摩擦。

诊断模块函数仍由可信 owner 直接使用；材料候选已接入 `open_session(..., candidate=...)` 和 `open_grasp_sweep` 的新建场流程。候选不会写回正式材料默认值。数值合同检查为 `ci_checks/test-ipc-development-diagnostics.py`，实际物理证据需单独运行。

```bash
.venv-gs121/bin/python -m topogym.planning.calibration_tools smoke \
  --kind geometry --variation easier --output runs/oracle_dev/geometry_smoke_01

.venv-gs121-nyx/bin/python -m topogym.planning.calibration_tools smoke \
  --kind physics --backend cuda --rgb --variation very_easy --steps 3 \
  --output runs/oracle_dev/physics_smoke_01

.venv-gs121/bin/python ci_checks/test-calibration-tools.py -v
.venv-gs121-nyx/bin/python ci_checks/test-calibration-physics.py \
  --variation easier --backend cuda --rgb --output runs/test_results/calibration_easier_01
bash ci_checks/check-calibration-isolation.sh
```

CLI 的 `script --commands commands.json` 顺序调用 JSON 数组中的 `{ "method": "...", "params": {...} }`；`--config config.json` 接收完整 SimulatorConfig 字段，`--candidate candidate.json` 接收开发候选及可选 `object_drives` 声明。

本轮新增支持的工具检查入口为 `PYTHONDONTWRITEBYTECODE=1 .venv-gs121-nyx/bin/python -B -m topogym.planning.calibration_tools.test_support -v`，覆盖状态解释、忙碌时查询、运行对照、接触／表面距离、外力边界和清理；它不运行完整 Task 或证明 GPU 物理成功。本轮代码、测试和说明只改本目录。

正式隔离检查可加 `--artifact <wheel或sdist>`、四个角色的 `--limited-image`／`--privileged-image`／`--sim-image`／`--verifier-image`、`--require-images` 和实际容器的 `--container`。未提供的运行环境记为 `not_verified`。不把本机基镜像检查当成所有未来部署挂载都已检查。

## 交付和证据边界

接口、worker、supervisor、适配器均在本目录。目录外仅增加发布排除、CI 与验收脚本，以及 Env 的可选 owner `sensor_factory`；默认构造仍用原 SensorSuite。没有修改物理步进、任务判据、正式 Interaction、PrivilegedAccess 或 Harbor RPC。

`pyproject.toml` 排除该包，`MANIFEST.in` 排除源码包中的该目录，现有正式镜像规则排除整个 planning。私有 pipe 仅由开发父进程传给 worker；没有监听端口或可供模型发现的控制 socket。源码位置检查和会话身份是误用保护，不能充当任意 Python 同进程沙箱。

运行目录包含 `session.json`、`source_manifest.json`、`operations/`、`events.jsonl`、`resources.jsonl`、`worker.log`、`report.json`，以及按需出现的 `execution/`、`frames/`、`probe_*/`。直接编辑／人工抓持／建模预览标记探索运行；回溯不清除标记。所有报告固定 `formal_qualification=False`，正式成功需普通 runner 从原初态连续执行另行验收。
