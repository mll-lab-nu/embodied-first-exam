# 当前 13 类任务的 success 条件

核对日期：2026-09-30。以当前源码默认 easy/medium/hard 为准；Lock 为 `terminal_v4_bore_contact_default_success`，保留 v3 的孔壁接触判据。下面描述实际判据，不把历史 demo 目标、开发计划或机器人可解性当作当前条件。自定义参数以实例保存的有效配置为准。

## 公共终止规则与开关职责

[TaskDefinition.update](../../../topogym/tasks/base.py) 只有在 `goal_complete=True`、本任务全部条件满足、必需证据 available、无失败且连续达到确认时间时才输出 `task_success=True / reward=1 / terminated=True`。首次满足的 tick 记作窗口起点，后续连续 tick 累计时间；中途失效清零，明确失败优先，终止结果锁存。缺失必要读数不能当作成功。

当前 13 类任务的所有已集成变体统一默认启用成功判据，继承或显式使用 `goal_complete=True`；Keyhole/Hedgehog 不再通过资格 property 控制开关。`goal_complete` 及兼容字段 `goal_evaluation_complete` 只表示成功判定已启用，不表示当前局已成功或实例已经物理验收。sample 有效性仍由生成/建场检查，必要读数是否齐全由 `evaluation_status` 表达。

资格匹配仅保留在管理方 `terminal_metadata().qualification` 中，附历史证据和范围；不再把命中记录直接转换为当前实例的 `thresholds_calibrated=True` 或 `reachability_qualified=True`。registry 已移除因缺少物理资格而设置的 `solve` 阻塞项，未实现变体和辅助抓持限制仍保留。修改启用逻辑的任务已更新 terminal revision，使旧 checkpoint 不会被当作新规则的实例恢复。

## 六类完整放置任务的共同条件

以下 Claws、Hedgehog、Horseshoe、Keyhole、Slotted、Orbits 共用 [placement.py](../../../topogym/tasks/placement.py)、[placement_candidate](../../../topogym/evaluation/task_metrics.py) 和 [GoalRegion](../../../topogym/utils/geometry/regions.py)：

- 所有目标几何点完整处于固定绿色目标体积内；刚体使用登记的视觉及碰撞几何，软体使用全部体积顶点。不是只检查中心点。
- XY 必须在框内再留 **1 mm**；高度在桌面以下最多 **1 mm** 到该实例目标体积上界之间。体积高度由实例生成；这里没有额外的“必须接触桌面”条件。
- 剩余全部部件的几何必须留在固定分界线的系统侧。目标区域生成时与系统侧至少分隔 **30 mm**，部分任务配置可要求更大距离；框和分界线不会跟随物体移动。
- 目标刚体线速度 ≤ **1 mm/s**、角速度 ≤ **0.02 rad/s**；目标软体所有顶点速度 ≤ **1 mm/s**。不要求剩余部件都静止。
- **允许继续抓持，不要求释放，不检查公共释放后的漂移窗口**。
- Claws/Horseshoe/Hedgehog/Keyhole 保留刚体失败保护：非有限状态、任何任务物体低于桌面 100 mm、读到相关接触穿透超过 1 mm 会失败。Slotted/Orbits 使用其软体与连接完整性检查。

### 1. Interlocked Claws（默认开启）

完整棕色目标爪进入目标区，另一件及剩余部件留在系统侧，满足上述目标速度条件，持续 **0.5 s**。当前代码已不是仅检查“两爪分开一定距离”。允许抓持。

源码：[interlocked_claws/common.py](../../../topogym/tasks/interlocked_claws/common.py)。

### 2. Rope Threading（默认开启）

- 按绳的材料坐标排列孔面穿越，easy 必须恰好是 **R1− → R2+**；medium/hard 必须恰好是 **R1− → R2+ → R3+**。正负号相对各环登记法向；不能少穿、多穿或方向错误。
- 使用实际环位姿；有效孔半径扣除环管半径、绳半径和 **0.1 mm** 余量。
- 环中心面和厚度两侧面均检查穿越，数量/方向符合规则且无模糊交点；名义孔径下的穿越数量也须一致。
- 全绳顶点速度 ≤ **1 mm/s**；IPC 原生有效，绳体积诊断有效且最小体积比 > 0。
- 持续 **0.5 s**。不要求释放。此处是现有三平面实现，不是完整绳体与环实体碰撞的独立认证。

源码：[rope_threading/common.py](../../../topogym/tasks/rope_threading/common.py)。

### 3. Lock Picking（默认开启；已修孔壁接触判据）

- 钥匙朝穿入方向；钥匙杆在四片板的前后面均通过孔。对倾斜杆使用保守截面半径 `shaft_radius / cos(tilt)`，孔内最大径向超出量允许 **10 μm（0.01 mm）** 的数值接触误差。不再要求额外 0.1 mm 空隙，也不再单独限制倾角 ≤ 1°。
- **有限长度**钥匙杆必须仍覆盖三片转盘和 END 的全部厚度，并考虑倾斜截面在杆端的轴向范围；不能只剩杆尖穿过 END。
- 最前齿的保守后缘超过 END 外侧至少 **1 mm**。
- 三个齿与正在重叠的板槽无非法角向干涉；检查包含倾角和轴偏移引起的额外角度余量。
- 有限行程转盘不能超出配置上下界超过 **0.5°**；全周旋转盘不套有限行程限制。钥匙掉到桌面下 100 mm 或无效状态不得成功。
- 连续 **0.5 s**。**没有速度门槛，不要求松手**；这里连续保持几何条件不等于物体完全静止。

10 μm 是覆盖现有三档已记录末态约 2.82/2.94/5.87 μm 误差的窄容差，不代表对所有引擎配置完成标定。保留 `thresholds_calibrated=False`。旧指标 `coaxial` 保留为兼容别名，含义是孔内几何检查通过；新诊断包括 `shaft_bore_clear`、`shaft_bore_excess_m`、`shaft_through_all_plates`。

版本改为 `terminal_v3_bore_contact`，新参数名为 `shaft_contact_tolerance_m`。旧 `maximum_tilt_deg` / `shaft_clearance_m` 配置不能直接送给新判据并冒充旧运行；新建实例应使用新默认值。重算历史记录时显式替换 terminal 配置并另记结果，不更改旧 manifest、任务身份或成绩。

源码：[lock_picking/common.py](../../../topogym/tasks/lock_picking/common.py)。[原始状态重算结果](../../../runs/test_results/lock_contact_fix_20260930_01/replay.json)：4789 个状态、三档末态通过，原来通过的状态没有被新增有限杆检查拒绝。此为离线重算，没有新增物理执行或生产 success。

### 4. Hedgehog in Cage（默认开启）

球体和**全部尖刺**完整进入固定目标区，笼体及其余部件留在系统侧；满足共同放置条件持续 **2 s**。允许抓持。随机 seed、参数和历史资格匹配不再控制成功开关。

源码：[hedgehog_in_cage/common.py](../../../topogym/tasks/hedgehog_in_cage/common.py)。

### 5. Fiber Bundling（默认开启）

- 所有细芯按材料顺序、尖端先行通过铜环，不能只把终态坐标放到另一侧；判据保存穿越历史。
- 通过判断位于环自身平面，两个历史判定面间距 **1 μm**；采用的径向分界为孔半径加环管半径。通过后每个材料采样点还必须超过出口侧的“环管半径 + 芯半径”。这不是在入口最前面先卡死孔径。
- 分叉端的前护套也必须具有通过历史，且按护套半径计算完全越过出口；固定后端不要求穿过。
- 任意相邻细芯段的最大弯折角 ≤ **60°**。
- 从初始化起，接触事件的子步和几何角色覆盖必须完整；夹爪任何一次接触细芯立即失败，包括没有明显接触力的触碰。
- 条件保持 **0.5 s**；没有单独速度或释放门槛，可抓粗护套。后端固定由场景机构实现，判据没有独立“锚点残差阈值”。

源码：[fiber_bundling/common.py](../../../topogym/tasks/fiber_bundling/common.py)。

### 6. Horseshoe Ring（默认开启）

可移除目标环完整入区，其余系统留在系统侧，目标满足速度条件；**永久链/眼连接的每条边都必须保持绝对 linking number = 1**，丢失则失败。持续 **0.5 s**，允许抓持。

源码：[horseshoe_ring/common.py](../../../topogym/tasks/horseshoe_ring/common.py)。

### 7. Knot Untying（默认开启）

- 材料中心线的 XY 投影无交叉、重叠、退化段或共线折返；非局部段间距至少一个绳直径，材料相邻部分按算法豁免距离要求，但真实投影交点不豁免。
- 全部绳体顶点高度在桌面 **−1 mm** 至桌面加 **绳直径 + 3 mm** 之间。
- 全部顶点速度 ≤ **1 mm/s**，IPC 和体积诊断有效。
- 必须解除 assist，机器人与绳体有可验证的至少 **5 mm** 间隙；确认窗口内所有顶点相对参考状态漂移 ≤ **1 mm**。
- 上述条件共同保持 **0.5 s**。这是“无投影交叉并贴桌”的几何规则，不是独立计算数学结型不变量。

源码：[knot_untying/common.py](../../../topogym/tasks/knot_untying/common.py)、[公共释放确认](../../../topogym/evaluation/terminal/settling.py)。

### 8. Cast Coil（默认开启）

- 当前三档均固定 `objective=assemble`：两件按建模原点校正后的相对位置误差 **< 1 mm**，相对旋转误差 **< 0.02 rad**。
- 两件线速度 **< 1 mm/s**、角速度 **< 0.02 rad/s**；没有有效抓持接触（刚体旧检查的力门槛为 0.05 N），且必须通过公共释放确认。
- 装配模式至少一件底部距桌面 ≤ **3 mm**，两件底部均不低于桌面 **1 mm**；每件 XY 包围盒与桌面范围有交叠。代码不是要求整个组合都贴桌，也不是完整包含在桌面 XY 内。
- assist 已解除，机器人离两件均至少 **5 mm**；确认期间位置漂移 ≤ **1 mm**、转角漂移 ≤ **0.02 rad**。
- 共同保持 **0.5 s**。保留刚体状态/掉落/穿透失败保护。

基类还实现 `disassemble` 分支：两件包围盒分离量 > **10 mm**，且两件底部都接近桌面；当前三档不允许把 objective 改成该分支。

源码：[cast_coil/common.py](../../../topogym/tasks/cast_coil/common.py)。

### 9. Cast Keyhole（默认开启）

完整银色件进入固定绿色区域，金色件和其余部件留在系统侧，目标满足共同速度条件，持续 **0.5 s**。允许抓持，不要求最终释放。资格匹配只影响历史证据元数据，不控制成功开关。

源码：[cast_keyhole/common.py](../../../topogym/tasks/cast_keyhole/common.py)。

### 10. Buzz Wire 3D（默认开启）

- 金属环从导线起点沿整条路线通过，保存连续路线进度。起终点弧长容差 **10 mm**，相邻进度跳变不得超过 `2 × 位姿移动量 + 3 mm`；不能直接摆到终点算完成。
- 从初始化起，子步接触和角色覆盖完整；任何金属环/杆与金属导线触碰立即失败。木柄接触不属于此禁触规则。
- 已完成遍历后，工具实际位姿距预设终点支承姿态 ≤ **5 mm**、角误差 ≤ **10°**；考虑工具绕手柄轴半圈对称。
- 工具与终点支承存在接触；无机器人持握接触，assist 已解除，机器人离工具至少 **5 mm**。
- 线速度 ≤ **1 mm/s**、角速度 ≤ **0.02 rad/s**；确认期间位移 ≤ **1 mm**、转角漂移 ≤ **0.02 rad**。
- 最终条件持续 **1 s**。遍历完成历史可在工具放到 deck、脱离最后孔面交点后保留；仅终点姿态不能制造该历史。

源码：[buzz_wire_3d/common.py](../../../topogym/tasks/buzz_wire_3d/common.py)。

### 11. Blanket Flatten（默认开启）

- 布料三角形在桌面 XY 的实际投影覆盖面积 / 原布长宽面积 ≥ **90%**；不是简单包围盒面积。
- 最高粒子距桌面 ≤ **30 mm**，最低粒子不低于桌面一个 `particle_size_m`（当前默认 **8 mm**）。
- 任意材料边的长度 / 原长 ≤ **1.15**，不靠过度拉伸得到覆盖率。
- 最大粒子速度 ≤ **30 mm/s**；assist 已解除，机器人与按粒子尺寸扩展的布料包围范围至少 **5 mm** 间隙。
- 确认窗口内每个粒子相对参考状态漂移 ≤ **3 mm**；全部条件保持 **0.5 s**。
- 非有限粒子状态或布料低于桌面 100 mm 失败；冻结初态若已经满足原始展平判据，初始化拒绝。

源码：[blanket_flatten/common.py](../../../topogym/tasks/blanket_flatten/common.py)。

### 12. Slotted Post Ring（默认开启）

整个可移除金属环进入目标区；绳、左右端片、珠子、立柱等其余部件留在系统侧，目标满足共同速度条件。IPC 原生有效、绳体积比有效，`cord_disc_left/right` 的连接残差各 ≤ **2 mm**。持续 **0.5 s**，允许抓持；连接/体积损坏会失败，IPC 缺失则不可评估。

源码：[slotted_post_ring/common.py](../../../topogym/tasks/slotted_post_ring/common.py)。

### 13. Orbits（默认开启）

**整根绳的所有体积顶点和完整木柄**一起进入目标区，其余环和支架留在系统侧。绳和木柄满足共同速度条件；IPC/体积有效，`cord_handle_start/end` 两端连接残差各 ≤ **2 mm**。持续 **0.5 s**，允许抓持。只把木柄拉出、绳仍留在环中不够；没有把开绳任意闭合后计算链接数作为目标。

源码：[orbits/common.py](../../../topogym/tasks/orbits/common.py)。

## 本次验证与边界

2026-09-30 后续指令更新：13 类任务的 agent 目标统一由 [goal_description.py](../../../topogym/tasks/goal_description.py) 根据所选变体和有效配置生成，包括成功条件、持续时间、允许抓持/必须释放、失败行为。任务自身的 `public_instruction()`、Harbor `describe`、limited 服务的 task text 和两种模式的 instruction 共用该描述；limited 不包含物体坐标或内部状态。Rope 按实际环数生成顺序，并用可见环之间的相对侧面说明穿越方向。

仓库 26 份 instruction 及配套 README/任务摘要已更新，unlimited 源码明确标为部分实现参考；公共释放确认不再遗漏。旧 `describe.json` 如果缺少 `public_goal`，任务生成器会要求重新 describe，不继续沿用家族文字。现有检查入口为 [test-task-goal-descriptions.py](../../../ci_checks/test-task-goal-descriptions.py)，包含 39 个难度入口、配置变化、两环/三环、姿态随机化不泄露以及旧缓存拒绝；difficulty 测试另核对 limited/unlimited 输出相同的完整要求。

这次刷新只更新源码和任务包文字，没有重建 simulator 镜像，也没有重新冻结场景。发布新任务包时需使用包含本轮源码的镜像重新执行 describe/prepare；已冻结的历史 run、实例文件和 oracle 未改写。不能将新的 Lock 文字配合旧版 terminal 镜像作为一致的发布物。

Lock 的针对性 CPU 判据测试入口为 [ci_checks/test-lock-picking-terminal.py](../../../ci_checks/test-lock-picking-terminal.py)，覆盖靠壁、微小容差边界、合法/非法倾斜、有限杆穿过全部板、插入不足、齿槽干涉、转盘越界、稳定窗口中断和恢复，以及三档真实末态摘录。记录摘录保留源轨迹路径和 SHA256。

默认启用回归入口为 [test-terminal-defaults.py](../../../ci_checks/test-terminal-defaults.py)：检查所有已集成变体、四组采样种子的 156 个实例、资格不命中、元数据独立性、成功持续窗口、读数缺失、失败优先、终止锁存和旧 revision 的 checkpoint 拒绝。默认 difficulty 配置现为 39/39 实例允许判成功。共享状态机测试使用合成测量，Lock 另有真实保存状态摘录；这些检查不等于所有随机实例都完成物理验收。

本次没有新增 CPU/CUDA 动力学或时间步标定，未改变几何、接触容差、速度/释放要求或确认时长。物理证据补足继续见[工程计划](terminal_enablement_plan_zh.md)，不再作为默认 success 开关的前置条件。新 trial 应使用当前源码生成的镜像及新的 run-id；旧 run/manifest/成绩保持原样。
