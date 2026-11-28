# Embodied Olympics · snowboard (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-snowboard-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `snowboard`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Snowboard down the parallel-slalom course in one run, through all 18 gates in order, and cross the finish line.

## Success criteria
A parallel-slalom course on a groomed slope falling at 18.3 degrees, 40 m wide. Both feet are bound across one
snowboard. The robot stands on the level start platform at the top with the board's nose pointing down the slope;
the start signal is at t = 0 and nothing pushes it. The referee's stages, in order: start, gate 1 to gate 18, finish.
- Start: both feet cross the start line (the platform's edge), within 20 s of the signal.
- Gate 1 to gate 18: the gate lines are 13.5 m apart down the slope, the first 12 m down from the slope's reference
  line. Each gate line runs across the slope from its turning pole, 1 m from the centre line, to its outside pole 4 m
  further out; gate 1's poles are on the left looking down the slope, then right and left in turn. A gate is passed
  when the board's nose and tail and both feet have each crossed its gate line going down the slope; a point that
  comes back up across a gate line must cross it again. Gates count only in order. Hitting or folding a pole is
  allowed.
- Finish: after every gate, both feet cross the finish line (256 m down the slope) between its posts, 12 m apart and
  centred on the course. The success is called at that moment.

Fouls (each fails the attempt): the robot has not left the platform 20 s after the signal; any of the four points
passes down over a later gate's line, or both feet over the finish line, while a gate is not passed; the feet over the
finish line but outside its posts; after the start, the pelvis slower than 0.1 m/s for 1.5 s. The generic fall rule
is off; the snow's own fall rule (a failure at any time): any part other than the feet and hands touching the snow
(judged every physics step), or the pelvis less than 0.35 m above the snow, measured along the slope's normal. Time
limit: 90 s (9,000 control steps).

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
