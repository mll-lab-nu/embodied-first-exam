# roboengineer-anycar-compact-lap-silverstone-8-i00-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.1`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2.15) |
| Simulator / robot | `mujoco` / `anycar` |
| Family / instance | `roboengineer/anycar-compact-lap-silverstone-8` / seed 0 |
| Oracle | `full` — Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 10/10 held-out cases, mean engineering score 77.05; nop 0. |
| Agent time budget | 14400 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:control-transfer-0.2.0` |

## Task
Track a complete compact F1-inspired lap, targeted at 28 seconds within a 30-second episode, avoiding collisions/offtrack.

## Difficulty
Infer transfer failures from video and noisy sensors across bounded adaptation rounds.

## Reference solution
Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image efe-private:control-transfer-0.2.0: the reference controller (solution/, three feedback rounds) succeeded on 10/10 held-out cases, mean engineering score 77.05; nop 0.

## Verification
Frozen development and held-out banks, data-only deployment, fresh-process state hashes, separate no-network verifier. All numeric scores and physical outcomes are operator-only until submission closes.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 9 GB | 3 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle on aws:rcb-cpu3 (2026-10-18, anycar-tracking, anycar-compact-lap-monaco-6, anycar-tight-drift-park, neuralfly-general-skydio, go2-weave; docker stats + cgroup memory.peak every 3-6 s): sidecar 1.7-1.9 cores during deployments, its 4-CPU cap during finalization (held-out x2, 4 workers, + video: 79-199 s), peak 0.6-2.13 GiB (go2-weave); the agent's container <= 0.23 GiB. Minimum = the agent's 6 GB cap (its 4 GiB limit is recorded, not enforced, by default) + the sidecar's peak x 1.2 + the monitor's 0.25 GB; CPU = the agent's 2-core cap + the sidecar's ~2 during deployments, the sidecar's 4 after the agent is stopped; verifier phase = the sidecar's collect hook (4 cores, <= 2.13 GiB x 1.2 + the monitor); the verifier itself only reads JSON (~20 s)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: the reference runs (2026-10-18) peaked at 0.23 GiB in the agent's container; 4 GiB (the author's budget) leaves room for an agent's own nominal training; processes / disk: design defaults.

## Details

### Notes
Procedural chassis with retained contact-wheel mechanism. Rigid Coulomb friction is not deformable sand. No learned vehicle model is evaluated. F1-inspired: periodic smoothing and minor-axis widening, then 45m normalization. Not exact scaled circuit outlines; tight corners/crossovers may be removed.
