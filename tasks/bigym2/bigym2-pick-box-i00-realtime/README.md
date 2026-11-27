# BiGym 2.0 · pick-box (realtime)

| | |
|---|---|
| Task ID | `bigym2-pick-box-i00-realtime` |
| Benchmark | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Zhang et al., 2026), upstream `swirl-uk/BiGym2@93ad4b3` |
| Robot | Unitree G1 humanoid (29 DoF) with Dex1-1 two-finger grippers; legs and waist driven by NVIDIA's GR00T-WBC walking policy |
| Mode | realtime, slowdown 1 |
| Instance | `pick-box`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move the cardboard box from the side table onto the kitchen counter and let go.

## Success criteria
Success predicate (upstream `PickBoxG1`), all at once: the box touches the kitchen counter, its centre is above the
counter top and its lowest point within 3 cm of the counter top's height (it rests on top, not against a side), and
no finger of either gripper touches it. Held for 1 s (50 consecutive control steps), with no fall in the episode: the
pelvis tilting past about 53° or dropping below 0.30 m makes the episode a failure without ending it.

Failure (ends the episode at once with 0): the pelvis more than 10 m from the scene's origin.

Graded: the live episode, judged by the simulator service; nothing is replayed. The clock does not stop: an episode
starts paused at the frozen start, and from the agent's first `submit` one control step runs every 20 ms × S of wall
time (slowdown S = 1) whether or not the agent sends anything; when the planned rows run out, the last row
is held, its walking velocity included. Reaching the goal does not end the episode and is not shown to the agent. The
episode ends at the agent's `/finish`, at the horizon (4,400 control steps, 88 s of robot
time), when the agent's time (1 h) runs out, or at a failure above, which scores 0. After it ends, the robot
holds its last command, standing still, for 1 s more (50 control steps). The task is passed if at the end of that
second upstream's success predicate has held for 50 consecutive control steps and the robot has not fallen at any
time in the episode or the hold; a failure during the hold scores 0. Resets granted: 0; only the episode after
the last reset is graded. After the agent's first command, a simulator error or a simulator crash inside a control
step is the agent's 0; anything before the first command, a killed service, a failed resume or a reset that does not
rebuild the scene is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 6 GiB | 1024 | 4 GiB | — |
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
