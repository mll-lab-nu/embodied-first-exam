# Helper：接收任务、执行和交回完整记录

2026-10-04：本流程已有代码与 CPU 合同测试；真实独立 GPU 主机到接收机器、目标 HF dataset 和外部评测网站的联合演练尚未完成。正式放行仍需完成该演练。入口是 `bash_scripts/run_difficulty_trials.sh`（trials）；源码发行包还提供根目录同名入口。

## 维护方先完成派单

在冻结的源码版本上编辑 [派单样例](../../configs/helpers/example_shared_folder.json)。样例只含 Cast Coil easy 的一个实例、两种模式，每次 agent 432 秒，用于交付试跑。正式任务应明确指定 task、easy/medium/hard 子集、limited/unlimited 子集、样本数、seed、模型、Codex 版本、effort、每次 agent 预算、CUDA 配方和 helper ID。预算不包括构建、预检、评分时间。`mirror=required` 是推荐交付要求。当前每批只有一个执行队列、同一时刻一个正式 trial；不要重复启动同一个 batch 来增加并行度。

```bash
# 复制并编辑样例，使用新的 batch；不要放密钥。
cp configs/helpers/example_shared_folder.json /data/helper-spec.json
bash bash_scripts/run_difficulty_trials.sh helper assign \
  --spec /data/helper-spec.json --work-dir /data/dispatch
```

输出 `/data/dispatch/assignments/<batch>/assignment.json` 及其 SHA256。维护方保留原件，通过可信渠道把原件交给 helper。任务单冻结具体实例、trial ID、源文件摘要和实验配置；helper 首次执行也核对，不会重新抽样。

维护方从**同一份源码**制作发行包；此后不要修改包内源码再使用原任务单。

```bash
python3 scripts/difficulty_release.py bundle --output /data/topogym-helper-source.tar.gz
sha256sum /data/topogym-helper-source.tar.gz > /data/topogym-helper-source.tar.gz.sha256
```

把源码包、源码包校验文件、assignment 和此手册发给 helper。若采用发布的控制镜像，也必须是对应的固定 digest，不能使用浮动 tag。工作区有未提交修改时仅给 commit 不足以复现，源文件摘要才代表实际派单字节。任务结果包不重复携带整个源码仓库；维护方另行保留此发行包。

HF 路线在生成 assignment **之前**把 spec 的 upload 改成 `{"type":"hf","repo_id":"组织/私有数据集","prefix":"helpers"}`。dataset 需事先存在并且是私有库；封包后不能改目的地来冒充原派单。共享文件夹路线无需 HF。

## Helper 收到后

宿主要求见 [Docker 启动手册](docker_quickstart_zh.md)：Linux x86_64、本机 Docker Engine/CLI + Buildx、NVIDIA 驱动/Container Toolkit、可访问依赖源和模型服务的网络、足够磁盘。默认 Docker 后端不要求宿主安装项目 venv。初次运行会构建镜像，耗时单独计算。解压并进入 `topogym`，以下示例约定：

- assignment：`/data/assignment.json`；batch：`helper01-coil-easy-smoke`。
- 工作目录：`/data/helper-work`；GPU：宿主 `0`。
- 以后所有操作都使用这份源码和同一工作目录。

先核对收到的源码包 SHA256。认证选择必须在任务单允许范围内：

```bash
# 订阅认证：按终端提示登录一次；登录保存在工具管理的私有目录。
bash bash_scripts/run_difficulty_trials.sh auth login --device-auth

# 可选：只验证派单与源码，不构建仿真镜像、不调用模型。
bash bash_scripts/run_difficulty_trials.sh \
  --assignment /data/assignment.json --phase plan \
  --work-dir /data/helper-work

# 如果执行过上面的 plan，all 加 --resume；直接 all 首跑则去掉 --resume。
bash bash_scripts/run_difficulty_trials.sh \
  --assignment /data/assignment.json --phase all --resume \
  --auth subscription --gpu-device 0 --work-dir /data/helper-work
```

API 认证可以把最后一条的 `--auth subscription` 换成 `--api-key`，按提示隐藏输入，或用 `--auth api-key --env-file /private/model.env`。封包扫描还要用到运行时的密钥；建议保留私有凭据来源，不将它放在 jobs/runs 或发行源码里。无须再传 `--tasks`、`--model`、预算或 seed；任务单拥有这些设置，冲突会被拒绝。

`all` 依次核对源码和任务单、冻结本批源码、准备镜像、检查宿主环境、生成任务包、运行全部实例预检、执行认证 canary、运行任务单中的 trials、收集汇总。canary 不计入正式 trial 数。当前 prepare/preflight 仍为选中实例生成并检查两个模式的任务包；实际模型调用只执行任务单授权的模式。

原始位置：

| 路径（相对 work-dir） | 内容 |
|---|---|
| `runs/difficulty_trials/<batch>/` | assignment、manifest、源码/执行/镜像身份、任务包、预检、资源与时间记录、summary、trials.jsonl |
| `jobs/difficulty_trials/<batch>/<trial-id>-a001/` | 全部 Harbor 原始记录、agent 日志、代码、verifier、已有轨迹和录像 |
| `jobs/difficulty_trials_mirror/<batch>/` | 独立容器保留的 agent 记录镜像、历史改写分段 |
| `logs/` | 控制器和环境检查日志；封包只选本批引用的日志 |

某些失败发生在生成录像/轨迹之前；完整交付保留实际产生的全部文件，不把缺失文件伪装成已生成。mirror 是轮询记录备份，保留观测到的追加/改写/删除事件，不是防恶意主机的密码学审计证明。

## 中断、恢复与重跑

中断后保留整个工作目录。相同 assignment、源码和工作目录运行 `--phase all --resume`，已启动的 attempt 保留，未启动项可继续。它不会自动重新执行失败 attempt。

需要重跑时，由维护方出具引用原 assignment 摘要的重跑单：

```bash
# 维护方命令；trial ID 来自 assignment 的 manifest.trials。
bash bash_scripts/run_difficulty_trials.sh helper retry-plan \
  --assignment /data/assignment.json \
  --trial-id d08-easy-s00-limited --reason 'host interrupted; retry approved' \
  --work-dir /data/dispatch

# helper 使用收到的重跑单；旧 a001 保留，获准的失败 trial 产生 a002。
bash bash_scripts/run_difficulty_trials.sh \
  --assignment /data/assignment.json --retry-plan /data/retry.json \
  --phase all --resume --rerun-incomplete --auth subscription \
  --gpu-device 0 --work-dir /data/helper-work
```

canary 失败需要在重跑单中显式列出 `--trial-id canary`。首版重跑针对不完整/基础设施失败项，已完成的 solved/unsolved 等终态不会被重跑选项覆盖。重跑单摘要负责一致性，文件必须由双方通过可信渠道交接。

## 执行停止后封包

等控制器退出后运行，导出器会检查本批锁和 Docker 写入者。订阅模式自动读取工具私有登录及本批刷新备份；API 模式显式提供原凭据文件。保留原凭据直到封包完成，否则扫描不能证明检查了本次使用的密钥。

```bash
# 订阅模式；可加 --redact-pii 清除 jobs/mirror 文本内邮箱及登录 account_id。
bash bash_scripts/run_difficulty_trials.sh helper export \
  --run-id helper01-coil-easy-smoke --work-dir /data/helper-work

# API 模式的对应命令：
bash bash_scripts/run_difficulty_trials.sh helper export \
  --run-id helper01-coil-easy-smoke --work-dir /data/helper-work \
  --env-file /private/model.env
```

Docker 导出由可信控制器以 root 读取本批可能为 root 私有的记录，成品所有权交回运行用户；agent 不获得额外权限。导出复制本批实际产生的原始 jobs、镜像记录、任务包和元数据，重建逐项账本，在 staging 中扫描和脱敏，不改写原始运行目录。扫描覆盖已加载密钥、常见 token/JWT、ZIP/NPZ 成员和 gzip 内容；不执行 pickle/agent 代码。未知密钥或嵌套压缩内容不能被承诺完全识别。不可读文件、路径越界、扫描失败、必要 mirror 缺失、复制过程中原文件变化会阻止交付。二进制含敏感值时阻止封包，不静默破坏轨迹。

如果失败，保留日志和工作目录供维护方诊断；不要上传 `.preparing-*`。失败 staging 可能含尚未脱敏内容；工具只把通过验证的成品放入下列 bundle-ID 目录。凭据扫描规则补齐或收集问题修复后再次导出。

```text
/data/helper-work/outgoing/upload_<batch>/<bundle-id>/
  <batch>__<helper>__<bundle-id>.tar.gz
  <batch>__<helper>__<bundle-id>.tar.gz.sha256
  MANIFEST.md
```

终端返回这三个绝对路径和 `evaluation_complete`。未完成的批次可以交部分包，明确为 incomplete；稍后补交是新的 bundle ID，保留旧包。相同证据重复导出复用原成品。

共享文件夹路线：把这**三个文件**放到同一个独立子目录，传给维护方 batch、bundle ID、文件名和 SHA256。无需上传源码、缓存、凭据或整个主机工作目录。

HF 路线：

```bash
# 把输出中的实际 tar.gz 路径代入；凭据置于源码仓库外的私有文件。
bash bash_scripts/run_difficulty_trials.sh helper upload \
  --archive /data/helper-work/outgoing/upload_BATCH/BUNDLE/ARCHIVE.tar.gz \
  --work-dir /data/helper-work --hf-token-file /private/hf-token
```

`--hf-dry-run` 只验包和打印目的地，不读 token、不上传。网络中断后重跑同一 upload 命令，核对远端已有文件、只补缺项；不会重新调用模型。远端目录为 `<prefix>/<helper>/<batch>/<bundle-id>/`，三个文件校验通过后才写 `UPLOAD_COMPLETE.json`，本地回执在 `helper_upload/<bundle-id>/receipt.json`。`upload_complete=true` 表示传输完成，`evaluation_complete` 单独表示评测终态是否齐全。

不要用旧 `--results_to_hf` 指标导出代替 helper 完整交付。接收方操作见 [异机验收手册](helper_import_zh.md)。
