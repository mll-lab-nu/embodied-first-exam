# Robot soccer 2 v 2: joint level, coach format, CPU + GPU resource tier

You play robot soccer 2 v 2 in the **coach format** against **a learned opponent team at the joint level (level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint interface and limits as yours; a learned strategy layer decides what each robot does)**: you are seat `A` and command **both** robots of team A. Four simulated Booster T1 humanoids (lower bodies: legs and trunk, held to the real robot's joint and motor limits) and one ball on a boarded 10 x 7 m pitch, two halves of 5 minutes of game time, a penalty shoot-out when level, under the RoboCup Humanoid Soccer League rules (deviations below). Your container: 6 CPU cores, 16 GB **and one GPU** with a GPU training environment (below). The network reaches only your model's API and the package registries. This is RoboOlympics' joint-level soccer task (revision `soccer-2v2-11`), one frozen instance: a learned opponent team at the joint level (level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint interface and limits as yours; a learned strategy layer decides what each robot does), the world slowed S = 10 times; the seed is fixed and never shown. The match service is at `http://localhost:8000`, your practice service at `http://localhost:8100`.

## What this task measures
- **What you can make of the resources you have** (the CPU + GPU resource tier): this tier has a GPU, the full 2 v 2
  match world on the GPU and a reinforcement-learning library. **The method is yours**: train controllers, write
  them by hand, or combine both; nothing is required. A twin task plays the same match (the same opponent, seed and time)
  with CPUs only; we compare the two tiers. Report what you built and trained (for how long, on what) and what it gained in `/app/output/NOTES.md`.
- **Success = you win the match.** The score and the rest are recorded for the analysis.

## Timeline and limits (read this first)
| Phase | Wall time | What happens | If you miss it |
| --- | --- | --- | --- |
| Development | from the session start, at most **2 h** | build and test your team; the world waits | send `game start` within 2 h of the session start, else **your side loses** (no-show) |
| Match | about **100 min** of play | the world runs at 1/10 of real speed (a 20 ms control step = 200 ms of wall time); your program plays | a step without a new row keeps the row (or plan) in effect |
| Reviews | at most **5 min each**, typically 3-10 per match | at every stoppage (goal, half time, dropped ball, full time, each shoot-out kick) the world and the clock freeze until you send `game ready "WHY" "PLAN"`. The opponent does not review. You may use a review to improve your program (practice matches and training run on) and restart it | **your side loses the match at once** if a review is not ended within 5 min |
| Session end | **4 h** (14400 s) after the session start | you are stopped and the match is graded as it stands | **if your session ends before the match is over, you lose** |

**Each review has a time limit: send `game ready` within 300 s of real time after the world freezes (`timing.review_timeout_s` in `game spec`), or your side loses the match** (`ready_timeout`, a valid result, success 0, even when you are ahead). The world does not go on by itself after the limit: watch for the freeze (your program's log, `game status`) and review at once.
**Send `game start` within 7200 s of real time after the match service starts (`start.window_s` in `game spec`), or you lose the match** (`no_show`, a valid result, success 0). The match does not run before that: read `game spec` and prepare your program first.

So: up to 2 h of development, then about 100 min of play plus your reviews, all inside 4 h. If you
use the whole 2 h, about 20 min are left for all your reviews together (a match that ends early by the
mercy rule leaves more): start earlier if you want long reviews. Watch the clock (`date`): the session started when you
received this text (write the time down now).

## Recommended workflow
1. (10 min) Read this text, `game spec` (the joint level: joints, ranges, PD, motors) and `/opt/robot/README.md`.
2. Build balance and walking first: a T1 cannot stand by PD alone (with constant targets it tips over within about
   1.5 s). Develop in `practice.py` (your process: drills with free placement and pushes).
   (CPU + GPU tier) Train on the GPU in parallel: e.g. a walking / balance policy on `train/hum_mjlab.py` (one T1) or a
   whole team on `train2v2/soc_mjlab.py` (the full match world against the scripted levels or yourself) with rsl_rl;
   then check it in `practice.py` and in practice matches (the match's own CPU world) before you rely on it.
3. Add ball handling (approach, dribble or kick) and tactics for two robots; handle placements (`held_s` > 0 after
   every kick-off and stand-up), falls, penalties and stoppages.
4. Test your whole team in **practice matches** (`/opt/robot/scrimmage.py`): many seeds against L5 (the team you meet; one match is
   noise: RoboCup teams judge a change over many games against the same opponents), against the other levels to see your
   margin, and against an earlier version of your own team ("self"). Keep a baseline and only replace it with
   something that wins more often.
5. Make the match program robust: one thread per robot (an act returns at the next 20 ms boundary), retries on 409
   / 429, a log you can read, and no crash when a robot is fallen, penalized or held.
6. Write `/app/output/METHOD.md` (a record, below), then send `game start` before the 2 h limit (when your team wins its practice matches, or at the latest about
   10 minutes before the limit), keep your program running, and use the reviews to look at what happened, fix,
   re-test in practice matches and restart; end every review well inside its 5 min.

## The joint level (this task)
This task is the **Agent as Robotics Engineer** level of robot soccer: there is **no walking policy and no kick skill**.
Each of your robots takes **12 leg joint targets every 20 ms** (game time), and everything else (balance, walking,
turning, kicking, getting through contacts) is yours to build.

- **Actions** (per robot, `entity` = its number): `{"type": "joints", "q": [12 targets]}` for the next control step,
  `{"type": "traj", "k0": K, "q": [[12], ...]}` a plan of up to 50 rows from control step K (a new act replaces the
  rest of the plan; after the last row the robot holds it), `{"type": "hold"}`. Joint order: left hip pitch, roll,
  yaw, knee, ankle pitch, ankle roll, then the right leg (`game spec` -> joint_level.joints, with the ranges).
- **Execution** (exactly as the real T1's joint position mode): each row is limited (at most the URDF joint speed x
  20 ms from the previous row, inside the joint ranges; non-finite values keep the previous row), then PD every 2 ms
  with Booster's deployment gains (hip, knee 200; ankle 50 N m/rad; damping 5 / 1; fixed), then the motors: the URDF
  torques 45 / 30 / 30 / 60 / 24 / 15 N m, a torque-speed envelope (full torque up to 64 % of the joint speed limit),
  a rated (continuous) torque of 60 % with an I^2 t foldback (a motor held at its peak for more than about 5 s folds
  back to the rated torque; your state shows each motor's heat `motor_heat`, 1 = at its limit), a 1 kW bus per robot.
- **Placements**: at every kick-off, restart, stand-up after a fall and return from a penalty the referee puts the
  robot in Booster's default stance (`game spec` -> joint_level.stance_on_placement) and **holds its trunk for 1 s**
  (`held_s` > 0; your rows already act); then it lets go. A fallen robot (trunk below 0.40 m) goes limp, lies 3 s,
  then is stood up where it lies (and held 1 s). Falls cost time only; pushing, ball holding (5 s), illegal defence,
  game stuck and leaving the field are judged as in the rules.
- **Observation** (`game status`, `game observe`; your team's frame): per own robot its pose, velocity, IMU,
  joint_pos, joint_vel, trunk_quat (w x y z), gyro, accelerometer (trunk frame), trunk_pos_z, trunk_vel, the row in
  effect (`row`), `plan_rows_left`, `held_s`, `motor_heat`, `step` (the control step), fallen, penalized; and
  **`truth`**: the ball's position and velocity and every robot's pose (this task gives you the full state; the
  cameras are there too, but you do not need them).
- **Timing**: run your control loop in a program (`game status` + one act per robot per step, or short `traj` plans to
  ride over hiccups); a step you miss keeps the row (or plan) in effect. **An act returns when it takes effect, at the
  next control-step boundary**: one act per robot may be in flight, so send each robot's acts from its own thread (or
  use plans); at most 20 requests per second and 4 open requests from your seat to the match service.
- **Not allowed**: any walking or balancing policy you did not build in this session (in particular the released
  Booster / SaiResearch T1 walking policies); after the match the verifier compares your robots' rows with the released Booster walking policy: a team found driving its robots with it loses the match (success 0).

## Practice: your copy of the match world
- **CPU-parallel simulation** (`/opt/robot/pool.py`): run many practice.py drills or rollouts at once on your 6 cores (both modes have the same).
- **Practice matches** (`/opt/robot/scrimmage.py`, service http://localhost:8100 on its own 4 CPUs, up to 4 worlds at a
  time): the match itself (same world, physics, motors, referee, rules, placements, kick-offs and the same
  observation dict as `game status`), but the world advances only when you call `step()`, as fast as your program
  runs (a 10-minute match takes a few minutes), and stoppages are resumed at once (no reviews). Opponents: `"L5"` (the team you meet in the match), `"L1"`, `"L2"`, `"L3"` (scripted teams on the released walking policy), all black boxes (you see what they do, not
  their code), or `"self"`. With `"self"` you drive both teams (team B sees the world in its own frame, as in a duel): spar your new program against your previous one. Practice seeds never coincide with match seeds; vary them.
- **Drills** (`/opt/robot/practice.py`, in your own process): the match's physics without referee or opponents, robots
  and ball placed where you like, pushes; for standing, walking, turning and kicking.
- Practice is free: it does not count, the match service does not see it, and it runs during the reviews too.

## Your GPU and the training environments (CPU + GPU tier)
- **GPU**: one NVIDIA GPU (24 GB class; the speeds below were measured on an RTX 4090; keep your GPU memory
  under ~10 GB; speed in the humanoid penalty pilot on 2026-10-13: about 140 000 20-ms steps/s including PPO updates at 4096 envs with the GPU free, 2-4x less when it is shared; the full match world: about 45 000-60 000 control steps/s at 4096-8192 worlds).
- **Two Python environments**: `python3` (system: numpy, SciPy, MuJoCo 3.3.7 = the match's; your match program,
  practice.py, scrimmage.py and pool.py run here) and `/opt/train/bin/python` (**mjlab 1.6.0** on **MuJoCo Warp 3.11**
  with PyTorch 2.14 (CUDA) and **rsl_rl 5.4.2**, ETH's PPO). No other ML packages; no internet access besides the package registries.
- **The full 2 v 2 match world on the GPU** `/opt/robot/train2v2/soc_mjlab.py`: four T1s, the ball, the referee's rules,
  the match's limiter, PD and motors, the scripted team at levels 1-3 (compiled: a black box, as in practice) or
  self-play; thousands of matches in parallel. Differences from the CPU match world: float32, no penalty shoot-out (a
  draw stays a draw), single trajectories drift apart after impacts (statistics agree). Training may use privileged
  state; the match gives you its own observation (your robots' state and `truth`).
- **One T1 on the GPU** `/opt/robot/train/hum_mjlab.py`: a single robot with a ball, for skills (walking, kicking).
- `example_rsl_rl.py` in each directory shows the rsl_rl plumbing (placeholder rewards) and the export of the actor
  to numpy. No reward is given: design your own.
- What you train runs in your own control program during the match (the GPU stays available; numpy inference of a
  small network takes well under a millisecond).
- The released Booster walking policy (inside `train2v2/soccer/models`) only drives the scripted opponents: using it,
  or anything made from it, for your robots is not allowed (a lost match).

## METHOD.md (for the record)
Before `game start`, write `/app/output/METHOD.md` (form: `/opt/robot/METHOD_TEMPLATE.md`): the controller's
structure and the methods you used (hand-written control, planning, optimisation, learning, ...), what you tuned or
trained and how. It is only a record: any method is allowed and nothing in it can lose you the match. After the match
we label what each seat used from its programs, notes and logs.

## Your program
You play through a program that observes, computes your robots' rows and sends them, without a new model response for
each action. You stay in the loop: watch its log, stop, fix and restart it whenever needed. Only you send `game
start` and `game ready`.

- Use only the service's replies (your robots' state and the full-state `truth`), your toolkit and this document; no
  simulator internals of the match service.
- One act per robot in flight: an act sent before that robot's previous one has returned is refused (HTTP 429).
- Keep your scripts, logs and notes in `/app/output/` (and a short `/app/output/NOTES.md`: what you built, what you
  tested, how it did in practice matches).

## Interface
Use the `game` command, or the same calls as HTTP with JSON at `http://localhost:8000/<SEAT>/` (your seat is `$SEAT`):

| `game` command | HTTP | |
| --- | --- | --- |
| `game spec` | `GET /spec` | the actions (types, fields, ranges), the cameras with their intrinsics, the rule constants |
| `game status` | `GET /status` | the current state, no image |
| `game start` | `POST /start {}` | you are ready; the match begins when every seat has started |
| `game wait DT` | `POST /wait {"dt": DT}` | let DT game seconds pass (0 < DT <= 1) |
| `game observe` | `POST /observe {}` | the state and the camera images (one PNG of tiles: `observation.tiles`) |
| `game act JSON` | `POST /act JSON` | one action |
| `game ready "WHY" "PLAN"` | `POST /ready {"why":"...","plan":"..."}` | ends your review of a stoppage |

Errors: 400 = an invalid action (nothing happens), 409 = not now (not your turn, or a review is due), 429 = one
action in flight, or more than 20 requests per second or 4 open requests from your seat (empty body: retry more slowly).

## Rules
- robot soccer 2 v 2 under the RoboCup Humanoid Soccer League rules: four simulated Booster T1 humanoids (lower bodies: legs and trunk, held to the real robot's joint and motor limits) and one ball on a boarded 10 x 7 m pitch with two goals, two halves of 5 minutes of game time, a penalty shoot-out when level. At the joint level your robots take 12 leg joint targets every 20 ms (section "The joint level" above); the opponent's two robots are under joint control too: they walk and kick on a policy trained with reinforcement learning on the same joint interface, PD, motors and limits as yours; a learned strategy layer decides what each robot does.
- `frame`: metres, seconds; your team's frame: you attack the goal at x = +5 and defend the goal at x = -5, y to the left when facing +x, z up, yaw counter-clockwise from +x (both teams see the pitch this way in their own frame)
- `pitch`: field of play 10 x 7 m (|x| <= 5, |y| <= 3.5), halfway line x = 0, centre circle radius 1.0 m, penalty areas 2.0 m deep and 4.0 m wide, goal areas 1.0 x 3.0 m, penalty marks 1.5 m in front of each goal line; boards 0.3 m high on the touchlines and goal lines except the goal mouths; goals 2.6 m wide (|y| < 1.3), 1.8 m high, 0.6 m deep with nets
- `ball`: radius 0.11 m, 0.45 kg, orange, a thin shell; on the turf it rolls with a deceleration of about 0.52 m/s^2 (a kicked ball first skids and loses about 2/5 of its speed); it bounces: a 2 m drop rebounds about 0.8 m, it comes off a post or a board at about 0.7 of its speed; a rolling ball that runs into a standing robot's legs mostly stops at its feet (its spin takes the rebound)
- `robots`: Booster T1 lower bodies (legs and trunk, no arms), trunk about 0.68 m above the floor, head camera about 1.0 m (it sees the floor from about 0.55 m ahead of the trunk on: a ball at your feet is out of view); held to the real T1's leg limits (motor torques 45 / 30 / 30 / 60 / 24 / 15 N m for hip pitch / roll / yaw, knee, ankle pitch / roll, a torque-speed envelope at the joint speed limits 12.5 / 10.9 / 10.9 / 11.7 / 18.8 / 12.4 rad/s, a rated (continuous) torque of 60 % of those torques: a motor held near its peak for more than about 5 s folds back to it (thermal), a 1 kW bus per robot); team A wears blue, team B red, bold white numbers 1 and 2 on the front and back; robots collide and contact can make a robot fall; a robot whose trunk drops below 0.40 m has fallen: it lies still and is stood up where it lies 3 s later
- `match_format`: you (seat A) command both robots of team A against team B (a learned opponent team at the joint level (level 5: its two T1s walk on a policy trained with reinforcement learning on the same joint interface and limits as yours; a learned strategy layer decides what each robot does); the scripted levels 1-3 are described here for the practice service); every level kicks with the in-walk kick (style step) (level 1, a warm-up, reacts to the ball 0.6 s late, walks at most 0.45 m/s and lines up its kicks loosely; level 2 0.3 s, 0.65 m/s, tighter; level 3, a challenge level: both robots go for the ball, react at once, walk at most 0.8 m/s and line up most precisely, the strongest scripted team found in the screening); success = winning the match
- `duel_format`: seat A commands team A (robots A1, A2), seat B team B (B1, B2); FIRST_PLAYER's team kicks off first (and shoots first in a shoot-out); play both orders
- `overhead_formats`: match_overhead and duel_overhead are match and duel with an overhead view instead of the head cameras: two fixed cameras 6.0 m above the floor look straight down, one over each half (tiles overhead0 = your own half, overhead1 = the opponents' half, 600 x 800 each), each tile a map of its half in your team's frame (image right = your +x, image up = your +y; calibration in game spec camera.overhead); the images show the world 0.04 s ago (as RoboCup SSL's shared vision); no head cameras; your robots' own state and the referee's information as in the other formats; the same scripted levels as match
- `kickoff`: your frame: when you kick off, your robot 1 stands about (-0.32, 0.06) facing +x behind the ball on the centre mark (the ball in its swing zone) and robot 2 about (-2.5, -1.5); when the opponents kick off, about (-1.6, 0.4) and (-3.6, -0.8) (up to 0.3 m off, seeded); before the ball is in play only the kick-off team's robots may be in the centre circle and nobody in the opponents' half (else a removal penalty)
- `stoppages`: a goal, half time, full time (level: the shoot-out), a dropped ball (the ball left the pitch, or nobody near the ball for 30 s) and every shoot-out kick end a unit: the world freezes and every player sends game ready WHY PLAN
- Winner: more goals after two halves wins (or a 10-goal lead at any time, the mercy rule); if level, a penalty shoot-out of 3 kicks each (the team that kicked off first shoots first); if still level, up to 3 sudden-death rounds, each won by the better kick category (goal, saved, post, wide, other, no kick); then (last resort, not from the rulebook) a coin toss drawn from the seed. There are no draws.
- Deviation D1 (rulebook Law 1): pitch 10 x 7 m (HSL S-Field 9 x 6, M-Field 14 x 9); boards 0.3 m high on the touchlines and goal lines (open goal mouths), no border strip; goals 2.6 x 1.8 m, 0.6 m deep
- Deviation D2 (rulebook Law 3): 2 v 2, no designated goalkeeper, no substitutes; robot-to-robot communication: in the team and team_match formats the team channel (at most 512 bytes per message, one message per robot every 0.2 game seconds, 4000 per robot and match, teammates only; 4000, not 3000: 3000 is exactly a full regular time of 600 s at the 0.2 s rate, so a robot that talks at the full rate would be refused in the shoot-out after it); in the match and duel formats one player commands both robots (no channel needed)
- Deviation D4 (rulebook Law 7): 2 x 5 minutes of game time (HSL 2 x 10 min; 2 x 2.5 min up to soccer-2v2-4), a review at half time, no change of ends (each team's frame stays), no timeouts; the world and the clock freeze at every stoppage until the reviews; ball-stop extension at most 3 s; mercy rule (10 goals) kept
- Deviation D5 (rulebook Law 8): the referee places the robots for a kick-off (seeded positions, up to 0.3 m off the nominal spots); the ball is in play when it has moved 0.15 m or 10 s after play resumes; the kick-off team must touch the ball outside the centre circle before it can score (else no goal, the other team kicks off); dropped ball: ball on the centre mark, robots placed in their halves; game stuck: local 15 s (the nearest robot removed; 10 s up to soccer-2v2-3, longer now that a swing kick takes about 5 s), global 30 s (dropped ball), with a 0.3 m ball-movement threshold and 1 m proximity
- Deviation D6 (rulebook Laws 9, 13, 15-17): the boards keep the ball in: no kick-ins, goal kicks or corners; a ball resting at a board (within 0.3 m of a touchline, or of a goal line beside the goal, moved less than 0.3 m for 3 s) is moved 1 m straight inwards while play goes on; no free kicks (a foul only removes the offender); a ball that ever leaves the pitch restarts with a dropped ball
- Deviation D7 (rulebook Law 10): no draws: a level match goes straight to the penalty shoot-out
- Deviation D8 (rulebook Law 12 (pushing)): measurable pushing: an opponent falls within 0.5 s of contact while the offender moved towards it faster (> 0.15 m/s more); or an opponent pushed more than 0.6 m back during one contact (gaps up to 0.5 s) by a robot moving towards it faster; or contact over 5 s (the faster mover); a kicking robot within 1.3 m of the ball is exempt
- Deviation D9 (rulebook Law 12 (illegal position, defence)): added: both robots of a team inside their own penalty area (2 x 4 m, the goal included) for more than 5 s: the one farther from the ball is removed (not counted as an offence)
- Deviation D10 (rulebook Law 12 (ball holding, fallen robot, removal penalty)): ball holding = the ball's centre within 0.16 m of a standing robot's trunk centre for more than 5 s; a fallen robot (trunk below 0.40 m) lies still 3 s and is stood up where it lies (no penalty: the T1 lower body has no arms to get up with; at the joint level it goes limp while it lies); removal penalty 15 s + 5 s per counted team offence (pushing, ball holding), served off the pitch beside the robot's own half, re-entry on the touchline; penalties end at half time; no cards
- Deviation D11 (rulebook Law 14): shoot-out: 3 kicks each, then up to 3 sudden-death rounds ranked by the HSL kick categories (goal, saved, post, wide, other, no kick), then a seeded coin toss; each team shoots at the goal it attacks; strikers robot 1, 2, 1, the keeper the other team's robot with the same number; 20 s to touch the ball; the keeper stays within 0.6 m of its line until the touch (else a goal); the team that kicked off first shoots first
- Deviation D13 (rulebook Law 4 (players: robots)): the robots are Booster T1 lower bodies (legs and trunk): the real T1's two 4-joint arms are not modelled (no arm motion, no arm contact, no dive or get-up motion); the legs are held to the real T1's limits (Booster URDF torques and joint speeds; estimates of bodies/booster_t1/body.toml: a linear torque-speed envelope, a rated torque of 60 % of the URDF torque with an I^2 t foldback after about 5 s at the peak, a 1 kW bus per robot, a walking-command rate limit)
- Deviation D14 (rulebook Law 4 (players: robots), robot perception): each robot's own pose comes from the simulator (exact self-localization in the team frame); a real T1 localizes itself from its camera and odometry with errors of several centimetres to decimetres. This task also gives you the ball's and every robot's true state (`truth`)
- Deviation D15 (rulebook Law 1 (field surface: artificial turf 20-30 mm)): the turf is a ball model calibrated to the FIFA Quality Programme for Football Turf (soccer-2v2-8; up to -7 the ball rolled with 0.15 m/s^2 and hardly bounced): a constant rolling deceleration of 0.52 m/s^2 (the FIFA roll test, a ball leaving a 1 m ramp at about 3.2 m/s, rolls 9.8 m here: allowed 4-10 m; the low end of 0.51-1.28 m/s^2, nearest RoboCup practice), a 2 m drop rebounds 0.81 m (allowed 0.60-1.00 m), the ball a thin shell (a ball struck at its centre skids and rolls on at 3/5 of its speed); not measured on a real HSL field (30 mm turf); a constant deceleration instead of one that grows with speed; the robots' feet meet the turf with a near-rigid contact (soccer-2v2-11; up to -10 a soft contact let a loaded foot creep inside its friction cone): friction coefficient 1.0 (studs on artificial turf about 0.8-1.3), no sliding below the friction limit, about 0.1 mm of sinking (a real turf yields a few millimetres under a foot; not modelled)

## Geometry and physics
Everything you need is in `game spec`: the frame, the pitch, the ball, the joint level (joints, ranges, row limits, PD,
motors, stance), the rule constants. The physics engine is MuJoCo 3.3.7 (2 ms physics steps, 20 ms control steps;
four Booster T1 lower bodies with the real T1's leg torques, torque-speed envelope, thermal foldback and bus cap; your
robots under joint control, the opponent's robots too (a walking policy learned at the joint level); a ball calibrated to
FIFA turf; robot-robot, robot-ball, goal and board contacts).

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only (the simulator in the `sim` service is the benchmark's and does not count): at most **12 GiB of GPU memory**, **13 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`. GPU memory counts what a process reserves (JAX, for example, reserves most of the card unless told not to). These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. When enforcement is on and GPU memory goes above 1.5 times its limit, the monitor also kills the process holding the most of it at once, to protect the machine; that alone does not fail the trial. CPU is capped at 6 cores for your container; the cap only slows you down.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and graded on what stands at that moment, as the sections above say. The service does not count this limit for you: the clocks it reports are the game's own. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
