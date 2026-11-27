# MolmoSpaces · pick-and-place (privileged)

| | |
|---|---|
| Task ID | `molmospaces-pick-and-place-i00-privileged` |
| Benchmark | [MolmoSpaces](https://github.com/allenai/molmospaces) (Kim et al., 2026), upstream `allenai/molmospaces@7351388` |
| Robot | Franka FR3 arm with a Robotiq 2F-85 gripper on a fixed base (the DROID setup) |
| Mode | privileged |
| Instance | `pick-and-place`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put the purple bottle in the clear ashtray.

## Success criteria
Success check (upstream `PickAndPlaceTask`), all at once:
- the purple bottle rests in or on the clear ashtray: the ashtray carries at least half of the bottle's weight through
  their contacts, or upstream's geometric on-top test finds the bottle on it, or the bottle has stayed within 5 mm and
  10° (in the ashtray's frame) of a pose at which one of these held earlier in the episode;
- the robot does not touch the bottle;
- the ashtray is at most 15 cm from where it started and tilted by at most 60° (turning it about the vertical does not
  count).

Graded file: `/app/output/trajectory.npz`, as `s.save_trajectory(...)` writes it: at most 100,000 rows of finite
joint targets, one row per control step. After the agent's session it is replayed once, open-loop, from the frozen
episode (`tests/instance.json`) in a fresh process of a separate verifier container without network. The replay
runs the rows in order and ends at the last row or at the episode's horizon (606 control steps,
40 s), whichever comes first; rows after the horizon never run. The task is passed if upstream's success check holds on the state the replay ends in; a success
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
