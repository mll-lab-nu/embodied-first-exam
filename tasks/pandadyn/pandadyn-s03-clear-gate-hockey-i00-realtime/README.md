# Panda Dynamic Scenes · Clear the blocker, recover and bank into the goal (S03) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-s03-clear-gate-hockey-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | realtime, slowdown 2 |
| Instance | `s03_clear_gate_hockey`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Touch the incoming puck with the paddle, then strike it into the blue blocker bar hard enough to push the bar aside. Let
the puck slide back toward you, then strike it again so that it banks off the green rail, without touching the grey one,
and crosses the goal line in front of the middle of the backstop while the bar is still pushed aside.

## Success criteria
The paddle is the arm's tool. The blocker is a bar on a rail; its rail position starts at 0. This instance's
designated rail is the green rail (along y at x = -0.14 m); the grey rail runs along x at y = -0.23 m. "Free" is the
time since the paddle's last contact with the puck.

Phases, in order:
1. `first_strike`: the paddle touches the puck.
2. `clear_blocker`: the puck hits the blocker while free for at least 0.15 s, at a horizontal speed (just before the
   hit) of 0.15 m/s or more; after that the blocker's rail position is above 0.065 m. A puck–blocker contact while free
   for less than 0.15 s fails the task.
3. `recover_deflection`: the puck's centre crosses x = 0.16 m heading -x, not touching the paddle and free for at least
   0.15 s.
4. `second_strike`: the paddle touches the puck.
5. `bank_and_goal`: since the paddle's last contact, the puck has begun a contact with the green rail while free for
   at least 0.1 s and has not touched the grey rail; it then crosses the goal line x = 0.46 m heading +x within 55 mm
   of y = 0.06 m, not touching the paddle, with the blocker's rail position above 0.065 m. A goal-line crossing in this
   phase without all of these fails the task.

A crossing: the puck's centre passes the line during one physics step.

Task failure: the paddle touching the blocker at any time.
Allowed contacts: the paddle may touch the puck; no other robot part may touch anything.
Horizon: 35 s of simulated time (3,500 control steps).

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
