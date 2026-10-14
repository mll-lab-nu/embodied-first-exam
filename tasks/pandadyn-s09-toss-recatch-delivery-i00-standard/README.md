# pandadyn-s09-toss-recatch-delivery-i00-standard

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `pandadyn-s09-toss-recatch-delivery-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s09_toss_recatch_delivery` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-pandadyn:0.1.0` |

## Task
Standard-mode twin of `pandadyn-s09-toss-recatch-delivery-i00-privileged` (same frozen instance): the agent gets only the `eai-standard/2.2` client
(docs/STANDARD_MODE.md); the simulator runs in the `sim` sidecar (`environment/docker-compose.yaml`, GPU on the sidecar
for SAPIEN's renderer), which owns the scene and records the episode as a (T, 8) trajectory of the environment's own
joint-target actions. The collect hook (`environment/sim/finalize.sh`) ends the episode, lets the service exit, replays the
trajectory in two fresh processes and writes `final.json`; the verifier runs in a separate sandbox (`tests/Dockerfile`) over
those artifacts. Compare against the privileged task to measure the cost of losing resets, privileged state and
self-replay. A ball is thrown high into the air when the episode starts and comes down near the robot. Catch it in the shallow cup the Panda holds, which has one open side. Bring the cup to a launch region and toss the ball straight up out of the cup with a real throw: it must leave the cup floor while rising. Move the cup sideways and catch the ball again. Finally, release it into an open box that slides back and forth along a rail, where it must settle while the box is moving.

## Difficulty
That of `pandadyn-s09-toss-recatch-delivery-i00-privileged` (its README), without resets, object poses or the success signal: the moving objects are seen only
through two static cameras (RGB, depth) and the robot's own proprioception, the simulated clock advances only with the
agent's calls (so the agent can look between control steps, at a cost in calls), and a missed catch stays missed.

## Reference solution
`solution/oracle_replay.py` streams the privileged oracle's rows (`solution/oracle_qpos.npy`, one row per control step,
`hold`) as one-second `joint_position` chunks through the client; after a service crash it waits for the resumed episode
and continues from the control step the service reports.

## Verification
`success` = live success ∧ replay success ∧ deterministic (two fresh-process replays agree), computed in the sidecar's
collect hook; `tests/grade.py` reads `final.json` with no network and writes the reward fields (with `infra_error` and the
crash-recovery fields), plus `/logs/verifier/replay.mp4`. The task's success check is evaluated after every physics step;
the episode ends at the first control step where the task has succeeded or failed, live and in the replays. Oracle: the
live episode and both replays end in the privileged oracle's final state (hash `3f8dccf95457c7ff`). `nop`: no control step
is executed; the episode ends at the collect hook with no phase complete, reward 0.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).
- Measured: 50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB; the sim service is one scene, the collect hook replays in fresh processes one after the other; CPU: one core per scene + one for the agent
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 14 GiB memory. Limits measured: memory: the agent container holds only Python and the client (0.03 GiB in the oracle trials): max(1.5 x peak, peak + 4, 8) -> 8 GiB; whole trial: + the sim service's 6 GiB (one scene, 1.3 GiB, with its frames and the replays' scenes); GPU 0.25 GiB in the sim service (50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | one episode, no reset, no step budget: it ends at the first control step where the task has succeeded or failed (the task's horizon, 25 s of simulated time, is a failure), when the agent's time is up, or on a simulator error; the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8: per arm 7 joint targets + the aperture, executed at 100 Hz with the agent's `dt`, a multiple of 0.01 s); `observe` frames or a watch window; `/kinematics` (FK / IK, stateless); binary RCB1 responses |
| Cameras | `overview` and `closeup` (static), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs eai-pandadyn (`images/pandadyn/`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | resume class `exact`: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode (docs/STANDARD_MODE.md §13) |
| Generator | `scripts/pandadyn/mk_tasks.py` (`scripts/pandadyn/descr/`, `frozen/`, `template/standard/`, `shared/`, `scripts/eai_standard/`); docs/benchmarks/pandadyn.md |
