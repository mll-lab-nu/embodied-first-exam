# TopoGym 项目规则

## 开发进展与 demo 交付（2026-09-19，适用于所有 session）

- 每次汇报新的开发进展，直接提供相关 `.mp4` 视频文件的可点击链接，并简要说明内容、版本和验证状态。多视角视频分别给出链接；不再创建、更新或部署用于进展展示的 HTML 页面，也不以 HTML 播放页作为交付入口。
- 完整流程 demo 在仓库根目录 `demos/<task_id>/` 对应子目录持续迭代；已有按视角组织的任务沿用 `demos/<task_id>/<camera>/`。这些视频目录中的文件只能是独立 `.mp4`，不得放入 HTML、README、JSON、图片、日志、配置、脚本或链接文件。版本用文件名区分。
- 配置、报告、状态/轨迹、场景资产、清单和哈希等配套材料放在 `runs/demo_metadata/<task_id>/<date>_<run_id>/`，开发中的原始产物可留在对应 `runs/` 目录；不要让生成器把非 MP4 副产物写入 `demos/` 视频目录。
- 仍须核对视频可播放、同步视角的帧数/时长、证据对应关系和直链目标；只更新必要的 Markdown / JSON 记录，不再要求生成或更新 `index.html`。未完成的局部尝试、运动学预演、重渲染等需如实标注。
- 本节覆盖下文及其他历史文档中要求 HTML 展示、更新播放页，或默认将新完整 demo 归档到 `runs/demos/` 的旧约定。已有历史 HTML、备份和 `demos/environment_bootstrap/` 运行入口保留；“只能放 MP4”适用于对应任务的视频目录。
- 所有读取本文件的 session 均须执行本节；开始后续开发和交付前重新读取本文件。若有可用的 session / 子 agent 通知通道，将本节同步给正在处理本项目的 session；未确认送达时，不声称已完成全量广播。

## 完整机器人 demo 的保留

- 按用户 2026-09-21 的最新要求，`demos/slotted_post_ring/` 只保留最新版正式完整流程录像，每个视角一份独立 MP4。历史版本、静态预览、重力探针和局部尝试移至 `runs/environment_bootstrap/slotted_post_ring/`，配套证据仍归档于 `runs/demo_metadata/slotted_post_ring/`。新版本验收及副本校验完成后再迁出旧版；外力驱动完整流程必须注明其辅助操作范围，不能计作完整机器人执行。

- 按用户 2026-09-19 确认，光纤收束的变体家族采用稀疏／标准／密集的线数分组，家族内以线数和环内半径随机化；不要求三类有本质不同的 IK 策略，也不把这一点列为生成器的待完成项。仍需保证 seed 可复现、实例可重载，并逐实例检查 IK 可达、夹爪禁碰、物理稳定性和完整穿环成功。

- Buzz Wire 3D 当前紧凑单臂完整动作按用户要求收录在仓库根目录 `demos/buzz_wire_3d/{agentview,front_oblique,wrist}/`，视角目录只放独立 MP4。配套播放页与物理证据保留在 `runs/demo_metadata/buzz_wire_3d/`；明确说明预穿环 / 预抓取起点、实际摩擦抓持、末端松手后重力滑落，以及实测状态重渲染。旧无机械臂台架的 `overview / front_oblique / topdown` 视频及 `runs/demos/buzz_wire_3d/` 备份继续保留，用文件名前缀区分版本。归档核对哈希、完整解码、同步帧数 / 时长和索引引用。

- 按用户要求，被子展平完整三视角视频收录在仓库根目录 `demos/blanket_flatten/{agentview,front_oblique,wrist}/`，每个视角目录仅放独立 MP4。播放页与物理证据保留在 `runs/demo_metadata/blanket_flatten/`；原 `runs/demos/blanket_flatten/` 副本作为备份保留。后续归档沿用此结构，并核对视频哈希、播放完整性及索引引用。

- 按用户 2026-09-18 的最新要求，光纤收束当前正式交付仅保留基础变体（8 芯、环内半径 13.5 mm、细铜杆支架）的无 UI 三视角视频，位于仓库根目录 `demos/fiber_bundling/{agentview,front_oblique,wrist}/`，每个视角目录一份独立 MP4，不加文字、状态栏或画中画，不保留合成画面。旧视频已按用户要求删除，历史物理证据保留于 `runs/demo_metadata/fiber_bundling/`。替换时先验证新副本并更新引用、清单及哈希，再移除旧文件。

- 每个环境首次生成完整机器人 demo 后，必须保留至少一份独立、可播放的 MP4 副本；新完整 demo 默认位于仓库根目录 `demos/<task_id>/`，已有视角目录的任务沿用 `demos/<task_id>/<camera>/`。视频目录内只能有 `.mp4` 视频文件，禁止放置其他格式文件或软链接；用 `<date>_<run_id>_<camera>.mp4` 文件名区分日期、版本和视角。已有 `runs/demos/` 归档继续保留。统一使用复数 `demos`；已有运行入口代码位于 `demos/environment_bootstrap/`，不混入任务视频目录。
- 按用户 2026-09-18 的要求，刺球出笼 CLASSIC wood 基础版的三路正式视频位于仓库根目录 `demos/hedgehog_in_cage/{agentview,front_oblique,wrist}/`，每个视角目录保留独立 MP4。对应证据仍在 `runs/demo_metadata/hedgehog_in_cage/2026-09-16_classic_wood/`；其他已归档变体与历史 preview 保留现有路径。整理时更新引用和清单，确认新路径、哈希与播放完整性后再移除旧路径。
- 按用户 2026-09-18 的要求，开锁新外观标准变体的三路完整过程视频位于仓库根目录 `demos/lock_picking/{agentview,front_oblique,wrist}/`，每个视角目录一份独立 MP4，播放页与证据放在 `runs/demo_metadata/lock_picking/`。从成功物理状态记录重渲染时，必须说明夹爪被动关节是否经过重建，不能据此宣称完成了新的动力学执行。
- 按用户 2026-09-18 的要求，Cast Coil 基础装配版的五路完整视频位于仓库根目录 `demos/cast_coil/{cam_high,cam_low,cam_left_wrist,cam_right_wrist,front_oblique}/`，每个视角目录只保留独立 MP4。对应播放页与证据仍在 `runs/demo_metadata/cast_coil/2026-09-17_aloha_full/`；历史拆解及其他变体保留现有路径。整理时更新引用和清单，确认新路径、哈希与播放完整性后再移除旧路径。
- 按用户 2026-09-18 的最新要求，Horseshoe Ring 重力修正后的基础版完整视频收录在仓库根目录 `demos/horseshoe_ring/{cam_high,cam_low,cam_left_wrist,cam_right_wrist,detail}/`，各视角目录一份独立完整 MP4。播放页、IK 和物理证据位于 `runs/demo_metadata/horseshoe_ring/`。整理时核对哈希、完整解码、时长和帧数，并更新索引与清单；明确区分已完成的基础执行和未完成的额外复验。
- Horseshoe Ring 历史变体仍保留在 `runs/demos/horseshoe_ring/`，按变体分一层子目录：最初的 `tutorial_solvable_v3` 演示归入 `original/`，其余演示归入对应的 `<variant_id>/`；跨变体同步对照放在 `comparisons/`。这些子目录只放独立 MP4 文件，继续用带日期、版本和视角的文件名；播放页及证据仍放 `runs/demo_metadata/`。整理时同步更新所有引用和清单，确认新路径、哈希与播放完整性后再移除旧路径。
- 正式收录要求同一次连续机器人执行覆盖该实例的完整任务流程，并保留至少三路同步视角。单臂默认 `agentview / front_oblique / wrist`；ALOHA 保留 `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路。只有初态环绕、静态三视图、局部尝试或不同运行拼出的视角不算完整 demo。
- 按用户 2026-09-18 的要求，Cast Keyhole 基础物理实例 `2026-09-17_current_instance_physical` 的视频按视角放入仓库根目录 `demos/cast_keyhole/<camera>/`，包括 `cam_high / cam_low / cam_left_wrist / cam_right_wrist / detail / oblique / four_views`。这些子目录只含独立 MP4，保留原文件名；元数据仍位于原 `runs/demo_metadata/` 归档。其余已有变体及 IK 预演保留原路径；迁移时先核对新副本及引用，再移除旧位置文件。
- 配置、报告、图片、状态/轨迹、场景资产及清单统一放在旁边的 `runs/demo_metadata/<task_id>/<date>_<run_id>/`，禁止混入视频目录；历史 HTML 播放页保留原位，不再作为新进展的展示入口或维护要求。交付前更新必要的 `README.md` 和 `catalog.json`；各实例的 `archive_manifest.json` 记录原始目录、环境/实例、录制范围、相机、时长、视频与配套文件路径及 SHA-256。核对视频可解码、帧数/时长一致、报告与视频对应、交付的 MP4 直链有效。
- 按用户 2026-09-18 的要求，解绳结的完整视频按视角保存在仓库根目录 `demos/knot_untying/{cam_high,cam_low,cam_left_wrist,cam_right_wrist,detail}/`，各视角目录只放独立 MP4，保留原文件名。配套播放页与证据仍在 `runs/demo_metadata/knot_untying/`；后续归档沿用此结构。迁移时先核对新副本的哈希、完整解码及引用，更新清单后再移除旧路径。
- 预抓取起点、辅助抓持、运动学回放、失败状态等必须如实说明。全过程运动学预演的视频可保留在对应任务目录，以 `<date>_<run_id>_kinematic_<camera>.mp4` 命名，并在配套目录中标注预演性质；不能计为已完成的物理机器人执行，也不能替代正式副本。
- 使用实际文件副本，不以指向工作目录的软链接或硬链接代替归档；视频与配套材料一起构成保留副本，播放与核心证据不得依赖原始 run 目录。原始产物可以继续留在原位，新版本使用新的文件名前缀和配套目录，禁止覆盖最后一份已验证副本。
- 清理、迁移或重跑覆盖 `runs/` 时，必须保护上述副本。每个已完成环境始终至少保留一份经过检查的完整 demo；删除旧版前先确认替代副本齐全。`runs/` 被 Git 忽略不代表归档可以删除。
