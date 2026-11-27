# Embodied Olympics · foosball, game against level 3 (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-foosball-match-i01-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | The four rods of one side of a foosball table |
| Mode | realtime, slowdown 20 |
| Opponent | Scripted computer team at level 3 of 4, playing on the true ball position a short reaction delay ago, with the same rods |
| Instance | `foosball_match`, seed 7 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a game of foosball to 5 goals against the computer team.

## Success criteria
The instance: the agent's four rods (seat A) against the computer team at level 3, seed 7.
One game of foosball: the first to 5 goals wins. The game also ends after 240 s of play (frozen time does not count) or 40 rallies; then the player with more goals wins; at equal goals, the player who scored the last goal; if nobody scored, the player with the ball less time in its own half; as a last resort, the player who did not have the first kick-off. There are no draws.

Success: the game ends by the rules (`match_over`) with the agent's side as the winner. The agent's side loses the
game, a valid 0, by any of these forfeits:
- `no_show`: no `game start` within 1800 s of real time after the match service starts, or the session ends before
  the start;
- `ready_timeout`: no `game ready` review within 300 s of real time after a rally, even when ahead;
- `abandoned`: the agent's session ends while the game is in play.

A simulator error in a control step, after the agent's first applied action, is a valid 0 too.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. The world
runs on a clock that does not stop: one second of game time takes 20 s of real time. There is one match and no reset,
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
Exported by the Embodied Olympics task exporter from its task `roboolympics/foosball-match-wallclock-program-standard` (upstream commit
`d71e9f642ead`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
