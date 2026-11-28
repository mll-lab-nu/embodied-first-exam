# Embodied Olympics · robot soccer 2 v 2 at the joint level (CPU + GPU tier), match against level 5 (realtime)

| | |
|---|---|
| Task ID | `embodied-olympics-match-soccer-jointgpu-i01-realtime` |
| Benchmark | [Embodied Olympics - Match](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@0d7f680` |
| Robot | Booster T1 humanoids (the agent's team) |
| Mode | realtime, slowdown 10 |
| Opponent | Learned team at level 5: two Booster T1s under joint control like yours (12 leg joint targets every 20 ms, the same limits), each walking on a gait policy trained by reinforcement learning (PPO), with a learned plan choosing what each robot does; it reads the simulator's true state |
| Instance | `soccer_jointmatch`, seed 101 |
| Time limit | 4 h |
| Reference solution | Pipeline check only |

## Task
Win a 2 v 2 robot soccer match against the other team.

## Success criteria
One 2 v 2 match at the joint level, of two halves of 5 minutes of game time (a half runs on for up to 3 s while the
ball still rolls). The team with more goals after two halves wins; a 10-goal lead wins at once. Level after two halves:
a shoot-out of 3 kicks each (decided as soon as one team cannot be caught), then up to 3 sudden-death rounds, each won
by the better kick (goal, saved, post, wide, other, no kick, in this order), then a coin toss drawn from the seed. There
are no draws. In the shoot-out the striker has 20 s to touch the ball, and a keeper more than 0.6 m from its goal line
before the touch concedes a goal. A kick-off team that scores before it touched the ball outside the centre circle gets
no goal.

A win is then checked for the released Booster walking policy. The match is replayed, and for a sample of each of
your robots' joint rows (every 20th control step, at most 600 per robot, spread over the match) the policy's closest
possible row is fitted (its velocity command and gait phase free, from the robot's state up to 3 control steps
earlier). If for either robot more than half of these rows are fitted within
0.02 rad (RMS), the win is void and scores 0. A win whose check gives no result, or whose replay does not reproduce the
match, is an infrastructure failure, not a score. `METHOD.md` and `NOTES.md` are not graded.

Success: the match ends by these rules, team A won it and the check found no released policy. Your side loses the match
at once, a valid 0, if you do not send `game start` within 7200 s of real time after the match service starts or before
your session ends (`no_show`); if a review is not sent with `game ready` within 300 s of real time after a stoppage (a
goal, half time, a dropped ball, full time when level, each shoot-out kick; `ready_timeout`, even when you are ahead);
or if your session ends before the match is over (`abandoned`).

A simulator error in a control step, after the agent's first applied action, is a valid 0 too.

Graded: the live match, as the trusted match service recorded it while it was played; nothing is replayed. The world
runs on a clock that does not stop: one second of game time takes 10 s of real time. There is one match and no reset,
and the agent cannot end it with `/finish`: the match's rules end it. A technical failure of the match service (a
crash, an error in its bookkeeping, rendering or metering) voids the trial as an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 6 | 16 GiB | 2048 | 12 GiB | 10 GiB |
| `sim` | 6 | 8 GiB | 1024 | no GPU | — |
| `practice` | 4 | 8 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: RTX 4090 24GB / L4 24GB / L40S 48GB.

## Others
Exported by the Embodied Olympics soccer pilot exporter from its task `roboolympics/soccer-match-wallclock-program-lowlevel-standard` (upstream commit
`7ae66874c32e`). The files changed here after the export are listed for this task in
`ci_checks/benchmarks/embodied-olympics-match/exported.toml`.

## License
Embodied Olympics ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics), a private repository) is released
under the MIT License; its exported match services, referees, scripted opponents and graders inside this task are MIT
too. The simulator is MuJoCo (Apache License 2.0). No non-commercial terms apply.
