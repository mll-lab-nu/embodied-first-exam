# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-basketball-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `n0-hb-standard`, trial `humanoidbench-manip-basketball-i__Q8WEny3`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 0 (the standard configuration); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 141 s |
| tokens in / out | 317,724 / 9,221 (within the budget) |
| cost | $0.01 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 48, "sim_steps": 48, "calls": 7, "rows": 28, "resets": 0, "reset_budget": 0, "sim_startups": 1, "elapsed_s": 99.2, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request (after 3 free looks), then 2 chunks of 10–20 rows (linear, dt 0.02 s) and 1 timed watch; its own labels: "raise arms for ball", "reach higher". The task's own termination ended the episode at control step 48 of 500 (failed; this task ends when the ball goes through the hoop, when the ball drops low, when the robot falls).
