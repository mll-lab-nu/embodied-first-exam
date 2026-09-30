# 七项任务 terminal 判断与分离任务目标区：工程计划

> 2026-09-29 归档提示：本文涉及的独立研究／诊断／测试入口已移入[统一归档](../../../legacy/research_tools_20260929/README.md)；相关旧路径与命令保留为历史说明，不再是当前运行入口。rollout 准备、执行及 Harbor 工具仍在活动目录。

日期：2026-09-25；接入更新：2026-09-26。状态：独立判据、公共结果、Buzz 子步事件与恢复、六项目标区部署已实现；真实物理资格未通过。当前实施与剩余项见[接入记录](../dev-logs/task_terminal_integration_20260926_zh.md)及第 14 节；前一批见[独立部分记录](../dev-logs/task_terminal_independent_implementation_20260925_zh.md)。

同日修订：按用户补充，核验 Lock 的实体销—滑槽限位；分离类任务采用桌面绿色虚线目标区，成功条件以指定物体完整入区为主。目标区是明确加入的新任务要求，取代前稿中“任意位置分离 / 在线通用拓扑证明”的主判定；旧 demo 的成功标签不追溯更改。

并行会话核对更新（2026-09-25 21:48，America/Chicago）：确认保留每 physics tick 一份完整快照，另汇总 tick 内 solver substep 接触事件；补充 segment 公共结果适配、当前变体范围和共享文件衔接，详见第 11 节。此次仍只修改计划。

依据 `/home/jianwen/topogym` 当前工作区核对；该工作区有其他会话的未提交修改。本文中的“现有”指本次读取到的实现，“拟新增 / 拟修改”指后续工作，不代表已经验证任务成功。本文细化[成功判据与可解性总计划](../dev-logs/task_success_control_and_solvability_plan_20260924_zh.md)中尚缺判据的七项，文件位置以当前 `tasks/<task_id>/common.py` 为准。

## 1. 核心判断：Buzz 的触线失败可以先做

用户提出的 `touch → terminate → failure` 正是合适的实现。现有链路已经成立：

```text
World.advance()
  → Task.update(actual_world_state, physics_dt)
  → evaluate_state 返回 failure="wire_touched"
  → TaskResult(terminated=True, task_success=False, reward=0)
  → Env 保存失败 tick，停止本次 action 剩余 physics ticks
```

对应现有代码：[`tasks/base.py`](../../../topogym/tasks/base.py) 的 `update/get_state/set_state`、[`simulator/env.py`](../../../topogym/simulator/env.py) 的 `step/_save_state/_restore`。失败不经过稳定窗口，也不受 `goal_complete=False` 阻挡。

**即时失败本身不必另加跨 tick 的 `ever_touched` 锁存。** 第一次接触就结束当前分支，现有 `result.terminated/reason/metrics` 已经锁存并进入快照；终止后 Env 禁止继续 step。`metrics.touch=True`、`first_touch_step` 可作为证据一起保存。回溯到触线之前，应恢复“尚未触线”，不能把已作废未来的触线带回新分支；恢复失败 tick 则仍然失败。

只有“触线后仍允许继续跑，最终再判失败”才需要额外的 `ever_touched |= touch_now`。本方案采用即时失败，不引入这种继续执行模式。Lock 的越界诊断也可即时终止无效执行，但它不能替代外环实体限位。真正首先需要历史进度的任务是 Fiber，以及严格验证沿线遍历时的 Buzz。

## 2. 对已有分析的修正

| 原判断 | 当前代码事实与实现影响 |
|---|---|
| 七项都先被公共历史状态阻塞 | 失败即终止已有锁存与恢复；先完成 Buzz/Lock 失败条件，不必等历史扩展 |
| FEM 下 `released()` 恒为 False | 四个 FEM Task 当前继承 `TaskDefinition`，并未调用该方法。`RigidTaskDefinition.released()` 只在 `contacts is None` 时保守返回 False；空的、不完整的 Genesis 接触数组反而可能返回 True。问题是接触覆盖不足，不能把未报告视为释放 |
| 为 Buzz/Fiber 继承 `RigidTaskDefinition` 即可 | 该类还要求 `local_vertices`，带整刚体 AABB、静止及 1 mm 穿透规则。Fiber 是关节链，不能套单刚体变换；应抽取可复用的接触查询，而不是为复用一个方法强行继承 |
| Lock 限位环功能不存在 | 当前源码、生成资产和旧 demo 都有外环弧形槽、锁片耳与销的碰撞结构。新生成资产的静态检查确认销在槽内可通行、越端部 1° 会与外环相交；见 5.2。尚缺当前运行时隔离关节限位后的受力验证，不能把该缺口写成“未实现外圈” |
| `disk_linking_number()` 可直接计开放绳穿盘 | 该函数用 `np.roll` 自动闭合，并返回带符号总和；开放绳会被加上虚构末段，正反两次穿越还会抵消。若保留 Slotted 拓扑诊断须修正；新的目标区终态不再依赖它 |
| Orbits 平面绕数加柱顶裁剪就能证明分离 | 高度裁剪会截断曲线，不能再当闭合曲线绕数使用。新的主判据检查全部绳体和木柄入区，固定器具留在分界另一侧；绕数只作诊断 |

中心线提取确实是小规模公共工作。执行器缺失主要影响阈值标定和完整成功证据，不妨碍实现确定的几何计算、失败条件及合成正反例。

## 3. 统一 terminal 合同

| 情况 | terminated | task_success | truncated | 处理 |
|---|---:|---:|---:|---|
| 合法状态，目标尚未确认 | False | False | False | 继续 |
| 本 tick 触犯任务硬规则 | True | False | False | 立即结束，稳定计时清零 |
| 目标满足约定确认时间 | True | True | False | 成功结束 |
| 仅耗尽时间 | False | False | True | 保留 Env 的 time limit |
| 物理引擎异常、必需读数损坏 | — | — | — | 按现有 Env 故障流程处理，不能冒充普通任务失败或成功 |

同 tick 同时满足目标和失败时，失败优先；目标/失败和时间预算同时发生时，保留现有 terminal 优先。检查器明确知道某证据源暂不支持时，输出 `evaluation_status="unavailable"`，不确认目标；已经声明支持的必需字段丢失则报接口错误，不能默认为零。

沿用当前 reward：运行/失败为 0，成功为 1。本轮不捆绑修改旧总计划中“所有 reward 改为零”的独立提案。

### 3.1 历史状态的最小扩展

在 `TaskDefinition` 增加可恢复的 `task_state`，用于每根 Fiber 的穿越进度等；不另建任务状态管理器，不复制 Env 历史。

拟定接口：

```python
initial_task_state(world_state) -> dict
evaluate_transition(world_state, task_state) -> (
    reached, failure_reason, metrics, next_task_state
)
```

- `evaluate_transition` 是纯计算，不能修改输入、推进物理或抽随机数；默认实现调用既有 `evaluate_state`，返回原任务私有状态，兼容六项已有任务。
- 有历史的任务覆盖该接口；其 `evaluate_state` 提供同一测量逻辑的只读预览，不在查询时提交历史。
- `initialize` 从真实 birth state 建立前一帧采样和初始进度，并检查出生是否合法。已在目标区不能被记录成“曾经穿过”；完整目标已成立的标准初态应拒绝，成功态夹具只用于测试。
- `update` 保留重复 tick 幂等及连续 tick 校验；生成并校验候选结果和 `next_task_state`，最后一次性提交。异常不能留下半更新的进度。
- `get_state/set_state` 深拷贝私有状态，校验字段、数组形状、有限性及 tick 一致性。升级 checkpoint schema 到 2；当前是同进程 episode 快照，旧 schema 明确拒绝，不用空字典假装历史完整。
- 私有历史只保存必要状态，例如 Fiber 每站当前通过状态、前次位置、穿越次序；不每 tick 保存整段接触日志或另一份 FEM 全顶点历史。
- 判据版本 `terminal_revision` 与生效阈值进入实例身份及 episode 元数据；避免相同实例标签在判据改变后含义不同。

`stable_duration_s` 拟允许 0，支持不要求等待的目标首次成立就结束；非零窗口维持现有规则：第一次看到目标为真只开始计时，后续连续 tick 累积，中断归零。失败一直即时生效，与这个扩展无关。

### 3.2 稳定与释放分开

静止可以直接读 FEM 顶点速度、刚体/关节链各 link 速度，不需要 IPC 接触力。**静止不等于已松手，已松手也不等于静止。**

建议基础规则：Buzz“稳放终点”要求支承、静止、释放；Lock/Fiber 不额外要求松手；Rope 的“稳定”先只要求低速连续成立；Knot 采用贴桌的无交叠证据；Slotted/Orbits 等分离任务改为整个指定物体进入桌面目标区，并保留短暂稳定确认。目标区规则本身不要求 IPC 接触力，也不默认增加“必须已松手”；若另行要求放下后释放，再启用同一释放测量。

对确需释放的 IPC 任务，使用保守的几何证据：目标表面与有关机器人碰撞表面间距大于 `release_clearance_m + distance_error_bound_m`；辅助抓持接回后，还须不存在目标上的有效 assist 约束。不能仅看夹爪开口量、TCP 距离、几个最近顶点或 `state.contacts` 为空。表面距离须覆盖线段/三角形内部，包含采样误差；证据不充分返回 unknown，而不是 released。

## 4. 共用几何与接触数据

### 4.1 中心线：声明时建立映射，tick 内仅索引

复用 `utils/geometry/rope.py`，拟增加 `rope_centerline_indices(rest, material_s)` 和 `sample_rope_centerline(fem_state, indices)`。

1. 四项 Task 在 `declare()` 写出 NPZ 后只读一次；从 `rest[:, 1:3] ≈ 0` 找轴点，按其 `material_s_m` 排序。
2. 校验每材料截面恰好一个轴点、材料坐标严格递增、至少两站、索引唯一且与 FEM 顶点身份一致。
3. tick 内用相同索引取实际位置/速度；不按空间位置重新排序，不每次读盘，不用 `spawn` 代替运行态。
4. 运行态已是世界坐标；Rope 环布局须加 table offset，Orbits 须应用自身 yaw/origin，不能重复旋转或遗漏平移。
5. 不依赖 `sides=8`；先不改变 NPZ 格式。将来增加显式 `axis_vertex_indices` 是可选优化，不是本轮阻碍。

### 4.2 穿盘与分离

新增纯几何文件 `utils/geometry/passage.py`，提供开放/闭合参数明确的折线穿盘测量，返回交点列表、材料坐标、方向以及退化状态。闭合时必须由调用方给出有物理意义的闭合路径；不得暗中将开放绳首尾相连。

必须区分：`unsigned_crossing_count`、`signed_crossing_sum`、`ambiguous`。共面段、切触、边界交点和零长段不能默认为无穿越；失败/不成功与“暂时不确定”也要区别。有限环厚与绳半径必须进入余量计算，中心线过了无限薄平面不自动代表整根穿过实体孔。

分离类任务改用 4.4 的完整入区规则，不再把通用拓扑识别或在线搜索退出路径作为上线前置条件。`solvers/collision/triangle_meshes.py` / `convex_compounds.py` 继续用于区域布置、机械限位和其他任务的几何验证；旧的穿环/绕数工具可作诊断，但不能覆盖目标区这个新目标。

### 4.3 接触语义与时间覆盖

`World.read_state()` 拟保留现有 contacts 字段，增加几何身份与数据覆盖信息。已安装 Genesis 的 collider 查询包含 `geom_a/geom_b/position/normal`，当前 World 只导出了 `link_a/link_b/force/penetration`；先扩展输出，优先避免为辨认材质而拆分刚体。

- `contact_observation` 标明来源、覆盖的实体对和采样时间范围。IPC 的 `contact_ownership` 已可用于说明哪些接触不归 Genesis 报告；它本身不是接触查询结果。
- Buzz 资产给碰撞形状标注稳定角色：导线、端点挡块、托架、工具金属环/杆、手柄。bind 阶段解析为运行时 geom ID；确认 Genesis 导入后仍可可靠对应，不把生成文件顺序当永久编号。
- 公共纯查询放 `evaluation/task_metrics.py`，只读取状态及角色表，任务自己决定哪些接触违规。

还有一个独立于历史锁存的边界：当前 Task 每个 physics tick 调用一次，默认一个 tick 内有 4 个 solver substeps。Genesis 接触缓存会更新/清理；tick 末 contacts 不是“这 4 个子步所有接触”的证明。

因此分两级交付：先实现 **观察到违规接触就立即失败**；严格“全程无触线”要求 World 在子步级汇总违规接触事件，tick 返回后由 Task 终止。必要时新增 `world/physics/rigid_contacts.py`，通过受控的场景实例适配收集事件，不修改全局 Genesis 类、不复制 simulator 循环。须先确认可用扩展点；若没有可靠接口，明确保留这项缺口，不能仅靠末帧接触就宣布全程检测完整。瞬时事件缓存进入 World checkpoint，并在 reset/rewind 正确恢复；`read_state()` 不能消费或清空事件。子步采样也不声称连续时间 CCD 保证，另以时间步敏感性测试界定实际能力。

用户确认的存储方式是 **每 tick 完整快照＋该 tick 的子步接触摘要**，不将 `step_snapshot` 替换成完整 `substep_snapshots` 数组，也不增加子步 rewind。默认一次 action 最多 10 个 physics ticks，每 tick 2.5 ms，内部 4 个 solver substeps；当前 Task 已经每 tick 更新。摘要至少区分接触对象/几何身份、首次观察到的子步及实际采样覆盖。采集发生在 `World.advance()` 内的可靠求解扩展点，Task 在 tick 末消费只读摘要；此处“即时失败”是发现违规的该 tick 终止，不承诺在 solver substep 中途停止。

### 4.4 分离类任务：绿色虚线目标区

按用户要求，把目标改成“将指定物体的所有部分放到绿色虚线区域内”。这是明确的空间任务，已脱离但尚未入区的状态继续运行。无需证明任意位置下的复杂拓扑解开，也不要求沿参考路线到达。

**区域定义与可达性。** 每个实例声明一个桌面上的有向矩形，记录中心、朝向、长宽、有效边界余量和相对桌面的允许高度范围。判定体是矩形上方的有限高度棱柱，不是无限高的 XY 投影；只把物体举到区域上空不能通过。高度范围按目标物体实际厚度、合法摆放姿态和误差设置，不能统一用一个过薄高度带。

区域须完全位于桌面可用范围内，与装置、机器人底座及固定障碍有间距，并能容纳完整目标及夹爪接近空间。按当前 robot profile 验证可行的放置姿态、接近/撤离路径；仅以 TCP 到基座的距离或一个 IK 解宣称“可达”不够。复杂绳体须验证完整绳体与木柄确实可摆进区域。区域可针对 seed/变体确定性选择，但一旦 reset 完成就固定，不随目标移动；无有效区域的实例拒绝或重新采样，不能放宽判据补救。

**可视化与 agent 指令。** 在桌面绘制绿色虚线边框；由同一份区域参数生成图形和计算边界，明确虚线内沿为有效范围，避免视觉与判定差半条线宽。标记使用 visual-only 网格/贴面，关闭碰撞，轻微抬升只为避免 z-fighting；不能让虚线成为绳子的物理障碍。RGB、录像、reset 和 rewind 显示同一固定区域。

任务说明同时提供：`将【明确列出的目标组件】整体放入绿色虚线区域，包括所有突出部分；其余装置组件保持在装置一侧。` Orbits 明确写“整根绳和木柄”，不能只写“把手柄放进去”。通过 `Task.observe()` 的公开 `instruction/goal_region` 字段交给普通 agent；更新任务卡，不以隐藏的判据坐标替代可见提示。区域数据是公开静态目标信息，不额外开放其他物体的特权真值。

**完整包含，而非中心点检查。** 将目标几何变换到区域坐标系，要求全部实体几何满足矩形与高度边界：

```text
abs(u) <= half_width  - boundary_margin
abs(v) <= half_depth - boundary_margin
table_z - penetration_tolerance <= z <= table_z + placement_height
```

- 刚体：全部碰撞几何及突出的实体部分，包含各 link 的实际变换；网格可检查全部顶点，解析曲面采用精确边界或保守外包。不能只查根位置、质心或 link 原点。
- FEM：全部体网格顶点，包括端部加粗/挡结，不只查中心线或两端；对于当前线性四面体与凸目标区，全部顶点入区足以覆盖单元内部。少数顶点出界也不算完成，不用 p95 替代“所有部分”。
- 永久相连的移动件：纳入同一 `target_entities`；如 Orbits 的 cord 和 handle。附着损坏、绳体失效不能因为剩余碎片入区而成功。

**防止整套系统一起拖入区。** “区域远离系统初始位置”只够静态布置，Slotted 的绳/珠/端片等仍会运动。每个区域同时声明一个水平分界方向 `n` 和边界 `b`，保证整个有效目标区处在 `n·x >= b + separation_margin`，其余装置组件的完整几何处在 `n·x <= b`。固定组件的条件可初始化时验证并缓存，活动组件每 tick 检查。桌面、机器人和绿色标记不属于“剩余装置”集合。

这样在线只需完整包含和另一侧的 min/max 边界检查，即得到明确空间分离；不需要链接数、柱绕数或接触力查询。若其余系统被拖到分界之外，该 tick 不成功，允许 agent 恢复摆放；不能只检查“其余物体的中心不在绿区”。分界与间距进入公开任务说明/区域配置，不设一个 agent 无法知晓的额外成功区。

最终候选为 `all_target_inside && remainder_on_system_side && required_connections_intact`，再经过该任务明确设置的短暂稳定窗口。目标区模式不是“已松手”的证据；本轮按完整入区简化判断，不偷偷追加接触力门限。需要几何释放的任务仍遵守 3.2 的单独定义。

**适用范围。** 本轮七项中首先用于 Slotted 和 Orbits。共享目标区同样用于分离任务 Cast Keyhole、Horseshoe Ring、Hedgehog in Cage、Interlocked Claws 的新判据版本，并在 5.8 列出目标集合；它们的迁移是此次用户要求带来的扩展。Buzz、Lock、Fiber、Rope、Knot 保留各自插入/穿环/无交叠目标，不因出现“移动”就改成入区任务。

## 5. 七项具体判据

### 5.1 Buzz Wire

**失败：** 合法接触事件涉及工具规定的金属部分和金属导线，立即返回 `wire_touched`，指标包含 `touch_now`、接触角色、首次 tick、力和穿深。力用于诊断，不先设任意的“超过 0.05 N 才算触线”；轻触同样违规。接触候选、安全距离与实际触碰的区分，按引擎接触距离语义及明确的数值容差实现，不靠连续多帧去抖而允许短触线。

**对象必须先分清：** 当前 `wire` link 同时含导线和端点挡块；木制挡块在外观生成中也可确认。`wand` link 同时含金属环/杆和手柄。不能把整个 `wand × wire` 接触都当“金属环碰金属线”。建议允许木挡块和托架支承，禁止金属环/杆触导线；这是本文提出的角色规则，应写进任务卡，而不是按 link 名隐式决定。

**成功：** 到达 `endpoint_pose(route, 1)` 对应的终点支承范围、环保持合法穿套关系、确有终点支承、静止且释放，持续现有 1.0 s。不能只判断工具原点离 `rail[-1]` 近。导线路径有靠近/交错区域时，进度须结合实际环孔与上一合法路线段，不能只用最近采样点；允许回退，不要求复刻 planner 的动作。

出生测试先检查正常托架接触和导线接触是否可区分。`initialize()` 遇到真正触线应拒绝；如果正常出生被判失败，修正角色或初态，不加“前 N tick 碰线豁免”。本次未做真实出生接触实测。

最小补丁可以先只交付失败条件，保留 `goal_complete=False`；完整成功、角色识别和时间覆盖完成后再移除 goal gap。

### 5.2 Lock Picking

**核查结论：用户描述的实体外圈限位已经存在，并已接入当前场景声明。** 它不是“允许转过去，然后用 terminal 判失败”的替代品。

实现链路如下：

1. [`assets/geometry/lock_picking.py::slot_profile/ring_limit_assets`](../../../topogym/assets/geometry/lock_picking.py) 生成有圆形端帽的弧形槽。外环由显式凸碰撞块拼成，保留槽与中心孔，不把整个环凸包化。
2. 同一生成器给锁片添加两段耳和一根轴向销；销有真实 collision，随 `disc_hinge` 绕 `-x` 转动，沿外环槽移动。销头有些外观部分不碰撞，不影响穿槽销本体的 collision。
3. `write_disc()` 把耳/销碰撞写入锁片 link，并为有限角度盘保留 URDF revolute limit；360°盘是 continuous joint，无人为角度端点。
4. [`tasks/lock_picking/common.py::declare`](../../../topogym/tasks/lock_picking/common.py) 加入固定的 `lock_frame_0/1/2`，与对应锁片使用相同装配原点。`fixed=True` 固定 URDF 基座，不会把子 link 的铰链锁死。当前声明未关闭这些实体的碰撞；外观处理只替换 visual。

**与旧 demo 对照。** 归档 [`implementation/_staged_lock_ring.py`](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/implementation/_staged_lock_ring.py) 中的 `slot_profile`、`ring_limit_assets` 与当前函数的 AST 完全一致；这两段实体限位实现被保留了。旧 [`implementation/scene.py`](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/implementation/scene.py) 实际加载了 `lock_stop_frame_1/2/3`，旧 [`source_config.yaml`](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/source_config.yaml) 使用 `single_ring` 并开启关节限位。旧 [`result.json`](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/source_evidence/result.json) 记录成功；归档 [`physics_equivalence.json`](../../../runs/demo_metadata/lock_picking/2026-09-18_standard_150mm_purple_trace_v1/physics_equivalence.json) 记录外观重渲染保留了碰撞、质量、惯量和关节。这支持“旧 demo 确实使用了该结构”，但不单独证明阻挡力全部来自槽端。

**本次新增的静态几何核验。** 用当前 registry 的默认 Task 重新生成资产，解析最终 URDF，以实际销网格和外环碰撞网格做 FCL 相交查询；结果写入[核查报告](../../../legacy/cleanup_20260929/runs/research/terminal_judgement_20260925/lock_stop_audit.json)，含实际源码 SHA-256：

| 当前盘 | 配置范围 | 槽内采样 | 越过端部 1° | 外环 collision 数 |
|---|---|---|---|---:|
| `lock_disc_0` | −15° 至 35° | −14°、10°、34°：不相交 | −16°、36°：销与环相交 | 559 |
| `lock_disc_1` | −10° 至 75° | −9°、32.5°、74°：不相交 | −11°、76°：销与环相交 | 559 |
| `lock_disc_2` | 360°连续槽 | −360° 至 360°的 7 个采样：不相交 | 无角度端部 | 369 |

17 个采样符合预期。槽内销与环的最小表面距离约 1.49–1.50 mm。检查没有使用 URDF 关节限位或 `evaluate_state`，所以确认了几何本身有挡住有限转角的实体槽端；它是静态离散几何证据，不是一次新的 Genesis 受力实验，也不证明所有角度连续无干涉。

**当前配置不等同旧 demo。** 旧标准 demo 盘距 150 mm、第一盘范围 −15° 至 15°；当前 registry 默认类虽然名为 `standard_150mm`，实际生成的 `pitch` 是 85 mm、第一盘范围 −15° 至 35°。F1/F3 等另有各自具名参数。这个差异不影响“外圈代码仍在”的结论，但不能将旧成功轨迹直接当当前默认实例已复验；默认实例命名/参数对齐应另列场景核对项。

**后续验收要求：机械限位优先，越界检查只做完整性保护。** 增加真实受力对照：在测试专用场景副本中关闭关节限位、保留实体销/槽，向两端施加有限持续转矩，观测销—外环接触和角度阻挡；反向转矩应能退回槽内。再用移除销或槽碰撞的测试副本证明相同转矩能越过原范围。关闭 terminal 越界提前停止对该机制试验的干预，防止“试验停止”被误当“机械挡住”。这些修改仅作用于测试副本，生产场景继续保留双重约束。按 bounds/缩放覆盖当前注册的 easy/medium/hard（含 F1/F3）及默认实例，并做时间步复验和 rewind。F2 `two_unequal` 已移入 `tasks/legacy`，不恢复注册、不作为活动任务上线前置；若借用它的特殊角度作几何反例，应直接构造参数夹具，不从 legacy 导入运行实现。

有限盘越出 bounds 加数值容差时可返回 `rotor_limit_exceeded`，作为约束失效诊断，不能以添加这个失败条件就关闭机械限位缺口。第三盘是 continuous joint，累计角度超出 `[-180°, 180°]` 不算违规；限位检查使用关节自己的坐标约定。

**建议插入定义：** 前端有效榫片的后表面越过 END 板的出口面并留出余量；杆轴对孔、横向偏移满足孔径间隙，跨盘厚范围内的全部榫片满足实际槽形 clearance。这个定义比“尖端刚过无限薄平面”明确，也不要求三个榫片全部穿到 END 后面。若任务最终选择另一深度，只改有名参数与测试，不埋进坐标常数。

从钥匙实际 SE(3) 位姿变换局部尖端/榫片几何，先测共轴及倾角，再使用 `LockGeometry.clearance()`；该函数的简化深度/转角模型不能独自排除钥匙斜插、侧移或从旁边绕过盘组。允许握持，建议成功等待为 0。

元数据要分清 `physical_rotor_frames=True`（已有结构）与“当前实体限位受力验证通过”。现有 `rotor_stops_complete=False` 混合了过载/退出资格的缺口，拟拆成明确的结构存在、机制验证和终态判据状态；不能继续用一个 False 表达“外圈没实现”。`effort=2` 的 URDF 字段不能当成实测负载证据。

### 5.3 Fiber Bundling

从 `fiber_<strand>_<segment>` link 的位姿和局部胶囊端点重建每根细芯，包含最末端点；不能只检查 link 原点。当前固定的是 terminal，细芯根部在可动工作护套上；任务范围为全部细芯及分叉处/前护套过环，尾部 lead 保持连接，不要求把固定 terminal 穿过环。

采用“尖端到根部有序穿孔 + 当前整根在出口侧 + 未过度弯折”的组合，避免整根绕到环外侧也被判完成：

- 每站跨越环厚对应的入口/出口边界时，验证穿越位置在缩小了半径余量的孔内，并按材料顺序推进。
- 不能只存 `tip_passed/root_passed` 两个 bool；中间材料段可能从孔外绕过。保存每段/站进度及必要的前帧位置；同一 tick 多个站通过时按插值穿越时刻排序。
- 允许正常回退重试：当前通过前沿在退回时回退，不将一次倒退自动定义成永久失败，也不能保留已退出细芯的“完成”标签。
- 弯折采用相邻实际切线夹角或扣除静态安装姿态后的关节 bend，不能把绕线轴的 twist 当作折弯。先检查初态弯折范围。

建议 `maximum_bend_deg=60` 仅作待标定候选；当前过度弯折先阻止成功，除非任务明确定义它为不可逆损伤，才改为即时失败。允许抓持，不额外加释放窗口。

### 5.4 Rope Threading

按固定材料顺序提取中心线，取得实际环的世界位置和法线。复用 `route_crossings()`，要求完整带符号序列恰为 `R1− / R2+ / R3+`，拒绝漏环、错序、反向和多余穿越；材料起点固定，不能事后倒置数组凑目标。

几何上模糊的切触/共面不成功，绳径、环厚和孔边余量要明确。全部参与绳顶点速度达到稳定条件并保持 0.5 s；首版不把“松手”加入“稳定”的含义。这项判据在最终状态中即可观察材料顺序，不要求把所有穿环事件都锁存。

### 5.5 Knot Untying

按用户的“绳不再自我交叠”采用操作性终态：绳位于桌面附近、XY 投影没有非相邻材料段交叉/重叠、绳径余量有效，并短暂停稳。贴桌条件让这个保守证据对应桌面上摊开的绳，不把空中近竖直绳的退化投影视为解开。

已有 `projected_crossings()` 只报横截交点，不处理所有共线重叠、投影塌缩与厚绳接近；需补非局部二维线段距离、退化检测及材料邻接排除。数学上某个非退化无自交投影是有用的充分证据，但现有函数返回 0 不等于已经获得这种证据。报告必须标成“贴桌无交叠终态”，不声称任意三维开绳拓扑识别。

`table_height_m` 在该 Task 的 declare 中也要正确保存；不能沿用基类 0。空中已解开但尚未进入该证据范围的情况暂不成功，应作为保守漏判说明。

### 5.6 Slotted Post Ring

目标改为：将整个移动环放入绿色虚线区域。`target_entities` 只包含该环；立柱、底座、全部绳体（含端部挡结）、珠和端片属于剩余装置，保留绳与端片的永久连接。

主判据按 4.4：环全部实体几何在目标区允许体内；剩余装置保持在分界另一侧；永久连接完整；环短暂停稳 0.5 s。环的位置和几何用耦合器写回的实际位姿，不用环心/物体原点入区代替整体入区。

绳、珠、端片可以在解谜中移动，但不能跟随目标一起进入分离区域。每 tick 的剩余装置边界检查处理这一点；只检查固定柱或其初态包围盒不够。开放绳穿盘次数可作调试指标，不再要求实现通用拓扑证明才能上线该终态。

### 5.7 Orbits

目标改为：将 **全部绳体 + 木柄** 一起放入绿色虚线区域。两端附着木柄的约束必须保持完整；固定组合包含四环、五柱、挡球和有关支承。

在线直接检查全部 FEM 顶点和木柄完整几何入区，并短暂停稳 0.5 s。固定器具与区域之间的分界/间距在初始化验证；若未来变体允许器具移动，则恢复每 tick 检查。只要一段绳尾、木柄角或端连接未满足条件，就不能成功。

因此不再需要“按柱顶高度裁剪绕数”来决定成功：即使已经翻过挡球，也要继续移入目标区；只移动木柄、绳仍在四环之间则不会通过。现有绕数/链接数仅保留诊断，不参与覆盖完整入区条件。

### 5.8 其他分离任务共用目标区

以下四项已有判据，但按此次用户提出的新任务形式同步列入迁移计划；新区域目标通过新 `terminal_revision` 区分。旧 demo 仍按旧目标记录，不能直接升级为“已完成入区”。

| Task | 应完整入区的对象 | 保留在装置侧的对象 |
|---|---|---|
| Cast Keyhole | 场景中明确标注的活动解锁件及其全部实体部分 | 配对的另一件 |
| Horseshoe Ring | `target_ring` 整环 | 两个马蹄、链和所有保留连接件 |
| Hedgehog in Cage | `hedgehog_ball`，包含所有尖刺 | 笼体及支架 |
| Interlocked Claws | 场景生成时指定并在指令中标明的目标爪整件 | 另一只爪 |

对于两个自由刚体组成的系统，必须固定目标身份，不能在快成功时临时交换“目标/剩余件”。Claws 此次按用户的新要求增加入区步骤，覆盖旧“只需分离、不加搬运”的任务约定；仍保留短暂停稳并允许握持，不额外加松手。它们分别修改自身 `common.py` 和任务说明，不改 Cast Coil 的拼装目标。

## 6. 参数与验证证据

参数放各 Task `defaults` 的具名 `terminal` 块，几何相关参数按实际半径/缩放计算；汇总到报告，不新增一份平行的阈值注册表。确认时间继续用现有 `stable_duration_s`，避免两个来源。

| 参数 | 第一版建议 | 状态 |
|---|---|---|
| Buzz 触线 | 合法物理触碰，禁止用较大力门限忽略轻触 | 数值接触容差须实测 |
| Lock 终端深度 | 前端榫片完整穿过 END 出口面 + 余量 | 本文建议定义 |
| Lock 限位容差 | 按 solver 角度误差单独配置，360°盘豁免有限限位；不能替代实体销/槽 | 实体几何已核验，独立受力验证待做 |
| Fiber 最大 bend | 60°候选，检查实际初态与可达成功过程 | 待校准，不作为已验证值 |
| 低速 | 现有刚体 1 mm/s、0.02 rad/s 可作比较起点；软体用全顶点最大速度，兼报 p99 | 待正例标定 |
| 目标区位置/尺寸/朝向 | 按桌面、robot profile、目标完整尺寸及变体布局确定，固定到当前实例 | 用户已确定目标区方案；具体布局待可达性验证 |
| 目标区高度/边界余量 | 允许完整摆放、排除高空投影，含网格/数值容差与可视边框内沿定义 | 每任务显式配置 |
| 装置与目标区间距 | 用共同分界及完整几何支持范围保证；不是从物体中心量距离 | 初始化验证；活动剩余件每 tick 复查 |
| 几何 release 余量 | 只供另行要求释放的任务；显式 m 单位并加距离近似误差，可先试 2 mm | 目标区模式不依赖这项 |
| 稳定时间 | Buzz 1.0 s；Rope/Knot/Slotted/Orbits 0.5 s；Lock/Fiber 建议 0 | 有等待的项先沿用当前默认 |

桌面高度带、孔径余量、插入余量单独命名，不复用一个“万能 epsilon”。模型半径随变体缩放；数值误差与物理目标间距分别记录。

验收分三层：

1. **纯逻辑：** 合成状态与几何正反例，验证坐标、符号、阈值、历史状态，不能记作机器人成功。
2. **真实机制：** 正常出生、一次轻触、隔离关节限位后的销—槽实体阻挡、目标区可达性/可见性、当前物理接触归属、真实速度与回溯；使用标准 Env 和共享 recording，记录实际源码/配置/资产哈希。静态 FCL 资产检查与这个层级分别报告。
3. **完整成功：** 执行器接回后，从标准初态连续运行到终态，用真实正例校准阈值、记录漏判和任务完成证据。不得把手工摆出的成功态或历史视频写成新框架 solved。

`goal_complete` 表示声明范围内的判据实现完整，和执行器是否找到解分开报告。严格规则仍有已知缺口（例如 Buzz 子步漏检、变体终态未定义）时继续保留相应 gap。完整规则和测试覆盖完成后逐任务更新，不等七项一起解除，也不删除独立的 assist gap。

## 7. 拟修改 / 新增文件

| 文件 | 动作与职责 |
|---|---|
| `topogym/tasks/base.py` | 私有状态与纯 transition 钩子、schema 2、零等待、初态校验、terminal revision；`observe()` 提供公共目标区/任务说明；保留失败优先/每 tick 幂等 |
| `topogym/tasks/{七个任务}/common.py` | 实际规则、角色绑定、局部几何缓存、中心线索引、任务 metrics 与参数；easy/medium/hard 等文件通常继承即可 |
| `topogym/tasks/{cast_keyhole,horseshoe_ring,hedgehog_in_cage,interlocked_claws}/common.py` | 用户新要求扩展：明确目标/剩余组件，接入目标区、实例指令和新 terminal revision |
| `topogym/evaluation/task_metrics.py` **新增** | 可复用接触过滤、静止、几何释放，以及完整目标/剩余组件实际几何取样；没有目标 registry，没有状态锁存 |
| `topogym/utils/geometry/rope.py` | 轴点索引与运行态中心线取样 |
| `topogym/utils/geometry/passage.py` **新增** | 开放折线穿有限孔盘、逐交点列表、材料顺序和退化处理 |
| `topogym/utils/geometry/regions.py` **新增** | 有向矩形/高度范围的完整包含与分界检查；纯几何，接收全顶点或保守几何界 |
| `topogym/assets/geometry/goal_region.py` **新增** | 由同一目标区参数生成绿色虚线 visual-only 标记，返回 `EntitySpec` 所需资产；不导入引擎 |
| `topogym/assets/geometry/buzz_wire_3d.py` | 给原碰撞形状增加语义身份/生成映射；优先保持实体结构、几何和外观不变；若导入器不能保留身份，再评估分 link |
| `topogym/assets/geometry/lock_picking.py` | 本次核验已有实体限位，无需为“补外圈”重写；仅真实机制验收发现问题时定点修改，测试使用独立副本 |
| `topogym/world/genesis_world.py` | 导出 geom ID、位置/法线、接触覆盖信息；必要时接入 tick 内事件汇总 |
| `topogym/world/physics/rigid_contacts.py` **条件新增** | 严格 Buzz 所需子步事件收集，先确定 Genesis 实例扩展点 |
| `topogym/world/state.py` **条件修改** | 若新增 Python 事件缓存，显式进入 World capture/restore；已有引擎数值 buffers 不能自动覆盖任意 Python 状态 |
| `topogym/simulator/env.py` | 主要复用 step/rewind；元数据增加判据版本/生效参数和目标区身份，内部证据按需读取 metrics，不另建 Env 循环 |
| `topogym/simulator/segment_contract.py` | 适配本次 Task 的评估状态、明确失败与判据版本；不能只用 `goal_evaluation_complete` 推导所有结果，保留公共信息边界 |
| `topogym/simulator/evidence.py`、`privileged.py` **按需修改** | 复用通用嵌套状态导出；核对新事件/判据状态的覆盖说明，不将刚体子步接触标成完整 IPC 接触 |
| `configs/task_cards/{六个分离任务}.yaml` | 更新完整入区目标和目标组件说明，与运行时公共指令保持同源；不能只改旧卡片而遗漏 `Task.observe()` |
| `topogym/config/registry.py` | 按任务更新 `_goal_gap`；失败判断已实现不代表成功判据完整 |
| `tests/unit/test_task_state.py` | 私有历史深拷贝、schema、重复 tick、失败优先、零等待、原子恢复 |
| `tests/unit/test_task_support.py` | 维持 goal_complete 与 catalog 一致；增加不完整判据仍可失败的断言 |
| `tests/unit/test_terminal_geometry.py` **新增** | 中心线、开放/闭合交点、正反抵消、刚体变换、共面/切触、表面间距误差 |
| `tests/unit/test_goal_region.py` **新增** | 中心入区但边角/尖刺出界、单个 FEM 顶点出界、悬在高空、系统整体拖入、旋转矩形、边界容差、目标身份、旧未来失效 |
| `tests/unit/test_lock_stop_geometry.py` **新增** | 固定环/销碰撞资产、真实 joint 轴向与装配、槽端/槽内及 continuous 特例；覆盖多组 bounds/缩放 |
| `tests/unit/test_terminal_<task_id>.py` **新增七个** | 七项最小正例、近似成功反例、必要历史；另为四项已有分离任务补目标区回归，共享构造器放 `tests/unit/terminal_fixtures.py` |
| `tests/contracts/test_env_lifecycle.py`、`test_episode_rewind.py` | 扩展真实事件语义夹具：动作中途失败、失败后 step 拒绝、回到接触前恢复、旧未来失效 |
| `tests/contracts/test_segment_execution.py`、`test_segment_artifact_access.py` | 在现有 segment 实现上补充明确失败/评估不可用/判据版本的输出适配，以及事件日志与 rewind 一致性；不复制执行器 |
| `tests/integration/test_task_terminal_runtime.py` **新增** | 真实出生/触线/限位/终态确认与 rewind 机制验证 |
| `tests/integration/test_lock_rotor_stops.py` **新增** | 关闭关节限位仍被实体槽挡住、去掉碰撞后不再被挡、反向可退、时间步和 rewind；不以 Task 提前终止代替阻挡 |
| `tests/runtime_evidence.py` | 报告每 tick 判据证据、接触来源、阈值/目标区、完整包含与剩余装置边界、判据版本和限制；沿用录制模块 |
| `scripts/test_base_tasks.py` | 增加 `--checks terminal` 分组，沿用现有进程隔离、报告/录像/源码快照；不恢复旧 bootstrap |
| 七项任务及四项扩展任务说明、`docs/develop/tasks/README.md`、`tests/README.md` | 同步完整入区的新目标、Lock 结构存在/机制验收区分、命令和证据等级 |

`rope_volume.py`、`world/physics/fem.py`、`world/physics/ipc.py` 目前已提供本轮所需中心线来源、速度和附着诊断，不因“公共层”三个字全部重写。初期也不需要新增 planner、改机器人控制，或恢复 `environment_bootstrap` 执行框架。若 assist 会话增加可恢复抓持状态，本轮读取其统一状态，避免重建第二套释放真值。

## 8. 完成后的相关目录结构

以下是实施后的目标结构，`+` 为新增，`~` 为修改，`?` 为满足条件才新增/修改；未列出的现有文件保留。任务沿用已经部署的分目录结构。

```text
topogym/
├── topogym/
│   ├── tasks/
│   │   ├── base.py                              ~
│   │   ├── buzz_wire_3d/common.py                ~
│   │   ├── lock_picking/common.py                ~
│   │   ├── fiber_bundling/common.py              ~
│   │   ├── rope_threading/common.py              ~
│   │   ├── knot_untying/common.py                ~
│   │   ├── slotted_post_ring/common.py           ~
│   │   ├── cast_keyhole/common.py               ~ 目标区迁移
│   │   ├── horseshoe_ring/common.py              ~ 目标区迁移
│   │   ├── hedgehog_in_cage/common.py            ~ 目标区迁移
│   │   ├── interlocked_claws/common.py           ~ 目标区迁移
│   │   └── orbits/common.py                      ~
│   │       # 各目录原有 easy/medium/hard/具名变体继续继承 common
│   ├── evaluation/task_metrics.py               +
│   ├── utils/geometry/
│   │   ├── rope.py                              ~
│   │   ├── passage.py                           +
│   │   ├── regions.py                           +
│   │   └── rigid_geometry.py                    # 保留原闭环接口
│   ├── solvers/collision/                       # 复用现有求距离实现
│   ├── assets/geometry/
│   │   ├── buzz_wire_3d.py                      ~
│   │   ├── goal_region.py                       +
│   │   └── lock_picking.py                      # 外圈/销实现已存在
│   ├── world/
│   │   ├── genesis_world.py                     ~
│   │   ├── state.py                             ?
│   │   └── physics/rigid_contacts.py             ?
│   ├── simulator/
│   │   ├── env.py                              ~ 增量适配既有 tick/state sink
│   │   ├── segment_contract.py                 ~ 公共评估结果适配
│   │   ├── evidence.py                         ? 复用既有通用导出
│   │   └── privileged.py                       ? 接触覆盖说明
│   └── config/registry.py                       ~
├── tests/
│   ├── unit/
│   │   ├── test_task_state.py                   ~
│   │   ├── test_task_support.py                 ~
│   │   ├── terminal_fixtures.py                 +
│   │   ├── test_terminal_geometry.py            +
│   │   ├── test_goal_region.py                  +
│   │   ├── test_lock_stop_geometry.py           +
│   │   └── test_terminal_<task_id>.py           + 七项及扩展回归
│   ├── contracts/
│   │   ├── test_env_lifecycle.py                ~
│   │   ├── test_episode_rewind.py               ~
│   │   ├── test_segment_execution.py            ~
│   │   └── test_segment_artifact_access.py      ~
│   ├── integration/
│   │   ├── test_task_terminal_runtime.py        +
│   │   └── test_lock_rotor_stops.py             +
│   └── runtime_evidence.py                      ~
├── configs/task_cards/<六个分离任务>.yaml         ~
├── scripts/test_base_tasks.py                   ~
├── docs/develop/tasks/
│   ├── terminal_judgement_engineering_plan_20260925_zh.md
│   ├── README.md
│   └── <七项任务及四项扩展任务>_zh.md             ~
└── runs/test_results/<terminal_run>/
    ├── source_hashes.json
    ├── <task_id>/report.json
    └── <task_id>/branch_*/                       # 共享 recording 产物
```

## 9. 实施顺序与各步交付

| 步骤 | 内容 | 可独立验收的结果 |
|---|---|---|
| P0 | Buzz 接触角色、birth 实测、tick/子步时间覆盖；Lock 实体销/槽生成与旧 demo 对照（本次已完成静态核查） | Buzz 一次违规接触即失败；Lock 已有结构与尚缺机制实测分别报告 |
| P1 | 私有历史 schema、中心线、几何交点；共享目标区完整包含、标记与 agent 指令 | 状态回溯、材料身份、入区边界可单测；区域位置先做布局/可达性验证 |
| P2 | Buzz 完整目标、Lock 插入目标及隔离关节限位后的实体阻挡验收、Fiber 全材料段有序通过 | 每项正反例；Lock 不能以越界判失败代替机械槽阻挡 |
| P3 | Rope → Knot；Slotted/Orbits 和四项已有分离任务接入同一目标区机制 | 目标完整入区、剩余装置不跟随入区；无需先完成通用拓扑解缠判断 |
| P4 | capability/catalog/任务文档/运行证据逐项同步，执行器可用后做真实正例标定 | 判据实现、真实机制、完整 solved 分别报告 |

关键反例必须包含：Buzz 只碰木托架/木挡块、轻触导线、同 tick 到终点又触线、子步中短触后离开；Lock 关节限位关闭后槽端仍挡住、槽内可运动、连续盘不误限位、侧向绕过、倾斜尖端越线；Fiber 漏一根/孔外绕行/退出后重试/同 tick 多站穿过；Rope 正反两次抵消/额外穿环/错误材料方向；Knot 共线重叠/近竖直投影/抬绳。

目标区重点反例：环心入区但边缘出界；刺球中心入区但尖刺出界；Orbits 木柄和大部分绳入区但一小段仍在四环中；Slotted 将未解开的环、绳、珠和端片一起拖入；目标高悬在区上方；非目标件入区；连接断开后碎片入区；视觉边框与实际边界错位；区域越过桌沿/被底座占据/夹爪无法放置；回溯后目标区或目标身份改变。旧拓扑工具的开放/闭合曲线反例继续属于几何工具测试，不作为绿色目标区模式的额外上线条件。

单元测试和合同测试先跑；后续新增 runtime 分组必须在详细报告与实际录制接好之后运行。没有可用 GPU 时提供明确 CLI，不把静态测试写成物理通过。

## 10. 本次实际交付与核对

初版新增本计划并在任务文档索引添加入口；本次修订更新 Lock 证据、目标区规则、扩展任务及脚本/目录清单，没有修改运行时代码、实际绘制目标区或启用任何任务的成功资格。

为核实“即时失败、动作中途终止、rewind 已经有基础支持”，运行了现有测试：

```bash
.venv-gs121/bin/python -m pytest -q \
  tests/unit/test_task_state.py \
  tests/contracts/test_env_lifecycle.py \
  tests/contracts/test_episode_rewind.py
```

初版结果：**20 passed**。这是现有状态机/Env 合同夹具的验证，本次文档修订未重复运行；不含新判据测试，不含 Buzz 真实接触、IPC 释放或七项真实成功局。

本次另外执行了 Lock 当前默认 Task 的资产生成/URDF 解析、两个函数与旧 demo 的 AST 对比和 **17 个静态销—外环几何采样**；全部符合预期，详细结果及源码身份见 `runs/research/terminal_judgement_20260925/lock_stop_audit.json`。未运行新的 Genesis 动力学/独立转矩实验，未声称新的机器人成功局。目标区的具体位置、大小和可达性留待实现阶段按实际场景验证。

## 11. 与其他会话的改动衔接

本节按上述时间读取共享工作区、相关本地会话记录与实施文档。工作区存在大量未提交及未跟踪文件，Git 差异本身不能准确归属到某个会话；以下区分当前源码、他方计划和本轮拟改内容，不代表其他会话此后不会继续修改。

### 11.1 核对结论与范围

| 相关会话 / 依据 | 当前事实 | 对 terminal 实施的影响 |
|---|---|---|
| segment 执行与录制，`01a0db3a-1141-7153-9075-6df2cdb1f999`；[实施记录](../dev-logs/simulator_segment_implementation_20260925_zh.md) | 已新增逐 tick state sink、普通反馈过滤、segment 日志、执行期间权限保护；真实验收仍在进行 | 时间粒度兼容，但 `env.py` 是共享修改点；公共评估结果需要显式适配，见下文 |
| 变体整理，`01a0d4eb-f813-7513-8aab-3c6601df6b3e`；[部署记录](variation_deployment_implementation_20260925_zh.md)、[归档说明](../../../legacy/cleanup_20260929/topogym/tasks/legacy/README.md) | 15 个表外入口已归档；Keyhole/Buzz 默认改指 easy；Orbits 默认仍是 reference85；主三档仍有未完成构造 | 沿当前注册实例补判据、区域布局和测试；不恢复旧入口、不把 common 判据完成误当占位档可运行 |
| Harbor / planner / assist，`01a0d03b-84d8-7090-a9f7-dc68c5e4f5fb`；[Harbor 计划](../../../legacy/cleanup_20260929/docs/develop/modules/harbor_shared_image_pipeline_plan_20260925_zh.md)、[assist 计划](assist_integration_engineering_plan_20260925_zh.md) | 主要是接入计划；统一 assist 尚未接入，Harbor 计划不代表 worker 已实现 | 当前没有第二套已实现 terminal 与本计划竞争；未来共享 World 生命周期、恢复状态与结果语义，提前约定而非现在重写 |

整体没有要求推翻本计划的架构冲突。已经发现一处具体输出适配缺口、一处本计划过期的变体范围，以及若干必须增量衔接的共享文件。

### 11.2 segment：同一 tick，只采一次状态，再判定、保存和导出

当前 `Env.step()` 在 `world.advance()` 后读取 `world_state`，传给 `Task.update()`，再交给 `_save_state(world_state=...)`；后者保存 World/Robot/Task 快照，提交 state ID，再调用 state sink 输出 `tick_record`。保持此顺序，以及新加入的 `_mutation` / `_execution_guard` 权限与重入保护。

子步接触收集必须发生在 World 内、上述读取之前。不能放进 state sink：sink 被调用时本 tick 的 Task 判定已经完成；也不能在 sink 里再推进物理或重新调用 Task。新摘要由这一份 `world_state` 同时进入判据与日志，避免两边看到不同事件。

`EpisodeState.task` 和当前证据编码器可以容纳嵌套状态，新增私有任务状态不要求重建 history 或 recording。Task checkpoint 升到 schema 2，不等于外层 TickRecord 也必须使用同一版本号；分别维护各自契约。新增 Python 接触摘要仍须进入 World capture/restore，重复查询和 rewind 后查询都不能消费它。保留 `ipc_contact_coverage=False`，另行描述刚体接触的采样时点、子步覆盖和遗漏范围。

### 11.3 已确认的输出适配缺口：判据完整性不等于本次结果是否明确

当前 `segment_contract.public_info()` 完全由 `goal_evaluation_complete` 推导 `evaluation_status` 和 `task_success`，忽略输入的独立评估状态。本次用两个纯函数输入实测：

| 输入 | 当前公共输出 | 本轮需要支持的语义 |
|---|---|---|
| 成功判据尚不完整，但 `termination_reason=wire_touch`、明确失败 | `evaluation_status=unavailable`、`task_success=None`、原因统一为 `task_terminal` | 保留成功判据不完整的事实，同时能够表达已确认失败 |
| 声明判据完整，但本次 `evaluation_status=unavailable` | 被重新写成 `available`、`task_success=False` | 保留本次证据不可用，不能转成正式失败分数 |

第二行是为拟新增接口构造的适配反例，当前 Env 尚未导出该独立字段，不是声称已有真实运行误判。第一行不影响 Env 实际终止，但公共使用方无法区分明确失败和不可评估。

实施时一起对齐 `TaskResult → Env._info() → public_info() → segment/未来 verifier`：分别表达规则实现完整性、本次证据可用性、已确认终态；明确失败不能仅因成功判据未齐而丢失。具体字段和版本在同一接口改动中确定，公共层只透出允许的结果/原因码及判据版本，不能为修正这一问题直接公开原始接触、隐藏 metrics 或 checkpoint。现有 segment 计划已经明确要求适配将来的 Task 状态与版本，因此是预期扩展。

目标区公共说明没有同样的过滤问题：当前 `Interaction.step/observe` 保留 observation，`SensorSuite` 调用 `task.observe()`。按本计划让 Task 提供公开目标区/对象说明即可；补合同测试确认 agent 能看到，避免新增重复观察通路。

### 11.4 变体、目标区和 assist 的衔接

Lock F2 已归档，前文已修正验收范围。Buzz 的出生接触与终点支撑要以当前默认 easy/F1 重新测量；不能用旧 default 的测量覆盖新的默认。目标区按实际实例布局验证，尤其 Orbits `base=reference85` 与 hard 的 75% video-v2 不是同一实例。当前主三档为 29 个具体构造、9 个待设计占位和 1 个准备流程阻塞，占位不能因父类启用 `goal_complete` 就获得运行或 solved 资格。

六个分离任务新增目标区会改变成功终态：后续恢复旧 planner 时，需要执行到完整入区；“旧策略执行完毕”不能替代新 Task 成功。这属于任务目标与策略的版本衔接，不是要求 terminal 会话现在实现所有 planner。新 `terminal_revision` 与目标区身份应追加到既有实例/证据身份中，保留变体会话已有的 family、model、资源哈希及不可用原因。

assist 计划也会修改 `world/genesis_world.py`、`world/state.py` 和 `simulator/env.py`。后续用同一 World 恢复机制分别保存接触摘要与 assist manager 状态；不让两边各自替换 `scene.step` 或维护第二套抓持真值。要求释放的任务必须同时核对实际辅助约束已解除与相应物理释放条件；允许保留抓持的目标区任务不因此新增统一放手要求。子步内“曾经接触”的并集只能证明发生过接触，不能直接当作 assist 所需“双指同时且持续接触”的证据，后者须保留足够的时间信息。

### 11.5 实施顺序与本次检查边界

可以先做 `tasks/base.py` 私有历史、中心线/区域几何、任务规则与合成状态测试。接入共享文件时，在 segment 当时的源码上小范围修改 `_info`、元数据和接触读数，不用计划编写时的旧 Env 整份覆盖；同步完成公共结果适配与 segment 回归，再做固定源码快照的机制验收。无需等待 Harbor 或所有 planner 完成。

本次读取到的默认时序仍是 `physics_dt_s=.0025 / solver_substeps=4 / control_decimation=10`。其他会话对执行成本的实验配置不能自动成为 terminal 验收默认；即使内部 solver 步长相同，改变 physics tick 长度也会改变 Task 检查、事件归组和可回溯点的频率。报告记录实际三项配置，不只记录 action 频率。

本次只更新本文及其脚本/目录清单，没有修改运行代码、覆盖其他会话文件或运行新的动力学测试。除读取源码与文档外，只执行了上面两个 `public_info()` 纯函数探针；它们证明当前适配行为，不表示本轮新判据或其他会话最新代码已通过验收。

## 12. 现在可独立实施的清单

这里“独立”指不依赖 segment 会话完成，不表示以下工作包彼此没有依赖，也不表示它们可以单独获得完整运行验收。按 A/B/C → D/E 实施，保持既有 Env 调用方式和 TaskResult 外部字段。下表保留拆分时的范围；当前交付与剩余接入见第 13 节。

| 工作包 | 修改文件 | 新增文件 | 本阶段交付与边界 |
|---|---|---|---|
| A：Task 私有历史与恢复 | `topogym/tasks/base.py`；`tests/unit/test_task_state.py` | 无必需新增模块 | transition 纯计算、私有历史初始化/深拷贝/校验、原子提交、Task checkpoint schema 2；失败优先、重复 tick 幂等及零稳定等待回归。复用现有 Env 保存 Task 字典的方式，暂不改公共结果投影或 episode 元数据 |
| B：中心线、穿环与公共测量 | `topogym/utils/geometry/rope.py` | `topogym/utils/geometry/passage.py`；`topogym/evaluation/task_metrics.py`；`tests/unit/test_terminal_geometry.py` | 缓存轴点索引、开放曲线逐交点/材料顺序、完整几何取样及低速测量。接触过滤只计算给定数据，不负责取得 Genesis 子步事件；缺失证据不能当成没有接触 |
| C：目标区几何和可视资产 | 无必需修改的运行模块 | `topogym/utils/geometry/regions.py`；`topogym/assets/geometry/goal_region.py`；`tests/unit/test_goal_region.py` | 完整包含、有限高度、剩余组件分界、同源绿色虚线资产；可先用合成布局验收。真实区域坐标、可达性、视觉导入和碰撞关闭仍需后续场景验证 |
| D：七项任务规则 | 下表七个 `common.py` | `tests/unit/terminal_fixtures.py`；下表七个测试文件；`tests/unit/test_lock_stop_geometry.py` | Task 内判据、历史和参数接线，合成状态正反例；Lock 静态限位回归。暂不解除注册表的完整成功 gap，Buzz 全子步无漏检和真实出生等仍待接入验证 |
| E：四项已有分离任务的新目标候选 | 下表四个 `common.py` | 下表四个测试文件，复用 `terminal_fixtures.py` | 新目标区规则、对象范围和公开说明生成可先实现测试；正式替换现有成功规则、启用新 revision 与更新外部指令放到接入阶段，避免中途把旧成功资格配给新规则 |

任务文件逐项如下；每行测试路径均以 `tests/unit/` 开头，均拟新增：

| 工作包 / 任务 | 修改的任务文件 | 新增测试文件 |
|---|---|---|
| D / Buzz | `topogym/tasks/buzz_wire_3d/common.py` | `test_terminal_buzz_wire_3d.py` |
| D / Lock | `topogym/tasks/lock_picking/common.py` | `test_terminal_lock_picking.py` |
| D / Fiber | `topogym/tasks/fiber_bundling/common.py` | `test_terminal_fiber_bundling.py` |
| D / Rope | `topogym/tasks/rope_threading/common.py` | `test_terminal_rope_threading.py` |
| D / Knot | `topogym/tasks/knot_untying/common.py` | `test_terminal_knot_untying.py` |
| D / Slotted | `topogym/tasks/slotted_post_ring/common.py` | `test_terminal_slotted_post_ring.py` |
| D / Orbits | `topogym/tasks/orbits/common.py` | `test_terminal_orbits.py` |
| E / Keyhole | `topogym/tasks/cast_keyhole/common.py` | `test_terminal_cast_keyhole.py` |
| E / Horseshoe | `topogym/tasks/horseshoe_ring/common.py` | `test_terminal_horseshoe_ring.py` |
| E / Hedgehog | `topogym/tasks/hedgehog_in_cage/common.py` | `test_terminal_hedgehog_in_cage.py` |
| E / Claws | `topogym/tasks/interlocked_claws/common.py` | `test_terminal_interlocked_claws.py` |

本批不必修改 Lock 现有几何，也不改 easy/medium/hard 参数入口或恢复 legacy。Buzz 的几何接触角色映射可以先定义并用夹具测试；资产导入身份与真实接触事件导出放在同一接入批次确认，不能靠普通 `wire` link 数据伪造更细的语义。

**留给接入批次的文件：**`topogym/simulator/env.py`、`segment_contract.py`、按需修改的 `evidence.py / privileged.py`，以及 `topogym/world/genesis_world.py`、`world/state.py`、拟新增 `world/physics/rigid_contacts.py`。World 接触能力本身并不依赖 segment 执行器完成，可以先独立研究 Genesis 扩展点；把实际修改放到接入批次，是为了统一接触数据、恢复和日志契约。

`topogym/config/registry.py`、`tests/unit/test_task_support.py`、公共合同测试、`tests/runtime_evidence.py`、`scripts/test_base_tasks.py`、六个分离任务的 task cards 及正式任务说明随接入/资格切换同步更新。独立批次运行既有合同测试检查兼容性，不修改 segment 的实现或专用测试。

## 13. 独立工作包实施后的接入边界（2026-09-25 历史状态）

A—E 的实现、精确文件清单和验收结果集中记录在[实施记录](../dev-logs/task_terminal_independent_implementation_20260925_zh.md)，本节只列仍需接线的部分。

| 剩余功能 | 拟改/新增文件 | 与 segment 的衔接 |
|---|---|---|
| Buzz 几何角色、子步事件及恢复 | 修改 `assets/geometry/buzz_wire_3d.py`、`world/genesis_world.py`、`world/state.py`；条件新增 `world/physics/rigid_contacts.py` | 在 World 求解子步收集，本 tick 读取前形成只读摘要；Task 消费，Env 保存同一 tick，state sink 再导出。不能由 segment 日志回调补采样 |
| 公共结果语义与判据身份 | 修改 `tasks/base.py`（正式 revision/结果字段）、`simulator/env.py`、`simulator/segment_contract.py`；按需修改 `evidence.py`、`privileged.py` | 明确失败、本次证据可用性、规则完整性分开；将正式 revision/阈值/目标区身份写入已有 metadata 和日志，不复制执行器 |
| 六项分离任务目标区实例化与正式启用 | 修改六个 `tasks/<task>/common.py`、六项 task cards；复用已新增的 `assets/geometry/goal_region.py` | 固定实例区域并完成布局/可达性验证后，在 declare 加标记，在 observe 转发公开说明；evaluate_state 调用候选规则，并通过原 Task.update 计稳。segment 直接沿用 observation 和 terminal |
| 能力注册与真实机制资格 | 修改 `config/registry.py`、`tests/unit/test_task_support.py`、`tests/runtime_evidence.py`、`scripts/test_base_tasks.py`；新增两项 integration 测试（见第 7 节） | 在固定源码上验证出生/触线/限位/目标区/rewind，使用现有 segment/recording 证据链。逐项解除 gap，不把本轮合成成功态变成 solved 标签 |
| 对接回归 | 增补既有 Env/rewind/segment 合同测试 | 验证失败在本 tick 停止剩余 action、失败优先、contact_events 与私有历史随 rewind 恢复、公共结果不丢失明确失败 |

本批已经跑既有 segment 合同以检查兼容，但没有修改 `simulator/` 或 `world/`。七项未完成 Task 仍为 `goal_complete=False`；四项旧分离 Task 的原成功条件保持有效，新增 `evaluate_goal_region(state, region)` 只是候选版本。绿色资产生成器已经可用，尚未向标准场景自动插入任何区域。


## 14. 2026-09-26 接入实施与当前边界

本节覆盖第 11—13 节中“尚未接入”的历史状态；实际结果和源码身份见[接入记录](../dev-logs/task_terminal_integration_20260926_zh.md)。沿用 segment 已完成的 `policy.act(obs)` / `obs.execution_state`，不引入第二个执行循环。

- `world/physics/rigid_contacts.py` 已新增。Buzz URDF 给 collision 形状命名语义角色；World 在 Genesis build 的 COM 重定位**之前**按 link、形状、局部位姿和网格资源匹配角色，再以稳定 geom ID 采集。无法匹配时明确不完整，不猜导入顺序。
- 采集器包装当前场景实例的 `rigid_solver.substep`；已核对安装源码中的纯刚体快捷路径和 legacy 混合路径。每个已执行子步清除查询缓存后复制 narrowphase 结果；负 penetration 候选不计触碰，零力但已接触仍计触碰。tick 末覆盖计数、几何角色覆盖、每条事件子步号进入 `world_state.contact_events`。不覆盖 IPC，不声称 CCD。这个适配器仍需真实 Genesis 接触试验验收。
- `WorldState.contact_events` 保存/恢复摘要；读取不消费事件。Task 在 tick 末判定，Env 停止 action 剩余 ticks，已有 state sink 写出同一份测量及 Task 结果。保留每 tick 完整快照，不增加 solver substep rewind。
- `TaskResult.evaluation_status`、`Env._info()`、`simulator/interaction.py::public_info` 已接通。`goal_evaluation_complete`、`evaluation_status`、`task_terminated/task_outcome` 分别表达成功资格、当次可评估性和结果；明确失败可以在 `goal_complete=False` 时公开。公共失败码仅 `wire_touched/task_failed`，详细接触和 metrics 仍在管理方证据。
- 新增 `tasks/placement.py`，Env 在 `declare` 后、资产哈希与 World build 前调用 `finalize_spec`。六项任务部署固定区域并调用完整入区规则；区域基于实际桌面、剩余系统包围几何、目标尺寸和机器人底座确定性选择，计入实例身份。区域、有效阈值及资格状态进入 episode metadata；绿色虚线和判断使用同一个区域对象。这个布局通过不等于放置路径可达。
- `simulator/rollout_simulation/policy.py` 默认将 `Task.public_instruction()` 接入政策 observation profile。limited 模式获得 RGB 绿色边界和静态物体说明，不自动获得区域数值坐标或目标物体真值。显式管理方 instruction 覆盖仍按已有 profile fingerprint 契约处理。
- 六项任务卡已更新；Claws 指定棕色件，Orbits 明确整绳与木柄。四项旧分离任务改用 `placement_region_v1` 后不继承旧资格；连同七项原未完成任务均保留 solve gap。已知失败仍正常 terminate，不受成功资格开关阻挡。

当前目录新增/改动集中如下（未列的独立几何/任务判据文件沿用上一批）：

```text
topogym/
├── tasks/
│   ├── base.py                          # 结果可用性、判据身份、实例完成钩子
│   ├── placement.py                     # 新增：六项固定目标区部署及公共指令
│   └── <11 个任务>/common.py            # revision、区域接线及任务说明
├── assets/geometry/buzz_wire_3d.py      # 碰撞形状语义命名
├── world/
│   ├── genesis_world.py                 # 采集器接入及出生/恢复
│   ├── state.py                         # 快照保存 contact_events
│   └── physics/rigid_contacts.py        # 新增：当前场景子步采集适配器
├── simulator/
│   ├── env.py                          # fixed region、metadata、公共结果源
│   ├── interaction.py                  # 公共结果过滤
│   └── rollout_simulation/policy.py    # 默认静态任务指令
└── config/registry.py                  # 新规则资格与缺口
configs/task_cards/<6 个分离任务>.yaml
tests/
├── unit/test_rigid_contact_events.py                 # 新增
├── unit/test_terminal_public_outcomes.py             # 新增
├── unit/test_terminal_region_deployment.py            # 新增
├── contracts/test_{segment,scripted_policy}_execution.py
├── integration/test_terminal_runtime.py              # 新增：13 个机制/接线用例
└── runtime_evidence.py                               # 记录 Task/接触摘要/判据 metadata
scripts/test_base_tasks.py                           # 新增 --checks terminal
```

尚需完成的是资格，不再是等待 segment 接口：Buzz 真实出生、短暂触线、木托/终点支承与时间步敏感性；Lock 去掉关节限位后的销槽正反向受力与无环负对照；六区真实视觉和机器人放置/接近撤离路径、完整绳柄容纳；各任务真实正例、阈值标定，再按具体实例解除 solve gap。已提供机制入口，但机器人解题策略和放置路径验证器没有在本轮凭空补齐。当前 CUDA 驱动不可用，实跑记录明确为未执行物理验收，不能报告 solved。
