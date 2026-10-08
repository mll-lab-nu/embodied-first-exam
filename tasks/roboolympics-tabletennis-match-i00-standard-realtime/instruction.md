# Table tennis: program play (match)

You play table tennis against a scripted opponent (you are seat `A`). Robot table tennis in a continuous world slowed by a factor S (MuJoCo Franka Panda + paddle, DeepMind ball and table model, recorded real serves), seen only through two cameras of four frames each; one game to 5 points (lead by 2 from 4:4, at 6:6 the next point wins); format match: you against a scripted opponent (level 1-4) that serves every point, format duel: two players and a neutral serve machine, the receiver changing every point.
This task is generated from `sports/tabletennis/sport.toml` (task `tabletennis-match-wallclock-program-standard`, RoboOlympics).

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
- Your container: Python 3.12 with numpy, SciPy and Pillow; also opencv-python-headless==5.0.0.93; no internet except your model's API. Keep your scripts, logs
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
| `game none ` | `POST /act {"type":"none", ...}` | one action (`game spec` lists the fields and ranges) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | your review after each of your actions |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one
action in flight.

## Rules
- robot table tennis in a continuous world slowed by a factor S (MuJoCo Franka Panda + paddle, DeepMind ball and table model, recorded real serves), seen only through two cameras of four frames each; one game to 5 points (lead by 2 from 4:4, at 6:6 the next point wins); format match: you against a scripted opponent (level 1-4) that serves every point, format duel: two players and a neutral serve machine, the receiver changing every point.
- `game_format`: first to 5 points; from 4:4 a lead of 2 is needed; at 6:6 the next point wins (7 at most)
- `rules`: after exactly one bounce on your half, hit the ball once so that it lands on your opponent's half, directly or after touching the net (the upper table edges count, the vertical sides do not); the same holds for your opponent's returns. You lose the point for a volley, a double hit, two bounces, a miss, a ball that lands on your own half or out, the ball touching your arm or handle while it is over or travelling towards your half, or your arm or paddle touching the table, net or floor. A shot that passes a player's half without touching it is out, even if it then hits that player's robot. A serve that touches the net or is irregular is a let. The receiver's 13th good return in a rally wins it the point (expedite rule). At 40 points played (lets included) the player ahead wins, at a level score the player who won the last point
- `opponent`: format match: the opponent serves every point (you always receive) and returns every ball it can reach; higher levels react faster, reach further and play faster, wider balls with more spin (`match.opponent_level` in game spec)
- `duel`: format duel: a neutral machine serves every point (first on the server's half, then on the receiver's); the receiver changes every point, `match.first_receiver` receives the first; both players get this document and see the game in their own frame
- `world`: metres; your frame: x to your right, y towards the opponent, z up; table top z = 0, |x| <= 0.7625, |y| <= 1.37; net at y = 0, top z = 0.1525; your half y < 0; your robot's base at (0, -1.75, 0) facing +y
- `ball`: radius 0.02 m, orange; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm; a bounce keeps about 96 % of the vertical and 87 % of the horizontal speed; a ball takes about 0.6-0.9 s from the opponent to you
- `reach`: the blade can meet a ball whose centre is within about 0.85 m of the shoulder (0, -1.75, 0.33) and above z = 0.12
- `blade`: 15 x 15 cm; at contact its centre is 2.75 cm from the ball's centre along the face normal; with n the unit face normal the ball leaves with about v_out = v_paddle - 0.96((v_in - v_paddle).n)n + (v_in - v_paddle) - ((v_in - v_paddle).n)n
- `observation`: observe: one PNG of 2 rows (camera behind your robot, camera at the side) x 4 columns (frames 40 ms apart, newest right) of 480 x 360 tiles, with each frame's control step (observation.view_steps); no ball coordinates; yellow marks every 0.25 m along the table edges; cameras' poses and intrinsics in game spec (pinhole, 45 degree vertical field of view, focal length 434.6 px, principal point at the tile centre)
- `action_high`: high action level: act {type: act, t, pos, normal, vel} = the blade's state at contact t seconds after the command takes effect (centre pos, face normal pointing at the opponent, velocity m/s); limits 0 < t <= 2.5, |x| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2, speed <= 8 m/s; it replaces the stroke under way; the service plans the swing (IK, joint speed limits) and the reply predicts how close the arm gets; the delivered state scatters by about 4 mm, 0.6 degrees and 2 %; {type: none} returns the arm to its ready pose
- `action_low`: low action level: joint position targets at 100 Hz, no IK or stroke planner: traj {k0, q: rows of 7 targets} (row i = control step k0 + i, <= 300 rows, consecutive rows within the per-step speed limit, the first row used within that limit of the target in force), slew {q, speed} (every joint towards q at speed x its limit), hold; game spec gives the kinematic chain, limits, the joint controller and the robot's own model (robot_model.robot_only_xml)
- `real_time`: the world runs on its own clock at 1/S of real speed (S = timing.slowdown in game spec); it never waits for you; an act takes effect at the next 10 ms control step after it arrives (the reply's took_effect); one act and one observation per seat in flight; after each point the world freezes until every player has sent game ready WHY PLAN
- `scatter_and_seed`: the serves, the opponent's returns and the execution scatter are drawn from the seed (RCB_SEED / DUEL_SEED)
- Winner: the first player to 5 points with a lead of 2, or the first to 7, wins the game (the match); a let scores no point; if 40 points (lets included) are played, the player ahead wins and at a level score the player who won the last point (last resort, not from the rulebook). There are no draws.
- Deviation D1 (rulebook ITTF 2.11, 2.12): one game to 5 points (from 4:4 a lead of 2 is needed, at 6:6 the next point wins: 7 points at most) instead of a best-of-games match with games to 11
- Deviation D2 (rulebook ITTF 2.6, 2.13): the robots cannot toss the ball: format match - the opponent serves every point with recorded real serves and you always receive; format duel - a neutral machine serves recorded real serves and the receiver changes every point (as under the expedite system, 2.13.3, 2.15.3)
- Deviation D3 (rulebook ITTF 2.5.7): only the blade can strike the ball: the ball touching the handle or arm loses the point
- Deviation D4 (rulebook ITTF 2.10.1.9-2.10.1.11): a robot has no free hand: any contact of the arm or paddle with the table, net or floor loses the point
- Deviation D5 (rulebook ITTF 2.10.1.7): any double hit loses the point, deliberate or not
- Deviation D6 (rulebook ITTF 2.15.4): the expedite rule applies from the first point: the receiver's 13th good return in a rally wins it the point (this bounds every rally)
- Deviation D7 (rulebook ITTF 2.9.1.1 (let)): a serve that touches the net or is irregular is a let; duel: faults by both players at the same instant are a let; the robot that is not receiving is transparent to the serve until it bounces on the receiver's half (the recorded serves were made for an empty serving end)
- Deviation D8 (rulebook - (cost limit, not from the rulebook)): if 40 points (lets included) are played the game ends: the player ahead wins; at a level score the player who won the last point (never reached in practice)

## Geometry and physics
Everything you need is in `game spec`: the world frame, the release point, the cameras (pose, field of view, size,
`focal_px`, `principal_point_px`; pinhole: u = cx + f * x_right / depth, v = cy - f * y_up / depth) and the
execution scatter. The physics engine is mujoco.
