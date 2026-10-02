# Cast Keyhole：very_easy / easier 场景与工程计划

日期：2026-10-02。状态：两套场景已实现，当前 v4 使用原三档的标准尺寸和初始摆位，无额外支撑；完整参考策略需适配恢复后的初态，机械臂求解及 Harbor 验收待验证。新增 `cast_keyhole_very_easy` 和 `cast_keyhole_easier`，保留现有 easy / medium / hard。

当前修订：两片均统一为 **207 × 78 × 9 mm**，灰色支撑已移除，摆位与 easy / medium / hard 一致，见[修订计划与实施结果](cast_keyhole_very_easy_easier_revision_plan_zh.md)。下文第 5 节的尺寸、支撑和短测结果保留为第一版历史；当前证据见[摆位修正报告](../../runs/test_results/cast_keyhole_original_layout_20261002_01/README.md)，旧交叉直立版本的静置／接近通过结论不沿用。

## 1. 基于你的方案，场景准备怎么做

总体保留 Cast Keyhole 的金、银两件结构和取出银色件的目标，把主要难度放在两件相对运动时的通道形状上。下面的线表示**通道的概念中心线**，不是完整零件轮廓，也不是最终机械臂轨迹；具体尺寸、摆放和抓取位置在建模时决定。

### very_easy：十字通道，直道可通过

```text
                短支槽
                   │
装配起点 ──────────┼────────── 脱离方向
                   │
                短支槽
```

采用一条宽松的主直道，中间带短的横向支槽，形成十字形。支槽作为轻微干扰，可以是浅的盲端；主通路不需要走进去再退出来。

预期操作是：机械臂接近并抓住零件，找到正确的相对方向，沿主通道取出银色件，再搬到目标区。允许初始对准和少量纠偏，抓住并对准后应能以基本不变的相对姿态通过，不需要原任务的复杂换抓或反复转向。

这里的“微小干扰”优先来自短支槽和轻微轮廓变化，避免把直道做成精密卡缝。需要让 agent 分辨主通路，同时保留足够的操作余量。

### easier：两处错位，中途改变运动方向

将你的示意理解为主通道中间有一段偏移：先从原来的直道错开，再回到出口方向。

```text
装配起点 ────┐              ┌──── 脱离方向
             │              │
             └──────────────┘
```

预期操作是：沿第一段推进，到错位处调整方向，走过中间段，再次调整并对准出口。两处错位应真实阻止“一直直拉到底”，但通路清楚、转弯处宽松，不做成长迷宫。

“两次错开”指两处需要重新对齐的区域，不强行限定为两个直角或两次转腕。**改变运动方向不一定等于旋转物体**：第一版先实现中途横移、转向和重新对齐；若零件形状自然需要小幅姿态调整，可以保留，不额外加入大幅翻转要求。

两档尽量共用外轮廓、抓取部位、机器人和初始摆放，主要区别是通道是否需要中途绕行。预期关系为 `very_easy < easier < easy`；具体偏移量、槽宽、转角和支槽长度由实际建模与机器人可达性决定。

## 2. 如何对应到现有 Cast Keyhole

当前实现是**开口金色叉件 + 带封闭孔的银色件**，使用 ALOHA 双臂。现有三档从独立 `geometry.json` 读取两件的平面轮廓，再生成有厚度的视觉网格和分块碰撞体，已经适合新增两套几何资源。

建议优先调整金色开口件的内缘，形成直道／错位通路；银色件的孔和穿行部位若仍带来旧解谜负担，也可以同步简化。保留可抓的外部区域，尽量让一臂稳住金色件、另一臂操作银色件时，一次抓牢就能走完主要取出过程。最终初态应稳定且便于从 home 接近，不继承旧策略中不必要的换抓过程。

需要一起看两件的完整形状：把槽画成十字或折线，不代表银色件就能沿中心线通过。建模时检查整个零件、手指及掌部的运动空间，同时确认没有从板外、其他开口或大幅倾斜直接绕过 `easier` 错位段的明显捷径。优先保留金色件连成一体、银色件有一个封闭孔的结构，以复用现有几何检查。

成功条件继续使用当前 Task：**整件银色零件进入固定目标区，金色件留在系统侧，满足现有速度要求并保持 0.5 s，允许继续抓持。** 通道形状负责产生操作差异，评分器不要求 agent 经过指定路点或完成指定次数的转腕。

源码依据：[Task 与抓持配置](../../topogym/tasks/cast_keyhole/common.py)、[几何生成器](../../topogym/assets/geometry/cast_keyhole.py)、[当前任务说明](../develop/tasks/cast_keyhole_zh.md)。

## 3. 预计新增／修改哪些文件

### 场景实现与注册

| 动作 | 文件／位置 | 预计内容 |
| --- | --- | --- |
| 新增 | `topogym/tasks/cast_keyhole/cast_keyhole_very_easy.py` | 声明新入口、独立 family／revision、参数和 very_easy 几何资源。 |
| 新增 | `topogym/tasks/cast_keyhole/cast_keyhole_easier.py` | 同上，指向 easier 几何资源。 |
| 首版新增，修订时移除 | `topogym/tasks/cast_keyhole/simplified.py` | 原支撑基类已删除，两档直接继承 `CastKeyholeTask`。 |
| 新增 | `topogym/assets/geometry/cast_keyhole_simplified.py` | 两类通道的可复现构造逻辑，集中管理槽宽、短支槽、错位量等设计参数；输出现有生成器可读取的轮廓记录。 |
| 新增 | `topogym/assets/resources/variations/cast_keyhole/very_easy/geometry.json` | 冻结十字通道的两件轮廓、厚度、比例和设计参数。 |
| 新增 | `topogym/assets/resources/variations/cast_keyhole/easier/geometry.json` | 冻结两处错位通道的对应几何。 |
| 修改 | `topogym/assets/resources/catalog.json` | 登记两个新资源及 SHA-256。 |
| 修改 | `topogym/config/variation_records.py` | 注册两个具名变体，保持原三档和 `base` 映射。 |
| 修改 | `topogym/tasks/cast_keyhole/common.py` | 让新场景的抓持区域匹配实际几何；必要时增加仅供新变体使用的初始摆放参数。现有 `build_assets()` 已能根据资源选择几何，优先复用。 |
| 按需修改 | `topogym/assets/geometry/cast_keyhole.py` | 复用 `generate_variant_assets()`、`polygon_slabs()`、`extrude_slabs()` 和 URDF 导出。若新初态需要不同的两件相对变换，增加可选字段并保留旧默认值。 |

两处现有假设需要特别处理：`generate_variant_assets()` 目前沿用基础模板的两件装配变换；`recommended_grasp_assist()` 使用旧零件上的固定抓持点。新形状不能只换网格而默认这些坐标仍有效。模型尺寸、实际抓持区域和 Task 声明要一致。

新素材放包内 `resources/variations/`，不依赖根目录 `assets/tasks/` 或历史 `runs/`。现有 F1／F2／F3 的几何文件保持原样；碰撞生成继续保留槽和孔，不能用整件凸包把通道填平。

### 参考执行与验证

| 动作 | 文件／位置 | 预计内容 |
| --- | --- | --- |
| 新增 | `topogym/planning/cast_keyhole/simplified_policy.py` | 为新两档提供接近、抓取、直行／错位取出、目标区搬运的参考策略；复用公共执行能力。 |
| 修改 | `scripts/oracle_runners/run_cast_keyhole_policy.py` | 接受 `very_easy`／`easier` 并分派到新策略；按所选 Task 构建几何，使用与运行任务一致的抓持配置。 |
| 按需复用／小改 | `topogym/planning/cast_keyhole/policy.py`、`kinematics.py` | 复用坐标转换、IK、碰撞预检和搬运辅助函数；把依赖旧抓点或旧形状的部分参数化。 |
| 新增 | `ci_checks/test-cast-keyhole-simplifications.py` | 检查入口、资源、几何通路及旧三档兼容；真实机器人与 Harbor 结果另留运行证据。 |
| 新增 | `scripts/check_cast_keyhole_simplifications.py` | 冻结源码、实际运行短测，记录 CPU／内存、零件漂移、初始帧与共享 Nyx 录像。 |
| 更新 | `docs/develop/tasks/cast_keyhole_zh.md` | 实施后补充两个正式入口及实际验证状态。 |

原 runner 的选项和 policy 的 `FAMILIES` 只支持 easy／medium／hard，并绑定 F1／F2／F3 参考路径；本次 runner 已为新两档增加独立策略分派，原路径保留。新变体使用自己的策略／参考路径，参考解法留在 planning 范围，不放进任务运行素材中；旧 `qualification.py` 的成功证据不转移给新几何。

## 4. 接入边界与实施顺序

首阶段只接入两个独立具名变体，可先放在现有 `experimental` 池，保持当前 `seeded` 的 easy／medium／hard 含义。先不扩展全项目五档采样，也不修改其他成员负责的三个任务。

Harbor 包继续由 `scripts/topogym_mk_task.py` 和 `scripts/topogym_mk_limited.py` 生成；根目录 `tasks/` 是生成产物，不作为几何编辑入口。进入验收时使用包含新源码和素材的镜像，重新冻结实例、生成双模式包。首版沿用默认 `terminal_contract_version=1`，复用共享控制、录制和评分，具体要求见[修复后场景开发约定](post_fix_scene_variant_guidelines_zh.md)。

建议按以下顺序推进：

1. **先做两套几何候选。** 看清十字直道与两处错位的区别，检查实体连通、真实孔槽、合法初态和完整零件通行空间。
2. **先跑通 very_easy，再调 easier。** 从 home 完成抓取、取出和搬运；very_easy 应能主要直行，easier 的直拉应受阻，而调整方向后能够通过。几何预检和真实机器人结果分别记录。
3. **检查共用代码影响。** 原三档的资源、入口和默认行为保持一致；若修改了共用几何、抓持或执行代码，按影响范围补回归。
4. **完成新包验收。** 先用短动作验证初始化、执行、回放、评分和录像，再补完整成功与明确未成功案例。产物放 `runs/test_results/cast_keyhole_simplifications_<run_id>/`。

交付重点是两套场景、一条能完成各自任务的参考执行，以及清楚的改动清单。尺寸和操作细节在迭代中确定；本计划不把概念草图当成已验证的几何或可解性结论。

## 5. 第一版实现与短测结果（历史）

- `very_easy` 保留十字短支槽；`easier` 使用两处横向错位。槽宽为 21 mm、板厚 9 mm，错位量为 21 mm（资源以原始 mm × 3 记录）。银色孔同步加长，让完整金色叉件在出口处有侧向退出空间。
- 首次实测发现沿用原倾斜摆放会自行倾倒，因此新增可见支撑条和止滑边。支撑不锁住零件，几何检查覆盖初态无穿透和向上提起 10 cm 的路径。原失败运行保留在证据目录的 `very_easy/`，修正后运行是 `very_easy_supported/`。
- 7 项几何／注册／抓点／支撑回归通过。有限厚度零件沿规划通路的离散检查通过；`easier` 的直拉和直接斜拉均被材料阻挡。这些检查尚未排除任意三维旋转捷径。
- 两档均实际运行 ALOHA home 保持 3 个控制步：CUDA Genesis、Nyx、seed 0、默认 2.5 ms tick／4 子步、每控制步 10 tick，共 0.075 s。两件最大位移均约 0.50 mm，最大转角小于 0.005°，末帧最大线速度约 0.242 mm/s，无异常终止或初态 success。这里只验证短时稳定，不代表长时间静置或完整抓取取出成功。
- 原 F1／F2／F3 生成资产共 526 个文件与修改前生成器逐字节一致，原抓持区域回归通过。新变体保持 experimental，`base` 和 `seeded` 原三档映射不变；本轮未改 pipeline、评分器或生成 Harbor 包。

[完整运行报告与各视角原图／视频](../../runs/test_results/cast_keyhole_simplifications_20261002_01/README.md)。以下命令的输出目录必须不存在：

```bash
.venv-gs121-nyx/bin/python scripts/check_cast_keyhole_simplifications.py \
  --variation very_easy --steps 3 --output runs/test_results/keyhole_very_easy_check
.venv-gs121-nyx/bin/python scripts/check_cast_keyhole_simplifications.py \
  --variation easier --steps 3 --output runs/test_results/keyhole_easier_check
```
