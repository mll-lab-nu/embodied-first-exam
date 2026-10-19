# embodied-olympics-fun (earlier tag: robofunolympics): the Embodied Olympics simulator for the Embodied Olympics - Fun tasks (tasks/embodied-olympics-fun/README.md):
# MuJoCo 3.3.7 on CPU (bit-exact replay) with OSMesa rendering (EGL on a GPU for the standard-realtime twins, since 0.2.1), and Embodied Olympics' robot library with its
# Unitree G1 (PROTOCOL §2.1: a base image holds the simulator and its assets) at /opt/roboolympics:
#   bodies/              the robot library (model, meshes, real limits, the one servo path, the joint-group arbiter,
#                        kinematics, the walking policies that come with the robot), unchanged
#                        (with the G1's optional FALCON and AGILE walking policies, numpy ports, since 0.2.0)
#   athletics/           the G1 running policy of Embodied Olympics' athletics (run_policy.py, policy/)
# Source and file list: roboolympics/SOURCE.md; every file is checked against roboolympics/manifest.sha256 here.
# No task code, no referee and no solution is in the image: those are in the task directories.
# Build: scripts/build_images.sh (context: this directory).
FROM docker.io/library/python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    RFO_SIM_DIR=/opt/roboolympics
# The same floating-point results on every x86-64 host with AVX2: the policies' matrix products run on OpenBLAS's Haswell
# kernels whatever the CPU, and numpy's own loops (exp, tanh) never take an AVX-512 path. Without this a host with
# AVX-512 and one without round differently, and a recorded reference solution replays differently on each.
ENV OPENBLAS_CORETYPE=Haswell \
    NPY_DISABLE_CPU_FEATURES="AVX512F AVX512CD AVX512_KNL AVX512_KNM AVX512_SKX AVX512_CLX AVX512_CNL AVX512_ICL"
COPY requirements.txt /opt/eai-robofunolympics/requirements.txt
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends libosmesa6 libgl1 libegl1 \
    && pip install -r /opt/eai-robofunolympics/requirements.txt && pip check \
    && rm -rf /var/lib/apt/lists/*
COPY roboolympics /opt/roboolympics
RUN cd /opt/roboolympics && sha256sum --quiet -c manifest.sha256 \
    && test "$(find . -type f ! -name manifest.sha256 | wc -l)" = "$(wc -l < manifest.sha256)" \
    && python -c "import sys; sys.path[:0] = ['/opt/roboolympics', '/opt/roboolympics/athletics']; \
import mujoco, numpy, imageio, OpenGL, PIL; from bodies import load_body; import run_policy; \
B = load_body('unitree_g1'); from bodies.unitree_g1.falcon import Falcon; from bodies.unitree_g1.agile import Agile; \
assert Falcon(B.decl).parity() < 1e-4 and Agile(B.decl).parity() < 1e-4; \
print('mujoco', mujoco.__version__, B.name, B.revision, 'falcon + agile parity ok')"
# EGL on the GPU for the standard-realtime twins (since 0.2.1): libglvnd's EGL loader, and the ICD manifest of the NVIDIA
# vendor library the container toolkit mounts under NVIDIA_DRIVER_CAPABILITIES=graphics (on some hosts it mounts the
# library without the manifest). Inert without a GPU; the default backend stays OSMesa (MUJOCO_GL above).
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf \
    '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
WORKDIR /app
