# Harbor 评分链与终态可达性审查

**合并后的当前状态以[问题复核报告](run_trials_post_merge_audit_20261001_zh.md)为准。** 下文保留原冻结版本的审查证据；0.2.5-cu128 已包含 IPC 修正，Knot 和 standard 流程也有后续改动。

记录日期：2026-10-01。范围：`tasks/` 下 106 个 Harbor 任务目录（13 个正式任务各有 1 个不分档实例和 easy、medium、hard 三个分档实例，外加 Cube 样板；每个实例分 unlimited 和 limited 两种模式），以及它们共用的评分脚本与 `topogym/tasks/` 成功判据。

**范围补充（同日旧镜像使用核查）：** 本文的旧镜像问题只针对冻结任务包/固定镜像入口，不计入当前新 `run_difficulty_trials.sh` 的 bug 数。新入口按源码身份构建独立镜像；旧包仍保留依赖，因此本轮没有删除镜像。当前问题清单以[全链路审查报告](run_trials_full_audit_20261001_zh.md)为准，使用与保留依据见[镜像核查记录](../../runs/test_results/run_trials_audit_20261001/image_usage_followup/README.md)。本文其余部分保留原检查证据，不作为新 runtime 已验证或存在同一缺陷的结论。

**冻结包检查结果：** 当时未发现评分逻辑错误的结论已被后续全链路审查中的复现补充；下列是原检查记录的固定版本问题：

- 不分档实例中有 8 类，用的旧镜像里成功判定开关是关着的；
- IPC 机械臂方向修正没有进任何镜像，带绳的 4 个任务都受影响；
- 多个可变形物体任务的时间预算撑不起已知最短路线；
- 少数判据和物理状态不相容。

目前通过本评分脚本拿到 1 分的只有 Cube 样板。13 个正式任务在 Harbor 时序下一次 `task_success=True` 都没有。

**方法与边界：** 本次全程只读，没有运行模拟器、GPU 或 Harbor 作业。检查分 5 组并行进行；镜像内容是用 `docker create` 加 `docker cp` 拷出来读的，没有启动容器。下文条目分两种：

- 标"已核"的，是本文作者亲自对过代码、镜像或数据；
- 未标的，是审查时依据所附证据得出的结论。

推断项集中列在第 7 节。本文不改任何代码，也不改任何已有结果。

## 1. 评分怎么判

**具体场景：** agent 在容器里调试完，交出 `/app/output/trajectory.npz`。这是一个 (T, action_dim) 的 JOINT_ABS 动作表，每行对应一个 25 ms 控制步。verifier 在另一个新进程里重建同一个冻结场景，按行把动作回放两次；两次都满足 Task 成功，才写 `reward.txt = 1`。

调用链：`tests/test.sh` → `tests/grade.py` → `rcb_topogym.Session.replay` → `env.is_solved()` → `Task.result.task_success`。

**成功的含义**（`topogym/tasks/base.py` 的 `TaskDefinition.update`）——每个物理 tick 都检查以下条件：

- `goal_complete` 为真。这是"是否允许判成功"的开关；当前源码里所有任务都是 True。
- 这一 tick 的目标判据达到（`evaluate_state` 返回 reached），且没有失败原因。
- 证据可用：`evaluation_status == "available"`。
- 上面三条连续保持 `stable_duration_s`（多数任务 0.5 s，Hedgehog 2 s，Buzz 1 s）。中间任何一个 tick 不满足，计时清零。

要求松手的任务（Coil、Buzz、Knot、Blanket）还要通过**静置确认**（`final_settling_spec`）：抓持辅助已解除；机器人碰撞盒与物体碰撞盒相距至少 5 mm；物体速度和窗口内漂移都在阈值内。

任何失败原因（掉下桌面 100 mm、接触穿透超限、Buzz 魔杖碰线、Fiber 夹爪碰细芯等）都会当场结束这一局。

**Harbor 时序：**

- 分档实例：`physics_dt_s = 0.0025`、`solver_substeps = 4`、`control_decimation = 10`、CUDA。也就是每个控制步跑 10 个物理 tick，每 2.5 ms 检查一次 Task。
- 不分档实例的 `instance.json` 没写这几项，取 `SimulatorConfig` 默认值，数值相同。
- 已归档的可解性证明全部是 CPU float64、25 ms tick、40 子步，每 25 ms 才检查一次 Task。因此证明不能直接说明 Harbor 实例可达。

**两类实例：**

| 类型 | 目录 | 镜像 | 抓持辅助 |
|---|---|---|---|
| 不分档 | `tasks/topogym-<task>-i00[-limited]`，dataset 里组织名为 `topogym/` | `rcb-topogym:0.1.0` | 全部没有。instruction 写 "physical grasping only"（Claws 例外，有 `contact_weld_v1`） |
| 分档 | `tasks/topogym-<task>-{easy,medium,hard}-i00[-limited]`，组织名为 `robot-coding-bench/` | `rcb-topogym:0.2.3-cu128` | 刚体任务用 `contact_weld_v1`；绳、布、纤维任务不用 |

**哪些运行路径用到这些目录：**

| 路径 | 用的任务目录 | 判据代码来源 |
|---|---|---|
| 难度试验：`bash_scripts/run_difficulty_trials.sh` → `scripts/difficulty_eval.py` | 不读 `tasks/`。按 `configs/sweeps/difficulty_eval.yaml`，每个任务每档抽一个 `seeded` 实例（seed = 3q + 档位），在运行目录里现场生成 unlimited 和 limited 任务目录 | 启动时复制当前工作区（含未提交改动），建成 `topogym-local/rcb-topogym-difficulty:<源码哈希>` 镜像 |
| 分档 agent sweep | `tasks/topogym-<task>-{easy,medium,hard}-i00[-limited]`，seed 0 | `rcb-topogym:0.2.3-cu128` |
| 手册示例与 dataset 发布 | `docs/rcb/README.md` 第 38、165–278、307 行的 `harbor run` 和 `run_agent_batch.sh` 示例都用不分档目录；`tasks/dataset.toml` 仍收录 28 个不分档条目 | `rcb-topogym:0.1.0` |

所以第 3.1 节只影响按手册示例运行或发布 dataset 的情况；难度试验和分档 sweep 不受影响。第 3.2 节影响分档 sweep；对难度试验，只影响修正写进工作区之前启动的运行。另外，手册第 185 行的通配 `-i 'topogym-*-i00'` 同时匹配不分档目录和分档的 unlimited 目录。

## 2. 结论总表

| 任务 | 不分档实例 | 分档实例 | 见 |
|---|---|---|---|
| Blanket | 判据开着；初态只能在旧镜像加 128 SM GPU 上建；预算只够约 29 s 仿真 | 初态只能在 RTX PRO 6000（188 SM）上恢复，评测机正是这个型号；多层布达不到静止阈值 | 4.1、4.2、4.3 |
| Buzz Wire | 判据开着；无抓持辅助；预算约 4,900 步，已知解要 8,662 步 | easy 有 CPU 原生成功；medium 终点姿态从未达到；hard 超预算 | 4.2、4.3 |
| Cast Coil | 判据开着；无抓持辅助，纯摩擦从未试过 | 无 Harbor 时序成功；证明用的是 25 ms / 40 子步 | 6 |
| Cast Keyhole | 判据开着；无抓持辅助 | 同 Coil；出生后金件倒下，越过分界 14 mm，需要搬回 | 4.3 |
| Interlocked Claws | **`goal_complete=False`，不可能** | medium 唯一通路间隙 55.7 µm，小于碰撞网格精度；hard 未搜过完整通路 | 3.1、4.3 |
| Hedgehog | **不可能** | easy/medium 有 CPU 证明；hard 出生重叠，开局弹飞 | 3.1、4.3 |
| Horseshoe | **不可能** | 无机器人成功 | 3.1 |
| Lock Picking | **不可能** | 只有离线重判通过；持杆时孔壁允差 10 µm | 3.1、4.3 |
| Knot Untying | **不可能** | **IPC 修正缺失**；每 tick 交叉检查耗时 2–7 s；超预算；静止阈值 | 3.1、3.2、4.2、4.3 |
| Rope Threading | **不可能** | **IPC 修正缺失**；厚度判据；超预算 | 3.1、3.2、4.2、4.3 |
| Fiber Bundling | 判据开着，但用的是旧 v3 判据，instruction 没有写 | 三档有 CPU 原生成功（用了抓持辅助）；hard 每步 53 s | 3.1、4.2 |
| Slotted Post Ring | **不可能** | **IPC 修正缺失**；超预算；28 mm 槽可能过不去 | 3.1、3.2、4.2、4.3 |
| Orbits | **不可能** | **IPC 修正缺失**；超预算；静止阈值；绳长 | 3.1、3.2、4.2、4.3 |
| Cube（样板） | 通过，是唯一拿过 `success=1` 的家族 | — | 6 |

## 3. 一定拿不到分

### 3.1 不分档实例用旧镜像，8 类的 `goal_complete=False`（已核）

28 个不分档目录（14 个家族，各有 unlimited 和 limited）的 Dockerfile 都是 `FROM ghcr.io/luigivamper/rcb-topogym:0.1.0`，`PYTHONPATH` 指向镜像里的 `/opt/topogym`，所以判据代码来自镜像，而不是当前源码。本地 0.1.0 镜像建于 2026-09-29 14:07，里面：

| 任务 | 0.1.0 中的状态 |
|---|---|
| Hedgehog、Horseshoe、Claws、Orbits、Slotted | `PlacementGoalMixin` 在 `topogym/tasks/placement.py:61` 写 `goal_complete = False`；Orbits 和 Slotted 各自也写 False |
| Lock | `goal_complete = False`，`terminal_revision = "terminal_v2"` |
| Knot | `goal_complete = False`，`terminal_v3_release_settling` |
| Rope | `goal_complete = False`，`terminal_v2` |
| Fiber | `goal_complete = True`，但判据是旧的 `terminal_v3_fiber_contacts` |
| Keyhole | `goal_complete` 由实例资格记录决定；easy 默认参数下成立 |
| Coil、Buzz、Blanket | 继承 `base.py` 的 True |

0.1.0 的 `base.py:296` 是 `succeeded = bool(self.goal_complete and …)`，所以上表前 8 类的 `is_solved()` 永远为 False，grade.py 的 `all_success` 永远为 0。

与此同时，这些目录的 `instruction.md` 已经按新判据重写过（例如 Lock 写"允许持杆、孔壁接触允差 0.01 mm"，Hedgehog 写"判据保持 2 s 即成功"），告诉 agent 的规则和评分实际用的规则不一致。

Fiber 不分档实例的 v3 判据要求：每根细芯在环中心面两侧 ±5.2 mm 的平面上，都从离环轴 12.18 mm 以内穿过；护套前端在 ±16 mm 平面上离轴 1.38 mm 以内。instruction 没有写这些数值。按 v3 重判，历史上真实全部穿环的演示只过了 1/4、2/8、7/16 根（[results_v3.json](../../runs/test_results/fiber_terminal_v4_20260929/results_v3.json)）。

**复现：**

```bash
cid=$(docker create ghcr.io/luigivamper/rcb-topogym:0.1.0)
docker cp $cid:/opt/topogym/topogym/tasks /tmp/rcb010_tasks
docker rm $cid
grep -rn "goal_complete = \|terminal_revision = " /tmp/rcb010_tasks --include=*.py
```

**边界：** 只核对了本机的 0.1.0 标签。这是可变标签，ghcr 上同名标签的内容没有核对。

### 3.2 IPC 机械臂方向修正没进任何镜像（已核）

**场景：** Knot 里 ALOHA 去捏绳。Genesis 1.2.1 声明 IPC 旋转关节的方向，与 pyuipc 0.0.25 的约定相反。结果是：参与绳子碰撞的那份 IPC 机械臂，与 agent 观测到、IK 算出的机械臂朝相反方向转。2026-10-01 的同步检查里，两份夹爪相差 85–170 mm；在 Harbor 时序下 8 步后已偏 32 mm；加上修正后差 0.0–0.2 mm（[ipc_sync_check 日志](../../runs/test_results/knot_robot_grasp_20260930/)）。

**现状：**

- 修正（`ForwardAxisRevoluteJoint`，`topogym/world/physics/ipc.py:271-277`）只在工作区，没有提交。
- HEAD 里没有这个修正，本地 0.2.4-cu128 镜像里也没有。
- 分档目录引用的 `0.2.3-cu128` 建于提交 6c530190，早于修正；本机也没有这个镜像。

**受影响：** Knot、Rope、Slotted、Orbits 的全部分档实例。这几个任务里机器人以 `external_articulation` 方式耦合进 IPC，绳、环、珠、把手都只存在于 IPC 中。Fiber 用的是刚体关节链，不受影响。

**修正发布后的新风险：** 修正带有 2 mm 的同步自检，超限会抛 `RuntimeError`。在 grader 里，这会记成 `grader_error`，而不是任务失败。夹爪用力接触时两份机械臂会不会偏开 2 mm，还没有测过。

## 4. 特定条件下拿不到

### 4.1 Blanket 分档初态绑定 GPU 型号（已核）

Blanket 三个分档实例从冻结的初始布料状态启动（`instance_assets/initial_state/`）。其中刚体碰撞器的缓冲 `RigidSolver/collider/_contact0_mpr_state/simplex_support/v1` 形状是 `[4, 24064, 3]`。Genesis 按"GPU 的 SM 数 × 128"分配这个缓冲：24064 = 188 × 128，对应 RTX PRO 6000 Blackwell；本机 RTX 4090 是 128 SM，对应 16384。

恢复初态时，`topogym/world/initial_state.py:119` 的 `require_same_layout` 严格比对形状，不一致就在 `Env.reset` 报错，后果是：

- agent 连 Session 都建不起来；
- unlimited grader 记 `grader_error=1`；
- limited sidecar 在写 `final.json` 之前就退出，被记成 `missing_log`。

CI 用例 `ci_checks/test-builder-feedback.py:173` 正好覆盖了 16384 对 24064 的报错。task README 和 instruction 都没有写明需要哪种 GPU。

**复现：**

```bash
grep -o '"shape": \[4, [0-9]*, 3\]' tasks/topogym-blanket-flatten-easy-i00/tests/instance_assets/initial_state/manifest.json
nvidia-smi --query-gpu=name --format=csv,noheader
```

不分档的 Blanket 没有 `task_parameters`，会加载镜像里的默认初态 `gathered_scene_v1/easy/seed_0`。那个初态需要 128 SM 的布局和旧的世界身份哈希，只能在旧 0.1.0 镜像加 128 SM GPU 上建成。

**评测机型号：** 提交 05d8181e 的说明写明，这些初态是在任务实际运行的 GPU（RTX PRO 6000）上制作的，PBD 初态只能在同型号 GPU 上恢复。所以在评测机上不受影响；在本机 RTX 4090 或其他型号上无法建场景，也无法本地复现分档 Blanket。task README 和 instruction 没有写这一硬件要求。

### 4.2 时间预算装不下已知最短路线

**预算是怎么来的：**

- agent 的墙钟预算 B：分档 21,600 s（Knot 分档 36,000 s），不分档 5,400 s。
- verifier 超时 = 3 × B + 900 s（`scripts/topogym_mk_task.py:302`）。里面要跑 2 次评分回放，外加 1 次视频回放（见 5.1），所以每次回放大约只有 B。
- agent 至少要把整条轨迹在自己的预算里录一遍，调试还要另外花时间。
- 能回放的最长仿真时长 ≈ B ÷ 每控制步墙钟耗时 × 0.025 s。

| 实例 | instruction 写的每步耗时 | 预算内最长仿真时长 | 已知最短路线 |
|---|---|---|---|
| Knot easy / medium / hard | 67.1 / 69.1 / 85.3 s | 13.4 / 13.0 / 10.6 s | 无臂纯绳路线，解开交叉就要 8.0 / 27.1 / 34.75 s，还不含机器人接近和松手 |
| Fiber hard | 53.4 s | 约 10 s | 639 s |
| Fiber easy / medium | 7.5 / 6.2 s | 72 / 87 s | 190 / 344 s |
| Slotted、Orbits 分档 | 19.3–31.7 s | 17–28 s | Slotted 外力解 147 s；Orbits 无臂解 208–220 s |
| Rope medium | 19.5 s | 27.7 s | 三环流程按已有速度约 125 s |
| Buzz hard | 5.9 s（[docs/rcb/README.md](../rcb/README.md) 实测约 1.05 s） | 按 1.05 s 算需要约 33,000 s，超过 21,600 s 预算 | 31,684 步 |
| Blanket 不分档 | 4.6 s | 约 29 s | 唯一的机器人成功用了 32.5 s，而且是带抓持辅助的更简单变体 |

**两个具体的耗时来源：**

- **Knot（已核代码）：** `topogym/tasks/knot_untying/common.py:92` 每个物理 tick 都调用 `planar_clearance`（`topogym/utils/geometry/passage.py:112`），由 `topogym/simulator/env.py:432` 驱动。它是纯 Python 的 O(N²) 双循环，easy 约 802 个站点、hard 约 987 个。审查实测：出生时约 2 s/次，因为遇到第一个交叉就提前返回；绳子解开后 6.7–7.0 s/次。也就是越接近成功越慢：一个控制步 10 个 tick，光这一项就要几十秒；0.5 s 确认窗口（200 个 tick）每次回放约 23 分钟。
- **Blanket：** `footprint_area`（16,000 个三角形求并）每个 tick 约 0.2 s，占每个控制步 4.6–4.9 s 中的约 2 s。

**instruction 里的每步耗时本身不可靠（已核测量方式）：** 它来自 `harbor_templates/topogym/common/rcb_topogym.py:1500`：场景建好后，取前 3 个保持步的平均值，可能含预热和 GPU 争用。

- 同一个 Claws hard 场景：分档 instruction 写 10.5 s，不分档写 0.7 s。
- 同一个 Hedgehog easy 场景：6.7 s 对 0.9 s。
- Coil 不分档在 verifier 里实测 0.41 s/步（[jobs/coil-full-20260929-172853](../../jobs/coil-full-20260929-172853)，286 步两次回放用了 233 s）。

数字偏高会误导 agent，以为只能走很短的路线；数字属实，则任务做不完。两种情况都需要重测。

### 4.3 判据与物理状态不相容

**Rope：搭在环上的绳判不过（已核代码；三环结论是推断）**

`topogym/tasks/rope_threading/common.py:95` 在环两侧 ±tube 半径的平面上检查穿过顺序，用的仍是缩小后的开口半径（R − tube − 绳半径 − 0.1 mm，easy/medium 为 64.9 mm，hard 为 45.9 mm）。而在这两个平面上，环的真实开口更大。绳子搭在环下缘时，中心线在这两个平面上约在 66.8 mm 处，因此 `thickness_ok` 不通过。证据：

- 作者文档里的"期望终态"（t = 374 s）按这个判据每个环都不过。
- 最长的机器人运行（[full_ik_v3_20260921_attempt_1](../../runs/environment-solvability/rope_threading/full_ik_v3_20260921_attempt_1)）有 98 帧穿环顺序正确，`thickness_ok` 0 帧通过。

所以绳子必须基本不接触环、悬空穿过。medium/hard 要求三个环，两爪之间垂下的绳段落在一个竖直平面内，审查采样约 1,700 万个竖直平面，没有一个同时穿过三个可用开口。easy 只有两个环，持绳状态下可达。

**静止阈值 1 mm/s 与 IPC 摩擦蠕动（Knot、Rope、Orbits；推断）**

- Knot 判据要求所有顶点速度 ≤ 1 mm/s（`topogym/tasks/knot_untying/common.py:23`）。
- 生产配置只设了接触距离 `contact_d_hat`（`topogym/world/physics/ipc.py:37`），没有设 `contact_eps_velocity`。这是低于它就把摩擦当作静摩擦平滑处理的速度阈值，默认 10 mm/s。
- 粗网格纯绳实验：交叉解开、贴桌后，松手 7 s 仍以约 3.2 mm/s 蠕动，每秒只下降约 0.07 mm/s；把该阈值设成 1 mm/s 后降到 0.34 mm/s 并通过（[knot_object_route_20260930](../../runs/test_results/knot_object_route_20260930/README.md)）。
- 33k 顶点的正式网格在 Harbor 时序下没有测过，判据也标着 `thresholds_calibrated=False`。

**Blanket：多层布达不到静止阈值**

- 判据要求 8,181 个粒子的最大速度 ≤ 30 mm/s，漂移 ≤ 3 mm，连续 201 个 tick（`topogym/tasks/blanket_flatten/common.py:39`、`:57-60`）。
- 多层叠放自由静置 44 s，峰值 498–657 mm/s，最长稳定窗口 0 s（[blanket_hard_long_settle_20260927_01](../../runs/test_results/blanket_hard_long_settle_20260927_01)）。
- 单层折叠能静止：峰值 6.7 mm/s。
- 所以覆盖率判据名义上容许 10% 重叠，实际上几乎要铺成单层；instruction 没有写这一点。

**其他**

- **Buzz medium：** 终点放置要求误差在 5 mm、10° 以内，历次松手后是 8.8 mm / 42.3° 和 8.7 mm / 52.4°（[independent_local_audit.json](../../runs/test_results/buzz_terminal_medium_20260929_01/independent_local_audit.json)）。目标姿态在几何上可行（魔杖金属离导线 14.46 mm，支撑多边形包含质心），问题在操作。另外，instruction 里的"把手朝内"有歧义：照搬起点姿态的镜像，hard 会差 18.9°。
- **Hedgehog hard：** 出生时球与笼的碰撞网格重叠最多 2.97 mm。Harbor 时序下，第 1 个 tick 穿透 0.61 mm（失败线 1 mm），球以 1.2 m/s 被弹出，30 个 tick 后仍有 0.5 m/s（[diagnostic.json](../../runs/hedgehog_three_20260930/hard_initial_diagnostic_01/diagnostic.json)）。GPU 回放不是逐位确定的，两次评分回放里球的落点可能不同，开环轨迹有风险。
- **Slotted：** 所有档位槽宽 28 mm，文档写环穿槽需要 20 mm 环管加两股 7 mm 绳，共 34 mm。只有 36 mm 的候选解出过；28 mm 需要把软绳压缩 6 mm，从未验证（推断）。
- **Orbits：** 分档绳长 0.80 m，已完成的无臂路线用的是 1.1–1.7 m，代码里也标着 `full_solution_length_qualified=False`。不分档 `reference85` 的绳长约 0.532 m，低于文档第一步动作的直线下界约 0.56 m（推断）。
- **Lock：** 判据要求 `bore_excess ≤ 10 µm`（`topogym/tasks/lock_picking/common.py:238-239`）。松手后钥匙靠在孔壁上，余量约 4–7 µm，能过；持杆时如果手臂的 PD 误差把钥匙压向孔壁，就会超出，所以持杆必须让钥匙完全离壁。离线重判（CPU、100 ms / 160 子步）三档都通过了（[replay.json](../../runs/test_results/lock_contact_fix_20260930_01/replay.json)），但这不是 Harbor 时序下的运行。
- **Keyhole：** 出生后组合件在约 0.1 s 内倒下，金件的最大 y 为 0.09973 m，分界线在 0.08576 m，从第 2 个 tick 起就越界 13.97 mm。成功前必须把金件往回搬至少 14 mm；证明里就是这样做的。instruction 的写法暗示金件一开始就在系统一侧。
- **Claws medium：** 唯一找到的物体通路最小间隙 55.7 µm，而两个部件按非凸网格做 SDF 碰撞，格子约 1.0–3.1 mm（受 Genesis 的 `sdf_max_res` 限制），比通路精度粗 20–60 倍（推断，没有物理运行）。**Claws hard** 在当前 0.68 缩放下没有搜过完整分离通路。

## 5. 评分脚本本身的问题

1. **unlimited 的 `grade.py` 先渲染视频、后写分数（已核）：** 第 82 行做第三次回放渲染视频，第 86 行才 `write(ok, out)`。视频回放超时或 Nyx 原生崩溃，会丢掉已经算好的成绩；verifier 超时 3 × B + 900 s 也没有给渲染留余量。limited 的 server 先写评分记录再渲染，顺序是对的。
2. **基础设施错误被记成 grader 或 agent 的问题：**
   - IPC 报"世界无效"时，当前提交的 `ipc.py` 直接抛异常，走不到 Task 的 `rope_volume_invalid` 分支，结果记成 `grader_error`，而不是任务失败。
   - Blanket 的"粒子状态非有限"失败分支永远不会触发：`read_state` 先抛 `FloatingPointError`。
   - limited sidecar 用 `strict=True` 建 Session（`server.py:112`），建场景失败时不写 `final.json`，被记成 `missing_log=1, grader_error=0`，看起来像 agent 失败。
3. **limited 结算只回放到实时运行结束的那一行，没有余量：** 实时运行一旦成功，局就结束；回放必须在同一个控制步完成 0.5 s 窗口。GPU 回放不逐位一致时，实时成功的运行可能 `replay_success=0`。这是有意设计，有 CI 用例覆盖，但和 [docs/rcb/README.md](../rcb/README.md) 里"把整局录成轨迹"的描述不一致。
4. **不分档目录里的旧 `rcb_topogym.py` 有 float32 限位 bug（已核）：** 第 485 行把关节限位转成 float32 时向外取整（例如 ALOHA ±3.14158、Panda ±2.8973）。动作落在限位上或被裁到限位时会报 "Joint target outside model limits"；limited 模式下返回 HTTP 500 并结束整局。分档目录已修（提交 f6f020c0）。
5. **文档和代码不一致：**
   - [LIMITED_MODE_PROTOCOL.md](../rcb/LIMITED_MODE_PROTOCOL.md) 第 202 行写 `success = live ∧ replay ∧ deterministic`，代码并不要求逐位确定（`grade.py` 里 `gpu=True`）。
   - `scripts/run_knot_robot_route.py` 的文件头注释、`docs/develop/tasks/knot_untying_zh.md`、`docs/develop/tasks/rope_threading_zh.md` 写着 `goal_complete=False`。对当前源码这已过期，对 0.1.0 镜像却是对的。
6. **参考解与 CI 缺口：** 106 个目录里有 104 个的 `solution/solve.sh` 都是 "no reference solution"，只有 Cube 的两个目录有 oracle。CI 没有用例跑 `grade.py`，即使用替身 Session 也没有。

## 6. 核对过、没有问题的部分

- **成功会锁存：** Task 终止后 `Session.step` 不再推进 Env，`Task.update` 返回已锁存的结果。成功之后继续追加的动作不影响得分。
- **每次回放从冻结初态完整重来：** `rewind_to(S0)` 同时恢复世界、抓持管理、接触记录、随机数、机器人目标和 Task 状态（结果、稳定计时、静置参考）。同一进程里的两次回放互不干扰。
- **两份副本一致：** 所有目录 `tests/` 与 `environment/` 下的 `instance.json` 和 `instance_assets` 逐字节相同。Blanket 的相对初态路径在 `/tests`、`/app`、`/srv` 下都能解析，哈希与 manifest 一致。
- **目标区放得下目标：** 目标区半宽 = max(0.10 m, 目标包围盒对角线 / 2 + 15 mm)，含绳的目标至少 0.20 m；高度 = max(0.15 m, 对角线 + 20 mm)（`topogym/tasks/placement.py:25-28`）。目标在任何朝向都放得下，目标区不与固定件相交，且在机器人可达范围内。
- **旧的 Keyhole 实例资格门已经不限制成功：** 当前源码里资格记录只作元数据；即使按旧门，分档参数也满足。
- **出生阶段不触发失败：** Hedgehog、Horseshoe、Slotted、Orbits 共 12 个分档实例，在 Harbor 时序下的前 30 个 tick 都没有触发失败（[rcb_builder_feedback_20261001](../../runs/test_results/rcb_builder_feedback_20261001/run_151751)）。Keyhole easy 在 CUDA、Harbor 时序下经历出生倒下的 93 个 tick 也没有触发失败（[trial_01_easy_pickup](../../runs/test_results/cast_keyhole_policy_20260928/trial_01_easy_pickup)）。
- **Cube 样板合理且可达：** unlimited 有 `jobs/cube-u-oracle-2`、`jobs/regrade-check` 得 1 分；limited 有 `jobs/cube-l-oracle-3` 得 1 分。

**现有成功证据与 Harbor 时序的差距：**

| 任务 | 原生成功运行 | 与 Harbor 的差别 |
|---|---|---|
| Keyhole、Coil | 各 3 档 | CPU float64、25 ms / 40 子步、`contact_weld_v1` |
| Hedgehog | easy、medium | 同上 |
| Buzz easy | 有，已独立审计（[independent_audit.json](../../runs/test_results/buzz_staged_easy_20260929_01/independent_audit.json)） | 同上 |
| Fiber | 三档（[fiber_quick_solvability_20260929](../../runs/test_results/fiber_quick_solvability_20260929)） | 同上；Harbor 分档实例不给抓持辅助 |
| Lock | 只有离线重判 | CPU float32、100 ms / 160 子步 |

这些运行的积分子步都是 0.625 ms，与 Harbor 相同；但 Task 的检查频率是 Harbor 的 1/10，而且全部用了抓持辅助。

## 7. 推断项与未验证项

以下结论没有经过运行验证，修复前需要实测：

1. ghcr 上 `rcb-topogym:0.1.0` 的内容与本机同名镜像一致。
2. instruction 里的每步耗时是否代表稳定运行状态，特别是各 hard 档、Hedgehog easy 档、Knot 档。
3. 33k 顶点正式网格在 Harbor 时序下的蠕动速度是否与粗网格相近。
4. Rope medium/hard 是否真的没有可行的三环穿法，例如借助桌面让绳弯折。
5. Slotted 28 mm 槽、Orbits 绳长、Claws medium 通路能否实际通过。
6. 不分档实例在纯摩擦抓持下，Coil、Keyhole、Buzz 能否完成。
7. 修正发布后，IPC 同步自检在夹爪用力接触时是否会误触发。

## 8. 建议的修复顺序与完成标准

| 顺序 | 修复 | 完成标准 |
|---|---|---|
| 1 | 不分档 14 个任务改用新镜像并重新生成 instance，或者从 dataset 里撤下 | 每个目录的 Dockerfile 镜像里，`goal_complete` 与当前源码一致；instruction 与镜像内判据一致 |
| 2 | 提交 IPC 修正，重建镜像，把分档 Dockerfile 的标签对齐到实际存在的镜像 | Knot、Rope、Slotted、Orbits 各跑一次同步检查，两份机械臂相差 ≤ 0.2 mm |
| 3 | 在 Blanket 的 task README 和 instruction 里写明只能在 RTX PRO 6000 上运行；如需在其他 GPU 上运行，改成不依赖 SM 数的恢复方式 | 文档写明硬件要求；或在 RTX 4090 上 Blanket 三档 `Session` 能建成 |
| 4 | `grade.py` 改成先写分数、再渲染视频 | 模拟视频回放超时时，`reward.txt` 已存在且等于评分结果；补一条 CI 用例 |
| 5 | Knot 的 `planar_clearance` 向量化（或先用包围盒剪枝），Blanket 的面积计算加速；在稳定运行状态下重测每步耗时并更新 instruction | Knot 解开状态下单次调用 < 0.05 s；instruction 的每步耗时取自稳定运行状态 |
| 6 | Rope 偏移平面改用该平面上的真实开口半径；在正式网格上校准静止阈值或 `contact_eps_velocity` | 作者的期望终态那一帧判为通过；正式网格松手后能在预算内静止 |
| 7 | 每个家族至少做出一条在 Harbor 时序下回放两次都成功的参考轨迹，放进 `solve.sh` | oracle agent 每个家族得 1 分 |
