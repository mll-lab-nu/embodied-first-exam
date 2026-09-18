# TopoGym Weekly Report · 2026-09-17

统计截止：2026-09-17 17:30:57 CDT（America/Chicago）。依据今天活跃的 14 份工程会话记录，覆盖 9 个任务；另补查电流棒。跨日续接纳入，审批及本报告会话排除。此前 demo 作为累计基础，不声称整个星期均已审计。

[打开可播放周报](index.html) · [结构化清单](report.json) · [来源快照](evidence_snapshot.json)

## 单任务五项门槛 · 十任务 Inspect

增补检查：2026-09-17 18:17:34 CDT。当前现存代码与报告的增补 inspection；原 demo 清单仍保持其 17:30:57 快照。未重跑物理仿真或完整冷启动恢复。

逐项判定，不加总成等级。“达到”仅对声明范围成立；“尚未验证”不等于实现失败。G5 的具体判据是本次补全的建议口径。

| 门槛 | 达到什么程度 | 可开始提炼 |
| --- | --- | --- |
| G1 一个基准实例可独立恢复 | 从保存的参数、资产与明确版本的依赖，在新进程恢复同一初态；不需手改代码或未记录实验文件。核对物体位姿、机器人状态、固定／抓持约束；柔性任务还包括参考网格与初始形状。 | 实例 Spec、资产与依赖清单、保存 / 加载接口。 |
| G2 任务语义和有效性明确 | 成功条件与允许辅助明确；正确路径可行，至少一个针对性错误操作确实被阻挡。声明物理有效时，要有 settle 和关键接触检查；通过范围须匹配当前基准。 | 验证协议、成功 / 有效性分离、证据等级、失败分类。 |
| G3 一个 family 有可用参数邻域 | 先开放少量有依赖规则的参数；变化后同步生成几何、初态、抓点与所需路径，保留机关约束。少量离散代表不自动证明完整连续参数盒；几何邻域与物理邻域分别声明。 | 参数定义、条件采样、参数到场景 / 动作的任务生成适配器。 |
| G4 小批量生成不需逐例修补 | 给定一组实例 seed，自动生成、验证、接受或拒绝；失败样本与原因可追溯；同实例不受批次顺序影响。固定一套规则跑完小批次，不能事后逐例改代码冒充自动化。 | 通用批处理、失败重采样、证据缓存与失效规则。 |
| G5 参数与难度关系有证据 | 在统一任务协议、控制器与扰动分布下，比较多个参数点及重复结果，记录成功率、重试、动作成本或容错区间。机制下界可作理论难度特征；单条 demo 长短、外形复杂或家族编号不等于实测难度。 | 难度特征、标定 / 分层评测与课程采样接口；实测前不固化 easy / medium / hard。 |

| 任务 | G1 恢复 | G2 语义 / 有效性 | G3 邻域 | G4 批量 | G5 难度 |
| --- | --- | --- | --- | --- | --- |
| Cast Keyhole | 部分达到 | 达到（限定范围） | 达到（限定范围） | 部分达到 | 尚未验证 |
| Cast Coil | 部分达到 | 达到（限定范围） | 部分达到 | 尚未达到 | 尚未验证 |
| Hedgehog in Cage | 部分达到 | 达到（限定范围） | 部分达到 | 尚未达到 | 尚未验证 |
| Horseshoe Ring | 部分达到 | 部分达到 | 部分达到 | 部分达到 | 尚未验证 |
| Interlocked Claws | 部分达到 | 部分达到 | 尚未达到 | 尚未达到 | 尚未验证 |
| Lock Picking | 部分达到 | 达到（限定范围） | 部分达到 | 尚未达到 | 部分达到 |
| Fiber Bundling | 部分达到 | 达到（限定范围） | 达到（限定范围） | 部分达到 | 尚未验证 |
| Rope Threading | 部分达到 | 部分达到 | 尚未达到 | 尚未达到 | 尚未验证 |
| Knot Untying | 部分达到 | 部分达到 | 尚未达到 | 尚未达到 | 尚未验证 |
| 3D Buzz Wire | 部分达到 | 部分达到 | 尚未达到 | 尚未达到 | 尚未验证 |

**提炼重点：** Keyhole 的参数生成 / 验证链；Coil、刺球、开锁的任务契约和证据协议；光纤的稀疏子集 / 参数 RNG；马蹄环的几何邻域证书。其余先收敛基准与局部验证。

**共性缺口：** 未找到完整 G1 新进程归档恢复验收；G4 的免逐例修补、完整接受 / 拒绝、实例顺序无关尚未全部闭环。开锁仅有 G5 理论动作下界，实测难度尚未标定。已有保存资料可支持 Spec / 加载草案，不等同于恢复验收已经通过。

[结构化五项检查](inspection.json) · [检查来源与哈希](inspection_snapshot.json) · [光纤 seed 顺序复测](inspect_probes.json)

## 1. 有变体讨论：变体轴、代表与对应 demo

### Cast Keyhole · 槽形解锁

**9 / 9 外形代表已有物理 demo。** 三种动作机制、每类三款明显不同的外轮廓已经完成；随机生成器另有三个通过验证的连续样本。

**五项门槛 Inspect**

判断基准：当前下孔道基准及 F1/F2/F3 的已验收实例；预抓取 + 接触门控辅助抓持，分离后保持。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 归档包含几何、轨迹、参数及哈希；三个随机样本有临时目录独立重建、完整 geometry.json 哈希一致的记录。 | 该记录只证明几何重建。尚未找到仅从归档输入在新进程加载并核对完整仿真初态的验收；family_seed 仍通过预设 runs 路径取父实例，要明确恢复入口与依赖。 | [证据 1](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/generator_manifest.json) · [证据 2](../../../topogym/tasks/cast_keyhole/family_variants.py) · [证据 3](../../../topogym/tasks/cast_keyhole/robot_execution.py) |
| G2 任务语义和有效性明确 | 达到（限定范围） | 分离目标、预抓取和辅助约束明确。九款及三个随机实例有两档步长的物理执行与独立复核；证书保留原路径、直拉或关键动作删减负对照，末态保持检查通过。 | 仅认证声明的辅助抓持任务；不包含自由拾取、解除约束落桌、纯摩擦抓持或全局唯一解。 | [证据 1](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/generator_manifest.json) · [证据 2](../../../topogym/tasks/cast_keyhole/family_pipeline.py) |
| G3 一个 family 有可用参数邻域 | 达到（限定范围） | 三个 family 已定义机制参数与外形联动；除九个代表外，三个同时改变 IK 参数和外形的样本通过全链验证，另有退化捷径样本被拒绝。 | 可提炼“提议—验证—拒绝”的小范围生成适配器；尚不能承诺每个参数组合可解，也未测大样本接受率。 | [证据 1](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/variant_space.json) · [证据 2](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/generator_manifest.json) |
| G4 小批量生成不需逐例修补 | 部分达到 | 已有自动 build / geometry / physics / audit / qualify、失败日志、最大尝试次数，以及带几何、轨迹、代码指纹的扫掠缓存；已保存接受与拒绝样本。 | sample() 使用一个批次 RNG，family 随已接受数量推进；实例 seed 与批次 seed 尚未形成顺序无关的契约。需单例 / 正序 / 逆序 / 分批重跑比对，并确认重试与缓存失效一致。 | [证据 1](../../../topogym/tasks/cast_keyhole/family_pipeline.py) · [证据 2](../../../topogym/tasks/cast_keyhole/family_variants.py) |
| G5 参数与难度关系有证据 | 尚未验证 | 已有机制必要动作对照与行程参数，但未见统一控制器下的难度标定。 | 需固定外形与抓持协议，比较行程、偏心和折返参数对成功率、容错、重试的影响；三类动作名称不能直接当难度。 | [证据 1](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/variant_space.json) |

**总结：** 生成与验证链最接近可复用；G1 的完整恢复和 G4 的顺序无关性仍缺闭环，G5 未标定。

**现在可提炼：** 优先提炼 Spec / 证据 schema、条件生成适配器，以及现有验证阶段与缓存指纹；批处理先保留为候选实现。

**下一步：** 把一个已归档实例做成独立恢复包并核对初态；再以显式 instance_seed 做批次顺序回归。

| Family | 动作 | 参数 |
| --- | --- | --- |
| F1 长行程错齿 | 加长穿齿行程，依次通过错齿 | 种子行程 ×1.20；探索 ×1.10–1.35 |
| F2 偏心开口 | 侧偏、上移后绕过转向窗口 | 种子右偏 6 mm、上移 3 mm；探索右偏 4.5–9 mm，上移为其一半 |
| F3 前送—转向—回退 | 深入下腔 → 转动 → 回退 → 横移分离 | 种子转动 25°、回退 25.5 mm；探索 20–30°、回退约 19.5–31.5 mm |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| F1_A | 圆冠长梯 | 完整物理 demo |
| F1_B | 方冠宽肩 | 完整物理 demo |
| F1_C | 渐缩楔架 | 完整物理 demo |
| F2_A | 豆形偏头 | 完整物理 demo |
| F2_B | 斜肩偏头 | 完整物理 demo |
| F2_C | 梨形偏头 | 完整物理 demo |
| F3_A | 圆腹回钩 | 完整物理 demo |
| F3_B | 方腹折返 | 完整物理 demo |
| F3_C | 双腹葫芦 | 完整物理 demo |

- 九款代表和三个随机样本均通过 1 ms / 0.5 ms 物理执行与独立复核；不代表整个连续采样域都通过。
- 外形宽高倍率 0.96–1.04、模板横移 −0.5–0.5 mm；材质库独立于 family。每次变动需重新验证机构、碰撞与物理执行。
- 视频从预抓取开始，双指接触后辅助抓持，完成分离后双臂保持；未包含拾取、落桌释放或纯摩擦抓取验证。

[生成空间与命令](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/variant_space.json) · [随机样本验证](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/generator_manifest.json)

可播放 demo：

- [Cast Keyhole · 双臂物理执行](../../../runs/demos/cast_keyhole/2026-09-17_current_instance_physical_detail.mp4)（23.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_current_instance_physical/index.html)。
- [Cast Keyhole · 长行程错齿型](../../../runs/demos/cast_keyhole/2026-09-17_long_stroke_v1_detail.mp4)（23.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_long_stroke_v1/archive_manifest.json)。
- [Cast Keyhole · 偏心转向窗型](../../../runs/demos/cast_keyhole/2026-09-17_eccentric_window_v1_detail.mp4)（24.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_eccentric_window_v1/archive_manifest.json)。
- [Cast Keyhole · 前送—转向—回退型](../../../runs/demos/cast_keyhole/2026-09-17_turnback_v1_detail.mp4)（28.3 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_turnback_v1/archive_manifest.json)。
- [Cast Keyhole · F1_A · 圆冠长梯](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F1_A_detail.mp4)（23.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F1_A/archive_manifest.json)。
- [Cast Keyhole · F1_B · 方冠宽肩](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F1_B_detail.mp4)（23.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F1_B/archive_manifest.json)。
- [Cast Keyhole · F1_C · 渐缩楔架](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F1_C_detail.mp4)（23.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F1_C/archive_manifest.json)。
- [Cast Keyhole · F2_A · 豆形偏头](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F2_A_detail.mp4)（24.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F2_A/archive_manifest.json)。
- [Cast Keyhole · F2_B · 斜肩偏头](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F2_B_detail.mp4)（24.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F2_B/archive_manifest.json)。
- [Cast Keyhole · F2_C · 梨形偏头](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F2_C_detail.mp4)（24.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F2_C/archive_manifest.json)。
- [Cast Keyhole · F3_A · 圆腹回钩](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F3_A_detail.mp4)（28.3 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F3_A/archive_manifest.json)。
- [Cast Keyhole · F3_B · 方腹折返](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F3_B_detail.mp4)（28.3 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F3_B/archive_manifest.json)。
- [Cast Keyhole · F3_C · 双腹葫芦](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_F3_C_detail.mp4)（28.3 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_F3_C/archive_manifest.json)。
- [九款全过程并排对照](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_process_grid.mp4)。
- [九款灰色外形对照（非执行）](../../../runs/demos/cast_keyhole/2026-09-17_families_v1_shape_grid.mp4)。

**另一会话暂停的三条候选（与 F1/F2/F3 分开）：**

| 候选 | 动作轴 | 当前状态 |
| --- | --- | --- |
| offset_window 偏心窗口 | 小偏心绕行；仍兼容原解法 | 物理与独立复查通过；全程工作目录录像 24.08 s，未正式归档 |
| double_gate 双重错槽 | 增加两道不同高度的横向换槽 | 物理报告通过；独立复核与完整录像未完成 |
| tilted_window 倾转穿窗 | 25°侧转 + 8°出平面倾转，再恢复 | 物理与复查通过；现有近景只到 13.25 s / 约 28.5 s 全流程，不作完整 demo |

[offset_window 全程工作目录录像](../../../runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/offset_window/recording/detail.mp4) · [交接记录](../../../runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/session_handoff.json)。

### Cast Coil · 卷绕件拆解

**3 个家族种子有 demo；9 个新外形待录制。** 已有基线、三个运动反推种子，以及三个基线单参数外观 demo。最新九款可见结构已通过几何与 IK，不能借用旧种子视频作为新结构的物理证据。

**五项门槛 Inspect**

判断基准：3 倍原型及三个反推家族种子；完整拆解、落桌释放、自由静置；新九款可见外形另行判断。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 基线归档有 resolved config、assets/template、source_plan、执行源码和半步证据；runner 显式接收 plan，模板哈希会核对。 | runner 仍 compose 仓库 preset 并设置固定运行值；没有“归档 Spec → 新进程同初态”的对照记录，不能只据文件齐全算通过。 | [证据 1](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/archive_manifest.json) · [证据 2](../../../topogym/tasks/cast_coil/robot_demo.py) |
| G2 任务语义和有效性明确 | 达到（限定范围） | 原型 / 已归档种子有正确连续路径、直拉阻挡证据、接触门控辅助抓持与完整释放静置；基线 validation.complete 和 passed 均为 true，半步复核保留。 | 结论限于已验收实例；新 A1–C3 几何 / IK 证据不继承旧视频的物理资格。 | [证据 1](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/validation.json) · [证据 2](../../../topogym/tasks/cast_coil/appearance.py) · [证据 3](../../../docs/develop/tasks/cast_coil_family_space_zh.md) |
| G3 一个 family 有可用参数邻域 | 部分达到 | 机制 θ=3/6/9 mm 的九个代表会联动通道与路径；三种基线单参数外观也有物理 demo。缩放规则会同步平移、转轴和推进量。 | 最新连续 θ / d / δ 候选域尚未完成条件采样器和新外形物理验证；已有几个离散点不能代表任意联合采样都可用。 | [证据 1](../../../docs/develop/tasks/cast_coil_family_space_zh.md) · [证据 2](../../../topogym/tasks/cast_coil/appearance.py) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 已有各阶段脚本与九个固定代表的实验入口。 | 还没有已验收的按实例 seed 自动提议、重采样、保留拒绝原因且顺序无关的小批量生成闭环。 | [证据 1](../../../docs/develop/tasks/cast_coil_family_space_zh.md) |
| G5 参数与难度关系有证据 | 尚未验证 | 目前证明的是运动参数与结构约束对应。 | 需测 θ、净空、厚度对同一控制器成功率或容错的影响；偏心更大、推进更长不自动等于更难。 | [证据 1](../../../docs/develop/tasks/cast_coil_family_space_zh.md) |

**总结：** 基准语义和物理证据扎实，参数适配已有雏形；目前仍以代表点实验为主。

**现在可提炼：** 提炼模板 / 计划配对、几何证书、正反例验证协议；把尺度与轨迹联动封装成任务适配器草案。

**下一步：** 先固定一个 family 的小参数邻域，补新外形物理验证，再实现统一 seed 采样与拒绝记录。

| Family | 动作 | 参数 |
| --- | --- | --- |
| A 偏心转动 | 滑开 → 绕偏移轴转 90° → 移出 | 偏心 e=3/6/9 mm；滑开 27.75/33.75/39.75 mm；左侧斜切 9/12/15 mm |
| B 分段错位 | 45° → 高度错位 → 再 45° → 移出 | 错位 h=3/6/9 mm；四角为逐渐增大的直角台阶 |
| C 旋转推进 | 转 90°时同步轴向推进 → 移出 | 推进 a=3/6/9 mm；四角斜切 9/12/15 mm，近似八边形 |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| A1 | 轻偏心 3 mm | 几何 + IK 已检查；新外形无物理录像 |
| A2 | 中偏心 6 mm | 几何 + IK 已检查；新外形无物理录像 |
| A3 | 大偏心 9 mm | 几何 + IK 已检查；新外形无物理录像 |
| B1 | 低台阶 3 mm | 几何 + IK 已检查；新外形无物理录像 |
| B2 | 中台阶 6 mm | 几何 + IK 已检查；新外形无物理录像 |
| B3 | 高台阶 9 mm | 几何 + IK 已检查；新外形无物理录像 |
| C1 | 短推进 3 mm | 几何 + IK 已检查；新外形无物理录像 |
| C2 | 中推进 6 mm | 几何 + IK 已检查；新外形无物理录像 |
| C3 | 长推进 9 mm | 几何 + IK 已检查；新外形无物理录像 |

- 每类以 6 mm 为新基型；候选轴为机制尺寸 θ、厚度倍率 d=0.90–1.10、轮廓微调 δ∈{−0.75,0,+0.75} mm；轮廓长度 L=6+θ+δ。参数需联动，不是任意组合都可解。
- 已有外观单轴 demo：正面缩小 5%、叠层加厚 10%、外角切角 5.25 mm；它们属于原始基线，不等于最新 A1–C3 九款。
- 三个旧种子及外观 demo 均为接触后辅助抓持的物理执行，完整拆解、分别落桌、解除辅助并自由静置。新九款仍缺动力学和录像。

[可交互九宫格](../../../runs/environment-solvability/cast_coil/family_space_20260917/index.html) · [最新家族空间](../../../docs/develop/tasks/cast_coil_family_space_zh.md) · [基线单参数外观对照](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_single_v1/index.html)

可播放 demo：

- [Cast Coil · ALOHA 双臂完整拆解](../../../runs/demos/cast_coil/2026-09-17_aloha_full_front_oblique.mp4)（30.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_aloha_full/index.html)。
- [Cast Coil · 偏心转动](../../../runs/demos/cast_coil/2026-09-17_inverse_eccentric_turn_front_oblique.mp4)（30.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_inverse_eccentric_turn/index.html)。
- [Cast Coil · 两段转动与错位解锁](../../../runs/demos/cast_coil/2026-09-17_inverse_split_turn_offset_front_oblique.mp4)（32.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_inverse_split_turn_offset/index.html)。
- [Cast Coil · 旋转与轴向推进](../../../runs/demos/cast_coil/2026-09-17_inverse_axial_screw_turn_front_oblique.mp4)（30.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_inverse_axial_screw_turn/index.html)。
- [Cast Coil · 基础版单参数 · 正面缩小 5%](../../../runs/demos/cast_coil/2026-09-17_appearance_face_small_front_oblique.mp4)（30.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_face_small/index.html)。
- [Cast Coil · 基础版单参数 · 叠层加厚 10%](../../../runs/demos/cast_coil/2026-09-17_appearance_depth_thick_front_oblique.mp4)（30.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_depth_thick/index.html)。
- [Cast Coil · 基础版单参数 · 外角切角 5.25 mm](../../../runs/demos/cast_coil/2026-09-17_appearance_corner_cut_front_oblique.mp4)（30.1 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/cast_coil/2026-09-17_appearance_corner_cut/index.html)。

### Hedgehog in Cage · 刺球出笼

**A1 / B1 / C1 有 demo；6 个外形待实现。** 采用最新 v2：三个动作 family 各配原型、鼓腹、八棱收腰三种外形。三条父路径已有完整物理证据，默认浅木色刺球、深木色笼子。

**五项门槛 Inspect**

判断基准：固定笼、十刺球、S2 抓点；A1/B1/C1 三个父实例，取出后落桌、解除辅助、撤离静置。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 三个 family 的归档保存 motion、IK、笼资产、软件环境、provenance 及两档执行；B 的最终运动参数另存为明确预设。 | 重建代码仍读取 SEED 下的 escape / release 等输入；须把这些依赖纳入恢复入口，核对新进程完整初态，避免误用 B 的探索默认值。 | [证据 1](../../../docs/develop/tasks/hedgehog_in_cage_family_demos_zh.md) · [证据 2](../../../topogym/tasks/hedgehog_in_cage/family_motion.py) · [证据 3](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/archive_manifest.json) |
| G2 任务语义和有效性明确 | 达到（限定范围） | 三条匹配路径与完整物理执行通过；六条跨 family 路径碰撞，关键动作删减受阻；抓持、释放和静置范围明确。 | 仅覆盖这三个父实例与声明的辅助抓持。新增六个外观规格不是已验证实例。 | [证据 1](../../../docs/develop/tasks/hedgehog_in_cage_family_demos_zh.md) · [证据 2](../../../docs/develop/tasks/hedgehog_in_cage_family_space_zh.md) |
| G3 一个 family 有可用参数邻域 | 部分达到 | 已有三个可解父点与外形增材、保护全机器人扫掠空间的规则；给出了鼓腹 / 八棱收腰条件范围。 | v2 新六款尚未实现 / 验收，连续动作范围也是提议域。还缺至少一个 family 的小邻域生成与逐实例完整验证。 | [证据 1](../../../configs/task_variants/hedgehog_in_cage/family_space_v2.json) · [证据 2](../../../docs/develop/tasks/hedgehog_in_cage_family_space_zh.md) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 父实例有分阶段执行和证据留存。 | 尚无 v2 邻域的自动条件采样、失败保留 / 重采样、顺序无关批次证据；先验收池采样仍是规划。 | [证据 1](../../../docs/develop/tasks/hedgehog_in_cage_family_space_zh.md) |
| G5 参数与难度关系有证据 | 尚未验证 | A / B / C 有动作区别与负对照，可提出训练顺序假设。 | 没有统一控制器和扰动试验；A 易、B 中、C 难不能作为已经测出的难度标签。 | [证据 1](../../../docs/develop/tasks/hedgehog_in_cage_family_space_zh.md) |

**总结：** 父实例已具备清晰验证协议；三类父点尚不足以支撑类内随机生成。

**现在可提炼：** 提炼任务成功 / 释放协议、动作 witness 与证书关联；先建立父实例 Spec，再把保护扫掠空间的外形规则做成候选适配器。

**下一步：** 先完成 A2/A3 的生成与复验，获得一个实际可用的 family 外观邻域，再扩到 B/C。

| Family | 动作 | 参数 |
| --- | --- | --- |
| A 单斜窗绕出 | 侧移配合倾斜，穿过偏置斜窗 | 已验证侧移 10 mm、倾角 −4°；后续探索 8–12 mm、−5°至−3° |
| B 双门槛换层 | 出主笼 → 换层对齐 → 通过外置挡板 | 第二挡板约 X=220 mm；后续探索 210–230 mm，保持双阶段通过 |
| C 螺旋导向 | 位置与姿态同步转向，沿连续扭带退出 | 已验证新增转向 36°、径向距离 200 mm；探索 32–40°、190–210 mm |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| A1 | 单斜窗 · 原型轮廓 | 完整物理 demo |
| A2 | 单斜窗 · 鼓腹厚框 | 设计规格；未实现／未验收 |
| A3 | 单斜窗 · 八棱收腰 | 设计规格；未实现／未验收 |
| B1 | 外置双门槛 · 原型轮廓 | 完整物理 demo |
| B2 | 外置双门槛 · 鼓腹厚框 | 设计规格；未实现／未验收 |
| B3 | 外置双门槛 · 八棱收腰 | 设计规格；未实现／未验收 |
| C1 | 螺旋导向 · 原型轮廓 | 完整物理 demo |
| C2 | 螺旋导向 · 鼓腹厚框 | 设计规格；未实现／未验收 |
| C3 | 螺旋导向 · 八棱收腰 | 设计规格；未实现／未验收 |

- 鼓腹：中段半径增加 12–18 mm，端部增加 0–4 mm；八棱收腰：肩部增加 12–18 mm、腰部增加 0–3 mm，腰肩比 0.80–0.90。高度暂固定 240 mm。
- 先保留父机关与完整机器人运动空间，在其外增材形成外观；首批复用父运动，六个候选仍须逐一做几何和完整物理验收。
- 三个父 demo 均从 S2 预抓取开始，接触后辅助抓持，取出、落桌、释放、撤离和静置。A→B→C 只可作动作复杂度的暂定顺序，尚无实测难度排名。

[v2 九宫格规划](../../../runs/environment-solvability/hedgehog_in_cage/family_design_v2/index.html) · [三个家族同步播放](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_representatives_v1/index.html) · [参数与验收规则](../../../docs/develop/tasks/hedgehog_in_cage_family_space_zh.md)

可播放 demo：

- [刺球出笼 · CLASSIC](../../../runs/demos/hedgehog_in_cage/2026-09-16_classic_wood_extraction_front_oblique.mp4)（82.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood/index.html)。
- [刺球出笼 · 轨迹反推偏心斜窗笼](../../../runs/demos/hedgehog_in_cage/2026-09-17_eccentric_window_v1_front_oblique.mp4)（82.2 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_eccentric_window_v1/index.html)。
- [刺球出笼 · A · 单斜窗绕出](../../../runs/demos/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1_front_oblique.mp4)（82.6 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_a_oblique_gate_v1/index.html)。
- [刺球出笼 · B · 双门槛换层](../../../runs/demos/hedgehog_in_cage/2026-09-17_family_b_staggered_gates_v1_front_oblique.mp4)（113.0 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_b_staggered_gates_v1/index.html)。
- [刺球出笼 · C · 螺旋导向](../../../runs/demos/hedgehog_in_cage/2026-09-17_family_c_helical_guide_v1_front_oblique.mp4)（90.6 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_c_helical_guide_v1/index.html)。

### Horseshoe Ring · 马蹄环取环

**4 份全程运动学预演；物理执行未完成。** 原版与三个 IK 种子都有全程动态视频。最新规划是 F1/F2/F3 × R/U/E 九个配对；九款有几何证据，新增六款外形尚缺机器人验证。

**五项门槛 Inspect**

判断基准：tutorial_solvable_v3 及三个 IK 种子；声明范围为运动学取环，完整链动力学尚未认证。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 归档有模板资产、initial_robot_state、完整 motion、几何证据和回放记录。 | 这些支持回放资料完整性，尚无归档输入驱动的新进程初态对照；shape / trace 的父目录依赖须统一记录。 | [证据 1](../../../runs/demo_metadata/horseshoe_ring/2026-09-16_aloha_full/archive_manifest.json) · [证据 2](../../../topogym/tasks/horseshoe_ring/family_space.py) |
| G2 任务语义和有效性明确 | 部分达到 | 取环目标、连接拓扑、连续几何通路与全程 IK 预演明确，形状证书核对初态拓扑和完全分离。 | 几何可行性不替代物理有效性；完整装配 settle、关键链环接触、力驱动抓取 / 换抓未闭环，针对性错误动作的阻挡也需统一入协议。 | [证据 1](../../../topogym/tasks/horseshoe_ring/shape_neighborhood.py) · [证据 2](../../../docs/develop/tasks/horseshoe_ring_family_space_zh.md) |
| G3 一个 family 有可用参数邻域 | 部分达到 | 旧耦合形状空间已有 seed17 的 12 个、seed29 的 30 个连续几何邻域样本，形状 / 椭圆度 / 链长联合收缩并生成完整物体路径。 | 只到几何层；新九配对的 6 个形状—抓点—机器人 IK 未认证，nine_pair_sampler_enabled=false。不能将 42 个几何样本算作机器人 family 邻域完成。 | [证据 1](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/samples_seed17/report.json) · [证据 2](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/samples_seed29/report.json) · [证据 3](../../../runs/environment-solvability/horseshoe_ring/family_space_plan_v1/report.json) |
| G4 小批量生成不需逐例修补 | 部分达到 | 几何层已有带 seed 的批量采样、邻域证书与代码指纹校验。 | sampler 使用批次 RNG 和洗牌；失败抛异常且未形成统一逐例拒绝清单；无完整机器人自动批处理与实例顺序无关证据。 | [证据 1](../../../topogym/tasks/horseshoe_ring/shape_sampler.py) · [证据 2](../../../topogym/tasks/horseshoe_ring/shape_neighborhood.py) |
| G5 参数与难度关系有证据 | 尚未验证 | F2/F3 的可见路线区别仍需强化。 | 先固定 family 身份与有效执行，再测形状、椭圆度、链长对应的容错和成功率。 | [证据 1](../../../docs/develop/tasks/horseshoe_ring_family_space_zh.md) |

**总结：** 几何邻域和批量样本已有实物路径证据，机器人与动力学层仍是主要缺口。

**现在可提炼：** 可先提炼几何层条件采样、扰动证书与缓存失效规则；机器人生成适配器保持未完成状态。

**下一步：** 把一个已认证形状样本重新配齐抓点、IK 与物理关键接触检查；优先解决椭圆转相位时的实际控制归属。

| Family | 动作 | 参数 |
| --- | --- | --- |
| F1 高位回环 | 左手抬高、绕回、再抓目标环 | 种子 compact_roll_planned；已有完整运动学预演 |
| F2 侧向大弧 | 侧面扫入，沿外侧通道换抓 | 种子 wide_roll_planned；仍需与 F3 拉开可见路线差异 |
| F3 分段回抓 | 先退让、调整腕姿，再接近抓取 | 种子 longer_regrasp_planned；仍需强化分段回抓特征 |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| F1_R | 经典轮廓 + 圆环 | 机器人运动学预演 |
| F1_U | 宽体 U 形；体量 ×1.18、椭圆比 1.05 | 几何证据；机器人配对待验收 |
| F1_E | 椭圆相位型；椭圆比 1.15 | 几何证据；机器人配对待验收 |
| F2_R | 经典轮廓 + 圆环 | 机器人运动学预演 |
| F2_U | 宽体 U 形；体量 ×1.18、椭圆比 1.05 | 几何证据；机器人配对待验收 |
| F2_E | 椭圆相位型；椭圆比 1.15 | 几何证据；机器人配对待验收 |
| F3_R | 经典轮廓 + 圆环 | 机器人运动学预演 |
| F3_U | 宽体 U 形；体量 ×1.18、椭圆比 1.05 | 几何证据；机器人配对待验收 |
| F3_E | 椭圆相位型；椭圆比 1.15 | 几何证据；机器人配对待验收 |

- 外观轴包括马蹄轮廓（宽 U、收腰／内凹的早期探索）、目标环椭圆度与相位、链长；必须联合采样并重算抓点和 IK。不能给椭圆环增加无人控制的转动。
- 每条视频约 69.08 秒，physics_steps=0；换抓基于运动学接触假设。完整播放不代表完整动力学执行。
- 先强化 F2/F3 的路线区别，再做 F1_U/F1_E，随后扩展四个配对。原版仍单列为 original 变体。

[九格与 IK 路线](../../../runs/environment-solvability/horseshoe_ring/family_space_plan_v1/index.html) · [四款全程动态对照](../../../runs/demo_metadata/horseshoe_ring/2026-09-17_trace_scene_variants_v1/index.html) · [耦合形状探索](../../../runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/index.html) · [最新空间规划](../../../docs/develop/tasks/horseshoe_ring_family_space_zh.md)

可播放 demo：

- [马蹄环 · ALOHA 双臂](../../../runs/demos/horseshoe_ring/original/2026-09-16_aloha_full_kinematic_detail.mp4)（69.1 s；运动学预演）；[多视角 / 证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-16_aloha_full/index.html)。
- [马蹄环变体 · compact_roll_planned](../../../runs/demos/horseshoe_ring/compact_roll_planned/2026-09-17_compact_roll_planned_v1_kinematic_detail.mp4)（69.1 s；运动学预演）；[多视角 / 证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-17_compact_roll_planned_v1/index.html)。
- [马蹄环变体 · wide_roll_planned](../../../runs/demos/horseshoe_ring/wide_roll_planned/2026-09-17_wide_roll_planned_v1_kinematic_detail.mp4)（69.1 s；运动学预演）；[多视角 / 证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-17_wide_roll_planned_v1/index.html)。
- [马蹄环变体 · longer_regrasp_planned](../../../runs/demos/horseshoe_ring/longer_regrasp_planned/2026-09-17_longer_regrasp_planned_v1_kinematic_detail.mp4)（69.1 s；运动学预演）；[多视角 / 证据](../../../runs/demo_metadata/horseshoe_ring/2026-09-17_longer_regrasp_planned_v1/index.html)。

### Interlocked Claws · 嵌合体脱困

**A0 有完整参考执行；另外 8 款为计划。** 规划三个动作与结构差异明显的 family：圆杆回钩、螺旋冠、正交双窗。当前只有 A0 原始网格完成参考全过程。

**五项门槛 Inspect**

判断基准：A0 原始网格与完整 12 阶段参考路径；预抓取、理想刚性辅助，落架释放静置。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 归档有原始几何、resolved config、实际状态、执行源码与可靠性报告。 | 尚未找到完整场景的新进程恢复对照；physical.py 仍从仓库 compose 默认配置，参考轨迹与碰撞分解需纳入显式依赖包。 | [证据 1](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/archive_manifest.json) · [证据 2](../../../topogym/tasks/interlocked_claws/physical.py) |
| G2 任务语义和有效性明确 | 部分达到 | A0 的完整参考执行、释放静置和步长对照通过；允许的理想辅助抓持已声明。 | generic_contact_robustness_passed=false，受阻接触对照仍失败。可提炼验证协议，但不能标记一般接触有效性已通过。 | [证据 1](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/reliability_report.json) |
| G3 一个 family 有可用参数邻域 | 尚未达到 | A/B/C 三类九个目标的形状与动作依赖已写成计划。 | A0 之外八款仍未建模 / 认证，尚无一个 family 的可用参数邻域。 | [证据 1](../../../runs/environment-solvability/interlocked_claws/family_space_plan_v1/plan.json) · [证据 2](../../../docs/develop/tasks/interlocked_claws_family_space_zh.md) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 现有 family_space 产出规划，不是通过资格验证的任务批量生成器。 | 需在 G2 接触问题和 G3 邻域可用后，补自动接受 / 拒绝、重采样及顺序验证。 | [证据 1](../../../topogym/tasks/interlocked_claws/family_space.py) |
| G5 参数与难度关系有证据 | 尚未验证 | 暂无变体执行统计。 | 螺旋或换轴的概念复杂度不足以建立参数—难度关系。 | [证据 1](../../../docs/develop/tasks/interlocked_claws_family_space_zh.md) |

**总结：** 有完整参考 demo，但尚未具备可放心扩展的接触有效性和参数族。

**现在可提炼：** 先提炼原资产 / 参考路径 Spec、参考执行与通用接触验收的分层协议，以及受阻失败类型。

**下一步：** 修复并复验 A0 的受阻接触，再建立 A family 的一个小形变邻域。

| Family | 动作 | 参数 |
| --- | --- | --- |
| A 空间互绕 | 保留原参考的通过顺序，改变绕行与出平面避让 | A0 原版；A1 横跨 ×1.25、深度 ×0.85；A2 宽 ×0.85、高 ×1.25、深 ×1.20 |
| B 螺旋推进 | 相对旋转 100°并同步推进，再侧退 | B0 40 mm；B1 矮宽扇翼 32 mm；B2 细高长冠 50 mm |
| C 换轴翻转 | 内推 → 第一轴翻转 → 窗间转移 → 第二轴翻转 → 退出 | C0 标准双窗；C1 横移约 56 mm（基型 40 mm）；C2 增加腔深与升降 |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| A0 | 经典回钩 | 完整参考物理执行；接触鲁棒性未通过 |
| A1 | 宽展浅钩 | 候选设计；未建模／未验证 |
| A2 | 高窄深钩 | 候选设计；未建模／未验证 |
| B0 | 标准螺旋冠 | 候选设计；未建模／未验证 |
| B1 | 矮宽扇翼 | 候选设计；未建模／未验证 |
| B2 | 细高长冠 | 候选设计；未建模／未验证 |
| C0 | 标准双窗 | 候选设计；未建模／未验证 |
| C1 | 横向宽跨 | 候选设计；未建模／未验证 |
| C2 | 高阶深腔 | 候选设计；未建模／未验证 |

- A0 的 158.6 秒录像覆盖 12 阶段、落架释放和自由静置；两种时间步完整参考执行通过，使用预抓取与理想刚性辅助抓持。
- generic_contact_robustness_passed=false：受阻接触对照仍有失败。完整参考执行成立，但不能据此宣称通用接触鲁棒性或纯摩擦抓取通过。
- B 的冠高、层间距和推进量，以及 C 的窗偏移、腔深和转移行程需联动；所有尺寸目前是设计目标。先验收三个基型，再扩展六款外观及随机生成。

[九款规划页](../../../runs/environment-solvability/interlocked_claws/family_space_plan_v1/index.html) · [完整空间规划](../../../docs/develop/tasks/interlocked_claws_family_space_zh.md) · [参考执行可靠性报告](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/reliability_report.json)

可播放 demo：

- [Claw · 原视频完整动作与物理验收](../../../runs/demos/interlocked_claws/2026-09-17_reference_full_v1_detail.mp4)（158.6 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/index.html)。

### Lock Picking · 三锁片钥匙机构

**9 款已有几何 + IK；代表视频尚缺。** 当前版本固定三齿，用 1/2/3 次必要回退作为宏观 family。S/M/L 仅调整可见几何，盘距保持或扩大，旧小间距方案已停用。

**五项门槛 Inspect**

判断基准：150 mm 盘距的三齿基准成功执行；F1/F2/F3 × S/M/L 的 v2 九款另有几何 / 解锁 IK 证据。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 基准有 config、layout、frames 和 success 报告；v2 各代表保存检查配置、资产与 IK。 | family_space 直接取 SOURCE 实验目录中的 config/layout/frames；尚缺独立恢复包、新进程初态对照和依赖缺失时报错的验收。 | [证据 1](../../../topogym/tasks/lock_picking/family_space.py) · [证据 2](../../../runs/environment-solvability/lock_picking/spaced_initial/result.json) |
| G2 任务语义和有效性明确 | 达到（限定范围） | 基准 evaluator 分离终点、静止、几何合法、力 / 接触与松手条件；成功报告均通过。机构证书给出正确孔道和必要回退下界，可识别省略回退的无效动作。 | 证书限同轴准静态模型；新九款 robot_scene_collision_verified 与 physical_execution_verified 仍为 false。单视角缺口属于归档层，不应据此否认基准语义已明确。 | [证据 1](../../../topogym/tasks/lock_picking/evaluator.py) · [证据 2](../../../topogym/tasks/lock_picking/certificate.py) · [证据 3](../../../runs/environment-solvability/lock_picking/spaced_initial/result.json) · [证据 4](../../../runs/environment-solvability/lock_picking/family_space_v2/summary.json) |
| G3 一个 family 有可用参数邻域 | 部分达到 | v2 固定三齿，盘距≥150 mm；盘径 / 盘距 / 齿距 / 握柄与动作联动，九代表及 26 个有效边界组合有同轴几何、回退下界和 IK 检查。 | 长钥匙可达余量很小；完整抓起 / 释放、机器人场景碰撞和物理执行未验收。不能把几何 / IK 候选范围当成机器人可用邻域。 | [证据 1](../../../docs/develop/tasks/lock_picking_family_space_zh.md) · [证据 2](../../../runs/environment-solvability/lock_picking/family_space_v2/summary.json) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 已有固定九点和边界组合生成 / 检查；summary 明示 random_physical_dataset_generator_implemented=false。 | 尚缺适配不同回退次数的完整控制、实例 seed、自动物理接受 / 拒绝与顺序无关批次。 | [证据 1](../../../runs/environment-solvability/lock_picking/family_space_v2/summary.json) |
| G5 参数与难度关系有证据 | 部分达到 | F1/F2/F3 的槽位与限位对应 1/2/3 次必要回退；这是参数→最少关键动作数的理论证据。 | 仅在限定动作模型内成立，尚无统一控制器的成功率 / 重试 / 容错测量。可作为结构难度特征，不能直接宣称 F3 在所有设置都更难。 | [证据 1](../../../topogym/tasks/lock_picking/certificate.py) · [证据 2](../../../docs/develop/tasks/lock_picking_family_space_zh.md) |

**总结：** 机构语义与理论动作复杂度最清楚；可用机器人参数邻域和自动批处理仍需完成。

**现在可提炼：** 提炼成功 / 有效性 evaluator、回退必要性证书，以及固定三齿、可视盘距的条件参数定义；难度先记录“必要回退次数”。

**下一步：** 先补 F1_M/F2_M/F3_M 的全机器人碰撞与物理执行，保留 p≥150 mm，再做批量和难度标定。

| Family | 动作 | 参数 |
| --- | --- | --- |
| F1 一次回退 | 回退一次，复位 30°后再插入 | D1 两槽：−30°、0°；D1 限位 ±15° |
| F2 两次回退 | 依次复位 28°、32° | D1 三槽：−60°、−32°、0°；限位 ±16° |
| F3 三次回退 | 三次各复位 24° | D1 四槽：−72°、−48°、−24°、0°；限位 ±12° |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| F1_S | 小盘通视：盘径 130 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F1_M | 标准基型：盘径 160 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F1_L | 大盘加宽：盘径 190 mm / 盘距 180 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F2_S | 小盘通视：盘径 130 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F2_M | 标准基型：盘径 160 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F2_L | 大盘加宽：盘径 190 mm / 盘距 180 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F3_S | 小盘通视：盘径 130 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F3_M | 标准基型：盘径 160 mm / 盘距 150 mm | 几何与解锁 IK 已检查；尚无代表录像 |
| F3_L | 大盘加宽：盘径 190 mm / 盘距 180 mm | 几何与解锁 IK 已检查；尚无代表录像 |

- 联合范围：R=65–95 mm，max(150,150×R/80)≤p≤180 mm；钥匙齿间距=p、握柄偏移=3p+45 mm、全插入行程=4p。三齿数量轴已撤回。
- 九款新实例的机器人场景碰撞、抓起／松手与接触动力学尚未验收；必要回退下界限定于声明的同轴准静态模型。
- 150 mm 盘距基准有一次完整成功执行，但仅 agentview 一路全程录像；既非九款代表的录像，也未满足三视角归档。优先补 F1_M/F2_M/F3_M。

[v2 九宫格](../../../runs/environment-solvability/lock_picking/family_space_v2/index.html) · [最新规则](../../../docs/develop/tasks/lock_picking_family_space_zh.md) · [宽间距基准 demo](../../../runs/environment-solvability/lock_picking/spaced_initial/index.html)

可播放 demo：

- [宽间距基准单视角完整成功录像](../../../runs/environment-solvability/lock_picking/spaced_initial/attempt06/agentview.mp4): 尚缺三视角正式归档，不属于九款新代表。

### Fiber Bundling · 多芯线穿环收束

**4 / 12 实例已归档；其余处理中。** 变体只控制线数 N 与环内半径 R，形成稀疏、标准、密集三类。它们是几何类别，尚未证明对应三种不同 IK 机制或难度。

**五项门槛 Inspect**

判断基准：新细铜杆 4 芯 / R=12.8、13.5、15.0 mm 的已验收子集；旧支柱 8 芯严格线形对照失败单列。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 每实例保存完整 config、动态电缆 / 环资产、plan、控制命令、执行源码与两档结果；生成参数含版本与 shape_seed。 | 参数重现已检查，但尚无从归档单独加载、核对固定终端、根部约束与全部线形的完整新进程 reset 对照。 | [证据 1](../../../runs/demo_metadata/fiber_bundling/2026-09-17_sparse_04_r13p5mm_hybrid_01/archive_manifest.json) · [证据 2](../../../topogym/tasks/fiber_bundling/variants.py) |
| G2 任务语义和有效性明确 | 达到（限定范围） | 成功是全部细线及前端护套通过，终端 / 环固定，只抓粗护套；禁碰检查有细线触碰失败与粗线不误判对照。新 4 芯三孔径完成加载 / 卸载、全程和严格步长线形检查。 | 只认证这个新支柱已验收子集和辅助夹持协议；旧 8 芯严格线形对照失败，材料也只是保留形变的任务近似。 | [证据 1](../../../docs/develop/tasks/fiber_bundling_density_radius_zh.md) · [证据 2](../../../topogym/tasks/fiber_bundling/contact_guard.py) · [证据 3](../../../runs/demo_metadata/fiber_bundling/2026-09-17_sparse_04_r13p5mm_hybrid_01/timestep_validation.json) |
| G3 一个 family 有可用参数邻域 | 达到（限定范围） | N / R 参数、根间距和实际孔径依赖明确；39 个重置几何点通过，新 4 芯三孔径可由同一整束反馈控制器完成，无固定逐根顺序。 | 可用范围限定为已验证 4 芯孔径子集及逐实例筛选机制；标准 / 密集类和整个连续孔径区间不能自动继承。 | [证据 1](../../../configs/task_variants/fiber_bundling_density_v1.yaml) · [证据 2](../../../topogym/tasks/fiber_bundling/variants.py) · [证据 3](../../../docs/develop/tasks/fiber_bundling_density_radius_zh.md) |
| G4 小批量生成不需逐例修补 | 部分达到 | 已有具名 RNG 流、生成检查、逐实例完整运行 / 复核 / 归档和 workflow 失败记录。本轮 6 个 seed 在两新进程中反向排序并加入无关全局 RNG 调用，参数仍一致。 | 只证明参数层顺序无关；仍需固定数值精度 / 重试策略后，验证一组未挑选 seed 的完整资产与物理接受 / 拒绝批次。代表实验中的精度调整不能算免修补生成已达标。 | [证据 1](../../../topogym/tasks/fiber_bundling/variants.py) · [证据 2](../../../topogym/tasks/fiber_bundling/variant_demo.py) · [证据 3](inspect_probes.json) |
| G5 参数与难度关系有证据 | 尚未验证 | 已有完成时长与执行诊断，三类目前只是线数 / 根部间距的几何类别。 | 需固定材料、精度、控制器与初态扰动，交叉比较 N / R 的成功率、接触 / 重试与操作成本；不能将更密或更紧直接标为更难。 | [证据 1](../../../docs/develop/tasks/fiber_bundling_density_radius_zh.md) |

**总结：** 稀疏子集已有可用生成基础；顺序无关性目前仅在参数层复测通过。

**现在可提炼：** 提炼 N / R 的条件采样、具名 RNG、接触违规与任务成功分离的验证协议；逐实例 runner 可作为批处理候选。

**下一步：** 冻结精度选择和失败重试规则，运行同一组 seed 的单例 / 正序 / 逆序完整小批次，并比对资产、初态与接受结果。

| Family | 动作 | 参数 |
| --- | --- | --- |
| 稀疏 sparse | N∈{4,5,6}，代表为 4 芯 | 每类均使用 R=12.8–15.0 mm；不绑定线数和孔径 |
| 标准 standard | N∈{7,8,9,10}，代表为 8 芯 | 固定单线半径 1.2 mm、护套半径 12 mm、根部圆半径 8 mm |
| 密集 dense | N∈{11,…,16}，代表为 16 芯 | 根部最小间隙与实际碰撞孔径需检查；更多线意味着更多接触对 |

| 代表 | 外形 | 状态 |
| --- | --- | --- |
| N4_R12.8 | 4 芯 · 内半径 12.8 mm · 细铜杆支架 | 完整 demo；严格时间步线形对照通过 |
| N4_R13.5 | 4 芯 · 内半径 13.5 mm · 细铜杆支架 | 完整 demo；严格时间步线形对照通过 |
| N4_R15.0 | 4 芯 · 内半径 15.0 mm · 细铜杆支架 | 完整 demo；严格时间步线形对照通过 |
| N8_R12.8 | 8 芯 · 内半径 12.8 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |
| N8_R13.5 | 8 芯 · 内半径 13.5 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |
| N8_R15.0 | 8 芯 · 内半径 15.0 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |
| N16_R12.8 | 16 芯 · 内半径 12.8 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |
| N16_R13.5 | 16 芯 · 内半径 13.5 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |
| N16_R15.0 | 16 芯 · 内半径 15.0 mm · 细铜杆支架 | 几何已生成；完整执行／复核／归档处理中 |

- 已归档旧支柱 8 芯 / R13.5：视频约 176.95 秒，两种时间步均成功，严格全程线形对照未通过（最大差约 4.93 mm）。
- 已归档细铜杆 4 芯 / R12.8、R13.5、R15.0 三款：各 116.7 秒，严格线形对照均通过。新支柱直径 5 mm，不能继承旧矩形支柱的物理证据。
- 九个正式几何代表之外，还规划 5 芯、6 芯 / R13.5 作为过渡；连同旧 8 芯共 12 个实例。5 芯两次运行已通过、待归档；6 芯和新 8 芯 / R13.5 主运行成功，仍待独立复核与归档。
- 只抓粗护套，接触后辅助夹持，最终全部细线与前端护套穿环，末态仍夹持；没有强制逐根顺序。材料为可保留形变的被动关节链近似，并非已标定的真实铜线本构。

[两参数九格示意](../../../runs/environment_bootstrap/fiber_bundling/2026-09-17_density_radius_v1/density_radius_grid.png) · [变体与材料定义](../../../docs/develop/tasks/fiber_bundling_density_radius_zh.md) · [12 个实例的执行清单](../../../runs/environment-solvability/fiber_bundling/variant_demos_v1/README.md) · [逐实例状态](../../../runs/environment-solvability/fiber_bundling/variant_demos_v1/status.json)

可播放 demo：

- [光纤收束 · 固定终端完整 IK 执行](../../../runs/demos/fiber_bundling/2026-09-17_anchored_ik_hybrid_v1_front_oblique.mp4)（176.9 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/fiber_bundling/2026-09-17_anchored_ik_hybrid_v1/archive_manifest.json)。
- [光纤收束 · 4 芯 · 环内半径 13.5 mm](../../../runs/demos/fiber_bundling/2026-09-17_sparse_04_r13p5mm_hybrid_01_front_oblique.mp4)（116.7 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/fiber_bundling/2026-09-17_sparse_04_r13p5mm_hybrid_01/archive_manifest.json)。
- [光纤收束 · 4 芯 · 环内半径 12.8 mm](../../../runs/demos/fiber_bundling/2026-09-17_sparse_04_r12p8mm_hybrid_01_front_oblique.mp4)（116.7 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/fiber_bundling/2026-09-17_sparse_04_r12p8mm_hybrid_01/archive_manifest.json)。
- [光纤收束 · 4 芯 · 环内半径 15 mm](../../../runs/demos/fiber_bundling/2026-09-17_sparse_04_r15p0mm_hybrid_01_front_oblique.mp4)（116.7 s；辅助抓持物理执行）；[多视角 / 证据](../../../runs/demo_metadata/fiber_bundling/2026-09-17_sparse_04_r15p0mm_hybrid_01/archive_manifest.json)。

## 2. 无变体讨论，但已有完整 demo

本次为空。已有完整 demo 的任务今天均有变体讨论，统一放在第一类，不重复计数。

## 3. 尚无完整成功 demo，以及物理 / 归档缺口

- **Rope Threading · 绳穿三环：尚无完整成功 demo。** 场景及单环穿入／滑动／释放试验已建立；半时间步初始接触线形 RMS 差约 7.76 mm，超过 2 mm 门槛。其后显存不足中断，仍需先解决步长敏感性，再补三环、换手与回退全过程。 [证据](../../../runs/environment-solvability/rope_threading/physics_v5/index.html)

**五项门槛 Inspect**

判断基准：三固定环参考场景及当前 physics_v5 的绳 / 单环接触试验。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 有参考几何、场景入口、资产准备、物理 case 配置和诊断轨迹。 | 尚缺统一 Spec / 依赖清单及完整三环初态在新进程恢复的对照；模型输入与参考动作版本需一起冻结。 | [证据 1](../../../topogym/tasks/rope_threading/prepare_assets.py) · [证据 2](../../../topogym/tasks/rope_threading/scene.py) · [证据 3](../../../runs/environment-solvability/rope_threading/physics_v5/cases.json) |
| G2 任务语义和有效性明确 | 部分达到 | 允许的抓持与物理检查已定义，单环穿入 / 滑动 / 释放有局部证据，初始穿插已修复。 | qualification.passed=false、full_demo=false；步长对照失败且完整三环正确路径尚未认证，不能将局部试验当作基准任务有效性通过。 | [证据 1](../../../runs/environment-solvability/rope_threading/physics_v5/qualification.json) · [证据 2](../../../topogym/tasks/rope_threading/qualification.py) |
| G3 一个 family 有可用参数邻域 | 尚未达到 | 目前主要在建立固定参考基准。 | 尚无经认证的同 family 参数邻域，以及随参数改变的完整抓点 / 穿环 / 换手路径。 | [证据 1](../../../docs/develop/tasks/rope_threading_zh.md) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 已有物理 case 调度和失败结果记录。 | 物理测试 suite 不等于任务实例生成批处理；还缺可用邻域、接受 / 拒绝闭环和 seed 顺序测试。 | [证据 1](../../../topogym/tasks/rope_threading/physics_suite.py) |
| G5 参数与难度关系有证据 | 尚未验证 | 未见有效任务变体的难度实验。 | 先认证三环基准，再测环姿态、净空和换手需求；数值失败不能作为任务更难的证据。 | [证据 1](../../../runs/environment-solvability/rope_threading/physics_v5/qualification.json) |

**总结：** 先收敛基准有效性；暂不抽象为通用任务生成器。

**现在可提炼：** 可以先提炼参考资产 Spec、局部物理验证协议和数值 / 接触 / 任务失败的分类。

**下一步：** 解决步长敏感性并完成三环基准的正确路径与针对性负例，再进入参数生成。

- **Knot Untying · 解绳结：完整成功录像仍在录制／验收。** 单手抓持、抬升、释放已通过；51 秒抽绳未解开，63 秒分段抽绳抽出自由端但留有回环。最新 v8 双手展开录像仍在执行，未形成完成报告及正式归档；此前 P3 网格对照也未通过。过程片段不能算完整成功解结 demo。 [证据](../../../docs/develop/tasks/knot_untying_recording_attempt_zh.md)

**五项门槛 Inspect**

判断基准：FEM + IPC 开放单结、显式直绳参考态；现有抓持 / 抽绳试验与 v8 展开录制。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 运行目录保存 resolved config、assets、mesh.npz（初始节点 / 参考量）、validation_spec 与 implementation 快照。 | 还未形成独立恢复验收；需核对材料参考态、当前节点、机器人—IPC 对齐、约束及指定软件版本，而不只是恢复可见绳形。 | [证据 1](../../../topogym/tasks/knot_untying/physics_probe.py) · [证据 2](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/spread_recording_v2/validation_spec.json) |
| G2 任务语义和有效性明确 | 部分达到 | 已明示接触后辅助抓持、实际释放与静置检查；18 秒抓持试验通过，51 秒 / 63 秒尝试保留了明确未解开结论。 | P3 网格收敛仍未通过，完整成功解结和最终自由静置验收尚未闭环；投影交叉清零本身不能替代完整成功证据。 | [证据 1](../../../docs/develop/tasks/knot_untying_recording_attempt_zh.md) · [证据 2](../../../runs/environment-stability/knot_untying/trefoil_v1_eps1mm/result.json) |
| G3 一个 family 有可用参数邻域 | 尚未达到 | 当前仍围绕一个固定结型和初态调试。 | 未建立结圈、尾长等参数改变后同步准备合法初态、抓点与完整解法的可用邻域。 | [证据 1](../../../docs/develop/tasks/knot_untying_physics_demo_plan_zh.md) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 已有实验 suite 和过程快照，可记录失败。 | 这些是求解 / 数值试验，不是无逐例修补的可解实例批量生成。 | [证据 1](../../../topogym/tasks/knot_untying/physics_suite.py) |
| G5 参数与难度关系有证据 | 尚未验证 | 暂无通过基准验收后的参数难度实验。 | 先区分物理分辨率不足和策略失败，再比较松紧、尾长等参数；仿真耗时不是解题难度。 | [证据 1](../../../docs/develop/tasks/knot_untying_physics_demo_plan_zh.md) |

**总结：** 底层诊断有复用价值，任务有效性和完整基准仍待完成。

**现在可提炼：** 先提炼柔性体初态 / 参考态 Spec、求解器和接触诊断、失败分类，完整成功判据仍需固化。

**下一步：** 完成解结—释放—静置的整次验收，并解决或明确限定网格收敛问题，再扩参数。

- **3D Buzz Wire · 立体电流棒：无完整机器人 demo · 补充盘点。** 今日未发现独立工程会话。现存材料为约 17 秒的平面局部接触试验；真正空间路径与机器人全过程尚缺。此项作为项目遗漏检查列入，不算今日新增工作。 [证据](../../../runs/environment_bootstrap/buzz_wire_3d/bend_contact/report.json)

**五项门槛 Inspect**

判断基准：现有 planar_bend_fixture_probe；不是完整三维机器人电流棒任务。

| 门槛 | 状态 | 已有证据 | 缺口 / 范围 | 来源 |
| --- | --- | --- | --- | --- |
| G1 一个基准实例可独立恢复 | 部分达到 | 局部 probe 的 report 记录几何、配置、Genesis 版本和实际物理步数，入口可定位。 | 缺完整三维任务的实例 Spec、资产 / 支架 / 机器人初态与保存加载验收；局部 probe 重跑不能代替完整基准恢复。 | [证据 1](../../../topogym/tasks/buzz_wire_3d/probe.py) · [证据 2](../../../runs/environment_bootstrap/buzz_wire_3d/bend_contact/report.json) |
| G2 任务语义和有效性明确 | 部分达到 | 17 秒局部试验的居中通行、故意碰壁、受阻和返回中心通过；无运行中位姿改写。 | full_task_deployed=false；完整空间路径、机器人抓持、任务成功 / 接触事件及 settle 协议未闭环。 | [证据 1](../../../runs/environment_bootstrap/buzz_wire_3d/bend_contact/report.json) |
| G3 一个 family 有可用参数邻域 | 尚未达到 | 有轨道半径 / 曲率等早期参数提案。 | 尚无含机器人与环杆完整扫掠的可用三维参数邻域。 | [证据 1](../../../docs/develop/tasks/ten_task_environment_deployment_plan_zh.md) |
| G4 小批量生成不需逐例修补 | 尚未达到 | 只有局部试验入口。 | 尚无任务生成、完整验证、拒绝 / 重采样和 seed 契约。 | [证据 1](../../../topogym/tasks/buzz_wire_3d/probe.py) |
| G5 参数与难度关系有证据 | 尚未验证 | 局部触壁检测不构成难度标定。 | 需完整有效任务后，测曲率、净空与出平面幅度对同一控制器的表现。 | [证据 1](../../../runs/environment_bootstrap/buzz_wire_3d/bend_contact/report.json) |

**总结：** 局部“应通 / 应阻”已有证据，任务层仍处于基准建设。

**现在可提炼：** 可提炼局部通行 / 受阻接触校准协议与参数记录格式；完整任务适配器先不定型。

**下一步：** 建立一个空间轨道的完整机器人基准，并明确轻触事件与到达目标的判据。

- **马蹄环 · 物理执行缺口：有全程预演；无完整物理 demo。** 原版和三个种子均为 physics_steps=0 的运动学预演；完整力驱动抓取、链动力学及换抓仍待验证。九款规划见第一类。 [证据](index.html#horseshoe_ring)

- **开锁 · 多视角归档缺口：有成功全程单视角；正式归档未齐。** 宽间距基准确有成功全程 agentview 录像，不应记成完全没有 demo；但缺三路同步完整视角，九款新代表尚无录像。变体计划见第一类。 [证据](index.html#lock_picking)

## 来源与判断口径

最新原始报告、匹配实例归档清单和实际视频优先于早期总结。旧实例成功不继承到新几何；图示、初态环绕、未结束录像不当作完整 demo；运动学预演与辅助抓持物理执行分别标注。

| 主题 | Session ID | 说明 |
| --- | --- | --- |
| 刺球基线 → Keyhole 三种逆向变体 | 01a0aaf4-1f21-72b0-8095-149500af6ba0 | 含今日工程消息 |
| 光纤固定终端完整执行 | 01a0ab7b-9927-7ea2-b8be-ca56f302a1fd | 含今日工程消息 |
| 马蹄环 IK 变体与九格规划 | 01a0ab7f-af38-7e82-b8f1-d62c39aa8546 | 含今日工程消息 |
| Coil 基线完整执行 | 01a0abcc-e94a-7963-baa2-3d82d49d9171 | 含今日工程消息 |
| Keyhole 当前初态求解 | 01a0aced-bea6-79c0-9a0e-dc760999b6ad | 含今日工程消息 |
| Claws 复现、参考执行与三类结构 | 01a0b06c-446f-76e1-a57d-0ed268dcf600 | 含今日工程消息 |
| 绳穿三环物理可靠性 | 01a0b06c-4ba0-7322-997d-1c94ba15e485 | 含今日工程消息 |
| Coil 三种种子与单参数外观 | 01a0abcc-e94a-7963-baa2-3d82d49d9171 | 续接记录，按任务合并 |
| Keyhole 暂停候选 → 刺球三家族 | 01a0aced-bea6-79c0-9a0e-dc760999b6ad | 续接记录，按任务合并 |
| 开锁 1/2/3 回退与新版 S/M/L | 01a0b090-b34a-7502-baf6-ae12a4427960 | 含今日工程消息 |
| Coil 九个可见代表 | 01a0abcc-e94a-7963-baa2-3d82d49d9171 | 续接记录，按任务合并 |
| Keyhole 九款与随机生成；刺球 wood／状态核对 | 01a0aaf4-1f21-72b0-8095-149500af6ba0 | 续接记录，按任务合并 |
| 光纤线密度、环半径与批次 demo | 01a0ab7b-9927-7ea2-b8be-ca56f302a1fd | 续接记录，按任务合并 |
| 解绳结物理修复与完整录制 | 01a0abcc-dd65-76a0-b792-fe7f503c66ee | 跨日会话，今日持续执行；无新用户消息 |

本轮只生成报告，不改写归档、启动仿真或把正在运行的任务提前标记完成。HTML 使用相对仓库链接，视频未复制到报告目录。
