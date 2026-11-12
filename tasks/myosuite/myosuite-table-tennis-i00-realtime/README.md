# myosuite-table-tennis-i00-realtime

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `myosuite-table-tennis-i00-privileged` |
| Simulator / robot | `myosuite` / `myoarm-torso` |
| Family / instance | `table_tennis` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `none` — a successful episode of the privileged twin (GPT-6 Luna xhigh, trial `myosuite-table-tennis-i00-privil__SMNgbHk`, 82 rows) planned from step 0 in one `submit(..., at=0)` at S = 1 succeeds live and in the fresh replay, with no stall (2026-10-14); the standard twin's evidence holds for the same instance and rule; human review in PR #201 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 10 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `myoChallengeTableTennisP1-v0` (MyoArm with torso, 273 muscles) on the same frozen instance as `myosuite-table-tennis-i00-privileged`: Return the served ball: hit it with the paddle so that it lands on the opponent's half of the table (MyoChallenge 2025 TableTennis P1's own success test on the ball's contact history: after the serve's bounce on your half, the paddle touches it once, then it touches the opponent's half, with no second paddle touch and no further bounce on your half). Failure (the episode ends): any other outcome of the rally, the ball falling below 0.3 m, or 3 s of simulated time.
You stand at a table-tennis table holding a paddle in the right hand; a ball is served toward you from the far side. Realtime mode (eai-standard/2.3, slowdown S = 1): once an episode's clock starts the body and the ball move whatever the agent does; it drives the body through the realtime client from a program of its own, with only its own proprioception and the scene's cameras, and 10 resets (only the last episode is graded).

## Difficulty
Same instance and success rule as the standard twin (first-pass rating: hard, harder here). The scene is dynamic (the ball is served with an initial velocity): the serve reaches you and the rally is decided within about 1.2 s of robot time after the clock starts (an episode that does nothing ends after 121 control steps), so nothing can be steered call by call; the agent has to plan or stream the muscle commands from a program, and learn the body and the serve from 11 real attempts.

## Reference solution
None in the repository. Solvability evidence: a successful episode of the privileged twin (82 rows, GPT-6 Luna xhigh) planned from step 0 through this service at S = 1 succeeded live and in the fresh replay, with no stall (2026-10-14).

## Verification
The sim service (`environment/sim/rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with `environment/sim/server.py`, MyoSuite's adapter) judges the episode live and records every control step it ran (`trajectory_live.f64`), after checking at the episode's start that the scene is the frozen instance (its recorded state hash; else `instance_mismatch`, an infrastructure failure); after the agent's time the collect hook stops the agent's programs and signals the service, which writes the live episode's verdict to `final.json` (`graded_by` = `live`; nothing is replayed to grade it) and then renders `replay.mp4` from the trajectory, which decides nothing; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded. The clock's record (`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the episode never starts (its clock starts at the first submit), reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 20 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Upstream | MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): measured RTF 2.1-2.7 (2026-10-14, an RTX 4090 workstation (32 cores, load 30-60), the service capped at 4 CPUs: 2.08 with the realtime service's clock flat out (RCB_SLOWDOWN = 0.01, 11 episodes, 13.3 s of robot time), 2.6-2.7 for the bare physics; S = ceil(1.5 / 2.08) = 1. At S = 1 a controller at the control rate with a camera image every 0.25 s ran 11 episodes with no stall (largest lag 0.23 s), and an EGL frame takes 5 ms (an OSMesa one 1.3 s)) |
| Service | the realtime layer of HumanoidBench, BiGym 2.0 and RoboOlympics (`rcb_realtime.py`, `rcb_service.py`, unchanged) with `server.py`, which implements `rcb_service.Sim` on `rcb_myosuite.Session` (the standard twin's scene, action and success rule); cameras `topview`, `default`, `close_up`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640 x 480, EGL on the GPU) |
| Resources | 4 CPUs and a GPU for rendering (the physics is on the CPU) |
| Reset budget | 10 (`RCB_RESET_BUDGET`, compose default; PROTOCOL §2): `POST /reset` starts a new episode from the frozen instance, paused; only the last episode is graded, a success ends the trial; results under another budget or slowdown are reported separately |

### Provenance
The frozen instance (`environment/sim/instance.npz`) and its scene facts were made at generation time; the realtime
service layer is the shared one (`embodied_first_exam/standard/realtime/`); see `tasks/myosuite/README.md`, "Realtime".
