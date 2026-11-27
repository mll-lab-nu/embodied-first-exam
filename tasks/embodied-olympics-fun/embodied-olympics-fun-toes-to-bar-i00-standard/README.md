# Embodied Olympics · toes to bar (standard)

| | |
|---|---|
| Task ID | `embodied-olympics-fun-toes-to-bar-i00-standard` |
| Benchmark | [Embodied Olympics - Fun](https://github.com/CHIGUI0/roboolympics) (Embodied Olympics authors, 2026), upstream `CHIGUI0/roboolympics@7df999b` |
| Robot | Unitree G1 humanoid (1.32 m, 33 kg, 29 joints), with Unitree's walking and running policies |
| Mode | standard |
| Instance | `toes_to_bar`, seed 0 |
| Time limit | 2 h |
| Reference solution | Included |

## Task
Do five toes-to-bar: hanging from the bar, bring both feet up to touch it between your hands and go back to a full hang,
without letting go.

## Success criteria
A fixed bar, 0.028 m thick, 2.8 m above the floor and 2.4 m long between its two uprights. The robot starts hanging
with each three-finger hand closed round the bar; the hands hold it by contact and friction only. A hand is on the
bar while the bar touches any part of it (fingers, thumb or palm). The referee's stages, in order: rep 1, rep 2, rep
3, rep 4, rep 5. Each repetition has two parts, in this order:
- Touch: both feet touch the bar at the same moment, each at a point between the two hands' grasp centres (shins,
  knees or other parts of the legs on the bar are not a touch, and are not a foul).
- Hang: afterwards both foot centres are at the same moment at least 1.4 m below the bar and behind it (the bar's
  side the robot hangs from). The repetition is counted at the hang; the next one needs a new touch.
The success is called at the hang of repetition 5. Swinging and bending the knees are allowed.

Fouls (each fails the attempt at once):
- a hand is off the bar for more than 0.05 s (let go or torn out; there is no re-grip);
- an arm, the trunk or the head touches the bar (only the hands and the legs may);
- any part of the robot touches the uprights, the mats or the floor.
The generic fall rule is off: the ground rule above replaces it. Time limit: 60 s (6,000 control steps).

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
