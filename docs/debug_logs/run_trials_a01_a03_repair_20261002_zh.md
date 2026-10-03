# Run-trials A01 / A03 修复记录

日期：2026-10-02。按用户确认，本轮只修 A01 的无效提交分类和 A03 的汇总/HF 证据对齐。A04 为来自其他 GPU 的冻结 Blanket 初态被正确拒绝，不改初态或兼容规则；A02、A05、G01 不在此次修复范围。

## 改动与行为

| 项目 | 修复位置 | 修复后的行为 |
| --- | --- | --- |
| A01：ZIP/NPZ 解析异常 | `harbor_templates/topogym/common/rcb_topogym.py` 的 `load_trajectory` | 不支持压缩方法或加密条目产生的 `NotImplementedError` / `RuntimeError`，在轨迹解析边界转换为 `InvalidTrajectory`；grader 返回 `success=0, bad_trajectory=1, grader_error=0`，collector 分类为 `invalid_submission`，队列继续 |
| A03：本地汇总 | `scripts/collect_batch_results.py` | 按双模式维护统一证据清单；新 manifest collector 和旧 batch collector 都保留对应 verdict、媒体状态、最终状态、录像帧表和 manifest |
| A03：HF 导出 | `scripts/difficulty_results_hf.py` | `--hf-artifacts standard` 使用同一清单；按原有脱敏规则导出 JSON/JSONL，记录原始与导出哈希，并更新录像 manifest 内指向已导出文件的哈希 |
| 新旧包身份 | 生成器、tooling checker、冻结哈希清单和 normalize | 新包记录 tooling v6；原有 v5 固定为本次改动前的哈希，原 106 包不被原地改写 |

A01 的捕获范围只包含文件解析，没有覆盖 Session 创建和物理回放；真实物理 `RuntimeError` 仍记为 grader error。未改动既有队列分类或成功率分母规则：`invalid_submission` 是完成但无效的提交，现有统计将其单独列出。

## 输出合同

`schema_version=1` 保留兼容，逐 trial 的 `result.json` 和 `_run/metadata.json` 新增 `artifact_contract_version=2`，标明这次文件清单扩展。

| 模式 | 共同文件之外的证据 |
| --- | --- |
| privileged（内部 unlimited） | `verdict.json`、`media.json`；存在时保留 `submission_error.json`、`instance_error.json` |
| standard（内部 limited） | `final.json`、`replay.verdict.json` |
| 两种模式共同 | 原有 reward / MP4 / last PNG / trajectory / episode，以及 `replay.frame_map.jsonl`、`replay.recording_manifest.json` |

仅从 verifier 目录取评分/媒体证据；privileged trajectory 继续从 Harbor 已收集的提交产物目录取。缺文件不合成假证据，不改变评分；模式不适用的文件不会列为缺失。两个错误诊断文件只在存在时导出，正常运行不因缺少它们产生缺证据提示。`--hf-artifacts metrics` 继续只导出 reward 和汇总元数据，不额外导出媒体证据。

本地收集保留原始字节；HF 对文本脱敏/规范化后，`artifacts[name].source_sha256` 记录原始文本文件哈希，`sha256` 记录导出字节哈希。录像 manifest 的 frame-map 哈希同步引用导出的 JSONL，视频字节保持原样。文件仍受原有固定清单、symlink/路径检查和上传快照校验约束。

## 验证

证据在 [本轮测试目录](../../runs/test_results/run_trials_a01_a03_repair_20261002_01/README.md)。本轮没有重跑 GPU 仿真：修改位于解析、收集、导出和包身份层；额外使用上轮真实 GPU 评分产物做离线导出验证。

| 检查 | 结果 |
| --- | --- |
| post-merge 回归 | 24/24 通过；新增 4 个 NPZ 子案例，分别修改 actions/task 条目的压缩方法/加密标志；真实 grader → classifier → 调度循环验证下一项继续 |
| 正常 NPZ / 真实错误类型边界 | `np.savez`、`np.savez_compressed` 正常加载；注入物理启动 RuntimeError 仍返回 grader error |
| HF 回归 | 24/24 通过；新增真实 collector → 离线导出、双模式文件来源、脱敏、源/目标哈希、manifest 引用、历史缺文件与 metrics 测试 |
| tooling / delivery 回归 | 9/9、10/10 通过 |
| difficulty-eval 回归 | 26/27 通过；1 项因下述本轮之前已存在的全局共享文件身份偏差失败 |
| 包身份独立验收 | 实际生成一对 v6 任务包并通过 checker；原有 106 个冻结包 checker 通过，生成结果保存在 `packages/` |
| 已有真实 GPU 产物离线导出 | 复用 Interlocked hard 双模式 verifier 输出，生成 26 个导出文件；两种模式的录像/帧表引用哈希均正确，未执行 HF 网络上传 |

HF 套件第一次运行因沙箱不允许建立测试用 UNIX socket 而失败；允许该本地 socket 后全套通过，日志分别保留。此测试使用 fake Docker / fake Hub，不操作真实远端服务。

**全仓库检查的独立阻塞：** `ci_checks/run_all.sh` 在本轮开始前已新增 calibration isolation 检查，当前 Git blob 为 `11bf337216b1`，共享文件身份表仍期待 `c9303f9421cb`。这导致 `run_all.sh` 及 difficulty-eval 中调用全局 tooling identity 的一个断言失败。开始/结束文件哈希相同，可由本轮 `baseline.json` 核对；此次未改该文件或放宽身份检查。生成 v6 双包的 TopoGym 专用 checker 已独立通过。不能把本轮称为“全仓库 CI 全绿”。

真实 GPU 产物导出测试使用模拟的 Harbor result 包装记录定位已有 verifier 文件，仅验证收集/导出，不代表本轮进行了新的 Harbor 模型任务。privileged 原产物没有 `episode.jsonl`，按缺失记录；没有补造文件。

## 生效范围

新 run 使用当前源码重新 prepare 时会生成 v6 包，包含 A01 修复，并使用新的 A03 收集/导出逻辑。已有 `--resume` run 继续使用它自己的冻结源码与任务包，不能假定自动获得修复；本轮没有覆盖它们、旧录像、已发布 HF 数据或失败上传的冻结快照。无需因这两项修复改变物理后端、Blanket profile 或正式 runtime 镜像版本。
