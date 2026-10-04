# 2026-10-03 Knot 冻结实例回放

状态：本批次仍在验证中，不能按目录存在推断三档已通过。

| 变体 | 原生执行 | 新进程正式实例回放 |
| --- | --- | --- |
| easy | 导入 `easy05`：575 actions、5,744 ticks、14.360 s，成功 | 导入原日志：一遍成功、instance_exact=true；没有两遍确定性证明 |
| medium | 导入 `medium03`：1,927 actions、19,268 ticks、48.170 s，成功 | 本轮首遍消耗全部动作但 `success=false, episode_end=null`；第二遍取消，暂缓排查 |
| hard | 导入的 `hard01` 尚有紧卷，不算成功 | `hard03` CUDA 初始化失败；`hard04` 按用户要求停止，当前以放宽后的搜索策略从相同冻结初态运行 `hard05`，结果待验 |

medium 的[首遍原生返回值](evidence/replays/medium03_first_pass/medium_first_replay_result.json)
来自只读进程状态，原生 session 事件也报告 `success=false`。初态 SHA 精确匹配；
第一遍完整结束后才取消第二遍，保留原始输出及源码，尚未给失败原因下结论。

原始成功 run、正式／无 RGB 实例、完整 IPC 状态及交接源码均按原始字节复制到 `evidence/`。
[归档清单](archive_manifest.json) 和 [副本验证](archive_validation.json) 只证明文件一致性；
[逐档索引](summary.json) 单独记录物理结果，归档本身不增加成功次数。
`evidence/` 沿用项目约定保留本地实文件、不自动提交 Git，传递本批次必须同时携带该目录。

实例时序为 2.5 ms × 10、IPC 子步 1、Newton/PCG 容差 1e-3/1e-5、linear_bvh、
600 tick 静置存档，grasp_assist none。原交接镜像 0.2.3，本轮镜像 0.2.6；
两者 libuipc build 均为 `292c98c3`，新环境结果单独验证。

```bash
KNOT_BATCH=solvability_proof/knot_untying/2026-10-03_frozen_replay/evidence
KNOT_REPLAY_SOURCE="$KNOT_BATCH/replays/medium03_first_pass/source_snapshot"
PYTHONPATH="$KNOT_REPLAY_SOURCE" python "$KNOT_REPLAY_SOURCE/scripts/audit_knot_oracle.py" \
  --instance "$KNOT_BATCH/instances/medium/instance.json" \
  --traj "$KNOT_BATCH/runs/medium03/trajectory.npz" \
  --repeat 2 --output runs/test_results/knot_medium_reaudit_new
```

以上历史复现命令需在原 0.2.6 运行环境中使用归档源码；当前工作区的 v14 tooling 不替代历史版本。
入口使用该快照任务目录自己的 `rcb_topogym.py replay --strict`，只在每一遍都原生成功且初态
exact 时通过。单次 `deterministic=true` 不能证明重复确定性；GPU state hash 不同本身也
不否定每遍原生成功，与 verifier 原有规则一致。
本批次当前尚无全程逐 tick 网格状态、逐子步机器人禁碰、网格／时间步收敛或新录像。
hard05 成功后的队列已准备首遍正式回放的逐 tick 数值证据、共享四路视频和独立几何检查，
尚未实际产出或通过，不能提前计入证明数量。其旧实例结果也不代表 v14 新实例通过。
完整命令与抓取／回溯经验见 [oracle README](../../../topogym/planning/knot_untying/README.md)。
