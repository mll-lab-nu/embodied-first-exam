# Embodied Olympics · table tennis on Unitree G1s (GPU tier), match against level 4 (standard)

## Task
Win a game of table tennis to 5 points against the other robot.

## Goal
Success: you win the match.

The match is graded when it is over; your session must last until then: when your session ends, a match that has not
started is a no-show and a match in play is lost. When the match is over its result is final and your session is ended a
few seconds later.

Keep your programs, trained models, logs and notes in `/app/output/`.

Rules:
- **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
  benchmark's demonstrations, trained policies); trials are reviewed.
- One match, no reset: a point lost stays lost.
- Use only what `game` gives your seat (the camera images, your robot's state, the referee's information) and this text:
  no match-world internals, other seats' files or the opponent's hidden settings (ground truth in your practice worlds
  is yours to use).
- Preparation: you have 30 minutes before the match starts, counted from your seat's first `game` request; the match
  world waits. Send `game start` when you are ready; if you have not started when preparation ends, you lose (no-show).
  Preparation time you do not use is not given back.
- Reviews: after every point the world freezes for up to 300 s; send `game ready "WHY" "PLAN"` (why the point went as it
  did, what you will change; up to 2000 characters each). A review you do not send is recorded as missed (it does not
  change the score); the world resumes when you have sent it, or at the deadline. You may inspect logs, train, test and
  redeploy programs during the window.
- Reach nothing outside your seat but the seat protocol (`game`, the match service at localhost:8000), the practice
  service (localhost:8100) and your model's API; do not interfere with the match service, the referee, the scoring, the
  clock, other seats or the platform. `game resign` resigns (you lose).

The match (ITTF Laws, with these changes; `game rules` has the complete rules and every deviation: read it before you
plan):
- One game: the first player to 5 points with a lead of 2, or the first to 7, wins.
- A player's third undue-delay fault loses it the match.
- A let scores no point (at most 2 service lets in a row).
- If 16 points (lets included) are played, the player ahead wins, at a level score the player who won the last point.
  There are no draws.
- The serve uses the ITTF service laws with a toss device (`toss`); `game rules` lists the sport's fouls and penalties.

## Robot Interface
Table tennis between two Unitree G1 humanoids (29 actuated joints each: arms 2 × 7, waist 3, legs 2 × 6; held to the
real robot's limits), each holding a racket. You control seat `A`'s G1 at the joint level, with no skill commands,
against a G1 the platform drives at level 4 of four (the BOSS). The world waits for you: it advances only while you let
it (`### Time` below). The robot runs as a service you reach only through its client, as if it were real hardware: one
live episode.

### Client
The `game` command (the seat protocol; `game spec` gives the exact command formats, observation fields, frames, limits
and timing; `game rules` the complete rules):
- `game spec` · `game rules` · `game status` (your robot's state at once, without images; the current phase and the time
  left in it) · `game observe` (adds the camera images) · `game start` · `game act` · `game wait DT` ·
  `game ready "WHY" "PLAN"` · `game resign` · `game program` (`### Programs`) · `game practice` (the practice service).
- One call takes about 15 ms of real time (each `game` command starts a new process), and a shell loop of `game` calls
  reaches about 70 calls per second. Commanding at the control-step rate takes a long-running program that uses the
  client library `ro_client` (its documentation: `python3 -m pydoc ro_client`); the match accepts one command in flight
  per robot.

### Actions
- You drive your robot with actuator-level (joint-level) commands, `joints` and `toss`, sent with `game act`
  (`game spec` gives each command's fields, units and the joint order). Your robot is held to the real robot's limits
  (`game spec` lists them).
- An accepted command takes effect at the next control step after it reaches the match server; one command in flight per
  robot. The reply to `game act` comes once the command has taken effect, up to one control step after it arrives. This
  robot adds no actuator delay after a command takes effect; a command taking effect does not mean the motion is done:
  the robot's motors and dynamics decide that.

### Observations
- Two cameras (`behind`, `side`), 480 × 360; your robot's own state; the referee's information (the fields:
  `game spec`). Each image is stamped with its physics step.
- Camera latency: every camera takes a frame at every control step; an `observe` call returns at once the frame taken
  two control steps (20 ms of game time) before, one frame per call (at the start of play and after each placement the
  first image comes two steps later): use its step stamp to account for the delay.

### Time
- Control step: 10 ms of game time.
- Speed: standard mode, lockstep: the world advances only while you let it, during an open `game wait DT` (at most DT
  game seconds, then it stops again) and, for a command you sent, up to the control step at which it takes effect (the
  step after the state it answers). Between your calls it stands still: your thinking, your program's computation and
  your observations take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on;
  a match you leave standing never ends, and it is lost when your session ends. The platform's opponent is held to the
  same rule. `game spec` says so (`timing.clock` = `lockstep`).
- The world stands still during preparation and in review windows, whose limits are real time. After preparation the
  match takes up to 90 minutes of real time.

### Programs
- `game program start "YOUR_COMMAND"` starts a program in a session of its own (output in `/app/output/program.log`): it
  keeps running while you think, inspect, develop or do other work, and after your session ends. By hand the same start
  is `setsid nohup YOUR_COMMAND > /app/output/program.log 2>&1 < /dev/null &`; a process your session still holds (a
  command it is still running, or one put in the background with `&` alone) can end with it.
- `game program status` shows what runs; `game program restart "NEW_COMMAND"` replaces a program (it stops the running
  program's process group, never your own shell, and starts the new one the same way); `game program stop` stops it;
  `--name` keeps several programs apart. Editing a file does not change a running program: restart it to deploy the
  change.
- Do not stop programs with `pkill -f` or `killall`: the pattern can match your own shell and end your session.
- The platform saves each program you deploy (its files, weights and command line); you need not package anything during
  the match.

### Practice and toolkit
- A complete copy of this world runs in your seat at `/opt/practice` (the same physics, robot, referee and action
  interface as the match; resettable; ground truth available; opponents: none, or the practice player, a program of the
  platform's that is not the official opponent, in the practice service `game practice` only). Read
  `/opt/practice/README.md`. It is available before, during and after play; practice results never count, and the
  official opponent's code, state and settings are not in it.
- The toolkit: the joint interface, robot models (your robot's: `/opt/ro/g1_robot_only.xml`), a simulator of your robot
  with the match's execution chain, actuator and motor models, a GPU training kit and other libraries and data; the full
  list is in `/opt/ro/toolkit.toml`.
- The training kit: `/opt/train/bin/python` runs PyTorch, NVIDIA Warp, MuJoCo Warp, mjlab and rsl_rl (the pinned
  packages: `/opt/train/requirements.txt`); the system `python3` runs the match's MuJoCo and has no CUDA. The kit is
  optional. Import `torch` and `torch._dynamo` before `warp`, `mujoco_warp` or `mjlab`; another order can end the
  process with a segmentation fault (the kit's modules, `bodies.gpu.*` in `/opt/robot/lib`, import in this order).
  `/opt/robot/lib/bodies/gpu/README.md` explains the kit: a quick start, a PPO run and the known gaps.
- The GPU twin (`bodies.gpu.twin`): `GpuTwin("/opt/ro/g1_tt_twin.xml", "/opt/ro/g1_tt_chain.json", num_envs=4096)` runs
  thousands of copies of your G1 with its paddle on the GPU and executes your rows as the match does (the chain file:
  row limiter, action latency, PD, motor curves, limits); `bodies.gpu.rl` wraps it for rsl_rl (a PPO example),
  `bodies.gpu.mjlab_compat` gives mjlab the same robot and chain, and `bodies.gpu.parity` compares a twin with the
  match's own CPU execution. The twin holds your robot and what its model file adds, nothing else of the match world:
  the ball (its flight with drag and spin, the bounces, the blade impact) and the referee are not in it (the twin gives
  the blade's pose, site `hand_center`); check what you train in practice, which runs the match's own simulator. After
  impacts single trajectories drift apart; their statistics agree.
- The twin's rows command all 29 joints (Unitree's order) as the match's `joints` act does: one row per 10 ms held over
  the 1 ms physics steps, saturated at the joint ranges and speed limits, your kp / kd clipped at the simulator's
  stability bound (without them the platform's gains), no feed-forward, Unitree's torque-speed curves and URDF torques,
  the PD on the joint sensors' noisy reading, no action delay; the optional leg walker is not in the twin.

### Container
- A wall-clock cap of 2 h 4 min from the start of preparation only stops a match that hangs (no result for either side);
  it never decides the winner and is no extra time.
- Your container's CPUs, memory and GPU are shared by everything you run (your tools, programs, training and practice):
  make full use of them during preparation and whenever you train. Everything you need is installed. This match starts
  from a clean seat: nothing carries over into it, and nothing carries out of it.

## Others
- The BOSS (level 4) reads the ball's true position, velocity and spin at its decision step (no camera latency, no
  measurement error) and rolls them out in the venue's own ball model; it never reads your robot's commands. Its
  commands take effect at the next control step after the world state they answer, as yours do.

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including waiting for the service.
  At the end you are stopped without warning and graded on the state at that moment, as Goal says. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). The clocks the service reports are the game's own. A
  call into a long-running process can block for its whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 16 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (20 GiB of its memory); the simulator (`sim`) and `practice` and `practice_player` run in containers of their
  own and do not count. Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: none: one match.
