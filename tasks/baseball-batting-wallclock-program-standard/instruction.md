# Robot baseball batting: program play

You are the batter: a simulated swing rig holding a wooden bat stands at home plate, and a computer pitcher throws to
you; its level is `match.opponent_level` in `game spec` (higher levels are harder). **Bat through 5 plate appearances
and collect at least 4 bases** (walk or single 1, double 2, home run 4).

## Time
The world runs on its own in real time, slowed by a factor S (`timing.slowdown` in `game spec`; S = 1 is real speed):
one second of game time takes S seconds of real time. It does not wait for you: your thinking, tool calls, the model
API and your program's computation all take real time while the game goes on. All times below are game seconds.

The world is frozen only before `game start` and after each pitch until you send `game ready "WHY" "PLAN"` (a short
review: why the pitch ended and what you will change). Your goal is to collect bases, not only to make contact: watch how each pitch turns out and adapt your program and
strategy.
Frozen time does not advance the game, but it counts toward your session limit of 2 hours of real time, preparation
included. The game is graded when your session ends: stay until it is over.

## Write a program
You may write a player program that observes, finds and tracks the ball, predicts its flight and sends commands on
its own, without a new model response for each command. You may also act yourself. Prepare and test it before
`game start`, run it in the background, watch its log, and stop, fix and restart it whenever needed, also during a
pitch. Use the reviews to improve it. Only you send `game start` and `game ready`; actions are refused while the world
is frozen.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 4 CPUs, 8 GB; no internet during
  the game. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | cameras, slowdown, the pitcher's level and arsenal, the fielders, limits |
| `game status` | `GET /status` | the current state, no image |
| `game observe` | `POST /observe {}` | the newest camera frames (`game` saves the image to a file; HTTP: `observation.image_png_b64`) and the state |
| `game act T PLANE HEIGHT SPEED [REACH]` | `POST /act {"type":"swing","t":T,"plane":PLANE,"height":HEIGHT,"speed":SPEED,"reach":REACH}` | a swing command (below) |
| `game act none` | `POST /act {"type":"none"}` | cancel a swing that has not started (take the pitch) |
| `game wait DT` | `POST /wait {"dt":DT}` | wait DT seconds (0 < DT <= 1) |
| `game start` | `POST /start {}` | start the game |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review and resume |

Every reply includes the current state (score, game time, whether the world is running, your robot and command) and
the result of any shot or pitch since your previous call. If a pitch ends before an action takes effect, the action is dropped.

**Observation** (`observe`): a PNG of 2 rows x 4 columns of 480 x 360 tiles. Row 1 is a camera behind home plate (the
catcher's view) at (0, -2.4, 1.5) looking towards (-0.3, 12, 1.4), vertical field of view 18 degrees (focal length
1136.5 px); row 2 a camera beside the first part of the pitch path at (7, 14.6, 1.55) looking along -x (the pitcher on
the right), vertical field of view 30 degrees (focal length 671.8 px). Both are pinholes with the principal point at the
tile centre (image right = forward x up); `game spec` gives their exact poses and intrinsics. The columns are frames 30
ms apart, newest on the right; the reply gives each frame's time since the release (`view_times`, negative during the
windup, also stamped on the tiles) and its game time (`view_sim_times`). There are no ball coordinates: the ball is a
small bright white sphere (7.3 cm). Until the release it rests in the pitcher's hand at the release point. Every reply
also reports the game time, `t_since_release`, what you heard (the release, the ball in the mitt or on the bat) and
your current command.

**Action** (`act`): a swing command,
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

## Rules
The pitcher winds up for 0.6-1.2 s (the ball in its hand at the release point), then releases.
- **Count**: a pitch you take is a *ball* or a *called strike* (strike zone below); a pitch that touches the ground
  before the plate is a ball. A swing that misses is a strike; a foul ball is a strike, except that a foul with two
  strikes does not count. 3 strikes = strikeout (0 bases), 4 balls = walk (1 base). A plate appearance that reaches
  15 pitches without ending is an out (0 bases). The count and the bases a reply shows during a pitch are those before
  the pitch.
- **Strike zone**: the ball's centre crosses the plane y = 0 (the middle of the plate) with |x| <= 0.216 + 0.0365 m
  and 0.46 - 0.0365 <= z <= 1.07 + 0.0365 m (any part of the ball over the plate, between knee and chest height).
- **Batted balls**: foul if the first landing point is behind home or outside the foul lines (45 degrees either side
  of straight-away centre field; balls over the fence count where they cross it). A fair ball is judged against nine
  fixed fielders: a fielder at distance r0 + v_run * max(0, t - t_react) from a ball that is at most 2.4 m high at
  time t after contact gets to it. The first fielder to get to the ball decides: in the air = out (caught); on the
  ground, an infielder (P, C, 1B, 2B, SS, 3B) throws the batter out if fielding time + 0.6 s + distance to first
  base / 30 m/s <= 4.3 s, else it is an infield single; an outfielder fielding it = single, or double if the ball
  first landed beyond 80 m or was fielded after 5 s. A ball over the fence (100 m from home, 3 m high) = home run;
  off the wall = double. Bases: walk or single 1, double 2, home run 4. Fielder positions and speeds are in
  `game spec`.
- **The pitcher** throws the pitch types and mix in `game spec` (`match.pitcher.arsenal`: speed band, spin rate and
  axis of each; `match.pitcher.mix`: how often), in or just off the strike zone. The images show the pitch in flight,
  not its type.
- **Deviations from the official rules** (MLB Official Baseball Rules, 2026 edition):
  - There are no base runners, runs or innings: each plate appearance scores the bases the batter reaches, and there
    are no triples (5.05, 5.06).
  - There is no batter's body: no hit by pitch (5.05(b)(2)).
  - Fouls are never caught and there are no foul tips: a foul never ends a plate appearance (5.09(a)(1), "Foul Tip").
  - Fair or foul is judged at the first landing point, also for short balls ("Fair Ball", "Foul Ball").
  - The strike zone is judged in one plane at the middle of the plate, at fixed heights ("Strike Zone").
  - The fence is a 100 m arc, 3 m high, at every angle (2.01 asks for at least 99 m at the lines and 122 m to centre).
  - Fielders do not move before contact and catch every ball they reach (no errors).
  - A plate appearance that reaches 15 pitches is an out (MLB has no limit).

## Geometry and physics
Metres and game seconds; ground z = 0. Home plate is centred at the origin (0.432 m wide); +y points to the pitcher
and centre field, +x to first base (the catcher's right), z up. The bases are 27.43 m apart (first base at (19.40,
19.40)). The batter bats right-handed from the -x side. The pitcher releases the ball at (-0.50, 16.80, 1.80).
- **Ball** (0.145 kg, radius 0.0365 m): gravity 9.81, drag and Magnus lift,
  `a = g - K_D |v| v + K_L0 C_L(S) |v| (w_hat x v)` with `K_D = 0.00601 /m`, `K_L0 = 0.01718 /m`, spin factor
  `S = R |w| / |v|`, `C_L = 1.5 S` for S < 0.1, else `0.09 + 0.6 S`; the spin w decays with a 30 s time constant. A
  pitch's spin rate and axis depend only on its type (spin axis given for a ball moving along -y). A fastball loses
  about 3 m/s by the plate and reaches it about 0.4-0.5 s after the release; slower pitches take up to 0.6 s.
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
