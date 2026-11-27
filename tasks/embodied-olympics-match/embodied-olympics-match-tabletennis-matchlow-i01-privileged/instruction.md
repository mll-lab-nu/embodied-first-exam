# Embodied Olympics · robot table tennis at the low level, match against level 1 (privileged)

## Task
Win a game of table tennis to 5 points against the scripted opponent, with a hitting skill you write yourself playing
every stroke.

## Goal
Success: your program wins the complete formal match.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that directory (at most 512 regular files
and 32 MiB; no links or special files; helpers are importable). It defines `make_policy(config)`, which returns an
object with an `act(view)` method; that object lives for the whole match. `view` has `state` (the twin's observation),
`truth` (the full current state) and `scores`; `act` returns one action of the twin's interface, `{"type": "ready"}`
during a review, or None. Save a valid program early and overwrite it when you have a better one.

The formal match: a separate verifier without network runs your final program as an unprivileged process against a fresh
match, with no reset. The world runs at 1/10 of real speed while your program computes, as in the realtime twin; each
review (after a point, a goal or another stoppage) freezes it for at most 300 s; the formal match has 7200 s of wall
time. The verifier runs on 4 pinned CPUs, so its speed matters.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. Hand in executable code, not a recorded trajectory
or a claimed score; no model or API calls during the formal match. Your program may read the public, read-only copy of
the simulator at `/opt/dev` for its own predictions, never the copy that runs the match, the referee or the logs.

## Robot Interface
Robot table tennis: each player is a Franka Panda arm with a paddle on an x-y rail base behind its end line, and the arm
and the base are both held to the real robot's limits. You see the game only through two cameras, four frames each. The
players' robots serve by the ITTF service laws, with a toss device on the robot. You are seat `A` against the scripted
level-1 opponent, seed 22: the same fixed match as the realtime twin
(`embodied-olympics-match-tabletennis-matchlow-i01-realtime`), with the same robot, actions, rules, limits and opponent.
The world runs at 1/10 of real speed. The low level: the twin's skill in the loop without its plumbing. Your program
returns the robot's low-level commands (traj / slew / hold / toss) itself; there is no hit skill and no skill server
(what the twin's skill computes, your program computes). The toolkit is under `sports/tabletennis/seat/`.
`from tools.fullsim.session import Session`; `Session("tabletennis", level=1, seed=22)` gives `state()`, `world`,
`spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. You have the full simulator to develop with; you hand in a
program that plays the match.

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
The twin's actions (`s.spec()` gives their fields and ranges): `traj`, `slew`, `hold` and `toss`: the low level, with no
hit skill. During a review return `{"type": "ready"}`.

## Others
- In development you may inspect and change private worlds and search with repeated resets; none of it reaches the
  formal match.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (the simulator's start-up too). At
  the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). Calls into a long-running process can block for their
  whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (`s.reset()`); none in the formal match.
