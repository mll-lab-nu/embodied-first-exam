# eai-yamlab: YAMLab (github.com/ARISE-Initiative/yamlab @ ec0455d, MIT) on Isaac Sim 5.1.0 + Isaac Lab @ f4aa17f (the
# commit YAMLab's install.sh pins), torch 2.7.0+cu128, LeRobot (YAMLab's fork, Apache-2.0) for its recorder imports.
# Every Python package is pinned in images/yamlab/requirements.lock (pip freeze of the reference build). The task assets
# (YAMLab's object USDs for PutPotOnCooktop and HangMugOnTree, MIT, from the Hugging Face dataset yamlab/yamlab_datasets
# at a pinned revision) are baked in under /opt/yamlab-data. Isaac Sim needs an RTX-class GPU even headless; a task's
# compose reserves it and mounts a trial-scoped cache volume at /cache.
# Tag = images/yamlab/VERSION; build from the repo root (images/yamlab/BUILD_ONLY has the command, licences and checks):
#   docker build -f images/yamlab/Dockerfile -t ghcr.io/mll-lab-nu/eai-yamlab:$(cat images/yamlab/VERSION) .
# BUILD_ONLY, never published: Isaac Sim 5.1 / Omniverse Kit may be installed and used but not redistributed.
FROM nvidia/cuda:12.8.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1 PRIVACY_CONSENT=N
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg cmake build-essential \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/opt/venv/bin:/root/.local/bin:${PATH}" VIRTUAL_ENV=/opt/venv
RUN uv python install 3.11 && uv venv --seed -p 3.11 /opt/venv
# the GPU stack first (largest layers): torch 2.7.0+cu128, then Isaac Sim 5.1.0 from pypi.nvidia.com
RUN uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128 && rm -rf /root/.cache/uv
RUN uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com && rm -rf /root/.cache/uv
# Isaac Lab at YAMLab's pinned commit, its extensions only ("none": no RL frameworks)
RUN git clone -q https://github.com/isaac-sim/IsaacLab.git /opt/IsaacLab && cd /opt/IsaacLab && \
    git checkout -q f4aa17f87e2e5db5484f0b5974918573e8918ce2 && echo Yes | TERM=xterm ./isaaclab.sh --install none && rm -rf /root/.cache/pip /root/.cache/uv
# LeRobot (YAMLab's fork; its recorder module imports it) and YAMLab at their pinned commits
RUN git clone -q https://github.com/RogerDAI1217/lerobot.git /opt/lerobot && cd /opt/lerobot && \
    git checkout -q 67031e92657f67c0e885fdde4cb0871adb71a302 && pip install --no-cache-dir -e . && \
    git clone -q https://github.com/ARISE-Initiative/yamlab.git /opt/yamlab && cd /opt/yamlab && \
    git checkout -q ec0455d2b4ce35f21fc126418ea5e74ac567133d && pip install --no-cache-dir -e . && \
    pip install --no-cache-dir coacd pymeshlab usd-core open3d portal huggingface_hub
# the two tasks' object assets (USD), from the dataset at a pinned revision
RUN python -c "from huggingface_hub import snapshot_download as d; d('yamlab/yamlab_datasets', repo_type='dataset', \
      revision='fc6be973b8645cca50c0e9236bfbd64afa42696f', local_dir='/opt/yamlab-data', \
      allow_patterns=['tasks_data/PutPotOnCooktop/objects/*', 'tasks_data/HangMugOnTree/objects/*'])" && \
    rm -rf /opt/yamlab-data/.cache && du -sh /opt/yamlab-data
# Web assets: Isaac Lab's default ground (GroundPlaneCfg) and the three MDL materials of YAMLab's workstation USDs are
# otherwise fetched from NVIDIA's asset bucket at run time. The tasks run with closed egress, so they are baked in, each
# checked against its sha256 (images/yamlab/web_assets.txt); rcb_yamlab points the scene's ground at its copy, and
# localize_assets.py rewrites the workstation USDs' material URLs to theirs (same files: same look; physics never reads them).
COPY images/yamlab/web_assets.txt images/yamlab/localize_assets.py /opt/isaac-assets/
RUN set -e; grep -v '^#' /opt/isaac-assets/web_assets.txt | while read -r sha url dst; do \
      mkdir -p "$(dirname "$dst")"; curl -sSfL -o "$dst" "$url"; echo "$sha  $dst" | sha256sum -c --quiet -; done; \
    python /opt/isaac-assets/localize_assets.py https://omniverse-content-production.s3.us-west-2.amazonaws.com/Materials/2023_1/ \
      /opt/isaac-assets/Materials/2023_1/ /opt/yamlab/yamlab/robot/yam/workstation/workstation.usd \
      /opt/yamlab/yamlab/robot/yam/workstation/Props/instanceable_meshes.usd
# Pin: the steps above follow YAMLab's install.sh; this one sets every package to the version of the reference build
# (images/yamlab/requirements.lock, without resolving: the reference environment is what upstream's sequence of pip
# installs leaves, including a psutil newer than isaacsim-kernel's pin), and the build fails unless the result is exactly
# the lock (editable checkouts aside: Isaac Lab, LeRobot and YAMLab at the commits above).
COPY images/yamlab/requirements.lock /opt/requirements.lock
RUN uv pip install --no-deps --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 \
      --extra-index-url https://pypi.nvidia.com -r /opt/requirements.lock && rm -rf /root/.cache/uv && \
    uv pip freeze --exclude-editable | diff - /opt/requirements.lock && echo "environment == requirements.lock"
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
WORKDIR /app
