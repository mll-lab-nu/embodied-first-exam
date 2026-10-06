# Helper 原命令与在线构建镜像

> 2026-10-06 回退说明：本文记录的是扩展 helper runner 的历史方案或发布状态。当前开发仓库已恢复原版 `run_agent_batch.sh`，新增派单/自动准备/封存入口已归档；下文命令不再直接适用于当前 checkout。已有固定 helper release 和实验记录未修改。

## 2026-10-06 诊断取证补充

本轮已修复的问题、尚未调整的判定逻辑、待查原因和发布验证范围，统一整理在 [Helper sweep 问题、修复与待查事项](helper_pipeline_debug_summary_20261006_zh.md)。

下面区分已发生的错误和仍待证明的原因。日志增强不改变模型、任务、token 上限或评分判定，也不把旧批次改成成功。

| 待证明的原因 | 已知事实与缺失证据 | 本次支持 |
| --- | --- | --- |
| 404 是否为服务商路由或模型可用性问题 | 已有真实 404，也有成功响应；缺发生时间、逐请求关联 ID、提供方信息，以及服务商侧查询结果 | `agent/openrouter-requests.jsonl` 记录本地请求 ID、HTTP 状态、允许列出的服务商 ID/名称、返回模型和 generation ID；不记录请求正文 |
| Broken pipe 是否由 Muse 取消、上游断流或进程退出引起 | 旧日志只有异常类型，缺写入/读取方向和终态是否已收到 | 逐请求记录读上游、写本地的阶段、耗时、字节数、是否收到并转发终态；需结合 Muse 原生日志确认取消原因 |
| token 是否漏计或重复计数 | 尚无算术错误证据；已收到的 usage 不覆盖未返回 usage 的潜在计费 | 记录 request→generation→usage、重复 ID 是否计入总数。要证明真实漏计，还需提供方按 generation ID 的计费记录；日志不能自行证明零消耗 |
| 原生 agent 是否完成却被包装层判失败 | 已看到原生完成事件与包装层非零退出；仍缺同次进程退出码 | `agent/muse-run-status.json` 分列原生退出码、终态、包装层退出码/原因、当时的计量状态，不更改判定规则 |
| 外层 TimeoutExpired 是否出在镜像复制、Docker 控制或 Harbor | 旧日志没有完整栈，不能还原具体超时命令 | `$JOBS/$B-lane-<id>-diagnostics.jsonl` 记录阶段、操作类别、容器名、期限、耗时、脱敏输出及栈帧；同时保留原始异常和清理异常 |
| Buildx 是否缺失或不可用 | 已有评分镜像构建 `unknown flag: --file`；缺 helper 本机版本/命令可用性证据 | 启动前检查 `docker buildx version` 和 `docker buildx build --help`，主机元数据保留版本；这些检查不能证明任意镜像构建必定成功 |
| Vulkan 或冻结资产真的不一致 | 目前主要是 agent 自述；需真实 SIGABRT/渲染栈、实例文件、资产路径与预期/实际 SHA，以及对应镜像身份 | GPU 检查日志附 ICD 文件、Vulkan loader、driver capabilities，明确 `rendering_tested=false`；原始模拟器日志/资产仍需从 trial 证据核对，不绕过冻结校验 |
| Muse 权限/Bubblewrap 警告是否导致退出 | 尚无直接因果证据 | 原始 stderr 已保存；新增运行状态记录 UID/GID、会话目录权限，与退出码/终态联查 |

新诊断由正式入口自动生成，正常的两次密钥扫描、原布局打包与 HF 上传步骤不变。旧批次缺失的历史信息无法补造。为了定位新问题，需要使用含新 runner 哈希的任务单；不要直接修改已封存 assignment 或旧结果。

正式 144-trial 批次的 API key 操作单见 [刚体 sweep 完整命令](rigid_sweep_helper_runbook_zh.md)。该文档已展开全部 task base，填写批次、HF 和当前本地 release 信息；远端尚未发布的限制也单独标明。本页保留机制说明和通用命令模板。

当前交付配置：8 个刚体／关节刚体任务 × easy、medium、hard × privileged、standard × K=3，共 144 个 trial。每档固定 oracle 参考 seed 0；每个 trial 43200 秒、150M input tokens、10M output tokens。token 超限目前在运行后判分，不是实时切断调用。

任务是 interlocked_claws、lock_picking、hedgehog_in_cage、fiber_bundling、horseshoe_ring、cast_coil、cast_keyhole、buzz_wire_3d。维护方提前 prepare 并发布 48 个冻结任务包。发布默认要求 preflight；本次用户因时间限制取消剩余预检，维护方可用 `publish_agent_batch.py --skip-preflight-reason "原因"` 显式发布，任务单保留已验证的通过记录并将其余实例标为未检查，仍核验包哈希、实例身份和镜像绑定。helper 不重新选难度、抽 seed、生成实例或改预算，也不补跑维护方取消的预检。

## Helper 的入口

继续按收到的固定版 `SHARING_RUNS.md` 克隆指定仓库并 checkout 指定 commit，使用任务单给的 batch、模型设置及 24 个 task base，执行原来的命令：

```bash
export JOBS=$PWD/jobs/agents
B=<任务单中的batch>
AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh ENV_FILE=$HOME/rcb.env \
  nohup scripts/run_agent_batch.sh "$B" <task-base> [<task-base> ...] > "run_$B.out" 2>&1 &
```

尖括号是任务单的占位符，不可原样执行。MODEL/EFFORT 使用派单给出的值；只有 assignment 明确允许选择模型时才能更改。K=3、双模式和预算从 assignment 读取，无须额外环境变量。

首次启动内部按顺序完成：安装固定的 runner 工具；核对冻结构建材料；缺少镜像时联网构建；检查实际安装的源码、Python 包内容、原生库、机器人／视觉资产和系统包版本；验证模型认证；开始 trial。构建发生在 trial 计时之前。相同源码镜像只构建一次，多 lane 共用构建锁。已存在但内容不符的镜像会明确报错并保留，不覆盖它。

使用本机 Codex 登录时，常规 API env 文件可以不存在；使用 API key 时，Codex auth 文件可以不存在。扫描器同样兼容原文同时列出两种认证文件。凭据仍然由 helper 在本机事先准备，不能放入仓库、镜像构建目录或结果归档。

任务结束后的 verdict 检查、两次密钥扫描、tar、sha256sum、MANIFEST 和 HF 上传继续使用收到的手册。自动 wrapper `run_helper_batch.sh` 仍可用，但不再是执行这套手册必须增加的步骤。

## MANIFEST 的一处命令兼容差异

本地构建镜像可能没有 RepoDigest。原文的 `{{index .RepoDigests 0}}` 会因此报错；填写 MANIFEST 时使用下式即可，手册本身允许记录 Id：

```bash
docker image inspect --format '{{.Id}}' <image>
```

不伪造 RepoDigest，不要求 helper 为产生 digest 再推送镜像。完整的实际镜像 ID、参考镜像 ID、构建清单哈希和内容检查结果还会自动写进 `agents/<batch>-metadata.json`，随原文 tar 选择一起交付。

## 维护方需要冻结的材料

`images/helper-build/<release>/manifest.json` 记录完整构建目录的哈希；assignment 的 `image_sources` 固定清单哈希和期望运行内容。构建目录包含冻结源码和资产、基础镜像 digest、Debian 软件源快照和全部包版本、带哈希的 Python 依赖锁、固定安装工具和已审计的 libuipc wheel。

libuipc wheel 是已固定的原生依赖产物，不是 Docker 镜像。复用它是为了让现有任务锁中的原生库字节、构建记录哈希保持一致，也避免每个 helper 重复 CUDA 编译。其余依赖由 helper 在线下载。构建成功不代表模型解题成功。

维护方使用生产工具 `scripts/agent_batch_image_build.py`：`--source` 指向 prepare 的冻结源码；`--image` 是对应参考镜像；`--wheel-image` 是同一源码 Dockerfile 的 `uipc-build` 阶段；`--apt-snapshot` 固定源时间；`--output` 放在发布 checkout 的 `images/helper-build/` 下。`--image-sources-output` 生成发布器要读取的 JSON。原始 prepare 目录和证据不改写。

交付前用同一工具的 `--verify-build <manifest.json> --repository <发布checkout> --tag <新测试标签> --receipt <报告.json>` 实际构建并检查。随后 `publish_agent_batch.py --image-sources <生成的JSON>` 将策略绑定进新 assignment，release exporter 会包含全部构建材料。已有 assignment 不覆盖，需要新的发布产物。

这一路只授权镜像 ID 不同而运行内容核对一致的重建；任务包、实例、评分代码和 runtime binding 都保留原字节。没有在线构建策略的旧 assignment 继续要求原镜像 ID。批次开始后也不能中途换镜像。

## 接收和验证范围

接收方独立下载 HF 的归档，使用原始 assignment 验证任务、全部 K 次 trial、用量和镜像构建记录。构建清单或记录不匹配会拦截验收；人工 MANIFEST 的文字不替代真实 verdict。网站导入仍是接收端的独立后续工作。

CPU 回归使用合成试验与模拟 Docker/HF，不能视为物理或模型验收。真实联网镜像重建报告在 `runs/test_results/helper_online_build_20261005/`；只有存在成功的 `build-receipt.json` 才表示该次重建内容核对通过。既有真实 HF 传输小样与本轮 144-trial 正式实验分别记录，不把前者当作后者完成。
