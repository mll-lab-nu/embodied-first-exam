# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-stair-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-stair-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-loco-stair-i00__x5sby8Q`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 69.70 / pass mark 700) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3530 s |
| tokens in / out | 25,083,805 / 122,123 (within the budget) |
| cost | $0.34 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 251, "final_reward": 1.791634762185904e-12, "sim_steps": 251, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

numpy PPO MLP + ES offset patches on own proxy: stands ~190 steps, lunges ~1.13 m, falls at step 251; proxy ~92 vs replay 69.70
