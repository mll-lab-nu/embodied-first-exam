# Embodied Olympics · robot epee fencing, bout against level 2 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-fencing-bout-i02-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Unitree G1 humanoid |
| Mode | privileged |
| Opponent | Scripted fencer at level 2 (the higher of its two levels), which picks its intention before each phrase from what it has seen, never from the agent's choice for that phrase |
| Instance | `fencing_bout`, seed 35 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Win an epee bout to 15 touches against the scripted fencer.

## Success criteria
The instance: the agent's fencer (seat A) against the scripted fencer at level 2, seed 35.
One epee bout between two Unitree G1s: the first to 15 touches wins. After 9 minutes of fencing time the fencer ahead wins; at equal scores one more minute is fenced, the first touch decides, else the fencer with priority (drawn by lot before it) wins. A second minute of fencing time without a touch (unwillingness to fight) loses the bout for the fencer with the lower score; at equal scores a seeded lot decides. There are no draws.

Deliverable: `/app/output/policy/program.py`, with any helper files in the same folder (at most 512 regular files and
32 MiB; no links or special files, else 0). It defines `make_policy(config)`; the object it returns gets `act(view)`
with the full state on each of its turns (one phrase intention) and at the review after each of its phrases (answer
`{"type": "ready"}`). Call rules: each call must answer within 5 s, with one command or none; a slower call or
another answer ends the bout with 0. The program's chess clock (3600 s in all) runs while it computes on its turn; out
of time loses the bout (`clock`). The formal bout is cut off after 4200 s of wall time; an unfinished bout scores 0.

Success: the bout ends by the rules (`match_over`) with the program's side as the winner. A forfeit scores 0.

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
| verifier | 2 | 4 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/fencing-bout-wallclock-program-standard` (upstream commit
`a6712a675343`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
