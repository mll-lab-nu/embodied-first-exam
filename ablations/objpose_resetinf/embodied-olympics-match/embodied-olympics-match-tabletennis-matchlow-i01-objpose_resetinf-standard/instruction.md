# Embodied Olympics · robot table tennis at the low level, match against level 1 (standard)

## Task
Robot table tennis: each player is a Franka Panda arm with a paddle on an x-y rail base behind its end line, both held
to the real robot's limits, and you see the game only through two cameras of four frames each. One game to 5 points; the
players' robots serve by the ITTF service laws, with a toss device on the robot. You are seat `A` against a scripted
opponent at level 1. At this low level the platform does not give you the robot's `hit` skill: you implement it
yourself, and every stroke of the match is played by your implementation (the skill in the loop). The world waits for
you: it advances only while you let it (Robot Interface, `### Time`). The robot runs as a service you reach only through its client, as if it were real hardware.

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
- You may change your skill or program during a review, but only what fits in its time limit, with `game ready` sent
  before it ends: the review is not development time.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first. Write, check and serve your skill (`game skill serve`) within that window; you can improve it at any
  time during the match.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The match (ITTF Laws, with these changes):
- One game: the first to 5 points with a lead of 2 from 4:4, or the first to 7 (at 6:6 the next point wins). A player's
  third undue-delay fault (no toss within 5 s of the serve opening) loses it the match. At 40 points played (lets
  included) the player ahead wins, at a level score the player who won the last point. There are no draws.
- Play: after exactly one bounce on your half, hit the ball once so that it lands on your opponent's half, directly or
  after touching the net (the upper table edges count, the vertical sides do not); the same holds for your opponent's
  returns. You lose the point for a volley, a double hit, two bounces, a miss, a ball that lands on your own half or
  out, the ball touching your arm or handle while it is over or travelling towards your half, or your robot or paddle
  touching the net assembly (touching the table is allowed). A shot that passes a player's half without touching it is
  out, even if it then hits that player's robot. The receiver's 13th good return in a rally wins it the point (expedite
  rule).
- Serves: you serve the first 2 points, the other player the next 2, and so on; from 4:4 the service changes after every
  point (lets do not count). The server must toss within 5 s of the serve opening, else it is a failed service (the
  receiver's point). The toss device projects the ball straight up with no spin from a point you choose behind your end
  line, above the table and near your base (`toss`, Robot Interface); strike it with your paddle as it falls, while it
  is still behind your end line and above the table. The service must bounce on your court and then directly on your
  opponent's court, at least 0.2 m from the net (closer is a failed service, even if it touched the net). A service that
  touches the net and is otherwise good is a let (replayed), at most 2 in a row: your third service let since the last
  point scored is a failed service.
- It is a fault (your opponent's point) if the toss touches anything before your strike, you strike it while it rises or
  rests, it drops below the table or comes in front of the end line before you strike it, you strike it twice, or it
  does not bounce on your court and then on your opponent's court. If the receiver touches your service before it
  bounces on its court, the receiver loses the point (a let after a net touch). The receiver must return the service
  after its bounce like any other ball.

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
| `game hold` | `POST /act {"type": "hold"}` | hold the targets in force |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |
| `game skill serve [DIR]` | (in your container) | start your skill server (default DIR `/app/output/skill`); it reloads the skill whenever its files change |
| `game skill status` | (in your container) | the loaded version, its functions, any load error |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- There is no hit skill or stroke planner at this level: `hit` is played by your own skill (`### Your skill`); the
  robot's own commands are `traj`, `slew`, `hold` and `toss`. A command takes effect at the next 10 ms control step
  after it arrives (the reply's `took_effect`); until then the robot keeps its current command.
- The low level (`traj`, `slew`, `hold`): joint position targets at 100 Hz for the base and the arm, no IK or stroke
  planner: traj {k0, q: rows of 9 targets [base_x, base_y, q1..q7]} (row i = control step k0 + i, <= 300 rows;
  consecutive rows within the per-step speed limit - 2 cm per base axis - and three consecutive rows within the
  acceleration limit: second difference <= acceleration limit × (10 ms)^2 - 8 m/s^2 per base axis, 15 / 7.5 / 10 / 12.5
  / 15 / 20 / 20 rad/s^2 for q1..q7; the first row used must satisfy both with the target in force and its velocity),
  slew {q (9), speed} (every arm joint towards q at speed × its speed limit within its acceleration limit, the base
  towards q's base position at speed × 2 m/s with bounded acceleration and jerk), hold; the robot's 1 kHz servo follows
  the targets with a setpoint that never exceeds the real limits (velocity, acceleration, jerk; the arm's torques 87 /
  12 N m changing by at most 1 N m per ms), so targets beyond them are followed late; `game spec` gives the kinematic
  chain (the base's two prismatic joints first), limits (limits.joint_accel_limit, joint_jerk_limit, the servo's law),
  the joint controller and the robot's own model (robot_model.robot_only_xml).
- `toss`: `{"type": "toss", "pos": [x, y, z], "height": H}` (both action levels; it takes effect like an act): the ball
  rests at pos for 0.1 s, then it is projected straight up with no spin to rise H metres above pos (0.16 <= H <= 1.0);
  pos behind your end line and above the table (y <= -1.39, 0.02 <= z <= 0.9) and within 0.9 m of your base
  horizontally; until then the ball waits out of sight in your robot's column. Strike it with a hit, which you may send
  before or after the toss (its contact time counted from when it takes effect; `state.serve.toss.projected_at_step`
  tells when the ball leaves the device).
- Your robot faces +y on an x-y rail base behind your end line: base position base_xy (link0 at table-top height),
  travel |x| <= 1.0, -2.40 <= y <= -1.50, home (0, -1.75); up to 2 m/s, 8 m/s^2 and 200 m/s^3 per axis; the arm is a
  Franka Panda held to its real joint limits (velocity 2.175 / 2.61 rad/s, acceleration 15 / 7.5 / 10 / 12.5 / 15 / 20 /
  20 rad/s^2, jerk 7500 / 3750 / 5000 / 6250 / 7500 / 10000 / 10000 rad/s^3, torque 87 / 12 N m, torque rate 1000 N
  m/s); its servo runs the arm at 0.9 of the velocity limits, and an arm joint faster than 1.05 × its limit triggers the
  robot's velocity reflex: it stops at that pose for 1 s, then resumes from rest (the stroke is lost; `game spec`
  limits.controller); its collision reflex does the same when the arm or paddle presses on the table with more than 20 N
  (touching the table is legal, but the robot protects itself).
- Reach: the blade can meet a ball whose centre is within about 0.85 m of the shoulder (base_xy, z = 0.33) and above z =
  0.12; the base moves the shoulder over the whole table width but never over the table (it stops 0.13 m behind the end
  line).

### Observations
- `game observe`: one PNG of 2 rows (camera behind your robot, camera at the side) × 4 columns (frames 40 ms apart,
  newest right) of 480 × 360 tiles, with each frame's control step (observation.view_steps); no ball coordinates; yellow
  marks every 0.25 m along the table edges; cameras' poses and intrinsics in `game spec` (pinhole, 45 degree vertical
  field of view, focal length 434.6 px, principal point at the tile centre).
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`.
- The state: `you_serve`, `you_receive_serve` and `serve`: `phase` `waiting` (the receiver is getting ready), `open`
  (0.8 s after the previous point; `opens_in_s`), `tossed` (`tossed_at_step`), `done`; `court` any (singles has no
  service court); `deadline_in_s`; `detail`, `server`, and for the server `delay_faults` and its own toss; `lets_in_row`
  counts the service lets in a row. Service faults are recorded as `serve_fault:<reason>: <text>`, reasons: undue_delay
  (no toss in time), dropped (the toss fell below the table unstruck), in_front (it came in front of the end line
  unstruck), position (another breach of the service law), toss_touched (it touched something before the strike),
  not_projected (struck while resting), rising (struck while rising), double_hit, not_own_court (the first bounce was
  not on your court), out (after your court it missed the opponent's court), undecided (not decided within 3 s of the
  strike), robot_net (your robot touched the net assembly during the service), repeated_let (your third service let in a
  row), short (the bounce on your opponent's court was closer than 0.2 m to the net).

### Frame and table
- Metres; your frame: x to your right, y towards the opponent, z up; table top z = 0, |x| <= 0.7625, |y| <= 1.37; net at
  y = 0, top z = 0.1525; your half y < 0.

### Time
The world waits for you: it advances only during an open `game wait DT` (at most DT game seconds, then it stops again)
and, for an action you sent, up to the control step at which it takes effect (the step after the state it answers).
Between your calls it stands still: your thinking, your program's computation and the service's planning of an action
take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on; a match you leave
standing never ends, and it is lost when your session ends. `game spec` says so (`timing.clock` = `lockstep`). At the
end of every unit (a point; `game spec`) the world freezes for the reviews; the reviews' time limit and the start window
are real time. One act and one observation per seat in flight.

### Your skill
At this level you are the robotics engineer: the platform does not give you the skill `hit` (the high level's action);
you implement it yourself from your toolkit, and the match is played with your implementation in the loop: your program
decides when and where, your skill turns each decision into the robot's commands.

- Your robot's own model is `/opt/robot/robot_only.xml` (MJCF: the rail base, the arm and the paddle only, nothing of
  the world; meshes in `/opt/robot/assets`), with MuJoCo at the simulator's version. Your toolkit
  (`/opt/robot/toolkit.toml`) also holds two optional libraries: `/opt/robot/lib/tt_kinematics.py` (PaddleKinematics:
  forward kinematics and Jacobians of the 9 joints, damped least-squares IK of the blade centre and face normal with the
  base at a given position, the rail's go-to law) and `/opt/robot/lib/tt_servo.py` (RobotSim: your robot's own servo law
  on the robot-only model, to roll your joint targets out before you send them). The hit contract: the blade centre at
  pos, its face normal along normal and its velocity vel at the contact step k_c = k_eff + round(t / 0.01) (k_eff: the
  step your hit's command takes effect) (the tolerances: `skill_contract`).
- Skill API: the contract (request ranges, what is measured, the tolerances, success) is `skill_contract` in
  `game spec`.
- Deliverable: `/app/output/skill/hit.py` (plus any files it needs in `/app/output/skill/`), served to the simulator
  from your own container with `game skill serve`, with
  `hit(t, pos, normal, vel, *, state, spec) -> one low-level command ({'type': 'traj', 'k0', 'q': rows of 9 targets} | {'type': 'slew', 'q', 'speed'} | {'type': 'hold'}) or None; the contact at control step state['step'] + round(t / 0.01) (in the API test the command takes effect at state['step']; in the match when your call returns, spec timing)`;
  optional:
  `step(*, state, spec) -> a command or None (called every 20 ms between hits: the return to a ready pose, the base's position)`.
  It may use numpy, scipy, mujoco, the toolkit under /opt/robot (robot_only.xml, assets, lib/tt_kinematics.py,
  lib/tt_servo.py) and files inside `/app/output/skill`; module-level memory between calls of one run; state = the low
  level's observe state (no images, no ball coordinates), spec = `game spec`'s kinematics, limits, toolkit,
  skill_contract; no network, no other files, no other processes. It must be deterministic; time limits per call: load
  30 s, hit 5 s, step 1 s.
- Toolkit: `/opt/robot/toolkit.toml` lists everything you are given (joint_interface, robot_model, robot_meshes,
  ik_library, servo_model); not given: hit.
- Practice requests: `/opt/robot/hit_cases_public.jsonl`: each the request, the robot's state and a reference plan; they
  show the contract at work (the task grades the match only).

### The skill in the loop
- To play `hit`, send it as an action: `game act '{"type": "hit", ...}'` with the fields of `skill_contract`. The
  simulator calls your skill server (`game skill serve`, a background process in your own container), which runs your
  `hit.py` in a sandbox of its own (a separate process, as an unprivileged user when your container runs as root, from a
  private copy of `/app/output/skill/`, the toolkit at its paths) with `state` = your observation without images
  (`state["step"]` = the control step your call arrived) and `spec` (`skill_contract`, the toolkit, the robot's
  kinematics and limits, and `timing`), and applies the low-level command your function returns.
- Your skill's computation takes no game time here (standard mode). The world stands still while a call computes (in the
  standard-realtime twin it runs on); its command takes effect at the first control step after it returns (the reply's
  `took_effect.step`; `t` counts from `state["step"]`). If it raises, times out, returns nothing or an invalid command,
  nothing happens: the reply's `skill.error` says why, `skill.status` shows the loaded version and any load error. The
  simulator waits at most the time limit of `hit` + 1 s for each answer; a later one is ignored.
- If your module defines `step(*, state, spec)`, it is called every 2 control steps during the match, synchronously: the
  world waits for its answer at most `step_wait_s` = one control period (0.1 s of real time at S = 10;
  `skill_in_loop.step_wait_s` in `game spec`, `timing.step_wait_s` in the `spec` your skill gets) and applies the
  command it returns at that very control step. No answer within `step_wait_s`, an error or an invalid command: no
  command at that step (the world goes on); a step() is skipped while one of your `hit` calls is computing. Keep `step`
  fast (it is a per-step reflex, not a planner).
- Your skill server is yours: a server that is down, slow, crashing or answering garbage only costs you your own
  commands (nothing happens for that call or step); it never stops the match. A server that was down is tried again by
  `step` within a second of coming back (at the latest at the next point).
- Low-level commands that bypass the skill are refused (HTTP 409) while a ball is in play (from a toss or a stroke until
  the point is decided: traj, slew and hold go through your hit); between points and before your toss you may send them;
  `toss` at any time.
- Start your skill server before you send `game start`: `game skill serve /app/output/skill` (once; it keeps running in
  the background). `game skill status` shows the loaded version (sha256), its functions and any load error (also in
  every hit's reply, `skill.status`). Without a server every skill call fails: nothing happens.
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
- The scripted opponent, level 1 (`match.opponent_level` in `game spec`): it serves its turns: a toss from its end, then
  a serve from the official serve library (always legal: the legal services a Franka on a rail made under the real
  robot's limits, struck as the toss falls back through the strike point; level 1 draws from the easiest 25 % of the
  library - ranked by how low the ball bounces up on your court and how much spin it has: the easiest bounce highest
  with the least spin -, level 2 40 %, level 3 60 %, level 4 all). It returns every ball it can reach; it judges how
  wide and how fast your ball is and, for your service, also how short (a service it meets close to the net is harder;
  level 1 meets nothing nearer than 0.62 m from the net, level 4 0.45 m), and it moves faster for a service (it is ready
  for it: 0.65-1.05 m/s by level); higher levels react faster, reach further and play faster, wider balls with more
  spin. It obeys the same real limits as your robot: its paddle moves along its end line within the rail's 2 m/s, 8
  m/s^2 and 200 m/s^3, and its shots stay within what the limited arm produces (at most 5.5 m/s off the paddle, 34 rad/s
  of spin, a blade speed of 2 m/s by the contact law).
- The ball: radius 0.02 m, orange; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm; a
  bounce keeps about 90 % of the vertical and 87 % of the horizontal speed (a ball dropped from 30 cm bounces back to
  about 23 cm); a ball takes about 0.6-0.9 s from the opponent to you.
- The blade: 15 × 15 cm; at contact its centre is 2.75 cm from the ball's centre along the face normal; with n the unit
  face normal the ball leaves with about v_out = v_paddle - 0.80((v_in - v_paddle).n)n + (v_in - v_paddle) - ((v_in -
  v_paddle).n)n.
- Your container: Python 3.12 with numpy, SciPy and Pillow, opencv-python-headless, MuJoCo at the simulator's version
  with its dependencies.

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
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as this run allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`).
