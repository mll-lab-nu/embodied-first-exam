# Embodied Olympics · robot epee fencing, bout against level 2 (privileged)

## Task
Win an epee bout to 15 touches against the scripted fencer.

## Goal
Success: your program wins the complete formal bout.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that directory (at most 512 regular files
and 32 MiB; no links or special files; helpers are importable). It defines `make_policy(config)`, returning an object
with `act(view)` that lives for the whole bout. `view` has `state` (the twin's observation), `truth` (the full current
state) and `scores`; `act` returns one action of the twin's interface (e.g. `{"type": "phrase", "intention": "lunge"}`),
`{"type": "ready"}` during the review after each of your phrases, or None. Save a valid program early and overwrite it
when you have a better one.

The formal bout: a separate verifier without network runs your final program as an unprivileged process against a fresh
bout, with no reset. On your turn your chess clock (3600 s in all) runs while the program computes, and each exchange
with it is limited to 5 s; out of time loses the bout.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. Hand in executable code, not a recorded list of
intentions or a claimed score; no model or API calls during the formal bout. Your program may read the public, read-only
copy of the simulator at `/opt/dev` for its own predictions, never the copy that runs the bout, the referee or the logs.

## Robot Interface
Two simulated Unitree G1 humanoids fence one epee bout, phrase by phrase: before each phrase each fencer chooses one of
nine tactical intentions. You are seat `A` against the scripted level-2 fencer, seed 35: the same fixed bout as the
standard twin (`embodied-olympics-match-fencing-bout-i02-standard`), with the same robot, actions, rules, limits and
opponent. It is turn-based: the bout waits for your decision. You have the full simulator to develop with; you hand in a
program that plays the bout.

### Session
```python
from tools.fullsim.turn import TurnSession
s = TurnSession("fencing", level=2, seed=35)
s.spec()          # the action interface and the rules (as the twin's `game spec`)
s.state()         # the observation
s.world           # the whole mutable bout
s.act(command)    # plays your intention for the next phrase and the opponent's answer, at once
s.reset()         # rebuilds the whole same-seed bout
```
The simulator and its source are at `/opt/fullsim`; `/opt/fullsim/README.md` documents the program API, the `truth`
fields, the units and a self-test of `program.py`.

### Actions
The twin's actions (`s.spec()` gives their fields and ranges): `phrase` with one of the nine intentions, and
`{"type": "ready"}` in the review after each of your phrases.

## Others
- In development you may inspect and change private worlds and search with repeated resets; none of it reaches the
  formal bout.

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 16 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (`s.reset()`); none in the formal bout.
