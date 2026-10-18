# roboengineer-landing-random-pad-i00-standard

| | |
|---|---|
| Benchmark | roboEngineer |
| Mode | standard (`eai-policy/1.0`) |
| Twin | — (none: roboEngineer has no privileged mode, PROTOCOL §2.15) |
| Simulator / robot | `mujoco` / `intel-aero-partial` |
| Family / instance | `roboengineer/landing-random-pad` / seed 0 |
| Oracle | `full` — Harbor 0.23.0 oracle agent on aws:rcb-cpu3, 2026-10-18, image eai-quadrotor-landing:0.1.0: six safe held-out landings of six, mean score 84.11; nop 0. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-quadrotor-landing:0.1.0` |

## Task
**roboEngineer → Drone → Neural Landing.** See the [collection roadmap](../../docs/benchmarks/roboengineer.md).

Randomized aerial landing with bounded sensor-only policy adaptation and a private held-out bank. Reference runs: the Oracle row; build instructions: docs/benchmarks/roboengineer.md.

## Difficulty
Identify unmodeled aerodynamic forces using noisy sensors and camera samples, while trading landing time against contact safety.

## Reference solution
The scripted learner in `solution/` fits force corrections from permitted IMU/RPM feedback over three rounds. It is not installed in the agent image. It lands all six held-out cases on both instances (the Oracle row).

## Verification
The private MuJoCo service evaluates the sealed policy in six held-out cases, each replayed twice in fresh processes. The no-network verifier reads only collected simulator evidence and emits binary success plus a continuous score. Reference times come from finite full-model optimization, without a claim of global optimality. Ground-truth states, model residuals, seeds, reference searches and grades are never feedback to the agent.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 1 |
| Memory | 8 GB | 1 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: Harbor 0.23 oracle / nop on aws:rcb-cpu3 (2026-10-18; the author: an 8-vCPU / 16-GiB c7i.2xlarge): the sidecar's reference search before the agent ~520 s on its 4 CPUs, finalization + video ~150 s; the verifier only reads JSON (~20 s)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 12 GiB memory. Limits measured: the reference runs (2026-10-18) peaked at 0.04 GiB in the agent's container; 4 GiB (the author's budget) leaves room for an agent's own nominal training; processes / disk: design defaults.
