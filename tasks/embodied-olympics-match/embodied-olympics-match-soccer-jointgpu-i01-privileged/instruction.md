# Embodied Olympics · robot soccer 2 v 2 at the joint level (CPU + GPU tier), match against level 5 (privileged)

## Task
Robot soccer 2 v 2 at the joint level: four simulated Booster T1 humanoids (12 leg joint targets per robot every 20 ms,
no walking policy or kick skill) and one ball on a boarded 10 × 7 m pitch. You are seat `A` against the learned
joint-level team (level 5), seed 101: the same fixed match as the realtime twin
(`embodied-olympics-match-soccer-jointgpu-i01-realtime`), with the same robot, actions, rules, limits and opponent. The
world runs at 1/10 of real speed. You have the full simulator to develop with; you hand in a program that plays the
match.

## Goal
Success: your program wins the complete formal match.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that directory (at most 512 regular files
and 32 MiB; no links or special files; helpers are importable). It defines `make_policy(config)`, returning an object
with `act(view)` that lives for the whole match. `view` has `state` (the twin's observation), `truth` (the full current
state) and `scores`; `act` returns one action of the twin's interface (or a list of at most 2), `{"type": "ready"}`
during a review, or None. Save a valid program early and overwrite it when you have a better one.

The formal match: a separate verifier without network runs your final program as an unprivileged process against a fresh
match, with no reset. The world runs at 1/10 of real speed while your program computes, as in the realtime twin; each
review (after a point, a goal or another stoppage) freezes it for at most 300 s; the formal match has 10800 s of wall
time. The verifier runs on 6 pinned CPUs, so its speed matters.

Rules: write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
Hand in executable code, not a recorded trajectory or a claimed score; no model or API calls during the formal match.
Your program may read the public, read-only copy of the simulator at `/opt/dev` for its own predictions, never the copy
that runs the match, the referee or the logs.

## Robot Interface
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
The twin's actions (`s.spec()` gives their fields and ranges): per robot `joints`, `traj` and `hold` (12 leg joint
targets). During a review return `{"type": "ready"}`.

## Others
- In development you may inspect and change private worlds and search with repeated resets; none of it reaches the
  formal match.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (12 GiB of its memory). Over a cap a process can be killed (the CPU cap only slows you down); usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (`s.reset()`); none in the formal match.
