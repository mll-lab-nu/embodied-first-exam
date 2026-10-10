# Air hockey: a match against a scripted opponent, in real time

You play robot air hockey (USAA rules with the deviations below) against a scripted opponent: a MuJoCo KUKA iiwa 14 arm holding a mallet at your end of the table (x < 0), seen only through one fixed camera. A rally starts with the puck at rest in one player's half; a goal, a seven-second foul or a dead puck ends it. The first to 7 goals wins.

**Your goal: win the match.** The task succeeds if the match finishes and you won it. Keep your scripts, logs and notes
in `/app/output/`; there is nothing else to hand in: the simulator records the match.

## Time does not stop
- The world runs at 1/10 of real speed (`spec()["timing"]["slowdown"]` = 10): one 10 ms control
  step of game time every 0.1 s of wall time. It never waits for you: while you think, the opponent
  plays on and your robot keeps executing its last command.
- The match starts paused. Its clock starts at your first `submit` or `get_obs(seconds > 0)`, and from then on it runs
  until the match is over. Look at the cameras and read `spec()` first (`get_obs(seconds=0)` does not start the clock).
- **Breaks.** After every rally the match stands still for 12 s of game time (120 s of wall time):
  the clock keeps running, nothing moves and nothing scores, and play resumes by itself at the end of the break. Use it
  to look at what happened and fix your program. Send a `ready` row to resume earlier (put your review, why you won or
  lost the rally and what you change, in `submit`'s `note`). Commands planned for steps inside a break are dropped.
- You have 7200 s in all. **If your session ends before the match is over, you lose** (success 0); so
  start the match well before your time runs out and stay until it is over (`meta["done"]`).
- No reset: one match is the whole episode.

## Write a program
A model response takes seconds, a rally only a few seconds of game time, so play with a program of your own: it
observes, measures in the images, computes its next command and submits it, in a loop, without a new model response
for each action. Run it in the background, watch its log, and stop, fix and restart it whenever needed (also during the
match). Use only the camera images, the service's replies and this document: no simulator internals or hidden state.

## Interface
The client is installed: `from rcb_client import Robot, EpisodeOver` (`/opt/tools/rcb_client.py`, on `PYTHONPATH`;
its docstring is the reference). Your container has Python 3.12 with numpy, SciPy, Pillow, requests and
opencv-python-headless; no internet except your model's API.

```python
r = Robot()                                   # connects to the simulator, waits until it is ready
spec = r.spec()                               # the facts: action_types, cameras, proprio_layout, rules, break, timing
res = r.get_obs(seconds=0)                    # now, at once: res.last[cam] (H x W x 3 uint8), res.proprio (rows)
res = r.get_obs(seconds=0.12, video_fps=25, video="frames")   # watch 0.12 s of game time: res.frames[cam] (N x H x W x 3)
r.submit("mallet", [row])                   # a command: answers at once; it takes effect at the next control step
r.submit("ready", [[0]], note="WHY ... PLAN ...")       # during a break: resume now
```

- `get_obs(cameras=None, seconds=0, video_fps=10, video="frames")`: `seconds=0` returns the current images and one
  proprio row; `seconds > 0` (at most `spec()["max_watch_s"]`) waits while that much game time runs and returns the
  frames the cameras saw (one every 1/`video_fps` s) and one proprio row per frame. `cameras=[]`: proprio only.
- `submit(type, rows, at=None, note="")`: one command per row; the rows become the plan from control step `at` (the
  next step by default; `meta["control_steps"]` is the next step's number), replacing whatever was planned from there.
  A row takes effect at its step: the command is checked and planned there, from the state of that step. Rows for
  steps that are already gone when the request arrives are dropped (`meta["late_steps"]`); out-of-range values are
  clipped (`meta["clipped"]`); a command the rules refuse at its step (e.g. a mallet target at a step where the rally is already over; a row planned for a step inside a break is dropped and does not count) changes nothing and
  counts in the proprio column `commands_refused`.
- `res.meta`: `control_steps`, `sim_time_s`, `time_left_s`, `done`, `reason`, `running`, `lag_s`, and `proprio`
  (`layout`, `now`). `EpisodeOver` is raised once the match is over.

Your commands (`spec()["action_types"]`):

| type | row | what it does |
|---|---|---|
| `mallet` | `[x, y]` | the mallet centre's target (m, table frame): the robot drives the mallet there along a speed- and acceleration-limited path (`spec()["rules"]["mallet_path"]`) and holds it until replaced. Own half only: a target outside the workspace (`spec()["rules"]["workspace"]`: 0.05 <= -x <= 0.92, \|y\| <= 0.47, at most 1.45 m from your base) is moved to its nearest point (`meta["clipped"]`). Rows may be a chunk `dt` apart with `interpolate="linear"`; a row equal to the target in force changes nothing |
| `stop` | `[0]` | the mallet stops where it is (its target becomes its position) |
| `ready` | `[0]` | end the break now (see Time) |

Proprioception and the referee's information (`spec()["proprio_layout"]`, one float row per frame; NaN = not
applicable now; times in game seconds, positions in metres in your frame): `match_step`, `break`, `break_left_s`, `finished`; `score_you`, `score_opponent`, `rally` (the rally being played, from 1), `t_play` (seconds of play; breaks do not count), `play_time_left_s` (to the 120 s cap); your mallet: `mallet_x/y/z` (its centre), `target_x/y` (the target in force); your arm: `q1`..`q7`, `q_striker1/2` and their velocities `qd1`..`qd7`, `qd_striker1/2`; the last rally: `last_rally_how` (1 goal, 2 seven-second foul, 3 dead puck, 4 time cap), `last_rally_scored` (1 you, -1 the opponent, 0 nobody), `last_rally_fouled` (who committed a foul), `last_rally_next_puck` (who gets the puck next, 0 a face-off); `commands_applied`, `commands_refused`, `last_refused_step`.

Cameras: one camera, `front`, 320 x 240 RGB, fixed above and behind your end of the table (pose, field of view 48 degrees, `focal_px`, `principal_point_px` in `spec()["cameras"]`). The puck is red; the opponent's mallet is at the far end.

The puck moves fast: track it over several consecutive images (`get_obs(seconds=0)` in a loop, each with its `t_play`) and move the mallet with a program that runs in the background.

## Rules
The rule texts come from RoboOlympics' `sport.toml`. Where they name RoboOlympics' own interface (`{'type': 'act', ...}`, `{'type': 'toss', ...}`, `{'type': 'none'}`, `{'type': 'target', ...}`, `state.*`, `game spec`, `/spec`), read: your `stroke`, `toss`, `rest`, `mallet` and `stop` rows, the proprio columns and `spec()`; where they say the world freezes for reviews, read: the break.

- `robot`: a seven-axis KUKA iiwa arm whose end holds a mallet; seat A plays from the end x < 0, seat B from the end x > 0 (format match: you are A, the scripted opponent is B; `match.opponent_level` in /spec)
- `rally`: a rally starts with the puck at rest in one player's half on a spot at |x| = 0.58 (y varies between -0.18 and 0.18, from the seed), both mallets at home (|x| = 0.82, y = 0); the first rally starts with the puck in the half of `match.first_player`
- `goal`: the puck wholly inside a goal scores 1 point for the other player, whoever touched it last; the player scored upon gets the puck for the next rally
- `seven_second_rule`: if the puck stays wholly in one player's half for 7 s, that player commits a foul: the next rally starts with the puck in the opponent's half; a foul gives no point; the 7 s start again when the puck has wholly entered the other half; while it touches the centre line it is in nobody's half (either player may hit it)
- `dead_puck`: if for 2 s neither mallet can reach the puck (near the centre line at the sides, beyond both workspaces), or the puck touches the centre line for 7 s, the next rally starts with a face-off: the puck at rest at the table centre
- `review`: every goal, foul or dead puck ends the rally: both mallets return home, the break follows (spec.break), then the next rally starts
- `game`: the first player to score 7 goals wins; the game also ends after 120 s of play (frozen time does not count) or 40 rallies, then the tiebreaks below decide
- `opponent`: format match: the scripted opponent (seat B, in the trusted simulator) guards its goal and strikes the puck at yours from the true puck position a reaction delay ago; levels 1-4 differ in its mallet speed (0.4 / 0.6 / 1 / 2 m/s), reaction delay and defence (level 1 does not guard its goal; level 4 guards the puck's predicted crossing point); it never reads your commands
- `table`: metres, seconds; the table frame: x along the table (seat A's end at x < 0, seat B's at x > 0), y across, z up. Playing surface 1.948 x 1.038 m (|x| <= 0.974, |y| <= 0.519), surrounded by rails; a goal mouth 0.35 m wide (|y| <= 0.175) in the middle of each end rail; the centre line is x = 0
- `puck`: radius 0.03165 m, mass 10 g; it slides flat on the air cushion and slows by about 10 % per second; rails return about 80 % of the puck's speed across them; mallets push it physically (a hit gives the puck up to about 1.3 times the mallet's speed); the puck's top face is at z = 0.022, its centre plane z = 0.012
- `mallet`: radius 0.04815 m, its centre 0.0645 m above the surface; home (-0.82, 0) for A, (0.82, 0) for B; the arm links have no collision geometry
- `cameras_pose`: the camera of seat A at (0, -1.3, 2.2), image right (1, 0, 0), image up (0, 0.861, 0.509), 48 degree vertical field of view; seat B's is the same turned half a turn about the table centre
- `rates`: physics 1000 Hz, control 100 Hz (10 ms steps)
- Winner: the first player to score 7 goals wins; at the safety cap (120 s of play or 40 rallies) the player with more goals wins; at equal goals the player who scored the last goal; if nobody has scored, the player in whose half the puck spent less time; last resort (not from the rulebook): the player who did not have the puck first
- Rulebook: USAA (United States Air Hockey Association) Official Rules of Air Hockey, as published by Gold Standard Air Hockey, retrieved 2026-10-05
- Deviation D1 (I.1, III.1): one game to 7 points instead of a match of several games
- Deviation D2 (- (the rules have no time limit)): a safety cap of 120 s of play (frozen time does not count) or 40 rallies; then the player with more goals wins, at equal goals the scorer of the last goal, at 0:0 the player in whose half the puck spent less time, and if that is equal the player who did not have the first possession (the stated last resort: no draws)
- Deviation D3 (III.1-2): the game starts with the puck at rest in the half of the first player (FIRST_PLAYER, the coin toss) instead of a face-off; a face-off places the puck at rest at the table centre with both mallets at home instead of a referee's release
- Deviation D4 (I.10, VI.1): the seven-second rule is a foul with the rulebook's penalty, forfeiture of the puck: the opponent gets it at rest on its spot; a foul gives no point
- Deviation D5 (IV.6, I.11): a dead puck (play suspended) is added for a puck that no mallet can reach for 2 s (the robots' reach) or that touches the centre line for 7 s (I.11 has no limit); it is followed by a face-off
- Deviation D6 (I.4, I.14-15): after every goal (I.4: the player scored upon gets the puck), foul or dead puck both mallets return home and the world freezes for the reviews; the time-outs are not used
- Deviation D7 (I.8, I.13, VI.6): palming, goal-tending and topping cannot occur: only the mallets touch the puck and it stays flat on the table
- Deviation D8 (I.12, VI.9): the mallets cannot cross the centre line: the mallet workspace ends 0.05 m before it (and at 1.45 m from the robot's base), so the players cannot touch each other
- Deviation D9 (-): the players are seven-axis KUKA iiwa arms holding a mallet, commanded by a Cartesian target for the mallet (a smooth path of at most 2 m/s and 10 m/s^2, inverse kinematics and torque-limited motors), not human hands
- Deviation D10 (II.A.1 (the rules name the sanctioned tables, not their dimensions)): the goal mouth is 0.35 m wide (|y| <= 0.175) instead of the 0.25 m of the table model (AirHockeyChallenge, 1.948 x 1.038 m): the arms move the mallet at about 2 m/s, so a shot takes 0.5-1 s to arrive and a defender that follows the puck would cover a 0.25 m mouth almost completely

Your robot: KUKA LBR iiwa 14 holding a mallet (the striker on two passive joints), its base at (-1.51, 0) beside your end. Everything else you need (the frame, the geometry and the rule constants) is in
`spec()["rules"]`; the physics engine is MuJoCo.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.
