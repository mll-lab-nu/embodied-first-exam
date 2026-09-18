# 任务生成四层架构与 seed 接口审查

检查日期：2026-09-17。对象为当前工作区的十项任务、共享生成代码及现存运行证据。本文是工程审查和接口建议，没有实施运行时代码改造；不以 Git HEAD 代替当前正在开发的工作区。

## 结论

四项需求都可以模块化。当前阶段是“已有共享随机基础设施、多个任务专用生成器和局部验证闭环，尚未组成统一实例生成系统”。旧 seed 模块值得保留，但不能仅在新 demo 上传入 seed 就认为对接完成。

| 层 | 已有工程基础 | 距离需求的主要缺口 |
| --- | --- | --- |
| Task Spec | `EpisodeKey / TaskVariant / EpisodeSpec` dataclass、Hydra YAML、任务卡和各任务模板 | 统一的完整实例快照、难度及版本身份、资产与初始状态绑定、从快照恢复的公共入口 |
| Procedural Asset Generator | 多任务参数化实体/绳网格、显式复合碰撞体、部分水密/连通/质量惯量检查 | 统一资产输出契约和验收入口；各任务参数域覆盖不齐；无共享 CoACD/VHACD 流水线 |
| Randomization Engine | 具名独立随机流、声明式分布、派生参数、确定性 retry；三个新任务有不同深度的采样器 | 新任务统一接入、逐实例 seed 语义、难度到条件参数域的映射、拒绝记录 |
| Validity Checker | 几何证书、逆向设计、若干 settle/IK/物理执行检查及证据哈希 | 公共验证接口、统一能力与状态声明、每实例必经门槛；绳结逆向物理构造闭环 |

完成度应按上述能力分别验收。已有完整 demo、固定九代表或 `passed=true` 都不能直接换算成连续随机生成已完成。

## 旧模块能否直接接新任务

### 可复用的部分

- [variant_rng.py](../../../topogym/generation/variant_rng.py)：`VariantRng(seed).stream(name, retry=k)`，SHA-256 派生具名流，`VARIANT_RNG_VERSION=1`。具名流之间不会因取样调用顺序改变而串扰；retry 也有确定映射。
- [layout_randomization.py](../../../topogym/generation/layout_randomization.py)：支持 `choice / uniform / distinct_choice / spaced_pair / derived / validate`。先采样、后派生、再校验；校验或派生抛出 `ValueError` 时，按新 retry 重新采样整组参数。
- [variant_episode.py](../../../topogym/generation/variant_episode.py)：记录显式采样轴及发生变化的派生字段，生成指令、goal ID 和 EpisodeSpec。
- [episode_spec.py](../../../topogym/generation/episode_spec.py)、[episode_runner.py](../../../topogym/runtime/episode_runner.py)：提供实例与执行上下文的接口基础。

### 当前五处断点

1. **新任务没有走旧公共入口。** 当前 `configs/` 未发现 `variation:` 声明，当前任务/demo 未发现 `build_variant_episode` 或 `randomize_task_cfg` 的实际调用。Fiber 的 [variants.py](../../../topogym/tasks/fiber_bundling/variants.py) 直接调用了 VariantRng；其他新任务采样器采用各自逻辑。无 variation 时旧采样器直接返回原配置。
2. **difficulty 形参尚未生效。** `randomize_task_cfg` 明确忽略 difficulty，采完整 envelope。`VariantRng.tier()` 只是 `seed % n`，不能替代难度映射。稀疏/密集、S/M/L、动作 family 也没有自动成为已标定的 easy/hard。
3. **EpisodeSpec 还不是完整实例快照。** 构造器的 `resolved_config` 只写四组配置的路径，而不是展开后的配置值；TaskVariant.parameters 只记变化/采样字段，不能独立恢复未变化的物理参数、机器人和成功条件。实际任务有额外 config/template/geometry/state 文件，但尚未绑定到统一恢复接口。
4. **身份未绑定完整语义。** `EpisodeKey.stable_id()` 包含 task、preset、seed、variant，不含 difficulty、generator version 或配置/资产内容指纹。改变摩擦或生成规则仍可能得到相同 ID。现有自由字典和约定也没有强制要求每个新任务填全这些信息。
5. **seed 的粒度不一致。** Fiber 是逐实例 seed；Keyhole、Horseshoe 是批次随机流。Keyhole 还按已接受数量轮换 family，前面实例的拒绝会影响后续抽样。`baseline_manifest(task_id, seed)` 则只在固定任务卡外记录 seed，不改变场景。代码中的 IK seed 有时是参考关节解，不是随机整数。

本次复现：同一测试配置和 seed=42，easy/hard 均得到 `x=1.2843455756264526`，stable_id 相同；未提供来源时 resolved_config 为四个 null 路径。这确认了接口上的实际行为。

## 几何层已有多少

当前并非主要依靠手工存十套 mesh。Coil 有显式盒实体布尔划分和外形变换；Keyhole 有槽口/窗口与动作联合设计；Horseshoe 有马蹄、目标环和链环的联合参数；Hedgehog 有刺球/笼体及反推窗口；Fiber、Knot、Rope Threading 有参数化中心线与绳网格。

但“有参数化”不等于所提参数空间全部可用。Buzz Wire 的 [probe.py](../../../topogym/tasks/buzz_wire_3d/probe.py) 目前是直段加平面弯曲的探针场景，尚非通用三维样条路线生成器。Knot 的 [geometry.py](../../../topogym/tasks/knot_untying/geometry.py) 是解析 trefoil 加自由尾段，并检查交叉关系、间距和水密性，没有从已解开软体经物理动作打结的生成流水线。

碰撞已经有显式 box/cylinder/sphere/capsule/凸块组合，不必把所有资产强制重新做通用凸分解。新统一接口应同时支持“原生复合碰撞体”和“任意网格的凸分解后端”，并检查实际加载的碰撞体。对环或孔整体取凸包会封住通道，视觉网格水密也不能证明碰撞表示保留了任务。

质量检查应复用已有任务检查，统一输出水密/绕向/连通性、退化、质量惯量、碰撞近似误差和通道余量。刚体和软体需要不同检查策略，不能用单一网格条件代替所有物理有效性。

## 当前十项任务进度

| 任务 | 当前能力与证据范围 | 接入统一系统尚缺 |
| --- | --- | --- |
| Cast Keyhole | [family_pipeline.py](../../../topogym/tasks/cast_keyhole/family_pipeline.py) 已有采样、动作/几何生成、IK/几何检查、双时间步物理执行、审计和拒绝闭环 | 从批次改为稳定的逐实例请求；外部难度映射；统一 Spec；源资产/运动依赖固定 |
| Horseshoe Ring | [shape_sampler.py](../../../topogym/tasks/horseshoe_ring/shape_sampler.py) 对已认证邻域采样并联合收缩；另有新轨迹反推场景及机器人检查 | 形状采样与新 trace 变体尚非同一条随机流水线；九组合采样开关关闭；新 trace 没有动力学验收 |
| Fiber Bundling | 按逐实例 seed 采密度 family、线数和环半径；生成资产并检查初态几何；形状 seed 固定为 7 | 把独立 variant demo、IK/接触稳定性和完整穿环验收串入采样；无难度标定 |
| Cast Coil | 参数化/逆向设计、三个动作 family 和固定代表；基础版三个单参数外观变体已有物理报告 | 连续随机采样 API、接受率、难度映射；固定代表的成功不能外推整个参数域 |
| Hedgehog in Cage | 参数化运动与结构、逆向窗口、A/B/C 物理代表、独立稳定性检查 | 新 family 空间仍有不可执行的生成规划，缺 seed 到已验证实例闭环 |
| Lock Picking | 固定 family × S/M/L 代表、几何/回退证书；旧模式可按 seed 扰动角度 | 新 family 空间无整数 seed 采样闭环；物理随机数据生成开关为 false |
| Interlocked Claws | 已有基础几何、碰撞和物理检查模块；新 family 空间有审查/展示工具 | 新 family 的 `generator_implemented=false`、`random_generation_enabled=false` |
| Rope Threading | 参数化布局、网格和任务专用物理/参考动作检查 | 未发现当前任务的随机 family/参数到对应解验收入口 |
| Knot Untying | 参数化 trefoil、几何拓扑检查和物理 probe | probe seed 不是绳结结构随机化；缺物理逆向打结与逐实例验收 |
| Buzz Wire 3D | 参数化环和弯曲导线探针 | 三维路线族、seed 采样和机器人/物理验证闭环 |

两个当前打开的页面应这样理解：

- [Coil 外观单参数页](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_single_v1/index.html)：基础版外另有正面缩小、加厚、切角三个固定实例。归档报告记录默认/半时间步物理执行通过，采用预抓取起点和双侧接触后 weld 辅助抓持，三个变体视频是实际物理状态的离线渲染。该页证明这三个实例，不证明连续外观采样器。
- [Horseshoe trace 变体页](../../../runs/environment-solvability/horseshoe_ring/trace_scene_variants_v1/index.html)：三个新实例通过连续谜题几何证书和采样机器人场景检查。summary 的 `physics_steps=0`、`dynamic_execution_verified=false`、`robot_execution_verified=false`；整体 `passed=true` 仅在其声明的运动学/几何范围内成立。

## 四层应如何衔接

建议保留任务专用几何和检查器，通过薄适配层统一输入输出。以下名称是拟议接口，不表示已经实现：

```text
InstanceRequest(task_id, family_id, difficulty, seed, generator_version, preset_id)
    → DifficultyPolicy：确定条件参数域与必需验证项
    → CandidateGenerator：使用具名 RNG，生成参数/几何/初态及可选构造见证
    → AssetBuilder：生成视觉与碰撞资产，计算质量惯量和内容哈希
    → ValidityPipeline：独立检查几何、初态、settle、IK、构造/解路径
    → ResolvedTaskSpec + ValidationReport
    → save / load / reset
```

其中 CandidateGenerator 必须允许动作与几何联合生成。Keyhole 等已有实现从动作反推结构，不能强制所有任务先独立抽几何、再寻找解。逆向构造是生成策略；ValidityChecker 负责独立验证生成器提交的证据，不在校验时悄悄修改几何。

**实例契约。** 对外可以保持“任务族、难度、seed”；在冻结的生成器/preset 版本下才有唯一含义。内部 Spec 至少包含：

- schema/generator/RNG/难度规则版本，任务及 family，seed 与接受的 attempt；
- 完整采样及派生参数、单位与坐标系，初始刚体位姿/速度、机器人 qpos；软体需要其重建配方或节点/必要内部状态快照；
- 视觉和碰撞资产、机器人模型、父参考证据及哈希；
- 物理材料、摩擦、刚度、求解器、dt/substeps/精度、约束与辅助抓持设置；
- 成功条件参数、展开后的配置、各验证结果与输入指纹。

实例 ID 应绑定规范化的实例内容或包含完整版本身份，不能只依赖路径。资产/物理/机器人改变后，旧证据应失效或经过显式的证书迁移验证。先保证相同请求产生相同实例内容，以及保存/加载后的初态相同；不能把参数确定性扩展成跨 GPU/求解器物理轨迹逐位一致。

**随机化与难度。** 继续用 VariantRng，按实例和语义轴分流；批量运行只是独立实例请求的集合。先从已验证参考周围定义条件范围，再标定间隙比、转向需求、路径长度、抓取余量等难度指标。联合收缩和拒绝都会改变输出分布，报告应同时保留 proposal、最终参数、retry、拒绝原因。随机化材料还会改变动力学可解性，应纳入对应验证要求。

**验证结果。** 用分别记录的检查项和 `passed / failed / not_run / not_applicable`，包括 geometry、initial_topology、construction_witness、settle、IK/机器人碰撞、physical_execution；不要用一个 passed 混淆不同范围。请求规定验收策略，未运行的必需检查不能当通过。settle 应检查有限状态、速度/漂移、有无自行成功或散开；IK 应固定机器人和抓点，并另查碰撞与需要的路径连续性。

**逆向构造。** 现有“反推几何/轨迹”不等于“从已解开状态物理缠回去”。后者对绳结仍需开发。一次打结过程留下了很有价值的构造见证，但摩擦、接触、软体形变和单向操作并不保证逆放控制命令可执行，需要针对生成初态复核解开见证。可以将见证作为内部验收材料，不必把 oracle 或答案暴露给策略。

## 建议施工顺序及验收

1. **补全共享契约。** 明确 Spec、请求版本、ValidationReport、规范化序列化与资产哈希；处理 Fiber 卡片和 catalog 的状态枚举不兼容。把 RNG/声明式指令的公共回归检查从 legacy 恢复到当前检查集。
2. **接三个现成采样器。** 先适配 Fiber、Horseshoe、Keyhole，分别保持其初态几何、连续几何、辅助抓持物理验收范围；保留现有几何和验证实现。统一逐实例 seed 和接受记录。
3. **以少数已验证 family 打通难度。** 从受约束的参考邻域开始，落实 easy/hard 到实际参数范围的映射、条件派生、失败分类。不能直接把整个提案区间标为有效域。
4. **扩展族覆盖和验证策略。** Coil/Hedgehog/Lock Picking 增加连续采样，之后补软体逆向构造、Buzz Wire 三维路径；接入统一 settle 和机器人检查适配器。

第一阶段验收应覆盖：同请求重建的参数/资产一致；修改配置后旧快照仍能恢复；难度或生成版本不会误用同一个身份；改变碰撞资产使旧证据失效；串行与不同批次/顺序生成的同一实例一致；必需验证缺失时不产出“已验证”实例。物理重跑以声明的误差容限及成功条件验收。

## 本次实际验证及边界

执行环境：`.venv-gs121-nyx/bin/python`。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python -m unittest \
  tests.check_fiber_variants tests.check_horseshoe_shape_neighborhood \
  tests.check_task_baseline_catalog tests.check_cast_coil_appearance \
  tests.check_configs_compose -v
```

共 19 项，18 通过，1 项错误。错误为 Fiber 任务卡的两个轴使用 `geometry_candidate`，catalog.validate_card 只接受 `candidate`，导致 `baseline_manifest` 和全 catalog 检查失败；Fiber 专用采样测试通过。审查没有通过更改卡片状态掩盖该问题。

额外执行 legacy 模块的 `check_variant_rng / check_directives / check_braid`，三项均无失败；这是当前公共实现的复核，并非整个 legacy 测试套件。

逐个比较十任务的 baseline_manifest(seed=0/1)：九项返回相同 card 哈希并声明 `fixed_baseline`，Fiber 被上述枚举不兼容阻断。另执行了本文所述 difficulty/Spec 小型复现。

复核 [Keyhole 随机批次](../../../runs/environment-solvability/cast_keyhole/families_random_validation_v1/samples.json)：seed=20260917、vary_ik=true，三个 family 各接受一个实例、共拒绝一次。三个接受实例的 qualification、几何、运动、证书、两档物理报告/审计/轨迹及审计引用文件哈希均匹配。它们明确声明预抓取、辅助 weld、终态仍抓持，未验证纯摩擦抓取。

Coil 和 Horseshoe 的上述进度来自本次读取的归档/运行报告及相关单元检查。本次未重跑 Genesis 物理流水线，也未重新解码归档视频；没有新增十任务通用可解性或跨机器物理确定性的证明。

逐任务 seed 审查另见 [seed_variant_generation_audit_zh.md](seed_variant_generation_audit_zh.md)。
