# Embodied Olympics · robot soccer 2 v 2 at the joint level (CPU + GPU tier), match against level 5 (standard)

## Task
Robot soccer 2 v 2 at the joint level: four simulated Booster T1 humanoids (lower bodies: legs and trunk, held to the
real robot's joint and motor limits) and one ball on a boarded 10 × 7 m pitch. There is no walking policy and no kick
skill: each of your robots takes 12 leg joint targets every 20 ms of game time, and balance, walking, turning, kicking
and getting through contacts are yours to build. You are seat `A` and command both robots of team A against a learned
team at the joint level, level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint
interface and limits as yours, and a learned strategy layer decides what each robot does. This is the CPU + GPU tier:
one GPU with a GPU training environment (Robot Interface, `### GPU training`); train controllers, write them by hand, or
combine both. The world waits for you: it advances only while you let it (Robot Interface, `### Time`). The robot runs as a service you reach only through its client, as if it were real hardware.

## Goal
Success: your team wins the match.

The match is graded when your session ends: stay until it is over. If your session ends before the match is over, or you
never sent `game start`, you lose.

Nothing to hand in: the service records and grades the episode. Keep your scripts, logs and notes in `/app/output/`,
with a short `/app/output/NOTES.md`: what you built, what you trained (for how long, on what) and what it gained.

Real-robot rules:
- Resets: as many as your time allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`); only the last episode is graded.
- No privileged match internals: use only the service's replies (your robots' state and the full-state `truth`), your
  toolkit and this text.
- Write your own controller: no walking or balancing policy you did not build in this session (in particular not the
  released Booster or SaiResearch T1 walking policies, nor anything made from them); a team found driving its robots
  with one loses the match.
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
- Two halves of 5 minutes of game time, 2 v 2 with no designated goalkeeper and no substitutes; no change of ends (each
  team's frame stays), no timeouts. More goals after two halves wins, or a 10-goal lead at any time (the mercy rule).
  Level after two halves: a penalty shoot-out of 3 kicks each (the team that kicked off first shoots first; strikers
  robot 1, 2, 1, the keeper the other team's robot with the same number; each team shoots at the goal it attacks; 20 s
  to touch the ball; the keeper stays within 0.6 m of its goal line until the touch, else a goal), then up to 3
  sudden-death rounds, each won by the better kick category (goal, saved, post, wide, other, no kick), then a coin toss
  drawn from the seed. There are no draws.
- Kick-off: your frame: when you kick off, your robot 1 stands about (-0.32, 0.06) facing +x behind the ball on the
  centre mark (the ball in its swing zone) and robot 2 about (-2.5, -1.5); when the opponents kick off, about (-1.6,
  0.4) and (-3.6, -0.8) (up to 0.3 m off, seeded); before the ball is in play only the kick-off team's robots may be in
  the centre circle and nobody in the opponents' half (else a removal penalty). The ball is in play when it has moved
  0.15 m or 10 s after play resumes; the kick-off team must touch the ball outside the centre circle before it can score
  (else no goal, and the other team kicks off).
- The boards keep the ball in: no kick-ins, goal kicks or corners; a ball resting at a board for 3 s is moved 1 m
  straight inwards while play goes on. A ball that leaves the pitch, or 30 s with nobody near the ball, restarts with a
  dropped ball: the ball on the centre mark, the robots placed in their halves. A ball that the robots near it leave
  unmoved for 15 s gets the nearest robot removed (game stuck).
- No free kicks: a foul only removes the offender. Removal penalties: pushing (an opponent falls, or is pushed back,
  because a robot moved into it faster; or contact for more than 5 s; a robot kicking close to the ball is exempt), ball
  holding (the ball kept right at a standing robot's trunk for more than 5 s), illegal defence (both robots of a team
  inside their own penalty area for more than 5 s: the one farther from the ball; not counted as an offence) and, before
  the ball is in play at a kick-off, a robot in the centre circle that is not of the kick-off team or any robot in the
  opponents' half. A removal lasts 15 s + 5 s per counted team offence (pushing, ball holding), served off the pitch
  beside the robot's own half, with re-entry on the touchline; penalties end at half time; no cards.
- Placements: at every kick-off, restart, stand-up after a fall and return from a penalty the referee puts the robot in
  Booster's default stance (`game spec` -> joint_level.stance_on_placement) and holds its trunk for 1 s (`held_s` > 0;
  your rows already act); then it lets go.
- A robot whose trunk drops below 0.40 m has fallen: it goes limp, lies 3 s and is then stood up where it lies (and held
  1 s; no penalty).
- A goal, half time, full time (when level: the shoot-out), a dropped ball and every shoot-out kick end a unit: the
  world and the clock freeze for the reviews.

## Robot Interface
### Client
The `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the joint level (joints, ranges, row limits, PD, motors, stance), the frame, the pitch, the ball, the rule constants, the timing |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | any action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why": "...", "plan": "..."}` | your review when the world freezes |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one action
in flight (sent before the previous one returned), or more than 20 requests per second or 4 open requests from your seat
(empty body: retry more slowly).

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
The world waits for you: it advances only during an open `game wait DT` (at most DT game seconds, then it stops again)
and, for an action you sent, up to the control step at which it takes effect (the step after the state it answers).
Between your calls it stands still: your thinking, your program's computation and the service's planning of an action
take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on; a match you leave
standing never ends, and it is lost when your session ends. `game spec` says so (`timing.clock` = `lockstep`). At the
end of every unit (a goal or another stoppage; `game spec`) the world freezes for the reviews; the reviews' time limit
and the start window are real time. Run your control loop in a program (`game status` + one act per robot per step, or
short `traj` plans to ride over hiccups); a step you miss keeps the row (or plan) in effect. An act returns when it
takes effect, at the next control-step boundary: one act per robot may be in flight, so send each robot's acts from its
own thread (or use plans); at most 20 requests per second and 4 open requests from your seat to the match service.

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

### This run: unlimited resets, save and load
This run lets you restart the match and go back to a saved moment.

- `POST http://localhost:8000/$SEAT/reset` with `{}`: the match from its start again (the same instance: the world, the
  opponent, the score and the clocks), as a new episode. You have 1000 resets (`budget.reset` in `/spec`).
- `POST http://localhost:8000/$SEAT/save_state` with `{}` answers `{"handle": "s1", "step": ...}`: the whole match now
  (the world, the opponent with its own internal state, the random generators, the score, the game clock) kept in the
  service; the handle is all you get. `POST http://localhost:8000/$SEAT/load_state` with `{"handle": "s1"}` goes back to
  it exactly, as a new episode. At most 32 handles are kept (the least recently used is dropped). Saves and loads do not
  use up resets.
- After a reset or a load the world is frozen until you send `game start` (or `game ready`), at most
  `timing.review_timeout_s` of real time; then it advances again, only while you let it (`game wait`, your acts), as
  before. The task's time limit keeps running.
- A match you lose by its rules (the opponent wins it, a missed review, the clock) is held at its end: `/status` shows
  phase `over`, and you may still reset or load. A match you win ends the run: no reset, save or load after it.
- Only the last episode is graded, with the task's rules: from the start, or for a loaded episode the play that led to
  the saved moment followed by what came after the load. If your session ends during a match, that match is abandoned
  (success 0); a held loss stays a loss. `final.json` records `resets`, `saves`, `loads` and `episodes`.

## Others
- A workflow that works: (1) Read this text, `game spec` (the joint level: joints, ranges, PD, motors) and
  `/opt/robot/README.md`. (2) Build balance and walking first: a T1 cannot stand by PD alone (with constant targets it
  tips over within about 1.5 s). Develop in `practice.py` (your process: drills with free placement and pushes). Train
  on the GPU in parallel: e.g. a walking / balance policy on `train/hum_mjlab.py` (one T1) or a whole team on
  `train2v2/soc_mjlab.py` (the full match world against the scripted levels or yourself) with rsl_rl; then check it in
  `practice.py` and in practice matches (the match's own CPU world) before you rely on it. (3) Add ball handling
  (approach, dribble or kick) and tactics for two robots; handle placements (`held_s` > 0 after every kick-off and
  stand-up), falls, penalties and stoppages. (4) Test your whole team in practice matches (`/opt/robot/scrimmage.py`):
  many seeds against L5 (the team you meet; one match is noise: RoboCup teams judge a change over many games against the
  same opponents), against the other levels to see your margin, and against an earlier version of your own team
  ("self"). Keep a baseline and only replace it with something that wins more often. (5) Make the match program robust:
  one thread per robot (an act returns at the next 20 ms boundary), retries on 409 / 429, a log you can read, and no
  crash when a robot is fallen, penalized or held. (6) Write `/app/output/METHOD.md` (Goal), then send `game start`
  before the 2 h limit (when your team wins its practice matches, or at the latest about 10 minutes before the limit),
  keep your program running, and use the reviews to look at what happened, fix, re-test in practice matches and restart;
  end every review well inside its 5 min.
- The practice service's other teams: `"L1"`-`"L3"` are scripted teams on the released walking policy (every level kicks
  with the in-walk kick; level 1 reacts 0.6 s late and walks at most 0.45 m/s, level 2 0.3 s and 0.65 m/s, level 3 at
  once and 0.8 m/s).
- The ball: radius 0.11 m, 0.45 kg, orange, a thin shell; on the turf it rolls with a deceleration of about 0.52 m/s^2
  (a kicked ball first skids and loses about 2/5 of its speed); it bounces: a 2 m drop rebounds about 0.8 m, it comes
  off a post or a board at about 0.7 of its speed; a rolling ball that runs into a standing robot's legs mostly stops at
  its feet (its spin takes the rebound).
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
- Resources: 6 CPUs, 16 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (12 GiB of its memory); the simulator (`sim`) and `practice` run in containers of their own and do not count.
  Over a cap a process can be killed (the CPU cap only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: as many as this run allows, with save and load (Robot Interface,
  `### This run: unlimited resets, save and load`).
