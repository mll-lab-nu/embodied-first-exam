# eai-bigym2: BiGym 2.0 (bigym 1.0.0, Apache-2.0; Imperial College London) on MuJoCo 3.8.1: a Unitree G1 with Dex1-1
# grippers whose legs and waist NVIDIA's GR00T-WBC drives (two ONNX policies on onnxruntime, CPU; the weights ship in
# the package under the NVIDIA Open Model License). Infrastructure only: the upstream package, no benchmark code; tasks
# `FROM` it and COPY their own tooling. Physics on the CPU, rendering through EGL on an NVIDIA GPU.
# Tag = images/bigym2/VERSION. Build from the repo root:
#   docker build -f images/bigym2/Dockerfile -t ghcr.io/mll-lab-nu/eai-bigym2:$(cat images/bigym2/VERSION) .
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
# libegl1 is the libglvnd EGL loader (the NVIDIA vendor library is mounted by the container runtime); ffmpeg writes
# the replay videos (upstream's EnvTools.start_recording).
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ffmpeg libgl1 libegl1 && \
    rm -rf /var/lib/apt/lists/*
# Every dependency at upstream's own lock (uv.lock at 93ad4b3, extra `agent`, Python 3.12: `uv export --frozen
# --extra agent --no-dev --no-emit-project`), so the physics is the substrate upstream measured (bigym2-mj381-v1).
COPY images/bigym2/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
# Not in upstream's lock: the standard-mode service encodes the clients' mp4 videos through imageio's ffmpeg plugin
# (rcb_service.py). 0.1.0 lacked it, and a submit with the client's default video="mp4" ended the episode as an error.
RUN pip install --no-cache-dir imageio-ffmpeg==0.6.0
# The package only, in ONE layer with the clone it is built from: the repository also holds what a task must not ship
# (tests/fixtures/demo_endpoints.npz: a successful demonstration's final state for every task; docs; examples), and a
# file deleted in a later layer stays readable in this layer's blob for anyone who pulls the image. The wheel holds
# `bigym/` alone. Nothing in it is a solution: upstream has no scripted expert or planner, its demonstrations and its
# agents' rollouts live on the Hugging Face Hub (never fetched here; the agent reaches the model APIs only).
# Upstream rewrote its history on 2026-10-09: the release first published as 6a6632b is now 93ad4b3, with the same
# package (BIGYM_TREE, the git tree of bigym/, is checked: a later force-push that changes the package fails the build).
ARG BIGYM_COMMIT=93ad4b3faedeba35b4b330987bb298aafd207e3f
ARG BIGYM_TREE=b66136c4fb88fc1c594f6c05cf52f4f931381895
RUN git clone https://github.com/swirl-uk/BiGym2.git /tmp/bigym2 && \
    git -C /tmp/bigym2 checkout --detach "${BIGYM_COMMIT}" && \
    test "$(git -C /tmp/bigym2 rev-parse HEAD:bigym)" = "${BIGYM_TREE}" && \
    pip install --no-cache-dir --no-deps /tmp/bigym2 && \
    rm -rf /tmp/bigym2 /root/.cache && \
    python -c "import bigym, os; p = os.path.dirname(bigym.__file__); \
bad = [os.path.join(r, f) for r, _, fs in os.walk(p) for f in fs if f.endswith(('.npz', '.parquet', '.mp4', '.pkl'))]; \
assert not bad, bad"
# libglvnd finds a vendor driver through an ICD manifest; some hosts' NVIDIA runtime mounts libEGL_nvidia.so.0 but
# not the manifest (images/humanoidbench/Dockerfile). Inert without a GPU.
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf \
    '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
# The demonstrations are not part of any task: the loader stays offline even if someone opens the network.
ENV HF_HUB_OFFLINE=1 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
RUN python -c "import bigym, bigym.loco; from bigym.loco.tasks import TASKS; print('bigym', len(TASKS), 'tasks')"
WORKDIR /app
