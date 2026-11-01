# embodied-olympics-match-tabletennisg1-matchcpu-i01-standard-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Match |
| Mode | standard-realtime (`eai-standard-realtime/1.0`) |
| Twin | `embodied-olympics-match-tabletennisg1-matchcpu-i01-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `tabletennisg1_match` / seed 4 |
| Oracle | `partial` — the sport's reference player (solution/: builtin_players:OpenReference, camera images and /spec only, the learned striker of the release on CPU) over HTTP: the camera-only reference won this seed 7:6 live (x1i: 2 of 5 seeds against level 4: 4, 5); in this repository it lost 2:5 (standard-realtime) and 5:7 (standard): no winning oracle. Embodied First Exam's local Harbor runs: see the benchmark README; nop 0 |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RO_SLOWDOWN`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0@sha256:8bc6d02f91aa5730bbf93bc5c1c4a477feee6f5846ff8c609aaa3a25e0eb36af` |

## Task
Table tennis between two Unitree G1 humanoids (Embodied Olympics' sport `tabletennis_g1`), Engineer track: the agent's
program drives all 29 joints of its G1 at 100 Hz (no walking service) from two cameras, against the platform's G1 at
level 4 of 4, in real time (x1). The benchmark README's "Table tennis on two Unitree G1s" says what was ported and
what Embodied First Exam changed.

## Difficulty
Frozen development instance: seed 4, level 4, x1. Not one of the sport's official (hidden) seeds, so results
here are previews, not official Embodied Olympics results.

## Reference solution
`solution/`: the sport's camera-only reference player (`builtin_players:OpenReference`, the release's learned striker
on CPU) through the same HTTP interface; the camera-only reference won this seed 7:6 live (x1i: 2 of 5 seeds against level 4: 4, 5); in this repository it lost 2:5 (standard-realtime) and 5:7 (standard): no winning oracle.

## Verification
Separate sandbox, no network. Graded by the live match (`final.json` `graded_by` live, no grading replay; the replay
video is drawn after the verdict): the Embodied Olympics Judge (`tests/grade.py`, `tests/eo_judge/`) applies the
sport's validity rules (a platform fault, including an integrity breach of the real-time world, voids the trial; the
player's own problems are a valid loss) and writes reward.json; success = a valid, finished match that the agent won.
`tests/fexam_reward.py` adds `infra_error`, `graded_by_live`, `realtime`, `opponent_level`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 20 | 8 GiB | 1024 | no GPU | — |
| `practice` | 8 | 4 GiB | 512 | no GPU | — |
| `practice_player` | 1 | 1 GiB | 64 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.
