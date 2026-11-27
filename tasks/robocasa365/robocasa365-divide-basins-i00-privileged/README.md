# RoboCasa365 · DivideBasins (privileged)

| | |
|---|---|
| Task ID | `robocasa365-divide-basins-i00-privileged` |
| Benchmark | [RoboCasa365](https://github.com/robocasa/robocasa) (Nasiriany et al., 2026), upstream `robocasa/robocasa@4f8a298` |
| Robot | Franka Panda arm on an Omron mobile base with a torso lift (PandaOmron), parallel-jaw gripper |
| Mode | privileged |
| Instance | `robocasa365/DivideBasins`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Move the item in the sink's left basin to the right basin, then put the cup from the counter in the left basin, and move
your hand away.

## Success criteria
The measuring cup that was in the sink's left basin is now in the right basin, and the cup is in the left basin. An
object counts as in a basin when its centre, seen from above, lies within that basin's region; its height is not
checked. The gripper's grip point is more than 25 cm from both.

In the conditions above, an object's centre is its body origin in the simulator; touching is a MuJoCo contact between the two
models' collision geoms; an object's horizontal radius is half the diagonal of its bounding box seen from above; the
gripper's grip point is the robot's end-effector site; a joint's opening is its position as a fraction of the joint's
range. The environment's check runs three times per control step (once inside the environment's step, before the
fixtures update their state, and twice after it) and once at the frozen start; counts of checks above are counts of
these runs.

The graded file is `/app/output/trajectory.npz`: an array `actions` of shape (T, 13), finite, with 1 ≤ T ≤ 3000, one
row per control step (1/20 s); each row is clipped to the controller's limits when it is executed. The verifier replays
it once, open-loop, in a fresh process from its own copy of the frozen instance, and takes the check's result on the
state after the last row; nothing earlier in the replay counts, except where the conditions above say a count or a
moment counts as it happens. It scores 1 when that result is a success and the check did not already hold at the
frozen start. A missing file scores 0, and so does an invalid one: over 8 MB, not an archive of at most 64 plain `.npy`
arrays, no `actions`, a shape other than (T, 13), a NaN or infinite value, or T outside 1 to 3000. A replay that fails
with an error (a simulator error, or the verifier's frozen instance failing its hash check) scores 0.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 20 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
The kitchen tasks, scenes and success checks are RoboCasa365's ([robocasa/robocasa](https://github.com/robocasa/robocasa)
@ `4f8a298`, robocasa 1.0.1), released under the MIT License (Copyright (c) 2026 the RoboCasa Team); the simulation
framework is [robosuite](https://github.com/ARISE-Initiative/robosuite) @ `5ce6643` (1.5.2, MIT License) on MuJoCo 3.3.1
(Apache License 2.0). RoboCasa's assets (fixtures, object meshes, textures, including the Objaverse and AI-generated
objects) are under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) as RoboCasa states (credit: RoboCasa,
robocasa.ai); no non-commercial terms apply. They are downloaded, pinned by SHA-256, when the image is built and are not
redistributed in this repository. Paper: Nasiriany et al., 2026, "RoboCasa365: A Large-Scale Simulation Framework for
Training and Benchmarking Generalist Robots", ICLR 2026.
