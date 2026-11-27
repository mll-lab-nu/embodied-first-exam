# ABC Sim · ball-tray balancing (realtime)

| | |
|---|---|
| Task ID | `abc-sim-ball-tray-i00-realtime` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | realtime, slowdown 1 |
| Instance | `ball_tray`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hold the tray by both handles, one gripper on each, and keep the ball on the tray until the episode ends.

## Success criteria
The ball stays on the tray, and both handles are held for the whole countdown. The countdown (11 s of simulated time)
starts at the first control step at which the left gripper's fingers touch one handle bar and the right gripper's
fingers touch the other. During it, both handles count as held at a control step when both were touched within the
last 0.1 s. The ball is on the tray while its origin, in the frame of the tray's centre, is within 12.9 cm of the
centre along the tray's x axis and 12.4 cm along its y axis, and at least 8 mm above the centre along the tray's
normal.

Success: when the episode ends, the countdown has completed and the ball has been on the tray at every control step.
The episode ends as a failure at the first control step at which the ball is off the tray (also after the countdown
has completed), or at which a handle is not held during the countdown; after the countdown, letting go of a handle is
no failure. There is no hold window.

Graded: the live episode the simulator service ran; nothing is replayed. The clock does not stop: the episode starts
paused at the frozen start, and from the agent's first `submit` one control step runs every 0.034 s × S of wall time
(slowdown S = 1) whether or not the agent sends anything; when the planned targets run out, the last ones
are held. There is one episode and no reset. The episode ends when the agent sends `/finish` or when its session ends
(at the latest after 1 h); the task's own failure, where the rule above has one, and a simulator error also end
it. Success is never shown and never ends the episode. The verdict is on the state the episode ends in. Where the
condition must hold for 30 consecutive control steps, the service, after the agent is gone, keeps the robot's last
command for 30 more control steps (1.02 s), and the condition must hold at every one of them. An episode ended by the
task's failure or by a simulator error scores 0.

The scene is checked to start at the frozen instance (its state hash) before the agent is served; a mismatch is an
infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 10 GiB | 8192 | 5 GiB | — |
| verifier (as `main`) | 4 | 10 GiB | no cap | no GPU | 20 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## License
ABC Sim (`abc_sim` of [amazon-far/abc](https://github.com/amazon-far/abc) @ `d0832d1`) is released under the
[Apache License 2.0](https://github.com/amazon-far/abc/blob/d0832d12651d1b260a652861a14648dc5f3660c7/LICENSE). Its
simulator assets are under CC BY 4.0 (RoboCasa's Objaverse, LightWheel and AI-generated packs, Google Scanned Objects,
individually credited Sketchfab creators), CC0 (freepoly.org), MIT (the I2RT YAM robot model, a LIBERO drawer fixture)
and Apache-2.0 (everything modelled in-house); no non-commercial terms apply. The licences and credits ship in the image
at `/opt/abc/ASSET_LICENSES.md` (`images/abc-sim/ASSET_LICENSES.md`). The simulator is MuJoCo 3.6.0 (Apache License
2.0).
