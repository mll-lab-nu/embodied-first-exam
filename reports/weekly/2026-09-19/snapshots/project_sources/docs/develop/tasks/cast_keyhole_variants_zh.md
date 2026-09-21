# Cast Keyhole：面向 episode 的随机变体生成器 v2

这里的变体是后续数据生成的环境输入，不是给录像临时换皮。实现采用固定机构目录、固定外形菜单、独立参数采样、实例资格检查四层；本次不生成数据集或 H5。

## 固定家族与固定外形

旧版 F1 比原始解法仅增加约 6.36 mm 行程，F2 的侧向偏心只有 6 mm，不能仅凭名字声称动作足够醒目。v2 冻结了增强后的代表 IK，再用实际 FK 扫掠体反推实体。生成 episode 时不再搜索或随机设计新的宏观机构。

| 家族 | 固定解锁运动（场景尺寸） | 三种预先设计的外形 |
|---|---|---|
| F1 长行程错齿 | 穿齿直行 50.88 mm，相比原始 31.8 mm 增加 19.08 mm | A 圆冠长梯；B 方冠宽肩；C 渐缩楔架 |
| F2 偏心转向窗 | 顶部绕行向侧面增加 24 mm、向上增加 12 mm | A 豆形偏头；B 斜肩偏头；C 梨形偏头 |
| F3 前送—转向—回退 | 深入转向空间，转动 25°，保持该姿态回退 25.5 mm，再横移、复位、退出 | A 圆腹回钩；B 方腹折返；C 双腹葫芦 |

F1 的主要区别在下方直行穿齿阶段，F2 在上方绕行阶段，F3 多出转向、回退和复位阶段。三类仍共享部分基础解锁动作，并非从第一帧起完全不同。数值差异及轨迹对照提供可视化依据，不把自动阈值写成人类感知实验结论。

六种跨家族轨迹互换均有碰撞见证，说明不能直接用另一家的既有轨迹代替本家的解；这不构成全局唯一解证明。

固定机构存放在 `assets/tasks/cast_keyhole/seed_families_v2/`。目录包含实际几何、完整关节轨迹、连续间隙证书和 SHA-256 清单，运行时不依赖 `runs/environment-solvability/` 下的原始设计目录。设计溯源中保留原目录名，仅作为历史记录。

F1 的增强行程会在毛坯中围出非功能小腔，先填充毛坯，再减去完整运动扫掠体。F2 的增强绕行会切下极小碎料，仅保留唯一含抓持锚点的主体，且废料不得超过毛坯面积的 1%；实体拓扑和碰撞仍须通过检查。

## 参数空间与两种模式

`mode="fixed"` 只选择家族 F1/F2/F3 和外形 A/B/C；尺寸、材料和 pose 均用基准值。同一外形不会因 seed 改变而再次随机设计。每个 episode 的身份和溯源仍独立。

`mode="parameterized"` 在固定菜单上采样以下微调：

| 参数 | 默认范围 | 实际作用 |
|---|---|---|
| 外部轮廓宽度、高度 | 各 0.98–1.02 倍 | 仅调整外侧毛坯，保留功能核心和抓持区 |
| 外部轮廓横移 | 模板 ±0.3 mm，即场景 ±0.9 mm | 只移动外形包络，随后重新减去运动扫掠体 |
| 材料外观 | 三套固定配色、金属度及粗糙度 | 不随机改变密度、摩擦或抓持模式 |
| 双手中心 X/Y | 各 ±2 mm | 双臂重新联合求 IK，而非仅挪动零件 |
| 世界坐标偏航微调 | ±1° | 约束共同朝向；共同俯仰/滚转可调整以满足可达性 |

pose 重定向约束谜题相对 SE(3)、双手中心和共同朝向；真实 FK、关节插值、自碰撞、机器人/零件碰撞和桌面间隙全部重新检查。初态为预抓取，不能任意移动单个零件而保留旧关节轨迹。

功能孔宽、齿位置、厚度、抓持锚点和任意整体缩放不属于这里的微调轴。扩大这些轴需要重新反推机构并验证，不能把旧解当作自动成立的证书。

早期 ±4% / ±0.5 mm 范围的边界检查暴露出变化不足及浮点细缝。本版默认范围已收紧；数值清理只处理低于 `1e-8` 模板 mm 的退化间隙，网格精度为 `1e-9` 模板 mm，面积改变上限 `1e-6 mm²`，之后仍执行核心保护和真实拓扑检查。此措施不放宽碰撞容差。

## seed 和 pipeline 接口

沿用 `VariantRng` v1、`build_variant_episode`、`EpisodeSpec`、`TaskLayout` 和 `EpisodeRunner`，不修改公共 seed 派生算法。

每个 episode 使用一个非负整数 seed。家族、外形和每个微参数分别使用 `cast_keyhole/randomization.<axis>` 命名随机流。批量顺序、worker 数量和无关随机调用不改变结果。外部可指定 `family` / `style` 做分层采样；默认家族为均匀随机选择，并不承诺每个小批次精确均衡。

拒绝重采样使用同一 seed 的 `retry` 子流，只重采微参数，保留原家族和固定外形。默认最多三次，耗尽后返回明确失败并保留每次原因，不能默默把失败家族换成更容易的一家。显式边界参数和 `fixed` 模式只尝试一次。数据调度器今后应保留拒绝记录，不能丢掉失败计数造成家族分布偏差。

实例身份绑定 seed、attempt、实际参数、固定目录哈希、实现指纹和机器人/物理配置。输出目录不参与身份计算；旧目录禁止覆盖，证书、轨迹或实现变化会被拒绝。相同依赖版本和配置下可重建同一实例。

```python
from topogym.tasks.cast_keyhole.variants import sample, prepare
from topogym.tasks.cast_keyhole.variant_runner import KeyholeVariantRunner
from topogym.runtime.episode_runner import EpisodeRunContext

# 纯采样：没有渲染、物理执行或数据集写入。
cfg, spec = sample(19, family="F1", style="A", mode="parameterized")

# 实体、重定向 IK、连续几何与关节插值检查。
prepared, folder = prepare(spec, "runs/keyhole_seed19_candidate")

# 消费同一 EpisodeSpec；分别执行 1 ms 和 0.5 ms，再独立审计实际状态。
result = KeyholeVariantRunner("runs/keyhole_seed19_validation").run(
    EpisodeRunContext(prepared)
)
assert result.success and result.stable_ready
assert not result.export_ready  # 本轮没有实现/调用数据集导出。
```

需要有界拒绝重采样时，以 `generate(seed, output, ...)` 代替 `sample + prepare`。CLI：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variants sample --seed 19
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variants generate \
  --seed 19 --family F1 --style A --output runs/keyhole_seed19
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.variant_runner \
  --spec runs/keyhole_seed19/attempt_00/episode_spec.json \
  --output runs/keyhole_seed19_physics
```

新数据生成调度入口应调用上述接口；历史 `family_pipeline sample --count` 是设计/展示脚本，其单批次 RNG 行为不能充当逐 episode seed 契约。

## 验证边界

参数采样成功、实体成功、几何/机器人成功、物理成功是不同状态。候选不会继承母体的物理资格。`prepare` 只返回 `geometry_robot_verified_physics_pending`；runner 必须取得两种时间步的实际执行及独立审计，才能置 `success/stable_ready=true`。全过程不导入 H5 writer，`export_ready` 保持 false。

物理动作范围仍为双臂预抓取 → 双指接触后辅助 weld 抓持 → 完整解锁 → 分离后持稳；不包含桌面拾取、末端释放，也不宣称纯摩擦抓持。有限种子和边界检查不代表整个连续参数域已有数学可解性保证，每个新实例仍须过检查。

本轮证据保存在 `runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/`。轨迹分析 MP4 位于 `demos/cast_keyhole/comparisons/`，其内容是实际物理状态的轨迹图，不是新的机器人相机录屏。正式机器人相机 demo 与分析视频分开标注；不生成新的 HTML 页面。

## 本轮已完成的验证（2026-09-19）

- 14 项自动测试通过，包括退化细缝、非法参数、拒绝上限、失败状态、配置改动和 seed 复现。
- 256 个 seed 覆盖全部九种外形；倒序、四 worker 的采样结果一致。
- 默认范围内 128 个随机实体及 72 个尺寸边界组合全部通过实体/核心保护检查；这 200 项不是物理执行计数。
- 九种固定外形均通过连续几何与机器人检查；六种跨家族错配轨迹均有碰撞见证。
- F1/seed 19、F2/seed 23、F3/seed 29 的参数化实例，各自通过 1 ms、0.5 ms 的实际物理执行和独立状态审计，共六次。
- F1 实测穿齿约 50.795 mm；F2 实测额外偏移约 `[24.011, 12.015] mm`；F3 实测转动约 24.964°、回退约 25.248 mm。三组运动在轨迹对照中可以区分。
- 六次执行的实测最小零件间隙约 0.450–0.532 mm，最终分离下界约 55.452–55.473 mm。
- F1 同 seed 在不同目录重建，几何、proposal、IK、机器人轨迹、证书五个完整文件哈希相同。

[动作轨迹对照 MP4](../../../demos/cast_keyhole/comparisons/2026-09-19_seed_v2_trajectory_comparison.mp4)（三次独立物理运行的状态分析，341 帧 / 12 fps / 28.417 秒，已完整解码）。
[完整验证记录](../../../runs/demo_metadata/cast_keyhole/2026-09-19_seed_generator_v2/validation_summary.json)。本轮未生成数据集或 H5。
