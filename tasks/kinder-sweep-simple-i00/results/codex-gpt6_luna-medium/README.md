# Codex + GPT-6 Luna, effort medium — kinder-sweep-simple-i00

Recorded 2026-09-29 before protocol v1.0 (Harbor job `kinder-full-sweep-simple-codex-gpt6luna-medium-60min`, trial `kinder-sweep-simple-i00__jfJARDU`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is an earlier wording of today's; the scene and verifier are the same. |
| agent | Codex 0.159.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 17,472,185 / 200,067 (within the budget) |
| cost | $0.34 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 536, "sim_steps": 536, "missing_trajectory": 0, "invalid_trajectory": 0, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

base cannot touch cubes; wiper grasps failed; 3 gripper-pad sweeps along +y moved 4 cubes 6-34 cm; 0/10 in box; 536-step replay fails
