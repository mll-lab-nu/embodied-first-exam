# Panda Dynamic Scenes · Plate catch, transport and release (S02) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-s02-plate-catch-transport-release-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | realtime, slowdown 2 |
| Instance | `s02_plate_catch_transport_release`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Catch the ball on the flat plate and settle it in the middle. Carry it through the two waypoints without letting it roll
off, settle it again, and tip it into the sliding basin while the basin is moving.

## Success criteria
The plate is the arm's tool, 0.22 m square with no rim; its frame's origin is the centre of its top surface. The ball's
radius r is 18 mm. The ball is on the plate when its centre is less than 0.085 m from the plate's centre in x and in y
and 14 to 33 mm above the surface (plate frame), and it touched the plate within the last 25 ms.

Phases, in order:
1. `airborne_plate_catch`: the ball touches the plate, after it has been free of all contact for more than 50 ms at
   some moment of this phase.
2. `recenter`: the ball is on the plate within 35 mm of its centre horizontally (plate frame), moving at less than
   0.08 m/s relative to the plate, for 0.3 s.
3. `turning_transport`: with the ball on the plate, the plate's origin comes within 25 mm of waypoint A (0.0, 0.08,
   0.27), and later within 25 mm of waypoint B (0.18, 0.13, 0.25).
4. `rolling_recovery`: as phase 2 with a relative speed below 0.04 m/s, for 0.4 s.
5. `moving_basin_release`: the ball is contained in the basin (inner half-width 0.075 m, wall height 0.06 m), does not
   touch the plate, and the basin slides at more than 0.02 m/s, for 0.7 s.

Contained in a receptacle of inner half-width h and wall height H: in the receptacle's frame (origin at the centre of
its floor), the ball's centre is less than h - 0.45 r from the centre in x and in y and between r - 4 mm and H - 0.12 r
above the floor, the ball touched the receptacle within the last 25 ms, and its speed relative to the receptacle is
below 0.09 m/s.

Task failure: during phases 2 to 4, the ball's centre more than 0.11 m from the plate's centre in x or y, or more than
10 mm below its surface (plate frame).
Allowed contacts: the plate may touch the ball; no other robot part may touch anything.
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
  or a non-finite object position.

Graded: the live episode, judged by the simulator service as it runs; nothing is replayed. The clock does not stop: an
episode starts paused at the frozen start, and from the agent's first `submit` one 10 ms control step runs every 10 ms
× S of wall time (slowdown S = 2) whether or not the agent sends anything; when the planned targets run out
the last ones are held. The task is judged as an event: once the last phase is complete at some control step with no
failure recorded by then, the episode is a success, even if a failure above ends it afterwards; a failure before that
scores 0. Completing the task neither ends the episode nor is shown to the agent. Otherwise the episode ends at the
agent's `/finish`, at the task's horizon (whether or not every phase is done by then), after 4,500 control steps, or
when the agent's time (1 h) runs out, and it is a success only if the task was completed by then. The agent has
3 resets, each starting a new, paused episode from the frozen start; only the last episode (the one after the
last reset) is graded. After the agent's first command, a simulator error or a simulator crash inside a control step
is the agent's 0; anything before the first command, a killed service, a failed resume or a reset that does not
rebuild the scene is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 12 GiB | 1024 | 3 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## License
Panda Dynamic Scenes is an original suite of Embodied First Exam. Its environment package (`images/pandadyn/panda_dynamics/`) is released
with this repository under the repository's MIT License. The simulation stack in the image: ManiSkill 3 and its Franka
Panda model (Apache License 2.0), SAPIEN (MIT), Ruckig community version (MIT), PyTorch (BSD 3-Clause). No
non-commercial terms apply.
