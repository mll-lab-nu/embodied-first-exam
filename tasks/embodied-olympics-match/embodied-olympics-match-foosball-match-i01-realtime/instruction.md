# Embodied Olympics · foosball, game against level 3 (realtime)

## Task
Win a game of foosball to 5 goals against the computer team.

## Goal
Success: you win the game.

The game is graded when your session ends: stay until it is over. If your session ends before the game is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One game, no reset: a goal against you stays.
- Play from the camera images and the service's replies; do not use the simulator's state or the opponent's code to
  choose actions.
- Reviews: after every rally the world freezes; send `game ready "WHY" "PLAN"`, a short review, within 300 s of real
  time (`timing.review_timeout_s` in `game spec`), or your side loses the match (`ready_timeout`), even when you are
  ahead. After a stoppage the world stays frozen until you send `game ready`: watch for the freeze (your program's log,
  `game status`) and review at once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The game (ITSF rules, with these changes):
- One game: the first to 5 goals wins. The game also ends after 240 s of play (frozen time does not count) or 40
  rallies: then the player with more goals wins, at equal goals the player who scored the last goal, if nobody has
  scored the player with the ball less time in its own half, and as a last resort the player who did not have the first
  kick-off. There are no draws.
- A goal: the ball wholly over the goal line scores 1 point for the other team, whoever touched it last.
- Possession: a rod may keep the ball within its reach for at most 15 s (the goalie rod: goalkeeper rod and 2-rod
  together), 10 s (5-rod) or 15 s (3-rod); its clock restarts when the ball leaves its reach and already runs during the
  opening sequence.
- Kick-off: before the ball may leave the restart rod (the 5-rod, or the goalkeeper rod and 2-rod together), complete
  the opening sequence: a move by one figure, a contact by another figure, then a contact by any figure other than that
  second one (`restart.opening_complete` in the state).
- Spinning: a rod that turned more than a full turn before or after its contact makes the ball's transition a foul, and
  a goal scored that way does not count (the rods' stops make a full turn impossible).
- A foul (possession time, incomplete opening, spinning) gives the opponent the ball on its 5-rod (after a 3-rod
  possession foul: on its goalie rod), never a point.

## Robot Interface
Table football on a physical table: you drive the four motorised rods of one team (the goalkeeper rod with 3 figures,
the 2-rod with 2, the 5-rod with 5, the 3-rod with 3) by slide and angle targets that the motors follow along a speed-
and acceleration-limited path, and you see the table only through an overhead camera. You are seat `A` (blue) against a
scripted computer team (red) at level 3. The world runs at 1/S of real speed (S = 20). The robot runs as a service you
reach through its client or its MCP tools, as if it were real hardware, on a clock that does not stop while you think:
one live episode.

### Client
The service at `http://localhost:8000` speaks eai-standard/2.x with the match extension (`eai-standard/2.3+match/1.0`): the endpoints
of every standard task, plus `/start` and `/ready`. The shared client is installed (`from rcb_client import Robot`).

| HTTP | |
| --- | --- |
| `GET /spec` | the standard spec (`cameras` with intrinsics and pose, `action_types` with each type's fields and row layout, `timing`) and, under `match`, everything `game spec` gives |
| `GET /status` | the state, no image |
| `POST /start {}` | you are ready; the match begins when every seat has started |
| `POST /observe {"cameras": [...]}` | the camera images of now, at once; no time passes (RCB1: `last/<camera>`, `frames/<camera>`, `view` = the tiled PNG of `game observe`) |
| `POST /submit {"type": T, "rows": [ACTION, ...], "dt": DT, "at": STEP}` | your actions (the objects of `game act`), a plan: row i at control step `at` + i × DT / control step |
| `POST /submit {"type": T, "interpolate": "hold", "seconds": S}` | no new action for S seconds: what was planned for that robot from now on is dropped, and its last action stays in force |
| `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

`/submit` answers at once. `at` (default: the current step, `meta.step`) and DT (default: one control step) place the
rows; a new chunk replaces what was planned for the same robot from `at` on, and rows whose step has passed are dropped
(`meta.late_rows`). Each row is sent to the match at its step and takes effect like a `game act`; the next answers list
each row's `effect_step` in `meta.effects` (a row the match refuses: `code` 400 there). The last action stays in force
(no interpolation between rows). The plan is cleared when the world freezes. Where an action names a robot (`entity`),
one chunk commands one: `"entity": E` in the chunk, or the type `T@E`. Every answer's `meta` has `score`, `review_due`
(send `/ready` now), `match_over`, `step`, `phase` and your `state`. A `/submit` while the world is frozen or before the
start executes nothing (`ok: false`, `not_now`); after the match is over requests are a 409. `/finish` and `/reset` are
not offered (404): the match's rules end it, and there is one match. What differs from the plain standard:
`timing.deviations` in `/spec`.

The same match also answers the `game` command, or the same calls as HTTP with JSON under
`http://localhost:8000/<SEAT>/` (the paths below are under it; your seat is `$SEAT`); you may use both:

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the limits, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens); 409 = not now (not your turn, or a review is due); 429 = one action
already in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from
your seat (empty body: retry more slowly). Acts are never out of turn: one in flight per seat (it may address several
rods).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `start`, `ready`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images are written as files under `/app/obs/` (`.png`, `.npy`) and the
  result lists them. There is no `finish` tool: the match's rules end it.
- `observe` returns at once; `submit` answers at once, as the endpoint does.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client, the `game` command and the tools play the same seat in the same match; use any of them.

### Actions
- `rods`:
  `game act '{"type": "rods", "rods": {"midfield": {"slide": 0.03, "angle": 1.1, "omega": 40}, "goalie": {"slide": -0.05}}}'`
  (`POST /act` with that body; `"type"` may be left out): new targets for any of your rods goalie, defence (2-rod),
  midfield (5-rod) and attack (3-rod); rods you do not name keep their targets. slide (m) moves the rod along your local
  v (0 = centre; within ±0.11 goalie, ±0.19 defence, ±0.06 midfield, ±0.11 attack); angle (rad) turns it (0 = figures
  hanging straight down, + = feet swing towards the opponent's goal, up to ±2.6; 1.5 is about level, so a ball passes
  underneath); optional omega (rad/s, at most 52) and speed (m/s, at most 2.0) cap the rod's angular and sliding speed
  for this target. Each rod follows a smooth path to the target (sliding at most 2.0 m/s and 40 m/s^2, turning at most
  52 rad/s and 4000 rad/s^2) with limited force (60 N) and torque (5 N m); the rod itself never moves faster than 2.0
  m/s or 52 rad/s, not even when the ball pushes it: a rod the ball held up catches up with its path at these speeds at
  most; an action takes effect 2 control steps (20 ms of game time) after it arrives: it reaches the motors 2 control
  steps after the control step that takes it (the reply's `took_effect`: `taken_step`, `effect_step` = `taken_step` +
  2), and holds until replaced; the rods cannot make a full turn (stops at ±2.8 rad). Out of range: HTTP 400.

### Observations
- The state: your own rods (slide, angle, their velocities and the command at the motors), the score, fouls, the time of
  play and of the rally, the play time left, the referee's restart (which team and rod puts the ball into play, whether
  its opening sequence is complete) and the rallies that ended (last_rally, rallies: how, who scored or fouled, the
  restart); no ball or opponent coordinates. The image: one 384 × 240 RGB tile from the fixed overhead camera straight
  above the table centre at 1.45 m (32 degree vertical field of view; `game spec` camera / cameras), turned so that your
  own goal is on the left and the image's right and up are your local +u and +v. The ball is orange, seat A's figures
  blue, seat B's red, the rods grey; figures and rods can hide the ball.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`.

### Frame and table
- Metres, seconds. World frame: x along the table (seat A's goal at x = -0.60, seat B's at x = +0.60), y across, z up,
  playfield z = 0 with its centre at (0, 0). Your local frame (the image, your rods, `game spec` geometry): u towards
  the opponent's goal, v to the left when you look along u (seat A: u = x, v = y; seat B: u = -x, v = -y).
- Playfield 1.20 × 0.68 m between side walls with rounded fillets (radius 0.02 m), goal mouths 0.20 m wide; ball radius
  0.0175 m, 24 g, it rolls with little resistance (about 0.1 m/s^2), bounces off the walls and is stopped by a figure it
  runs into; a kick sends it off at about the foot's speed, at an angle when the foot hits it off centre. Rods 0.09 m
  above the playfield at u = -0.525 (your goalkeeper rod), -0.375 (2-rod), -0.075 (5-rod), 0.225 (3-rod), the opponent's
  at the negated u; figures at slide 0 (v): goalkeeper and 3-rod -0.20, 0, 0.20; 2-rod -0.12, 0.12; 5-rod -0.24, -0.12,
  0, 0.12, 0.24; a foot is a capsule along u (radius 0.012 m, half length 0.014 m) 0.075 m below the rod. Physics 1000
  Hz, control 100 Hz (10 ms steps); a transparent cover 4 cm above the playfield normally keeps the ball on the table.

### Time
The world runs on its own clock at 1/S of real speed, S = 20 (`timing.slowdown` in `game spec`): it never waits for you,
so your thinking and your program's computation cost game time. At the end of every unit (a rally; `game spec`) the
world freezes for the reviews.

### Physics
- A full-speed kick sends the ball off at about 4-5 m/s (at most about 5.4 m/s).

### Container
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Others
- Every goal, foul, dead ball or ball off the table ends a rally: the world freezes for the reviews, every rod returns
  to slide 0, angle 0, and the next rally starts with a restart. The world is not frozen during the opening sequence.
- The first kick-off is `match.first_kickoff`'s (`game spec`); after a goal the team that conceded kicks off.
- Dead ball: a ball at rest for 1 s that no rod can reach is put back into play, between the two 5-rods by a kick-off
  (by the team that conceded the last goal, else the first kick-off's team), behind a 5-rod by the goalie rod of that
  half. A ball off the table goes to the goalie rod of the team that did not touch it last.
- Not judged: the passing and wall rules, playing the ball dead, delay of game; no warnings, penalty shots or time-outs.
- The computer team (red, level 3 of 4) plays on the true ball position a short reaction delay ago and never reads your
  commands; its rods have the same top speeds as yours, and it shoots from every rod, passes and aims past your figures.

## Limits
- Time: 14400 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning and graded on the state at that moment, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). The clocks the service reports are the game's own. A
  call into a long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Going over a cap can get a process killed (the CPU
  cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none: one game.
