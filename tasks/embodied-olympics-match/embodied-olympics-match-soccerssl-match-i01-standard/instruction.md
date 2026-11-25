# Embodied Olympics · wheeled robot soccer 5 v 5 (RoboCup SSL Division B), match against level 4 (standard)

## Task
Win a 5 v 5 wheeled robot soccer match against the yellow team.

## Goal
Success: your team wins the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One match, no reset: a goal against you stays.
- Use only the camera images, the service's replies and this text: no simulator internals or hidden state.
- Reviews: after every goal, at half time, before the shoot-out and after every shoot-out kick the world freezes; send
  `game ready "WHY" "PLAN"`, a short review, within 600 s of real time (`timing.review_timeout_s` in `game spec`), or
  your side loses the match (`ready_timeout`), even when you are ahead. The world does not go on by itself: watch for
  the freeze (your program's log, `game status`) and review at once.
- Start window: send `game start` within 1800 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first.
- You may write a program that observes, measures in the images, computes your next action and sends it, without a new
  model response for each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send
  `game start` and `game ready`.

The match (RoboCup SSL rules, Division B, with these changes):
- Two halves of 300 s of playing time (the clock stops whenever no team may play the ball); the teams change ends at
  half time. A team with 10 goals and a lead of more than one wins at once.
- Level after two halves: a shoot-out of 5 penalty kicks each, then sudden death, after 10 rounds a seeded coin toss; no
  overtime. In the shoot-out each team shoots at the goal it attacked in the second half, the team that kicked off first
  shoots first, robot 1 kicks and robot 0 keeps. There are no draws.
- A goal counts only if the ball fully entered the goal between the posts, its lowest point was never above 0.15 m after
  the scoring team's last touch, the team had no more robots on the field than allowed and committed no non-stopping
  foul in the last 2 s; else play goes on as for a ball over the goal line.
- A robot other than the keeper touching the ball while entirely inside its own defense area gives the other team a
  penalty kick (no foul counted).
- Every third foul of a team is a yellow card: one robot fewer for 120 s of playing time. Name the robot to take off
  with substitute(to = off) within 10 s (else the referee takes one off: the card's last offender, else your
  highest-numbered field robot) and bring it back with substitute(to = on) when the card expires. A third card while two
  yellow cards are active is red: one robot fewer for the rest of the match.

## Robot Interface
Wheeled robot soccer 5 v 5 under the RoboCup Small Size League rules (Division B): ten omnidirectional SSL robots
(kicker, chip kicker, dribbler; their real speed, acceleration, kick and dribbler limits) and an orange golf ball on the
9 × 6 m field, with an automatic referee. You command your robots with skills (move to a pose, kick flat or chipped,
spin the dribbler) and see the game through four overhead cameras, 40 ms late. You are seat `A` and command the blue
team against the yellow team at level 4. The world waits for you: it advances only while you let it (`### Time` below).
The robot runs as a service you reach only through its client, as if it were real hardware: one live episode.

### Client
The `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges; `skill_contract`), the cameras (pose, field of view, size, `focal_px`, `principal_point_px`), the world frame, the limits, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game move ENTITY X Y THETA` | `POST /act {"type": "move", ...}` | a robot's `move` (the fields: `game spec`) |
| `game kick ENTITY SPEED MODE ARMED_FOR` | `POST /act {"type": "kick", ...}` | a robot's `kick` |
| `game dribble ENTITY RPM` | `POST /act {"type": "dribble", ...}` | a robot's `dribble` |
| `game substitute ENTITY TO` | `POST /act {"type": "substitute", ...}` | take a robot off or bring it back (`substitute`) |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

### Actions
- Your actions are the sport's skill API (`move`, `kick`, `dribble`): the platform executes each one; `game spec`
  (`skill_contract`) says exactly what it delivers.
- Per robot (`entity` = its number as a string): move(x, y, theta[, t][, v_end]) the base to a pose in your frame, by
  game time t (state.t_sim; omit: as fast as possible), at velocity v_end (omit: at rest), planned at the real limits
  from where the robot is (no obstacle avoidance: it never looks at the ball or other robots); kick(speed, mode
  flat|chip, armed_for s) along the robot's heading, now (with the ball in the break beam) or the moment the ball blocks
  the beam within armed_for; dribble(rpm); substitute(to off|on) the robot handler; batch(commands) several robots at
  one boundary. A command takes effect at the next 10 ms control step and replaces the robot's previous command of the
  same skill; one act per robot in flight (429); a robot off the field: 409. The full contract: `skill_contract` in
  `game spec`.
- Your robots: after TIGERs Mannheim's v2020: 0.178 m across, 0.148 m high, 2.62 kg, flat front 0.0715 m from the centre
  with the dribbler opening and the kicker; base: 3 m/s, 3 m/s^2 (also braking), jerk 150 m/s^3, 20 rad/s, 50 rad/s^2;
  kicker: flat up to 8.5 m/s, chip up to 5.5 m/s at 45 deg, speed scatter 3 %, direction 1 deg (1 sigma), the capacitor
  full in 2 s (a kick at v needs (v / v_max)^2 of the full charge and uses a quarter of that); dribbler: up to 17000
  rpm; WITH THE BALL (accelerating at 3 m/s^2) a robot loses it at about 2.3 m/s backwards (up to about 2.8 m/s with the
  bar above 8000 rpm), 2.6 m/s sideways and 9.3 rad/s turning (the move skill turns at up to 20 rad/s: turn in steps
  when you hold the ball); it receives balls up to about 4-5 m/s; a push of about 0.75 N takes a held ball; on top the
  SSL pattern: a 50 mm blue or yellow centre dot and four 40 mm pink / green dots for the id (`game spec`
  `vision_pattern`).

### Observations
- The four overhead camera tiles (2 × 2: top-left = world x < 0, y > 0; 800 × 600 each; calibration in `game spec`
  cameras: straight down from 4.0 m, image right = world +x, image up = world +y; the robots' tops at 0.148 m), showing
  the world vision.latency_s = 0.04 s ago (vision.t_capture; frame.age_s = the image's age now); team (your colour,
  robots, keeper); frame.attack_sign; robots: each of YOUR robots' own state (on_field, pose, vel, vel_body,
  dribbler_rpm, kicker_charge, kicker_wait_max_s, kicker_armed, ball_in_beam, target, eta); referee: the game
  controller's information (stage, half, command, for_team, next_command, play_time, time_left, score, fouls,
  yellow_cards_left_s, red_cards, allowed_robots, on_field, placement, remove_robot_within_s, shootout); events of the
  current unit (the referee's calls with their locations; your robots' command results and kicker events); no ball or
  opponent coordinates.
- The images are ideal (no noise, no lens distortion, no motion blur, even lighting); both teams see the same images.
- Pinhole cameras (`game spec` gives each one's pose, field of view, size, `focal_px` and `principal_point_px`):
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
The world waits for you: it advances only during an open `game wait DT` (at most DT game seconds, then it stops again)
and, for an action you sent, up to the control step at which it takes effect (the step after the state it answers).
Between your calls it stands still: your thinking, your program's computation and the service's planning of an action
take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on; a match you leave
standing never ends, and it is lost when your session ends. `game spec` says so (`timing.clock` = `lockstep`). At the
end of every unit (a goal or another stoppage; `game spec`) the world freezes for the reviews; the reviews' time limit
and the start window are real time. Reaction delay: an action takes effect no earlier than 2 control steps after the
step of the latest world state you were sent (`now.step` of any reply; `timing.reaction_delay_steps` in `game spec`),
the same for every player; if your program needs longer, its own time counts instead. The act's reply says when it took
effect (`took_effect.step`).

### Physics
- The ball: an orange golf ball, 0.043 m, 0.046 kg; kicked flat it slides at about 3.4 m/s^2 and rolls at about 5/7 of
  its speed after about 0.7 s, then slows by 0.45 m/s^2; a chipped ball bounces with a vertical restitution of about
  0.54; no air drag.

### Container
- Your container: Python 3.12 with numpy, SciPy and Pillow.

## Others
- Five robots per team, numbers 0-4, robot 0 the keeper.
- Restarts: kick-off (all robots in their own half outside the centre circle, one robot of the kicking team may be
  inside it) and free kick (the defenders keep 0.5 m from the ball) are in play once the ball moved 0.05 m or after 10
  s; penalty kick: keeper on the goal line, the others 1 m behind the ball, 10 s, the ball may only move towards the
  goal. The referee places the ball 1 s after a stop; the game goes on 2 s after all robots keep the distance and the
  ball is steady, at the latest 10 s after the placement. After a goal the other team kicks off.
- Ball out: over a touch line, a free kick for the other team 0.2 m inside the line where it crossed; over a goal line,
  a goal kick (1 m from the goal line, 0.2 m from the touch line) or a corner kick (0.2 m from both lines) for the team
  that did not touch it last. An aimless kick (touched in its own half, then over the halfway line and out over the
  opponent goal line without another touch) gives the other team a free kick where it was kicked.
- Stopping fouls (a free kick for the other team): closer than 0.2 m to the opponent defense area in stop or before a
  free kick is taken (2 s grace), pushing, ball holding, the keeper holding the ball 10 s in a defense area, dribbling
  more than 1 m from where the contact began, kicking the ball over the walls; a double touch by the kicker of a
  kick-off or free kick also gives the other team a free kick (no foul counted).
- Non-stopping fouls (each robot is called at most once per 2 s for the same foul): touching the ball inside the
  opponent defense area (not while robots of both teams touch it), kicking the ball above 6.5 m/s, crashing (a collision
  with a projected speed difference above 1.5 m/s: the faster robot, both when their speeds are about equal); with the
  ball out of play, closer than 0.5 m to the ball at an opponent kick-off or free kick, or faster than 1.5 m/s in the
  STOP state (not during kick-off or penalty preparation; 2 s grace; the platform does not slow your robots).
- The referee's definitions: pushing is an opponent moved away during a contact, ball holding is two or more robots of a
  team crowding the ball for 1 s, dribbling ends at a visible gap between the ball and the robot. Robots still out of
  position 10 s into a kick-off or penalty preparation are moved to legal spots, with one foul for each team; no
  progress for 10 s gives a force start; other unsporting behaviour is not judged.
- The yellow team (level 4) is the official level 3 team with a trained network choosing each robot's option; it reads
  the true state after a reaction delay and commands its robots with the same skills and limits as yours.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and graded on what stands, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the clocks the service reports are the game's own. Calls
  into a long-running process can block for their whole wait time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included.
- Resources: 2 CPUs, 5 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`), no
  GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap only
  slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one match.
