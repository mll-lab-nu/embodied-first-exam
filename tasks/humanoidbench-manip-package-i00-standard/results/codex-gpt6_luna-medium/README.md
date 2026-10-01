# Codex + GPT-6 Luna, effort medium — humanoidbench-manip-package-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `n0-hb-standard`, trial `humanoidbench-manip-package-i00__BEQVXkq`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 0 (the standard configuration); sensors: head cameras, joint angles and velocities, pelvis IMU, room camera |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/humanoidbench/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 566 s |
| tokens in / out | 2,367,207 / 37,343 (within the budget) |
| cost | $0.05 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 1000, "sim_steps": 1000, "calls": 28, "rows": 1000, "resets": 0, "reset_budget": 0, "sim_startups": 1, "elapsed_s": 547.4, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request (after 2 free looks), then 24 chunks of 5–100 rows (linear, dt 0.02 s); its own labels: "small torso yaw to inspect package", "40-step low-amplitude alternating gait test", "return to known initial standing pose" (and 15 more). The episode used up its 1000 control steps without reaching the goal (failed).
