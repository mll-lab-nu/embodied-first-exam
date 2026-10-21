# abc-sim-conveyor-pick-i00-standard-realtime

| | |
|---|---|
| Benchmark | ABC Sim |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `abc-sim-conveyor-pick-i00-privileged` |
| Simulator / robot | `mujoco` / `i2rt-yam-bimanual` |
| Family / instance | `conveyor_pick` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` |

## Task
ABC Sim `conveyor_pick` (two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each) side by side at the near edge of a table, facing +x (the left arm is the one at +y)): Pick the three objects off the moving belt and put them in the bin. Success: all three objects' centres are inside the bin's interior (between its walls, below its rim) at the same time. The goal must hold for 30 consecutive control steps (1.02 s); the episode then ends in success.
A conveyor belt runs across the table in front of the arms, along y, between two rails; it carries three objects (canned food, bagged food, boxed drink) towards the left (+y) at about 9 cm/s. A bin stands right behind the belt (on its far side). The objects keep moving with the belt until they are lifted off it. The robot is a service; the episode it runs is graded.

## Difficulty
First-pass rating: hard. The scene does not wait: the belt carries the objects past the arms, so each grasp has to be timed on a moving object, and the objects are of different shapes and sizes. The action is joint-level (two 6-joint arms and two grippers; no motion primitives), and the goal has to hold, so passing through it does not count.

## Reference solution
The privileged twin's reference (the commanded actions of one of upstream's validation demonstrations of this task): `solution/oracle.npy`, 274 rows, planned into the episode at the control steps where they ran in the privileged replay (`submit(..., at=step)`, sent ahead of the clock; `solution/oracle_plan.py`), so the service executes exactly those rows at S = 1.

## Verification
The live episode's verdict, judged by the sim sidecar (the shared realtime layer and this benchmark's adapter) on the episode it ran; the collect hook waits for `final.json`; the verifier (the shared `v2_1/grade.py`) transcribes it. `nop`: the episode times out, reward 0.

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
| Instance | the scene of one of upstream's validation demonstrations (its assembled scene XML, initial qpos and randomization record); the model-side state its randomizer sets outside the XML written into the scene; state hash `73fd8e08bd4000ee`, checked on every load |
| Actions | 14 joint-position targets per control step (0.034 s, 17 physics substeps of 2 ms) |
| Success | the upstream evaluator `conveyor_pick` held 30 control steps |

### Provenance
The frozen instance (`instance.npz`) and the reference solution (`solution/oracle.npy`) were made at generation time from
an upstream validation demonstration; see `tasks/abc-sim/README.md`.

### Change Log
- 2026-10-21: first version.
