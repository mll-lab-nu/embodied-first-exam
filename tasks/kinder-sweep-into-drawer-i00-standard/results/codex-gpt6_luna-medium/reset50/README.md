# Codex + GPT-6 Luna, effort medium — kinder-sweep-into-drawer-i00-standard

Recorded 2026-10-01 under protocol v1.0 (Harbor job `r50-kinder-standard`, trial `kinder-sweep-into-drawer-i00-sta__kfxouBa`).

| | |
|---|---|
| result | **0** |
| mode | standard (`eai-standard/2.1`); reset budget 50 (the optional reset capability, PROTOCOL D1: reported separately from runs without reset); sensors: the robot cameras, wrist depth, odometry, joint encoders |
| agent | Harbor's `codex` agent, Codex 0.159.2, `openai/gpt-6-luna` through OpenRouter, reasoning effort medium, web search disabled (`scripts/kinder/configs/codex-openrouter.yaml`) |
| budget | 60 min; tokens 100M in / 10M out (PROTOCOL D10) |
| agent time | 3603 s |
| tokens in / out | 26,645,024 / 169,978 (within the budget) |
| cost | $0.38 |
| verifier | `{"success": 0, "live_success": 0, "replay_success": 0, "deterministic": 1, "finalized": 1, "missing_log": 0, "infra_error": 0, "grader_error": 0, "sim_crashed_on_call": 0, "n_actions": 275, "sim_steps": 2067, "calls": 3547, "rows": 2067, "resets": 5, "reset_budget": 50, "sim_startups": 1, "elapsed_s": 3587.6, "video_rendered": 1}` |

![the verifier's replay, last frame](replay.last.jpg)

## What happened

First move within a minute of its first request; 1811 chunks in all, 2067 control steps over 6 episodes (5 of its 50 resets used); its own labels include "pregrasp_cube2:0", "pregrasp_cube2:1", "pregrasp_cube2:2" (and 1798 more). Of the episodes before the last, 5 abandoned by a reset while running. The graded episode 6 was still running at its control step 275 when its 60 min ran out (timeout).
