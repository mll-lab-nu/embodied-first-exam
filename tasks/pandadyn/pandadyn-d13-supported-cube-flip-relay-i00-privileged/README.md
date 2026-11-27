# Panda Dynamic Scenes · Supported cube flip relay (D13) (privileged)

| | |
|---|---|
| Task ID | `pandadyn-d13-supported-cube-flip-relay-i00-privileged` |
| Benchmark | [Panda Dynamic Scenes](https://www.embodied-first-exam.ai/suite/pandadyn/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Two Franka Emika Panda (FER) arms, each with 7 joints and its standard two-finger hand |
| Mode | privileged |
| Instance | `d13_supported_cube_flip_relay`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Bring the tray with the cube to the presentation point and, while the tray keeps moving, tip the cube over with a short
push of the pusher, so that the face toward the right arm ends up on top. Move it on the tray to a new place, tip it
once more the same way so that its original bottom face ends up on top, and bring it to the output point.

## Success criteria
The tray is panda-0's tool, its frame's origin at the centre of its floor; the pusher is panda-1's tool. The cube (44
mm) is on the tray when it touched the tray within the last 25 ms. Its faces are named by the cube's own axes at the
start: +x faces the right arm, -z is the bottom face.

A flip about a balance axis to a target face: the pusher touches the cube, then does not touch it for more than 20 ms;
the release counts if, at the pusher's last contact, the balance axis was tilted from vertical by more than 0.03 rad
and less than π/4 - 0.02 rad, and the cube still turns faster than 0.4 rad/s; after that release the tilt passes π/4
with no pusher contact. The flip is complete when the target face points up within 0.18 rad, the cube moves slower
than 0.05 m/s and turns slower than 0.3 rad/s. A pusher contact after a counted release and before the tilt passes π/4
fails the task. From the first pusher contact of a push (after a gap of more than 20 ms) until the tilt passes π/4,
the tray must move at 0.08 m/s or faster throughout; otherwise the task fails.

Phases, in order:
1. `support_presentation`: the cube is on the tray and the tray's frame is within 25 mm of (0.08, 0.015, 0.23).
2. `first_inertial_flip`: a flip about the cube's z axis to the +x face, with the cube on the tray, held for 0.25 s.
3. `second_contact_geometry`: the cube is on the tray, more than 25 mm from where it was when phase 2 completed, and
   does not touch the pusher.
4. `second_inertial_flip`: a flip about the cube's x axis to the -z face, with the cube on the tray, held for 0.25 s.
5. `oriented_output`: the cube is on the tray with its -z face up within 0.18 rad, the tray's frame within 25 mm of
   (-0.04, 0.16, 0.25), and the cube moves at less than 0.04 m/s relative to the tray, for 0.5 s.

Task failures: the flip rules above; the cube's centre 0.115 m or more from the tray's centre in x or y, or 10 mm or
more below the tray floor (tray frame), at any time.
Allowed contacts: the tray and the pusher may touch the cube; no other robot part may touch anything.
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
