# quadrotor-landing-random-pad-i00-standard

> Experimental multi-round policy proposal. This package is not admitted by main's `eai-standard/2.x` protocol or listed in the accepted dataset. Its historical ID is retained for traceability; successful package checks are not protocol approval.

| | |
|---|---|
| Benchmark | Neural Lander |
| Mode | standard (`eai-policy/1.0`) |
| Twin | — (experimental multi-round policy proposal; not an accepted standard-mode task) |
| Simulator / robot | `mujoco` / `intel-aero-partial` |
| Family / instance | `quadrotor-landing/random-pad` / seed 0 |
| Oracle | `full` — Native Harbor 0.23.0 Docker CPU oracle/nop validation passed on both frozen instances with resource enforcement: six safe held-out landings per oracle, exact replay, and zero for no submission. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-quadrotor-landing:0.1.0` |

## Task
**roboEngineer → Drone → Neural Landing.** See the [collection roadmap](../../docs/benchmarks/roboengineer.md).

Randomized aerial landing with bounded sensor-only policy adaptation and a private held-out bank. Native Harbor 0.23.0 Docker CPU oracle/nop validation passed on both instances with resource enforcement; see the benchmark documentation for evidence and build instructions.

## Difficulty
Identify unmodeled aerodynamic forces using noisy sensors and camera samples, while trading landing time against contact safety.

## Reference solution
The scripted learner in `solution/` fits force corrections from permitted IMU/RPM feedback over three rounds. It is not installed in the agent image. Native Harbor oracle validation achieves binary success on all six held-out cases; its continuous timing score is recorded separately.

## Verification
The private MuJoCo service evaluates the sealed policy in six held-out cases, each replayed twice in fresh processes. The no-network verifier reads only collected simulator evidence and emits binary success plus a continuous score. Reference times come from finite full-model optimization, without a claim of global optimality. Ground-truth states, model residuals, seeds, reference searches and grades are never feedback to the agent.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 6 | 4 |
| Memory | 8 GB | 5 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: native Harbor 0.23.0 oracle/nop verified on 8-vCPU/16-GiB AWS c7i.2xlarge, CPU MuJoCo/OSMesa; declared minima remain conservative estimates
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 4 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 9 GiB memory. Limits measured: native Harbor oracle/nop passed with enforcement on both instances; conservative 4 GiB agent / 5 GiB simulator budgets and process/disk design defaults retained.
