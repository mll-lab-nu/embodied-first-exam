# MyoSuite · bimanual (privileged)

| | |
|---|---|
| Task ID | `myosuite-bimanual-i00-privileged` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm (63 muscles) next to a motorized prosthetic arm (MPL, 17 motors) |
| Mode | privileged |
| Instance | `bimanual`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Pick up the object with your right hand, pass it to the prosthetic left hand, and set it on top of the goal pillar. Each
hand must touch it for at least 1 s in total, and it must never touch the table or the floor.

## Success criteria
Success event (MyoChallenge 2024 `myoChallengeBimanual-v0`, its `solved` and its contact check): the event is the
first control step at which the object's centre is less than 0.17 m from the goal point on the goal pillar and the
object has touched the goal pillar on at least 10 control steps of the episode so far. At that step the object's
contact history must also pass MyoChallenge's contact check:
- the object has touched the MyoArm's hand on at least 100 control steps (1 s at 10 ms per step);
- the object has touched the prosthetic arm on at least 100 control steps;
- on each of the last 8 control steps the object touched the goal pillar and nothing else;
- the object never touched anything other than the MyoArm, the prosthesis, the start pillar and the goal pillar (the
  table and the floor included).

The order of the two hands is not checked. If the contact check fails at the step of the event, the episode ends with
0.

Failure (MyoSuite's `done`, ends the episode with 0): 10 s of simulated time pass without the event, or the object is
below 0.3 m.

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
