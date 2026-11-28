# BiGym 2.0 · dishwasher-load-plates (privileged)

| | |
|---|---|
| Task ID | `bigym2-dishwasher-load-plates-i00-privileged` |
| Benchmark | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Zhang et al., 2026), upstream `swirl-uk/BiGym2@93ad4b3` |
| Robot | Unitree G1 humanoid (29 DoF) with Dex1-1 two-finger grippers; legs and waist driven by NVIDIA's GR00T-WBC walking policy |
| Mode | privileged |
| Instance | `dishwasher-load-plates`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move both plates from the dish rack into the dishwasher's lower rack, standing on edge and facing left or right as seen
from where you start, and let go.

## Success criteria
Success predicate (upstream `DishwasherLoadPlatesG1`), for each of the two plates at once:
- its face points within 20° of left or of right, as seen from where the robot starts (the plate stands on edge);
- it touches the dishwasher's lower rack;
- no finger of either gripper touches it.
Held for 1 s (50 consecutive control steps), with no fall in the episode: the pelvis tilting past about 53° or
dropping below 0.30 m makes the episode a failure without ending it.

Failures (each ends the episode at once with 0): a plate touches the floor; the pelvis is more than 10 m from the
scene's origin.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name and at most
3,150 rows of finite actions, one row per 50 Hz control step (values outside the action bounds are
clipped). After the agent's session it is replayed once, open-loop, from the frozen start (`tests/instance.json`) in
a fresh process of a separate verifier container without network. The replay runs until upstream ends the episode
(the success held for 1 s, a failure above, or the horizon of 3,150 control steps, 63 s) or
the rows run out. The task is passed if, at that point, upstream's success has been held for 1 s and the robot has
not fallen at any time in the replay. Rows after the end are not run. Only the trajectory is scored (`gen.py` and
`NOTES.md` are not). A missing file, a file for another task, or one that is not such an array scores 0. A replay
that crashes or times out, or a frozen start that does not rebuild, is reported as `grader_error` (infrastructure),
not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 13 GiB | 1024 | 5 GiB | 10 GiB |
| verifier | 4 | 16 GiB | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## License
BiGym 2.0 ([swirl-uk/BiGym2](https://github.com/swirl-uk/BiGym2) @ `93ad4b3`, `bigym` 1.0.0) is released under the
Apache License 2.0. Bundled components keep their own licences: the Unitree G1 description (BSD 3-Clause) in AMO's
MuJoCo packaging (Apache License 2.0); the scene props (CC0 or CC BY 4.0, attributions in upstream's
`bigym/envs/xmls/3D_MODELS_ATTRIBUTION.md`); NVIDIA's GR00T-WBC weights, redistributed under the NVIDIA Open Model
License (upstream's `NOTICE` and `THIRD_PARTY_NOTICES.md`). The simulator is MuJoCo 3.8.1 (Apache License 2.0). No
non-commercial terms apply.
