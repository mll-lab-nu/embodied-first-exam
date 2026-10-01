# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-balance-simple-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-balance-simple-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-loco-balance-simpl__e3XTKSR`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 146.25 / pass mark 800) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3548 s |
| tokens in / out | 22,866,637 / 156,506 (within the budget) |
| cost | $0.33 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 248, "final_reward": 4.728570290927322e-05, "sim_steps": 248, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

survival-steps search: const targets, COM/board PD, MPC stuck at 190; timed knee/hip-roll edits on saved actions; 248 steps, board hits floor
