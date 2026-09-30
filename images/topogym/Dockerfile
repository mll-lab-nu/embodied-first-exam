# rcb-topogym: Genesis 1.2.1 / Nyx with cu128 torch and original pyuipc 0.0.25 materials.
# Infrastructure only, no benchmark code (docs/rcb/PROTOCOL.md §1): the task tooling (rcb_topogym.py) comes with each task,
# and prune.py removes everything that could hold a reference solution. Tag = images/VERSION; build: scripts/build_images.sh
# topogym (from the repository root, which is the build context; .dockerignore keeps it small).
ARG UIPC_BUILDER=sameli/manylinux_2_34_x86_64_cuda_12.8@sha256:0b99ea5d0e32f5ad49b02de2663520f17a8dafc8739365cd7463a82ed3f0590a
FROM ${UIPC_BUILDER} AS uipc-compile
ENV PATH=/opt/python/cp311-cp311/bin:$PATH
# CUDA is already pinned in the builder; generic tools need only OS repos.
# Avoid unrelated NVIDIA repo metadata failures (e.g. stale repodata URLs).
RUN yum --disablerepo='cuda*' install -y git curl zip unzip tar gzip
COPY requirements/uipc-build.lock /recipe/uipc-build.lock
RUN python -m pip install --require-hashes -r /recipe/uipc-build.lock
COPY images/topogym/build_uipc.sh images/topogym/verify_uipc_wheel.py /recipe/
ARG UIPC_CONFIG=uipc-build.json
COPY images/topogym/${UIPC_CONFIG} /recipe/uipc-build.json
RUN bash /recipe/build_uipc.sh prepare
RUN --mount=type=cache,target=/root/.cache/vcpkg \
    --mount=type=cache,target=/build/vcpkg/downloads \
    --mount=type=cache,id=topogym-uipc-objects-${UIPC_CONFIG},target=/build/uipc-build,sharing=locked \
    bash /recipe/build_uipc.sh compile
FROM uipc-compile AS uipc-build
# Keep packaging independent of the expensive compiler stage.
COPY images/topogym/build_uipc.sh images/topogym/verify_uipc_wheel.py /recipe/
ARG UIPC_CONFIG=uipc-build.json
COPY images/topogym/${UIPC_CONFIG} /recipe/uipc-build.json
RUN bash /recipe/build_uipc.sh audit

FROM python:3.11.15-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3 AS runtime-deps
ARG CUDA_FLAVOR=cu128
ENV TOPOGYM_CUDA_FLAVOR=${CUDA_FLAVOR}
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TOPOGYM_VISUAL_ASSET_ROOT=/opt/topogym-visuals TOPOGYM_ASSET_ROOT=/opt/topogym-assets \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=all
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl ca-certificates git build-essential ffmpeg libegl1 libgl1 libglib2.0-0 \
    libx11-6 libxext6 libxrender1 libvulkan1 vulkan-tools libgomp1 ripgrep \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.11.30
ARG RUNTIME_LOCK=difficulty-eval-runtime.lock
COPY requirements/${RUNTIME_LOCK} /opt/requirements/runtime.lock
COPY images/topogym/verify_uipc_wheel.py /opt/verify_uipc_wheel.py
RUN python /opt/verify_uipc_wheel.py dependencies /opt/requirements/runtime.lock

FROM runtime-deps AS runtime
COPY --from=uipc-build /out/wheels/ /opt/uipc-wheel/
COPY images/topogym/check_gpu_stack.py /opt/check_gpu_stack.py
RUN python /opt/verify_uipc_wheel.py install /opt/uipc-wheel \
    && cp /opt/uipc-wheel/uipc-build.json /opt/uipc-build.json \
    && rm -rf /opt/uipc-wheel
# Resolve pip-provided CUDA libraries without relying on torch import order.
RUN python -c 'import site; from pathlib import Path; paths=sorted({str(p) for s in site.getsitepackages() for p in (Path(s)/"nvidia").rglob("lib") if p.is_dir()}); assert paths; Path("/etc/ld.so.conf.d/topogym-cuda.conf").write_text("\n".join(paths)+"\n")' \
    && ldconfig \
    && python /opt/check_gpu_stack.py --link-only
COPY assets/robots/ /opt/topogym-assets/robots/
RUN chmod -R a+rX /opt/topogym-assets
COPY scripts/prepare_nyx_studio.py /opt/prepare_nyx_studio.py
RUN python /opt/prepare_nyx_studio.py
COPY topogym/ /opt/topogym/topogym/
COPY images/topogym/prune.py /opt/prune.py
RUN python /opt/prune.py /opt/topogym && rm /opt/prune.py && chmod -R a+rX /opt/topogym
# Trusted limited sidecars run as the invoking UID and write artifacts here.
RUN mkdir -p /data && chmod 1777 /data
ENV PYTHONPATH=/opt/topogym TOPOGYM_SOURCE=/opt/topogym/SOURCE.json
WORKDIR /app
