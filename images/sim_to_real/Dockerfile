# eai-sim_to_real: plain MuJoCo 3.3.7 (CPU physics, bit-exact replay; EGL rendering on a GPU, OSMesa fallback) and the
# I2RT YAM arm with the linear_4310 gripper and wrist D405 from MuJoCo Menagerie (MIT, pinned commit below; derived from
# I2RT's SDK v1.3.6). Infrastructure only: no benchmark code. The tasks compose the bimanual station themselves
# (rcb_yam.py) and COPY their own tooling. Tag = images/sim_to_real/VERSION. Build from the repo root:
#   docker build -f images/sim_to_real/Dockerfile -t ghcr.io/mll-lab-nu/eai-sim_to_real:$(cat images/sim_to_real/VERSION) .
# Every pip package is pinned (the closure of the install line): the frozen instances' state hashes depend on them.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends git ca-certificates libegl1 libgl1 libglvnd0 \
      libosmesa6 libgomp1 ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir mujoco==3.3.7 numpy==1.26.4 scipy==1.17.1 imageio==2.38.0 imageio-ffmpeg==0.6.0 \
      pillow==12.3.0 absl-py==2.5.0 etils==1.14.0 fsspec==2026.9.0 glfw==2.10.2 pyopengl==3.1.10 \
      typing-extensions==4.16.0 zipp==4.1.1
# MuJoCo Menagerie @ f054586 (2026-10-05, "I2rt yam linear 4310 (#328)"): only i2rt_yam/ (+ Menagerie's licence).
ARG MENAGERIE_COMMIT=f054586a8e90465d49ee5be15335c4a0c7f57caf
RUN git init -q /tmp/m && cd /tmp/m && git remote add origin https://github.com/google-deepmind/mujoco_menagerie.git && \
    git fetch -q --depth 1 origin $MENAGERIE_COMMIT && git checkout -q FETCH_HEAD && \
    mkdir -p /opt/eai_s2r/menagerie && cp -r i2rt_yam LICENSE /opt/eai_s2r/menagerie/ && rm -rf /tmp/m
# glvnd's vendor file for the NVIDIA EGL library the container toolkit mounts (without it EGL falls back to llvmpipe).
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
ENV MUJOCO_GL=egl PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all RCB_YAM_ROOT=/opt/eai_s2r/menagerie/i2rt_yam
RUN python -c "import mujoco; m = mujoco.MjModel.from_xml_path('/opt/eai_s2r/menagerie/i2rt_yam/yam_linear_4310.xml'); print('mujoco', mujoco.__version__, 'yam nu', m.nu)"
WORKDIR /app
