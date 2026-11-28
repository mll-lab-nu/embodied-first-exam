# Embodied Olympics · table tennis on Unitree G1s (GPU tier), match against level 4 (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-tabletennisg1-matchgpu-i01-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Unitree G1 humanoid |
| Mode | realtime, slowdown 1 |
| Opponent | Scripted Unitree G1 at level 4 of 4 (the BOSS), which reads the ball's true position, velocity and spin |
| Instance | `tabletennisg1_match`, seed 4 |
| Time limit | 2 h |
| Reference solution | Pipeline check only |

## Task
Win a game of table tennis to 5 points against the other robot.

## Success criteria
The instance: the agent's G1 (seat A) against the scripted G1 at level 4, seed 4. One game of table tennis between two Unitree G1s: the first to 5 points with a lead of 2, or the first to 7, wins. At 16 points played (lets included) the player ahead wins; at a level score, the player who won the last point. A player's third undue-delay fault loses it the match. There are no draws.

Success: the match ends with the agent's side as the winner. The agent's side loses, a valid 0, by:
- `no_show`: no `game start` within the 1800 s preparation counted from the seat's first `game` request, or the
  session ends before the start;
- `abandoned`: the agent's session ends while the match is in play;
- `resigned`: the agent sends `game resign`.

A missed review never loses: the match resumes at the review's 300 s deadline. A failure of the world, the match
service or the platform, a breach of the real-time integrity checks, and a match the wall-clock cap stops, void the
trial as an infrastructure failure; a simulator error is one of these, never the agent's 0.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. The world
runs on a clock that does not stop: one second of game time takes 1 s of real time. There is one match and no reset,
and the agent cannot end it with `/finish`: the match's rules end it. A technical failure of the match service (a
crash, an error in its bookkeeping, rendering or metering) voids the trial as an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 2048 | 20 GiB | 10 GiB |
| `sim` | 20 | 8 GiB | 1024 | no GPU | — |
| `practice` | 8 | 8 GiB | 512 | no GPU | — |
| `practice_player` | 1 | 1 GiB | 64 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: L40S 48GB / RTX 4090 24GB / L4 24GB.

## Others
Ported from Embodied Olympics core 0.5, which has no exporter: its task `roboolympics/tabletennis_g1-match-wallclock-program-engineer-standard` (revision
`g1tt-10+core-0.5`, upstream commit `45ed806a5`). The files changed here are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
