# roboarc

> `Dockerfile` builds RoboARC's MuJoCo release image (`efe:roboarc-<VERSION>`) FROM the published base image
> `efe:robotangle-0.2.22`, pinned by digest. Everything below describes that base image (the simulator source, libuipc
> builds and instance staging the MuJoCo image inherits); its build recipe is not part of this repository.

`ghcr.io/mll-lab-nu/efe:roboarc-<images/roboarc/VERSION>` is a public image: RoboARC's simulator (the pruned
`topogym` package of the release commit), Genesis 1.2.1, libuipc (the audited determinism-patched wheel, plus an sm_86 build
of the same recipe), PyTorch, Nyx and every task's frozen instance. The tasks `FROM` it, and the standard `sim` service runs
it. Maintainers push it with `scripts/push_images.sh` after validating a build.

- **Nyx.** The image contains Genesis AI's Nyx renderer (the `gs-nyx` wheels on PyPI). The benchmark owner has permission to
  redistribute it in this image.
- **Build source.** The build context comes from the private Hugging Face dataset `eai-v2-internal/robotangle-assets`. It is
  internal and is never made public; only the built image is public. It holds, at the revision and sha256s pinned in
  `images/roboarc/assets.json`:
  - `image/release-<commit>.tar.gz`: the release tree (`images/roboarc/release.json` `release_commit`), the paths
    `images/topogym/Dockerfile` copies;
  - `image/uipc-prebuilt/`: the audited libuipc wheel and its `uipc-build.json` (sha256 `39781d19…`), which every task's
    runtime binding names. nvcc output is not bit-reproducible, so a wheel compiled elsewhere never matches the binding;
  - `image/uipc-sm86/`: the sm_86 build of the same recipe and its `uipc-build.json` (sha256 `712470d2…`; "The libuipc
    builds", below). The image installs it in `/opt/uipc_sm86` (`install_uipc_prefix.py`);
  - `instances/`: every task's frozen instance. `stage_instance.py` copies a task's instance next to its
    `runtime_binding.json` and checks it (privileged `environment/` and `tests/` images; the standard `sim` entrypoint).

  Access: a member of `eai-v2-internal`, logged in with `hf auth login`, or `HF_TOKEN` in the environment (never printed).

## Host

- Linux x86_64. Not WSL: Nyx needs the NVIDIA Vulkan driver inside the container.
- An NVIDIA GPU with driver >= 580, and Docker with the NVIDIA Container Toolkit. Docker's default runtime stays `runc`.
- Exactly one GPU per container: Nyx crashes when two GPUs are visible. The task compose files reserve one GPU with a
  device reservation (`count: 1`, `capabilities: [gpu]`), without `runtime: nvidia`. NVIDIA_DRIVER_CAPABILITIES=all makes
  the toolkit mount the driver's graphics libraries, and the image's Vulkan ICD and EGL vendor files point the loaders at
  them, as in `images/robopaint/`. `VK_ICD_FILENAMES` names the image's ICD file: a toolkit in CDI mode also mounts the
  host's `/etc/vulkan/icd.d/nvidia_icd.json`, which would list the GPU twice.
- `count: 1` is host GPU 0 unless the runner pins GPUs; IPC sims (knot_untying, rope_threading) run alone on a 24 GB GPU
  (`tasks/roboarc/README.md`, Image).
- GPU architecture (`tasks/roboarc/README.md`, Image, has the table):
  - knot_untying and rope_threading run libuipc: the audited wheel on compute capability 8.9 and 12.x, the sm_86 build on
    any other GPU (native on 8.6, e.g. RTX A6000; untested elsewhere). 7.5 (T4, RTX 20xx) can run neither;
  - GPUs without RT cores (e.g. A100, H100) cannot run Nyx, so they run no RoboARC task;
  - the driver must include its graphics (GL/Vulkan) user-space libraries.
- blanket_flatten: on a GPU other than the one its frozen PBD states were prepared on (an RTX PRO 6000 Blackwell), the task
  generates the birth state from the recipe frozen in the instance (`tasks/roboarc/README.md`, GPU portability).
- Build:
  - about 25 GB of free disk: the 11.3 GB image plus BuildKit cache;
  - BuildKit with the default `docker` driver;
  - network access to docker.io, pypi.org, download.pytorch.org and dl.polyhaven.org (the CC0 studio HDRI).
- Running needs no network.

## Build (from the repository root)

0.2.22 was published as a delta of the published 0.2.21: `FROM ghcr.io/mll-lab-nu/efe:robotangle-0.2.21@sha256:4fd681598e07a7a29201b8f30ccbee9944baaa856a5b05b045e48522c138f7ab` plus one `COPY` layer with the eight IPC instances'
`instance_assets/frozen_assets/rope_volume.npz` (mode 0644). Its files are those of a full build from the pinned dataset
revision, and a host that has 0.2.21 pulls only that layer (13 MB). A full build with the commands below gives the same
files in other layers.

```bash
images/roboarc/fetch_image_context.sh [<download dir>]     # images/roboarc/context/ from the pinned dataset, checked
docker build -f images/roboarc/Dockerfile -t ghcr.io/mll-lab-nu/efe:roboarc-$(cat images/roboarc/VERSION) images/roboarc/context
```

`scripts/build_images.sh` builds it from `images/roboarc/BUILD_CONTEXT` once the context exists, and skips it otherwise.
The image is not cache-warmed: every container compiles its kernels on first use, and scene ready took 67-296 s for the
rigid families on a shared 4090, against the 1800 s startup watchdog. The release tree's `images/topogym/warm_cache.sh`
does not apply here. It expects `topogym-*` task directories with their own `instance.json`, and RoboARC's tasks stage
their instances from the image.

## Check a build

The image must install exactly the runtime every task is bound to:

```bash
docker run --rm ghcr.io/mll-lab-nu/efe:roboarc-$(cat images/roboarc/VERSION) python -c 'import json; from topogym.simulator.frozen_binding import installed_runtime; print(json.dumps(installed_runtime(), sort_keys=True))' > /tmp/roboarc_runtime.json
python3 -c 'import json, sys; sys.exit(0 if json.load(open("/tmp/roboarc_runtime.json")) == json.load(open("images/roboarc/release.json"))["runtime"] else "image differs from the tasks runtime binding: do not run")'
```

Every session checks it again at start (`runtime_binding_ok` in reward.json) and refuses a different runtime. The two
libuipc builds must be the ones `images/roboarc/release.json` `uipc_builds` names, and the image build already checked
both wheels against their build records:

```bash
docker run --rm ghcr.io/mll-lab-nu/efe:roboarc-$(cat images/roboarc/VERSION) sh -c 'sha256sum /opt/uipc-build.json /opt/uipc_sm86/uipc-build.json; cat /opt/uipc-check.json'
```

## The libuipc builds

The image holds two builds of one libuipc recipe (libuipc 292c98c3 with the determinism patches of the release's
`images/topogym/uipc-patches`, the pinned CUDA 12.8 builder image, pyuipc `0.0.25+topogym.det1.cuda128`):
- the audited wheel (`89-real;120-real;120-virtual`) in site-packages, `/opt/uipc-build.json`: every evidence run used it,
  and GPUs of compute capability 8.9 and 12.x always load it;
- the sm_86 build (`86-real;86-virtual`) in `/opt/uipc_sm86`: any other GPU loads it. The task tooling chooses at Session
  start, before uipc is imported (`rcb_topogym.py` `select_uipc_build`).

Both keep the pyuipc version and libuipc commit, which the frozen IPC settled states record; that is why the sm_86 build
restores them. Do not give a rebuild another local version label.

