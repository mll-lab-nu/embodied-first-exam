# dexjoco-bimanual-photograph-i00-standard

| | |
|---|---|
| Benchmark | DexJoCo |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexjoco-bimanual-photograph-i00-privileged` |
| Simulator / robot | `dexjoco` / `franka-allegro-bimanual` |
| Family / instance | `bimanual_photograph` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2` |

## Task
DexJoCo `bimanual_photograph` (two Franka Panda arms, each with a 16-DoF Allegro hand) on the same frozen instance as `dexjoco-bimanual-photograph-i00-privileged`: Hold the camera with the left hand in front of the logo and press its shutter with the right hand. Success, at one control step: the camera's view point is inside the target region (0.16 m radius, +-0.10 m height, 0.40 m in front of the logo along -x, i.e. about 0.3 m above the table), the camera's viewing axis is within 10 degrees of world +x, and the shutter button is touched by something other than the camera.
Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with the robot's own
sensors, calibrated cameras (RGB, optional depth) and the robot's kinematics.

## Difficulty
Same instance and success check as `dexjoco-bimanual-photograph-i00-privileged`. In standard mode the agent loses resets, the
simulator and the object poses: it sees camera images and proprioception, acts in chunks of tcp-target + hand-joint rows
(or joint targets), and gets one episode, so it has to close the loop on what the cameras show and recover from its own
mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle_trajectory.npz`, 260 rows, float32-exact)
through the client as `ee_pose` chunks; it uses no privileged information at run time. The service's recorded
trajectory is then exactly the privileged reference, and the episode ends with success after 260 control steps.

## Verification
The verdict is the live episode's (`graded_by = "live"`, `replays = 0`): the sim service judges the episode it runs with
DexJoCo's own success check and records every executed control step. The collect hook
(`environment/sim/finalize.sh`) ends the service, writes that verdict into `final.json` (nothing is replayed to grade
it), then renders `replay.mp4` from the recorded trajectory in one video-only pass (`environment/sim/video.py`), which
never changes the verdict. `tests/grade.py` (separate sandbox, no network) passes iff the live episode ended in success.
The service checks the frozen instance when the episode begins: a scene that does not rebuild to the instance's recorded
state hash gets no episode (`instance_mismatch`, `grader_error` and `infra_error` = 1). A `final.json` that is missing,
unreadable or without a verdict (the hook did not finish), a give-up after crashes between the agent's calls, and a sim
sidecar that runs fewer than 4 OpenBLAS threads (fewer than 4 CPUs visible to it: the service starts no episode,
`too_few_cpus`, `grader_error` and `infra_error` = 1) are infrastructure failures (`infra_error = 1`), not the agent's 0.
Oracle: success after 260 control steps.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 4 | 4 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: sim 1.9 GB, privileged container 2.1 GB, verifier 2.1 GB, mem_guard (docker memory per container, ws-1, 10-02..10); CPU-only; CPUs: 4, visible to each container that runs the simulator (cpuset / affinity, not a quota): OpenBLAS runs no more threads than that and DexJoCo's result differs below 4 (docs/benchmarks/dexjoco.md, Threads); with fewer there is no verdict (too_few_cpus, infra_error)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 14 GiB memory. Limits measured: memory: no samples of the agent's container; floor 8 GiB (at most the 8 GiB cap); whole trial: + the sim service's 6 GiB (docker peak 1.9 GiB, 2 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | DexJoCo @ 8d23b0f (brave-eai/dexjoco, MIT) on MuJoCo 3.4.0; CPU physics, OSMesa rendering, no GPU |
| Instance | the initial state of the human demonstration `photograph_demo_10_2026-03-16_14-31-13_305518` (DexJoCo-Datasets-Raw); instance sha `b8b1dbe8dba6c733` |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`scripts/eai_standard/`); action types `ee_pose` and `joint_position`; cameras `front`, `back`, `left`, `right`, `top0`, `handcam_rgb_right`, `handcam_rgb_left`, `cam_pos_z` (640 x 480); `/kinematics` for the arm links, the hand mount and the tcp; crash recovery class `exact` |
| Resources | 4 CPUs, 8 GB, no GPU; `OPENBLAS_NUM_THREADS=4` in the sim sidecar (the service, a resume and the video pass: the simulation's result depends on the thread count below 4, docs/benchmarks/dexjoco.md). The 4 CPUs must be visible to the sidecar (its cpuset / affinity; a `cpus:` quota does not matter): OpenBLAS runs no more threads than that. The collect hook replays nothing; its one video pass takes about 9 CPU-minutes per trial (median; at most 4500 s) |

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
- 2026-10-10 (review round 3, board 0067): **what the agent observes changed.** The camera `cam_pos_z` rides on an
  object of the scene (here: it is the lens of the camera the hands have to pick up). The service published its
  mount and its live pose as it does for the robot's own cameras (`spec["cameras"][cam]["mount"]`,
  `meta["cameras"]`, the per-frame `extrinsic_cv`), and the texts called it static: that pose is the object's
  pose, which standard mode must not give (PROTOCOL §4.5). It now gives images and depth only: no mount,
  `extrinsic_cv` / `cam2world_gl` null in `meta["cameras"]`, NaN per frame. Standard-mode results of this task
  from before this date could read the object's pose and are reported separately.
- 2026-10-14 (review of board 0105, B-M3): `environment/sim/instance.npz` and `environment/sim/rcb_dexjoco.py`. The
  frozen instance's `meta` entry no longer names the demonstration the scene was restored from (`source`, `demo`;
  the reference solution is that demonstration's actions), and the tooling refuses to save an instance that does.
  The sidecar's files are out of the agent's reach, so nothing reached the agent from this copy; it changed with
  the privileged twin's, from the one committed instance. Every array of the scene is the same (instance sha
  `b8b1dbe8dba6c733`): the scene, the pass rule and the grader are unchanged, so the task keeps its name and earlier
  results stand.
- 2026-10-17 (owner, boards 0150 and 0151): **the verdict is the live episode's.** `environment/sim/finalize.sh`,
  `environment/sim/server.py`, the new `environment/sim/video.py`, `tests/grade.py`, `task.toml`. Success is DexJoCo's
  own check on the episode the service ran (`graded_by = "live"`, `replays = 0`); the collect hook no longer replays
  the trajectory in two fresh processes (success was live ∧ both replays ∧ the same final state), and renders
  `replay.mp4` in one video-only pass after the verdict. The frozen instance is checked when the episode begins (a
  scene that does not rebuild to its recorded hash: no episode, `instance_mismatch`, infrastructure); before, the
  replays checked it. The episode ends at the first success, so no replay ever judged a state the live check had not.
  The scene, the frozen instance, the pass rule and what the agent sees are unchanged, so the task keeps its name;
  `reward.json` no longer has `replay_success`, `deterministic` and `live_matches_replay`. A collect hook on `main`
  (`kill -9 -1`) stops whatever the agent left running before the service ends the episode.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`,
  `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and
  `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service
  keeps that moment; before, they counted from the service's own start of the episode (when its scene was ready).
  Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s
  over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent
  still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit`
  tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen
  instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
