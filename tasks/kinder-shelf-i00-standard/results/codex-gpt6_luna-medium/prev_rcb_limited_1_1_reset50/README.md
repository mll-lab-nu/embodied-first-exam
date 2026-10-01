# Codex + GPT-6 Luna, effort medium — kinder-shelf-i00-standard, 50 resets

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-limited-shelf-codex-gpt6luna-medium-60min-reset50-depth-ee`, trial `kinder-shelf-i00-limited__ctKfzTU`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** |
| mode | standard; reset budget 50 (resets used: 23); sensors: cams+proprio+depth |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.159.2 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 31,957,561 / 278,574 (within the budget) |
| cost | $0.53 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 659, "sim_steps": 659, "steps": 18839, "resets": 23, "elapsed_s": 3604.1, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

FK/IK at spec end_effector + wrist RGB-D; gen.py replayed pick and route 21 eps, cube height kept changing (0.86/0.59/1.14); ep23 timeout step 659
