# 光纤收束

更新：2026-10-02（两档简化变体与完整执行）；terminal 说明为 2026-09-29，旧三档 demo 状态为 2026-09-21。全项目进度见[当前进度](../../progress/current_zh.md)，正式视频直链见下文。

## 任务与实现

固定电源终端和被动细线保持连续，机器人只操作粗护套，使分叉端先进入闭环并完成整束穿环；需要逐步检查细线禁碰、抓持及受载稳定性。

当前源码：[任务与判据](../../../topogym/tasks/fiber_bundling/common.py) · [几何生成](../../../topogym/assets/geometry/fiber_bundling.py) · [穿孔历史](../../../topogym/utils/geometry/passage.py) · [子步接触](../../../topogym/world/physics/rigid_contacts.py)。参数与成功定义见[任务卡](../../../configs/task_cards/fiber_bundling.yaml)，统一运行入口见 [Simulator API](../modules/simulator_api_zh.md)。旧 bootstrap、robot_sequence 和 recording_adapter 不再是当前入口。

## very_easy / easier

2026-10-02 按确认的初态布置新增具名入口，并完成 seed 0 的连续机器人穿环与独立审计：

| 入口 | 分叉布置 |
| --- | --- |
| `fiber_bundling_very_easy`（别名 `very_easy`） | 2 根细线，绕护套轴相隔 180°，截面上相对。 |
| `fiber_bundling_easier`（别名 `easier`） | 3 根细线，绕护套轴相隔 120°，截面上构成等边三角形。 |

两档均继承现有 easy–hard 场景：240 mm 长、24 mm 直径的工作护套，80 mm 长、2.4 mm 直径的细线，8 mm 根部展开半径，13.5 mm 名义铜环内半径、4 mm 环管半径；分叉根部到环平面 110 mm，轴线高于桌面 240 mm，工作护套原点 xy 为 `[-0.1, -0.25]` m。固定终端、松弛引线、U 型托架、环支架和 Panda + Robotiq 的 home 姿态均复用当前实现。

[简化几何](../../../topogym/assets/geometry/fiber_bundling_simplified.py) 复用旧生成器的第一根 seeded 曲线，并绕轴复制，使根部、沿途各截面与尖端都保持对称。只规定 reset 时的形状；运行时各细线仍为原有被动关节，没有保持对称的弹簧、驱动或位姿写入。运行所需资产由包内 Python 生成器在 reset 时生成，不依赖历史 `runs/` 或根目录资产副本。

任务入口：[very_easy](../../../topogym/tasks/fiber_bundling/fiber_bundling_very_easy.py)、[easier](../../../topogym/tasks/fiber_bundling/fiber_bundling_easier.py)。例如 `topogym.make("fiber_bundling", variation_id="very_easy", seed=0)`；原有 `base` 仍对应 medium，`seeded` 仍只采样 easy／medium／hard。新两档沿用 `terminal_v4_fiber_ring_plane` 的完整穿环和细线禁碰要求。

预览证据放在 [runs/test_results/fiber_bundling_simplified_preview_20261002](../../../runs/test_results/fiber_bundling_simplified_preview_20261002/)，包括生成资产、源码哈希、相机位姿、截图与逐档报告。截图使用 Genesis/CUDA + Nyx + compact_lab，在标准 home 初态、零 physics tick 下保存；标准相机图保留，额外近景与轴向图仅调整展示相机。[几何检查](../../../ci_checks/test-fiber-bundling-simplifications.py) 覆盖对称、线长、初始间隙、被动关节、夹爪禁碰角色及旧入口；[资产回归报告](../../../runs/test_results/fiber_bundling_simplified_preview_20261002/regression_report.json) 对 seed=0 的原 easy／medium／hard 分别核对 236／372／644 个文件，生成字节及实例 ID 均与修改前一致。

### 完整执行与录像

参考策略从标准 home 接近并抓住 `trunk_04` 护套，依次利用环外侧收拢 2／3 根细线，再回正并完整送入环内。使用已有 `contact_weld_v1`，取得双指 native 接触后才建立辅助抓持；细线不属于辅助目标。执行没有物体位姿写入、预抓跳转或 rewind。两档送入阶段允许至多 0.5 mm 起点偏心，仍通过原有 1 mm 规划碰撞间隙检查，不修改终态判据。旧三档策略参数不变。

| seed 0 连续执行 | 原生终态 | 仿真时间 | 独立核对状态数 | 全程最大采样弯折 |
| --- | --- | --- | --- | --- |
| very_easy，25 ms / 40 子步 / 1 倍控制降采样 | 成功 | 106.350 s | 4,255 | 8.167° |
| easier，相同时序 | 成功 | 155.425 s | 6,218 | 8.244° |
| very_easy，默认 2.5 ms / 4 子步 / 10 倍控制降采样 | 成功 | 106.635 s | 42,655 | 8.172° |
| easier，默认时序，以已成功动作从 home 重新执行 | 成功 | 155.417 s | 62,168 | 8.247° |

以上为 CPU float64；默认时序还使用任务包的 `use_contact_island=False`。每例检查所有细线 tip-to-root 穿环、前护套清出、0.5 s 稳定窗口、完整子步禁碰覆盖、固定环／终端不动、home 起点、关节限位及连续健康抓持。[独立审计](../../../topogym/planning/fiber_bundling/audit.py)重新生成资产并核对身份，重算每 tick 的 Task。easier 首次默认时序复验约 127 s 被 SIGTERM 中断，保留原记录；第二次以已成功动作从 home 全程重跑并审计通过。详情见[交付报告](../../../runs/test_results/fiber_bundling_simplified_development_20261002/delivery_report.json)。

录像来自前两条已审计完整历史，由共享 `rigid_replay` 恢复全部记录关节（含被动夹爪关节），逐帧核对所有 link 位姿后以 Nyx + compact_lab / RecordingSession 重渲染。位置与旋转恢复误差均为 0；三视角 848×480、30 fps，已全量解码并核对同步。重渲染不增加物理成功次数。

- very_easy：[全景](../../../demos/fiber_bundling/varaition_very_easy/agentview/varaition_very_easy_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_very_easy/front_oblique/varaition_very_easy_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_very_easy/wrist/varaition_very_easy_wrist.mp4)；3,191 帧，106.367 s。[证据与清单](../../../runs/demo_metadata/fiber_bundling/2026-10-02_very_easy_symmetric_v1/archive_manifest.json)。
- easier：[全景](../../../demos/fiber_bundling/varaition_easier/agentview/varaition_easier_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_easier/front_oblique/varaition_easier_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_easier/wrist/varaition_easier_wrist.mp4)；4,664 帧，155.467 s。[证据与清单](../../../runs/demo_metadata/fiber_bundling/2026-10-02_easier_symmetric_v1/archive_manifest.json)。

### 判据与任务包

[几何和注册检查](../../../ci_checks/test-fiber-bundling-simplifications.py) 6 项、[终态正反例](../../../ci_checks/test-fiber-bundling-terminal.py) 3 项通过，覆盖缺一根、只过尖端、环外绕行、逆序、接触证据缺失、过度弯折、稳定窗口与恢复。两档另在真实 Genesis 中以约 0.05 mm 浅接触验证：夹爪碰细线立即失败，碰护套可继续，rewind 能恢复。这些探针有明确的管理方位姿干预，只验证机制。原 easy／medium／hard 的 seed 0 资产和实例 ID 回归不变。

两档各生成 privileged / standard 包，使用本地镜像 `topogym-local/fiber-bundling-variants:20261002-01`、tooling v11、terminal v4，登记在 [dataset.toml](../../../tasks/dataset.toml)：

- very_easy：[privileged](../../../tasks/topogym-fiber-bundling-very-easy-i00-privileged/README.md) · [standard](../../../tasks/topogym-fiber-bundling-very-easy-i00-standard/README.md)。
- easier：[privileged](../../../tasks/topogym-fiber-bundling-easier-i00-privileged/README.md) · [standard](../../../tasks/topogym-fiber-bundling-easier-i00-standard/README.md)。

辅助抓持写入新包 frozen instance；旧三档默认配置不变。两档 privileged 的三条 hold 动作、严格实例重建、独立 verifier 两遍回放和视频收尾通过，正常得到 0 分。两档 standard 也已通过公开 HTTP 观察／三条动作、服务结束、独立进程回放及 verifier；live/replay 状态哈希一致，无基础设施或评分错误，录像完整。该服务检查未覆盖 Harbor 容器隔离资格。所有包保留 `oracle="none"`：本地参考求解、包流程可运行与 Harbor 完整参考解评分分别记录；镜像未推送到远程，未运行模型难度评估。详见[交付报告](../../../runs/test_results/fiber_bundling_simplified_development_20261002/delivery_report.json)。

复现命令见 [runner 用法](../../../scripts/oracle_runners/README.md#fiber-两档简化变体)。完整日志、冻结源码、资产、配置、接触探针及各次尝试见 [development 目录](../../../runs/test_results/fiber_bundling_simplified_development_20261002/)。已结束运行的大日志按需无损压缩，`lossless_compression.json` 保留原文件哈希；审计和重渲染支持 `.jsonl.gz`。

结果只证明所测 seed 0 在所列配置下可完成，不外推到所有 seed，不宣称 `very_easy < easier < easy` 已由模型评测确认。保留 `thresholds_calibrated=False`，没有新增连续时间 CCD 或长期物理资格。

## 当前自动终态

`terminal_v4_fiber_ring_plane` 对 very_easy/easier/base/easy/medium/hard 启用 `goal_complete=True`。所有细芯必须按尖端到根部的材料顺序穿过环心平面，穿过时离环轴小于圆管中心线半径（孔最窄半径 + 管半径 = 17.48 mm），最后全部离环心平面超过管半径 + 细芯半径（5.2 mm）、留在出口侧；前护套端面按同一规则穿过环心平面，并越过环心 16 mm 清出；实际弯折角不超过 60°，连续满足默认 0.5 s。允许保持粗护套抓持。前护套采用 [2026-09-25 设计 §5.3](terminal_judgement_engineering_plan_20260925_zh.md#53-fiber-bundling) 的端面通过条件；旧任务卡的额外 30 mm 深度不用于本版本，历史验收记录不追溯修改。

**为什么从 v3 改成 v4（2026-09-29）。** v3 在环心前后各 5.2 mm 的入口/出口平面上检查离轴距离，并且都用孔最窄处的尺寸：细芯 ≤ 12.18 mm（13.479 − 1.2 − 0.1），前护套 ≤ 1.379 mm。可是入口平面在环前表面再往前 1.2 mm，那里圆管还没收窄。细芯在那里离轴 13–15 mm，继续前进会被圆管前侧的弧面导进孔里，却被 v3 判成没穿过。

历史 4/8/16 芯完整成功轨迹按 v3 只算 1/4、2/8、7/16 根穿过，差的全是尖端：过入口平面时离轴 12.3–14.9 mm，过环心平面时 ≤ 12.2 mm，已经在孔内。

在环心平面上，细芯中心要么在孔里（≤ 12.28 mm），要么在环外（≥ 22.7 mm），两者之间就嵌进圆管了。取圆管中心线半径作阈值，正好在这个不可能区间的中间，从环外绕过去的情况仍然判不通过。按 v4 重放，历史三条轨迹全部判成功。证据和重放脚本见 [v4 验证](../../../runs/test_results/fiber_terminal_v4_20260929/)。

每个刚体 solver 子步收集 native narrowphase 接触，几何角色按 MJCF 所属 link、局部位姿、形状和尺寸在 build 前匹配。Genesis 会复用 primitive mesh 的 metadata 名称，不能把该名称或导入顺序作为身份。机器人描述中的夹爪根 link 覆盖全部后代，包括手指、外壳、连杆；机械臂保持独立分类。任何夹爪—细芯接触（包括零力接触）立即失败，复用 Task/Env 的终止锁存，公共失败码为 `task_failed`，管理方原因是 `fiber_gripper_contact`。接触摘要缺失或任一子步、细芯/机器人几何覆盖不完整时，当前分支不确认成功；回溯到缺口前可恢复完整覆盖。

`goal_complete` 表示实现启用，不表示机器人已经完成任务或 60° 等阈值已完成物理标定；`thresholds_calibrated=False` 保留。穿孔轨迹仍采用 physics tick 采样与线性插值，子步接触也不声称连续时间 CCD。成功时 Task 输出 `task_success=True`、`terminated=True`、`reward=1`，Harbor 还会独立检查运行证据和预算。

2026-09-28 验证：80 项相关测试通过；全量 unit/contracts/architecture 为 555 通过、3 项既有失败，三项均在恢复本轮改动前的独立基线中复现。easy/medium/hard（seed=0，Panda + Robotiq）的 9 项 CUDA/Nyx 机制测试全部通过：每档出生与 80 ticks、夹爪轻碰细芯即失败、轻碰护套继续运行，以及各自的回溯。接触探针包含管理方位姿干预；成功路径测试使用合成状态，本轮没有新增完整机器人穿环成功或阈值标定。源码快照、修改坐标、哈希、逐项报告及三视角录像见[本轮验证报告](../../../runs/test_results/fiber_terminal_delivery_20260928/README.md)。Harbor 使用旧镜像时须重建才能载入此实现。

## 当前状态与边界

正式视频已覆盖稀疏 4 芯、标准 8 芯、密集 16 芯三个代表，环内半径均为 13.5 mm、细铜杆支架，每个变体三路无 UI 完整视频。目录为 `demos/fiber_bundling/varaition_<实例名>/<视角>/`；每个相机叶子目录一份 MP4。8 芯原视频直接迁移，4/16 芯从各自成功物理轨迹补录；均以辅助夹持保持末态。三例的两种时间步均完成穿环，严格全程线形对照仅 4 芯通过；这些代表不为任意随机参数提供资格。

## 变体与下一步

稀疏/标准/密集是线数家族，不要求三种 IK 机制。fixed 使用 4/8/16 芯和 R=13.5 mm；parameterized 分别采样 4–6/7–10/11–16 芯及 R=12.8–15.0 mm。300 个 seed 初态几何通过；IK、禁碰、受载稳定性、完整穿环和时间步对照必须逐实例补齐。

## 当前证据

- [稀疏 4 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_sparse_04_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/agentview/2026-09-21_sparse_04_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/front_oblique/2026-09-21_sparse_04_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_sparse_04_r13p5mm/wrist/2026-09-21_sparse_04_r13p5mm_clean_v1_wrist.mp4)，各 116.7 秒。
- [标准 8 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-18_standard_08_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/agentview/2026-09-18_standard_08_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/front_oblique/2026-09-18_standard_08_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_standard_08_r13p5mm/wrist/2026-09-18_standard_08_r13p5mm_clean_v1_wrist.mp4)，各 177 秒。
- [密集 16 芯](../../../runs/demo_metadata/fiber_bundling/2026-09-21_dense_16_r13p5mm_clean_v1)：[全景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/agentview/2026-09-21_dense_16_r13p5mm_clean_v1_agentview.mp4) · [近景](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/front_oblique/2026-09-21_dense_16_r13p5mm_clean_v1_front_oblique.mp4) · [腕部](../../../demos/fiber_bundling/varaition_dense_16_r13p5mm/wrist/2026-09-21_dense_16_r13p5mm_clean_v1_wrist.mp4)，各 237.15 秒。
- [2026-09-19_variant_generation_audit](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit)

运行报告记录有限实例的实际结果；几何、IK、短程协议、完整任务和物理资格分开判定。正在执行的任务以运行目录中的最终报告为准。

## 历史生成入口（已退役）

以下命令仅记录旧 demo 的来源，当前工作区已移除该入口，不能作为现有三档运行方式。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.generation \
  --seed 42 --family standard --mode parameterized \
  --output runs/environment-solvability/fiber_bundling/generated_seed42
```
