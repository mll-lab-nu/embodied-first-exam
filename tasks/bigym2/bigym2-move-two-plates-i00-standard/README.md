# BiGym 2.0 · move-two-plates (standard)

| | |
|---|---|
| Task ID | `bigym2-move-two-plates-i00-standard` |
| Benchmark | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Zhang et al., 2026), upstream `swirl-uk/BiGym2@93ad4b3` |
| Robot | Unitree G1 humanoid (29 DoF) with Dex1-1 two-finger grippers; legs and waist driven by NVIDIA's GR00T-WBC walking policy |
| Mode | standard |
| Instance | `move-two-plates`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move both plates from the left dish rack into slots of the right dish rack, standing on edge and facing the same way as
now, clear of the table, and let go.

## Success criteria
Success predicate (upstream `MoveTwoPlatesG1`), for each of the two plates at once:
- its centre is within 5 cm of one of the slots of the right dish rack;
- its face points within 20° of the robot's right as seen from where it starts, the way the plates face at the
  start (a plate turned around does not count);
- it touches the right rack and does not touch the table;
- no finger of either gripper touches it.
Held for 1 s (50 consecutive control steps), with no fall in the episode: the pelvis tilting past about 53° or
dropping below 0.30 m makes the episode a failure without ending it.

Failures (each ends the episode at once with 0): a plate touches the floor; the pelvis is more than 10 m from the
scene's origin.

Graded: the live episode, judged by the simulator service; nothing is replayed. Reaching the goal does not end the
episode and is not shown to the agent. The episode ends at the agent's `/finish`, at the horizon (2,300
control steps, 46 s of robot time), when the agent's time (1 h) runs out, or at a failure above,
which scores 0. After it ends, the robot holds its last command, standing still, for 1 s more (50 control steps).
The task is passed if at the end of that second upstream's success predicate has held for 50 consecutive control
steps and the robot has not fallen at any time in the episode or the hold; a failure during the hold scores 0.
Resets granted: 0. A reset starts a new episode from the frozen start; only the episode after the last reset
is graded. A simulator error raised by the agent's own call ends the episode with 0. An episode that does not start
from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 6 GiB | 1024 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
BiGym 2.0 ([swirl-uk/BiGym2](https://github.com/swirl-uk/BiGym2) @ `93ad4b3`, `bigym` 1.0.0) is released under the
Apache License 2.0. Bundled components keep their own licences: the Unitree G1 description (BSD 3-Clause) in AMO's
MuJoCo packaging (Apache License 2.0); the scene props (CC0 or CC BY 4.0, attributions in upstream's
`bigym/envs/xmls/3D_MODELS_ATTRIBUTION.md`); NVIDIA's GR00T-WBC weights, redistributed under the NVIDIA Open Model
License (upstream's `NOTICE` and `THIRD_PARTY_NOTICES.md`). The simulator is MuJoCo 3.8.1 (Apache License 2.0). No
non-commercial terms apply.
