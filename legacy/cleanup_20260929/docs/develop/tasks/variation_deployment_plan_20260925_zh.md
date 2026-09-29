# 变体按 Task 形式部署的实施计划

> 2026-09-25 后续归档更新：三档构造齐备任务只保留 common、三个难度模块及 __init__；两轮累计 37 个表外入口移入 tasks/legacy 并退出活动 registry。下文保留表外模块的原计划已由[实施记录](variation_deployment_implementation_20260925_zh.md)覆盖。Horseshoe 已按用户选择采用 waist_mild / u_mild / waist_ellipse 三档，旧入口归档，见[三档适用性分析与决定](horseshoe_existing_candidates_tier_review_20260925_zh.md)。

日期：2026-09-25。状态：**用户已授权实施，任务子目录、具名变体和占位文件已落地**。当前结果及缺口见[部署实施记录](variation_deployment_implementation_20260925_zh.md)；下文保留设计依据，物理验收以实际报告为准。

依据：[变体资产代码位置清单](variant_asset_code_inventory_20260925_zh.md)、[三档评估及捷径风险](variant_difficulty_review_20260924_zh.md)。目标是在当前统一模拟器中，按 Task 脚本形式接入所有可追溯的变体实现，并以 `<task_name>_easy / medium / hard` 命名三档主 setting。

## 1. 推荐方案与范围

采用 **`topogym/tasks/<task_name>/<task_name>_easy.py`**、`<task_name>_medium.py`、`<task_name>_hard.py`，每个任务的具体 setting 和共用实现归在同一目录，不再新增 `tasks/variations/` 层级。现有 `topogym/tasks/<task_name>.py` 改为同名包，通用部分提取到包内 `common.py`；三档是同级的具体 Task，复用公共声明、判据和状态协议。

这个结构更适合当前 13 项固定任务：从一个任务目录即可找到它的三档实现，不必在基础 Task 与另一棵 variations 目录之间跳转。原“基础变体”是三档中的一个具体 setting，通过注册元数据注明，不再单独维护一份并行的基础场景实现。

这里的“部署”分为源码归入正式包、资产构建、当前 Genesis 初始化／运行验收三个步骤；完整机器人解题和动作必要性另外记录。不能因为历史 demo 成功或新模块能 import，就将变体标成当前运行已通过。

本轮拟实施范围包括：

1. 命名、任务子目录、可追溯来源和变体注册。
2. 迁移当前代码与历史快照中需要的纯几何／初态构造能力，打包必要资源。
3. 将变体连接到现有 `TaskDefinition → TaskSpec → GenesisWorld → Env`。
4. 修复活动代码、配置、测试、文档及安装包的引用。
5. 运行对应资产、生命周期和基础场景验收，逐项报告缺口。

不以此次部署强行新设计尚不存在的两环 Orbits、大环 Slotted 等 setting，也不恢复历史独立模拟循环。下一阶段可另做这些新设计及无捷径检验。

## 2. 目标目录与命名

```text
topogym/
├── tasks/
│   ├── base.py
│   ├── scene_presets.py
│   ├── cast_keyhole/
│   │   ├── __init__.py                 # 轻量包入口
│   │   ├── common.py                   # 同任务公共行为，不是第四档
│   │   ├── cast_keyhole_easy.py        # CastKeyholeEasyTask
│   │   ├── cast_keyhole_medium.py
│   │   └── cast_keyhole_hard.py
│   ├── cast_coil/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── cast_coil_easy.py
│   │   ├── cast_coil_medium.py
│   │   ├── cast_coil_hard.py
│   │   └── cast_coil_eccentric_turn.py  # 表外、明确实验状态
│   ├── horseshoe_ring/
│   ├── hedgehog_in_cage/
│   ├── lock_picking/
│   ├── fiber_bundling/
│   ├── buzz_wire_3d/
│   ├── interlocked_claws/
│   ├── knot_untying/
│   ├── blanket_flatten/
│   ├── rope_threading/
│   ├── slotted_post_ring/
│   └── orbits/
├── assets/
│   ├── geometry/                      # 可复用几何实现
│   └── resources/
│       ├── catalog.json
│       └── variations/<task>/<revision>/...
└── config/
    └── registry.py                    # 唯一任务目录，关联各任务的变体记录
```

- 模块名与规范 `variation_id` 一致，如 `interlocked_claws_easy`；类名为 `InterlockedClawsEasyTask`。
- `task_id` 仍是 `interlocked_claws`，不把 39 个目标档位扩成 39 项独立任务。
- 每项仍以 easy／medium／hard 三档为主。外形、手性、旧机制、其他历史代表使用有意义的描述性名字，不硬塞到三档里，也不产生第四个难度标签。
- 尚无实际实现的档位创建对应难度占位文件，在注册记录中注明 `planned` 或 `blocked` 和原因；占位类明确拒绝实例化，不静默回退到 base。
- 参数连续变化由共享构建函数和明确参数域表示；不为每个 seed、颜色或重复历史修订创建一个模块。
- 正式的三档名字是难度目标。底层仍保存稳定的 `family_id / model_revision`，后续校准难度时不能抹掉原实例身份。
- `tasks/base.py` 是所有任务的协议；`tasks/<task>/common.py` 是该任务共享逻辑。easy／medium／hard 都继承 common，不让 medium／hard 继承 easy 的具体场景默认值。没有值得提取的共用部分时不强行增加空 common 文件。

## 3. Task 与 variation 的职责

### 3.1 为什么不能只移动现有字典

当前 [variation 解析器](../../../topogym/tasks/task_variations/__init__.py)只返回参数字典；[Env](../../../topogym/simulator/env.py)在构造时固定基础 Task 类，reset 时才合并 variation 参数。这能表达 Knot 家族参数，却不能直接选择 Keyhole F1 实体、Claws B/C 构造或 Blanket 的物理准备流程。

计划改为解析得到一条变体记录，包含目标 Task 类、规范身份、默认参数、允许覆盖的参数和能力缺口。Env 使用解析后的类建立当前 episode，后续执行仍走原有 `declare / bind / initialize / update / get_state / set_state`。

### 3.2 每个变体脚本写什么

每个已实现 setting 使用该任务 `common.py` 中公共类的具体子类，明确：

- 规范 variation 名、所属任务、目标难度、原 family 和模型 revision。
- 完整且可验证的默认 setting，包括尺寸、初态、机器人条件和资源标识。
- 必要的资产构建或初态差异；通过任务内部的小型构建接口接入。
- 相对基础 Task 新增的能力缺口，例如某个实体命名／终态检查尚未适配。

对于 Fiber 4/8/16、Knot 三结型等，子类只需配置默认参数。对于 Keyhole、Claws、Hedgehog 等，先在原任务中提取可覆盖的资产构建方法，再由子类选择实现；不复制整段 `declare()` 和同一套判据到三个模块。某个变体确需不同实体声明时才覆盖相关方法。

几何计算继续放 `assets/geometry/`，物理准备状态属于 Task 或共享物理模块；variation 脚本不拥有 scene、step 循环、录像器、planner 或 agent。历史“构造＋参考求解＋录制”混合脚本只抽取所需构造能力。

现有 Task 判据只有在实体角色和任务语义一致时才复用。更换实体、尺度或初态后重新检查；已有 `goal_complete=False` 和 `SupportGap` 不因加一个子类而消失。不能将父类的资格标签直接继承给新实例。

能力查询和操作前检查合并父任务与变体自身的 gaps；某个变体新增的初始化／判据缺口不能只写在文档里，也不能被父任务的 integrated 状态覆盖。

### 3.3 注册与调用

扩展当前 [registry.py](../../../topogym/config/registry.py)关联各任务的变体记录，并接收旧 variation 查询／解析职责，保留单一权威目录。具体实现路径指向 `topogym.tasks.<task>.<task>_<difficulty>:<Class>`；各任务 `__init__.py` 保持轻量，必要时只提供旧类名的惰性兼容导出。查询目录只加载轻量记录，具体 Task 类按需 import，不扫描或导入所有历史生成器。

未来调用仍使用现有 `task_id + variation_id` 形式：

```python
# 计划中的调用示例；当前尚未部署。
env = topogym.make(
    "cast_keyhole",
    variation_id="cast_keyhole_easy",
    seed=19,
)
```

`env_list()` 仍返回 13 项任务；`env_list(details=True)` 增加可查询的变体元数据，分别列出主三档、表外变体、待实现档位、当前运行验证和解题判据缺口。未实现或仅源码保留的记录不能被当作当前可创建场景的列表项。

解析缺失变体时应在创建物理场景前报出具体原因；已接入但尚未做物理资格验收的候选需明确标记，不冒充已验收环境。现有 reset 权限、episode 句柄失效、tick 历史和四种控制接口保持原合同。

## 4. 39 个主档位的部署映射

以下是**迁移目标**，不是当前运行状态。`可追溯` 表示已有构造代码或固定资产可以作为迁移来源；实际部署仍可能因当前后端、初始化或判据缺口而受阻。

| 任务目录 | `<task>_easy` | `<task>_medium` | `<task>_hard` | 迁移重点 |
|---|---|---|---|---|
| cast_keyhole | F1 long_stroke，可追溯 | F2 eccentric_window，可追溯 | F3 turnback，可追溯 | 迁移最终固定核心物化链及共同摆放；当前 base 不能直接冒充 F1 |
| cast_coil | baseline_assembly，可追溯 | axial_screw_turn，可追溯 | split_turn_offset，可追溯 | 接入现有 synthesize／冻结模板；锁定历史 9 mm setting，排除默认 6 mm 混用 |
| horseshoe_ring | 宽余量，planned | 标准余量，planned | 窄余量，planned | 新分档未实现；现有基础与旧接近路线三族另列 |
| hedgehog_in_cage | CLASSIC，可追溯 | oblique_gate，可追溯 | gen_keyhole，可追溯 | 迁移固定原型构建，区分十刺／六刺实体与出口 |
| lock_picking | F1 one_retreat，可追溯 | standard_150mm，可追溯 | F3 three_retreats，可追溯 | 从目录恢复槽位、限位与相应初态；不能把 F2 unequal 当原基础 |
| fiber_bundling | sparse 4 芯，可追溯 | standard 8 芯，可追溯 | dense 16 芯，可追溯 | 共用 anchored 构造；对齐环半径 13.5 mm 与其余固定参数 |
| buzz_wire_3d | F1 三拱，可追溯 | F2 over_under_eight，可追溯 | F3 plane_switch，可追溯 | 迁移线路 compose 和冻结布局；保留支撑／端挡，不能只恢复曲线 |
| interlocked_claws | B0 balanced 螺旋，可追溯 | C0 balanced 双窗，可追溯 | A0 原始 Claw，可追溯 | 将已有 FamilyModel 输出适配统一实体；C0 对应已有版，非两件全等框提案 |
| knot_untying | overhand_trefoil，可追溯 | figure_eight local support v2，可追溯 | double_overhand，可追溯 | medium 固定放大结区及尾段参数，复用当前 FEM 链 |
| blanket_flatten | simple_folds，可追溯 | fold_roll，可追溯 | gathered_twist，可追溯但准备流程需迁移 | 补卷曲字段接线；hard 需要完整初态准备，不能仅改一个参数名 |
| rope_threading | 两环，planned | wang_reference_v1，可追溯 | 三环小孔，planned | 先保留精确三环 reference；两种新设定需要新构造与穿环关系定义 |
| slotted_post_ring | 大环顶部解脱，planned | 中环倾斜解脱，planned | 原基础，可追溯 | 大／中目标环不等于 36 mm 柱槽候选 |
| orbits | 两环，planned | 三环，planned | 四环视频实例，可追溯 | 四环要恢复 75% 器具和匹配绳长；当前校验拒绝两／三环 |

据当前清单，39 个主档位中 **30 个有可追溯迁移来源，9 个仍缺确定的新 setting**。这不是“30 个已可运行”的承诺；尤其 Blanket hard 的物理准备需单独验收。Horseshoe 原基础虽然存在，但尚未确定属于新余量三档的哪一档，因此不直接填入 medium。

## 5. “所有能追溯到的 variation”如何保留

三档主表之外的真实差异也列入迁移清单，不只迁移三档后丢弃其他构造能力。每项完成来源核对后，选择以下一种落位：可用实验变体、仅资产构建、历史退役记录；没有当前 Genesis 适配的旧实现不发布为可运行 Task。

| 任务 | 主表外已知内容 | 部署方式 |
|---|---|---|
| Keyhole | A/B/C 外形、旧基础及开发修订 | 外形通过同族参数／资源表达；旧基础身份保留；已替换修订保留来源，不恢复默认池 |
| Coil | eccentric_turn；face_small、depth_thick、corner_cut | 明确命名的表外模块或受控参数预设；不与主三档混名 |
| Horseshoe | 旧 F1/F2/F3 接近路线；非圆环和其他形状候选 | `horseshoe_ring_approach_top / outer / rear` 等描述性名字；若只改脚本路线而场景相同，登记为策略来源，不伪造不同环境；几何候选按实际构造能力另记 |
| Hedgehog | fixed_side_window；更早 staggered_gates、helical_guide | fixed_side_window 可作表外实验 setting；退役族的构造和来源保留，不自动进默认可用池 |
| Lock | F2 two_unequal、S/M/L 尺度代表 | `lock_picking_two_unequal` 与尺度参数；不提升几何／IK 记录为动力学资格 |
| Fiber | 密度族内芯数／环径随机域，早期 branched/anchored 修订 | 主模型支持具名参数域；旧建模修订记录适用范围，不把所有重复归档当新变体 |
| Buzz | 旧双拱、不同 wood/toy/support/home 修订 | 确有线路差异的双拱可单列；材质和录制版本作为 revision／外观，不各生成一个难度 |
| Claws | 旧 helical_crown、旧大框 orthogonal_gate、其他形状候选 | 新 B0/C0 用明确 balanced revision；旧件可保留构造与实验身份，但退役版不混入默认池 |
| Knot | left_overhand、原尺寸 figure_eight、形状尺度／朝向 | 独立表外模块或参数预设；medium 放大版与原版不能共用模糊别名 |
| Blanket | three_folds、five_folds、fold_spiral、corner_cross_twist 等 | 可复用构造全部迁移；复杂准备失败／不稳定版本明确保留资产或诊断级状态 |
| Rope | 当前三环的布局／绳插值修订 | 明确 revision 与参数，不据此宣称两环已实现 |
| Slotted | clearance36 柱槽候选 | `slotted_post_ring_clearance36` 表外模块，不能命名为 easy 大环 |
| Orbits | 旧无臂路线 v1、视频路线 v2 | 只改解法的路线不是新资产 setting；有尺寸／初态差异的实例才单独登记 |

实施第一步从 [代码位置清单](variant_asset_code_inventory_20260925_zh.md)逐项形成来源映射：源文件／函数、源 SHA-256、实际参数、固定资产及哈希、目标模块、调用依赖、当前可部署状态。历史快照按内容去重，不能只按同名文件选择，也不能不核对 revision 就取“最新文件”。迁移后仍保留原归档，便于追溯。

## 6. 默认值、别名与身份规则

### 6.1 base 与三档的关系

最终 `base` 只作为注册层的兼容别名，指向该任务指定的基础档；不再创建独立 `<task>_base.py` 与三档重复。下面列的是之前三档表中指定的基础实例归属，难度尚待实测校准。

| 任务 | 规划中的基础档 | 基础实例 | 当前代码 base 的核对备注 |
|---|---|---|---|
| Cast Keyhole | easy | F1 long_stroke | 当前基础模板入口还不是 F1 专用生成链，不能直接宣称已对应 |
| Cast Coil | easy | baseline_assembly | 基础装配；迁移时核对完整配置 |
| Horseshoe Ring | 待定；建议标准余量锚点作为 medium 候选 | 原基础实例 | 新余量三档未定义，不能把旧接近路线 F1/F2/F3 当难度 |
| Hedgehog in Cage | easy | CLASSIC | 当前生成入口为十刺 CLASSIC |
| Lock Picking | medium | standard_150mm，两次回退 | 保留原基础语义；不替换为 F2 unequal |
| Fiber Bundling | medium | standard 8 芯 | 当前默认线数为 8；核对环径等其余参数 |
| Buzz Wire 3D | easy | F1 三拱两谷 | 当前 Task 默认使用通用 spatial_maze_v2 构造，不能直接认定为 F1 三拱包 |
| Interlocked Claws | hard | A0 原始 Claw | 当前基础生成入口对应 A0 |
| Knot Untying | easy | overhand_trefoil | 当前默认结型对应三叶基础 |
| Blanket Flatten | easy | simple_folds | 当前默认五折初态 |
| Rope Threading | medium | wang_reference_v1 三环 | 三环基础，场景摆位修订独立记录 |
| Slotted Post Ring | hard | 原尺度完整穿套任务 | 原基础机制，不能混同 clearance36 候选 |
| Orbits | hard | 四环视频基础 | 同为四环，但当前场景 linear_scale=0.85，表中视频版为 0.75；不是同一精确 setting |

因此，迁移完成后可直接交付一张基础档映射表；当前不能声称所有 `make(task_id)` 已等价于表中三档代表。Keyhole、Buzz、Orbits 等不一致项先选定要部署的精确实例，再记录默认入口的明确版本变更并重新验收。若需保留旧调用结果，过渡期用唯一、描述性的旧实例记录承接，不能与新三档共用同一身份，也不复制公共逻辑。

### 6.2 旧 ID 与旧 import

- 当前可调用的 `left_overhand / figure_eight / double_overhand / three_folds / five_folds` 保留语义等价映射。原 figure_eight 不直接映射到放大 25% 的 medium；需要保留原尺寸版本的独立记录。
- 历史 F1/F2/F3 同名但参数不同的情况不做盲目别名；别名必须唯一绑定 task、family 和 revision。
- 活动源码的查询／解析统一改用 `topogym.config.registry`，具体 Task 指向 `topogym.tasks.<task>.<module>`。若实际安装包调用方需要过渡，旧 `task_variations/__init__.py` 最多保留一层弃用转发，不保留第二套实现或重复 registry；迁移完成后按兼容需求清理。
- 历史快照、历史视频 manifest、轨迹和证书不批量改写，因为它们记录当时源码身份。当前文档和运行入口引用更新到新位置。

### 6.3 防止“名字是 hard，实际参数已经变成 easy”

每个 setting 区分机制固定参数与允许扰动的参数。覆盖无关外观和共同摆位可以保留 difficulty_target；改变芯数、孔径、结区尺度、窗口结构等定义参数时，超出该档允许域应明确拒绝，或要求使用另行登记的自定义／表外 setting，不能继续冒充已冻结的三档实例。

参数合并应有明确嵌套规则并拒绝未知字段，避免当前一层字典覆盖造成必需默认值丢失。seed 只控制声明的随机项；固定 setting 不借 seed 改变所属家族。

`instance_id` 的规范身份至少覆盖 task、family／revision、有效配置、seed 和构造资源版本；episode 元数据同时记录请求 ID 与规范 variation ID。原 [TaskDefinition](../../../topogym/tasks/base.py)目前只对 task/config/seed 哈希，必须处理不同变体类配置相同但几何不同的身份碰撞。别名本身不制造另一个物理实例身份，历史身份不回写修改。

## 7. 资产与历史源码迁移

1. **所有运行所需文件随安装包提供。** 从根目录 `assets/tasks/` 或 `runs/` 提取实际需要的模板、碰撞分块、初态数据等，归入 `topogym/assets/resources/variations/<task>/<revision>/` 并登记到资源 catalog。运行时不读取开发机的历史目录。
2. **保留精确来源，去掉机器绝对路径依赖。** 保持碰撞实体、单位、质量／惯量、坐标变换与元数据一致；URDF 资源引用使用可重定位路径。源文件作为不可变来源记录，生成目标使用新身份和哈希，不沿用已失效的证书。
3. **固定 setting 优先复用冻结结构。** Coil／Keyhole 的昂贵逆向设计不要求每次 reset 重新搜索。可随包保存最终核心，实例只做确定性重建／允许变换；完整生成算法仍迁入当前几何模块以供构造新实例。
4. **几何与规划依赖解开。** Coil 的 `family_parameter` 等纯几何参数工具从旧 `task_variations/cast_coil.py` 移到共享几何层；`assets/geometry/cast_coil.py` 和 `planning/motions/cast_coil.py` 同时修引用，避免底层几何反向依赖 variation 子类。
5. **不复制旧物理模型冒充当前验证。** 历史 MuJoCo 的机器人、weld、flex XML 不能直接作为 Genesis Task。提取可用几何／材料意图，使用当前 EntitySpec、AttachmentSpec 和物理链重新声明。
6. **复杂软体初态单独处理。** Blanket gathered_twist 迁移目标生成和物理准备；以落稳后的合格状态为 episode 起点，保留材料坐标、绑定及可恢复状态。初态准备不能污染操作方 tick 历史；静态截图、仅可视网格或跨后端旧状态文件不能冒充可恢复物理初态。若当前接口缺乏这条路径，就明确登记准备缺口，暂不进入可运行列表。

对历史预抓持代表，不照搬辅助固定来伪装 home 起步。新 setting 要把机构相对姿态、桌面支撑、机器人初态和必要辅助条件写全；不具备真实起始条件的候选保持缺口，而不是为了初始化成功改成已分离状态。

## 8. 需要修改的引用与文件范围

| 当前位置 | 计划修改 |
|---|---|
| [tasks/task_variations/](../../../topogym/tasks/task_variations) | 迁移到任务子目录；原纯几何工具移到对应几何层；只在需要时保留短期转发 |
| 当前 `tasks/<task>.py` 单文件模块 | 转为 `tasks/<task>/` 包；不能同时保留同名 `.py` 和包造成导入歧义。公共行为移入 common，具体基础 setting 放进对应难度模块 |
| [config/registry.py](../../../topogym/config/registry.py) | 关联变体 Task 类、规范 ID、别名、资源 revision 和能力缺口；保留 13 项父任务 |
| [simulator/env.py](../../../topogym/simulator/env.py) | 从解析结果选择 Task 类，传入规范身份与有效参数；仍只有一个 reset／step／历史实现 |
| [simulator/api.py](../../../topogym/simulator/api.py) | 更新 `env_list(details=True)` 的变体查询和 import |
| [simulator/config.py](../../../topogym/simulator/config.py) | 保留 `variation_id` 字段；按需补充校验，不新增第二种环境入口 |
| [tasks/base.py](../../../topogym/tasks/base.py) 与 13 项 Task | 支持不冲突的变体身份；提取必要构建接口；补齐已遗漏的参数接线。单文件移入包后，原 `.base / .scene_presets` 相对导入改为 `..base / ..scene_presets` 或规范绝对导入 |
| [assets/geometry/](../../../topogym/assets/geometry) 与 [planning/motions/cast_coil.py](../../../topogym/planning/motions/cast_coil.py) | 迁移需要的纯构造函数，修复旧 task_variations import，保持实体角色合同 |
| [assets/library.py](../../../topogym/assets/library.py)、资源 catalog、[pyproject.toml](../../../pyproject.toml) | 纳入嵌套变体资源；当前 package-data 模式不覆盖拟新增的 variations 子树，需要同步调整 |
| 活动 YAML／示例／任务文档 | 将当前使用的入口改成新规范名；旧 Hydra 任务块转换为当前 Task 参数，不原样塞入 config |
| [tests/unit/test_task_variations.py](../../../tests/unit/test_task_variations.py)、任务定义／配置／架构测试 | 从参数字典测试扩展为注册→Task 类→资产→身份的行为检查；更新目录允许列表 |
| [scripts/inventory_sources.py](../../../scripts/inventory_sources.py)、[topogym/README.md](../../../topogym/README.md) | 更新模块路径说明与清单分类 |
| [Harbor 交付布局文档](../modules/harbor_docker_delivery_and_runner_layout_zh.md) 及相关打包脚本 | 修正文档中的 task_variations 路径；验证镜像只靠安装包即可加载变体 |

另外更新 registry 中原 `topogym.tasks.<task>:<Class>` 的目标、`SupportGap.module` 文件位置、架构测试的单文件假设，以及所有直接 import 原 Task 类的活动调用方。保留旧导入路径时由包内惰性导出处理，不能复制一份旧 Task 实现。

批量改名后执行全局引用搜索，但不修改 `runs/`／`reports/` 的历史源码副本。对于当前没有调用方的旧配置，不假装改完字符串就已经接入：明确标记为历史或完成真实转换。

当前 AGENTS.md 记录另一个会话正在修改 Task／场景及共享 Env 文件。本计划涉及这些位置，实施时应以届时工作树为准逐处合并，保护对方改动；若出现同函数的实际冲突，列明影响后再协调，不整份覆盖。该边界不阻碍本轮编写计划，也不要求预先暂停所有互不冲突的迁移。

## 9. 实施顺序与阶段产物

### P0：冻结来源与最终映射

- 为三档和表外变体逐一记录源码／资产／参数哈希，确认 source revision。
- 确认当前 base 与计划中“基础档”的实际差异，完成旧 ID 别名表。
- 对 9 个缺失档位登记原因；对仅脚本路线不同的项目登记策略来源，避免虚增环境数。
- 产物：可审阅的迁移映射与资源清单，不改变运行行为。

### P1：目录、注册与低成本试点

- 建立 `tasks/<task>/` 包、三档具体脚本、公共行为、变体记录、按需加载与身份机制，接入当前 Env。
- 先迁移 Fiber 三芯数、Knot 三结型、Blanket simple_folds/fold_roll，验证参数与生成实体确实一致。
- 修复这些设置的具名引用及打包资源；保留旧名字的精确语义。
- 产物：从规范 variation_id 到当前 Task 的第一批完整调用链；未通过物理的不标通过。

### P2：刚体家族与冻结原型

- 迁移 Coil 三档、Claws 三档、Keyhole 三族、Hedgehog 三档、Lock 槽位家族和 Buzz 三线路。
- 统一角色名称、抓取尺寸、初态、资源输出、碰撞表示与父 Task 判据的适配。
- 在各任务同时迁入具备构造依据的表外 setting，退役和未合格项保持明确状态。
- 产物：实体结构正确的变体 Task、可重定位资产及逐项运行证据。

### P3：剩余软体初态与表外构造

- 接入 Rope 三环、Slotted 原型／clearance36、Orbits 四环的精确 setting。
- 独立完成 Blanket gathered_twist 的初始化准备与状态恢复能力；若未完成，保留可追溯构造及阻塞原因。
- 迁入 Horseshoe 旧路线／形状的可用构造能力，但不将其重命名为新余量三档。
- 产物：全部可追溯构造均有正式位置或明确不可部署原因，剩余新设计继续 planned。

### P4：引用收口、安装包与验收清单

- 更新调用、文档、架构约束和交付布局，验证无需仓库 `runs/` 和根目录 `assets/tasks/`。
- 汇总主三档、实验变体、资源级构造、待设计档位及失败原因。
- 没有实际运行通过的条目不因“部署收尾”统一改为可用。

## 10. 验证与完成标准

### 必须验证的行为

1. **选择正确。** 每个规范 ID 和旧别名解析到预期 class、family、revision；planned ID 明确拒绝；环境目录仍为 13 项任务。
2. **生成内容正确。** 检查实际结构差异，如 Fiber 芯数、Lock 槽位／限位、Knot 参数、Claws 两件几何、Buzz 三拱、Coil 9 mm、Blanket 卷曲层。仅检查不同 ID 返回不同字典不够。
3. **身份与复现正确。** 相同 setting／资源／seed 在不同输出路径重建一致；不同实际结构不会共享实例身份；参数覆盖不会悄悄跨档；不依赖绝对路径。
4. **资源可安装。** 在隔离安装目录构建每个已接入变体，禁用对仓库历史目录的访问；资源清单和 wheel 内文件齐全。
5. **真实运行可审查。** 按当前公共验收流程保存源码身份、配置、资产哈希、实际状态、失败报告和标准录像，放 `runs/test_results/`。运行前准备报告规格；GPU 不可用时提供完整 CLI，不静默替换视觉后端。
6. **生命周期不回退。** 对不同物理模型和新增初始化路径检查 reset／seed、句柄失效、当前 episode 回溯以及 Task 状态恢复；变化后的变体逐项初始化与短程推进。共享机制使用代表实例验收，变体自身资产和初态逐项验收，不无差别重复所有测试。
7. **任务证据不越级。** 场景可运行、物理资格、完整机器人成功、无简单捷径、模型难度分开记录。历史成功与当前执行身份不混用；未完成的 solved 判据仍如实返回缺口。

对于本次新增或改变的构造，先用基础几何阻挡／穿套关系检查防止迁移意外破坏机构。前文提出的组合侧移等全面捷径搜索仍是独立验收工作；不能以这次部署替代它，更不能在 Task 成功条件里强制参考动作次数。

### 最终交付

- `tasks/<task>/` 下的 `<task>_easy.py`、`<task>_medium.py`、`<task>_hard.py` 可用具体 Task 脚本，以及全部可追溯变体的状态目录。
- 基础实例 → easy／medium／hard 的最终映射，以及与迁移前默认 base 不一致的版本变更记录。
- 三档新命名、旧名字精确映射、资源 revision 和源码来源清单。
- 当前几何模块和打包资源中的所需能力，不依赖历史路径运行。
- 已修正的活动引用、测试和交付文档。
- 按变体列出的构建、安装、真实初始化／物理推进结果，以及明确的未完成档位。

接受条件是“每项可追溯构造都有明确落位，声称可运行的 setting 在当前链路实际通过对应检查”。**不以凑齐 39 个能 import 的文件作为完成，也不把 9 个尚不存在的 setting 用基础场景复制填满。**
