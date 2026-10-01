# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-basketball-i00

Recorded 2026-09-28 before protocol v1.0 (Harbor job `hb-full-basketball-codex-gpt6luna-medium-60min-text7`, trial `humanoidbench-manip-basketball-i__PQUfSN3`). Not an official v1.0 result: the run went through the repository's former OpenRouter adapter (`harbor_agents/`, removed under PROTOCOL D11), and on the task as it then was.

| | |
|---|---|
| result | **0** (return 1091.75 / pass mark 1200) |
| mode | privileged |
| task version | before protocol v1.0, which changed only this task's metadata and image name: the instruction it was given is today's, word for word, and the scene and verifier are the same. |
| agent | Codex 0.157.0 via OpenRouter, `openai/gpt-6-luna`, reasoning effort medium, web search off |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3602 s |
| tokens in / out | 24,391,629 / 219,488 (within the budget) |
| cost | $0.42 |
| verifier | `{"success": 0, "all_success": 0, "deterministic": 1, "n_actions": 125, "final_reward": 1000.9323627703001, "sim_steps": 125, "grader_error": 0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

IK + DE search of prep/reach/strike/recovery poses on own hoop proxy; ball sinks at step 125, pre-sink part ~91; 1091.75<1200; timed out
