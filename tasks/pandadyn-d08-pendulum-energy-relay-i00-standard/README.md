# pandadyn-d08-pendulum-energy-relay-i00-standard

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `pandadyn-d08-pendulum-energy-relay-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda-bimanual` |
| Family / instance | `d08_pendulum_energy_relay` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-pandadyn:0.1.0` |

## Task
Standard-mode twin of `pandadyn-d08-pendulum-energy-relay-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar
for SAPIEN's renderer), which owns the scene and records the episode as a (T, 16) trajectory of the environment's own
joint-target actions. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the service exit, writes the
live episode's verdict into `final.json` and renders the video; the verifier runs in a separate sandbox (`tests/Dockerfile`)
over those artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and
self-replay. A passive pendulum (a rod with a ball-shaped bob) hangs between the two arms, each of which holds a flat paddle. The left arm must actively push the pendulum so that it swings out toward the right arm. The right arm must meet it and brake it, then actively drive it back so that it swings out toward the left arm, no longer touching it. The left arm must then touch it again, and the pendulum must end up hanging almost straight down and almost still, and stay that way for one second.

## Difficulty
That of `pandadyn-d08-pendulum-energy-relay-i00-privileged` (its README), without resets, object poses or the success signal: the moving objects are seen only
through two static cameras (RGB, depth) and the robot's own proprioception, the simulated clock advances only with the
agent's calls (so the agent can look between control steps, at a cost in calls), and a missed catch stays missed.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's rows (`solution/oracle_qpos.npy`, one row per control step,
`hold`) as one-second `joint_position` chunks through the client; after a service crash it waits for the resumed episode
and continues from the control step the service reports.

## Verification
The verdict is the live episode's (`graded_by` = `live`, `replays` = 0; since 2026-10-17, board 0151): `success` = the
task's own check as the episode the service ran ended (every phase in order, no failure), recorded by the service in
`episode.json` and written into `final.json` by the sidecar's collect hook; nothing is replayed to grade it. The task's
success check is evaluated after every physics step and the episode ends at the first control step where the task has
succeeded or failed, so there is no settle window to add. The service checks the frozen start when it builds the scene
(the state hash against the instance's `initial_sha`; a mismatch is `instance_mismatch`, an infrastructure failure, before
the agent is served). `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error`
and the crash-recovery fields), plus `/logs/verifier/replay.mp4`: after the verdict the hook films the trajectory once in
a fresh process (`video_matches_live`: it ended in the live state; neither decides anything). Oracle: the live episode ends
in the privileged oracle's final state (hash `e904b59c2a0b6551`). `nop`: no control step is executed; the episode ends at the
collect hook with no phase complete, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).
- Measured: 50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB; the sim service is one scene; after the verdict the collect hook builds one more to film the video (until 2026-10-17: two fresh-process replays, one after the other); CPU: one core per scene + one for the agent
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 14 GiB memory. Limits measured: memory: the agent container holds only Python and the client (0.03 GiB in the oracle trials): max(1.5 x peak, peak + 4, 8) -> 8 GiB; whole trial: + the sim service's 6 GiB (one scene, 1.3 GiB, with its frames and the video pass's scene); GPU 0.25 GiB in the sim service (50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where the task has succeeded or failed (the task's horizon, 25 s of simulated time, is a failure), when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (16: per arm 7 joint targets + the aperture, executed at 100 Hz with the agent's `dt`, a multiple of 0.01 s); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Cameras | `overview` and `closeup` (static), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs eai-pandadyn (`images/pandadyn/`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE.md §13) |
| Generator | `scripts/pandadyn/mk_tasks.py` (`scripts/pandadyn/descr/`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/pandadyn.md |

### Change Log
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay (until then: two
  fresh-process replays, success = live ∧ replay ∧ deterministic); the frozen start is checked when the service builds
  the scene; the video by one filming pass after the verdict; the collect hooks now stop the agent's programs first
  (`kill -9 -1` in its container). Instance, scene, success check and the agent's side are unchanged.
