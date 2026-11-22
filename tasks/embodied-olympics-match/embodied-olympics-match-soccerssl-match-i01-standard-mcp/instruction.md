# Embodied Olympics · wheeled robot soccer 5 v 5 (RoboCup SSL Division B), match against level 4 (standard-mcp)

## Task
Wheeled robot soccer 5 v 5 under the RoboCup Small Size League rules (Division B): ten omnidirectional SSL robots
(kicker, chip kicker, dribbler; their real speed, acceleration, kick and dribbler limits) and an orange golf ball on the
9 × 6 m field, with an automatic referee. You command your robots with skills (move to a pose, kick flat or chipped,
spin the dribbler) and see the game through four overhead cameras, 40 ms late. You are seat `A` and command the blue
team against the yellow team at level 4 (Others). The world waits for you: it advances only while you let it (Robot
Interface, `### Time`). The robot runs as a service you reach only through the `efe-robot` MCP tools, as if it were real
hardware: one live episode.

## Goal
Success: your team wins the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never called `start`, you lose.

Nothing to hand in: the service records and grades the episode, and the tool server records your calls.

Real-robot rules:
- One match, no reset: a goal against you stays.
- No privileged state: use only the camera images, the tools' results and this text; no simulator internals or hidden
  state.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.
- Reviews: after every goal, at half time, before the shoot-out and after every shoot-out kick the world freezes; call
  `ready(why, plan)`, a short review, within 600 s of real time (`timing.review_timeout_s` in `spec`), or your side
  loses the match (`ready_timeout`), even when you are ahead. The world does not go on by itself: watch for the freeze
  (`review_due` in every result) and review at once.
- Start window: call `start` within 1800 s of real time after the match service starts (`start.window_s` in `spec`), or
  you lose the match (`no_show`). The match does not run before that: read `spec` first.
- Tools only: you may write and run code to compute, but every robot command and observation is an `efe-robot` tool call
  you make yourself; no script starts or calls the tool server, and code must not contact the simulator (the service's
  request log is checked against the server's).

The match (RoboCup SSL rules, Division B, with these changes):
- Two halves of 300 s of playing time; the clock stops whenever no team may play the ball (stop, kick-off and penalty
  preparation); level after two halves: a shoot-out of 5 penalty kicks each, then sudden death (after 10 rounds a seeded
  coin toss); a team with 10 goals and a lead of more than one wins at once. No overtime: in the shoot-out each team
  shoots at the goal it attacked in the second half, the team that kicked off first shoots first, robot 1 kicks and
  robot 0 keeps. The teams change ends at half time. There are no draws.
- Five robots per team, numbers 0-4, robot 0 the keeper; every yellow or red card takes a robot off.
- Restarts: kick-off (all robots in their own half outside the centre circle, one robot of the kicking team may be
  inside it; in play when the ball moved 0.05 m or after 10 s); free kick (the defenders keep 0.5 m from the ball; in
  play after 0.05 m or 10 s); force start; penalty kick (keeper on the goal line, the others 1 m behind the ball, 10 s,
  the ball may only move towards the goal); the referee places the ball 1 s after a stop, the game goes on 2 s after all
  robots keep the distance and the ball is steady, at the latest 10 s after the placement; after a goal the other team
  kicks off.
- Ball out: over a touch line: free kick for the other team 0.2 m inside the line where it crossed; over a goal line:
  goal kick (1 m from the goal line, 0.2 m from the touch line) or corner kick (0.2 m from both lines) for the team that
  did not touch last; aimless kick: touched in its own half, over the halfway line and out over the opponent goal line
  without another touch: free kick for the other team where it was kicked.
- Goals: a goal counts if the ball fully entered the goal between the posts, its height (its lowest point above the
  carpet) was never above 0.15 m after the scoring team's last touch, the team had no more robots on the field than
  allowed and committed no non-stopping foul in the last 2 s; else play goes on as for a ball over the goal line.
- Fouls: stopping fouls (free kick for the other team): closer than 0.2 m to the opponent defense area in stop or before
  a free kick is taken (2 s grace), pushing, ball holding, keeper held ball (the ball 10 s in a defense area), dribbling
  more than 1 m from where the contact began, kicking the ball over the walls; a robot other than the keeper touching
  the ball while entirely inside its own defense area: penalty kick (no foul counted); double touch by the kicker of a
  kick-off or free kick: free kick for the other team (no foul counted); non-stopping fouls (each robot is called at
  most once per 2 s for the same foul): touching the ball inside the opponent defense area (not while robots of both
  teams touch the ball), accelerating the ball above 6.5 m/s, crashing (a collision with a projected speed difference
  above 1.5 m/s: the faster robot is called, both when their speeds are about equal); with the ball out of play: closer
  than 0.5 m to the ball during an opponent kick-off or free kick, faster than 1.5 m/s in the STOP state (not during
  kick-off or penalty preparation; 2 s grace; the platform does not slow your robots); no progress for 10 s: force
  start.
- Cards: every third foul of a team is a yellow card: one robot fewer for 120 s of playing time; name the robot to take
  off with substitute(to = off) within 10 s (else the referee takes one off: the card's last offender, else your
  highest-numbered field robot); when the card expires bring it back with substitute(to = on); a third card while two
  yellow cards are active is red (one robot fewer for the rest of the match).
- The automatic referee judges every rule an SSL auto-referee judges, by fixed definitions: pushing (an opponent moved
  away during a contact), ball holding (two or more robots of a team crowding the ball for 1 s), the end of dribbling (a
  visible gap between the ball and the robot), a penalty ball that goes back. Robots still out of position 10 s into a
  kick-off or penalty preparation are moved to legal spots, with one foul for each team; other unsporting behaviour is
  not judged.
- A goal, half time, full time before a shoot-out and every shoot-out kick end a unit: the world freezes for the
  reviews.

## Robot Interface
### Tools
The `efe-robot` tools (in your tool list, e.g. `mcp__efe-robot__act`):
- `spec()`: the actions (types, fields, ranges; `skill_contract`), the cameras (pose, field of view, size, `focal_px`,
  `principal_point_px`), the world frame, the limits, the rule constants, the timing; the whole spec also as a JSON file
  (`spec_file`).
- `status()`: the current state, no image.
- `start()`: you are ready; the match begins when every seat has started.
- `wait(seconds)`: let up to 10 game seconds pass in one call; it stops early when the world freezes for a review or the
  match ends.
- `observe(query?, inline_tiles?)`: the state and the camera images as PNG files under `/app/obs/` (the view and one
  file per tile, native size; pixel coordinates in a tile are its camera's own); `inline_tiles` puts tiles in the
  result.
- `act(action)`: one action, an object with `type` and the fields `spec` lists for it, e.g. `act({"type": "move", ...})`
  (a robot's `move`).
- `ready(why, plan)`: your review (each at most 2000 characters).
- Every result is the service's reply (the state under `now` or `state`), plus `review_due` (call `ready` now) and
  `match_over`. A refused call returns the service's error (400 an invalid action, nothing happens; 409 not now); the
  tools keep to the service's request rate themselves. One call at a time; one still running after 45 s returns
  `{"pending": true, "operation": id}`: collect it with `wait(operation=id)`.

### Actions
- Your actions are the sport's skill API (`move`, `kick`, `dribble`): the platform executes each one; `spec`
  (`skill_contract`) says exactly what it delivers.
- Per robot (`entity` = its number as a string): move(x, y, theta[, t][, v_end]) the base to a pose in your frame, by
  game time t (state.t_sim; omit: as fast as possible), at velocity v_end (omit: at rest), planned at the real limits
  from where the robot is (no obstacle avoidance: it never looks at the ball or other robots); kick(speed, mode
  flat|chip, armed_for s) along the robot's heading, now (with the ball in the break beam) or the moment the ball blocks
  the beam within armed_for; dribble(rpm); substitute(to off|on) the robot handler; batch(commands) several robots at
  one boundary. A command takes effect at the next 10 ms control step and replaces the robot's previous command of the
  same skill; one act per robot in flight; a robot off the field: 409. The full contract: `skill_contract` in `spec`.
- Your robots: after TIGERs Mannheim's v2020: 0.178 m across, 0.148 m high, 2.62 kg, flat front 0.0715 m from the centre
  with the dribbler opening and the kicker; base: 3 m/s, 3 m/s^2 (also braking), jerk 150 m/s^3, 20 rad/s, 50 rad/s^2;
  kicker: flat up to 8.5 m/s, chip up to 5.5 m/s at 45 deg, speed scatter 3 %, direction 1 deg (1 sigma), the capacitor
  full in 2 s (a kick at v needs (v / v_max)^2 of the full charge and uses a quarter of that); dribbler: up to 17000
  rpm; WITH THE BALL (accelerating at 3 m/s^2) a robot loses it at about 2.3 m/s backwards (up to about 2.8 m/s with the
  bar above 8000 rpm), 2.6 m/s sideways and 9.3 rad/s turning (the move skill turns at up to 20 rad/s: turn in steps
  when you hold the ball); it receives balls up to about 4-5 m/s; a push of about 0.75 N takes a held ball; on top the
  SSL pattern: a 50 mm blue or yellow centre dot and four 40 mm pink / green dots for the id (`spec` `vision_pattern`).

### Observations
- The four overhead camera tiles (2 × 2: top-left = world x < 0, y > 0; 800 × 600 each; calibration in `spec` cameras:
  straight down from 4.0 m, image right = world +x, image up = world +y; the robots' tops at 0.148 m), showing the world
  vision.latency_s = 0.04 s ago (vision.t_capture; frame.age_s = the image's age now); team (your colour, robots,
  keeper); frame.attack_sign; robots: each of YOUR robots' own state (on_field, pose, vel, vel_body, dribbler_rpm,
  kicker_charge, kicker_wait_max_s, kicker_armed, ball_in_beam, target, eta); referee: the game controller's information
  (stage, half, command, for_team, next_command, play_time, time_left, score, fouls, yellow_cards_left_s, red_cards,
  allowed_robots, on_field, placement, remove_robot_within_s, shootout); events of the current unit (the referee's calls
  with their locations; your robots' command results and kicker events); no ball or opponent coordinates.
- The images are ideal (no noise, no lens distortion, no motion blur, even lighting); both teams see the same images.
- Pinhole cameras (`spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
  `u = cx + f · x_right / depth`, `v = cy - f · y_up / depth`.

### Frame and field
- Metres, seconds, radians; the world frame has its origin at the field centre, x along the 9 m length, y along the 6 m
  width; YOUR TEAM'S FRAME (every command, every coordinate of the observation): you attack +x (the goal at x = +4.5)
  and defend the goal at x = -4.5, y to the left when facing +x, theta counter-clockwise from +x; the camera images are
  in the world frame: observation.frame.attack_sign (+1 or -1) maps them (team x, y = attack_sign * world x, y); blue
  attacks +x in the world in the first half and the teams change ends at half time.
- Division B: field of play 9 × 6 m (lines 0.01 m wide, a line belongs to the area it bounds), walls 0.3 m beyond the
  field lines (0.1 m high), centre circle diameter 1 m, defense areas 2 m wide × 1 m deep in front of each goal, penalty
  marks 6 m from the goal they face (x = ∓1.5); goals 1 m wide inside, 0.18 m deep, 0.16 m high, no crossbar, foam
  inside; substitution area: the field margin within 1 m of the halfway line.

### Time
The world waits for you: it advances only during a `wait(seconds)` call (at most the game seconds you give, then it
stops again) and, for an action you sent, up to the control step at which it takes effect (the step after the state it
answers). Between your calls it stands still: your thinking and the service's planning of an action take no game time,
so you have to keep calling `wait` (or acting) for the match to go on; a match you leave standing never ends, and it is
lost when your session ends. `spec` says so (`timing.clock` = `lockstep`). At the end of every unit (a goal or another
stoppage; `spec`) the world freezes for the reviews; the reviews' time limit and the start window are real time.
Reaction delay: an action takes effect no earlier than 2 control steps after the step of the latest world state you were
sent (`now.step` of any reply; `timing.reaction_delay_steps` in `spec`), the same for every player; if you take longer,
your own time counts instead. The act's reply says when it took effect (`took_effect.step`).

## Others
- The yellow team, level 4 (`match.opponent_level` in `spec`): the official level 3 team with a trained network choosing
  each robot's option; it reads the true state with a reaction delay and commands its robots with the same skills and
  limits.
- The ball: an orange golf ball, 0.043 m, 0.046 kg; kicked flat it slides at about 3.4 m/s^2 and rolls at about 5/7 of
  its speed after about 0.7 s, then slows by 0.45 m/s^2; a chipped ball bounces with a vertical restitution of about
  0.54; no air drag.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (the time the tools take too). At
  the end you are stopped without warning and graded on what stands, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the clocks the service reports are the game's own. Calls
  into a long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the files the tools write included. Do not search for or download a ready-made
  solution (published or reference solutions, recorded demonstrations, trained policies); trials are reviewed.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one match.
