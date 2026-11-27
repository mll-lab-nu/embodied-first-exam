# MetaWorld+ · stick-pull (standard)

| | |
|---|---|
| Task ID | `metaworldplus-stick-pull-i00-standard` |
| Benchmark | [Meta-World](https://github.com/Farama-Foundation/Metaworld) (McLean et al., 2025), upstream `Farama-Foundation/Metaworld@59fc34d` |
| Robot | Rethink Robotics Sawyer arm with a two-finger gripper |
| Mode | standard |
| Instance | `metaworld/stick-pull`, seed 1 |
| Time limit | 30 min |
| Reference solution | Included |

## Task
Hook the stick into the thermos's handle and pull the thermos to the target with it. Leave the stick in the handle.

## Success criteria
The thermos's handle (site `insertion`, the loop the stick goes into) is within 12 cm of the target point AND the stick
is still in the handle: the stick's far end (site `stick_end`) is at or beyond the handle in x, within 4 cm of it in y
and within 6 cm of it in z. A thermos that is at the target with the stick pulled out does not count; whether the
stick is held does not matter.

In this environment the success state does not persist on its own: holding still after reaching it can lose it within
10 control steps. Only the graded state counts.

The check is Meta-World's own success test for `stick-pull-v3` (`evaluate_state`, its `success` value), applied to one
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
