# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-balance-hard-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-balance-hard-codex-gpt6luna-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-loco-balance-hard__WTxSB35`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 45.44 / pass mark 800) |
| mode | standard; reset budget 50 (resets used: 50); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 1000 s |
| tokens in / out | 5,084,490 / 83,890 (within the budget) |
| cost | $0.11 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 66, "sim_steps": 2117, "steps": 2117, "resets": 50, "elapsed_s": 983.3, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

IMU hip/ankle feedback, board-angle estimate, hip-roll loop; spec masses printed not used; longest ep 75; graded ep50 board down at step 66
