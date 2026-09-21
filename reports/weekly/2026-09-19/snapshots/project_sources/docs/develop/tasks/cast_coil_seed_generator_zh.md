# Cast Coil 固定家族与 seed 随机变体生成器

2026-09-19：本轮只开发和验证变体生成，不生成数据集或 H5。生成器版本 `cast_coil_seed_v2`；固定资产库为 `seed_families_v1`。这里的 v2 是排除首轮发现的无效切角取值后的采样域版本，公共 RNG 仍为版本 1。

## 三个家族的动作能否看出不同

固定采用已经设计好的 9 mm 核心代表，分别施加单侧切角、四角直角台阶、四角斜切轮廓。它们是不同机制和结构，不是在同一物体上随机换 IK 初始关节角。

| family | 当前装配方向的区别 | 观察重点 |
| --- | --- | --- |
| A `eccentric_turn` | 绕偏心轴连续回转 90°，随后闭合；偏心量 9 mm | 回转中心和银件在正面内的移动范围；单侧切角 |
| B `split_turn_offset` | 回转 45° → 平移错位 9 mm → 再回转 45° → 闭合 | 中途角度保持、只平移的独立阶段；四角直角台阶 |
| C `axial_screw_turn` | 回转 90°与轴向回退 9 mm 同时进行，随后闭合 | 侧面的层间深度移动；四角斜切 |

**统一近景中可以区分，远景不能保证。** B 的阶段变化最明显；A/C 回转角度进度相同，主要区别是偏心平面路径与轴向位移。正面会压缩 C 的深度运动，应结合侧面或斜视。按相同动作开始时间对齐，规划关节最大差异 A/B 50.27°、A/C 4.71°、B/C 51.63°；这包含 B 多出的中间阶段，不是所有关节持续存在这么大的差异。

在本次固定 480 px 单栏相机中，9 mm z 错位投影约 15.9 px；9 mm 轴向位移正面约 2.4 px、侧面约 14.3 px、斜视约 9.6 px。这是投影量和人工图像检查，不是识别率或所有默认机器人相机均可辨的证明。

三路同步局部对照，均为 12 秒 / 240 帧 / 20 fps：

- [正面 MP4](../../../demos/cast_coil/motion_front/2026-09-19_seed_families_v1_kinematic_motion_front.mp4)
- [侧面 MP4](../../../demos/cast_coil/motion_side/2026-09-19_seed_families_v1_kinematic_motion_side.mp4)
- [斜视 MP4](../../../demos/cast_coil/motion_oblique/2026-09-19_seed_families_v1_kinematic_motion_oblique.mp4)

视频为相同相机、尺度和材质下的 **运动学机制局部对照**，仅包含转动/错位和闭合阶段；较短路径末尾保持静止。没有机器人或动力学回放，不是完整物理 Demo。它使用实际复合盒实体，不是装饰性的替代形状。原正式五视角基础装配视频保持原位。视频清单及完整解码结果位于 [review metadata](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_family_motion_review_v2/video_validation.json)。

## 生成规则与当前范围

先按 seed 选择固定 family/core，再在它的条件域内微调。机制参数固定为 9 mm，不在每条样本中重新反推通道。新增的 [variants.py](../../../topogym/tasks/cast_coil/variants.py) 复用公共 `build_variant_episode`、声明式 `choice/uniform/derived/validate` 和 `VariantRng`，**无需改变公共 seed 映射或 RNG 实现**。

| 参数 | 当前取值 | 联动规则 |
| --- | --- | --- |
| family | A/B/C 离散选择，可显式固定 | 固定核心、轮廓类型与相对运动模式绑定 |
| 正面尺寸 `face_scale=s` | `[0.97,1.03]` | x/z 同比缩放，抓点、路径平移和转轴同步缩放 |
| 厚度 `depth_scale=d` | 基础域 `[0.94,1.06]`，按质量进一步收窄 | 同时缩放材料、层间空隙、抓点和 C 的轴向位移 |
| 外轮廓增加量 `delta` | `{0,1.5}` mm | 原型坐标切角长度 `L=15+delta`，实际尺寸再乘 s；保持家族轮廓和抓持材料 |
| 场景整体位置 | 基础 x/y 各 ±5 mm | 场景与 IK 共用解析位置，重新规划 |
| 场景 yaw | `90°±3°` | 物体与局部抓取方向同步变换 |
| 两件初始偏移 | `(-120,+180) mm` 的 x/y 各 ±5 mm | 检查两轴实际外包络间隙均 ≥10 mm，不把原点距离当表面间距 |

每件质量倍率为 `r_i = s²*d*V_i(delta)/V_i(0)`，要求 `0.9 <= r_i <= 1.1`。先根据 family、s、delta 计算 d 的交集范围，再用 `[0,1]` 随机比例映射进去。禁止独立随意修改碰撞体、运动和质量。

每个候选独立检查实体水密/连通/孔洞、连续装配件间路径、六方向直拉阻挡，以及另外两个 family 的参考路径有实际重叠见证。这些负对照不证明全局唯一解。抬升高度由完整相对路径的桌面余量计算，默认至少 80 mm；A 的基础代表需要约 **95.34 mm**，不能沿用 80 mm。规划器补充零件—桌面检查，并重算双臂 IK、关节限位和采样机器人碰撞。

## seed 接口、恢复与拒绝

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-gs121-nyx/bin/python -m topogym.tasks.cast_coil.variants \
  --seed 42 --output runs/environment-solvability/cast_coil/seed42
```

默认执行几何与机器人规划检查；`--family split_turn_offset` 可固定家族，`--representative` 可生成该族的固定代表；`--geometry-only` 明确跳过机器人检查。输出目录必须是新目录，拒绝覆盖旧证据，也拒绝将 JSON/YAML 等元数据写入 `demos/`。

Python 入口：

```python
from topogym.tasks.cast_coil.variants import sample, generate, load_instance

cfg, spec = sample(42)                   # 仅采样候选，尚未做几何/IK验收
result = generate(42, "runs/coil_seed42") # 默认验收几何及采样机器人 IK
cfg = load_instance("runs/coil_seed42/attempt_00/instance.json")
```

恢复时应从 `result.json` 的 `candidate_directory` 获取实际接受目录，不能假定始终是 `attempt_00`。`load_instance` 校验内容指纹并直接恢复展开配置，不重新采样；`scene.build_scene` 支持该配置内绑定的模板，规划和物理执行读取同一实例布局。

相同 seed、版本、条件和配置得到相同参数/模板/身份，不依赖调用次序、输出路径或全局 numpy RNG。实例保存 seed、draw_seed、attempt、生成器/RNG 版本、固定核心哈希、完整配置和内容指纹。验收失败时最多尝试 8 次，使用原 seed 派生的具名 retry 流，保留每次失败原因；显式指定 family 时重试不会换族。固定代表失败不重复尝试相同几何。

生成结果的 `accepted` 只表示声明的几何/采样 IK 检查通过。`physical_execution` 始终单独记录，本生成入口不运行物理、更不创建数据集。scene reset、可解参考与视频录制均可以消费同一实例，而不是由 Demo 脚本决定随机性。基础 `cast_coil_aloha` 配置仍表示固定基础版；随机入口使用 `cast_coil_variants` 配置。

## 本轮验证与发现的问题

最终[验收汇总](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/validation.json)、[批量报告](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/sampling_report.json)和[回归日志](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/tests.log)分别保留验证层级及源文件指纹。

- 384 个 seed：384 份不同几何配置，倒序重复采样的实例指纹逐项一致；A/B/C 数量分别为 116/143/125。
- 48 个内部/边界几何样本：48/48 通过，包含另外两个 family 的错误路径真实重叠见证。
- 12 个随机实例的完整采样双臂规划：12/12 首次通过，无需重采；三个固定代表也通过规划。
- 55 项回归检查通过；同 seed、调用顺序隔离、条件质量范围、失败记录、恢复及篡改拒绝均有检查。
- 公共 `variant_rng / layout_randomization / variant_episode / episode_spec` 源文件与开发前 SHA-256 相同。

各层结果分别统计，不把 384 次采样说成 384 次机器人或物理成功。以上为有限压力检查，不是整个连续参数域永不失败的证明；运行入口仍逐实例验收并保留拒绝。

开发过程中实际修复：

- 原配置换 seed 不改变场景：增加任务专用采样声明、条件派生、完整实例输出和加载。
- A 大偏心结构接近阶段撞桌：补零件—桌面检查，根据路径计算抬升；保留失败记录，不放宽追踪阈值。
- C 的 0.75 mm 外轮廓增加量产生非水密实体：从首版公共取值域剔除，采用 `{0,1.5}`，重做随机/边界检查。
- B/C 装配被基础版阶段检查误拒绝：按绑定的 family 推导必需阶段；中间错位和 screw 阶段仍不能省略。
- 场景 yaw 变了而抓取方向未同步的问题：使用固定局部抓取参考方向，按当前物体姿态转换。
- 错误被退出时的残留约束信息覆盖：保留原始失败原因，额外记录 cleanup_error。

额外完成三个固定代表各两档时间步的接触后辅助抓持装配试验，**6/6 达到装配、释放和静置目标，但严格归档门槛只有 4/6 通过**。A 的默认步长曾出现最小 SAT 间隙 -0.363 µm，C 的半步长为 -1.264 µm；现有门槛要求全程采样间隙为正，因此仍判不通过，未为这两次试验放宽门槛。B 两档均通过。详见[物理试验汇总与原报告](../../../runs/demo_metadata/cast_coil/2026-09-19_seed_generator_validation_v2/physics_summary.json)。本轮交付的是几何与采样 IK 变体生成器，不把局部物理试验变成全随机域的动力学资格。
