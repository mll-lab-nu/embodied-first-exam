# Embodied Olympics · robot badminton at the low level, match against level 2 (standard)

## Task
Robot singles badminton on a small court (the BWF court's lengths × 0.4, the net at its full height): each player is a
Franka Panda arm with a racket, held to the real Panda's limits, on an x-y gantry base; the shuttle has the real
shuttle's high drag and does not bounce. Rally scoring, one game to 11 points; the players' robots serve. You are seat
`A` against a scripted opponent at level 2. At this low level the platform does not give you the robot's `act` skill:
you implement it yourself, and every stroke of the match is played by your implementation (the skill in the loop). The
world waits for you: it advances only while you let it (Robot Interface, `### Time`). The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: you win the match, with your own skill playing every stroke.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Nothing to hand in: the service records and grades the episode. Keep your scripts, logs and notes in `/app/output/`.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- Privileged state queries: this run lets you read the simulator's state (Robot Interface,
  `### This run: privileged state queries`); the answers never say whether the task is done.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Reviews: after every point the world freezes; send `game ready "WHY" "PLAN"`, a short review, within 300 s of real
  time (`timing.review_timeout_s` in `game spec`), or your side loses the match (`ready_timeout`), even when you are
  ahead. The world does not go on by itself: watch for the freeze (your program's log, `game status`) and review at
  once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first. Write, check and serve your skill (`game skill serve`) within that window; you can improve it at any
  time during the match.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

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

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- There is no act skill or stroke controller at this level: `act` is played by your own skill (`### Your skill`); the
  robot's own commands are `traj`, `move`, `toss` and `none`. A command takes effect `act.lead_steps` control steps
  after the step at which it arrives (`game spec`); until then the robot keeps its current command.
- `act` (played by your skill, the contract of `skill_contract`):
  `{"type": "act", "t": T, "pos": [PX, PY, PZ], "normal": [NX, NY, NZ], "vel": [VX, VY, VZ]}`: the racket's state at
  contact, T s after the act takes effect: the head centre, the string-face normal and the head velocity (m/s). Limits:
  0 < T <= 5, |x| <= 2.136, -3.68 <= y <= -0.3, 0.2 <= z <= 3.0, speed <= 8 m/s. It replaces the stroke under way. An
  act may carry `"base": [BX, BY]`, where the base stands at contact (default: the forehand stance for pos: (PX, PY) -
  0.62 r (1, 1), r = max(0.30, 0.95 - 0.35 |PZ - 1.333|)); after a stroke the base stays where it struck (no automatic
  return).
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
- Your skill's computation takes no game time here (standard mode). The world stands still while a call computes (in the
  standard-realtime twin it runs on); its command takes effect at the first control step after it returns (the reply's
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
- A query only reads: no control step, the clock neither advances nor pauses (the world stands still during it, as
  between your calls). It is served until the match is over (409 after). Queries are counted and recorded; they do not
  change the grading.
- Nothing else changes: no answer holds the score, a point's result or the opponent's plan or strategy.

### This run: unlimited resets, save and load
This run lets you restart the match and go back to a saved moment.

- `POST http://localhost:8000/$SEAT/reset` with `{}`: the match from its start again (the same instance: the world, the
  opponent, the score and the clocks), as a new episode. You have 1000 resets (`budget.reset` in `/spec`).
- `POST http://localhost:8000/$SEAT/save_state` with `{}` answers `{"handle": "s1", "step": ...}`: the whole match now
  (the world, the opponent with its own internal state, the random generators, the score, the game clock) kept in the
  service; the handle is all you get. `POST http://localhost:8000/$SEAT/load_state` with `{"handle": "s1"}` goes back to
  it exactly, as a new episode. At most 32 handles are kept (the least recently used is dropped). Saves and loads do not
  use up resets.
- After a reset or a load the world is frozen until you send `game start` (or `game ready`), at most
  `timing.review_timeout_s` of real time; then it advances again, only while you let it (`game wait`, your acts), as
  before. The task's time limit keeps running.
- A match you lose by its rules (the opponent wins it, a missed review, the clock) is held at its end: `/status` shows
  phase `over`, and you may still reset or load. A match you win ends the run: no reset, save or load after it.
- Only the last episode is graded, with the task's rules: from the start, or for a loaded episode the play that led to
  the saved moment followed by what came after the load. If your session ends during a match, that match is abandoned
  (success 0); a held loss stays a loss. `final.json` records `resets`, `saves`, `loads` and `episodes`.

## Others
- The scripted opponent (`match.opponent_level` in `game spec`): it serves when it won the last rally, from its service
  court at 1.05 m, upwards, high and deep or short into your diagonal service court, at most 18 m/s, always within your
  reach (level 1: 70 % high serves, towards the middle of the court; levels 2-3: 50 % high, wider and closer to the
  short service line); it stands still in its service court while you serve. It never makes an unforced error: it
  returns every shuttle it can reach, into your court. It is a robot too, on a base with the same limits as yours: a
  reaction time after your hit it predicts the flight, its base moves until the shuttle is within its reach, and its arm
  then needs 0.55 s for a full stroke; with less than 0.3 s to spare it is under pressure (a weak, high lift into the
  middle of your court when hard pressed, a normal return in between, an attack when it has time); a shuttle it meets
  too late for a full stroke but with at least 0.45 s of arm time it still blocks (a weak lift); later still beats it,
  and shuttles arriving fast press it too. Its shots leave a robot waiting in the middle of your court time to reach
  them (level 1: 0.45 s to spare, levels 2-3: 0.25 s), except its kills: some of its attacks (level 1: 20 %, level 2: 50
  %, level 3: 90 %) are played without that guarantee. It plays 70 % of its shots to the side away from your base, and
  when your base stands within 1.2 m of the net it lifts 70 % of its returns over your head (its clears pass above 2.8 m
  over your forward court). After its own stroke its base stays put for 0.35 s and then walks at 0.6 m/s to where it
  waits: 70 % of the way towards the mean landing point of your last 4 shots. It reads your habits: when 4 of your last
  5 changes of side agree (always switching, or always staying) and your last 3 shots were all short or all deep, it
  predicts your next shot and moves 90 % of the way there at full speed. So where you place the shuttle (away from it,
  and not in a pattern) and where your base waits both matter. Level 1: reaction 0.30 s, reach 0.85 m, mild attacks
  (smashes up to 15 m/s, 70 % of the court's width); level 2: reaction 0.25 s, reach 0.85 m, level 2's attacks (up to 17
  m/s, the court's full width); level 3: as level 2 with a reaction of 0.20 s, a reach of 0.9 m and a fast walk back (2
  m/s). Its shots leave its racket at most at 18 m/s.
- The shuttle: a point mass under gravity (9.81 m/s^2) and quadratic air drag, dv/dt = g - K |v| v with K = 0.212 per
  metre (terminal speed 6.8 m/s): hit at 40 m/s it slows to about 10 m/s within 0.3 s, and a high shuttle falls almost
  vertically at close to 6.8 m/s. No spin, no wind, no bounce.
- Racket contact: the racket meets the shuttle when the shuttle's centre crosses the string plane within 0.14 m of the
  head centre; the shuttle leaves exactly along the face normal n (the side the head moves towards, relative to the
  shuttle) at the speed 4 max(0, v_head·n) (1 - 0.3 (r/0.14)^2) + 0.15 max(0, -v_in·n), where v_head is the head
  velocity, r the contact's distance from the head centre and v_in the shuttle's incoming velocity; the rest of the head
  and incoming velocity is lost. A head speed along the normal of 1 m/s gives about 4 m/s, 2.5 m/s about 10 m/s (a
  lofted shot of 10 m/s flies about 4-5 m and 1.3-1.5 s).
- Your container: Python 3.12 with numpy, SciPy and Pillow, MuJoCo at the simulator's version with its dependencies.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as this run allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`).
