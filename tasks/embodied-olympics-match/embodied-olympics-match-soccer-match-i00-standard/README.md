# Embodied Olympics · robot soccer 2 v 2, match against level 2 (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-match-soccer-match-i00-standard` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Booster T1 humanoids (the agent's team) |
| Mode | standard |
| Opponent | Scripted team B at level 2: two Booster T1s on the same walking policy and kick skill as yours; they read the simulator's true state, react to the ball 0.3 s late, walk at most 0.65 m/s and kick in their stride (the in-walk kick) |
| Instance | `soccer_match`, seed 7 |
| Time limit | 2 h |
| Reference solution | Pipeline check only |

## Task
Win a 2 v 2 robot soccer match against the other team.

## Success criteria
One 2 v 2 match of two halves of 5 minutes of game time (a half runs on for up to 3 s while the ball still rolls). The
team with more goals after two halves wins; a 10-goal lead wins at once. Level after two halves: a shoot-out of 3 kicks
each (decided as soon as one team cannot be caught), then up to 3 sudden-death rounds, each won by the better kick
(goal, saved, post, wide, other, no kick, in this order), then a coin toss drawn from the seed. There are no draws. In
the shoot-out the striker has 20 s to touch the ball, and a keeper more than 0.6 m from its goal line before the touch
concedes a goal. A kick-off team that scores before it touched the ball outside the centre circle gets no goal.

The world runs in lockstep: it advances only during the agent's waits and up to the step at which its action
takes effect.

Success: the match ends by these rules and team A won it. Your side loses the match at once, a valid 0, if you do not
send `game start` within 1800 s of real time after the match service starts or before your session ends (`no_show`);
if a review is not sent with `game ready` within 600 s of real time after a stoppage (a goal, half time, a dropped
ball, full time when level, each shoot-out kick; `ready_timeout`, even when you are ahead); or if your session ends
before the match is over (`abandoned`).

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
Exported by the Embodied Olympics task exporter from its task `roboolympics/soccer-match-wallclock-program-standard` (upstream commit
`0d7f680cc049`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
