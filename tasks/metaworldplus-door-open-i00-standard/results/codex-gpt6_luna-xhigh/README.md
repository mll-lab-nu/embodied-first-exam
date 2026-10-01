# Codex + GPT-6 Luna, reasoning effort xhigh, 60 min — metaworldplus-door-open-i00-standard

Run: Harbor job `codex-gpt6_luna-xhigh-sample`, trial `metaworldplus-door-open-i00-stan__UHDgzFJ`, 2026-10-01. Mode: **standard (robot as a service)**.

| | |
|---|---|
| result | **0** — agent ended with `AgentTimeoutError` |
| agent time | 3603 s |
| actions / sim steps | 1123 / 1123 |
| tokens in / out (cached in) | 13786303 / 142239 (13370496) |
| token budget | 10M in / 10M out per trial: **over** (`over_token_budget = 1`, scored 0) |
| verifier | `{"success": 0, "deterministic": 1, "replay_success": 0, "live_success": 0, "finalized": 1, "control_steps": 1123, "sim_steps": 1123, "calls": 102, "elapsed_s": 3868.9, "final_reward": 5.376322185419836, "video_rendered": 1, "sim_error": 0, "infra_error": 0, "grader_error": 0}` |
| verifier sandbox | separate, no network |
| setup | Harbor 0.23.0 `-a codex` (Codex CLI ?), model `openai/gpt-6-luna`, `reasoning_effort=xhigh`, no reasoning summaries; ChatGPT subscription login (`CODEX_FORCE_AUTH_JSON=1`); agent egress allowlisted to the model APIs |

## Agent's last messages

- The calibrated views show the bar’s free end is still to the right of the TCP, so a leftward pull was moving away from it. I’m repositioning to the right side of the bar, then I’ll push it left in short increments while watching the handle move.
- The arm needed more settling time than the short action chunks allowed. After a half-second hold, the TCP has caught up to its target and is now near the lever. I’ll use a few short pushes with settling holds so I can see whether the door advances, then stop when the handle reaches the marker or the remaining time requires it.
- Short leftward pushes with settling holds are now rotating the door steadily. The open door edge has moved close to the green marker in the top view; I’m continuing in small increments to bring the handle closer without losing contact.

## Failure analysis

The agent first pushed on the wrong side of the handle, then switched to short pushes with settling holds that were rotating the door when the 60-minute limit ended the run (`AgentTimeoutError`). It also used 13.8M input tokens, over the 10M budget, so the trial scores 0 either way.
