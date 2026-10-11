# RoboOlympics (standard-realtime)

Three real-time sports from [RoboOlympics](https://github.com/CHIGUI0/roboolympics) (by CHIGUI0; MIT): one robot
against the sport's scripted opponent, seen only through cameras. The world runs on its own clock at 1/S of real speed
while the agent thinks, so the agent plays with a program of its own and fixes it during the match. Standard-realtime
mode only, on `eai-standard/2.3` (PROTOCOL §4b), with the per-benchmark exceptions below.

| | |
|---|---|
| upstream | RoboOlympics, branch `upstream-export` at `596d551a` (core 0.2.13; the repository is private): the sports' simulators, referees, scripted opponents, action layers and reference players, copied unchanged into `scripts/roboolympics/shared/` (one change: `renderers/presentation/assets.py` reads the players' meshes from `RO_LOD_DIR`) |
| simulator | MuJoCo 3.3.7 on CPU, OSMesa rendering; bit-exact replay |
| tasks | 3: `tasks/roboolympics-<sport>-<format>-i00-standard-realtime` (no privileged or standard twin) |
| protocol | `eai-standard/2.3`: HumanoidBench's 2.3 layer (`rcb_realtime.py`, `rcb_service.py`, `rcb1.py`, `rcb_client.py`) unchanged, plus the RoboOlympics adapter `scripts/roboolympics/shared/sim/rcb_olympics.py` |
| image | `ghcr.io/mll-lab-nu/eai-olympiad:0.2.0` (`images/olympiad/`; public): the simulator stack and the players' visual meshes |
| generator | `scripts/roboolympics/gen_tasks.py render` / `check` (CI: `ci_checks/check-generated-tasks.sh`) from `tasks.toml`, `sports.toml`, `templates/`, `shared/`, `oracle/` |
| oracle | full: the sport's RoboOlympics reference player (camera images, the proprio columns and `/spec` only) through the agent's own client (`scripts/roboolympics/oracle/oracle_play.py`) |
| agent budget | 7200 s (uniform; a match plus its breaks takes 5-60 min of wall time at S = 10) |

## Tasks
| task | sport, rules | robot, commands | instance |
|---|---|---|---|
| `roboolympics-tabletennis-match-i00-standard-realtime` | table tennis, ITTF Laws (deviations in the instruction): one game to 5 points; the opponent serves recorded real serves (DeepMind), you receive | Franka Panda with a paddle; `stroke` (the blade's state at contact; the service plans the swing), `rest` | seed 101, opponent level 1 of 4 |
| `roboolympics-badminton-match-i00-standard-realtime` | singles badminton, BWF Laws: first to 5 points, rally scoring, the players serve | Franka Panda with a racket on an x-y sliding base; `stroke` (the racket head's state at contact, planned during a 4-step lead), `toss`, `rest` | seed 101, opponent level 1 of 2 |
| `roboolympics-airhockey-match-i00-standard-realtime` | air hockey, USAA rules: one game to 7 goals, 0.35 m goal mouth, a 120 s play cap | KUKA iiwa 14 with a mallet; `mallet` (the mallet's target in your half, a row per control step; Cartesian path and torque control in the sim), `stop` | seed 101, opponent level 1 of 4 |

Every task also has `ready` (end a break early). The agent sees two cameras (table tennis, badminton: 480 x 360; air
hockey: one 320 x 240) and, as proprio columns, its own robot and the referee's information (score, the ball's clock,
what it heard, the serve); never the ball's or the opponent's state, nor the seed.

## How RoboOlympics maps onto eai-standard/2.3
- **Clock.** One control step of the service is one 10 ms control step of the match (`Match.step()`). The match starts
  paused; its clock starts at the agent's first `submit` or `get_obs(seconds > 0)` and then runs one step every
  0.01 × S s of wall time, whatever the agent does, until the match is over (`rcb_realtime.py`, unchanged).
- **Commands.** A `/submit` row is one of the sport's own commands (its RoboOlympics action layer at the task's level).
  It takes effect at the control step it is planned for: there the action layer parses it, plans it from that step's
  state and lowers it to a low-level command, which `Match.apply()` installs before the step runs (RoboOlympics'
  realtime effect boundary). Out-of-range values are clipped (`meta.clipped`); a command the rules refuse at its step
  (a toss when it is not the agent's serve) changes nothing and is counted (`commands_refused`).
- **A plan of several action types.** RoboOlympics is the one benchmark whose plan mixes types (a toss and the stroke
  that follows; `stop`, then a `mallet` target). The realtime layer never combines rows of different types: a command
  that is no target (`stroke`, `toss`, `rest`, `stop`, `ready`) is its row, issued once at its step, and a gap before a
  row's `at` is held steps (no command); only an interpolable target (`mallet`) is interpolated, from the mallet target
  in force, and held through a gap of its own.
- **Breaks between points.** RoboOlympics froze the world after every unit until the agent sent a review. Here the
  clock never stops: after every unit (a point, a rally) the match stands still for **12 s of game time (120 s of wall
  time at S = 10)** while the clock runs on (control steps, wall time, the agent's plan), nothing moves and nothing
  scores; play resumes by itself when the break is over, or at the step of the agent's `ready` row (its review goes in
  `submit`'s `note`, recorded in `calls.jsonl`). A break is part of the game's logic, like a break between points in a
  real match, not a protocol feature: it needs no protocol exception. Commands planned inside a break are dropped. The
  play-time rules (air hockey's 120 s cap, the seven-second rule) count play only, as before.
- **Record and grading.** A sim row is `[command id, ready]`: the id of the low-level command that took effect at that
  step (-1: none) and the agent's `ready`. The commands are in `/data/commands.jsonl`, written before the row that names
  them, so the journal (`trajectory_live.f64`) and that table are the whole record. Finalize replays it in a fresh
  process (`rcb_olympics.py replay`): `success` = live success (a finished match the agent won) ∧ replay success ∧
  deterministic (the replay ends in the live state). `match.json` is the replay's summary (score, breaks, commands);
  `tests/grade.py` grades `final.json` only. A crash resumes the same match from the journal (bit-exact), paused;
  past `RCB_MAX_RESUMES` it is an infrastructure failure (`infra_error = 1`).
- **Timing.** The service renders the images and plans the strokes on its own thread between control steps; a long
  plan (badminton) makes it run late and catch up (`max_lag_s`, `stalls` in `final.json`), never changes what happens
  in the match. `final.json` and `reward.json` also carry `clock_s`, `stalled_s` and `stalled_share` (the wall time the
  clock ran, the time its stalls dropped, their ratio), `held_steps`, `requests_refused` and `request_busy_s`: evidence,
  which decides no verdict. The agent's requests cannot slow the clock (the shared 2.3 layer, since 2026-10-10: bodies
  are read, decoded and checked off the simulator's thread, waiting requests are served once the clock has caught up,
  the cameras are rendered once per control step; `docs/STANDARD_MODE.md`).

## Per-benchmark exceptions (owner, 2026-10-08; PROTOCOL §4b)
| | PROTOCOL §4b | RoboOlympics | why |
|---|---|---|---|
| slowdown S | `RCB_SLOWDOWN` default 1 | default **10**, overridable | RoboOlympics' official slowdown of all three sports: a model call takes seconds and a rally is over in a few, so at S = 1 play would be reflexes, not reasoning. Results state S; S ≠ 1 is reported separately anyway (§4b, §5) |
| privileged twin | `<base>-privileged` shares the instance | none | the sports measure play from camera images against an opponent; there is no trajectory deliverable to hand in. CI exempts `roboolympics-*` explicitly (`ci_checks/check-instance-copies.sh`, `scripts/task_conventions.py` `NO_TWIN`) |

The reset budget is §4b's default, 0: one match is one episode. Everything else is `eai-standard/2.3` as specified.

## Run
```bash
MODES=standard-realtime scripts/run_agent_batch.sh <batch> roboolympics-tabletennis-match-i00 \
  roboolympics-badminton-match-i00 roboolympics-airhockey-match-i00
```
Docker, CPU only. Per trial the sim takes up to 6 CPUs and 8 GB (air hockey 4 CPUs), the agent container 2 CPUs and
4 GB. Run real-time tasks where the host is not overloaded: the service's lag behind its clock is reported
(`max_lag_s`, `stalls`). The agent reaches the sim through Harbor's egress-control namespace (`allowlist`: the model
APIs and the package registries only); with public egress `main` could not reach `localhost:8000`.

## Image
`images/olympiad/`: MuJoCo 3.3.7, numpy, imageio, PyOpenGL, Pillow, OSMesa, and since 0.2.0 the players' visual meshes
at `/opt/roboolympics/lod` (`RO_LOD_DIR`): the 25k level of detail of MuJoCo Menagerie's `franka_emika_panda` and
`kuka_iiwa_14` (Apache-2.0, licences next to them). `images/olympiad/prepare_assets.sh` rebuilds them from Menagerie's
pinned commit with RoboOlympics' `lod.py` (bit-identical) and checks them against `lod.json`; every task's renderer
checks them again (sha256 per file) before drawing. No task code and no solution is in the image.

## Evidence
Harbor 0.23.0, S = 10, CPU only, on a shared 32-core host (load 30-70), image 0.2.0, the tasks as merged (PR #106):

| task | oracle | match (game time) | trial wall | `max_lag_s`, stalls | nop |
|---|---|---|---|---|---|
| table tennis | 1: won 5:2 | 22.4 s, 6 breaks (each ended by `ready`) | 289 s | 0.32, 0 | 0 (the match never starts) |
| badminton | 1: won 7:5 | 229 s, 11 breaks | 2432 s | 0.45, 1 | 0 |
| air hockey | 1: won 3:2 at the 120 s play cap | 120 s, 7 breaks | 1297 s | 0.16, 1 | 0 |

Every replay was deterministic. Badminton's reference player is the weakest of the three: its matches are close
(this loop also won 6:4 locally; an earlier version of the loop, which re-planned its stroke at every step, lost 3:5).

## Changes in place
- **2026-10-10 (board 0067, review finding C1).** Until this date the realtime layer took whatever row the plan held
  as the start of a chunk's interpolation and as the filler of the gap before its `at`, whatever its action type. A
  toss followed by a stroke sent before the toss's step had run (or the stroke first, as the instruction allows) was a
  500 (4 values against 10), and `stop` or `ready` followed by a `mallet` target a few steps ahead put a one-value row
  under the `mallet` type, which broke the simulator at its step. Either way the match ended `reason = "error"` with
  `infra_error = 1`: a legal sequence of commands, booked as an infrastructure failure. A command planned ahead of
  another of its type was also issued again at every step of the gap between them (a stroke restarted five times; a
  `rest` or `stop` fired at once instead of at its step). Fixed in `rcb_realtime.py` (tests:
  `scripts/humanoidbench/tests/test_realtime_service.py` on a stub simulator with these action types;
  `scripts/roboolympics/tests/test_adapter.py` `test_mixed_plan` on the three sports in the image). **A RoboOlympics
  trial recorded before this date that ended `error` / `infra_error = 1` may be this bug, not a simulator fault**:
  `episode.jsonl` shows it (an `error` event whose text is a numpy broadcast error or an IndexError); such trials are
  to be rerun, and a match the agent played around the bug (one command per call, waiting for each to take effect, as
  the oracle does) is unaffected.
- **2026-10-10.** `final.json` is `finalized` the moment the verdict is written, before the replay video is rendered (`video_pending` while it renders); the collect hook waits for the verdict and then, as long as its timeout allows, for the video, so a slow, hung or killed render costs the video and never the verdict. `reward.json` writes `deterministic` and `sim_error` in every branch; a refused
  `/reset` no longer answers a pending `get_obs(seconds=...)` early, and `final.json`'s realtime counters survive a
  crash-resume.
- **2026-10-10 (board 0067, review R2 finding M1).** The shared 2.3 layer no longer lets the agent's requests slow the
  clock: bodies are read, decoded and checked off the simulator's thread (more than 1 MiB of JSON text by a child
  process), waiting requests are served once the clock has caught up, and the cameras are rendered once per control
  step. On a stub simulator at 50 Hz, four threads of refused 21 MB bodies used to leave 3 control steps in 6 s, four
  threads of `/observe` with a 25 ms render 234 of 300; both now keep every step
  (`scripts/humanoidbench/tests/test_realtime_load.py`). `final.json` and `reward.json` add `clock_s`, `stalled_s`,
  `stalled_share`, `held_steps`, `requests_refused` and `request_busy_s`, and `max_lag_s` is the true maximum (it never
  passed 0.5). The match, the commands that take effect and the verdict rule are unchanged. **A trial recorded before
  this date whose `final.json` shows `stalls` > 0 ran on a clock that was slower than S for part of the match** (how
  much is not recorded there: each stall dropped more than 0.5 s); whether such a trial counts is an owner decision.

## Attribution
- RoboOlympics (simulators, referees, opponents, reference players): CHIGUI0 and contributors, MIT.
- Table-tennis serves (`sport/sim/serves_pool.json`): recorded real serves from Google DeepMind's
  competitive robot table tennis data, licensed under CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/);
  the table, ball and contact model follow DeepMind's `competitive_robot_table_tennis` (Apache-2.0).
- Air-hockey table and arm models: AirHockeyChallenge (MIT; `sport/scene/UPSTREAM_LICENSE` and `ORIGIN.md`).
- Robot models: MuJoCo Menagerie's Franka Emika Panda (Apache-2.0) and KUKA LBR iiwa 14 (BSD-3-Clause, from Drake's
  iiwa14 description); the licences ship with the meshes in the image and in `renderers/presentation/`.
