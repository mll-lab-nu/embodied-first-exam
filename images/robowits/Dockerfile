# eai-robowits: RoboWits (gs_gym) + Genesis v0.4.7 installed from RoboWits' OWN uv.lock (every version = the reference
# environment: torch 2.10.0+cu129, trimesh 4.11.1, pin 3.8.0, pin-pink 4.0.0, numpy 2.2.6, ...), minus the LeRobot/transformers
# training stack. Infrastructure only, no benchmark code. Only the Apache-2.0 HuggingFace asset bundle is baked in; the BlenderKit
# models are fetched by each user with their own key and mounted at /opt/robowits/assets/blender_kit (NOTICE here).
# Tag: ghcr.io/mll-lab-nu/eai-robowits:<images/robowits/VERSION> (docs/benchmarks/robowits.md, Image).
# 0.1.1 is the image published 2026-09-20 as rcb-robowits:0.1.1 (same image, sha256:62688073fee9...). The uv, huggingface_hub,
# imageio and asset-bundle pins below are the versions that image contains; apt packages and the CUDA base tag are not pinned,
# so a rebuild is not bit-identical: the published image is the reference.
# Validated 2026-09-20: builds in ~10 min (~20 GB), headless EGL on NVIDIA works, task 06 steps at ~26 Hz with three 848x480 cameras on an RTX 4090 laptop.
FROM nvidia/cuda:12.9.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git build-essential ffmpeg \
      libegl1 libgl1 libglvnd0 libglu1-mesa libx11-6 libxrender1 libxext6 libgomp1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{\n    "file_format_version" : "1.0.0",\n    "ICD" : {\n        "library_path" : "libEGL_nvidia.so.0"\n    }\n}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/0.12.17/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
RUN git clone https://github.com/UMass-Embodied-AGI/RoboWits /opt/robowits && cd /opt/robowits && git checkout -q 9cc30aedbbebea86b975c0d66ea9ac227ca38535 && git submodule update --init --depth 1 || true
WORKDIR /opt/robowits
# lockfile-exact install; lerobot (local path) and transformers (git) are the training stack and are skipped
RUN uv python install 3.11 && uv venv -p 3.11 .venv && \
    uv sync --frozen --no-install-package lerobot --no-install-package transformers && rm -rf /root/.cache/uv
ENV PATH="/opt/robowits/.venv/bin:${PATH}" VIRTUAL_ENV=/opt/robowits/.venv
RUN uv pip install --python /opt/robowits/.venv/bin/python "numpy==2.2.6" "huggingface_hub==0.35.3" "imageio[ffmpeg]==2.37.2" "imageio-ffmpeg==0.6.0" && rm -rf /root/.cache/uv && \
    hf download XHRlyb2001/RoboWits_assets --repo-type dataset --revision b1b49abba3bda9f3b91982d37139d62b3de9a543 --local-dir /opt/robowits/assets/hf_assets && rm -rf /root/.cache/huggingface
