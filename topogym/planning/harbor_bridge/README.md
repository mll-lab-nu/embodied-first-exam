# Harbor oracle bridge

共享入口是 `scripts/oracle_runners/harbor_oracle.py`，使用仓库的 Python 3.11+ 环境。
本模块负责冻结身份、动作转换、私有依赖打包和 Harbor oracle/nop 批量执行。
策略、IK、场景和原生成功判据仍由原任务提供；执行使用任务包原有的 `Session.step`。
oracle 运行代码随 `solution/` 上传，不进入公共 simulator / verifier 镜像。

当前已接入 11 类 easy / medium / hard 的私有算法回调和参考数据，33 项打包检查通过。
Coil easy 已实测完成 3 步 oracle 前缀的 privileged 两遍回放，以及 standard 服务执行和独立进程回放；
两模式均有录像、基础设施错误为 0、实际 grade 为 0。其余任务仍待逐项实机验证。
短程接线通过不构成完整可解性证明。
原任务包、原 oracle runner、既有证据和成功资格均保留。

当前实测范围按用户要求仅为 **easy / medium / hard**，不运行 very_easy / easier。
盘点与执行都可加 `--tiers easy medium hard`；执行入口会拒绝范围外任务，避免名称后缀误匹配。
简化档已有产物保留，但不纳入本轮三档验收。

## 支持的输入

| `--kind` | 输入 | privileged | standard |
| --- | --- | --- | --- |
| `existing` | 原 `solve.sh` 中 `run-oracle --code` 指向的脚本及私有依赖 | 支持 | 不支持 |
| `session` | `topogym.planning.*` 内的 `callback(session, output, **kwargs)` | 支持 | 不支持 |
| `public_trajectory` | 同一冻结实例声明的公开关节/夹爪布局轨迹 | 支持 | 通过原 HTTP client 提交 |
| `native_trajectory` | 同一冻结实例的原生关节/夹爪目标 | 逐行预检转换后执行 | 不支持 |

现有创建 Env、reset 或自行录制的独立 runner 不能直接作为 `existing` 输入。
这种 runner 应提取接收外部 Session 的薄回调，保留原策略及原 CLI 默认行为。
公共 `SessionExecutor.step(action, mode=...)` 复用现有动作编译器，支持显式控制模式；
`step_public(row)` 可提交公开布局。两者都不拥有场景或 recorder 的生命周期。

`session` 依赖收集会遍历 Python 静态导入及包初始化文件；动态导入和数据文件用
`--include topogym/planning/<相对文件>` 显式补齐。仅允许私有 planning 依赖，
不打包 `scripts`、`legacy`、`calibration_tools`、`deferred`，也不覆盖公共物理模块。
第三方运行库仍须由已有镜像提供；打包检查不代表这些库已在镜像中实际导入成功。

## 身份及执行约束

- 精确绑定完整 `instance.json`、源码身份、资产身份、`instance_assets/` 文件哈希及 task tooling。
  缺少身份信息的旧包会报告 `blocked_identity`；先从正确版本生成新冻结包，不能补写虚构身份。
- `instance.topogym_source` 只说明实例生成来源。独立的 `runtime_binding.json` 记录实际镜像 ID、
  镜像中的源码文件重算哈希、Python/物理依赖版本和 UIPC 构建身份，允许旧实例经新运行环境精确恢复。
  这不自动证明语义兼容或可解性。源码、工具、实例和状态资产任一错配均在执行前拒绝。
- 参考来源与目标包的 seed、场景、判据、机器人、物理时序及辅助抓持必须一致。
  soft-state 相对路径只允许按现有 tooling 解析到同一份绑定资产。
- 不自动重排、重采样动作或改变夹爪目标。新候选由冻结实例声明 `gripper_space=native`，
  夹爪列为 `<arm>_native_gripper`，保留 ALOHA 的驱动位置（m）及 Robotiq 的驱动角度（rad）；
  privileged、standard 和 grader 使用相同布局。原宽度实例及 Knot 保留 `gripper_space=width`。
  原生目标往返误差须不超过 1e-6（对应 m 或 rad），关节误差须不超过 1e-6 rad；
  只允许 float32 在模型限位处向内舍入。旧宽度布局无法表达的目标仍拒绝，不饱和代替。
- 每行执行一个原控制周期。只接受最后一行因 Task 结束而缩短的 tick 记录；
  不把任意 `_physics_steps` 覆盖传给 Session。轨迹结束不追加保持或静置动作。
- wrapper 统一开始/结束轨迹记录；回调不能 reset、rewind、替换配置或 recorder。
  结束时核对 Session 记录、Env 控制计数和物理 tick，发现绕过 Session 推进时失败。
- 脚本异常、仅策略完成、原生 Task 未成功均返回失败；尽可能保留部分轨迹与失败报告。
  原生成功报告为 `native_success_pending_harbor_verifier`，仍须独立 verifier 通过。
- standard 模式只使用公开 HTTP。断连后按服务确认的控制步前缀续传，不重复已确认动作；
  HTTP spec 提供不泄露状态的 `instance_binding_id`。agent 核对该 ID，verifier 独立核对服务启动和
  fresh-process replay 两份绑定记录，且两者均必须 `instance_exact=true`。

公开 NPZ 必须包含 `actions`（可精确表示为 float32 的二维数组）、`action_layout`、
`task`、`instance_sha`（对应冻结 `state_sha`）和 `scene_seed`，可附带
`physics_steps_per_action`。原生 NPZ 使用 `targets`、`layout`、可选 `physics_steps`；
夹爪列必须显式命名为 `<arm>_native_gripper`。两种轨迹都必须另传 `--source-instance`，
不根据数组形状推断来源或控制语义。

## 连接到评测语义及验收标准

直接 `Env` 的历史成功只作为参考来源。实际接入必须由冻结 task tooling 创建 `Session`，
在该 Session 安装安全规则、力矩限制、桌面保护、PBD 接触修复及不稳定检测后，
让原策略读取此 Session 的环境反馈，并且只经其 `step()` 推进。不能在旁边新建 Env 执行。
`SessionPolicyRunner` 遇到 Session 的成功/失败终止立即停止请求动作。

privileged bridge 的 `bridge_report.json.evaluation` 记录运行前后的规则参数、
PBD 修复参数、粒子速度 guard 和整段 safety 摘要，以及请求/实际执行动作的 float32 哈希、
调整行数、逐关节最大差和前八个调整样本。Session 的桌面保护允许按评测规则修改目标，
bridge 保留该行为并明确报告，不能把它称为与旧 Env 逐动作等效。
规则对象替换、规则参数修改、绕过受观测的 Session.step 会使候选失败。
这些记录来自 agent 进程，是诊断证据；最终资格仍由隔离 verifier 判定。

“连接正确”与“效力保留”分别验收：前者检查身份、动作语义、生命周期及规则路径；
后者要求每个 easy / medium / hard 冻结实例在当前规则下完整成功，再通过其模式原有的
独立回放（privileged 两遍；standard live + fresh-process replay）、oracle/nop 和视觉验收。
只有前者通过时不能报告后者通过，也不能靠放宽安全规则或修改成功判据恢复历史成功标签。
如需调整策略来遵守当前规则，应另存 oracle 版本并重新验收。

## 使用

从仓库根目录执行。所有候选输出为 `<output>/<原任务目录名>`；已有目录不覆盖。
实例及状态资产保留原字节；支持绑定的候选 tooling 会在 `environment/`、`tests/` 增加同一运行绑定。
其文件和 Dockerfile COPY 改动逐项记入 `binding_additions`；不会改写来源任务包。
候选包始终标记 `oracle = "none"`、`harbor_qualified = false`，不继承来源的 full 资格。

### 逐项实机 grade 交接（easy–hard）

入口：[run_harbor_oracle_grades.sh](../../../bash_scripts/run_harbor_oracle_grades.sh)。
默认范围为 Coil、Keyhole、Lock Picking、Buzz Wire、Fiber、Horseshoe、Hedgehog、Claws、
Blanket、Rope、Knot 的 easy / medium / hard，共 33 个实例、最多 66 个模式结果。
排除 Orbits、Slotted Post Ring、very_easy、easier。它执行完整 oracle，不带 nop 负对照，
不激活发布版本。完整执行可能耗时很长；`--wall-seconds` 是每个实例双模式的总时限，
不是整个 33 项队列的一小时时限。

接收方需要完整 Git checkout、Python 3.12 管理环境、Docker daemon、NVIDIA Container Toolkit
及可用 CUDA/Nyx GPU。三档 Harbor 回调的参考输入随 `topogym/planning/` 交付，
无需复制原机器的 `runs/` 或 `solvability_proof/*/*/evidence/`。
首次执行从独立源码快照构建候选镜像，再生成双模式任务；默认镜像标签为
`ghcr.io/luigivamper/rcb-topogym:<images/topogym/VERSION>-cu128`（v16：`0.2.14-dev-cu128`），本地构建不会 push 镜像。
恢复已绑定队列时不重新构建镜像，镜像 ID 和源码身份仍须匹配。
不要在队列运行时修改其源码、镜像标签或任务包；其他运行若使用同一开发镜像标签，
应先协调构建时间，或显式准备独立镜像与候选任务后传 `--tasks-root`。

新机器从仓库根目录准备管理环境（需要已有 `uv`）：

```bash
uv venv --python 3.12 .venv-harbor
uv pip install --python .venv-harbor/bin/python --require-hashes \
  -r requirements/difficulty-eval-controller.lock
export TOPOGYM_PYTHON="$PWD/.venv-harbor/bin/python"
export TOPOGYM_HARBOR="$PWD/.venv-harbor/bin/harbor"
"$TOPOGYM_PYTHON" ci_checks/check-oracle-portability.py --check-git
```

该环境负责准备输入和调度，正式物理依赖由镜像的 runtime lock 安装。
已有管理环境可通过上面两个环境变量指定，不要求沿用作者的虚拟环境目录名。
`--check-git` 检查三档参考输入及私有 Python 依赖是否收录；发送前须把新增的
`reference_data/`、检查脚本及代码修改一起提交。仅 push 旧提交不会带上未提交文件。
文件检查通过只表示交付依赖齐全，不表示 Task 成功或完整 Harbor 评分通过。

Blanket 的冻结初态还有硬件约束：当前三档 `tasks/.../instance_assets/initial_state/manifest.json`
绑定 `cuda_sm120_mp188_87407517a32a`，来源为 RTX PRO 6000 Blackwell Max-Q，
Genesis 1.2.1、torch 2.11.0+cu128、numpy 2.3.5、quadrants 1.0.2。
候选准备会保留这些初态字节（v16 只为覆盖率阈值 0.95 改写副本的身份记录，arrays 字节不变）；4090（sm89/mp128）不能直接恢复它们。
接收机器须匹配完整兼容性清单；使用其他硬件时，经 `scripts/prepare_blanket_initial_states.py`
准备对应 profile 的初态，再生成并验收新的冻结实例。更换初态属于新实例，不能继承旧分数或改写兼容性哈希。

当前 active 为 v16，`tasks_root=null`；仓库 `tasks/` 中的 78 个原三档包仍为 v14。
因此新机器使用下面的构建入口生成候选，或显式传入同源码生成的活动版本 `--tasks-root`。
直接运行默认 `test_harbor_oracles.py` 会因活动任务树未冻结而 blocked，这是版本保护。

先查看队列（不启动 Docker）：

```bash
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output runs/test_results/harbor_grade_handoff_new --plan
```

先生成 Coil easy 候选并跑完整评分（输出目录必须不存在）：

```bash
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output runs/test_results/harbor_grade_coil_easy_new \
  --families cast_coil --tiers easy
```

若交接者只想再次确认接线，在上述命令末尾加 `--smoke-steps 3 --wall-seconds 600`，
同时换一个全新输出目录。短程 `smoke_passed` 允许实际 grade 为 0，不能当作 grade 1。

运行全部 33 项完整评分（自动准备独立候选，逐家族构建并逐实例评分）：

```bash
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output runs/test_results/harbor_grade_all_new
```

也可选择 `--families cast_keyhole,lock_picking --tiers easy`。生成阶段默认等待 GPU 空闲
且至少有 12000 MiB 可用，最长等 600 秒；可用 `--gpu-wait-seconds 3600` 延长等待。
`--gpu` 选择生成时设备，Harbor 执行设备仍由任务 compose 配置决定（本机单卡）。
镜像构建日志和资源监控在 `image-build-*/`；任务构建日志为 `build-<family>-*.log`。
已绑定镜像不匹配时应准备新的队列，保留旧运行证据；不会静默使用旧发布包。

中断后使用完全相同的命令加 `--resume`：已完成的结果保留，包括失败结果；
未完成项写入新的 attempt 目录。重测已完成的失败项，指定对应 family/tier 和新的输出目录。
构建阶段的完成回执也可复用。脚本对自身队列加锁；资源监控在系统内存达到 90% 时
停止本轮拥有的 worker，CPU 只记录。不要用 `kill -9` 跳过 Harbor 的清理。

查看 `<output>/summary.tsv` 或 `summary.json`；逐项的 `results` 列指向详细 `results.json`，
其 `runs` 给出原生 Harbor job、`reward.json`、轨迹及 verifier 录像的位置。
每个 attempt 旁的 `.dispatch.log` 是调度日志，构建日志为 `build-<family>-*.log`。
退出码 0 表示所选范围全部通过；非 0 时根据汇总区分任务 grade 0、未运行、绑定失败和基础设施错误。
正式模式仅在 privileged 获得 grade 1 后，将同实例轨迹交给 standard 服务执行；否则 standard
为 `blocked_dependency`。这与 standard 实际执行后得到 grade 0 不同。单项失败不会跳过其他家族。

本轮接线证据：`runs/test_results/oracle_harbor_connectivity_20261003_01/static_matrix/results.json`
（33 项私有打包检查）及 `trials_02/cast_coil/results.json`（相对同一证据根目录；双模式实机短程评分）。
其余 10 类的实机接线和所有任务的完整 grade 1 均留待本脚本验证。

### 交付审计结果（2026-10-04）

证据根目录为 `runs/test_results/oracle_portability_20261004/`，它是本机检查产物，
接收方运行不依赖这个目录。检查使用独立源码副本；公共物理源码仍有其他会话并行修改，
对应文件身份见 `effective_checkout_manifest03.json`，不能将结果外推到未经检查的新修改。

| 范围 | 定位与处理 |
| --- | --- |
| Fiber、Claws、Horseshoe | 默认参考曾指向被 Git 忽略的证明 evidence；现将必需文件复制到私有 `reference_data/` 并校验原始哈希 |
| Hedgehog easy/hard | 同样缺 pickup 文件，且打包遗漏 `reference_routes.json`；两项均补齐，medium 不需要 pickup 文件 |
| Buzz medium 分阶段入口 | `stages.py` 曾读取被 Git 忽略的 `runs/.../medium_traverse_guide.json`，且未登记在默认依赖中；现将原字节、SHA-256 和阶段模块一并纳入私有资源打包及搬迁读取回归 |
| Keyhole、Buzz、Lock | Session worker 曾无条件导入镜像裁剪的 SegmentRunner／记录哈希模块；现在仅独立本地 runner 加载 SegmentRunner，记录哈希算法保持一致 |
| Fiber、Horseshoe 共享 stages | `planning/solvability.py` 的记录哈希也依赖裁剪模块，隔离容器复现后已替换为同一私有哈希函数 |
| Rope | 补齐 `hard_plans.json`；机器人资产按安装目录解析，保留原文档文件哈希，不再查找 `/solution/assets/` |
| Coil、Blanket、Knot | 默认回调无额外本机 oracle JSON 依赖；仍需对应的冻结实例、完整物理执行与 verifier |
| 新机器入口 | 首次评分实际执行镜像构建；生成命令沿用调用者 Python；提交检查检测遗漏文件及尚未暂存的私有依赖修改 |
| Orbits、Slotted Post Ring | 尚无完整机器人 oracle，不在默认 33 项队列中 |
| very_easy/easier、旧无分档包与 Cube 示例 | 未迁入当前三档 v15 oracle 流程；当前目录中的历史版本不能绕过活动版本身份检查 |

Buzz medium 的补充检查执行了搬迁后的 `solution/` 中实际阶段参数的引导读取，
并验证删除／篡改文件会报错；原检查仅遍历已登记依赖，无法发现未登记的运行时文件。
引导原文件为 284,534 字节，SHA-256 为
`4511df68f53ded79077a12998ddfe76f1cbf65f6ac552b412fbdefa4bf16cd0f`。
后续核对 lab 调用栈确认实际失败来自默认通用 planner，而非缺文件异常。
默认 `public_session` 现已改选完整 oracle：easy 使用 11 段反馈 selection；medium/hard
使用已审计的完整动作序列（29,544／43,568 行），含终点转正与释放。
缺少输入或 seed／布局／初始姿态／控制周期不匹配时，在动作前失败，不回退到通用 planner。
对方若显式走历史 medium 分阶段入口，旧 selection 路径仍须按 [参考输入说明](reference_data/README.md) 更新。
提交 Python、资源和 manifest 后，接收方须重新打包，并用新的输出目录重试；
旧候选 `solution/` 和 `--resume` 队列不会自动获得新文件。
这是资源交付和策略选择修复；本机 NVIDIA 驱动不可用，没有运行完整 GPU grading，也不代表 Horseshoe 动作、Rope 稳定阈值
或 Blanket 末态抖动已解决。

已完成的检查：

- `packages03/`：11 个家族 × 3 个难度，共 33 个私有候选完成文件打包及完整性检查。
  为隔离检查使用 v14 包作公共文件载体，没有执行这些旧包或伪造 v15 runtime binding。
- `container_imports03/summary.json`：33/33 在无网络、只读容器中通过私有模块与参考数据读取。
  使用已有运行镜像的第三方依赖、按正式规则裁剪的候选公共源码及每项独立 `solution/`；
  不挂载原 `runs/`／proof evidence，不启用 GPU，也不创建物理场景。
- `controller_bootstrap/`：105 个管理依赖全部匹配 controller lock；无 Genesis 的容器成功生成
  39 组候选输入，尚未执行 make-instance 或镜像构建。
- `checks03.json`：124 项 CPU 回归及源码隔离静态检查通过。
- `default_release_plan/results.json`：当前默认套件 78 项明确 blocked，原因为活动 v15 任务树尚未冻结，
  不是 78 项实际执行得零分。采用上方候选构建入口后方可进行真实评分。

以上结果不新增任何完整物理成功或 grade 1。截图的 Keyhole/Buzz “BUG 1”未提供完整堆栈，
本次确认的是上述可独立复现的裁剪依赖错误，不能据此断言两者是同一个缺陷。
IDE 中的 `oracle_v12_replay_20261003_easy_retry01` 则是 Knot 的 CUDA 内存分配失败：
`native_replay.log` 报 `cudaErrorMemoryAllocation`，容器退出 139、无最终 replay 报告，
最后进度为 100 controls / 1000 physics ticks；这属于运行时失败，不能当作正常 grade 0。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py inventory

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py inventory --tiers easy medium hard

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py compare \
  --reference-instance <参考-instance.json> --target-instance <目标-instance.json>

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py bind \
  --task <选定的候选任务目录> --output runs/test_results/runtime_bindings_new

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py preflight \
  --task <选定的候选任务目录> --runtime-lock <该任务的绑定JSON> \
  --output runs/test_results/exact_restore_new --gpu 0 --execute

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py package \
  --task <同一实例的standard候选目录> --runtime-lock <该任务的绑定JSON> \
  --output runs/test_results/oracle_standard_new --kind public_trajectory \
  --source-instance <该实例的privileged目录>/environment/instance.json \
  --trajectory <同一实例已验收的-trajectory.npz>

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py check \
  --task <生成的私有oracle候选目录>

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py run \
  --task <已绑定参考的原三档候选目录> \
  --tiers easy medium hard \
  --output runs/test_results/oracle_jobs_new
```

`bind` 与其他新实验入口仅接受活动版本；CLI 会拒绝 `--release published` 和旧 tooling。
活动版本未生成任务树、目标镜像缺失、镜像 tag 移动或任一输入不完整都会失败，不退回旧镜像。
`preflight` 不加 `--execute` 只保存命令；执行仅加载精确初态，不运行 oracle，也不授予成功资格。
管理方底层绑定工具可检查历史 v14，但不构成活动版本实验；正式双模式绑定评分需要候选 tooling，
原 v14 标准服务没有绑定回执接口，不能通过偷偷替换旧服务实现来声称它已支持。

`run` 默认只输出完整 Harbor 命令，不创建 job；加 `--execute` 顺序运行 oracle/nop，
无需模型或模型凭证。宿主需要可用 Docker、匹配镜像和 NVIDIA GPU。
受限沙箱中的 `nvidia-smi` 失败或 Docker socket 不可访问，不能据此判断宿主 GPU/驱动不可用；
应在有宿主设备和 Docker 权限的执行环境复核。实际作业还需留出足够显存，保留其他会话的运行。
复用 `process_limits.run_guarded` 监控 CPU/内存，在系统内存达到 90% 时停止本轮 worker；
保存 `plan.json`、`results.json`、各 job 日志及资源记录，非预期评分或基础设施错误即停止队列。
退出成功只表示本批评分符合预期；两种模式的 oracle=1、nop=0、独立回放、视觉证据和隔离检查
仍须一起审查后才能授予资格。此入口不修改现有 `difficulty_eval.py` 的模型评测流程。

## Oracle 的双模式回归入口

`scripts/oracle_runners/test_harbor_oracles.py` 逐任务验收正式 Harbor 流程。
默认选择 easy / medium / hard、privileged / standard，并执行 oracle 与 nop；
`--families`、`--tiers`、`--modes` 可以缩小范围。每个任务的接入缺口也进入报告，
不会将没有 oracle、缺失 twin 或旧版本任务跳过后报告全通过。

```bash
# 只生成全量覆盖清单与计划；活动版本没有任务树时，旧包仅用于列举缺口。
.venv-gs121-nyx/bin/python scripts/oracle_runners/test_harbor_oracles.py \
  --output runs/test_results/harbor_oracle_inventory_new

# 活动版本逐任务执行；输出目录必须全新。
.venv-gs121-nyx/bin/python scripts/oracle_runners/test_harbor_oracles.py \
  --output runs/test_results/harbor_oracle_regression_new --execute

# 单实例候选冒烟：使用当前活动版本的真实生成包，不要求先激活全量 78 包。
.venv-gs121-nyx/bin/python scripts/oracle_runners/test_harbor_oracles.py \
  --tasks-root <候选目录>/tasks --candidate --families cast_coil --tiers easy \
  --output runs/test_results/harbor_oracle_coil_new --execute
```

`--candidate` 仅允许当前源码、tooling、镜像和冻结输入匹配的候选包，仍使用原生 Harbor
容器隔离与正式 grader；它不激活 release，也不授予全量环境资格。
默认路径仍要求已登记的活动任务。执行前后均核对绑定及包完整性，禁用 Harbor 自动重试。
系统内存达到 90% 时停止本轮 worker；基础设施或评分证据异常停止后续队列，
正常 grade 0 则记录为 oracle 回归失败并继续其他任务。

入口复用现有 bridge 的私有打包与回调。已有 bridge 包直接运行；本轮 11 类任务
自动选择已登记的 Session 回调及私有参考数据；生成器原有 `run-oracle --code` 脚本也可直接打包。
standard 默认取同名 privileged 在本批次得到 grade 1 的轨迹，经公共 HTTP 服务实际执行。
实例不匹配、privileged 未成功或尚无适配的独立 Env runner 均明确报告 blocked。
其他 oracle 用 `--references references.json` 指定 `package()` 输入，键为完整任务目录名，例如：

```json
{
  "topogym-horseshoe-ring-easy-i00-privileged": {
    "kind": "public_trajectory",
    "trajectory": "/absolute/path/reference.npz",
    "source_instance": "/absolute/path/instance.json"
  }
}
```

引用轨迹必须满足上述冻结身份与动作布局合同；本地 demo 成功标签不能代替这些检查。
只运行 standard 时须提供它的显式参考轨迹或已有 bridge 包。`--no-nop` 可省略负对照。

`results.json` 保存每项 grade、状态、命令和原生证据路径；`jobs/` 保留 Harbor 全部产物，
`supervision/` 保存日志与 CPU/内存记录。验收同时读取 Harbor result、verifier reward 和可信侧证据：

- privileged：至少两次回放逐次成功，完整 runtime binding、精确初态及提交轨迹哈希一致。
- standard：live 与 fresh-process replay 均成功，服务启动/回放的绑定回执一致，并保存服务端执行历史。
- reward 不一致、未结束 trial、grader/infra 错误不能成为通过或正常负对照。

GPU 末态 `deterministic=0` 和视频状态单独报告，沿用正式 grader 语义，不额外改变 grade 规则。
`grade_one_count` 只计证据核验通过的 oracle；`all_passed` 还要求所有选中任务及启用的 nop 通过。
此报告是评分回归结果，`harbor_qualified` 保持 false，媒体与 release 资格仍按原流程审查。
CPU 回归：`python ci_checks/test-harbor-oracle-suite.py`，使用合成证据，不代表物理成功。

修复前的 Cast Coil easy / seed 0 候选诊断使用当时匹配的 tooling 15 / `0.2.13-dev-cu128`：
privileged oracle 执行 371 行后，原策略 `close_and_acquire` 的原生夹爪目标 `.002 m`
不能无损转换成公共开口宽度，bridge 拒绝继续。独立 grader 重放两遍均未成功，grade 0；
精确初态、运行绑定正常，grader/infra error 均为 0。随后显式把这条 **未完成轨迹** 提交到
同实例 standard 服务，live 371 行与 fresh-process replay 均未成功、grade 0；两个模式 nop 均为 0。
因此已运行两条完整评分通道，但没有新的 grade-1 可解性证明，也没有修改原策略或放宽规则。
原批次的 standard 自动依赖仍标记 blocked；未完成轨迹诊断另存一批，不能混同为成功 oracle。
证据见 [privileged 批次](../../../runs/test_results/harbor_oracle_suite_20261003_coil_easy/results.json)、
[privileged 逐次回放核验](../../../runs/test_results/harbor_oracle_suite_20261003_coil_easy/privileged_evidence_recheck.json)
及 [standard 未完成轨迹诊断](../../../runs/test_results/harbor_oracle_suite_20261003_coil_standard_prefix/results.json)。
构建/初态预检的 Docker 命令已补齐 `--runtime nvidia`；仅 `--gpus` 在本机不会注入 Vulkan ICD，
会导致 Nyx 建场景失败。Harbor Compose 原有 NVIDIA runtime 声明保持有效。

## 逐任务接入状态与剩余验证

下表是当前冻结实例的接入路线，不推断新 seed 的可解性。运行 `inventory` 获取当前任务包列表；
runner 文件存在不代表已有完整成功证据。任何物理/几何版本差异都需要另建对应版本的新 task 包。

| 任务 | 当前接入重点 |
| --- | --- |
| Cast Keyhole | 原三档 orchestration 已迁入私有 runner 并注入 Session；F1/F2/F3 数据随包；待实机验证 |
| Lock Picking | 原三档 reindex 求解流程已接 Session 和原生目标；待实机核对 Task success |
| Cast Coil | easy 双模式 3 步接线与 grading 实测通过；三档完整 grade 1 待验证 |
| Fiber Bundling | 包初始化、既有 stages 和三档 selection 已接入；候选显式保留 sheath assistance；待实机验证 |
| Buzz Wire | 默认选择 easy 完整 11 段反馈配方及 medium/hard 完整编译动作；保留冻结物理，完整 GPU grading 待 lab 验证 |
| Hedgehog | 反馈回调及 easy/hard 已选 pickup 数据已接入；待核验当前模型与实机执行 |
| Interlocked Claws | 既有机器人策略、witness 和只读几何审计已接入，保留预抓持 birth；待实机验证 |
| Horseshoe | stages、配方及五份输入已打包并核对哈希；当前模型检查保留；待实机验证 |
| Knot Untying | runner 已可注入 Session，由 bridge 持有 recorder；保留宽度协议和 IPC 初态；待实机验证 |
| Blanket Flatten | v15 候选已统一公共 material/PBD 支持并接入 Session 回调；待新镜像完整回放 |
| Rope Threading | v15 候选已显式绑定参考模型并接入 Session 回调；待新镜像完整回放，旧无辅助包仍不兼容 |
| Slotted Post Ring | 尚缺完整机器人 oracle，公共 bridge 不能补出任务策略 |
| Orbits | 尚缺完整机器人 oracle，历史外力流程不能作为机器人参考 |
| Cube fixture | 旧包缺完整冻结身份，需从匹配版本生成新包后才能接入 |

当前实施顺序：先核对 easy / medium / hard 的参考证明与 Harbor 冻结输入，
对匹配实例运行双模式 oracle/nop；存在配置差异的刚体任务先准备对应版本的新包，
再处理 Knot / Rope / Blanket 的冻结状态及共享运行支持；缺完整 oracle 的任务单独完成策略验证。
每个任务优先只增加参数/证据声明及薄回调，共享模块不增加按任务名分支的执行逻辑。

## v14 基线与合并候选

已发布的 v14 / `0.2.12-cu128` 工具哈希与镜像引用冻结在
`ci_checks/topogym_tooling_versions.json`，现有 78 个三档任务目录和 dataset 保留。
活动模板为 **tooling 16 / image 0.2.14-dev**（merged-v16），这是待验收候选编号；v15 候选（0.2.13-dev）的工具哈希已冻结。
唯一开发目标由 `ci_checks/topogym_active_release.json` 的 `active` 指定，`published` 保留正式基线。
当前 active 的 `tasks_root=null`，明确表示新镜像/任务树尚未完成，不能把 `tasks/` 下的旧版本当成候选。
两种生成器拒绝覆盖其他 tooling 版本的目录，standard twin 必须来自同版本 privileged 包。

合并保留 v14 的 R2–R5、PBD 多接触修复和 simulator-instability 分类；v16 用物理有效性策略取代 R1：穿透深度只作证据（深穿透的成功挂起待审，不结束 episode），施力（forcing）只记录，仿真崩溃是基础设施错误，除非崩溃前 0.25 s 内机械臂正在施力。详见 `docs/rcb/benchmarks/topogym.md`。
本地 Horseshoe 几何、Hedgehog hard 模型进入候选；Rope 的 `contact_relaxed_v16`、
Blanket 的 patch assistance、Fiber 的 sheath assistance 作为显式候选配置，三方使用同一冻结值。
旧刚体 oracle 的时间积分参数、开发时材质 monkeypatch 不自动提升为任务规则。
Rope 的 40 ms tick 下，0.25 s 持续窗口在第 7 tick 判断；原 v14 的 2.5 ms tick 仍是 100 tick。

Blanket 的 birth UV 及只读材质绑定已进入公共 task/PBD 代码，原 `assist_support.enable()`
保留为无操作兼容入口。Rope 的反馈规划依赖移到私有 `relay_feedback`，不需要打包 calibration_tools。
以下回调复用既有策略，通过 `SessionPolicyRunner` 仅调用当前 Session 推进：

| 家族 | `--entrypoint` | 私有数据 |
| --- | --- | --- |
| Blanket | `topogym.planning.blanket_flatten.public_session:run_feedback_policy` | 无额外文件；`--kwargs <JSON文件>`，内容如 `{"variation":"easy"}` |
| Rope | `topogym.planning.rope_threading.public_session:run_feedback_policy` | 用 `--include` 加入 `reference_relays/manifest.json`、所选档的 `<tier>_seed0.npz` 与 `<tier>_evidence.json`；同样传 variation |
| Coil | `topogym.planning.cast_coil.public_session:run_feedback_policy` | 从绑定 Session 读取 variation、seed 和任务参数；EE_ABS 经转换器提交 |
| Keyhole | `topogym.planning.cast_keyhole.harbor_session:run_feedback_policy` | F1/F2/F3 私有参考 |
| Lock | `topogym.planning.lock_picking.public_session:run_feedback_policy` | 原 reindex 算法 |
| Buzz | `topogym.planning.buzz_wire_3d.public_session:run_feedback_policy` | 三档 recipe；easy selection；medium/hard 全部 compiled actions；不继承历史成绩 |
| Fiber | `topogym.planning.fiber_bundling.public_session:run_feedback_policy` | 三档 selection |
| Horseshoe | `topogym.planning.horseshoe_ring.public_session:run_feedback_policy` | recipe + 哈希绑定的五份数据 |
| Hedgehog | `topogym.planning.hedgehog_in_cage.public_session:run_feedback_policy` | easy/hard pickup；medium 原内置配方 |
| Claws | `topogym.planning.interlocked_claws.public_session:run_feedback_policy` | witness + reference_routes |
| Knot | `topogym.planning.knot_untying.public_session:run_feedback_policy` | 原决策算法；使用冻结宽度布局 |

`--include` 的路径均从 `topogym/planning/rope_threading/` 开始，`--source-root` 指向源码根。
回调的旧参考证据用于确认输入来源，不能继承为新环境成功。它们仍需新镜像完整执行及独立评分。
`SessionPolicyRunner` 不生成 SegmentRunner 完整 tick 证明；Harbor wrapper 负责记录动作和检查生命周期。

先生成 39 个实例的独立输入与源码快照（不伪造 instance 或 describe）：

```bash
.venv-gs121-nyx/bin/python scripts/topogym_merge_candidate.py \
  --output runs/test_results/v15_candidate_new --gpu 0
```

产物 `candidate.json` 逐项列出相对 v14 的配置差异；`source_manifest.json` 绑定复制的源码。
`build_image.sh` 从该快照构建唯一的 dev 镜像标签，不更新 latest；`build_candidates.sh` 在该镜像中
为 IPC 导出初态、生成新 instance、实测 describe，再渲染 privileged/standard 共 78 个候选目录。
生成器同时检查 describe 的实际运行身份并写入双模式 runtime binding；旧 describe 缓存不得冒充新镜像实测。
专用 privileged agent 镜像可以包含额外工具，但它的公共 simulator 源码和物理依赖必须与 verifier 相同。
这两个构建脚本应在有 GPU/镜像构建依赖的主机上运行并沿用资源监控；prepare 本身不执行 Docker。
脚本保留基线实例与资产副本，运行不依赖另一个会话正在修改的源码。

之后对选定包调用上述 `harbor_oracle.py package/check/run`。保持 `oracle = "none"`、
`harbor_qualified = false`，直到严格初态重载、完整原生成功、fresh-process replay、视频与两种模式的
oracle/nop 独立评分均通过。候选镜像未构建或 GPU 未运行时，CPU 合同通过只代表合并接线检查通过。

## 检查范围

`ci_checks/test-harbor-oracle-bridge.py` 检查跨机器人动作、实例错配、私有依赖闭包、
打包完整性、隔离进程中的 wrapper 生命周期、失败证据、标准服务续传和评分分类。
隔离进程使用假的 task tooling；这些检查不运行 Genesis，也不构成可解性或物理回放证据。
源码隔离静态规则可用 `ci_checks/check-calibration-isolation.py` 检查；真实镜像验证需显式传入镜像。
`ci_checks/test-frozen-runtime-binding.py` 覆盖旧生成来源/新运行身份分离、源码替换、镜像漂移、
错误绑定拒绝、服务/回放双回执及 39 组正式实例副本一致性。它同样不构成物理可解性证据。
