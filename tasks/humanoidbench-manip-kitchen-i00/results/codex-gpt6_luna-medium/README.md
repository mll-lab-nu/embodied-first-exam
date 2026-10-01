# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-kitchen-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-kitchen-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-kitchen-i00__cjukLmF`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 0.00 / pass mark 4) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3445 s |
| tokens in / out | 22,248,724 / 211,562 (within the budget) |
| cost | $0.40 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 375, "final_reward": 0.0, "sim_steps": 375, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

source goals + IK; microwave max ~0.13 rad, knob -0.66 alone; 375-step traj skips microwave, kettle ~0.20 off, knob unmoved; 0.00
