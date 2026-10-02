# Run trials 合并后修复实施与验收

日期：2026-10-01。依据：[工程计划](../rcb/run_trials_post_merge_repair_plan_zh.md)。本页记录实际实现和证据，不把计划验收目标当作已通过结果。

本轮已实现 B04–B09、B11–B13 的修复，并为 B10 增加显式、默认关闭的子步判据版本。代码、模板和新生成包已更新，候选运行镜像已在本机构建。**这不是全任务发布验收：78 项流程矩阵、完整正负评分参考解及 B10 的真实瞬时违规对照仍未完成。** 历史 106 个冻结任务包没有改写，没有发布镜像、调用模型或上传 HF。

## 1. 实际版本与身份

| 项目 | 本轮身份 |
| --- | --- |
| 修改基线 | `6a7c755bb8d8d2a9bb2af8857f9a244c00840c93`；实现尚在工作树 |
| 运行镜像 | `ghcr.io/luigivamper/rcb-topogym:0.2.6-cu128` |
| 本机 image ID | `sha256:245cf0674327d207a3f29f5149b2d6ca015d62607193e827f481a516a12a0a2e`，不是已推送的 registry digest |
| 生成工具 / standard 协议 | tooling v5 / `eai-standard/2.3` |
| 最终公共工具 SHA-256 | `087b695bd68a9435d071798d484747053476624de120ae10ec2e7198a69e1a4b` |
| 最终生成包 | `topogym-repair-qualified-interlocked-hard-i00-{privileged,standard}`，位于本轮证据目录的 `tasks/` |
| 默认 terminal 合同 | 1；版本 2 仅为五种刚体任务的可选候选合同 |

证据总目录：[run_trials_post_merge_repair_20261001](../../runs/test_results/run_trials_post_merge_repair_20261001/README.md)。镜像内部七个关键运行文件与工作树逐字节核对，见 `image-identity.json`。最终生成包全部文件哈希见 `package-identity-qualified.json`；模板对应检查见 `final-package-check.json`。完整修改身份见 `source-identity-final.json`。

首次 Interlocked、子步测试及首次 standard 预检使用了本轮中间工具版本；各报告保留实际 SHA，不能把它们全部说成最终工具的验收。最终 standard 包单独生成和测试。构包复用了历史冻结 hard 实例和已实测的 describe 文本，未伪造新的资产或场景测量。

## 2. B04–B13 修复与关闭矩阵

“修复已验证”限于表中复现边界；“资格待补”表示已有实现但尚未满足工程计划的完整关闭条件。CPU 测试中使用的模拟物理对象不算 GPU 证据。

| 编号 / 原问题 | 修复位置与行为 | 复现 / 回归、实际证据 | 状态与剩余限制 |
| --- | --- | --- | --- |
| B04 非法提交被误报为基础设施错误 | 公共 `load_trajectory`、privileged grader；构建 Session 前检查 NPZ 头、数组、任务、有限值和长度，只捕获明确的提交解析错误 | 新 CPU 回归；最终 privileged 包在非 root、无 GPU 容器处理错误维度，得到 `bad_trajectory=1, grader_error=0`；collector/HF 离线回归通过 | 原复现已修复并验证；实际物理初始化失败仍归 infra，不吞掉宿主 I/O 错误 |
| B05 录像收尾失败丢失已经得到的成绩 | privileged `verdict.json`；standard `replay.verdict.json`、finalize；先原子持久化评分，再关闭编码；父进程可恢复兼容 reward | 两模式的真实子进程 SIGKILL 注入测试通过（物理为替身）；standard 真实 GPU 独立 replay 和媒体收尾验证 | 原提交后丢分窗口已修复；尚未落盘的内存结果无法恢复，未承诺机器断电故障的实测资格 |
| B06 拒绝/终态后动作污染轨迹、提前结束仍按完整周期计时 | `Session.step/save/replay`、`Env.step`、standard server 与 tick journal；只保存实际接受并执行的前缀、每行 tick 和物理时间 | CPU 拒绝动作、可信前缀及 journal 恢复；GPU 3 tick 对应 0.0075 s，终态后五次调用不增计数；多后端短程及 replay | 原计数/回放复现已修复；原生推进到 journal 提交之间仍是 approximate resume，不是物理 exactly-once |
| B07 非整数 dt 被悄悄取整 | canonical standard 协议统一 `control_periods`，执行与记录前拒绝非法周期 | 40 Hz 下 0.0375 拒绝、合法周期和浮点边界通过；真实 server 函数的零变更检查；协议与 GPU standard 预检 | 原复现已修复并验证；保持规定的浮点容差 |
| B08 实例不匹配还能给成功、软体质心比较太弱 | Session 默认严格，两个 grader 都阻止不匹配成功；standard 启动不匹配直接写资格失败并干净退出；新实例记录生成资产哈希及完整软体节点状态 | CPU 等质心不同形变、资产内容与临时目录归一化、真实子进程启动异常至 standard grader 分类检查；GPU 刚体冻结实例匹配、Blanket/IPC 短程 | **资格待补**：旧软体实例缺节点参考时不再允许质心兜底；新软体实例跨进程/三档/跨 GPU profile 的容差资格未完整覆盖 |
| B09 视频首末帧和时间轴不对应真实过程 | 正式 grader 迁移 `RecordingSession`；reset 后开始，按实际物理时间采样，追加真实末态；保留多视角合成、frame map、manifest、解码校验 | CPU 共享录制编码/解码与时间检查；真实 GPU live/replay/partial 视频及末态；最终 standard 独立 replay | 已验证代表性短程；CFR 末态呈现可能补一帧，视频时长不能直接等同物理时间；全任务录像矩阵待补 |
| B10 一个物理 tick 内短暂违规可能漏判 | `rigid_contacts`、world、task base、SimulatorConfig；可选合同 2 保存每子步 contacts 和当时 grasp，要求完整覆盖 | CPU 前子步越阈值、末子步恢复的合成事件；GPU 实际采到每 tick 全部 4 个 solver substep | **未关闭**：尚无真实“越阈值后恢复”物理对照；仅五种刚体允许选用，IPC/FEM 不支持，默认仍为合同 1 |
| B11 客户端先超时、重试重复执行、原生卡死分类错误 | canonical client/server；时限包含排队；operation ID 持久化与查询、重复拒绝；控制步边界检查与 watchdog 标记 | 16 项真实 HTTP 协议测试，含同 ID 不重复执行和过期请求不执行；CPU tick journal 与 watchdog 恢复分类；GPU standard 正常链路 | **故障资格待补**：未在真实 GPU 原生卡死中验证 watchdog；完成操作不缓存整份视频响应，恢复仍遵守已提交 checkpoint |
| B12 不完整 prepare 目录阻塞后续恢复 | `difficulty_eval.prepare_blanket`；独立编号 attempt、锁、最多三次、完整文件/哈希/可读性校验后发布指针 | CPU 不完整旧目录保留、新 attempt、幂等复用、构包回归；既有冻结资产不覆盖 | 原目录存在即失败路径已修复；**准备事务资格待补**：未对真实 Blanket 准备逐阶段强制中断；物理/profile 兼容继续由后续实例构建/预检把关 |
| B13 相同 run_id 清掉其他 workspace 容器 | local 创建/清理统一 workspace、run_id、owner、role，删除前 inspect 复核 | CPU 归属检查；真实 Docker 两个不同 workspace、相同 run_id 容器，只删除目标 workspace 容器 | 原复现已修复并验证；无归属旧容器不自动纳入清理，没有全局 prune |

公共工具位于 [rcb_topogym.py](../../harbor_templates/topogym/common/rcb_topogym.py)，公共协议位于 [rcb_limited.py](../../scripts/eai_standard/rcb_limited.py)，编排位于 [difficulty_eval.py](../../scripts/difficulty_eval.py)。精确接口与兼容边界见 [standard 2.3 合同](../rcb/STANDARD_MODE_2_3.md)。

## 3. 已完成的验收

### CPU、协议与生成产物

- **182 项 CPU 回归通过**：原有 160 项加本轮 22 项边界/故障注入；其中 HF 离线导出 22 项单独运行，其余见 `checks-final.json` 和对应 `*-final.log`。
- **16/16 协议测试通过**：原有 14 项加重复 operation ID、过期请求两项，见 `protocol-qualified.log`。这是本机 HTTP 与可控物理替身测试。
- 仓库静态检查通过，106 个历史冻结包通过原身份检查；与实施基线比较，其 `tasks/` 文件无变化。最终新包的模板身份单独通过，避免拿旧包代替新实现。
- 真实 Docker 所有权隔离测试通过；最终生成 privileged 包的无 GPU 非法输入分类通过。
- 两模式评分后 SIGKILL 注入保留权威成绩，standard 的实际 finalize 合并代码读取落盘结果；不把替身的成功分数当作任务求解成功。
- 最终 standard 包的独立 verifier 容器通过：`finalized=1`、`video_rendered=1`、`infra_error=0`、`grader_error=0`；hold 前缀未解题，正确得到 `success=0`。共完整解码 23 份原始/收集后视频，见 `final-validation.json`、`standard-grader-final/` 与 `media-validation-final.json`。

### 代表性 GPU

硬件 RTX 4090，CUDA cu128，Nyx + compact_lab，非 root 容器；各 GPU 作业串行，监控内存，未触发 90% 停止阈值。测试执行 hold 短前缀，不是机器人完整求解。

| 场景 | 实际检查 | 证据 |
| --- | --- | --- |
| Interlocked hard（中间工具） | 5 控制步 / 50 tick；可信 replay；3 tick 部分周期；三份录像 | `gpu_interlocked/report.json` |
| Interlocked 可选合同 2（中间工具） | 3 tick 提前终止，后五次调用不增加记录；4/4 子步接触快照；reset/replay | `gpu_substep_terminal/report.json` |
| Blanket easy（最终公共工具） | 2 控制步 / 20 tick；replay；3 tick 部分周期；共享录制 | `gpu_blanket_easy/report.json` |
| Knot、Rope、Orbits、Slotted Post Ring（最终公共工具） | 各 1 控制步 / 10 tick；replay；3 tick 部分周期；共享录制 | 各 `gpu_<task>/report.json` |
| 最终 standard 包 | pinned client → 非 root GPU live → 服务退出 → 独立进程 replay → final 与视频 | `standard-preflight-qualified-result.json` 和 `build/topogym-repair-qualified-interlocked-hard-i00/limited/` |

GPU 求解非逐位确定；部分短程 live 与 replay 状态哈希不同，原始值全部保留。该短测只断言生命周期、实际 tick、输出和记录合同，不能由它推出所有物理状态严格等价或任务已经成功。最终 standard 的哈希对照以其 `final.json` 为准。

最终 standard 本次 live/replay 哈希均为 `8a16a5f94a79734d`，实际执行 1 行 / 10 tick / 0.025 s，媒体状态 complete。冻结初态重建的精确哈希不同，按既有刚体位姿容差通过，记录为 `instance_exact=false, instance_matches=true`；没有把容差兼容冒充逐字节复现。

部分 Nyx 退出日志出现 shader cache 导出警告；对应进程退出码和视频解码结果分别记录，没有将警告当作求解成功或忽略实际失败。

## 4. 尚未取得的资格与发布边界

1. 未跑 13 × 3 × 2 的 78 项完整流程矩阵，也未跑 cu130；当前只能交付有明确证据范围的修复候选。
2. Blanket medium/hard、软体新冻结实例跨进程重建、完整正负评分轨迹、FEM 长程显存及真实 GPU watchdog 故障注入尚未完成。
3. B10 保持可选且未关闭，不改变历史成绩或默认终态规则。真实四子步采集不能替代瞬时禁止接触对照，也不等于连续碰撞检测。
4. 未重写 106 个历史包。使用旧包时仍执行其冻结工具；只有新生成 v5 包和匹配运行镜像获得本轮修复。不要直接用旧 run 目录跨版本 resume。
5. 只进行本地构建与离线 HF 导出回归，没有 registry 发布、真实模型评测、HF 上传或旧镜像清理。

## 5. 性能项

本轮优先修正确性，O01–O06 未整体实施。保留合并后的 Knot 向量化和 FEM checkpoint 约束。镜像构建在现有缓存下约 5 秒，见 `image-build.result.json`；这是单次缓存命中结果，不是冷构建或总体加速结论。GPU 短测墙钟包含初始化、reset、三次录制和解码，不能直接当作纯 simulator 吞吐量。

本轮新增 fsync、完整视频解码、实例资产/软体节点检查具有必要开销；尚未完成固定工作量的修复前后性能对比。长期显存、Rope 初始化分段耗时及全任务 prepare image 成本不在本页宣称已优化。
