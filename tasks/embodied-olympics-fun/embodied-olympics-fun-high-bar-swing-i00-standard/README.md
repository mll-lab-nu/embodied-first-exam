# Embodied Olympics · high bar giant swing (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-high-bar-swing-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `high_bar_swing`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Jump from the block, catch the high bar with both hands and swing one full circle round it with your body straight,
without letting go.

## Success criteria
The bar is 0.028 m thick, 2.80 m above the floor, fixed (it does not turn). The robot starts standing on a 1.1 m block
behind it, hands open; its three-finger hands hold the bar by contact and friction only. The referee's stages, in
order: jumped, caught the bar, over the top, full circle.
- Jumped: the robot leaves the block without holding the bar. It may land back on the block and jump again.
- Caught the bar: both hands grasp the bar (the bar touches the hand's index or middle finger and its thumb or palm)
  after the robot has left the block.
- Over the top and full circle: the swing angle is the angle between straight down and the line from the bar to the
  robot's centre of mass, seen from the side. After the catch it must travel 360 degrees in one direction. A turn back
  of more than 5 degrees starts the count again from there. Whenever the centre of mass is higher than the bar it must
  be at least 0.59 m from the midpoint of the two wrists; closer, and the count starts again. "Over the top" latches
  when the counted travel passes straight up; the success is called when it reaches 360 degrees.

Fouls (each fails the attempt): both hands grasp the bar before the robot has left the block; before the catch, any
part of the robot touches the mats or the floor; any part other than the hands touches the bar; after the catch, a
hand is off the bar (touching it with no part) for more than 0.05 s, with no regrip; after the catch, the robot touches
the block, the uprights, the mats or the floor. The generic fall rule is off; these rules replace it. Time limit: 60 s
(6,000 control steps).

Graded: the live attempt, judged by the referee in the simulator service as it runs; nothing is replayed. The referee's
success call is an event: once it is made at some control step, the attempt is a success. It is never shown to the
agent and does not end the attempt: the physics goes on until the agent's `/finish`, the attempt's time limit, or the
end of the agent's time (2 h), and nothing after the call undoes it. A failure the referee calls before any
success (a foul, a fall, the physics diverging) ends the attempt at once with 0. Reaching the time limit or the end of
the session without a success call scores 0. The agent has 5 resets, each starting a new attempt from the
frozen start; only the last attempt (the one after the last reset) is graded, and a success in an earlier attempt does
not count. A simulator error raised by the agent's own call ends the attempt with 0. An attempt that does not start
from the frozen instance, or a service crash outside the agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## License
The Embodied Olympics robot library and running-policy port ([CHIGUI0/roboolympics](https://github.com/CHIGUI0/roboolympics)
@ `7df999b`, a private repository) is released under the MIT License (`LICENSE.roboolympics` in the image); this
benchmark's venues and referees are MIT too. Third-party parts in the image: the Unitree G1 model and meshes from MuJoCo
Menagerie (BSD-3-Clause), the Unitree H1-2 model, meshes and walking policy and the G1 walking policy from
unitree_rl_gym (BSD-3-Clause), the G1 running policy from C1801SYQ/g1_running (Apache-2.0), FALCON's G1 walking policy
from LeCAR-Lab/FALCON (MIT) and the WBC-AGILE G1 walking policy from NVIDIA (Apache-2.0). No non-commercial terms apply.
