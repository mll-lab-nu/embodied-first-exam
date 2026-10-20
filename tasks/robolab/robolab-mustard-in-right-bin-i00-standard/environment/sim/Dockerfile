# The `sim` sidecar's image (environment/docker-compose.yaml builds it): images/robolab/Dockerfile, verbatim.
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
# RoboLab's code at v0.3.1 (LFS pointers only), then the asset library as its own layer (every LFS file present)
RUN git init -q /opt/robolab && cd /opt/robolab && git remote add origin https://github.com/NVlabs/RoboLab && \
    git fetch -q --depth 1 origin 9db0aaf09d9fe5d4f37b168320788258c7012463 && GIT_LFS_SKIP_SMUDGE=1 git checkout -q FETCH_HEAD && \
    test "$(git rev-parse HEAD)" = 9db0aaf09d9fe5d4f37b168320788258c7012463
WORKDIR /opt/robolab
RUN git lfs pull && test -z "$(git lfs ls-files | grep -v '^[0-9a-f]* \* ')" && \
    (git lfs prune -f --verify-remote=false >/dev/null 2>&1 || true) && rm -rf /opt/robolab/.git/lfs
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
WORKDIR /app
# <<< images/robolab/Dockerfile
# The rest of the `sim` sidecar's image (environment/docker-compose.yaml builds it): the image above, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:robolab-sim-files-0.1.1@sha256:9f1e403e8751df326980d3e62625e31cc416b33894bdcb90c3cb79fde383dfbb \
     /sim/finalize.sh \
     /sim/live_video.py \
     /rcb_robolab.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-sim-files-0.1.1@sha256:d9a4e130a67056d0fb47594562ac303b2f000c5f48fbe5ec235593bef0f3543f \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
