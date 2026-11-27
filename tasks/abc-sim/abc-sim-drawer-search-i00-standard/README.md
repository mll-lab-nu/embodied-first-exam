# ABC Sim · multi-drawer search (standard)

| | |
|---|---|
| Task ID | `abc-sim-drawer-search-i00-standard` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | standard |
| Instance | `drawer_search`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Find the measuring cup in the drawers and put it in the bin, then do the same with the dish brush.

## Success criteria
The measuring cup and then the dish brush have been counted in the bin. An object counts when its origin lies inside
the bin's goal region (a box fixed in the bin's frame). The dish brush is looked at only from the control step at which
the measuring cup is first counted: at that step or any later one at which it is in the region, it is counted too.
Once both are counted, the condition stays met for the rest of the episode, whether or not they stay in the bin; it
must then hold for 30 consecutive control steps (1.02 s).

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
