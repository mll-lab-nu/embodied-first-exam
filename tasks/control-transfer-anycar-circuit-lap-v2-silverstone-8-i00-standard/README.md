# control-transfer-anycar-circuit-lap-v2-silverstone-8-i00-standard

| | |
|---|---|
| Benchmark | Control Transfer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (policy adaptation is standard only, PROTOCOL §4p) |
| Simulator / robot | `mujoco` / `anycar` |
| Family / instance | `control-transfer/anycar-circuit-lap-v2` / seed 0 |
| Oracle | `none` — Development-only circuit-lap/2. Local full-lap positives exist on Silverstone, Monaco and Suzuka, with one full-video replay and a zero no-op control. All-layout multi-round native Harbor and LLM acceptance remain unperformed. No full oracle; human review required. |
| Agent time budget | 129600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0` |

## Task
Track one complete lap of a scaled circuit at the prescribed speed; cross every ordered gate and finish line, avoiding collisions/offtrack. Record actual finish-crossing time.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Development-only circuit-lap/2. Local full-lap positives exist on Silverstone, Monaco and Suzuka, with one full-video replay and a zero no-op control. All-layout multi-round native Harbor and LLM acceptance remain unperformed. No full oracle; human review required.

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
Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No AnyCar learned transformer is evaluated. Planar SVG-derived schematic, smoothed and uniformly scaled for RC steering; no elevation/bridge reconstruction.
