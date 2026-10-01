# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-door-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `n0-hb-standard`, trial `humanoidbench-manip-door-i00-sta__figikC6`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 0 (the standard configuration); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 233 s |
| tokens in / out | 496,095 / 15,595 (within the budget) |
| cost | $0.02 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 88, "sim_steps": 88, "calls": 11, "rows": 88, "resets": 0, "reset_budget": 0, "sim_startups": 1, "elapsed_s": 178.0, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move 1 min after its first request (after 3 free looks), then 4 chunks of 20–40 rows (linear, dt 0.02 s); its own labels: "right arm reach toward handle", "extend right arm to touch and press handle", "pull handle back by retracting extended arm" (and 1 more). The task's own termination ended the episode at control step 88 of 1000 (failed; this task ends when the robot falls (its pelvis drops too low)).
