# dexjoco-bimanual-photograph-i00-privileged

| | |
|---|---|
| Benchmark | DexJoCo |
| Mode | privileged |
| Twin | `dexjoco-bimanual-photograph-i00-standard` |
| Simulator / robot | `dexjoco` / `franka-allegro-bimanual` |
| Family / instance | `bimanual_photograph` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexjoco-0.1.2` |

## Task
DexJoCo `bimanual_photograph` (two Franka Panda arms, each with a 16-DoF Allegro hand): Hold the camera with the left hand in front of the logo and press its shutter with the right hand. Success, at one control step: the camera's view point is inside the target region (0.16 m radius, +-0.10 m height, 0.40 m in front of the logo along -x, i.e. about 0.3 m above the table), the camera's viewing axis is within 10 degrees of world +x, and the shutter button is touched by something other than the camera.
Privileged mode: the agent works in the simulator's container with live object poses, unlimited resets and thin motion
primitives, and hands in one trajectory replayed open-loop from the frozen instance.

## Difficulty
First-pass rating: hard. Dexterous manipulation with two 16-DoF hands on two arms (46 action values per control step);
the primitives only move tcp and hand-joint targets, so grasping, pressing and every other skill is the agent's. The
reference (the human teleoperator's demonstration) takes 260 control steps (5.2 s at 50 Hz).

## Reference solution
`solution/oracle_trajectory.npz` = the human demonstration's own actions, rounded to float32 (the standard client's
precision; the rounded rows still succeed) and replayed from the frozen instance until the episode ends in success
(260 rows). The demonstration is public (DexJoCo-Datasets-Raw on Hugging Face), so agent egress is
limited to the model APIs.

## Verification
Open-loop replay of `/app/output/trajectory.npz` from `tests/instance.npz`, once in a fresh process in the verifier's own
sandbox (no network); pass iff the episode ends in success (`tests/grade.py`); plus
`/logs/verifier/replay.mp4`, rendered after the verdict is written. A rebuilt instance that does not match its recorded
hash (the image no longer rebuilds the scene) replays nothing and gives no verdict: `instance_mismatch`, `grader_error`
and `infra_error` = 1, not the agent's 0.
A file that is not a readable trajectory (not an npz, no `task` / `actions`, a wrong shape, NaN) or has more than
50,000 rows scores 0 as `bad_trajectory`: the cap keeps a replay of the slowest family well inside the verifier's
3600 s. A verifier that runs fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it) replays
nothing and gives no verdict: `too_few_cpus`, `grader_error` and `infra_error` = 1, not the agent's 0.
Oracle: success after 260 control steps.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `photograph_demo_10_2026-03-16_14-31-13_305518` (DexJoCo-Datasets-Raw), restored with DexJoCo's own state restorer; instance sha `b8b1dbe8dba6c733` |
| Resources | 4 CPUs, 8 GB, no GPU; `OPENBLAS_NUM_THREADS=4` in the agent's container and the verifier's (the simulation's result depends on the thread count below 4: tasks/dexjoco/README.md). The 4 CPUs must be visible to the container (its cpuset / affinity; a `cpus:` quota does not matter): OpenBLAS runs no more threads than that |

### Tooling notes
DexJoCo's reset samples object poses from the global RNG and its state restorer edits the MuJoCo model (table height,
fixed bodies), so `instance.npz` stores the full physics state (`mjSTATE_INTEGRATION`), the mocap targets, the controls,
every numeric model array a task can change, and the env's Python-side task state. Its per-step camera rendering,
real-time sleep, episode cap and hanoi's wall-clock auto-reset are disabled in the tooling (`rcb_dexjoco.py`).

### Provenance
Generated from the frozen instance (`environment/instance.npz`), restored from DexJoCo's demonstration of the task.
