# roboengineer-anycar-compact-lap-monaco-6-i01-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2.15) |
| Simulator / robot | `mujoco` / `anycar` |
| Family / instance | `roboengineer/anycar-compact-lap-monaco-6` / seed 1 |
| Oracle | `full` — Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-control-transfer:0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 10/10 held-out cases, mean engineering score 76.21; nop 0. |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-control-transfer:0.2.0` |

## Task
Track a complete compact F1-inspired lap, targeted at 28 seconds within a 30-second episode, avoiding collisions/offtrack.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-control-transfer:0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 10/10 held-out cases, mean engineering score 76.21; nop 0.

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 1 |
| Memory | 12 GB | 1 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle / nop on aws:rcb-cpu3 (2026-10-18): finalization (held-out x2, 4 workers) + video 76-217 s on the sidecar's 4 CPUs; the verifier only reads JSON (~20 s)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: the reference runs (2026-10-18) peaked at 0.04 GiB in the agent's container; 4 GiB (the author's budget) leaves room for an agent's own nominal training; processes / disk: design defaults.

## Details

### Notes
Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No learned vehicle model is evaluated. F1-inspired: periodic smoothing and minor-axis widening, then 45m normalization. Not exact scaled circuit outlines; tight corners/crossovers may be removed.
