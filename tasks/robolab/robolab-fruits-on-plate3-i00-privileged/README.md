# RoboLab · fruits_on_plate3 (privileged)

| | |
|---|---|
| Task ID | `robolab-fruits-on-plate3-i00-privileged` |
| Benchmark | [RoboLab](https://github.com/NVlabs/RoboLab) (Yang et al., 2026), upstream `NVlabs/RoboLab@9db0aaf` |
| Robot | Franka Emika Panda arm with a Robotiq 2F-85 gripper (RoboLab's DROID setup) |
| Mode | privileged |
| Instance | `fruits_on_plate3`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Add fruit (not the pumpkins) to the plate until exactly 3 fruits are on it, then let go; the orange already there
counts.

## Success criteria
Exactly three of the seven fruits, no more and no fewer, each rest on the plate (`clay_plates`), are over it and are
released. The seven fruits are the lemons (`lemon_01`, `lemon_02`), the limes (`lime01`, `lime01_01`), the oranges
(`orange_01`, `orange_02`) and the pomegranate (`pomegranate01`).

An object rests on a surface when the contact force of that surface on the object is at least 0.1 N, points upward and
lies within 45° of vertical. Over a body means that the centre of the object's bounding box lies within the x-y extent
of that body's bounding box, widened by 1 cm on every side; height is not compared. Bounding boxes are each body's own
bounding box, oriented with the body in its current pose. Released means that neither inner finger of the Robotiq
gripper touches the object (no contact-force component above 0.1 N with either finger).

The condition above is RoboLab's own success term for `fruits_on_plate3`, evaluated after every control step. The verifier, in a
separate sandbox without network, replays `/app/output/trajectory.npz` open-loop from its own copy of the frozen start,
one row per control step (15 Hz), up to 3 times, each in a fresh process, and stops at the first replay that succeeds. A
replay succeeds as soon as the condition holds at one control step: RoboLab then ends the episode and later rows are not
executed. After the last row, the last row is held for 30 more control steps (2 s) and the condition is still checked at
each of them. The task passes if any replay succeeds.

A missing file scores 0, and so does an invalid one: not an `.npz` archive, no `task` or `actions` array, a `task` other
than `fruits_on_plate3`, pickled or object arrays, an array larger than 100,000 × 8 numbers, `actions` not of shape (T, 8) with
T ≤ 100,000, or a NaN or infinite value. If the rebuilt start scene does not match the frozen instance (its state hash,
or else every object pose and robot joint within tolerance), or a replay process fails or runs out of time, the trial is
an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 29 GiB | 4096 | 22 GiB | 10 GiB |
| verifier | 8 | 32 GiB | no cap | 22 GiB | no cap |

- GPU: an RTX-class NVIDIA GPU (ray-tracing cores), one of the models in `gpu_types`: L40S, L40, L4, RTX 4090, RTX 6000 Ada, RTX PRO 6000 Blackwell, held by `main`.
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
