# Mini-golf putting: program play

You are the golfer. Play a round of 4 mini-golf putting holes on simulated greens (sloped, enclosed by walls, one hole
with an obstacle block); par is 2, 2, 2, 3 (par 9). **Succeed by finishing the round in 9 or fewer strokes;** fewer
strokes is better. One round, no practice green.

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
| `game spec` | `GET /spec` | the holes, cameras, limits, your clock |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | start the round; your clock starts |
| `game observe` | `POST /observe {}` | the current decision point and its camera image (`game` saves it to a file and prints the path; HTTP: `observation.image_png_b64`) |
| `game putt AIM_DEG SPEED` | `POST /act {"type":"putt","aim_deg":A,"speed":V}` | play one stroke (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review of your last stroke |

Every reply includes the current state (score, `clock_left_s`) and the result of any shot since your previous
call.

**Observation** (`observe`): the decision point (`hole`, `par`, `stroke`: the number of the stroke you are about to
play, and your previous stroke on this hole as `last_putt`: what you played and what happened) and one PNG of
2000 x 1000 pixels with three camera views (their pixel rectangles are in `game spec`, `image.tiles`):
- left column, top: `behind` (800 x 500): crouched 2.0 m behind the ball along -x, 1.1 m above the green there,
  looking along +x (straight down the green, heading 0 degrees), pitched 14 degrees down;
- left column, bottom: `side` (800 x 500): fixed for each hole, beyond the green's left wall at mid-green (its position
  is in `game spec`, `match.holes[].side_camera_pos_m`), looking along -y (heading -90 degrees), pitched 12 degrees
  down: view right is +x, the far end of the green;
- right, from x = 800, top: `overhead` (1200 x 600): straight down over the whole green (view right = +x, view up =
  +y); the path of your previous stroke on this hole is drawn as yellow dots, one every 0.1 s.

There are no ball or cup coordinates and no slope numbers: find the ball (white, 4.3 cm), the cup (black disc with a
white rim, 10.8 cm across, with a yellow flagstick and a red flag) and the walls in the image. White grid lines on the
green every 0.5 m follow the surface (they bend over bumps and ridges); mowing stripes are 1 m wide. All cameras are
pinholes with square pixels and the principal point at the centre of their view; their fields of view and focal
lengths, the overhead camera's height for each hole and each green's size are in `game spec`.

**Action** (`putt`):
- `AIM_DEG`: where the putter face points, i.e. the ball's start direction, in degrees in the green's frame: 0 = +x
  (straight down the green, away from the end the ball starts at), positive = counter-clockwise seen from above (90 =
  +y, to the left as seen from behind), negative = clockwise; -180 to 180. It is not relative to the cup. Walls can be
  used for bank shots.
- `SPEED`: the ball's initial rolling speed, m/s; 0.05 to 6.0.
- The executed stroke scatters around what you asked for: about 0.3 degrees in direction and 1.5 % in speed.
The reply reports the result (`holed`, `stopped`, `lipped out`, `rolled over the edge of the cup`), how often the
ball hit a wall or block, and, when the hole is finished, its score.

## Rules
Scoring as in minigolf (WMF Rulebook 2.3, 9.1): the score is the total number of strokes, and fewer is better; a hole
not holed after 6 strokes is picked up and scores 7. Each hole starts from its own fixed spot; the ball is played from
where it stopped.

Deviations from the official rules (WMF Rulebook 2.3; R&A Rules of Golf 2023):
- The greens are enclosed by walls: no border line and no out of bounds (WMF 2.7, 8).
- No time limit per stroke (WMF 11.3): each player has a chess clock instead.

## Geometry and physics
Metres, seconds.
- Each green has its own frame: x in [0, L] along the green, y in [-W/2, W/2] across it, z up (sizes in `game spec`).
  The surface is smooth but not flat: tilts, bumps, hollows and ridges of up to a few centimetres to a decimetre.
- The ball rolls without slipping: slopes accelerate it downhill ((5/7) g sin(slope), g = 9.81 m/s^2); rolling
  resistance slows it at a constant rate. Green speed: stimpmeter 10 ft, i.e. on a flat green a ball starting at
  1.83 m/s stops after 3.05 m. The ball comes to rest when it is slow and the slope cannot move it.
- Walls and blocks: the ball rebounds, keeping about 70 % of its speed into the wall and about 92 % along it.
- The cup: a ball whose centre passes over the cup drops if it is slow enough (straight at the centre, up to about
  1.7 m/s; less when it only catches the edge); faster, it lips out or rolls over the edge.
