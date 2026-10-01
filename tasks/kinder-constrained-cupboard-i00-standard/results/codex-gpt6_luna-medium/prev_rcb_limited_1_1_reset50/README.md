# Codex + GPT-6 Luna, effort medium — kinder-constrained-cupboard-i00-standard, 50 resets

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-limited-constrained-cupboard-codex-gpt6luna-medium-60min-reset50-depth-ee`, trial `kinder-constrained-cupboard-i00__Ude7beA`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** |
| mode | standard; reset budget 50 (resets used: 43); sensors: cams+proprio+depth |
| task version | rcb-limited/1.1, the protocol before v1.0: one action or a batch per `POST /step`, base64 images, `POST /reset` within a budget; this task now speaks eai-standard/2.1, so its instruction and client differ from what this run had. The scene, sensors, actions and success check are the same. |
| agent | Codex 0.159.2 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 42,864,098 / 335,244 (within the budget) |
| cost | $0.68 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "n_actions": 1000, "sim_steps": 1000, "steps": 23005, "resets": 43, "elapsed_s": 3615.4, "video_rendered": 1, "grader_error": 0}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

FK/IK at end_effector, base-cam rod map; gen.py rerun 40 eps, all 6 released in 4 eps without success, last 2 on the roof; ep43 5/6 by step 1000
