# Badminton: a match against a scripted opponent, in real time

You play robot singles badminton (BWF rules with the deviations below) against a scripted opponent: a MuJoCo Franka Panda on a 1 m pedestal whose base slides on rails, holding a racket, seen only through two cameras. Rally scoring; you serve the first point, then the winner of each rally serves. One game to 5 points.

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
- You have 7200 s in all. **If your session ends before the match is over, you lose** (success 0); so
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
opencv-python-headless; no internet except your model's API.

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
  clipped (`meta["clipped"]`); a command the rules refuse at its step (e.g. a toss when it is not your serve) changes nothing and
  counts in the proprio column `commands_refused`.
- `res.meta`: `control_steps`, `sim_time_s`, `time_left_s`, `done`, `reason`, `running`, `lag_s`, and `proprio`
  (`layout`, `now`). `EpisodeOver` is raised once the match is over.

Your commands (`spec()["action_types"]`):

| type | row | what it does |
|---|---|---|
| `stroke` | `[t, x, y, z, nx, ny, nz, vx, vy, vz]` | the racket head's state at contact, `t` seconds after the command takes effect: head centre `x y z` (m), string-face normal `nx ny nz`, head velocity `vx vy vz` (m/s). It takes effect `spec()["rules"]["act"]["lead_steps"]` control steps after its row's step (4 at S = 10: the planning time; `stroke_pending_effect_step` shows it) and `t` counts from then; the service plans the swing and the base's move, then the robot returns to its ready pose and the base home. A stroke, toss or rest planned before the previous one took effect is refused. Limits: 0 < t <= 5, \|x\| <= 3.4, -7.5 <= y <= -0.3, 0.2 <= z <= 3.0, speed <= 8 m/s (clipped) |
| `toss` | `[x, y, z, height]` | your serve's toss: the shuttle appears at `x y z` (your half, y <= -0.5, 0.5-1.8 m high, within 1.0 m of your base horizontally) when the command takes effect (the same lead), from rest or rising `height` (0-0.5 m) straight up. Only the server, once per serve, once the receiver is ready (`serve_phase` 1, open). Then hit it with a stroke (it may be sent before the toss); the serve rules are in `spec()["rules"]["serve"]` |
| `rest` | `[0]` | cancel the stroke under way (the same lead) |
| `ready` | `[0]` | end the break now (see Time) |

Proprioception and the referee's information (`spec()["proprio_layout"]`, one float row per frame; NaN = not
applicable now; times in game seconds, positions in metres in your frame): `match_step`, `break`, `break_left_s`, `finished`; `score_you`, `score_opponent`, `point`; the serve: `you_serve`, `serve_court_right`, `serve_phase` (0 waiting: the receiver is getting ready, 1 open: toss now, 2 tossed, 3 done), `serve_opens_in_s`, `serve_deadline_in_s` (toss before it: an undue delay is a fault), `serve_tossed_at_step`; the shuttle: `ball_kind` (0 the opponent's serve, 1 your serve, 2 the opponent's return), `t_since_played` (seconds since it was played: served, tossed or hit; NaN before), `ball_in_play`, `ball_not_served`, `ball_tossed` (yours to hit), `ball_coming`, `ball_going`; your robot: `base_x`, `base_y`, `q1`..`q7`, `racket_x/y/z`, `racket_nx/ny/nz`; the stroke under way: `stroke_active`, `stroke_contact_in_s`, `stroke_traj_steps_left`, `stroke_pending_effect_step` (a stroke, toss or rest waiting for its effect step, NaN if none), `stroke_head_speed_limited`, `stroke_pose_not_delivered` (the planner's notes); `last_point_won`; `commands_applied`, `commands_refused`, `last_refused_step`.

Cameras: two cameras, 480 x 360 RGB each: `behind` (behind and above your base line, looking down the court) and `side` (at the side of the court, x < 0, looking along +x: your half is on the right). Pose, field of view (45 degrees), `focal_px` and `principal_point_px` in `spec()["cameras"]`. The shuttle is drawn enlarged: an orange cork (a 12 cm ball centred on its position) with a white skirt behind it; yellow marks every 1 m outside the singles side lines and behind the base lines. Each image is stamped with the match step `k` and the shuttle's clock `t`.

Four frames 60 ms apart (`get_obs(seconds=0.18, video_fps=17, video="frames")`) with the two cameras let you triangulate the shuttle and fit its flight (gravity and quadratic drag, `spec()["rules"]["shuttle"]`).

## Rules
The rule texts come from RoboOlympics' `sport.toml`. Where they name RoboOlympics' own interface (`{'type': 'act', ...}`, `{'type': 'toss', ...}`, `{'type': 'none'}`, `{'type': 'target', ...}`, `state.*`, `game spec`, `/spec`), read: your `stroke`, `toss`, `rest`, `mallet` and `stop` rows, the proprio columns and `spec()`; where they say the world freezes for reviews, read: the break.

- `match`: first to 5 points (rally scoring); from 4-4 a player must lead by 2, and at 6-6 the next point wins (at most 7); the match also ends after 300 hits (both sides) or 40 points played (replayed lets included): then the player with more points wins, at equal points the player who won the last point
- `play`: there is no bounce: hit the shuttle before it reaches the floor. Your shot is good if your racket meets the shuttle once, on your half, and the shuttle passes over the net and lands in your opponent's singles court (lines are in); after your hit your racket no longer touches it. You lose the point if your shot goes into the net (crosses the net plane below the top), comes down on your own side or lands out, or if a shuttle that is yours to hit lands in your court; an opponent's shot that would land out of your court wins you the point, so you may let it go. Serves (BWF Law 9): the winner of a rally serves the next point (after a let the same server; state.you_serve, state.serve). Before every serve both robots are put at rest in the ready pose at their spots: x = +0.3 in the right service court or -0.3 in the left one, y = -4.0 (your frame); both stand in their right courts when the server's score is even, else in their left ones (diagonally opposite); the spot is your base's home for the point. From 1 s after play resumes (the receiver is ready; state.serve.phase 'open') the server has 3 s to toss the shuttle with {'type':'toss','pos':[X,Y,Z],'height':H}: when the command takes effect (the same lead as an act) the shuttle appears at that point (0.5 <= Z <= 1.8, within 1.0 m horizontally of your base, Y <= -0.5) and is released from rest (H = 0 or omitted) or rises H straight up (0 <= H <= 0.5) before it falls (until then it is held beside the server). Then hit it with your racket (an act, which you may send before the toss): the serve is good if your racket meets the shuttle below 1.15 m, the shuttle leaves the racket upwards, passes over the net and lands in the receiver's diagonally opposite service court (between its short service line and its back line, lines in) or is returned. It is the server's fault (the receiver's point) if it does not toss the shuttle in time (undue delay; the third time disqualifies the player: it loses the match), misses the shuttle, hits it above 1.15 m or not upwards, or the serve hits the net or lands outside that court. Both bases must stay within 5 cm of their spots until the serve is hit (or faulted): a base moving earlier is that player's fault (both at once: a let, replayed)
- `opponent`: format match-wallclock: a scripted computer opponent. You serve the first point; the opponent serves when it won the last rally: from its service court at 1.05 m, upwards, high and deep or short into your diagonal service court, always within your reach (level 1: 70 % high serves, towards the middle of the court; level 2: 50 % high, wider and closer to the short service line); it stands still in its service court while you serve. It never makes an unforced error: it returns every shuttle it can reach, into your court and within your reach; shuttles far from it or fast beat it; level 2 reacts and moves faster and reaches further than level 1
- `world`: metres; your own frame: x to your right, y towards the opponent, z up. Floor z = 0; singles court |x| <= 2.59, |y| <= 6.70 (lines in); the net is the plane y = 0 with its top at z = 1.524 (posts at x = +-3.05); short service lines at |y| = 1.98; the centre line x = 0 divides each half into a right and a left service court. Your half is y < 0
- `robot`: a Franka Panda arm on a 1.0 m pedestal whose base slides on rails (|bx| <= 3.25, -7.5 <= by <= -0.5, up to 6 m/s and 20 m/s^2; home: the point's spot (+-0.3, -4.0), see play); the racket head centre is 0.56 m beyond the flange; the string face is a disc of radius 0.14 m. The racket meets shuttles 0.4-2.5 m above the floor; overhead contacts (1.8-2.5 m) allow the fastest, steepest shots
- `shuttle`: a point mass under gravity (9.81 m/s^2) and quadratic air drag, dv/dt = g - K |v| v with K = 0.212 per metre (terminal speed 6.8 m/s): hit at 40 m/s it slows to about 10 m/s within 0.3 s, and a high shuttle falls almost vertically at close to 6.8 m/s. No spin, no wind, no bounce
- `racket_contact`: the racket meets the shuttle when the shuttle's centre crosses the string plane within 0.14 m of the head centre; the shuttle leaves exactly along the face normal n (the side the head moves towards, relative to the shuttle) at the speed 20 max(0, v_head.n) (1 - 0.3 (r/0.14)^2) + 0.15 max(0, -v_in.n), where v_head is the head velocity, r the contact's distance from the head centre and v_in the shuttle's incoming velocity; the rest of the head and incoming velocity is lost. A head speed along the normal of 0.5 m/s gives about 10 m/s, 2 m/s about 40 m/s; the arm manages up to about 2.4 m/s
- Winner: a player disqualified for repeated undue delay (its third serve not tossed in time) loses; else first to 5 points (from 4-4 by 2, at most 7); at the match limit (300 hits or 40 points played) the player with more points; at equal points the player who won the last point that was not a let; then (last resort, not from the rulebook) the player who received first (format match-wallclock: the opponent)
- Rulebook: BWF Laws of Badminton (BWF Statutes, Section 4.1, version 5.0), 2025-04-26
- Deviation D1 (7): one short game: first to 5 points, from 4-4 a two-point lead is needed, at most 7 (6-6: the next point wins) instead of best of three games to 21 (cap 30); the match also ends after 300 hits (both sides) or 40 points played (lets included): the player ahead wins, at equal points the winner of the last point
- Deviation D2 (9.1.5-9.1.8): the robot has no free hand to hold and drop the shuttle: the server tosses it with the command toss {pos: [x, y, z], height: H} (the common racket-sport toss, docs/conventions/racket_serve_zh.md): when the command takes effect the shuttle appears at that point (0.5-1.8 m high, within 1.0 m horizontally of the server's base, on its half) and is released from rest (H = 0) or projected straight up to rise H (at most 0.5 m; the Laws do not forbid a small toss); until then it is held beside the server. The toss has no spin (a point mass has none, Law 9.1.5). Judged: the server's racket must hit it (a miss is a fault, Law 9.1.8), with the shuttle below 1.15 m at the hit (Law 9.1.6, judged at the shuttle's point: it has no size) and leaving the racket upwards (Law 9.1). Not judged: the racket hitting the base of the shuttle first and moving forwards throughout the service (Laws 9.1.5, 9.1.7)
- Deviation D3 (13.3-13.4): the shuttle is a point mass: a crossing of the net plane below the net top (between the posts) is a fault of the hitter; touching the net or reaching over it is not judged; a racket meets the shuttle only on its own half and only when it is that player's turn (no double hits)
- Deviation D4 (9.1.3-9.1.4): before every serve the referee puts both robots at rest in the ready pose at a fixed spot in their service courts (diagonally opposite: the right courts when the server's score is even, Law 10.1): x = +0.3 (right court) or -0.3 (left court), y = -4.0 in each robot's frame; the spot is the robot's home for the point (where its base returns between strokes). Standing still (Law 9.1.4) is judged on the base: a base more than 5 cm from its spot before the serve is delivered (hit, or faulted) is that player's fault; both at once: a let (Law 14.2.2). The base moves within |x| <= 3.25, -7.5 <= y <= -0.5 at up to 6 m/s and 20 m/s^2
- Deviation D5 (-): the last resort of the no-draw rule (equal points at the match limit and no point won) is not from the rulebook: the player who received first wins (format match-wallclock: the opponent)
- Deviation D6 (9.1.1, 16.6-16.7): undue delay has a fixed limit: the server must toss the shuttle within 3 s after the receiver is ready (1 s after play resumes, Law 9.4), else it is a service fault (the receiver's point); a player's third such fault disqualifies it (it loses the match) instead of the umpire's warning and the referee's discretion (Laws 16.7.1-16.7.2)
- Deviation D7 (6): no toss: format duel-wallclock: the runner plays both orders of the first server (match.first_server); format match-wallclock: you serve the first point

Your robot: Franka Panda on a 1.0 m pedestal whose base slides on x-y rails, holding a badminton racket. Everything else you need (the frame, the geometry and the rule constants) is in
`spec()["rules"]`; the physics engine is MuJoCo.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.
