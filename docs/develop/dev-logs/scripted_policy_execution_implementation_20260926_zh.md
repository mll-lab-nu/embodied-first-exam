# Scripted policy 调度与方块 rollout 实施记录

日期：2026-09-26。状态：**本地实现及本轮真实验收完成。** 计划见[工程计划](../modules/scripted_policy_execution_plan_20260926_zh.md)，用法见[本地 API](../modules/simulator_api_zh.md)。

## 已实现

- 执行模块迁入 `simulator/rollout_simulation/`，根层 SegmentRunner 惰性导出不变；基础 Interaction 的 public_info 不依赖段执行模块。
- 管理方 `run_policy()` 持有 segment 与 step。policy 只实现 `act(obs)`，返回 mapping／None；初始化与结束通知可选。终态、异常、幂等和证据仍沿用原段执行路径。
- limited 同时提供关节、TCP、夹爪与配置 RGB；固定相机标定按公开名单选择；Task、物体真值、腕部标定、控制器目标和 reward 不混入 actor obs。unlimited 显式选择额外状态。
- 同状态本体缓存复用 SensorSuite 的一次测量；policy 初始化、投影和结束通知不推进物理。`obs.execution_state` 区分执行结果与任务是否达成。
- `planning/examples/cube_pick_place.py` 提供实际动作样板。原位与搬运各有独立测试判据；原来的搬运距离标准未放宽。
- 新入口 `scripts/test_scripted_policy_rollout.py` 分配 `task_rollouts/<experiment_content>_<experiment_date>/<task_name>/rollout_<编号>/`，先冻结源码与参数身份，再在独立进程执行，保存真实 RGB、视频和日志。失败编号不会被覆盖。

## 验证记录

迁移阶段原 segment／产物／录制回归：30 项通过。接入后合同、录制、架构和 Task 状态测试：151 项通过、1 项按标记排除；这些是确定性测试与编码检查，不代替真实物理。

最终相关冻结源码 CPU 集合共 **189 项通过、1 项按标记排除**（合同／录制／架构／Task 状态／控制规格／配置／机器人描述）。报告保存在 `cube_transfer/rollout_0002/contract_junit.xml`。先前的 30、151、186 项结果是阶段性重叠集合，不能相加。追加覆盖观测读取失败后的过期末步通知和 RGB 子集／无相机时的媒体边界。

首个原位样例 `cube_pick_place/rollout_0001` 已通过：453 控制步／453 tick、11.325 s 仿真，抬离桌面 8.34 cm，放回误差 0.104 mm。单段搬运 `cube_transfer/rollout_0001` 已通过：515 控制步／515 tick、12.875 s 仿真，空中横移 20.08 cm，放置误差 0.326 mm。两者均由独立 Task 判据确认持稳、释放、撤离和落桌稳定 0.5 s。

同 seed 两段搬运 `cube_transfer/rollout_0002` 已通过：第一段 289 控制步后 policy_done，第二段 226 控制步后 env_terminal。总 tick 仍为 515，初始物理状态哈希与单段相同；段 1 末帧和段 2 首帧的三个 PNG 哈希逐视角一致，边界不推进物理。

空抓对照 `cube_transfer/rollout_0003` 已通过负例验收：290 步后 policy_error，私有原因明确为 `Reference policy failed to lift the cube`；held_once／task_success 均为 false。不能将任意 policy_error 当作空抓通过，离线验收额外核对了实际阶段与具体失败原因。空夹爪闭合存在左右指尖的正常接触（最大记录穿透 0.0089 mm），与手臂碰桌或非预期自碰分开。

limited 短闭环 `cube_transfer/rollout_0004` 已通过：`enable_privileged=False`，8 控制步／80 个默认 2.5 ms tick／0.2 s；移动目标只由初始 TCP 加 5 mm 得出，最终实测误差 0.666 mm。输入断言覆盖三路 RGB、关节／TCP／夹爪、仅两台固定相机标定与无 privileged 字段。此例以 policy_done 正常结束，Task 未成功，不能计为 limited 抓取解题。

各例位于 `task_rollouts/scripted_policy_pick_place_20260926/`，初始报告和源码快照先于建场景生成。已完成例的离线检查核对源码及媒体哈希、连续 tick／控制步／段边界和末帧身份，并确认实测初态等于 home、手臂关节未越限、成功样例记录中的机器人接触只有夹爪—方块。接触审查是保存 tick 上的检查，不代表所有求解器子步均单独存档。

长程示例使用显式 `physics_dt_s=.025 / control_decimation=1 / solver_substeps=40`，控制 40 Hz、内部求解子步 .625 ms；不改变 SimulatorConfig 默认值，也不宣称默认 2.5 ms tick 的完整长程资格。真实渲染使用 Genesis + Nyx + compact_lab、Panda 的 agentview/front_oblique/wrist 三视角，848×480、录像 30 fps，从默认 home 连续执行。

## 最终真实验收矩阵

**9 项真实验收通过：7 次完整任务成功、1 次空抓负例、1 次 limited 短闭环。** 合计 10 个 segment、40 份对外 MP4（各段三视角与拼屏；共享录制工作目录中的同哈希副本另存）。所有本轮核心实现共 13 个 Python 文件在各运行快照与最终工作树中哈希一致；测试驱动和其他文件以各自 `run_source_manifest.json` 为准。未将其他生产 Task 或默认时序的完整搬运算入资格。

| 用例 | 目录／完整报告 | 控制步 / tick | Task 成功 | 验收结果 |
|---|---|---:|---|---|
| 原位抓起放下 | [cube_pick_place/rollout_0001](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/run_report.json) | 453 / 453 | 是 | 通过；放置误差 0.104 mm |
| 搬运 seed 0 | [cube_transfer/rollout_0001](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/run_report.json) | 515 / 515 | 是 | 通过；放置误差 0.326 mm |
| 两段连续搬运 seed 0 | [cube_transfer/rollout_0002](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0002/run_report.json) | 515 / 515 | 是 | 通过；放置误差 0.326 mm |
| 空抓负例 | [cube_transfer/rollout_0003](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0003/run_report.json) | 290 / 290 | 否（预期） | 负例通过 |
| limited 默认时序短闭环 | [cube_transfer/rollout_0004](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0004/run_report.json) | 8 / 80 | 否（预期） | 闭环通过 |
| 搬运 seed 1 | [cube_transfer/rollout_0005](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0005/run_report.json) | 514 / 514 | 是 | 通过；放置误差 0.493 mm |
| 搬运 seed 2 | [cube_transfer/rollout_0006](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0006/run_report.json) | 515 / 515 | 是 | 通过；放置误差 0.407 mm |
| 搬运 seed 3 | [cube_transfer/rollout_0007](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0007/run_report.json) | 515 / 515 | 是 | 通过；放置误差 0.283 mm |
| 搬运 seed 4 | [cube_transfer/rollout_0008](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0008/run_report.json) | 514 / 514 | 是 | 通过；放置误差 0.572 mm |

机器可读汇总见 [validation_summary.json](../../../task_rollouts/scripted_policy_pick_place_20260926/validation_summary.json)。每个 rollout 内保留 `run_report.json`、`offline_audit.json` 及可复跑的 `offline_audit.py`，包括源文件、媒体 SHA-256、连续 tick／控制步、段边界、末帧与已存完整解码检查。成功案例放置误差为 0.104–0.572 mm；全部记录中的最小手臂关节限位余量约为 0.574 rad，最大记录刚体穿透 0.755 mm。接触检查覆盖保存 tick，不声称逐求解器子步或 actuator force 全覆盖。

## 可直接查看的视频

| 样例 | 拼屏 | 外部 agentview | 外部 front_oblique | 腕部 wrist |
|---|---|---|---|---|
| 原位抓起放下 | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/views/agentview/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/views/front_oblique/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_pick_place/rollout_0001/views/wrist/segment_1.mp4) |
| 约 20 cm 搬运 | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/views/agentview/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/views/front_oblique/segment_1.mp4) | [MP4](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0001/views/wrist/segment_1.mp4) |

两段连续例分别为[抓起并持稳](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0002/segment_1.mp4)、[搬运并放下](../../../task_rollouts/scripted_policy_pick_place_20260926/cube_transfer/rollout_0002/segment_2.mp4)，来自同一次未重置的连续物理运行。

## 执行命令

```bash
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --experiment scripted_policy_pick_place_20260926 --case pick_place --seed 0
# 原位例 + 搬运 seeds 0–4 + 两段连续 + 空抓负例；串行新进程执行。
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --experiment scripted_policy_suite_20260926 --suite
# limited 短程反馈，显式使用库默认物理 tick；不读取物体真值。
.venv-gs121-nyx/bin/python scripts/test_scripted_policy_rollout.py \
  --experiment scripted_policy_limited_20260926 --case limited \
  --physics-dt .0025 --control-decimation 10 --solver-substeps 4
```

库默认时序可显式传 `--physics-dt .0025 --control-decimation 10 --solver-substeps 4`；完整每 tick checkpoint 的内存和墙钟开销仍存在。本轮不加入段预算、历史淘汰、模型 API、源码上传沙箱、VLA 模型或 RL 训练器。样板需要物体 world 真值，不能称为 limited 的视觉解题成功。
