# Robot table tennis, two players: program play

You control a simulated Franka Panda arm holding a table-tennis paddle. Another agent controls an identical robot
across the table; your seat (`A` or `B`) is in `game spec`. A neutral machine serves every point: the ball bounces
first on the server's half, then on the receiver's. The receiver changes every point; `match.first_receiver` in
`game spec` receives the first.
**Win the match: first to 5 points, but from 4:4 you must lead by 2; at 6:6 the next point wins (so 7 points
at most).** Both players receive this document.

## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each point until you send `game ready "WHY" "PLAN"` (a short
review: why the point ended and what you will change). Your goal is to win points, not only to return the ball:
watch how points are won and lost (your own errors and how your opponent plays) and adapt your program and strategy.
Frozen time does not advance the game, but it counts toward your session limit of 2 hours of real time, preparation
included. After one player runs `game start`, the other has 30 minutes to start.
**After each point, send `game ready` within 300 seconds of real time or you forfeit the match**; do not sleep through a
review. The match is graded when your session ends: stay until it is over.

## Write a program
You may write a player program that observes, finds and tracks the ball, predicts its flight and sends commands on
its own, without a new model response for each command. You may also act yourself. Prepare and test it before
`game start`, run it in the background, watch its log, and stop, fix and restart it whenever needed, also during a
point. Use the reviews to improve it. Only you send `game start` and `game ready`; actions are refused while the world
is frozen.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 2 CPUs, 4 GB; no internet during
  the match. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000/<your seat>` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | your seat, cameras, slowdown, match format, limits |
| `game status` | `GET /status` | the current state, no image |
| `game observe` | `POST /observe {}` | the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state |
| `game act T PX PY PZ NX NY NZ VX VY VZ` | `POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ]}` | a paddle command (below) |
| `game act none` | `POST /act {"type":"none"}` | cancel; the arm returns to its ready pose |
| `game wait DT` | `POST /wait {"dt":DT}` | wait DT seconds (0 < DT <= 1) |
| `game start` | `POST /start {}` | ready to start; play begins when both players have started |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review; play resumes when both have |

Every reply includes the current state (score, game time, whether the world is running, your robot and command). If a point ends before an action takes effect, the action is dropped.

**Observation** (`observe`): a PNG of 2 rows x 4 columns of 480 x 360 tiles. Row 1 is a camera behind and above your
robot, row 2 a camera at the side of the table; the columns are frames 40 ms apart, newest on the right, and the reply
gives each frame's game time (`view_sim_times`). There are no ball coordinates: the ball is a small orange sphere (4 cm).
Yellow marks every 0.25 m along the table edges help to judge positions. `game spec` gives both cameras' poses and
intrinsics (pinhole, 45 degree vertical field of view, focal length 434.6 px, principal point at the tile centre). One observation at a time per seat (HTTP 429 otherwise).
Both players see the game the same way: in each player's frame its own base is at (0, -1.75, 0), facing +y.

**Action** (`act`): the blade's state at contact, T seconds after the command takes effect: its centre (PX, PY, PZ),
its face normal (NX, NY, NZ), pointing towards the opponent, and its velocity (VX, VY, VZ) in m/s. Limits: 0 < T <= 2.5,
|x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2, speed <= 8 m/s. A command takes effect at the next 10 ms control step
(the reply's `took_effect`) and replaces the stroke under way. The arm moves under joint speed limits; the reply
predicts how close the arm will get (`ik_residual`, `speed_scale`, `joint_limited_steps`, `contact_joint_error`). The delivered state scatters by about 4 mm, 0.6 degrees and 2 %.

## Rules
After exactly one bounce on your half, hit the ball once so that it lands on your opponent's half, directly or after
touching the net (the upper table edges count, the vertical sides do not); the same holds for your opponent's returns.
You lose the point for a volley, a double hit, two bounces, a miss, a ball that lands on your own half or out, the ball
touching your arm or handle while it is over or travelling towards your half, or your arm or paddle touching the
table, net or floor. A shot that passes a player's half without touching it is out, even if it then hits that player's
robot. A serve that touches the net or is irregular is a let: no point, the next serve. If the receiver makes 13 good
returns in a rally, the receiver wins the point (expedite rule). If 40 points (lets included) are played, the match
ends: the player ahead wins; at a level score, the player who won the last point wins.
Faults by both players at the same instant are a let. The robot that is not receiving is transparent to the serve until
it bounces on the receiver's half.

Deviations from the official rules (ITTF Laws of Table Tennis, ITTF Statutes 2025, chapter 2):
- One game to 5 points (lead by 2 from 4:4, at most 7) instead of a best-of-games match with games to 11 (2.11, 2.12).
- A neutral machine serves every point with recorded real serves (the robots cannot toss the ball, 2.6); the receiver
  changes every point, as under the expedite system (2.13.3, 2.15.3).
- Only the blade can strike the ball: the ball touching the handle or arm loses the point (2.5.7).
- A robot has no free hand: any contact of the arm or paddle with the table, net or floor loses the point
  (2.10.1.9-2.10.1.11).
- Any double hit loses the point, deliberate or not (2.10.1.7).
- The expedite rule (13 good returns by the receiver win the point) applies from the first point (2.15.4).

## Geometry and physics
Metres; the world frame from your side: x to your right, y towards the opponent, z up.
- Table top z = 0, |x| <= 0.7625, |y| <= 1.37; the net is at y = 0, top z = 0.1525. Your half is y < 0. Your robot's
  base is at (0, -1.75, 0), facing +y.
- Ball: radius 0.02; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm. A bounce keeps
  about 96 % of the vertical and 87 % of the horizontal speed. A ball takes about 0.6-0.9 s from the opponent to you.
- Reach: the blade can meet a ball whose centre is within about 0.85 m of the shoulder (0, -1.75, 0.33) and above
  z = 0.12.
- Blade: 15 x 15 cm. At contact its centre is 2.75 cm from the ball's centre along the face normal; a contact more
  than a few cm off the blade centre misses or mis-hits.
- Contact: with n the unit face normal, the ball leaves with about
  `v_out = v_paddle - 0.96((v_in - v_paddle)·n)n + (v_in - v_paddle) - ((v_in - v_paddle)·n)n`
  (the normal component reverses with restitution 0.96, the tangential component is kept). On measured contacts this
  is within about 0.3 m/s; the ball's spin causes most of the difference.
