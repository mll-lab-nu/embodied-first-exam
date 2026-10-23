# pandadyn-s11-cylinder-rescue-route-deliver-i00-standard

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `pandadyn-s11-cylinder-rescue-route-deliver-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s11_cylinder_rescue_route_deliver` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
Standard-mode twin of `pandadyn-s11-cylinder-rescue-route-deliver-i00-privileged` (same frozen instance and success check): the agent gets only the `eai-standard/2.1`
client (docs/protocol/standard_mode.md Part 1, with the optional reset capability); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar for SAPIEN's renderer), which owns the scene, judges the episode
live and records every control step it ran. Between the agent's calls the world is frozen; 3 resets, only the last
episode graded. The sidecar's adapter (`environment/sim/server.py`) is the benchmark's standard-realtime twins', code for code,
on the same shared service layer, so where a family has that twin the two modes differ only in the clock. Compare against the
privileged task to measure the cost of losing privileged state, free resets and self-replay. A short round-ended cylinder is rolling along a raised lane when the episode starts and will run off its end. Intercept it in the open-sided tray the Panda holds. Bring it to rest in the tray with its long axis along the world's y axis. Put it into a gently sloping guide channel near the channel's entry, and let it travel out past the far end without the tray touching it at that moment. Catch it again in the tray at the exit, aligned and settled. Finally, deliver it lying along y into a pocket that slides back and forth on a rail, where it must rest while the pocket is moving.

## Difficulty
That of `pandadyn-s11-cylinder-rescue-route-deliver-i00-privileged` (its README), without object poses or the success signal and with 3 resets: the moving objects
are seen only through two static cameras (RGB, depth) and the robot's own proprioception; the simulated clock advances
only with the agent's calls (so the agent can look between control steps, at a cost in calls), and a missed catch costs
an episode.

## Reference solution
`solution/oracle_replay.py` spends the reset budget on short scouting episodes (the first second of the rows each, then
`reset`), then streams the privileged oracle's rows (`solution/oracle_qpos.npy`, one row per control step, `hold`) as
one-second `joint_position` chunks through the client in the last episode; after a service crash it waits for the
resumed episode and continues from the control step the service reports. It uses no privileged information at run time.

## Verification
The sim service (`environment/sim/rcb_service.py`, the shared eai-standard/2.1 layer, with `environment/sim/server.py`,
this benchmark's adapter on `rcb_pandadyn.Session`) judges the episode live and records every control step it ran
(`trajectory_live.f64`); after the agent's time the collect hook stops the agent's programs and signals the service, which
writes the last episode's verdict into `final.json` (`graded_by` = `live`, `replays` = 0; nothing is replayed to grade it)
and then renders the video from the graded episode's rows; `tests/grade.py` (separate sandbox, no network) passes iff the
last episode ended in the task's success (every phase in order, no failure: the episode's end, so there is no settle
window to add). The frozen start is checked when the first episode begins and after every reset (the state hash against
the instance's `initial_sha`; a mismatch is `instance_mismatch`, an infrastructure failure). Oracle: the last episode ends
in the privileged oracle's final state (hash `0a467788c6abaca5`). `nop`: no control step is executed; the episode ends at
the collect hook with no phase complete, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).
- Measured: 50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, efe:pandadyn-0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB; the sim service is one scene, rebuilt on every reset and once after the verdict to film the graded episode in the same process (until 2026-10-17 a second scene in the collect hook, before it two fresh-process replays); CPU: one core per scene + one for the agent
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 14 GiB memory. Limits measured: memory: the agent container holds only Python and the client (0.03 GiB in the oracle trials): max(1.5 x peak, peak + 4, 8) -> 8 GiB; whole trial: + the sim service's 6 GiB (one scene, 1.3 GiB, with its frames and the video pass's scene); GPU 0.25 GiB in the sim service (50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, efe:pandadyn-0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | it ends at the first control step where the task has succeeded or failed (the task's horizon, 25 s of simulated time, is a failure), when the agent's time is up, or on a simulator error; 3 resets (`POST /reset`: the scene rebuilt from the frozen instance); no step budget, the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8: per arm 7 joint targets + the aperture, one row per 10 ms control step or `dt` apart, a chunk at most 10 s); `observe` frames or a watch window (at most 30 s); binary RCB1 responses |
| Cameras | `overview` and `closeup` (static), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs efe:pandadyn (`images/pandadyn/`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | the shared service layer's: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode |
| Benchmark notes | tasks/pandadyn/README.md |

### Change Log
- 2026-10-17 (owner): standard mode graded by the live episode; no grading replay (until then: two
  fresh-process replays, success = live ∧ replay ∧ deterministic); the frozen start is checked when the service builds
  the scene; the video by one filming pass after the verdict; the collect hooks now stop the agent's programs first
  (`kill -9 -1` in its container). Instance, scene, success check and the agent's side are unchanged.
- 2026-10-17 (owner): aligned with the benchmark's standard-realtime twins: 3 resets (until then
  none), and their adapter on the shared standard service layer (`eai-standard/2.1`, until then 2.2 with an adapter of its own), so
  the two modes share the action, the control granularity (rows `dt` apart, a multiple of 0.01 s, up to 10 s per chunk;
  watches up to 30 s; up to 30 frames per second) and the observations, and differ only in the clock. Gone with the 2.2
  layer: `/kinematics` (FK / IK), per-frame camera poses and the depth modes, which the realtime twins never had. Instance,
  scene, success check and cutoff are unchanged; results from before are a different configuration and are not ranked
  with these.
- 2026-10-23 (owner): pandadyn 0.2.0, base image `efe:pandadyn-0.2.0`. Unused configuration parameters (`radius`,
  `restitution`) are gone; scene, physics and checks are unchanged. Frozen instance: seed 0, `initial_sha`
  eec08812e42872ec; reference rows: 1782 control steps (the same start and reference rows as before). Results from
  before are under the earlier digest and are not ranked with these.
