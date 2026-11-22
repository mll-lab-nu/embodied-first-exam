# Embodied Olympics · robot epee fencing, bout against level 2 (standard-mcp)

## Task
Two simulated Unitree G1 humanoids holding epees fence one bout, phrase by phrase: before each phrase each fencer
chooses one of nine tactical intentions, which the robots execute. You are seat `A` against a scripted fencer at level
2. It is turn-based: nothing moves while you think. The robot runs as a service you reach only through the `efe-robot`
MCP tools, as if it were real hardware: one live episode.

## Goal
Success: you win the bout.

The bout is graded when your session ends: stay until it is over. If your session ends before the bout is over, or you
never called `start`, you lose.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One bout, no reset: a touch against you stays.
- No privileged state: use only the camera images, the tools' results and this text; no simulator internals or hidden
  state.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Your chess clock: 60 minutes of real time, running only on your turn (thinking, tool calls and your reviews all
  count). If it runs out, you lose.
- After each of your actions (except one that ends the match) call `ready(why, plan)`, a short review, before the game
  goes on.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

The bout (FIE direct elimination, no draws):
- Every phrase starts on guard. Each fencer has chosen one intention (lunge, low lunge, point in line, reactive line,
  stop-hit, counter-attack, delayed lunge, retreat, draw) and starts it after a short random delay, drawn for each
  fencer after both have chosen; which end of the piste each fences from is drawn per phrase (the two ends play slightly
  differently). The phrase ends at the first touch (the point on the opponent's body; the epee itself is not a target;
  touches by both at almost the same moment are a double) or after a few seconds without one, and takes its fencing time
  from the bout clock.
- The first to 15 touches wins. After 9 minutes of fencing time the fencer ahead wins; at equal scores one more minute
  is fenced and the first touch decides, else the fencer with priority (drawn by lot before that minute) wins. A double
  counts for both, except at 14-14 (not counted) and in the extra minute (the scores stay equal).
- Unwillingness to fight: a minute of fencing time without a touch gives, the first time, both fencers a P-red card (a
  penalty touch each), the second time the lower score a P-black card, who loses the bout (at equal scores: a seeded
  lot). No card at 14-14; the minute restarts after every touch, double and penalty touch, not after a phrase without a
  touch; it does not apply in the extra minute.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__act`):
- `spec()`: the actions (types, fields, ranges), the cameras (pose, field of view, size, `focal_px`,
  `principal_point_px`), the world frame, the rule constants, the phrase table; the whole spec also as a JSON file
  (`spec_file`).
- `status()`: the current state, no image.
- `start()`: you are ready; the match begins when every seat has started.
- `wait()`: blocks until it is your turn (or a review is due, or the match is over).
- `observe(query?, inline_tiles?)`: the state and the camera images as PNG files under `/app/obs/` (the view and one
  file per tile, native size; pixel coordinates in a tile are its camera's own); `inline_tiles` puts tiles in the
  result.
- `act(action)`: one action, an object with `type` and the fields `spec` lists for it, e.g.
  `act({"type": "phrase", ...})` (your intention for the next phrase).
- `ready(why, plan)`: your review (each at most 2000 characters).
- Every result is the service's reply (the state under `now` or `state`), plus `review_due` (call `ready` now) and
  `match_over`. A refused call returns the service's error (400 an invalid action, nothing happens; 409 not now); the
  tools keep to the service's request rate themselves. One call at a time; one still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`.

### Actions
- `phrase`: your intention for the next phrase, one of the nine (`act` with `{"type": "phrase", ...}`; `spec` lists the
  intentions and the fields).

### Observations
- The state: the score, the phrase number, the fencing time and the time left, the extra minute and the priority, the
  passivity minute and the cards, and every phrase so far (both intentions, both start delays, the result, its fencing
  time, the score after it, cards).
- The image: 2 rows (a side camera beside the piste, a top camera above it) × 2 columns (the last phrase half-way and at
  its end) of 800 × 360 tiles; your robot red, the opponent blue, the points yellow. Pinhole cameras (`spec` gives each
  one's pose, field of view, size, `focal_px` and `principal_point_px`): `u = cx + f · x_right / depth`,
  `v = cy - f · y_up / depth`.
- The phrase table (`spec` `phrase_table`): for every pair of intentions, how many of its 72 equally likely phrases (36
  pairs of delays × both ends of the piste) end with a touch for you, for the opponent, a double or none.

## Others
- The opponent chooses its intention before each phrase from what it has seen (both fencers' intentions and the
  results), never from your choice for this phrase; it knows the phrase table, predicts your next intention from your
  patterns, models how you read it, and now and then plays the table's equilibrium mix.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and graded on what stands, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the clocks the service reports are the game's own. Calls
  into a long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one bout.
