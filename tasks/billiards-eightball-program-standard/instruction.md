# 8-ball: program play

You play one rack of 8-ball on a simulated 7-ft pool table against a computer opponent; its level is
`match.opponent_level` and who breaks is `match.first_player` in `game spec` (set by the configuration). **Win the
game: clear your group (solids or stripes), then pot the 8 into the pocket you call.** Every game ends with a winner.

## Time
Nothing moves while you think: the world waits for your shot. Time is a chess clock: you have 60 minutes of real time
for the whole game, and your clock runs only on your turn (thinking, tool calls, the model API, your programs and
your reviews all count; your opponent's turns and the simulation do not). `clock_left_s` is in every reply. **If your clock runs out, the
game ends as a loss.**

After each of your shots (except one that ends the game), send `game ready "WHY" "PLAN"` (a short review: why the shot went well or badly and what you
will change) before the game goes on. Your goal is to win, not only to score: watch how your shots and your opponent's turns go and
adapt your program and strategy. The game is graded when your session ends: stay until it is
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
| `game spec` | `GET /spec` | table, pockets, cameras, opponent level, who breaks, clock |
| `game status` | `GET /status` | the current state, no images |
| `game start` | `POST /start {}` | start the game and your clock; shows the table |
| `game observe [AIM_DEG]` | `POST /observe {"aim":AIM_DEG}` | the state and two camera images (`game` saves them to files and prints their paths; HTTP: `observation.images_png_b64`) |
| `game shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=C]` | `POST /act {"type":"shoot","aim_deg":A,"speed":V,"spin_x":X,"spin_y":Y,"cue_x":CX,"cue_y":CY,"call":C}` | play a shot (below) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | hand in the review after your shot |

Every reply includes the current state (your group, the opponent's group and the balls left in each, whose turn it is, `clock_left_s`) and the result of any shot
since your previous call.

**Observation** (`observe`): the state in every reply says your group and the opponent's (`open`, `solids`,
`stripes`, with `(on the 8)` once a group is cleared), the balls left in each group, and, on your turn, `break_shot`,
`ball_in_hand` (none, above the head string, or anywhere), `on_the_8` and `call_required` (every shot but the break).
`observe` adds `balls_on_table` (their numbers) and two PNG images (`top`, `sight`). There are no ball coordinates:
find the balls in the images. Solids (1-7) are coloured all over, the 8 is black, stripes (9-15) are white with a
coloured band (white caps above and below it in the top view); each object ball shows its number on a white disc, and
the cue ball is plain white.
- **top** (1120 x 640 px): a fixed overhead camera 2.6 m above the table centre looking straight down; image right =
  +y, image down = +x.
- **sight** (960 x 540 px): an eye 0.75 m behind the cue ball and 0.32 m above the cloth, looking at the cloth 1.0 m
  ahead of the cue ball along the sighting direction AIM_DEG (default: towards the table centre); the cue stick is drawn
  along it, also in the top view. Observing plays nothing. With the cue ball off the table it looks from the head spot.

Both are ideal pinhole cameras; their poses and intrinsics are in the observation's `cameras` (the top camera also in
`game spec`): OpenCV axes (camera x = image right, y = image down, z = viewing direction),
`p_cam = R_world_to_camera @ (p_world - position_world)`, `u = fx * x / z + cx`, `v = fy * y / z + cy`. A ball's image
centre is the projection of its centre, at height z = R above the cloth.

**Action** (`shoot AIM_DEG SPEED [SPIN_X SPIN_Y] [cue=X,Y] [call=C]`): the cue stick's state at impact, not a
target, with the call.
- `AIM_DEG`: the direction the cue stick points and strikes in the table plane, degrees counter-clockwise from +x
  (0 = +x, 90 = +y). With a centre hit the cue ball leaves in exactly this direction.
- `SPEED`: the cue stick's speed at impact, 0.3-7 m/s. A centre hit sends the cue ball off at about 1.54 x SPEED. On
  an empty table a centre-hit cue ball travels (cushions included) about 0.6 m at SPEED 0.3, 1.6 m at 0.5, 3.3 m at 1.0
  and 5.6 m at 2.0 before it stops.
- `SPIN_X SPIN_Y` (default 0 0): where the tip hits the cue ball, in ball radii from its centre: SPIN_X > 0 = right
  english, SPIN_Y > 0 = follow (topspin), SPIN_Y < 0 = draw (backspin); sqrt(SPIN_X^2 + SPIN_Y^2) <= 0.5. Sidespin
  turns the cue ball's start direction a little (squirt: about 1.2 degrees clockwise, seen from above, for SPIN_X = 0.3).
- `cue=X,Y` (HTTP `cue_x`, `cue_y`): only with ball in hand: place the cue ball at (X, Y) before the shot. It must lie
  on the table (R <= X <= W - R, R <= Y <= L - R) and cannot touch a ball or lie in a pocket opening; with the ball in
  hand above the head string it must lie at Y < L/4. Without it the cue ball stays where it is; if it was potted it goes
  on the head spot (or the nearest free point on the long centre line), or, in hand above the head string, on
  (W/2, L/4 - 0.05) (or the nearest free point there).
- `call=C` (HTTP `call`): required on every shot except the break, refused on the break. C is `BALL:POCKET` or
  `safety`: BALL is the number of a ball you may hit first, POCKET one of `lb` (0, 0), `rb` (W, 0), `lc` (0, L/2),
  `rc` (W, L/2), `lt` (0, L), `rt` (W, L) (l/r: x = 0 / W; b/c/t: y = 0 (head end) / L/2 / L (foot end); the letters
  are not image directions). Examples: `call=3:rc`, `call=8:lt`, `call=safety`.

An action that breaks these rules is refused (HTTP 400) and changes nothing. Every shot is executed with a small random
scatter: about 0.06 degrees in direction, 2 % in speed and 0.01 ball radii in tip offset (one standard deviation). The
reply reports what happened: where the cue ball was placed, the call and whether it was made, the first ball hit, the
balls potted and their pockets, a foul and its reason, groups assigned, whether you keep the turn, and the game's
end.

## Rules
One rack of 8-ball under the WPA Rules of Play (effective 2025-09-15), 8-Ball, with the deviations at the end:
- The 15 object balls are racked in a triangle with the front ball on the foot spot, the 8 in the middle of the third
  row and one solid and one stripe in the back corners (the order of the others depends on the seed).
- **Break**: the breaker has ball in hand above the head string (Y < L/4; the head string itself is not part of that
  area); the break is not called. It is legal if a ball is potted or at least four object balls reach a cushion. After a
  legal break that pots a ball (the 8 included: it is spotted again) the breaker shoots again; the table is open after
  the break. After an illegal break (no ball potted and fewer than four object balls to a cushion) the balls are
  racked again in the same order and the other player breaks. A scratch, or an object ball driven off the table, on an
  otherwise legal break is a foul: the other player has ball in hand above the head string.
- **Spotting**: a spotted ball goes on the long centre line as close as possible to the foot spot, between the foot spot
  and the foot rail; if that is blocked, as close as possible above the foot spot.
- **Called shots**: every other shot is called: a ball and a pocket (`call=BALL:POCKET`), or `call=safety`. The called
  ball must be one you may hit first. You stay at the table only if the called ball is pocketed in the called pocket on
  a legal shot. Other balls pocketed on a legal shot stay down and count for whoever's group they belong to, but do not
  keep you at the table; a safety ends your turn, and balls pocketed on it stay down.
- **Open table and groups**: on an open table you may hit any object ball except the 8 first, unless a group has been
  completely pocketed: then you may claim that group and shoot (and call) the 8. The groups are decided when a player
  legally pockets its called ball: that ball's group (solids 1-7 or stripes 9-15) becomes the shooter's, the other
  group the opponent's. Until then the table stays open.
- **Fouls** (after the break): the cue ball is potted; an object ball is driven off the table; no ball is hit; the first
  ball hit is not one you may hit first; or after the first contact no ball is potted and no ball reaches a cushion.
  Balls potted on a foul stay down. After a foul the other player has ball in hand anywhere on the table.
- **Bad play from above the head string**: with the cue ball in hand above the head string (after a foul on the
  break), the cue ball must either cross the head string or first contact a ball on or below it (Y >= L/4). If the
  first ball it contacts lies above the head string (Y < L/4) and it has not crossed the head string before that
  contact, the shot is a foul.
- **The 8**: once your group is cleared you are on the 8 and call it into a pocket. You win by pocketing it in the
  called pocket on a legal shot. You lose if you pocket it before your group is cleared, in a pocket you did not call
  (or on a safety), on a foul (for example while the cue ball is potted), or drive it off the table.
- Shot limit: 60 shots each; a player who has used all 60 passes; when both have, the player with fewer balls left in its
  group wins (an open table counts as 7). If still level at the cap, the player with more chess-clock time left wins.
  Both players' shots are executed with the same scatter.
- Who breaks is fixed by the configuration (`match.first_player`). The opponent is a scripted player: it calls and
  plays the easiest direct pot of its group with an aiming error, and plays safe when it has none; higher levels aim
  better and choose safer shots. Its chess clock never runs (it keeps its 60 minutes), so a tie at the shot limit goes
  to it.
- **Deviations from the WPA rules**: the 8 pocketed on the break is always spotted (no re-break option); after an
  illegal break the other player always re-racks and breaks (the other options do not exist); a foul on the break gives
  ball in hand above the head string (no option to accept the table); with ball in hand above the head string you cannot
  ask for a ball above it to be spotted; every call is explicit (no "obvious" shots); the action has no cue elevation,
  so there are no jump or massé shots; the cue ball cannot be placed touching a ball or in a pocket opening; a 60-shot
  limit per player, decided by the balls left and then by the chess clocks, replaces the stalemate
  rule.

## Geometry and physics
Metres, world frame, z up.
- The playing surface (inside the cushion noses) is 0 <= x <= W = 0.9906, 0 <= y <= L = 1.9812; the cloth is at z = 0.
  Balls: radius R = 0.028575, all the same mass.
- Six pockets (centres and radii in `game spec`): corners at (0, 0), (W, 0), (0, L), (W, L), sides at (0, L/2) and
  (W, L/2). The openings between the cushion jaws are about 11.7 cm wide at the corners and 13.5 cm at the sides; side
  pockets accept only balls that come in fairly straight (within about 45 degrees of the cushion normal).
- The head spot is (W/2, L/4), the foot spot (W/2, 3L/4); the head string is the line y = L/4 (the head end is
  y = 0, the foot end y = L). Diamonds on the rails mark every L/8 along the long rails and every W/4 along the short
  rails.
- Physics: sliding friction 0.2, rolling resistance 0.01, ball-ball restitution 0.95, cushion
  restitution 0.85. A ball struck without spin slides first and then rolls; after a full-ball hit a stun cue ball
  stops, a follow ball keeps rolling forward and a draw ball comes back. In a cut shot the object ball leaves along the
  line of centres at contact (ghost-ball aim: send the cue ball to the point 2R behind the object ball on the line from
  the pocket through the object ball), slightly thrown by friction.
