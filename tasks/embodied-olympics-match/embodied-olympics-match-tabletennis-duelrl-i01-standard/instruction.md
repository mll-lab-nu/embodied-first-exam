# Embodied Olympics · robot table tennis, duel against the built-in RL player (standard)

## Task
Robot table tennis: each player is a Franka Panda arm with a paddle on an x-y rail base behind its end line, both held
to the real robot's limits, and you see the game only through two cameras of four frames each. One game to 5 points; the
players' robots serve by the ITTF service laws, with a toss device on the robot. You are seat `A` against a built-in
player (seat `B`) that runs inside the simulator service and plays by the same rules, with the same robot and limits as
you, but reads the simulator's true ball state (never shown to you) instead of the cameras and picks its shots with a
learned policy. The world waits for you: it advances only while you let it (Robot Interface, `### Time`). The robot runs
as a service you reach only through its client, as if it were real hardware: one live episode.

## Goal
Success: you win the match against the built-in player.

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
- Serves: `match.first_server` serves the first 2 points, the other player the next 2, and so on; from 4:4 the service
  changes after every point (lets do not count). The server must toss within 5 s of the serve opening, else it is a
  failed service (the receiver's point). The toss device projects the ball straight up with no spin from a point you
  choose behind your end line, above the table and near your base (`toss`, Robot Interface); strike it with your paddle
  as it falls, while it is still behind your end line and above the table. The service must bounce on your court and
  then directly on your opponent's court, at least 0.2 m from the net (closer is a failed service, even if it touched
  the net). A service that touches the net and is otherwise good is a let (replayed), at most 2 in a row: your third
  service let since the last point scored is a failed service.
- It is a fault (your opponent's point) if the toss touches anything before your strike, you strike it while it rises or
  rests, it drops below the table or comes in front of the end line before you strike it, you strike it twice, or it
  does not bounce on your court and then on your opponent's court. If the receiver touches your service before it
  bounces on its court, the receiver loses the point (a let after a net touch). The receiver must return the service
  after its bounce like any other ball.
- Faults by both players at the same instant (both arms touching the table, or both robots touching the ball at the same
  moment) are a let.

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
| `game none` | `POST /act {"type": "none"}` | the arm back to its ready pose |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- Your actions are the sport's skill API (`hit`): the platform executes each one; `game spec` (`skill_contract`) says
  exactly what it delivers. An act (or toss) takes effect at the next 10 ms control step after it arrives (the reply's
  `took_effect`).
- `act` (the high level): `{type: act, t, pos, normal, vel, base?}` = the blade's state at contact t seconds after the
  command takes effect (centre pos, face normal pointing at the opponent, velocity m/s) and optionally the base position
  [bx, by] at contact; limits 0 < t <= 2.5, |x| <= 2.0, -3.3 <= y <= -0.3, -0.5 <= z <= 1.5, speed <= 8 m/s, base within
  its travel; it replaces the stroke under way; the service moves the base (to `base`, else only as much as needed: the
  contact within 0.25 m sideways and 0.10 m in depth of the point 0.45 m in front of the base; arriving at rest 5 steps
  before the contact, or as far as it gets) and plans the swing within the real arm's limits (IK at that base position;
  a jerk-limited joint trajectory within the Panda's velocity, acceleration and jerk limits: a wind-up, a stroke started
  as late as the slowest joint allows, a follow-through; with too little time the best reachable contact, and the
  reply's speed_scale / plan_scale say how much of the blade speed the limits deliver; if the direct swing would pass
  through the table it comes down onto the contact from a pose 0.10 or 0.18 m above it - reply field approach); the
  reply predicts how close the arm gets; the delivered state scatters by about 1 cm, 1.5 degrees and 5 %; after the
  stroke the arm returns to its ready pose and the base to its rest position; {type: move, base: [bx, by]} sets that
  rest position (home again at each point); {type: none} returns the arm to its ready pose. Control authority: the
  service reads only your robot's own state (joints, targets, servo, base) and your command - never the ball or the
  opponent; it neither predicts the ball nor aims; its rehearsals run on a robot-only copy. Failure handling: a
  malformed or out-of-range act is refused (HTTP 400) and changes nothing; a contact time already passed when the act
  takes effect is not executed (reply stroke 'too late'; the stroke in force goes on); an unreachable pose, a blade
  speed beyond the joint limits or a base that cannot get there in time is executed as well as the limits allow and the
  reply says so (ik_residual, blade_error_m, normal_error_deg, speed_scale, base); a new act replaces the stroke under
  way (here: the plan is not rehearsed, and if the trajectory in force predicts a better contact at the new contact step
  it is kept, reply field kept).
- `toss`: `{"type": "toss", "pos": [x, y, z], "height": H}` (both action levels; it takes effect like an act): the ball
  rests at pos for 0.1 s, then it is projected straight up with no spin to rise H metres above pos (0.16 <= H <= 1.0);
  pos behind your end line and above the table (y <= -1.39, 0.02 <= z <= 0.9) and within 0.9 m of your base
  horizontally; until then the ball waits out of sight in your robot's column. Strike it with an act, which you may send
  before or after the toss (its contact time counted from when it takes effect; `state.serve.toss.projected_at_step`
  tells when the ball leaves the device).
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

## Others
- The built-in player controls an identical robot across the net, serves by the same rules and sees the game in its own
  frame; before every point both robots are put back at rest in the ready pose with their bases at home.
- The ball: radius 0.02 m, orange; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm; a
  bounce keeps about 90 % of the vertical and 87 % of the horizontal speed (a ball dropped from 30 cm bounces back to
  about 23 cm); a ball takes about 0.6-0.9 s from the opponent to you.
- The blade: 15 × 15 cm; at contact its centre is 2.75 cm from the ball's centre along the face normal; with n the unit
  face normal the ball leaves with about v_out = v_paddle - 0.80((v_in - v_paddle).n)n + (v_in - v_paddle) - ((v_in -
  v_paddle).n)n.
- Your container: Python 3.12 with numpy, SciPy and Pillow, opencv-python-headless.

## Limits
- Time: 7200 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
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
