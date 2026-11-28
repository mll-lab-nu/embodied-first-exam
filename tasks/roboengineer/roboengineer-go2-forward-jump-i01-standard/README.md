# roboEngineer · go2-forward-jump (standard)

| | |
|---|---|
| Task ID | `roboengineer-go2-forward-jump-i01-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | Unitree Go2 quadruped |
| Mode | standard |
| Instance | `roboengineer/go2-forward-jump`, seed 1 |
| Time limit | 4 h |
| Reference solution | None |

## Task
Make the Go2 jump straight ahead the commanded distance in one real jump and land steadily.

## Success criteria
There are 10 held-out cases. Each is a 6 s episode with a commanded forward distance between 0.70 and 1.00 m. A flight
is a stretch after 1 s in which no part of the robot touches the ground; it counts when it lasts at least 0.08 s and the
base rises at least 0.07 m during it, and the longest such flight is graded. A case succeeds when there is such a flight,
the base moves forward by at least 70 % of the commanded distance during it, the base's forward travel from the start
is within 0.15 m of the commanded distance both at touchdown and at the end of the episode, the sideways offset at the
end is below 0.15 m, and at every step of the last second at least three feet touch the ground, the base's speed is
below 0.25 m/s, its angular speed below 0.35 rad/s and its roll and pitch below 0.22 rad. The case fails if at any step a
part of the robot other than a foot touches the ground, the base drops below 0.12 m, or the roll or pitch exceeds 1.1
rad. A policy whose `enabled` flag is false fails every case.

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
