# Panda Dynamic Scenes · Swinging load transit and dock (S10) (privileged)

| | |
|---|---|
| Task ID | `pandadyn-s10-swinging-load-transit-dock-i00-privileged` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | privileged |
| Instance | `s10_swinging_load_transit_dock`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Grip the carrier's bar and damp the swinging pendulum. Carry it through the two waypoints without touching the obstacle
block, stop at the second and damp the swing again, then lower it slowly until the pendulum's ball rests in the dock,
still holding the bar.

## Success criteria
The arm has no tool (its bare hand). The carrier is a bar with a pendulum hanging from it (0.15 m long); the bob is the
pendulum's lower end point. The bar is gripped when both fingers touch it (impulse above 1e-7 N s in that physics
step). The swing is settled when the pendulum is within 0.07 rad of hanging straight down and turns slower than 0.18
rad/s. Speeds of the bar and the bob are their mean speeds over the last 50 ms.

Phases, in order:
1. `grasp_settle_and_damp`: the bar is gripped and the swing settled, for 0.35 s.
2. `obstacle_transit`: the bar is gripped, its centre within 35 mm of waypoint A (-0.05, 0.04, 0.38).
3. `turn_and_brake`: the bar is gripped, its centre within 35 mm of waypoint B (0.0, 0.15, 0.37), moving slower than
   0.025 m/s, for 0.2 s.
4. `residual_swing_cancel`: the bar is gripped and the swing settled, for 0.5 s.
5. `load_dock`: the bar is gripped, the swing settled, the pendulum touched the dock within the last 10 ms, and the bob
   is at z = 0.037 ± 0.003 m and within 35 mm of (0.07, 0.19) horizontally, for 0.5 s.

Task failures: before the task is complete, the bob moving faster than 0.05 m/s while it is within 0.079 m (x) and
0.077 m (y) of the dock's centre (0.07, 0.19) with its lowest point below z = 0.07 m; the carrier or the pendulum
touching the obstacle block; the bar's centre below z = 0.16 m.
Allowed contacts: the fingers may touch the carrier bar; no other robot part may touch anything (the pendulum
included).
Horizon: 25 s of simulated time (2,500 control steps).

Phases count only in order: each phase's condition is checked after every 1 ms physics step, and only once the phase
before it is complete. A condition "for t s" must hold at every physics step over t s; a break restarts it. Positions
are in the world frame (metres, z up, the table top is the plane z = 0); "horizontally" means in x and y.

Failures shared by every task (each ends the episode at once, in any phase):
- a forbidden contact: two arms touching each other (tools included); an arm touching itself, except its two fingers
  touching each other (a finger touching the arm's own tool counts); any robot part, tool included, touching anything
  the allowed contacts above do not list (the table, the floor and the arm pedestals included); any contact in the
  scene that penetrates deeper than 4 mm;
- a violation of the Franka Panda's safety limits by an arm, checked at every physics step: a joint more than 0.002 rad
  beyond its position limits; measured joint speeds above 101 % of the limits (2.175 rad/s for joints 1-4, 2.61 rad/s
  for joints 5-7); a finger faster than 0.051 m/s; the hand's TCP faster than 1.01 x 1.7 m/s or 1.01 x 2.5 rad/s,
  measured or in the servo's reference motion; a motor torque above 87 N m (joints 1-4) or 12 N m (joints 5-7), or one
  changing faster than 1000 N m/s; reference joint speeds, accelerations or jerks above the Panda's limits; measured
  joint accelerations or jerks, or measured or reference TCP accelerations (13 m/s², 25 rad/s²), averaged over 20 ms,
  above 105 % of the limits;
- an object leaving the workspace (its centre below z = -0.2 m or more than 1.8 m from the world origin horizontally),
  or a non-finite object position;
- the task's horizon (above) reached before the last phase is complete.

Graded file: `/app/output/trajectory.npz`, as `Session.save_trajectory(...)` writes it: `task` naming this task and
`actions`, a finite array with one row per 10 ms control step (8 values per arm: 7 joint-position targets and the total
gripper aperture) and at most 4,500 rows. Each row's joint targets are clipped to the joint limits and its aperture to
[0, 0.08] m before it runs. After the agent's session the verifier replays the file once, open-loop, in a fresh process
of a separate container without network, from its own copy of the frozen instance. The replay stops at the end of the
first control step in which the task has completed or failed (later rows are never run), or when the rows run out. The
task is passed if, at that point, the last phase is complete and no failure has been recorded. A missing file, a file
for another task, a file that is not such an array, a replay that ends without completing every phase, and a simulator
error on the agent's rows (for example the servo's trajectory generator failing) score 0. A rebuilt start that does not
match the frozen instance's state hash, a replay that gives no result or runs past its time limit (300 s plus 0.1 s per
row), or any other error in the grader is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 5 | 10 GiB | 1024 | 3 GiB | 10 GiB |
| verifier | 4 | 8 GiB | no cap | 3 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## License
Panda Dynamic Scenes is an original suite of Embodied First Exam. Its environment package (`images/pandadyn/panda_dynamics/`) is released
with this repository under the repository's MIT License. The simulation stack in the image: ManiSkill 3 and its Franka
Panda model (Apache License 2.0), SAPIEN (MIT), Ruckig community version (MIT), PyTorch (BSD 3-Clause). No
non-commercial terms apply.
