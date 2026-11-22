# Embodied Olympics · robot badminton, match against level 5 (standard-mcp-shell)

## Task
Robot singles badminton on a small court (the BWF court's lengths × 0.4, the net at its full height): each player is a
Franka Panda arm with a racket, held to the real Panda's limits, on an x-y gantry base; the shuttle has the real
shuttle's high drag and does not bounce. Rally scoring, one game to 11 points; the players' robots serve. You are seat
`A` against a scripted opponent at level 5, a tier above the sport's levels 1-3 (Others). The world waits for you: it
advances only while you let it (Robot Interface, `### Time`). The robot runs as a service you reach through the
`efe-robot` MCP tools, their Python client `efe_robot` or the service's own client, as if it were real hardware: one
live episode.

## Goal
Success: you win the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Nothing to hand in: the service records and grades the episode. Keep your scripts, logs and notes in `/app/output/`.

Real-robot rules:
- One match, no reset: a point lost stays lost.
- No privileged state: use only the camera images, the service's replies and this text; no simulator internals or hidden
  state.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Reviews: after every point the world freezes; send `game ready "WHY" "PLAN"`, a short review, within 300 s of real
  time (`timing.review_timeout_s` in `game spec`), or your side loses the match (`ready_timeout`), even when you are
  ahead. The world does not go on by itself: watch for the freeze (your program's log, `game status`) and review at
  once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready` (or call `start` and `ready`).
- One route at a time: the tools, `efe_robot` and the service's client all drive the one robot.

The match (BWF Laws, with these changes):
- One game, rally scoring: the first to 11 points wins; from 10-10 a player must lead by 2, and at 14-14 the next point
  wins (at most 15). The match also ends after 400 hits (both sides) or 40 points played (lets included): then the
  player with more points wins, at equal points the player who won the last point that was not a let, and as a last
  resort the player who received first (here: the opponent). There are no draws.
- Play: there is no bounce: hit the shuttle before it reaches the floor. Your shot is good if your racket meets the
  shuttle once, on your half, and the shuttle passes over the net and lands in your opponent's singles court (lines are
  in); after your hit your racket no longer touches it. You lose the point if your shot goes into the net (crosses the
  net plane below the top), comes down on your own side or lands out, or if a shuttle that is yours to hit lands in your
  court; an opponent's shot that would land out of your court wins you the point, so you may let it go. Touching the net
  or reaching over it is not judged; a racket meets the shuttle only on its own half and only when it is that player's
  turn (no double hits).
- Serves: the winner of a rally serves the next point (after a let the same server; you serve the first point;
  `state.you_serve`, `state.serve`). Before every serve both robots are put at rest in the ready pose at their spots,
  diagonally opposite: in their right service courts when the server's score is even, else in their left ones (Robot
  Interface, `### Frame and court`); the spot is your base's home for the point, and after the serve there is no
  automatic return. The robot has no free hand: the server tosses the shuttle with `toss`.
- From 1 s after play resumes (the receiver is ready; `state.serve.phase` `open`) the server has 3 s to toss the shuttle
  and then hits it with the racket: the serve is good if the racket meets the shuttle below 1.15 m, the shuttle leaves
  the racket upwards, passes over the net and lands in the receiver's diagonally opposite service court (between its
  short service line and its back line, lines in) or is returned.
- It is the server's fault (the receiver's point) if it does not toss the shuttle in time (undue delay: every time,
  never a disqualification), misses the shuttle, hits it above 1.15 m or not upwards, or the serve hits the net or lands
  outside that court. Both bases must stay on their spots until the serve is hit (or faulted): a base that moves earlier
  is that player's fault (both at once: a let, replayed).

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__act`), also as Python functions: `import efe_robot`
(`/opt/tools/efe_robot.py`, on `PYTHONPATH`; each function has the tool's name, arguments and result, its docstring the
tool's description) or `python3 /opt/tools/efe_robot.py <tool> '<JSON arguments>'` from the shell. They carry the calls
of the `game` command (`### Client`).
- `spec()`: the actions (types, fields, ranges; `skill_contract`), the cameras (pose, field of view, size, `focal_px`,
  `principal_point_px`), the world frame, the limits, the rule constants, the timing; the whole spec also as a JSON file
  (`spec_file`).
- `status()`: the current state, no image.
- `start()`: you are ready; the match begins when every seat has started.
- `wait(seconds)`: let up to 10 game seconds pass in one call; it stops early when the world freezes for a review or the
  match ends.
- `observe(query?, inline_tiles?)`: the state and the camera images as PNG files under `/app/obs/` (the view and one
  file per tile, native size; pixel coordinates in a tile are its camera's own); `inline_tiles` puts tiles in the
  result.
- `act(action)`: one action, an object with `type` and the fields `spec` lists for it, e.g. `act({"type": "none"})`
  (cancel the stroke under way (the arm returns to its ready pose)).
- `ready(why, plan)`: your review (each at most 2000 characters).
- Every result is the service's reply (the state under `now` or `state`), plus `review_due` (call `ready` now) and
  `match_over`. A refused call returns the service's error (400 an invalid action, nothing happens; 409 not now); the
  tools keep to the service's request rate themselves. One call at a time (the Python functions wait for a pending call
  themselves); one still running after 45 s returns `{"pending": true, "operation": id}`: collect it with
  `wait(operation=id)`.

### Client
The `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

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

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- Your actions are the sport's skill API (`act`, `toss`, `move`, `none`) and the low level (`traj`): the platform
  executes each one, and `game spec` (`skill_contract`) says exactly what it delivers. An action takes effect
  `act.lead_steps` control steps after the step at which it arrives (`game spec`; the stroke is planned meanwhile);
  until then the robot keeps its current command.
- `act`: `{"type": "act", "t": T, "pos": [PX, PY, PZ], "normal": [NX, NY, NZ], "vel": [VX, VY, VZ]}`: the racket's state
  at contact, T s after the act takes effect: the head centre, the string-face normal and the head velocity (m/s).
  Limits: 0 < T <= 5, |x| <= 2.136, -3.68 <= y <= -0.3, 0.2 <= z <= 3.0, speed <= 8 m/s. It replaces the stroke under
  way. An act may carry `"base": [BX, BY]`, where the base stands at contact (default: the forehand stance for pos: (PX,
  PY) - 0.62 r (1, 1), r = max(0.30, 0.95 - 0.35 |PZ - 1.333|)); after a stroke the base stays where it struck (no
  automatic return).
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
- `toss`: `{"type": "toss", "pos": [X, Y, Z], "height": H}` tosses the shuttle for your serve: when the command takes
  effect the shuttle appears at that point (0.5 <= Z <= 1.8, within 1.0 m horizontally of your base, Y <= -0.5) and is
  released from rest (H = 0 or omitted) or rises H straight up (0 <= H <= 0.5) before it falls (until then it is held
  beside the server; no spin). Then hit it with an act, which you may send before the toss.
- `traj` (the low level): `{"type": "traj", "q": [[base_x, base_y, q1..q7], ...]}`: joint targets, one per 10 ms control
  step from the next step on (then the arm returns to its ready pose and the base holds its last target, or goes to the
  point of a `move`), each within the joint ranges and speed limits of `game spec` `joints`, the base's within the
  gantry's speed (2 m/s) and per-axis acceleration (15 m/s^2, from the targets' second differences), else refused; the
  arm's targets pass through the Panda's setpoint generator (acceleration and jerk limits: a target beyond them is
  reached later).
- Your robot: a Franka Panda arm held to the real Panda's limits (joint velocity 2.175 / 2.61 rad/s, acceleration 15 /
  7.5 / 10 / 12.5 / 15 / 20 / 20 rad/s^2, jerk, torque 87 / 12 N m, torque rate 1000 N m/s: `game spec` `arm_limits`) on
  a 1.0 m pedestal whose base rides a ball-screw gantry (|bx| <= 1.5, -3.53 <= by <= -0.5, up to 2 m/s and 15 m/s^2 per
  axis); it starts each point on the point's spot and then waits where you put it (`move`) or where it last struck. Its
  servo runs the arm at 0.9 of the velocity limits, and an arm joint faster than 1.05 × its limit triggers the robot's
  velocity reflex: it stops at that pose for 1 s (the gantry brakes to rest) and then resumes from rest, so the stroke
  under way is lost (`velocity_reflexes` in the final record). The racket head centre is 0.56 m beyond the flange; the
  string face is a disc of radius 0.14 m; the racket meets shuttles 0.4-2.5 m above the floor. From its ready pose
  (racket head 1.15 m high) a stroke is delivered reliably about 0.8-1 s ahead, and its head reaches about 2-2.3 m/s
  along a forward face normal.

### Observations
- `game observe`: a PNG of 2 rows × 4 columns of 480 × 360 tiles: row 1 a camera behind and above your base line looking
  down the court, row 2 a camera at the side of the court (x < 0) looking along +x (your half on the right); the columns
  are frames 60 ms apart, newest on the right, with each frame's step and game time (`view_steps`, `view_sim_times`). No
  shuttle coordinates: the shuttle is drawn enlarged, an orange cork (12 cm ball centred on its position) with a white
  skirt behind it.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`. Both cameras: 45 degree vertical field of view, focal
  length 434.6 px, principal point at the tile centre.
- The state: your robot (`robot_base_xy`, `q_arm`, `racket_pos`, `racket_normal`), what you heard (tosses, serves and
  hits, with their times), whether the shuttle is coming to you, and the serve: `you_serve`, `serve.court` (right or
  left), `serve.phase` (`waiting`: the receiver is getting ready; `open`: the server may toss; `tossed`; `done`: the
  serve was delivered), `serve.opens_in_s` and `serve.deadline_in_s` for the server, `serve.tossed_at_step`; a point
  lost by a service fault says `serve_fault:<reason>: ...` (undue_delay, missed, too_high, not_upwards, net, out,
  moved), the receiver's early move `receive_fault:moved: ...`.

### Frame and court
- Metres; your own frame: x to your right, y towards the opponent, z up; the floor z = 0. Your half is y < 0.
- The court (the BWF court's lengths × 0.4): singles court |x| <= 1.036, |y| <= 2.68 (lines in); the net is the plane y
  = 0 with its top at z = 1.524 (posts at x = ±1.22); short service lines at |y| = 0.792; the centre line x = 0 divides
  each half into a right and a left service court; the singles back line is also the long service line.
- The serve spots: x = +0.12 in the right service court or -0.12 in the left one, y = -1.6 (each player's own frame).

### Time
The world waits for you: it advances only during an open `game wait DT` (at most DT game seconds, then it stops again)
and, for an action you sent, up to the control step at which it takes effect (the step after the state it answers).
Between your calls it stands still: your thinking, your program's computation and the service's planning of an action
take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on; a match you leave
standing never ends, and it is lost when your session ends. `game spec` says so (`timing.clock` = `lockstep`). At the
end of every unit (a point; `game spec`) the world freezes for the reviews; the reviews' time limit and the start window
are real time. One action at a time per seat (429).

## Others
- The opponent, level 5 (`match.opponent_level` in `game spec`): the level 2 opponent (reach 0.85 m, level 2's attacks,
  0.25 s to spare on its shots except its kills) with a reaction of 0.22 s, level 3's walk back after its own stroke (2
  m/s instead of 0.6 m/s) and level 3's kills, in 90 % of its attacks. Like every level it predicts the shuttle's flight
  exactly; its base and arm obey the same limits as yours.
- The levels it is built from: it serves when it won the last rally, from its service court at 1.05 m, upwards, high and
  deep or short into your diagonal service court, at most 18 m/s, always within your reach (level 1: 70 % high serves,
  towards the middle of the court; levels 2-3: 50 % high, wider and closer to the short service line); it stands still
  in its service court while you serve. It never makes an unforced error: it returns every shuttle it can reach, into
  your court. It is a robot too, on a base with the same limits as yours: a reaction time after your hit it predicts the
  flight, its base moves until the shuttle is within its reach, and its arm then needs 0.55 s for a full stroke; with
  less than 0.3 s to spare it is under pressure (a weak, high lift into the middle of your court when hard pressed, a
  normal return in between, an attack when it has time); a shuttle it meets too late for a full stroke but with at least
  0.45 s of arm time it still blocks (a weak lift); later still beats it, and shuttles arriving fast press it too. Its
  shots leave a robot waiting in the middle of your court time to reach them (level 1: 0.45 s to spare, levels 2-3: 0.25
  s), except its kills: some of its attacks (level 1: 20 %, level 2: 50 %, level 3: 90 %) are played without that
  guarantee. It plays 70 % of its shots to the side away from your base, and when your base stands within 1.2 m of the
  net it lifts 70 % of its returns over your head (its clears pass above 2.8 m over your forward court). After its own
  stroke its base stays put for 0.35 s and then walks at 0.6 m/s to where it waits: 70 % of the way towards the mean
  landing point of your last 4 shots. It reads your habits: when 4 of your last 5 changes of side agree (always
  switching, or always staying) and your last 3 shots were all short or all deep, it predicts your next shot and moves
  90 % of the way there at full speed. So where you place the shuttle (away from it, and not in a pattern) and where
  your base waits both matter. Level 1: reaction 0.30 s, reach 0.85 m, mild attacks (smashes up to 15 m/s, 70 % of the
  court's width); level 2: reaction 0.25 s, reach 0.85 m, level 2's attacks (up to 17 m/s, the court's full width);
  level 3: as level 2 with a reaction of 0.20 s, a reach of 0.9 m and a fast walk back (2 m/s). Its shots leave its
  racket at most at 18 m/s.
- The shuttle: a point mass under gravity (9.81 m/s^2) and quadratic air drag, dv/dt = g - K |v| v with K = 0.212 per
  metre (terminal speed 6.8 m/s): hit at 40 m/s it slows to about 10 m/s within 0.3 s, and a high shuttle falls almost
  vertically at close to 6.8 m/s. No spin, no wind, no bounce.
- Racket contact: the racket meets the shuttle when the shuttle's centre crosses the string plane within 0.14 m of the
  head centre; the shuttle leaves exactly along the face normal n (the side the head moves towards, relative to the
  shuttle) at the speed 4 max(0, v_head·n) (1 - 0.3 (r/0.14)^2) + 0.15 max(0, -v_in·n), where v_head is the head
  velocity, r the contact's distance from the head centre and v_in the shuttle's incoming velocity; the rest of the head
  and incoming velocity is lost. A head speed along the normal of 1 m/s gives about 4 m/s, 2.5 m/s about 10 m/s (a
  lofted shot of 10 m/s flies about 4-5 m and 1.3-1.5 s).
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and graded on what stands, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the clocks the service reports are the game's own. Calls
  into a long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one match.
