# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-push-i00-standard, 50 resets

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-limited-push-codex-gpt6luna-medium-60min-reset50-imu-roomcam-text7`, trial `humanoidbench-manip-push-i00-lim__R6DtjyA`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return -224.09 / pass mark 700) |
| mode | standard; reset budget 50 (resets used: 50); sensors: head+joints+imu+room |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 2859 s |
| tokens in / out | 32,302,485 / 151,810 (within the budget) |
| cost | $0.42 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 500, "sim_steps": 2568, "steps": 2568, "resets": 50, "elapsed_s": 2727.2, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

pixel-only arm probes, hip lean, 18-pose reset batch; box never touched; graded ep used spec-FK arm pose, fell back by step 120, ran to 500
