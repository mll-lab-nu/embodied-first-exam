# Embodied Olympics - Fun

## Overview

Seventy-nine single-robot sports for a humanoid. One Unitree G1 or Unitree H1-2 sprints the indoor 50 m, jumps rope,
takes a penalty against a keeper, returns a table-tennis serve, dunks, swings a giant on the high bar, skis a slalom,
flies a big air or dives from the 10 m platform. A referee for each sport decides from the simulator's state whether
the robot did the sport. The physics is real and the robot is its own; the agent may use the robot's built-in walking
(and, on the G1, running) policies, drive every joint, and find and adapt public tools and pretrained controllers.

| | |
|---|---|
| tasks | 79 families, one frozen instance each (seed 0): 79 `-privileged`, 79 `-standard` and 21 `-realtime` task directories, `embodied-olympics-fun-<family>-i00-<mode>` |
| simulator | MuJoCo 3.3.7 on the CPU, 1 ms physics steps, 10 ms control steps, on the Embodied Olympics robot library |
| robots | Unitree G1 (1.32 m, 33 kg, 29 joints; Unitree's walking policy, FALCON and WBC-AGILE walking policies, a running policy) and Unitree H1-2 (1.78 m, 67 kg, 27 joints; Unitree's walking policy), each family on the one its official venue needs |
| score | the referee's binary verdict: every stage of the sport in order, no rule broken, within the attempt's time limit |
| image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-<images/embodied-olympics-fun/VERSION>`; the shared files (`rcb_rfo.py`, the `rfo` package, the graders, the standard service, each family's referee module) come from `efe:embodied-olympics-fun-files-<VERSION>` (`images/embodied-olympics-fun-files/FILES.json`); source `embodied_first_exam/benchmarks/embodied-olympics-fun/` |
| agent time | 7200 s in every mode (each task's `[agent] timeout_sec`) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/embodied-olympics-fun -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

## Upstream and license

- Upstream: the Embodied Olympics robot library ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a
  private repository, MIT), commit `7df999b` (branch `athletics-v3`; the G1 at revision g1-4 and the H1-2 at revision
  h1-4 of its robot library), copied unchanged into the image (`images/embodied-olympics-fun/roboolympics/`, checked
  against `manifest.sha256` at build time; `SOURCE.md` lists every file).
- The sports, venues and referees (`rfo/`, one module per family under `rfo/tasks/`) are this benchmark's own, MIT.
- Third-party parts, each with its licence file next to it in the image: the Unitree G1 model and meshes from MuJoCo
  Menagerie `unitree_g1` (BSD-3-Clause, modified by Embodied Olympics); the Unitree H1-2 model, meshes and walking policy
  and the G1 walking policy from unitree_rl_gym (BSD-3-Clause); the G1 running policy from C1801SYQ/g1_running
  (Apache-2.0); FALCON's G1 policy from LeCAR-Lab/FALCON (MIT); the WBC-AGILE G1 velocity-height policy from NVIDIA
  (Apache-2.0). No non-commercial terms apply.

## Changes from upstream

- **Left out of the image**: the robots' high-resolution meshes and tools, the G1's `policy/motion.pt` and its kick
  skill (`kick.py`, a task-level skill; the arbiter's `kick()` answers "no kick skill").
- **Actuators**: Unitree's measured actuator data (torque-speed curves, rotor inertia, friction) on both robots
  (`rfo/world.py` `unitree_actuators`). The H1-2's legs and arms use H2-class actuators from Unitree's H2 data (hips
  and knees 360 N m); its torso keeps 200 N m and its wrists 19 N m.
- **Collision shells**: where a robot's visible body has no collision geometry (the H1-2's thighs, shins, knees, hips
  and wrist housings, the G1's waist and outer shoulder housings), its visual mesh gets a massless convex shell that
  touches the props, so a bar, rope, ball, hurdle or opponent cannot pass through it. Real self-collision; contact with
  the ground stays MuJoCo's soft default.
- **Hands** (`rfo/realhand.py`): nothing a hand holds is welded. In 23 families the robot's own finger hands (the G1's
  Dex3-1, the H1-2's Inspire RH56DFX) hold rackets, balls, bars, poles and handles by contact and friction, one closure
  command per hand; in other families a ball is pressed between or carried on flat palm pads, or a tool (racket, paddle,
  club) sits on the wrist mount.
- **Raised parameters** are at most 1.5 to 2 times native, each declared with its measured need; the one exception is
  `high_bar_swing`'s grip (5 times: a giant swing pulls four or more body weights at the bottom).
- **Venues**: official dimensions where the hardware can reach them; otherwise the demand is lowered only to near the
  measured physical limit and declared (for example the ring at 2.39 m in `dunk` and `dunk_between_legs`, a 5 kg
  technique bar from 0.35 m blocks in `clean_and_jerk`, the women's 600 g javelin, the indoor 50 m in `sprint` and
  `hurdles_freestanding`). Balls come from two-wheel ball machines; keepers, rope turners and opponents are
  force-limited mechanisms. No held object is welded, nothing is pinned or moved by mocap, and no velocity is written
  after the start. Each family's instruction names its rule book and every deviation from it with its reason.

## Interface

**Actions** (both modes): one sim row per 10 ms control step, in one of the robot's action types: `stand` (waist and arm
targets, the legs held in the stance), `walk` (a velocity command for Unitree's walking policy, plus waist and arm
targets), `joints` (a target for every joint), `lowcmd` (Unitree's LowCmd: q, dq, tau, kp, kd for every joint), and on
the G1 also `walk_falcon`, `walk_agile` (the FALCON and WBC-AGILE walking policies), `run` and `run_arms` (the running
policy). Every type ends with `grip_left`, `grip_right`: a palm-pad grip (≥ 0.5 closes it) or a finger hand's closure
command (0 open to 1 closed). A sim row is 151 floats on the G1 and 141 on the H1-2.

- **privileged**: `/opt/tools/rcb_rfo.py` (`from rcb_rfo import Session`): the frozen instance with the full world
  (`s.world`: MuJoCo model and data, the robot, the referee and its live record), `s.state()` (the pelvis, the joints,
  the task's objects), `s.step(type, row)`, `s.reset()` (unlimited), `s.replay()` (what the verifier does) and
  `s.save_trajectory()`. The deliverable is `/app/output/trajectory.npz`.
- **standard**: the robot as a service in a `sim` sidecar, through `rcb_client.py` or the `efe-robot` MCP tools, on the
  eai-standard/3.0 endpoints. The agent gets the robot's two head cameras (270 × 480 RGB, depth on the left one), joint
  encoders, motor torques, the pelvis and torso IMUs, whether each hand holds something, and the venue's fixed cameras;
  action chunks of any of the action types. It never gets the robot's or an object's pose during an attempt or the
  referee's state. The rule book and the venue are described as an athlete knows them. When the referee ends an attempt
  on a foul or a fall, every later reply names the rule broken (`meta["outcome"]`); a success and the stages reached are
  never shown. Reset budget: 5 (`RCB_RESET_BUDGET`; 0 gives one attempt), each a new attempt from the frozen start.
- **realtime** (21 families with a ball, keeper, rope, boom or opponent that moves on the venue's clock): standard mode
  on a clock that does not stop, one control step every 10 ms of wall time (slowdown S = 1 in every family). The
  sidecar renders the cameras with EGL on its GPU.

Egress is open in every mode (`[agent] network_mode = "public"`): the agent may search for, vet and adapt public tools,
robot models and pretrained controllers, but must not use an existing solution to the task (the instruction's **No
cheating.** rule; trials are reviewed).

## Grading

- **The referee** (`rfo/referee.py`, with the family's rules in `rfo/tasks/<family>.py`) judges from the simulator's
  state after every 1 ms physics step: stages that latch in the sport's order, contact events and legal body parts,
  crossings found between physics steps, flight phases. A success needs every stage latched with no rule broken. A
  foul, a fall (for most families: the pelvis below a set height, or any part but the legal ones on the ground), the
  attempt's time limit or the physics diverging ends the attempt as a failure. Once the referee has called the
  attempt, its record no longer changes. Its record is part of the state hash.
- **Privileged**: `tests/grade.py` replays the trajectory once, in a fresh process of a separate verifier container
  without network, from the frozen start until the referee calls the attempt; pass if it called a success.
- **Standard and realtime**: the referee in the sidecar judges the live attempt; nothing is replayed. The success
  call is an event: it counts the moment it is made, is never shown, and does not end the attempt, which goes on until
  the agent's `/finish`, the time limit or the end of the session. A failure called before any success ends the
  attempt with 0. Only the last attempt is graded. The start is checked against the instance's state hash.

## Tasks

One row per family; "ref." marks the 19 families with a reference solution (`oracle = "full"`: `solution/solve.sh`
succeeds in the task's own setting); the other 60 have none. Every family's referee has a
test with a declared positive and negative controls. Each task's README states its family's exact success conditions.

| family | robot | event | modes | ref. |
|---|---|---|---|---|
| `alpine_slalom` | G1 | Alpine skiing: slalom | privileged, standard |  |
| `backflip` | G1 | Backflip | privileged, standard |  |
| `badminton_serve` | G1 | Badminton: singles service | privileged, standard |  |
| `balance_beam` | G1 | Balance beam | privileged, standard |  |
| `balance_board` | G1 | Balance board | privileged, standard |  |
| `basketball_dribble` | H1-2 | Basketball: dribble to the frontcourt | privileged, standard |  |
| `bowling` | H1-2 | Ten-pin bowling: a strike | privileged, standard |  |
| `box_jump` | H1-2 | Box jump | privileged, standard |  |
| `boxing` | H1-2 | Boxing: one clean punch on the heavy bag | privileged, standard | yes |
| `breaking_windmill` | G1 | Breaking: windmills | privileged, standard |  |
| `catch_and_shoot` | H1-2 | Basketball: catch and shoot | privileged, standard, realtime |  |
| `catch` | H1-2 | Baseball: catch a fly ball | privileged, standard, realtime |  |
| `clean_and_jerk` | H1-2 | Weightlifting: clean and jerk | privileged, standard | yes |
| `crawl` | G1 | Low-wire crawl | privileged, standard |  |
| `discus` | H1-2 | Athletics: discus throw | privileged, standard |  |
| `dodgeball` | G1 | Dodgeball: dodge five throws | privileged, standard, realtime | yes |
| `double_dutch` | G1 | Double Dutch (enter two turning ropes and jump them) | privileged, standard, realtime |  |
| `dribble_slalom` | G1 | Football: slalom dribble | privileged, standard |  |
| `dunk_between_legs` | H1-2 | Basketball: between-the-legs dribble and dunk | privileged, standard |  |
| `dunk` | H1-2 | Basketball: two-hand dunk, lowered ring | privileged, standard |  |
| `first_time_shot` | G1 | Football: first-time shot | privileged, standard, realtime | yes |
| `free_kick_wall` | G1 | Football: direct free kick over or around the wall | privileged, standard |  |
| `free_throw` | H1-2 | Basketball: free throw | privileged, standard |  |
| `freeski_360` | G1 | Freeski big air: 360 spin | privileged, standard |  |
| `freeski_straight_air` | G1 | Freeski big air: straight air | privileged, standard |  |
| `giant_slalom` | G1 | Alpine skiing: giant slalom | privileged, standard |  |
| `goalkeeper_save` | H1-2 | Football: goalkeeper, save three penalties | privileged, standard, realtime | yes |
| `golf_putt` | G1 | Golf: a 3 m putt | privileged, standard | yes |
| `handstand` | G1 | Handstand | privileged, standard |  |
| `header` | H1-2 | Football: header | privileged, standard, realtime |  |
| `high_bar_swing` | G1 | High bar: jump to the bar and giant swing | privileged, standard |  |
| `high_jump` | H1-2 | High jump | privileged, standard |  |
| `hurdles_freestanding` | H1-2 | 50 m hurdles, free-standing hurdles | privileged, standard |  |
| `inline_slalom` | G1 | Inline speed slalom | privileged, standard |  |
| `javelin` | H1-2 | Athletics: javelin throw | privileged, standard |  |
| `juggle_three` | G1 | Juggling: a three-ball cascade | privileged, standard, realtime |  |
| `juggling_feet` | G1 | Football: keepie-uppie with the feet | privileged, standard |  |
| `juggling_head` | G1 | Football: head juggling | privileged, standard, realtime |  |
| `juggling` | G1 | Football: keepie-uppie | privileged, standard |  |
| `jump_rope` | G1 | Rope skipping (one minute) | privileged, standard |  |
| `kick_target` | H1-2 | Kick the heavy bag at trunk height | privileged, standard |  |
| `layup` | H1-2 | Basketball: layup | privileged, standard |  |
| `long_jump` | G1 | Long jump | privileged, standard |  |
| `long_rope` | G1 | Long rope (jumping a rope turned by two turners) | privileged, standard, realtime | yes |
| `paddle_bounce` | G1 | Table tennis: keep the ball bouncing on a paddle | privileged, standard, realtime | yes |
| `penalty_kick` | G1 | Football: penalty kick | privileged, standard, realtime |  |
| `pitch_target` | H1-2 | Baseball: pitch a strike | privileged, standard |  |
| `platform_10m` | G1 | 10 m platform: forward dive straight (101A) | privileged, standard | yes |
| `pole_vault` | G1 | Pole vault | privileged, standard |  |
| `round_off` | G1 | Round-off | privileged, standard |  |
| `rugby_conversion` | G1 | Rugby: conversion kick over the crossbar | privileged, standard | yes |
| `shot_put` | H1-2 | Athletics: shot put | privileged, standard |  |
| `shuttle_run` | G1 | 4 x 10 m shuttle run | privileged, standard |  |
| `skateboard_ollie` | G1 | Skateboard ollie | privileged, standard |  |
| `slalom` | G1 | Illinois agility test | privileged, standard |  |
| `sled_push` | H1-2 | Sled push: one 12.5 m length on turf | privileged, standard |  |
| `snowboard` | G1 | Snowboard: parallel slalom | privileged, standard |  |
| `springboard_3m` | G1 | 3 m springboard: forward dive straight (101A) | privileged, standard | yes |
| `sprint` | G1 | 50 m | privileged, standard | yes |
| `standing_long_jump` | G1 | Standing long jump | privileged, standard |  |
| `steeplechase` | H1-2 | Steeplechase: the water jump | privileged, standard |  |
| `sumo` | G1 | Sumo (one bout against a pushing robot) | privileged, standard, realtime | yes |
| `sweeper_jump` | G1 | Sweeper jump (jumping the boom of a Meltdown sweeper) | privileged, standard, realtime | yes |
| `table_tennis_return` | G1 | Table tennis: return a service | privileged, standard, realtime |  |
| `taekwondo_kick` | G1 | Taekwondo: a scoring kick to the trunk protector | privileged, standard |  |
| `tennis_return` | H1-2 | Tennis: return of serve | privileged, standard, realtime |  |
| `tennis_serve` | H1-2 | Tennis: serve | privileged, standard | yes |
| `toes_to_bar` | G1 | High bar: toes-to-bar | privileged, standard | yes |
| `trampoline` | G1 | Trampoline: tuck jump and stop | privileged, standard | yes |
| `trap_ball` | H1-2 | Football: trap a pass | privileged, standard, realtime |  |
| `triple_jump` | G1 | Triple jump | privileged, standard |  |
| `vault` | H1-2 | Vault | privileged, standard |  |
| `vertical_jump` | G1 | Vertical jump (jump and reach) | privileged, standard |  |
| `volley_shot` | H1-2 | Football: volley shot | privileged, standard, realtime |  |
| `volleyball_bump` | H1-2 | Volleyball: serve receive | privileged, standard, realtime | yes |
| `volleyball_serve` | H1-2 | Volleyball: serve | privileged, standard | yes |
| `volleyball_set` | H1-2 | Volleyball: set | privileged, standard, realtime |  |
| `volleyball_spike` | H1-2 | Volleyball: spike | privileged, standard, realtime |  |
| `wall_ball` | H1-2 | Wall ball: throw, rebound, catch | privileged, standard |  |

The matches Embodied Olympics exports with its own service are the separate benchmark
[Embodied Olympics - Match](../embodied-olympics-match/README.md).

## Others

- Compute: privileged and standard are CPU only (MuJoCo on the CPU, OSMesa rendering); one world steps about 0.8 to
  3.6 times real time on one core, depending on the host (the finger-hand families slowest), and holds about 0.4 GB.
  Realtime needs an NVIDIA GPU with EGL in the sidecar. Caps per container: `scripts/task_resources.toml` (each task's
  README lists them).
- Rebuild the image with `scripts/images.sh build` (context `images/embodied-olympics-fun/`); after a change to a
  shared file, rebuild and re-pin the files image (`scripts/files_image.py build|pin embodied-olympics-fun-files`).
