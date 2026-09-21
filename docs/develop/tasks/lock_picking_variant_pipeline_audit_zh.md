# Lock-picking：固定结构库与数据集变体生成接入审查

**后续实现（同日）**：固定原型库、seed 参数适配、逐实例几何／IK 验证、确定性重试和保存／重载已补齐，见[生成器 v1](lock_picking_seed_generator_zh.md)。下文保留开发前的审查证据；其中“生成入口缺失”等结论描述审查时状态。完整物理执行与数据 writer 本轮不接入，未生成数据集或 H5。

审查日期：2026-09-19。结论：**设计可以沿用“预制结构选择 + 条件参数随机化”，现有生成与检查函数可以复用；当前尚未接成数据集随机生成器。** 生成器的主要产物应是可保存、可恢复的任务实例，Demo 和数据集采集共同消费这个实例，视频是可选产物。

本次只审查和运行几何／IK 检查，未修改生产运行逻辑、未步进动力学、未生成新视频。实验代码、参数、结果和源文件哈希见 [probe.py](../../../runs/demo_metadata/lock_picking/2026-09-19_variant_pipeline_audit/probe.py) 与 [report.json](../../../runs/demo_metadata/lock_picking/2026-09-19_variant_pipeline_audit/report.json)。

## 1. 两类变体如何对应现有设计

| 用户所说的变体 | 当前 Lock-picking 的对应项 | 数据集中的处理方式 |
| --- | --- | --- |
| 预先设计的固定形状 | F1：双槽、一次回退；F2：三槽、28°/32° 两次复位；F3：四槽、三次回退；各自已有 S/M/L 三个代表 | 注册固定 `prototype_id`，按 seed 或指定 ID 选择并加载，不必每条数据重新设计孔槽和限位 |
| 参数随机化 | 盘半径 R、条件盘距 p；未来经验证的摆放与渲染参数 | 显式开启相应轴，在所选原型允许的范围内采样，联动派生尺寸与路径，按变化重新验证 |

固定结构库本身就是合法的变体生成方式，允许不同 seed 选中同一结构，不要求每个 seed 都创造新形状。S/M/L 是代表点，可以直接作为有限库；也可以作为连续参数域的展示锚点，二者不必同时开启。

默认冻结每个原型的复位角、孔槽和限位。现有 plan 中的复位角扰动域属于**可选的机构设计扩展**，不应为了“随机”而自动启用。只有主动改变这些机构参数时，才重新执行动作生成和槽位反推。

保留用户既有约束：

```text
固定三片锁片、三齿；不启用齿数轴。
65 ≤ R ≤ 95 mm
max(150, 150 × R / 80) ≤ p ≤ 180 mm
钥匙齿距 = p；握柄偏移 = 3p + 45 mm；全插入行程 = 4p。
```

R/p 是真实几何参数，不能当作不影响碰撞和动力学的纯外观扰动。颜色、纹理等与 family 独立；当前 palette/roughness 随机域仍是规划，场景没有接入对应 seed 采样。任意姿态旋转也尚未支持：当前机构沿世界 x 轴构建，不能只加一个 yaw 随机数便继续使用原路径。平移字段虽然存在，也要同步处理初态、机器人可达性和相机。

## 2. 本次实际检查

| 检查 | 结果及证据范围 |
| --- | --- |
| 当前 `lock_picking_spaced_preview` 接入公共 `build_variant_episode`，seed 0…63 | 64 个实例 ID，但只有 **1 种配置、1 种几何**；采样参数全部为空。当前配置没有 `variation:`，该入口不会自动选择 family |
| 公共实例描述 | instruction 为空、layout 为 null；`resolved_config` 仅保存配置来源字段，本次未传 sources，因此为 null。传入来源路径也不等于保存完整配置和资产 |
| 九个固定代表的实际检查配置 | `aligned_entry` 正确保留给定几何；本次重新检查同轴路径与必要回退，9/9 通过。九份既有 IK 报告通过，但机器人场景碰撞和新结构物理执行均未认证 |
| 默认场景模式加载 F1_M/F2_M/F3_M | `limited_two_retreats` 将三者都改写成旧 `[-60,-30,0]` 三槽模式；不能只填写 family 几何而保留这个默认模式 |
| 当前物理 oracle 的入口 | F1_M/F3_M 在控制前被明确拒绝：只接受必要回退数为 2。未用模拟结果替代实际物理验证 |
| 复用 `candidate()` 的三个非锚点样本 | 冻结各族名义复位角，只由具名 RNG 采 R/p；3/3 同轴几何与采样 IK 通过。同 seed 参数可复现、family 调用顺序不影响参数。属于审查夹具，不是已注册的生产采样器，也未导出新资产或执行动力学 |
| 提案域边界 | `candidate()` 接受 R=60 mm、p=150 mm，几何和 IK 均通过，但 R 已低于 plan 的 65 mm 下限。说明现有函数不能独立承担全部采样域校验 |
| 现有标准视频 | 三路文件 SHA-256 与既有已完整解码的归档一致；本次未重新解码或录制。该成功轨迹不能用于认证九个新代表 |

三个非锚点样本的整数 seed 均为 20260919，各 family 使用独立具名流：

| Family | R / mm | p / mm | 必要回退 | IK 采样数 |
| --- | ---: | ---: | ---: | ---: |
| F1 | 83.8971 | 172.3040 | 1 | 644 |
| F2 | 83.0760 | 172.9047 | 2 | 939 |
| F3 | 78.1169 | 164.3709 | 3 | 1122 |

上述样本最小关节余量约 0.00318 rad（0.18°），IK 成功不代表具有足够执行余量或已经通过碰撞检查。有限样本也不能认证整个连续域。

**现有成功基线与 F2_M 必须分开命名。** 当前视频的基线是 D1 槽位 `[-60,-30,0]`、限位 ±15°，对应两次 30° 复位；规划的 F2_M 是 `[-60,-32,0]`、限位 ±16°，对应 28°/32°。建议把成功基线注册为独立 `baseline_two_equal_150mm`，不要因同样是两次回退就将 F2_M 标为已通过物理执行。

复现（仓库根目录，零物理步进）：

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-gs121-nyx/bin/python \
  runs/demo_metadata/lock_picking/2026-09-19_variant_pipeline_audit/probe.py
```

## 3. 可以复用的代码和实际缺口

- **生成与验证核心可复用。** [family_space.py](../../../topogym/tasks/lock_picking/family_space.py) 的 `candidate()` 接受具体机构和尺寸参数，返回几何、限位、关键帧、几何证书和 IK；[inverse_variants.py](../../../topogym/tasks/lock_picking/inverse_variants.py) 已分出动作构造、反推、资产导出和机械臂 IK。它们有独立于视频的用途，不必重新写一套 Demo 专用生成器。注意 `candidate(seed, ...)` 中的 `seed` 是原型 `LockGeometry`，不是整数随机种子。
- **固定库和逐实例入口缺失。** 当前 `build()` 批量遍历九个固定组合，依赖 `runs/.../handle_clearance` 的配置、布局和历史帧；没有 `seed → 选原型 → 采参数 → 接受/拒绝实例` 的正式入口。应将所需固定资产、路径/IK 初值及其来源纳入版本化库，消除对临时实验目录的依赖。历史展示生成逻辑不应成为数据集生成的必经步骤。
- **公共随机框架可以继续用。** [VariantRng](../../../topogym/generation/variant_rng.py)、[layout_randomization.py](../../../topogym/generation/layout_randomization.py)、[build_variant_episode](../../../topogym/generation/variant_episode.py) 已有具名流、choice/uniform、派生与拒绝能力。Lock-picking 需要任务声明和适配层，并保存接受 attempt 和拒绝原因；现在公共 retry 会重采全部轴，不返回接受的 retry，固定 family 配额不能靠接受先后顺序实现。
- **实例必须贯穿场景和控制。** 场景应消费已经解析的几何，不能再由 `limited_two_retreats` 隐式改写。初期可显式使用已有 `aligned_entry`，后续将模式与原型身份分开。执行器、`runner` 中的 `len(cycles)==2` 以及完整抓取/换抓/释放策略，都需要按实例的路径和证书处理；不能仅删除“两次回退”检查来放行其他 family。
- **完整实例快照缺失。** 当前 EpisodeKey 不包含生成器/资产库版本，公共 EpisodeSpec 的实际构造也没有填完整配置与布局。应补最终几何、初态、单位/坐标系、相机、成功条件、机器人/物理/控制配置、源资产及路径哈希、生成规则版本和实际验证等级。恢复实例直接加载这些确定值，不重新采样。默认资产缓存只使用 `variant + seed`，并行数据生成应传入独立 `asset_dir` 或内容哈希目录。
- **数据采集未接上。** [runner.py](../../../topogym/tasks/lock_picking/runner.py) 当前写视频、帧 JSON 和报告，没有调用 [EpisodeDatasetWriter](../../../topogym/data/episode_dataset_writer.py)。单臂控制器接口与这个 writer 有可复用基础，但尚未完成实接。必须显式选择三路相机、映射结果，记录时间戳、真实控制命令、完整机器人状态与辅助抓持状态。writer 当前末端 action 是“下一帧实测位姿”，需要与实际下发命令区分，不能宣称两者相同。

## 4. 数据集生成的目标契约

以下是应补的契约，**并非已实现 API**：

```text
request(task_id, seed, pool_version, generator_version,
        prototype_id=auto, randomization_profile, validation_policy)
    → 选择一个预制原型（固定结构模式到此停止结构随机化）
    → 可选：在该原型的条件域内采参数，并派生联动尺寸/场景
    → 构造或加载资产与对象路径；需要时重新求机械臂 IK
    → 按政策验证，返回 accepted instance 或 rejected attempt + reason
    → 保存完整 instance spec + 资产/路径哈希 + 验证记录

同一个已解析实例
    → demo runner → 可选 MP4
    → dataset runner → obs / action / result + 实例身份
```

首版建议提供两个清楚的 profile：`fixed_library` 只选择固定形状；`shape_parameters` 冻结机构角度，再采经验证的 R/p。pose 和 render 随机化分别作为后续独立轴开放，不必为了统一接口强行加入尚未验证的自由度。

新生成实例分开记录 `geometry / ik / robot_collision / physics` 的 `passed / failed / not_run`。物理成功数据集要求的项目未通过时，不输出成功样本；用于结构研究的候选池可以包含几何/IK 样本，但保留真实等级。已有验证只在相同结构、初始化、机器人和执行配置等适用条件下复用。

固定 family 配额时，family 是请求条件，拒绝后在同一 family 内按 `retry` 重采。实例参数应与工作进程数、执行顺序和批次边界无关；输出保存所有拒绝原因，避免默默跳过困难机构。train/validation/test 按原型或父机构分组；同一结构只换颜色/小幅 pose 的样本不能冒充未见结构泛化。参考 IK 和内部几何证书属于验收材料，不自动作为策略观测。

接入完成的最低验收是：**固定原型选择可重现 → 无视频依赖生成并保存实例 → 重新加载同一实例 → 通过要求的执行与验证 → 写数据文件 → 读取后确认实例身份和观测/动作时间轴一致**。再做多 seed、批次重排、重试和覆盖率检查。当前已证明生成核心能用于代表点以外的几何/IK 候选，尚未完成这条数据集闭环。

## 现有视频证据

版本 `2026-09-18_standard_150mm_purple_trace_v1`，三路各 159.35 秒，150 mm 盘距、三齿、两次等角回退。成功物理记录的外观重渲染，夹爪被动关节按实测开合量重建；不是本次新执行，也不代表 F1/F2/F3 新结构已通过动力学。

- [agentview MP4](../../../demos/lock_picking/agentview/2026-09-18_standard_150mm_purple_trace_v1_agentview.mp4)
- [front_oblique MP4](../../../demos/lock_picking/front_oblique/2026-09-18_standard_150mm_purple_trace_v1_front_oblique.mp4)
- [wrist MP4](../../../demos/lock_picking/wrist/2026-09-18_standard_150mm_purple_trace_v1_wrist.mp4)
