# Embodied Olympics - Match

The matches [Embodied Olympics](https://github.com/CHIGUI0/roboolympics) (CHIGUI0; MIT, private) exports itself with its own
service inside the task, and a privileged twin: table tennis, badminton, humanoid soccer, wheeled soccer and
foosball matches, duels against a learned player, the low-level matches and a turn-based fencing bout; and table
tennis between two Unitree G1 humanoids, ported from Embodied Olympics core 0.5. 41 task
directories: 12 exported (11 realtime, 1 standard; `ci_checks/benchmarks/embodied-olympics-match/exported.toml`), the 11
standard twins of the real-time matches (below), 12 privileged twins, and the G1 table-tennis task in its three modes,
in a CPU and a GPU tier (below). 14 tasks: 14 `-privileged`, 14 `-standard` and 13 `-realtime` dirs; core set 13
(12 default realtime, fencing default standard; the G1 table-tennis task in its CPU tier only).

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/embodied-olympics-match -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

**A benchmark of its own since 2026-10-18** (owner). Until then these tasks were part (2) of Embodied Olympics;
part (1), the 50 single-humanoid sports families, is now [Embodied Olympics - Fun](../embodied-olympics-fun/README.md). Each of the two
benchmarks has its task-name prefix (`embodied-olympics-match-` here, `embodied-olympics-fun-`
there; `scripts/task_conventions.py` `BENCHMARKS`).

## Tasks exported by Embodied Olympics (its own service inside the task; PROTOCOL §3)

Embodied Olympics exports these tasks itself with its own exporter (CHIGUI0/roboolympics, private): its own
generated task, with the simulator service, referee, scripted opponents, observation, the frozen review between points,
the fresh-process replay and the grader unchanged, turned into a plain Harbor 0.23.0 task (contributed in #180, by
CHIGUI0; merged with the maintainers' fixes below). They are listed in `ci_checks/benchmarks/embodied-olympics-match/exported.toml` (with the
Embodied Olympics commit and the sport's frozen revision of each, and the files changed here since the export);
they are refreshed by re-running the exporter on this checkout, then `scripts/task_conventions.py` on them (each keeps its own `[agent] timeout_sec`).

| task | what | instance | oracle (vanilla Harbor 0.23.0) |
|---|---|---|---|
| `embodied-olympics-match-tabletennis-match-i04-realtime` | table tennis vs the scripted opponent at the frozen level 4, Embodied Olympics revision `wallclock-15` (players serve, rail base, real-robot limits; S = 10 since Embodied Olympics PR #138) | level 4, seed 34, S = 10 | partial: the camera-only reference lost 2:5 twice (valid, replay identical); feasibility on this very instance: the truth-state reference won it 5:3 (it wins level 4 in 2 of 40 seeds); a mirror match (level 4's player on the agent's side, same limits, true state) wins 18 of 40, many points decided by the 13-shot rule; GPT-6 Astra (one precheck) lost 0:5; nop 0 |
| `embodied-olympics-match-badminton-match-i04-realtime` | singles badminton on a 0.4-scale court (BWF Laws, one game to 11; revision `badminton-wallclock-12`, PR #81): Franka Panda with a racket on a Festo gantry base; the players serve; at an export-only top tier: opponent level 5 (level 2 with a 0.22 s reaction, level 3's 2 m/s walk back and level 3's kills, 90 % of its attacks; Embodied Olympics PR #181; never an official level) | level 5, seed 1034, S = 20; agent budget **14400 s** (a per-task exception: a game to 11 at S = 20 took the reference alone 78 min; at S = 10 the camera-only reference loses level 1, 0 of 20) | partial: the camera-only reference lost 1:11 (a valid, replayed match); feasibility with the true shuttle state: the reference's strokes placed short to a random front corner win level 5 in 5 of 40 development seeds (this seed 11:8), and a learned shot-selection policy on the reference's strokes (Embodied Olympics PR #187) wins level 5 in 16 of 20 (this seed 11:3); every simple baseline loses; nop 0 |
| `embodied-olympics-match-soccer-match-i00-realtime` | humanoid soccer 2 v 2 (RoboCup Humanoid League rules, revision `soccer-2v2-10`: the T1's real motors): one agent commands both Booster T1 robots of its team (walk velocity, stand, kick) from their head cameras against a scripted team; 2 x 5 min of game time | level 2, seed 7, S = 5 (2 x 5 min = 3000 s of wall time plus the reviews, inside 7200 s) | partial: the camera-only reference lost 1:8 on soccer-2v2-10 (0:2 on soccer-2v2-9; it cannot kick while walking; a model has won level 2, Astra 12:2); nop 0. Image `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0` (public) |
| `embodied-olympics-match-foosball-match-i01-realtime` | foosball, first to 5 goals or 240 s of play against the scripted rods (revision `foosball-program-v2`, Embodied Olympics PR #121: the rod speeds of the KiRo table robot) | level 3 (the hardest level the reference wins; at level 4 it lost 0:5), seed 7, S = 20; agent budget **14400 s** (240 s of play is up to 4800 s of wall time at S = 20, plus the start window and the reviews after each rally) | partial: the camera-only reference won 5:4 in one run and lost 1:5 in another (realtime play varies; it wins level 3 in 21 of 100 seeds in the screening); nop 0 |
| `embodied-olympics-match-tabletennis-duelrl-i01-realtime` | table-tennis duel against a built-in RL opponent: the other robot of the duel world (same robot, limits and execution scatter), driven by a learned policy with a fast-swing planner inside the sim service (Embodied Olympics core 0.2.31 built-in seat; the agent cannot reach that seat over HTTP); success = the agent's seat A wins | seed 8, S = 10, 7200 s | partial: the camera-only reference (seat A) won 5:3 (valid, replay identical); evidence: mirror match 68/120, the truth-state reference beats it 15/160 (level 4: 2/40), the camera reference 3/20; GPT-6 Astra (one precheck) lost 1:5; nop 0 |
| `embodied-olympics-match-badminton-duelrl-i01-realtime` | badminton duel against a built-in RL opponent: the duel world's other robot (the same Panda on a gantry base, the same limits and execution scatter) driven by a learned policy inside the sim service (Embodied Olympics core 0.2.31 built-in seat, not reachable over HTTP); success = the agent's seat A wins | seed 1001, S = 20, 14400 s | partial: the camera-only reference (seat A) lost 1:11 (valid, replay identical); evidence: mirror match 21/40 for seat A, the RL beats level 3 19/20, the truth-state reference beats it 1/20, our camera reference through the live service 0/20; GPT-6 Astra (one precheck) lost by a missed review (`ready_timeout`) at 5:5; nop 0 |
| `embodied-olympics-match-soccerssl-match-i01-realtime` | wheeled soccer 5 v 5 (RoboCup Small Size League rules, revision `soccer_ssl-1`): one agent commands its five omnidirectional robots (move, kick, dribble) from four overhead cameras against an RL team as an export-only match level 4 (a learned policy in the world, like levels 1-3); two halves and, if level, a shoot-out (about 1035 s of game time) | level 4, seed 7, S = 10; agent budget **14400 s** (the task's own `[agent] timeout_sec`: the match alone is 2.9 h of wall time at S = 10, and at S = 5 the four cameras cannot be rendered in time) | partial: the camera-only reference lost 7:10 (a valid, replayed match); evidence: the RL team beats level 3 64-11-25 over 100 seeds, the truth-state reference beats it 10/20, every simple baseline 0/15; GPT-6 Astra (one precheck) lost by a missed review (`ready_timeout`) while 0:1 down; nop 0 |
| `embodied-olympics-match-soccer-jointcpu-i01-realtime`, `embodied-olympics-match-soccer-jointgpu-i01-realtime` | a resource-tier pair (exported by Embodied Olympics' soccer pilot exporter): humanoid soccer 2 v 2 at the joint level (12 leg joint targets per Booster T1 every 20 ms, no walking policy, revision `soccer-2v2-11`) against level 5, our joint-level RL team (a PPO gait at the joint level and an RL strategy layer), any method, a practice service with full copies of the match world; the two tasks are the same match and differ only in the agent's resources (CPU tier: 6 cores, numpy / SciPy / MuJoCo; GPU tier: + one NVIDIA GPU with mjlab + rsl_rl and the 2 v 2 world on the GPU) | level 5, seed 101, S = 10, 2 h start window, 300 s reviews, 14400 s | partial: the joint-level reference lost 0:10 to level 5 v1 in both tasks (valid, replay identical); feasibility: three frozen GPU-tier GPT-6 Astra programs win 30 % of 90 matches against v2 (40 % against v1); a walking-policy audit in the collect hook; nop 0 |
| `embodied-olympics-match-fencing-bout-i02-standard` | robot epee fencing, one FIE direct-elimination bout (15 touches or 9 min of fencing time; Embodied Olympics revision `fencing-7`, a Embodied Olympics preview sport): two Unitree G1s (NVIDIA SONIC on legs, waist and free arm) fence phrase by phrase from on guard, each phrase replayed from a table of all 2916 phrases measured in MuJoCo; the agent chooses each phrase's tactical intention (one of nine) against a scripted fencer that reads its choices; turn-based (`eai-standard-turn/1.0`), a chess clock of 60 min per player | level 2, seed 35 | full: the camera-only reference won 15:13 (32 phrases, replay identical; the world is deterministic, so the oracle's result is the one Embodied Olympics computes in process); nop 0 |
| `embodied-olympics-match-tabletennis-matchlow-i01-realtime` | table tennis at the **low level** (Embodied Olympics' Engineer mode as a match; owner's decision 2026-10-16): the agent implements the robot's `hit` skill itself from the joint interface and the toolkit, serves it from its own container (`game skill serve`; the sim calls it over the shared loopback), and every stroke of the match is played by that skill (the skill in the loop: its compute counts in match time; no execution scatter); success = the agent wins | level 1, seed 22, S = 10, 7200 s | partial: Embodied Olympics' toolkit-only reference skill with the camera-only reference strategy lost 0:5 (valid, replay identical; it lost 0:5 on 8 more seeds: its slow serves bounce twice on its own court); feasibility: the platform's own hit packaged as a skill, with the truth-state strategy, wins level 1 in 7 of 8 seeds of Embodied Olympics' competition test (this seed 5:1; the reference skill 0 of 4); through the live service (core 0.2.32's upload path) with the camera-only strategy it scored 2:5, 1:5, 2:5; GPT-6 Astra (one precheck) lost 2:3 by a missed review (`ready_timeout`, a valid loss; its own skill, then uploaded to the sim (core 0.2.32), won 2 points); nop 0 |
| `embodied-olympics-match-badminton-matchlow-i01-realtime` | badminton at the **low level**, as the table-tennis one: the agent implements the robot's `act` skill (the racket head's state at contact, optional base position) from the joint interface and the toolkit (bm_kinematics, bm_servo), serves it from its own container (`game skill serve`), and every stroke of the match is played by that skill; success = the agent wins | level 2, seed 8, S = 20, 14400 s | partial: our toolkit-only reference act with the camera-only reference strategy lost 1:11 on this instance (vanilla Harbor 0.23.0, the skill served from the oracle's own container: a valid, replayed match, 30 act calls, none failed); feasibility: our evaluator's competition test (the camera-only reference strategy calling a skill, no wall clock) wins level 1 4/4 and level 2 2/4 with our toolkit-only reference act (API test 512/519), and in the screening's skill-in-the-loop match (revision 12, S = 20) Claude Opus won level 1 11:6 with its own act; level 2 because models won level 1; nop 0 |

**Standard twins of the real-time matches (`eai-standard-lockstep/1.0`).** Each `-realtime` match has a
`-standard` twin: the same export (instance, seed, level, opponent, rules, referee, observation, action levels, reviews,
cutoff, live grading, oracle), with the sim service started as `python3 -m core.lockstep` (`environment/sim/core/lockstep.py`,
Embodied First Exam's, on top of the unchanged `core/realtime.py`). Only the clock differs: the world advances one control
step at a time, and only while every seat that plays lets it (an open `wait {dt}`, up to its target step; an accepted act,
up to the step at which it takes effect); between the player's calls it stands still, and nothing advances while any
act is being prepared (the high level's planning, a low-level skill call), so thinking and computation cost no game
time. A built-in seat (the duels) is held to the same rule: the world waits for it too, so it plays its loop (observe,
act, `wait 0.05`) step for step, as the core's in-process play does. The scripted opponents live inside the world's step
and play exactly as in real time. `/spec` timing has `clock = "lockstep"`, `period_s` null; `final.json` has
`clock = "lockstep"`; `tests/fexam_reward.py` writes `realtime = 0`. The episode is a realtime episode, so the replay
video and grading are unchanged. A program that never waits leaves the match standing; it is lost when the session ends
(`abandoned`). The reviews keep their limit of real time, and the start window is unchanged.

**Privileged twins.** Every exported match has a privileged twin `<base>-privileged` on the same frozen instance: the
full simulator in development (any state, the whole match reset), the deliverable a closed-loop Python program that
plays a fresh, unmodified match in the verifier on the original clock (a turn-based bout: the original turns and chess
clock), seeing the full state instead of camera images. The generic full-simulator layer (`tools/fullsim`) with a per-task
adapter; a duel's built-in learned seat plays inside the formal match as in the twin. The soccer joint pair keeps its
resource tiers: the GPU twin's agent container holds a GPU and the twin's training stack, the verifier is CPU-only in both.

| twin | oracle (Harbor; nop: no program, 0) |
|---|---|
| `embodied-olympics-match-soccer-match-i00-privileged` | see its README |
| `embodied-olympics-match-badminton-duelrl-i01-privileged` | untested (oracle runs waived); nop 0 |
| `embodied-olympics-match-badminton-match-i04-privileged` | partial: lost 2:11 (valid, replay identical) |
| `embodied-olympics-match-badminton-matchlow-i01-privileged` | partial: lost 0:11 (valid, replay identical) |
| `embodied-olympics-match-fencing-bout-i02-privileged` | full: won 15:13 (valid, replay identical) |
| `embodied-olympics-match-foosball-match-i01-privileged` | full: won 5:3 (valid, replay identical) |
| `embodied-olympics-match-soccer-jointcpu-i01-privileged` | untested (oracle runs waived); nop 0 |
| `embodied-olympics-match-soccer-jointgpu-i01-privileged` | untested (oracle runs waived) |
| `embodied-olympics-match-soccerssl-match-i01-privileged` | untested (oracle runs waived); nop 0 |
| `embodied-olympics-match-tabletennis-duelrl-i01-privileged` | partial: lost 3:5 to the built-in learned seat (valid, replay identical) |
| `embodied-olympics-match-tabletennis-match-i04-privileged` | partial: lost 4:6 (valid, replay identical) |
| `embodied-olympics-match-tabletennis-matchlow-i01-privileged` | partial: lost 0:5 (valid, replay identical) |

## G1 table tennis (`tabletennisg1`, ported from Embodied Olympics core 0.5)

Embodied Olympics' `tabletennis_g1` is a separate sport from `tabletennis`'s Franka. It is played by two Unitree G1s, each holding a racket. On the
Engineer track the agent's program drives all 29 joints of its G1 at 100 Hz and sees the ball only through two cameras. The match is one game to 5 points.
One task against the hardest opponent, level 4 (owner 2026-11-01), in three modes and two resource tiers. It is ported by Embodied First Exam,
not exported: core 0.5 has no exporter. The source is the release branch's generated task
`tabletennis_g1-match-wallclock-program-engineer-standard` (revision `g1tt-10+core-0.5`, commit `45ed806a5`). Its sim
service, core and judge (`tests/eo_judge`) are kept, and the changed files are listed under `patched` in `exported.toml`.
The patches switch on through the compose environment:
- The seat is `unmetered` (`core/metering/think_clock.py`): there is no metering proxy, and Harbor records the usage.
- The match is graded live (`RO_VERDICT_REPLAY=0`).
- The verdict ends the session: the agent container's entrypoint (`environment/match_end.sh`) asks the match service whether the result is final (`GET /over`, a patch of `core/http.py`: no seat, no arrival) and, a few seconds after it is, stops every process of the container (the collect hook's `kill -9 -1`). Harbor records the harness's exit (`NonZeroAgentExitCodeError`) and grades as at the cutoff; the result is already final.
- The session's end decides (`RO_COLLECT_ENDS_MATCH=1`). Without this patch, core 0.5 lets the programs play on after the session.
  - An end before the start is a no-show.
  - An end during play is `abandoned`, the agent's R-EXIT.
  - Both are valid losses.
- Two tiers (`resource_tier`, `tier_twin`). `matchcpu`: the seat has no GPU; the release's GPU serves only its training kit, and the kit's PyTorch runs on the CPUs. `matchgpu`: the release's seat, one NVIDIA GPU for the kit (20 GiB cap). The world and the opponent run on CPU in both.

The `-standard` twin runs `python3 -m core.lockstep`: the rule of the paragraph above, written for core 0.5. The platform's opponent is
a program on core 0.5 (`core/platform_seat.py`), so it is held to the same rule (`live = False`): the world waits for its
reply after every step. The reference plays observe, act, `wait` (`solution/ro_client.py`).
The `-privileged` twin is Embodied First Exam's (`tools/g1tt_priv`, `tests/formal.py`; the agent plays the computer,
owner 2026-11-01). Development has the full simulator at `/opt/fullsim`: any level, seed or state, and the formal
runner itself. The deliverable is a program `make_policy(config).act(view)`; every view has the seat's state, its camera
images and `truth` (the sport's `practice_truth()`: the ball's position, velocity and spin, both robots, the score). In the
separate verifier the program, run as `nobody` in its own process, plays seat A of a fresh match with the sport's
in-process runner (`core/local.py`). The world waits for it at every control step: 0.5 s a call, 1800 s of program time
in all. The opponent is waited for the same way. The core's fresh-process replay must agree with the match, and the video
is drawn after the verdict. No duel, no persistent session. The `matchgpu` privileged container adds the seat image's
GPU kit (`/opt/train`, `/opt/robot`, `/opt/ro`); the formal match runs the program on CPU without PyTorch.

**Hosts (realtime).** x1 needs fast cores. A trial uses:
- the world: 12 vCPU;
- the platform's G1: 8 vCPU;
- the seat: 8 vCPU;
- the practice service: 8 vCPU;
- the practice player: 1 vCPU.

Oracle runs (levels 1-4 while porting) on an idle Xeon Platinum 8488C (m7i.16xlarge) passed the integrity rules in all 5 matches:
- world lag p99: 1.2-1.7 ms;
- late step p99: 9.4-11.2 ms;
- render misses: 0.08-0.12 %.

The limits are 0.5 s, 0.05 s and 1 %. On a Ryzen 9 7950X at a load of 30-50 on 32 threads, the matches were voided (late step p99 0.09-0.8 s). A breach
voids the match as infrastructure (R-INTEGRITY), never as the player's loss. The x1 world's minimum is 12 vCPU, the fewest
measured (`scripts/task_resources.toml`).

| task | instance | oracle (Harbor 0.23.0; nop: a valid no-show or no deliverable, 0) |
|---|---|---|
| `embodied-olympics-match-tabletennisg1-matchcpu-i01-realtime` | level 4 (the BOSS), seed 4 | no winning oracle: the camera-only reference lost 2:5 to level 4 (valid; the release: it won 2 of 5 seeds, this one 7:6) |
| `embodied-olympics-match-tabletennisg1-matchcpu-i01-standard` | as above, lockstep | no winning oracle: lost 5:7 |
| `embodied-olympics-match-tabletennisg1-matchcpu-i01-privileged` | as above, full state, in-process runner | full: the reference program (camera-only, it ignores the truth) won 5:3, replay identical |
| `embodied-olympics-match-tabletennisg1-matchgpu-i01-realtime` | the CPU tier's, one GPU | no valid oracle: on an EPYC host with L40S GPUs (g6e.12xlarge, load 8-27 of 48 from other trials) all 3 x1 matches were voided by R-INTEGRITY (late step p99 0.053-0.178 s, render misses 36-71 %) |
| `embodied-olympics-match-tabletennisg1-matchgpu-i01-standard` | as above, lockstep | the reference won 5:1 (same host) |
| `embodied-olympics-match-tabletennisg1-matchgpu-i01-privileged` | as above, full state | partial: the reference program lost 6:7 on that host, replay identical (it won 5:3 on the Xeon 8488C: the in-process match agrees with its replay on one host, not across CPU architectures) |

What differs from Embodied Olympics - Fun's tasks (`eai-standard/2.x`; PROTOCOL §3):

| | Embodied Olympics - Fun (`eai-standard/2.x`) | Embodied Olympics - Match (exported) | why |
|---|---|---|---|
| protocol | `eai-standard/2.x` | `eai-standard-realtime/1.0` (real-time matches; Embodied Olympics' own: `game` CLI / HTTP at `localhost:8000/A/...`), `eai-standard-turn/1.0` (turn-based matches, mode `standard`: the same service and `game` CLI; the world waits for the player whose turn it is, and each player has a chess clock of real time that runs on its own turns, reviews included; a player whose clock runs out loses, a valid 0) | the frozen review after every point (at most 300 s, 600 s in soccer: `READY_TIMEOUT_S`; the world stands still, the agent's time runs on; a side that has not sent `ready` by then loses the match, `ready_timeout`, a valid 0: the world does not go on by itself; stated in each instruction and in `game spec` `timing.review_timeout_s`, `patched` in exported.toml) is part of Embodied Olympics' rules, and its results are only comparable under them |
| crash recovery | journal, resume | none: a sim crash ends the trial with `infra_error = 1` | the match is one continuous live record (its scores and winner); a resumed match would not be the recorded one |
| slowdown | — | per task, the sport's official slowdown: table tennis 10 (Embodied Olympics PR #138), badminton 20, humanoid soccer 5, wheeled soccer 10, foosball 20 (the sim service's `RO_SLOWDOWN` default); turn-based matches have none (`metadata.chess_clock_s`: fencing 3600 s) | results state S, or the chess clock |
| agent budget | the benchmark's 7200 s | 7200 s; badminton i04, the badminton duel, wheeled soccer and foosball 14400 s (those tasks' own `[agent] timeout_sec`) | a game to 11 at S = 20 took the reference alone 78 to 93 min; a 5 v 5 match is 2.9 h of wall time at S = 10; foosball's 240 s of play is up to 4800 s at S = 20 |
| network | open (Embodied Olympics - Fun's exception) | the allowlist (model APIs and package registries), as every other benchmark: these tasks declare it, and PROTOCOL H.6 holds them to it | Embodied Olympics' design; the open-egress exception is Embodied Olympics - Fun's |
| twin | privileged + standard | a privileged twin for every match, a standard twin (the world in lockstep) for every real-time match (below) | no trajectory deliverable; a twin needs a full-state program the verifier can play |
| seeds | the instance's | matches: `instance_seed` = the instance's development seed, the only one allowed (a turn-based match whose world is deterministic has one outcome per sequence of choices: its oracle is `full` when the reference wins that seed); skill tasks: seed 0 = the fixed development request set | development seeds below 100000: previews; Embodied Olympics' official results are produced by Embodied Olympics on its hidden six-digit seeds |
| metering | the usage gateway | the same (the seat is "unmetered" for Embodied Olympics: no proxy, no credential in the sim; the proxy file `metering/think_proxy.py` is in the image's copy but never started) | |

**Graded by the live match.** The core's fresh-process validity replay (`python -m core.episode`, `replay_check.json`)
does not run. The verdict is the live match as the trusted core recorded
it while playing: `scores`, `match_winner`, `reason`, `errors` and the seats' metering in `final.json` (`graded_by` live,
`replays` 0). `valid_trial` = finalized ∧ complete ∧ no technical error, without the replay term, and success = a valid
match the agent's seat A won (duelrl: `tests/fexam_reward.py`'s `valid_trial` ∧ `A_won`).
A patch to the exported files (listed under `patched` in `exported.toml`) switches on with `RO_VERDICT_REPLAY=0` in the sim service's compose environment (the convention of #300's matchlow tasks, whose core has the same hunks), so the core
keeps its upstream behaviour without it. The patch touches `core/service.py` (`finalize` skips the replay, `write_final`
drops the replay term, `deterministic` and `replay_scores`) and `core/grading.py` = `tests/grade.py` (a live record needs
no `replay_check.json`; reward.json gets `graded_by_live 1`, `replays 0`, and loses `deterministic` and the sports' legacy
`replay_*` fields). The spectator video stays a video-only pass after the verdict. Where its limit was below the old
replay's 600 s (table tennis, foosball) it is 600 s, and the hook waits 720 s for it and 180 s for the verdict.
**source_sha:** `core/` is hashed into every match's `source_sha` (with the sport's directory), so the patch gives
each task a `source_sha` of its own; archived episodes still replay, because the replay echoes the header's own
`source_sha`.
**Agent-caused simulator errors (docs/protocol/standard_mode.md Part 3).** In a real-time match graded live and finalized, an error of the control step itself (`reason` technical_error, every `errors[]` entry `where` "world_step": `core/realtime.py` records the agent's commands applied and the world's step under that name) after the agent's first applied act (`seats.A.applied` > 0; acts refused 409 / 429 never reached the world) is the agent's 0 (`valid_trial` 1, `agent_sim_error` 1), not a technical failure with a free retry. Before it, in a turn-based match, with an unfinalized record, or for any other technical error (the loop's bookkeeping, rendering, metering, a crashed sim service) it stays infrastructure. A fatal-signal crash of the sim process leaves no final record in these tasks (no crash recovery), so it stays infrastructure. The badminton tasks' `spectator/sport_video.py` compares its replay's end with the live record (`final.json`: `matches_live_record` in video.json). The table tennis and foosball hooks wait 720 s for the video (its limit 600 s + 120 s) and 180 s for the verdict.

**Replay videos of the matches.** The sim service draws the spectator video after the verdict (`core.spectator`, `RCB_VIDEO_TIMEOUT_S`); the grade never depends on it. Humanoid soccer's full match takes about 8-10 min to replay and draw, so its limit is 1800 s (as wheeled soccer) and the collect hook waits as long. Badminton declares no spectator camera or scene, so the core drew nothing: its tasks run `environment/sim/spectator/sport_video.py` from the collect hook instead (the players' two cameras, the sport's own `Views`, at 10 frames per game second; `video.json` says whether that replay ended in the verdict replay's state). `spectator/` is outside the match's `source_sha` (`core/`, `sport/`), so the match and the grade do not depend on it; both are `patched` in `exported.toml` (to be sent upstream: a spectator camera in `sports/badminton/sport.toml` would change the sport's `source_sha`). Table tennis (about 100-420 frames) and wheeled soccer (1800 s) rendered every recorded video and are unchanged. Fencing (turn-based) draws one still per phrase, held 1 s, with `core.spectator`; its limit is 900 s, the collect hook waits as long. Badminton i04 and the badminton duel use it too (collect 2640 s, verifier 2820 s: 60 s of headroom) (checked on a local duel: 392 frames in 28 s, `matches_verdict_replay` true); foosball (at most 240 s of play, 2400 frames; a 136 s match drew 1360 frames in 47 s), the table-tennis duel and table tennis i04 draw with `core.spectator` within 300 s.

**Duels against a built-in seat.** In `-duelrl-` tasks seat B is a built-in player inside the service (RO_BUILTIN_SEATS), which never ends a session. Embodied Olympics' core forfeits an abandoned match only for a single side, so unpatched an agent that left a duel after the start would end it `collected` (not a valid trial, a free retry). Both duel tasks patch `core/service.py` `abandon_single` to leave built-in seats out: the HTTP side that leaves loses `abandoned`, a valid 0, as in a match against the scripted opponent; the instruction says so, and it says that the learned opponent reads the simulator's true state (the table-tennis one also plans its own swing, a field only built-in seats may send). `tests/test.sh` writes success 0 with `grader_error = infra_error = 1` (a grader failure: one retry under H.5) if `fexam_reward.py` (which adds the duel's `A_won`) fails, never `grade.py`'s `valid_trial` alone. `patched` in `exported.toml`; to be sent upstream.

**The low-level match: the skill served from the agent's own container (Embodied Olympics core 0.2.34, 2026-10-17).** In Embodied Olympics' own low-level matches the player's skill runs in a trusted per-seat container that mounts the agent's `/app/output` volume, adds SETUID / SETGID and sets `network_mode: none`, three breaches of H.1 here. In `embodied-olympics-match-tabletennis-matchlow-i01-realtime` and `embodied-olympics-match-badminton-matchlow-i01-realtime` there is no such container and no agent code runs in the sim (H.3): the agent starts its own skill server in its own container (`game skill serve /app/output/skill`: skilleval's `skillhost.py serve --tcp 127.0.0.1:8765 --live`, shipped in the agent's image under `/opt/skillkit`; the skill runs from a private copy in its own process, as `nobody` when the container runs as root). The sim and the agent's container share the egress sidecar's network namespace, so the sim calls the server over the loopback (`RCB_SKILL_INLOOP_A = "tcp:127.0.0.1:8765"`): no published port, no volume, no capability, no network of its own. The server reloads the skill whenever its files change (the new version plays from the next call). Each call's answer carries the version (sha256); `inloop_A.jsonl` (an artifact) logs every call and every version change; the episode holds the lowered joint commands, so the fresh-process replay needs no skill. A call without a server, or one that fails or times out, changes nothing (the command in force stays) and is logged: the player's own error, the match stays valid. The skill's compute counts in match time as before. Reward extra fields `skill_*` (versions, calls, failures); success is the match. Live grading (owner 2026-10-17): the tasks' compose files set `RO_VERDICT_REPLAY = 0`: the verdict is the sim's live record (`final.json` `verdict_replay` false), no fresh-process grading replay; `tests/grade.py` accepts it and reports `graded_by_live` / `replays`. Patched here (the #300 review; `patched` in `exported.toml`, to be sent upstream): the agent controls the server the sim calls, so the sim's `RemoteHost` (`environment/sim/skilleval/skillhost.py`, and the identical copy under `environment/skillkit/`) reads only typed fields of its answers (a version is a string, `functions` a list of strings; an answer that is not a JSON object is a failed call): before, an answer such as `status: [1]` raised inside the control step (a `world_step` technical error: a free retry before the agent's first act) and a list as the version stopped `tests/fexam_reward.py` (no `infra_error` field); `fexam_reward.py` also skips malformed rows of `inloop_A.jsonl`.

**Option c (owner 2026-10-17; Embodied First Exam's patch, `patched` in `exported.toml`).** The
agent's skill runs only in the agent's own container, and no agent code can run in the sim's: the in-sim upload host
(core 0.2.32's `POST /<seat>/skill`, `game skill upload`, `skillhost.UploadHost`) and its jail (seccomp, one CPU, `nobody`)
are removed from the tasks' copies (the sim's and the agent's kit), and the compose files set `RCB_SKILL_REMOTE_ONLY=1`
(`skilleval/inloop.py` refuses any skill source but `tcp:`). The skill's `step()` is one **synchronous** call at each due
control step (`RCB_SKILL_INLOOP_TIMING=sync`): the world waits for its answer at most `step_wait_s` = min(the step time
limit, one control period S x control_dt) (0.1 s for table tennis at S = 10, 0.2 s for badminton at S = 20; `game spec`)
and applies it at that step; no answer in time, an error, garbage or a dead server = no command at that step (the
player's, never infrastructure; the world goes on, its compute counted in match time); a step() is skipped while a
`hit` / `act` call computes. `hit` / `act` calls run as before, off the world's lock (the world runs on), each waited for
at most its time limit + 1 s (`skillhost.LIVE_MARGIN_S`; was limit + 40 s). The sim sends the skill the seat's
whitelisted observation without images (the same `state` its `/status` gives) and the public spec; it reads back one
command, which the low level's own parser checks (any exception there is the skill's failure, never the control
step's). The agent may change its skill at any time: its server reloads changed files at each call, and that call plays
the new version; every version that played is an episode row `skill_load` (information only, never replayed) besides
`inloop_A.jsonl`. The
fresh review's fixes (same day): each call to the agent's server has ONE deadline, its send included (a server that
withholds its receive window cannot hold the world for a send and then a full answer time), the connection and its
configure inside the same bound; step()'s answer is capped at 128 KiB (it is parsed on the world's thread); a server
that was down or not loaded is tried again by step() at most once a second (one bounded call), not only at the next
unit; the agent's server is always played in timing sync (a `tcp:` host in "wall" or "free" is refused, and the
default for it is sync); any exception of a live call is the skill's failure (kind `server`, never `host`); a command
of the seat's own step() counts for the seat (`applied_tick` in final.json's seat stats, core/realtime.py), so a
`world_step` error after it, before any act, is the agent's 0 in `tests/grade.py` (= `core/grading.py`), not a free
retry; at most 200 `skill_load` episode rows per seat (the rest counted, `loads_not_written`; all in `inloop_A.jsonl`),
a live one labelled `reported_by: your skill server`; the server checks for changed files by a stat walk and hashes
only when a size or mtime changed. Round 2 of the review: a reconnect's configure gets only the time left of the
call's deadline; a step() command is counted (`tick_submitted`) before it is applied, so one whose application raises
also makes the error the agent's; a live call that fails unexpectedly closes its connection; stale data waiting on the
connection before a request drops it (a new connection for that call); the once-a-second retry is armed only by a call
actually sent. Harbor 0.23.0
trials (a cloud CPU host, 2026-10-17, this patch): table tennis oracle a valid match lost 0:5 (899 step() calls, each answered
inside the 0.1 s bound, max 0.074 s, applied at the step asked; 15 hits, none failed; replay.mp4), badminton oracle a
valid match lost 1:11 (33 act calls, none failed; replay.mp4), nop on both: no_show, valid, success 0, infra_error 0;
an adversarial probe on table tennis (the reference player's decisions through a skill that sleeps past its limits,
raises, returns unhashable / NaN / oversized / 500-deep answers): a valid match, success 0, infra_error 0, 656 of 929
calls failed as the player's, every step() wait at most 0.101 s, POST and GET /A/skill 404, /A/state etc. 404, no sim
file readable from the agent's container, only port 8000 open on the loopback; the skill was sent the seat's
whitelisted state (no ball coordinates) and the public spec only.

**Skill tasks' verifier.** The verifier runs the delivered skill as `nobody` in its own process, in the container that
grades it. A skill must not be able to leave a detached process behind (double fork, `setsid`) that rewrites
`/logs/verifier/report.json` or the reward files after the evaluation (Harbor makes `/logs/verifier` 777, without the
sticky bit). So: the evaluator is the subreaper of the skill's tree, and closing a skill kills its session and every process of
`nobody` below the evaluator until none is left (`skilleval/sandbox.py` `end_sandbox_processes`; it raises, and the
grade is a `grader_error`, if one survives); the skill runs with `RLIMIT_NPROC` 128; `tests/test.sh` makes
`/logs/verifier` 755 and writes the report to `/var/lib/skilleval/` (root, 700); `tests/grade.py` kills any
process of `nobody` left in the container, removes every entry of `/logs/verifier` root did not write, reads the
report only from a root-owned directory nobody else can write, and writes the reward files fresh (`O_EXCL`,
`O_NOFOLLOW`), then copies the report there. The isolation probe (`python3 -m skilleval.evaluate --sport-dir sport
--probe --skill <dir with probe.py>`) adds three targets: writing `/logs/verifier`, writing the report's directory,
and a detached process that must be gone after the skill is closed (`survives_close`), plus `nproc_unlimited`. Measured
in the verifier image (Harbor's layout: root, no network, `/logs/verifier` 777): a skill that plants a success and
leaves a process to keep it there gets 0; the reference skill passes; the probe finds no leak. Still possible and harmless: a skill with `memory = "per_case"` can keep files in `/tmp`
between requests (it gets no outcome back, so it learns nothing it was not given).

Images: `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0` (public; the image Embodied Olympics' frozen revisions were screened on;
built from Embodied Olympics' own tree, not from this repository), for every task but humanoid soccer, which runs on
`ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0` (public). CPU only, except the agent's containers of the GPU tiers (`soccer-jointgpu`, `tabletennisg1-matchgpu`). G1 table tennis (public): `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0` (the sim and
practice services) and `-tabletennisg1-seat-0.1.1` (the agent's container: the release's seat image, 0.1.0, plus the GPU kit's
missing `bodies/sources.py` in `/opt/robot/lib/bodies`, the release's fix 7e0b8c573; without it `bodies.gpu.twin.GpuTwin` fails to import `bodies.servo`).
