# TactileLab: third-party files and their licences

Some files under `embodied_first_exam/benchmarks/tactilelab/tactilelab_tasks/` (image `tactilelab-files`) and in the
data-only images `tactilelab-assets-files` and `tactilelab-thirdparty-files` come from third-party projects and keep their own
licences. Files whose licence is not confirmed are not in git: they are in the images `tactilelab-thirdparty-files` and
`tactilelab-assets-files` (below), whose source is the public Hugging Face dataset `MLL-Lab/embodied-first-exam-public`,
pinned by commit and checked by sha256; they can be taken down there if a licence does not allow them. This page lists
them for reviewers and users of the repository. The agent does not receive it: the files images carry only the files
listed in their `FILES.json` (PROTOCOL Appendix H.2, `ci_checks/check-agent-pointers.py`).

| Set (under `tactilelab_tasks/`) | Origin | Licence | What was done |
|---|---|---|---|
| `assets/objects/assembly/` (11 parts: table top and legs, drawer box and containers, lamp base, bulb, hood) | FurnitureBench part meshes | MIT, `assets/objects/assembly/LICENSE_FURNITUREBENCH_MIT.txt` (its copyright notice) | converted to binary USD, one mesh per part, convex colliders; `Annotation/*.json` (grasp and insertion poses) are this benchmark's |
| `assets/objects/mechanical/` (bolt, nut, three gears, gear base; image `tactilelab-thirdparty-files`, not in git) | NVIDIA Isaac Lab Factory assets (Isaac Sim 5.1 asset library) | NVIDIA's licence of the Isaac Sim assets — **to confirm (author)** | processed with `pxr`: articulation root and root fixed joint removed, solver iteration counts and contact / rest offsets baked, SDF colliders kept, `gear_medium` and `nut_m16` re-origined to the body centre; `Annotation/*.json` are this benchmark's |
| `assets/objects/insertion/` (HDMI plug and slot, test tube, tube base and slot, bottle cradle; image `tactilelab-thirdparty-files`, not in git) | UniVTAC object meshes | Apache-2.0 as stated by the author; no source URL yet — **to confirm (author)** | converted to USD; `Annotation/*.json` are this benchmark's |
| `assets/objects/bottle/bottle_5_xtrainer/` (image `tactilelab-thirdparty-files`, not in git) | `bottle_5`, from the object library of the simulator the tasks were first developed against | **to confirm (author)** | re-exported for the X-Trainer grasp |
| `assets/objects/dough/` | this benchmark: procedural USDs (box handle and head, `UsdPreviewSurface`, convex-hull colliders) | the repository's | — |
| `assets/robots/xtrainer_gsmini/` (images `tactilelab-thirdparty-files` and `tactilelab-assets-files`, not in git) | the X-Trainer dual-arm robot: URDF, meshes, USD | **to confirm (author)** | joint limits edited for simulation (notes at the top of `urdf/xtrainer_pink.urdf`); cuRobo configuration with collision spheres for the printed GelSight Mini fingers |
| `tactile/calib/gsmini/` | GelSight Mini calibration set of TacEx | MIT (declared in the project's README, which names no copyright holder; it has no separate licence file): `tactile/calib/gsmini/LICENSE_TACEX_MIT.txt` | `0.png`, `gelmap.npy`, `polycalib.npz` as distributed. `dataPack.npz` without its `imgs` member (the 22 MB calibration image stack, which the renderer never reads; `f0` and the small members are unchanged). `shadowTable.npz` holds the same values as flat float64 arrays with offsets instead of a pickled object array (`taxim.py` rebuilds the identical table; rendered images are bit-identical). `params.json` is this benchmark's |
| `tactile/taxim.py` | port of the GPU Taxim renderer (CMU RoboTouch), Si & Yuan 2022 | MIT, `tactile/LICENSE_TAXIM_MIT.txt` | torch backend, see the module docstring |

## Files over 2 MB: image `tactilelab-assets-files`

The repository holds no file over 2 MB (pull request checklist). These eight are in the same public Hugging Face dataset
as the third-party set below, pinned by commit and checked by sha256 in
`images/tactilelab-assets-files/FILES.json`; `python3 scripts/files_image.py fetch tactilelab-assets-files` puts them in
`images/tactilelab-assets-files/context/` (git-ignored), and the tasks' Dockerfiles copy them from the image over the package
directory. The robot files among them are of unconfirmed licence (the X-Trainer row above).

| File (under `tactilelab_tasks/`) | Size |
|---|---|
| `assets/robots/xtrainer_gsmini/usd/xtrainer.usd` (the robot; `xtrainer_gsmini.usd`, a layer over it, is in the image `tactilelab-thirdparty-files`) | 47.8 MB |
| `assets/robots/xtrainer_gsmini/meshes/base_link.STL`, `J1_5.STL`, `J1_6.STL`, `J2_5.STL`, `J2_6.STL` | 2.0 – 3.7 MB each |
| `tactile/calib/gsmini/gelmap.npy`, `polycalib.npz` | 2.5 MB, 2.3 MB |

## Files of unconfirmed licence: image `tactilelab-thirdparty-files`

The 54 files under `assets/objects/mechanical/`, `assets/objects/insertion/`, `assets/objects/bottle/` and
`assets/robots/xtrainer_gsmini/` (the rows marked "to confirm" above, with this benchmark's `Annotation/*.json` files next to
them) are in the public Hugging Face dataset `MLL-Lab/embodied-first-exam-public`, pinned by commit and checked by sha256
in `images/tactilelab-thirdparty-files/FILES.json`; `python3 scripts/files_image.py fetch tactilelab-thirdparty-files` puts
them in `images/tactilelab-thirdparty-files/context/` (git-ignored), and the tasks' Dockerfiles copy them
from the image over the package directory. They come back into git once their licences are confirmed.
