# TopoGym 周追踪：变体部署 → oracle 校验 → 数据管线与首次训练

> 建立：2026-09-04（周五）。本文是持续更新的追踪表，每天改「§3 今日任务」与各表的状态列；当天细节仍归档到 `YYYY-MM-DD_progress_zh.md`，本文只放状态与下一步。
> 本周指 2026-09-04 至 2026-09-11。最近一次更新：2026-09-08 凌晨（cloth_fold 换单调裕度轴 `grasp.inset` → `goal.fold_fraction`，96 角点四组全量重跑逐格对上预期；swap 的文档欠账清完；§7 三项决定全部收口）。
> 09-08 场景评审那一批**场景与轴的改动**单独追踪在 `scene_rework_tracker_zh.md`（七项：谁改完了、证据在哪、谁还没动）。

## 0. 三条周目标

| # | 目标 | 完成判据 | 现状（09-08 凌晨） |
|---|---|---|---|
| 1 | 13 个任务的变体（variation）全部部署 | 每任务六项交付齐全：yaml `variation:` 块、`checks()` 与派生、demo 接线、离线门、sweep 脚本、GPU 写回文档 | **13 / 13 完成，六项交付逐项齐（09-08 凌晨）**。09-07 收口第 5 步 swap_crossing_sign（§1 第 5 行），09-08 收口两件：swap 的文档写回（`swap_crossing_sign_zh.md` §5.8、§4 的 planner 门数字按 `lane_overshoot` 0.130 复记、`checks()` 八行三处、进度文档 §3）；cloth_fold 换单调裕度轴并全量重跑（§1 第 11 行），`cloth_fold_zh.md` §7 的三项决定全部有结论 |
| 2 | 校验 oracle 的覆盖与稳定性 | 每任务：seed 0–9 oracle 10/10、对照策略落在预期区间、角点门全过；再按 §6.3 第 3 级跑 50 seed 稳定性统计（物理分类、失败标签） | **13 个任务 seed 0–9 oracle 10/10 与对照组全过；角点门 13 个任务全过**（形变体取子集）。cloth_fold 换轴后 96 角点四组重跑：oracle **96/96**、`fixed_fold` **32/96**、`fixed_corner` **24/96**、`drag` **0/96**，后三组逐格等于各自的预期数（f=1.0 的格 32、far_left 的格 24、全失败）。第 2 级 50 seed 稳定性统计见 §2 |
| 3 | 引入一个 RL 算法、补全 generation pipeline、初步训练 | (a) 13 任务各有 `build_<task>_episode_spec` + split；(b) 至少一个任务录出 H5 数据集并过 π0.5 冒烟；(c) 一个任务上 RL 训练跑通并有学习曲线 | 09-07 复核仍无变化：(a) 只有 7 个旧任务有 generator、3 个有 split；(b) H5 writer 与 π0.5 冒烟链路已有，13 个变体任务没录过；(c) RL 只有类图设计（`classes_map/G1_online_rl.md`），无代码；§5 决策未定，目标 3 的排期从 09-05 起顺延，已顺延三天。09-07 下午把 (a)(b)(c) 拆成了 §7 的 S1–S7 七步，其中 S1–S4 不吃 GPU，可与夜间 sweep 并行 |

## 1. 目标 1：变体部署进度（`variation_axes_plain_zh.md` §6.2 顺序）

| 序 | 任务 | 物理 | 状态 | GPU 证据 | 记录 |
|---|---|---|---|---|---|
| 1 | linkbar_rotate_to_zone | 刚体 | 完成（09-10 收口） | GPU seed 0–9 `runs/linkbar_variation/20260910_arc/`：oracle 10/10、nearest_zone 3/10、visual 10/10；角点物理 `runs/linkbar_rotate_to_zone_corners/20260910_arc/` oracle 20/20；离线：planner 6/6 + nearest_zone 3/6、几何门全过、角点解析 20/20、首抽拒绝率 0.010（门 0.02） | 09-09 红蓝定色 + 梁上去标识色 + `obs/goal_id`；09-10 修色条画法（两个尺寸装反，画的比判的宽一倍、径向只有 7.2 mm），指令改成「进到色条标出的扇形内即成功」，再把半宽 8°→**12°**、径向 40→**18 mm**、段数 7→10，色条成 4:1 的弧带。**成功窗口 16°→24°，任务容易一档**；跟着改的四处（区中心 ±78°、最小角距 24°、出生禁区 14°、角点命名对）见 `linkbar_rotate_to_zone_zh.md` §11.7 |
| 2 | diverter_route_ball | 刚体 | 完成 | oracle 10/10，fixed 7/10，角点 256/256 | `diverter_route_ball_zh.md` §8 |
| 3 | gate_cage_ball | 刚体 | 完成（09-11 三档坡自由滚动设计收口） | GPU seed 0–9 `runs/gate_cage_ball_variation/20260910_tiers/`：oracle 10/10、greedy 3/10（= 档 0）、fixed 7/10、visual 10/10；角点物理 `20260910_tiers1152/` 1152/1152 | `gate_cage_ball_zh.md` §5–§7。09-09 加三条轴（引道坡档、敞口镜像、架子侧镜像），`ball.speed` 改由坡档派生。**greedy 2/10 与 fixed 3/10 都是包络拉宽的直接后果不是回归**（球先到 46.2% → 18.4%；任何固定延时的上限 60% → 28.9%）。**只欠 1152 角点的物理层（4.3 h）** |
| 4 | band_untwist | FEM 绳 | **场景改造中（09-10 起：交叉数 1–2、四种出生形态）**；8 字版曾完成 | 8 字版：oracle 10/10，wrong_end 3/3，角点子集（由新一轮取代）。新版离线全绿（顶点 1280/1280、拒绝率 0.000）；GPU：seed 组 20 格 oracle **20/20**（09-13，余量校准后），wrong_end 8 字 / 6 字 2/2 判失败；待覆盖数组 | `band_untwist_zh.md` §8 |
| 8 | unlink_c_ring | 刚体 | 完成 | oracle 10/10，no_align 10/10 判失败，角点 32/32 | `unlink_c_ring_zh.md` §11 |
| 12 | bar_through_hole | 刚体 | 完成（09-09 重跑：圆杆圆孔 + 三孔只有一个通） | seed 0–9：oracle 10/10、bypass 10/10 判失败、`wrong_hole` 成功 2 格恰为 `open_index=1` 的两个 seed、三机位录像 30 段；角点 384：oracle 384/384、bypass 384/384 判失败、`wrong_hole` 成功 128 格逐格等于 `open_index=1` 的角点集合（反例 0）；「哪个孔是通的」跨孔径三机位实测，`front` 通/盲 0.55–0.62 对 0.15–0.19（256×256 上不掉），`topdown` 读不出 | `bar_through_hole_zh.md` §5、§7–§9 |
| 5 | swap_crossing_sign | FEM 绳 | 完成（09-07） | oracle 10/10，visual 3/3，restack_same 3/3 判失败，角点子集 8/8（两个符号各四格，一格 8–9 min） | `swap_crossing_sign_zh.md`（§5.8 待补，见 §3 第 1 项）；轴：`braid.crossing_sign` Cat{+1, −1} 防捷径（braid 字直接给 `(±1,)`，0 = 沿用 seed 采样）、`crossing_frac` U[0.30, 0.75]（换道窗口按位置向 `braid_span` 两端裁剪）、`channel_spacing` U[0.072, 0.095]、`center_y` ±0.040、`x_end` U[0.16, 0.20]；无派生叶子；共用 Layout 的 `checks()` 八行；三处包络取值与计划表 §3.4 原表不同，依据是算术（抬升顶 0.40、cover 步合成形状、两插头净空 7.0 cm）；1000 seed 拒绝率 0、32 角点离线全过；一处执行链修正：oracle 第一步把线铺回自家车道时越界量 `lane_overshoot` 0.040 → 0.130，并把这个假设写成第八行 `lane_entry_gap`——首跑 7/10，三格是铺下的线与另一根贴到 9.7 mm；根因是 FEM 绳的无应力形状就是出生的 S 形（`rest_shape: spawn`），松手后换道段回弹最多 38 mm，两处靠张力拉直的改动（拖到 97% 伸展、沿可达球面下放）实测无效已撤回，余量只能从几何来；与 untangle_continuous 共用构建器，seed 0–9 braid 字改前后逐位一致、默认布局八行全过（最紧 `lane_entry_gap` 35.3 mm / 门 32 mm） |
| 6 | rope_winding | FEM 绳 | 完成（09-05 晚） | oracle 10/10，visual 10/10，wrong_way 3/3 判失败，角点子集 10/10 | `physics/rope_winding/rope_winding_zh.md` §9；1000 seed 拒绝率 0、1536 角点全过；绳长反解、插头出生点规则、靶心 x/y 派生到直线去 C 数对圈的位置、cw 不镜像（防捷径轴）、`orbit_direction: opposite` 对照组；首跑 c1052 暴露「绕远侧路线对缠满的绳不成立」，修规则不改包络 |
| 7 | rope_unwinding | FEM 绳 | 完成（09-05 凌晨） | oracle 10/10，visual 10/10，wrong_way 3/3 判失败，角点子集 12/12 | `physics/rope_winding/rope_unwinding_zh.md` §7；1000 seed 拒绝率 0、1536 角点全过；cw = 镜像布局；圈距下界 0.012（tetgen 实测）；两处执行链修正（对照组覆盖不进校验、贴柱守卫改全绳比例门） |
| 9 | cloth_unpleat / cloth_unroll | 布 | **cloth_unpleat 09-13 三构型收口**（single / parallel / cross；十字为真二维折、分层圆弧初始化、角抓对角展开）；**cloth_unroll 完成（09-06 晚转轴；09-07 改为只钉尾端）** | cloth_unpleat 09-13：oracle **10/10**（单褶 4 / 平行 2 / 十字 4，单层率全 1.000）、shove 10/10 判失败（十字 shove 按余量截短）、single_pull 6/6 判失败、角点 **11,008 全过**（分层穷举）、首抽拒绝率 0；证据 `runs/cloth_unpleat_variation/20260913_final/`。09-05 旧记录：oracle 10/10（镜像 6 格）、shove 10/10 判失败、角点 192/192（闭环补拉 + 守卫改口径后全量复跑；首跑 170/192：10 格是占用网格相位误判、12 格是扁褶残褶 8–10 mm）、1000 seed 拒绝率 0、一格 14–29 s。cloth_unroll：oracle **10/10**（镜像 3 格）、shove 10/10 判失败、角点 **96/96**（一格 18–36 s，40 min）、1000 seed 拒绝率 0、可达 0.665 取等角点全过；1 圈 + 层距 0.018 的角点回收比 0.56（门 0.50）、c042 单层率 0.76（门 0.70），余量都只有 0.06 | `cloth_unpleat_zh.md`；三个执行链修正：`observe()` 抓取高度、占用网格锚到布带、oracle 闭环补拉（`PullExtender`，拉完量铺开长度再补差额，上限 1.15 × 存料，含 5 mm 松手回弹量）；三项决定见 `cloth_unpleat_zh.md` §7：整带平移只记录、守卫只看铺展长度。`cloth_unroll_zh.md` §9：圈数 Cat{1.0, 1.25, 1.5} + `pull_side` 镜像 + 杆高 / center_x，层距（平铺段五行二分）与纵向位置 frac 派生，起始守卫阈值派生（1 圈松卷静置后 0.65 > 固定 0.50，四格都靠它放行）；1.75 圈在 0.280 m 布上无平铺段；立柱 0.075 → 0.090；镜像格手腕转不到指令朝向（差 34–43°，位置误差不变，只记录）；09-06 胶带式保持（`TapeRelease` 改弧长钉与放、物理步前钉住、默认开）+ 层间摩擦 0.1：c002 回收比 0.56 → 0.81、1.5 圈 0.84 → 0.89，杆后落团消失；剩杆脚约 40 mm 折边（侧面出布固有）；09-06 判据加第三条门 `over_pull`（前端越过铺平位 ≤ 0）判过拉、`pull_scale` 1.30 → 1.10、摩擦回 0.4（§9.9：先试的后端距离量的是折边不是多拉，撤回；overpull 走法 +112…+161 mm 判失败）；按 1.10 全量 seed 10/10、角点 96/96，但 c042 单层率跨门（折边随机，§9.10）→ 09-06 晚**转轴**（§9.11）：横梁改为辊、卷身绑到辊上按放出长度转动解绑、布尾粘住、绷直后多拉 20 mm 扯断；判据四条门（`tail_on_bar`、`over_pull` 按放松位、回收比分母 `span_max`），`pull_scale` 退役。**全量复跑：seed oracle 10/10、shove 10/10 判失败、overpull 10/10 扯断判失败、角点 96/96（一格 22 s）**；单层率中位 0.935（比固定杆版 +0.14）、多层格中位 96 → 32 且构成变为「挂着的那一段」不再是折边、c042 三次复跑 0.934 逐次相同；1000 seed 拒绝率 0 。**09-07 只钉尾端**（§9.12）：钉住集合从整卷 1518 改为粘住的尾端 198，卷身交给重力——出生态 `on_bar` 198 → 534、`spread_ratio` 0.405 → 0.383（卷变紧，与 08-25 松卷 +17% 散开相反，差别在尾端有没有锚住）；卷仍靠尾端经布↔布接触被辊带着转，零外加耦合实测 84%。**全量复跑：seed oracle 10/10、shove 10/10 判失败、overpull 10/10 扯断判失败、角点 96/96 全 all_pass**；读数与钉死版持平（角点单层率 0.892–0.968 中位 0.935，回收比 0.961–1.306，`over_pull` −4.0…+17.3）|
| 10 | ring_transfer | FEM 环 | 完成（09-05） | oracle 10/10（seed 0 首跑死于 GPU 争用，空闲时复跑过）；角点子集 8/8（首跑 4/8 是派生写了带空格的 `goal.instruction`，改成模板 + `Layout.instruction()` 后 B 出发四格复跑 4/4）；lift_only 首版无效（off 段只抬 2 cm，终态 = 出生态），09-05 改为 carry 同款抬离 + 放到两柱中点，固定布局 / seed 3 / seed 0 三格判失败、终态绕数集合为空、目标柱顶未越过；visual 10/10 | `ring_transfer_zh.md` §7；三个搬运高度 / 长轴 / 捏取侧改为 Layout 推导，柱对走 `pair` + `derived`（无新 kind），中点 frac 派生含可达圆；1000 seed 拒绝率 0、256 角点全过 |
| 11 | cloth_fold | 布 | **六项齐（09-06）；09-08 换单调裕度轴后全量重跑** | seed 0–9：oracle **10/10**、drag 10/10 判失败、fixed_corner 2/10（= far_left 的 seed 数）、fixed_fold 5/10（= f=1.0 的 seed 数）；96 角点四组：oracle **96/96**、fixed_fold **32/96**、fixed_corner **24/96**、drag **0/96**，逐格对上预期数；固定布局 3.31 mm / 两层率 0.966；1000 seed 拒绝率 0 | `cloth_fold_zh.md`（§8 记换轴依据）。轴：`grasp.corner` 四选一指令轴、**`goal.fold_fraction` Cat{1.0, 0.9, 0.8}**（折痕位置，同为指令轴，2026-09-07 取代 `grasp.inset`——那条轴无视它反而得 100%，产生的是门线方差不是难度）、`center_y` ±0.030、`fold_slack` [0.96, 1.00]、`center_x` 由 frac 在远角可达盘封顶的窗口里派生；`checks()` **四行**（原第五行 `attach_disc_has_cloth` 随 inset 一起删，是死行）；结构判据改按**预测两层区**归一化、门 0.60 → 0.80（旧的裸比值默认角对角折，f=0.8 的几何上限只有 0.49，门在惩罚「折得短」）；余量随 f 单调收窄 7.57 / 7.05 / 1.98 mm；§7 三项决定全部收口。已知缺口：c030 型单粒子跳变自愈被记为发散而丢弃，约 1/96 |

已固定的范式（每个新任务照此）：每轴独立区间；区间依赖其他轴的量抽归一化 `*_frac` 再由 Layout 派生；拒绝率门 2%；`validate` 只兜派生区间为空；角点门全跑（形变体取子集）；派生只能写标量、无空格的叶子（ring_transfer 教训）；FEM 绳任务接线前先用 `Layout.rope_mesh` + tetgen 离线探针出生路线（rope_unwinding 教训，0.3 s 一格）。
历次部署每次都晒出执行链里的隐含假设（diverter `max_lag`、gate `pinched`、gate 取板姿态插值、c_ring `passed_through` 与摆动段闭环、band 落点规则、bar 托座 y 硬写 0、rope_unwinding 对照覆盖进校验 + 贴柱守卫绝对门、ring_transfer 派生写句子进 Hydra 覆盖、cloth_unpleat 抓取高度取褶顶 + 占用网格锚在世界原点 + 行程公式假设存料全能放出，swap_crossing_sign 把线铺回自家车道的越界量按默认布局定死、没考虑一次交叉后另一根的尾段就躺在这条车道里），修的都是执行链不是包络。swap 还多一条教训：FEM 绳的无应力形状是出生形状，松手回弹靠张力拉不掉，余量只能从几何留。

13 个任务的部署到 09-07 全部收口。形变体任务一格 1–18 min，GPU 时间仍是后续第 2 级 sweep 的主要成本；GPU 与他人任务共用时 libuipc 会在首步以 `cudaErrorInvalidDevice` 退出（ring_transfer 已遇三次），遇到先看 `nvidia-smi` 再原样复跑该格。

## 2. 目标 2：oracle 覆盖与稳定性

| 层级（§6.3） | 内容 | 已做 | 未做 |
|---|---|---|---|
| 第 0 级 | 1000 seed 离线拒绝率 < 2% | **13 个任务全部 ≤ 0.2%**（rope_unwinding、ring_transfer、cloth_unroll、cloth_fold、swap_crossing_sign 均为 0；`check_variant_rng.py` 一次跑完 13 个任务，09-07 复跑 swap 段 0.000、交叉符号 +1/−1 = 461/539、最大预测抬升 0.357 m） | 无 |
| 第 1 级 | 角点门（离线 + 物理） | **13 个任务离线全过，物理也全过**；ring_transfer 离线 256/256、物理子集 8/8；cloth_unroll 离线 96/96、物理 96/96（转轴版）；swap_crossing_sign 离线 32/32、物理子集 8/8；**cloth_fold 09-08 换轴后重跑：离线 96/96、物理 oracle 96/96**，另加三组对照各 96 格逐格对上预期 | 无 |
| 第 2 级 | 全包络 × 50 seed 稳定性 sweep：物理分类、oracle 成败与失败标签、对照成败、任务读数 | 无 | 13 个任务。**09-07 下午改口径**：不再往 `stability_sweep.sh` 补 13 行任务表——13 个 `<task>_variation_sweep.sh` 本来就是「seed × 组」的扫描器，各自写 `summary.csv`，把 `SEEDS` 从 0–9 换成 0–49 就是第 2 级；`stability_sweep.sh` 留给它原有的 6 个旧任务（untangle、untangle_continuous、cable_routing、stacked_plate、unlink_c_ring、band_untwist）。缺的是下面三样 |
| 划档 | 按单调裕度轴分三档写回 `levels:` | 无 | 第 2 级之后 |

09-04 夜间 GPU 被 rope_unwinding / ring_transfer 链占满、09-05 与 09-06 夜间被 rope_winding / cloth_unroll / cloth_fold / swap_crossing_sign 的部署链占满，第 2 级一直没跑成。现在部署已全部收口，GPU 空出来了。

**第 2 级还缺的三样**（都不必改那 13 个 sweep 脚本本身）：

1. **每格墙钟没有留档。** 13 个脚本都把 `---- <格名> (<秒>s)` 打到自己的标准输出，而标准输出通常只留在终端里；整个 `runs/` 下只有 `runs/ring_transfer_variation/20260905_lift_only/sweep.stdout` 一份留在了运行目录里，另有 cloth_fold 的五份留在 `runs/` 根目录（`cloth_fold_seeds.out` 与四份角点的 `.out`）。**约定**：以后每批都写成 `bash bash_scripts/tests/<task>_variation_sweep.sh oracle > $OUTDIR/sweep.stdout 2>&1`。
2. **物理发散没有统一分类。** `stability_sweep.sh` 的 `classify()` 认 `CRASH-segv`（段错误）与 `CRASH-phys`（进程没崩但物体飞出）；13 个任务脚本的 `run_state()` 只认 `TIMEOUT` 与 `RAISED`，物理发散要么落进任务自己的判据（cloth_fold 的 `diverged=True`），要么根本没有名字。
3. **没有跨任务汇总。** 13 份 `summary.csv` 的列各不相同（每个任务的轴与读数不一样），共同的只有 seed、oracle 结果、对照结果三样。

**一格 oracle 的实测墙钟**（取各任务 seed 0–9 那一批 `oracle_s*.log` 的时间戳差；对 cloth_fold 可与 `runs/cloth_fold_seeds.out` 里打印的 20–21 s 对照，两法一致）：

| 一格 10–30 s（刚体 + 布，八个） | s | 一格 6–15 min（FEM 绳 / 环，五个） | s |
|---|---|---|---|
| linkbar_rotate_to_zone | 10 | band_untwist | 379（277–726） |
| diverter_route_ball | 10 | swap_crossing_sign | 429（389–482） |
| gate_cage_ball | 11 | ring_transfer | 464（416–490） |
| unlink_c_ring | 17 | rope_winding | 565（332–896） |
| cloth_fold | 20 | rope_unwinding | 877（481–1760） |
| cloth_unroll | 25（22–30） | **五个合计** | **2714 s / seed** |
| bar_through_hole | 25 | | |
| cloth_unpleat | 布带 26（21–31）／十字 298（280–315） | | |
| **八个合计** | **144 s / seed** | | |

cloth_unpleat 那一格从 2026-09-11 起分两档：构型轴抽到 `single` / `parallel` 时是一条 3.5k 粒子、
4 子步的布带；抽到 `cross` 时是一张约 60k 粒子、16 子步的方布（22–24.5 cm 见方；九层叠层在 4 mm 或
4 子步下静置就自己散了，实测表见任务 yaml 的 `cloth.cross.solver`）。三种等概率，所以按 120 s / seed 估。

由此算 GPU 预算：八个便宜任务 50 seed 只跑 oracle 是 7200 s = 2.0 h，加一组对照约 3.6 h；五个 FEM 任务 50 seed 只跑 oracle 是 135 700 s = **37.7 h**（一天半），加一组对照约 68 h。本周装不下后者。

**建议的第 2 级口径**：八个便宜任务跑满 50 seed（oracle + 对照，约 3.6 h，一夜足够）；五个 FEM 任务先跑 20 seed（oracle only，54 280 s = 15.1 h，也是一夜），50 seed 留到划档阶段按需要补。对照组必须跑与 oracle 同一批 seed，否则「对照打不过」这条证据落在另一个样本上，说明不了同一个场景。

## 3. 今日任务（2026-09-07）

| # | 任务 | 状态 |
|---|---|---|
| 1 | 第 5 步 swap_crossing_sign 收口：前五项交付齐、GPU 链跑完（第六项「GPU 写回文档」见第 2 项） | 完成（09-06 16:44 – 09-07 03:06）：seed 0–9 oracle 10/10、visual 3/3、restack_same 3/3 判失败、角点子集 8/8，都在 `runs/swap_crossing_sign_*/20260906_231606_*/`；§1 第 5 行已写回 |
| 2 | swap_crossing_sign 文档补齐 | **完成（09-08 凌晨）**：`swap_crossing_sign_zh.md` 补 §5.8（0.130 那一轮的 oracle 10/10、visual 3/3、restack 3/3、角点 8/8、c001/c005 确认 2/2）；§4 的 planner 门数字按 `lane_overshoot` 0.130 复记（冻结 347、四角点 321/300/360/337 mm）；§5.6 的目录名 `223432` → `223446`；「`checks()` 七行」改八行（swap yaml 两处、计划表 §6.2 第 5 行） |
| 3 | `2026-09-06_swap_crossing_sign_progress_zh.md` 补 §2 末行许诺的 §3 | **完成（09-08 凌晨）** |
| 4 | cloth_fold 的三项决定（`cloth_fold_zh.md` §7） | **三项全部收口（09-08 凌晨，§7 重写）**：(1) `grasp.inset` 0.020 档 → 整条轴删掉换成折痕位置 `goal.fold_fraction`（§8）；(2) `fold_slack` 1.00 端**不收**——09-06 的证据是 inset 借给它的，换轴后两端各 48 格全过；(3) 发散守卫**不改口径、保守丢弃**，记为已知缺口（约 1/96） |
| 5 | 第 2 级稳定性 sweep 起跑（原写作「给 `stability_sweep.sh` 补任务表」） | **口径已改（下午）**，理由见 §2：13 个 `<task>_variation_sweep.sh` 本身就是「seed × 组」的扫描器，`SEEDS="0 1 … 49"` 就是第 2 级，不必把 13 个任务的判据行、对照组名、成功词再抄一遍进 `stability_sweep.sh`。今晚先跑八个便宜任务满 50 seed（oracle + 对照，约 3.6 h），五个 FEM 任务 20 seed（oracle only，约 15.1 h）；每批标准输出重定向进 `$OUTDIR/sweep.stdout` |
| 6 | 定 RL 算法与首个训练任务（§5 决策点） | 待你拍板（09-04 遗留，已拖三天） |
| 7 | 目标 3 的三条线（`build_<task>_episode_spec` 骨架、13 任务 split、RL 环境壳） | 未动；09-07 复核仍是 7 个旧 generator、3 个 split。下午的调查（第 11 项）把这三条线拆成了 §7 的 S1–S7 七步，并给出了先后次序 |
| 8 | 本追踪文档 | 完成（上午写状态；下午加 §7、改 §2 口径与 §4 排期） |
| 9 | 当日进度归档 `2026-09-07_progress_zh.md` | 晚间 |
| 10 | 跨任务汇总脚本 `bash_scripts/tests/variant_stability_report.py` | 待做（下午新加）：读若干个运行目录，出一张跨任务表——任务、seed 数、oracle 成功率、失败标签直方图、对照组成功率、物理发散格数、每格墙钟中位数与最大值。不改那 13 个 sweep 脚本，墙钟先读 `sweep.stdout` 的 `---- <格名> (<秒>s)` 行，没有这个文件时退回按 `oracle_s*.log` 的时间戳差估 |
| 11 | 数据生成管线的工程步骤调查：一条随机变体 episode 从 seed 走到 policy 吃得下的格式（RL / diffusion policy / VLA），中间缺哪几步 | 完成（下午），结论落在新 §7。三处断点：变体身份没进 H5 的 `setup` 段、13 个变体 demo 没接录制、动作向量缺夹爪一维且姿态用四元数；另有 9 个任务的指令文本没有进配置（7 个根本没有、2 个只写在 demo 的 f-string 里），这条是 VLA 的硬门 |
| 12 | 按 §7 排 S1（通用 `build_episode_spec`）与 S2（13 个任务的指令文本）两步 | 待做；两步都不吃 GPU，可与夜间 sweep 并行 |

可选（我提的，不是排期内）：swap_crossing_sign 的对照组只有 restack_same（第二步把同一根放回去），是目标层面的对照；防捷径轴 `braid.crossing_sign` 目前只有间接证据（判定器读到的出生符号与抽到的一致 10/10、第一步抓的都是实测在上那根 10/10）。要打直这条轴，可以照 cloth_fold 的 `fixed_corner`、linkbar 的 `nearest_zone` 加一个「无视符号、永远先抓固定那根」的对照，预期约 5/10 判失败，成本三格 GPU 约 25 min。

09-06 一天做了两件：cloth_unroll 转轴版全量复跑收尾、cloth_fold 六项齐（细节分别在 `2026-09-05_progress_zh.md` 末三节与 `cloth_fold_zh.md`，09-06 没有单独的归档文件）；swap_crossing_sign 从 09-06 下午跨到 09-07 凌晨，归档在 `2026-09-06_swap_crossing_sign_progress_zh.md`。

## 4. 本周排期

| 日期 | 目标 1 | 目标 2 | 目标 3 |
|---|---|---|---|
| 09-04 周五 | bar 收尾 | | 定 RL 算法与任务 |
| 09-05 周六 | 第 7 步 rope_unwinding 已完成（09-04 晚 – 09-05 凌晨）；ring_transfer GPU 收尾完成（角点 8/8、oracle 10/10、lift_only 对照重做）；开始第 6 步 rope_winding | 刚体五任务 50 seed 稳定性 sweep 夜间跑（先补 `stability_sweep.sh` 任务表） | `build_<task>_episode_spec` 通用骨架：读 `randomize_task_cfg` 结果绑成 `TaskVariant`，先接 linkbar（若 rope_winding 占满白天则顺延到 09-06） |
| 09-06 周日 | 第 6 步 rope_winding 已提前到 09-05 晚跑完 → 实际做的是 cloth_unroll 转轴版收尾 + cloth_fold 六项齐，下午起第 5 步 swap_crossing_sign | | 未动 |
| 09-07 周一 | 第 5 步 swap_crossing_sign 凌晨收口（含 untangle_continuous 共用构建器回归）→ **13 / 13 部署完成**，只差文档写回（§3 第 2 项） | 下午定第 2 级口径（§2）；夜间起跑：八个便宜任务 50 seed（oracle + 对照，3.6 h）+ band_untwist 与 swap_crossing_sign 20 seed（oracle only，808 s/seed × 20 = 4.5 h），合计 8.1 h，一夜装得下 | 下午出 §7 的工程步骤调查；晚间做 S1（通用 `build_episode_spec`）与 S2（13 个任务的指令文本），两步都不吃 GPU |
| 09-08 周二 | 部署已完；只剩 cloth_fold 三项决定定了之后补那 8 格角点 | 白天写 `variant_stability_report.py` 并汇总昨夜十格；夜间跑剩下三个 FEM 任务 20 seed（ring_transfer 464 + rope_winding 565 + rope_unwinding 877 = 1906 s/seed × 20 = 10.6 h） | S3（动作向量补夹爪 + 旋转换 6D）、S4（录制窗口与频率）、S5（一条命令录一个 split）；split 的 seed 列表取昨夜 sweep 判成功的那些 |
| 09-09 周三 | — | 十三个任务的第 2 级汇总表；开始看失败标签能不能构成划档的单调轴 | 录首个数据集：选 cloth_fold（一格 20 s）或 linkbar（10 s），150 + 50 条 H5，走 `export_h5_lerobot.py` → π0.5 冒烟 |
| 09-10 周四 | — | 划档草案（先做八个便宜任务，它们有满 50 seed） | S6：RL 环境壳（刚体任务，动作定义在高层参数上），首次训练跑起来看曲线 |
| 09-11 周五 | 补漏 | 划档草案定稿；FEM 五任务缺的 30 seed 按需要排 | 训练调参 / S7 数据集卡片；周总结 |

09-07 下午起四行的排期是我按「部署已收口 + §2 的实测墙钟 + §7 的七步」重排的建议，不是已定的计划：目标 1 那一列空出来了，容量全部挪给目标 2 的第 2 级 sweep 和目标 3。两条线抢的不是同一种资源——第 2 级 sweep 全在夜间吃 GPU，§7 的 S1–S5 是白天的纯 Python 活，只有 09-09 录数据那一格会与 sweep 抢 GPU。

风险：目标 3 三条线（骨架 / split / RL 壳）到 09-07 上午仍一个没动，§5 决策已拖三天，本周剩四天，(a)(b)(c) 三条判据同时达成的余量已经很薄。第 2 级的 GPU 量按 §2 的实测算下来比原估的更悬殊：五个 FEM 任务满 50 seed 只跑 oracle 就是 37.7 h，所以本周只给它们 20 seed。目标 3 (b) 的成本同样由任务贵贱决定——录 200 条（150 train + 50 val）在八个便宜任务上是 144 s × 200 = 8.0 h，在五个 FEM 任务上是 2714 s × 200 = 150.8 h（6.3 天，还没算录两路相机的渲染开销），所以首个数据集只能选便宜任务，13 个任务全量录制不是本周的事。

## 5. 目标 3 的决策点（需要拍板）

**RL 算法与训练对象。** 仓库里已有的是：四个旧任务的高层 MDP 壳（`topogym/envs/*_mdp.py`，`gym.Env` 接口，动作是离散的高层选择）；`classes_map/G1_online_rl.md` 的设计是包 rsl-rl 的 `OnPolicyRunner`（PPO），不重写训练循环；π0.5 / OpenPI 的 IL 冒烟链路已通。

建议：
- 算法用 **PPO（rsl-rl）**，与已有设计一致，不引入第二套训练框架。
- 首个训练任务选 **linkbar_rotate_to_zone**：刚体、一格 10 s、动作空间可以定义成高层参数（目标区选择 + 旋转角），奖励直接用判定器读数（角差、区内 / 区外）；防捷径离散轴（目标区颜色）正好检验策略是否读了指令。
- 状态用低维几何（销位姿、两区角度、目标区 id），不用图像；图像策略走 IL 那条线（π0.5）。
- 与 generation pipeline 的关系：RL 的 `reset(seed)` 走同一条 `VariantRng → randomize_task_cfg → build_<task>_episode_spec` 链，保证 RL 与录数据看到同一套变体分布。

需要你定的三件事：(1) PPO / rsl-rl 是否接受；(2) 首个任务是否 linkbar；(3) 训练目标是「跑通 + 曲线」还是要到某个成功率。

## 6. 数据管线现状（目标 3 (a)(b) 的起点）

| 模块 | 现状 | 缺口 |
|---|---|---|
| `topogym/generation/episode_spec.py` | `EpisodeKey / TaskVariant / TaskLayout / EpisodeSpec` 已定义 | 13 个变体任务无 `build_<task>_episode_spec` |
| `topogym/generation/<task>_generator.py` | 7 个旧任务（cable_routing、maze、onestroke、peeling、stacked_plate、swap、untangle） | 13 个变体任务一个都没有 |
| `configs/episode_splits/` | cable_routing、swap、untangle | 其余 |
| `topogym/data/episode_dataset_writer.py` + `h5_schema.py` | 可用，`setup/` 已写 seed / difficulty / task_goal | `setup/` 追加 `variant.parameters` 与 `success_params` |
| π0.5 冒烟（`il_adaptation/pi05_smoke_zh.md`） | 任务参数化，默认 untangle | 变体任务没录过数据 |

09-07 上午核对：`topogym/generation/` 仍是 7 个旧 generator（cable_routing、maze_wall_removal、onestroke、peeling、stacked_plate、swap、untangle），`configs/episode_splits/` 仍是 3 个文件（cable_routing、swap、untangle），与 09-04 相同。09-07 下午把这张表里每个缺口该怎么补、按什么次序补，写进了 §7；两处这张表没写到的缺口也在那里：13 个任务里 9 个的指令文本没有进配置（§7.3），以及动作向量缺夹爪一维（§7.4）。

## 7. 目标 3：一条随机变体 episode 走到 policy 吃得下的格式，缺哪几步（09-07 下午调查）

### 7.1 先把这条链整条摆出来

以 cloth_fold 为例（其余十二个任务同形），一次跑现在是这样走的：

一个整数 seed → `randomize_task_cfg(cfg, "cloth_fold", seed)` 按任务 yaml 末尾的 `variation:` 块，把 `cfg.task` 里声明过的叶子改写成这个 seed 的取值（抓四个角里的哪一个、折痕落在哪——被抓的角朝对角走完全程 / 九成 / 八成、布心在桌面上的位置、折叠余量 0.96–1.00）→ `ClothFoldSceneBuilder(...).build()` 按改写后的配置把布和机械臂搭出来 → planner 读回配置与场景排出路径点 → primitive 驱动机械臂，`scene.step()` 一步 10 ms 地推物理 → verifier 在末态读出判据（粒子平均偏离 mm、两层率、发散守卫），产出一个 `EpisodeResult`。

这一整条 13 个任务全部打通，这就是目标 1 的成果。**再往后就断了**：跑完除了一个 mp4 和终端里的几行数字，什么也没留下。要变成 policy 能训的数据，后面还要接三节：

`EpisodeSpec`（这一跑的身份与全部变体取值）→ `EpisodeDatasetWriter`（每 10 个物理步抓一帧，存图像、本体状态、动作，写成 `episode_0/timestep_<K>/{obs,action,info}` 的 HDF5）→ `scripts/export_h5_lerobot.py`（H5 → LeRobot 数据集 → π0.5）。

这三节的代码都已经存在，但只在三个**旧**任务上接过（untangle、cable_routing、rope_winding），而且 rope_winding 是借 cable_routing 的生成器顶上的——`demos/routing/rope_winding_physical_handle_demo.py:68` 直接 import 的就是 `build_cable_routing_episode_spec`。13 个变体任务一个都没有自己的接线。

### 7.2 三类 policy 各要什么格式

| policy 类 | 它吃什么 | 现在有什么 | 差什么 |
|---|---|---|---|
| VLA（π0.5 / OpenPI） | 一个 LeRobot 数据集，每帧五个字段：`image`、`wrist_image`、`state`(8 维 = 7 个臂关节 + 1 个夹爪)、`actions`(7 维)、`task`（一句自然语言指令，当 prompt 用） | `scripts/export_h5_lerobot.py` 已跑通冒烟链路（`compute_norm_stats` + `train.py` 几步不报形状错），默认任务 untangle | 动作里没有夹爪那一维、姿态用四元数（§7.4）；13 个变体任务里 7 个在配置里没有任何指令字段，另有 2 个（rope_winding / rope_unwinding）的指令只活在 demo 的 f-string 里（§7.3） |
| diffusion policy | 动作块：一次预测未来 H 步（常见 8–16 步）的动作，外加定长的观测历史 | H5 是逐帧存的，切块是下游转换器的事，这一层不缺 | 同样的动作表示问题；另外帧间隔（现在 10 个物理步 × 10 ms = 0.1 s）只以 `every_n_steps` 的形式写在 `setup` 里，没有写成秒，下游算增量要自己知道 dt=0.01 |
| RL（PPO / rsl-rl） | 不吃数据集，吃环境接口：`reset(seed)`、`step(action)`、每步一个 reward | 4 个旧任务的高层离散动作壳（`topogym/envs/*_mdp.py`）；`rsl-rl-lib==5.3.0` 与 `gymnasium==1.3.0` 已在 requirements 里 | 13 个变体任务没有环境壳；且 FEM 任务一个 episode 是 380–880 秒（§2 的表），在线 RL 在这些任务上不成立 |

### 7.3 断点一：变体身份与指令文本没有进文件

**身份。** 录出来的 H5 的 `setup` 段现在写的是 `stable_id / task_id / seed / preset_id / variant_id / difficulty / task_goal / status / success`——只有 seed，没有这个 seed 实际抽出了什么。想知道「这条数据是抓的哪个角、捏取点内缩几毫米」，只能拿 seed 回去重跑一遍随机化。数据集自己说不清自己，划档、按轴取值分层、按轴做泛化实验就都做不了。

**S1（不吃 GPU）：一个通用的 `build_episode_spec(cfg, task_id, seed)`，不是 13 个 generator。** 理由是 `variation:` 块已经声明了「这个任务哪些叶子会变」，而 `layout_randomization.sampled_leaves(task_cfg)` 已经能把这些路径列出来（`tests/check_variant_rng.py` 就是这么用的）。所以一份实现读一遍这些叶子的当前值，填进 `TaskVariant.parameters`，13 个任务共用——照旧任务的样子手写 13 份 125 行的 generator，是把同一件事抄 13 遍。
- 落点：`topogym/generation/variant_episode_spec.py` 一个函数；`episode_index.py` 的 `_GENERATORS` 表从「一任务一行」退化成 13 个任务指向同一个函数。
- 顺带把判据读数（`checks()` 的那几行、末态的粒子偏离与两层率）写进 `setup` 的 `success_params`——§6 表里已经点名这个缺口。
- 判据：13 个任务各跑一次，从 H5 的 `setup` 段读回的轴取值，与该 seed 的 sweep `summary.csv` 同一行的数字逐个相等。

**指令文本。** 这一条对 VLA 不是格式问题而是内容问题。现状盘点：

| 情况 | 任务 |
|---|---|
| 有按 seed 填空的指令模板 | cloth_fold（`goal.instruction`，`{corner}` 由 `ClothFoldLayout.instruction()` 填成 "far left" 这样的词）、ring_transfer（`{start}` / `{goal}` 填柱名） |
| 有一句固定的 `command.prompt` | linkbar_rotate_to_zone、diverter_route_ball（后者的注释写明「封死一侧之后指令没有内容可表达，退化成常量」）、bar_through_hole（09-09 加 `variation.instruction`："Push the bar through the hole that goes all the way through the panel."——哪个孔是通的只在画面里，指令刻意保持常量，见 `bar_through_hole_zh.md` §9.5） |
| 指令写死在 demo 的 f-string 里 | rope_winding / rope_unwinding（`rope_winding_physical_handle_demo.py:1609`） |
| 没有任何指令字段 | band_untwist、cloth_unpleat、cloth_unroll、gate_cage_ball、swap_crossing_sign、unlink_c_ring（六个） |

判断标准不是「指令要不要随 seed 变」，而是**策略靠「指令 + 出生那一帧画面」两样加起来，能不能唯一确定该做什么**。防捷径轴的取值只要有一样能读到就够：

| 防捷径轴 | 取值在哪里能读到 | 指令要不要随 seed 变 |
|---|---|---|
| linkbar `zones.target`（去哪个颜色区） | **哪里都读不到**（2026-09-09 起连接梁上一处标识色都没有：销、销套环、手柄盖与转轴同灰） | **要**。已改（`{target_colour}` 模板 + `instruction_fn`，填 red / blue）。无语言输入的基线走 `goal.goal_id_fn` → `obs/goal_id`（red=0、blue=1，h5 schema 0.3.0）。此前销取目标区的颜色、信息在画面里，那让「转到同色」这一次颜色配对就能满分（09-08 堵掉，改成第三种颜色）；09-09 再把梁上剩下的那块标识色也去掉 |
| cloth_fold `grasp.corner`（抓哪个角） | 哪里都读不到：布是正方形、四角一样 | **要**。已有（`{corner}` 模板） |
| ring_transfer 起止柱 | 起柱看得见（环就套在上面），**目标柱看不见**（柱子没有标记） | **要**。已有（`{start}` / `{goal}` 模板） |
| rope_winding / rope_unwinding 绕向 | 出生态是一根直绳加一根柱，顺时针逆时针从画面上无从分辨 | **要**。现在只写在 demo 的 f-string 里，没进配置 |
| cloth_unroll `pull_side`（从哪一侧拉） | 画面：整个布局是镜像的，自由端在哪一侧看得见 | 不要，常量即可 |
| swap_crossing_sign `braid.crossing_sign` | 画面：当前哪根在上看得见；任务是把它换成另一个符号 | 不要，常量即可（「把交叉处上下两根对调」） |

写错了会怎样：该随 seed 变而没变的那两处（cloth_fold、ring_transfer，现在都已经对了），同一张图会对应两个互相矛盾的正确动作，策略无从分辨该做哪个——训练集自相矛盾，这不是训练技巧能补的。rope 两个任务现在是「对的内容放在错的地方」：指令确实随绕向变，但它活在 demo 的 f-string 里，配置和 H5 都不知道有这回事，换个 demo 或换条录制路径就丢了。

**S2（不吃 GPU）：13 个任务都在 yaml 里有 `goal.instruction`，demo 把它传给 writer 的 `task_goal`。** 其中三处要按 seed 填空（cloth_fold、ring_transfer 已有；rope_winding / rope_unwinding 把绕向从 demo 的 f-string 搬进模板），其余按上表写成常量句。写法照 cloth_fold 与 ring_transfer 已有的做（注意 ring_transfer 的教训：派生只能写标量、无空格的叶子，句子要走模板不走派生）。
- 判据：13 个任务各抽 10 个 seed 录出 `task_goal`；上表标「要」的三个任务，两个轴取值不同的 seed 指令文本不同；标「不要」的任务，指令文本逐 seed 相同且句子里没有出现只有该 seed 才成立的量。

### 7.4 断点二：动作向量缺夹爪，姿态用四元数

现在 `action/ee_pose_action` 是 7 个数：下一帧的**绝对**末端位姿 = 位置 xyz（米）+ 姿态四元数 (w,x,y,z)。三个问题：

1. **没有夹爪。** 抓与放是每个任务的关键时刻，但动作里没有这一维；夹爪只出现在观测里（`obs/gripper_state` 是手指关节位置，`obs/is_gripper_close` 是布尔）。拿这份数据做行为克隆，策略学不到「此刻该合上手指」，只能从图像里猜。
2. **四元数不适合回归。** 同一个姿态有两个四元数 q 与 −q（双覆盖）。逐维归一化再回归 L2，等价于要网络在两个等价答案里挑一个，梯度互相抵消；OpenPI 的 `compute_norm_stats` 对这四维也算不出有意义的均值方差。`export_h5_lerobot.py` 的文件头已经把这条标成 KNOWN SCHEMA GAP。
3. **形状对上了但含义没对上。** π0.5 冒烟能过，是因为我们的 `state`(8) / `actions`(7) 恰好与 OpenPI 的 Libero 样例同形；但 Libero 的 7 维是「末端增量 6 + 夹爪 1」，我们的 7 维是「绝对位置 3 + 四元数 4」。冒烟验的是形状，不是语义。

**S3：writer 多写两个数据集，现有 `ee_pose_action` 一个字节不动**（三个旧任务已录的数据不作废）：
- `gripper_action`（1 个数）：控制器**下发**的目标开合值 `controller.current_gripper_qpos`（`topogym/robot/franka.py:46` 起由 `open()` / `close()` 写），不是实测的手指位置 `gripper_qpos()`。行为克隆要学的是指令，不是结果。
- `ee_rot6d_action`（6 个数）：下一帧姿态旋转矩阵的前两列。连续、无双覆盖，第三列由叉积恢复。
- 增量表示**不进** H5，放在 `export_h5_lerobot.py` 里由相邻两帧的绝对位姿现算，同时把帧间隔（秒）写进 `setup`。理由：增量除以帧间隔才有意义，而帧间隔由 `every_n_steps` 决定；把增量落盘就是把这个数字焊死，以后改采样率会让已录数据的单位悄悄改变。
- 这样 VLA 那一路拿到的 7 维 =「位置增量 3 + 旋转增量 3 + 夹爪 1」，与 Libero 约定同形也同义；diffusion policy 那一路拿绝对位姿的动作块（3 + 6 + 1 = 10 维）。
- 判据：`topogym/data/replay.py` 用新字段开环回放，末端轨迹跟踪门与现在同样紧；夹爪那一维的开合时刻与 oracle 计划里的抓 / 放时刻对齐。

### 7.5 断点三：录制没接线、录制窗口不对

**S4（不吃 GPU）：**
- `record_dataset` 与 `dataset_every_n_steps` 现在只在 4 个旧任务的 run 配置里（cable_routing、rope_winding、rope_unwinding、untangle_handle）。放进 `configs/run_configs/default.yaml` 一次，13 个 demo 都继承；每个 demo 再照 rope_winding demo 的样子套一层 `dataset_writer_or_null`。
- 采样率现在是对的：`dt = 0.01`、`every_n_steps = 10` → 10 Hz，与 `export_h5_lerobot.py` 的 `--fps 10` 一致。
- **录制窗口两头都不对**：`EpisodeDatasetWriter` 从 `__enter__` 就开始抓帧，而布 / 绳任务开头有一段静置——cloth_unroll 的 `success.settle_steps` 是 200 步（其中 60 步与夹爪张开重叠），200 × 10 ms = 2 秒 = 20 帧「机械臂还没开始动」。已经有 `stop_capture()` 管收尾（不把 `reset_home` 的瞬移录进去），缺一个对称的起点——要么加 `start_capture()`，要么把 `with` 块的入口挪到静置之后。另外 `stop_capture()` 只有三个旧 demo 调了（untangle、cable_routing、rope_winding），13 个变体 demo 接 writer 时要一起接上，否则末尾 `run.final_hold_steps`（cloth_fold 是 100 步 = 10 帧）和退刀会一起进数据集。
- 相机不缺：`front`（512×512）与 `wrist`（256×256）在 env 配置里，`tabletop.py` 建场景时无条件加上，13 个任务都有。

**S5（吃 GPU）：一条命令录一个 split。** `configs/episode_splits/` 现在只有 3 个旧任务。加 `bash_scripts/tests/record_split.sh`，照 `<task>_variation_sweep.sh` 的样子写：一个 seed 一格、失败的格重录、写 `summary.csv`。
- **split 的 seed 列表要挂在第 2 级 sweep 的结果上**：只把 oracle 判成功的 seed 放进 train，判失败的 seed 单独留一份清单（那是「这个包络里 oracle 打不过的地方」的记录，本身有价值）。这就是目标 2 与目标 3 的接缝，也是先跑第 2 级、再录数据的理由。
- 成本（§2 的实测墙钟 × 200 条）：八个便宜任务 144 s × 200 = 8.0 h；五个 FEM 任务 2714 s × 200 = 150.8 h ≈ 6.3 天，还没算录两路相机的渲染开销（首批录完实测写回）。首个数据集只能选便宜任务。

### 7.6 RL 那一路（S6）

录数据只要「跑一遍、存下来」；RL 要「随时 `reset(seed)`、每步给 reward」，是另一套接口。两条线共用的只有前半段：`reset(seed)` 必须走同一条 `VariantRng → randomize_task_cfg → build_episode_spec`，否则 RL 见到的变体分布与录的数据不是同一个分布。

一条硬约束来自 §2 的墙钟：FEM 任务一个 episode 是 380–880 秒，在线 RL 要几千到几万个 episode，这些任务上不可能。刚体任务 10–25 秒一格，一万个 episode 也要 28–70 小时。所以首个 RL 任务只能在刚体里选，而且**动作要定义在高层参数上**（一个 episode 一次决策：选哪个目标区 + 转多少度），不是低层的每步控制。这与 §5 已有的建议一致，但「一个 episode 一次决策」这条要写明白——那样每条轨迹只有一步，PPO 的优势估计里没有时序可言，退化成上下文赌博机；如果要真正的多步 MDP，得先把任务切成多个可中断的阶段。这是 §5 需要你拍板的第三件事（训练目标）之外的一个新问题。

### 7.7 七步的先后与判据

| 步 | 内容 | 吃 GPU | 判据 |
|---|---|---|---|
| S1 | 通用 `build_episode_spec`：变体取值 + 判据读数进 `setup` | 否 | 13 个任务从 H5 读回的轴取值与 sweep `summary.csv` 同行相等 |
| S2 | 13 个任务的 `goal.instruction` 进 yaml；三处按 seed 填空 | 否 | §7.3 表里标「要」的三个任务，轴取值不同的 seed 指令不同；标「不要」的逐 seed 相同 |
| S3 | 动作向量补 `gripper_action` 与 `ee_rot6d_action`；增量放在转换器里算 | 否 | `replay.py` 开环回放跟踪门不放松；夹爪开合时刻与计划对齐 |
| S4 | `record_dataset` 进 `default.yaml`、13 个 demo 接 writer、录制起止挪到动作段两端 | 否 | 任一任务录一条 H5，首帧是机械臂开始动的那一帧、末帧是松手沉降完的那一帧 |
| S5 | `record_split.sh`；split 的 seed 取自第 2 级 sweep 的成功集合 | 是 | 首个便宜任务录满 150 + 50 条，π0.5 冒烟过 |
| S6 | RL 环境壳（刚体任务，高层参数动作），`reset(seed)` 复用同一条随机化链 | 是 | 训练跑起来有曲线；同一个 seed 下 RL 与录数据看到同一个场景 |
| S7 | 数据集卡片与合约：13 个任务的轴与区间、split、oracle 成功率、字段与单位、坐标系 | 否 | `data_pipeline/h5_data_format_zh.md` 补上变体那一节 |

S1–S4 互不依赖，都不吃 GPU，可以与夜间的第 2 级 sweep 并行；S5 依赖 S1–S4 全部完成，也依赖第 2 级 sweep 出成功集合；S6 只依赖 S1；S7 最后写。

需要你拍板的（在 §5 三件事之外新增一件）：**S3 改动作向量会不会让三个旧任务已录的数据与新数据不同构**——我的做法是只增不改（`ee_pose_action` 原样保留），旧数据仍可读，但旧数据没有夹爪那一维，两批数据不能直接合成一个训练集。如果不打算再用那三份旧数据，这一条就不是问题。

## 8. 更新约定

- 每天结束：改 §3 为次日任务，把当天状态写进 §1 / §2 / §6 的状态列，细节归档到当天的 `progress` 文件。
- §7 的 S1–S7 做完一步：在 §7.7 那张表的对应行后面补「完成（日期）」+ 判据实测结果，并把 §6 表里对应的缺口划掉。
- 每个任务部署完：§1 状态列写「完成（日期）」+ GPU 证据 + 文档章节。
- 决策定了：§5 改成「已定：…」并写日期。
