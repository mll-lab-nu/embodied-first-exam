# MyoSuite · table_tennis (standard)

| | |
|---|---|
| Task ID | `myosuite-table-tennis-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm with torso: MyoSuite's table tennis player, 273 muscles and two pelvis slides, holding a paddle |
| Mode | standard |
| Instance | `table_tennis`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Return the served ball: after it bounces once on your half, hit it once with the paddle so that it lands on the
opponent's half, with no second paddle touch and no second bounce on your half.

## Success criteria
Success event (MyoChallenge 2025 `myoChallengeTableTennisP1-v0`, its contact test on the ball): the ball touches the
opponent's half of the table after it has touched the paddle, and before that:
- the ball did not touch the paddle again after it had left the paddle;
- the ball touched the robot's own half only in one bounce, at most two control steps long.

A bounce on the robot's own half before the hit is not required. Contacts with the net or anything else are not
checked.

Failure (MyoSuite's `done`, ends the episode with 0): 3 s of simulated time pass without the event, or the ball is
below 0.3 m. A rally that has gone wrong (a second paddle touch, a second bounce on the robot's half) does not end the
episode by itself: it can then no longer succeed, and it ends at one of these two.

The success event does not end the episode. Once it has happened the task is passed, even if a failure above ends the
episode later. Before it, a failure ends the episode with 0.

Graded: the live episode, judged by the simulator service; nothing is replayed. No success signal is shown to the
agent. The episode ends at the agent's `/finish`, at a failure above, at the episode's own end where the rule above
has one, or when the agent's time (1 h) runs out. Resets granted: 10. A reset starts a new episode from
the frozen start; only the episode running at the end is graded. A simulator error raised by the agent's own call
ends the episode with 0. An episode that does not start from the frozen instance, or a service crash outside the
agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 7 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 7 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## License
MyoSuite ([MyoHub/myosuite](https://github.com/MyoHub/myosuite), version 2.12.2, tag `v2.12.2` = `5635e1a`) is
released under the Apache License 2.0, as are the models it bundles (MyoSim, the MPL prosthetic arm, the object,
furniture and YCB models). The MyoDex reference motions (the `dex_*` families) derive from the GRAB motion-capture
dataset; MyoSuite asks their users to comply with GRAB's licence, which allows non-commercial scientific research
only. The simulator is MuJoCo (Apache License 2.0).
