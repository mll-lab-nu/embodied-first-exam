# `topogym/utils` — 通用杂项

和具体任务无关的展示/胶水 helper。

| 文件 | 提供什么 |
| --- | --- |
| `hud.py` | `hud_lines` / `draw_hud_overlay` — 给录制的视频帧画一层文字 HUD；没装 OpenCV 或帧格式不对时直接原样返回，不报错 |
| `recording.py` | `add_recording_args` / `DEFAULT_RECORDING_CONFIG` — 统一的录制 CLI 参数（是否录、路径、相机、fps、每几步录一帧等） |
| `franka.py` | `initialize_franka_controller` — 见 [`module_robot.md`](module_robot.md)，只是取出机器人并配置 `FrankaPositionIKController` 的薄封装 |

**不负责**：新增核心架构逻辑。新的 spec/generator/planner 应该放进 `generation` / `planning`，不要因为"图省事"塞进 `utils`。
