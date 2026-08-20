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
```

| 文件 | 检查什么 |
| --- | --- |
| `check_demo_configs.py` | demo 的 Hydra 接线：未定义名、`OmegaConf.merge` 是否往 struct 配置里加新键、`cfg.run.X` 是否在该 demo 的 run 配置链里，以及一张七列的迁移形态指纹表 |
| `check_configs_compose.py` | 每份任务配置与每份主配置能否 compose，以及全部 `${...}` 插值能否解析 |
| `check_rope_winding_geometry.py` | rope_winding 的布局与 oracle：路点是否是配置要求的螺旋、出生路线是否已经绕柱、终态绕数是否恰为 ±turns、绳长是否够 |
| `check_rope_tube_mesh.py` | 喂给 tetgen 的那张绳管皮：两个方向的镶嵌误差（截面弦高 vs 环距按曲率折算的纵向弦高）、表皮自带扭转、最小曲率半径与管半径之比。先用 `run.build_only=true` 生成 OBJ |

前两个覆盖不到的部分写在各自的 docstring 里：带默认值的 `getattr` 动态访问、迁移时值
取错、以及物理行为。第二类刚发生过一次——`fem_ipc_rope_spike` 迁 Hydra 时默认后端从
gpu 变成 cpu，不报错，只是结果不可比（见
[`../docs/develop/physics/fem_ipc_step_cost_zh.md`](../docs/develop/physics/fem_ipc_step_cost_zh.md)）。

## 需要 GPU 的

```bash
python -m tests.fem_ipc_rope_spike run.bench_steps=100      # 每步耗时
python -m tests.fem_ipc_rope_spike run.test=contact         # 两绳接触是否穿模
```

`fem_ipc_rope_spike.py` 是 FEM+IPC 后端的诊断场景：自建 scene，只有一个地面加绳，
没有桌子、没有机械臂、没有 connector latch，用来把后端的行为与任务场景的行为分开。
`run.test` 有 `settle` / `anchor` / `follow` / `contact` 四档。`prefabs.rope_fem` 里那组
材料参数就是它标定出来的，所以它同时是复现标定的入口。配置在
`configs/fem_ipc_rope_spike.yaml`。

demo 本身也带一个不跑物理的检查模式，`run.build_only=true`，约 90 秒；
`run.bench_steps=N` 量每步耗时。见 [`../demos/README.md`](../demos/README.md)。
