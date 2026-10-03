# Robot basketball shooting: program play

You are the shooter: a simulated Franka Panda arm on a 1 m pedestal with a ball cup, which works as a launcher (you
choose the release, it throws), on a basketball court. You take **10 shots**: two from each of five spots, in order
(spot 1 twice, then spot 2 twice, ... spot 5 twice), from mid-range to beyond the three-point line. Nobody tells you
where the spots are: you see the court, the hoop and the defender only through cameras. **Success: at least 6 makes
of 10.**

## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have 60 minutes of real time
for the whole round, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; the simulation does not). `clock_left_s` is in every reply. **If your clock runs out, the
round ends and counts as a failure.**

After each of your shots (except one that ends the round), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. Do as well as you can: reaching the success line above is the minimum. Watch how your shots go and adapt
your program and strategy. The round is graded when your session ends: stay until it is
over.

## Write a program
You may write a program that observes, measures your shots in the images, computes your next command and sends it,
without a new model response for each shot. You may also act yourself. You stay in the loop: watch its log, and stop,
fix and restart it whenever needed. Use the reviews to improve it. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 4 CPUs, 8 GB; no internet during
  the round. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the court, the shooter, the ball, the cameras, the clock |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | start the round (your clock starts); the state and the image |
| `game observe` | `POST /observe {}` | the state and the camera image |
| `game shoot ANGLE SPEED SPIN YAW` | `POST /act {"type":"shoot","angle_deg":ANGLE,"speed":SPEED,"spin_hz":SPIN,"yaw_deg":YAW}` | take one shot (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | after each shot: your review |

Every reply includes the current state (makes so far, `clock_left_s`) and the result of any shot since your previous
call.

**Observation** (`observe`): one PNG (`game` saves it as a file and prints its path; HTTP:
`observation.image_png_b64`, base64), a 2 x 2 grid of 640 x 480 tiles. Top left `shooter_wide` and top right
`shooter_zoom`: two cameras on your shooter (the same position, behind and above the arm, looking along the shooter's
heading, pitched up 8 degrees; vertical field of view 55 and 16 degrees). Bottom left `broadcast`, bottom right
`baseline`: fixed cameras overlooking the court. There are no hoop, ball or shooter coordinates: judge them from the
images. `game spec` gives every camera's pose and intrinsics (pinholes, no distortion; for the two shooter cameras the
pose in the shooter's frame), so image points can be turned into rays. The reply to a shot gives its `result`
(`made`, `rim`, `backboard`, `blocked`, `airball`), `how` it went in, what the ball `touched`, and a picture strip of
it (`result_image_file`; HTTP: `result_image_b64`): 4 frames 100 ms apart around the ball's closest approach to the
hoop, from a side camera at the hoop (row 1) and your `shooter_zoom` (row 2).

**Action** (`shoot`): `ANGLE SPEED SPIN YAW`:
- `ANGLE`: release elevation above horizontal, degrees, 20 to 80;
- `SPEED`: release speed, m/s, 3 to 14;
- `SPIN`: revolutions per second, -5 to 5; positive = backspin (Magnus force, below), negative = topspin;
- `YAW`: the release direction relative to the shooter's current heading, degrees, -35 to 35, **positive = to the
  left** (counter-clockwise seen from above). The shooter is parked facing roughly, **not exactly**, towards the hoop
  (a few degrees off, different at every spot).
The launcher is good but not perfect: each shot's release scatters by about 0.5 % in speed, 0.4 degrees in elevation
and direction, and 0.15 rev/s in spin (1 sigma).

## Rules
A shot is **made** when the ball enters the basket from above and passes through it (FIBA Art. 16.1.1); every make
counts 1, from any spot. A defender stands between you and the hoop, on the line from you to it,
`min(3.0 m, 0.55 x your distance to the hoop)` from you (axis to axis), with its hands up (the hands' top at 2.55 m);
it does not move. A ball that touches the defender first is **blocked** and does not count.

Deviations from the official rules (there is no official shooting contest in the FIBA or NBA rules; the closest
standard is the FIBA 3x3 Shoot-out Contest, 10 shots, each make worth 1):
- A shooting contest: 10 shots from five spots, instead of a game.
- Every make counts 1, from any spot, instead of 2 or 3 points by the release area (FIBA Art. 16.2.1).
- NBA court markings and equipment sizes (FIBA Art. 2 uses a 6.75 m three-point arc and a 1.80 m backboard).
- A static defender with its hands up, and a ball that touches it first does not count, instead of live defence.
- The shots are thrown by a launcher with a stated scatter; time is a chess clock instead of a shot clock.

## Geometry and physics
Metres, seconds. NBA court markings. The hoop's centre is at (0, 0, 3.048) (rim height 3.048 m); the floor is z = 0;
the court is y < 0 (the baseline is y = +1.60 behind the backboard). Rim inner diameter 0.457 m (orange, 16 mm tube);
backboard 1.83 x 1.07 m, its front face 0.381 m behind the rim centre, bottom edge at 2.90 m, with a red border and a
red 0.61 x 0.45 m shooter's square above the rim. Court lines (white, 5 cm): lane 4.88 m wide, free-throw line at
y = -4.19 with its 1.8 m circle, three-point arc 7.24 m from the hoop centre (straight 6.71 m from the centre line in
the corners), sidelines x = +-7.62.
- The shooter's frame: origin on the floor at the pedestal axis, +x = its heading, z up. The ball (radius 0.1195 m,
  size 7, 0.62 kg) is released at (0.503, 0, 2.166) in that frame, rotated with `YAW` about the pedestal axis (the arm
  turns to aim), 0.45 s after the throw starts.
- Flight: gravity 9.81; air drag F = -0.01454 |v| v N; Magnus F = 0.00419 (omega x v) N (omega in rad/s; backspin
  turns about the horizontal axis d x z, d the release direction). The floor, rim, bracket and backboard are hard and
  bouncy (restitution about 0.8 floor, 0.6 rim, 0.65 backboard); the net is visual only.
