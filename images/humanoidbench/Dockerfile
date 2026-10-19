# eai-humanoidbench: HumanoidBench (MuJoCo / dm_control / Unitree H1) environment. Infrastructure only —
# contains no benchmark code; tasks `FROM` it and COPY their own tooling. Tag = images/humanoidbench/VERSION.
# Unlike rcb-robosuite / rcb-libero this image has no CUDA base: HumanoidBench needs neither curobo nor a
# GPU. MuJoCo physics is CPU-only, so a GPU can only ever accelerate offscreen rendering — osmesa does it
# on the CPU at ~130 ms/frame (256x256), egl on the GPU at ~0.4 ms. Both backends are installed and
# rcb_hb.py picks one per run, so the same image works with and without a GPU.
# Build from the repo root (docs/benchmarks/humanoidbench.md).
FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
# libegl1 is the libglvnd EGL loader; the NVIDIA vendor driver behind it is mounted by the container
# runtime at run time, not installed here.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates tmux build-essential ffmpeg \
      libgl1 libegl1 libosmesa6 libglew2.2 libglfw3 libx11-6 && \
    rm -rf /var/lib/apt/lists/*

# Upstream has no releases or tags, so pin the commit. MIT licence, RLL @ UC Berkeley.
#
# 🚩 Clone, patch and scrub in ONE layer. A Docker layer is an immutable tarball, so anything the clone
# writes stays readable in that layer's blob even after a later layer deletes it -- `docker pull` then
# `docker save`, untar, and there is the answer key. We measured it on 0.1.4, which scrubbed three layers
# later: the clone layer held basic_locomotion_envs.py at 13350 bytes with 5 `def get_reward`, next to the
# scrubbed 4742-byte copy. The full .git directory (deleted in the install layer) was archaeology of the
# same kind, only worse -- `git show` reconstructs every file. The agent inside the container never saw
# either, because overlayfs shows it only the merged view; this is a leak to whoever pulls the image, and
# the image is meant to be public.
#
# `no-torch.patch`: `import humanoid_bench` pulls torch + the whole jax/brax stack through
# humanoid_bench.mjx.flax_to_torch, imported at five sites. Three of those imports are dead
# (envs/{reach,package,push}.py never use the symbols) and the two live ones in wrappers.py only fire for
# hierarchical policies, which this benchmark does not use. Deleting/deferring them takes the venv from
# ~1.2 G to ~450 M and removes the CUDA wheels.
#
# `scrub_oracles.py delete`: removes the trained REACHING policies under data/, the paper's baseline
# curves under logs/ and its training harnesses, and -- the important one -- every get_reward() together
# with the scoring constants and weights only it read. A dense reward IS the answer key; with it in hand
# an agent inverts an expression instead of controlling a robot. The formulas live in
# images/humanoidbench/rewards.json and are patched back only inside the verifier, which runs in a
# container of its own once the agent's is gone. rcb_hb.py (the tooling every task ships) comes along because the scrub keeps the
# helpers it calls: it is a reader of the package like any other.
#
# Physics fixes (the table, measurements and reasons: docs/benchmarks/humanoidbench.md, Physics); upstream's rewards,
# success bars and terminations are untouched:
# - MuJoCo 3.3.7, not upstream's 3.1.6 (the install layer below): 3.1.6's general convex collision gave wrong contacts.
# - `box_feet.py apply`: box feet where the feet stand on a box (h1 and h1hand: stair, balance_simple, balance_hard).
# - `upstream-fixes.patch`: room's reset (it wrote into the right hand) and powerlift's dumbbell mass.
ARG HB_COMMIT=cb1189039151c8aadaaa987b442da54383c87fab
COPY images/humanoidbench/no-torch.patch images/humanoidbench/upstream-fixes.patch images/humanoidbench/scrub_oracles.py \
     images/humanoidbench/box_feet.py images/humanoidbench/rcb_hb.py /tmp/
RUN git clone https://github.com/carlosferrazza/humanoid-bench.git /opt/humanoid-bench && \
    git -C /opt/humanoid-bench checkout --detach ${HB_COMMIT} && \
    git -C /opt/humanoid-bench apply /tmp/no-torch.patch /tmp/upstream-fixes.patch && \
    rm -rf /opt/humanoid-bench/.git /tmp/no-torch.patch /tmp/upstream-fixes.patch && \
    python /tmp/box_feet.py apply /opt/humanoid-bench && \
    python /tmp/scrub_oracles.py delete

# setup.py pins torch/brax/gymnax/mujoco-mjx alongside the real dependencies, so install the real ones
# ourselves and register the package without its requirements. Versions are setup.py's own pins, except MuJoCo
# (3.3.7, see above) and the dm_control that matches it (1.0.34, the last to accept 3.3.x). Upstream vendors
# dm_control 1.0.20's generated table of MuJoCo's array shapes (dmc_deps/dmc_sizes.py, byte-identical to that
# release's mjbindings/sizes.py), so it is swapped for the matching release's own; dmc_index.py needs no change.
RUN pip install --no-cache-dir \
      mujoco==3.3.7 dm_control==1.0.34 gymnasium==0.29.1 numpy==1.26.4 \
      imageio==2.34.2 imageio-ffmpeg==0.6.0 && \
    pip install --no-cache-dir --no-deps -e /opt/humanoid-bench && \
    cp "$(python -c 'import dm_control, os; print(os.path.dirname(dm_control.__file__))')/mujoco/wrapper/mjbindings/sizes.py" \
       /opt/humanoid-bench/humanoid_bench/dmc_deps/dmc_sizes.py

# The other half of the scrub: assert nothing survived and the package still steps. Separate from `delete`
# because it imports the package, which needs the install above -- and a separate layer is fine here,
# since by now there is nothing left to leak.
RUN MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa python /tmp/scrub_oracles.py verify && rm /tmp/scrub_oracles.py /tmp/rcb_hb.py

# The fixes must hold, or the image does not build: MuJoCo 3.3.7 with native convex collision; box feet that follow
# the mesh on exactly the three box-standing families, on which a robot with every joint locked stands still on each
# stair tread; room starts with every joint in range and no object in the floor; the dumbbell weighs 53.7 kg.
COPY images/humanoidbench/check_fixes.py /tmp/
RUN python /tmp/box_feet.py verify && python /tmp/check_fixes.py && rm /tmp/box_feet.py /tmp/check_fixes.py

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
