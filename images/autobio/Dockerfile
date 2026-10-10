# eai-autobio: AutoBio (autobio-bench/AutoBio @ 0850421, the "preliminary version" of the ICLR 2026 benchmark): a biology
# laboratory bench on MuJoCo 3.3.0 with UR5e and ALOHA arms, laboratory instruments (thermal cycler, thermal mixer with
# a working panel and display, centrifuges), screw-capped tubes and a pipette, and AutoBio's own physics plugins (thread
# and detent mechanisms, a quasi-static liquid surface). CPU physics (bit-exact replay) and CPU rendering (OSMesa): no GPU.
# One image for the privileged tasks' environment and verifier and the standard tasks' `sim` service.
# Deliberately NOT included (strip_experts.py, in the same layer as the clone, so no layer holds them): the scripted
# expert of every task module (the benchmark's reference solutions), the modules' `__main__` demonstration generators,
# the repository history, and AutoBio's copies of openpi and RDT (policy training code).
# Tag = images/autobio/VERSION; build from the repository root (the COPYs name images/autobio/...):
#   docker build -f images/autobio/Dockerfile -t ghcr.io/mll-lab-nu/eai-autobio:$(cat images/autobio/VERSION) .
# BUILD_ONLY, never published: AutoBio's repository states no licence for its code or its assets (images/autobio/BUILD_ONLY).
FROM python@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
RUN apt-get update && apt-get install -y --no-install-recommends git libosmesa6 libgl1 libegl1 libglib2.0-0 libgomp1 ffmpeg && \
    rm -rf /var/lib/apt/lists/*
# every pip package pinned: the closure of AutoBio's own install line (autobio/README.md) with mujoco==3.3.0, resolved
# for Python 3.11 on 2026-10-07
COPY images/autobio/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && pip check && rm /tmp/requirements.txt
# Clone and scrub in ONE layer: a later layer deleting the experts would leave them in this layer's blob.
COPY images/autobio/strip_experts.py /tmp/strip_experts.py
RUN git clone -q https://github.com/autobio-bench/AutoBio.git /opt/AutoBio && cd /opt/AutoBio && \
    git checkout -q 08504213356cbfe9a82bcd33a43cd282945a45df && \
    python /tmp/strip_experts.py /opt/AutoBio/autobio && python /tmp/strip_experts.py --check /opt/AutoBio/autobio && \
    rm -rf .git openpi RoboticsDiffusionTransformer autobio/packages /tmp/strip_experts.py && \
    ! grep -rlE "^class [A-Za-z0-9_]+Expert\(" /opt/AutoBio/autobio && \
    printf '%s\n' 08504213356cbfe9a82bcd33a43cd282945a45df > /opt/autobio-commit
ENV AUTOBIO_ROOT=/opt/AutoBio/autobio
# the task modules load AutoBio's MuJoCo plugin by a relative path, so the check runs from the checkout
RUN cd /opt/AutoBio/autobio && python -c "import mani_thermal_mixer, mani_pipette, screw_tighten; import mujoco; print('AutoBio on MuJoCo', mujoco.__version__)"
RUN mkdir -p /app/output
WORKDIR /app
