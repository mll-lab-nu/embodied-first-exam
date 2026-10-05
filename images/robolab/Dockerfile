# eai-robolab: NVIDIA RoboLab v0.3.1 (Isaac Lab 2.3.2.post1 / Isaac Sim 5.1.0, the `isaac51` extra) installed from OUR lockfile
# (images/robolab/uv.lock, generated with `uv lock` from RoboLab's pyproject at v0.3.1: every version = the reference environment,
# torch 2.7.0+cu128, numpy 1.26.0, isaacsim 5.1.0.0). Infrastructure only, no benchmark code. RoboLab's asset library (~6 GB of USD
# objects/scenes/backgrounds, Apache-2.0 like the code, distributed through the repo's git LFS) IS baked in, as RoboLab's own
# docker/Dockerfile does; nothing has to be mounted. Isaac Sim needs an RTX-class GPU even headless: a task's
# environment/docker-compose.yaml reserves it and mounts a trial-scoped cache volume at /cache (shader/extension cache, ~2 min first launch).
# Tag = images/robolab/VERSION; build from the repo root (images/robolab/BUILD_ONLY has the command, the licences and the checks):
#   docker build -f images/robolab/Dockerfile -t ghcr.io/mll-lab-nu/eai-robolab:$(cat images/robolab/VERSION) .
# BUILD_ONLY, never published: Isaac Sim 5.1 / Omniverse Kit may be installed and used but not redistributed; every host builds it.
FROM nvidia/cuda:12.8.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
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
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
# code at the pinned release (LFS pointers only), then the asset library as its own layer
RUN GIT_LFS_SKIP_SMUDGE=1 git clone -q --branch v0.3.1 --depth 1 https://github.com/NVlabs/RoboLab /opt/robolab
WORKDIR /opt/robolab
RUN git lfs pull && git lfs prune -f --verify-remote=false >/dev/null 2>&1 || true; rm -rf /opt/robolab/.git/lfs
# lockfile-exact install of RoboLab + the Isaac 5.1 stack (isaacsim wheels come from pypi.nvidia.com, declared in pyproject)
COPY images/robolab/uv.lock /opt/robolab/uv.lock
RUN uv python install 3.11 && uv venv -p 3.11 .venv && uv sync --frozen --extra isaac51 && rm -rf /root/.cache/uv
ENV PATH="/opt/robolab/.venv/bin:${PATH}" VIRTUAL_ENV=/opt/robolab/.venv
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a shared volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
WORKDIR /app
