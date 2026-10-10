# eai-labutopia: LabUtopia (Rui-li023/LabUtopia @ 8df7278, NeurIPS 2025 Datasets and Benchmarks), a chemistry laboratory
# with a Franka Panda, on NVIDIA Isaac Sim 6.1.0. LabUtopia's README installs Isaac Sim 5.1.0 (Python 3.11); this image
# uses 6.1.0 (Python 3.12), the first release NVIDIA lists as tested on its R595 driver branch, on which 5.1.0 and 6.0
# crash at start-up (images/labutopia/BUILD_ONLY). Every Python package is pinned in images/labutopia/requirements.txt:
# `isaacsim[all,extscache]==6.1.0` with what it resolves to, plus hydra-core and omegaconf at LabUtopia's own pins and
# the few other packages its code imports, at versions that go with Isaac Sim 6.1's numpy 2.
# Infrastructure only, no benchmark code. Baked in: LabUtopia's scene assets (0.36 GB of USD through git LFS), with its
# scripted solutions removed in the layer that clones it (strip_solutions.py), and the 64 files that LabUtopia and
# Isaac Sim would otherwise load from NVIDIA's asset servers at run time (nvidia_assets.sha256).
# Isaac Sim needs an RTX-class GPU even headless: a task's environment/docker-compose.yaml reserves it. Kit keeps its
# caches inside its own package directory, so each container has its own (none is shared between an agent's container,
# the sim sidecar and the verifier).
# Tag = images/labutopia/VERSION; build from the repo root (images/labutopia/BUILD_ONLY has the command and the licences):
#   docker build -f images/labutopia/Dockerfile -t ghcr.io/mll-lab-nu/eai-labutopia:$(cat images/labutopia/VERSION) .
# BUILD_ONLY, never published: Isaac Sim / Omniverse Kit may be used but not redistributed, and LabUtopia's assets
# are CC BY-NC 4.0.
FROM nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/0.12.21/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
# the Python environment: every package at its pinned version (isaacsim wheels come from pypi.nvidia.com)
COPY images/labutopia/requirements.txt /tmp/requirements.txt
RUN uv python install 3.12 && uv venv -p 3.12 /opt/venv && \
    uv pip install --python /opt/venv/bin/python --no-deps -r /tmp/requirements.txt \
      --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match && \
    rm -rf /root/.cache/uv /tmp/requirements.txt
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv
# LabUtopia at the pinned commit with its scene assets (git LFS), without its history and without its scripted
# solutions: cloned, stripped and checked in ONE layer, so no layer holds them. No `git lfs fsck`: upstream commits its
# two README images as plain files under an LFS pattern, which fsck reports; the check is that no asset is left as an
# LFS pointer. GitHub's LFS endpoint answers 502 now and then: the pull is tried three times.
COPY images/labutopia/strip_solutions.py /tmp/strip_solutions.py
RUN GIT_LFS_SKIP_SMUDGE=1 git clone -q https://github.com/Rui-li023/LabUtopia.git /opt/labutopia && cd /opt/labutopia && \
    git checkout -q 8df72784265c375a327ffa3f0a0cf8c676f229a7 && \
    { git lfs pull || { sleep 30; git lfs pull; } || { sleep 120; git lfs pull; }; } && \
    ! grep -rIl '^version https://git-lfs.github.com/spec' assets robots | grep . && \
    rm -rf .git && python /tmp/strip_solutions.py /opt/labutopia && python /tmp/strip_solutions.py --check /opt/labutopia && \
    rm /tmp/strip_solutions.py && printf '%s\n' 8df72784265c375a327ffa3f0a0cf8c676f229a7 > /opt/labutopia-commit
# What LabUtopia loads from NVIDIA's public asset server at run time, mirrored under the server's own paths: Isaac Sim's
# Franka (LabUtopia references the robot under the Isaac asset root: 39 USD layers, 5 textures), the cabinet its
# laboratory stage references in the Isaac 4.2 asset tree (3 USD files), four materials of the Omniverse material
# library with their textures (14 files), and one sample file an example extension of Isaac Sim's default app reads
# when it starts. Each file is checked against its recorded sha256; rcb_labutopia.py redirects the server's URLs here.
COPY images/labutopia/nvidia_assets.sha256 /tmp/nvidia_assets.sha256
RUN mkdir -p /opt/nvidia-assets && cd /opt/nvidia-assets && \
    while read -r _sum path; do \
      mkdir -p "$(dirname "$path")" && \
      curl -fsSL --retry 5 -o "$path" "https://omniverse-content-production.s3-us-west-2.amazonaws.com/$path" || exit 1; \
    done < /tmp/nvidia_assets.sha256 && \
    sha256sum -c --quiet /tmp/nvidia_assets.sha256 && rm /tmp/nvidia_assets.sha256
RUN mkdir -p /app/output
ENV LABUTOPIA_ROOT=/opt/labutopia NVIDIA_ASSETS=/opt/nvidia-assets
WORKDIR /app
