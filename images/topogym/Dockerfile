# rcb-topogym: TopoGym's simulator (the topogym package: Genesis 1.2.1, the Nyx renderer, robot assets) on CUDA 12.6 torch.
# Infrastructure only, no benchmark code (docs/rcb/PROTOCOL.md §1): the task tooling (rcb_topogym.py) comes with each task,
# and prune.py removes everything that could hold a reference solution. Tag = images/VERSION; build: scripts/build_images.sh
# topogym (from the repository root, which is the build context; .dockerignore keeps it small).
FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu126
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TOPOGYM_VISUAL_ASSET_ROOT=/opt/topogym-visuals TOPOGYM_ASSET_ROOT=/opt/topogym-assets \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl ca-certificates git build-essential ffmpeg libegl1 libgl1 libglib2.0-0 \
    libx11-6 libxext6 libxrender1 libvulkan1 libgomp1 ripgrep \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.30
COPY requirements/uv-topogym-gs121.txt requirements/uv-topogym-gs121-nyx.txt /opt/requirements/
RUN uv pip install --system torch==2.12.0 torchvision==0.27.0 --index-url ${TORCH_INDEX} \
    && uv pip install --system -r /opt/requirements/uv-topogym-gs121.txt --overrides /opt/requirements/uv-topogym-gs121-nyx.txt \
    && uv pip install --system -r /opt/requirements/uv-topogym-gs121-nyx.txt \
    && uv pip install --system imageio==2.37.0 imageio-ffmpeg==0.6.0 pyuipc==0.0.25
COPY assets/robots/ /opt/topogym-assets/robots/
COPY scripts/prepare_nyx_studio.py /opt/prepare_nyx_studio.py
RUN python /opt/prepare_nyx_studio.py
COPY topogym/ /opt/topogym/topogym/
COPY images/topogym/prune.py /opt/prune.py
RUN python /opt/prune.py /opt/topogym && rm /opt/prune.py
ENV PYTHONPATH=/opt/topogym TOPOGYM_SOURCE=/opt/topogym/SOURCE.json
WORKDIR /app
