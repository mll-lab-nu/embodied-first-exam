# Embodied Olympics · robot epee fencing, bout against level 2 (standard)

## Task
Win an epee bout to 15 touches against the scripted fencer.

## Goal
Success: you win the bout.

The bout is graded when your session ends: stay until it is over. If your session ends before the bout is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One bout, no reset: a touch against you stays.
- Use only the camera images, the service's replies and this text: no simulator internals or hidden state.
- Your chess clock: 60 minutes of real time, running only on your turn (thinking, tool calls, your programs and your
  reviews all count). If it runs out, you lose.
- After each of your actions (except one that ends the match) send `game ready "WHY" "PLAN"`, a short review, before the
  game goes on.
- You may write a program that observes, computes your next action and sends it; you stay in the loop (watch its log,
  stop, fix, restart). Only you send `game start` and `game ready`.

The bout (FIE direct elimination, no draws):
- The first to 15 touches wins. After 9 minutes of fencing time the fencer ahead wins; at equal scores one more minute
  is fenced and the first touch decides, else the fencer with priority (drawn by lot before that minute) wins.
- A touch is the point on the opponent's body (the epee itself is not a target); touches by both at almost the same
  moment are a double. A double counts for both, except at 14-14 (not counted) and in the extra minute (the scores stay
  equal).
- Unwillingness to fight: a minute of fencing time without a touch gives both fencers a P-red card (a penalty touch
  each) the first time, and the second time a P-black card to the lower score, who loses the bout (at equal scores: a
  seeded lot). No card at 14-14 or in the extra minute; the minute restarts after every touch, double and penalty touch,
  not after a phrase without a touch.

## Robot Interface
Two simulated Unitree G1 humanoids holding epees fence one bout, phrase by phrase: before each phrase each fencer
chooses one of nine tactical intentions, which the robots execute. You are seat `A` against a scripted fencer at level
2. It is turn-based: nothing moves while you think. The robot runs as a service you reach through its client or its MCP
tools, as if it were real hardware: one live episode.

### Client
The service at `http://localhost:8000` speaks eai-standard/2.x with the match extension (`eai-standard/2.1+match/1.0`;
docs/protocol/standard_mode.md Part 5): the endpoints of every standard task, plus `/start` and `/ready`. The shared
client is installed (`from rcb_client import Robot`).

| HTTP | |
| --- | --- |
| `GET /spec` | the standard spec (`cameras` with intrinsics and pose, `action_types` with each type's fields and row layout, `timing`) and, under `match`, everything `game spec` gives |
| `GET /status` | the state, no image |
| `POST /start {}` | you are ready; the match begins when every seat has started |
| `POST /observe {"cameras": [...]}` | the camera images of now, at once; no time passes (RCB1: `last/<camera>`, `frames/<camera>`, `view` = the tiled PNG of `game observe`) |
| `POST /submit {"type": T, "rows": [ACTION, ...]}` | your action for this turn (one row: the object of `game act`) |
| `POST /submit {"type": T, "interpolate": "hold", "seconds": S}` | waits up to S seconds of real time for your turn (as `game wait`) |
| `POST /ready {"why": "...", "plan": "..."}` | your review |

`/submit` takes one row: the action of your turn; an action the match refuses is a 400. Every answer's `meta` has
`score`, `review_due` (send `/ready` now), `match_over`, `step`, `phase` and your `state`. A `/submit` sent while the
world is frozen or before the start executes nothing (`ok: false`, `not_now`). After the match is over, every request
gets a 409. `/finish` and `/reset` are not offered (404): the match's rules end it, and there is one match.
`timing.deviations` in `/spec` lists what differs from the plain standard.

The same match also answers the `game` command, and the same calls as HTTP with JSON under
`http://localhost:8000/<SEAT>/` (your seat is `$SEAT`; the paths below are under it). You may use both:

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

Errors: 400 = an invalid action (nothing happens); 409 = not now (not your turn, or a review is due); 429 = one action
already in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from
your seat (empty body: retry more slowly).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `start`, `ready`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images are written as files under `/app/obs/` (`.png`, `.npy`) and the
  result lists them. There is no `finish` tool: the match's rules end it.
- `observe` returns at once; time passes only through `submit`; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets it pass (here: waits for your turn).
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client, the `game` command and the tools play the same seat in the same match; use any of them.

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

### Container
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Others
- Every phrase starts on guard; each fencer starts its intention after a short random delay, and which end of the piste
  each fences from is drawn per phrase (the two ends play slightly differently). A phrase ends at the first touch or
  after a few seconds without one, and its fencing time comes off the bout clock.
- The opponent chooses its intention before each phrase from what it has seen (both fencers' intentions and the
  results), never from your choice for this phrase; it knows the phrase table and predicts your next intention from your
  patterns.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and graded on what stands, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the clocks the service reports are the game's own. Calls
  into a long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 4 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one bout.
