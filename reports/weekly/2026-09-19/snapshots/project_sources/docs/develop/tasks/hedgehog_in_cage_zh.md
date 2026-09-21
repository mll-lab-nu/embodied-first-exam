# 刺球出笼：场景、变体生成与完整演示

Agent 接入：CLASSIC wood 固定基础实例已增加[单臂 adapter](../modules/hedgehog_agent_adapter_zh.md)，复用公共执行循环和本地文件队列，包含三路实时观测及可复制的求解 prompt。短程接口检查已通过；完整 agent 求解与下述 v2 随机变体接入尚未验证。

2026-09-19，生成器 v2：保留 `oblique_gate`，以 `fixed_side_window`（固定六刺、圆端侧孔）和 `gen_keyhole`（固定六刺、斜笼条、顶部钥匙孔）替换默认池中的双门和螺旋家族。两者都是经典结构参考下的自定义适配，不是官方 CAD 复刻；默认深木色笼体、浅木色刺球。侧孔方案与 CLASSIC 共享侧向取出策略，不宣称三类都需要本质不同的 IK。

- 保持 `sample → materialize → load_instance → variant_runtime.build_scene`、共享 `VariantRng` 和 `EpisodeSpec` 接口。[配置](../../../configs/task_variants/hedgehog_in_cage/generator_v2.yaml)只更换默认家族池，继续在固定原型内采样尺寸、位置、朝向和木质外观。
- 新实例使用 `hedgehog_seed_v2` 身份；已保存的 v1 实例仍按 v1 配置和资产校验、重载。旧原型库和完整视频保留，退役家族不参与新的默认抽样。
- GEN 的窄槽有作用：封住窄槽后，保存的退出路径碰撞。这个反事实检查随几何微调一起变换，并逐实例重验；跨家族路径仅作为诊断，不用不同刺球的交叉碰撞推断 IK 必然不同。
- [生成与重载检查](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_generator_replacements_review_v2/verification.json)：9 项回归测试、13 个固定／随机／边界实例的几何与 IK 预检查（13,556 个机器人碰撞采样）、三个家族的 Genesis 场景加载均通过。1000 个 seed 的家族抽样覆盖三类；GEN seed 42 跨进程生成的 667 个文件一致，仅配置输出目录不同，迁移后不重采样重载成功；三套旧 v1 实例重载和旧螺旋实例重新构建也通过。没有生成数据集或 H5，随机后代仍为 `physical_execution=not_run, export_ready=false`，不能继承父实例的物理成功。

当前代表视频来自单次连续物理执行，均为预抓取起点、双指接触后辅助抓持，包含取出、落桌、解除辅助、张爪撤离和自由静置。
两个新原型各通过 0.5 ms / 0.25 ms 内部子步的完整执行及实际状态碰撞复核；六路 MP4 均完整解码通过，同组帧数和时长一致。侧孔组 82.25 s，GEN 组 98.83 s。

生成入口保持不变，例如 `python -m topogym.tasks.hedgehog_in_cage.variants --seed 42 --family gen_keyhole --output runs/variant_checks/hedgehog_in_cage/example_v2_seed42`；省略 `--family` 按 seed 选择家族，加 `--mode fixed` 只选固定原型。输出目录必须尚不存在。

| 默认家族 | agentview | front_oblique | wrist |
| --- | --- | --- | --- |
| CLASSIC 参考单斜窗（保留） | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-17_family_a_oblique_gate_v1_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-17_family_a_oblique_gate_v1_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-17_family_a_oblique_gate_v1_wrist.mp4) |
| 固定六刺侧孔（替换双门） | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-19_fixed_side_window_v2_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-19_fixed_side_window_v2_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-19_fixed_side_window_v2_wrist.mp4) |
| GEN 风格顶部钥匙孔（替换螺旋） | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-19_gen_keyhole_v2_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-19_gen_keyhole_v2_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-19_gen_keyhole_v2_wrist.mp4) |

以下保留早期试验及 v1 的历史记录，不代表当前默认家族池。

2026-09-19 侧孔方案验证：自定义六根固定圆柱刺、球核直径 18 mm、圆端长孔高 60 mm，最宽处 22 mm 时已找到整体旋转退出路径，初始姿态直拉受阻。3 倍场景经 8,516 个姿态及采样间运动界复核，网格间隙下界 0.953 mm，导出资产重载复核一致。[木质几何预演 MP4](../../../demos/hedgehog_in_cage/detail/2026-09-19_fixed_spikes_side_window_v3_kinematic_detail.mp4) · [报告](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_fixed_spikes_side_window_v3/report.json)。入口 `side_window_probe.py` 支持宽度扫描、`--plan-width` 重规划及 `--path` 重放；`side_window_preview.py` 录制物体运动学预演。这是自定义模型，不是官方 AXIS/GEN 复刻或已验证机器人执行，尚未纳入随机生成器，也未证明独立的新动作家族。

2026-09-19：已实现面向后续数据管线的随机变体生成器。固定选择 A 单斜窗、B 双门换层、C 螺旋导向三套已验证原型，再在家族内采样笼体尺寸、整体位置／朝向和木质外观。固定模式只选现成原型。此前规划的另外六种外形仍未纳入可执行原型库。

- 入口：[variants.py](../../../topogym/tasks/hedgehog_in_cage/variants.py)，参数域：[generator_v1.yaml](../../../configs/task_variants/hedgehog_in_cage/generator_v1.yaml)。复用共享 `VariantRng` 命名随机流和 `EpisodeSpec`；`sample → materialize → load_instance → variant_runtime.build_scene` 不依赖录视频入口或历史工作目录。
- 笼体径向／高度按原型通道余量约束，固定底面，单点最大位移不超过原余量的 35%；位置 ±4 mm、朝向 ±2°。保留刺球、抓持部位和各家的物体解法，整体位姿变化后重算连续分支 IK。默认深木色笼体、浅木色刺球。
- 每个接受实例检查完整物体路径余量、全机器人离散碰撞、放置后张爪／撤离，以及家族动作删减和跨家族反例；失败在同一家族内有界重试，记录原因和原始请求。保存资产、配置、轨迹、版本、参数与文件哈希，重载不重新采样。
- 验证：1000 个 seed；15 个固定／随机／边界实例全部通过预检查；三家随机实例分别通过 Genesis 场景加载；同 seed 跨进程的 368 个文件完全相同，只有配置中的输出目录不同；8 项回归测试通过。[检查报告](../../../runs/demo_metadata/hedgehog_in_cage/2026-09-19_generator_review_v1/verification.json)。
- 本轮没有生成数据集或 H5。新随机实例的动力学执行尚未运行，`export_ready=false`；原型的物理成功不继承给随机后代。连续余量证明针对物体路径，机器人碰撞是最大 0.01 rad 步长的离散检查。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.variants \
  --seed 42 --output runs/variant_checks/hedgehog_in_cage/example_seed42
```

可加 `--family oblique_gate` 指定家族，或 `--mode fixed` 只选择原型。已存在的输出目录不会覆盖。
三家原型完整物理视频（预抓取起点、接触后辅助抓持，含释放／撤离／静置）：

| 家族 | agentview | front_oblique | wrist |
| --- | --- | --- | --- |
| A 侧移配合倾斜 | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-17_family_a_oblique_gate_v1_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-17_family_a_oblique_gate_v1_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-17_family_a_oblique_gate_v1_wrist.mp4) |
| B 两道门之间换层侧移 | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-17_family_b_staggered_gates_v1_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-17_family_b_staggered_gates_v1_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-17_family_b_staggered_gates_v1_wrist.mp4) |
| C 旋转与推进耦合 | [MP4](../../../demos/hedgehog_in_cage/agentview/2026-09-17_family_c_helical_guide_v1_agentview.mp4) | [MP4](../../../demos/hedgehog_in_cage/front_oblique/2026-09-17_family_c_helical_guide_v1_front_oblique.mp4) | [MP4](../../../demos/hedgehog_in_cage/wrist/2026-09-17_family_c_helical_guide_v1_wrist.mp4) |

2026-09-17 新增：[从可解 IK 反推偏心斜窗笼](hedgehog_in_cage_inverse_window_zh.md)，包含完整提取、落桌释放、物理检查与三视角录制流程。以下保留最初的资产与初态工程记录。

同日新增：[三个动作 family 各一个完整代表 demo](hedgehog_in_cage_family_demos_zh.md)，包含单斜窗、双门槛及螺旋导向的实体结构、两档子步物理执行和三视角对照。

日期：2026-09-16。范围：参考资产准备、参数化重建、带静止机械臂的初态展示。

变体空间规划：[3 个动作 family × 3 种外形](hedgehog_in_cage_family_space_zh.md)，区分设计候选、可解性证据与完整物理演示。

## 型号与资料

按用户选择保留三套独立模板：CLASSIC 三星（10 刺）、ORIGINAL（12 刺）、Worrall 1896（13 刺）。
本次只实现第一套。刺的数量、排布与笼子结构应成套变更。

官方资料：[CLASSIC 产品页](https://puzzles.rademic.cz/classic.htm)、
[官方解法页](https://help.rademic.cz/)、
[三星版英文解法图](https://help.rademic.cz/hedgehog_in_the_cage_puzzle_classic_solution_rademic_puzzles_IMG_2432um.jpg)。
三星普通版和五星黄铜／不锈钢版的解法图不同。

已知外形为 45 × 80 mm、10 刺、一个较宽出口。未获得官方 CAD 或完整工程尺寸。
本次资产是带来源标注的重建：球径、刺位、刺长、内壁、五窗排布和圆角都是暂定值。
未套用其他型号的刺长、球径或间隙数据；不宣称已经复现 CLASSIC 的真实退出运动。

## 文件与运行

| 路径 | 用途 |
| --- | --- |
| `assets/tasks/hedgehog_in_cage/classic_3star/` | 官方参考图、来源、参数及原尺寸 OBJ / URDF |
| `topogym/tasks/hedgehog_in_cage/geometry.py` | 笼体分块、十刺球、质量惯量估计和初态几何距离检查 |
| `topogym/tasks/hedgehog_in_cage/prepare_assets.py` | 不加载 Genesis 的资产生成入口 |
| `topogym/tasks/hedgehog_in_cage/scene.py` | 共享桌面、Panda + Robotiq、固定笼和自由刺球 |
| `topogym/tasks/hedgehog_in_cage/demo.py` | 静态渲染、相机巡视视频、运行报告与本地页面 |
| `configs/hedgehog_in_cage_classic_preview.yaml` | 缩放、布局、相机和输出配置 |

从仓库根目录运行：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.demo
```

也可通过 `-m demos.environment_bootstrap.hedgehog_in_cage` 运行。
加 `run.record_video=false` 可只生成静态图片。
输出为 `runs/environment_bootstrap/hedgehog_in_cage/classic_initial/index.html`，并接入环境汇总页。

## 场景与检查范围

原型统一放大 3 倍，笼体外形 135 × 240 mm；机器人保持原尺寸。
笼体固定在桌面底座，刺球为一个保留 6 自由度的刚体。所有刺与球核共用一个 link。
球核凸块、逐刺凸块和逐段笼体凸块保留孔道，不对整件凹形物体取凸包。

确定性搜索无相交姿态，再下移到接近笼体支撑的位置。球核使用球包络，刺使用包围实际锥形刺的圆柱包络；
对中心线采样并将半采样步长计入半径，得到保守的连续间隙下界。
初态检查只涉及刺球与笼体，不代替全机器人运动可达性或装配路径验证。

机器人只在初始化时设置 home；演示不调用 `scene.step()`，不执行操作轨迹。
视频只改变相机，报告核对前后机器人和刺球 qpos 完全相同。
因此 `simulation_steps=0`，不声称重力静置、摩擦抓持、释放或求解已经通过。

后续先补几何尺寸和官方解图对应姿态，再验证接触与退出路径；“各侧等宽可退出”在此基准上另行改造并验通路。
