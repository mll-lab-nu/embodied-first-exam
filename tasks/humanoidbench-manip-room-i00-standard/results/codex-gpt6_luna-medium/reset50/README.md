# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-room-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-manip-room-i00-sta__PK4BqQt`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 160 s |
| tokens in / out | 423,289 / 11,619 (within the budget) |
| cost | $0.01 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 127, "sim_steps": 127, "calls": 9, "rows": 127, "resets": 0, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 118.5, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request; 3 chunks in all, 127 control steps over 1 episode (0 of its 50 resets used); its own labels include "hold observed starting posture", "small pitch correction probe", "counter forward lean". The graded episode 1 was ended by the task's own termination at its control step 127 (failed; this task ends when the robot falls (its pelvis drops near the ground)).
