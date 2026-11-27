# Panda Dynamic Scenes · Cylinder rescue, guide route and oriented delivery (S11) (standard)

| | |
|---|---|
| Task ID | `pandadyn-s11-cylinder-rescue-route-deliver-i00-standard` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | standard |
| Instance | `s11_cylinder_rescue_route_deliver`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Catch the rolling cylinder in the tray as it comes off the lane and settle it lying left to right. Put it into the guide
channel near its entry, let it run out past the far end by itself, catch it again in the tray, and lay it, still left to
right, into the sliding pocket while the pocket is moving.

## Success criteria
The receiver tray is the arm's tool, 0.14 m square inside with 30 mm walls and open on its -x side; its frame's origin
is the centre of its floor's top surface. The cylinder (radius 19 mm) is held when it touched the tray within the last
25 ms and its centre is less than 0.07 m from the tray's centre in x and in y and 13 to 70 mm above the floor (tray
frame). It is aligned when its long axis is within 0.2 rad of the world y axis.

Phases, in order:
1. `rolling_interception`: the cylinder is held and does not touch the source lane.
2. `axial_alignment`: the cylinder is held and aligned and moves at less than 0.06 m/s relative to the tray, for 0.3 s.
3. `guide_rail_traverse`: after the cylinder has touched the guide with its centre at x < 0.02 m, its centre is at x >
   0.24 m while it does not touch the tray.
4. `exit_reception`: the cylinder is held and aligned, does not touch the guide, and moves at less than 0.06 m/s
   relative to the tray, for 0.2 s.
5. `oriented_moving_delivery`: the cylinder touches the pocket and is not held; in the pocket's frame its centre is
   more than 16 mm above the floor, and its extent (19 mm, plus 19 mm times its axis's share in each direction) stays
   within 0.075 m of the centre in x and in y and below 63 mm above the floor; it is aligned and moves at less than
   0.06 m/s relative to the pocket; and the pocket slides at more than 0.02 m/s; for 0.7 s.

Task failure: the cylinder touching the table after phase 1 is complete.
Allowed contacts: the tray may touch the cylinder; no other robot part may touch anything.
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

Graded: the live episode, judged by the simulator service as it runs; nothing is replayed. Each row the agent sends (8
values per arm, clipped to the limits) runs as one 10 ms control step; between the agent's calls the world is frozen.
The task is judged as an event: once the last phase is complete at some control step with no failure recorded by then,
the episode is a success, even if a failure above ends it afterwards; a failure before that scores 0. Completing the
task neither ends the episode nor is shown to the agent. Otherwise the episode ends at the agent's `/finish`, at the
task's horizon (whether or not every phase is done by then), after 4,500 control steps, or when the agent's time
(1 h) runs out, and it is a success only if the task was completed by then. The agent has 3 resets, each
starting a new episode from the frozen start; only the last episode (the one after the last reset) is graded. A
simulator error raised by the agent's own call ends the episode with 0. An episode that does not start from the frozen
instance, or a service crash outside the agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | 3 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## License
Panda Dynamic Scenes is an original suite of Embodied First Exam. Its environment package (`images/pandadyn/panda_dynamics/`) is released
with this repository under the repository's MIT License. The simulation stack in the image: ManiSkill 3 and its Franka
Panda model (Apache License 2.0), SAPIEN (MIT), Ruckig community version (MIT), PyTorch (BSD 3-Clause). No
non-commercial terms apply.
