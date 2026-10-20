# ese: where its contents come from

The snapshot is Embodied Safety Exam 0.5.6, the source commit pinned in `source.env` (its release tag v0.5.6), as
`git archive` gives it. Each frozen instance records its own source; historical files still require current-candidate
validation before release.
Embodied Safety Exam's source repository is not public yet: the snapshot in `context/` is what this
repository builds from, and `fetch_context.sh --check <clone>` lets a maintainer with access compare it with the
repository.

**Names.** Embodied Safety Exam (ESE) is the benchmark formerly named RoboSafeBench; the source keeps the old name only
in its README's "formerly RoboSafeBench" sentence and in the audit's list of benchmark names to catch. Its package is
`embodied_safety_exam/`, its environment variables `ESE_*`, and its public provenance identifiers are
`historical-source://...`. Scenes, physics, rules, verdicts and every task's start state are those of the 0.5.4 release;
the asset manifest hash is `9df4b0248d271b5e59009a1e806d153a1f1733f9a24ead7d41a8bcb2700f4785`. The realism_v3 binaries
are in the Hugging Face dataset `MLL-Lab/embodied-safety-exam-assets`.
Inside the image the package is installed from `/opt/ese`; the build's checksums and manifests are in `/opt/ese-image`.

| Part | Source | How it is checked |
|---|---|---|
| `context/ese-src/` | Embodied Safety Exam at the commit in `source.env`, as `git archive` gives it (README.md's sentence about the repository's own documents rewritten to point at `tasks/embodied-safety-exam/README.md`): the package `embodied_safety_exam/`, `pyproject.toml`, `README.md`, `LICENSE` (Apache-2.0), `LICENSE-assets` (CC BY 4.0, its generated assets), `assets/third_party/README.md` and the DejaVu font (`assets/third_party/fonts/`, its own licence) | `context/ese-src.sha256`, every file, in the image build; `fetch_context.sh --check <clone>` against Embodied Safety Exam |
| robot models | MuJoCo Menagerie (public; Apache-2.0 and the models' own licences, each model's `LICENSE` beside it) at `MENAGERIE_COMMIT`, only the files Embodied Safety Exam vendors under `assets/third_party/mujoco_menagerie/` (byte-for-byte copies of that commit) | `context/menagerie.sha256`, every file, in the image build |
| G1 assets (`context/ese-src/assets/third_party/bigym2/`, Embodied Safety Exam 0.5.2) | BiGym 2.0's G1 model and controller configuration as Embodied Safety Exam vendors them: the model and config under Apache-2.0 (`LICENSE`, `NOTICE` kept), the Unitree G1 meshes under BSD-3-Clause (`g1/LICENSE.unitree`; the MJCF packaging's `g1/LICENSE`, Apache-2.0); the walking controller's policy weights `wbc/*.onnx` (NVIDIA GR00T Whole-Body Control) under the NVIDIA Open Model License, NOT Apache-2.0 or CC BY 4.0: its text (`wbc/NVIDIA Open Model License.txt`) and the notice "Licensed by NVIDIA Corporation under the NVIDIA Open Model License" (`wbc/NOTICE`) ship beside them | `context/ese-src.sha256`, every file, in the image build; Embodied Safety Exam's own sha256 of the weights (`embodied_safety_exam/sim/wbc.py` `WEIGHTS_SHA256`) when they load |
| Python stack | PyPI, `requirements.txt` (MuJoCo 3.8.1, numpy 2.2.6, PyOpenGL, Pillow, imageio + imageio-ffmpeg; onnxruntime 1.28.0 with flatbuffers, protobuf and packaging for the G1's controller) | pinned versions, `pip check` |
| system | Debian's OSMesa and GL libraries, git | the pinned Python base image |

The snapshot keeps the complete native `embodied_safety_exam` package, including its harness, diagnosis tools,
command line, HTTP server and agent-facing documents. `fetch_context.sh` does not prune package modules.
The trusted simulator installs this package so that native validation, subprocess replay and the runtime
use the same source. Packaging code alone does not invoke a harness or a model; the benchmark's simulator
service does not start either. The verdict's reading of an exit's text (`named`) is in `verify/words.py`.

The families' scripted reference methods also remain in this trusted simulator package: the episode's
checks and the oracle compiler use the same classes. The task's agent image contains only its client,
without this simulator package or its reference methods. Generated oracle plans live under `solution/`;
trusted validation sidecars remain outside the generated task directories. This source provenance
statement is not a substitute for the final image's isolation and installed-runtime checks.

The `realism_v3` pack's `.png` / `.obj` files and the third-party `assets/third_party/bigym2/` `.STL` / `.onnx` files are not committed (`images/ese/.gitignore`): `python3 images/ese/assets.py fetch` restores them from the Hugging Face datasets pinned in `images/ese/assets.json` (`MLL-Lab/embodied-safety-exam-assets` and `MLL-Lab/embodied-first-exam-public`, both public: no login) before a build. After a context refresh, `assets.py export <dir>` lays them out for upload and `assets.py pin <pack> <dir> <revision>` records a pack's new revision.

To move to another Embodied Safety Exam commit: set `ESE_COMMIT` and `ESE_VERSION` in `source.env`, bump `VERSION`,
run `fetch_context.sh <clone>` (needs a clone with that commit) and rebuild; the tasks are a frozen release:
new tasks for another commit come from Embodied Safety Exam's release tooling. Never
rebuild a tag that trials have used.

The native `embodied_safety_exam/client/remote.py` client and `verify.verify_in_subprocess`
(`verify/__init__.py`) are retained with the rest of the package. The latter runs
`python -m embodied_safety_exam verify`; its `__main__.py` entry point is retained as well.
Only the native admission workflow invokes that verifier, not the tasks' service.

`bigym2/THIRD_PARTY_NOTICES.md` and `bigym2/wbc/PROVENANCE.md` are carried as upstream ships them, so they also list
items Embodied Safety Exam does not vendor and that are not in the snapshot: BiGym's props and their textures (sections 5 to 8
of the notices: CC BY 4.0 and CC0 props, the procedural box, the upstream BiGym assets) and the GR00T-WBC runtime's
Python source (section 2; Embodied Safety Exam runs the two policies with its own `embodied_safety_exam/sim/wbc.py`). Embodied Safety Exam
records these files at the exact source pin in `source.env`; the context manifest preserves their bytes.
