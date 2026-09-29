# TopoGym 原生 Harbor

TopoGym 现在直接发布标准 Harbor task，运行入口是官方 `harbor run`。实现位于本目录，与 `robot_coding_bench` 没有运行时、导入、挂载或下载依赖。协议研究基准为本机已保存的 `origin/dev/qineng@fa59c1a6`；本次未查询到服务器的更新状态，也没有修改该仓库。

旧 runner、远程 Python policy 服务和双 token 预算网关归档在 [`legacy/harbor_20260929`](../../legacy/harbor_20260929/README.md)。本地 `Env`、`Interaction`、`SegmentRunner` 继续使用。

## 安装、导出、运行

```bash
cd /home/jianwen/topogym
./scripts/setup_benchmark.sh
./scripts/build_benchmark_image.sh topogym-simulator:20260929

# 默认：13 个基础 family，各 limited / unlimited，一共 26 个任务。
# 输出目录必须不存在，避免覆盖已冻结的任务。
.venv-harbor/bin/python -m topogym.benchmark export --output harbor_tasks
.venv-harbor/bin/python scripts/check_benchmark_tasks.py harbor_tasks

# 单任务，例如基础设施测试方块；不加入正式 13 项 family 的成绩。
.venv-harbor/bin/python -m topogym.benchmark export \
  --task cube_pick_place --mode both --output runs/harbor_cube_tasks_native

# 原生 Harbor nop 验证：预期 reward=0。
.venv-harbor/bin/harbor run \
  -p "$PWD/runs/harbor_cube_tasks_native/cube-pick-place-base-s0-limited" \
  -a nop -n 1 -k 1 --jobs-dir "$PWD/runs/harbor_jobs"

# 使用已配置的官方 coding agent；模型名来自你自己的服务配置。
.venv-harbor/bin/harbor run -p harbor_tasks \
  -a opencode -m "$MODEL" --env-file .secrets/harbor.env \
  -n 1 -k 1 --jobs-dir "$PWD/runs/harbor_jobs"
```

修复验收已生成 `runs/harbor_cube_tasks_native/` 时，直接运行即可，不要重复 export 到同一路径。旧 `runs/harbor_cube_tasks/` 保留为失败运行的原始输入，缺少评分入口，不能用于新运行。修改导出器不会自动更新已生成任务。

按模式筛选可使用 `-p runs/harbor_cube_tasks_native -i '*-limited'` 或 `-i '*-unlimited'`。`-n` 是并发数，`-k` 是每任务 attempts。jobs 路径使用绝对路径，避免 Docker Compose 对相对复制路径的解析问题。Harbor 会展示 reward.json 的多个指标；成功分数看 `success` / reward.txt，`deterministic=1` 不代表任务成功。

`--all-variants --seed 0 --seed 1` 枚举 registry 中 integrated 的变体，并保留未导出变体及原因。当前 registry 为 46 个 integrated 变体、1 个不可用变体；每个 seed 可以生成 92 个双模式 task。`--task <task_id>`、`--mode limited|unlimited|both` 可缩小范围。`--image` 可指定本地固定 tag 或镜像 digest。镜像构建和正式运行需要 Docker socket 权限及 NVIDIA runtime。

生成目录包含 instruction、task.toml、environment、tests、solution、source-manifest；每个 task 内的 runtime.tar.gz 都是本项目自己的冻结副本。文件可以独立搬走使用，不依赖工作区绝对路径。`dataset.toml` 使用 Harbor 的 `[dataset]`、`org/name` 和 `sha256:` 格式，摘要按官方 Packager 计算；source-manifest 同时放入会被打包的 `tests/`。`coverage.json` 分列 exported、protocol_passed、replay_passed、oracle_passed、scoring_eligible。当前清单明确命名为 `topogym/development`，不是已取得评分资格的正式发布集。生成的 `harbor_tasks/` 不提交 Git，可通过导出命令重建；尚不提供克隆远端后直接运行或 Harbor Hub `-d` 的发布流程。

自定义物理频率、目标和预算使用 `--instance-file configs/benchmark/cube_pick_place.yaml`，也可以提供实例列表，详见 [实例配置](../../configs/benchmark/README.md)。模型、并发和重试仍使用 Harbor 原生参数。

## 两种模式

| 模式 | Agent 获得的能力 | 最终交付 |
| --- | --- | --- |
| limited | 轻量 main 内的 Robot 客户端；独立 sim sidecar 提供 RGB-D、实测本体和机器人 FK/IK；无 reset、对象真值、Python policy 上传 | sim 自动记录实际关节目标，包括 watch/hold |
| unlimited | 本地 Session、simulator 源码、状态读取和同一个固定实例的 reset | `/app/output/trajectory.npz` |

limited 示例：

```python
from topogym_client import Robot
r = Robot()
spec = r.spec()
obs = r.get_obs(depth="frames", video="both")
obs.save("/app/output/first_observation")
print(obs.group("joint_pos"), obs.frame_step, obs.frame_time_s)
# actions 的列顺序、原生夹爪单位和限位以 spec["action_types"] 为准。
result = r.submit("joint_position", actions, dt=1/spec["control_hz"])
```

unlimited 示例：

```python
from topogym.benchmark.session import Session
with Session("/app/instance.json") as s:
    obs = s.get_obs(depth="last")
    state = s.state()
    # 用 s.submit(...) 执行动作；需要重试时 s.reset() 保持固定实例。
    s.save("/app/output/trajectory.npz")
```

HTTP 协议是 `rcb-limited/2.2`：`GET /spec`、`GET /status`、`POST /observe`、`POST /submit`、`POST /kinematics`。二进制 RCB1，不用 base64；保留 2.0/2.1 请求和 `include_depth=True`。RGB、深度序列、本体、控制步、时间、外参共享帧轴。越界关节目标裁剪并报告，错误结构/NaN 在任何执行前拒绝；动作请求断线后不自动重试。

`joint_position` 支持 linear/hold；夹爪在行起点切换原生目标。`ee_pose` 为每臂世界坐标 xyz/wxyz + 原生夹爪命令，逐行 IK，失败保持上一目标并返回 plan。FK/IK 使用固定机器人模型与完整 q；不会隐式读取当前关节作为默认 IK seed。

RGB 始终使用 Nyx + compact_lab。Depth 是同一相机位置、像素网格下的 Genesis 几何 z-depth，单位米，0 表示无效；它不是 Nyx 透明表面路径追踪的深度，透明材质处可能不同。夹爪本体输出实测碰撞几何间隙；spec 同时说明固定 TCP 和原生驱动坐标，Robotiq 的弧度不能当成开度米。

## 评分和成本

预算为 wall clock。默认导出任务 5400 秒；模型 token/成本由 Harbor agent 记录，物理步和模拟时间作为成本记录。旧 input/output 硬额度不再是主流程条件。Benchmark 显式关闭 `max_physics_steps`，本地 Env 默认上限不变。

Harbor 在 main 停止后调用 sim 的 collect；live 进程退出，释放 GPU，才依次启动两个新进程回放。Verifier 使用 separate sandbox；仅接受完整、身份匹配的 sidecar/replay 证据，写 numeric-only reward.json 与 reward.txt。unlimited 同样在独立 verifier 中重放，不接受 agent 写的成功标志。

状态指纹保留整数、判据和拓扑，SI 浮点数规范化至 12 位小数，并排序接触记录；原始最终状态和其哈希同时保留。`deterministic` 表示这些规范化指纹一致。GPU 还可能出现约 `1e-11` 的约束归约差异，故评分另外要求 `replay_consistent`：所有 SI 数值满足固定 `atol=rtol=1e-9`，离散字段、拓扑、步骤数和成功判据完全一致，接触记录按集合匹配。它不是逐任务调大容差，也不会把 `replay_consistent=1` 写成 `deterministic=1`。较大差异、缺失判据、缺失轨迹或 replay 错误均无法成功评分。

完整 tick history 使用私有磁盘 backing，无隐式淘汰；rewind 后未来 ID 作废且不复用。磁盘文件仅用于当前进程的 live 引用恢复，不是可导入的状态文件。公开轨迹为有限数值 NPZ，禁用 pickle。长响应媒体也临时落盘，超过 256 MiB 时先降级深度序列，再降级 raw frames，并写入 `meta.degraded`。

## 模型入口

运行模型使用官方 `harbor run`，`topogym-benchmark` 只负责导出和模拟器工具。`-a` 选择 agent，`-m` 选择模型；没有单独的 `--api-key` 或交互式输入向导。API key 可由 shell 环境、`--env-file /绝对路径/凭据文件` 或 `--agent-env KEY=VALUE` 提供。

| 运行方式 | 模型格式 | 凭据 | 可选端点 |
| --- | --- | --- | --- |
| 官方 `-a opencode` / `-a codex` 的 OpenAI API 接入 | `openai/<模型ID>` | `OPENAI_API_KEY` | `OPENAI_BASE_URL` |
| 官方 `-a claude-code` | `anthropic/<模型ID>` | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` |
| 本项目 CodexOpenRouter | `openrouter/<provider>/<模型ID>` | `OPENROUTER_API_KEY` | `OPENROUTER_BASE_URL` |
| 本项目 CodexChatGPT | `openai/<模型ID>` | `CODEX_AUTH_JSON_PATH`，缺省本机 `~/.codex/auth.json` | 原生登录路径 |

例如在 shell 中输入 OpenAI 模型和 key，无需新建配置文件：

```bash
read -rp '模型 ID（不含 openai/ 前缀）: ' MODEL_ID
read -rsp 'API key: ' OPENAI_API_KEY
echo
export OPENAI_API_KEY
.venv-harbor/bin/harbor run \
  -p "$PWD/runs/harbor_cube_tasks_native/cube-pick-place-base-s0-limited" \
  -a opencode -m "openai/$MODEL_ID" \
  -n 1 -k 1 --jobs-dir "$PWD/runs/harbor_jobs"
```

使用 `--env-file` 时，文件内容为 `OPENAI_API_KEY=...`（或所选 provider 的 key 变量）；自定义端点可另外写 `OPENAI_BASE_URL=...`。模型仍通过 `-m` 传入。真实账号连通性尚未验收。TopoGym 的两个薄 adapter 用法如下：

```bash
# OpenRouter：保留 provider/model 完整 ID，使用 Responses provider。
.venv-harbor/bin/harbor run -p "$TASK_PATH" \
  -a topogym.benchmark.agents:CodexOpenRouter \
  -m "openrouter/<provider>/<模型ID>" --env-file "$PWD/.secrets/harbor.env" \
  --ak reasoning_effort=medium -n 1 -k 1 --jobs-dir "$PWD/runs/harbor_jobs"

# 已有 ChatGPT 登录：由 Harbor 官方 auth.json 注入路径使用。
CODEX_AUTH_JSON_PATH="$LOGIN_FILE" .venv-harbor/bin/harbor run -p "$TASK_PATH" \
  -a topogym.benchmark.agents:CodexChatGPT -m "openai/<模型ID>" \
  -n 1 -k 1 --jobs-dir "$PWD/runs/harbor_jobs"
```

这两个 adapter 复用 Harbor 的安装、执行和用量记录；没有复现参考项目的模型 gateway、provider_only 路由、Flex SSE 重试及 ChatGPT 元数据规避行为。这些模型路由扩展与 simulator API 兼容分开，不能宣称它们具有相同的模型行为。本轮未运行付费模型。

不要直接照搬参考仓库的 `--ak provider_only=...`、`allow_fallbacks`、`dump_requests`：当前 adapter 不支持，Harbor 会拒绝这些参数。OpenRouter adapter 继承官方 Codex 的登录选择逻辑；运行它时不要同时设置 `CODEX_AUTH_JSON_PATH` / `CODEX_FORCE_AUTH_JSON`，否则登录文件优先于 API key。参考项目的 ChatGPT gateway 使用 `chatgpt/openai/<模型ID>` 并只转交 access token；本项目采用官方 auth.json 注入，参数和行为不同。完整对照见[实施记录](../../docs/develop/modules/rcb_harbor_implementation_20260929_zh.md)。

## 验证

```bash
.venv-gs121-nyx/bin/python -m pytest tests/benchmark tests/contracts tests/recording_data -q
.venv-harbor/bin/python -m pytest --confcutdir=tests/benchmark_host tests/benchmark_host -q

# 明确启动 CUDA/Nyx：先冻结源码、实例、机器人资产哈希和报告，再录像、回放。
.venv-gs121-nyx/bin/python scripts/test_benchmark.py \
  --task cube_pick_place --steps 2 --output runs/test_results/benchmark_cube_new

# 实际 HTTP + sidecar 停机回放（本机，不代表 Docker 隔离验收）。
.venv-gs121-nyx/bin/python scripts/test_benchmark.py \
  --http --output runs/test_results/benchmark_http_new
```

当前验收状态及视频见 [实施记录](../../docs/develop/modules/rcb_harbor_implementation_20260929_zh.md)。Task 的 `solution/solve.sh` 在没有合格 oracle 时明确失败，不用占位成功脚本。Cube 的微动作回放通过仅证明基础设施，不证明 13 项任务可解或模型成功。旧的 runs、task_rollouts、demos 和凭据均保留。
