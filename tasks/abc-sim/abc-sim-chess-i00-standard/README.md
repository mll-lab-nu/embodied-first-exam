# ABC Sim · set up chess pieces (standard)

| | |
|---|---|
| Task ID | `abc-sim-chess-i00-standard` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | standard |
| Instance | `chess`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Put the black pieces that stand next to the board back on their empty starting squares, standing upright.

## Success criteria
Each of the six black target pieces stands upright on a starting square of its own kind that it left empty. Pieces
of one kind are matched to that kind's empty squares, nearest first. A matched piece counts when its origin is within
2.8 cm of the square's centre in the board's plane and within 5 cm of it along the board's normal (the squares are
taken in the board's current frame, so they move with the board), and it stands upright: its own vertical axis
points up with a component of at least 0.85 (about 32° from vertical). The other pieces are not checked. All the target
pieces must count at once, for 30 consecutive control steps (1.02 s).

Graded: the live episode the simulator service ran; nothing is replayed. There is one episode and no reset. The
episode ends when the agent sends `/finish` or when its session ends (at the latest after 1 h); the task's own
failure, where the rule above has one, and a simulator error also end it. Success is never shown and never ends the
episode. The verdict is on the state the episode ends in. Where the condition must hold for 30 consecutive control
steps, the service, after the agent is gone, keeps the robot's last command for 30 more control steps (1.02 s), and
the condition must hold at every one of them. An episode ended by the task's failure or by a simulator error scores 0.

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
