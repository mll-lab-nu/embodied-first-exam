# tactilelab-cable-needle-thread-i00-privileged

| | |
|---|---|
| Benchmark | TactileLab |
| Mode | privileged |
| Twin | — (privileged only) |
| Simulator / robot | `tactilelab` / `xtrainer-gsmini` |
| Family / instance | `cable_needle_thread` / seed 0 |
| Oracle | `full` — solution/: the scripted demonstration policy of this task, recorded through the Session; graded 1 by the fresh-process replay. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe-private:tactilelab-0.1.0` |

## Task
Thread the cable tip through the square hole in the wall.

## Difficulty
Contact-rich manipulation with a tactile gripper, driven through end-effector targets only.

## Reference solution
`solution/oracle_cable_needle_thread.py`: the scripted demonstration policy, recorded through the Session; `solution/solve.sh` lays the policy code over the package first (the agent's image does not carry it).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in one fresh process (`tests/grade.py`); pass iff the task's success predicate holds, and the rebuilt frozen scene matches the recorded one.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 13 GB | 13 GB |
| GPU memory | 6.5 GB | 6.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: L40S 48GB / L4 24GB / RTX 4090 24GB.
- Measured: author estimate: one Isaac Sim 5.1 process (PhysX on the GPU, RTX rendering) took 8-10 GB of host memory and 4-6 GB of GPU memory in the author's runs; to be re-measured
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: 24 GiB GPU memory, 24 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 24 GiB GPU memory, 24 GiB memory. Limits measured: author estimate: one Isaac Sim 5.1 process (PhysX on the GPU, RTX rendering) took 8-10 GB of host memory and 4-6 GB of GPU memory in the author's runs; to be re-measured.

## Details
| | |
|---|---|
| Simulator | TactileLab tasks on Isaac Lab 2.3.2 / Isaac Sim 5.1 (PhysX on the GPU, RTX rendering), X-Trainer with two GelSight Mini sensors (taxel raycast + Taxim look-up table) |
| Task | `cable_needle_thread`; the frozen instance (the scene state after reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/tactilelab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); every Python process pays ~1 min of Isaac Sim launch + scene build (tasks/tactilelab/README.md) |
| Benchmark notes | tasks/tactilelab/README.md |
