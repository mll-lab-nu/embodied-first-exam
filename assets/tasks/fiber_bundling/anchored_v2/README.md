# 光纤收束：固定终端与承托支架（当前默认）

当前已有从初态连续执行的完整机器人解：2 ms / 1 ms 分别在 174.894 / 174.872 s 完成八根细线及前端护套穿环，固定端、入环方向和夹爪禁碰检查通过，含接触后辅助夹持。按当前整束形状选择接触动作，无固定逐根顺序。正式视频在 [MP4 目录](../../../../runs/demos/fiber_bundling/)，配置、轨迹与报告在 [配套目录](../../../../runs/demo_metadata/fiber_bundling/2026-09-17_anchored_ik_hybrid_v1/)。严格全程时间步线形对照未通过：瞬时局部最大差异 4.932 mm；末态局部最大差异为 0.528 mm。完整执行成功与数值收敛结论分别记录。

电缆永久连接一个固定电源终端，防止把自由尾端翻转过来先穿环。终端、出线口、粗线余量段、240 mm 工作段及八根细线组成同一个 MJCF 关节树：终端根部没有自由关节，第一段粗线与终端刚性相连，其余粗线和细线保持被动关节。没有运行时重置尾端位置来代替连接约束。

- 终端为桌面固定电源盒，有外壳、把手、状态灯、安装脚与出线接头。
- 新增约 **830 mm** 的弯曲粗线余量，直径与工作段相同，为前端整理、提起、送线留出空间；不会要求整个电缆离开终端。
- 工作段初始位于独立的开放 U 形托架上。托架有真实碰撞，接触承托、顶部开放，没有把电缆焊在托架上。
- 当前 `spaced_support_v3` 布局把托架朝终端／桌边后移 **80 mm**，圆环与电缆初态不动。托架中心到环平面为 **330 mm**，上部前沿到环平面为 **265 mm**；`task.cradle_x_m=0.02` 控制该位置。历史保存配置未指定此字段时仍回放旧托架位置。
- 前端保留八根 80 mm 彩色细线、固定根部位置和自然外弯初态。细线仍不受重力改变初态；现有整条电缆重力补偿设置保持不变，因此托架是几何承托，不是重力下垂实验。
- 机械臂抓取白名单只有 `trunk_00`–`trunk_05`。终端、出线接头、余量段和细线均不提供抓取目标。
- **夹爪直接接触任意细线即判本次任务失败**，包括指垫、手指、夹爪外壳和连杆；无需夹紧，不设最小接触力或持续时间。保留真实碰撞，细线与圆环／支架及线间碰撞不触发此规则。
- **整理期间允许邻线形状变化**。旧 0.5 mm 变化停止规则已经移除，变化量只记录。新的整束 IK 控制器不要求逐根顺序，也不要求入环之前全部捋直；允许接触环口时继续收束，最终按真实穿环状态验收。

`geometry/bundle.xml` 是带固定终端的动态模型；`bundle_initial.glb/.obj` 包含终端及完整电缆；`anchored_initial.glb` 另含托架；`cradle.glb` 是独立托架预览；`ring.urdf` 保留实际孔洞。静态预览不替代碰撞模型。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.prepare_assets
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.demo
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.anchored_probe
```

显存繁忙时，场景预览可以添加 `env.genesis.backend=cpu env.renderer.type=rasterizer`；仍运行相同碰撞场景，实际渲染后端记录在报告中。

成功要求分叉端先从入环侧穿孔，八根细线和至少 30 mm 前端护套越过环后，粗线在孔中只有一个正向交点，尾端继续连接终端。`FiberScene.step()` 与该任务的 `scene.step()` 每步都更新历史判定：终端／连接点移动、环移动、中段折弯或反面先入孔、从环外绕行都会使本次执行无效。不要绕过任务场景直接推进底层 solver，仅以末态截图判断成功。

当前判定 `front_jacket_entry_all_fines_final_v3` 不要求前端护套首次入孔时八个线头已经全部到环后；只要求入孔部位和方向合法，并在终点验证全部细线通过。`ik_search.py` 探索整束直推、绕行和环边按压，实际记录见 [IK 探索目录](../../../../runs/environment-solvability/fiber_bundling/ik_exploration/)。

当前 `contact_model: capsule_closest_points_scale_relative_v1` 修正 Genesis 1.2.1 对毫米级胶囊轴线的最近点判断，避免漏掉短线段的中部交叉碰撞；不改变模型尺寸或穿透限额。原生碰撞对照在 [contact_precision](../../../../runs/environment-solvability/fiber_bundling/contact_precision/)，新模型独立静置／轻载与时间步复核在 [ik_stability](../../../../runs/environment-solvability/fiber_bundling/ik_stability/)。此复核通过不代表完整操作或释放后静止已经验证。

`contact_guard.py` 在每个 Genesis 刚体物理子步之后读取实际接触对，匹配全局 link ID，覆盖整个夹爪子树与全部细线段。当前 2 ms 步长、4 子步对应每 0.5 ms 检查一次；即使某次接触在同一主步结束前消失也会记录。`task.step()` 返回的状态及 `task.state()` 中，`failed=true`、`terminated=true` 表示本次执行失败，`success` 保持 false；`invalid_reasons` 包含 `gripper_fine_strand_contact`，`contact_rule.first_contact` 保存首次接触的时间、夹爪部件、细线段和位置。撤开、继续推进物理或恢复物理状态都不能清除本次失败。开始新 episode 需新建任务场景。

任务输出终止标志供运行器结束 episode；物理推进仍可用于失败后的诊断。检测依据求解器报告的离散接触，不是任意高速运动下的连续碰撞保证。

目录：[当前宽间距场景预览](../../../../runs/environment_bootstrap/fiber_bundling/anchored_spaced_initial/)；[新布局静置与施力检查](../../../../runs/environment-solvability/fiber_bundling/spaced_stability/)；[旧布局预览](../../../../runs/environment_bootstrap/fiber_bundling/anchored_initial/)；[夹爪接触判败验证](../../../../runs/environment-solvability/fiber_bundling/gripper_contact_rule/)。接触验证包含真实 Panda + Robotiq 碰细线判失败、撤开仍失败、接触工作粗线不误判；测试通过移动机器人基座制造接触，不作为合法操作轨迹或完整求解 demo。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.contact_rule_probe --target fine
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.contact_rule_probe --target trunk
```

固定连接检查覆盖 2 s 静置、粗绳工作段受力和 1 s 卸载；没有写入线段位姿或驱动细线。

新布局已独立完成 5 s 静置、0.35 s 轻载、5 s 释放及 2→1 ms 时间步复跑，报告在 [spaced_stability](../../../../runs/environment-solvability/fiber_bundling/spaced_stability/)，末态局部线形最大差异约 0.061 mm。静置无漂移、连接和接触数值有界，但完全释放后仍有运动，不能称为释放后已静止。旧布局的同类报告保存在 [anchored_stability](../../../../runs/environment-solvability/fiber_bundling/anchored_stability/)；旧布局真实 Panda + Robotiq 的首次纯接触抓取曾在两种时间步下分别成功，阶段末局部线形最大差异约 0.093 mm，不外推为新布局完整接触路径认证。

新布局此前的 [机器人尝试](../../../../runs/environment_bootstrap/fiber_bundling/anchored_spaced_initial/) 在同一次连续执行中整理前两根电线，允许邻线暂时改变形状；72.172 s 时第三根按压触发细线几何穿透检查，该次没有完成全流程。该次没有夹爪碰细线或机器人与夹具接触，辅助夹持状态在视频和报告中明确标注。

[历史机器人尝试视频目录](../../../../runs/environment_bootstrap/fiber_bundling/anchored_robot_attempt/) 保留局部尝试的 MP4、实际报告和原始状态；最新完整结果见本文开头的整束 IK 目录。启用辅助夹持约束的试验会明确标注，并持续检查双侧真实接触；不能靠张开夹爪后的约束继续搬运。

旧 `branched_v1` 的单根、全流程 demo 及时间步稳定性结果只属于自由电缆版本，不作为本版本的完整求解或稳定性认证。空间分辨率收敛与真实导线材料标定仍未完成。
