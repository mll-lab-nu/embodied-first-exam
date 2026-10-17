# Full-simulator table tennis: develop a program against L2

Win one complete match against the frozen sport's scripted L2 opponent, seed 22: the same frozen instance
as `roboolympics-tabletennis-match-i01-standard-realtime` (its standard-realtime twin; there you see only camera images).
The original Franka Panda, high-level actions, serve laws, limits, scoring and opponent are unchanged.
First to five, win by two from 4:4, cap seven. Full simulator development is allowed; no video is required.

## Development and deliverable
Use `from tools.tt_fullsim.session import Session`; `Session(level=2, seed=22)` gives `state()`, `world`,
`spec()`, `act(command)`, `step(n)`, `ready()` and `reset()`. The full simulator (source included) is at `/opt/fullsim`.
Reset rebuilds the WHOLE same-seed match at 0:0. You may inspect/modify private worlds and develop/search with
repeated resets within your agent resource and time limits. These changes never enter the formal match.
Read `/opt/fullsim/README.md` for the complete program API, observation fields, serving phases and game-time units.

Leave `/app/output/policy/program.py` and any helper/data files within that policy directory (512 regular files,
32 MiB total; no links/special files). Define `make_policy(config)` returning an object with `act(view)`.
The object persists for the full match. `view` contains `state`, full declared `truth`, `scores`, `observation`.
Return one original high action, `{"type":"ready"}` during a point's review, or `None`. Helpers in the policy
folder are importable. No model/API calls are available during formal evaluation. Submit executable policy code,
not a pre-recorded trajectory or a claimed score. Write a valid program early and update it as you improve.

## Formal evaluation
After development, a separate no-network verifier runs your final program as an unprivileged process against a
fresh unmodified original simulator. Your program may read a public read-only copy of the full simulator
(`/opt/dev`, the same files as `/opt/fullsim`) for its own predictions; it cannot read the trusted simulator, referee
or logs. Formal full-state snapshots are read-only values, not a mutable
world object. Formal reset and score rollback are not allowed. The original realtime clock runs at S=10 even
while your program computes; point reviews freeze the world under the existing rules. One response per observation,
one action at a time. See `config["spec"]` and the README for the policy execution, load, review and call limits.
The match ends as in `roboolympics-tabletennis-match-i01-standard-realtime`: when it is over, or at that task's cutoff (7200 s of wall
time), where an unfinished match is not won; a program error does not win either. The platform records the executed
actions and replays that trusted journal in a fresh process. Success requires a completed win,
valid original referee result and matching hashes/scores/steps/outcome. The generated trajectory is evidence,
not your submission. This fixed-instance result does not measure unseen-instance generalization.

## Strategy notes
Your serve begins with `waiting`, then `open`, then `tossed`. Toss only when `open`. There is a stationary
0.1 game-second pause before projection; contact the ball on its fall. Use `spec.serve` and the original action
schema for legality. Every control step is 0.01 game seconds; at S=10 that is 0.1 wall seconds.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **6 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
