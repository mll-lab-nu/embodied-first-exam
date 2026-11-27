# Panda Dynamic Scenes · Spring gate switchyard (D07) (privileged)

| | |
|---|---|
| Task ID | `pandadyn-d07-spring-gate-switchyard-i00-privileged` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | privileged |
| Instance | `d07_spring_gate_switchyard`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hold the gate by its handle with the left gripper, swing it open toward the right arm and keep holding it open. Hit the
puck deep into the pen with the right paddle; while it runs round, swing the gate over the other way, toward the left
arm, so that it stands open that way when the puck hits the side rail on the left arm's left. Then intercept the puck
with the right paddle and send it across the goal line in front of the middle of the backstop.

## Success criteria
panda-0 has no tool (its bare hand); the paddle is panda-1's tool. q is the spring gate's hinge angle: q > 0 opens it
toward the right arm, q < 0 toward the left arm. The gate is held when both left fingers touch the gate and, in that
physics step, each of them presses (impulse above 1e-7 N s) at contact points on the handle: inside the handle's box
(centre (0, -0.13, 0.07) in the gate's frame, half sizes 16 x 12 x 12 mm) grown by 2 mm. The hold is checked only at
the moments named below.

Phases, in order:
1. `left_gate_open`: the gate is held with q > 0.5 rad.
2. `right_loop_shot`: the paddle touches the puck while the gate is held with |q| > 0.3 rad; later the puck's centre is
   at x < -0.05 m, not touching the paddle, while the gate is held with |q| > 0.3 rad.
3. `gate_reconfiguration`: the puck touches the upper rail (along x at y = 0.23 m) while the gate is held with q <
   -0.35 rad.
4. `return_interception`: the paddle touches the puck while the gate is held with |q| > 0.3 rad.
5. `final_gate_shot`: the puck crosses the goal line x = 0.43 m heading +x within 55 mm of y = 0.15 m, not touching the
   paddle, while the gate is held with |q| > 0.3 rad.

A crossing: the puck's centre passes the line during one physics step.

Allowed contacts: the left fingers may touch the puck and the gate's swinging leaf (handle included), not its base; the
paddle may touch the puck; no other robot part may touch anything.
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
  or a non-finite object position;
- the task's horizon (above) reached before the last phase is complete.

Graded file: `/app/output/trajectory.npz`, as `Session.save_trajectory(...)` writes it: `task` naming this task and
`actions`, a finite array with one row per 10 ms control step (8 values per arm: 7 joint-position targets and the total
gripper aperture) and at most 4,500 rows. Each row's joint targets are clipped to the joint limits and its aperture to
[0, 0.08] m before it runs. After the agent's session the verifier replays the file once, open-loop, in a fresh process
of a separate container without network, from its own copy of the frozen instance. The replay stops at the end of the
first control step in which the task has completed or failed (later rows are never run), or when the rows run out. The
task is passed if, at that point, the last phase is complete and no failure has been recorded. A missing file, a file
for another task, a file that is not such an array, a replay that ends without completing every phase, and a simulator
error on the agent's rows (for example the servo's trajectory generator failing) score 0. A rebuilt start that does not
match the frozen instance's state hash, a replay that gives no result or runs past its time limit (300 s plus 0.1 s per
row), or any other error in the grader is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 5 | 10 GiB | 1024 | 3 GiB | 10 GiB |
| verifier | 4 | 8 GiB | no cap | 3 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU with Vulkan (RTX 4090 / L4).

## License
Panda Dynamic Scenes is an original suite of Embodied First Exam. Its environment package (`images/pandadyn/panda_dynamics/`) is released
with this repository under the repository's MIT License. The simulation stack in the image: ManiSkill 3 and its Franka
Panda model (Apache License 2.0), SAPIEN (MIT), Ruckig community version (MIT), PyTorch (BSD 3-Clause). No
non-commercial terms apply.
