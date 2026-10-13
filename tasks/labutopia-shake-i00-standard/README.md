# labutopia-shake-i00-standard

| | |
|---|---|
| Benchmark | LabUtopia |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `labutopia-shake-i00-privileged` |
| Simulator / robot | `labutopia` / `franka-panda` |
| Family / instance | `shake` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-labutopia:0.1.0` |

## Task
LabUtopia's `shake` (Shake (LabUtopia's level-2 ShakeBeaker is the same task)) on the same frozen instance as `labutopia-shake-i00-privileged`: Pick up the glass beaker, shake it, and hold it still. Nothing is counted while the beaker's centre is less than 5 cm above where it stood. Success the moment the second of these is met: (1) five times, the beaker's centre moves 5 cm or more (horizontally) from where it was when that count began; (2) after the fifth, the centre stays within 1 cm in each horizontal direction over one second (60 control steps in a row).
On the bench in front of the arm: one small glass beaker, about 6.5 cm across and 10 cm tall. Standard mode (eai-standard/2.2): the agent drives the robot through a client in one episode, with only its proprioception and the scene's cameras.

## Difficulty
Same instance and success rule as `labutopia-shake-i00-privileged` (LabUtopia's level 1). A small beaker has to survive five quick moves of 5 cm in the grip and then be held within 1 cm for a second: the grasp has to be firm enough for the accelerations. In standard mode the agent loses resets, the simulator and the state of the objects: it sees camera images (glassware is nearly transparent in them and absent from the depth maps) and the robot's proprioception, acts in joint target chunks, and gets one episode, so it has to find the things it handles in the images and recover from its own mistakes without starting over.

## Reference solution
`solution/oracle_stream.py` streams the privileged reference's rows (`solution/oracle.npz`, 1087 rows, float32) through the client as `joint_position_velocity` chunks; it uses no privileged information at run time. The service's recorded trajectory is then exactly the privileged reference: success after 1087 control steps.

## Verification
The sim service judges the episode live and records every executed control step; the collect hook (`environment/sim/finalize.sh`) ends the service, replays the recorded trajectory in two fresh processes and writes `final.json`; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded, both replays succeed, and they end in the same state. A missing or unfinished `final.json` (the hook never wrote its verdict) and a replay that gave no result are `infra_error = 1`, never the agent's 0. `nop`: the episode times out, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 8 | 8 |
| Memory | 28 GB | 27 GB |
| GPU memory | 8.5 GB | 8.5 GB |

- GPU: required, an RTX-class NVIDIA GPU (ray-tracing cores, for Isaac Sim / Omniverse RTX rendering); recommended: RTX 4090 24GB / L40S 48GB.
- Measured: oracle checks on RTX 4090 (driver 580), lab_001 pick: rendering container peak 17 GB RAM, about 7 GB GPU, 8 CPUs (start-up bursts to 16 cores for about 70 s); author: lab_003 families 21 GB at the peak (8 vCPU host)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 16 GiB GPU memory, 28 GiB memory. Limits measured: GPU: about 7 GiB, oracle on an RTX 4090 (author); no trial data -> max(1.5 x peak, peak + 4), at least 16 for Isaac Sim; memory: no samples of the agent's container; floor 8 GiB (at most the 32 GiB cap); whole trial: + the sim service's 20 GiB (docker peak 12.7 GiB, 1 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | LabUtopia (github.com/Rui-li023/LabUtopia @ 8df7278; code MIT, assets CC BY-NC 4.0) on NVIDIA Isaac Sim 6.1.0 (LabUtopia pins 5.1.0; the image is built locally, images/labutopia/BUILD_ONLY) |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`scripts/eai_standard/`); cameras `camera_1`, `camera_2`, `wrist_cam` (512 x 512); action types `joint_position` (9) and `joint_position_velocity` (18); forward and inverse kinematics of the arm |
| Resources | an RTX-class NVIDIA GPU for the `sim` sidecar (Isaac Sim), 8 CPUs, 32 GB of RAM |

### Provenance
Generated by `scripts/labutopia/generate.py` from `scripts/labutopia/instances/shake.json` (`make_facts.py`),
`scripts/labutopia/oracles/shake.npz` and `scripts/labutopia/families.json`; see `docs/benchmarks/labutopia.md`.

### Change Log
- 2026-10-10: how a trial that could not be graded is recorded, and request checks; the scene, the frozen instance and the pass rule are unchanged, so the task keeps its name. `tests/grade.py`: a missing, unreadable or unfinished `final.json` (the collect hook never wrote its verdict) is `infra_error = 1` (was the agent's 0, or no reward at all); a reward is always written. `environment/sim/finalize.sh`: each verdict replay has a time limit (2400 s; a replay without a result was and is `infra_error`), the video replay gets what is left, `final.json` is written atomically, and the collect hook's `timeout_sec` is 9000 s (was 5400 s). `environment/sim/server.py`: a malformed request field (null or a wrong type for `dt`, `seconds`, `cameras`, `note`) is a 400 before anything is executed (was a 500 that ended the episode). A pass before this change is a pass after it; results recorded before it may hold infrastructure failures counted as the agent's 0.
- 2026-10-10 (review round 2, board 0067): texts and the client only. The renderer's first start is stated as measured (5 to 27 minutes by stage and host: 26-27 minutes for the `lab_003` stage on an 8-vCPU L40S host, where the texts said about 15); `Robot()` waits up to 3600 s for the service (was 600 s, so the instruction said `Robot(timeout=2400)`) and prints its progress once a minute; `cameras="name"` (a string) is one camera, no longer its characters. `pour` only: the instruction says that the last condition counts 84 control steps in all, not in a row (what the rule always did). The service, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-10 (review round 3, board 0067): the shared service layer and the client only (`environment/sim/rcb_limited.py`, `environment/rcb_client.py`). A camera named more than once in `cameras` is rendered and returned once (N copies of one name made the service build N x N images within the frame budget, which could exhaust its memory). A service that has given up on the episode (it could not start it, or could not resume it after its crashes) answers every request with 409 and the reason, and `Robot()` / `wait_ready()` raise `EpisodeOver` at once; before, nothing answered and they waited out their timeout (up to an hour). The adapter, the collect hook, the grader, the scene and the pass rule are unchanged.
- 2026-10-13 (owner, boards 0085 and 0087): the sim service's clock (`environment/sim/rcb_limited.py`, `environment/sim/server.py`, the docstring of `environment/rcb_client.py`). `meta["time_s"]` and `meta["time_left_s"]` count from the agent's first request to the service (any endpoint), and a restarted service keeps that moment; before, they counted from the service's first start in its container (`time_left_s`) and from when its scene was ready (`time_s`). Where the service is ready before the agent's phase begins (the harness is installed in between: a median of 79 s over the recorded standard trials), that clock ran ahead of the agent's and `time_left_s` reached 0 while the agent still had that time. `/spec` says what the clock counts from (`budget.clock`), and the instruction's `## Time limit` tells the agent to plan by `time_left_s`. The service never ended an episode on this clock: the scene, the frozen instance, the pass rule and the grader are unchanged, so the task keeps its name and earlier results stand.
- 2026-10-10 (review round 2, shared framework): the `sim` sidecar's docker memory cap is 32 GiB (was 24 GiB, below the 27 GB this task declares as the verifier phase's minimum: a simulator killed at that cap inside a call would have been counted as the agent's failure). Nothing the agent sees or the grader decides changes (`scripts/task_resources.toml`, `[metadata.resources.caps]`).
