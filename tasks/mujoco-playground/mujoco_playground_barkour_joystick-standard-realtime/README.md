# mujoco_playground_barkour_joystick-standard-realtime

| | |
|---|---|
| Benchmark | MuJoCo Playground |
| Mode | standard-realtime (`eai-standard/2.3`) |
| Twin | `mujoco_playground_barkour_joystick-privileged` |
| Simulator / robot | `mujoco` / `google-barkour-vb` |
| Family / instance | `mujoco_playground/BarkourJoystick` / seed 2 |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (PROTOCOL §5) |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §4b) |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.3` |

## Task
MuJoCo Playground `BarkourJoystick` (Google Barkour vB) on the same frozen instance as `mujoco_playground_barkour_joystick-privileged`: Make Google's Barkour quadruped follow the joystick command schedule for the whole 10 s episode, through random pushes, without falling over.
For 10 s the robot gets a joystick command schedule (2 segments: planar velocity and yaw rate in its own frame) and must track it without falling over. Its torso is pushed 12 times. Standard-realtime mode (eai-standard/2.3, slowdown S = 1): once an episode's clock starts the
robot runs at 100 Hz whatever the agent does; it drives the robot through the realtime client from a program
of its own, with 10 resets (only the last episode is graded), the robot's own sensors and the cameras that
follow it.

## Difficulty
Same instance and success check as `mujoco_playground_barkour_joystick-standard`. The scene is dynamic (`scripts/task_dynamics.toml`: scripted pushes (kicks) apply an external force to the torso at moments the agent is not told),
and here time does not stop: the robot falls within a second without active balance and the pushes come at moments
the agent is not told, so nothing can be steered call by call. The agent has to write a feedback controller that runs
at the control rate in its own container, and learn the robot from 11 real attempts.

## Reference solution
`solution/oracle_plan.py` plans the privileged reference's rows (`solution/oracle.npy`, 1000 rows) into the episode
from its first control step (`submit(..., at=0)`); it uses no privileged information at run time. On the clock the rows
run at the same control steps as in the privileged replay, and the episode ends after the 1000 steps of the schedule, with success.

## Verification
The sim service (`environment/sim/rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with
`environment/sim/server.py`, this benchmark's adapter) judges the episode live and records every control step it ran
(`trajectory_live.f64`); after the agent's time the collect hook stops the agent's programs and signals the service,
which writes the live episode's verdict into `final.json` (`graded_by = "live"`, `replays = 0`: the task's check on the
episode it ran; nothing is replayed to grade it), then renders `replay.mp4` from the trajectory in one pass; the service
refuses an episode whose start does not hash to the instance's `state_sha` (`instance_mismatch`, infrastructure).
`tests/grade.py` (separate sandbox, no network) passes iff the live episode passed the check. The
clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. Oracle: success, worst segment errors 0.033 m/s and 0.028 rad/s. `nop`: the
episode never starts (its clock starts at the first submit), reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 3 GB | 2 GB |
| GPU memory | 1 GB | 1 GB |

- GPU: required, any NVIDIA GPU; recommended: any NVIDIA GPU with EGL (RTX 4090 / L4).
- Measured: as the standard twin; the GPU only renders the cameras over EGL (board 0112, 2026-10-14): GPU 1.0-1.3 GB, vram_profile (batch_eval_live per-trial GPU peaks, 10-03..10); memory: privileged container p90 2.6 GB, sim 0.7 GB, mem_guard (docker memory per container, 4090-ws1, 10-02..10); CPU p90 1.9 cores, live sampler (docker stats + cgroup anon + nvidia-smi every 30 s, 13 AWS hosts + 4090-ws1, 10-10)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 20 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 4 GiB GPU memory, 13 GiB memory. Limits measured: memory: agent container docker peak 2.5 GiB over 4 samples (mem_guard (docker memory incl. page cache, top-4 containers every 10 min, 4090-ws1, 10-02..10)) -> max(1.5 x peak, peak + 4, 8), at most the 8 GiB cap; whole trial: + the sim service's 5 GiB (docker peak 0.7 GiB, 3 samples); processes 512 and disk 20 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | MuJoCo Playground @ 4057c14 (Apache-2.0): `menagerie/google_barkour_vb/scene_mjx.xml`; MuJoCo Menagerie @ 1b86ece (`google_barkour_vb`); MuJoCo 3.3.7 on the CPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): measured RTF 31.6 (2026-10-14, board 0112, 4090-ws1 at load 44, the service capped at 4 CPUs: the reference's 1000 rows planned from step 0 with the clock flat out, RCB_SLOWDOWN = 0.01), far above 3, so S = 1. At S = 1 the reference succeeds live and in the fresh replay with no stall, also streamed one row per call with a camera image every 0.25 s (7.7 ms each over EGL) |
| Service | the realtime layer of HumanoidBench, BiGym 2.0 and MyoSuite (`rcb_realtime.py`, `rcb_service.py`, unchanged) with `server.py`, which implements `rcb_service.Sim` on `rcb_quadruped.Session` (the standard twin's scene, schedule, pushes, termination rule and check); cameras `track` (follows the robot) and `realsense/rgb` (on its head) (320 x 240, EGL on the GPU) |
| Resources | 4 CPUs and a GPU for rendering (the physics is on the CPU) |

### Provenance
Generated by `scripts/mujoco-playground/generate.py` (`templates/realtime/`, `shared/realtime/`), as its privileged twin.

### Change Log
- 2026-10-14 (owner, board 0112): added. The family's scene is dynamic (PROTOCOL §2.14), so it gets a standard-realtime
  twin with S = 1 and 10 resets; the cutoff is the standard twin's.
- 2026-10-17 (owner, boards 0150 and 0151): **graded by the live episode, no grading replay** (`environment/sim/server.py`,
  the shared layer `rcb_service.py` / `rcb_realtime.py`, `tests/grade.py`, `task.toml`). Success is the task's check on the
  episode the service ran (`graded_by = "live"`, `replays = 0`); the service no longer replays it in a fresh simulator
  (success was live ∧ that replay ∧ the same final state). The rule is the same: the replay ran the same rows through the
  same check. The frozen start is checked when an episode begins (the instance's `state_sha`; a mismatch gets no
  episode, `instance_mismatch`, infrastructure), the video is one render pass after the verdict, and the collect hook
  waits 300 s for the verdict (was 840 s). The scene, the instance, the pass rule and what the agent sees are unchanged
  (the instruction's grading sentence now says live), so the task keeps its name; `reward.json` no longer has
  `replay_success` and `deterministic`.
