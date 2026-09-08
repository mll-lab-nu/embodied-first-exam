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
| 连续布局轴 | `physical.pull_scale` | U[0.98, 1.12] | 1.05 | **首段**行程相对存料的倍数；之后由闭环补拉（§5.4）按实测铺开长度补差额，总行程 ≤ 存料 × `pull_extend_max_scale` 1.15。可达 / 工作区 / 行程三行按 1.15 的上限算终点 |
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
| `hand_reach` | 最远拉动终点（首段 + 补拉上限）到 `reach.base_xy` (−0.570, 0) 的距离 | ≤ `reach.max_hand_dist` 0.665 | 0.6293 | 0.6650（center_x 0.070、center_y 派生取窗口上端，构造取等） |
| `pull_within_stroke` | 存料 × max(pull_scale, 1.15) | ≤ 0.120 | 0.0706 | 0.0980 |
| `start_still_stored` | 出生铺展比 = 俯视跨度 / 材料全长 | ≤ `grasp.max_start_spread_ratio` 0.80 | 0.764 | 0.787（width 0.024、crest 0.016，余量 0.013） |

`reach.max_hand_dist` 0.665 是**新键、是假设**：桌面高度沿 +y 贴桌拉的唯一实测点是 cloth_unroll 2026-08-24 在 x = 0.040 拉到 y = 0.181（离底座 0.636）；本任务 center_x 到 0.070 时同一 y 离底座 0.665。与 bar / gate 0.700、rope_unwinding 0.780 不是一个口径：那些手在 5–10 cm 高，这里指垫在桌面上 8.5 mm。角点子集先跑 center_x 0.070 + center_y 窗口上端的格（c1xx，见 §5），跟随误差中止就收到能过的值写回。

`start_still_stored` 是把 demo 的起始态守卫（`grasp.max_start_spread_ratio`）提前到采样期：不提前，width 0.024 × crest 0.016 的格出生铺展比 0.787，静置时褶再松一点就被 demo 以 `material_already_released` 中止，而那是布局问题不是执行问题。

**起始态守卫只剩这一条**（2026-09-05 决定）：静置后布带铺开的长度是否明显短于材料全长，即「料还收在褶里」。原来的第二条「三层重叠格数 ≥ 12」撤掉，理由见 §5.3 第一类；三层格数仍打印，只记录。

## 4. 离线实测（2026-09-05）

| 门 | 结果 |
|---|---|
| `tests/check_cloth_unpleat_geometry.py`（numpy + PyYAML，系统 python 3 / numpy 1.21 与 venv numpy 2.4 都过） | PASS：原三段不变；新段「变体包络」：基准七行全过；派生还原基准（frac 0.4 → inset 0.012、frac 0.5 → center_y 0）；基准下两个窗口都是全宽（[0.008, 0.018]、±0.030）；镜像布局七行逐行相等、抓取点与拉动终点 y 取反（+0.0873 / +0.1517 ↔ −0.0873 / −0.1517）、规划器沿 −y 拉；**192 角点派生区间都非空、七行全过**，最紧行见 §3 表；三个负例（褶宽 0.040 + 顶缘 0.028 内缩窗口为空；褶宽 0.035 + 顶缘 0.028 + pull 1.12 + center_x 0.070 时纵向 +0.030 的可达读数 0.672 > 0.665 而派生窗口上端是 +0.0058；顶缘 3 mm 被 `crest_above_underlayer` 拒） |
| `tests/check_variant_rng.py` cloth_unpleat 段 | PASS：叶子顺序、seed 3 确定性、1000 seed 每轴在区间内、`edge_inset` 与 `center_y` 逐 seed 等于派生公式且在 [0.008, 0.018] / ±0.030 内、七行全过、三档褶宽 350 / 350 / 300、两侧 477 / 523、拉动终点的 y 与 pull_side 同号、最大可达 0.665、最长行程 95.4 mm、33 个 seed 的纵向窗口被可达 / 工作区封顶；**首抽拒绝率 0.000** |
| `tests/check_variant_corners.py --task cloth_unpleat` | **192 角点 192 可行**，Hydra compose 读数逐行一致（派生叶子 `center_y` / `edge_inset` 作为 `task.*` 覆盖传给固定布局路径） |
| `tests/check_configs_compose.py`、`tests/check_demo_configs.py` | PASS（run yaml 新键 `randomize_layout / difficulty / variant_id`；task yaml 新键 `center_x / center_y / center_y_frac / pull_side / edge_inset_frac / reach / workspace`） |
| CPU `run.build_only=true` | 固定布局：粒子 2283、checks 行七行 ok、`grasp=(+0.040,+0.087)`；`run.randomize_layout=true run.seed=3`：抽到 width 0.030、crest 0.0196、center (+0.0365, +0.0163)、inset 0.0152、pull 0.98、**side −1**，粒子 2344，`grasp=(+0.037,−0.064)`，`target=(+0.037,−0.132)`，七行 ok |

## 5. GPU 实测（4090，2026-09-05，GPU 无其他租户）

### 5.1 固定布局复跑（`runs/cloth_unpleat_variation/20260905_baseline/fixed_unfold.log`）

`observe()` 修正的直接证据：静置后观测到的抓取点 z = 0.9216 = 桌面 + 2 mm，与设计点差 0.23 mm（08-23 的日志是 0.9288，高 7.15 mm）；`arm_pos_err_mm` 8.6 → **1.9**，`follow_error_mm` 6.2 → 1.2，`attach_error_mm` 0.45 → 0.57。判定 `unpleated=True`：单层率 0.945、回收比 **0.883**（08-23 CPU 后端 1.000）、跨度 252.8 mm、整带平移 1.66 mm。**一格 19 s**（含建场景与录像），比预估便宜一个量级，所以角点 192 格全跑而不取子集。

### 5.2 seed 0–9（`bash bash_scripts/tests/cloth_unpleat_variation_sweep.sh oracle shove`，`runs/cloth_unpleat_variation/20260905_seeds/`）

**oracle 10/10、shove 10/10 判失败。** 位置是任务坐标（side −1 的格抓取点与终点在 −y）；`shift` 是整带平移量（只记录）；一格 24–29 s。

| seed | width | crest | center (x, y) | inset | pull_scale | side | 存料 | 行程 | 抓取 y | 终点 y | 单层率 | 回收比 | shift mm | shove 回收比 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.035 | 0.0236 | (+0.037, +0.026) | 0.0153 | 1.103 | −1 | 81.1 | 89.4 | −0.048 | −0.137 | 1.000 | 0.999 | 2.6 | −0.098 |
| 1 | 0.030 | 0.0259 | (+0.042, −0.015) | 0.0092 | 1.107 | +1 | 74.9 | 83.0 | +0.069 | +0.152 | 1.000 | 0.998 | 1.2 | −0.109 |
| 2 | 0.024 | 0.0222 | (+0.054, −0.021) | 0.0102 | 1.088 | −1 | 61.6 | 67.0 | −0.110 | −0.177 | 1.000 | 1.046 | 3.4 | +0.185 |
| 3 | 0.030 | 0.0196 | (+0.037, +0.016) | 0.0152 | 0.980 | −1 | 68.9 | 67.6 | −0.064 | −0.132 | 0.941 | **0.889** | 1.2 | −0.039 |
| 4 | 0.030 | 0.0178 | (+0.015, −0.016) | 0.0110 | 1.018 | −1 | 67.5 | 68.7 | −0.101 | −0.170 | 0.942 | **0.907** | **27.9** | −0.043 |
| 5 | 0.024 | 0.0255 | (+0.024, −0.004) | 0.0096 | 1.014 | +1 | 65.4 | 66.3 | +0.084 | +0.150 | 1.000 | 1.044 | **22.9** | +0.211 |
| 6 | 0.035 | 0.0210 | (+0.037, +0.010) | 0.0080 | 1.092 | −1 | 78.9 | 86.2 | −0.073 | −0.159 | 1.000 | 1.004 | 0.8 | −0.142 |
| 7 | 0.024 | 0.0275 | (+0.039, −0.005) | 0.0168 | 1.099 | +1 | 67.9 | 74.6 | +0.075 | +0.149 | 1.000 | 1.040 | **29.5** | −0.058 |
| 8 | 0.030 | 0.0212 | (+0.070, −0.008) | 0.0093 | 1.061 | −1 | 70.3 | 74.6 | −0.093 | −0.168 | 1.000 | 1.037 | 4.0 | +0.103 |
| 9 | 0.030 | 0.0212 | (+0.052, −0.013) | 0.0092 | 1.061 | +1 | 70.3 | 74.6 | +0.072 | +0.147 | 1.000 | 1.040 | 4.9 | +0.179 |

- 十格全部两条门过；`observe()` 观测到的抓取点离设计点 0.04–1.13 mm、z 全部 0.9216；`arm_pos_err_mm` 1.9–2.2、`attach_error_mm` 0.51–0.90。
- **镜像轴生效**：side −1 六格（seed 0 / 2 / 3 / 4 / 6 / 8）抓取点在 −y 端、向 −y 拉、判成功；`band_shift` 的位置回退路径按 sign 取远端后读数与 +1 格同量级（0.8–4 mm），只有 seed 4 例外（见下）。
- **回收比与行程倍数**：pull_scale ≤ 1.02 的三格（seed 3 / 4 与基准 1.05）回收比 0.883–0.907、终态峰高 5.6–5.7 mm（还留一条两层带）、跨度 252–254 mm；≥ 1.06 的七格回收比 1.00–1.05、峰高 2.0 mm、跨度 260–263 mm（略超材料全长，布被拉长 1%）。回收比门 0.85 在下端只剩 0.03–0.06 余量：08-23 的 1.000 是 CPU 后端、指垫比布面高 7 mm 时的读数，不能再当基准。划档时 pull_scale 下端是候选的难度旋钮。
- **整带平移**：seed 4 / 5 / 7 的远端移了 23–29 mm（其余 ≤ 5 mm），判定仍成功，因为 `band_shift` 只记录不判定。三格的褶宽、方向、位置互不相同，共同点还看不出来；留给第 2 级 50 seed sweep 统计，是否升格为门槛那时再定。
- **shove 对照 10/10 判失败**，两条门都不过（单层率 0.57–0.73、回收比 −0.14 … +0.21、三层格 31–61）。回收比为正的四格是往褶推时把褶顶推塌、跨度涨了 10 mm，仍远低于 0.85。
- 十格 `visual_s*.mp4` 有帧（斜视机位，各 1.2 MB）。

### 5.3 角点 192 格（`bash bash_scripts/tests/variant_corners_sweep.sh cloth_unpleat oracle`，`runs/cloth_unpleat_corners/20260905_all/`）

**首跑 170 / 192**（守卫修正后复跑十格全过，合计 **180 / 192**；余 12 格是第二类），一格 9–21 s，总 66 min。22 个失败格分两类，两类都不是「oracle 够不着」：七行判据里最紧的可达行（c188 / c190，`hand_reach` 恰等于 0.665）和抓取净空行（取等的格）全部通过，**可达门 0.665 这个假设在角点上成立**。

**第一类：起始态守卫误判（10 格，`aborted reason=layers_came_apart`），判定器的隐含假设。** 十格全是褶宽 0.030 + 顶缘 0.016，且布带纵向位置在窗口的某一端。对照两格：c064 与 c065 只差 `center_y`（−0.030 与 +0.030，即 60 mm = 7.5 个 8 mm 格），静置后峰高 8.73 / 8.75 mm、铺展比 0.747 / 0.747 一样，三层格数却是 **24 与 6**——物理相同，读数只随布带相对**世界原点锚定的 8 mm 占用网格**的相位变。三层带宽 2 × 0.030 = 60 mm 正好 7.5 格，半格相位差把三层格数从 24 压到 6，再叠加 GPU 静置的逐次抖动（c073 / c075 几何相同读 21 / 10），低于门 12 就被 demo 当「三层散了」中止。同一网格 side −1 的镜像格读数也不同（c128 16 对 c160 30）。

处置按「修判据定义、不动包络」：`layer_report` / `occupied_cells` 加 `origin` 参数（默认世界原点，cloth_fold / cloth_unroll 不受影响），`ClothUnpleatEvaluator.classify` 把网格角锚在**静置后布带点云的最小角**上，末态也用同一网格。读数从此只是布的函数，与布带放在桌上哪里无关。三个 cloth 离线门复跑全过。

十格复跑（`runs/cloth_unpleat_corners/20260905_guard_rerun/`，连同邻格 c064 / c073 / c097 共 13 格）：**13 / 13 PASS**。（随后按 §7 决定把这条守卫整个撤掉，锚定网格保留给末态单层率读数。）锚定后三层格数：side +1 的五格 22–25，side −1 的五格 **恰好 12**（= 门），c097 18。镜像格读数低是因为锚点角换到了另一端：三层带离锚点角的距离从引入段长 97 mm 变成尾段长 67 mm，差 30 mm = 3.75 格，相位仍然不同。也就是说锚定消掉了「布带放哪」的依赖，没消掉「三层带落在网格哪个相位」的依赖，side −1 的读数正压在门上，GPU 静置抖动再大一点还会误判。两个更稳的候选（未做，见 §7）：三层格数取若干个子格相位偏移里的最大值；或改用静置后峰高（三层叠合 8.7–9.1 mm，两层 5.5，单层 2.0，三者分得开，本轮 192 格全部 8.7–9.1）。

同批复跑里 c064 / c073 的回收比从首跑的 0.801 / 0.848 变为 0.874 / 0.870（同一配置），GPU 静置与拉动的逐次抖动约 ±0.05，与 cloth_unroll 文档记的 0.09 同量级；门 0.85 附近的格因此不稳定。

**第二类：回收比 0.78–0.85 < 门 0.85（12 格），物理量与 oracle 行程公式的差。** 把 170 个跑完的格按 (pull_scale, 顶缘, 褶宽) 分组，算「损失」= 行程 − 回收比 × 存料（单位 mm，即拉了却没变成铺展长度的材料）：

| pull_scale | 顶缘 | 褶宽 0.024 | 褶宽 0.030 | 褶宽 0.035 |
|---|---|---|---|---|
| 0.98 | 0.016 | 损失 6–11（中位 8.0），回收比 0.78–0.87 | 4–12（8.1），0.80–0.92 | 8–10（9.1），0.85–0.87 |
| 0.98 | 0.028 | −2（全放出且拉长 1%），1.00–1.01 | −2，1.01–1.02 | 6–10（7.7），0.87–0.91 |
| 1.12 | 0.016 | 7–10，0.94–1.00 | 8，1.00 | 9–11，0.98–1.00 |
| 1.12 | 0.028 | 5（受拉长上限封顶），1.04–1.05 | 8，1.01–1.03 | 9–12，0.98–1.02 |

- 失败的 12 格全在 pull_scale 0.98 且顶缘 0.016（褶宽 0.024 的 10 格、0.030 的 2 格）。存料 55–66 mm、行程 54–65 mm，损失 8–10 mm 之后回收比落在 0.78–0.85。末态峰高 5.4–5.8 mm、两层格 15–32：**褶的最后 8–10 mm 没打开，留了一条两层的残褶**。
- 损失与褶的扁平程度相关：顶缘 0.028 配褶宽 ≤ 0.030（顶缘 / 褶宽 ≥ 0.93）损失 ≈ 0，其余（比值 ≤ 0.80）损失 8–10 mm；基准 0.022 / 0.024（0.92）在 1.05 下损失 10 mm（§5.1 的 0.883）。扁的褶静置后三层贴得整齐，层间摩擦 0.4 把最后一段折叠按住；陡的褶静置后层间不平整，全部放出。
- 这暴露的是 oracle 行程公式 `pull = 存料 × pull_scale` 里的隐含假设「存料全部能放出」，实测缺 8–10 mm。三种处置方式各有代价（见 §7 决策项），未定。

**只记录不判定的观察：整带平移。** 62 格远端移了 25–37 mm，几乎全是褶宽 0.035（c016–031、c048–063，两个方向全部）和褶宽 0.030 的大半；褶宽 0.024 的 64 格全部 ≤ 5 mm。这些格回收比 0.98–1.02、判成功。机制：宽褶存料多、行程长，层间摩擦要靠更长的拉力打开，而锚点那一半（引入段 87–99 mm）的桌面摩擦按不住，整条带滑 3 cm 后褶才开。任务模块把「整条布带被拖走」列为首要失败模式，判定器却只记录 `band_shift`。是否升格为门、门放在哪（seed sweep 里正确格 1–5 mm、shove 18–31 mm、这里 25–37 mm 三者重叠），见 §7。

### 5.4 闭环补拉（2026-09-05 下午决定并实现）

`topogym/planning/cloth_unpleat_planner.PullExtender` + `ClothLinkAttachDragPrimitive.run(extend=)`：按 `存料 × pull_scale` 拉完、手臂在末点保持 120 步到位后，量布带沿材料方向的铺开长度；比目标短就再拉差额，再量，直到达标或总行程到 `存料 × pull_extend_max_scale`（1.15）。目标 = 静置长度 + `pull_extend_target`（0.95）× 存料 + `pull_extend_recoil_m`（5 mm）。只对 `run.motion=unfold` 开；shove / overpull 两种标定走法保持开环。原语加了一个可选回调，默认不传时行为不变（cloth_fold / cloth_unroll 不受影响）。

两个实测出来的细节：

- **回弹量**。补拉时布带还被夹爪拉着，处于张紧状态；判定读的是松手静置后的。出厂布局：拉着时 257.9 mm、松手后 252.9 mm，差 5 mm（约布长 2% 的弹性伸长），折成回收比 0.08。第一版没加这项，拉着时读 0.966 ≥ 0.95 不补拉，松手后 0.885。
- **最小补拉量**。首版设一个粒径 4 mm，出厂布局的差额恰好 3.9 mm 被跳过；改为半个粒径 2 mm。

固定布局复跑（`runs/cloth_unpleat_variation/20260905_baseline_closedloop/fixed_unfold_min2.log`）：补拉 1 次 4.1 mm，总行程 68.5 mm（上限 70.6），松手后回收比 **0.885 → 1.026**，峰高 5.7 → 2.0 mm（残褶消失），整带平移 1.8 mm 不变，一格 21 s。全量复跑（seed 0–9 + 192 角点）见 §5.5。

### 5.5 闭环 + 新守卫的全量复跑

**seed 0–9（`runs/cloth_unpleat_variation/20260905_seeds_v2/`）：oracle 10/10、shove 10/10 判失败。** 与 §5.2 逐 seed 对照，只有回收比与残褶变了：

| seed | pull_scale | 存料 | 首段行程 | 补拉 | 回收比 §5.2 → 现在 | 末态峰高 |
|---|---|---|---|---|---|---|
| 3 | 0.980 | 68.9 | 67.6 | 1 次 2.1 mm | 0.889 → **1.012** | 2.0 mm |
| 4 | 1.018 | 67.5 | 68.7 | 0（拉着时差额 2.0 mm，正好低于最小补拉量 2 mm） | 0.907 → 0.906 | 5.3 mm |
| 其余八格 | 1.06–1.11 | | | 0（拉着时已超目标） | 1.00–1.05 不变 | 2.0 mm |

补拉只在需要的格触发，其余格与开环完全相同，所以 §5.2 的其他读数（抓取点、手臂误差、整带平移、shove）全部照旧。seed 4 那 2.0 mm 的差额是最小补拉量的边界，松手后 0.906 仍高于门 0.85。

**192 角点（`runs/cloth_unpleat_corners/20260905_all_v2/`）：192 / 192 PASS**，一格 14–27 s（中位 21），总 68 min。

- 补拉触发 56 格、不触发 136 格；没有一格碰到 1.15 × 存料的上限。触发的格松手后回收比 0.874–1.020。
- 全部 192 格回收比 0.874–1.054（中位 1.006），8 格在 0.90 以下（门 0.85，余量 ≥ 0.024）；单层率最低 0.937（门 0.90）。
- 首跑第一类的十格：守卫撤掉后全过；第二类的十二格：补拉后全过。
- 褶宽 0.035 的部分格末态仍留 4.5–6 mm 的峰高（一小段两层），回收比 0.99；宽褶铺开后的最后一小段贴着叠，判定不受影响。
- 整带平移 > 10 mm 的格 76 个（最大 37.6 mm），比开环的 62 个多：补拉的格多拉了几毫米，锚点也多滑了一点。按 §7 决定只记录。

到此六项交付齐全：yaml `variation:` 块、七行 `checks()` 与两个派生、demo 接线 + variant / checks / pull_extend 三行 + run 配置三键、`check_variant_rng.py` 段 + 几何离线门（含闭环与包络两段）、两份 sweep 脚本、本文档。

## 6. 文件集

| 文件 | 改动 |
|---|---|
| `configs/task_configs/cloth_unpleat_topogym_tabletop_v1.yaml` | `center` 拆键 + `center_y_frac`、`pull_side`、`edge_inset_frac`、`reach:`、`workspace:`、`pull_extend_*` 三键、撤 `min_start_three_layer_cells`、末尾 `variation:` 块 |
| `configs/run_configs/cloth_unpleat.yaml` | `randomize_layout / difficulty / variant_id` |
| `topogym/tasks/deformation/_cloth_unpleat_geometry.py` | 新：派生区间、拉动终点（按补拉上限）、七行 `cloth_unpleat_checks` |
| `topogym/tasks/deformation/cloth_unpleat.py` | Layout：`pull_sign`、`origin` 默认零、`band_centre` 读新键、`corners` 镜像、`observe` 抓取高度修正、`checks / validate`；builder 建场景前 `validate` + 字面量断言；模块级 `derive_task_cfg / validate_task_cfg` |
| `topogym/verification/cloth_fold_verifier.py` | `occupied_cells` / `layer_report` 加 `origin` 参数（默认世界原点） |
| `topogym/verification/cloth_unpleat_verifier.py` | 占用网格锚在静置点云最小角；`band_shift(sign=)`；`ClothUnpleatEvaluator.pull_sign` |
| `topogym/planning/cloth_unpleat_planner.py` | `PullExtender`、`EXTEND_MIN_M` |
| `topogym/primitives/cloth_link_attach_drag.py` | `run(extend=)` 回调：拉完保持后可续拉 |
| `demos/deformation/cloth_unpleat_physical_demo.py` | `randomize_task_cfg` 接线、`variant` / `checks` / `pull_extend` 行、守卫只剩铺展比、闭环接线 |
| `tests/check_cloth_unpleat_geometry.py` | 新键；「闭环补拉」段；「变体包络」段（192 角点、镜像、三负例） |
| `tests/check_variant_rng.py`、`tests/check_variant_corners.py` | cloth_unpleat 任务段 / `TASKS` 条目 |
| `bash_scripts/tests/cloth_unpleat_variation_sweep.sh` | 新：oracle（含录像）+ shove 两组 |
| `bash_scripts/tests/variant_corners_sweep.sh` | `cloth_unpleat)` 分支（visual = 带录像的 oracle 格） |

## 7. 三项决定（2026-09-05 下午）

1. **扁褶残褶**：采用闭环补拉（§5.4），不改 pull_scale 包络，不加手写残褶量。
2. **整带平移**：不设门。褶被拉平（单层率 + 回收比两条门）即成功，布带整体滑动只记录 `band_shift`。
3. **起始态守卫**：只看「布带铺开的长度是否短于材料全长」（`max_start_spread_ratio`），三层格数那条撤掉（它就是 §5.3 第一类误判的来源）。射线穿层法留作次选，未做。
4. 可达门 0.665 由 `hand_reach` 取等的 c188 / c190 通过（跟随误差 1.1–1.2 mm）确认；再远没有测，键仍标为实测点外推。
