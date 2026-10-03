# 3D Buzz Wire：场景变体与验证记录

## 2026-10-02：very_easy / easier 简化变体

两档已按预览确认的形状接入任务定义、独立包内布局及原有完整判据。下方预览是建模阶段的初态证据；机器人执行与任务包验证单独记录，不由预览推断成功。

| 入口 | 轨道形状 |
| --- | --- |
| `buzz_wire_3d_very_easy`（别名 `very_easy`） | 竖直上行 → 40 mm 半径圆弧 → 一条水平直道 → 圆弧 → 竖直下行。 |
| `buzz_wire_3d_easier`（别名 `easier`） | 相同上行、下行及圆弧；起点侧保留 35 mm 横向弯曲，终点侧改为 35 mm 向下凹弯，中间平滑转换弯曲平面。 |

very_easy 当前为 `straight_span_deck_rest_v1`，easier 为 `sideways_then_down_deck_rest_v2`。按预览反馈，将首版两个横弯中的终点侧横弯转为向下；转换区匹配位置、切线和曲率，避免直接折转 90° 产生尖角。正式布局与已确认预览的几何逐项一致，版本名移除了 `candidate`；这不表示已经完成难度校准。

通过公共入口选择场景：

```python
import topogym

with topogym.make("buzz_wire_3d", variation_id="very_easy", seed=0) as env:
    env.reset()  # variation_id="easier" 选择横弯接下凹弯。
```

两档直接参考**当前 easy 运行时布局**：底座 520.1 × 368.9 × 17.5 mm、底座抬高 125 mm、底座中心平面坐标 `[-0.08, -0.27] m`、起终点间距 350 mm、中段高度约为底座顶面上方 157.5 mm。铜轨直径 2.94 mm、工具环中心线半径 15.4 mm、环管直径 2.52 mm、木手柄长度 30.52 mm 均保持一致。起点工具的位置、朝向及底座支承方式与 easy 相同；机器人仍使用 Panda + Robotiq 的默认 home。

新几何由 [buzz_wire_3d_simplified.py](../../../topogym/assets/geometry/buzz_wire_3d_simplified.py) 生成，沿用公共 URDF / GLB 生成器和材质。已分别冻结为 `variations/buzz_wire_3d/straight_span_deck_rest_v1/layout.json` 与 `sideways_then_down_deck_rest_v2/layout.json`，并登记素材 SHA-256；运行时读取各自的包内布局，不随 easy 后续修改而漂移。旧布局的朝向和中心偏移参考轨迹不套用于新线路。任务入口和终态判据继承现有实现，仍要求完整走线、不碰铜轨并在终点释放静置。新入口暂属 `experimental`，`base` 与 `seeded` 的 easy / medium / hard 含义不变。

几何与判据检查入口：`.venv-gs121-nyx/bin/python ci_checks/test-buzz-wire-simplifications.py`，**5/5 通过**。检查覆盖尺寸和初始姿态继承、直道/横弯/下凹弯、弯曲半径、独立素材及接触角色、原三档 seed 映射，以及终点必须具备走线历史、释放、支撑、低速和完整接触覆盖的判据合同。[几何差异记录](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/geometry_delta.json)核对了 very_easy 不变、easier 横弯非过渡区及出口圆弧/立柱不变；新轨道最小采样曲率半径约 29.4 mm。

两档均已通过统一 `Env.reset(seed=0)` 在 **Genesis CUDA + Nyx + compact_lab** 中加载，从公共 `SensorFrame` 保存三路默认相机及三个检查机位的原始 PNG。全部图片对应默认 home、物理步数 0 的同一初态；检查机位只调整相机，没有移动机器人或任务物体。初态 `task_success=false`、`terminated=false`、`touch_now=false`。这证明场景加载和取景可用，不证明动态稳定性或完整可解性。

- very_easy：[斜视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/very_easy/inspection_oblique.png) · [俯视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/very_easy/inspection_top.png) · [运行报告](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/very_easy/preview_report.json)
- easier v2：[斜视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/easier/inspection_oblique.png) · [正视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/easier/inspection_front.png) · [俯视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/easier/inspection_top.png) · [运行报告](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/easier/preview_report.json)
- easier 已确认的高机位：[70° 俯斜视图](../../../runs/test_results/buzz_wire_easier_high_view_20261002_01/easier/inspection_high_70deg.png)，只改变检查相机，未改变场景。
- easier 首版双横弯，仅供对照：[原斜视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/easier/inspection_oblique.png) · [原俯视图](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/easier/inspection_top.png)

[v2 产物目录](../../../runs/test_results/buzz_wire_simplified_preview_20261002_02/)与[首版产物目录](../../../runs/test_results/buzz_wire_simplified_preview_20261002_01/)保留各自生成资产、源码快照、PNG 哈希、相机参数、CPU/内存记录和截图脚本。可在可用 CUDA 环境从仓库根目录重拍，例如：

```bash
PYTHONPATH=. PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python \
  runs/test_results/buzz_wire_simplified_preview_20261002_02/source_snapshot/buzz_wire_preview_20261002.py \
  --variant easier --output runs/test_results/buzz_wire_simplified_preview_repeat/easier
```

### 任务包与独立加载检查

已生成 `topogym-buzz-wire-3d-{very-easy,easier}-i00-{privileged,standard}` 四个任务包，登记在 `tasks/dataset.toml`，两种模式共享各档冻结实例。使用本地镜像 `topogym-local/buzz-wire-variants:20261002-01`（`sha256:c87ffe22502e09659b6ce5266030a01a0a03924c3f3ed00daea01fe3ee014a77`）；尚未发布到镜像仓库。包内保留原有成功规则，`oracle=none`，没有 Harbor 正分参考解资格。

- 四包结构/字段/镜像引用与 dataset 对应关系：13 项检查通过；公共 tooling 身份检查通过。
- wheel 构建后从隔离目录导入两档，资源目录与素材哈希验证通过：[结果](../../../runs/test_results/buzz_wire_simplified_development_20261002/wheel_check/result.json)。
- 两档各在新容器静置 1 s：初态匹配公共容差，工具漂移约 0.0507 mm；二进制状态摘要并不完全一致（`instance_exact=false`），不称为逐位复现。
- 两档 privileged 包的空动作轨迹分别由原始 verifier 在另一容器重放两次，均 `success=0`、`grader_error=0`、`deterministic=1`：[very_easy](../../../runs/test_results/buzz_wire_simplified_development_20261002/container_very_easy/verifier_logs/reward.json) · [easier](../../../runs/test_results/buzz_wire_simplified_development_20261002/container_easier/verifier_logs/reward.json)。这是加载、负例与评分链路验证，不是完整可解证明。

容器检查使用冻结包记录的 CPU 64 位物理、2.5 ms tick、10 倍控制降采样、4 子步，Nyx 图形资源正常加载。机器人参考策略的非默认时序实验另行记录，不能继承为这些包已通过完整正例。

### 新变体的机器人验证

开发入口为 [run_buzz_wire_simplified_policy.py](../../../scripts/oracle_runners/run_buzz_wire_simplified_policy.py)。使用公共 `Env` / `SegmentRunner`，从默认 home 执行普通关节目标；抓持采用任务既有的双侧接触触发 `contact_weld_v1`。规划查询不推进物理；重用前缀时重新执行已记录动作，不写入工具位姿或恢复途中状态。

2026-10-03 已将规划逻辑整理到 [planning/buzz_wire_3d/simplified_policy.py](../../../topogym/planning/buzz_wire_3d/simplified_policy.py)：按每段实际观测规划抓取、完整走线、低位释放和终点摆正。常规入口不依赖历史动作或 run 目录；独立审计入口为 [audit.py](../../../topogym/planning/buzz_wire_3d/audit.py)，具体用法见 [planning README](../../../topogym/planning/buzz_wire_3d/README.md)。

新版 very_easy 已从默认 home 连续成功：**262.8 s / 10,512 tick，终点误差 3.418 mm / 5.024°**。完整谱系、普通 action 覆盖、所有上报刚体子步、工具与机器人无触线均通过独立审计。[运行与审计](../../../runs/test_results/buzz_wire_simplified_oracle_20261002/very_easy_feedback_01/)保留实际冻结源码身份。

该次成功的完整刚体状态经公共 `record_rigid_history` 重渲染为三路 Nyx 视频，逐帧核对所有 link 位姿，最大误差为 0；重渲染没有增加物理成功次数。三路均为 848 × 480、30 fps、7,885 帧，完整解码和同步检查通过，并由公共 `archive_recording` 归档：

- very_easy：[全景](../../../demos/buzz_wire_3d/varaition_very_easy/agentview/varaition_very_easy_agentview.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_very_easy/front_oblique/varaition_very_easy_front_oblique.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_very_easy/wrist/varaition_very_easy_wrist.mp4) · [归档清单](../../../runs/demo_metadata/buzz_wire_3d/20261003_very_easy_feedback_01/archive_manifest.json)。

easier 的终点标定使用 `planning/calibration_tools` 的原生物理检查点、恢复、抓持状态、接触明细和夹爪几何工具。第一次终点抓取改为相对偏航 223.625°；实测抓持后先平移 `[3, -3, 0] mm` 使环居中，再提高 4 mm，转向终点保留 3 mm 高度。窄间隙离开路径单独采样检查，后续转向仍要求 1.5 mm 规划净空；场景、碰撞失败条件与成功阈值未修改。[标定分支](../../../runs/test_results/buzz_wire_simplified_oracle_20261002/calibration_easier_01/calibration_summary.json)已经达到原生成功（3.695 mm / 4.697°），该分支使用过检查点，不能当作从 home 零回溯的完整 oracle 资格；独立完整复验仍在运行。

**建模阶段 very_easy 还保留两次完整原生成功。** [attempt07 报告](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt07_cpu/run_report.json)记录 262.1 s、10,484 个物理 tick，连续完成起点抓取/换抓、全部线路、终点低位放回、重新抓取摆正、释放撤臂及静置。终点位置误差 3.644 mm、姿态误差 4.739°，释放后满足完整终态判据持续 1 s。[独立审计](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt07_cpu/independent_audit.json)核对从出生状态开始的完整无回溯链、普通动作覆盖、全部上报刚体子步接触证据；工具—铜轨、机器人—铜轨接触事件均为 0。

[attempt08 带 RGB 的真实复跑](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/run_report.json)再次成功，[独立审计](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/independent_audit.json)同样通过。公共录制的三路完整视频均为 848 × 480、30 fps、7,864 帧，完整解码与同步检查通过；视频覆盖默认 home 至完整成功，无回溯或跨执行拼接：

- [very_easy 全景完整视频](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/agentview.mp4)
- [very_easy 斜前完整视频](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/front_oblique.mp4)
- [very_easy 腕部完整视频](../../../runs/test_results/buzz_wire_simplified_development_20261002/very_easy_attempt08_rgb/segments/segment_1/videos/wrist.mp4)

上述成功限定于 **seed 0、CPU 64 位、25 ms tick / 1 倍控制降采样 / 40 子步**。这与冻结任务包默认动作时序不同，尚不能视为 Harbor 包正分参考解或难度排序资格。初期直接高位松爪的尝试会转动触线，记录仍保留；正式策略必须受控低位下放，不能以静态 IK 通过代替物理结果。

easier 的 [attempt06 报告](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/run_report.json)已记录从 home 完成整条线路、低位下放及释放；`traversal_complete=true`，独立审计确认 9,036 tick 的接触覆盖完整，工具和机器人均无触线。但终点再次抓取后，辅助抓持在 225.9 s 因 `relative_pose_error` 解除，策略中止，**该次不是完整 Task 成功**。录像按同一执行的连续段保存：[起点抓取与主轨道](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/segments/segment_1/videos/agentview.mp4) · [终点受控下放](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/segments/segment_2/videos/agentview.mp4) · [释放及静置](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/segments/segment_3/videos/agentview.mp4) · [再次抓取的失败段](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt06_rgb/segments/segment_4/videos/agentview.mp4)。后续闭爪控制实验独立记录，不覆盖此失败结果。

本轮部分早期失败实验的分段观察日志已无损压缩为 `steps.jsonl.gz`；解压字节数及 SHA-256 逐项一致，见 [压缩映射](../../../runs/test_results/buzz_wire_simplified_development_20261002/lossless_compression_manifest.json)。动作账本、完整私有 tick 证据、成功执行和正在执行的日志未压缩。

[easier attempt07](../../../runs/test_results/buzz_wire_simplified_development_20261002/easier_attempt07_cpu/run_report.json)从 home 重新执行到首次释放，再用缓慢闭爪寻找双侧接触；到达闭合上限仍为 `no_bilateral_candidate`，本次同样未成功。**当前交付状态：两档场景、资源、完整判据及双模式任务包均已接入；very_easy 有完整机器人成功，easier 的终点重新抓取/摆正仍待完成。** 原有终态要求未放宽，easier 不登记完整正例，不用于证明两档的难度排序。

## 原 easy / medium / hard 验证记录

2026-09-29 相机：Panda 默认使用任务专属斜上方角点主机位，让水平与两个竖直方向的线路展开；`front_oblique` 从另一侧补充观察交叉段。
[相机配置](../../../topogym/config/profiles/camera_configs/buzz_wire_3d_observation.yaml) ·
[三档投影对比、检查范围与 Nyx 补拍命令](../../../runs/test_results/task_camera_study_20260929/README.md)。
当前通过三档默认几何取景检查，尚未取得新机位 Nyx 初始化帧。

> **2026-09-29 当前注册 E/M/H 的求解核对（默认参数、seed 0）：** 三档各 14 个关键位置＋朝向通过 IK、关节限位和采样间隙检查，共 **42/42**，并复核到 **4/2/5 次**历史双指接触触发的辅助夹持与释放。关键点与已有走线夹持证据为 **3/3**；加上终态动作的分段证据为 **2/3（easy、hard）**：Hard 新补局部转正、释放及静置，最终误差 **0.057 mm / 8.146°**，稳定 **5.95 s**。Medium 终态转正仍未通过。局部实验以历史工具静置姿态和机器人默认 home 为初态，没有与旧走线连续衔接；从默认初态完成原生 Task 并独立审计通过仍只有 **easy 1/3**，不能宣称三档完整可解性均已证明。本轮使用 `segment` 检查点，无视频，进程均已退出；内存或 CPU 达到 90% 时暂停本轮进程。详见[最新分段证据与资源记录](../../../runs/test_results/buzz_three_tier_component_proof_20260929_01/README.md)、[关键姿态及旧证据哈希](../../../runs/test_results/buzz_fast_feasibility_20260929_01/README.md)和[策略说明](../../../topogym/planning/buzz_wire_3d/README.md)。下文历史 F1/F2/F3 demo 保留各自版本的资格范围。

> **2026-09-28 当前版本：** 三档端点改为 8 × 8 × 12 mm 细连接块，可穿过约 28.3 mm 内径的工具环；移除工具托架，环与原尺寸握柄直接落在底板上，底板顶面距桌面 142.5 mm。原机械臂模型保持不变。三档 1 秒初始化录像已完成，40 项相关单测通过；Medium 另完成落板稳定性、采样接近路径和双指接触空间检查。实际验证范围与录像见[实施记录](../../../runs/test_results/buzz_deck_rest_20260928/README.md)。下述 9 月 27 日整体抬高版及历史完整 demo 保留各自版本含义。

> **2026-09-27 更新：** 三档冻结布局的底座、线路与起终点支撑均整体再抬高 40 mm，medium 初始化录像已补录。 建模、录像与验证边界见[本轮开发报告](initial_scene_feedback_20260927_zh.md#9-本轮开发与验证2026-09-27)；全部当前入口见[39 项初始化索引](../../../runs/test_results/base_acceptance_final/README.md)。下文历史证据仍保留原版本含义。


F1/F2/F3 已更新为 **home_lab_v4**：使用公共 `topogym.recording` 和 `lab_default_v1` 实验室背景，从机器人配置的默认 home 姿态开始，连续完成接近、拾取、全部关卡、支撑放回、松爪撤臂与静置。三个新执行均通过 4/2 ms 独立物理复验，完整 IK 和九路正式视频已冻结。

2026-09-22 起 F1 由双拱改为 **三拱**（设计规格 `vertical_wave_v1.yaml` 的 `F1_triple_arch`：3 座高拱夹 2 个深谷，比双拱多 1 拱 1 谷，即多 2 道竖直弯；半径由 55 mm 改为 50 mm，拱顶 250 mm、谷底 80 mm、前后跨度 100 mm 不变）。三拱版沿用 70% 紧凑玩具版、同一工具和抓持，重新走完搜索、拾放、home 接近、4/2 ms 复验与公共录制，包为 `F1_triple_compact_toy_s70_home_lab_v1`。旧双拱包 `F1_compact_toy_s70_home_lab_v4` 与其归档保留为历史证据，不再是默认展示代表。

## 当前完整 demo

| 固定家族 | 每路时长 / 帧数 | 三路同步 MP4 | 种子与证据 |
| --- | --- | --- | --- |
| F1：三座高拱与两个深谷 | 96.57 s / 2897 | [全景](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/agentview/F1_triple_home_lab_v1_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/front_oblique/F1_triple_home_lab_v1_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f1_vertical_wave/wrist/F1_triple_home_lab_v1_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F1_triple_home_lab_v1_full/archive_manifest.json) |
| F2：三连回折、错层八字、竖直 W | 136.63 s / 4099 | [全景](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/agentview/F2_home_lab_v4_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/front_oblique/F2_home_lab_v4_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f2_over_under_eight/wrist/F2_home_lab_v4_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F2_compact_toy_s70_home_lab_v4/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F2_home_lab_v4_full/archive_manifest.json) |
| F3：水平梳齿、竖直 W、侧向 Ω、倾斜螺旋 | 131.47 s / 3944 | [全景](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/agentview/F3_home_lab_v4_full.mp4) · [斜前](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/front_oblique/F3_home_lab_v4_full.mp4) · [腕部](../../../demos/buzz_wire_3d/varaition_f3_plane_switch/wrist/F3_home_lab_v4_full.mp4) | [完整 IK](../../../assets/tasks/buzz_wire_3d/F3_compact_toy_s70_home_lab_v4/robot_seed.json) · [归档](../../../runs/demo_metadata/buzz_wire_3d/2026-09-22_F3_home_lab_v4_full/archive_manifest.json) |

全部为 30 fps；公共外部相机为 1280 × 720，腕部为 960 × 720。每族三路来自同一次新的连续物理执行，第一条实测状态的七个主臂关节与 `robot_control.home.qpos` 一致，夹爪按 home 开度张开，时间为 0。记录完整机器人关节（含被动夹爪关节）和工具位姿，再由公共模块零积分重渲染；没有拼接 home 片头，不增加物理执行次数。

环初始已穿在线路上，由底座实体木托支撑；机械臂张爪且未抓持。视频包含实际拾取和放回，不包含首次穿环。正式目录每族每视角一份 MP4，共九份；替换记录和旧版副本位于归档元数据。

## 场景与支撑

保留 70% 紧凑玩具版的全部关卡及顺序，Panda + Robotiq 2F-85 的尺寸、安装位及物理关节限位不变。底板与导线整体同步抬升；底板采用削角分层浅木材、铜色导线、银色套环、木柄及木托，无电池或电路板。F1/F2 底板为 520.1 × 368.9 × 17.5 mm，F3 为 520.1 × 385 × 17.5 mm。

F1/F3 使用倾斜柄托；F2 终点用固定在底座上的 V 形环托和柄颈托，保留机械臂可达倾角。与支撑拾放 v3 相比，F2 整体沿世界 X 移动 -30 mm、Y 移动 +25 mm，避开默认姿态下夹爪与线路的干涉；完整主路径与首尾 IK 已重算并重新验收。F3 的玩具摆位不变。F1 三拱版的中央拱顶恰好落在默认 home 张爪正下方（双拱版此处是深谷），因此相对双拱摆位沿世界 X 移动 -20 mm、Y 移动 +70 mm，让第二个深谷落在张爪下方，home 张爪与线路净空 20 mm；向 -Y 移动会使终点立柱一侧的 IK 超出姿态容差，已排除。

| 家族 | 底座垫高 | 世界 X / Y | 主路径 IK 位姿数 | 两步长通行最大位置差 | 两次运行最大工具接触穿透 |
| --- | --- | --- | ---: | ---: | ---: |
| F1 | 25 mm | -0.050 / +0.070 m | 4571 | 0.0795 mm | 0.3251 mm |
| F2 | 40 mm | -0.010 / +0.025 m | 13549 | 0.2964 mm | 0.3794 mm |
| F3 | 25 mm | -0.010 / +0.000 m | 11333 | 0.1015 mm | 0.3492 mm |

接触穿透包含抓持和木托接触，是每个外层物理步的实测值，不能视为积分子步的连续上界。F2 松爪后从实测关节姿态重新求解并审计撤臂路径，避免抓持反馈改变冗余分支后跳回名义关节轨迹；实际撤臂 IK 随包保存。

## 动作与验收

1. 机械臂从配置 home 张爪开始，工具在木托上无抓持静置 2 秒。
2. 沿经过关节限位及碰撞审计的连续路径接近；张爪对准木柄，缓慢闭合、提离木托。
3. 通过全部关卡，检查触线、双侧夹爪接触与机器人碰撞。
4. 放到终点木托，确认连续支撑接触后松爪。
5. 张爪退开并至少静置 4 秒，检查末态速度、位置及支撑接触。

三族均通过完整工具连续导线净空、密集 IK/碰撞审计及 Genesis CPU 64 位、4 ms / 2 ms、各 16 子步的独立执行。通行阶段无记录触线，双侧夹爪持续接触。抓持依靠真实接触摩擦，无焊接、环杆外力或运行中位姿覆盖。公共 replay 检查 CPU 执行模型与 CUDA/Nyx 录制模型的物理签名一致；归档检查哈希、完整解码、帧数及三视角同步。

这仍是仿真状态反馈参考控制，不代表视觉 agent 自主求解。导线为固定刚体，未模拟铜线弹性和蜂鸣电路。新包保留源配置 producer instance_id；新旧运行通过 execution UUID、run ID 和计划哈希区分，不改写原执行身份。

## 从三个完整 IK 派生

当前机器入口：[fixed_home_lab_v4.yaml](../../../configs/task_variants/buzz_wire_3d/fixed_home_lab_v4.yaml)（F1 条目已指向三拱包，`previous_representative` 记录旧双拱包）。每族保存原执行配置、含 home_approach 的完整 `planning/`、`robot_seed.json`、资格报告及哈希。`fixed_supported_toy_v3.yaml` 只描述历史拾取附近起步、棋盘背景的版本。

后续先选 F1/F2/F3，再微调转弯半径、跨度、高度或底座 pose，保留关卡数与顺序。使用对应 IK 和抓持变换作为初值，不能缩放关节角。每次变化都重新检查默认 home 与张爪净空，重规划接近、拾取、通行、下放与撤臂，并独立执行完整流程和半步长复验；不得继承母实例资格。通用随机采样器及保证成功的参数范围尚未完成。

原始设计候选范围：[F1](../../../configs/task_variants/buzz_wire_3d/vertical_wave_v1.yaml)、[F2](../../../configs/task_variants/buzz_wire_3d/over_under_eight_v1.yaml)、[F3](../../../configs/task_variants/buzz_wire_3d/plane_switch_v1.yaml)。

## 复现与公共录制

在仓库根目录执行，替换 `F1` 可选择 F2/F3，输出目录使用新名称。环境：`.venv-gs121-nyx`；公共 Nyx 录制需要 CUDA。

```bash
# 新的完整物理执行：默认 home → 拾取 → 全关卡 → 放回 → 静置。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. .venv-gs121-nyx/bin/python \
  -m topogym.tasks.buzz_wire_3d.robot_runtime \
  --plan assets/tasks/buzz_wire_3d/F1_triple_compact_toy_s70_home_lab_v1/planning \
  --output runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal

# 同一计划加 --dt 0.002，写入 F1_home_review_refined；随后对照两次执行。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.robot_verify \
  --nominal runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal \
  --refined runs/environment-solvability/buzz_wire_3d/F1_home_review_refined \
  --output runs/environment-solvability/buzz_wire_3d/F1_home_review_suite.json

# 任务适配器只冻结资格、实测状态与资产，不自行取帧或编码。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.tasks.buzz_wire_3d.recording_adapter snapshot \
  --run runs/environment-solvability/buzz_wire_3d/F1_home_review_nominal \
  --suite runs/environment-solvability/buzz_wire_3d/F1_home_review_suite.json \
  --output runs/recordings/buzz_wire_3d/F1_home_review_source \
  --family F1 --run-id F1_home_review_full

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. PYOPENGL_PLATFORM=egl \
  .venv-gs121-nyx/bin/python -m topogym.recording replay \
  --source runs/recordings/buzz_wire_3d/F1_home_review_source/source_manifest.json \
  --output runs/recordings/buzz_wire_3d/F1_home_review_full --fps 30

# 全片校验后按变体替换正式三视角；旧版保留在归档回滚证据中。
PYTHONPATH=. .venv-gs121-nyx/bin/python -m topogym.recording archive \
  runs/recordings/buzz_wire_3d/F1_home_review_full
```

从种子重建使用 `robot_plan --seed-plan .../robot_seed.json`，新计划仍须重新做物理验收。共享录制说明见[模块用法](../modules/recording_module_usage_zh.md)。旧 `robot_render` 已删除；`robot_archive` 仅保留对历史 v3 目录的校验，新演示使用上述公共入口。

现有[基础实例 agent adapter](../../../legacy/cleanup_20260929/docs/develop/modules/buzz_wire_agent_adapter_zh.md)仍对应较早布局和短程协议验证，三个新家族尚未完成自主 agent 完整通行验收。
