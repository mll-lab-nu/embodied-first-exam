# Panda Dynamic Scenes · Moving fixture unlock (D11) (standard)

| | |
|---|---|
| Task ID | `pandadyn-d11-moving-fixture-unlock-i00-standard` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | standard |
| Instance | `d11_moving_fixture_unlock`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Grip the fixture with the left hand and lift it off its stand. While it is still moving, push the right arm's peg into
the socket; then press the latch button down until the gate opens and pull the peg out; then let the ball run out of the
outlet into the top of the chute and down into the basin.

## Success criteria
panda-0 has no tool (its bare hand); the peg is panda-1's tool, its tip 0.07 m below its frame. The left gripper grips
the fixture when both of its fingers touch the fixture's body (impulse above 1e-7 N s in that physics step). The peg's
depth is how far its tip is below the socket's mouth: 0.09 m minus the tip's height in the fixture's frame. The ball's
radius r is 16 mm.

Phases, in order:
1. `moving_fixture_presentation`: the fixture is gripped, its origin more than 18 mm from its start (0.02, 0, 0.26) and
   moving faster than 5 mm/s.
2. `relative_pin_insertion`: the fixture is gripped and moves faster than 3 mm/s, and the peg's tip is within 5 mm of
   the socket's axis (fixture-frame point (0.020, 0.065) horizontally) at a depth of 10 to 35 mm, for 0.06 s.
3. `mechanical_latch_open`: the latch is pressed down more than 17 mm while the peg touches it.
4. `follow_and_withdraw`: the peg's tip is more than 15 mm above the socket's mouth, the peg does not touch the latch,
   and the fixture is gripped.
5. `gravity_delivery`: the ball touches the chute in this phase, after it has left the fixture; after that it is
   contained in the basin (inner half-width 0.06 m, wall height 0.04 m), for 0.7 s.

The outlet check, once, the first moment the ball leaves the fixture (in the fixture's frame its centre passes x =
0.035 m through the outlet, or leaves the fixture otherwise): it must have left through the outlet, and the outlet
point (fixture frame (0.03, 0, 0)) must lie, relative to the chute's upper end (0.15, 0.13, 0.205), 0 to 60 mm down
along the chute, within 8 mm across it and 0 to 70 mm above the chute's floor plane, with the fixture's x axis within
15° of the chute's horizontal direction; otherwise the task fails.
Contained in a receptacle of inner half-width h and wall height H: in the receptacle's frame (origin at the centre of
its floor), the ball's centre is less than h - 0.45 r from the centre in x and in y and between r - 4 mm and H - 0.12 r
above the floor, the ball touched the receptacle within the last 25 ms, and its speed relative to the receptacle is
below 0.09 m/s.

Task failures: the outlet check above; the fixture's origin below z = 0.18 m at any time.
Allowed contacts: the left fingers may touch the fixture's body and the ball, not the latch; the peg may touch the
fixture's body, the latch and the ball; no other robot part may touch anything.
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
