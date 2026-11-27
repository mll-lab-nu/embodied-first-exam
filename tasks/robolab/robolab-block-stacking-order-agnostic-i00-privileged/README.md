# RoboLab · block_stacking_order_agnostic (privileged)

| | |
|---|---|
| Task ID | `robolab-block-stacking-order-agnostic-i00-privileged` |
| Benchmark | [RoboLab](https://github.com/NVlabs/RoboLab) (Yang et al., 2026), upstream `NVlabs/RoboLab@9db0aaf` |
| Robot | Franka Emika Panda arm with a Robotiq 2F-85 gripper (RoboLab's DROID setup) |
| Mode | privileged |
| Instance | `block_stacking_order_agnostic`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Stack the red, blue, green and yellow blocks into one tower, in any order.

## Success criteria
The red, blue, green and yellow blocks (`red_block`, `blue_block`, `green_block`, `yellow_block`) form one tower, in any
order: ranked by the height of their origins, each block is on the next lower one.

A block (or cube) is on the one below it when the two touch (a contact-force component above 0.1 N) and either every
corner of the upper one's bounding box is at or above the top of the lower one's bounding box, with the upper box's
centre within the lower box's x-y extent widened by 1 cm, or every corner of the upper box is at or above the bottom of
the lower box, with the upper box's centre within the lower box's x-y extent. Bounding boxes are each body's own
bounding box, oriented with the body in its current pose. Nothing about the gripper is checked: the tower counts while
it is held.

The condition above is RoboLab's own success term for `block_stacking_order_agnostic`, evaluated after every control step. The verifier, in a
separate sandbox without network, replays `/app/output/trajectory.npz` open-loop from its own copy of the frozen start,
one row per control step (15 Hz), up to 3 times, each in a fresh process, and stops at the first replay that succeeds. A
replay succeeds as soon as the condition holds at one control step: RoboLab then ends the episode and later rows are not
executed. After the last row, the last row is held for 30 more control steps (2 s) and the condition is still checked at
each of them. The task passes if any replay succeeds.

A missing file scores 0, and so does an invalid one: not an `.npz` archive, no `task` or `actions` array, a `task` other
than `block_stacking_order_agnostic`, pickled or object arrays, an array larger than 100,000 × 8 numbers, `actions` not of shape (T, 8) with
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
