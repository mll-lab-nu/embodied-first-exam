# MyoSuite · soccer (privileged)

| | |
|---|---|
| Task ID | `myosuite-soccer-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoLegs: musculoskeletal model of the human legs and pelvis |
| Mode | privileged |
| Opponent | Goalkeeper on the goal line (scripted, MyoChallenge 2025's P1 policy `stationary`): it stays where the frozen start placed it |
| Instance | `soccer`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Score a goal: kick the ball past the goalkeeper into the goal.

## Success criteria
Success event (MyoChallenge 2025 `myoChallengeSoccerP1-v0`, a goal): the ball's centre crosses the goal line, between
the posts (at most 3.3 m to either side of the goal's centre) and from 0 to 2.2 m high.

Failure (MyoSuite's `done`, ends the episode with 0):
- 10 s of simulated time pass without a goal;
- the pelvis is below 0.2 m (a fall).

The replay ends in success at the first control step at which the success event happens, or with 0 at a failure.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
144,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
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
