# 新一轮 pull 后的 Run trials 全流程审查

日期：2026-10-02，Chicago。范围：镜像准备、任务生成与预检、动作接收、物理状态读取和终态、双模式评分、录像、结果收集和 HF 离线导出。用户已授权真实 GPU 验证。

本轮为审查，不修改生产代码、任务包或既有暂存内容。发现的问题及建议如下；完整参考解、78 项 GPU 矩阵与冷构建性能不在本轮通过结论中。

**后续处置（2026-10-02）：** 用户确认 A04 的跨 GPU 冻结初态拒绝加载符合预期，本轮不调整 Blanket 兼容规则或异常分类。用户授权修复 A01、A03，已实施于新生成 tooling v6 与当前收集/导出代码；旧包和旧 run 的冻结源码不追溯替换。详情、验证及全仓库检查的独立阻塞见 [A01/A03 修复记录](run_trials_a01_a03_repair_20261002_zh.md)。下文保留审查时证据。

## 1. 审查版本与证据范围

审查开始时 HEAD 为 `597593dbb`，包含协议合并 `c4d952c86` 和 Keyhole 简化变体。工作树另有 **850 个暂存改动**，包括批量读取刚体状态、版本 0.2.7，以及三档任务包重生成。因此本报告核对的是 **HEAD 加当前工作树快照**，不能把所有发现归因于这一次 pull。

- 106 个现有任务包：78 个三档双模式包为 tooling v5，28 个历史包继续保持旧身份。
- 当前公共工具使用 standard 2.3；镜像版本文件为 0.2.7。
- 已固定源码、选定任务包及文件哈希，见[本轮证据目录](../../runs/test_results/run_trials_pull_audit_20261002_01/README.md)中的 `baseline.json`、`snapshot/`、`package-hashes.json`。
- GPU 为 RTX 4090，计算能力 8.9；测试串行、非 root、无模型调用。主机另有无关工作负载，因此短程时间不作为独占机器的吞吐基准。
- GPU 使用独立审查镜像 `topogym-local/pull-audit:20261002-01`，包含固定的当前源码及既有 cu128 依赖。另按完整当前 Dockerfile 构建 `topogym-local/pull-audit-full:20261002-01`，不覆盖正式 tag。
- 两审查镜像的运行源码与数据文件一致；前者额外含三个 README，依赖版本一致。细目见 `image-comparison.json`。没有将此说成 registry 上的 0.2.7 已发布或完成全任务验收。

## 2. 问题汇总

| 编号 | 优先级 / 性质 | 发现 | 证据与影响范围 |
| --- | --- | --- | --- |
| A01 | P1，错误分类及队列中断 | 加密或不支持压缩格式的 NPZ 仍被记为 grader error | CPU 调用真实 parser → grader → collector，得到 `infra_failed`；新 run-trials 也受影响 |
| A02 | P1，实例资格检查缺口 | 刚体位姿容差兜底不比较速度 | CPU 复现初始速度从 0 变成 2 m/s 仍匹配；未声称 GPU 已发生错误成功评分 |
| A03 | P1，输出流程未对齐 | 汇总结果和 HF 导出漏掉新的 verdict、媒体状态和录像时间轴文件 | 真实 collector 复现丢失；影响双模式的结果可追溯性，原 Harbor 目录仍可保留这些文件 |
| A04 | P1，固定包兼容性及故障分类 | 当前三档 Blanket 初态来自计算能力 12.0，RTX 4090 无法加载；异常未统一归为实例不兼容 | easy 包真实 GPU 初始化失败；三档 manifest 均为 12.0；默认新 run 本机 prepare 的路径需单独区分 |
| A05 | P2，请求恢复的可观测性 | operation 查询被正在执行的请求阻塞 | 真实 HTTP 测试中查询等待约 4.07 s，直到动作全部执行完才返回 |
| A06 | P2，版本升级回归测试 | 镜像版本已变成 0.2.7，测试仍硬编码 0.2.6 | 195 项 CPU 回归中该项失败；这是测试维护问题，不代表镜像标签函数出错 |
| G01 | 合同覆盖缺口，沿用 B10 | 默认刚体合同仍看 tick 末接触，不能承诺任一子步违规必被发现 | 现有 CPU 合成事件回归通过；真实瞬时违规对照仍未取得 |

另有 observe 时间量化边界，见第 4 节。性能情况与优化建议见第 5 节。

## 3. 问题详情

### A01 畸形轨迹仍可被当作基础设施故障

[load_trajectory](../../harbor_templates/topogym/common/rcb_topogym.py:110) 在审查时只转换部分解析异常。从一个很小的正常 NPZ 出发，将 `actions.npy` 标为不支持的压缩方法，实际抛出 `NotImplementedError`；将该 entry 标为加密，实际抛出 `RuntimeError`。修改后的文件不是符合提交要求的合法轨迹；这两项是异常输入边界测试，不代表正常生成的 NPZ 普遍失败。

两者均未创建 Session，但 [privileged grader](../../harbor_templates/topogym/unlimited/tests/grade.py:112) 输出 `success=0, grader_error=1`，collector 返回 `infra_failed`。run-trials 随后按基础设施失败停止队列，而非记录无效提交后继续。见 `targeted-repros.json` 的两个输入案例及 `malformed_classification`。

建议在 ZIP 容器检查阶段明确限制加密标志和压缩方法，并转换该阶段可识别的格式异常。不要把所有 `RuntimeError` 都视为提交错误，以免掩盖真实物理故障。该问题是 B04 修复的剩余输入边界。

### A02 刚体实例匹配没有覆盖初始速度

[Session._poses_match](../../harbor_templates/topogym/common/rcb_topogym.py:964) 已检查软体完整节点位置/速度，但对刚体只比较对象位置、四元数及机器人关节位置。`objects()` 中保存的刚体 `velocity` 没有参与比较。

CPU 复现保持对象位姿和机器人关节相同，仅将刚体线速度从 `[0,0,0]` 改成 `[2,0,0]`，函数仍返回 True。在精确状态哈希不同、资产匹配的分支中，这会允许动力学初态不同的实例进入评分。见 `targeted-repros.json/rigid_velocity_fallback`。

这证明检查条件有缺口，不证明常规 GPU 重建已经产生 2 m/s 差异。建议冻结并比较任务相关刚体线速度、角速度及必要的机器人速度/控制目标，容差应通过实际重建验证，不能要求所有 GPU 字节完全一致。

### A03 新的评分和录像证据没有被完整收集

生成包已经输出权威 verdict、媒体状态、frame map 和 recording manifest，但 [collect_manifest](../../scripts/collect_batch_results.py:93) 仍只复制五类旧文件；[HF MEDIA 清单](../../scripts/difficulty_results_hf.py:32) 同样未扩展。

本轮在两模式的 verifier 目录放入相应 sidecar 后，实际调用 collector，以下文件均未进入 `results/`：`verdict.json`、`media.json`、`final.json`、`replay.verdict.json`、`replay.frame_map.jsonl`、`replay.recording_manifest.json`。各模式实际适用的文件应分别保留，不要求生成没有意义的空文件。

后果是汇总结果/HF 数据无法独立核对录像源物理时间、评分提交记录及媒体失败原因。原 Harbor trial 目录中的证据不一定丢失，数值 reward 也不因此必然出错。建议同时更新本地收集、HF allowlist、schema 和离线回归；涉及路径或内部信息的字段按现有导出规则处理。

### A04 当前 Blanket 固定包的 GPU profile 不适合本机

当前 easy、medium、hard 的冻结初态 manifest 都记为计算能力 `[12,0]`，来源 GPU 为 RTX PRO 6000 Blackwell Max-Q。本机为 `[8,9]`。真实运行 easy privileged 包时，在恢复初态阶段抛出：

```text
Frozen initial-state incompatibility at backend/device/compute_capability:
archive=[12, 0], runtime=[8, 9]
```

见 `gpu_blanket_flatten/report.json` 和 `gpu-blanket_flatten.log`。拒绝不兼容物理缓冲区是正确保护，不能修改哈希或缩放缓冲区绕过。

问题在于交付范围和错误分类：这六个当前三档包不能被默认视为已适配 RTX 4090；[require_compatible](../../topogym/world/physics/initial_state_compatibility.py:106) 抛普通 `ValueError`，发生在 Session 创建的 `env.reset` 内，尚未到包装成 `InstanceMismatch` 的位姿校验。privileged 的通用异常分支会将其记为 grader error，standard 的启动 mismatch 专用分支也捕获不到该类型。

另将真实 GPU 所得的异常类型/消息注入真实 grader 和 standard 启动入口：privileged 得到 `grader_error=1`；standard 进程退出 1，未生成 `final.json`。见 `profile-error-classification/classification.json`。此补充是 CPU 错误分类验证，不是第二次 GPU 物理运行。

建议明确固定包的 GPU profile，提供适合目标机器的新冻结初态，并让明确的初态兼容异常统一进入资格失败路径。**默认新 run-trials 的 `prepare_blanket` 会在所选 GPU 上准备新状态；本轮固定包失败不能外推为该 fresh prepare 路径必然失败。** 已有完整 package/preflight 身份检查应继续保留。

### A05 操作查询不能在长请求执行中及时返回

[共享服务](../../scripts/eai_standard/rcb_limited.py:964) 使用单线程 `HTTPServer`；POST 未处理完之前，GET `/operations/<id>` 也不会被处理。[客户端查询](../../scripts/eai_standard/rcb_client.py:181) 的读取超时为 60 秒。

真实 HTTP 复现先确认操作记录为 admitted，再发查询；查询等待约 4.07 秒，最终只拿到 completed。见 `inflight-status.json`。这是可控慢步骤测试，没有 GPU 卡死注入。

因此“请求出问题后查询当前操作”在长时间不可抢占调用中并不能保证可用；超过 60 秒时客户端还有再次超时的风险。相同 ID 去重本身的回归通过，没有因此发现重复执行。建议由能独立处理只读请求的服务层提供已提交进度，保持物理执行仍由主线程串行负责。

### A06 版本升级后的测试期待值过期

[test_profile_image_tags](../../ci_checks/test-builder-feedback.py:211) 仍期待 `0.2.6-cu128`，实际 `images/topogym/VERSION` 为 0.2.7。本轮该断言失败，其余同套测试通过。建议将通用标签拼接测试与固定历史版本兼容测试分开，升级版本时更新对应测试，避免把正常升级误判为运行逻辑回归。

## 4. 物理步语义与各任务流程对齐

78 个当前三档包使用同一代 v5 工具及双模式模板，静态身份检查通过。未发现本次 pull 将先前动作记录、整数 dt、评分先落盘、共享录制或实例匹配成功门槛整体回退。历史 28 包按冻结身份检查，不计为新流程回退。

物理过程的观测范围仍按任务和后端不同：

| 任务 | 过程与终态检查边界 |
| --- | --- |
| Interlocked Claws、Cast Coil、Cast Keyhole、Hedgehog、Horseshoe | 默认公共刚体合同 1 检查 tick 末 contacts；可选合同 2 使用完整子步快照，仍待真实瞬时违规资格验证 |
| Buzz Wire、Fiber Bundling | 已有专属子步接触事件和覆盖检查；不能据此保证所有几何事件连续时间可观测 |
| Lock Picking | 按 tick 更新路线、接触和终态状态；不能继承其他刚体任务的合同 2 资格 |
| Blanket | PBD 状态/形状与稳定条件；冻结初态另受 backend/GPU profile 约束 |
| Knot、Rope Threading、Orbits、Slotted Post Ring | IPC/FEM 状态与任务条件；当前不能选择上述刚体子步合同 2 |

**G01 / B10 仍未关闭。** 本轮原有合成事件回归通过，但没有新增真实“前子步违规、末子步恢复”对照，不能把默认合同 1 宣称为全过程无违规保证。

还复现了 observe 的量化边界：在 40 Hz 下，`seconds=0.0125` 实际执行 0 控制步，`seconds=0.0375` 执行 2 步、0.05 s。[do_observe](../../harbor_templates/topogym/limited/environment/sim/server.py) 使用 `round(seconds * CTRL_HZ)`，与 submit 对整数周期的严格要求不同。实际物理计数仍然正确，响应 `seconds` 则保留请求值。见 `observe-quantization.json`。建议明确声明请求值与实际时长，或统一量化/拒绝规则；此处列为语义边界，不等同于已经发现错误评分。

新增 Keyhole very_easy/easier 是独立具名入口；当前三档采样不会自动包含它们。其加入并不自动将原 78 项矩阵改为五档，也不能继承旧实例成功记录。

## 5. 性能检查与可优化方向

### 已有优化的实测

当前工作树新增 `_RigidReadout`，把逐实体、逐 link 的刚体状态读取改为按 solver 字段批量读取。本轮在真实物理推进中比较实际 `read_state()` 与旧的逐 link 读取结果，包括键顺序、dtype、shape 和字节；通过范围以 GPU 报告为准。

Interlocked 短程首个结果：44 次对照均一致；新完整 read_state 中位约 2.23 ms，旧方法仅刚体部分约 22.42 ms。两个计时范围并不完全相同，且探针同时执行两种读取，**不能将这个比例说成整局或整控制步加速倍数**。它支持“刚体状态回读热点已明显改善”的判断。

### 镜像构建实测

完整当前 Dockerfile 构建约 **24.0 秒**，峰值主机内存占用 22.2%；构建上下文传输 166.46 MB。编译阶段约 7.5 秒，其中 Ninja 报 `no work to do`；wheel audit 约 5.6 秒，Nyx 资源准备约 2.4 秒。见 `full-image-build.log/json`。

这是**已有依赖层和编译对象缓存的单次结果**。新增 `UIPC_BUILD_JOBS` ARG 使本次 compile RUN 重新执行，但对象缓存仍命中。没有清缓存测冷构建，没有测全套 controller/runtime/client/agent 镜像总耗时，也没有推送或覆盖正式镜像。

### 值得继续优化的部分

| 方向 | 当前依据 | 建议与约束 |
| --- | --- | --- |
| 场景初始化与独立 replay | 代表性初始化仍为百秒量级；短动作后重新建场景的固定成本显著 | 分开计时资产生成、Genesis build、初态恢复和 Nyx 初始化；优先缓存可验证的静态资产，不跨物理实例复用可变状态 |
| grader 的非录像回放 | Session 默认启用 RGB，Env 每控制步仍走 observation；第一遍评分没有正式录像 | 测量无媒体阶段的观测成本，再验证关闭非必需 RGB 是否保持实例与物理结果一致；agent 需要的观测保留 |
| Blanket 几何判据、IPC/FEM 长程 | 本轮短测不能覆盖大网格判据总成本、长程显存和多次 reset | 单独做固定工作量长程测量；不能用更少物理 tick、凸包近似或放宽判据伪造加速 |
| UIPC 编译并行度 | Dockerfile 默认 3 jobs，直接构建可传更高值；默认 delivery 未提供这一用户选项 | 根据内存设置受控参数并记录构建身份；提高 jobs 会影响 cache key，应避免重复无效打包 |
| 输出与持久化 | 新增 fsync、录像完整解码及重复证据复制具有成本 | 分段测量后减少不必要复制，保留权威 verdict 的可靠提交与独立媒体校验 |

## 6. 验收汇总与限制

- CPU：17 套共 195 项，194 通过，1 项版本期待值失败；本轮针对性复现另行记录，不混入“通过”计数。
- 协议：在具备 requests 的 Harbor 环境中 16/16 通过。首次用模拟器 venv 缺 requests，属于审查环境问题，保留原日志，不算产品回归。
- 静态：当前 106 个任务包检查通过，历史迁移警告保留。
- GPU：三个场景完成短程执行、reset 回放和共享录像，132 次新旧刚体读取对照无差异；Blanket 固定包因 GPU profile 不兼容失败，见下表。
- 测试脚本、命令、退出码、资源采样与录像保留；未运行模型、未上传 HF、未做 78 项全 GPU 矩阵、未验证全部任务可解性，也没有真实 GPU 原生卡死注入。

| GPU 场景 | 实际身份与范围 | 结果 |
| --- | --- | --- |
| Interlocked Claws hard | 当前冻结包，2 控制步 / 20 物理步，然后 reset 回放 | 流程通过，44 次读取对照无差异；初始化约 179 s |
| Slotted Post Ring hard | 当前冻结包，IPC/FEM，2 控制步 / 20 物理步，然后 reset 回放 | 流程通过，44 次读取对照无差异；初始化约 147 s |
| Cast Keyhole very_easy | 当前新变体 seed 0，使用当前共用工具，未生成独立冻结交付包 | 流程通过，44 次读取对照无差异；初始化约 128 s |
| Blanket easy | 当前冻结包，PBD 初态来自计算能力 12.0 | 本机 8.9 拒绝恢复，见 A04；不能记为 GPU 流程通过 |

具体结果见 `gpu-summary.json`、`gpu_*/report.json`。以上都是短程可运行性检查，未求解任务；重放最终状态的精确哈希不同，不能声称 bitwise deterministic 或已验收所有临界判据。

**standard 独立进程链路：** 对 Interlocked hard 调用实际 `limited_preflight`，完成启动、client hold、收尾、独立 replay 和包内 verifier。预检通过，约 301.5 s；`finalized=1, live_rows=1, physics_steps=10, video_rendered=1`，`grader_error/infra_error/instance_mismatch=0`。保持姿态的短程输入未解题，`success=0` 符合用途。`deterministic/live_matches_replay=0` 如实保留；现有 GPU 协议允许哈希不逐字节相等，这不等于数值轨迹已经按容差验收。见 `standard-preflight.json` 和 `standard-grader.result.json`。

**privileged 正式评分入口：** 使用完整 Dockerfile 构建的审查镜像，执行当前包内 `test.sh`，两遍 replay 完成，约 162.3 s；`instance_ok=1, replays=2, physics_steps=20, grader_error=0, video_rendered=1`。短程输入未解题，`success=0`；`instance_exact=0, deterministic=0` 保留为诊断字段。见 `privileged-grader-qualified.result.json`。这是实际评分代码验证，未启动 Harbor 模型 agent。

初次自定义 privileged 非 root 探针未设置可写 cwd，Nyx 写 `/app/__nyx_cache__` 失败；实际 verifier 模板默认 root，不据此登记产品 bug。改为 `-w /tmp` 后通过；原始 `privileged-grader.log/result.json` 保留，不能误当作最终重跑结果。另一次宿主监控解释器缺 psutil、首次临时审查镜像 FROM 写法失败也分别归档为测试配置问题。

**媒体与工作区：** 9 份导出 MP4（含 standard 收集副本）完整解码及 frame map / manifest 帧数、路径、哈希校验通过，见 `media-validation.json`。这些仅有 2 帧，是短程流程录像，不能代替长视频或完整任务证据。此次 GPU/完整构建观测到的主机内存峰值最高 24.0%，未触发 90% 停止条件；原有 tracked 文件哈希无漂移，本轮临时容器均已退出，保留审查镜像、缓存及证据。

建议优先修 A01、A03，以及目标 GPU 上的 A04 交付与异常分类；A02 补齐动力学初态资格检查；A05 和 G01 按明确的请求/物理过程合同继续验收。性能优化与上述正确性问题分别记账。
