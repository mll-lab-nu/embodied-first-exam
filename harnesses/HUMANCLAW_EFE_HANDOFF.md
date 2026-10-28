# HumanCLAW 接入 Embodied First Exam：Harbor tasks 与 harness 完整交接

核对日期：2026-10-27。接收者：EFE 合作者及负责实现的 coding agent。

## 0. 要完成什么

**请同时完成两项接入，并证明它们能一起运行：**

1. **Benchmark 接入**：把 HumanCLAW 的环境、冻结 episode、动作执行、成功判定和轨迹记录，封装成 Embodied First Exam（EFE）能够发现、启动、评测的 **Harbor-format tasks**。
2. **Harness 接入**：把迁移来的 HumanCLAW harness，尤其是 native Codex/Pi 路径与 adaptive Pi 的接口发现、校验、执行和修复能力，接到 EFE 的任务接口上。在同一批 HumanCLAW tasks 上跑通 EFE 原生 agent 和我们的 harness；再用一个已有 EFE standard task 验证 harness 的通用接口。

最终交付是可运行代码、可复现命令、测试证据及简明文档。复制源码目录、只跑 HumanCLAW 原 CLI、只做 Harbor task 模板、只接 harness 中任意一项，都不算完成。

现有 HumanCLAW PSV / Bare API / Codex / Pi 源码均已完整迁移，不能再次缩减成只有 Pi 的小包。保留这些实现和能力说明；HumanCLAW PSV 用于原行为基线，EFE 原生 Codex 用于独立任务验收，adaptive Pi 必须有真实的 EFE 运行入口。已有 LIBERO 等集成保留原状，本次新 benchmark 的主体是 HumanCLAW。

可以按照 EFE 的贡献规则把 task、共享支持代码、harness 拆成关联 PR；拆分不改变上述两项都必须完成的范围。

## 1. 正确的代码来源，以及当前已经做到哪里

| 项目 | 固定参考 |
| --- | --- |
| 目标仓库 | https://github.com/mll-lab-nu/embodied-first-exam |
| 来源 fork | https://github.com/HenryLiu0405/embodied-first-exam |
| 已有 PR | https://github.com/mll-lab-nu/embodied-first-exam/pull/490 |
| 来源分支 | `codex/harness-improving` |
| 完整导入 commit | `fe3d37676264cba2f71569aa8822428e9c73e1ca` |
| 导入时的 EFE base | `49395ed94f2be39fbe254ac881e2dcb1b5eb2320` |
| 原 HumanCLAW 来源 commit | `f7defc43cb295bda7142112a6a40a39aac2e1a45` |
| 完整源码在 EFE 中的位置 | `harnesses/humanclaw/` |
| 该目录的 Git tree hash | `f60d71a04c79411089fc5e606322b96f61cad8dd` |
| 来源清单 | `harnesses/humanclaw-source.json` |

PR #490 在核对时是 open、非 Draft。它包含 **15,125 个原始 tracked 文件、94.4 MiB 的完整 HumanCLAW 源码快照**，以及来源清单和顶层介绍。它目前完成的是源码导入，**尚未注册 HumanCLAW Harbor tasks，也没有完成 EFE verifier / runner / agent 接线**。

PR 前两个 commit（`5362886`、`fbbd53f`）曾经只提取独立 adaptive harness。**不要只 cherry-pick 这两个 commit**。完整来源是最后的 `fe3d376`；最终树里 Pi 位于 `harnesses/humanclaw/harnesses/pi-adaptive/`，不再使用早期独立的 `efe_adaptive` 包。

源码快照不包含未跟踪文件、密钥、已安装依赖、外部 HSSD 数据、外部 checkpoint 和服务器上未提交的结果。已经提交过的资源、报告和证据属于快照的一部分。完整源码不意味着 GPU 运行资产已经齐备。

### 获取可核对的来源

在自己的 EFE clone 中执行以下只读获取步骤；worktree 目录须选择尚不存在的路径：

~~~bash
git fetch https://github.com/HenryLiu0405/embodied-first-exam.git codex/harness-improving
git show --no-patch --oneline fe3d37676264cba2f71569aa8822428e9c73e1ca
git rev-parse fe3d37676264cba2f71569aa8822428e9c73e1ca:harnesses/humanclaw
git worktree add --detach ../humanclaw-pr490-source fe3d37676264cba2f71569aa8822428e9c73e1ca
~~~

tree hash 必须等于上表值。这样 coauthor 不需要访问原 private repository。

在独立 integration branch 实现，不覆盖他人未提交改动，不改动原 HumanCLAW-PRO 仓库、remote 或分支。先判断 PR #490 是否已经合并：已合并则基于维护者当前 main；未合并则明确采用叠加 PR 或维护者认可的导入方案，并在 PR 中写清依赖。不要盲目把含大批源码的 commit 当作 task-only PR。

**本文件是新的 EFE integration handoff。** 导入源码里的 `docs/COAUTHOR_HANDOFF.md` 是此前在另一台 GPU 服务器运行 HumanCLAW 的说明，含旧分支、旧部署环境和历史 fullval 约束，不能当成本次 EFE 接入说明。

## 2. 开工前的阅读顺序

以下相对路径从 EFE 仓库根目录解释。记 `H = harnesses/humanclaw`，这是本文的路径缩写，不是新增环境变量。

1. EFE：`AGENTS.md`、`README.md`、`CONTRIBUTING.md`、`docs/protocol/README.md`、`docs/protocol/running.md`。
2. EFE task 与隔离：`docs/protocol/standard_mode.md`、`docs/protocol/leakage.md`、`docs/REVIEWING.md`。
3. EFE 参考任务：`tasks/robotwin-2/robotwin_2_0_stack_blocks_two-standard/` 及它的 `-privileged` twin。
4. EFE 服务参考：`embodied_first_exam/standard/toy_server.py`、`rcb_limited.py`、`rcb_client.py`、`rcb1.py`、`run.sh`。
5. HumanCLAW：`H/README.md`、`H/docs/ARCHITECTURE.md`、`H/docs/ASSETS.md`、`H/docs/METRICS.md`。
6. Harness：`H/docs/NATIVE_HARNESSES.md`、`H/docs/AUTONOMOUS_INTERFACE_LOCAL.md`、`H/harnesses/pi-adaptive/package.json` 与 `H/harnesses/pi-adaptive/src/`。

以实施时 checkout 的 EFE 规范为准，记录相对上述固定 base 的变化。当前协议中一般配置建议与 Appendix H 的强制不变量不同：benchmark 可以声明设置差异，不能放松 H.1–H.8。

当前贡献流程要求新 benchmark 有已批准的 proposal。先找已有的 `proposal-approved` issue；没有则准备 proposal，说明任务定义、资产、协议、资源、评分、oracle 和接入范围，交由 coauthor 与维护者确认。PR #490 的存在不等于已获得 benchmark 接入批准。源码审查、接口实现和本地测试可先形成可审查结果；正式合并遵循维护者流程。

## 3. 最终系统应如何连接

~~~text
Harbor / EFE runner：分配 task、seed、时间与资源，管理容器和结果
  |
  +-- main / agent 容器
  |     选择 A：Harbor 原生 Codex（独立验证 task）
  |     选择 B：我们的 Pi / adaptive harness（本次必须接入）
  |         公共 instruction + RGB / 允许的 proprioception
  |         公共 client / 经校验的 tool binding
  |                    |
  |                    v
  +-- sim 容器：HumanCLAW session
  |     冻结 episode -> skill 校验 -> motion model
  |     -> patched Habitat-Sim / Half-Physics -> 新观测
  |     可信状态、终止判定、指标、轨迹、视频、最终 verdict
  |
  +-- 独立 verifier 容器
        读取可信的 finalized verdict / 证据 + 资源监控
        -> /logs/verifier/reward.txt 与 reward.json
~~~

三个边界必须保持：

- **Agent 做决策**；sim 执行动作和物理演化。不能在 sim 中再启动一个 HumanCLAW planner 替 EFE agent 解题。
- **Harbor task 与具体 agent 解耦**；没有我们的 harness，原生 Codex 仍能通过公共工具操作 HumanCLAW task。
- **评分属于可信环境/verifier**；harness 的反思、修复 reviewer 或 agent 自写的 `metrics.json` 都不能成为成绩来源。

原 HumanCLAW 的 “verifier” 有 planner/action validation 含义，与 EFE 的独立奖励 verifier 是不同组件。实现和文档里要明确命名。

## 4. HumanCLAW 现有架构与复用位置

| 层 | 来源文件（相对 H） | 本次接入职责 |
| --- | --- | --- |
| Episode | `src/humanclaw_bench/benchmark/episodes.py` | 读取冻结实例，保留 scene、target、初始状态和预算 |
| 环境 | `src/humanclaw_bench/envs/find_nav_interact_env.py`、`envs/half_physics_env.py`、`envs/half_physics/hp.py` | sim 生命周期、物理推进、公共观测与私有状态 |
| 动作与运动 | `src/humanclaw_bench/agent/skills.py`、`agent/types.py`、`motion/runner.py`、`motion/conditioning.py`、`motion/state.py` | 参数校验、动作标准化、motion 生成与坐标变换 |
| Episode 执行 | `src/humanclaw_bench/evaluation/evaluator.py` | 提取 reset / execute_decision 所需逻辑，保持行为一致 |
| 评分与记录 | `src/humanclaw_bench/evaluation/metrics/episode.py`、`evaluation/trajectory.py`、`evaluation/replay.py`、`evaluation/video.py` | 可信判据、前后轨迹与证据 |
| Native harness | `src/humanclaw_bench/harnesses/runtime.py`、`environment.py`、`services.py`、`pi_adaptive.py` | 保留 agent 生命周期，替换环境绑定与部署位置 |
| Adaptive Python | `src/humanclaw_bench/harnesses/adaptive/` | discovery、broker、校验、执行状态、repair、持久记录 |
| Pi TypeScript | `harnesses/pi-adaptive/src/` | runner、context、adaptation、execution boundary |
| 实验记录 | `src/humanclaw_bench/experiments/` | 把已有事件、usage、轨迹引用映射到 Harbor trial |

原流程是：

`CLI -> evaluator -> PSV / Bare API / Codex / Pi -> SkillCall -> MotionSkillRunner -> Half-Physics -> RGB -> 下一次决策`。

优先复用 `evaluator.py` 中的 `_reset_env_for_rollout`、`execute_decision` 的真实执行语义。独立出不依赖 VLM 的 session 层，由 EFE sim service 调用；避免直接在服务里运行会构造模型和 agent 的完整 `evaluate_main`。同一 session 的 Habitat/OpenGL 调用留在拥有它的线程，用请求队列连接 HTTP 层，防止渲染上下文跨线程。

## 5. 必须保留的 benchmark 语义

### 5.1 Episode、动作与物理

- Canonical val 有 1,218 个 episode、41 个 scene，其中 597 个为 interaction episode；val100 是 100 个 episode、5 个 scene 的开发子集。索引键用 `(scene_id, episode_id)`，不能仅使用跨场景可能重复的 episode_id。
- Canonical 内容位于 `H/resources/benchmark/episodes/val/content/*.json.gz`。顶层 `val/val.json.gz` 可以是空 episodes 的 header，不能因此认定数据缺失。
- 保留 `start_position`、`start_rotation`、`init_offset`、`init_yaw` 等冻结值；已修正的 spawn 不要重新随机采样。
- 默认 paper 人体、hand-merged 配置与 `configs/paper_fullval_v1.json` 一致；finger-separated 作为另一个明确配置，不能静默替换。
- 动作包括 `walk_forward`、`side_walk`、`step_back`、`turn`、`step_climb_up`、`step_climb_down`、`sit`、`stand`。参数 schema、单位和边界从现有实现提取，写入公共 spec；不要凭名字重新定义动作。
- 非 Stop 动作生成 15 帧、30 Hz 的 75D SMPL-X motion chunk。保持坐标转换、4 次 PJSC 子步、root XZ 更新时点及原物理参数。
- 原实现的 `stand` 在该决策路径上是 Stop：提交当前姿态并终止，**不额外生成一段站立 motion**。公共接口要解释这个容易误解的行为。
- 原 profile 最多 100 个动作、无 reset。EFE 一般采用 wall-clock cutoff；首先保留 HumanCLAW 原预算并明确声明差异。若维护者选择去掉动作上限，应另立命名 profile，不能称其结果与原 paper_fullval 完全同条件。
- 时间预算、动作预算、episode 终止原因分别记录，不能用多次 reset 寻找更容易的实例。

### 5.2 成功判据

以下实现以 `evaluation/metrics/episode.py` 为准，接入测试直接对照原函数：

| 指标 | 应保留的含义 |
| --- | --- |
| NavSR@20cm | 主动 Stop，并且 body joints 到 target AABB 的最小距离不超过 0.2 m；不能换成 root 到目标中心距离 |
| InteractSR | interaction 类型、主动 Stop、至少一次 Sit，并且 Stop 前最后一段 motion 的最后一帧有 pelvis 与目标 mesh 接触；历史任意一次接触不够 |
| FindSR | 目标 semantic pixels 至少 100，并满足原实现的非否定目标可见性声明；GeoFindSR 仅是像素条件，两者不能混用 |
| Collision / disturbance | 基于实际 post-physics 轨迹统计 |
| Jerk | 基于 pre-physics 生成轨迹，不能与 post-physics 数据混算 |

首批 navigation task 的主 reward 使用 NavSR@20cm，interaction task 使用 InteractSR；其他指标作为诊断，除非 proposal 明确指定为该 task 的目标。FindSR 若进入主评分，必须另外定义公共声明如何记录，并复用原判定，不能临时用一个 LLM judge 替代。

**原环境 `step` 返回的 reward 为 0.0，不是 EFE 的任务成功奖励。** 也不能把非空 metrics dict 转成 bool 当作成功。奖励由 task 明确指定的谓词决定。

保留 `trajectory_before.npz`、`trajectory_after.npz`、`replay_manifest.json` 以及可信指标；映射为 EFE 需要的 journal / trajectory 和录像证据，并注明每种轨迹的含义。

## 6. GPU 环境和外部资产交接

把部署拆成 Harbor host、agent image、sim image、verifier image。当前 EFE 根项目固定 Harbor 0.23.0、Python >=3.12 且 <3.15；不要强迫 Habitat 的 Python / CUDA 环境与 Harbor host 共用一个虚拟环境。

| 内容 | 权威来源 / 注意事项 |
| --- | --- |
| HumanCLAW Python 依赖 | `H/pyproject.toml`、`H/constraints/eval-cu124.txt`；原 CUDA 路径为 PyTorch 2.6.0 / CUDA 12.4，按实际驱动验证 |
| Habitat-Sim | revision `acbe6f4922e68145e401e55c30f9dfea460a3f24`；按 `H/patches/habitat-sim/README_zh.md` 构建 headless / Bullet / CUDA 和 Python bindings |
| Half-Physics patch | `H/patches/habitat-sim/humanclaw_halfphysics.patch`；必须验证 patch 已应用，不能换成普通 Habitat-Sim |
| HSSD 官方资产 | 依 `H/docs/ASSETS.md` 获取有权使用的固定输入，不包含在 Git 中 |
| HumanCLAW HSSD supplement | https://huggingface.co/datasets/HumanCLAW/HumanCLAW-HSSD ，需要获准访问；登录不代表已获 gated 权限 |
| Motion weights | `H/resources/weights/paper_fullval_v1.json` 为权威清单；来自 https://huggingface.co/HumanCLAW/HumanCLAW |
| Pi runtime | 原 `package.json` / lockfile，SDK 固定 1.3.0、Node >=22.19.0；采用锁文件，不任意升级 |
| Adaptive Python | `humanclaw-bench[adaptive]` 依赖及原校验器；宿主、容器分别明确安装所需部分 |

权重归档 `HumanCLAW_pretrained_weights_paper_fullval_v1_20260816.tar.gz` 的 SHA-256 为：

~~~text
3b3c0c1b232af4c462301655de909a4bc54fd4756bcd42c22e7965fccb650667
~~~

推理权重约 1.136 GB；HSSD supplement 约 79.8 MiB 压缩包、1,693 个 mesh，完整场景还需要官方 HSSD 输入。这些大小不是 Docker image 总大小，也不是最低 GPU 显存要求。用实际完整 trial 测量内存、显存、磁盘和 CPU，再填写 EFE resource 声明。

准备时使用原 `prepare-hssd`、`assets` 工具。`prepare-hssd` 生成的目录含 symlink，容器构建必须把目标资产正确物化或封装在固定镜像路径；不能依赖作者机器的 HF cache、个人 home 或绝对路径。`src/humanclaw_bench/paths.py` 通过 `HUMANCLAW_BENCH_HOME` 或源码布局找资源；仅安装 wheel 不保证资源齐全。

镜像保留 Apache-2.0 LICENSE / NOTICE。资产能否随公共 image 分发按实际许可处理；需要限制分发则使用 EFE 的 BUILD_ONLY / 受控镜像方案，并交付可重建说明。不要把下载 token 烧进 image。Agent image 只带公共操作接口和 agent runtime；场景私有元数据、目标几何、指标逻辑和 motion 权重放在 sim / verifier 所需位置。

## 7. Workstream A：做成真正的 Harbor tasks

### A1. 冻结实例和任务集合

先用一例 navigation 和一例 interaction 跑通完整链路，再扩展所交付任务集合。提供受版本控制的 task 清单，列明 task 名、profile、实例摘要、seed、目标类别、成功谓词、预算和覆盖范围。

完整保留对 1,218 个 canonical episode 的读取与映射能力；不能硬编码只支持 demo 两例。初始贡献若只导出子集，要准确写出覆盖数量和选择规则，不声称已交付 fullval 全集。具体提交多少任务按批准的 proposal 冻结。

上游 episode ID 与原解答定位信息放在维护者 provenance / 可信元数据中，不进入 agent 可读镜像；公共 task ID 采用不泄漏解答位置的名称。每个 task 的实例在 trial 前冻结，agent 不能改 seed、目标或初始状态。

### A2. 提取可独立驱动的 HumanCLAW session

实现 session 的 reset、公共观测、动作执行、Stop、finalize 和 artifact 收集。内部方法名自行选择，但必须满足：

- reset 只由受信任生命周期调用；原配置无 reset 时，agent 无重置能力。
- Action schema 复用原校验与条件变换，非法动作返回可解释错误，不推进物理状态。
- 一条有效动作只执行一次；记录 observation/version、动作、开始/结束、实际推进、错误和终止状态。
- sim 保存私有 ground truth，返回过滤后的 RGB 和已声明 proprioception。
- terminal / cutoff 后拒绝新动作；finalize 可重复调用但不能再次执行物理动作。
- CPU 单测覆盖状态机；GPU 测试以固定动作序列比较原 evaluator 和新 session 的轨迹、终态、指标，报告数值误差，不能仅比较文件是否存在。

### A3. 明确公开协议，不能靠修改 URL 冒充兼容

HumanCLAW 的 skill 动作和 EFE 的标准 action contract 不必天然等价。先提交一张接口映射表：每个公共观测字段、动作字段、单位、坐标系、终止语义、超时和重试规则如何映射。

**优先保持 HumanCLAW 的动作与物理语义。** 若 EFE 现有 `eai-standard/2.x` 的 adapter / 声明的 action extension 能准确表达，就复用原共享 client、RCB1 和服务层，并通过协议测试。若不能，就使用 EFE 协议 §3 允许的 benchmark-specific exported protocol，在 `ci_checks/benchmarks/humanclaw/exported.toml` 中登记、补充检查；这仍然是 Harbor task。

不得把 JSON-only skill API 标成 `eai-standard/2.2`，也不得把 2.4 的 operations/idempotency 能力解释为任意高层 skill 接口。协议名、`/spec`、task metadata、文档和 CI 必须一致。

若使用 2.2，共享 `rcb_client.py`、`rcb1.py`、`rcb_limited.py`、`run.sh` 按 EFE identity 规则使用；benchmark 差异放 adapter 中。若使用 exported protocol，提供 agent 可用的简单 client、同等隔离与真实 trial 证据，说明与标准协议的差异。无需为了形式统一改写原运动控制器。

### A4. 任务目录和共享运行时

下面是**拟新增布局**，不是当前 PR 中已经存在的文件。按维护者认可的 benchmark 前缀和命名落地：

~~~text
tasks/humanclaw/
  README.md
  <task-name>-standard/
    task.toml
    instruction.md
    README.md
    DIGEST
    environment/
      Dockerfile
      docker-compose.yaml
      sim/
        Dockerfile
        <可信的冻结实例文件>
    tests/
      Dockerfile
      test.sh
      <grader 或从固定 files image 复制的 grader>
    solution/
      solve.sh
      <仅 oracle 路径可访问的参考方案>

images/humanclaw/
  Dockerfile
  VERSION
  <构建与资产清单>

embodied_first_exam/benchmarks/humanclaw/
  <session、server adapter、grader 与公共 tooling 的共享源>

ci_checks/benchmarks/humanclaw/
  <benchmark 检查；使用 exported protocol 时增加 exported.toml>
~~~

先做 standard 模式即可满足这一阶段；README 明确说明没有 privileged twin。若新增 twin，必须是同一冻结实例、成功条件、seed 和 cutoff，不能通过降低标准让 oracle 通过。

任务 runtime 不得通过 `../../harnesses/humanclaw` 或宿主 editable install 偷读仓库。把所需代码安装进固定 base image，或通过 EFE files-only image + `FILES.json` 物化进任务镜像，`COPY --from` 使用固定 digest。Agent-facing 公共 client 与 sim 私有代码分开打包。

完成必要注册：`scripts/task_conventions.py` 的 benchmark/folder 表、`ci_checks/ci_scope.py` 的 UNITS、`scripts/task_resources.toml` 的资源规则，以及 taxonomy / benchmark checks 中实际需要的项。不要关闭现有检查来跳过新 benchmark。

任务生成器、oracle 搜索器、实例冻结脚本和结果包不要混进 task-only 上游贡献；按贡献规范放在维护者认可的开发工具位置或独立工作区。只把最终任务运行必需的代码和声明交付给任务 PR。

### A5. instruction 与资源

instruction 应让一个不熟悉 HumanCLAW 的通用 agent 能操作：目标、观测、动作参数和示例、坐标/单位、Stop 语义、时间/动作/reset 预算、允许的外部材料。公共接口不能包含 target ground-truth pose、成功状态探针或 oracle。

以 task.toml / resource rules 为单一来源运行 normalizer，生成 README、instruction 的资源与时间段、monitor / sanitize 配置及 DIGEST。不要手工伪造生成段或设置一个从未测量的 GPU 下限。

### A6. 可信评分和结束流程

遵循参考任务的 monitor seal、停止 agent 进程、sim finalize、等待 verdict、收集 artifact、独立 verifier 流程。finalized verdict 先落盘，视频随后生成，视频耗时不影响成功判定。

- standard 模式按本次 **live episode** 的真实结局评分；replay 用于诊断和视频验证，不能用另一次 replay 的成功覆盖 live 失败。
- `reward.txt` 写单个 0 或 1；`reward.json` 数值字段遵循 EFE 约定，包含适用的 success、live_success、graded_by_live、错误和资源字段；字符串细节放其他日志。
- 不能信任 agent 提供的 metrics / reward；隐藏成功谓词、trusted volume、verifier 镜像对 agent 不可写。
- 基础设施在动作前失败与动作执行中 sim error 要按 EFE 分类，后者不能一概当 infra retry。动作结果不确定时不得盲目重发。
- 保留 trusted trajectory、终态摘要、可播放视频及 `video_source`。若尚未验证 bit-wise replay，standard 使用 live recording；不要先声称 deterministic。
- 缺失资产、verdict 或必需记录是需要报告的错误，不能通过填默认 reward / 空文件伪装正常完成。

## 8. Workstream B：把我们的 harness 接进 EFE

### B1. 提供真正的 Harbor agent 入口

实现独立、可安装的接入包，例如 `harnesses/humanclaw-efe/`、Python import path `humanclaw_efe.agent:HumanClawAdaptiveAgent`。这些名称是建议，最终以实际交付为准。

Harbor wrapper 管理安装、启动、日志、usage 和取消；实际模型循环、工具调用、Python LocalServices / MCP、Pi SDK 和自生成程序都运行在 **main agent 容器内**。不能在宿主或 sim 容器上执行 agent 工具。

采用 Harbor 0.23.0 对应的 `BaseInstalledAgent`；核对该版本的 `install`、`run(instruction, environment, context)`、日志收集和 `AgentContext` 契约，不套用另一个版本的 `AgentResult` 示例。接入类必须能被 Harbor host import；被执行的 agent runtime 则必须安装在容器内。EFE 根 wheel 目前不会自动打包整个 `harnesses/`，所以两边安装流程都要写明。

参考：[Harbor custom agents](https://docs.harborframework.com/agents/custom-agents)、[固定版本 BaseInstalledAgent](https://github.com/harbor-framework/harbor/blob/v0.23.0/src/harbor/agents/installed/base.py)。不要直接照抄最新版文档中该固定版本没有的方法。

至少交付以下运行配置：

| 配置 | 用途与要求 |
| --- | --- |
| EFE native Codex | 完全不依赖我们的 adaptive loop，使用公共 task tooling；验证任务本身可用 |
| HumanCLAW Pi / adaptive with explicit binding | 对接新的 HumanCLAW 公共接口，保留 broker、校验、状态和修复能力 |
| Adaptive bootstrap / discovery | 从 agent 可读 spec/docs 开始发现接口；不能暗中注入同一目标的手写 binding 后声称自主发现 |
| 原 HumanCLAW PSV | 保留可复现的独立基线和原行为对照命令；其结果与 EFE trial 分开标记 |

对 HumanCLAW native Codex 现有工具封装，保留能映射到新公共 binding 的可用路径；无需把原生 Codex 重新命名成一个没有增加功能的 custom agent。对未实现或未验收的其他 agent profile 明确标记，不能声称全部路径已验证。

### B2. 环境绑定与 RCB1 transport 是具体开发项

`NativeHarness.run` 已支持 environment binding 注入；把原 `EnvironmentBridge` 的本地环境 callback 替换成对 EFE 公共接口的客户端。梳理已有 binding 的 `catalog()`、`observation_id`、`execute(tool, args)` 和适用的 `reconcile` 契约，保持 observation 与 action receipt 的关联。

**已确认的兼容缺口**：adaptive autonomous HTTP adapter 当前按 JSON 编码并用 `json.loads` 解码；EFE standard client 使用 `application/x-rcb1` 二进制封包，包含 JSON header 与 RGB 等 raw blobs。仅改 base URL 无法接上。

需要实现受管理的 RCB1 transport / client binding，或者调用 EFE 已有公共 Python client，将结果转换成 harness 的图像/工具结果类型。支持长动作、超时、operation/receipt 查询（仅在协议支持时）、明确的副作用状态，不允许把图片丢掉只返回文本。

即使 HumanCLAW 任务选择 exported skill protocol，**generic EFE RCB1 binding 仍是本次 harness 接入的一部分**，并用一个已有 EFE standard task 验证它。这样交付的 harness 才能运行 EFE 的其他任务。

### B3. 保留 adaptive 行为和执行边界

- 保留 discovery、schema/参数校验、proposal/reviewer、程序/工具执行、context/memory、repair 和 trace；不能绕过这些组件后只证明 Pi 能发一次 HTTP。
- Broker 的 durable intent / receipt 与不确定状态要保留。物理动作可能已发生但响应丢失时，优先 reconcile；不支持查询就报告 uncertain 并停止该动作流程，不能自动补发第二次。
- 原动态程序执行在 macOS 使用 sandbox-exec、Linux 使用 bubblewrap。Docker 内的 user namespace / bubblewrap 可用性要实际测试；不能通过 `--privileged`、宿主 socket 或直接去掉隔离来让测试变绿。
- 每个 Harbor trial 使用独立 workspace、session、数据库、预算和记忆；不同 task 不共享答案或自生成程序状态。
- instruction 必须完整传入，不删改 task 限制；可添加公开工具说明，但不得加入私有 evaluator 状态或 oracle。
- 模型 provider、model ID、endpoint、reasoning 配置按运行配置声明。现有 adaptive 路径有 Responses API 假设，不自动等于兼容任意 Claude/OpenAI transport。
- 统计实际主 agent 与额外 reviewer / repair 调用的 usage，不能只报主循环 token；缺失 usage 保留 unknown，不填 0。
- 捕获 wall-clock timeout、进程取消、provider 错误和工具错误；清理整个 agent 进程组，flush broker/trace。harness 自己报告的成功不能改变 verifier reward。

### B4. 官方 EFE 运行与实验 harness 的关系

当前 EFE `AGENTS.md` / `docs/protocol/running.md` 的正式运行规则限定 Harbor 原生 agents，禁止自定义 adapter 和改变请求/持有凭据的模型 gateway；`scripts/run_agent_batch.sh` 当前只接 codex / claude-code。

因此必须交付两个清楚的入口：

1. 遵守当前正式规则的 native-agent task 验证入口。
2. 能实际运行我们 harness 的独立 experimental Harbor profile，记录它与正式规则的差异。

**“暂不符合官方运行规则”不等于可以不做 harness 接入。** 保留完整实现、运行证据和扩展提案；能否纳入正式成绩由维护者批准，或通过适当的 Harbor native integration 解决。不能悄悄改官方 batch whitelist、挪用官方标签，也不能把本地模型代理或远程工具调用当成已获例外。

依据：[EFE official runs](https://github.com/mll-lab-nu/embodied-first-exam/blob/49395ed94f2be39fbe254ac881e2dcb1b5eb2320/docs/protocol/running.md)。

## 9. 实施顺序与每步完成条件

| 阶段 | 实施内容 | 可核查的产物 |
| --- | --- | --- |
| M0 来源与协议 | 获取完整 snapshot，读当前 EFE 规则，确认 proposal、资产和实施基线 | source hash、接口差异表、依赖/资产清单 |
| M1 原环境基线 | 建 Linux GPU 运行环境，跑原 smoke 和冻结动作/episode | 环境版本、GPU 记录、真实轨迹/指标 |
| M2 Session / protocol | 提取不含 planner 的 session，实现公共接口及隔离 | schema、CPU 状态机测试、原实现与 adapter 的 GPU 对照 |
| M3 Harbor tasks | nav + interaction 任务、sim/verifier、oracle、nop、注册/normalize | 可由 Harbor 启动的任务与可信评分证据 |
| M4 Harness 接线 | Installed agent、HumanCLAW binding、RCB1 binding、adaptive 生命周期 | native baseline + adaptive + discovery 的实际 trial |
| M5 联合验收 | 同任务/seed/预算对照，一个已有 EFE task，错误/超时/泄漏检查 | 验收表、命令、trial IDs、artifact 清单、CI 结果 |
| M6 交付审查 | 文档、资产镜像与构建说明、PR 拆分、限制说明 | coauthor 能复现且 reviewer 能追到代码和证据 |

M3 后任务尚未完成；M4、M5 是必做部分。缺 GPU 或资产时继续完成 CPU、协议、打包和检查工作，同时列出具体缺项。没有真实 GPU / Harbor 证据的项目标记 blocked / not run，不得宣称通过。

## 10. 验证命令与预期结果

以下第一组是已有源码入口；后续 task 与 agent 名称是待实现目标，必须在完成时替换成真实路径并实际执行。安装遵循各子项目锁文件，不把 host、agent 和 sim 的依赖混装。

### 10.1 原环境与迁移回归

从 `H` 运行，输出使用新的独立目录：

~~~bash
PYTHONPATH=src python tests/runtime_hp_contract.py
PYTHONPATH=src python tests/runtime_habitat_smoke.py --output /tmp/humanclaw-efe-habitat-smoke
PYTHONPATH=src python tests/runtime_forward_replay.py /absolute/path/to/saved-rollout --max-steps 0
python -m pytest -q -ra
npm --prefix harnesses/pi-adaptive run check
npm --prefix harnesses/pi-adaptive test
~~~

runtime_habitat_smoke 需要真实 patched Habitat、准备好的场景和视频依赖，但不等于完整 motion-model rollout。还需验证 motion weights 加载、真实动作推进与完整 episode。replay 检查需要先生成实际 rollout。

已有迁移验证记录为 586 个 Python tests 通过、4 skipped，10 个 TypeScript tests 通过、类型检查和 CLI 启动通过。skip 涉及可选 RoboRSI、ffmpeg、需要显式配置的真实 Codex/Pi 测试。这些结果证明源码回归情况，**不证明新 Harbor 接入已成功**；此前导入验证没有运行真实 GPU Harbor trial。

### 10.2 EFE 任务检查

在 EFE 根目录，先把变量替换成实际已实现的任务目录：

~~~bash
TASK_DIR='tasks/humanclaw/<actual-task-name>-standard'
python3 scripts/task_conventions.py "$TASK_DIR"
python3 scripts/task_conventions.py --check "$TASK_DIR"
python3 ci_checks/check-resources.py "$TASK_DIR"
python3 ci_checks/check-cutoffs.py "$TASK_DIR"
python3 ci_checks/check-seeds.py "$TASK_DIR"
python3 ci_checks/check-twins.py "$TASK_DIR"
bash ci_checks/run_invariants.sh "$TASK_DIR"
bash ci_checks/run_all.sh "$TASK_DIR"
~~~

`<actual-task-name>` 是说明用占位符，使用前需替换；不要把整段未替换的内容粘到 shell。文件完成修改后重新 normalize，确保 DIGEST 对应最终内容。对新 task 使用 `python3 scripts/stamp_mtimes.py "$TASK_DIR"` 按仓库规则处理时间戳。提交后的差异检查使用 `bash ci_checks/run_all.sh --changed`，核对 scope 确实覆盖新 benchmark / harness 共享改动。

检查在满足 EFE 要求的 Linux 工具环境执行；macOS 自带旧 Bash 或缺 GNU 工具导致的检查未完成不能记为通过。

### 10.3 Harbor 真实 trial

以下是接口目标；选择已配置的模型、独立输出目录与明确预算，完成时给出展开后的实际命令及有效 config：

~~~bash
harbor run -p "$TASK_DIR" -a oracle
harbor run -p "$TASK_DIR" -a nop
harbor run -p "$TASK_DIR" -a codex -m "$MODEL"
harbor run -p "$TASK_DIR" -a humanclaw_efe.agent:HumanClawAdaptiveAgent -m "$MODEL"
~~~

`MODEL` 由 coauthor 按可用 provider 配置，不在文档中写密钥；bootstrap/discovery 运行的额外 agent kwargs 按实际实现列出。正式成绩使用 EFE 官方 runner 及其网络、usage、seed 配置；上述简短命令用于单任务接通和测试，不能据此自动声称符合正式运行条件。

Harbor 0.23.0 支持 `-a module.path:ClassName`，前提是模块对 Harbor host 可导入。依据：[固定版本 CLI](https://github.com/harbor-framework/harbor/blob/v0.23.0/src/harbor/cli/jobs.py)。

Oracle 应以公共动作接口操作，证明所选实例可解；不要直接写 reward 或私有终态。Nop 在特意选定的非平凡实例上应失败。对已提供真实 oracle 的任务至少验证固定 seed 的重复运行，记录结果；不能凭模板就声明 oracle 可用。

## 11. 最终验收清单

| 必须验收的事项 | 通过证据 |
| --- | --- |
| 完整来源 | 固定 source tree hash；没有再漏掉 HumanCLAW 环境、motion、资源和 harness |
| 环境可重建 | 镜像 digest、资产 revision/hash、构建说明、驱动与运行依赖记录 |
| 实例覆盖明确 | task 清单、冻结 seed/目标/初态、canonical episode 映射、准确的覆盖数 |
| 无隐含第二个 agent | sim 仅执行动作/物理/指标，EFE agent 实际决定每步 |
| 物理与原语义一致 | 固定动作序列下原 evaluator 与 adapter 对照；Stop、Sit、距离和 contact 边界测试 |
| Task 可独立运行 | 不安装 adaptive harness 也能由 native Codex 通过公共接口产生真实轨迹 |
| 奖励可信 | oracle/nop 对照，agent 伪造 metrics 无效，错误与未终止情况正确分类 |
| 隔离与截止有效 | 无隐藏状态泄漏；cutoff 后动作被拒绝；trusted files 不可写；资源检查有效 |
| Harness 真正接入 | adaptive 显式 binding 与 bootstrap 均有实际运行记录；未用 stub/直接 callback 绕过公开接口 |
| 通用 EFE 接口 | 在一个已有 standard task 上通过 RCB1 获取图像并执行合法动作，完成可评分 trial |
| 生命周期可靠 | timeout / cancel / uncertain request / repair 失败测试；不重复物理动作；trial 之间状态隔离 |
| 轨迹和视频完整 | live verdict、可信轨迹、可播放录像、video_source、终态与错误记录 |
| 结果身份准确 | native/experimental、原 HumanCLAW/EFE variant、live/replay、完整集/子集清楚区分 |
| 自动检查 | normalizer 幂等、DIGEST 一致、invariants 通过；advisory 警告逐项解释 |
| 双方可接手 | 一份从空机器准备到单 task、批量评测、日志定位的实测指南 |

任务成功率不要求 100%。要求的是：可解性由 oracle 证明、失败准确反映环境状态、agent 的成功或失败都能留下可信的完整证据，且两条接入链路真实可用。

## 12. 最终给 coauthor / reviewer 的交付包

提交代码时附一页状态说明和可复现细节：

- **做成了什么**：任务数量与类型，公开协议选择，已接通的 harness profiles，是否有官方运行资格。
- **代码入口**：session、server/client、grader、Harbor agent class、binding、task 示例和主要测试的位置。
- **如何重跑**：获取代码、构建/拉取镜像、准备资产、安装 agent、oracle/nop/native/adaptive/discovery 命令；说明 host 与容器分别执行哪一步。
- **如何核对结果**：trial ID、实际命令与 config、commit/image/asset hashes、seed/预算、reward、错误、token/cost、轨迹/视频位置。
- **哪些没验证**：明确未运行、失败和外部阻塞；没有 GPU/资产/模型权限时写出需要谁提供什么，不把它们计入完成项。
- **如何审查合并**：task PR 与 harness/共享支持 PR 的依赖，现有 PR #490 与新增变更的关系，协议差异及维护者批准状态。

大权重、场景资产、视频、大量 rollout 和训练/分析输出放在指定服务器或 artifact storage；Git 只放运行必需的代码、配置、任务定义、必要小型证据和文档。原 private repo 保持不变。

### 给执行 agent 的最终指令

按本 handoff 实现 **HumanCLAW Harbor tasks + EFE harness 接入** 两项工作。先核对真实代码与当前协议，再复用已有组件完成最小真实链路，然后扩展、测试并交付。所有“已支持/已通过”的结论都提供对应命令和证据。遇到限制时说明并继续不受阻的工作，不以复制源码、通用方案、mock reward 或只完成其中一项结束任务。
