# Untangle 重构计划：插头式连接器 + 双态 weld 锚定 + 绳身三层平滑

> 日期：2026-07-10
> 来源：collaborator 给的完整迭代方案（回应 reviewer 对 untangle 端点/绳身的反馈）。
> 关系：本文**取代** `reviewer_feedback_action_plan_zh.md` 里 untangle 的 2.2~2.4——那几条（加长 handle + 颜色匹配 + `anchor_radius` 固定 ~2 圈粒子）降级为**已落地的过渡改动（down-payment）**，是本方案的雏形，可平滑升级进来。
> 设计原则：贴 benchmark "**隔离拓扑、剔除低层控制混杂 / 拓扑事件原子性**" 的定位。

---

## 一、连接器建模（取代现在的 peg / 竖直圆柱 handle）

现在 handle 是一根悬在孔里的竖直圆柱，看着像凭空插进去、且太小难抓。改成**工业插头式连接器**：

- **尺寸对齐 Franka 夹爪**：抓取柱**直径 ~15mm**、露出板面**总高 ~40mm（柱体 35 + 法兰 5）**。Panda 夹爪最大开度 80mm、指垫长 ~20mm，闭合时手指距板面仍 >2cm、不蹭板。相比现状（露出 15mm、直径 10mm），**可抓体积 ~4×**，俯视图可见面积也够 VLM 分辨。柱体加 **2~3 道浅环槽 grip ring**，视觉说明"这是被抓的地方"。
- **法兰（解决"不自然"的核心）**：法兰**直径 > 孔径、平坐板面** → 一眼读出"插头插到底了"，补上现在缺的"它为什么停在这个高度"的视觉解释。空孔处加一圈**孔口垫圈 grommet** 网格 → 空孔 vs 占用孔在渲染里更易区分（利于 VLM 判合法目标孔）。
- **插销 = mesh-only、不注册 collision**：插销纯视觉"插进孔里"，**物理锚定完全由代码约束完成（见第二节）**，彻底绕开 peg-in-hole 的接触仿真。
- **绳-连接器刚柔耦合：钉 2~3 个粒子（沿引出轴），而不是 1 个**：把绳末端最后 2~3 个 PBD 粒子焊到连接器局部坐标系里**沿引出轴线排列**的固定点 → 不仅固定端点位置，还**固定出线切向**，绳沿"应力消除锥"轴线自然引出，而不是从一个点上以任意角度长出来（当前不自然的另一主因）。应力消除锥再盖住刚柔接缝。
  - 👉 我们 Phase 2 已把 `rope.anchor_radius` 0.008→0.012（固定 ~2 圈粒子）——就是这条的雏形，升级时改成"沿引出轴排列的固定点"。
- **评估过的备选**：蘑菇头旋钮（球头，抓取容差最好，但"球插孔里"无工业语义）；T 形拉手（抓取语义强，但俯视里横杆朝向引入**无关朝向信息、可能干扰 VLM 读 crossing**）。→ **插头方案在抓取可行性/视觉自然度/工业映射三项都不劣，直接选它。**

---

## 二、孔洞锚定：双态 weld 交换，无自由态

assisted grasp + 代码 attachment，把连接器生命周期做成**只有两态的状态机**，物理上从不发生真实插拔接触：

- **状态 = { SOCKETED, GRASPED }，没有 FREE 态**。
- **Grasp（assisted）**：夹爪 TCP 进入抓取柱轴线附近的**捕获域**（如 XY 偏差 <1.5cm、Z 在柱体高度范围）且发出闭合指令时 → 代码里**删 socket 约束、建 gripper↔connector 固定约束**，手指做到贴合位置的闭合动画。**不做摩擦抓取——抓取成功率恒 100%**，把低层控制误差彻底排除出评测变量（对齐"隔离拓扑、剔除控制混杂"）。
- **Snap 落座**：机械臂带连接器移到目标孔上方，当连接器底面进入空孔**捕获半径（XY <1cm）**并降到高度阈值 → **释放夹爪约束**，用 ~0.2s 位姿插值把连接器"吸"到落座位姿（法兰贴板、销入孔），再**建 socket weld**。**落座瞬间 = 该动作的拓扑事件时刻。**
- **非法动作 & 原子性**：目标孔被占用、或落点不在任何孔捕获半径 → **拒绝落座**，连接器随夹爪返回原孔重新 socket。状态机无 FREE 态 → 连接器**永不躺板/掉落**；每个 action **要么完整完成一次端点迁移、要么状态完全不变** → 精确对齐原版 Untangle "非法动作消耗步数但不改状态" + 拓扑事件原子性优先。
- **Genesis 最省事实现**：连接器整个做成 **kinematic 刚体**——socketed 时位姿钉死孔位，grasped 时逐帧跟随 TCP 加固定偏移，绳末粒子每 substep 钉到连接器坐标系。连接器对物理求解器只是**移动边界条件**，PBD 绳身照常自然演化，**不需要真的用约束求解器解 weld**。

---

## 三、绳身 kink/zigzag：初始化 / 求解 / 渲染 三层各下一刀

锯齿通常非单一原因，三层同时处理：

**初始化层（消除"天生的"锯齿）**
- 静息形状**不要**用直线段或随机撒点；改成**过两个端点孔位拟合一条 Catmull-Rom 样条**，加 **5~15% 松弛**（弧长 = 1.05~1.15 × 弦长），沿样条**等弧长采样粒子**。
- scramble 生成初始局面同理：每次端点重定位后**按新孔位重新铺样条**，而不是 teleport 端点后让绳被硬拽成锯齿。→ 天然对齐原版 "deterministic re-threading" 语义，且保住可复现性。

**求解层（消除动态抖动）**
- **粒子间距 ~1~1.5× 绳半径**（0.8cm 直径、35cm 绳 → ~45~60 粒子）；间距过大是折线感头号来源。（现状 `particle_size=0.004`=radius，偏大。）
- 启用/调高 **bending constraint**（锯齿的物理本质=弯曲约束太弱压不平局部高曲率）。
- **substeps 8~10、XPBD 迭代 15~30**，让约束真正收敛。⚠️ **约束**：tabletop V1 locked preset 把 `sim.substeps` 锁死 4（`StandardTabletopSceneBuilder._validate_locked_preset`）；要提 substeps 得给 untangle **开 preset 例外**，否则先靠加迭代。
- 每步 **速度阻尼 0.98~0.995** 杀振荡；自碰撞保证**粒子间距 < 2× 碰撞半径**避免穿透后 popping。
- **settle-and-freeze 协议**：每个动作执行完跑 N 步松弛，直到**最大粒子速度低于阈值**才截图作观测 → VLM 永远看到静态无残余抖动画面，对确定性也是加分。

**渲染层（最便宜、收益最大）**
- **不**逐粒子渲染 capsule 链；先对粒子位置**拟合 Catmull-Rom 样条，再沿样条 sweep 出圆管 mesh** → 中等粒子数下视觉就完全平滑，物理层甚至不用调到极致。
- **硬性守则：crossing 判定和渲染必须用同一条平滑曲线**。若 oracle 在原始粒子折线上数交叉、渲染却用平滑样条，样条过冲会制造"像素里可见但标签里不存在"的交叉（或反之），GT 和图像脱节。→ 判定用的**俯视投影 polyline 直接从渲染样条采样**。

---

## 四、实施顺序 & 验收标准

**顺序**
1. 连接器建模 + 绳端焊接（~1~2 天）
2. 双态锚定状态机（~1~2 天；此时抓取成功率应恒为 100%）
3. 绳身三层平滑（~2~3 天）
4. 回归验证

**验收（4 条）**
1. 全部 regression 实例上，**平滑曲线投影算出的 crossing 数 = oracle 逻辑 crossing 数**（完全一致）。
2. 每个动作后的 settle 截图**无可见锯齿**（自动：相邻段夹角最大值 < 阈值；再抽样人工看）。
3. **同 seed 下端点轨迹 + 最终拓扑确定**；中段物理**不要求逐帧一致**，但**全程稳定、无爆解/崩溃/粒子飞出**（这是选 A 后的硬门槛）。
4. 评测分辨率下**空孔 / 占用孔 / 各色连接器三者可清晰区分**。

---

## 五、设计决策（已定 2026-07-10）：选 A —— 物理拖拽 + settle

**决策**：走 **A. 物理拖拽 + settle**（更 embodied、是 manipulation 版对 paper 的差异化卖点）；**B. 落座后重铺样条**留作 fallback 开关。

**复现范围放宽（关键）**：只要求**复现绳头(端点)的运动轨迹 + 最终拓扑**，**不要求中段物理逐帧 100% 一致**。即同 seed 下端点走一样的路、最后落一样的孔、拓扑结构一致即可；中段绳子形状允许物理上的细微差异（不同 run 之间不必逐粒子相同）。

**换来的硬性要求 = 稳定性**：既然放弃逐帧一致，绳子就**必须稳定——绝不能出 PBD 爆解 / solver 崩溃 / 粒子飞出**这类 bug。这把第三节"求解层"从"美观诉求"提升为**硬门槛**（直接套用 cable_routing 那轮的教训：细网格 + 硬约束 + 少迭代 + 快拖 = 爆解；对策=够多迭代/substep、particle_size<radius、限拖速、settle）。

**对 oracle / label 的影响**：crossing 数**从实际 settle 后的绳子(渲染样条)读取**，不是预先规定；oracle / topology 逻辑读**同一状态** → 第三节渲染层"**判定与渲染同源**"这条因此更关键。`untangle_planner` 本就"动态按当前拓扑选下一步"，天然契合物理拖拽后重读拓扑。

---

## 六、和当前代码/架构的对接（落点）

现状：
- `topogym/tasks/entangle/untangle.py`——scene（board / holes / pegs / anchor_pins / endpoint pins / rope 建 mesh + `fix_particles_to_link`）。
- `topogym/planning/untangle_planner.py`——动态：每次按当前拓扑选下一次 endpoint relocation（`plan_next_untangle_move`）。
- `demos/entangle/untangle_physical_handle_demo.py`——现用 `PBDHandleDragPrimitive` 做物理抓取 + 拖拽。
- `topogym/envs/untangle_mdp.py`——RL 壳。

本方案落点：
| 模块 | 改动 |
| --- | --- |
| 连接器建模 | `tasks/entangle/untangle.py` 的 endpoint handle 构建：插销(mesh-only,无 collision) + 法兰 + grip ring + grommet；绳端焊 2~3 粒子沿引出轴（**已起步：anchor_radius→0.012**）。可能需要生成 connector mesh OBJ（Genesis 无 Capsule morph，只有 Cylinder/Box/Sphere，复杂形状走 `gs.morphs.Mesh`，和绳管 OBJ 一个套路）。 |
| 双态 weld 状态机 | 新的 connector 生命周期逻辑（kinematic 刚体 + 每 substep 钉粒子 + 捕获域/落座判定），**替代/包装**现有 `PBDHandleDragPrimitive` 物理抓拖；与 `untangle_planner` 的 endpoint move 对接（落座=拓扑事件时刻）。 |
| 绳身三层 | init 样条铺粒子（scene/generation 层）；求解参数（`untangle_topogym_tabletop_v1.yaml`：particle_size/bending/iters/damping/self-collision，substeps 需 preset 例外）；**渲染样条 + crossing 判定同源**（渲染/评测层）。 |

**已落地的过渡改动（Phase 2，可平滑升级进本方案）**：handle 加长 0.024→0.032、颜色匹配绳色（深一档 ferrule）、`anchor_radius` 0.008→0.012（固定 ~2 圈粒子）。这些是"更大可抓体积 / 钉 2~3 粒子"的雏形，重构时并入，不冲突。

---

## 七、下一步

1. 先把**待定决策（第五节：物理拖拽 vs 重铺样条）**和 Qineng 对齐——它决定后面求解层和 oracle 的实现方向。
2. 按第四节顺序推进；每步遵循"一次一个量、GPU viewer / settle 截图验证"。
3. 眼下已落地的 Phase 2 过渡改动可先录一版对比，作为重构前的 baseline。

---

## 八、落地记录（2026-07-11：Phase B 已通）

第一、二节（连接器 + 双态锚定）已在 `untangle_physical_handle_demo.py` 落地并在 GPU 上端到端验证（seed 0：抓取→搬运→落座 `engaged=True xy_error≈1mm`→`task_success=True`）。实现要点与教训：

- **双态状态机**：复用 `ConnectorLatch`（SOCKETED，逐步强制位姿）+ `RigidAttachment`（GRASPED，跟随 TCP）；primitive 新增 `on_close` 回调做"latch→attachment"同步原子交接，`before_release` 里落座重焊；失败路径原子退回原孔。无 FREE 态。
- **绳顶部出线**：几何注入在 `UntangleLayout.rope_mesh`（mesh 层），**不改 config `strands.points`**——`_over_orders_from_config` 用全 strand 的 max z_offset 定 over/under，config 层抬端点会翻转交叉 GT。
- **踩过的 4 个坑**（详细机理见 memory `untangle-connector-phase-b`）：
  1. 出线路径的尖角发卡弯 → 扫掠管自交 → tetgen 崩溃；顶部 U 弯必须圆弧化（R≥2.5×绳半径）。
  2. 管 mesh 生成器原来用固定世界 ẑ 作 binormal，垂直段截面被压扁自交；已换**平行传输帧**（平躺绳退化为旧帧，无视觉差异）。
  3. 球形固定带切在竖直段中间 → 带边界单粒子被固定/自由邻居撕扯 → 弹射到 PBD 求解域角点 (100,100,100)；已改**沿轴圆柱锚定**整段插头内绳（`_connector_anchor_indices`）。
  4. 绳↔指垫 PBD 接触在撤退时钩住顶部出线的垂坠段 → 中段拉爆。曾用"机器人退出 PBD 耦合"（`robot_material=Rigid(needs_coup=False)`）修复；**2026-07-11 按用户要求改为实验**：恢复绳↔机器人接触，改用「压低端头（column 0.035→0.020，出线弧顶 68→~48mm）+ 高抬升搬运（lift_delta 0.028→0.100，先垂直上提再平移，垂坠段从俯视交叉的绳上方跨越）」来规避钩挂与贴地穿模，待用户 GPU viewer 观察确认。若复现撕裂，fallback = 在 `UntangleSceneBuilder.build` 里重新传 `robot_material=Rigid(needs_coup=False)`（builder 参数已保留）。
- **遗留（视觉/评测）**：绳管与顶帽交界有轻微穿插豁口（等应力消除锥盖住）；余量绳可能物理搭在他绳上而逻辑拓扑无交叉（第三节"判定与渲染同源"仍未做）；评测距离下空孔对比度过低（做 grommet 时一并提高）。
