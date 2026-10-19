# eai-ikea-mujoco-sim: the `sim` sidecar image of the IKEA MuJoCo STANDARD-mode tasks (tasks/ikea-<task>-i00-standard).
# = eai-ikea-mujoco (plain MuJoCo 3.14.0 CPU float64 with the EPA-patched libmujoco.so + numpy 2.5.4 + the frozen scenes,
# unchanged: the physics process) + what the robot-as-a-service layer needs to render and encode:
#   - Nyx, RoboARC's renderer, in its OWN interpreter environment, the venv /opt/nyx (python 3.12 of the base, separate
#     site-packages): gs-nyx 0.1.3 needs numpy < 2.4, the physics keeps numpy 2.5.4, so the sim service renders every RGB
#     image in a separate render process (each task's environment/sim/ikea_nyx.py) fed the scene once and per-frame poses
#     over a pipe. The venv's packages are RoboARC's exact versions and wheel hashes (nyx-requirements.txt, from
#     requirements/difficulty-eval-runtime.lock): gs-nyx 0.1.3, numpy 2.3.5, scipy 1.17.1, trimesh 5.1.0, mujoco 3.14.0 (stock wheel,
#     only to read the compiled scene's visual geometry; it never steps physics), nvidia-cuda-nvrtc-cu12 12.8.93;
#   - RoboARC's studio HDRI (Poly Haven studio_small_09, CC0; scripts/prepare_nyx_studio.py's URL and sha256);
#   - the Vulkan loader and RoboARC's NVIDIA Vulkan ICD / EGL vendor files (images/robotangle/Dockerfile): Nyx renders
#     through Vulkan; MuJoCo's EGL raster still draws the depth images, as RoboARC's MuJoCo raster depth;
#   - imageio + ffmpeg (mp4), Pillow (jpeg), PyOpenGL for the physics process (unchanged from 0.3.0).
# Build (context = this directory):
#   docker build -t ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-sim-$(cat images/ikea-mujoco/sim/VERSION) images/ikea-mujoco/sim
FROM ghcr.io/mll-lab-nu/efe-private:ikea-mujoco-0.3.0
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgl1 libopengl0 libglvnd0 libvulkan1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir PyOpenGL==3.1.10 imageio==2.37.0 imageio-ffmpeg==0.6.0 pillow==12.3.0
COPY nyx-requirements.txt /opt/nyx-requirements.txt
RUN python -m venv /opt/nyx \
    && /opt/nyx/bin/pip install --no-cache-dir --no-deps --require-hashes -r /opt/nyx-requirements.txt \
    && /opt/nyx/bin/python -c "import numpy, mujoco, trimesh, torch, gs_nyx.nyx_py_sdk; assert (numpy.__version__, mujoco.__version__, trimesh.__version__, torch.__version__) == ('2.3.5', '3.14.0', '5.1.0', '2.11.0+cu128')" \
    && python -c "import numpy, mujoco; assert (numpy.__version__, mujoco.__version__) == ('2.5.4', '3.14.0')"
RUN mkdir -p /opt/nyx-assets && curl -fsSL -o /opt/nyx-assets/studio_small_09_2k.hdr \
        https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_09_2k.hdr \
    && echo "36724313c0fc66dab126ff90f081b85a0b1ef47be65eda1417bd20b033f0573f  /opt/nyx-assets/studio_small_09_2k.hdr" | sha256sum -c - \
    && printf 'Studio Small 09 by Sergej Majboroda / Poly Haven\nhttps://polyhaven.com/a/studio_small_09\nLicense: CC0\n' > /opt/nyx-assets/CREDITS.txt \
    && chmod -R a+rX /opt/nyx-assets
# NVIDIA_DRIVER_CAPABILITIES=all (compose) makes the container toolkit mount the driver's graphics libraries; these files
# point the Vulkan and EGL loaders at them (as images/robotangle/Dockerfile). The toolkit's CDI mode also mounts the host's
# ICD json, which would list the GPU twice: VK_ICD_FILENAMES names ours only.
RUN mkdir -p /usr/share/vulkan/icd.d /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.0"}}\n' > /usr/share/vulkan/icd.d/nvidia_icd.json && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
ENV MUJOCO_GL=egl PYOPENGL_PLATFORM=egl NVIDIA_DRIVER_CAPABILITIES=all VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json \
    RCB_NYX_PYTHON=/opt/nyx/bin/python RCB_NYX_ENV_MAP=/opt/nyx-assets/studio_small_09_2k.hdr
