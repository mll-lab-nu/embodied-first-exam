# eai-robosafe: where its contents come from

The snapshot starts from the unreleased RoboSafeBench 0.5.4.dev1 source pinned in `source.env`, then applies the exact public metadata projection in `PUBLIC_SOURCE_PROJECTION.json`. Each frozen instance records its own source; historical files still require current-candidate validation before release.
RoboSafeBench's source repository is not public yet: the snapshot in `context/` is what this
repository builds from, and `fetch_context.sh --check <clone>` lets a maintainer with access compare it with the
repository.

The projection replaces 56 historical source locators in exactly 20 asset JSON files with public provenance identifiers and refreshes only their child byte counts and SHA values in the 688-file manifest. It changes no texture, geometry, material, physics value or executable native source. The bridge records relative paths, JSON pointers and original/projected hashes without publishing private locator values. `public_source_projection.py` replays this fixed transformation during context preparation and rejects any different original bytes or extra changes. This projected package is identified separately from the original native byte map; it is not claimed byte-identical to that map.

| Part | Source | How it is checked |
|---|---|---|
| `context/robosafe-src/` | RoboSafeBench at the commit in `source.env`, as `git archive` gives it (README.md's sentence about the repository's own documents rewritten to point at `docs/benchmarks/robosafe.md`): the package `robosafebench/`, `pyproject.toml`, `README.md`, `LICENSE` (Apache-2.0), `LICENSE-assets` (CC BY 4.0, its generated assets), `assets/third_party/README.md` and the DejaVu font (`assets/third_party/fonts/`, its own licence) | `context/robosafe-src.sha256`, every file, in the image build; `fetch_context.sh --check <clone>` against RoboSafeBench |
| robot models | MuJoCo Menagerie (public; Apache-2.0 and the models' own licences, each model's `LICENSE` beside it) at `MENAGERIE_COMMIT`, only the files RoboSafeBench vendors under `assets/third_party/mujoco_menagerie/` (byte-for-byte copies of that commit) | `context/menagerie.sha256`, every file, in the image build |
| G1 assets (`context/robosafe-src/assets/third_party/bigym2/`, RoboSafeBench 0.5.2) | BiGym 2.0's G1 model and controller configuration as RoboSafeBench vendors them: the model and config under Apache-2.0 (`LICENSE`, `NOTICE` kept), the Unitree G1 meshes under BSD-3-Clause (`g1/LICENSE.unitree`; the MJCF packaging's `g1/LICENSE`, Apache-2.0); the walking controller's policy weights `wbc/*.onnx` (NVIDIA GR00T Whole-Body Control) under the NVIDIA Open Model License, NOT Apache-2.0 or CC BY 4.0: its text (`wbc/NVIDIA Open Model License.txt`) and the notice "Licensed by NVIDIA Corporation under the NVIDIA Open Model License" (`wbc/NOTICE`) ship beside them | `context/robosafe-src.sha256`, every file, in the image build; RoboSafeBench's own sha256 of the weights (`robosafebench/sim/wbc.py` `WEIGHTS_SHA256`) when they load |
| Python stack | PyPI, `requirements.txt` (MuJoCo 3.8.1, numpy 2.2.6, PyOpenGL, Pillow, imageio + imageio-ffmpeg; onnxruntime 1.28.0 with flatbuffers, protobuf and packaging for the G1's controller) | pinned versions, `pip check` |
| system | Debian's OSMesa and GL libraries, git | the pinned Python base image |

The snapshot keeps the complete native `robosafebench` package, including its harness, diagnosis tools,
command line, HTTP server and agent-facing documents. `fetch_context.sh` does not prune package modules.
The trusted simulator installs this package so that native validation, subprocess replay and the runtime
use the same source. Packaging code alone does not invoke a harness or a model; the benchmark's simulator
service does not start either. The verdict's reading of an exit's text (`named`) is in `verify/words.py`.

The families' scripted reference methods also remain in this trusted simulator package: the episode's
checks and the oracle compiler use the same classes. The task's agent image contains only its client,
without this simulator package or its reference methods. Generated oracle plans live under `solution/`;
trusted validation sidecars remain outside the generated task directories. This source provenance
statement is not a substitute for the final image's isolation and installed-runtime checks.

The `realism_v3` pack's `.png` / `.obj` files are not committed (`images/robosafe/.gitignore`): `python3 scripts/robosafe/assets.py fetch` restores them from the Hugging Face dataset pinned in `scripts/robosafe/assets.json` (`MLL-Lab/robosafe-assets`, public) before a build. After a context refresh, `assets.py export <dir>` lays them out for upload and `assets.py pin <dir> <revision>` records the new revision.

To move to another RoboSafeBench commit: set `ROBOSAFEBENCH_COMMIT` and `ROBOSAFEBENCH_VERSION` in `source.env`, bump `VERSION`,
run `fetch_context.sh <clone>` (needs a clone with that commit), rebuild, and freeze the instances again
(`scripts/robosafe/AUTHORING.md`). Never rebuild a tag that trials have used.

The native `robosafebench/client/remote.py` client and `verify.verify_in_subprocess`
(`verify/__init__.py`) are retained with the rest of the package. The latter runs
`python -m robosafebench verify`; its `__main__.py` entry point is retained as well.
Only the native admission workflow invokes that verifier, not the tasks' service.

`bigym2/THIRD_PARTY_NOTICES.md` and `bigym2/wbc/PROVENANCE.md` are carried as upstream ships them, so they also list
items RoboSafeBench does not vendor and that are not in the snapshot: BiGym's props and their textures (sections 5 to 8
of the notices: CC BY 4.0 and CC0 props, the procedural box, the upstream BiGym assets) and the GR00T-WBC runtime's
Python source (section 2; RoboSafeBench runs the two policies with its own `robosafebench/sim/wbc.py`). RoboSafeBench
records these files at the exact source pin in `source.env`; the context manifest preserves their bytes.

The public provenance projection also omits a non-public source repository locator.
Its provenance JSON, asset manifest, projection map and package checksum differ
from the privately qualified image metadata; runtime code, geometry, textures,
physics and third-party license files retain their original bytes. The private
image proof is not a build proof for this additional public metadata projection.
