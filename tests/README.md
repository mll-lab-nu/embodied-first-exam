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
python tests/check_rope_tube_mesh.py          # 只用 numpy；量的是已经生成的管皮 OBJ
python tests/check_closed_band_mesh.py        # 只用 numpy + PyYAML；自己生成闭合带并量
python tests/check_c_ring_clearance.py        # 只用 numpy + PyYAML；量 docx 3.4 两个环的净空
python tests/check_gateway_extract_quat.py    # 只用 numpy + PyYAML；抽出原语的旋转合成
```

| 文件 | 检查什么 |
| --- | --- |
| `check_demo_configs.py` | demo 的 Hydra 接线：未定义名、`OmegaConf.merge` 是否往 struct 配置里加新键、`cfg.run.X` 是否在该 demo 的 run 配置链里，以及一张七列的迁移形态指纹表 |
| `check_configs_compose.py` | 每份任务配置与每份主配置能否 compose，以及全部 `${...}` 插值能否解析 |
| `check_rope_winding_geometry.py` | rope_winding 的布局与 oracle：路点是否是配置要求的螺旋、出生路线是否已经绕柱、终态绕数是否恰为 ±turns、绳长是否够 |
| `check_rope_tube_mesh.py` | 喂给 tetgen 的那张绳管皮：两个方向的镶嵌误差（截面弦高 vs 环距按曲率折算的纵向弦高）、表皮自带扭转、最小曲率半径与管半径之比。先用 `run.build_only=true` 生成 OBJ |
| `check_gateway_extract_quat.py` | docx 3.4 抽出原语的手腕转动：四元数合成之后 C 环开口是否真的落到管身方向上、手腕有没有走远路，以及原语的四元数写法与 `_c_ring_geometry.apply_phases` 的矩阵写法是否是同一个旋转。写反的后果是把环转进闭合环里，而 assisted carry 下那是穿模不是卡住，下游看不出来 |
| `check_c_ring_clearance.py` | docx 3.4 的固定环 + C 环：五条布局不等式的余量、分段近似的弦高、出生时是否读作互锁（弦闭合后 `Lk=±1`），以及 gateway 轨迹全程无接触而八条非 gateway 轨迹是否全部卡住 |
| `check_closed_band_mesh.py` | docx 3.3 的闭合弹性带（Phase 0）：周期扫掠是否水密且两向镶嵌相当、接缝闭合后的自链数 `Lk` 是否为 0（`Lk=±1` 的带永远翻不平）、出生自接触间隙是否够势垒、以及自交叉计数在 O 形／8 字／反向翻转／压扁 8 字四种解析折线上的读数 |

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
