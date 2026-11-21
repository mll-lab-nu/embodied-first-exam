# behavior-collecting-aluminum-cans-i00-standard

| | |
|---|---|
| Benchmark | BEHAVIOR-1K |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `behavior-collecting-aluminum-cans-i00-privileged` |
| Simulator / robot | `behavior` / `r1pro` |
| Family / instance | `collecting_aluminum_cans` / seed 301 |
| Oracle | `none` — No reference solution: BEHAVIOR-1K ships no expert or planner that replays on this frozen instance. Solvable: model trial behavior-collecting-aluminum-can__VRvxwLv (behavior-lunaxh-t8-0927, the privileged twin behavior-collecting-aluminum-cans-i00-privileged on the same frozen instance and BDDL goal) graded success=1, deterministic=1 by the separate verifier on a pre-v1.0 version of this task (dev branch 20a382a8; grader verdict and frozen instance unchanged since); not re-run on this version (static validation only). Human review per family (protocol §4). |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:behavior-0.1.2` |

## Task
Standard-mode twin of `behavior-collecting-aluminum-cans-i00-privileged` on the same frozen instance (2026 BEHAVIOR Challenge public_test instance 301): Collect the six soda cans in the bedroom, three lying on the bed and three on the floor, into the bucket that stands on the bedroom floor.

## Difficulty
Same scene, frozen instance and success rule as `behavior-collecting-aluminum-cans-i00-privileged` (see its Difficulty). In standard mode the agent has no reset, no privileged state and no planning primitives: it sees the robot's cameras (RGB, depth on request) and its proprioception only, acts through the client, and gets one episode.

## Reference solution
None (`oracle = "none"`): no reference solution was written. Evidence that the task is solvable: the privileged twin's model trial `behavior-collecting-aluminum-can__VRvxwLv` on the same frozen instance and BDDL goal (`task.toml` `oracle_evidence`).

## Verification
`success` = the live episode's success, judged by the sim sidecar (graded live, no replay: 2026-10-17): the success
rule (the BDDL goal held 1 s, released and at rest) at every control step; when the agent's episode is still running at
its end, the sidecar holds the robot still for up to 5 s on the live simulator after the agent's container is stopped
and a goal that settles there counts (`settled_success`). The frozen start is checked when the sidecar builds the scene,
before the agent is served. The crash-recovery fields (`sim_startups`, `resumes`, `resume_state_mismatch`) are
reported; the video (`/logs/verifier/live.mp4`) is recorded during the episode (a video-only render, `replay.mp4`, only
when it is missing) and never decides anything. `infra_error` = 1 (no verdict on the agent) when `final.json` is
missing, unreadable or not finalized, the service never ended the episode, it gave up after crashes not all inside the
agent's calls, or the frozen start did not rebuild (`instance_mismatch`).

No oracle: the family is reviewed by a maintainer (PROTOCOL §4) in the pull request that adds it, on a positive example and a `nop` run per mode.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 12 | 32 GiB | 4096 | 16 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## Details
| | |
|---|---|
| Protocol | `eai-standard/2.2`: RGB-D + proprioception through the client; no reset, no object poses, no success predicate |
| Action space | `submit` chunks of `joint_position` (25, streamed at the 30 Hz control rate with the agent's `dt`; base entries are per-step targets) or of `ee_pose` (16, both end effectors, cuRobo IK per row); `observe` frames or a watch window; binary RCB1 responses |
| Crash recovery | `restart: on-failure:6`; the service journals every control step (`journal.f64`) and resumes the same episode after a crash (resume class `approx`, docs/protocol/standard_mode.md §13.1); startup watchdog `RCB_STARTUP_TIMEOUT_S` = 1800 s |
| Dataset | the licensed BEHAVIOR dataset, mounted read-only into the sidecar from `$RCB_BEHAVIOR_DATA` (a precondition) |
| Budget | the agent's time is the `Agent time budget` row (the number is this task's `[agent] timeout_sec`; tasks/behavior-1k/README.md) |
| Collect hook time | 23400 s: the episode end (up to 2 h through a resume, with the 5 s settle window) + a video-only render after the verdict, only when the live video is missing (up to 4 h) + 30 min |

### Sidecar and grading
The agent gets only the `eai-standard/2.2` client (docs/protocol/standard_mode.md); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`: GPU on the sidecar, the licensed dataset mounted read-only at `/data`, the service's own
record in `/out`), which owns the scene, judges the episode and records it as a (T, 25) trajectory and a video. The
collect hook (`environment/sim/finalize.sh`) ends the episode (the settle window on the live simulator when it was still
running), lets the service exit and writes `final.json` from the live result; nothing replays the episode. The
verifier runs in a separate sandbox (`tests/Dockerfile`) over those artifacts.
