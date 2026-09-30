# 可解性证明

统一保存已完成的 policy、IK 规划与模拟器实际成功证据。目前收录 **3 项任务、7 个变体实例**，均从默认 home 连续执行到原 Task 的 `task_success=True`，并通过独立逐 tick 复核。

| 任务 | 已验收变体 | 证明与完整证据 |
| --- | --- | --- |
| Cast Keyhole | easy / F1、medium / F2、hard / F3，3/3 | [证明目录](cast_keyhole/README.md) |
| Cast Coil | easy、medium、hard，3/3 | [证明目录](cast_coil/README.md) |
| Hedgehog in Cage | medium 已验收，三档总体 1/3；easy/hard 待补齐 | [证明目录](hedgehog_in_cage/README.md) |

[机器索引](catalog.json)记录批次、数量、清单及哈希。每个变体目前只覆盖默认参数、seed 0、CPU 双精度和接触触发的 `contact_weld_v1` 辅助抓持；Coil/Keyhole 使用 ALOHA + EE_ABS，Hedgehog 使用 Panda/Robotiq + JOINT_ABS。显式采用 25 ms World tick / 40 solver 子步，40 Hz action 与 Task/assist 检查，积分子步 0.625 ms；无 RGB 或视频。证明绑定各次冻结源码与配置，不扩大为整个随机参数域、默认 400 Hz 检查时序、纯摩擦抓持或连续时间无穿透资格。

[现有 run 与下一批证明候选](run_candidates.md)逐项核对其余任务可复用的运行、当前缺口和执行顺序；候选与历史成功不计入上表的已验收数量。

## 目录约定

```text
solvability_proof/
  README.md                         # 全部已验收证明的入口
  catalog.json                      # 机器可读索引
  <task_id>/
    README.md                       # 任务证明入口
    <validation_batch>/
      README.md                     # 结果、解法、范围、复核命令
      summary.json                  # 使用归档内路径的逐变体索引
      archive_manifest.json         # 每份证据的原路径、字节数、SHA-256
      archive_validation.json       # 归档一致性检查结果
      evidence/
        runs/<original_run_id>/     # 完整成功运行：policy 源码、配置、状态、action、报告
        qualification/<run_id>/     # 必要的前置资格证据，单独标注原始状态
        supporting/                 # 独立复核代码、相关检查和原说明快照
        <original_summary>.json     # 原汇总，保持原始字节
```

实际归档使用独立文件副本；已逐文件核对 SHA-256，并验证冻结源码清单及报告引用的数值证据哈希。原 `runs/test_results/` 目录保留，已有代码与历史引用继续有效。原报告、冻结源码中的路径和身份不改写；访问副本使用本目录的 `summary.json`，原路径与副本的对应关系见 `archive_manifest.json`。`supporting/` 中的说明快照保留原文，其相对链接仍以原位置为上下文。

完整状态和源码证据保存在本地 `evidence/`，与 `runs/` 一样不自动提交 Git；README、索引、清单和验证结果可纳入版本管理。传递完整证明时必须同时携带 `evidence/`。运行依赖和 Python 虚拟环境不在归档中；归档中的逐 tick 数值状态用于复核，不等同于可任意继续物理执行的引擎 checkpoint。

## 收录规则

新增证明沿用 `<task_id>/<validation_batch>/`，每个变体记录具体 seed、资产/实例身份、配置、冻结 policy/Task 源码、全部 action 与 tick 状态、真实 Task 结果和独立复核。批次目录一经验收保留原始证据，新执行写新目录，再更新索引；不覆盖既有运行。

计入已完成须同时具有完整连续机器人执行、实际 `task_success=True` 和通过的独立复核。几何/IK 候选、旧版本 demo、初始化验收及失败尝试保留其原范围。Keyhole 必需的旧资格运行已单独归档，仍保留 `task_success=False`，不计入上述成功次数；Hedgehog 的旧资格运行同样保留原始 false。

其余任务的已有研究与历史执行入口见[任务说明](../docs/develop/tasks/README.md)和[解法及 action / IK 研究](../docs/develop/tasks/task_variant_solutions_action_ik_zh.md)。例如 Lock 当前完整观测流程仍有正式 terminal 资格缺口，Claws 当前新版及 Hedgehog 未列出的变体仍无本目录完整成功证明，均不并入这里的通过数量。
