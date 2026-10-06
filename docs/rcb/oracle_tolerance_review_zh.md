# Oracle 位姿与路径门槛 review

2026-10-06，源码基线 `7571e4194ac580c0c13c4443d5203541004d7862`。

本轮按用户要求审查所有 oracle：**参考位姿是帮助找到解的目标；实际可执行的路径和原生 Task 成功才是验收依据。** 不应仅因偏离任意参考位置、朝向或关节分支就认定任务不可解。

下文 review 保留审查时的基线。随后按用户授权，仅对 `very_easy` / `easier` 实施第 1、2、4、5 项；实现和验证范围见下一节。第 3 项阶段到达阈值没有调整；公共模拟器、冻结实例、物理参数和 Task 成功条件没有修改。

## 两档实施结果

- **通用 IK**：新增私有 [`oracle_ik.py`](../../topogym/planning/oracle_ik.py)。优先使用原精确解；精确拟合失败后，尝试原种子及两个确定性种子，候选搜索预算为 **5 mm / 0.1 rad**。这些数值只限制候选搜索，不能代替路径检查或 Task 验收。接受/拒绝记录包含精确求解的错误、候选实际 FK 残差及路径检查结果，写入 `ik_candidates.json`。
- **耦合 IK**：Keyhole、Horseshoe、Claws 的微米级参考残差不再单独拒绝两档中的近似候选；工作区中心作为偏好。候选仍须满足位置/朝向搜索预算、真实关节范围、当前场景的采样路径检查。原三档没有进入此作用域，继续使用原门槛。
- **实际几何**：Buzz/Fiber 的共享搬运路径、Hedgehog 持物路径、Keyhole 目标搬运、简化 Claws 预检及 Horseshoe 耦合规划，按候选关节 FK 和抓持偏移重建携带物姿态。新 [`oracle_path.py`](../../topogym/planning/oracle_path.py) 检查机器人、夹爪和刚体携带物的关节插值；原生球/盒/地面等使用解析几何，网格按原生凸性标记处理，非凸孔洞保留。被动刚体抓持要求实测双指接触力；这里只建立规划用携带关系，不添加物理约束。
- **路径候选**：Rope 两档在执行穿环搬运前尝试 **10 / 6 / 3 cm** 中间高度、**0 / ±10°** yaw、先抬升及直接关节过渡，共至多 18 条候选。转动时保持指定指垫接触点；各候选整段检查关节范围、自碰撞、桌面、双臂及环/支架间隙。公开动作范围也参与预检。只有浮点表示导致的限位边界残差可向内规范化，实质越界仍拒绝。有限候选耗尽报告“当前搜索未找到经过检查的路径”。`threading_planning.json` 保存候选、阶段和实测跟踪结果。
- **作用域**：接入当前 catalog 中 12 类任务的 24 个两档 Session 入口，涵盖直接 EE 编译及限速执行器；Rope 本地开发 runner 同样接入。共享规划器需要处于 `below_easy_scope` 才启用新逻辑。Slotted Post Ring 两档仍没有 catalog callback，本次没有补造完整 oracle，也不把它计作已接通。

新采样检查对移动中的既有碰撞保守拒绝，仅豁免不变的静态接触及已识别抓持的自身手指接触。它**不是连续碰撞证明或软体动态证明**；原有各任务的间隙检查、接触/失抓保护、原生物理有效性和成功条件继续执行。原生成功、回放成功与这些候选检查分别记录。

验证产物位于 [`oracle_tolerance_implementation_20261006`](../../runs/test_results/oracle_tolerance_implementation_20261006/)：19 项新增回归覆盖碰撞否决、路径中段碰撞、携带物随 FK 移动、被动双指证据、双臂/夹爪组合命令、公共范围、两档隔离和 Rope 备用路径；另有 15 个相关回归套件共 188 项，共 **207 项通过**。Keyhole 的旧测试夹具补齐必需的 `action_layout` 后复跑通过。CPU Genesis 探测检查真实场景 38 个碰撞几何、静止及小幅运动、IK/FK 回查，查询没有改写实测关节状态，物理步数为 0。最终测试索引见 [`validation.json`](../../runs/test_results/oracle_tolerance_implementation_20261006/validation.json)，本次改动身份见 [`source_identity.json`](../../runs/test_results/oracle_tolerance_implementation_20261006/source_identity.json)。

**未新增 v18 完整物理成功结论。** 当前 `nvidia-smi` 无法连接 NVIDIA 驱动；CPU 探测不包含绳/IPC、Nyx 或完整 Task 执行。特别是之前 Rope very_easy 的丢抓、easier 的动作范围问题，还需要在新的候选路径上重新执行验证。

GPU 环境下可用以下命令构建独立 v18 候选并执行两档 Harbor 验收，不激活或覆盖现有 release；只复查 Rope 时将家族数组缩为 `rope_threading`。构建和运行工具保留源码身份、资源监控与原生录像/回放证据。

```bash
cd /home/jianwen/topogym
oracle_candidate="runs/test_results/oracle_tolerance_v18_gpu_$(date +%Y%m%d_%H%M%S)"
oracle_families=(cast_coil cast_keyhole lock_picking buzz_wire_3d fiber_bundling interlocked_claws rope_threading knot_untying blanket_flatten orbits hedgehog_in_cage horseshoe_ring)
.venv-gs121-nyx/bin/python scripts/topogym_merge_candidate.py \
  --output "$oracle_candidate" --families "${oracle_families[@]}" \
  --tiers very_easy easier --image local/topogym:oracle-tolerance-v18-cu128 --gpu 0
.venv-gs121-nyx/bin/python scripts/topogym_candidate_pipeline.py \
  --candidate "$oracle_candidate" --phase build --gpu 0
.venv-gs121-nyx/bin/python scripts/topogym_candidate_pipeline.py \
  --candidate "$oracle_candidate" --phase preflight --gpu 0
.venv-gs121-nyx/bin/python scripts/oracle_runners/test_harbor_oracles.py \
  --tasks-root "$oracle_candidate/tasks" --candidate --families "${oracle_families[@]}" \
  --tiers very_easy easier --modes privileged standard \
  --output "$oracle_candidate/harbor-oracles" --execute
```

## 覆盖与证据

- 审查 13 类任务的本地规划/控制实现、原三档和简化档的分派，以及公共 IK、原生动作编译、Harbor 桥接和共享刚体参考控制器；补查 Cube 示例。
- 静态解析 175 个源码文件，记录 23 个 `solve_checked` 调用点（含原生动作编译）和 137 个候选拒绝分支。候选分支是检索证据，不等于 137 个缺陷。
- 当前 catalog 的 65 个「家族 × 五档」组合中，57 个有 Session callback。Orbits 原三档和 Slotted Post Ring 五档没有该 catalog callback；已检查其本地实现，不将它们描述为完成了 Harbor 接线或完整成功验收。
- 每个扫描文件的 SHA-256、调用表达式、显式参数及 `**kwargs`、入口覆盖见 [源码清单](../../runs/test_results/oracle_tolerance_review_20261006/source_inventory.json)。不能仅按调用点是否显式写容差推断默认值：Slotted 使用 `**self.tolerances`，Fiber/Hedgehog/Orbits 还存在继承或复用。
- very-easy Rope 的已证实失败来自绑定 `merged-v18` 的运行：见 [bridge_report.json](../../runs/test_results/harbor_below_easy_v18_20261005_01/trials/rope_threading/very_easy/attempt-20261006T124633-257137/jobs/001-oracle/topogym-rope-threading-very-easy__hEu49eY/artifacts/app/output/bridge_report.json)。其他门槛的 review 结论不等于已经实测证明其造成失败。

## 主要发现（按整改优先级）

### 1. 高优先级：通用 IK 精度成了任务无关的硬门槛

[`GenesisIKSolver.solve_checked`](../../topogym/solvers/genesis_kinematics.py) 默认按 **0.1 mm / 0.001 rad** 拒绝候选。其内部求解的 `pos_tol=1e-5`、`rot_tol=1e-4` 是更精细的优化目标，应与最终是否接受候选分开理解。

这个默认门槛经直接调用或继承进入 Buzz、Fiber、Hedgehog、Blanket、Horseshoe、Claws 等规划器，也通过 [`robot/control.py`](../../topogym/robot/control.py) 的原生 EE 编译进入 Coil、Keyhole、Lock 和简化 Claws。不能只修改各家族文件里的数字而遗漏 EE 编译路径。公共 `/kinematics` 的 **2 mm / 0.02 rad** 不是上述代码当前实际采用的容差。

Rope 简化档、Knot 和 Orbits 原生控制器复用的 [`KnotIK.solve`](../../topogym/planning/knot_untying/kinematics.py) 写死 **0.5 mm / 0.01 rad**。Rope 原三档的 [`LiveArmIK`](../../topogym/planning/rope_threading/relay_policy.py) 及其 [Session 入口](../../topogym/planning/rope_threading/public_session.py) 又显式指定 **0.1 mm / 0.001 rad**。

**已证实例子：** Rope very-easy 在 `raise_to_ring` 尝试四个种子后停止；最后候选的残差 **1.27072 mm / 0.0181975 rad**。只证明没有候选通过该门槛，不能推出任务无解，也不能推出该候选的实际路径已经有效。

**建议：** 将残差优先用于候选排序。按阶段验证实际末端、抓持物和路径能否完成下一项功能，允许位置区间、朝向范围及对称自由度。普通搬运先尝试较宽候选预算；窄通道和抓取按实际几何、接触条件决定。不能通过全局放宽公共 solver 同时改变普通 agent 的控制合同。

### 2. 高优先级：三种耦合规划器用微米级参考拟合决定成败

- [`CoupledKeyholeIK.solve`](../../topogym/planning/cast_keyhole/kinematics.py)：相对位置 **0.01 mm**、相对朝向 **0.0001 rad**、越出工作区的残差 **0.01 mm**。
- [`CoupledHorseshoeIK.solve`](../../topogym/planning/horseshoe_ring/coupled.py)：同样三项门槛。
- [`CoupledClawsIK.solve`](../../topogym/planning/interlocked_claws/kinematics.py)：同样三项门槛；`solve_world` 为 **0.05 mm / 0.0005 rad**。

这些数值是优化器后验的拒绝条件，不是原生 Task 成功判据。工作区框本身也属于选姿偏好。把越过该框几微米直接当成不可行会扩大假阴性范围。

**建议：** 公共摆位、冗余姿态、工作区中心作为软偏好；相对位姿只保留通过当段几何所需的精度。候选解的实际两件相对姿态通过网格、接触和路径检查后，允许继续，记录相对参考的残差。

### 3. 高优先级：自由搬运也被窄通道级终点误差卡住

- [`CastCoilPolicy.follow_bodies`](../../topogym/planning/cast_coil/policy.py)：所有阶段结束都要求绝对、相对材料位移界小于 **0.25 mm**，包括 `tight=False` 的自由段；自由段推进却允许 **4 mm**。可以沿路线前进，却在已到终点附近长期等待。
- [`SimplifiedCoilPolicy`](../../topogym/planning/cast_coil/simplified_policy.py)：所有阶段结束都要求小于 `min(0.2 mm, 2/3 × seam)`；自由段推进允许 **3 mm**。装配缝隙的预算外溢到了自由搬运。
- [`SimplifiedClawsPolicy.follow`](../../topogym/planning/interlocked_claws/simplified_policy.py)：所有段终点要求材料位移界小于 **0.4 mm**，推进门槛为 **0.8 mm**。
- [`HorseshoePolicy.move`](../../topogym/planning/horseshoe_ring/policy.py)：通用移动结束后要求 TCP 位置小于 **0.5 mm**，超过默认 5 s 等待即失败；没有在这个函数中区分接近和实际夹取。
- [`BuzzWirePolicy`](../../topogym/planning/buzz_wire_3d/policy.py)：默认到达预算 **0.4 mm**，推进 **1.5 mm**；各配方有覆盖值。已有按路线 clearance 缩放的机制，但固定到达门槛仍需要逐阶段检查。

这里的「材料位移界」是平移误差加上物体半径乘转角，并非纯 TCP 位置误差。

**建议：** 自由段以到达可继续下一段的区域、抓持仍有效、下一段路径验证通过为准；保留窄通道横向预算，允许沿通道方向滞后。先投影到当前有效路线或从实测状态重规划，避免从偏离的位置直接跳到下一段。

### 4. 高优先级：放宽 IK 后，部分路径检查仍使用理想物体姿态

[`BuzzIK.plan_held_waypoints`](../../topogym/planning/buzz_wire_3d/kinematics.py) 求得 `q` 后调用 `clearance(q, (p, r))`；其中 `(p, r)` 仍是目标物体姿态，未由候选 `q` 的 FK 和抓持变换重建。Fiber/Hedgehog 的复用路径同样需要检查这个边界。

[`CoupledHorseshoeIK.plan`](../../topogym/planning/horseshoe_ring/coupled.py) 从左件的实际解推导公共变换，再把整组参考姿态转换到世界坐标；右件的相对求解残差不会直接体现为被检查的物体姿态。

因此，「把门槛改大，仍调用原来的碰撞检查」还不足以证明实际路径有效。原先很小的残差掩盖了这部分近似。

**建议：** 从候选关节做 FK，结合当前抓持变换重建实际携带物姿态；使用这些姿态检查允许接触、禁碰、几何余量和整段插值。可参考 Claws 的 `pieces_at(q)`，不能让名义路线的几何证书自动转移给近似 IK 解。软绳还需实测材料位置和动态抓持反馈。

### 5. 中优先级：固定朝向、直线路线和分支偏差被误当作唯一解

Rope 简化档保持夹爪朝下抬到环中心上方 10 cm，随后 very-easy 又要求上方 9 cm；这是配方选取的中间姿态。v18 探测显示下调到 6 cm 可绕过第一处 IK 问题，但后续仍有丢抓/动作范围问题，详见 [v18 探测记录](ORACLE_FIXES_FOR_JIANWEN.md#11-v18-below-easy-oracle-sweep-buzz-fixed-rope-and-knot-easier-analysed-topospeed-2026-10-06)。

Rope relay、Slotted 还存在 IK 分支距离门槛。分支突变需要重采样和验证扫掠，不应简单删除门槛后发送大步关节命令；也不应在存在另一条连续合法路线时直接宣布无解。

**建议：** 保留任务需要的抓持方向，放开无关 yaw/roll、公共摆位和中间高度；尝试邻近目标/替代支路。候选满足公开关节范围与速度、整段路径有效后才执行。有限种子失败应标成「当前候选搜索失败」。

### 6. 中优先级：抓取对准与自由接近需要分开

Knot 的 [`below_easy_runner`](../../topogym/planning/knot_untying/below_easy_runner.py) 在自由接近使用 **20 mm / 0.1 rad**，真正闭爪前使用 **2 mm / 0.1 rad** 并检查当前材料位置；后者针对实际抓绳，不能当作与通用 IK 精度同类的冗余检查。其 [converge](../../topogym/planning/knot_untying/robot_oracle.py) 饱和保护也防止闭在绳旁边。

Orbits 原生控制器的 **1.5 mm** 对准条件也是实际绳段与指垫的接触准备；`reach_row` 中 **2e-6** 比较的是已接受命令与目标，检查限速/保护后的命令传递，不是机械臂实测跟踪精度。

**建议：** 能可靠验证双指接触、材料夹持和试抬成功时，优先使用这些功能条件；只有固定几何对准代理时，需要先补功能验证再放宽。数值有限性、四元数规范、冻结实例身份、序列化往返误差等也不属于参考姿态模仿，不能一并删除。

## 逐家族结论

| 家族 | 实际入口/门槛 | Review 结论与优先动作 |
| --- | --- | --- |
| Rope Threading | 简化档 KnotIK：0.5 mm / 0.01 rad；原三档 relay：0.1 mm / 0.001 rad；简化档还要求关节跟踪 <0.007 rad | 首先改固定高位/朝向的搜索与候选接受；保留实际绳段、抓持及穿环/搭绳验证。已有 v18 假阴性风险的具体失败证据，但放宽后的成功尚未建立。 |
| Knot Untying | KnotIK：0.5 mm / 0.01 rad；preclose 2 mm / 0.1 rad | 放宽通用参考拟合；闭爪前的材料对准用真实接触/试抬替代或补强。不能取消 bias 饱和保护来掩盖没抓到绳。 |
| Blanket Flatten | `Arms.solve` 继承 0.1 mm / 0.001 rad；分阶段接触抓取和布料健康检查 | 自由悬停/搬运采用姿态范围；布面接触、局部抓持、原生铺平/停稳条件保留。固定 top-down 候选不足时扩大姿态搜索。 |
| Cast Coil | 原生 EE 编译继承 0.1 mm / 0.001 rad；终点 0.25 mm，简化档 ≤0.2 mm | 明确的阶段预算混用；优先解除自由段的装配级到达门槛，窄缝横向/转角按缝隙检查。 |
| Cast Keyhole | 原生 EE、预规划 IK 默认 0.1 mm / 0.001 rad；coupled 0.01 mm / 0.0001 rad | 解除微米级相对拟合和工作区框硬拒绝；狭槽相对路径预算保留，基于实际解验证通道。简化档入口采样最小间隙 1.125 mm，当前通过段相对误差界 0.5 mm，不能无依据改成厘米级。 |
| Interlocked Claws | 原三档 coupled 相对 0.01 mm / 0.0001 rad，world 0.05 mm / 0.0005 rad；简化档 EE 默认且终点材料界 0.4 mm | 以实际两件能否分离为准，弱化公共摆位与参考拟合；已具备 FK 重建物体姿态的基础。简化档放宽自由段须与接触/窄口预算分开。 |
| Horseshoe Ring | native IK 默认 0.1 mm / 0.001 rad；规划 coupled 0.01 mm / 0.0001 rad；通用 move 0.5 mm | 放宽自由移动和冗余公共摆位；折叠、环与马蹄接触依据实际几何，修正耦合规划中的名义物体检查。配方内部分 placement 已使用更宽预算，不覆盖其已有设置。 |
| Buzz Wire 3D | BuzzIK 与 CheckedJointPolicy 默认 0.1 mm / 0.001 rad；默认到达材料界 0.4 mm，配方可覆盖 | 无关姿态/自由转移适合放宽；金属触线属于任务失败条件，持物候选必须按实际 FK 与抓持变换复核。 |
| Fiber Bundling | 继承 BuzzIK；配方跟踪/到达约 0.5–1 mm | 通用 IK 严格门槛可重构；保留禁止碰细丝及穿环几何，不能把纤维间隙预算当作普通末端精度去掉。 |
| Hedgehog in Cage | 继承 BuzzIK，Session 执行 measured-route/分阶段抓取；另有共享摩擦基线 | 笼外转移应给朝向/位置自由度；穿笼阶段按尖刺完整外形与真实抓持检查，不继续复用名义球体位置代替实际候选。 |
| Lock Picking | 原生 EE/RecordedIK 默认 0.1 mm / 0.001 rad；`_move_key` 目标 0.15–0.35 mm / 0.0003–0.001 rad，最终拒绝用两倍额度 | 应区分搬运、入孔、旋片三个阶段；孔内需要的轴向/横向/旋转约束分别计算，不使用六维统一小残差代表是否可插入。 |
| Orbits | below-easy 原生 Session 复用 KnotIK 0.5 mm / 0.01 rad；另有 MuJoCo 运动学导入代码 | 原生入口按绳段接触和拓扑进展 review；导入运动学是独立实现，不能冒充 v18 原生 oracle。2e-6 命令传递一致性不应放宽为实测姿态容差。 |
| Slotted Post Ring | 本地 `ArmIK` 默认 0.2 mm / 0.005 rad，经 `**self.tolerances` 传递；阶段重试/功能检查 | 通用抓点 IK 可按阶段重构；保留实际盘/环通过槽和拓扑检查。当前 catalog 没有 callback，不能因门槛修改就宣布接线或完整解法完成。 |

补查：[`CubePickPlacePolicy`](../../topogym/planning/examples/cube_pick_place.py) 使用原生 EE，另有阶段到达 **3 mm / 0.6 s** 的硬等待；[`FrictionReferencePolicy`](../../topogym/planning/rigid_reference/feedback.py) 默认参考终点 **1 mm / 0.01 rad**、跟踪 **3 mm / 0.03 rad**。它们是示例/可复用基线，不应与所有家族当前正式 callback 混为一谈；后续同样改为阶段功能判定。

## 建议的统一接受逻辑

1. **目标表达**：任务需要的接触点、穿孔方向、相对拓扑和目标区域是约束；中间绝对位姿、对称转角、工作区中心和关节分支是可搜索的偏好。
2. **候选生成**：仍尽量求准确的 IK，保留实际残差；没有达到精细优化目标时，把有限的近似解交给后验可行性检查，不直接以 `Unreachable` 终止。
3. **候选验证**：按实际 FK、抓持变换、实测软体状态验证关节范围、允许/禁止接触、物体间隙与连续路径。朝向误差需换算为物体关键点偏移；同一角误差对短柄和长尖刺不是同等影响。
4. **执行与恢复**：动作遵守公共速度/范围；路径跟踪误差优先触发减速、投影到有效路线、重规划或恢复抓取。只有没有可执行候选、功能失败且恢复耗尽、任务原生失败或资源预算耗尽时结束。
5. **验收**：以原生 Task 成功和同一冻结实例的 Harbor 回放为准。不能用修改 Task 的孔内余量、接触/体积有效性或停稳条件来弥补控制器问题。

不建议新设一个适用于全部家族的“大容差常数”。2 mm / 0.02 rad 可作为普通位姿候选预算的实验起点，是否接受仍由上述功能/几何条件决定；它不是窄槽或抓绳的通用通行证。

## 后续修改的验证要求

- 首先对 Rope very-easy 的 v18 失败检查点比较：原门槛拒绝、近似候选残差、实际 FK/关节/插值路径检查、实测抓持和原生终态。降低高度与放宽误差是两种独立改动，应分别记录。
- 每个被修改的阶段至少包含一项「偏离参考但实际有效」正例，以及「残差不大但禁碰/间隙/关节范围无效」负例。
- 对 nominal-body 检查的调用方增加实际候选几何复核后，再放宽门槛；只测试数值比较变化不能覆盖这项风险。
- 运行受影响档位的原生完整流程和独立 Harbor 回放。既有 grade 1 只对原身份成立，不自动授予修改后的 oracle。

本轮验证仅包括源码解析、入口矩阵与证据交叉核对、报告链接/源码身份检查；完整物理运行数为 0。
