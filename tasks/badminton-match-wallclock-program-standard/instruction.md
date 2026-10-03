# Robot badminton: program play

You control a simulated Franka Panda arm holding a badminton racket, on a pedestal whose base slides around your half
of the court. Across the net a computer opponent plays you; its level is `match.opponent_level` in `game spec` (higher
levels are stronger). The opponent serves every point. **Win the match: first to 5 points, but from 4-4 you need a
two-point lead; at 6-6 the next point wins** (rally scoring: every rally gives a point).

## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each point until you send `game ready "WHY" "PLAN"` (a short
review: why the point ended and what you will change). Your goal is to win points, not only to return the shuttle:
watch how points are won and lost (your own errors and how your opponent plays) and adapt your program and strategy.
Frozen time does not advance the game, but it counts toward your session limit of 2 hours of real time, preparation
included. The match is graded when your session ends: stay until it is over.

## Write a program
You may write a player program that observes, finds and tracks the shuttle, predicts its flight and sends commands on
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
| `game observe` | `POST /observe {}` | the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state |
| `game act T PX PY PZ NX NY NZ VX VY VZ` | `POST /act {"type":"act","t":T,"pos":[PX,PY,PZ],"normal":[NX,NY,NZ],"vel":[VX,VY,VZ]}` | a racket command (below) |
| `game act none` | `POST /act {"type":"none"}` | cancel; the robot returns to its ready pose, the base home |
| `game wait DT` | `POST /wait {"dt":DT}` | wait DT seconds (0 < DT <= 1) |
| `game start` | `POST /start {}` | start the match |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review and resume |

Every reply includes the current state (score, game time, whether the world is running, your robot and command) and
the result of any shot or point since your previous call. If a point ends before an action takes effect, the action is dropped.

**Observation** (`observe`): a PNG of 2 rows x 4 columns of 480 x 360 tiles. Row 1 is a camera behind and above your
base line, looking down the court; row 2 a camera at the side of the court (at x < 0, looking along +x; your half is on
the right). The columns are frames 60 ms apart, newest on the right, and the reply gives each frame's game time
(`view_sim_times`). There are no shuttle coordinates: the shuttle is drawn enlarged, an orange ball (12 cm, its centre
is the shuttle's position) with a white skirt behind it. White court lines and yellow marks every 1 m along the outside
of the singles side lines (y = -6 ... 6) and behind the base lines (x = -2, -1, 1, 2) help to judge positions.
`game spec` gives both cameras' poses and intrinsics (pinhole, 45 degree vertical field of view, focal length 434.6 px,
principal point at the tile centre). The opponent is the grey figure with the red racket.

**Action** (`act`): the racket's state at contact, T seconds after the command takes effect: the head centre
(PX, PY, PZ), the string-face normal (NX, NY, NZ) and the head velocity (VX, VY, VZ) in m/s. Limits: 0 < T <= 5,
|x| <= 3.4, -7.5 <= y <= -0.3, 0.2 <= z <= 3, speed <= 8 m/s. A command takes effect `timing.act_lead_steps` control
steps (10 ms each) after it arrives (`game spec`; the stroke controller's planning time, about 0.4 s of real time, so
about 0.4/S s of game time; the reply's `took_effect`). Until then the robot keeps its current command; the new command
replaces it. The controller drives the base to stand for a forehand at the contact point (the contact ends up about
0.2-0.6 m to the right of and in front of the base; base speed up to 6 m/s, acceleration up to 20 m/s^2; if
the base cannot get there in time it stops short and the arm reaches further) and swings the arm under joint speed
limits; it knows nothing about the shuttle. The reply predicts how close the robot will get (`ik_residual`, `blade_error_m`, `normal_error_deg`, `speed_scale`, `racket_vel_delivered`, `base`). The delivered
state scatters by about 6 mm, 0.8 degrees and 3 %.

## Rules
There is no bounce: the shuttle must be hit before it reaches the floor. Your shot is good if your racket meets the
shuttle once, on your half, and the shuttle passes over the net and would land in the opponent's court (lines are in);
after your hit your racket no longer touches it. You lose the point if your shot goes into the net, comes down on
your own side or would land out of the opponent's court, or if a shuttle that is yours to hit lands in your court; a
shot of your opponent that would land out of your court wins you the point, so you may let it go.

The opponent serves every point, from its right service court when its score is even, else from its left one,
into your diagonally opposite service court, high and deep or short. A serve landing outside that court is a fault and the receiver's point; a serve into the net is replayed.
Before every serve the robots are put back at home in the ready pose; the serve comes 1 s after play resumes.
The opponent never makes an unforced error: it returns every shuttle it can reach, into your court and within your
reach. Shuttles far from it or fast beat it; higher levels move faster and reach further.

If the shuttle has been hit 300 times in the match (both sides), the match ends after that point: the player ahead
wins; if the score is level, the winner of the last point wins. There are no draws.

Deviations from the BWF Laws of Badminton (2025):
- One short game: first to 5 points, a two-point lead from 4-4, at most 7 (Law 7: best of three games to 21, cap 30).
- The opponent serves every point (Law 10.3: the rally winner serves); you never serve.
- The robots' base moves up to 6 m/s and 20 m/s^2, like a fast player.
- The shuttle is a point mass (no flip, no feathers); a shuttle crossing the net plane below the top is a fault (it
  cannot touch the net and fall over), and touching or reaching over the net is not judged (Law 13.4).

## Geometry and physics
Metres; the world frame from your side: x to your right, y towards the opponent, z up.
- Floor z = 0. Singles court |x| <= 2.59, |y| <= 6.70 (lines are in); the net is the plane y = 0 with its top at
  z = 1.524 (posts at x = +-3.05); short service lines at y = +-1.98; the centre line x = 0 divides each half into a
  right and a left service court. Your half is y < 0. Your robot's base waits at (0, -4.0) and goes back there after
  each stroke; it moves within |x| <= 3.25, -7.5 <= y <= -0.5.
- Shuttle: a point mass under gravity (9.81 m/s^2) and quadratic air drag, dv/dt = g - K |v| v with K = 0.212 per
  metre (terminal speed 6.8 m/s): hit at 40 m/s it slows to about 10 m/s within 0.3 s, and a high shuttle falls almost
  vertically at close to 6.8 m/s. No spin, no wind, no bounce.
- Racket: the head centre is 0.56 m beyond the flange; the string face is a disc of radius 0.14 m. The racket meets the
  shuttle when the shuttle's centre crosses the string plane within 0.14 m of the head centre, so put the head centre
  where the shuttle will be at T. The head moves at a few m/s while a falling shuttle moves at up to 6.8 m/s: contacts
  more than about 5 cm off along the flight usually miss.
- Contact: the shuttle leaves exactly along the face normal n (the side the head moves towards, relative to the
  shuttle) at the speed `20 · max(0, v_head·n) · (1 − 0.3·(r/0.14)^2) + 0.15 · max(0, −v_in·n)`, where v_head is the
  head velocity, r the contact's distance from the head centre and v_in the shuttle's incoming velocity. The rest of
  the head velocity and of the incoming velocity is lost. A head speed along the normal of 0.5 m/s gives about 10 m/s,
  2 m/s about 40 m/s; the arm manages up to about 2.4 m/s.
- Reach: the racket meets shuttles 0.4-2.5 m above the floor; overhead contacts (1.8-2.5 m) allow the fastest,
  steepest shots. Clears take about 1.5-2.5 s from racket to racket, drops 1-1.5 s, drives about 1 s, smashes 0.6-1 s.
