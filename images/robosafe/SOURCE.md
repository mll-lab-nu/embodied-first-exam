# eai-robosafe: where its contents come from

The snapshot is RoboSafeBench 0.5.3 (commit `70373cd`, `source.env`), the version the tasks were frozen with.
RoboSafeBench's source repository is not public yet: the snapshot in `context/` is what this
repository builds from, and `fetch_context.sh --check <clone>` lets a maintainer with access compare it with the
repository.

| Part | Source | How it is checked |
|---|---|---|
| `context/robosafe-src/` | RoboSafeBench at the commit in `source.env`, as `git archive` gives it (README.md's sentence about the repository's own documents rewritten to point at `docs/benchmarks/robosafe.md`): the package `robosafe/`, `pyproject.toml`, `README.md`, `LICENSE` (Apache-2.0), `LICENSE-assets` (CC BY 4.0, its generated assets), `assets/third_party/README.md` and the DejaVu font (`assets/third_party/fonts/`, its own licence) | `context/robosafe-src.sha256`, every file, in the image build; `fetch_context.sh --check <clone>` against RoboSafeBench |
| robot models | MuJoCo Menagerie (public; Apache-2.0 and the models' own licences, each model's `LICENSE` beside it) at `MENAGERIE_COMMIT`, only the files RoboSafeBench vendors under `assets/third_party/mujoco_menagerie/` (byte-for-byte copies of that commit) | `context/menagerie.sha256`, every file, in the image build |
| G1 assets (`context/robosafe-src/assets/third_party/bigym2/`, RoboSafeBench 0.5.2) | BiGym 2.0's G1 model and controller configuration as RoboSafeBench vendors them: the model and config under Apache-2.0 (`LICENSE`, `NOTICE` kept), the Unitree G1 meshes under BSD-3-Clause (`g1/LICENSE.unitree`; the MJCF packaging's `g1/LICENSE`, Apache-2.0); the walking controller's policy weights `wbc/*.onnx` (NVIDIA GR00T Whole-Body Control) under the NVIDIA Open Model License, NOT Apache-2.0 or CC BY 4.0: its text (`wbc/NVIDIA Open Model License.txt`) and the notice "Licensed by NVIDIA Corporation under the NVIDIA Open Model License" (`wbc/NOTICE`) ship beside them | `context/robosafe-src.sha256`, every file, in the image build; RoboSafeBench's own sha256 of the weights (`robosafe/sim/wbc.py` `WEIGHTS_SHA256`) when they load |
| Python stack | PyPI, `requirements.txt` (MuJoCo 3.8.1, numpy 2.2.6, PyOpenGL, Pillow, imageio + imageio-ffmpeg; onnxruntime 1.28.0 with flatbuffers, protobuf and packaging for the G1's controller) | pinned versions, `pip check` |
| system | Debian's OSMesa and GL libraries, git | the pinned Python base image |

Left out of the snapshot, as the simulator does not need them (`fetch_context.sh` `PRUNE`): RoboSafeBench's harnesses
and model clients (`robosafe/harness`, `verify/recognise.py`), diagnosis tools (`robosafe/diagnose`, `verify/audit.py`,
`verify/ladder.py`, `verify/render.py`), metrics, its command line and HTTP server, and its agent-facing documents
(`robosafe/docs`: the tasks carry their own instruction). The image carries no code that calls a model: the verdict's
reading of an exit's text (`named`) is in `verify/words.py`. The image's build ends with an episode that exits and is
judged, so a module the verdict needs cannot go missing unnoticed. The families' scripted solutions stay
in the package (the episode's checks and the oracle compiler use the same classes); the image is only ever the
standard tasks' `sim` service, which the agent cannot reach.

To move to another RoboSafeBench commit: set `ROBOSAFE_COMMIT` and `ROBOSAFE_VERSION` in `source.env`, bump `VERSION`,
run `fetch_context.sh <clone>` (needs a clone with that commit), rebuild, and freeze the instances again
(`scripts/robosafe/AUTHORING.md`). Never rebuild a tag that trials have used.

Known leftovers in the snapshot, kept so that its bytes stay RoboSafeBench's at that commit: `robosafe/client/remote.py`
(the HTTP client of RoboSafeBench's own harness; nothing in the image calls it) and `verify.verify_in_subprocess`
(`verify/__init__.py`), which runs `python -m robosafe verify` and so needs the pruned `__main__.py`; only RoboSafeBench's
admission calls it, never the tasks' service.

`bigym2/THIRD_PARTY_NOTICES.md` and `bigym2/wbc/PROVENANCE.md` are carried as upstream ships them, so they also list
items RoboSafeBench does not vendor and that are not in the snapshot: BiGym's props and their textures (sections 5 to 8
of the notices: CC BY 4.0 and CC0 props, the procedural box, the upstream BiGym assets) and the GR00T-WBC runtime's
Python source (section 2; RoboSafeBench runs the two policies with its own `robosafe/sim/wbc.py`). RoboSafeBench
corrects both files in its next release; the snapshot keeps the bytes of 2803dd4.
