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
