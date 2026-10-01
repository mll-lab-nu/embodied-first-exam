# Codex + GPT-6 Sol, effort medium — humanoidbench-loco-walk-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-walk-codex-gpt6sol-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-loco-walk-i00-limi__JB3uDYx`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 52.65 / pass mark 700) |
| mode | standard; reset budget 50 (resets used: 50); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-sol`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 739 s |
| tokens in / out | 4,176,155 / 21,236 (within the budget) |
| cost | $1.26 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 223, "sim_steps": 6717, "steps": 6717, "resets": 50, "elapsed_s": 717.8, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

stance bias, sine then IK shuffle gait; spec facts printed only; graded ep50 (untried ankle switch + speed ramp) fell forward at step 223
