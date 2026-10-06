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

默认队列保留 **easy / medium / hard**。简单档采用下方独立队列；精确匹配难度，
`very_easy` 不会误匹配 `easy`。运行器使用冻结源码中的打包器、控制器和任务生成器。

## very_easy / easier 独立 sweep

现已接入 9 类 × 2 档 × privileged/standard，共 36 个可选择评分位置；seed 0，
完整 oracle，串行执行，无模型调用。Rope 控制器仍是开发候选；本地历史成功不继承为当前 grade。
Slotted 的 very_easy（2026-10-06）经同一分派器接入 `slotted_post_ring/below_easy_oracle.py`（指尖捏环、直上越柱顶、
放入目标区），无参考数据；easier 暂缺 oracle，分派后由 `public_session` 拒绝（见 `docs/rcb/ORACLE_FIXES_2_FOR_JIANWEN.md`
第 5 节）。Hedgehog 的两档（2026-10-06）经同一分派器
接入 easy 的实测路径 oracle，每档一个 pickup（`reference_data/hedgehog_in_cage/<tier>/pickup.json`，由
`hedgehog_in_cage/below_easy_pickup.py` 生成）。

```bash
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output runs/test_results/harbor_below_easy_new \
  --families cast_coil,cast_keyhole,lock_picking,buzz_wire_3d,fiber_bundling,interlocked_claws,rope_threading \
  --tiers very_easy,easier --image topogym-below-easy:new --gpu 0
```

新目录、新镜像 tag 保留其他队列及历史结果。实例从当前 Task 默认参数及当前 Harbor 时序／抓持配置
重新生成，不复制旧三档的几何覆盖。镜像与私有控制器共享源码快照。`summary.tsv` / `summary.json`
逐项记录 grade、solve 和状态：仅有效完整评分写 `solve=0/1`；基础设施、打包、构建错误及未执行
保持空值并记录原因。privileged 未取得 grade 1 时，standard 标记依赖阻塞，不算已实测失败。
只需预览队列时加 `--plan`；恢复原队列时保留所有参数并加 `--resume`。

Blanket 的 very_easy / easier 按用户要求使用 **tooling v18+** grading。它们复用 Blanket
现有的 `SessionPolicyRunner` 和生成时关节限速，候选使用 95% 覆盖率及 1.3 抓持拉伸保护。
必须先在目标镜像／GPU profile 上准备两份初态，再显式传给候选构建器；构建器复制完整数值包，
只为 release 的覆盖率参数生成重键副本。不能把本地 Env 成功或旧版本轨迹算作 `solved=1`。

```bash
.venv-harbor/bin/python scripts/topogym_merge_candidate.py \
  --output <新候选目录> --families blanket_flatten --tiers very_easy easier \
  --image <独立的v18或更新镜像tag> \
  --blanket-initial-state very_easy=<同运行栈准备目录>/very_easy/state/manifest.json \
  --blanket-initial-state easier=<同运行栈准备目录>/easier/state/manifest.json
bash <新候选目录>/build_image.sh
.venv-harbor/bin/python <新候选目录>/source_snapshot/scripts/topogym_candidate_pipeline.py \
  --candidate <新候选目录> --phase build --families blanket_flatten
bash bash_scripts/run_harbor_oracle_grades.sh \
  --output <新评分目录> --tasks-root <新候选目录>/tasks \
  --families blanket_flatten --tiers very_easy,easier
```

接入层向旧策略提供 `mode`、观测字段及实例实际声明的 `grasp_assist`。Fiber 的分阶段执行使用
冻结 Session 的初始快照检查，允许 Harbor 启动时恢复快照产生的分支号，但仍禁止执行中回退、
重置、跨实例或跳过物理 tick；本地独立 proof 的出生状态要求不变。
Rope 两个简单档的新候选明确声明其现有 oracle 所需的 `ipc_soft_band_v1`，并在动作开始前检查
模型及 rope target。不兼容的旧实例会直接报配置错误，不自动修改运行中的配置。
这类新实例的评分不能替代旧 `grasp_assist=none` 实例的结果。

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

### 显式转换 standard 轨迹时序

privileged 的关节轨迹可能超过 standard 服务的每控制步关节目标变化限制。
打包默认 `--standard-timing exact`，仍逐行原速回放；仅在显式选择
`--standard-timing rate_limited` 时，打包器从该任务绑定的 tooling 读取 `JOINT_STEP_LIMIT_RAD`，
提前拆分超限行。`--references` 中的 standard recipe 同样可填写 `"standard_timing": "rate_limited"`。
每个原始关节终点保持不变，夹爪目标从该行的第一个子步切换，兼容行不变。
第一行保持原样，由真实服务检查它与初始命令的距离；不从轨迹猜测机器人初始姿态。

新包保留原始 `source_reference.npz`、转换后的 `reference.npz` 和带行映射、源码及轨迹哈希的
`timing_conversion.json`。转换会改变动作时序及可能的物理结果，属于新的待评分轨迹；
不继承源轨迹的成功标签。服务仍必须逐行恰好执行一步，任何额外限速、位置裁剪或台面保护
仍使桥接失败。成功继续要求原生 standard live 执行和独立回放均通过；不修改任务、服务或 grader。

### 跨设备鲁棒性 review（2026-10-05）

本次 frozen v16 简单档 sweep 与主仓库新合入的 v17 分开判断。Lock 两档 privileged 在
`deterministic=0` 时仍通过，说明末态字节差异本身没有导致这两项零分；standard 的已知问题是
动作超限。异机的其他失败需要各自日志，不能一概归为 GPU 数值偏差。

补读其他会话交接并核对实现后的更新：

- [第一批 oracle 修复](../../../docs/rcb/ORACLE_FIXES_FOR_JIANWEN.md)的 `oraclefix 08`
  已由 `5e1bfa54f` 合入。Lock 的共享 runner 在 Harbor Session 中采用生成时限速，原三档和
  below-easy 的 `route_mode="simplified"` 都经过该入口。旧 v16 sweep 快照没有这项修复。
- v17 已合入 R-hold：privileged 不再要求至少一遍在原动作长度内严格成功；具体评分实现以
  `unlimited/tests/grade.py` 的 `strict_replay_required=0` 为准，不能依据 common tooling 中保留的
  v16 注释推断现行规则。Lock 仅允许末尾最多 2 s 保持，没有放宽锁孔或槽的几何判据。
- [确定性物理说明](../../../docs/rcb/benchmarks/topogym.md#deterministic-gpu-physics-tooling-v17-2026-10-05)
  与实现均确认：v17 固定 GPU 刚体求解分支，PBD 累加改用定点数；IPC 的 libuipc 求解仍未覆盖。
  现有证据主要是同机重复回放，不代表不同型号 GPU 全程一致。
- [第二批 oracle 修复](../../../docs/rcb/ORACLE_FIXES_2_FOR_JIANWEN.md)已报告限速改变状态后，
  Keyhole/Buzz/Horseshoe 的后续抓取或释放可能走向不同结果。因此限速后的轨迹必须重新实际生成和评分，
  不能只用数组变化上限通过替代物理验证。

- `suite.py` 将成功 privileged 执行的动作数组交给 standard；两个模式的 verifier 都重新执行动作。
  本地控制器的在线纠偏不会随动作文件一起回放。闭环策略成功率与导出轨迹的回放稳定性应分别统计；
  只改本地反馈不能保证回放通过。规划应选择有余量的路径／终点，并对同一冻结构建做多次、跨设备回放。
- `callbacks.run_stages` 按数组位置锁定参考步骤名，Fiber 的 comb 次数却由实测状态决定；微小变化
  导致多一次或少一次 comb 时，可能触发 recipe mismatch。参考应表达阶段目标和优先候选，允许在当前状态
  重新规划；候选尚未推进物理时可以尝试下一候选，已执行失败后的恢复必须通过真实连续动作，不能 rewind。
- Lock 固定次数的精对齐、Buzz/Fiber 的参考跟随停滞门槛、Rope 固定目标姿态的有限 IK 种子都需要
  区分“仍在收敛”“稳定小偏差”“实际不可达”。使用有界纠偏、几何余量及任务允许的姿态自由度；
  不把真实碰撞、抓持丢失、材料损坏或原生 Task 失败用容差掩盖。
- 已用合成观测复现 `BuzzWirePolicy.joint_reference_actions` 的终点等待问题：到达轨迹末端后，
  若 `arrival_error_m <= error < progress_error_m`，`elapsed` 已不再增长，但 `last_advance` 每次仍刷新。
  默认容差下固定 0.8 mm 残差在 30 s 后仍等待；2 mm 残差则在 8.025 s 正常报停滞。
  这是控制流复现，不是物理成功／异机失败证据。需要按真实路径推进或误差改善更新进展，并在
  几何安全预算内增加有界纠偏／局部重规划；只延长超时或只修成更早失败都不能解决残余偏差。
- Buzz 的 `checked_turn` 当前丢弃每个候选的 `ValueError`，只保留总失败。需要保留候选、IK 残差、
  最小间隙与拒绝阶段，才能判定应扩大搜索、重抓，还是路径确实不可行。

固定轨迹的改进应直接针对回放：生成阶段选择孔／槽中央、远离接触临界分支、抓取与后续搬运都有
余量的路线，在关键接触之前安排足够收敛时间，然后冻结动作数组，在独立运行中检验同一数组。
生成时的重新对齐、局部重规划只帮助找到候选；grader 不执行这些分支，不能承诺回放自动恢复。
`Session.step` 在原生首次成功后停止记录，成功后的 hold 不能由 oracle 随意补进原始连续证据；
当前 standard twin 的有限 hold 与 grader 的 R-hold 已分别实现，二者不是新的闭环策略。

先验证生成时限速的 Lock 新参考，再按失败日志判断是生成失败、接触路径分叉还是仅终点确认延迟。
同一冻结实例的控制器执行、独立动作回放分别记录成功率及首次失败阶段，不挑选成功重跑替代失败分母。
受控扰动测试属于单独的鲁棒性实验，不覆盖正式冻结实例。实例／源码身份、记录完整性和评分条件保持严格。

### 全部 very_easy / easier oracle 的逐入口复核

2026-10-05 工作区 review，基于 `b1ab6b18d` 加当时未提交改动；包含正在开发的 Knot
`BelowEasyRunner`。这里只审查两个简单档，原 easy / medium / hard 没有增加运行。
[范围、源码哈希与合成复现](../../../runs/test_results/below_easy_oracle_robustness_review_20261005/review.json)
覆盖 13 类 × 2 档：24 个场景已登记，8 类／16 档有 Harbor 候选机器人 oracle 入口。
Coil、Keyhole 的两个入口仍在 registry 的 experimental 池，`difficulty=None`，范围按明确的变体 ID
和桥接入口识别，不能只筛选 difficulty 字段漏掉它们。入口存在不等于解题或稳健性验收完成。

共同原则如下，后续生成和验收均按这些边界记录：

1. **执行接口有余量。** 以实例实际 tooling 的步长限制为准，在生成时限制编译后的关节目标；
   从 home 的第一行、float32 转换、请求分批和 native guard 后的实际接受目标都要覆盖。
   不能把末端速度慢或名义路径密集当作公开关节动作必然合法。改变时序后重新生成并评分。
2. **收敛有时间预算。** 关键接触之前允许实际动作保持与收敛，区分路径推进、误差改善和完全停滞；
   阶段有总时长上限。到达路径末端不应刷新“仍在前进”的计时。生成时的反馈不随动作数组回放。
3. **目标与安全边界分开。** 规划尽量进入可行区域内部，分别记录横向、轴向、倾斜、槽角度和接触余量；
   容差从对应几何与回放偏差确定。候选不能仅以“第一个不碰撞”作为稳健性标准，后续动作也应可行。
4. **终止及物理约束不被掩盖。** 保留原生碰撞、抓持、材料、拓扑和 Task 失败判据；恢复通过连续动作。
   现有 standard twin hold 与 GPU 家族 R-hold 分别复用，不能把成功后未执行的动作写成已记录轨迹。
   v17 的确定性刚体／PBD 修复在共享 Session 生效，IPC 不因此获得跨机确定性保证。
5. **固定数组单独验收。** 分开记录生成成功、双模式评分与同一动作文件的多次／跨机回放。
   保存版本、实例、动作哈希、最小几何余量、确认延迟、hold／容差使用、首次偏离阶段和全部失败次数。
   现有可核对记录没有覆盖全部 16 档的跨机余量验收；下表历史正分不升级为该资格。

| 家族（均审查两档） | 已具备的做法 | 具体缺口或限制 | 可核对的历史评分范围 |
| --- | --- | --- | --- |
| Cast Coil | 从 seam 派生 arrival/insertion 误差；区分横向偏离与沿插入轴滞后；抓取保持、阶段总超时、释放静置 | Harbor 用普通 `SessionPolicyRunner`，没有统一生成时关节限速；终点仍会刷新局部进展计时，但有阶段总上限；未校准跨机最小间隙 | v16 两档 P/S 均 1；保存动作最大相邻步长约 0.01182／0.02376 rad |
| Cast Keyhole | 有受限积分／阻尼、相对位姿推进预算、拾取和搬运预检；拾取尝试 TCP 抬升 0／1／2 mm | 简单档独立 `public_session.submit` 直接 `Session.step`，未使用原三档 runner 的限速；拾取预检允许桌面间隙 0，且取首个通过候选。旧运行预检间隙仅约 0.068／0.040 mm；较宽的路径跟踪门槛还缺跨机余量校准 | v16 两档 P/S 均 1；最大相邻步长约 0.02792／0.03665 rad；上述桌面间隙是采样预检结果，不是 live 最小间隙 |
| Lock Picking | 两档确实经过共享生成时限速；0.3 s 保持和有界负载纠偏；原生插入成功及稳定窗口 | 固定最多 10 次精对齐、固定 0.15 mm／0.0003 rad 目标，以及 easier 的锁片 ±2° 检查，尚未按剩余几何空间分解；共享 spread limiter 的 guard 边界缺陷见下文 | 旧 v16 两档 P=1、S=0，均因 10 行约 0.04166 rad 超限；新 v17 实际限速生成批正在运行 |
| Buzz Wire 3D | 从实测抓持规划；有采样间隙、慢速放置、夹爪落稳和终点候选 | 简单档仍用普通 runner，未继承原 easy 的限速；两个末端等待循环存在局部看门狗缺陷；终点候选取首个可行项并丢弃逐候选异常，余量与失败原因不足 | 旧 v16 very_easy 终点规划失败，easier P=1/S=0；easier 有 12 行超限，最大相邻步长 0.18446 rad |
| Fiber Bundling | 1 mm 路径 clearance，梳丝目标给入环中心误差留量；参考后保持；逐 tick 不变量和阶段总超时；简单档允许 0.5 mm 轴向预检残差而保持原生穿环判据 | 动态 comb 次数与固定 selection 下标不一致时会 recipe mismatch；session 模式只读候选失败也立即退出；未统一限速；继承空手接近循环的局部看门狗缺陷，但 pickup 外层有 90 s 上限 | v16 修复批两档 P/S 均 1，最大相邻步长均约 0.00925 rad。held-reference 的 progress/arrival 明确相等，不能将 Buzz 该处死区直接套用到它 |
| Interlocked Claws | 实测抓持、积分加阻尼；限制相对目标推进步长；物体路径保留 1.5 mm 余量、机器人预检保留 2 mm 桌面间隙；阶段总超时与目标保持 | 无统一生成时限速；0.4／0.8 mm 跟踪门槛固定，缺各条窄路径的回放误差预算；局部终点计时同样刷新，但总上限兜底。easier 更长的路线应单独量化累计偏差 | v16 修复批两档 P/S 均 1；最大相邻步长约 0.00626／0.01950 rad |
| Rope Threading | 名义关节速度限制、2 s 到达等待、4 s 渐进抓取；读取当前绳形、检查实际材料被提起，结束保持最多 10 s | 未统一约束实际公开关节步长；完整插值目标仍固定位置和姿态，有限 IK 种子失败后没有合法替代路线；未对路径和交接余量做跨机验收；IPC 噪声未由 v17 全部消除 | 修复抓持配置后的 very_easy live 已发生 IK 失败；easier 无本轮完整正分。不能把有限 IK 失败直接归为微小浮点噪声 |
| Knot Untying | 简单档专属限速给 5% 余量，并核对 guard 后目标；根据实测交叉选择可达抽绳候选。easier 新增闭爪前对准、实际提绳检查和最多三次连续恢复尝试 | 当前 `BelowEasyRunner` 明确保留原插值并关闭共享实验性 hover/crush 路径，不能声称继承了这些策略；follow-up 抓取修复只覆盖特定分支；新工作区代码尚未获得完整回放资格，IPC 仍有未覆盖的非确定性 | 另一会话冻结 v16 的 very_easy P/S 均 1、无 hold／容差使用；easier 旧尝试抓取失效并中断，无最终分数；新源码不继承旧快照成绩 |

表中动作步长来自[保存数组审计](../../../runs/test_results/below_easy_oracle_robustness_review_20261005/recorded_action_bounds.json)，
只统计相邻目标，不替代第一行、实测接受动作和新版本物理执行检查。
Keyhole 的[拾取间隙记录](../../../runs/test_results/below_easy_oracle_robustness_review_20261005/keyhole_pickup_margins.json)
保留原报告路径与哈希。未超过 0.04 rad 的历史轨迹不能证明该生成器在所有状态都满足限速。

Hedgehog、Horseshoe、Slotted Post Ring、Orbits 的两档场景已有，但未找到对应完整机器人 oracle／Harbor
callback，因此八档记为“缺少可审查的完整 oracle”，不能套用原 easy 的策略或算作原则通过。
Blanket 的两个简单档尚未在当前 registry 登记，也未找到相应 oracle。Cube 是测试任务，不混入这 13 类。

**已复现的代码边界问题：**

- `BuzzWirePolicy.joint_reference_actions` 与 `acquire_actions` 在路径进度已到 1、残差仍处于两条阈值
  之间时持续刷新 `last_advance`。1 s 合成路径、固定 1.2 mm 残差，两个循环到 30 s 都未停止；
  0.5 mm 正常完成、2 mm 正常触发停滞。Fiber 继承空手接近循环，但外层 Stage 仍会超时。
  应依据实际推进或误差改善更新时间，并给末端收敛独立预算；不能把更早报错当作鲁棒性修复完成。
- `standard_rate.RateLimiter` 的 spread 模式预先计算插值步数；若 native guard 拦住中间一步，
  后续重新锚定后仍按原步数完成，最后直接发送原目标。合成“第一步 arm 不动、第二步接受”的反馈，
  0.04165614 rad 请求产生了同样大的接受跳变，超过服务 0.04 rad。应每一步（含最后一步）相对实际
  接受目标限幅，并将受阻后的未完成量交给有界反馈处理。当前简单档中的共享 limiter 使用者是 Lock；
  Knot 的独立 limiter 已逐步 clip 并检查。该复现不证明正在运行的 Lock 发生了台面 guard，也不是其旧失败原因。

整改顺序：先修已证实的限速／看门狗边界并补 Buzz 简单档限速；随后评估 Keyhole 的正间隙抓取候选、
Fiber 的语义阶段匹配和只读候选回退、Lock 的几何误差预算；Rope/Knot 的抓取及可达路线按各自失败日志处理。
Coil/Claws 保留已有效的间隙与反馈设计，补统一执行保障和固定数组回放验证。
所有影响时序、抓取或路线的改动都形成新候选，不修改正在评分的冻结源码，不继承旧轨迹成绩。

### v18 补丁对简单档的适用范围（2026-10-05）

在上述 v17 review 后，工作区新增了 merged-v18 / tooling 18 / image 0.2.16-dev 补丁；
当前 release 仍为 `source_candidate`，`tasks_root=null`。以下是源码及 CPU 检查结论，不是新版本
的简单档物理成绩。[检查记录与源码哈希](../../../runs/test_results/v18_patch_review_20261005_210448/report.json)、
[两档配置与依赖核对](../../../runs/test_results/v18_patch_review_20261005_210448/compatibility.json)。

| 补丁 | 简单档适用方式及边界 |
| --- | --- |
| libuipc 三个确定性补丁 | 公共 CUDA 求解、装配／接触候选排序、分段归约的修复，适用于使用 IPC 的 Rope、Knot、Orbits、Slotted，不按难度过滤。需构建并安装 `0.0.25+topogym.det1.cuda128` 或 `cuda130` wheel；只更新 Python 文件或复用旧 wheel 不生效。补丁附带的确定性证据限定同 GPU 型号，不等于跨型号 oracle 成功保证。 |
| settled-state 恢复后重算 forward dynamics | 修复恢复后第一次推进仍使用旧机器人质量矩阵的错误；公共恢复入口生效。旧 IPC 状态含旧 pyuipc 身份，需在新环境重新准备，不能只改 manifest 哈希。原三档 Rope 发布配置不使用该资产；当前简单档候选构建也为 Rope 导出 IPC 状态，因此应与 Knot 一起重新准备。 |
| Knot K2 | 当前 tooling 的两个简单档配置均继承 `physics_dt_s=0.005`、`control_decimation=5`、半隐式 Newton 且至少 3 次迭代。控制周期仍为 25 ms，但此前 2.5 ms 完整 Newton 的物理积分过程已改变；不能继承 v17 简单档轨迹资格，需在 v18 新实例上生成并独立回放验收。 |
| 抓持／释放／Blanket coverage 加速 | 公共物理与判据实现中的等价优化，调用这些入口的简单档自动受益；不会给 oracle 增加重规划或更宽成功条件。本机 300 例抓持、300 例释放几何对照均无差异；完整简单档回放仍未在本轮执行。 |
| warm-cache 日志修复 | 避免把空 `RCB_SESSION_LOG` 固化到镜像，所有使用该预热流程的新镜像受益。修复的是交互日志和统计，不是路径或成功判据。 |
| Buzz retiming、Blanket 限速 | 属于 oracle 入口改动。Buzz 当前 medium recipe 接入按实测间隙减速／保持的重定时器；两个简单档仍走独立 `below_easy` 策略，没有自动继承。Blanket 修改现有原三档 route 的 runner，不能据此认为新增简单档已有完整 oracle。 |

本地核对时 `.venv-gs121-nyx` 的 pyuipc 为 `0.0.25`，Lock `harbor_below_easy_20261005_05`
仍绑定 v17 冻结包。接入 v18 应使用独立源码快照、新镜像和新任务包；不热替换正在运行的队列。
两种 CUDA 构建配置的三个补丁哈希均匹配。CPU 单元检查 103 项通过、1 项报错：
`test_resume_cannot_switch_cuda_profile` mock 未建立冻结源码目录，读取 release 文件时失败；
HEAD 原版测试在当前 pipeline 上同样复现，不能归为 IPC 求解失败。其余 tooling 检查通过
（126 个历史／活动包），无本轮新增 GPU 成功或跨机确定性结论。

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
该默认范围排除 Orbits、Slotted Post Ring、very_easy、easier；简单档使用本页独立 sweep。
它执行完整 oracle，不带 nop 负对照，
不激活发布版本。完整执行可能耗时很长；`--wall-seconds` 是每个实例双模式的总时限，
不是整个 33 项队列的一小时时限。

接收方需要完整 Git checkout、Python 3.12 管理环境、Docker daemon、NVIDIA Container Toolkit
及可用 CUDA/Nyx GPU。三档 Harbor 回调的参考输入随 `topogym/planning/` 交付，
无需复制原机器的 `runs/` 或 `solvability_proof/*/*/evidence/`。
首次执行从独立源码快照构建候选镜像，再生成双模式任务；默认镜像标签为
`ghcr.io/luigivamper/rcb-topogym:<images/topogym/VERSION>-cu128`（v18：`0.2.16-dev-cu128`），本地构建不会 push 镜像。
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

当前 active 为 v18，`tasks_root=null`；仓库 `tasks/` 中的 78 个原三档包仍为 v14。
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
| very_easy/easier | 7 类控制器已接入独立队列；重新生成当前版本任务包，逐项等待 Harbor 评分 |
| 旧无分档包与 Cube 示例 | 不在当前分档队列中；历史版本不能绕过活动版本身份检查 |

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
活动模板为 **tooling 18 / image 0.2.16-dev**（merged-v18），这是待验收候选编号；v15 候选（0.2.13-dev）、v16 候选（0.2.14-dev）与 v17（0.2.15-dev）的工具哈希已冻结。
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
| Hedgehog | `topogym.planning.hedgehog_in_cage.public_session:run_feedback_policy` | easy/hard 及 very_easy/easier pickup（简单档行速受标准服务步长限制）；medium 原内置配方 |
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

## 2026-10-06 两档 IK／路径改动重跑

`harbor_below_easy_v18_20261006_ik01` 使用独立冻结源码、镜像和新生成的实例，重跑
very_easy／easier；不执行原三档，不继承旧评分。通用 IK、实际 FK 路径检查和共享执行入口
影响全部 12 类已接入的简单档 oracle，因此旧 sweep 已通过的 18 项也在复验范围内。

首批 10 类、40 项：Buzz、Lock、Coil、Keyhole、Fiber、Claws、Hedgehog、Horseshoe、Knot、
Orbits，每类两档、privileged／standard 双模式；优先处理 Buzz 和 Lock。Rope／Blanket 共 8 项
等待用户明确此前「取消柔体辅助」要求与本次最新版配置的关系，未擅自启用后加入队列。
Slotted 两档在本批冻结时仍缺 Session callback，不记为已覆盖（同日合并的上游已接入 very_easy，见上文，不在本批内）。启动器已接通 Orbits 的两档分派。

本次 oracle 改动的 28 个文件与既有 207 项测试的源码记录一致；新增启动器验证 7 项通过，
12 类 × 两档共 24 个私有依赖闭包检查通过。冻结 1232 个源文件并校验一致。
这些检查不是物理成功。新队列已启动，实际结果以
[`state.json`](../../../runs/test_results/harbor_below_easy_v18_20261006_ik01.supervision/state.json)、
[`summary.json`](../../../runs/test_results/harbor_below_easy_v18_20261006_ik01/summary.json) 为准；
逐项重跑依据见
[`retest_decisions.json`](../../../runs/test_results/harbor_below_easy_v18_20261006_ik01.supervision/retest_decisions.json)。
旧 `harbor_below_easy_v18_20261005_01` 队列已停止，结果保留；未完成 Rope easier 取消的记录见其
同级 `.supervision/superseded.json`，不能将中断记录解释为新物理评分。

## 检查范围

`ci_checks/test-harbor-oracle-bridge.py` 检查跨机器人动作、实例错配、私有依赖闭包、
打包完整性、隔离进程中的 wrapper 生命周期、失败证据、标准服务续传和评分分类。
隔离进程使用假的 task tooling；这些检查不运行 Genesis，也不构成可解性或物理回放证据。
源码隔离静态规则可用 `ci_checks/check-calibration-isolation.py` 检查；真实镜像验证需显式传入镜像。
`ci_checks/test-frozen-runtime-binding.py` 覆盖旧生成来源/新运行身份分离、源码替换、镜像漂移、
错误绑定拒绝、服务/回放双回执及 39 组正式实例副本一致性。它同样不构成物理可解性证据。
