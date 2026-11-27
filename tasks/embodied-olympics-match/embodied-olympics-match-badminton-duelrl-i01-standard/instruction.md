# Embodied Olympics · robot badminton, duel against the built-in RL player (standard)

## Task
Win a game of singles badminton to 11 points against the other robot.

## Goal
Success: you win the match against the built-in player.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One match, no reset: a point lost stays lost.
- Play from the camera images and the service's replies; do not use the simulator's state or the opponent's code to
  choose actions.
- Reviews: after every point the world freezes. Within 300 s of real time (`timing.review_timeout_s` in `game spec`),
  send a short review with `game ready "WHY" "PLAN"`; otherwise your side loses the match (`ready_timeout`), even when
  you are ahead. After a stoppage the world stays frozen until you send `game ready`: watch for the freeze (your
  program's log, `game status`) and review at once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The match (BWF Laws, with these changes):
- One game, rally scoring: the first to 11 points wins; from 10-10 a player must lead by 2, and at 14-14 the next point
  wins (at most 15).
- The match also ends after 400 hits (both sides) or 40 points played (lets included): then the player with more points
  wins, at equal points the player who won the last point that was not a let, and as a last resort the player who
  received first. There are no draws.
- Hit the shuttle once, on your half, before it reaches the floor, so that it passes over the net and lands in the
  opponent's singles court (lines are in).
- You lose the point if your shot goes into the net (below its top), comes down on your own side or lands out, or if a
  shuttle that is yours to hit lands in your court. An opponent's shot that would land out wins you the point, so you
  may let it go. Touching or reaching over the net is not judged.
- The winner of a rally serves the next point (after a let, the same server); `match.first_server` serves the first
  point. Before every serve both robots are put at rest on their serve spots, diagonally opposite: in their right
  service courts when the server's score is even, else in their left ones.
- The server has 3 s, starting 1 s after play resumes, to toss the shuttle (`toss`). Then it hits the shuttle below 1.15
  m, upwards, over the net into the receiver's diagonally opposite service court (between its short service line and its
  back line, lines in).
- A serve that breaks this is a fault and gives the receiver the point. The faults: a toss not made in time (a fault
  every time, never a disqualification), a miss, a hit above 1.15 m or not upwards, a serve into the net or outside that
  court.
- Both bases must stay on their spots until the serve is hit (or faulted). A base that moves earlier is that player's
  fault; if both move at once, it is a let and the point is replayed.

## Robot Interface
Robot singles badminton on a small court: the BWF court's lengths × 0.4, with the net at its full height. Each player is
a Franka Panda arm with a racket, held to the real Panda's limits, on an x-y gantry base. The shuttle has the real
shuttle's high drag and does not bounce. You are seat `A` against a built-in player (seat `B`) that runs inside the
simulator service. The world waits for you: it advances only while you let it (`### Time` below). The robot runs as a
service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

### Client
The service at `http://localhost:8000` speaks eai-standard/2.x with the match extension (`eai-standard/2.1+match/1.0`): the endpoints
of every standard task, plus `/start` and `/ready`. The shared client is installed (`from rcb_client import Robot`).

| HTTP | |
| --- | --- |
| `GET /spec` | the standard spec (`cameras` with intrinsics and pose, `action_types` with each type's fields and row layout, `timing`) and, under `match`, everything `game spec` gives |
| `GET /status` | the state, no image |
| `POST /start {}` | you are ready; the match begins when every seat has started |
| `POST /observe {"cameras": [...]}` | the camera images of now, at once; no time passes (RCB1: `last/<camera>`, `frames/<camera>`, `view` = the tiled PNG of `game observe`) |
| `POST /submit {"type": T, "rows": [ACTION, ...], "dt": DT}` | your actions (the objects of `game act`), one after the other, each followed by DT of game time |
| `POST /submit {"type": T, "interpolate": "hold", "seconds": S}` | lets S seconds of game time pass with your last actions in force (as `game wait S`) |
| `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

`/submit` returns after its last row: each row takes effect at the current step, then the world advances DT (default:
one control step). An action the match refuses is a 400 (a later row's: `code` 400 in `meta.effects`). Where an action
names a robot (`entity`), one chunk commands one: `"entity": E` in the chunk, or the type `T@E`. Every answer's `meta`
has `score`, `review_due` (send `/ready` now), `match_over`, `step`, `phase` and your `state`. A `/submit` while the
world is frozen or before the start executes nothing (`ok: false`, `not_now`); after the match is over requests are a
409. `/finish` and `/reset` are not offered (404): the match's rules end it, and there is one match. What differs from
the plain standard: `timing.deviations` in `/spec`.

The same match also answers the `game` command, or the same calls as HTTP with JSON under
`http://localhost:8000/<SEAT>/` (the paths below are under it; your seat is `$SEAT`); you may use both:

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges; `skill_contract`), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the limits, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game none` | `POST /act {"type": "none"}` | cancel the stroke under way (the arm returns to its ready pose) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens); 409 = not now (not your turn, or a review is due); 429 = one action
already in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from
your seat (empty body: retry more slowly).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `start`, `ready`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images are written as files under `/app/obs/` (`.png`, `.npy`) and the
  result lists them. There is no `finish` tool: the match's rules end it.
- `observe` returns at once; time passes only through `submit`; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets it pass.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client, the `game` command and the tools play the same seat in the same match; use any of them.

### Actions
- Your actions are the sport's skill API (`act`, `toss`, `move`, `none`) and the low level (`traj`): the platform
  executes each one, and `game spec` (`skill_contract`) says exactly what it delivers. An action takes effect
  `act.lead_steps` control steps after the step at which it arrives (`game spec`; the stroke is planned meanwhile);
  until then the robot keeps its current command.
- `act`: `{"type": "act", "t": T, "pos": [PX, PY, PZ], "normal": [NX, NY, NZ], "vel": [VX, VY, VZ]}`: the racket's state
  at contact, T s after the act takes effect: the head centre, the string-face normal and the head velocity (m/s).
  Limits: 0 < T <= 5, |x| <= 2.136, -3.68 <= y <= -0.3, 0.2 <= z <= 3.0, speed <= 8 m/s. It replaces the stroke under
  way. An act may carry `"base": [BX, BY]`, where the base stands at contact. By default the base takes the forehand
  stance for pos: (PX, PY) - 0.62 r (1, 1), with r = max(0.30, 0.95 - 0.35 |PZ - 1.333|). After a stroke the base stays
  where it struck (no automatic return).
- The stroke controller drives the base to stand for a forehand at the contact point (or as far as it gets in time) and
  swings the arm within the joint speed and acceleration limits (a slower head when the time left does not allow the
  commanded one; the reply's stroke notes say so, and `state.command` gives the rehearsal's head velocity
  `vel_rehearsed` and position error `pos_error_rehearsed_m`); it knows nothing about the shuttle. The arm and racket
  cannot pass through the robot's own pedestal, platform and links (they stop the arm): the controller takes a swing
  that its rehearsal finds clear of them when it can (else the stroke notes say self-collision). The delivered state
  scatters by about 6 mm, 0.8 degrees and 3 % (seeded; your own stream, independent of the opponent's).
- `none`: `{"type": "none"}` cancels the stroke (the arm returns to its ready pose, the base stays where it is).
- `move`: `{"type": "move", "base": [BX, BY]}` sets where the base waits (it goes there once no stroke is under way;
  until a serve is delivered both bases must stay on their spots).
- `toss`: `{"type": "toss", "pos": [X, Y, Z], "height": H}` tosses the shuttle for your serve. When the command takes
  effect, the shuttle appears at that point (0.5 <= Z <= 1.8, within 1.0 m horizontally of your base, Y <= -0.5). It is
  released from rest (H = 0 or omitted) or rises H straight up (0 <= H <= 0.5) before it falls, with no spin; until then
  it is held beside the server. Then hit it with an act, which you may send before the toss.
- `traj` (the low level): `{"type": "traj", "q": [[base_x, base_y, q1..q7], ...]}`: joint targets, one per 10 ms control
  step from the next step on. After the last row the arm returns to its ready pose, and the base holds its last target
  or goes to the point of a `move`. Each target must be within the joint ranges and speed limits of `game spec`
  `joints`, and the base's within the gantry's speed (2 m/s) and per-axis acceleration (15 m/s^2, from the targets'
  second differences); otherwise the action is refused. The arm's targets pass through the Panda's setpoint generator,
  which has acceleration and jerk limits: a target beyond them is reached later.
- Your robot: a Franka Panda arm held to the real Panda's limits (joint velocity 2.175 / 2.61 rad/s, acceleration 15 /
  7.5 / 10 / 12.5 / 15 / 20 / 20 rad/s^2, jerk, torque 87 / 12 N m, torque rate 1000 N m/s: `game spec` `arm_limits`) on
  a 1.0 m pedestal whose base rides a ball-screw gantry (|bx| <= 1.5, -3.53 <= by <= -0.5, up to 2 m/s and 15 m/s^2 per
  axis); it starts each point on the point's spot and then waits where you put it (`move`) or where it last struck. Its
  servo runs the arm at 0.9 of the velocity limits. An arm joint faster than 1.05 × its limit triggers the robot's
  velocity reflex: the robot stops at that pose for 1 s (the gantry brakes to rest), then resumes from rest, and the
  stroke under way is lost (`velocity_reflexes` in the final record). The racket head centre is 0.56 m beyond the
  flange; the string face is a disc of radius 0.14 m; the racket meets shuttles 0.4-2.5 m above the floor. From its
  ready pose (racket head 1.15 m high) a stroke is delivered reliably about 0.8-1 s ahead, and its head reaches about
  2-2.3 m/s along a forward face normal.

### Observations
- `game observe`: a PNG of 480 × 360 tiles in 2 rows × 4 columns. Row 1 is a camera behind and above your base line,
  looking down the court; row 2 is a camera at the side of the court (x < 0), looking along +x (your half on the right).
  The columns are frames 60 ms apart, newest on the right, each with its step and game time (`view_steps`,
  `view_sim_times`). No shuttle coordinates: the shuttle is drawn enlarged, an orange cork (12 cm ball centred on its
  position) with a white skirt behind it.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`. Both cameras: 45 degree vertical field of view, focal
  length 434.6 px, principal point at the tile centre.
- The state: your robot (`robot_base_xy`, `q_arm`, `racket_pos`, `racket_normal`), what you heard (tosses, serves and
  hits, with their times), whether the shuttle is coming to you, and the serve: `you_serve`, `serve.court` (right or
  left), `serve.phase` (`waiting`: the receiver is getting ready; `open`: the server may toss; `tossed`; `done`: the
  serve was delivered), `serve.opens_in_s` and `serve.deadline_in_s` for the server, and `serve.tossed_at_step`. A point
  lost by a service fault says `serve_fault:<reason>: ...` (undue_delay, missed, too_high, not_upwards, net, out,
  moved); a point lost by the receiver's early move says `receive_fault:moved: ...`.

### Frame and court
- Metres; your own frame: x to your right, y towards the opponent, z up; the floor z = 0. Your half is y < 0.
- The court (the BWF court's lengths × 0.4): singles court |x| <= 1.036, |y| <= 2.68 (lines in); the net is the plane y
  = 0 with its top at z = 1.524 (posts at x = ±1.22); short service lines at |y| = 0.792; the centre line x = 0 divides
  each half into a right and a left service court; the singles back line is also the long service line.
- The serve spots: x = +0.12 in the right service court or -0.12 in the left one, y = -1.6 (each player's own frame).

### Time
The world waits for you. It advances only during an open `game wait DT` (at most DT game seconds, then it stops again),
and, after you send an action, up to the control step at which that action takes effect (the step after the state it
answers). Between your calls the world stands still: your thinking, your program's computation and the service's
planning of an action take no game time. So a program has to keep calling `game wait` (or acting) for the match to go
on. A match you leave standing never ends, and you lose it when your session ends. `game spec` says so (`timing.clock` =
`lockstep`). At the end of every unit (a point; `game spec`) the world freezes for the reviews; the reviews' time limit
and the start window are real time. One action at a time per seat (429).

### Physics
- The shuttle: a point mass under gravity (9.81 m/s^2) and quadratic air drag, dv/dt = g - K |v| v with K = 0.212 per
  metre (terminal speed 6.8 m/s): hit at 40 m/s it slows to about 10 m/s within 0.3 s, and a high shuttle falls almost
  vertically at close to 6.8 m/s. No spin, no wind, no bounce.
- Racket contact: the racket meets the shuttle when the shuttle's centre crosses the string plane within 0.14 m of the
  head centre. The shuttle leaves exactly along the face normal n (pointing to the side the head moves towards, relative
  to the shuttle) at the speed 4 max(0, v_head·n) (1 - 0.3 (r/0.14)^2) + 0.15 max(0, -v_in·n). Here v_head is the head
  velocity, r the contact's distance from the head centre and v_in the shuttle's incoming velocity. The rest of the head
  and incoming velocity is lost. A head speed of 1 m/s along the normal gives a shuttle speed of about 4 m/s, and 2.5
  m/s gives about 10 m/s. A lofted shot at 10 m/s flies about 4-5 m in 1.3-1.5 s.

### Container
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Others
- The other robot is the built-in player: the same robot, limits and rules as yours, but it reads the true shuttle state
  and your base position (never shown to you) instead of the cameras and picks its shots with a learned policy.

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
- Resets: none. You get one match.
