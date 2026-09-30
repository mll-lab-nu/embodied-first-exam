# Hedgehog medium：物体通路 → IK → 连续执行

当前四腰窗模型 `waisted4_dark_wood_v1`、默认参数、seed 0 已完成一份有限实例的构造性可解证据。机器人从默认 home 出发，真实接近、双指接触抓住长刺、抬升、旋转出笼并进入固定目标区；第 2,260 个物理 tick 原生 `task_success=True`，仿真时间 56.5 s，完整刺球低速保持 2 s。[逐 tick 独立审计](evidence/runs/native_audit_01/execution_audit.json)通过，`accepted_proof=True`。

## 解法与证据层次

| 层次 | 方法与结果 | 证据 |
| --- | --- | --- |
| 纯物体 | 先从笼内抬升到宽窗口带，再向 −y 侧移并转动，让尖刺依次通过，出笼后送入目标区；7 个关键位姿 | [物体证书](evidence/supporting/object_final_01/object_witness.json) |
| 连续几何复核 | 初始抬升段间隙下界 0.199 mm；后续路径下界 1.044 mm；完整可视及碰撞表面、封闭端、底座、桌面和全部尖刺均纳入 | [重建审计](evidence/supporting/object_final_audit_01/object_audit.json) |
| 机械臂转换 | 使用实测被动夹爪形状及抓持变换重新规划，把夹爪、link7 和包围 link6 全转角的圆柱一起纳入；7 个关键位姿、1,273 个 IK 采样，复合物体路径下界约 1.000 mm，最小关节余量 0.383 rad | [持件规划](evidence/runs/native_success_01/held_plan_0.json) |
| 真实执行 | 默认 home → 接近 → 双指接触 → 12 mm 试抬升 → 同步旋转侧移出笼 → 目标区停稳；只发原生 JOINT_ABS，不摆放物体、不设置被动关节、不回溯 | [执行报告](evidence/runs/native_success_01/oracle_report.json)、[完整 tick 状态](evidence/runs/native_success_01/trail/private/physics_states.jsonl) |
| 独立物理证据复核 | 2,261 个状态连续；运输时球体最小间隙 1.027 mm，机械臂环境间隙 2.924 mm，非相邻机械臂自碰间隙 71.414 mm；禁碰接触力记录为 0；最大接触穿透约 0.0199 mm | [审计报告](evidence/runs/native_audit_01/execution_audit.json) |

纯物体路径说明窗口确实可通行，但不能直接照搬成夹爪轨迹。真实夹爪的被动连杆形状与名义闭合模型不同；直线抬升还会碰上窗口上缘。机器人版本从试抬升后的实测状态出发，联合考虑刺球、夹爪和腕部，边转动边侧移。IK 使用前一采样点作种子，并逐点检查限位、环境碰撞和非相邻机械臂自碰。

几何证书的每条边使用线性平移和最短 SLERP。半区间内任意表面点的运动量由 `||Δp|| + R·θ` 约束；FCL 中点距离减去运动上界和 1 μm 数值误差预算，得到整段间隙下界。不能认证的细分区间拒绝通过。因此它是具有明确数值误差假设的几何证书，不是连续动力学或所有参数的形式化证明。

## 抓持、终态和资格范围

真实双指接触触发原有 `contact_weld_v1`，之后由该理想刚性抓持模型保持刺球。这份证明包含完整机器人动作，但**属于辅助抓持，不是纯摩擦抓持证明**。此前纯摩擦试抬升未能稳定带起刺球；诊断原件保留在 `runs/hedgehog_oracle_20260930/pickup_03/`，不计入成功数量。旧 `demos/` 中单斜窗视频仅提供抓刺和旋转的参考，属于旧几何，不转移其资格。

保持原先的固定目标区、完整尖刺包含、其余部件在分隔线后、线速度 ≤ 0.001 m/s、角速度 ≤ 0.02 rad/s、稳定 2 s 的判据；允许继续抓持。先前[资格运行](evidence/qualification/frozen_diagnostic_01/oracle_report.json)达到相同几何目标并稳定 2.75 s，但其 `task_success=False` 保持不变。[该次独立审计](evidence/qualification/diagnostic_audit_02/execution_audit.json)通过后才为后续运行启用 `hedgehog_placement_v2`。本次新的物理运行实际取得原生成功，没有重写旧结果。

[范围及反例检查](evidence/supporting/boundary_checks_01/checks.json)确认未验证的 seed、easy/hard、修改摆位或缩短稳定时间不会继承资格；目标未完全入区、笼子越过分隔线、修改资产、非 home 起点和缺失末段状态均被拒绝。

配置是 Panda + 原尺度 Robotiq、CPU float64、JOINT_ABS、25 ms World tick / 40 solver 子步（积分子步 0.625 ms）、40 Hz 控制与 Task/assist 检查。机器人碰撞几何和接触审计基于 tick 末状态；固定安装底座 link0 不进入机器人表面距离统计，底座与桌面接触允许，机器人与笼体接触仍检查。内部夹爪连杆及腕部配合面不计入非相邻机械臂自碰检查。未授予默认 400 Hz、半时间步、连续时间/所有子步无穿透、其他 seed/参数或视觉资格。没有新增视频。

## 复现与独立复核

在仓库根目录执行，输出目录须尚不存在；各入口冻结源码并监控资源，内存超过 90% 或 CPU 达到 90% 时只停止本次工作进程。

```bash
.venv-gs121-nyx/bin/python scripts/plan_hedgehog_object_oracle.py --output runs/hedgehog_object_new
.venv-gs121-nyx/bin/python scripts/plan_hedgehog_object_oracle.py --audit runs/hedgehog_object_new/object_witness.json --output runs/hedgehog_object_audit_new
.venv-gs121-nyx/bin/python scripts/run_hedgehog_oracle.py --assisted --output runs/hedgehog_run_new
.venv-gs121-nyx/bin/python scripts/audit_hedgehog_oracle.py --run runs/hedgehog_run_new --require-native-success --output runs/hedgehog_audit_new
```

也可将最后一条的 `--run` 指向本归档的 `evidence/runs/native_success_01`，从冻结数值证据复核，毋须再次运行物理。精确重建历史软件应使用各目录 `source_snapshot/` 与 `source_manifest.json`；[依赖版本](evidence/supporting/boundary_checks_01/runtime_versions.json)已记录，虚拟环境本身未打包。策略报告原始 `accepted_proof=False` / `pending_audit` 字段保留，最终验收状态以独立审计及[汇总](summary.json)为准。

## 归档

[清单](archive_manifest.json)逐文件记录原路径、大小、SHA-256 与角色；[归档复核](archive_validation.json)验证独立副本、源码清单和物理状态哈希。完整源码、资产、动作、状态及审计均在本地 `evidence/` 中，不依赖清理前的原始 run。完整证据被 Git 忽略，传递证明须同时携带 `evidence/`。归档不增加物理成功次数。本次成功复跑的主机内存峰值 24.4%，前置资格复跑峰值 26.7%，未触发暂停。
