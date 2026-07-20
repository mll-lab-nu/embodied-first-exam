# TopoGym 物理真实性准则与 Metrics（v0 草案）

> 日期：2026-07-11
> 性质：**准则/度量定义文档，不含代码改动**（用户要求先立规再动手）。
> 对应：reviewer plan §2.5 第 4 条"物理真实性"；redesign plan §5 的稳定性硬门槛。
> 用法：新 demo/新任务落地前对照 §1 准则自查；录制/评测 run 用 §2 metrics 出量化结论。

---

## 1. 准则（qualitative principles）

**P1 无隐形传送**。物体位姿只能由两种途径改变：物理演化，或**声明过的 kinematic 状态机事件**（assisted grasp 附着、connector 落座 snap 等）。声明的传送必须：(a) 在 IL contract 打印中可见（`print_collision_il_contract` 先例）；(b) 单次幅度有上限（≤ 对应 latch 的 capture tolerance）；(c) 语义上是拓扑事件（落座/抓取交接），不是纠错手段。

**P2 无可见穿模**。在评测相机分辨率（512px）下，刚-刚、刚-柔、指-物不得出现肉眼可辨的互穿。已知豁免需记档（当前豁免清单：untangle 绳管与连接器顶帽的交界豁口——待应力消除锥；机器人已退出 PBD 耦合的任务中指-绳理论穿模——untangle connector 模式，见 flyout debug-log）。

**P3 PBD 稳定不变量**。任何 run 全程：出域粒子数恒为 0；无"直梁"蒙皮伪影。这是 redesign plan §5 的硬门槛（放弃逐帧复现换来的对价）。

**P4 接触驱动优先**。摩擦抓取任务（swap 等）中物体运动必须来自接触力，禁止用 set_pos 修正结果；assisted 模式（untangle connector、cable_routing latch）必须显式打印 runtime_attachment / runtime_set_pose 契约。

**P5 拖拽限速**。EE 每物理步位移 < 1 个粒子间距（当前 untangle：move_steps=300 → ~0.33mm/步 vs 粒子间距 4mm，余量 >10×）。新 primitive/新任务沿用该预算。

**P6 观测前 settle**。截图/拓扑判定前物体应基本静止（settle-and-freeze，redesign §3）；spawn 布局应接近 rest 状态（绳按 rest 形状生成 mesh——已满足）。

**P7 参数物理合理**。摩擦 ∈ [0.01, 5.0]（`validate_rigid_friction` 已强制）；密度用真实材料量级（绳 ~650、塑料件 ~700 kg/m³ 等）；夹爪 qpos 目标与被抓几何半径匹配（留 1~3mm 压量，不怼到 0）。

---

## 2. Metrics（quantitative，按"已可测/待实现"标注）

| # | Metric | 定义 | 建议阈值 | 数据来源 | 状态 |
|---|---|---|---|---|---|
| M1 | parked_particles | 到 PBD 域角点 (100,100,100) 距离 <1 的粒子数 | == 0 全程 | untangle demo `--probe`（PROBE 行 parked 字段） | ✅ untangle 已可测；其他 PBD 任务待移植 probe |
| M2 | max_step_particle_jump | 单步最大粒子位移 | < 0.02 m（cable_routing FLYOUT_JUMP 同款阈值；正常量级 ~3mm） | `--probe` jump 字段 / CableRoutingProbe rope_jump | ✅ untangle+cable_routing |
| M3 | handle_follow_error | 被抓物与 EE 期望位姿偏差 | ≤ max_handle_error（0.035） | PBDHandleDragPrimitive 分段日志 | ✅ |
| M4 | placement_error_xy | 放置后与目标的 xy 误差 | ≤ placement_tolerance_xy（0.030） | demo `physical_move` 行 | ✅ |
| M5 | seat_snap_distance | 落座 snap 传送幅度（P1c 量化） | xy ≤ capture_tolerance_xy（0.010）、z ≤ 0.020 | `connector_seat` 行 xy_error/z_error | ✅ |
| M6 | lift_delta_actual | lift test 实际抬升 | ≥ min_lift_delta | primitive 日志 | ✅ |
| M7 | grasp_success_rate | 抓取成功率 | assisted 模式恒 1.0（设计保证）；摩擦模式按任务定基线 | physical_move success 汇总 | ✅ 单集；跨集汇总待脚本 |
| M8 | rope_stretch_ratio | 绳当前弧长 / rest 弧长 | ≤ 1.05（stretch 接近不可伸长） | 待实现：probe 加一行（粒子链长/初始链长） | ⬜ |
| M9 | settle_residual_speed | 观测时刻最大粒子速度 | < 0.005 m/s（P6 量化） | 待实现：settle 循环出口条件 | ⬜ |
| M10 | penetration_depth | 绳最低粒子相对支撑面 | ≥ −1mm（cable_routing rope_minz_above_surf 先例） | CableRoutingProbe 已有；untangle probe 可加 | 🔶 |
| M11 | finger_rope_min_dist | 指垫与非目标柔体最小距离 | 摩擦任务无约束；assisted 任务 > 0（不接触） | untangle `--probe` finger_dist 字段 | ✅ untangle |
| M12 | teleport_budget_violations | 非声明位姿跳变次数（P1 量化） | == 0 | 待实现：对所有刚体做逐步位姿跳变检查（阈值 ~5mm/步 且无接触/无附着） | ⬜ |

**验收口径建议**：一条 run "物理真实性通过" = M1..M6 全绿 + 无 P2 未记档穿模。M8/M9/M12 实装后并入。

---

## 3. 与现有工具的映射 / 落地顺序建议（待批准后另立项）

1. 把 untangle 的 `UntangleProbe` 泛化成通用 `PBDRealismProbe`（M1/M2/M8/M10 全 PBD 任务可用）——中等工作量；
2. M9 settle 出口条件（settle 循环从固定步数改为速度阈值+上限步数）——小；
3. M12 逐步位姿跳变审计——小；
4. 每集 run 末尾打一行 `realism_summary M1=.. M2=.. ...` 供批量汇总——小。

> 注：§2.1（swap 抓取 grasp_qpos 贴合 block 半宽）是 P7 的第一个待办实例，尚未落地。
