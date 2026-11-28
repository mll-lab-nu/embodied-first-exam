# Embodied Olympics · trampoline (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-trampoline-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `trampoline`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
On the trampoline, do one tuck jump, land on both feet, then stop the bounce and stand still.

## Success criteria
A competition trampoline: the bed 4.28 m by 2.14 m, 1.155 m above the floor; the robot starts at its centre. A flight is
a time of at least 0.1 s in which nothing of the robot touches anything; the reference height is the robot's centre of
mass when it stands at the start. Straight bounces before the tuck jump are free. The referee's stages, in order: tuck
jump, landing, stop.
- Tuck jump: the first flight in which the body is not straight. At some moment of its middle half (from a quarter to
  three quarters of the flight's time) both legs are tucked, held for at least 0.05 s without a break: the angle at the
  hip (shoulder, hip, knee) and at the knee (hip, knee, ankle) 135 degrees or less (180 degrees is straight). In the
  flight the centre of mass rises at least 0.1 m above the reference height. The stage is called at its landing.
- Landing: the tuck jump's landing, on the feet only, both feet on the bed within 0.1 s of each other.
- Stop: the robot then stands still for 3.0 s without a break: only the feet on the bed, the torso within about 20
  degrees of upright, the pelvis slower than 0.35 m/s, the ankles at most 0.28 m apart. The success is called at the end
  of the 3.0 s.
After the tuck jump's landing one more flight, an out-bounce, is allowed; it must be straight (hips and knees more open
than 135 degrees through its middle half), and the stop then follows its landing.

Fouls (each fails the attempt at once):
- a tuck whose centre of mass rises less than 0.1 m above the reference height;
- a flight before the tuck jump in which a hip or a knee closes to 135 degrees or less in the middle half without the
  tuck (another element);
- a second flight after the tuck jump, or an out-bounce that is not straight;
- a landing in which the second foot reaches the bed more than 0.1 s after the first;
- any part of the robot other than the feet on the bed;
- touching anything other than the bed (the padding over the frame and springs, the end platforms, the floor).
The generic fall rule is off: these rules replace it. Time limit: 30 s (3,000 control steps).

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
