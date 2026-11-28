# RoboCasa365 · TurnOnToasterOven (realtime)

| | |
|---|---|
| Task ID | `robocasa365-turn-on-toaster-oven-i00-realtime` |
| Benchmark | [RoboCasa365](https://github.com/robocasa/robocasa) (Nasiriany et al., 2026), upstream `robocasa/robocasa@4f8a298` |
| Robot | Franka Panda arm on an Omron mobile base with a torso lift (PandaOmron), parallel-jaw gripper |
| Mode | realtime, slowdown 2 |
| Instance | `robocasa365/TurnOnToasterOven`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Turn on the toaster oven by setting its timer.

## Success criteria
The toaster oven's timer knob is turned at least 10% of its range (its hinge, travel 0 to 4.01 rad, at 0.40 rad or
more), as the oven's state update reads it after the control step.

The environment's check runs three times per control step: once inside the environment's step, before the fixtures
update their state, and twice after it.

Graded is the one live episode, judged by the simulator service on its own state; nothing is replayed. The clock does
not stop: the episode starts paused at the frozen start, and from the agent's first `submit` one control step runs
every 0.05 s × S of wall time (slowdown S = 2), whether or not the agent sends anything; when the planned
commands run out the last one is held. There is no reset. The episode ends at the agent's `/finish`, after 3,000
control steps (150 s of robot time), or when the agent's time (1 h) is up, and is judged on the state it ends
in: the check's result after the last control step must be a success, and the check must not have held at the
episode's start. A success earlier in the episode neither ends it nor is shown to the agent. After the agent's first
command, a simulator error or repeated simulator crashes inside control steps are the agent's 0; a failure before the
first command, a killed service, a failed resume, a start that is not the frozen instance's state or a missing
verdict is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 6 | 14 GiB | 8192 | no GPU | — |
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
