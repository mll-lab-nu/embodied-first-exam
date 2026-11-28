# MyoSuite · hand_pose (standard)

| | |
|---|---|
| Task ID | `myosuite-hand-pose-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoHand: musculoskeletal model of the human forearm and hand, 39 muscles |
| Mode | standard |
| Instance | `hand_pose`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Put your hand in the target pose that the see-through fingertip markers show, and hold it for a second. The pose's joint
angles are at the end of Robot Interface.

## Success criteria
Success rule (MyoSuite `myoHandPoseFixed-v0`, its `solved` held): the hand and wrist joints are near the target pose:
the length of the vector of joint-angle errors over all the hand's joints is less than 0.7 rad, held for 50
consecutive control steps (1 s at 20 ms per step).

Failure (MyoSuite's `done`, ends the episode with 0): that error is more than 2π rad.

Reaching the goal does not end the episode. When the agent sends `/finish` or its time runs out while the goal is
being held but not yet for the full 50 steps, the service keeps stepping from that state with the last command held
until the hold is complete, the goal is lost or a failure happens (at most 50 more steps). The task is passed if the
goal has then held for at least 50 consecutive control steps up to the end. A failure ends the episode with 0, also
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
