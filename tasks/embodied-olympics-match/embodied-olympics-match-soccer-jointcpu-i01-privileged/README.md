# Embodied Olympics · robot soccer 2 v 2 at the joint level (CPU tier), match against level 5 (privileged)

| | |
|---|---|
| Task ID | `embodied-olympics-match-soccer-jointcpu-i01-privileged` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Booster T1 humanoids (the agent's team) |
| Mode | privileged |
| Opponent | Learned team at level 5: two Booster T1s under joint control like yours (12 leg joint targets every 20 ms, the same limits), each walking on a gait policy trained by reinforcement learning (PPO), with a learned plan choosing what each robot does; it reads the simulator's true state |
| Instance | `soccer_jointmatch`, seed 101 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a 2 v 2 robot soccer match against the other team.

## Success criteria
The match and its rules: one 2 v 2 match at the joint level, of two halves of 5 minutes of game time (a half runs on
for up to 3 s while the ball still rolls). The team with more goals after two halves wins; a 10-goal lead wins at once.
Level after two halves: a shoot-out of 3 kicks each, then up to 3 sudden-death rounds, each won by the better kick
(goal, saved, post, wide, other, no kick), then a coin toss drawn from the seed. In the shoot-out the striker has 20 s
to touch the ball, and a keeper more than 0.6 m from its goal line before the touch concedes a goal. A kick-off team
that scores before it touched the ball outside the centre circle gets no goal. The formal match runs no check for the
released walking policy.

The call rules: the files under `/app/output/policy/` (at most 512 regular files and 32 MiB, no links or special
files, with `program.py`) are copied and run as an unprivileged process. `make_policy(config)` must be ready within
30 s. The match runs at 1/10 of real speed while the program computes. After each answer, the next view comes once 1
more control step (0.02 s of game time) has passed; during a review the program is asked again and again. Each call
must answer within 5 s with exactly one response of at most 1 MiB: None, one command, a list of at most 2 commands
(one per robot), or `{"type": "ready"}` alone. A command the match refuses does not end the match; one that answers a
view from a play period that has ended is dropped. A review not ended with `ready` within 300 s loses the match
(`ready_timeout`), and a match not over within 10800 s of wall time from the start of the evaluation scores 0. Only a
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
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 6 | 12 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Others
Exported by the Embodied Olympics full-simulator exporter from its task `roboolympics/soccer-match-wallclock-program-lowlevel-standard` (upstream commit
`7ae66874c32e`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
