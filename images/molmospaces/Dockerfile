# molmospaces: MolmoSpaces (Ai2; molmo-spaces 0.2.9, Apache-2.0) on MuJoCo 3.5.0 -- CPU physics, EGL rendering on a
# GPU (OSMesa without one) -- with the upstream assets of the frozen MolmoSpaces instances and nothing else. One image for
# the privileged tasks' environment and verifier and the standard tasks' `sim` service (PROTOCOL D5); tasks COPY their
# own tooling and instance. tasks/molmospaces/README.md.
# Build: run images/molmospaces/prepare_assets.sh first (it builds the `base` stage, installs and prunes the assets in a
# container of it, and stages them in images/molmospaces/build/), then scripts/build_images.sh, or in this directory:
#   docker build -t ghcr.io/mll-lab-nu/efe:molmospaces-$(cat VERSION) .
# Not included (PROTOCOL §2.7): upstream's scripted experts (molmo_spaces/policy/solvers: stubs only) and every grasp file.
# Licences: code Apache-2.0; scenes and AI2-THOR objects CC BY 4.0; Objaverse objects ODC-BY 1.0 and each its creator's
# CC BY / BY-SA / CC0 (no instance uses an episode with a non-commercial one).
FROM docker.io/library/python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1 AS base
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=egl PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all \
    MLSPACES_ASSETS_DIR=/opt/molmospaces/assets MLSPACES_CACHE_DIR=/opt/molmospaces/cache NLTK_DATA=/opt/molmospaces/nltk_data
RUN apt-get update && apt-get install -y --no-install-recommends \
      libegl1 libgl1 libglvnd0 libosmesa6 libglib2.0-0 libgomp1 ffmpeg strace gcc libc6-dev procps && \
    rm -rf /var/lib/apt/lists/*

# The measured environment, and in the SAME layer (a later layer cannot unwrite an earlier one) upstream's scripted
# experts, the reference solutions, replaced by stubs that keep their names and only raise (scrub_experts.py).
COPY requirements.txt scrub_experts.py /tmp/
RUN pip install --no-cache-dir --no-deps --extra-index-url https://download.pytorch.org/whl/cpu -r /tmp/requirements.txt && \
    python /tmp/scrub_experts.py && rm /tmp/requirements.txt /tmp/scrub_experts.py

# WordNet, which upstream's object metadata reads (it would otherwise try to download it at run time).
RUN python -m nltk.downloader -q -d "$NLTK_DATA" wordnet wordnet2022

# The Objaverse assets the benchmark episodes were made with (eval_main's _EXPECTED_DATA_VERSIONS lists 20251016_from_20250610
# first; 0.2.9 defaults to 20260131 and warns that its assets may differ), pinned by upstream's own MLSPACES_PINNED_ASSETS_FILE.
# The object metadata (names, synsets, CLIP features; no geometry) stays 20260129, also accepted there: 0.2.9 cannot read
# the 20251117 file (a list, not a map by uid).
COPY pinned_assets.json /opt/molmospaces/pinned_assets.json
ENV MLSPACES_PINNED_ASSETS_FILE=/opt/molmospaces/pinned_assets.json

# The NVIDIA runtime mounts libEGL_nvidia.so.0 but some hosts do not inject this manifest, and without it libglvnd
# cannot find the driver. Inert without a GPU.
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf \
    '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
WORKDIR /app

FROM base
# The assets of the frozen instances as prepare_assets.sh left them (install_assets.py install: downloaded with upstream's
# resource manager, traced, pruned), checked here without network (so nothing is fetched at run time): every instance
# rebuilds to its recorded t = 0 state hash. No GPU during the build: OSMesa. /opt/molmospaces/ATTRIBUTION.md: the licence
# of every shipped asset (the build fails on a non-commercial one).
COPY build/assets /opt/molmospaces/assets
COPY build/cache /opt/molmospaces/cache
COPY build/check /tmp/check
RUN --network=none cd /tmp/check && MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONPATH=/tmp/check RCB_SESSION_LOG= \
      python install_assets.py verify instances && \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa PYTHONPATH=/tmp/check RCB_SESSION_LOG= \
      python install_assets.py attribution instances /opt/molmospaces/ATTRIBUTION.md && \
    rm -rf /tmp/check /root/.cache /tmp/rcb_molmospaces && chmod -R a+rX /opt/molmospaces
