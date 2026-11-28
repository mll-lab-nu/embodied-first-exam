# MetaWorld+ · stick-push (standard)

| | |
|---|---|
| Task ID | `metaworldplus-stick-push-i00-standard` |
| Benchmark | [Meta-World](https://github.com/Farama-Foundation/Metaworld) (McLean et al., 2025), upstream `Farama-Foundation/Metaworld@59fc34d` |
| Robot | Rethink Robotics Sawyer arm with a two-finger gripper |
| Mode | standard |
| Instance | `metaworld/stick-push`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Use the stick to push the thermos to the target. At the end, still hold the stick, lifted off the table.

## Success criteria
The thermos (the point 9 cm in +y from its handle, site `insertion`) is within 12 cm of the target point AND the stick
is still held and lifted: both finger pads touch the stick with a positive contact force, the gripper is not fully
shut (its opening is above 0), and the stick's centre is more than 1 cm above the height it started at. A thermos that
is at the target after the stick has been let go does not count.

The check is Meta-World's own success test for `stick-push-v3` (`evaluate_state`, its `success` value), applied to one
state: the live simulator's state after the last executed control step of the one episode; nothing is replayed. The
episode ends when the agent sends `/finish`, or when the agent's session ends (at the latest after 30 min); there is
no reset, no step limit and no other termination. Meeting the condition earlier in the episode does not count, and the
service never reports success while the episode runs. The target point is `meta["task"]["target_pos"]`; distances are
straight-line distances in metres in the world frame unless the axes compared are named.

An episode ended by a simulator error (actions that make the simulation unstable) scores 0. The scene is checked to
start at the frozen instance (instance and starting-state hashes) before the agent is served; a mismatch is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
Meta-World ([Farama-Foundation/Metaworld](https://github.com/Farama-Foundation/Metaworld) @ `59fc34d`) is released
under the [MIT License](https://github.com/Farama-Foundation/Metaworld/blob/59fc34d7768af9785e4688c3e1db671424f4a6c3/LICENSE)
(Copyright (c) 2019 Meta-World Team). The Sawyer robot and object models (MuJoCo XML and meshes) used here ship in that
repository under the same license; no non-commercial terms apply. The simulator is MuJoCo 3.3.0 (Apache License 2.0).
Meta-World's scripted policies (`metaworld/policies/`) are not part of the task image.
