# Buzz Wire 3D policy 与实际验收

2026-10-04 Harbor 默认三档入口已改为显式选择完整参考：easy 使用
`buzz_staged_easy_20260929_01` 的 11 段反馈 selection；medium / hard 使用下表两次
已审计执行的全部 29,544 / 43,568 个普通关节动作，包含末端转正、释放和停稳。
实现见 [reference_policy.py](reference_policy.py)，数据位于私有
`harbor_bridge/reference_data/buzz_wire_3d/<tier>/`，默认 `public_session` 不再进入
通用在线搜索分支。历史 medium traverse guide 仅保留给显式开发配方。

每档 `recipe.json` 记录源报告／审计 SHA-256、输入 SHA-256、布局与初始机器人姿态。
运行前检查 fresh Session、seed 0、Panda/Robotiq、JOINT_ABS、辅助抓持、布局与 25 ms
控制周期。Harbor 的物理步长、降采样、后端和精度保持冻结值；例如 2.5 ms × 10
可以执行同一 25 ms 动作序列，但不继承历史 CPU64／40 子步的成功资格。
报告写入 `reference_report.json`，必须以当前 Task success 判断执行是否完成；
最终成绩仍由 Harbor verifier 给出。

本机 NVIDIA 驱动不可用，未执行本次完整 GPU grading。提交代码及新增参考文件后，
lab 从新 checkout 和新输出目录执行（沿用其 `TOPOGYM_PYTHON` / `TOPOGYM_HARBOR`）：

```bash
"$TOPOGYM_PYTHON" ci_checks/check-oracle-portability.py --families buzz_wire_3d --check-git
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output runs/test_results/harbor_buzz_complete_reference_01 \
  --families buzz_wire_3d --tiers easy,medium,hard --gpu 6
```

使用新的候选任务与镜像源码身份；旧 `solution/` 或 `--resume` 不会自动切换策略。
very_easy / easier 不在该三档 sweep 中，继续使用各自的简化策略入口。

2026-10-03：原 medium / hard 均已从默认 home 连续完成原生 Task，并通过独立审计。
Medium 使用用户批准的 `F2_terminal_xy40_20_deck_rest_v1` 布局，hard 布局保持原值。
两档完整接触记录中工具和机器人触线均为 0，正式运行通过导入拦截确保没有加载 calibration tools。
生产策略 [compiled.py](compiled.py) 只逐 tick 输出已检查 IK 解对应的关节动作，不恢复仿真状态。
开发中使用的回溯仅用于寻找候选；成功资格来自另起的一局无回溯执行。

| 变体 | 动作数 / 仿真时长 | 最终位置 / 角度误差 | 动作、源码与审计归档 | 三路 Nyx 视频 |
| --- | ---: | ---: | --- | --- |
| medium | 29,544 / 738.600 s | 2.036 mm / 3.466° | [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-10-03_medium_v12_continuous/archive_manifest.json) | [全景](../../../demos/buzz_wire_3d/varaition_medium/agentview/varaition_medium_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_medium/front_oblique/varaition_medium_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_medium/wrist/varaition_medium_wrist.mp4) |
| hard | 43,568 / 1089.200 s | 4.466 mm / 8.982° | [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-10-03_hard_v12_continuous/archive_manifest.json) | [全景](../../../demos/buzz_wire_3d/varaition_hard/agentview/varaition_hard_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_hard/front_oblique/varaition_hard_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_hard/wrist/varaition_hard_wrist.mp4) |

录像为 RTX 4090 上按全部原始关节状态重渲染，848×480、30 fps；
完整连杆位姿核对、视频解码、同步与归档副本哈希检查均通过，不增加物理成功次数。
两档补齐后，原 easy / medium / hard 各自冻结实例的完整成功证据为 **3/3**。

```bash
BUZZ_VARIANT=medium
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_buzz_wire_policy.py \
  --variant "$BUZZ_VARIANT" --seed 0 --v12-performance \
  --compiled-actions "runs/demo_metadata/buzz_wire_3d/2026-10-03_${BUZZ_VARIANT}_v12_continuous/execution/policy_actions.json" \
  --output "runs/test_results/buzz_${BUZZ_VARIANT}_recheck"
.venv-gs121-nyx/bin/python -m topogym.planning.buzz_wire_3d.audit \
  "runs/test_results/buzz_${BUZZ_VARIANT}_recheck"
```

将 `BUZZ_VARIANT` 改为 `hard` 即可执行另一档；输出目录须尚不存在。
入口会重新冻结执行源码，并报告与候选物理源码的差异；
归档内的 `execution/source_snapshot/` 保留本次实际验收的版本。
上述资格只覆盖冻结 seed 0、CPU64、25 ms / 40 子步 / 单 tick 控制及
`contact_weld_v1`；`--v12-performance` 从建场启用全局刚体求解和目标触发静止检查。
其他 seed、纯摩擦抓持及 Harbor 默认时序不继承此次结果。

2026-10-02 新增两档的规划实现 [simplified_policy.py](simplified_policy.py)。
`SimplifiedBuzzOracle.stages()` 根据每段开始时的实际状态，依次规划默认 home 抓取、换抓、
完整走线、低位释放和终点摆正。`make_stage_policy()` 将阶段参数转换为普通机器人关节 action；
不需要已有 run、保存的物理状态或历史动作文件。只读 IK / 碰撞检查沿用当前 easy 的实现，
工具尺寸、初态、接触判据与成功阈值均由场景提供。

运行入口负责源码冻结、`Env` / `SegmentRunner` 执行及证据记录：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_buzz_wire_simplified_policy.py \
  --variant very_easy --seed 0 --no-rgb --output runs/test_results/buzz_very_easy_new
.venv-gs121-nyx/bin/python -m topogym.planning.buzz_wire_3d.audit \
  runs/test_results/buzz_very_easy_new
```

将 `very_easy` 换成 `easier`，并使用新的输出目录，即可选择另一档。
入口默认 **CPU 64 位、25 ms tick、每 tick 一次控制、40 子步**，使用双指接触触发的
`contact_weld_v1` 辅助抓持。`--no-rgb` 只关闭图像；完整动作与逐 tick 物理证据仍保留。
开启 RGB 需要 Nyx / CUDA。该开发时序与任务包默认 2.5 ms / 10 倍降采样 / 4 子步不同，
不能直接继承 Harbor 正分资格，也不代表纯摩擦抓持或其他 seed 已通过。

[audit.py](audit.py) 独立核对出生到终点的连续谱系、普通 action 覆盖、完整刚体接触报告、
工具/机器人无触线及原生 Task 成功；兼容已无损压缩的历史 JSONL。
`--prefix-run` / `--replay-run` 是显式开发选项，常规 oracle 不使用它们。
布局、两档实测结果与任务包资格见 [任务页](../../../docs/develop/tasks/buzz_wire_3d_zh.md)；
下文三档历史成功数量不包含这两个新变体。新版 very_easy / easier 的 seed 0 均已从 home 无回溯完整成功（262.8 s / 290.875 s），独立审计确认无工具或机器人触线。

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

下文为截至 2026-09-29 的历史记录，覆盖 `buzz_wire_3d_easy` / `medium` / `hard`，默认参数、seed 0；10 月 3 日补齐的结果见本页开头。
**关键姿态与历史走线夹持检查 3/3；含终态动作的分段证据 2/3（easy、hard）；连续完整 Task 成功与独立审计仍为 1/3（easy）。**
最新结果见 [`buzz_three_tier_component_proof_20260929_01`](../../../runs/test_results/buzz_three_tier_component_proof_20260929_01/README.md)。
Hard 新补的局部转正、释放和静置通过，最终误差 **0.057 mm / 8.146°**，持续满足终态 **5.95 s**。
Medium 的终态转正仍未通过；三档完整可解性不能标为全部通过。
局部实验将历史工具静置姿态作为显式初态，机器人从默认 home 开始；历史走线与局部实验的机器人状态没有连续衔接，不能计作新的完整 Task 成功。
本轮仿真和查询进程均已退出。使用 `segment` 检查点，无视频；达到 90% 内存或 CPU 使用率时暂停本轮进程。

easy 的本次证据为
[`buzz_easy_continuous_20260929_02`](../../../runs/test_results/buzz_easy_continuous_20260929_02/)：
从默认 home 连续执行 211.55 秒，共 8463 个状态，无回溯、无工具触线、无机器人触线，
原生 Task 在工具释放并稳定后成功。见该目录的 `run_report.json` 和
`independent_audit.json`。三个变体的统一归档尚未完成；旧的有回溯开发成功不计数。
2026-09-29 会话中断后，medium / hard 的第二轮进程已结束，分别保留到
228.775 s / 792.100 s，未取得最终成功。数值日志不能当作可恢复的物理 checkpoint；
它们的 `interruption_status.json` 记录这一范围，不能称为仍在后台运行。

## 关键姿态与夹持证据复核（2026-09-29，终态局部实验之前）

按最新验证范围，复用已有物理执行，只补当前场景的少量关键姿态检查，不生成视频。
结果见 [`buzz_fast_feasibility_20260929_01`](../../../runs/test_results/buzz_fast_feasibility_20260929_01/README.md)：

- easy / medium / hard 各 14 个 route point 的完整位置＋朝向 IK、关节限位和采样碰撞间隙均通过，共 **42/42**；本轮零新增物理 tick。
- 旧记录中分别核对到 **4 / 2 / 5 次**双指接触建立、随后释放的 `contact_weld_v1` 辅助夹持；medium 的回溯不重复计数。两份 easy 成功审计及全部 17126 个数组块哈希匹配。
- medium 已有无回溯走线前缀及后续成功释放分支，最后偏离目标 **8.8 mm / 42.3°**，终点修正抓取未通过。hard 最后位置误差 **0.051 mm**，朝向仍偏 **25.4°**。两档完整 Task success 仍未取得。
- 当前碰撞资产与旧执行匹配，源码差异单列；旧物理证据不改标为当前源码的新完整执行。关键点检查不覆盖点间路径、自碰撞和释放动力学，不扩大到其他 seed。

上述阶段之后的局部执行使用 **`history_storage="segment"`**：episode 起点与分段起点保存完整 checkpoint，其他 tick 保留轻量记录。
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
.venv-gs121/bin/python scripts/oracle_runners/run_solvability_workflow.py --mode diagnostic \
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
  scripts/oracle_runners/run_buzz_wire_policy.py --variant easy \
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
