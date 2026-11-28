# RoboLab · keyboard_out_of_bin (standard)

| | |
|---|---|
| Task ID | `robolab-keyboard-out-of-bin-i00-standard` |
| Benchmark | [RoboLab](https://github.com/NVlabs/RoboLab) (Yang et al., 2026), upstream `NVlabs/RoboLab@9db0aaf` |
| Robot | Franka Emika Panda arm with a Robotiq 2F-85 gripper (RoboLab's DROID setup) |
| Mode | standard |
| Instance | `keyboard_out_of_bin`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Take the keyboard out of the grey bin and put it on the table.

## Success criteria
The keyboard (`keyboard`) is out of the grey bin (`grey_bin`), rests on the table (`table`) and is released.

An object is out of a container when the centre of the object's convex hull is not inside the container's convex hull
with its upward-facing faces removed (faces whose outward normal has a component of at least 0.7 along the container's
own up axis), so the space above the rim, to any height, still counts as inside. An object rests on a surface when the
contact force of that surface on the object is at least 0.1 N, points upward and lies within 45° of vertical. Released
means that neither inner finger of the Robotiq gripper touches the object (no contact-force component above 0.1 N with
either finger).

The condition above is RoboLab's own success term for `keyboard_out_of_bin`, applied to one state: the live simulator's state at
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
