# iSpatialGym · make the scene look like a picture (standard)

| | |
|---|---|
| Task ID | `ispatialgym-camera-relocalization-obstructed-i00-standard` |
| Benchmark | [iSpatialGym](https://github.com/kmy17518/iSpatialGym) (iSpatialGym Authors, 2026), upstream `kmy17518/iSpatialGym@fddcf75` |
| Robot | Galaxea R1 Pro mobile bimanual manipulator (holonomic wheeled base, 4-joint trunk, two 7-joint arms with parallel-jaw grippers) |
| Mode | standard |
| Instance | `camera_relocalization_obstructed`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move the robot until its head camera sees the scene as the goal image /app/goal.png shows it; its arms and grippers do
not have to match it.

## Success criteria
The robot's head camera (`robot_r1:zed_link:Camera:0`) is within 15 cm of the pose the goal image was taken from, and its
orientation is within 0.45 rad of that pose's orientation. No object is checked.

Success is iSpatialGym's own geometric success with settle-eval on, as its evaluation judges a policy run. On some
control step the conditions above have held on that step and on each of the 44 steps before it (45 consecutive control
steps, 1.5 s at 30 Hz). On that step the robot and every object named above are also at rest: over the last 45 steps
the object's root pose stayed within 2 mm and 5 mrad of where it was at the first of them, and each of its joints within
5 mrad (5 mm for a sliding joint). For the robot this covers its base pose and all its joints.

Graded is the one live episode (no reset), judged by the simulator service at every control step; nothing is replayed.
The task passes if the success above is reached at any control step of the episode. Once reached it stands, even if the
scene changes afterwards. The service never reports it and it does not end the episode.

The episode ends at the agent's `POST /finish`, when the agent's session ends, or after 1,324 control steps. At
`/finish` and at the session's end, if the success has not been reached yet, the service holds the robot's last command
with the base stopped for up to 45 control steps and stops as soon as it is reached; steps that held before count. At the
step limit the episode is judged as it stands. There is no fall rule: a robot that has tipped over does not end the
episode.

A simulator error raised by the agent's calls scores 0, and so do repeated service crashes that all happened while
serving the agent's calls. A frozen start that does not rebuild as recorded (checked before the agent is served), a crash
the episode cannot be resumed from, or a service that leaves no finalized result is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 12 | 21 GiB | 2048 | 9 GiB | — |
| verifier (as `main`) | 8 | 5 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
iSpatialGym ([kmy17518/iSpatialGym](https://github.com/kmy17518/iSpatialGym) @ `fddcf75`) and its evaluation data
(Hugging Face `kmy17518/ispatialgym-eval-data`, revision `v1.0`, which holds the goal images) are released under the MIT
License. Its BEHAVIOR-1K fork (OmniGibson and bddl) is MIT. The scenes, objects and robot assets are the BEHAVIOR Data
Bundle, under its End User License Agreement: **non-commercial academic research use only (NC)**, no redistribution;
the dataset is mounted at run time and never copied into an image or this repository. NVIDIA Isaac Sim 5.1 and
Omniverse Kit are proprietary; building the simulator image accepts NVIDIA's licence terms.
