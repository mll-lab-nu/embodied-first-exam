# MyoSuite · dex_hammer_use (standard)

| | |
|---|---|
| Task ID | `myosuite-dex-hammer-use-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | standard |
| Instance | `dex_hammer_use`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Pick up the hammer and swing it, following the recorded reference motion.

## Success criteria
Success rule (ours, on MyoDex `MyoHandHammerUse-v0` and its recorded reference motion of the hammer; MyoDex itself
defines no success): over the 99 control steps of the reference motion (20 ms each), the hammer's motion follows the
reference's. A step is on track when its errors are within these bounds:
- the hammer's displacement since the start is within 0.03 m of the reference's displacement since its start;
- the hammer's rotation since the start is within 0.5 rad of the reference's rotation since its start.

The task is passed if at least 90% of the 99 steps are on track, the last step is on track, and the displacement error
is never above 0.05 m.

Failure (MyoDex's termination, ends the episode with 0): the hammer's centre of mass is 0.25 m or more from the
reference's, or 0.25 m or more from the wrist.

The episode lasts 99 control steps (1.98 s), the length of the reference motion, and is judged when it ends. An
episode ended earlier by `/finish` or by the end of the agent's time fails. MyoDex's termination ends the episode with
0.

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
