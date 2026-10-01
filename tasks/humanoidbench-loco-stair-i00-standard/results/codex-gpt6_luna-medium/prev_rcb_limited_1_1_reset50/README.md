# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-stair-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-stair-codex-gpt6luna-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-loco-stair-i00-lim__P8XiYVR`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 17.23 / pass mark 700) |
| mode | standard; reset budget 50 (resets used: 50); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 675 s |
| tokens in / out | 3,007,661 / 58,372 (within the budget) |
| cost | $0.07 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 122, "sim_steps": 3918, "steps": 3918, "resets": 50, "elapsed_s": 654.2, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

hip -0.8 lean stance + small shuffle + IMU fixes; no ep past 150 steps, barely moved; untested low-pass variant graded, fell at step 122
