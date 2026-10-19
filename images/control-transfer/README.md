# Control Transfer images

These images are **BUILD_ONLY**. Private flight-log-derived calibration and operator assets are not published by this repository. See [task fidelity and provenance](../../docs/benchmarks/control-transfer.md) before preparing assets.

From the repository root, provide a workspace containing `sim2realbench/vendor/unitree_rl_mjlab` at commit `1425b15f73bd4095f0df53709d7c389c3eb9e790`, a Menagerie checkout at `0059d4335f8156206f63a35662313385f7ad6d74`, and the separately prepared private flight-force asset:

```bash
python images/control-transfer/stage_nominal_assets.py \
  --workspace /operator/source-workspace \
  --go2-source /operator/mujoco_menagerie \
  --out /operator/nominal-assets \
  --private-go2-out /operator/private-go2
python images/control-transfer/neuralfly_visual.py --out /operator/skydio-visual-assets
python images/control-transfer/prepare_assets.py \
  --assets /operator/nominal-assets \
  --fly /operator/private-fly \
  --go2 /operator/private-go2 \
  --skydio /operator/skydio-visual-assets
bash images/control-transfer/build.sh
```

Both preparation steps require fresh output directories. Staged `assets/` are gitignored. The private flight directory must contain the pinned `forces.npz` described in [Neural Fly](../../docs/benchmarks/roboengineer-neuralfly.md); its fitting procedure (calibrate_fly.py) is kept with the benchmark's construction tooling, outside this repository. A different fitted artifact requires a separately versioned benchmark definition, not a silent replacement.

| Target | Contents | Tag |
|---|---|---|
| `nominal` | CPU MuJoCo and software rendering; public G1 training dependency subset and nominal Go2 geometry | `eai-control-transfer:0.2.0-nominal` |
| `train` | Nominal image plus pinned Torch (CUDA 12.8), MuJoCo Warp, mjlab, rsl-rl, export dependencies and EGL | `eai-control-transfer:0.2.0-train` |
| `evaluator` | Nominal runtime plus private force model and complete Go2 integrity manifest | `eai-control-transfer:0.2.0` |

Task code is copied by the tasks' Dockerfiles; it is not installed into these base images. Agent services use only `nominal` or `train`. The evaluator runs native CPU MuJoCo and numeric NumPy policies with no GPU devices, even when training uses a GPU.

The G1 public subset deliberately excludes non-G1 task configurations: upstream task discovery recursively imports configs, so retaining Go2/H1 configs alongside a G1-only robot initializer breaks training configuration. Reference actors and private evaluation modules are excluded from the nominal assets.

The final CPU targets have native Docker build and boundary checks; the G1 evaluator additionally ran four terrain cases with exact fresh-container replay. The CPU reference families have native Harbor validation. **`train` (0.2.0-train, board 0165)**: built FROM the 0.2.0-nominal tag (`TRAIN_ONLY=1 bash build.sh` on a host that pulled it; `BUILD_TRAIN=1` after the nominal build), torch 2.11.0+cu128 from the PyTorch CUDA 12.8 index (NVIDIA driver >= 570; the AWS hosts run 580.178.04), `pip check` clean, numpy 2.3.1 / mujoco 3.5.0 unchanged from nominal; full Harbor training / export / deployment trials on two L40S hosts (docs/benchmarks/roboengineer-g1.md). EGL rendering is not used by training and not tested: the task's compose file grants the GPU's compute capability only.

Version 0.1.1 adds checksum-pinned Apache-2.0 Skydio appearance assets. The operator
preparation command downloads only those pinned public files; runtime images never
download them. The Docker build verifies every mesh/texture/license hash. Existing
tasks remain on their original 0.1.0 image tags; only the explicit
`neural-fly-general-skydio-v1` observation revision selects 0.1.1 and enables
`NEURALFLY_VISUAL_STYLE=skydio-x2/1` in both nominal and evaluator environments.
The 0.1.1 build and native Harbor run are unverified locally; the native acceptance
described above belongs to 0.1.0. Do not overwrite older image tags.
