# Rope Threading oracle

## easy / medium / hard：Wang 0° 接力方案

三档共用物体路径、ALOHA IK 和接力控制器，按变体选择独立方案：

| 变体 | 默认方案 | 关键换抓 |
| --- | --- | --- |
| easy | `A10_B_pull19_B20_recvA` | R1 右手送、左手接；左手在绳尖后 20 cm 换抓，送过 R2，右手接 |
| medium | `A10_B_pull19_B20_keep_recvA6` | 左手在绳尖后 20 cm 换抓，保持抓持穿过 R2/R3，右手接 |
| hard | `A10_B_pull19_B24_keep_recvA5` | 换抓点改为绳尖后 24 cm，末环 poke 为 5 cm |

`A=right, B=left`，IK hold 采样间隔默认 10 mm。配方在 `profiles.py`、
`hard_plans.json`；`geometry.py` / `object_oracle.py` 构建物体路径证据，
`relay_kinematics.py` / `relay_ik.py` 做只读 IK、Jacobian 和碰撞检查，
`relay_policy.py` 通过普通 `EE_ABS` 执行动作。无物体瞬移、无运行时 `set_qpos`。

从仓库根目录运行下面三步；将 `variant=easy` 改成 `medium` 或 `hard` 即为另一档：

```bash
variant=easy
run="runs/test_results/rope_threading_${variant}_new"
.venv-gs121-nyx/bin/python scripts/plan_rope_threading_oracle.py \
  --variation "$variant" --seed 0 --output "$run/object"
.venv-gs121-nyx/bin/python scripts/plan_rope_threading_ik.py \
  --witness "$run/object/object_witness.json" --output "$run/ik"
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_rope_threading_relay.py \
  --variant "$variant" --seed 0 --samples "$run/ik/relay_samples.npz" \
  --output "$run/execution"
```

每个输出目录须不存在；三步均冻结源码、保存输入和资源监控，内存达到 90% 只停止本轮 worker。
只读规划器沿用项目约定放在 `scripts/`，物理执行入口放在 `scripts/oracle_runners/`。
`--plans-json` 仍可显式试其他配方；hard 的默认方案已内置，无需外部文件。
物体路径可用 `plan_rope_threading_oracle.py --audit <object_witness.json> --output <新目录>` 独立重建。

执行默认从标准 home 开始，使用当前公共物理时序（2.5 ms、4 子步、10 倍控制降采样）、
CUDA FEM/IPC、显式 `ipc_soft_band_v1` 和共享 SegmentRunner/Nyx 四视角录像。
`--no-rgb` 显式禁用录像；`--physics-dt .005 --control-decimation 5` 可复现附件执行命令的时序。
执行器检查轨迹中的变体、seed、实例／资产、robot mount 和 home 身份。
旧的无身份 NPZ 必须重新生成，不直接作为本仓库轨迹执行。

来源清单与原始导入哈希见 `wang_source.json`。附件声明三档 IK 已验证，物理作业均取消；
其中的 IPC 轴补丁已由本仓库 `world/physics/ipc.py` 覆盖，无需另打补丁。
整合时保留核心 IK 算法，纳入当前实体底座碰撞检查，修正带 `/via_home` 等后缀的阶段序列化，
回放采用固定插值起点并限制平移／旋转速度，抓持等待实际 native solve 并检测丢失。

IK 只证明采样点的可达与间隙；物体模型仍假设绳沿固定路径滑动，并有无人抓持的换抓阶段。
`EE_ABS` 回放与测量反馈不能继承 IK 的关节分支／碰撞证书。完整物理通过须原生 Task
`task_success`、终止和完整逐 tick 证据；`policy_done` 不代表成功，成功时允许仍抓持。
实际验证范围见[任务页](../../../docs/develop/tasks/rope_threading_zh.md)。

回归入口：`.venv-gs121-nyx/bin/python ci_checks/test-rope-threading-oracles.py`。

2026-10-03 当前仓库 seed 0 复验：三档物体路径均通过，easy / medium / hard 的
首选方案分别生成 452 / 466 / 500 个通过的 IK 样本；18 项接入回归和 6 项场景回归通过。
记录见[整合报告](../../../runs/test_results/rope_threading_wang_integration_20261003/integration_report.json)，
可直接使用报告中的各档 `samples` 路径启动对应执行入口；本轮没有执行完整物理流程。

## very_easy / easier：简化任务开发控制器

入口：`scripts/oracle_runners/run_rope_threading_policy.py`。
`very_easy` 使用上方敞开的下半圆；`easier` 使用单个完整 R1，并检查双手交接。

控制器从统一 ALOHA home 开始，读取实际绳端位置，以普通 `JOINT_ABS` 指令连续接近、夹取、抬起。
双指接触经共享 `ipc_soft_band_v1` 确认后才能抓持。`ThreadingIK` 使用原生 IK/FK，检查关节限位、
桌面、双臂和场景支架；环的碰撞查询保留原三角网格，不把通孔凸包化。

`--part pickup` 只执行抓取和 40 mm 抬起；`--part solve` 继续执行搭绳或送绳／接绳候选路径。
`--speed-scale`、`--physics-dt`、`--solver-substeps` 都写入报告。更快的开发时序不等于默认物理资格。
`--no-rgb` 明确关闭视频；否则使用共享 SegmentRunner 的四路 Nyx 录制，从 home 起完整留证。

这是尚未完成完整机器人资格验收的开发策略。查阅
[任务页](../../../docs/develop/tasks/rope_threading_zh.md)和每次运行的 `run_report.json`，
不要把 `pickup_passed`、合成状态回归或 `policy_done` 当成原生任务成功。
