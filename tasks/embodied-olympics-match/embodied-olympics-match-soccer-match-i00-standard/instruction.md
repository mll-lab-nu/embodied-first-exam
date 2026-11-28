# Embodied Olympics · robot soccer 2 v 2, match against level 2 (standard)

## Task
Win a 2 v 2 robot soccer match against the other team.

## Goal
Success: your team wins the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One match, no reset: a goal against you stays.
- Play from the camera images and the service's replies; do not use the simulator's state or the opponent's code to
  choose actions.
- Reviews: at every stoppage (a goal, half time, a dropped ball, full time, each shoot-out kick) the world freezes; send
  `game ready "WHY" "PLAN"`, a short review, within 600 s of real time (`timing.review_timeout_s` in `game spec`), or
  your side loses the match (`ready_timeout`), even when you are ahead. After a stoppage the world stays frozen until
  you send `game ready`: watch for the freeze (your program's log, `game status`) and review at once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The match (RoboCup Humanoid Soccer League rules, with these changes):
- Two halves of 5 minutes of game time (a half runs on for up to 3 s while the ball is still moving); more goals after
  two halves wins, or a 10-goal lead at any time (the mercy rule). No change of ends (each team's frame stays), no
  timeouts, no designated goalkeeper, no substitutes.
- If the score is level after two halves, there is a penalty shoot-out of 3 kicks each. Then come up to 3 sudden-death
  rounds, each won by the better kick (goal, saved, post, wide, other, no kick), and then a coin toss drawn from the
  seed. There are no draws.
- In the shoot-out the team that kicked off first shoots first. The strikers are robot 1, 2, 1, and the keeper is the
  other team's robot with the same number. Each team shoots at the goal it attacks. The striker has 20 s to touch the
  ball. A keeper more than 0.6 m from its goal line before the touch concedes a goal.
- After a kick-off the ball is in play once it has moved 0.15 m, or 10 s after play resumes. The kick-off team must
  touch it outside the centre circle before it can score; otherwise there is no goal, and the other team kicks off.

## Robot Interface
Robot soccer 2 v 2: four simulated Booster T1 humanoids (lower bodies on a walking policy, held to the real robot's
joint limits) and one ball on a boarded 10 × 7 m pitch with two goals. Each robot takes a walk velocity command, stand
or a kick, and you see the game only through your robots' head cameras. You are seat `A` and command both robots of team
A (blue) against a scripted team B (red) at level 2. The world waits for you: it advances only while you let it
(`### Time` below). The robot runs as a service you reach through its client or its MCP tools, as if it were real
hardware: one live episode.

### Client
The service at `http://localhost:8000` speaks eai-standard/3.0 with the match extension: the endpoints
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
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the limits, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
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
- Per robot (`entity` = its number): walk v = [vx, vy, wz] (the walking controller's body-frame velocity command, each
  in [-1, 1] m/s, m/s, rad/s; the command the controller sees moves toward yours by at most 2 m/s^2, 2 m/s^2, 4 rad/s^2
  (the robot's state shows it as command.walk_now); the robot reaches about 0.75 of a forward command; held until the
  next command), stand, kick (power in [0, 1], default 1; aim in [-0.6, 0.6] rad, default 0: up to 0.6 rad away from the
  support foot's side (right foot: to the right, left foot: to the left), up to 0.3 rad across it (larger values across
  are clipped); foot right (default) or left; style swing (default), step or push; optional at = [t, x, y]: the timed
  kick, below; optional v for step).
- Swing: the swing kick of the chosen leg (right by default) from a standing stance: the walking controller first stops
  the robot and the kick waits for the ball to roll slower than 0.15 m/s (if either takes longer than 1 s the kick is
  called off and the robot stands; your events then show kick_cancelled with the reason), then the kick shifts the
  weight onto the other foot, winds the kicking foot back and swings it through the ball as it lies when the kick starts
  (control authority: the kick reads the ball's position once, when it starts, and moves the foot's path onto it by at
  most 0.08 m sideways, the strike point clipped to 0.05-0.32 m beyond the support foot's toe line and 0.03-0.12 m high;
  it never follows a rolling ball, predicts or chooses a direction), along the robot's heading turned by aim (+ = left),
  returns to the standing pose and steps in place; the ball is hit about 2.4-2.9 s after the command and the kick ends
  after about 4.7-5.6 s; it hits the ball well only if the ball's centre lies 0.26-0.38 m ahead of the trunk and
  0.02-0.10 m to the kicking foot's side (right foot: to the right; left foot: to the left) when the kick starts (a ball
  farther out may be hit badly and the foot may land on it); power sets the swing's speed: a clean hit sends the ball
  off at about 1.2 m/s at power 0 to 4.3 m/s at power 1 and it rolls on at about 0.8, 1.0, 1.8, 2.45 and 2.8 m/s at
  power 0, 0.25, 0.5, 0.75 and 1 (about 0.6, 1.0, 3.1, 5.8 and 7.5 m).
- Step: the in-walk kick: the robot walks on with v (default: the walk under way, else [0.3, 0, 0]) and the first
  lift-off of the kicking foot with the ball 0.16-0.40 m ahead of the support foot and within 0.08 m of the kicking
  foot's line (about 0.16 m to that side of the trunk) starts the kick: the walking controller keeps the support leg and
  the balance, the kicking foot winds back (0.08 s), swings through the ball as it lies then (2.4 + 1.6 power m/s
  nominal foot speed, along the heading turned by aim) and comes back to a short step (0.08 s), then the controller puts
  it down and steps to a stop (0.6 s); contact typically 0.5-1.5 s after the command; the ball leaves at about 2.7-3.9
  m/s and rolls on at about 1.6-2.6 m/s (power 0-1); if no step reaches the ball within 2 s the kick is called off
  (kick_cancelled); the same control authority as the swing (the ball read once when the swing is planned, the path
  moved onto it by at most 0.08 m sideways).
- Push: the toe-poke run-up (stand 0.5 s, walk straight at 0.6 + 0.4 power m/s holding the heading until a foot is past
  the ball's centre, at most 2.64 m, stand 0.5 s; best with the ball 0.90-1.05 m ahead and 0.10-0.20 m to the right;
  about 1.3 m/s, never falls; aim does nothing).
- Wider aims: the ball must lie where the swing's line passes for that aim (robot.strike_zone.swing_by_aim: ahead and
  left of the trunk per aim, right foot; the left foot mirrored); the ball leaves 0.05-0.15 rad less wide than aimed at
  the widest aims.
- Timed kick (at = [t, x, y], swing only): you say where the ball's centre will be (x, y in your frame) and when (t s
  from now, at most 6); the kick does not wait for a still ball and never reads the ball: the robot stops, prepares as
  for every swing (about 2.6 s) and keeps the foot wound up until the swing must start so that the strike point meets
  (x, y) at t (if t is shorter than the preparation, it strikes as soon as it can and your events show kick_late with
  the delay); sending the same kick again (same foot and aim) before the swing starts only moves t and (x, y) (no new
  preparation, the robot's state shows command.at as now planned; the foot stands on one leg while it waits: an update
  that moves the point by more than a few centimetres jerks the foot and can unbalance the robot); a rolling ball
  arriving from the front half is struck as by a still one (a ball crossing the swing leaves turned by its own sideways
  speed: about 0.3-0.6 rad per m/s).
- A robot can fall during a swing kick (the kick ends; it is stood up 3 s later).
- A command takes effect at the next 20 ms control step and replaces the one under way (also a kick); one act per robot
  in flight; a command for a penalized or fallen robot is refused (HTTP 409).

### Observations
- Per own robot one head-camera tile (480 × 360, 80 degree vertical field of view, tile robotN; during a review the
  frame before the stoppage); its own state (pose: exact self-localization in your frame, velocity, IMU, trunk height,
  joints, fallen, penalized, command); the referee's information (score, period, clock, kick-off, every robot's penalty,
  the shoot-out) and its events of the current unit (goals, penalties, stoppages; falls and called-off kicks only of
  your own robots); no ball or opponent coordinates.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`.

### Frame and pitch
- Metres, seconds; your team's frame: you attack the goal at x = +5 and defend the goal at x = -5, y to the left when
  facing +x, z up, yaw counter-clockwise from +x (both teams see the pitch this way in their own frame).
- Field of play 10 × 7 m (|x| <= 5, |y| <= 3.5), halfway line x = 0, centre circle radius 1.0 m, penalty areas 2.0 m
  deep and 4.0 m wide, goal areas 1.0 × 3.0 m, penalty marks 1.5 m in front of each goal line; boards 0.3 m high on the
  touchlines and goal lines except the goal mouths; goals 2.6 m wide (|y| < 1.3), 1.8 m high, 0.6 m deep with nets.

### Time
The world waits for you. It advances only during an open `game wait DT` (at most DT game seconds, then it stops again),
and, after you send an action, up to the control step at which that action takes effect (the step after the state it
answers). Between your calls the world stands still: your thinking, your program's computation and the service's
planning of an action take no game time. So a program has to keep calling `game wait` (or acting) for the match to go
on. A match you leave standing never ends, and you lose it when your session ends. `game spec` says so (`timing.clock` =
`lockstep`). At the end of every unit (a point, a goal or another stoppage; `game spec`) the world freezes for the
reviews; the reviews' time limit is real time.

### Kick-off
- Kick-off positions, in your frame: when you kick off, your robot 1 stands at about (-0.32, 0.06), facing +x behind the
  ball on the centre mark (the ball in its swing zone), and robot 2 at about (-2.5, -1.5). When the opponents kick off,
  your robots stand at about (-1.6, 0.4) and (-3.6, -0.8). Each position can be up to 0.3 m off (seeded).

### Physics
- The ball: radius 0.11 m, 0.45 kg, orange, a thin shell. On the turf it rolls with a deceleration of about 0.52 m/s^2
  (a kicked ball first skids and loses about 2/5 of its speed). It bounces: a 2 m drop rebounds about 0.8 m, and it
  comes off a post or a board at about 0.7 of its speed. A rolling ball that runs into a standing robot's legs mostly
  stops at its feet (its spin takes the rebound).
- The robots: Booster T1 lower bodies (legs and trunk, no arms), trunk about 0.68 m above the floor, head camera about
  1.0 m (it sees the floor from about 0.55 m ahead of the trunk on: a ball at your feet is out of view); held to the
  real T1's leg limits (motor torques 45 / 30 / 30 / 60 / 24 / 15 N m for hip pitch / roll / yaw, knee, ankle pitch /
  roll, a torque-speed envelope at the joint speed limits 12.5 / 10.9 / 10.9 / 11.7 / 18.8 / 12.4 rad/s, a rated
  (continuous) torque of 60 % of those torques: a motor held near its peak for more than about 5 s folds back to it
  (thermal), a 1 kW bus per robot, a walking-command rate limit); team A wears blue, team B red, bold white numbers 1
  and 2 on the front and back; robots collide and contact can make a robot fall; a robot whose trunk drops below 0.40 m
  has fallen: it lies still and is stood up where it lies 3 s later.

### Container
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Others
- At a kick-off, before the ball is in play, only the kick-off team's robots may be in the centre circle, and no robot
  may be in its opponents' half; breaking this is a removal penalty.
- The boards keep the ball in: no kick-ins, goal kicks or corners; a ball resting at a board for 3 s is moved 1 m
  straight inwards while play goes on. A ball that leaves the pitch, or 30 s with nobody near the ball, gives a dropped
  ball: the ball on the centre mark, the robots placed in their halves. If the robots near the ball leave it unmoved for
  15 s, the nearest robot is removed.
- No free kicks and no cards: a foul only removes the offender. It stays off the pitch beside its own half for 15 s + 5
  s per counted team offence (pushing, ball holding), then re-enters on the touchline. Penalties end at half time.
- Removal fouls: pushing, ball holding and illegal defence. Pushing: an opponent falls, or is pushed back, because a
  robot moved into it faster, or the two stay in contact for more than 5 s; a robot kicking close to the ball is exempt.
  Ball holding: the ball is kept right at a standing robot's trunk for more than 5 s. Illegal defence: both robots of a
  team are inside their own penalty area for more than 5 s; the one farther from the ball is removed, and it is not
  counted as an offence.
- A robot whose trunk drops below 0.40 m has fallen: it lies still 3 s and is then stood up where it lies (no penalty).
- A goal, half time, full time (when level: the shoot-out), a dropped ball and every shoot-out kick freeze the world and
  the clock for the reviews.
- The scripted team B (level 2): both robots react to the ball a little late, walk slowly and kick in their stride (the
  in-walk kick).

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
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
