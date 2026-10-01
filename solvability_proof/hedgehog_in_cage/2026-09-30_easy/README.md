# Hedgehog easy：侧窗移出、释放换抓、进入目标区

当前 CLASSIC 三星刺球 `simulator_v1`、默认参数、seed 0 已取得一份有限实例的构造性可解证据。从 Panda 默认 home 连续执行两次接触抓取，到原目标区低速保持 2 s，第 **9,555 tick / 238.875 s** 原生 `task_success=True`；[完整独立审计](evidence/runs/easy_qualified_audit_01/execution_audit.json)通过，`accepted_proof=True`。本批仅计 easy 一份成功；medium 保留在[原批次](../2026-09-30/README.md)，hard 尚未完成。

## 从物体路径到机器人执行

纯物体先保持姿态上抬到笼中心，再多次转向并向 +X 宽侧窗移动，让球核和各根尖刺依次穿过，最后在笼外进入目标区。[20 个关键位姿的证书](evidence/supporting/easy_object_frozen_01/object_witness.json)及[独立几何复核](evidence/supporting/easy_object_audit_01/object_audit.json)覆盖完整可视/碰撞表面、封闭体初态、连续插值和终点全尖刺包含，连续间隙下界约 0.100379 mm。

机械臂版本采用两次抓取。第一次抓 S8，经实测持件规划送到侧窗外，球心约 `(88.42, 1.67, 32.93)` mm；松开后由物理自然落到底座，停在约 `(89.36, 19.94, -77.06)` mm。第二次抓 S6，抬起约 12 mm，向外上方移动时微转约 4.4°，再向外至 x≈150 mm、转回原朝向，绕过笼体进入原目标区。坐标以笼中心为原点；释放和重新抓取都发生在同一连续 episode，没有恢复快照、摆放物体或设置被动关节。

原物体路线在窗边需要较大的转向；已测试的单次固定抓法没有覆盖整条路线。自然释放改变了后续抓取姿态，第二次抓取使最后的出笼调整减至约 4.4°。这是一种已构造并执行的解法，不是单次抓取无解的证明。所有新物体路线均先向用户报告，再进行相应的抓取与 IK 搜索。

| 层次 | 结果 | 归档证据 |
| --- | --- | --- |
| 释放后物体续接 | 主要路径连续间隙下界 0.100429 mm；离开支撑 0.1 mm 后的竖直抬升段下界 98.18 μm | [独立几何复核](evidence/supporting/easy_far_continuation_audit_01/object_audit.json) |
| 实测持件与 IK | 第一次 3,023 个、第二次 637 个 IK 样本；检查整机环境、自碰、限位及相邻样本关节变化 | [第一次](evidence/runs/easy_qualified_native_01/held_plan_0.json)、[第二次](evidence/runs/easy_qualified_native_01/regrasp_1_held_plan_0.json) |
| 实际默认 home 全程 | 两次抓取、第一次释放、第二次抬升、出笼、全尖刺入区并低速保持 2 s | [执行报告](evidence/runs/easy_qualified_native_01/oracle_report.json)、[每 tick 状态](evidence/runs/easy_qualified_native_01/trail/private/physics_states.jsonl) |
| 独立逐 tick 审计 | 9,556 个连续状态，两次新绑定均与当 tick 原生接触力和穿透量一致 | [审计](evidence/runs/easy_qualified_audit_01/execution_audit.json) |
| 范围与反例 | 其他 seed、参数/默认值、几何、模板不继承 easy 资格；损坏接触与缺失状态被拒绝 | [资格边界](evidence/supporting/easy_boundary_checks_01/checks.json)、[接触对应检查](evidence/supporting/native_acquisition_regression_01/checks.json) |

[六个实测关键状态示意图](evidence/supporting/easy_audited_execution_figure_01/audited_execution.png)取自之前已审计的完整诊断运行，明确保留其原生 `task_success=False`；它是保存状态的几何示意，不是 RGB 录像，也不增加物理成功次数。[短物体续接图](evidence/supporting/easy_far_released_escape_01/short_continuation.png)则展示规划阶段的物体几何路线。最初离开支撑的 0.1 mm 不包含在正间隙几何证书中，其实际接触和抬升由完整物理状态审计覆盖。

## 终态、碰撞与抓持范围

固定目标区、全尖刺包含、其余部件处于分隔线后、线速度 ≤0.001 m/s、角速度 ≤0.02 rad/s、稳定 2 s 的规则保持原样，允许继续抓持。运输刺球间隙最小 **0.100888 mm**；机器人环境间隙最小 **2.668452 mm**，非相邻机械臂自碰间隙最小 **71.393393 mm**；禁止的机器人接触力和运输刺球接触力均为 0，最大原生接触穿透 **0.131217 mm**。

抓持使用真实双指接触触发的 `contact_weld_v1`，之后由理想六自由度刚性约束保持刺球，**不构成纯摩擦抓取证明**。单一声明接触球域包含两次抓取各自的 30 mm 邻域：局部中心 `[0.0, -0.03594005425704966, -0.05225000000000788]` m，半径 67.513331 mm。两次绑定都重新满足双指原生接触、闭合意图和原 TCP 距离门限；审计分别检查两次取得时刻，不能重用第一次绑定。实际抓取配置见[声明](evidence/runs/easy_qualified_native_01/grasp_region.json)。

配置为 Panda + Robotiq、原生 JOINT_ABS、CPU float64、25 ms World tick / 40 solver 子步、control decimation 1，Task 和辅助抓取按 40 Hz 检查。记录的是 tick 末接触和位姿，不能证明所有积分子步或连续时间完全无穿透。固定安装底座 link0 的桌面接触允许；夹爪内部连杆及腕部配合面不计入非相邻机械臂自碰检查。其他 seed、其他参数、默认 400 Hz、纯摩擦和 RGB/视频均未取得本批资格。

## 资格与历史结果

[诊断执行](evidence/qualification/easy_two_grasp_native_01/oracle_report.json)实际达到相同目标并稳定 2.725 s；其原始 `task_success=False` 保持不变。资格前的[独立审计](evidence/qualification/easy_two_grasp_audit_01/execution_audit.json)通过后，当前 easy 默认参数和 seed 0 获得有限资格，绑定几何生成器、Task 声明、模板哈希和目标区域身份；后续直接匹配原生接触的[加强复审](evidence/qualification/easy_two_grasp_audit_02/execution_audit.json)也通过。本批新增的物理运行从默认 home 重新开始，实际取得原生成功，没有追改诊断结果。

## 复现及归档复核

在仓库根目录执行，输出目录须不存在：

```bash
.venv-gs121-nyx/bin/python scripts/run_hedgehog_oracle.py --variation easy --pickup solvability_proof/hedgehog_in_cage/2026-09-30_easy/evidence/runs/easy_qualified_native_01/submitted_pickup.json --assisted --search-iterations 12000 --max-physics-steps 24000 --output runs/hedgehog_easy_new
.venv-gs121-nyx/bin/python scripts/audit_hedgehog_oracle.py --run runs/hedgehog_easy_new --require-native-success --output runs/hedgehog_easy_audit_new
```

独立审计也可直接读取本归档 `evidence/runs/easy_qualified_native_01`，无需重跑物理。精确复现源码使用各目录 `source_snapshot/` 和 `source_manifest.json`；[依赖版本](evidence/supporting/easy_boundary_checks_01/runtime_versions.json)有单独记录，虚拟环境不打包。资源规则按当前 AGENTS.md：CPU 只监控，系统内存达到 90% 时停止本轮拥有的工作进程；本次原生成功复跑内存峰值为 28.7%。

[汇总](summary.json)、[逐文件清单](archive_manifest.json)和[归档复核](archive_validation.json)记录原路径、独立副本、大小和 SHA-256，并核对冻结源码、报告及物理状态哈希。原始字节和内部历史路径保持不变，访问副本使用汇总里的相对路径。证据在本批本地 `evidence/` 内；传递证明须同时携带该目录。归档不增加物理成功次数。
