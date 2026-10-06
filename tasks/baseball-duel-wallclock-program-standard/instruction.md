# Robot baseball, two players: program play

Two agents play baseball against each other, pitcher against batter. In each half-inning one seat bats (a
simulated swing rig holding a wooden bat at home plate) and the other pitches (it chooses every pitch) until the batting
seat has 3 outs; then they swap. Your seat (`A` or `B`) is in `game spec`; `match.first_player` is the seat that bats
first, in the top of each inning (the visitors), and the other seat bats in the bottom (home). Your current role is
`role` in every reply. The game is 1 inning: each seat bats one half-inning. **Win the game: score more runs than
your opponent** (with base runners, as in baseball; rules below). If the runs are level after the inning, extra innings
are played until they differ, at most 1; if they are still level, the winner of the last pitch wins (the batter
if that pitch ended the plate appearance with a walk or a hit, else the pitcher). There are no draws. Both players
receive this document.

## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each pitch until you send `game ready "WHY" "PLAN"` (a short
review: why the pitch ended and what you will change). Your goal is to score more runs than your opponent: watch how each pitch turns out, as batter and as pitcher,
and adapt your program and strategy.
Frozen time does not advance the game, but it counts toward your session limit of 2 hours of real time, preparation
included. After one player runs `game start`, the other has 30 minutes to start.
**After each pitch, send `game ready` within 300 seconds of real time or you forfeit the game**; do not sleep through a
review. The game is graded when your session ends: stay until it is over.

## Write a program
You may write a player program that observes, finds and tracks the ball, predicts its flight and sends commands on
its own, without a new model response for each command. You may also act yourself. Prepare and test it before
`game start`, run it in the background, watch its log, and stop, fix and restart it whenever needed, also during a
pitch. Use the reviews to improve it. Only you send `game start` and `game ready`; actions are refused while the world
is frozen.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 2 CPUs, 4 GB; no internet during
  the game. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000/<your seat>` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | your seat, the first batter, cameras, slowdown, the pitch types and limits, the fielders |
| `game status` | `GET /status` | the current state, no image |
| `game observe` | `POST /observe {}` | the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state |
| `game act T PLANE HEIGHT SPEED [REACH]` | `POST /act {"type":"swing","t":T,"plane":PLANE,"height":HEIGHT,"speed":SPEED,"reach":REACH}` | batting: a swing command (below) |
| `game pitch TYPE SPEED X Z [SPIN BREAK]` | `POST /act {"type":"pitch","pitch":TYPE,"speed":SPEED,"x":X,"z":Z,"spin_rpm":SPIN,"break_deg":BREAK}` | pitching: the pitch (below) |
| `game act none` | `POST /act {"type":"none"}` | cancel your swing, or your pitch (no pitch at the release is an automatic ball) |
| `game wait DT` | `POST /wait {"dt":DT}` | wait DT seconds (0 < DT <= 1) |
| `game start` | `POST /start {}` | ready to start; play begins when both players have started |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review; play resumes when both have |

Every reply includes the current state (score, game time, whether the world is running, your robot and command). If a pitch ends before an action takes effect, the action is dropped.

**Observation** (`observe`): a PNG of 2 rows x 4 columns of 480 x 360 tiles. Row 1 is a camera behind home plate (the
catcher's view) at (0, -2.4, 1.5) looking towards (-0.3, 12, 1.4), vertical field of view 18 degrees (focal length
1136.5 px); row 2 a camera beside the first part of the pitch path at (7, 14.6, 1.55) looking along -x (the pitcher on
the right), vertical field of view 30 degrees (focal length 671.8 px). Both are pinholes with the principal point at the
tile centre (image right = forward x up); `game spec` gives their exact poses and intrinsics. The columns are frames 30
ms apart, newest on the right; the reply gives each frame's time since the release (`view_times`, negative during the
windup, also stamped on the tiles) and its game time (`view_sim_times`). There are no ball coordinates: the ball is a
small bright white sphere (7.3 cm). Until the release it rests in the pitcher's hand at the release point. Every reply
also reports the game time, `t_since_release`, what you heard (the release, the ball in the mitt or on the bat) and
your current command. One observation at a time per seat (HTTP 429 otherwise). Both
players see the same cameras, whatever their role. Base runners (red, like the batter) stand on their bases: a runner on
second shows behind the pitcher in row 1, one on third in the background of row 2, one on first in neither.

**Batting** (`game act`, HTTP `act` with `"type":"swing"`, while you bat, after the release):
the bat's state when it is square (pointing along +x, see below), T seconds after the command takes effect: the swing
plane PLANE (attack angle, -15 to 35 degrees, positive = the bat moves upwards through the zone), HEIGHT of the bat
axis at the square position (0.30 to 1.40 m), SPEED of the sweet spot (15 to 34 m/s) and REACH, a shift of the pivot
towards the plate (-0.20 to 0.20 m, default 0); 0 < T <= 2.5.
A command takes effect at the next 10 ms control step (the reply's `took_effect`). The rig starts the swing
3.9741 / SPEED s before square (at once if that is already past: then it is square later than asked; the reply's
`swing` says when). Until the swing starts, a new `act` replaces it and `act none` cancels it; once started it cannot be
changed. A swing command is refused before the release. With no swing started when the ball is 0.03 s past the plate,
the pitch is taken. The rig knows nothing about
the ball. It delivers your command with a seeded scatter: N(0, 3 ms) in the swing start, N(0, 1 degree) in the plane,
N(0, 8 mm) in the height, N(0, 1.5 %) in the speed and N(0, 8 mm) in the reach.

**Pitching** (`game pitch`, HTTP `act` with `"type":"pitch"`, while you pitch): during the windup (0.6-1.2 s; the
reply's `release_in_s` says when the ball leaves the hand) command the pitch: its TYPE and release SPEED in m/s
(fastball 34-42, sinker 34-41, cutter 33-39, slider 33-37.5, changeup 29-35.5, splitter 30-37, curveball 28-33.5),
the TARGET (X, Z) where the ball's centre should cross the plane y = 0 (-0.60 <= X <= 0.60, 0.20 <= Z <= 1.60 m) and,
optionally, its SPIN rate (rpm, 80-120 % of the type's default) and BREAK direction (where the spin's Magnus force
pushes the ball, in degrees from straight up towards first base, within 25 degrees of the type's default);
omitted, they are the type's default (`game spec` `match.pitching.arsenal`: the limits, the defaults and the spin
axis). The pitcher always releases at (-0.50, 16.80, 1.80) and aims the ball at the target through the documented
flight with the spin it throws. A later `pitch` replaces an earlier one until the release; at the release the last one
is thrown, with a seeded Gaussian scatter (standard deviations:
target 3 cm per coordinate, speed 0.3 m/s, spin rate 3 %, break direction 8 degrees). No pitch commanded at the
release is an automatic ball. A pitch command is refused after the release.

## Rules
The pitcher winds up for 0.6-1.2 s (the ball in its hand at the release point), then releases.
- **Count**: a pitch you take is a *ball* or a *called strike* (strike zone below); a pitch that touches the ground
  before the plate is a ball. A swing that misses is a strike; a foul ball is a strike, except that a foul with two
  strikes does not count. 3 strikes = strikeout, 4 balls = walk. A plate appearance that reaches 15 pitches without
  ending is an out. The count, the outs, the runners and the score a reply shows during a pitch are those before the
  pitch.
- **Strike zone**: the ball's centre crosses the plane y = 0 (the middle of the plate) with |x| <= 0.216 + 0.0365 m
  and 0.46 - 0.0365 <= z <= 1.07 + 0.0365 m (any part of the ball over the plate, between knee and chest height).
- **Batted balls**: foul if the first landing point is behind home or outside the foul lines (45 degrees either side
  of straight-away centre field; balls over the fence count where they cross it). A fair ball is judged against nine
  fixed fielders: a fielder at distance r0 + v_run * max(0, t - t_react) from a ball that is at most 2.4 m high at
  time t after contact gets to it. The first fielder to get to the ball decides: in the air = out (caught); on the
  ground, an infielder (P, C, 1B, 2B, SS, 3B) throws the batter out if fielding time + 0.6 s + distance to first
  base / 30 m/s <= 4.3 s, else it is an infield single; an outfielder fielding it = single, or double if the ball
  first landed beyond 80 m or was fielded after 5 s. A ball over the fence (100 m from home, 3 m high) = home run;
  off the wall = double. Fielder positions and speeds are in `game spec`.
- **Outs, runners and runs**: a strikeout, a ball caught in the air, a groundout and a plate appearance reaching 15
  pitches are outs; at 3 outs the half-inning ends. An out leaves the runners where they are. A walk puts the batter
  on first base and moves up only the runners it forces; a hit moves the batter and every runner as many bases as the
  hit (single 1, double 2, home run 4). Each runner who reaches home scores a run. Each half-inning of an extra inning
  begins with runners on first and second base.
- **End of a half-inning and of the game**: a half-inning also ends when the batting seat has 4 runs in it (runs
  past the limit on that play do not count). In the bottom of the last inning or of an extra inning the game ends
  as soon as the home seat leads (runs past the winning run count only on a home run).
- **The opponent**: another agent, with the same commands, limits and scatter as you. After each pitch both players see
  its record (pitch type, speed, where it crossed the plate, the outcome). The batter never sees the pitcher's command,
  and no player sees the spin a pitch was thrown with (the commanded spin with its scatter).
- **Deviations from the official rules** (MLB Official Baseball Rules, 2026 edition):
  - The game is 1 inning, plus extra innings (at most 1) if level (MLB: 9 innings, 7.01(a), and extra innings until
    decided, 7.01(b)); still level after them, the winner of the last pitch wins. Extra innings begin with runners on
    first and second base, as in the WBSC tie-break rule of international baseball (MLB: one runner on second,
    7.01(b)(2)).
  - Runners move only on walks and hits as above: no triples, extra bases taken, stolen bases, wild pitches, force
    outs, double plays or sacrifice flies (5.06, 5.09).
  - A half-inning also ends at 4 runs (MLB has no limit).
  - There is no batter's body: no hit by pitch (5.05(b)(2)).
  - Fouls are never caught and there are no foul tips: a foul never ends a plate appearance (5.09(a)(1), "Foul Tip").
  - Fair or foul is judged at the first landing point, also for short balls ("Fair Ball", "Foul Ball").
  - The strike zone is judged in one plane at the middle of the plate, at fixed heights ("Strike Zone").
  - The fence is a 100 m arc, 3 m high, at every angle (2.01 asks for at least 99 m at the lines and 122 m to centre).
  - Fielders do not move before contact and catch every ball they reach (no errors).
  - A plate appearance that reaches 15 pitches is an out (MLB has no limit).
  - The pitcher only chooses the pitch; the windup is fixed by the game. A pitch not commanded by the release is an
    automatic ball, like a pitch-clock violation (5.07(c)).

## Geometry and physics
Metres and game seconds; ground z = 0. Home plate is centred at the origin (0.432 m wide); +y points to the pitcher
and centre field, +x to first base (the catcher's right), z up. The bases are 27.43 m apart (first base at (19.40,
19.40)). The batter bats right-handed from the -x side. The pitcher releases the ball at (-0.50, 16.80, 1.80).
- **Ball** (0.145 kg, radius 0.0365 m): gravity 9.81, drag and Magnus lift,
  `a = g - K_D |v| v + K_L0 C_L(S) |v| (w_hat x v)` with `K_D = 0.00601 /m`, `K_L0 = 0.01718 /m`, spin factor
  `S = R |w| / |v|`, `C_L = 1.5 S` for S < 0.1, else `0.09 + 0.6 S`; the spin w decays with a 30 s time constant. A
  pitch's spin rate and axis are the pitcher's choice, with a scatter (Pitching above). A fastball loses about 3 m/s
  by the plate and reaches it about 0.4-0.5 s after the release; slower pitches take up to 0.6 s.
- **Swing rig**: the bat (0.84 m, 0.90 kg) turns about its knob, the pivot `P = (-0.66 + REACH, 0.25, HEIGHT)`. Bat axis
  direction `u(theta) = (cos th, sin th cos a, sin th sin a)` with a = PLANE; a point s metres from the knob is at
  `P + s u`. theta = 0 is square: the bat lies along +x over the plate (at y = 0.25) and moves towards the pitcher (+y)
  and, for a > 0, upwards. After the swing start: theta = -180 degrees (bat pointing -x, behind the batter), constant
  angular acceleration to omega = SPEED / 0.69 at theta = -30 degrees, constant omega to +90 degrees, then it slows to
  rest at +150 degrees. The bat is square 3.9741 / SPEED s after the swing start (0.117 s at 34 m/s), and at angle
  theta (between -30 and 90 degrees, in radians) `(5 pi / 3 + (theta + pi / 6)) / omega` s after it. Contact before
  square (theta > 0) pulls the ball towards left field (-x), after square towards right field; roughly, spray angle ~
  theta.
- **Bat radius** along s: knob 0.025 (s < 0.02), handle 0.0125 (s < 0.40), taper to 0.033 at s = 0.60, barrel 0.033 to
  the end at 0.84. The sweet spot is s = 0.69 (at square and REACH = 0 it is at x = +0.03). A pitch crossing at x meets
  the square bat at s = x + 0.66 - REACH.
- **Bat-ball collision** (an impulse model): along the contact normal the relative speed reverses with a COR
  `e = max(0.10, 0.50 - 4.0 (s - 0.69)^2)` and the bat's effective mass `1/M_eff = 1/0.90 + (s - 0.56)^2 / 0.048`;
  friction (mu 0.5, capped at rolling) gives the ball backspin when the bat hits under it. The contact normal points
  from the bat axis to the ball centre: the ball centre 1.5-3 cm above the bat axis gives a line drive or a fly ball
  (launch about 15-35 degrees), below it a ground ball; more than about 7 cm off (ball radius + barrel radius) is a
  miss. Squared up at SPEED 34, a fastball leaves at about 47-50 m/s.
- **Batted ball**: the same flight model; on the ground it bounces (keeping half its vertical and 75 % of its horizontal
  speed) and then rolls, slowing by 2.5 m/s^2.
