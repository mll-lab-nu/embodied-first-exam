# Darts, 501: program play

You throw darts with a simple release mechanism standing at the throw line. Your opponent is a computer thrower; its
level is `match.opponent_level` in `game spec` (higher levels are stronger). **Win the match: best of 3 legs** of 501,
double-out, in visits of 3 darts; the players take turns. The opponent throws first in legs 1 and 3, you throw first
in leg 2.

## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have 60 minutes of real time
for the whole match, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; your opponent's turns and the simulation do not). `clock_left_s` is in every reply. **If your clock runs out, the
match ends as a loss.**

After each of your shots (except one that ends the match), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. Your goal is to win, not only to score: watch how your shots and your opponent's turns go and
adapt your program and strategy. The match is graded when your session ends: stay until it is
over.

## Write a program
You may write a program that observes, measures your shots in the images, computes your next command and sends it,
without a new model response for each shot. You may also act yourself. You stay in the loop: watch its log, and stop,
fix and restart it whenever needed. Use the reviews to improve it. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 4 CPUs, 8 GB; no internet during
  the match. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the board, the throw, the cameras, the opponent, the clock |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | start the match (your clock starts); the state and the image |
| `game observe` | `POST /observe {}` | the state and the camera image |
| `game throw YAW PITCH SPEED` | `POST /act {"type":"throw","yaw":YAW,"pitch":PITCH,"speed":SPEED}` | throw one dart (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | after each of your darts: your review |

Every reply includes the current state (legs and remaining scores, whose turn it is, `clock_left_s`) and the result of any shot
since your previous call.

**Observation** (`observe`): one PNG (`game` saves it as a file and prints its path; HTTP: `observation.image_png_b64`,
base64) with three camera tiles at the positions given in `game spec` (`image.tiles`: x, y, width, height):
- `oche` (900 x 900): your view from the throw line, eye at (0, 0, 1.80), looking at the bullseye;
- `board` (900 x 900): straight at the board face from 0.9 m in front of the bullseye; image right = your right,
  image up = up;
- `side` (1024 x 576): from your right (y = -3.4), looking along +y; image right = towards the board. The path of your
  last dart is drawn as small yellow balls, one every 10 ms.
The board shows the darts of the latest visit, yours or your opponent's, with yellow (dart 1), cyan (dart 2) and
magenta (dart 3) flights; they are pulled out when the next visit begins. You may observe at any time. There are no dart coordinates: find the darts in the images. A stuck dart's tip is 6 mm inside the
board; its flight is centred 13.5 cm behind the tip along the dart, so it appears a little above the point. The
cameras are pinholes with square pixels and the principal point at the tile centre; their poses, fields of view and
focal lengths are in `game spec`. The reply to a throw gives the caller's call ("treble 20", "double 16", "single 5",
"no score") and a board close-up taken right after the dart landed (`landed_image_file`; HTTP: `landed_image_b64`).

**Action** (`throw`): `YAW PITCH SPEED`, the dart's release from the fixed release point (0.40, 0.00, 1.68):
- `YAW` is the horizontal direction in degrees: 0 = straight at the board, along +x; positive = to your left;
- `PITCH` is the elevation above horizontal in degrees; positive = up;
- `SPEED` is the release speed in m/s.
Limits: |yaw| <= 20, -10 <= pitch <= 40, 4 <= speed <= 9. This is what the release mechanism does, not a target:
where the dart lands is decided by the flight. Your release is not perfect: it scatters around your command with
1 sigma = 0.35 degrees in yaw, 0.30 degrees in pitch and 0.8 % in speed, about 1.2 cm on the board in each direction.

## Rules
The WDF rules of 501, double-out. Each player starts each leg on 501, and each dart subtracts its score. The dart
that brings your score to exactly 0 must land in a double or the bull (the bull counts as a double); the first player
to check out wins the leg, and the first to win 2 legs wins the match. A dart that leaves you on 1, below 0, or on 0
without a double is a **bust**: the visit ends at once, and your score goes back to what it was at the start of the
visit. A leg nobody has checked out after 30 visits each goes to the lower remaining score; if the scores are level,
the player with more chess-clock time left wins the leg (the last-resort rule; both clocks are recorded exactly).

The opponent knows the board and the physics, throws at its own fixed speed with its own scatter (both in `game
spec`) and aims well for that scatter. It uses no clock time, so it wins a leg that is level at the visit cap. After
its visit, the replies give the caller's calls for its darts and its new score.

Deviations from the official rules (WDF Playing and Tournament Rules, 2018):
- The darts are thrown by a release mechanism with a stated scatter, not by hand, and there are no practice darts
  (WDF 1.02, 13.01).
- Darts always stick where the point reaches the board: no bounce-outs, fall-outs or wire deflections (WDF 1.05-1.06,
  3.02-3.03).
- The throw order is fixed (the opponent first in legs 1 and 3) instead of a throw for the bull (WDF 12.01-12.03).
- The 30-visit cap per leg, with the lower remaining score and then the chess clocks deciding, is a cost limit; the
  rules play on until someone checks out.

## Geometry and physics
Metres, seconds. The origin is on the floor at the centre of the throw line; +x points towards the board, +y to your
left, z up. The board face is the plane x = 2.37; the bullseye centre is at (2.37, 0, 1.73).
- A regulation board. Radii from the centre: bull 6.35 mm (50), outer bull 15.9 mm (25), treble ring 99 to 107 mm,
  double ring 162 to 170 mm. Beyond 170 mm a dart scores nothing, and beyond 225 mm it misses the board. There are 20
  segments of 18 degrees; 20 is at the top, centred on the vertical, and clockwise as you face the board they are: 20,
  1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5.
- The dart flies under gravity (9.81 m/s^2) and slows a little from air drag, a = -k |v| v. The drag constant k is
  fixed for the match and lies between 0.02 and 0.05 per metre, **but it is not given.**
