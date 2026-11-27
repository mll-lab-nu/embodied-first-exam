# MyoSuite · chase_tag (standard)

| | |
|---|---|
| Task ID | `myosuite-chase-tag-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoLegs: musculoskeletal model of the human legs and pelvis |
| Mode | standard |
| Opponent | Opponent body in the arena (scripted, MyoChallenge 2023's opponent; the frozen start drew its `stationary` policy): it stands still |
| Instance | `chase_tag`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Tag the opponent: get right next to it.

## Success criteria
Success event (MyoChallenge 2023 `myoChallengeChaseTagP1-v0`, chase task: a tag): the pelvis comes within 0.5 m of the
opponent, measured horizontally.

Failure (MyoSuite's `done`, ends the episode with 0):
- 20 s of simulated time pass without a tag;
- the pelvis is below 0.5 m (a fall);
- the pelvis leaves the arena: more than 6.5 m from its centre along either axis.

The success event does not end the episode. Once it has happened the task is passed, even if a failure above ends the
episode later. Before it, a failure ends the episode with 0.

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
