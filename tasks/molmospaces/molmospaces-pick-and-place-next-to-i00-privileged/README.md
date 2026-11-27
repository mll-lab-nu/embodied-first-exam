# MolmoSpaces · pick-and-place-next-to (privileged)

| | |
|---|---|
| Task ID | `molmospaces-pick-and-place-next-to-i00-privileged` |
| Benchmark | [MolmoSpaces](https://github.com/allenai/molmospaces) (Kim et al., 2026), upstream `allenai/molmospaces@7351388` |
| Robot | Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) |
| Mode | privileged |
| Instance | `pick-and-place-next-to`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put the black rail mount down right beside the bread, almost touching it.

## Success criteria
Success check (upstream `PickAndPlaceNextToTask`), all at once:
- the gap between the black rail mount and the bread, measured in the horizontal plane between their axis-aligned
  bounding boxes, is at most 6 cm (overlapping boxes count as no gap);
- the rail mount and the bread rest on the same supporting body;
- the bread is at most 15 cm from where it started and rotated by at most 60° in total.
Whether the robot still touches the rail mount is not checked.

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: at most 100,000 rows of finite
joint targets, one row per control step. After the agent's session it is replayed once, open-loop, from the frozen
episode (`tests/instance.json`) in a fresh process of a separate verifier container without network. The replay
runs the rows in order and ends at the last row or at the episode's horizon (455 control steps,
30 s), whichever comes first; rows after the horizon never run. The task is passed if upstream's success check holds on the state the replay ends in; a success
reached earlier and then undone does not count. A missing file, a file for another task, or one that is not such an
array scores 0. A replay that crashes or times out, or a frozen start that does not rebuild, is reported as
`grader_error` (infrastructure), not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 7 | 20 GiB | 2048 | 7 GiB | 10 GiB |
| verifier | 4 | 16 GiB | no cap | 7 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).

## License
MolmoSpaces ([allenai/molmospaces](https://github.com/allenai/molmospaces), molmo-spaces 0.2.9, tag `v0.2.9` @
`7351388`) is released under the Apache License 2.0 (Allen Institute for Artificial Intelligence). Assets: the scenes
and AI2-THOR objects are CC BY 4.0; Objaverse objects are ODC-BY 1.0, each also under its creator's CC BY, CC BY-SA or
CC0 licence, listed with its attribution in the image's `/opt/molmospaces/ATTRIBUTION.md`. The image build refuses
any asset with non-commercial terms, so no non-commercial terms apply. The simulator is MuJoCo 3.5.0 (Apache License
2.0).
