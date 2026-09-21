# rcb-humanoidbench: HumanoidBench (MuJoCo / dm_control / Unitree H1) environment. Infrastructure only —
# contains no benchmark code; tasks `FROM` it and COPY their own tooling. Tag = images/VERSION.
# Unlike rcb-robosuite / rcb-libero this image has no CUDA base: HumanoidBench needs neither curobo nor a
# GPU. MuJoCo physics is CPU-only, so a GPU can only ever accelerate offscreen rendering — osmesa does it
# on the CPU at ~130 ms/frame (256x256), egl on the GPU at ~0.4 ms. Both backends are installed and
# rcb_hb.py picks one per run, so the same image works with and without a GPU.
# Build from repo root: scripts/build_images.sh
FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
# libegl1 is the libglvnd EGL loader; the NVIDIA vendor driver behind it is mounted by the container
# runtime at run time, not installed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates tmux build-essential ffmpeg \
      libgl1 libegl1 libosmesa6 libglew2.2 libglfw3 libx11-6 && \
    rm -rf /var/lib/apt/lists/*

# Upstream has no releases or tags, so pin the commit. MIT licence, RLL @ UC Berkeley.
ARG HB_COMMIT=cb1189039151c8aadaaa987b442da54383c87fab
RUN git clone https://github.com/carlosferrazza/humanoid-bench.git /opt/humanoid-bench && \
    git -C /opt/humanoid-bench checkout --detach ${HB_COMMIT}

# `import humanoid_bench` pulls torch + the whole jax/brax stack through humanoid_bench.mjx.flax_to_torch,
# imported at five sites. Three of those imports are dead (envs/{reach,package,push}.py never use the
# symbols) and the two live ones in wrappers.py only fire for hierarchical policies, which this benchmark
# does not use. Deleting/deferring them takes the venv from ~1.2 G to ~450 M and removes the CUDA wheels.
COPY images/humanoidbench/no-torch.patch /tmp/no-torch.patch
RUN git -C /opt/humanoid-bench apply /tmp/no-torch.patch && rm /tmp/no-torch.patch

# Upstream ships trained low-level REACHING policies under data/ (the hierarchical baseline's low level)
# and the paper's per-task baseline curves under logs/. Rolling the policy out and recording the actions
# is a ready-made submission for `reach` and a head start on every manipulation task, so both go.
COPY images/humanoidbench/scrub_oracles.py /tmp/scrub_oracles.py
RUN python /tmp/scrub_oracles.py && rm /tmp/scrub_oracles.py

# setup.py pins torch/brax/gymnax/mujoco-mjx alongside the real dependencies, so install the real ones
# ourselves and register the package without its requirements. Versions are setup.py's own pins.
RUN pip install --no-cache-dir \
      mujoco==3.1.6 dm_control==1.0.20 gymnasium==0.29.1 numpy==1.26.4 \
      imageio==2.34.2 imageio-ffmpeg==0.6.0 && \
    pip install --no-cache-dir --no-deps -e /opt/humanoid-bench && \
    find /opt/humanoid-bench -name .git -prune -exec rm -rf {} +

# libglvnd finds a vendor driver through an ICD manifest. The NVIDIA container toolkit injects
# libEGL_nvidia.so.0 whenever NVIDIA_DRIVER_CAPABILITIES includes `graphics`, but on hosts whose driver
# packaging has no /usr/share/glvnd/egl_vendor.d/10_nvidia.json it does not inject the manifest — the
# library is mounted and unreachable, and egl fails with "an OpenGL platform library has not been loaded".
# Writing it here is inert without a GPU: libglvnd just fails to dlopen the vendor and falls back.
RUN mkdir -p /usr/share/glvnd/egl_vendor.d && printf \
    '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
    > /usr/share/glvnd/egl_vendor.d/10_nvidia.json

# MUJOCO_GL is deliberately left unset in the image: rcb_hb.py resolves it per run. Pinning it here would
# override that choice. The build machine has no GPU, so the smoke test scopes osmesa to its own process.
# Smoke test: the env constructs headlessly, renders, and drags in neither torch nor jax.
RUN MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa python - <<'SMOKE'
import sys, gymnasium as gym, humanoid_bench
heavy = sorted(m for m in sys.modules if m.split(".")[0] in ("torch", "jax", "brax"))
assert not heavy, f"heavy deps leaked back in: {heavy}"
e = gym.make("h1-sit_simple-v0", render_mode="rgb_array"); e.reset(seed=0)
print("humanoid-bench ok:", e.unwrapped.model.nu, "actuators,",
      "success_bar", e.unwrapped.task.success_bar, "frame", e.render().shape)
SMOKE
WORKDIR /app
