# Embodied Olympics · robot epee fencing, bout against level 2 (standard)

## Task
Two simulated Unitree G1 humanoids holding epees fence one bout, phrase by phrase: before each phrase each fencer
chooses one of nine tactical intentions, which the robots execute. You are seat `A` against a scripted fencer at level
2. It is turn-based: nothing moves while you think. The robot runs as a service you reach only through its client, as if
it were real hardware: one live episode.

## Goal
Success: you win the bout.

The bout is graded when your session ends: stay until it is over. If your session ends before the bout is over, or you
never sent `game start`, you lose.

Nothing to hand in: the service records and grades the episode. Keep your scripts, logs and notes in `/app/output/`.

Real-robot rules:
- One bout, no reset: a touch against you stays.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Your chess clock: 60 minutes of real time, running only on your turn (thinking, tool calls, your programs and your
  reviews all count). If it runs out, you lose.
- After each of your actions (except one that ends the match) send `game ready "WHY" "PLAN"`, a short review, before the
  game goes on.
- You may write a program that observes, computes your next action and sends it; you stay in the loop (watch its log,
  stop, fix, restart). Only you send `game start` and `game ready`.

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
### Client
The `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the rule constants, the phrase table |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait` | `POST /wait {"timeout_s": 60}` | blocks until it is your turn (or the match is over) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game phrase INTENTION` | `POST /act {"type": "phrase", ...}` | your intention for the next phrase (`game spec` lists the fields) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- `phrase`: your intention for the next phrase, one of the nine (`game phrase INTENTION`, or `game act` with
  `{"type": "phrase", ...}`; `game spec` lists the intentions and the fields).

### Observations
- The state: the score, the phrase number, the fencing time and the time left, the extra minute and the priority, the
  passivity minute and the cards, and every phrase so far (both intentions, both start delays, the result, its fencing
  time, the score after it, cards).
- The image: 2 rows (a side camera beside the piste, a top camera above it) × 2 columns (the last phrase half-way and at
  its end) of 800 × 360 tiles; your robot red, the opponent blue, the points yellow. Pinhole cameras (`game spec` gives
  each one's pose, field of view, size, `focal_px` and `principal_point_px`): `u = cx + f · x_right / depth`,
  `v = cy - f · y_up / depth`.
- The phrase table (`game spec` `phrase_table`): for every pair of intentions, how many of its 72 equally likely phrases
  (36 pairs of delays × both ends of the piste) end with a touch for you, for the opponent, a double or none.

### This run: privileged state queries
This run lets you query the simulator's state.

- `GET http://localhost:8000/$SEAT/state/entities` lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}, "note"?}}}`. The
  kinds are `robot` (your robot, and the opponent's when it is one), `robot_link` (your paddle, racket, rods or blade),
  `object` (the ball or the shuttle, the opponent's paddle, racket or blade, a scripted opponent that is only drawn),
  `articulation` (the opponent's rods) and `scene_feature` (the table, net, court, goals, playfield, piste and its
  lines); `note` says what an entity is. The list is fixed for the run.
- `POST http://localhost:8000/$SEAT/state/query` with `{"names": ["ball", ...], "fields": ["pos"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the current
  values from the simulator. `fields` is optional. The fields and their units are in the list: `pos` m, `quat`,
  `lin_vel` m/s, `ang_vel` rad/s, `joint_pos` / `joint_vel` / `joint_range` {joint: value}, `size` (the full extents
  along the body's own axes, m) and `bbox` (its axis-aligned box, `[[x, y, z] min, [x, y, z] max]`, m), all in the frame
  `frame` names (your own frame, as in the observation). An unknown name or field is a 400 that lists the valid ones.
- A phrase is fenced at once, inside the act that completes it; between phrases the fencers stand on guard, and a query
  gives that layout.
- A query only reads: no control step, the clock neither advances nor pauses (your turn's clock keeps running). It is
  served until the match is over (409 after). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: no answer holds the score, a point's result or the opponent's plan or strategy.

## Others
- The opponent chooses its intention before each phrase from what it has seen (both fencers' intentions and the
  results), never from your choice for this phrase; it knows the phrase table, predicts your next intention from your
  patterns, models how you read it, and now and then plays the table's equilibrium mix.
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one bout.
