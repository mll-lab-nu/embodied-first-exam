# Embodied Olympics · robot table tennis at the low level, match against level 1 (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-match-tabletennis-matchlow-i01-standard` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | standard |
| Opponent | Scripted robot at level 1 of 4, with the same robot and limits as the agent's |
| Instance | `tabletennis_matchlow`, seed 22 |
| Time limit | 2 h |
| Reference solution | Pipeline check only |

## Task
Win a game of table tennis to 5 points against the scripted opponent, with a hitting skill you write yourself playing
every stroke.

## Success criteria
The instance: the agent's robot (seat A) against the scripted opponent at level 1, seed 22, at
the low action level. One game of table tennis: the first to 5 points wins, with a lead of 2 from 4:4, or the first to 7 (at 6:6 the next point wins). At 40 points played (lets included) the player ahead wins; at a level score, the player who won the last point. A player's third undue-delay fault (no toss within 5 s of the serve opening) loses it the match. There are no draws. Every stroke is a `hit` that the simulator hands, in the loop, to the agent's own
skill server in the agent's own container; a call that fails, is late or returns no valid command gives no command.
The world runs in lockstep: it advances only during the agent's waits and up to the step at which an action takes
effect, and it waits for each skill call.

Success: the match ends by the rules (`match_over`) with the agent's side as the winner. The grader checks only the
match result. The agent's side loses the match, a valid 0, by any of these forfeits:
- `no_show`: no `game start` within 1800 s of real time after the match service starts, or the session ends before
  the start;
- `ready_timeout`: no `game ready` review within 300 s of real time after a point, even when ahead;
- `abandoned`: the agent's session ends while the match is in play.

A simulator error in a control step, after the agent's first applied action, is a valid 0 too.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. There is
one match and no reset, and the agent cannot end it with `/finish`: the match's rules end it. A technical failure of
the match service (a crash, an error in its bookkeeping, rendering or metering) voids the trial as an infrastructure
failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 6 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics task exporter from its task `roboolympics/tabletennis-match-wallclock-program-lowlevel-standard` (upstream commit
`02c93822a35e`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
