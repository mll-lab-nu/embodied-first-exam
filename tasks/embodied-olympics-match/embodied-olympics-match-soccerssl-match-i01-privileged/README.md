# Embodied Olympics · wheeled robot soccer 5 v 5 (RoboCup SSL Division B), match against level 4 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-soccerssl-match-i01-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | RoboCup Small Size League omnidirectional wheeled robots (the agent's team of five) |
| Mode | privileged |
| Opponent | Yellow team at level 4: the scripted level 3 team (man marking, a blocker, passes) with a trained network choosing each field robot's option every 0.2 s; it reads the simulator's true state with no reaction delay and commands its robots with the same skills and limits as yours |
| Instance | `soccer_ssl_match`, seed 7 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a 5 v 5 wheeled robot soccer match against the yellow team.

## Success criteria
The match and its rules: one 5 v 5 match under the RoboCup SSL Division B rules, with an automatic referee: two halves
of 300 s of playing time (the clock stops whenever no team may play the ball), ends changed at half time. The team with
more goals after two halves wins; a team with 10 goals and a lead of more than one wins at once. Level after two
halves: a shoot-out of 5 penalty kicks each, then sudden death; still level after 10 kicks each, a coin toss drawn from
the seed. A goal counts only if the ball fully entered the goal between the posts, was never higher than 0.15 m after
the scoring team's last touch, and the scoring team had no more robots on the field than allowed and committed no
non-stopping foul in the last 2 s.

The call rules: the files under `/app/output/policy/` (at most 512 regular files and 32 MiB, no links or special
files, with `program.py`) are copied and run as an unprivileged process. `make_policy(config)` must be ready within
30 s. The match runs at 1/10 of real speed while the program computes. After each answer, the next view comes once 5
more control steps (0.05 s of game time) have passed; during a review the program is asked again and again. Each call
must answer within 5 s with exactly one response of at most 1 MiB: None, one command (a `batch` command moves several
robots), or `{"type": "ready"}` alone. A command the match refuses does not end the match; one that answers a view
from a play period that has ended is dropped. A review not ended with `ready` within 600 s loses the match
(`ready_timeout`), and a match not over within 13500 s of wall time from the start of the evaluation scores 0. Only a
match that ends by its rules (`match_over`) can pass.

A simulator error in a control step, after the program's first applied command, also scores 0.

Graded: one formal match, played after the agent's session in a separate verifier container without network by the
agent's final program, from a fresh, unmodified start against the same opponent; nothing the agent played during its
session counts. The task is passed only if that match ends by the rules above with the program's side as the winner.
A program that fails to load, raises, breaks the call rules above, or leaves a process behind scores 0. A failure of
the verifier or of the trusted match service, or a replay of the match record that disagrees with the match, is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 8 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/soccer_ssl-match-wallclock-program-standard` (upstream commit
`91156213b0de`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
