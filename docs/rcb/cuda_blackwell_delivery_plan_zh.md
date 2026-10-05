# RTX PRO 6000 Blackwell：CUDA 交付修复工程计划

日期：2026-09-30。状态：分析与计划，尚未修改运行依赖、构建新镜像或完成 Blackwell 验收。

范围：修复 Docker difficulty eval 在 RTX PRO 6000 Blackwell 上的运行兼容性，同时保留 RTX 4090 支持。沿用现有 Bash → Python 调度器 → Harbor 链路；不改变 13 tasks、三难度、双模式、每难度默认一个样本、每个 agent 阶段默认 21600 秒的实验定义。

## 1. 反馈意味着什么

反馈包含两个独立问题：对方判断 CUDA 栈与 GPU 不兼容；借用 GPU 的可用时间不足以完成当前实验规模。升级 CUDA 不会自动解决实验排期。

“Image 现在是 13.0”尚不能作为版本证据。它可能指云平台基础镜像、容器里的 Toolkit、PyTorch 使用的 CUDA，也可能只是 `nvidia-smi` 显示的驱动支持上限。后者不是容器实际加载的 CUDA runtime 版本。[NVIDIA nvidia-smi 文档](https://docs.nvidia.com/deploy/nvidia-smi/index.html)

需要用实际 GPU 型号和 compute capability 区分 RTX PRO 6000 Blackwell 与 RTX 6000 Ada 等同名近似型号。NVIDIA 列出的 Blackwell 工作站、Max-Q 和服务器版本均为 compute capability 12.0（`sm_120`），4090 为 8.9。[NVIDIA GPU 表](https://developer.nvidia.com/cuda/gpus)

工程目标是让每条 GPU 执行路径具有可运行的内核、兼容的用户态库与驱动。不能仅检查版本数字，也不要求所有组件的版本字符串相同；controller/client 镜像无需安装 CUDA。CUDA 12.8 已加入 `sm_120` 编译支持。[CUDA 12.8 发布说明](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html)

## 2. 已确认事实与尚缺的证据

本轮基于提交 `e3a8ec7` 及当前工作区只读检查。工作区另有开发改动，实施时冻结独立源码快照，不覆盖其他会话修改。

| 项目 | 本轮证据 | 判断边界 |
| --- | --- | --- |
| simulator 镜像 | `images/topogym/Dockerfile` 使用 Python 3.11.15 slim，安装命令为 `--torch-backend cu126` | Dockerfile 不是 CUDA 13.0 基础镜像；对方实际运行的镜像仍待核对 |
| runtime 锁 | `torch==2.12.0+cu126`、`torchvision==0.27.0+cu126`，CUDA runtime/NVRTC 等也锁定 12.6 系列 | 不能只替换 Dockerfile 中一个字符串 |
| 本地环境 | 包元数据显示同一 torch/torchvision 版本；Genesis 1.2.1、quadrants 1.0.2、pyuipc 0.0.25、gs-nyx 0.1.3、plugin 0.1.4 | 本地 venv 不等于对方镜像，必须在运行镜像内复核 |
| 本地 IPC CUDA 库 | `cuobjdump --list-elf` 只列出 `sm_89`；`--list-ptx` 未列出 PTX | 此文件不能据此宣称支持 `sm_120`；它的发行 wheel/镜像来源尚需核对 |
| IPC 版本耦合 | `topogym/world/physics/ipc.py:require_episode_checkpoint` 要求 Genesis 1.2.1 / pyuipc 0.0.25 | 升级 pyuipc 会触发版本约束，且可能改变 native dump/recover；不能仅放宽判断 |
| 现有 `check` | `scripts/difficulty_delivery.py:GPU_CHECK` 执行 torch 小数组、同步、包版本、Genesis import、资产和 Vulkan 检查 | 没有完整 Genesis JIT、IPC 步进/恢复或 Nyx 实际出图验证 |
| 受影响物理路径 | Rope Threading、Knot 使用 FEM/IPC；Blanket 使用 PBD cloth | 只验证 Cast Coil / Cast Keyhole 不覆盖软体后端 |
| 对方故障 | 当前只有聊天反馈，没有异常栈、镜像 ID、硬件版本报告 | 不能把具体首个失败点或唯一根因写成已复现 |

本地 IPC 文件：`.venv-gs121-nyx/lib/python3.11/site-packages/uipc/_native/libuipc_backend_cuda.so`，SHA-256 为 `404c8e6234b5b3dc27e6db1484cff31d4e95c315b888c760ba5e4524d325b39a`。本轮检查未启动物理或模型实验。

需要纠正反馈附件中的两个推断：

- `torch.cuda.get_arch_list()` 中看不到某个 `sm_*`，不应单独作为所有内核均无兼容代码的证明；需核对 cubin/PTX 并执行实际算子。CUDA 12.8 之前构建的应用若带合适 PTX，也可能在新 GPU 上运行。
- 架构兼容不是“编号小于最大编号就能运行”。例如 8.x 的 cubin 不能据此用于 9.x 或 12.x；8.9 可利用合适的同主版本 cubin，跨主版本通常需要 PTX 或重新构建。条件架构的 PTX 还有额外限制。[NVIDIA Blackwell 兼容指南](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/index.html)

## 3. 目标依赖组合与决策

### 3.1 优先验证 CUDA 12.8 路线

| 组件 | 首选候选 | 决策原则 |
| --- | --- | --- |
| Python | 保持 runtime 3.11.15，controller/client 维持原版本 | 不把 Python 升级混入此次迁移 |
| PyTorch / torchvision | `2.11.0+cu128` / `0.26.0+cu128` | 官方索引存在 CPython 3.11 Linux x86_64 wheel；本轮临时完整依赖求解已通过，仍需 Genesis 运行回归，见第 9 节 |
| CUDA 用户态库 | 重新求解并锁定 cu128 组合的全部传递依赖与 SHA-256 | 不手工沿用 cu126 wheel 的哈希，不用宿主 CUDA 或临时 pip 覆盖 |
| Genesis / quadrants | 优先保持 1.2.1 / 1.0.2 | 必须验证目标卡的 JIT 与实际物理步进；不能用 import 成功代替 |
| pyuipc | 优先对 0.0.25 对应源码重建多架构 wheel | 保持现有 checkpoint ABI/API；目标至少包含 `sm_89`、`sm_120` |
| Nyx / plugin | 优先保持 0.1.3 / 0.1.4 | 实测 RGB、动态相机和依赖库加载；单个 OIDN 库包含 `sm_120` 不等于完整渲染链路通过 |

PyTorch 官方已说明 2.12 不再提供 CUDA 12.8 预编译包。因此 `torch==2.12.0` 保持不动、只把 `cu126` 改成 `cu128` 不是可执行的锁定方案。上述候选来自本轮查看的官方索引，仍须以实施时的 resolver 结果和下载哈希为准。[PyTorch 2.12 支持矩阵调整](https://dev-discuss.pytorch.org/t/introducing-cuda-13-2-and-deprecating-cuda-12-8-release-2-12/3337)、[torch cu128 索引](https://download.pytorch.org/whl/cu128/torch/)、[torchvision cu128 索引](https://download.pytorch.org/whl/cu128/torchvision/)

若 2.11/cu128 在现有 Genesis 栈上出现不可接受的回归，再评估保留 2.12、迁移 cu130 的单独组合。CUDA 13.x 需要更新的驱动；不能因为对方说“13.0”就切换默认，也不能假定该组合兼容本地 4090 的现有驱动。12.8 路线确定前，不同时维护两个正式默认栈。[NVIDIA CUDA 兼容说明](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)

驱动门槛应取“目标 GPU 的驱动支持要求、所选 Toolkit/PTX 路径要求、图形库要求”的交集。CUDA 12.8 GA 配套 Linux 驱动为 570.26 起，具体 update 版本要求可能更高；这不是所有 Blackwell 整机和所有执行路径的充分条件。发行清单记录最终验证的精确驱动版本，不能仅写“>=570 就一定可运行”。

### 3.2 pyuipc 的重建要求

1. 找到 0.0.25 wheel 对应的上游源码 commit、submodule、构建方式与依赖版本，固定到构建清单。先下载/检查发行 wheel，排除本地安装与发布产物不一致。
2. 使用固定 digest 的 CUDA 12.8 devel builder，生成 CPython 3.11 wheel。构建系统、glibc、libstdc++ 和 wheel 平台标签必须兼容当前 Debian bookworm runtime；通过 `auditwheel`/动态链接检查确认，不直接复制不明来源 `.so`。
3. 显式指定架构，禁止 `native` 根据构建机 GPU 自动选择。当前上游提供 `UIPC_CUDA_ARCHITECTURES` 并可能覆盖 CMake 变量；固定源码版本要单独核对。候选目标为 `89-real;120-real;120-virtual`，以该版本支持的参数格式和实际编译命令为准，不能只设置 `TORCH_CUDA_ARCH_LIST`。[上游 CMake 构建定义](https://raw.githubusercontent.com/spiriMirror/libuipc/main/CMakeLists.txt)
4. 对产物执行 cubin/PTX 清单检查，确认所需 native kernels；PTX 是补充，不替代对两种实际 GPU 的验证。产物需附源码身份、编译器版本、架构列表和 wheel SHA-256。
5. 通过固定 URL+hash 或镜像内明确的 wheelhouse 安装，防止 resolver 又选回原 PyPI wheel。若使用 `0.0.25+topogym.<build>` 本地版本标识，先验证 metadata、锁文件解析及现有版本检查行为；不得伪装成来源不明的同名原 wheel。
6. builder、wheel、recipe 的内容身份纳入镜像缓存和 release identity。构建失败不得回退到旧 sm_89-only wheel；必要时报告 IPC 后端不兼容并停止包含 IPC 任务的实验。

若必须升级 pyuipc 上游版本，拆成独立兼容改造：先验证 native dump/recover、frame 编号、关节耦合、接触历史和恢复后分支一致性，再修改严格版本检查。不得仅为了启动成功而删除版本保护。

## 4. 分阶段实施与文件范围

| 阶段 | 改动 | 完成条件 |
| --- | --- | --- |
| P0：固定现场 | 保存对方 GPU 完整型号/UUID/capability、驱动、所用命令、run/release ID、controller/runtime/agent image ID、完整首个异常栈；在实际 runtime 内收集 torch CUDA/架构和动态库身份 | 分清宿主驱动、容器 Toolkit、wheel runtime 与应用内核；明确故障发生阶段 |
| P1：候选锁与 IPC 构建 | 修改 `requirements/difficulty-eval-runtime.in`，重新生成 `.lock`；调整 `images/topogym/Dockerfile`；新增 `images/topogym/uipc-builder.Dockerfile` 和构建清单 | 无目标 GPU也能完成固定架构构建；两种架构产物齐全、哈希可复现核对、无隐式旧包回退 |
| P2：镜像身份与能力检查 | 扩展 `scripts/difficulty_delivery.py`、`scripts/difficulty_release.py`、`images/difficulty-eval/release.schema.json`；必要时更新 `.dockerignore`、Dockerfile 专用 ignore 和 source inventory | runtime、unlimited agent、limited sidecar、独立 verifier 均能追溯到同一栈；新增 builder/清单输入变动使缓存失效 |
| P3：分层运行验收 | 新增 `ci_checks/test-gpu-stack.py`，复用现有 prepare/preflight、Harbor 边界测试与资源守卫 | 在 4090 和实际 RTX PRO 6000 Blackwell 上逐层通过，保存失败日志与版本身份 |
| P4：交付与时间管理 | 更新 quickstart、主交付计划和生成的源码包；增加阶段用时和可选 GPU 归还时间控制 | 新用户不手工 pip 修复、不装宿主 CUDA；短试跑与完整实验明确区分，默认预算保持原值 |

controller/client 不因 CUDA 升级而安装 GPU 依赖；unlimited agent 从新 runtime 派生。现有生成任务中的固定 `FROM`、`images/VERSION`、普通 `build_images.sh` 入口和 Docker difficulty eval 的缓存镜像都应纳入核对，避免只修了一条启动路径。生成包更新使用现有生成器，不逐个手改 26 套 task 模板。

新增构建脚本/清单置于活动 `images/`、`scripts/` 或 `ci_checks/`；不恢复 `legacy/`，不要求 `demos/`，不改任务几何或成功判据。构建进程控制并行度；按用户 2026-09-30 最新要求，CPU 仅记录，系统内存达到 90% 时停止本轮进程。

## 5. 把 `check` 改为可解释的兼容检查

保留 `check` 名称，不增加 `doctor`。拆成快速环境检查和显式后端检查；建议新增 `check --level runtime`，这是待实现参数，当前命令尚不支持。`--phase all` 在模型调用前自动执行所选任务需要的后端检查，不能要求用户记住额外的手动步骤。

快速检查记录实际 GPU name/UUID/capability、驱动、torch/vision 版本、`torch.version.cuda`、wheel 架构、镜像 ID 和 release ID。执行 CUDA 分配、elementwise、矩阵乘和同步，并验证非平凡结果。错误分别标记为驱动不可用、架构/内核不支持、动态库冲突、JIT 失败、显存不足、资产失败等，保留原始异常。

运行时检查分开启动受控子进程，覆盖 Genesis rigid、PBD、FEM/IPC、Nyx。对每一步记录 `passed/failed/not_run`、超时、冷/热启动用时、显存峰值和日志路径；不能使用一个 `cuda: true` 代表所有后端。超时也不能被归类为架构不兼容。

GPU 架构不在已验证矩阵时标记未验证，按显式后端探针判断，不单凭型号字符串宣称通过或静默换到 CPU/raster RGB。检查缓存至少绑定 GPU capability、UUID、驱动、runtime image ID、探针版本；换镜像、驱动或目标 GPU 后重检。`--phase all` 仍保持所有所选实例通过 prepare/preflight 后才启动模型的 guard。

探针不能继承现在固定 180 秒作为所有后端的统一总超时：JIT 与 IPC 初始化有不同成本。按后端设置可记录的超时，区分冷编译与挂死；不通过无限延长超时掩盖失败。检查失败时退出、保留报告，模型调用数必须为零。

## 6. 验收矩阵与发布门槛

下列各层都要在 RTX 4090 与实际 RTX PRO 6000 Blackwell 上执行。只在 4090 通过或只看到 wheel 中的 `sm_120`，都不能标为 Blackwell 已验收。

| 层级 | 工作内容 | 验收证据 |
| --- | --- | --- |
| L0：构建/静态 | hash 锁、依赖完整性、ELF/PTX、动态库解析、发行身份、GPU UUID 传播、失败 guard | 构建清单和日志；新锁中没有误选 cu126；无模型调用 |
| L1：GPU 基础 | torch 非平凡计算、同步、结果检查；Vulkan 实际设备匹配 | 实际 GPU/驱动/runtime 报告；不能仅 import 或 is_available |
| L2：后端物理 | rigid 连续步进；Blanket PBD；Rope/Knot IPC 建场、有限步进、dump/recover 和恢复后继续执行 | 状态有限、无设备错误、恢复一致性符合原合同；不是“任务已解出” |
| L3：视觉 | Nyx 实际 RGB、动态相机/腕部相机、短录像解码；按需 depth 的几何路径 | 图像尺寸/非空/有限值、相机更新、资产身份；不以 OIDN 库或 Vulkan 枚举代替渲染 |
| L4：Harbor | 两种模式、真实产物收集、独立 verifier、超时 finalize、Ctrl-C/TERM 与所属资源清理 | 有效结果与录像；可用 nop/短受控动作，不以 nop 失败分数判定基础设施失败 |
| L5：覆盖与模型 | 全 13 × 3 采样实例的真实 preflight；再运行少量双模式真实模型试验 | 每实例状态、失败分类；物理可运行、模型能交互、任务求解成功分别报告 |

优先顺序：8/9 刚体 → 11 Blanket PBD → 2 Rope Threading / 7 Knot IPC。刚体两任务的短模型试跑可用于验证交付，但不作为全部 13 项已支持的标签。基础设施失败继续保持非任务失败分类；不静默跳过 IPC 任务或更换物理后端。

跨版本、跨 GPU 的浮点轨迹不要求逐字节相同；要求保持任务语义、结构、稳定性及既有恢复约束，并报告数值差异。不能用改宽成功阈值掩盖换栈回归。

每次证据置于独立的 `runs/test_results/cuda_blackwell_<date>/<gpu>/<run-id>/`，包含源码快照身份、配置/seed、镜像和 wheel 哈希、驱动、分阶段日志、图像/录像及结果。保留失败尝试，不覆盖旧 cu126 验收，也不把本计划写成已通过报告。

## 7. GPU 租借窗口与耗时改造

完整默认实验共 78 trials。若每个 agent 都用满 6 小时，串行 agent 时间累计为 **468 小时（19.5 天）**，准备、预检、收集和评分另计；这不是实际耗时预测。两个任务的 12 trials 即便每次只给 432 秒，agent 预算累计也有 **86.4 分钟**，仍不能保证在 10 点前结束。

立即可采用的流程：借卡之前构建/分发镜像、校验资产和完成 CPU plan；借到目标卡后先做无模型兼容检查与所选实例 preflight，再启动小规模真实试跑。镜像分发沿用现有许可边界；Nyx 发布限制没有解除时，不承诺公开镜像可直接拉取。源码构建和维护方预构建包是两个交付路径，分别验收。

实现阶段记录下载、构建、JIT、建场、preflight、agent、收集、replay/评分各自用时，展示当前阶段、任务、已完成数量及冷/热缓存区别。先用实测耗时估计剩余时间，未测阶段标为未知；不因为 GPU 更强就承诺物理或网络模型调用按比例加速。

建议在 P4 增加可选 `--stop-at <带时区的 ISO-8601 时间>` 与 `--shutdown-grace-s`，默认不设置截止时间，保持现有 6 小时单 trial 预算。该功能需：

1. 在启动前验证截止时间、时区和收尾窗口，记录到 run 元数据。
2. 覆盖 prepare/preflight/run/collect 的停止检查；到达停止接收工作的时间后不再创建新 trial。
3. 对剩余时间不足以容纳 agent 配置预算和收尾估计的 trial，记录 `not_started_due_to_deadline`，不静默缩短实验预算。
4. 对正在执行的 trial 先走现有中断/finalize/收集流程，预留 grace；最终边界仍未退出时仅停止本 run 所属容器，标记 `interrupted_by_deadline` 并保留已有证据。硬截止与完整评分无法同时保证时，如实记录评分未完成。
5. `--resume` 沿用旧配置与 attempt 语义；只有显式 `--rerun-incomplete` 才重跑中断项。测试截止发生于准备、agent、评分、GPU 等待的情况。

该截止控制是排期功能，不阻塞 P1–P3 的 CUDA 修复，也不应与兼容性错误混为一类。当前未实现前，不在 quickstart 中给出可直接执行的新参数示例。

## 8. 发布与回退

- 候选栈先使用新内容哈希/版本标识，不覆盖旧镜像标签的内容。新 runtime、agent、controller 和生成包必须使用相匹配的 release identity；纯 client 层可按输入身份复用。
- 依赖发生变化后使用新 run-id；旧 `--resume` 继续使用原源码/原固定镜像。不能让旧 run 用新物理栈接着评分，也不承诺旧 IPC dump 能跨栈恢复。
- 4090 回归失败时保留原 cu126 release 供原环境恢复；Blackwell 不得自动回退到 cu126。用明确失败阻止模型费用与无效实验。
- 发布前更新 [启动说明](docker_quickstart_zh.md) 和 [Docker 交付计划](difficulty_sweep_delivery_plan_zh.md)，给出已测 GPU、驱动、软件组合和仍未覆盖的范围。若 IPC 或 Nyx 未通过，只能发布明确限定范围的候选版本，不能标为“全部 13 tasks 的 Blackwell 支持”。
- 计划完成标准：新栈可重复构建；两种 GPU 上后端、视觉及 Harbor 链路通过；13 × 3 实例逐项给出 preflight 状态；真实模型验证单列；新机器按文档启动无需临时改包。求解成功率不属于 CUDA 迁移验收。

最初计划阶段仅交付本文与入口文档链接；后续研究见第 9 节，已授权的实际实施与验收状态见第 10 节。未列入实施结果的 CLI 扩展仍为计划项。

## 9. 补充核查：torch 2.11 与 pyuipc 升级影响

2026-09-30 补充。证据位于 `runs/test_results/torch211_pyuipc_review_20260930/`，包含临时候选锁、resolver 报告、上游 tag 源码及哈希、包元数据和材料公式计算。本轮没有安装候选包、执行 GPU 物理或测量运行速度。

### 9.1 torch 2.11：依赖层通过，运行层待验收

- 项目 `pyproject.toml` 没有 torch 2.12 的下限要求；当前 2.12 是 runtime 配方的固定选择。
- 已安装 Genesis 1.2.1 的 `genesis/__init__.py` 将 `<2.8` 标记为不支持；2.11 满足该版本检查。其另一个 `>2.9.1` 分支涉及 Metal 的 DLPack，不是要求 CUDA 使用 2.12。
- 检查活动 TopoGym、Genesis 和 quadrants 的版本分支与 torch 调用，未发现明确依赖 2.12 新增接口的使用；这属于源码筛查，不是穷尽证明。
- 仅在临时输入中将 torch/torchvision 改成 2.11.0/0.26.0，使用 `uv pip compile --torch-backend cu128 --generate-hashes` 成功解析整套 runtime 依赖。Genesis 1.2.1、quadrants 1.0.2、pyuipc 0.0.25、Nyx 0.1.3 和 plugin 0.1.4 保持原版本；环境安装仍为旧版本。

因此可以把“是否存在明显依赖冲突”这一项关闭，优先进入 2.11/cu128 的隔离镜像验证。暂时不能把“可安装、源码无明显障碍”写成“所有场景、求解器和 GPU 已兼容”。候选 lock 是一次依赖求解快照，正式迁移仍须审查传递依赖变化并完成本文 L1–L5 验收。

### 9.2 pyuipc 0.0.28 已有 Blackwell wheel，但包含数值行为变更

本轮 PyPI 查询的当前版本为 0.0.28。官方发布记录说明该版本提供 `sm_120`，同时修复 0.0.27 架构列表传递错误；因此不能根据 0.0.27 发布文案就认定其 wheel 包含宣称的全部架构。0.0.28 也处理了 CUDA Toolkit 动态库依赖问题。这使官方新 wheel 成为值得验证的替代方案，但本轮未下载/执行该 wheel，架构结论来自发布记录。[0.0.28 发布说明](https://github.com/spiriMirror/libuipc/releases/tag/v0.0.28)

升级对本项目的影响分为四类：

| 层面 | 已查到的变化 | 对 TopoGym 的意义 |
| --- | --- | --- |
| 安装/启动 | 项目额外依赖固定 0.0.25；`require_episode_checkpoint` 同样严格检查版本 | 直接替换包后，IPC 建场会被当前代码拒绝；需要正式适配，不能删除保护了事 |
| 材料本构 | 0.0.25 的实际能量路径含对 `Ic+1` 的对数项；0.0.28 切换到 SNK1；模量转换代码相同 | 相同 E/ν 不保证相同力—形变关系；不只是 Hessian 的实现加速 |
| 求解与接触 | 半隐式终止默认从 0 变 1，min_iter 从 1 变 0，新 K_min 为 6；接触/摩擦等也有修复 | 我们未显式覆盖所有这些字段，会继承新默认；迭代次数、接触轨迹和稳定性可能改变 |
| 状态与性能 | backend、归约、CUDA graph 等有改造；所核对的 state-accessor 公共头文件和材料 Python binding 未变 | 不能据此断言 API 一定断裂，也不能保证 native dump 格式、缓存状态和恢复语义不变；加速比例需实测 |

默认值直接对比两版 `src/core/core/scene_default_config.cpp`；Genesis 的 `IPCCouplerOptions` 多个字段为 `None`，`build_scene_config` 只覆盖非 None 字段。本项目设置了部分容差，却未固定半隐式终止开关。两版默认 contact constitution 都是 `ipc`；不能把所有 AL-IPC 修复都声称为我们当前启用的路径。[0.0.25 默认配置](https://github.com/spiriMirror/libuipc/blob/v0.0.25/src/core/core/scene_default_config.cpp)、[0.0.28 默认配置](https://github.com/spiriMirror/libuipc/blob/v0.0.28/src/core/core/scene_default_config.cpp)

### 9.3 材料影响的具体证据

项目 `topogym/world/physics/ipc.py` 调用 `StableNeoHookean`，通过 `ElasticModuli.youngs_poisson(E, nu)` 传入模量。`topogym/assets/materials.py` 的 rope 默认参数为 E=50000 Pa、ν=0.30、ρ=650 kg/m³。

对比上游实际调用链，而不是仅看文件名：0.0.25 的 `stable_neo_hookean_3d_function.h` 将 **detail/** 下的实现包含进 `sym::stable_neo_hookean_3d` 命名空间；不能误把仓库中另一个 **sym/simplified_...** 文件当成执行中的公式。0.0.28 的 CUDA kernel 则调用 `snk1`。

令 `Ic = ||F||²`、`J = det(F)`，μ/λ 表示 `apply_to` 转换后的内部参数。两版的能量密度为：

```text
0.0.25: Ψ = λ/2 · (J − 1 − 3μ/(4λ))² + μ/2 · (Ic − 3) − μ/2 · log(Ic + 1)
0.0.28: Ψ = λ/2 · (J − 1 − μ/λ)²      + μ/2 · (Ic − 3)
```

两版 `src/constitution/stable_neo_hookean.cpp` 及 `elastic_moduli.cpp` 在本次对比中相同。对于简单剪切 `F=[[1,γ,0],[0,1,0],[0,0,1]]`，旧版的 `P12 = μ·γ·(1−1/(4+γ²))`，新版为 `P12 = μ·γ`。所以在 γ→0 时，**相同输入参数下，新版切线剪切刚度约为旧版的 4/3**。

这是由已核对源码作出的解析推导，不是整根绳子的挠度、任务成功率或 GPU 性能测试。它说明不能假定升级只改变速度；也不能将 E 简单乘 0.75 就宣称恢复全部旧行为，因为体积响应、有限形变、接触及求解终止也参与结果。[旧版实际能量实现](https://github.com/spiriMirror/libuipc/blob/v0.0.25/src/backends/cuda/finite_element/constitutions/detail/stable_neo_hookean_3d.inl)、[新版 SNK1 实现](https://github.com/spiriMirror/libuipc/blob/v0.0.28/src/backends/cuda/finite_element/constitutions/detail/stable_neo_hookean_3d_snk1.inl)、[模量映射](https://github.com/spiriMirror/libuipc/blob/v0.0.28/src/constitution/stable_neo_hookean.cpp)

### 9.4 对迁移决策的更新

优先做 A/B/C 分离实验：A=现有 torch2.12/cu126+pyuipc0.0.25；B=torch2.11/cu128+同源码 pyuipc0.0.25 多架构构建；C=torch2.11/cu128+pyuipc0.0.28。先在同一张 4090 上比较 A/B、B/C，避免把换卡加速混入版本差异；再在 Blackwell 上比较 B/C。A 不作为 Blackwell 的可运行基线。

固定 seed、几何、参考网格、材料参数、dt/substeps、控制动作和渲染设置，分别比较：

- 材料：单元拉伸/压缩/剪切的力—形变曲线、绳子静态挠度和动态回弹，先隔离接触再加入接触。
- 接触与约束：穿透/间隙、摩擦滑移、抓取/释放、stitch、有限状态和能量行为；不通过修改成功阈值掩盖差异。
- 恢复：native dump/recover 后的分支轨迹、速度、接触状态与原实现合同；不跨版本混用旧检查点。
- 计算性能：冷启动/JIT 与热态每步耗时、Newton/PCG 迭代、显存峰值、状态保存/恢复成本；与模型 API 等待分开计时。

若当前首要目标是尽量保留已调好的材料与轨迹，继续优先验证 B。若目标是采用上游新求解器及官方 Blackwell wheel，则 C 是正式物理引擎升级，需要重新进行材料与任务资格验证；不能将“新版可能更快”作为跳过验证的理由。

## 10. 双 CUDA 配置实施

2026-09-30，用户授权保留 `cu128`，同时提供面向 RTX PRO 6000 Blackwell 等新机器的 `cu130` 候选。默认仍为 `cu128`；不自动按 GPU 名称切换，也不升级宿主驱动。两套都固定原始 pyuipc 0.0.25 源码提交 `292c98c3fec2dfbe9ae2c2407572f2f446a4a738`，不采用 0.0.28 的新材料公式。新编译器/数学库仍可能影响数值结果与速度，材料源码相同不等于轨迹逐位相同。

| 配置 | torch / torchvision | IPC 包身份 | 目标内核 | 当前用途 |
| --- | --- | --- | --- | --- |
| `cu128`，默认 | 2.11.0+cu128 / 0.26.0+cu128 | 0.0.25+topogym.det1.cuda128（tooling v18 起：确定性求解补丁；之前为 0.0.25+topogym.cuda128） | sm_89、sm_120、compute_120 PTX | 保留现有 4090 驱动环境的候选；也覆盖 Blackwell 编译目标 |
| `cu130` | 2.11.0+cu130 / 0.26.0+cu130 | 0.0.25+topogym.det1.cuda130（tooling v18 起；之前为 0.0.25+topogym.cuda130） | sm_89、sm_120、compute_120 PTX | R580+ 宿主驱动的新机器候选；Blackwell 实机待验收 |

### 10.1 改动与身份隔离

- `images/topogym/Dockerfile` 共用多阶段构建；两份 `uipc-build*.json` 固定不同 manylinux/CUDA builder digest。`build_uipc.sh` 固定源码、子模块和 vcpkg 版本，默认三路编译。
- 原版 CMake 多架构属性缺少引号，只修复该构建语句。`verify_uipc_wheel.py` 校验原始材料文件、源码提交及改动范围；实际 wheel 必须检出两种原生架构及 PTX，记录二进制/源码/wheel 哈希后才能安装。PTX 检查使用 `--all-fatbin` 覆盖 RDC 可重定位段；不据此承诺未验收的新 GPU 架构可用。
- 旧 tinygltf 2.9.6 标签归档哈希已与 vcpkg 不符。核对 1,344 个文件与固定提交 `26422192e2908a562b641175dde18489824e609e` 一致，历史镜像标签也指向同一提交；使用固定提交归档及其 SHA512，不跳过校验、不升级 tinygltf。
- `requirements/difficulty-eval-runtime{,-cu130}.{in,lock}` 分开锁定运行依赖，`requirements/uipc-build.lock` 锁定构建工具及 CMake 原先会自动安装的 pybind11、stubgen、NumPy。两套非 CUDA 包版本相同；不把现有 cu128 IPC 动态库直接放入仅有 CUDA 13 用户库的镜像。cu128 wheel 标签为 manylinux_2_34，cu130 实测需要 GLIBC_2.35，按 manylinux_2_35 打包；运行镜像 Debian bookworm 的 glibc 2.36 满足这两者。
- `scripts/cuda_profiles.py` 统一选择配方。`difficulty_eval.py` 和 `difficulty_delivery.py` 接收 `--cuda-flavor`，构建参数参与镜像身份，run 下 `cuda-profile.json` 禁止续跑切换，发布清单可声明 `cuda_flavor`。
- `check_gpu_stack.py` 执行真实 elementwise、矩阵乘、线性求解、torchvision NMS，校验安装后的 IPC 后端哈希和动态加载。运行镜像显式登记 pip 提供的 NVIDIA 库目录，并在构建时执行独立 IPC 链接检查，避免依赖 torch 提前加载库。Docker 的 `check` / `all` 接入 GPU 检查；它不代表 IPC 物理步进或 Nyx 场景渲染已通过。

```bash
# 默认 cu128：不调用模型
bash bash_scripts/run_difficulty_trials.sh check --cuda-flavor cu128

# cu130：需要 R580+ 宿主驱动，不调用模型
bash bash_scripts/run_difficulty_trials.sh check --cuda-flavor cu130

# cu130 全任务实验：13 × 3 × 1 × 2 = 78 trials，每个 agent 阶段最多 6 小时
bash bash_scripts/run_difficulty_trials.sh \
  --phase all --run-id luna-all-tasks-cu130 --cuda-flavor cu130 \
  --tasks all --samples-per-difficulty 1 --agent-wall-clock-s 21600 \
  --auth subscription --agent codex --model openai/gpt-6-luna \
  --agent-arg version=0.157.0 --agent-arg reasoning_effort=max
```

### 10.2 CUDA 13.0 的可行性与边界

PyTorch 官方提供 2.11.0 / torchvision 0.26.0 的 cu130 wheel，因此无需仅为 CUDA 13 更换 torch 大版本。完整项目依赖已在独立研究目录成功解析；结果是安装依赖证据，不能代替 GPU 验收。[PyTorch 安装矩阵](https://pytorch.org/get-started/previous-versions/)

原始 libuipc 0.0.25 的 `src/backends/cuda/CMakeLists.txt` 已包含 CUDA 13 的 CCCL include 路径分支，说明有移植基础；旧 MUDA/CCCL 模板、编译器和动态链接仍需通过实际构建。保持材料公式无需升级到 pyuipc 0.0.28。[固定版本构建定义](https://github.com/spiriMirror/libuipc/blob/v0.0.25/src/backends/cuda/CMakeLists.txt)

常规 CUDA 13.x 部署要求 R580+；13.0 GA 配套 Linux 驱动为 580.65.06，具体 update/GPU/图形路径仍须核对。本机实测为 RTX 4090、570.153.02，因此可以交叉编译 13.0 wheel，但不能据此完成 CUDA 13 GPU 验收。也不要求 CUDA 13 驱动只能跑 cu130：较新驱动可以运行兼容的 cu128 栈。[CUDA 13 发布说明](https://docs.nvidia.com/cuda/archive/13.0.0/cuda-toolkit-release-notes/index.html)

不把 `cuda-compat` 作为默认绕过办法：其硬件范围有限，且 NVIDIA 明确列出 CUDA/OpenGL/Vulkan interop 的限制；项目 Nyx 视觉路径需要独立验证。Nyx 官方文档还给出 CUDA 12.9+/driver 575+ 要求；固定 0.1.3 wheel 的 ELF 依赖与当前实际表现要单独记录，不能只用 torch 检查替代视觉资格。[兼容包限制](https://docs.nvidia.com/deploy/cuda-compatibility/forward-compatibility.html)、[Nyx 安装要求](https://genesis-embodied-ai.github.io/genesis-nyx/latest/user_guide/installation.html)

### 10.3 验收状态（双镜像与 cu128 代表性短检查通过）

第一次最终链接触发旧的 CPU 90% 停止规则，cu128 约 34 分钟时被中断，同行 cu130 构建也随全机 CPU 阈值停止；这次没有成功 wheel。用户随后明确允许 CPU 超过 90%。已改为仅系统内存达到 90% 停止，保留上游 LTO，拆分源码准备、编译、wheel 审计，并缓存编译目录；新一轮构建的证据目录为各自的 `runtime-build-memory-only/`。

- cu128 镜像内 torch 2.11 的四项真实 GPU 算子已在 RTX 4090 / driver 570.153.02 上通过，单次探针约 8 秒；无 IPC 物理或任务成功含义。
- CPU 构建/双配置合同测试 8 项、Docker 交付合同测试 10 项、workflow 合同测试 18 项通过（包含 CPU 100%/内存 89% 继续执行、内存 90% 停止）。真实 Docker CLI 帮助与 cu130 的旧驱动拒绝检查通过；两套 CLI plan 各生成相同的 39 个实例 / 78 trials / 21600 秒预算。
- cu130 依赖镜像已实际构建，torch / torchvision / Genesis / Nyx / quadrants 的无 GPU 导入检查通过；不代表 CUDA 13 GPU 运算通过。
- 两套 IPC 编译与最终链接已完成（本轮约 34.2 / 34.8 分钟，CPU 峰值 95.8% / 99.7%，内存峰值 37.4% / 36.4%）。首次审计分别发现 PTX 检查参数遗漏可重定位段、CUDA 13 wheel 的 glibc 标签过低；修正后 wheel 审计通过。通过 BuildKit 命名上下文复用同源码编译层，只重做打包和审计，记录于 `runtime-build-audited/` 与 `runtime-source-audited.json`。两套完整 runtime 镜像已构建成功，均通过独立 IPC 动态加载；cu128 的 GPU 算子、机器人/视觉资产、NVIDIA Vulkan 检查通过。cu130 最终镜像的 torch/torchvision/Genesis/Nyx/quadrants 导入通过。cu128 的 Cast Coil / Rope Threading 固定实例建场、3 个控制步、reset/replay 和四路 Nyx RGB 均完成；详细范围与限制见下表。Blackwell 真卡验收仍未完成。
- 证据目录：`runs/test_results/cuda128_delivery_20260930/`、`runs/test_results/cuda130_feasibility_20260930/`。保留旧 venv 与旧镜像，不调用模型、不推送镜像。

本轮审计 wheel 保存在各证据目录的 `wheels/`，实际运行镜像身份见 `runtime-image.json`，IPC 二进制与材料哈希见 `uipc-build-audited.json`。GPU/环境证据为 `final-environment-check/`（cu128）、`final-import-check-corrected/`（cu130，无 GPU 运算）。


### 10.4 本轮短物理证据与待办

实际使用 RTX 4090 / driver 570.153.02，cu128 完整镜像。任务源码固定为 `ad8a1b356e92c044`，不是并行会话后续修改的最新场景；两项均为 easy / seed 20260930。

| 项目 | Cast Coil（刚体） | Rope Threading（FEM IPC） |
| --- | --- | --- |
| 真实建场并冻结实例 | 通过，约 123 秒 | 通过，约 95 秒 |
| 独立重建与冻结实例匹配 | 通过 | 通过 |
| 3 个控制步、有限关节状态、无异常 episode_end | 通过 | 通过 |
| reset / replay 执行 | 完成，终态哈希相同 | 完成，终态哈希不同；不宣称精确确定性 |
| 四路 RGB 与短 MP4 解码验证 | 通过，约 40 秒的完整 smoke | 通过，约 94 秒的完整 smoke |
| 完成任务 | 未执行解题 | 未执行解题，冻结版本 `evaluable_for_task_success=false` |

两个场景在退出时均记录 Nyx `Failed to export shader library`，进程退出码为 0，RGB/视频产物有效；缓存导出问题尚未处理，不能称为无错误日志运行。初始化检查命令早期使用了错误 UID/不可写工作目录，已按正式调度器的实际 UID 与可写 work-dir 修正；原失败记录保留。

证据：[总报告](../../runs/test_results/cuda128_delivery_20260930/delivery-summary.json)、[Cast Coil 短视频](../../runs/test_results/cuda128_delivery_20260930/physics-smoke/cast_coil/smoke/segments/segment_0/videos/combined.mp4)、[Rope Threading 短视频](../../runs/test_results/cuda128_delivery_20260930/physics-smoke/rope_threading/smoke/segments/segment_0/videos/combined.mp4)。视频每路 3 帧、0.1 秒，仅展示短检查，不是成功演示。

仍需在 R580+ / RTX PRO 6000 Blackwell 实机分别验收两套栈，并按 9.4 固定动作做旧/新材料数值与速度对比；本轮没有完成这些对比，也没有进行 13 项任务的全部物理资格检查或模型 rollout。

### 10.5 首次工具安装遇到 NVIDIA 软件源 404

另一台机器的冷构建在 `yum install -y git curl zip unzip tar gzip` 失败：启用的 `cuda-rhel9-x86_64` 源返回 repodata 文件 404，导致并行的 Python 依赖下载被取消。这发生在 IPC 编译和 GPU 检查之前，日志不能据此判断 GPU/CUDA 不兼容；404 的上游或缓存具体原因未确认。

已将该步骤改为 `yum --disablerepo='cuda*' install -y git curl zip unzip tar gzip`。固定 builder 已带 CUDA 工具链，这里仅安装通用工具，无需访问 CUDA 软件源。两套固定 builder 均用 `--no-cache` 验证工具安装及 `git` / `curl` / `nvcc` 版本检查通过，分别约 23 / 24 秒；没有为此重做完整 IPC 编译或物理验收。证据：`runs/test_results/cuda_repo_bootstrap_20260930/`。

远端使用包含此修复的源码后，重新执行 `check --cuda-flavor cu128`（或所选 cu130）。无需删除 Docker 缓存；如果失败来自正式实验且已经冻结 manifest，源码变更后使用新的 run ID，避免旧快照继续使用旧 Dockerfile。
