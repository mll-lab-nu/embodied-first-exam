# Table tennis: a match against a scripted opponent, in real time

You play robot table tennis (ITTF rules with the deviations below) against a scripted opponent: a MuJoCo Franka Panda holding a paddle, at your end of a real-size table, seen only through two cameras. The opponent serves every point (recorded real serves) and returns every ball it can reach; you always receive. One game to 5 points.

**Your goal: win the match.** The task succeeds if the match finishes and you won it. Keep your scripts, logs and notes
in `/app/output/`; there is nothing else to hand in: the simulator records the match.

## Time does not stop
- The world runs at 1/10 of real speed (`spec()["timing"]["slowdown"]` = 10): one 10 ms control
  step of game time every 0.1 s of wall time. It never waits for you: while you think, the opponent
  plays on and your robot keeps executing its last command.
- The match starts paused. Its clock starts at your first `submit` or `get_obs(seconds > 0)`, and from then on it runs
  until the match is over. Look at the cameras and read `spec()` first (`get_obs(seconds=0)` does not start the clock).
- **Breaks.** After every point the match stands still for 12 s of game time (120 s of wall time):
  the clock keeps running, nothing moves and nothing scores, and play resumes by itself at the end of the break. Use it
  to look at what happened and fix your program. Send a `ready` row to resume earlier (put your review, why you won or
  lost the point and what you change, in `submit`'s `note`). Commands planned for steps inside a break are dropped.
- **If your session ends before the match is over, you lose** (success 0), and the time limit (`## Time limit`) ends it; so
  start the match well before your time runs out and stay until it is over (`meta["done"]`).
- No reset: one match is the whole episode.

## Write a program
A model response takes seconds, a point only a few seconds of game time, so play with a program of your own: it
observes, measures in the images, computes its next command and submits it, in a loop, without a new model response
for each action. Run it in the background, watch its log, and stop, fix and restart it whenever needed (also during the
match). Use only the camera images, the service's replies and this document: no simulator internals or hidden state.

## Interface
The client is installed: `from rcb_client import Robot, EpisodeOver` (`/opt/tools/rcb_client.py`, on `PYTHONPATH`;
its docstring is the reference). Your container has Python 3.12 with numpy, SciPy, Pillow, requests and
opencv-python-headless; the network reaches only your model's API and the package registries (PyPI, Debian / Ubuntu archives).

```python
r = Robot()                                   # connects to the simulator, waits until it is ready
spec = r.spec()                               # the facts: action_types, cameras, proprio_layout, rules, break, timing
res = r.get_obs(seconds=0)                    # now, at once: res.last[cam] (H x W x 3 uint8), res.proprio (rows)
res = r.get_obs(seconds=0.12, video_fps=25, video="frames")   # watch 0.12 s of game time: res.frames[cam] (N x H x W x 3)
r.submit("stroke", [row])                   # a command: answers at once; it takes effect at the next control step
r.submit("ready", [[0]], note="WHY ... PLAN ...")       # during a break: resume now
```

- `get_obs(cameras=None, seconds=0, video_fps=10, video="frames")`: `seconds=0` returns the current images and one
  proprio row; `seconds > 0` (at most `spec()["max_watch_s"]`) waits while that much game time runs and returns the
  frames the cameras saw (one every 1/`video_fps` s) and one proprio row per frame. `cameras=[]`: proprio only.
- `submit(type, rows, at=None, note="")`: one command per row; the rows become the plan from control step `at` (the
  next step by default; `meta["control_steps"]` is the next step's number), replacing whatever was planned from there.
  A row takes effect at its step: the command is checked and planned there, from the state of that step. Rows for
  steps that are already gone when the request arrives are dropped (`meta["late_steps"]`); out-of-range values are
  clipped (`meta["clipped"]`); a command the rules refuse at its step (e.g. a stroke whose contact time has already passed) changes nothing and
  counts in the proprio column `commands_refused`.
- `res.meta`: `control_steps`, `sim_time_s`, `time_left_s`, `done`, `reason`, `running`, `lag_s`, and `proprio`
  (`layout`, `now`). `EpisodeOver` is raised once the match is over.

Your commands (`spec()["action_types"]`):

| type | row | what it does |
|---|---|---|
| `stroke` | `[t, x, y, z, nx, ny, nz, vx, vy, vz]` | the blade's state at contact, `t` seconds after the command takes effect: centre `x y z` (m), face normal `nx ny nz` (pointing where the ball should go), velocity `vx vy vz` (m/s). The service plans the swing (IK, joint speed limits, rehearsals on its own copy of the arm) from the arm's state at that step, then the arm returns to its ready pose. A new stroke replaces the one under way. Limits: 0 < t <= 2.5, \|x\| <= 1.2, -2.5 <= y <= -0.5, 0 <= z <= 1.2, speed <= 8 m/s (clipped, `meta["clipped"]`). The delivered state scatters by about 4 mm, 0.6 degrees and 2 % (from the task's frozen seed) |
| `rest` | `[0]` | cancel the stroke under way: the arm returns to its ready pose |
| `ready` | `[0]` | end the break now (see Time) |

Proprioception and the referee's information (`spec()["proprio_layout"]`, one float row per frame; NaN = not
applicable now; times in game seconds, positions in metres in your frame): `match_step`, `break`, `break_left_s`, `finished`; `score_you`, `score_opponent`, `point` (the point being played, from 1); the current ball: `ball_is_serve` (1: the opponent's serve, 0: its return), `t_since_played` (seconds since the opponent served or hit it; negative while a serve waits), `serve_in_s`, `ball_in_play`, `ball_coming` (coming to you), `ball_going` (going to the opponent); what you heard of the current ball, as the time on its clock (`t_since_played`) of the first event of each kind, NaN if not heard yet: `heard_opp_bounce_t` (a bounce on the opponent's half), `heard_own_bounce_t` (a bounce on your half), `heard_net_t`, `heard_paddle_t` (your paddle), `heard_robot_t` (your arm), `heard_floor_t`; your arm: `q1`..`q7` (joint angles, rad), `paddle_x/y/z` (blade centre), `paddle_nx/ny/nz` (face normal); the stroke under way: `stroke_active`, `stroke_contact_in_s`, and how well the planner can deliver it: `stroke_speed_scale` (> 1: the paddle speed was cut by the joint speed limits), `stroke_blade_error_m`, `stroke_normal_error_deg`, `stroke_ik_residual`; `last_point_won` (1 you, -1 the opponent, 0 a let); `commands_applied`, `commands_refused`, `last_refused_step`.

Cameras: two cameras, 480 x 360 RGB each: `behind` (behind and above your robot, looking down the table) and `side` (at the side of the table, looking along +x: your robot is on the right). Pose (`position`, `forward`, `up`), field of view (45 degrees vertical), `focal_px` (434.6) and `principal_point_px` in `spec()["cameras"]`; pinhole: u = cx + f x_right / depth, v = cy - f y_up / depth. The ball is orange, the opponent is the red paddle; yellow marks every 0.25 m along the table edges. Each image is stamped with the match step `k` and the current ball's clock `t`.

A ball takes about 0.6-0.9 s of game time from the opponent to you (6-9 s of wall time at S = 10). Three or more frames of the ball (`get_obs(seconds=0.12, video_fps=25, video="frames")` returns four, 40 ms apart, with one proprio row each) let you triangulate it with the two cameras and fit its flight.

## Rules
The rule texts come from RoboOlympics' `sport.toml`. Where they name RoboOlympics' own interface (`{'type': 'act', ...}`, `{'type': 'toss', ...}`, `{'type': 'none'}`, `{'type': 'target', ...}`, `state.*`, `game spec`, `/spec`), read: your `stroke`, `toss`, `rest`, `mallet` and `stop` rows, the proprio columns and `spec()`; where they say the world freezes for reviews, read: the break.

- `game_format`: first to 5 points; from 4:4 a lead of 2 is needed; at 6:6 the next point wins (7 at most)
- `rules`: after exactly one bounce on your half, hit the ball once so that it lands on your opponent's half, directly or after touching the net (the upper table edges count, the vertical sides do not); the same holds for your opponent's returns. You lose the point for a volley, a double hit, two bounces, a miss, a ball that lands on your own half or out, the ball touching your arm or handle while it is over or travelling towards your half, or your arm or paddle touching the table, net or floor. A shot that passes a player's half without touching it is out, even if it then hits that player's robot. A serve that touches the net or is irregular is a let. The receiver's 13th good return in a rally wins it the point (expedite rule). At 40 points played (lets included) the player ahead wins, at a level score the player who won the last point
- `opponent`: format match: the opponent serves every point (you always receive) and returns every ball it can reach; higher levels react faster, reach further and play faster, wider balls with more spin (`match.opponent_level` in game spec)
- `world`: metres; your frame: x to your right, y towards the opponent, z up; table top z = 0, |x| <= 0.7625, |y| <= 1.37; net at y = 0, top z = 0.1525; your half y < 0; your robot's base at (0, -1.75, 0) facing +y
- `ball`: radius 0.02 m, orange; gravity 9.81 m/s^2; air drag about 0.13 |v| v; spin bends the flight by a few cm; a bounce keeps about 96 % of the vertical and 87 % of the horizontal speed; a ball takes about 0.6-0.9 s from the opponent to you
- `reach`: the blade can meet a ball whose centre is within about 0.85 m of the shoulder (0, -1.75, 0.33) and above z = 0.12
- `blade`: 15 x 15 cm; at contact its centre is 2.75 cm from the ball's centre along the face normal; with n the unit face normal the ball leaves with about v_out = v_paddle - 0.96((v_in - v_paddle).n)n + (v_in - v_paddle) - ((v_in - v_paddle).n)n
- `scatter`: the serves, the opponent's returns and your strokes' execution scatter are drawn from the task's frozen seed (never shown)
- Winner: the first player to 5 points with a lead of 2, or the first to 7, wins the game (the match); a let scores no point; if 40 points (lets included) are played, the player ahead wins and at a level score the player who won the last point (last resort, not from the rulebook)
- Rulebook: ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2), 2025 (effective 1 January 2025)
- Deviation D1 (ITTF 2.11, 2.12): one game to 5 points (from 4:4 a lead of 2 is needed, at 6:6 the next point wins: 7 points at most) instead of a best-of-games match with games to 11
- Deviation D2 (ITTF 2.6, 2.13): the robots cannot toss the ball: format match - the opponent serves every point with recorded real serves and you always receive; format duel - a neutral machine serves recorded real serves and the receiver changes every point (as under the expedite system, 2.13.3, 2.15.3)
- Deviation D3 (ITTF 2.5.7): only the blade can strike the ball: the ball touching the handle or arm loses the point
- Deviation D4 (ITTF 2.10.1.9-2.10.1.11): a robot has no free hand: any contact of the arm or paddle with the table, net or floor loses the point
- Deviation D5 (ITTF 2.10.1.7): any double hit loses the point, deliberate or not
- Deviation D6 (ITTF 2.15.4): the expedite rule applies from the first point: the receiver's 13th good return in a rally wins it the point (this bounds every rally)
- Deviation D7 (ITTF 2.9.1.1 (let)): a serve that touches the net or is irregular is a let; duel: faults by both players at the same instant are a let; the robot that is not receiving is transparent to the serve until it bounces on the receiver's half (the recorded serves were made for an empty serving end)
- Deviation D8 (- (cost limit, not from the rulebook)): if 40 points (lets included) are played the game ends: the player ahead wins; at a level score the player who won the last point (never reached in practice)

Your robot: Franka Panda (MuJoCo Menagerie panda_nohand) holding a 15 x 15 cm paddle; its base at (0, -1.75, 0) facing +y. Everything else you need (the frame, the geometry and the rule constants) is in
`spec()["rules"]`; the physics engine is MuJoCo.

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` is its own count of this limit, from the service's start or from your first request, so it can differ from the time you really have left. Installing packages is not cheating (`## External material` above).
