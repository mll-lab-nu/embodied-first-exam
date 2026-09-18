# 当前十任务的实验记录与复现协议：代码改造方案

日期：2026-09-17。范围：当前十任务，不包含 `legacy/`。

本文是拟议实现方案；下面标为“新增”的 Python 文件、API 和 CLI 尚未实现。本次只补充设计文档，没有改变生成、物理、验证或归档逻辑。

## 1. 目标与已有基础

目标是让每个新实验都能回答：测了哪个实例、输入是什么、实际运行了什么、结果验证了什么、用哪些文件可以重建或重跑。

当前已有大量可复用材料，不必重新发明报告内容：

- `core/config.py` 已能在 Hydra job 内保存展开配置；许多任务另行 `OmegaConf.save(..., resolve=True)`，Buzz Wire 则保存普通 dict 的 `config.json`。
- Coil 保存计划、模板、配置、源代码、实际状态和归档清单；Keyhole 有几何/运动/证书/双时间步审计哈希；Hedgehog 有资产与源实现指纹。
- Knot/Rope Threading 的 `validation_spec.json` 保存实验模式、阈值、求解设置、动作说明、依赖版本及源码指纹。Fiber 还有按源码快照执行的机制。
- `EpisodeSpec`、`EpisodeResult`、`EpisodeDatasetWriter` 已存在，但不能完整覆盖几何生成、局部 probe、物理对照、离线渲染等实验类型。

核心工作是统一关联和解释上述材料，并补足恢复入口。刚体与软体的内部状态仍由任务适配器处理。

## 2. 首先区分三个对象

### InstanceRecord：具体任务实例

包含任务/family/变体、实际参数、几何与碰撞资产、材料、机器人模型与摆位、规定的初始化方式、任务成功条件及任务假设。固定手工实例也合法，没有整数 episode seed 时记录 null，不用 0 冒充已随机生成。

`instance_id` 对规范化的实例内容生成指纹，路径改名不应改变身份。生成器版本、源参考和随机请求作为 provenance 保存；不要把仅有相同 seed 的两个不同几何当成同一实例。

语义身份与可复现请求应分别记录：`request = task/family/difficulty/seed/generator_version` 是配方，InstanceRecord 是实际产物。物理拒绝、外部证据变化等可能影响接受结果，恢复现有实例应以已保存产物为准。

### RunRecord：一次实验执行

每次执行都有新的 `run_id`，关联 instance_id。记录实验种类、动作/控制器输入、仿真 seed、dt/substeps/精度/后端、相关包版本和源代码、实际执行时长、状态文件以及进程结局。

默认时间步和半时间步是同一任务实例的两次不同 run；数值设置进入 `execution_fingerprint`，旧物理验证不能直接套用。材料、机器人模型或规定初态发生变化应产生新实例。改变控制器也改变执行指纹。

离线渲染是另一个 run，明确 `kind=render_recorded_states` 和 `source_run_id`；它本次的 physics_steps 可以是 0，物理来源必须指向真实执行。Horseshoe 的运动学预演则是 `kind=kinematic_rehearsal`，两者不能因为都用 set_pose 渲染就归为同一类证据。

### ValidationReport：对特定输入和范围的结论

报告绑定 instance_id、一个或多个 run_id、相关文件哈希、checker 版本、验收规则和阈值。运行完成、任务成功、物理稳定、可归档分别记录。

现有反例：`interlocked_claws/physical.py` 中 `passed=failed is None`，而 `success` 另查完整执行、稳定、约束释放及最终分离。`horseshoe_ring/trace_scene_variants.py` 的 passed 包含几何与采样机器人检查，实际 physics_steps 为 0。统一读取 `report['passed']` 会丢失这些区别。

推荐 CheckResult 字段：`name / status / scope / method / thresholds / measurements / evidence_refs / checker_version`。status 至少有 `passed / failed / not_run / error / not_applicable`。历史证据缺失标 unknown，不能猜成通过或实际失败。文件缺失或哈希不匹配属于 evidence integrity 状态，保留原报告并使它不可作为当前通过证据。

例如：

```yaml
checks:
  - name: puzzle_path_clearance
    status: passed
    scope: continuous_puzzle_geometry
  - name: robot_scene_collision
    status: passed
    scope: sampled_robot_path
  - name: physical_execution
    status: not_run
    scope: complete_task
```

公共汇总按具名 policy 决定“本次请求是否完成”。几何检查 policy 可以满足，完整物理 demo policy 则未满足。`not_applicable` 必须有理由且被对应 policy 允许，不能用来跳过必需检查。仍由任务检查器给出任务结论；公共层不降低 Coil 等现有严格验收。

## 3. 最小新增代码

建议新增轻量包 `topogym/experiments/`，避免把所有实验强塞入训练 episode 类型：

```text
topogym/experiments/
    __init__.py       # 不在导入时初始化 Genesis、GPU 或加载任务
    records.py        # InstanceRecord / RunRecord / CheckResult / ValidationReport / ArtifactRef
    io.py             # 序列化、内容指纹、文件清单、输入快照、完整性检查
    recorder.py       # 运行生命周期、开始/完成/失败记录、源实现与环境信息
    reproduce.py      # inspect / verify / diff，及按能力调用任务恢复入口
```

### records.py

使用 dataclass + 显式 schema_version 和字段验证即可。统一核心字段，任务特殊参数放版本化的 task_payload；大数组保存在 npy/npz 等文件，用 ArtifactRef 引用，记录 dtype/shape/单位/坐标系。注册实际物理后端，Fiber 当前的分段关节模型不能自动按 FEM 节点格式保存。

SeedInfo 应区分 episode/geometry/simulation/batch seed、候选 index/attempt、RNG 算法版本；参考轨迹单独保存为 parent_artifact。Horseshoe `load_seed()` 返回的是参考场景/轨迹，不能填进整数随机种子。

首版只记录现有随机语义，不更换 Keyhole/Horseshoe 的取样顺序或子 seed 派生规则。未来改成具名逐实例流时另升 generator_version，保留旧映射和已有实际参数。

### io.py

- 支持 OmegaConf 与普通 dict 的冻结副本；展开插值，检查有限数值，保留单位与约定。
- 在输出路径/时间戳之外定义版本化的身份字段；资产以角色、内容哈希和相对引用参与指纹。全配置保留，但 presentation/runtime 字段不能未经分类全塞进实例身份。
- 区分“文件原始字节 SHA-256”和“新协议的规范化内容指纹”；不改写或重新解释旧证书使用的哈希算法。
- 文件清单记录 role/path/sha256/size 与 dependency，覆盖 URDF/MJCF 引用网格、材料、FEM 网格、机器人及参考轨迹。任务先显式提供依赖清单，公共层验证闭包；遇到不支持的引用表达时报告缺口，不静默当成独立可复现。
- 小型任务资产和父证据保留独立副本；大模型可引用不可变内容存储，但若尚依赖外部目录，必须标为 external dependency，不能声称 portable。加载时将逻辑资产引用绑定到当前包内路径，原始配置快照不改写。
- 原子写入状态文件，新 run 使用新目录；状态更新与输入冻结分开，避免报告包含自身哈希形成循环。

### recorder.py

提供类似 `ExperimentRecorder` 的上下文对象，在昂贵生成/build 之前写下 request 和 running 状态。配置和代码常量的有效值确定后保存最终输入；构建失败也有记录。构建成功后冻结实例和资产，保存动作开始时实际状态，结束后收录原始报告及标准报告。

记录生命周期建议为 running/completed/error/interrupted，任务结论另列。进程正常结束但任务失败仍是 completed，不能自动等同 success。SIGKILL 无法保证清理，应由后续检查发现没有完成标记的 running 记录，标为 incomplete/unknown，而非凭空补写失败原因。

复用现有轨迹写入，不在第一版额外 monkeypatch scene.step，也不改变仿真步数、RNG 状态或控制时序。需要额外状态时在明确的 reset/action-start/final 边界调用任务 capture 函数。

源实现至少记录 Git commit、相关文件实际哈希及可恢复源码快照。当前存在大量未提交文件，commit 不足以标识执行代码；清单要包含任务真正使用的公共 robot/world/backend 模块及补丁。仅留 hash 能发现漂移，不能恢复源码。依赖版本及后端兼容条件也必须保留。

### reproduce.py

第一版实现 `inspect / verify / diff`，均无需启动物理。恢复能力按任务逐项声明，随后提供 `rebuild_scene / rerun / render_recorded_states` 的分派；只调用受控的当前任务适配器。

加载后先验证输入文件、实现及环境兼容性；使用已保存的实际参数与资产，不再次采样，也不回退到今天的默认 YAML。重跑写新目录并保存 parent_run_id；有意改变配置的试验标为派生 run/instance，不能覆盖原实验。

恢复初态、重跑实验、从状态渲染和任意时刻断点续跑是四种能力。FEM 节点位置/速度、参考网格、约束也未必包含求解器所有内部状态；不支持时明确 `checkpoint_resume=false`。几何导出可恢复不代表该任务已经能物理重跑。

## 4. 需要修改的现有公共文件

| 文件 | 建议修改 |
| --- | --- |
| `topogym/core/config.py` | 增加可在 Hydra 外使用的 freeze/write 帮助函数，保留原 save_resolved_config 包装；由任务在 CLI override 和有效常量确定后调用 |
| `topogym/generation/variant_episode.py` | 将 resolved_config 填为展开配置值，source paths 单独保存 provenance；采用显式版本区分旧含义；此项不作为新任务记录的前置依赖 |
| `topogym/generation/episode_spec.py` | 增加与 InstanceRecord 的转换/关联，保留旧 stable_id 为旧标签，不直接替换旧数据集身份；EpisodeResult.ok 不用作实验统一验收函数 |
| `topogym/runtime/episode_runner.py` | 仅对实际使用此协议的 runner 增加可选 record 上下文。当前任务多绕过这里，不能只改此文件就称全部接入 |
| `topogym/data/episode_dataset_writer.py` | 在需要导出训练数据时增加 instance_id/run_id/record schema 与快照引用，保留已有字段。实验记录独立于 HDF5 写入，避免异常导致完全没有记录 |
| `topogym/tasks/catalog.py` | 保持固定任务卡语义；如展示实验进度，读取新记录/能力元数据，不把 baseline seed 变成随机生成或物理通过的证据；另处理 Fiber 状态枚举不兼容 |
| `scripts/build_bootstrap_review.py` | 新记录存在时按 scope 展示检查结果，缺失时仍显示原任务报告并标历史格式；不依据文件存在或单个 passed 推断完整 demo |

其中记录核心、config 帮助函数、两个入口适配为首批工作；HDF5、全部公共 runner 迁移和展示工具升级可以后续推进。

## 5. 十任务分别怎么接

每项新增一个轻量 `topogym/tasks/<task_id>/experiment.py` 适配器，逐项实现输入声明、初态描述、原报告映射、恢复能力。共同保存协议，内部仍调用现有生成/scene/检查器。下表是主要改动入口，额外 probe 后续沿用相同方法接入。

| 任务 | 优先修改的现有入口 | 必须保留的任务语义 |
| --- | --- | --- |
| Cast Coil | `appearance.py`、`robot_demo.py`、`robot_archive.py`、`render_physical_trace.py` | 模板与计划对应；预抓取、接触触发辅助、释放；默认/半 dt 两次 run；离线渲染指向物理状态来源 |
| Cast Keyhole | `family_pipeline.py`、`family_variants.py`、`robot_execution.py`、`physical_audit.py` | batch seed、child seed、attempt/family/接受拒绝完整关联；require_variant 与双时间步校验继续执行；终态仍抓持等限制不丢失 |
| Horseshoe Ring | `shape_sampler.py`、`trace_scene_variants.py`、`trace_scene_verification.py`、`aloha_demo.py` | 整数随机 seed 与参考运动来源分开；父几何证书、密集见证和时间映射保留；连续谜题路径与采样机器人检查分别记录 |
| Fiber Bundling | `variants.py`、`run_config.py`、`variant_trial.py`、`variant_demo.py` | episode_seed 与固定 shape_seed=7 分开；环半径、根部连接、夹具与材料绑定；初态几何报告不提升为完整穿环；保留 snapshot_trial 行为 |
| Hedgehog in Cage | `family_motion.py`、`family_runtime.py`、`inverse_runtime.py`、`stability.py` | family/轨迹/反推笼体和真实加载碰撞的对应；区分台架、机器人执行、静置、离线渲染，完整保存 dt 与 substeps |
| Lock Picking | `runner.py`、`scene.py`，以及 `demos/environment_bootstrap/lock_picking_inspect.py` | task.seed 实际控制的布局与仿真分别登记；layout、settle 后状态、自由钥匙/辅助抓持；回退证书与实际回退次数分开 |
| Interlocked Claws | `physical.py`、`reliability.py`、`recording.py`、`archive.py` | 原始模型、坐标变换、source_motion；start_time/duration/初始持握；无异常运行与完整脱困成功分开；保留释放/时间步对照证据 |
| Knot Untying | `physics_probe.py`、`scene.py`、`physics_suite.py` | 保留现有 validation_spec/source 快照；实际体网格、参考直绳、初始化形变、耦合与约束、机器人初态；各 mode 单独声明 scope |
| Rope Threading | `physics_probe.py`、`qualification.py`、`scene.py`、`recording.py` | 几何/material 顺序、参考动作速度和 qualification 依赖；free_settle、ring_contact、reference_prefix、full_threading 分别记录 |
| Buzz Wire 3D | `demos/environment_bootstrap/buzz_wire.py`、`topogym/tasks/buzz_wire_3d/probe.py` | 普通 dict 配置、dataclass layout、硬编码有效力控参数与阈值；首版范围为局部环杆接触，不申报完整机器人或任意三维路线 |

对所有任务，保存 YAML 仍可能不足：例如 Claws 的 duration/start_time、Coil 计划中的抓持初态、Buzz Wire 的控制常量均在配置之外。适配器必须描述实际输入；记录 YAML 加版本号不能自动涵盖它们。

## 6. 新运行目录与调用方式

保留现有目录布局，在每个 run 旁新增 `record/`：

```text
<run>/
    config.yaml 或 config.json
    assets/、轨迹、原始报告、原有证书……
    record/
        instance.json         # 构建成功后冻结的实例描述；失败候选允许不存在
        run.json              # 从运行开始就有；唯一运行身份、输入与生命周期
        validation.json       # 标准范围与检查结果，引用原始报告
        artifacts.json        # 相对 run 根的依赖清单与哈希
        inputs/               # 原目录外的输入快照、参考证据
        implementation/       # 尚未由原任务归档的相关源码快照
```

现有 config/assets/source 等材料直接引用，不机械复制第二套；JSONL/NPZ 大轨迹仍采用任务当前格式。资产/源码快照一旦冻结，后续参数覆盖必须形成新记录。规定初态/初始化配方在 InstanceRecord；settle 后实际观测状态和动作起点在 RunRecord，并明确采集时机。

以下仅为拟议接入形态，不是当前可执行 API：

```python
with ExperimentRecorder(output, task_id=TASK_ID, request=request) as record:
    cfg, inputs = resolve_actual_inputs(args)
    record.capture_inputs(cfg, inputs, adapter=adapter)
    task = build_scene(cfg, inputs)
    record.bind_instance(adapter.describe_instance(task, cfg, inputs))
    initialize_and_settle(task)
    record.capture_initial_state(adapter.capture_state(task))
    raw_result = execute_existing_experiment(task)
    write_existing_reports(raw_result)
    record.complete(adapter.validation_report(raw_result, output))
```

生成器入口不必构建物理场景；在生成资产和几何检查后即可结束一个 geometry_generation run。完整运行如有多次检查，应保存相应步骤的报告，半时间步比较作为绑定两次 run 的独立验证结果。

## 7. 旧产物与正式归档

不批量改写既有 report/certificate/config/hash。若需要纳入新索引，生成旁路 imported record，记录导入时间、来源与 available/unknown 字段；不能用今天的代码版本、默认参数或猜测 seed 填补历史输入。

旧证据的适用性仍通过原 checker 及原指纹验证。历史目录有多个冲突报告时明确列出，不选择最乐观的 passed。没有足够恢复材料的记录可以被审查，但 capabilities 要如实标记。

正式归档脚本将 record/ 和它需要的输入一起复制到 `runs/demo_metadata/<task>/<run_id>/`，扩展 archive_manifest；视频仍遵循 AGENTS.md 放在 runs/demos 对应位置。保留原任务对完整性、相机、辅助与释放的准入检查，公共记录不赋予额外验收资格。

## 8. 分阶段交付与验收

**首批：记录可读、结果可解释。** 实现 records/io/recorder 与 inspect/verify/diff；接 Coil 与 Horseshoe，验证物理/运动学/离线渲染三种模式表达正确。同步接入现有失败退出路径。此时可以宣称统一记录，不宣称十任务统一重跑。

**第二批：两个实例能搬目录恢复。** 为 Coil、Keyhole 实现任务恢复适配，隔离原始 run 与可变默认配置，只依赖保存输入重建；保留必要不可变公共模型依赖并明确能力。验证默认/半 dt 和父证据引用，覆盖批次拒绝。此时再逐任务增加恢复支持。

**第三批：其余任务记录全覆盖，软体恢复单独验收。** 接十项主要入口、review 与归档；Knot/Rope Threading 检查体网格、参考形状、约束和初始化耦合，Fiber 按实际关节模型恢复。数据集指纹关联随后接入。

建议的回归检查：

1. 同实例重复运行 instance_id 不变、run_id 不同；换目录不改变内容身份。
2. 修改摩擦/碰撞资产/规定初态产生不同实例；修改 dt 产生不同执行指纹，禁止复用旧物理验收。
3. 删除原工作目录或修改默认 YAML 后，已声明 portable 的记录仍可加载；不完整依赖明确报缺失。
4. Horseshoe 的几何通过不变成物理通过；Claws 的无异常局部执行不变成完整成功；离线物理状态渲染保留其来源。
5. 配置或 build 失败也留下输入和错误；未完整退出的目录不显示为成功；记录器不额外取 RNG 或调用 scene.step。
6. 改写证据文件后 verify 报哈希不匹配；变更 checker/阈值产生新验证报告，不能覆盖历史结论。
7. 恢复状态按任务声明的坐标/单位/容差比较；物理重跑验证限定指标，不要求跨后端轨迹逐位一致。

这些检查围绕记录的正确性与恢复能力，不新增难度标定、任意几何生成或通用可解性算法。

相关背景：[四层架构与 seed 审查](../tasks/task_generation_modularity_audit_zh.md)。
