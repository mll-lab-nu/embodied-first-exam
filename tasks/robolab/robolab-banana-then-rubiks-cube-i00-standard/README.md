# RoboLab · banana_then_rubiks_cube (standard)

| | |
|---|---|
| Task ID | `robolab-banana-then-rubiks-cube-i00-standard` |
| Benchmark | [RoboLab](https://github.com/NVlabs/RoboLab) (Yang et al., 2026), upstream `NVlabs/RoboLab@9db0aaf` |
| Robot | Franka Emika Panda arm with a Robotiq 2F-85 gripper (RoboLab's DROID setup) |
| Mode | standard |
| Instance | `banana_then_rubiks_cube`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put the banana in the bowl, then the Rubik's cube.

## Success criteria
The banana (`banana`) and the Rubik's cube (`rubiks_cube`) are each in the bowl (`bowl`), touching it and released, and
the banana was put in first: the first control step at which the banana was in the bowl, touching it and released, is no
later than the first such step for the cube (the same step counts). That first step is kept for the whole episode, so
taking an object out again does not undo it.

An object is in a container when the centre of the object's convex hull lies inside the container's convex hull with its
upward-facing faces removed (faces whose outward normal has a component of at least 0.7 along the container's own up
axis): the space above the rim counts as inside, to any height, and the test moves with the container when it tips. Two
bodies touch when a component of the contact force between them is above 0.1 N. Released means that neither inner finger
of the Robotiq gripper touches the object (no contact-force component above 0.1 N with either finger).

The condition above is RoboLab's own success term for `banana_then_rubiks_cube`, applied to one state: the live simulator's state at
the last control step of the one episode; nothing is replayed. The episode ends when the agent sends `/finish` or when
the agent's session ends (at the latest after 1 h). The agent's last command is then held for 30 more control
steps (2 s), and the condition is judged at the last of them. There is no reset. The service evaluates the condition
after every control step but never reports it and never ends the episode on it, so meeting the condition earlier in the
episode does not count.

The episode also ends at a technical cap of 100,000 control steps; that state is judged as it stands, with no hold. An
episode ended by a simulator error scores 0, and so does one the service gives up on after repeated crashes inside the
agent's calls. The scene is checked to start at the frozen instance (its state hash, or else every object pose and robot
joint within tolerance) before the agent is served; a mismatch, a give-up after crashes between calls or a failed resume
is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 24 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 26 GiB | 4096 | 22 GiB | — |
| verifier (as `main`) | 8 | 24 GiB | no cap | no GPU | 10 GiB |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `sim`.
- Recommended GPU: L40S 48GB / L4 24GB / RTX 4090 24GB.

## License
RoboLab ([NVlabs/RoboLab](https://github.com/NVlabs/RoboLab) @ `9db0aaf`, v0.3.1) is released under the
[Apache License 2.0](https://github.com/NVlabs/RoboLab/blob/9db0aaf09d9fe5d4f37b168320788258c7012463/LICENSE). Its bundled
assets carry their own licences
([THIRD_PARTY_NOTICES.md](https://github.com/NVlabs/RoboLab/blob/9db0aaf09d9fe5d4f37b168320788258c7012463/THIRD_PARTY_NOTICES.md)):
the scenes, fixtures, materials, robots and most object sets are **CC BY-NC-SA 4.0 (non-commercial, share-alike)**; the
YCB objects are MIT, the HOT3D objects CC BY-SA 4.0 with a non-sale restriction, the VOMP objects CC BY 4.0 and the
backgrounds CC0 1.0. The simulator is NVIDIA Isaac Sim 5.1 with Isaac Lab 2.3.2 (Isaac Lab's source is BSD-3-Clause;
Isaac Sim and the Isaac Lab wheels are NVIDIA proprietary software that may not be redistributed, so the simulator image
is built locally and never published).
