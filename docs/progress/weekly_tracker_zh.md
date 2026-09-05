# TopoGym 周追踪：变体部署 → oracle 校验 → 数据管线与首次训练

> 建立：2026-09-04（周五）。本文是持续更新的追踪表，每天改「§3 今日任务」与各表的状态列；当天细节仍归档到 `YYYY-MM-DD_progress_zh.md`，本文只放状态与下一步。
> 本周指 2026-09-04 至 2026-09-11。最近一次更新：2026-09-05 下午（ring_transfer 第 10 步收口：oracle 10/10、角点 8/8、lift_only 对照重做；文档同步）。

## 0. 三条周目标

| # | 目标 | 完成判据 | 现状（09-05 上午） |
|---|---|---|---|
| 1 | 13 个任务的变体（variation）全部部署 | 每任务六项交付齐全：yaml `variation:` 块、`checks()` 与派生、demo 接线、离线门、sweep 脚本、GPU 写回文档 | 8 / 13 完成（09-05）：ring_transfer 的 oracle 10/10、角点子集 8/8、§7.4 已写回；`lift_only` 对照改成真提离（carry 的捏取 + 反应式抬离，放到两柱中点）后三格判失败、终态绕数集合为空，六项齐全 |
| 2 | 校验 oracle 的覆盖与稳定性 | 每任务：seed 0–9 oracle 10/10、对照策略落在预期区间、角点门全过；再按 §6.3 第 3 级跑 50 seed 稳定性统计（物理分类、失败标签） | 7 个任务过了 seed 0–9 与角点门；ring_transfer oracle 9/10（seed 0 死于 GPU 争用，待复跑）、lift_only 10/10 判失败、角点 5/8 过 + 3 格复跑中；50 seed 统计一个都没跑 |
| 3 | 引入一个 RL 算法、补全 generation pipeline、初步训练 | (a) 13 任务各有 `build_<task>_episode_spec` + split；(b) 至少一个任务录出 H5 数据集并过 π0.5 冒烟；(c) 一个任务上 RL 训练跑通并有学习曲线 | 09-05 无变化：(a) 只有 7 个旧任务有 generator、3 个有 split；(b) H5 writer 与 π0.5 冒烟链路已有，13 个变体任务没录过；(c) RL 只有类图设计（`classes_map/G1_online_rl.md`），无代码；§5 决策未定，目标 3 的排期从 09-05 起顺延 |

## 1. 目标 1：变体部署进度（`variation_axes_plain_zh.md` §6.2 顺序）

| 序 | 任务 | 物理 | 状态 | GPU 证据 | 记录 |
|---|---|---|---|---|---|
| 1 | linkbar_rotate_to_zone | 刚体 | 完成 | oracle 10/10，nearest_zone 5/10，角点 20/20 | `linkbar_rotate_to_zone_zh.md` §8；`init_frac` 改法后十格待复核 |
| 2 | diverter_route_ball | 刚体 | 完成 | oracle 10/10，fixed 7/10，角点 256/256 | `diverter_route_ball_zh.md` §8 |
| 3 | gate_cage_ball | 刚体 | 完成 | oracle 10/10，greedy 8/10，fixed_delay 6/10，角点 64/64 | `gate_cage_ball_zh.md` §5 |
| 4 | band_untwist | FEM 绳 | 完成 | oracle 10/10，wrong_end 3/3，角点子集 | `band_untwist_zh.md` §7 |
| 8 | unlink_c_ring | 刚体 | 完成 | oracle 10/10，no_align 10/10 判失败，角点 32/32 | `unlink_c_ring_zh.md` §11 |
| 12 | bar_through_hole | 刚体 | 完成（09-04） | oracle 10/10，bypass 10/10 判失败，角点 64/64，bypass 角点 64/64 判失败；夹空门 c000 三机位目视核对（09-05） | `bar_through_hole_zh.md` §5 |
| 5 | swap_crossing_sign | FEM 绳 | 未开始 | | 前置：`braid.py` 交叉位置接收采样值；`verify_braid_spec`；planner 抬升守卫。与 untangle_continuous 共用 builder，要一起回归 |
| 6 | rope_winding | FEM 绳 | 离线完成（09-05），GPU 跑中 | 固定布局复跑、seed 0–9 oracle / visual、wrong_way 0–2、角点子集 8 格跑中 | `physics/rope_winding/rope_winding_zh.md` §9；1000 seed 拒绝率 0、1536 角点全过；绳长反解、插头出生点规则、cw 不镜像（防捷径轴）、`orbit_direction: opposite` 对照组；demo / planner 与 rope_unwinding 共用，继承了两处执行链修正 |
| 7 | rope_unwinding | FEM 绳 | 完成（09-05 凌晨） | oracle 10/10，visual 10/10，wrong_way 3/3 判失败，角点子集 12/12 | `physics/rope_winding/rope_unwinding_zh.md` §7；1000 seed 拒绝率 0、1536 角点全过；cw = 镜像布局；圈距下界 0.012（tetgen 实测）；两处执行链修正（对照组覆盖不进校验、贴柱守卫改全绳比例门） |
| 9 | cloth_unpleat / cloth_unroll | 布 | cloth_unpleat 离线完成（09-05），GPU 进行中；cloth_unroll 未开始 | cloth_unpleat：1000 seed 拒绝率 0、192 角点全过；GPU 待写 | `cloth_unpleat_zh.md`；褶宽三档 + `pull_side` 镜像轴 + 两个 frac 派生（附着盘净空、可达盘 0.665 假设）；`observe()` 抓取高度已修；cloth_unroll 前置：圈数上限按层距、杆高、行程联合 |
| 10 | ring_transfer | FEM 环 | 完成（09-05） | oracle 10/10（seed 0 首跑死于 GPU 争用，空闲时复跑过）；角点子集 8/8（首跑 4/8 是派生写了带空格的 `goal.instruction`，改成模板 + `Layout.instruction()` 后 B 出发四格复跑 4/4）；lift_only 首版无效（off 段只抬 2 cm，终态 = 出生态），09-05 改为 carry 同款抬离 + 放到两柱中点，固定布局 / seed 3 / seed 0 三格判失败、终态绕数集合为空、目标柱顶未越过；visual 10/10 | `ring_transfer_zh.md` §7；三个搬运高度 / 长轴 / 捏取侧改为 Layout 推导，柱对走 `pair` + `derived`（无新 kind），中点 frac 派生含可达圆；1000 seed 拒绝率 0、256 角点全过 |
| 11 | cloth_fold | 布 | 未开始 | | 前置：四角抓取；工作区 / 可达断言 |

已固定的范式（每个新任务照此）：每轴独立区间；区间依赖其他轴的量抽归一化 `*_frac` 再由 Layout 派生；拒绝率门 2%；`validate` 只兜派生区间为空；角点门全跑（形变体取子集）；派生只能写标量、无空格的叶子（ring_transfer 教训）；FEM 绳任务接线前先用 `Layout.rope_mesh` + tetgen 离线探针出生路线（rope_unwinding 教训，0.3 s 一格）。
八次部署每次都晒出一条执行链里的隐含假设（diverter `max_lag`、gate `pinched`、gate 取板姿态插值、c_ring `passed_through` 与摆动段闭环、band 落点规则、bar 托座 y 硬写 0、rope_unwinding 对照覆盖进校验 + 贴柱守卫绝对门、ring_transfer 派生写句子进 Hydra 覆盖），修的都是执行链不是包络。

剩余 5 个任务（swap_crossing_sign、rope_winding、cloth_unpleat / unroll、cloth_fold）全是形变体：一格 1–18 min，GPU 时间是主要成本；GPU 与他人任务共用时 libuipc 会在首步以 `cudaErrorInvalidDevice` 退出（ring_transfer 已遇三次），遇到先看 `nvidia-smi` 再原样复跑该格。

## 2. 目标 2：oracle 覆盖与稳定性

| 层级（§6.3） | 内容 | 已做 | 未做 |
|---|---|---|---|
| 第 0 级 | 1000 seed 离线拒绝率 < 2% | 8 个任务全部 ≤ 0.2%（rope_unwinding、ring_transfer 均为 0） | 剩余 5 个 |
| 第 1 级 | 角点门（离线 + 物理） | 8 个任务；ring_transfer 离线 256/256、物理子集 8/8 | 剩余 5 个 |
| 第 2 级 | 全包络 × 50 seed 稳定性 sweep：物理分类、oracle 成败与失败标签、对照成败、任务读数 | 无 | 13 个任务；`stability_sweep.sh` 要补 13 个任务表 |
| 划档 | 按单调裕度轴分三档写回 `levels:` | 无 | 第 2 级之后 |

刚体任务的 50 seed sweep 便宜（linkbar / diverter / gate / c_ring / bar 一格 10–60 s，五个任务 × 3 组 × 50 seed 约 4–6 h GPU），可以先跑；09-04 夜间 GPU 被 rope_unwinding / ring_transfer 链占满没跑成，改到 09-05 夜间，前置是给 `stability_sweep.sh` 补五个刚体任务的任务表。

## 3. 今日任务（2026-09-05）

| # | 任务 | 状态 |
|---|---|---|
| 1 | ring_transfer B 出发的 4 个角点复跑（c129 c142 c189 c247，指令派生改模板后） | 完成 4/4（`runs/ring_transfer_corners/20260905_b_corners/`），角点子集合计 8/8 |
| 2 | ring_transfer seed 0 oracle、seed 9 visual 复跑（首跑死于 GPU 争用 `cudaErrorInvalidDevice`） | 完成，两格都过（`runs/ring_transfer_variation/20260905_rerun/`）→ oracle 10/10、visual 10/10 |
| 3 | `ring_transfer_zh.md` §7.4 写回；`lift_only` 对照重做（首版只抬 2 cm、终态 = 出生态，不算对照）：新增 `lift_only_phase`，carry 同款抬离后放到两柱中点，固定布局 / seed 3 / seed 0 三格判失败、绕数集合为空 | 完成；§1 第 10 行「完成（09-05）」；判据缺口记入任务文档 §6：不检查松手后环相对挡头的高度 |
| 4 | 第 6 步 rope_winding 六项交付：绳长反解、`to_c_route: closure`、柱顶联合不等式进 `checks()`；离线 tetgen 探针 | 离线五项完成；GPU 链（固定复跑 + seed 0–9 + wrong_way + 8 角点，约 10 h，与 ring_transfer 共用 GPU）后台跑中，写回 `rope_winding_zh.md` §9.4 |
| 5 | 给 `stability_sweep.sh` 补五个刚体任务的任务表，夜间跑 50 seed × 3 组 | 待做 |
| 6 | 定 RL 算法与首个训练任务（§5 决策点） | 待你拍板（09-04 遗留） |
| 7 | 本追踪文档 | 完成（上午） |
| 8 | 当日进度归档 `2026-09-05_progress_zh.md` | 晚间 |

昨日（09-04）九项全部收口，细节在 `2026-09-04_progress_zh.md`；未收的只有第 7 项 RL 决策；第 9 项 ring_transfer 的 GPU 尾巴今日第 1–3 项已收口。

## 4. 本周排期

| 日期 | 目标 1 | 目标 2 | 目标 3 |
|---|---|---|---|
| 09-04 周五 | bar 收尾 | | 定 RL 算法与任务 |
| 09-05 周六 | 第 7 步 rope_unwinding 已完成（09-04 晚 – 09-05 凌晨）；ring_transfer GPU 收尾完成（角点 8/8、oracle 10/10、lift_only 对照重做）；开始第 6 步 rope_winding | 刚体五任务 50 seed 稳定性 sweep 夜间跑（先补 `stability_sweep.sh` 任务表） | `build_<task>_episode_spec` 通用骨架：读 `randomize_task_cfg` 结果绑成 `TaskVariant`，先接 linkbar（若 rope_winding 占满白天则顺延到 09-06） |
| 09-06 周日 | 第 6 步 rope_winding | | 13 任务 split 文件（离线门通过即可，不跑物理） |
| 09-07 周一 | 第 5 步 swap_crossing_sign（与 untangle_continuous 一起回归） | rope 两任务 seed 0–9 + 角点子集 | RL 环境壳：按 `classes_map/G1_online_rl.md` 起 `RlTrainer` 骨架，接首个任务 |
| 09-08 周二 | ring_transfer 已提前到 09-05 收尾 → 空档给第 9 步 cloth_unpleat / unroll 提前一天开始 | | 录首个任务 150 + 50 条 H5，π0.5 冒烟 |
| 09-09 周三 | 第 9 步 cloth_unpleat / unroll（续） | cloth seed 0–9 | RL 首次训练跑起来，看曲线 |
| 09-10 周四 | 第 11 步 cloth_fold | 形变体任务的角点子集 | 训练调参 / 第二个任务 |
| 09-11 周五 | 补漏、13 任务 sweep 汇总表 | 划档草案（刚体任务） | 周总结 |

风险：形变体一格分钟级，GPU 与他人任务共用；如果第 5、6、9、11 步的 GPU 时间不够，优先保证 seed 0–9 oracle，角点只跑子集。目标 3 三条线（骨架 / split / RL 壳）到 09-05 上午还没动，§5 决策再拖会把 09-07 起的 RL 排期整体后移。

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

09-05 上午核对：`topogym/generation/` 仍是 7 个旧 generator，`configs/episode_splits/` 仍是 3 个文件，与 09-04 相同。

## 7. 更新约定

- 每天结束：改 §3 为次日任务，把当天状态写进 §1 / §2 / §6 的状态列，细节归档到当天的 `progress` 文件。
- 每个任务部署完：§1 状态列写「完成（日期）」+ GPU 证据 + 文档章节。
- 决策定了：§5 改成「已定：…」并写日期。
