# Embodied Olympics · table tennis on Unitree G1s (GPU tier), match against level 4 (privileged)

## Task
Win a game of table tennis to 5 points against the other robot.

## Goal
Success: your program wins the complete formal match.

Deliverable: `/app/output/policy/program.py`, with any helper or data files in that folder (at most 512 regular files,
32 MiB; no links; helpers are importable). It defines `make_policy(config)`, which returns an object with an `act(view)`
method; that object lives for the whole match. `config` has `spec` (the seat's spec), `seat`, `level`, `seed`,
`call_limit_s`, `budget_s`. Every control step (0.01 s of game time) `act` gets `view`: `state` (the seat's state: the
score, the rally, your robot's joints and sensors, ...), `observation` (the camera images, as the twins' seat gets them)
and `truth` (the ground truth: the ball's position, velocity and spin, both robots' `qpos` / `qvel`, the score, the
rally). It returns one joint-level action body (the spec's schema: joint targets with gains, or the serve's toss) or
`None`. The formal match runs your program with the system `python3` on the CPU (no GPU, no PyTorch): keep trained
weights as files in your folder that your program reads with NumPy. Save a valid program early and overwrite it when you
have a better one.

The formal match: after your session a separate verifier without network runs your final program as an unprivileged
process against a fresh copy of the simulator, with the sport's in-process runner: the world waits for your answer at
every control step, which takes effect at that step; an answer later than 0.5 s of wall time is no command at that step,
and past 1800 s of your program's time in total it sends no command for the rest of the match. The platform's opponent
waits the same way. The match ends when it is over; one still unfinished after 636000 control steps is not won. A
program error is no command at that step; a program that dies plays no more. Leave no process of your program running
after the match: one left scores the trial 0.

Rules: **No cheating.** Do not search for, download or use any existing solution (published or reference solutions, the
benchmark's demonstrations, trained policies); trials are reviewed. Hand in executable code, not a recorded trajectory;
no model or API calls during the formal match. Your program may read the public read-only copy `/opt/dev` (the same
files as `/opt/fullsim`), never the trusted simulator or the referee.

## Robot Interface
Table tennis between two Unitree G1 humanoids (29 joints within Unitree's URDF limits and motor torque-speed curves,
joint sensors' noise, self-collision, falls), each holding a real racket. You are seat `A` against the platform's G1 at
level 4 of four (the BOSS), seed 4: the same fixed match as the realtime twin
(`embodied-olympics-match-tabletennisg1-matchgpu-i01-realtime`, where you see only camera images and the world runs in
real time), with the same rules, referee, opponent and joint-level interface. The BOSS reads the ball's true state; here
you do too. You have the full simulator to develop with; you hand in a program that plays the match.

### Tooling
```
python3 -m tools.g1tt_priv.match POLICY_DIR [LEVEL [SEED [DATA]]]    # in /opt/fullsim
python3 -c "from tools.g1tt_priv import match; import json; print(json.dumps(match.public_spec()))"
```
- The first plays one match of your program exactly as the formal match does (the same runner, view and limits), in your
  own process; it prints the score, and DATA keeps the episode. The second prints the seat's spec (the robot, the
  joints, the cameras, the action schema).
- The full simulator, source included, is at `/opt/fullsim` (the match's own core and sport, `PYTHONPATH=/opt/fullsim`).
  You may read, run and change any copy of it: any level 1-4, any seed, any state, as many matches as you like.
- The robot toolkit is at `/opt/fullsim/sport/seat` (`toolkit.toml`: the robot's model, a robot-only simulator); the
  sport's reference player (camera only, a learned striker) is `/opt/fullsim/sport/builtin_players.py` with
  `/opt/fullsim/sport/lowlevel/reference/`.
- The GPU training kit: `/opt/train/bin/python` runs PyTorch, NVIDIA Warp, MuJoCo Warp, mjlab and rsl_rl (the pinned
  packages: `/opt/train/requirements.txt`); the kit's modules are in `/opt/robot/lib` (`bodies.gpu`,
  `/opt/robot/lib/bodies/gpu/README.md`), among them the official GPU twin of your G1 with its paddle
  (`/opt/ro/g1_tt_twin.xml`, `/opt/ro/g1_tt_chain.json`). Import `torch` and `torch._dynamo` before `warp`,
  `mujoco_warp` or `mjlab`. The system `python3` is the formal match's (no CUDA).

### Actions
One joint-level action body per control step (the spec's schema: joint targets with gains, or the serve's toss). The
rules: one game to 5 points (lead by 2 from 4:4, the first to 7 wins), the ITTF service laws with a toss device;
`/opt/rules/RULES.md` has the complete rules (the twins' `game rules`).

## Limits
- Time: 7200 s of wall-clock time from the start of your session. Everything counts, including the simulator's start-up.
  At the end you are stopped without warning and only what is in `/app/output/` at that moment is graded. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`). A call into a long-running process can block for its
  whole wait time. Use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, including the simulator's and the benchmark's source.
- Resources: 8 CPUs, 16 GiB memory, 2048 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  one GPU (20 GiB of its memory). Going over a cap can get a process killed (the CPU cap only slows you down). Usage:
  `/run/rcb-limits/usage.json`.
- Resets: as many as you like in development (any level, seed and state); none in the formal match.
