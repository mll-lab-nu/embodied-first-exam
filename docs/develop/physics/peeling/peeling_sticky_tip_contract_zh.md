# Peeling Sticky-Tip / Kinematic Sheet 公约

本文记录 Peeling V1 的稳定实现约定。它的目标不是模拟完整胶层断裂材料学，而是提供一套可复现、可录制、可用于 IL/RL 的接触抽象。

## 当前实现

默认 `grasp.mode: contact_attachment` 使用 sticky-tip 机制：

1. 机械臂末端移动到贴片自由角附近。
2. 末端推算出的 grasp point 与贴片角点距离小于 `physical.attach_tolerance` 时，环境进入 attached 状态。
3. attached 后不再只移动角点 particles，而是由 `PeelingKinematicSheetDriver` 驱动已释放的贴片区域。
4. 未释放区域保持在初始平整位置，代表仍然粘在基底上。
5. 每个 `peel_group_*` 段开始前，环境调用 `release_peeling_groups()` 释放下一条 adhesion band。
6. 已释放区域随末端移动，peel front 附近按 `kinematic_front_blend_fraction` 做平滑过渡，并用 `kinematic_curl_height` 给出轻微卷曲。
7. 全部释放后，整张贴片作为连续薄片搬运到 `placement.center` 附近，再松开并沉降。

关键代码：

- `topogym.tasks.peeling_physical.PeelingKinematicSheetDriver`
- `topogym.primitives.pbd_particle_pinch.PBDParticleAttachmentDragPrimitive`
- `prototypes.peeling_physical_single_demo`
- `configs/task_configs/peeling_physical_single_topogym_tabletop_v1.yaml`

## 为什么这样做

直接让 Franka 指尖夹 PBD 贴片会在 Genesis 1.1.0 中触发不稳定的 rigid-PBD 接触，用户已经在 `corner_descend` 前后复现过 native `Segmentation fault`。只移动角点 particles 虽然能避开 segfault，但会把贴片拉成尖三角，因为其余 particles 仍被固定在桌面上。

`PeelingKinematicSheetDriver` 的作用是把 sticky-tip 变成一个正式环境机制：角点接触只负责触发 attachment，贴片形变由环境里的 deterministic sheet dynamics 负责。

## Demo / IL / RL 一致性公约

Peeling V1 后续所有 demo、实时 RL 训练、IL 数据生成必须遵守以下规则：

1. **同一动力学**
   demo、IL collector、RL env 都必须调用同一个 sticky-tip + kinematic sheet driver。不能在 demo 里额外 teleport 贴片，也不能在训练时换成另一套规则。

2. **动作只控制机器人**
   policy 或 scripted teacher 的 action 只能表达末端运动、姿态、夹爪/吸附命令等机器人动作。不得把 particle index、released group、peel front 作为 action 直接写入。

3. **attachment 由环境判定**
   attached 状态只能由环境根据末端位置、容差和可选吸附命令触发。teacher 可以移动到正确位置，但不能直接设置 `attached=True` 后跳过接触判定。

4. **peel front 是环境内部状态**
   `released_groups`、`released_fraction`、`peel_group_*`、sheet weights 可以用于 reward、terminal、debug log 和 privileged teacher metadata，但默认不进入视觉策略的 observation。

5. **轨迹必须逐步推进**
   贴片不能在普通 step 中瞬间从平整状态跳到目标位置。每一步应先移动机器人，再由 driver 根据当前末端位姿和 released groups 更新贴片。

6. **IL 数据记录真实 action**
   IL 记录的是 teacher 实际发给机器人控制器的动作序列，而不是 driver 内部写 particle 的结果。driver 的状态可以作为 debug/info 保存，但不是 policy action。

7. **RL reward 可看内部状态**
   RL reward 可以读取 `released_fraction`、`lifted_fraction`、`target_xy_error` 等 evaluator 状态，因为 reward 本来就是环境函数；但这些值是否进入 policy observation 要单独声明。

8. **版本标注**
   数据集和视频应记录 `grasp.mode=contact_attachment`、`sheet_driver=kinematic`、`kinematic_front_blend_fraction`、`kinematic_curl_height` 和 Genesis 版本，避免和旧的 direct-contact 实验混在一起。

## 当前边界

这不是纯物理胶层模型，也不是完整双向力耦合。它是一个稳定的任务动力学抽象：机械臂通过接触触发吸附，通过连续运动推进剥离。等后续需要更高保真度时，可以把 sheet driver 替换成更真实的 adhesion/fracture 模型，但 action、observation、reward 的接口应尽量保持不变。
