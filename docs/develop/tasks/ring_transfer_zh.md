# ring_transfer —— docx 2.6「绳圈从柱 A 转移到柱 B」设计契约与落地记录

日期：2026-08-24。类别 `routing`。代码：`topogym/tasks/routing/ring_transfer.py`（场景）、
`_ring_transfer_geometry.py`（布局预算）、`topogym/planning/ring_transfer_planner.py`（oracle）、
`topogym/verification/ring_transfer_verifier.py`（判定）、`demos/routing/ring_transfer_physical_demo.py`
（demo）、`tests/check_ring_transfer_geometry.py`（离线门）、`tests/ring_transfer_spike.py`（无臂 spike）。
配置：`configs/task_configs/ring_transfer_topogym_tabletop_v1.yaml`。

## 1. 任务定义

闭合弹性环平铺在桌面、套在柱 A 上；终态环套在柱 B 上、不再围住 A。判定量是环中心线绕每根柱轴的
**绕数**（俯视投影，闭合曲线的转角和 / 2π，整数），enclosure 是绕数为 1 的柱子集：{A} → {B}。
路径证据单独记录：每根柱的挡头顶是否被越过（`top_crossed`）、环到柱面的最小间隙（穿模监视）。

判定器输出每柱绕数向量，oracle 吃 `layout.crossings()` 给出的跨越序列。2026-08-24 的数据结构预留过多柱出生形
（`posts` 列表、`ring.enclosure` / `goal.enclosure` 子集）；09-04 做变体部署时改成了 `posts: {A, B}` + `ring.on_post` /
`goal.on_post` 标量（抽样叶子必须是标量），多柱预留放弃。现在的变体轴与数值见 §7。

## 2. 场景（第二版，2026-08-25）

- 两根工业走线柱（柱身 r=0.016 高 0.100、底座锥 r=0.030、**碰撞挡头** r=0.026 厚 0.008；深灰柱身、
  黑色底座与挡头），A 在 (−0.100, 0)，B 在 (+0.120, 0)。第一版（r 0.012、高 0.085、柱距 0.14、
  周长 0.53）是 transfer 路线的几何，用户看 demo 后要求环更小、柱距更远、柱子更拟真。
- 闭合环：`world/closed_band.py` 周期管，周长 0.40、半宽 0.045、管半径 0.004，出生为围住 A 的跑道形、
  长轴指向 −x。FEM+IPC，`rest_shape=spawn`（闭合环上 straight 不可用）。
- 默认 oracle 是 `carry`（§3b）；`transfer`（§3）在这组几何下拉伸比 1.96，不可用，离线门只报告。
- 挡头是碰撞体，与 cable_routing 的装饰顶盖不同：无挡头时远端帽抬高后拉线与桌面成约 40°，A 处缠绕在
  tan(角) > μ=0.3 时沿柱身上滑并越过柱顶（实测平移段第 60 步脱离）。gateway 因此是挡头顶。

## 3. 单夹爪为什么必须分两段、以及为什么要钩

1. **单点捏住的环套不进任何柱子。** 环被拉紧后在 A 处收拢成 2(r_post + r_tube)=0.032 宽的双股，
   闭合曲线只在 A 处有绕数；离线门第一版量得绳股离 B 轴 12.5 mm < 16 mm。
2. **悬空的环也套不进柱子。** 单手提起的环竖直悬挂，俯视投影是一条 70 mm 线段、面积为零，而围住 B
   要求投影包住 B。实测：环脱离 A 后搬到 B 上方放下，B 绕数 0。
3. 因此 on-phase 用**两指伸进远端帽张开 0.070 钩住**（两条 follow band），A 柱当第二只手把环撑成
   梯形（A 处 0.032 → 远端 0.070），B 处绳股间距 0.062 ≥ 0.044。路径：绕 A 平转（z=0.03，经 +y 到
   55°）→ 抬到 0.155 → 平移到 B 远侧 x=0.116 上方 → 下放 → 释放。平移段全程绷紧（拉伸比 1.05~1.15）。
4. off-phase 捏住贴着 A 的帽，抬到挡头顶 +0.024，向 B 平移 0.060 滑过挡头，释放。

离线门检查的全部不等式与路径采样见 `tests/check_ring_transfer_geometry.py` 文档字符串。

## 3b. 主 oracle：捏取 + 搬运套索（`carry`，2026-08-25，用户提议）

「悬空的环套不进柱子」只对**从上方放下**成立。从**侧面**推则不同：把悬挂环的底部 U 推向柱身，
两股绳被柱子分到两侧，手再越过柱子，环就套住了柱子（套马索），放低松手即可。

抓取是**捏取**（用户定的流程）：张开的两指移到近帽顶点上方 → 转到合拢方向 ⟂ 绳切向 → 下到
指尖 = 绳心 + 2 mm → 合拢到 `grasp_qpos`=绳半径 → `attach_error` 校验 → 此时才 engage assist →
抬升搬运。夹持证据是 `finger_qpos` 停在 0.004。

捏住的环为什么还能张开：夹钳把约 20 mm 绳段夹直（follow band 的偏移刚性保持），绳水平离开夹钳
后才在重力下弯垂，弯垂特征长度 (EI/w)^{1/3} = (2e-5/0.32)^{1/3} ≈ 0.04 m，所以悬挂环顶部被撑开
约 0.08，底部 U 同宽，大于柱身进入所需的 2(r_post + 2 r_tube + d_hat) = 0.052。这是推导，spike
`carry` 档的 `u_width` 读数实测；不够则回退到内撑抓取（两指伸进环内张开，transfer on-phase 的
hook 机制，2026-08-25 曾以 70 mm 张开实测套索成功）。

路径：抬到指尖 0.282（悬挂深度保守估计 (0.36−0.04)/2 = 0.16，底部高出 A 挡头 10 mm；spike 实测后
`carry.hang_depth` 写实测值）→ 平移到 B 近侧上方 → 降到 U 底 0.050 → 沿 A→B 推过 B 轴 0.06 →
放低到 0.020 → 张开松手。不借 A 撑开、不拉伸、柱距无关。

## 3c. 机械臂不得穿模（2026-08-25，用户原则）

第一版捏取点在近帽顶点（离 A 轴 50 mm）：捏帽顶时合拢方向指向柱心，Franka 手掌沿合拢方向
±100 mm、底面只比指尖高 77 mm（低于挡头顶），手掌必然罩到 A 上——demo 实测穿模。改法：
- 环出生方向改为从 A 向 −y 伸出，整环、捏取点、悬挂中的环都不在两柱连线之间；周长 0.46 使直段
  长 0.073；
- 捏取点在远离 B 的那条直段上、离 A 轴 0.070（09-04 起由 Layout 推导，见 §7.1；原为 `carry.pinch_along/pinch_side`）：绳沿 y、手指沿 x
  合拢，手掌沿 x 展开但 y 向偏移 70 mm，离 A 挡头边 12 mm；
- 离线门新增 `hand_clearance`：手掌盒体（半长 0.100、半厚 0.030、底面高指尖 0.077，
  `task.physical`）在抓取位与放下位对每根挡头的间隙必须 > 0；放下位指尖抬到 0.040、推过 B 轴
  0.080 后手掌底面 0.117 高于挡头顶 0.093；
- 柱高 0.100 → 0.085，抬离指尖 0.295、手 0.398 留在工作区内。

## 3c'. 抬离 A 只能从正上方（2026-08-25，inspect_lift 实测）

从捏取点（A 的 −x 直段）竖直抬起：环被勒在 A 柱身上（A_gap 27→2 mm），A 远侧的绳段沿柱身爬到
挡头下沿（near_A_max_z 106 mm，挡头 100–108）并卡住，环被拉长 56%，臂被拖偏 142 mm，手指在
IPC 里把拉力传回臂——就是「起伏、绕圈」的来源。环与 A 是链环，从侧面拉只会勒紧并卡进挡头。
改为：`lift_low`（抬 4 cm，环其余部分留在桌上）→ `over_anchor`（水平移到 A 轴上方、朝远离捏取
点那侧多走 2 cm）→ `clear`（竖直抬到底部 U 高出挡头）：两股从上方经过挡头边缘下垂，底部 U
（106–130 mm）从直径 52 mm 的挡头上方越过。`grasp_qpos` 0.004 → 0.006（绳半径 + d_hat）：0.004
时手指越过绳心（finger_qpos −0.002），势垒没起作用。

## 3d. 夹爪与绳的真实接触（2026-08-25，用户要求）

`physical.robot_rope_contact=fingers`：`hand`、`left_finger`、`right_finger` 三个 link 以
`two_way_soft_constraint` 进 IPC（与 cable_routing 同机制），指垫真的夹住绳、手掌穿不过绳；
`robot_rope_friction` 0.6（接触摩擦 ≈ 0.42）——捏取要握得住，与 rope_winding 让绳蹭过指垫的 0.004
相反。assist 仍保留（同一运动，不冲突），接触负责不穿模与视觉。指尖放在绳心下方 2 mm 让指垫盖住
绳截面；合拢 80 步（30 步只走到 0.036）。带臂实测悬挂深度 140–155 mm、U 宽 106–130 mm；
`carry.hang_depth` 取 0.140，推的高度按它算（0.19 的外推值让 U 底从 B 挡头上划过、没套上）。

2026-08-25 第二次（inspect_clear2）：carry 段去掉 assist、`finger_links` 只留两指后，**整段没抓到绳**——
descend 结束指尖离桌 19 mm（绳顶 10 mm），指垫在绳上方合拢，finger_qpos 正好停在指令值 0.006；
`set_gripper` 80 步走完手指仍在 0.036；环全程 loop_min_z 2 mm，band_err 与手抬高量 1:1 增长；
反应式抬离读拉伸比恒 1.000，空手升了 400 步到 1.32 m。位置门 attach_error 4.6 mm 照样放行。由此补三项：
（1）hover / descend 之后按实测残差修正指令直到 < `grasp.settle_tol`（IK 停早的对策）；
（2）合拢逐步走到手指静止并逐 10 步打印；合拢后先抬 `grasp.lift_check`，near band 必须跟着升
≥ `lift_check_min_rise`，否则报「rope not held」退出——这才是捏住的证据，取代位置门；
（3）反应式抬离加中止条件：滑移 > `slip_abort`、arm_err > `arm_err_abort`、指尖高于 `max_z` 任一即 ABORT。

2026-08-25 第三次（inspect_clear3）：descend 在指尖 9.4 mm 处到底——指垫已贴桌（指垫底面比指尖点低
约 7 mm）；合拢每 10 步只走 0.4 mm（指垫拖着桌面滑）；lift_check 期间手指走到 −0.0023，腕部机位里
指垫合拢后绳从中间穿过。机制：`two_way_soft_constraint` 是给手指在 IPC 里做副本、用刚度 100 的弹簧
互拉，碰绳的是副本，渲染与 finger_qpos 是刚体手指，刚体手指的 PD 力可以越过副本——有/无 assist 两次
都是 −0.002。**2026-08-26 定 B 路线**（用户）：臂回到 IPC 之外，合拢停在 `grasp_qpos`（指垫离绳面
1 mm，视觉上夹住），合拢后焊 assist，`lift_check` 仍验证绳跟手走；`pinch_lift` +0.006（指垫底离桌 4 mm）。

2026-08-26 inspect_clear5：B 路线全程成功（读数见 §5）。附带修正：`lift verdict` 不再把绕数当判据——环悬在 A
正上方时俯视投影仍套着 A 轴，读 1（travel 25 步后才变 0），只看「A 接触 0 且环最低点高于挡头顶」；
`run.stop_after=clear` 在反应式分支里补上。合拢无阻力也要 300+ 步才到 0.006（指关节 PD 响应），`close_max_steps` 400。

## 4. 与 2.7 的关系

on-phase 结束时环同时围住 A、B（2.7 的终态）。但 2.7 要求终态绷紧（错误动作释放后回弹）需要周长
< 围两柱的最短周长 0.381，而钩开梯形在该周长下要求 >45% 拉伸；两者冲突，2.7 需另行设计
（更细的 B 柱或两点钩持），本任务终态是松的。

## 5. spike 读数（2026-08-24，GPU，无臂）

| 档 | 读数 |
|---|---|
| settle | 50 步收敛，winding {A:1,B:0}，A 间隙 33.8 mm，无穿模 |
| stretch | 钩带跟踪误差 ≤0.25 mm；平移段 A 顶未越过、B 顶越过；释放后 {A:1,B:1}，弧长比 1.013 |
| transfer | near band 距设计点 26.7 mm（demo 按实测位置抓）；释放后 {A:0,B:1}，全程最小间隙 2.0 mm（=势垒） |
| carry 捏取（2026-08-25，周长 0.36、柱距 0.22） | 单带捏住近帽顶点：悬挂深度 lift 130.6 / travel 116.5 / approach 135.9 mm，底部 U 宽 67 / 91 / 78 mm ≥ 52（夹钳撑开的推导成立）；push 第 50 步 B 绕数 0→1；释放后 {A:0,B:1}，环离 A 137 mm，最小间隙 2.0 mm |
| **carry 带臂全程（2026-08-26，inspect_clear5，B 路线）** | descend 残差 1.9 mm（指尖 12.4 mm）；合拢到 0.006；lift_check band 升 11.1 mm；lift_low band_err ≤ 2.0 mm；反应式抬离 80 步（z 65 / xy 14）：绳先沿 A 柱身爬到 146 mm、拉伸比超 1.02 后手朝 A 轴心走、环底 123 mm 越过挡头，拉伸峰值 1.011；travel/approach 悬挂 179/156 mm、U 宽 81/102 mm；push 第 50 步 B 绕数 0→1；终态 {A:0,B:1}，A/B 顶越过均 True，最小间隙 2.0 mm，**success=True**，2016 步 |
| carry 钩持（2026-08-25，旧几何） | 抬到指尖 0.295 时环离开 A（第 145 步 A 顶越过）；推过 B 第 50 步 B 绕数 0→1（两股分到两侧）；放低释放后 {A:0,B:1}，环远端搭在 A 柱面（松环，绕数 0） |

## 6. 待办

- demo 三视角录制；`drape_outside` 依赖不可用的 transfer 几何，不再作对照（`lift_only` 09-05 重做，§7.4）。
- 判据不检查松手后环相对挡头的高度：环平躺在目标柱挡头顶面上会被判成功，需要一个对照或一条高度条件（§7.4）。
- off-phase 夹爪与 A 柱的干涉：指垫沿 y 张开、手心离柱面 4 mm，若 rigid 求解器里手指碰柱需把
  抓取点沿环外移。
- `build_ring_transfer_episode_spec` 与 split（目标 3 的通用骨架）；`stability_sweep.sh` 的 13 任务表（§6.3 第 2 级）。

## 7. 变体部署（2026-09-04 晚，`variation_axes_plain_zh.md` §6.2 第 10 步）

六项交付：yaml `variation:` 块、Layout 的 `checks()` 与派生、demo 接线 + variant 行 + run 配置键、
`check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测写回（本节）。参照 `physics/rope_winding/rope_unwinding_zh.md` §7
（同为 FEM 形变体、带 `*_frac` 派生）与 `bar_through_hole_zh.md` §3–§6（搬运高度改为 Layout 公式的先例）。

**物理图景。** 桌上两根一样的走线柱 A、B（柱身 + 喇叭底座 + 比柱身粗的挡头），闭合弹性环平铺套在出生柱上、长轴背离
另一根柱。夹爪捏住环远离目标柱的那条直段，从出生柱**正上方**竖直提起（环挂在指尖下呈 U 形），搬到目标柱近侧，沿
出生柱→目标柱方向推过它（U 底撞上柱身、两股分到柱子两侧），放低松手。终态：环只套在目标柱上，绕数 (A:1, B:0) → (A:0, B:1)。
这条路线叫 `carry`（§3b），是唯一可用的 oracle；`transfer`（借出生柱撑开梯形）在柱距 0.22 下不可用，离线门只报告。

**高度链**（z 向，桌面 = 0；本节的三个高度 2026-09-04 起由 Layout 推导，常量在 `_ring_transfer_geometry.py` 顶部）：
挡头顶 `top_z = height + head_height`（基准 0.100 + 0.008 = 0.108）→ `lift_low_z = top_z + 0.012`（先抬一点，环其余部分留在桌上；
必须 < 悬挂深度 `hang_depth` 0.140，否则抬离时已产生张力）→ `clear` 指尖 = `top_z + r_tube + clear_margin + hang_depth`
（0.108 + 0.004 + 0.008 + 0.140 = 0.260，原本就按柱顶推导）→ `hang_bottom_z = base_height + 0.024`（推向目标柱时 U 底离桌
0.040，在底座锥顶 0.016 与挡头下沿 `height` 之间）→ `drop_z = max(hang_bottom_z, top_z + 0.009 − palm_bottom_above_tip 0.077)`
（放低到的指尖高度，基准 0.040；手掌盒体在放下位罩在目标柱上方，掌底必须高于挡头顶）。

**术语。** 变体轴 / `variation:` 块：yaml 末尾的抽样指令表，`kind` 只有 `choice` / `uniform` / `derived` / `validate`
（`topogym/generation/layout_randomization.py`）；列表元素不能作为 `path`，所以向量叶子都拆成标量键。`*_frac` 派生：叶子的可行区间
依赖其他轴时抽 [0,1] 再由 Layout 映射到实际值，不靠拒绝。首抽拒绝率：1000 个 seed 第一次抽样被 `validate` 拒绝的比例，门 2%
（`tests/check_variant_rng.py` 的 `MAX_REJECTION`）。角点门：连续轴取端点 × 离散轴取全部值的笛卡尔积，每个角点都要过 `checks()`
（`tests/check_variant_corners.py`，§4.3）。对照组：故意做错的 motion，证明判定器不会把错的判成对。

### 7.1 轴

yaml 结构先改了四处，抽样才有标量叶子可指：`posts:` 列表改成 `posts: {A: {x, y, 颜色}, B: …}` + 两柱共用尺寸块 `post_shape:`
（radius / height / head_overhang / head_height / base_radius / base_height）；新增 `pair:`（mid_x / mid_y / spacing / heading_deg +
两个 frac 与窗口 range），两柱位置由它派生（成对平移 / 旋转不加新 `pair` kind，走 bar_through_hole 的 `derived` 先例）；
`ring.enclosure: [A]` / `goal.enclosure: [B]` 改成标量 `ring.on_post` / `goal.on_post`（08-24 预留的多柱出生形放弃）；
`ring.long_axis`、`carry.pinch_along / pinch_side / lift_low_z / hang_bottom_z / drop_z` 六个叶子删除，改为 Layout 规则。

| 类 | 叶子 | 抽法 | 基准 | 说明 |
|---|---|---|---|---|
| A | `ring.on_post` | choice [A, B] | A | 防捷径指令轴；`goal.on_post` 派生为另一根，`goal.instruction` 派生带柱名 |
| B | `post_shape.height` | uniform [0.085, 0.115] | 0.100 | 单调裕度轴（难度候选）；上界由 lift_low_below_hang 定（0.123 + 0.012 < 0.140，余 5 mm） |
| B | `post_shape.radius` | uniform [0.013, 0.022] | 0.016 | 上界：U 底撑开量 2(r + 2 r_tube + d_hat) = 0.064 ≤ 实测 U 宽 0.130 |
| B | `post_shape.head_overhang` | uniform [0.008, 0.014] | 0.010 | 下界 = 管径 0.008；上界受捏取点与挡头净空限制（palm_clears_heads_at_grasp 收到 5.6 mm） |
| B | `pair.spacing` | uniform [0.18, 0.28] | 0.220 | 下界：悬挂股避开出生柱挡头、手掌与两挡头净空；上界：工作区与可达 |
| B | `pair.heading_deg` | uniform [−30, 30] | 0 | A→B 相对 +x 的角；长轴 = (sin θ, −cos θ) 随之转 |
| B→C | `pair.mid_x_frac`、`pair.mid_y_frac` | uniform [0, 1] | 字面 mid (0.010, 0) | 窗口 = `mid_*_range` ∩ 工作区（所有 carry 手位 + 出生环，余量 0.020）∩ 可达圆（手位到底座 ≤ 0.780，x 在 y 定下后按圆解） |
| C | `ring.long_axis`、`carry.pinch_side`、`carry.pinch_along`、三个搬运高度 | Layout 规则 | 还原 [0,−1] / −1 / 0.070 / 0.120 / 0.040 / 0.040 | pinch_side = 远离目标柱的直段；pinch_along = min(直段长 0.073, head_radius + hand_half_thickness + 0.014) |
| D | `ring.perimeter / loop_radius`、`carry.hang_depth / hang_half_width`、`grasp.*`、`rope.fem.*`、`physical.*` | 固定 | | perimeter 变了要重测 hang_depth；柱高不改变悬挂深度 |

字面拷贝三处：`rope.radius` 0.004、`rope.fem.contact_d_hat` 0.002（prefab）、`workspace.x/y/z`（common），builder 断言相等。
派生顺序：`goal.on_post` → `pair.mid_y`（窗口只看工作区）→ `pair.mid_x`（窗口含可达圆，按已定的 mid_y 解）→ `posts.A/B.x,y`。派生只写标量、无空格的叶子：指令文本是 `goal.instruction` 模板 + `Layout.instruction()`，不是派生叶子（09-05 角点首跑的教训，§7.4）。

### 7.2 `checks()` 十五行

纯函数 `_ring_transfer_geometry.ring_transfer_checks(layout)`，`RingTransferLayout.checks()` 调它；随机化的拒绝步、离线门、角点门、
demo 开局打印用同一张表。transfer 路线的行（拉伸梯形、远端帽路径）不在其中，留在离线门里只报告。

| 行 | 读数 | 门 | 基准 | 256 角点最紧 |
|---|---|---|---|---|
| loop_clears_post | loop_radius − (r + r_tube + d_hat) | ≥ 0 | +28.0 mm | +22.0（r 0.022） |
| spawn_clears_target | 出生环到目标柱轴最小 xy 距离 − head_radius − r_tube | ≥ 0.020 | +140 | +90 |
| head_overhang | head_radius − radius | ≥ 2 r_tube | +10.0 | +8.0（下界） |
| pinch_on_straight | 直段长 − pinch_along | ≥ 0 | +2.9 | 0（封顶时） |
| palm_clears_heads_at_grasp | 抓取位手掌盒体到两挡头最小间隙 | > 0 | +11.9 | +5.6（r 0.022、挡头 0.014） |
| palm_clears_heads_over_anchor | 越柱位同上 | > 0 | 掌底高于挡头 | 同 |
| palm_clears_heads_at_drop | 放下位同上 | > 0 | 掌底高于挡头 | 同（drop_z 派生保证） |
| fingertips_over_anchor_head | lift_low_z − 出生柱挡头顶 | > 0 | +12.0 | +12.0 |
| lift_low_below_hang | hang_depth − lift_low_z | > 0 | +20.0 | +5.0（柱高 0.115） |
| hang_bottom_on_shaft | min(hang_bottom_z − base_height, height − hang_bottom_z) | ≥ 0.015 | +24.0 | +24.0 |
| u_width_fits_target | 2 hang_half_width − 2(r + 2 r_tube + d_hat) | ≥ 0 | +78.0 | +66.0（r 0.022） |
| hanging_strands_clear_anchor_head | travel/approach/push/lower 处 ±hang_half_width 的股到出生柱挡头 | > 0 | +133.5 | +82.6 |
| carry_in_workspace | 所有 carry 手位（含 hand_above）到工作区边界最小裕度 | ≥ 0.020 | +37.0 | +22.0（柱高 0.115 的 clear 手位 0.378） |
| spawn_in_workspace | 出生环到工作区边界最小裕度 | ≥ 0.020 | +100 | +22.3（柱距 0.28、mid_y 上界） |
| hand_reach | 手位到 `reach.base_xy` 最大距离 | ≤ 0.780 | 0.770 | 0.780（窗口边界） |

`reach.max_hand_dist` 0.780 沿用 rope_unwinding 的假设，是 `mid_x` 窗口的主要边界（柱距 0.22 朝向 0° 时上限 0.019、柱距 0.28 时
−0.011；1000 seed 里最窄 11.1 mm）；基准布局推过 B 的手位 0.770 在 08-26 带臂跑通，所以这条假设至少有 10 mm 的实证余量。
角点子集（§7.4）先跑贴着这条边界的格。

### 7.3 离线实测（2026-09-04）

先在 scratch 里用现有几何模块对 256 个规划角点做了数值探针，确认区间与常量后才接 yaml（rope_unwinding 的做法）：256 个全可行、
窗口无空，与接好之后的门读数一致。

| 门 | 结果 |
|---|---|
| `check_ring_transfer_geometry.py` | PASS：十五行；基准 yaml 还原 A (−0.100, 0)、B (0.120, 0)、长轴 [0, −1]、捏取侧 −1、pinch_along 0.070、三高度 0.120 / 0.040 / 0.040；朝向 30° = 基准绕中点旋转（两柱、出生环、carry 路径逐点一致）；on_post=B 时跨越序列 [(A, on), (B, off)]、捏取侧 +1；256 角点 0 拒绝 0 失败；负例柱高 0.130 → lift_low_below_hang、柱半径 0.050 → loop_clears_post、柱距 0.28 + 字面 mid_x 0.040 → carry_in_workspace 均被拒 |
| `check_variant_rng.py` ring_transfer 段 | 1000 seed 首抽拒绝率 **0.000**；on_post A 476 / B 524；最大可达 0.780；最窄 mid_x 窗口 11.1 mm |
| `check_variant_corners.py --task ring_transfer` | **256/256**，Hydra compose（`run.randomize_layout=false` + `task.*` 覆盖）读数一致 |
| `check_configs_compose.py`、`check_demo_configs.py` | PASS |
| demo `run.build_only=true run.randomize_layout=true run.seed=3`（GPU 建场景） | variant 行：on_post A、柱高 0.099、半径 0.0145、挡头 0.0135、柱距 0.2165、朝向 +18.7°、mid (0.001, 0.003)、A (−0.102, −0.032)、B (0.104, 0.037)、pinch_along 0.072、lift_low 0.119；checks 行十五行全 ok |

### 7.4 GPU 实测（4090，与 rope_unwinding 链共用）

1. 固定布局 `carry` 复跑（几何模块读法改了，先确认没退化；上次成功 08-26 inspect_clear5）：`runs/ring_transfer_variation/20260904_baseline/fixed_carry_retry.log` **success=True**，1292 步；attach_error 3.3 mm、finger_qpos 0.0067；反应式抬离 85 步（xy 17 / z 67）后环底 124.4 mm 越过挡头顶 108，lift verdict CLEAN；travel / approach 悬挂 164 / 160 mm、U 宽 95 / 78 mm（≥ 52）；终态 {A:0, B:1}，两顶越过，最小间隙 2.0 mm，length_ratio 1.000。与 08-26 的读数同量级（当时悬挂 179 / 156、U 81 / 102）。第一次尝试（`fixed_carry.log`）在第一步物理就被 libuipc 以 `cudaErrorInvalidDevice`（cub radix sort）终止：当时 GPU 有三个租户（omnigibson 11 GB + rope_unwinding 链 6–10 GB + 本进程），耦合审计与 build 行和 08-26 逐字相同，同时刻无臂 spike `settle` 能跑；十分钟后原样重跑通过。记为 GPU 争用，不是执行链问题；sweep 时若再遇到同样的首步终止，先看 `nvidia-smi` 再复跑该格。
2. seed 0–9 三组（09-04 22:30 起，`runs/ring_transfer_variation/20260904_223036/`）：首跑 oracle 9 / 10、visual 9 / 10，两个缺口（oracle seed 0、visual seed 9）都是首步 libuipc `cudaErrorInvalidDevice`——与固定布局第一次尝试同一症状，GPU 争用；09-05 GPU 空闲时复跑（`…/20260905_rerun/`）两格都过：oracle seed 0 PASS（1375 步，一格 136 s）、visual seed 9 出片。合计 oracle **10 / 10**，lift_only **10 / 10 判失败**（读数要打折，见下），visual 10 / 10。

   | seed | on_post | 柱高 / 半径 / 挡头 | 柱距 / 朝向 | mid | lift_low / drop | 反应式抬离 | approach 悬挂 / U 宽（需要） | 步数 | oracle | lift_only |
   |---|---|---|---|---|---|---|---|---|---|---|
   | 0 | B | 0.106 / 0.018 / 0.011 | 0.277 / +1.8° | (−0.001, +0.003) | 0.126 / 0.046 | 92 步，126.4 > 125.5 | 152 / 75（56） | 1375 | PASS（复跑） | 判失败 |
   | 1 | B | 0.113 / 0.021 / 0.009 | 0.200 / −3.1° | (+0.028, −0.027) | 0.133 / 0.053 | 85 步，135.2 > 133.2 | 163 / 73（62） | 1352 | PASS | 判失败 |
   | 2 | B | 0.099 / 0.015 / 0.012 | 0.220 / +12.8° | (+0.008, +0.022) | 0.119 / 0.040 | 93 步 | 148 / 94（49） | 1348 | PASS | 判失败 |
   | 3 | A | 0.099 / 0.015 / 0.014 | 0.217 / +18.7° | (+0.001, +0.003) | 0.119 / 0.040 | 96 步 | 145 / 90（49） | 1322 | PASS | 判失败 |
   | 4 | B | 0.087 / 0.016 / 0.013 | 0.234 / +2.2° | (+0.024, +0.017) | 0.107 / 0.040 | 97 步 | 150 / 90（52） | 1355 | PASS | 判失败 |
   | 5 | A | 0.112 / 0.016 / 0.013 | 0.186 / +18.4° | (+0.036, +0.017) | 0.132 / 0.052 | 97 步 | 141 / 106（51） | 1326 | PASS | 判失败 |
   | 6 | B | 0.106 / 0.020 / 0.009 | 0.236 / +28.4° | (+0.010, +0.022) | 0.126 / 0.046 | 79 步 | 160 / 76（60） | 1349 | PASS | 判失败 |
   | 7 | B | 0.110 / 0.013 / 0.008 | 0.254 / +16.9° | (−0.002, −0.013) | 0.130 / 0.050 | 72 步 | 146 / 89（46） | 1352 | PASS | 判失败 |
   | 8 | B | 0.105 / 0.017 / 0.013 | 0.267 / +4.8° | (+0.001, +0.017) | 0.125 / 0.045 | 96 步 | 156 / 72（54） | 1372 | PASS | 判失败 |
   | 9 | A | 0.113 / 0.019 / 0.009 | 0.219 / −16.0° | (+0.016, +0.004) | 0.133 / 0.053 | 78 步 | 163 / 73（57） | 1276 | PASS | 判失败 |

   - oracle 10 格终态都只套目标柱、两顶越过、最小间隙 ≈ 2 mm，length_ratio ≤ 1.001（没有拉伸）；柱高 0.113 时 lift_low 0.133 仍在悬挂深度 0.140 之下。
     approach 时 U 宽最小 72 mm（seed 8，柱半径 0.017 需要 54）：与角点 c189 一起，`post_shape.radius` 上界的余量在 7–18 mm。
   - 防捷径轴起作用：seed 0–2、4、6–8 从 B 出发，plan 行 `carry_B_to_A`、终态 {A:1, B:0}；3、5、9 从 A 出发。
   - **`lift_only` 对照首版无效，09-05 重做。** 首版走的是 transfer 路线的 off 段：捏住后把捏点抬到挡头顶 + 0.020 = 0.132、平移 0.060 松手。
     悬挂 140 mm 的环只把捏点抬高 2 cm 提不脱（§3c' 的老问题），10 格判失败都是因为终态 = 出生态（`top_crossed A=False`），只证明判定器不把出生态判成功。
     重做后的对照有自己的相位构造函数 `lift_only_phase`（`carry_phase` 与 `off_phase` 不动）：与 carry 相同的捏取、先抬一点、移到出生柱正上方、反应式抬离到环底越过挡头顶，
     然后水平移到两柱中点、放低到 carry 的 drop 高度、松手；环平躺在两柱之间。判据的三个条件里两个独立地拒绝它：终态绕数集合为空 ≠ 目标集合，目标柱挡头顶从未越过。

     | 格 | 反应式抬离 | 终态绕数 | 越顶 | 最小间隙（mm） | 步数 | 判定 |
     |---|---|---|---|---|---|---|
     | 固定布局 | 85 步，环底 124.4 > 120 | A 0、B 0 | A 越、B 未越 | A 2.0、B 13.5 | 1229 | 失败 |
     | seed 3（A 出发） | 96 步，120.4 > 119 | A 0、B 0 | A 越、B 未越 | A 2.0、B 15.3 | 1260 | 失败 |
     | seed 0（B 出发） | 92 步，126.5 > 125.5 | A 0、B 0 | B 越、A 未越 | B 2.0、A 47.6 | 1303 | 失败 |

     `runs/ring_transfer_variation/20260905_lift_only/`。抬离段的读数与 oracle 同一格的读数一致（固定布局 85 步 / 124.4 mm 与 carry 复跑相同），
     说明对照与 oracle 共享的只是几何，不共享判定结果。判据的一个理论缺口另记：它不检查松手后环相对挡头的高度，环平躺在目标柱挡头顶面上
     （挡头直径 52–72 mm，环宽 100 mm）会读成绕数 1 且越顶为真；现有对照都不覆盖这个情形。
3. 固定布局 `lift_only`：见上表第一行。
4. 角点子集 `runs/ring_transfer_variation/corner_subset.txt` = c004 c074 c112 c127 c129 c142 c189 c247（编号 = on_post·128 + height·64 + radius·32 + overhang·16 + spacing·8 + heading·4 + mid_x_frac·2 + mid_y_frac，0 = 下端 / A）：
   c127 柱最高 × 最粗 × 挡头最大 × 柱距最远 × +30° × mid 上界（carry_in_workspace、hand_reach、lift_low_below_hang 同时最紧）；c112 / c247 同样的柱形在柱距最近、两根出生柱各一；c074 高瘦柱、柱距最远、−30°；c189 矮胖柱、柱距最远、+30°、B 出生；c129 / c142 / c004 最矮最细柱在近 / 远柱距、两个方向。
   `CORNERS="$(cat runs/ring_transfer_variation/corner_subset.txt)" bash bash_scripts/tests/variant_corners_sweep.sh ring_transfer oracle`。

   **首跑（09-05 01:13，`runs/ring_transfer_corners/20260905_011329/`）oracle 4 / 8**：A 出发的四格全过、B 出发的四格全在建场景前退出。
   不是物理问题，是派生写了一个非标量叶子：`derive_task_cfg` 把 `goal.instruction` 改写成带空格的句子「Move the elastic loop from post B onto post A.」，
   角点 sweep 脚本把 Hydra 覆盖按空格切词后 Hydra 报 `Error parsing override 'the'`（A 出发时指令串与 yaml 相同、不进覆盖，所以照常跑；进程内的
   `check_variant_corners.py` 用列表传 token，没暴露）。处置：yaml 的 `goal.instruction` 改成模板 `… post {start} onto post {goal}.`，柱名由
   `RingTransferLayout.instruction()` 填，派生只写 `goal.on_post`；demo 的 plan 行打印拼好的指令。教训记进 §7.1：**派生只能写标量、无空格的叶子**。

   | 角点 | 取的极值 | 反应式抬离 | 悬挂 travel / approach（mm） | U 宽（mm，需要） | 步数 | 结果 |
   |---|---|---|---|---|---|---|
   | c004 | A；最矮最细柱、挡头最小、柱距最近、+30°、mid 下 / 上 | 70 步（xy 4 / z 65），环底 107.6 > 93 + 12 | 143 / 104 | 107 / 136（46） | 1295 | PASS |
   | c074 | A；最高最细柱、柱距最远、−30°、mid 上 / 下 | 71 步，环底 138.0 > 135 | 177 / 135 | 87 / 97（46） | 1321 | PASS |
   | c112 | A；最高最粗柱、挡头最大、柱距最近、−30°、mid 下 / 下 | 93 步（xy 23 / z 69），137.9 > 135 | 154 / 157 | 92 / 80（64） | 1280 | PASS |
   | c127 | A；最高最粗柱、挡头最大、柱距最远、+30°、mid 上 / 上（三行同时最紧） | 93 步，136.4 > 135 | 165 / 152 | 97 / 76（64） | 1340 | PASS |
   | c129 | B；最矮最细柱、挡头最小、柱距最近、−30°、mid 下 / 上 | 70 步（xy 3 / z 66），106.1 > 105 | 151 / 105 | 94 / 141（46） | 1305 | PASS |
   | c142 | B；最矮最细柱、柱距最远、+30°、mid 上 / 下 | 71 步（xy 0 / z 70），112.1 > 105 | 171 / 141 | 87 / 97（46） | 1361 | PASS |
   | c189 | B；最矮最粗柱、挡头最大、柱距最远、+30°、mid 下 / 上 | 93 步（xy 22 / z 70），108.1 > 105 | 169 / 155 | 93 / 71（64） | 1364 | PASS |
   | c247 | B；最高最粗柱、挡头最大、柱距最近、+30°、mid 上 / 上 | 96 步（xy 26 / z 69），135.2 > 135 | 157 / 141 | 90 / 102（64） | 1346 | PASS |

   B 出发的四格复跑（09-05 10:48，`runs/ring_transfer_corners/20260905_b_corners/`）**4 / 4**，合计 **8 / 8**：终态都是 {A:1, B:0}、两顶越过、最小间隙 1.9–2.0 mm；
   plan 行印出 `carry_B_to_A` 与拼好的指令。最紧的一格是 c189：最粗柱要求 U 宽 64 mm，approach 时实测 70.9 mm，余量 7 mm——这是 `post_shape.radius` 上界 0.022 的物理证据，再往上就要重测 `hang_half_width`。

   A 出发的四格终态都是 {A:0, B:1}、两顶越过、最小间隙 2.0 mm。最矮柱（c004）approach 时悬挂只有 104 mm、U 宽却撑到 136 mm：环底 40 mm 高时
   绳大半还在指尖附近，U 更扁更宽，对套柱有利。最粗柱（c112 / c127）需要的 U 宽 64 mm，实测 76–97 mm，余量 12 mm 以上。

### 7.5 文件集

```
configs/task_configs/ring_transfer_topogym_tabletop_v1.yaml   posts 改 dict + post_shape + pair；on_post 标量；六个派生叶子删除；rope.radius / contact_d_hat 字面量；reach / workspace / variation 块
configs/run_configs/ring_transfer.yaml                        randomize_layout / difficulty / variant_id
topogym/tasks/routing/_ring_transfer_geometry.py              常量五个；posts_from_config(dict, shape)；ring_from_config 接收 long_axis / on_post；pair_*、long_axis_from_heading、pinch_side_for、pinch_along_for、carry_heights、mid_*_window、value_from_frac；carry_path 三高度改参数；ring_transfer_checks 十五行
topogym/tasks/routing/ring_transfer.py                        Layout 派生属性、mid_windows / checks / validate；derive_task_cfg / validate_task_cfg；_assert_literal_copies；builder 先 validate；_add_post 读 post_shape；transfer 三个 cfg 读法收进 Layout
topogym/planning/ring_transfer_planner.py                     drape / off 段改问 Layout（near_side_landing / transfer_carry_z / off_shift）；新增 lift_only_phase（对照专用，carry / off 不动）
topogym/verification/ring_transfer_verifier.py                from_layout 的 goal 读 layout.target
demos/routing/ring_transfer_physical_demo.py                  randomize_task_cfg 接线；variant 行 + checks 行
tests/check_ring_transfer_geometry.py                         carry 段改打印 checks() 十五行；变体包络段（还原、旋转、on_post B、256 角点、三负例）
tests/check_variant_rng.py                                    check_ring_transfer_randomization
tests/check_variant_corners.py                                TASKS["ring_transfer"]
tests/README.md                                               两行
bash_scripts/tests/ring_transfer_variation_sweep.sh           新：visual / oracle / lift_only
bash_scripts/tests/variant_corners_sweep.sh                   ring_transfer 分支
docs/develop/tasks/variation_axes_plain_zh.md                 §2 柱高注、§6.2 第 10 行
docs/progress/weekly_tracker_zh.md                            §1 第 10 行、§3、§4
```
