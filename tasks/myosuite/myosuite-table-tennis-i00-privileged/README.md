# MyoSuite · table_tennis (privileged)

| | |
|---|---|
| Task ID | `myosuite-table-tennis-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm with torso: MyoSuite's table tennis player, 273 muscles and two pelvis slides, holding a paddle |
| Mode | privileged |
| Instance | `table_tennis`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Return the served ball: hit it once with the paddle so that it lands on the opponent's half, with no second paddle
touch and at most one bounce on your half before that.

## Success criteria
Success event (MyoChallenge 2025 `myoChallengeTableTennisP1-v0`, its contact test on the ball): the ball touches the
opponent's half of the table after it has touched the paddle, and before that:
- the ball did not touch the paddle again after it had left the paddle;
- the ball touched the robot's own half only in one bounce, at most two control steps long.

A bounce on the robot's own half before the hit is not required. Contacts with the net or anything else are not
checked.

Failure (ends the episode with 0): 3 s of simulated time pass without the event, the ball is below 0.3 m, or the same
contact test finds the rally lost: a second paddle touch, a second bounce on the robot's half (or a first one longer
than two control steps), or the ball on the opponent's half without a paddle touch. The episode ends at the control
step this happens.

The replay ends in success at the first control step at which the success event happens, or with 0 at a failure.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
108,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
of a separate verifier container without network. The replay runs the rows in order until the episode ends as above;
later rows are not run. If the rows run out before the episode has ended in success, the task fails. A missing file,
a file that is not such an array, a file for another family, a wrong row width, an empty array, more rows than the
limit, a non-finite value, or an `.npz` entry larger than the row limit allows scores 0. A replay that gives no result
(it times out or dies), or a frozen start that does not rebuild with its recorded hash, is reported as
`grader_error` (infrastructure), not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 4096 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## License
MyoSuite ([MyoHub/myosuite](https://github.com/MyoHub/myosuite), version 2.12.2, tag `v2.12.2` = `5635e1a`) is
released under the Apache License 2.0, as are the models it bundles (MyoSim, the MPL prosthetic arm, the object,
furniture and YCB models). The MyoDex reference motions (the `dex_*` families) derive from the GRAB motion-capture
dataset; MyoSuite asks their users to comply with GRAB's licence, which allows non-commercial scientific research
only. The simulator is MuJoCo (Apache License 2.0).
