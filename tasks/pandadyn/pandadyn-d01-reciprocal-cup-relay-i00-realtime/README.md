# Panda Dynamic Scenes · Reciprocal two-cup air relay (D01) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-d01-reciprocal-cup-relay-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | realtime, slowdown 3 |
| Instance | `d01_reciprocal_cup_relay`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Catch the falling ball in the left cup and throw it high through the air to the right cup, which must be moving as it
catches it. Carry it with the right cup to the second transfer point and throw it back from there; catch it again in the
left cup and drop it into the sliding cart while the cart is moving.

## Success criteria
The left cup is panda-0's tool and the right cup panda-1's; each cup is 0.12 m square inside with 28 mm walls, and its
frame has its origin at the centre of its floor's top surface. The ball's radius r is 18 mm.

Phases, in order:
1. `left_initial_catch`: the left cup catches the ball.
2. `left_to_right_flight`: the ball is free of all contact for more than 45 ms with its centre above z = 0.30 m.
3. `right_catch`: the right cup catches the ball, and the right cup's frame is more than 4 cm from where it started.
   If the catch holds while the right cup's horizontal speed, taken when the ball entered it, was below 0.15 m/s, the
   task fails.
4. `second_region`: the right cup's frame is within 35 mm of the second transfer point (0.13, 0.15, 0.24), with the
   ball contained in the right cup.
5. `right_to_left_flight`: the ball is free of all contact for more than 45 ms with its centre above z = 0.31 m. Its
   last contact before that must have been with the right cup alone, at a ball position within 35 mm (horizontally) of
   (0.13, 0.15); otherwise the task fails.
6. `left_catch_and_deliver`: the left cup catches the ball; after that the ball is contained in the cart (inner
   half-width 0.075 m, wall height 0.06 m), the cart slides at more than 0.02 m/s and the ball does not touch the left
   cup, for 0.7 s.

A catch: after at least 25 ms without touching anything, the ball's centre passes downward through the plane r above
the cup's rim height (cup frame) while more than r inside the inner walls in x and y; after that the ball is contained
in the cup for 0.18 s. Contained in a receptacle of inner half-width h and wall height H: in the receptacle's frame
(origin at the centre of its floor), the ball's centre is less than h - 0.45 r from the centre in x and in y and
between r - 4 mm and H - 0.12 r above the floor, the ball touched the receptacle within the last 25 ms, and its speed
relative to the receptacle is below 0.09 m/s.

Allowed contacts: each cup may touch the ball; no other robot part may touch anything.
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
× S of wall time (slowdown S = 3) whether or not the agent sends anything; when the planned targets run out
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
