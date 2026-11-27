# Panda Dynamic Scenes · Load a coasting cart, throw the switch, recover the part (S08) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-s08-load-switch-recover-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | realtime, slowdown 6 |
| Instance | `s08_load_switch_recover`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Grasp the part from the moving conveyor, lift it about a hand's length and drop it into the coasting cart without
stopping the cart. Before the cart reaches the switch, push the switch with a finger so that it sends the cart into the
branch nearer to you, then lift the part back out of the cart and hold it up.

## Success criteria
The arm has no tool (its bare hand). The hand grips the part when both of its fingers touch it (impulse above 1e-7 N s
in that physics step). The part is a 36 mm cube; the cart rolls on ball bearings. This instance's selected branch is
the one nearer the robot (at x < 0); the switch angle q is positive toward it.

Phases, in order:
1. `moving_part_pickup`: the hand grips the part while the part moves faster than 0.025 m/s; after that, gripped, the
   part's centre is above z = 0.20 m.
2. `load_coasting_cart`: the part is not gripped, touches the cart, and the cart moves faster than 0.02 m/s.
3. `physical_switch_operation`: after a finger has touched the switch in this phase, q is above 0.50 rad and the switch
   turns slower than 0.12 rad/s, while the cart's centre is still at y < 0.105 m. Before that, a cart–switch contact or
   the cart's centre reaching y > 0.105 m fails the task.
4. `selected_branch`: the cart has touched the switch and the selected branch's rail; then the cart's centre is at y >
   0.23 m and x < -0.08 m.
5. `payload_recovery`: the part is gripped, its centre more than 0.10 m above the cart's centre, and it does not touch
   the cart, for 0.5 s. The cart's centre at |x| > 0.27 m or y > 0.43 m during this phase fails the task.

Task failures: the cart moving slower than 0.03 m/s (horizontally) for 0.1 s before phase 4 starts; the part's centre
below z = 0.018 m during phases 3 and 4.
Allowed contacts: the fingers may touch the part, the cart (chassis and bearings) and the switch's moving blade; no
other robot part may touch anything.
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
× S of wall time (slowdown S = 6) whether or not the agent sends anything; when the planned targets run out
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
