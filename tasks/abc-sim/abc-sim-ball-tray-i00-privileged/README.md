# ABC Sim · ball-tray balancing (privileged)

| | |
|---|---|
| Task ID | `abc-sim-ball-tray-i00-privileged` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | privileged |
| Instance | `ball_tray`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Hold the tray by both handles, one gripper on each, and keep the ball on the tray until the episode ends.

## Success criteria
The ball stays on the tray, and both handles are held for the whole countdown. The countdown (11 s) starts at the
first control step at which the left gripper's fingers touch one handle bar and the right gripper's fingers touch the
other. During it, both handles count as held at a control step when both were touched within the last 0.1 s. The ball
is on the tray while its origin, in the frame of the tray's centre, is within 12.9 cm of the centre along the tray's
x axis and 12.4 cm along its y axis, and at least 8 mm above the centre along the tray's normal.

The episode ends in success at the control step the countdown completes. It ends as a failure at the first control
step at which the ball is off the tray (before or during the countdown), or at which a handle is not held during the
countdown. There is no hold window.

The verifier, in a separate sandbox without network, replays `/app/output/trajectory.npz` (array `actions`, shape
(T, 14) with 1 ≤ T ≤ 20,000, all values finite) once, open-loop, in a fresh process from its own copy of the frozen
instance, one row per 0.034 s control step. The rule above is checked after every control step. Where the condition
must hold for 30 consecutive control steps, the episode ends in success at the 30th of them. The replay stops at the
step the episode ends; later rows are not run. The task scores 1 when the replayed episode ends in success; a
trajectory whose rows run out first scores 0.

A missing file scores 0, and so does an invalid one: not a readable `.npz`, no `actions` array, a shape other than
(T, 14), a NaN or infinite value, T outside 1 to 20,000, or a `family` entry that names another family. A replay that
does not start at the instance's recorded state hash, or that gives no result within 40 min, is a grader error, not a
score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 8192 | 5 GiB | 10 GiB |
| verifier | 4 | 8 GiB | no cap | 5 GiB | no cap |

- GPU: any NVIDIA GPU, held by `main`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## License
ABC Sim (`abc_sim` of [amazon-far/abc](https://github.com/amazon-far/abc) @ `d0832d1`) is released under the
[Apache License 2.0](https://github.com/amazon-far/abc/blob/d0832d12651d1b260a652861a14648dc5f3660c7/LICENSE). Its
simulator assets are under CC BY 4.0 (RoboCasa's Objaverse, LightWheel and AI-generated packs, Google Scanned Objects,
individually credited Sketchfab creators), CC0 (freepoly.org), MIT (the I2RT YAM robot model, a LIBERO drawer fixture)
and Apache-2.0 (everything modelled in-house); no non-commercial terms apply. The licences and credits ship in the image
at `/opt/abc/ASSET_LICENSES.md` (`images/abc-sim/ASSET_LICENSES.md`). The simulator is MuJoCo 3.6.0 (Apache License
2.0).
