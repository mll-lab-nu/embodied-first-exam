# Panda Dynamic Scenes · Moving bank relay (D06) (standard)

| | |
|---|---|
| Task ID | `pandadyn-d06-moving-bank-relay-i00-standard` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | standard |
| Instance | `d06_moving_bank_relay`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Strike the sliding puck back with the right paddle so that it returns through the gap it came through, bounces off the
moving bank board and hits the left paddle. Strike it back again so that it comes through the other gap, next to the
side rail, onto the left paddle held at a new place and angle; then send it with the left paddle back out through that
gap and across the goal line in front of the middle of the backstop.

## Success criteria
The left paddle is panda-0's tool and the right paddle panda-1's. Speeds of the puck and of the bank board are those of
the physics step before the contact.

Phases, in order:
1. `right_first_strike`: within 50 ms after a right-paddle contact made in this phase, the puck touches neither paddle,
   its centre is at x > 0.18 m and its velocity along x is -0.20 m/s or less.
2. `left_first_rebound`: the puck crosses the line x = 0.16 m heading -x within 48 mm of y = -0.01 m; then, with no
   paddle contact in between, it touches the sliding bank board while the board moves at 0.02 m/s or faster; then it
   touches the left paddle at a horizontal speed of 0.08 m/s or more. A right-paddle contact cancels the crossing. The
   left paddle's pose at that contact is recorded.
3. `right_recovery_strike`: as phase 1, more than 60 ms after phase 2 completed.
4. `left_changed_rebound`: the puck crosses x = 0.16 m heading -x within 48 mm of y = 0.16 m; then, with no
   right-paddle contact in between, it touches the left paddle at a horizontal speed of 0.08 m/s or more while the left
   paddle's frame is more than 35 mm from, and turned by more than 0.24 rad from, its recorded pose.
5. `terminal_goal`: the puck crosses x = 0.16 m heading +x within 48 mm of y = 0.16 m (a right-paddle contact cancels
   this crossing); then it crosses the goal line x = 0.42 m heading +x within 55 mm of y = 0.16 m while not touching the
   right paddle, the left paddle having touched it since phase 4 completed.

A crossing: the puck's centre passes the line during one physics step.

Allowed contacts: each paddle may touch the puck; no other robot part may touch anything.
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
