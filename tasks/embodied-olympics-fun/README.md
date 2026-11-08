# Embodied Olympics - Fun

Seventy-nine single-robot sports for a humanoid: one Unitree G1 or H1-2 sprints the indoor 50 m, jumps rope, takes a
penalty against a keeper, returns a table-tennis serve, dunks, swings a giant on the high bar, skis a slalom, flies a
big air or dives from the 10 m platform. A referee decides from the simulator's state whether it did the sport. The
physics is real and the robot is its own, so most tasks have no known solution with the robot's own controls: the
benchmark is meant to find the ceiling of coding agents, which may use the robot's built-in walking (and, on the G1,
running) policy, drive every joint, and search for and download public tools and pretrained controllers.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/embodied-olympics-fun -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it. Each task dir's README carries its family's rule book, deviations, evidence
and numbers.

| | |
|---|---|
| tasks | 79 families: 79 `-privileged`, 79 `-standard` (`eai-standard/2.1`) and 21 `-realtime` (`eai-standard/2.3`, the dynamic families), 179 dirs, `embodied-olympics-fun-<family>-i00-<mode>`; core set 56 (45 default standard, 11 default realtime) |
| simulator | MuJoCo 3.3.7 on the CPU (1 ms physics, 10 ms control), on [Embodied Olympics](https://github.com/CHIGUI0/roboolympics)' robot library and running policy (MIT), unchanged in the image |
| image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-<images/embodied-olympics-fun/VERSION>`; shared files (tooling `rcb_rfo.py`, the `rfo` core, graders, the standard service, the dynamic families' modules) from `efe:embodied-olympics-fun-files-<VERSION>` (`images/embodied-olympics-fun-files/FILES.json`); source `embodied_first_exam/benchmarks/embodied-olympics-fun/` |
| actions | one sim row per 10 ms: `stand`, `walk`, `joints`, `lowcmd` (Unitree's LowCmd), on the G1 also `walk_falcon`, `walk_agile`, `run`, `run_arms`; `grip_left`, `grip_right` |
| score | the referee's binary verdict (every stage in order, no rule broken, within the time limit), with `progress` and the family's metrics beside it |
| agent budget | 7200 s in every mode (each task's `[agent] timeout_sec`) |
| network | open (below) |

## Robots and hands

- **Unitree G1** (1.32 m, 33 kg, 29 joints; three walking policies and a running policy) with its **Dex3-1**
  three-finger hands, and the **Unitree H1-2** (1.78 m, 67 kg, 27 joints; a walking policy) where the venue needs an
  adult-size body, with its **Inspire** five-finger hands (20 N per fingertip, 30 N the thumb).
- Unitree's measured actuator data (torque-speed curves, rotor inertia, friction); the H1-2's legs and arms are
  H2-class actuators from Unitree's H2 data (hips and knees 360 N m), its torso keeps 200 N m and its wrists 19 N m.
  Real self-collision; contact with the ground stays MuJoCo's soft default by design.
- Nothing a hand holds is welded and nothing is grippable. In 23 families the finger hands hold rackets, balls, bars,
  poles and handles by contact and friction (one closure command per hand); in 5 ball families (`bowling`,
  `juggling`, `juggling-feet`, `shot-put`, `volleyball-serve`) the ball is pressed between or carried on the hands' flat
  palm pads; elsewhere the hands hold nothing.

## Design rules

- **Real physics.** No welds of held objects, no pins, no mocap bodies, no velocities written after the start: balls
  come from two-wheel ball machines, keepers and rope turners are force-limited mechanisms, material numbers are sourced.
- **The native body.** Each robot with its own hands and actuators.
- **Raised parameters at most 1.5-2 times native**, declared with the measured need; the one exception is
  `high-bar-swing`'s grip (5 times: a giant swing pulls four or more body weights at the bottom).
- **Official venues where the hardware can reach them**, else the demand lowered only to near the measured physical
  limit, and declared. For example:
  - `dunk`, `dunk-between-legs`: the ring at 2.39 m, where an own-motor dunk from the start hold is shown by search;
  - `clean-and-jerk`: a 5 kg aluminium technique bar lifted from 0.35 m blocks;
  - `javelin`: the women's 600 g javelin;
  - `sprint`, `hurdles-freestanding`: the indoor 50 m.

Every family names its rule book and lists each deviation with its reason in its task's instruction and README.

## Modes

- **privileged**: the world in the agent's container (full state, the referee's live record, the rules as code,
  unlimited resets); the deliverable is `trajectory.npz` (sim rows).
- **standard**: a client only (head cameras with depth, joint encoders, torques, IMUs, the hands' state, the venue's
  camera; action chunks); the rule book and the venue as an athlete knows them, never the robot's or an object's pose
  during an attempt or the referee's state; each attempt ends with the referee's call.
- **realtime** (21 dynamic families: a ball, keeper, rope, boom or opponent that moves on the venue's clock):
  standard on a clock that does not stop, 100 Hz control, slowdown S = 1 in every family (real time); rendered with EGL on the
  sidecar's GPU.

**Reset budget 5** in standard and realtime: a sport is attempts, and 5 is about the trials a field event
gives an athlete, enough to correct from the referee's call and too few to search for a plan by trial and error. The
last attempt is graded and a success ends the trial. With resets the first attempt is kept (`trajectory.first.npz`,
`replay.first.mp4`; `first_success` in `final.json` and `reward.json`): the no-reset view.

## Grading

- **The referee** (`rfo/referee.py`) judges from the simulator's state after every 1 ms physics step: stages that
  latch in order, contact events and legal body parts, crossings found between physics steps, flight phases; a foul,
  a fall, the time limit or a physics blow-up ends the attempt. Its record is part of the state hash.
- **Privileged**: `tests/grade.py` replays the trajectory in one fresh process, which must succeed.
- **Standard and realtime**: the sidecar's referee calls the live attempt (`final.json`, `graded_by` live,
  no grading replay); the start is checked against the instance's state hash, and a crash resumes the attempt from the
  sidecar's journal.

## Reference solutions

19 families have a real controller that succeeds in the task's own setting (`oracle = "full"`, marked below); the
other 60 have none (`oracle = "none"`, human review). Every family has a referee test with a declared positive (a real
controller or a magic action that makes the sport's events happen in physics) and negative controls.

## Network: open

The tasks declare open egress, `[agent] network_mode = "public"`: the instruction encourages the agent to find, vet and adapt public
tools, robot models and pretrained controllers (fair equipment, as a published walking controller is for a real G1)
and asks only that it not look up a ready-made solution to the task, such as this repository's reference solutions
(an honour rule; trials are reviewed). Results are open-network results; the harness's web search stays off in
official runs; trial rows stay private (a passing trajectory is a complete solution).

## Compute

Privileged and standard: CPU only (MuJoCo on the CPU, OSMesa rendering); one world steps about 0.8 to 3.6 times real time on one core, depending on the host (the finger-hand families slowest) and holds about 0.4 GB.
Realtime: the sidecar needs an NVIDIA GPU, which renders the cameras with EGL (the physics stays on the CPU).
Privileged: agent 8 CPUs / 16 GiB, verifier 4 CPUs / 8 GiB; standard: sidecar 4 CPUs / 5 GiB, agent 4 CPUs / 10 GiB;
realtime: sidecar 4 CPUs / 8 GiB and 4 GiB of GPU memory, agent 4 CPUs / 10 GiB (`scripts/task_resources.toml`).

## Run

```bash
harbor run -p tasks/embodied-olympics-fun/embodied-olympics-fun-sprint-i00-privileged -a oracle        # or -a nop: scores 0
harbor run -p tasks/embodied-olympics-fun/embodied-olympics-fun-penalty-kick-i00-standard -a codex -m openai/gpt-6-astra --env-file .env
```
Build the image with `scripts/build_images.sh` (context `images/embodied-olympics-fun/`); after a change to a shared
file, rebuild and re-pin the files image (`scripts/files_image.py build|pin embodied-olympics-fun-files`).

## The 79 families

One row per family; "ref." marks the 19 with a reference solution. The robot is the family's `Task.robot`.

| family | robot | event | ref. | family | robot | event | ref. |
|---|---|---|---|---|---|---|---|
| `sprint` | G1 | 50 m | yes | `tennis-return` | H1-2 | Tennis: return of serve |  |
| `hurdles-freestanding` | H1-2 | 50 m hurdles, free-standing hurdles |  | `tennis-serve` | H1-2 | Tennis: serve | yes |
| `shuttle-run` | G1 | 4 x 10 m shuttle run |  | `badminton-serve` | G1 | Badminton: singles service |  |
| `slalom` | G1 | Illinois agility test |  | `table-tennis-return` | G1 | Table tennis: return a service |  |
| `high-jump` | H1-2 | High jump |  | `paddle-bounce` | G1 | Table tennis: keep the ball bouncing on a paddle | yes |
| `long-jump` | G1 | Long jump |  | `golf-putt` | G1 | Golf: a 3 m putt | yes |
| `standing-long-jump` | G1 | Standing long jump |  | `javelin` | H1-2 | Athletics: javelin throw |  |
| `triple-jump` | G1 | Triple jump |  | `shot-put` | H1-2 | Athletics: shot put |  |
| `vertical-jump` | G1 | Vertical jump (jump and reach) |  | `discus` | H1-2 | Athletics: discus throw |  |
| `jump-rope` | G1 | Rope skipping (one minute) |  | `pitch-target` | H1-2 | Baseball: pitch a strike |  |
| `long-rope` | G1 | Long rope (jumping a rope turned by two turners) | yes | `bowling` | H1-2 | Ten-pin bowling: a strike |  |
| `pole-vault` | G1 | Pole vault |  | `catch` | H1-2 | Baseball: catch a fly ball |  |
| `alpine-slalom` | G1 | Alpine skiing: slalom |  | `juggle-three` | G1 | Juggling: a three-ball cascade |  |
| `giant-slalom` | G1 | Alpine skiing: giant slalom |  | `wall-ball` | H1-2 | Wall ball: throw, rebound, catch |  |
| `freeski-360` | G1 | Freeski big air: 360 spin |  | `boxing` | H1-2 | Boxing: one clean punch on the heavy bag | yes |
| `snowboard` | G1 | Snowboard: parallel slalom |  | `kick-target` | H1-2 | Kick the heavy bag at trunk height |  |
| `freeski-straight-air` | G1 | Freeski big air: straight air |  | `taekwondo-kick` | G1 | Taekwondo: a scoring kick to the trunk protector |  |
| `double-dutch` | G1 | Double Dutch (enter two turning ropes and jump them) |  | `dodgeball` | G1 | Dodgeball: dodge five throws | yes |
| `penalty-kick` | G1 | Football: penalty kick |  | `sumo` | G1 | Sumo (one bout against a pushing robot) | yes |
| `dribble-slalom` | G1 | Football: slalom dribble |  | `balance-beam` | G1 | Balance beam |  |
| `trap-ball` | H1-2 | Football: trap a pass |  | `steeplechase` | H1-2 | Steeplechase: the water jump |  |
| `volley-shot` | H1-2 | Football: volley shot |  | `box-jump` | H1-2 | Box jump |  |
| `juggling` | G1 | Football: keepie-uppie |  | `vault` | H1-2 | Vault |  |
| `juggling-feet` | G1 | Football: keepie-uppie with the feet |  | `backflip` | G1 | Backflip |  |
| `juggling-head` | G1 | Football: head juggling |  | `crawl` | G1 | Low-wire crawl |  |
| `header` | H1-2 | Football: header |  | `high-bar-swing` | G1 | High bar: jump to the bar and giant swing |  |
| `volleyball-bump` | H1-2 | Volleyball: serve receive | yes | `toes-to-bar` | G1 | High bar: toes-to-bar | yes |
| `volleyball-set` | H1-2 | Volleyball: set |  | `clean-and-jerk` | H1-2 | Weightlifting: clean and jerk | yes |
| `volleyball-serve` | H1-2 | Volleyball: serve | yes | `balance-board` | G1 | Balance board |  |
| `volleyball-spike` | H1-2 | Volleyball: spike |  | `platform-10m` | G1 | 10 m platform: forward dive straight (101A) | yes |
| `rugby-conversion` | G1 | Rugby: conversion kick over the crossbar | yes | `springboard-3m` | G1 | 3 m springboard: forward dive straight (101A) | yes |
| `free-kick-wall` | G1 | Football: direct free kick over or around the wall |  | `trampoline` | G1 | Trampoline: tuck jump and stop | yes |
| `goalkeeper-save` | H1-2 | Football: goalkeeper, save three penalties | yes | `handstand` | G1 | Handstand |  |
| `first-time-shot` | G1 | Football: first-time shot | yes | `round-off` | G1 | Round-off |  |
| `free-throw` | H1-2 | Basketball: free throw |  | `breaking-windmill` | G1 | Breaking: windmills |  |
| `catch-and-shoot` | H1-2 | Basketball: catch and shoot |  | `sled-push` | H1-2 | Sled push: one 12.5 m length on turf |  |
| `layup` | H1-2 | Basketball: layup |  | `skateboard-ollie` | G1 | Skateboard ollie |  |
| `dunk` | H1-2 | Basketball: two-hand dunk, lowered ring |  | `inline-slalom` | G1 | Inline speed slalom |  |
| `dunk-between-legs` | H1-2 | Basketball: between-the-legs dribble and dunk |  | `sweeper-jump` | G1 | Sweeper jump (jumping the boom of a Meltdown sweeper) | yes |
| `basketball-dribble` | H1-2 | Basketball: dribble to the frontcourt |  |  |  |  |  |

## Tasks exported by Embodied Olympics

The matches Embodied Olympics exports with its own service (PROTOCOL §3), listed in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`, and their standard and privileged twins are the benchmark
[Embodied Olympics - Match](../embodied-olympics-match/README.md) (task prefix `embodied-olympics-match-`).

## Licences

This benchmark's code: MIT. Embodied Olympics (robot library, running policy port, freeski course and ski-snow model):
MIT. Unitree G1 model with the Dex3-1 hands: MuJoCo Menagerie, BSD-3-Clause. H1-2 model and Unitree's walking policy
(unitree_rl_gym): BSD-3-Clause. Running policy (C1801SYQ/g1_running): Apache-2.0. FALCON (LeCAR-Lab): MIT. WBC-AGILE
(NVIDIA): Apache-2.0. Licence files sit next to their files in the image (`images/embodied-olympics-fun/roboolympics/SOURCE.md`).
