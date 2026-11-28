# MyoSuite · die_reorient (standard)

| | |
|---|---|
| Task ID | `myosuite-die-reorient-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | standard |
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
