# 2026-09-05 进度：ring_transfer GPU 链

详细记录 `../develop/tasks/ring_transfer_zh.md` §7.4；追踪表 `weekly_tracker_zh.md` §1 第 10 行。

**一句话。** 角点子集 8/8、seed 0–9 oracle 10/10、`lift_only` 对照重做后三格判失败，第 10 步的六项交付齐了，追踪表第 10 行记「完成（09-05）」。

| 项 | 内容 |
|---|---|
| 角点首跑 4 / 8（01:13） | A 出发四格 PASS；B 出发四格在建场景前退出：`derive_task_cfg` 把 `goal.instruction` 改写成带空格的句子，角点 sweep 脚本按空格切 Hydra 覆盖 → `Error parsing override 'the'` |
| 处置 | yaml 指令改为模板 `… post {start} onto post {goal}.`，`RingTransferLayout.instruction()` 填柱名，派生只写 `goal.on_post`；demo plan 行打印拼好的指令。规则记入 §7.1：派生只写标量、无空格的叶子。离线两道门复跑 PASS |
| 角点复跑（10:48） | B 出发四格 4 / 4，`runs/ring_transfer_corners/20260905_b_corners/`；合计 8 / 8 |
| seed 0–9（09-04 22:30 起） | 首跑 oracle 9 / 10、visual 9 / 10，缺的两格都是首步 libuipc `cudaErrorInvalidDevice`（GPU 争用）；GPU 空闲时复跑两格都过（`…/20260905_rerun/`，oracle seed 0 一格 136 s）→ oracle **10 / 10**、visual 10 / 10 |
| 最紧物理余量 | 最粗柱：角点 c189 approach U 宽 70.9 对需要 64、seed 8 为 72 对 54——`post_shape.radius` 上界 0.022 的实证，余量 7–18 mm |
| `lift_only` 对照 | 首版 10/10 判失败但终态是原封不动的出生态（off 段只抬 2 cm 提不脱环），不算对照。重做：新增 `lift_only_phase`（carry 同款捏取与反应式抬离，搬到两柱中点放下；`carry_phase` / `off_phase` 不动），固定布局 / seed 3 / seed 0 三格判失败、绕数 A 0 B 0、目标柱顶未越过（`runs/ring_transfer_variation/20260905_lift_only/`） |

待办：判据不检查松手后环相对挡头的高度（环平躺在挡头顶面上会判成功），要补对照或高度条件。

## bar_through_hole：夹空门 c000 目视核对（11:32）

09-04 的 c000 斜视录像里合爪被面板挡住。同一格开 `run.verbose=true` 加俯视 / 手腕 / 斜视三机位复跑
（`runs/bar_through_hole_grasp_video/oracle_c000_multi_*.mp4`、`oracle_c000_verbose.log`）：手腕视角看到两指同时贴到杆两侧、杆在正中；
`approach` → `lift_test` 杆心 xy 不动、z 升 0.0426；`finger_qpos=0.0090` 即两指开度 18 mm 等于杆径。离门 0.0086 最近的这一格确认是「指垫压在杆上」。
写回 `bar_through_hole_zh.md` §5.3。夹空侧仍未实测。

## cloth_unpleat 变体部署：离线六项 + GPU 基准（12:00 起）

详细记录 `../develop/tasks/cloth_unpleat_zh.md`；追踪表 §1 第 9 行。计划文件里三个待拍板项按推荐执行：先做 cloth_unpleat、加 `pull_side` 镜像轴、可达门 0.665 作假设。

| 项 | 内容 |
|---|---|
| 场景与轴 | 布带沿 y 铺、中段一道刀褶，夹爪拉自由端。褶宽 Cat{0.035, 0.030, 0.024}（单调裕度轴）；`pull_side` ±1 镜像（防捷径轴：自由端在 +y 还是 −y 端，剖面对 y 取反，底座与工作区关于 y = 0 对称）；顶缘高度 / 横向位置 / 行程倍数三条连续轴；捏取点内缩量、纵向位置抽归一化分数派生 |
| 两处非独立区间 | 内缩量上限 = 半跨度 − 褶宽 − 2 × 附着盘半径（褶宽 0.035 + 顶缘 0.028 时 0.0164，独立抽 0.018 该角点净空 34.4 mm < 36）；纵向位置上端 = 可达盘弦长 − 终点偏移（center_x 0.070 + 最长行程时 +0.0058，独立抽 +0.030 可达读数 0.672 > 0.665）。两者都按「抽 frac 再派生」构造式满足 |
| 执行链修正 | `observe()` 抓取高度取的是整条布带中线的最高粒子（躺平后的褶顶，桌面 + 9.5 mm），改为抓取点附着半径内的最高粒子。GPU 复跑：观测 z 从设计点上方 7.15 mm 变为 0.23 mm，`arm_pos_err_mm` 8.6 → 1.9，`attach_error_mm` 0.45 → 0.57 |
| 首版一处类型错误 | 派生值是 numpy float64，OmegaConf 拒收 → 1000 seed「拒绝」33 个全是这个；转 Python float 后拒绝率 0。正好是可达盘封顶生效的 33 个 seed |
| 离线门 | `check_cloth_unpleat_geometry.py`（系统 python numpy 1.21 与 venv numpy 2.4 都过）：192 角点七行全过、镜像七行相等、三负例被拒；`check_variant_rng.py` cloth_unpleat 段：三档 350/350/300、两侧 477/523、拒绝率 0.000；`check_variant_corners.py`：192/192 可行、Hydra compose 一致；`check_demo_configs.py`、`check_configs_compose.py` 过 |
| GPU 基准复跑（`runs/cloth_unpleat_variation/20260905_baseline/`） | 固定布局 unfold：`unpleated=True`，单层率 0.945、回收比 **0.883**（08-23 CPU 后端 1.000）、跨度 252.8 mm、整带平移 1.66 mm、跟随误差 1.2 mm；**一格 19 s**（含建场景），比预期便宜得多，所以角点 192 格全跑 |
| 在跑 | `cloth_unpleat_variation_sweep.sh oracle shove`（seed 0–9 各两格，`runs/cloth_unpleat_variation/20260905_seeds/`）→ `variant_corners_sweep.sh cloth_unpleat oracle`（192 格，`runs/cloth_unpleat_corners/20260905_all/`） |

回收比 1.000 → 0.883 的差别待解释：两次抓取高度不同（旧版指垫比布面高 7 mm、绑定的 64 个粒子相同）、后端不同（CPU / GPU）。seed 0–9 的分布出来后看它是否随褶宽单调。

**GPU 结果（13:00–15:30）**，细节 `cloth_unpleat_zh.md` §5。

| 项 | 内容 |
|---|---|
| seed 0–9 | oracle **10/10**（镜像 6 格），shove 10/10 判失败（两条门都拦）；抓取点观测 z 全部 = 桌面 + 2 mm，`arm_pos_err_mm` 1.9–2.2；pull_scale ≤ 1.02 的格回收比 0.88–0.91，≥ 1.06 的格 1.00–1.05；三格整带平移 23–29 mm |
| 角点 192 格首跑 | **170 / 192**，66 min。可达门取等的 c188 / c190 通过（0.665 假设成立） |
| 失败第一类（10 格） | 起始态守卫 `three_layer_cells ≥ 12` 误判：同一物理褶（峰高、铺展比相同）平移 60 mm = 7.5 格后三层格数 24 → 6，是世界原点锚定的 8 mm 占用网格的相位效应。修判定器：`layer_report` / `occupied_cells` 加 `origin`，unpleat 判定器把网格锚在静置点云的最小角；三个 cloth 离线门过；十格复跑 **10/10**。但 side −1 的格读数恰为 12，相位依赖只是从「布带位置」换成「三层带离锚点角的距离」，仍不稳 |
| 失败第二类（12 格） | pull_scale 0.98 + 顶缘 0.016 的扁褶：回收比 0.78–0.85 < 0.85。170 格的「行程 − 回收比 × 存料」显示扁褶（顶缘 / 褶宽 ≤ 0.8）与褶宽 0.035 一律留 8–10 mm 残褶，陡褶（≥ 0.93）全部放出。oracle 行程公式 `存料 × pull_scale` 的隐含假设是「存料全部能放出」 |
| 只记录的观察 | 62 格整带平移 25–37 mm 仍判成功，全是褶宽 0.030 / 0.035；褶宽 0.024 的 64 格 ≤ 5 mm。同配置复跑回收比抖动 ±0.05 |
| 三项决定（下午） | 闭环补拉；整带平移不设门，褶拉平即成功；起始态守卫只看铺开长度是否短于材料全长，三层格数撤掉 |
| 闭环补拉实现 | `PullExtender`（planner）+ `ClothLinkAttachDragPrimitive.run(extend=)`：拉完保持到位后量铺开长度，差多少补多少，上限 1.15 × 存料。两个实测细节：拉着时比松手后长 5 mm（弹性回弹，目标加 `pull_extend_recoil_m`）；最小补拉量 4 mm 会跳过 3.9 mm 的差额，改 2 mm。基准格回收比 0.885 → 1.026 |
| 全量复跑（闭环 + 新守卫） | seed 0–9 oracle **10/10**、shove 10/10 判失败；角点 **192/192**（补拉触发 56 格，无一碰上限；回收比 0.874–1.054，8 格 < 0.90）；一格 14–27 s |
| 收口 | cloth_unpleat 六项齐，追踪表第 9 行「完成（09-05）」。另一会话并行做 cloth_unroll，共享文件（`check_variant_rng.py` / `check_variant_corners.py` / `variant_corners_sweep.sh` / 追踪表）双方都用定点替换，条目互不覆盖 |

## cloth_unroll 变体部署：离线五项（14:30–15:10）

详细记录 `../develop/tasks/cloth_unroll_zh.md` §9；追踪表 §1 第 9 行、§2 第 0 / 1 级。GPU 不跑，留给后续。

| 项 | 内容 |
|---|---|
| 两个决定 | 防捷径轴用 `pull_side` 镜像（支架在 −y 侧向 +y 拖，或镜像到 +y 侧向 −y 拖），不用计划文档的 `material_axis` Cat{x, y}：沿 +x 拖终点 x ≈ +0.32 出工作区，朝机械臂拖的可达未实测。立柱 `post_height` 0.075 → 0.090：杆高 0.053 + 最粗的卷半径 0.031 = 0.084 会高过 0.075 |
| 离线算出的两个事实 | 计划文档的 turns [1.0, 1.75] 在 0.280 m 布上不成立：1.75 圈任何层距平铺段为负，1.5 圈只允许层距 ≤ 0.0158（杆高 0.053）→ 圈数 Cat{1.0, 1.25, 1.5}，层距由 frac 在「平铺段五行都成立的最大层距」窗口里二分派生。1 圈松卷设计铺展比 0.60–0.66 > demo 起始守卫 0.50 → 守卫阈值派生为设计铺展比 + 0.11（基准 0.502） |
| 轴 | `pull_side` ±1、圈数三档、杆高 U[0.037, 0.053]、center_x U[0.010, 0.050]（可达盘定上限）、`pitch_frac` / `center_y_frac` 派生、守卫派生；96 角点 |
| 十行 `checks()` | 平铺段 ≥ 4 格、附着盘离垂落段、抓取点离梁心 ≥ 57 mm（规划器常量 `SHOVE_BAR_CLEARANCE`）、卷底离桌、立柱高过卷顶、层距 ≥ 0.014、出生足迹与终点在工作区、可达 0.665、行程 ≤ stroke_m、出生铺展比 ≤ 守卫 |
| 镜像实现 | 剖面与 landmarks 保持无符号，符号落在 `_plan_point` / `pull_direction` / `observe` / 网格扫掠四处；规划器与判定器不改 |
| 离线门 | `check_cloth_unroll_geometry.py` 原三段读数不变 + 变体包络段（96 角点十行全过、镜像十行相等、四负例、出生态三层格最少 64）；`check_variant_rng.py` cloth_unroll 段拒绝率 0.000（三档 363/326/311、两侧 481/519、最长行程 263 mm、层距在 311 个 seed 被封顶）；`check_variant_corners.py` 96/96、Hydra compose 一致；compose / demo 配置门过；CPU 建场景固定 / seed 3 / seed 5（镜像，支架 y +0.123、向 −y 拖）三格十行 ok |
| 未跑 | `cloth_unroll_variation_sweep.sh`、`variant_corners_sweep.sh cloth_unroll` 已写未跑。GPU 要看：1 圈松卷静置后是否仍过守卫；镜像与 center_x 0.050 的可达 0.665；立柱 0.090 有无新接触 |

**cloth_unroll GPU 结果（16:21–17:51，用户跑）**，细节 `cloth_unroll_zh.md` §9.6。

| 项 | 内容 |
|---|---|
| seed 0–9 | oracle **10/10**（镜像 3 格），shove 10/10 判失败（回收比 −0.26 … +0.14）；`on_bar` 全 0、穿透 0、`arm_pos_err_mm` 1.6–1.9；一格 42–55 s（含录像） |
| 起始守卫 | 派生阈值全部放行：静置后铺展比比设计高 0.01–0.08，0.11 的余量剩 0.03–0.10；1 圈四格静置后 0.65，固定 0.50 会全部中止 |
| 角点 96 格 | **96/96**，一格 18–36 s、共 40 min；可达 0.665 取等的角点全过、位置误差 ≤ 1.9 mm；立柱 0.090 无异常 |
| 余量不足 | 1 圈 + 层距 0.018 + 杆高 0.037 的四个角点回收比 0.56–0.58（门 0.50）；c042 等三格单层率 0.76–0.77（门 0.70）。余量 0.06 < ±0.09 摆幅。末态留 43–111 个两层格：oracle 行程 = 铺平位移 × 1.30 的固定多走量在 1 圈只有 38 mm，与 cloth_unpleat 同一条「存料全能放出」假设，那边已改闭环补拉 |
| 只记录 | 镜像 48 格 `arm_tilt_deg` 34–43°（+1 侧 0.8°）：`finger_axis: across` 的指令偏航角向 −y 时反 180°，手腕转不到位，位置误差不变；cloth_unpleat 镜像格 28–34° 同现象 |

---

## rope_winding 变体部署（第 6 步，本会话，09-05 上午起、GPU 晚间跑完）

详细记录 `../develop/physics/rope_winding/rope_winding_zh.md` §9；本节只汇总。

**一句话。** 六项交付齐全：离线 1000 seed 首抽拒绝率 0、1536 角点全过；GPU 固定布局复跑通过、seed 0–9 oracle **10/10**、visual 10/10、wrong_way 3/3 判失败、角点子集 **10/10**。
三圈与顺时针都是第一次在 GPU 上跑通。

| 决定 | 内容 |
|---|---|
| 出生弧张角 | 由 `derive_task_cfg` 按松弛带中点 10% 反解（绳长反解）：需求 = \|S−柱\| + turns × 0.151 + \|柱−C\|，二分解 弧长 = 弦长 × θ / (2 sin(θ/2))；基准 2 圈解出 201°，1 / 2 / 3 圈还原配对表 155 / 200 / 230 在 3° 内 |
| 插头出生点 | 手写坐标改为 `routes.initial` 的规则条目 `plug_spawn_from`：柱心外 0.2233、方位角 307.5°，离锚点对径射线 ≥ 27°（切向出口占 23°）；基准还原到 0.2 mm |
| 靶心位置 | x、y 各由归一化量派生（先 y 后 x）：方框里避开插头 0.040 净空、且直线去 C 不穿锚点对径射线的位置；基准还原 (0.075, −0.130) |
| 方向轴 | `direction` 是防捷径离散轴：桌上东西不动，只翻转轨道方向与目标符号；对照组 `orbit_direction: opposite`（planner 新关键字） |
| 柱 x 上界 | 0.060 → 0.045：插头出生点在柱东南 0.223 m，是手最远的点，按可达 0.780 反推 |
| 共用规则 | 首圈高度、靶心净空、可达、工作区、`oracle_view` 从 `_rope_unwinding_geometry.py` 搬到 `_winding_post_geometry.py`，两个绕柱任务共用 |
| 贴柱守卫 | 加 `safety_max_contact_fraction: 0.85`（三圈缠满贴柱 3600–4000，接近绝对门 4800） |

**首跑暴露的隐含假设（c1052）。** 首版把 `to_c_route` 改成 closure、靶心只派生 x。角点 c1052（3 圈、锚点在柱东北）三圈缠完后 planner 走远侧去 C，
绳已缠满绷着，绕远侧等于把缠好的绳倒拖近一圈、机械臂折到底座旁，插头被拽脱手。处置：`to_c_route` 回到 straight，靶心 y 也派生，插头方位角上限从 20° 改 27°。
修后 1536 角点无一需要绕远侧；GPU 全部重跑。

**观察（只记录）。** 顺时针一圈的格（seed 2 / 7）终态绳离柱面 20 mm、贴柱 0，闭合计数 −1 判成功；逆时针一圈贴柱 1311。cw 三圈贴柱比 ccw 少 600–1400 节点。

文件清单见 `rope_winding_zh.md` §9.5；未提交。

## cloth_unroll 胶带式保持（09-06 00:00–01:10）

详细记录 `cloth_unroll_zh.md` §9.8。用户定的目标：布卷全程保持卷的形态直到被剥完。

| 项 | 内容 |
|---|---|
| 改动 | `TapeRelease` 改为按材料弧长钉与放（出生钉住绕在杆上的全部布，夹爪每走 d 松开离出口 ≤ d + lead 的粒子，最外层先、内端最后），demo 在任何物理步之前钉住、每步推进；`cloth.tape.enabled: true`；层间摩擦 0.4 → 0.1 |
| 首版教训 | 在夹爪张开的 60 步之后才钉：外圈已滑离剖面 42 mm，错位粒子按错弧长钉住 → 邻距 35 mm、单步跳 38 mm、`diverged=True`。移到物理步之前后邻距 4.6 mm |
| GPU 探针 | c002（1 圈、层距 0.018、杆高 0.037）回收比 0.561 → 0.732（胶带）→ 0.810（+ 摩擦 0.1）；seed 3（1.5 圈）0.843 → 0.894；seed 7 0.736 → 0.703 不变；seed 3 shove 仍判失败（−0.004，不释放） |
| 剩下的 | 末态两层格全在杆 +y 侧脚下 26–66 mm：尾端从杆顶翻下时叠在已铺布带上的约 40 mm 折边，长度 ≈ 垂落高度，所有格都有、再拉不开，是侧面出布支架固有的；要消掉只能改成从杆底出布（场景改动，未做） |
| 待跑 | `cloth_unroll_variation_sweep.sh oracle shove` 与 `variant_corners_sweep.sh cloth_unroll oracle` 全量复跑，更新 §9.6 |

## cloth_unroll 防过拉（09-06 上午）

详细记录 `cloth_unroll_zh.md` §9.9。任务考「刚好拉多少」，此前 oracle 多拉 30%、判据不罚过拉。用户先提的内端钉杆方案不可行（圈数守恒，卷只会被勒紧）。

| 项 | 内容 |
|---|---|
| 判据 | 第三条门 `over_pull` = 布带前端越过铺平位（杆轴 + 布长）的距离 ≤ 0，与单层率、回收比合取；判定器读 `pull_side`。先试的后端距离 `tail_gap` 撤回：行程固定时后端 = 前端 − 铺开长度，量的是折边（seed 1 / 9 没多拉却读 +38 mm，正是回收比最低的两格），改为只记录 |
| oracle | `pull_scale` 1.30 → 1.10：胶带之后按 1.0 拉后端正好停在杆轴，回收比 1.0–1.1 持平；1.10 比 1.05 多的 5% 给折边最长的角点 c002（0.43 → 0.68） |
| 探针 | seed 3 / 7 各四档 pull_scale、seed 3 overpull（前端 +161 mm）；按 1.10 复核 c002 / seed 1 / seed 9 全过（over_pull −12 … −16 mm），seed 1 overpull +112 mm 只被 over_pull 判失败 |
| 全量（1.05 那版） | seed 0–9 oracle 10/10、shove 10/10 判失败；角点 95/96（c002 折边最长，回收比 0.43） |
| 其他 | 摩擦回 0.4；离线门四种末态段改判过拉失败；sweep 汇总表加 `over_pull_mm` / `tail_gap_mm` |
| 全量（1.10） | seed 10/10、shove 10/10 判失败、角点 96/96，`over_pull` −9 … −23 mm；c042 单层率 0.708 贴门，三次复跑 0.687 / 0.787 / 0.698（两负），折边随机 65–140 格（§9.10）。处置待定：接受 / 平铺段下限 45 mm / 杆底出布 |

## cloth_unroll 转轴（09-06 晚）

详细记录 `cloth_unroll_zh.md` §9.11。用户方案：横梁改为随拉动转的辊、布尾粘在辊上、拉过头扯断。

| 项 | 内容 |
|---|---|
| 场景 | 横梁 → URDF 铰链辊（`add_hinge_mechanism`）；卷身 `fix_particles_to_link` 绑到辊；辊按放出布长转到「剥离前沿正对出口」（`spool_angle`），前沿之前 8 mm 解绑；内端起 20 mm 粘住；剥完后再拉超过 L + 20 mm 环境解绑尾端。耦合单向，辊由环境转 |
| oracle | 终点 = 尾端点 + √((L − 10 mm)² − 垂落高²)，`pull_scale` 退役 |
| 判据 | `tail_on_bar`（on_bar ≥ 10）、`over_pull` 按放松位 ≤ 0.030、回收比分母改 `span_max`、单层率不变 |
| 探针 | 固定 / seed 7 / c002 / c042 全过，两层格 0 / 1 / 1 / 16（原 60–140），单层率 0.95 / 0.97 / 0.93 / 0.93；shove 辊不转判负；overpull 放出 200 mm 时扯断、判负 |
| 离线 | 几何门（转轴段 + 四种末态改写）、角点 96/96、配置门过 |
| 全量（22:09–23:15） | seed oracle **10/10** 无扯断、shove **10/10** 判失败、overpull **10/10** 扯断判失败；角点 **96/96**（一格 22 s、35 min）。单层率 0.911–0.968（中位 0.935，固定杆版 +0.140）、回收比 0.98–1.29、`over_pull` −1.7…+15.5 mm（门 30）、辊上 132–231 粒子（门 10）、邻距 4.3–4.7（静止 3.7） |
| 折边确认消失 | 多层格中位 96 → 32，且构成从「桌面上的两层折边」（>2 层的格 0、峰高 5.9 mm）变成「从辊垂到桌面那一列」（>2 层 18 格、峰高 54 mm）。c042 三次复跑 0.934 逐次相同（此前 0.687 / 0.787 / 0.698）——±0.09 的摆幅来自折边不是求解器 |
| 转轴按预期 | 每格 `released = held − glued`（卷都剥完）；转角只随圈数分三组、组内差 6°（−254 / −345 / −434°）；邻距比 1.15–1.27，剥离处无硬拽 |
| 口径变化 | 回收比分母改 `span_max` 后 oracle 全部 0.98–1.29（超 1 的部分是约 2% 拉长，1 圈的格分母小放大到 +0.3），分辨力下降；吃紧的门变成单层率与 `tail_on_bar` / `over_pull` |
