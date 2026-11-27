# Embodied Olympics - Match

## Overview

Robot matches against an opponent, with a referee that scores them by the sport's rules: table tennis, badminton,
humanoid soccer, wheeled soccer, foosball, a turn-based fencing bout, duels against a learned player, two low-level
matches where the agent writes the stroke skill, and table tennis between two Unitree G1 humanoids. 14 matches in up
to three modes: 41 task directories, `tasks/embodied-olympics-match/embodied-olympics-match-<match>-i<NN>-privileged`,
`-standard` and `-realtime` (the fencing bout has no realtime mode).

| | |
|---|---|
| upstream | [Embodied Olympics](https://github.com/CHIGUI0/roboolympics) (a private repository): its own exporter writes each match as a task, with the simulator service, referee, scripted opponents, observation, reviews and grader inside |
| simulator | MuJoCo, CPU physics (the GPU tiers add one NVIDIA GPU to the agent's container only) |
| robots | Franka Panda on a moving base (table tennis, badminton), Booster T1 humanoids (humanoid soccer), RoboCup Small Size League robots (wheeled soccer), foosball rods, Unitree G1 humanoids (fencing, G1 table tennis) |
| score | the match's result: passed only if the match ends by its rules with the agent's side as the winner |
| image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0`; humanoid soccer `...-soccer-0.1.0`; G1 table tennis `...-tabletennisg1-0.1.0` and the seat image `...-tabletennisg1-seat-0.1.1` (all public) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/embodied-olympics-match -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the full simulator in development (any state, the whole match reset) | unlimited | its program, playing one fresh formal match in the verifier |
| standard | its seat in the live match; the world in lockstep (it advances only while the agent's seat lets it) | 0 | the live match |
| realtime | the same seat on a clock that does not stop, at 1/S of real speed | 0 | the live match |

## Upstream and license

- Upstream: Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), private), MIT License.
  Each task names its export (the source task, the sport's frozen revision, the upstream commit) in its README, and
  `ci_checks/benchmarks/embodied-olympics-match/exported.toml` lists the files changed here after the export.
- Simulator: MuJoCo (Apache License 2.0). No non-commercial terms apply.

## Changes from upstream

Every change below is listed under `patched` in `exported.toml`, and switches on through the sim service's compose
environment where it changes the core's behaviour, so the core keeps its upstream behaviour without it.

- **Graded by the live match.** The core's fresh-process validity replay (`python -m core.episode`,
  `replay_check.json`) does not run (`RO_VERDICT_REPLAY=0`). The verdict is the live match as the trusted core
  recorded it: `scores`, `match_winner`, `reason`, `errors` and the seats' metering in `final.json` (`graded_by`
  live, `replays` 0). The patch touches `core/service.py` (`finalize` skips the replay; `write_final` drops the replay
  term) and `core/grading.py` = `tests/grade.py`. `core/` is hashed into each match's `source_sha`, so each task has a
  `source_sha` of its own; archived episodes still replay, because the replay echoes the header's own `source_sha`.
- **Agent-caused simulator errors.** In a match graded live and finalized that runs on a game clock (the realtime
  tasks, and the standard tasks in lockstep, whose core tags its step errors the same way), an error of the control
  step itself (`reason` technical_error, every `errors[]` entry `where` "world_step") after the agent's first applied
  act is the agent's 0 (`valid_trial` 1, `agent_sim_error` 1). Before it, in the turn-based bout, with an unfinalized
  record, or for any other technical error (bookkeeping, rendering, metering, a crashed sim service) it stays an
  infrastructure failure. The privileged formal match applies the same rule to the program. G1 table tennis has its
  own judge (below).
- **Standard tasks: the world in lockstep** (`environment/sim/core/lockstep.py`, on top of the unchanged
  `core/realtime.py`). The world advances one control step at a time, and only while every seat that plays lets it:
  an open `wait`, up to its target step; an accepted act, up to the step at which it takes effect. Between the
  player's calls it stands still, and nothing advances while an act is being prepared, so thinking and computation
  cost no game time. A built-in seat (the duels) is held to the same rule; the scripted opponents live inside the
  world's step and play exactly as in real time. `/spec` timing has `clock = "lockstep"`; `final.json` has
  `clock = "lockstep"`; `tests/fexam_reward.py` writes `realtime = 0`. A program that never waits leaves the match
  standing; it is lost when the session ends (`abandoned`). The reviews keep their limit of real time, and the start
  window is unchanged.
- **Standard endpoints.** Every match except the low-level ones and G1 table tennis also serves the standard endpoints
  (`/spec`, `/status`, `/observe`, `/submit`, plus `/start`, `/ready` and, in team formats, `/say` and `/team`) next
  to the core's own seat API (`embodied_first_exam/benchmarks/embodied-olympics-match/eai_std/`, below).
- **Duels against a built-in seat.** Seat B is a built-in learned player inside the service (`RO_BUILTIN_SEATS`). The
  core forfeits an abandoned match only for a single side, so unpatched an agent that left a duel after the start
  would end it `collected` (no valid trial). Both duels patch `core/service.py` `abandon_single` to leave built-in
  seats out: the side that leaves loses `abandoned`, a valid 0. `tests/test.sh` writes success 0 with
  `grader_error = infra_error = 1` if `fexam_reward.py` (which adds the duel's `A_won`) fails.
- **Low-level matches: the skill served from the agent's own container.** Upstream runs the player's skill in a
  trusted per-seat container that mounts the agent's output, adds capabilities and has no network of its own. Here no
  agent code runs in the sim: the agent starts its own skill server in its own container
  (`game skill serve /app/output/skill`: `skillhost.py serve --tcp 127.0.0.1:8765 --live`, shipped under
  `/opt/skillkit`). The sim and the agent's container share the egress sidecar's network namespace, so the sim calls
  the server over the loopback (`RCB_SKILL_INLOOP_A = "tcp:127.0.0.1:8765"`). The in-sim upload host and its jail are
  removed, and `RCB_SKILL_REMOTE_ONLY=1` refuses any skill source but `tcp:`. Details under Interface.
- **G1 table tennis** is ported from Embodied Olympics core 0.5, which has no exporter: the release branch's generated
  task `tabletennis_g1-match-wallclock-program-engineer-standard` (revision `g1tt-10+core-0.5`, commit `45ed806a5`).
  Its sim service, core and judge (`tests/eo_judge`) are kept. The patches: the seat is `unmetered`
  (`core/metering/think_clock.py`; Harbor records the usage); the match is graded live; the verdict ends the session
  (`environment/match_end.sh` asks `GET /over`, a patch of `core/http.py`, and stops the agent's container a few
  seconds after the result is final); the session's end decides (`RO_COLLECT_ENDS_MATCH=1`: an end before the start
  is `no_show`, an end during play `abandoned`, both valid losses). Its privileged tasks are this repository's
  (`tools/g1tt_priv`, `tests/formal.py`).
- **Videos.** The sim service draws the spectator video after the verdict (`core.spectator`); the grade never depends
  on it. Badminton declares no spectator camera, so its tasks run `environment/sim/spectator/sport_video.py` from the
  collect hook instead (the players' two cameras, at 10 frames per game second; `video.json` says whether that replay
  ended in the live record's state). `spectator/` is outside the match's `source_sha`. Fencing draws one still per
  phrase.

## Interface

**Two routes to the seat.** A standard or realtime match offers its seat through the `game` command (HTTP at
`localhost:8000/A/...`) and, in the same task, through the `efe-robot` MCP server, one tool per `game` command. The
low-level matches keep their own interface only: the player delivers skill code the platform runs in the loop, which a
tool call cannot deliver.

**The standard endpoints** (the match extension, docs/protocol/standard_mode.md Part 5). Every answer's `meta`
carries `score`, `review_due` and `match_over`. In the real-time matches `/submit` answers at once and its rows become a
plan from control step `at`; a new chunk replaces it from `at` on, passed rows are dropped, and the last command holds.
As in every `eai-standard/3.0` task, `/observe` answers at once and never lets time pass (`seconds > 0` is a 400);
time passes only through `/submit`, and a rows-free hold chunk (`"interpolate": "hold"`, `seconds`) lets it pass
without a new action (lockstep: that many seconds of game time, as `game wait`; fencing: a wait of up to that many real
seconds for your turn). `/spec` `timing.deviations` declares what the match cannot follow: the clock starts at the
start barrier and freezes for the reviews, a high-level action takes effect at the first boundary after the platform
has planned it, the core runs missed steps back to back, and `/observe` returns the sport's own frames of now, not a
video. In the standard tasks `/submit` runs its rows in lockstep; in fencing one row, the turn's phrase. `/finish`,
`/reset` and `/kinematics` are not offered (404): the match's rules end the episode, never the agent. There is one
match and no reset. `apply_eai_std.py` copies the extension into each task's `environment/sim/eai_std/`; the sim runs
`python3 -m eai_std.serve`, which builds and runs the match unchanged and only wraps the core's HTTP server, on the
same port as the seat API (one request budget for both). The agent's image gets the shared client from the pinned
`standard-files` image (`/opt/tools/rcb_client.py`).

**The match's rules** (each instruction states them, and `game spec` gives the numbers):
- The start: the agent sends `game start` within the start window, or loses `no_show`.
- The review: after every point (rally, goal, phrase) the world stands still and each side reviews; a side that has
  not sent `ready` within the review limit (300 s; 600 s in humanoid soccer; `timing.review_timeout_s`) loses the match
  (`ready_timeout`). The world does not go on by itself, and the agent's time runs on during the review.
- The session's end: a match the agent's session leaves before the final score is lost (`abandoned`).
- Turn-based fencing: each player has a chess clock of real time that runs on its own turns, reviews included; a player
  whose clock runs out loses (`clock`).
- G1 table tennis follows core 0.5's own rules: the start window is a 1800 s preparation counted from the seat's first
  `game` request (`no_show`); a missed review never loses, and the match resumes at the review's 300 s deadline; a
  player may resign (`resigned`).

**Slowdown.** Each real-time match runs at the sport's official slowdown S (the sim service's `RO_SLOWDOWN`): table
tennis 10, badminton 20, humanoid soccer 5 (10 at the joint level), wheeled soccer 10, foosball 20, G1 table tennis 1
(real speed). Turn-based fencing has none.

**The low-level matches.** The agent implements the robot's stroke skill (table tennis `hit`; badminton `act`, the
racket head's state at contact and an optional base position) from the joint interface and the toolkit, and serves it
from its own container. Every stroke of the match is played by that skill, and its compute counts in match time. The
server reloads the skill whenever its files change; the new version plays from the next call. Each answer carries the
version (sha256); `inloop_A.jsonl` logs every call and version change, and every version that played is an episode row
`skill_load`. The skill's `step()` is one synchronous call at each due control step (`RCB_SKILL_INLOOP_TIMING=sync`):
the world waits for its answer at most `step_wait_s` = min(the step time limit, one control period), 0.1 s for table
tennis at S = 10 and 0.2 s for badminton at S = 20 (`game spec`), and applies it at that step. `hit` / `act` calls
run off the world's lock, each waited for at most its time limit + 1 s. No answer in time, an error, a malformed answer
or a dead server means no command at that step: the player's own error, never infrastructure, and the match stays
valid. The sim sends the skill the seat's whitelisted observation without images and the public spec, and reads back
one command, which the low level's own parser checks. The sim's `RemoteHost` reads only typed fields of the server's
answers.

**Privileged.** The full simulator in development (the generic layer `tools/fullsim` with a per-task adapter; for G1
table tennis `/opt/fullsim`, with the formal runner itself): any state, level or seed, and the whole match reset. The
deliverable is a closed-loop Python program that plays seat A of a fresh, unmodified match in the verifier, seeing the
full state instead of camera images. A duel's built-in learned seat plays inside the formal match as in development.
The soccer joint pair keeps its resource tiers: the GPU task's agent container holds a GPU and the training stack; the
verifier is CPU-only in both.

## Grading

- **Standard and realtime.** `tests/grade.py` (= `core/grading.py`) reads the live record. `valid_trial` = finalized,
  complete (the match ended by `match_over`, `ready_timeout`, `clock`, `abandoned` or `no_show`, with a winner) and no
  technical error. Success = a valid match the agent's seat A won (duels: `tests/fexam_reward.py`'s `valid_trial` and
  `A_won`). A crash of the sim service ends the trial as an infrastructure failure: there is no crash recovery, since
  the match is one continuous live record and a resumed match would not be the recorded one.
- **Privileged.** `tests/grade.py` runs the formal match (`tools.fullsim.formal.evaluate`) after the agent's session
  in a verifier container without network. The program runs as `nobody` in its own process, on the original clock (the
  turn-based bout: the original turns and chess clock). Success = a valid match (reason `match_over`, the core's
  fresh-process replay agreeing, no program error) won by the program's side. A program error, a call over its limit,
  not one command response per observation, the wall cutoff, or a process left behind scores 0. A failure of the
  verifier or of the trusted service, or a replay that disagrees, is an infrastructure failure. G1 table tennis uses
  `tests/formal.py`: the program plays seat A with the sport's in-process runner (`core/local.py`); the world waits for
  it at every control step, 0.5 s a call and 1800 s of program time in all, and the core's fresh-process replay must
  agree with the match. In its standard and realtime tasks the judge (`tests/eo_judge`) voids the trial as infrastructure on any failure of the world,
  the match service or the platform, a simulator error included, and on a match the wall-clock cap stops.
- **Joint-level soccer (standard and realtime).** A win is replayed and checked for the released Booster walking
  policy (`environment/sim/audit/policy_fingerprint.py`, `tests/fexam_reward.py`). For a sample of each robot's joint
  rows (every 20th control step, at most 600 per robot) the policy's closest possible row is fitted; if for either
  robot more than half of the rows fit within 0.02 rad RMS, the win scores 0. A win whose check gives no result, or
  whose replay does not reproduce the match, is an infrastructure failure. The privileged formal match runs no such
  check.
- **Low-level skill verifier.** The delivered skill runs as `nobody` in its own process. The evaluator is the
  subreaper of the skill's tree and kills every process of `nobody` below it when the skill is closed
  (`skilleval/sandbox.py` `end_sandbox_processes`; a survivor makes the grade a `grader_error`); the skill runs with
  `RLIMIT_NPROC` 128. `tests/test.sh` makes `/logs/verifier` 755 and writes the report to a root-only directory;
  `tests/grade.py` kills any process of `nobody` left, removes every entry of `/logs/verifier` root did not write, and
  writes the reward files fresh (`O_EXCL`, `O_NOFOLLOW`).
- **G1 table tennis, realtime.** A breach of the match's integrity limits (world lag p99 0.5 s, late step p99 0.05 s,
  render misses 1 %) voids the match as infrastructure (R-INTEGRITY), never as the player's loss. Such a match needs
  fast cores: the world 12 vCPU, the platform's G1 8, the seat 8, the practice service 8, the practice player 1
  (`scripts/task_resources.toml`).

## Tasks

| match | sport | opponent | instance | slowdown | agent's time |
|---|---|---|---|---|---|
| `tabletennis-match-i04` | table tennis, Franka Panda on a rail base, one game to 5 | scripted, level 4 | seed 34 | 10 | 7200 s |
| `tabletennis-duelrl-i01` | table tennis duel | built-in learned seat | seed 8 | 10 | 7200 s |
| `tabletennis-matchlow-i01` | table tennis, the agent's `hit` skill | scripted, level 1 | seed 22 | 10 | 7200 s |
| `tabletennisg1-matchcpu-i01`, `tabletennisg1-matchgpu-i01` | table tennis, two Unitree G1s, one game to 5 | the platform's G1, level 4 | seed 4 | 1 | 7200 s |
| `badminton-match-i04` | singles badminton on a 0.4-scale court, one game to 11, Franka Panda on a gantry base | scripted, level 5 | seed 1034 | 20 | 14400 s |
| `badminton-duelrl-i01` | badminton duel | built-in learned seat | seed 1001 | 20 | 14400 s |
| `badminton-matchlow-i01` | badminton, the agent's `act` skill | scripted, level 2 | seed 8 | 20 | 14400 s |
| `soccer-match-i00` | humanoid soccer 2 v 2, two Booster T1s from their head cameras, 2 x 5 min | scripted team, level 2 | seed 7 | 5 | 7200 s |
| `soccer-jointcpu-i01`, `soccer-jointgpu-i01` | humanoid soccer 2 v 2 at the joint level (12 leg joint targets per T1 every 20 ms) | joint-level RL team, level 5 | seed 101 | 10 | 14400 s |
| `soccerssl-match-i01` | wheeled soccer 5 v 5 (RoboCup Small Size League), four overhead cameras | RL team, level 4 | seed 7 | 10 | 14400 s |
| `foosball-match-i01` | foosball, first to 5 goals or 240 s of play | scripted rods, level 3 | seed 7 | 20 | 14400 s |
| `fencing-bout-i02` | robot epee, one FIE direct-elimination bout, two Unitree G1s, turn-based | scripted fencer, level 2 | seed 35 | none (chess clock 3600 s) | 7200 s |

The two tasks of each resource-tier pair are the same match and differ only in the agent's resources: the CPU tier
has no GPU; the GPU tier adds one NVIDIA GPU to the agent's container (with mjlab and rsl_rl for the joint-level
soccer, the release's training kit for G1 table tennis). Each task's README states the opponent, the rules that end
its match, and every way the match is lost.

Seeds: each match's `instance_seed` is the instance's development seed. `[metadata.seeds]` adds two more per match:
the first two public seeds of the instance's format and level cell in `sport.toml` `[official]`, else the sport's
development seeds 1 and 2 (`scripts/task_seed.py materialize` sets `RO_SEED`, `match_instance.json` and the texts).
Embodied Olympics produces its official results on hidden six-digit seeds.

## Others

- Network: the allowlist (model APIs and package registries), as in every other benchmark.
- Metering: the seat is "unmetered" for Embodied Olympics (no proxy, no credential in the sim); the usage gateway
  records the agent's usage.
- Images are built from Embodied Olympics' own tree, not from this repository. CPU only, except the agent's containers
  of the GPU tiers. The G1 seat image `-tabletennisg1-seat-0.1.1` is the release's seat image plus the GPU kit's
  missing `bodies/sources.py` in `/opt/robot/lib/bodies`, without which the kit's GPU module fails to import.
