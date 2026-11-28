# Embodied Olympics · 50 m sprint (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-sprint-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `sprint`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Run the 50 m: start on the gun and sprint down your lane until your torso reaches the finish line.

## Success criteria
A straight 50 m lane, 1.22 m wide; the robot stands just behind the start line facing the finish. "On your marks" is
at t = 0, "set" 2 s later, and the gun between 1.2 and 2.2 s after "set" (fixed for the task, not announced); a lamp
shows the phase. The referee's stages, in order: start, finish.
- Start: the robot's start movement, the first moment its pelvis is more than 0.05 m from where it was at "set", or
  the front end of a foot reaches the start line (on the ground or in the air). It must come at least 0.1 s after the
  gun.
- Finish: the leading point of the torso (not the head, arms, legs or feet) reaches the finish line, within 30 s of
  the gun. The success is called at that moment.

Fouls (each fails the attempt): a false start (a start movement before the gun or less than 0.1 s after it, or a
foot reaching the start line at any time before that, "set" included); from the gun on, the pelvis more than 0.61 m
to either side of the lane's centre line; 30 s after the gun without a finish. The generic fall rule is off: a fall
does not end the race, and the robot may get up and run on, but from the gun on, the pelvis below 0.4 m for 10 s in a
row fails it. Time limit: 34.2 s (3,420 control steps), with the 30 s from the gun ending the attempt first.

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
