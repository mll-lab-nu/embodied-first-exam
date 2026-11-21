# Table tennis (G1) · Fixed opponent · Engineer track

**Standard mode: the world waits for you.** Wherever this document speaks of the world running in real time ("never waits", computation that costs game time, wall seconds per control step), it describes this task's standard-realtime twin; here the Timing section's lockstep rule holds. A match you leave standing never ends, and it is lost when your session ends (abandoned).

## 1. Goal
You control a legged humanoid (Unitree G1, 29 DOF) in a Table tennis (G1) match from seat `A`. Your opponent is a G1 driven by the platform at level 4 of four (L1-L4; `game spec` names it).
Your goal is to win by developing, operating and continuously improving your robot's control within the rules.
You are encouraged to study your opponent: observe how it plays, find its patterns and weaknesses, anticipate what it will do, and adapt your tactics to gain an advantage.

## 2. Rules & Scoring
`game rules` is the authority: the complete rules of this match and every deviation from the ITTF Laws of Table Tennis (ITTF Statutes 2025, chapter 2). Read it before you plan your approach; this chapter does not replace it.
- How a match is won: The winner: a player's third undue-delay fault loses it the match; else the first player to 5 points with a lead of 2, or the first to 7, wins the game (the match); a let scores no point (at most 2 service lets in a row); if 16 points (lets included) are played, the player ahead wins and at a level score the player who won the last point (last resort, not from the rulebook); there are no draws.
- This match belongs to no competition: its result stands on its own, and `game rules` holds the match rules only.

## 3. Match Setup & Procedure
### This match
- This is a single match outside any competition.
- The platform runs your opponent under your timing and information: its commands take effect at the next control step after the world state they answer, as yours do, and it sees the world only through what your seat gets, camera images two control steps late as yours. Declared exception, which concerns information only (`game spec` names it): the BOSS (level 4), which reads the ball's true position, velocity and spin at its decision step instead of your cameras' frames (no camera latency, no measurement error) and rolls them out in the venue's own ball model; its commands still take effect at the next control step after they are decided, as yours after they arrive, and it never reads your robot's commands.
- `game spec` gives this match's details (your side and your robots, the opponent's level).

### Timing
- Duration: after preparation, the match takes up to 90 minutes of real time.
- Speed (standard mode: lockstep): the world advances only while you let it: during an open `game wait DT` (at most DT game seconds, then it stops again) and, for a command you sent, up to the control step at which it takes effect (the step after the state it answers). Between your calls it stands still: your thinking, your program's computation and your observations take no game time, so a program has to keep calling `game wait` (or acting) for the match to go on. The platform's opponent is held to the same rule: after every control step the world waits for its program, so its computation takes no game time either. `game spec` says so (`timing.clock` = `lockstep`). The world also stands still during preparation and in review windows, whose limits are real time.
- Safety cap: a wall-clock cap of 2 h 4 min counts from the start of preparation over the whole match (preparation, play and reviews). It only stops a match that hangs: reaching it voids the match with no result for either side. It never decides the winner and is no extra time.
- `game status` shows the current phase and the time left in it.

### Preparation
- You have 30 minutes before the match starts, counted from your seat's first request to the match service (any `game` command); the official match world waits. Develop, train and test your programs.
- Send `game start` when you are ready; the match begins when you start. If you have not started when preparation ends, you lose (no-show).
- Preparation time you do not use is not given back: your robot plays from the start with whatever you have deployed then.

### Live match
- The world advances as your calls let it (Timing): your robot does what your programs (or you) command.
- You may keep developing, training and testing during play and deploy improved programs at any time.
- Watch your opponent throughout the match: its recurring patterns, strengths and weaknesses, and how its play changes. Use what you see to anticipate it and adapt your tactics; how you model it is up to you.

### Reviews
- After every point the world freezes for up to 300 s.
- Use the window to look back: why the point went as it did, what worked and what failed, what your opponent did, and what you will change. You may inspect logs, train, test and redeploy programs during the window.
- Send the review with `game ready "WHY" "PLAN"` (WHY: why the point went as it did; PLAN: what you will change; up to 2000 characters each). A review you do not send is recorded as missed; it does not change the score.
- The world resumes when you have sent it, or at the deadline.

### End
- The match ends when its rules end it (chapter 2); every match has a finite end. You may resign with `game resign` (you lose).
- The result is recorded automatically. When the match is over (full time, a no-show or a forfeit), its result is final and your session is ended a few seconds later; nothing after that changes the result.
- Your session must last until the match is over: when your session ends (you finish, or the time limit), a match that has not started is a no-show and a match in play is lost (abandoned), both valid losses.

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
- In this standard mode the world stands still while your program computes and communicates (Timing): only the steps you let pass count. A command taking effect does not mean the motion is done: the robot's motors and dynamics decide that.
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
- This task's seat has no GPU: the kit's PyTorch runs on your CPUs; the GPU twin and the CUDA paths of Warp and MuJoCo Warp are not available.
- `/opt/train/bin/python` runs PyTorch 2.14.1+cu130, NVIDIA Warp 1.17.0+cu12, MuJoCo Warp 3.11.0 on MuJoCo 3.11.0, mjlab 1.6.0 and rsl_rl 5.4.2 (every pinned package: `/opt/train/requirements.txt`). The system `python3` runs the match's MuJoCo 3.3.7 and has no CUDA. The kit is optional: train or build however you like.
- Import `torch` and `torch._dynamo` before `warp`, `mujoco_warp` or `mjlab`; another order can end the process with a segmentation fault. The kit's modules (`bodies.gpu.*` in `/opt/robot/lib`) import in this order.
- The official GPU twin (`bodies.gpu.twin`): `GpuTwin("/opt/ro/g1_tt_twin.xml", "/opt/ro/g1_tt_chain.json", num_envs=4096)` (your G1 with its paddle) runs thousands of copies of the match robot on the GPU and executes your rows as the match does (the chain file: row limiter, action latency, PD, motor curves, limits). `bodies.gpu.rl` wraps it for rsl_rl (a PPO example); `bodies.gpu.mjlab_compat` gives mjlab the same robot and chain. The twin holds your robot and what its model file adds, nothing else of the match world; check what you train in practice, which runs the match's own simulator.
- The parity test (`bodies.gpu.parity`) compares a twin with the match's own CPU execution of the same robot: open loop, the joints within 0.05 rad and the root within 0.01 m for 2 s; root held in the air, the joints within 0.002 rad for 4 s; closed loop, the joints within 0.05 rad and the root within 0.01 m for 1 s. After impacts single trajectories drift apart; their statistics agree.
- `/opt/robot/lib/bodies/gpu/README.md` explains the kit: a quick start, a PPO run and the known gaps.
- The twin's rows command all 29 joints (Unitree's order) through the robot library's open-control arbiter as the match's `joints` act does: one row per 10 ms held over the 1 ms physics steps, saturated at the joint ranges and speed limits, your kp / kd clipped at the simulator's stability bound (without them the platform's gains: the legs the walking deployment's, the waist and arms Unitree's), no feed-forward, Unitree's torque-speed curves and URDF torques, the PD on the joint sensors' noisy reading, no action delay. FALCON (the optional walker of the legs) is not in the twin.
- The ball is not in the twin: in the match it is this sport's own physics in the simulator (the flight with drag and spin, the table and net bounces, the blade impact), as is the referee. Add a ball model to your GPU training yourself if you need one; the twin gives the blade's pose (site `hand_center`).
- Parity with the match's MuJoCo 3.3.7 (the CPU chain steps the open-control arbiter bit for bit): the pelvis held in the air, tracking rows, the joints within 1e-3 rad up to the first self-contact (0.5 s; 4e-7 rad without the sensors' noise, which each side draws on its own: the same law, not the same numbers); on the floor, tracking, within 0.007 rad and 0.8 mm (0.47 s); open loop, falling, within 0.046 rad and 8 mm over the first 2 s (the kit's tolerance: 0.05 rad). After contacts single trajectories drift apart; statistics agree.

### Compute and workspace
- Your container's CPUs and memory are under `## Resources`; they are shared by everything you run (your tools, programs, training and practice).
- Make full use of your resources during preparation and whenever you train.
- Everything you need is installed.
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
- Stay in your session until full time: a review you do not send is recorded as missed, and when your session ends the match ends with it (a no-show before the start, a loss once it is in play). Nothing wakes a session that has ended.

### Deployment records
- The platform saves each program you deploy (its files, weights and command line) and may rerun it offline for diagnostics; that never changes your result, and you need not package anything during the match.

## 7. Restrictions
You are free to develop, train, experiment and adapt inside your seat. Not allowed:
- Reaching anything outside your seat other than the seat protocol (`game`, the match service at localhost:8000), the practice service (localhost:8100) and your model's API.
- Reading the match world's internals or hidden state, other seats' environments, programs or files, or an opponent's hidden settings, other than through `game` (ground truth in your practice worlds is yours to use).
- Interfering with the match service, the referee, the scoring, the clock, other seats or the platform.
`game rules` lists the sport's fouls and penalties.

## 8. References
- Rules and configuration: `game spec` (match configuration, robots, interfaces, timing, limits, this match's details) · `game rules` (the complete rules)
- Operation: `game start` · `game status` · `game observe` · `game act` · `game wait` · `game ready` · `game resign` · `game program`
- Development: `/opt/practice/README.md` · `game practice` · `/opt/ro/toolkit.toml` · `/opt/ro/g1_robot_only.xml` · `/opt/robot/lib/bodies/gpu/README.md`
Before you develop or deploy your programs, read `game spec` and `game rules`.

## This run: privileged state queries

This run lets you query the simulator's state. This section overrides anything above that says to use only the
camera images, the service's replies and this document, or that the simulator's state is never given.

- `GET http://localhost:8000/$SEAT/state/entities` lists what you can query:
  `{"frame": ..., "quaternion_order": ..., "entities": {name: {"kind": ..., "fields": {field: unit}, "note"?}}}`.
  The kinds are `robot` (your robot, and the opponent's when it is one), `robot_link` (your paddle, racket, rods or
  blade), `object` (the ball or the shuttle, the opponent's paddle, racket or blade, a scripted opponent that is only
  drawn), `articulation` (the opponent's rods) and `scene_feature` (the table, net, court, goals, playfield, piste and
  its lines); `note` says what an entity is. The list is fixed for the run.
- `POST http://localhost:8000/$SEAT/state/query` with `{"names": ["ball", ...], "fields": ["pos"]}` answers JSON
  `{"state": {name: {field: value}}, "control_steps": ..., "sim_time_s": ..., "state_queries": ...}` with the
  current values from the simulator. `fields` is optional. The fields and their units are in the list: `pos` m,
  `quat`, `lin_vel` m/s, `ang_vel` rad/s, `joint_pos` / `joint_vel` / `joint_range` {joint: value}, `size` (the
  full extents along the body's own axes, m) and `bbox` (its axis-aligned box, `[[x, y, z] min, [x, y, z] max]`, m),
  all in the frame `frame` names (your own frame, as in the observation). An unknown name or field is a 400 that
  lists the valid ones.
- A query only reads: no control step, the clock neither advances nor pauses (the world stands still during it, as between your calls).
  It is served until the match is over (409 after). Queries are counted and recorded; they do not change the grading.
- Nothing else changes: no answer holds the score, a point's result or the opponent's plan or strategy.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **2048 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator (`sim`) and `practice` and `practice_player` run in containers of their own and do not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and graded on what stands at that moment, as the sections above say. The service does not count this limit for you: the clocks it reports are the game's own. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
