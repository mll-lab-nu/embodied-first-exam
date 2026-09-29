# 共享录制模块用法与迁移状态

`topogym.recording` 已提供可调用的配置、在线录制、状态重渲染、验证和归档入口。新任务在建场景前调用 `prepare()`，接入一次 binding，之后无需编写取帧循环或视频 writer。

本页描述实际实现；原始设计及阶段验收见[工程计划](../../../legacy/cleanup_20260929/docs/develop/modules/recording_module_plan_zh.md)。已有任务的全面迁移仍在进行，不能把兼容 writer 的接入计为完整录制迁移。

后续新录制与重录统一使用本模块和 `lab_default_v1` 实验室预设，规则见根目录 [AGENTS.md](../../../AGENTS.md)。任务侧保留场景、控制和状态适配；同步取帧、编码、验证及正式归档由公共入口完成。

新的完整机器人 demo 从对应机器人配置的 `robot_control.home.qpos` 开始。任务在 reset 阶段初始化默认姿态，开启 session 后，由控制器连续执行 home → 接近 → 拾取 → 任务后续动作；接近段同样需要碰撞、关节限位及物体稳定性检查。录制模块只观察和记录，不自动生成或执行 home 运动。下文 `execute_task(task)` 应包含这段接近过程，不能在进入 session 前直接跳到抓取附近的 IK 姿态。

历史来源缺少 home 接近段时，`replay` 保留其真实起点并标明范围。要交付从默认姿态开始的完整 demo，需重新执行和验收，不能通过插入默认姿态图片或拼接另一条轨迹补齐。

## 1. 预设与环境

| 配置 | 用途 |
| --- | --- |
| `configs/recording_profiles/lab_default_v1.yaml` | 根据 `robot_control.robot.name` 选择下列具体 profile |
| `lab_franka_v1.yaml` | `agentview / front_oblique / wrist` 三路 |
| `lab_aloha_v1.yaml` | `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路 |
| `configs/presentation_configs/nyx_lab.yaml` | 既有实验室、外观和 Genesis Nyx 配置 |
| `configs/env_configs/world_tabletop*.yaml` | 既有桌面、安装位置、坐标和求解器配置 |
| `configs/camera_configs/franka_demo_v1.yaml`、`aloha_observation.yaml` | 相机参数；ALOHA 光学参数由 YAML 与 Python rig 共用 |

组合配置已存在。`prepare()` 返回独立的只读 OmegaConf，不修改传入配置，不覆盖现有物理世界、时间步、求解器和机器人安装。已有场景必须与准备后的配置及实际背景匹配；不要在 build 后补换碰撞桌面。

使用项目 Python 环境，并确保 `ffmpeg`、`ffprobe` 可执行。纯配置、时间线、编码和归档可在 CPU 运行；实际 Genesis Nyx、MuJoCo EGL 渲染需要对应后端。Genesis 默认沿用 Nyx；MuJoCo 使用原生渲染器，共用房间几何并记录材质/灯光差异。

```bash
.venv-gs121-nyx/bin/python -m topogym.recording preflight --config cast_coil_aloha
.venv-gs121-nyx/bin/python -m topogym.recording preflight --config config --preset lab_franka_v1
```

`preflight` 只验证配置、相机和资产引用，实际实体、无碰撞背景与桌面在绑定时检查。未知机器人、歧义相机、缺资产会报错，不静默切换背景。ALOHA 可以使用 canonical `cam_*` 或原来的四个 alias，但不能同时提供两套有歧义的定义。

## 2. 新任务在线录制

```python
import uuid
from topogym import recording
from topogym.recording.adapters.genesis import GenesisBinding

plan = recording.prepare(cfg, preset="lab_default_v1", fps=30)
task = build_scene(plan.scene_config, asset_dir)
binding = GenesisBinding.from_task(
    task, plan.scene_config,
    entities={"robot": "qpos", **{name: "pose" for name in task.bodies}},
)
identity = recording.RunIdentity(
    task_id="my_task", variant_id="base", run_id="trial_001",
    execution_id=uuid.uuid4().hex,
)
with recording.session(plan, binding, identity=identity) as rec:
    result = execute_task(task)  # 原有控制器正常调用 scene.step()
    rec.finish(task_result=result)

artifact = rec.result
```

如果已有 `TabletopBaseScene`，也可用 `base.recording_binding(plan.scene_config, entities=...)`。`entities` 必须覆盖所有影响画面的动态实体，机器人选全部 `qpos`，独立刚体选 `pose`；不能用刚体 pose 声称支持绳、布、FEM 离线恢复。省略 mapping 可在线录制 RGB，但不会自动获得完整状态重渲染能力。

阶段事件可调用 `rec.event("grasp", assistance="contact_gated_weld")`。会话订阅每次完成的物理步，所有相机共享状态，渲染不能推进物理；无需在控制循环里追加 writer 调用。默认输出 `runs/recordings/<task>/<run_id>/`，也可显式传 `output`，已有目录拒绝覆盖。

`finish()` 必须显式调用，之后不能继续推进物理。任务失败可以正常结束录制并保存 `status="failed"` 的任务结果；异常、缺少 `finish()`、取帧或编码失败则将录制标为 `incomplete`，保留部分产物并恢复原步进函数。

录制状态与任务状态分开。供正式收录的任务 evaluator 结果需要以下字段及真实证据：

```python
task_result = {
    "status": "success", "complete": True,
    "execution_kind": "robot_physics", "continuous_execution": True,
    "physics_qualified": True,
    "assistance": ["pregrasp", "contact_gated_welds"],
    "reconstruction": [],
    "evidence_files": [{"path": "evidence/task_result.json", "sha256": digest}],
}
```

其中状态和资格必须来自任务 evaluator；模块只核对声明、完整性及证据哈希，不替代物理资格判定。保存证据时可使用 `topogym.recording.io.write_json/sha256`。

外观增量在 `prepare(..., camera_overrides=..., extra_cameras=["detail"], presentation_overrides=...)` 中声明。任务相机已有参数保留，显式录制覆盖优先；新增相机不会代替 profile 的必需视角。不要改变已冻结的 policy observation 相机。非整数采样比按物理时间选择帧；首尾状态导致编码时长与物理区间可能相差一个视频帧，报告分别记录两者。

## 3. 保存状态重渲染

在线刚体录制可以生成显式来源：

```python
from topogym.recording.sources import source_from_recording

source = source_from_recording(
    artifact.directory,
    factory="topogym.recording.adapters.genesis:from_source",
    scene_builder="topogym.tasks.my_task.scene:build_scene",
    evidence=["source_inputs/template.json"],
    config_references={"task.template_path": "source_inputs/template.json"},
)
rendered = recording.replay(source, output="runs/recordings/my_task/rerender_001")
```

builder 接收 `cfg`、`asset_dir`，只能构造场景，不执行策略或物理步。任务 adapter 负责将模板、模型和必要依赖复制到来源目录，并在 `evidence/config_references` 中声明；通用模块不猜测任意 builder 的外部输入。回放需要相同项目代码和引擎环境，代码/包版本与未提交源码哈希写入审计。

可用 `sources.snapshot_config_inputs(directory, cfg, fields)` 复制显式声明的配置文件引用、MJCF 依赖、纹理/HDR，并返回 `evidence` 与 `config_references`。Cast Coil 入口已经使用它打包 ALOHA 模型和共享外观资产。其他格式的复杂依赖需要任务提供 resolver，不能仅复制顶层 XML。

`source_manifest.json` schema 1 支持 JSONL 和 NPZ。它包含身份、配置、带 SHA-256 的输入文件、状态字段和能力声明、factory，以及原始物理模型签名。JSONL 的行包含 `time_s / physics_step / state`；NPZ manifest 显式声明时间字段和状态数组。路径必须在来源目录内，禁止未展开的外部依赖和软链接逃逸。

MuJoCo 使用 `topogym.recording.adapters.mujoco:from_source`，提供已打包 MJCF、资产及模型所需的 `qpos/qvel/act/mocap/eq_active` 等字段。恢复用 `mj_forward`，不调用 `mj_step`；含 flex/plugin 或缺字段的来源明确拒绝。Genesis 当前支持已声明刚体的完整关节与姿态恢复，不支持通用软体离线恢复，也不承诺恢复动力学继续运行。

默认 binding 面向固定模型/材质与固定或已声明挂载关系的相机。若任务在运行中改变材质、拓扑、动态模型参数或自定义镜头轨迹，必须扩展状态 adapter 和恢复验证，不能直接沿用默认 binding 的完整状态声明。

```bash
python -m topogym.recording replay --source <source_manifest.json> --output <new_directory>
python -m topogym.recording replay --source <source_manifest.json> --output <same_directory> --resume
python -m topogym.recording validate <recording_directory>
```

均匀来源默认保留源 FPS；显式 `--fps` 使用最近的已有状态，并限制时间偏差，不插值状态。输出保留源 execution/episode ID，不增加任务成功次数。恢复误差、模型签名和零积分检查写入 `replay_report.json`。

在线 session 逐物理步保存状态，源采样率可能明显高于视频帧率。例如 Cast Coil 400 Hz 状态可以用 `--fps 20` 重渲染，保持原速同时避免为每个物理步渲染一张图。

离线缓存位于输出旁的 `.<name>.replay/`，逐帧保存已完成图像及 checkpoint。`--resume` 比对来源、配置、代码和图像哈希，重验边界状态。完成的录制拒绝覆盖；失败的旧产物保留为 `.failed_<id>`，不拼接任意两个 MP4。长来源的状态索引和 checkpoint 元数据随帧数增长；完整 RGB 放磁盘，在线新 encoder 不积累整段视频。

Genesis CUDA 回放在建场景时，对较大的碰撞支撑查询表分批进行精确上传，降低临时显存峰值；不更改碰撞网格、表分辨率、数值精度或求解器配置。引擎接口变化时明确拒绝运行，建场景结束后恢复原上传函数。实际上传方式写入 `scene_report.json` 的 `support_table_upload`；模型签名及零积分检查仍然执行。此优化不保证任意场景都能在剩余显存内完成。

## 4. 产物与正式收录

录制目录包含 `videos/*.mp4`、`recording_manifest.json`、`resolved_config.yaml`、配置/源码来源、`scene_report.json`、`states.jsonl`、`frame_map.jsonl`、`events.jsonl`、`validation.json` 及抽样图；回放另含 `source/` 和 `replay_report.json`。抽样图用于人工核对背景与镜头，自动黑帧检查不能替代视觉审阅。

```bash
python -m topogym.recording archive <recording_directory>
python -m topogym.recording recover <metadata_directory>
```

也可 `recording.archive(artifact)`。只有完整、成功、有资格证据的一次连续机器人运行可以进入 `formal_demo_v1`；必须满足三路/ALOHA 四路、桌面与背景兼容、完整解码、同组时间线及哈希要求。回放还要求完整源状态和已验证的物理模型签名。外力、静态预览、失败结果不能顶替正式任务。Cast Keyhole 只接受规定的 F1/F2/F3 代表。

任务专属要求声明在 `configs/recording_policies/formal_demo_v1.yaml`。Cast Coil 保留原有半时间步收敛、几何、接触、释放与最终稳定窗口检查；单次运行通过摘要检查不会自动获得正式资格。录制完成后调用下列适配器附加资格报告与独立证据，再调用公共 archive：

```bash
python -m topogym.tasks.cast_coil.recording_adapter --run <new_run> --reference <verified_half_dt_run>
python -m topogym.recording archive <new_run>/recording
```

需要正式收录的回放应先完成任务资格，再冻结来源并重渲染。回放继承冻结时的资格，后续验证不会追溯修改已生成的产物。

发布路径为 `demos/<task>/varaition_<variant>/<camera>/<run_id>.mp4`；证据复制到 `runs/demo_metadata/<task>/<date>_<run_id>/evidence/`。变体整组加锁、暂存、切换后更新 catalog/README；旧组保留在事务 metadata 中用于回滚。不同运行不会逐相机拼组，也不会自动清理源状态或工作目录。`archive_manifest.json` 的 `committed` 标志与事务日志定义发布状态。

用户明确要求的 Orbits 无机械臂整套解法使用独立的 `external_physics_v1` 收录策略：
`python -m topogym.recording archive <recording_directory> --policy external_physics_v1`。
Orbits 入口接纳 `orbits/rope_only`，要求视频阶段与实测穿环检查、最终整绳和木柄分离、
无手工物理状态改写的连续执行，以及四路完整同步录像。长运行允许在动作边界保存并恢复
同一 episode 的完整求解器状态；需保留检查点哈希、逐位恢复比较和轨迹边界一致性证据，
不能把不同初态或修改过状态的片段拼成完整版。它保持 `execution_kind=external_physics`、
`physics_qualified=false`；不能通过默认 `formal_demo_v1` 的机器人资格门槛。
原始平面桌面的物理模型保持不变，背景使用共享实验室；桌面差异在 scene report 中保留。

Slotted Post Ring 的 `clearance36` 体积 FEM 外力流程也使用 `external_physics_v1`，要求三路完整同步视角、连续执行且无初始状态之后的位姿改写、逐步数值与释放落稳检查，以及全部四面体与木环至少 10 mm 的保守分离证明。该入口只接纳任务适配器核验的完整结果，局部检查点续跑与未完成动作不能发布。材料未标定与非机器人执行的范围保持不变。

`export_video_set()` 仅用于旧开发目录兼容导出，拒绝向正式 `demos/` 直接写入。旧 `utils.recording` 和 `recording.encoding.get_writer()` 保留旧时序/参数，不产生通用正式归档资格。

## 5. 已接入入口与迁移状态

2026-09-22 起，13 个任务的录制代码全部收敛到本模块：任务目录内不再有取帧循环、视频 writer、ffmpeg 子进程、私有相机拼装或棋盘背景。`configs/recording_profiles/migration_inventory.json` 的 `exceptions` 为空，`shared_entries` 列出各任务的接入文件。绕转相机预览视频、轨迹/家族对比等分析视频、任务级拼图与 HTML 播放页已按用户决定删除；各任务 `demo.py`/`preview.py` 只输出静态 PNG 与 `inspection_report.json`。

| 任务 | 接入方式 | 状态与限制 |
| --- | --- | --- |
| `cast_coil.robot_demo --record` | 在线 session；`recording_adapter.qualify` 附加半时间步资格并生成来源 | 旧 `render_physical_trace`/`variant_review` 已删；重渲染用 `python -m topogym.recording replay` |
| `blanket_flatten.recording_adapter` | `BlanketBinding` 恢复布粒子 + 机器人 qpos，`snapshot` 冻结 `physical_trace.npz` 为 NPZ 来源；`preview.py` 落布 settle 走在线 session | 软体状态由任务 NPZ 提供，binding 声明不支持通用软体离线恢复；无机器人外力运行没有 `wrist` 相机，不能在 Franka profile 下回放 |
| `blanket_flatten.bimanual` / `bimanual_full` | 在线 session（ALOHA 四路） | 不变 |
| `buzz_wire_3d.recording_adapter` | `snapshot` 冻结 home 起始执行，公共 replay/archive | 旧 `render`/`robot_render`/`compact_render` 已删；`qualification.py` 保留签名与帧选择函数 |
| `cast_keyhole.recording_adapter` | `KeyholeBinding` 恢复机器人与零件位姿并返回垫片 FK 误差；`snapshot` 用 `physical_recording` 的采样规则冻结 NPZ 来源；`aloha_demo`/`variant_runtime render`/`family_pipeline` 均调它 | `four_views` 拼图已删；三个 archive 脚本读公共 `recording_manifest.json` |
| `fiber_bundling.recording_adapter` | `FiberBinding` 恢复线束关节、根位姿与机器人并返回中线误差；`render_ready`/`variant_demo` 调它 | 合成 `demo.mp4`、画中画、字幕已删；阶段表写入 `task_result.phases` |
| `hedgehog_in_cage.recording_adapter` / `extract.py` | `HedgehogBinding` 恢复 qpos 与球位姿并返回 FK 复核误差；`family_runtime`/`inverse_runtime render` 调它；`extract.py` 在线 session | `audit.py` 的视频帧数检查拆为 `video_consistent`，不再并入物理 `passed`；旧 run 的 `runner_sha256` 门限因源码变更会失败 |
| `horseshoe_ring.recording_adapter` | `HorseshoeBinding` 附夹爪垫 FK 误差；`snapshot(kind=physical|gravity)`；视锥覆盖检查保留 | 旧 `render_physical`/`render_gravity`/`render_family_comparison` 已删；重力保持结果写 `task_result.gravity_check` |
| `interlocked_claws.recording_adapter` / `family_render` | MuJoCo 家族 replay；相机移到 `configs/camera_configs/claws_family_v1.yaml` | 旧 Genesis 五路 `recording.py` 已删；历史 z=0 桌面仍 `world_compatible=false` |
| `knot_untying.recording_adapter` | 在线 session（`physics_probe --record`）；`detail` 相机与 `cam_low` 俯仰在 `prepare_recording` 内作为覆盖生成 | 旧 `recording.py` 已删；`archive_demo` 用公共 `validate` |
| `rope_threading.recording_adapter` | 在线 session（`physics_probe --record`），阶段标签作事件 | 旧继承式 `ThreadingRecorder`、IK 预览与弹起分析视频已删；`--record-renderer rasterizer` 在 OSMesa 下不再有 FBO 补丁 |
| `lock_picking.runner` / `recording_adapter` | `runner` 在线 session（机器人 + 锁体/盘片 qpos）；adapter 的 `LockBinding` 含 Robotiq 被动连杆重建并声明 `reconstruction` | `lock_picking_spaced_preview.yaml` 仍用 1.8 m 桌面（机构底座超出共享桌面），回放报告 `world_compatible=false` |
| `orbits.recording_adapter` / `robot_recording` / `motion_render` | MuJoCo 绳与机器人 replay；`motion_render` 改为 `OrbitsCordBinding`（绳网格仅图形载体，`render_state_complete=False`） | 旧 `rope_render`/`probe_render` 已删 |
| `slotted_post_ring.recording_adapter` | `FEMBinding` 增加 `eq_active/eq_data/eq_obj2id` 字段；`archive`/`curate_demos` 读公共清单 | 旧 `render_physics` 已删；旧布局的 `runs/*/recording/` 需重新回放才能归档 |
| `agent_rollout.media` | 编码、拼图、解码与抽帧下沉到公共 media | 不是正式 demo 归档入口 |

```bash
python -m topogym.recording audit
python -m unittest tests.check_recording_migration -q
```

审计会拒绝任何未登记的新 writer/ffmpeg 调用；例外清单现为空，新增入口必须走 session/replay。它是静态依赖检查，不是任务成功证明。各任务 `archive*.py` 的解码校验统一调用 `recording.encoding.probe`，但除 Cast Coil、Buzz Wire、Orbits、Slotted 外，正式发布仍由任务 archive 脚本完成，尚未全部切到公共 `archive` 事务。

## 6. 验证入口

CPU 合约检查覆盖配置、时间线、会话失败、来源篡改、续录、归档复制与回滚；真实引擎检查另外执行：

```bash
python -m tests.check_recording_engines --engine genesis --output <new_check_dir>
python -m tests.check_recording_engines --engine genesis_aloha --output <new_check_dir>
MUJOCO_GL=egl python -m tests.check_recording_engines --engine mujoco --output <new_check_dir>
```

这些短程检查的任务状态明确为诊断，不会成为正式成功任务。实际 Claw 完整状态 pilot 已输出 331 帧、五路、约 16.5 秒物理区间，恢复字段误差为零，完整解码和同步通过；它保留原执行身份与桌面不兼容声明。全部正式入口完成迁移、软体离线恢复和所有历史来源的独立复现，仍不属于已完成能力。

Cast Coil 新执行 `runs/recording_checks/cast_coil_live_v1` 已完成装配、放置、释放、撤臂和稳定观察：13,241 步、33.1025 秒、五路各 663 帧，任务结果成功。复制模型、纹理和源状态后生成的 `cast_coil_rerender_v1` 同样通过五路解码与同步，零积分，最大恢复误差约 `1.1e-16`。这些都是 160×120 的模块验收视频，任务的半时间步资格另由上文 adapter 检查。

同 CUDA 后端的 `cast_coil_half_dt_v1` 复核已通过：两次执行最终位置最大差异约 1.59 微米、姿态差异约 `3.71e-6` 弧度。在线 artifact 已附加真实资格，并在 `cast_coil_archive_rehearsal_v1` 隔离目录完成公共归档：五路真实视频副本、72 个证据文件及来源依赖哈希全部通过。`cast_coil_rerender_v1` 冻结于资格复核之前，保留当时的待复核声明。

汇总见 [`runs/recording_checks/module_validation_summary.json`](../../../runs/recording_checks/module_validation_summary.json)。65 项核心/相机/配置/rollout 回归与 11 项 rollout 工具回归通过；测试包括复制时来源变更、目录切换中途进程退出、旧组恢复及引用回滚。
