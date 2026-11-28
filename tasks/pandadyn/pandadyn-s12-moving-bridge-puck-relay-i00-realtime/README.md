# Panda Dynamic Scenes · Spinning bridge puck relay and goal (S12) (realtime)

| | |
|---|---|
| Task ID | `pandadyn-s12-moving-bridge-puck-relay-i00-realtime` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Franka Emika Panda (FER), one 7-joint arm with its standard two-finger hand |
| Mode | realtime, slowdown 3 |
| Instance | `s12_moving_bridge_puck_relay`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Strike the incoming puck with the paddle while it is still sliding fast, so that it slides over the turning bridge onto
the exit lane. Stop it there, then strike it again through the doorway of the swinging gate while the gate is wide open,
without touching the gate, and across the goal line in front of the backstop.

## Success criteria
The paddle is the arm's tool. The bridge is a rotating platform; the swinging gate opens and closes by itself, and q
is its opening angle. Speeds of the puck are horizontal, in the physics step before the contact.

Phases, in order:
1. `incoming_strike`: the paddle's first contact with the puck. The puck's speed must be 0.25 m/s or more; otherwise
   the task fails.
2. `physical_bridge_transfer`: after the puck has touched the bridge, it touches the exit lane while not touching the
   bridge.
3. `exit_interception`: the paddle touches the puck.
4. `second_strike`: the paddle touches the puck more than 35 ms after the first moment of this phase at which it did
   not touch it.
5. `closing_gate_goal`: the puck crosses the doorway line x = 0.37 m heading +x within 55 mm of y = 0.12 m with q at
   least 1.0 rad; after that it crosses the goal line x = 0.48 m heading +x within 45 mm of y = 0.12 m, not touching
   the paddle, with q above 0.20 rad. In this phase the puck touching the gate, crossing the doorway line with q below
   1.0 rad, or crossing the goal line without the other conditions fails the task.

A crossing: the puck's centre passes the line during one physics step.

Allowed contacts: the paddle may touch the puck; no other robot part may touch anything.
Horizon: 32 s of simulated time (3,200 control steps).

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
