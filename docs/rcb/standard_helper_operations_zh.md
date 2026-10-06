# 标准 helper batch：实施状态与固定 oracle 实例 K=3 操作手册

> 2026-10-06 回退说明：本文记录的是扩展 helper runner 的历史方案或发布状态。当前开发仓库已恢复原版 `run_agent_batch.sh`，新增派单/自动准备/封存入口已归档；下文命令不再直接适用于当前 checkout。已有固定 helper release 和实验记录未修改。

本页对应 `standard_helper_pipeline_engineering_plan_zh.md` 的实际代码。使用 **`scripts/run_agent_batch.sh`**，保留 `jobs/agents/<batch>-<mode>-<task>/` 和 sibling `agents_mirror/`。旧 difficulty 入口负责维护方准备实例，helper 不必用它调度 rollout。

最新交付安排：上游指定 `SHARING_RUNS.md` 为静态 helper 手册，本页作为工程操作说明；取得官方原文后将 TopoGym 入口补入其 §3b。第三方 helper 使用另行发布的可访问 release，不克隆私有 `robot_coding_bench`。下一阶段开发和实测见 [独立 release 与 HF 小测试计划](helper_release_and_hf_smoke_plan_zh.md)。

当前自助小批次和接收 CLI 见 [helper_native_cli_zh.md](helper_native_cli_zh.md)。已新增 `--init-config`、HF `--check-access`、`export_native_helper_release.py` 和独立 `import_helper_results.sh`；本机工具安装/实例规划已通过，GPU prepare 尚被显存保护拦住，尚无真实 HF 上传结果。

## 1. 实验口径和目前可以声称的完成范围

用户 2026-10-04 最新指定：排除 Knot、Slotted Post Ring、Orbits，每个任务、每档使用 oracle 测验的固定 seed，同一实例重复三次，`K=3`。当前配置是 [helper_oracle_reference.yaml](../../configs/sweeps/helper_oracle_reference.yaml)：10 个任务 × easy/medium/hard × privileged/standard × 3 = **180 trials**，分为 **30 个实例、60 个任务包和 60 个 jobs**。Very-easy/easier 不在本次三档口径中；旧 [oracle_reference.yaml](../../configs/sweeps/oracle_reference.yaml) 保留为 13 任务的历史预设。

具名 variation 分别是 `easy`、`medium`、`hard`，seed 都是 0；不走 `seeded` 的场景参数抽样。来源是任务 oracle 入口的默认 seed 和 `docs/progress/current_zh.md` 的各档记录。固定 seed 不等于固定全部配置：源码、环境 profile、冻结状态、资产和镜像还要一起锁定。任务准备使用当前 v15 的公开环境 profile，不把历史 v12 的成功自动转移过来。

本次排除的三个任务不会出现在派单中。其余任务发布前仍须核对实际实例与目标 oracle 配置/证据；不能只核对整数 seed。

模型由维护方在上述 YAML 的 `native_batch` 中一次指定，目前为 `openai/gpt-6-sol`、`xhigh`；发布器自动继承，helper 不重填。模型 ID 与 effort 见 [OpenAI 官方模型页](https://developers.openai.com/api/docs/models/gpt-6-sol)，具体 helper 账户仍须通过真实 canary。

预算均为**每个 trial**：agent 43200 秒（12 小时）、input 150000000 tokens（含缓存）、output 10000000 tokens（含 reasoning）。Harbor 对 agent 时间执行超时；镜像构建、环境准备和 verifier 收尾另有时间，不保证整个 job 在 12 小时内结束。token 采用仓库协议的运行后判分：超过任一上限标为 `over_token_budget`，调整后得分为 0，保留原始 verifier 得分；用量缺失标为 `usage_missing`，不能通过完整验收。**token 阈值不是实时 API 消耗硬上限**，不会在达到阈值的一瞬间终止模型。原始 result/reward 不改写，网站以后须读取验收后的分数与预算。

v16 的 `success=0, success_pending_review=1` 在 native helper 中记为 **`pending_review`**，表示运行结束、成功资格待人工复核。它不计入 solved/unsolved 分母，汇总中的 `success` 为 null，`raw_success=0` 保留评分器原值；不会被自动选入 rerun。身份、runtime binding、预算和交付完整性检查继续生效：用量缺失仍为 `usage_missing`，超预算仍为 `over_token_budget`，同时保留原始待审标志。

待审结果可按现有完整性规则封包、上传和接收；`evaluation_complete` / `delivery_complete` 不表示人工审批通过。summary、MANIFEST、接收审查页和 HF 回执单列待审数量；有授权补跑时，统计采用补跑后的有效结果，原始记录和页面继续保留。`verifier/verdict.json` 的 `evidence.review`（privileged）、`verifier/review.json`（standard）和已有 `review_frames/` 随原始归档保留，渲染失败记录也不改写。本次不新增自动审批或历史评分重写；旧封包若把待审记为 unsolved，新接收器会因派生报告与原始记录不一致而拒绝，需维护方保留旧包并用更新后的工具另行交付修正包。

代码已提供：固定实例选择、预检后发布任务包和 batch dispatch、标准 runner 分流、认证解析与刷新保护、逐 K verdict、共享停止、mirror 最终同步和脱敏、MANIFEST/inventory、标准 tar 接收和逐 trial 审查页、显式 rerun 派单、HF 私有目标及远端文件哈希检查。

**尚未放行 180 次真实实验。** 本轮没有生成并发布全部 60 个 v15 包、运行真实模型/GPU canary、向 HF 上传或在独立接收主机实测。没有把当前工作区提交/推送成 helper 可 checkout 的发布 commit。网站按用户决定暂缓。CPU 合同和真实 Docker mirror 的验证记录见本页末尾。

## 2. 维护方先做什么

### 2.1 冻结源码、准备 30 个实例

先选定包含本轮代码、各 Task 合并修正和匹配 runtime 的源码版本。不要一边修改 Task 一边制作正式发布包。确认模型、预算、helper ID、batch 名和交付目标；下面示例每次 agent 预算使用配置中的 43200 秒。

```bash
cd /path/to/topogym
WORK=/data/maintainer-work
RUN=helper-oracle-reference-v15-release01

bash bash_scripts/run_difficulty_trials.sh \
  --run-id "$RUN" --phase plan \
  --setting configs/sweeps/helper_oracle_reference.yaml --work-dir "$WORK"

bash bash_scripts/run_difficulty_trials.sh \
  --run-id "$RUN" --phase prepare --resume \
  --gpu-device 0 --work-dir "$WORK"

bash bash_scripts/run_difficulty_trials.sh \
  --run-id "$RUN" --phase preflight --resume \
  --gpu-device 0 --work-dir "$WORK"
```

这些阶段不需要模型凭据。prepare 包含真实 GPU 建场、冻结实例、Blanket 初态和 IPC 状态处理；preflight 检查恢复、动作、RGB、replay 和 limited finalization。失败不能换 seed 或补写成功标记。源码快照和证据在 `$WORK/runs/difficulty_trials/$RUN/`。

当前通用 active release 仍可能显示 `merged-v15 has no frozen task tree yet`。本流程以真正完成预检的包生成独立 batch catalog；runner 对它进行发布清单和 release/binding 校验，不回退历史 v14，也不把全局 active release 改成“已完成”。

### 2.2 发布到标准 tasks/ 和 configs/helper_batches/

维护方和 helper 的 native runner 工具安装相同。需要 Linux、Python 3.12、npm、Docker/Compose 和 NVIDIA Container Toolkit；模型/依赖安装需要网络。脚本固定 Harbor 0.23.0、Codex 0.157.0 和私有 Node 22.14.0，安装已有哈希锁和认证刷新补丁，不改宿主 Node。Python 3.12 若由 uv 管理，脚本可找到已安装的解释器。

```bash
bash scripts/setup_agent_batch.sh
export PATH="$PWD/.venv-agent-batch/bin:$PWD/.tools/agent-batch/node_modules/.bin:$PATH"

B=helper01-oracle-v15-k3
python scripts/publish_agent_batch.py \
  --run "$WORK/runs/difficulty_trials/$RUN" \
  --batch "$B" --helper helper01
```

只添加新包，不覆盖现有 tasks；已经发布且文件/dataset digest 完全相同的包可复用于另一个 batch。脚本验证 prepared/preflight、来源和实际镜像；将主机 GPU UUID/UID 替换为运行时部署变量；写 dataset digest 和 `configs/helper_batches/$B.json`。dispatch 锁任务完整字节、instance binding、seed/variation、模型参数、预算、K、job 清单和 runner 工具哈希。失败时不会生成可运行的 dispatch；中断产生的新增目录保留供检查。

先做小批次时，可以仅发布 Coil easy、双模式、K=1，共两个 trial；这两个包通过后可原样复用于全量派单：

```bash
python scripts/publish_agent_batch.py \
  --run "$WORK/runs/difficulty_trials/$RUN" \
  --batch helper01-coil-easy-smoke --helper helper01 --repetitions 1 \
  --task-base topogym-cast-coil-easy-o00
```

对方最新回复已确认私有接收库 `eai-v2-internal/helper-uploads` 建好，并由上游实测过上传、下载；**我们尚未使用当前工具对真实库认证实测**。HF 目标示例已集中在 [native_upload_target.example.json](../../configs/helpers/native_upload_target.example.json)：

```json
{"type":"hf","repo_id":"eai-v2-internal/helper-uploads","prefix":"helpers/helper01/helper01-oracle-v15-k3"}
```

确认真实 helper ID（小写）和 batch 后，维护方复制并调整此示例，发布时加 `--upload-spec /private/upload-target.json`；prefix 必须与 `--helper`、`--batch` 一致。不传此选项时仍是 shared-folder。库由对方组织维护者创建并确认 private；helper 运行前会认证检查，不自动建库。公开的 `eai-v2-internal/agent-runs` 是对方所述网站用库，不能作为原始 helper 归档的目标。发布后不手改 dispatch；修改内容会导致 plan digest 校验失败。

维护方还要：

1. 对这些具体包执行真实 Harbor nop 检查，再准备小批次进行真实 agent 单 lane/多 lane 验收；nop 无法证明模型解题成功。
2. 将新增 tasks、dataset、dispatch 和 runner 提交到 helper 可访问的仓库，给出准确 commit。`git clone ... && git checkout <commit>` 必须能取得全部包，不能只存在本机 runs。
3. 提供 dispatch 所列**全部角色镜像**。可推送约定 registry 后从同一镜像重新冻结绑定，或使用 `docker image save -o images.tar <所有指定镜像引用>` 并附 checksum，让 helper `docker image load -i images.tar`。不能仅告知一个准备机专用 tag；runner 会核对实际 Id。
4. 自己另存原始 `$B.json`，用于异机验收。发给 helper：commit、batch、任务 bases、模型/预算、镜像取得方式、上传目标，以及是否准许 partial 交回。

## 3. Helper 从 clone 到运行

### 3.0 推荐：统一 helper 入口

维护方先完成上一节，给出真实的 commit、assignment 和镜像。helper checkout 后复制 [配置模板](../../configs/helpers/native_helper.example.json) 到私有目录，只填写本机路径、GPU/认证和 HF token 路径：

```bash
cp configs/helpers/native_helper.example.json "$HOME/helper.local.json"
chmod 600 "$HOME/helper.local.json"
# 编辑该 JSON 后执行；首次登录不要套 nohup，先完成前台设备授权。
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json"
```

模板各项的含义：

| 字段 | 填写方式 |
|---|---|
| `assignment` | 我们提供的真实 `configs/helper_batches/<batch>.json` 路径，模板中的占位路径不能直接运行 |
| `jobs_dir` | 本机结果目录，必须以 `/agents` 结尾；默认模板 `/data/helper-work/jobs/agents` |
| `auth` | 订阅使用 `{"method":"subscription","auth_file":"~/.codex/auth.json"}`；API 使用 `{"method":"api-key","env_file":"/private/eai.env"}` |
| `lanes` | 每个元素指定 `gpu`；可用该元素的 `auth` 覆盖顶层配置；同一订阅缓存串行 |
| `images.archives` | 维护方提供的镜像 tar 的本机路径列表；没有则 `[]` |
| `images.pull_missing` | 仅在维护方保证派单镜像引用可从 registry 拉取时设 true；最终仍核对实际 image Id |
| `hf_token_file` | HF 上传所用的私有 token 文件路径（0600）；共享文件夹时可为 null |
| `upload` | true 时完成验包后上传到派单中的 HF 目标；false 只生成本地交付文件 |
| `allow_partial` | 默认 false；需要明确交回部分结果时才设 true，回执仍标为 incomplete |
| `background` | 默认 true；前台安装/认证检查通过后自动转后台；`--foreground` 可保持前台 |
| `notes_file` | 可选的本机异常说明文本；没有则 null，机器不能自动保证“无异常” |
| `rerun_assignments` | 合并交付授权 rerun 时填我们给出的派单路径；正常运行是 `[]` |

相对路径以配置文件所在目录解析。模型、种子、任务、K 和预算从 assignment 读取，不能在 helper 配置中覆盖。依赖安装检查 Python 3.12、Node 22、Docker 和 NVIDIA；脚本不替 helper 安装 GPU 驱动或修改宿主权限。已有工具安装必须通过固定版本/补丁检查，损坏安装会报错保留。

统一入口顺序执行：工具/任务/镜像检查 → HF 访问检查（启用上传时）→ 首次订阅登录及模型 canary → 各 lane → 完整性检查、最终脱敏、MANIFEST → 标准 tar/checksum → 本地验包 → HF 三文件上传和远端哈希检查。只用既有 native runner；不发布任务、不自动 rerun，不接收其他 helper 的结果，不操作网站。

状态和私有工作日志位于 `jobs_dir` 父目录下的 `.helper-pipeline/<batch>/`；交付文件只有 `upload_<batch>/` 中的 archive、checksum、MANIFEST。HF 上传使用固定 SDK 的一次三文件 commit，目标/内容与手动 `hf upload` 相同；缓存、token 和工作日志不进入上传目录。

```bash
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json" --phase status
# 只重试打包；不再次运行模型。
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json" --phase deliver
# 只重试上传；重新检查文件和远端状态，同字节已上传则不重复提交。
bash bash_scripts/run_helper_batch.sh --config "$HOME/helper.local.json" --phase upload
```

正在运行时重复启动会拒绝；正常封存后的 `all` 只继续交付。lane 异常死亡时由人检查后显式 `--phase deliver --recover`，不会把原 trial 自动补跑。已有上传目录被视为固定交付版本，不覆盖。若原批已上传，授权 rerun 可用它自己的 assignment 单独交付到 `<batch>-rerun` 目标；工具不会用合并包覆盖 HF 上原批不同字节。合并归档适用于第一次交付前就已完成 rerun 的情况。完整性判定以回执中的 `delivery_complete` 为准，工作流 `complete` 仅表示所选阶段执行完毕。

以下 3.1 起保留逐条手动步骤，便于对照原 helper 文档和诊断。

### 3.1 首次准备与认证

第三方 helper 无法访问私有开发仓库，必须使用维护方提供的 helper release 仓库和固定 commit。以下两个变量来自任务单；当前尚未发布该独立 release：

```bash
git clone "$HELPER_REPO" helper-release
cd helper-release
git checkout "$RELEASE_COMMIT"
bash scripts/setup_agent_batch.sh
export PATH="$PWD/.venv-agent-batch/bin:$PWD/.tools/agent-batch/node_modules/.bin:$PATH"
```

对方已将原示例名 `rcb.env` / `rcb_helper_runs` 更正为 `eai.env` / `eai_helper_runs`；本页命令随之更新。它们只是可配置路径，不改变 `agents/` 与 `agents_mirror/` 的交付结构，已有运行无须重命名。

完成维护方指定的镜像导入/下载。确认宿主 GPU 驱动和 Docker GPU 权限；不要运行未经授权的全局清理命令。

订阅认证示例使用原文默认文件路径：

```bash
codex -c 'cli_auth_credentials_store="file"' login --device-auth
codex -c 'cli_auth_credentials_store="file"' login status
printf 'CODEX_FORCE_AUTH_JSON=1\nCODEX_AUTH_JSON_PATH=%s/.codex/auth.json\n' "$HOME" > "$HOME/eai.env"
chmod 600 "$HOME/eai.env" "$HOME/.codex/auth.json"
```

`eai.env` 按数据解析，不 shell-source。若实际使用其他 auth 路径，在 env 文件和扫描命令中同时指定该路径。旧 difficulty Docker 登录的默认缓存路径与 `~/.codex/auth.json` 不同，不能假定已自动互通。

API 认证则把 `OPENAI_API_KEY` 和需要的 `OPENAI_BASE_URL` 写入私有 `eai.env`；不要同时放订阅强制变量。HF_TOKEN 不放此文件。API 模式的扫描不传不存在的 `--codex-auth` 文件。

```bash
B=helper01-oracle-v15-k3
ASSIGNMENT="$PWD/configs/helper_batches/$B.json"
ENV_FILE="$HOME/eai.env" python scripts/check_agent_batch_auth.py \
  --assignment "$ASSIGNMENT" --receipt /data/helper-auth-canary.json
```

这一步实际向指定模型发出一次很小的请求，确认账户/模型可用，不计入 180 次试验。CLI 使用临时 profile；订阅刷新保存回原缓存。它不替代 Docker/GPU smoke。

### 3.2 启动 batch：主命令保持原样

```bash
export JOBS=$PWD/jobs/agents
mapfile -t TASK_BASES < <(python3 - "$ASSIGNMENT" <<'PY'
import json, sys
print('\n'.join(json.load(open(sys.argv[1]))['task_bases']))
PY
)

AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh ENV_FILE=$HOME/eai.env \
  nohup scripts/run_agent_batch.sh "$B" "${TASK_BASES[@]}" > "run_$B.out" 2>&1 &
```

`TASK_BASES` 是把原文 `<task-base> [<task-base> ...]` 展开为派单中的 30 个值。dispatch 自动给出 `K=3`；全局若有不同的 K/MODEL/MODES/AK，会直接拒绝，不会偷偷改实验。

进度仍是 `$JOBS/$B.log`；summary 仍是 `$JOBS/$B.summary.md`，每一份 K trial 单列。一个 lane 一次只运行一个 trial。再次执行相同命令可增加 lane；GPU 不同可加 `GPU_DEVICE=1`。helper 应按实测显存容量安排 lane。

**同一份订阅缓存会串行持锁**，防止 refresh token 并发轮换；多开进程不会让这个账户并行执行。要真正并行使用 API 凭据或独立登录缓存。原子 claim 仍保证一个 job 只被一个 runner 认领。模型账户/配置失败写共享停止标记，阻止后续新 job；已经运行的其他 lane 保留自己的结果并完成收尾。

## 4. 收尾、检查、打包

最后一个正常退出的 lane 自动最终同步 mirror、扫描并脱敏、生成 `B-MANIFEST.md`、metadata、逐 trial verdict 和精确 inventory。原始 mirror 留在 jobs 父目录的 `.agent-batch-private/`，容器 root 所有且 helper 不可读取；经过扫描的完整历史副本放在 `agents_mirror/<job>/`。不删除历史版本。

如有人工异常说明，先写私有文本，然后更新自动 MANIFEST；不要在封包之后随意改证据：

```bash
ENV_FILE="$HOME/eai.env" python scripts/finish_agent_batch.py \
  --jobs "$JOBS" --assignment "$ASSIGNMENT" --notes-file /data/helper-incidents.txt
```

只有 lane 异常死亡、需要保留 partial 证据时使用同一命令的 `--recover`。它确认没有活 lane，只停止记录中明确归本批的容器，不重跑、不移走 job/claim；mirror 中断仍记 incomplete。若已存在不完整 mirror 交付副本，工具会阻止覆盖，需人工审查原记录。

原文循环保留作粗检查：

```bash
for d in "$JOBS"/"$B"-*/; do ls "$d"*/verifier/reward.json >/dev/null 2>&1 || echo "no verdict: $d"; done
```

正式检查新增一条，逐个核对 180 项，区分正常 0 分、非法提交、infra、未启动、身份不符、token 超预算/用量缺失和缺成功录像：

```bash
python3 scripts/check_agent_batch.py --jobs "$JOBS" --batch "$B" \
  --assignment "$ASSIGNMENT" --require-complete
```

订阅模式下保留原文两次扫描的参数结构，按对方更正使用示例文件名 `eai.env`，并自动覆盖 sibling mirror。它们拒绝仍在写入或已封存后意外修改的数据：

```bash
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/eai.env" --codex-auth "$HOME/.codex/auth.json" --redact
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/eai.env" --codex-auth "$HOME/.codex/auth.json"
```

原文打包命令保留；先保存 repo 路径，避免 `cd` 后找不到脚本：

```bash
REPO=$PWD
H=helper01
cd "$(dirname "$JOBS")"
tar -czf "${B}__${H}.tar.gz" agents/"$B"-* agents/"$B".log agents/"$B".summary.md \
  $(ls -d agents_mirror/"$B"-* 2>/dev/null)
sha256sum "${B}__${H}.tar.gz" > "${B}__${H}.tar.gz.sha256"

mkdir -p "upload_$B"
cp "${B}__${H}.tar.gz" "${B}__${H}.tar.gz.sha256" "upload_$B/"
cp "agents/$B-MANIFEST.md" "upload_$B/MANIFEST.md"
python3 "$REPO/scripts/agent_batch_delivery.py" verify \
  --archive "${B}__${H}.tar.gz" --assignment "$ASSIGNMENT" --require-complete
```

未完成批次可不带 `--require-complete` 验包并交回，但必须明确 partial。正常失败/0 分算已评测；基础设施失败不算。成功媒体还会做 MP4 区块、PNG 区块/CRC 和截断检查；这不是全帧解码或视觉正确性证明，不能替代人对解题录像/任务质量的审查。

自动 MANIFEST 展开 repo/dirty、CPU/RAM、GPU/driver、驱动支持的 CUDA 信息、Python/Harbor/Codex、Docker/Compose、镜像 Id/RepoDigests、agent 设置、各 lane/GPU/auth、开始/结束和异常备注。镜像内实际库版本由 plan 的 runtime binding 记录。采集失败记 unknown，不把未知写成“无异常”。原文 `git -C "$REPO" rev-parse HEAD`、`nvidia-smi`、`docker --version`、`harbor --version` 可以保留人工核对；无 RepoDigest 的本地镜像应看 `.Id`。

## 5. HF 上传或共享文件夹

共享文件夹只交上述三个文件。HF 需要目标存在且 private、token 对 dataset 有写权限、确定的 `helpers/<helper>/<batch>` 路径和网络。token 不等于目标配置。

```bash
cd "$REPO"
UPLOAD="$(dirname "$JOBS")/upload_$B"
python scripts/check_agent_batch_hf.py --assignment "$ASSIGNMENT" \
  --folder "$UPLOAD" --hf-token-file /private/eai-helper-hf-token
```

预检查同时阻止覆盖远端同路径的不同字节。随后保留原文 `hf upload`：

```bash
# huggingface_hub 已由 setup 的锁文件安装；无需再 pip install -U 改变版本。
HF_TOKEN="$(cat /private/eai-helper-hf-token)" hf upload eai-v2-internal/helper-uploads "$UPLOAD" "helpers/$H/$B" --repo-type dataset
python scripts/check_agent_batch_hf.py --assignment "$ASSIGNMENT" \
  --folder "$UPLOAD" --hf-token-file /private/eai-helper-hf-token --verify-uploaded \
  --receipt /data/helper-hf-receipt.json
```

工具仅检查，不自动上传/建库/发消息。上传成功和实验完整是两回事。远端回执记录 revision 和三个文件的字节身份；接收方仍要下载后重新验包。不要在本地开启 shell `set -x` 输出 token。

## 6. 接收方在另一台机器验全部结果

下载 archive、checksum、MANIFEST 到同一目录，取出**维护方自己保存的原始 assignment**。不需要 helper 的模型凭据、GPU或原始绝对路径；stdllib 接收器可用系统 Python 3.10+。

```bash
REPO=/path/to/receiver-checkout
cd /data/received
sha256sum -c helper01-oracle-v15-k3__helper01.tar.gz.sha256
python3 "$REPO/scripts/agent_batch_delivery.py" import \
  --archive /data/received/helper01-oracle-v15-k3__helper01.tar.gz \
  --assignment /data/dispatch/helper01-oracle-v15-k3.json \
  --destination "$HOME/eai_helper_runs/helper01/jobs" --require-complete
```

`sha256sum -c` 在压缩包所在目录执行（checksum 内是 basename）。import 自身也做 checksum；在临时目录逐项拒绝路径穿越、链接、特殊文件、重复成员和超限归档，核对精确 inventory/维护方派单，再重算每个 K verdict。成功后保留标准 `agents/`、`agents_mirror/`，另外生成 `receipt.json` 和 **`review/README.md`**，链接到每个 trial 的日志、verifier、媒体和 mirror。

因此原文 `mkdir ... && tar -xzf ...` 的结果布局相同，但推荐用此 import 替代裸解包，以便完整验收。重复导入相同包不覆盖；不同包必须用新接收目录。收 partial 时去掉 `--require-complete`。

如要调用旧的重评分工具，在接收机另 checkout 发布 commit，并给 import 加 `--tasks-root /path/to/checkout/tasks`。工具核对包哈希并生成本机映射，不改写原 result.json 中的历史路径。实际重新物理评分另外需要对应 GPU/镜像；浏览全部原始 results 不需要这些。

## 7. 基础设施 rerun

helper 不自行重跑。维护方检查 partial 后可生成只包含未完成 trial 的新授权：

```bash
python3 scripts/create_agent_batch_rerun.py \
  --assignment /data/dispatch/original.json --jobs /data/accepted/jobs/agents \
  --output /data/dispatch/original-rerun.json
```

派单记录每个新 trial 对应的原 job/repetition，batch 必须是 `<batch>-rerun`。helper 设置 `BATCH_ASSIGNMENT=/path/to/original-rerun.json`，用它的 batch/task_bases 再调用原 runner。原始 job、claim、失败记录都保留。重跑是独立 attempt，不把旧记录改成成功。

原文主 batch 的 `B-*` 会把 sibling rerun 一并收入 tar。接收它时增加 `--rerun-assignment /data/dispatch/original-rerun.json`；缺少维护方独立授权会拒绝。回执保留原批次的不完整状态以及替补覆盖后的完整性，不隐藏额外执行次数。

同一个合并包在 helper 端执行 `agent_batch_delivery.py verify` 或上传前后的 `check_agent_batch_hf.py` 时，也必须传入这份 `--rerun-assignment`。合并包仍使用原 batch 的 archive 名与 HF 目标；单独交付 rerun 时则使用 rerun 派单中的目标。

## 8. 是否与原文逐项完全一致

| 原文步骤 | 当前行为 |
|---|---|
| clone/checkout、JOBS、B、nohup run_agent_batch | clone 改用第三方可访问的 helper release；其他入口保留，前提是 commit 真的发布了任务包和 dispatch |
| 查看 runner 头部、日志与 summary | 保留；发布派单固定模型/预算/K，额外覆盖会拒绝 |
| 重复命令增加 lane | 保留认领方式；同一订阅缓存串行，实际并行需独立缓存/API |
| verdict 的 for 循环 | 原样可运行，但不足以验 K；必须增加严格 checker |
| 两次 scan_secrets | 原样可运行，自动含 sibling mirror；认证文件路径必须真实存在 |
| tar、sha256sum、三文件 | 原样可运行；MANIFEST 自动生成后复制 |
| 主机/镜像版本手抄 | 可保留，已有自动 metadata；没有 digest 的镜像记录 Id |
| pip install -U、hf upload | hf upload 保留；依赖改为固定安装，补目标/远端哈希检查 |
| 接收方 checksum、mkdir/tar | checksum 保留；建议安全 import 代替裸 tar，输出相同 jobs 布局 |
| hosts/state/make runs 网站步骤 | 尚未接入，按用户决定跳过 |

结论不是“原文不用增加任何准备就能逐字跑完”。主要运行/归档命令兼容；新增的是固定工具安装、准确认证、模型 canary、完整性检查和安全接收。网站命令现在仍不能运行。

## 9. HF 与网站还需要的资料

用户提供的对方回复已明确以下安排；这是沟通确认，尚未对真实 HF 库/账号执行核验：

| 项目 | 已回复的安排 |
|---|---|
| HF 组织 | `eai-v2-internal` |
| 原始结果接收库 | 上游确认已建好 private dataset `eai-v2-internal/helper-uploads`，并实测上传、下载 |
| 上传目录 | `helpers/<helper>/<batch>/` |
| helper 写权限 | 每位 helper 一个仅针对该库的 fine-grained 写 token，私下交付，用完吊销 |
| 接收方读权限 | 使用有权访问该库的组织成员账号 |
| 名称 | helper ID 小写；batch 由维护方派单确定 |
| 正式文档 | 静态 `docs/SHARING_RUNS.md`；据上游说明，`dev/jianwen` 的同文副本为 `docs/rcb/SHARING_RUNS.md`，TopoGym 入口补入 §3b |
| 网站用库 | 对方称 `eai-v2-internal/agent-runs` 为公开库，网站在用；原始 helper 上传不能放在那里 |

现在仍需落实：

1. 取得最新 `SHARING_RUNS.md` 和来源 commit；本机旧引用尚无该文件，更新分支遇到 SSH 公钥认证失败。随后用我们自己的工具实测真实 HF 目标。
2. 这次实际的 helper ID 和正式 batch 名，由我们写入派单。
3. 小测试凭据已单独提供；实际运行时从仓库外私有文件读取，并配置 `hf_token_file`，不记录在代码、日志、手册或机器 assignment 中。正式 helper 凭据由上游逐人发放、交付后吊销。
4. 我们实际用于接收的组织成员账号已获得此库读权限；仅有“组织成员”这个安排不代替权限实测。

目录契约与当前代码一致，私有库/写权限/远端哈希检查也已有，无需改上传协议。旧 difficulty 上传器的默认库继续保留其历史用途，不替代此次派单目标。HF 未就绪时可以先验证本地交付；统一入口不猜测或自动创建 dataset。对方提供的是库级 token 范围，不应声称其技术权限被限制在单个 helper 文件夹内；文件夹范围由本工具按派单约束。

网站：未来恢复时需要 review site 仓库地址/本机路径及 commit、benchmark 名、原文 registering-runs 文档、hosts 与 state/runs 的实际 schema、importer 对 K/sidecar/rerun/预算调整后得分的处理方式，以及维护者运行 `make runs` 的环境。此外要确认网站怎样把经审查、可公开的数据写入 `agent-runs`、实际存储 schema 和发布入口。接收流程应先下载私有归档、验收和审查，再按网站实际机制发布可公开产物；不能把整个原始 tar 直接转传公开库。helper 统一脚本到私有交付为止，不承担网站发布。

## 10. 验证证据

- 旧 13 任务配置实际生成 39 个 named-tier/seed-0 实例；当前 10 任务配置生成 30 个。这里只是配置和身份验证。
- 新 native CPU 合同覆盖缺 trial/job、错 binding/checksum/预算、verdict 冲突、账户失败、缺媒体及真实媒体截断、运行中封包、目录前缀冲突、tar 穿越/链接、认证来源/刷新、rerun 授权、HF 私有性/远端哈希、预检过期时拒绝发布、相同包复用和异机任务映射。
- [基础回归](../../runs/test_results/helper_delivery_20261004_163105/summary.json)：native、release-selection、difficulty-eval、helper-delivery 全部通过。[发布/交付最终回归](../../runs/test_results/helper_delivery_20261004_170801/summary.json) 的 native 20 项通过，包含 HF 合并 rerun 包必须提供维护方授权的检查；[release/镜像/刷新回归](../../runs/test_results/helper_delivery_20261004_170037/summary.json) 的相关项通过；[HF 回归](../../runs/test_results/helper_delivery_20261004_164613/summary.json) 24 项通过。
- [真实 Docker mirror 小样](../../runs/test_results/native_batch_docker_20261004_163528/summary.json)：两 lane、K=3、六份合成结果；真实 root 保护和六份改写历史段；原 scanner/tar/checksum 与离线 import 通过。没有真实模型或任务物理执行，也不是独立两台机器验收。
- [后续 Docker 复测](../../runs/test_results/native_batch_docker_20261004_165428/summary.json) 同样通过。另在本机已缓存的 Harbor 0.23.0 controller 中离线验证了更新后的认证/资源归属 patch 能应用并编译，实际 Task.checksum API 可调用；没有重新联网安装 bootstrap 或调用真实账户。
- [统一入口最终回归](../../runs/test_results/helper_delivery_20261004_174822/summary.json)：workflow 11 项、native 20 项通过；[交付兼容回归](../../runs/test_results/helper_delivery_20261004_174549/summary.json) 的 helper-delivery 25 项通过。覆盖前台流程、后台子进程接续、两 lane 环境传递、重复执行不重跑、partial、包被修改、HF 三文件与重试、逐 trial token 限额和用量缺失；模型/GPU/HF 使用测试替身。[difficulty-eval 28 项回归](../../runs/test_results/helper_delivery_20261004_174048/summary.json) 含新增 12 小时双模式文本任务包和 collect 时间检查，不执行物理。
- 所有运行遵守 CPU 仅监控、主机内存 90% 停止自有工作；未终止其他会话任务。当前 60 包发布、模型/GPU smoke、独立机器接收属于正式放行前仍需完成的检查。
