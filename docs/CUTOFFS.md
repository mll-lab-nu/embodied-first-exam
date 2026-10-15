# Agent time cutoffs

Every task gives the agent a fixed wall-clock time, its **cutoff**: Harbor's `[agent] timeout_sec` in the task's own
`task.toml`. At the cutoff the agent is stopped and the trial is graded as it stands ([PROTOCOL.md](PROTOCOL.md) §2.12).

**Each task sets its own** (since 2026-10-14, owner, board 0120; as in Terminal-Bench): the author decides the number in
the pull request that adds or changes the task, and states it in the pull request's Contract. A benchmark rendered by a
generator keeps its number as a constant of the generator (`scripts/<bench>/`), so that a change of it is a change of
the benchmark's own files only. There is no central table and no apply script; the numbers in use, per benchmark and
mode, are in the task list generated after every merge to `main`.

Rules, checked per task by `ci_checks/check-cutoffs.py` (on a pull request: the tasks of the benchmarks it touches):

- a whole number of seconds, **at most 14400** (PROTOCOL D8; no benchmark is excepted); 3600 unless the pull request
  justifies another number;
- **twins have the same cutoff**: a task's privileged and standard versions (the mode registry's `same_cutoff_as`,
  PROTOCOL §2.15, §2.16; owner, 2026-10-12);
- the instruction's closing `## Time limit` section states the task's own number (below), and nothing else in the
  instruction states the limit as a duration; the README's `Agent time budget` row and, in the standard modes, the sim
  service's `RCB_WALL_CLOCK_S` say the same number;
- a benchmark SHOULD use one number for all its tasks of a mode; a pull request that gives some tasks another number
  says why (the pull request's overview lists the numbers it changes).

**When the clock starts.** Harbor counts the cutoff around the agent's run only (`asyncio.wait_for(agent.run(...), timeout=...)` in its trial's agent phase): after the environment has been built and started and after the agent's harness has been installed, each of which has a timeout of its own. It does not count from the container's start. In the standard modes the `sim` service starts with the environment, so whatever start-up it has not finished by then is waited out inside the agent's time.

## What the agent is told

Every `instruction.md` ends with the same section, written by `scripts/task_conventions.py` from the task's `[agent] timeout_sec`: the last thing the agent reads (here for 3600 s; the first paragraph is the same in every mode):

> ## Time limit
> You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
>
> This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).

In the standard and standard-realtime modes the second paragraph is:

> This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).

(No benchmark keeps the earlier, weaker sentence today: every service counts from the agent's first request.)

What a benchmark adds about its own time (a simulator's start-up, what its service counts) stands in its own text and names no number: it says "the time limit (`## Time limit`)".

## Changing a cutoff

A change of a cutoff is an owner decision (PROTOCOL §2.12). Its pull request:

1. sets the new `[agent] timeout_sec` in each task concerned (a generated benchmark: its generator's constant, then
   re-run the generator), for the privileged and the standard version alike;
2. runs `python3 scripts/task_conventions.py tasks/<task> ...` (any generator ends with it), which writes from the
   number the closing section of `instruction.md`, the README's `Agent time budget` row, the sim service's
   `RCB_WALL_CLOCK_S` (standard modes) and the task's `DIGEST`;
3. states in its description what changed, old -> new, who decided and why; that and the git history of the tasks are
   the record (the History below ends on the day the central table was removed).

A change of a cutoff changes the task in place: the scene, the frozen instance, the success rule and the verifier are the same, so the task keeps its name (PROTOCOL §2.8, §2.12). Results recorded under another cutoff are reported separately (PROTOCOL D8), and trials already running keep the cutoff they started with.

## What follows the number, and what does not

- **Follows by itself** (`normalize`): everything listed above, and a scheduler's estimate of a trial's length, which reads `task.toml`.
- **The sim service's clock** (`RCB_WALL_CLOCK_S`) only reports: `spec["budget"]["wall_clock_s"]` and `meta["time_left_s"]`, counted from the agent's first request to the service (any endpoint; kept through a restart of the service), never from the service's start: the service is up before the agent's phase begins, so a clock started with it ran ahead of Harbor's (a median of 79 s over the recorded trials). Harbor's timeout is what stops the agent. RoboARC's service still ends the episode itself when its own count reaches 0; since its MuJoCo release (2026-10-13) that count starts at the first request, so it is never before Harbor's timeout (to become report-only at RoboARC's next task update: `docs/benchmarks/roboarc.md`).
- **Look at these when you raise a cutoff** (lowering one is safe): the collect-hook and verifier budgets that were sized for an episode as long as the agent's time (RoboCasa, RoboCasa365 and RoboCasa-GR1 `COLLECT_TIMEOUT_S`; RoboLab, YAMLab, DexJoCo and BEHAVIOR-1K, see their `docs/benchmarks/` pages), and the cap of 14400 s.
- **RoboOlympics' exported matches**: the cutoff has to stay above a match's wall time at its slowdown plus the frozen reviews between points (wheeled soccer: 2.9 h at S = 10; badminton: 1.3 to 1.6 h at S = 20).
- **Not derived from it**: the token budget (PROTOCOL §5), the resource limits (§2.10), reset budgets, step caps, verifier timeouts.

## History (2026-10-11 to 2026-10-14)

From 2026-10-11 to 2026-10-14 the cutoffs lived in one table, `scripts/task_cutoffs.toml` (per benchmark and mode, with
exceptions per family and per task: on 2026-10-14 three RoboOlympics standard-realtime matches had 14400 s, which
are now simply those tasks' own numbers), written into the tasks by `scripts/task_cutoffs.py apply`;
the table started with the number every task had on 2026-10-11 and recorded each change. Its record, as it was when
the table was removed (the table itself is in the git history before that commit); later changes are recorded by their
pull requests:


| Date | What | Change | Decided by | Note |
|---|---|---|---|---|
| 2026-10-11 | RoboDojo, privileged, standard | 5400 s -> 3600 s | owner | #155, before this table existed (the baseline already has 3600); trials recorded with 5400 s are kept apart |
| 2026-10-12 | RoboFunOlympics, privileged, standard | (none) -> 7200 s | owner | the benchmark's first tasks (#161): the agent may go online and is asked to find, download and adapt controllers, or to build one, which an hour does not hold |
| 2026-10-12 | BEHAVIOR-1K, privileged, standard | 14400 s -> 7200 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 14400 s are kept and reported as such |
| 2026-10-12 | ManiGuard, privileged, standard | 7200 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 7200 s are kept and reported as such |
| 2026-10-12 | RoboPaint, privileged, standard | 7200 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 7200 s are kept and reported as such |
| 2026-10-12 | RoboLab, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | MyoSuite, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | DexJoCo, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | RoboWits, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | YAMLab, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | LabUtopia, privileged, standard | 5400 s -> 3600 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 5400 s are kept and reported as such |
| 2026-10-12 | RoboTwin 2.0, privileged, standard | 3600 s -> 1800 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 3600 s are kept and reported as such |
| 2026-10-12 | VLABench, privileged, standard | 3600 s -> 1800 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 3600 s are kept and reported as such |
| 2026-10-12 | MetaWorld+, privileged, standard | 3600 s -> 1800 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 3600 s are kept and reported as such |
| 2026-10-12 | LIBERO-MAX, privileged, standard | 3600 s -> 1800 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 3600 s are kept and reported as such |
| 2026-10-12 | MuJoCo Playground, privileged, standard | 3600 s -> 1800 s | owner | stricter cutoffs in 30-minute steps, the same number in both modes (board 0085 section 9: of the successful trials so far, the share that fits the new number, the simulation cost and the task's execution time); results recorded with 3600 s are kept and reported as such |
| 2026-10-12 | RoboTangle, privileged, standard | 21600 s -> 7200 s | owner | stricter cutoffs, the same number in both modes (board 0085 section 9); no result in the pool was recorded with 21600 s (the results of 10-08..10-10 were set aside before the egress fix); the cap exception of PROTOCOL 2.3 is no longer used |
| 2026-10-13 | Panda Dynamic Scenes, privileged, standard | (none) -> 3600 s | proposal #177 (D8 default) | the benchmark's first tasks: the protocol's default; a scene builds in seconds and simulates at 60-150 control steps per second, so the hour is the agent's own work |
| 2026-10-13 | RoboTangle, privileged, standard | 7200 s -> (removed) | owner | removed: the benchmark is renamed RoboARC (next entry) and its Genesis tasks are deleted; RoboARC's MuJoCo release replaces them, and results recorded under this row are not carried over |
| 2026-10-13 | RoboARC, privileged, standard | (none) -> 10800 s | owner | new row: RoboARC, the MuJoCo release that replaces RoboTangle's Genesis tasks (prepared as RoboTangle-New, then RoboTangle; their entries, 0 -> 7200 on 2026-10-12 and 7200 -> 10800 on 2026-10-13, are folded into this one): 3 h wall clock for every family, within the default cap |
| 2026-10-13 | RoboSafeBench, standard | (none) -> 3600 s | owner | the benchmark's first tasks: the protocol's default (D8); RoboSafeBench's own trials gave agents 40 minutes |
| 2026-10-14 | RoboSafeBench, standard-realtime | (none) -> 3600 s | owner (board 0112: a realtime twin's cutoff equals its standard twin's) | the benchmark's first standard-realtime tasks: the standard tasks' number (D8 default); the episode's robot-time budget under the realtime clock (1800 s for the realtime set, RoboSafeBench 0.5.1) runs in real time from the first submit, so 3600 s leaves 1800 s for looking and planning before the clock starts (the harness's set-up and the service's start are outside or before it); the collect hook's finalize is outside the agent's time |
| 2026-10-14 | RoboOlympics, standard-realtime | 7200 s -> (removed) | owner (board 0107, E7) | removed: the three standard-realtime tasks on this repository's eai-standard/2.3 adapter (table tennis, badminton, air hockey) are deleted; their results are moved out of the pool (jobs-backup), not carried over |
| 2026-10-14 | RoboFunOlympics, privileged, standard | 7200 s -> (removed) | owner (board 0107, E7) | removed: the benchmark is renamed RoboOlympics (next entry); the same 100 tasks, renamed robofunolympics-* -> roboolympics-* |
| 2026-10-14 | RoboOlympics, privileged, standard | (none) -> 7200 s | owner (board 0107, E7) | RoboFunOlympics' row under its new name (its entry of 2026-10-12, 0 -> 7200, owner): the same tasks and the same number; no result was recorded under the old name |
| 2026-10-14 | RoboOlympics, standard-realtime | (none) -> 7200 s | owner (board 0107, E7; proposed in #180) | the matches RoboOlympics exports with its own service (PROTOCOL §4c; table tennis, humanoid soccer): a match at its slowdown plus the frozen reviews between points fits in 7200 s; RoboOlympics' skill-engineering tasks (standard, policy) take the benchmark's standard number, 7200 s |
| 2026-10-14 | `roboolympics-soccerssl-match-i00-standard-realtime` | (none) -> 14400 s | owner (board 0107, E7; proposed in #180 by RoboOlympics' owner, 2026-10-13) | wheeled soccer 5 v 5 exported by RoboOlympics: two halves and a shoot-out are about 1035 s of game time, 2.9 h of wall time at its slowdown S = 10, plus the frozen reviews; at S = 5 its four overhead cameras cannot be rendered in time (51 % busy at S = 10); the D8 cap |
| 2026-10-14 | `roboolympics-badminton-match-i01-standard-realtime` | (none) -> 14400 s | owner (board 0107, E7; proposed in #180 by RoboOlympics' owner, 2026-10-14) | badminton stays at RoboOlympics' slowdown S = 20 (at 10 its camera-only reference player loses level 1, 0 of 20: its swing planning takes up to 0.89 s, p90); a game to 11 at S = 20 took the reference alone 78 to 93 min, so a model with its reviews needs more than 7200 s; the D8 cap |
| 2026-10-14 | `roboolympics-badminton-match-i02-standard-realtime` | (none) -> 14400 s | owner (board 0107, E7; proposed in #180 by RoboOlympics' owner, 2026-10-14) | as roboolympics-badminton-match-i01-standard-realtime (the same match at opponent level 2) |
| 2026-10-14 | MyoSuite, standard-realtime | (none) -> 3600 s | owner (board 0112: a realtime twin's cutoff equals its standard twin's) | the first standard-realtime task (table_tennis): the standard twin's number |
| 2026-10-14 | DexHand, privileged, standard | (none) -> 3600 s | DexHand tasks pull request (D8 default; team meeting 2026-10-14) | the benchmark's first tasks: the protocol's default; a scene builds in 1-12 s and the recorded reference episodes replay in seconds to 10 minutes on one core (the longest, sweep_dustpan, is 66 s of robot time at 2 kHz), so the hour is mostly the agent's own work |
| 2026-10-14 | Panda Dynamic Scenes, standard-realtime | (none) -> 3600 s | owner (board 0112: a realtime twin's cutoff equals its standard twin's) | the standard-realtime twins of the 19 dynamic families: the standard twin's number |
| 2026-10-14 | RoboCasa365, standard-realtime | (none) -> 3600 s | owner (board 0112: a realtime twin's cutoff equals its standard twin's) | the first standard-realtime task (TurnOnToasterOven): the standard twin's number |
| 2026-10-14 | MuJoCo Playground, standard-realtime | (none) -> 1800 s | owner (board 0112: a realtime twin's cutoff equals its standard twin's) | the first standard-realtime task (BarkourJoystick): the standard twin's number |
| 2026-10-14 | AM-Bench, privileged | (none) -> 3600 s | proposal (D8 default) | the benchmark's first tasks (privileged only): the protocol's default; every Python process pays a few minutes of Isaac Sim start, which the hour includes |
| 2026-10-14 | AutoBio, privileged, standard | 3600 s -> (removed) | owner | removed: the benchmark's tasks are deleted from the repo (board 0119); its pool results were moved to jobs-backup/autobio-labutopia-removed-1014 |
| 2026-10-14 | LabUtopia, privileged, standard | 3600 s -> (removed) | owner | removed: the benchmark's tasks are deleted from the repo (board 0119); its pool results were moved to jobs-backup/autobio-labutopia-removed-1014 |
