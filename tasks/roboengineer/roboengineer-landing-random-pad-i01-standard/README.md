# roboEngineer · Quadrotor landing adaptation (standard)

| | |
|---|---|
| Task ID | `roboengineer-landing-random-pad-i01-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Intel Aero quadrotor (partly calibrated) with the Neural Lander ground-effect residual |
| Mode | standard |
| Instance | `roboengineer/landing-random-pad`, seed 1 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Land the drone gently near the centre of the round pad as quickly as you safely can, and keep it there, level and still,
until the end.

## Success criteria
There are 6 held-out cases. Each is a 16 s episode: the drone starts 0.8 to 1.5 m up and lands on a round pad of radius
0.45 m on the floor, placed per case. A case succeeds when only the drone's feet touch the floor, and only inside the
pad; at the first touch the drone's vertical speed is below 0.4 m/s and its horizontal speed below 0.25 m/s; and the
drone is settled without a break for at least the last 1 s of the episode, checked every 10 ms: feet on the floor,
centre within 0.15 m (horizontally) of the pad's centre, tilt below 0.15 rad and speed below 0.08 m/s. The case fails if
another part of the drone touches the floor, a foot touches the floor outside the pad (even if the drone later slides
onto it), the tilt exceeds 0.8 rad, the drone goes more than 3 m from the origin along x or y, or it climbs above 3 m.

The evaluator grades one policy: the deployment round the agent sealed or, without a seal, the latest round that
completed before the agent's session ended (at the latest after 1 h). A round still running at that moment is
not graded, and with no completed round the score is 0. The evaluator runs that policy on every held-out case, each in
two fresh processes without rendering; the two runs must give the same state hash, metrics and noisy observations. The
task succeeds when every held-out case succeeds. `final_reward` is the mean case score (0 to 100); it does not decide
success. A case in which the simulation diverges fails. A failure of the evaluator itself (a missing or mismatched
asset or instance, a worker crash, two runs that disagree) is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
roboEngineer is an original suite of Embodied First Exam. Its components carry their own terms: AnyCar's car mechanism
([LeCAR-Lab/anycar](https://github.com/LeCAR-Lab/anycar) @ `20fc50a`, Apache License 2.0 as its README declares) and
F1DB's circuit outlines ([f1db/f1db](https://github.com/f1db/f1db) @ `7cf634e`, CC BY 4.0; `anycarbench/NOTICE`);
the Unitree G1 model and training task of [unitreerobotics/unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab)
@ `1425b15` (Apache License 2.0); MuJoCo Menagerie's Unitree Go2 (BSD 3-Clause, Unitree Robotics) and Skydio X2
(Apache License 2.0) models. The Neural Fly force fit is made from the flight logs of
[aerorobotics/neural-fly](https://github.com/aerorobotics/neural-fly) @ `0ed5024`, which are **for personal and
educational use only** (written permission from the authors is needed for further use); the fit is not distributed.
The Neural Landing residual is converted from the checkpoint of
[GuanyaShi/neural_lander_sim_1d](https://github.com/GuanyaShi/neural_lander_sim_1d) @ `30ab04c`, which states no
licence. The simulator is MuJoCo (Apache License 2.0).
