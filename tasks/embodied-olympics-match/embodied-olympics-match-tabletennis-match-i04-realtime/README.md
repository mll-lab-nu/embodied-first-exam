# Embodied Olympics · robot table tennis, match against level 4 (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-tabletennis-match-i04-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | realtime, slowdown 10 |
| Opponent | Scripted robot at level 4 of 4, with the same robot and limits as the agent's |
| Instance | `tabletennis_match`, seed 34 |
| Time limit | 2 h |
| Reference solution | Pipeline check only |

## Task
Win a game of table tennis to 5 points against the scripted opponent.

## Success criteria
The instance: the agent's robot (seat A) against the scripted opponent at level 4, seed 34.
One game of table tennis: the first to 5 points wins, with a lead of 2 from 4:4, or the first to 7 (at 6:6 the next point wins). At 40 points played (lets included) the player ahead wins; at a level score, the player who won the last point. A player's third undue-delay fault (no toss within 5 s of the serve opening) loses it the match. There are no draws.

Success: the match ends by the rules (`match_over`) with the agent's side as the winner. The agent's side loses the
match, a valid 0, by any of these forfeits:
- `no_show`: no `game start` within 1800 s of real time after the match service starts, or the session ends before
  the start;
- `ready_timeout`: no `game ready` review within 300 s of real time after a point, even when ahead;
- `abandoned`: the agent's session ends while the match is in play.

A simulator error in a control step, after the agent's first applied action, is a valid 0 too.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. The world
runs on a clock that does not stop: one second of game time takes 10 s of real time. There is one match and no reset,
and the agent cannot end it with `/finish`: the match's rules end it. A technical failure of the match service (a
crash, an error in its bookkeeping, rendering or metering) voids the trial as an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 6 | 6 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics task exporter from its task `roboolympics/tabletennis-match-wallclock-program-standard` (upstream commit
`e25d8cc11861`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
