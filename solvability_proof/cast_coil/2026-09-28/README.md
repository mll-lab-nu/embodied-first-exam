# Cast Coil：2026-09-28 验收批次

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

**3/3 实际 `Task.task_success=True`，独立逐 tick 复核全部通过，共 20,461 个状态。** [逐变体索引](summary.json) · [完整证据清单与哈希](archive_manifest.json) · [归档检查](archive_validation.json)。

| 变体 | 仿真时间 | 最终相对位置误差 | 实际运行 | 独立复核 |
| --- | ---: | ---: | --- | --- |
| easy | 162.900 s | 0.176 mm | [报告](evidence/runs/easy_fast_03/run_report.json) | [passed](evidence/runs/easy_fast_03/audit.json) |
| medium | 181.300 s | 0.206 mm | [报告](evidence/runs/medium_fast_05/run_report.json) | [passed](evidence/runs/medium_fast_05/audit.json) |
| hard | 167.250 s | 0.190 mm | [报告](evidence/runs/hard_fast_05/run_report.json) | [passed](evidence/runs/hard_fast_05/audit.json) |

从 ALOHA 默认 home 接近桌面自由零件，真实双指接触触发 `contact_weld_v1`，按实测物体/TCP 反馈进行逆向装配，放桌、解除辅助、撤手并稳定 0.5 s。策略仅提交标准 action，经 SegmentRunner / Env / Genesis IK 与物理执行。

默认参数、seed 0、CPU float64、EE_ABS，使用 unlimited 对象状态；显式 25 ms tick / 40 子步 / 1 tick per action，action 和 Task/assist 检查 40 Hz，积分子步 0.625 ms，无 RGB/视频。该范围不覆盖纯摩擦、全部随机参数或默认 400 Hz 检查时序。

## 三档路线与源码范围

| 变体 | 主要装配线路 |
| --- | --- |
| easy / baseline_assembly | 插入 → 逆转 90° → 合拢 |
| medium / axial_screw_turn | 插入 → 同时逆转并撤销 9 mm 轴向偏移 → 合拢 |
| hard / split_turn_offset | 插入 → 逆后 45° → 撤销 9 mm 偏移 → 逆前 45° → 合拢 |

放置使用抓取前实测桌面支撑姿态。详见[任务解法与复现命令](../../../docs/develop/tasks/cast_coil_zh.md#当前三档-policy-与可解性验收)。每次执行的 policy/Task/世界源码位于其 `source_snapshot/`，并有 `run_source_manifest.json`、配置/资产、全部 `private/physics_states.jsonl`、`private/control_steps.jsonl` 和引用的数组文件。

easy 的冻结执行源码早于最终放置修正；[action 一致性检查](evidence/runs/easy_fast_03/current_policy_replay.json)证明当时最终 policy 在成功日志上逐项复现 6,516 个 action，不增加一次物理执行，也不代表今后任意源码版本都等价。medium/hard 的 05 运行直接执行含修正的冻结源码。[原机器汇总](evidence/summary.json)中的 `current_core_source_matches` 也是原汇总时点的比较，不能解释为与此后工作区自动保持一致。

逐 tick 精确碰撞盒最小间隙为 easy −0.00161 mm、medium −0.00114 mm、hard −0.00935 mm，仍有微米级重叠；该批次证明原 Task success，不声称连续时间或全部 solver 子步无穿透。[参考几何证书](evidence/supporting/reference_geometry.json)仅覆盖理想对象路径；[放置几何修正检查](evidence/supporting/placement_geometry_check.json)、[单元检查](evidence/supporting/unit_results.xml)和[真实继续执行/回溯检查](evidence/supporting/checkpoint_runtime.xml)分别保留自身范围。

## 复核

在仓库根目录使用现有依赖环境和每次运行自己的审计源码；输出使用新路径。原 Coil CLI 会写回运行目录的 `audit.json`，下面直接调用其复核函数，把新结果写到归档外。审计从冻结 Task 重算记录的每 tick 状态，不启动新物理 rollout：

```bash
.venv-gs121-nyx/bin/python -B - <<'PY'
import json
from pathlib import Path
import runpy
run = Path('solvability_proof/cast_coil/2026-09-28/evidence/runs/easy_fast_03')
audit = runpy.run_path(str(run / 'source_snapshot/scripts/audit_cast_coil_policy.py'))['audit']
result = audit(run)
with Path('/tmp/coil_archive_reaudit_easy.json').open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
assert result['passed'], result['issues']
PY
```

另两档替换 `easy_fast_03` 和输出名。完整副本保留原文件字节与身份，原始诊断尝试仍在 `runs/test_results/cast_coil_ik_20260928/`；访问归档采用本批次的 `summary.json`。本次归档及哈希验证不新增物理成功次数。
