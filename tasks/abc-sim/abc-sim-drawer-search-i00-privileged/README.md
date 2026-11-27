# ABC Sim · multi-drawer search (privileged)

| | |
|---|---|
| Task ID | `abc-sim-drawer-search-i00-privileged` |
| Benchmark | [ABC Sim](https://github.com/amazon-far/abc) (Allshire et al., 2026), upstream `amazon-far/abc@d0832d1` |
| Robot | Two I2RT YAM arms (6 revolute joints and a parallel two-finger gripper each), side by side at a table |
| Mode | privileged |
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
