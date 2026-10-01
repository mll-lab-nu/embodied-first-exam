# eai-kinder: KinDER (Princeton PRPL, RSS 2026; MIT) at a pinned commit. Infrastructure only -- no task code; tasks
# `FROM` it and COPY their own tooling. Tag = images/kinder/VERSION. Build from the repo root (docs/benchmarks/kinder.md).
# Physics is CPU (MuJoCo for the Dynamic3D tasks). A GPU only speeds up images: egl ~ms a frame, osmesa on the CPU far
# slower. Both are installed and the tooling picks one per run, so the same image works with and without a GPU.
FROM python:3.12-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates ffmpeg libgl1 libegl1 libosmesa6 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/*

# Upstream has no release tag for this state, so pin the commit; every dependency is pinned in requirements.txt and
# installed with --no-deps, so the environment is exactly the one the tasks were measured in.
ARG KINDER_COMMIT=5b2dbac482142b879b48449b3fa2af63f641aed3
COPY images/kinder/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.txt && \
    pip install --no-cache-dir --no-deps \
      "kindergarden @ git+https://github.com/Princeton-Robot-Planning-and-Learning/kindergarden@${KINDER_COMMIT}" && \
    rm /tmp/requirements.txt

# The MimicLabs scenes every Dynamic3D task is set in (~2 GB). Upstream downloads them from Google Drive on first use;
# fetch them once here, so a task container never needs the network for them.
RUN python -c "import kinder.utils as u; u.download_mimiclabs_assets(non_interactive=True)"
# Some tasks (the seesaw's pivot) generate meshes at reset into the package's assets/.tmp: writable for any user.
RUN d=$(python -c "import kinder, pathlib; print(pathlib.Path(kinder.__file__).parent / 'envs/dynamic3d/models/assets/.tmp')") && \
    mkdir -p "$d" && chmod 1777 "$d"

# The NVIDIA runtime mounts libEGL_nvidia.so.0 but some hosts do not inject this manifest, and without it libglvnd
# cannot find the driver. Inert without a GPU.
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf \
    '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

# Smoke test (no GPU on the build machine: osmesa, scoped to this process): a Dynamic3D task builds, steps, renders.
RUN MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa python - <<'SMOKE'
import kinder, numpy as np
kinder.register_all_environments()
e = kinder.make("kinder/Tossing3D-o1-v0", render_mode="rgb_array"); e.reset(seed=0)
e.step(np.zeros(e.action_space.shape, dtype=e.action_space.dtype))
print("kinder ok:", e.action_space.shape, "frame", e.render().shape)
SMOKE
WORKDIR /app
