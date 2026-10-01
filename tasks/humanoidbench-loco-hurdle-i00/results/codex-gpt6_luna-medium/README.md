# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-hurdle-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-hurdle-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-loco-hurdle-i00__vcTe69J`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 50.22 / pass mark 700) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3544 s |
| tokens in / out | 28,222,774 / 125,761 (within the budget) |
| cost | $0.37 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 266, "final_reward": 1.224483688822332e-10, "sim_steps": 266, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

numpy PPO failed, then DE on 19-param phase gait w/ state feedback + hand offsets; clears 1st hurdle, falls x~9.4 m at step 266
