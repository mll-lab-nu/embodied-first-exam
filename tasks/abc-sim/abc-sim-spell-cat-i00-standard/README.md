# ABC Sim · spell cat (standard)

| | |
|---|---|
| Task ID | `abc-sim-spell-cat-i00-standard` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | standard |
| Instance | `spell_cat`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Spell CAT with the letter blocks: lay C, A and T side by side in a straight row on the table, each with a letter face up
or down, reading from left to right as the arms face the table.

## Success criteria
The letter blocks C, A and T form a row in that order, from left to right as the arms face the table: each
block's origin is 1.5 to 6 cm to the right (-y) of the previous block's and at most 3 cm in front of or behind it (x).
Each of these blocks rests at table height (its origin within 2 cm of the table's surface plus the block's own
half-height) with a letter face up or down (that face's normal within about 32° of vertical). The other blocks are not
checked. This must hold for 30 consecutive control steps (1.02 s).

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
