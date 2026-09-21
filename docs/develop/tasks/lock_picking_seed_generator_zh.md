# Lock-picking：固定家族与 seed 随机生成器 v1

2026-09-19：已接通 **seed → 固定机构选择 → 受约束参数采样 → 几何与 IK 检查 → 实例保存／重载**。
这是独立于 demo 的生成模块；没有生成数据集或 H5，也没有将 IK 候选标成物理成功。
实现为 [variants.py](../../../topogym/tasks/lock_picking/variants.py)，
配置为 [lock_picking_variants.yaml](../../../configs/lock_picking_variants.yaml)。

## 家族区别与可见性

| 家族 | 第一锁片槽数 | 必要回退次数 | 固定复位角 |
| --- | ---: | ---: | --- |
| F1 | 2 | 1 | 30° |
| F2 | 3 | 2 | 28°、32° |
| F3 | 4 | 3 | 24°、24°、24° |

每次回退的轴向距离是一个盘距，至少 150 mm，随后转动复位并重新插入。
可以从视频中数出不同的回退次数，也可以从第一锁片的槽数区分机构。
三者使用同一种“退出解耦—换槽—再插入”动作原理；主要差别是分支数和序列长度，
不能据此直接声称机器人或人的成功率已具有简单／中等／困难梯度。

固定机构保存在 [版本化原型库](../../../assets/tasks/lock_picking/seed_families_v1/catalog.json)。
默认冻结孔槽、复位角和限位，不启用历史规划中可选的角度扰动域，也不启用齿数轴。
一次生成会重新核对最少必要回退数、唯一最短分支序列、连续同轴几何路径、
整段机械臂 IK 误差、关节限位和相邻解的连续性。

## 家族内参数

| 参数 | 范围／规则 |
| --- | --- |
| 外盘半径 R | 65–95 mm |
| 盘距 p | `max(150, 150 × R / 80)` 至 180 mm；从不低于当前 150 mm 基准 |
| 三齿／握柄 | 固定三齿；齿距 p，握柄偏移 `3p+45 mm`，全插入行程 `4p` |
| 整体位置 | x、y 各 ±5 mm；z ±2 mm，机构、钥匙、支撑与检查相机联动 |
| 配色 | 紫／蓝、青／紫、灰蓝／锈红三套；第一锁片均避免与黄色孔缘撞色 |
| 表面 | roughness 0.35–0.60，metallic 0.20–0.55；不修改摩擦、质量或阻尼配置 |

S/M/L 继续是展示锚点：`(R,p)=(65,150)/(80,150)/(95,180) mm`。
它们不是额外机构家族，也不是强制的难度标签。
目前只支持平移，不开放 yaw/pitch/roll 或相机随机化。连续参数域是候选域；
不同候选须逐例验证，有限 seed 检查不等于证明全域可达或无遮挡。

颜色和材质使用独立具名随机流，不改变同 seed 的机构、位置或 IK 目标。
位置变化可能触及现有机器人关节限位，所以 IK 失败会显式记录并重试。
重试使用同 seed 的 `retry=k`，保留家族和外观，仅重采尺寸与位置；默认最多 8 次，
耗尽后明确拒绝，不返回未经检查的候选。若要求家族配额，应显式指定 family。

## 接入方式

公共 `VariantRng` **保持 v1，无须修改旧 seed 算法**。
新配置的 `variation` 使用现有 choice/uniform/derived/validate 机制；
现有 `build_variant_episode` 可以抽出真实不同的配置。
生产调用应使用任务适配层 `generate()`，因为公共抽样入口本身不验证 IK。

```python
from topogym.tasks.lock_picking.variants import generate, write_instance, load_instance

instance = generate(42)                       # 自动选择 F1/F2/F3
# instance = generate(42, family="F2")        # 固定家族，家族内随机
# instance = generate(0, family="F1", representative=True, anchor="M")
write_instance(instance, "runs/my_lock_instance")  # 必须是新目录
cfg, episode_spec, saved = load_instance("runs/my_lock_instance")
```

命令行等价入口：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.lock_picking.variants --seed 42 --output runs/my_lock_instance
```

实例包含完整 `EpisodeSpec`（指令、布局、机器人、场景、相机、物理和控制配置）、
生成器／原型库／RNG 版本、选定原型快照、原型哈希、接受 attempt、全部拒绝原因、
关键动作与整段 IK、验证等级、URDF／网格以及文件校验清单。
输出路径不参与实例 ID。恢复时校验哈希、直接读取确定值；不依赖历史 run 或当前原型库重采样。
场景缓存使用实例内容 ID；并行构建仍建议每个 worker 使用独立 `asset_dir`。

`sample()` 只解析参数和 EpisodeSpec；`generate()` 才返回已通过几何与 IK 的候选。
`write_instance()` 和 `load_instance()` 不依赖视频。后续 demo runner 与数据集 pipeline
可以消费同一个已解析实例及其 `EpisodeSpec`，无须从展示脚本反推参数。

场景消费 `aligned_entry` 下的确定几何，并拒绝将已生成实例改回会覆盖槽位的
`limited_two_retreats`。当前旧物理 oracle 仍只支持两次回退，不能直接承担全部家族的完整执行；
未来接数据集采集时还需按实例动作序列实现／验收完整抓取、解锁、释放和真实动作记录。

## 检查与视频

[验证报告](../../../runs/demo_metadata/lock_picking/2026-09-19_seed_generator_v1/report.json)
逐项记录 seed 覆盖、拒绝次数、误差、九个固定代表以及跨进程复现结果。
本轮 seed 0–255 共 **256/256 接受**，F1/F2/F3 分别 84/88/84 个，
256 种几何与 256 种表面配置；157 个首次通过，99 个经过确定性重试，最多用满 8 次尝试。
最小盘距 150.025 mm；机械臂最大位置误差约 2.00 μm、最大转动误差约 1.07×10⁻⁵ rad。
九个固定 S/M/L 代表全部通过几何／IK；27 项回归检查通过，
seed 0/128/255 在两个独立工作进程、反向提交顺序下复现同一实例 ID。
较高的首次 IK 拒绝比例说明当前位置域还有优化空间，不能将这 256 个 seed 的结果推广为任意 seed 必定接受。

复现命令（仅生成验证材料）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.lock_picking.verify_variants --count 256 --output runs/lock_generator_audit_NEW
.venv-gs121-nyx/bin/python -m unittest tests.check_lock_picking_variants \
  tests.check_lock_picking_geometry tests.check_lock_picking_certificate tests.check_lock_release_gate -v
```

三个 M 代表使用相同相机、相同采样播放节奏。视频是**已对齐起点到插入终点的 IK 运动学预演**，
零物理步进，不包含抓起和松手，不计为完整机器人动力学 demo：

- [F1：一次回退](../../../demos/lock_picking/front_oblique/2026-09-19_F1_M_kinematic_front_oblique.mp4)
- [F2：两次回退](../../../demos/lock_picking/front_oblique/2026-09-19_F2_M_kinematic_front_oblique.mp4)
- [F3：三次回退](../../../demos/lock_picking/front_oblique/2026-09-19_F3_M_kinematic_front_oblique.mp4)

已生成实例的机器人场景碰撞、接触动力学和完整流程资格仍为 `not_run`。
已有成功物理视频属于等角两回退基线，不能为这里的三类新机构背书。
当前 IK 可达余量较小，因此本轮完成的是可重复、会检查和拒绝的候选生成链路；
后续物理采集应另加资格检查，不能仅凭 `generate()` 返回就写成成功样本。
