# Mini-golf putting, two players: program play

You are a golfer. You and another agent play the same round of 4 mini-golf putting holes on simulated greens (sloped,
enclosed by walls, one hole with an obstacle block; par 2, 2, 2, 3). Each of you has your own ball and the balls never
meet: a player plays a hole alone, from the start to the cup, then the other plays the same hole. The stroke scatter
is the same for both of you: your n-th stroke on a hole scatters exactly like your opponent's n-th stroke on that hole.
Your seat (`A` or `B`) and the first player are in `game spec` (`seat`, `match.first_player`). **Win with fewer total
strokes;** equal totals go to a sudden-death play-off (Rules). Both players receive this document.

## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have 60 minutes of real time
for the whole match, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; your opponent's turns and the simulation do not). `clock_left_s` is in every reply. **If your clock runs out, the
match ends as a loss.**

After each of your shots (except one that ends the match), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. Your goal is to win, not only to score: watch how your shots and your opponent's turns go and
adapt your program and strategy. After one player runs `game start`, the other has 30 minutes to start. The match is graded when your session ends: stay until it is
over.

## Write a program
You may write a program that observes, measures your shots in the images, computes your next command and sends it,
without a new model response for each shot. You may also act yourself. You stay in the loop: watch its log, and stop,
fix and restart it whenever needed. Use the reviews to improve it. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Players take turns: an action sent when it is not your turn is refused (HTTP 409); `game wait` returns when it is
  your turn (or the match is over).
- Your container: Python 3.12 with numpy, SciPy, Pillow and OpenCV (headless); 2 CPUs, 4 GB; no internet during
  the match. Keep your scripts, logs and notes in `/app/output/`.

## Interface
Use the `game` command, or, from a program, the same calls as HTTP with JSON at `http://sim:8000/<your seat>` (faster than starting a process):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the holes, cameras, limits, your clock |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | start the round; your clock starts |
| `game observe` | `POST /observe {}` | the current decision point and its camera image (`game` saves it to a file and prints the path; HTTP: `observation.image_png_b64`) |
| `game wait [MAX_S]` | `POST /wait {"max_s":S}` | return when it is your turn or the match is over (at most 60 s) |
| `game putt AIM_DEG SPEED` | `POST /act {"type":"putt","aim_deg":A,"speed":V}` | play one stroke (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review of your last stroke |

Every reply includes the current state (score, whose turn it is, `clock_left_s`) and the result of any shot
since your previous call.

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

Turns: a hole is played by one player at a time, who plays it out (a review after each stroke), then the other plays
it (as WMF 11.2). The first player plays hole 1 first; after that, whoever played a hole second plays the next hole
first (A B, B A, A B, B A when `A` is the first player). You see only your own ball; after each of your opponent's
strokes you are told its result, and both scores are in every reply. The lower total wins (WMF 9.2).

Tie: equal totals go to a sudden-death play-off (WMF 9.3): hole 1, then hole 2, and so on, are played again, one player
after the other with the starter still alternating; each play-off hole is scored alone, and the lower score on it
wins. If the match is still level after 4 play-off holes, the player with more chess-clock time left wins.

Deviations from the official rules (WMF Rulebook 2.3; R&A Rules of Golf 2023):
- The greens are enclosed by walls: no border line and no out of bounds (WMF 2.7, 8).
- No time limit per stroke (WMF 11.3): each player has a chess clock instead.
- The starter alternates from hole to hole instead of following the honour (R&A 6.4b); the first play-off hole continues
  the alternation instead of a coin flip (WMF 9.3).
- The play-off stops after 4 holes; then the chess clock decides (WMF 9.3 continues until there is a difference).

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
