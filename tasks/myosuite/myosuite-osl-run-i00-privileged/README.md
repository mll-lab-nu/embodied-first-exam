# MyoSuite · osl_run (privileged)

| | |
|---|---|
| Task ID | `myosuite-osl-run-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoLeg with a powered knee-ankle prosthesis (OSL) on the right leg, 54 muscles |
| Mode | privileged |
| Instance | `osl_run`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Run 29 m down the track to the finish, staying on your feet and near the middle of the track.

## Success criteria
Success event (MyoChallenge 2024 `myoChallengeOslRunFixed-v0`, the finish): the body's root crosses the finish line, y
= -15 m, 30 m down the flat track from where it starts (y = 15 m). There is no time limit.

Failure (MyoSuite's `done`, ends the episode with 0):
- the root is more than 1 m to the side of the track's centre line;
- the root goes back past y = 16 m (1 m behind the start);
- a fall: the head is less than 0.2 m above the mean height of the two feet, or less than 0.2 m above the ground.

The prosthetic leg's knee and ankle are driven by MyoSuite's own controller; the agent's commands for them are
ignored.

The replay ends in success at the first control step at which the success event happens, or with 0 at a failure.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
216,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
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
