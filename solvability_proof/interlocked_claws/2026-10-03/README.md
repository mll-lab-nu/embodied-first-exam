# 2026-10-03：Claws 三档连续证明

三档均原生 `task_success=True`，完整状态逐 tick 经独立审计。
本批依据用户提供的另一 agent 代码交接，在本地重新执行；旧报告中的成功标签未转移。

| 变体 | 原始连续执行 | 独立审计 | 全部状态数 |
| --- | --- | --- | --- |
| easy | [运行报告](evidence/easy/run/oracle_report.json) | [审计](evidence/easy/audit/execution_audit.json) | 743 |
| medium | [运行报告](evidence/medium/run/oracle_report.json) | [审计](evidence/medium/audit/execution_audit.json) | 1,252 |
| hard 收薄版本 | [运行报告](evidence/hard/run/oracle_report.json) | [有界滑动审计](evidence/hard/audit/execution_audit.json) | 8,330 |

策略分别使用两段螺旋退钩、偏航与滚转穿双窗，以及录制路线经走廊重连的复合运动。
每次都先真实接触取得双手辅助抓持，再根据实测物体／夹爪偏移重求耦合 IK。
未设置物体轨迹、未回溯、未更改机器人模型与执行增益。目标是完整分离后静稳，
不要求搬运到绿色区域。easy / medium 几何沿用交接；hard 的 3 mm 表面收薄为新版本。

当前几何证书余量为 1 / 4 / 4 mm，实测抓持状态 IK 分别含 139 / 112 / 739 行。
IK 是采样检查，独立执行审计覆盖完整离散物理 tick，均不冒充连续时间机器人碰撞证明。
easy / medium 接受辅助抓持后第一秒内的脱离接触，随后禁止件间接触。
hard 的 5 个三角交叠 tick 中有 3 tick 被引擎报告件间接触，最大三角深度 0.429 mm；
采用明确的 8 N／1 mm 引擎／0.5 mm 三角上限。全场景最大引擎穿透 0.534 mm，
包含手指夹持。严格无接触检查会拒绝该 hard 运行。
[严格拒绝记录](evidence/supporting/hard_strict_rejection/execution_audit.json) 与
[六轴直拉反例](evidence/supporting/straight_pull_controls.json) 同批保留。

CPU float64、25 ms tick、40 子步、control decimation 1，seed 0，原尺寸 ALOHA，
普通 JOINT_ABS，`contact_weld_v1`。起点为任务预抓姿态，不含标准 home 接近过程。
本批无 GPU／Nyx 视频；不覆盖原始未收薄 hard、随机实例域、默认任务包时序或纯摩擦抓持。

每档 `evidence/<档位>/run/` 含完整 `trail/`、实际动作、物体 witness、实测 IK、
碰撞几何、源码快照和 manifest。`audit/` 另含冻结审计源码、配置及复核结果。
原 `oracle_report.json` 保持 `native_success_pending_audit` 的原字节；
合并原生成功与独立审计后的正式状态以 [summary.json](summary.json) 为准。
真实复制及 SHA-256 校验见 [清单](archive_manifest.json) 和 [验证](archive_validation.json)。

重新执行命令见 [Oracle 说明](../../../scripts/oracle_runners/README.md#claws-easy--medium--hard-交接路线)。
复核已归档证据示例：

```bash
.venv-gs121/bin/python scripts/audit_claws_oracle.py \
  --run solvability_proof/interlocked_claws/2026-10-03/evidence/hard/run \
  --require-native-success --tolerate-piece-contact --piece-force-n 8 --contact-depth-mm .5 \
  --output runs/test_results/claws_hard_archive_reaudit_new
```

使用未来源码复核时仍会校验资产、模型及终态身份；若它们已变，使用归档 `audit/source_snapshot`
中的相同 CLI，不能把新版几何的复核记到旧实例上。
