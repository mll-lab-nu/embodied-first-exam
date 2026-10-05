# 维护方：在另一台机器验收 helper 结果

接收机器只需要对应发行版本的工具、收到的三个成品文件、维护方自己保存的 assignment 原件。验收不需要 helper 原目录、模型凭据、模型访问权或 GPU，不执行收到的 `gen.py`。归档 SHA256 与任务单摘要检查完整性和一致性，不构成对恶意 helper 的签名或独立物理正确性证明。

## 接收与导入

从共享文件夹或 HF 下载 tar.gz、同名 `.sha256`、`MANIFEST.md`，保存在同一个目录，每个 bundle 独立一层。HF 路线先确认该 bundle 有 `UPLOAD_COMPLETE.json`；还要执行下面本地校验，不以远端存在标记替代验包。保存我们派出的原 assignment，不能只信包内 helper 提供的副本。

```bash
# 在对应发行源码目录执行。默认 Docker；不需要 GPU 或模型登录。
bash bash_scripts/run_difficulty_trials.sh helper verify \
  --archive /data/received/BUNDLE/ARCHIVE.tar.gz \
  --assignment /data/dispatch/assignments/BATCH/assignment.json \
  --require-complete

# import 自身也会完整验包，平时可直接执行这一条。
bash bash_scripts/run_difficulty_trials.sh helper import \
  --archive /data/received/BUNDLE/ARCHIVE.tar.gz \
  --assignment /data/dispatch/assignments/BATCH/assignment.json \
  --require-complete --work-dir /data/acceptance
```

接收机完全离线或没有 Docker，可以加 `--backend local`；Python 3.10+ 标准库即可验包和导入，不安装 TopoGym 仿真依赖：

```bash
TOPOGYM_EVAL_PYTHON=python3 bash bash_scripts/run_difficulty_trials.sh helper import \
  --backend local --archive /data/received/BUNDLE/ARCHIVE.tar.gz \
  --assignment /data/dispatch/assignments/BATCH/assignment.json \
  --require-complete --work-dir /data/acceptance
```

默认 Docker 路线仍需本机 Docker 和已存在或可构建的控制镜像；“无 GPU 验收”不表示可凭空离线构建镜像。接收端采用对应发行工具，helper 端冻结过的绝对路径不会被当成当前机器路径。

`import` 会校验外层 SHA256、归档成员类型/路径、逐文件大小和哈希、bundle 身份、原 assignment、源身份与准备好的任务包、显式 trial 列表与路径映射。它从原始 Harbor result/reward 重新分类并核对账本和汇总，禁止用汇总声称不存在的成功；结果包内所有 attempt 保留。验证和解包限制规模，并拒绝符号链接、硬链接、设备文件、重复成员和 `../` 越界。

成功后：

```text
/data/acceptance/imports/<batch>/
  index.json                         # 本批已收 bundle 与不可覆盖的终态原始证据
  <bundle-id>/
    receipt.json                     # 验收回执
    payload/
      BUNDLE.json
      inventory.json
      delivery/                      # assignment、helper manifest、路径映射、扫描/脱敏记录
      runs/difficulty_trials/<batch>/
      jobs/difficulty_trials/<batch>/
      jobs/difficulty_trials_mirror/<batch>/
    reports/
      README.md                      # 所有 trial/attempt 的入口
      trials/00001.md                 # 链接该 attempt 的全部已收到文件
      site-input.json                # 外部评测网站适配器输入描述
```

重复导入同一包返回已有回执并重新核对现有 payload。补交包导入新的 bundle 目录，保留之前收到的证据；如果它改写或省略此前已接收的**终态 job 文件**，导入失败。不完整 attempt 的后续收集可以增加证据，新 attempt 不覆盖旧目录。

## 看什么才算验收通过

| 检查 | 含义 |
|---|---|
| 命令退出码 0、`import_complete=true` | 包已校验并导入 |
| `expected_assignment_verified=true` | 与我们保存的原任务单逐项一致；应始终提供 `--assignment` |
| `summary.evaluation_complete=true` | 每个授权 trial 的最新 attempt 都到达有效终态 |
| `summary.planned_trials/completed_trials/status_counts` | 派单总数、终态数量、各状态数量；对照计划检查 |
| `reports/README.md` 与逐项链接 | 人工查看代码、对话、评分、已有录像/轨迹，以及必要的异常与脱敏记录 |

`solved`/`unsolved` 都是完成的评测；`not_evaluable`/`invalid_submission` 也算已有终态，但不纳入正常 solved/unsolved 成功率分母。`pending`、`blocked_preflight`、`interrupted`、`infra_failed` 等不算完成。因此“全部跑完”与“全部解题成功”是两个不同结论。

如果要先收中断证据，去掉 `--require-complete`；回执仍明确 `evaluation_complete=false`。读完报告后维护方可以生成受限 retry-plan，再让 helper 补跑。没有提供 `--assignment` 时只能获得包内自洽性检查，回执明确原任务单未验证，不能据此通过正式派单验收。

导入报告直接使用相对路径，不改写原始 Harbor `result.json` 中的历史绝对路径。`trial_task_paths.original_task()` 根据 `delivery/path-map.json` 找到本包冻结任务文件，并验证哈希；`write_task_results.py` / `regrade_trials.py` 已接入该定位方式。普通离线验收无需重新评分；独立重放/重新评分仍需要相应仿真环境、GPU 与发行源码，且属于额外验证，不能把导入成功说成物理重放成功。

## 外部评测网站边界

当前仓库提供完整 Markdown 审查入口和 `site-input.json`，保留原 job/trial/task 名称，供网站 adapter 注册/重建页面。尚未拿到实际网站 importer 的代码与入口，故没有宣称已接通网站的 `hosts.<name>.local`、`state/runs` 或旧 `jobs/agents` 约定。实际网站注册与页面重建仍需在那个仓库实现并验收；当前可以直接在另一台机器验完整包和审查全部已产生文件。

相关命令和失败处理见 [Helper 操作手册](helper_quickstart_zh.md)，工程范围与放行门槛见 [工程计划](helper_delivery_engineering_plan_zh.md)。
