# MyoSuite · relocate (standard)

| | |
|---|---|
| Task ID | `myosuite-relocate-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm: musculoskeletal model of the human shoulder, arm and hand |
| Mode | standard |
| Instance | `relocate`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Pick up the object on the table and put it in the receptacle.

## Success criteria
Success rule (MyoChallenge 2023 `myoChallengeRelocateP1-v0`, its `solved` held): the object is less than 0.1 m from
the target point in the receptacle (its orientation is not checked), held for 100 consecutive control steps (1 s at 10
ms per step).

Failure (MyoSuite's `done`, ends the episode with 0): the palm is more than 0.5 m from the object.

Reaching the goal does not end the episode. When the agent sends `/finish` or its time runs out while the goal is
being held but not yet for the full 100 steps, the service keeps stepping from that state with the last command held
until the hold is complete, the goal is lost or a failure happens (at most 100 more steps). The task is passed if the
goal has then held for at least 100 consecutive control steps up to the end. A failure ends the episode with 0, also
after a held goal.

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
