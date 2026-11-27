# Embodied Olympics · table tennis on Unitree G1s (CPU tier), match against level 4 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-tabletennisg1-matchcpu-i01-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Unitree G1 humanoid |
| Mode | privileged |
| Opponent | Scripted Unitree G1 at level 4 of 4 (the BOSS), which reads the ball's true position, velocity and spin |
| Instance | `tabletennisg1_match`, seed 4 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Win a game of table tennis to 5 points against the other robot.

## Success criteria
The instance: the agent's G1 (seat A) against the scripted G1 at level 4, seed 4. One game of table tennis between two Unitree G1s: the first to 5 points with a lead of 2, or the first to 7, wins. At 16 points played (lets included) the player ahead wins; at a level score, the player who won the last point. A player's third undue-delay fault loses it the match. There are no draws.

Deliverable: `/app/output/policy/program.py`, with any helper files in the same folder (at most 512 regular files and
32 MiB; no links). It defines `make_policy(config)`; the object it returns gets `act(view)` with the seat's state, the
camera images and the ground truth at every control step (10 ms of game time). The sport's in-process runner waits for
each answer. An answer later than 0.5 s of wall time, a program error or no answer is no command at that step; after
1800 s of the program's own time in total it sends no more commands. A missing `program.py` scores 0.

Success: the match ends by the rules with the program's side as the winner. A match still unfinished after 636,000
control steps is not won. A process of the program left running after the match scores 0. A failure of the trusted
runner, or a fresh-process replay that disagrees with the match, is an infrastructure failure, not a score.

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
| `main` (the agent's) | 8 | 16 GiB | 2048 | no GPU | 10 GiB |
| verifier | 12 | 16 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Ported from Embodied Olympics core 0.5, which has no exporter: its task `roboolympics/tabletennis_g1-match-wallclock-program-engineer-standard` (revision
`g1tt-10+core-0.5`, upstream commit `45ed806a5`). The files changed here are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
