# Full-simulator badminton: develop a program against level 1

Win one complete match against the frozen sport's scripted level-1 opponent, seed 7: the same frozen
instance as `roboolympics-badminton-match-i01-standard-realtime` (its privileged twin; there you see only camera images). The robot, the actions,
the rules, the limits and the opponent are unchanged; the world runs at 1/20 of real speed.

## Development and deliverable
`from tools.fullsim.session import Session`; `Session("badminton", level=1, seed=7)` gives `state()`,
`world`, `spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. The simulator and its source are at
`/opt/fullsim`. Reset rebuilds the WHOLE same-seed match. You may inspect and change private worlds and develop and
search with repeated resets within your resource and time limits; nothing of this reaches the formal match.
Read `/opt/fullsim/README.md` for the program API, the `truth` fields, the units and the self-test.

Leave `/app/output/policy/program.py` and any helper or data files in that directory (512 regular files, 32 MiB;
no links or special files). Define `make_policy(config)` returning an object with `act(view)`; it lives for the whole
match. `view` holds `state` (the twin's observation fields), `truth` (the full current state), `scores`. Return one
original action, a list of at most 1, `{"type": "ready"}` during a review, or None. No model or
API calls during the formal evaluation. Submit executable code, not a recorded trajectory or a claimed score; save a
valid program early and improve it.

## Formal evaluation
A separate verifier without network runs your final program as an unprivileged process against a fresh, unmodified
match; your program can read a public copy of the simulator for its own predictions, never the referee or the logs.
There is no formal reset. The original realtime clock runs at S = 20 while your program computes; each
review (after a point, a goal or another stoppage) freezes the world (at most 300 s). The formal match
has 7200 s of wall time.
The trusted journal is replayed twice in fresh processes; success is a complete win by the original referee with
matching replays. This fixed instance does not measure generalization to other instances.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **13 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
