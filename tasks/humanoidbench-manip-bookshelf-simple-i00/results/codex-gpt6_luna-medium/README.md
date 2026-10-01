# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-bookshelf-simple-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-bookshelf-simple-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-bookshelf-si__he9Rdxm`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 793.15 / pass mark 2000) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3602 s |
| tokens in / out | 20,397,928 / 248,542 (within the budget) |
| cost | $0.41 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 1000, "final_reward": 0.7923557676298242, "sim_steps": 1000, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

ankle-pitch stance + IK/pose search; right hand touched trophy but never lifted it; saved hand-resting take; timed out at 60 min
