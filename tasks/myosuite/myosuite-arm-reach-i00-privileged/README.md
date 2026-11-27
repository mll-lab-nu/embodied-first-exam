# MyoSuite · arm_reach (privileged)

| | |
|---|---|
| Task ID | `myosuite-arm-reach-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm: musculoskeletal model of the human shoulder, arm and hand |
| Mode | privileged |
| Instance | `arm_reach`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Touch the small sphere in front of you with your index fingertip and hold it there for a second.

## Success criteria
Success rule (MyoSuite `myoArmReachFixed-v0`, its `solved` held): the index fingertip is less than 0.0125 m from the
target point, held for 50 consecutive control steps (1 s at 20 ms per step).

Failure (MyoSuite's `done`, ends the episode with 0): from the third control step on, the index fingertip is more than
1 m from the target point.

The replay ends in success at the first control step at which the goal has held for 50 consecutive control steps, or
with 0 at a failure.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
720,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
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
