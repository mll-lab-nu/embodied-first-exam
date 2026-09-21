# 解绳结：机器人抓持与录像复测

已完成并归档 75 s 连续机器人解结录像，包含四路 ALOHA 标准相机与一路近景。[同步播放](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/index.html) · [实际报告](../../../runs/demo_metadata/knot_untying/2026-09-17_bounded_spread_trefoil_v9/report.json)。从双手张爪准备位开始，双指接触后使用显式辅助抓持；松手时解除全部约束。本次轨迹的局部物理检查通过，P3 网格收敛及通用双手交接验收仍未通过。

## 早期接触试录

[同步播放页](../../../runs/environment-stability/knot_untying/trefoil_robot_v2/grasp_recording/index.html) · [原始报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v2/grasp_recording/report.json)

- 同一次连续仿真，四路 ALOHA 标准相机加 `detail` 近景；每路 197 帧，10 fps，19.7 s。实际仿真在 19.75375 s 停止。
- 19.690 s 左手两指与 FEM 表面的最小间距分别为 0.775 / 0.798 mm，进入声明的 0.8 mm 接触作用距离，随后启用显式辅助抓持。
- 闭爪目标在接触时冻结，但实测手指仍继续内收；19.75375 s 检出抓持带内单元翻转，最小 `J=-0.0184`。这段记录不能认证抓持或解结成功。
- 15,803 个实际 IPC 子步均有原生收敛记录，最大 Newton 迭代数 38；求解器收敛并不能排除局部单元翻转。

原接近路径在前臂滚转接近 −π 时触发限位错误。新入口用原 ALOHA 模型做有界 IK，先求悬停位姿再平滑插值关节目标；仿真仍由执行器驱动，没有逐帧重写机器人或绳状态。它已经完成原先失败的接近阶段。

## 关节耦合复测

使用 `external_articulation` 隔离原逐连杆软耦合对抓持的影响。它改变机器人与 IPC 的耦合方式，属于新候选配置，不能继承旧实验的抓持通过状态。

该后端禁止构建后直接设定关节状态，因此中立关节姿态在刚体求解器构建后、IPC 构建前声明，并同步首次关节增量的参考。不能通过改写 `joint.init_qpos` 代替实际初始化；那会改变关节坐标参考，与原模型的正向运动学不一致。错误初始化的短诊断和主动停止记录保留在 `trefoil_robot_v3/external_build_home/`、`contact_recording/`，不计为有效抓持验收。

修正后的 [构建核对报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v3/external_reference/report.json) 仅模拟一个控制步；双手 Genesis 实测位置与原模型 FK 的差异均约 0.0002 mm，只验证初始化。其后的 [9 s 接触复测](../../../runs/environment-stability/knot_untying/trefoil_robot_v3/contact_reference_recording/index.html) 没有检出绳单元翻转，但没有建立双指接触，未执行抬升和释放。原生日志还记录一次 Newton 达到 100 次迭代上限，见 [完整日志复核](../../../runs/environment-stability/knot_untying/trefoil_robot_v3/contact_reference_recording/solver_audit.json)；该配置不通过。

继续核对发现了独立的关节轴接口问题：Genesis 1.2.1 声明旋转关节时反转边顶点，而当前 pyuipc 0.0.25 的原生旋转正向因此与 Genesis 相反。0.1 s 腰部正向运动中，显示机器人与 IPC 碰撞体的手指位置相差约 19 mm，见 [原始位姿核对](../../../runs/environment-stability/knot_untying/trefoil_robot_v3/native_pose_audit/native_pose_audit.json)。初始 FK 一致并不能证明动态碰撞体一致。

任务内 `ipc_compat.py` 在构建关节约束时抵消这一反向，不在运行中改写关节或刚体位姿。同一动作的 [修正核对](../../../runs/environment-stability/knot_untying/trefoil_robot_v3/native_pose_axis_corrected/native_pose_audit.json) 中，最大连杆位置差降至 0.391 mm。兼容修正只接受实测的上述版本组合；换版本需重新核对。新机器人试跑另加原生碰撞表面与 Genesis 表面的逐控制步误差检查，超过 2 mm 即停止。

轴方向修正后的 [9 s 抓持复测](../../../runs/environment-stability/knot_untying/trefoil_robot_v4/contact_axis_corrected/index.html) 已结束：7200 个子步全部收敛，最大 Newton 迭代数 40，无绳单元翻转；原生机器人表面与显示表面最大差 0.520 mm。但双指抓持判定仍未触发，未进入抬升和释放，不能认证抓持通过。

原判定只计算绳顶点到手指表面的距离，会漏掉边—边及反向顶点—面的接触。已改成 ipctk 完整表面特征距离，并用“双方顶点都远离对侧表面，只有边相距 0.5 mm”的反例验证；间距仍须进入原定 0.8 mm 接触范围，没有放宽门槛。距离记录中的 `null` 表示查询范围内未发现接触候选，不表示间距为零。

补全表面特征后的 [18 s 复测](../../../runs/environment-stability/knot_untying/trefoil_robot_v5/contact_surface_features/index.html) 已通过，见 [实际报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v5/contact_surface_features/report.json)。8.545 s 建立双指接触后启用辅助抓持，抬升 20 mm、放回，12 s 解除约束，随后自由静置。14,400 个子步全部收敛，最大 Newton 迭代数 35；无穿透或单元翻转，最小 J=0.855，抓持跟随最大误差 0.633 mm。末两秒 RMS / 最大速度分别为 0.128 / 0.328 mm/s，最大漂移 0.604 mm。构建前声明左手张爪悬停初位；中立位到准备位的运动未录制。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --mode robot_contact --seconds 18 --friction-eps .001 \
  --robot-coupling external_articulation --pregrasp-start \
  --record --fps 10 --resolution 640 360 \
  --output runs/environment-stability/knot_untying/trefoil_robot_v5/contact_surface_features
```

该目录已经用于实际运行；复跑应另取新目录。`robot_contact` 只检查单手抓持、抬升、放回和释放，不代替 P4 的双手交接。

## 后续候选动作与交付边界

`untying.py` 提供右手固定远尾端、左手抓取材料弧长约 250 mm 的下穿绳段，抬升后向左抽出、放回和释放的状态机。抽出下穿绳段的思路参考 [HULK / BRUCE 原始论文](https://arxiv.org/html/2011.04999)；改用远尾端支撑及早期 400 mm 路径是本任务的候选设计。该早期路径未完成解结，后续成功的 v9 在分段抽绳后增加受限展开，见下文。

原邻近支撑方案的 [互碰检查](../../../runs/environment-stability/knot_untying/trefoil_robot_v4/pair_collision_preflight.json) 发现腕部 / 夹爪重叠，因此候选改成远尾端支撑，并将场景沿 x 平移 −110 mm。[新抓点检查](../../../runs/environment-stability/knot_untying/trefoil_robot_v4/remote_anchor_preflight.json) 仅验证可达性与机器人模型互碰，不能替代绳的物理执行。初始双手张爪准备位在构建前声明，视频需明确说明未覆盖中立位到准备位的运动。

[完整路径的 205 个采样姿态](../../../runs/environment-stability/knot_untying/trefoil_robot_v5/remote_anchor_full_preflight_v2.json) 通过可达性和机器人互碰检查后的 [51 s 实际录像](../../../runs/environment-stability/knot_untying/trefoil_robot_v6/remote_anchor_recording/index.html) 已结束：四路标准相机加 `detail`，每路 1020 帧、20 fps、960×540。流程为静置、右手固定远尾端、左手抓下穿段、抬升 15 mm、20 s 内抽出 400 mm、放回、43 s 解除两处辅助抓持、退出、自由静置到 51 s。源码快照随配置保存，运行中没有人为改写绳节点或机器人关节状态。

[实际报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v6/remote_anchor_recording/report.json) 中，40,800 个子步全部收敛，最大 Newton 迭代数 40；全部局部力学检查通过，最小 J=0.761，最大总长度变化 0.619%、局部轴向应变 3.777%，无穿透、翻转或刚体互穿。双手分别在 9.570 / 16.545 s 建立实体双指接触，43 s 解除全部抓持；跟随误差最高 0.242 mm，机器人表面对齐误差最高 0.284 mm。末两秒 RMS / 最大速度为 0.164 / 0.426 mm/s，最大漂移 0.730 mm。

本次失败项仅为解结结果：末态仍有三个投影交叉，第一个交叉距自由端约 11 mm。`passed=false`、`untying_verified=false`，不能收录为完整解结 demo。两处实际抓持与释放通过，不替代通用双手交接验收。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --mode robot_untying --seconds 51 --friction-eps .001 \
  --robot-coupling external_articulation --pregrasp-start --x-offset -.11 \
  --record --fps 20 --resolution 960 540 \
  --output runs/environment-stability/knot_untying/trefoil_robot_v6/remote_anchor_recording
```

前一轮 P3 网格收敛仍未通过，见 [物理计划与报告](knot_untying_physics_demo_plan_zh.md)。本轮没有修改冻结的验收阈值。这些未通过的试录保留在 `runs/environment-stability/`；通过完整执行检查的 v9 已按视角独立归档至 `demos/knot_untying/varaition_<id>/<camera>/`，并在 `runs/demo_metadata/` 保存配套证据与归档清单。

## 分段补充抽绳试录

`remote_adaptive` 沿用相同初态、两个材料抓点、材料参数与物理阈值，先抽 450 mm；若还有投影交叉，每段用 3 s 再抽 25 mm，在段末静止时重新检查，最大总行程 550 mm。交叉清零或达到行程上限后，依次放回 3 s、松手退出 3 s、自由静置 5 s；全过程为 51–63 s。基本抽绳峰值速度为 33.75 mm/s，补充段为 12.5 mm/s。左手退出方向调整为 +60 mm x / +80 mm z，避开更远端的竖直退出可达性限制。

[最大路径范围](../../../runs/environment-stability/knot_untying/trefoil_robot_v6/adaptive_maximum_envelope_preflight.json) 已做 CPU 可达性与机器人互碰检查；它不是动力学证据。分段停止、行程上限和释放后观测时长也已加入测试，相关 41 项测试通过。实际录制输出到 `runs/environment-stability/knot_untying/trefoil_robot_v7/adaptive_recording/`，最终结论以本次报告为准。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --mode robot_untying --seconds 63 --friction-eps .001 \
  --robot-coupling external_articulation --pregrasp-start --x-offset -.11 \
  --untying-route remote_adaptive --record --fps 20 --resolution 960 540 \
  --output runs/environment-stability/knot_untying/trefoil_robot_v7/adaptive_recording
```

另有 `understrand` 方向及旋转场景的 CPU 预检，只作为备用规划；尚未执行物理试录，不能计为解结成功证据。

## 残余回环的备用展开动作

v7 的 [63 s 实际录像](../../../runs/environment-stability/knot_untying/trefoil_robot_v7/adaptive_recording/index.html) 已结束。约 37 s 将交叉从三处减为两处，约 47 s 抽出自由端后剩一处绳身回环；52 s 达到 550 mm 左手行程上限，55 s 解除全部抓持，63 s 末态仍有一处回环交叉。[实际报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v7/adaptive_recording/report.json) 的全部局部力学检查通过：50,400 个子步全部收敛，最大 Newton 迭代数 75，无警告、翻转或穿透；总长度变化最高 0.687%，局部轴向应变最高 6.673%。末两秒 RMS / 最大速度为 0.283 / 0.529 mm/s，最大漂移 0.995 mm。抓持跟随误差最高 0.291 mm，机器人表面对齐误差最高 0.284 mm。

五路视频均为 1260 帧、20 fps、960×540，完整解码与同步检查通过。失败项仍是末态及释放后观察窗的交叉未清零，`passed=false`、`untying_verified=false`；未进入完整 demo 目录。本轮源码快照保留实际运行版本。

已另接入 `remote_adaptive_spread` 候选：沿用相同抓取和分段抽绳，只有达到 550 mm 上限且仍有交叉时，才保持左手位置，在 20 s 内向右移动支撑手，将抓点间直线距离展开到 780 mm。当前抓点间材料长度约 810 mm，保留余量；若余量不足或右手位移超过已检查的 400 mm 范围，控制器拒绝执行。右手展开峰值速度不超过 30 mm/s。随后仍是放回 3 s、松手退出 3 s、自由静置 5 s，最大总时长 83 s。

[实际控制代码的 CPU 路径检查](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/spread_actual_code_preflight.json) 中，展开、放回和退出共 125 个姿态无机器人互穿，最小关节限位余量约 0.190 rad；预估右手展开 370.9 mm。该检查使用模拟抓持对象，只验证 IK、路径及状态机，不构成动力学或解结证据。相关 45 项测试与 Ruff 检查通过，包括展开范围、材料余量、完整释放时窗及松手后支撑手不退回旧目标的回归检查。

v8 物理录制已结束，沿用冻结的物理阈值及四路 ALOHA 标准相机；`detail` 改用较陡的俯视角，减少前臂遮挡并覆盖展开范围。首段 `spread_recording/` 在 0.37 s 因首帧瞄准点偏移主动停止，未执行抓取，不计为动力学失败或完整录像。修正时按实际场景原点计算相机目标，并完成 [实际配置的视野范围检查](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/detail_camera_preflight.json)。83 s 连续录制从原初态重新开始，见 [同步播放页](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/spread_recording_v2/index.html) 和 [实际报告](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/spread_recording_v2/report.json)。

本次 66,400 个子步全部收敛，最大 Newton 迭代数 25，无警告、翻转或绳表面穿透；全部局部力学检查通过。最小 J=0.630，总长度变化最高 2.507%，局部轴向应变最高 12.083%。两处抓持均由实际双指接触触发，75 s 解除全部约束，跟随误差最高 0.530 mm，机器人表面对齐误差最高 0.284 mm。末两秒 RMS / 最大速度为 0.264 / 1.397 mm/s，最大漂移 0.913 mm。五路视频各 1660 帧、20 fps，完整解码及同步核对通过。

约 62.8 s 清除原结芯的全部投影交叉；继续拉到 780 mm 间距后，自由绳尾再次搭到主体，末态保留一处交叉。失败项仅为末态及释放后窗口的交叉检查，未放宽判据，未归档至完整 demo 目录。轨迹诊断见 [展开前后](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/diagnostic_spread_57.png) 和 [63 / 71 s 对照](../../../runs/environment-stability/knot_untying/trefoil_robot_v8/diagnostic_spread_71.png)。资源等待仅暂停本次进程的墙钟执行，不修改任何物理状态；等待记录随原始结果保留。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --mode robot_untying --seconds 83 --friction-eps .001 \
  --robot-coupling external_articulation --pregrasp-start --x-offset -.11 \
  --untying-route remote_adaptive_spread --record --fps 20 --resolution 960 540 \
  --output runs/environment-stability/knot_untying/trefoil_robot_v8/spread_recording_v2
```

## 收短展开间距的复录

v9 保留相同初态、抓点、分段抽绳、材料、接触设置和验收门槛，仅将可选右手展开改为 12 s 内达到 650 mm 抓点间距，随后放下 3 s、松手撤离 3 s、自由静置 5 s，最大总时长 75 s。新增 `--spread-span` 与 `--spread-duration` 明确记录这两个动作参数；控制器仍拒绝余量不足、位移超过 400 mm 或峰值速度超过 30 mm/s 的动作。

[实际控制代码的 CPU 路径检查](../../../runs/environment-stability/knot_untying/trefoil_robot_v9/spread_actual_code_preflight.json) 通过：93 个姿态无机器人互穿，最小关节限位余量约 0.190 rad；预估右手展开 235.3 mm，峰值约 29.4 mm/s。48 项相关测试与 Ruff 检查通过，新增检查覆盖参数有效性、速度上限、完整释放窗口和退出时目标连续性。这些检查不构成解结成功证据。

v9 物理录制已结束，本次解结与局部物理检查通过，输出到 `runs/environment-stability/knot_untying/trefoil_robot_v9/bounded_spread_recording/`，仍为四路 ALOHA 相机加近景的同一次连续执行，最终录像和报告已归档，见上方同步播放链接。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.physics_probe \
  --mode robot_untying --seconds 75 --friction-eps .001 \
  --robot-coupling external_articulation --pregrasp-start --x-offset -.11 \
  --untying-route remote_adaptive_spread --spread-span .65 --spread-duration 12 \
  --record --fps 20 --resolution 960 540 \
  --output runs/environment-stability/knot_untying/trefoil_robot_v9/bounded_spread_recording
```


最终记录：60,000 个原生子步全部收敛；末态无投影交叉，释放后的观察窗也保持无交叉。最小 J=0.761，最大总长度变化 1.060%，最大局部轴向应变 6.580%。末两秒 RMS / 最大速度为 0.287 / 0.638 mm/s，最大漂移 0.982 mm。所有视频已独立复制、完整解码并核对同步时间与 SHA-256。
