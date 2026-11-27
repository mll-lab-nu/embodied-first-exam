# Panda Dynamic Scenes · Reciprocal sliding transfer (D12) (privileged)

| | |
|---|---|
| Task ID | `pandadyn-d12-reciprocal-sliding-transfer-i00-privileged` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | privileged |
| Instance | `d12_reciprocal_sliding_transfer`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Without tilting the scoops, slide the cube from the left scoop onto the right scoop, which must be moving along with the
left one when the cube arrives and then stop with the cube on it. Carry it to a new place, slide it back the same way
onto the left scoop, and set it down on the output platform.

## Success criteria
The left scoop is panda-0's tool and the right scoop panda-1's; each scoop's frame has its origin at the centre of its
floor, with +x toward its open side. The block is on a scoop when it touched that scoop within the last 25 ms. When the
block comes onto a scoop, that scoop's horizontal speed and the horizontal difference between the two scoops'
velocities are recorded (its arrival).

Phases, in order:
1. `left_inertial_slip`: the block is on the left scoop and has moved more than 28 mm along the left scoop's x axis
   from its start (scoop frame).
2. `right_receive_and_brake`: the block is on the right scoop and not on the left one, within 65 mm of the right
   scoop's centre in x and y (scoop frame), moving at less than 0.05 m/s relative to it; the right scoop's arrival
   speed was at least 0.2 m/s with a velocity difference of at most 0.05 m/s; the right scoop moves slower than 0.02
   m/s; and this hold starts within 1.5 s of that arrival; for 0.3 s.
3. `reverse_geometry`: the block is on the right scoop, the right scoop's frame more than 0.06 m from where it was
   when phase 2 completed.
4. `left_receive_and_brake`: as phase 2 with the scoops' roles swapped.
5. `final_support_deposit`: the block touches the output platform, is on neither scoop, its centre within 65 mm of
   (0.18, -0.22) horizontally, and it moves slower than 0.04 m/s, for 0.5 s.

Task failures, before phase 5 starts: a scoop tilted more than 2.1° from level; the block on neither scoop for more
than 0.09 s.
Allowed contacts: each scoop may touch the block; no other robot part may touch anything.
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
