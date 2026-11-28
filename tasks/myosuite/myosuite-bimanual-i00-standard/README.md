# MyoSuite · bimanual (standard)

| | |
|---|---|
| Task ID | `myosuite-bimanual-i00-standard` |
| Benchmark | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), upstream `MyoHub/myosuite@5635e1a` |
| Robot | MyoArm (63 muscles) next to a motorized prosthetic arm (MPL, 17 motors) |
| Mode | standard |
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
