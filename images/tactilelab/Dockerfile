# tactilelab: Isaac Sim 5.1.0 + Isaac Lab 2.3.2 (Python 3.11, torch 2.7.0 cu128) + Pink IK for the TactileLab tasks (dual-arm
# X-Trainer, two GelSight Mini sensors on the right gripper). Infrastructure only, no task code: the tasks take the
# tactilelab_tasks package and their tooling from the files-only image tactilelab-files. Isaac Sim needs an RTX-class GPU even
# headless; a task's compose reserves it and mounts a trial-scoped cache volume at /cache (shader/extension cache).
# The recipe needs no build context. Building it accepts the NVIDIA Isaac Sim / Omniverse licence (images/tactilelab/BUILD_ONLY).
FROM docker.io/nvidia/cuda:12.8.1-base-ubuntu22.04@sha256:001469ea0f3dec85a1ca929aeea3b58ae369d4c11228b10aec1f642bb6ca7a6f AS tactilelab-base
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
# the Isaac 5.1 stack in /opt/tactilelab/.venv: torch 2.7.0 (CUDA 12.8 wheels), isaacsim from pypi.nvidia.com, Isaac Lab 2.3.2
# (flatdict, one of its dependencies, builds with pkg_resources: setuptools < 81 and no build isolation), Pink IK
RUN uv python install 3.11.17 && uv venv -p 3.11.17 /opt/tactilelab/.venv && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "torch==2.7.0" "torchvision==0.22.0" --index-url https://download.pytorch.org/whl/cu128 && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "setuptools<81" wheel && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install --no-build-isolation "flatdict==4.0.1" && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "isaaclab[isaacsim,all]==2.3.2" --extra-index-url https://pypi.nvidia.com && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "pin-pink==4.2.0" "daqp" "h5py" "pyyaml" "scipy" "imageio[ffmpeg]" && \
    rm -rf /root/.cache/uv
# Pink IK's own stack at the versions the tasks were developed with (pinocchio 2.x, which the line above resolves to,
# does not load with pin-pink 4.2); numpy goes back to Isaac Sim 5.1's 1.26 without touching the rest
# (its replicator graph breaks on numpy 2; pin 4.0 declares numpy >= 2 but runs on 1.26, as in the tasks' development setup)
RUN VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install "pin==4.0.0" "pin-pink==4.2.0" "daqp==0.7.2" "qpsolvers==4.8.2" && \
    VIRTUAL_ENV=/opt/tactilelab/.venv uv pip install --no-deps --reinstall "numpy==1.26.0" && \
    rm -rf /root/.cache/uv
ENV PATH="/opt/tactilelab/.venv/bin:${PATH}" VIRTUAL_ENV=/opt/tactilelab/.venv
# the Newton sidecar of the cloth / cable / dough / FEM tasks: its own Python 3.12 environment (Newton needs warp >= 1.17,
# the Isaac side ships 1.12); the tasks' sidecar code goes next to it, in /opt/tactilelab/sidecar (from tactilelab-files)
RUN uv python install 3.12.13 && uv venv -p 3.12.13 /opt/tactilelab/sidecar/.venv && \
    VIRTUAL_ENV=/opt/tactilelab/sidecar/.venv uv pip install "newton==1.7.0" "warp-lang==1.18.0" "numpy" && \
    rm -rf /root/.cache/uv
ENV WARP_CACHE_PATH=/cache/warp
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
# apt read the Ubuntu archive snapshot above, so the build's packages stay pinned; the image itself points apt back at the
# Ubuntu archive (the base image's sources.list, byte for byte): an `apt-get update` at run time is fast and reliable
RUN sed -i -e '/ jammy-security /s|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://security.ubuntu.com/ubuntu/|' \
           -e 's|http://snapshot.ubuntu.com/ubuntu/20261001T000000Z/|http://archive.ubuntu.com/ubuntu/|' /etc/apt/sources.list && \
    echo "15a39563d491def84446c8a5304e873a6b6509d56e2b54edce8eea154e1290a0  /etc/apt/sources.list" | sha256sum -c -
WORKDIR /app
