# roboEngineer · anycar-tight-drift-park (standard)

| | |
|---|---|
| Task ID | `roboengineer-anycar-tight-drift-park-i01-standard` |
| Benchmark | [roboEngineer](https://www.embodied-first-exam.ai/suite/roboengineer/) (Wang et al., 2026), upstream `mll-lab-nu/embodied-first-exam@b2280d8` |
| Robot | AnyCar 1/10-scale racing car (contact wheels, suspension, steering) |
| Mode | standard |
| Instance | `roboengineer/anycar-tight-drift-park`, seed 1 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Drive the car round the U-bend, then drift through a half turn into the tight parking space on the inside, between the
two parked cars, and stop there.

## Success criteria
There are 10 held-out cases. Each is a 16 s episode on a U-shaped course (radius 2.2 m) that ends next to a tight parking
bay; the bay is 0.43 m wide and 0.65 to 0.73 m long, and its direction points along +x, opposite to the car's heading at
the end of the route. The state is checked every 2 ms. The route has gates; a gate counts when the car's centre comes
within 0.28 m of it, in order. After the last gate the car's heading must change in total by 180° (within 0.25 rad,
either way round), and the car must drift near the bay (within 2.5 m along x of its centre, and from 0.8 m below the
bay's centre line to 0.4 m beyond the course radius along y): one continuous slide of at least 0.15 s with sideways
speed above 0.2 m/s, speed above 0.6 m/s and a sideslip angle above 10°, at least 0.06 m of sideways slide in total,
and at least 120° of the turn made while sliding. A case succeeds when the car has done so and, for at least the last
0.5 s of the episode, the whole car is inside the bay, its centre is within 0.18 m (along the bay) and 0.12 m (across
it) of the bay's centre, its heading is within 0.14 rad of the bay's direction, its speed is below 0.08 m/s and its yaw
rate below 0.1 rad/s. The case fails if the car touches a barrier or a parked car, the chassis touches the ground, the
car tips more than 60° from upright, the car is more than 0.65 m from the route before the last gate, or it leaves the
area |x| ≤ 7 m, |y| ≤ 5 m.

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
