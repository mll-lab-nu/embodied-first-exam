# 三难度 setting 补齐工程计划

2026-09-29 Blanket 更新：按用户当前优先级先补统一聚褶 0° / 135° / 270° 的三档场景，沿用平坦出生、物理构形和冻结初态方案，显式暂缓粒子运动资格。实现、调用和验收范围见 [Blanket 当前说明](blanket_flatten_zh.md)。下文关于必须先解决静稳再部署的原排期，已由本轮场景布设范围调整；完整静稳及机器人难度仍待验，不改写历史失败。

> 2026-09-29 Orbits 更新：两／三／四环已接入标准 Task；共用当前 0.85 比例、0.8 m 紧凑绳与外置木柄。三档资产及同 seed 重建通过，真实静置验收遇到共享 GPU／CUDA 初始化阻塞，尚未取得稳定性或解法资格。当前实现与复现命令见 [Orbits 任务页](orbits_zh.md#2026-09-29两三四环场景与稳定性验收入口)。下文计数、75% 长绳代表及先证明路线再接入的顺序均属 9 月 25 日计划；本轮按用户要求先补场景和稳定性验证。

2026-09-29 Rope 场景更新：按用户“先把场景建好”的范围，easy 已接入原 R1/R2（138 mm 净孔），hard 已接入三环 100 mm 净孔；medium 保持原样。三档共用绳初态与材料，支架连接和有序目标合同均已接通。具体资产检查与场景预览见 [Rope 说明](rope_threading_zh.md)。这一步完成场景部署，连续解法、捷径及难度排序验收仍未完成；下文 2026-09-25 的全局数量为当日快照。

2026-09-25。状态：已实施第一批可隔离的几何参数化与 PBD 绑定审计，结果见第 9 节；尚未切换难度入口或部署 Blanket 新初始化。共享 simulator／terminal 正在由其他会话修改，保留其最新实现。

目标是让 13 个任务各有明确、可复现的 easy / medium / hard setting，并分别记录构造、运行、解法和难度资格。当前 39 档中 32 已接入，6 个 planned、1 个 blocked。本文优先补 Rope、Slotted、Orbits 的 6 个空档和 Blanket hard，同时按用户新方向设计 Blanket 的统一扭转三档。若采用该方案，实际是 **7 个空缺档位补齐＋2 个已有 Blanket 档位改版**，不是只新增 7 个参数文件。

## 1. 两项设计判断

### 1.1 Orbits：环少是否必然更简单

**不能直接断言；可以作为优先验证的假设。** 在环柱递进关系、初始绕绳方式和局部通行余量保持同一规则时，较少层级有望减少回穿与整理阶段，因此保留两／三／四环作为第一版候选。这是本项目的设计推断，不是已经证明的最少动作数关系。

本地四环参考记录包含 15 个阶段、93 个外力脚本动作，其中有多轮第一环回穿；这说明四环已知解有重复结构，但 93 混合了提圈、运输、整理、落桌等细动作，并非拓扑最短步数。两／三环对应解尚不存在，不能把 93 按环数比例折算，也不能直接套九连环的递推公式。来源见 [Orbits 说明](orbits_zh.md)。外部[厂商 Orbits 页面](https://www.siammandalay.com/products/orbits)可用于确认产品来源；本计划不将产品分类或难度描述作为本项目两／三／四环单调难度的证据。

需要验证的反例包括：删环后原本被困的绳圈可直接抬出；重排阶梯后抓点反而更难到达；绳长沿用四环值造成多余堆绳；某一奇偶环数改变回穿方式。工程验收应先得到三档各自的可行路线，再在相同动作语义下比较回穿轮次、过孔事件、展开／换手阶段和容错。找到的一条长路线只给出可行解，不能证明不存在短解。

如果两环仍需要核心回穿但轮次少，可以接受 easy；如果两环退化成一次直拉，或两／三环难度无法分开，应调整初态／结构并重新验证，而不是强行保留档位标签。仍不成立时，记录结果，再考虑同器具不同受困初态作为另一个设计方案，不静默替换。

### 1.2 Blanket：能否按扭转程度逐档增加

**可以，且比同时更换折叠、卷曲和扭转结构更容易解释。** 建议三档采用同一种纵向聚褶构造，固定布料尺寸、材料、网格、褶数、聚褶程度、轴向收缩与桌面位置，仅改变沿长轴的扭转总角度。

第一轮搜索中心建议 **0°／135°／270°**，分别作为 easy／medium／hard 的候选；这些是试验起点，不是已验证尺寸。easy 的 0° 仍保留聚褶，不能一开始就满足展平判据。若中档稳定形态与 easy 太近，可比较 90°／180° 等邻近候选，最终只冻结一组三档。

必须区别：旧 medium 的 `roll_angle_deg` 表示折铰累计卷曲，不能直接当作长轴扭转角；当前 hard 的 `gathered_target` 才具有这种目标。三档共用聚褶构造会替换现有 easy 的五折、medium 的三折五卷，旧实例与证据必须保留修订身份。

**角度越大也不保证越难。** 更高扭转可能储存更多弹性变形，释放后自行展开；可见抓点、层间摩擦和自接触也可能改变解法。必须在准备控制撤除、正常重力下稳定后测量实际扭转、覆盖面积、层叠、材料伸长和是否自行达成终态；不能只比较目标参数或第一张目标网格。

## 2. 全部 13 项的目标表

| 任务 | easy | medium | hard | 本次 setting 工作 |
|---|---|---|---|---|
| Cast Keyhole | F1 long_stroke | F2 eccentric_window | F3 turnback | 保持已有构造，后续核对路线与捷径 |
| Cast Coil | baseline_assembly | axial_screw_turn | split_turn_offset | 保持已有构造 |
| Horseshoe Ring | waist_mild | u_mild | waist_ellipse | 保持刚选定的形状三档；机器人解法与排序待验 |
| Hedgehog in Cage | CLASSIC | oblique_gate | gen_keyhole | 保持已有构造 |
| Lock Picking | one_retreat | standard_150mm | three_retreats | 保持已有构造；easy/hard 缺完整机器人证据 |
| Fiber Bundling | 4 芯 | 8 芯 | 16 芯 | 保持已有构造 |
| Buzz Wire 3D | F1 | F2 | F3 | 保持已有构造 |
| Interlocked Claws | B0 balanced | C0 balanced | A0 claw_weave | 保持已有构造；旋转／翻转必要性需捷径检查 |
| Knot Untying | overhand_trefoil | figure_eight | double_overhand | 保持已有构造；后两档完整成功待补 |
| Blanket Flatten | 低扭转聚褶 | 中扭转聚褶 | 高扭转聚褶 | 拟统一构造；首轮中心 0°／135°／270°，全部重新验初态 |
| Rope Threading | 两环 | 原三环 | 三环小孔 | 补 easy/hard，medium 作为回归锚点 |
| Slotted Post Ring | 大环宽松顶部解脱 | 中环定向顶部解脱 | 原尺度解法 | 补 easy/medium，先验证机制与端盘约束 |
| Orbits | 两环阶梯 | 三环阶梯 | 原四环 video-v2 | 补 easy/medium，验证重复解题阶段是否递增 |

这张表是实施目标。当前运行入口仍以[部署实施记录](variation_deployment_implementation_20260925_zh.md)和 registry 为准；本文不会将占位状态提前改为 integrated。

## 3. 四项具体工程

### 3.1 Rope Threading：先补最直接的两档

现有 [ThreadingLayout](../../../topogym/assets/geometry/rope_threading.py) 从固定 reference 读取环与绳，已有 `ring_mesh`、`route_crossings` 和 [FEM Task](../../../topogym/tasks/rope_threading/common.py)。缺少的是显式布局选择／尺寸配置及其共同验证，不是缺圆环建模工具。

实施内容：

1. 为布局增加稳定 ring ID、有序目标环列表和孔径参数，支架／底座随所选环生成。保留 medium 的原资源、尺寸和变换行为，避免改变已部署实例。
2. easy 首选保留原顺序中的前两个目标环，移除第三环及对应支架，暂不加大孔径。这样首先只改变环数；确认可达和初态后再冻结，若不合适记录原因并选择另一组。
3. hard 保留 medium 三环位置、法向和顺序，先只减小内孔。固定绳半径、材料和初始形态，参数搜索必须同时检查目标环线材外径与支架连接，不能缩了环却悬空。
4. 同步输出有序环信息、绳材料坐标与实际孔径，供 terminal 会话消费；不把开放绳简单闭合后的净绕数当成逐环穿过证据。
5. 接入 `rope_threading_easy.py / hard.py`，维持现有标准 EntitySpec、FEM／IPC 与 simulator 接口。

验收：初态无非法接触、未提前穿环；easy 路线完成两个指定目标，hard 完成三个；存在正通行余量与连续机器人可达路径，不以小于实际绳碰撞直径的孔“制造 hard”。少一个环可以减少要求，但不能未经验证宣称必然少一次换手。环距变化作为后续单独实验轴，本轮不同时加入。

### 3.2 Slotted Post Ring：先确定尺寸窗口，再部署

[SlottedPostLayout](../../../topogym/assets/geometry/slotted_post_ring.py) 已开放目标环主半径／管径、柱、槽、珠和端盘尺寸，合法性检查能用于候选筛选；[clearance36](../../../topogym/tasks/slotted_post_ring/slotted_post_ring_clearance36.py) 只改槽宽，不能直接充当 easy。

实施内容：

1. 固定 hard 的柱、绳、珠、端盘和环管径，以目标环主半径为单一搜索轴；先求满足初态无穿透、基座支撑、端盘保留等必要条件的候选区间。静态尺寸不等式仅作预筛。
2. 为每个候选尝试完整“顶部解脱”路线，检查环—柱—绳—珠—端盘的连续运动。另检查向绳末端脱出等被禁止捷径；不能只测裸柱能否穿环。
3. easy 选择顶部路径位置／倾角容差较大的代表；medium 选择仍可行、但需要更准确倾角的代表。比较容差而非仅给两种相近半径贴标签。
4. 对原 hard 也复查顶部短路线。现有 validate 本就要求环可套住柱截面，hard 不能顶部取出的原因必须来自完整组装状态，不能只凭“环小”推断。
5. 冻结参数后填 `slotted_post_ring_easy.py / medium.py`，并向 terminal 提供目标物与有效分离区域所需描述。

若在固定端盘条件下找不到非空且区分明显的尺寸窗口，输出失败候选与原因，重新评估机制。不要扩大端盘、移动珠或加私有约束后仍声称只改了环径；若确需改动其他部件，作为明确的新修订设计。

### 3.3 Orbits：几何、绳初态与解法阶段一起参数化

改动坐标：[orbits.py](../../../topogym/assets/geometry/orbits.py) 的 `OrbitsLayout.validate / geometry_report / make_meshes / cord_centerline`，[orbits_initial.py](../../../topogym/assets/geometry/orbits_initial.py) 的工作绳生成，[common.py](../../../topogym/tasks/orbits/common.py) 的布局／绳 profile 接线及 easy／medium 入口。

实施内容：

1. 支持 N=2/3/4，柱数为 N+1，环／柱／顶球语义 ID 按层级生成；替换 `range(4)`、第五柱等固定假设，并核对几何报告和下游判据中的同类假设。
2. 保持局部孔径、管径、柱距、阶梯高差、最低环下方通道与统一尺度策略。顶层高度随 N 变化必须记录并检查机器人可达性，不把不可达当 hard。现有 hard 75% 精确实例保持回归。
3. 初态绳圈按同一规则受困在最后一柱、最低环下；木柄两端连接不变。新 profile 显式规定绳长和摆放余量，不能照搬 `working_cord` 的四环绝对控制点或自动继承四环默认绳长。先尝试共用可行绳长；如需按层数调整，用固定、可审查的长度规则并记录其影响。
4. 为两／三环建立分阶段几何解，记录有序过孔／回穿事件、受控材料点、抓点转换与结束分离。抽象阶段模型可以帮助比较，但只有物理可实现的转换才能作为可解证据。
5. 做直接提圈、拉柄、越球及跳过中间层的短路线检查；结果应区分已发现捷径、已测捷径被阻挡、尚未覆盖的动作，不宣称穷尽所有策略。
6. 只有三档都存在有效解且差异可解释，才冻结两／三环代表。若回穿阶段未递增，优先修正设计，不以强制 planner 绕远路补差异。

不能要求 agent 必须复现 93 动作脚本；任务仍按合法终态判定。宏观动作和路线用于设计解释与诊断，不作为惩罚替代解法的隐性规则。

### 3.4 Blanket：共用聚褶准备，再改变扭转角

用户后续补充：初始观测应是**布料已平稳放在任务桌面上**，不再展示悬空自由落体。PBD 跨层视觉误绑必须先解决，绑定与紧密初态构造分离；具体调查、初始化方案与新增脚本范围见第 8 节。本节中的稳定等待须采用验收条件，不能只等待固定步数。

现有能力包括 [generate_flat_binding](../../../topogym/assets/geometry/blanket_flatten.py)、[gathered_target](../../../topogym/assets/geometry/blanket_gathered.py)、[hard.preparation_target](../../../topogym/tasks/blanket_flatten/blanket_flatten_hard.py)，以及 [历史 preparation.py](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/preparation.py) 的受限速度准备。当前几何文件中也存在 gathered_target 定义；实施前核对两处实现与调用方，选定唯一共享入口，避免再形成两套参数行为。

实施内容：

1. 建立共用 `gathered_twist` 参数 profile。初始建议沿用现有 hard 的面板分配、褶角、尺寸与材料，仅给三档不同 twist_angle_deg。首轮关闭角度随机扰动，先得到固定代表。
2. 确认目标函数中的 `twist` 是准备进度而非难度字段：难度由总角度控制；避免通过改变进度同时改变 `axial_scale`，把轴向压缩也变成隐藏难度轴。
3. 从同一平坦材料 rest shape 构建网格，分阶段聚褶→扭转→撤除准备控制→恢复正常重力→稳定。历史脚本直接访问 solver 私有重力和 `scene.step()`，不能原样复制；提取准备数学逻辑，物理推进由现有 World 路径负责，后端写入封装在受控管理侧适配中。
4. 管理方 reset 在准备与验收完成前不交付 interaction。初始 RGB、公开 episode 零时刻和首个可回溯状态必须对应同一个准备结束状态；准备过程单独保留日志和物理 tick 来源，不与 agent 解题动作混算，也不以未完成准备的图片作为初始输入。
5. 准备失败明确报错，不静默换 seed、降角度或换一张成功网格。若使用离线准备状态，必须含材料 rest、拓扑、速度及恢复所需 solver 状态和版本身份，经过标准恢复验证；只有 OBJ／粒子位置不足以代表完整初态。
6. 无控制稳定后，沿有序材料截面测量解缠绕后的扭转分布，并结合多截面方向、层叠和覆盖面积；不能仅用两端方向主值区分 270° 与 −90°。检查三档实际形态有间隔、均未自动 solve、应变和接触有效。
7. 准备时允许的管理侧控制必须在交给 agent 前全部移除。不通过锁定布料、持续抵抗松解或只对 oracle 开放准备控制来维持难度。
8. 三档新初态通过后，更新 easy／medium／hard 的 family／revision 和元数据，将旧 simple_folds／fold_roll 的入口与参数来源归档，保留历史视频身份。过渡期不先撤掉已可用 easy／medium；整组三档准备机制通过后再切换默认。

该方案比只补原 hard 改动更多，但长期只维护一套准备流程与一条主要难度轴。若短期准备流程未通过，保留当前可用两档并报告 hard blocked，不把未验证高扭转强行装入 standard simulator。

## 4. 共同合同与工程边界

- 任务目录保持 `common.py + <task>_easy/medium/hard.py + __init__.py`；已完成三档之后再按既定规则归档表外入口。入口只声明差异，几何与状态协议由 common／assets 复用，活动代码不导入 legacy。
- 有效配置包含难度轴、冻结参数、资源哈希、初态准备修订和来源；改变 Blanket 家族或新初态时必须更换 revision，不能沿用旧成功实例身份。几何资源放包内，不依赖历史 runs 路径启动。
- 管理方选 setting 和 seed，操作方仍经 `interaction.step(action)`；现有 [SegmentRunner](../../../topogym/simulator/segment.py) 负责连续执行与产物，不新增平行 runner／录制循环。
- 初期可用特权几何检查和外力探针验证构造，但明确标为几何／外力证据；机器人可解性必须通过标准动作链，assist 能力及触发规则与实际 agent 一致。
- terminal 同步消费环 ID／顺序、目标实体和准备后基准状态；按[terminal 计划](terminal_judgement_engineering_plan_20260925_zh.md)协作，不将“找到一条路径”直接设为 solved。缺判据时可以验资产与运行，不发布正式成功率。
- 解题录像沿用 `task_rollouts/<experiment_name_date>/<task_name>/trail_<x>_<difficulty>/segment_<n>.mp4` 及现行各视角／状态索引合同。逐 tick 详细 state 和完整来源写入管理侧报告，普通 agent 保持原权限；开发预检与准备报告放 `runs/test_results/`。

## 5. 实施顺序与交付门槛

| 阶段 | 工作 | 进入下一阶段的条件 |
|---|---|---|
| A：固定设计合同 | 冻结本轮四任务主轴、保持项、终态和禁止捷径；保存原代表的源码／资源／配置身份 | 分清 7 个空缺与 Blanket 两档改版；当前 32 个已接入档位有回归锚点 |
| B：少量候选预检 | 先 Rope 两环／小孔；Slotted 尺寸窗口和 Orbits N=2/3 的解法检查；Blanket 用同一准备流程试三角度 | 每个拟落位档有合法初态、可行路径依据，关键退化已测；未通过继续占位 |
| C：标准构造接入 | 填难度入口／registry、随包资源和元数据；Blanket 管理侧准备完整接入后才切三档 | 安装包中构建成功，seed／跨目录重建一致或符合既定物理复现容差；共享接口及已有档位回归通过 |
| D：标准物理验收 | 正常重力静置、真实 RGB、短程交互、跨 segment 连续与回溯；准备状态恢复验证 | 无非法初态、准备控制残留和资产引用问题；录像与日志身份一致；不将本阶段叫做 solved |
| E：解法与档位验证 | 每档完整 oracle 路线、捷径对照、位姿扰动／多 seed 复验、相同 agent 条件比较 | 逐档报告成功／失败；可解证据与设计排序分开，最终按模型表现校准 |

实际执行建议先交付 Rope easy，再复用布局支持补 hard；在此过程中对 Slotted 做小范围机制检查。Orbits 在证明减环仍保持核心解题结构后接入。Blanket 的准备流程是最大公共工程依赖，应先做一个低扭转端到端样例，接通后逐步增加角度，不从最难初态开始调完整机器人解法。

验收区分五层：**构造接入、物理运行、几何／外力路线、机器人完整 solve、模型难度校准**。已有 registry 的 integrated 只表达第一层，其余写入独立报告，不把阶段 E 作为所有基础设施工作的前置条件。

## 6. 有针对性的检查清单

1. 参数／资产：错误 N 与非法尺寸拒绝；目标 ID 稳定；体积材料和永久连接正确；三档几何身份不同；资源可离线随包加载。
2. 已有代表回归：Rope medium、Slotted hard、Orbits hard 及未改动的另外九任务保持原合同。若修复真实缺陷导致变化，单独记录修订，不修改断言去掩盖差异。
3. 初态：无初始成功、无非法自穿透；同 seed 重建；Blanket rest shape／材料坐标不变、所有准备控制撤除、稳定后档位差异仍存在。
4. 路线：连续几何及实际动力学各自检查；环／柱／端盘连接不被破坏；数量变化带来的解法步骤变化记录为实测，不声称全空间最优证明。
5. 终态和留证：使用统一 Task 判据及标准 segment，放置／释放要求按任务合同，失败也保存最后有效状态和证据；初态准备、外力与机器人执行有明确来源区分。
6. 难度：同模型、同观测／动作／assist 条件下比较成功率、时间和重试；episode 时限足以容纳各档已知有效解，避免仅因 hard 路线更长而被人为截断。不通过额外减小时间预算来制造难度排序。

完成本计划的 setting 部分意味着 39 个主档都有可复现构造和明确状态，不意味着 39 个机器人解法或模型排序同时完成。若有限参数搜索未找到符合原设想的档位，应保留具体失败证据和占位原因，再决定设计调整。

## 7. 拟修改文件清单

以下是整体实施范围，逐项实际进度见第 9 节。“条件修改”表示先复用现有能力，仅在确认缺接口或写死数量时调整；不为了目录对称而改所有 common。Blanket 的共享接口部分须与 simulator／terminal 会话按函数协作。

### 7.1 任务与几何

所有路径相对仓库根目录 `/home/jianwen/topogym/`。

| 文件 | 修改内容 | 范围 |
|---|---|---|
| `topogym/assets/geometry/rope_threading.py` | 布局选择、稳定环 ID、环数／孔径及报告参数化 | 必改 |
| `topogym/tasks/rope_threading/common.py` | 接入所选布局，声明对应实体和目标环元数据 | 必改；不在本轮重写 terminal |
| `topogym/tasks/rope_threading/rope_threading_easy.py` | 填两环代表 | 必改 |
| `topogym/tasks/rope_threading/rope_threading_hard.py` | 填小孔三环代表 | 必改 |
| `topogym/tasks/slotted_post_ring/slotted_post_ring_easy.py` | 填验证后的大环尺寸 | 必改 |
| `topogym/tasks/slotted_post_ring/slotted_post_ring_medium.py` | 填验证后的中环尺寸 | 必改 |
| `topogym/assets/geometry/slotted_post_ring.py` | 补尺寸窗口／路径检查所需几何报告；现有生成能力足够则不改 | 条件修改 |
| `topogym/tasks/slotted_post_ring/common.py` | 仅在现有 geometry 参数透传或任务元数据不够时补充 | 条件修改 |
| `topogym/assets/geometry/orbits.py` | N 环、N+1 柱构造与检查，去掉四环固定假设 | 必改 |
| `topogym/assets/geometry/orbits_initial.py` | 两／三环工作绳初态和绳长规则 | 必改 |
| `topogym/tasks/orbits/common.py` | 接入环数对应初态 profile／元数据 | 必改 |
| `topogym/tasks/orbits/orbits_easy.py` | 填两环代表 | 必改 |
| `topogym/tasks/orbits/orbits_medium.py` | 填三环代表 | 必改 |
| `topogym/assets/geometry/blanket_flatten.py` | 复用平坦材料绑定，收敛重复 gathered_target 入口，保持旧折叠构造可复现 | 必改 |
| `topogym/assets/geometry/blanket_gathered.py` | 共用聚褶／扭转目标、参数检查及准备所需几何输出 | 拟修改；已有函数够用时只调整调用方 |
| `topogym/tasks/blanket_flatten/common.py` | 声明准备参数、保存材料基准、接入准备结束后的初态数据 | 必改 |
| `topogym/tasks/blanket_flatten/blanket_flatten_easy.py` | 切为低扭转聚褶及新 revision | 新准备机制通过后修改 |
| `topogym/tasks/blanket_flatten/blanket_flatten_medium.py` | 切为中扭转聚褶及新 revision | 新准备机制通过后修改 |
| `topogym/tasks/blanket_flatten/blanket_flatten_hard.py` | 接入高扭转聚褶，替换准备占位 | 新准备机制通过后修改 |

Rope medium、Slotted hard、Orbits hard 保持参数与实例合同，作为回归对象；如果公共实现修复迫使其身份改变，单独列出原因和修订，不默认改动这些文件。

### 7.2 公共模块与资源

| 文件／路径 | 修改内容 | 范围 |
|---|---|---|
| `topogym/config/variation_records.py` | 档位 family、revision、状态与原因 | 必改，逐档达到接入要求后更新 |
| `topogym/tasks/base.py` | 为 TaskSpec 增加声明式初态准备合同（具体字段在实施前与接口方确定） | Blanket 共享接口拟改 |
| `topogym/world/genesis_world.py` | 由 World 执行准备物理推进、调用后端适配 | Blanket 共享接口拟改 |
| `topogym/simulator/env.py` | reset 中等待准备成功、初始化 Task、保存首状态和返回初始观测 | Blanket 共享接口拟改，仅增量修改 reset 相关路径 |
| `topogym/world/physics/cloth_preparation.py` | 拟新增：布料准备速度控制、状态检查及控制撤除，封装后端细节 | 名称暂定；先确认现有 World 是否已有可复用接口 |
| `topogym/assets/resources/variations/<task>/…` | 冻结新布局／准备参数及来源 | 按需新增；不为可直接声明的少量标量强制建 JSON |
| `topogym/assets/resources/catalog.json` | 登记新增资源路径、SHA-256 和来源 | 新增随包资源时更新 |
| `topogym/tasks/legacy/manifest.json`、`README.md`、对应任务归档文件 | 保存被替换的 Blanket 代表；三档完成后整理剩余表外入口 | 后续归档阶段 |

`simulator/history.py`、`simulator/config.py`、`world/physics/pbd.py` **不列为默认必改**；只有初态准备／恢复检查证明现有能力不足时，才列出具体缺口并扩展。既有 segment、action 编码、Harbor runner 和机器人控制不因本计划自动重写；`planning/` 完整 oracle 迁移另按其计划执行。

### 7.3 验收与文档

| 文件 | 修改／新增内容 |
|---|---|
| `tests/unit/test_task_variations.py` | 更新占位、家族、参数冻结与别名断言 |
| `tests/unit/test_task_definitions.py` | 验证新增 setting 实体及资产合同 |
| `tests/unit/test_scene_presets.py` | 已有主档回归及默认场景的实际变化 |
| `tests/unit/test_setting_geometries.py`（拟新增） | N 环计数、非法尺寸、目标 ID、初态几何正反例 |
| `tests/integration/test_cloth_preparation.py`（拟新增） | 真实准备、控制撤除、首观测一致性及恢复；失败完整留证 |
| `scripts/check_variation_assets.py`、`scripts/test_variation_runtime.py` | 优先原样复用；仅在无法选新增档位或记录准备证据时增补 |
| `docs/develop/tasks/variation_deployment_implementation_20260925_zh.md` | 实际落位、状态和证据链接 |
| 本计划、`planner_oracle_inventory_20260925_zh.md` 及相关任务说明 | 同步最终设计和历史证据适用范围 |

不会先创建一批空测试／适配文件；新增文件只在对应实现阶段需要时落地，测试应验证实际合同和退化风险。

## 8. PBD 视觉绑定调查与平稳落桌初态（用户后续补充）

2026-09-26 补充：用户进一步要求正式 reset 不再重复掉落或运动准备。已将实施方案细化为[Blanket 冻结初态工程计划](blanket_frozen_initialization_plan_20260926_zh.md)，其中逐文件列明跨重建状态包、离线准备和首状态恢复接口。本节保留机制调查与备选依据；正式部署顺序以新计划为准，受控准备放到离线制作阶段，在线不通过额外静置掩盖恢复不完整。

### 8.1 当前结论与证据边界

优先采用 **展开状态建立材料与视觉绑定 → 保持绑定不变地形成褶叠／扭转 → 低速放置到桌面 → 撤除控制并通过静置验收 → 交付初始 RGB**。这将安全绑定所需的出生几何与 agent 看到的紧密布团分开，不再要求可见初态保留大层距，也不依赖高处自由落体来压实布料。这里沿用任务桌面，未改为实验室地板。

本节最初完成历史资料与当前源码调查、一个小型 NumPy 绑定反例。后续第 9 节已新增实际 Genesis 出生绑定读取验证（CPU、无 RGB、零物理步），仍**没有完成布料塑形／落桌物理、Nyx 验收或后端绑定算法修复**。以下路线在当前标准框架是否通过仍需实际验收。

| 来源 | 核对到的事实 | 对方案的影响 |
|---|---|---|
| [legacy cloth_unroll §3／§4／§9.12](../../../legacy/docs/develop/tasks/cloth_unroll_zh.md) | 旧记录的层距 4.5 mm、粒子实测间距约 3.7 mm，visual 有撕裂感；粒子诊断未见对应物理破坏。扩大出生层距到 14 mm 后改善；随后探索保持出生绑定、让卷层压实 | 支持“出生误绑”诊断，不意味着每次看见撕裂都只是渲染问题 |
| 本地 `ParticleEntity._add_vverts_to_solver` | 按出生时三维欧氏距离选支撑粒子，再以伪逆求仿射权重；选择过程没有布料材料坐标／同层约束 | 紧邻但材料上相距很远的两层可能混选；这与夹爪 assist 附着是两种不同的绑定 |
| 本地 `PBDSolver.update_render_fields` 对应视觉更新内核 | 可视顶点由固定 support 表对当前粒子位置加权重建 | 后续压紧不会因为距离变近就自动重选近邻；但物理自穿透、强形变下的插值误差仍可能出现 |
| 当前 [Blanket.bind](../../../topogym/tasks/blanket_flatten/common.py) | 检查粒子到出生面的材料坐标投影，再构建诊断三角网；没有读取实际 visual support 表做跨层审计 | 材料坐标检查不能替代视觉绑定检查，需回收完整审计 |
| 当前 [Env.reset](../../../topogym/simulator/env.py) | bind 后仅推进配置的 reset_physics_steps，再建立 episode 初状态 | 固定等待不等于通过布料静置与形态验收，需加入准备完成合同 |
| 历史 [diagnostics.binding_audit](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/diagnostics.py) 与 [scene.py](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/scene.py) | 已审计实际 support 索引、权重、材料距离、出生重建及假想展平误差；受控构造分支已有平铺绑定 | 可回收审计计算，后端私有字段读取应封装在适配层 |
| [gathered_robot_v9/binding_report.json](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/assets/binding_report.json) | 18406 粒子、4636 视觉顶点、12 supports；非局部支撑计数 0，最大材料距离 12 mm、当时阈值 16 mm | 证明历史某个绑定配置通过，不等于该版本完整准备／机器人执行成功，也不是当前引擎验收 |

本地引擎坐标为 `.venv-gs121-nyx/lib/python3.11/site-packages/genesis/engine/entities/particle_entity.py`、`pbd_entity.py` 与 `engine/solvers/pbd_solver.py`，哈希保存在[本轮核对报告](../../../runs/test_results/pbd_binding_review_20260925_01/report.json)。调查以本地文件为准；尝试读取上游 GitHub 页面未获得源码正文，不将其作为本地版本行为证据。

两项历史结论不能原样扩大使用：

- “出生层距超过约 3 倍粒距”是旧案例的工程经验，不是充分保证。支撑邻居数、重网格化、折角、边界和局部密度都会影响结果；旧 Blanket 也曾在面板间距足够时，因尖折线两侧材料上过远的混选而拒绝绑定。
- legacy 文档曾称 bending_compliance 不起作用；当前本地源码存在 bending 参数赋值、求解内核和调用，不能据旧记录宣称当前抗弯恒为零，也不能仅见代码就认为其数值行为已验证。后续只做受控参数敏感性检查，不先用加刚度来掩盖绑定问题。

### 8.2 本轮小型反例：出生位置准确并不保证绑定正确

用两块材料上不同的规则网格，复现本地“最近 12 支撑＋伪逆仿射权重”的 NumPy 计算。粒距 4 mm，25 个底层视觉顶点；绑定后仅对另一层做独立刚体转动和平移，检查底层视觉是否错误移动。

| 出生层距 | 跨层 support 条目数（共 300 条） | 出生重建最大误差 | 另一层运动后底层视觉偏差 |
|---|---:|---:|---:|
| 1 mm | 150 | 数值舍入量级 | 约 0.380 mm |
| 4 mm | 125 | 数值舍入量级 | 约 0.630 mm |
| 8／12／16 mm | 0 | 数值舍入量级 | 数值舍入量级 |

这只是近邻混选和错误形变耦合的数值反例，不是连续布料运动或完整视觉撕裂复现。该规则网格在 2 倍间距不混选，不代表实际折叠布料也能用这个阈值。初态外观正确、权重和为 1、重建误差小均不足以发现误绑，必须检查材料局部性与后续形变。脚本和结果见[调查产物](../../../runs/test_results/pbd_binding_review_20260925_01/README.md)。

### 8.3 优先实施路线：绑定一次，受控放置，静置后交付

1. **平坦材料建模。** 使用 generate_flat_binding 和实际 remesh 后的粒子建立材料 UV、物理约束及 visual support。粒子索引不能假定等于输入 OBJ 顶点索引。出生高度只服务于安全构造，不作为 agent 初态。
2. **立即审计并冻结身份。** 支撑必须属于同一布料，且在材料 UV／网格图上局部；记录实际粒距分布、支撑数、材料距离、重建误差、权重有限性和权重和、权重绝对值和及放大风险。当前伪逆权重允许负值，不能仅因权重为负就拒绝；平坦面矩阵秩为 2 也属正常，不能要求满三维秩。阈值由控制网格与实际采样联合标定。
3. **形变审计。** 使用同一支撑表做离线假想展平与已知材料弯折重建对照；它不修改真实粒子、不算物理解法。记录材料边、visual 边的长度变化，区分物理材料拉伸与单独视觉异常。
4. **物理塑形与低速放置。** 在桌面净空内分阶段折叠／扭转，靠近桌面后降低目标速度，逐步将支撑交给桌面接触。准备速度控制不得强行顶穿桌面或压缩自接触层。目标受阻时失败或回退准备阶段，不直接写穿透位置、不清零应变。
5. **撤除全部准备控制。** 正常重力下进行自由静置；无虚拟手、隐藏 pin、临时托板、额外关闭碰撞或维持扭转的控制残留。避免批量用 fix_particles_to_link 来摆布料：legacy unroll 曾记录被固定粒子冻结在桌下的另一类问题。
6. **条件验收，不只计时。** 检查材料完整性、自接触／桌面穿透、平均及尾部分位速度、最大位移窗口、桌面范围、覆盖与高度、未自动成功、三档残留扭转差异。给出最短观察时间和最长超时；所有阈值写入配置与报告，不能为通过高扭转档单独放宽。视觉未破裂也不等于物理合法。
7. **原子交付初态。** 通过后再建立 episode 首状态、首 RGB 和操作句柄；准备期间仍走唯一 World 物理路径，单独记录阶段／tick。失败不发布半准备的 episode，不自动换 seed。对 agent 而言，从第一帧起布料就已稳定落桌。

注意：冻结绑定表只是避免重新近邻选择；它不能保证任意尖折／大曲率下的线性视觉插值都足够好。必须持续比较实际粒子、材料三角网与 Nyx 渲染使用的视觉网格，必要时进一步提高材料局部插值质量。

### 8.4 加快 reset 的两种复用途径

**A. 经验证的完整初态 checkpoint。** 对固定代表／seed 离线完成上述准备，保存准备结束的完整物理状态、材料 rest、拓扑、support／weights、引擎与网格哈希及准备来源。新建平坦材料、核对身份后，通过标准 World 恢复受支持的状态，并做无控制复验，再作为新 episode 初态。不能通过操作方 rewind 跨 episode 导入；静态映射是否进入 checkpoint 也要实测，不能假定 history 已完整覆盖外部资产身份。

**B. 记录形状作为新初态，随后重新静置。** 历史 [initial_state.restore_selected_shape](../../../runs/environment_bootstrap/blanket_flatten/gathered_robot_v9/source_snapshot/initial_state.py) 已有这种逻辑：比较 faces／material_uv／supports／weights，保持 rest 不变，再初始化粒子位置和零速度。它明确标为 `fresh_physics_from_recorded_shape_with_zero_velocity`，并非原轨迹动力学续接。

B 可作为工程备选，不应被误认成“加载扭曲 OBJ 并重建 rest”。若采用，位置初始化仅限管理方、首次交付前一次，清理或重建一致的接触／约束缓存，记录写入次数并经正常重力静置；不能冒充精确 checkpoint 恢复，不能在 agent 执行中使用。缓存方案都必须拒绝网格／版本不匹配，不能对紧密多层位置重新做空间最近邻绑定。

先让 A 的在线准备路线成立，再评估缓存收益。缓存不掩盖坏初态，也不允许多个 seed 悄悄加载同一实例却声称多样化。

### 8.5 仅在优先路线不足时修改绑定算法

若平坦绑定后仍有明显视觉插值问题，再研究材料空间／网格邻接约束的支撑选择，或材料三角形内的重心插值；粒子材料坐标必须来自平坦状态的可靠映射。按 UV 区分材料远近，不能在已经紧密折叠的三维位置上猜哪一层属于谁。

该方案涉及 Genesis 创建 visual supports 的时机及 Nyx 消费网格的路径，需要独立后端适配／补丁与版本锁定，不能只修改 TopoGym 内一份诊断映射就宣称修复渲染。当前不建议直接改 site-packages、动态 monkey-patch 或依赖重启后消失的内存补丁。

不优先采用的替代做法：持续增大层距会破坏紧密初态；只减小粒径可能增加开销且仍混选；只减小 support 数可能放大噪声；把渲染切成粒子可以诊断但不能替代正式 RGB；在紧密姿态下重新 remesh／绑定可能再次跨层或改变材料身份。

### 8.6 验证矩阵与新增文件范围

验证顺序：

| 检查 | 正反对照 | 通过依据 |
|---|---|---|
| 出生绑定 | 平铺、开口折叠、紧密层叠与尖折负例 | 实际 support 表的材料局部性；不能只验出生重建 |
| 后续变形 | 正确绑定后压紧／展开；错误绑定负例做同类变形 | 物理边与视觉边指标分离，错误映射被捕获 |
| 放置方式 | 当前自由落体基准；低速受控放置后撤控 | 静置耗时、位移、应变、穿透与目标形态；不是只比较视频是否平稳 |
| 三档 | 固定其他参数的低／中／高扭转，多 seed | 稳定后形态仍可区分，均未提前 solved |
| 复用／恢复 | 在线准备、完整 checkpoint、明确新初态重置备选 | 来源分类正确、材料／绑定身份一致、正常重力续跑有效 |
| 渲染 | 同一状态的粒子／材料网格诊断、实际 visual 网格与 Nyx RGB | 证明异常出在哪一层；标准视频仍走 Nyx＋共享录制 |

第 7 节文件清单增补：

- `topogym/world/physics/pbd_binding.py`（拟新增）：版本受控地读取实际粒子／视觉支撑映射并输出审计数据，隔离私有后端访问；是否合并进已有 PBD 适配文件在实施时决定。
- `topogym/evaluation/cloth_binding.py`（已新增）：纯数组的材料局部性与视觉重建指标；不在指标层直接访问 Genesis。实际实施选用独立文件，避免扩大共享 `cloth_metrics.py` 的修改面。
- `topogym/tasks/blanket_flatten/common.py`：消费审计结果、保存材料身份并拒绝无效出生；不承担 scene.step 或读取求解器私有字段。
- `topogym/world/physics/cloth_preparation.py`（前述拟新增）、`world/genesis_world.py`、`simulator/env.py`：加入低速放置、撤控、静置门槛及首状态交付；按共享接口边界增量衔接。
- `tests/unit/test_pbd_binding_metrics.py`（拟新增）：正常平面与跨层负例、重建误差小但局部性错误的反例。
- `tests/integration/test_cloth_preparation.py`：增加真实 remesh/support 审计、放置与 checkpoint／新初态重置对照；输出同步 Nyx 视频与逐 tick 状态。

本阶段先恢复审计和证明稳定初态交付，再切 Blanket 三档；不要求先重写整个 PBD 引擎，也不沿用旧“高处释放才不会撕裂”的初始化限制。

## 9. 并行边界核对与第一批实施结果

### 9.1 结论：部分独立，不能整份计划同时落位

已发现实际代码重叠。terminal 相关改动涉及 `tasks/base.py`、Rope／Slotted／Orbits 的 `common.py` 和几何评估工具；Blanket 的首状态交付还要接入 `simulator/env.py` 与 `world/genesis_world.py`。本轮开始时 Rope 判据写死三环，不能把两环场景直接交给它。

本轮只写了下表 7 个源码／测试文件，以及本文和模块说明；没有修改 shared common、base、Env、World、segment、registry 或 planner。期间另一会话已把 Rope 判据改为 `layout.required_crossings()`，这是共享工作区的后续变更，不能归为本轮修改，也不再作为“仍写死三环”的阻塞理由。已另存兼容快照验证衔接。

| 本轮文件 | 实际完成内容 |
|---|---|
| `assets/geometry/rope_threading.py` | 有序 `ring_ids`、`ring_inner_radius_m`、随孔径移动支架与底座、实际孔径／目标顺序报告、`required_crossings()`；旋转底座间隙在局部坐标计算；拒绝旧输出目录残留已删环资产 |
| `assets/geometry/orbits.py` | N=2/3/4、N+1 柱、实际环数的连接／孔洞／绕柱检查；四环保留旧报告兼容字段 |
| `assets/geometry/orbits_initial.py` | 两／三环必须显式提供绳长；四环旧余绳函数拒绝误用于减环场景；保持四环原默认输出 |
| `world/physics/pbd_binding.py` | `read_birth_visual_binding(entity)` 只读获取真实出生 XYZ、support 索引及权重，转换为实体局部索引，检查归属／形状／有限性并复制保存身份 |
| `evaluation/cloth_binding.py` | `audit_visual_binding(...)` 检查材料 UV 局部性、位置／假想展平重建、权重和与放大量；允许合法负权重与平面秩；材料坐标由调用方可靠映射提供 |
| `tests/unit/test_pbd_binding_metrics.py` | 正常平面、负权重、出生重建准确但跨层误绑、跨实体、异常缓冲区及只读副本测试 |
| `tests/unit/test_setting_candidate_geometry.py` | 删环实体、目标顺序、缩孔后支架连接、旋转一致性、非法参数、Orbits 绕最后一柱及显式绳长测试 |

表中路径前五项相对 `topogym/`，测试相对仓库根目录。后端适配只适用于已检查的 Genesis PBD 缓冲区形状；它不重新选择 supports、不修补引擎、不推进物理，不经 interaction 向普通 agent 开放。材料 UV 必须匹配实际 remesh 后的粒子／视觉顶点顺序，不能直接照搬输入 OBJ 顶点编号，也不能从紧密折叠 XYZ 猜材料归属。

### 9.2 已取得的证据

- 固定源码快照第一轮 **46 项通过**；其他会话接上 Rope 动态顺序后，第二份固定兼容快照 **47 项通过**。包括新测试、变体注册合同和 Rope／Orbits／Slotted 的已有 terminal 单元测试；不代表完整终态物理资格。
- Rope 原默认 OBJ／GLB／MTL／NPY 资产哈希全部与修改前一致。Orbits 1.0／0.75／0.85 尺度的默认网格顶点、面、绳中心线，以及原四环自然余绳／木柄输出哈希一致。报告新增字段不要求与旧 JSON 字节相同。
- Rope 两环候选保留 `R1- → R2+`，内孔直径 138 mm；小孔三环候选直径 100 mm，保留三环原中心和法向。均通过静态初态检查、初始穿环列表为空；尚未验证连续机器人路径。
- Orbits 两／三／四环均在 75% 尺度、木柄 x=0.60 m 下通过静态孔洞、固定连接、绳—实体间隙与绕最后一柱检查。三者明确输入同一参考绳长 1.697880695 m；与现有 hard 一样按 1 mm 重采样后，实际折线长分别为 1.697270996／1.697274104／1.697267627 m，报告保留这项采样差异。这不是回穿路线或难度递增证明。
- Slotted 没有改生产代码。主半径 61／62／63／64 mm（内孔直径 102／104／106／108 mm）均通过现有静态检查；端盘阻挡直径余量依次为 8／6／4／2 mm。顶部连续解脱路线和倾角容差尚未验证，不能据这四个数直接定 easy／medium。
- 真实 Genesis 1.2.1 出生绑定检查经 `GenesisWorld.add_entities/build` 构建两块小平面布：每块 124 个实际粒子、81 个视觉顶点、每顶点 12 supports；第二块具有非零全局偏移。两块均无跨实体／材料非局部支撑，位置重建最大误差小于 1.3e-16 m，读取前后引擎支撑表完全一致。这次显式使用 **CPU、无 RGB、零物理步**，没有稳定性、准备或渲染验收含义。32 mm 材料局部阈值只用于该小平面 fixture，不作为所有 Blanket 初态的合格线。

完整脚本、配置、后端源码哈希、两份固定源码快照、报告及原始数组见[本轮证据](../../../runs/test_results/setting_independent_20260925_01/README.md)。本轮没有生成 solve／落桌视频，也没有宣称 PBD 视觉撕裂已修复。

### 9.3 尚待衔接与下一批工作

1. **Rope：** 动态顺序已由另一会话接入。接下来用冻结候选完成路线／接触与可达性检查，再填 easy/hard 和 revision；本轮仍保留占位。
2. **Orbits：** 两／三环 profile 需要在 common 明确透传绳长、木柄位置与环数；先验证核心回穿和短路线，再冻结参数。当前 `video_solution_v2` 仍无显式绳长，不能直接把 N 改成 2/3 使用；新 guard 会清楚报错。
3. **Slotted：** 用完整环—柱—绳—珠—端盘场景验证顶部路径与容差。若候选窗口不能分档，应记录失败原因再改设计。
4. **Blanket：** 在独立准备模块中消费上述真实绑定快照与可靠材料映射；补物理／视觉边应变对照、低速放置、撤控和静置验收。随后与接口会话增量接好 TaskSpec／World／Env 的原子初态交付，最后切三档。当前审计器只是先抓住误绑，尚未替代初始化流程。

因此本轮是阶段 B 的独立工具与静态预检交付。32 已接入、6 planned、1 blocked 的主档计数未因本轮更改；7 个空档补齐和 Blanket 两档改版仍未完成。后续不需要重写 Harbor／segment／action 协议，但 Blanket 必须按共享 reset 生命周期接入，不能另起模拟循环来避开协作。
