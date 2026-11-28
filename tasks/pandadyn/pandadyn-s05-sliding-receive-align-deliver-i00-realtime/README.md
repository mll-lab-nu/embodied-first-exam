# Panda Dynamic Scenes · Sliding receive, inertial staging and moving hand-off (S05) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-s05-sliding-receive-align-deliver-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | realtime, slowdown 2 |
| Instance | `s05_sliding_receive_align_deliver`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Receive the cube that slides off the lane in the tray and slide it, keeping the tray level, to the staging point in the
tray. Carry it through the two waypoints, bring the tray to the match point beside the sliding platform, moving with it,
and put the cube onto the platform.

## Success criteria
The tray is the arm's tool, 0.18 m square inside and open on its -x side; its frame's origin is the centre of its
floor. The block is a 36 mm cube. The block is on the tray when it touched the tray within the last 25 ms.

Phases, in order:
1. `source_to_tray`: after the block has touched the source lane, the block is on the tray, does not touch the lane,
   its centre is at x > 0.12 m and it moves at less than 0.05 m/s relative to the tray, for 0.10 s. Its tray-frame
   position at that moment is recorded.
2. `inertial_staging`: at some moment of this phase the hand's TCP accelerates horizontally at more than 0.54 m/s², and
   the block has slid more than 25 mm (horizontally, tray frame) from its recorded position; then the block is on the
   tray, its centre within 14 mm of the staging point (0.03, 0) of the tray frame, moving at less than 0.045 m/s
   relative to the tray, for 0.3 s. The tray tilted more than 2.1° from level during this phase fails the task.
3. `transport_turn`: with the block on the tray, the tray's origin comes within 22 mm of waypoint A (0.08, 0.13,
   0.22), and later within 22 mm of waypoint B (0.19, 0.20, 0.22).
4. `match_receiver`: with the block on the tray, the tray's origin is within 12 mm of the point 0.34 m along +x and 8
   mm above the sliding platform's origin, and the tray's velocity differs from the platform's by less than 0.05 m/s.
   The platform slides at up to 0.04 m/s.
5. `support_transfer`: the block touches the platform, is not on the tray, its centre is within 70 mm of the platform's
   origin in x and in y, and it moves at less than 0.045 m/s relative to the platform, for 0.5 s.

Task failure: during phases 2 to 4, the block's centre more than 15 mm below the tray floor or more than 0.11 m from
its centre in x or y (tray frame).
Allowed contacts: the tray may touch the block; no other robot part may touch anything.
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
