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
python tests/check_band_untwist_geometry.py   # 只用 numpy + PyYAML；docx 3.3 开口绳 8 字的几何、自交叉计数与规划器门
python tests/check_ring_transfer_geometry.py  # 需要项目 venv；docx 2.6 两柱 + 闭合环的布局门
python tests/check_c_ring_clearance.py        # 只用 numpy + PyYAML；量 docx 3.4 两个环的净空
python tests/check_gateway_slide_path.py      # 只用 numpy + PyYAML；抽出原语的滑动路径
```

| 文件 | 检查什么 |
| --- | --- |
| `check_demo_configs.py` | demo 的 Hydra 接线：未定义名、`OmegaConf.merge` 是否往 struct 配置里加新键、`cfg.run.X` 是否在该 demo 的 run 配置链里，以及一张七列的迁移形态指纹表 |
| `check_configs_compose.py` | 每份任务配置与每份主配置能否 compose，以及全部 `${...}` 插值能否解析 |
| `check_rope_winding_geometry.py` | rope_winding 的布局与 oracle：路点是否是配置要求的螺旋、出生路线是否已经绕柱、终态绕数是否恰为 ±turns、绳长是否够 |
| `check_rope_unwinding_geometry.py` | rope_unwinding（docx 2.5）：出生路线读数恰为 ±start_turns、螺旋在柱身上且圈间有净空、尾弧沿切线离柱、oracle 反向轨道逐圈下降且在柱顶下、逐圈脱离读 start_turns…1,0、强制同向轨道读 2·start_turns、三档圈数的 slack 都在带内 |
| `check_rope_tube_mesh.py` | 喂给 tetgen 的那张绳管皮：两个方向的镶嵌误差（截面弦高 vs 环距按曲率折算的纵向弦高）、表皮自带扭转、最小曲率半径与管半径之比。先用 `run.build_only=true` 生成 OBJ |
| `check_gateway_slide_path.py` | docx 3.4 抽出原语的对准滑动：环心走完弧之后开口是否真的落到管身方向上，以及弧的分段够不够细（单段弦向内切 3.35mm，超过整个余量；8 段 0.053mm）。带负对照——断言 1 段是不够的，这样以后有人悄悄去掉分段会在这里失败而不是在场景里失败。四个 `hang_yaw_deg` 都测。取代了 `check_gateway_extract_quat.py`：执行路径上已经没有四元数合成 |
| `check_c_ring_clearance.py` | docx 3.4 的固定环 + C 环：五条布局不等式的余量、分段近似的弦高、出生时是否读作互锁（弦闭合后 `Lk=±1`），以及 gateway 轨迹全程无接触而八条非 gateway 轨迹是否全部卡住 |
| `check_ring_transfer_geometry.py` | docx 2.6（`ring_transfer`）的两根走线柱 + 闭合弹性环：环与柱的净空、周期管水密与 `Lk=0`、势垒不越过自表面；拉伸梯形在 B 处的绳股间距（含两个负对照：单点捏住、20mm 柱）；远端帽整条 oracle 路径（平转/抬升/平移/下放）逐样本量绳股线段到 B 轴的距离、平移段全程绷紧、越顶高度下限、工作区与抓取净空 |
| `check_band_untwist_geometry.py` | docx 3.3 的开口绳桌面版（`band_untwist`）：8 字控制线的端距、最小转角半径、交叉处抬高与绳长；开口折线自交叉计数在 8 字／压扁 8 字／直绳／两头相邻的 C 形／两交叉曲线上的读数（C 形专抓闭合计数器的幻影段）；规划器在 oracle / wrong_end 两档各选一端、抬升过弧长、落点等距交叉点且离另一端 place_clearance、全部路点在工作区内 |
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
