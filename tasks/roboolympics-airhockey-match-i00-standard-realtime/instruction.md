# Air hockey: program play (match)

You play air hockey against a scripted opponent (you are seat `A`). Robot air hockey on a physical MuJoCo table: a seven-axis KUKA iiwa arm holding a mallet at each end, the puck sliding on the air cushion, in a continuous world slowed by a factor S; you command your mallet's target in your own half and see the table only through your fixed camera; one game to 7 goals under the USAA rules (seven-second rule, dead-puck face-offs, a safety cap with a stated last resort, a 0.35 m goal mouth); format match: you against a scripted opponent (level 1-4), format duel: two players.
This task is generated from `sports/airhockey/sport.toml` (task `airhockey-match-wallclock-program-standard`, RoboOlympics).

## Time
The world runs in real time at 1/S of real speed (S = `timing.slowdown` in `game spec`); your thinking costs game time. At the end of every unit the world freezes for the reviews.

Whenever the world freezes for a review (after every unit: a point, a shot, a heat; see `game spec`), send `game ready "WHY" "PLAN"` (a short review) before the next unit starts.
The match is graded when your session ends: stay until it is over. **If your session ends before the match is over, you lose the match** (a valid result, success 0), also if you never sent `game start`.

## Write a program
You may write a program that observes, measures in the images, computes your next action and sends it, without a
new model response for each action. You stay in the loop: watch its log, and stop, fix and restart it whenever
needed. Only you send `game start` and `game ready`.

- Use only the camera images, the service's replies and this document; no simulator internals or hidden state.
- One action at a time: an action sent before the previous one has returned is refused (HTTP 429).
- Your container: Python 3.12 with numpy, SciPy and Pillow; no internet except your model's API. Keep your scripts, logs
  and notes in `/app/output/`.

## Interface
Use the `game` command, or the same calls as HTTP with JSON at `$SIM_URL/<SEAT>/` (SIM_URL = http://localhost:8000, your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras with their intrinsics, the rule constants |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait` | `POST /wait {"timeout_s": 60}` | block until it is your turn (or the match is over) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | one action |
| `game target X Y` | `POST /act {"type":"target", ...}` | one action (`game spec` lists the fields and ranges) |
| `game none ` | `POST /act {"type":"none", ...}` | one action (`game spec` lists the fields and ranges) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | your review after each of your actions |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one
action in flight.

## Rules
- robot air hockey on a physical MuJoCo table: a seven-axis KUKA iiwa arm holding a mallet at each end, the puck sliding on the air cushion, in a continuous world slowed by a factor S; you command your mallet's target in your own half and see the table only through your fixed camera; one game to 7 goals under the USAA rules (seven-second rule, dead-puck face-offs, a safety cap with a stated last resort, a 0.35 m goal mouth); format match: you against a scripted opponent (level 1-4), format duel: two players.
- `real_time`: this sport is real time (where the generic text above says otherwise, this line holds): `game wait DT` (POST /wait {"dt": DT}, 0 < DT <= 1) lets the world run DT game seconds; `game ready "WHY" "PLAN"` is due only after each rally, not after each action; acts are never out of turn, one in flight at a time; there is no release point and no execution scatter: your target goes to the mallet's path, the arm's inverse kinematics and its motors
- `robot`: a seven-axis KUKA iiwa arm whose end holds a mallet; seat A plays from the end x < 0, seat B from the end x > 0 (format match: you are A, the scripted opponent is B; `match.opponent_level` in /spec)
- `action`: target: a target for your mallet's centre in table metres (world frame). It must lie in your mallet's workspace (`workspace` in /spec): in your own half, 0.05 <= |x| <= 0.92, |y| <= 0.47, and at most 1.45 m from your robot's base at (-1.51, 0) for seat A, (+1.51, 0) for seat B; a target outside it is refused (HTTP 400). The mallet moves towards the target along a smooth path of at most 2 m/s and 10 m/s^2, driven by the arm's inverse kinematics and torque-limited motors, so it arrives later than the command and may lag when the arm is loaded or hits the puck. A command takes effect at the next 10 ms control step and holds until replaced; none holds the mallet where it is. The service has no puck tracking: aiming, timing and defending are up to you
- `observation`: one 320 x 240 RGB image per observation from your fixed camera above and behind your end of the table (`cameras` in /spec: pose, field of view, focal length; pixel centres at (column + 0.5, row + 0.5)). The puck is red, the mallet of seat A blue, the mallet of seat B green, the arms orange; four yellow markers are at (+-0.9, +-0.46) on the table surface and the centre line is grey. The state gives the score (points and fouls per seat), the time of play, your own mallet position, its command and your arm's joint positions and velocities (`own`), and the rallies that ended (`rallies`, the latest `last_rally`); no puck or opponent coordinates and no seed. Both seats see the game the same way: the two cameras are images of each other turned half a turn about the table centre
- `rally`: a rally starts with the puck at rest in one player's half on a spot at |x| = 0.58 (y varies between -0.18 and 0.18, from the seed), both mallets at home (|x| = 0.82, y = 0); the first rally starts with the puck in the half of `match.first_player`
- `goal`: the puck wholly inside a goal scores 1 point for the other player, whoever touched it last; the player scored upon gets the puck for the next rally
- `seven_second_rule`: if the puck stays wholly in one player's half for 7 s, that player commits a foul: the next rally starts with the puck in the opponent's half; a foul gives no point; the 7 s start again when the puck has wholly entered the other half; while it touches the centre line it is in nobody's half (either player may hit it)
- `dead_puck`: if for 2 s neither mallet can reach the puck (near the centre line at the sides, beyond both workspaces), or the puck touches the centre line for 7 s, the next rally starts with a face-off: the puck at rest at the table centre
- `review`: every goal, foul or dead puck ends the rally: both mallets return home, the world freezes for the reviews, then the next rally starts
- `game`: the first player to score 7 goals wins; the game also ends after 120 s of play (frozen time does not count) or 40 rallies, then the tiebreaks below decide
- `opponent`: format match: the scripted opponent (seat B, in the trusted simulator) guards its goal and strikes the puck at yours from the true puck position a reaction delay ago; levels 1-4 differ in its mallet speed (0.4 / 0.6 / 1 / 2 m/s), reaction delay and defence (level 1 does not guard its goal; level 4 guards the puck's predicted crossing point); it never reads your commands
- `table`: metres, seconds; the table frame: x along the table (seat A's end at x < 0, seat B's at x > 0), y across, z up. Playing surface 1.948 x 1.038 m (|x| <= 0.974, |y| <= 0.519), surrounded by rails; a goal mouth 0.35 m wide (|y| <= 0.175) in the middle of each end rail; the centre line is x = 0
- `puck`: radius 0.03165 m, mass 10 g; it slides flat on the air cushion and slows by about 10 % per second; rails return about 80 % of the puck's speed across them; mallets push it physically (a hit gives the puck up to about 1.3 times the mallet's speed); the puck's top face is at z = 0.022, its centre plane z = 0.012
- `mallet`: radius 0.04815 m, its centre 0.0645 m above the surface; home (-0.82, 0) for A, (0.82, 0) for B; the arm links have no collision geometry
- `cameras_pose`: the camera of seat A at (0, -1.3, 2.2), image right (1, 0, 0), image up (0, 0.861, 0.509), 48 degree vertical field of view; seat B's is the same turned half a turn about the table centre
- `rates`: physics 1000 Hz, control 100 Hz (10 ms steps)
- Winner: the first player to score 7 goals wins; at the safety cap (120 s of play or 40 rallies) the player with more goals wins; at equal goals the player who scored the last goal; if nobody has scored, the player in whose half the puck spent less time; last resort (not from the rulebook): the player who did not have the puck first. There are no draws.
- Deviation D1 (rulebook I.1, III.1): one game to 7 points instead of a match of several games
- Deviation D2 (rulebook - (the rules have no time limit)): a safety cap of 120 s of play (frozen time does not count) or 40 rallies; then the player with more goals wins, at equal goals the scorer of the last goal, at 0:0 the player in whose half the puck spent less time, and if that is equal the player who did not have the first possession (the stated last resort: no draws)
- Deviation D3 (rulebook III.1-2): the game starts with the puck at rest in the half of the first player (FIRST_PLAYER, the coin toss) instead of a face-off; a face-off places the puck at rest at the table centre with both mallets at home instead of a referee's release
- Deviation D4 (rulebook I.10, VI.1): the seven-second rule is a foul with the rulebook's penalty, forfeiture of the puck: the opponent gets it at rest on its spot; a foul gives no point
- Deviation D5 (rulebook IV.6, I.11): a dead puck (play suspended) is added for a puck that no mallet can reach for 2 s (the robots' reach) or that touches the centre line for 7 s (I.11 has no limit); it is followed by a face-off
- Deviation D8 (rulebook I.12, VI.9): the mallets cannot cross the centre line: the mallet workspace ends 0.05 m before it (and at 1.45 m from the robot's base), so the players cannot touch each other
- Deviation D10 (rulebook II.A.1 (the rules name the sanctioned tables, not their dimensions)): the goal mouth is 0.35 m wide (|y| <= 0.175) instead of the 0.25 m of the table model (AirHockeyChallenge, 1.948 x 1.038 m): the arms move the mallet at about 2 m/s, so a shot takes 0.5-1 s to arrive and a defender that follows the puck would cover a 0.25 m mouth almost completely

## Geometry and physics
Everything you need is in `game spec`: the world frame, the release point, the cameras (pose, field of view, size,
`focal_px`, `principal_point_px`; pinhole: u = cx + f * x_right / depth, v = cy - f * y_up / depth) and the
execution scatter. The physics engine is mujoco 3.3.7 (1 kHz physics, 10 ms control): two physically simulated KUKA iiwa arms with passive striker joints (AirHockeyChallenge robot model), a 10 g puck on an air-cushion plane, physical rails and mallets.
