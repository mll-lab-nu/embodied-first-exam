# Embodied Olympics · inline slalom (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-inline-slalom-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `inline_slalom`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Skate the speed slalom: from the start box, skate on one foot through the 20 cones, passing them alternately left and
right, and over the end line.

## Success criteria
The robot wears inline skates (four wheels in a line on each). 20 free plastic cones (0.078 m high, 0.02 kg) stand on
the line y = 0, one every 0.8 m from 12 m beyond the start line; the end line is 0.8 m beyond the last cone. The
referee's stages, in order: start, cone line, cone 5, cone 10, cone 15, cone 20, finish.
- Start: the front of the robot's body at 0.40 m above the ground (the gate beam's height) crosses the start line,
  within 5 s of the start.
- Cone line: the front wheel of either skate reaches the front edge of the first cone. If not exactly one skate is
  on the ground at that moment, that is one penalty. The first skate that is alone on the ground is the supporting
  skate; from then on the other (free) skate must not touch the ground, and a change of feet is not allowed.
- Cones: a cone is passed when the supporting skate's centre reaches the cone; it is passed on the side of the line
  where that skate is. Cone 5, 10, 15 and 20 are stages.
- Finish: the front wheel of the supporting skate crosses the end line first, with that skate on the ground, after
  all 20 cones are passed.
- Penalties, counted at the finish: each kicked cone (its base centre more than 0.0335 m from its mark, or tilted more
  than 30 degrees), each missed interval (two cones in a row passed on the same side), and the first-cone penalty
  above (not counted again if the first cone is kicked). More than 4 penalties fail the attempt.

Fouls (each fails the attempt): no start within 5 s; not on one skate when the second cone is passed; the free skate
touches the ground; the free skate's front wheel crosses the end line first; the supporting skate is in the air at
the end line; the end line is crossed before all 20 cones are passed. Fall rule: on, the pelvis below 0.45 m or any
part of the robot other than the feet on the ground (the skates' wheels and frames may touch it). Time limit: 60 s
(6,000 control steps), from the start, not from the gate beam.

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
