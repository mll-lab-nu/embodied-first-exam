# Embodied Olympics · foosball, game against level 3 (standard)

## Task
Table football on a physical table: you drive the four motorised rods of one team (the goalkeeper rod with 3 figures,
the 2-rod with 2, the 5-rod with 5, the 3-rod with 3) by slide and angle targets that the motors follow along a speed-
and acceleration-limited path, and you see the table only through an overhead camera. You are seat `A` (blue) against a
scripted computer team (red) at level 3. The world waits for you: it advances only while you let it (Robot Interface,
`### Time`). The robot runs as a service you reach only through its client, as if it were real hardware: one live
episode.

## Goal
Success: you win the game.

The game is graded when your session ends: stay until it is over. If your session ends before the game is over, or you
never sent `game start`, you lose.

Nothing to hand in: the service records and grades the episode. Keep your scripts, logs and notes in `/app/output/`.

Real-robot rules:
- One game, no reset: a goal against you stays.
- No privileged state: use only the camera images, the service's replies and this text; no simulator internals or hidden
  state.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Reviews: after every rally the world freezes; send `game ready "WHY" "PLAN"`, a short review, within 300 s of real
  time (`timing.review_timeout_s` in `game spec`), or your side loses the match (`ready_timeout`), even when you are
  ahead. The world does not go on by itself: watch for the freeze (your program's log, `game status`) and review at
  once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The game (ITSF rules, with these changes):
- One game: the first to 5 goals wins. Every goal, possession-time foul, incomplete opening sequence, illegal spin, dead
  ball or ball off the table ends a rally: the world freezes for the reviews, every rod returns to slide 0, angle 0, and
  the next rally starts with the restart. The game also ends after 240 s of play (frozen time does not count) or 40
  rallies: then the player with more goals wins, at equal goals the player who scored the last goal, if nobody has
  scored the player with the ball less time in its own half, and as a last resort the player who did not have the first
  kick-off. There are no draws.
- Kick-off: a rally starts with the ball at rest beside the central figure of the restart rod. The first kick-off is
  `match.first_kickoff`'s (`game spec`); after a goal the team that conceded kicks off. Before the ball may leave the
  restart rod (the 5-rod, or the goalkeeper rod and 2-rod together), the restarting team must complete the opening
  sequence: a move by one figure, a contact by another figure, then a contact by any figure other than that second one
  (`restart.opening_complete` in the state). If the ball leaves first, the opponent gets the ball on its 5-rod
  (incomplete_opening). The world is not frozen during the opening. The referee places the ball (its side, and a few
  millimetres along the rod, drawn from the seed); play starts when the reviews are in.
- Goal: the ball wholly over the goal line scores 1 point for the other team, whoever touched it last.
- Possession: while the ball is within reach of a rod (a figure of it can touch the ball), that rod's possession clock
  runs; it restarts when the ball leaves the rod's reach. The goalkeeper rod and 2-rod count as one (the goalie rod).
  Limits: goalie rod 15 s, 5-rod 10 s, 3-rod 15 s. Over the limit is a foul: after the goalie rod or the 5-rod the
  opponent gets the ball on its 5-rod, after the 3-rod on its goalie rod. A foul gives no point. The restart rod's clock
  already runs during the opening sequence.
- Spinning: a transition (the ball leaving a rod's reach) after the rod turned more than a full turn before or after its
  contact is a foul (the opponent gets the ball on its 5-rod; a goal scored that way does not count); the rods' stops
  make a full turn impossible.
- Dead ball: a ball at rest for 1 s that no rod can reach is put back into play: between the two 5-rods by a kick-off
  (by the team that conceded the last goal, else the first kick-off's team), behind a 5-rod by the goalie rod of that
  half.
- Ball off the table: it goes to the goalie rod of the team that did not touch it last.
- A foul is always given as the possession award (the 5-rod or the goalie rod), without the non-offending team's option
  to play on, warnings, penalty shots or time-outs; a foul gives no point. The passing and wall rules and playing the
  ball dead are not judged; there is no delay-of-game rule.

### This run: no success signal
This run hides the match's result.

- No reply shows the score, a point's, rally's or phrase's result, who scored a goal or the match's winner: they are
  left out of `/status`, `/observe` and every other answer (`/spec` keeps the rules). The rest is unchanged: the phase
  (`over` once the match has ended by its rules), the reviews, the clocks, your robot's state and the images.
- You decide when you are done: `POST http://localhost:8000/$SEAT/finish` with `{}` (`game` has no command for it; in
  Python `requests.post(base + "/finish", json={})`). It ends your session at once and the match is decided as when your
  session ends: before `game start` a no-show, during the match abandoned (a valid result, success 0), after the match
  has ended its result stands. After `/finish` every call but `/spec` and `/status` is refused (409).
- The match is graded with the task's rules: you succeed if you win it. Play it to its end before you finish.

## Robot Interface
### Client
The `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the limits, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly). Acts are never out of turn: one in flight per seat (it may address several rods).

### Actions
- `rods`:
  `game act '{"type": "rods", "rods": {"midfield": {"slide": 0.03, "angle": 1.1, "omega": 40}, "goalie": {"slide": -0.05}}}'`
  (`POST /act` with that body; `"type"` may be left out): new targets for any of your rods goalie, defence (2-rod),
  midfield (5-rod) and attack (3-rod); rods you do not name keep their targets. slide (m) moves the rod along your local
  v (0 = centre; within ±0.11 goalie, ±0.19 defence, ±0.06 midfield, ±0.11 attack); angle (rad) turns it (0 = figures
  hanging straight down, + = feet swing towards the opponent's goal, up to ±2.6; 1.5 is about level, so a ball passes
  underneath); optional omega (rad/s, at most 52) and speed (m/s, at most 2.0) cap the rod's angular and sliding speed
  for this target. Each rod follows a smooth path to the target (sliding at most 2.0 m/s and 40 m/s^2, turning at most
  52 rad/s and 4000 rad/s^2) with limited force (60 N) and torque (5 N m); the rod itself never moves faster than 2.0
  m/s or 52 rad/s, not even when the ball pushes it: a rod the ball held up catches up with its path at these speeds at
  most; an action takes effect 2 control steps (20 ms of game time) after it arrives: it reaches the motors 2 control
  steps after the control step that takes it (the reply's `took_effect`: `taken_step`, `effect_step` = `taken_step` +
  2), and holds until replaced; the rods cannot make a full turn (stops at ±2.8 rad). Out of range: HTTP 400.

### Observations
- The state: your own rods (slide, angle, their velocities and the command at the motors), fouls, the time of play and
  of the rally, the play time left, the referee's restart (which team and rod puts the ball into play, whether its
  opening sequence is complete) and the rallies that ended (last_rally, rallies: how, who scored or fouled, the
  restart); no ball or opponent coordinates. The image: one 384 × 240 RGB tile from the fixed overhead camera straight
  above the table centre at 1.45 m (32 degree vertical field of view; `game spec` camera / cameras), turned so that your
  own goal is on the left and the image's right and up are your local +u and +v. The ball is orange, seat A's figures
  blue, seat B's red, the rods grey; figures and rods can hide the ball.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`.

### Frame and table
- Metres, seconds. World frame: x along the table (seat A's goal at x = -0.60, seat B's at x = +0.60), y across, z up,
  playfield z = 0 with its centre at (0, 0). Your local frame (the image, your rods, `game spec` geometry): u towards
  the opponent's goal, v to the left when you look along u (seat A: u = x, v = y; seat B: u = -x, v = -y).
- Playfield 1.20 × 0.68 m between side walls with rounded fillets (radius 0.02 m), goal mouths 0.20 m wide; ball radius
  0.0175 m, 24 g, it rolls with little resistance (about 0.1 m/s^2), bounces off the walls and is stopped by a figure it
  runs into; a kick sends it off at about the foot's speed, at an angle when the foot hits it off centre. Rods 0.09 m
  above the playfield at u = -0.525 (your goalkeeper rod), -0.375 (2-rod), -0.075 (5-rod), 0.225 (3-rod), the opponent's
  at the negated u; figures at slide 0 (v): goalkeeper and 3-rod -0.20, 0, 0.20; 2-rod -0.12, 0.12; 5-rod -0.24, -0.12,
  0, 0.12, 0.24; a foot is a capsule along u (radius 0.012 m, half length 0.014 m) 0.075 m below the rod. Physics 1000
  Hz, control 100 Hz (10 ms steps); a transparent cover 4 cm above the playfield normally keeps the ball on the table.

### Time
The world waits for you: it advances only during an open `game wait DT` (at most DT game seconds, then it stops again)
and, for an action you sent, up to the control step at which it takes effect (the step after the state it answers).
Between your calls it stands still: your thinking, your program's computation and the service's planning of an action
take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on; a match you leave
standing never ends, and it is lost when your session ends. `game spec` says so (`timing.clock` = `lockstep`). At the
end of every unit (a rally; `game spec`) the world freezes for the reviews; the reviews' time limit and the start window
are real time.

## Others
- The scripted team (red, level 3 of 4; `match.opponent_level` in `game spec`): it plays the reference player's policy
  on the true ball position a reaction delay ago (90 ms) and never reads your commands; it slides at up to 1.6 m/s and
  kicks at 45 rad/s, shoots from every rod, aims past your figures, passes, lifts its rods out of its shots and splits
  the goal between goalkeeper and 2-rod. Its rods are yours (the same top speeds).
- A full-speed kick sends the ball off at about 4-5 m/s (at most about 5.4 m/s).
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one game.
