# Full-simulator table tennis on a Unitree G1: develop a program against the BOSS (level 4)

Win one complete match from seat `A` against the platform's G1 at level 4 of four (the BOSS), seed 4: the same frozen
instance as `embodied-olympics-match-tabletennisg1-matchgpu-i01-realtime` (its realtime twin; there you see only camera images and the world runs in real time).
Both robots are Unitree G1 humanoids (29 joints within Unitree's URDF limits and motor torque-speed curves, joint
sensors' noise, self-collision, falls), each holding a real racket. The rules, the referee, the opponent and the
joint-level interface are unchanged: one game to 5 points (lead by 2 from 4:4, the first to 7 wins), the ITTF service
laws with a toss device; `/opt/rules/RULES.md` has the complete rules (the twins' `game rules`). The BOSS reads the ball's true state; here you do too.

## Development
- The full simulator, source included, is at `/opt/fullsim` (the match's own core and sport, `PYTHONPATH=/opt/fullsim`).
  You may read, run and change any copy of it: any level 1-4, any seed, any state, as many matches as you like.
- `python3 -m tools.g1tt_priv.match POLICY_DIR [LEVEL [SEED [DATA]]]` (in `/opt/fullsim`) plays one match of your
  program exactly as the formal match does (the same runner, view and limits), in your own process; it prints the
  score, and DATA keeps the episode. `python3 -c "from tools.g1tt_priv import match; import json; print(json.dumps(match.public_spec()))"`
  prints the seat's spec (the robot, the joints, the cameras, the action schema).
- The robot toolkit is at `/opt/fullsim/sport/seat` (`toolkit.toml`: the robot's model, a robot-only simulator); the sport's
  reference player (camera only, a learned striker) is `/opt/fullsim/sport/builtin_players.py` with
  `/opt/fullsim/sport/lowlevel/reference/`.
- Your container has one NVIDIA GPU and the release's GPU training kit: `/opt/train/bin/python` runs PyTorch 2.14.1+cu130, NVIDIA Warp 1.17.0+cu12, MuJoCo Warp 3.11.0 on MuJoCo 3.11.0, mjlab 1.6.0 and rsl_rl 5.4.2 (every pinned package: `/opt/train/requirements.txt`); the kit's modules are in `/opt/robot/lib` (`bodies.gpu`, `/opt/robot/lib/bodies/gpu/README.md`), among them the official GPU twin of your G1 with its paddle (`/opt/ro/g1_tt_twin.xml`, `/opt/ro/g1_tt_chain.json`). Import `torch` and `torch._dynamo` before `warp`, `mujoco_warp` or `mjlab`. The system `python3` is the formal match's (MuJoCo 3.3.7, no CUDA).
- The formal match runs your program with the system `python3` on the CPU (no GPU, no PyTorch): keep trained weights as files in your folder that your program reads with NumPy.

## Deliverable
Leave `/app/output/policy/program.py` and any helper or data files in that folder (at most 512 regular files, 32 MiB;
no links). It defines `make_policy(config)` returning an object with `act(view)`; the object lives for the whole match.
`config` has `spec` (the seat's spec), `seat`, `level`, `seed`, `call_limit_s`, `budget_s`. Every control step (0.01 s
of game time) `act` gets `view`: `state` (the seat's state: the score, the rally, your robot's joints and sensors, ...),
`observation` (the camera images, as the twins' seat gets them) and `truth` (the ground truth: the ball's position,
velocity and spin, both robots' `qpos` / `qvel`, the score, the rally). It returns one joint-level action body (the
spec's schema: joint targets with gains, or the serve's toss) or `None`. Helpers in the folder are importable. Submit
executable code, not a recorded trajectory. Write a valid program early and improve it.

## Formal evaluation
After your session a separate verifier without network runs your final program as an unprivileged process against a
fresh, unmodified copy of the simulator, with the sport's in-process runner (`core/local.py`): the world waits for
your answer at every control step, which takes effect at that step; an answer later than 0.5 s of wall time
is no command at that step, and past 1800 s of your program's time in total it sends no command for the rest of
the match. The platform's opponent waits the same way. Your program may read the public read-only copy `/opt/dev` (the
same files as `/opt/fullsim`); it cannot read the trusted simulator or the referee, and it has no model or API access.
The match ends when it is over; one still unfinished after 636000 control steps is not won. The verifier replays the
recorded episode in a fresh process; success requires a completed match you won and a replay that agrees. A program
error is no command at that step; a program that dies plays no more. Any process of your program left after the
match makes the trial your 0. This fixed instance does not measure generalization to unseen instances.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **16 GiB of memory**, **2048 processes and threads**, **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`) and **one GPU, 20 GiB of its memory**. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
