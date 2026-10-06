# Knot Untying oracle

`robot_oracle.py` 在任务目录的 `rcb_topogym.Session` 中执行 ALOHA 纯摩擦抓取，
`route_rule.py` 从实测材料中心线选择删交叉／两端拉开的动作，`kinematics.py` 提供 IK。
执行入口统一在 `scripts/oracle_runners/`。几何交叉减少不等于成功；必须得到原生
`task_success`，随后用正式冻结实例在新进程回放。

当前证据、导入产物与剩余物理验证见 [任务页](../../../docs/develop/tasks/knot_untying_zh.md)。
2026-10-03 交接包已导入 `runs/test_results/knot_handoff_20261003/`，保留原始字节和 SHA-256 清单。
统一归档在 [solvability_proof/knot_untying](../../../solvability_proof/knot_untying/README.md)。
未指定 `--instance` 时使用当前 `tasks/` 中与 tooling 同目录的 i00 实例。
历史归档需显式指定 `--instance`，并使用那次记录的源码快照和镜像；旧轨迹不自动代表新实例通过。

## 当前释放判据

最新执行转入用户要求的 **Harbor grading**：[运行状态](../../../runs/test_results/knot_harbor_hard14_20261004_01/status.json)。使用独立冻结的 v16 候选和现有 `public_session.run_feedback_policy`，经任务 `Session.step()` 执行及原生隔离 verifier 评分；先 privileged，通过后再 standard。hard14 本地原生成功保留，其旧回放在 9.8425 s 主动停止，完整物理资格未完成；新 Harbor 实例的原生 oracle 已成功（51.0625 s、2,043 actions、20,425 ticks、稳定 0.5 s），隔离 verifier 正在第一遍独立核验，最终 Harbor 分数尚未产生。这里的释放判据 v5、Tooling v16、运行编号 hard14 分开记录，不能互相代替版本或成功资格。

2026-10-04 用户授权启用 `terminal_v5_fixed_contact_active_clearance_1mm`：夹爪／活动连杆间隙为 **1 mm**；世界固定底座可正常接触；所有部件仍拒绝绳体内部相交。保守包络不能确认时，使用共享 `utils/geometry/solid_contact.py` 的原生实体细化；1 nm 数值分辨率不作为允许穿透深度。保持落桌、速度、漂移、0.5 s 连续稳定及全 tick 独立物理审计。

`hard11` 使用独立冻结源码和新评价实例，预检要求原始物理 S0、机器人、控制目标和资产完全相同；Task／释放证据的版本改变会产生新的状态 SHA，不能冒称原始 v14 任务验收。原 `tasks/` 镜像包和旧结果保留其原判据。96 项相关 CPU 检查通过；两个 hard10 实测静置样本的新释放检查通过，但不替代完整回放。hard10 已主动停止；hard11 已通过原生初态一致性和 10 ticks 预检，新评价 SHA 为 `182eb5736b649784`；[hard11 计划](../../../runs/test_results/knot_oracle_20261003/hard11_native_launcher/launch_plan.json)与[实时状态](../../../runs/test_results/knot_oracle_20261003/background_status.json)记录新运行。下文 hard10 段落是旧版运行记录。

**hard11 原生成功已实测通过，但无穿透资格已被反例否定**：51.7925 s、2,072 actions／20,717 ticks，末动作 7 ticks，连续稳定 0.5 s；终态活动部件间隙下界 38.263 mm、最大绳速 0.8823 mm/s、漂移 0.4516 mm。[原生动作与报告](../../../runs/test_results/knot_oracle_20261003/hard11/report.json)及[独立轨迹／初态核验](../../../runs/test_results/knot_oracle_20261003/hard11/native_evidence_validation.json)保留。首遍正式回放的原生碰撞网格在 6.7325 s 起出现右手指与桌面内部重叠，已查前缀最大深度 0.06535 mm；[复核及主动停止记录](../../../runs/test_results/knot_oracle_20261003/hard11/replay_physical_rejection.json)已保存，未发布成功证明或视频。

`hard12` 在夹紧后将选中的 anchor 先抬高 2 mm，再由另一只手拉绳；参数 `anchor_lift_m` 仍可搜索 0／4／8 mm，不增加命令保护。只读桌面诊断提前发现了首次下降时的左手指浅重叠：1.875–2.025 s 共 5 个控制步末，最大约 0.11704 mm；hard11 的相同时刻也存在该问题。hard12 已主动停止，证据保留。

当前 [hard13](../../../runs/test_results/knot_oracle_20261003/hard13_native_launcher/launch_plan.json) 保留该抬升，并将 hard 的 `pinch_height_m` 设为 +1 mm，放绳时也保持这一高度偏移。30 项 CPU 检查通过，物理／v14 安全／v5 释放及穿透判据不变。每步记录接受的动作和实际 ticks，并保存部分轨迹快照。

**hard13 已原生成功：50.8575 s、2,035 actions／20,343 ticks，末动作 3 ticks**。从原始物理 S0 经两次决策、零回退完成 4→1→0，释放后稳定 0.5 s。终态 `robot_clear=true`，活动间隙下界 38.916 mm、最大速度 0.9054 mm/s、漂移 0.4704 mm。[完整动作及运行身份核验](../../../runs/test_results/knot_oracle_20261003/hard13/native_evidence_validation.json)通过，2,036 个控制步边界桌面检查无 findings。正式回放的早期逐 tick 检查却在 782–784 三个 tick 发现控制步之间的真实桌面浅重叠，最大 3.4375 μm；[独立复核及停止记录](../../../runs/test_results/knot_oracle_20261003/hard13/replay_physical_rejection.json)已保留。因此 hard13 不能取得全过程无穿透资格，未发布成功视频。

[首遍正式回放 0–3 s 窗口](../../../runs/test_results/knot_oracle_20261003/hard14_replay/early_table_window_validation.json)已核对 1,201 个状态：机器人／桌面检查无 findings，最小手指顶面垂直间隙约 0.4654 mm；旧反例时刻均有约 0.488–0.499 mm 正间隙。状态链、原始记录哈希及两个同内核观察器的输出一致；全程及 FEM 资格仍待验。

hard14 将默认 hard 抓取／放下目标再提高 0.5 mm（总偏移 +1.5 mm），原有物理、释放判据和 2 mm anchor 抬升不变。新运行已启动，在原生执行前 3 s 直接订阅每个物理 tick 做桌面诊断，避免同类步内反例等到正式回放才被发现；这不替代后续完整 FEM／碰撞验收。

该 [0–3 s 实测窗口](../../../runs/test_results/knot_oracle_20261003/hard14/milestones/early_tick_window/validation.json)已完整检查 1,201 个状态，无桌面 findings；手指顶面垂直间隙最低约 0.4654 mm，旧反例时刻约 0.488–0.499 mm。逐 tick 连续性和前 120 个实际动作核对通过；全程解结及正式物理资格仍待验证。

hard14 已在 **29.275 s** 完成首轮抽绳及释放，交叉数 **4→1**、零回退；随后进入两端整理。[首轮动作核验](../../../runs/test_results/knot_oracle_20261003/hard14/milestones/first_withdrawal/validation.json)通过：1,171 个动作／11,710 ticks 与原生台账一致，1,172 个控制边界桌面记录无 findings。约 42 s 已观测到零交叉和 `planar_clear=true`；仍在完成整理，落桌与稳定条件尚未满足。当前仍是中间结果，未取得原生成功或完整物理／回放资格。

[hard14 归档检查准备](../../../runs/test_results/knot_oracle_20261003/supporting/archive_helpers/release_v5_hard14/preparation.json)已通过 10 项 CPU 检查，并核对前 17 个实测动作／170 ticks 的独立副本。它按原生分支身份重建最终保留的动作路径；缺少完整成功、正式回放或物理审计时拒绝发布。该准备工作不代表 hard14 已通过真实任务验证，当前尚未发布成功归档或视频。

hard13 首轮抽绳和双手释放的独立节点也已保留：**29.25 s、1,170 actions／11,700 ticks，交叉 4→1**。[首轮检查点核验](../../../runs/test_results/knot_oracle_20261003/hard13/milestones/decision_1/validation.json)保存动作、台账和检查点的独立副本；1,171 个控制步边界桌面检查无 findings。该节点记录只证明对应前缀，完整原生结果见上文。

## 执行和回放

下列命令需要有兼容 Genesis 1.2.1、Nyx 和 CUDA IPC 的 Python；正式 IPC 存档还核对
pyuipc 版本和 libuipc build，不绕过身份检查。

当前任务包要求镜像 **0.2.12**，以下是对应入口；截至 v14 对比时，本机尚未安装该镜像、
尚未完成此版本的物理验证；实际拉取被 registry 拒绝，镜像来源待补。
`hard06`、`hard07`、`hard08_resume01`、`hard09` 已保留证据并停止。此前 `hard10` 使用冻结 v6 搜索源码、v14 任务工具、v14 hard 初态及本机
`0.2.13-dev` 镜像；真实预检初态 exact、一个控制步及 8 个抓姿 IK 通过。
这是上述明确版本组合的验证，不能称为官方 0.2.12 镜像已通过。
编译与 Nyx 缓存使用可写目录，容器内沿用当前用户身份。

```bash
docker run --rm --runtime nvidia --gpus all --user "$(id -u):$(id -g)" \
  -e NVIDIA_DRIVER_CAPABILITIES=all -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/work \
  -e XDG_CACHE_HOME=/work/runs/knot_cache \
  -e NUMBA_CACHE_DIR=/work/runs/knot_cache/numba \
  -e MPLCONFIGDIR=/work/runs/knot_cache/matplotlib \
  -v "$PWD":/work -w /work ghcr.io/luigivamper/rcb-topogym:0.2.12-cu128 \
  python scripts/oracle_runners/run_knot_oracle.py \
    --variation knot_untying_easy --output runs/test_results/knot_easy_new
```

```bash
python scripts/oracle_runners/run_knot_oracle.py \
  --variation knot_untying_medium \
  --output runs/test_results/knot_medium_new

python scripts/audit_knot_oracle.py \
  --instance tasks/topogym-knot-untying-medium-i00-privileged/environment/instance.json \
  --traj runs/test_results/knot_medium_new/trajectory.npz \
  --repeat 2 --output runs/test_results/knot_medium_replay_new

python scripts/oracle_runners/run_knot_branching.py \
  --variation knot_untying_hard \
  --output runs/test_results/knot_hard_new
```

所有输出目录必须尚不存在。入口冻结实际源码、任务工具和机器人资源，worker 使用该快照；
`resources.jsonl` 记录 CPU／内存，只有系统内存达到 90% 才停止本轮子进程。
正式回放须使用启用 RGB 的 `instance.json`，开发可使用同物理配置的 `instance_norgb.json`。
v14 的 R2 允许短于 0.25 s 的体积异常恢复，R4 的目标高度下限为桌面下 15 mm；
这些是 benchmark 的判定与命令保护，不构成全程无穿模资格。原生 R2 决定体积异常持续时间的
任务结论；独立审计记录每 tick 异常，并另行区分接触、实体内部相交和未解决的几何证据。
Nyx 初始化不等于已录视频；默认记录动作与中心线。连续执行可加 `--record-video`，
通过共享 `RecordingSession` 保存四路实际运行视频；回溯搜索仍单独回放成功路径录制。

运行产物为 `report.json`、`steps.jsonl`、`centerlines.npz`、`trajectory.npz`。
`native_progress.json` 每 8 控制步及终止时保存完整原生指标；被拒分支在回溯前保存动作前缀、
终态指标及共享 `SegmentEvidence` 的最后一 tick 状态，后者不构成全程碰撞证明。
控制器保持计划路径高度，释放不重复扣除已经损失的抬升高度。有原生 `Session.table_guard`
时不额外检查 +0.5 mm 命令间隙，也不强制抬高目标；下一次 IK 使用原生实际接受的目标。
只有兼容旧 tooling 的分支仍保留旧命令保护。实际状态另做独立物理审计。
工作区命令检查使用 `chain_fk.py` 的只读 CPU FK，与原生模型对照通过；它在构建时复制链参数，
每次查询不触碰实时 solver。hard07 起已采用该实现；原生 IK 仍使用共享适配器。

当前 `native_rules_clearance_search_v6` 默认不按交叉数停滞剪枝，总预算 16 层／128 次尝试。
hard09 使用冻结 v4，曾从精确初态真实重放 2,299 actions／22,990 ticks，中心线误差 0.05613 mm、关节误差 4.255×10⁻⁸ rad，恢复检查通过。hard10 已将同一前缀真实重放完成，恢复检查通过（中心线 0.06839 mm、关节 5.056×10⁻⁹ rad），不继承 hard09 的物理成功标签。本轮 tick 21,757（54.3925 s）的实际只读采样确认平面解结、落桌、静止和松手通过，原生 `robot_clear=false`。首个 +8 cm 局部抓取候选从 57.475 s 直接开始，首次局部抓取、平移和释放已实际执行。64.7125 s 的原生间隙下界提升至 2.147 mm，底座附近绳段沿 −Y 位移中位数约 4.46 mm；仍未达到 5 mm，原生完整成功与物理资格待验证。
候选包括两端选择、交换手臂、抓姿偏转／倾斜、不同抓点、上股固定、三维拉向和抬升／侧移路径。
IK 可尝试当前、home 和两个扰动种子，接受误差为 0.5 mm／0.01 rad；关节限制仍由原生模型执行。
抓点在三维中排序，拥挤点不再仅因投影间隙不足直接被否决；95% 材料跨度停止线默认关闭。
零交叉等待超时后继续撤手、双端平移、重新落绳或拉开，仍以原生 task_success 为完成条件。
v4 针对已落桌但机器人间隙未通过的状态，优先尝试双端同时平移：沿桌面八个方向各 2／4／8 cm，
附加 5 mm 的临时拱形抬升，再释放和静置。`translate_x_m`／`translate_y_m` 可调整有符号位移，
`translate_lift_m` 可调整非负临时抬升。现有体网格与全部机器人包络用于候选排序，
预测不能通过也不删除候选；预测采用固定机器人姿态下的绳体刚性平移，不证明真实抓持或变形后的间隙。
两臂每一步都解出 IK 后才共同提交动作；不改变 Task、材料、碰撞或原生安全规则。
v4 曾通过 25 项 oracle 和 12 项命令安全 CPU 检查；平移动作已实际执行，但未满足终态间隙，见下文。
v5 曾补充检查点搜索阶段记账，26 项 oracle CPU 检查通过：新检查点恢复后不重复已执行的入口静置，旧检查点仍保守等待，后续新决策仍正常等待。当时 hard09 保持 v4 冻结源码，因此在 57.475 s 恢复后额外静置了 10 s；这不是原生任务新增的限制。
hard09 完整尝试两端平移后，底座附近绳段跟随不足，原生间隙仍未通过，已保留 83.15 s 动作前缀并在 86.025 s 主动停止。hard10 部署 v6：用原生体网格间隙定位受限绳段，优先选择其材料位置 +8 cm、再 −8 cm 的邻近抓点，另一臂抓远端，同时保留两端抓取，共 72 条默认平移候选。`translate_grasp=clearance|ends`、`translate_grasp_offset_m` 可配置；这是候选优先级，不是固定终点要求。v6 还会识别旧检查点中已完成的静置尾段，保留物理重放与偏差核对。28 项 oracle 和 12 项命令安全 CPU 检查通过；局部 IK 与底座接近几何预检见任务页，真实局部抓取和完整物理资格仍待验证。
抓姿在可达的两个夹爪朝向中优先选择相对实测关节转动较小的一种，也可用 `grasp_flip` 指定。
接近默认 1 s，之后最多等待 4 s，让实际预抓位跟上；20 mm／0.1 rad 是下降时序的判断值，
超时仍尝试原生 IK，不是额外抓取否决条件。`approach_s`／`approach_wait_s` 可配置。
此修复针对 hard07 的真实跟踪滞后：左腕尚差 1.56 rad 时就要求固定最终朝向的笛卡尔下降，
导致 IK 不可达；未修改 v14 力矩限制。hard08 已完成首轮 29.125 s／11,650 ticks 的退绳、
释放及退开，交叉 4→1，动作前缀与第二轮检查点一致。第二轮已推进到 37.625 s 时收到外部
SIGTERM，未观察到原生失败；用户确认继续后启动 hard08_resume01，现已真实重放首轮并通过恢复检查：
中心线最大坐标偏差 0.09750 mm、关节最大偏差 1.610×10⁻⁷ rad，均低于 0.2 mm／0.2 mrad 容差；已续跑第二轮。
hard08_resume01 随后完成零交叉和释放；固定右底座附近的绳体未满足原生 5 mm 终态间隙。
该轮在 80.425 s 的静置阶段主动停止以升级策略，无原生失败；hard09 使用其 57.475 s 的 `d3_a2.pkl`，
通过真实回放和 0.2 mm／0.2 mrad 偏差检查后续跑。前 2,299 条控制器日志是继承记录，
最终连续物理证据由新的完整正式回放提供；完整解结及物理资格仍待验证。
轨迹保留每条 action 的实际物理 tick 数；原生成功会使最后一个控制步短于 25 ms。
只在原生成功时执行器返回 0。`audit_knot_oracle.py` 调用任务工具原有 `replay --strict`，
检查所有回放原生成功、正式初态 exact 和动作身份，写 `replay_audit.json`，失败返回非零。
只读观察器每 20 个 action 及不足一个控制步的末尾 action 更新 `replay_progress.json`，
同时记录原生终态指标，每遍完成写 `replay_passes.jsonl`；
动作、实际 tick 请求、原生 replay 循环和结束规则保持由任务工具处理。
单次回放的 `deterministic=true` 不表示重复运行已确定；至少两次才记录 determinism_tested。

独立全 tick 审计可加 `--workers 8` 使用多个 CPU 进程。每 tick 的实体测量函数相同，主进程按
原顺序计算证据哈希、验证状态链并汇总体积异常连续时长；最多保留 `2*workers` 条待处理状态。
9 项审计回归覆盖串并行等价、1 µm 穿透、跨批次体积异常和非法回溯。11 个真实 hold 状态的
串行／4 进程／8 进程结果及证据哈希一致，耗时约 10.85／4.74／4.32 s；该短样本不代表
完整轨迹吞吐。原 hard08 队列已随外部 SIGTERM 中断；hard08_resume01 使用同一冻结审计源码，
在首遍正式回放 capture 完整封存后运行 8 个 CPU 进程，不重复跑串行审计。
正式归档绑定实际审计源码哈希，并核验物理重放的前缀检查点；缺证据时拒绝发布。
GPU 非逐位确定性本身不否决全部回放的原生成功，与任务 verifier 保持一致。

`audit_knot_oracle.py --physics-evidence` 可通过共享 `SegmentEvidence` 保存每遍回放的初态和
每个已提交物理 tick，输出在 `physics_replay_*/`，并保存实际 FEM 网格、刚体碰撞网格与碰撞配对。
这会增加磁盘和运行开销；它只观察原生 reset／step／replay，不补动作或改变判据。
可加 `--physics-evidence-passes 1` 只记录首遍的完整 tick，其他原生 replay 仍全部执行；
记录过程保留 10 GiB 磁盘余量，不足时失败并封存不完整状态。
Knot 完整回放启用共享 `SegmentEvidence` 的可选 `deduplicate_arrays=True`：按字段路径复用
上一条相同 dtype、shape 和逐字节内容的数组引用，连接表等不变数据不重复落盘；每个 tick 和字段仍完整保存。
缓存只保留每条当前字段路径的上一值，原读取器可直接解码；其他调用者默认关闭该选项。
再加 `--video-evidence`，使用共享 `RecordingSession` 同步保存该遍的四路 Nyx 视频，
录像和数值证据的 episode／branch／state ID 必须对应，完成后全量解码核对帧数。
网格导出只读静态顶点和原生几何位姿，不调用会刷新物理顶点缓存的 `get_verts()`。
`capture.json.complete` 仅表示证据连续、完整，**不代表碰撞审计通过**。
`collision_audit.py` 已提供独立四面体体积检查和非相邻绳面三角形自交检查；
`physics_audit.py` 使用 `contact_geometry.py` 对接触候选做实体检查：原生凸网格／BOX 的精确凸体、
解析球及闭合凹网格。边界接触允许通过，凸包重叠只触发进一步检查；未实现的几何组合明确记为
unresolved，不称为穿透或完整合格。1 nm 为几何比较精度，不是毫米级穿透许可。
绳自接触由非相邻表面三角形及其相邻实体四面体区分边界接触与内部相交；不覆盖共享顶点面的
自折叠、无表面接触的完整自包含或 tick 间 CCD。每 tick 体积异常和原生接触深度保留诊断。
以下为 hard05/hard06 的旧审计设计：当时对全部填充四面体与原生启用刚体配对检查外包络分离，
包括完全包含的情况；外包络可能把凹槽算入实体，所以重叠只能判为不能认证，不能直接当作真实穿透。
原生球体按解析半径使用外接多面体，BOX 使用解析角点；不能把内接球面网格当作完整球体，未知 primitive 拒绝认证。
命令如下；非完整证据、碰撞疑点或原生未成功均返回非零。正式回放上的实际验证仍待进行。

```bash
python scripts/audit_knot_physics.py \
  --capture runs/test_results/knot_hard_replay/physics_replay_01 \
  --output runs/test_results/knot_hard_collision_audit
```

自交检查排除共享顶点／边的相邻三角形，检查范围为记录时刻，不作连续时间 CCD 声明。

## 分支与经验

- 默认闭合开口为 **5 mm**，是两指之间的实际宽度；旧 Env 执行器的原生夹爪坐标不可直接搬来。
  零开口曾在旧运行中压翻绳的四面体；当前 CLI 允许非负开口，由原生机器人限制处理命令，
  不把这条经验当成参数禁令。两端拉开默认离端头 **35 mm**，候选也包含其他端部距离。
- hard 默认 `full_pull=True, max_pull=.55`。交叉刚从 4 降到 3 就停会留下拉紧小卷；完整拉绳
  来自物体路线经验，机器人成功须另验。`--no-full-pull` 可显式复现旧策略。
- 分支候选包含 0.65 m 完整拉绳、方向调整和端部抓点调整。退绳的材料跨度停止线默认关闭，
  只有显式提供 `span_ratio` 才启用；IK 到达边界可结束当前延伸，再释放和尝试后续动作。
  两端拉开默认尝试到绳长的 90%，或零交叉后再延伸两段；这是可配置动作配方，不是任务成功条件。
- `branching.py` 在每个决策点补全 Env checkpoint；当前动作或后续决策失败都会回退并换候选。
  `branching.json` 保留全部尝试，最终 trajectory 只保留当前有效分支，仍须新进程回放认证。
  工作区的拒绝证据目录使用尝试开始时分配的 `attempt_id`，避免父子分支回退时重名；
  该修复已通过 CPU 回归并用于 hard08；旧 hard06 快照保留原实现。
- 搜索默认不按交叉数停滞剪枝，支持交叉暂时不变或增加后的恢复。
  可选 `--max-nonprogress-decisions` 才限制未刷新最低交叉数的操作次数；`4→5→4` 不刷新该可选预算。
  总预算默认为 **16 层决策／128 次尝试**；预算耗尽只表示本次搜索未找到解，不是原生物理失败。
  小于 12 cm 的紧圈只写诊断标记，不再直接回退；`--tight-curl-m` 仅调诊断阈值。
  medium / hard 在每个节点交替尝试删交叉和两端拉开的候选，旧规则只决定优先级。
  新运行的 `branching.json.search_policy` 标明 `native_rules_clearance_search_v4`；旧运行快照不随工作区修改。
- `checkpoints/d<k>_a<n>.pkl` 是受信本地控制器存档及动作前缀，不是跨进程原生物理存档。
  `--resume <文件>` 重建同一实例，回放全部前缀，核对绳形和关节后继续；需要原来的模拟时间。
  不接收缺少身份与 tick 校验的旧格式 checkpoint。
- 默认自动候选耗尽即退出；`--wait-hours 6` 会在根决策候选耗尽后等 `control/next.json`。
  文件须为候选对象列表，例如 `[{"max_pull": 0.7, "full_pull": true}]`；只收参数，不热加载代码。
  子决策耗尽先返回上游，不会因等待新参数而阻止上游回溯。

## 冻结实例

### 已确认的 very_easy / easier 变体

`very_easy` 为圈口单交叉；`easier` 为上下交替的双交叉。场景已获用户确认，具名入口已接入。
两档共用原 FEM/IPC、机器人 home 和终态判据；不是旧 easy 实例的别名。旧三档及 seeded 选择不变。
下列工具保存各自源码快照和工具 SHA；显式指定当前工具以免新变体误用历史任务包。

新两档控制器按所选 tooling 的 `JOINT_STEP_LIMIT_RAD` 限制每步关节目标变化，较大的移动
通过真实 `Session.step()` 分段执行并记录，保留 standard 的控制时序。Harbor 采用已有
`public_session.run_feedback_policy(session, output, variation=...)`；私有策略随 `solution/`
打包，公共镜像和 verifier 不包含 oracle。构建并评分两档的入口为：

```bash
bash bash_scripts/run_harbor_oracle_grades.sh \
  --families knot_untying --tiers very_easy,easier --gpu 0 \
  --image topogym-local/knot-below-easy:new \
  --output runs/test_results/knot_below_easy_harbor_new
```

每档先执行 privileged oracle 及两遍隔离评分回放，成功后把同实例轨迹交给 standard
在线执行和独立回放。以实际 verifier reward 为准；本地原生成功不等于 `solved=1`。
本轮冻结输入、私有源码和评分进展见[验证计划](../../../runs/test_results/knot_below_easy_harbor_20261005_01/plan.json)。

v16 的 `very_easy` 已在两种模式获得 `solved=1`，835 actions／8,341 ticks／20.8525 s；
两遍 privileged 回放和一遍 standard 回放均严格成功，未用额外保持步或回放容差。
证据见 [privileged](../../../runs/test_results/knot_below_easy_harbor_20261005_01/very_easy_privileged_verification.json)
和 [standard](../../../runs/test_results/knot_below_easy_harbor_20261005_01/very_easy_standard_verification.json)。
`easier` 首次尝试在抽绳 2→1 后双端抓取失效；第二轮三次空中对准均超限，
已保存完整失败轨迹，并停止其后续 verifier 回放。两轮都没有完整 Harbor 成绩。
第三轮通过 [`BelowEasyRunner`](below_easy_runner.py) 改为按剩余交叠再做一次抽绳，
保留闭爪前实测对准及抬升后的绳段跟随检查，复用同一公共候选执行。
[修订与检查记录](../../../runs/test_results/knot_below_easy_harbor_20261005_01/retry03_plan.json)。第三轮已在 v16 原生完成：
1,065 actions／10,645 ticks／26.6125 s，含松爪、落桌及 0.5 s 停稳；
见[动作与原生目标复核](../../../runs/test_results/knot_below_easy_harbor_20261005_01/easier_native_execution_check.json)。
用户要求切换 v18 后，已停止尚未完成的 v16 评分；该轮没有 easier 正式成绩。
上述成绩仅对应本轮 [`oracle_source_01`](../../../runs/test_results/knot_below_easy_harbor_20261005_01/oracle_source_01/)
冻结快照；工作区后续共享策略修改须独立验证，不能继承该成绩。

当前已启动 [v18 独立复验](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/plan.json)：
重新生成 K2／det1 冻结初态，分别重跑原 source01／source03 的冻结策略，再由双模式 verifier 评分。
旧实例与旧成绩保留，新版成绩尚未产生；[实时状态](../../../runs/test_results/knot_below_easy_harbor_20261005_01/regrades/v18_20261006_01/status.json)。

```bash
python scripts/prepare_knot_instances.py --variations very_easy easier --seed 0 \
  --tooling harbor_templates/topogym/common/rcb_topogym.py \
  --output runs/test_results/knot_below_easy_instances_new

python scripts/check_knot_initial_states.py \
  --instance runs/test_results/knot_below_easy_instances_new/very_easy/instance.json \
  --tooling harbor_templates/topogym/common/rcb_topogym.py \
  --output runs/test_results/knot_very_easy_initial_new

python scripts/oracle_runners/run_knot_oracle.py --variation knot_untying_very_easy \
  --instance runs/test_results/knot_below_easy_instances_new/very_easy/instance.json \
  --tooling harbor_templates/topogym/common/rcb_topogym.py --record-video \
  --output runs/test_results/knot_very_easy_robot_new

python scripts/audit_knot_oracle.py \
  --instance runs/test_results/knot_below_easy_instances_new/very_easy/instance.json \
  --tooling harbor_templates/topogym/common/rcb_topogym.py \
  --traj runs/test_results/knot_very_easy_robot_new/trajectory.npz --repeat 2 \
  --output runs/test_results/knot_very_easy_replay_new
```

替换 `very_easy` 为 `easier` 可检查另一档。`--record-video` 只用于连续无回溯的执行，采用共享
RecordingSession；回溯搜索仍通过保存成功动作后独立重放来录制。只读 IK 不证明真实夹持，
短时静置不证明解绳，原生成功与独立回放／物理审计／Harbor 评分分别记录。

以下为原三档的默认准备方式：

仓库旧 `tasks/` knot 存档早于 `contact_eps_velocity=.001` 修正，与当前代码的
physics_options 不同。已有交接实例可直接用；确需重新生成时：

```bash
python scripts/prepare_knot_instances.py \
  --variations easy medium hard --seed 0 --output runs/test_results/knot_instances_new
```

该入口串行调用 `export-ipc-state` 和 `make-instance`，保存完整 IPC 原生存档和正式／开发两份配置。
输出新的实例，不改 `tasks/` 的冻结 benchmark。重建后须重新核对轨迹身份及回放结果。

CPU 回归：`python ci_checks/test-knot-oracle.py` 和 `python ci_checks/test-oracle-runners.py`。
它们不授予物理成功资格。当前范围也不包括多 seed、网格／步长收敛或逐子步机器人禁碰审计。
