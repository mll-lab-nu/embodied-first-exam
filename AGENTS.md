# TopoGym 项目规则

## 完整机器人 demo 的保留

- 每个环境首次生成完整机器人 demo 后，必须在 `runs/demos/<task_id>/` 保留至少一份独立、可播放的 MP4 副本。除下述 `horseshoe_ring` 规则外，任务目录内只能有 `.mp4` 视频文件，禁止放置其他格式文件、软链接或嵌套子目录；用 `<date>_<run_id>_<camera>.mp4` 文件名区分日期、版本和视角。`runs/demos/` 根下只放任务目录。统一使用复数 `demos`；仓库根目录的 `demos/` 仍放运行入口代码。
- 按用户要求，`runs/demos/horseshoe_ring/` 按变体分一层子目录：最初的 `tutorial_solvable_v3` 演示归入 `original/`，其余演示归入对应的 `<variant_id>/`；跨变体同步对照放在 `comparisons/`。这些子目录只放独立 MP4 文件，继续用带日期、版本和视角的文件名；播放页及证据仍放 `runs/demo_metadata/`。整理时同步更新所有引用和清单，确认新路径、哈希与播放完整性后再移除旧路径。
- 正式收录要求同一次连续机器人执行覆盖该实例的完整任务流程，并保留至少三路同步视角。单臂默认 `agentview / front_oblique / wrist`；ALOHA 保留 `cam_high / cam_low / cam_left_wrist / cam_right_wrist` 四路。只有初态环绕、静态三视图、局部尝试或不同运行拼出的视角不算完整 demo。
- HTML 播放页、配置、报告、图片、状态/轨迹、场景资产及清单统一放在旁边的 `runs/demo_metadata/<task_id>/<date>_<run_id>/`，禁止混入视频目录。交付前更新 `runs/demo_metadata/index.html`、`README.md` 和 `catalog.json`；各实例的 `archive_manifest.json` 记录原始目录、环境/实例、录制范围、相机、时长、视频与配套文件路径及 SHA-256。核对视频可解码、帧数/时长一致、报告与视频对应、页面内的本地链接有效。
- 预抓取起点、辅助抓持、运动学回放、失败状态等必须如实说明。全过程运动学预演的视频可保留在对应任务目录，以 `<date>_<run_id>_kinematic_<camera>.mp4` 命名，并在配套目录中标注预演性质；不能计为已完成的物理机器人执行，也不能替代正式副本。
- 使用实际文件副本，不以指向工作目录的软链接或硬链接代替归档；视频与配套材料一起构成保留副本，播放与核心证据不得依赖原始 run 目录。原始产物可以继续留在原位，新版本使用新的文件名前缀和配套目录，禁止覆盖最后一份已验证副本。
- 清理、迁移或重跑覆盖 `runs/` 时，必须保护上述副本。每个已完成环境始终至少保留一份经过检查的完整 demo；删除旧版前先确认替代副本齐全。`runs/` 被 Git 忽略不代表归档可以删除。
