# 解绳结：一个松 Trefoil 的基础场景

> **2026-09-27 更新：** 正式 easy 为两次重叠单绳圈；medium 为原 easy 的 overhand_trefoil；hard 为原 medium 的 figure_eight。double_overhand 已移到实验附表。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。

## 冻结实例 oracle 交接与整合（2026-10-03）

已导入用户提供的 `knot_untying_oracle_artifacts.tar.gz`：原始运行、三档 IPC 存档及日志位于
`runs/test_results/knot_handoff_20261003/runs/knot_oracle/`，
[导入清单](../../../runs/test_results/knot_handoff_20261003/import_manifest.json) 记录压缩包与每个文件的 SHA-256。
代码归入 [planning/knot_untying](../../../topogym/planning/knot_untying/README.md)，
执行入口为 `scripts/oracle_runners/run_knot_oracle.py` 和 `run_knot_branching.py`。

| 档位 | 已收到的物理证据 | 本轮状态 |
|---|---|---|
| easy | `easy05` 原生成功，575 actions、5,744 ticks、14.360 s；已有正式实例新进程回放成功日志，exact=true | 原证据已核验导入；单次回放不证明重复确定性 |
| medium | `medium03` 原生成功，1,927 actions、19,268 ticks、48.170 s | 正式初态精确恢复；本轮首遍跑完全部动作但 `success=false, episode_end=null`，第二遍按用户要求取消，原因待查 |
| hard | `hard01` 部分执行 53.075 s，4→3→1，仍有紧卷；没有完整成功 | `hard03` CUDA 初始化失败；`hard04` 在 15.63 s 按用户要求停止，改为从同一冻结初态运行放宽搜索的 `hard05`，结果待验 |

medium 首遍返回值见 [原生结果](../../../runs/test_results/knot_oracle_20261003/medium_first_replay_result.json)。
原命令请求两遍；第一遍完成后在第二遍初态恢复期间暂停，通过只读进程检查保存第一遍
`Session.replay` 的完整返回值，并由原生 session 日志交叉确认。随后停止进程给 hard 释放显存；
不能将进程的人工停止码当成首遍物理失败，也不能称本轮回放通过。末尾静置余量与轨迹偏差尚未区分。

本轮回放使用已冻结工作区源码、`ghcr.io/luigivamper/rcb-topogym:0.2.6-cu128`、
Genesis 1.2.1／libuipc build `292c98c3`。日志与快照在
[本轮验证目录](../../../runs/test_results/knot_oracle_20261003/)。原交接使用镜像 0.2.3，
结果不自动移植给新环境；新进程回放单独记结果。当前源码已启用 `goal_complete=True`，
绳接触摩擦平滑为 1 mm/s；旧 `tasks/` 存档的 physics_options 与此不同，需使用交接的重建实例。
未修改任务判据、绳径、有效体积要求或旧 benchmark 包。

执行保持实例时序：2.5 ms tick × 10、IPC 子步 1、纯摩擦抓持、默认 ALOHA home 起步。
easy 抬起 s=224 mm 的上股 25 mm、沿 −x 搬运 95 mm；medium 远端固定、删交叉再两端拉开。
夹爪命令是实际开口宽度，默认 **5 mm**；两端拉开的抓点离端头 **35 mm**。
零开口会压翻体单元，medium 离端头 15 mm 的旧尝试也失败，保留失败证据而不放宽判据。
hard 的物体路线经验是完整拉 0.55 m，不能在第一次交叉减少时即停止。

本次补全了：实际 tick 计时、原生终止立即收尾、失败退出码、动作前缀存盘、完整决策回溯、
续跑前的实例／tick／绳形核对，以及正式 RGB 实例的新进程 replay 检查。
交叉已清零但原生稳定窗口未完成仍判未解开；分支搜索成功仍须重新回放。
复现和实例重建命令见 [oracle README](../../../topogym/planning/knot_untying/README.md)。
这批证据不扩展到其他 seed、网格／时间步收敛或逐子步机器人禁碰资格；本轮没有新录像。

## 当前 oracle 的点位、路径限制与防穿模边界

本节只核对 Knot 的 easy / medium / hard；初始检查依据 `hard04` 冻结源码，随后按用户要求放宽搜索并重启为 `hard05`。
**三档原生 Task 的固定 XY 终点限制为 0，参考路径匹配限制为 0。原搜索的 2 条操作末尾硬剪枝已放宽，新运行 `hard05` 使用该策略。**
源码哈希和 CPU 判据探针见 [检查记录](../../../runs/test_results/knot_oracle_20261003/constraint_audit/predicate_probes.json)。
检查中 48 个合成终态候选覆盖直绳／弯曲绳、平移／旋转和不同机器人远离位置，均通过候选判据；
6 个无效体积、运动、低于桌面、未释放或机器人过近的反例均未通过。
这些输入使用合成表面环和诊断字段，只证明判据行为，不构成真实 FEM 执行或无穿模证明。

| 层次 | 当前限制 | 如何处理 |
|---|---|---|
| 原生终态 | 不指定绳端坐标、XY 目标区、机器人回 home 姿态或动作阶段顺序；要求无投影交叉／重叠、贴桌、松手、机器人离绳至少 5 mm，速度不超过 1 mm/s、漂移不超过 1 mm，稳定 0.5 s | 保留完成语义；弯曲但无重叠的绳也可以完成。不满足时通常继续等待，并非立即失败 |
| easy 路线 | 固定材料坐标 `s=.224 m`，抬 25 mm、沿 −x 搬运 95 mm；当前 carry 只有一个默认候选 | 这是求解器配方，不是评分规则；若该配方失效，可扩展抓点和搬运方向候选 |
| medium / hard 路线 | 按较短自由端选首个下穿交叉；竖直下夹，拉绳阶段保持抓取方向；主要只有删交叉／两端拉开两类动作 | 已允许同一节点交替尝试两类动作的参数候选，旧规则仅决定优先级；抓点和姿态仍沿用已有物理动作 |
| 原分支硬剪枝 1 | **一次完整操作后**交叉数不减少（`after >= before`）就回退 | 已改为默认允许连续 2 次未刷新本分支最低交叉数的操作；下一次若取得新低可继续。`4→5→4` 不刷新预算，可用 `--max-nonprogress-decisions` 调整上限 |
| 原分支硬剪枝 2 | 两端拉开后仍有材料跨度小于 **12 cm** 的交叉圈就回退 | 已改成 `tight_curl_after_spread` 诊断标记，不再据此回退，允许继续尝试恢复 |
| 搜索与等待预算 | 默认最多 8 层决策、30 次候选；交叉清零后最多再等 10 s | 预算耗尽只能说明本求解器尚未找到解，不能证明其他路径失败 |
| 新进程回放 | 精确核对**初始实例**，执行提交动作及 tick；不要求末态 SHA 与原运行一致，也不检查是否属于已知路线；动作结束后不自动追加静置 | 保留证据身份检查。需要更长静置时显式补动作、重新验证；medium 首遍未成功的原因仍未确定 |
| checkpoint 续跑 | 前缀回放后，绳形／关节必须与该 checkpoint 接近（0.2 mm／0.2 mrad） | 这是恢复控制器状态的前提，不是要求最终回到该位置；保留 |

本轮放宽只改搜索剪枝和动作类别候选，没有修改 Task、绳模型、碰撞参数或正在执行的
`hard04` 快照；不能通过放宽体积有效性、减小绳径或容许穿透来获取成功。
`branching.json` 记录策略版本 `bounded_nonmonotonic_v1`、每次操作的诊断标记和未进展计数。
计数由有效决策前缀重算，回溯和旧 checkpoint 续跑不会带入已丢弃分支的计数。
17 项 Knot CPU 回归通过，覆盖交叉数不变／增加后成功、小紧圈恢复、振荡预算、物理失败拒绝和完整回溯；
这些结果不代表放宽后的策略已经完成新的物理执行。原始判据检查记录保留修改前源码哈希。

用户要求重跑后，`hard04` 保留日志、源码和已有检查点，标为主动取消而非物理失败；
其第一个动作原语尚未结束，未完整写出这段执行的动作前缀。
`hard05` 从相同 hard 冻结初态重新开始，沿用 `hard04` 的物理／几何／资源源码，
只替换 `branching.py`、`cli.py` 和只读回放指标观察器 `replay_audit.py`。
[启动身份记录](../../../runs/test_results/knot_oracle_20261003/hard05_launcher/launch_plan.json)与
[实时状态](../../../runs/test_results/knot_oracle_20261003/background_status.json)可追踪当前版本；
原生成功后自动启动 `hard05_replay` 的正式实例新进程回放。

**防穿模仍有验收缺口。** 原生每 tick 检查 IPC 有效和体单元正体积，末态检查贴桌与机器人离开，
但这些不等价于全程网格无相交。`KnotIK.check()` 能检查机器人对桌面、同臂和双臂碰撞，
目前 `robot_oracle.py` 没有调用它；该函数本身也不包括形变绳的碰撞体。
抓点的中心线间隙、95% 材料跨度停止线和 5 mm 夹爪开口是预防措施，不能代替实际接触审计。
现有贴桌判据允许低于桌面至多 1 mm，这不是已经满足用户“无穿模”要求的证明，也不应继续放宽。
在扩展路线后的正式验收中，需要补充实际机器人／绳／桌面接触检查，并报告时间采样范围；
本轮 native success 或 replay success 均不能单独标成完整无穿模资格。

## 三档物体路线与 IK 的历史记录（2026-09-30）

本节描述当时状态；机器人与终态开关的最新情况以上方 10 月 3 日记录为准。

按"只动绳的路线 → 机器人 IK → 任务 Env 内连续物理执行"的顺序补证据，**机器人物理执行尚未完成**。绳上位置一律用弧长 s（从 A 端起，直绳参考态的材料坐标）；"交叉"指俯视投影中两段不相邻绳的交点；"抓点"指离 s 不超过 6 mm 的那一段绳。

**动作及出处。** 三档只用两类动作：
- 删交叉（node deletion，[HULK](https://arxiv.org/abs/2011.04999)）：从较近的自由端往里找第一个"该端从下面穿过"的交叉，一只手按住、另一只手抓住该交叉之后 35 mm 处抬起并往外拉，每拉 50 mm 重新数交叉（HULK 每次动作后重新感知）。与 HULK 不同，按住的是另一端离端 15 mm 处（v9 demo 的远端固定）：按 HULK 原样按在交叉旁的上股时，两手之间只有约 291 mm 绳，拉开时绳被拉长、松手回弹（`hard_cl_v4/v5`），不采用。
- 两端拉开（Reidemeister move，HULK 与 [SGTM 2.0](https://arxiv.org/abs/2207.07813)）：只剩局部小圈（一个交叉的两次经过之间没有别的交叉）时，两手捏住两端往外拉，小圈翻转消失。
- easy 的两个交叉都是同一条腿压在上面（Reidemeister II 构型），一只手把上面那条腿抬起越过另一条即可。

| 档位 | 只动绳的路线（粗网格，IPC 摩擦平滑 1 mm/s） | 交叉数 | 机器人 IK（CPU，仅运动学） |
|---|---|---|---|
| easy | A 腿鼓包 s=224 mm 抬 25 mm、−x 平移 95 mm、放回 | 2→0，终态判据稳定通过 | 右臂可达，桌面最小间隙 2.1 mm |
| medium | 远端 B 固定；A 侧 s=249 mm 抬 15 mm 沿绳拉 300 mm；两端拉开到约 0.9 m | 3→2→0，稳定通过；绳总长最大 +1.8 % | 左臂按 B、右臂拉 A；两端拉开右 A 左 B；均可达 |
| hard | 远端 A 固定；B 侧 s=1135 mm 抬 30 mm 往外拉 0.55 m；两端拉开到约 1.15 m | 4→1→0，稳定通过；绳总长最大 +1.9 % | 右臂按 A、左臂拉 B；两端拉开右 A 左 B；均可达 |

只动绳的证据与失败轮次见 [README](../../../runs/test_results/knot_object_route_20260930/README.md)；IK 检查见 `runs/test_results/knot_ik_keyframes_20260930/`（`scripts/check_knot_keyframes.py`，竖直下夹、夹指垂直于绳，预抓位与撤离各高 80 mm，查桌面、同臂、两臂与关节限位，绳不作碰撞体）。机器人执行器为 `scripts/run_knot_robot_route.py`，选点规则与只动绳共用 `topogym/planning/knot_untying/route_rule.py`，抓取为纯摩擦（不开抓持辅助）。

**已知边界。** 只动绳的路线用的是 8 边粗网格（约 1.6k 顶点，正式约 3.2 万）并把接触摩擦平滑速度设为 1 mm/s；正式配置未设该参数（libuipc 默认 10 mm/s），此时弯绳以约 3 mm/s 持续蠕动，过不了"最大速度 ≤ 1 mm/s"。机器人执行沿用正式网格与正式接触参数，只把时序改为每物理步 25 ms、40 子步（IPC 积分步长仍为 0.625 ms），原因是正式时序下每模拟秒约 2700 s 墙钟。`KnotUntyingTask.goal_complete=False`，Env 不会报 `task_success`，Harbor 中 knot 的 trial 因而不会判成功；可解性证明直接核对终态判据（无投影交叉/重叠、贴桌、静止、已松手、机器人离开 ≥5 mm、稳定 0.5 s）。


Agent 接入见 [Knot Untying adapter](../../../legacy/cleanup_20260929/docs/develop/modules/knot_untying_agent_adapter_zh.md)：本地文件队列、双臂四图、CUDA FEM 接触辅助与可复制 prompt。该接口的验证状态独立于下述历史 demo。

变体设计见 [固定结型与家族内参数构造方案](knot_untying_family_space_zh.md)：三叶结、开放八字结、双重单结分别作为 easy / medium / hard 的目标代表，每个结型配独立的动作与 IK 路径。三档均要求持续支撑、余量控制和受限方向下的操作；难度须经实际执行及简单路线对照确认，当前 v9 也需补查这一操作要求。新增家族与参数范围目前为设计提案。固定实例可直接选择，参数采样另设入口。

实施与结果见 [物理稳定性验收与三视角全过程 demo 计划](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_physics_demo_plan_zh.md)。已完成 [完整机器人解结录像](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html)，实际连续模拟 75 s，保留五路同步视角。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。详细记录见 [抓持与录像复测](../../../legacy/cleanup_20260929/docs/develop/tasks/knot_untying_recording_attempt_zh.md)。

完整 demo 的 MP4 已按视角独立归档至 `demos/knot_untying/varaition_<id>/<camera>/`；播放页、报告、轨迹和归档清单保存至 `runs/demo_metadata/knot_untying/<date>_<run_id>/`。

本阶段铺设一根绳上只打一次结的场景。采用开放绳的 overhand knot；将自由端从外侧无交叉地闭合后，得到 trefoil / 3₁。物理场景中保留两个自由端，可供后续抓取和退绳。结型参考：[MathWorld](https://mathworld.wolfram.com/TrefoilKnot.html)。

## 几何和配置

源码在 `topogym/tasks/knot_untying/`，Hydra 入口为 `configs/knot_untying_preview.yaml`，基线登记在 `configs/task_cards/knot_untying.yaml`。

| 参数 | 默认值 |
| --- | --- |
| 绳径 | 8 mm |
| 总长 | 约 1.074 m，由曲线和自由端共同决定 |
| 每端余长 | 180 mm，包含平滑转向段 |
| 结形平面尺度 a | 32 mm；参数卡圈径比定义为 2a / 绳径 = 8 |
| 高度幅值 h | 8 mm |
| 初态桌面净距 | 至少 1 mm |
| 网格轴向间距 / 圆周段数 | ≤2.5 mm / 12 |
| 自接触作用距离 | 0.8 mm |
| 材料 | E=100 kPa，ν=0.45，ρ=650 kg/m³，μ=0.3，沿用共享候选值 |
| 材料参考态 | 直绳，初始结形有弯曲预应力 |
| 时间步 / 子步 | 5 ms / 4 |
| 固定或跟随顶点 | 0 |

采用曲线 `x=a(sin t+2 sin 2t), y=a(cos t−2 cos 2t), z=h sin 3t`，截取 `[π+0.5, 3π−0.5]`，升高到桌面之上；两端用切向连续的曲线转向结外，再接直尾。镜像 x 可切换手性。

几何验收检查三个横截交叉、沿绳的交替上下顺序、Gauss 顺序 123123 和一致交叉符号，并确认外侧诊断闭合不添加交叉。因此不是仅凭“有三个投影交点”判断结型。初始管面最小间距使用线段到线段距离；排除沿绳距离小于 πr 的局部邻居，另查局部弯曲半径。

## 运行

Nyx 环境需要额外安装 FEM 接触库；本机补齐的是旧仿真环境已有的同版本：

```bash
uv pip install --python .venv-gs121-nyx/bin/python -r requirements/uv-topogym-fem-ipc.txt
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.knot_untying
.venv-gs121-nyx/bin/python -m unittest tests.check_knot_untying
```

默认输出 [trefoil_initial/index.html](../../../runs/environment_bootstrap/knot_untying/trefoil_initial/index.html)，包含 Nyx 实验室全景、俯视、近景静态图以及自由静置前后状态；不再生成相机环绕视频。`run.settle_steps=0` 仅建场与渲染，不会声明静置通过。

`inspection_report.json` 保存实际求解参数、体网格检查、模拟时长与初末状态；`settle_trace.json` 逐步记录位移与交叉数，`settle_states.npz` 保留实际顶点与中心线。直绳参考态若会翻转四面体，任务在构建前拒绝，不能静默改成结形参考态。

当前预览包含单台待命 Panda＋Robotiq 2F-85；机器人与绳接触已接入，未执行抓取。独立物理探针已加入长时接触检查和 ALOHA 双臂试跑，实际通过范围见上方验收页面。短时预览记录只检查这一初态的有限状态、体单元方向与投影交叉保留，不能代替连续碰撞的全程拓扑认证。

## 本机检查结果

2026-09-16 的默认运行完成 40 步、0.2 s 自由静置。实际体网格包含 6,516 个顶点、21,519 个四面体；直绳参考态和静置末态均无反转单元。三个交叉在每个采样步保留，末态 Gauss 顺序、上下交替和手性复查通过。

最大顶点位移约 37.27 mm，属于初始预弯曲绳的松弛，不能称为静止不动。末态按中心线及名义半径重建的管面净距约 0.48 mm，距桌面约 0.60 mm；这两个数是中心线诊断，不是形变后 FEM 表面的精确碰撞距离。实际报告保存该检查方法和范围。

几何、配置组合、参数卡和当前目录引用共 14 项测试通过；新增 Python 文件通过 Ruff 检查。Nyx 视频已检查为 45 帧、15 fps，只展示初始结形的相机环绕。
