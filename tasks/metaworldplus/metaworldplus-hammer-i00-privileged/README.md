# MetaWorld+ · hammer (privileged)

| | |
|---|---|
| Task ID | `metaworldplus-hammer-i00-privileged` |
| Benchmark | [Meta-World](https://github.com/Farama-Foundation/Metaworld) (McLean et al., 2025), upstream `Farama-Foundation/Metaworld@59fc34d` |
| Robot | Rethink Robotics Sawyer arm with a two-finger gripper |
| Mode | privileged |
| Instance | `metaworld/hammer`, seed 0 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Use the hammer to drive the nail into the block.

## Success criteria
The nail has been driven more than 9 cm into the block (its slide joint `NailSlideJoint` is past 0.09 m). Nothing is
compared with the target point, which marks where the nail's head ends up; where the hammer ends does not matter.

The check is Meta-World's own success test for `hammer-v3` (`evaluate_state`, its `success` value), applied to one
state: the state after the last action of the delivered trajectory. The verifier, in a separate sandbox without
network, replays `/app/output/trajectory.npz` (array `actions`, shape (T, 4) with 1 ≤ T ≤ 500, values clipped to
[-1, 1]) once, open-loop, in a fresh process from its own copy of the frozen start, one action per control step.
Meeting the condition at an earlier step does not count. The target point is `target_pos` of `s.state()`; distances
are straight-line distances in metres in the world frame unless the axes compared are named.

A missing file scores 0, and so does an invalid one: not a plain `.npz` of at most 2 MB holding only arrays (at most
64 members), no `actions` array, a shape other than (T, 4), a NaN or infinite value, or T outside 1 to 500. A replay
during which the simulator becomes unstable scores 0.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 1024 | no GPU | 10 GiB |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
Meta-World ([Farama-Foundation/Metaworld](https://github.com/Farama-Foundation/Metaworld) @ `59fc34d`) is released
under the [MIT License](https://github.com/Farama-Foundation/Metaworld/blob/59fc34d7768af9785e4688c3e1db671424f4a6c3/LICENSE)
(Copyright (c) 2019 Meta-World Team). The Sawyer robot and object models (MuJoCo XML and meshes) used here ship in that
repository under the same license; no non-commercial terms apply. The simulator is MuJoCo 3.3.0 (Apache License 2.0).
Meta-World's scripted policies (`metaworld/policies/`) are not part of the task image.
