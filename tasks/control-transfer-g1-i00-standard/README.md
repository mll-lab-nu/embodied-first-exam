# control-transfer-g1-i00-standard

| | |
|---|---|
| Benchmark | Control Transfer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (policy adaptation is standard only, PROTOCOL §4p) |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `control-transfer/g1` / seed 0 |
| Oracle | `none` — Implementation validation is separate from a successful reference. Native Harbor oracle/nop validation and reference calibration pending. |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0` |

## Task
Train a 29-DoF Unitree G1 walking policy in mjlab/MuJoCo Warp and transfer to CPU MuJoCo. Stand 2 s, walk forward at 0.6 m/s for 18 s.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
No verified full oracle yet. Reference implementation checks are not model scores.

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 12 | 4 |
| Memory | 30 GB | 6 GB |
| GPU memory | 24 GB | 0 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: RTX 4090 24GB or larger CUDA GPU.
- Measured: provisional training allocation; convergence and native GPU resource calibration pending
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: 24 GiB GPU memory, 20 GiB memory, 512 processes, 40 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 24 GiB GPU memory, 30 GiB memory. Limits measured: provisional training budget; not a measured minimum.

## Details

### Notes
Simulation transfer only, not hardware. Fixed 98→512→256→128→29 ELU actor, frozen public PD wrapper. Coding-agent feedback contains only joint angles and images.
