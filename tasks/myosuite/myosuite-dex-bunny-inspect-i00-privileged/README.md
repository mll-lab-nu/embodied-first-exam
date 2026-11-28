# MyoSuite · dex_bunny_inspect (privileged)

| | |
|---|---|
| Task ID | `myosuite-dex-bunny-inspect-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | privileged |
| Instance | `dex_bunny_inspect`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Pick up the bunny and turn it to look it over, following the recorded reference motion.

## Success criteria
Success rule (ours, on MyoDex `MyoHandStanfordbunnyInspect-v0` and its recorded reference motion of the bunny; MyoDex
itself defines no success): over the 99 control steps of the reference motion (20 ms each), the bunny's motion follows
the reference's. A step is on track when its errors are within these bounds:
- the bunny's displacement since the start is within 0.03 m of the reference's displacement since its start;
- the bunny's rotation since the start is within 0.5 rad of the reference's rotation since its start.

The task is passed if at least 90% of the 99 steps are on track, the last step is on track, and the displacement error
is never above 0.05 m.

Failure (MyoDex's termination, ends the episode with 0): the bunny's centre of mass is 0.25 m or more from the
reference's, or 0.25 m or more from the wrist.

The replay lasts 99 control steps (1.98 s), the length of the reference motion, and is judged at its last step; it
ends earlier, with 0, at MyoDex's termination. A trajectory of fewer rows fails.

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
