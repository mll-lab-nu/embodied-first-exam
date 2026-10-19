# mujoco: plain MuJoCo (CPU physics, bit-exact replay; EGL rendering on a GPU, OSMesa fallback) + task assets.
# Assets: run images/mujoco/prepare_assets.sh first (pinned MuJoCo Menagerie / MuJoCo Playground / SimToolReal commits).
# Deliberately NOT included: SimToolReal's RL code and pretrained policy, MuJoCo Playground's training code.
FROM python:3.12-slim
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libegl1 libgl1 libglvnd0 libosmesa6 libgomp1 ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mujoco==3.3.7 "numpy<2" scipy imageio imageio-ffmpeg pillow requests
COPY rcb_mj /opt/rcb_mj
# glvnd's vendor file for the NVIDIA EGL library the container toolkit mounts. Without it EGL silently resolves to Mesa's
# llvmpipe (software) even with a GPU: 0.1.1 rendered a 4-camera frame in ~1.3 s instead of ~7 ms. Tagged by hand
# (the mujoco image only; images/VERSION is shared): 0.1.2 = 0.1.1 + this file. 0.1.3 = 0.1.2 + the quadruped assets
# (MuJoCo Playground's locomotion/{go1,spot} scenes, Menagerie's Go1, Spot and Barkour; prepare_assets.sh).
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
ENV MUJOCO_GL=egl PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all RCB_MJ_ROOT=/opt/rcb_mj
RUN python -c "import mujoco, numpy; print('mujoco', mujoco.__version__)"
WORKDIR /app
