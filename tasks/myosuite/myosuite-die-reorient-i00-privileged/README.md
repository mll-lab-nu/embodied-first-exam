# MyoSuite · die_reorient (privileged)

| | |
|---|---|
| Task ID | `myosuite-die-reorient-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | privileged |
| Instance | `die_reorient`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Turn the die in your palm until it matches the see-through target die, and hold it there for a second.

## Success criteria
Success rule (MyoChallenge 2022 `myoChallengeDieReorientP1-v0`, its `solved` held): the die is within 0.025 m of the
target die's position (MyoSuite corrects for the display offset between the two), and the length of the difference
between the die's and the target's Euler angles is below 0.262 rad, held for 100 consecutive control steps (1 s at 10
ms per step).

Failure (MyoSuite's `done`, ends the episode with 0): the die is more than 0.2 m from the target position (dropped).

The replay ends in success at the first control step at which the goal has held for 100 consecutive control steps, or
with 0 at a failure.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
612,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
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
