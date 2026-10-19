# Control Transfer images

The evaluator image is **BUILD_ONLY** (private): flight-log-derived calibration and operator assets are not published by this repository. The agents' bases `nominal` and `train` hold public assets only and are public (`ghcr.io/mll-lab-nu/efe`). See [task fidelity and provenance](../../tasks/roboengineer/control-transfer.md) before preparing assets.

From the repository root (git, python3 and network access to github.com and PyPI):

```bash
images/control-transfer/fetch_assets.sh --fit-fly   # pinned public sources -> assets/, Neural Fly force fit made locally
BUILD_TRAIN=1 bash images/control-transfer/build.sh
```

`fetch_assets.sh` clones unitree_rl_mjlab @ `1425b15f73bd4095f0df53709d7c389c3eb9e790` and MuJoCo Menagerie @
`0059d4335f8156206f63a35662313385f7ad6d74` (Go2), downloads the Skydio X2 files from Menagerie @ `d7b481ba` with their
sha256 checked, and runs `stage_nominal_assets.py`, `neuralfly_visual.py` and `prepare_assets.py`. `--fit-fly` also
clones aerorobotics/neural-fly @ `0ed50246b1f1db194e8f0726749351636d3501bf` and fits the Neural Fly force surrogate locally
with `calibrate_fly.py` in a throwaway `python:3.12.14-slim` container (numpy 2.3.1, mujoco 3.5.0; needs docker and PyPI):
the result is byte-identical to the pinned `forces.npz` (`8e1c148e…`), which the script checks. `--fly <dir>` uses a
`forces.npz` you already have (same check). With neither, the evaluator holds no force asset and the
`roboengineer-neuralfly-*` tasks refuse to start; all other tasks run.

Both preparation steps require fresh output directories. Staged `assets/` are gitignored. The private flight directory must contain the pinned `forces.npz` described in [Neural Fly](../../tasks/roboengineer/neuralfly.md); `calibrate_fly.py` is its fitting procedure. The fit is never published: the Neural-Fly logs are "for personal and educational use only", with written permission from the authors required for further use. A different fitted artifact requires a separately versioned benchmark definition, not a silent replacement.

| Target | Contents | Tag |
|---|---|---|
| `nominal` | CPU MuJoCo and software rendering; public G1 training dependency subset and nominal Go2 geometry | `efe:control-transfer-0.2.0-nominal` |
| `train` | Nominal image plus pinned Torch (CUDA 12.8), MuJoCo Warp, mjlab, rsl-rl, export dependencies and EGL | `efe:control-transfer-0.2.0-train` |
| `evaluator` | Nominal runtime plus private force model and complete Go2 integrity manifest | `efe-private:control-transfer-0.2.0` |

Task code is copied by the tasks' Dockerfiles; it is not installed into these base images. Agent services use only `nominal` or `train`. The evaluator runs native CPU MuJoCo and numeric NumPy policies with no GPU devices, even when training uses a GPU.

The G1 public subset deliberately excludes non-G1 task configurations: upstream task discovery recursively imports configs, so retaining Go2/H1 configs alongside a G1-only robot initializer breaks training configuration. Reference actors and private evaluation modules are excluded from the nominal assets.

The final CPU targets have native Docker build and boundary checks; the G1 evaluator additionally ran four terrain cases with exact fresh-container replay. The CPU reference families have native Harbor validation. **`train` (0.2.0-train, board 0165)**: built FROM the 0.2.0-nominal tag (`TRAIN_ONLY=1 bash build.sh` on a host that pulled it; `BUILD_TRAIN=1` after the nominal build), torch 2.11.0+cu128 from the PyTorch CUDA 12.8 index (NVIDIA driver >= 570; the AWS hosts run 580.178.04), `pip check` clean, numpy 2.3.1 / mujoco 3.5.0 unchanged from nominal; full Harbor training / export / deployment trials on two L40S hosts (tasks/roboengineer/g1.md). EGL rendering is not used by training and not tested: the task's compose file grants the GPU's compute capability only.

Version 0.1.1 adds checksum-pinned Apache-2.0 Skydio appearance assets. The operator
preparation command downloads only those pinned public files; runtime images never
download them. The Docker build verifies every mesh/texture/license hash. Existing
tasks remain on their original 0.1.0 image tags; only the explicit
`neural-fly-general-skydio-v1` observation revision selects 0.1.1 and enables
`NEURALFLY_VISUAL_STYLE=skydio-x2/1` in both nominal and evaluator environments.
The 0.1.1 build and native Harbor run are unverified locally; the native acceptance
described above belongs to 0.1.0. Do not overwrite older image tags.
