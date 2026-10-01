# Codex + GPT-6 Luna, effort medium — humanoidbench-loco-stair-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-hb-standard`, trial `humanoidbench-loco-stair-i00-sta__btuVjoS`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 1418 s |
| tokens in / out | 5,869,095 / 93,024 (within the budget) |
| cost | $0.12 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 167, "sim_steps": 5655, "calls": 2222, "rows": 5655, "resets": 50, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 1381.8, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request; 2146 chunks in all, 5655 control steps over 51 episodes (50 of its 50 resets used); its own labels include "gait period=1.0, hip_amp=0.42, knee_lift=0.52", "gait period=1.4, hip_amp=0.12, knee_lift=0.15", "gait period=2.5, hip_amp=0.12, knee_lift=0.15" (and 17 more). Of the episodes before the last, 44 ended by the task's own termination, 6 abandoned by a reset while running. The graded episode 51 was ended by the task's own termination at its control step 167 (failed; this task ends when the robot falls (its torso tips close to horizontal)).
