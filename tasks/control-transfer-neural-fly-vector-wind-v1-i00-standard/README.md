# control-transfer-neural-fly-vector-wind-v1-i00-standard

| | |
|---|---|
| Benchmark | Control Transfer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (policy adaptation is standard only, PROTOCOL §4p) |
| Simulator / robot | `mujoco` / `neural-fly-partial` |
| Family / instance | `control-transfer/neural-fly-vector-wind-v1` / seed 0 |
| Oracle | `none` — Development-only general-eight-wind/1 with synthetic isotropic vector drag, not directionally flight-calibrated dynamics. Existing scalar-wind reference results do not establish acceptance of this revision. Native Harbor and LLM acceptance remain unperformed. No full oracle; human review required. |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0` |

## Task
Track six timed laps of a randomized figure eight: vertical, horizontal or inclined plane; yaw in [-pi,pi]; both traversal directions; half extents 0.9-1.5 m and 0.45-0.85 m; angular rate 0.8-1.1 rad/s; randomized phase, center and initial offset. Follow the provided world-frame position, velocity and acceleration commands.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Development-only general-eight-wind/1 with synthetic isotropic vector drag, not directionally flight-calibrated dynamics. Existing scalar-wind reference results do not establish acceptance of this revision. Native Harbor and LLM acceptance remain unperformed. No full oracle; human review required.

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
Flight-data quadratic force surrogate and approximate rigid-body/actuator dynamics; not DAIML or PX4. Fixed 50-degree command tilt envelope; 2.2 thrust-to-weight limit. Synthetic world-frame vector wind with isotropic quadratic drag increment (0.045 kg/m); not calibrated directional aerodynamics. Per-axis residual force cap remains 12 N.
