# Horseshoe 现有候选能否组成三档

## 用户选定方案与部署结果（同日后续更新）

用户已确认先采用形状／定向三档，替代原先“宽／中／窄余量”定义：

| 难度 | 选定代表 | 标准入口 | 当前证据 |
|---|---|---|---|
| easy | `waist_mild`，轻收腰、近圆环 | [horseshoe_ring_easy.py](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_easy.py) | 已接入；有历史完整零件几何路径 |
| medium | `u_mild`，较方 U、近圆环 | [horseshoe_ring_medium.py](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_medium.py) | 已接入；有历史完整零件几何路径 |
| hard | `waist_ellipse`，轻收腰、椭圆环 | [horseshoe_ring_hard.py](../../../topogym/tasks/horseshoe_ring/horseshoe_ring_hard.py) | 已接入；有历史几何路径及环内转角消融 |

三档均使用原冻结模板、每侧 1 个链节，链中心线长半轴 18 mm（模板单位），默认场景 scale=2。common 实体、终态判据和模板资源未修改。默认 `base=easy`；旧照片比例 reference 与 21 个描述性候选入口归档到 `tasks/legacy/horseshoe_ring/`，撤下旧具名注册。被选三个候选的构造直接复用在难度文件中，活动代码不导入 legacy。

这次确定的是**暂定设计档位**：medium 的实际区分、捷径排除及三档完整机器人执行仍待验证，不能标为三档已由机器人 solve。后续按模型表现校准。资产构建与入口检查见[部署验收](../../../runs/test_results/horseshoe_tiers_20260925_01/README.md)。

以下保留定档前的调查与两种方案比较；其中“占位／暂留候选／尚未选定”等描述是本次决定前的状态，以本节为准。


2026-09-25。核对当前 Task、随包模板、历史生成器、连续几何证书和对照结果；本轮没有重新运行机器人，也没有修改 Horseshoe 几何、注册内容或三档占位。

**结论：有可复用的构造和路径，但目前没有证据充分的“宽／中／窄穿出余量”三件套，不能直接挑三个旧名字填档。** 若愿意将难度轴改为“取环时的方向配合”，`waist_mild → u_mild → waist_ellipse` 可以作为优先验证的假设，其中 medium 的区分最弱。若维持原表，建议在同一已成功圆环实例上只改变目标环内径，重新测量并冻结三档。

## 1. 目前究竟有哪些东西

| 现有组 | 内容与证据 | 能否直接当三档 |
|---|---|---|
| 当前 `reference` | 照片比例模板，每侧 3 个链节；当前默认环境 | 只有一个设置；不能继承单链节 tutorial 模板的成功证书 |
| 历史 baseline、F1/F2/F3 | 旧完整机器人流程可追溯；F1 高处接近、F2 外侧接近、F3 后方接近；另有尺寸、位置、yaw 等小扰动 | 不能。路线由旧 planner 指定，场景没有强制 agent 走指定接近点；全局同比缩放也不构成独立的穿出余量轴 |
| 11 个 `chain_*` | 单链节 tutorial 原型，只改未直接抓持的中间链环；马蹄、目标圆环、保存的关节与零件轨迹固定 | 可用于几何泛化／稳健性对照，不足以定难度 |
| 10 个 coupled-shape | 4 种马蹄与椭圆环组合，部分各带 17／17.5／18 mm 链长；都有完整零件连续几何路径 | 可作为设计种子；缺对应机器人流程和难度分档证据 |

当前 21 个实验入口及 `reference` 全部暂留 [horseshoe_ring](../../../topogym/tasks/horseshoe_ring)；easy／medium／hard 继续明确占位。旧 F 编号不与新档位自动对应。

历史路线定义见 [family_routes.py](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring/family_routes.py)，生成器还明确拒绝将非圆／变形原型直接套入旧物理流程：[variant_generator.py](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring/variant_generator.py)。历史机器人来源见 [oracle 清单 §3](planner_oracle_inventory_20260925_zh.md#3-horseshoe-ring)。

## 2. 为什么不能按链环名字直接排档

11 个 fixed-trace 模板的马蹄相同，目标环中心线半径均为 31 mm、线材半径 1.4 mm；场景 scale=2，目标环内直径为 **118.4 mm**。改变的是链环，不是目标环口径。

| 候选（省略 `chain_`） | 链中心线半轴／线材半径，模板 mm |
|---|---|
| slender | (18, 5)／0.8 |
| shorter、longer | (17.5, 5)、(18.5, 5)／0.7 |
| narrower、wider | (18, 4.7)、(18, 5.3)／0.7 |
| compact、elongated_wide | (17.7, 4.8)、(18.3, 5.2)／0.7 |
| thicker | (18, 5)／1.1 |
| long_control、wide_control、thick_control | (19, 5)／1.0；(18, 5.5)／1.0；(18, 5)／1.2 |

这些参数见 [variants.json](../../../assets/tasks/horseshoe_ring/fixed_trace_v1/variants.json)。旧 README 记载 11 个候选中 8 个通过，但它引用的 `runs/environment-solvability/horseshoe_ring/fixed_ik_trace_v1/` 当前不存在；本轮未找到对应的逐候选 compatibility 报告，因此不能替任何具体三个候选补写“已通过”。

仍能追溯的 [fixed_trace_variants.py](../../../runs/demo_metadata/horseshoe_ring/2026-09-19_variant_generator_v2/source_snapshot/topogym/tasks/horseshoe_ring/fixed_trace_variants.py) 明确将范围限定为完整零件几何路径、采样机器人碰撞和 ±X 直拉对照，并写出 `physics_steps=0`、`dynamic_execution_verified=False`。即使恢复这 8 个报告，也不是 8 次新的动力学成功。

链环变短可能收紧马蹄连接处，却让目标环远离链环；变粗还改变接触动力学和质量。因此 `longer / slender = easy`、`shorter / thicker = hard` 都需要验证，不能仅凭名称成立。

## 3. 形状候选里哪些最有价值

本轮逐项比较：**当前随包 10 个模板与历史 references/template.json 的 JSON 内容完全一致；证书中的模板哈希也一致。** 这是来源对应检查，不是当前生成器／物理引擎的重验。

| 组 | 当前候选 | 历史完整路径最小保守间隙下界，场景 mm | 判断 |
|---|---|---:|---|
| 轻收腰、近圆环 | `waist_mild` | 0.1481 | 四组中最适合先做机器人迁移；仍不能称“宽余量 easy” |
| 较方 U、近圆环 | `u_mild`、`u_mild_chain17p5`、`u_mild_chain17p0` | 均 0.1274 | 可作为中档候选，是否明显比 mild 难尚无证据 |
| 轻收腰、椭圆环 | `waist_ellipse`、`waist_ellipse_chain17p5`、`waist_ellipse_chain17p0` | 均 0.1173 | 最有价值的 hard 设计种子：环自身相位需要配合 |
| 深收腰、近圆环 | `deep_waist`、`deep_waist_chain17p5`、`deep_waist_chain17p0` | 均 0.1002 | 不建议仅因“deep”就定 hard；当前证据主要是更贴近该路径的检查阈值 |

证书要求的下界为 0.10 mm。这些值是**各自找到的一条路径在数值保守检查下的下界**，不是该场景最佳路线的最大余量，也不是可容许的机器人位姿误差。不能把 0.1481／0.1274／0.1002 当成已经测得的三档难度。

具体反例：`deep_waist` 的链长从 18 降到 17.5、17 mm 时，整条路径最小下界始终是 0.1002 mm；右马蹄—下链环下界约为 0.818／0.637／0.198 mm，但上链环—目标环下界反而约为 0.132／0.398／0.794 mm。瓶颈来自不同部位，链长不能提供统一的单调排序。

更有辨识度的是 [controls.json](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/controls.json)：

- 四个基础形状的初始 ±X 直拉都被阻挡；只排除了这两条路径，没有排除侧移后直拉、倾斜后越过一只马蹄等捷径。
- `waist_ellipse` 的已知解相对种子路径增加约 **58.66°** 环内转角。保持位置和法向变化、去掉该转角，392 个采样中 154 个低于要求间隙，其中 153 个接触／相交。
- `waist_mild` 相同消融没有失败采样；`u_mild` 有 13 个、`deep_waist` 有 7 个低于阈值。这能比较特定路径的敏感性，不能证明全空间最短解或动作必需性。

十个证书均明确 `robot_execution_verified=False`、`dynamic_execution_verified=False`、`lab_obstacle_collision_verified=False`。已有全程几何解值得回收，但旧圆环抓点不能直接视为新椭圆环的合法抓点。

原始资料：[参考实例及证书](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/references)、[历史设计说明](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/README.md)、[本轮核对数据](../../../runs/test_results/variation_legacy_cleanup_20260925_01/horseshoe_review.json)。

## 4. 建议如何落到 easy / medium / hard

**优先建议：保持原表“宽／中／窄余量”定义。** 从有完整机器人流程的某个精确圆环实例恢复模板和初态；固定马蹄、链环、机器人、抓持规则与起点，只调整目标环中心线半径，线材半径保持不变。不要混用当前三链节 reference 与历史单链节 tutorial。

依次执行：

1. 在原成功尺寸附近提出少量半径候选，用现有零件路径作初值重新检查与优化；同时检查初始装配、端部止挡和链连接。
2. 对每个候选尝试 ±X／±Y／±Z 直移、少量侧移后直拉、倾斜后直接穿出等短路线。发现简单解就排除该尺寸；有限搜索没有发现捷径只能报告“已测捷径未通过”。
3. 用相同安全裕度与采样密度检查穿出段；测量可接受的位置／角度扰动范围。选出三个**都有正余量、容错有明显差距**的尺寸，不从刚好不穿模的临界值硬凑 hard。
4. 再经标准 simulator 完整机器人执行，确认抓点、质量变化、摩擦和 assist 合同下均可解；冻结三档及证据，最后按模型表现校准。

这条路线复用旧解法、只改变一个主要几何轴，适合目前赶进度。具体半径和误差阈值仍需测量，现有证据不足以现在给出三个可靠数值。

**备选：改用形状／定向难度。** 可以先测试 `waist_mild`（easy 候选）、`u_mild`（medium 候选）、`waist_ellipse`（hard 候选），链长先统一 18 mm，避免再混入链长轴。优点是已有完整零件路径和相位消融；缺点是需要迁移三套机器人抓取，medium 区别弱，且这会改变原先“只压缩余量”的档位含义。没有通过机器人和捷径检查前，不建议正式填进难度脚本。

本轮因此保留全部 Horseshoe 候选，不归档、不提前定档。其他三档构造齐备任务的表外入口归档另见 [部署实施记录](variation_deployment_implementation_20260925_zh.md)。
