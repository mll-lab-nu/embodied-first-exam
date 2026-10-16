# Curling: program play (match)

You play curling against a scripted opponent (you are seat `A`). Two teams slide granite stones down a sheet of ice towards the house, 4 ends of 5 stones per team; you skip one team and throw every one of its stones (release speed, direction and spin); in the `match` format the other team is a scripted computer team, in the `duel` format another player.
This is RoboOlympics task `curling-match-program-standard` (revision `curling-4`), one frozen instance: the scripted opponent at level 3, a chess clock of 60 minutes for each side; the seed is fixed and never shown. The simulator service is at `http://localhost:8000`.

## Time
Nothing moves while you think: the world waits for the player whose turn it is. Each player has a chess clock of 60 minutes of real time, running only on its own turn (thinking, tool calls, your programs and your reviews all count). **If your clock runs out, you lose.**

After each of your actions (except one that ends the match), send `game ready "WHY" "PLAN"` (a short review) before the game goes on.
**Send `game start` within 1800 s of real time after the match service starts (`start.window_s` in `game spec`), or you lose the match** (`no_show`, a valid result, success 0). No chess clock runs before the match starts: read `game spec` and prepare your program first; the camera images come with the match (`game observe` answers 409 until then).
The match is graded when your session ends: stay until it is over. **If your session ends before the match is over, you lose the match** (a valid result, success 0), also if you never sent `game start`.

## Write a program
You may write a program that observes, measures in the images, computes your next action and sends it, without a
new model response for each action. You stay in the loop: watch its log, and stop, fix and restart it whenever
needed. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy and Pillow; the network reaches only your model's API and the package registries. Keep your scripts, logs
  and notes in `/app/output/`.

## Interface
Use the `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras with their intrinsics, the rule constants |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait` | `POST /wait {"timeout_s": 60}` | block until it is your turn (or the match is over) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | one action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | your review after each of your actions |

The reply to an action also carries images of its result, in the format of `game observe` (`observation.image_png_b64` and `observation.tiles`; `game` saves them in `/app/output/views/`): the reply to each of your throws shows the house camera (600 x 1000) right after your stone and every stone it moved came to rest, before the next stone (in the match format the scripted team's reply follows inside your action, so this is the only image of where your stone stopped if the reply moves it).

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one
action in flight, or more than 20 requests per second or 4 open requests from your seat (empty body: retry more slowly).

## Rules
- two teams slide granite stones down a sheet of ice towards the house, 4 ends of 5 stones per team; you skip one team and throw every one of its stones (release speed, direction and spin); in the `match` format the other team is a scripted computer team, in the `duel` format another player.
- `world`: metres; the release point (the hack) is the origin, +y runs down the sheet towards the far house, +x is to the right as seen from the hack, z up
- `sheet`: far hog line y = 32.004, tee line y = 38.405 (the tee, the centre of the house, is at (0, 38.405)), back line y = 40.234; the house has radius 1.829 with rings at 1.219 and 0.610 and the button at 0.152; the sheet spans |x| <= 2.375; stones have radius 0.145 and mass 19.96 kg (top of a stone at z = 0.112, handle top at 0.146)
- `throw`: game act '{"type": "throw", "speed": 2.5, "angle": 2.0, "spin": "ccw"}' (HTTP POST /act with that body): the stone's state at release, not a target. speed: release speed at the hack, 0.5-4.0 m/s; angle: release direction in degrees from the centre line, + = to the right (+x), |angle| <= 5; spin: ccw (counter-clockwise seen from above) curls the stone to the left (-x), cw to the right (+x). The numbers are rounded to 6 decimals. Once released the stone cannot be stopped, steered or swept: the simulation runs it, and every stone it moves, to rest inside the action (in the match format the scripted team's stones follow inside the same action). The delivery machine adds only the declared execution scatter (execution_noise_1sigma); it reads nothing of the sheet and never aims or corrects. Refused, changing nothing: a value out of range, not a number, a missing or extra field (HTTP 400); a throw out of turn or before the review of your last action (409); a second action while one is in flight (429)
- `execution_noise_1sigma`: {"speed_m_s": 0.004, "angle_deg": 0.03, "note": "about +-14 cm in length for a draw and +-2 cm sideways at the house; each player's execution noise is independent of the opponent's within a match (its own seeded stream, its size the thrower's own); the two matches of a duel pair (the same seed, the first player swapped) swap the noise sequences, so over the pair both players meet the same draws", "draw": "every throw: the release speed becomes speed + 0.004 z1 m/s (then kept within 0.1-4.05 m/s) and the direction angle + 0.03 z2 degrees, with z1, z2 independent standard normal numbers, new for every stone; they come from the thrower's own random stream, keyed by the match seed, the end, the stream (match: you 1, the scripted team 2; duel: the player who throws the first stone of end 1 1, the other 2) and the stone's number in the end; the scripted team's sizes are its level's (level 1: 0.020 m/s, 0.08 degrees; level 2: 0.010 m/s, 0.05 degrees; level 3: 0.006 m/s, 0.035 degrees); the spin is never perturbed"}
- `ice`: the speed v decreases at a(v) = kd x (0.00200985 / (v + 0.06385782) + 0.00626286) x 9.80665 m/s^2, where kd is this sheet's deceleration scale: one number for the whole match and for both teams, somewhere in 0.97-1.03 (drawn per match, not told; read it off your own throws). A rotating stone curls: the direction of its velocity turns at 0.00820 x v^-0.8 rad/s, towards -x for ccw and +x for cw; every stone is released with |omega| = pi/2 rad/s, the spin decays at 0.025 / v rad/s^2 and this never reverses the curl. The curl is strongest when the stone is slow: a draw curls much more than a takeout. The simulation steps these laws every 1 ms
- `collisions`: elastic (restitution 1, equal masses) with friction 0.2 at the contact; a full hit on a stationary stone roughly stops the thrower and sends the struck stone on at the thrower's speed; glancing hits split the motion
- `in_play`: a delivered stone that does not come to rest completely beyond the far hog line (stone centre y < 32.149) is removed from play unless it struck another stone; a stone that touches the side line (|x| + 0.145 >= 2.375) or completely crosses the back line (y - 0.145 > 40.234) is removed
- `free_guard_zone`: the area between the far hog line and the tee line, excluding the house; before the 6th stone of an end, if a delivered stone moves an opposition stone from the zone out of play (directly or indirectly), the delivered stone is removed and every moved stone is put back
- `scoring`: after all 10 stones of an end, the team with the stone closest to the tee (among stones in the house: centre distance < 1.829 + 0.145) scores one point for each of its stones in the house closer than the other team's closest stone; no stone in the house: a blank end
- `hammer`: the team without the hammer (the last stone of the end) throws first and the teams alternate; after an end the team that scored throws first in the next end; a blank end keeps the hammer
- `match_format`: one player (seat A, yellow) against a scripted computer team (red) of level RCB_LEVEL 1-3 (level 1 is a warm-up level; levels 2 and 3 are the official ones): level 1 draws to the button and takes out your stones, choosing the shot that would score best if the end ended now; levels 2 and 3 choose among draws, takeouts (also off-centre and firm), centre and corner guards, peels of your guards once the free guard zone allows and, with the last stone, throw-aways, by a positional value (the score if the end ended now, discounted early in the end; its centre guards when it lacks the hammer; your guards and stones in the house when it has it; a finished end by its chance to win the match) and look one reply of yours ahead; level 3 throws more precisely than level 2; it plays on the true ice (deviation D8); its execution error is its own size; a coin toss drawn from the seed decides who has the hammer in end 1 (`game spec` match.hammer_end_1 says who); its chess clock never runs. Success = winning the match
- `duel_format`: seat A (yellow) against seat B (red); a coin toss drawn from the seed decides who throws the first stone of end 1 (FIRST_PLAYER when it falls 0, else the other player; `game spec` match.throws_first_in_end_1 says who), and the other player has the hammer in end 1
- `observation`: the score, the end, the throw in the end, the hammer, the stones left to throw and in play, the ends so far and the throws since your last one (what was heard: collisions, stones removed and why; no stone coordinates), and one PNG of two camera tiles: house (straight above the far house, image up = +y, image right = +x) and hack (behind the hack looking down the sheet). Stones are grey granite with a coloured top and handle
- Winner: the higher total after 4 ends wins; if level, extra ends are played until a team scores, at most 3; if still level, the player with more chess-clock time left wins (match format: the scripted team's clock never runs, so a tie goes to it); if the clocks are equal too, (last resort, not from the rulebook) the player who had the hammer in end 1. There are no draws.
- Deviation D1 (rulebook C5, R2(b)): 4 ends of 5 stones per team (official: 8 or 10 ends of 8 stones)
- Deviation D2 (rulebook R12(a)): at most 3 extra ends while tied; then the player with more chess-clock time left wins (official: extra ends until a team scores)
- Deviation D3 (rulebook R8): no sweeping
- Deviation D5 (rulebook R7): no no-tick rule
- Deviation D6 (rulebook R5(a)): the team with the hammer in end 1 is decided by a coin toss drawn from the seed (official: a coin toss or a last stone draw). Match format: the toss gives the hammer to you or to the scripted team, and the official seeds are balanced (per level, half of them give you the hammer); duel: FIRST_PLAYER throws the first stone of end 1 if the toss falls 0, else the other player (it falls 0 for the official seeds 1-3), and the other player has the hammer
- Deviation D8 (rulebook - (the ice and pre-game practice, not from the rulebook)): the ice's deceleration scale kd (hidden, drawn per match from 0.97-1.03, the same for both teams) is learnt during the match: there is no pre-game practice on the sheet. Match format: the scripted computer team plays on the true ice (it knows kd, like a home team on its own ice); you learn it from your throws

## Geometry and physics
Everything you need is in `game spec`: the world frame, the release point, the cameras (pose, field of view, size,
`focal_px`, `principal_point_px`; pinhole: u = cx + f * x_right / depth, v = cy - f * y_up / depth) and the
execution scatter. The physics engine is curling ice model (DigitalCurling FCV1, pure Python, 1 ms steps) with impulse collisions; MuJoCo renders the cameras.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and graded on what stands at that moment, as the sections above say. The service does not count this limit for you: the clocks it reports are the game's own. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
