# 本地任务难度评测实施计划（13 项可选 × 三档难度 × 双模式）

2026-09-29。状态：已按本计划实现，默认全 13 项、每档 1 个样本、agent 预算 21600 秒。
当前命令与验证范围见 [Harbor 手册的难度评测入口](README.md#8-难度评测入口)。本批真实 trial 尚未启动；短流程合同测试不能代替 13 项物理验收。

本次目标是在 `/home/jianwen/topogym/bash_scripts/` 提供一个 Bash 入口：按 `configs/sweeps/difficulty_eval.yaml`，每个正式 task 的 easy / medium / hard 各抽取 N 个随机化场景实例（默认 N=1），准备必要资产与 Harbor 任务包，同一实例分别执行一次 limited 和 unlimited trial。每次 rollout 的 agent 墙钟上限默认 **6 小时，即 21600 秒**。支持自己的 ChatGPT 订阅认证，以及 API key + model name 两类运行方式。

本次共 **39 个实例、78 个任务包、78 次正式 trial / 模型**，`cube_pick_place` 仅作流程检查。本文是本地单次试跑方案；[Docker 交付计划](difficulty_sweep_delivery_plan_zh.md)中的每模式三次、234 trials、远端发布属于另一实验范围，其 5400 秒预算不适用于本次。

上述数量是默认全 13 项、`samples_per_difficulty=1` 的配置，不是脚本限制。支持 `--tasks` 选择其中 T 项；抽样、任务生成、队列、输出路径和汇总均按 manifest 数量工作，不硬编码 39/78。每个 task/difficulty 可设置 N 个样本，总实例数 `3TN`，双模式各一次时总 trial 数 `6TN`。全文未另外标注的 39/78 为默认全任务、N=1 的例子；选子集时不能报告为全 13 项覆盖。

配置为 **`configs/sweeps/difficulty_eval.yaml`**。任务从固定 13 项目录中选择，默认全部；每个所选任务的三档难度、两模式和每实例/模式一次 trial 固定。CLI 可覆盖任务子集及每档 randomized sample 数。实际配置如下：

```yaml
schema_version: 1
task_ids:
  - interlocked_claws
  - rope_threading
  - lock_picking
  - hedgehog_in_cage
  - fiber_bundling
  - horseshoe_ring
  - knot_untying
  - cast_coil
  - cast_keyhole
  - buzz_wire_3d
  - blanket_flatten
  - slotted_post_ring
  - orbits
difficulties: [easy, medium, hard]    # 固定，不开放 CLI 删档
modes: [unlimited, limited]          # 固定，不开放 CLI 删模式
samples_per_difficulty: 1            # 可由 --samples-per-difficulty N 覆盖
sampling_seed: 20260929
agent_wall_clock_s: 21600
concurrency: 1
```

首次解析遵循显式 CLI > setting > 默认值；恢复时未显式覆盖的值取冻结 manifest。mapping v1 和每模式一次 trial 由代码固定，不在 YAML 重复配置。三档、双模式若被改动或配置中出现未知字段则报错。正式入口不开放 `--difficulty`、`--modes` 或 `--trials`；单项开发探针使用现有底层命令并单独记录，不混入该评测的完整性统计。

**任务编号（固定 mapping v1）：**沿用[现有任务进展目录](../progress/current_zh.md)的编号，不按 registry 遍历顺序或字母排序重新编号。

| 编号 | task_id | 名称 |
| --- | --- | --- |
| 1 | `interlocked_claws` | 双爪互锁 |
| 2 | `rope_threading` | 绳穿环 |
| 3 | `lock_picking` | 开锁 |
| 4 | `hedgehog_in_cage` | 刺球出笼 |
| 5 | `fiber_bundling` | 光纤收束 |
| 6 | `horseshoe_ring` | 马蹄环 |
| 7 | `knot_untying` | 解绳结 |
| 8 | `cast_coil` | Cast Coil |
| 9 | `cast_keyhole` | Cast Keyhole |
| 10 | `buzz_wire_3d` | 立体电流棒 |
| 11 | `blanket_flatten` | 被子展平 |
| 12 | `slotted_post_ring` | 长孔立柱解环 |
| 13 | `orbits` | Orbits 阶梯解绳 |

`--tasks all` 选择全部；支持逗号分隔编号、闭区间和 canonical task_id，例如 `--tasks 8`、`--tasks 1,8-10,13`、`--tasks cast_coil,orbits`。默认使用 setting 的 task_ids（默认全 13 项）。去掉字段首尾空白，展开后去重并按固定编号排序；空列表、空字段、未知名称、越界编号、反向区间及 `all` 与其他项混用均报错，不静默忽略。另提供 `--list-tasks` 打印映射后退出，无需模型、凭据或 GPU。

映射/解析逻辑放在专职抽样脚本，Python 调度器调用其共享函数，Bash 只转发参数，避免维护两份列表。manifest 同时记录 mapping 版本、选择器和最终编号/task_id；随机流以 canonical task_id/difficulty 命名，所以选择子集、改变参数顺序不会改变共同任务的样本。resume 必须沿用同一所选集合；改变集合则另建 run。

当前已实现的方案：**公共模板独立到 `harbor_templates/topogym/`；专职抽样脚本管理可复现实例清单，`scripts/difficulty_eval.py` 统一调度各阶段，Bash 保留兼容启动入口。** 原先拟新增的 prepare/run/collect 三个独立 Python 脚本取消。生成继续调用现有生成器，每个实例/模式仍调用一次 `harbor run`，结果检查与汇总复用现有整理器。按用户后续授权，原 Bash 中的 Python 片段及进程管理已迁入单一 Python 调度器。

**1. 现在能否确认全部场景已可布设且 simulation 正确？**

结论：**场景定义已覆盖 13 × 3，但不能确认当前全部 39 项都已完成真实物理验收，更不能确认任意新 seed 或 6 小时连续运行正确。** 已有布设、短程仿真、完整评分、完整任务成功应分别报告。

本次核对源码 HEAD 为 `f8f10e02a4de1bf1865089c7aee3b274a1447ca9`，工作区有进行中的未提交修改。下述证据有不同源码与实例身份，不能统一当作当前工作区通过；正式执行须冻结完整源码、配置和资产。

- `topogym/config/variation_records.py` 有 39 条 `pool=tier` 记录，每档一个具名变体；36 条标注 `not_runtime_validated`，Blanket 三条标注 `scene_layout_only_motion_deferred`。这些标签不是完整运行验收结论，也不否定另外保存的历史短程证据。
- `runs/task_build/*/describe.json` 和 `runs/test_results/harbor_rcb_parity_20260929/segment_history/sec_per_step.json` 覆盖 13 个正式家族及 cube 的默认实例。`cmd_describe` 执行三次保持动作并 reset；这种证据仅能说明特定实例曾建场并短程执行。
- 当前 `tasks/` 是 14 家族 × 2 模式，共 28 包，不是 39 个难度场景的双模式矩阵。全部现有默认实例均为 seed 0，但并非全部 easy，Orbits 甚至使用 compatibility 池的 `reference85`。
- Harbor 历史完整验收主要是 cube 两模式 oracle/nop、cube limited 协议检查，以及 knot limited nop 起服务/收尾/出分。后者不能证明非空动作完整执行。详细范围见 [Harbor 手册](README.md#7-验收记录)。部分验收后又修改过工具与模拟器。

逐家族需要关注的范围如下。“历史三档短程”来自 `runs/test_results/initial_scenes*/summary.json`，通常只有 0.1 秒 home hold，Buzz 新批为 1 秒；不表示当前源码、随机种子或完整解法通过。

| 正式 task | 当前 Harbor i00 的变体 | 已有证据与本批缺口 |
| --- | --- | --- |
| `cast_keyhole` | easy | 有历史三档短程记录；本批新 seed、双模式与长时运行待验 |
| `cast_coil` | easy | 有历史三档短程记录；本批实例及双模式待验 |
| `horseshoe_ring` | easy | 历史三档曾短程通过，当前 revision 已变化，须复验 |
| `hedgehog_in_cage` | easy | 历史三档曾短程通过，medium revision 已变化，须复验 |
| `lock_picking` | medium | 历史三档曾短程通过，medium revision 已变化，须复验 |
| `interlocked_claws` | hard | 历史三档曾短程通过，当前 revision 已变化；冻结辅助抓持及预抓取设定 |
| `buzz_wire_3d` | easy | 09-28 新三档有短程记录；本批实例、接触失败判据与双模式待验 |
| `fiber_bundling` | medium | 有历史三档短程记录；当前场景/判据仍有工作区修改，本批待验 |
| `knot_untying` | easy | 当前默认实例有短程耗时及 limited nop 证据；当前三档、非空动作和长时 FEM 待验 |
| `blanket_flatten` | easy | 当前三档 seed 0 已取得布设资格，粒子运动稳定性暂缓；随机 seed 需单独准备完整初态包 |
| `orbits` | reference85，非 tier | 新三档资产构造/同 seed 重建通过；物理稳定性被显存及原生 CUDA 错误阻塞，尚无结论 |
| `rope_threading` | medium | 新三档几何已接入；本轮 Nyx/物理尝试因显存不足中止，不能继承旧三环资格 |
| `slotted_post_ring` | hard | 当前 FEM 三档几何通过；长时稳定性被 OOM/原生 IPC 错误阻塞，部分只取得极短物理序列 |

后三类 FEM 和 Blanket 的具体证据见 [Orbits](../develop/tasks/orbits_zh.md)、[Rope Threading](../develop/tasks/rope_threading_zh.md)、[Slotted Post Ring](../develop/tasks/slotted_post_ring_zh.md)、[Blanket](../develop/tasks/blanket_flatten_zh.md)。本批应将这些项列为优先复验对象，不能用静态构建成功替代动态资格。通过短程 gate 后可以做探索性 trial，但报告仍须保留稳定性未验收标签。

这里“验收缺口”主要是测试被运行问题阻断：Rope 三档初始化 OOM，重试未等到足够显存；Slotted Post Easy/Medium 只分别审计到约 0.1675/0.085 秒后 OOM，已执行部分的检查通过，Hard 初始化失败；Orbits 新三档未获得有效物理序列，此外历史 hard 有弹起/松弛现象待复验。不能统一解释为三项均已发现物理不稳定，也不能把 `InvalidDevice` 尚未定位的根因直接归为显存不足。

**2. 抽样和冻结规则**

正式 task 候选目录固定为上述 13 项，先按选择器确定本 run 的 T 项；难度固定 `easy/medium/hard`，只读取 `pool=tier` 的候选，不使用 `base` 别名或 compatibility 变体代替难度。

**现有 simulator 的实际规则：** `variation_id="seeded"` 时，`registry.seeded_variation()` 用 `seed % 3` 选 easy/medium/hard（余数 0/1/2），再由 `Env.reset()` 调用 `scene_variation.draw()` 采样该档的场景扰动。`VariantRng` 用 seed、轴名称、版本派生独立随机流；同 seed 与同版本下参数可复现，增加一个轴不会改变其他命名轴的抽样。

这层扰动包括任务声明范围内的位置、朝向、颜色/外观，不任意改变孔径、尺寸或难度结构。比如 Cast Coil 的中心 X 偏移 ±3 cm、Y 偏移 −3～0 cm、yaw ±10°、金银件明暗各 ±0.1；Claws 的初始预抓取固定，所以该层只改外观。各任务自身原有的 seed 随机化仍保留，例如 Fiber 的丝束布局。

**显式 `variation_id="easy"` 加不同 seed，不会启用上述 `scene_variation.draw()`。** 它固定档位，仍可能触发任务内部自己的随机参数，但不能等同于完整 seeded 场景随机化。此前仅写“显式 variation + seed”不足以表达本批所需行为，按以下流程补正：

1. 新增 `scripts/sample_difficulty_instances.py`，输入正式任务、档位、每档样本数和 `sampling_seed`，只生成 manifest，不建 GPU 场景、不运行 Harbor。当前每档只有一个 canonical variation，无需另建变体池或随机化算法。建议首批 `sampling_seed=20260929`。
2. 外层固定遍历 task/difficulty，对每组用现有 `VariantRng(sampling_seed)` 的独立命名流抽整数 q。设档位编号 t=0/1/2，令 `scene_seed=3*q+t`，限制 `0 <= scene_seed < 2**32`。这样调用现有 seeded 入口即可保证指定数量的样本全部属于该档；q 的上界为 `floor((2**32-1-t)/3)`。不直接拿全局连续随机 seed 碰运气覆盖三档，也不因顺序变化改变其他组的样本。
3. 每个实例仅抽一次，再由它生成两个模式。limited/unlimited 必须共享 variation、seed、完整 simulator 配置、资产、辅助抓持、机器人初态和 instance 文件内容。
4. 初始化不合格时记录 `blocked` 和原因，不自动换 seed，不改用 base，也不按模型成功与否筛选样本。必要修复后仍对同一实例复验；若必须换实例，则生成新 manifest 并明确变更理由。
5. Blanket 的随机 seed 先调用现有 `prepare_blanket_initial_states.py --seeded --seed <scene_seed>` 准备对应完整状态包，并按当前 `scene_layout` 范围验收。没有准备包就阻断该项；不得借 seed 0 的状态冒充随机实例，也不得提升为 `released_stable`。
6. manifest 保存 requested variation=`seeded`、解析后的 canonical variation/difficulty、scene seed、RNG/scene variation 版本、draws、有效 task_parameters 和完整配置。Harbor 冻结/重放必须保留 seeded 入口，或显式保存并重放全部有效参数；不能只写回 canonical variation 而丢掉扰动。辅助抓持等按解析后的档位与实例生成。验证实际 scene 与 manifest 一致，并拒绝未声明的参数覆盖。
7. 冻结工作区快照及逐文件哈希，记录 Git commit、dirty 状态、依赖版本和镜像 ID/digest。缓存 key 至少包含源码/配置/资产/instance 哈希；不能按 family 或旧 i00 目录复用 describe。seed 的参数复现不等于不同 GPU 的浮点动力学逐位一致。

**每档多个样本：**抽样脚本和 Bash 都提供 `--samples-per-difficulty N`，正整数，默认 1；数量不得超过对应档位的可用 seed 数。同一 task/difficulty 内按上述固定随机流依次取 q，遇到已经选过的 q 就继续取，直到得到 N 个不同 scene seed。流名和派生规则不包含 N，因此同一 sampling_seed、候选/算法版本下，N=5 的前 3 项与 N=3 完全一致，首项也与 N=1 一致。不同 seed 不保证有限外观选项绝不重复，不按视觉相似程度重新筛样本。

每项有稳定 `sample_id=s00/s01/...`，instance、describe、资产、预检和结果路径都包含该 ID；双模式共享该 sample 的 seed，不同 sample 使用各自冻结初态。增大 N 时输出新 manifest/run，保留旧版清单；已有相同身份的准备缓存可校验后复用，但不修改旧 run 或自动把旧成绩计入新批次。

| 每 task/difficulty 样本数 N | 场景实例 | 双模式各一次的 trial / 模型 |
| --- | ---: | ---: |
| 1 | 39 | 78 |
| 3 | 117 | 234 |
| 5 | 195 | 390 |

这里 N=3 是三个不同 seed 的实例，各跑一次；与“一个实例重复三次 trial”的统计含义不同。拟议抽样命令（待实现）：

```bash
python scripts/sample_difficulty_instances.py \
  --sampling-seed 20260929 \
  --samples-per-difficulty 5 \
  --out runs/difficulty_trials/difficulty-n5/manifest.lock.json
```

**3. 6 小时预算如何落地**

以 setting 中唯一的 `agent_wall_clock_s=21600` 驱动两种任务生成器。这里的 unlimited 表示可读取特权状态并重试场景，仍受 6 小时 agent 墙钟约束；不限制动作步数。仿真时间与墙钟时间分别记录。

“预算传播”指把这一处 21600 秒同步写入所有实际消费者：Harbor agent 超时、limited Compose 环境变量、服务倒计时、任务说明，以及由它计算的 collect/verifier 余量。这不是新增预算机制，也不涉及任务完成判据。若仅改文字或 Harbor 命令覆盖值，sim 仍可能显示旧的 5400 秒，收尾也可能沿用旧超时。还须核对有效 Harbor override/multiplier 没有把 21600 再缩短或放大。

| 位置 | 当前状态 | 本批改动 |
| --- | --- | --- |
| `scripts/topogym_mk_task.py` | `BUDGET_S=5400` | 增加显式预算参数；生成 `[agent].timeout_sec=21600` 和一致说明文字 |
| `scripts/topogym_mk_limited.py` | 独立硬编码 5400 | 从同一 setting/参数读取，禁止双模式预算不一致 |
| limited Compose | `RCB_WALL_CLOCK_S=5400` | 生成 21600；`/spec.budget.wall_clock_s` 必须等于 task.toml |
| limited `server.py` 模板 | 环境变量缺省 5400；服务 ready 后重置 `t0` | 更新缺省与校验；记录 ready、agent 开始及实际结束时刻，明确两时钟不同起点 |
| `ci_checks/check-task-fields.sh` | 超过 14400 秒失败 | 将 TopoGym 上限显式调整至 21600，保留其他字段检查，并记录与 vendor 基线的有意差异 |
| unlimited verifier | `3 × B + 900` | B=21600 时为 **65700 秒**，包含两遍重放和一遍录像 |
| limited collect | `600 + 2 × (B + 600)` | 为 **45000 秒**；每轮两秒轮询 11100 次，依次等 finalized 与 video_done |
| limited verifier | 1200 秒，读取服务证据 | 初版保留；与 collect 分开记录，检查 Harbor 实际阶段边界 |

上述重放预算沿用现有生成器公式，是规划余量，不是“重放一定不超过 live 时间”的保证。Nyx 录像、重建与硬件争用可能更慢；对代表性刚体/FEM 实测后可在 setting 中提高评分预算，不能因此延长 agent 的 21600 秒。collect 超时应明确失败，禁止仅 `cat final.json` 存在就视为完成。

当前 limited 服务提供倒计时，结束也依赖 Harbor collect 发来的 SIGUSR1；不能仅修改 `/spec` 就宣称已验证硬截止。实施时用短预算验证空闲、活动请求、长动作及中断的截止行为，在模拟器主线程安全边界结束/拒绝新动作，报告原生求解不可抢占造成的超时尾部。Harbor agent timeout 是 agent 阶段权威上限；limited ready 计时和 Harbor agent 起点可能有偏差，必须记录，首版不宣称两者严格同步。

不能用 `timeout 6h harbor run ...` 包住整个 job，否则会截断正常 verifier。78 次 agent 若都用满，共 **468 小时（19.5 天）串行 agent 时间**，总作业时间另含准备、建场、重放和录像。默认全局并发 1，agent/sim/verifier 共用 GPU 调度额度。

**4. 需要实现的文件和 Harbor 支持**

| 文件/组件 | 职责 |
| --- | --- |
| `scripts/difficulty_eval.py`（统一调度入口） | 解析参数、锁定 run、调用抽样共享函数及现有工具；读取冻结清单并顺序执行 `harbor run`；处理认证、资源监控、中断、恢复与完成判定 |
| `bash_scripts/run_difficulty_trials.sh`（兼容启动入口） | 选择 Python 解释器，用 `exec` 启动 `difficulty_eval.py` 并原样透传参数，信号直接交给 Python 处理 |
| `configs/sweeps/difficulty_eval.yaml`（新增） | 13 项编号目录，默认全选，可覆盖子集；所选任务固定三档、两模式、各一次 trial；每档 randomized sample 数可覆盖，默认 1；默认 21600 秒及固定资源策略 |
| `scripts/sample_difficulty_instances.py`（新增专职工具） | 维护编号映射与选择器；复用 registry/VariantRng/scene_variation，按指定难度抽取 seed 并输出 3TN 项 manifest；独立于 GPU 建场和作业调度 |
| `scripts/topogym_mk_task.py`（扩展） | 保留逐实例生成入口；消费 manifest 的 seeded/seed/有效参数，支持独立输出/slug/build-cache、预算和公共模板路径 |
| `scripts/topogym_mk_limited.py`（扩展） | 从指定 unlimited 包生成同实例 limited 包，读取同一预算和公共模板；不再自行选择场景 |
| `scripts/collect_batch_results.py`（扩展） | 保留旧 CLI；新增 manifest/job 列表输入、逐 job 状态检查、全部 78 项汇总和明确的 trial/attempt 目录，不再取 latest 覆盖 |
| `scripts/write_task_results.py`（按需扩展） | 若使用现有逐任务 README 输出，增加生成任务的根目录参数；当前硬编码 `root/tasks` 会跳过 run 私有任务 |
| `harbor_templates/topogym/common/rcb_topogym.py`（迁移维护源） | 公共 `make-instance`/Session 支持 seeded 与 scene seed、完整有效参数，保留显式档位和旧 eval-index 兼容；统一配置校验后真实建场冻结 |
| 现有资产准备/场景验收脚本和公共工具 selftest | Python 调度器调用这些入口准备 Blanket 初态及执行预检，缺少的检查补在对应现有入口，不另建 preflight 调度框架 |
| `scripts/mem_guard.py`（扩展） | 增加本 run 的精确进程/容器归属及 系统内存 90% 阈值模式（CPU 仅记录）；新入口不使用原全局匹配行为 |
| `ci_checks/` | 支持独立 dataset 根目录、6 小时预算、实例双模式一致性和任务副本一致性 |

**公共模板目录方案（待迁移）：**

```text
harbor_templates/topogym/
  common/rcb_topogym.py          # 唯一维护源，两模式及 verifier 共用
  unlimited/
    environment/               # Dockerfile、Compose 模板
    tests/                     # 独立评分器及 Docker 模板
  limited/
    environment/               # 客户端、Compose 和 sim 服务模板
    tests/                     # limited 独立评分器模板
    solution/                  # 通用轨迹回放工具（如仍需）
```

Cube 变成普通的示例任务包，不再承担模板源职责。其专属 instance、参考解和成绩保留在 cube 任务中，不进入 13 项正式清单。先逐字节抽取公共文件再调整生成器路径，避免迁移时顺便改变物理行为；预算与 variation/seed 支持作为后续独立改动。

维护源移动后，生成器仍把公共工具复制到各包的 `environment/`、`tests/` 或 `environment/sim/`。当前 Dockerfile 的 `COPY` 以这些目录为 build context，不能直接删除任务副本并改为仓库外相对导入或软链接。这样每个包仍可独立构建和评分，开发时只编辑公共源。迁移同步更新手册和一致性检查，检查生成副本与公共源逐字节一致；vendor 原样文件继续保留来源/哈希校验，位置变化单独更新映射。

当前 `topogym_mk_task.py --difficulty` 只是 README 难度说明，**不会切换物理场景**；`--eval-index` 也不能直接当作 easy/medium/hard，目前每个 family 的实例列表只有一个入口。须先改真实实例选择链，再生成任务。

每个 unlimited 包包括 `instruction.md`、`README.md`、`task.toml`、agent Dockerfile/Compose、`environment/instance.json`、共享工具、独立 `tests/instance.json` 与评分器。limited 包从它复制实例到 `environment/sim/instance.json`，配齐客户端、协议、sim 服务、Compose、收尾与独立评分器。limited agent 不获得物体真值、冻结实例或判据源码。正式 13 家族没有 Harbor oracle 的项明确标记，使用真实模型运行，不以 nop/oracle 代替本次正式 trial。

生成到 run 私有目录，避免覆盖现有 `tasks/`、dataset 和旧实验。各包采用如 `topogym-cast-coil-easy-s00[-limited]` 的独立名字，真实 scene seed 存 manifest；重算 Harbor dataset digest，并核验容器内实际 instance 哈希，防止构建缓存装入另一实例。

当前 `ci_checks/run_all.sh` 虽接受单任务路径，repo 级检查仍硬编码根 `tasks/`。必须参数化这些检查或提供等价的 run dataset 检查，不能用旧 28 包检查通过冒充新 78 包通过。

镜像从冻结源码构建一次，agent/limited sim/verifier 固定同一身份。特别检查 Blanket 初态包和外部资产：当前基础 Dockerfile 主要复制 `topogym/` 与机器人资产，不能假设宿主 `configs/`、`runs/` 的状态包自动进入镜像。按实例打包完整依赖、重写可移植引用，在容器内预检；不要给 limited agent 暴露 sim 私有资产。

**5. 执行顺序与前置验收**

流水线为 `plan → prepare → preflight → run → collect`，每一步均可独立重入。`--phase all` 在 prepare、preflight 各阶段结束后检查全部计划实例；任何一项未完成就返回非零并保留证据，不进入下一阶段。模型 canary 和正式 trial 都必须等待全批准备及预检通过，单独 `--phase run` 也执行同一守卫。

1. **静态计划**：生成 39 条实例和 78 条逻辑 trial，检查候选、数量、唯一性、配置及六小时预算。不创建 GPU 场景、不调用模型。
2. **准备**：冻结源码、构建镜像；串行准备场景资产及 Blanket 状态包，真实生成 instance、describe 和双模式包。任何失败保存日志和身份，保留矩阵位置。
3. **39 项场景 gate**：在最终镜像中建场/reset；验证同实例重建、有限状态、任务必要对象、机器人关节及 home/声明的预抓取姿态；获取 Nyx + compact_lab 的规定相机观测。执行短程保持动作和小幅安全控制，检查动作确实推进物理、没有异常/NaN/非法初始终止，保存可重放非空轨迹并检查终止判据接口。
4. **动态资格**：对 Orbits、Slotted Post 等沿用任务现有稳定性检查；Blanket 明确保留 motion deferred。短程通过只授予 `runtime_smoke_passed`，稳定性单列。初版允许短程通过但稳定性待验的探索性试跑，结果标记资格受限；初始化/动作/重放失败则不得启动正式模型 trial。
5. **78 项协议 gate**：对每个选中实例，两种模式分别走实际 Docker 链路。unlimited 重放非空探针轨迹；limited 检查连接、obs、至少一次 submit、无 reset、收尾、服务端轨迹、重放和评分。沿用评分隔离检查；准备探针单独存储、不计入 78 次正式模型 trial，也不能在 limited 正式 episode 中先做探针。
6. **正式运行**：仅调度通过最低运行 gate 的项，每项新建容器/episode/agent 会话，limited/unlimited 从同一冻结初态开始。某项 blocked 不阻断其他合格项，但最终只能报告部分完成，不能声称完成全部 78 项。
7. **整理**：逐项读取 Harbor trial `result.json`、reward、trajectory、重放日志和视频，生成包含 blocked/pending 的完整表。`success=0` 可能是合法未解开；无轨迹、评分器异常、无重放证据分别分类，不能统称为物理通过。

所有真实预检应通过公共 `RuntimeEvidence/RecordingSession` 留存源码、配置、资产身份及可完整解码的录像。默认 CUDA + Nyx，不因 GPU 不足切换渲染器或降低精度；CPU/静态检查不赋予物理资格。

**6. Python 调度、Bash 入口与运行目录**

所有参数统一在 `scripts/difficulty_eval.py` 解析；Bash 只保留 7 行启动代码。也可用 `.venv-gs121-nyx/bin/python scripts/difficulty_eval.py` 直接运行，参数和默认值完全相同。`sample_difficulty_instances.py` 保留独立抽样 CLI，并提供共享的参数定义和 `prepare_manifest()`，不重复实现采样。

以下是待实现接口示例，现在不可直接运行。`--model` 由调用方提供；执行阶段显式选择 `--auth`，或通过 `--api-key` 明确选择 API 认证。`--agent` 默认 `codex`，可指定已验证的 Harbor agent/适配器。setting 不包含密钥，也不固定某个模型。

**参数名称与含义：**

| 参数 | 含义与默认值 |
| --- | --- |
| `--setting PATH` | 评测定义文件，默认 `configs/sweeps/difficulty_eval.yaml`；保存默认任务集合、固定难度/模式及默认样本数、预算 |
| `--tasks SELECTOR` | 指定所选任务，例如 `all`、`8`、`1,8-10,13` 或 `cast_coil,orbits`；默认 setting 的集合，详见前面的 1–13 映射 |
| `--list-tasks` | 列出 1–13 编号及 canonical task_id 后退出，不启动任何实验 |
| `--phase all` | 顺序执行 plan→prepare→preflight→run→collect；也可指定某个阶段，入口检查其依赖产物，不能跳过必要预检 |
| `--run-id NAME` | 唯一批次标识，用于产物目录和 job 名；不是 seed，也不表示 trial 数 |
| `--sampling-seed INTEGER` | 外层抽样种子，决定各 task/difficulty/sample 的 scene seed；默认来自 setting |
| `--samples-per-difficulty N` | 每个 task 的每档难度抽 N 个不同 scene seed 的实例；默认 1，支持 3/5 等；不是同场景重复次数 |
| `--agent-wall-clock-s 21600` | 每个实例每模式的 agent 阶段墙钟上限，单位秒；包括该阶段内的建场/执行/等待，不包含单独的评分录像阶段；覆盖 setting 后同步生成相关预算 |
| `--agent NAME` | 执行工具调用的 agent harness，例如 `codex` 或已验证的 Harbor 适配器类路径；不是推理模型，默认 `codex` |
| `--model MODEL_ID` | 交给 agent 的模型标识，如以前的 `openai/gpt-6-luna`；`openai/` 是提供方前缀，不决定订阅/API 认证 |
| `--agent-arg KEY=VALUE` | 可重复，转成 Harbor 的 `--ak`；例如 `reasoning_effort=max`、`version=0.157.0`；禁止覆盖已选择的认证方式/关键预算 |
| `--concurrency 1` | 整批最多同时活动的 trial 数，包含其 sim/verifier 占用；首版串行，仅接受 1，不通过此参数启动并行 agent |
| `--auth subscription\|api-key` | 明确选择自己的 ChatGPT 订阅或 API key；传 `--api-key` 且未指定 auth 时即为 api-key，resume 可从已冻结非敏感配置读取；禁止失败后切换认证 |
| `--provider openai\|openrouter` | API 接入 profile，默认 openai；subscription 首版固定 OpenAI Codex 登录。OpenRouter 使用现有适配器并单独验证；其他服务不可仅凭兼容标签自动接入 |
| `--auth-json PATH` | subscription 使用的 Codex 登录缓存位置，默认从 `CODEX_HOME` 推导，未设置时为 `~/.codex/auth.json`；只传路径，不打印内容 |
| `--api-key [VALUE]` | 直接提供 key；省略 VALUE 时从终端隐藏输入，显式空值报错。脚本自动映射至 Harbor 子进程的 provider 环境变量，无需手动 export；与 subscription 冲突时报错 |
| `--api-key-env NAME` | 可选备用方式：从哪个环境变量读取 key；默认按 provider 为 `OPENAI_API_KEY` 或 `OPENROUTER_API_KEY`；参数值是变量名，不是 key 本身 |
| `--env-file PATH` | api-key 可选的 dotenv 凭据文件；优先级低于 `--api-key`、高于继承环境变量。只读取允许的键，不用 shell `source` 执行文件，不全量传入无关凭据 |
| `--resume` | 校验冻结身份后跳过已完整结束项，继续未启动项；中断项按第 7 节处理，不是恢复模型上下文或 limited 旧 episode |

**为什么没有 difficulty / trials 参数：** 每个所选任务按定义覆盖全部三档和双模式，所以无需每次重复指定。每个 `(task, difficulty, sample_id, mode)` 只有一次 trial，对应 `-k 1`。选择 T 个任务且 `--samples-per-difficulty N` 时，总数为 `T × 3 × N × 2 × 1 = 6TN`；不增加同一场景的 replication。例如 `--tasks 8,9 --samples-per-difficulty 3` 为 18 个场景、36 次 trial；默认全 13 项为 39N 个场景、78N 次 trial。

**订阅方式，沿用之前 Luna 实验：**

本机之前实际的 `jobs/coil-full-20260929-172853/config.json` 记录了 `codex`、`openai/gpt-6-luna`、CLI 版本 `0.157.0`、`reasoning_effort=max` 和 `forced_login_method=chatgpt`。下面保留这个明确配置，不将其当作其他模型也支持 max 的保证。首次需要在宿主完成 Codex 登录并有可供 Harbor 上传的文件缓存；已有有效缓存时跳过登录。

```bash
cd /home/jianwen/topogym
# 首次准备登录时执行；该命令本身不是计划新增的接口。
# codex -c 'cli_auth_credentials_store="file"' login --device-auth

bash bash_scripts/run_difficulty_trials.sh \
  --setting configs/sweeps/difficulty_eval.yaml \
  --phase all \
  --run-id difficulty-eval-luna-subscription-n3 \
  --tasks all \
  --sampling-seed 20260929 \
  --samples-per-difficulty 3 \
  --agent-wall-clock-s 21600 \
  --auth subscription \
  --auth-json "${CODEX_HOME:-$HOME/.codex}/auth.json" \
  --agent codex \
  --model openai/gpt-6-luna \
  --agent-arg version=0.157.0 \
  --agent-arg reasoning_effort=max \
  --concurrency 1

# 中断后，核验 manifest 和实际作业状态再继续
bash bash_scripts/run_difficulty_trials.sh \
  --run-id difficulty-eval-luna-subscription-n3 --resume
```

**API key + model name 方式：**

```bash
cd /home/jianwen/topogym
# 不需要事先 export OPENAI_API_KEY；下面是直接传值的调用形式，示例不含真实 key。
bash bash_scripts/run_difficulty_trials.sh \
  --setting configs/sweeps/difficulty_eval.yaml \
  --phase all \
  --run-id difficulty-eval-api-coil-keyhole-n3 \
  --tasks 8,9 \
  --sampling-seed 20260929 \
  --samples-per-difficulty 3 \
  --auth api-key \
  --provider openai \
  --api-key '<在本机填写的 key>' \
  --agent codex \
  --model 'openai/<该账号可用且 agent 支持的模型 ID>' \
  --concurrency 1
# 将 --api-key 后的值省略，脚本会隐藏输入；也可使用 --env-file 或 --api-key-env。
```

第二个例子的 agent 预算省略时从 setting 取得 21600 秒，只跑 Cast Coil/Keyhole 的三档和双模式，N=3 共 36 trials。两种认证使用相同的 sampling seed、生成器版本和实验配置时，共同任务的抽样场景一致；账户可用模型集合并不因此相同。若使用 OpenRouter，需要 `--provider openrouter`、`--agent harbor_agents.codex_openrouter:CodexOpenRouter`、`--model openrouter/<provider>/<model>`；同一个 `--api-key` 会自动映射到 `OPENROUTER_API_KEY`。现有适配路径仍需纳入接入验收，不承诺任意 model name 均兼容。

**`--api-key` 的处理约定：**优先级为显式/隐藏输入的 `--api-key` > 指定 env-file 的所选键 > 继承环境变量。高优先级来源若显式为空或不可读则报错，不静默退回别的凭据。未指定 `--auth` 时，提供 `--api-key` 就意味着 api-key 模式；若同时指定 subscription 则在启动前报冲突。无值形式只从 TTY 隐藏读取，不存在 TTY 时明确失败，不在无人值守 job 中无限等输入；`--api-key=VALUE` 也可使用。

解析后只在受限的 Harbor 子进程环境中映射 provider 所需变量，不写用户 shell 配置、不永久 export、不保存 key 到 setting/manifest/job 参数列表。记录命令时将该字段显示为 `<redacted>`，不记录原始 argv、不启用 shell xtrace，也不把 key 当作 Harbor 的 `--ak` 或 CLI `--env` 值。日志整理继续检查实际 credential 值。

直接传值仍可能被调用方 shell 历史和操作系统进程参数记录，脚本的日志脱敏不能消除这部分可见性；不想在命令行放 key 时可用无值 `--api-key` 隐藏输入，同样无需配置环境变量。使用直接/隐藏输入凭据的 run 恢复时需重新提供 key（例如 `--resume --api-key`），不从历史 manifest 恢复秘密；认证模式/provider 保持冻结。

**认证到 Harbor 的映射与验收：**

| 入口认证模式 | Harbor/agent 配置 |
| --- | --- |
| subscription | 在 Harbor 子进程环境设置 `CODEX_FORCE_AUTH_JSON=1` 和解析后的 `CODEX_AUTH_JSON_PATH`，由 Harbor 上传登录缓存；向标准 Codex agent 注入 `config.forced_login_method=chatgpt` |
| api-key + openai | 清除子进程继承的 `CODEX_FORCE_AUTH_JSON`/`CODEX_AUTH_JSON_PATH`，将选定 key 映射到 `OPENAI_API_KEY`，标准 Codex 配置 `forced_login_method=api` |
| api-key + openrouter | 清除订阅认证选择项，映射到 `OPENROUTER_API_KEY`，使用项目现有 CodexOpenRouter provider/网关配置 |

订阅分支不注入 API key；API 分支不上传宿主的订阅缓存。所有清理/映射仅作用于新建的 Harbor 子进程，不登出宿主账号、不覆盖宿主 auth.json。只允许所选 provider/profile 的 endpoint 与必要凭据进入运行环境，拒绝和 `--auth` 冲突的 agent config、env-file 内容及不兼容的 agent/provider/model 组合。默认 OpenAI 接入不继承无意设置的第三方 base URL。

本机 Harbor `agents/installed/codex.py::_resolve_auth_json_path()` 确认了登录缓存优先于 API key 的选择逻辑，所以需要上述显式隔离。Codex 本身支持订阅和 API key 两类认证、文件缓存和指定登录方式，见 [OpenAI 官方认证说明](https://learn.chatgpt.com/docs/auth)与[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。这里 `--auth`、`--auth-json`、`--api-key`、`--api-key-env` 等是评测入口参数，由 Python 解析、Bash 透传；`CODEX_FORCE_AUTH_JSON` 是 Harbor 集成变量，不是官方 Codex 登录命令。

run/all 启动前验证所选凭据存在且类型正确，接入 canary 验证实际 agent 能用指定模型调用工具、观察图像并走完整 Harbor 链路；canary 产物单列，不计为正式样本。分别验收 subscription 和 api-key，包括二者同时存在、缓存过期、key 错误、模型不可用时的明确失败及“不自动换认证/模型”。认证失败或额度耗尽暂停该模型队列，不把缺失 trial 记为解题失败。

`--phase plan` 是无模型调用、无 GPU 执行的 dry-run；plan/prepare/场景 preflight 不强制要求模型凭据，模型接入检查在 run 前进行。resume 从冻结配置读取并拒绝身份、认证模式或预算漂移；刷新同一来源的凭据不修改实验定义。manifest 只保存 auth 模式/provider/agent/model/非敏感参数及凭据来源描述，不保存 key、token 或 auth.json 内容；已有日志整理/脱敏逻辑覆盖两种凭据，真实结果以 Harbor agent 使用的认证和模型配置为准。

每个逻辑 trial 使用一次 Harbor 调用，`-p` 指向单个生成包，`-n 1 -k 1 --max-retries 0`。记录非敏感执行配置，Harbor 保存有效 job 配置；Python 用参数列表启动子进程，不用 shell `eval` 拼接 agent 参数。本机 Harbor CLI 源码已确认上述重试参数。Python 调度器负责循环与进程管理，agent、sim、独立 verifier、收集产物和预算执行仍交给 Harbor。

循环的核心是下面这段；`trial_queue.tsv` 由已冻结 manifest 导出，包含通过预检且尚未启动的项。路径字段禁止 TAB/换行，空格正常保留。此片段仅展示调用方式，完整入口还包括前述预检、状态检查、资源守护和信号处理。

```bash
while IFS=$'\t' read -r task_path job_name; do
  cmd=("$HARBOR_BIN" run -p "$task_path"
       -a "$AGENT" -m "$MODEL"
       -n 1 -k 1 --max-retries 0
       -o "$JOBS_DIR" --job-name "$job_name")
  cmd+=("${AGENT_ARGS[@]}" "${AUTH_ARGS[@]}")
  if "${cmd[@]}" >"$LOG_DIR/$job_name.log" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  printf '%s\t%s\n' "$job_name" "$rc" >>"$RUN_DIR/exit_codes.tsv"
  # 交由扩展后的 collect_batch_results.py 检查实际 trial 状态和证据；退出码不代表解题成功。
done <"$RUN_DIR/trial_queue.tsv"
```

**方案比较与选择：**

| 方式 | 评价 |
| --- | --- |
| 一个 Python 调度器循环执行 `harbor run -p <单包>`，Bash 仅启动 | 本次采用；默认 78 次，每项 job、日志和退出码独立，逐项资源等待/账号异常停止/恢复容易定位 |
| 一次 `harbor run -p <78 包的目录> -n 1 -k 1` | 也可运行已准备好的集合，调度代码更少；适合整体交给 Harbor，但逐项资格筛选、暂停条件及恢复策略仍需预先处理 |
| 原先三个新 Python 脚本加 Bash | 本次固定单模型、每模式一次、串行运行不需要，取消 |

已有 `scripts/run_agent_batch.sh` 本身就是循环 `harbor run`，证明无需自建执行层；但不直接套用它：它按顶层 `result.json` 存在就跳过作业，使用全局 `rcb-log-mirror` 和宽泛 mem_guard，任务路径也固定为根 `tasks/`。统一 Python 调度器保留所需循环，不继承这些行为，也不为 13 个任务分别创建运行脚本。真实难度/seed、预算传播、独立输出、特殊资产和完成判定由公共工具与调度器共同实现。

```text
runs/difficulty_trials/<run_id>/
  setting.effective.yaml
  manifest.lock.json
  source_identity.json
  instances/<task>/<difficulty>/<sample_id>/instance.json
  build/<instance_id>/describe.json
  tasks/<task_slug>/...
  tasks/dataset.toml
  trial_queue.tsv
  exit_codes.tsv
  trials.jsonl
  results/<task>/<difficulty>/<sample_id>/<mode>/trial_01/attempt_01/...
  summary.csv
  summary.md
jobs/difficulty_trials/<run_id>/<job_name>/<Harbor trial>/...
runs/test_results/difficulty_trials/<run_id>/...
```

逻辑 trial 主键：`manifest_hash/model_config_hash/task/difficulty/sample_id/mode/trial_01`，另存 Harbor job/trial 的真实 ID，不能从截断目录名猜测。模式执行顺序由固定 seed 平衡并写入 manifest，便于降低固定先后顺序造成的环境偏差。

**7. 恢复、资源和结果规则**

**这里的“完成判定/中断处理”分三层，不能混用：**

| 层次 | 当前已有实现 | 本批需要做什么 |
| --- | --- | --- |
| 物理任务成功/失败与 episode 终止 | 任务 `evaluate_state/evaluate_transition`、公共 `TaskDefinition.update()`、Env terminated/truncated、Session 与 sim `finish()` | 沿用，不在 Bash 重写解题判据 |
| 单次 Harbor trial 超时、收集、评分和取消 | Harbor trial 生命周期；RCB limited SIGUSR1 收尾、服务端重放/录像与独立 verifier | 沿用公共机制，验证参数一致及真实运行行为 |
| 78 项批次续跑 | RCB `run_agent_batch.sh` 有循环及 claim，但以 job result 文件存在判断跳过 | Python 调度器/整理器确认实际完成状态，保留中断记录，只续未启动项；不重跑已完成项、不把低分误当基础设施故障 |

参考仓库已在本地按固定 `fa59c1a6` 核对：`scripts/run_agent_batch.sh`、`tasks/robowits-stack-cubes-i00-limited/environment/sim/server.py`、该任务 `task.toml` 和 `scripts/regrade_trials.sh` 都有相关机制。其批量脚本在 result 文件存在时直接 skip，不能作为本批“完整完成”的唯一判断；TopoGym 的有限扩展应保持在批次记录和恢复边界，不另写物理终止系统。

另有独立的计分资格问题：当前 Orbits、Rope Threading、Slotted Post Ring 的 Task 基类均显式 `goal_complete=False`。公共终止框架存在，但这三项当前不能授予 `task_success=True`；即使基础仿真跑通，也只能作运行探针或未具备成功计分资格的探索性 trial，不能将其 0 分解释为模型解题失败。正式成功率报告前需要补齐并验收对应任务判据，而不是修改 Bash 来绕过该标记。manifest/汇总必须记录 `goal_evaluation_complete` 与 `evaluable_for_task_success`。

- `flock` 防止同 run 重复启动；manifest 不变，Harbor 原始结果是执行状态依据，整理器原子重建 `trials.jsonl`，不再另建状态数据库。状态至少有 pending/running/completed/blocked/infra_error/interrupted，任务结果另列 solved/unsolved/invalid_submission。
- resume 先验证快照、实例、包、预算与模型配置，再对账活跃进程/容器。已完成且证据完整的 trial 跳过；只有顶层 result.json 不算完成。未知 running 状态先调查，不重复启动。
- 本批 `--resume` 默认只继续未启动项，保留中断项待处理。不要直接对所有旧目录重放 `harbor run` 或 `harbor jobs resume`：本机 Harbor 会在恢复时删除部分缺 result 的 trial 目录，resume 还默认筛除 `CancelledError` 项。恢复单项前先保存原始产物；需要重新模型执行时采用下面的显式新 attempt 规则，不假定能续接旧 limited episode。
- 每模式一次正式 trial，不因失败或低分自动重跑。基础设施故障保留 attempt；需要恢复执行时显式标为新 attempt，并固定有效结果选择规则，不能选择最高分。verifier 故障优先重判原轨迹。
- 整批并发默认 1；GPU 空闲显存门槛按实际家族峰值设置，FEM 不沿用轻量 cube 的需求。资源等待有界，超限标记资源阻塞。持续监控 CPU、宿主和容器内存；按 2026-09-30 更新，仅系统内存达到 90% 阈值停止本 run 相关工作，保留产物，不终止其他实验。
- 捕获 INT/TERM：停止发新 job，记录当前状态并仅清理已登记的本 run 进程组、容器和 Compose project。不使用全局 `pkill`、容器名宽泛匹配或 Docker prune。中断清理与正常 collect 分开，不无限等待十余小时的评分预算。
- 每项记录 agent/初始化/仿真/collect/verifier 耗时、实际动作步数、峰值资源、token、可得费用、错误原因和证据路径。未知费用记 null，禁止填 0。认证或模型配置错误暂停对应队列，避免重复空跑。
- 汇总按 manifest 列出 expected=`6TN`（默认 78）、launched、completed、evaluable、solved、blocked、infra_error；完整成绩应有所选 task/difficulty/sample 的双模式一对结果。报告显式列出所选和未选任务，不能将未选项计为失败。一次样本不代表难度分布，也不声称完整可解性。

**8. 实施次序和验收条件**

| 阶段 | 交付与验收 |
| --- | --- |
| P0 公共模板与真实实例选择 | 先逐字节迁移公共维护源并检查生成副本，再由专职抽样脚本贯通 seeded/seed/有效参数；静态产生 39 实例、78 唯一 trial；Orbits 不能落回 reference85 |
| P1 六小时和独立输出 | 两生成器、Compose、服务、CI、说明及收尾预算一致；所有检查作用于新 dataset；旧任务包不被覆盖 |
| P2 场景与容器 gate | 当前镜像逐实例建场、Nyx、动作、重放；特殊初态依赖齐全；输出 39 项资格表与 78 项协议结果 |
| P3 Python 调度/认证/恢复及 Bash 兼容 | 编号/区间/名称选择器、去重、非法输入、子集抽样不变与 6TN 计数通过；顺序调用 Harbor；subscription（原 Luna 配置）与 api-key 两条路径均完成 canary；直接 key、隐藏输入、env-file/env 的优先级、脱敏和恢复不落盘通过；混合凭据不串用；dry-run 无副作用；短预算超时、信号中断、resume、资源归属检查通过；canary 与正式统计分开 |
| P4 78 trial 覆盖 | 每项恰好一次试跑；无静默换 seed、覆盖结果或重复运行；未完成项全部明确呈现；判据未完成项单列，不纳入模型解题成功率 |

先用离线 fixture 验证抽样复现、双模式实例一致、预算传播、独立输出、结果状态和恢复去重；再用短预算真实 probe 检查超时/收尾。GPU/模型验收与离线检查分开记账。无需等所有模型解题成功才算批量脚本有效，但只有 78 项全部获得完整执行和评分证据，才可声明本批端到端覆盖完成。

本次文档核对只读取现有源码、配置及历史证据，未新启 GPU 仿真或模型请求。下一步实施应先解决 P0/P1，再以 P2 的结果决定可启动哪些正式 trial；当前仍不能承诺全部 13 家族三档均已验证可正确长时仿真。

## 实现落地补充（2026-09-29）

- 主配置、抽样工具、公共模板、现有生成器扩展及现有 collector 扩展均已落地；按后续授权新增单一 `scripts/difficulty_eval.py` 统一调度，Bash 从 606 行精简为 7 行。没有拆出独立的 prepare/run/collect 脚本，原命令、默认全任务/每档 1 个样本、认证方式、6 小时预算和恢复语义保持兼容。
- 公共模板维护源迁至 `harbor_templates/topogym/`；已有 28 个示例/任务包只同步共享 Python 工具，历史实例、预算和结果不重生成。
- 每次 run 复制实际 dirty 源码及机器人资源，在 Docker 中完成新 seed 的建场/冻结与检查，避免宿主 Python 与镜像的数值初态版本不一致。原计划使用宿主模拟器的部分由此替换。
- 物理 preflight 使用现有 Session 加公共 `SegmentMedia`，另用真实 limited 客户端检查短动作和 30 秒自动期限。已归档研究测试不再作为运行依赖。证据跟随 run 保存于 `build/<slug>/`；开发合同日志另存 `runs/test_results/`。
- canary 复用通过 preflight 的相机帧，不额外建 cube 场景，且不进入正式 trial 统计。其评分只确认模型提交了工具/图像检查结果，不是物理成功判据。
- 首版 `--agent-arg` 只接受 `version`、`reasoning_effort`；`--rerun-incomplete` 明确创建新 attempt。默认恢复不自动重跑已开始的 job。
- 真实 13×3 场景的物理检查、Blanket 任意抽样 seed 的容器重载、真实订阅/API canary 仍须在资源可用并给出运行凭据后执行。不能将 CPU 工作流测试或抽样清单视为这些验收已通过。
