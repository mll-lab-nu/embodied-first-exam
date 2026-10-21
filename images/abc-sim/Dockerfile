# abc-sim: ABC Sim (`abc_sim` of github.com/amazon-far/abc @ d0832d1, Apache-2.0) on MuJoCo 3.6.0, the version its
# demonstrations were recorded with: two I2RT YAM arms at a table, CPU physics, camera images rendered over EGL on an
# NVIDIA GPU (OSMesa on the CPU where EGL does not start). Holds the simulator package, the meshes and textures the
# benchmark's frozen scenes use, and the benchmark's tooling (/opt/abc-tools: the privileged Session, the graders, the
# standard and standard-realtime adapters); tasks `FROM` it and add their frozen instance.
# Tag = ghcr.io/mll-lab-nu/efe:abc-sim-<images/abc-sim/VERSION>; the build context is the repo root:
#   docker build -f images/abc-sim/Dockerfile -t ghcr.io/mll-lab-nu/efe:abc-sim-$(cat images/abc-sim/VERSION) .
# Nothing in it is a reference solution: abc_sim ships no scripted expert or policy, and its pointers to the upstream
# demonstrations, checkpoints and asset mirror (READMEs, the asset manifest, the episode exporter, one XML comment) are
# left out in the fetch stage, whose layers are not part of this image.

# ---- fetch: the upstream package at its commit and the checksum-pinned asset packages, assembled into /out
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS fetch
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git init -q /src && git -C /src fetch -q --depth 1 https://github.com/amazon-far/abc.git \
      d0832d12651d1b260a652861a14648dc5f3660c7 && git -C /src checkout -q FETCH_HEAD
ADD --checksum=sha256:ffb892f424a4d4e26f4f3f5e9cf3118e47d1dd1b9e98ff3d2514623b604efa6a https://abc-data.timehorizons.org/sim_assets/blocks.tar.gz /pkgs/
ADD --checksum=sha256:1f6b3fddefd555b688c06f5dfb1cd111dc4e406bb3bee18f3fa42c90fd52007c https://abc-data.timehorizons.org/sim_assets/brush_flat.tar.gz /pkgs/
ADD --checksum=sha256:0e91795f17a81006f65743707a6fd3395c36a02b75d4ee934e499fe554edbfa5 https://abc-data.timehorizons.org/sim_assets/chess.tar.gz /pkgs/
ADD --checksum=sha256:0bd60a4a11e038a88cabbecc8b4baf71123d4c371f98219250c36386e9aaacf2 https://abc-data.timehorizons.org/sim_assets/cup_stacking.tar.gz /pkgs/
ADD --checksum=sha256:9746caee3de796f7da66c6d200f5a391c746e75c9941460f299fbd400b820761 https://abc-data.timehorizons.org/sim_assets/dustpan.tar.gz /pkgs/
ADD --checksum=sha256:fee5374110e3a805539fb876962765db169c91bcba9d6bf92207551cf318d5a2 https://abc-data.timehorizons.org/sim_assets/garbage_can.tar.gz /pkgs/
ADD --checksum=sha256:ed5144c0b4ae55da75a3701b5bad9ca3599977cc8b73c59996e5e1633749aad7 https://abc-data.timehorizons.org/sim_assets/i2rt_yam.tar.gz /pkgs/
ADD --checksum=sha256:06fe8d31f4849443bcdbe6decc7151d77744f4877afd3ae6cd57b98f0d7c165d https://abc-data.timehorizons.org/sim_assets/mug.tar.gz /pkgs/
ADD --checksum=sha256:988d5f6455fd24f44f046d3ee88dddb867025ea05b84bcb22ed7f168a39fd71b https://abc-data.timehorizons.org/sim_assets/mug_tree.tar.gz /pkgs/
ADD --checksum=sha256:f3b816f9bc654f03c2af4e8f277e25b8881769c4132769fd6eb591a944bfcc08 https://abc-data.timehorizons.org/sim_assets/paper_ball.tar.gz /pkgs/
ADD --checksum=sha256:5229ca71cbcf4bf243033d42a384266b0f0cdf40388e0d59484678ac60095e21 https://abc-data.timehorizons.org/sim_assets/task_bins.tar.gz /pkgs/
ADD --checksum=sha256:093c1ab6389932dab39c58d31639e353a865655a6676ee253f303f9cbc7b5ffa https://abc-data.timehorizons.org/sim_assets/task_chess.tar.gz /pkgs/
ADD --checksum=sha256:e229fc943dc245b75dbf5af236beb28e3f5d57615493572cd15d02da61454f99 https://abc-data.timehorizons.org/sim_assets/task_conveyor_pick_v2.tar.gz /pkgs/
ADD --checksum=sha256:e025985d199ae42b4b935deef42aa28adb4af625d45747120fc313976221b0b1 https://abc-data.timehorizons.org/sim_assets/task_dishrack.tar.gz /pkgs/
ADD --checksum=sha256:d51a595ff0a4078f737d71043343080d8be1b501554ebb8bf5b49f4f52269a12 https://abc-data.timehorizons.org/sim_assets/task_inhand_transfer.tar.gz /pkgs/
ADD --checksum=sha256:b0d43a4856cdd72f1aed2b9d05e489fbd1a553458d3a497917dd74b3d1950744 https://abc-data.timehorizons.org/sim_assets/task_mug_flip.tar.gz /pkgs/
ADD --checksum=sha256:a23dea938cb6abb4e907d4e4e52e2d9797221bc6dda2027f1452a8447de6cb50 https://abc-data.timehorizons.org/sim_assets/task_mug_tree.tar.gz /pkgs/
ADD --checksum=sha256:b0ac5a7da7f98d91518bb08d383c898faa44bea9fc590d7c632defe481658dd8 https://abc-data.timehorizons.org/sim_assets/task_multi_drawer_search.tar.gz /pkgs/
ADD --checksum=sha256:a389616fbbbf922bf6d444e472e9b95697eab5f0589b29b1a09575b1b2ba5aeb https://abc-data.timehorizons.org/sim_assets/task_nuts_bolts.tar.gz /pkgs/
ADD --checksum=sha256:0ef853c1a7a96561ec1b1ac9baa7f1ed79897656461b08c910b5ac1be140041d https://abc-data.timehorizons.org/sim_assets/task_put_relative.tar.gz /pkgs/
ADD --checksum=sha256:a93e7d5d4fd5204b136e368af94bcc949d7a94435f19f2d14fc792e689f9c7ca https://abc-data.timehorizons.org/sim_assets/task_water_bottles.tar.gz /pkgs/
ADD --checksum=sha256:b130c04a7b72356d2336a60ab9ab68804035bbf7d8655d41d7b5f253fa715bea https://abc-data.timehorizons.org/sim_assets/tray.tar.gz /pkgs/
COPY images/abc-sim/assemble.py images/abc-sim/assets.txt /tmp/
RUN python /tmp/assemble.py /src /pkgs /tmp/assets.txt /out

# ---- the image
FROM docker.io/library/python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
# libEGL (glvnd) finds the NVIDIA driver's EGL library through the vendor file below once the container runtime mounts
# the driver (NVIDIA_DRIVER_CAPABILITIES includes graphics); libOSMesa is the CPU fallback.
RUN apt-get update && apt-get install -y --no-install-recommends libegl1 libgl1 libglvnd0 libosmesa6 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && mkdir -p /usr/share/glvnd/egl_vendor.d && \
    printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' \
      > /usr/share/glvnd/egl_vendor.d/10_nvidia.json
COPY images/abc-sim/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --no-deps -r /tmp/requirements.lock && rm /tmp/requirements.lock
COPY --from=fetch /out /opt/abc
COPY images/abc-sim/ASSET_LICENSES.md /opt/abc/ASSET_LICENSES.md
COPY images/abc-sim/tools /opt/abc-tools
ENV PYTHONPATH=/opt/abc:/opt/abc-tools ABC_SIM_ROOT=/opt/abc PYTHONUNBUFFERED=1 NVIDIA_DRIVER_CAPABILITIES=all \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# Smoke test (no GPU at build time: OSMesa): the package imports and the tooling loads.
RUN cd /tmp && RCB_GL=osmesa python -c "import abc_sim, mujoco, rcb_abc; assert mujoco.__version__ == '3.6.0'; \
print('abc-sim ok: mujoco', mujoco.__version__, 'gl', rcb_abc.GL)"
WORKDIR /app
