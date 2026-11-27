# roboEngineer · go2-weave (standard)

| | |
|---|---|
| Task ID | `roboengineer-go2-weave-i01-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Unitree Go2 quadruped |
| Mode | standard |
| Instance | `roboengineer/go2-weave`, seed 1 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Make the Go2 weave forward past the four poles ahead, passing to the left of the first, to the right of the next and so
on, without touching any or falling.

## Success criteria
There are 10 held-out cases. Each is a 20 s episode with four poles on the line y = 0, at x = 0.9, 1.9, 2.9 and 3.9 m;
the Go2 starts at the origin facing +x. The base must pass each pole's x position in order, at least 0.16 m to its left
(+y) for the first pole, to its right for the second, and so on, alternating. A crossing on the wrong side or closer
than 0.16 m does not count for that pole. At the end of the episode the base must be more than 0.35 m past the last
pole (x above 4.25 m). The case fails if at any step a pole touches the robot, a part of the robot other than a foot
touches the ground, the base drops below 0.12 m, or the roll or pitch exceeds 1.1 rad. A policy whose `enabled` flag is
false fails every case.

The evaluator grades one policy: the deployment round the agent sealed or, without a seal, the latest round that
completed before the agent's session ended (at the latest after 4 h). A round still running at that moment is
not graded, and with no completed round the score is 0. The evaluator runs that policy on every held-out case, each in
two fresh processes without rendering; the two runs must give the same state hash, metrics and noisy observations. The
task succeeds when every held-out case succeeds. `final_reward` is the mean case score (0 to 100); it does not decide
success. A case in which the simulation diverges fails. A failure of the evaluator itself (a missing or mismatched
asset or instance, a worker crash, two runs that disagree) is an infrastructure error, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 6 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | no GPU | — |
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
