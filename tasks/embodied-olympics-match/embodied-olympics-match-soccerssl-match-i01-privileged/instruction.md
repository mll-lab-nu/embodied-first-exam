# Embodied Olympics · wheeled robot soccer 5 v 5 (RoboCup SSL Division B), match against level 4 (privileged)

## Task
Win a 5 v 5 wheeled robot soccer match against the yellow team.

## Goal
Success: your program wins the complete formal match.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that directory (at most 512 regular files
and 32 MiB; no links or special files; helpers are importable). It defines `make_policy(config)`, which returns an
object with an `act(view)` method; that object lives for the whole match. `view` has `state` (the twin's observation),
`truth` (the full current state) and `scores`; `act` returns one action of the twin's interface, `{"type": "ready"}`
during a review, or None. Save a valid program early and overwrite it when you have a better one.

The formal match: a separate verifier without network runs your final program as an unprivileged process against a fresh
match, with no reset. The world runs at 1/10 of real speed while your program computes, as in the realtime twin; each
review (after a point, a goal or another stoppage) freezes it for at most 600 s; the formal match has 13500 s of wall
time. The verifier runs on 4 pinned CPUs, so its speed matters.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. Hand in executable code, not a recorded trajectory
or a claimed score; no model or API calls during the formal match. Your program may read the public, read-only copy of
the simulator at `/opt/dev` for its own predictions, never the copy that runs the match, the referee or the logs.

## Robot Interface
Wheeled robot soccer 5 v 5 under the RoboCup SSL rules (Division B): ten omnidirectional SSL robots and an orange golf
ball on the 9 × 6 m field. You are seat `A` against the scripted level-4 opponent, seed 7: the same fixed match as the
realtime twin (`embodied-olympics-match-soccerssl-match-i01-realtime`), with the same robot, actions, rules, limits and
opponent. The world runs at 1/10 of real speed. You have the full simulator to develop with; you hand in a program that
plays the match.

### Session
```python
from tools.fullsim.session import Session
s = None
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
The twin's actions (`s.spec()` gives their fields and ranges): per robot `move`, `kick`, `dribble` and `substitute`, and
`batch` for several robots at one boundary. During a review return `{"type": "ready"}`.

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
- Resources: 4 CPUs, 8 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (`s.reset()`); none in the formal match.
