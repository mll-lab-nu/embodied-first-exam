# Embodied Olympics · robot badminton at the low level, match against level 2 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-badminton-matchlow-i01-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Franka Emika Panda arm on a moving base (an x-y rail in table tennis, a gantry in badminton), holding a paddle or racket |
| Mode | privileged |
| Opponent | Scripted robot at level 2 with the same arm, racket and gantry limits: it plays from the simulator's true state, predicts the shuttle's flight exactly, reacts 0.25 s after your hit, returns every shuttle it can reach, places most shots away from your base and reads habits in your shots |
| Instance | `badminton_matchlow`, seed 8 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a game of singles badminton to 11 points against the scripted opponent, with a stroke skill you write yourself
playing every stroke.

## Success criteria
The match and its point rules: one game of singles badminton with rally scoring against the scripted opponent, played
with the low-level commands (`traj`, `move`, `toss`, `none`); you serve the first point. The first to 11 points wins;
from 10-10 a player must lead by 2, and at 14-14 the next point wins (at most 15). The match also ends after 400 hits
(both sides) or 40 points played (lets included): then the player with more points wins; at equal points, the winner
of the last point that was not a let; if no point was won, the opponent. You lose a point when your shot goes into the
net, comes down on your own side or lands out; when a shuttle that is yours to hit lands in your court or is still
unplayed 6 s after the opponent played it; on your own service fault (no toss within 3 s of the window opening 1 s
after play resumes, a miss, a hit above 1.15 m or not upwards, a serve into the net or outside the diagonal service
court); and when your base leaves its serve spot by more than 5 cm before the serve is delivered.

The call rules: the files under `/app/output/policy/` (at most 512 regular files and 32 MiB, no links or special
files, with `program.py`) are copied and run as an unprivileged process. `make_policy(config)` must be ready within
30 s. The match runs at 1/20 of real speed while the program computes. After each answer, the next view comes once 2
more control steps (0.02 s of game time) have passed; during a review the program is asked again and again. Each call
must answer within 5 s with exactly one response of at most 1 MiB: None, one command, or `{"type": "ready"}` alone. A
command the match refuses does not end the match; one that answers a view from a point that has ended is dropped. A
review not ended with `ready` within 300 s loses the match (`ready_timeout`), and a match not over within 7200 s of
wall time from the start of the evaluation scores 0. Only a match that ends by its rules (`match_over`) can pass.

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
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/badminton-match-wallclock-program-lowlevel-standard` (upstream commit
`02c93822a35e`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
