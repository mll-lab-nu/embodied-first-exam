# Codex + GPT-6 Luna, reasoning effort xhigh, 60 min — metaworldplus-assembly-i00-standard

Run: Harbor job `codex-gpt6_luna-xhigh-sample`, trial `metaworldplus-assembly-i00-stand__KgXgFm5`, 2026-10-01. Mode: **standard (robot as a service)**.

| | |
|---|---|
| result | **0** |
| agent time | 1791 s |
| actions / sim steps | 2026 / 2026 |
| tokens in / out (cached in) | 4714515 / 71500 (4565120) |
| token budget | 10M in / 10M out per trial: within (`over_token_budget = 0`) |
| verifier | `{"success": 0, "deterministic": 1, "replay_success": 0, "live_success": 0, "finalized": 1, "control_steps": 2026, "sim_steps": 2026, "calls": 91, "elapsed_s": 2060.3, "final_reward": 1.2950727212428463, "video_rendered": 1, "sim_error": 0, "infra_error": 0, "grader_error": 0}` |
| verifier sandbox | separate, no network |
| setup | Harbor 0.23.0 `-a codex` (Codex CLI ?), model `openai/gpt-6-luna`, `reasoning_effort=xhigh`, no reasoning summaries; ChatGPT subscription login (`CODEX_FORCE_AUTH_JSON=1`); agent egress allowlisted to the model APIs |

## Agent's last messages

- The ring is lowered to the peg’s height and remains aligned in the overhead view. I’m opening the gripper so it can settle onto the peg, then I’ll inspect the final state without advancing the simulator.
- The nut is released, and the left camera shows it resting around the peg. The overhead view places it close to the provided target point. I’m stopping control submissions here so the episode remains in this final state.
- The nut is released and appears seated around the peg in the final camera views. I stopped submitting controls after the release, leaving that state for grading.  Controller: [gen.py](/app/output/gen.py)   Trajectory record: [trajectory.jsonl](/app/output/trajectory.jsonl)

## Failure analysis

The agent lifted the nut, lowered it next to the peg and released it, judging from the overhead and side views (the gripper occluding the peg) that it was seated. The replay's final frame shows the nut beside the peg, not on it; Meta-World's check (aligned and hooked) fails in the live episode and the replay alike (final dense reward 1.3).
