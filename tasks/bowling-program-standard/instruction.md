# Ten-pin bowling: program play

You are the bowler. Bowl one game of ten-pin bowling (10 frames) on a simulated lane. **Succeed by scoring 200 or
more.** No practice balls.

## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have 60 minutes of real time
for the whole game, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; the simulation does not). `clock_left_s` is in every reply. **If your clock runs out, the
game ends and counts as a failure.**

After each of your shots (except one that ends the game), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. Do as well as you can: reaching the success line above is the minimum. Watch how your shots go and adapt
your program and strategy. The game is graded when your session ends: stay until it is
over.

## Write a program
You may write a program that observes, measures your shots in the images, computes your next command and sends it,
without a new model response for each shot. You may also act yourself. You stay in the loop: watch its log, and stop,
fix and restart it whenever needed. Use the reviews to improve it. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 4 CPUs, 8 GB; no internet during
  the game. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the lane, cameras, limits, your clock |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | start the game; your clock starts |
| `game observe` | `POST /observe {}` | the current decision point and its camera image (`game` saves it to a file and prints the path; HTTP: `observation.image_png_b64`) |
| `game roll BOARD ANGLE_DEG SPEED RPM AXIS_DEG` | `POST /act {"type":"roll","board":B,"angle_deg":A,"speed":V,"rpm":R,"axis_deg":X}` | bowl one ball (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review of your last ball |

Every reply includes the current state (score, `clock_left_s`) and the result of any shot since your previous
call.

**Observation** (`observe`): the decision point (`frame`, `ball` 1-3, `fresh_rack`, `pins_standing`, and your previous
ball as `last_ball`: what you played and how many pins fell) and one PNG of 1960 x 1620 pixels with four camera views
(their pixel rectangles are in `game spec`, `image.tiles`):
- left column, top: `approach` (960 x 540): your eye on the approach, 2.2 m behind the foul line over the centre of the
  lane, 1.55 m up, looking down the lane, pitched 5 degrees down;
- left column, middle: `pindeck` (960 x 540): the pins standing now, seen from 2.4 m in front of the head pin, 0.95 m
  up, pitched 17 degrees down;
- left column, bottom: `pindeck_after` (same camera): the deck right after your previous ball settled, before the
  fallen pins were swept (black before your first ball);
- right, from x = 960: `lane` (1000 x 1360): the lane from straight above in four stacked panels of 5 m each (top
  panel: from 0.5 m behind the foul line; bottom: the pin deck); in each panel image right = towards the pins and image
  up = left. The path of your previous ball is drawn as yellow dots, one every 1/30 s.

There are no ball or pin coordinates and no oil numbers: find the pins, the ball's path and the lane markings in the
image. After each ball you are told how many pins fell, not which. All cameras are pinholes with square pixels and the
principal point at the centre of their view; their poses and fields of view are in `game spec`.

**Action** (`roll`): the release; what the ball then does is physics.
- `BOARD`: where the ball's centre is laid down on the lane, 35 cm past the foul line. The lane is 39 boards
  (27.03 mm each) wide, counted from the right gutter: board 1 is the rightmost, 20 the centre, 39 the leftmost (as
  seen facing the pins). Fractions are fine; 1 to 39.
- `ANGLE_DEG`: the launch direction, degrees from the lane's axis; + = towards the left (higher boards); -10 to 10.
- `SPEED`: ball speed at release, m/s; 3 to 11.
- `RPM`: rev rate at release, revolutions per minute; 0 to 700 (0 = no revs, a straight ball).
- `AXIS_DEG`: axis rotation: the spin axis is horizontal; 0 = end-over-end roll (no hook), 90 = the axis points along
  the launch direction (all side roll, the most hook); + hooks the ball to the left, - to the right; -90 to 90.
- Each executed value scatters around what you asked for (Gaussian, standard deviations: board 1.0, angle 0.24
  degrees, speed 1.5 %, rev rate 4 %, axis 2 degrees).
The reply reports how many pins fell, strike, spare or gutter, and whether the frame is finished.

## Rules
Ten-pin rules as in the USBC Playing Rules 2025-2026. Scoring: a strike scores 10 plus your next two balls, a spare 10
plus your next ball; a strike or spare in the 10th frame gives bonus balls (three balls at most); 300 is perfect. Each
frame's first ball (and in the 10th frame each ball after a strike or spare) gets a fresh rack. After the first ball of
a frame the fallen pins are swept away; the pins still standing stay where they are, even if they were moved. A pin
counts as down if it tilts more than 20 degrees or leaves the lane surface (into a gutter, the pit or against a side
wall); a pin standing anywhere on the lane counts as standing. A ball that enters a gutter before it reaches the pins
scores no pins, and the pins it moves are respotted (USBC 6b.1).

Deviations from the official rules (USBC Playing Rules 2025-2026):
- Pin down: tilted more than 20 degrees or off the lane surface (approximates USBC 6a).
- No fouls: the release is a set of numbers and the ball starts past the foul line (USBC 5a does not apply).
- No rear cushion: the pit behind the pin deck is open (USBC 6b.2 does not apply).

## Geometry and physics
Metres, seconds; rigid-body physics. The lane frame: x along the lane from the foul line towards the pins, y across
(+ = left), z up; lane surface z = 0.
- Regulation lane: 18.29 m from the foul line to the head pin, 1.054 m wide, gutters on both sides, then the pin deck,
  the pit behind it and side walls (kickbacks) that pins bounce off. Markings: the foul line, aiming arrows on boards
  5, 10, ..., 35 between 3.9 and 4.6 m (the centre one furthest), dots at 2.13 m.
- Pins: 38.1 cm tall, 1.53 kg, standing in a triangle 30.48 cm apart: pin 1 (the head pin) in front at the centre, 2
  and 3 behind it (2 on the left, 3 on the right as you see them), then 4-5-6, then 7-8-9-10 (7 far left, 10 far
  right).
- Ball: 21.8 cm, 7 kg. The front part of the lane is oiled (low friction: the ball skids), the back end is dry (high
  friction). A ball with side roll skids straight on the oil, then hooks where the friction rises and finally rolls.
  The oil runs further down the middle boards than on the outside boards, so a ball out towards the gutters meets the
  dry lane sooner. How long the oil is and how much the ball hooks: find out from your balls' paths.
