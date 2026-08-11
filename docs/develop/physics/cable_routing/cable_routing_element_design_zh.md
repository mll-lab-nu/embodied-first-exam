# Cable Routing 全要素建模方案(基于真实布线方式)

> 日期:2026-07-12
> 背景:此前 cable_routing 的 S 桩/蓝色方块自由端/红 socket 盒均为占位几何;用户要求所有 rope 任务统一"绳+端点"建模,并以真实 cable routing 场景为原型重新定义全要素。
> 决策(2026-07-12,用户确认):**复用 untangle 的插头端点建模**——untangle 唯一不可迁移的语义支点是孔洞棋盘,cable 以"port 底座"替代;插头/顶部出线/圆柱锚定/双态生命周期整套照搬(prefab 化后两任务同源)。

## 一、真实世界映射

现实中的 cable routing(机柜理线/设备面板布线/NIST 装配任务板类):**一根两端带成型插头的成品线缆,从源设备端口出发,绕过理线柱(保证弯曲半径、避开区域),插入目标设备端口**。

| 任务元素 | 旧占位几何 | 真实原型 | 新建模(迭代 2 定稿)|
|---|---|---|---|
| 绳 | PBD 弹性管 ✓ | 成品线缆 | 不变:`prefabs.rope_pbd` + cable 细网格(0.0055/12)|
| 自由端 | 蓝色 box 0.022³×0.032 | 线缆插头 | `prefabs.rope_endpoint_connector` 灰插头(与 untangle 同一 mesh),绳顶部沿轴出线,origin=柱心;**初始坐在 spawn 插孔座里**("拔出"语义)|
| S 起点 | 绿桩 + 绳粒子世界钉死 | **固定端子**(线缆不可动端从设备端子引出)| `prefabs.rope_fixed_terminal`:底板+壳体+出线颈 gland,绳从颈顶垂直引出;绳 START 粒子圆柱带焊到端子 |
| C 终点 | 红 socket 盒(墙壁无碰撞)| **目标插孔座** | `prefabs.rope_socket_housing`(红色):底板+座体+真实 counterbore 孔;落座 = 法兰贴座顶、销入孔;latch 语义/无碰撞(flyout 修复)不变 |
| spawn 位 | (插头裸立板面) | staging 插孔座 | 同款 socket(中性灰)——任务视觉链 = **拔出 → 绕桩 → 插入** |
| P1/P2 | 光秃圆柱 | 理线柱(routing post,底法兰+顶帽防滑盘)| **碰撞体保持现有圆柱不动**;法兰/顶帽做无碰撞装饰件(见 §四取舍)|
| (无) | — | 卡扣 clips / 线槽 | 本轮不做(snap-in 是新接触难题;benchmark 关注路径拓扑,绕柱已足)|

> 迭代 1 的"port 平垫圈底座"方案已被插孔座取代(用户反馈:插头直接立在平面上不自然);`port_base` 配置键留档。z 链单参贯通:插头坐座 origin = 板 + 座顶 0.016 + 柱心 0.012 = 0.028 → `physical.z_offset = 0.019`(留档链 0.015→0.003→0.019)。出线弧按端参数化(`with_end_entries`:S 端用端子高度、自由端用座+插头高度),untangle 经包装器保持零变化。

**端口朝向:垂直(顶部插拔)**。水平设备口更"像"桌面设备,但会破坏顶部出线的统一绳端建模、夹爪需侧向进给(工作空间/IK 复杂化);垂直口与 untangle 完全同构(同一套插头/出线/抓取/latch 代码),真实世界亦常见(面板馈通、DIN 端子)。水平口否决留档。

## 二、生命周期(与 untangle 同一状态机)

S 端插头 SOCKETED 常驻(fixed);自由端插头:**spawn latch 托住**(mesh-only 无碰撞,防坠)→ 夹爪闭合 `on_close` 原子交接到手部 attachment(GRASPED)→ 绕 P1/P2 拖拽(assisted,绳张力物理演化)→ C 端口捕获域 snap 落座(现有 ConnectorLatch,容差沿用)→ 张爪撤退。无 FREE 态。复用件:`PBDHandleDragPrimitive.on_close`、`ConnectorLatch`、`AttachmentManager`、`connector_anchor_indices`(圆柱带锚定,消球形带的单粒子撕裂模式)、`with_connector_entries`(顶部出线,自 UntangleLayout 泛化)。

## 三、关键几何参数

- 插头 = `prefabs.rope_endpoint_connector`(柱 Ø15×14mm、法兰 Ø22×5、灰 [0.62,0.63,0.65]),origin=柱心(板上 12mm);
- demo `physical.z_offset` 0.015→**0.003**(柱心 12mm − rope.z 9mm;planner 与 handle 形状解耦,z 链路经此一参自动正确);`grasp_qpos`→0.0075(=柱半径);
- port 底座:环外径 0.028、厚 2mm;凹口盘 0.013、深色;
- 理线柱装饰:底法兰 = 杆径+4mm/厚 3mm,顶帽 = 杆径+5mm/厚 3mm。

## 四、实施取舍记录

1. **理线柱顶帽 = 纯视觉**:若做进碰撞体,凸包会把"杆+帽"撑成帽径粗圆柱,改变绕线半径且丢失防滑语义;保持物理圆柱不变 = wrap 行为零变化(一次一类变化原则)。若日后实测绳上滑脱柱,再评估凸分解碰撞;
2. **S 端从 fix_particles(世界)改为 fix_particles_to_link(fixed 插头)**:物理等价(固定 link),换来的是端点视觉与 untangle 同源;
3. box handle/绿桩/红 socket 盒配置注释留档,可整块回退;
4. episode stable_id 会变(endpoint_handle 在 layout.objects.rope 内)——预期。

## 五、验证

每阶段:untangle 回归门(参数等值断言+网格哈希,GPU viewer 应零变化)+ `python -m demos.routing.cable_routing_physical_handle_demo run.viewer=true run.probe=true run.verbose=true`(看:S 端子出线、插头从 spawn 座拔出、绕桩张力、插入 C 座、全程无 flyout/不中断)。

## 附录:迭代 2 的"脱手断流程"诊断(2026-07-12)

用户 GPU 实测迭代 1 版本中途"插头脱手、流程中断"。headless `--probe --verbose` 复现实锤:

- `[pbd_handle abort 06/137] label=smooth_005 target_error=0.0716 > target_limit=0.0700`,同刻 `handle_follow_error=0.0070`——**attachment 辅助工作正常**(插头 7mm 内跟手),被掐断的是**摩擦时代遗留的 target-lag 检查**(手对指令航点的滞后是控制器属性,assisted 模式下不构成抓取失败;cli_commands 历史上就需要 `--allow-target-lag` 才能到 C);
- abort 后失败路径把插头瞬移回 spawn = "脱手"观感;
- 无 FLYOUT、无绳-指钩挂签名 → 机器人 PBD 耦合保持开启(一次一类变化)。

修复(均 gated 在插头模式):`max_segment_target_error=None`(等效 --allow-target-lag,成功门仍是 C latch + connector_error_xy)、`max_downward_follow_error_z=None`(attachment 下死信号)、失败路径改为"原地冻结在爪中"(latch 钩子越过 attachment manager 生命周期,viewer hold 期插头不坠)。

## 附录 2:迭代 3——P2 弹飞的物理解(2026-07-12)

**症状**:用户 viewer 实测 P2 绕桩段绳中段弹飞;probe 实锤弹飞前一拍 `rope_minz=+0.002`(绳贴桌被拖)+`p2_gap` 收窄 → **柱底×桌面 90° 楔角双面挤压弹射**。

**方向裁定(用户)**:不用"机器人退出 PBD 耦合"这类关闭物理的方案(needs_coup 提案否决记档);优先柱形/柱高/路径的物理解。

**修复与归因(A/B 门法)**:
- A1 柱基座喇叭:注意**"陡坡基座+直杆"单体不是凸体**(凸性要求半径函数上凹),凸包会把绕线半径撑粗;正解 = **复合碰撞体**:原直杆圆柱(绕线半径 12mm 精确不变)+ 独立凸台锥(r 0.016→0.012 / 10mm,楔角 90°→112°);顶帽仍装饰;
- A2 wrap_z_lift 0.024→0.040(接触点上移离开基座区);A3 柱高 0.090→0.070(前臂净空);
- 门 A 结果:**拖拽/绕桩段全清**(p2_contact=101 缠绕完好),但弹飞转移到**落座 snap 瞬间**(高接触压力缠绕态对冲量敏感)→ 触发 B;
- B:volume 三件套任务级 fork 回调抗弹射软值(maxvolume 5e-8 / vol iters 16 / vol_compliance 0.0020)——**缠桩高压态是 cable 特有工况**,当年 flyout 实验 #1 的调软值在此确实必要;stretch/bending/摩擦/密度仍吃 prefab 单源;
- 门 B 结果:**全程 max rope_spread=0.278,零弹射**,137/137、落座 0 误差、P2 wrap verify 全绿。

## 附录 3:绳"折线感"归因与缓解(2026-07-12)

**归因**(与 untangle 配置全量对比):折线/刚体观感 = ①**弯曲刚度偏硬**(参数统一使 cable bending_compliance 0.0100→0.0030,硬 3.3 倍;张紧绕桩下呈接触硬折角+直弦——主因)× ②**变形节点偏稀**(iter-3 maxvolume 5e-8 粗 tet;视觉皮肤跟随 tet 顶点,节点间为直线段)。cable 更细的**表面**网格(0.0055/12)帮不上——形变分辨率由 tet 密度决定。张紧姿态下的"直"部分为物理正确,消折角不消直线。

**分级缓解结果(2026-07-12 定档)**:
- Stage 1 @0.0080:稳定门过,用户观感"折角弱化但仍在";
- **Stage 2(maxvolume 回细 2.5e-8):稳定门失败**——~~决定性负结果:粗 tet 承重~~ **【2026-07-13 更正:此归因有误】** 复查 runs/cable_stage2.log:细 tet 弹射发生在 `phase=connector_latch`(C-snap),前一拍 rope_spread=0.225/p2_contact=119——**绳带细 tet 走完全程+两次绕桩完全稳定**,只在当时的水平侧滑 C-snap 炸。该落座动作已被垂直悬停下插取代,故弹射触发条件已消失;**细 tet 未被证明是绕桩必需,待在当前管线重测**(见 B-TEST);
- Stage 1 打满 @0.0100(历史全值):稳定门过(max_spread 0.278、落座窗口 p2_contact 69-93、137/137)。**这是物理参数侧安全可得的极限**;
- 剩余折角的正解 = redesign §3 渲染层样条 sweep(判定渲染同源),另立项;Stage 3(stretch fork)备而未动(副作用触及布线张力语义)。

**落座动作修正(2026-07-12)**:smooth route 原以坐座高度横向抵达 C(观感=侧蹭穿座沿)。demo 在插头模式下把末段拆为两段:C 正上方悬停(+`physical.insert_hover_lift`,默认 0.035,销底高于座顶)→ `insert_at_C` 垂直下插到坐座位——自上而下"插进去"。门:138/138、落点误差 4.1mm、latch 咬合、稳定无恙。

**端口形制三案定档(2026-07-13,取代上一段的凸台座+碰撞裙方案)**:凸台插孔座陷入两难——无碰撞被拖绳穿模;加碰撞裙后又**挡绳**(绕线视觉从"绕 P1+P2"劣化为"绕端口+P2")。用户三案取舍:①挪位置(否:spawn=路径起点,牵连路径安全验证);②大幅降高(次选:仍留残余交互);③**平嵌端口(定档)**——边框环 2mm + 深色凹陷孔,低于绳径,**不挡绳、不可见穿模、零碰撞体零弹射风险**,与 untangle 孔位语义同构;垂直插入 + 销没入板下保住"插进去"读感。z 链第四档:坐港 origin=板+14mm → `z_offset=0.005`(留档链 0.015→0.003→0.019→0.005)。凸台座/碰撞裙生成器保留为 prefab 备用件。门:全程 spread 0.277、零弹射、138/138、插入落点 2.8mm、P1 物理缠绕 108 接触点恢复健康。已知残余:绳正压过 2mm 边框环瞬间可有 ≤2mm 视觉重叠(与 untangle 孔盘同级,评测距离不可辨)。

**末段轨迹与插孔可见性(2026-07-13)**:①平嵌端口使 exit-to-C 航点贴地滑行(法兰离板 2mm)——demo 记录最后一个 wrap 抬升航点,其后**整个尾段抬到悬停高度**(坐港+35mm,XY 沿用安全验证路径),高位直达靶心正上方后一次垂直下插;门实测尾段 z 恒定 0.9686 → 0.9336,无触地平移。②C 平嵌孔曾被 4 层红白靶心(顶 4.9mm)整个盖住——深色凹陷孔按靶心叠层自动推导加高,穿出顶层 0.6mm,"靶心中央一个插孔"可见(坐姿 z 链只读 rim_height,不受影响)。

## 附录 4:绳"完全柔体"可行性评估(2026-07-13,Genesis 1.2.1 源码核实)

**结论:物理层"完全柔体绳"在 Genesis 1.2.1 内不可原生达成。**依据:①PBD 材质族 = Cloth(2D)/Elastic(3D tet)/Liquid/Particle,**无 1D Rod/Cosserat 绳原语**;②tet Elastic 的弯折尺度由 tet 尺寸决定,cable 的 tet 已被稳定性锁死(5e-8,回细即弹射,附录 3 决定性负结果);③弯曲柔度已在历史最软(0.0100)——物理侧杠杆用尽。

**两条视觉路径**:(a) `vis_mode='recon'` 粒子表面重建(splashsurf/openvdb)——demo 已挂 `--rope-recon` 实验开关,一行启停零残留;风险=形状发糊、逐帧重建性能;(b) **渲染层样条 sweep(立项建议,推荐)**——逐帧对绳心线拟合 Catmull-Rom 重蒙皮,观感上限最高且满足 redesign §3"判定与渲染同源";两条实现路线:动 Genesis 蒙皮管线(工程大、双任务实时受益)或录制后处理(零引擎风险、仅录制受益);建议与组长同步后独立立项。

**末段手部"上下颠"修复(2026-07-13)**:日志实锤为逐航点锯齿(段内 z 循环 0.960→0.956→0.958,常速 ±7mm)——`_move_hand` 每段从含 PD 重力下垂的**实际手位**重插值到命令高度所致。修复 = primitive 新增 `command_space_segments`(opt-in,默认关零行为变化):段插值锚定上一段**命令**目标,下垂变恒定偏置、锯齿消失;cable 插头模式启用,untangle 暂不动。

**废案清扫(2026-07-13)**:观感改造阶段性定稿后删除全部死代码——recon 蒙皮实验(demo `--rope-recon`+vis_mode 透传)、凸台插孔座与碰撞裙生成器(`socket_housing_*`/`socket_collision_skirt_*` 五函数,grep 证零调用方)、prefab `rope_socket_housing` 块、C 口老 socket 墙(`_add_connector_socket` 方法+分支+yaml `C.socket` 块+demo override)。保留:box/圆柱回退分支(config 可达)。门:untangle 零变化(config+网格哈希)、cable 12 航点冒烟通过。

**绳初始形状:折线 → 样条(2026-07-13)**:折线感的 A 类根因经离线硬数据确认——cable 绳 spawn 用 `routes.initial` 的**9 手写控制点直连折线**,7 个 waypoint 硬角(31-73°,均值42°);`route_polyline` 只 stack、`_sample_polyline` 只细分不磨角;`smooth_route` 只管 oracle 手路径不碰绳形。修复:`rope.centerline_spline` 开关(prefab 默认关=untangle 零变化;cable 开)→ `catmull_rom_centerline`(向心 Catmull-Rom 穿过原控制点)磨平,实测逐点转角 73°→11°、硬角 7→0、绳长 +1.6%、peg 净空 89/236mm。**一个自交坑**:样条把绳身加密到 5mm 后,`with_end_entries` 的 24mm 端点位移+落地会和端部密集点重叠→tube 自交→tetgen `recoversubfaces` 崩;修法=样条后用 `reserve_endpoint_footprint` 剔除每端 entry footprint(~24mm)内的绳身点(保留真端点),恢复稀疏端点条件。自由端 hairpin 处剩 8.28mm 净空(管径8mm,边际,tetgen 通过;新增路由变体时需留意)。门:全程 138/138、max_spread 0.30、无弹射、双桩缠绕、初始绳形肉眼平滑;untangle 三绳 mesh 哈希零变化。

**遗留(非本轮引入)**:`routing_success=False` 来自 P1 的 `endpoint_route_ok=False`(手部轨迹在 P1 左侧投影不足;`rope_wrap_ok=True` 绳物理缠绕正常)。smooth-route 重设计时即记录"P1:left 运行时验证未做"——属路径/判据校准问题,待下轮:要么微调路径让手部更深入 P1 左侧,要么把成功判据改为以 rope_wrap_ok 为准(评测语义变更,需用户拍板)。
