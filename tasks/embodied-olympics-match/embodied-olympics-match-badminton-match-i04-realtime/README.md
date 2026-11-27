# Embodied Olympics · robot badminton, match against level 5 (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-badminton-match-i04-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | realtime, slowdown 20 |
| Opponent | Scripted robot at level 5 (a tier above the sport's levels 1-3) with the same arm, racket and gantry limits: it plays from the simulator's true state, predicts the shuttle's flight exactly, reacts 0.22 s after your hit, returns every shuttle it can reach, places most shots away from your base and reads habits in your shots |
| Instance | `badminton_match`, seed 1034 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a game of singles badminton to 11 points against the scripted opponent.

## Success criteria
One game of singles badminton with rally scoring against the scripted opponent; you serve the first point. The first
to 11 points wins; from 10-10 a player must lead by 2, and at 14-14 the next point wins (at most 15). The match also
ends after 400 hits (both sides) or 40 points played (lets included): then the player with more points wins; at equal
points, the winner of the last point that was not a let; if no point was won, the opponent. There are no draws.

You lose a point when your shot goes into the net, comes down on your own side or lands outside the opponent's singles
court (lines are in); when a shuttle that is yours to hit lands in your court, or is still unplayed 6 s after the
opponent played it; and on your own service fault: no toss within 3 s (the window opens 1 s after play resumes), a
miss (the shuttle lands, or 6 s pass after the toss), a hit above 1.15 m or not upwards, a serve into the net or outside
the opponent's diagonal service court. Your base more than 5 cm from its serve spot before the serve is delivered also
loses you the point. You win the point when the opponent's shot lands out or in the net, or its serve is a fault.

Success: the match ends by these rules and you won it. Your side loses the match at once, a valid 0, if you do not send
`game start` within 1800 s of real time after the match service starts or before your session ends (`no_show`); if a
review is not sent with `game ready` within 300 s of real time after a point (`ready_timeout`, even when you are
ahead); or if your session ends before the match is over (`abandoned`).

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
Exported by the Embodied Olympics task exporter from its task `roboolympics/badminton-match-wallclock-program-standard` (upstream commit
`62333496959f`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
