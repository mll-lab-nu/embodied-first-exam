# Embodied Olympics · robot table tennis, match against level 4 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-tabletennis-match-i04-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | privileged |
| Opponent | Scripted robot at level 4 of 4, with the same robot and limits as the agent's |
| Instance | `tabletennis_match`, seed 34 |
| Time limit | 2 h |
| Reference solution | Pipeline check only |

## Task
Win a game of table tennis to 5 points against the scripted opponent.

## Success criteria
The instance: the agent's robot (seat A) against the scripted opponent at level 4, seed 34.
One game of table tennis: the first to 5 points wins, with a lead of 2 from 4:4, or the first to 7 (at 6:6 the next point wins). At 40 points played (lets included) the player ahead wins; at a level score, the player who won the last point. A player's third undue-delay fault (no toss within 5 s of the serve opening) loses it the match. There are no draws.

Deliverable: `/app/output/policy/program.py`, with any helper files in the same folder (at most 512 regular files and
32 MiB; no links or special files, else 0). It defines `make_policy(config)`; the object it returns gets `act(view)`
with the full state every 5 control steps. Call rules: each call must answer within 5 s, with one command or none; a
slower call or another answer ends the match with 0. The world runs at 1/10 of real speed while the program computes.
After every point the program must answer `{"type": "ready"}` within 300 s, or its side loses the match
(`ready_timeout`). The formal match is cut off after 7200 s of wall time; an unfinished match scores 0.

Success: the match ends by the rules (`match_over`) with the program's side as the winner. A forfeit scores 0. A
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
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/tabletennis-match-wallclock-program-standard` (upstream commit
`e25d8cc11861`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
