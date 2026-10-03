# Robot tennis: program play

You control a simulated Franka Panda arm holding a tennis racket, on a base that slides on rails over the back part of
your half of a regulation singles court (see Action). Across the net a computer opponent plays you; its level is
`match.opponent_level` in `game spec`. The opponent serves every point into your service box diagonally opposite; the
box changes every two points (right box twice, then left box twice, ...). **Win the match: first to 5 points; from 4:4
a player must lead by 2, and at 6:6 the next point wins.** The match also ends after 400 racket hits or 40 points
played (replayed lets included): then the player with more points wins, and at equal points the player who won the
last point.

## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each point until you send `game ready "WHY" "PLAN"` (a short
review: why the point ended and what you will change). Your goal is to win points, not only to return the ball:
watch how points are won and lost (your own errors and how your opponent plays) and adapt your program and strategy.
Frozen time does not advance the game, but it counts toward your session limit of 2 hours of real time, preparation
included. The match is graded when your session ends: stay until it is over.

## Write a program
You may write a player program that observes, finds and tracks the ball, predicts its flight and sends commands on
its own, without a new model response for each command. You may also act yourself. Prepare and test it before
`game start`, run it in the background, watch its log, and stop, fix and restart it whenever needed, also during a
point. Use the reviews to improve it. Only you send `game start` and `game ready`; actions are refused while the world
is frozen.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 4 CPUs, 8 GB; no internet during
  the match. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | cameras, slowdown, opponent level, limits |
| `game status` | `GET /status` | the current state, no image |
| `game observe` | `POST /observe {}` | the newest camera frames (`game` saves the image to a file and prints its path; HTTP: `observation.image_png_b64`) and the state |
| `game act T PX PY PZ NX NY NZ VX VY VZ [BX BY]` | `POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ],"base":[BX,BY]}` | a racket command (below); `base` is optional |
| `game move BX BY` | `POST /act {"type":"move","base":[BX,BY]}` | the base's rest position |
| `game act none` | `POST /act {"type":"none"}` | cancel; the arm returns to its ready pose |
| `game wait DT` | `POST /wait {"dt":DT}` | wait DT seconds (0 < DT <= 1) |
| `game start` | `POST /start {}` | start the match |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review and resume |

Every reply includes the current state (score, game time, whether the world is running, your robot and command) and
the result of any shot or point since your previous call. If a point ends before an action takes effect, the action is dropped.

**Observation** (`observe`): a PNG of 2 rows x 4 columns of 640 x 480 tiles. Row 1 is a camera behind and above your
base line looking down the court, row 2 a camera at the side of the court (x < 0) looking along +x (your half on the
right); the columns are frames 40 ms apart, newest on the right, and the reply gives each frame's step and game time
(`view_steps`, `view_sim_times`) and `view_leg_ids` (a new id each time the ball is served or hit). There are no ball
coordinates: the ball is drawn enlarged, a yellow-green sphere of radius 9 cm centred on the ball's true position.
Yellow marks every 2 m outside the doubles side lines and every 1 m behind the base lines help to judge positions.
`game spec` gives both cameras' poses and intrinsics (pinhole, 45 degree vertical field of view, focal length
579.4 px, principal point at the tile centre). The replies also give your robot's state (`robot_base_xy`, `q_arm`,
`racket_pos`, `racket_normal`), the bounces you have heard (side and time, no position) and whether the ball is coming
to you.

**Action** (`act`): the racket's state at contact, T seconds after the command takes effect: the head centre
(PX, PY, PZ), the string-face normal (NX, NY, NZ), pointing towards the incoming ball, the head velocity (VX, VY, VZ)
in m/s and, optionally, the base position at contact (BX, BY; default: the forehand stance, base = (PX - 0.62,
PY - 0.30)). Limits: 0 < T <= 5, |x| <= 6.5, -16 <= y <= -6, 0.1 <= z <= 2.4, speed <= 8 m/s. An act is accepted at
the next 10 ms control step and takes effect `timing.act_lead_steps` steps later (the reply's `took_effect`) while
the stroke is planned; it replaces the stroke under way. `move BX BY` sets the base's rest position, where the base
goes whenever no stroke is under way (back to home (0, -11.4) after each point); it and `act none` take effect at the
next step and count as acts. The base moves on rails over the back part of your half (|BX| <= 5.9,
-15.4 <= BY <= -7.6) at up to 4 m/s and 8 m/s^2; the arm under joint speed limits. The reply predicts how close the
stroke gets (`ik_residual`, `blade_error_m`, `normal_error_deg`, `speed_scale`, `racket_vel_delivered`, `base`). The
delivered state scatters by about 5 mm, 0.5 degrees and 2 %.

## Rules
After the serve has bounced in your service box, or after your opponent's shot (which you may also hit before it
bounces), hit the ball once so that it passes over the net, directly or after touching its top edge, and first lands
inside your opponent's singles court (lines are in). You lose the point for returning the serve before it bounces, a
second bounce on your half, a ball into the net, or a ball that lands out or on your own half; your opponent loses it
for the same faults. A serve that misses the box or touches the net is a let: the point is replayed from the same side
with a new serve. The opponent never makes unforced errors and returns every ball it can reach; higher levels react
and run faster, reach further and hit faster, wider balls with more spin.

**Deviations from the official rules** (ITF Rules of Tennis 2026):
- One tie-break-style game to 5 points instead of games and sets (Rules 5-7); from 4:4 a lead of 2 is needed and at
  most 7 points are played (as in a tie-break, Rule 5 b, but shorter).
- The serve is a machine-like serve that you only receive; a serve that misses the box or touches the net is replayed
  (no service faults, Rules 19-22).
- Only the strings touch the ball: it passes through the frame, arm and base (Rule 24 i).
- The robot moves on rails over the back part of its half instead of anywhere.

## Geometry and physics
Metres; the world frame from your side: x to your right, y towards the opponent, z up.
- Court surface z = 0; singles court |x| <= 4.115, |y| <= 11.885; service lines at |y| = 6.40. The net is the plane
  y = 0, its top 0.914 m at x = 0 rising linearly to 1.07 m at |x| = 5.029. Your half is y < 0.
- Robot: shoulder 0.88 m above the court; the racket head centre is 0.52 m beyond the flange; the strung face is an
  ellipse of half axes 0.13 m x 0.16 m. Contacts are comfortable 0.6-1.4 m high, about 0.6-0.8 m to the right of and
  0.2-0.4 m in front of the base. At contact the ball's centre is 3.35 cm (its radius) from the string plane.
- Ball: mass 57.7 g, radius 0.0335; gravity 9.81 m/s^2; drag `a = -0.0203 |v| v`; Magnus lift
  `a = 0.0370 C_L |v|^2 unit(w x v)` with `C_L = 1/(2 + 1/S)`, `S = 0.0335 |w| / |v|`; the spin w is constant in flight.
- Court bounce: the normal velocity reverses with restitution 0.76; friction (coefficient 0.6) acts on the ball's
  contact point until it rolls (the tangential impulse is the smaller of 0.6 x the normal impulse and what stops the
  sliding); the ball's moment of inertia is 0.55 m r^2.
- Net: a ball whose centre comes within its radius of the net's top edge bounces off the edge by the same law
  (restitution 0.3, friction 0.3) and play goes on; a ball that meets the net lower down stops there.
- Racket contact: the ball leaves as if the racket head moved 5 times faster than its delivered velocity
  (`V = 5 x` the head velocity). In the frame moving with V, with n the unit face normal towards the ball, the normal
  component reverses with restitution 0.82 (at the head centre, up to 25 % less towards the frame) and friction
  (coefficient 0.4) acts as in the court bounce. Without the friction: `v_out = v_in - 1.82 ((v_in - V)·n) n`.
