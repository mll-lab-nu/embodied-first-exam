# control-transfer-anycar-drift-i00-standard

> Experimental multi-round policy proposal. This package is not admitted by main's `eai-standard/2.x` protocol or listed in the accepted dataset. Its historical ID is retained for traceability; successful package checks are not protocol approval.

| | |
|---|---|
| Benchmark | Control Transfer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (experimental multi-round policy proposal; not an accepted standard-mode task) |
| Simulator / robot | `mujoco` / `anycar` |
| Family / instance | `control-transfer/anycar-drift` / seed 0 |
| Oracle | `none` — Development-only drift-park/1. A scripted nominal example succeeds, but the frozen controller passes 0/26 randomized cases across two plants (6 adaptation and 20 held-out). Three exact fresh-process and rendered replays pass. Transfer solvability and LLM evaluation remain unverified. Native infrastructure validation is reported separately from control success. No full oracle; human review required. |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0` |

## Task
Follow the ordered U-bend, then slide sideways into a parallel-parking space between two stationary cars and hold a precise stop.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Development-only drift-park/1. A scripted nominal example succeeds, but the frozen controller passes 0/26 randomized cases across two plants (6 adaptation and 20 held-out). Three exact fresh-process and rendered replays pass. Transfer solvability and LLM evaluation remain unverified. Native infrastructure validation is reported separately from control success. No full oracle; human review required.

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 4 |
| Memory | 12 GB | 6 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: provisional caps; CPU adapter smoke runs only, native container peak measurements pending
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: provisional generous caps; native validation pending.

## Details

### Notes
Rigid RC tire contact and rear-wheel dry-friction brake; not a calibrated pneumatic-tire drifting or vehicle-damage model.
