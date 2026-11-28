# Embodied Olympics · keepie-uppie (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-juggling-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `juggling`, seed 0 |
| Time limit | 2 h |
| Reference solution | None |

## Task
Drop the football from your hands and keep it up for ten counted touches with your feet, legs or head, without it
touching the ground.

## Success criteria
A size 5 football starts held between the robot's palms. The referee's stages, in order: touch 1, touch 2, ...,
touch 10.
- Drop: the ball leaves the hands (clear of them for 0.03 s). Before the drop, only the hands may touch the ball.
- A touch is contact by a foot, shin, thigh or the head; contacts less than 0.05 s apart are one touch. A touch lasts
  at most 0.15 s. It counts when the ball's centre then rises at least 0.22 m above its height at the start of the
  touch before it is touched again. From the second touch on, the ball must also leave at no less than 0.95 times
  the speed it came in with; a touch that sends it off slower is not counted, and is not a fault.
- Touch 10 is the tenth counted touch.

Fouls (each fails the attempt): the ball touches the ground; a hand or arm touches the ball later than 0.15 s after
the drop (handball); the trunk touches the ball; a touch lasts longer than 0.15 s (carrying); the ball is touched
again before it has risen 0.22 m. Fall rule: on, the pelvis below 0.35 m or any part other than the feet on the
ground. Time limit: 30 s (3,000 control steps).

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
