# tactilelab-cloth-fold-half-i00-privileged

| | |
|---|---|
| Benchmark | TactileLab |
| Mode | privileged |
| Twin | `tactilelab-cloth-fold-half-i00-standard` |
| Simulator / robot | `tactilelab` / `xtrainer-gsmini` |
| Family / instance | `cloth_fold_half` / seed 0 |
| Oracle | `full` — solution/: the scripted demonstration policy of this task, recorded through the Session; graded 1 by two fresh-process replays, which ended in the same state on an L40S (verifier, 2026-10-29); nop graded 0. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:tactilelab-0.2.0` |

## Task
Fold the cloth in half over the fold line and let go.

## Difficulty
Contact-rich manipulation with a tactile gripper, driven through end-effector targets only.

## Reference solution
`solution/oracle_cloth_fold_half.py`: the scripted demonstration policy, recorded through the Session; `solution/solve.sh` lays the policy code over the package first (the agent's image does not carry it).

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` (`tests/grade.py`): two fresh-process replays, which must both succeed and end in the same final-state hash. The rebuilt scene must hash to `instance.json` `state_sha`, the time limits and whose failure a 0 is: tasks/tactilelab/README.md.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 13 GiB | 2048 | 16 GiB | 10 GiB |
| verifier | 8 | 20 GiB | no cap | 16 GiB | 20 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `main`.
- Recommended GPU: L40S 48GB.

## Details
| | |
|---|---|
| Simulator | TactileLab tasks on Isaac Lab 2.3.2 / Isaac Sim 5.1 (PhysX on the GPU, RTX rendering), X-Trainer with two GelSight Mini sensors (taxel raycast + Taxim look-up table) |
| Task | `cloth_fold_half`; the frozen instance (the scene state after reset, with its hash) is `environment/instance.json` |
| Image | built locally on every host (`images/tactilelab/BUILD_ONLY`: it contains Isaac Sim); needs an RTX-class NVIDIA GPU (`environment/docker-compose.yaml`) |
| Budget | the agent's cutoff is the `Agent time budget` row above (this task's `[agent] timeout_sec`); every Python process pays ~1 min of Isaac Sim launch + scene build (tasks/tactilelab/README.md) |
| Benchmark notes | tasks/tactilelab/README.md |
