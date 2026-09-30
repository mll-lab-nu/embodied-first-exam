# Cast Keyhole：2026-09-28 验收批次

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**3/3 实际 `Task.task_success=True`，独立复核全部通过，共 59,424 个状态。** [逐变体索引](summary.json) · [完整证据清单与哈希](archive_manifest.json) · [归档检查](archive_validation.json)。

| 变体 | 仿真时间 | 状态数 | 实际运行 | 独立复核 |
| --- | ---: | ---: | --- | --- |
| easy / F1 长行程 | 488.650 s | 19,547 | [报告](evidence/runs/trial_38_easy_qualified/run_report.json) | [passed](evidence/runs/trial_38_easy_qualified/independent_goal_audit.json) |
| medium / F2 偏心窗口 | 459.600 s | 18,385 | [报告](evidence/runs/trial_35_medium_qualified/run_report.json) | [passed](evidence/runs/trial_35_medium_qualified/independent_goal_audit.json) |
| hard / F3 转向回退 | 537.275 s | 21,492 | [报告](evidence/runs/trial_37_hard_qualified/run_report.json) | [passed](evidence/runs/trial_37_hard_qualified/independent_goal_audit.json) |

运行从默认 home 和桌面自由物体开始，连续完成双指接触拾取、两次真实换抓、联合解锁、固定绿色目标区搬运及 0.5 s 稳定窗口。允许保持抓持；银件全几何进入目标区，金件留在分界另一侧。无段间 reset、rewind 或物体位姿覆盖。

默认参数、seed 0、ALOHA、CPU float64、EE_ABS，使用实际双指接触触发的 `contact_weld_v1`。显式 25 ms World tick / 40 子步 / 1 tick per action：积分子步 0.625 ms，action 与 Task/assist 检查 40 Hz。无 RGB/视频；不是默认 400 Hz 检查时序、纯摩擦或随机参数域证明。三次最大任务接触穿透分别为 0.406917 / 0.364626 / 0.428768 mm；这些是 tick 采样值。

## 解法与保存内容

[解法及 action / IK 采样细节](../../../topogym/planning/cast_keyhole/README.md)说明抓姿候选、换抓路径、双臂联合 FK/IK、碰撞预检及实测反馈。规划仅生成标准 EE_ABS 目标，实际使用 Genesis IK、电机及物理积分执行。每个 `evidence/runs/<run_id>/` 保存完整原目录，包括：

- `source_snapshot/` 和 `run_source_manifest.json`：实际执行的冻结源码与逐文件哈希。
- `config.json`、`invocation.json`、`asset_manifest.json`、`scene/`：配置、命令和场景资产。
- `private/physics_states.jsonl`、`private/control_steps.jsonl`：全部 tick 状态和 action；同目录的监测/事件及数组文件一并保留。
- `coupled_ik_plan.json`、换抓与目标区路径、碰撞预检、segment 报告和最终独立审计。

[原始机器汇总](evidence/proof_summary.json)保留原路径与原始哈希；当前本地访问路径见上方 `summary.json`。性能优化的逐字节状态、继续执行/回溯检查保存在 `evidence/supporting/`，不增加任务成功次数。

## 前置资格证据

三个旧运行先满足同一完整目标条件，随后给精确匹配的几何、默认参数和目标区开放 success。其源码、状态、审计和原失败报告也完整归档：

| 变体 | 前置运行与复核 | 原始状态 |
| --- | --- | --- |
| easy | [trial_36_easy_goal_clearance](evidence/qualification/trial_36_easy_goal_clearance/independent_goal_audit.json) | raw goal 满足；当时 `task_success=False` |
| medium | [trial_27_medium_pid](evidence/qualification/trial_27_medium_pid/independent_goal_audit.json) | raw goal 满足；当时 `task_success=False` |
| hard | [trial_33_hard_packed](evidence/qualification/trial_33_hard_packed/independent_goal_audit.json) | raw goal 满足；当时 `task_success=False` |

以上不计入正式成功数。归档没有改写其状态，也没有放宽几何、区域、速度、稳定窗口或穿透阈值。

## 复核

在仓库根目录使用现有依赖环境执行；输出使用未存在的路径。审计导入所选运行的冻结源码，从记录的数值状态重算 Task，不启动新的物理 rollout：

```bash
.venv-gs121-nyx/bin/python -B \
  solvability_proof/cast_keyhole/2026-09-28/evidence/supporting/audit_cast_keyhole_policy.py \
  solvability_proof/cast_keyhole/2026-09-28/evidence/runs/trial_38_easy_qualified \
  --output /tmp/keyhole_archive_reaudit_easy.json
```

另两档替换运行目录及输出名。新的物理执行命令见[任务页](../../../docs/develop/tasks/cast_keyhole_zh.md#当前运行入口)，归档副本不作为新实验输出目录。原始运行保留在 `runs/test_results/cast_keyhole_policy_20260928/`；复制和哈希验证不新增物理成功次数。
