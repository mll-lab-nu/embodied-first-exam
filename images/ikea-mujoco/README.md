# eai-ikea-mujoco

`ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-<images/ikea-mujoco/VERSION>`: MuJoCo 3.14.0 (the PyPI wheel with the EPA
horizon-overflow fix byte-patched in, `mujoco-3.14.0-epa/` here; CPU, float64; numpy 2.5.4, Python 3.12) and the IKEA
furniture scenes of the IKEA MuJoCo tasks (`tasks/ikea-mujoco/ikea-<task>-i00-{privileged,standard}`;
docs/benchmarks/ikea_mujoco.md). Each scene is
self-contained: `scene.py` (`load()` returns the scene: `S.model`, `S.data`, `S.step(n)` = n physics steps plus the
scene's mechanism, `S.success()`), `scene.xml` with the two arms, the scene's mechanism and success modules,
`task.json`, `layout.json`, `assets/` (meshes). The image holds no task code: the tooling (`rcb_ikea.py`) and the
graders are copied by each task, and no robot demo or direct-force reference is in it.

The image carries twelve scenes. Eight are tasks (lack, svallet, gladom, variera, eket, ikea365, vesken, stegesund);
burvik, kyrre, stenerik and uppsta are in the image but are not tasks (work in progress: no reference passes every gate
yet; docs/benchmarks/ikea_mujoco.md). Keeping them in the image keeps the image the one the tasks were validated on.

`sim/` is the standard tasks' sidecar image, `ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-sim-<images/ikea-mujoco/sim/VERSION>`:
this image unchanged as the physics process, plus Nyx (RoboARC's renderer) in its own venv `/opt/nyx`
(`sim/nyx-requirements.txt`: RoboARC's exact versions and wheel hashes), the Vulkan loader and NVIDIA ICD / EGL vendor
files, imageio + ffmpeg, Pillow and PyOpenGL.

## Build source

The scene code is in git, `scenes/<task>/` here. The meshes (`scenes/<task>/assets/`, 2,078 files, about 40 MB per
scene) are not: they are on the private Hugging Face dataset `eai-v2-internal/ikea-mujoco-assets` (layout
`<task>/assets/<file>`), pinned by its revision and by the sha256 of every file in `images/ikea-mujoco/assets.json`
(`repo`, `revision`, and per scene `files`). Every task's `tests/runtime_binding.json` repeats its scene's pins, which
the grader checks in the verifier image (`instance_exact`) together with the initial-state hash (`instance_ok`).

What is staged per scene: `scene.py`, `scene.xml`, `task.json`, `layout.json`, `sw_cutover.json` (where present), the
scene's own Python modules (not `_*.py` scripts) and `assets/`; then `assets.json` (its `note` and `tasks`, the pins the
image carries at `/opt/ikea/assets.json`) and `bytepatch_libmujoco.py`. `stage_context.py` refuses any file whose sha256
differs from the pins and any scene text that points at upstream material (PROTOCOL Appendix H.2); the scenes' upstream
provenance is kept out of the image, in `images/ikea-mujoco/provenance.json`.

## Build (from the repository root)

```bash
images/ikea-mujoco/fetch_image_context.sh          # meshes at the pinned revision (needs read access: `hf auth login` or HF_TOKEN),
                                                    # checked, staged with the scene code into images/ikea-mujoco/context/
docker build -f images/ikea-mujoco/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-$(cat images/ikea-mujoco/VERSION) images/ikea-mujoco/context
docker build -t ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-sim-$(cat images/ikea-mujoco/sim/VERSION) images/ikea-mujoco/sim
```

`scripts/build_images.sh` does the same once the context is staged (`BUILD_CONTEXT`; `sim/` is built after the base as
its sub-image). The build needs network access to docker.io, pypi.org (and download.pytorch.org, dl.polyhaven.org for
`sim/`); running needs none. Host: Linux x86_64, Docker; the base image needs no GPU, the sidecar an NVIDIA GPU with
Vulkan and EGL.

A rebuild from the same context on a host that holds the build's layer cache gives the same image id
(`ed950d079b63` for 0.3.0); a build from scratch installs the same wheels (the patch script asserts the wheel's and the
patched `.so`'s sha256) and the same scene files, but its layers, and so its id, differ. The sidecar image's apt layer
follows the Debian archive of its build day, so its id differs per build host. After a scene changes: `stage_context.py <tree> --pin`, rebuild, bump
`VERSION`, refresh `images/ikea-mujoco/bindings.json` (`python /opt/tools/rcb_ikea.py info --task <t>` in the image, per
task), upload the meshes as a new dataset revision and pin it, and re-render the tasks. A changed scene is a new task
(PROTOCOL §2.8).

## Registry

`ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-<VERSION>` and `ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-sim-<sim/VERSION>` (the benchmark
registry rule, `ghcr.io/mll-lab-nu/efe-private:<name>-<version>` for a BUILD_ONLY image). The tasks name the tags; `images/ikea-mujoco/bindings.json` holds the
base image's id (`sha256:ed950d079b63…` for 0.3.0), which every task's `tests/runtime_binding.json` repeats. The build
context's source of record is the dataset revision in `images/ikea-mujoco/assets.json`.
