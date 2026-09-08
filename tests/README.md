# tests — 用来检查系统的东西

判据是**产出什么**，不是用什么语言写的：

| 目录 | 放什么 | 判据 |
| --- | --- | --- |
| `tests/` | 检查与测量 | 跑完给出的是「对不对」「多快」 |
| `scripts/` | 产出工件 | 跑完留下一个数据集、一份改过的配置文件 |
| `bash_scripts/tests/` | 批量跑真实 episode 的 harness | 需要 GPU，一次几十分钟起；它们调用 `demos/` |

2026-08-11 由 `scripts/` 分出。此前检查类脚本和工件生成脚本混在一起。

## 不需要 GPU 的

```bash
python tests/check_demo_configs.py            # 只用标准库 + PyYAML，任何解释器都能跑
python tests/check_configs_compose.py         # 需要 hydra 包，即项目 venv
python tests/check_rope_winding_geometry.py   # 需要项目 venv
python tests/check_rope_unwinding_geometry.py # 需要项目 venv；docx 2.5 预绕螺旋 + 反向 oracle 的布局门
python tests/check_rope_tube_mesh.py          # 只用 numpy；量的是已经生成的管皮 OBJ
python tests/check_closed_band_mesh.py        # 只用 numpy + PyYAML；自己生成闭合带并量
python tests/check_band_untwist_geometry.py   # 只用 numpy + PyYAML；docx 3.3 开口绳 8 字的几何、自交叉计数、规划器门（含落点离留桌那股）、变体包络 256 角点八行
python tests/check_swap_crossing_sign_geometry.py  # 只用 numpy + PyYAML；docx 3.2 两根线一次交叉：八行布局判据、交叉位置 / 符号两个生成器输入、变体包络 32 角点、负例
python tests/check_swap_crossing_sign_planner.py   # 只用 numpy；cover 步的落点确实跨过另一根、抬升在合成形状（1–3 弓形 × 两档松弛）下不超工作区顶——冻结布局 + 包络 (x_end, 间距) 四角点
python tests/check_ring_transfer_geometry.py  # 需要项目 venv；docx 2.6 两柱 + 闭合环的布局门
python tests/check_c_ring_clearance.py        # 只用 numpy + PyYAML；量 docx 3.4 两个环的净空 + 变体包络 32 角点
python tests/check_gateway_slide_path.py      # 只用 numpy + PyYAML；抽出原语的滑动路径
python tests/check_variant_rng.py             # 只用 numpy；每 episode 种子 → 按名字派生的随机流是否确定、独立、有黄金值
python tests/check_variant_corners.py         # 需要项目 venv；十三个任务变体包络的全部角点：派生、校验、各判据余量、Hydra 覆盖路径复现
python tests/check_bar_through_hole_geometry.py  # 需要项目 venv；docx 2.3 派生高度与托座位置还原手写基准、横推窗口、最坏角点
python tests/check_cloth_unpleat_geometry.py  # 只用 numpy + PyYAML；docx 1.2 判据两侧、材料守恒、轨迹、变体包络 192 角点七行
python tests/check_cloth_unroll_geometry.py   # 只用 numpy + PyYAML；docx 1.3 判据四种末态、材料守恒、轨迹、变体包络 96 角点十行
python tests/check_cloth_fold_geometry.py     # 只用 numpy + PyYAML；docx 1.1 判据六种末态、弧线、贴图、变体包络 96 角点五行
```

| 文件 | 检查什么 |
| --- | --- |
| `check_demo_configs.py` | demo 的 Hydra 接线：未定义名、`OmegaConf.merge` 是否往 struct 配置里加新键、`cfg.run.X` 是否在该 demo 的 run 配置链里，以及一张七列的迁移形态指纹表 |
| `check_configs_compose.py` | 每份任务配置与每份主配置能否 compose，以及全部 `${...}` 插值能否解析 |
| `check_rope_winding_geometry.py` | rope_winding 的布局与 oracle：路点是否是配置要求的螺旋、出生路线是否已经绕柱、终态绕数是否恰为 ±turns、绳长是否够 |
| `check_rope_unwinding_geometry.py` | rope_unwinding（docx 2.5）：出生路线读数恰为 ±start_turns、螺旋在柱身上且圈间有净空、尾弧沿切线离柱、oracle 反向轨道逐圈下降且在柱顶下、逐圈脱离读 start_turns…1,0、强制同向轨道读 2·start_turns、三档圈数的 slack 都在带内 |
| `check_rope_tube_mesh.py` | 喂给 tetgen 的那张绳管皮：两个方向的镶嵌误差（截面弦高 vs 环距按曲率折算的纵向弦高）、表皮自带扭转、最小曲率半径与管半径之比。先用 `run.build_only=true` 生成 OBJ |
| `check_gateway_slide_path.py` | docx 3.4 抽出原语的对准滑动：环心走完弧之后开口是否真的落到管身方向上，以及弧的分段够不够细（单段弦向内切 3.35mm，超过整个余量；8 段 0.053mm）。带负对照——断言 1 段是不够的，这样以后有人悄悄去掉分段会在这里失败而不是在场景里失败。四个 `hang_yaw_deg` 都测。取代了 `check_gateway_extract_quat.py`：执行路径上已经没有四元数合成 |
| `check_c_ring_clearance.py` | docx 3.4 的固定环 + C 环：七条布局不等式的余量（含抓取点可达、手在闭合环之外两行）、分段近似的弦高、出生时是否读作互锁（弦闭合后 `Lk=±1`），以及 gateway 轨迹全程无接触而八条非 gateway 轨迹是否全部卡住；再对 yaml `variation:` 块的 32 个角点重做以上四问，两个负例（`gap_azimuth_deg=295` 手净空、`hang_yaw_deg=0` 可达）必须被拒 |
| `check_ring_transfer_geometry.py` | docx 2.6（`ring_transfer`）的两根走线柱 + 闭合弹性环：周期管水密与 `Lk=0`、势垒不越过自表面；carry oracle 的 `RingTransferLayout.checks()` 十五行（环净空、出生环避开目标柱、挡头外伸、捏取点在直段上、手掌在抓取 / 越柱 / 放下位避开挡头、lift_low 低于悬挂深度、U 底在柱身上、U 宽够套柱、悬挂股避开出生柱挡头、手位与出生环在工作区、可达）；transfer 路线只报告（拉伸梯形在 B 处的绳股间距含两个负对照、远端帽路径逐样本量绳股到 B 轴距离、平移段绷紧、越顶高度下限）；变体包络：基准 yaml 还原手写值（A/B 位置、长轴 [0,-1]、捏取侧 −1、pinch_along 0.070、三高度 0.120/0.040/0.040）、朝向 30° 的布局 = 基准绕中点旋转、on_post=B 时跨越序列反转、256 个角点全过并打印各行最紧余量、三个负例（柱高 0.13、柱半径 0.030、柱距 0.28 + 中点 0.040）被拒 |
| `check_band_untwist_geometry.py` | docx 3.3 的开口绳桌面版（`band_untwist`）：8 字控制线的端距、最小转角半径、交叉处抬高与绳长；开口折线自交叉计数在 8 字／压扁 8 字／直绳／两头相邻的 C 形／两交叉曲线上的读数（C 形专抓闭合计数器的幻影段）；规划器在 oracle / wrong_end 两档各选一端、抬升过弧长、落点等距交叉点且离另一端**与留桌那股整条折线** ≥ place_clearance、与布局的离线重演一致、全部路点在工作区内（鼓包折线把落点推远的合成例）；变体包络：yaml `variation:` 块的 256 个角点（`over_end` 两值 × 7 条 uniform 两端，`end_gap` 由 `end_frac` 派生）八行 `figure_eight_checks` 全过、恰一个交叉且实测 over 端 = spec、镜像格两绳头位置不变；负例：开口叶太小时 `end_gap` 区间闭合、交叉点推到工作区边缘时 footprint 拒、`place_clearance` 0.30 时落点扫描抛错且该行判负 |
| `check_cloth_unpleat_geometry.py` | docx 1.2 的褶皱布带（`cloth_unpleat`）：在合成布上跑真实判定器——铺平过两条门、压塌（也是真实起始态）被层数与材料守恒一起挡住、拉过头两门都过而只有 `band_shift` 分得出；剖面算术（存料 = 全长 − 俯视跨度）；轨迹（拉距 = 存料 × pull_scale、贴桌不侧偏、shove / overpull 名副其实）；条纹与折痕垂直的两个约定；**闭环补拉**（`PullExtender`：目标铺开长度的算术、差 10 mm 时补差额或上限余量、铺到全长后停、锚点滑走时停在 1.15 × 存料）；**变体包络**（2026-09-05）：七行 `cloth_unpleat_checks` 基准全过、两个派生还原基准、镜像布局（`pull_side` −1）七行相等且抓取点 / 终点 y 取反、192 角点全过并打印最紧行、三个负例（褶宽 0.040 内缩窗口为空、最远布局纵向 +0.030 被可达行拒、顶缘 3 mm 被拒） |
| `check_cloth_unroll_geometry.py` | docx 1.3 的卷筒布带（`cloth_unroll`）：在合成布上跑真实判定器——铺平过两条门、起始态与整卷被扯下来都被挡住且 `on_bar` 分得开、拉过头两门都过；剖面算术（卷料 + 垂落 + 平铺 = 全长）；轨迹（行程 = 铺平位移 × pull_scale、分段不换来可达、shove / overpull 名副其实、终点与卷筒几何无关的恒等式）；**变体包络**（2026-09-05）：十行 `cloth_unroll_checks` 基准全过、三个派生还原基准、层距窗口在 1.5 圈被平铺段封顶、镜像布局（`pull_side` −1）十行相等且支架 / 抓取点 / 终点 y 取反、96 角点全过并打印最紧行、96 角点出生态三层格 ≥ 守卫、四个负例（1.75 圈窗口为空、1.5 圈 + 杆高 0.053 + 层距 0.016 抓取点离梁心 < 57 mm、最远布局纵向 −0.070 被可达行拒、1 圈设计铺展比 > 固定守卫 0.50） |
| `check_cloth_fold_geometry.py` | docx 1.1 的折角（`cloth_fold`）：在合成布上跑真实判定器——完美折过两条门、未折 / 揉团 / 贴地拖 / 整体偏移 12 mm / 5% 乱团各被该管它的门拦住、没有一条门是多余的；层数是真的在数层；弧线由材料定死（等半径、按松紧差距停在对角前、过顶、弦误差 < 粒径、步数合标定手速）；UV 与织纹。**变体包络**（2026-09-06）：五行 `cloth_fold_checks` 基准全过、派生还原基准（`center_x_frac` 1.0 → 窗口顶端 0.0402，远角构造落在可达盘上）、四角互为抓取点 / 落点且折向是四条对角线方向、`drag` 走法俯视同路贴桌不抬、`fixed_corner` 走法无视指令按 far_left 规划、96 角点全过并打印最紧行、96 个 center_x 窗口都 ≥ 0.020、三个负例（松紧 0.93 差 11.9 mm 被 `slack_within_gate` 拒、布最靠外远角 0.775 被可达行拒、内缩 0.110 被附着行拒） |
| `check_bar_through_hole_geometry.py` | docx 2.3 的杆穿孔：2026-09-04 起四个搬运高度与三个托座 x 由 `BarThroughHoleLayout` 推导，本测试钉住推导在基准 yaml 上还原手写值（grasp / lift / seat 1 mm 内，insert 由 0.193 改到横推窗口中点 0.192）与托座 −0.070 / 0.020 / 0.200；横推窗口在 `across_flats` 0.029 / 0.032 / 0.038 三点为 4.88 / 7.88 / 13.88 mm；最坏角点（杆最靠面板、面板最靠杆）杆长区间收到 [0.170, 0.190]、抓取偏移收到 [0.060, 0.070] 且九行 `checks()` 全过 |
| `check_variant_rng.py` | `topogym/generation/variant_rng.py`：同种子同名字的流在两次调用、两个实例、先抽别的名字之后都逐数相等；不同名字、不同种子不相等；`retry=k` 各自独立；`tier(3)` = seed % 3；黄金值（seed 0、名字 `golden` 的首个均匀数）钉住派生规则，改规则不升 `VARIANT_RNG_VERSION` 在这里失败。另回归 `randomize_task_cfg`（4 个已注册任务：确定、种子敏感、输入不变、未注册原样返回、cable_routing 抖动在 ±0.010 内且等于该叶子命名流的直接抽样）与 `sample_braid_word`（传 seed 与传 `braid/word` 流结果相同） |
| `check_swap_crossing_sign_geometry.py` | docx 3.2 的两根线一次交叉（`swap_crossing_sign`，与 untangle_continuous 共用场景）：冻结布局的七行 `braid_checks`（插头间距、裁剪后换道窗口、自由直段、工作区 x / y、插线板覆盖、separate 步预测抬升）钉住记录值且控制折线弧长仍是 0.4376；`crossing_frac` 0.30 / 0.75 时窗口裁在 `braid_span` 内、陡峭度过门、交叉落在指定处，`crossing_sign` ±1 只换哪根带鼓包；3 字 word 保持等分槽位；变体包络 32 角点七行 + braid 自检全过、最坏预测抬升 0.361；负例：`x_end` 0.23 只挂 `footprint_x`、顶 0.25 只挂 `lift_height`、间距 0.060 只挂 `end_separation`、`center_y` 0.22 挂 `footprint_y` + `strip_cover`、`crossing_frac` 0.90 抛错、0.84 挂 `crossing_window` |
| `check_swap_crossing_sign_planner.py` | `swap_crossing_sign` 的 cover 步（第二步把另一根压上去）纯几何：两线还叠着 / 只是挨着时拒绝；夹回可达范围后的落点仍跨过另一根、抬升高于手下悬垂弧长、落点离另一根线身 ≥ `place_clearance`；形状扫描（1–3 个弓形 × 两档松弛）在冻结布局与变体包络 (x_end, 间距) 四角点上最坏抬升不超 0.40 顶（x_end 0.20 / 间距 0.072 最坏 0.399，这是 x_end 上限取 0.20 的依据）；对照对 oracle / restack_same 压的是不同的线 |
| `check_variant_corners.py` | 变体包络的边界值测试（linkbar / diverter / gate_cage_ball / band_untwist / swap_crossing_sign / unlink_c_ring / bar_through_hole / rope_unwinding / ring_transfer / rope_winding / cloth_unpleat / cloth_unroll / cloth_fold）：从 yaml `variation:` 块自动构造角点——连续轴取两端点、离散轴取全部取值、`spaced_pair` 用脚本里的命名对，做全组合（20 / 256 / 64 / 256 / 32 / 32 / 64 / 1536 / 256 / 1536 / 192 / 96 / 96 个）；每个角点过任务自己的 `derived` / `validate` 钩子并打印各判据余量，再按 GPU 脚本的方式经 Hydra compose（`run.randomize_layout=false` + `task.*` 覆盖）复现同样读数。`--manifest` 输出角点清单给 `bash_scripts/tests/variant_corners_sweep.sh`。只在测试里用：不碰 `randomize_task_cfg`，seed→变体映射不变 |
| `check_closed_band_mesh.py` | docx 3.3 的闭合弹性带（Phase 0，**已废弃路线**，保留作证据）：周期扫掠是否水密且两向镶嵌相当、接缝闭合后的自链数 `Lk` 是否为 0（`Lk=±1` 的带永远翻不平）、出生自接触间隙是否够势垒、以及自交叉计数在 O 形／8 字／反向翻转／压扁 8 字四种解析折线上的读数 |

前两个覆盖不到的部分写在各自的 docstring 里：带默认值的 `getattr` 动态访问、迁移时值
取错、以及物理行为。第二类刚发生过一次——`fem_ipc_rope_spike` 迁 Hydra 时默认后端从
gpu 变成 cpu，不报错，只是结果不可比（见
[`../docs/develop/physics/fem_ipc_step_cost_zh.md`](../docs/develop/physics/fem_ipc_step_cost_zh.md)）。

## 需要 GPU 的

```bash
python -m tests.fem_ipc_rope_spike run.bench_steps=100      # 每步耗时
python -m tests.fem_ipc_rope_spike run.test=contact         # 两绳接触是否穿模
python -m tests.closed_band_spike run.test=hold            # 8 字带释放后是否自解
python -m tests.closed_band_spike run.test=flip run.flip_side=wrong
python -m tests.closed_band_spike run.test=hold recording=default recording.path=runs/x.mp4
python -m tests.ring_transfer_spike run.test=stretch    # 单夹爪两指钩住能否把 B 套进环
```

`fem_ipc_rope_spike.py` 是 FEM+IPC 后端的诊断场景：自建 scene，只有一个地面加绳，
没有桌子、没有机械臂、没有 connector latch，用来把后端的行为与任务场景的行为分开。
`run.test` 有 `settle` / `anchor` / `follow` / `contact` 四档。`prefabs.rope_fem` 里那组
材料参数就是它标定出来的，所以它同时是复现标定的入口。配置在
`configs/fem_ipc_rope_spike.yaml`。

`closed_band_spike.py` 是 docx 3.3（`band_untwist`）的 Phase 0：地面 + 壁面 + 挂销 +
闭合弹性带，不接机械臂。带按平整 O 形出生，8 字由求解器拧出来（直杆静止形状会把接缝
扭转抄进静止态，理由见该脚本的模块文档）。`run.test` 有 `mesh` / `settle` / `hold` /
`flip` 四档，按依赖排序，前一项不过不跑后一项；`hold` 是决定该任务是否成立的一档 ——
8 字若无外力自行张开成 O，则不需要机械臂即自解。配置在
`configs/closed_band_spike.yaml` 与 `configs/run_configs/closed_band_spike.yaml`。
录制走 `recording` 配置组，相机单独定义在 `run.camera`（本场景没有桌子，`env.cameras`
那组 world 系位姿指过去是空的）；视角接近正对壁面，与自交叉判定的投影方向一致，
帧上带自交叉数的 HUD。`recording.path` 每次要单独给，否则三次跑会互相覆盖。

demo 本身也带一个不跑物理的检查模式，`run.build_only=true`，约 90 秒；
`run.bench_steps=N` 量每步耗时。见 [`../demos/README.md`](../demos/README.md)。
