# Codex + GPT-6 Luna, reasoning effort xhigh, 60 min — metaworldplus-push-i00-standard

Run: Harbor job `codex-gpt6_luna-xhigh-sample`, trial `metaworldplus-push-i00-standard__tCoxUL8`, 2026-10-01. Mode: **standard (robot as a service)**.

| | |
|---|---|
| result | **0** |
| agent time | 2431 s |
| actions / sim steps | 1865 / 1865 |
| tokens in / out (cached in) | 7699591 / 101389 (7284480) |
| token budget | 100M in / 10M out per trial (PROTOCOL §5 default): within (`over_token_budget = 0`) |
| verifier | `{"success": 0, "deterministic": 1, "replay_success": 0, "live_success": 0, "finalized": 1, "control_steps": 1865, "sim_steps": 1865, "calls": 97, "elapsed_s": 2698.3, "final_reward": 0.007002346229975704, "video_rendered": 1, "sim_error": 0, "infra_error": 0, "grader_error": 0}` |
| verifier sandbox | separate, no network |
| setup | Harbor 0.23.0 `-a codex` (Codex CLI ?), model `openai/gpt-6-luna`, `reasoning_effort=xhigh`, no reasoning summaries; ChatGPT subscription login (`CODEX_FORCE_AUTH_JSON=1`); agent egress allowlisted to the model APIs |

## Agent's last messages

- The fingers are still short in x, but the top view puts them just behind the puck. I’m trying a controlled 4 cm sweep along y toward the target to see if the edge contact can move it into a more reachable position.
- The edge tests have not made contact. I’m checking whether the arm can reach farther left at a different y posture, then I’ll use that posture to approach the puck if it gives us more x reach.
- I couldn’t complete the push. After a push, the puck drifted toward the far-left edge. The top view showed it outside the arm’s reachable area, and later contact probes did not move it. I stopped submitting actions with the arm raised and the puck stationary.  I left the controller at [gen.py](/app/output/gen.py). The staged camera and action records are in `/app/runs/controller`.

## Failure analysis

The agent pushed the puck once, saw it slide towards the far-left edge of the table and lost it outside the arm's reach; later contact probes did not move it. With no reset the episode could not be recovered; it stopped with the puck far from the target (final dense reward 0.007).
