# Embodied Olympics · robot soccer 2 v 2 at the joint level (CPU + GPU tier), match against level 5 (standard)

## Task
Win a 2 v 2 robot soccer match against the other team.

## Goal
Success: your team wins the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Keep your scripts, logs and notes in `/app/output/`, with a short `/app/output/NOTES.md`: what you built, what you
trained (for how long, on what) and what it gained.

Rules:
- **No cheating.** No walking or balancing policy you did not build in this session (in particular not the released
  Booster or SaiResearch T1 walking policies, nor anything made from them), and do not search for, download or use any
  existing solution; a team found driving its robots with one loses the match.
- One match, no reset: a goal against you stays.
- No privileged match internals: use only the service's replies (your robots' state and the full-state `truth`), your
  toolkit and this text.
- Start window: send `game start` within 7200 s of real time after the match service starts (`start.window_s` in
  `game spec`), or you lose the match (`no_show`). The match does not run before that: read `game spec` and prepare your
  program first. Until then you develop and test your team; the world waits.
- Reviews: at every stoppage (a goal, half time, a dropped ball, full time, each shoot-out kick) the world freezes; send
  `game ready "WHY" "PLAN"`, a short review, within 300 s of real time (`timing.review_timeout_s` in `game spec`), or
  your side loses the match (`ready_timeout`), even when you are ahead. The world does not go on by itself: watch for
  the freeze (your program's log, `game status`) and review at once. You may use a review to improve your program
  (practice matches run on) and restart it; the opponent does not review.
- You play through a program that observes, computes your robots' rows and sends them, without a new model response for
  each action; you stay in the loop (watch its log, stop, fix and restart it). Only you send `game start` and
  `game ready`.
- Before `game start`, write `/app/output/METHOD.md` (form: `/opt/robot/METHOD_TEMPLATE.md`): the controller's structure
  and the methods you used, what you tuned or trained and how. It is a record only: any method is allowed and nothing in
  it can lose you the match.

The match (RoboCup Humanoid Soccer League rules, with these changes):
- Two halves of 5 minutes of game time; more goals after two halves wins, or a 10-goal lead at any time (the mercy
  rule). No change of ends (each team's frame stays), no timeouts, no designated goalkeeper, no substitutes.
- If the score is level after two halves, there is a penalty shoot-out of 3 kicks each. Then come up to 3 sudden-death
  rounds, each won by the better kick (goal, saved, post, wide, other, no kick), and then a coin toss drawn from the
  seed. There are no draws.
- In the shoot-out the team that kicked off first shoots first. The strikers are robot 1, 2, 1, and the keeper is the
  other team's robot with the same number. Each team shoots at the goal it attacks. The striker has 20 s to touch the
  ball. A keeper more than 0.6 m from its goal line before the touch concedes a goal.
- After a kick-off the ball is in play once it has moved 0.15 m, or 10 s after play resumes. The kick-off team must
  touch it outside the centre circle before it can score; otherwise there is no goal, and the other team kicks off.

## Robot Interface
Robot soccer 2 v 2 at the joint level: four simulated Booster T1 humanoids (lower bodies: legs and trunk, held to the
real robot's joint and motor limits) and one ball on a boarded 10 × 7 m pitch. There is no walking policy and no kick
skill: each of your robots takes 12 leg joint targets every 20 ms of game time, and balance, walking, turning, kicking
and getting through contacts are yours to build. You are seat `A` and command both robots of team A. This is the CPU +
GPU tier: one GPU with a GPU training environment (Robot Interface, `### GPU training`); train controllers, write them
by hand, or combine both. The world waits for you: it advances only while you let it (`### Time` below). The robot runs
as a service you reach through its client or its MCP tools, as if it were real hardware: one live episode.

### Client
The service at `http://localhost:8000` speaks eai-standard/2.x with the match extension (`eai-standard/2.1+match/1.0`;
docs/protocol/standard_mode.md Part 5): the endpoints of every standard task, plus `/start` and `/ready`. The shared
client is installed (`from rcb_client import Robot`).

| HTTP | |
| --- | --- |
| `GET /spec` | the standard spec (`cameras` with intrinsics and pose, `action_types` with each type's fields and row layout, `timing`) and, under `match`, everything `game spec` gives |
| `GET /status` | the state, no image |
| `POST /start {}` | you are ready; the match begins when every seat has started |
| `POST /observe {"cameras": [...]}` | the camera images of now, at once; no time passes (RCB1: `last/<camera>`, `frames/<camera>`, `view` = the tiled PNG of `game observe`) |
| `POST /submit {"type": T, "rows": [ACTION, ...], "dt": DT}` | your actions (the objects of `game act`), one after the other, each followed by DT of game time |
| `POST /submit {"type": T, "interpolate": "hold", "seconds": S}` | lets S seconds of game time pass with your last actions in force (as `game wait S`) |
| `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

`/submit` returns after its last row: each row takes effect at the current step, then the world advances DT (default:
one control step). An action the match refuses is a 400 (a later row's: `code` 400 in `meta.effects`). Where an action
names a robot (`entity`), one chunk commands one: `"entity": E` in the chunk, or the type `T@E`. Every answer's `meta`
has `score`, `review_due` (send `/ready` now), `match_over`, `step`, `phase` and your `state`. A `/submit` while the
world is frozen or before the start executes nothing (`ok: false`, `not_now`); after the match is over requests are a
409. `/finish` and `/reset` are not offered (404): the match's rules end it, and there is one match. What differs from
the plain standard: `timing.deviations` in `/spec`.

The same match also answers the `game` command, or the same calls as HTTP with JSON under
`http://localhost:8000/<SEAT>/` (the paths below are under it; your seat is `$SEAT`); you may use both:

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the joint level (joints, ranges, row limits, PD, motors, stance), the frame, the pitch, the ball, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens); 409 = not now (not your turn, or a review is due); 429 = one action
already in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from
your seat (empty body: retry more slowly).

### MCP tools
- The same service is also an MCP server, `efe-robot` (in your tool list), with one tool per endpoint: `spec`,
  `observe`, `submit`, `start`, `ready`. A tool takes its endpoint's request fields (any other field in `fields`) and
  returns the service's reply `meta` unchanged; images are written as files under `/app/obs/` (`.png`, `.npy`) and the
  result lists them. There is no `finish` tool: the match's rules end it.
- `observe` returns at once; time passes only through `submit`; a `submit` with `interpolate` "hold", `seconds` and no
  rows lets it pass.
- A call still running after 45 s returns `pending` with an `operation` id; `observe(operation=id)` collects its reply.
- The client, the `game` command and the tools play the same seat in the same match; use any of them.

### Actions
- Actions (per robot, `entity` = its number): `{"type": "joints", "q": [12 targets]}` for the next control step,
  `{"type": "traj", "k0": K, "q": [[12], ...]}` a plan of up to 50 rows from control step K (a new act replaces the rest
  of the plan; after the last row the robot holds it), `{"type": "hold"}`. Joint order: left hip pitch, roll, yaw, knee,
  ankle pitch, ankle roll, then the right leg (`game spec` -> joint_level.joints, with the ranges).
- Execution (exactly as the real T1's joint position mode): each row is limited (at most the URDF joint speed × 20 ms
  from the previous row, inside the joint ranges; non-finite values keep the previous row), then PD every 2 ms with
  Booster's deployment gains (hip, knee 200; ankle 50 N m/rad; damping 5 / 1; fixed), then the motors: the URDF torques
  45 / 30 / 30 / 60 / 24 / 15 N m, a torque-speed envelope (full torque up to 64 % of the joint speed limit), a rated
  (continuous) torque of 60 % with an I^2 t foldback (a motor held at its peak for more than about 5 s folds back to the
  rated torque; your state shows each motor's heat `motor_heat`, 1 = at its limit), a 1 kW bus per robot.

### Observations
- Observation (`game status`, `game observe`; your team's frame): per own robot its pose, velocity, IMU, joint_pos,
  joint_vel, trunk_quat (w x y z), gyro, accelerometer (trunk frame), trunk_pos_z, trunk_vel, the row in effect (`row`),
  `plan_rows_left`, `held_s`, `motor_heat`, `step` (the control step), fallen, penalized; and `truth`: the ball's
  position and velocity and every robot's pose (this task gives you the full state; the cameras are there too, but you
  do not need them).

### Frame and pitch
- Metres, seconds; your team's frame: you attack the goal at x = +5 and defend the goal at x = -5, y to the left when
  facing +x, z up, yaw counter-clockwise from +x (both teams see the pitch this way in their own frame).
- Field of play 10 × 7 m (|x| <= 5, |y| <= 3.5), halfway line x = 0, centre circle radius 1.0 m, penalty areas 2.0 m
  deep and 4.0 m wide, goal areas 1.0 × 3.0 m, penalty marks 1.5 m in front of each goal line; boards 0.3 m high on the
  touchlines and goal lines except the goal mouths; goals 2.6 m wide (|y| < 1.3), 1.8 m high, 0.6 m deep with nets.

### Time
The world waits for you. It advances only during an open `game wait DT` (at most DT game seconds, then it stops again),
and, after you send an action, up to the control step at which that action takes effect (the step after the state it
answers). Between your calls the world stands still: your thinking, your program's computation and the service's
planning of an action take no game time. So a program has to keep calling `game wait` (or acting) for the match to go
on. A match you leave standing never ends, and you lose it when your session ends. `game spec` says so (`timing.clock` =
`lockstep`). At the end of every unit (a goal or another stoppage; `game spec`) the world freezes for the reviews; the
reviews' time limit and the start window are real time. Run your control loop in a program (`game status` + one act per
robot per step, or short `traj` plans to ride over hiccups); a step you miss keeps the row (or plan) in effect. An act
returns when it takes effect, at the next control-step boundary: one act per robot may be in flight, so send each
robot's acts from its own thread (or use plans); at most 20 requests per second and 4 open requests from your seat to
the match service.

### Practice: your copy of the match world
- CPU-parallel simulation (`/opt/robot/pool.py`): run many practice.py drills or rollouts at once on your 6 cores (both
  modes have the same).
- Practice matches (`/opt/robot/scrimmage.py`, service http://localhost:8100 on its own 4 CPUs, up to 4 worlds at a
  time): the match itself (same world, physics, motors, referee, rules, placements, kick-offs and the same observation
  dict as `game status`), but the world advances only when you call `step()`, as fast as your program runs (a 10-minute
  match takes a few minutes), and stoppages are resumed at once (no reviews). Opponents: `"L5"` (the team you meet in
  the match), `"L1"`, `"L2"`, `"L3"` (scripted teams on the released walking policy), all black boxes (you see what they
  do, not their code), or `"self"`. With `"self"` you drive both teams (team B sees the world in its own frame, as in a
  duel): spar your new program against your previous one. Practice seeds never coincide with match seeds; vary them.
- Drills (`/opt/robot/practice.py`, in your own process): the match's physics without referee or opponents, robots and
  ball placed where you like, pushes; for standing, walking, turning and kicking.
- Practice is free: it does not count, the match service does not see it, and it runs during the reviews too.

### GPU training
- GPU: one NVIDIA GPU (keep your GPU memory under about 10 GB; about 140 000 20-ms steps/s including PPO updates at 4096
  envs with the GPU free, 2-4x less when it is shared; the full match world: about 45 000-60 000 control steps/s at
  4096-8192 worlds).
- Two Python environments: `python3` (system: numpy, SciPy, MuJoCo at the match's version; your match program,
  practice.py, scrimmage.py and pool.py run here) and `/opt/train/bin/python` (mjlab on MuJoCo Warp with PyTorch (CUDA)
  and rsl_rl, ETH's PPO). No other ML packages; no internet access besides the package registries.
- The full 2 v 2 match world on the GPU `/opt/robot/train2v2/soc_mjlab.py`: four T1s, the ball, the referee's rules, the
  match's limiter, PD and motors, the scripted team at levels 1-3 (compiled: a black box, as in practice) or self-play;
  thousands of matches in parallel. Differences from the CPU match world: float32, no penalty shoot-out (a draw stays a
  draw), single trajectories drift apart after impacts (statistics agree). Training may use privileged state; the match
  gives you its own observation (your robots' state and `truth`).
- One T1 on the GPU `/opt/robot/train/hum_mjlab.py`: a single robot with a ball, for skills (walking, kicking).
- `example_rsl_rl.py` in each directory shows the rsl_rl plumbing (placeholder rewards) and the export of the actor to
  numpy. No reward is given: design your own.
- What you train runs in your own control program during the match (the GPU stays available; numpy inference of a small
  network takes well under a millisecond).
- The released Booster walking policy (inside `train2v2/soccer/models`) only drives the scripted opponents: using it, or
  anything made from it, for your robots is not allowed (a lost match).

### Kick-off
- Kick-off positions, in your frame: when you kick off, your robot 1 stands at about (-0.32, 0.06), facing +x behind the
  ball on the centre mark (the ball in its swing zone), and robot 2 at about (-2.5, -1.5). When the opponents kick off,
  your robots stand at about (-1.6, 0.4) and (-3.6, -0.8). Each position can be up to 0.3 m off (seeded).

### Physics
- The ball: radius 0.11 m, 0.45 kg, orange, a thin shell. On the turf it rolls with a deceleration of about 0.52 m/s^2
  (a kicked ball first skids and loses about 2/5 of its speed). It bounces: a 2 m drop rebounds about 0.8 m, and it
  comes off a post or a board at about 0.7 of its speed. A rolling ball that runs into a standing robot's legs mostly
  stops at its feet (its spin takes the rebound).
- The robots: Booster T1 lower bodies (legs and trunk, no arms), trunk about 0.68 m above the floor, head camera about
  1.0 m (it sees the floor from about 0.55 m ahead of the trunk on: a ball at your feet is out of view); held to the
  real T1's leg limits (motor torques 45 / 30 / 30 / 60 / 24 / 15 N m for hip pitch / roll / yaw, knee, ankle pitch /
  roll, a torque-speed envelope at the joint speed limits 12.5 / 10.9 / 10.9 / 11.7 / 18.8 / 12.4 rad/s, a rated
  (continuous) torque of 60 % of those torques: a motor held near its peak for more than about 5 s folds back to it
  (thermal), a 1 kW bus per robot); team A wears blue, team B red, bold white numbers 1 and 2 on the front and back;
  robots collide and contact can make a robot fall; a robot whose trunk drops below 0.40 m has fallen: it lies still and
  is stood up where it lies 3 s later.
- The physics: 2 ms physics steps, 20 ms control steps; the real T1's leg torques, torque-speed envelope, thermal
  foldback and bus cap; robot-robot, robot-ball, goal and board contacts.

## Others
- At a kick-off, before the ball is in play, only the kick-off team's robots may be in the centre circle, and no robot
  may be in its opponents' half; breaking this is a removal penalty.
- The boards keep the ball in: no kick-ins, goal kicks or corners; a ball resting at a board for 3 s is moved 1 m
  straight inwards while play goes on. A ball that leaves the pitch, or 30 s with nobody near the ball, gives a dropped
  ball: the ball on the centre mark, the robots placed in their halves. If the robots near the ball leave it unmoved for
  15 s, the nearest robot is removed.
- No free kicks and no cards: a foul only removes the offender. It stays off the pitch beside its own half for 15 s + 5
  s per counted team offence (pushing, ball holding), then re-enters on the touchline. Penalties end at half time.
- Removal fouls: pushing, ball holding and illegal defence. Pushing: an opponent falls, or is pushed back, because a
  robot moved into it faster, or the two stay in contact for more than 5 s; a robot kicking close to the ball is exempt.
  Ball holding: the ball is kept right at a standing robot's trunk for more than 5 s. Illegal defence: both robots of a
  team are inside their own penalty area for more than 5 s; the one farther from the ball is removed, and it is not
  counted as an offence.
- At every kick-off, restart, stand-up after a fall and return from a penalty the referee puts the robot in Booster's
  default stance (`game spec` -> joint_level.stance_on_placement) and holds its trunk for 1 s (`held_s` > 0; your rows
  already act); then it lets go.
- A robot whose trunk drops below 0.40 m has fallen: it goes limp, lies 3 s and is then stood up where it lies (and held
  1 s; no penalty).
- A goal, half time, full time (when level: the shoot-out), a dropped ball and every shoot-out kick freeze the world and
  the clock for the reviews.
- The other team (level 5) is learned: its two T1s walk on a policy trained with reinforcement learning on the same
  joint interface and limits as yours, and a learned strategy layer decides what each robot does.

## Limits
- Time: 14400 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning and graded on the state at that moment, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). The clocks the service reports are the game's own. A
  call into a long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 6 CPUs, 16 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (12 GiB of its memory); the simulator (`sim`) and `practice` run in containers of their own and do not count.
  Going over a cap can get a process killed (the CPU cap only slows you down). Usage: `/run/rcb-limits/usage.json`.
- Resets: none: one match.
