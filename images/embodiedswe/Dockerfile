# embodiedswe: EmbodiedSWE-Bench (`robobench`, github.com/EmbodiedSWE/EmbodiedSWE at commit 67f44e8a2c) on Isaac Sim 5.1 /
# Isaac Lab 2.3.2: the PhysX tasks. Two stages:
#  1. robolab-base: RoboLab's Isaac Sim 5.1 / Isaac Lab 2.3.2 recipe, verbatim (images/robolab/Dockerfile; builds from
#     public sources, shares Docker's build cache with the RoboLab tasks). Its RoboLab code and assets are unused here.
#  2. embodiedswe: robobench at the pinned commit (scrubbed: images/embodiedswe/scrub_embodiedswe.py), its whole-body IK
#     dependencies and Warp at the versions EmbodiedSWE validated its PhysX stack with, its Hugging Face assets checked
#     file by file against the commit's own SHA-256 manifest (robobench/assets_manifest.json), and this benchmark's
#     tooling (/opt/efe: rcb_embodiedswe.py, esw_proxy.py). Nothing is downloaded at run time (HF_HUB_OFFLINE=1).
# Contains NVIDIA Isaac Sim (no redistribution) and CC BY-NC / Fab-licensed assets: BUILD_ONLY (images/embodiedswe/BUILD_ONLY).
# >>> images/robolab/Dockerfile
# robolab: NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2.post1 / Isaac Sim 5.1.0, the `isaac51` extra) installed from OUR lockfile
# (images/robolab/uv.lock, generated with `uv lock` from RoboLab's pyproject at v0.3.1: torch 2.7.0+cu128, numpy 1.26.0,
# isaacsim 5.1.0.0), RoboLab's Apache-2.0 asset library (~6 GB, git LFS) and the remote files its USD layers reference.
# Infrastructure only, no benchmark code; nothing is mounted or downloaded at run time. Isaac Sim needs an RTX-class GPU even
# headless: a task's compose reserves it and mounts a trial-scoped cache volume at /cache (shader/extension cache).
# Every RoboLab task's Dockerfile starts with this recipe (scripts/task_conventions.py normalize copies it there) and builds
# it when the runner cannot pull ghcr.io/mll-lab-nu/efe-private:robolab-<VERSION>, the same recipe built with inline cache.
# The recipe needs no build context: the repository's files come by URL at a pinned commit, each checked by its sha256
# (a commit a tag keeps reachable; a change to uv.lock, mirror_remote_assets.py or remote_assets.sha256 = a new commit and
# checksum here + a new VERSION).
# Building it accepts the NVIDIA Isaac Sim / Omniverse licence (images/robolab/BUILD_ONLY).
FROM docker.io/nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f AS robolab-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1
# system libraries from the Ubuntu archive as it was on 2026-10-01 (snapshot.ubuntu.com), and the NVIDIA Vulkan / EGL loader entries
RUN rm -f /etc/apt/sources.list.d/cuda*.list && \
    sed -i -e 's|http://archive.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' \
           -e 's|http://security.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' /etc/apt/sources.list && \
    apt-get -o Acquire::Retries=10 update && apt-get -o Acquire::Retries=10 install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
COPY --from=ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 /uv /uvx /root/.local/bin/
ENV PATH="/root/.local/bin:${PATH}"
# RoboLab's code at v0.3.1 and its asset library (every LFS file present), in one RUN that then deletes the repository's
# .git (its objects hold every committed file: `git show` would rebuild what is removed) and examples/recorded_data
# (RoboLab's one recorded episode, a successful run of one of the RoboLab tasks: its actions, log and video; PROTOCOL H.2)
RUN git init -q /opt/robolab && cd /opt/robolab && git remote add origin https://github.com/NVlabs/RoboLab && \
    git fetch -q --depth 1 origin 9db0aaf09d9fe5d4f37b168320788258c7012463 && GIT_LFS_SKIP_SMUDGE=1 git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = 9db0aaf09d9fe5d4f37b168320788258c7012463 && \
    git lfs pull && test -z "$(git lfs ls-files | grep -v '^[0-9a-f]* \* ')" && \
    rm -rf /opt/robolab/.git /opt/robolab/examples/recorded_data && test ! -e /opt/robolab/.git
WORKDIR /opt/robolab
# lockfile-exact install of RoboLab + the Isaac 5.1 stack (isaacsim wheels from pypi.nvidia.com, declared in RoboLab's pyproject)
ADD --chmod=644 --checksum=sha256:8e7ff47350cbce86ba30ec9cf59dcb5737efdbfc367a30144a9a7ea857e7c588 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/robolab/uv.lock /opt/robolab/uv.lock
RUN uv python install 3.11.17 && uv venv -p 3.11.17 .venv && uv sync --frozen --extra isaac51 && rm -rf /root/.cache/uv
ENV PATH="/opt/robolab/.venv/bin:${PATH}" VIRTUAL_ENV=/opt/robolab/.venv
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
# the remote files RoboLab's USD layers reference on NVIDIA's public Omniverse content bucket, copied to
# /opt/robolab/assets/_remote, each checked against remote_assets.sha256, and the layers pointed at the copies (tasks run offline)
ADD --chmod=644 --checksum=sha256:05492bd92e016b68d00a4bcf7e0530964480f430e271970f330ca2bea8908694 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/robolab/mirror_remote_assets.py /opt/robolab/mirror_remote_assets.py
ADD --chmod=644 --checksum=sha256:c4ae7e62d3d7285e26218e9aec8d5cd8c92fe3d2c1f81d6d931c536a8550f998 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/robolab/remote_assets.sha256 /opt/robolab/remote_assets.sha256
RUN python /opt/robolab/mirror_remote_assets.py /opt/robolab/assets /opt/robolab/assets/_remote --check /opt/robolab/remote_assets.sha256
# apt read the Ubuntu archive snapshot above, so the build's packages stay pinned; the image itself points apt back at the
# Ubuntu archive (the base image's sources.list, byte for byte): an `apt-get update` at run time is fast and reliable
RUN sed -i -e '/ jammy-security /s|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://security.ubuntu.com/ubuntu/|' \
           -e 's|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://archive.ubuntu.com/ubuntu/|' /etc/apt/sources.list && \
    echo "15a39563d491def84446c8a5304e873a6b6509d56e2b54edce8eea154e1290a0  /etc/apt/sources.list" | sha256sum -c -
WORKDIR /app
# <<< images/robolab/Dockerfile

FROM robolab-base AS embodiedswe
ARG ESW_COMMIT=67f44e8a2ca51c3e133867e5e669377778e8f97d
# whole-body IK for the G1 pink_ik bindings (EmbodiedSWE README), Warp as EmbodiedSWE's validated PhysX stack (1.11.0)
RUN uv pip install --python /opt/robolab/.venv/bin/python "pin==2.7.0" "pin-pink==3.1.0" "daqp==0.8.5" "numpy==1.26.0" \
      "warp-lang==1.11.0" && rm -rf /root/.cache/uv && \
    python -c "import numpy, warp, pink, pinocchio; assert numpy.__version__ == '1.26.0', numpy.__version__; print('warp', warp.__version__, 'pin', pinocchio.__version__)"
# robobench at the pinned commit. Only robobench/, LICENSE and pyproject.toml are kept; .git goes in the same RUN (the
# repository's history holds solve-calibrated configurations), and the scrub removes the graders, the smoke probes and
# the solve-calibrated notes before anything is compiled.
COPY scrub_embodiedswe.py /opt/efe/build/scrub_embodiedswe.py
RUN git init -q /tmp/esw && cd /tmp/esw && git remote add origin https://github.com/EmbodiedSWE/EmbodiedSWE && \
    git fetch -q --depth 1 origin ${ESW_COMMIT} && git checkout -q FETCH_HEAD && test "$(git rev-parse HEAD)" = "${ESW_COMMIT}" && \
    rm -rf .git && mkdir -p /opt/embodiedswe && cp -a . /opt/embodiedswe/ && cd / && rm -rf /tmp/esw && \
    python -I /opt/efe/build/scrub_embodiedswe.py /opt/embodiedswe && \
    python -I /opt/efe/build/scrub_embodiedswe.py /opt/embodiedswe --check
ENV PYTHONPATH=/opt/embodiedswe:/opt/efe COSIGEN_ASSET_DIR=/opt/embodiedswe
# the Hugging Face assets of the PhysX suites and their rooms at the manifest's pinned dataset revision, every file
# checked against its SHA-256 (robobench's own fetch, run once here); the download caches go in the same RUN
RUN cd /opt/embodiedswe && python -I -c "import sys; sys.path.insert(0, '/opt/embodiedswe'); \
from robobench.scripts import fetch_assets as f; \
roots = sorted(r for r in f.load_manifest()['bundles'] if '/deformable/' not in r); print(roots); \
sys.exit(1 if f.fetch(prefixes=roots) else 0)" && \
    rm -rf /opt/embodiedswe/.cache /root/.cache/huggingface && \
    ! grep -rlaE "https?://[A-Za-z0-9.-]*(amazonaws|nvidia|huggingface)" /opt/embodiedswe/robobench --include=*.usda --include=*.mdl
# Isaac Lab's default ground plane, which puzzle.spatula, puzzle.syringe, cutting.slice and cutting.dice spawn
# (`GroundPlaneCfg()`: {ISAAC_NUCLEUS_DIR}/Environments/Grid/default_environment.usd), and its whole USD dependency closure
# (the three textures it references; OmniPBR.mdl is Kit's own), from NVIDIA's public Omniverse content bucket, each checked by
# its sha256, at the bucket's key layout under /opt/isaac_assets. Isaac Lab's experience files then point the asset root
# (/persistent/isaac/asset_root/{default,cloud,nvidia}, read by isaaclab.utils.assets) at that mirror, so the scenes load
# unchanged and offline. Closure + checksums: images/embodiedswe/isaac_assets.json (fetch_isaac_assets.py).
ADD --chmod=644 --checksum=sha256:deab39088eaf39ed7be951966c5e6bd5e58b90ab64743b0cdc8e5579fd5a99d9 https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/WireframeBlur_basecolor.png /opt/isaac_assets/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/WireframeBlur_basecolor.png
ADD --chmod=644 --checksum=sha256:44fc0e82007bb0bd94631cd7ec45986a71ed74b9413899fbffac13efe151be4b https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/WireframeBlur_blue.png /opt/isaac_assets/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/WireframeBlur_blue.png
ADD --chmod=644 --checksum=sha256:940b96ee8c8e53bd1acbc770d4ca0ac98bed9c96439ab386d1b27dbc9790cc4e https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/Wireframe_blue.png /opt/isaac_assets/Assets/Isaac/5.1/Isaac/Environments/Grid/Materials/Textures/Wireframe_blue.png
ADD --chmod=644 --checksum=sha256:8a21c317d638d33a4e6c20c958a7ed8f4d8c5195efd7e20f1b85178b4a15638a https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Environments/Grid/default_environment.usd /opt/isaac_assets/Assets/Isaac/5.1/Isaac/Environments/Grid/default_environment.usd
RUN A=/opt/robolab/.venv/lib/python3.11/site-packages/isaaclab/apps && \
    sed -i '/^persistent\.isaac\.asset_root\.\(default\|cloud\|nvidia\) = /s#"https://omniverse-content-production\.s3-us-west-2\.amazonaws\.com/Assets/Isaac/5\.1"$#"/opt/isaac_assets/Assets/Isaac/5.1"#' $A/*.kit && \
    test "$(grep -h '^persistent\.isaac\.asset_root\.\(default\|cloud\|nvidia\) = "/opt/isaac_assets/Assets/Isaac/5\.1"$' $A/*.kit | wc -l)" = 18 && \
    ! grep -n 'asset_root.*https://' $A/*.kit && chmod -R a+rX /opt/isaac_assets && \
    test -f /opt/isaac_assets/Assets/Isaac/5.1/Isaac/Environments/Grid/default_environment.usd
ENV HF_HUB_OFFLINE=1 OMNI_KIT_ALLOW_ROOT=1
# the graded solution process runs as `nobody`: it must reach the interpreter (under /root, traverse only) and read the
# package trees, never write them. The tooling (rcb_embodiedswe.py, esw_proxy.py) is not in this image: each task copies
# it to /opt/efe from the files image ghcr.io/mll-lab-nu/efe:embodiedswe-files (source embodied_first_exam/benchmarks/embodiedswe).
RUN chmod 711 /root && chmod -R a+rX /opt/embodiedswe /root/.local/share/uv && mkdir -p /opt/efe && \
    python -I -B -c "import sys; sys.path[:0] = ['/opt/embodiedswe']; import robobench; robobench.discover(); \
from robobench.core.registries import ENVS; [ENVS.get(p) for p in ('assembly.bulb.franka.osc', 'puzzle.stack_blocks.g1.pink_ik', 'locomanip.fruit_delivery.g1.loco_pink_ik')]; print('tasks ok')" && \
    find /opt/embodiedswe -name __pycache__ -prune -exec rm -rf {} + && \
    python -I -B /opt/efe/build/scrub_embodiedswe.py /opt/embodiedswe --check && mkdir -p /app/output
WORKDIR /app
