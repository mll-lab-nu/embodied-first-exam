# BiGym 2.0 · stack-blocks (privileged)

| | |
|---|---|
| Task ID | `bigym2-stack-blocks-i00-privileged` |
| Benchmark | [BiGym 2.0](https://github.com/swirl-uk/BiGym2) (Zhang et al., 2026), upstream `swirl-uk/BiGym2@93ad4b3` |
| Robot | Unitree G1 humanoid (29 DoF) with Dex1-1 two-finger grippers; legs and waist driven by NVIDIA's GR00T-WBC walking policy |
| Mode | privileged |
| Instance | `stack-blocks`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Move all three blocks to the other table, stack them into one tower on the green pad and let go.

## Success criteria
Success predicate (upstream `StackBlocksG1`), all at once, with the blocks taken from lowest to highest:
- the lowest block touches the green pad on the far table;
- the middle block touches the lowest, and the top block touches the middle one;
- each block's centre is at least 3 cm higher than the one below it and within 5 cm of it horizontally;
- no finger of either gripper touches any block.
Held for 1 s (50 consecutive control steps), with no fall in the episode: the pelvis tilting past about 53° or
dropping below 0.30 m makes the episode a failure without ending it.

Failures (each ends the episode at once with 0): a block touches the floor; the pelvis is more than 10 m from the
scene's origin.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: this task's name and at most
8,750 rows of finite actions, one row per 50 Hz control step (values outside the action bounds are
clipped). After the agent's session it is replayed once, open-loop, from the frozen start (`tests/instance.json`) in
a fresh process of a separate verifier container without network. The replay runs until upstream ends the episode
(the success held for 1 s, a failure above, or the horizon of 8,750 control steps, 175 s) or
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
