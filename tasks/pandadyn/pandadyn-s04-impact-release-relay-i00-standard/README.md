# Panda Dynamic Scenes · Impact release, interception and passage relay (S04) (standard)

| | |
|---|---|
| Task ID | `pandadyn-s04-impact-release-relay-i00-standard` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | standard |
| Instance | `s04_impact_release_relay`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Strike the sliding block with the paddle so that it hits the gate's latch and releases the ball on the chute. Once the
ball has left the chute, hit it through the passage between the two walls, then touch it again and stop it in the target
zone beyond the passage.

## Success criteria
The paddle is the arm's tool. The cue is the sliding block; the ball (radius 18 mm) rests behind the latch gate at the
top of the chute. The latch turns about a pivot at (-0.185, 0, 0.17); q is its angle.

Phases, in order:
1. `cue_strike`: the paddle touches the cue.
2. `mechanical_unlatch`: the cue hits the latch; then the latch opens beyond |q| = 0.45 rad while the ball's centre is
   at x > -0.165 m; and, within 1.0 s of the cue's first hit on the latch, the ball's centre is more than 0.125 m × sin
   |q| + 24 mm beyond the pivot in x, moving down the chute at 0.4 m/s or faster. If the 1.0 s passes first, the task
   fails.
3. `payload_interception`: after the ball has touched the chute in this phase, the paddle touches the ball while its
   centre is at x > 0.10 m.
4. `passage_redirection`: the ball, not touching the paddle, is more than 0.105 m into the passage between the two
   walls and within 45 mm of the passage's centre line, measured from the passage entry (0.285, -0.163) along the
   direction (0.551, -0.835).
5. `payload_braking`: after the paddle has touched the ball in this phase, the ball's centre is within 50 mm of the
   target (0.399, -0.345) horizontally, the ball moves slower than 0.035 m/s and touches the table, for 0.5 s.

Task failure: the paddle touching the latch at any time.
Allowed contacts: the paddle may touch the cue and the ball; no other robot part may touch anything.
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
