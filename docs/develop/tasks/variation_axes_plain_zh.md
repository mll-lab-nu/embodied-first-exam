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
| linkbar_rotate_to_zone | **两块颜色区离横梁初始方向的远近差** | 相差 ≥20° / 10–20° / ≤10° | 两区离得一样远时，「转向最近那块」这个偷懒办法就变成抛硬币 |
| cloth_fold | **捏取点离布角尖的距离** | 0 / 1 / 2 cm | 往里捏得越多，角尖越容易耷拉，折边越不齐 |
| cloth_unpleat | **布带上那道褶叠进去的宽度** | 3.5 / 3 / 2.4 cm | 褶越窄，「拉平了」和「褶塌了」两种读数越难分开 |
| cloth_unroll | **布带卷在杆上的圈数** | 1 / 1.25 / 1.44 圈 | 卷得多，要拉的距离和存在卷里的材料都多 |

每一行的共同点：左边是一个能用尺子或数数量出来的东西，右边三档是它的三个取值，从左到右 oracle 完成任务的余量单调变小（或要做的动作量单调变大）。

说明：

- ring_transfer 的柱高目前不能直接改：搬运路径里的三个高度是手写数值，柱高一变就错，须先改为按柱顶高度推导。
- bar_through_hole 的孔径下限 31 mm 受插入高度的手写偏置限制；改为推导后可加一档 27 mm。
- diverter 只有两档；可加第二维「岔道张角」36° / 30° / 24°（角越小拨杆离基座越远）。
- linkbar 的这条轴不是单个参数，是两区角度联合抽样后按差值分箱。
- 这些参数原先在连续布局轴里连续抽，改为离散档后，连续布局轴里相应删除。

## 3. 逐任务的防捷径离散轴

| 任务 | 防捷径离散轴 | 取值 | 藏起来的那一位信息在哪 |
| --- | --- | --- | --- |
| rope_winding | **绕柱方向** | 顺 / 逆 | 只在指令里；画面相同 |
| ring_transfer | **环从哪根柱搬到哪根** | A→B / B→A | 指令；两柱外观相同 |
| swap_crossing_sign | **出生时哪根绳压在上面** | + / − | 场景线索（必须看交叉处） |
| band_untwist | **8 字哪一端的绳压在上面** | 端 0 / 端 1 | 场景线索（待新增） |
| diverter_route_ball | **死路在哪边**；**拨板出生时封着哪边** | 左 / 右；左 / 右（独立） | 指令 + 场景；两者组合里一半实例正确动作是不转 |
| linkbar_rotate_to_zone | **销钉是哪种颜色**（即目标区）；**两区颜色是否互换** | 左 / 右；原样 / 互换 | 场景线索（销钉、套环、手柄盖同色） |
| cloth_fold | **捏哪个角** | 四角之一 | 指令（待扩展） |
| cloth_unpleat / cloth_unroll | **布带沿桌子前后铺还是左右铺** | 前后 / 左右 | 场景 |

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
| gate_cage_ball | 球的起滚点；球过闸后到尽头的距离；闸板架子的位置；槽道左右位置 |
| diverter_route_ball | 岔道张角；拨杆长度；分岔口位置；球速与起点 |
| linkbar_rotate_to_zone | 两块颜色区各自离横梁初始方向的角度；横梁初始偏转；颜色区的宽度 |
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
| `configs/task_configs/<task>.yaml` | 无 variation 块 | 新增 `variation:` 块：每条轴写 `{path, kind: choice / uniform / levels, values 或 lo/hi, derive: <Layout 方法名>}`；档位表 `levels: {easy, medium, hard}` 划档后再填。任务定义单文件内聚，与 RoboMME 一个任务一个文件同形 |
| `topogym/generation/variant_rng.py`（新） | 无 | `VariantRng(seed)`：每个 episode 一个实例，`stream(axis_name)` 按轴名的稳定哈希从 `SeedSequence` 派生独立随机流。不做全局单例：全局状态会使取值依赖调用顺序、并行不安全、测试需手动重置 |
| `topogym/generation/layout_randomization.py` | 4 个旧任务的 python 字面值注册表、4 种连续 directive、难度倍率 | 改为读 yaml `variation:` 块；新增 `_ChoiceJitter` / `_ScalarJitter` / `_PairJitter` / `_DerivedSolve` / `_Validate`；随机数只从 `VariantRng` 取；删除难度倍率，改为 `seed % 3` 选档位表（划档前 `envelope` 档 = 全包络） |
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

按「前置代码最少、C4 强制优先」排序，每步交付：yaml `variation:` 块、Layout 的 `checks()` 与派生函数、generator、单元测试（同 seed 同结果、seed 敏感、越界为零、拒绝率 < 5%、planner 离线可解）、run 配置键、sweep 表项。

| 序 | 任务 | 前置代码 |
| --- | --- | --- |
| 0 | 通用 | `VariantRng`；`layout_randomization.py` 读 yaml + 五种 directive；`EpisodeSpec` 加 `success_params` |
| 1 | linkbar_rotate_to_zone | `validate()` 已有；两区角联合抽样后按角差分箱 |
| 2 | diverter_route_ball | 球径双侧不等式抽成函数；可达行（拨杆 ≤ 0.69 m） |
| 3 | gate_cage_ball | 新增 `checks()`：两条可解性不等式 + 架子与槽道不重叠 |
| 4 | band_untwist | 镜像开关（同步 `layout.over_end`）；planner 抬升 ≤ 0.40 守卫；`end_gap` 上限随开口叶半径 |
| 5 | swap_crossing_sign | `braid.py` 交叉位置改为接收采样值并裁剪窗口；接入 `verify_braid_spec`；planner 抬升守卫 |
| 6 | rope_winding | 绳长反解；`to_c_route: closure`；柱顶联合不等式进 `checks()` |
| 7 | rope_unwinding | 两个出生点改为推导；run 配置键 |
| 8 | unlink_c_ring | `SceneGeometry.checks()` 接入拒绝采样；抓取方位角推导；补可达行 |
| 9 | cloth_unpleat / cloth_unroll | 修 `observe()` 抓取高度（unpleat）；褶宽上限 0.035；圈数上限按层距、杆高联合；run 配置补 seed 键 |
| 10 | ring_transfer | 三个搬运高度改为按柱顶推导（柱高轴的前置）；环长轴、捏取侧推导；成对平移 / 旋转 directive；run 配置 + EpisodeSpec |
| 11 | cloth_fold | 四角抓取（`_grasp_offset` + `finger_axis` 回退）；补工作区 / 可达断言 |
| 12 | bar_through_hole | 插入高度改为推导；新增 `validate()` |

### 6.3 实测与划档

1. 第 0 级（无 Genesis）：每任务抽 1000 条变体，拒绝率 < 5%；50 条上离线调 planner，无异常且路点在工作区。
2. 第 1 级（无 GPU）：seed 0–199 跑离线门，输出每条的轴取值与各不等式读数。
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
