# Table tennis (G1) · Fixed opponent · Engineer track

## 1. Goal
You control a legged humanoid (Unitree G1, 29 DOF) in a Table tennis (G1) match from seat `A`. Your opponent is a scripted player built into the world (one of the levels L1-L4, set for each match; `game spec` names it).
Your goal is to win by developing, operating and continuously improving your robot's control within the rules.
You are encouraged to study your opponent: observe how it plays, find its patterns and weaknesses, anticipate what it will do, and adapt your tactics to gain an advantage.

## 2. Rules & Scoring
`game rules` is the authority: the complete rules of this match and every deviation from the ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2). Read it before you plan your approach; this chapter does not replace it.
- How a match is won: The winner: a player's third undue-delay fault loses it the match; else the first player to 5 points with a lead of 2, or the first to 7, wins the game (the match); a let scores no point (at most 2 service lets in a row); if 16 points (lets included) are played, the player ahead wins and at a level score the player who won the last point (last resort, not from the rulebook); there are no draws.
- This match belongs to no competition: its result stands on its own, and `game rules` holds the match rules only.

## 3. Match Setup & Procedure
### This match
- This is a single match outside any competition.
- The platform runs your opponent under your timing and information: its commands take effect at the next control step after the world state they answer, as yours do, and it sees the world only through what your seat gets, camera images two control steps late as yours. Declared exceptions, which concern information only (`game spec` names those of your level): L3: level 3 reads the ball's true position and velocity as your cameras would show them (6 control steps old, with an error of 0.6 cm and 5 cm/s per axis) and the ball's true spin, which no camera shows, and rolls them out in the venue's own ball model; its commands still take effect at the next control step after they are decided, as yours after they arrive, and it never reads your robot's commands; L4: the BOSS (level 4) reads the ball's true position, velocity and spin at its decision step instead of your cameras' frames (no camera latency, no measurement error) and rolls them out in the venue's own ball model; its commands still take effect at the next control step after they are decided, as yours after they arrive, and it never reads your robot's commands.
- `game spec` gives this match's details (your side and your robots, the opponent's level).

### Timing
- Duration: after preparation, the match takes up to 90 minutes of real time.
- Speed: during play the world runs at 1/1 of real speed (one second of game time takes 1 s of real time) and never waits for your computation; it stands still during preparation and in review windows.
- Safety cap: a wall-clock cap of 2 h 4 min counts from the start of preparation over the whole match (preparation, play and reviews). It only stops a match that hangs: reaching it voids the match with no result for either side. It never decides the winner and is no extra time.
- `game status` shows the current phase and the time left in it.

### Preparation
- You have 30 minutes before the match starts; the official match world waits. Develop, train and test your programs.
- Send `game start` when you are ready; the match begins when you start. If you have not started when preparation ends, you lose (no-show).
- Preparation time you do not use is not given back: your robot plays from the start with whatever you have deployed then.

### Live match
- The world runs continuously: your robot does what your programs (or you) command, and nothing waits for you.
- You may keep developing, training and testing during play and deploy improved programs at any time.
- Watch your opponent throughout the match: its recurring patterns, strengths and weaknesses, and how its play changes. Use what you see to anticipate it and adapt your tactics; how you model it is up to you.

### Reviews
- After every point the world freezes for up to 300 s.
- Use the window to look back: why the point went as it did, what worked and what failed, what your opponent did, and what you will change. You may inspect logs, train, test and redeploy programs during the window.
- Write the review yourself with `game ready "WHY" "PLAN"` (WHY: why the point went as it did; PLAN: what you will change; up to 2000 characters each). A review sent by a program is refused, and a review you do not send is recorded as missed; neither changes the score.
- The world resumes when you have sent it, or at the deadline.

### End
- The match ends when its rules end it (chapter 2); every match has a finite end. You may resign with `game resign` (you lose).
- The result is recorded automatically. When the match has ended, `game status` gives one short post-match step; it never changes your result.

### Continuity
- This match starts from a clean seat: nothing carries over into it from earlier matches, and nothing carries out of it.

## 4. Robot & Interface
### Robot and control
- You control one robot, a legged humanoid (Unitree G1, 29 DOF) with 29 actuated joints (arms 2 × 7, waist 3, legs 2 × 6). Your robot is held to the real robot's limits (`game spec` lists them).
- You are the Engineer: the match takes no skill commands. You drive your robot with actuator-level (joint-level) commands: `joints` and `toss` (`game spec` gives each command's fields, units and the joint order). How you prepare and what you build is up to you.
- Send commands with `game act`.

### Observations
- What you see: two cameras (`behind`, `side`), 480×360; your robot's own state; the referee's information (the fields: `game spec`). Each image is stamped with its physics step.
- `game status` returns your robot's state at once, without images; `game observe` adds the camera images.
- Camera latency: every camera takes a frame at every control step; an `observe` call returns at once the frame taken two control steps (20 ms of game time) before, one frame per call (the newest you can have; at the start of play and after each placement the first image comes two steps later): an image shows the world as it was, so use its step stamp to account for the delay.

### Control timing and latency
- Control step: 10 ms of game time (0.01 s of real time).
- Commands: an accepted command takes effect at the next control step after it reaches the match server; one command in flight per robot. The reply to `game act` comes once the command has taken effect, up to one control step (0.01 s of real time) after it arrives.
- Actuator latency: this robot adds no actuator delay after a command takes effect.
- The world keeps moving while your program computes and communicates, so that time adds to how late your robot responds. A command taking effect does not mean the motion is done: the robot's motors and dynamics decide that.
- High-frequency control: each `game` command starts a new process: one call takes about 15 ms of real time, and a shell loop of `game` calls reaches about 70 calls per second. Commanding at the control-step rate (a control step lasts 0.01 s of real time) takes a long-running program that uses the client library `ro_client` (its documentation: `python3 -m pydoc ro_client`); the match accepts one command in flight per robot.
- Exact command formats, observation fields, coordinate frames, limits and timing: `game spec`.

## 5. Resources & Practice
### Practice
- A complete copy of this world runs in your seat at `/opt/practice` (same physics, robot, referee and action interface as the match; resettable; ground truth available; practice opponents: none (no opponent plays) or the practice player (a program of the platform's, not the official opponent; in the practice service `game practice` only, which names its opponent id)). Read `/opt/practice/README.md`. It is available before, during and after play.
- Practice results never count, and the official opponent's code, state and settings are not available in practice.

### Development tools
- Provided toolkit: the joint interface; robot models; a simulator of your robot with the match's execution chain; actuator and motor models; a GPU training kit; other libraries and data. The full list is in `/opt/ro/toolkit.toml`.
- Your robot's model: `/opt/ro/g1_robot_only.xml`.

### GPU training kit
- `/opt/train/bin/python` runs PyTorch 2.14.1+cu130, NVIDIA Warp 1.17.0+cu12, MuJoCo Warp 3.11.0 on MuJoCo 3.11.0, mjlab 1.6.0 and rsl_rl 5.4.2 (every pinned package: `/opt/train/requirements.txt`). The system `python3` runs the match's MuJoCo 3.3.7 and has no CUDA. The kit is optional: train or build however you like.
- Import `torch` and `torch._dynamo` before `warp`, `mujoco_warp` or `mjlab`; another order can end the process with a segmentation fault. The kit's modules (`bodies.gpu.*` in `/opt/robot/lib`) import in this order.
- The official GPU twin (`bodies.gpu.twin`): `GpuTwin("/opt/ro/g1_tt_twin.xml", "/opt/ro/g1_tt_chain.json", num_envs=4096)` (your G1 with its paddle) runs thousands of copies of the match robot on the GPU and executes your rows as the match does (the chain file: row limiter, action latency, PD, motor curves, limits). `bodies.gpu.rl` wraps it for rsl_rl (a PPO example); `bodies.gpu.mjlab_compat` gives mjlab the same robot and chain. The twin holds your robot and what its model file adds, nothing else of the match world; check what you train in practice, which runs the match's own simulator.
- The parity test (`bodies.gpu.parity`) compares a twin with the match's own CPU execution of the same robot: open loop, the joints within 0.05 rad and the root within 0.01 m for 2 s; root held in the air, the joints within 0.002 rad for 4 s; closed loop, the joints within 0.05 rad and the root within 0.01 m for 1 s. After impacts single trajectories drift apart; their statistics agree.
- `/opt/robot/lib/bodies/gpu/README.md` explains the kit: a quick start, a PPO run and the known gaps.
- The twin's rows command all 29 joints (Unitree's order) through the robot library's open-control arbiter as the match's `joints` act does: one row per 10 ms held over the 1 ms physics steps, saturated at the joint ranges and speed limits, your kp / kd clipped at the simulator's stability bound (without them the platform's gains: the legs the walking deployment's, the waist and arms Unitree's), no feed-forward, Unitree's torque-speed curves and URDF torques, the PD on the joint sensors' noisy reading, no action delay. FALCON (the optional walker of the legs) is not in the twin.
- The ball is not in the twin: in the match it is this sport's own physics in the simulator (the flight with drag and spin, the table and net bounces, the blade impact), as is the referee. Add a ball model to your GPU training yourself if you need one; the twin gives the blade's pose (site `hand_center`).
- Parity with the match's MuJoCo 3.3.7 (sports/tabletennis_g1/tests/test_gpu_kit.py; the CPU chain steps the open-control arbiter bit for bit): the pelvis held in the air, tracking rows, the joints within 1e-3 rad up to the first self-contact (0.5 s; 4e-7 rad without the sensors' noise, which each side draws on its own: the same law, not the same numbers); on the floor, tracking, within 0.007 rad and 0.8 mm (0.47 s); open loop, falling, within 0.046 rad and 8 mm over the first 2 s (the kit's tolerance: 0.05 rad). After contacts single trajectories drift apart; statistics agree.

### Compute and workspace
- Your seat has 8 vCPUs (hardware threads), 16 GB of memory and one GPU, shared by everything you run (your tools, programs, training and practice).
- Your GPU is half an NVIDIA RTX PRO 6000 Blackwell: one MIG 2g.48gb+gfx instance with 48 GB of GPU memory, about 1.1 × an RTX 4090.
- Make full use of your resources, including your GPU, during preparation and whenever you train.
- There is no internet: everything you need is installed.
- Keep your programs, trained models, logs and notes in `/app/output/`.

## 6. Program Operation
### Running programs
- You may act yourself or run programs that observe and command your robot continuously. `game program start "YOUR_COMMAND"` starts a program in a session of its own (output in `/app/output/program.log`): it keeps running while you think, inspect, develop or do other work, and after your session ends.
- By hand, the same start is `setsid nohup YOUR_COMMAND > /app/output/program.log 2>&1 < /dev/null &`. A process your session still holds (a command it is still running, or one put in the background with `&` alone) can end with it.

### Monitoring and updating
- `game program status` shows what runs; `game program restart "NEW_COMMAND"` replaces a program: it stops the running program's process group, never your own shell, and starts the new one the same way; `game program stop` stops it; `--name` keeps several programs apart.
- Editing a file does not change a running program: restart it to deploy the change.
- Do not stop programs with `pkill -f` or `killall`: the pattern can match your own shell and end your session.

### Session and program lifetime
- Stay in your session until full time: only you can write a review (a review sent by a program is refused), and a review you do not send is recorded as missed. If your session ends before full time, the platform wakes it at each review window and once at full time, with a short summary of the match since then.
- Your seat and the programs you started in sessions of their own stay in the match either way.

### Deployment records
- The platform saves each program you deploy (its files, weights and command line) and may rerun it offline for diagnostics; that never changes your result, and you need not package anything during the match.

## 7. Restrictions
You are free to develop, train, experiment and adapt inside your seat. Not allowed:
- Reaching anything outside your seat other than the seat protocol (`game`) and the model gateway.
- Reading the match world's internals or hidden state, other seats' environments, programs or files, or an opponent's hidden settings, other than through `game` (ground truth in your practice worlds is yours to use).
- Interfering with the match service, the referee, the scoring, the clock, other seats or the platform.
- Having a program write or send your reviews.
`game rules` lists the sport's fouls and penalties.

## 8. References
- Rules and configuration: `game spec` (match configuration, robots, interfaces, timing, limits, this match's details) · `game rules` (the complete rules)
- Operation: `game start` · `game status` · `game observe` · `game act` · `game wait` · `game ready` · `game resign` · `game program`
- Development: `/opt/practice/README.md` · `game practice` · `/opt/ro/toolkit.toml` · `/opt/ro/g1_robot_only.xml` · `/opt/robot/lib/bodies/gpu/README.md`
Before you develop or deploy your programs, read `game spec` and `game rules`.
