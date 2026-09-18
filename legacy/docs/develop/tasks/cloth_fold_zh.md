# cloth_fold（docx 1.1 折角）：变体部署记录

> 2026-09-06 部署，2026-09-07 换单调裕度轴（`grasp.inset` → `goal.fold_fraction`，见 §2 与 §8），
> 2026-09-08 指令改用颜色指角（方位词退场，见 §2 与 §9）。
> 变体计划 `variation_axes_plain_zh.md` §6.2 第 11 步，13 个任务里最后一个布料任务。
> 按六项清单部署：yaml `variation:` 块、`checks()` 与派生钩子、demo 接线 + variant 行 + run 配置键、
> `check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测。参考样例 `cloth_unpleat_zh.md` §1–§3、§6
> （同为 PBD 布、同一个原语、同一个判定器文件）。任务本体的标定过程在 task yaml 的注释里，本文不重复。

## 1. 场景（所有轴都从这一幅画面出发）

桌面任务坐标系：x 轴从机械臂底座（x = −0.570）指向远处，y 轴左右（机械臂面向 +x，它的左手边是 +y），z = 0 是桌面。工作区盒 x ∈ [−0.25, 0.25]、y ∈ [−0.30, 0.30]、z ∈ [0.03, 0.40]。

一块 24 cm × 24 cm 的正方形单层布平铺在桌上，中心在 (4.0, 0.0) cm，四条边与 x、y 轴平行，四个角在中心的 (±12, ±12) cm 处。**四个角各涂一块 6 cm × 6 cm 的颜色**（红 / 绿 / 黄 / 紫，2026-09-08 起），哪个角涂哪种颜色每个 episode 重抽一个排列；指令说的是颜色（"the red corner"），不是方位（§9）。夹爪张开、下到**离机械臂最远的左边那个角的角尖**（远左角，(16.0, 12.0) cm），指垫停在布面上方 8 mm，刚性绑定角尖周围半径 18 mm 内的粒子（只有四分之一个圆盘压在布上，约 22 个粒子），然后提着这个角**绕折痕转半圈**：折痕垂直于「被抓的角 → 对角角尖」这条对角线；被抓的角先升起、越过折痕上方最高点、再落下，松手。落下的那块布盖在另一块上，覆盖处变成两层，折痕就是那条线。

**折痕落在哪，是这个任务的第二条指令。** `goal.fold_fraction`（下文写 f）定义为

```
f = 抓点到折痕的垂直距离 ÷ 布中心到角尖的距离 L，   L = 12√2 = 16.97 cm（半条对角线）
```

等价地 f = 角实际走的距离 ÷ 角对角走完的距离（33.94 cm）。折痕从布中心朝**被抓的那个角**外移 L(1 − f)。f = 1 时折痕正好是另一条对角线、落点正好是对角那个角（近右角，(−8.0, −12.0) cm），布变成一个两层的直角三角形——这是 2026-09-06 之前唯一做过的折法。

弧线不是选的，是材料定的：被抓的角到折痕的布料长度 = L × f，角只能在以折痕为轴、半径 = 材料长 × `physical.fold_slack` 的圆上走，步数由标定手速 3.6 mm/步反推：

| f | 折痕离布中心 | 抓点到折痕 | 角走的距离 | 落点离对角角尖 | 动的材料 | 弧半径(slack 0.98) | 步数 | 最高点离桌面 |
|---|---|---|---|---|---|---|---|---|
| 1.000 | 0 cm | 16.97 cm | 33.94 cm | 0 cm | 50.0% | 16.63 cm | 145 | 16.6 cm |
| 0.875 | 2.12 cm | 14.85 cm | 29.70 cm | 4.24 cm | 38.3% | 14.55 cm | 127 | 14.5 cm |
| 0.750 | 4.24 cm | 12.73 cm | 25.46 cm | 8.49 cm | 28.1% | 12.47 cm | 109 | 12.4 cm |

判定（`ClothFoldEvaluator`，两条门合取）：每个粒子离「折好之后它该在的位置」的平均距离 ≤ 7.5 mm，且离目标超过 15 mm 的粒子占比 ≤ 2%（这两条合成一条形态判据）；覆盖格里恰好两层的格占比 ≥ 0.60（结构判据）。目标位置是算出来的：对角线这一边的粒子不动，那一边的粒子沿对角线镜像过去再抬高一个布厚。对照走法 `run.motion=drag` 沿同一条弧线的俯视投影贴桌面拖、不抬，布被推皱，两层率 ≈ 0.2，应判失败；`run.motion=fixed_corner` 无视指令永远折远左角，判定按指令的角算目标位置，折错角每个粒子都不在位，应只在指令恰好是远左角时成功。

**术语。** 远 / 近 = 离机械臂底座远 / 近（x 大 / x 小）；左 / 右 = +y / −y；四个角叫 far_left（远左，基准）、far_right、near_left、near_right。**这四个名字只是几何身份，不进指令**——它们是以机械臂为原点读的，同一句话换个机位就指到别的角上去（§9）。远角 = 抓取点与落点里 x 大的那个（抓 far_* 时是抓取点，抓 near_* 时是落点），手要在桌面高度到它。折痕位置 f = 见上（`goal.fold_fraction`），分母是**半条对角线** 16.97 cm，不是边长 24 cm。可达盘 = 以 `reach.base_xy` (−0.570, 0) 为圆心、`reach.max_hand_dist` 为半径的水平圆。首抽拒绝率 = 1000 个 seed 里第一次抽样就被派生 / 校验拒掉的比例，门 2%（`tests/check_variant_rng.py` 的 `MAX_REJECTION`）；角点 = 连续轴两端 × 离散轴全部取值的组合（`tests/check_variant_corners.py`）。

## 2. 变体轴与派生

| 类 | 叶子 | 抽法 | 基准 | 在场景里改的是什么 / 边界来源 |
|---|---|---|---|---|
| 防捷径离散轴 | `grasp.corner` | Cat{far_left, far_right, near_left, near_right} | far_left | **抓哪个角**。布是正方形、四角形状一样，唯一能知道该抓哪个角的地方是指令 `goal.instruction`（模板 "Fold the {corner} corner of the cloth {extent}."，`ClothFoldLayout.instruction()` 填**该角涂的颜色名**；2026-09-08 之前填的是 `CORNER_WORDS` 的 "far left" 这类方位词，见 §9。派生只写标量叶子，ring_transfer 教训）。折向、落点、弧半径、手腕偏航全部由角的符号对 (±1, ±1) 推出 |
| 防捷径离散轴（视觉） | `cloth.corner_paint.*` 四个叶子 | `distinct_choice`，四色不放回（`keys_of: cloth.palette`） | red / purple / green / yellow | **哪个角涂哪种颜色**。没有任何几何后果，只改布的贴图与指令里那个词。固定不变的话策略可以背下「红 = 远左」，那就等于换了个说法的方位词；重抽之后指令说的颜色只能到画面里去找，指令与画面缺一不可。1000 seed 抽满 4! = 24 个排列，四种颜色各当 232–265 次目标（§9.5） |
| 单调裕度轴 + 指令轴 | `goal.fold_fraction` | Cat{1.000, 0.875, 0.750} | 1.000 | **折到多远**（§1 的表）。折痕从布中心朝被抓的角外移 L(1 − f)，移动的材料、弧半径、步数全部跟着变。同样只有指令说得清（`EXTENT_WORDS` 填 "three quarters of the way to the opposite corner" 这样的词）。下限 0.750 是实测定的，见 §8 |
| 连续布局轴 | `cloth.center_y` | U[−0.030, +0.030] | 0.000 | 布左右平移 ±3 cm。布边最远到 y = 15 cm，离工作区边 30 cm 余量大，不需要派生。`cloth.center: [x, y]` 拆成 `center_x / center_y`（band_untwist 教训：随机器与角点覆盖写不了列表元素） |
| 连续布局轴 | `physical.fold_slack` | U[0.96, 1.00] | 0.98 | 弧半径 ÷ 材料长。手停在离对角 材料长 × (1 − slack) 的地方；0.96 差 6.8 mm。计划文档的下限 0.93 差 11.9 mm，超过主判据的 7.5 mm 平均误差门，oracle 自己就判失败（2026-09-06 算出，用户定为收到 0.96 并加 `slack_within_gate` 行） |
| 连续 → 派生 | `cloth.center_x_frac` → `cloth.center_x` | U[0, 1] **派生** | 1.0 → 0.0402 | 布前后平移。区间 [0.010, min(0.070, 可达盘封顶)]，封顶随抓哪个角、`center_y`、`fold_fraction` 变（下文）。基准 yaml 的固定值 0.040 与派生顶端 0.0402 差 0.2 mm；固定布局不经派生 |
| 固定量 | `cloth.size`、`mesh.cols/rows` 33×33、`particle_size` 0.004、`fold_step_m`、`touch_clearance`、`grasp_qpos`、`attach_radius`、桌面摩擦、`grasp.at: corner`、`grasp.finger_axis: across` | 固定 | | 各有实测事故记录（yaml 注释）；33×33 + 0.004 是唯一实测保序的网格组合；`edge_mid` 实测三条判据都不过；布不能转（网格生成器轴对齐） |

**为什么 `center_x` 不能独立抽。** 抓取点与落点里 x 大的那个（远角），手要在桌面高度到它。基准布局远角离底座 √(73.0² + 12.0²) = 74.0 cm，是本任务一直在抓的点。若 center_x 独立在 [0.010, 0.070] 里抽，center_x = 0.070、center_y = +0.030、抓 far_left 时远角离底座 √(76.0² + 15.0²) = 77.5 cm，没有证据说够得着（离线门负例）。

**怎么算**（`_cloth_fold_geometry.center_x_bounds` + `_far_corner_offset`）：先抽角、`fold_fraction`、`center_y`；远角相对布中心的偏移是——抓 far_\* 角时就是抓取点本身 (±12, ±12) cm，抓 near_\* 角时是落点 (1 − 2f) × 抓取点偏移，也就是 x 偏移 (2f − 1) × 12 cm。可达盘在远角那个 y 上的弦长半宽 = √(R² − y_far²)，R = 0.740；center_x 上限 = 底座 x + 弦长半宽 − 远角的 x 偏移，再与 0.070 取小；center_x = 0.010 + frac × (上限 − 0.010)。写回前转 Python float（OmegaConf 拒收 numpy 标量）。

**`fold_fraction` 只在 near_\* 角上影响这个窗口，而且是放松**：折得越短，落点越靠近布中心、离底座越近。

| 角 | f | center_y | 远角 x 偏移 | y_far | 弦长半宽 | center_x 上限 |
|---|---|---|---|---|---|---|
| far_left（基准） | 1.00 | 0 | 12.0 cm | 12.0 cm | 73.02 | **4.02 cm** |
| far_left | 1.00 | +3 | 12.0 | 15.0 | 72.46 | 3.46 |
| near_left | 1.00 | 0 | 12.0 | −12.0 | 73.02 | 4.02 |
| near_left | 0.75 | 0 | 6.0 | −6.0 | 73.76 | **6.76 → 封到 7.00** |

96 个角点的窗口宽 2.5–6.0 cm，都大于连续轴 2 cm 的抖动下限（计划文档 §2.3）。

两个字面量副本进 task yaml（角点门裸加载 task yaml，`${common…}` 解析不了）：`workspace.x / y / z`、`reach.base_xy`；`ClothFoldSceneBuilder.build` 断言 `workspace` 与 common 相等。

**变体前修的三处执行链。**

1. **判定器的占用网格锚在世界原点。** `ClothFoldEvaluator.classify` 原来调 `layer_report` / `occupied_cells` / `fold_target_cells` / `footprint_iou` 时不传 `origin`，8 mm 格子的相位随布的位置变（cloth_unpleat 09-05 同一缺陷：同一物理形状平移 7.5 格，三层格数 24 → 6），而 `two_layer_frac` 是门。改为锚在静置点云的最小角，四个调用同一个锚点。固定布局复跑读数不变量级（§5.1）。
2. **Layout 只会一个角。** `_grasp_offset()` 原来写死远左角；改为按 `grasp.corner` 取符号对，其余量全部由这个偏移与 `fold_fraction` 推出。`ClothFoldLayout.origin` 加零默认值（角点门从 task cfg 单独建 Layout）。
3. **手腕朝向。** 四个角的折向方位角是 +45° / −45° / +135° / −135°；加 `grasp.finger_axis: across | arm_default`（同 cloth_unpleat 的键），默认 across，near_* 角出现位置误差再切。

## 3. `checks()` 四行

纯函数在 `topogym/tasks/deformation/_cloth_fold_geometry.py`（numpy only，不 import Genesis），只吃 task 配置，任务坐标系；`ClothFoldLayout.checks()` 转发，`validate()` 任一行不 ok 抛 `ValueError`；建场景、随机化拒绝、离线门、角点门、demo 启动打印共用。

| 行 | 读数 | 门 | 基准 | 96 角点最紧 |
|---|---|---|---|---|
| `far_corner_reach` | 远角到 `reach.base_xy` 的水平距离 | ≤ `reach.max_hand_dist` 0.740 | 0.7398 | 0.7400（center_x 派生取窗口顶端，构造取等） |
| `cloth_in_workspace` | 出生布四角到工作区盒 x / y 边的最小距离 | ≥ 0.040 | 0.0900 | 0.0600（center_y −0.030、center_x 顶端） |
| `apex_below_workspace_top` | 最高点手的高度 = `cloth.z` + 弧半径 + `touch_clearance` | ≤ 0.40 | 0.1763 | 0.1797（f 1.0、slack 1.0） |
| `slack_within_gate` | 材料长 × (1 − `fold_slack`) = 手停在离折痕对面多远 | ≤ `success.particle_error_mean_max` 0.0075 | 0.0034 | 0.0068（f 1.0、slack 0.96） |

**为什么是四行不是五行。** 原来还有一行 `attach_disc_has_cloth`（半边长 − `grasp.inset` ≥ `attach_radius` 0.018），守的是「捏取点往里退太多，附着盘会有一部分悬在布外」。`grasp.inset` 在 2026-09-07 删掉之后（§8），捏取点恒在角尖，这一行恒为 0.120 ≥ 0.018，永远不可能挂——是死行，一并删掉。新轴 `fold_fraction` 在 [0.75, 1.0] 内不触发任何一行：f 变小时弧半径、最高点、松紧差距全部变小，`cloth_in_workspace` 只看出生布不看折法，`far_corner_reach` 对 near_\* 角还会放松。不为它硬造一行凑数。

`reach.max_hand_dist` 0.740 是**新键、是假设**，与 cloth_unpleat / cloth_unroll 的 0.665 不是一个口径：那两个任务在这个距离上还要贴桌面拉 6–10 cm，这里手到远角只是抓或放，之后就沿弧线往折痕上方走。近角离底座最近 46.9 cm（center_x 0.010），仓库里没有手在桌面高度靠这么近的实测，不加行、先跑角点（§5.2）。

## 4. 离线实测（2026-09-08，换轴后）

- `python tests/check_cloth_fold_geometry.py` PASS：判据六种末态分得开（见 §5.5 的门重标）；「变体包络」段——四行基准全过、`center_x_frac` 1.0 → 窗口顶端 0.0402、四角材料长相等、`drag` 俯视同路贴桌不抬、`fixed_corner` 三个非基准角都按 far_left 规划、**`fixed_fold` 指令折 0.9 / 0.8 时仍按角对角规划且抓的角不变、落点差 2L(1−f)**；96 角点派生区间非空、四行全过，最紧 `far_corner_reach` 余量 0（构造取等）、`slack_within_gate` 0.0007；96 个 center_x 窗口宽 0.0246–0.0600；三负例各被该管的行拒（松紧 0.93 挂 `slack_within_gate`、布最靠外挂 `far_corner_reach`、**折痕位置 0.6 没有对应措辞被 `fold_fraction` 拒**）；两条折痕位置的几何恒等式（材料长 / 弧半径 / 最高点逐档下降；f=1.0 落点是对角角尖、f=0.8 落点离中心 0.6 L）。
- `python -B tests/check_variant_rng.py` cloth_fold 段 PASS：1000 seed 抽样分布 far_left 234 / far_right 268 / near_left 238 / near_right 260，`fold_fraction` 1.0 / 0.9 / 0.8 = 345 / 311 / 344；最大远角距离 0.7400；center_x 窗口在 782 个 seed 里被可达盘封顶；**首抽拒绝率 0.000**（门 0.02）。另加一条断言：「+x 那个点必须也是离底座最远的那个」1000 seed 全过——原来的「远角严格在 +x 侧」在折得短的 near_\* 角上会取等（f 小到落点落回布中心时），换成了这条真正该守的。
- `python -B tests/check_variant_corners.py --task cloth_fold`：**96 角点 96 可行、0 拒绝**，经 Hydra compose 复现的四行读数与离线一致。
- `check_configs_compose.py`、`check_demo_configs.py` PASS。

## 5. GPU 实测（4090，2026-09-07 – 09-08，换轴后全量重跑）

09-06 那一轮的角点结果**全部作废**：角点集合的构成从「四角 × 三档内缩量」变成「四角 × 三档折痕位置」，不是同一批配置。

### 5.1 固定布局基准（`runs/cloth_fold_variation/20260908_final/fixed.log`）

最终配置（f = 1.0、结构判据门 0.80）：`folded=True`、`diverged=False`、平均误差 **3.31 mm**、偏离比例 **0.000**、两层率 **0.966**、`gates=all_pass`。指令行 `'Fold the far left corner of the cloth over onto the opposite corner.'`。f = 1.0 时折线就是另一条对角线，几何与 09-06 的基准逐位相同，读数差别来自结构判据换了分母（旧口径同一格是 480/517 = 0.928）。

### 5.2 seed 0–9 四组（`runs/cloth_fold_variation/20260907_f109/`）

| 组 | 结果 | 预期 | |
|---|---|---|---|
| oracle | **10 / 10 折成** | 全过 | ✓ |
| drag | **10 / 10 判失败** | 全失败 | ✓ |
| fixed_corner | **2 / 10 成功** | = 抽到 far_left 的 seed 数 **2** | ✓ |
| fixed_fold | **5 / 10 成功** | = 抽到 f = 1.0 的 seed 数 **5** | ✓ |

`fixed_fold` 这一行是**新轴的证明**：一个无视折痕位置、永远角对角折的策略，只在指令恰好说角对角时才对。被它取代的 `grasp.inset` 过不了这条检验——无视 inset、永远捏角尖反而得 100%（§8）。

### 5.3 96 角点四组（`runs/cloth_fold_corners/20260907_f109/`，384 格，约 2.3 h）

| 组 | 折成 | 预期 | |
|---|---|---|---|
| oracle | **96 / 96** | 全过 | ✓ |
| fixed_fold | **32 / 96** | = f = 1.0 的格数 **32** | ✓ |
| fixed_corner | **24 / 96** | = far_left 的格数 **24** | ✓ |
| drag | **0 / 96** | 全失败 | ✓ |

四组逐格对上预期数，没有一格例外。

### 5.4 oracle 按折痕位置分：余量单调收窄

判据里真正会挂的是**单点容差 15 mm**（`particle_off_target_m`），所以「移动那半布的平均误差」离 15 mm 还有多远，就是这条轴的余量。

| f | 32 格 | 移动半误差 中位 / 最大 | 余量（15 − 最大） | 平均误差 中位 / 最大（门 7.5） | 两层率 最小 / 中位（门 0.80） |
|---|---|---|---|---|---|
| 1.0 | 32 折成 | 4.76 / **7.43** | **7.57 mm** | 3.75 / 5.37 | 0.876 / 0.938 |
| 0.9 | 32 折成 | 2.92 / **7.95** | **7.05 mm** | 2.85 / 5.12 | 0.843 / 0.942 |
| 0.8 | 32 折成 | 7.88 / **13.02** | **1.98 mm** | 3.54 / 5.40 | 0.871 / 0.920 |

余量 7.57 → 7.05 → 1.98 单调收窄，这是单调裕度轴该有的形状。**平均误差三档基本持平**（3.75 / 2.85 / 3.54）——折得短的时候动的材料少，整块布的平均误差反而不涨，涨的是移动那半布的局部误差。所以 §4.4 划档的统计量 `s` 应取**移动半误差**或**折痕偏移**，不是平均误差。

**下限为什么停在 0.8。** 更小的档实测过：

| f | 最差格实测（far_right、center_y +0.03、slack 1.0、center_x 0.01） | 96 角点最大 |
|---|---|---|
| 0.900 | 6.41 mm（余量 8.59） | 7.95（余量 7.05） |
| 0.875 | 10.14 mm（余量 4.86） | 10.13（余量 4.87） |
| 0.800 | 12.97 mm（余量 2.03） | 13.02（余量 1.98） |
| 0.750 | 14.13 mm（余量 0.87） | 14.28（余量 0.72） |
| 0.500 | — | **判失败**，偏离比例 0.122 |

0.75 太贴门：那一轮 seed 0–9 里 far_right 那格实测 **14.47 mm 判失败**，比 96 角点的最大值 14.28 还高——**角点取的是轴端点，并不覆盖这个量的最坏情况**（那个 seed 的 `center_x` 落在区间内部）。这是这次部署晒出来的一条通用教训。

**f = 0.5 记为 oracle 胜任边界**（计划文档 §4.3 的口径），不进包络。三次复跑逐位相同（偏离比例 0.122 / 0.122 / 0.122），失败机制单一：折痕落偏 15.3 mm → 整片镜像过去的布偏约 30 mm → 移动的那 12.5% 粒子几乎全部越过 15 mm 容差（0.122 ≈ 移动粒子占比 0.125）。物理上讲得通：角对角折时折痕被两个没动的角钉住、几何自己对位；折短了没有东西钉它，折痕落在哪全看放走多少材料——这正是这个任务要求预测的形变量，也是这条轴取代 `grasp.inset` 的理由。

### 5.5 结构判据：换分母 + 门 0.60 → 0.80

判定器把桌面切成 8 mm 格子，数每格恰好两层的格。原来的读数是**裸比值**「恰好两层的格 ÷ 有布的格」，它默认折法是角对角对折：

| f | 移动的粒子 | 预测两层区 | 折好后总覆盖 | 裸比值的几何上限 |
|---|---|---|---|---|
| 1.0 | 2111 / 4225 | 466 格 | 467 格 | ≈ 1.00 |
| 0.9 | 1711 / 4225 | 394 格 | 555 格 | 0.71 |
| 0.8 | 1378 / 4225 | 311 格 | 636 格 | **0.49** |

f = 0.8 的上限 0.49 **低于原来 0.60 的门**——一个折得完美的短折也过不了，门在惩罚「折得短」而不是「折得差」。改成按**预测两层区**（移动那半布的目标位置落进的格集，`fold_targets` 本来就算了）归一化，三档上限都是 1.0，问的是同一个问题：该变两层的地方有多少真的变了。

`layer_report` 因此追加一个返回键 `two_layer_cell_keys`（哪些格是两层），**只加不改**——cloth_unpleat / cloth_unroll 用的现有键含义不变，两个任务各跑一格固定布局回归确认（§5.7）。

换分母之后 drag 那一侧整体抬高（它把布推皱，皱起来的叠合恰好落在预测两层区里，而分母不再是被推得摊开的整块覆盖区），旧门失效：

| 组 | n | 最小 | 中位 | 最大 |
|---|---|---|---|---|
| oracle | 96 | **0.843** | 0.931 | 0.994 |
| drag | 96 | 0.000 | 0.195 | **0.693** |

加上 seed 组（drag 最高 0.755、oracle 最低 0.857），实际边界是 **drag ≤ 0.755 < oracle ≥ 0.843**。门提到 **0.80**，两侧各留约 0.045。按日志重判 384 格 + 40 格：

| 组 | 旧门 0.60 折成 | 新门 0.80 折成 | 结构判据**独立**否决：旧 → 新 |
|---|---|---|---|
| oracle | 96 | **96**（0 格改判、0 格误杀） | 0 / 96 → 0 / 96 |
| drag | 0 | 0 | 92 / 96 → **96 / 96** |
| fixed_corner | 24 | 24 | 67 / 96 → **72 / 96** |
| fixed_fold | 32 | 32 | 21 / 96 → **45 / 96** |

**没有一格改判**（drag 本来就被距离那两条挂掉），提门恢复的是这条判据自己的作用——分类学合同 4.1 要求「结构指标 + 形态指标的合取」，门若对某条错法完全失效，合取就只剩一条腿。`fixed_fold` 的 21 → 45 尤其说明问题：折错距离之后，该变两层的那片区域有一半没变成两层，旧口径读不出来。

余量要老实说：0.80 两侧各约 0.045，比旧口径（正确 0.845 / 最好的错误 0.202，两侧各差一倍）紧得多。多种子跑完再看。

### 5.6 发散守卫：96 格里 1 格（c030），已知缺口

`oracle_c030`（far_right、f = 1.0、center_y +0.03、slack 1.0、center_x_frac 0.0）：`folded=True` 但 `diverged=True`，单步位移 **97.2 mm** 越过重力预算 54.7 mm（1.8 倍），发生在 `arc_02`——12 段弧线的第二段、手在 z 方向还落后 50–64 mm 正在追上来的那一下。

这一格**不是真发散**：`parked_outside=0`（没有材料跑丢）、无 NaN、`carry_stretch_mean` 1.021（整块布平均只拉伸 2%）、末态平均误差 3.98 mm、偏离比例 0.000、两层率 0.933、**最大层数 2**——折得比中位数还好。`carry_stretch_max` 17.63 意味着某一条边被拉到 66 mm（静止间距 3.75 mm），而夹爪附着圈的正常局部峰值是 1.57 倍 = 5.9 mm。按记录的判读，是**一个被夹爪刚性绑住的粒子在手加速那一下被拽离约束、下一步投影又拉了回来**。

时间与空间尺度：一步 10 ms，整格约 640 步；录像 30 fps 时**一帧 ≈ 3.3 步**。所以画面上是布面某处冒出一根约 6 cm 的针尖状毛刺、持续不到一帧，然后收回去。对照真发散的画面：布炸开拉成面条飞出画面、或者材料被求解器停放到 10 m 外凭空消失（`parked_outside > 0`）、或者 NaN 整块消失——那些**看录像一眼就知道坏了**，而且末态是废的。

**处置：不改守卫口径，保守丢弃。** 现在的行为已经是想要的——守卫判的是「这次不算一次尝试」，episode 既不作正样本也不作负样本进数据集。理由：

- 规模小。96 格 oracle 里 1 格（约 1%），seed 0–9 一格没触发。
- 分不出「自愈的单粒子跳变」和「真炸了」需要改 `ClothFoldWatch`，那是**三个布任务共用**的类，cloth_unpleat（192 角点）与 cloth_unroll（96 角点）要一起回归，约 2 h GPU；还要新加一个末态 `stretch_max` 读数，而末态这个量**被折痕主导**（一个几何完美的折叠读数就是 1.46），门槛要重新标。
- 代价 2 h + 一条要重标的新读数，收益 1%。

**已知缺口，记在这里**：c030 型（单粒子跳变、自愈、末态判据全过）会被记为发散而丢弃，约 1/96。宁可丢也不放行——万一真是物理崩溃，放进数据集的危害更大。等目标 2 第 2 级的 50 seed sweep 跑完，看这类触发在 13 个任务上的总量再决定要不要改口径。

c030 同一格三次都触发，数值几乎一样（97.2 / 98.3 / 97.2 mm）：**与布局有关、可复现**，不是随机噪声。

### 5.7 共用判定器的回归（`runs/cloth_fold_variation/20260908_final/`）

`layer_report` 加了返回键但没改现有键，两个共用它的布任务各跑一格固定布局：

- cloth_unpleat：`unpleated=True`、`diverged=False`、`peak_mm=2.00`、附着 64 个粒子、跟随误差 0.3 mm
- cloth_unroll：`unrolled=True`、`diverged=False`、`torn=False`、`contact_ok=True`、`penetration_mm=-0.00`

## 6. 文件集

| 文件 | 改动 |
|---|---|
| `configs/task_configs/cloth_fold_topogym_tabletop_v1.yaml` | `center` 拆键 + `center_x_frac`、`grasp.corner`、`grasp.finger_axis`、`goal.instruction` 双占位、`goal.fold_fraction`、`reach:`、`workspace:`、末尾 `variation:` 块（09-07 删 `grasp.inset`、加 `goal.fold_fraction`；09-08 加 `cloth.palette`、`cloth.corner_paint`、`texture.corner_size` 与颜色排列轴） |
| `topogym/world/textures.py` | `fabric_weave` 加 `corner_colors` / `corner_size_m` 与 `_paint_corners`（09-08）：贴图四角各盖一块颜色，与 `pattern` 正交，条纹保留 |
| `configs/run_configs/cloth_fold.yaml` | `motion`、`randomize_layout / difficulty / variant_id` |
| `topogym/tasks/deformation/_cloth_fold_geometry.py` | 09-08 加 `corner_colour_name` / `corner_colour_grid`（指令里那个词、贴图四角的颜色，都从 `CORNER_SIGNS` 读出，不另建第二张表）。原有：角符号表、`EXTENT_WORDS`、`fold_fraction`、折线三式（`fold_point_task / fold_normal_task / fold_target_task`）、`material_distance`、远角与 `_far_corner_offset`、`center_x_bounds / center_x_from_frac`、四行 `cloth_fold_checks` |
| `topogym/tasks/deformation/cloth_fold.py` | Layout：`origin` 默认零、`corner` / `corner_signs`、`_grasp_offset` 四角、`fold_fraction`、`with_corner` / `with_fold_fraction`、`instruction` 双占位、折线三式随 f、`grasp_yaw` 按 `finger_axis`、`checks / validate`；builder 建场景前 `validate` + 字面量断言；模块级 `derive_task_cfg / validate_task_cfg` |
| `topogym/verification/cloth_fold_verifier.py` | `classify` 占用网格锚在静置点云最小角；`fold_target_cells / footprint_iou` 透传 `origin`；`layer_report` 追加 `two_layer_cell_keys`（只加不改）；`two_layer_frac` 改成按预测两层区归一化（§3 与 §5） |
| `topogym/planning/cloth_fold_planner.py` | `MOTIONS`、`FIXED_CORNER` / `FIXED_FRACTION`、`execution_layout`、`arc_point(lifted=)`、`fold_waypoints(motion=)`、`plan_cloth_fold(motion=)` |
| `demos/deformation/cloth_fold_physical_demo.py`（发散守卫） | `ClothFoldWatch` 传 `max_speed=float("inf")`：那条写死的 3 m/s 在本任务上是 30 mm/步，比类自己按重力推导的 49–55 mm/步紧 1.6–1.8 倍，与类文档论证的设计矛盾（09-07，§5） |
| `demos/deformation/cloth_fold_physical_demo.py` | `randomize_task_cfg` 接线、`variant` / `checks` / `instruction` 行、`run.motion` 分支（执行用 `hand`、判定用 `layout`）、result 行加 `motion / corner / executed`、对照走法退出码 |
| `tests/check_cloth_fold_geometry.py` | 新键；「变体包络」段（四行、派生还原、四角对称、三种对照走法、96 角点、三负例、折痕位置的两条几何恒等式） |
| `tests/check_variant_rng.py`、`tests/check_variant_corners.py` | cloth_fold 任务段 / `TASKS` 条目 |
| `bash_scripts/tests/cloth_fold_variation_sweep.sh` | 新：oracle（含录像）+ drag + fixed_corner + fixed_fold 四组 |
| `bash_scripts/tests/variant_corners_sweep.sh` | `cloth_fold)` 分支 |

## 7. 09-06 那三项决定的收口（2026-09-08）

| # | 09-06 的问题 | 结论 |
|---|---|---|
| 1 | `grasp.inset` 0.020 档 24/32，是收窄档位、接受 75%、还是放宽门？ | **三个选项都不用了：整条轴删掉，换成折痕位置**（§8）。原来那 8 格失败是判据与几何失配，不是难度 |
| 2 | `fold_slack` 1.00 这一端要不要收？ | **不收**。09-06 的证据是「slack 1.00 的 48 格 42 折成」，但失败全部同时落在 inset 0.020 档，是 inset 借给它的。换轴后 96 角点 oracle 96/96，slack 两端各 48 格全过，`slack_within_gate` 最紧余量 0.0007（f 1.0、slack 0.96）。这条轴自己不产生失败 |
| 3 | 发散守卫的口径 | **不改，保守丢弃**。理由与已知缺口见 §5.6 |

## 8. 换单调裕度轴：`grasp.inset` → `goal.fold_fraction`（2026-09-07）

### 8.1 为什么删 inset

`grasp.inset` 是捏取点从角尖沿两条边各往里退多少（0 / 10 / 20 mm），部署时定为单调裕度轴。两轮 96 角点实测证明它不称职。

**一、无视它反而更好。** 一条轴是不是真的要求了什么，可操作的判据是：**能不能写一个无视它的对照策略，而它会失败**（`fixed_corner` 对 `grasp.corner` 就是这样，72 格 0 成功）。inset 过不了：

```
inset 0      32/32 折成      inset 0.010  32/32 折成      inset 0.020  24/32 · 23/32（两轮）
```

一个「无视指令要求的内缩量、永远捏在角尖」的对照会得 **100%**，比照着做还高。你无视它就得分更高的轴，不可能是难度轴。

**二、它产生的机制是判据失配，不是形变预测的负担。** 失败全部挂在 `particle_off_target_frac` 上；判定器把目标位算成「沿折线镜像」，而捏取点外那块腿长 2 cm 的三角形加附着盘边缘一圈，本来就不在镜像位上。证据是**过了门的格**：0.020 档过门格的偏离比例中位也有 0.016，门是 0.02——整档贴着门走，不是个别格坏。

**三、它产生的是方差不是难度。** 09-06 与 09-07 两轮同配置跑，96 格里 **9 格结论翻转**。另外查过一个可疑现象：inset 0.020 时 `center_y = +0.03` 侧 8/16 失败、`−0.03` 侧 1/16，看着像有方向的缺陷。查下来不是——

- 三区分解里**静止半误差两侧完全相同**（3.86 vs 3.84），排除「布被差别对待地拖动」
- 执行读数两侧也相同（手跟随误差 50.7 vs 50.9 mm、臂位置误差 57.54 vs 57.51 mm），排除机械臂
- 16 对镜像格里 11 对同向（符号检验单侧 p = 0.029，看着显著），但**对照档把它推翻了**：inset 0.010 那一档方向是反的（9 对偏向 +0.03，p = 0.21）
- 均值差 1.9 倍，中位数只差 1.4 倍，去掉最大三格后 1.65 倍——被少数极端格拖出来的

结论：**0.020 档是门线附近的高方差区，不是有方向的缺陷**。这也意味着不用回头查 cloth_unpleat / cloth_unroll 的镜像轴。

一条只让判据结果变随机的轴，对录数据尤其糟糕：录出来的「成功」「失败」标签不对应任何策略上的差别。

### 8.2 为什么是折痕位置

这个任务要求预测的形变量写在 `fold_radius()` 的注释里：**捏取点只能在一个以折线为轴的圆上走，它和那条线之间连着固定长度的材料；走远了是在拉布，走近了布会垂到桌上被横着拖走。** 折痕位置直接改这个量——折线平移，移动的材料、弧半径、步数全跟着变（§1 的表）。

而且它过得了 §8.1 那条检验：`fixed_fold` 对照无视它、永远角对角折，**32/96 成功，逐格等于 f = 1.0 的格数**（§5.3）。

判定器早就为此留了口子：`fold_targets` / `fold_target_cells` / `crease_indices` / `crease_report` / `anchor_shift` 全部把折线当参数收，`fold_target_cells` 的注释写明「也适用于不过中心的折线」。唯一把对角线钉死的是 `ClothFoldLayout.fold_point()` 一行 `return self.cloth_centre()`。

### 8.3 定档过程

档位从计划里写的 {1.0, 0.75, 0.5} 走到 {1.0, 0.9, 0.8}，每一步都有实测（§5.4 的两张表）：0.5 判失败、0.667 与 0.75 骑在门线上（0.75 在 seed 组掉了一格）、0.875 与 0.9 有余量。最终取 **{1.0, 0.9, 0.8}**，最难档余量 1.98 mm。

**上限不取大于 1**：翻过去的布会越过对角角尖落到光桌面上，而 `fold_targets` 给每个移动粒子一律加一个布厚（`fold_thickness` = `particle_size` 4 mm），悬空那条带就有 4 mm 系统偏差，对 7.5 mm 的平均误差门是致命的。

### 8.4 跟着变的三处

1. **`checks()` 五行 → 四行**：`attach_disc_has_cloth`（半边长 − inset ≥ 附着盘半径）随 inset 一起删——inset 没了它恒为 0.120 ≥ 0.018，是死行。不为新轴硬造一行凑数：f 在 [0.8, 1.0] 内不触发任何一行（弧半径、最高点、松紧差距全部随 f 变小，`far_corner_reach` 对 near_\* 角还会放松）。
2. **指令模板加第二个占位符**：`"Fold the {corner} corner of the cloth {extent}."`，`EXTENT_WORDS` 填 "nine tenths of the way to the opposite corner" 这样的词。布是纯色正方形，画面里没有线索能说明折痕该落在哪，和抓哪个角一样只能由句子说清。`fold_fraction` 因此**同时是防捷径指令轴和单调裕度轴**。
3. **结构判据换分母 + 提门**：见 §5.5。

### 8.5 这次晒出来的两条通用教训

1. **角点取的是轴端点，并不覆盖所有量的最坏情况。** f = 0.75 那一轮，96 角点最大移动半误差 14.28 mm 全过，而 seed 0–9 里 far_right 那格实测 14.47 mm 判失败——那个 seed 的 `center_x` 落在区间内部。对这类「连续轴组合出来的量」，角点门过了不等于包络内都过。
2. **一条轴要当难度统计量，先过「无视它的对照会不会失败」这一关。** 这是 `grasp.inset` 被删的直接理由，也是 `goal.fold_fraction` 被接受的直接证据。


## 9. 指令改用颜色指角（2026-09-08）

### 9.1 为什么方位词不成立

指令原来说 "Fold the **far left** corner of the cloth …"。这四个词（远 / 近 × 左 / 右）是以机械臂底座为原点定义的：far = +x、left = +y。问题不在定义不清楚，在于**读它的人和策略看的是相机，不是底座**。

同一个 far_left 角，在三个已有机位上分别出现在画面的：俯视机位（`topdown`，up = +x）左上角；`front` 机位（RoboMME 那个，也是数据集录的那一路）**右下角**；`base_camera` 右下角。也就是说，一张 `front` 机位的图配上 "far left"，画面里那个角在右下——策略没有任何办法把这两件事对上，除非它先知道相机的外参。09-08 会上 Qineng 的原话是这是「非常 vague、非常不好的描述」。

改法：**四个角各涂一块颜色，指令说颜色**。"the red corner" 在任何机位下都指同一个角。

### 9.2 颜色↔角的对应每个 episode 重抽

固定对应（红永远是远左角）只解决了「人读指令」这一半：策略仍然可以背下「红 = (+x, +y)」，那就等于把方位词换了个说法。所以四个角的颜色是一条 `distinct_choice` 轴，四色不放回地抽一个排列（1000 seed 抽满 4! = 24 个排列）。这之后：

- 只读指令：知道要红色的角，不知道红色在哪 → 只能瞎猜，1/4；
- 只看画面：四个角都涂着色，看不出该折哪个 → 1/4；
- 两样都读：唯一确定。

对照组不用新加。既有的 `fixed_corner`（无视指令永远折远左角）在颜色化之后仍然是 1/4 的预期；再加一条「永远折红色那个角」与它同分，区分不出来。

### 9.3 颜色画在哪、怎么画

布的表面细节只有一个通道：diffuse 贴图（光栅化器丢掉粗糙度 / 法线 / 自发光，光追在本安装不可用）。所以色块画进贴图里，不是另加实体：`fabric_weave` 新增 `corner_colors`（2×2 嵌套，按 `[v][u]` 索引，0 = 该轴低端）与 `corner_size_m`，在底色算完之后、织纹明暗乘上去之前盖四块方形。织纹的明暗是逐像素的一个**标量**倍数，所以色块保留织物质感、色相不变——离线门就是靠这一点比方向余弦而不比亮度。

**色块 6 cm**（布边 24 cm 的四分之一）。小于 3 cm 在 512×512 斜视机位下不到 10 个像素、读不出颜色；大于 8 cm 四块连成一片、不再读作「角上的标记」。

**贴图与布的对应**（这是本次唯一需要实测的一条）。布的控制网格每个顶点写了 UV：`u = 列 /(列数−1)` 沿 +x、`v = 行 /(行数−1)` 沿 +y，一张图正好铺满整块布。所以 u 最大端是远（+x）边、v 最大端是左（+y）边。但**渲染链从图像下缘往上读 v**（trimesh 的 `uv_to_color`：`y = (1 − v) × (height − 1)`），v = 0 落在数组的最后一行而不是第一行。模块里其余的东西（织纹、条纹）在 v 上对称，所以这是第一处这个翻转看得见的地方，`_paint_corners` 在一处处理掉。

实测确认（09-08，`topdown` / `front` / `base_camera` 三机位各建一格）：绿色抓取标记落在指令说的那个颜色块上，四个角逐个对上。

**调色板去掉了蓝与橙。** 首轮用 red / blue / green / yellow，实测截图里蓝色块 [0.15, 0.45, 0.85] 与布的蓝条纹 [0.20, 0.33, 0.55] 在俯视 768×768 下读成「一条更宽的条纹」而不是一块角标；换成紫 [0.58, 0.25, 0.75]。橙 [0.88, 0.55, 0.10] 夹在红与黄之间，三者同场最难分，也不用。四色取值照 linkbar 的六色调色板（`zones.colors`），少维护一份色表。

### 9.4 一条虚惊：inspect demo 的画面不是 episode 的出生态

量四个角在各机位上的可见像素数时，`near_left` 那个角在 `front` / `base_camera` / `oblique` / `topdown` 四个固定机位上全是 0–7 像素，只有腕部相机看得见（223 像素）——看上去是「四分之一的 episode 指令说的颜色在第一帧里看不见」。

根因是量错了对象：`cloth_fold_inspect_demo` 不建控制器，机械臂停在 MJCF 的中性姿态（Genesis 自己也会警告 `qpos0 exceeds joint limits`），那个姿态正好摊在布上。真实 episode 走 `initialize_franka_controller` → `reset_home()`，机械臂收到 RoboMME 的确定性 home 位姿之后**四个角全部可见**：

| 阶段 | front 机位四角的像素数（far_left / far_right / near_left / near_right） |
|---|---|
| 建完场景、未 reset（= inspect demo 的画面） | 2782 / 2801 / **1** / 1422 |
| `reset_home()` 之后（= episode 第一帧） | 2781 / 2829 / **1419** / 1422 |

结论：没有遮挡问题。记在这里是因为下次用 inspect demo 判断「画面上看不看得见某个东西」时会再踩一次——那个 demo 的机械臂姿态不是 episode 的姿态。

### 9.5 实测

- 离线门 `tests/check_variant_rng.py` 的 cloth_fold 段：1000 seed 首抽拒绝率 **0.000**（门 0.02）；四种颜色各当目标 red 242 / green 232 / yellow 265 / purple 261 次；**24 个排列全部抽到**。
- 角点门 `tests/check_variant_corners.py --task cloth_fold`：仍是 **96 个角点、96 个可行、0 拒**。角点门对 `distinct_choice` 的规定是固定取前 `len(paths)` 个键，正合适——颜色分配没有任何几何后果，要守的是「指令里的词 = 该角涂的颜色」，那条在几何离线门里。
- 几何离线门 `tests/check_cloth_fold_geometry.py`：新增一段走完整条链（`grasp.corner` → 角尖的 uv → 贴图像素 → 颜色 → 指令里的词），四个角的方向余弦都是 1.0000；另加「四角四色互不相同」「换一个排列指令词跟着换」两条。
- GPU seed 0–9 四组（`runs/cloth_fold_variation/20260908_colour/`）：**oracle 10/10**、
  `drag` 10/10 判失败（两层率 0.000–0.469）、`fixed_corner` **2/10 成功 = 抽到 far_left 的格数 2**、
  `fixed_fold` **5/10 成功 = 抽到 f = 1.00 的格数 5**——两条对照都逐格对上预期，换指令词没有松动任何一条。
  oracle 的粒子平均偏离 3.04–5.89 mm（门 7.5），两层率 0.871–0.987（门 0.80）。
  贴图仍然到得了渲染器（`texture ok(960, 960, 4)`）。
- **同一个颜色词在不同 seed 上指不同的角**，这是这条轴要的性质：seed 0 的 red 是 near_right、
  seed 2 的 red 是 near_left、seed 7 的 red 是 far_left。只背「红 = 某个方位」的策略在这十格上会错八格。
