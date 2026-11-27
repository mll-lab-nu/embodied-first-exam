# MyoSuite · baoding (privileged)

| | |
|---|---|
| Task ID | `myosuite-baoding-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | privileged |
| Instance | `baoding`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Roll the two balls around each other in your palm so that each one follows its moving marker, for one full circle of the
markers.

## Success criteria
Success rule (MyoChallenge 2022 `myoChallengeBaodingP1-v1`, its `solved` held): each of the two balls is within 0.015
m of its own target marker, while the two markers circle the palm once every 5 s, held for 200 consecutive control
steps (5 s at 25 ms per step: one full circle).

Failure (MyoSuite's `done`, ends the episode with 0): a ball's height is below 1.25 m (it fell out of the hand).

The replay ends in success at the first control step at which the goal has held for 200 consecutive control steps, or
with 0 at a failure. The markers' path has 1,000 points: a replay that reaches step 1,000 without success fails.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array with one row per control step and one column
per actuator (muscles first, in the layout the tooling gives), as `s.save_trajectory(...)` writes it, at most
540,000 rows. After the agent's session it is replayed once, open-loop, from the frozen start in a fresh process
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
