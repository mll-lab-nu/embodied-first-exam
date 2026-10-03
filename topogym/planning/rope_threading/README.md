# Rope Threading oracle

## 已验证的开发参考（seed 0）

Easy、Medium、Hard 均已从标准 home 达到原生 `task_success`，逐 tick 证据完整。
参考轨迹及实测报告保存在 [`reference_relays/manifest.json`](reference_relays/manifest.json)。
入口校验轨迹哈希、变体、模型参数与完整成功报告，然后使用统一 Env／SegmentRunner 执行：

```bash
.venv-gs121-nyx/bin/python -m topogym.planning.rope_threading.profiles \
  --variation easy --execute-reference --output runs/oracle_dev/rope_easy
```

将 `easy` 改为 `medium` 或 `hard` 即可运行另一档。输出目录必须是新目录，执行证据在其 `execution/`。
这是显式 `contact_relaxed_v16` 开发配置：5 MPa 初始 U 形参考绳、较粗四面体网格、
机器人 IPC 手指接触、调整后的环架布局、圆环截面孔径判定及 1 mm 接触余量；
末态按 1 cm/s 持续 0.5 秒停稳。使用 4090／v12 加速选项，默认不录视频。
原生任务成功与默认模型的物理精度、收敛性和视频资格分别记录。

## 常规场景的 Wang 0° 规划入口

以下为未应用上述开发配置的基础配方和重新规划流程；其历史 IK 结果不继承开发参考的物理成功。

三档共用物体路径、ALOHA IK 和接力控制器，按变体选择独立方案：

| 变体 | 默认方案 | 关键换抓 |
| --- | --- | --- |
| easy | `A10_B_pull19_B20_recvA` | R1 右手送、左手接；左手在绳尖后 20 cm 换抓，送过 R2，右手接 |
| medium | `A10_B_pull19_B24_keep_recvA5` | 左手在绳尖后 24 cm 换抓，给 R3 交接和送绳手撤回留出空间 |
| hard | `A10_B_pull19_B24_keep_recvA5` | 换抓点改为绳尖后 24 cm，末环 poke 为 5 cm |

`A=right, B=left`，IK hold 采样间隔默认 10 mm。配方在 `profiles.py`、
`hard_plans.json`；`geometry.py` / `object_oracle.py` 构建物体路径证据，
`relay_kinematics.py` / `relay_ik.py` 做只读 IK、Jacobian 和碰撞检查，
`relay_policy.py` 通过普通 `JOINT_ABS` 回放规划关节，跨过 ViperX 腕部奇异点。
approach／pinch／hold 的实测站点偏移使用规划关节作为 IK 种子；其余阶段直接回放。
无物体瞬移、无运行时 `set_qpos`。

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
`--tooling-ipc` 使用 v12 rope 的单子步、Newton/PCG 1e-3/1e-5 和 `linear_bvh`。
旧 Harbor 包的 75° 冻结静置态不适用于当前 0° 场景，不加载该静置态。
`SegmentRunner(history_privileged="reference")` 保留 `world` 权限声明并引用属主证据，避免重复写入 FEM 数组。
执行器检查轨迹中的变体、seed、实例／资产、robot mount 和 home 身份。
旧的无身份 NPZ 必须重新生成，不直接作为本仓库轨迹执行。

来源清单与原始导入哈希见 `wang_source.json`。附件声明三档 IK 已验证，物理作业均取消；
其中的 IPC 轴补丁已由本仓库 `world/physics/ipc.py` 覆盖，无需另打补丁。
整合时保留核心 IK 算法，纳入当前实体底座碰撞检查，修正带 `/via_home` 等后缀的阶段序列化，
回放采用固定插值起点并限制平移／旋转速度，抓持等待实际 native solve 并检测丢失。

IK 只证明采样点的可达与间隙；物体模型仍假设绳沿固定路径滑动，并有无人抓持的换抓阶段。
关节回放保持名义分支，但实测反馈与连续插值不能继承离散 IK 的碰撞证书。完整物理通过须原生 Task
`task_success`、终止和完整逐 tick 证据；`policy_done` 不代表成功，成功时允许仍抓持。
实际验证范围见[任务页](../../../docs/develop/tasks/rope_threading_zh.md)。

回归入口：`.venv-gs121-nyx/bin/python ci_checks/test-rope-threading-oracles.py`。

2026-10-03 初次整合的 seed 0 复验：三档物体路径均通过，easy / medium / hard 的
首选方案分别生成 452 / 466 / 500 个通过的 IK 样本；18 项接入回归和 6 项场景回归通过。
记录见[整合报告](../../../runs/test_results/rope_threading_wang_integration_20261003/integration_report.json)，
其中 easy 样本通过新增的非运动手连续性校验；medium／hard 旧样本在 R3 pinch 意外重置
持绳手，已被加载器拒绝，需用修复后的分支规划器重新生成。该历史报告不证明物理成功。

后续连续性修复的证据在 `runs/test_results/rope_threading_relay_continuation_20261003/`：
easy 沿用通过连续性检查的 452 点；hard 重算为 546 点；medium 采用相同 24 cm 配方，
通过 `--reuse-samples` 对新场景的所有样本重新检查后导出独立 546 点轨迹。
复用要求 mount/home、材料站点路径和配方匹配，并重新运行目标任务的物体证书和机器人碰撞检查，
不会沿用原变体的通过标签。

`--free-speed` 单独设置自由运动速度，`--grasp-max-strain` 显式设置辅助抓持的材料边长比门槛；
`--rope-young-modulus` 通过 calibration tools 在新场景建场时试验 FEM 材料，不改动已安装 Task。
`--feedback-joint-limit` 设置站点反馈 IK 相对原规划关节的偏差上限（默认 0.25 rad）；
`--ipc-tolerance-scale` 可显式缩放 v12 的两项收敛容差，非 1 值标记为独立求解器实验。
这些设置连同实际时序记录到报告。最后一次抓持后保持姿态，等待原生停稳窗口；不额外松手。
超出位置反馈上限立即报告模型偏差，不再将目标截断到一个不在真实绳上的位置。
`--material-feedback` 在接近时测量实际材料切线，并绕抓取站点修正夹爪姿态；
偏差超过 0.8 rad 拒绝执行，修正在最初 10 cm 的持绳运动内逐渐消退。
它需要新生成、带 `station_tangent` 的轨迹。此反馈仍经过规划关节作种子的 IK，
不修改绳节点，也不能继承名义路径的碰撞资格。

`--material-tangent` 是 IK 规划器的实验选项，保持抓持材料轴朝向模型切线；
`--material-tangent-delay` 允许先离开桌面后逐渐对齐。原来的 pad-plane 模型仅约束夹爪闭合轴，
实测不能保证自由绳端跟随规划路径。上述实验选项尚不能解释为三档物理成功。
`--material-axis-tolerance-deg` 允许有限的材料轴倾斜；第一段延迟对齐期间另有逐步收敛过程。
`--material-tangent-min-lead` 可只在自由绳端足够长的送绳阶段施加材料方向约束。
`--max-holds` 导出局部探针，报告为 `robot_ik_prefix_verified`；执行必须显式加 `--allow-prefix`，
局部轨迹不能通过缓存复用变为完整方案。是否完成原生任务仍由真实 Task 判定。

`plan_rope_threading_oracle.py --task-parameters-json candidate.json` 可冻结显式建模候选。
例如 `{"rope_mesh":{"spacing":0.0055,"sides":12},"rope_material":{"E":5000000},"rope_reference_shape":"initial"}`
采用较粗的同类四面体网格和无初始预应力的弯绳。`rope_reference_shape` 默认仍为 `straight`；
`initial` 只改变弹性参考坐标，材料站点和辅助抓持的材料身份仍用原直绳坐标。
`robot_riser_height_m` 可另设底座高度。候选参数、资产哈希和机器人场景贯穿 object witness、IK 和物理执行，
不能把候选的成功标签转移给默认任务。所有这些选项都不改变环的数量、孔径或穿越成功检查。

IK 的 `--support-regrasps` 在同手换抓前插入另一只手的静止抓持，并重新检查该抓持及接近／撤离路径。
执行顺序为辅助手抓住、原手松开并换抓、辅助手松开；双手抓持期间不推进材料行程。
缓存样本必须具有完全相同的抓持顺序、站点及行程，才可逐点复验。
`--measured-keeper` 让执行器在静止辅助手阶段读取真实 FEM 站点，调用 calibration adapter
在独立 CPU 机器人场景中重选绕绳姿态、规划接近和撤离；CUDA 物理场景不会被规划器写入。
每次规划保存输入、完整关节路径和碰撞结果到 `calibration/keeper_XX/`。
直接关节接近擦到环缘时，先尝试肩／肘等关节的短绕行；每段仍按原采样步幅检查，
不会为绕行移动另一只持绳手，也不会自动提高允许挤压门槛。
允许软绳与手臂接触，保留环架、台面、自碰撞和双臂检查；实际抓持仍等待原生健康状态。
静态修复或辅助抓持成功均不代表完整穿环成功。

`--measured-regrasps` 配合 `--measured-keeper --normalize-keeper`，在 R1 之后的接力抓取
重新测量绳形并规划真实抓取，再在双手持绳时移动到名义推进起点。它保留后续整段行程，
不会因超过普通 8 cm 反馈上限而直接拒绝可规划的换抓。
Task 参数 `aperture_contact_allowance_m` 默认 0，可显式设置至绳半径的一半；
开发候选用 1 mm 放宽中心线孔内余量。此参数只允许判定中的轻微挤压，物理环孔与接触仍保留。
`aperture_check_profile=round_ring` 在前后厚度平面使用实际圆环截面的较大孔径，
中央平面保持相同孔径；默认 `cylindrical` 保留旧的恒定最小孔径近似。
两项参数均绑定 Task 身份，原生判据和对象路径检查使用同一计算。

完整接力以最后抓持停稳为终点，规划器不再要求目标之外的最终松手／回 home。
若缩短配方以最后送绳直接结束，可用 `--reuse-samples ... --reuse-leading-holds` 选择完整缓存
中的精确前缀；目标对象路径需重新取证，抓持顺序、每段终点、材料站点及整段机器人碰撞
均重新检查，不插值捏造终点，也不接受局部源轨迹冒充完整目标。

开发候选 `rope_robot_contact="fingers"` 只让四个夹爪手指参与机器人的原生 IPC 接触，
避免粗手臂网格在换抓时推走绳身。该底层链接过滤同时作用于 IPC 环架，不仅作用于软绳；
绳／环、手指／环接触以及机器人自碰撞、机器人／台面刚性接触保留。
规划按 Task 的相同链接集合检查环架：`fingers` 候选检查手指，`full` 检查整臂。
台面、自碰撞、双臂和底座检查仍覆盖整臂；这些采样检查不代表完整物理资格。
默认仍为 `full`，接触候选绑定新的 Task 身份，IPC 状态记录实际四个启用链接。
规划可显式设置零间距及 `--max-penetration-mm 3`，接受 FCL 估计深度至 3 mm 的轻度接触，
报告保留 `allowed_contacts` 和超限的 `rejected_contacts`。这只是几何接触估计，执行仍由原生物理处理。
运行选项 `--grasp-follow-error` 和 `--grasp-max-penetration` 分别控制辅助抓持跟随及挤压门槛；
默认 10 mm／2 mm，开发试验可显式放宽，均写入运行配置。

`--allow-covered-grasp` 关闭 soft target 的重力向上遮挡检查，适用于另有绳段在上方的侧向抓取。
它保留同一材料区域的双指表面近接与材料归属；`require_exposed_patch` 的默认值仍为 true。
`--normalize-keeper` 必须配合 `--measured-keeper`：获得原生健康辅助抓持后，在两手持续抓持
的条件下，通过检查过的机器人路径将绳身抬回参考位置／方向，再让原手松开换抓。
所有运动仍是普通 JOINT_ABS 指令，规划器不会修改绳节点。
若归位可达但腕部属于另一分支，校准可重算本次抓持后**整段**推进的关节路径，
保持每个原 TCP 目标，并检查关节限位、连续性和刚性碰撞；不再强行旋回旧关节角。
另一只手的撤离另行实测规划，后续推进检查按缓存的停放姿态进行；未来 FEM 绳形未知，
仍由原生接触和抓持健康检查约束执行。`follow_rows`／`follow_checks` 保存全部替换与检查，
不接受局部替换，也不修改源轨迹文件。左手优先尝试已经过物理执行的 −20° 接绳姿态。

当前接触放宽候选可从源码导出，避免依赖手工编辑的 runs 配置：

```bash
.venv-gs121-nyx/bin/python -m topogym.planning.rope_threading.profiles \
  --variation easy --output runs/oracle_dev/rope_easy_profile
```

`medium`、`hard` 同样支持。生成的 `task_parameters.json`、`route.json`、`relay.json`
分别传给对象规划器；`plans.json` 传给 IK 规划器。`profile.json` 保存完整的 `ik_args` 和
`execution_args` 参数数组。该配置明确标记 development，是否完成仍以每次原生运行报告为准。
v16 显式采用 `terminal.maximum_speed_m_s=.01` 与原来的 0.5 秒稳定时长；
默认 Task 的 1 mm/s 门槛不变。Easy 的 R2 与三环候选对齐；Hard 仍保留原孔径。
可选 `geometry.ring_inner_radii_m={"R2": .058}` 只调整单个环并同步移动支架，
不会改变其中心、法向或其他环；它是独立建模候选，并非 v16 必需项。

导出时增加 `--execute-samples <relay_samples.npz>`，即可按该候选的完整执行参数调用
统一 runner，证据写到输出目录的 `execution/`。入口先核对变体、完整轨迹资格与 Task
参数，不接受其他模型的缓存；执行仍从标准 home 开始，默认关闭 RGB。例：

```bash
.venv-gs121-nyx/bin/python -m topogym.planning.rope_threading.profiles \
  --variation easy --output runs/oracle_dev/rope_easy_execution \
  --execute-samples runs/test_results/rope_threading_goal_20261003/easy_ik_v16_quiet/relay_samples.npz
```

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
