# Embodied Olympics · foosball, game against level 3 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-foosball-match-i01-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | The four rods of one side of a foosball table |
| Mode | privileged |
| Opponent | Scripted computer team at level 3 of 4, playing on the true ball position a short reaction delay ago, with the same rods |
| Instance | `foosball_match`, seed 7 |
| Time limit | 4 h |
| Reference solution | Included |

## Task
Win a game of foosball to 5 goals against the computer team.

## Success criteria
The instance: the agent's four rods (seat A) against the computer team at level 3, seed 7.
One game of foosball: the first to 5 goals wins. The game also ends after 240 s of play (frozen time does not count) or 40 rallies; then the player with more goals wins; at equal goals, the player who scored the last goal; if nobody scored, the player with the ball less time in its own half; as a last resort, the player who did not have the first kick-off. There are no draws.

Deliverable: `/app/output/policy/program.py`, with any helper files in the same folder (at most 512 regular files and
32 MiB; no links or special files, else 0). It defines `make_policy(config)`; the object it returns gets `act(view)`
with the full state at every control step. Call rules: each call must answer within 5 s, with one command or none; a
slower call or another answer ends the game with 0. The world runs at 1/20 of real speed while the program computes.
After every rally the program must answer `{"type": "ready"}` within 300 s, or its side loses the game
(`ready_timeout`). The formal game is cut off after 6000 s of wall time; an unfinished game scores 0.

Success: the game ends by the rules (`match_over`) with the program's side as the winner. A forfeit scores 0. A
simulator error in a control step, after the program's first applied command, also scores 0.

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
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/foosball-match-wallclock-program-standard` (upstream commit
`d71e9f642ead`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
