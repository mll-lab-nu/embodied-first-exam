# robodojo: RoboDojo's simulation benchmark (github.com/RoboDojo-Benchmark/RoboDojo @ cb2a37d, MIT) on Isaac Sim
# 5.1.0 + RoboDojo's Isaac Lab fork (2.3, @ afca7b0) + its cuRobo fork (@ d17b54c), torch 2.7.0+cu128, following
# RoboDojo's scripts/install.sh step by step. The benchmark assets (Robots, Object, Material, Room, Background, Sensor,
# Traj, Eval_Layout; Apache-2.0, Hugging Face dataset RoboDojo-Benchmark/RoboDojo at a pinned revision, ~41 GB) are baked
# in under /opt/RoboDojo/Assets. Isaac Sim needs an RTX-class GPU even headless; cuRobo needs CUDA.
# Tag = images/robodojo/VERSION; build from the repo root (images/robodojo/BUILD_ONLY has the command, licences, checks):
#   docker build -f images/robodojo/Dockerfile -t ghcr.io/mll-lab-nu/efe-private:robodojo-$(cat images/robodojo/VERSION) .
# With the assets already downloaded (same revision), pass them instead of downloading again:
#   --build-context robodojo-assets=<dir containing Assets/>
# BUILD_ONLY, never published: Isaac Sim 5.1 / Omniverse Kit may be installed and used but not redistributed.

# -- the assets, at the dataset revision RoboDojo's eval layouts were checked against --------------------------------
FROM python:3.11-slim AS robodojo-assets-download
RUN pip install --no-cache-dir huggingface_hub==0.35.3 && python -c "from huggingface_hub import snapshot_download as d; \
      d('RoboDojo-Benchmark/RoboDojo', repo_type='dataset', revision='35efbc7dedfdbeeb6e95fb749bd885d73d483e41', \
        local_dir='/dl', allow_patterns=['Assets/*'], max_workers=8)" && rm -rf /dl/.cache
FROM scratch AS robodojo-assets
COPY --from=robodojo-assets-download /dl/Assets /Assets

# -- the simulator stack -------------------------------------------------------------------------------------------------
# cuRobo builds CUDA extensions, so the base is the CUDA devel image RoboDojo's own Dockerfile uses
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04 AS stack
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    NVIDIA_DRIVER_CAPABILITIES=all VK_DRIVER_FILES=/etc/vulkan/icd.d/nvidia_icd.json \
    VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json \
    OMNI_KIT_ACCEPT_EULA=YES ACCEPT_EULA=Y OMNI_KIT_ALLOW_ROOT=1 PRIVACY_CONSENT=N \
    CUDA_HOME=/usr/local/cuda FORCE_CUDA=1 TORCH_CUDA_ARCH_LIST="7.0;7.5;8.0;8.6;8.9;9.0+PTX" MAX_JOBS=8
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git git-lfs ffmpeg cmake ninja-build pkg-config build-essential \
      libvulkan1 libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxt6 libxext6 libxrender1 libxi6 libxrandr2 libxinerama1 \
      libxcursor1 libsm6 libice6 libgomp1 libglib2.0-0 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libfreetype6 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/opt/venv/bin:/root/.local/bin:${PATH}" VIRTUAL_ENV=/opt/venv
RUN uv python install 3.11 && uv venv --seed -p 3.11 /opt/venv
# RoboDojo and its three submodules at the pinned commits
RUN git clone -q https://github.com/RoboDojo-Benchmark/RoboDojo.git /opt/RoboDojo && cd /opt/RoboDojo && \
    git checkout -q cb2a37d58dbbeb2777b0c2b30e97ecb8ab91095c && \
    git submodule update -q --init --depth 1 third_party/IsaacLab third_party/curobo XPolicyLab && \
    test "$(git -C third_party/IsaacLab rev-parse HEAD)" = afca7b09d60d8beb9c1cb28b43066499940b969b && \
    test "$(git -C third_party/curobo rev-parse HEAD)" = d17b54ce32cba095c0b000c4c58777075d11de0e && \
    test "$(git -C XPolicyLab rev-parse HEAD)" = 53c5da5a01bc720d1cf0e6ab6ed212e8cef0eda2
# install.sh: base deps (its dev tools ruff and pre-commit left out), then torch, Isaac Sim, Isaac Lab, cuRobo, re-pins
RUN uv pip install huggingface_hub transforms3d ffmpeg open3d msgpack-numpy && \
    uv pip install opencv-python-headless==4.11.0.86 pillow matplotlib "scipy==1.15.3" scikit-learn && \
    uv pip install numpy==1.26.0 && rm -rf /root/.cache/uv
RUN uv pip install "numpy==1.26.0" "typing_extensions==4.12.2" "filelock==3.13.1" && \
    uv pip install torch==2.7.0 torchvision==0.22.0 torchaudio==2.7.0 --index-url https://download.pytorch.org/whl/cu128 && \
    rm -rf /root/.cache/uv
RUN uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com && rm -rf /root/.cache/uv
RUN cd /opt/RoboDojo/third_party/IsaacLab && echo Yes | TERM=xterm ./isaaclab.sh --install none && \
    rm -rf /root/.cache/pip /root/.cache/uv
RUN cd /opt/RoboDojo/third_party/curobo && pip install --no-cache-dir -e ".[cu12]" --no-build-isolation && \
    pip install --no-cache-dir "numpy==1.26.0" "packaging==23.0" "typing_extensions==4.12.2" "filelock==3.13.1" \
      "websockets==12.0" "scipy==1.15.3" "warp-lang==1.11.0" && \
    find /opt/RoboDojo/third_party -name .git -prune -exec rm -rf {} + ; true
# Pin: the steps above follow RoboDojo's install.sh; this one sets every package to the version of the reference build
# (images/robodojo/requirements.lock, without resolving: the reference environment is what upstream's sequence of pip
# installs leaves), and the build fails unless the result is exactly the lock (editable checkouts aside: RoboDojo's Isaac
# Lab and cuRobo at the commits above).
# Packages an unpinned upstream install step pulls in today but the lock does not list are removed first, so a fresh
# build still ends at exactly the lock.
COPY images/robodojo/requirements.lock /opt/requirements.lock
RUN uv pip install --no-deps --index-strategy unsafe-best-match --extra-index-url https://download.pytorch.org/whl/cu128 \
      --extra-index-url https://pypi.nvidia.com -r /opt/requirements.lock && rm -rf /root/.cache/uv && \
    uv pip freeze --exclude-editable | grep -vxFf /opt/requirements.lock | sed 's/[ =@].*//' | xargs -r uv pip uninstall && \
    uv pip freeze --exclude-editable | diff - /opt/requirements.lock && echo "environment == requirements.lock"
# RoboDojo's Isaac Lab (2.3.2) pins the extension isaacsim.asset.importer.urdf =2.4.31, the isaacsim 5.1.0 wheels carry
# 2.4.30: Kit downloads 2.4.31 from NVIDIA's extension registry at its first start, as on any RoboDojo install. The tasks
# run offline, so the app starts once here (the dependency solve needs no GPU; the start itself then fails without one)
# and what Kit downloaded moves into the wheels' extension cache, where an offline start finds it.
RUN cd /tmp && (timeout 900 python -c "import argparse; from isaaclab.app import AppLauncher; ap = argparse.ArgumentParser(); \
      AppLauncher.add_app_launcher_args(ap); a = ap.parse_args([]); a.headless = True; a.enable_cameras = True; AppLauncher(a)" \
      > /tmp/kit_warmup.log 2>&1 || true) && D=/root/.local/share/ov/data/exts/v2 && \
    X=/opt/venv/lib/python3.11/site-packages/isaacsim/extscache && ls -d $D/isaacsim.asset.importer.urdf-2.4.31+* && \
    mv $D/isaacsim.asset.importer.urdf-2.4.31+* $D/omni.kit.pip_archive-* $X/ && rm -rf /root/.local/share/ov /tmp/kit_warmup.log

# -- the image: the stack plus the assets --------------------------------------------------------------------------------
FROM stack
COPY --from=robodojo-assets /Assets /opt/RoboDojo/Assets
# RoboDojo's install step: the robots' cuRobo configs (curobo.yml) from their templates, with the asset path filled in
RUN cd /opt/RoboDojo && python utils/update_embodiment_config_path.py > /dev/null && ls Assets/Robots/*/curobo.yml
# Web assets: two of RoboDojo's USDs load three MDL materials from NVIDIA's asset bucket at run time (the tasks run with
# closed egress): baked in, each checked against its sha256 (images/robodojo/web_assets.txt), and localize_assets.py rewrites
# both URL forms in those USDs to the copies (same files: same look; physics never reads them). The USD rewrite uses a
# throwaway usd-core: Isaac Sim's own pxr loads only inside Kit.
COPY images/robodojo/web_assets.txt images/robodojo/localize_assets.py /opt/isaac-assets/
RUN set -e; grep -v '^#' /opt/isaac-assets/web_assets.txt | while read -r sha url dst; do \
      mkdir -p "$(dirname "$dst")"; curl -sSfL -o "$dst" "$url"; echo "$sha  $dst" | sha256sum -c --quiet -; done; \
    python -m venv /tmp/usdv && /tmp/usdv/bin/pip install -q --no-cache-dir usd-core==25.5 && \
    /tmp/usdv/bin/python /opt/isaac-assets/localize_assets.py \
      https://omniverse-content-production.s3.us-west-2.amazonaws.com/Materials/2023_1/=/opt/isaac-assets/Materials/2023_1/ \
      http://omniverse-content-production.s3-us-west-2.amazonaws.com/Materials/=/opt/isaac-assets/Materials/2023_1/ -- \
      /opt/RoboDojo/Assets/Sensor/Camera/realsense.usd /opt/RoboDojo/Assets/Object/RoboDojo/Geometry/camera_stand/00000/object.usd && \
    rm -rf /tmp/usdv
# Vulkan: the NVIDIA container toolkit injects the driver's libraries but not every host injects its Vulkan ICD manifest
# (none here: Isaac's renderer then fails with ERROR_INCOMPATIBLE_DRIVER); one manifest, the one VK_ICD_FILENAMES names
# (a toolkit that does inject it writes the same path, so the loader never sees two ICDs for one GPU)
RUN mkdir -p /etc/vulkan/icd.d /etc/vulkan/implicit_layer.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194"\n    }\n}\n' > /etc/vulkan/icd.d/nvidia_icd.json && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "layer": {\n        "name": "VK_LAYER_NV_optimus",\n        "type": "INSTANCE",\n        "library_path": "libGLX_nvidia.so.0",\n        "api_version" : "1.3.194",\n        "implementation_version" : "1",\n        "description" : "NVIDIA Optimus layer",\n        "functions": {\n            "vkGetInstanceProcAddr": "vk_optimusGetInstanceProcAddr",\n            "vkGetDeviceProcAddr": "vk_optimusGetDeviceProcAddr"\n        },\n        "enable_environment": {\n            "__NV_PRIME_RENDER_OFFLOAD": "1"\n        },\n        "disable_environment": {\n            "DISABLE_LAYER_NV_OPTIMUS_1": ""\n        }\n    }\n}\n' > /etc/vulkan/implicit_layer.d/nvidia_layers.json
# Kit caches (shaders, extension registry, user data) live under /cache so a task's compose can keep them in a volume
RUN mkdir -p /cache/ov-cache /cache/ov-data /cache/ov-logs /root/.cache /root/.local/share /root/.nvidia-omniverse /app/output && \
    ln -s /cache/ov-cache /root/.cache/ov && ln -s /cache/ov-data /root/.local/share/ov && ln -s /cache/ov-logs /root/.nvidia-omniverse/logs
ENV PYTHONPATH=/opt/RoboDojo
WORKDIR /app
