# Embodied Olympics · robot epee fencing, bout against level 2 (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-match-fencing-bout-i02-standard` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Unitree G1 humanoid |
| Mode | standard |
| Opponent | Scripted fencer at level 2 (the higher of its two levels), which picks its intention before each phrase from what it has seen, never from the agent's choice for that phrase |
| Instance | `fencing_bout`, seed 35 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Win an epee bout to 15 touches against the scripted fencer.

## Success criteria
The instance: the agent's fencer (seat A) against the scripted fencer at level 2, seed 35.
One epee bout between two Unitree G1s: the first to 15 touches wins. After 9 minutes of fencing time the fencer ahead wins; at equal scores one more minute is fenced, the first touch decides, else the fencer with priority (drawn by lot before it) wins. A second minute of fencing time without a touch (unwillingness to fight) loses the bout for the fencer with the lower score; at equal scores a seeded lot decides. There are no draws. The bout is played in turns: one action per turn, then the agent's review (`game ready`) before play goes
on.

Success: the bout ends by the rules (`match_over`) with the agent's side as the winner. The agent's side loses the
bout, a valid 0, by any of these forfeits:
- `no_show`: no `game start` within 1800 s of real time after the match service starts, or the session ends before
  the start;
- `clock`: the agent's chess clock (3600 s of real time, running only on its own turn: its actions and its reviews)
  runs out;
- `abandoned`: the agent's session ends while the bout is in play.

Any error of the match service, the simulator included, is an infrastructure failure, not a score.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. There is
one match and no reset, and the agent cannot end it with `/finish`: the match's rules end it. A technical failure of
the match service (a crash, an error in its bookkeeping, rendering or metering) voids the trial as an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 4 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics task exporter from its task `roboolympics/fencing-bout-wallclock-program-standard` (upstream commit
`a6712a675343`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
