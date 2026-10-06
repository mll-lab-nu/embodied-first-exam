# Helper 原命令与在线构建镜像

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
