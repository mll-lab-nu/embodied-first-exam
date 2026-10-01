# Lock Picking：完整机械臂流程与逐动作 IK 证明

本批补齐[上一批物体路径与名义 IK](../2026-09-30_object_ik/README.md)没有执行的机器人过程：默认 home → 空手接近 → 双指抓取 → 抬起钥匙 → 插入、转动及回退换槽 → 机构支撑下释放、撤离并重新抓取 → 穿过 END → 最终松手、撤离和静置。每个变体是一局连续 Genesis 物理执行，两个 segment 首尾相接，没有回溯或拼接。

验收范围是**接触触发辅助抓持下的完整机器人过程**。当前原生 Task 的 `goal_complete=False`，三档 `task_success` 仍为 false；本批不增加全局正式 benchmark 成功数量。下方数据以三个独立复核报告为准。

| 变体 | 回退次数 | 实际仿真时间 | 笛卡尔 IK 查询 | IK 最大位置误差 | 最小关节限位余量 | 完整流程独立复核 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| easy | 1 | 124.7 s | 972 | 0.009826 mm | 0.054919 rad | [通过](evidence/audits/easy_audit_01/robot_process_audit.json) |
| medium | 2 | 159.2 s | 1,270 | 0.009965 mm | 0.022806 rad | [通过](evidence/audits/medium_audit_01/robot_process_audit.json) |
| hard | 3 | 194.7 s | 1,571 | 0.010003 mm | 0.018171 rad | [通过](evidence/audits/hard_audit_02/robot_process_audit.json) |

共 **3,813 次笛卡尔 IK 查询、4,789 个保存状态**。三档 IK 查询与 Env 实际关节目标的最大差异均为 **0 rad**；实测关节 FK 与保存 TCP 的最大位置差异小于 0.00002 mm。所有检查过的状态均无关节越界或下述禁碰；以下间隙不包含允许的手指／握柄与钥匙／槽壁接触。

| 保存状态的最小几何间隙 | easy | medium | hard |
| --- | ---: | ---: | ---: |
| 机器人／场景 | 7.344 mm | 7.354 mm | 4.331 mm |
| 非指机器人／钥匙 | 2.184 mm | 2.200 mm | 2.197 mm |
| 手指／钥匙杆与齿 | 11.350 mm | 11.351 mm | 11.349 mm |
| 所检查的非相邻机械臂几何 | 62.486 mm | 45.828 mm | 41.881 mm |

| 抓持事件发生 tick | easy | medium | hard |
| --- | ---: | ---: | ---: |
| 初次双指抓取 | 131 | 131 | 131 |
| 机构支撑下释放 | 845 | 1190 | 1541 |
| 重新双指抓取 | 988 | 1333 | 1684 |
| END 最终释放 | 1204 | 1549 | 1903 |

释放并静置后的前齿穿出余量分别为 **1.328／1.601／1.343 mm**，均满足未改动的 1 mm 门限；余量是最终实测值，不用进给指令值代替。

## 从物体路径到机械臂 IK

三档沿用同一个构造。第一片 D1 的局部槽中心分别为 `[-30, 0]`、`[-60, -30, 0]`、`[-72, -48, -24, 0]` 度，允许转角分别为 ±15°、±15°、±12°。进入 D2 后联动转动；达到本次行程末端便退出 D2、仅在 D1 啮合时反向复位，再退入盘间空隙转钥匙选下一槽。D2 保留先前获得的转角，重复 1／2／3 次后使 D1、D2、D3 和 END 的槽相通。完整物体模型及回退下界见上一批。

本次机器人控制在第一片限位前保留名义 1.5° 余量；转钥匙时计入 4° 槽齿余隙，每次重插都从实测盘角计算两个孔槽的交集。它沿用前批构造，但不是逐点复用前批理想轨迹：实际盘角、机构支撑下的下沉、换抓后的相对位姿都由反馈处理。

持件时，设实测钥匙位姿为 `T_WK`，TCP 位姿为 `T_WT`，先得到 `T_KT = inverse(T_WK) * T_WT`，再把目标钥匙位姿变为 `T_WT_target = T_WK_target * T_KT`。精细插入阶段保留前一条 TCP 指令中的负载补偿，并根据实测钥匙误差追加有界修正。换抓之后重新建立这个变换。空手段用位置平滑插值和姿态 SLERP，夹爪开合由普通 action 给出。

`RecordedIKPolicy` 在每条笛卡尔 action 执行前，用当时实测的完整关节向量作为 IK 初值，包含被动夹爪坐标；扣除配置中的手部至 TCP 偏移后查询 Genesis IK。查询检查关节限位，并用独立 FK 记录位置和姿态残差。原 action 随后交给 Env 编译执行，复核器逐条比较查询结果与 `executed_joint_targets`。空 action、保持和单独夹爪动作同样写入日志，但不重复计为笛卡尔 IK 查询。

策略只实现 `act(obs)`，使用 unlimited 观测反馈并输出普通 `EE_ABS` 动作。它不持有 Scene，不设置钥匙／锁片状态，也不手动建立抓持约束。两次抓取均由真实闭爪动作和同一末子步的双指接触触发 Env 的 `contact_weld_v1`；这仍是理想六自由度辅助约束，不构成纯摩擦抓持证明。

## 实际换抓与末态

第一次穿入 D3 后，策略开爪并等待机构支撑钥匙；空爪后退 80 mm、抬高 120 mm，根据当时钥匙位姿重新定向和接近握柄，再次闭爪取得双指接触，校正并重插 D3。最后进给至 END，松手等待 2 秒，空爪上移 130 mm，要求至少连续 0.5 秒无抓持且钥匙线速度小于 0.01 m/s、角速度小于 0.1 rad/s。

easy、medium 的最终指令深度为 4.08 个盘距，hard 为 4.10。hard 首次也用 4.08：机器人完整动作执行完毕，但释放后回滑，前齿越过 END 外表面的余量只有约 0.8 mm，低于原有 1 mm 门限，因此运行及独立复核均拒绝通过。随后只将 hard 最后进给增加 3 mm，从默认 home 重新执行整局；没有放宽门限或修改 Task／几何。首次失败的完整运行和复核分别保存在 [hard_01](evidence/failed/hard_01/run_report.json) 和 [失败复核](evidence/failed/hard_failed_audit_01/robot_process_audit.json)。

静置时钥匙杆自然靠在孔壁上。本批独立末态检查要求前齿完整穿出至少 1 mm、杆贯穿机构、无齿／板干涉，并显式允许 0.2 mm 径向接触柔顺量；这与 Task 的严格正间隙／同轴检查分别记录。三档末态 `coaxial=False`，也仍缺原 Task 的机构过载／退回资格与阈值校准，不能据此将 `task_success` 改为 true。

## 复核范围

- **连续性与身份：** 默认 home 出生、同一 episode、branch 0、逐 tick 连续编号、两个 segment 状态引用首尾相等；冻结源码哈希和重建场景的实例／资产哈希匹配。
- **机器人：** 实测全关节 FK 对应实测 TCP；机械臂关节不越界；记录相邻 tick 最大关节变化。IK 查询与实际执行目标一一对应，覆盖空手、持件、换抓和撤离。
- **几何：** 按引擎导入的每个凸碰撞片分别建立 FCL 查询，不对锁孔整体取凸包。使用每个保存 tick 的实测 link 位姿，包括被动夹爪连杆。检查机器人／场景、非指机器人／钥匙、手指／钥匙杆及齿、112 对非相邻机械臂几何。
- **接触：** 只允许手指与握柄接触；双指抓取事件与保存的原生接触数组核对。机器人／非钥匙场景接触力超过 0.1 N 会拒绝；钥匙推动槽壁属于任务需要的接触。
- **终态：** 实测回退数为 1／2／3；两次取得抓持和两次释放；完整换抓及撤离阶段存在；重新计算穿出、径向容纳与最后 0.5 秒静置。

几何自碰撞检查排除同一 link、机械臂索引相差不超过 2 的近邻、两者索引均 ≥6 的腕部／工具安装及夹爪内部配合；仅 `robot/link0` 排除桌面安装接触。不能把这称为所有 link 对的无条件自碰撞证明。碰撞检查覆盖 **100 ms 间隔的全部保存状态**，接触数据为每个 World tick 最后一个 solver 子步；没有对全部 160 个子步或连续时间做扫掠碰撞证明，也未增加力矩、速度极限资格。

## 测量轨迹与证据

[轨迹图 PNG](measured_robot_process.png) · [可导出 PDF](measured_robot_process.pdf) · [汇总 JSON](summary.json) · [归档清单](archive_manifest.json) · [副本与哈希核验](archive_validation.json)

图中三列分别对应 easy／medium／hard，展示实测插入深度、钥匙与三片盘角、七个机械臂关节；绿色线为自动抓取，紫色线为释放。最终自由释放后钥匙可绕自身轴滚转，图中的角度跳变不代表杆轴倾倒。图由记录值绘制，没有生成机器人预演帧。

每个 `evidence/runs/<run>/` 都包含原始 `run_report.json`、连续 segment 账本 `report.json`、`private/physics_states.jsonl` 及所引用数组、`private/control_steps.jsonl`、`private/lock_monitor.jsonl`、`private/robot_ik.jsonl`、场景配置／资产、引擎身份、冻结源码与哈希、资源监控。每个 `evidence/audits/<audit>/` 另存复核源码、重建场景、逐 tick 碰撞距离和复核报告。归档为独立文件副本，不依赖原 `runs/` 目录；原始报告不改写。

固定范围：默认参数、seed 0、Panda + Robotiq、CPU float32、World tick 0.1 秒、160 子步（积分步长 0.625 ms）、control decimation 1、接触辅助抓持。每档仅此一个通过实例，不能推广为多 seed、随机参数域、默认时序或 GPU 数值一致性证明。本批显式关闭 RGB，没有新增视频；上一批保留的视频是历史参考，不充当本批录像。CPU 仅监控，系统内存达到 90% 时由 guard 停止本轮进程。

## 复现

活动入口：[执行器](../../../scripts/run_lock_picking_policy.py)、[三档反馈策略](../../../topogym/planning/lock_picking/reindex_policy.py)、[逐动作 IK](../../../topogym/planning/lock_picking/recorded_ik.py)、[独立复核入口](../../../scripts/audit_lock_picking_robot.py)、[状态复核](../../../topogym/planning/lock_picking/robot_audit.py)、[碰撞复核](../../../topogym/planning/lock_picking/robot_geometry.py)。准确批次身份以归档快照为准，共享工作区后续变化不自动继承此次验收。

在仓库根目录执行；所有输出目录须尚不存在。命令与本批相同，包含 easy／medium 的 4.08、hard 的 4.10 末端深度。

```bash
set -e
for variation in easy medium hard; do
  endpoint_depth=4.08
  if [ "$variation" = hard ]; then endpoint_depth=4.10; fi
  .venv-gs121-nyx/bin/python scripts/run_lock_picking_policy.py \
    --output "runs/test_results/lock_robot_reproduce/${variation}" \
    --variation "$variation" --route-mode reindex --setting current --part solve \
    --grasp-style side --grasp-roll-deg -45 --endpoint-depth "$endpoint_depth" \
    --physics-dt .1 --solver-substeps 160 --control-decimation 1 \
    --compute-backend cpu --precision 32 --no-rgb --audit-ik
  .venv-gs121-nyx/bin/python scripts/audit_lock_picking_robot.py \
    --run "runs/test_results/lock_robot_reproduce/${variation}" \
    --output "runs/test_results/lock_robot_reproduce/${variation}_audit"
done
```

运行退出码 0 只表示 runner 的路线末态检查通过，还须取得独立复核的 `passed=true`。复核失败退出码为 2；`--allow-failed` 可诊断封存的失败运行，不能使失败运行获得通过标签。`--geometry-probe` 仅检查查询准备，不是机器人执行证明。要新增实际视频，必须另行使用 CUDA／Nyx 和公共录制模块完成运行或按原记录状态重渲染，并单独验证录像身份；本批 CPU 结果不推断其通过。
