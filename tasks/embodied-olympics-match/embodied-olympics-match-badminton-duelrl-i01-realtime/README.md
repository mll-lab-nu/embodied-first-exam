# Embodied Olympics · robot badminton, duel against the built-in RL player (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-badminton-duelrl-i01-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | realtime, slowdown 20 |
| Opponent | Built-in player (seat B) with the same robot, limits, rules and stroke controller as yours: it reads the true shuttle state and your base position instead of the cameras, and a policy trained by the cross-entropy method picks its contact, its shot and where its base waits |
| Instance | `badminton_duel`, seed 1001 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a game of singles badminton to 11 points against the other robot.

## Success criteria
One game of singles badminton with rally scoring between you (seat `A`) and the built-in player (seat `B`); `A`
serves the first point. The first to 11 points wins; from 10-10 a player must lead by 2, and at 14-14 the next point
wins (at most 15). The match also ends after 400 hits (both sides) or 40 points played (lets included): then the
player with more points wins; at equal points, the winner of the last point that was not a let; if no point was won,
`B` (the player who received first). There are no draws.

The rules are the same for both players. A player loses the point when its shot goes into the net, comes down on its
own side or lands outside the other singles court (lines are in); when a shuttle that is its to hit lands in its court,
or is still unplayed more than 6 s after it was last played; and on its own service fault: no toss within 3 s (the
window opens 1 s after play resumes), a miss, a hit above 1.15 m or not upwards, a serve into the net or outside the
receiver's diagonal service court. A base more than 5 cm from its serve spot before the serve is delivered loses that
player the point; if both bases move, the point is a let and is replayed.

Success: the match ends by these rules and seat `A` won it. Seat `A` loses the match at once, a valid 0, if it does not
send `game start` within 1800 s of real time after the match service starts or before the session ends (`no_show`); if
its review is not sent with `game ready` within 300 s of real time after a point (`ready_timeout`, even when ahead); or
if the session ends before the match is over (`abandoned`). The built-in player never ends a session.

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
Exported by the Embodied Olympics task exporter from its task `roboolympics/badminton-duel-wallclock-program-standard` (upstream commit
`b12667a02300`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
