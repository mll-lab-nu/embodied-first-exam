# MolmoSpaces · open-door (standard)

| | |
|---|---|
| Task ID | `molmospaces-open-door-i00-standard` |
| Benchmark | [MolmoSpaces](https://github.com/allenai/molmospaces) (Kim et al., 2026), upstream `allenai/molmospaces@7351388` |
| Robot | Rainbow Robotics RB-Y1 mobile manipulator: holonomic base, 6-joint torso, two 7-joint arms with grippers |
| Mode | standard |
| Instance | `open-door`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Pull the door open, at least two-thirds of the way.

## Success criteria
Success check (upstream `DoorOpeningTask`): the door's hinge is open at least 67% of its 90° range, in the state
judged.

Graded: the live episode, judged by the simulator service; nothing is replayed. Meeting the goal does not end the
episode and is not shown to the agent. The episode ends at the agent's `/finish` (or the `done` action, which is the
same), at the horizon (400 control steps, 40 s of robot time), or when the agent's time
(1 h) runs out. It is passed if upstream's success check holds on the state the episode ends in; a success
reached earlier and then undone does not count. No reset: the one episode is graded. A simulator error raised by the
agent's actions ends the episode with 0. A frozen start that does not rebuild, or a service crash between the
agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 4 GiB | 1024 | no GPU | 12 GiB |
| `sim` | 2 | 10 GiB | 1024 | 5 GiB | — |
| verifier (as `main`) | 3 | 4 GiB | no cap | no GPU | 12 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4 / L40S).

## License
MolmoSpaces ([allenai/molmospaces](https://github.com/allenai/molmospaces), molmo-spaces 0.2.9, tag `v0.2.9` @
`7351388`) is released under the Apache License 2.0 (Allen Institute for Artificial Intelligence). Assets: the scenes
and AI2-THOR objects are CC BY 4.0; Objaverse objects are ODC-BY 1.0, each also under its creator's CC BY, CC BY-SA or
CC0 licence, listed with its attribution in the image's `/opt/molmospaces/ATTRIBUTION.md`. The image build refuses
any asset with non-commercial terms, so no non-commercial terms apply. The simulator is MuJoCo 3.5.0 (Apache License
2.0).
