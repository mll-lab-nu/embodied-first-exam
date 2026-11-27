# Embodied Olympics · clean and jerk (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-clean-and-jerk-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree H1-2 humanoid (1.78 m, 67 kg, 27 joints), with Unitree's walking policy |
| Mode | standard |
| Instance | `clean_and_jerk`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Clean and jerk the barbell: lift it from its blocks with both hands to your shoulders, then overhead on locked arms, and
hold it still until the down signal.

## Success criteria
A 5.0 kg technique barbell rests by its sleeves on two blocks on a 4.0 m by 4.0 m platform. A hand holds the bar while
the bar's grip section touches that hand's fingers (a break of up to 0.05 s is not letting go). The referee's stages,
in order: lift-off, clean, overhead, down signal.
- Lift-off: the bar's axis rises 0.03 m above its rest, which must happen with both hands holding it. Once the bar's
  centre has been 0.48 m above the platform the attempt has begun: from then on letting go with either hand, or any
  part of the barbell touching the platform or a block, fails.
- Clean: for 0.5 s without a break, the bar's axis is within 0.15 m of both shoulder joints, both hands hold it, both
  knees are within 10 degrees of straight, both feet are on the platform and in line (centres at most 0.05 m apart
  square to the bar), the bar and the pelvis are slower than 0.1 m/s, and the robot is under the bar (trunk upright,
  tilt cosine at least 0.94; the bar's centre within 0.25 m horizontally of the point between the shoulder joints; the
  bar within 20 degrees of the shoulder line, seen from above). The bar's centre more than 0.25 m above the centre of
  the head before the clean fails the attempt.
- Overhead: the bar's centre at least 0.25 m above the centre of the head, both hands on it, both elbows within 10
  degrees of straight.
- Down signal: the overhead position together with every condition of the clean except the shoulder distance (knees,
  feet in line, both on the platform, motionless, under the bar) held for 2.0 s without a break. Under a bar tilted
  more than 60 degrees from level the feet never count as in line. The success is called at the down signal.

Fouls (each fails the attempt at once): any part of the robot other than the feet touches the platform; any part of
the robot touches a block; any part of the robot or the barbell touches the floor beside the platform. The generic fall
rule is off. Time limit: 60 s (6,000 control steps).

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
