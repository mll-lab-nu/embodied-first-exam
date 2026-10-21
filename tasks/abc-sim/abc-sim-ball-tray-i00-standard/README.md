# abc-sim-ball-tray-i00-standard

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `abc-sim-ball-tray-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `ball_tray` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` |

## Task
ABC Sim `ball_tray_balancing` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Grab the tray by both handles -- the left gripper on one handle bar, the right gripper on the other -- and keep the ball on the tray. The moment both handle bars are touched by the fingers (one arm's fingers on each bar), an 11-second countdown starts and the ball gets a push every 0.5 s (a 0.1 s force in the tray's plane, up to ~0.18 m/s each, its direction drifting from push to push). Success: the countdown completes with the ball on the tray throughout and both handles held throughout (each bar touched by its arm's fingers within the last 0.1 s at every control step). Failure, which ends the episode: the ball leaves the tray (its centre outside the tray floor's central ~0.26 x 0.25 m area, or lower than 8 mm above the floor), or a handle is let go during the countdown.
A flat tray with a handle bar along each side lies on the table with a small ball on it. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. A bimanual grasp of both handles, then closed-loop balancing for 11 s against random pushes the agent cannot predict, with the ball's position known only from the cameras (standard modes). The action is joint-level (two 6-joint arms and two grippers; no motion primitives).

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 453 rows, streamed as `joint_position` chunks through the client (`solution/oracle_stream.py`); the service executes exactly those rows and ends at the same state as the privileged replay.

## Verification
The live episode's verdict (PROTOCOL H.4): the sim sidecar judges the episode it ran by the task's rule (the 1.02 s hold included) and the collect hook (`/opt/abc-tools/standard/finalize.sh`) writes it to `final.json`; the verifier (the shared `v2_1/grade.py`) transcribes it. Nothing is replayed to grade it; the video is rendered from the trajectory afterwards. `nop`: the episode times out, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 4 GB |
| GPU memory | 1.5 GB | 1.5 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: oracle trials of all 60 directories, RTX 4090 workstation, 2026-10-21 (docker stats every 3 s; the rcb_monitor's NVML samples): the sim sidecar 2.1 GB and 0.83 GiB of GPU memory (standard, chess; realtime 0.8 GB and 0.72 GiB), the agent's container (the client) 0.03 GB; the collect hook renders the video inside the sidecar (EGL)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 5 GiB GPU memory, 16 GiB memory. Limits measured: the agent's container holds Python and the client only (0.03 GB in the oracle trials, no GPU); the whole trial adds the sim sidecar (2.1 GB and 0.83 GiB of GPU memory at most in the oracle trials, 2026-10-21) under its 10 GiB cap; processes 512 and disk 20 GiB: design defaults.

## Details
| | |
|---|---|
| Upstream | ABC Sim, `abc_sim` of github.com/amazon-far/abc @ d0832d1 (Apache-2.0; assets CC BY 4.0 / MIT), on MuJoCo 3.6.0 |
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `6cdaa86a450092e7`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `ball_tray_balancing` held 30 control steps (ball tray: its own rule, tasks/abc-sim/README.md) |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.

### Change Log
- 2026-10-21: first version.
