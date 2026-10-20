# maniguard: ManiGuard (NU-IDEAS-Lab/ManiGuard @ a1b6444b3, a manipulation SAFETY benchmark) on its own pinned stack:
# BEHAVIOR-1K v3.7.2 = OmniGibson 3.7.2 + bddl 3.7.0 + Isaac Sim 4.5.0.0 (NVIDIA's pip wheels), Python 3.10, torch
# 2.6.0+cu124, and Spot 2.16 (conda-forge; the LTL library ManiGuard's safety monitor needs). This is what BEHAVIOR-1K
# v3.7.2's own installer builds (`setup.sh --new-env --omnigibson --bddl`, the order and pins of that script) plus PyAV from
# its `--eval` step (the PyPI wheel, see below), g++ for torch.compile and two Kit extensions for offline launches, minus
# the extras ManiGuard's evaluation never imports (`--primitives`: cuRobo and OMPL; `--joylo`; the rest of `--eval`, BEHAVIOR's
# challenge evaluator), and ManiGuard's evaluator only (images/maniguard/maniguard-keep.txt: its import closure; nothing of
# its data generation, demonstrations, policy servers or SFT code).
# NO dataset: the licensed BEHAVIOR-1K 3.7.2 data root is mounted read-only at /data from $RCB_MANIGUARD_DATA
# (images/maniguard/prep_data.py). Isaac Sim needs an RTX-class GPU even headless; a task's compose reserves it.
# Every ManiGuard task carries this file, without its header, as its `maniguard-base` stage: Harbor builds it on a task's first run, from
# public sources only (no account or token), and every task on that machine reuses it. Our prebuilt copy
# ghcr.io/mll-lab-nu/efe-private:maniguard-<images/maniguard/VERSION> (private: NVIDIA Isaac Sim may be used but not redistributed) is
# the tasks' compose `cache_from`: with read access its layers are pulled instead of built. Every input is pinned: the base
# image by digest, Ubuntu packages by the snapshot.ubuntu.com date, uv and Python by version, git checkouts by commit, this
# repository's files by sha256 at a tagged commit (ADD --checksum), downloads by sha256. Built alone (it reads nothing from the build context):
#   docker build --target maniguard-base -t ghcr.io/mll-lab-nu/efe-private:maniguard-$(cat images/maniguard/VERSION) images/maniguard
# images/maniguard/BUILD_ONLY has the licences, the host and the checks. A change here is copied into every task (and VERSION bumped).
# Locks: the build writes the installed package sets to /opt/locks/{dpkg,conda,pip}.lock and fails unless they equal the
# committed images/maniguard/*.lock (copied from the first tested build, 2026-10-03).
FROM docker.io/nvidia/cuda:12.4.1-base-ubuntu22.04@sha256:0f6bfcbf267e65123bcc2287e2153dedfc0f24772fb5ce84afe16ac4b2fada95 AS maniguard-base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 NVIDIA_DRIVER_CAPABILITIES=all \
    VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1

# System libraries Isaac Sim's renderer needs, from the Ubuntu archive as it was on 2026-10-01 (snapshot.ubuntu.com), and
# the NVIDIA Vulkan / EGL loader entries (the driver's libraries come from the NVIDIA container toolkit at run time).
RUN rm -f /etc/apt/sources.list.d/cuda*.list && \
    sed -i -e 's|http://archive.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' \
           -e 's|http://security.ubuntu.com/ubuntu/|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|' /etc/apt/sources.list && \
    apt-get -o Acquire::Retries=10 update && apt-get -o Acquire::Retries=10 install -y --no-install-recommends \
      ca-certificates curl git libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 \
      libxrandr2 libxinerama1 libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 \
      libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

# The committed locks of the reference build (images/maniguard/*.lock), which the steps below install from and the
# last step checks against; removed there.
ADD --checksum=sha256:edf82448f7c2cc5c98c331db06082b7ef4396f573dd6f31ec67fef5a84dedfe4 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/maniguard/dpkg.lock /tmp/locks/dpkg.lock
ADD --checksum=sha256:c45b0c50cbe65d870fda4cef1228ffd2be291da7a69e5054966fdc1ffe2d41a5 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/maniguard/conda.lock /tmp/locks/conda.lock
ADD --checksum=sha256:77865f2d1a97887ecd5d42cde15aa2de2cb6feef334fb4f1dc5abac49155591c https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/maniguard/pip.lock /tmp/locks/pip.lock

# Python 3.10 in a conda env named `behavior`, as setup.sh --new-env makes it, from conda-forge only (Miniforge: no Anaconda
# channels, so no Anaconda terms apply), the installer verified by its sha256. The env is created from the explicit lock
# (images/maniguard/conda.lock: every conda-forge package by URL and md5, Python 3.10.21 and ManiGuard's Spot 2.16 among
# them), so a build on any later day installs exactly the packages of the reference build.
RUN curl -fsSL --retry 5 -o /tmp/miniforge.sh https://github.com/conda-forge/miniforge/releases/download/26.7.2-0/Miniforge3-26.7.2-0-Linux-x86_64.sh && \
    echo "281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05  /tmp/miniforge.sh" | sha256sum -c - && \
    bash /tmp/miniforge.sh -b -p /opt/conda && rm /tmp/miniforge.sh && \
    /opt/conda/bin/conda create -y -n behavior --file /tmp/locks/conda.lock && /opt/conda/bin/conda clean -afy
# Every pip install below is constrained to the versions of images/maniguard/pip.lock, so newer PyPI releases never enter
# a fresh build. Build-time only (the locks are removed after the last step has checked them).
ARG PIP_CONSTRAINT=/tmp/locks/pip.lock

# Harbor runs the agent and the verifier with `docker exec`, which bypasses any entrypoint: the env goes first on PATH.
ENV PATH=/opt/conda/envs/behavior/bin:/opt/conda/bin:${PATH} CONDA_DEFAULT_ENV=behavior

# setup.sh --new-env: numpy < 2, setuptools <= 79, then torch 2.6.0 for CUDA 12.4 (its default --cuda-version)
RUN pip install --no-cache-dir "numpy<2" "setuptools<=79" && \
    pip install --no-cache-dir torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124

# setup.sh --bddl --omnigibson: BEHAVIOR-1K at tag v3.7.2 (commit 88454bd04f75, ManiGuard's submodule pin), editable installs
# of bddl3 and OmniGibson (no extras), from a sparse checkout of just those two directories
RUN git init -q /opt/behavior-1k && cd /opt/behavior-1k && git remote add origin https://github.com/StanfordVL/BEHAVIOR-1K.git && \
    git sparse-checkout set OmniGibson bddl3 && \
    git fetch -q --depth 1 --filter=blob:none origin 88454bd04f75dc57c00ab1f1a00bcde1ff505950 && git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = 88454bd04f75dc57c00ab1f1a00bcde1ff505950 && \
    pip install --no-cache-dir -e /opt/behavior-1k/bddl3 && pip install --no-cache-dir -e /opt/behavior-1k/OmniGibson

# setup.sh's Isaac Sim 4.5.0.0: the same 26 wheels from pypi.nvidia.com, each verified by its sha256 (isaacsim-4.5.0.0.sha256,
# from the index's own hashes), installed together; then setup.sh's websockets fix and its cffi 1.17.1 reinstall. Downloaded
# and removed in one layer.
ADD --checksum=sha256:c44b6e384e2cefb7fedd8d9df155c083791a9e9223ebdc74a1b2faa35c9d4fc9 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/maniguard/isaacsim-4.5.0.0.sha256 /tmp/isaacsim.sha256
RUN mkdir /tmp/isaac && cd /tmp/isaac && \
    while read -r sha f; do pkg="$(echo "$f" | cut -d- -f1 | tr _ -)"; curl -fsSL --retry 5 -o "$f" "https://pypi.nvidia.com/$pkg/$f" || exit 1; done < /tmp/isaacsim.sha256 && \
    sha256sum -c --quiet /tmp/isaacsim.sha256 && pip install --no-cache-dir ./*.whl && cd / && rm -rf /tmp/isaac /tmp/isaacsim.sha256 && \
    ISAAC_PATH="$(python -c "import isaacsim, os; print(os.environ.get('ISAAC_PATH', ''))")" && \
    if [ -n "$ISAAC_PATH" ] && [ -d "$ISAAC_PATH/extscache" ]; then find "$ISAAC_PATH/extscache" -type d -name websockets -path "*/pip_prebundle/*" -exec rm -rf {} +; fi && \
    pip install --no-cache-dir --force-reinstall cffi==1.17.1

# ManiGuard's Spot is in the env (conda.lock; "do NOT pip install spot"). setup.sh --eval's PyAV from PyPI instead of conda-forge: every conda-forge ffmpeg
# since 2024 brings its own Vulkan loader and libglvnd (libGL/libEGL) into the env, and once PyAV has loaded them Isaac Sim's
# renderer segfaults on its first frame (measured 2026-10-03, driver 580.178.04); the PyPI wheel bundles its libraries under
# private names. Same PyAV version, numpy < 2 kept.
RUN pip install --no-cache-dir av==16.0.1 && \
    python -c "import numpy, spot; from spot import buddy; assert numpy.__version__ < '2', numpy.__version__; assert all(hasattr(spot, a) for a in ('formula', 'translate', 'atomic_prop_collect')); print('numpy', numpy.__version__, 'spot ok')"

# ManiGuard's evaluator at the pinned commit: only the files of images/maniguard/maniguard-keep.txt, on the env's path
ADD --checksum=sha256:200abd97ef23584ec77526861b540c9adff2e3dca20fcd8ddd786b0ff8faa6a8 https://raw.githubusercontent.com/mll-lab-nu/embodied-first-exam/ce96d0f0ad5ae48c818deb1ad770cf5d89abb08b/images/maniguard/maniguard-keep.txt /tmp/maniguard-keep.txt
RUN git clone -q --filter=blob:none --no-checkout https://github.com/NU-IDEAS-Lab/ManiGuard.git /tmp/mg && cd /tmp/mg && \
    keep="$(grep -v '^#' /tmp/maniguard-keep.txt)" && git checkout -q a1b6444b3d17b2f9e4118c406824d36af6b24187 -- $keep && \
    mkdir -p /opt/maniguard && for f in $keep; do test -f "$f" || exit 1; mkdir -p "/opt/maniguard/$(dirname "$f")"; cp "$f" "/opt/maniguard/$f"; done && \
    cd / && rm -rf /tmp/mg /tmp/maniguard-keep.txt && \
    echo /opt/maniguard > "$(python -c 'import site; print(site.getsitepackages()[0])')/maniguard.pth"
ENV MANIGUARD_ROOT=/opt/maniguard OMNIGIBSON_HEADLESS=1 OMNIGIBSON_DATA_PATH=/data OMNIGIBSON_APPDATA_PATH=/cache/appdata

# OmniGibson's launcher copies BEHAVIOR-1K's docs/assets/OmniGibson_logo.png into Isaac Sim's apps directory at every start
# (simulator.py): the one file outside OmniGibson/ and bddl3/ it needs, from the same commit, sha256-checked.
RUN mkdir -p /opt/behavior-1k/docs/assets && curl -fsSL --retry 5 -o /opt/behavior-1k/docs/assets/OmniGibson_logo.png \
      https://raw.githubusercontent.com/StanfordVL/BEHAVIOR-1K/88454bd04f75dc57c00ab1f1a00bcde1ff505950/docs/assets/OmniGibson_logo.png && \
    echo "415480a53ed07ee3b909b4a3510f0aa44c4f44aa23296713ebc07af5a461ec23  /opt/behavior-1k/docs/assets/OmniGibson_logo.png" | sha256sum -c -

# OmniGibson compiles some of its transforms with torch.compile (inductor), which needs a C++ compiler at run time (same
# Ubuntu snapshot as above); its compiled kernels are cached under the trial's /cache volume.
RUN apt-get -o Acquire::Retries=10 update && apt-get -o Acquire::Retries=10 install -y --no-install-recommends g++ && \
    rm -rf /var/lib/apt/lists/*
ENV TORCHINDUCTOR_CACHE_DIR=/cache/torchinductor TRITON_CACHE_DIR=/cache/triton

# OmniGibson's kit file depends on two extensions the Isaac Sim wheels do not ship (omni.flowusd and its schema); Kit fetches
# them from NVIDIA's extension CDN at its first launch into the per-trial cache, so an offline launch (a standard-mode
# sidecar behind the agent's egress allowlist, a verifier without network) stops with "dependency solver failure"
# (measured 2026-10-03). They are fetched here instead, sha256-checked, into the extscache folder the kit file scans.
RUN X="$(python -c 'import isaacsim, os; print(os.path.join(os.path.dirname(isaacsim.__file__), "extscache"))')" && cd /tmp && \
    for e in "omni.flowusd-106.5.2+106.5.0.lx64.r.cp310.ub3f efaeac05f2e055334010a209977b0ff896891f33f663fbb84dfbb5fe8e996d7f" \
             "omni.usd.schema.flow-107.0.0+106.1.0.ub3f 2b5c46b749b88a165988f53bbd9d5b6b99532caee64ff5ffb1bd74588431932b"; do \
      set -- $e; curl -fsSL --retry 5 -o ext.zip "https://d4i3qtqj3r0z5.cloudfront.net/$(echo "$1" | sed 's/+/%2B/g').zip" && \
      echo "$2  ext.zip" | sha256sum -c - && python -m zipfile -e ext.zip "$X/$1" && rm ext.zip || exit 1; \
    done && test -f "$X/omni.flowusd-106.5.2+106.5.0.lx64.r.cp310.ub3f/config/extension.toml"

# Kit's caches (shaders, extension cache, logs) and OmniGibson's appdata under /cache, which a task mounts as a volume of its
# trial; the evaluator must import (no GPU needed for that); the installed package sets, checked against committed locks.
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /cache/appdata /cache/torchinductor /cache/triton /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output /data && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs && \
    python -c "import maniguard.eval.benchmark, maniguard.eval.goal_checker, maniguard.utils.safety_monitor, maniguard.utils.ltl_utils, maniguard.envs.frozen_task_runtime, maniguard.data.bench_builder.perturbation, maniguard.data.datagen.primitives.scene, maniguard.utils.camera_setup; print('maniguard evaluator imports')"
RUN mkdir -p /opt/locks && \
    dpkg-query -W -f='${db:Status-Status} ${Package}:${Architecture} ${Version}\n' | LC_ALL=C sort > /opt/locks/dpkg.lock && \
    conda list -n behavior --explicit --md5 | grep -v '^#' | LC_ALL=C sort > /opt/locks/conda.lock && \
    pip list --format=freeze | LC_ALL=C sort > /opt/locks/pip.lock && \
    for l in dpkg conda pip; do if [ -s "/tmp/locks/$l.lock" ]; then diff "/opt/locks/$l.lock" "/tmp/locks/$l.lock" || { echo "$l.lock differs"; exit 1; }; fi; done && rm -rf /tmp/locks
WORKDIR /app
