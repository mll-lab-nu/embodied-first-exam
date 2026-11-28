# Panda Dynamic Scenes · Inertial cube flip, chute run and pocket recovery (S06) (standard)

| | |
|---|---|
| Task ID | `pandadyn-s06-cube-flip-route-recover-i00-standard` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | standard |
| Instance | `s06_cube_flip_route_recover`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
With a short push of the blade, tip the cube over so that the face toward you ends up on top, the cube finishing the tip
on its own. Then push it onto the chute, let it slide down by itself, meet it with the blade near the chute's lower end,
and bring it to rest in the pocket with the same face on top.

## Success criteria
The pusher blade is the arm's tool. The cube is 44 mm wide; its faces are named by the cube's own axes at the start
(-x faces the robot). The chute runs down from (0.16, 0, 0.138) to (0.36, 0, 0.035).

A flip to the -x face: the blade touches the cube, then does not touch it for more than 20 ms; the release counts if,
at the blade's last contact, the cube's z axis was tilted from vertical by more than 0.03 rad and less than π/4 - 0.02
rad, and the cube still turns faster than 0.4 rad/s; after that release the tilt passes π/4 with no blade contact. The
flip is complete when the -x face points up within 0.18 rad, the cube moves slower than 0.05 m/s and turns slower than
0.3 rad/s. A blade contact after a counted release and before the tilt passes π/4 fails the task.

Phases, in order:
1. `momentum_face_flip`: a flip to the -x face, with the cube touching the launch surface, held for 0.25 s.
2. `oriented_chute_entry`: the cube touches the chute with its centre at x > 0.18 m and its -x face within 0.35 rad of
   the chute floor's normal.
3. `downstream_intercept`: the blade touches the cube while the cube's centre is at x > 0.32 m, the cube touches the
   chute, the blade's frame is downhill of the cube's centre along the chute, the cube has slid at least 0.12 m down the
   chute since phase 2 completed or since the blade's previous contact, and its speed down the chute (in the step
   before) is at least 0.33 m/s. Any other blade contact in this phase restarts the 0.12 m count.
4. `pocket_delivery`: the cube touches the pocket, its centre within 40 mm of (0.41, 0) horizontally, its -x face up
   within 0.18 rad, moving slower than 0.04 m/s and turning slower than 0.2 rad/s, for 0.5 s.

Task failure: the flip rule above.
Allowed contacts: the blade may touch the cube; no other robot part may touch anything.
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
