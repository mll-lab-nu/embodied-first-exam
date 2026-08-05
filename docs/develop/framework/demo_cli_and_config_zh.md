# demo 命令行参数与配置的归属

> 状态：**已盘点，未开工**。本文记录现状、已发生的问题、参数三分类，以及分两步的计划。
> 盘点日期 2026-08-05，范围是 `prototypes/*_demo.py` 共 11 个（legacy 任务不计）。

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

### (b) 运行模式 —— 不进 configs/

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

## 6. 计划

### 第一步（针对已发生的三次问题，风险最低）

| 项 | 改动 | 挡住什么 |
|---|---|---|
| 1. 加 `--set key=value`（可重复），用 `OmegaConf.from_dotlist` 合并 | 约 5 行 | 让任何 config 键都能从命令行覆盖，19 处手写 merge 可删 |
| 2. 配置加载后开 struct 模式 | `topogym/core/config.py` 加一行 | 路径拼错立刻抛异常 |
| 3. 把实际生效的覆盖打印到 stdout 并写进 trace header | 已在 `untangle_continuous_physical_pinch_demo` 局部实现（摩擦 / substeps / preset_locked 四个字段），需推广 | 运行结束后可确认参数是否生效 |
| 4. 抽 `add_standard_demo_args(parser)`，收拢 (b) 类的 27 个 | 纯增量，各 demo 删掉重复定义 | 第 4 节的 `--close-on-finish` 与 viewer 退出三套冲突 |

第 2 项落地前需逐个确认哪些是合法的动态加键。`merge_recording_config` 就是把整个
`recording` 节加进配置的，开 struct 之后行为需要复核。

### 第二步（等第一步稳定，且要做批量扫参时）

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

- `@hydra.main` 接管 `main()`，启动方式由 `python -m prototypes.x --flag v` 变为
  `python -m prototypes.x flag=v`。全部现有命令行、`bash_scripts/` 下的脚本、文档中的
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
