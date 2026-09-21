# 光纤收束：铜杆支架与线密度／孔径变体

2026-09-19 补充：[实例生成与 seed 接入检查](fiber_bundling_variant_pipeline_zh.md)。现在提供固定代表选型、参数随机化、完整 EpisodeSpec／资产快照及重载校验；300 个 seed 与 39 个边界组合通过初态几何检查。用户已确认本任务采用密度三类，不要求 IK 有本质区别；生成候选仍需独立完成物理验收。

本版以 **线数 N、环内半径 R** 为两个生成参数。稀疏、标准、密集是三个可见的几何类别，每类均覆盖同一孔径范围；不预先把它们命名为三个不同 IK 解法或已经验证的难度等级。

## 材料能否表达任务意图

当前模型可以表达：细线起初沿护套方向伸出，随后自然外弯；通过粗护套带动细线与环接触，改变弯曲形状，卸载后不主动恢复初始曲线。根部位置受关节约束，不能滑离护套端面；根部朝向和后续关节均可变。

实现是刚性短杆／胶囊的被动关节链，细线关节 `stiffness=0`、`damping=2e-5`，整条电缆 `gravity_compensation=1`。初始曲线只写入初态，不是运行期间的回弹目标。模型没有弹性区、屈服阈值、硬化或实测铜线参数；小力和运动惯性同样可能改变形状，卸载后也可能继续运动一段时间。因此它是**保留形变的任务近似**，不能作为真实铜导线材料力学的验证。

旧矩形支柱的 8 芯、R=13.5 mm 场景已有约 175 s 完整机器人执行，2 ms / 1 ms 两次均完成全部细线穿环，夹爪禁碰通过，含双侧接触后辅助夹持。完整路径的严格步长对照仍未通过：瞬时局部最大线形差异 4.932 mm；不能把“两次都成功”解释成材料精度或全程数值收敛。原报告保存在 `runs/demo_metadata/fiber_bundling/2026-09-17_anchored_ik_hybrid_v1/`；旧视频已按用户 2026-09-18 的要求移除，当前交付只保留基础铜杆版无 UI 三视角。

如果目前目标是这个操作任务，保留现有近似有依据；若目标变为区分不同真实铜线的屈服和回弹，需要另建弹塑性本构并做加载／卸载标定。这次不更改材料参数。

## 新外观与真实碰撞尺寸

- 铜环下方改为 **直径 5 mm 的圆铜杆**，替换原 12 × 16 mm 矩形柱。杆顶嵌入环外侧下缘 2 mm，保持可见连接，完全位于孔外。
- 铜环和杆采用偏红铜色；导出的 PBR 金属度 0.85、粗糙度 0.32。护套、彩色绝缘层、切口填充和短铜丝线头保留。
- 杆的渲染半径与碰撞半径均为 2.5 mm；不保留外观之外的旧矩形碰撞柱。环仍使用原 64 段复合碰撞体，截面半径 4 mm。
- 杆、底座、铜环均为固定夹具。杆的铜材质是外观设定，这里没有模拟支架本身弯曲。
- 新配置为 `configs/fiber_bundling_copper_preview.yaml`；旧 `fiber_bundling_preview.yaml` 保留原支柱，历史缺省配置按 `legacy_box_v1` 回放。新支柱或新孔径不能继承旧布局的稳定性证据。

新场景目录：`runs/environment_bootstrap/fiber_bundling/2026-09-17_copper_rod_v4_cpu/`。`initial_overview.png` 看安装关系，`initial_cable_end.png` 看细线与环，`preview.mp4` 是相机环绕。CPU / rasterizer 实际运行 250 步、0.5 s，细线和关节位置无可测漂移，根部最大误差约 2.12e-8 m，1000 个子步未触发夹爪禁碰。**这项初态检查本身不认证完整穿环；后续逐实例机器人结果见下方记录目录。** GPU 动态场景渲染因显存不足退出，未把该次作为通过证据。

交付截图使用 rasterizer，能检查形状与配色，不能用它评价 Nyx 的金属反射效果。PBR 设置已写入 GLB；额外的静态 Nyx 材质渲染未完成出图，停止状态和实验源码保存在预览目录的 `material_preview/`。

## 三类如何控制两个参数

| 类别 | 采样线数 N | 首个代表 | 同一类内的环内半径 R |
| --- | --- | --- | --- |
| 稀疏 `sparse` | {4,5,6} | 4 芯 | [12.8,15.0] mm |
| 标准 `standard` | {7,8,9,10} | 8 芯 | [12.8,15.0] mm |
| 密集 `dense` | {11,12,13,14,15,16} | 16 芯 | [12.8,15.0] mm |

九个首批代表为 `{4,8,16} × {12.8,13.5,15.0}`。每个线数都有小、中、大三种环，保留“线少但孔紧”和“线多但孔宽”的组合，避免把线数与孔径绑成一个难度开关。

固定粗护套半径 12 mm、单根细线半径 1.2 mm、细线长度 80 mm、根部所在圆半径 8 mm、28–50° 初始末端切向角分布、形状种子 7、材料密度及阻尼。增加 N 自然增加细线总质量和接触对数量，不补偿单根质量，也不调整刚度来抵消这些变化。环截面厚度、终端、线托和空间布局固定。

这里的“密度”是**芯线数量／根部间距**，不是配置中 `density_kg_m3` 的材料质量密度。当前根部排在一圈上，还不是多层填满整个护套截面的工业电缆填充模型。

相邻根部中心间距与表面间隙为：

```text
pitch(N) = 2 × 8 mm × sin(π/N)
surface_gap(N) = pitch(N) − 2 × 1.2 mm
```

4 / 8 / 16 芯对应约 **8.914 / 3.723 / 0.721 mm** 的表面间隙。绝缘线截面积之和占护套外圆面积的 4% / 8% / 16%；这项指标只描述该模型的几何占比，不代表导电铜的填充率。

半径使用环碰撞模型的最小实际孔径，而不只看视觉圆：

```text
R_actual = (R + 4 mm) × cos(π/64) − 4 mm
clearance = R_actual − 12 mm
```

R=12.8 / 13.5 / 15.0 mm 对应实际径向余量约 **0.780 / 1.479 / 2.977 mm**。最低允许余量设为 0.7 mm；不能只要求名义环半径比电缆大一点。这个余量是候选生成筛选值，不是机器人接触稳定性的充分条件。

## 采样、拒绝与验收

1. 先按类别均衡配额；默认连续 episode seed 用 `seed % 3` 交错选择类别。也可显式指定 `--family`。每类内部均匀抽取允许的整数 N。
2. 使用现有 `VariantRng` 的独立具名随机流采样 N 与 R。R 在三类中均为同一个均匀分布；同 seed、不同类别的孔径相同。首版形状种子固定，只有这两个参数变化。
3. 检查根部不重叠、所有初始细线不相交、根部在护套内、环与初态细线分离、实际孔径余量达到下限，并排除整束初态已经收拢的无效样本。失败实例保存拒绝依据，不裁剪参数以冒充原采样值。
4. 保存完整配置、生成器／RNG 版本、资产、实际孔径、根部间距与检查结果。初始资产产物标记为 `geometry_candidate`；后续执行认证另存，不能借用 8 芯旧支柱的全流程录像。
5. 后续按**每个实例**执行静置、粗护套加载／卸载、2→1 ms 对照，以及真正的机器人抓取与全流程穿环。执行始终只能抓粗护套，夹爪触细线立即失败；允许任意收束次序、邻线形变和环口引导，只验最终全部细线与前端护套通过。
6. 操作时间、接触次数、重试数、末态余量和失败率测完之后再讨论难度或不同策略。不能仅从 N 增加或 R 减少断言某种 IK 解法成为必需；环孔足够大也不单独证明机械臂可达或固定尾线存在可行路径。

## 生成与查看

规则文件：[fiber_bundling_density_v1.yaml](../../../configs/task_variants/fiber_bundling_density_v1.yaml)。生成器：[variants.py](../../../topogym/tasks/fiber_bundling/variants.py)。

```bash
# 新目录；不覆盖已经生成或验证的实例。
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.variants \
  --representatives --output runs/environment_bootstrap/fiber_bundling/NEW_GRID
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.variants \
  --family dense --seed 23 --output runs/environment_bootstrap/fiber_bundling/NEW_SAMPLE
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.plot_variants \
  runs/environment_bootstrap/fiber_bundling/NEW_GRID

# 生成某实例的短时物理与场景预览，使用其已解析配置。
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.demo \
  --config-path /ABSOLUTE/PATH/TO/NEW_SAMPLE --config-name config \
  env.genesis.backend=cpu env.renderer.type=rasterizer run.output=/ABSOLUTE/PATH/TO/NEW_PREVIEW
```

已生成目录：`runs/environment_bootstrap/fiber_bundling/2026-09-17_density_radius_v1/`。

- `density_radius_grid.png / .svg`：九个同尺度截面示意，展示两参数；为目标对齐关系，不是初态分叉线的物理帧。
- `density_scene_comparison.png`：4 / 8 / 16 芯同相机、同孔径的实际场景近景。4、16 芯另做 0.1 s 短时静置，均无可测细线漂移；不代表长程接触稳定性。
- `manifest.json`：九例参数与几何检查状态。
- `<类别>_<线数>_r<半径>mm/config.yaml`：完整可复现配置。
- 每例 `assets/bundle.xml` 为动态电缆，`ring.urdf` 为环碰撞资产，`ring_fixture.glb` 为支架检查资产，`scene_initial.glb` 为整体静态资产；细杆实际碰撞由场景生成器按相同参数创建。

九例重置几何检查均通过；额外覆盖 4–16 芯所有整数 × 三档孔径共 39 个重置几何点，均通过。33 项相关代码检查通过。这批重置检查没有计入任何全流程机器人执行；后续新增的完整 demo 单独记录如下。


## 完整 demo 批次：从 4–6 芯到标准与密集

执行记录目录：[variant_demos_v1](../../../runs/environment-solvability/fiber_bundling/variant_demos_v1/)。`README.md` 给出各实例当前状态，`status.json` 保留加载检查、两种步长的完整任务结果、严格线形对照及归档位置。按用户最新要求，正式 MP4 在 [demos/fiber_bundling](../../../demos/fiber_bundling/) 中只保留基础版全景、近景、腕部三个同步视频，各视角一个目录，无文字 UI 或画中画。

本批已经完成九个铜杆代表、5 芯和 6 芯的 R=13.5 mm 过渡实例，以及已有的旧支柱 8 芯完整 demo，共 12 个几何实例。原 52 份视频已按用户要求删除，历史物理证据仍保留。[当前视频目录清单](../../../runs/demo_metadata/fiber_bundling/README.md)链接基础变体 `2026-09-18_standard_08_r13p5mm_clean_v1`，三路各 177 秒，使用原 8 芯 R=13.5 mm 完整物理轨迹重新渲染。控制器沿用已完成 demo 的整束反馈 IK，按真实包络选择接触动作，没有强制逐根顺序；只有真实双侧护套接触后才能启用辅助夹持，禁碰检查保持每个物理子步执行。

12 例均在 2 ms 和 1 ms 下独立完整通过；严格全过程线形对照通过 6 例：4 芯三孔径、5 芯中孔径、6 芯中孔径、16 芯最小孔径。其余 6 例保留差异超限结果，没有放宽阈值。16 芯小／中／大孔径的主运行分别为 333.924／235.094／224.254 秒。最终逐例配套文件、视频哈希、独立副本和本地链接核对见批次的 `final_archive_verification.json`；录像已在归档时完整解码。

每个新实例先完成 5 s 静置、0.35 s 粗护套轻载和 5 s 卸载，并做减半时间步对照；通过后从初态独立运行完整机器人过程。两次都完成穿环与严格全程线形收敛分别记录，不把其中一个替代另一个。视频由其中一次连续物理轨迹生成，按记录状态回放，三路视角同帧同步；归档前完整解码、核对帧数／时长、校验轨迹和文件哈希。

另对保存轨迹做细线穿孔补查：沿细线每 0.5 mm 取材料样本，检查各样本最后一次从近侧越过环平面的位置，并确认完整末态在出口侧。允许先在环外整理后退回；最后一次通过必须位于孔内，沿用原有 0.3 mm 接触容差。补查使用最大间隔 40 ms 的已保存状态做线性插值，属于采样诊断，不能替代原生逐步接触检查或称为连续碰撞证明。旧归档的补充结果保存在批次的 `passage_audits/`；后续归档同时保存 `fine_passage_validation.json` 和检查代码。

历史 6 芯录制曾因局部阴影过暗而重新渲染，关闭阴影贴图并保留定向光照；物理轨迹未变。该录像现已按用户要求移除，报告仍保留。所有图形回放逐帧核对细线中心线，允许的数值显示误差不超过 2 μm；当前基础版无 UI 录制的中心线回放误差为 0。

6 芯和 16 芯的单精度加载对照出现世界坐标差异超限，原失败记录保留。6 芯及 16 芯三种孔径改用双精度后，均逐实例通过同样的 2→1 ms 加载门槛。没有调整材料、加载幅度或验收阈值，双精度结果也不构成真实铜线本构标定。完整控制器、配置、资产和接触修正均在运行目录冻结；减半步长使用相同版本重新从初态执行。 16 芯的初态性能诊断中，CG 约为 Newton 的 2.8 倍速度；CG 单精度加载对照仍失败，双精度通过，因此只把双精度 CG 纳入后续完整执行候选。每个孔径重新取得匹配求解算法的加载证据，结果见各实例的 `stability_cg64/`；性能诊断本身不计为完成或物理认证。

```bash
# 对已经生成且尚未运行的实例执行加载、完整机器人、独立复核和录像归档。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYOPENGL_PLATFORM=egl \
  .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.variant_demo \
  runs/environment-solvability/fiber_bundling/variant_demos_v1/instances/INSTANCE \
  --attempt NEW_ATTEMPT --stage complete

# 从已有报告更新目录清单，不改写物理证据。
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.variant_progress \
  runs/environment-solvability/fiber_bundling/variant_demos_v1
```

遇到已经开始但中断的目录，运行器停止并保留证据，不能在原轨迹上续接后冒充一次从初态开始的完整执行。新尝试使用新目录；旧版完整副本始终保留。
