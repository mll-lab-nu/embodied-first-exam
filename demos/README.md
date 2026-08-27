# demos — 可运行的任务演示

分类与 `topogym/tasks/` 对齐：同一个任务的 demo 和它的场景生成代码在同名的类别目录下。
2026-08-10 由平铺的 `prototypes/` 改成这个结构，原因见
[`../docs/develop/framework/task_taxonomy_zh.md`](../docs/develop/framework/task_taxonomy_zh.md) §6.1。

| 目录 | 任务 | demo |
| --- | --- | --- |
| `entangle/` | swap_crossing_sign | `swap_crossing_sign_physical_pinch_demo` |
| | unlink_c_ring | `unlink_c_ring_physical_extract_demo`（主力）、`unlink_c_ring_inspect_demo`（stage-0：场景与静置） |
| | untangle_continuous | `untangle_continuous_physical_pinch_demo`（主力）、`untangle_continuous_fem_demo`、`untangle_continuous_inspect_demo` |
| | untangle（离散版） | `untangle_physical_handle_demo` |
| `connectivity/` | stacked_plate | `stacked_plate_physical_rotate_demo`、`stacked_plate_inspect_demo` |
| `routing/` | cable_routing | `cable_routing_physical_handle_demo` |
| | rope_winding | `rope_winding_physical_handle_demo` |
| | rope_unwinding | `rope_unwinding_physical_handle_demo`（入口；主体复用 rope_winding 的 `run_from_config`） |
| | bar_through_hole | `bar_through_hole_physical_insert_demo` |
| | ring_transfer | `ring_transfer_physical_demo` |

`topogym/tasks/deformation/` 目前是空的，这里不建对应目录。

## 配置方式

全部 demo 用 Hydra，参数是配置路径，没有 `--flag`。
2026-08-10 起 argparse 配置体系已从仓库删除，`demos/legacy/` 的 5 个 demo 同时删除。

```bash
python -m demos.entangle.untangle_continuous_physical_pinch_demo
python -m demos.entangle.untangle_continuous_physical_pinch_demo run.viewer=true run.keep_open=true
python -m demos.entangle.untangle_continuous_physical_pinch_demo task.rope.mesh.segment_length=0.004
python -m demos.entangle.untangle_continuous_physical_pinch_demo --cfg job   # 只打印解析后的配置
python -m demos.entangle.untangle_continuous_physical_pinch_demo -m run.seed=0,1,2   # 扫参

swap_crossing_sign 另有一个选择第二步压哪根绳的开关，两个取值构成它的 contrast pair：
```bash
python -m demos.entangle.swap_crossing_sign_physical_pinch_demo                          # oracle：压另一根，符号翻转
python -m demos.entangle.swap_crossing_sign_physical_pinch_demo run.oracle_mode=restack_same  # 对照：压回同一根，预期失败
```

覆盖整组配置用组名：`env_configs@env=world_tabletop_v1`、`recording=hq`、
`task_configs@task=cable_routing_topogym_tabletop_v1`。

每次运行会在 `runs/hydra/<日期>/<时间>/.hydra/` 留下三份文件：`config.yaml`（本次完整配置）、
`config_resolved.yaml`（同一份但引用已展开，直接可读）、`overrides.yaml`（本次命令行给的覆盖）。
它们的用途是事后回答"这次跑用的什么参数"——此前有三次运行因为答不上这个问题而作废。

| demo | 主配置 | 运行模式配置 |
| --- | --- | --- |
| `entangle/swap_crossing_sign_physical_pinch_demo` | `configs/swap_crossing_sign_pinch.yaml` | `configs/run_configs/swap_crossing_sign.yaml` |
| `entangle/untangle_continuous_physical_pinch_demo` | `configs/untangle_continuous_pinch.yaml` | `configs/run_configs/untangle_continuous.yaml` |
| `entangle/untangle_continuous_fem_demo` | `configs/untangle_continuous_fem.yaml` | `configs/run_configs/untangle_continuous_fem.yaml` |
| `entangle/untangle_continuous_inspect_demo` | `configs/untangle_continuous_inspect.yaml` | `configs/run_configs/untangle_continuous_inspect.yaml` |
| `entangle/untangle_physical_handle_demo` | `configs/untangle_handle.yaml` | `configs/run_configs/untangle_handle.yaml` |
| `connectivity/stacked_plate_physical_rotate_demo` | `configs/stacked_plate_rotate.yaml` | `configs/run_configs/stacked_plate_rotate.yaml` |
| `connectivity/stacked_plate_inspect_demo` | `configs/stacked_plate_inspect.yaml` | `configs/run_configs/stacked_plate_inspect.yaml` |
| `routing/cable_routing_physical_handle_demo` | `configs/cable_routing.yaml` | `configs/run_configs/cable_routing.yaml` |
| `routing/rope_winding_physical_handle_demo` | `configs/rope_winding.yaml` | `configs/run_configs/rope_winding.yaml` |
| `routing/rope_unwinding_physical_handle_demo` | `configs/rope_unwinding.yaml` | `configs/run_configs/rope_unwinding.yaml` |
| `routing/bar_through_hole_physical_insert_demo` | `configs/bar_through_hole.yaml` | `configs/run_configs/bar_through_hole.yaml` |
| `routing/ring_transfer_physical_demo` | `configs/ring_transfer.yaml` | `configs/run_configs/ring_transfer.yaml` |

`tests/fem_ipc_rope_spike.py`（FEM 后端诊断场景）用同一套方式，主配置
`configs/fem_ipc_rope_spike.yaml`。仓库里的检查与测量都在 `tests/`，见
[`../tests/README.md`](../tests/README.md)。

## 只验管线，不跑物理

```bash
python -m demos.entangle.untangle_physical_handle_demo run.build_only=true
python -m demos.entangle.untangle_physical_handle_demo run.bench_steps=100   # 量一步多少毫秒
```

走完配置解析、`derive_config`、场景构建、契约校验、primitive 构造就退出，约 90 秒。
它跳过物理，**不是提速**——完整物理跑仍然是 46 分钟（2026-08-11 实测，untangle 三绳
FEM+IPC 场景）。

判据：改动只涉及参数怎么传、场景怎么搭，用 `run.build_only=true`；改动涉及物体
怎么动，跑完整的。八个 demo 都认这个开关，`tests/check_demo_configs.py` 的形态表
会检查这一点。

`run.bench_steps=N` 把建好的场景空跑 N 步并报每步耗时。场景静止、机械臂不动，量到的是
一步的地板价。与真实运动时的速率对比可以分开两件事：两者接近说明成本在静止求解（看网格
与 IPC 预算），运动时明显更慢说明成本来自接触下的 Newton 迭代（IPC 预算是直接旋钮）。
判据写在 `topogym/supervision/step_bench.py`。

**目前没有已知有效的提速旋钮。** 2026-08-11 实测：静止场景 660 ms/步，其中求解器
643 ms、每步钩子 17 ms（3%）。把 Newton 上限从 1024 降到 64、把网格从约 3000 个四面体
降到 2048 个，两者都没有改变耗时。测量过程与已排除的假设见
[`../docs/develop/physics/fem_ipc_step_cost_zh.md`](../docs/develop/physics/fem_ipc_step_cost_zh.md)。

**不要用降 `env.sim.substeps` 提速。** 它确实是四倍算力（IPC 每 substep 求解一次），
但 `substeps=1` 已经在 FEM 预设 v1.0 试过并被推翻：刚体子步变 10ms 后，边缘搁置的
自由端插头走位 21mm/百步。`topogym/world/tabletop.py` 的锁定预设校验会直接拒绝这个
覆盖。理由写在 `configs/env_configs/world_tabletop_fem_v1.yaml` 文件头。

## 已删除的 legacy demo

2026-08-10 删除 `demos/legacy/`（swap / onestroke / maze_wall_removal / peeling 四个
demo 加录制批处理 `record_physical_demos`，共 2242 行）。它们是 argparse 配置体系仅剩的
使用者，而这些任务已不在主线范围。

它们的任务代码 `topogym/tasks/legacy/` 保留：`topogym/envs/` 下的 `swap_mdp.py`、
`onestroke_mdp.py`、`maze_wall_removal_mdp.py` 三个 RL 环境壳还在用。
`configs/task_configs/` 下对应的四份任务配置同样保留。
