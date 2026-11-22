# pandadyn-s06-cube-flip-route-recover-i00-standard

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `pandadyn-s06-cube-flip-route-recover-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s06_cube_flip_route_recover` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.2.0` |

## Task
Standard-mode twin of `pandadyn-s06-cube-flip-route-recover-i00-privileged` (same frozen instance and success check): the agent gets only the `eai-standard/2.1`
client (docs/protocol/standard_mode.md Part 1, with the optional reset capability); the simulator runs in the `sim` sidecar
(`environment/docker-compose.yaml`, GPU on the sidecar for SAPIEN's renderer), which owns the scene, judges the episode
live and records every control step it ran. Between the agent's calls the world is frozen; 3 resets, only the last
episode graded. The sidecar's adapter (`environment/sim/server.py`) is the benchmark's standard-realtime twins', code for code,
on the same shared service layer, so where a family has that twin the two modes differ only in the clock. Compare against the
privileged task to measure the cost of losing privileged state, free resets and self-replay. A cube rests on a raised launch surface. With a short push from the pusher blade, tip it over so that the face that initially faces the robot (-x) ends up on top, the cube completing the tip by its own momentum after the blade has let go, and let it settle. Then push the flipped cube onto an inclined chute, let it slide down by itself, meet it with the blade on its downhill side near the chute's lower end, and bring it to rest in the pocket at the bottom of the chute with the same face still on top.

## Difficulty
That of `pandadyn-s06-cube-flip-route-recover-i00-privileged` (its README), without object poses or the success signal and with 3 resets: the moving objects
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
in the privileged oracle's final state (hash `ad3ddd2643881562`). `nop`: no control step is executed; the episode ends at
the collect hook with no phase complete, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | 3 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## Details
| | |
|---|---|
| Episode | it ends at the first control step where the task has succeeded or failed (the task's horizon, 25 s of simulated time, is a failure), when the agent's time is up, or on a simulator error; 3 resets (`POST /reset`: the scene rebuilt from the frozen instance); no step budget, the wall clock is the only budget |
| Action space | `submit` chunks of `joint_position` (8: per arm 7 joint targets + the aperture, one row per 10 ms control step or `dt` apart, a chunk at most 10 s); `observe` frames or a watch window (at most 30 s); binary RCB1 responses |
| Cameras | `overview` and `closeup` (static), 640×480 RGB, z-depth on request |
| Images | the `sim` sidecar runs efe:pandadyn (`images/pandadyn/`); the agent container and the verifier run the shared client image with its pip pins (`embodied_first_exam/standard/client.env`) |
| Crash recovery | the shared service layer's: every control step journaled, a checkpoint with the state hash after every call; `restart: on-failure:6`, the service resumes the same episode |
| Benchmark notes | tasks/pandadyn/README.md |
