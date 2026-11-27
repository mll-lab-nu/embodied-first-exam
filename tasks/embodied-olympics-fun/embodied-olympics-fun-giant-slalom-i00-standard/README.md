# Embodied Olympics · giant slalom (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-giant-slalom-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `giant_slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Ski down the giant-slalom course in one run, through all 26 gates in order, and cross the finish line.

## Success criteria
A giant slalom run on a groomed slope falling at 18.3 degrees, each foot bound to a giant-slalom ski. The robot starts
on the level start platform with its boots 0.30 m behind the start line. 26 open gates: gate 1's line is 15 m down the
slope, each next one 24 m further; the inner pole of a gate's turning pair stands 2.0 m from the centre line, on the
left for gate 1 and then alternately right and left, and its gate line runs 5.0 m outwards from there. The finish line
is 640 m down the slope, 14 m wide, centred on the course. The referee's stages, in order: start, gate 1, ...,
gate 26, finish.
- Start: both feet cross the start line, by the robot's own action, within 20 s.
- Gate k: both ski tips and both feet have crossed its gate line going down the slope. A point that comes back up
  across a gate line must cross it again. Hitting a pole or a panel is allowed.
- Finish: after every gate, both feet cross the finish line between its posts.

Fouls (each fails the attempt): no start within 20 s; any of the four points goes down past a later gate's line while
a gate is not passed (a missed gate); both feet cross the finish line with a gate not passed, or outside the posts;
after the start the pelvis is slower than 0.10 m/s for 1.5 s (a stop). Fall rule (the snow's own): a part of the robot
other than the feet and the hands touches the snow (checked at every physics step), or the pelvis is less than 0.35 m
above the snow, measured along the slope's normal. Time limit: 150 s (15,000 control steps).

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
