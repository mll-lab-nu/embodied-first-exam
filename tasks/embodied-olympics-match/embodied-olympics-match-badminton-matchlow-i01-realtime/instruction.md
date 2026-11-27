# Embodied Olympics · robot badminton at the low level, match against level 2 (realtime)

## Task
Win a game of singles badminton to 11 points against the scripted opponent, with a stroke skill you write yourself
playing every stroke.

## Goal
Success: you win the match, with your own skill playing every stroke.

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
  program first. Write, check and serve your skill (`game skill serve`) within that window; you can improve it at any
  time during the match.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The match (BWF Laws, with these changes):
- One game, rally scoring: the first to 11 points wins; from 10-10 a player must lead by 2, and at 14-14 the next point
  wins (at most 15).
- The match also ends after 400 hits (both sides) or 40 points played (lets included): then the player with more points
  wins, at equal points the player who won the last point that was not a let, and as a last resort the player who
  received first (here: the opponent). There are no draws.
- Hit the shuttle once, on your half, before it reaches the floor, so that it passes over the net and lands in the
  opponent's singles court (lines are in).
- You lose the point if your shot goes into the net (below its top), comes down on your own side or lands out, or if a
  shuttle that is yours to hit lands in your court. An opponent's shot that would land out wins you the point, so you
  may let it go. Touching or reaching over the net is not judged.
- The winner of a rally serves the next point (after a let, the same server); you serve the first point. Before every
  serve both robots are put at rest on their serve spots, diagonally opposite: in their right service courts when the
  server's score is even, else in their left ones.
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
shuttle's high drag and does not bounce. You are seat `A` against a scripted opponent at level 2. At this low level the
platform does not give you the robot's `act` skill: you implement it yourself, and every stroke of the match is played
by your implementation (the skill in the loop). The world runs at 1/S of real speed (S = 20). The robot runs as a
service you reach only through its client, as if it were real hardware, on a clock that does not stop while you think:
one live episode. There is no `finish` tool: the match's rules end it.

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
| `game skill serve [DIR]` | (in your container) | start your skill server (default DIR `/app/output/skill`); it reloads the skill whenever its files change |
| `game skill status` | (in your container) | the loaded version, its functions, any load error |

Errors: 400 = an invalid action (nothing happens); 409 = not now (not your turn, or a review is due); 429 = one action
already in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from
your seat (empty body: retry more slowly).

### Actions
- There is no act skill or stroke controller at this level: `act` is played by your own skill (`### Your skill`); the
  robot's own commands are `traj`, `move`, `toss` and `none`. A command takes effect `act.lead_steps` control steps
  after the step at which it arrives (`game spec`); until then the robot keeps its current command.
- `act` (played by your skill, the contract of `skill_contract`):
  `{"type": "act", "t": T, "pos": [PX, PY, PZ], "normal": [NX, NY, NZ], "vel": [VX, VY, VZ]}`: the racket's state at
  contact, T s after the act takes effect: the head centre, the string-face normal and the head velocity (m/s). Limits:
  0 < T <= 5, |x| <= 2.136, -3.68 <= y <= -0.3, 0.2 <= z <= 3.0, speed <= 8 m/s. It replaces the stroke under way. An
  act may carry `"base": [BX, BY]`, where the base stands at contact. By default the base takes the forehand stance for
  pos: (PX, PY) - 0.62 r (1, 1), with r = max(0.30, 0.95 - 0.35 |PZ - 1.333|). After a stroke the base stays where it
  struck (no automatic return).
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
The world runs on its own clock at 1/S of real speed, S = 20 (`timing.slowdown` in `game spec`): it never waits for you,
so your thinking and your program's computation cost game time. At the end of every unit (a point; `game spec`) the
world freezes for the reviews. One action at a time per seat (429).

### Your skill
At this level you are the robotics engineer: the platform does not give you the skill `act` (the high level's action);
you implement it yourself from your toolkit, and the match is played with your implementation in the loop: your program
decides when and where, your skill turns each decision into the robot's commands.

- Your robot's own model is `/opt/robot/robot_only.xml` (MJCF: the base, the pedestal, the arm and the racket only,
  nothing of the world; meshes in `/opt/robot/assets`), with MuJoCo at the simulator's version. Your toolkit
  (`/opt/robot/toolkit.toml`) also holds two optional libraries: `/opt/robot/lib/bm_kinematics.py` (RacketKinematics:
  forward kinematics and Jacobians of the 9 joints, damped least-squares IK of the racket head centre and string-face
  normal with the base at a given position, the self-collision clearance, the base's go-to law) and
  `/opt/robot/lib/bm_servo.py` (RobotSim: your robot's own servo law on the robot-only model, to roll your joint targets
  out before you send them, from the observed state q, qd, q_target, servo; it models the joint-velocity rule: the servo
  runs the arm at 0.9 of its velocity limits, and an arm joint faster than 1.05 × its limit stops the robot for 1 s -
  `game spec` limits.velocity_rule, the state's servo.reflex). The act contract: the racket head centre at pos, its
  string-face normal along normal (either face) and its velocity vel at the contact step (base, when the request gives
  it: where your base stands at contact; it is passed as a fifth positional argument only when given) k_c = k_eff +
  round(t / 0.01) (k_eff: the step your act's command takes effect) (the tolerances: `skill_contract`).
- Skill API: the contract (request ranges, what is measured, the tolerances, success) is `skill_contract` in
  `game spec`.
- Deliverable: `/app/output/skill/act.py` (plus any files it needs in `/app/output/skill/`), served to the simulator
  from your own container with `game skill serve`, with
  `act(t, pos, normal, vel, base=None, *, state, spec) -> one low-level command ({'type': 'traj', 'q': rows of 9 targets [base_x, base_y, q1..q7], row i for control step state['step'] + i} | {'type': 'none'}) or None`;
  optional: `step(*, state, spec) -> a command or None (called every 20 ms between acts)`. It may use numpy, scipy,
  mujoco, the toolkit under /opt/robot (robot_only.xml, assets, lib/bm_kinematics.py, lib/bm_servo.py) and files inside
  `/app/output/skill`; module-level memory between calls of one run; state = the low level's observe state (no images,
  no shuttle coordinates) with step, spec = `game spec`'s joints, limits, toolkit, skill_contract; no network, no other
  files, no other processes. It must be deterministic; time limits per call: load 30 s, act 5 s, step 1 s.
- Toolkit: `/opt/robot/toolkit.toml` lists everything you are given (joint_interface, robot_model, robot_meshes,
  ik_library, servo_model); not given: act.
- Practice requests: `/opt/robot/act_cases_public.jsonl`: each the request, the robot's state and a reference plan; they
  show the contract at work (the task grades the match only).

### The skill in the loop
- To play `act`, send it as an action: `game act '{"type": "act", ...}'` with the fields of `skill_contract`. The
  simulator calls your skill server (`game skill serve`, a background process in your own container), which runs your
  `act.py` in a sandbox of its own (a separate process, as an unprivileged user when your container runs as root, from a
  private copy of `/app/output/skill/`, the toolkit at its paths) with `state` = your observation without images
  (`state["step"]` = the control step your call arrived) and `spec` (`skill_contract`, the toolkit, the robot's
  kinematics and limits, and `timing`), and applies the low-level command your function returns.
- Your skill's computation counts. The world runs on while it computes (1 wall second = 1/S game seconds, S =
  `timing.slowdown`); its command takes effect at the first control step after it returns (the reply's
  `took_effect.step`; `t` counts from `state["step"]`). If it raises, times out, returns nothing or an invalid command,
  nothing happens: the reply's `skill.error` says why, `skill.status` shows the loaded version and any load error. The
  simulator waits at most the time limit of `act` + 1 s for each answer; a later one is ignored.
- If your module defines `step(*, state, spec)`, it is called every 2 control steps during the match, synchronously: the
  world waits for its answer at most `step_wait_s` = one control period (0.2 s of real time at S = 20;
  `timing_skill.step_wait_s` in `game spec`, `timing.step_wait_s` in the `spec` your skill gets) and applies the command
  it returns at that very control step. No answer within `step_wait_s`, an error or an invalid command: no command at
  that step (the world goes on); a step() is skipped while one of your `act` calls is computing. Keep `step` fast (it is
  a per-step reflex, not a planner).
- Your skill server is yours: a server that is down, slow, crashing or answering garbage only costs you your own
  commands (nothing happens for that call or step); it never stops the match. A server that was down is tried again by
  `step` within a second of coming back (at the latest at the next point).
- Low-level commands that bypass the skill are refused (HTTP 409) while a shuttle your robot may meet is in play (coming
  to it, or your own toss in the air: traj and move go through your act); between points you may send them; `toss` at
  any time.
- Start your skill server before you send `game start`: `game skill serve /app/output/skill` (once; it keeps running in
  the background). `game skill status` shows the loaded version (sha256), its functions and any load error (also in
  every act's reply, `skill.status`). Without a server every skill call fails: nothing happens.
- The server reloads your skill whenever its files change, at any time: the new version plays from the next call (write
  each file completely, e.g. write and rename).
- Tip: the skill server shares your container's CPUs with everything else you run. If timing matters, consider pinning
  the server to a core of its own (e.g. `taskset -c 1 game skill serve /app/output/skill`) and keeping heavy work
  (training, your model's own tools) off that core during play.

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
- Your container: Python 3.12 with numpy, SciPy and Pillow, MuJoCo at the simulator's version with its dependencies.

## Others
- The opponent is a scripted robot at level 2 with the same limits as yours: it predicts the shuttle's flight exactly,
  never makes an unforced error, returns every shuttle it can reach, plays away from your base and reads patterns in
  your shots.

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
