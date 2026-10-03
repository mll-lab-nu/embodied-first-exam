# Hedgehog hard：S5 高位支撑、顶部转出

用户批准的 `fixed_v3_s5_post`、默认参数、seed 0 已取得完整有限实例证明。Panda 从默认 home 连续执行，实际抓取 S6，经顶部转出并送入原目标区，第 **6,029 tick / 150.725 s** 原生 `task_success=True`；[独立审计](evidence/runs/native_audit_02/execution_audit.json)核对 **6,030 个连续状态**，`accepted_proof=True`。

新增固定支座半径 8 mm，笼局部 z 从 −102 mm 至 23.5 mm。刺球初始球心 z=72 mm，S5 向下，先由重力下落约 0.5 mm 站稳。原笼柱、顶孔、六刺及目标判定规则保留；[模型验证](evidence/supporting/final_provenance/model_validation.json)确认 640 个原始网格/反例资源成员字节不变，笼体碰撞部件为 612 个。[用户批准](evidence/supporting/provenance/approval.json)明确改变默认初态，省去原笼底取球和中途换抓。旧 `fixed_v2` 不继承此次成功。

## 解法与证据

纯物体路线先在约 72 mm 高度转向，升至约 98 mm，边转边降到约 82 mm，再倾斜升至 118 mm，最终提到 230 mm 完全出笼；之后从上方移至原目标区并降低。坐标为笼局部球心高度。[物体证书](evidence/supporting/body_proof_03/object_report.json)及[独立重建](evidence/supporting/body_proof_03/object_audit.json)验证初态无相交、完整可视/碰撞几何、连续插值及终点全尖刺包含，连续间隙下界 **0.100189 mm**。

机器人从 home 接近支座上的刺球，在 tick 1180 通过当 tick 的原生双指接触获得辅助绑定。实测抓取后重新规划，前段 112 个、后段 2480 个 IK 样本通过几何与关节检查，并执行实际关节控制到原任务成功。全程一次抓取，没有瞬移、预绑定、回溯或设置被动关节。[抓取参数](evidence/runs/native_03/submitted_pickup.json)、[实测前段 IK](evidence/runs/native_03/pickup_departure_plan.json)、[出笼及入区 IK](evidence/runs/native_03/held_plan_0.json)、[完整动作和结果](evidence/runs/native_03/oracle_report.json)、[逐 tick 状态](evidence/runs/native_03/trail/private/physics_states.jsonl)均已保存。

| 独立审计项目 | 结果 |
| --- | --- |
| 初态 | 无相交，严格检查，没有初始穿透豁免 |
| 原目标区 | 全尖刺进入，保持低速 2 s；允许保持抓持 |
| 运输刺球最小间隙 | 0.113980 mm |
| 机械臂与环境最小间隙 | 3.689914 mm |
| 非相邻机械臂自碰最小间隙 | 71.411599 mm |
| 最大原生接触穿透 | 0.024481 mm |
| 禁止的机械臂接触力 / 运输刺球接触力 | 0.0 N / 0.0 N |

**机制限制：** [对照检查](evidence/supporting/body_proof_03/negative_controls.json)中，固定初始朝向直拔被阻挡，但封闭钥匙孔窄槽后的同一路线仍通过。因此本证据证明当前自定义模型可从顶部转出，不证明窄槽必需，也不等同于实物 GEN 的解锁机制。

## 执行范围与复核

Panda + Robotiq、JOINT_ABS、CPU float64，25 ms World tick / 40 solver 子步、control decimation 1；采用 v12 刚体性能配置：关闭 contact islands、分段历史、4 个 Torch 线程。[性能配置](evidence/runs/native_03/performance_profile.json)和[依赖版本](evidence/supporting/final_provenance/runtime_versions.json)随证据保存。Task 与 assist 在 40 Hz 检查；tick 末证据不代表所有积分子步或连续时间均无穿透。固定安装 link0 的桌面接触排除，夹爪内部连杆及腕部配合面不计入非相邻机械臂自碰检查。

抓持为真实接触触发的 `contact_weld_v1`，不构成纯摩擦证明。其他 seed、参数、默认 400 Hz 及 RGB/视频资格未扩大。系统内存达到 90% 时守护器停止本轮 worker；本次原生执行峰值 52.6%，CPU 仅监控。

仓库根目录的复现命令（输出目录必须不存在）：

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/run_hedgehog_oracle.py --variation hard --seed 0 --pickup solvability_proof/hedgehog_in_cage/2026-10-03_hard_s5_post/evidence/runs/native_03/submitted_pickup.json --assisted --search-iterations 2500 --max-physics-steps 24000 --output runs/hedgehog_hard_post_new
.venv-gs121-nyx/bin/python scripts/audit_hedgehog_oracle.py --run runs/hedgehog_hard_post_new --require-native-success --output runs/hedgehog_hard_post_audit_new
.venv-gs121-nyx/bin/python scripts/plan_hedgehog_object_oracle.py --audit solvability_proof/hedgehog_in_cage/2026-10-03_hard_s5_post/evidence/supporting/body_proof_03/object_report.json --output runs/hedgehog_hard_post_object_audit_new
```

审计也可直接读取归档中的 `evidence/runs/native_03`。精确历史代码见各运行的 `source_snapshot/` 与 `source_manifest.json`，运行依赖和虚拟环境不打包。[归档清单](archive_manifest.json)及[逐文件复核](archive_validation.json)覆盖独立副本、大小、SHA-256、源码和物理状态哈希；交付完整证明时需携带本地 `evidence/`。原始报告中的绝对路径仅保留为来源记录，访问副本使用[汇总](summary.json)里的相对路径。

`native_02` 和其审计已成功，但当时资产报告漏计新增支座。更正仅涉及资产报告与构建来源记录，几何字节相同；本批以最终资源重新运行的 `native_03` 为唯一正式成功实例，不重复计数。模型打包初次错误与其他研究失败仍保留在原 runs，未追改。easy、medium 的既有正式批次不变。

[目标框补查](../2026-10-03_scope_review/README.md)：新初始朝向使自动目标框略大，但同一条原生轨迹按旧目标框检查仍稳定满足 2 s。数值目标框并非完全不变；目标生成规则未改动。
