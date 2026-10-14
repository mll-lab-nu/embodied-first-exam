# eai-pandadyn: ManiSkill 3.0.1 (SAPIEN 3.0.3, CPU PhysX) + Ruckig 0.12.2 + the Panda Dynamic Scenes environment package
# (images/pandadyn/panda_dynamics/: its scenes, tasks, success predicates and the Panda's torque servo; written by
# scripts/pandadyn/sync_env.py, which leaves out everything that is not simulation code). No reference solution, recorded
# rollout or controller is in this image: tasks `FROM` it and COPY their own tooling (rcb_pandadyn.py).
# Tag = ghcr.io/mll-lab-nu/eai-pandadyn:<images/pandadyn/VERSION>; the build context is the repo root:
#   docker build -f images/pandadyn/Dockerfile -t ghcr.io/mll-lab-nu/eai-pandadyn:$(cat images/pandadyn/VERSION) .
# Physics (CPU PhysX at 1000 Hz, PhysX enhanced determinism) and the servo run on the CPU (torch CPU build). SAPIEN still
# needs a Vulkan device (the NVIDIA GPU) to build a scene at all (visual shapes create render materials) and to render the
# cameras: NVIDIA_DRIVER_CAPABILITIES=all makes the container runtime mount the driver's Vulkan/EGL libraries and the ICD
# json files below point the loaders at them (as images/robopaint/). Tasks pass the GPU through with
# environment/docker-compose.yaml (and the verifier with tests/docker-compose.yaml).
FROM nvidia/cuda:12.4.1-base-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 UV_LINK_MODE=copy NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl libvulkan1 libglvnd0 libgl1 libegl1 \
      libx11-6 libxext6 libxrender1 libgomp1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /usr/share/vulkan/icd.d /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3.0"}}\n' > /usr/share/vulkan/icd.d/nvidia_icd.json && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN curl -LsSf https://astral.sh/uv/0.12.19/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
# Python 3.11.16: the interpreter the frozen instances were verified with.
RUN uv python install 3.11.16 && uv venv -p 3.11.16 /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" VIRTUAL_ENV=/opt/venv
COPY images/pandadyn/requirements.lock /tmp/requirements.lock
RUN uv pip install --no-deps -r /tmp/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match && \
    rm -rf /root/.cache/uv /tmp/requirements.lock
# One thread per numeric library: the physics is single-threaded CPU PhysX and the servo's numpy is small; fixed thread
# counts keep floating-point reductions in the same order on every host.
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg
COPY images/pandadyn/panda_dynamics /opt/pandadyn/panda_dynamics
ENV PYTHONPATH=/opt/pandadyn
# Smoke test (no GPU at build time): the stack imports and the 25 tasks register.
RUN cd /tmp && python -c "import mani_skill, sapien, torch, ruckig, panda_dynamics as P; assert len(P.TASKS) == 25; \
print('eai-pandadyn ok: mani_skill', mani_skill.__version__, 'sapien', sapien.__version__, 'torch', torch.__version__, 'tasks', len(P.TASKS))"
WORKDIR /app
