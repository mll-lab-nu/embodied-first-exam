# Cast Coil：固定结构库与数据集随机生成接入审查

后续进展：本文记录的是开发前审查。当前已补 seed 随机实例入口、固定三族核心、条件变换、恢复、桌面余量和 family 装配阶段检查，见[生成器实现与验证](cast_coil_seed_generator_zh.md)；H5/数据集和全随机域物理认证不在本轮范围内。

审查日期：2026-09-19。当前任务目标是 **assemble：两个在 x/y 均分离的自由零件装配、落桌、释放**。本次检查当前工作区，未修改运行时代码、未生成新数据集或重跑机器人动力学。

## 结论与两类变体

设计可以采用“固定结构库 + 条件参数随机化”，已有几何与路径模块可以复用；当前实现还不是已接通的数据集随机生成器。后续应以可保存、可恢复的任务实例为生成器产物，Demo 和数据采集共用实例，视频是可选输出。

| 用户所说的变体 | Cast Coil 的对应内容 | 当前落实情况 |
| --- | --- | --- |
| 预先设计的不同形状 | 三个 family：偏心转动、分段错位、旋转推进；每族的 3/6/9 mm 代表结构 | 有确定模板和对应零件相对路径；九个带可见轮廓的模板仍在实验目录，尚未进入正式固定资产注册表 |
| 形状上的参数随机化 | 厚度、外角轮廓微调、场景 pose、分离间距等 | 有部分几何变换、联动规则和检查器，但无 Cast Coil 的逐实例 seed → 参数 → 验收输出入口；可行范围仍需按当前装配目标认证 |

**选择预制形状不等于重新设计形状。** 可以按 seed 从固定库选择 `family_id / prototype_id`，直接加载该模板和路径；不必每条数据重新做扫掠反推。每个模板内的机制尺寸 theta 可以冻结为身份的一部分。只有显式开启结构设计实验、改变 theta 时，才需要重新合成通道和验收。

现有 `appearance.py` 的 `face_small / depth_thick / corner_cut` 是三份固定 preset。它证明了外观变换与三个具体实例，尚未提供连续随机采样。有限固定库本身也是合法的变体生成方式，不要求所有任务都具备无限或连续的新形状。

“IK family”在这里主要指零件相对运动模式。结构库绑定该模式和构造见证；场景 pose、抓点或尺寸变化后，机械臂关节轨迹要重新求解，不能随机改旧关节角来定义实例。

## 实际复核结果

可复现实验及源文件 SHA-256 见 [report.json](../../../runs/demo_metadata/cast_coil/2026-09-19_variant_pipeline_audit/report.json)；检查脚本为同目录的 [probe.py](../../../runs/demo_metadata/cast_coil/2026-09-19_variant_pipeline_audit/probe.py)。

| 检查 | 结果与含义 |
| --- | --- |
| 当前 `cast_coil_aloha` 配置调用 `build_variant_episode`，seed=0…63 | **64 个不同 ID、1 种场景配置**；无 `variation:`，所有 `variant.parameters` 为空。只换 seed 并不会生成不同实例 |
| 指令和实例快照 | 当前公共入口得到空 instruction；`resolved_config` 仅预留四个配置来源路径，本次未传 sources，因此均为 null。即使传 sources，也不会自动保存完整展开配置和资产 |
| 三个旧 family 核心模板的当前装配路径 | 本次重新计算分离初态、接近路径及反向连续件间几何证书，**3/3 通过**；未重新运行 IK、机器人碰撞或动力学 |
| family 装配阶段与归档契约 | 使用现有报告的合成测试夹具，仅替换 family 与阶段名：A 接受，B/C 拒绝。原因是装配归档固定要求 `assembly_quarter_turn`，而 B/C 正确阶段分别为多次反向转动/错位、反向 screw。测试夹具不是物理证据 |
| 九个可见轮廓代表点 | 读取原报告：几何 9/9、采样 IK 9/9、新结构物理 0/9；原检查是拆解路径，不是当前装配执行。它们不同于本次复核的三个旧核心模板 |
| 当前基础装配视频 | 五路 SHA-256 与归档一致、全部完整解码，均为 663 帧、20 fps、33.15 s；没有新录制，也不能用于认证其他形状 |

复现命令（仓库根目录，零物理步进）：

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv-gs121-nyx/bin/python \
  runs/demo_metadata/cast_coil/2026-09-19_variant_pipeline_audit/probe.py
```

## 接入数据集的具体缺口

1. **固定资产选择与条件采样未接入。** [inverse_design.py](../../../topogym/tasks/cast_coil/inverse_design.py) 是确定的结构合成器，支持家族专属机制参数；[appearance.py](../../../topogym/tasks/cast_coil/appearance.py) 是有限 preset 与路径变换。九代表的外轮廓生成仍在 `runs/.../visible.py`，不能让生产批次依赖临时 run 脚本。需把可复用逻辑和固定模板索引纳入主线，并为每个条目记录实际验收范围。
2. **采样器、场景、规划器尚未共用实例。** [scene.py](../../../topogym/tasks/cast_coil/scene.py) 能读 `template_path / variant / center_xy_m / yaw_deg / initial_xy_offset_m`；但 [robot_plan.py](../../../topogym/tasks/cast_coil/robot_plan.py) 内固定 90° yaw、根位置和抓点，[robot_demo.py](../../../topogym/tasks/cast_coil/robot_demo.py) 又固定布局，不能只随机 YAML 而沿用旧 plan。Python `build()` 默认目标还是 disassemble，CLI 默认才是 assemble；适配层必须显式传任务目标。
3. **装配验收还需按 family 适配。** 修复阶段检查时，应从绑定的已认证路径推导必需阶段，并保留释放、静置和真实目标检测；不能删除阶段门槛来让所有报告通过。几何反向路径有解不代表接触动力学可以倒放，旧拆解视频也不能成为装配物理证据。
4. **Spec 不足以独立恢复。** 共享 [VariantRng](../../../topogym/generation/variant_rng.py) 和 [build_variant_episode](../../../topogym/generation/variant_episode.py) 可复用，但后者记录的只是采样/变更字段与配置来源；当前稳定 ID 不包含资产内容或生成规则版本。需要补完整配置、资产哈希、单位/坐标系、初态、成功条件、控制与物理配置、接受 attempt 和证据身份。保存最终实例，不能要求恢复时重新采样。
5. **数据 writer 尚未对接 ALOHA。** [EpisodeDatasetWriter](../../../topogym/data/episode_dataset_writer.py) 按单个 `hand_pos()/hand_quat()/gripper_qpos()` 读取控制器，而 ALOHA 顶层提供 `arms[left/right]` 与 `state()`，没有这些单臂方法。当前 HDF5 schema 和导出器也采用单末端动作语义；应显式记录左右臂观测、关节/夹爪命令、时间戳与同步相机，不能只包装其中一臂。已有下一帧实测末端位姿动作与真实下发关节命令需区分。
6. **交互 adapter 不等于生成器。** 新 [agent_adapter.py](../../../topogym/tasks/cast_coil/agent_adapter.py) 提供实时操作，但 `create()` 内加载固定配置、Genesis seed=0，不接收随机实例或 EpisodeSpec。它使用无辅助抓持的 pilot evaluator；正式基础 Demo 是接触后辅助抓持。两者应分别记录 execution profile，不能混用资格或成功标签。

## 建议采用的生成契约

以下为接入设计，**接口名称尚未实现**。优先复用公共 RNG、Spec 与任务专用几何/检查器，无需另建一套“Demo 随机函数”。

```text
request(task_id, objective=assemble, seed, generator_version, pool_version,
        family_id=auto, prototype_id=auto, validation_policy)
    → 按具名 RNG 选择固定 family / prototype
    → 从该 prototype 的条件域采参数，派生相互约束的尺寸与 pose
    → 加载/变换模板及相对路径，解析完整场景实例
    → 几何与初态检查 → 机器人规划/碰撞 → 物理与任务验收
    → accepted instance spec + assets + validation report
      或 rejected attempt + reason

同一个已解析实例
    → demo runner → 可选多视角 MP4
    → dataset runner → 同步观测/动作/结果 + 实例身份
```

**固定库与资格。** 保留最初基础版，另注册三个 family 的代表形状；库条目绑定 `template_id + geometry hash + route hash + qualification scope`。当前装配的已完成物理证据仅覆盖最初基础版；其他条目可以作为研究候选注册，但不能标为已批准的装配数据源。缓存只对相同几何、初始化、机器人和物理/控制配置生效；任何变化后按依赖关系重新验收，不能拿旧形状的视频背书。

**参数联动。** 冻结 theta 后，厚度 d 和外轮廓微调 delta 可作为后续候选轴，pose/分离间距另作为场景轴。沿用家族规划中的 `L=6+theta+delta`；C 的推进量必须同步变为 `d*a`。厚度同时缩放两件材料、空隙与路径，轮廓切削还需保留连通性、抓持区域与锁止负对照。此前 `[0.9,1.1]`、`{-0.75,0,+0.75} mm` 是探索域，**不是已认证装配范围**；当前无可直接批准的 pose 随机范围。

**确定性和拒绝。** 使用共享 `choice / uniform / derived / validate`：先选择原型，再把随机比例映射到它的条件范围；验证失败按具名 retry 处理，记录 proposal、派生值、接受 attempt 和拒绝原因。当前公共采样器会重采全部轴，且不返回接受的 retry；若需固定 family 配额，应把该 family 作为请求条件，并在外层显式记 attempt，不能依赖全局接受顺序。跨批次、进程顺序和并行数量改变时，同请求仍应得到相同实例参数与资产身份。

**数据划分。** 按 `prototype_id` 或 `family_id` 预先固定 train/validation/test 分组；同一形状的小 pose 扰动不能假装是未见结构。另设共享结构上的参数泛化划分时，明确其评测目的。seed 不同也不保证形状不同，有限库中的重复是正常的，需要记录结构身份。

**数据输出。** 实例快照与物理动作记录独立于渲染开关；先保证不录视频也能生成、恢复和运行实例。训练数据保留左右臂命令及执行语义、实际观测、终态结果、辅助抓持声明和验证状态。参考解/内部几何见证作为生成验收材料，不能无意加入策略观测。

## 分阶段接通与验收

1. 固定形状库和完整实例快照：先让基线可保存/恢复，再注册 family 候选；同 seed 重复生成一致，不同 seed 按声明选择原型，且不重复结构反推。
2. 从相同实例驱动场景、规划和执行，修复当前装配的 family 阶段检查；逐一完成选定固定形状的装配物理资格。
3. 开放通过验证的条件参数域，检查大批 seed 的覆盖、拒绝率、批次顺序一致性和失败记录。批次数与范围需明确声明；有限抽样成功不能称为整个连续域的证明。
4. 补双臂数据 writer 和 schema/导出适配，至少完成一个无视频依赖的 `seed → instance → execute → dataset → reload` 冒烟闭环；几何、IK、物理各自记录 `passed / failed / not_run`，必需项未运行时拒绝输出“验证成功”的实例。

这四步是从现有模块接入数据集的剩余工作，本次完成的是审查、件间装配路径复核与接口阻塞复现。

## 现有视频证据

基础装配执行版本 `2026-09-18_assembly_baseline`，文件名保留 `2026-09-17_aloha_full`。五路来自同一次物理状态记录的离线渲染，接触后辅助抓持；默认/半时间步通过。本次复核文件哈希与完整解码，没有新增物理执行或随机实例录像。

- [cam_high](../../../demos/cast_coil/cam_high/2026-09-17_aloha_full_cam_high.mp4)
- [cam_low](../../../demos/cast_coil/cam_low/2026-09-17_aloha_full_cam_low.mp4)
- [cam_left_wrist](../../../demos/cast_coil/cam_left_wrist/2026-09-17_aloha_full_cam_left_wrist.mp4)
- [cam_right_wrist](../../../demos/cast_coil/cam_right_wrist/2026-09-17_aloha_full_cam_right_wrist.mp4)
- [front_oblique](../../../demos/cast_coil/front_oblique/2026-09-17_aloha_full_front_oblique.mp4)
