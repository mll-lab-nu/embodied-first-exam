# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-cube-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-cube-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-cube-i00__iXg59UK`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 325.05 / pass mark 370) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3486 s |
| tokens in / out | 33,209,253 / 137,007 (within the budget) |
| cost | $0.46 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 500, "final_reward": 0.7266939219469533, "sim_steps": 500, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

pitch/x feedback legs (first 500 steps at 25 min), timed shoulder-yaw/wrist/right-arm turns tuned on linear signed-dot mean 0.893; 325.05
