# 光纤收束：固定终端与分叉电缆

2026-09-19 新增[实例生成与 seed 接入检查](fiber_bundling_variant_pipeline_zh.md)：固定模板和参数采样统一输出完整实例，供后续执行／数据 pipeline 使用；用户已确认稀疏／标准／密集三类按线数划分，不要求 IK 有本质区别。

2026-09-18 当前交付为基础 8 芯、环内半径 13.5 mm、细铜杆支架的无 UI 三视角，各 177 秒，分别放在 [demos/fiber_bundling/agentview](../../../demos/fiber_bundling/agentview/)、[front_oblique](../../../demos/fiber_bundling/front_oblique/)、[wrist](../../../demos/fiber_bundling/wrist/)。由原完整物理轨迹重新渲染，文件名前缀为 `2026-09-18_standard_08_r13p5mm_clean_v1`。旧 52 份视频已按用户要求删除，历史执行证据保留；[当前清单](../../../runs/demo_metadata/fiber_bundling/README.md)。

2026-09-17 新增[细铜杆支架与线数／孔径三类变体](fiber_bundling_density_radius_zh.md)。九个代表之外增加 5、6 芯过渡实例，并把下面的旧支柱完整 demo 计为一个独立变体；各实例的加载检查、完整执行与视频归档状态见 [variant_demos_v1 记录目录](../../../runs/environment-solvability/fiber_bundling/variant_demos_v1/)。正式视频统一放在 [demos/fiber_bundling](../../../demos/fiber_bundling/)。

## 旧矩形支柱版本：整束反馈 IK 完整机器人解

`greedy_hybrid_05_adaptive_clearance` 已从原始场景初态完成真实抓取、环边接触收束及整束穿环，连续物理运行 **174.894 s**，2 ms / 4 子步。没有保存状态恢复、电缆位姿写入或细线直接驱动；只命令 Panda 关节与 Robotiq 夹爪电机，双侧真实护套接触后启用辅助夹持，并在末态继续持握。因此这是含接触后辅助夹持的完整物理执行，不是纯摩擦夹持结果。

最终八根细线整根位于环后，前端护套跟进 **34.087 mm**，粗线在孔内只有一个正向交点；固定终端和环未移动，349,788 个子步的夹爪禁碰检查没有触发。实际环轴下八根细线的最大包络半径为 **12.984 mm**，小于 **13.479 mm** 最小净孔半径。全程最大原生细线接触穿透 **0.0150 mm**、独立细线间穿透 **0.00452 mm**、粗线接触穿透 **0.2676 mm**、机器人与夹具穿透 **0.0228 mm**，均通过预设数值门槛。

策略依据当前整束最突出部位选择接触方向，一次按压可同时改变多根线，允许已收拢的线暂时再次外张。不固定逐根顺序，不要求先把每根线都变成直线；必要时在空处换侧绕开支柱及腕部限位，按当前整束轮廓扩大接近距离，最后让环口继续引导收束。IK 目标的最大位置残差约 **10 μm**、旋转残差 **5.80×10⁻⁵ rad**，相邻 10 ms 关节目标最大变化 **0.00778 rad**；这些是 IK 解的残差，不是电机全程跟踪误差。

相同程序与参数以 **1 ms / 4 子步** 从初态独立复跑，**174.872 s** 完整通过；夹爪禁碰检查覆盖 699,488 个子步，没有触发失败。该次最大细线原生穿透 **0.01746 mm**、独立细线间穿透 **0.00461 mm**，末态整束最大包络约 **12.992 mm**。两种步长都成功不等于逐帧线形已经收敛：严格全程线形对照存在超过预设门槛的瞬时差异，独立报告保留未通过结论。

完整对照的末态局部最大差异 / RMS 为 **0.528 / 0.175 mm**，满足原来的 **2.0 / 0.5 mm** 门槛；全过程同一时间的局部最大差异 / RMS 峰值为 **4.932 / 2.605 mm**，世界坐标最大差异 **3.980 mm**。按动作结束时比较，局部最大差异不超过 0.888 mm，但世界坐标在最后一次按压后的检查阶段达到 2.507 mm，仍超过 2 mm 门槛。因此 `timestep_validation.json` 的整体 `passed=false`，不能宣称完整路径已经通过严格数值收敛验证；没有放宽这些阈值。

此旧矩形支柱版的视频已按用户要求从正式目录删除。配置、物理报告、两种时间步的完整轨迹及源代码、图像和 SHA-256 清单仍在 [配套报告目录](../../../runs/demo_metadata/fiber_bundling/2026-09-17_anchored_ik_hybrid_v1/)。归档证明当前模型下的完整机器人执行，严格时间步对照未通过的结果也随归档保留；当前视频见页首基础铜杆版目录。

原始完整执行目录：[greedy_hybrid_05_adaptive_clearance](../../../runs/environment-solvability/fiber_bundling/ik_exploration/greedy_hybrid_05_adaptive_clearance/)。[整束包络与实际通过数量曲线](../../../runs/environment-solvability/fiber_bundling/ik_exploration/greedy_hybrid_05_adaptive_clearance/bundle_progress.png) 展示全过程真实采样结果。该次的 Nyx 全景、近景、腕部和合成视频均为 **3539 帧 / 20 fps / 176.95 s**，含末尾 2 s 保持，已完整解码验证；逐帧回放与原始物理中心线最大误差 **0.968 μm**。此前的保存状态续跑诊断不计为完整执行。

## 当前默认：anchored_terminal_v2

为排除把自由尾端翻转后先穿环的捷径，电缆现在永久接到固定电源终端。终端与整条电缆属于同一 MJCF 树，根部没有自由关节；第一段粗线刚性接在终端出线口，其余关节被动。原有 240 mm 工作段前加入约 830 mm 的弯曲余量粗线，使固定尾端后仍有送线和整理的空间。工作段初始放在开放 U 形支架上，支架只参与碰撞，不夹紧或焊接电缆。

八根细线、环孔和工作段原参数不变。沿用整条电缆重力补偿与零弹性刚度／正阻尼的离散模型；支架展示几何承托，不将本场景说成重力下垂实验。机械臂抓取白名单仍只有工作段 `trunk_00`–`trunk_05`。

### 当前布局与整理策略：spaced_support_v3

开放托架沿电缆向终端／桌边后移 **80 mm**：相对工作段起点的 `cradle_x_m` 从 0.10 改为 0.02，世界 X 从 −0.15 改为 −0.23 m。圆环保持 `[0.10, 0.40, 1.1596429] m`，电缆及固定终端初态也保持原位。托架中心至环平面的轴向距离从 **250 增至 330 mm**；托架上部前沿至环平面从 **185 增至 265 mm**，至环最近表面约 261 mm。这些是夹具间的几何间距，不代表任意夹爪姿态都已验证可达。

默认配置、资产生成器和物理检查使用这一布局；`scene.py` 读取 `task.cradle_x_m`。旧运行的保存配置没有此字段时仍使用原来的 0.10 m，避免回放历史视频时悄悄改变托架位置。新版目录为 [anchored_spaced_initial](../../../runs/environment_bootstrap/fiber_bundling/anchored_spaced_initial/)，可以直接打开 PNG 或 MP4。

**邻线形状变化只记录，不判失败。** 旧机器人运行器在一根线整理后保存其中心线；将后续形状转换到电缆端面的局部坐标系，消除整体平移／转动后，计算各采样点相对参考形状的最大位移。任意后续时刻超过 0.5 mm 即停止；另有整理一根线时其余线变化不得超过 0.5 mm 的检查。它们原本用于保守实现“不扰动其他线”，不是物理稳定性或孔径条件，而且会把暂时弯曲也算进去。两处停止规则及整理后额外降速均已删除。

允许邻线被碰弯、在运动中暂时改变形状或需要再次整理。旧的 `robot_sequence.py` 整理策略最多做两轮，并在推进前按真实环轴检查整束包络（含线半径及 0.3 mm 规划余量）。这只是该控制器的保守规划条件，**不是任务规则**。新的 `ik_search.py` 不要求逐根顺序，也不要求先把整束全部捋直才允许推进：可以在入环接触过程中继续收束。各段是否全朝前仅作诊断，历史“整理成功”标签不能替代当前检查。耗尽尝试次数只表示这条策略没完成，不永久判任务物理失败。最终成功仍必须通过真实穿环历史判定。

新布局已独立完成 5 s 静置、0.35 s 轻载、5 s 卸载及 2→1 ms 时间步复跑：[spaced_stability](../../../runs/environment-solvability/fiber_bundling/spaced_stability/)。静置无漂移，末态局部线形最大差异 **0.0608 mm**，全程局部最大差异 **0.1147 mm**；两组检查通过。完全释放后仍有运动，不声称已静止或完整机器人接触路径已获认证。稳定性门槛现在同时匹配电缆哈希和明确的托架／环布局，不能仅凭电缆文件未变复用旧布局检查。

新布局 `spaced_robot/attempt01` 已实跑到 72.172 s。真实机器人从初态抓取、提起、换抓后，依次将红线和蓝线整理至 12.207 / 12.442 mm 包络半径，使用双侧接触后启用的辅助夹持。整理第二根期间，红线相对首次整理后形状的最大变化约 4.810 mm，包络曾暂时增大到 14.873 mm；第二根整理结束后，红线形状差异降回 0.029 mm，包络为 12.227 mm。这一段没有因为邻线变化而停止，符合只在最后检查整束的策略。图 `neighbor_shape_diagnostic.png` 保存实际采样曲线。

该次运行在第三根按压阶段因独立细线几何检查发现 **0.30069 mm** 穿透（红线第 5 段与白线第 4 段）超过 0.3 mm 数值门槛而停止；没有夹爪碰细线，机器人与夹具的穿透最大值为零。新视频 `anchored_spaced_initial/robot_attempt.mp4` 是同一次连续仿真的局部尝试，尚未完成八根整理或最终穿环。保留这个接触检查，未将移除邻线形状限制解释为允许几何互穿。

新增硬性失败条件：**夹爪任何部件直接接触细线，本次 episode 即失败**。`contact_guard.py` 每个刚体物理子步检查原生碰撞接触对，覆盖手指、指垫、夹爪外壳与连杆；不要求夹紧、持续接触或达到某个力阈值。粗电缆抓取、细线与圆环／支架及线间接触不触发这一规则。失败后即使撤开夹爪或把线穿过去，`success` 也不能恢复。`task.state()` / `task.step()` 返回 `failed`、`terminated`、`invalid_reasons`，首次违规细节保存在 `contact_rule.first_contact`；运行器应在 `terminated` 时结束 episode，诊断仍可继续推进物理。当前每 0.5 ms 检查一次求解器接触，不替代连续碰撞检测。

验证目录：`runs/environment-solvability/fiber_bundling/gripper_contact_rule/`，其中 `fine/report.json` 验证真实夹爪接触细线与撤开后仍失败，`trunk/report.json` 验证真实夹爪接触工作粗线不误判。两项均通过；另外规则测试覆盖接触对正反顺序、零力接触、仅在首个子步出现的短暂接触及达到穿环末态仍失败。这些是判定器验证，测试中的机器人基座移位不是任务 demo。

任务终点改为：**分叉端先入孔，全部细线及至少 30 mm 前端护套越过环后，尾端仍连着固定终端**。不再要求整条电缆通过。`anchored_verifier.py` 验证粗线只有一个孔内正向交点，并记录首次入环历史；反面／中段折弯先入环、从孔外绕行、移动终端或环会永久使本次执行无效。`FiberSceneBuilder` 给本任务的 `scene.step()` 接入检查，使用 `task.step()` 或直接 `task.scene.step()` 都会更新历史。

[当前资产说明](../../../assets/tasks/fiber_bundling/anchored_v2/README.md)；[新场景与终端预览目录](../../../runs/environment_bootstrap/fiber_bundling/anchored_spaced_initial/)；[新布局静置及粗绳施力报告](../../../runs/environment-solvability/fiber_bundling/spaced_stability/result.json)。新模型已有固定连接、静置、受力与方向判定检查；没有将旧自由电缆的完整穿环、时间步收敛或机械臂执行结果沿用到新版。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.prepare_assets
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.demo
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.anchored_probe
```

默认仍使用 Nyx。其他并行任务占满显存时，可用 `demo env.genesis.backend=cpu env.renderer.type=rasterizer` 完成带碰撞的 CPU 场景检查与 OpenGL 预览，报告保留实际后端。旧的 `single_strand` 和 `sequential` 仅在显式传入 `--legacy-free` 时运行。

## 整束 IK 探索与接触精度修正

`ik_search.py` 从场景初态执行真实 Panda + Robotiq 抓取，以 100 Hz 连续 IK 目标驱动关节电机；电缆、终端和环没有运行时位姿写入，细线没有直接驱动。探索直推、收缩绕行、侧向按压、接触中旋转、空处转向后按压和惯性牵拉。动作允许同时影响多根线，亦可根据当前最大突出部位自适应选择下一次按压；没有固定逐根顺序，也没有邻线形变限额。

当前任务判定版本为 `front_jacket_entry_all_fines_final_v3`：首次粗线入环必须是前端护套的单个孔内正向交点，但不再要求这一时刻八根细线的线头已经全部到环后。中间状态允许不同线头先后通过，最后仍要求**全部细线和至少 30 mm 前端护套穿过孔**。尾端／中段先入环、孔外绕行、移动固定物和夹爪碰细线仍永久判败。这个变更移除额外的顺序条件，没有把“一个线头过平面”当作成功。

IK 连续性比较相邻两次关节目标，阈值为每个 10 ms 指令 0.15 rad；不把电机滞后误判为 IK 分支跳变。初始辅助夹持仍要求两侧手指同时真实接触同一工作粗线段。持握期间允许两侧接触同一连续护套的相邻离散段：抓取段及紧邻的前后各一段；远处粗线和细线不能代替接触，仍检查当前双侧接触、夹爪开度及超过 100 ms 的接触丢失。辅助 weld 仅在接触抓取之后启用，`--no-assist` 可关闭。含辅助约束的结果不能当成纯摩擦夹持结果。

本轮还发现 Genesis 1.2.1 的胶囊轴线距离函数将长度四次方的行列式与无量纲 float32 epsilon 直接比较。对 8 mm 细线段，即使轴线垂直也进入近乎平行分支，可能漏掉段中间碰撞。`contact_precision.py` 使用尺度相关平行判断并枚举边界／内部最近点，运行时替换本进程的距离函数，不修改已安装的 Genesis 文件，不改半径或穿透阈值。当前配置记录 `contact_model: capsule_closest_points_scale_relative_v1`，旧运行缺省为 `genesis_default`。

原生求解器对照见 [contact_precision](../../../runs/environment-solvability/fiber_bundling/contact_precision/)：8 mm 胶囊预设 0.4 mm 重叠时，原函数漏掉垂直和斜交两例；修正后垂直、斜交、平行偏置均测得约 0.400004 mm，分离对照没有接触。新接触模型重新执行了 5 s 静置、0.35 s 轻载、5 s 释放以及 2→1 ms 时间步对照，[ik_stability](../../../runs/environment-solvability/fiber_bundling/ik_stability/) 通过这组检查；释放后仍未静止，不代表完整机器人路径已获稳定性认证。稳定性门槛现在同时匹配接触模型、布局和电缆资产哈希。新模型也重新验证了真实夹爪碰细线会锁存失败。

`greedy_orbit_01` 保持护套朝向，根据当前最大突出部位依次选到黑、红、黄、棕、蓝线；这次顺序由状态产生，不是任务规定。第五轮结束时，这五根的局部包络为 **13.15–14.73 mm**，按压棕线还将白线从约 28 mm 缩到约 19 mm。这里的局部包络缩小不等于已穿环，部分值仍大于 13.479 mm 净孔；允许后续入环接触继续收束。

该次在第六轮的 **78.774 s** 停止：绿线靠近环下方支柱，原生接触穿透达到 **0.3042 mm**。`post_collision_audit.json` 用保存的线段与支柱前表面独立算得约 0.3075 mm 重叠，确认是支柱阻挡，不是邻线形变规则。此前五轮没有夹爪碰细线；整次独立细线间穿透最大约 0.0493 mm。`greedy_hybrid` 因而对接近方向受下方支柱阻挡的突出部位改用环侧面的按压，再回正并重新测量整束。

直推的 `axial_03`、1 ms 的 `axial_04_half_step` 和半速的 `axial_05_slow` 都在细线折回挤压前端护套时触发接触穿透检查，仍未完成任务。它们说明这些直推策略没有通过，不证明所有不预整理的策略都不可行。

前五轮及后续转向准备已做相同程序的 2→1 ms 独立复核，见 `ik_exploration/hybrid_before_ik_choice_timestep.json`。0–74.8 s 同一仿真时刻的中心线最大差异为世界坐标 **0.549 mm**、护套局部坐标 **0.506 mm**，最大局部 RMS **0.202 mm**，均满足已有 2.0 / 0.5 mm 数值门槛；两次分别在 74.804 / 74.802 s 遇到相同的腕部关节限位。对照报告的整体 `passed` 仍为 false，因为没有完成全任务，不能把已验证的这段轨迹外推为完整穿环认证。

侧面整理还需要检查机械臂自身的姿态路径。`greedy_hybrid_01` 的第一种转向在第 7 关节目标达到 −2.8973 rad 限位后，无法继续满足姿态误差阈值；这不证明该末端姿态全局无解。`ik_turn_probe.py` 从保存姿态做独立的纯运动学诊断，同高度另一侧的 −70° 转向通过了 352 个连续 IK 采样，最大相邻关节目标变化约 0.0070 rad。该诊断会恢复保存位姿，**不是物理执行或成功 demo**。最新控制器在真实运行中预检查两侧转向，再选择通过连续 IK 检查的一侧；执行时仍重新求解 IK，并保留全部原生接触、夹持和穿透检查，候选记录在 `turn_ik_audits.json`。

`greedy_hybrid_03_ik_choice` 在真实执行中使用了这一预检，成功改走另一侧并避开支柱；最终仍在 153.752 s 送线时因夹爪接触细线而失败。原因之一是回正后灰线外张至约 44 mm，原来的 60 mm 侧向接近距离已不能让整束位于环外，后续接触反而使它更加外张。`prepare_orbit` 因此增加按当前整束轮廓计算的接近距离，并在空处移动后再次检查余量；没有缩小电线碰撞半径或放宽穿透检查。

保存状态上的后续策略试验单独放在 [ik_continuations](../../../runs/environment-solvability/fiber_bundling/ik_continuations/)。此类诊断明确记录状态恢复，且不恢复求解器热启动；即使后续到达目标，也不能当作从初态执行成功，必须独立重跑完整过程。完整时间步复核除源代码与资产外，还比较全部执行参数和稳定性报告的内容哈希，仅允许时间步及报告文件位置不同。

每次独立试验保存在 [ik_exploration 原始记录目录](../../../runs/environment-solvability/fiber_bundling/ik_exploration/)。`report.json` 区分完整成功、规则违规、数值超限和 IK／持握失败；`bundle_metrics.json` 记录各阶段整束包络，`robot_commands.json` 保存 IK 残差与相邻关节目标变化，`trajectory.npz` 保存实际物理状态。早期试验使用旧接触模型／旧判定，必须按各自 `config.yaml`、`plan.json` 和 `source/` 解读，不能与新版条件混用或追溯改成成功。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.ik_search \
  --mode greedy_hybrid --grasp-link trunk_04 --press-radius .0353 --max-presses 16 \
  --output runs/environment-solvability/fiber_bundling/ik_reproduction
```

## 固定终端旧布局：数值检查与机器人执行尝试

本节 attempt01–14 与以下测量使用原来 `cradle_x_m=0.10` 的布局；0.5 mm 邻线保护是历史策略，已由上面的最终整束检查替代。旧运行文件保留原始停止原因，不追溯改成成功。

当前固定终端模型已补做 5 s 静置、0.35 s 粗线施力、5 s 卸载的连续检查，并将主步长从 2 ms 减半至 1 ms 独立复跑。施力只作用于 `trunk_04`，世界坐标力为 `[-0.04, 0.008, 0.01] N`；不写电缆位姿，不施力于细线。目录为 `runs/environment-solvability/fiber_bundling/anchored_stability/`。

两次静置均无漂移，固定连接、细线根部和段长误差低于 0.04 μm；最坏原生穿透 0.011 mm，独立线段检查未发现细线相互穿透。减半时间步后的末态局部线形最大差异为 0.057 mm，RMS 为 0.024 mm；全程同一时刻的局部最大差异为 0.437 mm，世界坐标差异保持在 2 mm 阈值内。`assess_anchored.py` 同时核对资产哈希、载荷、采样时间和固定根部，不能用自由电缆报告或不同模型代替。

这个结果只通过**静置与轻载的数值有界性检查**。完全释放后末期仍有约 0.050 m/s 的线段速度，最后 1 s 的局部线形变化约 0.954 mm；报告明确保留 `free_release_settled=false` 和 `full_robot_contact_sequence_qualified=false`。零弹性刚度、重力补偿模型不会自动回到原形，也不保证整束释放后迅速静止。机器人接触全程及其时间步复核需要另外验收。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.anchored_probe \
  --output runs/environment-solvability/fiber_bundling/anchored_stability_reproduction/baseline \
  --settle-seconds 5 --load-seconds .35 --release-seconds 5 --load-scale .1 --cradle-x .10 --contact-model genesis_default
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.anchored_probe --dt .001 \
  --output runs/environment-solvability/fiber_bundling/anchored_stability_reproduction/half_step \
  --settle-seconds 5 --load-seconds .35 --release-seconds 5 --load-scale .1 --cradle-x .10 --contact-model genesis_default
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.assess_anchored \
  runs/environment-solvability/fiber_bundling/anchored_stability_reproduction
```

`robot_sequence.py` 使用真实 Panda 关节电机控制和 Robotiq 手指碰撞，从初态接近护套、建立双侧接触、提起、换抓到较后方，再尝试借固定环缘逐根整理。全程只命令机器人关节；终端、环和电缆均无位姿写入，细线无直接驱动。可选的辅助抓持只在双侧手指同时接触同一段粗线后启用原生 weld；`--no-assist` 完全不使用该约束。持续检查夹爪开度及双侧接触，不能靠张开的夹爪和隐藏约束继续带动电缆。

首次纯接触抓取已在 2 ms 和 1 ms 步长下分别成功。按双侧接触后的 0.4 s 保持阶段末态比较，细线局部最大差异 0.093 mm、RMS 0.047 mm，世界坐标最大差异 0.180 mm；接触触发时间相差 3 ms。半步长运行粗线接触穿透最大 0.036 mm，两次均无夹爪碰细线。见 `anchored_stability/robot_grasp_timestep_comparison.json`，不把这一小段的结果外推至完整操作。

每次尝试保存在独立的 `runs/environment-solvability/fiber_bundling/anchored_robot/attemptXX/`。`report.json` 区分抓取完成和完整穿环，失败时保留停止阶段；`trajectory.npz` 保存电缆与机器人状态，`robot_commands.json` 保存关节目标，`source/` 保存当次运行器。视频来自该次连续物理运行的状态回放，渲染不参与物理控制，并逐帧核对细线中心线。局部尝试不能当作已完成的八根整理与最终穿环。

可直接播放的副本集中在 [anchored_robot_attempt 目录](../../../runs/environment_bootstrap/fiber_bundling/anchored_robot_attempt/)。`attempt13` 已在真实机器人加接触后辅助夹持的条件下完成第一根红线整理：40.716 s 时包络半径 12.178 mm，小于 13.479 mm 净孔，其余七根线形变化最多 0.130 mm。43.874 s 切换第二根时，红线变化达到 0.504 mm，超过预先设置的 0.5 mm 保护阈值，自动停止。全程无夹爪与细线或托架接触，未完成全流程。纯接触的 `attempt11` 完成提起、换抓后在选线下降过程中丢失双侧夹持；不能把辅助约束试验当作纯接触完整成功。

`attempt14` 将已有整理结果后的所有移动耗时加倍，保持相同 0.5 mm 阈值；第一根整理结果复现，但 46.588 s 切换第二根时变化达到 0.5003 mm，仍自动停止。因此尚未获得固定终端版本的完整机器人解法。这里的停止是保护判据未通过，不是数值发散，也不能据此断言任务不可解。两条轨迹均不直接写电缆位姿，没有继续执行未获保护检查通过的整束推进。

## 以下为 branched_v1 自由电缆的历史记录

本节以下的自由基座、整条粗绳过环和相关通过结果仅适用于历史模型，不能作为当前固定终端版本的验收依据。

2026-09-16 的用户定义替代部署提案中“多根独立导线、双臂逐根穿环”的暂定版本。任务为一根粗绳的前端连接多根细绳，细绳根部相对粗绳端面的位置固定，初始方向、弯曲和角度随机；细绳不受重力影响，能被碰撞改变形状。机械臂只能操纵粗绳，目标是把整个分叉组件捋顺并穿过只能容纳粗绳的固定闭环。

## 资产与基础场景

`topogym/tasks/fiber_bundling/` 沿用 Layout → SceneBuilder → Scene。默认单臂 Panda + Robotiq 2F-85，Nyx 与完整 compact_lab 背景。粗绳与细绳是同一自由多体树，固定支架只连接环；粗绳没有固定到世界或机器人。

| 参数 | 基线 |
| --- | --- |
| 粗绳半径 / 长度 / 分段 | 12 mm / 240 mm / 6 |
| 细绳数量 / 半径 / 露出长度 / 分段 | 8 / 1.2 mm / 80 mm / 10 |
| 连接点分布 | 粗绳端面、半径 8 mm 圆周，位置不随种子改变 |
| 初始方向与曲率 | seed=7；出口前 16 mm 沿护套轴向，随后自然外弯；末端切线角在 28–50° 内采样，拒绝相交初态 |
| 环内半径 / 管半径 | 13.5 mm / 4 mm |
| 实际最小径向余量 | 64 段环碰撞体内孔与粗绳相差约 1.479 mm |
| 主场景步长 | 2 ms，4 个子步，100 次求解迭代 |

外观修订将露出线长从 150 mm 缩至 80 mm，并收小发散角。外层为连续黑色护套，切口有环形薄壁和内部填充；内部使用常见的红、蓝、绿、棕、白、黄、黑、灰绝缘线配色，末端为约 3 mm 的七股铜丝。GLB 包含护套、绝缘层与铜的 PBR 材质；Nyx 动态场景使用独立视觉几何与逐几何颜色，绕过当前插件共享 MJCF 材质覆盖的问题。细节仅改变视觉，不添加抓取对象，也不缩小碰撞半径。

细绳每节使用真实有限半径胶囊体，带线间、线与环、线与粗绳的碰撞。相邻父子节按引擎的关节碰撞规则排除相互接触。根部球关节锁定三维位置，允许转动；后续球关节允许分段弯曲。连接点不是运行中重新投影回端面的点，也没有按帧写入细绳位置。

首版零弹性刚度，只有粘性阻尼，近似可被整理且不自动弹回初态的软线。整个粗细绳组件采用重力补偿 1，世界仍为 -9.81 m/s²；粗绳也不因自重下垂。主场景可通过 `grasp_target("trunk_XX")` 获取粗绳抓取目标，细绳名称会被拒绝。该接口是任务级限制，未把机器人与细绳的真实接触关闭；后续动作策略需要沿用此抓取入口。

自然外弯只设置初始关节坐标系，仿真中没有恢复这条曲线的力矩，也不重写细绳姿态。碰撞后保留新形状属于塑性行为的离散近似，尚无真实铜材的弹性区、屈服阈值与硬化模型。

## 运行

仓库根目录：

```bash
# 纯资产生成，不初始化 Genesis
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.prepare_assets

# 实验室初态、0.2 s 静置、四个相机（含切口特写）以及相机环绕视频
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.fiber_bundling

# 接触和卸载诊断：只驱动粗绳根部，随后移走环并被动模拟 1.5 s
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.probe

# 不依赖 GPU 的回归
.venv-gs121-nyx/bin/python -m unittest tests.check_fiber_bundling
```

展示：`runs/environment_bootstrap/fiber_bundling/branched_initial/index.html`。
主场景配置：`configs/fiber_bundling_preview.yaml`；候选轴：`configs/task_cards/fiber_bundling.yaml`。
可覆盖 `task.geometry.seed=13` 改变曲线，数量变更受连接点间距检查约束；这些参数尚未获得变体物理认证。

## 验证范围与后续工作

主场景记录真实静置时间、细绳位移、根部位置误差。接触试验使用两套相同绳模型与相同根部运动，一套有环、一套无环，对比碰撞力、形变差、根部误差和最大接触穿透。加载结束后仅将环移至空处，细绳继续被动模拟，不清零速度或写入状态；检查外部接触消失、残余形变保持、末期形状稳定。形变按端面固定根部定义的坐标系计算，排除粗绳整体运动。

试验中的粗绳根部是显式运动夹具，每步改变夹具位置；主场景仍为自由绳，不借用夹具限制。报告和 `states.npz` 保存初态、加载后、卸载后实际结果，失败会以非零退出码结束。`review.py` 根据状态生成对比图与 HTML，可独立重建：`python -m topogym.tasks.fiber_bundling.review runs/environment_bootstrap/fiber_bundling/contact_probe`。

当前范围是可复用资产、初态场景与局部接触行为，不是完整 oracle。尚需验证实际夹爪夹持粗绳、负载下的自接触与细绳互穿、步长/分段收敛、细绳全部穿环及主绳跟进，以及自动调整的成功率。
“必须反复微调”仍需用直推失败对照和合法微调成功轨迹建立证据，不能仅用窄孔几何宣称已实现。现有状态接口只报告整根细绳是否位于环后，不把单个端点越过平面认定为完整任务成功。

## 2026-09-16 初版长线本机验证（历史）

本节数字对应修订前的 150 mm / 大发散角版本，保存在 `branched_long_wide_reference/` 和 `contact_probe_long_wide_reference/`；当前短线版本以 `branched_initial/inspection_report.json` 与 `contact_probe/report.json` 的实际结果为准。

主场景实际静置 100 步（0.2 s），细绳最大位移为 0，机器人与绳组件接触步数为 0；根部位置约束误差约 2.1×10⁻⁸ m。已生成三个 Nyx 视角与 4 秒相机环绕视频。

独立配对夹具试验运行 700 步（含静置，共 1.4 s），只平移粗绳根部。有环组记录到 142 步接触；无环组保持原形。消除粗绳自身的刚体运动后，细绳相对根部的最大形变差为 **38.43 mm**，说明接触确实改变了细绳的形状。最大接触穿透 **0.256 mm**，根部约束误差约 3.1×10⁻⁸ m，通过本地诊断阈值。以上不等于完整穿环或连续杆精度认证。

新增 6 项 CPU 检查覆盖 seed/连接点不变性、线长、孔隙与根部拥挤拒绝、有限线段相交、被动动态树、粗绳抓取限制和消除粗绳刚体运动的形变测量。

## 短线与小发散角修订验证（历史）

下列结果对应此前从出口直接发散的版本，已归档至 `branched_short_fan_reference/` 和 `contact_probe_short_fan_reference/`。

80 mm / 10 节细绳的实际横向包络半径为 43.59 mm（初版为 148.50 mm）。新版场景静置 0.2 s 无漂移、无机器人接触，四张视图与视频已重生成。12 项相关回归通过。

短线配对夹具复核通过：1.4 s 中记录 373 步环接触，最大穿透 0.199 mm，根部误差 3.20e-08 m；无环对照保持原形。细绳受环口偏折，仍无细绳位置写入或执行器。该局部试验不证明完整穿环策略。

## 轴向出线、自然外弯与卸载保持验证

当前 80 mm 细绳前两节沿轴向伸出，然后平滑增加外弯角度，整体横向包络半径约 32.46 mm，较上一版 43.59 mm 更收拢。此处 `fan_angle_min_deg/max_deg` 定义末端切线角，不能与旧版出口发散角直接比较。

实际 GPU 配对试验共 2.9 s（0.2 s 静置、1.2 s 加载、1.5 s 卸载），全部 9 项检查通过：379 步环接触，最大穿透 0.212 mm，根部误差 3.37e-08 m；无环对照保持初态。加载结束时，端面坐标系中的最大弯曲差为 135.12 mm；移走环后为 142.06 mm，约为加载结束时的 105.1%。该数值是同一中心线点相对于对照组的位置差，不是线长或应变；卸载初期惯性会使弯曲继续变化，随后停止。

卸载期间没有与环接触，最后 0.3 s 未测到形状漂移（保存的数值精度下为 0），说明初始外弯不是永久锁定形态。9 项局部检查不构成任意载荷、长期稳定性或材料精度保证。13 项相关 CPU 回归通过。

[初态、碰撞后与卸载后对比](../../../runs/environment_bootstrap/fiber_bundling/contact_probe/index.html)；[场景与切口特写](../../../runs/environment_bootstrap/fiber_bundling/branched_initial/index.html)。

## 单根红线整理过程

`single_strand.py` 使用相同的 8 根细线、固定环和被动物理参数，仅控制粗绳后端 `trunk_00` 的显式运动夹具。动作是偏移粗绳使红线线头进入环孔、向前送入、回正、沿环口回拉整理、重新送进，再做小角度方向校正。其余细线仍参与碰撞；不移动环，不直接控制任何细线。

该局部 demo 没有执行机器人实际抓取。检查不仅要求线头在环后，也要求红线穿过孔内、整根红线含半径的横向投影容入净孔、相对粗绳端面的弯曲减小，并检查连接约束与碰撞穿透。它不等于整束细线及粗绳全部穿环。

```bash
# 运行真实物理过程，保存动作、逐阶段指标及原始关节和中心线状态
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.single_strand --legacy-free

# 根据记录的状态生成近景视频、沿环轴画中画和中文阶段字幕
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.render_single_strand \
  runs/environment_bootstrap/fiber_bundling/single_strand_demo
```

[单根细线整理 demo](../../../runs/environment_bootstrap/fiber_bundling/single_strand_demo/index.html)。
`plan.json` 保存粗绳夹持端的动作；`report.json` 保存实际物理检查。`trajectory.npz` 中保存真实采样状态，视频回放不合成线形、不插值修改关节。渲染场景只平移至实验室展示位置，每帧核对中心线与原始物理轨迹，误差写入 `render_report.json`。视频慢放，画面时间是原始仿真时间。

本机最终轨迹运行 4.3 s，9 项物理检查通过。红线末端与环轴夹角由 41.75° 降至 14.48°；相对粗绳端面的末端角由 41.75° 降至 16.04°，因此形状改善并非仅来自整体旋转。红线横向包络半径由 33.51 mm 缩至 8.23 mm（含线半径），小于 13.48 mm 净孔半径；线头越过环后 33.24 mm。264 步红线—环接触，最大穿透 0.209 mm，根部误差 3.36e-08 m。16 项相关 CPU 回归通过。

## 数值稳定性与可解性应分开验证

电缆半径小于净孔半径，说明轴向摆正的粗绳可以容入孔径；它本身不保证仅操纵粗绳就能把全部细线整理到可通过状态。当前固定连接点允许一个无碰撞的目标构型：8 根细线全部沿轴向，细线束半径 9.20 mm，粗绳半径 12.00 mm，环最小净孔半径 13.479 mm，细线表面之间至少相隔 3.723 mm。`straight_goal_witness.npz` 保存这一几何见证，不把它当作执行过的解法。

`validation.py` 在运行前记录验收阈值，分别在 CPU、GPU 上执行：自由基座静置 10 s；实际接触整理 4.3 s 后停止输入并静置 5 s；将宏时间步从 2 ms 减至 1 ms（均为 4 子步）重新完整运行。逐步检查有限状态、连接点误差、段长、原生接触穿透、独立线段距离计算出的线间穿透，以及每步位移；卸载静置时检查形状漂移和残余速度。

两种后端均通过这组检查。自由静置与最后 1 s 的保持检查均未测出漂移；最大根部/段长误差低于 0.04 μm，最坏接触穿透 0.256 mm，低于预先设定的 0.300 mm。消除粗绳整体运动后，2→1 ms 的末态最大差异 / RMS 为 GPU 1.396 / 0.358 mm、CPU 1.659 / 0.352 mm，低于 2.0 / 0.5 mm 阈值。同时间步 CPU/GPU 的末态差异为最大 0.852 mm、RMS 0.316 mm。

这是一组针对 seed=7、当前分段杆模型和已测试动作的工程检查，不是任意载荷的稳定性证明。没有标定铜线屈服/硬化模型，也没有完成空间离散收敛性检查。CPU/GPU 和不同时间步的毫米级差异仍需保留在报告中，不能把“通过阈值”描述成轨迹完全一致。

[GPU 稳定性报告](../../../runs/environment-solvability/fiber_bundling/stability/index.html)；[CPU 稳定性报告](../../../runs/environment-solvability/fiber_bundling/stability_cpu/index.html)。

```bash
STABILITY_RUN=runs/environment-solvability/fiber_bundling/stability_reproduction
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.validation --backend cpu --output "$STABILITY_RUN/baseline"
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.validation --backend cpu --dt .001 --output "$STABILITY_RUN/half_step"
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.validation --backend cpu --free --output "$STABILITY_RUN/free_hold"
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.assess_stability "$STABILITY_RUN"
```

复查旧的单根红线 demo 时，其余线在端面坐标系中的形状改变约 35–53 mm。因此不能把这条局部动作直接循环八次，也不能用其单根成功结论声称其他线得到保护。新的逐根策略改用固定环的外侧轻压选中线头，准备阶段让其他线远离环；始终通过粗绳根部运动施加边界条件，细线无位置写入、无执行器、无外加力命令。已整理电线的累计形变阈值为 0.5 mm，环支架也参与碰撞。

## 逐根整理与整束穿环 demo

[打开全流程视频与阶段跳转](../../../runs/environment_bootstrap/fiber_bundling/full_bundle_demo/index.html)。物理仿真持续 33.95 s，视频为保存状态的慢放，并逐帧核对回放中心线。只控制粗绳夹持端，尚未执行机械臂真实抓取。

每轮先在环前安全位置转动粗绳，使选中电线的弯曲平面对准接触方向，再把线头移到环外侧。缓慢侧向推进时读取该线头的 x/z 位置，用于微调粗绳，避免在环的曲面上侧滑；细线受到的整理力来自接触。撤开后检查横向包络，再记录其形状，作为后续所有动作的保护参考。八根都准备好后退回环前、对准内孔，一次推进 390 mm，让整段电缆通过。

2 ms 运行全部成功检查通过：8 根细线都曾从孔内跨越环平面，最终所有细线（计入半径）和整段粗绳都越过环后平面。逐根整理后的包络半径为 12.46–12.67 mm；最终推进前，整束对实际净孔仍有 0.817 mm 径向余量。已整理电线全过程累计最大形变 0.080 mm，低于预设 0.5 mm；原生最大接触穿透 0.100 mm，独立检查未发现线间穿透。粗绳后端表面最终超过环后平面 14 mm。

相同策略以 1 ms 时间步独立复跑，也通过完整穿环与已整理线保护检查；最大接触穿透 0.123 mm。对比八次整理结束、推进前和最终状态，两次运行的最大形状差异不超过 0.177 mm，最大 RMS 0.054 mm；最后 0.3 s 保持期间均未测出形状漂移。原始对比见 demo 中的 `timestep_validation.json`；这是对完整动作的额外复核，不把前一节单根轨迹的稳定性结果代替全程验证。

这里的“整理”指形成能够容入孔径的稳定形状，不要求每根线成为严格直线。初期两次探索分别因线间挤压造成已整理线偏移 1.086 mm 和 2.950 mm 而停止，失败结果保存在 `environment-solvability/fiber_bundling/sequential_outer_rim_trial/` 和 `sequential_gentle_trial/`，没有放宽保护阈值。最终采用 35.3 mm 的粗绳轴线到环中心侧向距离，并对齐受压平面。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.sequential --legacy-free \
  --stability runs/environment-solvability/fiber_bundling/stability_cpu/result.json \
  --output runs/environment_bootstrap/fiber_bundling/full_bundle_reproduction
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.sequential --legacy-free --dt .001 \
  --stability runs/environment-solvability/fiber_bundling/stability_cpu/result.json \
  --output runs/environment-solvability/fiber_bundling/full_bundle_half_reproduction
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.assess_sequence \
  runs/environment_bootstrap/fiber_bundling/full_bundle_reproduction \
  runs/environment-solvability/fiber_bundling/full_bundle_half_reproduction
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.render_single_strand \
  runs/environment_bootstrap/fiber_bundling/full_bundle_reproduction --stride 2
```

完整 demo 提供当前模型与显式夹持边界条件下的一条可执行接触路径；机器人关节可达性、真实夹爪保持力、材料参数标定和其他随机种子的成功率仍不在本次结论内。
