# pandadyn-s04-impact-release-relay-i00-standard-realtime

| | |
|---|---|
| Benchmark | Panda Dynamic Scenes |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `pandadyn-s04-impact-release-relay-i00-privileged` |
| Simulator / robot | `maniskill` / `franka-panda` |
| Family / instance | `s04_impact_release_relay` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 2 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 3 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:pandadyn-0.1.0` |

## Task
Standard-realtime twin of `pandadyn-s04-impact-release-relay-i00-privileged` (same frozen instance and success check as it and as `pandadyn-s04-impact-release-relay-i00-standard`): the agent gets only
the realtime client (`eai-standard/2.3`, docs/protocol/standard_mode.md Part 3); the simulator runs in the `sim` sidecar on a clock
that does not stop, at slowdown **S = 2** (one 10 ms control step every 20 ms of wall-clock time), with
3 resets (only the last episode is graded). A small block (the cue) slides along a raised deck toward the robot side at the start. Strike it with the paddle so that it hits a spring-held gate latch and swings the gate open, releasing a ball (the payload) that waits behind the gate on an inclined chute; within 1 s of the cue's impact the ball must be past the gate and rolling down the chute. Intercept the ball with the paddle after it has left the chute, send it through a narrow passage between two walls, then touch it again and bring it to rest in a target zone on the table beyond the passage.

## Difficulty
That of `pandadyn-s04-impact-release-relay-i00-standard`, and the scene no longer waits between calls: once an episode's clock starts, the moving objects and
the robot's servos run whatever the agent does, so the agent has to plan or stream the targets from a program of its own
(the task's horizon is 25 s of robot time, about 50 s of wall-clock time at S = 2), and
learn the scene from 4 real attempts.

## Reference solution
`solution/oracle_plan.py` plans the privileged oracle's rows (`solution/oracle_qpos.npy`, one row per control step,
`hold`) into the episode from control step 0 through the realtime client, one chunk of at most 10 s at a time, each at
its own step (`at`), so every row runs at the control step it was recorded for; it uses no privileged information at run
time. Checked at S = 2 (board 0112, under the grading of then): live success, fresh-process replay success, the
same final state.

## Verification
The sim service (`environment/sim/rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with
`environment/sim/server.py`, this benchmark's adapter on `rcb_pandadyn.Session`) judges the episode live and records
every control step it ran (`trajectory_live.f64`); after the agent's time the collect hook stops the agent's programs and
signals the service, which writes the live episode's verdict into `final.json` (`graded_by` = `live`, `replays` = 0;
nothing is replayed to grade it; since 2026-10-17, board 0151) and then renders the video from the graded episode's rows;
`tests/grade.py` (separate sandbox, no network) passes iff the last episode ended in the task's success (every phase in
order, no failure: the episode's end, so there is no settle window to add). The frozen start is checked when the first
episode begins (the state hash against the instance's `initial_sha`; a mismatch is `instance_mismatch`, an infrastructure
failure). The clock's record (`stalls`, `max_lag_s`, `late_steps`, ...) is copied into `reward.json`
and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 4 GB | 3 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).
- Measured: 50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB; the sim service is one scene, the graded episode is replayed in one fresh process while the live scene is still up (two scenes at once), then filmed by the live scene (board 0112); CPU: one core per scene + one for the agent
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 14 GiB memory. Limits measured: memory: the agent container holds only Python and the client (0.03 GiB in the oracle trials): max(1.5 x peak, peak + 4, 8) -> 8 GiB; whole trial: + the sim service's 6 GiB (one scene, 1.3 GiB, with its frames and the video pass's scene); GPU 0.25 GiB in the sim service (50 oracle trials, 25 per mode (rcb_monitor samples every 5 s, eai-pandadyn:0.1.0, RTX 4090, 2026-10-13): privileged trial peak 0.79 GiB (anon + shmem), GPU 0.05 GiB; standard sim service peak 0.94 GiB, GPU 0.35 GiB, agent container 0.03 GiB; CPU p90 about 1 core per container; one filmed scene (render_video, S12 and D07): RSS 1.2-1.3 GiB, GPU 0.25 GiB); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Episode | it ends at the first control step where the task has succeeded or failed (the task's horizon, 25 s of robot time, is a failure), when the agent's time is up, or on a simulator error; 3 resets (`POST /reset`: the scene rebuilt from the frozen instance, paused) |
| Action space | `submit` chunks of `joint_position` (8: per arm 7 joint targets + the aperture, one row per 10 ms control step or `dt` apart) planned from step `at`; `observe` now or a watch window; binary RCB1 responses |
| Cameras | `overview` and `closeup` (static), 640×480 RGB, z-depth on request, rendered by SAPIEN on the sidecar's GPU |
| Images | the `sim` sidecar runs eai-pandadyn (`images/pandadyn/`); the agent container and the verifier run the shared client image with its pip pins (`scripts/eai_standard/client.env`) |
| Crash recovery | the shared realtime layer's: a checkpoint every second of robot time, `restart: on-failure:6`, the service resumes the same episode, paused |
| Generator | `scripts/pandadyn/mk_tasks.py` (`REALTIME`, `template/realtime/`, `scripts/humanoidbench/shared/{realtime,standard}/`); docs/benchmarks/pandadyn.md |

### Change Log
- 2026-10-14 (owner, board 0112): added. The family's scene is dynamic (PROTOCOL §2.14), so it gets a standard-realtime
  twin with S = 2 and 10 resets.
- 2026-10-17: reset budget 10 -> 3. Every reset restores the same frozen start, so the budget is the number of
  times an agent can rerun and tune a plan on a deterministic scene; with 10, realtime trials succeeded far more often
  than standard ones (no reset), mostly on a late episode (docs/benchmarks/pandadyn.md, "Reset budget"). Instance,
  scene, success check and S are unchanged; results under 10 resets are ranked separately.
- 2026-10-17 (owner, board 0150/0151): graded by the live episode; no grading replay (until then: one fresh-process
  replay, success = live ∧ replay ∧ deterministic); the frozen start is checked when the first episode begins; the video
  is rendered from the graded episode's rows after the verdict. Instance, scene, success check, S and resets are unchanged.
