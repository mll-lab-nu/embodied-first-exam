# demo 命令行参数与配置的归属

> 状态：**进行中**。§1~§5 是 2026-08-05 的盘点（当时 `prototypes/` 平铺，11 个 demo、
> 82 个参数），保留作为问题的记录。§6 的计划已被取代，实际走向见下方「实际进展」。
>
> 2026-08-10 复盘时参数已涨到 97 个、参数驱动的 merge 点 32 处，说明问题在扩大而非收敛。

---

## 1. 现状

11 个 demo，命令行参数并集 **82 个**。

真正共用的只有两个助手函数：

| 助手 | 位置 | 提供的参数 | 被几个 demo 调用 |
|---|---|---|---|
| `add_common_config_arg` | `topogym/core/config.py:13` | `--common-config` | 9 |
| `add_recording_args` | `topogym/utils/recording.py:30` | `--record-video` / `-fps` / `-camera` / `-every-n-steps` / `-res` / `-aa` | 9 |

其余全部由每个 demo 自己 `parser.add_argument`。其中一批是**每个 demo 各写一遍的同一批参数**：

| 参数 | 出现在几个 demo |
|---|---|
| `--backend` | 11 |
| `--viewer` | 11 |
| `--env-config` / `--robot-config` / `--task-config` | 10 |
| `--seed` | 10 |
| `--verbose` | 10 |
| `--keep-open` | 9 |

8 个参数 × 约 10 个 demo，合计约 80 处重复定义。`--seed` 的默认值还不一致：
`maze_wall_removal_physical_demo` 是 11，其余是 0。

## 2. 同一件事有四套机制

"命令行参数覆盖配置"这件事，在仓库里有四种并存的实现：

| 机制 | 做法 | 覆盖范围 |
|---|---|---|
| 1 | `OmegaConf.merge(cfg, {...})` | demo 里共 27 处调用，其中 19 处由命令行参数驱动，覆盖 10 个不同的 config 路径 |
| 2 | 直接读 `args.x`，完全不经过配置 | 约 60 个参数 |
| 3 | `_primitive_value(scene, "move_steps", args.move_steps)`，flag 为 `None` 时回落到配置 | `peeling_physical_demo` 自己写的 |
| 4 | 只有配置键，没有对应 flag | 例如 `untangle_continuous` 的 `pinch.move_steps` |

机制 2 与机制 4 会撞车：`peeling` 的配置里本来就有 `move_steps: 70`、`grasp_qpos: 0.006`，
同时又有同名 flag。同一个量在两处定义。

配置本身**不是 struct 模式**（`topogym/core/config.py:42-49` 只做 `OmegaConf.load` +
`OmegaConf.create`，全仓库唯一一处 `set_struct` 在 `generation/layout_randomization.py:144`，
且是把它关掉）。因此机制 1 里写错路径不会报错：

```python
cfg = OmegaConf.merge(cfg, {"task": {"braid": {"lenght": 1}}})   # 拼错
```

会新增一个 `lenght` 键，程序照常跑完，读到的仍是原来的 `length`。

## 3. 已经发生的问题

2026-08-03 至 08-05 期间，由这套机制直接造成的三次运行作废：

| 事件 | 表现 | 原因 |
|---|---|---|
| 要一处交叉，跑出三处 | 视觉上直到被指出才发现 | 配置 `braid.length: 1` 与 demo 常量 `_DIFFICULTY_LENGTH["easy"] = 2` 是两个来源，传 `--difficulty default` 覆盖成 3 |
| 一次运行既无 viewer 也无 trace | 进程正常退出，看起来像跑完了 | 命令行里用了 shell 变量，变量未定义时展开为空，argparse 不报错 |
| `bar_through_hole` 每次运行都崩 | 报 `Missing key recording` | `merge_recording_config` 返回新对象，该 demo 丢弃了返回值 |

共同形态：**参数没生效和参数生效了，产物长得一模一样。**

## 4. 已确认的冲突

| 冲突 | 详情 |
|---|---|
| `--close-on-finish` 同名反义 | cable_routing / untangle / stacked_plate 用 `store_true`；maze_wall_removal 用 `store_false` |
| viewer 退出有三套 | `--keep-open`（9 个）、`--close-on-finish`（4 个）、`--keep-open-no-step`（2 个）。maze 与 stacked_plate 同时具备前两者 |
| onestroke 的三组反义参数 | `--stop-on-terminal` / `--no-stop-on-terminal`、`--continue-on-failure` / `--stop-on-failure`、`--edge-support` / `--no-edge-support`。同时传互相矛盾的两个没有校验 |
| `--difficulty` 类型与默认值不一致 | cable_routing / peeling / stacked_plate / untangle 是自由 str，默认 `'default'`；untangle_continuous 两个是 choice，默认 `None`。`None` 表示不覆盖配置，`'default'` 表示覆盖成 default 档，语义不同而同名 |
| 两套 record 命名相似机制无关 | `--record-video`（helper，出 mp4，走 `cfg.recording`）与 `--record-dataset`（3 个 demo 各自定义，出 H5，走另一条路径） |

## 5. 参数三分类

### (a) 场景与物理定义 —— 应在 configs/，命令行只作覆盖入口

约 35 个：

```
--segment-length --radial-segments --rope-static-friction --rope-kinetic-friction
--grasp-qpos --gripper-steps --move-steps --lift-steps --place-steps --settle-steps
--motion-steps --close-hold-steps --place-hold-steps --release-hold-steps
--between-moves-settle-steps --finger-friction --wall-friction --block-friction
--noslip-iterations --no-friction-override --lift-check-delta --min-lift-delta
--max-grasp-xy-error --max-grasp-attempts --arc-steps --edge-support --strands
--max-walls --max-waypoints --target-angle-degrees --target-xy-bias --target-yaw-bias
--grasp-yaw --source-slot --target-slot --block
```

这批里绝大多数**配置里已经有对应键**，flag 是第二份定义。

### (b) 运行模式 —— 进 configs/ 的 `run` 组

> 2026-08-10 更正：08-05 写的是「不进 configs/」。引入 Hydra 后它们必须是配置字段，
> 只是单独放在 `run` 组里与场景定义分开。判据不变。

约 27 个：

```
--viewer --keep-open --keep-open-no-step --close-on-finish --verbose --backend
--trace --trace-every --record-video --record-fps --record-camera --record-res
--record-aa --record-every-n-steps --record-dataset --dataset-every-n-steps
--probe --probe-every --no-build --no-robot --inspect-only --lite --seeds
--slow-factor --viewer-speedup --env-config --robot-config --task-config --common-config
```

判据：同一份 config 配上不同的这些参数，物理结果应当相同。它们描述"这一次怎么跑"。

### (c) 实验与诊断覆盖 —— 临时，需明确标注

```
--grasp-strand --substeps --randomize-layout --max-moves --run-oracle --oracle-mode
--rotate-to-target --continue-on-failure --stop-on-failure --stop-on-terminal
--no-stop-on-terminal --allow-target-lag --hide-peel-zones
```

有了通用覆盖入口之后，这批里对应 config 键的可以删掉，改用覆盖语法。
只有不对应任何 config 键的诊断开关需要保留，例如 `--grasp-strand`。

### 特例

| 参数 | 说明 |
|---|---|
| `--seed` | 决定场景（属 a），但每次运行都要换（用起来像 b）。放 configs/ 给默认值，命令行覆盖 |
| `--difficulty` | 现阶段只作为占位参数存在，不接难度轴逻辑。它现有的类型与默认值分歧留到做难度轴时一并处理 |
| `--substeps` | 被 `topogym_tabletop_v1` 冻结基线锁死为 4（`topogym/world/tabletop.py:453`）。命令行覆盖需同时设 `env.preset.locked=false`，那会关闭全部基线校验 |

---

## 6. 实际进展（2026-08-10 起）

08-05 的计划是「先加 `--set` 与 struct 模式，等要批量扫参时再上 Hydra」。
实际决定直接引入 Hydra，跳过 `--set` 那一步——两者的覆盖语法一致，
先做 `--set` 再换 Hydra 等于同一件事做两遍。

已完成：

| 项 | 内容 |
|---|---|
| FEM 参数归位 | `rope_backends/fem_ipc.py` 的 `_DEFAULTS` 六个值搬进 `configs/prefab_configs/` 的 `rope_fem` 块，三个任务配置转引；`_fem_value` 缺键时报错而非静默回落 |
| 主配置与 config group | `configs/config.yaml` + `configs/run_configs/`；目录名不改，用 `组名@包名` 落到既有包路径，读取侧代码与 40 多个 yaml 未改动 |
| 等价性验证 | `scripts/check_hydra_compose_equivalence.py`，10 个任务配置、455~727 个键，Hydra compose 与 `load_topogym_configs` 逐键一致 |
| 目录整理 | `prototypes/` → `demos/`，分类与 `tasks/` 对齐；模块路径引用更新 |
| 两处落地问题 | Hydra 的 root logger 重复输出（关掉 `job_logging`）；存档未展开插值（另存 `config_resolved.yaml`） |
| 8 个主线 demo 迁移 | 全部完成，见下表 |

### 迁移结果（2026-08-10）

| demo | 行数 | 手写 merge |
|---|---:|---:|
| `entangle/untangle_continuous_physical_pinch_demo` | 774 → 578 | 11 → 0 |
| `connectivity/stacked_plate_inspect_demo` | 78 → 65 | 1 → 0 |
| `routing/bar_through_hole_physical_insert_demo` | 324 → 287 | 0 → 0 |
| `connectivity/stacked_plate_physical_rotate_demo` | 330 → 261 | 1 → 0 |
| `entangle/untangle_continuous_inspect_demo` | 291 → 151 | 8 → 0 |
| `entangle/untangle_continuous_fem_demo` | 601 → 524 | 2 → 0 |
| `entangle/untangle_physical_handle_demo` | 912 → 764 | 5 → 0 |
| `routing/cable_routing_physical_handle_demo` | 1276 → 1065 | 9 → 0 |
| 合计 | 4586 → 3695 | 37 → 0 |

保留的 `OmegaConf.merge` 只剩每个 demo 的 `derive_config()`：那里合并的是**由其它
配置值算出来的**内容（例如端点把手的尺寸取自 `task.physical_handle`），写成配置字面量
会与几行之外的值重复。可选的固定数值组（例如低分辨率绳）已搬进任务配置的 `rope.lite`
块，由 `run.lite` 选中。

### 第二轮：删除 argparse 体系（同日）

第一轮的判断是「legacy demo 保持 argparse 不动」，结果留下两套并存的参数体系。确认
legacy 任务已被放弃后改为彻底移除：

| 删除 | 规模 |
|---|---|
| `demos/legacy/` 五个文件 | 2242 行、102 个 `add_argument` |
| `topogym/core/config.py` 的 `load_topogym_configs`、`add_common_config_arg` | 43 行 |
| `topogym/utils/recording.py` 的 `add_recording_args`、`recording_config_from_args`、`merge_recording_config`、`_default_recording_config` | 83 行 |
| `bash_scripts/lib/demo_cli.sh` | 只为翻译两套语法而存在 |
| `scripts/check_hydra_compose_equivalence.py` | 比对对象没了；compose 那半保留为 `check_configs_compose.py` |

连带处理：

- `topogym/data/replay.py` 删 `_setup_swap`，该文件从此只有 Hydra 一套机制。副作用：
  swap 是唯一评估 success 的任务，`--require-success` 此后无法通过，已在 docstring 与
  参数帮助里写明。
- `tests/fem_ipc_rope_spike.py` 迁 Hydra（450 → 368 行）。它标定出的数值就是
  `prefabs.rope_fem` 那一组，此前这些量是 CLI 专属的，配置里查不到某次跑用了什么值；
  现在 `--e` / `--nu` / `--rho` / `--friction-mu` / `--d-hat` / `--strength` 分别对应
  `task.rope.fem.E` / `.nu` / `.rho` / `.friction_mu` / `.contact_d_hat` /
  `.follow_strength`，与 demo 读的是同一处。迁移前后默认值逐项相同。
- 四个 bash 脚本的任务注册表去掉 legacy 项，参数直接写 Hydra 点路径。
  `record_all_tasks.sh` 顺带补上此前漏登记的 bar_through_hole。

`topogym/tasks/legacy/` 与 `configs/task_configs/` 下四份任务配置**保留**：
`topogym/envs/` 的三个 RL 环境壳仍在 import。

保留 argparse 的地方只剩三个纯工具 CLI —— `topogym/data/replay.py`、
`scripts/export_h5_lerobot.py`、`scripts/register_openpi_config.py`。它们接的是文件路径
与容差，不加载任何 topogym 配置，不属于本文讨论的参数体系。

### 迁移中出现的两类缺陷与静态检查

实跑暴露两类缺陷，都在各 demo 自己的 Python 代码里，共用的配置体系没有问题：

| 缺陷 | 机理 | 命中 |
|---|---|---|
| merge 往 struct 配置里加新键 | Hydra 交给 `main` 的配置带 `struct=True`，只能改已有键；被它替换掉的加载路径从不设这个标志，于是 demo 一直在运行时加 yaml 里没有的键 | 5 个键，2 个 demo |
| 漏删的 `args` | `run_demo(args, cfg, ...)` 改成 `run_demo(cfg, ...)` 时只改了函数体 | 2 个 demo |

两类都可静态判定，固化为 `tests/check_demo_configs.py`（标准库 + PyYAML，无需 GPU）：
未定义名（`symtable`）、merge 加新键（`ast` 抽键路径比对 yaml）、`cfg.run.X` 是否在 run
配置链里、以及一张七列的迁移形态指纹表。该脚本自身做过注入自检：两类缺陷各注入一次，
均被报出并使退出码为 1。

查不出的部分：带默认值的 `getattr` 动态访问、迁移时值取错、物理行为。

### 已作废：08-05 的第一步（针对已发生的三次问题，风险最低）

| 项 | 改动 | 挡住什么 |
|---|---|---|
| 1. 加 `--set key=value`（可重复），用 `OmegaConf.from_dotlist` 合并 | 约 5 行 | 让任何 config 键都能从命令行覆盖，19 处手写 merge 可删 |
| 2. 配置加载后开 struct 模式 | `topogym/core/config.py` 加一行 | 路径拼错立刻抛异常 |
| 3. 把实际生效的覆盖打印到 stdout 并写进 trace header | 已在 `untangle_continuous_physical_pinch_demo` 局部实现（摩擦 / substeps / preset_locked 四个字段），需推广 | 运行结束后可确认参数是否生效 |
| 4. 抽 `add_standard_demo_args(parser)`，收拢 (b) 类的 27 个 | 纯增量，各 demo 删掉重复定义 | 第 4 节的 `--close-on-finish` 与 viewer 退出三套冲突 |

第 2 项落地前需逐个确认哪些是合法的动态加键。`merge_recording_config` 就是把整个
`recording` 节加进配置的，开 struct 之后行为需要复核。

### 已作废：08-05 的第二步（等第一步稳定，且要做批量扫参时）

引入 Hydra。`hydra-core==1.3.2` **已经安装并在 `requirements/uv-topogym-gs110.txt`
钉住**，全仓库无任何 `import hydra`；`recording.py` 的注释写着 "Hydra-friendly config
section"，说明当初就是朝这个方向设计的。所以不增加依赖。

| Hydra 能力 | 对应痛点 | 价值 |
|---|---|---|
| 命令行点路径覆盖 | 四套机制、19 处手写 merge | 高 |
| structured config（dataclass schema） | 路径拼错静默失效、类型不一致 | 高 |
| multirun 扫参 | `bash_scripts/tests/rope_contact_sweep.sh` 是手写的三重循环 | 高 |
| defaults 组合 | `load_topogym_configs` 手写拼 5 段 | 中 |

代价：

- `@hydra.main` 接管 `main()`，启动方式由 `python -m demos.<组>.<demo> --flag v` 变为
  `python -m demos.<组>.<demo> flag=v`。全部现有命令行、`bash_scripts/` 下的脚本、文档中的
  命令都要改。
- Hydra 1.3 默认 chdir 到输出目录，会打断 `runs/`、`.cache/topogym/meshes/` 这些相对路径。
  需 `hydra.job.chdir=False`。
- (b) 类的运行开关进入配置树，会把"这次怎么跑"与"场景是什么"放进同一棵树。

第一步的 `--set` 语义与 Hydra 的覆盖语法一致，届时是替换而非重写。

---

## 7. 不在范围内

- legacy 任务的 demo。
- `--difficulty` 的难度轴逻辑。现阶段只保留参数占位。
- (a) 类 35 个参数的删除。要等 `--set` 落地后才好动，因为它们大多是被删而不是搬家。
