# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-insert-normal-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-manip-insert-norma__u6jjHnv`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 32,260,947 / 139,449 (within the budget) |
| cost | $0.42 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 55, "sim_steps": 1326, "calls": 261, "rows": 1326, "resets": 24, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 3592.7, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move 1 min after its first request; 140 chunks in all, 1326 control steps over 25 episodes (24 of its 50 resets used). Of the episodes before the last, 3 ended by the task's own termination, 21 abandoned by a reset while running. The graded episode 25 was still running at its control step 55 when its 60 min ran out (timeout).
