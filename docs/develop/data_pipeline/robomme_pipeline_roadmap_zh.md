# RoboMME 式产物 · 单任务落地路线图（第 1–6 层）

> 日期：2026-07-18
> 关系：本文件是**可执行路线图**；它的现状分析依据在 `robomme_benchmark_deliverables_zh.md`（那份是**分析**，本份是**行动计划**）。两者配合读。
> 目标读者：接着往下把 TopoGym 从"环境/demo"推到"benchmark 产物"的人。

---

## 1. 背景与目标

`robomme_benchmark_deliverables_zh.md` 第 3.5 节（基于实际代码核对）的结论：我们目前只做出了

- 第 1 层的一半：`EpisodeKey/EpisodeSpec` 身份对象（`topogym/generation/episode_spec.py`）；
- 第 6 项的一半：`PlannedSubgoal` 结构（`topogym/planning/subgoal.py`）。

最关键的缺口是**没有逐帧 obs/action/info 的结构化数据集，也没有对外合约文档**——当前录制产物只有 `topogym/utils/recording.py` 产的 mp4。

**本路线图的终点画在第 1–6 层**：产出一份**可下载、可回放、有成文合约**的单任务数据集。

- 落地顺序：先在已稳定的刚体任务 **swap** 上把"固化 seed → 逐帧录制 H5 → replay 自校验 → 成文合约"这条链路跑通（验机，不与 PBD 物理不稳互相污染），再把同一套接口灌到 **cable_routing**（最高风险的 PBD 任务），最终用 cable_routing 端到端产出数据集。
- **不在本次范围**：评测协议（第 7 层）、基线 IL（第 8 层）。留作下一阶段。

### 明确排除项

**让 generator 真正按 seed 随机化布局**不在本次范围。当前 swap/cable_routing 的 layout 是确定性的（`swap_generator.py` 注释："seed reserved for future randomization"）。本次 seed 只用于**固定 episode 身份**（与 RoboMME "按编号点名 episode"一致），不改场景布局，也不阻塞数据管线。让 generator 真随机化是一个独立的后续任务。

---

## 2. Schema 保真度决策

对 RoboMME 的 `h5_data_format.md`：**结构保真、字段取子集、差异成文**。

- **采纳 RoboMME 的 HDF5 群组骨架**（几乎零成本，换来他们的 `dataset_replay` 心智模型和未来 Pickle/LeRobot/TF 转换器）：
  `episode_<N>/setup/...` + `episode_<N>/timestep_<K>/{obs, action, info}`。
- **只存我们真正产得出的字段**，字段名沿用 RoboMME（有真实对应的才用）：
  - `obs`：`front_rgb`(+ 若有 wrist 相机则 `wrist_rgb`)、`eef_state`(xyz+rpy)、`gripper_state`、`is_gripper_close`；`joint_state` 能拿到就存。
  - `action`：`ee_pose_action`(7, controller 绝对末端目标) + `waypoint_action`(7, planner 的 `WaypointTarget`)。我们天然同时有这两种表示。
  - `info`：`task_goal`、`simple_subgoal`（当前 `PlannedSubgoal.label`）、`is_subgoal_boundary`、`is_completed`、`status`。
- **不伪造 RoboMME-VLA 专属字段**：`joint_action`、`choice_action`/`multi_choice`、`grounded_subgoal`（带空间指代）、`is_video_demo`。在合约文档里显式标为 **reserved / 差异**，等真正产得出时再补——避免 dead fields，同时让缺口可见、可闭合。

---

## 3. 工作项 · 优先级 · 依赖

```
W1, W2  (P0, 便宜, 互不依赖)          ← 已完成（本轮）
   └─> W3  (P1, 关键路径核心)
          └─> W4  (P1, 先 swap 验机, 再 cable_routing)
                 └─> W5  (P2, replay 自校验, 依赖 W1+W3+W4)
W6  (P2, 合约文档, schema 定死后可与 W3/W4 并行)
```

### P0 — 地基（便宜，解锁一切）

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| **W1** | 固化 seed split + episode 点名寻址 | `configs/episode_splits/swap.yaml`；`topogym/generation/episode_index.py`（`load_split` / `split_seeds` / `make_episode_spec` / `iter_episode_specs`） | ✅ 本轮完成（仅 swap） |
| **W2** | `EpisodeResult` 加 `status` 枚举 `{success,fail,timeout,error,ongoing}` | `topogym/generation/episode_spec.py`（`EpisodeStatus`）；swap demo 结果行输出 status | ✅ 本轮完成 |

### P1 — 核心工程：录制器 + H5 schema

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| **W3** | 逐帧数据集写入器（关键路径）。复用 `recording_session` 的 `scene.step` 包裹法采 obs/action/info；`setup/` 从 `EpisodeSpec` 落盘。新依赖 `h5py`；新建 `topogym/data/` 包（`h5_schema.py` + `episode_dataset_writer.py`，命名区别于 video recording） | `topogym/data/` | ✅ 完成（含 `EpisodeDatasetWriter`；action=下一帧绝对 eef 位姿；wrist 相机 render 前调 `update_dynamic_camera`） |
| **W4** | 各 demo 接 `--record-dataset` + `--dataset-every-n-steps`；用 `dataset_writer_or_null` helper 在 main 层套写入器，`status` 作 in-place 参数供 subgoal_label_fn 读 | swap / untangle / cable_routing demo | ✅ swap + untangle + cable_routing 三个都已接（PBD 用 status→subgoal 标签） |

### P2 — 自校验 + 合约文档

| 项 | 内容 | 落点 | 状态 |
| --- | --- | --- | --- |
| **W5** | `dataset_replay` 式自校验：读 H5 → 从 seed 重建环境 → 开环回放存下的 action → **eef 轨迹跟踪为硬门** + 成功率报告（`--require-success` 可选硬门） | `topogym/data/replay.py` + `bash_scripts/tests/replay_dataset.sh` | ✅ 完成（swap；不渲染，快） |
| **W6** | 成文对外合约：`env_format_zh.md`（obs/action/status/坐标系）+ `h5_data_format_zh.md`（镜像 RoboMME schema，含"与 RoboMME 差异"专节）。理想上 schema 文档先于代码定死 | `framework/env_format_zh.md` + `data_pipeline/h5_data_format_zh.md` | ✅ 完成（2026-07-22；含 π0.5 下游消费的实测形状） |

---

## 4. 验证方式（端到端 CLI；sim 测试由跑的人本人执行）

> 全部命令**在 repo 根目录、激活 venv 后运行**。demo 一律用 `python -m prototypes.<name>`（模块形式）而**不是** `python prototypes/<name>.py`——本 repo 没有 pyproject/setup，`topogym` 靠 repo 根在 `sys.path` 上才可导入，只有 `-m` 从根目录跑才满足（见 `cli_commands.txt`、`bash_scripts/record_all_tasks.sh`）。

W1/W2（本轮，纯 Python，无需 Genesis）：

```bash
# W1：split 寻址
python -c "from topogym.generation import load_split, split_seeds; \
print(load_split('swap')); assert split_seeds('swap','test')==[200,201,202,203,204]"
# W2：status 枚举
python -c "from topogym.generation import EpisodeKey, EpisodeResult, EpisodeStatus as S; \
k=EpisodeKey(task_id='swap',seed=0); \
assert EpisodeResult.ok(k).status is S.SUCCESS; \
assert EpisodeResult.failed(k,'boom',status=S.ERROR).status is S.ERROR; print('W1+W2 OK')"
# 冒烟：结果行里应出现 status=...
python -m prototypes.swap_physical_grasp_demo --seed 0
```

W3（数据集录制，已实现）—— 一键录制+结构检查：

```bash
# 通用验证脚本：录一条 H5 并用 h5py 断言检查结构/字段（默认 swap）
bash bash_scripts/tests/verify_dataset_recording.sh
# 环境变量可调：BACKEND=cpu SEED=0 EVERY=10 OUTDIR=... 见脚本头注释
```

W4–W5（后续）：

```bash
# 手动等价：swap 录制
python -m prototypes.swap_physical_grasp_demo --seed 0 --record-dataset <out>/swap_ep0.h5
# 看 H5 结构
python -c "import h5py; h5py.File('<out>/swap_ep0.h5').visit(print)"
# replay 自校验（脚本同样需在 repo 根用 -m 跑）
python -m scripts.dataset_replay <out>/swap_ep0.h5
# cable_routing 端到端（接进同一套接口后）
python -m prototypes.cable_routing_physical_handle_demo --seed 0 --backend gpu --record-dataset <out>/cable_ep0.h5 --close-on-finish
```

> cable_routing 的 demo 不接受 `--keep-open`，用 `--close-on-finish`。
