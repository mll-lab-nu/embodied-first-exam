# 变体参数轴的白话说明

> 日期：2026-08-28
> 配套：`variation_and_difficulty_plan_zh.md`（参数路径、包络数值、校验函数以该文档为准）、
> `../../progress/TopoGym_变体参数轴表.xlsx`（逐轴明细）。
> 本文只用「物体 + 度量」的说法描述各轴，不写变量名。

---

## 1. 轴的四类

与 `variation_and_difficulty_plan_zh.md` §2.1 的对应：A 实例轴 = 本文的防捷径离散轴 + 单调裕度轴；B 布局轴 = 连续布局轴；C、D 同名。

| 类别 | 一句话 | 例子 |
| --- | --- | --- |
| 防捷径离散轴 | 每个 episode 随机抽一个离散值，它决定「该做什么」，而这个信息只能从指令或场景里一个必须读的线索得到。不读它、只背固定动作的策略，成功率被固定在瞎猜水平。取值之间没有难易。 | 绕柱方向顺/逆；死路在左/右；目标区是哪种颜色 |
| 单调裕度轴 | 每个 episode 随机抽一个离散档；取值有序，且 oracle 完成任务所需的余量（净空、时间窗、行程、材料存量）随取值单调变化。按 3–5 档抽；是划难度档的首选依据，但档位与难度的对应等实测后定。 | 见第 2 节 |
| 连续布局轴 | 在一个允许区间内连续抽的几何量（位置、朝向、小尺寸）；oracle 从场景读回后自动适应。作用是让策略学位置泛化，而不是背坐标。 | 柱子在桌上平移几厘米 |
| 派生量 / 固定量 | 派生量随上面三类重算（绳长、出生点、抬升高度）；固定量有实测事故记录，不动（粒径、接触距离、摩擦、步长）。 | — |

## 2. 逐任务的单调裕度轴

| 任务 | 单调裕度轴 | 三档 | 为什么越往右越紧 |
| --- | --- | --- | --- |
| rope_winding | **绳要绕柱子的圈数** | 1 圈 / 2 圈 / 3 圈 | 圈数多，绳要更长、螺旋堆得更高、手臂绕的路更长 |
| rope_unwinding | **出生时绳已经绕在柱上的圈数** | 1 / 2 / 3 | 同上，反着解 |
| ring_transfer | **走线柱的高度** | 8.5 / 10 / 11.5 cm | 柱越高，环要拎得越高才能越过挡头，绳拉得越紧 |
| bar_through_hole | **面板上六角孔的对边距**（杆是 18 mm） | 38 / 34 / 31 mm | 孔越小，杆每边的余量从 10 mm 缩到 6.5 mm，稍歪就卡 |
| swap_crossing_sign | **两根绳平行时的间距** | 9.5 / 8 / 6.5 cm | 越近，抓一根越容易碰到另一根，「分开够远」越难达到 |
| unlink_c_ring | **C 环缺口的张角** | 28° / 24.5° / 21.5° | 缺口越窄，穿过圆环管身时每边余量从 4.3 mm 缩到 1.3 mm |
| band_untwist | **8 字开口那一叶的大小**（半径） | 4 / 5.2 / 6.5 cm | 叶越大，交叉点到绳头越远，整股要抬得越高才能跨过去 |
| gate_cage_ball | **球滚动的速度** | 8 / 11 / 13 cm/s | 球越快，从过闸口到必须落闸的时间窗越短 |
| diverter_route_ball | **活路出口有没有目标垫** | 有 / 无 | 无垫时画面看不出该去哪，只能读指令 |
| linkbar_rotate_to_zone | **两块颜色区离横梁初始方向的远近差** | 相差 ≥20° / 10–20° / ≤10° | 两区离得一样远时，「转向最近那块」这个偷懒办法就变成抛硬币。2026-09-01 起两区在固定导轨上自由放置，可同侧、可相邻 |
| cloth_fold | **捏取点离布角尖的距离** | 0 / 1 / 2 cm | 往里捏得越多，角尖越容易耷拉，折边越不齐 |
| cloth_unpleat | **布带上那道褶叠进去的宽度** | 3.5 / 3 / 2.4 cm | 褶越窄，「拉平了」和「褶塌了」两种读数越难分开 |
| cloth_unroll | **布带卷在杆上的圈数** | 1 / 1.25 / 1.44 圈 | 卷得多，要拉的距离和存在卷里的材料都多 |

每一行的共同点：左边是一个能用尺子或数数量出来的东西，右边三档是它的三个取值，从左到右 oracle 完成任务的余量单调变小（或要做的动作量单调变大）。

说明：

- ring_transfer 的柱高 2026-09-04 起可以直接改：搬运路径里的三个高度（`lift_low_z` / `hang_bottom_z` / `drop_z`）已改为 Layout 按挡头顶与底座高推导（`ring_transfer_zh.md` §7.1）。
- bar_through_hole 的孔径下限 31 mm 受插入高度的手写偏置限制；改为推导后（09-04）下限到 29 mm——再往下受横推段竖直窗口限制（far 托座斜面顶端到孔上沿），27 mm 每侧只剩 1.45 mm，除非收窄 far 托座夹板。
- diverter 只有两档；可加第二维「岔道张角」36° / 30° / 24°（角越小拨杆离基座越远）。
- linkbar 的这条轴不是单个参数，是两区角度联合抽样后按差值分箱。
- 这些参数原先在连续布局轴里连续抽，改为离散档后，连续布局轴里相应删除。

## 3. 逐任务的防捷径离散轴

| 任务 | 防捷径离散轴 | 取值 | 藏起来的那一位信息在哪 |
| --- | --- | --- | --- |
| rope_winding | **绕柱方向** | 顺 / 逆 | 只在指令里；画面相同 |
| ring_transfer | **环从哪根柱搬到哪根** | A→B / B→A | 指令；两柱外观相同 |
| swap_crossing_sign | **出生时哪根绳压在上面** | + / − | 场景线索（必须看交叉处） |
| band_untwist | **8 字哪一端的绳压在上面** | 端 0 / 端 1 | 场景线索（`figure_eight.over_end`，09-03） |
| diverter_route_ball | **死路在哪边**；**拨板出生时封着哪边** | 左 / 右；左 / 右（独立） | 指令 + 场景；两者组合里一半实例正确动作是不转 |
| linkbar_rotate_to_zone | **销钉是哪种颜色**（即目标区）；**两区各是六色里的哪两种** | color_1 / color_2；30 种有序颜色对 | 场景线索（销钉、套环、手柄盖同色） |
| cloth_fold | **捏哪个角** | 四角之一 | 指令（待扩展） |
| cloth_unpleat | **布带的自由端在左边还是右边**（2026-09-05 起；沿 y 铺，自由端在 +y 端或 −y 端，整个布局镜像） | +y / −y | 场景（褶的折向：三层区叠向引入段那一侧，拉错端会拖走锚点）。「前后铺 / 左右铺」按变体轴表搁置：沿 +x 拉的终点桌面高度够不着 |
| cloth_unroll | **布带沿桌子前后铺还是左右铺** | 前后 / 左右 | 场景 |

没有防捷径离散轴的任务：rope_unwinding（出生缠绕方向画面可见，反向解绕只作对照策略）、bar_through_hole、unlink_c_ring、gate_cage_ball。这四个任务的防捷径由物理本身保证：绕过面板顶判 0、缺口不对准就卡住、时机不对就关不住。

## 4. 逐任务的连续布局轴

| 任务 | 连续抽的东西 |
| --- | --- |
| rope_winding / rope_unwinding | 柱子、固定端子、靶心贴纸各自在桌上的位置；柱上每圈之间的间距；第一圈离桌面的高度 |
| ring_transfer | 两根柱一起在桌上的位置；两柱的间距；两柱连线相对桌边的倾斜角；柱身粗细；挡头比柱身大多少 |
| bar_through_hole | 杆（连同前面两个托架）的位置；面板（连同后面托架）的位置；杆的长度；抓杆的哪一段 |
| swap_crossing_sign | 交叉点在绳的哪一段；两根绳整体前后位置；绳的长度 |
| unlink_c_ring | C 环出生时缺口朝哪个方向；整个装置绕竖轴转的角度；装置在桌上的位置 |
| band_untwist | 8 字整体的朝向和位置；交叉处两股的夹角；闭合叶的大小；两绳头之间的距离 |
| gate_cage_ball | 球速；槽道左右位置；闸板架子沿槽道方向的位置；球过闸后到尽头的距离（在「封得住」允许的区间内的归一化位置）；球的起滚点（在「臂来得及」允许的区间内的归一化位置）；架子离槽道的距离（在不重叠区间内的归一化位置） |
| diverter_route_ball | 岔道张角；拨杆长度；球速；分岔口位置（在可达区间内的归一化位置）；球起点（在直道可出生段内的归一化位置） |
| linkbar_rotate_to_zone | 两块颜色区在固定导轨（±90°）上的位置（不重叠即可，可同侧、可相邻）；横梁初始偏转（±15° 扣掉两区禁区后的并集上定位，销不出生在区里）；颜色区的宽度 |
| cloth_fold | 布的位置；弧线松紧 |
| cloth_unpleat | 布带位置；褶隆起的高度；拉多远；捏取点离布边多远 |
| cloth_unroll | 支架位置；卷的层间距；杆离桌面的高度 |

## 5. 难度怎么来

不预设。先让四类轴按上面的范围随机，跑一遍 sweep，记录每个 episode 的参数、oracle 成败与失败原因、对照策略成败、物理是否稳定；然后主要看单调裕度轴（必要时加一条连续轴），按实测把取值分成三段，每段写成一档。每个 episode 属于哪一档由 seed 除以 3 的余数决定，三档在训练集和评测集里各占三分之一。

## 6. 开发计划

### 6.1 变体逻辑放在哪

变体生成逻辑放在 `topogym/generation/`，数据生成 pipeline 只消费一条采好的变体记录。原因：录数据、跑评测、开 viewer、稳定性 sweep 四条下游要用同一条记录；放进 pipeline 则只有录数据那条路径有变体。

| 模块 | 现状 | 要做的 |
| --- | --- | --- |
| `configs/task_configs/<task>.yaml` | linkbar 已有 `variation:` 块（2026-09-01）；其余 12 个无 | 每任务在 yaml 末尾加 `variation:` 列表，每条 `{kind, path 或 paths, 参数…}`，最多一条 `validate`；档位表 `levels:` 划档后再填。任务定义单文件内聚，与 RoboMME 一个任务一个文件同形 |
| `topogym/generation/variant_rng.py` | **已落地（2026-08-29）** | `VariantRng(seed)`：每个 episode 一个实例，`stream(name, retry=k)` 按名字的 SHA-256 前 8 字节作 `SeedSequence` 派生键，得到只由 (seed, name, `VARIANT_RNG_VERSION`) 决定的独立随机流；`tier(n)` = seed % n。名字约定 `"<task_id>/<叶子路径>"`，保留前缀 `visual/`、`demo/`、`braid/word`。不做全局单例；重采用 `retry=k` 进名字而不是继续抽。已接入 `layout_randomization.py`（每叶子一条流）与 `braid.sample_braid_word`（`braid/word` 流）；测试 `tests/check_variant_rng.py`（含黄金值）。改派生规则必须升版本号 |
| `topogym/generation/layout_randomization.py` | **2026-09-01 已改读 yaml**：`randomize_task_cfg` 解析 `cfg.task.variation` 块，无块即 no-op；python 注册表 `_REGISTRY` 已删除。kind ↔ 类：`choice`→`_ChoiceJitter`、`uniform`→`_ScalarJitter`、`distinct_choice`→`_DistinctChoiceJitter`、`spaced_pair`→`_SpacedPairJitter`（间距 ≥ min_gap 的有序对，构造式不拒绝）、`validate`→`_Validate`（`fn: "模块:函数"`，调用时才 import，本模块不依赖 Genesis）。重采按 `retry=k` 命名；流名 `<task_id>/<path>` 不变，搬家前后 100 seed 逐字节一致 **2026-09-02 加 `derived`→`_Derived`**：采样后、校验前调用任务模块函数就地写回派生叶子；区间依赖其他轴的量抽归一化 `[0,1]` 再派生，构造式满足约束、不靠拒绝（linkbar 初始角、diverter 分岔口与球起点）。每任务首抽拒绝率门 ≤ 2%（`check_variant_rng.py` 的 `MAX_REJECTION`） | 到任务时补 `pair`（成对平移）；划档后每条轴加 `levels:` 子键，`seed % 3` 选档 |
| `topogym/tasks/<cat>/<task>.py` Layout | 部分任务有 `validate()` / `checks()`；派生量散在 demo | `checks() -> [(name, measured, limit, ok)]` 统一签名；派生函数（绳长反解、出生点、环长轴、抬升高度）；`task_goal()` 指令模板；`success_params()` |
| `topogym/generation/<task>_generator.py` | 7 个旧任务有，seed 只作身份 | 13 个任务各一个：`build_<task>_episode_spec(cfg, seed)` 输出 `EpisodeSpec`，把采样结果、指令文本、判据参数绑成一条记录 |
| `configs/episode_splits/<task>.yaml` | 仅 3 个任务 | 13 个任务各一份 train / val / test seed 列表；每任务固化 1000 条变体记录（离线门通过即可，不跑物理） |
| `topogym/data/episode_dataset_writer.py` | `setup/` 已写 seed、difficulty、task_goal | `setup/` 追加 `variant.parameters` 与 `success_params`；不采样 |
| `demos/<cat>/<task>_demo.py`、`stability_sweep.sh`、录制脚本 | 各自维护任务表；3 个 demo 调 `randomize_task_cfg` | 统一走 `build_<task>_episode_spec`，seed 从 split 文件取 |

一条 episode 的调用顺序：

```
seed → VariantRng(seed)
     → randomize_task_cfg(cfg, task, rng)        # generation：采防捷径离散轴 → 采单调裕度轴 → 采连续布局轴 → 派生 → checks() 不过则重采（≤20 次）
     → build_<task>_episode_spec(cfg', seed)     # generation：绑成记录（参数 + 指令 + 判据）
     → SceneBuilder(cfg'.env, cfg'.task).build() # tasks：建场景（不变）
     → Planner.plan(layout, observe(scene))      # planning：oracle 只问 layout，不读 cfg 叶子，不读难度
     → EpisodeDatasetWriter(spec)                # data：逐帧落盘，setup/ 写入记录
```

两条禁止项：抽随机数只在 `layout_randomization.py` 一处（`braid.py` 的交叉位置、`band_untwist` 的 `figure_eight_spec()` 内不得自行抽样，只接收采好的值）；难度不另建环境类，档位表在同一 yaml 内。

### 6.2 落地顺序

按「前置代码最少、C4 强制优先」排序，每步交付六项：yaml `variation:` 块、Layout 的 `checks()` 与派生函数、demo 接线 + variant 行 + run 配置键、`check_variant_rng.py` 任务段 + 几何离线门、sweep 脚本、GPU 实测写回文档。generator / EpisodeSpec 属数据管线，暂缓。

**当前进度（2026-09-03）**：第 0–3 步已落地，三个 C4 强制任务（linkbar、diverter、gate_cage_ball）都在 GPU seed 0–9 上 oracle 10/10、对照规则落在中间、离线 1000 seed 首抽拒绝率 ≤ 0.2%。
三步共用的范式已固定：每条轴各自区间；区间依赖其他轴的量抽归一化 `[0,1]` 再由 Layout 派生（`derived` kind）；拒绝率门 2%；`validate` 只兜派生区间为空。
每个任务的 sweep 都晒出了一个判据里的隐含假设（diverter 的 `max_lag` 含手的跟踪滞后、gate 的 `pinched` 只看球心位置），都改的是判据定义而不是包络。
角点门（§4.3）三任务全过：linkbar 20/20、diverter 256/256、gate 64/64——gate 首跑 54/64，暴露的是取板原语丢了姿态插值（`gate_cage_ball_zh.md` §5.3），修的是原语，包络同样没动。
**第 4 步 band_untwist 已落地（2026-09-03，`band_untwist_zh.md` §7）**：镜像开关 `figure_eight.over_end` 是防捷径离散轴（两绳头位置不变、上下股互换）；
`end_gap` 由 `end_frac` 在 [夹爪跨距 0.070, 0.95 × 开口叶直径] 里派生；`checks()` 六行，抬升高度 ≤ 0.40 在内；离线 1000 seed 拒绝率 0，256 角点全过。
角点 c130（开口叶最大 + 绳头最近 + 镜像）落下压出第二个交叉：落点规则只量到另一插头、不看那股的弧，被搬那股正好压在它上面（孪生 c002 过，纯属运气）；09-04 改 planner 落点沿圆外摆到离留桌那股整条折线 ≥ 35 mm，`checks()` 加落点两行成八行，包络没动（`band_untwist_zh.md` §7.5）。
FEM 绳一格 6–13 min，GPU 只跑 seed 0–9 与角点子集。
**第 8 步 unlink_c_ring 已落地（2026-09-03 离线部分，`unlink_c_ring_zh.md` §11）**：五条连续轴、抓取方位角由开口方位角 + 112.5° 派生；`checks()` 从五行加到七行（抓取点可达、手在闭合环之外），
手净空行把 `gap_azimuth_deg` 的包络从计划的 ±15 收到 ±10（302.4° 以下抓取点离环缘不足 45 mm，±15 约 8% 拒绝）；离线 1000 seed 拒绝率 0，32 角点全过。
纯刚体，GPU 一格 8–18 s。08-24 的基线 `passed_through` 判失败复现后定性为判据口径（gateway 接触 −2.6 mm 对 no_align 互锁 −9 mm），判定器改判 `success.max_pass_through_depth` 5 mm。
首跑 seed 0–9 oracle 7/10、角点 oracle 16/32：失败全是原语对准门 `max_align_deg` 3.0，开口方位角 305 那一侧摆动后残差 3.7–5.8°，根因是摆动段 9 mm 稳态落后（基线就有，门只剩 0.35° 余量）。
处置是修原语不是改门或收包络：摆动段走完后重测环心、把差值加到命令点再走一段（`align_correct_passes`），残差压到 0.2–0.4°；重跑 oracle **10/10**、角点 **32/32**，no_align 10/10 判失败。同 diverter / gate 的先例：变体把执行链里的隐含假设晒出来，改的是执行链。

| 序 | 任务 | 前置代码 |
| --- | --- | --- |
| 0 | 通用 | `VariantRng`（已落地 08-29）；`layout_randomization.py` 读 yaml `variation:` 块 + 五种 kind（已落地 09-01）。`EpisodeSpec` / H5 落盘属数据管线，暂缓 |
| 1 | linkbar_rotate_to_zone | **已完成（2026-08-29）**；**2026-09-02 收尾**：初始角改为 `init_frac` 派生（±15° 扣掉两区禁区后的并集上定位），首抽拒绝率 0.234 → 0.002，seed→变体映射随之改变，09-01 §8.4 的 GPU 十格需按新规则重跑复核。原记录：注册条目、demo 接线、离线门、`bash_scripts/tests/linkbar_variation_sweep.sh`；GPU seed 0–9：oracle 10/10 成功、`nearest_zone` 5/10（防捷径成立）、拒绝率 0；结果见 `linkbar_rotate_to_zone_zh.md` §8.2。视觉上十格几乎一样 → **2026-09-01 改版**：固定 ±90° 虚线导轨 + 两区自由放置（同侧/相邻均可）、六色调色板、键名 color_1/color_2、销出生不在区内（首抽拒绝率 0.234，结构性）；离线门全过；GPU seed 0–9：oracle 10/10、`nearest_zone` 5/10、十格画面可分（§5.3、§8.4）。`steps_arc` 已改为按扫掠角推导（恒定角速度，88–92° 扫掠 `max_lag` 4.79° → 2.9°）。角差分箱留到划档 |
| 2 | diverter_route_ball | **已落地（2026-09-02，GPU 待跑）**：yaml 块 3 离散 + 3 连续 + 2 归一化派生（分岔口按可达反解、球起点按直道长度）；`checks()` 六行含可达行；`steps_arc` 按扫掠角推导；离线 1000 seed 拒绝率 0、8 种离散组合全覆盖、`rotate_needed` 0.516；GPU seed 0–9：oracle **10/10**（首跑 9/10，seed 0 接近段撞拨杆，`approach_z` 0.260 → 0.300 后过；`checks()` 加接近净空行）、`fixed_direction` 7/10（与死路侧抽样一致）、十格首帧可分；`max_lag` 14–16° 超 6° 门是 08-22 起的既有问题（`diverter_route_ball_zh.md` §8 步骤 5）。原前置：球径双侧不等式抽成函数；可达行（拨杆 ≤ 0.69 m） |
| 3 | gate_cage_ball | **已落地（2026-09-03）**：`timing:` 段把步长与触发富余写进任务定义；封闭区长度、球起点、架子 x 按两条可解性判据反解区间后派生；`checks()` 五行；第三条对照规则 `fixed_delay`；离线 1000 seed 拒绝率 0、球先到 46%。GPU seed 0–9：oracle 首跑 6/10（判据 `pinched` 把贴着已落座闸板往返的球标成夹住）→ 修正定义后 **10/10**，greedy 8/10，fixed_delay 6/10；见 `gate_cage_ball_zh.md` §5。原前置：新增 `checks()`：两条可解性不等式 + 架子与槽道不重叠 |
| 4 | band_untwist | 已落地（09-03）：镜像开关 `figure_eight.over_end`；`checks()` 的 `lift_height` 行守 0.40；`end_gap` 由 `end_frac` 派生 |
| 5 | swap_crossing_sign | `braid.py` 交叉位置改为接收采样值并裁剪窗口；接入 `verify_braid_spec`；planner 抬升守卫 |
| 6 | rope_winding | 绳长反解；`to_c_route: closure`；柱顶联合不等式进 `checks()` |
| 7 | rope_unwinding | 已落地（09-04，`docs/develop/physics/rope_winding/rope_unwinding_zh.md` §7）：两个手写出生点改为 `routes.initial` 的规则条目 `lead_in_toward` / `tail_arc`；`direction=cw` 定义为镜像布局（Layout 取反三个 fixture 的 y；不镜像时首抽拒绝率 21%）；`wind_z_start` 由 `wind_z_frac` 派生、`C.x` 由 `x_frac` 在挖掉插头净空盘后的区间里派生（独立抽时 3.3% 拒绝）；`checks()` 十二行；离线 1000 seed 拒绝率 0、1536 角点全过；固定布局 GPU 复跑通过（插头出生点西移 28 mm）；GPU：seed 0–9 oracle **10/10**、visual 10/10、wrong_way 3/3 判失败、角点子集 **12/12**。三次首跑失败：网格生成硬边界（3 圈 × 圈距 0.0102 管皮自交 → `climb_per_turn` 下界 0.010 → 0.012，离线 tetgen 定界）；对照组覆盖进了布局校验（`checks()` 改用 oracle 轨道评估、planner 强制轨道下退回直线）；贴柱守卫的绝对门按两圈标定（改为 max(4800, 0.85 × 全绳节点)，锚点最贴柱的角点解下的绳绕在柱脚、贴柱数 1.6 倍出生值但闭合计数 0）|
| 8 | unlink_c_ring | 已落地（09-03）：`checks()` 七行含可达与手净空行并接入拒绝采样；抓取方位角由 `grasp_offset_deg` 派生；`gap_azimuth` ±10；判据 `passed_through` 改判 `max_pass_through_depth`；摆动段闭环修正后 GPU oracle 10/10、角点 32/32、no_align 10/10 判失败 |
| 9 | cloth_unpleat / cloth_unroll | **cloth_unpleat 离线已落地（2026-09-05，`cloth_unpleat_zh.md`）**：褶宽 Cat{0.035, 0.030, 0.024}、`pull_side` 镜像轴、顶缘 / 横向位置 / 行程倍数三条连续轴、内缩量与纵向位置由 frac 派生（附着盘净空、可达盘）；`checks()` 七行；`observe()` 抓取高度修正；离线 1000 seed 拒绝率 0、192 角点全过；GPU 见该文档 §5。cloth_unroll 未开始：圈数上限按层距、杆高、行程上限联合 |
| 10 | ring_transfer | **离线已落地（2026-09-04，`ring_transfer_zh.md` §7）**：三个搬运高度、环长轴、捏取侧 / 捏取点全部改为 Layout 按柱推导；成对平移 / 旋转不加新 kind，走 `pair`（中点、柱距、朝向）→ `derived` 写两柱位置（bar_through_hole 先例）；中点由 `mid_x_frac / mid_y_frac` 在工作区 ∩ 可达圆的窗口里派生；`ring.on_post` 是防捷径指令轴；`checks()` 十五行；离线 1000 seed 拒绝率 0、256 角点全过。**GPU 完成（09-05）**：seed 0–9 oracle 10/10（一格 1276–1375 步），角点子集 8/8（首跑 4/8：派生写了带空格的 `goal.instruction` 句子，角点 sweep 的 Hydra 覆盖按空格切词失败——派生只能写标量、无空格的叶子，指令改为模板 + `Layout.instruction()`），`lift_only` 对照重做为 carry 同款抬离 + 放到两柱中点，3/3 判失败、终态绕数集合为空。原前置：三个搬运高度改为按柱顶推导（柱高轴的前置）；环长轴、捏取侧推导；成对平移 / 旋转 directive；run 配置 + EpisodeSpec |
| 11 | cloth_fold | 四角抓取（`_grasp_offset` + `finger_axis` 回退）；补工作区 / 可达断言 |
| 12 | bar_through_hole | 已落地（09-04，`bar_through_hole_zh.md`）：四个搬运高度改由 Layout 推导（横推高度取「far 托座斜面顶端 ↔ 孔上沿」窗口的中点）；`checks()` 九行；`across_flats` 下界 0.027 → 0.029（竖直窗口）；杆长与抓取偏移由归一化 frac 派生、托座跟随用 `derived`；离线 1000 seed 拒绝率 0、64 角点全过 |

### 6.3 实测与划档

1. 第 0 级（无 Genesis）：每任务抽 1000 条变体，拒绝率 < 5%；50 条上离线调 planner，无异常且路点在工作区。
2. 第 1 级（无 GPU）：seed 0–199 跑离线门，输出每条的轴取值与各不等式读数。
   **角点门（2026-09-03 加）**：`tests/check_variant_corners.py` 从 yaml `variation:` 块构造包络全部顶点（连续轴两端点 × 离散轴全部取值；linkbar 的成对轴用命名对），过派生与校验、打印各判据余量，并经 Hydra compose 复现；`bash_scripts/tests/variant_corners_sweep.sh <task>` 把这些顶点逐个送进物理（`run.randomize_layout=false` + `task.*` 覆盖，走固定布局路径，不碰随机化逻辑）。随机 sweep 抽不到边界，这一步补上「oracle 在包络顶点上可解」的物理证据。
3. 第 2 级（GPU）：`stability_sweep.sh` 补齐 13 个任务，全包络 × 50 seed；记录物理分类、oracle 成败与失败标签、对照策略成败、任务读数。
4. 划档：按单调裕度轴（必要时加一条连续轴）把 sweep 样本分三个分位区间，检查 oracle 成功率单调、对照策略接近随机、无 CRASH；每档取值集合写回 yaml `variation.levels`；每档报告 oracle 成功率、拒绝率、对照策略成功率。包络内 oracle 成功率无显著变化的任务只设一档。
5. 固化 split；每任务录 150 条训练（防捷径离散轴组合多的 200）+ 50 条评测；录制帧率改为 20 Hz（`dataset_every_n_steps: 5`），使 13 任务总帧数约 450 k，匹配 140 k 步 × batch 32 的训练预算（约 10 epoch）；oracle 执行加 5% 路点噪声 + 恢复选项。

### 6.4 与先例的对应

| 做法 | 来源 |
| --- | --- |
| 1000 条变体记录固化、按编号取用 | SoftGym（预采 1000 初态并缓存）、RoboMME `make_env_for_episode(idx)` |
| 防捷径离散轴 = 逐 seed 随机的隐藏信息，用对照策略分数验证 | RoboMME 非马尔可夫设计（π0.5 无记忆 17.9% vs 记忆 44.5%） |
| 单调裕度轴 3 档 + `seed % 3` 交错 | RoboMME `configs[difficulty]`、`seed % 3` |
| 校验不过则重采 | RLBench / ManiSkill 规划失败丢弃；MimicGen 变换后验证 |
| 每任务一个文件内聚场景、随机化、判定、指令 | RoboMME `robomme_env/<Task>.py` |
| 路点噪声 + 恢复 | RoboMME 数据生成（5% 关键帧噪声） |
