# TopoGym RCB builder 反馈修补工程计划

日期：2026-10-01。状态：代码修补已实施，当前验收结果已归档；剩余 GPU 测试按用户要求暂停。本文面向 TopoGym 维护方，逐项解释 builder 报告中的 A 至 F，并给出修改范围、实施步骤和验收标准；同时覆盖本地复核发现的预检工具选择和镜像标签问题。

本轮实际代码修改、逐条错误链路、测试状态与证据见[修复验收报告](../../runs/test_results/rcb_builder_feedback_20261001/run_151751/report_zh.md)。计划中的验收目标不等于已通过；以报告中的实际运行结果为准。

当前已通过：普通入口 39/39、limited 入口 32/39、两个真实生成包的恢复／非 root 评分器运行／limited 收尾、16 项专项合同与 27 项流程回归。剩余 7 项 limited 矩阵、最大 seed 的额外 limited 检查、正式镜像两项独立 GPU 复核已暂停；F1 完整放置路线仍未证明，F2 在已测取件动作中未复现。逐项状态见[实测矩阵](../../runs/test_results/rcb_builder_feedback_20261001/run_151751/test_matrix_zh.md)。

本计划的目标是让任务生成、预检、正式执行和评分使用一致的控制逻辑与运行环境，让 Blanket 冻结初态具备明确的读取权限和兼容边界，并把运行故障与任务可解性缺口分开处理。优先恢复可靠的执行与交付链路，再完成当前实例的完整轨迹验收。

## 1 基线与证据范围

本次 pull 从 `76583213` 快进到 `c0a35177`，新增 5 个提交。交付包括 13 个正式任务的 easy、medium、hard 共 39 个 seed 0 实例，以及每个实例的 limited、unlimited 两种模式，共 78 个新任务目录。原有 28 个目录保留，当前 dataset 共 106 个目录。

这批提交还包含 float32 关节限位修复、limited 回放终点修复、interlocked 专用工具、离线重评分脚本和 `0.2.3` 镜像配方更新。78 个新目录均未提供参考解；目录中的 `solution/solve.sh` 明确退出 1。运行验证、任务判据已启用、参考解成功是不同状态。

下表记录开始实施前的分析基线；修复后的物理运行和当前验收状态见上方报告链接。

| 检查 | 结果与边界 |
| --- | --- |
| 全仓库静态 CI | 在 Python 3.11 环境运行 `ci_checks/run_all.sh`，全部通过；不证明物理可运行或任务可解 |
| A 的控制转换 | 使用报告提供的宽度表端点，执行当前工具转换及抓持意图逻辑，复现通用工具错误张开；专用补丁保留初始 native 值 |
| B 的文件权限 | 实际调用原子 JSON 写入器，新建与重写后的权限均为 `0600` |
| C 和 D 的存档 | 读取旧默认资源与新任务存档，比较 backend identity、scene identity、shape 和资格记录 |
| E 的 seed 分布 | 重新运行当前默认抽样函数，39 个样本中 17 个 seed 不小于 `2³¹` |
| 对方物理结果 | A 的 40 步测试、F 的跟随误差、穿透深度和 IK 残差来自用户提供的 builder 报告；本轮未在 GPU 上独立重跑 |

工作区另有 Horseshoe、Knot、Hedgehog 等开发改动。实施时记录实际源码与资产哈希，使用独立快照或隔离工作目录，保留已有未提交修改；不把不同源码身份的证据合并成一次验收。原修复阶段的静态 CI 区分三档、interlocked 专用和旧 i00 工具身份。

后续与远端 `8ad74b46` 合并时，公共工具升级为 v4，纳入远端 FEM checkpoint 限制和 Knot 判据向量化；
生成器采用 privileged/standard 协议流程，保留本地已实现的 builder 修复与 IPC 修正；F1 等验证缺口仍保留。
镜像升级为 `0.2.5-<cu128|cu130>`，
历史包按固定哈希保留，**不会自动获得 v4 修复**。实际合并与验证记录见
[合并验证](../../runs/test_results/merge_local_remote_20261001/README.md)，当前规则见
[公共模板说明](../../harbor_templates/topogym/README.md) 和 [工具身份检查](../../ci_checks/check-tooling-identity.sh)。

## 2 问题清单与处理决策

P0 表示会使受影响任务的执行或交付不可靠，必须在下一批相应实验前处理。P1 表示需要纳入后续修补与回归。可解性验收单列，不通过修改通用物理限制来代替。

| 编号 | 问题 | 开始实施时的状态 | 处理决策 |
| --- | --- | --- | --- |
| A | 宽度转换把保持闭合变成张开 | 新 interlocked 包有局部补丁，通用工具仍有问题 | P0，将保持动作的无损转换收敛到公共实现 |
| B | 初态 manifest 写成 `0600` | writer 未修复；已交付文件经过人工处理 | P0，明确公开资产权限并验证非所有者读取 |
| C | 冻结状态依赖 GPU 相关缓冲区布局 | 已知限制，缺少完整元数据和解释性错误 | P0，交付时检查兼容 profile；跨 GPU 通用恢复另立后续工作 |
| D | 整个源码文件哈希使存档过度失效 | 旧默认资源仍不匹配；新包单独重新准备 | P0，分离来源身份与兼容合同，再更新默认资源 |
| E | 高位 uint32 seed 不能传入底层 int32 初始化 | 源码已修复，报告列举的 seed 0 验证未覆盖边界 | P1，保留实现，补新进程回归 |
| F1 | interlocked hard 初态较高且一种下降路径 IK 失败 | 无当前完整参考解或可达性资格 | 单独完成当前终态的连续轨迹验收 |
| F2 | lock_picking 抬柄引发转动与脱持 | 转动与脱持来自 builder 观察；具体接触来源待核实 | P1，区分支架取件与插入后运动，补抓持及接触诊断 |
| G | 预检与任务包使用不同工具 | 本地复核确认，当前 CI 未覆盖该调用关系 | P0，统一工具选择并绑定预检证据 |
| H | 生成、构建和任务引用的镜像标签不同 | 本地复核确认 | P0，统一版本与 CUDA flavor 的解析 |

## 3 A 夹爪宽度转换破坏预抓持

### 问题内容

`_Robot` 用 33 个 native actuator 样本建立“夹爪开口宽度与 native 坐标”的转换表。名义 pad gap 在真正闭合端之前已经达到最小值；执行单调化和去重后，表中丢掉了最后一段 native 行程。

报告中的 ALOHA 闭合目标为 `0.002`，但表的闭合端为 `0.00746875`。出生目标经过 `targets()` 和 `command()` 后发生以下转换：

```text
native 0.002 → width 0 → native 0.00746875
闭合比例 1.0 → 0.84375
```

因此 `hold_action()` 虽然表达保持，实际发出了张开命令。`GraspManager.before_tick()` 检测到闭合比例下降超过 `intent_deadband=0.002`，将意图改为 open，预抓持无法正常取得。该判断符合收到的命令，主要缺陷在控制适配层。

本次 pull 的 `rcb_topogym_interlocked.py` 缓存当前 `(width, native)`，相同宽度保留 native，已覆盖六个 interlocked 三档目录。但它没有改变宽度表：张开后再请求 width 0，仍映射到 `0.00746875`。这是补丁的能力边界，不应写成所有闭合端问题已解决。

代码依据：[通用工具](../../harbor_templates/topogym/common/rcb_topogym.py)、[专用补丁](../../harbor_templates/topogym/common/rcb_topogym_interlocked.py)、[抓持管理器](../../topogym/world/physics/grasp_manager.py)、[任务初始目标](../../topogym/tasks/interlocked_claws/common.py)。

### 修补计划

1. 将“保持宽度时保留当前 native 目标”的逻辑纳入公共控制实现，以机器人当前已接受的控制目标为权威值，不依赖调用者恰好先调用某个查询函数。保留浮点表示容差，并验证 float32 动作行不会产生误张开。
2. 如保留缓存，明确其生命周期：动作被拒绝时不改变缓存；reset、rewind 和新 Session 后从恢复出的控制目标重建；不得沿用上一局或上一条失败命令的值。
3. 新版任务统一使用公共实现，删除生成器对 interlocked 的运行分叉。历史专用工具按冻结版本保留，不直接重写已有试验使用的文件。调整 CI，按明确版本检查旧、新工具身份，不能简单移除身份校验。
4. 完成 G，使 make-instance、describe、smoke、replay、limited sidecar 和 verifier 使用同一工具版本。
5. 本轮保持既有 width 命令的闭合力度，避免同时改变所有家族的接触行为。将“width 最小值不等于机械行程终点”写入开发说明。若后续需要完全闭合能力，单独修订端点及动作语义，并发布新控制版本。

最后一项需要单独处理，因为多个 native 值可能对应同一个 width。低层动作只有 width 时，无法同时无歧义表达“保持平台区内当前 native”和“强制走到机械闭合端”。不能通过盲目追加重复宽度节点，或提高抓持张开阈值来绕过该问题。

### 验收标准

- 在 ALOHA 与 Panda 的实际控制模型上检查 native → width → hold command；平台区内外的保持动作都不意外改变目标，真实张开命令仍能释放。
- 对 interlocked 三档出生初态执行至少 40 个控制步 hold，逐 tick 记录 fraction、intent、抓持阶段和接触限制，确认正常完成准入并持续持有。
- 覆盖 arm-only 运动、开合循环、失败动作、reset 后首次 hold，以及保存轨迹后的新进程回放。
- limited 与 unlimited 使用同一控制实现；不因修补放宽 `1 mm` 任务接触限制或 `2 mm` 持物手指接触限制。
- 对公共工具覆盖的其他机器人／抓持配置做有代表性的回归，再生成完整任务矩阵。隔离的数值测试不作为物理持物成功证据。

## 4 B 初态资产文件权限不适合交付

### 问题内容

`save_numeric_archive()` 使用 `write_json_atomic()` 写出 manifest。后者通过 `mkstemp` 创建权限为 `0600` 的临时文件，然后 rename，最终文件保留该权限。即使原目标文件为 `0644`，重写后也会回到 `0600`。

当 Docker COPY 将它变为 root 所有，而读取进程为其他 UID 时，读取 manifest 或计算其 SHA 会抛出 `PermissionError`，最终表现为 grader error。基础镜像已经对 `/opt/topogym` 设置可读权限，但后续任务镜像单独 COPY 的 `instance_assets` 不在该保障范围内。

新任务目录中检查到的 manifest 已可读，说明交付副本经过处理；writer 本身仍有缺陷。Git 的普通文件模式也不能用来证明生成后的 `0600` 问题已经消失。

代码依据：[原子写入器](../../topogym/utils/io.py)、[初态归档](../../topogym/world/initial_state.py)、[任务 verifier Dockerfile](../../harbor_templates/topogym/unlimited/tests/Dockerfile)、[初态安装脚本](../../scripts/install_blanket_initial_state.py)。

### 修补计划

1. 为 `write_json_atomic` 增加显式可选权限参数。保持未指定时的已有行为，公开资产调用方明确要求 `0644`；在临时文件 rename 前设置权限，维持原子替换语义。
2. 在初态归档与公开资源安装路径中统一检查 manifest、arrays 和父目录的访问权限。公开文件为 `0644`，目录具备所需遍历权限；同时覆盖限制较严的 umask。
3. 任务生成器复制 `instance_assets` 后执行权限检查或规范化，覆盖 unlimited environment、unlimited verifier 和 limited sidecar 三类副本。
4. 对新交付资源重新检查权限；仅权限变化时确认内容哈希未改变，不伪造新的物理验证结果。

### 验收标准

- 首次写入与覆盖写入都得到调用方明确要求的权限；其他用途的 JSON 不被统一改成公开可读。
- 使用不同于文件所有者的非 root UID，读取完整资产树并校验 manifest 与 arrays 的 SHA。
- 在实际生成的任务镜像内完成同样检查；验证的是 task-specific COPY 后的文件，而不只是基础镜像资源。
- 三档 Blanket 在相关运行入口中不再出现由资源权限导致的 grader error。

## 5 C 冻结状态依赖硬件相关布局

### 问题内容

当前 archive 保存了 rigid/PBD 的数值状态和补充缓冲区，其中包含 rigid collider 的临时工作区。本地 Genesis 源码按 GPU 的 SM 数与每个 SM 的核心数分配部分碰撞缓冲区，因而不同硬件可以产生不同 shape。

检查 hard 的旧资源与 builder 新包得到：

| 缓冲区 | 旧默认资源 | 新三档任务资源 |
| --- | --- | --- |
| `RigidSolver/collider/_contact0_mpr_state/simplex_support/v1` | `[4, 16384, 3]` | `[4, 24064, 3]` |

`require_same_layout()` 拒绝这种恢复是正确的。准确限制应描述为“需要匹配后端兼容合同和实际缓冲区布局”；相同 GPU 型号也不能替代软件、精度、几何与布局检查。报告的 Blackwell → 4090 失败有合理的源码解释，但本轮没有独立重跑该跨卡实验。

代码依据：[PBD 初态 codec](../../topogym/world/physics/pbd_initial_state.py)、[layout 检查](../../topogym/world/initial_state.py)、[状态缓冲区收集](../../topogym/world/state.py)。后端分配依据为已安装 Genesis 的 `engine/solvers/rigid/collider/collider.py`，实施时须记录实际版本及文件哈希。

### 修补计划

1. 与 D 一起设计新版 manifest 元数据：记录准备 GPU 名称、compute capability、SM 数、后端、精度、关键依赖版本、有效 solver 选项和缓冲区布局指纹。驱动、设备标识和准备镜像身份用于追溯，不把设备 UUID 相等作为通用恢复条件。
2. 在读取 archive 元数据时先检查可判定的环境差异；建场后、写入任何恢复状态前检查完整布局。错误中给出首个差异路径、源端与目标端的 shape/dtype，以及选择兼容资源或重新准备的具体方法。
3. 让调度器在正式模型调用前识别不兼容实例，归类为初态兼容性失败，不记作模型任务失败，也不静默换卡或换物理后端。
4. 当前版本采用明确的兼容 profile 选择资源。若支持 4090 与 Blackwell 两类交付，分别准备并验收各自 profile 的资源；单一 profile 通过时，只声明该 profile 已支持。
5. 记录 profile、资产 SHA 和冻结初态身份。相同 seed 在另一 GPU 上重新准备，可能生成不同物理初态，必须作为不同资产身份记录，不能宣称逐状态相同或直接合并可比性结论。

跨 GPU 通用恢复不列为本轮完成条件。后续若要实现，需要逐项识别可重建的 scratch buffer、必须保留的历史状态和 RNG 状态，再验证恢复后继续步进的语义。禁止直接跳过检查、截断数组或按形状补零。

### 验收标准

- 同一已验证 profile 上，生成进程退出后，在新容器和新进程中恢复并继续步进。
- 使用不兼容布局进行负例检查，在写入 live buffer 前给出可解释错误；正式模型调用数为零。
- 在实际目标 GPU 上分别完成验证，报告包括布局指纹、环境身份和差异。未获得某类硬件时明确标记未测，不能以型号列表代替验收。

## 6 D 存档兼容门槛与默认资源失配

### 问题内容

`backend_identity()` 将整个 `topogym/world/genesis_world.py` 的 SHA 纳入严格相等判断。seed 修复改变了文件内容，连 seed 0 的旧 archive 也会因源码身份不同而被拒绝。

旧默认资源中的 `world_sha256` 为 `93073f…`，当前源码及 builder 新包中为 `e30677…`。更进一步，检查 old/new hard archive 发现它们记录的 scene identity 完全相同，但 rigid 顶点布局分别为 `13876` 与 `14008`。因此只删掉源码哈希检查仍不能恢复旧资源，只比较输入参数也不能保证实际生成布局相同。

builder 已在新三档 task 包内重新准备初态，但默认 `gathered_scene_v1` 资源与 catalog 没有随之迁移。直接使用默认 task 入口，仍可能选中失效资源。新包只通过 `scene_layout` 资格，三档均记录 `passed=false`、`scene_layout_passed=true`、`settled=false`；这符合当前显式接受范围，但不代表释放后稳定性已通过。

代码依据：[backend identity 和恢复](../../topogym/world/physics/pbd_initial_state.py)、[默认资源选择](../../topogym/tasks/blanket_flatten/gathered.py)、[资源 catalog](../../topogym/assets/resources/catalog.json)、[准备脚本](../../scripts/prepare_blanket_initial_states.py)、[安装脚本](../../scripts/install_blanket_initial_state.py)。

### 修补计划

1. 将完整源码、准备命令、镜像 digest、依赖与资产哈希保留为 provenance，用于追溯，不把所有 provenance 字段都直接作为兼容等式。
2. 引入显式的新版恢复合同，例如 `rigid_pbd_numeric_v2`。该名称是计划值，实施时落入真实格式定义。合同覆盖恢复语义版本、关键后端依赖与实现、有效 solver 配置、实际构建出的实体／几何／绑定身份、buffer inventory、shape/dtype 和 RNG 布局。
3. 格式版本与兼容版本分开：数字树序列化未变化时，不必仅因兼容合同变化就修改其外层 schema；恢复语义变化必须升级兼容版本。相同 shape 不能证明语义相同。
4. 保留 v1 的原有严格读取规则。旧资源不能通过改写哈希或自动“升级元数据”获得资格；不匹配时要求使用其原环境，或按新版本重新准备。
5. 在 A、B、C、D、H 的相关代码与运行依赖固定后，再准备三档 seed 0 初态。使用新的资源 revision 或不可变 profile 路径，更新 catalog、默认选择与实例依赖。继续使用现有安装脚本拒绝覆盖冻结目录的原则。
6. 区分准备镜像身份与最终包含新资产的执行镜像身份。记录两者及共同的运行栈身份，不要求包含资产的整镜像 digest 自我相等，也不让仅重新打包资产触发无意义的再准备循环。
7. 保持 acceptance 为明确的 `scene_layout`，记录未通过的 settled gate。增加恢复后短程运行诊断；若另行提高到 `released_stable`，必须完成对应物理资格，不在本修补中静默更改范围。
8. 固定三档资源验收后，再验证 difficulty sweep 的新 seed 准备路径；每个随机实例使用自己的准备结果与资产身份，不复用 seed 0 代替随机样本。

### 验收标准

- provenance 变化与兼容合同变化有不同的处理结果；不相关源码注释变化不会单独导致 v2 archive 失效，真实恢复语义或布局变化仍被拒绝。
- 覆盖几何／绑定、solver 配置、buffer shape/dtype、关键后端版本和 RNG 布局不匹配的负例，全部在状态写入前失败。
- 三档通过默认资源入口、显式 `initial_state_path`、生成后的两种模式入口，在目标 profile 的新进程中完成恢复及有限步进。
- 环境和 verifier 使用一致的 manifest 与 arrays 内容身份；默认资源、catalog、实例声明及准备来源互相匹配。
- v1 和历史 task 包保持可追溯；新交付不能把旧资源哈希替换后继续沿用原资格结论。

## 7 E 高位 seed 修复的回归覆盖

### 问题内容

底层 Quadrants 初始化参数要求 signed int32，而 difficulty sampler 生成 uint32 seed。大于等于 `2³¹` 的 seed 在首次 `gs.init()` 时可能失败；同一进程已初始化后跳过该调用，因此复用进程可能掩盖问题。

`76583213` 已将传给 `gs.init()` 的 seed 改为 `int(seed) & 0x7FFFFFFF`，并继续以完整 seed 设置其他随机源。当前默认 39 个采样实例中有 17 个高位 seed。builder 报告列举的 39 个 fresh-process gate 都使用 seed 0，不能单凭这部分证据认定高位边界已实际覆盖。

代码依据：[Genesis 初始化](../../topogym/world/genesis_world.py)、[抽样器](../../scripts/sample_difficulty_instances.py)、[命名随机流](../../topogym/utils/variant_rng.py)。

### 修补计划

1. 保留当前实现，不缩减 sampler 的 seed 空间，不改写冻结实例的原始 seed。
2. 对 `0`、`2³¹−1`、`2³¹`、`2³²−1` 分别启动独立进程，测试实际底层初始化。先完成轻量参数检查，再执行真实运行入口回归。
3. 选取报告涉及的真实高位样本，覆盖 make-instance、新 verifier 进程、limited sidecar 启动及准备／恢复流程。
4. 同时验证 full seed 仍进入 scene variation 与 Python／NumPy／Torch 等原有随机源。相差 `2³¹` 的 seed 共享受限 engine seed，是底层映射的结果，不能据此把场景身份合并。
5. 把原始 scene seed 与有效 engine seed 纳入诊断，便于定位以后仅在冷启动出现的错误。

### 验收标准

- 每个边界值都在新进程成功初始化，而不是同一进程循环创建 Env。
- 固定环境下，相同 full seed 的资产与配置生成保持原有复现合同；不承诺跨 GPU 浮点轨迹逐位一致。
- 小于 `2³¹` 的输入映射不变，高位 seed 不再触发 int32 转换错误。
- seed 修复引发的旧 archive 身份变化由 D 的迁移处理，不通过放松旧 archive 校验解决。

## 8 F1 interlocked hard 可解性与可达性缺口

### 问题内容

builder 报告 hard 两件 claw 的最低点出生时约在桌面上方 38 cm。直接释放后两件相碰，超过 `1 mm` 任务接触限制；在保持出生朝向、双臂同步竖直下降的尝试中，右臂在下降约 150–160 mm 时发生 IK 失败。

这些结果说明该释放方式和该下降路径存在问题，并不穷尽其他姿态、横向移动或手臂配置。当前冻结任务允许持续抓持、不要求落桌或释放，但要求整个棕色 claw 进入目标体积、其余部件留在 separator 系统侧，并连续稳定 0.5 s。hard 的目标体积高度约为桌面上方 294 mm。

因此“必须先落桌再释放”不是当前成功判据。真正缺失的是从预抓初态到当前目标终态的连续、满足约束的机器人轨迹。当前 placement 元数据仍标记 `reachability_qualified=False`，参考 runner 也未开放未完成资格验证的完整 solve。历史几何分离 demo 不能替代这一终态。

代码依据：[当前 hard 任务要求](../../tasks/topogym-interlocked-claws-hard-i00/README.md)、[placement 判据与资格](../../topogym/tasks/placement.py)、[现有参考 runner](../../scripts/oracle_runners/run_rigid_reference_policy.py)、[任务开发记录](../develop/tasks/interlocked_claws_zh.md)。

### 修补计划

1. 在 A 和 G 验收通过后，冻结当前 hard 的几何、机器人、目标区、抓持配置和初态身份。以该冻结实例为验收对象，不换用旧变体证明成功。
2. 先做几何与运动学诊断：计算物件包络、目标体积、双臂关节限位与持物可达区域；搜索允许改变朝向、横向位置及双臂配置的候选路线，记录失败阶段。
3. 分别检查解锁／分离过程与分离后的目标区搬运。允许继续抓持；只有确需换抓或释放的路线才增加对应步骤，避免给任务附加不必要的落桌条件。
4. 将候选路线转成连续机器人动作，保留碰撞、抓持健康和当前目标判据。物体级路径和 IK 可解仅用于筛选，不能直接授予物理成功资格。
5. 若仍无法得到完整路线，报告搜索覆盖、最小失败例和未排除路径。若确定是场景或目标区的设计缺陷，再提出独立的 task revision，附几何与可达性证据；保留现有冻结实例及其结果，不直接放宽物理限制。

### 验收标准

- 当前实例从出生状态连续执行至完整目标终态，满足全部接触、分离、目标包含与稳定时间要求。
- 保存原始动作、状态诊断和统一录制视频，并在独立 verifier 中回放；各次成功与失败分别记录。
- 物理可解证据与 limited 感知能力分开报告。通过 unlimited 参考轨迹不等于证明 limited agent 能仅凭图像求解。
- 未完成时保持“可解性待验”的状态；基础设施修复可以独立完成，但不得把 hard 标成已证明可解。

## 9 F2 lock picking 受约束钥匙的动作诊断

### 问题内容

builder 报告抬升手柄时钥匙转动并丢失抓持，沿轴向拉动则可以跟随。若物体相对手的误差超过抓持健康阈值 `0.01 m` 或 `0.15 rad`，当前抓持管理器会解除辅助约束；这能解释脱持机制，但不能单独确定相对误差的来源。

2026-10-01 进一步核对更正：当前冻结初态的钥匙是自由刚体，放在两个开口 V 形支撑上，尚未插入锁孔，没有把远端固定在锁上的 joint。hard 实例的钥匙前端约为 `x=-0.135 m`，第一块转子中心为 `x=0 m`，钥匙轴也低于孔轴约 `0.091 m`。此前将报告中的“远端受约束”直接解释为出生时受锁孔约束，证据不足。

必须核对报告的抬柄动作发生于支架取件阶段，还是钥匙已经插入后。若仍在支架上，需检查支撑接触、重力力矩、动作速度和辅助约束的实际跟随能力；若已插入，则检查孔壁／板件接触。开口支撑本身不意味着禁止竖直取件，不能预先将抬升归类为策略错误。轴向跟随的局部成功仍不等于完整插入／开锁成功。

代码依据：[初态声明](../../topogym/tasks/lock_picking/common.py)、[钥匙及支撑几何](../../topogym/assets/geometry/lock_picking.py)、[冻结 hard 实例](../../tasks/topogym-lock-picking-hard-i00/environment/instance.json)、[抓持健康配置](../../topogym/utils/grasp.py)、[抓持生命周期](../../topogym/world/physics/grasp_manager.py)、[Lock Picking 规划代码](../../topogym/planning/lock_picking/)。

### 修补计划

1. 检查现有 oracle、抓取探针和示例动作，明确每次测试的起始位姿、已执行动作及接触对象，先确定转动发生于哪个阶段。
2. 在三档实例中分别执行支架取件和插入后运动诊断，覆盖抓取保持、分级慢速抬升、沿钥匙局部轴的小位移及必要转动。增加独立无支撑接触的持钥匙诊断场景，用于区分接触约束与抓持本身的跟随问题；该场景不计作正式任务成功。
3. 同步记录末端目标、钥匙 pose、轴线误差、相对抓持误差、接触对象和失持原因；将轴向定义在实例坐标／钥匙局部坐标中，避免硬编码世界方向。
4. 根据证据决定修改脚本动作、控制参数还是约束实现。正常自由取件若也稳定失持，应定位抓持或控制问题；确实受孔壁限制的动作则按孔轴、转子槽和止挡条件修正。

### 验收标准

- 保持和轴向跟随的误差、抓持状态可解释；受阻动作导致的脱持有明确原因。
- 不为保住错误动作而放宽抓持健康阈值，不绕过孔壁／转子约束。
- 局部抓持诊断与完整任务成功分别记录；完整参考解仍需通过当前判据及回放。

## 10 G 预检与正式任务工具不一致

### 问题内容

生成器复制 interlocked 专用工具到任务目录，但 `run_tool()` 仍通过通用工具执行 make-instance 和 describe。`difficulty_eval.preflight()` 同样固定选择通用 `rcb_topogym.py` 进行 smoke 和 replay。这样预检可能触发已在正式任务中绕过的 A，也可能验证了与交付物不同的行为。

现有 CI 检查文件是否符合所属模板，但不检查运行阶段究竟调用哪个模板。因此静态 CI 全通过不能排除这个集成缺陷。

真实验收又发现 limited 预检通过 `docker exec` 在 simulator 镜像里启动客户端，而该镜像没有客户端依赖 `requests`。正式 limited 部署原本将两者分开；因此这是预检入口自身的环境错误，会在发出协议请求前失败。

代码依据：[生成器](../../scripts/topogym_mk_task.py)、[limited 生成器](../../scripts/topogym_mk_limited.py)、[预检调度](../../scripts/difficulty_eval.py)、[工具身份检查](../../ci_checks/check-tooling-identity.sh)。

### 修补计划

1. 在生成阶段只解析一次工具版本和路径，将其传给 make-instance、describe 与复制步骤。正式预检优先执行已经生成的任务包中的工具，验证实际将要交付的文件。
2. A 收敛为公共实现后，仍保留工具身份传递，避免将来再引入不一致。limited sidecar 和 verifier 必须继承同一实例对应的工具版本。
3. 在 prepared／preflight 证据中记录工具哈希、实例与资产哈希、运行镜像身份、GPU 兼容 profile 和探针版本。工具或运行环境改变时使旧通过标记失效，不仅凭 `preflight.ok.json` 存在就跳过。
4. 对 interlocked 增加与其出生合同相关的抓持检查；普通三步 hold 或“状态有限”检查不能单独证明预抓持有效。
5. limited 预检使用独立客户端镜像，只挂载客户端两个协议文件；通过 sidecar 的隔离网络命名空间连接 localhost。记录客户端实际 image ID 并纳入预检缓存身份；本地入口没有指定客户端镜像时从生成包的客户端 Dockerfile 构建。

### 验收标准

- 从同一次生成流程追踪所有运行入口，证明其工具字节身份一致。
- 替换工具、资产或运行 profile 后，旧预检通过记录不能被复用。
- 对包含 A 的旧工具运行对应诊断会失败；新工具通过。不能仅测试分发路径而不检查实际控制行为。

## 11 H 镜像版本与 CUDA flavor 解析不一致

### 问题内容

当前生成器读 `images/VERSION`，默认得到 `0.1.0`；构建脚本优先读 `images/topogym/VERSION`，得到 `0.2.3`；新三档任务引用的却是 `0.2.3-cu128`。显式传入 `--image` 的交付可以成功，但默认重新生成未必引用实际构建出的镜像。

这会使调用者在不同入口得到不同运行栈，还会放大 Blanket 的兼容问题。标签字符串一致也不等于镜像内容相同，验收还需要记录实际 image ID／digest。

代码依据：[镜像版本](../../images/topogym/VERSION)、[构建入口](../../scripts/build_images.sh)、[生成器默认镜像](../../scripts/topogym_mk_task.py)、[CUDA profiles](../../scripts/cuda_profiles.py)、[difficulty 交付](../../scripts/difficulty_delivery.py)。

### 修补计划

1. 为普通 TopoGym 镜像建立统一解析：版本来自 `images/topogym/VERSION`，CUDA flavor 来自现有 profile 配置，生成唯一的正式标签规则。新修补使用新版本，不覆盖已用于实验的旧标签内容。
2. 构建入口、生成器、limited sidecar 配置和 verifier 共用同一解析结果，并使实际构建参数与标签声明一致。保留显式镜像覆盖入口，但将覆盖值冻结到生成记录。
3. difficulty 流程已有按内容身份生成的镜像标签，继续保留该机制；将同一 release 的具体镜像引用传入生成器，不强行改成普通语义版本标签。
4. 更新 quickstart 与相关 README 的当前用法，旧版本历史记录保持原意。推送入口若涉及标签解析则同步维护，但不因本计划改变现有 TopoGym 镜像发布条件或执行远端推送。
5. 记录准备、agent runtime、limited sidecar 和 verifier 的实际镜像身份。纯 client 镜像不需要与 simulator 镜像相同，但协议和 release 映射必须一致。

### 验收标准

- 不显式传 `--image` 的默认构建和生成路径能够引用同一个实际镜像；显式覆盖也有清晰身份记录。
- 标签中的 CUDA flavor 与镜像内运行栈一致，基础镜像与最终任务镜像关系可追溯。
- 检查 agent、sidecar、verifier 及 archive preparation 路径，不只验证一个 Dockerfile。
- 错误或缺失镜像在 prepare／preflight 阶段暴露，正式模型调用之前停止。

## 12 实施批次与依赖顺序

以下为顺序和交付边界，不是耗时承诺。GPU 准备、JIT、重建和物理路线搜索的时长以实际记录为准。

| 批次 | 工作 | 进入下一阶段的条件 |
| --- | --- | --- |
| S0 固定基线 | 保存实际源码快照、现有任务身份、镜像映射、旧资源哈希与已有报告 | 旧、新产物和工作区改动可区分，证据可追溯 |
| S1 控制与入口 | A、G、H；保留已合入的关节限位与 limited 终点修复 | 控制层测试、工具选择与镜像解析通过；interlocked 短程诊断通过 |
| S2 归档与兼容 | B、C、D 的代码及格式合同；补 E 的边界回归 | 权限与负例检查通过，准备代码和运行栈固定 |
| S3 重新准备与打包 | 按最终合同准备 Blanket 新 revision，安装 catalog，生成新版任务 | 目标 profile 的默认入口、新进程恢复、双模式预检通过 |
| S4 运行回归 | 13 × 3 固定实例的预检；受影响任务的双模式执行与评分；随机高位 seed 代表 | 按实际覆盖分别记录，基础设施错误已消除或明确分类 |
| S5 可解性与策略 | F1 连续参考路线；F2 受约束动作诊断与所需脚本修正 | 每项给出成功证据，或有具体失败边界的未完成状态 |

S1 和 S2 的独立编码工作可以按文件责任安排，但 S3 必须等待影响存档合同与运行栈的改动稳定后再做。S5 的几何分析可以提前进行，最终物理验收必须使用已修补并冻结的控制实现。

## 13 回归矩阵与证据要求

| 层级 | 必须覆盖的行为 | 通过标准 |
| --- | --- | --- |
| 静态与 CPU | 工具身份、镜像解析、动作 round-trip、权限、兼容负例、seed 参数 | 对应故障能被旧行为触发，新行为修复；全部相关 CI 通过 |
| 容器与权限 | 根目录资源和 task-specific 资源，由非所有者 UID 读取 | manifest／arrays 及父目录均可访问，内容哈希匹配 |
| 初态恢复 | Blanket 三档、目标硬件 profile、新进程、恢复后继续步进 | 全部兼容校验在状态写入前完成，恢复后状态有效，资格范围如实记录 |
| 控制与评分 | interlocked 预抓、两种模式、关节边界动作、limited live 终点与 replay | 不出现意外释放或越界误判，回放不执行 live 未执行的尾部动作 |
| 全矩阵预检 | 13 个任务 × 3 档 seed 0；每个实例两种模式入口 | 逐实例列出通过／失败／未测，不能从少数刚体外推 PBD 或 FEM |
| seed 回归 | 四个边界 seed 与真实高位样本的新进程启动 | 高位初始化错误消失，full seed 身份保持 |
| 可解性 | 当前 hard 的完整终态轨迹；Lock Picking 局部诊断与完整解分列 | 判据、接触限制和回放都满足，缺失证据时不授予成功标签 |

保留本次已合入的 float32 关节限位修复和 limited live-end 截断，并用实际边界行为做回归。离线重评分只针对已知工具故障影响的旧 trial，使用原 task、原镜像和原始证据；新 verdict 与旧 verdict 分开保存，不能借重评分更新场景、替换动作或修改成功判据。

新运行证据放在独立的 `runs/test_results/rcb_builder_feedback_<date>/<run-id>/` 下，至少包含实际源码／配置／资产身份、工具与镜像身份、GPU 与依赖信息、执行命令、逐层结果、错误分类、动作和必要的物理诊断。运行视频复用 `topogym.recording`，不另建录制循环。测试入口使用活动脚本和 CI，不从 legacy 导入运行代码。

按当前仓库规则监控 CPU 与内存，CPU 记录即可；系统内存达到 90% 时停止本轮拥有的相关工作进程，保留缓存与证据，不终止无关进程。

## 14 交付完成条件

- A、B、C、D、G、H 的对应修补与验收完成；E 的高位 seed 回归具有独立新进程证据。
- 新镜像、工具、默认 Blanket 资源与生成任务之间身份一致，受影响任务的双模式运行和评分通过；支持范围以实际 GPU profile 和测试矩阵为准。
- 旧 i00、已运行三档实例和原始评分记录保持可追溯。新资源、控制行为或运行栈导致实例改变时，生成新身份，不混入旧 run 的 resume。
- 13 × 3 固定代表与随机 seed sweep 分别记录。没有执行随机准备路径，就不能把固定 seed 0 的覆盖写成随机实例覆盖。
- F1 与 F2 独立列出完成状态。基础设施交付完成不自动代表当前所有任务可解；若 hard 尚无完整路线，文档和元数据继续保留该缺口。

实施进度集中记录在[修复验收报告](../../runs/test_results/rcb_builder_feedback_20261001/run_151751/report_zh.md)，区分“已实现未物理验收／已验收／失败待定位”，并链接实际证据。上文保留问题出现时的基线和验收目标，避免把目标误当成结果。本文不设置自动发布、推送镜像、启动付费模型实验或覆盖历史任务的动作。
