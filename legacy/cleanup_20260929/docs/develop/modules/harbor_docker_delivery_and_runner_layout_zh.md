# TopoGym 的统一 segment rollout、Harbor 接入与 Docker 交付

日期：2026-09-25。状态：**接入设计，尚未实现或进行容器、GPU、模型调用验收。** 本文只规划交付与脚本，不改变当前 simulator API，也不启动延期中的 agent 实验。

> 后续方案已收敛为[共享镜像与 Harbor pipeline 开发计划](harbor_shared_image_pipeline_plan_20260925_zh.md)：镜像与实验 runner 分开维护，运行时自动生成 `harbor_tasks/`，每个任务不再维护 Dockerfile 或源码副本；录像沿用 `task_rollouts/`。下文保留方案讨论，发生目录或职责差异时以新计划为准。

## 0. 当前优先方案：一套 segment rollout，加一套 Harbor 模板

**所有任务共享同一套 segment rollout 是可行的，也是当前优先建议。** 前一版把完整 Docker 交付、容器隔离和模块拆分一起展开了；这些不都是 Harbor 的最低要求。本文第 0 节是最小实验结构，第 1～10 节保留为按需采用的完整交付设计，不要求第一版把其中所有目录、镜像和脚本都实现。

### 0.1 一次完整 rollout 对应一个 Harbor trial

我们希望运行的是：

```text
固定 task / 难度配置 / seed
  → 管理方创建并 reset Env
  → 发布初始 RGB
  → agent 读取观测，生成一个 segment 的 scripted policy
  → 通用 segment 执行器接收 policy，驱动 simulator
  → 完成录制，发布本段反馈
  → agent 读取反馈，生成下一段 policy
  → 重复，直到环境终止或预算耗尽
  → verifier 读取最终证据，输出 reward
```

建议映射为：一个固定实例是一个 Harbor task；agent 对它的一次完整尝试是一个 trial；一个 Job 可以包含多个实例和多次尝试。**segment 是 trial 内部的一次交互，不需要每段新开一个 `harbor run`，也不需要每段启动一个全新的 agent 会话。** Harbor 的 Job/Trial 定义见 [官方运行说明](https://docs.harborframework.com/core-concepts/jobs/run-a-job)。

难度 sweep 可以为不同配置分别启动 Job，也可以将它们准备成一个任务集合，由一次 `harbor run -p <集合目录>` 批量运行。两种方式都复用同一个 rollout 实现；配置应在 trial 开始前固定。这里“难度”由实验配置映射到现有 task/variation/参数，不假设目前所有 Task 都已提供统一的 `difficulty` 字段。

### 0.2 用户维护的最简目录

以下是拟新增结构，包含模板与入口，尚无可执行实现：

```text
harbor_runners/
├── instruction.md                # 所有任务共用的说明模板，填入目标、工具与预算
├── task.toml                     # 所有任务共用的 Harbor 配置模板
├── environment/
│   └── Dockerfile                # 共用环境模板：安装/引用 TopoGym 与段执行器
├── tests/
│   └── test.sh                   # 共用 verifier 入口，调用统一验收逻辑
├── run.py                        # 解析实例、生成标准包、调用 harbor run
└── task_rollouts/
    ├── cast_coil_rollout.py       # 读取 Cast Coil 配置，调用 run.py 的共用函数
    └── cast_keyhole_rollout.py    # 读取 Cast Keyhole 配置，调用同一函数
```

上述 `instruction.md`、`task.toml` 和环境文件作为源码模板使用；其中有占位参数时，整个源码目录不是可直接执行的评测实例。`run.py` 将它们解析到独立的运行目录，再把那个目录交给 Harbor。

你提出的 `task_rollouts/` 可以保留。每个脚本只负责选择任务、加载难度/seed、设置实验参数；它们不各自重写“调用模型 → 执行 segment → 读取录像”的循环。若差别全部是配置，后续也可以只保留一个通用入口和多个配置文件；不必为了每个 Task 都增加 Python 文件。

初版可以把原文的 `prepare.py`、`preflight.py`、`run.py` 合为一个 `run.py`；这些独立文件是维护选择，不是 Harbor 规范。`__init__.py` 等 Python 打包文件按实际调用方式补齐，图中省略。

### 0.3 为什么只有 instruction 和实验脚本还不够

Harbor 的标准评测输入还要回答：agent 在什么环境执行，以及最后如何判断结果。它不会把任意 `cast_coil_rollout.py` 自动识别成完整任务包。标准组成见 [Harbor task 结构](https://docs.harborframework.com/core-concepts/tasks/overview)。

例如，启动脚本为某个实例生成：

```text
runs/harbor/<run-id>/prepared_tasks/cast-coil-easy-s0/
├── instruction.md                # 已填好具体目标的说明
├── task.toml                     # 已解析的 Harbor 配置
├── environment/
│   ├── Dockerfile                # 从唯一模板生成
│   └── instance.json             # 本次解析后的配置；我们自定义的文件
└── tests/
    └── test.sh                   # 从唯一验收入口生成
```

然后调用标准入口：

```bash
harbor run -p runs/harbor/<run-id>/prepared_tasks/cast-coil-easy-s0 \
  -a <agent> -m <model>
```

这里展示的是命令形态；尖括号需要替换，模板和执行器也尚待实现。`harbor run rollout` 不是本文假定存在的 Harbor 原生子命令；“rollout”是我们的任务内容，可以由我们的 Python/CLI 入口封装上述调用。

`test.sh` 调用共用验收逻辑，把 simulator 的真实结果写成 `/logs/verifier/reward.txt` 或 `reward.json`；它在 agent 执行结束后验收，不能承担给 agent 提供段间反馈的职责。[Harbor verifier 约定](https://docs.harborframework.com/core-concepts/tasks/verifier)

这些运行时生成的文件只是小型配置与入口，不复制 `topogym/tasks/`，也不要求人工维护一个“任务 × 难度 × seed”的源码目录树。

### 0.4 segment 执行能力由一套共用代码提供

`harbor_runners/` 保持简单的前提，是镜像/运行环境中已经安装了统一 segment 执行能力。当前本地 simulator API 可复用，但接收 policy、保持 episode、完成录制并发布结果的适配仍需实现；可放在后文规划的 `topogym/agents/rollout/`，只维护一份。

面向 agent，可以将接口做成“提交一个 policy 文件，等待这一段执行完并获得反馈目录”。例如拟提供 `topogym-rollout execute /workspace/segment_001.py`；这是设计示意，不是当前已存在的命令。内部由独立 policy 执行进程通过受控接口驱动持有 Env 的 worker；提交整个 segment 不要求在 Env 进程中直接执行 agent 的任意代码。

反馈可采用下面的结构，其中 `/rollout` 是**当前 trial 环境内**的路径：

```text
/rollout/
├── initial/                     # 初始状态的 RGB 与可见元数据
├── segments/
│   ├── 0001/
│   │   ├── recordings/          # 公共 recording 模块产出的媒体
│   │   └── result.json          # 完成状态、帧/视频路径、允许的反馈
│   └── 0002/
└── status.json                  # 当前有效状态、terminal 与停止原因
```

不同 trial 的 `/rollout` 相互隔离，结束后归档到宿主机对应的 `runs/harbor/` 结果中。初始 RGB 在 agent 第一次决策前就绪；本段录像写完后再发布完成结果。下一段继续当前 Env，避免每次执行 policy 都新建/reset 场景。terminal、失败和预算耗尽由运行时区分，不能用 agent 文本自报成功代替任务判据。录像仍复用现有公共 recording，所选 agent 的图像/视频读取能力也需验证。

标准 coding agent 可以在一次会话内反复调用该工具。`instruction.md` 说明这个使用流程，但提示本身不能保证 agent 一定循环到 terminal：它也可能提前返回或超时。普通接入应如实记录这种结束，并由 verifier 判定；如果实验要求强制“每轮必须提交一段、读取反馈、且只在 terminal 后结束”，就需要在 agent adapter/控制逻辑中落实该协议。Harbor 支持 [自定义 agent](https://docs.harborframework.com/core-concepts/agents/custom-agents)，但我们自己调用模型来写这个强制循环时，它已经属于 agent 实现，需要明确所测对象，不能称为未修改的外部 coding agent。

### 0.5 Docker 是交付方式，不决定 rollout 的数量和形态

前一版可在本机运行，也可交给另一台机器运行；它不要求远程 Docker。可以先在本机安装 Harbor，由其启动包含 TopoGym 的任务环境，验证同一套 segment 流程，之后再给 Harbor 本身套 runner 镜像，保持同样的实验入口。

初版也可以让 agent 与 simulator worker 分属同一个任务容器内的不同进程；单容器有利于验证流程，但进程分开不自动形成防篡改边界。后文的三镜像/Compose 方案在需要隔离、依赖拆分或正式交付时采用。无论部署选择如何，普通操作方无 reset、trial 间隔离、段内预算与结果验收等协议都保持一致。

## 1. 按需采用的完整 Docker 交付方案

需要进一步向测试方交付配套镜像、拆分运行角色时，可在第 0 节的通用 rollout 上扩展为：

> **根目录一个多阶段 Dockerfile + `harbor_runners/` 中的实验脚本、配置和公共模板 + 运行时生成的 Harbor 标准任务包。**

`harbor_runners/` **不维护第二份 `topogym/tasks/`，也不逐任务复制 simulator 源码**。它根据现有任务注册表和实验配置，准备 Harbor 能读懂的输入，然后调用真实的 `harbor run`。

需要区分下面三个概念：

| 名称 | 本项目中负责什么 | 代码/文件位置 |
| --- | --- | --- |
| TopoGym Task | 场景、任务状态、变体与成功判据 | 现有 `topogym/tasks/` |
| TopoGym Env | 创建、reset、step、观测、历史、权限 | 现有 `topogym/simulator/` |
| Harbor task package | 一次评测实例的说明、容器配置与验收入口 | **运行时生成**在 `runs/harbor/.../prepared_tasks/` |

Harbor 的 environment 指供 agent 执行命令、读写文件的运行环境；其中可以有 TopoGym simulator 服务，但它并不是 TopoGym 的 `Env` 对象。[Harbor environment 定义](https://docs.harborframework.com/core-concepts/tasks/environment)

所以，“不在 `harbor_runners/` 中存任务实现”完全可行；“完全不准备 Harbor 标准任务输入，只提供任意脚本却直接让 `harbor run` 理解它”则不符合本文选用的 Harbor 工作流。

## 2. 完整交付方案与现有项目的源码目录 map

标记：`[现有]` 表示复用；`[新增]` 表示采用完整交付方案时的建议；`[调整]` 表示需补充配置。此图是第 0 节简化目录的展开形式，两套源码布局择一，不同时维护两份模板。这里只列与交付有关的目录，不是完整源码清单。

```text
topogym/                                           # 仓库根目录
├── Dockerfile                         [新增]      # 一个文件，定义多个镜像构建目标
├── .dockerignore                      [新增]      # 排除产物、缓存、密钥等构建无关内容
├── pyproject.toml                     [调整]      # 安装 runner、活动 rollout 模块和模板
│
├── requirements/                      [现有]
│   ├── uv-topogym-gs121-nyx.txt         [现有]      # 现有 Genesis/Nyx 约束输入
│   ├── uv-topogym-fem-ipc.txt           [现有]      # 现有 FEM/IPC 约束输入
│   ├── harbor-runner.lock.txt          [新增]      # 经验证的 Harbor 与 runner 依赖锁定
│   └── rollout-simulator.lock.txt      [新增]      # 经验证的仿真/录制完整依赖锁定
│
├── scripts/                           [现有]
│   ├── build_rollout_images.sh         [新增]      # 开发者构建、标记各目标镜像
│   └── run_rollout.sh                  [新增]      # 测试方宿主机入口，启动 runner 容器
│
├── harbor_runners/                    [新增]      # Python 包；不放任务实现副本
│   ├── README.md                                  # 面向实验使用者的简短说明
│   ├── __init__.py
│   ├── __main__.py                                # python -m harbor_runners 的入口
│   ├── preflight.py                               # 依赖、镜像、宿主机与实例资格检查
│   ├── prepare.py                                 # 选择实例并生成 Harbor 标准输入
│   ├── run.py                                     # 调用 harbor run；转发退出码和信号
│   ├── verify.py                                  # 可信仿真证据 → Harbor 数值 reward
│   ├── profiles/
│   │   └── default.json                           # 我们的任务选择/seed/agent/预算配置
│   └── templates/                                 # 所有任务共用，不按 task 复制一套
│       ├── instruction.md.tmpl
│       ├── task.toml.tmpl
│       ├── docker-compose.yaml.tmpl
│       └── test.sh.tmpl
│
├── topogym/                           [现有]      # 唯一的仿真实现
│   ├── __init__.py                                 # 公开 env_list / make
│   ├── simulator/                                 # Env、配置、interaction、历史与权限
│   ├── config/                                    # registry、机器人/场景配置等
│   ├── tasks/                                     # Task 定义、成功判据
│   │   └── <task_name>/                           # common.py 与 <task>_easy/medium/hard.py
│   ├── assets/                                    # 当前活动资产构建与资源
│   ├── world/                                     # Genesis 物理世界
│   ├── sensors/                                   # 公共 SensorFrame、Nyx 渲染
│   ├── recording/                                 # 公共录制、验证、归档
│   ├── evaluation/                                # 只读评估，不另定义 Task 成功
│   └── agents/
│       ├── deferred/                 [现有]       # 旧代码继续延期，不作为运行入口
│       └── rollout/                  [新增]       # 与 Harbor 无关的通用仿真服务适配
│           ├── __init__.py
│           ├── worker.py                           # 持有 Env，提供受控服务、可信证据
│           ├── client.py                           # agent 使用的轻量 SDK / CLI
│           └── segment.py                          # 动作段边界、预算、录制生命周期
│
├── tests/                             [现有]
│   └── harbor/                       [新增]       # 生成包、服务合同、容器闭环测试
├── docs/develop/modules/              [现有]
│   └── harbor_docker_delivery_and_runner_layout_zh.md
└── runs/                              [现有]
    └── harbor/                       [运行生成]   # 输入快照与实验结果，按 run/trial 隔离
```

这里没有新增根目录 `env/`，也没有新增另一套物理循环。当前应调用的入口见 [simulator/api.py](../../../topogym/simulator/api.py)、[Env](../../../topogym/simulator/env.py) 和 [本地 API 文档](simulator_api_zh.md)。

## 3. Dockerfile 应放哪里、里面放什么

### 3.1 根目录保留一个 Dockerfile，按角色构建镜像

Dockerfile 可以用多个 `FROM ... AS <target>` 定义构建阶段。每条 `docker build --target ...` 选择一个目标，输出对应镜像；共享阶段可以通过 `COPY --from=...` 提供构建产物。`docker run` 启动的是镜像，而不是重新执行 Dockerfile。[Docker 多阶段构建](https://docs.docker.com/build/building/multi-stage/)

建议这个文件包含一个公共构建阶段和三个交付目标：

| 阶段/目标 | 应包含的内容 | 运行时职责 |
| --- | --- | --- |
| `project-build` | 同一源码快照，构建 TopoGym wheel；准备轻量客户端文件 | 中间阶段，不交付运行 |
| `runner` | Python、固定版本 Harbor、Docker CLI/Compose、完整 TopoGym/`harbor_runners` 安装及所需依赖 | 默认入口 `python -m harbor_runners`，准备并启动实验 |
| `simulator` | 同版本 TopoGym、Genesis、Nyx、所选任务所需 FEM/IPC、视频编码依赖、活动资产 | 运行 `topogym.agents.rollout.worker`，持有一个 Env |
| `agent` | Shell、Python、所选 Harbor agent adapter 所需工具、轻量客户端及操作说明 | 作为 Harbor 的 agent 工作环境，供其写代码、执行和看反馈 |

runner 安装完整项目是为了交付入口、任务发现和配置解析；物理执行发生在 simulator 容器。第一版允许 runner 镜像较大，依赖应完整锁定，不能用未经验证的 `pip --no-deps` 跳过安装后宣称完整可用。以后再优化依赖拆分。

agent 镜像不需要完整物理引擎。建议将 `client.py` 设计成仅依赖标准库的独立模块，在构建时从唯一源码路径安装为轻量客户端文件。它不依赖从完整 `topogym` 包导入重型运行时。**从同一源码构建镜像中的安装副本，是正常发布；在仓库多个目录人工维护同一份 Task，是本文避免的代码重复。**

coding agent 本体的安装/启动应遵循固定 Harbor adapter 的方式。有些 adapter 在 trial setup 时安装 CLI；要实现明确的版本和离线缓存策略，需要逐 adapter 验证，不能仅凭 runner 镜像存在就承诺任意 agent 的依赖都已预装。

下面是未来 `build_rollout_images.sh` 应封装的构建形态，**当前还没有对应 Dockerfile，不能直接运行**：

```bash
docker build -f Dockerfile --target runner -t topogym-harbor:local .
docker build -f Dockerfile --target simulator -t topogym-simulator:local .
docker build -f Dockerfile --target agent -t topogym-agent:local .
```

一次调用脚本完成三个构建即可；测试方通常直接拉取我们发布的三个版本配套镜像。发布时记录镜像 digest，不能仅依赖可被覆盖的 `latest`。三个目标可以共享构建产物，但构建 runner 目标**不会自动发布另外两个镜像**。

### 3.2 不需要每个任务再写一个 Dockerfile

本方案生成的 `environment/docker-compose.yaml` 只引用现成的 agent/simulator 镜像。切换 Task 时改变 `instance.json`，不重新复制任务源码或构建物理环境。

Harbor 支持通过 `environment/docker-compose.yaml` 定义多容器环境；因此这里不需要每个任务的 `environment/Dockerfile`。单容器方案也可用 `task.toml` 的预构建镜像字段，但本文选择 Compose，不把单镜像快捷配置与多服务配置混用。[Harbor environment 配置](https://docs.harborframework.com/core-concepts/tasks/environment)

因此旧建议中的 `docker/Dockerfile.simulator` 和逐任务 `environment/Dockerfile` **在这版目录中都可以省去**。若以后拆文件，只是镜像维护方式变化，不是 Harbor 要求每个 TopoGym Task 都有一个独立 Dockerfile。

### 3.3 构建安装依赖，启动时选择实验

Dockerfile 的 `RUN` 用于构建镜像时安装依赖、构建项目；不要把真正的 `harbor run` 实验写进 `RUN`。任务选择、模型名、运行预算、API key 都是运行参数，最终由 `ENTRYPOINT` 启动的 runner 使用。

`.dockerignore` 应排除 `.git/`、本地虚拟环境、缓存、`runs/`、历史报告/录像、密钥文件等。应按当前资产依赖检查保留范围，不能把运行必需的资源与演示视频一起误排除。

Docker 镜像负责容器内的用户态依赖。测试方宿主机仍需可用的 Docker；本方案的 Nyx/CUDA 运行还需要兼容的 GPU 驱动与容器 GPU 支持。我们可以提供检查入口，但 Dockerfile 本身不能替宿主机安装内核驱动。初版交付目标应明确为已验收的 Linux/NVIDIA 环境。

## 4. 容器之间怎样连接

```text
测试方宿主机
  scripts/run_rollout.sh
       │ 启动一个 runner 容器
       ▼
  runner：python -m harbor_runners
       │ prepare → harbor run
       │ 通过宿主机 Docker daemon 管理 trial
       ▼
  Harbor 为每个 trial 创建独立的一组容器/网络/卷
       ├── main：coding agent + Python 脚本 + TopoGym client
       │       │ 受控请求：step / observe / segment 等
       │       ▼
       └── simulator：worker → make → Env.reset → interaction.step
               │
               └── 公共 recording → 本 trial 的反馈目录
                       └── main 只读访问视频、关键帧、段结果
```

这里 runner 与 trial 容器由同一个宿主机 Docker daemon 管理，是同级容器。runner 内不再启动第二个 Docker daemon；只有 runner 获得管理 Docker 的通道，agent/simulator 不挂载 Docker socket。

Compose 中的 agent 主服务采用 Harbor 当前的 `main` 名称；simulator 为我们增加的服务。主服务名称应随锁定版本验证，来源见 [Harbor 常量定义](https://github.com/harbor-framework/harbor/blob/main/src/harbor/constants.py)。GPU 分配应落实到 simulator 服务并实际验收，不能仅填写 `task.toml` 的资源意图就假设辅助服务已获得 GPU。

生成的 Compose 配置还需定义 worker 的就绪检查：完成实例创建、reset 和必要初始化后才报告 ready，主服务依赖这个状态再进入可用阶段。`main` 提供持续可用的执行环境和可写工作目录，具体 agent 进程由 Harbor 启动；容器已经启动本身不代表 simulator 可以接收动作。

有一个必须在 `run_rollout.sh` 中处理的路径问题：**bind mount 的源路径由宿主机 Docker daemon 解释，不由 runner 容器解释。** 建议把宿主机的运行根目录以同一个绝对路径挂入 runner，生成包和需挂载的临时文件都放在这里。还需核对锁定 Harbor 版本的临时目录配置；不能把仅存在于 runner `/tmp` 的路径直接交给宿主机 daemon。[Docker bind mount 规则](https://docs.docker.com/engine/storage/bind-mounts/)

为每个 trial 创建独立的观测卷、worker 数据卷和网络，避免固定 `container_name`、公共宿主机端口或跨 trial 共用可写目录。默认先串行运行，之后根据 GPU 实测容量增加并发。

## 5. 完整交付方案中 `harbor_runners/` 的脚本分工

这些是我们的文件命名与分工建议。Harbor 约束的是它消费的任务格式和执行合同，并不要求我们的源码目录必须叫这些名字。

| 文件 | 输入 → 输出 | 责任边界 |
| --- | --- | --- |
| `scripts/build_rollout_images.sh` | 源码版本、镜像前缀 → 三个镜像与版本清单 | 只构建发布，不启动评测 |
| `scripts/run_rollout.sh` | profile、agent/model、凭据环境变量 → runner 容器 | 宿主机路径、卷、Docker 连接、退出码与信号 |
| `harbor_runners/__main__.py` | CLI 参数 → `prepare` / `run` 子命令 | 提供唯一 Python 用户入口 |
| `preflight.py` | 配置、已装版本、镜像信息 → 检查报告 | 验证版本、所选 agent、资产与任务资格；运行检查还需 GPU/worker ready |
| `prepare.py` | profile + 当前任务元数据 + 镜像身份 → 标准任务目录、Harbor job 配置、manifest | 实例选择、模板渲染、模式验证；不推进物理 |
| `run.py` | 已准备的任务集合/Harbor 配置 → Harbor Job | 调用真实 CLI，保存命令与退出状态；不写自己的 LLM 或 trial 调度循环 |
| `verify.py` | 当前 trial 的可信 worker 最终证据 → reward 和诊断 | 复用 Task 判据，不根据 agent 自报的 `success.json` 打分 |
| `profiles/default.json` | 实验作者维护的选择与默认参数 | 定义测什么、怎么测；不复制 Task 几何或默认场景实现 |
| `templates/*` | 实例身份、预算、镜像引用等 → Harbor 标准文件 | 同一套模板服务多个 Task |

`run.py` 可以对模型/agent 组合依次提交多个 Harbor Job；每个 Job 内的 attempt、重试、并发、agent 生命周期和结果格式继续交给 Harbor。实际调用使用参数列表，不拼接带用户输入的 shell 字符串。

Harbor 可直接运行本地任务集合并选择 agent/model；输出、并发、attempt 数等由其 CLI/JobConfig 表达。[Harbor Job 入口](https://docs.harborframework.com/core-concepts/jobs/run-a-job)

调用形态如下，其中路径和变量由 runner 解析，示例不指定实际模型：

```bash
harbor run \
  -p "${PREPARED_TASKS_DIR}" \
  -a "${AGENT_NAME}" \
  -m "${MODEL_NAME}" \
  -o "${HARBOR_JOBS_DIR}" \
  -n 1 -k 1
```

`-n` 是并发 trial 数，`-k` 是每个任务的 attempt 数。生成配置时应使用**镜像中锁定的 Harbor 版本**验证字段；不要把我们自定义的 profile JSON 直接宣称为 Harbor JobConfig。

### 5.1 profile 应保存哪些内容

建议包含：任务 ID、variation 选择、seed 列表、机器人选择、允许的控制/观测模式、是否启用特权、每段与整个 trial 的预算，以及默认 agent、重复次数、并发。模型名和 API key 可在启动时提供；key 不写入 profile 或归档配置。

Task 名单通过当前 `topogym.env_list(details=True)` 与 registry 解析；配置字段参照 [SimulatorConfig](../../../topogym/simulator/config.py)。场景资产、几何和默认值继续由 Task/variation/配置模块决定，runner 只选择和覆盖允许的参数。

任务的人类可读目标、操作限制、反馈读取方法必须有人维护或审核。模板可以复用，但不能假设从 Python 类名就能自动生成完整可靠的 `instruction.md`。

固定 seed 的一个实例可以对应一个生成包。Harbor 的多次 attempt 测同一个实例；若要测不同 seed，明确生成不同实例包，避免把“多次采样 agent”与“切换场景”混为一谈。

## 6. 运行时生成什么：Harbor 标准任务包 map

```text
runs/harbor/<run-id>/
├── manifest.json                          # 源码/依赖/镜像/模板版本与哈希
├── profile.resolved.json                  # 去除秘密后的实验配置快照
├── job.json                               # 经过固定 Harbor 版本验证的 JobConfig
├── prepared_tasks/                        # 交给 harbor run -p 的本地任务集合
│   └── <task-id>--<variation-id>--s<seed>/
│       ├── instruction.md                 # 单数 instruction，Harbor 标准名称
│       ├── task.toml                      # 超时、元数据、环境/验收等 Harbor 配置
│       ├── environment/
│       │   ├── docker-compose.yaml        # 引用 agent/simulator 镜像
│       │   └── instance.json              # 只读挂载给 worker 的解析后实例配置
│       └── tests/
│           ├── test.sh                    # Harbor 标准 verifier 入口
│           └── verify.py                  # 从唯一 verifier 源文件生成的发布副本
├── jobs/                                  # Harbor 自己生成的 job/trial 输出
│   └── ...                                # 保持固定 Harbor 版本的目录语义
└── tmp/                                   # 需要宿主机可见的临时输入
```

这符合 Harbor 的 `instruction.md`、`task.toml`、environment 与 `tests/test.sh` 约定。`solution/solve.sh` 仅在有经过验证的参考解时追加；不生成虚假的 oracle 方案。[Harbor 任务结构](https://docs.harborframework.com/core-concepts/tasks/overview)

这里的 `instance.json` 是**我们自己的约定**，不是 Harbor 原生字段。它用于让 worker 调用已有工厂，例如 `make(task_id, **configuration)`，然后由管理方 `reset(seed=...)`；Task 源码由镜像内安装的 TopoGym 提供。生成包不含 `blanket_flatten.py`、`base.py` 或整个 `topogym/`。

生成物虽不逐个手工维护，仍要作为本次评测输入归档。包中的镜像引用和配置文件应足够让另一台已满足宿主机要求的机器复现；避免写入开发者 checkout 的绝对路径或软链接。运行时挂载路径由启动器在目标机器解析。

### 6.1 严格遵循 Harbor 的落点

| Harbor 合同 | 本方案怎样满足 |
| --- | --- |
| 标准 Task 输入 | `prepare.py` 输出上述目录并使用锁定版本校验 |
| 可启动的 environment | 官方 Docker/Compose 后端启动配套镜像 |
| agent 的安装和执行 | 使用 Harbor agent adapter；尚未收录的 agent 按其扩展接口接入 |
| Trial/Job 生命周期 | `run.py` 调用 `harbor run`，不接管 agent 的内部工具循环 |
| verifier 入口和 reward | `tests/test.sh` 调用统一 verifier，输出到规定位置 |
| 结果与轨迹 | 保留 Harbor 输出；补充带 trial/episode 身份的仿真证据 |

这不要求修改 Harbor 核心，也不要求把每个 TopoGym Task 改写成 Harbor 的 Python 类。对未收录 agent 的扩展应依据 [Harbor custom agents](https://docs.harborframework.com/core-concepts/agents/custom-agents)，与 simulator 适配分开。

## 7. `worker/client/segment` 如何复用现有 simulator

**当前已有的是本地 Python API，不是已经运行的 HTTP/RPC 服务。** 所以不能只写 `harbor run` 外壳就宣称接入完成；这三个模块是需要新增的通用桥接代码。

### 7.1 `worker.py`：持有环境，而非重写环境

worker 按只读实例配置创建 Env，并在 trial 开始时执行管理方 reset，随后一直存活到 verifier 完成。每个 worker 进程只持有一个已 build Env，符合当前运行边界。

它向 agent 暴露当前 episode 的受控操作。权限沿用 [interaction](../../../topogym/simulator/interaction.py)：

- 普通与特权操作方均不能 `make/reset/close`、换 seed 或修改环境配置。
- agent 可通过客户端操作 `step/observe/render` 等允许接口；请求必须校验参数、身份与预算。
- 特权模式仅增加当前 episode 的 `rewind_to` 与白名单 `get`。回溯后旧未来失效，不可跨 episode；客户端不能自行伪造有效 StateRef。
- 当前普通观测包含配置允许的机器人状态，不等于“只看 RGB”。若某实验要限定纯视觉，需要另外定义并实现观测过滤。

`reset` 因此是**运行管理服务能力**，不是普通 agent 的工具。agent 更换脚本或打开第二个 segment 时，复用当前 episode，不自动 reset。

### 7.2 `client.py`：agent 写的 policy 在哪里执行

agent 在 `main` 容器中编写 Python policy，并通过统一 segment 命令提交执行；执行器可以在该容器内启动 policy 子进程，policy 通过轻量 client 发送受控动作请求。worker 接收结构化请求，不在持有 Env 的进程内直接 `exec` agent 提交的任意 Python。这样对 agent 保持“一次提交一个段”的接口，内部仍复用现有 step。

这样，任意代码执行能力属于 coding agent 的工作环境；核心 Env 对象、实例配置和可信证据保留在 simulator 服务。更换 agent 主要改变 Harbor adapter，不必改变 TopoGym Task。

### 7.3 `segment.py`：动作段和录像的闭环

建议由统一段执行器封装 `begin_segment → step... → end_segment`，worker 负责实际限制和证据记录，agent 只需提交 policy 并读取返回的反馈目录。**这些是拟新增接口名，不是当前已有 simulator 方法。**

```text
发布初始 RGB → agent 写 segment_001.py → 提交统一段执行器
  → client 请求动作 → worker 调用当前 interaction.step
  → segment 结束，公共 RecordingSession 完成并刷新文件
  → 发布完成标记/manifest、视频与可读取的关键帧
  → agent 读取反馈，再编写或修改 segment_002.py
  → 继续同一个 episode
```

录制使用现有 [RecordingSession](../../../topogym/recording/session.py) 和 Env 的公共 frame/lifecycle sink；适配层只管理段边界与输出，不另写取帧循环或视频 writer。段结束需完成编码并原子发布结果，避免 agent 读到仍在写入的 MP4。

反馈目录建议在 worker 中可写、在 agent 中只读，并按 episode/segment 隔离。至少提供开始/结束 StateRef、实际步数、错误、视频和帧清单。出现 rewind 时标记失效段及状态；历史录像可留作审计，不能把旧未来当成有效当前轨迹。

每段限制以及整个 trial 的累计动作、仿真开销、墙钟预算由服务端实施；rewind 不返还已经消耗的预算。Harbor 管理 agent/环境阶段的超时，不能替代动作段协议中的计数与限制。

`instruction.md` 负责告诉 agent 怎样使用这些能力，但仅写说明不能保证进程持续存活、权限约束、视频完整或预算限制。另外，“目录里有 MP4”不代表任意 agent/model 都能看懂视频；要为所选 adapter 验证图片读取能力，并提供相应的关键帧或其他明确允许的反馈形式。

## 8. 验收、结果和可信来源

Harbor 运行 `tests/test.sh`，并读取 `/logs/verifier/reward.txt` 或 `/logs/verifier/reward.json` 中的数值结果。默认共享环境模式下，测试文件在 agent 运行后上传；也可以配置独立 verifier 环境。[Harbor verifier 合同](https://docs.harborframework.com/core-concepts/tasks/verifier)

本项目的 verifier 应从 worker 获取固定 trial/episode 的最终证据，再映射为 Harbor reward：

1. agent 结束后固定最终有效状态，拒绝继续写动作；worker 保持存活供验收取证。
2. 验收接口与普通观测接口分离；管理/验收权限不通过 agent 的配置或可读文件下发。
3. 验证实例身份、有效历史、预算与 Task 结果；最终成功来源于 Task 的完整判据。
4. 输出数值 reward，同时保存诊断与证据；在 Harbor 清理容器/卷之前归档媒体和 worker 记录。

Task 判据尚不完整的实例应排除在正式成功率任务集外，或单独作为接口 smoke suite 报告；基础运行通过不能映射为“任务完成”。网络错误、worker 崩溃、判据不完整和任务失败也应在诊断中区分，避免统一归零后被误读。

共享环境 verifier 不自动形成完整防篡改边界。若正式评测要求抵抗 agent 对执行环境的主动篡改，应采用该固定 Harbor 版本支持的独立 verifier，并验证其访问可信证据的路径；这属于额外的验收部署配置，不改变 Task 源码位置。

媒体反馈应在 trial 内通过共享只读卷或服务可见；不要依赖 trial 结束后的日志同步来给 agent 提供下一段反馈。归档时再将需要的媒体/证据纳入 Harbor 的收集范围。挂在 simulator 私有卷中的文件不会因为主服务有 `/logs` 就自然得到保存。

## 9. 现有打包配置必须补什么

当前 [pyproject.toml](../../../pyproject.toml) 只发现 `topogym*`，并排除整个 `topogym.agents*`；目前也没有 Harbor extra 或 runner 入口。因此，仅新建文件夹还不能保证镜像中安装后可用。

实施时需要完成以下对应修改：

| 当前情况 | 需要的调整 |
| --- | --- |
| 不包含 `harbor_runners` | 纳入包发现；注册入口或支持 `python -m harbor_runners` |
| 排除整个 `topogym.agents*` | 纳入新的活动 `rollout` 包，同时继续排除 `deferred` |
| 模板/profile 非 Python 文件 | 纳入 package data；通过包资源定位，不依赖源码工作目录 |
| TopoGym 依赖并不等于完整 Nyx/FEM/Harbor 交付依赖 | 在现有约束基础上求解、锁定、验收两个角色的完整依赖集 |
| 资源可能涉及构建路径与配置 | 从安装后的包/固定镜像位置解析资源，记录资产身份 |
| verifier 要在轻量 agent 环境执行 | 将统一 `verify.py` 作为生成包的测试辅助文件；其依赖提前安装，不临时安装整套物理引擎 |

建议让 `verify.py` 通过 worker 取证，只依赖轻量标准库协议；Task 判据仍由 worker 内的 TopoGym 执行。无论客户端还是 verifier 的发布副本，都由同一源码和构建流程产生，记录哈希，不人工维护第二份。

运行镜像还需包含当前活动任务依赖的资产，而不只是 Python 文件。现有 Nyx 与 FEM 约束参见 [Nyx 依赖](../../../requirements/uv-topogym-gs121-nyx.txt) 和 [FEM/IPC 依赖](../../../requirements/uv-topogym-fem-ipc.txt)。本文不预填一个未经安装与验收的 Harbor 版本号。

## 10. 最终交付给测试方的操作与实施顺序

### 10.1 预期用户入口

以下是**待实现的使用形式**。测试方有满足要求的宿主机，获得我们发布的启动脚本和配套镜像后，无需在宿主机安装 Python、TopoGym 或 Harbor：

```bash
./scripts/run_rollout.sh \
  --profile default \
  --agent '<已验收的 agent 名>' \
  --model '<该 agent 支持的 model 名>'
```

API key 由所选 provider/adapter 规定的环境变量或受支持凭据方式传入。启动器只转发所需凭据，不把 key 写进镜像、模板、实例或输出 manifest。若发行版固定默认 agent/profile，则用户通常只需提供 model 和凭据；这不等于任意 agent 都有相同认证协议或相同模型能力。

入口内部依次执行：宿主机/镜像检查 → 启动 runner → 解析 profile → 生成标准任务包 → 调用 Harbor → trial 内执行 agent/segment 闭环 → verifier → 归档结果。构建镜像与运行实验是分开的操作，测试方使用发布镜像时不必重新构建源码。

### 10.2 建议的实施顺序与完成依据

| 顺序 | 实现范围 | 通过什么判断完成 |
| --- | --- | --- |
| 1 | `prepare.py`、模板、profile、打包资源 | 脱离源码 cwd 的已安装包可生成输入；锁定 Harbor 版本能解析；生成包无 Task 源码副本 |
| 2 | worker/client/segment | 普通权限、episode 生命周期、段间持久状态、预算、录像完成语义通过合同测试 |
| 3 | 三个镜像与启动脚本 | 无宿主机 Python 环境也能启动；GPU、资源、挂载和退出清理通过真实检查 |
| 4 | 单实例 Harbor 闭环 | 采用已验证参考脚本；执行、取反馈、验收、结果归档贯通 |
| 5 | 一个实际 coding agent | 它能写并执行至少两段 policy，读取实际反馈后继续；记录所用 model/adapter 版本 |
| 6 | 多实例/多次运行 | seed 与 attempt 语义清楚；trial 隔离、失败归因、并发与复现得到验证 |

当前阶段只产出本设计文档。后续落地的核心交付是：**一处维护 Task/Env，一套通用 worker/client，通过生成的标准任务包交给 Harbor 执行；Docker 把这套实现和固定版本依赖打包给测试方。**
