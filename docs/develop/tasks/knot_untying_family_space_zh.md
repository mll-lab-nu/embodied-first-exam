# 解绳结变体：固定结型与家族内参数

**2026-09-21 最新状态：两种新家族仍未完成完整解结。** 八字结 v8 完成 150 mm 支撑展开并释放旧抓点，在 67.000 s 的换抓规划处停止：首选 band 60 的竖直接近路径未达到 3 mm 机器人间隙。53,600 个 IPC 子步全部收敛，最大 Newton 次数 32；最小 det(F) 0.70895，最大局部应变 9.811%，最大长度变化 1.405%。双重单结 v7 完成额外横移，在 58.935 s 的换抓规划处停止：横移后的下穿段移至左臂竖直抓姿的不可达区域。47,148 个子步全部收敛，最大 Newton 次数 26；最小 det(F) 0.69808，最大局部应变 3.204%，最大长度变化 0.596%。两轮均未触发机器人重叠、FEM 表面穿越或桌面穿透检查，但这不等于完整任务通过。五路局部录像分别为 1,340 帧 / 67 s 与 1,178 帧 / 58.9 s，完整解码和同步检查通过，直链见 [试录记录](../../../runs/environment-stability/knot_untying/families_20260919/README.md)。

固定绳形的检查说明：仅换用邻近材料带或翻转夹爪朝向不足以解决这两个姿态问题。新增候选允许夹爪绕闭合轴倾斜，并在真正的材料窗口内选择可通过的抓点；抓点至少位于首下穿点内侧 8 mm。接近与下降的全部离散样本检查 3 mm 机器人间隙及 1 mm 手部/桌面间隙，包含腕部相机外壳和指端球形几何；每个 200 Hz 实测姿态另查冻结的机器人重叠与桌面穿透限值。仍由实际双指表面接触触发辅助抓持，规划器不移动绳节点。

八字结的 [原实际停止状态检查](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v8_spread_checked/pitched_planner_stopped_state_cpu.json)找到 band 60、-30° 倾角的完整接近/下降候选；48 项回归检查通过。[v9](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v9_pitched_regrasp/launch_command.json) 已使用 `figure8_pitched_regrasp_v6` 从初态重新录制。双重单结使用 `double_overhand_pitched_regrasp_v8`：[实际停止状态的完整路径检查](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v7_support_shift_checked/pitched_planner_stopped_state_cpu.json)选择 band 9、45° 倾角及 20 mm 悬停高度，已进入 [v8 队列](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v8_launch_queue.json)。原先仅检查手指端点时可行的 60° 姿态，因相机外壳触及桌面而被完整路径检查拒绝；最终候选同时满足机器人和桌面间隙，不改变原有抬升及退出动作。48 项回归检查包含这两个实际停止状态的倾斜抓取规划，以及可达但触及桌面的反例。两轮旧运行的逐姿态手部/桌面复核均通过，最低模型间隙分别为 4.328 mm 和 4.501 mm。

以下为此前过程记录，实时状态以上述运行入口及 [状态文件](../../../runs/environment-stability/knot_untying/families_20260919/family_status.json)为准。

**2026-09-20 过程记录：两种新家族尚无完整成功 demo。** 八字结 v7 在 59.985 s 主动保存停止，尚未执行到新加入的闭爪追踪。对旧 v6 的实测关节进行逐帧重建，发现 60.95–62.59 s 有 329 个机器人姿态超过已有 CPU 预检的 0.5 mm 重叠限值，最坏在 61.21 s，两只夹爪基座重叠约 1.039 mm；关节限位本身未超出，见 [只读复核](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v6_narrow_approach/recorded_robot_pose_audit.json)。这是离散机器人模型检查，不是原生接触力或连续扫掠证书。基于 v7 已下发的接近轨迹、固定最后实测支撑臂的 CPU 推算也出现约 1.188 mm 重叠，因此先修改换抓空间，不能仅以绳段下沉解释旧失败。

v7 截止停止时的 11,997 个实测机器人姿态未检出上述模型重叠；47,988 个 IPC 子步全部收敛，最大 Newton 次数 54，无警告，未触发原有应变、体积或跟随误差阈值。五路录像均为 1,199 帧 / 59.95 s，通过完整解码及同步检查：[高位](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v7_tracking_regrasp/cam_high.mp4) · [低位](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v7_tracking_regrasp/cam_low.mp4) · [左腕](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v7_tracking_regrasp/cam_left_wrist.mp4) · [右腕](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v7_tracking_regrasp/cam_right_wrist.mp4) · [近景](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v7_tracking_regrasp/detail.mp4)。它仍有交叉，未完成松手与静置，不归档为完整 demo。

旧八字结 v6 于 66.000 s 第二次闭爪未建立双指接触。目标绳段中心在换抓期间下移约 2.84 mm，而工具仍追踪 58 s 时的固定目标；末态绳心比实际工具中心低约 5.85 mm，见 [定位分析](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v6_narrow_approach/regrasp_failure_analysis.json)。这仍是相关位姿证据，但须结合上面的夹爪基座间距问题一起处理。

双重单结 v3 于 43.735 s 因没有满足双手间距的下穿段抓点停止；34,988 个子步全部收敛，最大 Newton 次数 33，无警告。39 s 时允许材料窗口内的候选距支撑抓点约 90–105 mm，低于原定 120 mm；五路录像均为 874 帧 / 43.7 s，完整解码及同步通过，见 [空间检查](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v3_anchored_open/opening_failure_analysis.json) 和 [高位局部 MP4](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v3_anchored_open/cam_high.mp4)。两轮均未完成全部释放及末段静置，不将这些局部记录记作整套物理验收通过。

八字结 [v8 启动队列](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v8_launch_queue.json) 使用 `figure8_support_spread_checked_v5`，已于 2026-09-20 21:50 UTC 在满足同一 11,264 MiB 显存预留后启动。它保持两处实体抓持，在首次计划换抓前将支撑手向外移 150 mm，再根据实际绳形选择新抓点；保留原材料余量限制。换抓接近及下降的离散 IK 路径须有 3 mm 机器人几何间隙，执行期间每个 200 Hz 实测机器人姿态另查 0.5 mm 重叠限值。更高悬停位相应延长下降时间，包含追踪修正后仍遵守 30 mm/s 的既有规划速度界限。[名义前缀预检](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/support_spread_checked_v5_nominal_preflight.json)及从旧记录出发的 [冻结绳形 CPU 对照](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/checked_regrasp_cpu_review.json)通过对应候选检查；二者均不模拟支撑手移动后的绳形，也不认证新换抓或解结成功。

双重单结 v6 于 52.300 s 主动停止。46.2 s 的额外 80 mm 抬升使材料窗口内候选距支撑点约 142、147、154 mm，实际释放 A 端并完成退出后，在 51.735 s 选中材料弧长 0.254814 m 的 band 10。但这些中心线距离主要来自竖直分离，不能保证机器人可接近。对已下发的接近段作 [冻结支撑臂的 CPU 推算](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/predicted_first_undergrasp_approach.json)，发现未来左腕与右手指可能重叠约 30.61 mm，遂在到达该位置前停止。该推算不是未来动力学观测。

停止前 41,840 个 IPC 子步全部收敛，最大 Newton 次数 37，无警告；最小 det(F) 0.6981、最大局部应变 3.224%、最大长度相对变化 0.486%，桌面穿透为 0。[10,460 个实测机器人姿态复核](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/recorded_robot_pose_audit.json)未检出机器人模型重叠或关节越界。五路局部录像均为 1,046 帧 / 52.3 s，通过完整解码和同步检查：[高位](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/cam_high.mp4) · [低位](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/cam_low.mp4) · [左腕](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/cam_left_wrist.mp4) · [右腕](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/cam_right_wrist.mp4) · [近景](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v6_tracking_regrasp/detail.mp4)。尚未抓住打开后的下穿段，不计为完整 demo。

[降低悬停高度的 CPU 候选](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/undergrasp_low_approach_cpu_review.json)在 5–80 mm 的九个高度均未通过 3 mm 机器人间隙检查。[冻结绳形的支撑手位移对照](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/undergrasp_support_offset_cpu_review.json)中，沿 +X 再移 100 或 120 mm 后，40 mm 悬停接近及完整下降通过对应离散检查。因此新增候选 `double_overhand_support_shift_checked_v7`：保持尾端锚定，完成原打开动作后再将支撑手沿 +X 移 120 mm，然后真实释放、退出，按实际绳形重新选择抓点并检查接近路径。此 CPU 对照没有演化绳形，也不证明移动后的抓取或解结可行。 [完整准备前缀检查](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/support_shift_checked_v7_nominal_preflight.json)通过，包含新增横移与尾端退出；[v7 已排队](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v7_launch_queue.json)，等待同一显存预留条件。 另从 v6 的 46.2 s 实测锚定姿态检查新增横移、尾端退出，再接到旧 51.735 s 抓点，三段的 [离散机器人检查](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/support_shift_checked_v7_measured_state_cpu.json)通过 3 mm 间隙条件；抓点被冻结，不预测新横移后的实际绳形。

两种新候选都保留实际换抓时的有限平移追踪：修正速度上限 6 mm/s、相对初次定位点的偏移上限 10 mm；取得双指接触后冻结目标。机器人接近须通过 3 mm 离散模型间隙检查，每个实际 200 Hz 姿态另检查 0.5 mm 重叠限值。它们只改变机器人控制目标，不改写绳状态或提前激活辅助抓持。

双重单结保留尾端固定，横移上穿段后按实际绳形检查后续抓点。若没有达到 140 mm 准备间距的候选，支撑手每次再抬 20 mm，额外抬升最多 80 mm；随后仍执行原定 120 mm 换抓间距检查。抽绳时保留材料余量触发的实际换抓，并采用同样的有限平移追踪。最新 47 项回归检查通过；双重单结的离散预检覆盖横移后抬到最高候选高度及尾端退出，仍不包含 FEM 或真正换抓、解结。先启动的 v5 在静置 4.750 s 保存停止以合并定位修复，未执行操纵，不视为该路线的物理失败。当前状态以上述运行及队列链接为准；下文保留此前过程记录。

2026-09-19 实施中。三个固定模板已落地：`trefoil_open_v1`、`figure_eight_open_v1`、`double_overhand_open_v1`；保留单根开放绳、两个自由端和直绳材料参考态。三叶结复用 v9 的 75 s 完整物理执行，新家族的几何与首段机器人 CPU 预检已通过，静置和连续机器人执行分别记录结果。easy / medium / hard 是目标档位，持续精细操作及难度趋势尚未通过对照检验。已有 v9 的局部物理检查通过，但 P3 网格收敛和通用双手交接验收仍未通过。

实现入口为 [三个固定配置](../../../configs/task_variants/knot_untying/)、[家族加载器](../../../topogym/tasks/knot_untying/families.py) 和 [新家族动作控制器](../../../topogym/tasks/knot_untying/family_actions.py)。[初态对照 PDF](../../../runs/environment-stability/knot_untying/families_20260919/geometry_review/initial_templates.pdf) 只展示几何，不是解结 demo。

| 固定模板 | 初始交叉 | 绳长 | 最小绳面间距 | 机器人参考 yaw |
| --- | --- | --- | --- | --- |
| `overhand_trefoil` | 3，诊断闭合 3₁ | 1.074 m | 3.51 mm | 0° |
| `figure_eight` | 4，诊断闭合 4₁ | 1.241 m | 5.72 mm | 90° |
| `double_overhand` | 5，诊断闭合 5₁ | 1.384 m | 6.82 mm | 90° |

三种绳径均为 8 mm，单侧尾段参数均为 180 mm。表内绳面间距为初态几何诊断，不能替代受载后的 FEM 表面接触检查。新家族的 yaw 是根据双臂实际模型重新选择的参考摆位，并非照搬三叶结的关节轨迹。

## 本轮物理记录

两种新结型均已通过各自一次独立的 10 s 无夹持静置，采用冻结的原有物理阈值。每次检查 8,000 个 IPC 子步，全部收敛，无表面穿越、单元反转或超限桌面穿透；不把这两次局部实验记作整个 P1–P4 套件通过。

| 家族与实际测试朝向 | 最小 det(F) | 末 2 s 最大 RMS 速度 | 末 2 s 最大节点漂移 | 报告 |
| --- | --- | --- | --- | --- |
| 八字结，yaw 0° | 0.778 | 0.174 mm/s | 0.577 mm | [独立静置](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/free_settle_0/report.json) |
| 双重单结，yaw 90° | 0.759 | 0.260 mm/s | 1.639 mm | [独立静置重试](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/free_settle_retry1/report.json) |

八字结的首份静置记录早于机器人参考朝向改为 90°；新的机器人试录会在 yaw 90° 下重新检查抓取前的 10 s 自由静置。双重单结的首次建场因原生 CUDA InvalidDevice 中断，没有进入物理步进，失败日志保存在 `double_overhand/free_settle_0/`，未覆盖或计作通过。随后使用显式 GPU 0 的新进程完成了表内测试；尚未确认该 CUDA 错误的根因。

新路线的录像状态见 [各家族试录记录](../../../runs/environment-stability/knot_untying/families_20260919/README.md)。运行结束后保存 `robot_motion.npz`：实际关节位置、手部位姿、夹爪状态、阶段，以及新路线真正提交的关节控制目标。`execution_metrics.json` 记录分阶段行程和抓持事件，数值本身不认证持续精细操作或难度。

八字结 `robot_v1` 在 18.035 s 附近发生原生 SIGSEGV，未生成最终物理报告；最后完整日志子步为 14,428，最后已保存进度为 18.005 s。此前通过 yaw 90° 的抓取前静置门槛，并于 16.535 s 建立右手双指接触；当时尚未开始解结。五路局部 MP4 均完整解码为 360 帧 / 18 s，但缺少最终逐帧相机日志，不能归档为完整 demo。见 [失败记录](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v1/process_failure.json) 和 [左腕局部录像](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v1/cam_left_wrist.mp4)。`robot_v2` 保持几何、材料与求解参数，增加原生回溯、显存计数和相机日志检查点后重新执行。SIGSEGV 根因尚未确定，不将其直接归因于显存或结型难度。

`robot_v2` 的只读计数确认 Genesis 1.2.1 在无梯度执行中仍为每个子步保留 FEM 检查点，约增长 214 MiB / 模拟秒。该诊断运行于 0.585 s 主动停止。新增 `--bounded-forward-cache` 复用未使用的历史存储，继续调用原始 `save_ckpt` 和帧轮转，不覆盖原生 IPC 节点或修改力学参数；实现位于 [runtime_memory.py](../../../topogym/tasks/knot_untying/runtime_memory.py)。相同初态的 0.585 s 原生对照全部收敛，最终节点最大分量差 1.8 μm、速度差 0.011 mm/s，检查点数量保持为 5，见 [对照记录](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/forward_cache_comparison.json)。这是短时缓存回归证据，不能替代长时物理验证，也尚不能单独确定 v1 的 SIGSEGV 根因。`robot_v3` 使用该开关从原始初态重新录制。

`robot_v3` 已越过原生崩溃位置，完成两次实体接触抓持与抬绳，于 29.240 s 送绳阶段因辅助抓持跟随误差 2.006 mm 超过原定 2 mm 限值停止。23,392 个子步全部收敛，未检出表面穿越、单元反转或超限桌面穿透，但未完成解结或释放。末态压缩最强的单元位于右手抓持段附近并接近桌面，见 [失败定位](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v3/failure_analysis.json)；[低位局部录像](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v3/cam_low.mp4)覆盖 29.2 s，不能作为完整 demo。`robot_v4` 在首次抬绳时同时将支撑手抬高 12 mm，确认支撑绳段离桌至少 2 mm 后再送绳；两家族更新后的离散 IK 路径均通过预检。新增逐手跟随误差及最坏节点记录，验收阈值不变。

`robot_v4` 的前 53 s 已完成送绳和多段抽绳，未触发抓持或力学阈值；仍保留 6 个 XY 交叉，尚未解开。按原始材料弧长检查，首个下穿点距 B 端在 30–53 s 间仍约为 214–234 mm，主要观察到结区移动，不能把工具行程计作退穿进度，见 [状态分析](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v4/material_progress_54s.json)。当前实际支撑点是相反自由端附近；设计中的局部支撑仍需找到通过机器人碰撞检查的抓点。

v4 最终在 60.105 s 主动停止：五段共 500 mm 的抽绳后，目标下穿点材料弧长从 10 s 的 1.02549 m 变为 60 s 的 1.02367 m，未向 B 端有效推进；60 s 有 8 个投影交叉。48,084 个原生子步全部收敛，最大 Newton 次数 38，无警告；最大抓持跟随误差 0.545 mm，最小 det(F) 0.719，未触发几何或应变阈值。该结果只表明已执行动作段的检查情况，未完成双手释放，末段也不满足静置条件。见 [停止依据](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v4/route_window_review.json) 和 [60.1 s 高位局部录像](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v4/cam_high.mp4)；五路均为 1,202 帧且通过完整解码、物理时钟和相机同步检查，不归档为完整 demo。

v4 启动后的源码补充了三个待物理验证的控制细节：跨抽绳段保留抬绳目标高度；按实际夹持绳面最低点规划放回高度；为原本笔直的尾段预留非激活抓持带，以便交叉移到尾部后重新抓取。所有抓持仍须重新满足双指实体接触条件。它们不作用于已启动的 v4；该轮使用的精确代码保存在其 `implementation/`。双重单结 `robot_v1` 从初态独立启动，使用上述更新；它的状态见 [独立进度](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v1/progress.json)。两路试验均未获得完整成功标签。

局部支撑检查发现，原八字结的相邻抓点会使两只夹爪基座相碰。新建独立固定候选 `figure_eight_local_support_v2`：仅将结区平面及高度参数放大 25%，尾段仍为 180 mm，绳径、材料和摩擦不变；绳长 1.461 m，最小初始绳面间距 6.75 mm，参考 yaw 45°。右手选择目标上穿支路内不跨越其他交叉的绳段，左手先向外侧移 100 mm，再分段退穿。这条路径通过初始抓姿、抬绳、送绳、侧移和 300 mm 名义退穿的离散 CPU 检查，见 [最终预检](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/local_profile_v2_final_preflight.json)。此前直线退穿候选仍因夹爪相碰失败，未放宽碰撞阈值。

该候选通过 `--family figure_eight --route-profile figure8_local_curve_v2` 显式选择，配置位于 [独立 profile](../../../configs/task_variants/knot_untying/profiles/figure8_local_curve_v2.yaml)，不替换默认 v1，也不改变外观随机化范围。旧 v1 的物理及外观参数边界检查不适用于此候选。

`robot_v5_local_curve` 通过抓取前静置，随后在 22.560 s 左手闭爪阶段触发 20% 局部轴向应变限制。18,048 个原生子步全部收敛，未检出穿越、反转或桌面穿透；此时只有右手已建立辅助抓持，左手目标段尚未达到双指接触。末态应变集中在另一段材料弧长约 0.841 m 处，距左工具约 25 mm，而目标段为 1.204 m；结合录像，判断张开的手指扫到了邻近绳段。该定位来自最后记录状态，不是累计应变峰值所在原生子步，见 [分析](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v5_local_curve/failure_analysis.json)。五路局部录像均为 451 帧 / 22.55 s，通过完整解码及同步检查；[左腕录像](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v5_local_curve/cam_left_wrist.mp4)不计为完整 demo。

`robot_v6_narrow_approach` 保留同一摆法，改用 [figure8_local_curve_narrow_v3](../../../configs/task_variants/knot_untying/profiles/figure8_local_curve_narrow_v3.yaml)：在空中接近时先把手指滑轨位移收到 0.018 m，再下降和闭爪至实际双指接触；释放后先退出绳区，再完全张开。0.018 m 是滑轨关节位移，不是夹爪净开口宽度。此动作修改不改变材料、接触、辅助抓持强度或验收阈值，离散 CPU 预检通过；连续物理状态见 [v6 进度](../../../runs/environment-stability/knot_untying/families_20260919/figure_eight/robot_v6_narrow_approach/progress.json)，尚未验收完整成功。

双重单结 `robot_v1` 在首个 100 mm 抽绳后仍保留 5 个交叉，首下穿点材料坐标在 30–37 s 仅从 0.32823 m 变为 0.32946 m，没有向 A 端退出。两条交叉绳段同时位于操作夹爪内，提示抓取范围过大；这是位姿与图像诊断，不是非目标接触力的直接测量，见 [停止依据](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v1/route_window_review.json)。该轮主动停止于 37.515 s，30,012 个子步全部收敛，最大 Newton 次数 25，无警告；五路录像均为 750 帧 / 37.5 s 并通过完整解码及同步验证，[左腕局部录像](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v1/cam_left_wrist.mp4)不算完整 demo。后续 `robot_v2_narrow_approach` 使用同一初态和 [double_overhand_narrow_v2](../../../configs/task_variants/knot_untying/profiles/double_overhand_narrow_v2.yaml)重新执行，通过 CPU 预检后启动，尚待连续物理结果。

抓取前报告的历史序列化有一处已修复的问题：`extrema` 和 `failures` 原先引用监控器的可变容器，可能被后续受载过程更新。v3、v4 及修复前已经启动的双重单结 v1、八字结 v5 均保留原始报告，并附 `pregrasp_report_annotation.json`，不把这两个嵌套字段当作抓取前极值证据。10 s 时已计算的检查布尔值、标量及静置窗口数值不受影响；后续 `FemDiagnostics.report` 已改为独立快照并通过回归检查。

双重单结的额外静态诊断发现，在 v1 的 17 s 实际绳形中，首下穿段内侧 25–60 mm 处与非相邻支路的中心线距离仅约 9–10 mm，见 [抓点邻域分析](../../../runs/environment-stability/knot_untying/families_20260919/candidate_grasp_neighbourhoods.json)。这不等于手指接触证书，但说明仅改变闭爪开度可能仍不够。已准备 [double_overhand_anchored_open_v3](../../../configs/task_variants/knot_untying/profiles/double_overhand_anchored_open_v3.yaml) 作为待物理验证的另一条路线：参考 yaw 45°，左手先夹住 A 端并抬离桌面，右手抓目标上穿段，抬高 60 mm 后横移 120 mm；左手实际释放尾端并向前上方退出，再根据变化后的绳形重新抓下穿段。它保留原双重单结几何和物理参数，增加的抓取具有明确的支撑用途，不能仅凭阶段数认定难度提高。

这条新路线的准备、上穿段抬移、尾端释放后的退出已经通过 [离散 CPU 前缀检查](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/anchored_open_v3_final_preflight.json)。直线向上退出的候选因两只夹爪基座相碰而拒绝，采用向前 60 mm、向上 70 mm 的退出方向；未放宽碰撞阈值。该检查**不包含实际接触与绳动力学，也不包含打开后的重新抓取及解结路径**；窄开度 v2 于 18.180 s 主动保存停止，尚未执行下穿段抓取，不据此判断该开度方案失败；14,544 个子步全部收敛，五路局部视频均为 363 帧 / 18.15 s 并通过解码和同步验证，见 [切换记录](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v2_narrow_approach/route_switch_review.json)。`robot_v3_anchored_open` 已从原始初态独立启动同步物理试录，见 [进度](../../../runs/environment-stability/knot_untying/families_20260919/double_overhand/robot_v3_anchored_open/progress.json)。该路线的时间上限为 240 s，以容纳新增的实际准备和换抓动作；抽绳总行程及全部物理阈值未变。

另有尚未运行物理试录的备选 [anchored_adaptive_v4](../../../configs/task_variants/knot_untying/profiles/double_overhand_anchored_adaptive_v4.yaml)。它保留 v3 的打开过程，在抽绳段之间检查当前抓点是否仍位于首下穿点内侧，以及下一段是否会耗尽已限定的材料余量 / 手部行程；需要时先实际松手并重新抓取。总抽绳上限和物理阈值未变。其相同打开前缀通过 CPU 检查，新控制逻辑通过单元检查；这些修改不作用于已经启动的 v3，也不计为新的物理解结证据。

## 变体的两种入口

固定实例与参数采样分别使用：

- **固定实例库**：直接选择已经设计、检查过的实例，完整使用其结型、形状和准备状态。固定形状本身就是变体，不需要再随机扰动一次才算变体。
- **参数实例**：选择一个家族内的模板，再在已登记的参数范围中采样，并为所得实例重新记录检查结果。

建议的数据层次是 `family_id → template_id → instance_id`。家族定义打结结构和端点关系；模板定义一种具体摆法及对应的抓取语义；实例保存精确参数、初态和来源。固定实例可以直接加载；参数采样是另一个入口。

本任务首版保持一根开放绳、两个自由端、一个结区、同一桌面和 ALOHA 双臂。姿态、颜色、绳径变化登记在家族内部。多绳连接、端点固定、绳端封闭和多个串联结另开扩展范围，因为它们会改变任务边界。

## 三个结型与目标难度

| 目标难度 | 家族与固定代表实例 | 对应的操作结构 | 当前证据 |
| --- | --- | --- | --- |
| easy 参考 | `overhand_trefoil / balanced_right`：当前三叶结 | 双臂保持支撑与材料余量，沿下穿段抽绳，再协调展开剩余回环；最后放回、松手 | v9 已完成；持续精细操作与难度比较未实测 |
| medium 候选 | `figure_eight / staged_unthread`：有可操作余量的开放八字结，区分松解区与退穿区 | 支撑局部绳圈、送入余量，随后改变操作方向，沿圈口退穿并退绕；需要时换抓 | 已生成开放 4₁ 模板；B 端下穿段抓取及首段 IK 预检通过，连续执行待验收 |
| hard 候选 | `double_overhand / staged_unwind`：同一结区内多一次绕穿的双重单结 | 在支撑和余量控制下逐层松开、退绕；每层形状变化后重新定位操作段，必要时换抓并调整支撑点 | 已生成开放 5₁ 模板；A 端下穿段抓取及首段 IK 预检通过，逐层实际操作待验收 |

3₁ 与 4₁ 的标准结图可参考 [Knot Atlas：3₁](https://katlas.org/wiki/3_1)、[Knot Atlas：4₁](https://katlas.org/wiki/4_1)。这里的实际物体始终是开放绳，闭合编号依赖明示的诊断约定；诊断闭合线不进入物理场景。[双重单结的原始示范](https://www.animatedknots.com/double-overhand-stopper-knot)给出在 overhand 基础上增加一次绕穿的结构；它不是在绳上串联两个独立单结。当前模板采用 T(2,5) 曲线的开放弧段；外侧诊断闭合对应 **5₁**，参见 [Dror Bar-Natan 的 Knot Atlas：5₁ / Double Overhand](https://www.math.toronto.edu/~drorbn/private/KAtlas/Knots/5.1.html)，不是 5₂。其逆向构造提供解法候选，但不能据此声称机器人已经能够分层解开。

**八字结的可解性边界。** 本任务拟采用单根绳上、两端自由的八字止索结。其打结过程是形成绳圈、让尾端绕过主绳、再穿入圈内；由这一构造可得到逆向退穿的解法思路。[Animated Knots 的八字结原始示范](https://www.animatedknots.com/figure-8-knot)也明确说明它能够解开。若把两端真正接成封闭的 4₁ 结，则在不剪断、不允许绳段穿越的条件下不能变成无结圆环；模板中的诊断闭合线不能变成物理绳段。开放绳的手工可解性不等于当前机器人、夹爪和桌面范围内的执行已通过，八字结仍需实际建立可行路径。

普通八字结并不天然比 overhand 难解；上述示范还指出，overhand 可能收紧得更难松开。双重单结的额外绕穿也不自动证明它需要更多换抓。因此 medium / hard 来自经过设计并实测的代表实例和操作要求。若新代表实例用一次长距离抽绳或当前三叶结路线就能稳定解开，应调整其固定摆法、重新分档或更换候选，不能以结名、交叉数、增加停顿或故意绕路维持难度标签。难度登记在实例及其任务条件上，不推广为结型的固有属性。

## 三档共有的持续操作要求

easy 是本套精细操作任务中的相对低难度档。其完整解结阶段也应有持续的支撑、余量控制与方向约束；一次触发后被动散开的初态不进入正式三档。

- **约束来自实际绳与机器人接触。** 保持一根绳、两个自由端和原桌面；不新增隐藏固定点、沿路径拖动绳节点或形状保持约束来人为造难度。现有接触后辅助抓持须继续显式记录。
- **双臂的相对动作有实际作用。** 支撑手维持结区位置或局部余量，操作手退穿时避免把邻近部分重新收紧；需要时支撑手同步送绳或调整姿态。只让另一只手悬停在旁边不算双臂协调。
- **方向与空间约束持续存在。** 操作手的位置、姿态和夹爪扫掠体应随局部绳段切线、圈口方向及相邻绳段变化。间隙必须足够物理可行，但不能把圈放得无限大，以至于所有方向都可直接抽出；范围由实际检查确定。
- **每一步使用实际状态。** 送绳后测圈口和余量，退穿后确认自由端的位置，换抓后重新确认实体接触，再决定下一段目标。固定 IK 轨迹可作为参考名义路径，但需要状态检查和按阶段更新的目标来应对绳形变化。
- **动作需求用对照检验。** 尝试一次直拉、全程固定支撑手、跳过局部松解、保持初始退穿方向等适配后的简化策略。若这些简化同样稳定完成，应降低该实例的精细操作声明或重设模板；脚本失败本身不证明操作必需。

记录约束有效期间的局部绳面与夹爪间隙、材料余量 / 轴向应变、绳段切线与末端方向、支撑点漂移及每次状态更新的原因，并报告连续受限运动段的弧长及其占有效解结路径的比例；单帧通过一个窄点不足以说明持续操作。当前 v9 报告未提供力测量，余量和应变只能作为相应的状态指标，不宣称已经实现张力闭环。现有 v9 是可行执行参考，尚不能仅凭它的时长和两手抓持判定持续精细操作已通过。

## 三套动作与 IK 路径

三套路径共用 ALOHA 模型和 IK 求解器，各自定义抓取语义、末端位置与姿态、支撑关系和动作切换条件。每个实例重新求解双臂关节轨迹；平移、旋转或缩放旧关节序列不能替代这一步。

| 路径 ID（拟新增） | 解结阶段的末端动作 | 抓持变化 | 阶段切换依据 |
| --- | --- | --- | --- |
| `trefoil_pull_spread` | 支撑臂保持远端，操作臂沿下穿段受控抽绳，检查余量；之后支撑臂向另一侧协调展开残留回环 | 优先复用 v9 两处抓持；目标为一次主要退穿加回环展开 | 实际退穿进度、材料余量和回环状态；保留当前有界行程与释放检查 |
| `figure8_loosen_regrasp_unthread` | 一臂稳定局部绳圈；另一臂送入余量、开圈，按当前圈口姿态改变运动方向，沿分段空间路径退穿、退绕 | 需要时重新抓取；目标为局部松解后进行方向变化的退穿 | 圈口和工具扫掠余量足够、接触状态稳定、自由端退出对应穿绕区域；每段根据实际绳状态更新 |
| `double_overhand_incremental_unwind` | 支撑一层、松开相邻层，沿当前绕穿结构作分段退绕；退开一层后重新定位下一操作段并调整支撑，再继续退穿 | 目标包含有实际作用的重新抓取或支撑角色调整；逐层状态变化后重新规划 | 当前层确已松开，未操作部分没有重新收紧，下一段工具路径可通过；状态确认后进入下一层 |

medium / hard 行中的细化路线是待验证的操作设计，尚不能声称重新抓取、方向变化或每个子目标是任意解法的必要条件。双重单结若只需要把同一抽拉动作延长，不满足这套 hard 设计。开圈时须检查夹爪及所夹绳段的整体扫掠空间；若只能让绳端通过而夹爪过不去，需要先扩大圈口或设计可行的换抓流程，不能靠绳或机器人穿模完成。新原型优先使用一臂维持支撑、另一臂释放后重新抓取，避免把尚未通过通用验收的双手交接作为默认前提。

每套路线都应保存：接近与退出路径、左右臂的分段末端 SE(3) 目标、材料弧长上的抓取带、夹爪开合及接触事件、IK 结果和碰撞检查、完整物理轨迹。不能只交付三个外观不同的初态配同一条动作录像。IK 路径是机器人运动方案；绳的退穿和松解是否发生，以连续物理执行为准。

## 难度梯度如何验收

首轮统一机器人、绳径 8 mm、材料、接触模型、辅助抓持规则、观察相机与任务成功定义。三个代表实例都从未抓住绳的准备位开始，以完整松手和释放后稳定观察结束；记录各自绳长和初始余量。受控收拢程度可以作为明确登记的实例参数，但不采用极端锁紧、更改摩擦或制造求解异常来代替持续操作难度。

已保存一次 [实际抓点邻域对照](../../../runs/environment-stability/knot_untying/families_20260919/grasp_neighbourhood_comparison.json)：在支撑手已抓住、操作手尚未接近时，目标材料点距最近非相邻支路中心线，三叶结 v9 约 39.1 mm、八字结 v6 约 19.4 mm、双重单结原 v1 约 9.5 mm。三者统一排除材料弧长 ±75 mm 内的邻点，绳径均为 8 mm。它描述具体抓点的拥挤程度，支持为双重单结设计预打开动作；不是手指扫掠净距、精确变形绳面间隙或难度认证，也不是新 v3 打开后的测量。

- **先有三条成功参考执行。** 各自的专用路径应可靠完成任务；单条路径较差导致失败多，不能证明结更难。
- **比较有用的操作复杂度。** 排除接近、统一放回与录像停顿后，统计有效换抓次数、需要按顺序完成的解结子目标、受限运动段中的方向变化、局部通行余量及真实动作行程。目标是 easy 的单次主要退穿加协调展开、medium 的局部松解加方向变化的退穿、hard 的逐层操作与抓取 / 支撑调整；当前 v9 的 75 s 不构成任何难度档的依据。
- **检查简单解法是否能跳过设计阶段。** 对三档都尝试经过公平抓点适配的一次端点直拉、固定支撑下的下穿段抽拉加展开、以及省略送绳或保持初始方向的路线；medium / hard 另查省略换抓或逐层状态更新，使用相同的行程和接触限制并记录真实过程。如果更简单的路线也可靠完成，就调整难度归类或将其排除出持续精细操作实例集；不把一次 IK 失败或某个固定脚本失败当作操作必需性的证明。
- **在小扰动集上比较。** 首轮建议各实例检查基准加八个单轴扰动：x、y 各 ±5 mm，yaw ±5°，结区尺度 ±5%。这九个条件只是拟定检查集。分别记录参考路线和共同基线策略的成功率、换抓次数与有效动作代价，机械或求解无效的候选单独剔除并报告。
- **最后才扩大参数域。** difficulty 与 family 分别存储；参数变化后若实例变成可一次抽开的简单情况、或出现额外换抓需求，重新分档或拒绝进入目标难度集合。目标是三组代表实例呈现稳定、可解释的趋势，不宣称不同家族的所有参数组合严格全序。

在这套目标下，当前三叶结先作为 easy 参考，八字结作为 medium 候选，双重单结作为 hard 候选。三档都需通过持续操作要求；若当前三叶结的实际路径对局部方向和余量不敏感，也需要补充或调整固定模板。三种结型是首批交付主体，三叶结的镜像与尾长变化属于后续家族内扩充。

## 三叶结家族先做什么

在三个不同结型的代表实例之外，三叶结家族后续可扩充以下模板；这些模板不充当 easy / medium / hard 的三个不同结型：

| 模板 | 初态设计 | 用途与现有支持 |
| --- | --- | --- |
| `balanced_right` | 当前右手松结，两端各 180 mm，绳径 8 mm | 保留现有基准和 v9 证据 |
| `balanced_left` | 同一右手模板的镜像；尺寸和余长不变 | 当前几何已支持 `handedness=left`；抓取角色与整段动作需重新求解，尚无本轮物理证据 |
| `asymmetric_tails` | 结区保持基准形状，两端余长初步选 120 / 240 mm，总余长仍为 360 mm | 测试端点选择和抓取余量；当前只有共同的 `tail_length_m`，需增加两端独立长度支持并验证转向段 |

左右手结在本任务中归入同一个操作家族，但保留不同的 `handedness` 和模板身份，不把镜像当作平面旋转。`asymmetric_tails` 的两端按沿绳的 A / B 身份登记，不按画面左右命名，也不默认短端一定是正确操作端。

之后可补充一个经过设计的偏斜结区模板，让圈口偏向一侧；这需要有边界的平滑变形和交叉结构复核。固定模板的准入以其代表实例的检查为准，候选名字不等于已经可用。

## 首轮只提供三个可选外观参数

固定配置默认不随机。`--appearance-seed N` 以 NumPy 的局部随机生成器产生可复现配置，并保存解析后的全部参数；不会修改全局随机状态。

| 配置字段 | 候选范围 | 作用与验收边界 |
| --- | --- | --- |
| `appearance.shape_scale` | `[0.95, 1.05]` | 同比例缩放结区平面、高度与尾段；绳径保持 8 mm，实际总长改变，须重新检查网格、物理和 IK |
| `appearance.yaw_deg` | `[-4°, +4°]` | 相对各家族参考朝向的小幅桌面旋转；须重新解 IK 并检查扫掠碰撞 |
| `appearance.rope_color` | `orange / blue / teal` | 只影响渲染；不改变材料、摩擦、质量或控制 |

朝向最初尝试 ±8°，18 个新家族 CPU 边界组合中有 4 个因 IK 或机械臂自碰失败；收窄至 ±4° 后，尺度 × 朝向的 18 个组合均通过初态几何及首段机器人离散预检。加入支撑手离桌动作后，18 个组合再次全部通过，见 [更新后的记录](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_yaw4_support_lift/report.json)；原有路径的 [记录](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_yaw4/report.json)继续保留。该预检仍不覆盖绳动力学、连续扫掠或后续换抓。

上述 18 个组合仅覆盖两个原 v1 模板。独立 `figure8_local_curve_v2` 的九个尺度 × 朝向边界组合也已通过离散 CPU 检查，见 [v2 外观预检](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_local_v2/report.json)；同样不覆盖 FEM、连续扫掠或后续换抓。其固定结区放大属于模板设计，不计作随机采样。

双重单结 `anchored_open_v3` 的九个尺度 × 朝向边界组合中，**7 个通过** [打开前缀的 CPU 检查](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_anchored_v3/report.json)。尺度 0.95、相对 yaw 为 0° / +4° 的两个组合在尾端退出时发生夹爪基座自碰，必须拒绝这条路径或重新规划退出。该路线可先从尺度 `[1.0, 1.05]` 的候选开始；这仍不是连续可执行域认证。检查包含 A 端抓取位姿、上穿段抬移和尾端退出，不包含绳动力学或打开后的换抓、抽绳。

当前候选的边界检查已单独重做：八字结 `figure8_support_spread_checked_v5` 的九个尺度 × 朝向组合全部通过 [名义抽绳及支撑手展开前缀](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_support_spread_v5/report.json)；双重单结 `double_overhand_support_shift_checked_v7` 的九个组合全部通过 [打开、最终横移及尾端退出前缀](../../../runs/environment-stability/knot_untying/families_20260919/appearance_cpu_preflight_support_shift_v7/report.json)。这是各自路线的离散 CPU 边界采样；没有模拟绳状态，也未检查变化后的真实换抓。旧 v3 的 7/9 结果仍保留，不由新路线替换为通过。


这些是**已实现的候选采样范围**，不是已认证的连续参数域。采样前保持固定模板身份，采样后重新生成几何并运行检查；不继承基准 demo 的成功标签。首轮不同时开放尾长、绳径、摩擦或松紧程度，避免参数过多。后续若需要同一根绳的摆法对照，再引入固定总长和受控收拢准备过程。

## 实际运行入口

以下命令均从仓库根目录运行，GPU 环境使用 `.venv-gs121-nyx`。输出目录必须新建；已有报告或运行证据会拒绝覆盖。

```bash
# CPU：三个模板各有 prepare_assets --family；新家族的首段机器人预检示例
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.family_preflight \
  --family figure_eight --output runs/environment-stability/knot_untying/new_figure8_preflight.json

# GPU：未夹持的自由静置；只有静置阈值未满足时才延长同一次运行
PYOPENGL_PLATFORM=egl OMP_NUM_THREADS=2 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.knot_untying.physics_probe --family figure_eight \
  --mode free_settle --without-robot --seconds 10 --extend-to 30 --friction-eps 0.001 \
  --output runs/environment-stability/knot_untying/new_figure8_settle

# GPU：新家族专用路线；包含开爪接近、实体接触后辅助抓持、解结和完全释放
# 达到执行上限仍未完成会失败；180 s 是上限，不会为了录像强制等待。
PYOPENGL_PLATFORM=egl OMP_NUM_THREADS=2 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.knot_untying.physics_probe --family figure_eight \
  --mode family_untying --seconds 180 --friction-eps 0.001 --record --bounded-forward-cache \
  --output runs/environment-stability/knot_untying/new_figure8_robot
```

替换 `--family double_overhand` 使用另一套初态和路线。`family_untying` 强制采用 ALOHA、原生刚体表面审计和 external articulation；不能关掉机器人碰撞后获得成功标签。新家族禁止使用旧 `robot_untying` 控制器；三叶结 v9 继续使用其既有 `remote_adaptive_spread` 路线。

物理报告保留 `passed`、`untying_verified`、`complete_physics_suite_passed` 三种范围。局部执行通过不等于完整套件通过。`robot_preflight_v1.json` 仅检查离散机器人姿态：不模拟绳，不认证连续扫掠碰撞，也不认证后续状态相关换抓。新路线先在当前机器人准备位与参考朝向下自由静置 10 s；重新核查无载绳长、稳定速度、漂移和结图，失败即在抓取前终止。每段按实际绳形定位下穿段与材料余量；换抓必须先松手，再重新确认两指物理接触。录像由同一次物理执行同步采集五路相机，完成后独立归档至 `demos/knot_untying/<camera>/`，不新建 HTML。

## 构造与检查路径

参数实例遵循“模板 → 参数派生 → 几何检查 → 准备与静置 → 机器人检查 → 执行”的顺序。固定实例加载已经保存的初态和证据，并核对环境版本与资产哈希；环境变化时重新确定证据适用范围。

1. **保持模板身份。** 预先给出中心线顺序、上下穿关系、端点标签、结区、可操作绳段和外侧闭合约定。几何检查验证模板没有被错误生成；不另设数学可解性证明阶段。
2. **保持物理合法。** 复核绳管自交、桌面净距、局部弯曲半径、体网格和直绳材料参考态。尺度变换后的初态必须重新静置；不能因为同属一个家族就继承旧运行的物理结论。
3. **避免任务在接近前自行消失。** 在与机器人接近时长相符的静置窗口后仍应保留预定结区和可抓取段。自然松脱的候选单独记录，不能混入要求主动解结的实例。
4. **随形状重算操作。** 保存抓取语义，例如“目标交叉的下穿段”“A 端的可夹持段”“释放端”；在实例的实际状态中定位，再计算 IK、接近、抽绳、放回和退出。可借鉴 [HULK 原论文](https://arxiv.org/abs/2011.04999)的任务相关关键点思想；这里的实例生成与动作适配是本项目的设计。
5. **记录失败与通过范围。** 分别记录几何检查、静置检查、机器人预检、实际任务执行及完整物理套件状态。旧 oracle 失败不能直接归因为实例无解，也不能把未经实际执行的实例登记为完整 demo。

解开后的判定继续结合连续过程中的接触合法性、完整松手和释放后的状态。XY 投影交叉数可辅助当前桌面模板诊断，但不能作为所有家族、任意空间摆法的通用拓扑判据，也不要求解开后的绳必须笔直。

## 当前实现及尚未验收的部分

| 位置 | 本轮实现 | 保留的限制 |
| --- | --- | --- |
| `geometry.py` | 三种固定曲线；各自交替交叉顺序、有向交叉数、诊断闭合、间距与网格检查 | 结图识别只适用于所设计的 XY 投影，不是任意空间曲线的拓扑算法 |
| `families.py / configs/task_variants/knot_untying/` | 模板注册、参考摆位、三个可选外观参数与 seed 复现 | 参数域须逐实例验收 |
| `scene.py` | 注册模板共用 FEM+IPC、直绳参考态和物理机器人 | 建场或单元合法性失败直接拒绝 |
| `family_actions.py` | 两个新家族使用不同操作端、语义抓点与分段目标；实际交叉变化触发换抓 | 路线是待执行候选；送绳、换抓的必要性及难度尚未证实 |
| `physics_probe.py / physics_suite.py` | 家族选择、逐子步接触审计、失败保存、同步录像 | 未放宽冻结的物理阈值；完整套件仍单独验收 |
| `recording.py / physics_review.py` | MP4 与 Markdown / JSON 报告 | 不生成新的 HTML 展示页 |

新模板保存在 `assets/tasks/knot_untying/{figure_eight_v1,double_overhand_v1}/`；旧 `trefoil_v1` 的中心线保持逐点一致。原始实验保存在 `runs/environment-stability/knot_untying/families_20260919/`，成功连续执行才作为完整 demo 归档，失败记录继续保留。

## 首批实施顺序

1. **保留当前右手三叶结作为 easy 参考并复查操作要求**：整理模板与语义抓点，核查实际支撑、余量和方向约束；必要时增加受控摆法，维护原 v9 的证据与物理验收状态。
2. **构造开放八字结 medium 候选和专用路径**：完成局部支撑、送绳松解、方向变化的退穿与退绕，并检查这些动作是否有实际作用。
3. **构造双重单结 hard 候选和专用路径**：验证在当前夹爪下逐层松解、换抓 / 支撑调整和退绕是否可行；若只是一次更长的抽拉，就修改固定模板或更换 hard 候选。
4. **交付三个不同结型的三套实际执行录像与路径证据**，在上述小扰动集和简单路线对照上检查持续精细操作与难度趋势。未完成的家族保持候选状态。
5. **扩充家族内固定模板，再逐轴探索参数**：位置 / yaw、结区尺度与尾长、绳径及受控收拢；保留难度分档。候选域经检查后才开放随机采样，记录接受率与拒绝原因，并将测试模板或参数边界留作独立评测。

默认交付物是固定实例库加一个可选的条件采样器；候选域、可用实例和已完成机器人 demo 分别登记。

## 现有基准视频与证据

以下均为已有 v9 的同一次 75 s 实验执行，本轮尚未生成新家族的完整成功视频。起点为张爪准备位，双指接触后使用辅助抓持，末段解除并自由静置；局部检查通过，完整物理套件仍未通过。

| 视角 | 完整 MP4 |
| --- | --- |
| `cam_high` | [高位全景](../../../demos/knot_untying/cam_high/2026-09-17_bounded_spread_trefoil_v9_cam_high.mp4) |
| `cam_low` | [低位全景](../../../demos/knot_untying/cam_low/2026-09-17_bounded_spread_trefoil_v9_cam_low.mp4) |
| `cam_left_wrist` | [左腕](../../../demos/knot_untying/cam_left_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_left_wrist.mp4) |
| `cam_right_wrist` | [右腕](../../../demos/knot_untying/cam_right_wrist/2026-09-17_bounded_spread_trefoil_v9_cam_right_wrist.mp4) |
| `detail` | [结区近景](../../../demos/knot_untying/detail/2026-09-17_bounded_spread_trefoil_v9_detail.mp4) |

[实际报告](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json) · [归档清单](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/archive_manifest.json) · [物理计划与验收范围](knot_untying_physics_demo_plan_zh.md)

另对 v9 保存的真实中心线做了 [材料退穿诊断](../../../runs/environment-stability/knot_untying/families_20260919/overhand_trefoil/baseline_motion/observed_underpass_progress.pdf)：初始目标下穿点沿 A 端方向退出，之后余下交叉在后续抽绳和右手展开阶段消失。首个交叉消失后，“首个剩余下穿点”的身份会改变，因此曲线会跳变；该曲线不是单调完成度或新的拓扑证明，也不能单独证明某个动作不可省略。
