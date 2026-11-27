# Embodied Olympics · wheeled robot soccer 5 v 5 (RoboCup SSL Division B), match against level 4 (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-match-soccerssl-match-i01-standard` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | RoboCup Small Size League omnidirectional wheeled robots (the agent's team of five) |
| Mode | standard |
| Opponent | Yellow team at level 4: the scripted level 3 team (man marking, a blocker, passes) with a trained network choosing each field robot's option every 0.2 s; it reads the simulator's true state with no reaction delay and commands its robots with the same skills and limits as yours |
| Instance | `soccer_ssl_match`, seed 7 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a 5 v 5 wheeled robot soccer match against the yellow team.

## Success criteria
One 5 v 5 match under the RoboCup SSL Division B rules, with an automatic referee: two halves of 300 s of playing time
(the clock stops whenever no team may play the ball), ends changed at half time. The team with more goals after two
halves wins; a team with 10 goals and a lead of more than one wins at once. Level after two halves: a shoot-out of 5
penalty kicks each (decided as soon as one team cannot be caught), then sudden death; still level after 10 kicks each,
a coin toss drawn from the seed. There are no draws. A goal counts only if the ball fully entered the goal between the
posts, was never higher than 0.15 m after the scoring team's last touch, and the scoring team had no more robots on the
field than allowed and committed no non-stopping foul in the last 2 s.

The world runs in lockstep: it advances only during the agent's waits and up to the step at which its action
takes effect.

Success: the match ends by these rules and the blue team (yours) won it. Your side loses the match at once, a valid 0,
if you do not send `game start` within 1800 s of real time after the match service starts or before your session ends
(`no_show`); if a review is not sent with `game ready` within 600 s of real time after a stoppage (a goal, half time,
full time before the shoot-out, each shoot-out kick; `ready_timeout`, even when you are ahead); or if your session ends
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
Exported by the Embodied Olympics task exporter from its task `roboolympics/soccer_ssl-match-wallclock-program-standard` (upstream commit
`91156213b0de`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
