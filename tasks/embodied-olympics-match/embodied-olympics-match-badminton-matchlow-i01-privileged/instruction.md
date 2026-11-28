# Embodied Olympics · robot badminton at the low level, match against level 2 (privileged)

## Task
Win a game of singles badminton to 11 points against the scripted opponent, with a stroke skill you write yourself
playing every stroke.

## Goal
Success: your program wins the complete formal match.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that directory (at most 512 regular files
and 32 MiB; no links or special files; helpers are importable). It defines `make_policy(config)`, which returns an
object with an `act(view)` method; that object lives for the whole match. `view` has `state` (the twin's observation),
`truth` (the full current state) and `scores`; `act` returns one action of the twin's interface, `{"type": "ready"}`
during a review, or None. Save a valid program early and overwrite it when you have a better one.

The formal match: a separate verifier without network runs your final program as an unprivileged process against a fresh
match, with no reset. The world runs at 1/20 of real speed while your program computes, as in the realtime twin; each
review (after a point, a goal or another stoppage) freezes it until your program returns `{"type": "ready"}`;
if it has not within 300 s, your side loses the match. Each call to `act` may take at most 5 s, else the match is
lost. The formal match has 7200 s of wall time. The verifier runs on 4 pinned CPUs, so its speed matters.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. Hand in executable code, not a recorded trajectory
or a claimed score; no model or API calls during the formal match. Your program may read the public, read-only copy of
the simulator at `/opt/dev` for its own predictions, never the copy that runs the match, the referee or the logs.

## Robot Interface
Robot singles badminton on a small court: the BWF court's lengths × 0.4, with the net at its full height. Each player is
a Franka Panda arm with a racket, held to the real Panda's limits, on an x-y gantry base. The shuttle has the real
shuttle's high drag and does not bounce. You are seat `A` against the scripted level-2 opponent, seed 8: the same fixed
match as the realtime twin (`embodied-olympics-match-badminton-matchlow-i01-realtime`), with the same robot, actions,
rules, limits and opponent. The world runs at 1/20 of real speed. The low level: the twin's skill in the loop without
its plumbing. Your program returns the robot's low-level commands (`traj`, `move`, `toss`, `none`) itself; there is no
act skill and no skill server (what the twin's skill computes, your program computes). The toolkit is under
`sports/badminton/seat/`. `from tools.fullsim.session import Session`; `Session("badminton", level=2, seed=8)` gives
`state()`, `world`, `spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. You have the full simulator to develop
with; you hand in a program that plays the match.

### Session
```python
from tools.fullsim.session import Session
s = Session("badminton", level=2, seed=8)   # this task's match: its opponent level and seed
s.spec()          # the action interface and the rules (as the twin's `game spec`)
s.state()         # the observation
s.world           # the whole mutable match
s.act(command)    # one action of the twin's interface
s.step(n)         # advances n control steps
s.ready()         # ends a review
s.reset()         # rebuilds the whole same-seed match
```
The simulator and its source are at `/opt/fullsim`; `/opt/fullsim/README.md` documents the program API, the `truth`
fields, the units and a self-test of `program.py`.

### Actions
The twin's actions (`s.spec()` gives their fields and ranges): `traj`, `move`, `toss` and `none`: the low level, with no
act skill. During a review return `{"type": "ready"}`.

## Others
- In development you may inspect and change private worlds and search with repeated resets; none of it reaches the
  formal match.

## Limits
- Time: 14400 s of wall-clock time from the start of your session. Everything counts, including the simulator's
  start-up. At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time
  left: `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for
  its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (`s.reset()`); none in the formal match.
