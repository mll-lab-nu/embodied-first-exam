# 把建文作为 helper：正式入口的双模式小批次操作

本页使用已有正式 pipeline，不另写 smoke 执行脚本，也不上传合成结果。实例是 Cast Coil easy、oracle 参考 seed 0；privileged / standard 双模式，各 K=1，共两个真实 trials。模型 Sol xhigh，每 trial 12 小时、150M input / 10M output，token 仍是运行后判分。小样的作用是验证工程流程，不保证模型解题成功，也不保证几分钟内结束。

先按下方在当前主机完成“维护方准备”，再切换为 helper 运行；接收流程使用另一个目录。同机目录隔离不等于两台机器实测。向第三方派发时再使用第 6 节的独立 release。

## 0. 本轮已经执行到哪里

- 正式 `setup_agent_batch.sh` 已在本机安装通过：Python 3.12.13、Harbor 0.23.0 及固定补丁、私有 Node 22.14.0 / Codex 0.157.0。
- 正式 plan 已生成下文 `RUN`：1 个实例、2 个模式，agent 预算 43200 秒。
- 正式 prepare 已尝试，因 GPU 空闲约 11006 MiB、低于默认 12000 MiB，被显存保护拦住。没有运行物理或模型，没有生成可发布的完整包；已保留计划，可以直接 resume。
- 尚未使用真实 HF 凭据进行上传、下载，当前 HF 目录不应被描述为“已有本次结果”。

验证记录见 [summary.json](../../runs/test_results/native_helper_20261004/summary.json)：helper/native/HF/交付共 84 项通过，包含下载固定 revision、只读权限、文件篡改、上传响应丢失后的幂等重试。difficulty 的 29 项中 27 项通过，2 项被既有 `PROTOCOL.md` 与上游固定 blob 不一致拦住；本轮未修改该协议文件。上述回归不代表真实物理、模型或 HF 已通过。

## 1. 一次设置本机变量和凭据

下列代码块在同一个 Bash 终端顺序执行。HF token 使用此前提供的那一份即可，不要写入命令文本；`store` 会隐藏输入。若已有私有 token 文件，直接把 `HF_TOKEN_FILE` 指向它并跳过 store。

```bash
set -euo pipefail
umask 077
SOURCE_REPO=/home/jianwen/topogym
MAINT_WORK=/home/jianwen/helper-work/maintainer
HELPER_WORK=/home/jianwen/helper-work/helper
ACCEPT_WORK=/home/jianwen/helper-work/acceptance
CONTROL=/home/jianwen/helper-work/control
RUN=topogym-solxh-jianwen-smoke-20261004
B=topogym-solxh-jianwen-smoke-20261004
HF_TOKEN_FILE="$HOME/.config/eai/helper-hf.token"
CONFIG="$HOME/.config/eai/$B.json"
mkdir -p "$MAINT_WORK" "$HELPER_WORK" "$ACCEPT_WORK" "$CONTROL"
cd "$SOURCE_REPO"

# 此主机已完成安装；新机器首次执行下面这一行。
# bash scripts/setup_agent_batch.sh
export PATH="$SOURCE_REPO/.venv-agent-batch/bin:$SOURCE_REPO/.tools/agent-batch/node_modules/.bin:$PATH"
export TOPOGYM_EVAL_PYTHON="$SOURCE_REPO/.venv-agent-batch/bin/python"

if [ ! -f "$HF_TOKEN_FILE" ]; then
  python scripts/difficulty_hf_auth.py store --file "$HF_TOKEN_FILE"
fi

python scripts/check_agent_batch_hf.py --check-access --access write \
  --repo-id eai-v2-internal/helper-uploads --helper jianwen --batch "$B" \
  --hf-token-file "$HF_TOKEN_FILE" --receipt "$CONTROL/$B.hf-access.json"
```

这一步只检查真实私有库及写权限，不启动 GPU 或模型。失败时先解决凭据/权限/网络问题，不创建其他 dataset 作为替代。HF token 不用于模型认证；模型使用你本机的 `~/.codex/auth.json`，或在第 3 节改用 API env 文件。

## 2. 维护方：准备和发布两个冻结任务包

先确认 GPU 有至少 12000 MiB 空闲，且利用率低于 10%。不要为腾显存停止其他人的任务，也不要把阈值调低来绕过检查。原 source 快照和计划已保存，重试 prepare 不重新抽 seed。

```bash
cd "$SOURCE_REPO"
PREP="$MAINT_WORK/runs/difficulty_trials/$RUN"
nvidia-smi --query-gpu=index,memory.free,memory.total,utilization.gpu --format=csv

# 本机已有计划，跳过；新实验只用同一正式入口筛选任务/难度。
if [ ! -f "$PREP/manifest.lock.json" ]; then
  bash bash_scripts/run_difficulty_trials.sh --backend local \
    --run-id "$RUN" --phase plan --work-dir "$MAINT_WORK" \
    --setting configs/sweeps/helper_oracle_reference.yaml \
    --tasks cast_coil --difficulties easy
fi

bash bash_scripts/run_difficulty_trials.sh --backend local \
  --run-id "$RUN" --phase prepare --resume --gpu-device 0 --work-dir "$MAINT_WORK"

bash bash_scripts/run_difficulty_trials.sh --backend local \
  --run-id "$RUN" --phase preflight --resume --gpu-device 0 --work-dir "$MAINT_WORK"

cat > "$CONTROL/$B.upload.json" <<EOF
{"type":"hf","repo_id":"eai-v2-internal/helper-uploads","prefix":"helpers/jianwen/$B"}
EOF

python scripts/publish_agent_batch.py --run "$PREP" \
  --batch "$B" --helper jianwen --repetitions 1 \
  --task-base topogym-cast-coil-easy-o00 \
  --upload-spec "$CONTROL/$B.upload.json"

ASSIGNMENT="$SOURCE_REPO/configs/helper_batches/$B.json"
cp -n "$ASSIGNMENT" "$CONTROL/$B.original-assignment.json"
```

prepare/preflight 可能需要构建镜像并执行真实 GPU 检查。任一步失败就停止，读该 run 下的日志；不补写成功文件。发布器拒绝覆盖已有不同任务包和重复派单。若派单已经成功发布，继续第 3 节，不重复执行发布命令。源码物理身份若已经改变，需要以新 RUN/B 制作新发布，不能修改原计划来消除不一致。

这里 K=1 仅写在小样 assignment；正式全量仍由原 YAML 指定 K=3。普通任务失败得 0 也能形成完整交付，基础设施失败或缺少 token 用量不能通过完整验收。

## 3. 你作为 helper：配置一次，然后执行

当前同机测试使用已经具备冻结任务和镜像的 `$SOURCE_REPO`。第三方 release 的使用者把路径替换成自己的 release checkout；命令入口和输出结构相同。

```bash
cd "$SOURCE_REPO"
if [ ! -f "$CONFIG" ]; then
  bash bash_scripts/run_helper_batch.sh --init-config --config "$CONFIG" \
    --assignment "$ASSIGNMENT" --jobs-dir "$HELPER_WORK/jobs/agents" \
    --auth-file "$HOME/.codex/auth.json" --gpu 0 --hf-token-file "$HF_TOKEN_FILE"
fi

# 首次认证在前台；通过后统一脚本自动转后台。
bash bash_scripts/run_helper_batch.sh --config "$CONFIG"

bash bash_scripts/run_helper_batch.sh --config "$CONFIG" --phase status
tail -f "$HELPER_WORK/jobs/.helper-pipeline/$B/workflow.log"
```

`tail -f` 的 Ctrl-C 只退出查看日志。统一流程会核对工具/任务/镜像、做一次模型 canary、运行两个 trial、检查完整性与用量、扫描、生成 MANIFEST、打包并上传三文件。配置生成不会覆盖已有文件；需要 API 认证时，在第一次 `--init-config` 中用 `--env-file /private/eai.env` 替换 `--auth-file`。

如果只在最后上传阶段失败，修正网络后执行：

```bash
bash bash_scripts/run_helper_batch.sh --config "$CONFIG" --phase upload
```

这只重试上传，不重跑模型。若 trial 因基础设施问题中断，保留目录并检查状态，由维护方另发 rerun 派单。不要重新创建同名 job 或手改 verdict。

## 4. 在 HF 上确认结果

helper 工作流成功上传后会打印包含固定 HF commit 的 URL，并写 `hf-receipt.json`。也可以再次验证实际远端三文件：

```bash
python scripts/check_agent_batch_hf.py --assignment "$ASSIGNMENT" \
  --folder "$HELPER_WORK/jobs/upload_$B" --verify-uploaded \
  --hf-token-file "$HF_TOKEN_FILE" --receipt "$CONTROL/$B.hf-verified.json"

cat "$HELPER_WORK/jobs/.helper-pipeline/$B/hf-receipt.json"
```

浏览器目录：

`https://huggingface.co/datasets/eai-v2-internal/helper-uploads/tree/main/helpers/jianwen/topogym-solxh-jianwen-smoke-20261004`

目录应有 `${B}__jianwen.tar.gz`（即 batch 名后接 `__jianwen.tar.gz`）、同名 `.sha256` 和 `MANIFEST.md`。网页是私有的，需要登录有该 dataset 读权限的 HF 账号。脚本拿到写 token 可以上传，并不等于当前浏览器登录账号已加入组织；没有权限时目录链接可能显示不可访问。

## 5. 我们作为接收方：独立下载与验收

同机小测试可以沿用测试 token 的实际读权限；正式接收请将 `RECEIVER_TOKEN_FILE` 指向我们自己账号的只读凭据。用另一个目录下载，不读取 helper 的 jobs，也不以归档自带 assignment 作为可信任务单。

```bash
cd "$SOURCE_REPO"
RECEIVER_TOKEN_FILE="$HF_TOKEN_FILE"
bash bash_scripts/import_helper_results.sh \
  --assignment "$CONTROL/$B.original-assignment.json" \
  --work-dir "$ACCEPT_WORK" --require-complete \
  --hf-token-file "$RECEIVER_TOKEN_FILE"

cat "$ACCEPT_WORK/accepted/$B/receipt.json"
cat "$ACCEPT_WORK/accepted/$B/hf-source.json"
cat "$ACCEPT_WORK/accepted/$B/review/README.md"
```

第一次下载固定 main 当时的 commit，三文件全部从同一 revision 读取；中途 main 更新不会混入另一版本。重复执行会复核已下载内容和同一版本。之后可以离线验收，不再使用 HF 凭据：

```bash
bash bash_scripts/import_helper_results.sh --phase import \
  --assignment "$CONTROL/$B.original-assignment.json" \
  --work-dir "$ACCEPT_WORK" --require-complete
```

另一台接收机只需接收工具及 HF SDK，可设置 `TOPOGYM_RECEIVER_PYTHON` 指向安装了 `huggingface-hub==1.33.0` 的独立 Python。离线 import 不要求 SDK、GPU、Harbor 或模型认证。网站接通仍在独立后续阶段，本流程不会向公开网站库转传原始归档。

## 6. 向第三方交付独立 release

本机完整流程通过后，取得官方 `SHARING_RUNS.md` 原文及来源 commit，再导出包含上述 assignment 的 release。当前本机和缓存分支没有这份文件，SSH 更新失败；不能拿 §3b 片段冒充官方原文。导出器遇到缺手册会明确拒绝完整 release；`--runtime-only` 只用于分发/检查工具，不能运行实验派单。

```bash
cd "$SOURCE_REPO"
RELEASE_DIR="/home/jianwen/helper-releases/$B"
OFFICIAL_MANUAL=/path/to/upstream/docs/SHARING_RUNS.md
python scripts/export_native_helper_release.py \
  --assignment "$ASSIGNMENT" --manual "$OFFICIAL_MANUAL" --output "$RELEASE_DIR"
python scripts/export_native_helper_release.py --verify --output "$RELEASE_DIR"
```

导出器保留官方手册原文及 hash，附带待合入的 `docs/SHARING_RUNS_3b.md`。release 包含所选 tasks、dataset、派单、运行依赖和身份清单，不包含私有仓库 Git 历史或额外 oracle 解题开发代码。默认不 push、不上传镜像。

在我们约定的 helper 仓库中审查、提交这些文件，提供固定 commit；为 helper 分发清单中绑定的全部镜像。helper clone 后先安装工具/导入镜像，再运行第 3 节相同命令。它首次 prepare 还会检查完整 release 文件清单，防止复制漏文件或修改依赖。维护方保留原始 assignment；小样证明通过后再发布全量 60 包、180-trial 派单。
