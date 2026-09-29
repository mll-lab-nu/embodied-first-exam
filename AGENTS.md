# TopoGym 项目规则

## 旧实现归档（用户 2026-09-29 授权）

- 已将旧 Harbor、旧 research 候选与包内旧 Task 入口移入 `legacy/cleanup_20260929/`；具体原路径、新路径及哈希见该目录的 `manifest.json`、`files.jsonl`。下方历史段落提到的 `topogym/agents/deferred/` 等旧位置已失效，不恢复到活动包。
- 当前 Harbor 使用 `tasks/`、`images/`、`harbor_agents/`、`ci_checks/`，手册在 `docs/rcb/README.md`；本地 `simulator/rollout_simulation/` 继续保留。
- 旧名称回归测试只读取 `tests/fixtures/retired_variations.json`，不依赖 legacy 的位置或内容。
- 本轮后续检查须监控 CPU 和内存；达到 90% 时停止本轮启动的相关工作进程，不终止无关进程。完整物理或模型成功不得由静态检查、配置解析或 CPU 合同测试推断。

## 并行会话边界（用户 2026-09-24 新增）

- 另一个会话负责 `scene_preset_restoration_20260924_zh.md` 的 Task 建模、材质、默认场景预设；公共接口会话不改 `tasks/`、`assets/geometry/`、材质及该场景恢复文档，也不应用临时 Lock Picking 几何补丁。
- 计划存在共享文件：`simulator/config.py`、`simulator/env.py`、`world/genesis_world.py`、`tests/runtime_evidence.py`、`tests/integration/test_base_task_runtime.py`、`test_installed_simulator.py`、`pyproject.toml`。添加场景预设应保留当前已实现的管理方 reset / 操作方无 reset、episode 句柄失效、单条 tick 历史、四种控制和公共证据接口；不要用旧文件整份覆盖。
- 公共接口会话后续验收采用独立源码快照，并记录实际哈希；不得把快照通过称为另一会话正在变化的最新场景已通过。共享文件若出现冲突，先向用户列明具体文件/函数和影响，不自行覆盖另一会话改动。
- 本次边界核对时 Lock Picking 几何文件与接口会话开始时相同；其 URDF 绝对路径造成同 seed 资产字节不同是已有问题。待场景会话统一处理相对资源引用及外观处理调用链，接口会话保留严格 seed 检查，不隐藏此差异。

## 公共接口整改（用户 2026-09-24 最新要求，已授权实施与验收）

- 入口、Env、SimulatorConfig、历史及权限接口统一放 `topogym/simulator/`，不保留平行 Env 循环；顶层导出 env_list/make。
- **管理方**可 reset(seed=...) 更换场景；相同 seed、配置及资产应复现初始环境。不增加 last_seed 属性，也不锁死管理方的 seed。
- **操作方**只接收当前 episode 绑定的 interaction 句柄，普通与特权模式均无 reset、make、close 或 seed/config 设置接口。管理方 reset 后旧句柄失效。
- 特权只增加当前 episode 的 rewind_to 和白名单 get。不能跨 seed 或跨 episode（同 seed 的旧 episode 也不允许）；仅维护当前 episode 一条有效路径，每 tick 保存，回溯点之后旧未来作废且 ID 不复用。
- Genesis 唯一物理途径，Nyx + compact_lab 唯一标准视觉；默认双臂 4 路、单臂 3 路，848×480、30 fps。明确无 RGB 模式可用于纯物理。
- G2 生命周期/时间/错误边界必须验收；真实测试先具备报告、源码与配置身份及实际录像。运行产物放 runs/test_results/，GPU 无法访问时给用户可执行 CLI。
- 实施计划见 `docs/develop/dev-logs/simulator_public_api_and_validation_plan_20260924_zh.md`；实际改动、测试结果和剩余缺口见 `docs/develop/dev-logs/simulator_public_api_implementation_20260924_zh.md`。13 项基础环境运行与各 Task solved 判据完整分别报告。
- agent/网络 API 实验继续延期；本地 simulator API 在当前范围内。下文旧分支保留/reset(state_id) 合同已由本节覆盖。

## 当前核心重构范围（用户 2026-09-23 最新要求）

- 本阶段先建设 simulator 本身：标准模块、Env、observation 和 Genesis 单一执行途径。agent/API/rollout 工作暂存 `topogym/agents/deferred/`，不搭新接口、不做 API 使用实验。
- 当前优先目标是全部 13 个基础 Task 经统一 Env 真实运行与完整回溯；planner、完整成功判据、可解证明或 demo 不作为基础生命周期的前置要求，未完成判据仍不得报告成功。最新实施范围与计划见 `docs/develop/dev-logs/simulator_base_task_runtime_plan_zh.md`。
- `assets/textures.py` 和 `world/physics/fem.py` 已按用户要求恢复；迁移中尚未接入的实现不能仅因没有当前调用方就再次删除。
- `reset(state_id=...)` 必须支持回溯当前 episode 任意已保存状态；旧分支历史保留。实现和经过真实物理验证必须分别说明。
- 用户现已授权运行基础环境可运行性及相关合同/物理测试；运行前先审查并补齐详细报告、真实测试场景录像，产物放 `runs/test_results/`。GPU 若无法访问，提供完整 CLI 由用户运行。agent/API 实验仍不在本轮范围。
- 用户已授权删除 redundants 和直接使用 MuJoCo 的实现，也授权整改源码与清理旧入口；此前“仅移动文件”和旧 demo / agent 保护范围不再阻止本次整理。历史视频不作为恢复重复运行框架的理由。
- 本轮按后续计划 5.1 收敛目录并接入全部 13 项任务；用户允许任务未完成，但必须按任务/模块/脚本列出功能缺口。integrated 仅表示定义接入；FEM/IPC 的接线、真实运行与回溯结果以 `docs/develop/dev-logs/simulator_base_runtime_implementation_zh.md` 及逐任务测试报告为准，七项未完成判据不能声明 solved。
- 当前目录和默认值以 `docs/develop/dev-logs/simulator_simplification_20260923_zh.md` 为准，生命周期合同及任务缺口同时参照 `docs/develop/dev-logs/simulator_task_integration_20260923_zh.md` 和当前 registry；旧录制/agent 手册不能作为当前接口要求。更新完整脚本清单时可运行 `scripts/inventory_sources.py`，它仅读取文本、AST 与哈希，不执行测试或项目模块。

## 统一录制与默认起始姿态（用户最新要求）

- 后续新录制和重新录制统一使用 `topogym.recording` 公共模块，按[共享录制用法](docs/develop/modules/recording_module_usage_zh.md)接入 `prepare`、`session` / `replay`、`validate` 与 `archive`。任务只提供场景、状态适配及验收结果，不另写取帧循环、视频 writer、编码或正式归档实现；仅引用兼容 writer 不算完成迁移。
- 默认使用 `lab_default_v1` 选择机器人对应的实验室 profile，沿用共享 `compact_lab` 背景、外观及相机配置。在建场景前完成配置，不再在任务录制脚本中硬编码棋盘背景或另建实验室。当前只支持 `compact_lab`，其他背景选项已撤销。
- 运行时 RGB 与录像统一使用 Nyx + compact_lab，默认计算设备 CUDA；不得为基础测试静默切回 Rasterizer。`observe()`、`render()`、RecordingSession 共用 SensorFrame。CPU 物理可关闭 RGB；缺少 Nyx/CUDA/视觉资源时明确失败。历史 Rasterizer 验收不能作为 Nyx 验收证据。
- 新的完整机器人 demo 默认从所选机器人配置的 `robot_control.home.qpos` 开始录制，包含默认姿态、连续接近和后续任务动作。home 到任务起点由任务控制器规划和真实执行，并检查关节限位、碰撞及任务物体稳定性；录制模块不负责移动机器人。不能直接把第一帧设为抓取附近的 IK 姿态来代替这段动作。
- 历史状态重渲染保持原执行身份和真实起点。来源缺少 home 到任务起点的动作时，明确记录范围；要生成默认姿态开始的完整版，需要新的连续物理执行及相应验收，不拼接片头或改写旧轨迹。

## 变体视频目录（用户 2026-09-21 最新要求）

- Cast Keyhole 正式展示只收录最终 F1/F2/F3 各一个已验收代表：`varaition_f1_long_stroke`、`varaition_f2_eccentric_window`、`varaition_f3_turnback`。不额外收录旧 baseline、开发版本或多个 seed；版本和 seed 仅留在元数据中用于复现。此条覆盖下文基础实例也单独收录的通用示例。

- 有变体的任务统一采用 `demos/<task_id>/varaition_<variant_id>/<camera>/`，`varaition_` 沿用用户指定拼写。每个变体的每个视角保留一份独立 MP4；不能按任务全局只留一套而删除其他有效变体。
- 已有成功变体缺视频时，先找经过验证的副本；无副本时从其保存的完整物理状态重渲染。尚未成功的家族、静态或运动学预览须明确标注，不以这些视频替代完整物理流程。
- 同一结构的历史版本不自动视为不同变体；已明确替换退役的家族不恢复到默认池。迁移须核对哈希、完整解码和同组同步，再更新当前引用；开发中的输入、状态与队列不改动。
- 本节覆盖下文旧的 `demos/<task_id>/<camera>/` 目录示例；基础实例也使用具名变体目录。

## 当前清理与保留范围（用户 2026-09-21 最新要求）

- 正在开发的任务（有进程运行，或尚未产出最终完整 demo）暂不清理代码、文档和 runs 产物；不要删除其队列、状态、恢复点或输入依赖。
- 本轮保护 Orbits、Slotted Post Ring、Rope Threading、Knot 新结型、Buzz Wire 新家族、Blanket 复杂初态，以及 agent bridge / rollout 试验。开始后续清理时重新核对实际开发状态。
- 视频统一采用 `demos/<task_id>/varaition_<id>/<camera>/`，`varaition_` 沿用用户指定拼写。基础实例也有具名变体目录，每个相机叶子目录只保留一份独立 MP4；不同变体分别保留，不得以“全任务只留最新版”为由覆盖其他变体。已有完整流程的变体优先保留最新正式完整版；较新的静态预览、局部尝试不能覆盖最后一份完整 demo。无完整机器人流程的变体明确标注现有视频性质。
- 完整替代副本通过哈希、完整解码和同组同步检查后，才删除旧版；不同物理运行不得拼成一组完整 demo。
- 当前任务说明收敛为每任务一页，全局开发状态在 `docs/progress/current_zh.md`；正在开发的专属记录暂保留。不要重新创建旧研究草稿、每日流水账和重复汇报导出。
- 历史材料是否保留取决于当前用途；本节覆盖此前要求无条件保留旧视频、HTML、runs/demos 备份和历史变体的约定。

## Demo 与开发进展交付

- 按用户 2026-09-21 的变体目录要求，Claw 三个基础变体分别保存在 `demos/interlocked_claws/varaition_a0_original/<camera>/`、`varaition_b0_helical_crown/<camera>/`、`varaition_c0_orthogonal_gate/<camera>/`。`varaition_` 沿用用户指定拼写，每个变体各保留五路完整视频，每个相机叶子目录一份 MP4；不能将三种变体合并成“任务只留一份最新视频”而删掉其他基型。缺失视频优先从已验证完整物理状态补录，标明重渲染来源。
- 汇报开发进展时直接提供相关 `.mp4` 可点击链接，说明内容、版本和验证状态；多视角分别给出链接。不再创建、更新或部署进展展示 HTML。
- 正式视频位于仓库根目录 `demos/<task_id>/varaition_<id>/`，其下沿用已有相机名称。任务视频目录内只放独立 MP4，不放 HTML、README、JSON、图片、日志、配置、脚本或链接文件。
- `demos/environment_bootstrap/` 是运行入口代码，不属于上述视频叶子目录。
- 配套配置、报告、状态/轨迹、场景资产、清单和哈希放在 `runs/demo_metadata/<task_id>/<date>_<run_id>/`；开发中的局部尝试放对应 `runs/`。
- 正式收录要求同一次连续机器人执行覆盖该实例完整任务流程，至少三路同步视角。单臂默认 agentview / front_oblique / wrist；ALOHA 保留 cam_high / cam_low / cam_left_wrist / cam_right_wrist。
- 使用真实副本，不用指向工作目录的软链接或硬链接代替归档。播放与核心证据不得依赖将被清理的原始 run。
- `archive_manifest.json` 记录原始目录、实例、录制范围、相机、时长、视频/证据路径及 SHA-256；更新当前 README / catalog 的有效引用。
- 预抓取、辅助抓持、外力驱动、运动学预演、实测状态重渲染和失败尝试均须如实标明。外力完整流程不算机器人完成；重渲染不增加物理执行成功次数；被动夹爪关节重建须声明。
- `runs/` 被 Git 忽略不代表可以删除。清理前核对代码、配置、资产、测试夹具及活跃运行的读入路径，保护最后一份已验收视频与核心证据。

## 任务约束

- Claw 的任务目标是将两件完全分离后短暂停稳，允许保留抓持；新 demo 不再增加落桌、释放或搬运阶段。旧版任务包和历史评测结果不追溯更改。新结构要求两件尺寸及结构复杂度相当，有效互锁要用几何、错误动作阻挡和物理执行检验。
- Fiber 家族按稀疏/标准/密集线数分组，族内随机线数和环内半径；不要求三类有本质不同的 IK 策略。仍需逐实例验证可达、夹爪禁碰、稳定性、完整穿环、seed 复现及重载。
- 几何/IK 通过、短程接口通过、完整任务成功与物理/数据资格分别记录；新变体不可继承旧实例的成功标签。
- 当前源码不导入 legacy。可复用实现归入任务或共享模块；一次性脚本放仓库外临时目录。
