# Buzz Wire 3D policy 与实际验收

当前范围是注册的 `buzz_wire_3d_easy` / `medium` / `hard`，默认参数、seed 0。
**已通过实际成功与独立审计 1/3：easy；medium / hard 仍在验证。**
easy 的本次证据为
[`buzz_easy_continuous_20260929_02`](../../../runs/test_results/buzz_easy_continuous_20260929_02/)：
从默认 home 连续执行 211.55 秒，共 8463 个状态，无回溯、无工具触线、无机器人触线，
原生 Task 在工具释放并稳定后成功。见该目录的 `run_report.json` 和
`independent_audit.json`。三个变体的统一归档尚未完成；旧的有回溯开发成功不计数。
2026-09-29 会话中断后，medium / hard 的第二轮进程已结束，分别保留到
228.775 s / 792.100 s，未取得最终成功。数值日志不能当作可恢复的物理 checkpoint；
它们的 `interruption_status.json` 记录这一范围，不能称为仍在后台运行。

## 关键姿态与夹持证据复核（2026-09-29 后续）

按最新验证范围，复用已有物理执行，只补当前场景的少量关键姿态检查，不生成视频。
结果见 [`buzz_fast_feasibility_20260929_01`](../../../runs/test_results/buzz_fast_feasibility_20260929_01/README.md)：

- easy / medium / hard 各 14 个 route point 的完整位置＋朝向 IK、关节限位和采样碰撞间隙均通过，共 **42/42**；本轮零新增物理 tick。
- 旧记录中分别核对到 **4 / 2 / 5 次**双指接触建立、随后释放的 `contact_weld_v1` 辅助夹持；medium 的回溯不重复计数。两份 easy 成功审计及全部 17126 个数组块哈希匹配。
- medium 已有无回溯走线前缀及后续成功释放分支，最后偏离目标 **8.8 mm / 42.3°**，终点修正抓取未通过。hard 最后位置误差 **0.051 mm**，朝向仍偏 **25.4°**。两档完整 Task success 仍未取得。
- 当前碰撞资产与旧执行匹配，源码差异单列；旧物理证据不改标为当前源码的新完整执行。关键点检查不覆盖点间路径、自碰撞和释放动力学，不扩大到其他 seed。

后续局部执行使用 **`history_storage="segment"`**：episode 起点与分段起点保存完整 checkpoint，其他 tick 保留轻量记录。
旧 staged 输入显式写了 `memory`，不要直接沿用；本次另存了
[`continuation_configs/`](../../../runs/test_results/buzz_fast_feasibility_20260929_01/continuation_configs/)
三份 segment 配置，原执行配置保持其历史身份。资源监控每秒采样，达到 90% 暂停本轮工作进程；本轮内存峰值 28.8%，CPU 触发暂停后已恢复并完成。

## 分段可解性验证（2026-09-29）

`stages.py` 把一局 Buzz 拆成若干段，交给通用的分段流程 `topogym/planning/solvability.py` 执行（流程说明见上级 `planning/README.md`）。每段只包装现有的 `BuzzWirePolicy` part 或 `recipes.py` 函数，并在该段的实际起点重新规划。

**每段的检查：**
- **每个 tick 都查：** 接触统计完整；工具金属与导线金属无接触（Task 判失败的条件）；机械臂与导线金属无接触（Task 不判，这里判）；Task 未失败。
- **持工具的段：** 每个 tick 都要求抓持状态是 `holding`。
- **走线段：** 每个 tick 还要求 Task 的 `traversal_tracked` 为真。中途丢失追踪后无法恢复，因为 Task 只接受在导线起点 10 mm 内重新开始。
- **每段结束时：** 按类型检查结果，例如"抓到并有双指接触证据""已脱手且被木台支撑""Task 成功"。
- **时长上限：** 约为旧运行中同一段实测仿真时长的 2 倍，超过即判失败。

**easy：从 home 零回溯成功，独立审计通过。** 证据在 [`buzz_staged_easy_20260929_01`](../../../runs/test_results/buzz_staged_easy_20260929_01/)。
- 11 段依次为：抓起 → 换抓 → 走线 → 终点上方摆平 → 松手落台 → 抓取 → 转向 → 部分松手 → 抓取 → 转向 → 松手静置。
- 仿真 216.55 s，共 8662 个普通关节 action。
- 最终离目标 3.6 mm、5.74°，已松手、静止。
- `independent_audit.json` 记录：8663 个状态，工具触线 0，机械臂触线 0，接触统计完整，关节离限位最近 0.057 rad。
- 与已验收的 `buzz_easy_continuous_20260929_02` 不同，这次全程都是按观测反馈执行，没有重放开发阶段编译出的动作前缀。
- 墙钟共 52 min，含 1 min 55 s 规划；当时机器负载为 13–30，每 tick 约 0.24–0.35 s。这次零回溯，所以本身就是连续执行证据，不需要再跑一次正式执行。

| 段 | 仿真 s | 墙钟 s | 规划 s |
|---|---:|---:|---:|
| 抓起 | 17.08 | 205 | 0 |
| 换抓 | 33.78 | 385 | 0 |
| 走线 | 74.10 | 1040 | 65.1 |
| 终点上方摆平 | 6.23 | 145 | 0 |
| 松手落台（离目标 60.6°） | 9.20 | 184 | 0 |
| 抓取 1 | 25.80 | 298 | 9.2 |
| 转向 1（转到 23.8°） | 12.05 | 169 | 14.4 |
| 部分松手 | 5.60 | 82 | 0 |
| 抓取 2 | 22.65 | 316 | 6.7 |
| 转向 2（转到 5.7°） | 7.98 | 135 | 23.2 |
| 松手静置 | 2.10 | 24 | 0 |

**终点目标朝向。** `recipes.checked_turn` 的 `yaw` 是工具姿态 Rz(yaw)·Ry(−pitch)·Rx(180) 里的航向角。按 Task 的角度判据（含绕手柄轴 180° 对称）逐 0.5° 扫描，离终点姿态最近的 yaw 为：easy 168.5°，medium 146.5°，hard 174.5°。

运行方式（每次用新的输出目录）：

```bash
.venv-gs121/bin/python scripts/run_solvability_workflow.py --mode diagnostic \
  --config runs/test_results/buzz_fast_feasibility_20260929_01/continuation_configs/easy.json \
  --stage-factory topogym.planning.buzz_wire_3d.stages:stages \
  --output runs/test_results/<new_run>
.venv-gs121/bin/python scripts/audit_buzz_wire_policy.py runs/test_results/<new_run>
```

## 少量关键姿态的连接

`keyframes.py` 支持按实际场景简化规划。`resolve_keyframes` 用一次 unlimited
观测中的 entity 位置和朝向，把相对关键姿态转换到世界坐标；每个关键姿态同时包含
位置与四元数。`connect_held_guide` 优先直接连接起终姿态，只有 IK 或沿途碰撞检查
失败时，才从已有引导路线补入中间点。`mandatory_indices` 保留任务必须经过的关卡。

连接检查覆盖工具、整条机械臂及当前夹爪与导线／底座的间隙，并再次加密检查关节
插值产生的工具运动；沿用 BuzzIK 的碰撞对象范围，没有新增独立的机器人自碰撞审计。
关键姿态少不代表只检查端点；执行时仍输出连续普通 action。
每段限定为同一次抓持，换抓之后必须从新观测重测抓持变换，释放动力学单独验收。
这不是整个 Task 的成功证书，也不把有限采样扩大为连续时间碰撞保证。

真实场景的分段只读验证保存在
[`buzz_sparse_keyframes_20260929`](../../../runs/test_results/buzz_sparse_keyframes_20260929/README.md)：
每档各取一个已有的固定抓持终点片段，easy 的 570 个参考姿态连接为 2 个关键姿态，
medium 的 4459 个连接为 6 个，hard 的 1423 个连接为 7 个。三段均通过只读检查，
不是三条完整任务路径，也不增加上面的物理成功数量。

## 反馈执行与物理验收

`policy.py` 是接收观测、返回单条 `EE_ABS` action 的脚本 policy。它使用明确授权的
unlimited 世界状态，不持有 Env，不覆盖物体／机器人状态，也不重放历史关节角。
`kinematics.py` 在管理侧用当前 Genesis IK/FK 和导入的完整凸碰撞表面生成候选。
默认通过 `CheckedJointPolicy` 把笛卡尔目标转为普通 `JOINT_ABS` action，保留
空手避障规划选择的冗余关节分支；也可显式选择原生 `EE_ABS` 编译。
`joint_reference` 阶段可沿已检查的关节曲线执行普通关节 action，避免两个可达姿态间的
笛卡尔插值离开工作空间；其工具参考姿态由同一关节曲线的 FK 得到。
抓持后等待夹爪被动关节的实测速度收敛。easy 最后换抓的 0.45 rad 预闭合状态会出现
被动关节振荡，因此空手规划同时检查当前几何和一份已实测的被动关节形状；这只是
只读碰撞包络，不向机器人写入这些状态，也不把有限采样称为连续几何保证。
`stop_after_transfer` 可只执行已规划的空手撤离，不进入闭爪阶段；可选的
`free_tool_motion_limit_m` 会在工具位姿变化超过给定限值时停止继续发出动作。
这项监测用于已经静止的释放工具；有意让工具在重力下落稳的阶段单独验证。
换抓接近默认在原生双指接触进入 registered / holding 后停止继续推进，并重新测量
实际抓持变换；预闭合夹爪在接近中建立抓持时，也不会继续推向原来的空手目标。

流程：默认 home → 接近手柄 → 双指接触触发抓持 → 抬起 → 转向并放回底座 →
释放、撤手、从手柄外端重新抓持 → 实测抓持变换 → 搜索环的 roll 与倾角 →
反馈走线 → 终点对准、释放、由重力沿末端直柱落到底座 → 撤手与静止验收。
规划先搜几何／IK，再加密检查插值；实际触线、进度、支撑和最终 success 由 Task 判定。

为减少耗时，runner 默认 CPU 双精度、无 RGB、无视频，保留冻结源码、配置、资产身份、
全部 action 与逐 tick 状态。显式使用 25 ms World tick、40 子步、40 Hz action，积分
子步仍为 0.625 ms；这不同于默认 400 Hz Task/assist 检查。使用 `contact_weld_v1`
辅助抓持，必须先实测双指接触，释放后才允许 success。不能称为纯摩擦抓持资格。

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv-gs121/bin/python \
  scripts/run_buzz_wire_policy.py --variant easy \
  --output runs/test_results/buzz_easy_new

.venv-gs121/bin/python scripts/audit_buzz_wire_policy.py \
  runs/test_results/buzz_easy_new
```

将 `easy` 替换为 `medium` / `hard`，每次使用新的输出目录。`--part pickup` / `regrasp`
仅用于定位前置动作问题，即便 runner 报 `passed`，也不代表完整 Task success。
正式收录须有 `run_report.json` 中 `task_success=true` 和独立审计 `passed=true`。
无视频的数字证据不是完整引擎 checkpoint，不能据此承诺日后可以任意续跑或重渲染。
局部开发可在同一个存活 Env 内使用公开 rewind 接口；这类有分支的试验只作诊断，
最终仍须从默认 home 连续执行一次无回溯 policy，再独立审计。

`compile_buzz_wire_actions.py` 可沿成功开发状态的父状态链提取普通关节目标，
检查从 birth 开始的逐 tick 连续性。`compiled.py` 只逐条提交这些 action，
不恢复历史状态。将其 JSON 交给 runner 的 `--compiled-actions` 可省去正式重跑的
重复搜索；新 episode 仍执行所有物理步骤并重新判定 success。独立审计明确区分
“开发阶段查询 IK 后编译的动作”与“本轮在线查询 IK”。开发记录本身仍不算证明。
`--feedback-finish` 在 easy 的已检查抓持前缀之后使用 `recipes.py`：释放后重测工具
姿态，再规划两次换抓和反馈放置。当前整理版来自本次通过审计的分段提交，已用该次
实际观测完成七个阶段的只读规划重建；整理后的单入口尚未另做一次完整物理重跑。
纯动作回放已观察到毫米级落点偏差，不能假定释放后的
状态会逐位重现；两种执行方式均只按新 episode 的真实结果验收。

本次必要的判据修复保留原几何与阈值：凸网格导入重定位后的接触角色匹配；完整遍历事件
在降到金属线末端以下后保留；环、杆与矩形手柄绕柄轴 180° 的物理对称性。Task terminal
修订为 `terminal_v4_traversal_then_deck_release`，新结果不能覆盖旧修订的证据。
