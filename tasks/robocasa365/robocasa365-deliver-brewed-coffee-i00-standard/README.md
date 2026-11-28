# RoboCasa365 · DeliverBrewedCoffee (standard)

| | |
|---|---|
| Task ID | `robocasa365-deliver-brewed-coffee-i00-standard` |
| Benchmark | [RoboCasa365](https://github.com/robocasa/robocasa) (Nasiriany et al., 2026), upstream `robocasa/robocasa@4f8a298` |
| Robot | Franka Panda arm on an Omron mobile base with a torso lift (PandaOmron), parallel-jaw gripper |
| Mode | standard |
| Instance | `robocasa365/DeliverBrewedCoffee`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Take the coffee from the coffee machine and put it on the dining counter next to the breakfast plate, and move your hand
away.

## Success criteria
The coffee mug and the breakfast plate both touch the dining counter (the island), with their centres at most 30 cm
apart horizontally. The gripper's grip point is more than 25 cm from the mug's centre. Neither has to stand upright.

In the conditions above, an object's centre is its body origin in the simulator; touching is a MuJoCo contact between the two
models' collision geoms; an object's horizontal radius is half the diagonal of its bounding box seen from above; the
gripper's grip point is the robot's end-effector site; a joint's opening is its position as a fraction of the joint's
range. The environment's check runs three times per control step (once inside the environment's step, before the
fixtures update their state, and twice after it) and once at the start; counts of checks above are counts of these
runs.

Graded is the one live episode, judged by the simulator service on its own state; nothing is replayed. There is no
reset and no step limit, and only control steps (the rows of an action chunk, or a hold chunk) move time. The episode
ends at the agent's `POST /finish`, or when the agent's time (1 h) is up, and the verdict is the check's result
after the last executed control step: it must be a success, and the check must not have held at the start. A success
earlier in the episode neither ends it nor is shown to the agent. A simulator error raised while executing the agent's
call ends the episode with 0, as do more than two service crashes that all happened while serving the agent's calls.
A scene that does not start at the frozen instance (instance or start-state hash mismatch, or already solved), more
than two crashes not all inside the agent's calls, a failed resume or a missing verdict is an infrastructure error,
not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 6 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 10 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

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
