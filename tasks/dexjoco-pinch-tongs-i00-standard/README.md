# dexjoco-pinch-tongs-i00-standard

| | |
|---|---|
| Benchmark | DexJoCo |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexjoco-pinch-tongs-i00-privileged` |
| Simulator / robot | `dexjoco` / `franka-allegro` |
| Family / instance | `pinch_tongs` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2` |

## Task
DexJoCo `pinch_tongs` (a Franka Panda arm with a 16-DoF Allegro hand) on the same frozen instance as `dexjoco-pinch-tongs-i00-privileged`: Pick up the tongs and open and close them three times while holding them up. A pinch counts each time the tongs' hinge goes from open (>= 0.1 rad) to closed (<= -0.07 rad). Success: at least three pinches counted and the tongs at least 0.10 m above the table, held for 30 consecutive control steps.
Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with the robot's own
sensors, calibrated cameras (RGB, optional depth) and the robot's kinematics.

## Difficulty
Same instance and success check as `dexjoco-pinch-tongs-i00-privileged`. In standard mode the agent loses resets, the
simulator and the object poses: it sees camera images and proprioception, acts in chunks of tcp-target + hand-joint rows
(or joint targets), and gets one episode, so it has to close the loop on what the cameras show and recover from its own
mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle_trajectory.npz`, 375 rows, float32-exact)
through the client as `ee_pose` chunks; it uses no privileged information at run time. The service's recorded
trajectory is then exactly the privileged reference, and the episode ends with success after 375 control steps.

## Verification
The sim service judges the episode live and records every executed control step; the collect hook
(`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes
and writes `final.json`, then renders `replay.mp4` in the time it has left; `tests/grade.py` (separate sandbox, no
network) passes iff the live check succeeded, both replays succeed, and they end in the same state. A `final.json` that
is missing, unreadable or without a verdict (the hook did not finish, a replay gave no result) is an infrastructure
failure (`infra_error = 1`), not the agent's 0. So is a sim sidecar that runs fewer than 4 OpenBLAS threads (fewer than
4 CPUs visible to it): the service starts no episode (`too_few_cpus`, `grader_error` and `infra_error` = 1).
Oracle: success after 375 control steps.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim 1.9 GB, privileged container 2.1 GB, verifier 2.1 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only; CPUs: 4, visible to each container that runs the simulator (cpuset / affinity, not a quota): OpenBLAS runs no more threads than that and DexJoCo's result differs below 4 (docs/benchmarks/dexjoco.md, Threads); with fewer there is no verdict (too_few_cpus, infra_error)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 14 GiB memory. Limits measured: memory: no samples of the agent's container; floor 8 GiB (at most the 8 GiB cap); whole trial: + the sim service's 6 GiB (docker peak 1.9 GiB, 2 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `table_tongs_demo_10_2026-03-12_16-30-04_442884` (DexJoCo-Datasets-Raw); instance sha `ad2cfca40d427e20` |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`scripts/eai_standard/`); action types `ee_pose` and `joint_position`; cameras `front`, `back`, `left`, `right`, `top0`, `handcam_rgb` (640 x 480); `/kinematics` for the arm links, the hand mount and the tcp; crash recovery class `exact` |
| Resources | 4 CPUs, 8 GB, no GPU; `OPENBLAS_NUM_THREADS=4` in the sim sidecar (the service, a resume and the collect hook's replays: the simulation's result depends on the thread count below 4, docs/benchmarks/dexjoco.md). The 4 CPUs must be visible to the sidecar (its cpuset / affinity; a `cpus:` quota does not matter): OpenBLAS runs no more threads than that |

### Provenance
Generated by `scripts/dexjoco/generate.py`, as its privileged twin.

### Change Log
- 2026-10-10 (review round 3, board 0067): the sim service (`environment/sim/server.py`), the shared layer under it
  (`rcb_limited.py`) and the client (`environment/rcb_client.py`); the scene, the frozen instance and the pass rule
  are unchanged, so the task keeps its name. One call returns at most 1000 images (cameras x frames, per-frame
  depth counted again; `/spec` `max_frames_per_call`): a larger request is a 400 and nothing runs. Before, a call had
  no bound, and one request within the documented ranges (several cameras for 30 s at 50 fps) could exhaust the
  sidecar's memory: the service was killed, and a trial that then failed was recorded as an infrastructure
  failure (`resource_service_oom`), not as a result. A camera named more than once in `cameras` is rendered and
  returned once. A service that has given up on the episode (too few CPUs, or it could not resume after its
  crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at
  once; before, nothing answered and they waited out their timeout (up to an hour).
