# cloth_unpleat（docx 1.2 展开单个褶皱）：变体部署记录

> 2026-09-05。变体计划 `variation_axes_plain_zh.md` §6.2 第 9 步的前半（cloth_unroll 另记）。
> 按六项清单部署：yaml `variation:` 块、`checks()` 与派生钩子、demo 接线 + variant 行 + run 配置键、
> `check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测。参考样例 `bar_through_hole_zh.md` §3–§6、
> `../physics/rope_winding/rope_unwinding_zh.md` §7。任务本体的标定过程在 task yaml 的注释里，本文不重复。

## 1. 场景（所有轴都从这一幅画面出发）

桌面任务坐标系：x 轴从机械臂底座（x = −0.570）指向远处，y 轴左右，z = 0 是桌面。工作区盒 x ∈ [−0.25, 0.25]、y ∈ [−0.30, 0.30]。

一条 26 cm 长、12 cm 宽的布带沿 y 轴铺在桌上，宽度方向沿 x，中心在 (0.040, 0.000)。布带中段有一道**没压平的刀褶**：布带从 y 负端沿 +y 走到「下折痕」，向 −y 折回并抬起到「顶缘」，再越过下折痕落回桌面继续走到 y 正端。俯视图上，下折痕到顶缘之间是三层布叠着，两侧各一层。褶的几何由两个数决定：`cloth.pleat.width`（下折痕到顶缘的水平距离，24 mm）和 `cloth.pleat.crest_height`（顶缘离桌面的高度，22 mm）。收在褶里的材料 = 两条折臂之长 − width = 61.4 mm，不是自由参数，由这两个数算出（`cloth_profile_mesh.pleat_profile`）。

静置 60 步后褶自己躺平成三层叠合（PBD 布没有折痕刚度，实测事实），俯视跨度 198.6 mm 不变。夹爪张开、下降到布带**自由端**（+y 端）离布边 12 mm 处（`grasp.edge_inset`），在指垫离布面 8.5 mm 处刚性绑定一盘半径 18 mm 内的粒子，沿 +y 贴桌面直线拉 61.4 × 1.05 = 64.4 mm（`physical.pull_scale`），松手。桌面摩擦按住 −y 那一半布带，褶里的料被抽出来。

判定（`ClothUnpleatEvaluator`）：覆盖格里单层格占比 ≥ 0.90，且回收比（放出来的料 ÷ 静置后褶里存的料）≥ 0.85。对照走法 `run.motion=shove` 往 −y 推同样距离，布堆起来，回收比 ≈ 0，应判失败。整带平移量 `band_shift` 只记录。

**术语。** 半跨度 = 俯视跨度的一半；拉动终点 = 抓取点沿拉动方向前进 存料 × pull_scale 后的位置；可达盘 = 以 `reach.base_xy` 为圆心、`reach.max_hand_dist` 为半径的水平圆；首抽拒绝率 = 1000 个 seed 里第一次抽样就被派生 / 校验拒掉的比例，门 2%（`tests/check_variant_rng.py` 的 `MAX_REJECTION`）；角点 = 连续轴两端 × 离散轴全部取值的组合（`tests/check_variant_corners.py`）。

## 2. 变体轴与派生

| 类 | 叶子 | 抽法 | 基准 | 在场景里改的是什么 / 边界来源 |
|---|---|---|---|---|
| 单调裕度轴 | `cloth.pleat.width` | Cat{0.035, 0.030, 0.024} | 0.024 | 褶叠进去的宽度。越窄，「拉平了」与「褶塌了」两种读数越难分开。上限 0.035 来自抓取净空行：0.040 + 顶缘 0.028 时内缩量窗口 [0.008, 0.0072] 为空（离线门负例） |
| 防捷径离散轴 | `cloth.pull_side` | Cat{+1, −1} | +1 | **−1 = 镜像布局**：剖面对 y 取反，自由端在 −y 端，夹爪向 −y 拉。底座在 y = 0、工作区关于 y = 0 对称，两侧七行读数逐行相等（离线门断言）。藏起来的信息是「该拉哪一端」：褶的折向决定哪端是短尾段（75 mm）哪端是长引入段（99 mm），拉引入段会把锚点拖走。永远向 +y 拉的策略在 −1 格失败。判定器 `band_shift` 的位置回退路径按 sign 取远端（材料序路径不需要） |
| 连续布局轴 | `cloth.pleat.crest_height` | U[0.016, 0.028] | 0.022 | 顶缘出生高度。只影响出生三层间距与存料量（55–85 mm，见下表）；下限 4 × 粒径 |
| 连续布局轴 | `cloth.center_x` | U[0.010, 0.070] | 0.040 | 布带沿宽度方向平移 ±30 mm。`cloth.center: [x, y]` 拆成 `center_x / center_y` 两个标量键 |
| 连续布局轴 | `physical.pull_scale` | U[0.98, 1.12] | 1.05 | 行程相对存料的倍数。> 1.1 开始拖整条布带（yaml 注释实测） |
| 连续 → 派生 | `grasp.edge_inset_frac` → `grasp.edge_inset` | U[0, 1] **派生** | 0.4 → 0.012 | 捏取点离布边多远。区间 [0.008, min(0.018, 半跨度 − width − 2 × attach_radius)]：下限 2 × 粒径，上限保证附着盘离三层区 ≥ 36 mm。褶宽 0.035 + 顶缘 0.028 时上限 0.0164，独立抽 0.018 该角点净空 34.4 mm 不过 |
| 连续 → 派生 | `cloth.center_y_frac` → `cloth.center_y` | U[0, 1] **派生** | 0.5 → 0.000 | 布带沿长度方向平移。区间 [−0.030, min(+0.030, 可达盘弦长 − 终点偏移, 工作区上界 − 0.040 − 终点偏移)]，下端还受出生远边 ≥ 工作区下界 + 0.040 限制；终点偏移 = 半跨度 − inset + 存料 × pull_scale。1000 seed 里 33 个被可达盘封顶（center_x 大、行程长），独立抽会撞可达行 |
| 固定量 | `cloth.material_axis` = y | 固定 | y | 变体轴表写明「x 端到端有代码但未运行，实测后启用」；且沿 +x 拉的终点离底座 0.785 m，桌面高度够不着，启用前要改成向 −x 拉或另测可达 |
| 固定量 | `bending_relaxation` 0.0、布间摩擦 0.4、`pull_step_m`、`mesh.spacing`、`particle_size`、`touch_clearance`、`material_length`、`width` | 固定 | | 各有实测事故记录（yaml 注释） |

存料随两个褶参数变化（`pleat_profile` 算术）：

| width \ crest | 0.016 | 0.022 | 0.028 |
|---|---|---|---|
| 0.024 | 55.4 mm | 61.4 | 68.4 |
| 0.030 | 66.1 | 71.1 | 77.2 |
| 0.035 | 75.3 | 79.7 | 85.2 |

派生顺序（`cloth_unpleat.derive_task_cfg`）：先 `edge_inset_frac → edge_inset`（要褶宽、顶缘），再 `center_y_frac → center_y`（要内缩、行程、center_x）。派生值写回前转成 Python float：OmegaConf 拒收 numpy 标量（首版 33/1000 的「拒绝」全是这个类型错误，不是几何）。

两个字面量副本进 task yaml（角点门裸加载 task yaml，`${common…}` 解析不了）：`workspace.x / y`、`reach.base_xy`；`ClothUnpleatSceneBuilder.build` 断言 `workspace` 与 common 相等。

**变体前修的一处执行链：`observe()` 抓取高度。** 原来取「布带中线附着半径内全部粒子的最高 z」当抓取高度，那一条带包含整条布带，取到的是躺平后的褶顶（桌面 + 9.5 mm）而不是自由端（桌面 + 2 mm），指垫下降目标高 7.5 mm，基准布局靠 `attach_radius` 兜住。改为只在离抓取点沿材料方向 ≤ attach_radius 的粒子里取最高 z（cloth_unroll 2026-08-24 同一修法）。

## 3. `checks()` 七行

纯函数在 `topogym/tasks/deformation/_cloth_unpleat_geometry.py`（numpy + `cloth_profile_mesh`，不 import Genesis），只吃 task 配置，任务坐标系；`ClothUnpleatLayout.checks()` 转发，`validate()` 任一行不 ok 抛 `ValueError`；建场景、随机化拒绝、离线门、角点门、demo 启动打印共用。

| 行 | 读数 | 门 | 基准 | 192 角点最紧 |
|---|---|---|---|---|
| `pleat_fits_band` | 褶后尾段长 = lead − width | ≥ 4 × `mesh.spacing` = 0.030 | 0.0753 | 0.0524（width 0.035、crest 0.028） |
| `crest_above_underlayer` | crest_height | ≥ `particle_size` 0.004 | 0.022 | 0.016 |
| `grasp_clears_three_layers` | 半跨度 − edge_inset − width | ≥ 2 × `attach_radius` = 0.036 | 0.0633 | 0.0360（inset 派生取窗口上端，构造取等） |
| `band_in_workspace` | 出生布带四角 + 拉动终点到工作区 x / y 边的最小距离 | ≥ 0.040 | 0.1483 | 0.0952 |
| `hand_reach` | 拉动终点到 `reach.base_xy` (−0.570, 0) 的距离 | ≤ `reach.max_hand_dist` 0.665 | 0.6286 | 0.6650（center_x 0.070、center_y 派生取窗口上端，构造取等） |
| `pull_within_stroke` | 存料 × pull_scale | ≤ 0.120 | 0.0644 | 0.0954 |
| `start_still_stored` | 出生铺展比 = 俯视跨度 / 材料全长 | ≤ `grasp.max_start_spread_ratio` 0.80 | 0.764 | 0.787（width 0.024、crest 0.016，余量 0.013） |

`reach.max_hand_dist` 0.665 是**新键、是假设**：桌面高度沿 +y 贴桌拉的唯一实测点是 cloth_unroll 2026-08-24 在 x = 0.040 拉到 y = 0.181（离底座 0.636）；本任务 center_x 到 0.070 时同一 y 离底座 0.665。与 bar / gate 0.700、rope_unwinding 0.780 不是一个口径：那些手在 5–10 cm 高，这里指垫在桌面上 8.5 mm。角点子集先跑 center_x 0.070 + center_y 窗口上端的格（c1xx，见 §5），跟随误差中止就收到能过的值写回。

`start_still_stored` 是把 demo 的起始态守卫（`grasp.max_start_spread_ratio`）提前到采样期：不提前，width 0.024 × crest 0.016 的格出生铺展比 0.787，静置时褶再松一点就被 demo 以 `material_already_released` 中止，而那是布局问题不是执行问题。

## 4. 离线实测（2026-09-05）

| 门 | 结果 |
|---|---|
| `tests/check_cloth_unpleat_geometry.py`（numpy + PyYAML，系统 python 3 / numpy 1.21 与 venv numpy 2.4 都过） | PASS：原三段不变；新段「变体包络」：基准七行全过；派生还原基准（frac 0.4 → inset 0.012、frac 0.5 → center_y 0）；基准下两个窗口都是全宽（[0.008, 0.018]、±0.030）；镜像布局七行逐行相等、抓取点与拉动终点 y 取反（+0.0873 / +0.1517 ↔ −0.0873 / −0.1517）、规划器沿 −y 拉；**192 角点派生区间都非空、七行全过**，最紧行见 §3 表；三个负例（褶宽 0.040 + 顶缘 0.028 内缩窗口为空；褶宽 0.035 + 顶缘 0.028 + pull 1.12 + center_x 0.070 时纵向 +0.030 的可达读数 0.672 > 0.665 而派生窗口上端是 +0.0058；顶缘 3 mm 被 `crest_above_underlayer` 拒） |
| `tests/check_variant_rng.py` cloth_unpleat 段 | PASS：叶子顺序、seed 3 确定性、1000 seed 每轴在区间内、`edge_inset` 与 `center_y` 逐 seed 等于派生公式且在 [0.008, 0.018] / ±0.030 内、七行全过、三档褶宽 350 / 350 / 300、两侧 477 / 523、拉动终点的 y 与 pull_side 同号、最大可达 0.665、最长行程 95.4 mm、33 个 seed 的纵向窗口被可达 / 工作区封顶；**首抽拒绝率 0.000** |
| `tests/check_variant_corners.py --task cloth_unpleat` | **192 角点 192 可行**，Hydra compose 读数逐行一致（派生叶子 `center_y` / `edge_inset` 作为 `task.*` 覆盖传给固定布局路径） |
| `tests/check_configs_compose.py`、`tests/check_demo_configs.py` | PASS（run yaml 新键 `randomize_layout / difficulty / variant_id`；task yaml 新键 `center_x / center_y / center_y_frac / pull_side / edge_inset_frac / reach / workspace`） |
| CPU `run.build_only=true` | 固定布局：粒子 2283、checks 行七行 ok、`grasp=(+0.040,+0.087)`；`run.randomize_layout=true run.seed=3`：抽到 width 0.030、crest 0.0196、center (+0.0365, +0.0163)、inset 0.0152、pull 0.98、**side −1**，粒子 2344，`grasp=(+0.037,−0.064)`，`target=(+0.037,−0.132)`，七行 ok |

## 5. GPU 实测（4090，2026-09-05）

待写：固定布局复跑（`observe()` 修后 `grasp_after_settle` 的 z 应在桌面 + 2 mm 附近、`attach_error_mm` 不变坏、一格耗时）→ `bash bash_scripts/tests/cloth_unpleat_variation_sweep.sh oracle`（seed 0–9，同时录像）→ `SEEDS="0 1 2" … shove` → 角点子集（可达最远 + 镜像、抓取净空最紧 + 镜像、存料最多、铺展比守卫最紧）。

## 6. 文件集

| 文件 | 改动 |
|---|---|
| `configs/task_configs/cloth_unpleat_topogym_tabletop_v1.yaml` | `center` 拆键 + `center_y_frac`、`pull_side`、`edge_inset_frac`、`reach:`、`workspace:`、末尾 `variation:` 块 |
| `configs/run_configs/cloth_unpleat.yaml` | `randomize_layout / difficulty / variant_id` |
| `topogym/tasks/deformation/_cloth_unpleat_geometry.py` | 新：派生区间、拉动终点、七行 `cloth_unpleat_checks` |
| `topogym/tasks/deformation/cloth_unpleat.py` | Layout：`pull_sign`、`origin` 默认零、`band_centre` 读新键、`corners` 镜像、`observe` 抓取高度修正、`checks / validate`；builder 建场景前 `validate` + 字面量断言；模块级 `derive_task_cfg / validate_task_cfg` |
| `topogym/verification/cloth_unpleat_verifier.py` | `band_shift(sign=)` 位置回退路径按 sign 取远端；`ClothUnpleatEvaluator.pull_sign` |
| `demos/deformation/cloth_unpleat_physical_demo.py` | `randomize_task_cfg` 接线、`variant` 行、`checks` 行 |
| `tests/check_cloth_unpleat_geometry.py` | 新键；「变体包络」段（192 角点、镜像、三负例） |
| `tests/check_variant_rng.py`、`tests/check_variant_corners.py` | cloth_unpleat 任务段 / `TASKS` 条目 |
| `bash_scripts/tests/cloth_unpleat_variation_sweep.sh` | 新：oracle（含录像）+ shove 两组 |
| `bash_scripts/tests/variant_corners_sweep.sh` | `cloth_unpleat)` 分支（visual = 带录像的 oracle 格） |
