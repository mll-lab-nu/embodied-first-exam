# rcb-robotwin: RoboTwin 2.0 (SAPIEN 3 / PhysX + CuRobo, dual-arm ALOHA-AgileX by default) environment.
# Infrastructure only — contains no benchmark code; tasks `FROM` it and COPY their own tooling. Tag = images/VERSION.
# Needs an NVIDIA GPU at runtime (CuRobo planning on CUDA, SAPIEN rendering on Vulkan): tasks pass it through
# with environment/docker-compose.yaml (see docs). NVIDIA_DRIVER_CAPABILITIES=all makes the container runtime
# mount the driver's Vulkan/EGL libraries; the ICD json files below point the loaders at them.
# Build from repo root: scripts/build_images.sh   (submodule third_party/RoboTwin pinned to the 2.0 commit)
FROM nvidia/cuda:12.4.1-devel-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy CUDA_HOME=/usr/local/cuda \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git unzip build-essential cmake ninja-build ffmpeg tmux \
      libvulkan1 vulkan-tools libglvnd0 libgl1 libegl1 libx11-6 libxext6 libxrender1 libgomp1 libusb-1.0-0 && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/vulkan/icd.d /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.0"}}\n' > /usr/share/vulkan/icd.d/nvidia_icd.json && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /opt/RoboTwin
RUN uv python install 3.10 && uv venv -p 3.10 /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv
# Simulator assets (RoboTwin 2.0 HF dataset, pinned revision): embodiments + objects. background_texture (10 GB)
# is only used by domain randomisation and is left out; tasks use clean scenes.
RUN uv pip install huggingface_hub==0.25.0 && mkdir -p assets && cd assets && \
    python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='TianxingChen/RoboTwin2.0', repo_type='dataset', revision='981c92aa34d8f94d4cff47e0d5bc2f7d4e0af042', allow_patterns=['embodiments.zip','objects.zip'], local_dir='.')" && \
    unzip -q embodiments.zip && unzip -q objects.zip && rm -rf embodiments.zip objects.zip .cache
# Python deps (RoboTwin scripts/requirements.txt minus data-collection/LLM extras); torch cu124 matches nvcc.
RUN uv pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu124 && \
    uv pip install numpy==1.26.4 opencv-python-headless==4.10.0.84 transforms3d==0.4.2 sapien==3.0.0b1 scipy==1.10.1 \
      mplib==0.2.1 gymnasium==0.29.1 trimesh==4.4.3 open3d==0.18.0 imageio==2.34.2 imageio-ffmpeg "pydantic>=2.5" "PyYAML>=6" \
      "h5py>=3.8" toppra termcolor av matplotlib Pillow setuptools==69.5.1 wheel ninja && rm -rf /root/.cache/uv
# RoboTwin's install script patches two site-packages files (utf-8 URDF reads; mplib screw-plan collision check).
RUN SP=$(python -c "import sapien,os;print(os.path.dirname(sapien.__file__))") && \
    sed -i -E 's/("r")(\))( as)/\1, encoding="utf-8") as/g' $SP/wrapper/urdf_loader.py && \
    MP=$(python -c "import mplib,os;print(os.path.dirname(mplib.__file__))") && \
    sed -i -E 's/(if np.linalg.norm\(delta_twist\) < 1e-4 )(or collide )(or not within_joint_limit:)/\1\3/g' $MP/planner.py
# CuRobo v0.7.8 (RoboTwin's motion planner), compiled for Ampere/Ada/Hopper.
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"
RUN git clone --branch v0.7.8 --depth 1 https://github.com/NVlabs/curobo.git /opt/curobo && \
    uv pip install --no-build-isolation -e /opt/curobo && uv pip install warp-lang==1.12.0 && rm -rf /opt/curobo/.git /root/.cache/uv
COPY third_party/RoboTwin /opt/RoboTwin
RUN rm -rf .git .gitmodules && python scripts/update_embodiment_config_path.py >/dev/null
# Strip RoboTwin's built-in expert solutions (envs/<task>.py play_once + helpers, code_gen prompts): agents must not
# be able to look them up. Only scene definitions and success predicates remain.
COPY images/robotwin/scrub_oracles.py /tmp/scrub_oracles.py
RUN python /tmp/scrub_oracles.py && rm /tmp/scrub_oracles.py
ENV PYTHONPATH=/opt/RoboTwin ROBOTWIN_ROOT=/opt/RoboTwin
# Import smoke test. No GPU at build time, and `import envs` initialises CUDA through CuRobo, so only the pure deps here.
RUN python -c "import sapien, mplib, toppra, open3d; print('robotwin deps ok', sapien.__version__)"
WORKDIR /app
